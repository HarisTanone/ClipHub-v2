"""Cheap production helpers: smart thumb, virality explain, CTA, dead-air.

No new deps. Wire into V2 assemble + folder structure.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

# Retention-killer silence gap (seconds) between words
DEAD_AIR_GAP_S = 1.4
DEAD_AIR_MIN_GAPS = 1

CTA_TEMPLATES = (
    "Follow biar nggak ketinggalan part 2 🔥",
    "Save dulu, nonton lagi nanti 📌",
    "Komen setuju atau nggak 👇",
    "Share ke temen yang perlu dengar ini",
)


def smart_thumbnail_seek(
    words: list[dict] | None,
    duration: float,
    hook: str = "",
) -> float:
    """Pick seek time for thumbnail: peak energy word mid-clip, not fixed 1s.

    Priority: longest word in first 40% (hook face) → 25% of duration → 1.0s.
    """
    dur = max(0.5, float(duration or 1.0))
    fallback = min(max(1.0, dur * 0.25), max(0.5, dur - 0.3))
    if not words:
        return round(fallback, 2)

    window_end = max(1.0, dur * 0.45)
    best_t, best_score = fallback, -1.0
    for w in words:
        try:
            s = float(w.get("start", w.get("s", 0)) or 0)
            e = float(w.get("end", w.get("e", s + 0.2)) or s + 0.2)
            text = str(w.get("word", w.get("text", "")) or "")
        except (TypeError, ValueError):
            continue
        if s < 0.3 or s > window_end:
            continue
        mid = (s + e) * 0.5
        # Prefer longer spoken tokens + mid-face window
        score = (e - s) * 2.0 + min(len(text), 12) * 0.05
        if 0.8 <= mid <= window_end:
            score += 0.5
        if score > best_score:
            best_score = score
            best_t = mid
    return round(min(max(0.3, best_t), max(0.3, dur - 0.2)), 2)


def generate_smart_thumbnail(
    video_path: str,
    thumb_path: str,
    seek: float = 1.0,
    width: int = 360,
) -> bool:
    """ffmpeg single-frame thumb at smart seek. Returns True on success."""
    if not video_path or not os.path.exists(video_path):
        return False
    os.makedirs(os.path.dirname(thumb_path) or ".", exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{max(0.0, float(seek)):.2f}",
        "-i", video_path,
        "-frames:v", "1",
        "-vf", f"scale={width}:-1",
        "-q:v", "3",
        thumb_path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return r.returncode == 0 and os.path.exists(thumb_path)
    except Exception as exc:
        logger.debug("smart_thumb fail: %s", exc)
        return False


def virality_breakdown(
    score: int | float,
    hook: str = "",
    reason: str = "",
    duration: float = 0.0,
    words: list[dict] | None = None,
    broll_count: int = 0,
) -> dict[str, Any]:
    """Explainable virality components (0-100 each + total). No LLM."""
    hook_s = (hook or "").strip()
    reason_s = (reason or "").strip().lower()
    words = words or []

    # Hook punch: short + question/number/shock cues
    hook_len = len(hook_s.split())
    hook_score = 55.0
    if 3 <= hook_len <= 10:
        hook_score += 20
    elif hook_len <= 12:
        hook_score += 10
    if "?" in hook_s or any(c.isdigit() for c in hook_s):
        hook_score += 15
    if any(x in hook_s.lower() for x in ("rahasia", "gila", "jangan", "kenapa", "cara")):
        hook_score += 10
    hook_score = min(100.0, hook_score)

    # Retention proxy: duration sweet-spot 15-45s + low dead-air
    dur = float(duration or 0)
    if 15 <= dur <= 45:
        ret_score = 85.0
    elif 10 <= dur <= 60:
        ret_score = 70.0
    else:
        ret_score = 50.0
    gaps = dead_air_gaps(words)
    if gaps:
        ret_score = max(30.0, ret_score - 12 * min(3, len(gaps)))
    ret_score = min(100.0, ret_score)

    # Emotion/conflict cues from reason
    emo_score = 50.0
    for kw, pts in (
        ("marah", 20), ("ribut", 18), ("shock", 18), ("twist", 15),
        ("emotion", 12), ("energy", 10), ("conflict", 15), ("lucu", 12),
        ("surprise", 12), ("climactic", 15),
    ):
        if kw in reason_s:
            emo_score += pts
    emo_score = min(100.0, emo_score)

    # Visual density: broll + word density
    wpm = (len(words) / max(dur, 1.0)) * 60.0 if words else 0.0
    vis_score = 40.0 + min(30.0, broll_count * 12.0)
    if 80 <= wpm <= 180:
        vis_score += 20
    elif wpm > 40:
        vis_score += 10
    vis_score = min(100.0, vis_score)

    # Blend with model score (already 0-100-ish)
    model = float(score or 0)
    total = (
        0.30 * model
        + 0.25 * hook_score
        + 0.20 * ret_score
        + 0.15 * emo_score
        + 0.10 * vis_score
    )
    return {
        "total": round(total, 1),
        "model_score": round(model, 1),
        "hook_punch": round(hook_score, 1),
        "retention": round(ret_score, 1),
        "emotion": round(emo_score, 1),
        "visual_density": round(vis_score, 1),
        "dead_air_gaps": len(gaps),
        "factors": _top_factors(hook_score, ret_score, emo_score, vis_score, model),
    }


def _top_factors(hook: float, ret: float, emo: float, vis: float, model: float) -> list[str]:
    parts = [
        ("hook_punch", hook),
        ("retention", ret),
        ("emotion", emo),
        ("visual_density", vis),
        ("model_score", model),
    ]
    parts.sort(key=lambda x: -x[1])
    return [p[0] for p in parts[:3]]


def dead_air_gaps(words: list[dict] | None, gap_s: float = DEAD_AIR_GAP_S) -> list[dict]:
    """Find silence gaps between consecutive words (retention killers)."""
    if not words or len(words) < 2:
        return []
    ordered = []
    for w in words:
        try:
            s = float(w.get("start", w.get("s", 0)) or 0)
            e = float(w.get("end", w.get("e", s)) or s)
        except (TypeError, ValueError):
            continue
        ordered.append((s, e))
    ordered.sort(key=lambda x: x[0])
    gaps = []
    for i in range(1, len(ordered)):
        prev_e = ordered[i - 1][1]
        cur_s = ordered[i][0]
        g = cur_s - prev_e
        if g >= gap_s:
            gaps.append({"at": round(prev_e, 2), "duration": round(g, 2)})
    return gaps


def suggest_cta(hook: str = "", reason: str = "", rank: int = 1) -> dict[str, Any]:
    """End-card CTA text + placement hint. Deterministic from hook/rank."""
    h = (hook or "").strip()
    r = (reason or "").lower()
    if any(x in r for x in ("part", "lanjut", "series", "episode")):
        text = CTA_TEMPLATES[0]
        kind = "follow_series"
    elif "?" in h:
        text = CTA_TEMPLATES[2]
        kind = "comment"
    elif rank == 1:
        text = CTA_TEMPLATES[1]
        kind = "save"
    else:
        text = CTA_TEMPLATES[rank % len(CTA_TEMPLATES)]
        kind = "engage"
    return {
        "text": text,
        "type": kind,
        "kind": kind,
        "position": "end",
        "at": "end",
        "duration_sec": 1.5,
        "duration": 1.5,
        "style": "bottom_pill",
    }


def retention_trim_hints(words: list[dict] | None, duration: float) -> dict[str, Any]:
    """Suggest trim windows that kill dead-air (for editor / re-render)."""
    gaps = dead_air_gaps(words)
    if not gaps:
        return {"should_trim": False, "gaps": [], "suggested_cuts": []}
    cuts = []
    for g in gaps:
        # Suggest cut from mid-gap start, keep 0.15s pad each side
        pad = 0.15
        cut_start = round(g["at"] + pad, 2)
        cut_end = round(g["at"] + g["duration"] - pad, 2)
        if cut_end - cut_start >= 0.8:
            cuts.append({"start": cut_start, "end": cut_end, "reason": "dead_air"})
    return {
        "should_trim": len(cuts) > 0,
        "gaps": gaps,
        "suggested_cuts": cuts[:4],
        "clip_duration": round(float(duration or 0), 2),
    }
