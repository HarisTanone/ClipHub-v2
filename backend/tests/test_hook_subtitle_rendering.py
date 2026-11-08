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
async def test_render_via_direct_engines_skips_one_pass_for_karaoke_and_emphasis(tmp_path):
    """build_subtitle_filter_chain() (used by the 1-pass compositor) has no
    per-word highlight for "karaoke" and no big-keyword handling for
    "emphasis" — unlike SubtitleRenderer's multi-step implementations of the
    same transitions. The 1-pass shortcut must not be used for these, or the
    rendered subtitle looks different purely because hook_engine also
    happens to be "ffmpeg", with no indication anything is wrong."""
    output_dir = str(tmp_path)
    clip_file = os.path.join(output_dir, "clip_01.mp4")
    with open(clip_file, "wb") as f:
        f.write(b"\x00" * 100)

    clips = [Clip(rank=1, start=0.0, end=10.0, score=90, hook="", reason="Test")]
    trim_results = {1: True}
    clips_with_words = {1: [{"word": "Hello", "start": 3.5, "end": 4.0}]}

    service = V2PipelineService.__new__(V2PipelineService)
    service._emit = MagicMock()
    service._emit_clip_progress = MagicMock()
    service._repo = MagicMock()
    service._repo.update_status = AsyncMock()
    service._fonts_dir = "assets/fonts"

    job = Job(job_id="job_karaoke_direct", youtube_url="http://example.com", clips_data={})

    with patch(
        "src.infrastructure.unified_ffmpeg_compositor.UnifiedFFmpegCompositor.render_single_pass",
        new_callable=AsyncMock,
    ) as mock_one_pass, patch.object(
        SubtitleRenderer, "render_subtitles", return_value=os.path.join(output_dir, "clip_01_final.mp4")
    ) as mock_multi_step:
        await service._render_via_direct_engines(
            job=job,
            job_id="job_karaoke_direct",
            clips=clips,
            clips_with_words=clips_with_words,
            output_dir=output_dir,
            trim_results=trim_results,
            hook_style_config={},
            subtitle_style_config={"lineTransition": "karaoke"},
            hook_engine="ffmpeg",
            sub_engine="ffmpeg",
        )
        mock_one_pass.assert_not_called()
        mock_multi_step.assert_called_once()


@pytest.mark.asyncio
async def test_render_via_direct_engines_fails_closed_on_unsupported_hyperframes_engine(tmp_path):
    """_render_via_direct_engines only implements FFmpeg/Skia. A
    "hyperframes" engine reaching it (via the Remotion-failure fallback,
    which preserves hyperframes rather than rewriting it to ffmpeg) must not
    be silently rendered as plain FFmpeg drawtext — the clip should fail
    (recorded, not crash the whole run) rather than publish the wrong
    engine's visual output under a hyperframes selection."""
    output_dir = str(tmp_path)
    clip_file = os.path.join(output_dir, "clip_01.mp4")
    with open(clip_file, "wb") as f:
        f.write(b"\x00" * 100)

    clips = [Clip(rank=1, start=0.0, end=10.0, score=90, hook="Awesome Hook Text", reason="Test")]
    trim_results = {1: True}
    # No words: subtitle block is skipped, isolating the failure to the
    # hook-engine branch below.
    clips_with_words = {}

    service = V2PipelineService.__new__(V2PipelineService)
    service._emit = MagicMock()
    service._emit_clip_progress = MagicMock()
    service._repo = MagicMock()
    service._repo.update_status = AsyncMock()
    service._fonts_dir = "assets/fonts"

    job = Job(job_id="job_hf_fallback", youtube_url="http://example.com", clips_data={})

    with patch(
        "src.application.services.AutoClipService._render_hook_ffmpeg", new_callable=AsyncMock
    ) as mock_ffmpeg_hook:
        await service._render_via_direct_engines(
            job=job,
            job_id="job_hf_fallback",
            clips=clips,
            clips_with_words=clips_with_words,
            output_dir=output_dir,
            trim_results=trim_results,
            hook_style_config={"animation": "hook_banner_v1"},
            subtitle_style_config={},
            hook_engine="hyperframes",
            sub_engine="ffmpeg",
        )
        # The old binary check silently treated any non-"skia" hook_engine as
        # "ffmpeg" here. It must never be invoked for "hyperframes".
        mock_ffmpeg_hook.assert_not_called()

    # The clip still gets a final file (hooked_path falls back to base_path
    # on failure), but it must be the untouched base video — never a
    # silently-substituted FFmpeg-rendered hook burned in under the hood.
    final_path = os.path.join(output_dir, "clip_01_final.mp4")
    assert os.path.exists(final_path)
    with open(final_path, "rb") as f:
        assert f.read() == b"\x00" * 100


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

    # Fail closed: never publish a different engine's visual output when
    # the selected Remotion owner is unavailable.
    with pytest.raises(RuntimeError, match="Selected Remotion engine unavailable"):
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

    assert not service._render_via_direct_engines.called


