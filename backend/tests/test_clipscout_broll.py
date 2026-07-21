"""Unit tests for ClipScout B-Roll splice feature."""
import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.domain.entities import BRollSuggestion, SpliceSegment, VideoCandidate, VisualCategory
from src.infrastructure.clipscout_client import (
    ClipScoutClient,
    ClipScoutUnavailableError,
    build_segments_from_suggestions,
)
from src.infrastructure.clipscout_ai_selector import ClipScoutAISelector
from src.infrastructure.video_splicer import VideoSplicer
from src.infrastructure.media_timeline import MediaTimeline


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _sample_candidates():
    return [
        VideoCandidate(
            id="px_1234",
            title="Plant close-up footage",
            thumbnail_url="https://example.com/thumb.jpg",
            source_url="https://www.pexels.com/video/1234",
            embed_url="https://videos.pexels.com/1234.mp4",
            platform="pexels",
            license="royalty-free",
            duration_seconds=12,
            start_timestamp=0,
            relevance_score=0.85,
        ),
        VideoCandidate(
            id="yt_ABC123",
            title="Centella asiatica skincare",
            thumbnail_url="https://i.ytimg.com/thumb.jpg",
            source_url="https://www.youtube.com/watch?v=ABC123&t=54s",
            embed_url="https://www.youtube.com/embed/ABC123",
            platform="youtube",
            license="standard",
            duration_seconds=602,
            start_timestamp=54,
            relevance_score=0.95,
            transcript_snippet="Centella asiatica is a powerful anti-aging ingredient",
        ),
    ]


def _sample_suggestions():
    return [
        BRollSuggestion(at_time=5.0, keyword="centella asiatica", template="word_pop_typography", duration=3.0),
        BRollSuggestion(at_time=15.0, keyword="skincare routine", template="word_pop_typography", duration=2.5),
    ]


CLIPSCOUT_RESPONSE = {
    "results": [
        {
            "segmentId": "1",
            "videos": [
                {
                    "id": "px_5452747",
                    "title": "Close Shot Plants",
                    "thumbnailUrl": "https://images.pexels.com/thumb.jpg",
                    "sourceUrl": "https://www.pexels.com/video/5452747/",
                    "embedUrl": "https://videos.pexels.com/5452747-hd.mp4",
                    "platform": "pexels",
                    "license": "royalty-free",
                    "durationSeconds": 12,
                    "startTimestamp": 1,
                    "relevanceScore": 0.6,
                },
                {
                    "id": "yt_XSsFt2Zf8Rg",
                    "title": "What is Centella Asiatica?",
                    "thumbnailUrl": "https://i.ytimg.com/vi/thumb.jpg",
                    "sourceUrl": "https://www.youtube.com/watch?v=XSsFt2Zf8Rg&t=54s",
                    "embedUrl": "https://www.youtube.com/embed/XSsFt2Zf8Rg",
                    "platform": "youtube",
                    "license": "standard",
                    "durationSeconds": 602,
                    "startTimestamp": 54,
                    "relevanceScore": 0.95,
                    "transcriptSnippet": "what is Centella asiatica?",
                    "transcriptReason": "Direct explanation of the ingredient",
                },
            ],
        }
    ],
    "segments": [{"id": "1", "text": "centella asiatica"}],
}


# ─── Task 9.1: ClipScoutClient Tests ──────────────────────────────────────────

