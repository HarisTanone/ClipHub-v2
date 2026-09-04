"""Social Cover Generator for TikTok, Instagram Reels, and YouTube Shorts.

Generates high-retention, viral-optimized thumbnail covers featuring:
- Eye-catching Category Badge (e.g., "🔥 TRENDING HARI INI", "FAKTA MENGEJUTKAN")
- High-contrast Bold Hook Box (Anton / Montserrat typography in yellow/black or white/red)
- Secondary Topic Caption & Context
- Dynamic Hashtag Pills (#Topic #Keyword #FYP)
- TikTok Interactive Play Indicator ("Tap to Watch")
- Brand Watermark & Aspect-ratio awareness (9:16, 16:9, 1:1, 4:5)
"""
from __future__ import annotations

import logging
import os
import re
from typing import List, Optional, Tuple

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

# Fonts mapping relative to backend directory
FONT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts"))

PRIMARY_HOOK_FONTS = [
    os.path.join(FONT_DIR, "Anton-Regular.ttf"),
    os.path.join(FONT_DIR, "BebasNeue-Regular.ttf"),
    os.path.join(FONT_DIR, "ArchivoBlack-Regular.ttf"),
    os.path.join(FONT_DIR, "Poppins-Bold.ttf"),
]

SECONDARY_FONTS = [
    os.path.join(FONT_DIR, "Poppins-Bold.ttf"),
    os.path.join(FONT_DIR, "Montserrat-Variable.ttf"),
    os.path.join(FONT_DIR, "Inter-Variable.ttf"),
    os.path.join(FONT_DIR, "Roboto-Bold.ttf"),
]

ASPECT_RATIO_RESOLUTIONS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}


