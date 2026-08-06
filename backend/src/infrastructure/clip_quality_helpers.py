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


# ─── Per-clip analisa JSON (split meta for AI / assets) ──────────────────────

def extract_highlight_keywords(words: list[dict] | None, limit: int = 12) -> list[str]:
    """Keywords for subtitle highlight / soft seed (highlight|proper|long tokens).

    No stopword lexicon — AI visual_entities is the real seed path.
    """
    out: list[str] = []
    seen: set[str] = set()
    for w in words or []:
        text = str(w.get("word", w.get("text", "")) or "").strip()
        if not text or len(text) < 3:
            continue
        key = re.sub(r"[^\w\-]+", "", text, flags=re.UNICODE).lower()
        if not key or key in seen:
            continue
        flagged = bool(w.get("highlight"))
        proper = text[:1].isupper() and not text.isupper()
        longish = len(key) >= 5
        if flagged or proper or longish:
            seen.add(key)
            out.append(text.strip(".,!?;:\"'"))
        if len(out) >= limit:
            break
    return out


def extract_objects(
    words: list[dict] | None,
    footage_keywords: list[str] | None = None,
    limit: int = 20,
    visual_entities: list[dict] | None = None,
) -> list[dict[str, Any]]:
    """Timed objects for B-roll / overlay.

    AI visual_entities first. If thin (<3), top-up proper-case spoken tokens only
    (brand-like ASR) — no domain/stopword lexicon, no bare filler pad.
    Full offline path only when AI empty.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    had_ai = False

    for e in visual_entities or []:
        if not isinstance(e, dict):
            continue
        word = str(e.get("word") or e.get("label") or "").strip()
        if not word:
            continue
        low = re.sub(r"[^\w\-]+", "", word, flags=re.UNICODE).lower()
        if not low or low in seen:
            continue
        try:
            s = float(e.get("start", 0) or 0)
            end = float(e.get("end", s + 0.3) or s + 0.3)
        except (TypeError, ValueError):
            s, end = 0.0, 0.3
        seen.add(low)
        had_ai = True
        try:
            prio = int(e.get("priority") or 5)
        except (TypeError, ValueError):
            prio = 5
        out.append({
            "word": word,
            "start": round(s, 3),
            "end": round(end, 3),
            "label": str(e.get("label") or word),
            "entity_type": str(e.get("entity_type") or e.get("type") or "object"),
            "priority": max(1, min(10, prio)),
            "query_id": str(e.get("query_id") or ""),
            "query_en": str(e.get("query_en") or ""),
            "search_queries": list(e.get("search_queries") or []),
            "source": str(e.get("source") or "ai"),
        })
        if len(out) >= limit:
            return out

    # Thin AI or empty → proper-case tokens from words (Aikos/Shisha/Rokok)
    # Skip all-lowercase long fillers (ediknya/menyusahkan) when AI already present.
    need = 3 if had_ai else limit
    if len(out) < need:
        for w in words or []:
            try:
                text = str(w.get("word", w.get("text", "")) or "").strip().strip(".,!?;:\"'")
                s = float(w.get("start", w.get("s", 0)) or 0)
                e = float(w.get("end", w.get("e", s + 0.2)) or s + 0.2)
            except (TypeError, ValueError):
                continue
            clean = re.sub(r"[^\w\-]+", "", text, flags=re.UNICODE)
            if len(clean) < 4:
                continue
            low = clean.lower()
            if low in seen:
                continue
            proper = clean[:1].isupper() and not clean.isupper()
            if had_ai:
                hit = proper  # brand-like only when topping up AI
            else:
                hit = (
                    bool(w.get("highlight"))
                    or proper
                    or len(clean) >= 6
                )
            if not hit:
                continue
            # Skip very early chatter only when topping up thin AI
            if had_ai and s < 1.5:
                continue
            seen.add(low)
            out.append({
                "word": clean,
                "start": round(s, 3),
                "end": round(e, 3),
                "label": clean[:1].upper() + clean[1:],
                "query_id": f"{clean} close up",
                "query_en": clean,
                "search_queries": [clean, f"{clean} close up", f"{clean} product"],
                "source": "fallback" if had_ai else "heuristic",
            })
            if len(out) >= limit:
                break

    if had_ai:
        return out  # no footage_kw pad over AI

    for kw in footage_keywords or []:
        raw = " ".join(str(kw or "").split())
        if not raw or " " not in raw:
            continue
        low = raw.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append({
            "word": raw,
            "start": 0.0,
            "end": 0.0,
            "label": raw,
            "query_id": raw,
            "query_en": raw,
            "search_queries": [raw],
            "source": "footage_kw",
        })
        if len(out) >= limit:
            break
    return out


def build_clip_analisa(
    *,
    no: int,
    rank: int,
    start: float,
    end: float,
    hook: str = "",
    reason: str = "",
    score: int | float = 0,
    words: list[dict] | None = None,
    broll_suggestions: list[dict] | None = None,
    text_emphasis_events: list[dict] | None = None,
    top_overlay_events: list[dict] | None = None,
    object_overlay_events: list[dict] | None = None,
    visual_entities: list[dict] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One-clip analisa payload written to json_analisa/clip_{n}.json."""
    words = list(words or [])
    broll = list(broll_suggestions or [])
    dur = float(end) - float(start)
    footage_kw: list[str] = []
    seen_fk: set[str] = set()
    for s in broll:
        kw = str(s.get("keyword") or "").strip()
        if not kw:
            continue
        low = kw.lower()
        if low in seen_fk:
            continue
        seen_fk.add(low)
        footage_kw.append(kw)
    hl = extract_highlight_keywords(words)
    # AI entities only → footage; bare highlight tokens poison stock search
    object_queries = extract_objects(
        words, footage_kw, visual_entities=visual_entities
    )
    for o in object_queries:
        for q in (
            str(o.get("query_en") or ""),
            str(o.get("query_id") or ""),
            *list(o.get("search_queries") or []),
        ):
            q = " ".join(str(q or "").split())
            if not q:
                continue
            low = q.lower()
            if low not in seen_fk:
                seen_fk.add(low)
                footage_kw.append(q)
    try:
        viral = virality_breakdown(score, hook, reason, dur, words, len(broll))
        cta = suggest_cta(hook, reason, rank)
        retention = retention_trim_hints(words, dur)
        thumb = smart_thumbnail_seek(words, dur, hook)
    except Exception:
        viral, cta, retention, thumb = {}, {}, {}, 1.0

    body = {
        "rank": rank,
        "start": start,
        "end": end,
        "duration": round(dur, 3),
        "hook": hook,
        "reason": reason,
        "score": score,
        "highlight_keywords": hl,
        "footage_keywords": footage_kw[:16],
        "objects": object_queries,
        "broll_suggestions": broll,
        "text_emphasis_events": list(text_emphasis_events or [])[:4],
        "top_overlay_events": list(top_overlay_events or []),
        "object_overlay_events": list(object_overlay_events or []),
        "visual_entities": list(visual_entities or []),
        "hyperframes_polish": (extra or {}).get("hyperframes_polish") if extra else None,
        "thumb_seek": thumb,
        "virality": viral,
        "cta": cta,
        "retention_hints": retention,
        "words": words,
    }

    # Generate captions for social media posting
    try:
        cap_pack = build_share_pack(
            hook=hook, reason=reason, score=score or 0,
            duration=dur, words=words,
            visual_entities=visual_entities,
            cta=cta, virality=viral, rank=rank,
        )
        body["captions"] = cap_pack.get("captions", {})
        body["hashtags"] = cap_pack.get("hashtags", [])
        body["hook_alts"] = cap_pack.get("hook_alts", [])
    except Exception:
        body["captions"] = {}

    if extra:
        body.update(extra)
    return {"no": no, "clips": [body]}


