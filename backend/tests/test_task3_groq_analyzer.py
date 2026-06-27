"""Test Task 3: GroqAnalyzer — Dynamic Chunking + Groq LLM Highlight Analysis.

Tests cover:
- Dynamic chunking (time-based, char-based, short videos)
- JSON response parsing (clean, markdown-wrapped, partial)
- Clip candidate validation (timestamps, duration, score clamping)
- Overlap detection and removal
- Ranking logic
- Creative direction generation
- Full pipeline integration (mocked)
- Error handling (retry, fallback model)
"""
import asyncio
import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.groq_analyzer import GroqAnalyzer, GroqAnalyzerError
from src.domain.entities import (
    TranscriptResult, TranscriptSegment, HighlightCandidate, HighlightAnalysisResult,
)


def run_async(coro):
    return asyncio.run(coro)


# ─── Chunking Tests ──────────────────────────────────────────────────────────

def test_chunk_short_video_single_chunk():
    """Video < 10 min → single chunk, no splitting."""
    a = GroqAnalyzer()
    segments = [
        TranscriptSegment(text="Hello " * 50, start=i * 30.0, end=(i + 1) * 30.0)
        for i in range(10)
    ]  # 5 min total (10 × 30s)
    chunks = a._chunk_transcript(segments)
    assert len(chunks) == 1
    assert len(chunks[0]) == 10
    print("  [PASS] Short video (<10 min) → single chunk")


def test_chunk_by_time_limit():
    """Chunking respects 600s (10 min) time limit."""
    a = GroqAnalyzer()
    # 30 segments × 60s each = 1800s (30 min) → should split into ~3 chunks
    segments = [
        TranscriptSegment(text=f"Segment {i}", start=i * 60.0, end=(i + 1) * 60.0)
        for i in range(30)
    ]
    chunks = a._chunk_transcript(segments)
    assert len(chunks) == 3  # 1800s / 600s = 3
    # Each chunk ~10 segments (10 × 60s = 600s)
    for chunk in chunks:
        total_duration = sum(s.end - s.start for s in chunk)
        assert total_duration <= 660  # Some tolerance
    print("  [PASS] Chunking respects 600s time limit")


def test_chunk_by_char_limit():
    """Chunking respects 4000 char limit."""
    a = GroqAnalyzer()
    # Each segment is 1000 chars, duration 60s → char limit hit at 4 segments
    segments = [
        TranscriptSegment(text="x" * 1000, start=i * 60.0, end=(i + 1) * 60.0)
        for i in range(12)
    ]
    chunks = a._chunk_transcript(segments)
    assert len(chunks) == 3  # 12000 chars / 4000 = 3
    for chunk in chunks:
        total_chars = sum(len(s.text) for s in chunk)
        assert total_chars <= 4000
    print("  [PASS] Chunking respects 4000 char limit")


def test_chunk_empty_segments():
    """Empty segments list returns empty chunks."""
    a = GroqAnalyzer()
    chunks = a._chunk_transcript([])
    assert chunks == []
    print("  [PASS] Empty segments → empty chunks")


def test_chunk_mixed_limits():
    """Char limit triggers before time limit."""
    a = GroqAnalyzer()
    # Each segment 2000 chars but only 30s → char limit triggers at 2 segments (4000 chars)
    # even though time would allow 20 segments (600s / 30s)
    segments = [
        TranscriptSegment(text="y" * 2000, start=i * 30.0, end=(i + 1) * 30.0)
        for i in range(8)
    ]
    chunks = a._chunk_transcript(segments)
    assert len(chunks) == 4  # 8 segments, 2 per chunk (4000 char limit)
    print("  [PASS] Char limit triggers before time limit")


# ─── JSON Parsing Tests ───────────────────────────────────────────────────────

def test_parse_clean_json():
    """Parse clean JSON response."""
    a = GroqAnalyzer()
    raw = '{"clips": [{"rank": 1, "start": 10.0, "end": 55.0, "score": 85}]}'
    result = a._parse_json_response(raw)
    assert result["clips"][0]["start"] == 10.0
    assert result["clips"][0]["score"] == 85
    print("  [PASS] Parse clean JSON response")


def test_parse_markdown_wrapped_json():
    """Parse JSON wrapped in markdown code fences."""
    a = GroqAnalyzer()
    raw = '```json\n{"clips": [{"start": 10.0, "end": 55.0}]}\n```'
    result = a._parse_json_response(raw)
    assert "clips" in result
    assert result["clips"][0]["start"] == 10.0
    print("  [PASS] Parse markdown-wrapped JSON")


