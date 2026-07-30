"""Canvas background template library for 16:9 and 1:1 outputs.

Templates are design presets (gradient + accents + video placement), not flat colors.
Stored as data so new templates can be added without UI rewrites.
"""
from __future__ import annotations

from typing import Any

# Output resolution by aspect (width, height)
ASPECT_RESOLUTION: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
}

# Layouts are normalized fractions of canvas (0..1) unless noted as px.
_DEFAULT_LAYOUT_16_9 = {
    "videoX": 0.08,
    "videoY": 0.10,
    "videoW": 0.84,
    "videoH": 0.80,
    "borderRadius": 18,
    "shadow": "0 18px 60px rgba(0,0,0,0.55)",
}

_DEFAULT_LAYOUT_1_1 = {
    "videoX": 0.10,
    "videoY": 0.12,
    "videoW": 0.80,
    "videoH": 0.76,
    "borderRadius": 22,
    "shadow": "0 16px 48px rgba(0,0,0,0.5)",
}


def _tpl(
    id: str,
    name: str,
    category: str,
    *,
    background: dict[str, Any],
    accents: list[dict[str, Any]] | None = None,
    layout_16_9: dict | None = None,
    layout_1_1: dict | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "category": category,
        "supportedAspectRatios": ["16:9", "1:1"],
        "background": background,
        "accents": accents or [],
        "layout": {
            "16:9": {**_DEFAULT_LAYOUT_16_9, **(layout_16_9 or {})},
            "1:1": {**_DEFAULT_LAYOUT_1_1, **(layout_1_1 or {})},
        },
    }


CANVAS_TEMPLATES: list[dict[str, Any]] = [
    _tpl(
        "dark-studio",
        "Dark Studio",
        "Studio",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#1a1b1e"},
                {"offset": 0.45, "color": "#0d0e10"},
                {"offset": 1, "color": "#050505"},
            ],
            "angle": 160,
            "vignette": 0.55,
        },
        accents=[
            {"type": "soft-glow", "x": 0.5, "y": 0.15, "r": 0.35, "color": "rgba(255,255,255,0.04)"},
            {"type": "bar", "x": 0.08, "y": 0.92, "w": 0.18, "h": 0.006, "color": "rgba(255,255,255,0.12)"},
        ],
        layout_16_9={"videoX": 0.10, "videoY": 0.12, "videoW": 0.80, "videoH": 0.76, "borderRadius": 14},
        layout_1_1={"videoX": 0.12, "videoY": 0.14, "videoW": 0.76, "videoH": 0.72, "borderRadius": 16},
    ),
    _tpl(
        "modern-gradient",
        "Modern Gradient",
        "Modern",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#0b1220"},
                {"offset": 0.5, "color": "#12182b"},
                {"offset": 1, "color": "#1a0f2e"},
            ],
            "angle": 135,
            "vignette": 0.4,
        },
        accents=[
            {"type": "blob", "x": 0.12, "y": 0.18, "r": 0.22, "color": "rgba(99,102,241,0.18)"},
            {"type": "blob", "x": 0.88, "y": 0.82, "r": 0.28, "color": "rgba(168,85,247,0.14)"},
            {"type": "line", "x1": 0.05, "y1": 0.88, "x2": 0.28, "y2": 0.88, "color": "rgba(129,140,248,0.45)", "w": 2},
        ],
        layout_16_9={"videoX": 0.07, "videoY": 0.09, "videoW": 0.86, "videoH": 0.82, "borderRadius": 20},
    ),
    _tpl(
        "podcast-studio",
        "Podcast Studio",
        "Podcast",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#1c1410"},
                {"offset": 0.55, "color": "#120e0c"},
                {"offset": 1, "color": "#080706"},
            ],
            "angle": 180,
            "vignette": 0.5,
        },
        accents=[
            {"type": "soft-glow", "x": 0.5, "y": 0.35, "r": 0.45, "color": "rgba(251,146,60,0.08)"},
            {"type": "ring", "x": 0.5, "y": 0.5, "r": 0.42, "color": "rgba(255,255,255,0.04)", "stroke": 1},
            {"type": "bar", "x": 0.42, "y": 0.08, "w": 0.16, "h": 0.01, "color": "rgba(251,146,60,0.55)"},
        ],
        layout_16_9={"videoX": 0.14, "videoY": 0.10, "videoW": 0.72, "videoH": 0.78, "borderRadius": 12},
        layout_1_1={"videoX": 0.14, "videoY": 0.12, "videoW": 0.72, "videoH": 0.70, "borderRadius": 14},
    ),
    _tpl(
        "minimal-premium",
        "Minimal Premium",
        "Minimal",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#141414"},
                {"offset": 1, "color": "#0a0a0a"},
            ],
            "angle": 180,
            "vignette": 0.25,
        },
        accents=[
            {"type": "frame", "inset": 0.035, "color": "rgba(255,255,255,0.08)", "stroke": 1},
        ],
        layout_16_9={"videoX": 0.06, "videoY": 0.08, "videoW": 0.88, "videoH": 0.84, "borderRadius": 8},
        layout_1_1={"videoX": 0.08, "videoY": 0.08, "videoW": 0.84, "videoH": 0.84, "borderRadius": 10},
    ),
    _tpl(
        "neon-glow",
        "Neon",
        "Creative",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#050510"},
                {"offset": 0.5, "color": "#0a0a1a"},
                {"offset": 1, "color": "#0d0518"},
            ],
            "angle": 200,
            "vignette": 0.45,
        },
        accents=[
            {"type": "blob", "x": 0.15, "y": 0.2, "r": 0.2, "color": "rgba(34,211,238,0.15)"},
            {"type": "blob", "x": 0.85, "y": 0.75, "r": 0.25, "color": "rgba(236,72,153,0.12)"},
            {"type": "line", "x1": 0.72, "y1": 0.1, "x2": 0.92, "y2": 0.1, "color": "rgba(34,211,238,0.6)", "w": 2},
            {"type": "line", "x1": 0.08, "y1": 0.9, "x2": 0.28, "y2": 0.9, "color": "rgba(236,72,153,0.55)", "w": 2},
        ],
        layout_16_9={"videoX": 0.09, "videoY": 0.11, "videoW": 0.82, "videoH": 0.78, "borderRadius": 16},
    ),
    _tpl(
        "gradient-depth",
        "Gradient Depth",
        "Modern",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#0f172a"},
                {"offset": 0.4, "color": "#1e1b4b"},
                {"offset": 0.75, "color": "#312e81"},
                {"offset": 1, "color": "#0f172a"},
            ],
            "angle": 145,
            "vignette": 0.5,
        },
        accents=[
            {"type": "soft-glow", "x": 0.3, "y": 0.25, "r": 0.4, "color": "rgba(99,102,241,0.12)"},
            {"type": "soft-glow", "x": 0.75, "y": 0.7, "r": 0.35, "color": "rgba(14,165,233,0.1)"},
        ],
    ),
    _tpl(
        "studio-soft",
        "Studio Soft",
        "Studio",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#1f1f23"},
                {"offset": 0.5, "color": "#16161a"},
                {"offset": 1, "color": "#0c0c0e"},
            ],
            "angle": 170,
            "vignette": 0.35,
        },
        accents=[
            {"type": "soft-glow", "x": 0.5, "y": 0.0, "r": 0.55, "color": "rgba(255,255,255,0.05)"},
            {"type": "bar", "x": 0.78, "y": 0.9, "w": 0.14, "h": 0.005, "color": "rgba(255,255,255,0.15)"},
        ],
        layout_16_9={"videoX": 0.08, "videoY": 0.1, "videoW": 0.84, "videoH": 0.8, "borderRadius": 24},
        layout_1_1={"videoX": 0.1, "videoY": 0.1, "videoW": 0.8, "videoH": 0.8, "borderRadius": 28},
    ),
    _tpl(
        "creative-depth",
        "Creative",
        "Creative",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#111827"},
                {"offset": 0.55, "color": "#1f2937"},
                {"offset": 1, "color": "#0b1020"},
            ],
            "angle": 120,
            "vignette": 0.4,
        },
        accents=[
            {"type": "blob", "x": 0.9, "y": 0.12, "r": 0.18, "color": "rgba(52,211,153,0.12)"},
            {"type": "blob", "x": 0.08, "y": 0.85, "r": 0.2, "color": "rgba(59,130,246,0.12)"},
            {"type": "frame", "inset": 0.025, "color": "rgba(255,255,255,0.06)", "stroke": 1},
        ],
        layout_16_9={"videoX": 0.11, "videoY": 0.12, "videoW": 0.78, "videoH": 0.76, "borderRadius": 18},
    ),
]

