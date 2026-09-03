"""Server-side CTA (Call to Action) end-card rendering via Pillow & FFmpeg overlay.

Renders a pixel-perfect, high-definition Call to Action end-card matching
the frontend StyleEditorModal and Remotion CTALayer 1:1:
- Glassmorphic rounded card container with ambient glow and drop shadow
- Left column: Bold headline + subtitle / social handle
- Right column: Rounded pill button with clean vector icon (no emojis) and action text
- Full support for 'card', 'both' (text + icon), and 'text' modes
- Responsive scaling for 9:16 portrait, 16:9 landscape, and 1:1 square videos
- Smooth entry animations (slide_up, pop_in, fade_bounce, glow_pulse, glitch)
"""
import asyncio
import json
import logging
import math
import os
import re
import subprocess
import tempfile
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

DEFAULT_CTA_CONFIG = {
    "enabled": False,
    "ctaType": "card",
    "template": "follow_badge",
    "duration": 3.0,
    "text": "Jangan lupa follow untuk tips berikutnya!",
    "headline": "Follow For More",
    "subhead": "@yourchannel",
    "buttonText": "FOLLOW",
    "selectedIcon": "tiktok",
    "socialPlatform": "tiktok",
    "socialHandle": "@yourchannel",
    "position": "bottom",
    "bgBox": True,
    "animation": "slide_up",
    "primaryColor": "#10B981",
    "textColor": "#FFFFFF",
    "backgroundColor": "#0F172A",
    "bgOpacity": 90,
    "fontSize": 28,
    "fontFamily": "Poppins",
    "fontWeight": "700",
    "showIcon": True,
    "showArrow": True,
    "avatarUrl": None,
}


def _is_enabled(value) -> bool:
    """Truthy check that also handles string representations."""
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(value)


def _resolve_font_path(font_family: str, fonts_dir: str = "assets/fonts") -> Optional[str]:
    """Find TTF/OTF font file across assets and system fonts."""
    search_dirs = [
        fonts_dir,
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../../assets/fonts")),
        os.path.abspath("assets/fonts"),
        os.path.abspath("backend/assets/fonts"),
        "/usr/share/fonts/truetype",
        "/usr/share/fonts",
        "/opt/homebrew/share/fonts",
        "/Library/Fonts",
    ]
    family_clean = (font_family or "Poppins").replace(" ", "")
    candidates = [
        f"{family_clean}-Bold.ttf",
        f"{family_clean}-Regular.ttf",
        f"{family_clean}-Variable.ttf",
        f"{family_clean}.ttf",
        f"{font_family}-Bold.ttf",
        f"{font_family}-Regular.ttf",
        f"{font_family}.ttf",
    ]
    for d in search_dirs:
        if d and os.path.isdir(d):
            for cand in candidates:
                p = os.path.join(d, cand)
                if os.path.exists(p):
                    return p
    return None


def hex_to_rgba(hex_code: str, alpha: int = 255) -> tuple[int, int, int, int]:
    """Convert hex color string (#RGB, #RRGGBB) to RGBA tuple."""
    h = str(hex_code or "#FFFFFF").lstrip("#")
    if len(h) == 3:
        h = "".join([c * 2 for c in h])
    if len(h) < 6:
        h = h.ljust(6, "0")
    try:
        rgb = tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    except (ValueError, TypeError):
        rgb = (255, 255, 255)
    return (rgb[0], rgb[1], rgb[2], int(alpha))