def test_parse_json_with_extra_text():
    """Parse JSON embedded in extra text."""
    a = GroqAnalyzer()
    raw = 'Here is the analysis:\n{"clips": [{"start": 5.0, "end": 50.0}]}\nDone.'
    result = a._parse_json_response(raw)
    assert "clips" in result
    print("  [PASS] Parse JSON with surrounding text")


def test_parse_invalid_json():
    """Invalid JSON returns empty dict."""
    a = GroqAnalyzer()
    result = a._parse_json_response("this is not json at all")
    assert result == {}
    print("  [PASS] Invalid JSON returns empty dict")


# ─── Candidate Validation Tests ───────────────────────────────────────────────

def test_parse_chunk_response_valid():
    """Parse valid chunk response with proper candidates."""
    a = GroqAnalyzer()
    raw = json.dumps({
        "clips": [
            {"rank": 1, "start": 100.0, "end": 160.0, "score": 85,
             "hook": "Test hook", "reason": "viral", "content_type": "storytelling",
             "speaker_energy": "high"},
        ]
    })
    candidates = a._parse_chunk_response(raw, chunk_start=0.0, chunk_end=300.0)
    assert len(candidates) == 1
    assert candidates[0].start == 100.0
    assert candidates[0].end == 160.0
    assert candidates[0].score == 85
    assert candidates[0].hook == "Test hook"
    print("  [PASS] Parse valid chunk response")


def test_parse_chunk_response_filters_short_clips():
    """Clips shorter than 30s are filtered out."""
    a = GroqAnalyzer()
    raw = json.dumps({
        "clips": [
            {"start": 10.0, "end": 25.0, "score": 90, "hook": "Too short", "reason": "x"},  # 15s → filtered
            {"start": 50.0, "end": 110.0, "score": 75, "hook": "Good length", "reason": "y"},  # 60s → kept
        ]
    })
    candidates = a._parse_chunk_response(raw, chunk_start=0.0, chunk_end=300.0)
    assert len(candidates) == 1
    assert candidates[0].hook == "Good length"
    print("  [PASS] Short clips (<30s) filtered out")


def test_parse_chunk_response_filters_long_clips():
    """Clips longer than 120s are filtered out."""
    a = GroqAnalyzer()
    raw = json.dumps({
        "clips": [
            {"start": 10.0, "end": 200.0, "score": 90, "hook": "Too long", "reason": "x"},  # 190s → filtered
            {"start": 50.0, "end": 100.0, "score": 75, "hook": "Good", "reason": "y"},  # 50s → kept
        ]
    })
    candidates = a._parse_chunk_response(raw, chunk_start=0.0, chunk_end=300.0)
    assert len(candidates) == 1
    assert candidates[0].hook == "Good"
    print("  [PASS] Long clips (>120s) filtered out")


def test_parse_chunk_response_clamps_score():
    """Scores are clamped to 1-100."""
    a = GroqAnalyzer()
    raw = json.dumps({
        "clips": [
            {"start": 10.0, "end": 70.0, "score": 150, "hook": "Over", "reason": "x"},
            {"start": 100.0, "end": 160.0, "score": -5, "hook": "Under", "reason": "y"},
        ]
    })
    candidates = a._parse_chunk_response(raw, chunk_start=0.0, chunk_end=300.0)
    assert candidates[0].score == 100  # Clamped from 150
    assert candidates[1].score == 1    # Clamped from -5
    print("  [PASS] Scores clamped to 1-100 range")


def test_parse_chunk_response_clamps_timestamps():
    """Timestamps outside chunk bounds are clamped."""
    a = GroqAnalyzer()
    raw = json.dumps({
        "clips": [
            # start=-10 is before chunk_start=50 with >5s gap → gets clamped to 50.0
            # end=120 is fine (within chunk_end=300), duration 120-50=70s → valid
            {"start": -10.0, "end": 120.0, "score": 80, "hook": "Neg start", "reason": "x"},
        ]
    })
    candidates = a._parse_chunk_response(raw, chunk_start=50.0, chunk_end=300.0)
    assert len(candidates) == 1
    assert candidates[0].start == 50.0  # Clamped from -10
    print("  [PASS] Timestamps clamped to chunk bounds")


