"""Safe contract for sparse AI-selected cinematic text.

The LLM is only allowed to choose word IDs. All final text and timestamps are
rebuilt from Whisper words here, keeping audio, subtitles, and lip-sync on the
same timeline.
"""
from __future__ import annotations

import math
import re
from typing import Iterable


ALLOWED_EFFECTS = {
    "behind_person",
    "spotlight",
    "side_label",
    "floating_text",
    "auto_avoid",
    "around_head",
    "depth_text",
    "kinetic_type",
}
ALLOWED_POSITIONS = {"left", "center", "right"}

DEFAULT_TEXT_EMPHASIS_STYLE = {
    "effectMode": "auto",
    "animation": "cinematic",
    "fontFamily": "Anton",
    "fontSize": 92,
    "fontWeight": "900",
    "letterSpacing": 1,
    "lineHeight": 0.95,
    "color": "#FFFFFF",
    "accentColor": "#FFD400",
    "uppercase": True,
    "strokeEnabled": True,
    "strokeColor": "#09090B",
    "strokeWidth": 2,
    "shadowEnabled": True,
    "shadowColor": "#000000",
    "shadowBlur": 22,
    "positionY": 50,
    "maxWidthPct": 82,
    "maskFeather": 9,
    # Effect-specific tuning
    "floatSpeed": 1.2,
    "avoidPadding": 40,
    "aroundHeadRadius": 60,
    "depthIntensity": 0.5,
    "kineticStagger": 6,
}


def normalise_text_emphasis_style(style: object) -> dict:
    """Return a render-safe style without trusting arbitrary client values."""
    incoming = style if isinstance(style, dict) else {}
    result = {**DEFAULT_TEXT_EMPHASIS_STYLE, **incoming}

    effect_mode = str(result.get("effectMode", "auto"))
    result["effectMode"] = effect_mode if effect_mode in ALLOWED_EFFECTS | {"auto"} else "auto"
    animation = str(result.get("animation", "cinematic"))
    result["animation"] = animation if animation in {"cinematic", "slam", "reveal", "glitch", "neon"} else "cinematic"
    result["fontFamily"] = str(result.get("fontFamily") or "Anton")[:80]
    result["fontWeight"] = str(result.get("fontWeight") or "900")[:8]
    result["fontSize"] = _clamp_number(result.get("fontSize"), 32, 160, 92)
    result["letterSpacing"] = _clamp_number(result.get("letterSpacing"), -4, 20, 1)
    result["lineHeight"] = _clamp_number(result.get("lineHeight"), 0.7, 1.5, 0.95)
    result["strokeWidth"] = _clamp_number(result.get("strokeWidth"), 0, 12, 2)
    result["shadowBlur"] = _clamp_number(result.get("shadowBlur"), 0, 80, 22)
    result["positionY"] = _clamp_number(result.get("positionY"), 12, 88, 50)
    result["maxWidthPct"] = _clamp_number(result.get("maxWidthPct"), 35, 96, 82)
    result["maskFeather"] = int(_clamp_number(result.get("maskFeather"), 1, 31, 9))
    if result["maskFeather"] % 2 == 0:
        result["maskFeather"] += 1
    # Effect-specific tuning (new)
    result["floatSpeed"] = _clamp_number(result.get("floatSpeed"), 0.5, 3.0, 1.2)
    result["avoidPadding"] = _clamp_number(result.get("avoidPadding"), 10, 120, 40)
    result["aroundHeadRadius"] = _clamp_number(result.get("aroundHeadRadius"), 30, 120, 60)
    result["depthIntensity"] = _clamp_number(result.get("depthIntensity"), 0.1, 1.0, 0.5)
    result["kineticStagger"] = _clamp_number(result.get("kineticStagger"), 1, 18, 6)

    for key, fallback in (
        ("color", "#FFFFFF"),
        ("accentColor", "#FFD400"),
        ("strokeColor", "#09090B"),
        ("shadowColor", "#000000"),
    ):
        value = str(result.get(key) or fallback)
        result[key] = value if re.fullmatch(r"#[0-9A-Fa-f]{6}", value) else fallback
    for key in ("uppercase", "strokeEnabled", "shadowEnabled"):
        result[key] = bool(result.get(key))
    return result