@pytest.mark.asyncio
async def test_remotion_failure_fallback_keeps_resolved_hook_animation(tmp_path):
    """When Remotion fails mid-render and the clip falls back to a direct
    engine (FFmpeg/Skia), the fallback must render the animation that was
    actually resolved for this clip — not silently swap in
    _render_via_direct_engines's own unrelated "zoom_punch" default because
    hook_style_config never carried an explicit `animation` key for this
    under-specified (e.g. legacy pre-manifest) clip."""
    from types import SimpleNamespace
    from src.domain.entities import CreativeDirection

    output_dir = str(tmp_path)
    (tmp_path / "clip_01.mp4").write_bytes(b"\x00" * 100)

    clips = [Clip(rank=1, start=0.0, end=10.0, score=90, hook="Awesome Hook Text", reason="Test")]
    trim_results = {1: True}
    clips_with_words = {1: [{"word": "Hello", "start": 3.5, "end": 4.0}]}

    remotion = AsyncMock()
    remotion.render_clip.return_value = SimpleNamespace(success=False, error_message="boom", render_time_seconds=0.0)

    service = V2PipelineService.__new__(V2PipelineService)
    service._remotion_adapter = remotion
    service._emit = MagicMock()
    service._emit_clip_progress = MagicMock()
    service._repo = MagicMock()
    service._repo.update_status = AsyncMock()
    service._fonts_dir = "assets/fonts"
    service._render_via_direct_engines = AsyncMock()
    service._build_broll_events = MagicMock(return_value=[])

    job = Job(job_id="job_fallback_anim", youtube_url="http://example.com", clips_data={})

    await service._render_via_remotion(
        job=job,
        job_id="job_fallback_anim",
        clips=clips,
        clips_with_words=clips_with_words,
        creative_direction=CreativeDirection(hook_animation=""),
        output_dir=output_dir,
        trim_results=trim_results,
        reframe_data={},
        hook_style_config={},  # genuinely empty — no animation ever configured
        subtitle_style_config={},
        hook_engine="remotion",
        sub_engine="remotion",
    )

    service._render_via_direct_engines.assert_awaited_once()
    fallback_hook_cfg = service._render_via_direct_engines.await_args.args[6]
    assert fallback_hook_cfg["animation"] == "podcast_lower_third"


def test_emphasis_subtitle_style_never_calls_skia_when_ffmpeg_selected(tmp_path):
    """line_transition="emphasis" previously called into SkiaSubtitleRenderer
    unconditionally (regardless of the explicit "ffmpeg" engine selection),
    discarding every FFmpeg-tab setting. Engine ownership is strict: picking
    ffmpeg must render emphasis via pure FFmpeg drawtext, never Skia."""
    from src.domain.entities import SubtitleStyleConfig

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"\x00" * 10)

    words = [
        {"word": "Halo", "start": 0.2, "end": 0.6},
        {"word": "semua", "start": 0.7, "end": 1.1},
        {"word": "Jakarta", "start": 1.2, "end": 1.6},
    ]
    style = SubtitleStyleConfig(
        engine="ffmpeg",
        line_transition="emphasis",
        font_family="Poppins",
        font_size=36,
        color="#FFFFFF",
        highlight_color="#FFA500",
        max_words_per_line=3,
        stroke_width=2,
        glow_enabled=True,
    )

    renderer = SubtitleRenderer(font_dir="assets/fonts")
    with patch("src.infrastructure.skia_subtitle_renderer.SkiaSubtitleRenderer") as skia_cls, \
         patch.object(SubtitleRenderer, "_run_ffmpeg", return_value=str(tmp_path / "out.mp4")) as run_ffmpeg:
        out = renderer.render_subtitles(
            video_path=str(video_path),
            words=words,
            style=style,
            output_path=str(tmp_path / "out.mp4"),
            start_offset=0.0,
        )

    skia_cls.assert_not_called()
    run_ffmpeg.assert_called_once()
    filter_parts = run_ffmpeg.call_args.args[2]
    assert any("Jakarta" in part for part in filter_parts)
    assert out == str(tmp_path / "out.mp4")


def test_detect_emphasis_word_prefers_non_stopword_over_longer_stopword():
    """_detect_emphasis_word scores stopwords (from the dynamic,
    stop_words_store-backed SubtitleRenderer.STOP_WORDS — not a hardcoded
    literal) lower than any non-stopword, regardless of raw length."""
    renderer = SubtitleRenderer(font_dir="assets/fonts")
    line = [
        {"word": "sebagaimana"},  # long stopword
        {"word": "Jakarta"},       # shorter, non-stopword
    ]
    idx = renderer._detect_emphasis_word(line)
    assert line[idx]["word"] == "Jakarta"


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