# ─── Selling surface: share pack / hook roulette / clip DNA / A-B / chapters ──


def _slug_tag(text: str) -> str:
    t = re.sub(r"[^\w\s\-]", "", (text or "").lower(), flags=re.UNICODE)
    t = re.sub(r"\s+", "", t)
    return t[:28]


def hook_roulette(hook: str = "", reason: str = "", n: int = 6) -> list[dict[str, Any]]:
    """Deterministic hook alt lines — structural transforms only, no domain lexicon."""
    base = " ".join((hook or "").split()).strip()
    if not base:
        base = " ".join((reason or "").split())[:80].strip() or "Momen ini wajib ditonton"
    words = base.split()
    alts: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(text: str, style: str) -> None:
        t = " ".join(text.split()).strip()
        if not t or len(t) < 4:
            return
        key = t.lower()
        if key in seen:
            return
        seen.add(key)
        alts.append({"text": t[:120], "style": style, "chars": len(t)})

    add(base, "original")
    add(f"{base}?" if "?" not in base else base, "question")
    add(f"STOP. {base}", "stop")
    add(f"Wait… {base}", "wait")
    if words:
        add(f"{words[0].upper()}: {' '.join(words[1:])}".strip(": "), "colon")
        add(" ".join(w.upper() if i < min(3, len(words)) else w for i, w in enumerate(words)), "caps_lead")
    add(f"{base} 🔥", "emoji_fire")
    add(f"Part {max(1, n % 5)} — {base}", "series")
    if len(words) > 4:
        add(" ".join(words[:4]) + "…", "tease")
        add(" ".join(words[-4:]), "tail")
    # numeric punch if none
    if not any(c.isdigit() for c in base):
        add(f"3 detikkah? {base}", "number_bait")
    return alts[: max(1, min(n, 12))]


