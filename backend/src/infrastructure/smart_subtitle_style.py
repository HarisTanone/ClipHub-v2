"""Smart editorial subtitle styling and keyword highlighting."""
from __future__ import annotations

import re
from typing import Any


STOPWORDS = {
    "aku", "akan", "atau", "ada", "adalah", "agar", "aja", "anda", "apa",
    "bagai", "bagaimana", "bagi", "bahwa", "banyak", "baru", "begini",
    "begitu", "belum", "bisa", "buat", "cara", "dalam", "dan", "dari",
    "dengan", "dia", "di", "ini", "itu", "jadi", "juga", "kalau", "kami",
    "karena", "kata", "ke", "kita", "lagi", "lebih", "maka", "mereka",
    "mungkin", "nggak", "nih", "nya", "oleh", "pada", "paling", "para",
    "pernah", "saat", "saja", "sama", "sangat", "saya", "sebagai", "sebuah",
    "semua", "seperti", "sudah", "supaya", "tapi", "telah", "tentang",
    "terus", "tidak", "untuk", "yang",
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do",
    "for", "from", "have", "how", "i", "if", "in", "is", "it", "just",
    "like", "me", "my", "not", "of", "on", "or", "so", "that", "the",
    "this", "to", "we", "what", "when", "with", "you", "your",
}


CONTENT_PALETTES = {
    "gaming": {
        "stylePreset": "neon_pulse",
        "fontFamily": "Inter",
        "highlightFontFamily": "Black Ops One",
        "highlightColor": "#22D3EE",
        "highlightGlowColor": "#22D3EE",
        "bgColor": "#020617",
    },
    "podcast": {
        "stylePreset": "dual_pop",
        "fontFamily": "Barlow Condensed",
        "highlightFontFamily": "Anton",
        "highlightColor": "#F97316",
        "highlightGlowColor": "#F97316",
        "bgColor": "#06111F",
    },
    "talking_head": {
        "stylePreset": "spotlight_keyword",
        "fontFamily": "Inter",
        "highlightFontFamily": "Archivo Black",
        "highlightColor": "#FACC15",
        "highlightGlowColor": "#FACC15",
        "bgColor": "#030712",
    },
    "general": {
        "stylePreset": "dual_pop",
        "fontFamily": "Inter",
        "highlightFontFamily": "Archivo Black",
        "highlightColor": "#FACC15",
        "highlightGlowColor": "#FACC15",
        "bgColor": "#030712",
    },
}


def smart_editorial_enabled(clips_data: dict[str, Any] | None) -> bool:
    clips_data = clips_data or {}
    return bool(clips_data.get("smart_camera")) and bool(
        clips_data.get("smart_subtitle_position")
    )


