"""SkiaSubtitleRenderer — GPU-accelerated subtitle rendering via Skia (skia-python).

Renders subtitle frames as PNG overlays, then composites onto video via FFmpeg.
Supports: gradients, rounded backgrounds, glow, blur, per-word coloring, shadows.
Falls back to FFmpeg drawtext if skia-python is not installed.
"""
import logging
import os
import subprocess
import tempfile
from typing import Any, Optional

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

    def render_subtitles(
        self,
        video_path: str,
        words: list,
        style: dict,
        output_path: str,
        start_offset: float = 0.0,
    ) -> str:
        """Render subtitles with Skia effects onto video.

        Args:
            video_path: Input video path.
            words: List of word dicts [{word, start, end}] from Whisper.
            style: Skia style config dict (from subtitle_styles.SKIA_STYLES).
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
            return video_path

        if not SKIA_AVAILABLE:
            logger.warning("skia_subtitle: skia-python not available, falling back to FFmpeg")
            return self._ffmpeg_fallback(video_path, words, style, output_path, start_offset)

        try:
            return self._render_with_skia(video_path, words, style, output_path, start_offset)
        except Exception as e:
            logger.error(f"skia_subtitle: render failed ({e}), falling back to FFmpeg")
            return self._ffmpeg_fallback(video_path, words, style, output_path, start_offset)

    def _render_with_skia(
        self,
        video_path: str,
        words: list,
        style: dict,
        output_path: str,
        start_offset: float,
    ) -> str:
        """Core Skia rendering: generate PNG overlays per line, composite via FFmpeg."""
        lines = self._group_words_into_lines(words, style.get("max_words_per_line", 3))
        if not lines:
            return video_path

        tmp_dir = tempfile.mkdtemp(prefix="skia_sub_")
        overlay_specs = []  # (png_path, start_time, end_time)

        for idx, line in enumerate(lines):
            line_start = line[0]["start"] + start_offset
            line_end = line[-1]["end"] + start_offset
            line_text = " ".join(w["word"] for w in line)

            if style.get("uppercase", False):
                line_text = line_text.upper()

            # Determine which word is active (for word_pop, render each word separately)
            transition = style.get("line_transition", "karaoke")

            if transition == "word_pop":
                # Render each word as individual overlay
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

                # Active word highlight overlay (for karaoke mode)
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

        # Build FFmpeg command with overlay chain
        result = self._composite_overlays(video_path, overlay_specs, style, output_path)

        # Cleanup temp PNGs
        for f in os.listdir(tmp_dir):
            try:
                os.remove(os.path.join(tmp_dir, f))
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass

        return result

    def _render_text_frame(self, output_png: str, text: str, style: dict, is_highlight: bool = False):
        """Render a single text frame as transparent PNG using Skia."""
        surface = skia.Surface(self._width, self._height)
        canvas = surface.getCanvas()
        canvas.clear(skia.ColorTRANSPARENT)

        # Load font
        font_family = style.get("font_family", "Poppins")
        font_weight = style.get("font_weight", "Bold")
        font_size = style.get("font_size", 36)
        font_path = self._resolve_font(font_family, font_weight)

        typeface = None
        if font_path and os.path.exists(font_path):
            typeface = skia.Typeface.MakeFromFile(font_path)
        if not typeface:
            typeface = skia.Typeface.MakeDefault()

        font = skia.Font(typeface, font_size)
        text_blob = skia.TextBlob.MakeFromString(text, font)
        text_bounds = font.measureText(text)

        # Calculate position
        position_y_pct = style.get("position_y_pct", 82)
        x = (self._width - text_bounds) / 2
        y = self._height * (position_y_pct / 100)

        # Background
        if style.get("bg_enabled") and not is_highlight:
            bg_padding = style.get("bg_padding", 16)
            bg_radius = style.get("bg_radius", 12)
            bg_opacity = style.get("bg_opacity", 0.7)
            bg_color_hex = style.get("bg_color", "#000000")

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
            glow_paint.setColor(skia.Color(r, g, b, 120))
            glow_radius = style.get("glow_radius", 12)
            blur_filter = skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, glow_radius)
            glow_paint.setMaskFilter(blur_filter)
            canvas.drawTextBlob(text_blob, x, y, glow_paint)

        # Shadow
        if style.get("shadow_enabled") and style.get("shadow_color"):
            shadow_paint = skia.Paint()
            shadow_paint.setAntiAlias(True)
            r, g, b = self._hex_to_rgb(style["shadow_color"])
            shadow_blur = style.get("shadow_blur", 4)
            shadow_paint.setColor(skia.Color(r, g, b, 180))
            if shadow_blur > 0:
                blur_filter = skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, shadow_blur)
                shadow_paint.setMaskFilter(blur_filter)
            ox = style.get("shadow_offset_x", 0)
            oy = style.get("shadow_offset_y", 2)
            canvas.drawTextBlob(text_blob, x + ox, y + oy, shadow_paint)

        # Stroke
        if style.get("stroke_enabled") and style.get("stroke_width", 0) > 0:
            stroke_paint = skia.Paint()
            stroke_paint.setAntiAlias(True)
            stroke_paint.setStyle(skia.Paint.kStroke_Style)
            stroke_paint.setStrokeWidth(style["stroke_width"])
            r, g, b = self._hex_to_rgb(style.get("stroke_color", "#000000"))
            stroke_paint.setColor(skia.Color(r, g, b, 255))
            canvas.drawTextBlob(text_blob, x, y, stroke_paint)

        # Main text fill
        text_paint = skia.Paint()
        text_paint.setAntiAlias(True)

        if is_highlight and style.get("highlight_color"):
            color_hex = style["highlight_color"]
        else:
            color_hex = style.get("text_color", "#FFFFFF")

        # Gradient fill
        gradient_colors = None
        if style.get("gradient_enabled"):
            if is_highlight and style.get("highlight_gradient_colors"):
                gradient_colors = style["highlight_gradient_colors"]
            elif style.get("gradient_colors"):
                gradient_colors = style["gradient_colors"]

        if gradient_colors and len(gradient_colors) >= 2 and color_hex != "transparent":
            colors = [self._hex_to_skia_color(c) for c in gradient_colors]
            angle = style.get("gradient_angle", 90)
            grad_type = style.get("gradient_type", "linear")

            if grad_type == "radial":
                shader = skia.GradientShader.MakeRadial(
                    skia.Point(x + text_bounds / 2, y - font_size / 2),
                    max(text_bounds, font_size),
                    colors,
                    None,
                    skia.TileMode.kClamp,
                )
            else:
                # Linear gradient
                import math
                rad = math.radians(angle)
                dx = text_bounds * math.cos(rad)
                dy = text_bounds * math.sin(rad)
                shader = skia.GradientShader.MakeLinear(
                    [skia.Point(x, y), skia.Point(x + dx, y + dy)],
                    colors,
                    None,
                    skia.TileMode.kClamp,
                )
            text_paint.setShader(shader)
        elif color_hex != "transparent":
            r, g, b = self._hex_to_rgb(color_hex)
            text_paint.setColor(skia.Color(r, g, b, 255))
        else:
            # Transparent text (stroke-only neon style)
            text_paint.setColor(skia.ColorTRANSPARENT)

        canvas.drawTextBlob(text_blob, x, y, text_paint)

        # Save PNG
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

        # Limit overlays to prevent command-line overflow
        max_overlays = 150
        specs = overlay_specs[:max_overlays]

        # Build filter_complex
        inputs = ["-i", video_path]
        for png_path, _, _ in specs:
            inputs.extend(["-i", png_path])

        filter_parts = []
        prev_label = "[0:v]"

        for i, (_, start, end) in enumerate(specs):
            in_label = f"[{i + 1}:v]"
            out_label = f"[v{i}]"
            position_y_pct = style.get("position_y_pct", 82)
            # Overlay centered, at correct Y position
            filter_parts.append(
                f"{prev_label}{in_label}overlay="
                f"x=(W-w)/2:y=(H*{position_y_pct}/100-h/2)"
                f":enable='between(t,{start:.3f},{end:.3f})'{out_label}"
            )
            prev_label = out_label

        filter_complex = ";".join(filter_parts)

        # Final label
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
        """Fallback: use FFmpeg drawtext when Skia is not available."""
        from src.infrastructure.subtitle_renderer import SubtitleRenderer
        from src.domain.entities import SubtitleStyleConfig

        # Map Skia style to SubtitleStyleConfig
        config = SubtitleStyleConfig(
            font_family=style.get("font_family", "Poppins"),
            font_size=style.get("font_size", 34),
            font_weight=style.get("font_weight", "Bold"),
            color=style.get("text_color", "#FFFFFF"),
            highlight_color=style.get("highlight_color", "#FFCC00"),
            stroke_color=style.get("stroke_color", "#000000") if style.get("stroke_enabled") else "",
            stroke_width=style.get("stroke_width", 0) if style.get("stroke_enabled") else 0,
            background_opacity=style.get("bg_opacity", 0.0) if style.get("bg_enabled") else 0.0,
            position="bottom",
            padding_bottom=int(1920 * (1 - style.get("position_y_pct", 82) / 100)),
            uppercase=style.get("uppercase", False),
            max_words_per_line=style.get("max_words_per_line", 3),
            line_transition=style.get("line_transition", "word_pop"),
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
        if len(hex_color) == 6:
            return int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return 255, 255, 255

    @staticmethod
    def _hex_to_skia_color(hex_color: str) -> int:
        """Convert hex color to Skia color int."""
        r, g, b = SkiaSubtitleRenderer._hex_to_rgb(hex_color)
        return skia.Color(r, g, b, 255)
