"""Canvas templates: content aspect (16:9/1:1) on TikTok 9:16 final canvas.

Final output is ALWAYS 1080×1920 (TikTok). Content stays native aspect
inside a centered video slot; template fills top/bottom (never black bars).
9:16 content = full-bleed, no template.
"""
from __future__ import annotations

from typing import Any

# Final TikTok canvas — always
OUTPUT_RESOLUTION: tuple[int, int] = (1080, 1920)

# Intermediate content processing dims (pre-Remotion footage)
CONTENT_RESOLUTION: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
}

# Back-compat alias used by b-roll / splicer (content dims, not final canvas)
ASPECT_RESOLUTION = CONTENT_RESOLUTION

# 16:9 content on 9:16 canvas:
#   full-width band, height = (9/16)/(16/9) of canvas ≈ 0.3164, centered
#   top/bottom ~0.3418 each for template fill
_LAYOUT_16_9_ON_916 = {
    "videoX": 0.0,
    "videoY": 0.3418,
    "videoW": 1.0,
    "videoH": 0.3164,
    "borderRadius": 0,
    "shadow": "0 12px 40px rgba(0,0,0,0.45)",
}

# 1:1 content on 9:16: square band, full width, centered
_LAYOUT_1_1_ON_916 = {
    "videoX": 0.0,
    "videoY": 0.21875,
    "videoW": 1.0,
    "videoH": 0.5625,
    "borderRadius": 0,
    "shadow": "0 12px 40px rgba(0,0,0,0.4)",
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
            "16:9": {**_LAYOUT_16_9_ON_916, **(layout_16_9 or {})},
            "1:1": {**_LAYOUT_1_1_ON_916, **(layout_1_1 or {})},
        },
    }


