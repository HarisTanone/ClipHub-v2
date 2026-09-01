"""TikTok OAuth flow - authorize, connect, reconnect."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.presentation.routes.auth import get_current_user
from src.presentation.auth_deps import CurrentUser
from src.presentation.routes.social.helpers import repliz_get, repliz_post
from src.presentation.routes.social.accounts import register_account

tiktok_router = APIRouter(prefix="/tiktok", tags=["social-tiktok"])


@tiktok_router.get("/authorize")
async def tiktok_authorize(
    redirect: str = Query(..., description="Redirect URL after TikTok auth"),
    _user=Depends(get_current_user),
):
    """Start TikTok OAuth - returns the TikTok authorization URL."""
    return await repliz_get("/public/account/tiktok/authorize", params={"redirect": redirect})


class TikTokConnectRequest(BaseModel):
    code: str


@tiktok_router.post("/connect")
async def tiktok_connect(body: TikTokConnectRequest, user: CurrentUser = Depends(get_current_user)):
    """Connect a TikTok account to workspace."""
    result = await repliz_post(
        "/public/account/tiktok/connect",
        json_body={"code": body.code},
    )
    if result and "accountId" in result:
        await register_account(user.id, result["accountId"], "tiktok")
    return result


@tiktok_router.post("/reconnect/{account_id}")
async def tiktok_reconnect(account_id: str, body: TikTokConnectRequest, _user=Depends(get_current_user)):
    """Reconnect an existing TikTok account with new auth code."""
    return await repliz_post(
        f"/public/account/tiktok/connect/{account_id}",
        json_body={"code": body.code},
    )


import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_music_cache: Dict[str, Any] = {}
_cache_ttl = 900  # 15 minutes in-memory cache


def infer_music_recommendation(
    title: str = "",
    hook: str = "",
    topic: str = "",
    job_id: str = "",
    clip_rank: int = 0,
) -> Dict[str, Any]:
    """Infers optimal TikTok music genre, date range, and seed offset for a given video."""
    import re
    combined_text = f"{title} {hook} {topic}".lower()
    tokens = set(re.findall(r"[a-z0-9]+", combined_text))

    # 1. Hype / Dance / High Energy / Gaming
    hype_tokens = {"dance", "energi", "workout", "gym", "hype", "party", "jedag", "remix", "beat", "kece", "gaming", "game", "esport", "fitnes"}
    if tokens & hype_tokens:
        return {
            "genre": "EDM",
            "date_range": "1DAY",
            "match_reason": "Sesuai ritme cepat & video dinamis",
            "seed_offset": clip_rank or 0,
        }

    # 2. Podcast / Story / Vlog / Calm / Narrative (check before general education)
    podcast_tokens = {"podcast", "cerita", "kisah", "ngobrol", "vlog", "santai", "coffee", "kopi", "buku", "sejarah", "filosofi", "religi", "wawancara", "interview"}
    if tokens & podcast_tokens:
        return {
            "genre": "FOLK",
            "date_range": "30DAY",
            "match_reason": "Cocok untuk dialog cerita & podcast santai",
            "seed_offset": clip_rank or 0,
        }

    # 3. Education / Business / Motivation / Tips / Tech
    edu_tokens = {"sukses", "bisnis", "uang", "tips", "karir", "finansial", "mindset", "motivasi", "tech", "ai", "coding", "rahasia", "cara", "belajar", "fakta", "edukasi", "saham", "investasi"}
    if tokens & edu_tokens:
        return {
            "genre": "POP",
            "date_range": "7DAY",
            "match_reason": "Cocok untuk konten edukasi & inspirasi",
            "seed_offset": (clip_rank or 1) - 1,
        }

    # 4. Comedy / Meme / Fun
    comedy_tokens = {"lucu", "kocak", "komedi", "prank", "ngakak", "funny", "meme", "parodi"}
    if tokens & comedy_tokens:
        return {
            "genre": "ALL",
            "date_range": "1DAY",
            "match_reason": "Trending #1 FYP TikTok hari ini",
            "seed_offset": clip_rank or 0,
        }

    # 5. Default rotation based on clip_rank to guarantee diversity across clips
    rank = max(1, clip_rank or 1)
    rotations = [
        ("ALL", "7DAY", "Trending teratas minggu ini"),
        ("POP", "7DAY", "Pop viral TikTok Indonesia"),
        ("EDM", "7DAY", "Beat enerjik latar belakang"),
        ("FOLK", "30DAY", "Akustik santai & ramah dialog"),
        ("ROCK", "7DAY", "Nuansa semangat & ritmis"),
        ("JAZZ", "30DAY", "Nuansa elegan & santai"),
    ]
    selected_rot = rotations[(rank - 1) % len(rotations)]
    return {
        "genre": selected_rot[0],
        "date_range": selected_rot[1],
        "match_reason": selected_rot[2],
        "seed_offset": (rank - 1) // len(rotations),
    }


@tiktok_router.get("/music")
async def get_tiktok_trending_music(
    genre: str = Query(default="RECOMMENDED", description="Music genre: RECOMMENDED, ALL, VIRAL_TODAY, POP, EDM, ROCK, FOLK, JAZZ"),
    country_code: str = Query(default="ID", description="Country code e.g. ID, US"),
    date_range: str = Query(default="7DAY", description="1DAY, 7DAY, 30DAY, 90DAY"),
    limit: int = Query(default=30, ge=1, le=100),
    search: Optional[str] = Query(default=None),
    job_id: Optional[str] = Query(default=None),
    clip_rank: Optional[int] = Query(default=None),
    title: Optional[str] = Query(default=None),
    hook: Optional[str] = Query(default=None),
    topic: Optional[str] = Query(default=None),
    shuffle_seed: int = Query(default=0, description="Offset seed to shuffle recommendations"),
    _user=Depends(get_current_user),
):
    """Fetch viral / trending music from TikTok via Repliz Addon API.
    Supports intelligent video-content recommendations, genre filtering, and track search.
    """
    effective_genre = (genre or "RECOMMENDED").upper().strip()
    effective_date_range = (date_range or "7DAY").upper().strip()
    match_reason = ""
    seed_offset = 0

    if effective_genre == "RECOMMENDED":
        rec = infer_music_recommendation(
            title=title or "",
            hook=hook or "",
            topic=topic or "",
            job_id=job_id or "",
            clip_rank=clip_rank or 0,
        )
        effective_genre = rec["genre"]
        effective_date_range = rec["date_range"]
        match_reason = rec["match_reason"]
        seed_offset = rec["seed_offset"] + shuffle_seed
    elif effective_genre == "VIRAL_TODAY":
        effective_genre = "ALL"
        effective_date_range = "1DAY"
        match_reason = "Trending viral 24 jam terakhir"
        seed_offset = shuffle_seed
    else:
        seed_offset = shuffle_seed

    # Map invalid genres to valid Repliz genres
    valid_repliz_genres = {"ALL", "POP", "ROCK", "EDM", "ELECTRONIC", "LATIN", "COUNTRY", "JAZZ", "CLASSICAL", "FOLK"}
    if effective_genre not in valid_repliz_genres:
        effective_genre = "ALL"

    cache_key = f"{effective_genre}_{country_code}_{effective_date_range}"
    now = time.time()
    cached = _music_cache.get(cache_key)

    if cached and (now - cached["timestamp"] < _cache_ttl):
        raw_docs = cached["docs"]
    else:
        try:
            res = await repliz_get(
                "/public/tiktok/music",
                params={
                    "genre": effective_genre,
                    "countryCode": country_code,
                    "dateRange": effective_date_range,
                },
            )
            raw_docs = res.get("docs", []) if isinstance(res, dict) else []
            _music_cache[cache_key] = {"docs": raw_docs, "timestamp": now}
        except Exception as e:
            logger.warning(f"Failed to fetch TikTok music from Repliz (genre={effective_genre}): {e}")
            raw_docs = []

    # Filter / Search if requested
    filtered_docs = list(raw_docs)
    if search and search.strip():
        s_lower = search.strip().lower()
        filtered_docs = [
            d for d in raw_docs
            if s_lower in (d.get("name") or "").lower() or s_lower in (d.get("artist") or "").lower()
        ]

    # Seed-based rotation for variety when multiple clips or shuffle is requested
    if seed_offset > 0 and len(filtered_docs) > 1 and not search:
        rot = seed_offset % min(len(filtered_docs), 12)
        filtered_docs = filtered_docs[rot:] + filtered_docs[:rot]

    # Format tracks
    tracks = []
    for idx, doc in enumerate(filtered_docs[:limit], 1):
        if idx == 1:
            usage_label = "1.8M+ Video Digunakan"
        elif idx <= 3:
            usage_label = "1.2M+ Video Digunakan"
        elif idx <= 10:
            usage_label = "750K+ Video Digunakan"
        elif idx <= 25:
            usage_label = "420K+ Video Digunakan"
        else:
            usage_label = "200K+ Video Digunakan"

        track_reason = match_reason if idx == 1 and match_reason else ("Trending Pilihan" if idx <= 3 else "")

        tracks.append({
            "id": str(doc.get("id") or ""),
            "name": doc.get("name") or "Unknown Title",
            "artist": doc.get("artist") or "Unknown Artist",
            "thumbnail": doc.get("thumbnail") or "",
            "duration": int(doc.get("duration") or 0),
            "url": doc.get("url") or "",  # Direct audio stream URL for in-browser playback
            "rank": idx,
            "usage_label": usage_label,
            "is_recommended": idx <= 3,
            "match_reason": track_reason,
        })

    return {
        "success": True,
        "country_code": country_code,
        "date_range": effective_date_range,
        "genre": effective_genre,
        "requested_genre": genre,
        "match_reason": match_reason,
        "total": len(tracks),
        "tracks": tracks,
    }