def build_share_pack(
    *,
    hook: str = "",
    reason: str = "",
    score: int | float = 0,
    duration: float = 0.0,
    words: list[dict] | None = None,
    visual_entities: list[dict] | None = None,
    cta: dict | None = None,
    virality: dict | None = None,
    rank: int = 1,
) -> dict[str, Any]:
    """One-click TikTok/IG/YT caption + hashtags + hook alts. No external API."""
    hook_s = " ".join((hook or "").split()).strip()
    reason_s = " ".join((reason or "").split()).strip()
    cta = cta or suggest_cta(hook_s, reason_s, rank)
    viral = virality or virality_breakdown(score, hook_s, reason_s, duration, words or [])
    entities = []
    for e in visual_entities or []:
        if not isinstance(e, dict):
            continue
        w = str(e.get("word") or e.get("label") or "").strip()
        if w and w.lower() not in {x.lower() for x in entities}:
            entities.append(w)
        if len(entities) >= 6:
            break
    # hashtags from hook tokens + entities (length/proper only — no stop lexicon)
    tags: list[str] = ["fyp", "viral", "foryou", "autoclip"]
    for tok in re.findall(r"[\w\-]{4,}", hook_s, flags=re.UNICODE)[:5]:
        tags.append(_slug_tag(tok) or tok.lower()[:20])
    for ent in entities[:4]:
        tags.append(_slug_tag(ent) or ent.lower()[:20])
    # dedupe keep order
    seen_t: set[str] = set()
    hashtags = []
    for t in tags:
        t = t.lstrip("#").lower()
        if not t or t in seen_t:
            continue
        seen_t.add(t)
        hashtags.append(f"#{t}")
    hashtags = hashtags[:12]

    alts = hook_roulette(hook_s, reason_s, n=6)
    caption_tt = "\n".join(
        x for x in [
            hook_s or "Clip siap post",
            "",
            (cta or {}).get("text") or "",
            "",
            " ".join(hashtags[:8]),
        ] if x is not None
    ).strip()
    caption_ig = "\n".join(
        x for x in [
            hook_s,
            reason_s[:160] if reason_s else "",
            "",
            (cta or {}).get("text") or "Save biar gampang dicari 📌",
            "",
            " ".join(hashtags),
        ] if x
    ).strip()
    caption_yt = "\n".join(
        x for x in [
            hook_s,
            "",
            reason_s[:280] if reason_s else "",
            "",
            f"CTA: {(cta or {}).get('text') or ''}",
            "",
            " ".join(hashtags),
        ] if x is not None
    ).strip()

    return {
        "hook": hook_s,
        "hook_alts": alts,
        "cta": cta,
        "hashtags": hashtags,
        "entities": entities,
        "captions": {
            "tiktok": caption_tt,
            "instagram": caption_ig,
            "youtube": caption_yt,
            "plain": hook_s,
        },
        "virality": viral,
        "posting_tips": _posting_tips(duration, viral),
        "best_post_windows": ["07:00-09:00", "12:00-13:30", "19:00-22:00"],
    }