def build_smart_editorial_subtitle_style(
    base_style: dict[str, Any] | None,
    content_profile: dict[str, Any] | None = None,
    position_y: float | None = None,
    max_width_pct: float | None = None,
) -> dict[str, Any]:
    """Return a Remotion subtitle config for smart camera + smart subtitle."""
    base_style = dict(base_style or {})
    content_profile = content_profile or {}
    content_type = str(content_profile.get("content_type") or "general")
    palette = CONTENT_PALETTES.get(content_type, CONTENT_PALETTES["general"])

    existing_highlight_words = base_style.get("highlightWords")
    if not isinstance(existing_highlight_words, list):
        existing_highlight_words = []

    signal_words = [
        _normalise_token(signal)
        for signal in content_profile.get("signals", [])
        if isinstance(signal, str)
    ]

    smart_style = {
        "smartTemplate": "editorial_pro_v1",
        "stylePreset": palette["stylePreset"],
        "fontFamily": palette["fontFamily"],
        "fontSize": 42,
        "fontWeight": "800",
        "letterSpacing": 0,
        "lineHeight": 1.08,
        "color": "#F8FAFC",
        "highlightColor": palette["highlightColor"],
        "highlightScale": 1.12,
        "highlightBold": True,
        "highlightStyle": "scale",
        "highlightGlow": True,
        "highlightGlowColor": palette["highlightGlowColor"],
        "highlightWords": sorted(
            {
                *_clean_terms(existing_highlight_words),
                *_clean_terms(signal_words),
            }
        ),
        "dualStyleEnabled": True,
        "highlightFontFamily": palette["highlightFontFamily"],
        "highlightFontSize": 54 if content_type != "talking_head" else 58,
        "highlightFontWeight": "900",
        "highlightLetterSpacing": 0,
        "highlightItalic": False,
        "highlightUppercase": True,
        "highlightStrokeEnabled": True,
        "highlightStrokeColor": "#020617",
        "highlightStrokeWidth": 3,
        "highlightShadowEnabled": True,
        "highlightShadowColor": "#000000",
        "highlightShadowBlur": 18,
        "bgEnabled": True,
        "bgColor": palette["bgColor"],
        "bgOpacity": 0.42,
        "bgRadius": 8,
        "bgPadding": 14,
        "position": "bottom",
        "positionY": 85,
        "maxWidthPct": 88,
        "uppercase": False,
        "capitalize": False,
        "italic": False,
        "strokeEnabled": True,
        "strokeColor": "#020617",
        "strokeWidth": 2,
        "shadowEnabled": True,
        "shadowColor": "#000000",
        "shadowBlur": 16,
        "maxWordsPerLine": 3,
        "wordSpacing": 7,
        "animationStyle": "pop",
        "animationSpeed": 1.12,
        "lineTransition": "word_pop",
    }

    if content_type == "podcast":
        smart_style.update({
            "fontSize": 44,
            "highlightFontSize": 56,
            "bgOpacity": 0.36,
        })
    elif content_type == "gaming":
        smart_style.update({
            "fontSize": 40,
            "highlightFontSize": 50,
            "bgOpacity": 0.34,
            "maxWordsPerLine": 4,
        })

    # Smart mode owns the visual treatment. Position/width remain dynamic and
    # are applied after the template so camera analysis can move the caption.
    merged = {**base_style, **smart_style}
    if position_y is not None:
        merged["positionY"] = float(position_y)
    if max_width_pct is not None:
        merged["maxWidthPct"] = float(max_width_pct)
    return merged


def apply_smart_word_highlights(
    words: list[dict[str, Any]],
    *,
    hook_text: str = "",
    reason_text: str = "",
    content_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Mark important Whisper words for Remotion dual-style highlighting."""
    if not words:
        return []

    content_profile = content_profile or {}
    hook_terms = set(_significant_terms(hook_text))
    reason_terms = set(_significant_terms(reason_text))
    signal_terms = set(_clean_terms(content_profile.get("signals", [])))

    scored: list[tuple[float, int, str]] = []
    seen_by_term: dict[str, int] = {}
    for idx, word in enumerate(words):
        term = _normalise_token(str(word.get("word", "")))
        if not _is_keyword_candidate(term):
            continue

        score = min(len(term), 12) / 12
        if term in hook_terms:
            score += 3.0
        if term in signal_terms:
            score += 2.0
        if term in reason_terms:
            score += 1.2
        if any(ch.isdigit() for ch in term):
            score += 0.6

        # Avoid painting the same word every time it appears.
        repeat_count = seen_by_term.get(term, 0)
        score -= repeat_count * 0.75
        seen_by_term[term] = repeat_count + 1
        scored.append((score, idx, term))

    max_highlights = max(2, min(8, round(len(words) * 0.18)))
    selected: set[int] = set()
    selected_terms: set[str] = set()
    for score, idx, term in sorted(scored, reverse=True):
        if score < 1.15:
            continue
        if term in selected_terms:
            continue
        if any(abs(idx - existing) <= 1 for existing in selected):
            continue
        selected.add(idx)
        selected_terms.add(term)
        if len(selected) >= max_highlights:
            break

    highlighted = []
    for idx, word in enumerate(words):
        item = dict(word)
        item["highlight"] = bool(item.get("highlight")) or idx in selected
        highlighted.append(item)
    return highlighted


def _significant_terms(text: str) -> list[str]:
    return [
        term
        for term in (_normalise_token(part) for part in re.split(r"\s+", text or ""))
        if _is_keyword_candidate(term)
    ]


def _clean_terms(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    terms = []
    for value in values:
        if not isinstance(value, str):
            continue
        for part in re.split(r"\s+", value):
            term = _normalise_token(part)
            if _is_keyword_candidate(term):
                terms.append(term)
    return terms


def _normalise_token(value: str) -> str:
    return re.sub(r"[^0-9a-zA-ZÀ-ÿ]+", "", value.lower()).strip()


def _is_keyword_candidate(term: str) -> bool:
    return len(term) >= 4 and term not in STOPWORDS
