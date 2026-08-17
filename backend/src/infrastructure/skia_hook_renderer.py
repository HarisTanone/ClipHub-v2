"""SkiaHookRenderer — High-definition GPU/Canvas-style hook overlay rendering.

Renders rich graphical hook overlays that match the frontend Skia Canvas previews 1:1:
- Gradients (linear, multi-color, metallic)
- Glassmorphic / frosted rounded pill containers with borders and backdrop blur
- Multi-pass text glow and 3D drop shadows
- High-impact Google Fonts (Anton, Montserrat, Outfit, Bebas Neue, Inter, etc.)
- Smooth compositing over the first N seconds of video using FFmpeg
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


# ─── Skia Hook Presets Specifications ─────────────────────────────────────────

SKIA_HOOK_PRESETS: Dict[str, Dict[str, Any]] = {
    "skia_impact_badge": {
        "name": "Impact Hazard",
        "font_family": "Anton",
        "font_size": 60,
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
        "position_y": 38,
        "uppercase": True,
        "duration": 3.0,
    },
    "skia_neon_cyberpunk": {
        "name": "Neon Cyberpunk",
        "font_family": "Montserrat",
        "font_size": 54,
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
        "font_family": "Inter",
        "font_size": 48,
        "font_weight": "800",
        "text_color": "#FFFFFF",
        "bg_color": "#FFFFFF",
        "bg_opacity": 0.22,
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
        "font_size": 54,
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
        "font_size": 54,
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
        "font_size": 54,
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
        "font_size": 56,
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
        "font_size": 56,
        "font_weight": "700",
        "text_color": "#FFFFFF",
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
        "font_family": "Inter",
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
}


class SkiaHookRenderer:
    """Renderer for high-end Skia-style Hook overlays using high-DPI Pillow canvas & FFmpeg."""

    def __init__(self, font_dir: str = "assets/fonts", width: int = 1080, height: int = 1920):
        self._font_dir = font_dir
        self._width = width
        self._height = height

    def _hex_to_rgb(self, hex_code: str) -> Tuple[int, int, int]:
        """Convert #RGB or #RRGGBB to (r, g, b)."""
        hex_code = hex_code.lstrip("#")
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
        """Find best matching TrueType font file in font_dir."""
        family_clean = font_family.replace(" ", "").replace("-", "").lower()
        candidates = []

        if os.path.exists(self._font_dir):
            for file_name in os.listdir(self._font_dir):
                if not file_name.lower().endswith((".ttf", ".otf")):
                    continue
                clean_name = file_name.replace(" ", "").replace("-", "").lower()
                full_path = os.path.join(self._font_dir, file_name)

                # Direct match
                if family_clean in clean_name:
                    if font_weight.lower() in clean_name:
                        return ImageFont.truetype(full_path, size=size)
                    candidates.append(full_path)

        if candidates:
            return ImageFont.truetype(candidates[0], size=size)

        # Fallback fonts in priority order
        fallbacks = [
            "Anton-Regular.ttf",
            "Poppins-Bold.ttf",
            "Inter-Variable.ttf",
            "Montserrat-Variable.ttf",
            "Roboto-Bold.ttf",
        ]
        for fb in fallbacks:
            fb_path = os.path.join(self._font_dir, fb)
            if os.path.exists(fb_path):
                return ImageFont.truetype(fb_path, size=size)

        # Standard PIL default
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
            # measure width
            bbox = font.getbbox(test_line)
            w = bbox[2] - bbox[0]
            if w <= max_width or not current_words:
                current_words.append(word)
            else:
                lines.append(" ".join(current_words))
                current_words = [word]

        if current_words:
            lines.append(" ".join(current_words))

        # Balance lines if 2 lines
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
        grad = Image.new("RGBA", (width, height), (0, 0, 0, 0))
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
        """Generate a 1080x1920 RGBA transparent frame containing the complete Skia hook."""
        cfg = dict(SKIA_HOOK_PRESETS.get(hook_style, SKIA_HOOK_PRESETS["skia_impact_badge"]))

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

        font_size = int(cfg.get("font_size", 54))
        font = self._resolve_font(cfg.get("font_family", "Anton"), cfg.get("font_weight", "Bold"), font_size)

        # Wrap text (max 880px for 1080px canvas)
        max_text_width = int(self._width * 0.82)
        lines = self._wrap_text(display_text, font, max_text_width)
        if not lines:
            return Image.new("RGBA", (self._width, self._height), (0, 0, 0, 0))

        # Calculate bounding box of all lines
        line_height = int(font_size * 1.22)
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
            # Create rounded mask
            mask = Image.new("L", (card_w, card_h), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([(0, 0), (card_w, card_h)], radius=card_radius, fill=255)

            # Shadow under card
            shadow_color = cfg.get("bg_shadow_color", "#000000")
            shadow_offset = cfg.get("bg_shadow_offset_y", 6)
            sr, sg, sb = self._hex_to_rgb(shadow_color)
            shadow_layer = Image.new("RGBA", (card_w + 20, card_h + shadow_offset + 20), (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow_layer)
            shadow_draw.rounded_rectangle(
                [(10, 10 + shadow_offset), (card_w + 10, card_h + shadow_offset + 10)],
                radius=card_radius,
                fill=(sr, sg, sb, 200),
            )
            frame.paste(shadow_layer, (card_x - 10, card_y - 10), shadow_layer)

            # Paste gradient card
            frame.paste(grad_img, (card_x, card_y), mask)

        elif cfg.get("bg_color"):
            # Solid / Glassmorphic Card
            bg_color_hex = cfg.get("bg_color", "#0A0F1E")
            bg_opacity = float(cfg.get("bg_opacity", 0.75))
            bg_rgba = self._hex_to_rgba(bg_color_hex, bg_opacity)

            # Soft drop shadow under card
            shadow_blur = cfg.get("bg_shadow_blur", 0)
            if shadow_blur > 0:
                shadow_img = Image.new("RGBA", (card_w + shadow_blur * 2, card_h + shadow_blur * 2), (0, 0, 0, 0))
                s_draw = ImageDraw.Draw(shadow_img)
                s_draw.rounded_rectangle(
                    [(shadow_blur, shadow_blur), (card_w + shadow_blur, card_h + shadow_blur)],
                    radius=card_radius,
                    fill=(0, 0, 0, 180),
                )
                shadow_img = shadow_img.filter(ImageFilter.GaussianBlur(shadow_blur / 2))
                frame.paste(shadow_img, (card_x - shadow_blur, card_y - shadow_blur + 4), shadow_img)

            # Card fill
            card_img = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
            c_draw = ImageDraw.Draw(card_img)
            c_draw.rounded_rectangle([(0, 0), (card_w, card_h)], radius=card_radius, fill=bg_rgba)

            # Card border
            if cfg.get("bg_border_color"):
                b_color = self._hex_to_rgba(cfg["bg_border_color"], 0.9)
                b_width = cfg.get("bg_border_width", 2)
                c_draw.rounded_rectangle([(0, 0), (card_w, card_h)], radius=card_radius, outline=b_color, width=b_width)

            # Cyberpunk Corner Accents (skia_neon_cyberpunk)
            if cfg.get("corner_accents"):
                accent_color = self._hex_to_rgba("#FF007F", 1.0)
                # top-left
                c_draw.line([(0, 0), (14, 0)], fill=accent_color, width=3)
                c_draw.line([(0, 0), (0, 14)], fill=accent_color, width=3)
                # bottom-right
                c_draw.line([(card_w - 14, card_h - 1), (card_w, card_h - 1)], fill=accent_color, width=3)
                c_draw.line([(card_w - 1, card_h - 14), (card_w - 1, card_h)], fill=accent_color, width=3)

            frame.paste(card_img, (card_x, card_y), card_img)

        # ── 2. Draw Text (with Glow / Shadow / Gradient) ──
        text_origin_y = card_y + pad_y

        # Glow layer
        if cfg.get("glow_enabled") and cfg.get("glow_color"):
            glow_hex = cfg["glow_color"]
            glow_size = cfg.get("glow_size", 20)
            glow_layer = Image.new("RGBA", (self._width, self._height), (0, 0, 0, 0))
            g_draw = ImageDraw.Draw(glow_layer)
            gr, gg, gb = self._hex_to_rgb(glow_hex)

            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (self._width - lw) // 2
                ly = text_origin_y + i * line_height
                g_draw.text((lx, ly), line, font=font, fill=(gr, gg, gb, 220))

            glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(glow_size / 2))
            frame.paste(glow_layer, (0, 0), glow_layer)

        # Text Drop Shadow
        if cfg.get("shadow_enabled"):
            sh_hex = cfg.get("shadow_color", "#000000")
            sr, sg, sb = self._hex_to_rgb(sh_hex)
            sh_blur = cfg.get("shadow_blur", 8)
            sh_layer = Image.new("RGBA", (self._width, self._height), (0, 0, 0, 0))
            sh_draw = ImageDraw.Draw(sh_layer)

            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (self._width - lw) // 2 + 2
                ly = text_origin_y + i * line_height + 4
                sh_draw.text((lx, ly), line, font=font, fill=(sr, sg, sb, 200))

            if sh_blur > 0:
                sh_layer = sh_layer.filter(ImageFilter.GaussianBlur(sh_blur / 2))
            frame.paste(sh_layer, (0, 0), sh_layer)

        # Text Fill (Gradient or Solid)
        if cfg.get("gradient_enabled") and cfg.get("gradient_from") and cfg.get("gradient_to"):
            # Text Gradient Mask
            t_mask = Image.new("L", (card_w, card_h), 0)
            t_mask_draw = ImageDraw.Draw(t_mask)

            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (card_w - lw) // 2
                ly = pad_y + i * line_height
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
            # Solid Text
            txt_color_hex = cfg.get("text_color", "#FFFFFF")
            tr, tg, tb = self._hex_to_rgb(txt_color_hex)

            for i, line in enumerate(lines):
                lw = line_widths[i]
                lx = (self._width - lw) // 2
                ly = text_origin_y + i * line_height
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
        """Render Skia Hook onto video for the first 3 seconds with smooth pop animation."""
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

            # 2. FFmpeg overlay with alpha fade expression
            alpha_expr = (
                f"if(lt(t\\,0.35)\\,t/0.35\\,"
                f"if(gt(t\\,{duration - 0.35})\\,({duration}-t)/0.35\\,1))"
            )

            # Smooth pop-in scale & position filter
            filter_complex = (
                f"[1:v]format=rgba,colorchannelmixer=aa='{alpha_expr}'[hook];"
                f"[0:v][hook]overlay=x=0:y=0:enable='between(t,0,{duration})'[outv]"
            )

            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
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
            # Cleanup temp
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
