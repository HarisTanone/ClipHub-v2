"""Unit & Integration tests for CTA (Call to Action) End-Card Renderer & Compositor."""
import os
import pytest
from src.infrastructure.cta_renderer import (
    normalise_cta_config,
    escape_drawtext,
    build_cta_drawtext_filters,
    DEFAULT_CTA_CONFIG,
)
from src.infrastructure.unified_ffmpeg_compositor import UnifiedFFmpegCompositor


def test_normalise_cta_defaults():
    cfg = normalise_cta_config(None)
    assert cfg["enabled"] is False
    assert cfg["template"] == "follow_badge"
    assert cfg["duration"] == 3.0
    assert cfg["headline"] == "Follow For More"
    assert cfg["buttonText"] == "FOLLOW"
    assert cfg["position"] == "bottom"
    assert cfg["animation"] == "slide_up"


def test_normalise_cta_clamps_and_coercion():
    raw = {
        "enabled": "true",
        "template": "invalid_template",
        "duration": 15.0,  # Should clamp to 6.0
        "headline": "  Sub to our YouTube!  ",
        "buttonText": "SUBSCRIBE",
        "position": "invalid_pos",
        "animation": "pop_in",
        "fontSize": 100,  # Should clamp to 60
        "bgOpacity": 150,  # Should clamp to 100
    }
    cfg = normalise_cta_config(raw)
    assert cfg["enabled"] is True
    assert cfg["template"] == "follow_badge"  # fallback
    assert cfg["duration"] == 6.0  # clamped to 6.0
    assert cfg["headline"] == "Sub to our YouTube!"
    assert cfg["buttonText"] == "SUBSCRIBE"
    assert cfg["position"] == "bottom"  # fallback
    assert cfg["animation"] == "pop_in"
    assert cfg["fontSize"] == 60  # clamped
    assert cfg["bgOpacity"] == 100  # clamped


def test_escape_drawtext():
    raw = "Follow: @my_channel 100% 'Awesome'\\Fun"
    escaped = escape_drawtext(raw)
    assert "\\:" in escaped
    assert "\\%" in escaped
    assert "\\\\" in escaped


def test_build_cta_drawtext_filters_disabled():
    cfg = {"enabled": False, "headline": "Test"}
    filters = build_cta_drawtext_filters(cfg, clip_duration=30.0)
    assert filters == []


def test_build_cta_drawtext_filters_timing():
    cfg = {
        "enabled": True,
        "ctaType": "card",
        "template": "link_bio",
        "duration": 4.0,
        "headline": "Check Link in Bio!",
        "buttonText": "CLICK HERE",
        "position": "bottom",
        "primaryColor": "#3B82F6",
        "textColor": "#FFFFFF",
        "backgroundColor": "#0F172A",
        "bgOpacity": 90,
        "fontSize": 28,
    }
    clip_dur = 25.0
    filters = build_cta_drawtext_filters(cfg, clip_duration=clip_dur)
    assert len(filters) == 2  # Headline + Button
    # Verify timing: start at 25.0 - 4.0 = 21.000, end at 25.000
    assert "between(t,21.000,25.000)" in filters[0]
    assert "Check Link in Bio!" in filters[0]
    assert "between(t,21.000,25.000)" in filters[1]
    assert "[CLICK HERE]" in filters[1]


def test_build_cta_drawtext_filters_plain_text():
    cfg = {
        "enabled": True,
        "ctaType": "text",
        "text": "Jangan lupa follow untuk tips berikutnya!",
        "duration": 3.0,
        "position": "top",
        "bgBox": True,
        "fontSize": 26,
    }
    filters = build_cta_drawtext_filters(cfg, clip_duration=10.0)
    assert len(filters) == 1
    assert "between(t,7.000,10.000)" in filters[0]
    assert "Jangan lupa follow untuk tips berikutnya!" in filters[0]
    assert "h*0.08" in filters[0]  # top position


def test_unified_compositor_cta_integration():
    compositor = UnifiedFFmpegCompositor()
    cta_cfg = {
        "enabled": True,
        "template": "follow_badge",
        "duration": 3.0,
        "headline": "Follow Us",
        "buttonText": "FOLLOW",
        "fontFamily": "Poppins",
        "fontWeight": "700",
    }
    filters = compositor.build_cta_filter_chain(cta_cfg, clip_duration=15.0)
    assert len(filters) >= 1
    assert "between(t,12.000,15.000)" in filters[0]
    assert "Follow Us" in filters[0]


