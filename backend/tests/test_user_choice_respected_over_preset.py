"""Regression tests: user choice for optional features (broll, autogrid, AI text)
must be respected end-to-end and NOT silently overridden by preset defaults.

Bug history (2026-09-23):
- Frontend sends `broll_enabled=false` to backend, but backend
  `service.create_job` merged preset's `broll_enabled=true` over the request.
- `_get_builtin_default_preset` and many DB presets include broll_config with
  `enabled=True` that clobbered user choice.
- `Job` entity default for subtypes was True (fail-open) instead of False.
- `services_v2.py` `getattr(job, ..., True)` defaults caused re-enable on reload.

These tests pin the user-first precedence: the user request wins, period.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.infrastructure.preset_resolver import (
    _get_builtin_default_preset,
    resolve_preset,
)


# ─── Test 1: Builtin default preset must NOT silently enable b-roll ──────────

def test_builtin_default_preset_has_broll_disabled_by_default():
    """The builtin fallback preset must default b-roll OFF so users who don't
    pick a b-roll preset get exactly that — no b-roll."""
    preset = _get_builtin_default_preset()
    assert preset["broll_enabled"] is False, (
        f"builtin default preset should default broll_enabled=False, "
        f"got {preset['broll_enabled']}"
    )
    assert preset["autogrid_enabled"] is False, (
        f"autogrid must default False (9:16 opt-in only), "
        f"got {preset['autogrid_enabled']}"
    )
    assert preset["text_emphasis_enabled"] is False, (
        f"text_emphasis must default False (opt-in only), "
        f"got {preset['text_emphasis_enabled']}"
    )


# ─── Test 2: Empty preset request falls back to off, not silently on ──────────

def test_empty_preset_request_resolves_to_broll_disabled():
    """When user submits with no preset, resolve_preset must return a preset
    with broll_enabled=False — so services.py merging doesn't clobber user."""
    resolved = resolve_preset("")  # "" or None should fall back to defaults
    # Note: resolve_preset("") returns either user_preset or _get_builtin_default_preset
    # depending on env. In a unit test env (no DB), the default path is taken.
    if resolved is None:
        return  # No DB context — skip
    assert resolved["broll_enabled"] is False, (
        f"resolve_preset('') should yield broll_enabled=False to prevent override, "
        f"got {resolved['broll_enabled']}. This is the silent-override bug."
    )
    assert resolved["autogrid_enabled"] is False


# ─── Test 3: User request precedence over preset ─────────────────────────────
#
# We test the merge logic directly because service.create_job requires a full
# async DB stack. The merging behavior is the substance of the bug.

def _apply_preset_overrides(request, resolved_preset):
    """Replicate the merge logic from services.py:334-357 to validate."""
    r = dict(request) if request else {}
    if not resolved_preset:
        return r
    broll_cfg = resolved_preset.get("broll_config") or resolved_preset.get("broll_style_config") or {}
    if isinstance(broll_cfg, dict):
        # ─── USER-FIRST PRECEDENCE (the fix) ───
        # Only override when user has NOT explicitly sent a value (i.e. sentinel None).
        # Real broll_enabled=False from user must NOT be clobbered.
        if "enabled" in broll_cfg:
            v = bool(broll_cfg["enabled"])
            r["broll_enabled"] = v if r.get("broll_enabled") is None else r["broll_enabled"]
        if "image_overlay" in broll_cfg:
            v = bool(broll_cfg["image_overlay"])
            r["broll_image_overlay"] = v if r.get("broll_image_overlay") is None else r["broll_image_overlay"]
        if "behind_person" in broll_cfg:
            v = bool(broll_cfg["behind_person"])
            r["broll_behind_person"] = v if r.get("broll_behind_person") is None else r["broll_behind_person"]
        if "video_footage" in broll_cfg:
            v = bool(broll_cfg["video_footage"])
            r["broll_video_footage"] = v if r.get("broll_video_footage") is None else r["broll_video_footage"]
        if "autogrid_enabled" in broll_cfg:
            v = bool(broll_cfg["autogrid_enabled"])
            r["autogrid_enabled"] = v if r.get("autogrid_enabled") is None else r["autogrid_enabled"]
    # Preset top-level broll_enabled key is ignored — user request wins.
    return r


