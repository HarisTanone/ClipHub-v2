"""Regression coverage for AutoGrid/B-roll reliability fixes."""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.domain.entities import AssetResult, BRollSuggestion, VisualCategory
from src.infrastructure.broll_injector import BRollInjector, TEMPLATE_STYLES
from src.infrastructure.groq_analyzer import GroqAnalyzer
from src.infrastructure.asset_fetcher import AssetFetcher
from src.infrastructure.person_tracker import BBox, TrackedDetection
from src.infrastructure.podcast_reframe_engine import PodcastReframeEngine


def make_engine() -> PodcastReframeEngine:
    return PodcastReframeEngine()


def test_long_clip_sampling_covers_the_complete_timeline():
    engine = make_engine()
    total_frames = 30 * 240

    indices = engine._sample_frame_indices(total_frames, 30.0)

    assert len(indices) == engine.MAX_SAMPLES
    assert indices[0] == 0
    assert indices[-1] == total_frames - 1
    assert indices[len(indices) // 2] > total_frames * 0.45


def test_grid_does_not_open_from_one_transient_detection():
    engine = make_engine()
    timestamps = [index / 3 for index in range(12)]

    events = engine._build_layout_events(
        [True] + [False] * 11,
        timestamps,
    )

    assert events == [{"time": 0.0, "layout": "single"}]


def test_confirmed_opening_pair_is_backdated_without_blind_spot():
    engine = make_engine()
    timestamps = [index / 3 for index in range(12)]

    events = engine._build_layout_events([True] * 12, timestamps)

    assert events == [{"time": 0.0, "layout": "double"}]


def test_grid_rejects_a_face_that_would_appear_in_both_panels():
    engine = make_engine()
    geometry = {
        "crop_w": 400,
        "crop_h": 360,
        "first_crop_x": 0,
        "first_crop_y": 0,
        "second_crop_x": 240,
        "second_crop_y": 0,
    }
    detections = [
        TrackedDetection(0, BBox(260, 100, 340, 200), 0),
        TrackedDetection(1, BBox(480, 100, 560, 200), 0),
    ]

    assert engine._grid_frame_is_safe(
        detections,
        geometry,
        first_id=0,
        second_id=1,
        track_to_position={0: 0, 1: 1},
    ) is False


def test_video_broll_starts_on_event_clock_and_never_repeats_last_frame():
    injector = BRollInjector(render_engine=MagicMock())
    suggestion = BRollSuggestion(
        at_time=3.0,
        keyword="AGING POPULATION",
        template="word_pop_typography",
        duration=2.5,
        visual_category=VisualCategory.FOOTAGE,
        asset_result=AssetResult(
            local_path="/tmp/asset.mp4",
            source_api="pexels",
            license_type="pexels_license",
            original_url="test",
            asset_format="video",
        ),
    )

    graph = injector._build_filter_complex([suggestion], [])

    assert "trim=duration=2.500" in graph
    assert "setpts=PTS-STARTPTS+3.000/TB" in graph
    assert "eof_action=pass:repeatlast=0" in graph
    assert "shortest=1" not in graph


def test_text_fallback_uses_a_drawbox_expression_ffmpeg_can_evaluate():
    injector = BRollInjector(render_engine=MagicMock())

    filters = injector._build_drawtext_filter(
        text="FALLBACK TEST",
        start=3.0,
        end=5.0,
        duration=2.0,
        style=TEMPLATE_STYLES["word_pop_typography"],
        font_path=None,
    )

    assert "text_w" not in filters[0]
    assert "drawbox=" in filters[0]


def test_malformed_ai_broll_response_has_sparse_local_fallback():
    analyzer = GroqAnalyzer()
    analyzer._call_groq_llm = MagicMock(side_effect=ValueError("malformed JSON"))
    words = {
        1: [
            {"word": "global", "start": 3.2, "end": 3.6},
            {"word": "situation", "start": 3.7, "end": 4.1},
            {"word": "mengalami", "start": 4.2, "end": 4.6},
            {"word": "perubahan", "start": 4.7, "end": 5.2},
            {"word": "aging", "start": 8.0, "end": 8.4},
            {"word": "population", "start": 8.5, "end": 9.0},
        ]
    }

    result = asyncio.run(analyzer.analyze_broll_for_clips(words, {1: 12.0}))

    assert len(result["1"]) == 1
    assert 3.0 <= result["1"][0]["at_time"] < 11.0
    assert result["1"][0]["visual_category"] == "footage"


def test_splice_mode_promotes_motion_graphic_to_footage_fallback(tmp_path):
    fetcher = AssetFetcher()
    suggestion = BRollSuggestion(
        at_time=4.0,
        keyword="KUKU BERDARAH",
        template="word_pop_typography",
        duration=2.0,
        visual_category=VisualCategory.MOTION_GRAPHIC,
    )
    fetcher._fetch_via_clipscout = AsyncMock(return_value=None)

    async def resolve(current, _direction):
        assert current.visual_category == VisualCategory.FOOTAGE
        current.asset_result = AssetResult.fallback()

    fetcher._resolve_single = resolve
    with patch("src.infrastructure.asset_fetcher.settings.BROLL_SPLICE_ENABLED", True), patch(
        "src.infrastructure.asset_fetcher.settings.ASSET_FETCH_ENABLED", True
    ):
        asyncio.run(fetcher.fetch_assets([suggestion]))

    assert suggestion.visual_category == VisualCategory.FOOTAGE