class TestClipScoutClient:
    """Test ClipScout API client: success, retry, timeout scenarios."""

    @pytest.fixture
    def client(self):
        with patch("src.infrastructure.clipscout_client.settings") as mock_settings:
            mock_settings.CLIPSCOUT_API_URL = "https://www.clipscout.app/api/search"
            mock_settings.CLIPSCOUT_TIMEOUT = 15
            mock_settings.CLIPSCOUT_MAX_RETRIES = 2
            mock_settings.CLIPSCOUT_ENABLED_SOURCES = "pexels,pixabay,youtube_cc,youtube_protected"
            return ClipScoutClient()

    def test_parse_video_candidates_success(self, client):
        """Test parsing valid ClipScout response into VideoCandidate objects."""
        result = client.parse_video_candidates(CLIPSCOUT_RESPONSE)
        assert "1" in result
        assert len(result["1"]) == 2
        assert result["1"][0].id == "px_5452747"
        assert result["1"][0].platform == "pexels"
        assert result["1"][0].license == "royalty-free"
        assert result["1"][1].id == "yt_XSsFt2Zf8Rg"
        assert result["1"][1].relevance_score == 0.95

    def test_parse_video_candidates_empty(self, client):
        """Test empty response returns empty dict."""
        result = client.parse_video_candidates({"results": []})
        assert result == {}

    def test_parse_video_candidates_malformed(self, client):
        """Test malformed video entries that cause TypeError/ValueError are skipped."""
        malformed = {
            "results": [{"segmentId": "1", "videos": [
                {"durationSeconds": "not_a_number"},  # int() will raise ValueError
            ]}]
        }
        result = client.parse_video_candidates(malformed)
        # Should skip malformed entry that raises ValueError
        assert "1" not in result or len(result.get("1", [])) == 0

    def test_build_segments_from_suggestions(self):
        """Test building ClipScout segments from BRollSuggestion list."""
        suggestions = _sample_suggestions()
        segments = build_segments_from_suggestions(suggestions)
        assert len(segments) == 2
        assert segments[0]["id"] == "1"
        assert segments[0]["text"] == "centella asiatica"
        assert segments[0]["topic"] == "centella asiatica"
        assert segments[0]["searchQueries"] == ["centella asiatica"]
        assert segments[1]["id"] == "2"
        assert segments[1]["text"] == "skincare routine"

    def test_build_segments_skips_empty_keywords(self):
        """Test that suggestions with empty keywords are skipped."""
        suggestions = [
            BRollSuggestion(at_time=5.0, keyword="", template="word_pop_typography", duration=3.0),
            BRollSuggestion(at_time=10.0, keyword="valid keyword", template="word_pop_typography", duration=2.0),
        ]
        segments = build_segments_from_suggestions(suggestions)
        assert len(segments) == 1
        assert segments[0]["text"] == "valid keyword"


# ─── Task 9.2: ClipScoutAISelector Tests ──────────────────────────────────────

class TestClipScoutAISelector:
    """Test AI video selection: success and fallback scenarios."""

    def test_fallback_select_highest_relevance(self):
        """Test fallback selects video with highest relevanceScore."""
        selector = ClipScoutAISelector()
        candidates = _sample_candidates()
        result = selector._fallback_select(candidates)
        # YouTube has higher relevance (0.95 vs 0.85)
        assert result.id == "yt_ABC123"
        assert result.relevance_score == 0.95

    def test_fallback_prefers_royalty_free_when_equal_score(self):
        """Test fallback prefers royalty-free when scores are equal."""
        selector = ClipScoutAISelector()
        candidates = [
            VideoCandidate(
                id="px_1", title="A", thumbnail_url="", source_url="",
                embed_url="", platform="pexels", license="royalty-free",
                duration_seconds=10, start_timestamp=0, relevance_score=0.9,
            ),
            VideoCandidate(
                id="yt_1", title="B", thumbnail_url="", source_url="",
                embed_url="", platform="youtube", license="standard",
                duration_seconds=100, start_timestamp=0, relevance_score=0.9,
            ),
        ]
        result = selector._fallback_select(candidates)
        assert result.id == "px_1"  # Royalty-free wins as tiebreaker

    def test_fallback_returns_none_for_empty(self):
        """Test fallback returns None for empty candidate list."""
        selector = ClipScoutAISelector()
        assert selector._fallback_select([]) is None

    @patch("src.infrastructure.clipscout_ai_selector.get_nine_router_client")
    def test_select_best_with_ai_failure_falls_back(self, mock_get_client):
        """Test that AI failure falls back to relevanceScore selection."""
        mock_client = MagicMock()
        mock_client.is_configured = True
        mock_client.chat.side_effect = RuntimeError("AI timeout")
        mock_get_client.return_value = mock_client

        selector = ClipScoutAISelector()
        candidates = _sample_candidates()
        result = selector.select_best(candidates, keyword="test", required_duration=2.0)
        assert result is not None
        assert result.id == "yt_ABC123"  # Highest relevance

    @patch("src.infrastructure.clipscout_ai_selector.get_nine_router_client")
    def test_select_best_with_ai_success(self, mock_get_client):
        """Test successful AI selection returns correct video."""
        mock_client = MagicMock()
        mock_client.is_configured = True
        mock_client.chat.return_value = json.dumps(
            {"selected_id": "px_1234", "start_timestamp": 0, "reason": "royalty-free plant footage"}
        )
        mock_get_client.return_value = mock_client

        selector = ClipScoutAISelector()
        candidates = _sample_candidates()
        result = selector.select_best(candidates, keyword="centella", required_duration=2.0)
        assert result is not None
        assert result.id == "px_1234"

    def test_select_best_empty_candidates(self):
        """Test select_best returns None for empty candidates."""
        selector = ClipScoutAISelector()
        result = selector.select_best([], keyword="test")
        assert result is None


