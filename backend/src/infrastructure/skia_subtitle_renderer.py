"""SkiaSubtitleRenderer — High-definition GPU/Canvas-style subtitle rendering via Pillow + FFmpeg.

Renders subtitle frames matching the frontend Skia Canvas previews and FFmpeg previews 1:1:
- Glassmorphism: Frosted glass card with glossy border, inner top shine, and glowing active word
- Clean Editorial: Minimalist Swiss slate pill with cyan underline tracking
- Podcast Pro / Podcast Dialogue: Dark charcoal capsule with emerald MIC indicator dot and active speaker highlight
- Kinetic Word Box: Dynamic solid rounded badge encasing active word with clean horizontal spacing
- Neon Tube / Neon Glow: Hollow / multi-layer glowing neon text with triple-pass glow in cyan & hot magenta
- Gradient Fill: Multi-stop linear gradient text (indigo to pink) with active word in coral-gold gradient
- Cinematic Slate: Hollywood gold top and bottom rules with champagne gold active word
- Cinematic Bar: Full-width dark bar across the bottom with gold active word
- Modern Mono / Tech Mono: Cyber terminal box with traffic light dots, "TERMINAL v2.0" header bar, and cursor prompt
- Bold Impact / Bold Impact Stroke: Anton heavy shorts punch with solid thick black stroke and electric yellow/red active word
- Dual Layer Depth: 3D depth with purple backlight layer behind white text and gold active word
- Retro Chrome: 80s metallic chrome reflection vertical gradient with gold highlight and hard drop shadow
- Outline Stack: 3D anaglyphic red and cyan offset outline stack without fill, with white active word
- Hormozi Pop: Center-screen heavy impact font with thick solid 6px black outline and bright lime highlight
- Classic Karaoke: Clean Poppins bold text with golden yellow active word and dark drop shadow
- Devon Clean: Subtle rounded dark pill with crisp white typography and cyan active pop
- Fire Emphasis: Fiery orange-red highlight with intense warm shadow/glow and bold uppercase text
- Glass Blur: Translucent glass background card with rounded corners and sky blue highlight
- Gold Luxury: Champagne gold serif (Playfair Display) text with gold active word and soft drop shadow
- Minimal Lower: Clean lowercase documentary subtitle at bottom of the screen
"""
import logging
import math
import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from src.infrastructure.subtitle_styles import SKIA_STYLES, FFMPEG_STYLES, get_skia_style

logger = logging.getLogger(__name__)


