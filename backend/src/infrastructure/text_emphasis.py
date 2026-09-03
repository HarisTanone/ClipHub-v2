"""Safe contract for sparse AI-selected cinematic text.

The LLM is only allowed to choose word IDs. All final text and timestamps are
rebuilt from Whisper words here, keeping audio, subtitles, and lip-sync on the
same timeline.
"""
from __future__ import annotations

import math
import re
from typing import Iterable


# ─── New premium pack (2026-07-29) ────────────────────────────────────────────
# Old names map via LEGACY_EFFECT_MAP / LEGACY_ANIM_MAP so saved presets survive.

ALLOWED_EFFECTS = {
    "depth_cutout",   # text behind person cutout
    "hero_punch",     # center hero + vignette + accent bar
    "side_rail",      # editorial side label
    "float_track",    # bob following person
    "smart_gap",      # auto place in empty space
    "orbit_halo",     # orbit around head
    "z_parallax",     # depth scale with person
    "word_cascade",   # word-by-word kinetic
    "split_impact",   # two-tone split slam
    "type_pulse",     # typewriter + pulse glow
    "sticker_pop",    # comic sticker rotate pop
    "mirror_echo",    # ghost echo trail
}

ALLOWED_ANIMATIONS = {
    "rise",
    "impact",
    "slide",
    "static_glitch",
    "glow",
    "elastic",
    "blur_in",
    "flip_y",
}

LEGACY_EFFECT_MAP = {
    "behind_person": "depth_cutout",
    "spotlight": "hero_punch",
    "side_label": "side_rail",
    "floating_text": "float_track",
    "auto_avoid": "smart_gap",
    "around_head": "orbit_halo",
    "depth_text": "z_parallax",
    "kinetic_type": "word_cascade",
}

LEGACY_ANIM_MAP = {
    "cinematic": "rise",
    "slam": "impact",
    "reveal": "slide",
    "glitch": "static_glitch",
    "neon": "glow",
}

# Effects that need YOLO person foreground / tracking metadata
TRACKING_EFFECTS = {
    "depth_cutout",
    "float_track",
    "smart_gap",
    "orbit_halo",
    "z_parallax",
}

ALLOWED_POSITIONS = {"left", "center", "right"}

DEFAULT_TEXT_EMPHASIS_STYLE = {
    "effectMode": "auto",
    "animation": "impact",
    "fontFamily": "Bebas Neue",
    "fontSize": 104,
    "fontWeight": "900",
    "letterSpacing": 2,
    "lineHeight": 0.9,
    "color": "#FFFFFF",
    "accentColor": "#FF3B5C",
    "uppercase": True,
    "strokeEnabled": True,
    "strokeColor": "#0A0A0B",
    "strokeWidth": 3,
    "shadowEnabled": True,
    "shadowColor": "#000000",
    "shadowBlur": 28,
    "positionY": 48,
    "maxWidthPct": 86,
    "maskFeather": 9,
    # Effect-specific tuning
    "floatSpeed": 1.15,
    "avoidPadding": 44,
    "aroundHeadRadius": 58,
    "depthIntensity": 0.55,
    "depthParallax": 0.4,
    "depthFade": 0.4,
    "kineticStagger": 5,
    "echoOffset": 10,
    "stickerAngle": -6,
    "typeSpeed": 1.4,
}


def map_legacy_effect(name: object) -> str:
    raw = str(name or "").strip()
    if raw in ALLOWED_EFFECTS or raw == "auto":
        return raw
    return LEGACY_EFFECT_MAP.get(raw, raw)


def map_legacy_animation(name: object) -> str:
    raw = str(name or "").strip()
    if raw in ALLOWED_ANIMATIONS:
        return raw
    return LEGACY_ANIM_MAP.get(raw, raw)