def _posting_tips(duration: float, viral: dict) -> list[str]:
    tips = []
    dur = float(duration or 0)
    if dur and dur < 15:
        tips.append("Durasi pendek — taruh hook di 0.5s pertama")
    elif dur > 45:
        tips.append(">45s: potong dead-air, CTA di 3 detik terakhir")
    else:
        tips.append("Sweet-spot 15–45s — bagus untuk FYP")
    total = float((viral or {}).get("total") or (viral or {}).get("score") or 0)
    if total >= 75:
        tips.append("Skor tinggi — post asap, pin komentar CTA")
    elif total and total < 50:
        tips.append("Skor sedang — coba hook roulette + A/B style")
    if (viral or {}).get("dead_air_gaps"):
        tips.append("Ada silent gap — apply retention trim sebelum post")
    tips.append("Cover frame = smart thumb (bukan 0s)")
    return tips[:5]


def clip_dna(
    *,
    score: int | float = 0,
    hook: str = "",
    reason: str = "",
    duration: float = 0.0,
    words: list[dict] | None = None,
    broll_count: int = 0,
    visual_entities: list[dict] | None = None,
    virality: dict | None = None,
) -> dict[str, Any]:
    """Radar-style clip DNA from virality components + entity density."""
    v = virality or virality_breakdown(score, hook, reason, duration, words or [], broll_count)
    axes = {
        "hook_punch": float(v.get("hook_punch") or v.get("hook") or 0),
        "retention": float(v.get("retention") or 0),
        "emotion": float(v.get("emotion") or 0),
        "visual_density": float(v.get("visual_density") or v.get("visual") or 0),
        "model_score": float(v.get("model_score") or score or 0),
    }
    ent_n = len(visual_entities or [])
    axes["entity_richness"] = min(100.0, 30.0 + ent_n * 12.0)
    # archetype from top 2 axes
    ranked = sorted(axes.items(), key=lambda x: -x[1])
    top = [k for k, _ in ranked[:2]]
    archetype_map = {
        ("hook_punch", "emotion"): "shock_opener",
        ("emotion", "hook_punch"): "shock_opener",
        ("retention", "hook_punch"): "story_arc",
        ("hook_punch", "retention"): "story_arc",
        ("visual_density", "emotion"): "spectacle",
        ("emotion", "visual_density"): "spectacle",
        ("entity_richness", "visual_density"): "product_demo",
        ("visual_density", "entity_richness"): "product_demo",
    }
    arch = archetype_map.get((top[0], top[1]), "balanced_clip") if len(top) == 2 else "balanced_clip"
    total = float(v.get("total") or v.get("score") or 0)
    grade = "S" if total >= 85 else "A" if total >= 70 else "B" if total >= 55 else "C" if total >= 40 else "D"
    return {
        "axes": {k: round(val, 1) for k, val in axes.items()},
        "archetype": arch,
        "grade": grade,
        "total": round(total, 1),
        "top_factors": list(v.get("factors") or [t[0] for t in ranked[:3]]),
        "summary": f"{grade}-tier · {arch.replace('_', ' ')} · {round(total)} viral",
    }


