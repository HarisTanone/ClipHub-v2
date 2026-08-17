"""HyperFrames style catalog — mirrors hyperframes-renderer/templates.

Hook/subtitle/polish can opt into HF (fast fixed templates) or Remotion.
Supports auto mode (AI contextual selection) or specific user selection.
"""
from __future__ import annotations

import random
from typing import Any

HOOK_STYLES = (
    # ── Page 1: Premier Hero Styles ──
    {"id": "hook_cyber_hud", "name": "Cyberpunk Tech HUD", "design": "cyber-hud", "accent": "#00F0FF", "description": "Tech HUD digital box dengan aksen neon cyan & bracket cyberpunk"},
    {"id": "hook_floating_badge", "name": "Top Floating Badge", "design": "floating-badge", "accent": "#10B981", "description": "Badge melayang di sudut atas dengan beacon live pulse & list neon"},
    {"id": "hook_kinetic_split", "name": "Kinetic Duotone Split", "design": "kinetic-split", "accent": "#FF6B00", "description": "Panel terbelah oranye-hitam dinamis dengan nomor indeks kinetik"},
    {"id": "hook_electric_surge", "name": "Electric Plasma Shockwave", "design": "electric-surge", "accent": "#818CF8", "description": "Shockwave plasma nebula elektrik dengan aksen petir & laser glow"},
    {"id": "hook_glass_minimal", "name": "Frosted Glassmorphism", "design": "glass-minimal", "accent": "#A78BFA", "description": "Kartu transparan frosted glass Apple-grade dengan efek blur & glow halus"},
    {"id": "hook_editorial_pill", "name": "Editorial Minimal Pill", "design": "editorial-pill", "accent": "#E2E8F0", "description": "Kapsul obsidian hitam matte dengan dot emas & tipografi editorial"},

    # ── Page 2: High-Converting & Cinematic ──
    {"id": "hook_breaking_news", "name": "Breaking News Live", "design": "breaking-news", "accent": "#EF4444", "description": "Banner merah bold dengan badge LIVE UPDATE berkedip"},
    {"id": "hook_luxury_noir", "name": "Luxury Obsidian & Gold", "design": "luxury-noir", "accent": "#D4AF37", "description": "Kartu hitam obsidian pekat dengan list emas sampanye mewah"},
    {"id": "hook_retro_synth", "name": "80s Retro Synthwave", "design": "retro-synth", "accent": "#F43F5E", "description": "Estetika synthwave retro 80-an dengan tabung neon ungu-pink"},
    {"id": "hook_chromatic_gate_v2", "name": "Chromatic Gate Y2K", "design": "chromatic-gate", "accent": "#FF2E88", "description": "Gerbang chromatic tajam dengan glitch RGB & sudut brutalist"},
    {"id": "hook_gradient_aura", "name": "Gradient Aura Mesh", "design": "gradient-aura", "accent": "#38BDF8", "description": "Cahaya aura mesh gradasi multi-warna halus di sekitar teks"},
    {"id": "hook_warning_hazard", "name": "Warning Industrial Hazard", "design": "warning-hazard", "accent": "#F59E0B", "description": "Pita hazard striping dengan badge critical notice"},

    # ── Page 3: Creative Technical & Sci-Fi ──
    {"id": "hook_orbit_stamp_v2", "name": "Orbit Stamp Seal", "design": "orbit-stamp", "accent": "#8B5CF6", "description": "Cap lingkaran orbit berputar futuristik tanda autentik"},
    {"id": "hook_pixel_ticker_v2", "name": "Arcade Pixel Ticker", "design": "pixel-ticker", "accent": "#F7FF58", "description": "Pixel ticker kuning retro dengan grid dot arcade"},
    {"id": "hook_blueprint_v2", "name": "Blueprint Arch Reveal", "design": "blueprint-reveal", "accent": "#52C7FF", "description": "Sketsa blueprint biru arsitektural terukur"},
    {"id": "hook_comic_pop", "name": "Comic Pop Burst", "design": "comic-pop", "accent": "#FACC15", "description": "Badge komik miring bold kuning dengan aksen halftone pop-art"},
    {"id": "hook_hologram_scan", "name": "Sci-Fi Hologram Scanner", "design": "hologram-scan", "accent": "#06B6D4", "description": "Data feed holographic sci-fi dengan scanline vertikal"},
    {"id": "hook_cinema_tape", "name": "Caution Stencil Tape", "design": "cinema-tape", "accent": "#EAB308", "description": "Pita peringatan diagonal kuning-hitam dengan font stencil industrial"},
)

SUBTITLE_STYLES = (
    {"id": "sub_speech_capsule_v2", "name": "Speech Capsule", "design": "speech-capsule", "accent": "#FFFFFF", "description": "Kapsul balon dialog putih bersih"},
    {"id": "sub_signal_rail_v2", "name": "Signal Rail", "design": "signal-rail", "accent": "#B7FF00", "description": "Jalur sinyal radio audio dengan bar indikator hijau"},
    {"id": "sub_vertical_caption_v2", "name": "Vertical Caption", "design": "vertical-caption", "accent": "#00D9FF", "description": "Keterangan vertikal modern di sisi kiri"},
    {"id": "sub_notch_transcript_v2", "name": "Notch Transcript", "design": "notch-transcript", "accent": "#FFB000", "description": "Notch perekam suara dengan kursor aktif"},
)

HF_HOOK_TEMPLATES = tuple(style["id"] for style in HOOK_STYLES)
HF_SUBTITLE_TEMPLATES = tuple(style["id"] for style in SUBTITLE_STYLES)

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
    "hook_cyber_hud",
    "hook_glass_minimal",
    "hook_editorial_pill",
    "hook_floating_badge",
    "hook_luxury_noir",
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


def resolve_hf_template(cfg: dict | None, *, kind: str, clip_index: int = 0) -> str:
    if not isinstance(cfg, dict):
        cfg = {}
    
    # Check mode
    mode = str(cfg.get("mode") or "").strip().lower()
    raw = str(
        cfg.get("hf_template")
        or cfg.get("hyperframes_template")
        or cfg.get("default_template")
        or cfg.get("template")
        or ""
    ).strip()

    allowed = {
        "hook": (*HF_HOOK_TEMPLATES, *HF_LEGACY_HOOK_TEMPLATES),
        "subtitle": (*HF_SUBTITLE_TEMPLATES, *HF_LEGACY_SUBTITLE_TEMPLATES),
        "polish": (*HF_POLISH_TEMPLATES, *HF_HOOK_TEMPLATES),
    }.get(kind, ())

    if mode == "auto" or raw in ("auto", "random", "ai"):
        # Select from top 12 primary templates based on clip_index
        candidates = HF_HOOK_TEMPLATES if kind in ("hook", "polish") else HF_SUBTITLE_TEMPLATES
        return candidates[clip_index % len(candidates)]

    if raw in allowed:
        return raw
    return allowed[0] if allowed else "hook_cyber_hud"


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
