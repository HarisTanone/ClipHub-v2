"""Canonical Subtitle manifest — single resolver shared by all renderers.

A resolved manifest is immutable render intent: one engine, one subtitle_id
(style preset or HF template), and a complete normalized configuration.
Legacy field aliases are normalized here only; renderers must not infer an
engine or choose another visual preset.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Optional

from src.infrastructure.preset_resolver import DEFAULT_SUBTITLE_STYLE

CANONICAL_SUBTITLE_DEFAULT_ID = "canonical-subtitle-neutral-v1"
SUBTITLE_MANIFEST_VERSION = "1.0.0"
SUBTITLE_RENDERER_VERSION = "subtitle-render-spec-v1"
SUPPORTED_SUBTITLE_ENGINES = frozenset({"remotion", "hyperframes", "skia", "ffmpeg"})


class SubtitleManifestError(ValueError):
    """The requested Subtitle render intent is missing, invalid, or ambiguous."""


@dataclass(frozen=True)
class SubtitleManifest:
    preset_id: str
    subtitle_id: str
    engine: str
    enabled: bool
    position_y: float
    font_family: str
    font_size: float
    font_weight: str
    color: str
    highlight_color: str
    background: dict[str, Any]
    stroke: dict[str, Any]
    shadow: dict[str, Any]
    template: str
    version: str
    config: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(cfg: Mapping[str, Any], camel: str, snake: str, default: float) -> float:
    raw = cfg.get(camel, cfg.get(snake, default))
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise SubtitleManifestError(f"Invalid Subtitle value {camel}={raw!r}") from exc


def _canonical_config(raw: Mapping[str, Any]) -> dict[str, Any]:
    cfg = deepcopy(DEFAULT_SUBTITLE_STYLE)
    cfg.update(dict(raw))
    engine = str(cfg.get("engine") or "").strip().lower()
    if engine not in SUPPORTED_SUBTITLE_ENGINES:
        raise SubtitleManifestError(f"Unsupported subtitle engine: {engine or '<empty>'}")
    cfg["engine"] = engine
    cfg["positionY"] = _number(cfg, "positionY", "position_y", float(DEFAULT_SUBTITLE_STYLE.get("positionY", 85)))
    if not 0 <= cfg["positionY"] <= 100:
        raise SubtitleManifestError("Subtitle positionY must be between 0 and 100")
    template = str(cfg.get("template") or cfg.get("hf_template") or "").strip()
    if engine == "hyperframes" and not template:
        raise SubtitleManifestError("HyperFrames Subtitle requires an explicit canonical template")
    return cfg


def resolve_subtitle_manifest(
    explicit_config: Optional[Mapping[str, Any]],
) -> dict[str, Any]:
    """Resolve one complete Subtitle manifest without visual fallback or inference.

    - None / empty dict → canonical neutral Remotion preset.
    - Explicit engine must be one of the 4 supported values.
    - Engine is taken exclusively from cfg['engine']; prefix conventions are
      NOT used here — that logic lives in resolve_engine() for legacy compat only.
    - An already-resolved manifest (has 'version' key matching our version) is
      returned as-is (idempotent).
    """
    raw = dict(explicit_config or {})

    # Idempotency: already a resolved manifest → return unchanged
    if raw.get("version") == SUBTITLE_MANIFEST_VERSION and "subtitle_id" in raw:
        return raw

    if not raw.get("engine"):
        raw["engine"] = "ffmpeg"

    cfg = _canonical_config(raw)
    engine = cfg["engine"]
    template = str(cfg.get("template") or cfg.get("hf_template") or "").strip()
    # subtitle_id: for HF = template; for others = stylePreset or style_preset
    style_preset = str(
        cfg.get("stylePreset") or cfg.get("style_preset") or cfg.get("id") or ""
    ).strip()
    subtitle_id = template if engine == "hyperframes" else (style_preset or "classic_karaoke")

    manifest = SubtitleManifest(
        preset_id=CANONICAL_SUBTITLE_DEFAULT_ID,
        subtitle_id=subtitle_id,
        engine=engine,
        enabled=bool(cfg.get("enabled", True) is not False),
        position_y=float(cfg["positionY"]),
        font_family=str(cfg.get("fontFamily") or cfg.get("font_family") or ""),
        font_size=float(cfg.get("fontSize") or cfg.get("font_size") or 34),
        font_weight=str(cfg.get("fontWeight") or cfg.get("font_weight") or "700"),
        color=str(cfg.get("color") or ""),
        highlight_color=str(cfg.get("highlightColor") or cfg.get("highlight_color") or ""),
        background={
            "enabled": bool(cfg.get("bgEnabled", True)),
            "color": str(cfg.get("bgColor") or ""),
            "opacity": float(cfg.get("bgOpacity") or 0),
            "radius": float(cfg.get("bgRadius") or 0),
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
        },
        template=template,
        version=SUBTITLE_MANIFEST_VERSION,
        config=cfg,
    ).to_dict()
    return manifest


def subtitle_render_spec_hash(manifest: Mapping[str, Any]) -> str:
    """Stable cache key for native subtitle preview and final render-spec parity."""
    payload = {"manifest": dict(manifest), "renderer": SUBTITLE_RENDERER_VERSION}
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
