"""Object image+text overlay — AI visual entities → stock photo card on video.

Mentions/queries come from per-clip AI (analyze_visual_entities), not domain lexicons.
Style/anim knobs: settings + DB object_overlay_configs.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


def default_object_overlay_style() -> dict[str, Any]:
    """Defaults — mirrored in DB object_overlay_configs + env OBJECT_OVERLAY_*."""
    return {
        "enabled": bool(getattr(settings, "OBJECT_OVERLAY_ENABLED", True)),
        "max_per_clip": int(getattr(settings, "OBJECT_OVERLAY_MAX_PER_CLIP", 3)),
        "box_size_ratio": float(getattr(settings, "OBJECT_OVERLAY_BOX_SIZE", 0.28)),
        "corner_radius": int(getattr(settings, "OBJECT_OVERLAY_CORNER_RADIUS", 18)),
        "position": str(getattr(settings, "OBJECT_OVERLAY_POSITION", "top_right")),
        "animation": str(getattr(settings, "OBJECT_OVERLAY_ANIMATION", "slide_right")),
        "duration_sec": float(getattr(settings, "OBJECT_OVERLAY_DURATION", 2.4)),
        "margin_ratio": float(getattr(settings, "OBJECT_OVERLAY_MARGIN", 0.04)),
        "text_color": str(getattr(settings, "OBJECT_OVERLAY_TEXT_COLOR", "255,255,255")),
        "bg_color": str(getattr(settings, "OBJECT_OVERLAY_BG_COLOR", "20,20,24")),
        "border_color": str(getattr(settings, "OBJECT_OVERLAY_BORDER_COLOR", "255,255,255")),
        "font_scale": float(getattr(settings, "OBJECT_OVERLAY_FONT_SCALE", 0.55)),
        "opacity": float(getattr(settings, "OBJECT_OVERLAY_OPACITY", 0.95)),
        "min_relevance": float(getattr(settings, "OBJECT_OVERLAY_MIN_RELEVANCE", 0.35)),
        "show_label": bool(getattr(settings, "OBJECT_OVERLAY_SHOW_LABEL", True)),
    }


def normalise_object_overlay_style(raw: object = None) -> dict[str, Any]:
    base = default_object_overlay_style()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for k, v in raw.items():
        if k not in base or v is None:
            continue
        try:
            if isinstance(base[k], bool):
                out[k] = bool(v) if not isinstance(v, str) else v.lower() in ("1", "true", "yes")
            elif isinstance(base[k], int):
                out[k] = int(v)
            elif isinstance(base[k], float):
                out[k] = float(v)
            else:
                out[k] = str(v)
        except (TypeError, ValueError):
            continue
    anim = str(out.get("animation") or "slide_right").lower()
    if anim not in {
        "slide_right", "slide_left", "slide_down", "slide_up", "fade", "pop",
    }:
        out["animation"] = "slide_right"
    pos = str(out.get("position") or "top_right").lower()
    if pos not in {
        "top_right", "top_left", "bottom_right", "bottom_left", "center_right", "center_left",
    }:
        out["position"] = "top_right"
    out["box_size_ratio"] = min(0.55, max(0.12, float(out["box_size_ratio"])))
    out["duration_sec"] = min(5.0, max(1.0, float(out["duration_sec"])))
    out["max_per_clip"] = min(10, max(0, int(out["max_per_clip"])))
    return out


def load_object_overlay_style(user_id: int | None = None) -> dict[str, Any]:
    """Load style from DB (user → global) then merge env defaults."""
    base = default_object_overlay_style()
    try:
        from src.presentation.routes.settings import get_object_overlay_config
        return normalise_object_overlay_style({**base, **get_object_overlay_config(user_id)})
    except Exception as exc:
        logger.debug("object_overlay: DB style load skip: %s", exc)
    return base


def bilingual_queries(entity: dict | str | None) -> tuple[str, str, str]:
    """(id_query, en_query, label) from AI entity dict — no domain lexicon."""
    if isinstance(entity, dict):
        word = str(entity.get("word") or entity.get("label") or "").strip()
        label = str(entity.get("label") or word or "Object").strip() or "Object"
        id_q = " ".join(str(entity.get("query_id") or "").split())
        en_q = " ".join(str(entity.get("query_en") or "").split())
        if not en_q:
            sq = entity.get("search_queries") or []
            en_q = " ".join(str(sq[0] if sq else word).split())
        if not id_q:
            id_q = en_q or f"{word} close up"
        if not en_q:
            en_q = id_q or f"{word} object close up"
        return id_q[:80], en_q[:80], label[:40]
    clean = re.sub(r"[^\w\-]+", "", str(entity or ""), flags=re.UNICODE)
    label = clean[:1].upper() + clean[1:] if clean else str(entity or "Object")
    id_q = f"{clean} close up" if clean else "object close up"
    en_q = f"{clean} object close up" if clean else "object close up"
    return id_q, en_q, label


def pick_object_mentions(
    words: list[dict] | None,
    objects: list[dict] | None = None,
    *,
    max_items: int = 3,
    clip_duration: float = 0.0,
    blocked_ranges: list[tuple[float, float]] | None = None,
    style: dict | None = None,
) -> list[dict[str, Any]]:
    """Pick timed mentions for image cards — prefers AI objects with query_id/en."""
    style = normalise_object_overlay_style(style)
    max_items = min(max_items, int(style.get("max_per_clip", 3)))
    if max_items <= 0:
        return []
    dur_card = float(style.get("duration_sec", 2.4))
    blocked = list(blocked_ranges or [])
    candidates: list[dict[str, Any]] = []

    def _add_entity(o: dict, source: str) -> None:
        id_q, en_q, label = bilingual_queries(o)
        word = str(o.get("word") or label).strip()
        if not word or len(word) < 2:
            return
        try:
            start = float(o.get("start", 0) or 0)
            end = float(o.get("end", start + 0.3) or start + 0.3)
        except (TypeError, ValueError):
            start, end = 0.0, 0.3
        if start < 1.5 and source != "ai":
            return
        if clip_duration > 0 and start >= clip_duration - 0.8:
            return
        # bare entity first — stock APIs rank better than "... close up" noise
        bare = re.sub(r"[^\w\-]+", " ", word, flags=re.UNICODE).strip()
        ordered: list[str] = []
        seen_q: set[str] = set()
        for q in (bare, en_q, id_q, *list(o.get("search_queries") or []), f"{bare} product"):
            q = " ".join(str(q or "").split())
            low = q.lower()
            if not q or low in seen_q:
                continue
            seen_q.add(low)
            ordered.append(q)
        ordered = [q for q in ordered if q.lower() == bare.lower()] + [
            q for q in ordered if q.lower() != bare.lower()
        ]
        src = str(o.get("source") or source or "").lower()
        rank = 0 if src in ("ai", "fallback") else 1
        stem = re.sub(r"[^\w\-]+", "", word, flags=re.UNICODE).lower()
        try:
            priority = int(o.get("priority", 5) or 5)
        except (TypeError, ValueError):
            priority = 5
        priority = max(1, min(10, priority))
        entity_type = str(o.get("entity_type") or o.get("type") or "object").lower()
        candidates.append({
            "word": word,
            "label": label,
            "start": round(float(start), 3),
            "end": round(float(end) if end > start else start + 0.3, 3),
            "query_id": id_q,
            "query_en": en_q,
            "search_queries": ordered[:8],
            "source": src or source,
            "rank": rank,
            "stem": stem,
            "priority": priority,
            "entity_type": entity_type,
        })

    for o in objects or []:
        if isinstance(o, dict):
            _add_entity(o, str(o.get("source") or "objects"))

    if any(c.get("rank") == 0 for c in candidates):
        candidates = [c for c in candidates if c.get("rank") == 0]
    elif not candidates:
        for w in words or []:
            text = str(w.get("word", w.get("text", "")) or "").strip()
            if not text:
                continue
            clean = re.sub(r"[^\w\-]+", "", text, flags=re.UNICODE)
            if len(clean) < 4:
                continue
            try:
                s = float(w.get("start", 0) or 0)
                e = float(w.get("end", s + 0.3) or s + 0.3)
            except (TypeError, ValueError):
                continue
            hit = bool(w.get("highlight")) or (clean[:1].isupper() and len(clean) >= 4) or len(clean) >= 6
            if not hit:
                continue
            _add_entity(
                {"word": clean, "start": s, "end": e, "label": clean[:1].upper() + clean[1:],
                 "query_id": f"{clean} close up", "query_en": clean,
                 "search_queries": [clean, f"{clean} close up"],
                 "source": "words"},
                "words",
            )

    def _family_hit(stem: str, taken: list[str]) -> bool:
        if not stem:
            return False
        for t in taken:
            if stem == t:
                return True
            if len(stem) >= 4 and len(t) >= 4 and (stem in t or t in stem):
                return True  # merokok↔rokok
        return False

    # Prefer AI + high priority (brand/object/action) + longer stems + time spread
    candidates.sort(
        key=lambda c: (
            c.get("rank", 1),
            -int(c.get("priority") or 5),
            -len(c.get("stem") or ""),
            c["start"],
        )
    )
    selected: list[dict[str, Any]] = []
    seen_stems: list[str] = []

    def _try_add(c: dict) -> bool:
        stem = str(c.get("stem") or "")
        if _family_hit(stem, seen_stems):
            return False
        at = float(c["start"])
        if at <= 0 and clip_duration > 4:
            at = 3.0 + len(selected) * 4.0
            if at >= clip_duration - 1.5:
                return False
            c["start"] = round(at, 3)
        card_end = at + dur_card
        if any(at < be and card_end > bs for bs, be in blocked):
            return False
        if any(abs(at - float(s["start"])) < 3.5 for s in selected):
            return False
        seen_stems.append(stem)
        c["duration"] = dur_card
        c["at_time"] = round(at, 3)
        selected.append(c)
        blocked.append((at, card_end))
        return True

    # Greedy max-distance: always pick farthest-from-selected among remaining
    # (keeps Aikos/Shisha late brands instead of only early Merokok)
    pool = list(candidates)
    while pool and len(selected) < max_items:
        if not selected:
            # start with earliest AI, else earliest overall
            pool.sort(key=lambda c: (c.get("rank", 1), c["start"]))
            c0 = pool.pop(0)
            if not _try_add(c0):
                continue
            continue
        best_i = -1
        best_dist = -1.0
        for i, c in enumerate(pool):
            stem = str(c.get("stem") or "")
            if _family_hit(stem, seen_stems):
                continue
            st = float(c["start"])
            dist = min(abs(st - float(s["start"])) for s in selected)
            # slight bonus for longer stems (brand-like)
            dist += 0.01 * len(stem)
            if dist > best_dist:
                best_dist = dist
                best_i = i
        if best_i < 0:
            break
        c = pool.pop(best_i)
        if not _try_add(c):
            continue

    selected.sort(key=lambda c: float(c["at_time"]))
    return selected


def score_image_relevance(
    *,
    word: str,
    label: str,
    query_id: str,
    query_en: str,
    photo_meta: dict,
    clip_hook: str = "",
    clip_reason: str = "",
    search_queries: list[str] | None = None,
) -> float:
    """Cheap local relevance 0..1.

    Core = word/label/query_en/matched search query (tight).
    Extra = long query_id / search_queries (half weight) — avoids diluting EN hits
    with many unused ID tokens from long prompts.
    Hook/reason = soft only (never sole reason to accept).
    """
    # Score ONLY photo evidence — never the search query itself (self-match inflate)
    blob = " ".join([
        str(photo_meta.get("alt") or ""),
        str(photo_meta.get("url") or ""),
        str(photo_meta.get("photographer") or ""),
        " ".join(str(t) for t in (photo_meta.get("tags") or [])),
    ]).lower()
    generic = {
        "the", "and", "for", "with", "close", "product", "object", "image",
        "photo", "stock", "up", "isolated", "showing", "menunjukkan", "tanggal",
        "satu", "first", "second", "desk",
    }

    def _toks(*parts: str) -> set[str]:
        out: set[str] = set()
        for part in parts:
            out.update(re.findall(r"[a-z0-9]{3,}", str(part or "").lower()))
        return out - generic

    # Core: spoken entity + EN query + the specific API query that returned this hit
    matched_q = str(photo_meta.get("query") or "")
    core = _toks(word, label, query_en, matched_q)
    extra = _toks(query_id, *list(search_queries or [])) - core
    soft = _toks(clip_hook, clip_reason) - core - extra
    if not core and not extra and not soft:
        return 0.15 if blob else 0.05
    c_hits = sum(1 for t in core if t in blob)
    e_hits = sum(1 for t in extra if t in blob)
    s_hits = sum(1 for t in soft if t in blob)
    # API already filtered by entity query (ID bare word) but alt often EN-only
    entity_stems = {t for t in _toks(word, label) if len(t) >= 4}
    mq = matched_q.lower()
    api_trusted = bool(mq) and any(t in mq for t in entity_stems)
    # No entity hit on alt AND query wasn't the spoken entity → weak (junk reuse)
    if (core or extra) and c_hits == 0 and e_hits == 0 and not api_trusted:
        return max(0.0, min(1.0, 0.08 + 0.04 * min(2, s_hits)))
    denom = max(2.0, min(4.0, float(len(core) or 1)))
    score = (c_hits / denom) + 0.12 * min(3, e_hits) + 0.04 * min(2, s_hits)
    if api_trusted and c_hits == 0:
        # Cross-lang floor: stock hit for entity query, alt in another language.
        # Must clear default OBJECT_OVERLAY_MIN_RELEVANCE (0.35).
        score = max(score, 0.38)
    for bonus in ("hand", "pack", "device", "macro", "cigarette", "smoke",
                  "calendar", "hookah", "vape", "tobacco", "ash"):
        if bonus in blob:
            score += 0.05
    for bad in ("landscape", "skyline", "sunset beach", "mountain", "crowd people",
                "dandelion", "pebble", "makeup", "yogurt"):
        if bad in blob:
            score -= 0.2
    return max(0.0, min(1.0, score))


def _photo_queries(
    query_id: str,
    query_en: str,
    search_queries: list[str] | None = None,
    word: str = "",
    label: str = "",
) -> list[str]:
    """Deduped multi-query list — EN first, then ID, then extras."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(q: str) -> None:
        q = " ".join(str(q or "").split())[:80]
        low = q.lower()
        if not q or low in seen:
            return
        seen.add(low)
        out.append(q)

    for q in (word, query_en, query_id, *(search_queries or []), label):
        _add(q)
    return out[:6]


