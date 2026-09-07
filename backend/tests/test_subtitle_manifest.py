import pytest

from src.infrastructure.subtitle_manifest import (
    CANONICAL_SUBTITLE_DEFAULT_ID,
    SubtitleManifestError,
    resolve_subtitle_manifest,
    subtitle_render_spec_hash,
)


def test_empty_config_returns_complete_canonical_remotion_manifest():
    manifest = resolve_subtitle_manifest(None)
    assert manifest["preset_id"] == CANONICAL_SUBTITLE_DEFAULT_ID
    assert manifest["engine"] == "ffmpeg"
    assert manifest["subtitle_id"] == "classic_karaoke"
    assert set(manifest) >= {
        "preset_id", "subtitle_id", "engine", "enabled", "position_y",
        "font_family", "font_size", "font_weight", "color", "highlight_color",
        "background", "stroke", "shadow", "template", "version", "config",
    }


@pytest.mark.parametrize("engine", ["remotion", "skia", "ffmpeg"])
def test_explicit_engine_is_preserved_without_inference(engine):
    manifest = resolve_subtitle_manifest({"engine": engine, "stylePreset": "classic"})
    assert manifest["engine"] == engine
    assert manifest["config"]["engine"] == engine


def test_hyperframes_engine_with_explicit_template():
    manifest = resolve_subtitle_manifest({"engine": "hyperframes", "template": "sub_modern_card"})
    assert manifest["engine"] == "hyperframes"
    assert manifest["template"] == "sub_modern_card"


def test_unknown_engine_is_rejected():
    with pytest.raises(SubtitleManifestError, match="Unsupported subtitle engine"):
        resolve_subtitle_manifest({"engine": "magic", "stylePreset": "classic"})


def test_hyperframes_requires_explicit_template():
    with pytest.raises(SubtitleManifestError, match="template"):
        resolve_subtitle_manifest({"engine": "hyperframes", "stylePreset": "classic"})


def test_prefix_does_not_infer_engine():
    """Engine must come from explicit 'engine' field, not style prefix."""
    manifest = resolve_subtitle_manifest({"stylePreset": "skia_neon", "engine": "remotion"})
    assert manifest["engine"] == "remotion"


def test_visual_config_is_preserved_and_normalized():
    manifest = resolve_subtitle_manifest({
        "engine": "ffmpeg",
        "stylePreset": "classic_karaoke",
        "fontFamily": "Anton",
        "fontSize": 44,
        "positionY": 82,
        "color": "#fff000",
        "highlightColor": "#00ffff",
        "enabled": False,
    })
    assert manifest["enabled"] is False
    assert manifest["font_family"] == "Anton"
    assert manifest["font_size"] == 44
    assert manifest["position_y"] == 82
    assert manifest["highlight_color"] == "#00ffff"


def test_out_of_range_position_is_rejected():
    with pytest.raises(SubtitleManifestError, match="positionY"):
        resolve_subtitle_manifest({"engine": "remotion", "stylePreset": "classic", "positionY": 101})


def test_manifest_hash_is_stable_and_changes_with_config():
    one = resolve_subtitle_manifest({"engine": "remotion", "stylePreset": "classic"})
    two = resolve_subtitle_manifest({"engine": "remotion", "stylePreset": "classic", "fontSize": 99})
    assert subtitle_render_spec_hash(one) == subtitle_render_spec_hash(one)
    assert subtitle_render_spec_hash(one) != subtitle_render_spec_hash(two)


def test_existing_manifest_round_trips_without_re_resolving():
    """Passing an already-resolved manifest back must be a no-op."""
    original = resolve_subtitle_manifest({"engine": "skia", "stylePreset": "glassmorphism"})
    again = resolve_subtitle_manifest(original)
    assert again["preset_id"] == original["preset_id"]
    assert again["engine"] == original["engine"]
    assert again["subtitle_id"] == original["subtitle_id"]
