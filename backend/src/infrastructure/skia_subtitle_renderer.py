"""SkiaSubtitleRenderer — High-definition GPU/Canvas-style subtitle rendering via Pillow + FFmpeg.

Renders subtitle frames matching the frontend Skia Canvas previews 1:1:
- Glassmorphism: Frosted glass card with glossy border and glowing active word
- Clean Editorial: Minimalist Swiss slate pill with underline tracking
- Podcast Pro: Dark capsule with emerald MIC indicator dot and active speaker glow
- Kinetic Word Box: Dynamic solid rounded badge encasing active word
- Neon Tube: Hollow glowing neon text with multi-layer glow
- Gradient Fill: Iridescent text gradient with drop shadow
- Cinematic Slate: Hollywood serif framed by top and bottom gold rules
- Modern Mono: Cyber terminal box with mini traffic light window header
- Retro Chrome: 3D metallic/chrome text with heavy outline
- Outline Stack: Multi-pass bold outline typography
"""
import logging
import math
import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from src.infrastructure.subtitle_styles import SKIA_STYLES, get_skia_style

logger = logging.getLogger(__name__)


class SkiaSubtitleRenderer:
    """High-definition subtitle renderer with Canvas/GPU visual fidelity using Pillow + FFmpeg."""

    def __init__(self, font_dir: str = "assets/fonts", width: int = 1080, height: int = 1920):
        self._font_dir = font_dir
        self._width = width
        self._height = height

    def _normalize_style(self, style: Any) -> dict:
        """Normalize style dict from frontend camelCase or backend preset format."""
        if not isinstance(style, dict):
            style = {}

        # Look up preset by ID if provided (stylePreset, preset, id, style_id)
        preset_id = (
            style.get("stylePreset")
            or style.get("preset")
            or style.get("id")
            or style.get("style_id")
            or "glassmorphism"
        )
        base = dict(SKIA_STYLES.get(preset_id, {})) if preset_id in SKIA_STYLES else {}

        # Default font based on preset
        preset_default_fonts = {
            "glassmorphism": "Inter",
            "clean_editorial": "Inter",
            "podcast_pro": "Plus Jakarta Sans",
            "kinetic_word_box": "Plus Jakarta Sans",
            "neon_tube": "Montserrat",
            "gradient_fill": "Poppins",
            "cinematic_slate": "Playfair Display",
            "modern_mono": "Space Grotesk",
            "retro_chrome": "Bebas Neue",
            "outline_stack": "Anton",
        }
        default_font = preset_default_fonts.get(preset_id, "Inter")

        normalized = {
            "id": preset_id,
            "font_family": style.get("fontFamily") or style.get("font_family") or base.get("font_family", default_font),
            "font_size": int(style.get("fontSize") or style.get("font_size") or base.get("font_size", 42)),
            "font_weight": str(style.get("fontWeight") or style.get("font_weight") or base.get("font_weight", "Bold")),
            "text_color": style.get("color") or style.get("text_color") or base.get("text_color", "#FFFFFF"),
            "highlight_color": style.get("highlightColor") or style.get("highlight_color") or base.get("highlight_color", "#38BDF8"),
            "position_y_pct": float(style.get("positionY") or style.get("position_y_pct") or base.get("position_y_pct", 78)),
            "max_words_per_line": int(style.get("maxWordsPerLine") or style.get("max_words_per_line") or base.get("max_words_per_line", 4)),
            "line_transition": style.get("lineTransition") or style.get("line_transition") or base.get("line_transition", "karaoke"),
            "uppercase": bool(style.get("uppercase", base.get("uppercase", False))),
            "enabled": style.get("enabled", True) is not False,
            "start_offset": float(style.get("start_offset", 0.0)),
        }

        # Background parameters
        bg_enabled = bool(
            style.get("bgOpacity", 0) > 0
            or style.get("bg_enabled")
            or style.get("glassmorphism")
            or (base.get("background") is not None)
            or preset_id in ("glassmorphism", "clean_editorial", "podcast_pro", "modern_mono")
        )
        base_bg = base.get("background") or {}
        normalized["bg_enabled"] = bg_enabled
        normalized["bg_opacity"] = float(
            style.get("bgOpacity")
            or style.get("bg_opacity")
            or (base_bg.get("bg_opacity", 0.55) if bg_enabled else 0.0)
        )
        normalized["bg_color"] = style.get("bgColor") or style.get("bg_color") or base_bg.get("bg_color", "#1E293B")
        normalized["bg_radius"] = int(style.get("bgRadius") or style.get("bg_radius") or base_bg.get("border_radius", 18))
        normalized["bg_padding"] = int(style.get("bgPadding") or style.get("bg_padding") or base_bg.get("padding_x", 24))

        # Glow parameters
        glow_enabled = bool(
            style.get("glowEnabled")
            or style.get("glow_enabled")
            or base.get("glow_enabled")
            or preset_id in ("glassmorphism", "podcast_pro", "neon_tube", "modern_mono", "cinematic_slate")
        )
        normalized["glow_enabled"] = glow_enabled
        normalized["glow_color"] = (
            style.get("glowColor")
            or style.get("glow_color")
            or base.get("glow_color")
            or normalized["highlight_color"]
        )
        normalized["glow_radius"] = int(style.get("glowSize") or style.get("glow_radius") or base.get("glow_radius", 14))

        # Stroke / Border
        base_stroke = base.get("stroke") or {}
        stroke_enabled = bool(
            style.get("strokeEnabled")
            or style.get("stroke_enabled")
            or bool(base_stroke)
            or preset_id in ("neon_tube", "retro_chrome", "outline_stack")
        )
        normalized["stroke_enabled"] = stroke_enabled
        normalized["stroke_width"] = int(
            style.get("strokeWidth")
            or style.get("stroke_width")
            or (base_stroke.get("width", 3) if stroke_enabled else 0)
        )
        normalized["stroke_color"] = style.get("strokeColor") or style.get("stroke_color") or base_stroke.get("color", "#000000")

        # Shadow
        base_shadow = base.get("shadow") or {}
        shadow_enabled = bool(
            style.get("shadowEnabled")
            or style.get("shadow_enabled")
            or bool(base_shadow)
            or preset_id in ("clean_editorial", "podcast_pro", "kinetic_word_box", "gradient_fill", "retro_chrome")
        )
        normalized["shadow_enabled"] = shadow_enabled
        normalized["shadow_color"] = style.get("shadowColor") or style.get("shadow_color") or base_shadow.get("color", "#000000")

        return normalized

    def render_subtitles(
        self,
        video_path: str,
        words: list,
        style: Any,
        output_path: str,
        start_offset: float = 0.0,
    ) -> str:
        """Render subtitles with rich Skia effects onto video.

        Args:
            video_path: Input video path.
            words: List of word dicts [{word, start, end}] from Whisper.
            style: Skia style config dict or SubtitleStyleConfig.
            output_path: Output video path.
            start_offset: Seconds delay before subtitles start.

        Returns:
            Path to output video, or original on failure.
        """
        if not os.path.exists(video_path):
            logger.warning(f"skia_subtitle: input missing {video_path}")
            return video_path

        if not words:
            logger.info("skia_subtitle: no words, skipping")
            if video_path != output_path and os.path.exists(video_path):
                import shutil
                shutil.copy2(video_path, output_path)
            return output_path

        norm_style = self._normalize_style(style)

        if not norm_style.get("enabled", True):
            logger.info("skia_subtitle: subtitles disabled via config, bypassing render")
            if video_path != output_path and os.path.exists(video_path):
                import shutil
                shutil.copy2(video_path, output_path)
            return output_path

        try:
            res = self._render_with_pil(video_path, words, norm_style, output_path, start_offset)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return res
            logger.warning("skia_subtitle: Pillow render did not produce valid output, falling back to FFmpeg drawtext")
            return self._ffmpeg_fallback(video_path, words, norm_style, output_path, start_offset)
        except Exception as e:
            logger.error(f"skia_subtitle: Pillow render failed ({e}), falling back to FFmpeg drawtext")
            return self._ffmpeg_fallback(video_path, words, norm_style, output_path, start_offset)

    def _render_with_pil(
        self,
        video_path: str,
        words: list,
        style: dict,
        output_path: str,
        start_offset: float,
    ) -> str:
        """Core high-definition Pillow rendering: generates transparent PNG frames and composites via FFmpeg concat demuxer."""
        lines = self._group_words_into_lines(words, style.get("max_words_per_line", 4))
        if not lines:
            return video_path

        # Determine video duration
        video_dur = self._probe_duration(video_path)
        if video_dur <= 0:
            last_end = max((float(w.get("end", 0)) for w in words), default=60.0)
            video_dur = last_end + start_offset + 5.0

        tmp_dir = tempfile.mkdtemp(prefix="skia_sub_pil_")
        empty_png = os.path.join(tmp_dir, "empty.png")
        Image.new("RGBA", (self._width, self._height), (0, 0, 0, 0)).save(empty_png)

        concat_entries: List[Tuple[str, float]] = []
        cur_time = 0.0
        frame_idx = 0
        transition = style.get("line_transition", "karaoke")

        try:
            for line_idx, line in enumerate(lines):
                line_start = max(0.0, float(line[0].get("start", 0)) + start_offset)
                line_end = max(line_start + 0.1, float(line[-1].get("end", 0)) + start_offset)

                # Silence before line
                if line_start > cur_time:
                    gap_dur = line_start - cur_time
                    if gap_dur >= 0.02:
                        concat_entries.append((empty_png, gap_dur))
                        cur_time = line_start

                if transition == "word_pop":
                    # Word-pop mode: show only active word in sequence
                    for w_idx, w in enumerate(line):
                        w_start = max(0.0, float(w.get("start", 0)) + start_offset)
                        w_end = max(w_start + 0.08, float(w.get("end", 0)) + start_offset)

                        if w_start > cur_time:
                            gap = w_start - cur_time
                            if gap >= 0.02:
                                concat_entries.append((empty_png, gap))
                                cur_time = w_start

                        dur = max(0.06, w_end - w_start)
                        f_path = os.path.join(tmp_dir, f"f_{frame_idx:04d}.png")
                        self._render_line_frame_pil(f_path, [w], active_word_index=0, style=style)
                        concat_entries.append((f_path, dur))
                        cur_time = w_end
                        frame_idx += 1
                else:
                    # Line / Karaoke mode: show full line with word-by-word active highlight
                    for w_idx, w in enumerate(line):
                        w_start = max(0.0, float(w.get("start", 0)) + start_offset)
                        w_end = max(w_start + 0.08, float(w.get("end", 0)) + start_offset)

                        # Gap before active word in line
                        if w_start > cur_time:
                            gap = w_start - cur_time
                            if gap >= 0.02:
                                f_path = os.path.join(tmp_dir, f"f_{frame_idx:04d}.png")
                                self._render_line_frame_pil(f_path, line, active_word_index=None, style=style)
                                concat_entries.append((f_path, gap))
                                cur_time = w_start
                                frame_idx += 1

                        dur = max(0.06, w_end - w_start)
                        f_path = os.path.join(tmp_dir, f"f_{frame_idx:04d}.png")
                        self._render_line_frame_pil(f_path, line, active_word_index=w_idx, style=style)
                        concat_entries.append((f_path, dur))
                        cur_time = w_end
                        frame_idx += 1

                    # Hold line if line_end is greater than last word end
                    if line_end > cur_time:
                        hold_dur = line_end - cur_time
                        if hold_dur >= 0.05:
                            f_path = os.path.join(tmp_dir, f"f_{frame_idx:04d}.png")
                            self._render_line_frame_pil(f_path, line, active_word_index=len(line) - 1, style=style)
                            concat_entries.append((f_path, hold_dur))
                            cur_time = line_end
                            frame_idx += 1

            # Trailing silence until end of video
            if video_dur > cur_time:
                concat_entries.append((empty_png, video_dur - cur_time))

            if not concat_entries:
                return video_path

            # Write concat.txt demuxer script
            concat_txt = os.path.join(tmp_dir, "concat.txt")
            with open(concat_txt, "w") as f:
                for png_p, dur in concat_entries:
                    f.write(f"file '{png_p}'\n")
                    f.write(f"duration {dur:.4f}\n")
                # Repeat last entry to ensure demuxer finishes properly
                f.write(f"file '{concat_entries[-1][0]}'\n")

            # FFmpeg single-pass concat overlay
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-f", "concat", "-safe", "0", "-i", concat_txt,
                "-filter_complex", "[0:v][1:v]overlay=x=0:y=0:shortest=1[outv]",
                "-map", "[outv]",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                "-c:a", "copy",
                "-movflags", "+faststart",
                output_path,
            ]

            logger.info(f"skia_subtitle: rendering '{style.get('id')}' ({len(concat_entries)} timing cuts) → {os.path.basename(output_path)}")
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=max(180, int(video_dur * 3 + 60)))
            if res.returncode != 0:
                logger.error(f"skia_subtitle FFmpeg overlay failed: {res.stderr[-400:]}")
                return self._ffmpeg_fallback(video_path, words, style, output_path, start_offset)

            logger.info(f"skia_subtitle: successfully composited → {output_path}")
            return output_path

        finally:
            # Cleanup temp files
            if os.path.exists(tmp_dir):
                for fname in os.listdir(tmp_dir):
                    try:
                        os.remove(os.path.join(tmp_dir, fname))
                    except OSError:
                        pass
                try:
                    os.rmdir(tmp_dir)
                except OSError:
                    pass

    def _render_line_frame_pil(
        self,
        output_png: str,
        words_line: list,
        active_word_index: Optional[int],
        style: dict,
    ) -> None:
        """Render a single full-resolution 1080x1920 PNG frame with exact preset visual identity."""
        img = Image.new("RGBA", (self._width, self._height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        preset_id = style.get("id", "glassmorphism")
        font_family = style.get("font_family", "Inter")
        font_size = int(style.get("font_size", 42))
        is_uppercase = style.get("uppercase", False)

        font = self._load_pil_font(font_family, font_size)

        # Prepare word text and dimensions
        word_items = []
        for idx, w_dict in enumerate(words_line):
            raw_w = str(w_dict.get("word", "")).strip()
            w_text = raw_w.upper() if is_uppercase else raw_w
            bbox = draw.textbbox((0, 0), w_text, font=font)
            w_width = max(1, bbox[2] - bbox[0])
            w_height = max(1, bbox[3] - bbox[1])
            word_items.append({
                "index": idx,
                "text": w_text,
                "width": w_width,
                "height": w_height,
                "is_active": (idx == active_word_index),
            })

        if not word_items:
            img.save(output_png, format="PNG")
            return

        spacing = max(16, int(font_size * 0.35))
        total_text_width = sum(item["width"] for item in word_items) + (len(word_items) - 1) * spacing

        # Center positions
        pos_y_pct = float(style.get("position_y_pct", 78))
        center_y = int(self._height * (pos_y_pct / 100.0))
        center_x = self._width // 2

        start_x = center_x - total_text_width // 2
        line_height = max(item["height"] for item in word_items)
        baseline_y = center_y - line_height // 2

        # ─── 1. Background / Card Shapes ──────────────────────────────────────
        card_pad_x = int(style.get("bg_padding", 28))
        card_pad_y = max(14, int(font_size * 0.32))
        card_left = max(30, start_x - card_pad_x)
        card_right = min(self._width - 30, start_x + total_text_width + card_pad_x)
        card_top = center_y - line_height // 2 - card_pad_y
        card_bottom = center_y + line_height // 2 + card_pad_y

        if preset_id == "glassmorphism":
            # Frosted glass card with glossy border & subtle inner shine
            draw.rounded_rectangle(
                [card_left, card_top, card_right, card_bottom],
                radius=20,
                fill=(30, 41, 59, int(255 * 0.70)),
                outline=(255, 255, 255, 140),
                width=2,
            )
        elif preset_id == "clean_editorial":
            # Minimalist Swiss slate pill card with slim border
            draw.rounded_rectangle(
                [card_left, card_top, card_right, card_bottom],
                radius=14,
                fill=(15, 23, 42, int(255 * 0.85)),
                outline=(255, 255, 255, 45),
                width=1,
            )
        elif preset_id == "podcast_pro":
            # Dark charcoal pill with emerald border & MIC dot
            mic_extra_left = 60
            c_left = max(30, card_left - mic_extra_left)
            draw.rounded_rectangle(
                [c_left, card_top, card_right, card_bottom],
                radius=999,
                fill=(18, 18, 22, int(255 * 0.92)),
                outline=(16, 185, 129, 150),
                width=2,
            )
            # Emerald MIC indicator dot
            dot_cx = c_left + 24
            dot_cy = center_y
            draw.ellipse([dot_cx - 6, dot_cy - 6, dot_cx + 6, dot_cy + 6], fill=(16, 185, 129, 255))
            mic_font = self._load_pil_font("Inter", 18)
            draw.text((dot_cx + 12, dot_cy - 10), "MIC", font=mic_font, fill=(16, 185, 129, 230))
        elif preset_id == "modern_mono":
            # Cyber Terminal window with mini header bar
            header_h = 28
            term_top = card_top - header_h
            draw.rounded_rectangle(
                [card_left, term_top, card_right, card_bottom],
                radius=10,
                fill=(8, 12, 20, int(255 * 0.94)),
                outline=(6, 182, 212, 220),
                width=2,
            )
            # Traffic light window dots
            draw.ellipse([card_left + 12, term_top + 8, card_left + 22, term_top + 18], fill=(239, 68, 68, 255))
            draw.ellipse([card_left + 26, term_top + 8, card_left + 36, term_top + 18], fill=(234, 179, 8, 255))
            draw.ellipse([card_left + 40, term_top + 8, card_left + 50, term_top + 18], fill=(34, 197, 94, 255))
            term_font = self._load_pil_font("Space Grotesk", 14)
            draw.text((card_left + 58, term_top + 5), "TERMINAL v2.0", font=term_font, fill=(6, 182, 212, 200))
            draw.line([card_left, term_top + header_h, card_right, term_top + header_h], fill=(6, 182, 212, 80), width=1)
        elif preset_id == "cinematic_slate":
            # Hollywood gold top & bottom rules
            draw.line([card_left - 10, card_top - 4, card_right + 10, card_top - 4], fill=(252, 211, 77, 200), width=2)
            draw.line([card_left - 10, card_bottom + 4, card_right + 10, card_bottom + 4], fill=(252, 211, 77, 200), width=2)
        elif style.get("bg_enabled"):
            # Generic customizable background pill
            bg_rgba = self._parse_rgba(style.get("bg_color", "#000000"), style.get("bg_opacity", 0.6))
            draw.rounded_rectangle(
                [card_left, card_top, card_right, card_bottom],
                radius=int(style.get("bg_radius", 16)),
                fill=bg_rgba,
            )

        # ─── 2. Draw Words with Highlights & Effects ───────────────────────────
        cur_x = start_x
        normal_color = self._parse_rgba(style.get("text_color", "#FFFFFF"), 1.0)
        highlight_color = self._parse_rgba(style.get("highlight_color", "#38BDF8"), 1.0)

        for item in word_items:
            w_text = item["text"]
            w_w = item["width"]
            is_active = item["is_active"]

            word_x = cur_x
            word_y = baseline_y

            if preset_id == "kinetic_word_box" and is_active:
                # Hot pink solid badge behind active word
                badge_pad_x = 12
                badge_pad_y = 6
                badge_box = [
                    word_x - badge_pad_x,
                    word_y - badge_pad_y,
                    word_x + w_w + badge_pad_x,
                    word_y + item["height"] + badge_pad_y,
                ]
                draw.rounded_rectangle(badge_box, radius=8, fill=(255, 0, 85, 255))
                # Text inside badge is crisp white
                draw.text((word_x, word_y), w_text, font=font, fill=(255, 255, 255, 255))

            elif preset_id == "neon_tube":
                if is_active:
                    # Hot pink multi-pass neon tube glow
                    draw.text((word_x, word_y), w_text, font=font, fill=(255, 0, 127, 80), stroke_width=8, stroke_fill=(255, 0, 127, 80))
                    draw.text((word_x, word_y), w_text, font=font, fill=(255, 0, 127, 180), stroke_width=4, stroke_fill=(255, 0, 127, 180))
                    draw.text((word_x, word_y), w_text, font=font, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(255, 0, 127, 255))
                else:
                    # Cyan hollow gas tube
                    draw.text((word_x, word_y), w_text, font=font, fill=(0, 255, 255, 60), stroke_width=5, stroke_fill=(0, 255, 255, 60))
                    draw.text((word_x, word_y), w_text, font=font, fill=(0, 0, 0, 0), stroke_width=2, stroke_fill=(0, 255, 255, 230))

            elif preset_id == "retro_chrome":
                # Heavy 3D shadow + outline
                if is_active:
                    draw.text((word_x + 3, word_y + 4), w_text, font=font, fill=(0, 0, 0, 240))
                    draw.text((word_x, word_y), w_text, font=font, fill=(251, 191, 36, 255), stroke_width=4, stroke_fill=(0, 0, 0, 255))
                else:
                    draw.text((word_x + 2, word_y + 3), w_text, font=font, fill=(0, 0, 0, 200))
                    draw.text((word_x, word_y), w_text, font=font, fill=(226, 232, 240, 255), stroke_width=3, stroke_fill=(0, 0, 0, 255))

            elif preset_id == "clean_editorial" and is_active:
                # Active word with cyan underline bar
                draw.text((word_x, word_y), w_text, font=font, fill=(56, 189, 248, 255))
                draw.line([word_x, word_y + item["height"] + 4, word_x + w_w, word_y + item["height"] + 4], fill=(56, 189, 248, 255), width=3)

            elif is_active:
                # Glowing active word highlight
                hl_color = highlight_color
                if style.get("glow_enabled", True):
                    glow_rgba = (hl_color[0], hl_color[1], hl_color[2], 120)
                    draw.text((word_x, word_y), w_text, font=font, fill=glow_rgba, stroke_width=5, stroke_fill=glow_rgba)
                draw.text((word_x, word_y), w_text, font=font, fill=hl_color)

            else:
                # Normal inactive word
                if style.get("shadow_enabled", False):
                    draw.text((word_x + 1, word_y + 2), w_text, font=font, fill=(0, 0, 0, 180))
                if style.get("stroke_enabled", False) and style.get("stroke_width", 0) > 0:
                    strk_c = self._parse_rgba(style.get("stroke_color", "#000000"), 1.0)
                    draw.text((word_x, word_y), w_text, font=font, fill=normal_color, stroke_width=style["stroke_width"], stroke_fill=strk_c)
                else:
                    draw.text((word_x, word_y), w_text, font=font, fill=normal_color)

            cur_x += w_w + spacing

        img.save(output_png, format="PNG")

    def _group_words_into_lines(self, words: list, max_per_line: int) -> list[list[dict]]:
        """Group words into lines respecting word count and natural speech pauses."""
        max_chars = 26
        lines = []
        current_line = []
        current_chars = 0

        for w in words:
            word_text = str(w.get("word", "")).strip()
            if not word_text:
                continue
            word_len = len(word_text)
            new_chars = current_chars + word_len + (1 if current_line else 0)
            word_count = len(current_line) + 1

            force_new = False
            if current_line:
                prev_end = float(current_line[-1].get("end", 0))
                curr_start = float(w.get("start", 0))
                if curr_start - prev_end > 0.45:
                    force_new = True

            if force_new or word_count > max_per_line or new_chars > max_chars:
                if current_line:
                    lines.append(current_line)
                current_line = [w]
                current_chars = word_len
            else:
                current_line.append(w)
                current_chars = new_chars

        if current_line:
            lines.append(current_line)

        return lines

    def _load_pil_font(self, font_family: str, font_size: int) -> ImageFont.FreeTypeFont:
        """Load requested Google Font with seamless fallback."""
        clean_name = font_family.replace(" ", "")
        candidates = [
            f"{font_family}-Bold.ttf",
            f"{font_family}-Regular.ttf",
            f"{font_family}-Variable.ttf",
            f"{clean_name}-Bold.ttf",
            f"{clean_name}-Regular.ttf",
            f"{clean_name}-Variable.ttf",
            "Inter-Variable.ttf",
            "Poppins-Bold.ttf",
            "Roboto-Bold.ttf",
        ]
        for name in candidates:
            path = os.path.join(self._font_dir, name)
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, font_size)
                except Exception:
                    pass
        return ImageFont.load_default()

    def _probe_duration(self, video_path: str) -> float:
        """Probe video duration in seconds via ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                return float(res.stdout.strip())
        except Exception:
            pass
        return 0.0

    @staticmethod
    def _parse_rgba(color_val: Any, opacity: float = 1.0) -> Tuple[int, int, int, int]:
        """Parse hex string, color name, or rgb into (R, G, B, A) tuple."""
        if not color_val:
            return 255, 255, 255, int(opacity * 255)

        s = str(color_val).strip()
        named_colors = {
            "white": (255, 255, 255),
            "black": (0, 0, 0),
            "cyan": (6, 182, 212),
            "gold": (252, 211, 77),
            "emerald": (16, 185, 129),
            "pink": (255, 0, 127),
            "red": (239, 68, 68),
            "slate": (148, 163, 184),
        }
        if s.lower() in named_colors:
            r, g, b = named_colors[s.lower()]
            return r, g, b, int(max(0.0, min(1.0, opacity)) * 255)

        # Remove #
        s = s.lstrip("#")
        try:
            if len(s) == 3:
                s = "".join(2 * c for c in s)
            if len(s) >= 6:
                r = int(s[0:2], 16)
                g = int(s[2:4], 16)
                b = int(s[4:6], 16)
                a = int(s[6:8], 16) if len(s) >= 8 else int(max(0.0, min(1.0, opacity)) * 255)
                return r, g, b, a
        except Exception:
            pass

        return 255, 255, 255, int(opacity * 255)

    def _ffmpeg_fallback(
        self,
        video_path: str,
        words: list,
        style: dict,
        output_path: str,
        start_offset: float,
    ) -> str:
        """Fallback: use FFmpeg drawtext with exact normalized style parameters."""
        from src.infrastructure.subtitle_renderer import SubtitleRenderer
        from src.domain.entities import SubtitleStyleConfig

        config = SubtitleStyleConfig(
            font_family=style.get("font_family", "Poppins"),
            font_size=int(style.get("font_size", 34)),
            font_weight=style.get("font_weight", "Bold"),
            color=style.get("text_color", "#FFFFFF"),
            highlight_color=style.get("highlight_color", "#38BDF8"),
            highlight_words=True,
            stroke_color=style.get("stroke_color", "#000000") if style.get("stroke_enabled") else "",
            stroke_width=int(style.get("stroke_width", 0)) if style.get("stroke_enabled") else 0,
            background_opacity=float(style.get("bg_opacity", 0.0)) if style.get("bg_enabled") else 0.0,
            position="bottom",
            padding_bottom=int(1920 * (1 - style.get("position_y_pct", 78) / 100)),
            uppercase=style.get("uppercase", False),
            max_words_per_line=int(style.get("max_words_per_line", 4)),
            line_transition=style.get("line_transition", "karaoke"),
            start_offset=start_offset,
        )

        renderer = SubtitleRenderer(font_dir=self._font_dir)
        return renderer.render_subtitles(video_path, words, config, output_path)
