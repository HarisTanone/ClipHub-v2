"""SkiaHookRenderer — High-definition GPU/Canvas-style hook overlay rendering.

Renders rich graphical hook overlays that match the frontend Skia Canvas and FFmpeg previews 1:1:
- Neon Cyberpunk: Dual cyan & magenta glow with futuristic glass framing and corner brackets
- Impact Hazard / Impact Badge: High-voltage amber warning banner with bold black Anton typography
- Frosted Pill: Glassmorphic rounded capsule with subtle border and backdrop blur
- Aurora Gradient: Vivid emerald-to-violet Northern Lights gradient fill with ambient aura
- 3D Chrome: Reflective metallic silver and gold bevel luster with heavy drop shadow
- Ruby Flame: Fiery crimson-to-amber heat wave with intense outer aura
- Gold Prestige: Luxury 24K specular gold with letterbox framing
- Clean Editorial / Minimal: Minimalist Swiss headline with crisp modern contrast
- Glitch RGB: Chromatic RGB split channel rasterizer burst (red left, cyan right, white center)
- Typewriter Matrix: Monospace phosphor green CRT terminal glow
- Zoom Punch / Fade Scale / Shake Neon / Danger Bold / Cinematic Reveal: High-impact video hooks
"""
import asyncio
import logging
import math
import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)


# ─── Comprehensive Hook Presets Specifications ────────────────────────────────