# ─── Task 9.3: VideoSplicer Tests ─────────────────────────────────────────────

class TestVideoSplicer:
    """Test VideoSplicer overlap validation and segment ordering."""

    def test_validate_no_overlap_valid(self):
        """Test valid segments (>1s gap) pass validation."""
        splicer = VideoSplicer()
        segments = [
            SpliceSegment(footage_path="/tmp/a.mp4", at_time=5.0, duration=2.0, keyword="a", source_id="1", platform="pexels"),
            SpliceSegment(footage_path="/tmp/b.mp4", at_time=10.0, duration=2.0, keyword="b", source_id="2", platform="pexels"),
        ]
        assert splicer._validate_no_overlap(segments) is True

    def test_validate_no_overlap_overlapping(self):
        """Test overlapping segments (< 1s gap) fail validation."""
        splicer = VideoSplicer()
        segments = [
            SpliceSegment(footage_path="/tmp/a.mp4", at_time=5.0, duration=3.0, keyword="a", source_id="1", platform="pexels"),
            SpliceSegment(footage_path="/tmp/b.mp4", at_time=7.5, duration=2.0, keyword="b", source_id="2", platform="pexels"),
        ]
        # Gap = 7.5 - (5.0 + 3.0) = -0.5s < 1.0s
        assert splicer._validate_no_overlap(segments) is False

    def test_validate_no_overlap_exact_boundary(self):
        """Test segments with exactly 1s gap pass validation."""
        splicer = VideoSplicer()
        segments = [
            SpliceSegment(footage_path="/tmp/a.mp4", at_time=5.0, duration=2.0, keyword="a", source_id="1", platform="pexels"),
            SpliceSegment(footage_path="/tmp/b.mp4", at_time=8.0, duration=2.0, keyword="b", source_id="2", platform="pexels"),
        ]
        # Gap = 8.0 - (5.0 + 2.0) = 1.0s >= 1.0s
        assert splicer._validate_no_overlap(segments) is True

    def test_validate_no_overlap_single_segment(self):
        """Test single segment always passes validation."""
        splicer = VideoSplicer()
        segments = [
            SpliceSegment(footage_path="/tmp/a.mp4", at_time=5.0, duration=2.0, keyword="a", source_id="1", platform="pexels"),
        ]
        assert splicer._validate_no_overlap(segments) is True

    def test_splice_returns_clip_path_when_no_segments(self):
        """Test splice with empty segments returns original clip path."""
        splicer = VideoSplicer()
        result = asyncio.run(splicer.splice("/tmp/clip.mp4", [], "/tmp/out.mp4"))
        assert result == "/tmp/clip.mp4"

    def test_splice_returns_clip_path_when_clip_missing(self):
        """Test splice with non-existent clip returns original path."""
        splicer = VideoSplicer()
        segments = [
            SpliceSegment(footage_path="/tmp/footage.mp4", at_time=5.0, duration=2.0, keyword="a", source_id="1", platform="pexels"),
        ]
        result = asyncio.run(splicer.splice("/tmp/nonexistent.mp4", segments, "/tmp/out.mp4"))
        assert result == "/tmp/nonexistent.mp4"

    def test_splice_all_aborts_when_final_source_part_fails(self, tmp_path):
        """A failed long tail must not become a successful truncated output."""
        splicer = VideoSplicer()
        source = tmp_path / "source.mp4"
        footage = tmp_path / "footage.mp4"
        source.write_bytes(b"source")
        footage.write_bytes(b"footage")
        segment = SpliceSegment(
            footage_path=str(footage), at_time=30.0, duration=2.5,
            keyword="test", source_id="1", platform="youtube",
        )

        async def extract(_source, start, end, output):
            if end == pytest.approx(98.8):
                return False
            open(output, "wb").close()
            return True

        with patch(
            "src.infrastructure.video_splicer.probe_media_timeline",
            return_value=MediaTimeline(98.8, 0.0, 98.8, 0.0, 98.8),
        ):
            splicer._extract_video_segment = AsyncMock(side_effect=extract)
            result = asyncio.run(splicer._splice_all(
                str(source), [segment], str(tmp_path / "out.mp4"),
                str(tmp_path), [],
            ))

        assert result is None
        assert splicer._extract_video_segment.await_count == 2

    def test_validate_sync_rejects_truncated_video(self):
        """Regression: 32.2s video with 98.8s audio must be rejected."""
        source_timeline = MediaTimeline(98.8, 0.0, 98.8, 0.0, 98.8)
        output_timeline = MediaTimeline(98.8, 0.0, 32.2, 0.0, 98.8)

        with patch(
            "src.infrastructure.video_splicer.probe_media_timeline",
            side_effect=[source_timeline, output_timeline],
        ), patch(
            "src.infrastructure.video_splicer.timeline_is_safe",
            return_value=False,
        ) as safe:
            assert VideoSplicer()._validate_sync("output.mp4", "source.mp4") is False

        safe.assert_called_once_with(
            "output.mp4", expected_duration=98.8, max_start_drift=0.1,
            max_end_drift=0.25, max_duration_error=0.25,
        )

    def test_validate_sync_fails_closed_when_probe_fails(self):
        with patch(
            "src.infrastructure.video_splicer.probe_media_timeline",
            return_value=None,
        ):
            assert VideoSplicer()._validate_sync("output.mp4", "source.mp4") is False


# ─── Task 9.4: Fallback Chain Tests ───────────────────────────────────────────

class TestFallbackChain:
    """Test the full fallback chain: ClipScout → Legacy → drawtext."""

    def test_clipscout_unavailable_error_raised(self):
        """Test ClipScoutUnavailableError is a RuntimeError subclass."""
        err = ClipScoutUnavailableError("test message")
        assert isinstance(err, RuntimeError)
        assert "test message" in str(err)

    def test_suggestion_splice_segment_defaults_to_none(self):
        """Test BRollSuggestion has splice_segment=None by default."""
        s = BRollSuggestion(at_time=5.0, keyword="test", template="word_pop_typography")
        assert s.splice_segment is None

    def test_suggestion_can_attach_splice_segment(self):
        """Test splice_segment can be attached to BRollSuggestion."""
        s = BRollSuggestion(at_time=5.0, keyword="test", template="word_pop_typography")
        s.splice_segment = SpliceSegment(
            footage_path="/tmp/footage.mp4",
            at_time=5.0, duration=2.0,
            keyword="test", source_id="px_123", platform="pexels",
        )
        assert s.splice_segment.platform == "pexels"
        assert s.splice_segment.footage_path == "/tmp/footage.mp4"
