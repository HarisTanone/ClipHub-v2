"""Tests for dynamic database system configuration store with RBAC."""
import pytest
from src.config import settings
from src.infrastructure.system_config_store import (
    get_system_setting,
    set_system_setting,
    bulk_set_system_settings,
    get_all_settings_for_role,
    mask_secret_value,
    SYSTEM_SETTINGS_METADATA,
)


def test_system_config_defaults():
    """Verify that settings can be retrieved from defaults or .env."""
    provider = get_system_setting("LLM_PROVIDER")
    assert provider in ("nine_router", "groq", "gemini", "ollama")


def test_system_config_dynamic_update():
    """Verify that updating a setting in DB immediately reflects in settings."""
    orig = get_system_setting("REMOTION_CONCURRENCY", 2)
    new_val = 6
    ok = set_system_setting("REMOTION_CONCURRENCY", new_val, user_id=1)
    assert ok is True

    # Test direct store lookup
    assert get_system_setting("REMOTION_CONCURRENCY") == new_val

    # Test settings.__getattribute__ dynamic access
    assert settings.REMOTION_CONCURRENCY == new_val

    # Restore
    set_system_setting("REMOTION_CONCURRENCY", orig, user_id=1)
    assert settings.REMOTION_CONCURRENCY == orig


def test_system_config_rbac_role_filtering():
    """Verify that viewers and editors see only their permitted settings."""
    viewer_settings = get_all_settings_for_role("viewer")
    editor_settings = get_all_settings_for_role("editor")
    superadmin_settings = get_all_settings_for_role("superadmin")

    # Viewer should have fewer settings than editor, editor fewer than superadmin
    assert len(viewer_settings) <= len(editor_settings)
    assert len(editor_settings) < len(superadmin_settings)

    # Superadmin should see all registered settings
    assert len(superadmin_settings) == len(SYSTEM_SETTINGS_METADATA)

    # Editor should see visual and b-roll settings
    editor_keys = {s["key"] for s in editor_settings}
    assert "BROLL_SPLICE_ENABLED" in editor_keys
    assert "TOP_OVERLAY_ENABLED" in editor_keys

    # Editor should NOT see sensitive machine keys
    assert "JWT_SECRET_KEY" not in editor_keys


def test_system_config_secret_masking():
    """Verify that secrets are masked for safety."""
    masked = mask_secret_value("sk-1234567890abcdef")
    assert "..." in masked
    assert not masked.startswith("sk-1234567890")
    assert masked.endswith("cdef")


def test_system_config_bulk_update():
    """Verify transactional bulk update of multiple settings."""
    updates = {
        "BROLL_SPLICE_MAX_PER_CLIP": 5,
        "TOP_OVERLAY_SPLIT_RATIO": 0.70,
    }
    count = bulk_set_system_settings(updates, user_id=1)
    assert count == 2
    assert get_system_setting("BROLL_SPLICE_MAX_PER_CLIP") == 5
    assert get_system_setting("TOP_OVERLAY_SPLIT_RATIO") == 0.70
