import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.entities import Clip, Job, JobStatus, SubtitleStyleConfig
from src.infrastructure.subtitle_renderer import SubtitleRenderer
from src.infrastructure.unified_ffmpeg_compositor import UnifiedFFmpegCompositor
from src.infrastructure.watermark_renderer import _resolve_font as _resolve_wm_font
from src.application.services import AutoClipService
from src.application.services_v2 import V2PipelineService


def test_subtitle_renderer_resolve_font_finds_fonts():
    renderer = SubtitleRenderer(font_dir="assets/fonts")
    resolved = renderer._resolve_font("Montserrat", "Bold")
    # Should resolve to Montserrat or a fallback font if Montserrat exists
    assert resolved is None or os.path.exists(resolved)


def test_unified_compositor_resolve_font():
    compositor = UnifiedFFmpegCompositor(font_dir="assets/fonts")
    resolved = compositor._resolve_font("Montserrat", "Bold")
    assert resolved is None or os.path.exists(resolved)


def test_services_resolve_hook_font():
    svc = AutoClipService.__new__(AutoClipService)
    svc._fonts_dir = "assets/fonts"
    resolved = svc._resolve_hook_font(["Montserrat-Bold.ttf", "Poppins-Bold.ttf"])
    assert resolved == "" or os.path.exists(resolved)


def test_watermark_resolve_font():
    resolved = _resolve_wm_font("assets/fonts", "Montserrat")
    assert resolved == "" or os.path.exists(resolved)


@pytest.mark.asyncio
async def test_render_via_direct_engines_final_path_defined(tmp_path):
    output_dir = str(tmp_path)
    # Create fake base video clip
    clip_file = os.path.join(output_dir, "clip_01.mp4")
    with open(clip_file, "wb") as f:
        f.write(b"\x00" * 100)

    clips = [
        Clip(
            rank=1,
            start=0.0,
            end=10.0,
            score=90,
            hook="Awesome Hook Text",
            reason="Test",
        ),
        Clip(
            rank=2,
            start=10.0,
            end=20.0,
            score=85,
            hook="Second Hook Text",
            reason="Test 2",
        ),
    ]
    # Create clip 2 base
    clip_file2 = os.path.join(output_dir, "clip_02.mp4")
    with open(clip_file2, "wb") as f:
        f.write(b"\x00" * 100)

    trim_results = {1: True, 2: True}
    clips_with_words = {
        1: [{"word": "Hello", "start": 3.5, "end": 4.0}],
        2: [{"word": "World", "start": 13.5, "end": 14.0}],
    }

    service = V2PipelineService.__new__(V2PipelineService)
    service._emit = MagicMock()
    service._emit_clip_progress = MagicMock()
    service._repo = MagicMock()
    service._repo.update_status = AsyncMock()
    service._fonts_dir = "assets/fonts"
    service._apply_watermark = AsyncMock()

    job = Job(job_id="job_test", youtube_url="http://example.com", clips_data={})

    # Mock UnifiedFFmpegCompositor.render_single_pass to succeed
    with patch("src.infrastructure.unified_ffmpeg_compositor.UnifiedFFmpegCompositor.render_single_pass", new_callable=AsyncMock) as mock_render:
        mock_render.return_value = True
        
        # When mock_render is called, create the expected output file
        async def fake_render(input_video, output_video, **kwargs):
            with open(output_video, "wb") as f:
                f.write(b"\x00" * 100)
            return True
        mock_render.side_effect = fake_render

        await service._render_via_direct_engines(
            job=job,
            job_id="job_test",
            clips=clips,
            clips_with_words=clips_with_words,
            output_dir=output_dir,
            trim_results=trim_results,
            hook_style_config={"animation": "zoom_punch"},
            subtitle_style_config={"fontFamily": "Montserrat"},
            hook_engine="ffmpeg",
            sub_engine="ffmpeg",
        )

        assert mock_render.call_count == 2
        # Check that clip 1 rendered to clip_01_final.mp4 and clip 2 to clip_02_final.mp4
        assert os.path.exists(os.path.join(output_dir, "clip_01_final.mp4"))
        assert os.path.exists(os.path.join(output_dir, "clip_02_final.mp4"))


@pytest.mark.asyncio
async def test_render_clips_fallback_when_remotion_offline(tmp_path):
    output_dir = str(tmp_path)
    clip_file = os.path.join(output_dir, "clip_01.mp4")
    with open(clip_file, "wb") as f:
        f.write(b"\x00" * 100)

    clips = [
        Clip(
            rank=1,
            start=0.0,
            end=10.0,
            score=90,
            hook="Awesome Hook Text",
            reason="Test",
        )
    ]
    trim_results = {1: True}
    clips_with_words = {1: [{"word": "Hello", "start": 3.5, "end": 4.0}]}

    service = V2PipelineService.__new__(V2PipelineService)
    service._remotion_adapter = None
    service._emit = MagicMock()
    service._emit_clip_progress = MagicMock()
    service._repo = MagicMock()
    service._repo.update_status = AsyncMock()
    service._fonts_dir = "assets/fonts"
    service._render_via_direct_engines = AsyncMock()

    job = Job(job_id="job_test2", youtube_url="http://example.com", clips_data={
        "hook_style_config": {"engine": "remotion"},
        "subtitle_style_config": {"engine": "remotion"},
    })

    from src.domain.entities import CreativeDirection
    cd = CreativeDirection()

    # Should not raise RuntimeError, but gracefully call _render_via_direct_engines
    await service._render_clips(
        job=job,
        job_id="job_test2",
        clips=clips,
        clips_with_words=clips_with_words,
        creative_direction=cd,
        output_dir=output_dir,
        trim_results=trim_results,
        reframe_data={},
    )

    assert service._render_via_direct_engines.called