# Rich theme templates — accents biased to top/bottom bands (letterbox zones)
CANVAS_TEMPLATES: list[dict[str, Any]] = [
    _tpl(
        "video-mirror",
        "Blurred Video Mirror",
        "Dynamic",
        background={
            "type": "video_mirror",
            "blurAmount": 45,
            "dimAmount": 0.55,
            "vignette": 0.4,
        },
        accents=[
            {"type": "soft-glow", "x": 0.5, "y": 0.35, "r": 0.5, "color": "rgba(255,255,255,0.06)"},
            {"type": "soft-glow", "x": 0.5, "y": 0.65, "r": 0.5, "color": "rgba(255,255,255,0.06)"},
        ],
        layout_16_9={"videoX": 0.0, "videoY": 0.3418, "videoW": 1.0, "videoH": 0.3164, "borderRadius": 0, "ambientGlow": True},
        layout_1_1={"videoX": 0.04, "videoY": 0.24, "videoW": 0.92, "videoH": 0.52, "borderRadius": 16, "ambientGlow": True},
    ),
    _tpl(
        "dark-studio",
        "Dark Studio",
        "Studio",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#1a1b1e"},
                {"offset": 0.35, "color": "#0d0e10"},
                {"offset": 0.65, "color": "#0d0e10"},
                {"offset": 1, "color": "#050505"},
            ],
            "angle": 180,
            "vignette": 0.45,
        },
        accents=[
            {"type": "soft-glow", "x": 0.5, "y": 0.12, "r": 0.4, "color": "rgba(255,255,255,0.06)"},
            {"type": "soft-glow", "x": 0.5, "y": 0.88, "r": 0.35, "color": "rgba(255,255,255,0.04)"},
            {"type": "bar", "x": 0.3, "y": 0.06, "w": 0.4, "h": 0.004, "color": "rgba(255,255,255,0.2)"},
            {"type": "bar", "x": 0.35, "y": 0.94, "w": 0.3, "h": 0.004, "color": "rgba(255,255,255,0.15)"},
            {"type": "frame", "inset": 0.02, "color": "rgba(255,255,255,0.08)", "stroke": 1},
        ],
        layout_16_9={"videoX": 0.0, "videoY": 0.3418, "videoW": 1.0, "videoH": 0.3164, "borderRadius": 0},
        layout_1_1={"videoX": 0.04, "videoY": 0.24, "videoW": 0.92, "videoH": 0.52, "borderRadius": 12},
    ),
    _tpl(
        "modern-gradient",
        "Modern Gradient",
        "Modern",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#0b1220"},
                {"offset": 0.4, "color": "#12182b"},
                {"offset": 0.6, "color": "#1a0f2e"},
                {"offset": 1, "color": "#0a0614"},
            ],
            "angle": 180,
            "vignette": 0.35,
        },
        accents=[
            {"type": "blob", "x": 0.15, "y": 0.1, "r": 0.28, "color": "rgba(99,102,241,0.22)"},
            {"type": "blob", "x": 0.85, "y": 0.9, "r": 0.3, "color": "rgba(168,85,247,0.18)"},
            {"type": "line", "x1": 0.08, "y1": 0.18, "x2": 0.35, "y2": 0.18, "color": "rgba(129,140,248,0.55)", "w": 2},
            {"type": "line", "x1": 0.65, "y1": 0.82, "x2": 0.92, "y2": 0.82, "color": "rgba(168,85,247,0.5)", "w": 2},
            {"type": "ring", "x": 0.5, "y": 0.12, "r": 0.08, "color": "rgba(99,102,241,0.25)", "stroke": 1},
        ],
        layout_16_9={"borderRadius": 0},
        layout_1_1={"videoX": 0.05, "videoY": 0.2469, "videoW": 0.9, "videoH": 0.5062, "borderRadius": 16},
    ),
    _tpl(
        "podcast-studio",
        "Podcast Studio",
        "Podcast",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#2a1a10"},
                {"offset": 0.35, "color": "#120e0c"},
                {"offset": 0.65, "color": "#120e0c"},
                {"offset": 1, "color": "#1a1008"},
            ],
            "angle": 180,
            "vignette": 0.5,
        },
        accents=[
            {"type": "soft-glow", "x": 0.5, "y": 0.15, "r": 0.45, "color": "rgba(251,146,60,0.12)"},
            {"type": "soft-glow", "x": 0.5, "y": 0.85, "r": 0.4, "color": "rgba(251,146,60,0.08)"},
            {"type": "bar", "x": 0.38, "y": 0.08, "w": 0.24, "h": 0.008, "color": "rgba(251,146,60,0.7)"},
            {"type": "bar", "x": 0.4, "y": 0.92, "w": 0.2, "h": 0.006, "color": "rgba(251,146,60,0.45)"},
            {"type": "ring", "x": 0.5, "y": 0.5, "r": 0.48, "color": "rgba(255,255,255,0.03)", "stroke": 1},
        ],
        layout_16_9={"videoX": 0.03, "videoY": 0.35, "videoW": 0.94, "videoH": 0.3, "borderRadius": 8},
        layout_1_1={"videoX": 0.06, "videoY": 0.24, "videoW": 0.88, "videoH": 0.52, "borderRadius": 10},
    ),
    _tpl(
        "minimal-premium",
        "Minimal Premium",
        "Minimal",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#181818"},
                {"offset": 0.5, "color": "#0c0c0c"},
                {"offset": 1, "color": "#181818"},
            ],
            "angle": 180,
            "vignette": 0.2,
        },
        accents=[
            {"type": "frame", "inset": 0.025, "color": "rgba(255,255,255,0.12)", "stroke": 1},
            {"type": "bar", "x": 0.42, "y": 0.12, "w": 0.16, "h": 0.003, "color": "rgba(255,255,255,0.25)"},
            {"type": "bar", "x": 0.42, "y": 0.88, "w": 0.16, "h": 0.003, "color": "rgba(255,255,255,0.2)"},
        ],
        layout_16_9={"videoX": 0.0, "videoY": 0.3418, "videoW": 1.0, "videoH": 0.3164, "borderRadius": 0},
        layout_1_1={"videoX": 0.04, "videoY": 0.23, "videoW": 0.92, "videoH": 0.54, "borderRadius": 4},
    ),
    _tpl(
        "neon-glow",
        "Neon",
        "Creative",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#050510"},
                {"offset": 0.4, "color": "#0a0a1a"},
                {"offset": 0.6, "color": "#0a0a1a"},
                {"offset": 1, "color": "#0d0518"},
            ],
            "angle": 180,
            "vignette": 0.4,
        },
        accents=[
            {"type": "blob", "x": 0.2, "y": 0.1, "r": 0.25, "color": "rgba(34,211,238,0.2)"},
            {"type": "blob", "x": 0.8, "y": 0.9, "r": 0.28, "color": "rgba(236,72,153,0.18)"},
            {"type": "line", "x1": 0.1, "y1": 0.2, "x2": 0.4, "y2": 0.2, "color": "rgba(34,211,238,0.7)", "w": 2},
            {"type": "line", "x1": 0.6, "y1": 0.8, "x2": 0.9, "y2": 0.8, "color": "rgba(236,72,153,0.65)", "w": 2},
            {"type": "bar", "x": 0.0, "y": 0.0, "w": 1.0, "h": 0.006, "color": "rgba(34,211,238,0.5)"},
            {"type": "bar", "x": 0.0, "y": 0.994, "w": 1.0, "h": 0.006, "color": "rgba(236,72,153,0.5)"},
        ],
        layout_16_9={"videoX": 0.02, "videoY": 0.35, "videoW": 0.96, "videoH": 0.3, "borderRadius": 4},
        layout_1_1={"videoX": 0.05, "videoY": 0.24, "videoW": 0.9, "videoH": 0.52, "borderRadius": 12},
    ),
    _tpl(
        "gradient-depth",
        "Gradient Depth",
        "Modern",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#0f172a"},
                {"offset": 0.3, "color": "#1e1b4b"},
                {"offset": 0.7, "color": "#312e81"},
                {"offset": 1, "color": "#0f172a"},
            ],
            "angle": 180,
            "vignette": 0.45,
        },
        accents=[
            {"type": "soft-glow", "x": 0.3, "y": 0.12, "r": 0.4, "color": "rgba(99,102,241,0.18)"},
            {"type": "soft-glow", "x": 0.7, "y": 0.88, "r": 0.38, "color": "rgba(14,165,233,0.14)"},
            {"type": "frame", "inset": 0.03, "color": "rgba(129,140,248,0.15)", "stroke": 1},
        ],
    ),
    _tpl(
        "studio-soft",
        "Studio Soft",
        "Studio",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#2a2a30"},
                {"offset": 0.4, "color": "#16161a"},
                {"offset": 0.6, "color": "#16161a"},
                {"offset": 1, "color": "#1f1f23"},
            ],
            "angle": 180,
            "vignette": 0.3,
        },
        accents=[
            {"type": "soft-glow", "x": 0.5, "y": 0.08, "r": 0.5, "color": "rgba(255,255,255,0.07)"},
            {"type": "soft-glow", "x": 0.5, "y": 0.92, "r": 0.4, "color": "rgba(255,255,255,0.05)"},
            {"type": "bar", "x": 0.7, "y": 0.14, "w": 0.2, "h": 0.005, "color": "rgba(255,255,255,0.18)"},
            {"type": "bar", "x": 0.1, "y": 0.86, "w": 0.18, "h": 0.005, "color": "rgba(255,255,255,0.12)"},
        ],
        layout_16_9={"videoX": 0.02, "videoY": 0.348, "videoW": 0.96, "videoH": 0.304, "borderRadius": 10},
        layout_1_1={"videoX": 0.05, "videoY": 0.2469, "videoW": 0.9, "videoH": 0.5062, "borderRadius": 18},
    ),
    _tpl(
        "creative-depth",
        "Creative",
        "Creative",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#0b1020"},
                {"offset": 0.35, "color": "#1f2937"},
                {"offset": 0.65, "color": "#111827"},
                {"offset": 1, "color": "#0b1020"},
            ],
            "angle": 180,
            "vignette": 0.35,
        },
        accents=[
            {"type": "blob", "x": 0.88, "y": 0.1, "r": 0.22, "color": "rgba(52,211,153,0.16)"},
            {"type": "blob", "x": 0.12, "y": 0.9, "r": 0.24, "color": "rgba(59,130,246,0.16)"},
            {"type": "frame", "inset": 0.02, "color": "rgba(255,255,255,0.07)", "stroke": 1},
            {"type": "line", "x1": 0.15, "y1": 0.16, "x2": 0.4, "y2": 0.16, "color": "rgba(52,211,153,0.5)", "w": 2},
            {"type": "line", "x1": 0.6, "y1": 0.84, "x2": 0.85, "y2": 0.84, "color": "rgba(59,130,246,0.5)", "w": 2},
        ],
        layout_16_9={"videoX": 0.0, "videoY": 0.3418, "videoW": 1.0, "videoH": 0.3164, "borderRadius": 0},
        layout_1_1={"videoX": 0.06, "videoY": 0.24, "videoW": 0.88, "videoH": 0.52, "borderRadius": 14},
    ),
    _tpl(
        "cinematic-film",
        "Cinematic Film",
        "Film",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#1a1008"},
                {"offset": 0.4, "color": "#0a0806"},
                {"offset": 0.6, "color": "#0a0806"},
                {"offset": 1, "color": "#1a1008"},
            ],
            "angle": 180,
            "vignette": 0.55,
        },
        accents=[
            # classic film bars sit in letterbox zones (native 16:9 band ~0.316)
            {"type": "bar", "x": 0.0, "y": 0.0, "w": 1.0, "h": 0.3418, "color": "rgba(12,8,4,0.92)"},
            {"type": "bar", "x": 0.0, "y": 0.6582, "w": 1.0, "h": 0.3418, "color": "rgba(12,8,4,0.92)"},
            {"type": "line", "x1": 0.0, "y1": 0.3418, "x2": 1.0, "y2": 0.3418, "color": "rgba(212,175,55,0.35)", "w": 1},
            {"type": "line", "x1": 0.0, "y1": 0.6582, "x2": 1.0, "y2": 0.6582, "color": "rgba(212,175,55,0.35)", "w": 1},
            {"type": "bar", "x": 0.35, "y": 0.12, "w": 0.3, "h": 0.004, "color": "rgba(212,175,55,0.5)"},
            {"type": "bar", "x": 0.38, "y": 0.88, "w": 0.24, "h": 0.004, "color": "rgba(212,175,55,0.4)"},
        ],
        layout_16_9={"videoX": 0.0, "videoY": 0.3418, "videoW": 1.0, "videoH": 0.3164, "borderRadius": 0},
        layout_1_1={"videoX": 0.08, "videoY": 0.2638, "videoW": 0.84, "videoH": 0.4725, "borderRadius": 4},
    ),
    _tpl(
        "brand-border",
        "Brand Border",
        "Brand",
        background={
            "type": "gradient",
            "stops": [
                {"offset": 0, "color": "#0f172a"},
                {"offset": 0.5, "color": "#020617"},
                {"offset": 1, "color": "#0f172a"},
            ],
            "angle": 180,
            "vignette": 0.3,
        },
        accents=[
            {"type": "frame", "inset": 0.018, "color": "rgba(56,189,248,0.45)", "stroke": 3},
            {"type": "frame", "inset": 0.035, "color": "rgba(255,255,255,0.08)", "stroke": 1},
            {"type": "bar", "x": 0.25, "y": 0.1, "w": 0.5, "h": 0.01, "color": "rgba(56,189,248,0.6)"},
            {"type": "bar", "x": 0.3, "y": 0.89, "w": 0.4, "h": 0.008, "color": "rgba(56,189,248,0.4)"},
            {"type": "soft-glow", "x": 0.5, "y": 0.1, "r": 0.3, "color": "rgba(56,189,248,0.1)"},
            {"type": "soft-glow", "x": 0.5, "y": 0.9, "r": 0.28, "color": "rgba(56,189,248,0.08)"},
        ],
        layout_16_9={"videoX": 0.04, "videoY": 0.36, "videoW": 0.92, "videoH": 0.28, "borderRadius": 6},
        layout_1_1={"videoX": 0.08, "videoY": 0.26, "videoW": 0.84, "videoH": 0.48, "borderRadius": 10},
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
    """Content/intermediate resolution (pre-Remotion). Not final TikTok canvas."""
    return CONTENT_RESOLUTION.get(aspect_ratio, CONTENT_RESOLUTION["9:16"])


def output_resolution_for_job(content_aspect: str | None = None) -> tuple[int, int]:
    """Final Remotion/TikTok canvas — always 9:16."""
    return OUTPUT_RESOLUTION


def build_canvas_config(
    content_aspect: str,
    *,
    background_mode: str | None = None,
    background_template_id: str | None = None,
    background_image_url: str | None = None,
) -> dict[str, Any] | None:
    """Build canvas for Remotion/FE.

    content_aspect: framing of main video (16:9 / 1:1 / 9:16).
    Final canvas is always 9:16. None for full-bleed 9:16 content.
    """
    if content_aspect == "9:16":
        return None
    mode = background_mode or "template"
    if mode not in ("template", "upload"):
        mode = "template"
    w, h = OUTPUT_RESOLUTION
    cfg: dict[str, Any] = {
        "aspectRatio": "9:16",  # final canvas
        "contentAspect": content_aspect,  # main video framing
        "width": w,
        "height": h,
        "mode": mode,
        "backgroundImageUrl": background_image_url if mode == "upload" else None,
    }
    if mode == "template":
        tpl = get_template(background_template_id) or CANVAS_TEMPLATES[0]
        layout = tpl["layout"].get(content_aspect) or tpl["layout"]["16:9"]
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
        layout = (
            dict(_LAYOUT_16_9_ON_916)
            if content_aspect == "16:9"
            else dict(_LAYOUT_1_1_ON_916)
        )
        if content_aspect == "1:1":
            layout.update({"videoX": 0.04, "videoY": 0.24, "videoW": 0.92, "videoH": 0.52, "borderRadius": 12})
        cfg.update(
            {
                "templateId": None,
                "background": {
                    "type": "image" if background_image_url else "gradient",
                    "color": "#0a0a0a",
                    "imageUrl": background_image_url,
                    "stops": [
                        {"offset": 0, "color": "#1a1a1a"},
                        {"offset": 0.5, "color": "#0a0a0a"},
                        {"offset": 1, "color": "#1a1a1a"},
                    ],
                    "angle": 180,
                    "vignette": 0.35,
                },
                "accents": [
                    {"type": "frame", "inset": 0.02, "color": "rgba(255,255,255,0.08)", "stroke": 1},
                ],
                "layout": layout,
            }
        )
    return cfg
