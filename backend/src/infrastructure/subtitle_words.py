"""Utilities for preparing subtitle word timings before rendering."""
from __future__ import annotations

from typing import Optional


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

    return cleaned


def grid_subtitle_position_y(method: str) -> Optional[float]:
    """Return Remotion subtitle Y% for grid reframing methods."""
    if "speaker_emphasis" in method or "emphasis" in method:
        return 52.0
    if "double" in method or "grid" in method:
        return 43.0
    return None
