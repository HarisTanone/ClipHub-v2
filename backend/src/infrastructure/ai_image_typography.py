"""AI Image Typography & Aesthetic Layout Engine.

Provides Pinterest, editorial magazine, and viral carousel typography presets:
- Minimalist Aesthetic Quote
- Bold Editorial Magazine
- Skena Retro Indie
- Neo-Brutalist Poster
- Luxury Gold & Noir
- Cyberpunk Neon Glow
- Carousel Insight Card
- News Bulletin & Breaking Card
- Poetic Whisper
- Modern Business / Creator Card
- Cinematic Film Still
- Daily Stoic Maxim

Renders text hierarchies (hook, headline/quote, body/bullet, author/handle/signature)
directly onto images or transparent PNG overlays for video compositing.
Zero emoji tolerance.
"""
from __future__ import annotations

import logging
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from src.infrastructure.image_typography_store import (
    DEFAULT_ASPECT_RATIOS,
    DEFAULT_FONTS,
    DEFAULT_TEMPLATES,
    ensure_all_typography_tables,
    get_all_aspect_ratios,
    get_all_typography_fonts,
    get_all_typography_templates,
    get_resolutions_dict,
    get_typography_fonts_dict,
    get_typography_template,
)

logger = logging.getLogger(__name__)

FONT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts"))


class DynamicDict(dict):
    """Dynamic dictionary proxy that resolves lookups live against SQLite database."""

    def __init__(self, fetcher):
        super().__init__()
        self._fetcher = fetcher

    def _sync(self) -> dict:
        try:
            return self._fetcher()
        except Exception:
            return {}

    def get(self, key, default=None):
        return self._sync().get(key, default)

    def __getitem__(self, key):
        data = self._sync()
        if key in data:
            return data[key]
        raise KeyError(key)

    def __contains__(self, key):
        return key in self._sync()

    def keys(self):
        return self._sync().keys()

    def values(self):
        return self._sync().values()

    def items(self):
        return self._sync().items()

    def __iter__(self):
        return iter(self._sync())

    def __len__(self):
        return len(self._sync())


# Dynamically backed by SQLite tables image_typography_fonts and image_canvas_aspect_ratios
AVAILABLE_FONTS: dict[str, str] = DynamicDict(get_typography_fonts_dict)
RESOLUTIONS: dict[str, tuple[int, int]] = DynamicDict(get_resolutions_dict)


@dataclass
class TypographyContent:
    """Text content structure for typography overlay."""

    hook: str = ""                # Category, sub-header, or tag (e.g. "DAILY STOIC", "INSIGHT")
    headline: str = ""            # Main quotation or punchy headline
    body: str = ""                # Extended quote explanation or bullet points
    author: str = ""              # Author, speaker, or creator signature (e.g. "Marcus Aurelius")
    handle: str = ""              # Social media handle (e.g. "@cliperhub")
    slide_index: str = ""         # Slide indicator (e.g. "01 / 05")
    accent_color: str = "#EAB308" # Primary accent hex (gold, cyan, emerald, red)
    template: str = "minimal_quote"
    font_family: str = "auto"
    aspect_ratio: str = "9:16"


def get_font(font_name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a TrueType font by family name with fallback from database configuration."""
    fonts_map = get_typography_fonts_dict()
    file_name = fonts_map.get(font_name)
    if file_name:
        path = os.path.join(FONT_DIR, file_name)
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception as e:
                logger.debug(f"Failed loading font {path}: {e}")

    # Fallback search across directory
    for f in fonts_map.values():
        path = os.path.join(FONT_DIR, f)
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Wrap text to fit within max_width in pixels."""
    if not text:
        return []
    words = text.split()
    lines: list[str] = []
    current_line: list[str] = []

    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
    if current_line:
        lines.append(" ".join(current_line))
    return lines


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: Optional[tuple[int, int, int, int]] = None,
    outline: Optional[tuple[int, int, int, int]] = None,
    width: int = 1,
) -> None:
    """Draw a rounded rectangle with given radius, fill and outline."""
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def _apply_gradient_scrim(
    base: Image.Image,
    top_darkness: float = 0.45,
    bottom_darkness: float = 0.75,
) -> Image.Image:
    """Apply a smooth vertical darkness gradient scrim to enhance text legibility."""
    width, height = base.size
    scrim = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    scrim_draw = ImageDraw.Draw(scrim)

    # Fast gradient sampling in 40 bands
    steps = 40
    step_h = height // steps
    for i in range(steps):
        y0 = i * step_h
        y1 = (i + 1) * step_h if i < steps - 1 else height
        ratio = i / (steps - 1)
        # Smooth interpolation
        alpha = int(255 * (top_darkness + (bottom_darkness - top_darkness) * (ratio ** 1.3)))
        scrim_draw.rectangle([0, y0, width, y1], fill=(10, 10, 14, min(240, alpha)))

    return Image.alpha_composite(base.convert("RGBA"), scrim)


