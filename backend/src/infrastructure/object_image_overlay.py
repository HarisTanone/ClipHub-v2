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
    out["max_per_clip"] = min(6, max(0, int(out["max_per_clip"])))
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
            en_q = id_q or f"{word} product close up"
        return id_q[:80], en_q[:80], label[:40]
    clean = re.sub(r"[^\w\-]+", "", str(entity or ""), flags=re.UNICODE)
    label = clean[:1].upper() + clean[1:] if clean else str(entity or "Object")
    id_q = f"{clean} close up" if clean else "object close up"
    en_q = f"{clean} product close up" if clean else "product close up"
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
        sq = list(o.get("search_queries") or [])
        for q in (en_q, id_q):
            if q and q.lower() not in {x.lower() for x in sq}:
                sq.append(q)
        # Prefer AI-sourced rows
        rank = 0 if (o.get("source") == "ai" or o.get("query_en")) else 1
        candidates.append({
            "word": word,
            "label": label,
            "start": round(float(start), 3),
            "end": round(float(end) if end > start else start + 0.3, 3),
            "query_id": id_q,
            "query_en": en_q,
            "search_queries": sq[:6],
            "source": source,
            "rank": rank,
        })

    for o in objects or []:
        if isinstance(o, dict):
            _add_entity(o, str(o.get("source") or "objects"))

    # Soft fallback from highlighted/long words only when no AI objects
    if not candidates:
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
                 "query_id": f"{clean} close up", "query_en": f"{clean} product close up",
                 "source": "words"},
                "words",
            )

    candidates.sort(key=lambda c: (c.get("rank", 1), c["start"]))
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in candidates:
        key = c["label"].lower()
        if key in seen:
            continue
        at = float(c["start"])
        if at <= 0 and clip_duration > 4:
            at = 3.0 + len(selected) * 4.0
            if at >= clip_duration - 1.5:
                continue
            c["start"] = round(at, 3)
        card_end = at + dur_card
        if any(at < be and card_end > bs for bs, be in blocked):
            continue
        if any(abs(at - float(s["start"])) < 3.5 for s in selected):
            continue
        seen.add(key)
        c["duration"] = dur_card
        c["at_time"] = round(at, 3)
        selected.append(c)
        blocked.append((at, card_end))
        if len(selected) >= max_items:
            break
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
) -> float:
    """Cheap local relevance 0..1 (no LLM). Token overlap + alt/photographer noise filter."""
    blob = " ".join([
        str(photo_meta.get("alt") or ""),
        str(photo_meta.get("url") or ""),
        str(photo_meta.get("photographer") or ""),
        " ".join(str(t) for t in (photo_meta.get("tags") or [])),
    ]).lower()
    tokens = set()
    for part in (word, label, query_id, query_en, clip_hook, clip_reason):
        tokens.update(re.findall(r"[a-z0-9]{3,}", str(part or "").lower()))
    # Drop ultra-generic
    tokens -= {"the", "and", "for", "with", "close", "product", "image", "photo", "stock"}
    if not tokens:
        return 0.4 if blob else 0.2
    hits = sum(1 for t in tokens if t in blob)
    score = hits / max(3.0, min(8.0, float(len(tokens))))
    # Prefer portrait-ish / product framing keywords in alt
    for bonus in ("close", "product", "hand", "pack", "device", "macro"):
        if bonus in blob:
            score += 0.05
    # Penalize scenic noise
    for bad in ("landscape", "skyline", "sunset beach", "mountain", "crowd people"):
        if bad in blob:
            score -= 0.15
    return max(0.0, min(1.0, score))


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
) -> Optional[dict[str, Any]]:
    """Search Pexels then Pixabay photos with ID+EN queries; pick best relevance."""
    os.makedirs(download_dir, exist_ok=True)
    candidates: list[dict] = []

    async with httpx.AsyncClient(timeout=float(getattr(settings, "ASSET_FETCH_TIMEOUT", 20))) as client:
        # Pexels photos
        pexels_key = getattr(settings, "PEXELS_API_KEY", "") or ""
        if pexels_key:
            for q in (query_en, query_id):
                if not q:
                    continue
                try:
                    r = await client.get(
                        "https://api.pexels.com/v1/search",
                        headers={"Authorization": pexels_key},
                        params={"query": q, "per_page": 5, "orientation": "square"},
                    )
                    if r.status_code == 200:
                        for p in (r.json().get("photos") or [])[:5]:
                            src = (p.get("src") or {})
                            url = src.get("medium") or src.get("large") or src.get("original")
                            if not url:
                                continue
                            meta = {
                                "alt": p.get("alt") or "",
                                "url": url,
                                "photographer": p.get("photographer") or "",
                                "platform": "pexels",
                                "id": str(p.get("id") or ""),
                                "query": q,
                            }
                            meta["relevance"] = score_image_relevance(
                                word=word, label=label, query_id=query_id, query_en=query_en,
                                photo_meta=meta, clip_hook=clip_hook, clip_reason=clip_reason,
                            )
                            candidates.append(meta)
                except Exception as exc:
                    logger.debug("object_overlay: pexels fail q=%s: %s", q, exc)

        # Pixabay images
        pix_key = getattr(settings, "PIXABAY_API_KEY", "") or ""
        if pix_key:
            for q in (query_en, query_id):
                if not q:
                    continue
                try:
                    r = await client.get(
                        "https://pixabay.com/api/",
                        params={
                            "key": pix_key,
                            "q": q,
                            "image_type": "photo",
                            "per_page": 5,
                            "safesearch": "true",
                        },
                    )
                    if r.status_code == 200:
                        for h in (r.json().get("hits") or [])[:5]:
                            url = h.get("webformatURL") or h.get("largeImageURL")
                            if not url:
                                continue
                            tags = str(h.get("tags") or "").split(", ")
                            meta = {
                                "alt": h.get("tags") or "",
                                "url": url,
                                "photographer": h.get("user") or "",
                                "platform": "pixabay",
                                "id": str(h.get("id") or ""),
                                "tags": tags,
                                "query": q,
                            }
                            meta["relevance"] = score_image_relevance(
                                word=word, label=label, query_id=query_id, query_en=query_en,
                                photo_meta=meta, clip_hook=clip_hook, clip_reason=clip_reason,
                            )
                            candidates.append(meta)
                except Exception as exc:
                    logger.debug("object_overlay: pixabay fail q=%s: %s", q, exc)

    if not candidates:
        return None
    candidates.sort(key=lambda c: float(c.get("relevance") or 0), reverse=True)
    best = candidates[0]
    if float(best.get("relevance") or 0) < min_relevance:
        logger.info(
            "object_overlay: best relevance %.2f < min %.2f for '%s'",
            best.get("relevance"), min_relevance, label or word,
        )
        # still take best if anything — better than empty for known lexicon
        if float(best.get("relevance") or 0) < 0.15:
            return None

    # Download
    url = best["url"]
    ext = ".jpg"
    if ".png" in url.lower():
        ext = ".png"
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", (label or word or "obj"))[:40]
    local = os.path.join(download_dir, f"{safe}_{best.get('id') or 'x'}{ext}")
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
    """Build BGRA card: rounded image + optional text label below. Returns numpy array."""
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

    label_h = int(box * 0.28) if show_label and label else 0
    card_h = box + label_h
    card_w = box
    bg = _parse_rgb(bg_color, (20, 20, 24))
    tc = _parse_rgb(text_color, (255, 255, 255))
    bc = _parse_rgb(border_color, (255, 255, 255))

    card = np.zeros((card_h, card_w, 4), dtype=np.uint8)
    # rounded mask for image area
    mask = np.zeros((box, box), dtype=np.uint8)
    cv2.rectangle(mask, (0, 0), (box - 1, box - 1), 255, -1)
    if radius > 0:
        mask = np.zeros((box, box), dtype=np.uint8)
        cv2.rectangle(mask, (radius, 0), (box - radius - 1, box - 1), 255, -1)
        cv2.rectangle(mask, (0, radius), (box - 1, box - radius - 1), 255, -1)
        cv2.circle(mask, (radius, radius), radius, 255, -1)
        cv2.circle(mask, (box - radius - 1, radius), radius, 255, -1)
        cv2.circle(mask, (radius, box - radius - 1), radius, 255, -1)
        cv2.circle(mask, (box - radius - 1, box - radius - 1), radius, 255, -1)

    for c in range(3):
        card[:box, :box, c] = thumb[:, :, c]
    card[:box, :box, 3] = mask

    # border ring
    if radius >= 0:
        border = np.zeros((box, box), dtype=np.uint8)
        cv2.rectangle(border, (1, 1), (box - 2, box - 2), 255, 2)
        # only on opaque
        edge = cv2.bitwise_and(border, mask)
        for c, val in enumerate(bc):
            card[:box, :box, c] = np.where(edge > 0, val, card[:box, :box, c])

    if label_h > 0:
        # label strip with rounded bottom feel
        card[box:, :, 0] = bg[0]
        card[box:, :, 1] = bg[1]
        card[box:, :, 2] = bg[2]
        card[box:, :, 3] = 230
        text = str(label)[:18]
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = max(0.35, float(font_scale) * (box / 200.0))
        thickness = max(1, int(round(scale * 2)))
        (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
        tx = max(4, (card_w - tw) // 2)
        ty = box + (label_h + th) // 2 - 2
        # draw on BGR then copy alpha
        bgr = card[:, :, :3].copy()
        cv2.putText(bgr, text, (tx, ty), font, scale, tc, thickness, cv2.LINE_AA)
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
        return m, frame_h - card_h - m
    if pos == "bottom_right":
        return frame_w - card_w - m, frame_h - card_h - m
    if pos == "center_left":
        return m, max(m, (frame_h - card_h) // 2)
    if pos == "center_right":
        return frame_w - card_w - m, max(m, (frame_h - card_h) // 2)
    # top_right default
    return frame_w - card_w - m, m


def _anim_offset(
    t_local: float,
    duration: float,
    animation: str,
    card_w: int,
    card_h: int,
) -> tuple[int, int, float]:
    """Return (dx, dy, alpha_mul) for entrance/exit."""
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
    dx = dy = 0
    if anim == "slide_right":
        dx = int((1.0 - ease) * (card_w + 20))
    elif anim == "slide_left":
        dx = int(-(1.0 - ease) * (card_w + 20))
    elif anim == "slide_down":
        dy = int(-(1.0 - ease) * (card_h + 20))
    elif anim == "slide_up":
        dy = int((1.0 - ease) * (card_h + 20))
    elif anim == "pop":
        # scale simulated via alpha only at start
        alpha *= 0.5 + 0.5 * ease
    # fade: only alpha
    return dx, dy, max(0.0, min(1.0, alpha))


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
            )
            if not photo or not photo.get("local_path"):
                logger.info("object_overlay: no photo for %s", m.get("label"))
                continue
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
                dx, dy, amul = _anim_offset(t - t0, dur, animation, cw, ch)
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


def objects_from_analisa(analisa: dict) -> list[dict]:
    body = {}
    clips = analisa.get("clips") if isinstance(analisa, dict) else None
    if isinstance(clips, list) and clips:
        body = clips[0] if isinstance(clips[0], dict) else {}
    elif isinstance(analisa, dict):
        body = analisa
    out: list[dict] = []
    seen: set[str] = set()
    # Prefer AI visual_entities, then objects (both carry query_id/en when AI-backed)
    for key in ("visual_entities", "objects"):
        for o in body.get(key) or []:
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

    for s in body.get("footage_keywords") or []:
        _add(str(s))
    for s in body.get("highlight_keywords") or []:
        _add(str(s))
    for key in ("visual_entities", "objects"):
        for o in body.get(key) or []:
            if not isinstance(o, dict):
                continue
            for q in (
                o.get("query_en"),
                o.get("query_id"),
                o.get("word"),
                *(o.get("search_queries") or []),
            ):
                _add(str(q or ""))
    for b in body.get("broll_suggestions") or []:
        if isinstance(b, dict):
            _add(str(b.get("keyword") or ""))
    return out[:24]
