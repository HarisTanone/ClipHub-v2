"""Tests for SkiaHookRenderer and upgraded SkiaSubtitleRenderer."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.skia_hook_renderer import SkiaHookRenderer, SKIA_HOOK_PRESETS
from src.infrastructure.skia_subtitle_renderer import SkiaSubtitleRenderer


def test_skia_hook_renderer_all_presets_generate_frames():
    renderer = SkiaHookRenderer(font_dir="assets/fonts")
    sample_text = "Teror kepala babi malah jadi bercandaan?"

    for preset_id in SKIA_HOOK_PRESETS.keys():
        frame = renderer.generate_hook_frame(sample_text, hook_style=preset_id)
        assert frame is not None
        assert frame.size == (1080, 1920)
        assert frame.mode == "RGBA"


def test_skia_hook_renderer_custom_style_config_overrides():
    renderer = SkiaHookRenderer(font_dir="assets/fonts")
    custom_cfg = {
        "fontSize": 70,
        "color": "#FFCC00",
        "fontFamily": "Montserrat",
        "positionY": 35,
        "gradientEnabled": True,
        "gradientFrom": "#00F0FF",
        "gradientTo": "#FF007F",
    }
    frame = renderer.generate_hook_frame("Custom Hook Text", hook_style="skia_frosted_pill", style_config=custom_cfg)
    assert frame is not None
    assert frame.size == (1080, 1920)


@pytest.mark.asyncio
async def test_skia_hook_renderer_render_hook_execution(tmp_path):
    renderer = SkiaHookRenderer(font_dir="assets/fonts")
    input_video = os.path.join(tmp_path, "input.mp4")
    output_video = os.path.join(tmp_path, "output.mp4")

    # Create dummy video file
    with open(input_video, "wb") as f:
        f.write(b"\x00" * 200)

    with patch("subprocess.run") as mock_sub:
        mock_sub.return_value = MagicMock(returncode=0, stderr="")
        # Simulate creating output file
        def fake_run(*args, **kwargs):
            with open(output_video, "wb") as f:
                f.write(b"\x00" * 300)
            return MagicMock(returncode=0, stderr="")
        mock_sub.side_effect = fake_run

        out = await renderer.render_hook(input_video, "Testing Skia Hook", output_video, hook_style="skia_impact_badge")
        assert out == output_video
        assert os.path.exists(output_video)


def test_skia_subtitle_renderer_style_normalization():
    renderer = SkiaSubtitleRenderer(font_dir="assets/fonts")
    frontend_config = {
        "id": "glassmorphism",
        "fontFamily": "Montserrat",
        "fontSize": 42,
        "fontWeight": "800",
        "color": "#FFFFFF",
        "highlightColor": "#FACC15",
        "positionY": 75,
        "maxWordsPerLine": 3,
        "lineTransition": "karaoke",
        "bgOpacity": 0.8,
        "glowEnabled": True,
        "glowColor": "#FACC15",
    }
    normalized = renderer._normalize_style(frontend_config)
    assert normalized["font_family"] == "Montserrat"
    assert normalized["font_size"] == 42
    assert normalized["font_weight"] == "800"
    assert normalized["highlight_color"] == "#FACC15"
    assert normalized["position_y_pct"] == 75
    assert normalized["max_words_per_line"] == 3
    assert normalized["line_transition"] == "karaoke"
    assert normalized["bg_enabled"] is True
    assert normalized["bg_opacity"] == 0.8
    assert normalized["glow_enabled"] is True


def test_skia_subtitle_renderer_ffmpeg_fallback_invoked(tmp_path):
    renderer = SkiaSubtitleRenderer(font_dir="assets/fonts")
    input_video = os.path.join(tmp_path, "input.mp4")
    output_video = os.path.join(tmp_path, "output.mp4")

    with open(input_video, "wb") as f:
        f.write(b"\x00" * 200)

    words = [
        {"word": "Teror", "start": 3.0, "end": 3.5},
        {"word": "kepala", "start": 3.5, "end": 4.0},
        {"word": "babi", "start": 4.0, "end": 4.5},
    ]
    style = {
        "id": "glassmorphism",
        "fontFamily": "Inter",
        "fontSize": 34,
        "color": "#FFFFFF",
        "highlightColor": "#38BDF8",
    }

    with patch("src.infrastructure.subtitle_renderer.SubtitleRenderer.render_subtitles") as mock_sub_render:
        mock_sub_render.return_value = output_video
        result = renderer.render_subtitles(input_video, words, style, output_video)
        assert result == output_video
        assert mock_sub_render.called