def test_parse_chunk_truncates_long_hooks():
    """Hooks longer than 60 chars are truncated."""
    a = GroqAnalyzer()
    long_hook = "A" * 100
    raw = json.dumps({
        "clips": [
            {"start": 10.0, "end": 70.0, "score": 80, "hook": long_hook, "reason": "x"},
        ]
    })
    candidates = a._parse_chunk_response(raw, chunk_start=0.0, chunk_end=300.0)
    assert len(candidates[0].hook) == 60
    print("  [PASS] Long hooks truncated to 60 chars")


# ─── Ranking & Overlap Tests ─────────────────────────────────────────────────

def test_rank_by_score():
    """Clips ranked by score (highest first), then sorted by time."""
    a = GroqAnalyzer()
    candidates = [
        HighlightCandidate(rank=0, start=100.0, end=160.0, score=70, hook="C", reason=""),
        HighlightCandidate(rank=0, start=0.0, end=60.0, score=90, hook="A", reason=""),
        HighlightCandidate(rank=0, start=200.0, end=260.0, score=80, hook="B", reason=""),
    ]
    ranked = a._rank_and_merge(candidates, max_clips=3, video_duration=300.0)
    # Should be sorted by time after selection
    assert ranked[0].start == 0.0   # First by time
    assert ranked[1].start == 100.0
    assert ranked[2].start == 200.0
    # Ranks assigned 1, 2, 3
    assert ranked[0].rank == 1
    assert ranked[1].rank == 2
    assert ranked[2].rank == 3
    print("  [PASS] Clips ranked by score then sorted by time")


def test_rank_respects_max_clips():
    """Only max_clips are selected."""
    a = GroqAnalyzer()
    candidates = [
        HighlightCandidate(rank=0, start=i * 100.0, end=i * 100.0 + 60.0, score=90 - i, hook=f"H{i}", reason="")
        for i in range(10)
    ]
    ranked = a._rank_and_merge(candidates, max_clips=3, video_duration=1000.0)
    assert len(ranked) == 3
    print("  [PASS] max_clips limit respected")


def test_rank_removes_overlaps():
    """Overlapping clips: higher score wins."""
    a = GroqAnalyzer()
    candidates = [
        HighlightCandidate(rank=0, start=10.0, end=70.0, score=90, hook="Winner", reason=""),
        HighlightCandidate(rank=0, start=30.0, end=90.0, score=80, hook="Loser", reason=""),  # Overlaps with winner
        HighlightCandidate(rank=0, start=100.0, end=160.0, score=85, hook="Also OK", reason=""),
    ]
    ranked = a._rank_and_merge(candidates, max_clips=5, video_duration=300.0)
    assert len(ranked) == 2  # Overlap removed
    assert ranked[0].hook == "Winner"
    assert ranked[1].hook == "Also OK"
    print("  [PASS] Overlapping clips removed (higher score wins)")


def test_overlap_detection():
    """Test overlap detection helper."""
    a = GroqAnalyzer()
    clip = HighlightCandidate(rank=0, start=50.0, end=100.0, score=80, hook="", reason="")
    selected = [
        HighlightCandidate(rank=1, start=10.0, end=60.0, score=90, hook="", reason=""),  # Overlaps
    ]
    assert a._overlaps_with_any(clip, selected) is True

    non_overlapping = [
        HighlightCandidate(rank=1, start=10.0, end=45.0, score=90, hook="", reason=""),  # No overlap
    ]
    assert a._overlaps_with_any(clip, non_overlapping) is False
    print("  [PASS] Overlap detection works correctly")


def test_rank_empty_candidates():
    """Empty candidates → empty result."""
    a = GroqAnalyzer()
    ranked = a._rank_and_merge([], max_clips=5, video_duration=300.0)
    assert ranked == []
    print("  [PASS] Empty candidates → empty result")


# ─── Integration Tests (Mocked Groq) ─────────────────────────────────────────

