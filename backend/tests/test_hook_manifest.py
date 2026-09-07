import pytest

from src.infrastructure.hook_manifest import (
    CANONICAL_HOOK_DEFAULT_ID,
    HookManifestError,
    resolve_hook_preset,
)


def test_empty_preset_returns_complete_canonical_neutral_manifest():
    manifest = resolve_hook_preset(user_id=987654, preset_slug="", explicit_override=None)
    assert manifest["preset_id"] == CANONICAL_HOOK_DEFAULT_ID
    assert manifest["hook_id"] == manifest["animation"]
    assert manifest["engine"] == "remotion"
    assert set(manifest) >= {
        "preset_id", "hook_id", "engine", "text_source", "duration",
        "position_y", "font_family", "font_size", "font_weight", "color",
        "background", "stroke", "shadow", "animation", "template",
        "version", "config",
    }


def test_missing_named_preset_is_invalid_not_default():
    with pytest.raises(HookManifestError, match="not found"):
        resolve_hook_preset(987654, "definitely-missing-preset", None)


@pytest.mark.parametrize("engine", ["remotion", "skia", "ffmpeg"])
def test_neutral_preset_accepts_explicit_engine_selection(engine):
    manifest = resolve_hook_preset(
        987654, "", {"engine": engine, "animation": "podcast_lower_third"}
    )
    assert manifest["engine"] == engine


def test_neutral_preset_accepts_explicit_hyperframes_template():
    manifest = resolve_hook_preset(
        987654, "", {"engine": "hyperframes", "template": "hook_cyber_hud"}
    )
    assert manifest["engine"] == "hyperframes"
    assert manifest["hook_id"] == "hook_cyber_hud"


@pytest.mark.parametrize("duration", [2, 3, 5])
@pytest.mark.parametrize("position_y", [20, 50, 80])
def test_manifest_preserves_duration_position_and_text_controls(duration, position_y):
    manifest = resolve_hook_preset(
        987654,
        "",
        {
            "engine": "remotion",
            "duration": duration,
            "positionY": position_y,
            "uppercase": True,
            "text": "BARIS SATU\nBARIS DUA",
        },
    )
    assert manifest["duration"] == duration
    assert manifest["position_y"] == position_y
    assert manifest["config"]["uppercase"] is True
    assert manifest["config"]["text"] == "BARIS SATU\nBARIS DUA"


def test_unknown_engine_is_rejected_without_inference():
    with pytest.raises(HookManifestError, match="Unsupported hook engine"):
        resolve_hook_preset(987654, "", {"engine": "hook_cyber_hud"})


def test_preview_render_spec_is_the_exact_manifest_config():
    manifest = resolve_hook_preset(987654, "", {"engine": "remotion", "duration": 5})
    assert manifest["config"]["engine"] == manifest["engine"]
    assert manifest["config"]["duration"] == manifest["duration"]
    assert manifest["config"]["animation"] == manifest["animation"]
