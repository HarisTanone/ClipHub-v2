"""UnifiedFFmpegCompositor — 1-Pass Video Compositing & Encoding.

Combines Hook Drawtext + Subtitle Karaoke + Watermark Overlay + Audio Mix
into a single FFmpeg execution pass to avoid redundant multi-pass disk I/O
and generation-loss re-encoding.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Optional

from src.domain.entities import SubtitleStyleConfig
from src.infrastructure.gpu_encoder import get_video_encoder_args, get_encoder_name
from src.infrastructure.watermark_renderer import (
    normalise_watermark_config,
    _decode_image_data_url,
    _overlay_x_expr,
    _overlay_y_expr,
)
from src.infrastructure.cta_renderer import (
    normalise_cta_config,
    build_cta_drawtext_filters,
)

logger = logging.getLogger(__name__)

# Fallback hook preset styles
HOOK_STYLES = {
    "paper_clip_scrap": {
        "fontsize": 64,
        "fontcolor": "#1C1917",
        "borderw": 0,
        "bordercolor": "black",
        "bg_opacity": 0.0,
        "duration": 3.0,
        "y_expr": "h*0.42-text_h/2",
        "font_pref": ["Montserrat-Black", "Montserrat-Bold", "Anton"],
    },
    "trending_radar": {
        "fontsize": 64,
        "fontcolor": "white",
        "borderw": 2,
        "bordercolor": "#D946EF",
        "bg_opacity": 0.92,
        "duration": 3.0,
        "y_expr": "h*0.40-text_h/2",
        "font_pref": ["Montserrat-Black", "Montserrat-Bold"],
    },
    "news_breaking_live": {
        "fontsize": 64,
        "fontcolor": "white",
        "borderw": 0,
        "bordercolor": "black",
        "bg_opacity": 0.95,
        "duration": 3.0,
        "y_expr": "h*0.44-text_h/2",
        "font_pref": ["Montserrat-Black", "Montserrat-Bold"],
    },
    "news_viralin_badge": {
        "fontsize": 64,
        "fontcolor": "#09090B",
        "borderw": 0,
        "bordercolor": "black",
        "bg_opacity": 0.0,
        "duration": 3.0,
        "y_expr": "h*0.44-text_h/2",
        "font_pref": ["Montserrat-Black", "Montserrat-Bold"],
    },
    "news_portal_pantau": {
        "fontsize": 62,
        "fontcolor": "#09090B",
        "borderw": 0,
        "bordercolor": "black",
        "bg_opacity": 0.0,
        "duration": 3.0,
        "y_expr": "h*0.46-text_h/2",
        "font_pref": ["Inter-Black", "Montserrat-Black"],
    },
    "news_offset_box": {
        "fontsize": 64,
        "fontcolor": "white",
        "borderw": 0,
        "bordercolor": "black",
        "bg_opacity": 0.0,
        "duration": 3.0,
        "y_expr": "h*0.44-text_h/2",
        "font_pref": ["Montserrat-Black", "Montserrat-Bold"],
    },
    "brutalist_bracket": {
        "fontsize": 64,
        "fontcolor": "#09090B",
        "borderw": 0,
        "bordercolor": "black",
        "bg_opacity": 0.0,
        "duration": 3.0,
        "y_expr": "h*0.44-text_h/2",
        "font_pref": ["Montserrat-Black", "Montserrat-Bold"],
    },
    "quote_strip_tape": {
        "fontsize": 60,
        "fontcolor": "#09090B",
        "borderw": 0,
        "bordercolor": "black",
        "bg_opacity": 0.0,
        "duration": 3.0,
        "y_expr": "h*0.45-text_h/2",
        "font_pref": ["Montserrat-Black", "Montserrat-Bold"],
    },
    "podcast_lower_third": {
        "fontsize": 60,
        "fontcolor": "#F8FAFC",
        "borderw": 0,
        "bordercolor": "black",
        "bg_opacity": 0.0,
        "duration": 3.0,
        "y_expr": "h*0.78-text_h/2",
        "font_pref": ["BarlowCondensed-Bold", "Montserrat-Bold"],
    },
    "waveform_pulse": {
        "fontsize": 60,
        "fontcolor": "#14F1D9",
        "borderw": 0,
        "bordercolor": "black",
        "bg_opacity": 0.0,
        "duration": 3.0,
        "y_expr": "h*0.40-text_h/2",
        "font_pref": ["Montserrat-Black", "Montserrat-Bold"],
    },
    "breaking_tape": {
        "fontsize": 64,
        "fontcolor": "#111111",
        "borderw": 0,
        "bordercolor": "black",
        "bg_opacity": 0.0,
        "duration": 3.0,
        "y_expr": "h*0.40-text_h/2",
        "font_pref": ["Montserrat-Black", "Montserrat-Bold"],
    },
    "glass_flash": {
        "fontsize": 62,
        "fontcolor": "#FFFFFF",
        "borderw": 2,
        "bordercolor": "#C084FC",
        "bg_opacity": 0.85,
        "duration": 3.0,
        "y_expr": "h*0.40-text_h/2",
        "font_pref": ["Montserrat-Black", "Montserrat-Bold"],
    },
    "search_prompt": {
        "fontsize": 58,
        "fontcolor": "#FFFFFF",
        "borderw": 2,
        "bordercolor": "#22D3EE",
        "bg_opacity": 0.90,
        "duration": 3.0,
        "y_expr": "h*0.42-text_h/2",
        "font_pref": ["Montserrat-Bold", "Inter-Bold"],
    },
    "comment_reply": {
        "fontsize": 58,
        "fontcolor": "#18181B",
        "borderw": 0,
        "bordercolor": "black",
        "bg_opacity": 0.0,
        "duration": 3.0,
        "y_expr": "h*0.40-text_h/2",
        "font_pref": ["Inter-Bold", "Montserrat-Bold"],
    },
    "zoom_punch": {
        "fontsize": 68,
        "fontcolor": "white",
        "borderw": 4,
        "bordercolor": "black",
        "bg_opacity": 0.5,
        "duration": 3.0,
        "y_expr": "h*0.35-text_h/2",
        "font_pref": ["Montserrat-Black", "Montserrat-Bold", "Impact", "Arial-Bold"],
    },
    "glitch_rgb": {
        "fontsize": 72,
        "fontcolor": "white",
        "borderw": 0,
        "bordercolor": "black",
        "bg_opacity": 0.6,
        "duration": 3.5,
        "y_expr": "h*0.35-text_h/2",
        "effect": "glitch_rgb",
        "font_pref": ["SpaceGrotesk-Bold", "Impact", "Montserrat-Black"],
    },
    "shake_neon": {
        "fontsize": 70,
        "fontcolor": "#00FFCC",
        "borderw": 3,
        "bordercolor": "#00FFCC",
        "bg_opacity": 0.5,
        "duration": 3.0,
        "y_expr": "h*0.35-text_h/2",
        "effect": "shake_neon",
        "font_pref": ["Montserrat-Black", "SpaceGrotesk-Bold", "Impact"],
    },
    "cinematic_reveal": {
        "fontsize": 58,
        "fontcolor": "white",
        "borderw": 0,
        "bordercolor": "black",
        "bg_opacity": 0.7,
        "duration": 4.0,
        "y_expr": "h*0.40-text_h/2",
        "effect": "cinematic_reveal",
        "font_pref": ["PlayfairDisplay-Bold", "Cinzel-Bold", "Montserrat-Bold", "Times-Bold"],
    },
    "danger_bold": {
        "fontsize": 74,
        "fontcolor": "#FFCC00",
        "borderw": 5,
        "bordercolor": "black",
        "bg_opacity": 0.65,
        "duration": 3.5,
        "y_expr": "h*0.35-text_h/2",
        "effect": "danger_bold",
        "font_pref": ["Impact", "BlackOpsOne-Regular", "Montserrat-Black"],
    },
}


class UnifiedFFmpegCompositor:
    """Combines hook, subtitles, and watermark into a single FFmpeg filter complex pass."""

    def __init__(self, font_dir: str = "assets/fonts"):
        self._font_dir = font_dir

    def _resolve_font(self, font_family: str = "Montserrat", font_weight: str = "Bold") -> Optional[str]:
        """Find matching font file on filesystem."""
        candidates = [
            f"{font_family}-{font_weight}.ttf",
            f"{font_family}-{font_weight}.otf",
            f"{font_family}.ttf",
            f"{font_family}.otf",
            f"{font_family.lower()}_{font_weight.lower()}.ttf",
        ]
        search_dirs = [
            self._font_dir,
            "assets/fonts",
            "backend/assets/fonts",
            "/usr/share/fonts/truetype",
            "/usr/share/fonts/truetype/montserrat",
            "/usr/share/fonts/opentype",
            "/System/Library/Fonts",
            "/Library/Fonts",
        ]
        for sdir in search_dirs:
            if not os.path.exists(sdir):
                continue
            for c in candidates:
                p = os.path.join(sdir, c)
                if os.path.exists(p):
                    return p
            for root, _, files in os.walk(sdir):
                for f in files:
                    if font_family.lower() in f.lower() and (
                        f.endswith(".ttf") or f.endswith(".otf")
                    ):
                        return os.path.join(root, f)
        return None

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """Replace unsupported Unicode characters for drawtext compatibility."""
        replacements = {
            "\u2018": "'",
            "\u2019": "'",
            "\u201c": '"',
            "\u201d": '"',
            "\u2014": "-",
            "\u2013": "-",
            "\u2026": "...",
            "\u00a0": " ",
            "\u200b": "",
            "\u200c": "",
            "\u200d": "",
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        text = re.sub(
            r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf\ufe00-\ufe0f]",
            "",
            text,
        )
        return text.strip()

    @staticmethod
    def _escape_drawtext(text: str) -> str:
        """Escape text for direct inclusion in FFmpeg drawtext filter string."""
        return (
            str(text)
            .replace("\\", "\\\\")
            .replace("'", "'\\''")
            .replace(":", "\\:")
            .replace("%", "\\%")
        )

    # ─── Hook Filter Builder ───────────────────────────────────────────────────

    def build_hook_filter_chain(
        self,
        hook_text: str,
        style_config: dict | None,
        tmp_dir: str,
    ) -> tuple[list[str], list[str]]:
        """Construct FFmpeg drawtext filter pieces for hook overlay.

        Returns:
            (filter_pieces, temp_files_to_cleanup)
        """
        if not hook_text or not hook_text.strip():
            return [], []

        cfg = style_config or {}
        anim = cfg.get("animation", "zoom_punch")
        style = HOOK_STYLES.get(anim, HOOK_STYLES["zoom_punch"]).copy()

        # Database override if present
        try:
            from src.infrastructure.ffmpeg_styles_store import get_ffmpeg_hook_style
            db_style = get_ffmpeg_hook_style(anim)
            if db_style:
                style.update(db_style)
        except Exception:
            pass

        duration = float(cfg.get("duration") or style.get("duration", 3.0))
        fontsize = int(cfg.get("fontSize") or style.get("fontsize", 68))
        fontcolor = str(cfg.get("color") or style.get("fontcolor", "white"))
        borderw = int(cfg.get("strokeWidth") or style.get("borderw", 4))
        bordercolor = str(cfg.get("strokeColor") or style.get("bordercolor", "black"))
        if cfg.get("strokeEnabled") is False:
            borderw = 0
        bg_opacity = float(cfg.get("bgOpacity") if cfg.get("bgOpacity") is not None else style.get("bg_opacity", 0.5))

        y_expr = style.get("y_expr", "h*0.35-text_h/2")
        if cfg.get("positionY"):
            pos_y = int(cfg["positionY"])
            y_expr = f"h*{pos_y / 100:.2f}-text_h/2"

        # Multi-line split if text is long
        words_list = hook_text.strip().split()
        if len(words_list) > 4:
            mid = len(words_list) // 2
            display_text = " ".join(words_list[:mid]) + "\n" + " ".join(words_list[mid:])
        else:
            display_text = hook_text.strip()
        display_text = self._sanitize_text(display_text)

        text_file = os.path.join(tmp_dir, f"hook_{os.getpid()}_{abs(hash(hook_text)) % 10000}.txt")
        with open(text_file, "w", encoding="utf-8") as f:
            f.write(display_text)

        font_family = cfg.get("fontFamily") or (style.get("font_pref") or ["Montserrat"])[0]
        font_path = self._resolve_font(font_family, "Black") or self._resolve_font(font_family, "Bold")
        font_opt = f":fontfile='{font_path}'" if font_path else ""

        alpha_expr = (
            f"if(lt(t\\,0.5)\\,t/0.5\\,"
            f"if(gt(t\\,{duration - 0.5})\\,({duration}-t)/0.5\\,1))"
        )

        effect = style.get("effect", "")
        filters = []

        if bg_opacity > 0:
            filters.append(
                f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{bg_opacity}:t=fill:enable='between(t,0,{duration})'"
            )

        if effect == "glitch_rgb":
            filters.extend([
                f"drawtext=textfile='{text_file}':fontsize={fontsize}{font_opt}:fontcolor=#FF0000@0.7:borderw=0:x=(w-text_w)/2-4+sin(t*15)*3:y={y_expr}:alpha='{alpha_expr}':enable='between(t,0,{duration})'",
                f"drawtext=textfile='{text_file}':fontsize={fontsize}{font_opt}:fontcolor=#00FFFF@0.7:borderw=0:x=(w-text_w)/2+4-sin(t*15)*3:y={y_expr}:alpha='{alpha_expr}':enable='between(t,0,{duration})'",
                f"drawtext=textfile='{text_file}':fontsize={fontsize}{font_opt}:fontcolor=white:borderw=0:x=(w-text_w)/2:y={y_expr}:alpha='{alpha_expr}':enable='between(t,0,{duration})'",
            ])
        elif effect == "shake_neon":
            filters.extend([
                f"drawtext=textfile='{text_file}':fontsize={fontsize}{font_opt}:fontcolor={fontcolor}@0.3:borderw=12:bordercolor={fontcolor}@0.15:x=(w-text_w)/2:y={y_expr}:alpha='{alpha_expr}':enable='between(t,0,{duration})'",
                f"drawtext=textfile='{text_file}':fontsize={fontsize}{font_opt}:fontcolor={fontcolor}@0.5:borderw=6:bordercolor={fontcolor}@0.3:x=(w-text_w)/2+sin(t*25)*2:y={y_expr}+cos(t*20)*2:alpha='{alpha_expr}':enable='between(t,0,{duration})'",
                f"drawtext=textfile='{text_file}':fontsize={fontsize}{font_opt}:fontcolor={fontcolor}:borderw=0:x=(w-text_w)/2+sin(t*30)*1.5:y={y_expr}+cos(t*35)*1:alpha='{alpha_expr}':enable='between(t,0,{duration})'",
            ])
        elif effect == "cinematic_reveal":
            filters.extend([
                f"drawbox=x=0:y=0:w=iw:h=ih*0.12:color=black:t=fill:enable='between(t,0,{duration})'",
                f"drawbox=x=0:y=ih*0.88:w=iw:h=ih*0.12:color=black:t=fill:enable='between(t,0,{duration})'",
                f"drawtext=textfile='{text_file}':fontsize={fontsize}{font_opt}:fontcolor={fontcolor}:borderw=0:shadowx=2:shadowy=2:shadowcolor=black@0.8:x=(w-text_w)/2:y={y_expr}:alpha='if(lt(t\\,1.0)\\,t/1.0\\,if(gt(t\\,{duration - 0.8})\\,({duration}-t)/0.8\\,1))':enable='between(t,0,{duration})'",
            ])
        elif effect == "danger_bold":
            filters.extend([
                f"drawtext=textfile='{text_file}':fontsize={fontsize}{font_opt}:fontcolor=#FF0000@0.4:borderw=10:bordercolor=#FF0000@0.2:x=(w-text_w)/2:y={y_expr}:alpha='{alpha_expr}':enable='between(t,0,{duration})'",
                f"drawtext=textfile='{text_file}':fontsize={fontsize}{font_opt}:fontcolor={fontcolor}:borderw={borderw}:bordercolor=black:x=(w-text_w)/2:y={y_expr}:alpha='{alpha_expr}':enable='between(t,0,{duration})'",
            ])
        else:
            filters.append(
                f"drawtext=textfile='{text_file}':fontsize={fontsize}{font_opt}:fontcolor={fontcolor}:borderw={borderw}:bordercolor={bordercolor}:x=(w-text_w)/2:y={y_expr}:alpha='{alpha_expr}':enable='between(t,0,{duration})'"
            )

        return filters, [text_file]

    # ─── Subtitle Filter Builder ───────────────────────────────────────────────

    def build_subtitle_filter_chain(
        self,
        words: list[dict],
        style: SubtitleStyleConfig | dict | None,
        start_offset: float = 0.0,
    ) -> list[str]:
        """Construct FFmpeg drawtext filter pieces for word-level karaoke subtitles."""
        if not words:
            return []

        config = SubtitleStyleConfig.from_dict(style)

        if getattr(config, "enabled", True) is False:
            return []

        offset = start_offset if start_offset > 0 else config.start_offset
        timing_adj = config.timing_offset
        font_path = self._resolve_font(config.font_family, config.font_weight)
        font_file_opt = f":fontfile='{font_path}'" if font_path else ""

        stroke_color = config.stroke_color or "black"
        stroke_opt = f":borderw={config.stroke_width}:bordercolor={stroke_color}" if (config.stroke_width and config.stroke_width > 0) else ""
        shadow_color = config.shadow_color or "black@0.5"
        shadow_opt = f":shadowx={config.shadow_x}:shadowy={config.shadow_y}:shadowcolor={shadow_color}" if (config.shadow_x or config.shadow_y) else ""

        pos_y_raw = getattr(config, "position_y", None)
        if isinstance(pos_y_raw, (int, float)):
            y_pos = f"(h*{float(pos_y_raw) / 100.0:.2f}-text_h/2)"
        elif isinstance(pos_y_raw, str) and pos_y_raw.strip():
            if pos_y_raw.isdigit() or (pos_y_raw.replace(".", "", 1).isdigit() and pos_y_raw.count(".") <= 1):
                y_pos = f"(h*{float(pos_y_raw) / 100.0:.2f}-text_h/2)"
            else:
                y_pos = pos_y_raw.strip()
        else:
            y_pos = "(h*0.75-text_h/2)"

        autogrid_enabled = bool(style.get("autogrid_enabled", True)) if isinstance(style, dict) else True
        layout_events = style.get("layout_events") or [] if isinstance(style, dict) else []

        def _get_y_for_time(time_sec: float) -> str:
            if not autogrid_enabled:
                return y_pos
            if layout_events:
                curr = "single"
                for ev in sorted(layout_events, key=lambda x: float(x.get("time", 0.0))):
                    if float(ev.get("time", 0.0)) <= time_sec + 0.001:
                        curr = str(ev.get("layout", "single")).lower()
                    else:
                        break
                if curr in ("double", "grid", "2-grid", "split"):
                    return "(h*0.50-text_h/2)"
            elif isinstance(style, dict) and style.get("reframe_layout") in ("double", "grid", "2-grid", "split"):
                return "(h*0.50-text_h/2)"
            return y_pos

        # Group words into lines
        lines = []
        cur_line = []
        max_words = max(1, min(10, getattr(config, "max_words_per_line", 4)))
        for w in words:
            if not isinstance(w, dict) or not w.get("word"):
                continue
            cur_line.append(w)
            if len(cur_line) >= max_words:
                lines.append(cur_line)
                cur_line = []
        if cur_line:
            lines.append(cur_line)

        filters = []
        for line in lines:
            line_start = float(line[0].get("start", 0)) + offset + timing_adj
            line_end = float(line[-1].get("end", 0)) + offset + timing_adj

            if config.line_transition == "word_pop":
                for w in line:
                    w_start = float(w.get("start", 0)) + offset + timing_adj
                    w_end = float(w.get("end", 0)) + offset + timing_adj
                    word_text = str(w.get("word", "")).strip()
                    if config.uppercase:
                        word_text = word_text.upper()
                    escaped_word = self._escape_drawtext(word_text)
                    box_opt = f":box=1:boxcolor=black@{config.background_opacity}:boxborderw=10" if config.background_opacity > 0 else ""
                    active_stroke_w = (config.stroke_width + 1) if (config.stroke_width and config.stroke_width > 0) else 0
                    active_stroke_opt = f":borderw={active_stroke_w}:bordercolor={stroke_color}" if active_stroke_w > 0 else ""
                    current_y = _get_y_for_time(w_start)
                    filters.append(
                        f"drawtext=text='{escaped_word}'"
                        f":fontsize={int(config.font_size * 1.2)}"
                        f"{font_file_opt}"
                        f":fontcolor={config.highlight_color or config.color}"
                        f"{active_stroke_opt}"
                        f"{shadow_opt}"
                        f"{box_opt}"
                        f":x=(w-text_w)/2:y={current_y}"
                        f":enable='between(t,{w_start:.3f},{w_end:.3f})'"
                    )
            elif config.line_transition == "typing":
                for w_idx, w in enumerate(line):
                    w_start = float(w.get("start", 0)) + offset + timing_adj
                    next_w_start = (float(line[w_idx + 1].get("start", 0)) + offset + timing_adj) if (w_idx + 1 < len(line)) else line_end
                    w_end = max(w_start + 0.08, next_w_start)
                    typed_text = " ".join(str(item.get("word", "")).strip() for item in line[:w_idx + 1])
                    if config.uppercase:
                        typed_text = typed_text.upper()
                    escaped_typed = self._escape_drawtext(typed_text)
                    box_opt = f":box=1:boxcolor=black@{config.background_opacity}:boxborderw=8" if config.background_opacity > 0 else ""
                    current_y = _get_y_for_time(w_start)
                    filters.append(
                        f"drawtext=text='{escaped_typed}'"
                        f":fontsize={config.font_size}"
                        f"{font_file_opt}"
                        f":fontcolor={config.highlight_color or config.color}"
                        f"{stroke_opt}"
                        f"{shadow_opt}"
                        f"{box_opt}"
                        f":x=(w-text_w)/2:y={current_y}"
                        f":enable='between(t,{w_start:.3f},{w_end:.3f})'"
                    )
            else:
                # Karaoke/clean line rendering
                line_text = " ".join(str(w.get("word", "")).strip() for w in line)
                if config.uppercase:
                    line_text = line_text.upper()
                escaped_line = self._escape_drawtext(line_text)
                box_opt = f":box=1:boxcolor=black@{config.background_opacity}:boxborderw=8" if config.background_opacity > 0 else ""
                current_y = _get_y_for_time(line_start)
                filters.append(
                    f"drawtext=text='{escaped_line}'"
                    f":fontsize={config.font_size}"
                    f"{font_file_opt}"
                    f":fontcolor={config.highlight_color or config.color}"
                    f"{stroke_opt}"
                    f"{shadow_opt}"
                    f"{box_opt}"
                    f":x=(w-text_w)/2:y={current_y}"
                    f":enable='between(t,{line_start:.3f},{line_end:.3f})'"
                )

        return filters

    # ─── Watermark Filter Builder ──────────────────────────────────────────────

    def build_watermark_filter_chain(
        self,
        watermark_config: dict | None,
        tmp_dir: str,
    ) -> tuple[Optional[str], list[str], list[str]]:
        """Construct watermark filter and extra input arguments.

        Returns:
            (filter_string_or_None, extra_ffmpeg_inputs, temp_files_to_cleanup)
        """
        cfg = normalise_watermark_config(watermark_config)
        if not cfg.get("enabled"):
            return None, [], []

        margin = cfg["marginPct"] / 100.0
        opacity = cfg["opacity"] / 100.0

        if cfg["type"] == "text" and cfg["text"]:
            font_path = self._resolve_font(cfg["fontFamily"], cfg["fontWeight"])
            font_opt = f":fontfile='{font_path}'" if font_path else ""
            escaped_text = self._escape_drawtext(cfg["text"])
            x_expr = _overlay_x_expr(cfg["position"]).replace("main_w", "w").replace("overlay_w", "text_w").format(m=f"{margin:.4f}")
            y_expr = _overlay_y_expr(cfg["position"]).replace("main_h", "h").replace("overlay_h", "text_h").format(m=f"{margin:.4f}")
            color = cfg["color"]
            text_filter = (
                f"drawtext=text='{escaped_text}'"
                f"{font_opt}"
                f":fontsize={cfg['fontSize']}"
                f":fontcolor={color}@{opacity:.2f}"
                f":borderw=2:bordercolor=black@{opacity * 0.7:.2f}"
                f":shadowx=2:shadowy=2:shadowcolor=black@{opacity * 0.5:.2f}"
                f":x={x_expr}:y={y_expr}"
            )
            return text_filter, [], []

        elif cfg["type"] == "image" and cfg.get("imageDataUrl"):
            data, ext = _decode_image_data_url(cfg["imageDataUrl"])
            if data is not None:
                img_path = os.path.join(tmp_dir, f"wm_{os.getpid()}_{abs(hash(cfg['imageDataUrl'])) % 10000}.{ext}")
                with open(img_path, "wb") as f:
                    f.write(data)
                x_expr = _overlay_x_expr(cfg["position"]).format(m=f"{margin:.4f}")
                y_expr = _overlay_y_expr(cfg["position"]).format(m=f"{margin:.4f}")
                w_expr = f"max(2,trunc(main_w*{cfg['sizePct'] / 100.0:.4f}/2)*2)"
                overlay_complex = (
                    f"[1:v]setsar=1[wm_in];"
                    f"[wm_in][0:v]scale2ref=w='{w_expr}':h=-2[wm][base];"
                    f"[wm]format=rgba,lut=a='floor(val*{opacity:.2f})'[wm2];"
                    f"[base][wm2]overlay=x={x_expr}:y={y_expr}:format=auto,setsar=1"
                )
                return overlay_complex, ["-i", img_path], [img_path]

        return None, [], []

    # ─── CTA Filter Builder ───────────────────────────────────────────────────

    def _get_video_duration(self, video_path: str) -> float:
        """Probe video duration via ffprobe safely."""
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=10).decode().strip()
            return float(out)
        except Exception:
            return 30.0

    def build_cta_filter_chain(
        self,
        cta_config: dict | None,
        clip_duration: float,
    ) -> list[str]:
        """Construct CTA end-card filter chain."""
        if not cta_config:
            return []
        cfg = normalise_cta_config(cta_config)
        if not cfg.get("enabled"):
            return []
        font_path = self._resolve_font(cfg["fontFamily"], cfg["fontWeight"])
        return build_cta_drawtext_filters(cfg, clip_duration, font_path)

    # ─── 1-Pass Render Execution ───────────────────────────────────────────────

    async def render_single_pass(
        self,
        input_video: str,
        output_video: str,
        *,
        hook_text: str = "",
        hook_style_config: dict | None = None,
        words: list[dict] | None = None,
        subtitle_style_config: dict | None = None,
        watermark_config: dict | None = None,
        cta_config: dict | None = None,
        audio_normalize: bool = False,
    ) -> bool:
        """Execute all video and audio filters in a single FFmpeg encode pass."""
        if not os.path.exists(input_video):
            logger.error(f"unified_compositor: input video does not exist: {input_video}")
            return False

        os.makedirs(os.path.dirname(output_video), exist_ok=True)
        tmp_dir = tempfile.mkdtemp(prefix="unified_render_")
        cleanup_files = []

        try:
            hook_filters, hook_files = self.build_hook_filter_chain(
                hook_text=hook_text,
                style_config=hook_style_config,
                tmp_dir=tmp_dir,
            )
            cleanup_files.extend(hook_files)

            # Subtitle timing start offset if hook is present
            hook_dur = float((hook_style_config or {}).get("duration", 3.0) or 3.0) if hook_text else 0.0
            sub_filters = self.build_subtitle_filter_chain(
                words=words or [],
                style=subtitle_style_config,
                start_offset=hook_dur,
            )

            wm_filter, wm_inputs, wm_files = self.build_watermark_filter_chain(
                watermark_config=watermark_config,
                tmp_dir=tmp_dir,
            )
            cleanup_files.extend(wm_files)

            # Video duration for CTA calculation
            clip_dur = self._get_video_duration(input_video)
            cta_filters = self.build_cta_filter_chain(
                cta_config=cta_config,
                clip_duration=clip_dur,
            )

            # Assemble video filter chain (hook + watermark + CTA in FFmpeg)
            v_chain_elements = [*hook_filters]
            if cta_filters:
                v_chain_elements.extend(cta_filters)

            cmd = ["ffmpeg", "-y", "-i", input_video]
            if wm_inputs:
                cmd.extend(wm_inputs)

            if wm_inputs and wm_filter and "scale2ref" in wm_filter:
                # Complex filter graph required for image watermark scale2ref
                if v_chain_elements:
                    pre_chain = ",".join(v_chain_elements)
                    filter_complex = f"[0:v]{pre_chain}[v_pre];[1:v][v_pre]{wm_filter}[v_out]"
                else:
                    filter_complex = f"[1:v][0:v]{wm_filter}[v_out]"
                cmd.extend(["-filter_complex", filter_complex, "-map", "[v_out]"])
            else:
                if wm_filter:
                    v_chain_elements.append(wm_filter)
                if v_chain_elements:
                    cmd.extend(["-vf", ",".join(v_chain_elements)])
                cmd.extend(["-map", "0:v:0"])

            # Map audio
            cmd.extend(["-map", "0:a:0?"])
            if audio_normalize:
                cmd.extend(["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"])
            else:
                cmd.extend(["-c:a", "copy"])

            # Hardware-accelerated GPU encoder or optimized libx264
            encoder_args = get_video_encoder_args("medium")
            cmd.extend([*encoder_args, "-movflags", "+faststart", output_video])

            logger.info(
                f"unified_compositor: starting 1-pass render "
                f"[hook={bool(hook_text)}, sub={len(words or [])}w, wm={bool(wm_filter)}, enc={get_encoder_name()}] "
                f"→ {output_video}"
            )

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                err_msg = stderr.decode(errors="ignore")[-400:]
                logger.error(f"unified_compositor: FFmpeg render failed: {err_msg}")
                return False

            if not os.path.exists(output_video) or os.path.getsize(output_video) == 0:
                logger.error(f"unified_compositor: rendered file missing or empty: {output_video}")
                return False

            # High-fidelity subtitle overlay for exact 1:1 match to preview modal
            if words and (subtitle_style_config or {}).get("enabled", True) is not False:
                try:
                    from src.infrastructure.skia_subtitle_renderer import SkiaSubtitleRenderer
                    sub_renderer = SkiaSubtitleRenderer(font_dir=self._font_dir)
                    tmp_sub_out = os.path.join(tmp_dir, "sub_composite_out.mp4")
                    sub_renderer.render_subtitles(
                        video_path=output_video,
                        words=words,
                        style=subtitle_style_config,
                        output_path=tmp_sub_out,
                        start_offset=hook_dur,
                    )
                    if os.path.exists(tmp_sub_out) and os.path.getsize(tmp_sub_out) > 0:
                        os.replace(tmp_sub_out, output_video)
                except Exception as e:
                    logger.warning(f"unified_compositor: subtitle overlay failed ({e}), keeping base render")

            logger.info(f"unified_compositor: 1-pass render success → {output_video}")
            return True

        except Exception as e:
            logger.error(f"unified_compositor: exception during single-pass render: {e}")
            return False
        finally:
            for f in cleanup_files:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
            shutil.rmtree(tmp_dir, ignore_errors=True)
