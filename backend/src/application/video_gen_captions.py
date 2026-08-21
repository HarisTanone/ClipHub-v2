"""ASS subtitle generation for the AI video generator."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.config import settings


VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
_HEX_COLOR = re.compile(r"^#?([0-9a-fA-F]{6})$")
_ASS_COLOR = re.compile(r"^&H([0-9a-fA-F]{6}|[0-9a-fA-F]{8})&?$")
_SAFE_FONT = re.compile(r"[^A-Za-z0-9 _.-]")


ALL_SUBTITLE_PRESETS = {
    # Classic / Standard
    "classic", "classic_karaoke", "clean", "minimal", "bold",
    # High-impact / Viral
    "hormozi_pop", "meme_impact", "bold_impact", "bold_impact_stroke", "impact_badge",
    # Neon & Glow
    "neon_glow", "neon_pulse", "neon_tube",
    # Clean & Editorial
    "devon_clean", "minimal_clean", "clean_editorial",
    # Podcast & Dialogue
    "podcast_dialogue", "podcast_pro",
    # Cinematic & Documentary
    "cinematic_bar", "cinematic_slate", "documentary", "editorial_banner", "quote_box",
    # Fire & Energy
    "fire_emphasis", "fire_flame",
    # Glassmorphism
    "glass_blur", "glassmorphism", "gradient_glass",
    # Tech & Monospace
    "tech_mono", "modern_mono", "terminal_type",
    # Luxury & Gold
    "gold_luxury", "retro_chrome",
    # Positioning & Minimal
    "minimal_lower", "lower_third",
    # Dual & Outline
    "dual_pop", "spotlight_keyword", "outline_stack",
    # Word Tiles & Boxes
    "kinetic_word_box", "word_tiles", "caption_strip", "bubble_chat", "comic_burst", "breaking_tape",
}


def normalize_subtitle_style(raw_style: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a bounded FFmpeg/libass-compatible caption configuration supporting all Custom Style Editor presets."""
    raw = dict(raw_style or {})
    raw_preset = str(raw.get("stylePreset") or "classic").strip()
    preset = raw_preset if raw_preset in ALL_SUBTITLE_PRESETS else "classic"
    
    position = _choice(raw.get("position"), "bottom", {"top", "center", "bottom"})
    raw_transition = str(raw.get("lineTransition") or "word_pop")
    if raw_transition == "karaoke":
        raw_transition = "word_pop"
    line_transition = _choice(
        raw_transition,
        "word_pop",
        {"word_pop", "emphasis", "line_reveal"},
    )
    animation = _choice(raw.get("animationStyle"), "pop", {"pop", "fade", "slide", "none"})

    default_font = settings.VIDEO_GEN_SUB_FONT_NAME or "Montserrat"
    default_size = 48

    if preset in {"hormozi_pop", "meme_impact", "bold_impact", "bold_impact_stroke", "impact_badge", "bold"}:
        default_font = "Montserrat"
        default_size = 54
    elif preset in {"neon_glow", "neon_pulse", "neon_tube"}:
        default_font = "Montserrat"
        default_size = 48
    elif preset in {"tech_mono", "modern_mono", "terminal_type"}:
        default_font = "Space Grotesk"
        default_size = 42
    elif preset in {"gold_luxury", "cinematic_slate"}:
        default_font = "Playfair Display"
        default_size = 46
    elif preset in {"fire_emphasis", "fire_flame"}:
        default_font = "Anton"
        default_size = 52
    elif preset in {"devon_clean", "clean_editorial", "podcast_dialogue", "podcast_pro", "clean"}:
        default_font = "Inter"
        default_size = 44

    # Allow custom font override
    chosen_font = _font_name(raw.get("fontFamily"), default_font)

    style = {
        "stylePreset": preset,
        "fontFamily": chosen_font,
        "fontSize": _number(raw.get("fontSize"), default_size, 24, 140, integer=True),
        "fontWeight": _number(raw.get("fontWeight"), 800, 400, 950, integer=True),
        "letterSpacing": _number(raw.get("letterSpacing"), 0, -5, 12),
        "color": _color(raw.get("color"), settings.VIDEO_GEN_SUB_PRIMARY_COLOR or "#FFFFFF"),
        "highlightColor": _color(raw.get("highlightColor"), settings.VIDEO_GEN_SUB_HIGHLIGHT_COLOR or "#FACC15"),
        "bgEnabled": _boolean(raw.get("bgEnabled"), False),
        "bgColor": _color(raw.get("bgColor"), settings.VIDEO_GEN_SUB_BACK_COLOR or "#000000"),
        "bgOpacity": _number(raw.get("bgOpacity"), settings.VIDEO_GEN_SUB_BG_OPACITY, 0, 1),
        "bgPadding": _number(raw.get("bgPadding"), 14, 0, 40),
        "position": position,
        "positionY": _number(raw.get("positionY"), _default_position_y(position), 5, 95),
        "uppercase": _boolean(raw.get("uppercase"), False),
        "capitalize": _boolean(raw.get("capitalize"), False),
        "italic": _boolean(raw.get("italic"), False),
        "strokeEnabled": _boolean(raw.get("strokeEnabled"), True),
        "strokeColor": _color(raw.get("strokeColor"), settings.VIDEO_GEN_SUB_OUTLINE_COLOR or "#000000"),
        "strokeWidth": _number(raw.get("strokeWidth"), settings.VIDEO_GEN_SUB_OUTLINE or 3.5, 0, 12),
        "shadowEnabled": _boolean(raw.get("shadowEnabled"), True),
        "shadowColor": _color(raw.get("shadowColor"), settings.VIDEO_GEN_SUB_OUTLINE_COLOR or "#000000"),
        "shadowBlur": _number(raw.get("shadowBlur"), 8, 0, 36),
        "maxWordsPerLine": _number(raw.get("maxWordsPerLine"), 3, 1, 8, integer=True),
        "maxWidthPct": _number(raw.get("maxWidthPct"), 90, 45, 96),
        "lineTransition": line_transition,
        "animationStyle": animation,
    }

    # Apply signature preset defaults if not explicitly provided in raw
    if preset in {"hormozi_pop", "bold_impact", "meme_impact", "bold"}:
        if "uppercase" not in raw:
            style["uppercase"] = True
        if "highlightColor" not in raw:
            style["highlightColor"] = "#00FF66"
        if "strokeWidth" not in raw:
            style["strokeWidth"] = 5.0
        if "maxWordsPerLine" not in raw:
            style["maxWordsPerLine"] = 2
    elif preset in {"neon_glow", "neon_pulse"}:
        if "color" not in raw:
            style["color"] = "#00FFAA"
        if "highlightColor" not in raw:
            style["highlightColor"] = "#FF00FF"
        if "bgEnabled" not in raw:
            style["bgEnabled"] = True
            style["bgColor"] = "#000000"
            style["bgOpacity"] = 0.7
        if "strokeWidth" not in raw:
            style["strokeWidth"] = 4.0
        if "uppercase" not in raw:
            style["uppercase"] = True
    elif preset in {"devon_clean", "clean_editorial", "clean"}:
        if "bgEnabled" not in raw:
            style["bgEnabled"] = True
            style["bgColor"] = "#0F172A"
            style["bgOpacity"] = 0.8
        if "highlightColor" not in raw:
            style["highlightColor"] = "#00F0FF"
        if "strokeEnabled" not in raw:
            style["strokeEnabled"] = False
    elif preset in {"podcast_dialogue", "podcast_pro"}:
        if "bgEnabled" not in raw:
            style["bgEnabled"] = True
            style["bgColor"] = "#18181B"
            style["bgOpacity"] = 0.85
        if "highlightColor" not in raw:
            style["highlightColor"] = "#10B981"
        if "strokeEnabled" not in raw:
            style["strokeEnabled"] = False
    elif preset in {"cinematic_bar", "cinematic_slate", "documentary"}:
        if "bgEnabled" not in raw:
            style["bgEnabled"] = True
            style["bgColor"] = "#111827"
            style["bgOpacity"] = 0.85
        if "highlightColor" not in raw:
            style["highlightColor"] = "#FFD700"
        if "uppercase" not in raw:
            style["uppercase"] = True
    elif preset in {"fire_emphasis", "fire_flame"}:
        if "highlightColor" not in raw:
            style["highlightColor"] = "#FF4500"
        if "uppercase" not in raw:
            style["uppercase"] = True
        if "strokeWidth" not in raw:
            style["strokeWidth"] = 4.5
    elif preset in {"tech_mono", "modern_mono", "terminal_type"}:
        if "color" not in raw:
            style["color"] = "#94A3B8"
        if "highlightColor" not in raw:
            style["highlightColor"] = "#06B6D4"
        if "bgEnabled" not in raw:
            style["bgEnabled"] = True
            style["bgColor"] = "#050B14"
            style["bgOpacity"] = 0.85
        if "uppercase" not in raw:
            style["uppercase"] = True
    elif preset in {"gold_luxury", "retro_chrome"}:
        if "color" not in raw:
            style["color"] = "#CBD5E1"
        if "highlightColor" not in raw:
            style["highlightColor"] = "#FCD34D"
        if "strokeWidth" not in raw:
            style["strokeWidth"] = 3.0

    return style