def build_text_emphasis_context(
    clips_words: dict[int, list[dict]],
    max_total_words: int = 900,
) -> tuple[str, dict[int, dict[int, dict]]]:
    """Build a bounded word-ID transcript and its lookup table.

    Long direct-edit videos are sampled in contiguous windows across the full
    duration. IDs remain the original Whisper word indexes, so anchoring stays
    exact even when the prompt is sampled.
    """
    non_empty = {rank: words for rank, words in clips_words.items() if words}
    if not non_empty:
        return "", {}

    per_clip = max(80, min(360, max_total_words // len(non_empty)))
    lookup: dict[int, dict[int, dict]] = {}
    sections: list[str] = []
    for rank, words in sorted(non_empty.items()):
        clean_words = [word for word in words if str(word.get("word") or "").strip()]
        if not clean_words:
            continue
        indices = _sample_contiguous_indices(len(clean_words), per_clip)
        lookup[rank] = {index: clean_words[index] for index in indices}
        sections.append(f"CLIP {rank}")
        line: list[str] = []
        previous = None
        for index in indices:
            # A visual separator tells the model it must not span sampled gaps.
            if previous is not None and index != previous + 1:
                if line:
                    sections.append(" ".join(line))
                    line = []
                sections.append("[... gap ...]")
            word = clean_words[index]
            token = str(word.get("word") or "").strip().replace("\n", " ")
            start = _safe_float(word.get("start"), 0)
            line.append(f"[W{index:04d}|{start:.2f}]{token}")
            if len(line) >= 12:
                sections.append(" ".join(line))
                line = []
            previous = index
        if line:
            sections.append(" ".join(line))
    return "\n".join(sections), lookup


def build_text_emphasis_context_full(
    clips_words: dict[int, list[dict]],
) -> tuple[str, dict[int, dict[int, dict]]]:
    """Build a full word-ID transcript and lookup table without sampling.

    Unlike `build_text_emphasis_context`, this includes ALL words per clip
    without any contiguous-window sampling. IDs remain the original Whisper
    word indexes for exact anchoring.
    """
    non_empty = {rank: words for rank, words in clips_words.items() if words}
    if not non_empty:
        return "", {}

    lookup: dict[int, dict[int, dict]] = {}
    sections: list[str] = []
    for rank, words in sorted(non_empty.items()):
        clean_words = [word for word in words if str(word.get("word") or "").strip()]
        if not clean_words:
            continue
        lookup[rank] = {index: clean_words[index] for index in range(len(clean_words))}
        sections.append(f"CLIP {rank}")
        line: list[str] = []
        for index, word in enumerate(clean_words):
            token = str(word.get("word") or "").strip().replace("\n", " ")
            start = _safe_float(word.get("start"), 0)
            line.append(f"[W{index:04d}|{start:.2f}]{token}")
            if len(line) >= 12:
                sections.append(" ".join(line))
                line = []
        if line:
            sections.append(" ".join(line))
    return "\n".join(sections), lookup


def anchor_text_emphasis_response(
    raw_response: object,
    clips_words: dict[int, list[dict]],
    clip_durations: dict[int, float],
    style: object = None,
    min_start_by_clip: dict[int, float] | None = None,
    blocked_ranges_by_clip: dict[int, list[tuple[float, float]]] | None = None,
    max_events: int = 2,
) -> dict[int, list[dict]]:
    """Validate AI choices and rebuild every event from real Whisper words."""
    if max_events <= 0:
        return {}
    safe_style = normalise_text_emphasis_style(style)
    mode = safe_style["effectMode"]
    min_starts = min_start_by_clip or {}
    blocked = blocked_ranges_by_clip or {}

    if isinstance(raw_response, dict) and isinstance(raw_response.get("clips"), dict):
        response_map = raw_response["clips"]
    elif isinstance(raw_response, dict):
        response_map = raw_response
    else:
        return {}

    output: dict[int, list[dict]] = {}
    for rank, words in clips_words.items():
        candidates = response_map.get(str(rank), response_map.get(rank, []))
        if not isinstance(candidates, list) or not words:
            continue
        duration = max(0.0, _safe_float(clip_durations.get(rank), 0))
        min_start = max(0.0, _safe_float(min_starts.get(rank), 1.0))
        accepted: list[dict] = []

        for raw in candidates:
            if not isinstance(raw, dict):
                continue
            start_index = _parse_word_id(raw.get("start_word", raw.get("start_word_id")))
            end_index = _parse_word_id(raw.get("end_word", raw.get("end_word_id")))
            if start_index is None:
                continue
            if end_index is None:
                end_index = start_index
            if start_index < 0 or end_index < start_index or end_index >= len(words):
                continue
            if end_index - start_index > 6:
                end_index = start_index + 6

            phrase_words = words[start_index:end_index + 1]
            if any(not str(word.get("word") or "").strip() for word in phrase_words):
                continue
            start = max(0.0, _safe_float(phrase_words[0].get("start"), 0))
            spoken_end = max(start, _safe_float(phrase_words[-1].get("end"), start))
            if start < min_start or start >= duration - 1.0:
                continue

            # A short hold makes the phrase readable without shifting its anchor.
            end = min(duration, max(spoken_end + 0.55, start + 1.65))
            end = min(end, start + 2.8)
            if end - start < 1.0:
                continue
            if any(_ranges_overlap(start, end, a, b) for a, b in blocked.get(rank, [])):
                continue
            if any(abs(start - event["start"]) < 6.0 for event in accepted):
                continue

            requested_effect = str(raw.get("effect") or "spotlight")
            effect = mode if mode != "auto" else requested_effect
            if effect not in ALLOWED_EFFECTS:
                effect = "spotlight"
            position = str(raw.get("position") or ("left" if effect == "side_label" else "center"))
            if position not in ALLOWED_POSITIONS:
                position = "center"

            text = " ".join(str(word.get("word") or "").strip() for word in phrase_words)
            text = re.sub(r"\s+([,.;:!?])", r"\1", text).strip()
            if not text:
                continue
            accepted.append({
                "id": f"emphasis_{rank}_{len(accepted) + 1}",
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text,
                "effect": effect,
                "position": position,
                "start_word": start_index,
                "end_word": end_index,
                "reason": str(raw.get("reason") or "")[:160],
            })
            if len(accepted) >= min(2, max_events):
                break

        # Fallback: guarantee minimum 1 event per clip when AI returned nothing.
        if not accepted and max_events >= 1:
            fallback = _find_fallback_phrase(
                words, min_start, duration, blocked.get(rank, [])
            )
            if fallback is not None:
                accepted.append(fallback)

        if accepted:
            output[rank] = sorted(accepted, key=lambda event: event["start"])
    return output


def _find_fallback_phrase(
    words: list[dict],
    min_start: float,
    duration: float,
    blocked_ranges: list[tuple[float, float]],
) -> dict | None:
    """Find the best fallback phrase when AI returned 0 events for a clip.

    Scans all contiguous windows of 2-5 words that start after min_start,
    don't overlap blocked ranges, and picks the one with the longest combined
    word length (most "substantial" text).
    """
    best: dict | None = None
    best_length = 0

    total = len(words)
    for phrase_len in range(2, 6):  # 2 to 5 words
        for start_idx in range(total - phrase_len + 1):
            end_idx = start_idx + phrase_len - 1
            phrase_words = words[start_idx:end_idx + 1]

            # All words in the phrase must have non-empty text.
            if any(not str(w.get("word") or "").strip() for w in phrase_words):
                continue

            start = max(0.0, _safe_float(phrase_words[0].get("start"), 0))
            if start < min_start or start >= duration - 1.0:
                continue

            spoken_end = max(start, _safe_float(phrase_words[-1].get("end"), start))
            end = min(duration, max(spoken_end + 0.55, start + 1.65))
            end = min(end, start + 2.8)
            if end - start < 1.0:
                continue

            if any(_ranges_overlap(start, end, a, b) for a, b in blocked_ranges):
                continue

            combined_length = sum(
                len(str(w.get("word") or "").strip()) for w in phrase_words
            )
            if combined_length > best_length:
                best_length = combined_length
                text = " ".join(
                    str(w.get("word") or "").strip() for w in phrase_words
                )
                text = re.sub(r"\s+([,.;:!?])", r"\1", text).strip()
                if not text:
                    continue
                best = {
                    "id": "emphasis_fallback",
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": text,
                    "effect": "spotlight",
                    "position": "center",
                    "start_word": start_idx,
                    "end_word": end_idx,
                    "reason": "auto_fallback",
                }
    return best


def _sample_contiguous_indices(total: int, limit: int) -> list[int]:
    if total <= limit:
        return list(range(total))
    window_count = 6
    window_size = max(8, limit // window_count)
    starts = [round(i * max(0, total - window_size) / (window_count - 1)) for i in range(window_count)]
    indices = {index for start in starts for index in range(start, min(total, start + window_size))}
    return sorted(indices)[:limit]


def _parse_word_id(value: object) -> int | None:
    if isinstance(value, int):
        return value
    match = re.search(r"(\d+)", str(value or ""))
    return int(match.group(1)) if match else None


def _ranges_overlap(start: float, end: float, other_start: float, other_end: float) -> bool:
    return max(start, other_start) < min(end, other_end)


def _safe_float(value: object, default: float) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _clamp_number(value: object, minimum: float, maximum: float, fallback: float) -> float:
    return min(maximum, max(minimum, _safe_float(value, fallback)))
