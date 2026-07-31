"""Regression coverage for HyperFrames-owned hook/subtitle final rendering."""
from __future__ import annotations

import asyncio
from typing import Any, cast
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.application.services_v2 import V2PipelineService


class _Repo:
    update_status = AsyncMock()


def _service(remotion_adapter=None) -> V2PipelineService:
    return V2PipelineService(
        job_repo=cast(Any, _Repo()),
        downloader=cast(Any, object()),
        renderer=cast(Any, object()),
        whisper_local=cast(Any, object()),
        remotion_adapter=remotion_adapter,
    )


def test_mixed_hyperframes_failure_rejects_incomplete_final_clip(tmp_path):
    """Never accept a Remotion base whose HF-owned layer failed to render."""
    remotion = SimpleNamespace(health_check=AsyncMock(return_value=True))
    service = _service(remotion)
    service._render_via_remotion = AsyncMock()
    service._apply_hf_hook_subtitle_pass = AsyncMock(
        return_value=["clip 1 hook: renderer unavailable"]
    )
    job = SimpleNamespace(
        clips_data={
            "hook_style_config": {
                "engine": "hyperframes",
                "hf_template": "hook_neon_v1",
            },
            "subtitle_style_config": {"engine": "remotion"},
        },
        target_aspect_ratio="9:16",
        text_emphasis_enabled=False,
    )

    with pytest.raises(RuntimeError, match="HyperFrames hook/subtitle render failed"):
        asyncio.run(
            service._render_clips(
                job=cast(Any, job),
                job_id="job-hf-mixed",
                clips=[],
                clips_with_words={},
                creative_direction=cast(Any, SimpleNamespace()),
                output_dir=str(tmp_path),
                trim_results={},
                reframe_data={},
            )
        )


def test_hyperframes_adapter_exposes_hook_subtitle_capability():
    from src.infrastructure.hyperframes_adapter import HyperFramesAdapter

    adapter = HyperFramesAdapter()
    assert adapter.supports_template("hook_chromatic_gate_v2")
    assert adapter.supports_template("sub_speech_capsule_v2")
    assert adapter.supports_template("hook_neon_v1")
    assert adapter.supports_template("sub_neon_v1")
    assert not adapter.supports_template("podcast_lower_third")


def test_hyperframes_catalog_uses_distinct_v2_styles():
    from src.infrastructure.hf_style_catalog import catalogue

    data = catalogue()
    styles = (*data["hook"], *data["subtitle"])
    assert all(item["id"].endswith("_v2") for item in styles)
    assert len({item["design"] for item in styles}) == 8


def test_pure_hyperframes_without_events_copies_source_instead_of_moving_it(tmp_path):
    service = _service()
    source = tmp_path / "clip_01.mp4"
    source.write_bytes(b"base-video")
    clip = SimpleNamespace(rank=1, hook="", start=0.0, end=2.0, hyperframes_polish=None)
    adapter = SimpleNamespace(health=AsyncMock(return_value={"status": "healthy"}))

    with patch(
        "src.infrastructure.hyperframes_adapter.get_hyperframes_adapter",
        return_value=adapter,
    ):
        errors = asyncio.run(
            service._apply_hf_hook_subtitle_pass(
                job=SimpleNamespace(user_id=None),
                job_id="job-no-events",
                clips=[clip],
                clips_with_words={},
                output_dir=str(tmp_path),
                trim_results={1: True},
                hook_style_config={"engine": "hyperframes"},
                subtitle_style_config={"engine": "hyperframes"},
                hook_engine="hyperframes",
                sub_engine="hyperframes",
                base_is_input=True,
            )
        )

    assert errors == []
    assert source.read_bytes() == b"base-video"
    assert (tmp_path / "clip_01_final.mp4").read_bytes() == b"base-video"