async def search_stock_photo(
    query_id: str,
    query_en: str,
    *,
    download_dir: str,
    min_relevance: float = 0.35,
    word: str = "",
    label: str = "",
    clip_hook: str = "",
    clip_reason: str = "",
    search_queries: list[str] | None = None,
    exclude_ids: set[str] | None = None,
) -> Optional[dict[str, Any]]:
    """Search Pexels/Pixabay multi-query; skip already-used photo ids."""
    os.makedirs(download_dir, exist_ok=True)
    candidates: list[dict] = []
    seen_ids: set[str] = set()
    banned = {str(x) for x in (exclude_ids or set()) if x}
    queries = _photo_queries(query_id, query_en, search_queries, word, label)
    if not queries:
        return None

    async with httpx.AsyncClient(timeout=float(getattr(settings, "ASSET_FETCH_TIMEOUT", 20))) as client:
        pexels_key = getattr(settings, "PEXELS_API_KEY", "") or ""
        if pexels_key:
            for q in queries:
                try:
                    r = await client.get(
                        "https://api.pexels.com/v1/search",
                        headers={"Authorization": pexels_key},
                        params={"query": q, "per_page": 8, "orientation": "square"},
                    )
                    if r.status_code != 200:
                        continue
                    for p in (r.json().get("photos") or [])[:8]:
                        pid = str(p.get("id") or "")
                        if pid and (pid in banned or pid in seen_ids):
                            continue
                        src = (p.get("src") or {})
                        url = src.get("medium") or src.get("large") or src.get("original")
                        if not url:
                            continue
                        if pid:
                            seen_ids.add(pid)
                        meta = {
                            "alt": p.get("alt") or "",
                            "url": url,
                            "photographer": p.get("photographer") or "",
                            "platform": "pexels",
                            "id": pid,
                            "query": q,
                        }
                        meta["relevance"] = score_image_relevance(
                            word=word, label=label, query_id=query_id, query_en=query_en,
                            photo_meta=meta, clip_hook=clip_hook, clip_reason=clip_reason,
                            search_queries=search_queries,
                        )
                        candidates.append(meta)
                except Exception as exc:
                    logger.debug("object_overlay: pexels fail q=%s: %s", q, exc)

        pix_key = getattr(settings, "PIXABAY_API_KEY", "") or ""
        if pix_key:
            for q in queries:
                try:
                    r = await client.get(
                        "https://pixabay.com/api/",
                        params={
                            "key": pix_key,
                            "q": q,
                            "image_type": "photo",
                            "per_page": 8,
                            "safesearch": "true",
                        },
                    )
                    if r.status_code != 200:
                        continue
                    for h in (r.json().get("hits") or [])[:8]:
                        pid = str(h.get("id") or "")
                        if pid and (pid in banned or pid in seen_ids):
                            continue
                        url = h.get("webformatURL") or h.get("largeImageURL")
                        if not url:
                            continue
                        if pid:
                            seen_ids.add(pid)
                        tags = str(h.get("tags") or "").split(", ")
                        meta = {
                            "alt": h.get("tags") or "",
                            "url": url,
                            "photographer": h.get("user") or "",
                            "platform": "pixabay",
                            "id": pid,
                            "tags": tags,
                            "query": q,
                        }
                        meta["relevance"] = score_image_relevance(
                            word=word, label=label, query_id=query_id, query_en=query_en,
                            photo_meta=meta, clip_hook=clip_hook, clip_reason=clip_reason,
                            search_queries=search_queries,
                        )
                        candidates.append(meta)
                except Exception as exc:
                    logger.debug("object_overlay: pixabay fail q=%s: %s", q, exc)

    if not candidates:
        return None
    candidates.sort(key=lambda c: float(c.get("relevance") or 0), reverse=True)
    best = candidates[0]
    rel = float(best.get("relevance") or 0)
    if rel < min_relevance:
        logger.info(
            "object_overlay: best relevance %.2f < min %.2f for '%s' q=%s",
            rel, min_relevance, label or word, best.get("query"),
        )
        # Weak match without entity token → skip (stops same junk image reuse)
        if rel < 0.22:
            return None

    url = best["url"]
    ext = ".jpg"
    if ".png" in url.lower():
        ext = ".png"
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", (label or word or "obj"))[:40]
    local = os.path.join(download_dir, f"{safe}_{best.get('id') or 'x'}{ext}")
    if not os.path.exists(local):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(url)
                if r.status_code != 200:
                    return None
                with open(local, "wb") as f:
                    f.write(r.content)
        except Exception as exc:
            logger.warning("object_overlay: download fail: %s", exc)
            return None
    best["local_path"] = local
    return best


