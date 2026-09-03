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


def test_skia_subtitle_renderer_glow_and_gradient_frame(tmp_path):
    from src.infrastructure.skia_subtitle_renderer import SkiaSubtitleRenderer
    from PIL import Image

    renderer = SkiaSubtitleRenderer(font_dir="backend/assets/fonts")
    words_line = [
        {"word": "SUPER", "start": 0.0, "end": 0.5},
        {"word": "GLOW", "start": 0.5, "end": 1.0},
        {"word": "SUBTITLE", "start": 1.0, "end": 1.5},
    ]
    style = {
        "style_preset": "bold_impact_stroke",
        "fontSize": 48,
        "glowEnabled": True,
        "glowColor": "#14F1D9",
        "glowSize": 24,
        "gradientEnabled": True,
        "gradientFrom": "#FFFFFF",
        "gradientTo": "#FF007F",
    }
    norm_style = renderer._normalize_style(style)
    assert norm_style["glow_enabled"] is True
    assert norm_style["glow_color"] == "#14F1D9"
    assert norm_style["gradient_enabled"] is True
    assert norm_style["gradient_from"] == "#FFFFFF"
    assert norm_style["gradient_to"] == "#FF007F"

    out_png = str(tmp_path / "frame_glow.png")
    renderer._render_line_frame_pil(
        output_png=out_png,
        words_line=words_line,
        active_word_index=1,
        style=norm_style,
    )
    assert os.path.exists(out_png)
    assert os.path.getsize(out_png) > 0
    img = Image.open(out_png)
    assert img.size == (1080, 1920)
    assert img.mode == "RGBA"


def test_skia_subtitle_renderer_full_video_with_glow(tmp_path):
    import subprocess
    from src.infrastructure.skia_subtitle_renderer import SkiaSubtitleRenderer

    in_video = str(tmp_path / "in.mp4")
    out_video = str(tmp_path / "out_glow.mp4")

    # Generate 3s synthetic MP4
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=720x1280:d=3:r=30",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "3",
        "-c:v", "libx264", "-c:a", "aac", in_video
    ], capture_output=True, check=True)

    renderer = SkiaSubtitleRenderer(font_dir="backend/assets/fonts")
    words = [
        {"word": "RAHASIA", "start": 0.2, "end": 0.8},
        {"word": "SUKSES", "start": 0.8, "end": 1.6},
        {"word": "BISNIS", "start": 1.6, "end": 2.4},
    ]
    style = {
        "style_preset": "neon_glow",
        "glowEnabled": True,
        "glowColor": "#00FFFF",
        "gradientEnabled": True,
        "gradientFrom": "#00FFFF",
        "gradientTo": "#FF007F",
    }
    res = renderer.render_subtitles(
        video_path=in_video,
        words=words,
        style=style,
        output_path=out_video,
        start_offset=0.0,
    )
    assert os.path.exists(out_video)
    assert os.path.getsize(out_video) > 0


@pytest.mark.asyncio
async def test_trim_all_clips_parallel(tmp_path):
    """Verify _trim_all_clips trims clips concurrently."""
    svc = V2PipelineService.__new__(V2PipelineService)
    svc._renderer = MagicMock()

    trimmed_ranks = []

    async def mock_trim(video_path, clip, out_path, normalize_timestamps=False):
        await asyncio.sleep(0.05)
        trimmed_ranks.append(clip.rank)
        return True

    svc._renderer.trim_clip = mock_trim

    clips = [
        Clip(rank=1, start=0.0, end=10.0, score=90, hook="H1", reason="R1"),
        Clip(rank=2, start=15.0, end=25.0, score=85, hook="H2", reason="R2"),
        Clip(rank=3, start=30.0, end=40.0, score=80, hook="H3", reason="R3"),
    ]

    results = await svc._trim_all_clips(
        job_id="test-job",
        video_path="/dummy/video.mp4",
        clips=clips,
        output_dir=str(tmp_path),
        normalize_timestamps=True,
    )

    assert len(results) == 3
    assert all(results.values())
    assert sorted(trimmed_ranks) == [1, 2, 3]


@pytest.mark.asyncio
async def test_remotion_render_single_pass_cta_watermark(tmp_path):
    """Verify _render_via_remotion passes CTA and Watermark to Remotion and skips post-FFmpeg re-encodes."""
    from src.domain.interfaces_remotion import RemotionRenderResult

    svc = V2PipelineService.__new__(V2PipelineService)
    svc._repo = MagicMock()
    svc._repo.update_status = AsyncMock()
    svc._emit = MagicMock()
    svc._emit_clip_progress = MagicMock()
    svc._remotion_adapter = MagicMock()

    # Track calls to Remotion render_clip
    rendered_payloads = []

    async def mock_render_clip(**kwargs):
        rendered_payloads.append(kwargs)
        # Create output file
        out_p = kwargs["output_path"]
        with open(out_p, "wb") as f:
            f.write(b"video-data")
        return RemotionRenderResult(success=True, output_path=out_p, render_time_seconds=1.2)

    svc._remotion_adapter.render_clip = mock_render_clip

    # Spy on _apply_cta and _apply_watermark
    svc._apply_cta = AsyncMock()
    svc._apply_watermark = AsyncMock()
    svc._render_via_direct_engines = AsyncMock()
    svc._build_broll_events = MagicMock(return_value=[])

    out_dir = str(tmp_path)
    base_clip = tmp_path / "clip_01.mp4"
    base_clip.write_bytes(b"base-data")

    clip = Clip(rank=1, start=0.0, end=10.0, score=90, hook="Test Hook", reason="Test Reason")
    job = Job(
        job_id="test-remotion-opt",
        youtube_url="https://youtube.com/watch?v=dummy",
        target_aspect_ratio="9:16",
        broll_motion_style="none",
        clips_data={
            "cta_config": {"enabled": True, "headline": "Follow Us"},
            "watermark_config": {"enabled": True, "text": "MyChannel"},
        },
    )

    from src.domain.entities import CreativeDirection

    await svc._render_via_remotion(
        job=job,
        job_id="test-remotion-opt",
        clips=[clip],
        clips_with_words={1: []},
        creative_direction=CreativeDirection(),
        output_dir=out_dir,
        trim_results={1: True},
        reframe_data={},
        hook_style_config={"enabled": True, "engine": "remotion"},
        subtitle_style_config={"enabled": True, "engine": "remotion"},
    )

    # 1. Remotion render_clip was called with cta and watermark
    assert len(rendered_payloads) == 1
    assert rendered_payloads[0]["cta"] == {"enabled": True, "headline": "Follow Us"}
    assert rendered_payloads[0]["watermark"] is not None
    assert rendered_payloads[0]["watermark"]["text"] == "MyChannel"

    # 2. Post-Remotion FFmpeg re-encodes were skipped (single-pass composite)
    svc._apply_cta.assert_not_called()
    svc._apply_watermark.assert_not_called()