def test_skia_subtitle_render_fails_closed_instead_of_silent_cross_engine_fallback(tmp_path):
    """A Skia render failure must raise, never silently re-render through a
    different engine (legacy FFmpeg drawtext, or a bare copy with zero
    subtitles) while still reporting success — the caller's own error
    handling (services_v2.py) is what decides what happens to the clip."""
    from src.infrastructure.skia_subtitle_renderer import SkiaSubtitleRenderer

    video_path = tmp_path / "in.mp4"
    video_path.write_bytes(b"\x00" * 10)
    out_path = tmp_path / "out.mp4"

    renderer = SkiaSubtitleRenderer(font_dir="assets/fonts")
    words = [{"word": "Halo", "start": 0.0, "end": 0.5}]

    with patch.object(SkiaSubtitleRenderer, "_render_with_pil", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            renderer.render_subtitles(
                video_path=str(video_path),
                words=words,
                style={},
                output_path=str(out_path),
                start_offset=0.0,
            )
    assert not out_path.exists()
    assert not hasattr(SkiaSubtitleRenderer, "_ffmpeg_fallback")


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


def test_resolve_engine_hook_animation_not_overridden_by_subtitle_preset():
    from src.infrastructure.hf_style_catalog import resolve_engine

    # When hook config has animation, it must resolve to remotion even if stylePreset is a skia subtitle preset
    cfg = {
        "animation": "podcast_lower_third",
        "stylePreset": "clean_editorial",
    }
    assert resolve_engine(cfg) == "remotion"

    cfg2 = {
        "animation": "paper_clip_scrap",
        "preset": "podcast_pro",
    }
    assert resolve_engine(cfg2) == "remotion"

    cfg3 = {
        "animation": "trending_radar",
        "stylePreset": "minimal_clean",
    }
    assert resolve_engine(cfg3) == "remotion"


def test_resolve_engine_explicit_precedence():
    from src.infrastructure.hf_style_catalog import resolve_engine

    # Explicit engine overrides for styles without prefix
    assert resolve_engine({"engine": "remotion", "stylePreset": "clean_editorial"}) == "remotion"
    assert resolve_engine({"engine": "skia", "animation": "paper_clip_scrap"}) == "skia"
    assert resolve_engine({"engine": "ffmpeg", "animation": "paper_clip_scrap"}) == "ffmpeg"


def test_render_one_clip_trusts_resolved_hook_engine_over_animation_prefix(tmp_path):
    """resolve_engine() sniffs a "hook_"-prefixed animation string to "hyperframes"
    even when the stored engine is explicitly "remotion" (legacy HyperFrames
    template ids like hook_banner_v1 left in hook_style_config). _render_clips
    already resolved and trusts the canonical, persisted hook_engine — the
    per-clip Remotion render must use that same value instead of re-deriving
    it from hook_style_config via resolve_engine(), or it silently drops the
    hook from the only pass that would have rendered it."""
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from src.domain.entities import CreativeDirection

    (tmp_path / "clip_01.mp4").write_bytes(b"base")
    remotion = AsyncMock()
    remotion.render_clip.return_value = SimpleNamespace(success=True, render_time_seconds=0.1, error_message="")
    service = V2PipelineService(
        job_repo=AsyncMock(), downloader=AsyncMock(), renderer=AsyncMock(),
        whisper_local=AsyncMock(), remotion_adapter=remotion,
    )

    asyncio.run(service._render_via_remotion(
        job=Job(job_id="render3", youtube_url="upload://render3"),
        job_id="render3",
        clips=[Clip(rank=1, score=100, start=0, end=20, hook="Awesome Hook Text", reason="direct")],
        clips_with_words={1: []},
        creative_direction=CreativeDirection(),
        output_dir=str(tmp_path),
        trim_results={1: True},
        reframe_data={},
        hook_style_config={"engine": "remotion", "animation": "hook_banner_v1"},
        subtitle_style_config={},
        hook_engine="remotion",
        sub_engine="remotion",
    ))

    assert remotion.render_clip.await_args.kwargs["hook_text"] == "Awesome Hook Text"



def test_text_emphasis_fallback_phrase_relaxed_overlap():
    from src.infrastructure.text_emphasis import _find_fallback_phrase

    words = [
        {"word": "Halo", "start": 3.2, "end": 3.6},
        {"word": "semuanya", "start": 3.6, "end": 4.1},
        {"word": "selamat", "start": 4.1, "end": 4.5},
        {"word": "datang", "start": 4.5, "end": 5.0},
    ]
    # Block the entire timeline so strict non-overlap fails
    blocked_ranges = [(0.0, 10.0)]
    fallback = _find_fallback_phrase(
        words=words,
        min_start=3.0,
        duration=10.0,
        blocked_ranges=blocked_ranges,
        effect="hero_punch",
    )
    # Guaranteed fallback must return a valid event instead of None
    assert fallback is not None
    assert fallback["id"] == "emphasis_fallback"
    assert fallback["effect"] == "hero_punch"
    assert len(fallback["text"]) > 0


