"""Upload-only regression tests for direct hooks and A/V timeline sync."""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.services_v2 import V2PipelineService
from src.domain.entities import Clip
from src.infrastructure.renderer import FFmpegRenderer


def run(coroutine):
    return asyncio.run(coroutine)


def test_direct_edit_uses_custom_hook_without_ai_analysis():
    result = V2PipelineService._build_direct_edit_analysis(
        12.5,
        "  Hook custom dari user  ",
    )

    assert result.model_used == "direct"
    assert result.chunks_processed == 0
    assert result.clips[0].start == 0.0
    assert result.clips[0].end == 12.5
    assert result.clips[0].hook == "Hook custom dari user"


def test_direct_edit_without_custom_hook_renders_subtitle_only():
    result = V2PipelineService._build_direct_edit_analysis(8.0, "   ")

    assert result.clips[0].hook == ""
    assert result.clips[0].start == 0.0
    assert result.clips[0].end == 8.0


def test_upload_trim_resets_video_and_audio_timestamps():
    captured = {}

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_subprocess(*args, **_kwargs):
        captured["args"] = list(args)
        return FakeProcess()

    renderer = FFmpegRenderer()
    clip = Clip(
        rank=1,
        score=100,
        start=42.25,
        end=52.25,
        hook="",
        reason="upload sync test",
    )

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(side_effect=fake_subprocess)):
        assert run(renderer.trim_clip(
            "/tmp/upload.mov",
            clip,
            "/tmp/upload_clip.mp4",
            normalize_timestamps=True,
        )) is True

    args = captured["args"]
    assert args[args.index("-ss") + 1] == "42.25"
    assert args[args.index("-vf") + 1] == "setpts=PTS-STARTPTS"
    assert args[args.index("-af") + 1] == (
        "aresample=async=1:first_pts=0,asetpts=PTS-STARTPTS"
    )
    assert args[args.index("-c:a") + 1] == "aac"
    assert "copy" not in args
    assert "-avoid_negative_ts" not in args


def test_youtube_trim_keeps_existing_audio_copy_path():
    captured = {}

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_subprocess(*args, **_kwargs):
        captured["args"] = list(args)
        return FakeProcess()

    renderer = FFmpegRenderer()
    clip = Clip(
        rank=1,
        score=80,
        start=10.0,
        end=20.0,
        hook="",
        reason="youtube regression test",
    )

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(side_effect=fake_subprocess)):
        assert run(renderer.trim_clip(
            "/tmp/youtube.mp4",
            clip,
            "/tmp/youtube_clip.mp4",
        )) is True

    args = captured["args"]
    assert args[args.index("-c:a") + 1] == "copy"
    assert "setpts=PTS-STARTPTS" not in args