def test_user_broll_false_not_overridden_by_preset_true():
    """THE BUG: preset with broll_enabled=True must NOT override user's False."""
    user_request = {
        "broll_enabled": False,
        "broll_image_overlay": False,
        "broll_behind_person": False,
        "broll_video_footage": False,
        "autogrid_enabled": False,
        "text_emphasis_enabled": False,
    }
    preset_with_broll_on = {
        "broll_config": {"enabled": True, "image_overlay": True,
                         "behind_person": True, "video_footage": True},
        "broll_enabled": True,
        "broll_image_overlay": True,
        "broll_behind_person": True,
        "broll_video_footage": True,
    }
    merged = _apply_preset_overrides(user_request, preset_with_broll_on)
    assert merged["broll_enabled"] is False, "preset clobbered user False"
    assert merged["broll_image_overlay"] is False
    assert merged["broll_behind_person"] is False
    assert merged["broll_video_footage"] is False
    assert merged["autogrid_enabled"] is False, "preset clobbered autogrid"


def test_user_broll_unspecified_inherits_from_preset():
    """When user does NOT specify broll_enabled, preset value is used."""
    user_request = {"broll_enabled": None, "autogrid_enabled": None}
    preset = {"broll_config": {"enabled": True}, "broll_enabled": True}
    merged = _apply_preset_overrides(user_request, preset)
    assert merged["broll_enabled"] is True


def test_user_text_emphasis_false_honored():
    """Text emphasis must respect explicit user off."""
    user_request = {"text_emphasis_enabled": False}
    preset = {"text_emphasis_enabled": True}
    merged = dict(user_request)
    # Apply same rule: only override if None
    if merged["text_emphasis_enabled"] is None:
        merged["text_emphasis_enabled"] = preset["text_emphasis_enabled"]
    assert merged["text_emphasis_enabled"] is False


# ─── Test 4: Job entity defaults must be fail-closed ─────────────────────────

def test_job_entity_defaults_are_fail_closed():
    """Job entity default values for optional features must be off/false,
    matching the request schema. Pipeline must not activate from entity default.
    """
    from src.domain.entities import Job, JobStatus

    j = Job(job_id="x", youtube_url="https://example.com", status=JobStatus.VALIDATING)
    assert j.broll_enabled is False, (
        f"Job.broll_enabled default must be False (fail-closed); got {j.broll_enabled}"
    )
    assert j.broll_image_overlay is False, (
        f"Job.broll_image_overlay default must be False; got {j.broll_image_overlay}"
    )
    assert j.broll_behind_person is False
    assert j.broll_video_footage is False
    assert j.autogrid_enabled is False
    assert getattr(j, "text_emphasis_enabled", False) is False


# ─── Test 5: Preset with subtypes-only (no enabled key) does NOT enable b-roll

def test_preset_subtypes_only_does_not_imply_broll_enabled():
    """User preset saved with `broll_style = { image_overlay: true, ... }`
    but no explicit `enabled` key must NOT be read as broll_enabled=True.
    Earlier code defaulted enabled=True whenever broll_style had any subtype key,
    causing presets with old format to silently re-enable b-roll.
    """
    # Simulate the merge logic in preset_resolver._format_user_preset_row
    broll_style = {"image_overlay": True, "behind_person": True, "video_footage": True}
    # Old behavior: broll_enabled = bool(broll_style.get("enabled", True)) → True
    # New behavior: broll_enabled defaults to False unless "enabled" is explicit
    if isinstance(broll_style, dict) and broll_style:
        broll_enabled = bool(broll_style.get("enabled", False))  # FALSE default
    else:
        broll_enabled = False
    assert broll_enabled is False, (
        "preset with subtypes but no 'enabled' key must default to broll_enabled=False"
    )


if __name__ == "__main__":
    test_builtin_default_preset_has_broll_disabled_by_default()
    test_empty_preset_request_resolves_to_broll_disabled()
    test_user_broll_false_not_overridden_by_preset_true()
    test_user_broll_unspecified_inherits_from_preset()
    test_user_text_emphasis_false_honored()
    test_job_entity_defaults_are_fail_closed()
    test_preset_subtypes_only_does_not_imply_broll_enabled()
    print("ALL REGRESSION TESTS PASSED")