def _parse_rgb(s: str, default: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int, int]:
    try:
        parts = [int(x.strip()) for x in str(s).split(",")]
        if len(parts) >= 3:
            return max(0, min(255, parts[0])), max(0, min(255, parts[1])), max(0, min(255, parts[2]))
    except (TypeError, ValueError):
        pass
    return default


def build_overlay_card(
    image_path: str,
    label: str,
    *,
    box_px: int = 200,
    corner_radius: int = 18,
    text_color: str = "255,255,255",
    bg_color: str = "20,20,24",
    border_color: str = "255,255,255",
    font_scale: float = 0.55,
    show_label: bool = True,
) -> Optional[Any]:
    """Build BGRA glassmorphism card: rounded thumbnail + pill badge + drop shadow."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        return None
    box = max(64, int(box_px))
    radius = max(0, min(corner_radius, box // 3))
    # square cover crop
    h, w = img.shape[:2]
    side = min(h, w)
    y0 = (h - side) // 2
    x0 = (w - side) // 2
    crop = img[y0:y0 + side, x0:x0 + side]
    thumb = cv2.resize(crop, (box, box), interpolation=cv2.INTER_AREA)

    label_h = int(box * 0.26) if show_label and label else 0
    shadow_margin = 12
    card_h = box + label_h + shadow_margin
    card_w = box + shadow_margin
    bg = _parse_rgb(bg_color, (15, 23, 42))  # modern dark slate
    tc = _parse_rgb(text_color, (255, 255, 255))
    bc = _parse_rgb(border_color, (56, 189, 248))  # cyan/emerald neon accent

    card = np.zeros((card_h, card_w, 4), dtype=np.uint8)

    # ── 1. Soft Blurred Drop Shadow ──
    shadow_mask = np.zeros((card_h, card_w), dtype=np.uint8)
    sx0, sy0 = shadow_margin // 2, shadow_margin // 2
    cv2.rectangle(
        shadow_mask,
        (sx0 + 2, sy0 + 4),
        (sx0 + box - 2, sy0 + box + label_h - 2),
        160,
        -1,
    )
    shadow_blur = cv2.GaussianBlur(shadow_mask, (15, 15), 0)
    card[:, :, 3] = shadow_blur

    # ── 2. Rounded Thumbnail Mask ──
    mask = np.zeros((box, box), dtype=np.uint8)
    if radius > 0:
        cv2.rectangle(mask, (radius, 0), (box - radius - 1, box - 1), 255, -1)
        cv2.rectangle(mask, (0, radius), (box - 1, box - radius - 1), 255, -1)
        cv2.circle(mask, (radius, radius), radius, 255, -1)
        cv2.circle(mask, (box - radius - 1, radius), radius, 255, -1)
        cv2.circle(mask, (radius, box - radius - 1), radius, 255, -1)
        cv2.circle(mask, (box - radius - 1, box - radius - 1), radius, 255, -1)
    else:
        cv2.rectangle(mask, (0, 0), (box - 1, box - 1), 255, -1)

    # Copy image with rounded mask
    for c in range(3):
        card[sy0:sy0 + box, sx0:sx0 + box, c] = thumb[:, :, c]
    card[sy0:sy0 + box, sx0:sx0 + box, 3] = np.maximum(
        card[sy0:sy0 + box, sx0:sx0 + box, 3], mask
    )

    # ── 3. Glowing Border Ring ──
    border = np.zeros((box, box), dtype=np.uint8)
    cv2.rectangle(border, (1, 1), (box - 2, box - 2), 255, 2)
    edge = cv2.bitwise_and(border, mask)
    for c, val in enumerate(bc):
        img_region = card[sy0:sy0 + box, sx0:sx0 + box, c]
        card[sy0:sy0 + box, sx0:sx0 + box, c] = np.where(edge > 0, val, img_region)

    # ── 4. Glassmorphism Pill Label ──
    if label_h > 0:
        lbl_y0 = sy0 + box - 4
        lbl_y1 = lbl_y0 + label_h + 4
        lbl_x0 = sx0 + 4
        lbl_x1 = sx0 + box - 4

        # Pill background
        pill_mask = np.zeros((card_h, card_w), dtype=np.uint8)
        cv2.rectangle(pill_mask, (lbl_x0, lbl_y0), (lbl_x1, lbl_y1), 235, -1)

        for c, val in enumerate(bg):
            card[lbl_y0:lbl_y1, lbl_x0:lbl_x1, c] = val
        card[:, :, 3] = np.maximum(card[:, :, 3], pill_mask)

        # Border for pill
        bgr = np.ascontiguousarray(card[:, :, :3])
        cv2.rectangle(bgr, (lbl_x0, lbl_y0), (lbl_x1, lbl_y1), bc, 1)

        # High-contrast label text with badge indicator
        clean_text = str(label).strip()[:16].upper()
        badge_text = f"{clean_text}"
        font = cv2.FONT_HERSHEY_DUPLEX
        scale = max(0.32, float(font_scale) * (box / 210.0))
        thickness = 1
        (tw, th), _ = cv2.getTextSize(badge_text, font, scale, thickness)
        tx = max(lbl_x0 + 6, (lbl_x0 + lbl_x1 - tw) // 2)
        ty = lbl_y0 + (label_h + th) // 2 + 1

        # Drop shadow for text
        cv2.putText(bgr, badge_text, (tx + 1, ty + 1), font, scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
        cv2.putText(bgr, badge_text, (tx, ty), font, scale, tc, thickness, cv2.LINE_AA)
        card[:, :, :3] = bgr

    return card


def _anchor_xy(
    frame_w: int,
    frame_h: int,
    card_w: int,
    card_h: int,
    position: str,
    margin_ratio: float,
) -> tuple[int, int]:
    m = int(min(frame_w, frame_h) * float(margin_ratio))
    pos = (position or "top_right").lower()
    if pos == "top_left":
        return m, m
    if pos == "bottom_left":
        # Keep above standard subtitle bottom boundary (min 260px)
        return m, max(m, frame_h - card_h - max(m, 260))
    if pos == "bottom_right":
        return frame_w - card_w - m, max(m, frame_h - card_h - max(m, 260))
    if pos == "center_left":
        return m, max(m, (frame_h - card_h) // 2)
    if pos == "center_right":
        return frame_w - card_w - m, max(m, (frame_h - card_h) // 2)
    # top_right default (safe from subtitle collisions)
    return frame_w - card_w - m, m


def _anim_offset(
    t_local: float,
    duration: float,
    animation: str,
    card_w: int,
    card_h: int,
    with_scale: bool = False,
) -> tuple[int, int, float] | tuple[int, int, float, float]:
    """Return (dx, dy, alpha_mul) or (dx, dy, alpha_mul, scale_mul) if with_scale=True."""
    anim = (animation or "slide_right").lower()
    fade_in = 0.25
    fade_out = 0.25
    alpha = 1.0
    if t_local < fade_in:
        alpha = t_local / fade_in
    elif t_local > duration - fade_out:
        alpha = max(0.0, (duration - t_local) / fade_out)

    progress_in = min(1.0, t_local / fade_in) if fade_in > 0 else 1.0
    ease = 1.0 - (1.0 - progress_in) ** 2  # ease-out

    # Ken Burns Micro-Zoom: smooth 1.00x -> 1.06x over life of card
    t_norm = max(0.0, min(1.0, t_local / max(0.1, duration)))
    scale_mul = 1.0 + 0.06 * t_norm

    dx = dy = 0
    if anim == "slide_right":
        dx = int((1.0 - ease) * (card_w + 30))
    elif anim == "slide_left":
        dx = int(-(1.0 - ease) * (card_w + 30))
    elif anim == "slide_down":
        dy = int(-(1.0 - ease) * (card_h + 30))
    elif anim == "slide_up":
        dy = int((1.0 - ease) * (card_h + 30))
    elif anim == "pop":
        alpha *= 0.4 + 0.6 * ease
        scale_mul = (0.7 + 0.3 * ease) * scale_mul

    alpha_clamped = max(0.0, min(1.0, alpha))
    if with_scale:
        return dx, dy, alpha_clamped, scale_mul
    return dx, dy, alpha_clamped


def _blit_bgra(frame, card, x: int, y: int, opacity: float = 1.0):
    import numpy as np
    fh, fw = frame.shape[:2]
    ch, cw = card.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(fw, x + cw), min(fh, y + ch)
    if x0 >= x1 or y0 >= y1:
        return
    cx0, cy0 = x0 - x, y0 - y
    cx1, cy1 = cx0 + (x1 - x0), cy0 + (y1 - y0)
    roi = frame[y0:y1, x0:x1]
    patch = card[cy0:cy1, cx0:cx1]
    alpha = (patch[:, :, 3:4].astype(np.float32) / 255.0) * float(opacity)
    if patch.shape[2] == 4:
        rgb = patch[:, :, :3].astype(np.float32)
    else:
        rgb = patch.astype(np.float32)
    base = roi.astype(np.float32)
    blended = rgb * alpha + base * (1.0 - alpha)
    frame[y0:y1, x0:x1] = blended.astype(roi.dtype)


@dataclass
class ObjectOverlayEvent:
    at_time: float
    duration: float
    word: str
    label: str
    query_id: str
    query_en: str
    image_path: str = ""
    relevance: float = 0.0
    platform: str = ""
    style: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "at_time": self.at_time,
            "duration": self.duration,
            "word": self.word,
            "label": self.label,
            "query_id": self.query_id,
            "query_en": self.query_en,
            "image_path": self.image_path,
            "relevance": self.relevance,
            "platform": self.platform,
            "style": {
                k: self.style.get(k)
                for k in ("position", "animation", "box_size_ratio", "corner_radius")
                if self.style
            },
        }


class ObjectImageOverlayRenderer:
    """Bake object image+text cards onto a clip video."""

    async def resolve_events(
        self,
        mentions: list[dict],
        *,
        output_dir: str,
        clip_hook: str = "",
        clip_reason: str = "",
        style: dict | None = None,
    ) -> list[ObjectOverlayEvent]:
        style = normalise_object_overlay_style(style)
        if not style.get("enabled", True):
            return []
        img_dir = os.path.join(output_dir, "object_overlay")
        os.makedirs(img_dir, exist_ok=True)
        events: list[ObjectOverlayEvent] = []
        used_ids: set[str] = set()
        for m in mentions:
            photo = await search_stock_photo(
                m.get("query_id", ""),
                m.get("query_en", ""),
                download_dir=img_dir,
                min_relevance=float(style.get("min_relevance", 0.35)),
                word=str(m.get("word") or ""),
                label=str(m.get("label") or ""),
                clip_hook=clip_hook,
                clip_reason=clip_reason,
                search_queries=list(m.get("search_queries") or []),
                exclude_ids=used_ids,
            )
            if not photo or not photo.get("local_path"):
                logger.info("object_overlay: no photo for %s", m.get("label"))
                continue
            pid = str(photo.get("id") or "")
            if pid:
                used_ids.add(pid)
            events.append(ObjectOverlayEvent(
                at_time=float(m.get("at_time", m.get("start", 0))),
                duration=float(m.get("duration", style.get("duration_sec", 2.4))),
                word=str(m.get("word") or ""),
                label=str(m.get("label") or m.get("word") or ""),
                query_id=str(m.get("query_id") or ""),
                query_en=str(m.get("query_en") or ""),
                image_path=photo["local_path"],
                relevance=float(photo.get("relevance") or 0),
                platform=str(photo.get("platform") or ""),
                style=style,
            ))
        return events

    async def apply_to_clip(
        self,
        video_path: str,
        events: list[ObjectOverlayEvent],
        output_path: str,
        style: dict | None = None,
    ) -> Optional[str]:
        if not events or not os.path.exists(video_path):
            return None
        style = normalise_object_overlay_style(style or (events[0].style if events else None))
        return await asyncio.to_thread(
            self._render_sync, video_path, events, output_path, style
        )

    def _render_sync(
        self,
        video_path: str,
        events: list[ObjectOverlayEvent],
        output_path: str,
        style: dict,
    ) -> Optional[str]:
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.warning("object_overlay: cannot open %s", video_path)
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1080)
        fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1920)
        box_px = int(min(fw, fh) * float(style.get("box_size_ratio", 0.28)))
        cards: list[tuple[ObjectOverlayEvent, Any]] = []
        for ev in events:
            card = build_overlay_card(
                ev.image_path,
                ev.label if style.get("show_label", True) else "",
                box_px=box_px,
                corner_radius=int(style.get("corner_radius", 18)),
                text_color=str(style.get("text_color", "255,255,255")),
                bg_color=str(style.get("bg_color", "20,20,24")),
                border_color=str(style.get("border_color", "255,255,255")),
                font_scale=float(style.get("font_scale", 0.55)),
                show_label=bool(style.get("show_label", True)),
            )
            if card is not None:
                cards.append((ev, card))
        if not cards:
            cap.release()
            return None

        tmp_video = output_path + ".objov.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(tmp_video, fourcc, fps, (fw, fh))
        if not writer.isOpened():
            cap.release()
            logger.warning("object_overlay: writer fail")
            return None

        frame_i = 0
        opacity_base = float(style.get("opacity", 0.95))
        position = str(style.get("position", "top_right"))
        animation = str(style.get("animation", "slide_right"))
        margin = float(style.get("margin_ratio", 0.04))

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = frame_i / fps
            for ev, card in cards:
                t0 = float(ev.at_time)
                dur = float(ev.duration)
                if t < t0 or t > t0 + dur:
                    continue
                ch, cw = card.shape[:2]
                ax, ay = _anchor_xy(fw, fh, cw, ch, position, margin)
                dx, dy, amul, smul = _anim_offset(t - t0, dur, animation, cw, ch, with_scale=True)

                # Ken Burns Micro-Zoom: smooth scale expansion
                if abs(smul - 1.0) > 0.005:
                    new_w = max(16, int(round(cw * smul)))
                    new_h = max(16, int(round(ch * smul)))
                    zoomed_card = cv2.resize(card, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                    # Keep anchor centered on growth
                    cx_offset = (new_w - cw) // 2
                    cy_offset = (new_h - ch) // 2
                    _blit_bgra(frame, zoomed_card, ax + dx - cx_offset, ay + dy - cy_offset, opacity=opacity_base * amul)
                else:
                    _blit_bgra(frame, card, ax + dx, ay + dy, opacity=opacity_base * amul)
            writer.write(frame)
            frame_i += 1

        cap.release()
        writer.release()

        # mux original audio
        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", tmp_video,
                "-i", video_path,
                "-map", "0:v:0", "-map", "1:a:0?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-shortest",
                output_path,
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                try:
                    os.remove(tmp_video)
                except OSError:
                    pass
                return output_path
        except Exception as exc:
            logger.warning("object_overlay: mux fail: %s", exc)
        # fallback: move raw
        try:
            shutil.move(tmp_video, output_path)
            return output_path
        except OSError:
            return None


def load_clip_analisa(output_dir: str, rank: int) -> dict:
    """Read json_analisa/clip_{n}.json if present."""
    import json
    path = os.path.join(output_dir, "json_analisa", f"clip_{rank}.json")
    if not os.path.exists(path):
        # also try clip_01 style
        path2 = os.path.join(output_dir, "json_analisa", f"clip_{rank:02d}.json")
        path = path2 if os.path.exists(path2) else path
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def words_from_analisa(analisa: dict) -> list[dict]:
    """Word timings from clip analisa JSON (fallback when live words map missing)."""
    body: dict = {}
    clips = analisa.get("clips") if isinstance(analisa, dict) else None
    if isinstance(clips, list) and clips and isinstance(clips[0], dict):
        body = clips[0]
    elif isinstance(analisa, dict):
        body = analisa
    out: list[dict] = []
    for w in body.get("words") or []:
        if not isinstance(w, dict):
            continue
        text = str(w.get("word") or w.get("text") or "").strip()
        if not text:
            continue
        try:
            s = float(w.get("start", w.get("s", 0)) or 0)
            e = float(w.get("end", w.get("e", s + 0.2)) or s + 0.2)
        except (TypeError, ValueError):
            continue
        out.append({
            "word": text,
            "start": s,
            "end": e,
            "highlight": bool(w.get("highlight")),
        })
    return out


def objects_from_analisa(analisa: dict) -> list[dict]:
    body = {}
    clips = analisa.get("clips") if isinstance(analisa, dict) else None
    if isinstance(clips, list) and clips:
        body = clips[0] if isinstance(clips[0], dict) else {}
    elif isinstance(analisa, dict):
        body = analisa
    out: list[dict] = []
    seen: set[str] = set()

    ve = list(body.get("visual_entities") or [])
    if ve:
        for o in ve:
            if not isinstance(o, dict):
                continue
            word = str(o.get("word") or o.get("label") or "").strip()
            if not word:
                continue
            low = word.lower()
            if low in seen:
                continue
            seen.add(low)
            out.append(o)
        return out

    # No VE: keep non-heuristic objects only
    for o in body.get("objects") or []:
        if not isinstance(o, dict):
            continue
        src = str(o.get("source") or "").lower()
        if src in ("heuristic", "footage_kw", "words"):
            continue
        word = str(o.get("word") or o.get("label") or "").strip()
        if not word:
            continue
        low = word.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(o)
    return out


def footage_keywords_from_analisa(analisa: dict) -> list[str]:
    body = {}
    clips = analisa.get("clips") if isinstance(analisa, dict) else None
    if isinstance(clips, list) and clips:
        body = clips[0] if isinstance(clips[0], dict) else {}
    elif isinstance(analisa, dict):
        body = analisa
    out: list[str] = []
    seen: set[str] = set()

    def _add(s: str) -> None:
        s = " ".join(str(s or "").split())
        low = s.lower()
        if s and low not in seen:
            seen.add(low)
            out.append(s)

    for key in ("visual_entities", "objects"):
        for o in body.get(key) or []:
            if not isinstance(o, dict):
                continue
            src = str(o.get("source") or "").lower()
            if src in ("heuristic", "footage_kw", "words"):
                continue
            for q in (
                o.get("query_en"),
                o.get("query_id"),
                *(o.get("search_queries") or []),
            ):
                _add(str(q or ""))
    for s in body.get("footage_keywords") or []:
        raw = " ".join(str(s or "").split())
        if " " in raw or len(raw) >= 8:
            _add(raw)
    for b in body.get("broll_suggestions") or []:
        if isinstance(b, dict):
            _add(str(b.get("keyword") or ""))
    return out[:24]