def normalise_cta_config(config: Optional[dict]) -> dict:
    """Coerce raw CTA config dictionary into safe, validated dict supporting camelCase & snake_case."""
    cfg = config or {}
    try:
        dur = float(
            cfg.get("duration")
            if cfg.get("duration") is not None
            else (cfg.get("duration_sec") if cfg.get("duration_sec") is not None else 3.0)
        )
    except (TypeError, ValueError):
        dur = 3.0
    dur = max(1.0, min(6.0, dur))

    try:
        font_size = int(cfg.get("fontSize") or cfg.get("font_size") or 28)
    except (TypeError, ValueError):
        font_size = 28
    font_size = max(16, min(60, font_size))

    try:
        raw_opacity = cfg.get("bgOpacity") if cfg.get("bgOpacity") is not None else cfg.get("bg_opacity")
        bg_opacity = int(raw_opacity if raw_opacity is not None else 90)
    except (TypeError, ValueError):
        bg_opacity = 90
    bg_opacity = max(0, min(100, bg_opacity))

    cta_type = str(cfg.get("ctaType") or cfg.get("cta_type") or cfg.get("mode") or "card").strip().lower()
    if cta_type not in ("card", "text", "both"):
        cta_type = "card"

    text_msg = str(cfg.get("text") or cfg.get("headline") or DEFAULT_CTA_CONFIG["text"]).strip()
    headline = str(cfg.get("headline") or cfg.get("text") or DEFAULT_CTA_CONFIG["headline"]).strip()
    subhead = str(cfg.get("subhead") or "").strip()
    button_text = str(cfg.get("buttonText") or cfg.get("button_text") or DEFAULT_CTA_CONFIG["buttonText"]).strip()
    social_handle = str(cfg.get("socialHandle") or cfg.get("social_handle") or cfg.get("handle") or "").strip()

    template = str(cfg.get("template") or "follow_badge")
    if template not in ("follow_badge", "like_share", "link_bio", "subscribe_pill", "comment_prompt", "custom_card"):
        template = "follow_badge"

    position = str(cfg.get("position") or "bottom")
    if position not in ("bottom", "center", "lower-third", "top"):
        position = "bottom"

    animation = str(cfg.get("animation") or "slide_up")
    if animation not in ("slide_up", "pop_in", "fade_bounce", "glow_pulse", "glitch"):
        animation = "slide_up"

    selected_icon = str(cfg.get("selectedIcon") or cfg.get("selected_icon") or "tiktok")
    if selected_icon not in ("tiktok", "instagram", "youtube", "bell", "link", "share", "message", "zap", "user_plus", "heart", "star"):
        selected_icon = "tiktok"

    bg_box = cfg.get("bgBox") if cfg.get("bgBox") is not None else cfg.get("bg_box")
    if bg_box is not None:
        bg_box = _is_enabled(bg_box)
    else:
        bg_box = True

    return {
        "enabled": _is_enabled(cfg.get("enabled")),
        "ctaType": cta_type,
        "template": template,
        "duration": dur,
        "text": text_msg,
        "headline": headline,
        "subhead": subhead,
        "buttonText": button_text,
        "selectedIcon": selected_icon,
        "socialPlatform": str(cfg.get("socialPlatform") or cfg.get("social_platform") or cfg.get("type") or "tiktok"),
        "socialHandle": social_handle,
        "position": position,
        "bgBox": bg_box,
        "animation": animation,
        "primaryColor": str(cfg.get("primaryColor") or cfg.get("primary_color") or "#10B981"),
        "textColor": str(cfg.get("textColor") or cfg.get("text_color") or "#FFFFFF"),
        "backgroundColor": str(cfg.get("backgroundColor") or cfg.get("background_color") or "#0F172A"),
        "bgOpacity": bg_opacity,
        "fontSize": font_size,
        "fontFamily": str(cfg.get("fontFamily") or cfg.get("font_family") or "Poppins"),
        "fontWeight": str(cfg.get("fontWeight") or cfg.get("font_weight") or "700"),
        "showIcon": bool(cfg.get("showIcon", cfg.get("show_icon", True))),
        "showArrow": bool(cfg.get("showArrow", cfg.get("show_arrow", True))),
        "avatarUrl": cfg.get("avatarUrl") or cfg.get("avatar_url") or None,
    }


