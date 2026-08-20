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
        candidates = []

        for fdir in search_dirs:
            if not fdir or not os.path.exists(fdir):
                continue
            for file_name in os.listdir(fdir):
                if not file_name.lower().endswith((".ttf", ".otf")):
                    continue
                clean_name = file_name.replace(" ", "").replace("-", "").lower()
                full_path = os.path.join(fdir, file_name)

                if family_clean in clean_name:
                    if font_weight.lower() in clean_name:
                        try:
                            return ImageFont.truetype(full_path, size=size)
                        except Exception:
                            pass
                    candidates.append(full_path)

        if candidates:
            try:
                return ImageFont.truetype(candidates[0], size=size)
            except Exception:
                pass

        # Fallback fonts in priority order
        fallbacks = [
            "Anton-Regular.ttf",
            "Poppins-Bold.ttf",
            "Montserrat-Variable.ttf",
            "Inter-Variable.ttf",
            "Roboto-Bold.ttf",
        ]
        for fdir in search_dirs:
            if not fdir or not os.path.exists(fdir):
                continue
            for fb in fallbacks:
                fb_path = os.path.join(fdir, fb)
                if os.path.exists(fb_path):
                    try:
                        return ImageFont.truetype(fb_path, size=size)
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
        clean_key = hook_style
        if clean_key not in SKIA_HOOK_PRESETS and f"skia_{clean_key}" in SKIA_HOOK_PRESETS:
            clean_key = f"skia_{clean_key}"
        cfg = dict(SKIA_HOOK_PRESETS.get(clean_key, SKIA_HOOK_PRESETS["skia_impact_badge"]))

        # Normalize style_config overrides (support both camelCase and snake_case)
        if style_config:
            if style_config.get("fontSize") or style_config.get("font_size"):
                cfg["font_size"] = int(style_config.get("fontSize") or style_config.get("font_size"))
            if style_config.get("fontFamily") or style_config.get("font_family"):
                cfg["font_family"] = str(style_config.get("fontFamily") or style_config.get("font_family"))
            if style_config.get("color") or style_config.get("text_color"):
                cfg["text_color"] = str(style_config.get("color") or style_config.get("text_color"))
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

        font_size = int(cfg.get("font_size", 56))
        font = self._resolve_font(cfg.get("font_family", "Anton"), cfg.get("font_weight", "Bold"), font_size)

        # Wrap text (max 880px for 1080px canvas)
        max_text_width = int(self._width * 0.82)
        lines = self._wrap_text(display_text, font, max_text_width)
        if not lines:
            return Image.new("RGBA", (self._width, self._height), (0, 0, 0, 0))

        # Calculate bounding box of all lines
        line_height = int(font_size * 1.24)
        line_widths = [font.getbbox(line)[2] - font.getbbox(line)[0] for line in lines]
        total_text_width = max(line_widths)
        total_text_height = line_height * len(lines)

        # Padding & Card dimensions
        pad_x = cfg.get("bg_padding_x", 36)
        pad_y = cfg.get("bg_padding_y", 20)
        card_w = total_text_width + pad_x * 2
        card_h = total_text_height + pad_y * 2
        card_radius = cfg.get("bg_radius", 16)
        if card_radius >= 999:
            card_radius = card_h // 2

        # Card center position
        pos_y_pct = cfg.get("position_y", 38)
        card_x = (self._width - card_w) // 2
        card_y = int(self._height * (pos_y_pct / 100) - card_h / 2)

        # Base 1080x1920 Canvas
        frame = Image.new("RGBA", (self._width, self._height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)

        # ── 1. Draw Card Background ──
        if cfg.get("bg_gradient_from") and cfg.get("bg_gradient_to"):
            # Gradient Pill Card (e.g. skia_impact_badge)
            grad_img = self._create_linear_gradient(card_w, card_h, cfg["bg_gradient_from"], cfg["bg_gradient_to"])
            mask = Image.new("L", (card_w, card_h), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([0, 0, card_w, card_h], radius=card_radius, fill=255)

            # Bottom 3D shadow for impact badge
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

            # Outer Shadow / Glow
            if cfg.get("bg_shadow_blur") and cfg.get("bg_shadow_color"):
                sh_rgba = self._hex_to_rgba(cfg["bg_shadow_color"], 0.6)
                draw.rounded_rectangle(
                    [card_x - 4, card_y - 2, card_x + card_w + 4, card_y + card_h + 8],
                    radius=card_radius + 4,
                    fill=sh_rgba,
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

            # Corner accents for Cyberpunk style
            if cfg.get("corner_accents"):
                accent_c = (255, 0, 127, 255)  # Hot Pink
                bracket_sz = 14
                # Top-Left Bracket
                draw.line([card_x - 4, card_y - 4, card_x + bracket_sz, card_y - 4], fill=accent_c, width=3)
                draw.line([card_x - 4, card_y - 4, card_x - 4, card_y + bracket_sz], fill=accent_c, width=3)
                # Bottom-Right Bracket
                draw.line([card_x + card_w + 4, card_y + card_h + 4, card_x + card_w - bracket_sz, card_y + card_h + 4], fill=accent_c, width=3)
                draw.line([card_x + card_w + 4, card_y + card_h + 4, card_x + card_w + 4, card_y + card_h - bracket_sz], fill=accent_c, width=3)

        # ── 2. Draw Text ──
        text_origin_y = card_y + pad_y

        if cfg.get("is_glitch_rgb"):
            # 3-Layer RGB Split Glitch (Red left, Cyan right, White center)
            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (self._width - lw) // 2
                ly = text_origin_y + i * line_height
                # Red left channel
                draw.text((lx - 4, ly), line, font=font, fill=(255, 0, 0, 200))
                # Cyan right channel
                draw.text((lx + 4, ly), line, font=font, fill=(0, 255, 255, 200))
                # White main center text with black stroke
                draw.text((lx, ly), line, font=font, fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0, 255))

        elif cfg.get("gradient_enabled") and cfg.get("gradient_from") and cfg.get("gradient_to"):
            # Text Linear Gradient Mask
            t_mask = Image.new("L", (card_w, card_h), 0)
            t_mask_draw = ImageDraw.Draw(t_mask)

            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (card_w - lw) // 2
                ly = pad_y + i * line_height

                # Drop shadow behind gradient text
                draw.text((card_x + lx + 2, card_y + ly + 4), line, font=font, fill=(0, 0, 0, 220))

                # Stroke if enabled
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
            # Solid Color Text
            txt_color_hex = cfg.get("text_color", "#FFFFFF")
            tr, tg, tb = self._hex_to_rgb(txt_color_hex)

            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (self._width - lw) // 2
                ly = text_origin_y + i * line_height

                # Shadow
                if cfg.get("shadow_enabled", True):
                    draw.text((lx + 3, ly + 4), line, font=font, fill=(0, 0, 0, 220))

                # Glow
                if cfg.get("glow_enabled"):
                    gw_c = self._hex_to_rgba(cfg.get("glow_color", "#00F0FF"), 0.6)
                    gw_sz = max(4, cfg.get("glow_size", 14) // 2)
                    draw.text((lx, ly), line, font=font, fill=gw_c, stroke_width=gw_sz, stroke_fill=gw_c)

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

            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-loop", "1",
                "-t", str(duration + 1.0),
                "-i", png_path,
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                "-c:a", "copy",
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
