"""Utilities for preparing subtitle word timings before rendering."""
from __future__ import annotations

import math
import re

_STOP_WORDS = {"yang", "dan", "di", "ke", "dari", "ini", "itu", "dengan", "untuk", "pada", "adalah", "juga", "akan", "sudah", "tidak", "bukan", "ada", "bisa", "jadi", "saya", "aku", "kamu", "dia", "kita", "mereka", "the", "is", "a", "to", "of", "in", "it", "and", "for", "but", "we", "they"}


def mark_important_keywords(words: list[dict], clip_duration: float) -> list[dict]:
    """Select at most about ten meaningful big keywords per video minute."""
    quota = max(1, math.ceil(max(1.0, clip_duration) / 60.0 * 10))
    selected = {i for i, word in enumerate(words) if bool(word.get("highlight"))}
    frequencies: dict[str, int] = {}
    for word in words:
        token = re.sub(r"[^\w]", "", str(word.get("word", "")).lower())
        frequencies[token] = frequencies.get(token, 0) + 1
    candidates = []
    for i, word in enumerate(words):
        raw = str(word.get("word", "")).strip()
        token = re.sub(r"[^\w]", "", raw.lower())
        if i in selected or len(token) < 4 or token in _STOP_WORDS:
            continue
        score = len(token) + (4 if any(c.isdigit() for c in token) else 0) + (2 if raw.isupper() else 0) - frequencies.get(token, 1)
        candidates.append((score, i))
    selected = set(sorted(selected)[:quota])
    for _, i in sorted(candidates, key=lambda item: (-item[0], item[1]))[:max(0, quota - len(selected))]:
        selected.add(i)
    for i, word in enumerate(words):
        word["highlight"] = i in selected
    return words

def sanitize_subtitle_words(
    raw_words: list[dict],
    clip_duration: float,
) -> list[dict]:
    """Normalize word timings for subtitle rendering.

    Word-level providers occasionally return tiny negative starts, overlapping
    words, duplicate boundary words, or words past the trim end. Remotion expects
    clean, relative, monotonic timestamps.
    """
    if not raw_words or clip_duration <= 0:
        return []

    cleaned = []
    last_end = 0.0
    seen_nearby: set[tuple[str, int]] = set()

    def _as_float(value, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    sorted_words = sorted(
        raw_words,
        key=lambda w: (_as_float(w.get("start")), _as_float(w.get("end"))),
    )

    for word in sorted_words:
        text = str(word.get("word", "") or "").strip()
        if not text:
            continue

        raw_start = _as_float(word.get("start"))
        raw_end = _as_float(word.get("end"))
        start = max(0.0, min(raw_start, clip_duration))
        end = max(0.0, min(raw_end, clip_duration))

        if end <= start:
            end = min(start + 0.18, clip_duration)
        if end <= start or start >= clip_duration:
            continue

        dedupe_key = (text.lower(), int(round(start * 10)))
        if dedupe_key in seen_nearby:
            continue
        seen_nearby.add(dedupe_key)

        if start < last_end:
            start = min(last_end + 0.01, clip_duration)
        if end <= start:
            end = min(start + 0.18, clip_duration)
        if end <= start:
            continue

        cleaned.append({
            "word": text,
            "start": round(start, 3),
            "end": round(end, 3),
            "highlight": bool(word.get("highlight", False)),
        })
        last_end = end

    return mark_important_keywords(cleaned, clip_duration)
