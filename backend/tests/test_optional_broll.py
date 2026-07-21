"""Regression tests for user-controlled Auto B-roll."""
import asyncio
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.services_v2 import V2PipelineService
from src.domain.entities import (
    BRollSuggestion,
    Clip,
    CreativeDirection,
    Job,
    TranscriptResult,
    TranscriptSegment,
)
from src.infrastructure.groq_analyzer import GroqAnalyzer


def make_service(**overrides):
    defaults = {
        "job_repo": AsyncMock(),
        "downloader": AsyncMock(),
        "renderer": AsyncMock(),
        "whisper_local": AsyncMock(),
    }
    defaults.update(overrides)
    return V2PipelineService(**defaults)


def test_direct_broll_is_anchored_to_real_transcript_timestamps():
    analyzer = GroqAnalyzer()
    analyzer._call_groq_llm = MagicMock(return_value=json.dumps({
        "items": [
            {
                "at_time": 13.2,
                "keyword": "aging population",
                "duration": 8,
                "visual_category": "unknown",
                "template": "unknown",
            }
        ]
    }))
    transcript = TranscriptResult(
        segments=[
            TranscriptSegment(text="Pembuka", start=0, end=2),
            TranscriptSegment(text="Ada perubahan global", start=8, end=11),
            TranscriptSegment(text="Tentang aging population", start=14, end=18),
        ],
        source="nine_router_groq",
        language="id",
        total_duration=30,
    )

    result = asyncio.run(analyzer.analyze_broll(transcript, 30))

    assert result["1"][0]["at_time"] == 14.0
    assert result["1"][0]["duration"] == 3.0
    assert result["1"][0]["visual_category"] == "footage"
    assert result["1"][0]["template"] == "word_pop_typography"


def test_broll_parser_keeps_suggestions_inside_clip_timeline():
    service = make_service()
    suggestions = service._parse_broll_suggestions(1, {
        "1": [
            {"at_time": 0, "keyword": "EARLY", "duration": 9},
            {"at_time": 19.5, "keyword": "TOO LATE", "duration": 2},
        ]
    }, clip_duration=20)

    assert len(suggestions) == 1
    assert suggestions[0].at_time == 3.0
    assert suggestions[0].duration == 3.0


def test_disabled_broll_does_not_fetch_or_render(tmp_path):
    asset_fetcher = AsyncMock()
    injector = AsyncMock()
    service = make_service(asset_fetcher=asset_fetcher, broll_injector=injector)
    clip = Clip(
        rank=1,
        score=100,
        start=0,
        end=20,
        hook="",
        reason="direct",
        broll_suggestions=[BRollSuggestion(
            at_time=5,
            keyword="TEST",
            template="word_pop_typography",
        )],
    )

    asyncio.run(service._apply_brolls(
        job=Job(job_id="off", youtube_url="upload://off", broll_enabled=False),
        job_id="off",
        clips=[clip],
        creative_direction=CreativeDirection(),
        output_dir=str(tmp_path),
        trim_results={1: True},
    ))

    asset_fetcher.fetch_assets.assert_not_awaited()
    injector.inject.assert_not_awaited()


def test_enabled_text_only_broll_does_not_reintroduce_overlay(tmp_path):
    base_path = tmp_path / "clip_01.mp4"
    base_path.write_bytes(b"video")
    output_path = tmp_path / "clip_01_brolled.mp4"

    asset_fetcher = AsyncMock()
    injector = AsyncMock()

    service = make_service(asset_fetcher=asset_fetcher, broll_injector=injector)
    clip = Clip(
        rank=1,
        score=100,
        start=0,
        end=20,
        hook="",
        reason="direct",
        broll_suggestions=[BRollSuggestion(
            at_time=5,
            keyword="TEST",
            template="word_pop_typography",
        )],
    )

    asyncio.run(service._apply_brolls(
        job=Job(job_id="on", youtube_url="upload://on", broll_enabled=True),
        job_id="on",
        clips=[clip],
        creative_direction=CreativeDirection(),
        output_dir=str(tmp_path),
        trim_results={1: True},
    ))

    asset_fetcher.fetch_assets.assert_awaited_once()
    injector.inject.assert_not_awaited()
    assert not output_path.exists()


def test_remotion_uses_brolled_video_as_its_input(tmp_path):
    (tmp_path / "clip_01.mp4").write_bytes(b"base")
    brolled_path = tmp_path / "clip_01_brolled.mp4"
    brolled_path.write_bytes(b"broll")
    remotion = AsyncMock()
    remotion.render_clip.return_value = SimpleNamespace(
        success=True,
        render_time_seconds=0.1,
        error_message="",
    )
    service = make_service(remotion_adapter=remotion)

    asyncio.run(service._render_via_remotion(
        job=Job(job_id="render", youtube_url="upload://render", broll_enabled=True),
        job_id="render",
        clips=[Clip(
            rank=1,
            score=100,
            start=0,
            end=20,
            hook="",
            reason="direct",
        )],
        clips_with_words={1: []},
        creative_direction=CreativeDirection(),
        output_dir=str(tmp_path),
        trim_results={1: True},
        reframe_data={},
        hook_style_config={},
        subtitle_style_config={},
    ))

    assert remotion.render_clip.await_args.kwargs["video_path"] == str(brolled_path)