def normalise_text_emphasis_style(style: object) -> dict:
    """Return a render-safe style without trusting arbitrary client values."""
    incoming = style if isinstance(style, dict) else {}
    # Map legacy keys before merge so defaults win cleanly on unknown fields
    if "effectMode" in incoming:
        incoming = {**incoming, "effectMode": map_legacy_effect(incoming.get("effectMode"))}
    if "animation" in incoming:
        incoming = {**incoming, "animation": map_legacy_animation(incoming.get("animation"))}
    result = {**DEFAULT_TEXT_EMPHASIS_STYLE, **incoming}

    effect_mode = map_legacy_effect(result.get("effectMode", "auto"))
    result["effectMode"] = effect_mode if effect_mode in ALLOWED_EFFECTS | {"auto"} else "auto"
    animation = map_legacy_animation(result.get("animation", "impact"))
    result["animation"] = animation if animation in ALLOWED_ANIMATIONS else "impact"
    result["fontFamily"] = str(result.get("fontFamily") or "Bebas Neue")[:80]
    result["fontWeight"] = str(result.get("fontWeight") or "900")[:8]
    result["fontSize"] = _clamp_number(result.get("fontSize"), 32, 160, 104)
    result["letterSpacing"] = _clamp_number(result.get("letterSpacing"), -4, 20, 2)
    result["lineHeight"] = _clamp_number(result.get("lineHeight"), 0.7, 1.5, 0.9)
    result["strokeWidth"] = _clamp_number(result.get("strokeWidth"), 0, 12, 3)
    result["shadowBlur"] = _clamp_number(result.get("shadowBlur"), 0, 80, 28)
    result["positionY"] = _clamp_number(result.get("positionY"), 12, 88, 48)
    result["maxWidthPct"] = _clamp_number(result.get("maxWidthPct"), 35, 96, 86)
    result["maskFeather"] = int(_clamp_number(result.get("maskFeather"), 1, 31, 9))
    if result["maskFeather"] % 2 == 0:
        result["maskFeather"] += 1
    result["floatSpeed"] = _clamp_number(result.get("floatSpeed"), 0.5, 3.0, 1.15)
    result["avoidPadding"] = _clamp_number(result.get("avoidPadding"), 10, 120, 44)
    result["aroundHeadRadius"] = _clamp_number(result.get("aroundHeadRadius"), 30, 120, 58)
    result["depthIntensity"] = _clamp_number(result.get("depthIntensity"), 0.1, 1.0, 0.55)
    result["depthParallax"] = _clamp_number(result.get("depthParallax"), 0.05, 1.0, 0.4)
    result["depthFade"] = _clamp_number(result.get("depthFade"), 0.1, 1.5, 0.4)
    result["kineticStagger"] = _clamp_number(result.get("kineticStagger"), 1, 18, 5)
    result["echoOffset"] = _clamp_number(result.get("echoOffset"), 4, 28, 10)
    result["stickerAngle"] = _clamp_number(result.get("stickerAngle"), -18, 18, -6)
    result["typeSpeed"] = _clamp_number(result.get("typeSpeed"), 0.5, 3.0, 1.4)

    for key, fallback in (
        ("color", "#FFFFFF"),
        ("accentColor", "#FF3B5C"),
        ("strokeColor", "#0A0A0B"),
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
        # Adaptive tail pad so short clips still accept emphasis events.
        tail_pad = min(1.0, max(0.15, duration * 0.08)) if duration > 0 else 0.15
        max_start = max(min_start + 0.05, duration - tail_pad) if duration > 0 else min_start
        min_hold = 0.45 if duration < 3.0 else 0.8
        max_hold = min(2.8, max(0.9, duration * 0.4))
        gap_min = min(6.0, max(1.2, duration * 0.25))
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
            if start < min_start or start >= max_start:
                continue

            # A short hold makes the phrase readable without shifting its anchor.
            end = min(duration, max(spoken_end + 0.35, start + min_hold))
            end = min(end, start + max_hold, duration)
            if end - start < min_hold * 0.75:
                continue
            if any(_ranges_overlap(start, end, a, b) for a, b in blocked.get(rank, [])):
                continue
            if any(abs(start - event["start"]) < gap_min for event in accepted):
                continue

            requested_effect = map_legacy_effect(raw.get("effect") or "hero_punch")
            effect = mode if mode != "auto" else requested_effect
            if effect not in ALLOWED_EFFECTS:
                effect = "hero_punch"
            position = str(raw.get("position") or ("left" if effect == "side_rail" else "center"))
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
                words,
                min_start,
                duration,
                blocked.get(rank, []),
                effect=mode if mode in ALLOWED_EFFECTS else "hero_punch",
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
    effect: str = "hero_punch",
) -> dict | None:
    """Find the best fallback phrase when AI returned 0 events for a clip.

    Scans all contiguous windows of 1-5 words that start after min_start,
    don't overlap blocked ranges, and picks the one with the longest combined
    word length (most "substantial" text). Works for short clips too.
    If all windows overlap blocked ranges, a relaxed pass selects the window with
    least overlap to guarantee AI text is not lost.
    """
    best: dict | None = None
    best_length = 0
    tail_pad = min(1.0, max(0.15, duration * 0.08)) if duration > 0 else 0.15
    max_start = max(min_start + 0.05, duration - tail_pad) if duration > 0 else min_start
    min_hold = 0.45 if duration < 3.0 else 0.8
    max_hold = min(2.8, max(0.9, duration * 0.4))

    total = len(words)
    for phrase_len in range(1, 6):  # 1 to 5 words (short clips need 1-word)
        for start_idx in range(total - phrase_len + 1):
            end_idx = start_idx + phrase_len - 1
            phrase_words = words[start_idx:end_idx + 1]

            # All words in the phrase must have non-empty text.
            if any(not str(w.get("word") or "").strip() for w in phrase_words):
                continue

            start = max(0.0, _safe_float(phrase_words[0].get("start"), 0))
            if start < min_start or start >= max_start:
                continue

            spoken_end = max(start, _safe_float(phrase_words[-1].get("end"), start))
            end = min(duration, max(spoken_end + 0.35, start + min_hold))
            end = min(end, start + max_hold, duration)
            if end - start < min_hold * 0.75:
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
                    "effect": effect,
                    "position": "center",
                    "start_word": start_idx,
                    "end_word": end_idx,
                    "reason": "auto_fallback",
                }

    # Relaxed pass: if all windows collided with blocked ranges, choose candidate with minimal collision
    if best is None and words:
        least_overlap = float("inf")
        for phrase_len in range(1, 5):
            for start_idx in range(total - phrase_len + 1):
                end_idx = start_idx + phrase_len - 1
                phrase_words = words[start_idx:end_idx + 1]
                if any(not str(w.get("word") or "").strip() for w in phrase_words):
                    continue
                start = max(0.0, _safe_float(phrase_words[0].get("start"), 0))
                if start < min_start:
                    continue
                spoken_end = max(start, _safe_float(phrase_words[-1].get("end"), start))
                end = min(duration, max(spoken_end + 0.35, start + min_hold))
                end = min(end, start + max_hold, duration)
                if end - start < 0.3:
                    continue

                overlap_dur = sum(
                    max(0.0, min(end, b) - max(start, a))
                    for a, b in blocked_ranges
                )
                if overlap_dur < least_overlap:
                    least_overlap = overlap_dur
                    text = " ".join(str(w.get("word") or "").strip() for w in phrase_words)
                    text = re.sub(r"\s+([,.;:!?])", r"\1", text).strip()
                    if text:
                        best = {
                            "id": "emphasis_fallback",
                            "start": round(start, 3),
                            "end": round(end, 3),
                            "text": text,
                            "effect": effect,
                            "position": "center",
                            "start_word": start_idx,
                            "end_word": end_idx,
                            "reason": "auto_fallback_relaxed",
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