def draw_vector_icon(
    draw: ImageDraw.ImageDraw,
    icon_name: str,
    center_x: int,
    center_y: int,
    size: int = 24,
    color: tuple[int, int, int, int] = (255, 255, 255, 255),
) -> None:
    """Draw anti-aliased clean vector icons (No emojis)."""
    half = size // 2
    r = max(4, half - 2)
    
    if icon_name in ("follow_badge", "plus", "user_plus"):
        # Plus icon (+)
        draw.line([(center_x - r, center_y), (center_x + r, center_y)], fill=color, width=max(2, size // 7))
        draw.line([(center_x, center_y - r), (center_x, center_y + r)], fill=color, width=max(2, size // 7))
    elif icon_name in ("subscribe_pill", "bell", "youtube"):
        # Bell icon
        draw.arc([center_x - r, center_y - r, center_x + r, center_y + r - 4], start=180, end=0, fill=color, width=max(2, size // 8))
        draw.line([(center_x - r - 2, center_y + r - 4), (center_x + r + 2, center_y + r - 4)], fill=color, width=max(2, size // 8))
        draw.ellipse([center_x - 3, center_y + r - 2, center_x + 3, center_y + r + 2], fill=color)
    elif icon_name in ("link_bio", "link", "arrow_up_right"):
        # Arrow Up-Right (↗)
        w = max(2, size // 8)
        draw.line([(center_x - r + 2, center_y + r - 2), (center_x + r - 2, center_y - r + 2)], fill=color, width=w)
        draw.line([(center_x, center_y - r + 2), (center_x + r - 2, center_y - r + 2)], fill=color, width=w)
        draw.line([(center_x + r - 2, center_y), (center_x + r - 2, center_y - r + 2)], fill=color, width=w)
    elif icon_name in ("like_share", "share"):
        # Share icon
        draw.arc([center_x - r, center_y - r, center_x + r, center_y + r], start=90, end=270, fill=color, width=max(2, size // 8))
        draw.polygon([(center_x + r, center_y - r), (center_x + r - 6, center_y - r - 6), (center_x + r - 6, center_y - r + 6)], fill=color)
    elif icon_name in ("comment_prompt", "message"):
        # Message bubble
        draw.rounded_rectangle([center_x - r, center_y - r + 2, center_x + r, center_y + r - 2], radius=4, fill=color)
        draw.polygon([(center_x - r + 2, center_y + r - 2), (center_x - r + 2, center_y + r + 4), (center_x - r + 8, center_y + r - 2)], fill=color)
    elif icon_name in ("custom_card", "zap"):
        # Lightning Bolt (Zap)
        pts = [
            (center_x + 2, center_y - r),
            (center_x - r + 2, center_y + 1),
            (center_x, center_y + 1),
            (center_x - 2, center_y + r),
            (center_x + r - 2, center_y - 1),
            (center_x, center_y - 1),
        ]
        draw.polygon(pts, fill=color)
    elif icon_name == "heart":
        # Heart
        draw.ellipse([center_x - r, center_y - r, center_x, center_y], fill=color)
        draw.ellipse([center_x, center_y - r, center_x + r, center_y], fill=color)
        draw.polygon([(center_x - r, center_y - 2), (center_x + r, center_y - 2), (center_x, center_y + r)], fill=color)
    elif icon_name == "star":
        # Star
        draw.polygon([
            (center_x, center_y - r),
            (center_x + 3, center_y - 3),
            (center_x + r, center_y - 2),
            (center_x + 5, center_y + 3),
            (center_x + 7, center_y + r),
            (center_x, center_y + 5),
            (center_x - 7, center_y + r),
            (center_x - 5, center_y + 3),
            (center_x - r, center_y - 2),
            (center_x - 3, center_y - 3),
        ], fill=color)
    else:
        # Default Plus (+)
        draw.line([(center_x - r, center_y), (center_x + r, center_y)], fill=color, width=max(2, size // 7))
        draw.line([(center_x, center_y - r), (center_x, center_y + r)], fill=color, width=max(2, size // 7))


def render_cta_overlay_image(
    width: int = 1080,
    height: int = 1920,
    cta_config: Optional[dict] = None,
    fonts_dir: str = "assets/fonts",
) -> Image.Image:
    """Render a pixel-perfect, high-definition 32-bit RGBA CTA card overlay image."""
    cfg = normalise_cta_config(cta_config)
    cta_type = cfg["ctaType"]
    template = cfg["template"]
    headline = cfg["headline"] or "Follow For More"
    subhead = cfg["subhead"] or cfg["socialHandle"] or ""
    button_text = cfg["buttonText"] or "FOLLOW"
    text_msg = cfg["text"] or headline
    
    primary_color = cfg["primaryColor"]
    text_color = cfg["textColor"]
    bg_color = cfg["backgroundColor"]
    bg_opacity = cfg["bgOpacity"] / 100.0
    font_size = cfg["fontSize"]
    position = cfg["position"]
    bg_box = cfg["bgBox"]
    selected_icon = cfg["selectedIcon"]

    # Resolution scaling relative to standard 1080p canvas
    scale_factor = width / 1080.0
    scaled_font_size = max(18, int(font_size * 1.25 * scale_factor))

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    dummy_img = Image.new("RGBA", (1, 1))
    draw_d = ImageDraw.Draw(dummy_img)

    # Load fonts
    bold_p = _resolve_font_path(cfg["fontFamily"], fonts_dir=fonts_dir)
    if not bold_p or not os.path.exists(bold_p):
        bold_p = _resolve_font_path("Poppins", fonts_dir=fonts_dir)
    reg_p = _resolve_font_path("Inter", fonts_dir=fonts_dir) or bold_p

    try:
        bold_font = ImageFont.truetype(bold_p, scaled_font_size) if bold_p else ImageFont.load_default()
        sub_font = ImageFont.truetype(reg_p, max(14, int(scaled_font_size * 0.65))) if reg_p else bold_font
        btn_font = ImageFont.truetype(bold_p, max(15, int(scaled_font_size * 0.70))) if bold_p else bold_font
    except Exception:
        bold_font = ImageFont.load_default()
        sub_font = bold_font
        btn_font = bold_font

    pr, pg, pb, _ = hex_to_rgba(primary_color)
    br, bg, bb, _ = hex_to_rgba(bg_color)
    tr, tg, tb, _ = hex_to_rgba(text_color)

    # ─── MODE 1: CARD (Default) ───────────────────────────────────────────────
    if cta_type == "card":
        btn_text_bbox = draw_d.textbbox((0, 0), button_text, font=btn_font)
        btn_text_w = btn_text_bbox[2] - btn_text_bbox[0]
        btn_text_h = btn_text_bbox[3] - btn_text_bbox[1]

        icon_size = max(16, int(22 * scale_factor))
        icon_spacing = max(6, int(10 * scale_factor))
        btn_pad_x = max(18, int(30 * scale_factor))
        btn_pad_y = max(10, int(16 * scale_factor))

        btn_w = btn_text_w + icon_size + icon_spacing + (btn_pad_x * 2)
        btn_h = max(btn_text_h + (btn_pad_y * 2), int(54 * scale_factor))

        card_margin_x = int(60 * scale_factor)
        card_w = width - (card_margin_x * 2)
        card_h = int(140 * scale_factor)

        card_x = card_margin_x
        if position == "top":
            card_y = int(height * 0.08)
        elif position == "center":
            card_y = int(height * 0.50 - card_h / 2)
        elif position == "lower-third":
            card_y = int(height * 0.72)
        else:
            card_y = int(height * 0.83)

        # 1. Drop shadow & glow
        shadow_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow_img)
        s_draw.rounded_rectangle(
            [card_x + 4, card_y + int(10 * scale_factor), card_x + card_w + 4, card_y + card_h + int(10 * scale_factor)],
            radius=int(26 * scale_factor),
            fill=(0, 0, 0, 160),
        )
        s_draw.rounded_rectangle(
            [card_x, card_y, card_x + card_w, card_y + card_h],
            radius=int(26 * scale_factor),
            fill=(pr, pg, pb, 50),
        )
        shadow_blurred = shadow_img.filter(ImageFilter.GaussianBlur(radius=max(6, int(16 * scale_factor))))
        overlay = Image.alpha_composite(overlay, shadow_blurred)

        # 2. Main card body
        card_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        c_draw = ImageDraw.Draw(card_layer)
        c_draw.rounded_rectangle(
            [card_x, card_y, card_x + card_w, card_y + card_h],
            radius=int(26 * scale_factor),
            fill=(br, bg, bb, int(bg_opacity * 255)),
            outline=(pr, pg, pb, 110),
            width=max(2, int(3 * scale_factor)),
        )

        # Left Text: Headline + Subhead
        left_x = card_x + int(34 * scale_factor)
        hl_bbox = c_draw.textbbox((0, 0), headline, font=bold_font)
        hl_h = hl_bbox[3] - hl_bbox[1]

        if subhead:
            sub_bbox = c_draw.textbbox((0, 0), subhead, font=sub_font)
            sub_h = sub_bbox[3] - sub_bbox[1]
            text_gap = max(6, int(12 * scale_factor))
            total_text_h = hl_h + sub_h + text_gap
            start_y = card_y + (card_h - total_text_h) // 2
            hl_y = start_y
            sub_y = hl_y + hl_h + text_gap
            c_draw.text((left_x, hl_y), headline, font=bold_font, fill=(tr, tg, tb, 255))
            c_draw.text((left_x, sub_y), subhead, font=sub_font, fill=(148, 163, 184, 230))
        else:
            hl_y = card_y + (card_h - hl_h) // 2
            c_draw.text((left_x, hl_y), headline, font=bold_font, fill=(tr, tg, tb, 255))

        # Right Button: Pill with vector icon
        btn_x = card_x + card_w - btn_w - int(24 * scale_factor)
        btn_y = card_y + (card_h - btn_h) // 2

        c_draw.rounded_rectangle(
            [btn_x, btn_y, btn_x + btn_w, btn_y + btn_h],
            radius=btn_h // 2,
            fill=(pr, pg, pb, 255),
            outline=(255, 255, 255, 60),
            width=1,
        )

        icon_cx = btn_x + btn_pad_x + (icon_size // 2)
        icon_cy = btn_y + (btn_h // 2)
        draw_vector_icon(c_draw, template, icon_cx, icon_cy, size=icon_size, color=(255, 255, 255, 255))

        txt_x = icon_cx + (icon_size // 2) + icon_spacing
        txt_y = btn_y + (btn_h - btn_text_h) // 2 - 2
        c_draw.text((txt_x, txt_y), button_text, font=btn_font, fill=(255, 255, 255, 255))

        overlay = Image.alpha_composite(overlay, card_layer)

    # ─── MODE 2: BOTH (TEXT + ICON) ───────────────────────────────────────────
    elif cta_type == "both":
        msg_bbox = draw_d.textbbox((0, 0), text_msg, font=bold_font)
        msg_w = msg_bbox[2] - msg_bbox[0]
        msg_h = msg_bbox[3] - msg_bbox[1]

        icon_box_size = max(28, int(42 * scale_factor))
        icon_size = max(16, int(22 * scale_factor))
        pad_x = max(18, int(30 * scale_factor))
        pad_y = max(10, int(16 * scale_factor))
        gap = max(10, int(16 * scale_factor))

        pill_w = pad_x * 2 + icon_box_size + gap + msg_w
        pill_h = max(icon_box_size + (pad_y * 2), msg_h + (pad_y * 2))
        pill_x = (width - pill_w) // 2

        if position == "top":
            pill_y = int(height * 0.08)
        elif position == "center":
            pill_y = int(height * 0.50 - pill_h / 2)
        elif position == "lower-third":
            pill_y = int(height * 0.72)
        else:
            pill_y = int(height * 0.84)

        if bg_box:
            shadow_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            s_draw = ImageDraw.Draw(shadow_img)
            s_draw.rounded_rectangle(
                [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
                radius=pill_h // 2,
                fill=(pr, pg, pb, 60),
            )
            s_draw.rounded_rectangle(
                [pill_x + 3, pill_y + 8, pill_x + pill_w + 3, pill_y + pill_h + 8],
                radius=pill_h // 2,
                fill=(0, 0, 0, 160),
            )
            shadow_blurred = shadow_img.filter(ImageFilter.GaussianBlur(radius=max(6, int(14 * scale_factor))))
            overlay = Image.alpha_composite(overlay, shadow_blurred)

        pill_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        p_draw = ImageDraw.Draw(pill_layer)

        if bg_box:
            p_draw.rounded_rectangle(
                [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
                radius=pill_h // 2,
                fill=(br, bg, bb, int(bg_opacity * 255)),
                outline=(pr, pg, pb, 110),
                width=max(2, int(2.5 * scale_factor)),
            )

        # Left circular icon badge
        ib_x = pill_x + pad_x
        ib_y = pill_y + (pill_h - icon_box_size) // 2
        p_draw.ellipse(
            [ib_x, ib_y, ib_x + icon_box_size, ib_y + icon_box_size],
            fill=(pr, pg, pb, 255),
        )
        draw_vector_icon(
            p_draw,
            selected_icon,
            ib_x + (icon_box_size // 2),
            ib_y + (icon_box_size // 2),
            size=icon_size,
            color=(255, 255, 255, 255),
        )

        # Right text
        txt_x = ib_x + icon_box_size + gap
        txt_y = pill_y + (pill_h - msg_h) // 2 - 2
        p_draw.text((txt_x, txt_y), text_msg, font=bold_font, fill=(tr, tg, tb, 255))

        overlay = Image.alpha_composite(overlay, pill_layer)

    # ─── MODE 3: TEXT ONLY ───────────────────────────────────────────────────
    else:
        msg_bbox = draw_d.textbbox((0, 0), text_msg, font=bold_font)
        msg_w = msg_bbox[2] - msg_bbox[0]
        msg_h = msg_bbox[3] - msg_bbox[1]

        pad_x = max(24, int(40 * scale_factor))
        pad_y = max(12, int(20 * scale_factor))

        box_w = min(width - 80, msg_w + (pad_x * 2))
        box_h = msg_h + (pad_y * 2)
        box_x = (width - box_w) // 2

        if position == "top":
            box_y = int(height * 0.08)
        elif position == "center":
            box_y = int(height * 0.50 - box_h / 2)
        elif position == "lower-third":
            box_y = int(height * 0.72)
        else:
            box_y = int(height * 0.84)

        if bg_box:
            shadow_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            s_draw = ImageDraw.Draw(shadow_img)
            s_draw.rounded_rectangle(
                [box_x + 3, box_y + 8, box_x + box_w + 3, box_y + box_h + 8],
                radius=int(22 * scale_factor),
                fill=(0, 0, 0, 160),
            )
            s_draw.rounded_rectangle(
                [box_x, box_y, box_x + box_w, box_y + box_h],
                radius=int(22 * scale_factor),
                fill=(pr, pg, pb, 50),
            )
            shadow_blurred = shadow_img.filter(ImageFilter.GaussianBlur(radius=max(6, int(14 * scale_factor))))
            overlay = Image.alpha_composite(overlay, shadow_blurred)

        txt_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        t_draw = ImageDraw.Draw(txt_layer)

        if bg_box:
            t_draw.rounded_rectangle(
                [box_x, box_y, box_x + box_w, box_y + box_h],
                radius=int(22 * scale_factor),
                fill=(br, bg, bb, int(bg_opacity * 255)),
                outline=(pr, pg, pb, 110),
                width=max(2, int(2.5 * scale_factor)),
            )

        txt_x = (width - msg_w) // 2
        txt_y = box_y + (box_h - msg_h) // 2 - 2
        t_draw.text((txt_x, txt_y), text_msg, font=bold_font, fill=(tr, tg, tb, 255))

        overlay = Image.alpha_composite(overlay, txt_layer)

    return overlay


def escape_drawtext(text: str) -> str:
    """Escape text safely for FFmpeg drawtext filter."""
    if not text:
        return ""
    t = str(text).replace("\\", "\\\\")
    t = t.replace(":", "\\:")
    t = t.replace("'", "'\\\\''")
    t = t.replace("%", "\\%")
    return t


def build_cta_drawtext_filters(
    cta_config: Optional[dict],
    clip_duration: float,
    font_path: Optional[str] = None,
) -> list[str]:
    """Fallback FFmpeg drawtext filter builder (kept for legacy/compositor fallback)."""
    cfg = normalise_cta_config(cta_config)
    if not cfg["enabled"]:
        return []

    dur = cfg["duration"]
    start_t = max(0.0, clip_duration - dur)
    end_t = clip_duration

    enable_expr = f"between(t,{start_t:.3f},{end_t:.3f})"
    font_opt = f":fontfile='{font_path}'" if font_path else ""

    filters = []
    pos = cfg["position"]
    if pos == "top":
        base_y = "h*0.08"
    elif pos == "center":
        base_y = "h/2 - 60"
    elif pos == "lower-third":
        base_y = "h*0.75"
    else:
        base_y = "h*0.84"

    bg_opacity_hex = f"{cfg['bgOpacity'] / 100.0:.2f}"
    box_color = f"{cfg['backgroundColor']}@{bg_opacity_hex}"
    box_enabled = ":box=1:boxcolor=" + box_color + ":boxborderw=16" if cfg["bgBox"] else ":box=0"

    cta_type = cfg["ctaType"]

    if cta_type in ("text", "both"):
        msg_escaped = escape_drawtext(cfg["text"])
        text_filter = (
            f"drawtext=text='{msg_escaped}'"
            f"{font_opt}"
            f":fontsize={cfg['fontSize']}"
            f":fontcolor={cfg['textColor']}"
            f"{box_enabled}"
            f":borderw=2:bordercolor=black@0.6"
            f":shadowx=2:shadowy=3:shadowcolor=black@0.5"
            f":x=(w-text_w)/2:y={base_y}"
            f":enable='{enable_expr}'"
        )
        filters.append(text_filter)
        return filters

    headline_escaped = escape_drawtext(cfg["headline"])
    button_escaped = escape_drawtext(f"[{cfg['buttonText']}]") if cfg["buttonText"] else ""

    headline_filter = (
        f"drawtext=text='{headline_escaped}'"
        f"{font_opt}"
        f":fontsize={cfg['fontSize']}"
        f":fontcolor={cfg['textColor']}"
        f":box=1:boxcolor={box_color}:boxborderw=16"
        f":borderw=2:bordercolor=black@0.6"
        f":shadowx=2:shadowy=3:shadowcolor=black@0.5"
        f":x=(w-text_w)/2:y={base_y}"
        f":enable='{enable_expr}'"
    )
    filters.append(headline_filter)

    if button_escaped:
        button_filter = (
            f"drawtext=text='{button_escaped}'"
            f"{font_opt}"
            f":fontsize={max(16, cfg['fontSize'] - 4)}"
            f":fontcolor={cfg['primaryColor']}"
            f":borderw=2:bordercolor=black@0.8"
            f":shadowx=1:shadowy=2:shadowcolor=black@0.5"
            f":x=(w-text_w)/2:y={base_y} + {cfg['fontSize'] + 22}"
            f":enable='{enable_expr}'"
        )
        filters.append(button_filter)

    return filters


def _probe_video_info(video_path: str) -> tuple[float, int, int]:
    """Probe video duration, width, and height via ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height:format=duration",
            "-of", "json",
            video_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(res.stdout)
        dur = float(data.get("format", {}).get("duration", 30.0) or 30.0)
        streams = data.get("streams", [{}])
        w = int(streams[0].get("width", 1080) or 1080)
        h = int(streams[0].get("height", 1920) or 1920)
        return dur, w, h
    except Exception:
        return 30.0, 1080, 1920


def apply_cta(
    input_video: str,
    cta_config: dict,
    output_video: str,
    fonts_dir: str = "assets/fonts",
) -> bool:
    """Apply pixel-perfect CTA end-card overlay to video using Pillow rendering + FFmpeg overlay."""
    cfg = normalise_cta_config(cta_config)
    if not cfg["enabled"]:
        return False

    duration, width, height = _probe_video_info(input_video)
    dur = cfg["duration"]
    start_t = max(0.0, duration - dur)
    end_t = duration
    anim_dur = 0.35
    anim_type = cfg["animation"]
    scale_factor = width / 1080.0

    # 1. Render high-res RGBA CTA card overlay image
    try:
        overlay_img = render_cta_overlay_image(
            width=width,
            height=height,
            cta_config=cfg,
            fonts_dir=fonts_dir,
        )
    except Exception as e:
        logger.warning("cta_renderer: Pillow render failed (%s), falling back to drawtext", e)
        return _apply_cta_drawtext_fallback(input_video, cfg, output_video, fonts_dir, duration)

    # 2. Save overlay image to temp PNG
    tmp_png = tempfile.NamedTemporaryFile(suffix=".png", prefix="cta_card_", delete=False).name
    try:
        overlay_img.save(tmp_png, format="PNG")

        # 3. Construct animated overlay filter expression
        if anim_type == "pop_in":
            # Pop in with slight overshoot
            offset_expr = (
                f"if(lt(t,{start_t:.3f}),-H,"
                f"if(lt(t,{(start_t + anim_dur):.3f}),"
                f"{int(50 * scale_factor)}*sin((t-{start_t:.3f})/{anim_dur}*3.1415),0))"
            )
        elif anim_type == "fade_bounce":
            # Fade bounce
            offset_expr = (
                f"if(lt(t,{start_t:.3f}),-H,"
                f"if(lt(t,{(start_t + anim_dur):.3f}),"
                f"{int(40 * scale_factor)}*(1-(t-{start_t:.3f})/{anim_dur}),0))"
            )
        else:
            # Default slide_up
            slide_dist = int(90 * scale_factor)
            offset_expr = (
                f"if(lt(t,{start_t:.3f}),-H,"
                f"if(lt(t,{(start_t + anim_dur):.3f}),"
                f"{slide_dist}*(1-(t-{start_t:.3f})/{anim_dur}),0))"
            )

        filter_expr = f"[0:v][1:v]overlay=0:'{offset_expr}':enable='between(t,{start_t:.3f},{end_t:.3f})'[outv]"

        from src.infrastructure.gpu_encoder import get_video_encoder_args
        encoder_args = get_video_encoder_args("high")

        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-i", tmp_png,
            "-filter_complex", filter_expr,
            "-map", "[outv]", "-map", "0:a?",
            *encoder_args,
            "-c:a", "copy", "-movflags", "+faststart",
            output_video,
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        if proc.returncode != 0:
            logger.warning("cta_renderer: ffmpeg overlay failed (rc=%s): %s", proc.returncode, proc.stderr[-300:] if proc.stderr else "")
            return _apply_cta_drawtext_fallback(input_video, cfg, output_video, fonts_dir, duration)

        return proc.returncode == 0 and os.path.exists(output_video) and os.path.getsize(output_video) > 0
    except Exception as e:
        logger.warning("cta_renderer: exception during apply_cta (%s)", e)
        return _apply_cta_drawtext_fallback(input_video, cfg, output_video, fonts_dir, duration)
    finally:
        if os.path.exists(tmp_png):
            try:
                os.remove(tmp_png)
            except OSError:
                pass


def _apply_cta_drawtext_fallback(
    input_video: str,
    cfg: dict,
    output_video: str,
    fonts_dir: str,
    duration: float,
) -> bool:
    """Fallback FFmpeg drawtext method in case overlay fails."""
    font_path = _resolve_font_path(cfg["fontFamily"], fonts_dir=fonts_dir)
    filters = build_cta_drawtext_filters(cfg, duration, font_path)
    if not filters:
        return False
    filter_str = ",".join(filters)
    from src.infrastructure.gpu_encoder import get_video_encoder_args
    encoder_args = get_video_encoder_args("high")

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", filter_str,
        "-map", "0:v:0", "-map", "0:a?",
        *encoder_args,
        "-c:a", "copy", "-movflags", "+faststart",
        output_video,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        return proc.returncode == 0 and os.path.exists(output_video) and os.path.getsize(output_video) > 0
    except Exception as e:
        logger.warning("cta_renderer: drawtext fallback failed: %s", e)
        return False


async def apply_cta_if_configured(
    config: Optional[dict],
    output_dir: str,
    clip_rank: int,
    final_path: str,
    fonts_dir: str = "assets/fonts",
    job_id: str = "",
) -> None:
    """Apply a CTA to a finished clip in place (via a temp file). Safe no-op if disabled."""
    cfg = normalise_cta_config(config)
    if not cfg["enabled"]:
        logger.debug("[%s] CTA disabled for clip %s", job_id, clip_rank)
        return

    logger.info(
        "[%s] Applying HD CTA card to clip %s: type=%s, headline='%s', template=%s, dur=%.1fs",
        job_id, clip_rank, cfg.get("ctaType"), cfg.get("headline"), cfg.get("template"), cfg.get("duration")
    )
    tmp = f"{output_dir}/clip_{clip_rank:02d}_cta_tmp.mp4"
    try:
        ok = await asyncio.to_thread(apply_cta, final_path, cfg, tmp, fonts_dir)
        if ok and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, final_path)
            logger.info("[%s] CTA applied successfully to clip %s -> %s", job_id, clip_rank, final_path)
        elif os.path.exists(tmp):
            os.remove(tmp)
            logger.warning("[%s] CTA render returned false for clip %s", job_id, clip_rank)
    except Exception as e:
        logger.warning("[%s] CTA application failed clip %s: %s", job_id, clip_rank, e)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


async def apply_cta_for_job(
    job,
    clip_rank: int,
    output_dir: str,
    final_path: str,
    fonts_dir: str = "assets/fonts",
    job_id: str = "",
) -> None:
    """Read ``cta_config`` from ``job.clips_data`` and apply it in place."""
    config = (getattr(job, "clips_data", None) or {}).get("cta_config") or getattr(job, "cta_config", None)
    await apply_cta_if_configured(
        config, output_dir, clip_rank, final_path,
        fonts_dir=fonts_dir, job_id=job_id,
    )