def chapter_markers(words: list[dict] | None, duration: float = 0.0, max_n: int = 6) -> list[dict[str, Any]]:
    """Lightweight chapters from silence gaps + long tokens (editor scrub)."""
    words = words or []
    gaps = dead_air_gaps(words)
    marks: list[dict[str, Any]] = [{"t": 0.0, "label": "Hook", "kind": "start"}]
    for g in gaps[: max_n - 2]:
        marks.append({
            "t": round(float(g["at"]), 2),
            "label": f"Beat @ {g['at']:.1f}s",
            "kind": "gap",
            "gap": g.get("duration"),
        })
    # peak long word mid
    if words:
        mid_w = None
        best = -1.0
        for w in words:
            try:
                s = float(w.get("start", 0) or 0)
                text = str(w.get("word") or w.get("text") or "")
            except (TypeError, ValueError):
                continue
            score = len(text) + (5 if w.get("highlight") else 0)
            if score > best and s > 1.0:
                best = score
                mid_w = (s, text)
        if mid_w:
            marks.append({"t": round(mid_w[0], 2), "label": mid_w[1][:24], "kind": "peak"})
    dur = float(duration or 0)
    if dur > 2:
        marks.append({"t": round(max(0.0, dur - 1.5), 2), "label": "CTA", "kind": "cta"})
    # unique by t
    seen: set[float] = set()
    out = []
    for m in sorted(marks, key=lambda x: x["t"]):
        key = round(float(m["t"]), 1)
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
        if len(out) >= max_n:
            break
    return out


def ab_style_variants(base_hook: dict | None = None, base_sub: dict | None = None, n: int = 3) -> list[dict[str, Any]]:
    """A/B style packs for one-click multi-variant restyle (Remotion + HF mix)."""
    from src.infrastructure.hf_style_catalog import HOOK_STYLES, SUBTITLE_STYLES

    hook_ids = [h["id"] for h in HOOK_STYLES]
    sub_ids = [s["id"] for s in SUBTITLE_STYLES]
    remotion_hooks = [
        "podcast_lower_third",
        "bold_center",
        "neon_glow",
        "typewriter",
        "comic_pop",
    ]
    remotion_subs = ["classic", "karaoke", "boxed", "minimal", "neon"]
    packs = [
        {
            "id": "premium_remotion",
            "label": "Premium Remotion",
            "note": "Full custom · render lebih lama",
            "hook_style_config": {
                **(base_hook or {}),
                "engine": "remotion",
                "animation": remotion_hooks[0],
            },
            "subtitle_style_config": {
                **(base_sub or {}),
                "engine": "remotion",
                "stylePreset": remotion_subs[0],
            },
        },
        {
            "id": "fast_hyperframes",
            "label": "Fast HyperFrames",
            "note": "Template fixed · render cepat",
            "hook_style_config": {
                **(base_hook or {}),
                "engine": "hyperframes",
                "hf_template": hook_ids[0] if hook_ids else "hook_banner_v1",
                "animation": "podcast_lower_third",
            },
            "subtitle_style_config": {
                **(base_sub or {}),
                "engine": "hyperframes",
                "hf_template": sub_ids[0] if sub_ids else "sub_caption_v1",
                "stylePreset": "classic",
            },
        },
        {
            "id": "mixed_neon",
            "label": "Mixed Neon",
            "note": "Hook Remotion + sub HF",
            "hook_style_config": {
                **(base_hook or {}),
                "engine": "remotion",
                "animation": remotion_hooks[2] if len(remotion_hooks) > 2 else remotion_hooks[0],
            },
            "subtitle_style_config": {
                **(base_sub or {}),
                "engine": "hyperframes",
                "hf_template": sub_ids[1] if len(sub_ids) > 1 else (sub_ids[0] if sub_ids else "sub_neon_v1"),
                "stylePreset": "neon",
            },
        },
        {
            "id": "documentary",
            "label": "Documentary Clean",
            "note": "Minimal sub + lower hook",
            "hook_style_config": {
                **(base_hook or {}),
                "engine": "hyperframes",
                "hf_template": hook_ids[-1] if hook_ids else "hook_lower_v1",
            },
            "subtitle_style_config": {
                **(base_sub or {}),
                "engine": "hyperframes",
                "hf_template": sub_ids[-1] if sub_ids else "sub_minimal_v1",
                "stylePreset": "minimal",
            },
        },
    ]
    return packs[: max(1, min(n, len(packs)))]


