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

    def _apply_text_case(self, text: str, config) -> str:
        """Apply text transform based on config: uppercase or capitalize."""
        if config.uppercase:
            return text.upper()
        if getattr(config, "capitalize", False):
            return text.title()
        return text

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

        # Route to emphasis style if configured
        if config.line_transition == "emphasis":
            return self.render_emphasis_style(
                video_path=video_path,
                words=words,
                output_path=output_path,
                start_offset=offset,
                emphasis_color=config.highlight_color or "#FFA500",
                normal_color=config.color or "#FFFFFF",
                emphasis_font_size=int(config.font_size * 2.6),  # ~90px if base is 34
                normal_font_size=int(config.font_size * 0.8),    # ~28px if base is 34
                font_family=config.font_family,
                glow_enabled=True,
            )

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
            line_text = self._apply_text_case(line_text, config)

            escaped_line = self._escape_drawtext(line_text)

            # Background: use drawtext box option (drawbox can't access text_w)
            # Box is added directly to the base text drawtext filter below

            # Base line text (normal color - all words shown together)
            box_opt = f":box=1:boxcolor=black@{config.background_opacity}:boxborderw=8" if config.background_opacity > 0 else ""
            filter_parts.append(
                f"drawtext=text='{escaped_line}'"
                f":fontsize={config.font_size}"
                f"{font_file_opt}"
                f":fontcolor={config.color}"
                f":borderw={config.stroke_width}:bordercolor={config.stroke_color}"
                f":shadowx={config.shadow_x}:shadowy={config.shadow_y}:shadowcolor={config.shadow_color}"
                f"{box_opt}"
                f":x={config.position_x}:y={y_pos}"
                f":enable='between(t,{line_start:.3f},{line_end:.3f})'"
            )

            # Karaoke highlight: re-render full line in highlight color during each word's time
            # This avoids x-position overlap bugs from per-word rendering
            if config.highlight_color and config.highlight_color != config.color:
                for w in line:
                    w_start = w["start"] + offset + timing_adj
                    w_end = w["end"] + offset + timing_adj
                    word_text = self._apply_text_case(w["word"], config)
                    escaped_word = self._escape_drawtext(word_text)

                    # Render ONLY the active word in highlight color ABOVE the base line
                    filter_parts.append(
                        f"drawtext=text='{escaped_word}'"
                        f":fontsize={int(config.font_size * 1.1)}"
                        f"{font_file_opt}"
                        f":fontcolor={config.highlight_color}"
                        f":borderw={config.stroke_width}:bordercolor={config.stroke_color}"
                        f":x=(w-text_w)/2:y={y_pos}-{config.font_size + 10}"
                        f":enable='between(t,{w_start:.3f},{w_end:.3f})'"
                    )

        if not filter_parts:
            return video_path

        # FFmpeg can handle ~400+ drawtext filters. Only fall back for extreme cases.
        if len(filter_parts) > 250:
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
            line_text = self._apply_text_case(line_text, config)

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

    # ─── Emphasis Style Renderer (Big Keyword + Small Context) ────────────────

    # Indonesian stop words — never selected as emphasis keyword
    STOP_WORDS = {
        "yang", "dan", "di", "ke", "dari", "ini", "itu", "dengan", "untuk",
        "pada", "adalah", "juga", "akan", "sudah", "udah", "gak", "nggak",
        "tidak", "bukan", "ada", "bisa", "lagi", "kalau", "aja", "sih",
        "ya", "dong", "deh", "nih", "tuh", "loh", "kan", "pun", "atau",
        "tapi", "jadi", "saya", "aku", "kamu", "dia", "kita", "mereka",
        "apa", "siapa", "mana", "kapan", "gimana", "kenapa", "karena",
        "kayak", "banget", "sama", "terus", "the", "is", "a", "to", "of",
        "in", "it", "and", "for", "but", "so", "he", "she", "we", "they",
    }

    def render_emphasis_style(
        self,
        video_path: str,
        words: list,
        output_path: str,
        start_offset: float = 0.0,
        emphasis_color: str = "#FFA500",
        normal_color: str = "#FFFFFF",
        emphasis_font_size: int = 90,
        normal_font_size: int = 28,
        font_family: str = "Montserrat",
        glow_enabled: bool = True,
    ) -> str:
        """Render emphasis-style subtitles — karaoke with occasional keyword glow.

        Design:
        - ALL text at FIXED BOTTOM position (never jumps)
        - Normal: white text with stroke (same as regular karaoke)
        - Active word: colored (highlight_color)
        - Emphasis keyword (every 3rd line): colored + GLOW effect
        - Position NEVER changes — no split between top/bottom
        """
        if not os.path.exists(video_path):
            return video_path
        if not words:
            return video_path

        # Group into lines
        lines = self._group_words_into_lines(words, max_per_line=3)
        if not lines:
            return video_path

        font_path = self._resolve_font(font_family, "Bold")
        font_opt = f":fontfile={font_path}" if font_path else ""
        y_pos = "h-text_h-120"  # Fixed bottom position, NEVER changes

        filter_parts = []
        emphasis_interval = 3
        lines_since_emphasis = 0

        for line in lines:
            line_start = line[0]["start"] + start_offset
            line_end = line[-1]["end"] + start_offset
            line_text = " ".join(w["word"] for w in line)
            escaped_line = self._escape_drawtext(line_text)

            lines_since_emphasis += 1

            # Detect if this line should have emphasis keyword
            emphasis_idx = self._detect_emphasis_word(line)
            emphasis_word = line[emphasis_idx]["word"] if emphasis_idx >= 0 else ""
            should_emphasize = (
                lines_since_emphasis >= emphasis_interval
                and len(emphasis_word) > 4
                and emphasis_word.lower() not in self.STOP_WORDS
            )

            # Layer 1: Base line text (all words, normal color, stroke)
            filter_parts.append(
                f"drawtext=text='{escaped_line}'"
                f":fontsize={normal_font_size + 4}"
                f"{font_opt}"
                f":fontcolor={normal_color}"
                f":borderw=2:bordercolor=black@0.7"
                f":x=(w-text_w)/2:y={y_pos}"
                f":enable='between(t,{line_start:.3f},{line_end:.3f})'"
            )

            # Layer 2: Active word highlight (karaoke style — color each word when spoken)
            if emphasis_color and emphasis_color != normal_color:
                x_offset_chars = 0
                for w_idx, w in enumerate(line):
                    w_start = w["start"] + start_offset
                    w_end = w["end"] + start_offset
                    word_text = w["word"]
                    escaped_word = self._escape_drawtext(word_text)

                    # Calculate x position from prefix width
                    if w_idx == 0:
                        x_expr = f"(w-text_w)/2"
                    else:
                        prefix = " ".join(wd["word"] for wd in line[:w_idx]) + " "
                        avg_char_width = (normal_font_size + 4) * 0.55
                        x_px = int(len(prefix) * avg_char_width)
                        x_expr = f"(w-text_w)/2+{x_px}"

                    # Determine if THIS word is the emphasis keyword
                    is_emphasis = should_emphasize and w_idx == emphasis_idx

                    if is_emphasis:
                        lines_since_emphasis = 0
                        # Emphasis: glow layer behind
                        if glow_enabled:
                            filter_parts.append(
                                f"drawtext=text='{escaped_word}'"
                                f":fontsize={normal_font_size + 4}"
                                f"{font_opt}"
                                f":fontcolor={emphasis_color}@0.4"
                                f":borderw=8:bordercolor={emphasis_color}@0.2"
                                f":x={x_expr}:y={y_pos}"
                                f":enable='between(t,{w_start:.3f},{w_end:.3f})'"
                            )
                        # Emphasis word: colored + bold
                        filter_parts.append(
                            f"drawtext=text='{escaped_word}'"
                            f":fontsize={normal_font_size + 4}"
                            f"{font_opt}"
                            f":fontcolor={emphasis_color}"
                            f":borderw=0"
                            f":x={x_expr}:y={y_pos}"
                            f":enable='between(t,{w_start:.3f},{w_end:.3f})'"
                        )
                    else:
                        # Normal active word: just colored (karaoke highlight)
                        filter_parts.append(
                            f"drawtext=text='{escaped_word}'"
                            f":fontsize={normal_font_size + 4}"
                            f"{font_opt}"
                            f":fontcolor={emphasis_color}"
                            f":borderw=0"
                            f":x={x_expr}:y={y_pos}"
                            f":enable='between(t,{w_start:.3f},{w_end:.3f})'"
                        )

        if not filter_parts:
            return video_path

        # Safety: if too many filters, remove glow layers only
        if len(filter_parts) > 200:
            filter_parts = [f for f in filter_parts if "@0.4" not in f and "@0.2" not in f]

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
                logger.error(f"emphasis_subtitle failed: {result.stderr[-300:]}")
                return video_path
            logger.info(f"emphasis_subtitle: {len(lines)} lines → {output_path}")
            return output_path
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.error(f"emphasis_subtitle exception: {e}")
            return video_path

    def _detect_emphasis_word(self, line: list[dict]) -> int:
        """Auto-detect which word in a line should be the emphasis (big) word.

        Priority:
        1. Longest word that is NOT a stop word
        2. If all are stop words, pick the longest one
        """
        best_idx = 0
        best_score = -1

        for i, w in enumerate(line):
            word = w.get("word", "").lower().strip()
            is_stop = word in self.STOP_WORDS
            length = len(word)

            # Score: non-stop words get +100, then by length
            score = (0 if is_stop else 100) + length

            if score > best_score:
                best_score = score
                best_idx = i

        return best_idx

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