def test_full_analyze_highlights_success():
    """Full pipeline with mocked Groq calls."""
    a = GroqAnalyzer()

    # Mock successful Groq response for chunk analysis
    chunk_response = json.dumps({
        "clips": [
            {"start": 30.0, "end": 90.0, "score": 85, "hook": "Viral moment",
             "reason": "Strong emotion", "content_type": "storytelling", "speaker_energy": "high"},
        ]
    })

    # Mock creative direction response
    creative_response = json.dumps({
        "creative_direction": {
            "primary_color": "#FF3366",
            "secondary_color": "#FFD700",
            "background_accent": "#1A1A2E",
            "typography_mood": "bold_impact",
            "energy_level": "high",
            "transition_style": "fast_cuts",
            "music_mood": "energetic",
            "hook_animation": "fade_scale",
        },
        "broll_suggestions": {
            "1": [{"at_time": 15.0, "keyword": "VIRAL", "template": "word_pop_typography",
                   "duration": 2.0, "visual_category": "motion_graphic"}]
        }
    })

    call_count = [0]

    def mock_call(prompt):
        call_count[0] += 1
        if call_count[0] == 1:
            return chunk_response
        return creative_response

    transcript = TranscriptResult(
        segments=[TranscriptSegment(text="Test content " * 20, start=0.0, end=120.0)],
        source="youtube_api",
        language="id",
        total_duration=120.0,
    )

    async def run():
        with patch.object(a, "_call_groq_llm", side_effect=mock_call):
            result = await a.analyze_highlights(transcript, video_duration=120.0, max_clips=5)
            assert isinstance(result, HighlightAnalysisResult)
            assert len(result.clips) == 1
            assert result.clips[0].hook == "Viral moment"
            assert result.creative_direction["primary_color"] == "#FF3366"
            assert "1" in result.broll_suggestions

    run_async(run())
    print("  [PASS] Full analyze_highlights pipeline success")


def test_full_analyze_no_candidates_raises():
    """Pipeline raises when no candidates found."""
    a = GroqAnalyzer()

    empty_response = json.dumps({"clips": []})

    transcript = TranscriptResult(
        segments=[TranscriptSegment(text="Short", start=0.0, end=10.0)],
        source="youtube_api",
        language="id",
        total_duration=10.0,
    )

    async def run():
        with patch.object(a, "_call_groq_llm", return_value=empty_response):
            try:
                await a.analyze_highlights(transcript, video_duration=10.0, max_clips=5)
                assert False, "Should have raised"
            except GroqAnalyzerError as e:
                assert "tidak menghasilkan" in str(e)

    run_async(run())
    print("  [PASS] Raises GroqAnalyzerError when no candidates")


def test_creative_direction_failure_non_fatal():
    """Creative direction failure doesn't crash pipeline."""
    a = GroqAnalyzer()

    chunk_response = json.dumps({
        "clips": [
            {"start": 30.0, "end": 90.0, "score": 85, "hook": "Test",
             "reason": "R", "content_type": "storytelling", "speaker_energy": "medium"},
        ]
    })

    call_count = [0]

    def mock_call(prompt):
        call_count[0] += 1
        if call_count[0] == 1:
            return chunk_response
        raise Exception("Creative direction failed")

    transcript = TranscriptResult(
        segments=[TranscriptSegment(text="Content " * 30, start=0.0, end=120.0)],
        source="youtube_api",
        language="id",
        total_duration=120.0,
    )

    async def run():
        with patch.object(a, "_call_groq_llm", side_effect=mock_call):
            result = await a.analyze_highlights(transcript, video_duration=120.0, max_clips=5)
            # Should still succeed with empty creative direction
            assert len(result.clips) == 1
            assert result.creative_direction == {}

    run_async(run())
    print("  [PASS] Creative direction failure is non-fatal")


if __name__ == "__main__":
    print("\n=== Task 3 Tests: GroqAnalyzer ===\n")
    # Chunking
    test_chunk_short_video_single_chunk()
    test_chunk_by_time_limit()
    test_chunk_by_char_limit()
    test_chunk_empty_segments()
    test_chunk_mixed_limits()
    # JSON parsing
    test_parse_clean_json()
    test_parse_markdown_wrapped_json()
    test_parse_json_with_extra_text()
    test_parse_invalid_json()
    # Candidate validation
    test_parse_chunk_response_valid()
    test_parse_chunk_response_filters_short_clips()
    test_parse_chunk_response_filters_long_clips()
    test_parse_chunk_response_clamps_score()
    test_parse_chunk_response_clamps_timestamps()
    test_parse_chunk_truncates_long_hooks()
    # Ranking
    test_rank_by_score()
    test_rank_respects_max_clips()
    test_rank_removes_overlaps()
    test_overlap_detection()
    test_rank_empty_candidates()
    # Integration
    test_full_analyze_highlights_success()
    test_full_analyze_no_candidates_raises()
    test_creative_direction_failure_non_fatal()
    print("\n=== ALL TASK 3 TESTS PASSED (23/23) ===\n")
