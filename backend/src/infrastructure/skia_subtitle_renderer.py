"""SkiaSubtitleRenderer — GPU-accelerated subtitle rendering via Skia (skia-python).

Renders subtitle frames as PNG overlays, then composites onto video via FFmpeg.
Supports: gradients, rounded backgrounds, glow, blur, per-word coloring, shadows.
Falls back to FFmpeg drawtext if skia-python is not installed.
"""
import logging
import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from src.infrastructure.subtitle_styles import SKIA_STYLES, get_skia_style

logger = logging.getLogger(__name__)

try:
    import skia
    SKIA_AVAILABLE = True
except ImportError:
    SKIA_AVAILABLE = False
    logger.info("skia-python not installed — SkiaSubtitleRenderer will use FFmpeg fallback")


class SkiaSubtitleRenderer:
    """Render subtitles using Skia/CanvasKit for advanced visual effects.

    Pipeline:
    1. For each word group (line), render a PNG frame with text + effects
    2. Use FFmpeg overlay filter with enable/between to composite each frame at correct time
    3. Result: video with GPU-quality text that supports gradients, glow, blur, etc.
    """

    def __init__(self, font_dir: str = "assets/fonts", width: int = 1080, height: int = 1920):
        self._font_dir = font_dir
        self._width = width
        self._height = height

    def _normalize_style(self, style: Any) -> dict:
        """Normalize style dict from frontend camelCase or backend preset format."""
        if not isinstance(style, dict):
            style = {}

        # Look up preset by ID if provided
        preset_id = style.get("id") or style.get("style_id") or ""
        base = dict(SKIA_STYLES.get(preset_id, {})) if preset_id in SKIA_STYLES else {}

        normalized = {
            "id": preset_id or base.get("id", "glassmorphism"),
            "font_family": style.get("fontFamily") or style.get("font_family") or base.get("font_family", "Inter"),
            "font_size": int(style.get("fontSize") or style.get("font_size") or base.get("font_size", 34)),
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
        )
        base_bg = base.get("background") or {}
        normalized["bg_enabled"] = bg_enabled
        normalized["bg_opacity"] = float(style.get("bgOpacity") or style.get("bg_opacity") or base_bg.get("bg_opacity", 0.45) if bg_enabled else 0.0)
        normalized["bg_color"] = style.get("bgColor") or style.get("bg_color") or base_bg.get("bg_color", "#1E293B")
        normalized["bg_radius"] = int(style.get("bgRadius") or style.get("bg_radius") or base_bg.get("border_radius", 16))
        normalized["bg_padding"] = int(style.get("bgPadding") or style.get("bg_padding") or base_bg.get("padding_x", 20))
        normalized["blur_radius"] = int(style.get("blurRadius") or style.get("blur_radius") or base_bg.get("blur_radius", 0))

        # Glow parameters
        glow_enabled = bool(style.get("glowEnabled") or style.get("glow_enabled") or base.get("glow_enabled"))
        normalized["glow_enabled"] = glow_enabled
        normalized["glow_color"] = style.get("glowColor") or style.get("glow_color") or base.get("glow_color") or normalized["highlight_color"]
        normalized["glow_radius"] = int(style.get("glowSize") or style.get("glow_radius") or base.get("glow_radius", 14))

        # Stroke / Border
        base_stroke = base.get("stroke") or {}
        stroke_enabled = bool(style.get("strokeEnabled") or style.get("stroke_enabled") or bool(base_stroke))
        normalized["stroke_enabled"] = stroke_enabled
        normalized["stroke_width"] = int(style.get("strokeWidth") or style.get("stroke_width") or base_stroke.get("width", 2) if stroke_enabled else 0)
        normalized["stroke_color"] = style.get("strokeColor") or style.get("stroke_color") or base_stroke.get("color", "#000000")

        # Shadow
        base_shadow = base.get("shadow") or {}
        shadow_enabled = bool(style.get("shadowEnabled") or style.get("shadow_enabled") or bool(base_shadow))
        normalized["shadow_enabled"] = shadow_enabled
        normalized["shadow_color"] = style.get("shadowColor") or style.get("shadow_color") or base_shadow.get("color", "#000000")
        normalized["shadow_blur"] = int(style.get("shadowBlur") or style.get("shadow_blur") or base_shadow.get("blur", 6))
        normalized["shadow_offset_x"] = int(style.get("shadowOffsetX") or style.get("shadow_offset_x") or base_shadow.get("offset_x", 0))
        normalized["shadow_offset_y"] = int(style.get("shadowOffsetY") or style.get("shadow_offset_y") or base_shadow.get("offset_y", 2))

        return normalized

    def render_subtitles(
        self,
        video_path: str,
        words: list,
        style: Any,
        output_path: str,
        start_offset: float = 0.0,
    ) -> str:
        """Render subtitles with Skia effects onto video.

        Args:
            video_path: Input video path.
            words: List of word dicts [{word, start, end}] from Whisper.
            style: Skia style config dict.
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

        if not SKIA_AVAILABLE:
            logger.info("skia_subtitle: using robust FFmpeg renderer fallback")
            return self._ffmpeg_fallback(video_path, words, norm_style, output_path, start_offset)

        try:
            res = self._render_with_skia(video_path, words, norm_style, output_path, start_offset)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return res
            logger.warning("skia_subtitle: Skia render did not produce valid output, falling back to FFmpeg")
            return self._ffmpeg_fallback(video_path, words, norm_style, output_path, start_offset)
        except Exception as e:
            logger.error(f"skia_subtitle: render failed ({e}), falling back to FFmpeg")
            return self._ffmpeg_fallback(video_path, words, norm_style, output_path, start_offset)

    def _render_with_skia(
        self,
        video_path: str,
        words: list,
        style: dict,
        output_path: str,
        start_offset: float,
    ) -> str:
        """Core Skia rendering: generate PNG overlays per line, composite via FFmpeg."""
        lines = self._group_words_into_lines(words, style.get("max_words_per_line", 4))
        if not lines:
            return video_path

        tmp_dir = tempfile.mkdtemp(prefix="skia_sub_")
        overlay_specs = []  # (png_path, start_time, end_time)

        try:
            for idx, line in enumerate(lines):
                line_start = line[0]["start"] + start_offset
                line_end = line[-1]["end"] + start_offset
                line_text = " ".join(w["word"] for w in line)

                if style.get("uppercase", False):
                    line_text = line_text.upper()

                transition = style.get("line_transition", "karaoke")

                if transition == "word_pop":
                    for w_idx, w in enumerate(line):
                        w_start = w["start"] + start_offset
                        w_end = w["end"] + start_offset
                        word_text = w["word"].upper() if style.get("uppercase") else w["word"]
                        png_path = os.path.join(tmp_dir, f"word_{idx}_{w_idx}.png")
                        self._render_text_frame(png_path, word_text, style, is_highlight=True)
                        overlay_specs.append((png_path, w_start, w_end))
                else:
                    # Full line overlay
                    png_path = os.path.join(tmp_dir, f"line_{idx}.png")
                    self._render_text_frame(png_path, line_text, style, is_highlight=False)
                    overlay_specs.append((png_path, line_start, line_end))

                    # Active word highlight overlay (karaoke)
                    if transition == "karaoke":
                        for w_idx, w in enumerate(line):
                            w_start = w["start"] + start_offset
                            w_end = w["end"] + start_offset
                            word_text = w["word"].upper() if style.get("uppercase") else w["word"]
                            hl_path = os.path.join(tmp_dir, f"hl_{idx}_{w_idx}.png")
                            self._render_text_frame(hl_path, word_text, style, is_highlight=True)
                            overlay_specs.append((hl_path, w_start, w_end))

            if not overlay_specs:
                return video_path

            result = self._composite_overlays(video_path, overlay_specs, style, output_path)
            return result

        finally:
            # Cleanup temp PNGs
            if os.path.exists(tmp_dir):
                for f in os.listdir(tmp_dir):
                    try:
                        os.remove(os.path.join(tmp_dir, f))
                    except OSError:
                        pass
                try:
                    os.rmdir(tmp_dir)
                except OSError:
                    pass

    def _render_text_frame(self, output_png: str, text: str, style: dict, is_highlight: bool = False):
        """Render a single text frame as transparent PNG using Skia."""
        surface = skia.Surface(self._width, self._height)
        canvas = surface.getCanvas()
        canvas.clear(skia.ColorTRANSPARENT)

        font_family = style.get("font_family", "Inter")
        font_weight = style.get("font_weight", "Bold")
        font_size = style.get("font_size", 34)
        font_path = self._resolve_font(font_family, font_weight)

        typeface = None
        if font_path and os.path.exists(font_path):
            typeface = skia.Typeface.MakeFromFile(font_path)
        if not typeface:
            typeface = skia.Typeface.MakeDefault()

        font = skia.Font(typeface, font_size)
        text_blob = skia.TextBlob.MakeFromString(text, font)
        text_bounds = font.measureText(text)

        position_y_pct = style.get("position_y_pct", 78)
        x = (self._width - text_bounds) / 2
        y = self._height * (position_y_pct / 100)

        # Background
        if style.get("bg_enabled") and not is_highlight:
            bg_padding = style.get("bg_padding", 20)
            bg_radius = style.get("bg_radius", 16)
            bg_opacity = style.get("bg_opacity", 0.5)
            bg_color_hex = style.get("bg_color", "#1E293B")

            bg_paint = skia.Paint()
            bg_paint.setAntiAlias(True)
            r, g, b = self._hex_to_rgb(bg_color_hex)
            bg_paint.setColor(skia.Color(r, g, b, int(bg_opacity * 255)))

            rect = skia.Rect.MakeXYWH(
                x - bg_padding,
                y - font_size - bg_padding / 2,
                text_bounds + bg_padding * 2,
                font_size + bg_padding,
            )

            if style.get("blur_radius", 0) > 0:
                blur = skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, style["blur_radius"] / 2)
                bg_paint.setMaskFilter(blur)

            canvas.drawRoundRect(rect, bg_radius, bg_radius, bg_paint)

        # Glow effect
        if style.get("glow_enabled") and style.get("glow_color"):
            glow_paint = skia.Paint()
            glow_paint.setAntiAlias(True)
            r, g, b = self._hex_to_rgb(style["glow_color"])
            glow_paint.setColor(skia.Color(r, g, b, 140))
            glow_radius = style.get("glow_radius", 14)
            blur_filter = skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, glow_radius)
            glow_paint.setMaskFilter(blur_filter)
            canvas.drawTextBlob(text_blob, x, y, glow_paint)

        # Shadow
        if style.get("shadow_enabled") and style.get("shadow_color"):
            shadow_paint = skia.Paint()
            shadow_paint.setAntiAlias(True)
            r, g, b = self._hex_to_rgb(style["shadow_color"])
            shadow_blur = style.get("shadow_blur", 6)
            shadow_paint.setColor(skia.Color(r, g, b, 180))
            if shadow_blur > 0:
                blur_filter = skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, shadow_blur)
                shadow_paint.setMaskFilter(blur_filter)
            ox = style.get("shadow_offset_x", 0)
            oy = style.get("shadow_offset_y", 2)
            canvas.drawTextBlob(text_blob, x + ox, y + oy, shadow_paint)

        # Stroke
        if style.get("stroke_enabled"):
            stroke_paint = skia.Paint()
            stroke_paint.setAntiAlias(True)
            stroke_paint.setStyle(skia.Paint.kStroke_Style)
            stroke_paint.setStrokeWidth(style.get("stroke_width", 2))
            r, g, b = self._hex_to_rgb(style.get("stroke_color", "#000000"))
            stroke_paint.setColor(skia.Color(r, g, b, 255))
            canvas.drawTextBlob(text_blob, x, y, stroke_paint)

        # Text fill
        text_paint = skia.Paint()
        text_paint.setAntiAlias(True)
        color_hex = style.get("highlight_color", "#38BDF8") if is_highlight else style.get("text_color", "#FFFFFF")
        r, g, b = self._hex_to_rgb(color_hex)
        text_paint.setColor(skia.Color(r, g, b, 255))

        canvas.drawTextBlob(text_blob, x, y, text_paint)

        # Save to PNG
        image = surface.makeImageSnapshot()
        image.save(output_png, skia.kPNG)

    def _composite_overlays(
        self,
        video_path: str,
        overlay_specs: list,
        style: dict,
        output_path: str,
    ) -> str:
        """Composite PNG overlays onto video using FFmpeg overlay filter chain."""
        if not overlay_specs:
            return video_path

        max_overlays = 150
        specs = overlay_specs[:max_overlays]

        inputs = ["-i", video_path]
        for png_path, _, _ in specs:
            inputs.extend(["-i", png_path])

        filter_parts = []
        prev_label = "[0:v]"

        for i, (_, start, end) in enumerate(specs):
            in_label = f"[{i + 1}:v]"
            out_label = f"[v{i}]"
            position_y_pct = style.get("position_y_pct", 78)
            filter_parts.append(
                f"{prev_label}{in_label}overlay="
                f"x=(W-w)/2:y=(H*{position_y_pct}/100-h/2)"
                f":enable='between(t,{start:.3f},{end:.3f})'{out_label}"
            )
            prev_label = out_label

        filter_complex = ";".join(filter_parts)
        final_label = f"[v{len(specs) - 1}]"

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", final_label,
            "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

        try:
            clip_dur = overlay_specs[-1][2] - overlay_specs[0][1] if overlay_specs else 60
            timeout = max(180, int(clip_dur * 4 + 60))
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                logger.error(f"skia_composite failed: {result.stderr[-400:]}")
                return video_path
            logger.info(f"skia_subtitle: {len(specs)} overlays composited → {output_path}")
            return output_path
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.error(f"skia_composite exception: {e}")
            return video_path

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

        # Map normalized Skia style to SubtitleStyleConfig
        config = SubtitleStyleConfig(
            font_family=style.get("font_family", "Poppins"),
            font_size=int(style.get("font_size", 34)),
            font_weight=style.get("font_weight", "Bold"),
            color=style.get("text_color", "#FFFFFF"),
            highlight_color=style.get("highlight_color", "#38BDF8"),
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

    def _group_words_into_lines(self, words: list, max_per_line: int) -> list[list[dict]]:
        """Group words into lines respecting word count and natural pauses."""
        max_chars = 25
        lines = []
        current_line = []
        current_chars = 0

        for w in words:
            word_text = w.get("word", "")
            word_len = len(word_text)
            new_chars = current_chars + word_len + (1 if current_line else 0)
            word_count = len(current_line) + 1

            force_new = False
            if current_line:
                prev_end = current_line[-1].get("end", 0)
                curr_start = w.get("start", 0)
                if curr_start - prev_end > 0.5:
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

    def _resolve_font(self, font_family: str, font_weight: str = "Bold") -> Optional[str]:
        """Try to find font file in assets/fonts/."""
        if not os.path.isdir(self._font_dir):
            return None
        candidates = [
            f"{font_family}-{font_weight}.ttf",
            f"{font_family}-Regular.ttf",
            f"{font_family.replace(' ', '')}-{font_weight}.ttf",
            f"{font_family.replace(' ', '')}-Regular.ttf",
            "Poppins-Bold.ttf",
            "Inter-Variable.ttf",
        ]
        for name in candidates:
            path = os.path.join(self._font_dir, name)
            if os.path.exists(path):
                return path
        return None

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join(2 * c for c in hex_color)
        if len(hex_color) >= 6:
            return int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return 255, 255, 255

    @staticmethod
    def _hex_to_skia_color(hex_color: str) -> int:
        """Convert hex color to Skia color int."""
        r, g, b = SkiaSubtitleRenderer._hex_to_rgb(hex_color)
        return skia.Color(r, g, b, 255)