_BY_ID = {t["id"]: t for t in CANVAS_TEMPLATES}


def list_templates(aspect_ratio: str | None = None) -> list[dict[str, Any]]:
    if not aspect_ratio or aspect_ratio == "9:16":
        return list(CANVAS_TEMPLATES)
    out = []
    for t in CANVAS_TEMPLATES:
        if aspect_ratio in t["supportedAspectRatios"]:
            out.append(t)
    return out


def get_template(template_id: str | None) -> dict[str, Any] | None:
    if not template_id:
        return None
    return _BY_ID.get(template_id)


def resolution_for_aspect(aspect_ratio: str) -> tuple[int, int]:
    return ASPECT_RESOLUTION.get(aspect_ratio, ASPECT_RESOLUTION["9:16"])


def build_canvas_config(
    aspect_ratio: str,
    *,
    background_mode: str | None = None,
    background_template_id: str | None = None,
    background_image_url: str | None = None,
) -> dict[str, Any] | None:
    """Build Remotion/FE canvas config. None for 9:16 (full-bleed, no template)."""
    if aspect_ratio == "9:16":
        return None
    mode = background_mode or "template"
    if mode not in ("template", "upload"):
        mode = "template"
    w, h = resolution_for_aspect(aspect_ratio)
    cfg: dict[str, Any] = {
        "aspectRatio": aspect_ratio,
        "width": w,
        "height": h,
        "mode": mode,
        "backgroundImageUrl": background_image_url if mode == "upload" else None,
    }
    if mode == "template":
        tpl = get_template(background_template_id) or CANVAS_TEMPLATES[0]
        layout = tpl["layout"].get(aspect_ratio) or tpl["layout"]["16:9"]
        cfg.update(
            {
                "templateId": tpl["id"],
                "templateName": tpl["name"],
                "background": tpl["background"],
                "accents": tpl["accents"],
                "layout": layout,
            }
        )
    else:
        # Upload: full-bleed image behind, video inset slightly for depth
        layout = _DEFAULT_LAYOUT_16_9 if aspect_ratio == "16:9" else _DEFAULT_LAYOUT_1_1
        cfg.update(
            {
                "templateId": None,
                "background": {
                    "type": "image" if background_image_url else "solid",
                    "color": "#0a0a0a",
                    "imageUrl": background_image_url,
                    "vignette": 0.3,
                },
                "accents": [],
                "layout": layout,
            }
        )
    return cfg
