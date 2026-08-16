"""HyperFrames style catalog — mirrors hyperframes-renderer/templates.

Hook/subtitle can opt into HF (fast fixed templates) instead of Remotion.
Polish lower-thirds remain optional post-pass.
"""
from __future__ import annotations

from typing import Any

HOOK_STYLES = (
    {"id": "hook_chromatic_gate_v2", "name": "Chromatic Gate", "design": "chromatic-gate", "accent": "#FF2E88"},
    {"id": "hook_orbit_stamp_v2", "name": "Orbit Stamp", "design": "orbit-stamp", "accent": "#8B5CF6"},
    {"id": "hook_pixel_ticker_v2", "name": "Pixel Ticker", "design": "pixel-ticker", "accent": "#F7FF58"},
    {"id": "hook_blueprint_v2", "name": "Blueprint Reveal", "design": "blueprint-reveal", "accent": "#52C7FF"},
)

SUBTITLE_STYLES = (
    {"id": "sub_speech_capsule_v2", "name": "Speech Capsule", "design": "speech-capsule", "accent": "#FFFFFF"},
    {"id": "sub_signal_rail_v2", "name": "Signal Rail", "design": "signal-rail", "accent": "#B7FF00"},
    {"id": "sub_vertical_caption_v2", "name": "Vertical Caption", "design": "vertical-caption", "accent": "#00D9FF"},
    {"id": "sub_notch_transcript_v2", "name": "Notch Transcript", "design": "notch-transcript", "accent": "#FFB000"},
)

HF_HOOK_TEMPLATES = tuple(style["id"] for style in HOOK_STYLES)
HF_SUBTITLE_TEMPLATES = tuple(style["id"] for style in SUBTITLE_STYLES)

# Old jobs stay renderable. Legacy IDs are hidden from the new catalogue.
HF_LEGACY_HOOK_TEMPLATES = (
    "hook_banner_v1",
    "hook_neon_v1",
    "hook_tape_v1",
    "hook_lower_v1",
)
HF_LEGACY_SUBTITLE_TEMPLATES = (
    "sub_caption_v1",
    "sub_neon_v1",
    "sub_box_v1",
    "sub_minimal_v1",
)

HF_POLISH_TEMPLATES = (
    "lower_third_v1",
    "lower_third",
)

ENGINE_NOTES = {
    "remotion": {
        "label": "Remotion",
        "speed": "slower",
        "quality": "full custom, preview≡bake",
        "note": "Render lebih lama, hasil bagus, style bebas.",
        "default": True,
    },
    "hyperframes": {
        "label": "HyperFrames",
        "speed": "faster",
        "quality": "HF-native fixed templates",
        "note": "Render cepat, style HF fixed dan berbeda dari Remotion.",
        "default": False,
    },
}


def catalogue() -> dict[str, Any]:
    return {
        "engines": ENGINE_NOTES,
        "hook": [{**style, "kind": "hook"} for style in HOOK_STYLES],
        "subtitle": [{**style, "kind": "subtitle"} for style in SUBTITLE_STYLES],
        "polish": [{"id": t, "kind": "polish"} for t in HF_POLISH_TEMPLATES],
        "default_hook": HF_HOOK_TEMPLATES[0],
        "default_subtitle": HF_SUBTITLE_TEMPLATES[0],
        "default_polish": HF_POLISH_TEMPLATES[0],
    }


def resolve_engine(cfg: dict | None, key: str = "engine") -> str:
    if not isinstance(cfg, dict):
        return "remotion"
    eng = str(cfg.get(key) or cfg.get("render_engine") or "remotion").lower().strip()
    if eng in ("hyperframes", "hf", "hyperframe"):
        return "hyperframes"
    if eng in ("ffmpeg", "drawtext"):
        return "ffmpeg"
    if eng in ("skia", "canvaskit", "skia-python", "skia_python"):
        return "skia"
    return "remotion"


def resolve_hf_template(cfg: dict | None, *, kind: str) -> str:
    if not isinstance(cfg, dict):
        cfg = {}
    raw = (
        cfg.get("hf_template")
        or cfg.get("hyperframes_template")
        or cfg.get("template")
        or ""
    )
    raw = str(raw).strip()
    allowed = {
        "hook": (*HF_HOOK_TEMPLATES, *HF_LEGACY_HOOK_TEMPLATES),
        "subtitle": (*HF_SUBTITLE_TEMPLATES, *HF_LEGACY_SUBTITLE_TEMPLATES),
        "polish": HF_POLISH_TEMPLATES,
    }.get(kind, ())
    if raw in allowed:
        return raw
    return allowed[0] if allowed else "lower_third_v1"


def hook_events_from_text(text: str, duration: float = 3.0) -> list[dict]:
    lab = " ".join(str(text or "").split())[:80]
    if not lab:
        return []
    end = max(0.8, float(duration or 3.0))
    return [{"label": lab, "sub": "HOOK", "start": 0.0, "end": end, "word": lab}]


def subtitle_events_from_words(
    words: list[dict] | None,
    *,
    max_events: int = 40,
    group: int = 3,
) -> list[dict]:
    """Group Whisper words into short caption bursts for HF templates."""
    if not words:
        return []
    cleaned: list[dict] = []
    for w in words:
        if not isinstance(w, dict):
            continue
        t = str(w.get("word") or w.get("text") or "").strip()
        if not t:
            continue
        try:
            start = float(w.get("start", 0) or 0)
            end = float(w.get("end", start + 0.4) or start + 0.4)
        except (TypeError, ValueError):
            continue
        if end <= start:
            end = start + 0.35
        cleaned.append({"word": t, "start": start, "end": end})
    if not cleaned:
        return []

    out: list[dict] = []
    i = 0
    while i < len(cleaned) and len(out) < max_events:
        chunk = cleaned[i : i + max(1, group)]
        label = " ".join(c["word"] for c in chunk)[:64]
        out.append(
            {
                "label": label,
                "sub": "",
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"],
                "word": label,
            }
        )
        i += max(1, group)
    return out