SKIA_HOOK_PRESETS: Dict[str, Dict[str, Any]] = {
    "skia_impact_badge": {
        "name": "Impact Hazard",
        "font_family": "Anton",
        "font_size": 62,
        "font_weight": "700",
        "text_color": "#000000",
        "gradient_enabled": True,
        "bg_gradient_from": "#FACC15",
        "bg_gradient_to": "#EAB308",
        "bg_radius": 14,
        "bg_padding_x": 36,
        "bg_padding_y": 20,
        "bg_shadow_color": "#713F12",
        "bg_shadow_offset_y": 8,
        "tilt_angle": -1.5,
        "position_y": 38,
        "uppercase": True,
        "duration": 3.0,
    },
    "skia_neon_cyberpunk": {
        "name": "Neon Cyberpunk",
        "font_family": "Montserrat",
        "font_size": 56,
        "font_weight": "900",
        "text_color": "#00F0FF",
        "gradient_enabled": True,
        "gradient_from": "#00F0FF",
        "gradient_to": "#FF007F",
        "bg_color": "#0A0F1E",
        "bg_opacity": 0.85,
        "bg_radius": 16,
        "bg_border_color": "#00F0FF",
        "bg_border_width": 3,
        "glow_enabled": True,
        "glow_color": "#00F0FF",
        "glow_size": 24,
        "bg_padding_x": 36,
        "bg_padding_y": 20,
        "corner_accents": True,
        "position_y": 38,
        "uppercase": True,
        "duration": 3.0,
    },
    "skia_frosted_pill": {
        "name": "Frosted Pill",
        "font_family": "Plus Jakarta Sans",
        "font_size": 50,
        "font_weight": "800",
        "text_color": "#FFFFFF",
        "bg_color": "#FFFFFF",
        "bg_opacity": 0.20,
        "bg_radius": 999,  # capsule
        "bg_border_color": "#FFFFFF",
        "bg_border_width": 2,
        "bg_shadow_color": "#000000",
        "bg_shadow_blur": 16,
        "bg_padding_x": 42,
        "bg_padding_y": 20,
        "position_y": 40,
        "uppercase": False,
        "duration": 3.0,
    },
    "skia_aurora_gradient": {
        "name": "Aurora Gradient",
        "font_family": "Outfit",
        "font_size": 56,
        "font_weight": "800",
        "text_color": "#10B981",
        "gradient_enabled": True,
        "gradient_from": "#10B981",
        "gradient_to": "#8B5CF6",
        "bg_color": "#050F0A",
        "bg_opacity": 0.82,
        "bg_radius": 16,
        "glow_enabled": True,
        "glow_color": "#8B5CF6",
        "glow_size": 20,
        "bg_padding_x": 36,
        "bg_padding_y": 20,
        "position_y": 38,
        "uppercase": True,
        "duration": 3.0,
    },
    "skia_3d_chrome": {
        "name": "3D Chrome",
        "font_family": "Bebas Neue",
        "font_size": 58,
        "font_weight": "700",
        "text_color": "#F8FAFC",
        "gradient_enabled": True,
        "gradient_from": "#F8FAFC",
        "gradient_to": "#FBBF24",
        "stroke_enabled": True,
        "stroke_width": 3,
        "stroke_color": "#000000",
        "shadow_enabled": True,
        "shadow_color": "#000000",
        "shadow_blur": 12,
        "bg_color": "#0F172A",
        "bg_opacity": 0.75,
        "bg_radius": 16,
        "bg_padding_x": 36,
        "bg_padding_y": 20,
        "position_y": 40,
        "uppercase": True,
        "duration": 3.0,
    },
    "skia_ruby_flame": {
        "name": "Ruby Flame",
        "font_family": "Bungee",
        "font_size": 56,
        "font_weight": "400",
        "text_color": "#FF3366",
        "gradient_enabled": True,
        "gradient_from": "#FF3366",
        "gradient_to": "#FF9900",
        "glow_enabled": True,
        "glow_color": "#FF2E2E",
        "glow_size": 24,
        "bg_color": "#18050A",
        "bg_opacity": 0.80,
        "bg_radius": 16,
        "bg_padding_x": 36,
        "bg_padding_y": 20,
        "position_y": 38,
        "uppercase": True,
        "duration": 3.0,
    },
    "skia_gold_prestige": {
        "name": "Gold Prestige",
        "font_family": "Playfair Display",
        "font_size": 58,
        "font_weight": "700",
        "text_color": "#FEF08A",
        "gradient_enabled": True,
        "gradient_from": "#FEF08A",
        "gradient_to": "#CA8A04",
        "bg_color": "#0A0A0A",
        "bg_opacity": 0.88,
        "bg_radius": 14,
        "bg_border_color": "#CA8A04",
        "bg_border_width": 2,
        "bg_padding_x": 38,
        "bg_padding_y": 22,
        "position_y": 42,
        "uppercase": False,
        "duration": 3.5,
    },
    "skia_minimal_editorial": {
        "name": "Clean Editorial",
        "font_family": "Inter",
        "font_size": 48,
        "font_weight": "800",
        "text_color": "#FFFFFF",
        "bg_color": "#1E293B",
        "bg_opacity": 0.75,
        "bg_radius": 16,
        "bg_border_color": "#334155",
        "bg_border_width": 2,
        "bg_padding_x": 36,
        "bg_padding_y": 20,
        "position_y": 42,
        "uppercase": False,
        "duration": 3.0,
    },
    "skia_zoom_punch": {
        "name": "Zoom Punch",
        "font_family": "Anton",
        "font_size": 58,
        "font_weight": "700",
        "text_color": "#FFFFFF",
        "stroke_enabled": True,
        "stroke_width": 6,
        "stroke_color": "#000000",
        "shadow_enabled": True,
        "shadow_color": "#000000",
        "shadow_blur": 10,
        "bg_color": "#000000",
        "bg_opacity": 0.65,
        "bg_radius": 16,
        "bg_padding_x": 36,
        "bg_padding_y": 20,
        "position_y": 40,
        "uppercase": True,
        "duration": 3.0,
    },
    "skia_glitch_rgb": {
        "name": "Glitch RGB",
        "font_family": "Anton",
        "font_size": 58,
        "font_weight": "700",
        "text_color": "#FFFFFF",
        "is_glitch_rgb": True,
        "stroke_enabled": True,
        "stroke_width": 4,
        "stroke_color": "#000000",
        "bg_color": "#050505",
        "bg_opacity": 0.80,
        "bg_radius": 14,
        "bg_padding_x": 36,
        "bg_padding_y": 20,
        "position_y": 40,
        "uppercase": True,
        "duration": 3.0,
    },
    "skia_typewriter": {
        "name": "Typewriter Matrix",
        "font_family": "Space Grotesk",
        "font_size": 44,
        "font_weight": "700",
        "text_color": "#22C55E",
        "glow_enabled": True,
        "glow_color": "#22C55E",
        "glow_size": 16,
        "bg_color": "#020A05",
        "bg_opacity": 0.85,
        "bg_radius": 14,
        "bg_border_color": "#22C55E",
        "bg_border_width": 2,
        "bg_padding_x": 34,
        "bg_padding_y": 18,
        "position_y": 44,
        "uppercase": False,
        "duration": 3.5,
    },
    "skia_fade_scale": {
        "name": "Fade Scale",
        "font_family": "Poppins",
        "font_size": 50,
        "font_weight": "700",
        "text_color": "#FFFFFF",
        "stroke_enabled": True,
        "stroke_width": 3,
        "stroke_color": "#000000",
        "bg_color": "#0F172A",
        "bg_opacity": 0.60,
        "bg_radius": 16,
        "bg_padding_x": 36,
        "bg_padding_y": 20,
        "position_y": 42,
        "uppercase": False,
        "duration": 3.5,
    },
    # ─── Creative High-Converting Hook Presets ──────────────────────────────
    "paper_clip_scrap": {
        "name": "Paper Clip Scrap",
        "font_family": "Montserrat",
        "font_size": 48,
        "font_weight": "900",
        "text_color": "#1C1917",
        "bg_color": "#FEF08A",
        "box_color": "#FEF08A",
        "bg_opacity": 1.0,
        "bg_radius": 12,
        "bg_padding_x": 38,
        "bg_padding_y": 24,
        "position_y": 42,
        "uppercase": True,
        "duration": 3.0,
    },
    "trending_radar": {
        "name": "Trending Radar",
        "font_family": "Montserrat",
        "font_size": 48,
        "font_weight": "900",
        "text_color": "#FFFFFF",
        "bg_color": "#090514",
        "box_color": "#090514",
        "bg_opacity": 0.92,
        "bg_radius": 14,
        "badge_enabled": True,
        "badge_text": "TRENDING NOW",
        "badge_bg": "#D946EF",
        "badge_color": "#FFFFFF",
        "position_y": 40,
        "uppercase": True,
        "duration": 3.0,
    },
    "news_breaking_live": {
        "name": "Breaking News Live",
        "font_family": "Montserrat",
        "font_size": 48,
        "font_weight": "900",
        "text_color": "#FFFFFF",
        "bg_color": "#0F172A",
        "box_color": "#0F172A",
        "bg_opacity": 0.95,
        "bg_radius": 12,
        "badge_enabled": True,
        "badge_text": "BREAKING",
        "badge_bg": "#DC2626",
        "badge_color": "#FFFFFF",
        "position_y": 44,
        "uppercase": True,
        "duration": 3.0,
    },
    "news_viralin_badge": {
        "name": "#VIRALIN Badge",
        "font_family": "Montserrat",
        "font_size": 48,
        "font_weight": "900",
        "text_color": "#09090B",
        "bg_color": "#EAB308",
        "bg_opacity": 1.0,
        "bg_radius": 14,
        "bg_padding_x": 36,
        "bg_padding_y": 20,
        "badge_enabled": True,
        "badge_text": "#VIRALIN",
        "badge_bg": "#1D4ED8",
        "badge_color": "#FFFFFF",
        "position_y": 44,
        "uppercase": True,
        "duration": 3.0,
    },
    "news_portal_pantau": {
        "name": "News Portal Notch",
        "font_family": "Inter",
        "font_size": 46,
        "font_weight": "900",
        "text_color": "#09090B",
        "bg_color": "#FFFFFF",
        "bg_opacity": 1.0,
        "bg_radius": 14,
        "bg_padding_x": 36,
        "bg_padding_y": 22,
        "badge_enabled": True,
        "badge_text": "NEWS",
        "badge_bg": "#DC2626",
        "badge_color": "#FFFFFF",
        "position_y": 46,
        "uppercase": True,
        "duration": 3.0,
    },
    "news_offset_box": {
        "name": "Detik Red Box",
        "font_family": "Montserrat",
        "font_size": 48,
        "font_weight": "900",
        "text_color": "#FFFFFF",
        "bg_color": "#DC2626",
        "bg_opacity": 1.0,
        "bg_radius": 8,
        "bg_padding_x": 36,
        "bg_padding_y": 20,
        "bg_shadow_color": "#000000",
        "bg_shadow_offset_y": 8,
        "position_y": 44,
        "uppercase": True,
        "duration": 3.0,
    },
    "brutalist_bracket": {
        "name": "Brutalist Bracket",
        "font_family": "Montserrat",
        "font_size": 48,
        "font_weight": "900",
        "text_color": "#09090B",
        "bg_color": "#FFFFFF",
        "bg_opacity": 1.0,
        "bg_radius": 6,
        "corner_accents": True,
        "bg_padding_x": 40,
        "bg_padding_y": 22,
        "position_y": 44,
        "uppercase": True,
        "duration": 3.0,
    },
    "quote_strip_tape": {
        "name": "Quote Tape Strips",
        "font_family": "Montserrat",
        "font_size": 44,
        "font_weight": "900",
        "text_color": "#09090B",
        "is_tape_strips": True,
        "box_color": "#FFFFFF",
        "badge_enabled": True,
        "badge_text": "“ QUOTE",
        "badge_bg": "#0D9488",
        "badge_color": "#FFFFFF",
        "position_y": 45,
        "uppercase": True,
        "duration": 3.0,
    },
    "podcast_lower_third": {
        "name": "On-Air Lower",
        "font_family": "Barlow Condensed",
        "font_size": 46,
        "font_weight": "900",
        "text_color": "#F8FAFC",
        "bg_color": "#06111F",
        "bg_opacity": 0.85,
        "bg_radius": 14,
        "badge_enabled": True,
        "badge_text": "ON AIR",
        "badge_bg": "#16F2B3",
        "badge_color": "#000000",
        "position_y": 78,
        "uppercase": True,
        "duration": 3.5,
    },
    "quote_card": {
        "name": "Quote Card",
        "font_family": "Playfair Display",
        "font_size": 46,
        "font_weight": "800",
        "text_color": "#171717",
        "bg_color": "#F5EFE1",
        "bg_opacity": 0.98,
        "bg_radius": 16,
        "bg_padding_x": 38,
        "bg_padding_y": 24,
        "badge_enabled": True,
        "badge_text": "QUOTE",
        "badge_bg": "#FF4D2D",
        "badge_color": "#FFFFFF",
        "position_y": 45,
        "uppercase": False,
        "duration": 3.5,
    },
    "waveform_pulse": {
        "name": "Waveform Pulse",
        "font_family": "Montserrat",
        "font_size": 48,
        "font_weight": "900",
        "text_color": "#FFFFFF",
        "gradient_enabled": True,
        "gradient_from": "#FFFFFF",
        "gradient_to": "#14F1D9",
        "glow_enabled": True,
        "glow_color": "#14F1D9",
        "glow_size": 24,
        "bg_color": "#020617",
        "bg_opacity": 0.85,
        "bg_radius": 16,
        "badge_enabled": True,
        "badge_text": "LIVE AUDIO",
        "badge_bg": "#14F1D9",
        "badge_color": "#000000",
        "position_y": 44,
        "uppercase": True,
        "duration": 3.0,
    },
    "breaking_tape": {
        "name": "Breaking Tape",
        "font_family": "Archivo Black",
        "font_size": 50,
        "font_weight": "900",
        "text_color": "#111111",
        "bg_color": "#FFDD2D",
        "bg_opacity": 1.0,
        "bg_radius": 10,
        "badge_enabled": True,
        "badge_text": "HOT TAKE",
        "badge_bg": "#FF4D2D",
        "badge_color": "#FFFFFF",
        "position_y": 44,
        "uppercase": True,
        "duration": 3.0,
    },
    "mic_drop": {
        "name": "Mic Drop",
        "font_family": "Anton",
        "font_size": 56,
        "font_weight": "900",
        "text_color": "#FFFFFF",
        "gradient_enabled": True,
        "gradient_from": "#FFFFFF",
        "gradient_to": "#FF4D7D",
        "glow_enabled": True,
        "glow_color": "#FF4D7D",
        "glow_size": 24,
        "bg_color": "#16050C",
        "bg_opacity": 0.88,
        "bg_radius": 16,
        "badge_enabled": True,
        "badge_text": "MIC DROP",
        "badge_bg": "#FF4D7D",
        "badge_color": "#FFFFFF",
        "position_y": 44,
        "uppercase": True,
        "duration": 3.0,
    },
    "split_panel": {
        "name": "Split Panel",
        "font_family": "Inter",
        "font_size": 48,
        "font_weight": "900",
        "text_color": "#F8FAFC",
        "bg_color": "#0F172A",
        "bg_opacity": 0.92,
        "bg_border_color": "#38BDF8",
        "bg_border_width": 3,
        "bg_radius": 14,
        "position_y": 46,
        "uppercase": False,
        "duration": 3.0,
    },
    "kinetic_stack": {
        "name": "Kinetic Stack",
        "font_family": "Archivo Black",
        "font_size": 52,
        "font_weight": "900",
        "text_color": "#111827",
        "bg_color": "#F97316",
        "bg_opacity": 1.0,
        "bg_radius": 12,
        "position_y": 45,
        "uppercase": True,
        "duration": 3.0,
    },
    "glass_flash": {
        "name": "Glass Flash",
        "font_family": "Montserrat",
        "font_size": 48,
        "font_weight": "800",
        "text_color": "#F8FAFC",
        "glow_enabled": True,
        "glow_color": "#C084FC",
        "glow_size": 20,
        "bg_color": "#1E1528",
        "bg_opacity": 0.85,
        "bg_border_color": "#C084FC",
        "bg_border_width": 2,
        "bg_radius": 16,
        "badge_enabled": True,
        "badge_text": "FOCUS",
        "badge_bg": "#C084FC",
        "badge_color": "#000000",
        "position_y": 44,
        "uppercase": True,
        "duration": 3.0,
    },
    "marker_swipe": {
        "name": "Marker Swipe",
        "font_family": "Bebas Neue",
        "font_size": 56,
        "font_weight": "900",
        "text_color": "#111827",
        "bg_color": "#FDE047",
        "bg_opacity": 0.96,
        "bg_radius": 8,
        "position_y": 44,
        "uppercase": True,
        "duration": 3.0,
    },
    "signal_scan": {
        "name": "Signal Scan",
        "font_family": "Montserrat",
        "font_size": 46,
        "font_weight": "900",
        "text_color": "#E0F2FE",
        "glow_enabled": True,
        "glow_color": "#22D3EE",
        "glow_size": 20,
        "bg_color": "#04141E",
        "bg_opacity": 0.90,
        "bg_border_color": "#22D3EE",
        "bg_border_width": 2,
        "bg_radius": 14,
        "badge_enabled": True,
        "badge_text": "SIGNAL",
        "badge_bg": "#22D3EE",
        "badge_color": "#000000",
        "position_y": 44,
        "uppercase": True,
        "duration": 3.0,
    },
    "comment_reply": {
        "name": "Reply Comment",
        "font_family": "Inter",
        "font_size": 42,
        "font_weight": "800",
        "text_color": "#18181B",
        "bg_color": "#FFFFFF",
        "bg_opacity": 0.98,
        "bg_radius": 18,
        "badge_enabled": True,
        "badge_text": "@viewer",
        "badge_bg": "#E2E8F0",
        "badge_color": "#334155",
        "position_y": 26,
        "uppercase": False,
        "duration": 3.5,
    },
    "search_prompt": {
        "name": "Search Prompt",
        "font_family": "Inter",
        "font_size": 42,
        "font_weight": "800",
        "text_color": "#F8FAFC",
        "bg_color": "#0F172A",
        "bg_opacity": 0.94,
        "bg_border_color": "#38BDF8",
        "bg_border_width": 2,
        "bg_radius": 999,
        "position_y": 24,
        "uppercase": False,
        "duration": 3.5,
    },
    "countdown_list": {
        "name": "Countdown List",
        "font_family": "Archivo Black",
        "font_size": 48,
        "font_weight": "900",
        "text_color": "#111827",
        "bg_color": "#FACC15",
        "bg_opacity": 1.0,
        "bg_radius": 14,
        "badge_enabled": True,
        "badge_text": "03",
        "badge_bg": "#111827",
        "badge_color": "#FACC15",
        "position_y": 45,
        "uppercase": True,
        "duration": 3.0,
    },
    "pov_stamp": {
        "name": "POV Stamp",
        "font_family": "Montserrat",
        "font_size": 48,
        "font_weight": "900",
        "text_color": "#FFFFFF",
        "bg_color": "#12070C",
        "bg_opacity": 0.85,
        "bg_border_color": "#FB7185",
        "bg_border_width": 5,
        "bg_radius": 18,
        "badge_enabled": True,
        "badge_text": "POV",
        "badge_bg": "#FB7185",
        "badge_color": "#FFFFFF",
        "position_y": 44,
        "uppercase": False,
        "italic": True,
        "duration": 3.0,
    },
    # FFmpeg Hook Mappings
    "zoom_punch": {
        "name": "Zoom Punch",
        "font_family": "Anton",
        "font_size": 58,
        "font_weight": "700",
        "text_color": "#FFFFFF",
        "stroke_enabled": True,
        "stroke_width": 5,
        "stroke_color": "#000000",
        "bg_color": "#000000",
        "bg_opacity": 0.60,
        "bg_radius": 14,
        "bg_padding_x": 34,
        "bg_padding_y": 18,
        "position_y": 40,
        "uppercase": True,
        "duration": 3.0,
    },
    "glitch_rgb": {
        "name": "Glitch RGB",
        "font_family": "Anton",
        "font_size": 58,
        "font_weight": "700",
        "text_color": "#FFFFFF",
        "is_glitch_rgb": True,
        "bg_color": "#000000",
        "bg_opacity": 0.70,
        "bg_radius": 14,
        "bg_padding_x": 34,
        "bg_padding_y": 18,
        "position_y": 40,
        "uppercase": True,
        "duration": 3.0,
    },
    "shake_neon": {
        "name": "Shake Neon",
        "font_family": "Bungee",
        "font_size": 54,
        "font_weight": "400",
        "text_color": "#00FFCC",
        "glow_enabled": True,
        "glow_color": "#00FFCC",
        "glow_size": 24,
        "bg_color": "#051515",
        "bg_opacity": 0.75,
        "bg_radius": 14,
        "bg_border_color": "#00FFCC",
        "bg_border_width": 2,
        "bg_padding_x": 34,
        "bg_padding_y": 18,
        "position_y": 40,
        "uppercase": True,
        "duration": 3.0,
    },
    "cinematic_reveal": {
        "name": "Cinematic Reveal",
        "font_family": "Playfair Display",
        "font_size": 60,
        "font_weight": "700",
        "text_color": "#FFD700",
        "bg_color": "#111111",
        "bg_opacity": 0.85,
        "bg_radius": 10,
        "bg_border_color": "#FFD700",
        "bg_border_width": 2,
        "bg_padding_x": 38,
        "bg_padding_y": 20,
        "position_y": 42,
        "uppercase": False,
        "duration": 3.5,
    },
    "danger_bold": {
        "name": "Danger Bold",
        "font_family": "Anton",
        "font_size": 68,
        "font_weight": "700",
        "text_color": "#FF2D2D",
        "stroke_enabled": True,
        "stroke_width": 6,
        "stroke_color": "#000000",
        "glow_enabled": True,
        "glow_color": "#FF2D2D",
        "glow_size": 20,
        "bg_color": "#200505",
        "bg_opacity": 0.80,
        "bg_radius": 14,
        "bg_border_color": "#FF2D2D",
        "bg_border_width": 3,
        "bg_padding_x": 36,
        "bg_padding_y": 20,
        "position_y": 38,
        "uppercase": True,
        "duration": 3.0,
    },
    "typewriter": {
        "name": "Typewriter",
        "font_family": "Space Grotesk",
        "font_size": 44,
        "font_weight": "700",
        "text_color": "#00FF88",
        "glow_enabled": True,
        "glow_color": "#00FF88",
        "glow_size": 16,
        "bg_color": "#04140C",
        "bg_opacity": 0.85,
        "bg_radius": 12,
        "bg_border_color": "#00FF88",
        "bg_border_width": 2,
        "bg_padding_x": 34,
        "bg_padding_y": 18,
        "position_y": 45,
        "uppercase": False,
        "duration": 3.5,
    },
    "fade_scale": {
        "name": "Fade Scale",
        "font_family": "Poppins",
        "font_size": 50,
        "font_weight": "700",
        "text_color": "#FFFFFF",
        "stroke_enabled": True,
        "stroke_width": 3,
        "stroke_color": "#000000",
        "bg_color": "#000000",
        "bg_opacity": 0.60,
        "bg_radius": 14,
        "bg_padding_x": 34,
        "bg_padding_y": 18,
        "position_y": 42,
        "uppercase": False,
        "duration": 3.5,
    },
    "slide_punch_framer": {
        "name": "Slide Punch",
        "font_family": "Poppins",
        "font_size": 52,
        "font_weight": "700",
        "text_color": "#FFFFFF",
        "stroke_enabled": True,
        "stroke_width": 5,
        "stroke_color": "#000000",
        "bg_color": "#000000",
        "bg_opacity": 0.65,
        "bg_radius": 14,
        "bg_padding_x": 34,
        "bg_padding_y": 18,
        "position_y": 38,
        "uppercase": True,
        "duration": 3.0,
    },
    "bold_yellow": {
        "name": "Bold Yellow",
        "font_family": "Anton",
        "font_size": 64,
        "font_weight": "700",
        "text_color": "#FFD700",
        "stroke_enabled": True,
        "stroke_width": 5,
        "stroke_color": "#000000",
        "bg_color": "#000000",
        "bg_opacity": 0.65,
        "bg_radius": 14,
        "bg_padding_x": 34,
        "bg_padding_y": 18,
        "position_y": 40,
        "uppercase": True,
        "duration": 3.0,
    },
    "electric_blue": {
        "name": "Electric Blue",
        "font_family": "Bungee",
        "font_size": 54,
        "font_weight": "400",
        "text_color": "#00BFFF",
        "glow_enabled": True,
        "glow_color": "#00BFFF",
        "glow_size": 22,
        "bg_color": "#021220",
        "bg_opacity": 0.75,
        "bg_radius": 14,
        "bg_border_color": "#00BFFF",
        "bg_border_width": 2,
        "bg_padding_x": 34,
        "bg_padding_y": 18,
        "position_y": 40,
        "uppercase": True,
        "duration": 3.0,
    },
    "fire_red": {
        "name": "Fire Red",
        "font_family": "Anton",
        "font_size": 66,
        "font_weight": "700",
        "text_color": "#FF4444",
        "stroke_enabled": True,
        "stroke_width": 5,
        "stroke_color": "#220000",
        "bg_color": "#200404",
        "bg_opacity": 0.80,
        "bg_radius": 14,
        "bg_border_color": "#FF4444",
        "bg_border_width": 2,
        "bg_padding_x": 34,
        "bg_padding_y": 18,
        "position_y": 38,
        "uppercase": True,
        "duration": 3.0,
    },
    "minimal_white": {
        "name": "Minimal White",
        "font_family": "Inter",
        "font_size": 44,
        "font_weight": "700",
        "text_color": "#FFFFFF",
        "stroke_enabled": True,
        "stroke_width": 2,
        "stroke_color": "#000000",
        "bg_color": "#000000",
        "bg_opacity": 0.40,
        "bg_radius": 12,
        "bg_padding_x": 30,
        "bg_padding_y": 16,
        "position_y": 50,
        "uppercase": False,
        "duration": 3.0,
    },
}


