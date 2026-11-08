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


def test_missing_named_subtitle_preset_is_invalid_not_default():
    with pytest.raises(SubtitleManifestError, match="not found"):
        resolve_subtitle_manifest(None, user_id=987654, preset_slug="definitely-missing-preset")


def test_empty_preset_slug_behaves_exactly_like_no_preset_slug():
    """Backward compatibility: callers that don't pass preset_slug (every
    call site before this fix) must get byte-identical behavior."""
    with_slug = resolve_subtitle_manifest({"fontSize": 50}, user_id=1, preset_slug="")
    without_slug = resolve_subtitle_manifest({"fontSize": 50})
    assert with_slug == without_slug


def test_partial_override_on_named_preset_inherits_preset_fields_not_generic_defaults(monkeypatch):
    """A partial restyle override must inherit the rest of the NAMED preset's
    fields (e.g. its glow/stroke/background look), not silently fall back to
    the generic canonical default for every field the override omits — the
    same "preset owns its config" contract resolve_hook_preset() already
    enforces. This is what made a restyled clip's subtitle preset look
    inconsistent with what the style editor showed for that preset."""
    fake_preset = {
        "slug": "my-neon-preset",
        "id": "my-neon-preset",
        "subtitle_style_config": {
            "engine": "skia",
            "stylePreset": "neon_tube",
            "fontFamily": "Montserrat",
            "glowEnabled": True,
            "glowColor": "#00FFFF",
            "strokeEnabled": True,
        },
    }
    monkeypatch.setattr(
        "src.infrastructure.preset_resolver.resolve_preset",
        lambda slug, user_id=None: fake_preset if slug == "my-neon-preset" else None,
    )

    # Only fontSize is overridden — everything else must come from the preset.
    manifest = resolve_subtitle_manifest(
        {"fontSize": 60}, user_id=1, preset_slug="my-neon-preset"
    )
    assert manifest["config"]["fontFamily"] == "Montserrat"
    assert manifest["config"]["glowEnabled"] is True
    assert manifest["config"]["glowColor"] == "#00FFFF"
    assert manifest["config"]["strokeEnabled"] is True
    assert manifest["config"]["fontSize"] == 60
    assert manifest["engine"] == "skia"


def test_override_engine_conflicting_with_named_preset_engine_is_rejected(monkeypatch):
    fake_preset = {
        "slug": "my-ffmpeg-preset",
        "subtitle_style_config": {"engine": "ffmpeg", "stylePreset": "classic_karaoke"},
    }
    monkeypatch.setattr(
        "src.infrastructure.preset_resolver.resolve_preset",
        lambda slug, user_id=None: fake_preset if slug == "my-ffmpeg-preset" else None,
    )
    with pytest.raises(SubtitleManifestError, match="conflicts with preset engine"):
        resolve_subtitle_manifest(
            {"engine": "skia"}, user_id=1, preset_slug="my-ffmpeg-preset"
        )