def enrich_clip_selling_fields(clip: dict[str, Any]) -> dict[str, Any]:
    """Attach share_pack / dna / chapters onto a clip dict (mutates + returns)."""
    words = clip.get("words") or []
    dur = float(clip.get("duration") or (float(clip.get("end") or 0) - float(clip.get("start") or 0)))
    viral = clip.get("virality") or virality_breakdown(
        clip.get("score") or 0,
        clip.get("hook") or "",
        clip.get("reason") or "",
        dur,
        words,
        len(clip.get("broll_suggestions") or []),
    )
    cta = clip.get("cta") or suggest_cta(clip.get("hook") or "", clip.get("reason") or "", int(clip.get("rank") or 1))
    pack = build_share_pack(
        hook=clip.get("hook") or "",
        reason=clip.get("reason") or "",
        score=clip.get("score") or 0,
        duration=dur,
        words=words,
        visual_entities=clip.get("visual_entities") or [],
        cta=cta,
        virality=viral,
        rank=int(clip.get("rank") or 1),
    )
    dna = clip_dna(
        score=clip.get("score") or 0,
        hook=clip.get("hook") or "",
        reason=clip.get("reason") or "",
        duration=dur,
        words=words,
        broll_count=len(clip.get("broll_suggestions") or []),
        visual_entities=clip.get("visual_entities") or [],
        virality=viral,
    )
    chapters = chapter_markers(words, dur)
    clip["virality"] = viral
    clip["cta"] = cta
    clip["share_pack"] = pack
    clip["clip_dna"] = dna
    clip["chapters"] = chapters
    clip["hook_alts"] = pack.get("hook_alts") or []
    return clip


def write_split_job_meta(
    output_dir: str,
    *,
    job_id: str,
    youtube_url: str | None,
    aspect_ratio: str | None,
    created_at: str | None,
    clip_payloads: list[dict[str, Any]],
    clips_total: int | None = None,
    clips_success: int | None = None,
) -> str:
    """Write json_analisa/clip_{n}.json + slim meta_{job_id}.json. Returns meta path."""
    import json as json_mod

    analisa_dir = os.path.join(output_dir, "json_analisa")
    os.makedirs(analisa_dir, exist_ok=True)
    index: list[dict[str, Any]] = []
    for payload in clip_payloads:
        no = int(payload.get("no") or 0)
        if no <= 0:
            clips = payload.get("clips") or []
            if clips:
                no = int(clips[0].get("rank") or 0)
        if no <= 0:
            continue
        rel = f"json_analisa/clip_{no}.json"
        abs_path = os.path.join(output_dir, rel)
        with open(abs_path, "w", encoding="utf-8") as f:
            json_mod.dump(payload, f, indent=2, ensure_ascii=False, default=str)
        index.append({"no": no, "path": rel})

    meta = {
        "job_id": job_id,
        "youtube_url": youtube_url,
        "aspect_ratio": aspect_ratio,
        "clips_total": clips_total if clips_total is not None else len(index),
        "clips_success": clips_success if clips_success is not None else len(index),
        "created_at": created_at,
        "clips": index,
    }
    meta_path = os.path.join(output_dir, f"meta_{job_id}.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json_mod.dump(meta, f, indent=2, ensure_ascii=False, default=str)
    return meta_path
