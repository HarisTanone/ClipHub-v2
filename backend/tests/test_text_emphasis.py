"""Regression tests for optional AI cinematic text."""
import asyncio
import os
import sys
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.services_v2 import V2PipelineService
from src.domain.entities import Clip, Job
from src.infrastructure.text_emphasis import (
    anchor_text_emphasis_response,
    normalise_text_emphasis_style,
)
from src.presentation.schemas.jobs import UploadJobOptions


def _words(count=40):
    return [
        {"word": f"kata{i}", "start": i * 0.5, "end": i * 0.5 + 0.35}
        for i in range(count)
    ]


def _service():
    return V2PipelineService(
        job_repo=AsyncMock(),
        downloader=AsyncMock(),
        renderer=AsyncMock(),
        whisper_local=AsyncMock(),
    )


def test_option_is_explicitly_disabled_by_default_and_style_is_validated():
    options = UploadJobOptions()
    assert options.text_emphasis_enabled is False
    configured = UploadJobOptions(
        text_emphasis_enabled=True,
        text_emphasis_style_config={"effectMode": "behind_person"},
    )
    assert configured.text_emphasis_enabled is True


def test_ai_word_ids_are_rebuilt_from_whisper_and_capped_at_two():
    words = _words()
    result = anchor_text_emphasis_response(
        {"clips": {"1": [
            {"start_word": "W0008", "end_word": "W0010", "effect": "behind_person"},
            {"start_word": "W0022", "end_word": "W0024", "effect": "side_label"},
            {"start_word": "W0032", "end_word": "W0034", "effect": "spotlight"},
        ]}},
        {1: words},
        {1: 25.0},
        min_start_by_clip={1: 3.2},
    )

    assert len(result[1]) == 2
    assert result[1][0]["text"] == "kata8 kata9 kata10"
    assert result[1][0]["start"] == words[8]["start"]
    assert result[1][0]["end"] <= result[1][0]["start"] + 2.8


def test_hook_broll_and_spacing_ranges_are_enforced():
    result = anchor_text_emphasis_response(
        {"clips": {"1": [
            {"start_word": 2, "end_word": 3, "effect": "spotlight"},
            {"start_word": 10, "end_word": 11, "effect": "spotlight"},
            {"start_word": 14, "end_word": 15, "effect": "spotlight"},
            {"start_word": 28, "end_word": 29, "effect": "spotlight"},
        ]}},
        {1: _words()},
        {1: 25.0},
        min_start_by_clip={1: 3.5},
        blocked_ranges_by_clip={1: [(4.8, 6.5)]},
    )
    assert [event["start_word"] for event in result[1]] == [14, 28]


def test_unsafe_style_values_are_clamped():
    style = normalise_text_emphasis_style({
        "effectMode": "not-real",
        "fontSize": 900,
        "positionY": -20,
        "color": "red",
        "maskFeather": 8,
    })
    assert style["effectMode"] == "auto"
    assert style["fontSize"] == 160
    assert style["positionY"] == 12
    assert style["color"] == "#FFFFFF"
    assert style["maskFeather"] % 2 == 1


def test_disabled_feature_does_not_call_ai_or_segmentation(tmp_path):
    service = _service()
    service._get_analyzer = lambda: (_ for _ in ()).throw(AssertionError("AI must not run"))
    clip = Clip(rank=1, score=100, start=0, end=20, hook="", reason="direct")
    asyncio.run(service._prepare_text_emphasis(
        job=Job(job_id="off", youtube_url="upload://off", clips_data={"text_emphasis_enabled": False}),
        job_id="off",
        clips=[clip],
        clips_with_words={1: _words()},
        output_dir=str(tmp_path),
        trim_results={1: True},
    ))
    assert clip.text_emphasis_events == []
