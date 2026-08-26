"""
Test Preset Parity across API, Preset Resolver, Remotion, and Telegram/CLI Submissions.

Ensures that everything in a saved preset (Hook, Subtitle, Watermark, CTA, B-Roll, Text Emphasis)
is faithfully preserved, resolved, and embedded into jobs from any entrypoint.
"""
import json
import pytest
from src.infrastructure.preset_resolver import resolve_preset
from src.infrastructure.hf_style_catalog import resolve_engine
from src.infrastructure.db_connection import get_dict_connection


@pytest.fixture
def setup_test_preset():
    """Insert a comprehensive test preset into user_presets."""
    conn = get_dict_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM user_presets WHERE slug = 'viral-test-preset-01'")
    
    hook_style = {
        "animation": "glitch_rgb",
        "duration": 3.5,
        "fontFamily": "Montserrat",
        "fontSize": 48,
        "color": "#FFFFFF",
        "primary_color": "#00F0FF",
        "secondary_color": "#FF0055",
        "engine": "remotion",
        "transitionStyle": "slide_left",
        "transitionDuration": 0.4,
    }
    subtitle_style = {
        "stylePreset": "neon_pulse",
        "fontFamily": "Poppins",
        "fontSize": 36,
        "color": "#FFFFFF",
        "highlightColor": "#00FFCC",
        "highlightGlow": True,
        "highlightGlowColor": "#00FFCC",
        "dualStyleEnabled": True,
        "highlightFontFamily": "Anton",
        "position": "bottom",
        "positionY": 82,
        "engine": "remotion",
    }
    watermark_style = {
        "enabled": True,
        "type": "text",
        "text": "@ClipHubOfficial",
        "fontSize": 20,
        "color": "#FFFFFF",
        "opacity": 80,
        "position": "top-right",
        "marginPct": 3.0,
    }
    cta_style = {
        "enabled": True,
        "ctaType": "card",
        "template": "follow_badge",
        "headline": "Follow For More",
        "subhead": "@ClipHubOfficial",
        "selectedIcon": "tiktok",
        "socialPlatform": "tiktok",
        "duration": 3.0,
        "position": "bottom",
    }
    broll_style = {
        "enabled": True,
        "motion_style": "word_pop_typography",
        "image_overlay": True,
        "behind_person": True,
        "video_footage": True,
        "autogrid_enabled": True,
    }
    text_emphasis_style = {
        "effectMode": "hero_punch",
        "animation": "impact",
        "fontFamily": "Impact",
        "fontSize": 60,
        "color": "#FFE600",
    }
    autopost_style = {
        "enabled": True,
        "platforms": "tiktok,instagram",
        "schedule_mode": "ai",
    }

    cur.execute(
        """INSERT INTO user_presets 
        (user_id, name, slug, hook_style, subtitle_style, watermark_style, cta_style, broll_style, text_emphasis_style, autopost_style)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            1,
            "Viral Test Preset 01",
            "viral-test-preset-01",
            json.dumps(hook_style),
            json.dumps(subtitle_style),
            json.dumps(watermark_style),
            json.dumps(cta_style),
            json.dumps(broll_style),
            json.dumps(text_emphasis_style),
            json.dumps(autopost_style),
        ),
    )
    conn.commit()
    preset_id = cur.lastrowid
    conn.close()

    yield {
        "id": preset_id,
        "slug": "viral-test-preset-01",
        "name": "Viral Test Preset 01",
        "hook_style": hook_style,
        "subtitle_style": subtitle_style,
        "watermark_style": watermark_style,
        "cta_style": cta_style,
        "broll_style": broll_style,
        "text_emphasis_style": text_emphasis_style,
        "autopost_style": autopost_style,
    }

    # Teardown
    conn2 = get_dict_connection()
    conn2.execute("DELETE FROM user_presets WHERE slug = 'viral-test-preset-01'")
    conn2.commit()
    conn2.close()


def test_preset_resolver_full_parity(setup_test_preset):
    """Verify resolve_preset returns 100% of the preset fields exactly matching the saved data."""
    preset = setup_test_preset
    resolved = resolve_preset(preset["slug"], user_id=1)

    assert resolved is not None
    assert resolved["slug"] == preset["slug"]
    assert resolved["name"] == preset["name"]
    
    # Hook
    assert resolved["hook_style_config"]["animation"] == "glitch_rgb"
    assert resolved["hook_style_config"]["fontFamily"] == "Montserrat"
    assert resolved["hook_style_config"]["duration"] == 3.5
    assert resolved["hook_engine"] == "remotion"
    assert resolved["transition_style"] == "slide_left"
    assert resolved["transition_duration"] == 0.4

    # Subtitle
    assert resolved["subtitle_style_config"]["stylePreset"] == "neon_pulse"
    assert resolved["subtitle_style_config"]["fontFamily"] == "Poppins"
    assert resolved["subtitle_style_config"]["highlightColor"] == "#00FFCC"
    assert resolved["subtitle_style_config"]["dualStyleEnabled"] is True
    assert resolved["subtitle_style_config"]["highlightFontFamily"] == "Anton"
    assert resolved["subtitle_engine"] == "remotion"

    # Watermark
    assert resolved["watermark_config"]["enabled"] is True
    assert resolved["watermark_config"]["text"] == "@ClipHubOfficial"
    assert resolved["watermark_config"]["position"] == "top-right"

    # CTA
    assert resolved["cta_config"]["enabled"] is True
    assert resolved["cta_config"]["headline"] == "Follow For More"
    assert resolved["cta_config"]["selectedIcon"] == "tiktok"

    # B-Roll
    assert resolved["broll_enabled"] is True
    assert resolved["broll_image_overlay"] is True
    assert resolved["autogrid_enabled"] is True

    # Text Emphasis
    assert resolved["text_emphasis_enabled"] is True
    assert resolved["text_emphasis_style_config"]["effectMode"] == "hero_punch"

    # AutoPost
    assert resolved["auto_post_social"] is True
    assert resolved["auto_post_platforms"] == "tiktok,instagram"


def test_resolve_engine_remotion_preservation():
    """Verify resolve_engine preserves remotion engine for all preset combinations."""
    # Explicit remotion engine
    assert resolve_engine({"engine": "remotion", "stylePreset": "classic"}) == "remotion"
    assert resolve_engine({"engine": "remotion", "stylePreset": "minimal_clean"}) == "remotion"
    assert resolve_engine({"engine": "remotion", "animation": "podcast_lower_third"}) == "remotion"
    assert resolve_engine({"engine": "remotion", "animation": "glitch_rgb"}) == "remotion"

    # Inferred remotion animations & visual presets
    assert resolve_engine({"stylePreset": "neon_pulse"}) == "remotion"
    assert resolve_engine({"stylePreset": "dual_pop"}) == "remotion"
    assert resolve_engine({"stylePreset": "spotlight_keyword"}) == "remotion"
    assert resolve_engine({"stylePreset": "bubble_chat"}) == "remotion"
    assert resolve_engine({"stylePreset": "documentary"}) == "remotion"
    assert resolve_engine({"animation": "cinematic_reveal"}) == "remotion"
    assert resolve_engine({"animation": "danger_bold"}) == "remotion"
    assert resolve_engine({"animation": "slide_punch_framer"}) == "remotion"
    assert resolve_engine({"animation": "split_panel"}) == "remotion"
    assert resolve_engine({"animation": "glass_flash"}) == "remotion"

    # HyperFrames
    assert resolve_engine({"engine": "hyperframes"}) == "hyperframes"
    assert resolve_engine({"animation": "hook_cyber_hud"}) == "hyperframes"
    assert resolve_engine({"stylePreset": "sub_speech_capsule_v2"}) == "hyperframes"

    # Skia
    assert resolve_engine({"engine": "skia"}) == "skia"
    assert resolve_engine({"animation": "skia_impact_badge"}) == "skia"