class AIImageTypographyEngine:
    """Typography and Layout rendering engine for aesthetic social cards."""

    @property
    def TEMPLATES(self) -> list[dict[str, Any]]:
        """Active templates loaded dynamically from database."""
        return get_all_typography_templates(include_inactive=False)

    @classmethod
    def get_template_metadata(cls) -> list[dict[str, Any]]:
        """Return list of all template definitions dynamically loaded from database."""
        return get_all_typography_templates(include_inactive=False)

    @classmethod
    def get_available_fonts(cls) -> list[str]:
        """Return list of available font family names."""
        return list(AVAILABLE_FONTS.keys())

    def render_overlay(
        self,
        base_image: Optional[Image.Image],
        content: TypographyContent,
        width: int = 1080,
        height: int = 1920,
    ) -> Image.Image:
        """Render typography directly onto base_image (or create transparent canvas)."""
        aspect = content.aspect_ratio or "9:16"
        res = RESOLUTIONS.get(aspect, (width, height))
        width, height = res

        # 1. Base Canvas
        if base_image:
            # Resize and crop to fill canvas (cover mode)
            base_ratio = base_image.width / base_image.height
            target_ratio = width / height
            if base_ratio > target_ratio:
                # Base is wider, fit height then crop width
                new_h = height
                new_w = int(base_image.width * (height / base_image.height))
            else:
                new_w = width
                new_h = int(base_image.height * (width / base_image.width))
            resized = base_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
            x_crop = (new_w - width) // 2
            y_crop = (new_h - height) // 2
            canvas = resized.crop((x_crop, y_crop, x_crop + width, y_crop + height)).convert("RGBA")
        else:
            # Deep atmospheric dark background
            canvas = Image.new("RGBA", (width, height), (15, 17, 23, 255))

        # 2. Look up template metadata dynamically from database
        template_id = content.template or "minimal_quote"
        template_meta = get_typography_template(template_id)
        if not template_meta:
            all_tpl = get_all_typography_templates(include_inactive=False)
            template_meta = all_tpl[0] if all_tpl else DEFAULT_TEMPLATES[0]

        layout_type = template_meta.get("layout_type") or template_id or "minimal_quote"

        # Apply Template Specific Scrim & Atmosphere
        if layout_type == "luxury_gold":
            canvas = _apply_gradient_scrim(canvas, top_darkness=0.6, bottom_darkness=0.85)
        elif layout_type == "brutalist_poster":
            canvas = _apply_gradient_scrim(canvas, top_darkness=0.4, bottom_darkness=0.7)
        elif layout_type == "cyberpunk_neon":
            canvas = _apply_gradient_scrim(canvas, top_darkness=0.55, bottom_darkness=0.8)
        else:
            canvas = _apply_gradient_scrim(canvas, top_darkness=0.35, bottom_darkness=0.75)

        # 3. Create Draw Context
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Resolve Fonts dynamically from DB template record
        p_font_name = (
            content.font_family
            if content.font_family and content.font_family != "auto" and content.font_family in AVAILABLE_FONTS
            else template_meta.get("primary_font", "Playfair Display")
        )
        s_font_name = template_meta.get("secondary_font", "Inter")

        # Parse accent color from DB template record
        try:
            accent_rgb = ImageColor.getrgb(content.accent_color or template_meta.get("recommended_accent", "#EAB308"))
        except Exception:
            accent_rgb = (234, 179, 8)

        # Dispatch layout renderer based on layout_type
        if layout_type == "minimal_quote":
            self._draw_minimal_quote(draw, width, height, content, p_font_name, s_font_name, accent_rgb)
        elif layout_type == "bold_editorial":
            self._draw_bold_editorial(draw, width, height, content, p_font_name, s_font_name, accent_rgb)
        elif layout_type == "skena_magazine":
            self._draw_skena_magazine(draw, width, height, content, p_font_name, s_font_name, accent_rgb)
        elif layout_type == "brutalist_poster":
            self._draw_brutalist_poster(draw, width, height, content, p_font_name, s_font_name, accent_rgb)
        elif layout_type == "luxury_gold":
            self._draw_luxury_gold(draw, width, height, content, p_font_name, s_font_name, accent_rgb)
        elif layout_type == "cyberpunk_neon":
            self._draw_cyberpunk_neon(draw, width, height, content, p_font_name, s_font_name, accent_rgb)
        elif layout_type == "aesthetic_carousel_card":
            self._draw_carousel_card(draw, width, height, content, p_font_name, s_font_name, accent_rgb)
        elif layout_type == "news_bulletin":
            self._draw_news_bulletin(draw, width, height, content, p_font_name, s_font_name, accent_rgb)
        elif layout_type == "poetic_whisper":
            self._draw_poetic_whisper(draw, width, height, content, p_font_name, s_font_name, accent_rgb)
        elif layout_type == "modern_business":
            self._draw_modern_business(draw, width, height, content, p_font_name, s_font_name, accent_rgb)
        elif layout_type == "cinematic_film":
            self._draw_cinematic_film(draw, width, height, content, p_font_name, s_font_name, accent_rgb)
        elif layout_type == "daily_stoic":
            self._draw_daily_stoic(draw, width, height, content, p_font_name, s_font_name, accent_rgb)
        else:
            self._draw_minimal_quote(draw, width, height, content, p_font_name, s_font_name, accent_rgb)

        return Image.alpha_composite(canvas, overlay)

    # ─── Template Renderers ──────────────────────────────────────────────────

    def _draw_minimal_quote(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        c: TypographyContent,
        p_font: str,
        s_font: str,
        accent: tuple[int, int, int],
    ) -> None:
        margin_x = int(width * 0.1)
        content_w = width - (margin_x * 2)

        # 1. Top Hook Badge
        hook_text = (c.hook or "DAILY WISDOM").upper()
        f_hook = get_font(s_font, int(width * 0.026))
        draw.text((margin_x, int(height * 0.16)), hook_text, font=f_hook, fill=(*accent, 255))

        # Thin rule under hook
        draw.line(
            [(margin_x, int(height * 0.19)), (margin_x + 80, int(height * 0.19))],
            fill=(*accent, 220),
            width=3,
        )

        # 2. Large Quotation Mark
        f_mark = get_font(p_font, int(width * 0.22))
        draw.text((margin_x - 10, int(height * 0.22)), "“", font=f_mark, fill=(*accent, 160))

        # 3. Main Headline / Quotation
        headline = c.headline or "Focus on what is within your control, and make peace with the rest."
        f_main = get_font(p_font, int(width * 0.062))
        lines = _wrap_text(headline, f_main, content_w, draw)

        y_cursor = int(height * 0.35)
        line_height = int(width * 0.085)
        for line in lines[:8]:
            # Subtle drop shadow
            draw.text((margin_x + 2, y_cursor + 2), line, font=f_main, fill=(0, 0, 0, 180))
            draw.text((margin_x, y_cursor), line, font=f_main, fill=(255, 255, 255, 255))
            y_cursor += line_height

        # 4. Optional Body / Sub-text
        if c.body:
            y_cursor += 30
            f_body = get_font(s_font, int(width * 0.034))
            body_lines = _wrap_text(c.body, f_body, content_w, draw)
            for line in body_lines[:4]:
                draw.text((margin_x, y_cursor), line, font=f_body, fill=(210, 215, 225, 230))
                y_cursor += int(width * 0.048)

        # 5. Author Signature & Handle at Bottom
        author = c.author or "Marcus Aurelius"
        handle = c.handle or "@cliperhub"

        f_author = get_font(p_font, int(width * 0.042))
        f_handle = get_font(s_font, int(width * 0.026))

        draw.line(
            [(margin_x, height - int(height * 0.16)), (width - margin_x, height - int(height * 0.16))],
            fill=(255, 255, 255, 60),
            width=1,
        )
        draw.text((margin_x, height - int(height * 0.13)), f"— {author}", font=f_author, fill=(255, 255, 255, 255))
        draw.text((margin_x, height - int(height * 0.08)), handle, font=f_handle, fill=(*accent, 220))

    def _draw_bold_editorial(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        c: TypographyContent,
        p_font: str,
        s_font: str,
        accent: tuple[int, int, int],
    ) -> None:
        margin_x = int(width * 0.08)
        content_w = width - (margin_x * 2)

        # Editorial Top Masthead
        masthead = (c.hook or "MINDSET ARCHIVE").upper()
        f_mast = get_font(p_font, int(width * 0.11))
        draw.text((margin_x, int(height * 0.09)), masthead, font=f_mast, fill=(255, 255, 255, 255))

        # Thin issue date line
        f_sub = get_font(s_font, int(width * 0.025))
        draw.text((margin_x, int(height * 0.17)), "VOLUME 04 // ISSUE 2026 // PERSPECTIVE", font=f_sub, fill=(*accent, 240))
        draw.line([(margin_x, int(height * 0.19)), (width - margin_x, int(height * 0.19))], fill=(255, 255, 255, 90), width=2)

        # Main Headline
        headline = c.headline or "THE HARD TRUTH ABOUT BUILDING UNSTOPPABLE MOMENTUM."
        f_head = get_font(p_font, int(width * 0.082))
        lines = _wrap_text(headline.upper(), f_head, content_w, draw)

        y = int(height * 0.28)
        for line in lines[:6]:
            draw.text((margin_x, y), line, font=f_head, fill=(255, 255, 255, 255))
            y += int(width * 0.10)

        # Body quote
        if c.body:
            y += 40
            f_body = get_font(s_font, int(width * 0.038))
            body_lines = _wrap_text(c.body, f_body, content_w, draw)
            for line in body_lines[:4]:
                draw.text((margin_x, y), line, font=f_body, fill=(200, 205, 215, 230))
                y += int(width * 0.052)

        # Bottom Barcode & Signature
        y_bot = height - int(height * 0.14)
        draw.line([(margin_x, y_bot), (width - margin_x, y_bot)], fill=(255, 255, 255, 90), width=1)
        author = c.author or "HERMES EDITORIAL"
        f_auth = get_font(s_font, int(width * 0.030))
        draw.text((margin_x, y_bot + 25), author.upper(), font=f_auth, fill=(255, 255, 255, 255))

        # Barcode decorative bars
        bx = width - margin_x - 140
        for i in range(16):
            bw = 2 if i % 3 == 0 else 5
            draw.rectangle([bx + (i * 8), y_bot + 20, bx + (i * 8) + bw, y_bot + 65], fill=(255, 255, 255, 200))

    def _draw_skena_magazine(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        c: TypographyContent,
        p_font: str,
        s_font: str,
        accent: tuple[int, int, int],
    ) -> None:
        margin_x = int(width * 0.07)
        content_w = width - (margin_x * 2)

        # Retro Header Pill: REC [00:14:28]
        f_rec = get_font(s_font, int(width * 0.028))
        _draw_rounded_rect(draw, (margin_x, int(height * 0.12), margin_x + 220, int(height * 0.16)), radius=6, fill=(*accent, 220))
        draw.text((margin_x + 18, int(height * 0.128)), "REC [00:14:28]", font=f_rec, fill=(10, 10, 10, 255))

        tag = c.hook or "INDIE / SKENA"
        draw.text((margin_x + 245, int(height * 0.128)), f"# {tag.upper()}", font=f_rec, fill=(255, 255, 255, 230))

        # Main Headline in High Contrast Highlight Box
        headline = c.headline or "Bukan tentang siapa yang tercepat, tapi siapa yang tetap berdiri saat badai lewat."
        f_head = get_font(p_font, int(width * 0.068))
        lines = _wrap_text(headline, f_head, content_w - 60, draw)

        y = int(height * 0.32)
        for line in lines[:6]:
            bbox = draw.textbbox((margin_x + 20, y), line, font=f_head)
            _draw_rounded_rect(
                draw,
                (bbox[0] - 14, bbox[1] - 8, bbox[2] + 14, bbox[3] + 8),
                radius=8,
                fill=(12, 12, 16, 230),
                outline=(*accent, 200),
                width=2,
            )
            draw.text((margin_x + 20, y), line, font=f_head, fill=(255, 255, 255, 255))
            y += int(width * 0.10)

        # Body caption
        if c.body:
            y += 40
            f_body = get_font(s_font, int(width * 0.035))
            blines = _wrap_text(c.body, f_body, content_w, draw)
            for bl in blines[:3]:
                draw.text((margin_x, y), bl, font=f_body, fill=(220, 225, 235, 240))
                y += int(width * 0.048)

        # Footer coordinates
        f_coord = get_font(s_font, int(width * 0.024))
        draw.text(
            (margin_x, height - int(height * 0.09)),
            f"ARCHIVE #{c.slide_index or '01'} • JAKARTA • {c.handle or '@cliperhub'}",
            font=f_coord,
            fill=(*accent, 230),
        )

    def _draw_brutalist_poster(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        c: TypographyContent,
        p_font: str,
        s_font: str,
        accent: tuple[int, int, int],
    ) -> None:
        pad = int(width * 0.05)
        # Heavy Border Frame
        draw.rectangle([pad, pad, width - pad, height - pad], outline=(255, 255, 255, 240), width=4)

        # Crosshair Marks at 4 corners
        draw.text((pad + 10, pad + 8), "+", font=get_font(p_font, 28), fill=(*accent, 255))
        draw.text((width - pad - 26, pad + 8), "+", font=get_font(p_font, 28), fill=(*accent, 255))
        draw.text((pad + 10, height - pad - 36), "+", font=get_font(p_font, 28), fill=(*accent, 255))
        draw.text((width - pad - 26, height - pad - 36), "+", font=get_font(p_font, 28), fill=(*accent, 255))

        # Top Tag Bar
        f_tag = get_font(s_font, int(width * 0.026))
        tag_text = f"SYS.POST // REF_{c.slide_index or '01'} // {c.hook or 'BRUTAL_TRUTH'}".upper()
        draw.text((pad + 40, pad + 35), tag_text, font=f_tag, fill=(*accent, 240))

        # Giant Raw Headline
        headline = (c.headline or "ACTION CURES FEAR. MOTION CURES DOUBT.").upper()
        f_head = get_font(p_font, int(width * 0.082))
        lines = _wrap_text(headline, f_head, width - (pad * 2) - 80, draw)

        y = int(height * 0.28)
        for line in lines[:6]:
            draw.text((pad + 40, y), line, font=f_head, fill=(255, 255, 255, 255))
            y += int(width * 0.11)

        # Neon Highlight Block
        if c.body:
            y += 30
            f_body = get_font(s_font, int(width * 0.036))
            body_lines = _wrap_text(c.body, f_body, width - (pad * 2) - 100, draw)
            b_height = len(body_lines) * int(width * 0.050) + 30
            draw.rectangle(
                [pad + 30, y, width - pad - 30, y + b_height],
                fill=(*accent, 220),
                outline=(255, 255, 255, 255),
                width=2,
            )
            by = y + 15
            for bl in body_lines[:4]:
                draw.text((pad + 45, by), bl, font=f_body, fill=(10, 10, 15, 255))
                by += int(width * 0.050)

        # Bottom Author / ID stamp
        f_stamp = get_font(s_font, int(width * 0.024))
        draw.text(
            (pad + 40, height - pad - 50),
            f"AUTH: {c.author or 'HERMES'} // {c.handle or '@CLIEPRHUB'}",
            font=f_stamp,
            fill=(255, 255, 255, 200),
        )

    def _draw_luxury_gold(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        c: TypographyContent,
        p_font: str,
        s_font: str,
        accent: tuple[int, int, int],
    ) -> None:
        gold = (212, 175, 55)
        # Double Hairline Gold Border
        pad1 = int(width * 0.045)
        pad2 = int(width * 0.055)
        draw.rectangle([pad1, pad1, width - pad1, height - pad1], outline=(*gold, 140), width=1)
        draw.rectangle([pad2, pad2, width - pad2, height - pad2], outline=(*gold, 220), width=2)

        # Spaced Header
        f_top = get_font(s_font, int(width * 0.024))
        top_text = "E X E C U T I V E   P E R S P E C T I V E"
        draw.text((int(width * 0.22), int(height * 0.13)), top_text, font=f_top, fill=(*gold, 230))

        # Thin ornamental divider
        cx = width // 2
        draw.line([(cx - 70, int(height * 0.17)), (cx + 70, int(height * 0.17))], fill=(*gold, 220), width=2)

        # Main Quote
        headline = c.headline or "True wealth is not measured in possessions, but in the quiet control over your own time."
        f_main = get_font(p_font, int(width * 0.058))
        lines = _wrap_text(headline, f_main, int(width * 0.76), draw)

        y = int(height * 0.33)
        for line in lines[:7]:
            draw.text((int(width * 0.12) + 2, y + 2), line, font=f_main, fill=(0, 0, 0, 200))
            draw.text((int(width * 0.12), y), line, font=f_main, fill=(255, 250, 240, 255))
            y += int(width * 0.082)

        # Author Signature with Gold Script Feel
        author = c.author or "Marcus Aurelius"
        f_auth = get_font(p_font, int(width * 0.044))
        draw.text((int(width * 0.12), height - int(height * 0.15)), f"— {author}", font=f_auth, fill=(*gold, 255))

        f_handle = get_font(s_font, int(width * 0.024))
        draw.text((int(width * 0.12), height - int(height * 0.10)), c.handle or "@cliperhub", font=f_handle, fill=(200, 200, 200, 180))

    def _draw_cyberpunk_neon(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        c: TypographyContent,
        p_font: str,
        s_font: str,
        accent: tuple[int, int, int],
    ) -> None:
        cyan = (0, 240, 255)
        magenta = (255, 0, 127)
        margin_x = int(width * 0.08)
        content_w = width - (margin_x * 2)

        # Futuristic Bracket Tag <AI_CORE>
        f_tag = get_font(s_font, int(width * 0.026))
        draw.text((margin_x, int(height * 0.12)), f"< PROTOCOL // {c.hook or 'SYNTHESIS'} >", font=f_tag, fill=(*cyan, 240))

        # Glowing Headline
        headline = c.headline or "The machines do not replace thought. They accelerate intuition."
        f_head = get_font(p_font, int(width * 0.068))
        lines = _wrap_text(headline, f_head, content_w, draw)

        y = int(height * 0.28)
        for line in lines[:6]:
            # Neon Magenta Underglow
            draw.text((margin_x + 3, y + 3), line, font=f_head, fill=(*magenta, 180))
            # Neon Cyan Text
            draw.text((margin_x, y), line, font=f_head, fill=(255, 255, 255, 255))
            y += int(width * 0.095)

        # Technical Grid Underlay Bar
        draw.line([(margin_x, y + 20), (width - margin_x, y + 20)], fill=(*cyan, 180), width=2)
        y += 45

        if c.body:
            f_body = get_font(s_font, int(width * 0.034))
            blines = _wrap_text(c.body, f_body, content_w, draw)
            for bl in blines[:4]:
                draw.text((margin_x, y), bl, font=f_body, fill=(200, 230, 255, 230))
                y += int(width * 0.048)

        # Bottom System Info
        f_bot = get_font(s_font, int(width * 0.024))
        draw.text(
            (margin_x, height - int(height * 0.09)),
            f"SYSTEM: ONLINE • AUTONOMOUS RUN • {c.handle or '@cliperhub'}",
            font=f_bot,
            fill=(*cyan, 220),
        )

    def _draw_carousel_card(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        c: TypographyContent,
        p_font: str,
        s_font: str,
        accent: tuple[int, int, int],
    ) -> None:
        margin_x = int(width * 0.08)
        content_w = width - (margin_x * 2)

        # Top Header: Category Hook & Slide Number (01 / 05)
        f_tag = get_font(s_font, int(width * 0.028))
        f_slide = get_font(p_font, int(width * 0.032))

        tag_text = (c.hook or "CAROUSEL GUIDE").upper()
        draw.text((margin_x, int(height * 0.12)), tag_text, font=f_tag, fill=(*accent, 240))

        slide_txt = c.slide_index or "01 / 05"
        draw.text((width - margin_x - 90, int(height * 0.12)), slide_txt, font=f_slide, fill=(255, 255, 255, 255))

        # Main Question / Hook
        headline = c.headline or "3 Cara Mengubah Kebiasaan Buruk Menjadi Kekuatan Terbesarmu"
        f_head = get_font(p_font, int(width * 0.065))
        lines = _wrap_text(headline, f_head, content_w, draw)

        y = int(height * 0.24)
        for line in lines[:5]:
            draw.text((margin_x, y), line, font=f_head, fill=(255, 255, 255, 255))
            y += int(width * 0.090)

        # 3 Key Insight Pills / Bullets
        bullets = [b.strip() for b in (c.body or "Identifikasi pemicu utama tanpa menghakimi diri sendiri.\nGanti respons otomatis dengan rutinitas mikroskopis 2 menit.\nUkur konsistensi, bukan kesempurnaan harian.").split("\n") if b.strip()]

        y += 40
        f_bullet = get_font(s_font, int(width * 0.034))
        for idx, bullet in enumerate(bullets[:4]):
            # Number Badge Circle
            by = y + 15
            _draw_rounded_rect(draw, (margin_x, by, margin_x + 44, by + 44), radius=22, fill=(*accent, 230))
            draw.text((margin_x + 14, by + 6), str(idx + 1), font=f_tag, fill=(10, 10, 15, 255))

            # Bullet text
            blines = _wrap_text(bullet, f_bullet, content_w - 70, draw)
            ty = by
            for bl in blines:
                draw.text((margin_x + 60, ty), bl, font=f_bullet, fill=(235, 240, 250, 240))
                ty += int(width * 0.046)
            y = max(ty + 20, by + 60)

        # Swipe Indicator Footer
        y_foot = height - int(height * 0.10)
        draw.line([(margin_x, y_foot), (width - margin_x, y_foot)], fill=(255, 255, 255, 70), width=1)
        f_foot = get_font(s_font, int(width * 0.026))
        draw.text((margin_x, y_foot + 25), "GESER KE KIRI UNTUK LANJUTAN ->", font=f_foot, fill=(*accent, 240))
        draw.text((width - margin_x - 140, y_foot + 25), c.handle or "@cliperhub", font=f_foot, fill=(200, 200, 200, 200))

    def _draw_news_bulletin(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        c: TypographyContent,
        p_font: str,
        s_font: str,
        accent: tuple[int, int, int],
    ) -> None:
        margin_x = int(width * 0.07)
        content_w = width - (margin_x * 2)

        # Top Red/Accent Alert Pill
        f_pill = get_font(p_font, int(width * 0.030))
        pill_text = (c.hook or "BREAKING INSIGHT").upper()
        _draw_rounded_rect(draw, (margin_x, int(height * 0.12), margin_x + 260, int(height * 0.165)), radius=4, fill=(*accent, 240))
        draw.text((margin_x + 20, int(height * 0.128)), pill_text, font=f_pill, fill=(255, 255, 255, 255))

        # Giant Impact Headline
        headline = (c.headline or "PERUBAHAN BESAR PADA SISTEM EKONOMI DIGITAL DI DEPAN MATA.").upper()
        f_head = get_font(p_font, int(width * 0.076))
        lines = _wrap_text(headline, f_head, content_w, draw)

        y = int(height * 0.26)
        for line in lines[:6]:
            draw.text((margin_x, y), line, font=f_head, fill=(255, 255, 255, 255))
            y += int(width * 0.096)

        # Explanation box
        if c.body:
            y += 30
            f_body = get_font(s_font, int(width * 0.036))
            blines = _wrap_text(c.body, f_body, content_w - 40, draw)
            bh = len(blines) * int(width * 0.050) + 30
            _draw_rounded_rect(draw, (margin_x, y, width - margin_x, y + bh), radius=6, fill=(15, 17, 23, 210), outline=(255, 255, 255, 60), width=1)
            by = y + 15
            for bl in blines[:4]:
                draw.text((margin_x + 20, by), bl, font=f_body, fill=(230, 235, 245, 255))
                by += int(width * 0.050)

        # Source Footer
        f_src = get_font(s_font, int(width * 0.024))
        draw.text((margin_x, height - int(height * 0.08)), f"SUMBER: HERMES INTELLIGENCE • {c.handle or '@CLIPERHUB'}", font=f_src, fill=(180, 185, 195, 200))

    def _draw_poetic_whisper(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        c: TypographyContent,
        p_font: str,
        s_font: str,
        accent: tuple[int, int, int],
    ) -> None:
        content_w = int(width * 0.78)
        headline = c.headline or "Sometimes the quietest moments are the ones that reshape our entire lives."
        f_main = get_font(p_font, int(width * 0.056))
        lines = _wrap_text(headline, f_main, content_w, draw)

        # Centered ornament at top
        cx = width // 2
        f_ornament = get_font(s_font, int(width * 0.035))
        draw.text((cx - 35, int(height * 0.28)), "* * *", font=f_ornament, fill=(*accent, 220))

        y = int(height * 0.36)
        line_h = int(width * 0.080)
        for line in lines[:7]:
            bbox = draw.textbbox((0, 0), line, font=f_main)
            lw = bbox[2] - bbox[0]
            lx = (width - lw) // 2
            draw.text((lx + 2, y + 2), line, font=f_main, fill=(0, 0, 0, 180))
            draw.text((lx, y), line, font=f_main, fill=(255, 250, 245, 255))
            y += line_h

        # Centered Author
        y += 40
        author = c.author or "Rainer Maria Rilke"
        f_auth = get_font(s_font, int(width * 0.030))
        bbox = draw.textbbox((0, 0), f"— {author}", font=f_auth)
        ax = (width - (bbox[2] - bbox[0])) // 2
        draw.text((ax, y), f"— {author}", font=f_auth, fill=(*accent, 230))

    def _draw_modern_business(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        c: TypographyContent,
        p_font: str,
        s_font: str,
        accent: tuple[int, int, int],
    ) -> None:
        margin_x = int(width * 0.08)
        content_w = width - (margin_x * 2)

        # Profile Pill Header
        f_name = get_font(p_font, int(width * 0.034))
        f_sub = get_font(s_font, int(width * 0.024))

        author = c.author or "Hermes Founder"
        handle = c.handle or "@cliperhub"

        # Avatar circle placeholder
        ay = int(height * 0.14)
        _draw_rounded_rect(draw, (margin_x, ay, margin_x + 56, ay + 56), radius=28, fill=(*accent, 240))
        draw.text((margin_x + 18, ay + 12), author[:1].upper(), font=f_name, fill=(10, 10, 15, 255))

        draw.text((margin_x + 72, ay + 4), author, font=f_name, fill=(255, 255, 255, 255))
        draw.text((margin_x + 72, ay + 32), f"{handle} • Founder", font=f_sub, fill=(160, 165, 175, 220))

        # Main Business Maxim
        headline = c.headline or "Great companies are not built on groundbreaking ideas. They are built on obsessive execution of simple truths."
        f_head = get_font(p_font, int(width * 0.058))
        lines = _wrap_text(headline, f_head, content_w, draw)

        y = int(height * 0.28)
        for line in lines[:7]:
            draw.text((margin_x, y), line, font=f_head, fill=(255, 255, 255, 255))
            y += int(width * 0.080)

        # Metric Bar at Bottom
        y_bar = height - int(height * 0.12)
        draw.line([(margin_x, y_bar), (width - margin_x, y_bar)], fill=(255, 255, 255, 60), width=1)
        f_metric = get_font(s_font, int(width * 0.024))
        draw.text((margin_x, y_bar + 20), "INSIGHT REPORT // VERIFIED BY HERMES AI", font=f_metric, fill=(*accent, 220))

    def _draw_cinematic_film(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        c: TypographyContent,
        p_font: str,
        s_font: str,
        accent: tuple[int, int, int],
    ) -> None:
        # Cinematic Letterbox bars
        bar_h = int(height * 0.12)
        draw.rectangle([0, 0, width, bar_h], fill=(0, 0, 0, 255))
        draw.rectangle([0, height - bar_h, width, height], fill=(0, 0, 0, 255))

        # Top Title in Spaced Serif
        f_title = get_font(p_font, int(width * 0.038))
        title_text = (c.hook or "C I N E M A   V E R I T E").upper()
        bbox = draw.textbbox((0, 0), title_text, font=f_title)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, bar_h + 30), title_text, font=f_title, fill=(255, 255, 255, 220))

        # Dialogue Subtitle at Lower Third
        headline = c.headline or "“We all have two lives. The second begins when we realize we only have one.”"
        f_sub = get_font(s_font, int(width * 0.046))
        lines = _wrap_text(headline, f_sub, int(width * 0.82), draw)

        y = height - bar_h - (len(lines) * int(width * 0.065)) - 40
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=f_sub)
            lx = (width - (bbox[2] - bbox[0])) // 2
            # Black contour outline for film subtitle legibility
            for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
                draw.text((lx + dx, y + dy), line, font=f_sub, fill=(0, 0, 0, 255))
            draw.text((lx, y), line, font=f_sub, fill=(255, 245, 180, 255))
            y += int(width * 0.065)

    def _draw_daily_stoic(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        c: TypographyContent,
        p_font: str,
        s_font: str,
        accent: tuple[int, int, int],
    ) -> None:
        margin_x = int(width * 0.10)
        content_w = width - (margin_x * 2)

        # Roman Numeral & Latin Maxim
        roman = (c.hook or "I. AMOR FATI").upper()
        f_roman = get_font(s_font, int(width * 0.030))
        draw.text((margin_x, int(height * 0.18)), roman, font=f_roman, fill=(*accent, 240))

        draw.line([(margin_x, int(height * 0.22)), (margin_x + 90, int(height * 0.22))], fill=(*accent, 240), width=2)

        # Maxim Quote
        headline = c.headline or "Do not seek for things to happen the way you want them to; wish that what happens happens the way it happens: then you will be happy."
        f_main = get_font(p_font, int(width * 0.056))
        lines = _wrap_text(headline, f_main, content_w, draw)

        y = int(height * 0.29)
        for line in lines[:8]:
            draw.text((margin_x + 2, y + 2), line, font=f_main, fill=(0, 0, 0, 180))
            draw.text((margin_x, y), line, font=f_main, fill=(250, 250, 250, 255))
            y += int(width * 0.082)

        # Stoic Author & Modern takeaway
        author = c.author or "Epictetus, Enchiridion"
        f_auth = get_font(p_font, int(width * 0.038))
        draw.text((margin_x, height - int(height * 0.16)), f"— {author}", font=f_auth, fill=(*accent, 255))

        f_handle = get_font(s_font, int(width * 0.024))
        draw.text((margin_x, height - int(height * 0.10)), c.handle or "@cliperhub", font=f_handle, fill=(180, 180, 185, 200))


typography_engine = AIImageTypographyEngine()

