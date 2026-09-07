"""SubtitleRenderer — Word-by-word subtitle rendering via FFmpeg drawtext.

Renders karaoke-style subtitles with word-level Whisper timestamps.
Active word is highlighted in a different color (highlight_color).

Engine routing (fail-closed):
  - engine == "skia"  → SkiaSubtitleRenderer (Pillow PNG overlay pipeline)
  - everything else   → FFmpeg drawtext (this renderer)

line_transition modes (FFmpeg):
  - karaoke     : show full line, highlight active word
  - word_pop    : show only active word each beat
  - line_reveal : show full line at once, no per-word highlight
  - emphasis    : big keyword pop + small context line
  - typing      : typewriter progressive reveal per word
"""
import logging
import os
import subprocess
from typing import Any, Optional

from src.domain.entities import SubtitleStyleConfig
from src.domain.interfaces import ISubtitleRenderer
from src.infrastructure.gpu_encoder import get_video_encoder_args

logger = logging.getLogger(__name__)


class SubtitleRenderer(ISubtitleRenderer):
    """Word-by-word subtitle renderer using FFmpeg drawtext filters."""

    def __init__(self, font_dir: str = "assets/fonts"):
        self._font_dir = font_dir

    def _apply_text_case(self, text: str, config) -> str:
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
        """Render word-by-word subtitles with karaoke-style highlighting."""
        if not os.path.exists(video_path):
            logger.warning(f"subtitle_render: input missing {video_path}")
            return video_path

        if not words:
            logger.info("subtitle_render: no words, skipping")
            return video_path

        config = self._normalize_style(style)
        if getattr(config, "enabled", True) is False:
            logger.info("subtitle_render: subtitles disabled, bypassing render")
            if video_path != output_path and os.path.exists(video_path):
                import shutil
                shutil.copy2(video_path, output_path)
            return output_path

        offset = start_offset if start_offset > 0 else config.start_offset
        timing_adj = config.timing_offset

        # ── Engine routing: Skia only when explicitly selected ──────────────
        _engine = str(
            getattr(config, "engine", "")
            or (style.get("engine", "") if isinstance(style, dict) else "")
        ).lower().strip()

        if _engine == "skia":
            try:
                from src.infrastructure.skia_subtitle_renderer import SkiaSubtitleRenderer
                style_dict = (
                    style.to_dict() if hasattr(style, "to_dict")
                    else dict(style) if isinstance(style, dict)
                    else (config.__dict__ if hasattr(config, "__dict__") else {})
                )
                skia_renderer = SkiaSubtitleRenderer(font_dir=self._font_dir)
                res = skia_renderer.render_subtitles(
                    video_path=video_path,
                    words=words,
                    style=style_dict,
                    output_path=output_path,
                    start_offset=offset,
                )
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return res
            except Exception as e:
                logger.warning(f"subtitle_render: Skia failed ({e}), falling back to drawtext")

        # ── FFmpeg drawtext routing by line_transition ───────────────────────
        if config.line_transition == "emphasis":
            return self.render_emphasis_style(
                video_path=video_path,
                words=words,
                output_path=output_path,
                start_offset=offset,
                emphasis_color=config.highlight_color or "#FFA500",
                normal_color=config.color or "#FFFFFF",
                emphasis_font_size=int(config.font_size * 2.6),
                normal_font_size=int(config.font_size * 0.8),
                font_family=config.font_family,
                glow_enabled=True,
            )

        if config.line_transition == "typing":
            return self._render_typing_style(video_path, words, config, output_path, offset, timing_adj)

        # word_pop: one word at a time (no background line)
        if config.line_transition == "word_pop":
            return self._render_word_pop_style(video_path, words, config, output_path, offset, timing_adj)

        # karaoke / line_reveal: show full line, highlight active word (karaoke) or none (line_reveal)
        return self._render_karaoke_style(video_path, words, config, output_path, offset, timing_adj)

    # ─── Karaoke / Line Reveal ────────────────────────────────────────────────

    def _render_karaoke_style(
        self,
        video_path: str,
        words: list,
        config: SubtitleStyleConfig,
        output_path: str,
        offset: float,
        timing_adj: float,
    ) -> str:
        """Show full line, highlight active word (karaoke) or show static line (line_reveal)."""
        lines = self._group_words_into_lines(words, config.max_words_per_line)
        if not lines:
            return video_path

        font_path = self._resolve_font(config.font_family, config.font_weight)
        font_file_opt = f":fontfile={font_path}" if font_path else ""
        y_pos = self._calculate_y_position(config)
        stroke_color = config.stroke_color or "black"
        stroke_opt = (
            f":borderw={config.stroke_width}:bordercolor={stroke_color}"
            if (config.stroke_width and config.stroke_width > 0) else ""
        )
        shadow_color = config.shadow_color or "black@0.5"
        shadow_opt = (
            f":shadowx={config.shadow_x}:shadowy={config.shadow_y}:shadowcolor={shadow_color}"
            if (config.shadow_x or config.shadow_y) else ""
        )
        box_bg = config.background_opacity or (config.bg_opacity if hasattr(config, "bg_opacity") else 0.0)
        box_opt = f":box=1:boxcolor=black@{box_bg}:boxborderw=8" if box_bg > 0 else ""

        filter_parts = []
        is_line_reveal = config.line_transition == "line_reveal"

        for line in lines:
            line_start = line[0]["start"] + offset + timing_adj
            line_end = line[-1]["end"] + offset + timing_adj
            line_text = " ".join(w["word"] for w in line)
            line_text = self._apply_text_case(line_text, config)
            escaped_line = self._escape_drawtext(line_text)

            if is_line_reveal:
                # Show full line in normal color for its entire duration
                filter_parts.append(
                    f"drawtext=text='{escaped_line}'"
                    f":fontsize={config.font_size}"
                    f"{font_file_opt}"
                    f":fontcolor={config.color or '#FFFFFF'}"
                    f"{stroke_opt}{shadow_opt}{box_opt}"
                    f":x=(w-text_w)/2:y={y_pos}"
                    f":enable='between(t,{line_start:.3f},{line_end:.3f})'"
                )
                continue

            # Karaoke: dim line in normal color + bright active word overlay
            filter_parts.append(
                f"drawtext=text='{escaped_line}'"
                f":fontsize={config.font_size}"
                f"{font_file_opt}"
                f":fontcolor={config.color or '#FFFFFF'}@0.55"
                f"{stroke_opt}{shadow_opt}{box_opt}"
                f":x=(w-text_w)/2:y={y_pos}"
                f":enable='between(t,{line_start:.3f},{line_end:.3f})'"
            )

            for w in line:
                w_start = w["start"] + offset + timing_adj
                w_end = w["end"] + offset + timing_adj
                word_text = self._apply_text_case(w["word"], config)
                escaped_word = self._escape_drawtext(word_text)
                active_stroke_w = (config.stroke_width + 1) if (config.stroke_width and config.stroke_width > 0) else 0
                active_stroke_opt = f":borderw={active_stroke_w}:bordercolor={stroke_color}" if active_stroke_w > 0 else ""

                if getattr(config, "glow_enabled", False) or getattr(config, "highlight_glow", False):
                    glow_c = (
                        getattr(config, "glow_color", None)
                        or getattr(config, "highlight_glow_color", None)
                        or config.highlight_color or "#00FFFF"
                    )
                    filter_parts.append(
                        f"drawtext=text='{escaped_word}'"
                        f":fontsize={int(config.font_size * 1.15)}"
                        f"{font_file_opt}"
                        f":fontcolor={glow_c}@0.6"
                        f":borderw={max(6, (config.stroke_width or 3) + 8)}:bordercolor={glow_c}@0.4"
                        f":shadowx=0:shadowy=0:shadowcolor={glow_c}@0.8"
                        f":x=(w-text_w)/2:y={y_pos}"
                        f":enable='between(t,{w_start:.3f},{w_end:.3f})'"
                    )

                filter_parts.append(
                    f"drawtext=text='{escaped_word}'"
                    f":fontsize={int(config.font_size * 1.15)}"
                    f"{font_file_opt}"
                    f":fontcolor={config.highlight_color or '#FFCC00'}"
                    f"{active_stroke_opt}{shadow_opt}"
                    f":x=(w-text_w)/2:y={y_pos}"
                    f":enable='between(t,{w_start:.3f},{w_end:.3f})'"
                )

        if not filter_parts:
            return video_path

        if len(filter_parts) > 250:
            logger.warning(f"subtitle_render: {len(filter_parts)} filters, falling back to line-only mode")
            return self._render_line_only(video_path, words, config, output_path, offset, timing_adj)

        return self._run_ffmpeg(video_path, output_path, filter_parts, words, "karaoke")

    # ─── Word Pop ─────────────────────────────────────────────────────────────

    def _render_word_pop_style(
        self,
        video_path: str,
        words: list,
        config: SubtitleStyleConfig,
        output_path: str,
        offset: float,
        timing_adj: float,
    ) -> str:
        """Show only one word at a time, centered, with highlight color."""
        font_path = self._resolve_font(config.font_family, config.font_weight)
        font_file_opt = f":fontfile={font_path}" if font_path else ""
        y_pos = self._calculate_y_position(config)
        stroke_color = config.stroke_color or "black"
        stroke_opt = (
            f":borderw={config.stroke_width}:bordercolor={stroke_color}"
            if (config.stroke_width and config.stroke_width > 0) else ""
        )
        shadow_color = config.shadow_color or "black@0.5"
        shadow_opt = (
            f":shadowx={config.shadow_x}:shadowy={config.shadow_y}:shadowcolor={shadow_color}"
            if (config.shadow_x or config.shadow_y) else ""
        )

        filter_parts = []
        for w in words:
            w_start = w["start"] + offset + timing_adj
            w_end = w["end"] + offset + timing_adj
            word_text = self._apply_text_case(w["word"], config)
            escaped = self._escape_drawtext(word_text)
            filter_parts.append(
                f"drawtext=text='{escaped}'"
                f":fontsize={int(config.font_size * 1.1)}"
                f"{font_file_opt}"
                f":fontcolor={config.highlight_color or '#FFCC00'}"
                f"{stroke_opt}{shadow_opt}"
                f":x=(w-text_w)/2:y={y_pos}"
                f":enable='between(t,{w_start:.3f},{w_end:.3f})'"
            )

        if not filter_parts:
            return video_path

        if len(filter_parts) > 250:
            return self._render_line_only(video_path, words, config, output_path, offset, timing_adj)

        return self._run_ffmpeg(video_path, output_path, filter_parts, words, "word_pop")

    # ─── Typing / Typewriter ──────────────────────────────────────────────────

    def _render_typing_style(
        self,
        video_path: str,
        words: list,
        config: SubtitleStyleConfig,
        output_path: str,
        offset: float,
        timing_adj: float,
    ) -> str:
        """Typewriter: words reveal progressively, active word in highlight color."""
        lines = self._group_words_into_lines(words, config.max_words_per_line)
        if not lines:
            return video_path

        font_path = self._resolve_font(config.font_family, config.font_weight)
        font_file_opt = f":fontfile={font_path}" if font_path else ""
        y_pos = self._calculate_y_position(config)
        stroke_color = config.stroke_color or "black"
        stroke_opt = (
            f":borderw={config.stroke_width}:bordercolor={stroke_color}"
            if (config.stroke_width and config.stroke_width > 0) else ""
        )
        shadow_color = config.shadow_color or "black@0.5"
        shadow_opt = (
            f":shadowx={config.shadow_x}:shadowy={config.shadow_y}:shadowcolor={shadow_color}"
            if (config.shadow_x or config.shadow_y) else ""
        )

        filter_parts = []
        for line in lines:
            line_end = line[-1]["end"] + offset + timing_adj
            for i, w in enumerate(line):
                w_start = w["start"] + offset + timing_adj
                next_start = (
                    line[i + 1]["start"] + offset + timing_adj
                    if i + 1 < len(line) else line_end
                )
                # Revealed text up to this word (normal color)
                revealed = " ".join(
                    self._apply_text_case(lw["word"], config) for lw in line[:i]
                )
                active_word = self._apply_text_case(w["word"], config)

                # Show already-revealed words in dim color
                if revealed:
                    escaped_rev = self._escape_drawtext(revealed)
                    filter_parts.append(
                        f"drawtext=text='{escaped_rev}'"
                        f":fontsize={config.font_size}"
                        f"{font_file_opt}"
                        f":fontcolor={config.color or '#FFFFFF'}@0.6"
                        f"{stroke_opt}{shadow_opt}"
                        f":x=(w-text_w)/2:y={y_pos}"
                        f":enable='between(t,{w_start:.3f},{next_start:.3f})'"
                    )

                # Active word in highlight color
                escaped_active = self._escape_drawtext(active_word)
                filter_parts.append(
                    f"drawtext=text='{escaped_active}'"
                    f":fontsize={int(config.font_size * 1.05)}"
                    f"{font_file_opt}"
                    f":fontcolor={config.highlight_color or '#FFCC00'}"
                    f"{stroke_opt}{shadow_opt}"
                    f":x=(w-text_w)/2:y={y_pos}"
                    f":enable='between(t,{w_start:.3f},{next_start:.3f})'"
                )

        if not filter_parts:
            return video_path

        if len(filter_parts) > 300:
            return self._render_line_only(video_path, words, config, output_path, offset, timing_adj)

        return self._run_ffmpeg(video_path, output_path, filter_parts, words, "typing")

    # ─── Line Only (fallback) ─────────────────────────────────────────────────

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

        font_path = self._resolve_font(config.font_family, config.font_weight)
        font_file_opt = f":fontfile={font_path}" if font_path else ""
        y_pos = self._calculate_y_position(config)
        stroke_color = config.stroke_color or "black"
        stroke_opt = (
            f":borderw={config.stroke_width}:bordercolor={stroke_color}"
            if (config.stroke_width and config.stroke_width > 0) else ""
        )
        shadow_color = config.shadow_color or "black@0.5"
        shadow_opt = (
            f":shadowx={config.shadow_x}:shadowy={config.shadow_y}:shadowcolor={shadow_color}"
            if (config.shadow_x or config.shadow_y) else ""
        )

        filter_parts = []
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
                f":fontcolor={config.color or '#FFFFFF'}"
                f"{stroke_opt}{shadow_opt}"
                f":x={config.position_x}:y={y_pos}"
                f":enable='between(t,{line_start:.3f},{line_end:.3f})'"
            )

        if not filter_parts:
            return video_path

        return self._run_ffmpeg(video_path, output_path, filter_parts, words, "line_only")

    # ─── Shared FFmpeg runner ─────────────────────────────────────────────────

    def _run_ffmpeg(
        self,
        video_path: str,
        output_path: str,
        filter_parts: list,
        words: list,
        mode: str,
    ) -> str:
        filter_chain = ",".join(filter_parts)
        clip_dur = words[-1]["end"] - words[0]["start"] if words else 60
        timeout = max(120, int(clip_dur * 3 + 60))
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", filter_chain,
            *get_video_encoder_args("medium"),
            "-c:a", "copy", "-movflags", "+faststart", output_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                logger.error(f"subtitle_render[{mode}] failed: {result.stderr[-500:]}")
                if mode not in ("line_only",):
                    return self._render_line_only(
                        video_path, [], SubtitleStyleConfig(), output_path, 0, 0
                    )
                return video_path
            logger.info(f"subtitle_render[{mode}]: {len(filter_parts)} filters → {output_path}")
            return output_path
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.error(f"subtitle_render[{mode}] exception (timeout={timeout}s): {e}")
            return video_path

    # ─── Emphasis Style Renderer ──────────────────────────────────────────────

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
        """Emphasis: big keyword + small context, Skia-first then drawtext fallback."""
        if not os.path.exists(video_path):
            return video_path
        if not words:
            return video_path

        # Skia delegate for emphasis (better visual quality)
        try:
            from src.infrastructure.skia_subtitle_renderer import SkiaSubtitleRenderer
            style_dict = {
                "font_family": font_family,
                "font_size": normal_font_size + 4,
                "highlight_color": emphasis_color,
                "text_color": normal_color,
                "line_transition": "emphasis",
                "glow_enabled": glow_enabled,
            }
            skia_renderer = SkiaSubtitleRenderer(font_dir=self._font_dir)
            res = skia_renderer.render_subtitles(
                video_path=video_path,
                words=words,
                style=style_dict,
                output_path=output_path,
                start_offset=start_offset,
            )
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return res
        except Exception as e:
            logger.warning(f"render_emphasis_style: Skia delegate failed ({e}), falling back to drawtext")

        lines = self._group_words_into_lines(words, max_per_line=3)
        if not lines:
            return video_path

        font_path = self._resolve_font(font_family, "Bold")
        font_opt = f":fontfile={font_path}" if font_path else ""
        y_pos = "h-text_h-120"
        filter_parts = []

        for line in lines:
            line_start = line[0]["start"] + start_offset
            line_end = line[-1]["end"] + start_offset
            line_text = " ".join(w["word"] for w in line)
            escaped_line = self._escape_drawtext(line_text)
            filter_parts.append(
                f"drawtext=text='{escaped_line}'"
                f":fontsize={normal_font_size + 4}"
                f"{font_opt}"
                f":fontcolor={normal_color}"
                f":borderw=2:bordercolor=black@0.7"
                f":x=(w-text_w)/2:y={y_pos}"
                f":enable='between(t,{line_start:.3f},{line_end:.3f})'"
            )

        if not filter_parts:
            return video_path

        return self._run_ffmpeg(video_path, output_path, filter_parts, words, "emphasis")

    def _detect_emphasis_word(self, line: list[dict]) -> int:
        best_idx = 0
        best_score = -1
        for i, w in enumerate(line):
            word = w.get("word", "").lower().strip()
            is_stop = word in self.STOP_WORDS
            score = (0 if is_stop else 100) + len(word)
            if score > best_score:
                best_score = score
                best_idx = i
        return best_idx

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _normalize_style(self, style: Any) -> SubtitleStyleConfig:
        return SubtitleStyleConfig.from_dict(style)

    def _group_words_into_lines(self, words: list, max_per_line: int) -> list[list[dict]]:
        max_chars = 25
        lines = []
        current_line: list[dict] = []
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

    def _calculate_y_position(self, config: SubtitleStyleConfig) -> str:
        pos_str = str(config.position or "").strip().lower()
        if pos_str == "top":
            return "0.12*h"
        elif pos_str == "center":
            return "(h-text_h)/2"
        elif pos_str == "bottom":
            pad = config.padding_bottom or int(0.12 * 1920)
            return f"h-text_h-{pad}"

        if config.position_y:
            try:
                val_num = float(str(config.position_y).replace("%", "").strip())
                if 0 <= val_num <= 100:
                    return f"{val_num / 100.0}*h - text_h/2"
            except (ValueError, TypeError):
                pass
            return str(config.position_y)

        pad = config.padding_bottom or 120
        return f"h-text_h-{pad}"

    def _resolve_font(self, font_family: str, font_weight: str = "Regular") -> Optional[str]:
        search_dirs = [
            self._font_dir,
            "assets/fonts",
            "backend/assets/fonts",
            "/usr/share/fonts/truetype",
            "/System/Library/Fonts",
            "/Library/Fonts",
        ]
        candidates = [
            f"{font_family}-{font_weight}.ttf",
            f"{font_family}-Regular.ttf",
            f"{font_family.replace(' ', '')}-{font_weight}.ttf",
            f"{font_family.replace(' ', '')}-Regular.ttf",
            f"{font_family}-Variable.ttf",
            "Poppins-Bold.ttf",
            "Inter-Bold.ttf",
            "Montserrat-Bold.ttf",
            "Montserrat-Variable.ttf",
            "NotoSans-Variable.ttf",
        ]
        for sdir in search_dirs:
            if not sdir or not os.path.isdir(sdir):
                continue
            for name in candidates:
                path = os.path.join(sdir, name)
                if os.path.exists(path):
                    return os.path.abspath(path)
            try:
                for f in os.listdir(sdir):
                    if font_family.lower() in f.lower() and (f.endswith(".ttf") or f.endswith(".otf")):
                        return os.path.abspath(os.path.join(sdir, f))
            except OSError:
                pass
        return None

    @staticmethod
    def _escape_drawtext(text: str) -> str:
        cleaned = ""
        for ch in text:
            code = ord(ch)
            if code < 0x2000 or (0x2010 <= code <= 0x206F) or (0x2200 <= code <= 0x22FF):
                cleaned += ch
            else:
                cleaned += " "
        return cleaned.replace("'", "'\\''")\
                      .replace(":", "\\:")\
                      .replace("%", "\\%")
