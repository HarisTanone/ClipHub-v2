"""Unit tests verifying:
1. Subtitle positioning dynamically centers to 50% in 2-grid (double) and restores to bottom in single-grid.
2. Behind-person visual overlay is strictly suppressed during 2-grid segments.
3. Subtitle-aware fallback search in AssetFetcher extracts keywords from spoken subtitles when primary keyword search fails.
4. Pexels visual expansion uses word boundaries to avoid false-positive 'ai' matching on Indonesian words like 'pantai', 'sampai', 'terbaik'.
"""
from __future__ import annotations

import os
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock

from src.domain.entities import BRollSuggestion
from src.infrastructure.pexels_client import PexelsClient, expand_visual_queries
from src.infrastructure.asset_fetcher import AssetFetcher, AssetResult
from src.infrastructure.unified_ffmpeg_compositor import UnifiedFFmpegCompositor
from src.infrastructure.skia_subtitle_renderer import SkiaSubtitleRenderer
from src.infrastructure.top_behind_subject_renderer import (
    pick_top_overlay_suggestions,
    TopOverlaySegment,
)


def test_pexels_word_boundary_prevents_false_ai_match():
    """Verify Indonesian words containing 'ai' (pantai, sampai, terbaik) do not trigger 'ai' visual expansion."""
    # 'pantai' should map to beach/coast, NOT artificial intelligence
    queries_pantai = expand_visual_queries("pantai")
    assert not any("artificial intelligence" in q for q in queries_pantai)
    assert any("beach" in q for q in queries_pantai)

    # 'sampai' does not mean AI
    queries_sampai = expand_visual_queries("sampai")
    assert not any("artificial intelligence" in q for q in queries_sampai)

    # Standalone 'ai' DOES match artificial intelligence
    queries_ai = expand_visual_queries("ai teknologi")
    assert any("artificial intelligence" in q for q in queries_ai)

    # New podcast domain terms
    queries_fight = expand_visual_queries("fight terus")
    assert any("boxing" in q or "athlete" in q for q in queries_fight)


def test_unified_compositor_subtitle_y_dynamic_grid_vs_single():
    """Verify UnifiedFFmpegCompositor dynamically centers subtitle at 50% for double grid, and restores to bottom for single."""
    compositor = UnifiedFFmpegCompositor()
    words = [{"word": "TEST", "start": 1.0, "end": 2.0}]

    # 1. Whole clip is double layout -> filters should use h*0.50
    filters_double = compositor.build_subtitle_filter_chain(
        words=words,
        style={"reframe_layout": "double", "grid_position_y": 50.0, "position_y": 80.0},
    )
    assert any("h*0.50" in f for f in filters_double)

    # 2. Whole clip is single layout -> filters should use h*0.80
    filters_single = compositor.build_subtitle_filter_chain(
        words=words,
        style={"reframe_layout": "single", "grid_position_y": 50.0, "position_y": 80.0},
    )
    assert any("h*0.80" in f for f in filters_single)

    # 3. Dynamic timeline via layout_events:
    words_timeline = [
        {"word": "FIRST", "start": 1.0, "end": 2.0},   # at t=1.5 -> single (0.80)
        {"word": "SECOND", "start": 6.0, "end": 7.0},  # at t=6.5 -> double (0.50)
        {"word": "THIRD", "start": 11.0, "end": 12.0}, # at t=11.5 -> single (0.80)
    ]
    layout_events = [
        {"time": 0.0, "layout": "single"},
        {"time": 5.0, "layout": "double"},
        {"time": 10.0, "layout": "single"},
    ]
    filters_dyn = compositor.build_subtitle_filter_chain(
        words=words_timeline,
        style={
            "layout_events": layout_events,
            "grid_position_y": 50.0,
            "position_y": 80.0,
        },
    )
    joined = " ".join(filters_dyn)
    assert "h*0.80" in joined
    assert "h*0.50" in joined


def test_skia_subtitle_renderer_dynamic_grid_position():
    """Verify SkiaSubtitleRenderer evaluates layout at time and centers to 50% on double layout."""
    renderer = SkiaSubtitleRenderer()
    
    layout_events = [
        {"time": 0.0, "layout": "single"},
        {"time": 4.0, "layout": "double"},
        {"time": 8.0, "layout": "single"},
    ]
    
    # At t=2.0: single layout
    assert renderer._get_layout_at_time(layout_events, 2.0) == "single"
    # At t=6.0: double layout
    assert renderer._get_layout_at_time(layout_events, 6.0) == "double"
    # At t=10.0: single layout
    assert renderer._get_layout_at_time(layout_events, 10.0) == "single"