class SkiaHookRenderer:
    """Renderer for high-end Skia-style Hook overlays using high-DPI Pillow canvas & FFmpeg."""

    def __init__(self, font_dir: str = "assets/fonts", width: int = 1080, height: int = 1920):
        self._font_dir = font_dir
        self._width = width
        self._height = height

    def _hex_to_rgb(self, hex_code: str) -> Tuple[int, int, int]:
        """Convert #RGB or #RRGGBB to (r, g, b)."""
        if not hex_code:
            return (255, 255, 255)
        hex_code = hex_code.strip().lstrip("#")
        if len(hex_code) == 3:
            hex_code = "".join(2 * c for c in hex_code)
        if len(hex_code) >= 6:
            return (
                int(hex_code[0:2], 16),
                int(hex_code[2:4], 16),
                int(hex_code[4:6], 16),
            )
        return (255, 255, 255)

    def _hex_to_rgba(self, hex_code: str, opacity: float = 1.0) -> Tuple[int, int, int, int]:
        r, g, b = self._hex_to_rgb(hex_code)
        a = max(0, min(255, int(opacity * 255)))
        return (r, g, b, a)

    def _resolve_font(self, font_family: str, font_weight: str = "Bold", size: int = 50) -> ImageFont.FreeTypeFont:
        """Find best matching TrueType font file in font directories."""
        family_clean = font_family.replace(" ", "").replace("-", "").lower()
        search_dirs = [
            self._font_dir,
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts")),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "assets", "fonts")),
            os.path.abspath(os.path.join(os.getcwd(), "assets", "fonts")),
        ]

        # Explicit map of popular families to exact font filenames
        FONT_MAP = {
            "montserrat": ["Montserrat-Variable.ttf", "Montserrat-Bold.ttf", "Montserrat-Regular.ttf"],
            "inter": ["Inter-Variable.ttf", "Inter-Bold.ttf", "Inter-Regular.ttf"],
            "playfairdisplay": ["PlayfairDisplay-Variable.ttf", "PlayfairDisplay-Bold.ttf"],
            "playfair": ["PlayfairDisplay-Variable.ttf", "PlayfairDisplay-Bold.ttf"],
            "barlowcondensed": ["BarlowCondensed-Bold.ttf", "BarlowCondensed-Regular.ttf"],
            "barlow": ["BarlowCondensed-Bold.ttf", "BarlowCondensed-Regular.ttf"],
            "poppins": ["Poppins-Bold.ttf", "Poppins-Regular.ttf"],
            "archivoblack": ["ArchivoBlack-Regular.ttf"],
            "archivo": ["ArchivoBlack-Regular.ttf"],
            "bebasneue": ["BebasNeue-Regular.ttf"],
            "bebas": ["BebasNeue-Regular.ttf"],
            "bungee": ["Bungee-Regular.ttf"],
            "roboto": ["Roboto-Bold.ttf", "Roboto-Regular.ttf"],
            "robotocondensed": ["RobotoCondensed-Bold.ttf"],
            "oswald": ["Oswald-Bold.ttf"],
            "anton": ["Anton-Regular.ttf"],
            "titilliumweb": ["TitilliumWeb-Bold.ttf"],
            "titillium": ["TitilliumWeb-Bold.ttf"],
            "lato": ["Lato-Bold.ttf"],
            "raleway": ["Raleway-Variable.ttf"],
            "nunito": ["Nunito-Variable.ttf"],
            "notosans": ["NotoSans-Variable.ttf"],
            "righteous": ["Righteous-Regular.ttf"],
            "blackopsone": ["BlackOpsOne-Regular.ttf"],
            "merriweather": ["Merriweather-Bold.ttf"],
            "lora": ["Lora-Variable.ttf"],
        }

        def _post_process_font(font_obj):
            is_heavy = str(font_weight).lower() in ("bold", "black", "extrabold", "heavy", "900", "800", "700")
            if hasattr(font_obj, "set_variation_by_name"):
                variants = ["Black", "ExtraBold", "Bold", "SemiBold"] if is_heavy else ["Regular", "Medium"]
                for v_name in variants:
                    try:
                        font_obj.set_variation_by_name(v_name)
                        break
                    except Exception:
                        pass
            return font_obj

        # 1. Check exact font map first
        if family_clean in FONT_MAP:
            for fdir in search_dirs:
                if not fdir or not os.path.exists(fdir):
                    continue
                for fname in FONT_MAP[family_clean]:
                    p = os.path.join(fdir, fname)
                    if os.path.exists(p):
                        try:
                            f = ImageFont.truetype(p, size=size)
                            return _post_process_font(f)
                        except Exception:
                            pass

        # 2. Search all font directories matching the requested family
        for fdir in search_dirs:
            if not fdir or not os.path.exists(fdir):
                continue
            try:
                for file_name in os.listdir(fdir):
                    if not file_name.lower().endswith((".ttf", ".otf")):
                        continue
                    clean_name = file_name.replace(" ", "").replace("-", "").lower()
                    if family_clean in clean_name:
                        full_path = os.path.join(fdir, file_name)
                        try:
                            f = ImageFont.truetype(full_path, size=size)
                            return _post_process_font(f)
                        except Exception:
                            pass
            except Exception:
                pass

        # 3. Clean universal fallback fonts (Inter or Poppins or Roboto)
        fallbacks = [
            "Montserrat-Variable.ttf",
            "Inter-Variable.ttf",
            "Poppins-Bold.ttf",
            "Roboto-Bold.ttf",
            "Anton-Regular.ttf",
        ]
        for fdir in search_dirs:
            if not fdir or not os.path.exists(fdir):
                continue
            for fb in fallbacks:
                path = os.path.join(fdir, fb)
                if os.path.exists(path):
                    try:
                        f = ImageFont.truetype(path, size=size)
                        return _post_process_font(f)
                    except Exception:
                        pass

        try:
            return ImageFont.load_default(size=size)
        except Exception:
            return ImageFont.load_default()

    def _wrap_text(self, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
        """Wrap text into 1-2 visually balanced lines within max_width."""
        words = text.strip().split()
        if not words:
            return []

        lines = []
        current_words = []

        for word in words:
            test_line = " ".join(current_words + [word])
            bbox = font.getbbox(test_line)
            w = bbox[2] - bbox[0]
            if w <= max_width or not current_words:
                current_words.append(word)
            else:
                lines.append(" ".join(current_words))
                current_words = [word]

        if current_words:
            lines.append(" ".join(current_words))

        if len(lines) == 2 and len(words) >= 4:
            mid = len(words) // 2
            line1 = " ".join(words[:mid])
            line2 = " ".join(words[mid:])
            bbox1 = font.getbbox(line1)
            bbox2 = font.getbbox(line2)
            if (bbox1[2] - bbox1[0]) <= max_width and (bbox2[2] - bbox2[0]) <= max_width:
                return [line1, line2]

        return lines

    def _create_linear_gradient(
        self, width: int, height: int, from_hex: str, to_hex: str, vertical: bool = False
    ) -> Image.Image:
        """Create a smooth 2-color linear gradient image."""
        r1, g1, b1 = self._hex_to_rgb(from_hex)
        r2, g2, b2 = self._hex_to_rgb(to_hex)
        grad = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(grad)

        if vertical:
            for y in range(height):
                ratio = y / max(1, height - 1)
                r = int(r1 + (r2 - r1) * ratio)
                g = int(g1 + (g2 - g1) * ratio)
                b = int(b1 + (b2 - b1) * ratio)
                draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
        else:
            for x in range(width):
                ratio = x / max(1, width - 1)
                r = int(r1 + (r2 - r1) * ratio)
                g = int(g1 + (g2 - g1) * ratio)
                b = int(b1 + (b2 - b1) * ratio)
                draw.line([(x, 0), (x, height)], fill=(r, g, b, 255))

        return grad

    def generate_hook_frame(
        self, hook_text: str, hook_style: str = "skia_impact_badge", style_config: Optional[dict] = None
    ) -> Image.Image:
        """Generate a 1080x1920 RGBA transparent frame containing the complete Skia/FFmpeg hook."""
        clean_key = str(hook_style or "skia_impact_badge").lower().replace(" ", "_").replace("-", "_").strip()
        if clean_key not in SKIA_HOOK_PRESETS and f"skia_{clean_key}" in SKIA_HOOK_PRESETS:
            clean_key = f"skia_{clean_key}"
        cfg = dict(SKIA_HOOK_PRESETS.get(clean_key, SKIA_HOOK_PRESETS.get("news_viralin_badge", SKIA_HOOK_PRESETS["skia_impact_badge"])))

        # Normalize style_config overrides (support both camelCase and snake_case)
        if style_config:
            if style_config.get("fontSize") or style_config.get("font_size"):
                cfg["font_size"] = int(style_config.get("fontSize") or style_config.get("font_size"))
            if style_config.get("fontFamily") or style_config.get("font_family"):
                cfg["font_family"] = str(style_config.get("fontFamily") or style_config.get("font_family"))
            if style_config.get("color") or style_config.get("text_color"):
                cfg["text_color"] = str(style_config.get("color") or style_config.get("text_color"))
            
            # Custom box / background colors
            custom_box = style_config.get("boxColor") or style_config.get("bgColor") or style_config.get("bg_color")
            if custom_box:
                cfg["bg_color"] = custom_box
                cfg["box_color"] = custom_box
                # If user explicitly specifies a box color, disable default preset gradient so they don't collide
                if not style_config.get("gradientEnabled"):
                    cfg.pop("bg_gradient_from", None)
                    cfg.pop("bg_gradient_to", None)

            if style_config.get("lineColor"):
                cfg["line_color"] = style_config.get("lineColor")
                cfg["badge_bg"] = style_config.get("lineColor")

            if style_config.get("badgeEnabled") is not None:
                cfg["badge_enabled"] = bool(style_config.get("badgeEnabled"))
            if style_config.get("badgeText"):
                cfg["badge_text"] = str(style_config.get("badgeText"))

            if style_config.get("gradientEnabled") is not None:
                cfg["gradient_enabled"] = bool(style_config.get("gradientEnabled"))
            if style_config.get("gradientFrom"):
                cfg["gradient_from"] = style_config.get("gradientFrom")
            if style_config.get("gradientTo"):
                cfg["gradient_to"] = style_config.get("gradientTo")
            if style_config.get("glowEnabled") is not None:
                cfg["glow_enabled"] = bool(style_config.get("glowEnabled"))
            if style_config.get("glowColor"):
                cfg["glow_color"] = style_config.get("glowColor")
            if style_config.get("glowSize"):
                cfg["glow_size"] = int(style_config.get("glowSize"))
            if style_config.get("strokeEnabled") is not None:
                cfg["stroke_enabled"] = bool(style_config.get("strokeEnabled"))
            if style_config.get("strokeWidth"):
                cfg["stroke_width"] = int(style_config.get("strokeWidth"))
            if style_config.get("strokeColor"):
                cfg["stroke_color"] = style_config.get("strokeColor")
            if style_config.get("bgOpacity") is not None:
                cfg["bg_opacity"] = float(style_config.get("bgOpacity"))
            if style_config.get("positionY") is not None:
                cfg["position_y"] = float(style_config.get("positionY"))
            if style_config.get("uppercase") is not None:
                cfg["uppercase"] = bool(style_config.get("uppercase"))

        # Format text
        display_text = hook_text.strip()
        if cfg.get("uppercase", False):
            display_text = display_text.upper()

        font_size = int(cfg.get("font_size", 54))
        font = self._resolve_font(cfg.get("font_family", "Anton"), cfg.get("font_weight", "Bold"), font_size)

        # Wrap text (max 880px for 1080px canvas)
        max_text_width = int(self._width * 0.82)
        lines = self._wrap_text(display_text, font, max_text_width)
        if not lines:
            return Image.new("RGBA", (self._width, self._height), (0, 0, 0, 0))

        # Base 1080x1920 Canvas
        frame = Image.new("RGBA", (self._width, self._height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)

        # Calculate bounding box of all lines
        line_height = int(font_size * 1.28)
        line_widths = [font.getbbox(line)[2] - font.getbbox(line)[0] for line in lines]
        total_text_width = max(line_widths)
        total_text_height = line_height * len(lines)

        pos_y_pct = cfg.get("position_y", 42)
        center_y = int(self._height * (pos_y_pct / 100))

        # ─────────────────────────────────────────────────────────────────────
        # 1. SPECIAL CASE: Tape Strips (`quote_strip_tape`)
        # ─────────────────────────────────────────────────────────────────────
        if cfg.get("is_tape_strips") or clean_key == "quote_strip_tape":
            tape_pad_x = 28
            tape_pad_y = 12
            total_block_h = len(lines) * (line_height + 16)
            start_y = center_y - total_block_h // 2

            # 1. Floating Quote / Badge above first tape strip
            if cfg.get("badge_enabled", True):
                b_text = cfg.get("badge_text", "“ QUOTE")
                b_font = self._resolve_font("Montserrat", "Bold", 24)
                b_bbox = b_font.getbbox(b_text)
                b_w = (b_bbox[2] - b_bbox[0]) + 32
                b_h = 36
                b_x = (self._width - b_w) // 2
                b_y = start_y - b_h - 14
                b_bg = self._hex_to_rgba(cfg.get("badge_bg", "#0D9488"), 1.0)
                b_col = self._hex_to_rgba(cfg.get("badge_color", "#FFFFFF"), 1.0)
                
                # Draw badge pill shadow + pill
                draw.rounded_rectangle([b_x, b_y + 4, b_x + b_w, b_y + b_h + 4], radius=18, fill=(0, 0, 0, 120))
                draw.rounded_rectangle([b_x, b_y, b_x + b_w, b_y + b_h], radius=18, fill=b_bg)
                draw.text((b_x + 16, b_y + 4), b_text, font=b_font, fill=b_col)

            # 2. Draw each tape strip individually
            tape_bg = self._hex_to_rgba(cfg.get("box_color", "#FFFFFF"), 1.0)
            txt_col = self._hex_to_rgba(cfg.get("text_color", "#09090B"), 1.0)

            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (self._width - lw) // 2
                ly = start_y + i * (line_height + 16)

                strip_x1 = lx - tape_pad_x
                strip_y1 = ly - tape_pad_y
                strip_x2 = lx + lw + tape_pad_x
                strip_y2 = ly + line_height + tape_pad_y

                # Drop shadow
                draw.rounded_rectangle([strip_x1, strip_y1 + 6, strip_x2, strip_y2 + 6], radius=10, fill=(0, 0, 0, 150))
                # White tape strip
                draw.rounded_rectangle([strip_x1, strip_y1, strip_x2, strip_y2], radius=10, fill=tape_bg)
                # Text
                draw.text((lx, ly), line, font=font, fill=txt_col)

            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 1. SPECIAL CASE: Paper Clip Scrap (`paper_clip_scrap`)
        # ─────────────────────────────────────────────────────────────────────
        if clean_key == "paper_clip_scrap":
            pad_x = 44
            pad_y = 28
            card_w = min(int(self._width * 0.90), max(total_text_width + pad_x * 2, 520))
            card_h = total_text_height + pad_y * 2 + 14

            # 1. Pastel Kraft Paper Card (Tilted -2.5 degrees)
            paper_layer = Image.new("RGBA", (card_w + 60, card_h + 60), (0, 0, 0, 0))
            p_draw = ImageDraw.Draw(paper_layer)
            bg_col = self._hex_to_rgba(cfg.get("box_color", cfg.get("bg_color", "#FEF08A")), 1.0)

            # Paper shadow and body
            p_draw.rounded_rectangle([30, 30 + 8, 30 + card_w, 30 + card_h + 8], radius=14, fill=(0, 0, 0, 130))
            p_draw.rounded_rectangle([30, 30, 30 + card_w, 30 + card_h], radius=14, fill=bg_col)

            # Washi Tape on top right corner
            tape_w, tape_h = 70, 24
            p_draw.rectangle([30 + card_w - 60, 20, 30 + card_w + 10, 20 + tape_h], fill=(255, 255, 255, 170), outline=(200, 200, 200, 120), width=1)

            # Metallic Vector Paper Clip on top left corner
            clip_x = 46
            clip_y = 12
            clip_w = 30
            clip_h = 76
            p_draw.rounded_rectangle([clip_x, clip_y, clip_x + clip_w, clip_y + clip_h], radius=14, outline=(71, 85, 105, 255), width=5)
            p_draw.rounded_rectangle([clip_x + 1, clip_y + 1, clip_x + clip_w - 1, clip_y + clip_h - 1], radius=13, outline=(226, 232, 240, 255), width=2)
            p_draw.rounded_rectangle([clip_x + 8, clip_y + 16, clip_x + clip_w - 8, clip_y + clip_h - 14], radius=7, outline=(71, 85, 105, 255), width=4)
            p_draw.rounded_rectangle([clip_x + 9, clip_y + 17, clip_x + clip_w - 9, clip_y + clip_h - 15], radius=6, outline=(255, 255, 255, 255), width=1)

            # Rotate whole paper sheet -2.5 degrees
            p_rot = paper_layer.rotate(-2.5, resample=Image.BICUBIC, expand=True)
            px = (self._width - p_rot.width) // 2
            py = center_y - p_rot.height // 2
            frame.paste(p_rot, (px, py), p_rot)

            # Text directly centered on card
            txt_color = self._hex_to_rgba(cfg.get("text_color", "#1C1917"), 1.0)
            text_origin_y = center_y - (total_text_height // 2) + 6
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (self._width - lw) // 2
                ly = text_origin_y + i * line_height
                draw.text((lx, ly), line, font=font, fill=txt_color)

            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 2. SPECIAL CASE: Trending Radar Alert (`trending_radar`)
        # ─────────────────────────────────────────────────────────────────────
        if clean_key == "trending_radar":
            pad_x = 42
            pad_y = 26
            card_w = min(int(self._width * 0.92), max(total_text_width + pad_x * 2, 520))
            card_h = total_text_height + pad_y * 2 + 18
            card_x = (self._width - card_w) // 2
            card_y = center_y - card_h // 2

            neon_magenta = self._hex_to_rgba(cfg.get("badge_bg", "#D946EF"), 1.0)
            neon_cyan = self._hex_to_rgba(cfg.get("line_color", "#06B6D4"), 1.0)
            bg_col = self._hex_to_rgba(cfg.get("box_color", "#090514"), 0.94)

            # Glowing dark card
            draw.rounded_rectangle([card_x, card_y + 10, card_x + card_w, card_y + card_h + 10], radius=16, fill=(0, 0, 0, 180))
            draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=16, fill=bg_col, outline=neon_magenta, width=2)

            # Corner HUD crosshair brackets
            hud_len = 16
            draw.line([card_x + 6, card_y + 6, card_x + 6 + hud_len, card_y + 6], fill=neon_cyan, width=3)
            draw.line([card_x + 6, card_y + 6, card_x + 6, card_y + 6 + hud_len], fill=neon_cyan, width=3)
            draw.line([card_x + card_w - 6 - hud_len, card_y + 6, card_x + card_w - 6, card_y + 6], fill=neon_cyan, width=3)
            draw.line([card_x + card_w - 6, card_y + 6, card_x + card_w - 6, card_y + 6 + hud_len], fill=neon_cyan, width=3)
            draw.line([card_x + 6, card_y + card_h - 6 - hud_len, card_x + 6, card_y + card_h - 6], fill=neon_cyan, width=3)
            draw.line([card_x + 6, card_y + card_h - 6, card_x + 6 + hud_len, card_y + card_h - 6], fill=neon_cyan, width=3)
            draw.line([card_x + card_w - 6 - hud_len, card_y + card_h - 6, card_x + card_w - 6, card_y + card_h - 6], fill=neon_cyan, width=3)
            draw.line([card_x + card_w - 6, card_y + card_h - 6 - hud_len, card_x + card_w - 6, card_y + card_h - 6], fill=neon_cyan, width=3)

            # Top Badge "TRENDING NOW" with Radar Dot
            if cfg.get("badge_enabled", True):
                b_text = str(cfg.get("badge_text", "TRENDING NOW"))
                b_font = self._resolve_font("Montserrat", "900", 20)
                b_bbox = b_font.getbbox(b_text)
                bw = (b_bbox[2] - b_bbox[0]) + 44
                bh = 32
                bx = (self._width - bw) // 2
                by = card_y - 16
                draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=8, fill=neon_magenta, outline=(255, 255, 255, 80), width=1)
                # Radar Dot
                draw.ellipse([bx + 12, by + 10, bx + 22, by + 20], fill=(255, 255, 255, 255))
                draw.text((bx + 28, by + 6), b_text, font=b_font, fill=(255, 255, 255, 255))

            # Text
            txt_color = self._hex_to_rgba(cfg.get("text_color", "#FFFFFF"), 1.0)
            text_origin_y = card_y + pad_y + (10 if cfg.get("badge_enabled", True) else 0)
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (self._width - lw) // 2
                ly = text_origin_y + i * line_height
                draw.text((lx, ly), line, font=font, fill=txt_color)

            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 3. SPECIAL CASE: Breaking News Live (`news_breaking_live`)
        # ─────────────────────────────────────────────────────────────────────
        if clean_key == "news_breaking_live":
            pad_x = 40
            pad_y = 24
            card_w = min(int(self._width * 0.94), max(total_text_width + pad_x * 2, 540))
            card_h = total_text_height + pad_y * 2 + 16
            card_x = (self._width - card_w) // 2
            card_y = center_y - card_h // 2

            red_col = self._hex_to_rgba(cfg.get("badge_bg", "#DC2626"), 1.0)
            bg_col = self._hex_to_rgba(cfg.get("box_color", "#0F172A"), 0.95)

            # Dark card with bottom red stripe
            draw.rounded_rectangle([card_x, card_y + 8, card_x + card_w, card_y + card_h + 8], radius=14, fill=(0, 0, 0, 180))
            draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=14, fill=bg_col)
            draw.rounded_rectangle([card_x, card_y + card_h - 8, card_x + card_w, card_y + card_h], radius=4, fill=red_col)

            # Red Badge "BREAKING" with white circle indicator
            if cfg.get("badge_enabled", True):
                b_text = str(cfg.get("badge_text", "BREAKING"))
                b_font = self._resolve_font("Montserrat", "900", 22)
                b_bbox = b_font.getbbox(b_text)
                bw = (b_bbox[2] - b_bbox[0]) + 38
                bh = 34
                bx = card_x + 24
                by = card_y + 14
                draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=6, fill=red_col)
                draw.ellipse([bx + 10, by + 11, bx + 20, by + 21], fill=(255, 255, 255, 255))
                draw.text((bx + 26, by + 6), b_text, font=b_font, fill=(255, 255, 255, 255))

            # Text
            txt_color = self._hex_to_rgba(cfg.get("text_color", "#FFFFFF"), 1.0)
            text_origin_y = card_y + pad_y + (24 if cfg.get("badge_enabled", True) else 0)
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = card_x + 28
                ly = text_origin_y + i * line_height
                draw.text((lx, ly), line, font=font, fill=txt_color)

            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 4. SPECIAL CASE: #VIRALIN Badge (`news_viralin_badge`)
        # ─────────────────────────────────────────────────────────────────────
        if clean_key == "news_viralin_badge":
            pad_x = 40
            pad_y = 28
            card_w = min(int(self._width * 0.90), max(total_text_width + pad_x * 2, 500))
            card_h = total_text_height + pad_y * 2 + 10
            card_x = (self._width - card_w) // 2
            card_y = center_y - card_h // 2

            # 1. White rotated paper card behind (tilted -3 degrees)
            white_bg_layer = Image.new("RGBA", (card_w + 40, card_h + 40), (0, 0, 0, 0))
            w_draw = ImageDraw.Draw(white_bg_layer)
            w_draw.rounded_rectangle([20, 20, card_w + 20, card_h + 20], radius=12, fill=(255, 255, 255, 255))
            w_rot = white_bg_layer.rotate(3.0, resample=Image.BICUBIC, expand=True)
            w_x = (self._width - w_rot.width) // 2
            w_y = center_y - w_rot.height // 2
            # Drop shadow
            draw.rounded_rectangle([card_x - 6, card_y + 12, card_x + card_w + 6, card_y + card_h + 18], radius=14, fill=(0, 0, 0, 110))
            frame.paste(w_rot, (w_x, w_y), w_rot)

            # 2. Main Yellow Card
            yellow_bg = self._hex_to_rgba(cfg.get("box_color", cfg.get("bg_color", "#EAB308")), 1.0)
            draw.rounded_rectangle([card_x, card_y + 8, card_x + card_w, card_y + card_h + 8], radius=12, fill=(0, 0, 0, 160))
            draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=12, fill=yellow_bg)

            # 3. Tilted Blue Badge on top
            if cfg.get("badge_enabled", True):
                b_text = str(cfg.get("badge_text", "#VIRALIN"))
                b_font = self._resolve_font("Montserrat", "900", 26)
                b_bbox = b_font.getbbox(b_text)
                b_w = (b_bbox[2] - b_bbox[0]) + 36
                b_h = 42
                badge_layer = Image.new("RGBA", (b_w + 24, b_h + 24), (0, 0, 0, 0))
                b_draw = ImageDraw.Draw(badge_layer)
                badge_bg = self._hex_to_rgba(cfg.get("badge_bg", cfg.get("line_color", "#1D4ED8")), 1.0)
                badge_txt = self._hex_to_rgba(cfg.get("badge_color", "#FACC15"), 1.0)
                b_draw.rounded_rectangle([12, 12, 12 + b_w, 12 + b_h], radius=8, fill=badge_bg, outline=(255, 255, 255, 60), width=2)
                b_draw.text((12 + 18, 12 + 7), b_text, font=b_font, fill=badge_txt)
                b_rot = badge_layer.rotate(3.5, resample=Image.BICUBIC, expand=True)
                bx = (self._width - b_rot.width) // 2
                by = card_y - b_rot.height // 2 - 2
                frame.paste(b_rot, (bx, by), b_rot)

            # 4. Centered Black Text
            txt_color = self._hex_to_rgba(cfg.get("text_color", "#09090B"), 1.0)
            text_origin_y = card_y + pad_y + (6 if cfg.get("badge_enabled", True) else 0)
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (self._width - lw) // 2
                ly = text_origin_y + i * line_height
                draw.text((lx, ly), line, font=font, fill=txt_color)

            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 3. SPECIAL CASE: News Portal Notch (`news_portal_pantau`)
        # ─────────────────────────────────────────────────────────────────────
        if clean_key == "news_portal_pantau":
            pad_x = 36
            pad_y = 24
            card_w = min(int(self._width * 0.90), max(total_text_width + pad_x * 2, 500))
            card_h = total_text_height + pad_y * 2 + 20
            card_x = (self._width - card_w) // 2
            card_y = center_y - card_h // 2
            accent_col = self._hex_to_rgba(cfg.get("line_color", "#DC2626"), 1.0)

            # White Card with Red Bottom Border
            draw.rounded_rectangle([card_x, card_y + 8, card_x + card_w, card_y + card_h + 8], radius=14, fill=(0, 0, 0, 160))
            draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=14, fill=(255, 255, 255, 255))
            draw.rectangle([card_x, card_y + card_h - 6, card_x + card_w, card_y + card_h], fill=accent_col)

            # Red Category Tag at top-left
            if cfg.get("badge_enabled", True):
                cat_text = str(cfg.get("badge_text", "NEWS"))
                cat_font = self._resolve_font("Inter", "900", 22)
                cat_bbox = cat_font.getbbox(cat_text)
                cat_w = (cat_bbox[2] - cat_bbox[0]) + 24
                cat_h = 32
                draw.rounded_rectangle([card_x + 20, card_y + 16, card_x + 20 + cat_w, card_y + 16 + cat_h], radius=4, fill=accent_col)
                draw.text((card_x + 32, card_y + 20), cat_text, font=cat_font, fill=(255, 255, 255, 255))

            # Speech bubble triangular notch at bottom-right
            notch_w = 26
            notch_h = 16
            notch_x = card_x + card_w - 64
            draw.polygon([(notch_x, card_y + card_h), (notch_x + notch_w, card_y + card_h), (notch_x + notch_w // 2, card_y + card_h + notch_h)], fill=accent_col)

            # Text
            txt_color = self._hex_to_rgba(cfg.get("text_color", "#09090B"), 1.0)
            text_origin_y = card_y + pad_y + (30 if cfg.get("badge_enabled", True) else 0)
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = card_x + 24
                ly = text_origin_y + i * line_height
                draw.text((lx, ly), line, font=font, fill=txt_color)

            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 4. SPECIAL CASE: Detik Red Box (`news_offset_box`)
        # ─────────────────────────────────────────────────────────────────────
        if clean_key == "news_offset_box":
            pad_x = 36
            pad_y = 22
            card_w = min(int(self._width * 0.90), max(total_text_width + pad_x * 2, 500))
            card_h = total_text_height + pad_y * 2
            card_x = (self._width - card_w) // 2
            card_y = center_y - card_h // 2
            box_col = self._hex_to_rgba(cfg.get("box_color", cfg.get("bg_color", "#DC2626")), 1.0)
            frame_col = self._hex_to_rgba(cfg.get("line_color", "#FFFFFF"), 1.0)

            # White offset frame border sticking out top-left
            draw.line([card_x - 12, card_y - 12, card_x + int(card_w * 0.65), card_y - 12], fill=frame_col, width=4)
            draw.line([card_x - 12, card_y - 12, card_x - 12, card_y + int(card_h * 0.80)], fill=frame_col, width=4)

            # Main Red Box
            draw.rounded_rectangle([card_x, card_y + 8, card_x + card_w, card_y + card_h + 8], radius=8, fill=(0, 0, 0, 160))
            draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=8, fill=box_col)

            # White Centered Text
            txt_color = self._hex_to_rgba(cfg.get("text_color", "#FFFFFF"), 1.0)
            text_origin_y = card_y + pad_y
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (self._width - lw) // 2
                ly = text_origin_y + i * line_height
                draw.text((lx, ly), line, font=font, fill=txt_color)

            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 5. SPECIAL CASE: Brutalist Bracket (`brutalist_bracket`)
        # ─────────────────────────────────────────────────────────────────────
        if clean_key == "brutalist_bracket":
            pad_x = 42
            pad_y = 24
            card_w = min(int(self._width * 0.90), max(total_text_width + pad_x * 2, 500))
            card_h = total_text_height + pad_y * 2
            card_x = (self._width - card_w) // 2
            card_y = center_y - card_h // 2
            bracket_col = self._hex_to_rgba(cfg.get("line_color", "#000000"), 1.0)
            box_col = self._hex_to_rgba(cfg.get("box_color", "#FFFFFF"), 1.0)

            # Main White Box
            draw.rounded_rectangle([card_x, card_y + 8, card_x + card_w, card_y + card_h + 8], radius=8, fill=(0, 0, 0, 150))
            draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=8, fill=box_col)

            # Left Brutalist Bracket
            b_off = 12
            draw.line([card_x - b_off, card_y - b_off, card_x - b_off + 36, card_y - b_off], fill=bracket_col, width=6)
            draw.line([card_x - b_off, card_y - b_off, card_x - b_off, card_y + card_h + b_off], fill=bracket_col, width=6)
            draw.line([card_x - b_off, card_y + card_h + b_off, card_x - b_off + 36, card_y + card_h + b_off], fill=bracket_col, width=6)

            # Dark Text
            txt_color = self._hex_to_rgba(cfg.get("text_color", "#09090B"), 1.0)
            text_origin_y = card_y + pad_y
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = card_x + 24
                ly = text_origin_y + i * line_height
                draw.text((lx, ly), line, font=font, fill=txt_color)

            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 6. SPECIAL CASE: On-Air Lower Third (`podcast_lower_third`)
        # ─────────────────────────────────────────────────────────────────────
        if clean_key == "podcast_lower_third":
            pad_x = 36
            pad_y = 20
            pos_y_pct = cfg.get("position_y", 78)
            center_y = int(self._height * (pos_y_pct / 100))
            card_w = min(int(self._width * 0.92), max(total_text_width + pad_x * 2 + 80, 520))
            card_h = total_text_height + pad_y * 2
            card_x = (self._width - card_w) // 2
            card_y = center_y - card_h // 2
            accent_col = self._hex_to_rgba(cfg.get("line_color", "#16F2B3"), 1.0)

            # Dark Blue Glass Capsule with Gradient
            grad_img = self._create_linear_gradient(card_w, card_h, "#06111F", "#141C2C", vertical=False)
            mask = Image.new("L", (card_w, card_h), 0)
            m_draw = ImageDraw.Draw(mask)
            m_draw.rounded_rectangle([0, 0, card_w, card_h], radius=16, fill=230)
            draw.rounded_rectangle([card_x, card_y + 8, card_x + card_w, card_y + card_h + 8], radius=16, fill=(0, 0, 0, 160))
            frame.paste(grad_img, (card_x, card_y), mask)
            draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=16, outline=accent_col, width=2)
            # Left vertical accent bar
            draw.line([card_x + 4, card_y + 6, card_x + 4, card_y + card_h - 6], fill=accent_col, width=8)

            # Glowing "ON AIR" Badge
            if cfg.get("badge_enabled", True):
                badge_txt = str(cfg.get("badge_text", "ON AIR"))
                b_font = self._resolve_font("Montserrat", "900", 18)
                draw.ellipse([card_x + 22, card_y + (card_h // 2) - 14, card_x + 34, card_y + (card_h // 2) - 2], fill=accent_col)
                draw.text((card_x + 16, card_y + (card_h // 2) + 2), badge_txt, font=b_font, fill=accent_col)

            # Text
            txt_color = self._hex_to_rgba(cfg.get("text_color", "#F8FAFC"), 1.0)
            text_origin_y = card_y + pad_y
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = card_x + (85 if cfg.get("badge_enabled", True) else 24)
                ly = text_origin_y + i * line_height
                draw.text((lx, ly), line, font=font, fill=txt_color)

            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 7. SPECIAL CASE: Quote Card (`quote_card`)
        # ─────────────────────────────────────────────────────────────────────
        if clean_key == "quote_card":
            pad_x = 42
            pad_y = 26
            card_w = min(int(self._width * 0.90), max(total_text_width + pad_x * 2, 500))
            card_h = total_text_height + pad_y * 2 + 16
            card_x = (self._width - card_w) // 2
            card_y = center_y - card_h // 2
            card_bg = self._hex_to_rgba(cfg.get("box_color", "#F5EFE1"), 0.98)
            accent_col = self._hex_to_rgba(cfg.get("badge_bg", "#FF4D2D"), 1.0)

            # Cream Card with Shadow
            draw.rounded_rectangle([card_x, card_y + 8, card_x + card_w, card_y + card_h + 8], radius=16, fill=(0, 0, 0, 160))
            draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=16, fill=card_bg)

            # Top Orange Accent Bar
            bar_w = int(card_w * 0.38)
            bar_x = card_x + (card_w - bar_w) // 2
            draw.rounded_rectangle([bar_x, card_y + card_h - 14, bar_x + bar_w, card_y + card_h - 10], radius=2, fill=accent_col)

            # Quote Mark Symbol
            q_font = self._resolve_font("Playfair Display", "Bold", 48)
            draw.text((card_x + 20, card_y + 6), "\"", font=q_font, fill=accent_col)

            # Text
            txt_color = self._hex_to_rgba(cfg.get("text_color", "#171717"), 1.0)
            text_origin_y = card_y + pad_y
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (self._width - lw) // 2
                ly = text_origin_y + i * line_height
                draw.text((lx, ly), line, font=font, fill=txt_color)

            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 8. SPECIAL CASE: Waveform Pulse (`waveform_pulse`)
        # ─────────────────────────────────────────────────────────────────────
        if clean_key == "waveform_pulse":
            wave_col = self._hex_to_rgba(cfg.get("glow_color", cfg.get("text_color", "#14F1D9")), 1.0)
            pad_x = 36
            pad_y = 22
            card_w = min(int(self._width * 0.90), max(total_text_width + pad_x * 2, 500))
            card_h = total_text_height + pad_y * 2 + 50
            card_x = (self._width - card_w) // 2
            card_y = center_y - card_h // 2

            # 1. Live Audio Badge
            if cfg.get("badge_enabled", True):
                b_text = str(cfg.get("badge_text", "LIVE AUDIO"))
                b_font = self._resolve_font("Montserrat", "900", 20)
                b_bbox = b_font.getbbox(b_text)
                bw = b_bbox[2] - b_bbox[0]
                draw.text(((self._width - bw) // 2, card_y), b_text, font=b_font, fill=wave_col)

            # 2. Waveform Soundbars
            bar_count = 13
            bar_spacing = 16
            bar_w = 6
            total_bars_w = bar_count * bar_spacing
            start_bar_x = (self._width - total_bars_w) // 2
            bar_center_y = card_y + 40
            for bi in range(bar_count):
                bh = 14 + (bi % 4) * 8 + ((bi * 3) % 5) * 4
                bx = start_bar_x + bi * bar_spacing
                draw.rounded_rectangle([bx, bar_center_y - bh // 2, bx + bar_w, bar_center_y + bh // 2], radius=3, fill=wave_col)

            # 3. Text
            txt_color = self._hex_to_rgba(cfg.get("text_color", "#FFFFFF"), 1.0)
            text_origin_y = card_y + 70
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (self._width - lw) // 2
                ly = text_origin_y + i * line_height
                draw.text((lx + 3, ly + 4), line, font=font, fill=(0, 0, 0, 220))
                draw.text((lx, ly), line, font=font, fill=txt_color)

            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 9. SPECIAL CASE: Breaking Hazard Tape (`breaking_tape`)
        # ─────────────────────────────────────────────────────────────────────
        if clean_key == "breaking_tape":
            tape_color = self._hex_to_rgba(cfg.get("box_color", "#FFDD2D"), 1.0)
            badge_color = self._hex_to_rgba(cfg.get("line_color", "#D71920"), 1.0)
            card_w = int(self._width * 1.15)
            card_h = total_text_height + 60
            tape_layer = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
            t_draw = ImageDraw.Draw(tape_layer)

            # Yellow gradient tape with top/bottom black borders
            t_draw.rectangle([0, 0, card_w, card_h], fill=tape_color)
            t_draw.rectangle([0, 0, card_w, 6], fill=(0, 0, 0, 255))
            t_draw.rectangle([0, card_h - 6, card_w, card_h], fill=(0, 0, 0, 255))

            # HOT TAKE Badge
            if cfg.get("badge_enabled", True):
                b_text = str(cfg.get("badge_text", "HOT TAKE"))
                b_font = self._resolve_font("Montserrat", "900", 22)
                b_bbox = b_font.getbbox(b_text)
                bw = b_bbox[2] - b_bbox[0]
                t_draw.text(((card_w - bw) // 2, 12), b_text, font=b_font, fill=badge_color)

            # Text
            txt_color = self._hex_to_rgba(cfg.get("text_color", "#111111"), 1.0)
            text_origin_y = 20 + (22 if cfg.get("badge_enabled", True) else 0)
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (card_w - lw) // 2
                ly = text_origin_y + i * line_height
                t_draw.text((lx, ly), line, font=font, fill=txt_color)

            # Rotate Tape -4 degrees
            tape_rot = tape_layer.rotate(-4.0, resample=Image.BICUBIC, expand=True)
            rx = (self._width - tape_rot.width) // 2
            ry = center_y - tape_rot.height // 2
            # Drop shadow
            draw.rounded_rectangle([rx + 10, ry + 20, rx + tape_rot.width - 10, ry + tape_rot.height + 20], radius=16, fill=(0, 0, 0, 140))
            frame.paste(tape_rot, (rx, ry), tape_rot)
            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 10. SPECIAL CASE: Mic Drop Capsule (`mic_drop`)
        # ─────────────────────────────────────────────────────────────────────
        if clean_key == "mic_drop":
            accent_col = self._hex_to_rgba(cfg.get("box_color", cfg.get("gradient_to", "#FF4D7D")), 1.0)
            pad_x = 48
            pad_y = 28
            card_w = min(int(self._width * 0.90), max(total_text_width + pad_x * 2, 500))
            card_h = total_text_height + pad_y * 2
            card_x = (self._width - card_w) // 2
            card_y = center_y - card_h // 2
            radius = card_h // 2

            # Glowing Capsule
            draw.rounded_rectangle([card_x, card_y + 8, card_x + card_w, card_y + card_h + 8], radius=radius, fill=(0, 0, 0, 160))
            draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=radius, fill=(5, 5, 7, 200), outline=accent_col, width=4)

            # Bottom impact bar
            bar_w = 60
            bar_x = (self._width - bar_w) // 2
            draw.rounded_rectangle([bar_x, card_y + card_h + 12, bar_x + bar_w, card_y + card_h + 18], radius=3, fill=accent_col)

            # Text
            txt_color = self._hex_to_rgba(cfg.get("text_color", "#FFFFFF"), 1.0)
            text_origin_y = card_y + pad_y
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (self._width - lw) // 2
                ly = text_origin_y + i * line_height
                draw.text((lx + 3, ly + 4), line, font=font, fill=(0, 0, 0, 220))
                draw.text((lx, ly), line, font=font, fill=txt_color)

            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 11. SPECIAL CASE: Split Panel (`split_panel`)
        # ─────────────────────────────────────────────────────────────────────
        if clean_key == "split_panel":
            accent_col = self._hex_to_rgba(cfg.get("line_color", "#38BDF8"), 1.0)
            panel_col = self._hex_to_rgba(cfg.get("box_color", "#0F172A"), 0.92)
            badge_enabled = cfg.get("badge_enabled", True)
            badge_w = 56 if badge_enabled else 0
            pad_x = 36
            pad_y = 24
            card_w = min(int(self._width * 0.90), max(total_text_width + pad_x * 2 + badge_w, 500))
            card_h = total_text_height + pad_y * 2
            card_x = (self._width - card_w) // 2
            card_y = center_y - card_h // 2

            # Background Box
            draw.rounded_rectangle([card_x, card_y + 8, card_x + card_w, card_y + card_h + 8], radius=12, fill=(0, 0, 0, 160))
            draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=12, fill=panel_col, outline=accent_col, width=2)

            # Left Vertical Badge
            if badge_enabled:
                draw.rectangle([card_x, card_y, card_x + badge_w, card_y + card_h], fill=accent_col)
                b_text = str(cfg.get("badge_text", "POINT"))
                b_font = self._resolve_font("Montserrat", "900", 20)
                b_bbox = b_font.getbbox(b_text)
                bw = b_bbox[2] - b_bbox[0]
                # Rotate vertical text
                v_layer = Image.new("RGBA", (card_h, badge_w), (0, 0, 0, 0))
                v_draw = ImageDraw.Draw(v_layer)
                v_draw.text(((card_h - bw) // 2, 14), b_text, font=b_font, fill=(6, 17, 31, 255))
                v_rot = v_layer.rotate(90, expand=True)
                frame.paste(v_rot, (card_x, card_y), v_rot)

            # Text
            txt_color = self._hex_to_rgba(cfg.get("text_color", "#FFFFFF"), 1.0)
            text_origin_y = card_y + pad_y
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = card_x + badge_w + 24
                ly = text_origin_y + i * line_height
                draw.text((lx, ly), line, font=font, fill=txt_color)

            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 12. SPECIAL CASE: Comment Reply Bubble (`comment_reply`)
        # ─────────────────────────────────────────────────────────────────────
        if clean_key == "comment_reply":
            pad_x = 36
            pad_y = 20
            card_w = min(int(self._width * 0.90), max(total_text_width + pad_x * 2, 500))
            card_h = total_text_height + pad_y * 2 + 24
            card_x = (self._width - card_w) // 2
            card_y = center_y - card_h // 2
            box_col = self._hex_to_rgba(cfg.get("box_color", "#FFFFFF"), 0.98)

            # White speech bubble card
            draw.rounded_rectangle([card_x, card_y + 8, card_x + card_w, card_y + card_h + 8], radius=14, fill=(0, 0, 0, 150))
            draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=14, fill=box_col)

            # Speech tail at bottom-left
            tail_x = card_x + 36
            draw.polygon([(tail_x, card_y + card_h), (tail_x + 20, card_y + card_h), (tail_x + 10, card_y + card_h + 14)], fill=box_col)

            # Reply header
            h_text = str(cfg.get("badge_text", "replying to @viewer"))
            h_font = self._resolve_font("Inter", "Bold", 20)
            draw.text((card_x + 24, card_y + 16), h_text, font=h_font, fill=(100, 100, 110, 255))

            # Text
            txt_color = self._hex_to_rgba(cfg.get("text_color", "#18181B"), 1.0)
            text_origin_y = card_y + pad_y + 24
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = card_x + 24
                ly = text_origin_y + i * line_height
                draw.text((lx, ly), line, font=font, fill=txt_color)

            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 13. SPECIAL CASE: Search Prompt Bar (`search_prompt`)
        # ─────────────────────────────────────────────────────────────────────
        if clean_key == "search_prompt":
            pad_x = 56
            pad_y = 20
            card_w = min(int(self._width * 0.92), max(total_text_width + pad_x * 2 + 60, 520))
            card_h = total_text_height + pad_y * 2
            card_x = (self._width - card_w) // 2
            card_y = center_y - card_h // 2
            accent_col = self._hex_to_rgba(cfg.get("line_color", "#22D3EE"), 1.0)
            box_col = self._hex_to_rgba(cfg.get("box_color", "#0F172A"), 0.94)
            radius = card_h // 2

            # Search bar pill
            draw.rounded_rectangle([card_x, card_y + 8, card_x + card_w, card_y + card_h + 8], radius=radius, fill=(0, 0, 0, 150))
            draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=radius, fill=box_col, outline=accent_col, width=2)

            # Search Icon (Vector drawn magnifying glass)
            icon_cx = card_x + 36
            icon_cy = card_y + (card_h // 2)
            draw.ellipse([icon_cx - 9, icon_cy - 9, icon_cx + 6, icon_cy + 6], outline=accent_col, width=3)
            draw.line([icon_cx + 4, icon_cy + 4, icon_cx + 12, icon_cy + 12], fill=accent_col, width=3)

            # Arrow Icon on right (drawn vector arrow)
            ar_x = card_x + card_w - 36
            ar_y = icon_cy
            draw.line([ar_x - 6, ar_y + 6, ar_x + 6, ar_y - 6], fill=accent_col, width=3)
            draw.line([ar_x - 2, ar_y - 6, ar_x + 6, ar_y - 6], fill=accent_col, width=3)
            draw.line([ar_x + 6, ar_y - 6, ar_x + 6, ar_y + 2], fill=accent_col, width=3)

            # Text
            txt_color = self._hex_to_rgba(cfg.get("text_color", "#FFFFFF"), 1.0)
            text_origin_y = card_y + pad_y
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = card_x + 64
                ly = text_origin_y + i * line_height
                draw.text((lx, ly), line, font=font, fill=txt_color)

            return frame

        # ─────────────────────────────────────────────────────────────────────
        # 8. STANDARD CARD / BADGE / CYBERPUNK / GLASS HOOKS
        # ─────────────────────────────────────────────────────────────────────
        pad_x = cfg.get("bg_padding_x", 36)
        pad_y = cfg.get("bg_padding_y", 22)
        card_w = total_text_width + pad_x * 2
        card_h = total_text_height + pad_y * 2
        card_radius = cfg.get("bg_radius", 16)
        if card_radius >= 999:
            card_radius = card_h // 2

        card_x = (self._width - card_w) // 2
        card_y = center_y - card_h // 2

        # Draw Background Card
        if cfg.get("bg_gradient_from") and cfg.get("bg_gradient_to"):
            grad_img = self._create_linear_gradient(card_w, card_h, cfg["bg_gradient_from"], cfg["bg_gradient_to"])
            mask = Image.new("L", (card_w, card_h), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([0, 0, card_w, card_h], radius=card_radius, fill=255)

            if cfg.get("bg_shadow_color"):
                sh_rgb = self._hex_to_rgba(cfg["bg_shadow_color"], 1.0)
                sh_off_y = cfg.get("bg_shadow_offset_y", 6)
                draw.rounded_rectangle(
                    [card_x, card_y + sh_off_y, card_x + card_w, card_y + card_h + sh_off_y],
                    radius=card_radius,
                    fill=sh_rgb,
                )
            frame.paste(grad_img, (card_x, card_y), mask)

        elif cfg.get("bg_opacity", 0) > 0 and cfg.get("bg_color"):
            bg_rgba = self._hex_to_rgba(cfg["bg_color"], cfg["bg_opacity"])

            # Outer Shadow
            draw.rounded_rectangle(
                [card_x, card_y + 6, card_x + card_w, card_y + card_h + 6],
                radius=card_radius,
                fill=(0, 0, 0, 160),
            )
            draw.rounded_rectangle(
                [card_x, card_y, card_x + card_w, card_y + card_h],
                radius=card_radius,
                fill=bg_rgba,
            )

            # Border
            if cfg.get("bg_border_color") and cfg.get("bg_border_width", 0) > 0:
                b_rgba = self._hex_to_rgba(cfg["bg_border_color"], 0.9)
                draw.rounded_rectangle(
                    [card_x, card_y, card_x + card_w, card_y + card_h],
                    radius=card_radius,
                    outline=b_rgba,
                    width=cfg["bg_border_width"],
                )

            # Corner accents for Cyberpunk / Brutalist
            if cfg.get("corner_accents"):
                accent_c = (255, 0, 127, 255) if "cyber" in clean_key else (0, 0, 0, 255)
                bracket_sz = 16
                draw.line([card_x - 4, card_y - 4, card_x + bracket_sz, card_y - 4], fill=accent_c, width=4)
                draw.line([card_x - 4, card_y - 4, card_x - 4, card_y + bracket_sz], fill=accent_c, width=4)
                draw.line([card_x + card_w + 4, card_y + card_h + 4, card_x + card_w - bracket_sz, card_y + card_h + 4], fill=accent_c, width=4)
                draw.line([card_x + card_w + 4, card_y + card_h + 4, card_x + card_w + 4, card_y + card_h - bracket_sz], fill=accent_c, width=4)

        # ── Floating Badge above Card ──
        if cfg.get("badge_enabled") and cfg.get("badge_text"):
            b_text = str(cfg["badge_text"])
            b_font = self._resolve_font("Montserrat", "Bold", 24)
            b_bbox = b_font.getbbox(b_text)
            b_w = (b_bbox[2] - b_bbox[0]) + 32
            b_h = 36
            b_x = (self._width - b_w) // 2
            b_y = card_y - b_h - 12
            b_bg = self._hex_to_rgba(cfg.get("badge_bg", "#DC2626"), 1.0)
            b_col = self._hex_to_rgba(cfg.get("badge_color", "#FFFFFF"), 1.0)

            draw.rounded_rectangle([b_x, b_y + 3, b_x + b_w, b_y + b_h + 3], radius=18, fill=(0, 0, 0, 140))
            draw.rounded_rectangle([b_x, b_y, b_x + b_w, b_y + b_h], radius=18, fill=b_bg)
            draw.text((b_x + 16, b_y + 4), b_text, font=b_font, fill=b_col)

        # ── Draw Text ──
        text_origin_y = card_y + pad_y

        if cfg.get("is_glitch_rgb"):
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (self._width - lw) // 2
                ly = text_origin_y + i * line_height
                draw.text((lx - 4, ly), line, font=font, fill=(255, 0, 0, 200))
                draw.text((lx + 4, ly), line, font=font, fill=(0, 255, 255, 200))
                draw.text((lx, ly), line, font=font, fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0, 255))

        elif cfg.get("gradient_enabled") and cfg.get("gradient_from") and cfg.get("gradient_to"):
            t_mask = Image.new("L", (card_w, card_h), 0)
            t_mask_draw = ImageDraw.Draw(t_mask)

            # 1. Soft Ambient Glow if enabled
            if cfg.get("glow_enabled"):
                gw_c = self._hex_to_rgba(cfg.get("glow_color", cfg.get("gradient_from", "#00F0FF")), 0.85)
                glow_layer = Image.new("RGBA", (card_w + 60, card_h + 60), (0, 0, 0, 0))
                g_draw = ImageDraw.Draw(glow_layer)
                for idx, line in enumerate(lines):
                    lw = line_widths[idx]
                    lx = (card_w + 60 - lw) // 2
                    ly = 30 + pad_y + idx * line_height
                    g_draw.text((lx, ly), line, font=font, fill=gw_c, stroke_width=2, stroke_fill=gw_c)
                glow_blurred = glow_layer.filter(ImageFilter.GaussianBlur(radius=8))
                frame.paste(glow_blurred, (card_x - 30, card_y - 30), glow_blurred)

            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (card_w - lw) // 2
                ly = pad_y + i * line_height

                if cfg.get("stroke_enabled"):
                    sw = cfg.get("stroke_width", 2)
                    sc_hex = cfg.get("stroke_color", "#000000")
                    scr, scg, scb = self._hex_to_rgb(sc_hex)
                    draw.text(
                        (card_x + lx, card_y + ly),
                        line,
                        font=font,
                        fill=None,
                        stroke_width=sw,
                        stroke_fill=(scr, scg, scb, 255),
                    )
                t_mask_draw.text((lx, ly), line, font=font, fill=255)

            grad_text = self._create_linear_gradient(card_w, card_h, cfg["gradient_from"], cfg["gradient_to"])
            frame.paste(grad_text, (card_x, card_y), t_mask)

        else:
            txt_color_hex = cfg.get("text_color", "#FFFFFF")
            tr, tg, tb = self._hex_to_rgb(txt_color_hex)

            # Soft Ambient Glow if enabled
            if cfg.get("glow_enabled"):
                gw_c = self._hex_to_rgba(cfg.get("glow_color", "#00F0FF"), 0.85)
                glow_layer = Image.new("RGBA", (card_w + 60, card_h + 60), (0, 0, 0, 0))
                g_draw = ImageDraw.Draw(glow_layer)
                for idx, line in enumerate(lines):
                    lw = line_widths[idx]
                    lx = (card_w + 60 - lw) // 2
                    ly = 30 + pad_y + idx * line_height
                    g_draw.text((lx, ly), line, font=font, fill=gw_c, stroke_width=2, stroke_fill=gw_c)
                glow_blurred = glow_layer.filter(ImageFilter.GaussianBlur(radius=8))
                frame.paste(glow_blurred, (card_x - 30, card_y - 30), glow_blurred)

            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (self._width - lw) // 2
                ly = text_origin_y + i * line_height

                if cfg.get("shadow_enabled", True):
                    draw.text((lx + 3, ly + 4), line, font=font, fill=(0, 0, 0, 220))

                sw = cfg.get("stroke_width", 0) if cfg.get("stroke_enabled") else 0
                sc = self._hex_to_rgba(cfg.get("stroke_color", "#000000")) if sw > 0 else None

                draw.text(
                    (lx, ly),
                    line,
                    font=font,
                    fill=(tr, tg, tb, 255),
                    stroke_width=sw,
                    stroke_fill=sc,
                )

        return frame

    async def render_hook(
        self,
        video_path: str,
        hook_text: str,
        output_path: str,
        hook_style: str = "skia_impact_badge",
        style_config: Optional[dict] = None,
    ) -> str:
        """Render Hook overlay onto video for the first 3 seconds with smooth pop animation."""
        if not hook_text or not hook_text.strip():
            import shutil
            shutil.copy2(video_path, output_path)
            return output_path

        duration = 3.0
        if style_config and style_config.get("duration"):
            try:
                duration = float(style_config["duration"])
            except Exception:
                duration = 3.0

        tmp_dir = tempfile.mkdtemp(prefix="skia_hook_")
        png_path = os.path.join(tmp_dir, "hook_frame.png")

        try:
            # 1. Generate full-resolution 1080x1920 overlay PNG
            overlay_img = self.generate_hook_frame(hook_text, hook_style=hook_style, style_config=style_config)
            overlay_img.save(png_path, format="PNG")

            # 2. FFmpeg overlay with smooth alpha fade
            fade_out_st = max(0.0, duration - 0.35)
            fade_out_dur = min(0.35, duration / 2)
            filter_complex = (
                f"[1:v]format=rgba,"
                f"fade=t=in:st=0:d=0.35:alpha=1,"
                f"fade=t=out:st={fade_out_st:.3f}:d={fade_out_dur:.3f}:alpha=1[hook];"
                f"[0:v][hook]overlay=x=0:y=0:enable='between(t,0,{duration})'[outv]"
            )

            from src.infrastructure.gpu_encoder import get_video_encoder_args
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-loop", "1",
                "-t", str(duration + 1.0),
                "-i", png_path,
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "0:a?",
                *get_video_encoder_args("medium"),
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                output_path,
            ]

            logger.info(f"skia_hook: rendering '{hook_style}' ({duration}s) → {os.path.basename(output_path)}")
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=120
            )

            if result.returncode != 0:
                logger.error(f"skia_hook ffmpeg failed: {result.stderr[-350:]}")
                import shutil
                shutil.copy2(video_path, output_path)
            else:
                logger.info(f"skia_hook: successfully burned → {output_path}")

            return output_path

        except Exception as e:
            logger.error(f"skia_hook exception: {e}")
            import shutil
            shutil.copy2(video_path, output_path)
            return output_path

        finally:
            if os.path.exists(png_path):
                try:
                    os.remove(png_path)
                except OSError:
                    pass
            if os.path.exists(tmp_dir):
                try:
                    os.rmdir(tmp_dir)
                except OSError:
                    pass