def write_ass_subtitles(
    timeline: Iterable[Mapping[str, Any]],
    ass_path: str | Path,
    raw_style: Mapping[str, Any] | None = None,
) -> int:
    """Write paged karaoke captions to an ASS subtitle file and return cue count."""
    style = normalize_subtitle_style(raw_style)
    lines = _ass_header(style)
    cue_count = 0

    for start, end, words, durations in _caption_cues(timeline, style["maxWordsPerLine"]):
        if end <= start or not words:
            continue
        text = _caption_text(words, durations, style)
        if not text:
            continue
        lines.append(
            "Dialogue: 0,"
            f"{_format_ass_time(start)},{_format_ass_time(end)},Caption,,0,0,0,,{text}"
        )
        cue_count += 1

    Path(ass_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cue_count


def ffmpeg_subtitle_filter(ass_path: str | Path, fonts_dir: str | Path | None = None) -> str:
    """Build a safely escaped FFmpeg subtitles filter for an ASS file with font directory support."""
    import os
    escaped_path = str(ass_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    if not fonts_dir:
        for candidate in ["backend/assets/fonts", "assets/fonts", "/usr/local/share/fonts/autocliper", "/usr/share/fonts/truetype"]:
            if os.path.isdir(candidate):
                fonts_dir = candidate
                break

    if fonts_dir and os.path.isdir(fonts_dir):
        escaped_fonts = str(fonts_dir).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        return f"subtitles=filename='{escaped_path}':fontsdir='{escaped_fonts}':original_size={VIDEO_WIDTH}x{VIDEO_HEIGHT}"
    return f"subtitles=filename='{escaped_path}':original_size={VIDEO_WIDTH}x{VIDEO_HEIGHT}"


def _ass_header(style: Mapping[str, Any]) -> list[str]:
    background_enabled = bool(style["bgEnabled"])
    outline = (
        max(1, int(round(float(style["bgPadding"]) / 3)))
        if background_enabled
        else (float(style["strokeWidth"]) if style["strokeEnabled"] else 0)
    )
    shadow = int(round(float(style["shadowBlur"]) / 5)) if style["shadowEnabled"] else 0
    alignment, margin_v = _ass_alignment(style["position"], float(style["positionY"]))
    horizontal_margin = max(34, int((100 - float(style["maxWidthPct"])) * VIDEO_WIDTH / 200))
    font_weight = -1 if int(style["fontWeight"]) >= 600 else 0
    italic = -1 if style["italic"] else 0

    return [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {VIDEO_WIDTH}",
        f"PlayResY: {VIDEO_HEIGHT}",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 2",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Caption,"
        f"{style['fontFamily']},{style['fontSize']},{_ass_color(style['color'])},{_ass_color(style['color'])},"
        f"{_ass_color(style['strokeColor'])},{_ass_color(style['bgColor'], style['bgOpacity'])},"
        f"{font_weight},{italic},0,0,100,100,{style['letterSpacing']},0,"
        f"{3 if background_enabled else 1},{outline},{shadow},{alignment},"
        f"{horizontal_margin},{horizontal_margin},{margin_v},1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]


def _caption_cues(
    timeline: Iterable[Mapping[str, Any]],
    max_words_per_line: int,
) -> Iterable[tuple[float, float, list[str], list[int]]]:
    for entry in timeline:
        narration = str(entry.get("narration") or "").strip()
        if not narration:
            continue
        start = _as_float(entry.get("start_time"), 0.0)
        duration = _as_float(entry.get("duration"), 0.0)
        if duration <= 0:
            continue
        words = re.findall(r"\S+", narration)
        if not words:
            continue

        word_ticks = _word_ticks(words, duration)
        cursor = start
        page_words: list[str] = []
        page_ticks: list[int] = []

        for index, (word, ticks) in enumerate(zip(words, word_ticks)):
            page_words.append(word)
            page_ticks.append(ticks)
            next_word = words[index + 1] if index + 1 < len(words) else None
            punctuation_break = bool(re.search(r"[.!?;:]$", word)) and len(page_words) >= 2
            full_page = len(page_words) >= max_words_per_line
            final_word = next_word is None
            if not (punctuation_break or full_page or final_word):
                continue

            page_duration = sum(page_ticks) / 100
            yield cursor, cursor + page_duration, page_words, page_ticks
            cursor += page_duration
            page_words = []
            page_ticks = []


def _caption_text(words: list[str], durations: list[int], style: Mapping[str, Any]) -> str:
    visible_words = [_apply_case(word, style) for word in words]
    transition = style["lineTransition"]
    animation = style["animationStyle"]
    prefix = ""
    if animation == "fade":
        prefix = r"{\fad(80,120)}"
    elif animation == "slide":
        prefix = r"{\fad(60,100)\move(540,1980,540,1840,0,180)}"
    elif animation == "pop":
        prefix = r"{\fad(50,100)\fscx108\fscy108\t(0,120,\fscx100\fscy100)}"

    if transition == "word_pop":
        base_color = _ass_color(style["color"])
        highlight_color = _ass_color(style["highlightColor"])
        fragments = []
        for word, duration in zip(visible_words, durations):
            fragments.append(
                f"{{\\1c{highlight_color}\\2c{base_color}\\k{max(1, duration)}}}{_ass_escape(word)}"
            )
        return prefix + " ".join(fragments)

    if transition == "emphasis":
        emphasis_index = _emphasis_index(visible_words)
        fragments = []
        for index, word in enumerate(visible_words):
            escaped = _ass_escape(word)
            if index == emphasis_index:
                fragments.append(f"{{\\1c{_ass_color(style['highlightColor'])}\\b1}}{escaped}{{\\r}}")
            else:
                fragments.append(escaped)
        return prefix + " ".join(fragments)

    return prefix + " ".join(_ass_escape(word) for word in visible_words)


def _word_ticks(words: list[str], duration: float) -> list[int]:
    target_ticks = max(len(words), int(round(duration * 100)))
    weights = [max(1, len(re.sub(r"[^\w]", "", word))) for word in words]
    total_weight = sum(weights)
    ticks = [max(1, round(target_ticks * weight / total_weight)) for weight in weights]
    difference = target_ticks - sum(ticks)
    index = 0
    while difference:
        adjustment = 1 if difference > 0 else -1
        target = index % len(ticks)
        if adjustment > 0 or ticks[target] > 1:
            ticks[target] += adjustment
            difference -= adjustment
        index += 1
    return ticks


def _ass_alignment(position: str, position_y: float) -> tuple[int, int]:
    if position == "top":
        return 8, int(round(VIDEO_HEIGHT * position_y / 100))
    if position == "center":
        return 5, 0
    return 2, int(round(VIDEO_HEIGHT * (100 - position_y) / 100))


def _default_position_y(position: str) -> int:
    return {"top": 15, "center": 50, "bottom": 85}[position]


def _apply_case(word: str, style: Mapping[str, Any]) -> str:
    if style["uppercase"]:
        return word.upper()
    if style["capitalize"]:
        return word.capitalize()
    return word


def _emphasis_index(words: list[str]) -> int:
    return max(range(len(words)), key=lambda index: len(re.sub(r"[^\w]", "", words[index])))


def _format_ass_time(seconds: float) -> str:
    total_centiseconds = max(0, int(round(seconds * 100)))
    hours, remainder = divmod(total_centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds:02d}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _ass_color(value: Any, opacity: float = 1.0) -> str:
    text = str(value or "").strip()
    ass_match = _ASS_COLOR.match(text)
    if ass_match:
        raw = ass_match.group(1).upper()
        return f"&H{raw if len(raw) == 8 else f'00{raw}'}&"
    hex_match = _HEX_COLOR.match(text)
    if hex_match:
        red, green, blue = hex_match.group(1).upper()[0:2], hex_match.group(1).upper()[2:4], hex_match.group(1).upper()[4:6]
        alpha = max(0, min(255, round((1 - opacity) * 255)))
        return f"&H{alpha:02X}{blue}{green}{red}&"
    return "&H00FFFFFF&"


def _color(value: Any, fallback: str) -> str:
    return str(value).strip() if _HEX_COLOR.match(str(value or "").strip()) or _ASS_COLOR.match(str(value or "").strip()) else fallback


def _font_name(value: Any, fallback: str) -> str:
    cleaned = _SAFE_FONT.sub("", str(value or "")).strip()
    return (cleaned or fallback)[:80]


def _choice(value: Any, fallback: str, allowed: set[str]) -> str:
    return str(value) if value in allowed else fallback


def _number(value: Any, fallback: float, minimum: float, maximum: float, integer: bool = False) -> int | float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = fallback
    number = max(minimum, min(maximum, number))
    return int(round(number)) if integer else round(number, 3)


def _boolean(value: Any, fallback: bool) -> bool:
    return value if isinstance(value, bool) else fallback


def _as_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