@pytest.mark.asyncio
async def test_apply_cta_if_configured_disabled_is_noop():
    from src.infrastructure.cta_renderer import apply_cta_if_configured
    # Should safely return without touching anything when disabled
    await apply_cta_if_configured(
        {"enabled": False},
        output_dir="/tmp",
        clip_rank=1,
        final_path="/tmp/non_existent.mp4",
    )


def test_normalise_cta_snake_case():
    raw = {
        "enabled": True,
        "cta_type": "card",
        "duration_sec": 4.5,
        "button_text": "JOIN NOW",
        "social_handle": "@myuser",
        "bg_opacity": 85,
        "font_size": 32,
        "font_family": "Montserrat",
        "primary_color": "#FF5500",
        "text_color": "#EEEEEE",
        "background_color": "#111111",
        "bg_box": True,
        "show_icon": True,
        "show_arrow": False,
    }
    cfg = normalise_cta_config(raw)
    assert cfg["enabled"] is True
    assert cfg["ctaType"] == "card"
    assert cfg["duration"] == 4.5
    assert cfg["buttonText"] == "JOIN NOW"
    assert cfg["socialHandle"] == "@myuser"
    assert cfg["bgOpacity"] == 85
    assert cfg["fontSize"] == 32
    assert cfg["fontFamily"] == "Montserrat"
    assert cfg["primaryColor"] == "#FF5500"
    assert cfg["textColor"] == "#EEEEEE"
    assert cfg["backgroundColor"] == "#111111"
    assert cfg["showArrow"] is False


def test_font_resolver():
    from src.infrastructure.cta_renderer import _resolve_font_path
    font_p = _resolve_font_path("Poppins", fonts_dir="assets/fonts")
    assert font_p is not None
    assert "Poppins" in font_p


def test_render_cta_overlay_image_modes():
    from src.infrastructure.cta_renderer import render_cta_overlay_image
    
    # 1. Card mode
    img_card = render_cta_overlay_image(
        width=1080, height=1920,
        cta_config={
            "enabled": True, "ctaType": "card",
            "headline": "Follow For More", "subhead": "@channel",
            "buttonText": "FOLLOW", "primaryColor": "#10B981"
        },
        fonts_dir="assets/fonts",
    )
    assert img_card.size == (1080, 1920)
    assert img_card.mode == "RGBA"

    # 2. Both mode (text + icon)
    img_both = render_cta_overlay_image(
        width=1080, height=1920,
        cta_config={
            "enabled": True, "ctaType": "both",
            "text": "Subscribe Now", "selectedIcon": "bell",
            "primaryColor": "#EF4444"
        },
        fonts_dir="assets/fonts",
    )
    assert img_both.size == (1080, 1920)

    # 3. Text mode
    img_text = render_cta_overlay_image(
        width=1080, height=1920,
        cta_config={
            "enabled": True, "ctaType": "text",
            "text": "Save video ini!", "primaryColor": "#3B82F6"
        },
        fonts_dir="assets/fonts",
    )
    assert img_text.size == (1080, 1920)


def test_apply_cta_overlay_video(tmp_path):
    import subprocess
    from src.infrastructure.cta_renderer import apply_cta
    
    in_video = str(tmp_path / "in.mp4")
    out_video = str(tmp_path / "out.mp4")
    
    # Create 3s dummy video
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=720x1280:d=3:r=30",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "3",
        "-c:v", "libx264", "-c:a", "aac", in_video
    ], capture_output=True, check=True)
    
    ok = apply_cta(
        in_video,
        cta_config={
            "enabled": True,
            "ctaType": "card",
            "template": "follow_badge",
            "headline": "Follow Us",
            "buttonText": "FOLLOW",
            "duration": 2.0,
            "animation": "slide_up",
        },
        output_video=out_video,
        fonts_dir="assets/fonts",
    )
    assert ok is True
    assert os.path.exists(out_video)
    assert os.path.getsize(out_video) > 0