# Indonesian / English stop words for emphasis word detection
STOP_WORDS = {
    "yang", "dan", "di", "ke", "dari", "ini", "itu", "dengan", "untuk",
    "pada", "adalah", "juga", "akan", "sudah", "udah", "gak", "nggak",
    "tidak", "bukan", "ada", "bisa", "lagi", "kalau", "aja", "sih",
    "ya", "dong", "deh", "nih", "tuh", "loh", "kan", "pun", "atau",
    "tapi", "jadi", "saya", "aku", "kamu", "dia", "kita", "mereka",
    "the", "is", "a", "to", "of", "in", "it", "and", "for", "but",
    "so", "he", "she", "we", "they", "an", "at", "by", "from",
}


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
        raw_preset_id = str(
            style.get("stylePreset")
            or style.get("preset")
            or style.get("id")
            or style.get("style_id")
            or "glassmorphism"
        ).strip().lower()
        preset_id = raw_preset_id.replace(" ", "_").replace("-", "_")

        base = {}
        if preset_id in SKIA_STYLES:
            base = dict(SKIA_STYLES[preset_id])
        elif raw_preset_id in SKIA_STYLES:
            base = dict(SKIA_STYLES[raw_preset_id])
        elif preset_id in FFMPEG_STYLES:
            base = dict(FFMPEG_STYLES[preset_id])
        elif raw_preset_id in FFMPEG_STYLES:
            base = dict(FFMPEG_STYLES[raw_preset_id])

        # Default font based on preset
        preset_default_fonts = {
            "glassmorphism": "Inter",
            "clean_editorial": "Inter",
            "podcast_pro": "Plus Jakarta Sans",
            "podcast_dialogue": "Plus Jakarta Sans",
            "kinetic_word_box": "Plus Jakarta Sans",
            "neon_tube": "Montserrat",
            "neon_glow": "Montserrat",
            "gradient_fill": "Poppins",
            "cinematic_slate": "Playfair Display",
            "cinematic_bar": "Oswald",
            "modern_mono": "Space Grotesk",
            "tech_mono": "Space Grotesk",
            "retro_chrome": "Bebas Neue",
            "outline_stack": "Archivo Black",
            "hormozi_pop": "Montserrat",
            "bold_impact": "Anton",
            "bold_impact_stroke": "Anton",
            "dual_layer": "Outfit",
            "devon_clean": "Inter",
            "classic_karaoke": "Poppins",
            "fire_emphasis": "Bebas Neue",
            "glass_blur": "Inter",
            "gold_luxury": "Playfair Display",
            "minimal_lower": "Inter",
        }
        default_font = preset_default_fonts.get(preset_id, "Inter")

        # Clamp max_words_per_line between 1 and 6
        raw_words_per_line = (
            style.get("maxWordsPerLine")
            or style.get("max_words_per_line")
            or base.get("max_words_per_line", 4)
        )
        try:
            max_words_per_line = max(1, min(6, int(raw_words_per_line)))
        except (ValueError, TypeError):
            max_words_per_line = 4

        # Font size
        raw_font_size = int(
            style.get("fontSize")
            or style.get("font_size")
            or base.get("font_size", 38)
        )

        pos_str = str(style.get("position") or base.get("position") or "").strip().lower()
        raw_y = (
            style.get("positionY")
            if style.get("positionY") is not None
            else style.get("position_y")
            if style.get("position_y") is not None
            else style.get("position_y_pct")
            if style.get("position_y_pct") is not None
            else base.get("position_y_pct")
        )
        if pos_str == "top":
            pos_y_pct = float(raw_y) if (raw_y is not None and float(raw_y) <= 35) else 15.0
        elif pos_str == "center":
            pos_y_pct = float(raw_y) if (raw_y is not None and 35 < float(raw_y) < 65) else 50.0
        elif pos_str == "bottom":
            pos_y_pct = float(raw_y) if (raw_y is not None and float(raw_y) >= 65) else 78.0
        else:
            try:
                pos_y_pct = float(raw_y) if raw_y is not None else 78.0
            except (ValueError, TypeError):
                pos_y_pct = 78.0

        normalized = {
            "id": preset_id,
            "position": pos_str or ("top" if pos_y_pct <= 35 else "center" if pos_y_pct < 65 else "bottom"),
            "font_family": style.get("fontFamily") or style.get("font_family") or base.get("font_family", default_font),
            "font_size": raw_font_size,
            "font_weight": str(style.get("fontWeight") or style.get("font_weight") or base.get("font_weight", "Bold")),
            "text_color": style.get("color") or style.get("text_color") or base.get("color") or base.get("text_color", "#FFFFFF"),
            "highlight_color": style.get("highlightColor") or style.get("highlight_color") or base.get("highlight_color", "#38BDF8"),
            "position_y_pct": pos_y_pct,
            "position_y": pos_y_pct,
            "grid_position_y": float(style.get("gridPositionY") or style.get("grid_position_y") or 50.0),
            "layout_events": list(style.get("layout_events") or style.get("layoutEvents") or []),
            "autogrid_enabled": bool(style.get("autogrid_enabled", True) if style.get("autogrid_enabled") is not None else style.get("autogridEnabled", True)),
            "reframe_layout": str(style.get("reframe_layout") or style.get("reframeLayout") or "single"),
            "max_words_per_line": max_words_per_line,
            "line_transition": style.get("lineTransition") or style.get("line_transition") or base.get("line_transition", "karaoke"),
            "uppercase": bool(style.get("uppercase", base.get("uppercase", False))),
            "capitalize": bool(style.get("capitalize", False)),
            "italic": bool(style.get("italic", False)),
            "enabled": style.get("enabled", True) is not False,
            "start_offset": float(style.get("start_offset", 0.0)),
            "word_spacing": style.get("wordSpacing") or style.get("word_spacing"),
            "highlight_bold": style.get("highlightBold", True),
            "highlight_scale": float(style.get("highlightScale") or 1.15),
            "highlight_words": [w.lower().strip() for w in (style.get("highlightWords") or style.get("highlight_words") or []) if w],
        }

        # Gradient parameters
        gradient_enabled = bool(
            style.get("gradientEnabled")
            or style.get("gradient_enabled")
            or base.get("gradient_enabled")
            or preset_id in ("gradient_fill", "retro_chrome")
        )
        normalized["gradient_enabled"] = gradient_enabled
        normalized["gradient_from"] = (
            style.get("gradientFrom")
            or style.get("gradient_from")
            or base.get("gradient_from")
            or "#00F0FF"
        )
        normalized["gradient_to"] = (
            style.get("gradientTo")
            or style.get("gradient_to")
            or base.get("gradient_to")
            or "#FF007F"
        )
        normalized["dual_layer"] = bool(style.get("dualLayer") or base.get("dual_layer") or preset_id == "dual_layer")
        normalized["retro_chrome"] = bool(style.get("retroChrome") or base.get("retro_chrome") or preset_id == "retro_chrome")
        normalized["outline_stack"] = bool(style.get("outlineStack") or base.get("outline_stack") or preset_id == "outline_stack")

        # Background parameters
        base_bg = base.get("background") if isinstance(base.get("background"), dict) else {}
        bg_opacity = style.get("bgOpacity")
        if bg_opacity is None:
            bg_opacity = style.get("bg_opacity")
        if bg_opacity is None:
            bg_opacity = base.get("background_opacity") or base_bg.get("bg_opacity")

        bg_enabled = bool(
            (bg_opacity is not None and float(bg_opacity) > 0)
            or style.get("bgEnabled")
            or style.get("bg_enabled")
            or style.get("glassmorphism")
            or bool(base_bg)
            or preset_id in ("glassmorphism", "clean_editorial", "podcast_pro", "podcast_dialogue", "modern_mono", "tech_mono", "devon_clean", "glass_blur", "cinematic_bar")
        )
        normalized["bg_enabled"] = bg_enabled
        normalized["bg_opacity"] = float(bg_opacity if bg_opacity is not None else (0.65 if bg_enabled else 0.0))
        normalized["bg_color"] = (
            style.get("bgColor")
            or style.get("bg_color")
            or base.get("background_color")
            or base_bg.get("bg_color")
            or ("#0F172A" if preset_id in ("clean_editorial", "devon_clean")
                else "#121216" if preset_id in ("podcast_pro", "podcast_dialogue")
                else "#090D16" if preset_id in ("modern_mono", "tech_mono")
                else "#1A1A1A" if preset_id == "cinematic_bar"
                else "#FFFFFF" if preset_id == "glass_blur"
                else "#1E293B")
        )
        normalized["bg_radius"] = int(
            style.get("bgRadius")
            or style.get("bg_radius")
            or base.get("background_radius")
            or base_bg.get("border_radius", 18 if preset_id != "cinematic_bar" else 0)
        )
        normalized["bg_padding"] = int(
            style.get("bgPadding")
            or style.get("bg_padding")
            or base_bg.get("padding_x", 24)
        )

        # Glow parameters (GPU effects & Glow Shader)
        glow_enabled = bool(
            style.get("glowEnabled")
            or style.get("glow_enabled")
            or style.get("highlightGlow")
            or style.get("highlight_glow")
            or base.get("glow_enabled")
            or preset_id in ("glassmorphism", "podcast_pro", "neon_tube", "neon_glow", "modern_mono", "cinematic_slate", "fire_emphasis")
        )
        normalized["glow_enabled"] = glow_enabled
        normalized["glow_color"] = (
            style.get("glowColor")
            or style.get("glow_color")
            or style.get("highlightGlowColor")
            or style.get("highlight_glow_color")
            or base.get("glow_color")
            or normalized["highlight_color"]
        )
        normalized["glow_radius"] = int(
            style.get("glowSize")
            or style.get("glow_size")
            or style.get("glowRadius")
            or style.get("glow_radius")
            or base.get("glow_radius", 16)
        )

        # Stroke / Border
        base_stroke = base.get("stroke") if isinstance(base.get("stroke"), dict) else {}
        stroke_enabled = bool(
            style.get("strokeEnabled")
            or style.get("stroke_enabled")
            or bool(base_stroke)
            or (base.get("stroke_width", 0) > 0)
            or preset_id in ("neon_tube", "neon_glow", "retro_chrome", "outline_stack", "hormozi_pop", "bold_impact", "bold_impact_stroke", "classic_karaoke", "fire_emphasis", "gold_luxury")
        )
        normalized["stroke_enabled"] = stroke_enabled
        raw_stroke_w = (
            style.get("strokeWidth")
            or style.get("stroke_width")
            or base.get("stroke_width")
            or base_stroke.get("width", 3 if stroke_enabled else 0)
        )
        normalized["stroke_width"] = max(2, int(raw_stroke_w)) if stroke_enabled else 0
        normalized["stroke_color"] = (
            style.get("strokeColor")
            or style.get("stroke_color")
            or base.get("stroke_color")
            or base_stroke.get("color", "#000000")
        )

        # Shadow
        base_shadow = base.get("shadow") if isinstance(base.get("shadow"), dict) else {}
        shadow_enabled = bool(
            style.get("shadowEnabled")
            or style.get("shadow_enabled")
            or bool(base_shadow)
            or (base.get("shadow_x", 0) > 0 or base.get("shadow_y", 0) > 0)
            or preset_id in ("clean_editorial", "podcast_pro", "kinetic_word_box", "gradient_fill", "retro_chrome", "hormozi_pop", "bold_impact", "classic_karaoke", "fire_emphasis", "gold_luxury", "cinematic_slate")
        )
        normalized["shadow_enabled"] = shadow_enabled
        normalized["shadow_color"] = (
            style.get("shadowColor")
            or style.get("shadow_color")
            or base.get("shadow_color")
            or base_shadow.get("color", "#000000")
        )

        # Active Word Badge (for kinetic_word_box, etc.)
        base_badge = base.get("active_word_badge") if isinstance(base.get("active_word_badge"), dict) else {}
        normalized["badge_bg_color"] = (
            style.get("badgeBgColor")
            or style.get("badge_bg_color")
            or style.get("highlight_badge_color")
            or base_badge.get("bg_color")
            or "#FF0055"
        )

        return normalized

    def _get_layout_at_time(self, layout_events: list[dict], time_sec: float) -> str:
        """Find active layout ('single' or 'double') at given time_sec."""
        if not layout_events:
            return "single"
        curr = "single"
        for ev in sorted(layout_events, key=lambda x: float(x.get("time", 0.0))):
            if float(ev.get("time", 0.0)) <= time_sec + 0.001:
                curr = str(ev.get("layout", "single")).lower()
            else:
                break
        return curr

    def render_subtitles(
        self,
        video_path: str,
        words: list,
        style: Any = None,
        output_path: str = "",
        start_offset: float = 0.0,
        layout_events: list[dict] | None = None,
        autogrid_enabled: bool = True,
        style_config: Any = None,
    ) -> str:
        """Render subtitles with rich Skia effects and Auto-Grid dynamic recentering."""
        if not os.path.exists(video_path):
            logger.warning(f"skia_subtitle: input missing {video_path}")
            return video_path

        if not words:
            logger.info("skia_subtitle: no words, skipping")
            if video_path != output_path and os.path.exists(video_path):
                import shutil
                shutil.copy2(video_path, output_path)
            return output_path

        effective_style = style if style is not None else style_config
        norm_style = self._normalize_style(effective_style)
        if layout_events is not None:
            norm_style["layout_events"] = list(layout_events)
        if autogrid_enabled is not None:
            norm_style["autogrid_enabled"] = bool(autogrid_enabled)

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
        max_words = style.get("max_words_per_line", 4)
        lines = self._group_words_into_lines(words, max_words)
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

                is_word_pop = style.get("line_transition") == "word_pop"

                # Show full line or single word pop with active word highlighted as speech progresses
                for w_idx, w in enumerate(line):
                    w_start = max(0.0, float(w.get("start", 0)) + start_offset)
                    w_end = max(w_start + 0.08, float(w.get("end", 0)) + start_offset)

                    # Gap before active word inside line
                    if w_start > cur_time:
                        gap = w_start - cur_time
                        if gap >= 0.02:
                            f_path = os.path.join(tmp_dir, f"f_{frame_idx:04d}.png")
                            if is_word_pop:
                                concat_entries.append((empty_png, gap))
                            else:
                                self._render_line_frame_pil(f_path, line, active_word_index=None, style=style, time_sec=cur_time)
                                concat_entries.append((f_path, gap))
                                frame_idx += 1
                            cur_time = w_start

                    dur = max(0.06, w_end - w_start)
                    f_path = os.path.join(tmp_dir, f"f_{frame_idx:04d}.png")
                    words_to_render = [w] if is_word_pop else line
                    active_idx = 0 if is_word_pop else w_idx
                    self._render_line_frame_pil(f_path, words_to_render, active_word_index=active_idx, style=style, time_sec=w_start)
                    concat_entries.append((f_path, dur))
                    cur_time = w_end
                    frame_idx += 1

                # Hold line if line_end is greater than last word end
                if line_end > cur_time:
                    hold_dur = line_end - cur_time
                    if hold_dur >= 0.05:
                        f_path = os.path.join(tmp_dir, f"f_{frame_idx:04d}.png")
                        words_to_render = [line[-1]] if is_word_pop else line
                        active_idx = 0 if is_word_pop else len(line) - 1
                        self._render_line_frame_pil(f_path, words_to_render, active_word_index=active_idx, style=style, time_sec=cur_time)
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
            from src.infrastructure.gpu_encoder import get_video_encoder_args
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-f", "concat", "-safe", "0", "-i", concat_txt,
                "-filter_complex", "[0:v][1:v]overlay=x=0:y=0:shortest=1[outv]",
                "-map", "[outv]",
                "-map", "0:a?",
                *get_video_encoder_args("medium"),
                "-c:a", "copy",
                "-movflags", "+faststart",
                output_path,
            ]

            style_id = style.get("id") or "custom"
            out_base = os.path.basename(output_path)
            logger.info("skia_subtitle: rendering '%s' (%s words/line, %s timing cuts) -> %s", style_id, max_words, len(concat_entries), out_base)
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
        time_sec: Optional[float] = None,
    ) -> None:
        """Render a single full-resolution 1080x1920 PNG frame with exact preset visual identity."""
        img = Image.new("RGBA", (self._width, self._height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        preset_id = style.get("id") or style.get("style_preset", "glassmorphism")
        font_family = style.get("font_family", "Inter")
        raw_font_size = int(style.get("font_size", 38))
        base_font_size = raw_font_size
        is_uppercase = style.get("uppercase", False)
        is_capitalize = style.get("capitalize", False)
        line_transition = style.get("line_transition", "karaoke")
        is_word_pop = (line_transition == "word_pop")
        is_emphasis = (line_transition == "emphasis")
        is_line_reveal = (line_transition == "line_reveal")
        keyword_list = [k.lower() for k in style.get("highlight_words", [])]

        # ── Handle Emphasis Mode (Big Keyword + Small Context) ──
        if is_emphasis and len(words_line) > 1:
            raw_words = [str(w.get("word", "")).strip() for w in words_line]
            emph_idx = 0
            best_len = 0
            for idx, rw in enumerate(raw_words):
                w_clean = rw.lower().replace(",", "").replace(".", "").replace("!", "").replace("?", "")
                if w_clean not in STOP_WORDS and len(w_clean) > best_len:
                    best_len = len(w_clean)
                    emph_idx = idx

            context_words = [raw_words[i] for i in range(len(raw_words)) if i != emph_idx]
            context_text = " ".join(context_words)
            emph_text = raw_words[emph_idx]

            if is_uppercase:
                context_text = context_text.upper()
                emph_text = emph_text.upper()
            elif is_capitalize:
                context_text = context_text.capitalize()
                emph_text = emph_text.capitalize()

            ctx_font_size = max(18, int(base_font_size * 0.55))
            emph_font_size = int(base_font_size * 1.35)
            ctx_font = self._load_pil_font(font_family, ctx_font_size)
            emph_font = self._load_pil_font(font_family, emph_font_size)

            ctx_bbox = draw.textbbox((0, 0), context_text, font=ctx_font) if context_text else (0, 0, 0, 0)
            emph_bbox = draw.textbbox((0, 0), emph_text, font=emph_font)
            ctx_w = ctx_bbox[2] - ctx_bbox[0]
            ctx_h = ctx_bbox[3] - ctx_bbox[1]
            emph_w = emph_bbox[2] - emph_bbox[0]
            emph_h = emph_bbox[3] - emph_bbox[1]

            pos_y_pct = float(style.get("position_y") if style.get("position_y") is not None else style.get("position_y_pct", 78))
            center_y = int(self._height * (pos_y_pct / 100.0))
            center_x = self._width // 2

            # Draw context
            if context_text:
                draw.text((center_x - ctx_w // 2 + 2, center_y - emph_h // 2 - ctx_h - 10 + 2), context_text, font=ctx_font, fill=(0, 0, 0, 220))
                draw.text((center_x - ctx_w // 2, center_y - emph_h // 2 - ctx_h - 10), context_text, font=ctx_font, fill=self._parse_rgba(style.get("text_color", "#FFFFFF"), 1.0))

            # Draw emphasis keyword
            hl_color = self._parse_rgba(style.get("highlight_color", "#FFA500"), 1.0)
            # Drop shadow
            draw.text((center_x - emph_w // 2 + 3, center_y - emph_h // 2 + 4), emph_text, font=emph_font, fill=(0, 0, 0, 255))
            # Glow if enabled
            if style.get("glow_enabled", True):
                draw.text((center_x - emph_w // 2, center_y - emph_h // 2), emph_text, font=emph_font, fill=hl_color, stroke_width=8, stroke_fill=hl_color)
            # Outline & Main Text
            draw.text((center_x - emph_w // 2, center_y - emph_h // 2), emph_text, font=emph_font, fill=hl_color, stroke_width=4, stroke_fill=(0, 0, 0, 255))
            img.save(output_png, format="PNG")
            return

        # Prepare normal base font for consistent slot layout
        font_weight = str(style.get("font_weight", "Bold"))
        normal_font = self._load_pil_font(font_family, base_font_size, font_weight)

        # Prepare word items with base measurements (FIXED SLOT LAYOUT)
        word_items = []
        for idx, w_dict in enumerate(words_line):
            raw_w = str(w_dict.get("word", "")).strip()
            if is_uppercase:
                w_text = raw_w.upper()
            elif is_capitalize:
                w_text = raw_w.capitalize()
            else:
                w_text = raw_w

            is_active = (idx == active_word_index)
            is_keyword = raw_w.lower() in keyword_list
            should_highlight = is_active or is_keyword

            bbox = draw.textbbox((0, 0), w_text, font=normal_font)
            base_w = max(1, bbox[2] - bbox[0])
            base_h = max(1, bbox[3] - bbox[1])
            word_items.append({
                "index": idx,
                "text": w_text,
                "base_w": base_w,
                "base_h": base_h,
                "bbox": bbox,
                "is_active": should_highlight,
            })

        if not word_items:
            img.save(output_png, format="PNG")
            return

        # Natural word spacing calculation
        space_bbox = draw.textbbox((0, 0), " ", font=normal_font)
        natural_space_w = max(14, space_bbox[2] - space_bbox[0])
        user_spacing = style.get("word_spacing")
        if user_spacing is not None:
            spacing = int(user_spacing * 2.2)
        else:
            spacing = natural_space_w + max(16, int(base_font_size * 0.26))
        if preset_id == "kinetic_word_box":
            spacing = max(spacing, 28)

        total_text_width = sum(item["base_w"] for item in word_items) + (len(word_items) - 1) * spacing

        # Auto-scale font if line exceeds safe margins (920px)
        max_safe_width = 920
        if total_text_width > max_safe_width:
            scale_factor = max_safe_width / total_text_width
            base_font_size = max(22, int(base_font_size * scale_factor))
            normal_font = self._load_pil_font(font_family, base_font_size, font_weight)
            spacing = max(14, int(spacing * scale_factor))
            for item in word_items:
                bbox = draw.textbbox((0, 0), item["text"], font=normal_font)
                item["base_w"] = max(1, bbox[2] - bbox[0])
                item["base_h"] = max(1, bbox[3] - bbox[1])
                item["bbox"] = bbox
            total_text_width = sum(item["base_w"] for item in word_items) + (len(word_items) - 1) * spacing

        # Active font for highlights (scales outward around fixed slot centers)
        active_scale = float(style.get("highlight_scale") or 1.15) if (style.get("highlight_bold") is not False or is_word_pop) else 1.0
        active_font_size = int(base_font_size * active_scale)
        active_weight = "Black" if (is_word_pop or style.get("highlight_bold") is not False) else font_weight
        active_font = self._load_pil_font(font_family, active_font_size, active_weight)

        # Position calculation with Auto-Grid Dynamic Centering
        default_pos_y = float(style.get("position_y") if style.get("position_y") is not None else style.get("position_y_pct", 78))
        layout_events = style.get("layout_events") or []
        autogrid_enabled = bool(style.get("autogrid_enabled", True))

        if autogrid_enabled and layout_events and time_sec is not None:
            active_layout = self._get_layout_at_time(layout_events, time_sec)
            if active_layout in ("double", "grid", "2-grid", "split"):
                pos_y_pct = float(style.get("grid_position_y") or 50.0)
            else:
                pos_y_pct = default_pos_y
        elif autogrid_enabled and style.get("reframe_layout") in ("double", "grid", "2-grid", "split") and not layout_events:
            pos_y_pct = float(style.get("grid_position_y") or 50.0)
        else:
            pos_y_pct = default_pos_y

        center_y = int(self._height * (pos_y_pct / 100.0))
        center_x = self._width // 2
        line_height = max(item["base_h"] for item in word_items)

        # ─── 1. Background / Card Shapes (Fixed Dimensions Across Line) ────────
        user_pad = style.get("bg_padding")
        card_pad_x = int(user_pad * 1.5) if user_pad is not None else max(32, int(base_font_size * 0.6))
        card_pad_y = int(user_pad * 0.8) if user_pad is not None else max(16, int(base_font_size * 0.38))

        is_podcast = preset_id in ("podcast_pro", "podcast_dialogue")
        mic_extra_width = 72 if is_podcast else 0

        card_total_w = total_text_width + (card_pad_x * 2) + mic_extra_width
        card_left = center_x - card_total_w // 2
        card_right = card_left + card_total_w
        card_top = center_y - line_height // 2 - card_pad_y
        card_bottom = center_y + line_height // 2 + card_pad_y

        start_x = card_left + card_pad_x + mic_extra_width if is_podcast else (center_x - total_text_width // 2)

        # Compute fixed slots for each word on this line
        word_slots = []
        curr_x = start_x
        for item in word_items:
            mid_x = curr_x + item["base_w"] / 2.0
            word_slots.append({
                "x": curr_x,
                "mid_x": mid_x,
                "base_w": item["base_w"],
                "base_h": item["base_h"],
                "bbox": item["bbox"],
                "item": item,
            })
            curr_x += item["base_w"] + spacing

        if preset_id == "glassmorphism":
            # Frosted glass card with glossy border & top inner shine
            glass_opacity = float(style.get("bg_opacity", 0.45))
            draw.rounded_rectangle(
                [card_left, card_top, card_right, card_bottom],
                radius=int(style.get("bg_radius", 20)),
                fill=(30, 41, 59, int(255 * glass_opacity)),
                outline=(255, 255, 255, 140),
                width=2,
            )
            # Top edge subtle highlight
            draw.line([card_left + 16, card_top + 2, card_right - 16, card_top + 2], fill=(255, 255, 255, 60), width=1)

        elif preset_id in ("clean_editorial", "devon_clean"):
            # Minimalist Swiss slate pill card with slim border
            draw.rounded_rectangle(
                [card_left, card_top, card_right, card_bottom],
                radius=int(style.get("bg_radius", 14)),
                fill=(15, 23, 42, int(255 * float(style.get("bg_opacity", 0.75)))),
                outline=(255, 255, 255, 45),
                width=1,
            )

        elif is_podcast:
            # Dark charcoal pill with emerald border & MIC dot
            draw.rounded_rectangle(
                [card_left, card_top, card_right, card_bottom],
                radius=min(card_total_w, card_bottom - card_top) // 2,
                fill=(18, 18, 22, int(255 * float(style.get("bg_opacity", 0.85)))),
                outline=(16, 185, 129, 160),
                width=2,
            )
            # Emerald MIC indicator dot + text
            dot_cx = card_left + 24
            dot_cy = center_y
            draw.ellipse([dot_cx - 5, dot_cy - 5, dot_cx + 5, dot_cy + 5], fill=(16, 185, 129, 255))
            mic_font = self._load_pil_font("Inter", max(13, int(base_font_size * 0.32)))
            draw.text((dot_cx + 10, dot_cy - 8), "MIC", font=mic_font, fill=(16, 185, 129, 240))

        elif preset_id in ("modern_mono", "tech_mono"):
            # Cyber Terminal window with mini header bar
            header_h = 32
            term_top = card_top - header_h
            draw.rounded_rectangle(
                [card_left, term_top, card_right, card_bottom],
                radius=int(style.get("bg_radius", 10)),
                fill=(8, 12, 20, int(255 * float(style.get("bg_opacity", 0.9)))),
                outline=(6, 182, 212, 220),
                width=2,
            )
            # Traffic light window dots
            draw.ellipse([card_left + 12, term_top + 10, card_left + 22, term_top + 20], fill=(239, 68, 68, 255))
            draw.ellipse([card_left + 26, term_top + 10, card_left + 36, term_top + 20], fill=(234, 179, 8, 255))
            draw.ellipse([card_left + 40, term_top + 10, card_left + 50, term_top + 20], fill=(34, 197, 94, 255))
            term_font = self._load_pil_font("Space Grotesk", max(14, int(base_font_size * 0.35)))
            draw.text((card_left + 58, term_top + 7), "TERMINAL v2.0", font=term_font, fill=(6, 182, 212, 210))
            draw.line([card_left, term_top + header_h, card_right, term_top + header_h], fill=(6, 182, 212, 80), width=1)

        elif preset_id == "cinematic_bar":
            # Full width cinematic dark bar across bottom
            draw.rectangle([0, card_top, self._width, card_bottom], fill=(26, 26, 26, int(255 * 0.85)))
            draw.line([0, card_top, self._width, card_top], fill=(255, 215, 0, 180), width=2)
            draw.line([0, card_bottom, self._width, card_bottom], fill=(255, 215, 0, 180), width=2)

        elif preset_id == "glass_blur":
            # Translucent frosted white panel
            draw.rounded_rectangle(
                [card_left, card_top, card_right, card_bottom],
                radius=int(style.get("bg_radius", 16)),
                fill=(255, 255, 255, int(255 * float(style.get("bg_opacity", 0.35)))),
                outline=(255, 255, 255, 120),
                width=1,
            )

        elif preset_id == "cinematic_slate":
            # Hollywood gold top & bottom rules
            draw.line([card_left - 10, card_top - 4, card_right + 10, card_top - 4], fill=(252, 211, 77, 210), width=2)
            draw.line([card_left - 10, card_bottom + 4, card_right + 10, card_bottom + 4], fill=(252, 211, 77, 210), width=2)

        elif style.get("bg_enabled"):
            # Generic customizable background pill
            bg_rgba = self._parse_rgba(style.get("bg_color", "#000000"), style.get("bg_opacity", 0.6))
            draw.rounded_rectangle(
                [card_left, card_top, card_right, card_bottom],
                radius=int(style.get("bg_radius", 14)),
                fill=bg_rgba,
            )

        if is_line_reveal:
            # Top progress accent bar for line reveal
            draw.line([card_left + 10, card_top + 4, card_right - 10, card_top + 4], fill=self._parse_rgba(style.get("highlight_color", "#38BDF8"), 1.0), width=3)

        # ─── 2. Calculate Word Geometry and Positions ─────────────────────────
        normal_color = self._parse_rgba(style.get("text_color", "#FFFFFF"), 1.0)
        highlight_color = self._parse_rgba(style.get("highlight_color", "#38BDF8"), 1.0)

        slots_info = []
        for slot in word_slots:
            item = slot["item"]
            w_text = item["text"]
            is_active = item["is_active"]

            if is_active:
                f = active_font
                act_bbox = draw.textbbox((0, 0), w_text, font=f)
                act_w = max(1, act_bbox[2] - act_bbox[0])
                act_h = max(1, act_bbox[3] - act_bbox[1])
                word_x = int(slot["mid_x"] - act_w / 2.0) - act_bbox[0]
                word_y = int(center_y - act_h / 2.0) - act_bbox[1]
            else:
                f = normal_font
                act_w = slot["base_w"]
                act_h = slot["base_h"]
                base_bbox = slot["bbox"]
                word_x = slot["x"] - base_bbox[0]
                word_y = int(center_y - act_h / 2.0) - base_bbox[1]

            slots_info.append({
                "slot": slot,
                "item": item,
                "text": w_text,
                "is_active": is_active,
                "font": f,
                "act_w": act_w,
                "act_h": act_h,
                "word_x": word_x,
                "word_y": word_y,
            })

        # ─── 3. Atmospheric Glow Bloom Pass (Dual-stage Gaussian Blur) ────────
        glow_on = bool(
            style.get("glow_enabled")
            or style.get("glowEnabled")
            or style.get("highlight_glow")
            or style.get("highlightGlow")
            or preset_id in ("neon_tube", "neon_glow", "glassmorphism", "podcast_pro", "modern_mono", "cinematic_slate", "fire_emphasis")
        )
        if glow_on:
            glow_color_str = (
                style.get("glow_color")
                or style.get("glowColor")
                or style.get("highlight_glow_color")
                or style.get("highlightGlowColor")
                or style.get("highlight_color")
                or "#00FFFF"
            )
            glow_c = self._parse_rgba(glow_color_str, 1.0)
            glow_rad = max(6, int(style.get("glow_radius") or style.get("glowSize") or style.get("glow_size") or 16))

            glow_layer = Image.new("RGBA", (self._width, self._height), (0, 0, 0, 0))
            g_draw = ImageDraw.Draw(glow_layer)

            has_glow_items = False
            for s in slots_info:
                if s["is_active"]:
                    g_draw.text((s["word_x"], s["word_y"]), s["text"], font=s["font"], fill=glow_c, stroke_width=glow_rad * 2, stroke_fill=glow_c)
                    has_glow_items = True
                elif preset_id in ("neon_tube", "neon_glow"):
                    cyan_c = (6, 182, 212, 180)
                    g_draw.text((s["word_x"], s["word_y"]), s["text"], font=s["font"], fill=cyan_c, stroke_width=8, stroke_fill=cyan_c)
                    has_glow_items = True

            if has_glow_items:
                wide_glow = glow_layer.filter(ImageFilter.GaussianBlur(radius=glow_rad))
                core_glow = glow_layer.filter(ImageFilter.GaussianBlur(radius=max(3, glow_rad // 2)))
                img = Image.alpha_composite(img, wide_glow)
                img = Image.alpha_composite(img, core_glow)
                draw = ImageDraw.Draw(img)

        # ─── 4. Word Drawing Pass (Drop Shadows, Strokes, Fills & Gradients) ──
        gradient_on = bool(style.get("gradient_enabled") or style.get("gradientEnabled") or preset_id in ("gradient_fill", "retro_chrome"))
        grad_from = style.get("gradient_from") or style.get("gradientFrom") or "#00F0FF"
        grad_to = style.get("gradient_to") or style.get("gradientTo") or "#FF007F"

        for s in slots_info:
            w_text = s["text"]
            is_active = s["is_active"]
            f = s["font"]
            word_x = s["word_x"]
            word_y = s["word_y"]
            act_w = s["act_w"]
            act_h = s["act_h"]
            slot = s["slot"]

            if preset_id == "kinetic_word_box" and is_active:
                # Solid rounded badge behind active word
                badge_pad_x = max(16, int(base_font_size * 0.35))
                badge_pad_y = max(8, int(base_font_size * 0.20))
                badge_box = [
                    int(slot["mid_x"] - (act_w + badge_pad_x * 2) / 2.0),
                    int(center_y - (act_h + badge_pad_y * 2) / 2.0),
                    int(slot["mid_x"] + (act_w + badge_pad_x * 2) / 2.0),
                    int(center_y + (act_h + badge_pad_y * 2) / 2.0),
                ]
                badge_color_hex = style.get("badge_bg_color") or style.get("highlight_badge_color") or "#FF0055"
                badge_color = self._parse_rgba(badge_color_hex, 1.0)
                draw.rounded_rectangle(badge_box, radius=10, fill=badge_color)
                draw.text((word_x, word_y), w_text, font=f, fill=(255, 255, 255, 255))
                continue

            if preset_id == "dual_layer":
                # 3D depth with purple backlight layer behind sharp text
                draw.text((word_x, word_y + 4), w_text, font=f, fill=(124, 58, 237, 160), stroke_width=5, stroke_fill=(124, 58, 237, 160))

            elif preset_id == "outline_stack":
                # 3D anaglyphic red and cyan offset outline stack
                draw.text((word_x - 3, word_y - 2), w_text, font=f, fill=(0, 0, 0, 0), stroke_width=2, stroke_fill=(255, 50, 50, 220))
                draw.text((word_x + 3, word_y + 2), w_text, font=f, fill=(0, 0, 0, 0), stroke_width=2, stroke_fill=(0, 240, 255, 220))

            elif preset_id in ("clean_editorial", "devon_clean") and is_active:
                # Active word with cyan underline bar
                draw.line([word_x, word_y + act_h + 4, word_x + act_w, word_y + act_h + 4], fill=self._parse_rgba(style.get("highlight_color", "#38BDF8"), 1.0), width=4)

            # 1. Drop shadow
            shadow_enabled = style.get("shadow_enabled", True)
            if shadow_enabled:
                draw.text((word_x + 3, word_y + 4), w_text, font=f, fill=(0, 0, 0, 240))

            # 2. Text Stroke / Outline
            strk_enabled = style.get("stroke_enabled", True)
            if strk_enabled or preset_id in ("bold_impact", "bold_impact_stroke", "hormozi_pop", "fire_emphasis", "neon_tube", "neon_glow"):
                raw_w = style.get("stroke_width")
                strk_width = max(2, int(raw_w)) if raw_w is not None and int(raw_w) > 0 else (5 if is_active else 4)
                strk_c = self._parse_rgba(style.get("stroke_color", "#000000"), 1.0)
                draw.text((word_x, word_y), w_text, font=f, fill=(0, 0, 0, 0), stroke_width=strk_width, stroke_fill=strk_c)

            # 3. Text Fill (Gradient or Solid Color)
            if is_active and gradient_on:
                grad_img, offset = self._create_gradient_text(w_text, f, grad_from=grad_from, grad_to=grad_to)
                img.paste(grad_img, (word_x + offset[0], word_y + offset[1]), grad_img)
            elif is_active:
                draw.text((word_x, word_y), w_text, font=f, fill=highlight_color)
            else:
                draw.text((word_x, word_y), w_text, font=f, fill=normal_color)
        img.save(output_png, format="PNG")

    def _group_words_into_lines(self, words: list, max_per_line: int) -> list[list[dict]]:
        """Group words into lines respecting word count, punctuation, and natural speech pauses."""
        import re
        max_chars = max(28, max_per_line * 14)
        lines = []
        current_line = []
        current_chars = 0

        for i, w in enumerate(words):
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
                if curr_start - prev_end > 0.5:
                    force_new = True
                prev_word = str(current_line[-1].get("word", "")).strip()
                if bool(re.search(r"[.!?;:]$", prev_word)) and len(current_line) >= 2:
                    force_new = True

            if force_new or word_count > max_per_line or (word_count > 1 and new_chars > max_chars):
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

    def _load_pil_font(self, font_family: str, font_size: int, font_weight: str = "Bold") -> ImageFont.FreeTypeFont:
        """Load requested Google Font with seamless fallback and heavy weight prioritization."""
        clean_name = font_family.replace(" ", "").replace("-", "").lower()
        search_dirs = [
            self._font_dir,
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts")),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "assets", "fonts")),
            os.path.abspath(os.path.join(os.getcwd(), "assets", "fonts")),
        ]

        is_heavy = str(font_weight).lower() in ("bold", "black", "extrabold", "heavy", "900", "800", "700")

        # Specific font family candidates
        candidates = []
        if is_heavy:
            candidates.extend([
                f"{font_family}-Bold.ttf",
                f"{font_family}-Black.ttf",
                f"{font_family}-ExtraBold.ttf",
                f"{font_family}Condensed-Bold.ttf",
                f"{clean_name}-Bold.ttf",
                f"{font_family}-Regular.ttf",  # e.g. Anton-Regular, ArchivoBlack-Regular are naturally heavy 900
                "Anton-Regular.ttf",
                "ArchivoBlack-Regular.ttf",
                "Poppins-Bold.ttf",
                "Roboto-Bold.ttf",
                "Oswald-Bold.ttf",
                "BarlowCondensed-Bold.ttf",
                f"{font_family}-Variable.ttf",
            ])
        else:
            candidates.extend([
                f"{font_family}-Regular.ttf",
                f"{font_family}-Variable.ttf",
                f"{font_family}-Bold.ttf",
                "Inter-Variable.ttf",
                "Poppins-Bold.ttf",
            ])

        for fdir in search_dirs:
            if not fdir or not os.path.exists(fdir):
                continue
            for name in candidates:
                path = os.path.join(fdir, name)
                if os.path.exists(path):
                    try:
                        return ImageFont.truetype(path, font_size)
                    except Exception:
                        pass

        # If font not found by candidate, search directory for matching family
        for fdir in search_dirs:
            if not fdir or not os.path.exists(fdir):
                continue
            for file_name in os.listdir(fdir):
                if not file_name.lower().endswith((".ttf", ".otf")):
                    continue
                c_name = file_name.replace(" ", "").replace("-", "").lower()
                if clean_name in c_name:
                    try:
                        return ImageFont.truetype(os.path.join(fdir, file_name), font_size)
                    except Exception:
                        pass

        # Guaranteed fallback
        return ImageFont.load_default()

    def _parse_rgba(self, color_str: str, opacity: float = 1.0) -> Tuple[int, int, int, int]:
        """Convert CSS hex or rgba string into Pillow RGBA tuple (0-255)."""
        if not color_str:
            return (255, 255, 255, int(opacity * 255))
        c = color_str.strip().lower()
        if c.startswith("#"):
            c = c.lstrip("#")
            if len(c) == 3:
                c = "".join([x * 2 for x in c])
            if len(c) == 6:
                r = int(c[0:2], 16)
                g = int(c[2:4], 16)
                b = int(c[4:6], 16)
                return (r, g, b, int(opacity * 255))
            if len(c) == 8:
                r = int(c[0:2], 16)
                g = int(c[2:4], 16)
                b = int(c[4:6], 16)
                a = int(c[6:8], 16)
                return (r, g, b, int(a * opacity))
        elif c.startswith("rgba"):
            parts = c.replace("rgba(", "").replace(")", "").split(",")
            if len(parts) >= 4:
                return (
                    int(parts[0].strip()),
                    int(parts[1].strip()),
                    int(parts[2].strip()),
                    int(float(parts[3].strip()) * opacity * 255),
                )
        elif c.startswith("rgb"):
            parts = c.replace("rgb(", "").replace(")", "").split(",")
            if len(parts) >= 3:
                return (
                    int(parts[0].strip()),
                    int(parts[1].strip()),
                    int(parts[2].strip()),
                    int(opacity * 255),
                )
        return (255, 255, 255, int(opacity * 255))

    def _create_gradient_text(
        self,
        text: str,
        font: ImageFont.FreeTypeFont,
        grad_from: str = "#00F0FF",
        grad_to: str = "#FF007F",
        direction: str = "vertical",
    ) -> Tuple[Image.Image, Tuple[int, int]]:
        """Generate a linear gradient text RGBA image and alignment offset."""
        dummy = Image.new("RGBA", (1, 1))
        d = ImageDraw.Draw(dummy)
        bbox = d.textbbox((0, 0), text, font=font)
        text_w = max(1, bbox[2] - bbox[0])
        text_h = max(1, bbox[3] - bbox[1])

        grad_img = Image.new("RGBA", (text_w, text_h))
        c1 = self._parse_rgba(grad_from, 1.0)
        c2 = self._parse_rgba(grad_to, 1.0)
        g_draw = ImageDraw.Draw(grad_img)

        if direction == "vertical":
            for y in range(text_h):
                t = y / float(text_h - 1) if text_h > 1 else 0
                r = int(c1[0] * (1 - t) + c2[0] * t)
                g = int(c1[1] * (1 - t) + c2[1] * t)
                b = int(c1[2] * (1 - t) + c2[2] * t)
                a = int(c1[3] * (1 - t) + c2[3] * t)
                g_draw.line([(0, y), (text_w, y)], fill=(r, g, b, a))
        else:
            for x in range(text_w):
                t = x / float(text_w - 1) if text_w > 1 else 0
                r = int(c1[0] * (1 - t) + c2[0] * t)
                g = int(c1[1] * (1 - t) + c2[1] * t)
                b = int(c1[2] * (1 - t) + c2[2] * t)
                a = int(c1[3] * (1 - t) + c2[3] * t)
                g_draw.line([(x, 0), (x, text_h)], fill=(r, g, b, a))

        mask_img = Image.new("L", (text_w, text_h), 0)
        m_draw = ImageDraw.Draw(mask_img)
        m_draw.text((-bbox[0], -bbox[1]), text, font=font, fill=255)

        out_img = Image.new("RGBA", (text_w, text_h), (0, 0, 0, 0))
        out_img.paste(grad_img, (0, 0), mask_img)
        return out_img, (bbox[0], bbox[1])

    def _probe_duration(self, video_path: str) -> float:
        """Get duration of video in seconds."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                return float(res.stdout.strip())
        except Exception:
            pass
        return 0.0

    def _ffmpeg_fallback(
        self,
        video_path: str,
        words: list,
        style: dict,
        output_path: str,
        start_offset: float,
    ) -> str:
        """Graceful fallback to SubtitleRenderer if Pillow or FFmpeg overlay errors."""
        try:
            from src.infrastructure.subtitle_renderer import SubtitleRenderer
            from src.domain.entities import SubtitleStyleConfig
            renderer = SubtitleRenderer(font_dir=self._font_dir)
            cfg = SubtitleStyleConfig.from_dict(style)
            return renderer._render_line_only(
                video_path=video_path,
                words=words,
                config=cfg,
                output_path=output_path,
                offset=start_offset,
                timing_adj=0.0,
            )
        except Exception as e:
            logger.error(f"skia_subtitle fallback failed: {e}")
            if video_path != output_path and os.path.exists(video_path):
                import shutil
                shutil.copy2(video_path, output_path)
            return output_path
