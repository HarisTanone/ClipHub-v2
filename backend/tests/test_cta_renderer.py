"""Unit & Integration tests for CTA (Call to Action) End-Card Renderer & Compositor."""
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
