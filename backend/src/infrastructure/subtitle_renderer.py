"""SubtitleRenderer — Word-by-word subtitle rendering via FFmpeg drawtext.

Renders karaoke-style subtitles with word-level Whisper timestamps.
Active word is highlighted in a different color (highlight_color).
Each word appears individually with its own timing from Whisper.
"""
import logging
import os
import subprocess
from typing import Any, Optional

from src.domain.entities import SubtitleStyleConfig
from src.domain.interfaces import ISubtitleRenderer

logger = logging.getLogger(__name__)


class SubtitleRenderer(ISubtitleRenderer):
    """Word-by-word subtitle renderer using FFmpeg drawtext filters.

    Features:
    - Each word rendered individually with its own timing
    - Active word highlighted in highlight_color
    - Proper word wrapping with character limit per line
    - Background box for readability
    - Support for uppercase and custom positioning
    """

    def __init__(self, font_dir: str = "assets/fonts"):
        self._font_dir = font_dir

    def render_subtitles(
        self,
        video_path: str,
        words: list,
        style: Any,
        output_path: str,
        start_offset: float = 0.0,
    ) -> str:
        """Render word-by-word subtitles with karaoke-style highlighting.

        Each word appears with its line group and the currently-spoken word
        is rendered in highlight_color while others are in normal color.

        Args:
            video_path: Input video file path.
            words: List of word dicts [{word, start, end, highlight?}] from Whisper.
            style: SubtitleStyleConfig or dict.
            output_path: Output video file path.
            start_offset: Seconds to delay subtitle start.

        Returns:
            Path to rendered output video, or original path on failure.
        """
        if not os.path.exists(video_path):
            logger.warning(f"subtitle_render: input missing {video_path}")
            return video_path

        if not words:
            logger.info("subtitle_render: no words, skipping")
            return video_path

        config = self._normalize_style(style)
        offset = start_offset if start_offset > 0 else config.start_offset
        timing_adj = config.timing_offset

        # Group words into lines (respecting both word count AND char width)
        lines = self._group_words_into_lines(words, config.max_words_per_line)
        if not lines:
            return video_path

        filter_parts = []
        font_path = self._resolve_font(config.font_family, config.font_weight)
        y_pos = self._calculate_y_position(config)
        font_file_opt = f":fontfile={font_path}" if font_path else ""

        for line in lines:
            line_start = line[0]["start"] + offset + timing_adj
            line_end = line[-1]["end"] + offset + timing_adj

            # Render entire line text as background (dim color) for the full line duration
            line_text = " ".join(w["word"] for w in line)
            if config.uppercase:
                line_text = line_text.upper()

            escaped_line = self._escape_drawtext(line_text)

            # Background box behind text for readability
            if config.background_opacity > 0:
                filter_parts.append(
                    f"drawbox="
                    f"x=(w-text_w)/2-10:y={y_pos}-5"
                    f":w=text_w+20:h=text_h+10"
                    f":color=black@{config.background_opacity}:t=fill"
                    f":enable='between(t,{line_start:.3f},{line_end:.3f})'"
                )

            # Base line text (normal color - all words shown together)
            filter_parts.append(
                f"drawtext=text='{escaped_line}'"
                f":fontsize={config.font_size}"
                f"{font_file_opt}"
                f":fontcolor={config.color}"
                f":borderw={config.stroke_width}:bordercolor={config.stroke_color}"
                f":shadowx={config.shadow_x}:shadowy={config.shadow_y}:shadowcolor={config.shadow_color}"
                f":x={config.position_x}:y={y_pos}"
                f":enable='between(t,{line_start:.3f},{line_end:.3f})'"
            )

            # Highlight active word: render each word individually in highlight_color
            # during its active time, positioned at the correct x offset
            if config.highlight_color and config.highlight_color != config.color:
                x_offset_chars = 0
                for w_idx, w in enumerate(line):
                    word_text = w["word"]
                    if config.uppercase:
                        word_text = word_text.upper()

                    w_start = w["start"] + offset + timing_adj
                    w_end = w["end"] + offset + timing_adj

                    # Calculate x position: approximate char width
                    # Use tw (text_width) calculation based on preceding text
                    if w_idx == 0:
                        # First word: same x as line
                        prefix_text = ""
                    else:
                        prefix_words = [wd["word"] for wd in line[:w_idx]]
                        if config.uppercase:
                            prefix_words = [pw.upper() for pw in prefix_words]
                        prefix_text = " ".join(prefix_words) + " "

                    escaped_word = self._escape_drawtext(word_text)
                    escaped_prefix = self._escape_drawtext(prefix_text) if prefix_text else ""

                    # x position = line_center_x + width_of_prefix
                    # We use text_w of the full line to center, then offset by prefix width
                    # Simpler: render highlighted word with x calculated from prefix
                    if prefix_text:
                        # Use FFmpeg text_w to calculate position dynamically is complex
                        # Instead, use approximate pixel offset based on char count
                        avg_char_width = config.font_size * 0.55  # approximate
                        x_px = int(len(prefix_text) * avg_char_width)
                        # Relative to line start position
                        x_expr = f"(w-text_w)/2+{x_px}"
                    else:
                        x_expr = config.position_x

                    # Draw highlighted word on top during its active time
                    filter_parts.append(
                        f"drawtext=text='{escaped_word}'"
                        f":fontsize={config.font_size}"
                        f"{font_file_opt}"
                        f":fontcolor={config.highlight_color}"
                        f":borderw={config.stroke_width}:bordercolor={config.stroke_color}"
                        f":shadowx={config.shadow_x}:shadowy={config.shadow_y}:shadowcolor={config.shadow_color}"
                        f":x={x_expr}:y={y_pos}"
                        f":enable='between(t,{w_start:.3f},{w_end:.3f})'"
                    )

        if not filter_parts:
            return video_path

        # FFmpeg has a limit on filter complexity. If too many filters, batch them.
        if len(filter_parts) > 80:
            # Too many drawtext filters — fall back to line-only mode (no per-word highlight)
            logger.warning(f"subtitle_render: {len(filter_parts)} filters, falling back to line-only mode")
            return self._render_line_only(video_path, words, config, output_path, offset, timing_adj)

        filter_chain = ",".join(filter_parts)

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", filter_chain,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if result.returncode != 0:
                logger.error(f"subtitle_render failed: {result.stderr[-500:]}")
                # Fallback to simpler render
                return self._render_line_only(video_path, words, config, output_path, offset, timing_adj)
            logger.info(f"subtitle_render: {len(lines)} lines (highlight mode) → {output_path}")
            return output_path
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.error(f"subtitle_render exception: {e}")
            return video_path

    def _render_line_only(
        self,
        video_path: str,
        words: list,
        config: SubtitleStyleConfig,
        output_path: str,
        offset: float,
        timing_adj: float,
    ) -> str:
        """Fallback: render subtitles line-by-line without per-word highlight."""
        lines = self._group_words_into_lines(words, config.max_words_per_line)
        if not lines:
            return video_path

        filter_parts = []
        font_path = self._resolve_font(config.font_family, config.font_weight)
        font_file_opt = f":fontfile={font_path}" if font_path else ""
        y_pos = self._calculate_y_position(config)

        for line in lines:
            line_start = line[0]["start"] + offset + timing_adj
            line_end = line[-1]["end"] + offset + timing_adj
            line_text = " ".join(w["word"] for w in line)

            if config.uppercase:
                line_text = line_text.upper()

            escaped = self._escape_drawtext(line_text)

            filter_parts.append(
                f"drawtext=text='{escaped}'"
                f":fontsize={config.font_size}"
                f"{font_file_opt}"
                f":fontcolor={config.color}"
                f":borderw={config.stroke_width}:bordercolor={config.stroke_color}"
                f":shadowx={config.shadow_x}:shadowy={config.shadow_y}:shadowcolor={config.shadow_color}"
                f":x={config.position_x}:y={y_pos}"
                f":enable='between(t,{line_start:.3f},{line_end:.3f})'"
            )

        if not filter_parts:
            return video_path

        filter_chain = ",".join(filter_parts)

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", filter_chain,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                logger.error(f"subtitle_render line-only failed: {result.stderr[-300:]}")
                return video_path
            logger.info(f"subtitle_render: {len(lines)} lines (line-only) → {output_path}")
            return output_path
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.error(f"subtitle_render exception: {e}")
            return video_path

    def _normalize_style(self, style: Any) -> SubtitleStyleConfig:
        if isinstance(style, SubtitleStyleConfig):
            return style
        if isinstance(style, dict):
            return SubtitleStyleConfig(**{k: v for k, v in style.items() if hasattr(SubtitleStyleConfig, k)})
        return SubtitleStyleConfig()

    def _group_words_into_lines(self, words: list, max_per_line: int) -> list[list[dict]]:
        """Group words into lines respecting both word count and character width.

        Rules:
        - Max words per line (default 3 for short lines)
        - Max ~25 characters per line to prevent overflow
        - Natural pause breaks (gap > 0.5s forces new line)
        """
        max_chars = 25  # Prevent overflow on 9:16 portrait
        lines = []
        current_line = []
        current_chars = 0

        for i, w in enumerate(words):
            word_text = w.get("word", "")
            word_len = len(word_text)

            # Check if adding this word would overflow
            new_chars = current_chars + word_len + (1 if current_line else 0)
            word_count = len(current_line) + 1

            # Force new line conditions
            force_new = False
            if current_line:
                # Gap between words > 0.5s → natural break
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

    def _calculate_y_position(self, config: SubtitleStyleConfig) -> str:
        if config.position_y:
            return config.position_y
        if config.position == "top":
            return "50"
        elif config.position == "center":
            return "(h-text_h)/2"
        else:  # bottom
            return f"h-text_h-{config.padding_bottom}"

    def _resolve_font(self, font_family: str, font_weight: str = "Regular") -> Optional[str]:
        """Try to find font file in assets/fonts/."""
        if not os.path.isdir(self._font_dir):
            return None
        candidates = [
            f"{font_family}-{font_weight}.ttf",
            f"{font_family}-Regular.ttf",
            f"{font_family.replace(' ', '')}-{font_weight}.ttf",
            f"{font_family.replace(' ', '')}-Regular.ttf",
            f"{font_family}-Variable.ttf",
            # Fallback to any available font
            "Poppins-Bold.ttf",
            "Inter-Bold.ttf",
            "Montserrat-Bold.ttf",
        ]
        for name in candidates:
            path = os.path.join(self._font_dir, name)
            if os.path.exists(path):
                return path
        return None

    @staticmethod
    def _escape_drawtext(text: str) -> str:
        """Escape special characters for FFmpeg drawtext."""
        # Remove characters that can't be rendered by most fonts (emoji, special symbols)
        cleaned = ""
        for ch in text:
            code = ord(ch)
            # Keep ASCII, Latin Extended, common punctuation
            if code < 0x2000 or (0x2010 <= code <= 0x206F) or (0x2200 <= code <= 0x22FF):
                cleaned += ch
            else:
                cleaned += " "  # Replace unsupported chars with space

        return cleaned.replace("'", "'\\''").replace(":", "\\:").replace("%", "\\%")