def _load_font(candidates: List[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Attempt to load the first available TrueType font from candidates, falling back to default."""
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception as e:
                logger.debug(f"Failed to load font at {path}: {e}")
    try:
        return ImageFont.load_default()
    except Exception:
        return None  # type: ignore


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
    """Wrap text intelligently into multiple lines to fit max_width."""
    words = text.split()
    if not words:
        return []

    lines: List[str] = []
    current_line = []

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
                # Single word wider than max_width, force it
                lines.append(word)
                current_line = []

    if current_line:
        lines.append(" ".join(current_line))

    return lines


def _draw_rounded_rectangle(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[float, float, float, float],
    radius: float,
    fill: Optional[Tuple[int, ...]] = None,
    outline: Optional[Tuple[int, ...]] = None,
    width: int = 1,
) -> None:
    """Draw a smooth rounded rectangle."""
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill, outline=outline, width=width)


def _extract_hashtags_list(hashtags_input: Any, topic: str = "") -> List[str]:
    """Normalize hashtags input into a clean list of prefixed tags like ['#Viral', '#FYP']."""
    raw_tags: List[str] = []
    if isinstance(hashtags_input, list):
        for h in hashtags_input:
            if isinstance(h, str) and h.strip():
                tag = h.strip()
                if not tag.startswith("#"):
                    tag = f"#{tag}"
                raw_tags.append(tag)
    elif isinstance(hashtags_input, str) and hashtags_input.strip():
        # Match all words or existing #tags
        found = re.findall(r"#?([A-Za-z0-9_]+)", hashtags_input)
        for f in found:
            if f.strip():
                raw_tags.append(f"#{f.strip()}")

    # If empty, derive dynamic hashtags from topic keywords
    if not raw_tags and topic:
        clean_words = re.findall(r"\b[A-Za-z0-9]{3,}\b", topic)
        for w in clean_words[:4]:
            cap = w.capitalize()
            if cap.lower() not in ("yang", "pada", "dalam", "untuk", "dari", "ini", "itu", "dan"):
                raw_tags.append(f"#{cap}")

    # Fallback popular social tags
    if len(raw_tags) < 2:
        raw_tags.extend(["#Trending", "#Viral", "#FYP", "#TrendingNow"])

    # Unique and take top 4
    seen = set()
    unique_tags = []
    for t in raw_tags:
        clean = t.lower()
        if clean not in seen:
            seen.add(clean)
            unique_tags.append(t)
        if len(unique_tags) >= 4:
            break

    return unique_tags


def generate_social_cover(
    base_image_path: Optional[str],
    output_path: str,
    hook_text: str,
    caption_text: Optional[str] = None,
    hashtags: Optional[Any] = None,
    category_badge: Optional[str] = None,
    aspect_ratio: str = "9:16",
    watermark_text: Optional[str] = None,
    include_play_indicator: bool = True,
    theme_color: str = "#FACC15",  # Vibrant TikTok Cyber Yellow
) -> str:
    """Render a high-CTR social media cover thumbnail for TikTok, Reels, or YouTube Shorts.

    Args:
        base_image_path: Path to extracted keyframe video frame (or None to generate gradient)
        output_path: Target path to save final JPG thumbnail
        hook_text: Big bold headline / hook sentence
        caption_text: Sub-headline or topic explanation
        hashtags: Dynamic hashtags list or string
        category_badge: Header badge label (e.g. '🔥 TRENDING', 'FAKTA MENARIK')
        aspect_ratio: '9:16', '16:9', '1:1', or '4:5'
        watermark_text: Branding account watermark (e.g. '@cliperhub')
        include_play_indicator: Draw subtle TikTok 'Tap to Watch' play cue
        theme_color: Hex color for high-contrast hook badge accent

    Returns:
        output_path on success.
    """
    target_width, target_height = ASPECT_RATIO_RESOLUTIONS.get(aspect_ratio, (1080, 1920))

    # 1. Base Canvas Preparation
    if base_image_path and os.path.exists(base_image_path):
        try:
            with Image.open(base_image_path) as raw_img:
                raw_img = raw_img.convert("RGBA")
                # Calculate cover aspect fill (zoom & center-crop)
                src_w, src_h = raw_img.size
                src_ratio = src_w / float(src_h)
                target_ratio = target_width / float(target_height)

                if src_ratio > target_ratio:
                    # Source is wider, scale by height
                    new_h = target_height
                    new_w = int(target_height * src_ratio)
                else:
                    # Source is taller, scale by width
                    new_w = target_width
                    new_h = int(target_width / src_ratio)

                resized = raw_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                # Center crop
                left = (new_w - target_width) // 2
                top = (new_h - target_height) // 2
                canvas = resized.crop((left, top, left + target_width, top + target_height))
        except Exception as e:
            logger.warning(f"social_cover: failed opening base image {base_image_path}: {e}")
            canvas = Image.new("RGBA", (target_width, target_height), (18, 18, 24, 255))
    else:
        # Create rich dark gradient background
        canvas = Image.new("RGBA", (target_width, target_height), (15, 15, 20, 255))

    # 2. Cinematic Gradient Overlay (Ensures 100% legibility on any video frame)
    overlay = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # Multi-stop vertical dark gradients
    # Top bar (0 to 30% height): 50% opacity black down to 0
    top_bar_h = int(target_height * 0.28)
    for y in range(top_bar_h):
        alpha = int(140 * (1.0 - (y / float(top_bar_h))))
        overlay_draw.line([(0, y), (target_width, y)], fill=(0, 0, 0, alpha))

    # Middle Hook backdrop (22% to 65% height): semi-transparent dark box gradient
    mid_start = int(target_height * 0.18)
    mid_end = int(target_height * 0.68)
    mid_span = mid_end - mid_start
    for y in range(mid_start, mid_end):
        rel = (y - mid_start) / float(mid_span)
        # Bell curve opacity peaking in the middle
        opacity = 0.65 * (1.0 - 4.0 * ((rel - 0.5) ** 2))
        alpha = max(0, min(175, int(opacity * 255)))
        if alpha > 0:
            overlay_draw.line([(0, y), (target_width, y)], fill=(0, 0, 0, alpha))

    # Bottom bar (70% to 100% height): dark gradient for hashtags & clean TikTok lower zone
    bot_start = int(target_height * 0.70)
    for y in range(bot_start, target_height):
        rel = (y - bot_start) / float(target_height - bot_start)
        alpha = int(200 * rel)
        overlay_draw.line([(0, y), (target_width, y)], fill=(0, 0, 0, alpha))

    # Composite gradient onto canvas
    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)

    # 3. Top Category Badge ("🔥 TRENDING HARI INI")
    badge_text = category_badge or "🔥 TRENDING HARI INI"
    badge_font_size = int(target_width * 0.038)  # ~41px on 1080w
    badge_font = _load_font(SECONDARY_FONTS, badge_font_size)

    # Badge bounding box
    badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_tw = badge_bbox[2] - badge_bbox[0]
    badge_th = badge_bbox[3] - badge_bbox[1]

    badge_pad_x = int(target_width * 0.03)
    badge_pad_y = int(target_height * 0.008)
    badge_w = badge_tw + (badge_pad_x * 2)
    badge_h = badge_th + (badge_pad_y * 2)

    badge_y = int(target_height * 0.14)  # Safe zone top
    badge_x = (target_width - badge_w) // 2

    # Draw Badge Capsule
    _draw_rounded_rectangle(
        draw,
        (badge_x, badge_y, badge_x + badge_w, badge_y + badge_h),
        radius=badge_h // 2,
        fill=(220, 38, 38, 230),  # Rich TikTok Red
        outline=(255, 255, 255, 180),
        width=2,
    )
    # Draw Badge Text
    draw.text(
        (badge_x + badge_pad_x, badge_y + badge_pad_y),
        badge_text,
        font=badge_font,
        fill=(255, 255, 255, 255),
    )

    # 4. Primary Viral Hook Title (Large, Eye-Catching Centerpiece)
    hook_clean = (hook_text or "VIRAL HARI INI").strip()
    # Normalize uppercase for impactful headline punch
    hook_clean = hook_clean.upper()

    # Dynamic Hook Font Sizing
    hook_font_size = int(target_width * 0.078)  # ~84px on 1080w
    hook_font = _load_font(PRIMARY_HOOK_FONTS, hook_font_size)

    max_text_w = int(target_width * 0.86)
    wrapped_hook_lines = _wrap_text(hook_clean, hook_font, max_text_w, draw)

    # If more than 3 lines, reduce font size
    if len(wrapped_hook_lines) > 3:
        hook_font_size = int(target_width * 0.064)  # ~69px
        hook_font = _load_font(PRIMARY_HOOK_FONTS, hook_font_size)
        wrapped_hook_lines = _wrap_text(hook_clean, hook_font, max_text_w, draw)

    # Calculate total hook height
    line_metrics = []
    total_hook_h = 0
    line_spacing = int(hook_font_size * 0.28)

    for line in wrapped_hook_lines:
        bbox = draw.textbbox((0, 0), line, font=hook_font)
        lw = bbox[2] - bbox[0]
        lh = bbox[3] - bbox[1]
        line_metrics.append((line, lw, lh))
        total_hook_h += lh

    total_hook_h += line_spacing * max(0, len(wrapped_hook_lines) - 1)

    hook_start_y = badge_y + badge_h + int(target_height * 0.035)

    # Draw Hook Lines with Contrast Badging (TikTok Yellow Highlight or Bold 3D Drop-Shadow)
    current_y = hook_start_y
    for line, lw, lh in line_metrics:
        pad_x = int(target_width * 0.032)
        pad_y = int(target_height * 0.007)
        box_w = lw + (pad_x * 2)
        box_h = lh + (pad_y * 2)
        box_x = (target_width - box_w) // 2

        # Glowing Neon Yellow Box
        _draw_rounded_rectangle(
            draw,
            (box_x, current_y, box_x + box_w, current_y + box_h),
            radius=12,
            fill=(250, 204, 21, 245),  # Yellow #FACC15
            outline=(0, 0, 0, 200),
            width=2,
        )

        # Black Impact Typography inside Yellow Box
        text_x = box_x + pad_x
        text_y = current_y + pad_y
        draw.text(
            (text_x, text_y),
            line,
            font=hook_font,
            fill=(10, 10, 15, 255),
        )
        current_y += box_h + line_spacing

    # 5. Supporting Caption / Sub-Headline (Context & Curiosity)
    caption_start_y = current_y + int(target_height * 0.02)
    if caption_text and caption_text.strip():
        caption_clean = caption_text.strip()
        cap_font_size = int(target_width * 0.042)  # ~45px
        cap_font = _load_font(SECONDARY_FONTS, cap_font_size)

        wrapped_cap_lines = _wrap_text(caption_clean, cap_font, int(target_width * 0.84), draw)
        for cline in wrapped_cap_lines[:2]:
            cbbox = draw.textbbox((0, 0), cline, font=cap_font)
            cw = cbbox[2] - cbbox[0]
            ch = cbbox[3] - cbbox[1]
            cx = (target_width - cw) // 2

            # Text shadow for maximum clarity
            draw.text((cx + 2, caption_start_y + 2), cline, font=cap_font, fill=(0, 0, 0, 220))
            draw.text((cx, caption_start_y), cline, font=cap_font, fill=(240, 249, 255, 255))
            caption_start_y += ch + int(cap_font_size * 0.35)

    # 6. TikTok Interactive Play Indicator ("▶ TAP TO WATCH")
    if include_play_indicator and aspect_ratio == "9:16":
        play_y = int(target_height * 0.58)
        play_r = int(target_width * 0.075)  # 81px radius
        play_center_x = target_width // 2

        # Outer glowing glass circle
        play_box = (
            play_center_x - play_r,
            play_y - play_r,
            play_center_x + play_r,
            play_y + play_r,
        )
        draw.ellipse(play_box, fill=(255, 255, 255, 45), outline=(255, 255, 255, 160), width=3)

        # Inner play triangle
        tri_size = int(play_r * 0.70)
        tri_x = play_center_x + int(play_r * 0.08)
        tri_pts = [
            (tri_x - tri_size // 2, play_y - tri_size // 2),
            (tri_x + tri_size // 2, play_y),
            (tri_x - tri_size // 2, play_y + tri_size // 2),
        ]
        draw.polygon(tri_pts, fill=(255, 255, 255, 240))

        # "TAP TO WATCH" Subtitle Cue
        cue_font_size = int(target_width * 0.028)  # ~30px
        cue_font = _load_font(SECONDARY_FONTS, cue_font_size)
        cue_text = "KLIK UNTUK NONTON ▶"
        cue_bbox = draw.textbbox((0, 0), cue_text, font=cue_font)
        cue_w = cue_bbox[2] - cue_bbox[0]
        draw.text(
            ((target_width - cue_w) // 2, play_y + play_r + 14),
            cue_text,
            font=cue_font,
            fill=(255, 255, 255, 220),
        )

    # 7. Dynamic Hashtag Pills
    tag_list = _extract_hashtags_list(hashtags, topic=hook_text or (caption_text or ""))
    if tag_list:
        tag_font_size = int(target_width * 0.034)  # ~36px
        tag_font = _load_font(SECONDARY_FONTS, tag_font_size)

        # Compute tag widths
        tag_boxes = []
        pad_x = int(target_width * 0.022)
        pad_y = int(target_height * 0.006)
        total_tags_w = 0

        for t in tag_list:
            tbbox = draw.textbbox((0, 0), t, font=tag_font)
            tw = tbbox[2] - tbbox[0]
            th = tbbox[3] - tbbox[1]
            box_w = tw + (pad_x * 2)
            box_h = th + (pad_y * 2)
            tag_boxes.append((t, tw, th, box_w, box_h))
            total_tags_w += box_w + int(target_width * 0.015)

        # Center tags horizontally
        tag_start_y = int(target_height * 0.78)
        current_tag_x = max(int(target_width * 0.06), (target_width - total_tags_w) // 2)

        for t, tw, th, bw, bh in tag_boxes:
            if current_tag_x + bw > target_width - int(target_width * 0.04):
                break
            _draw_rounded_rectangle(
                draw,
                (current_tag_x, tag_start_y, current_tag_x + bw, tag_start_y + bh),
                radius=bh // 2,
                fill=(255, 255, 255, 35),
                outline=(250, 204, 21, 180),  # Yellow border
                width=2,
            )
            draw.text(
                (current_tag_x + pad_x, tag_start_y + pad_y),
                t,
                font=tag_font,
                fill=(254, 240, 138, 255),  # Soft glowing yellow
            )
            current_tag_x += bw + int(target_width * 0.018)

    # 8. Branding Watermark (Bottom Safe Area)
    if watermark_text and watermark_text.strip():
        wm_text = watermark_text.strip()
        if not wm_text.startswith("@"):
            wm_text = f"@{wm_text}"
        wm_font_size = int(target_width * 0.030)
        wm_font = _load_font(SECONDARY_FONTS, wm_font_size)
        wm_bbox = draw.textbbox((0, 0), wm_text, font=wm_font)
        wm_w = wm_bbox[2] - wm_bbox[0]
        wm_x = (target_width - wm_w) // 2
        wm_y = int(target_height * 0.87)

        draw.text((wm_x + 1, wm_y + 1), wm_text, font=wm_font, fill=(0, 0, 0, 180))
        draw.text((wm_x, wm_y), wm_text, font=wm_font, fill=(255, 255, 255, 190))

    # 9. Save final JPEG
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    final_rgb = canvas.convert("RGB")
    final_rgb.save(output_path, format="JPEG", quality=92, optimize=True)
    logger.info(f"social_cover: generated viral cover ({target_width}x{target_height}) -> {output_path}")
    return output_path