def test_behind_person_overlay_blocked_during_double_grid(tmp_path):
    """Verify pick_top_overlay_suggestions rejects behind-person overlays during double-grid segments."""
    vid = tmp_path / "footage.mp4"
    vid.write_bytes(b"dummy")

    def make_sug(at, dur):
        return SimpleNamespace(
            at_time=at,
            duration=dur,
            keyword="business",
            asset_result=SimpleNamespace(
                local_path=str(vid),
                asset_format="video",
                is_fallback=False,
                source_api="pexels",
            ),
            splice_segment=None,
        )

    # Double-grid active from t=4.0 to 10.0
    blocked_grid_ranges = [(4.0, 10.0)]

    sug_during_grid = make_sug(at=5.0, dur=3.0)  # overlaps 4..10 -> MUST BE BLOCKED
    sug_in_single = make_sug(at=12.0, dur=3.0)    # outside -> ALLOWED

    picks = pick_top_overlay_suggestions(
        [sug_during_grid, sug_in_single],
        max_per_clip=2,
        blocked_ranges=blocked_grid_ranges,
    )

    # Only single-grid suggestion should be accepted
    assert len(picks) == 1
    assert picks[0].at_time == 12.0


@pytest.mark.asyncio
async def test_asset_fetcher_extracts_subtitle_queries():
    """Verify AssetFetcher extracts relevant visual keywords from spoken subtitle text."""
    fetcher = AssetFetcher()
    
    sug = BRollSuggestion(
        at_time=2.0,
        duration=3.0,
        keyword="xyz",
        template="footage",
        subtitle_text="Nah misal cari kesempatan bisnis dan ide baru di toko kita",
    )
    queries = await fetcher._extract_subtitle_queries(sug)
    
    assert len(queries) > 0
    # Checks that visual keywords were extracted from subtitle text
    assert any("business" in q or "store" in q or "shop" in q or "retail" in q for q in queries)


@pytest.mark.asyncio
async def test_asset_fetcher_subtitle_fallback_flow(tmp_path):
    """Verify AssetFetcher falls back to subtitle_text when primary keyword search returns no result."""
    fetcher = AssetFetcher()
    mock_pexels = MagicMock()
    
    dummy_vid = tmp_path / "store.mp4"
    dummy_vid.write_bytes(b"dummy video data")

    # Step 1: primary search with keyword 'xyznonexistent123' returns fallback/None
    # Step 2: secondary search with extracted subtitle query returns a candidate
    async def mock_search(query, **kwargs):
        if any(term in query.lower() for term in ("store", "retail", "shop", "toko", "business")):
            return AssetResult(
                local_path=str(dummy_vid),
                source_api="pexels",
                license_type="pexels_license",
                original_url="http://example.com/store.mp4",
                asset_format="video",
                is_fallback=False,
            )
        return AssetResult.fallback()

    mock_pexels.search = AsyncMock(side_effect=mock_search)
    fetcher._pexels = mock_pexels
    from src.domain.entities import VisualCategory
    fetcher._client_chains[VisualCategory.FOOTAGE] = [mock_pexels]

    sug = BRollSuggestion(
        at_time=2.0,
        duration=3.0,
        keyword="xyznonexistent123",
        template="footage",
        subtitle_text="buka toko kesempatan bisnis baru",
    )

    await fetcher._resolve_single(sug, creative_direction=None)
    assert sug.asset_result is not None
    assert not sug.asset_result.is_fallback
    assert os.path.exists(sug.asset_result.local_path)
    assert sug.asset_result.source_api == "pexels"


def test_pixabay_blacklist_rejects_video_9038():
    """Verify PixabayClient explicitly skips video ID 9038 and banned neuron/synapse tags."""
    from src.infrastructure.pixabay_client import PixabayClient, BANNED_VIDEO_IDS, BANNED_TAGS
    
    assert "9038" in BANNED_VIDEO_IDS or 9038 in BANNED_VIDEO_IDS
    assert "neuron" in BANNED_TAGS
    assert "synapse" in BANNED_TAGS
    assert "nerve cell" in BANNED_TAGS

    client = PixabayClient()
    hit_9038 = {"id": 9038, "tags": "nerve cell, neuron, brain", "videos": {"large": {"url": "http://example.com/9038.mp4"}}}
    hit_banned_tag = {"id": 12345, "tags": "synapse, abstract glowing", "videos": {"large": {"url": "http://example.com/synapse.mp4"}}}
    hit_valid = {"id": 67890, "tags": "office, meeting, work", "videos": {"large": {"url": "http://example.com/office.mp4"}}}

    candidates = client.filter_banned_hits([hit_9038, hit_banned_tag, hit_valid])
    assert len(candidates) == 1
    assert candidates[0]["id"] == 67890



def test_gemini_agentic_video_service_candidate_verification():
    """Verify GeminiAgenticVideoService rejects banned abstract/talking head terms."""
    from src.infrastructure.gemini_agentic_video_service import GeminiAgenticVideoService

    service = GeminiAgenticVideoService()
    assert not service.verify_candidate("Nerve Cell glowing synapse", "yellow black abstract")
    assert not service.verify_candidate("Podcast host interview face", "talking head interview")
    assert service.verify_candidate("Business meeting handshake in modern office", "office, technology, team")

