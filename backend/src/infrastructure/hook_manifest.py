"""Canonical Hook manifest and the only supported Hook preset resolver.

A resolved manifest is immutable render intent: one preset, one hook id, one
engine, and one complete configuration shared by preview and final renderers.
Legacy field aliases are normalized here only; renderers must not infer an
engine or choose another visual preset.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Optional

from src.infrastructure.preset_resolver import DEFAULT_HOOK_STYLE, resolve_preset

CANONICAL_HOOK_DEFAULT_ID = "canonical-neutral-v1"
HOOK_MANIFEST_VERSION = "1.0.0"
HOOK_RENDERER_VERSION = "hook-render-spec-v1"
SUPPORTED_HOOK_ENGINES = frozenset({"remotion", "hyperframes", "skia", "ffmpeg"})
_EMPTY_PRESETS = frozenset({"", "default", "none", CANONICAL_HOOK_DEFAULT_ID})


class HookManifestError(ValueError):
    """The requested Hook render intent is missing, invalid, or ambiguous."""


@dataclass(frozen=True)
class HookManifest:
    preset_id: str
    hook_id: str
    engine: str
    text_source: str
    duration: float
    position_y: float
    font_family: str
    font_size: float
    font_weight: str
    color: str
    background: dict[str, Any]
    stroke: dict[str, Any]
    shadow: dict[str, Any]
    animation: str
    template: str
    version: str
    config: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(config: Mapping[str, Any], camel: str, snake: str, default: float) -> float:
    raw = config.get(camel, config.get(snake, default))
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise HookManifestError(f"Invalid Hook value {camel}={raw!r}") from exc


def _canonical_config(raw: Mapping[str, Any]) -> dict[str, Any]:
    cfg = deepcopy(DEFAULT_HOOK_STYLE)
    cfg.update(dict(raw))
    engine = str(cfg.get("engine") or "").strip().lower()
    if engine not in SUPPORTED_HOOK_ENGINES:
        raise HookManifestError(f"Unsupported hook engine: {engine or '<empty>'}")
    cfg["engine"] = engine
    cfg["duration"] = _number(cfg, "duration", "duration", 3.0)
    cfg["positionY"] = _number(cfg, "positionY", "position_y", 78.0)
    if cfg["duration"] <= 0:
        raise HookManifestError("Hook duration must be greater than zero")
    if not 0 <= cfg["positionY"] <= 100:
        raise HookManifestError("Hook positionY must be between 0 and 100")
    animation = str(cfg.get("animation") or "").strip()
    template = str(cfg.get("template") or cfg.get("hf_template") or "").strip()
    if engine == "hyperframes" and not template:
        raise HookManifestError("HyperFrames Hook requires an explicit canonical template")
    if engine != "hyperframes" and not animation:
        raise HookManifestError(f"{engine} Hook requires an explicit canonical animation")
    return cfg


def resolve_hook_preset(
    user_id: Optional[int],
    preset_slug: Optional[str],
    explicit_override: Optional[Mapping[str, Any]],
) -> dict[str, Any]:
    """Resolve one complete Hook manifest without visual fallback or inference.

    Empty/default selects the canonical neutral preset. A named missing preset is
    invalid. ``active`` is delegated with the same user id and is rejected when
    that user has no configured preset. Explicit overrides may tune a preset but
    may not silently change its engine.
    """
    requested = str(preset_slug or "").strip()
    key = requested.lower()
    preset_id = CANONICAL_HOOK_DEFAULT_ID
    base = deepcopy(DEFAULT_HOOK_STYLE)

    if key not in _EMPTY_PRESETS:
        resolved = resolve_preset(requested, user_id=user_id)
        if not resolved or resolved.get("source") == "builtin_default":
            raise HookManifestError(f"Hook preset '{requested}' not found for user {user_id}")
        preset_id = str(resolved.get("slug") or resolved.get("id") or requested)
        base = deepcopy(resolved.get("hook_style_config") or {})
        if not base:
            raise HookManifestError(f"Hook preset '{requested}' has no Hook configuration")

    override = dict(explicit_override or {})
    base_engine = str(base.get("engine") or "").strip().lower()
    override_engine = str(override.get("engine") or "").strip().lower()
    if override_engine and override_engine not in SUPPORTED_HOOK_ENGINES:
        raise HookManifestError(f"Unsupported hook engine: {override_engine}")
    # A named preset owns its engine and cannot be silently changed. The
    # canonical neutral default is only a baseline and must accept the user's
    # explicit engine selection (editor/NewJob/native preview).
    if key not in _EMPTY_PRESETS and override_engine and base_engine and override_engine != base_engine:
        raise HookManifestError(
            f"Explicit Hook engine '{override_engine}' conflicts with preset engine '{base_engine}'"
        )
    base.update(override)
    cfg = _canonical_config(base)
    engine = cfg["engine"]
    animation = str(cfg.get("animation") or "")
    template = str(cfg.get("template") or cfg.get("hf_template") or "")
    hook_id = template if engine == "hyperframes" else animation

    manifest = HookManifest(
        preset_id=preset_id,
        hook_id=hook_id,
        engine=engine,
        text_source=str(cfg.get("text_source") or ("custom" if cfg.get("text") else "clip_hook")),
        duration=float(cfg["duration"]),
        position_y=float(cfg["positionY"]),
        font_family=str(cfg.get("fontFamily") or ""),
        font_size=float(cfg.get("fontSize") or 0),
        font_weight=str(cfg.get("fontWeight") or ""),
        color=str(cfg.get("color") or ""),
        background={
            "enabled": bool(cfg.get("boxEnabled") or float(cfg.get("bgOpacity") or 0) > 0),
            "color": str(cfg.get("boxColor") or cfg.get("bgColor") or ""),
            "opacity": float(cfg.get("boxOpacity", cfg.get("bgOpacity", 0)) or 0),
        },
        stroke={
            "enabled": bool(cfg.get("strokeEnabled")),
            "color": str(cfg.get("strokeColor") or ""),
            "width": float(cfg.get("strokeWidth") or 0),
        },
        shadow={
            "enabled": bool(cfg.get("shadowEnabled")),
            "color": str(cfg.get("shadowColor") or ""),
            "blur": float(cfg.get("shadowBlur") or 0),
            "x": float(cfg.get("shadowX") or 0),
            "y": float(cfg.get("shadowY") or 0),
        },
        animation=animation,
        template=template,
        version=HOOK_MANIFEST_VERSION,
        config=cfg,
    ).to_dict()
    return manifest


def hook_render_spec_hash(manifest: Mapping[str, Any], *, frame: int = 0) -> str:
    """Stable cache key for native preview and final render-spec parity."""
    payload = {"manifest": dict(manifest), "frame": int(frame), "renderer": HOOK_RENDERER_VERSION}
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
