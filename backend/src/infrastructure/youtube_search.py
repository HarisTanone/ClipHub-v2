"""YouTube Search — Search YouTube videos/shorts via Data API v3.

Searches for footage candidates per scene keyword. Supports filtering
by duration (shorts), relevance, date, and view count.

Usage:
    yt = YouTubeSearch()
    results = await yt.search("Titanic ship sailing", max_results=5, shorts_only=True)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def simplify_stock_query(query: str) -> str:
    """Simplify query to 2-3 core physical nouns/actions by stripping filler terms and normalizing Indonesian terms to English.

    Stock APIs (Pexels, Pixabay) index primarily by 1-3 simple concrete English tags.
    Removing filmmaking adjectives (4k, cinematic, slow motion) and translating
    Indonesian terms (e.g. tepung-tepungan -> flour) drastically improves match hit rate and relevance.
    """
    if not query:
        return ""
    import re

    # 1. Normalize Indonesian entity/reduplications if present (e.g. tepung-tepungan -> flour baking)
    try:
        from src.infrastructure.object_image_overlay import normalize_indonesian_entity
        for token in query.lower().split():
            clean_tok = re.sub(r"[^\w\-]+", "", token)
            norm_id, norm_en, _ = normalize_indonesian_entity(clean_tok)
            if norm_en:
                query = query.lower().replace(token, norm_en)
    except Exception:
        pass

    fillers = [
        r"\bcinematic\b", r"\b4k\b", r"\b8k\b", r"\bhd\b", r"\buhd\b", r"\b60fps\b",
        r"\bultra\b", r"\bfootage\b", r"\bb-roll\b", r"\bbroll\b", r"\bstock\b",
        r"\bvideo\b", r"\bclip\b", r"\bhigh\s+quality\b", r"\bvertical\b",
        r"\b9:16\b", r"\bhyper-realistic\b", r"\brealistic\b", r"\bslow\s+motion\b",
        r"\bmacro\b", r"\bclose\s+up\b", r"\bextreme\b", r"\bwide\s+shot\b",
        r"\bdrone\s+shot\b", r"\bdrone\b", r"\baerial\b", r"\btracking\s+shot\b",
        r"\bcamera\b", r"\bshot\b", r"\bscene\b", r"\bbackground\b",
        r"\byang\b", r"\bdan\b", r"\batau\b", r"\buntuk\b", r"\bdengan\b",
    ]
    cleaned = query.lower()
    for f in fillers:
        cleaned = re.sub(f, " ", cleaned, flags=re.IGNORECASE)

    words = [w for w in re.findall(r'[a-zA-Z0-9]+', cleaned) if len(w) >= 3]
    if not words:
        words = [w for w in re.findall(r'[a-zA-Z0-9]+', query) if len(w) >= 3]

    return " ".join(words[:4]) if words else query.strip()


@dataclass
class YouTubeResult:
    """A single YouTube search result with metadata."""
    video_id: str
    title: str
    channel: str
    description: str = ""
    thumbnail_url: str = ""
    published_at: str = ""
    duration_seconds: int = 0
    view_count: int = 0
    url: str = ""
    is_hd: bool = True
    quality: str = "HD"

    def __post_init__(self):
        if not self.url:
            self.url = f"https://www.youtube.com/watch?v={self.video_id}"


@dataclass
class YouTubeSearchResult:
    """Aggregated search results for a single query."""
    query: str
    results: list[YouTubeResult] = field(default_factory=list)
    total_results: int = 0
    error: Optional[str] = None


def _get_pexels_api_key() -> str:
    try:
        from src.infrastructure.system_config_store import get_config_value
        val = get_config_value("PEXELS_API_KEY")
        if val:
            return str(val).strip()
    except Exception:
        pass
    return (getattr(settings, "PEXELS_API_KEY", "") or "").strip()


def _get_pixabay_api_key() -> str:
    try:
        from src.infrastructure.system_config_store import get_config_value
        val = get_config_value("PIXABAY_API_KEY")
        if val:
            return str(val).strip()
    except Exception:
        pass
    return (getattr(settings, "PIXABAY_API_KEY", "") or "").strip()


class YouTubeSearch:
    """YouTube Data API v3 search client.

    Features:
    - Search by keyword/topic
    - Filter for Shorts (videoDuration=short)
    - Get video details (duration, views)
    - Rate-limit aware with retry
    """

    def __init__(self):
        self._api_key = settings.YOUTUBE_API_KEY
        self._timeout = 15

    async def search(
        self,
        query: str,
        max_results: int = 5,
        shorts_only: bool = False,
        order: str = "relevance",
        published_after: Optional[str] = None,
        region_code: str = "",
        video_definition: str = "high",
    ) -> YouTubeSearchResult:
        """Search YouTube for videos (defaults to high definition HD 720p+).

        Args:
            query: Search keywords.
            max_results: Number of results (1-50).
            shorts_only: Filter for short videos (< 4 min, typically Shorts).
            order: Sort by 'relevance', 'date', 'viewCount', 'rating'.
            published_after: ISO date filter (e.g. '2024-01-01T00:00:00Z').
            region_code: ISO country code (e.g. 'US', 'ID').
            video_definition: 'high' for HD (720p+), 'any' for all resolutions.

        Returns:
            YouTubeSearchResult with list of video candidates.
        """
        if not self._api_key:
            return YouTubeSearchResult(
                query=query, error="YOUTUBE_API_KEY not configured"
            )

        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": min(max_results, 50),
            "order": order,
            "key": self._api_key,
        }

        if video_definition:
            params["videoDefinition"] = video_definition

        if shorts_only:
            params["videoDuration"] = "short"

        if published_after:
            params["publishedAfter"] = published_after

        if region_code:
            params["regionCode"] = region_code

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(YOUTUBE_SEARCH_URL, params=params)

                if resp.status_code == 403:
                    logger.error("youtube_search: API quota exceeded or key invalid")
                    return YouTubeSearchResult(
                        query=query, error="YouTube API quota exceeded"
                    )

                if resp.status_code != 200:
                    logger.error(f"youtube_search: API error {resp.status_code}")
                    return YouTubeSearchResult(
                        query=query, error=f"API error {resp.status_code}"
                    )

                data = resp.json()
                total = data.get("pageInfo", {}).get("totalResults", 0)

                # Parse search results
                video_ids = []
                snippets = {}
                for item in data.get("items", []):
                    vid_id = item["id"]["videoId"]
                    video_ids.append(vid_id)
                    snippets[vid_id] = item["snippet"]

                # Get video details (duration, views)
                details = {}
                if video_ids:
                    details = await self._get_video_details(client, video_ids)

                # Build results
                results = []
                for vid_id in video_ids:
                    snippet = snippets[vid_id]
                    detail = details.get(vid_id, {})

                    results.append(YouTubeResult(
                        video_id=vid_id,
                        title=snippet.get("title", ""),
                        channel=snippet.get("channelTitle", ""),
                        description=snippet.get("description", ""),
                        thumbnail_url=snippet.get("thumbnails", {}).get(
                            "high", {}
                        ).get("url", ""),
                        published_at=snippet.get("publishedAt", ""),
                        duration_seconds=detail.get("duration", 0),
                        view_count=detail.get("views", 0),
                    ))

                return YouTubeSearchResult(
                    query=query, results=results, total_results=total
                )

        except httpx.TimeoutException:
            logger.error(f"youtube_search: timeout for query '{query}'")
            return YouTubeSearchResult(query=query, error="Request timeout")
        except Exception as exc:
            logger.error(f"youtube_search: unexpected error: {exc}")
            return YouTubeSearchResult(query=query, error=str(exc))


    async def search_pexels(
        self,
        query: str,
        max_results: int = 4,
    ) -> list[dict]:
        """Search Pexels video API if configured."""
        api_key = _get_pexels_api_key()
        if not api_key:
            return []

        clean_q = simplify_stock_query(query) or query

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.pexels.com/videos/search",
                    headers={"Authorization": api_key},
                    params={"query": clean_q, "orientation": "portrait", "per_page": min(max_results, 10)},
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                results = []
                for v in data.get("videos", []):
                    files = v.get("video_files", [])
                    best_file = None

                    # Prioritize Full HD 1080p and HD 720p portrait/landscape files (start from 720p minimum)
                    hd_files = [
                        f for f in files
                        if f.get("link") and (
                            (min(f.get("width", 0), f.get("height", 0)) >= 720)
                            or (f.get("height", 0) >= 720 or f.get("width", 0) >= 1280)
                            or (f.get("quality") == "hd")
                        )
                    ]
                    if hd_files:
                        best_file = max(hd_files, key=lambda x: (x.get("height", 0) * x.get("width", 0)))
                    else:
                        best_file = files[0] if files else None

                    if best_file and best_file.get("link"):
                        h_val = int(best_file.get("height", 0))
                        w_val = int(best_file.get("width", 0))
                        is_hd = (min(h_val, w_val) >= 720) or h_val >= 720 or best_file.get("quality") == "hd"
                        q_label = "4K" if min(h_val, w_val) >= 2160 else ("1080p" if min(h_val, w_val) >= 1080 else ("720p" if is_hd else "SD"))
                        results.append({
                            "video_id": f"pexels_{v['id']}",
                            "title": f"Pexels Stock: {clean_q.title()}",
                            "url": best_file["link"],
                            "thumbnail_url": v.get("image", ""),
                            "duration_seconds": v.get("duration", 0),
                            "view_count": 50000,
                            "channel": v.get("user", {}).get("name", "Pexels Creator"),
                            "query": clean_q,
                            "platform": "pexels",
                            "media_type": "video",
                            "start_timestamp": 0.0,
                            "is_hd": is_hd,
                            "quality": q_label,
                            "height": h_val,
                            "width": w_val,
                        })
                return results
        except Exception as exc:
            logger.debug(f"pexels_search: failed for query '{query}': {exc}")
            return []

    async def search_pexels_photos(
        self,
        query: str,
        max_results: int = 4,
    ) -> list[dict]:
        """Search Pexels Photo API for high-resolution portrait images."""
        api_key = _get_pexels_api_key()
        if not api_key:
            return []

        clean_q = simplify_stock_query(query) or query

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.pexels.com/v1/search",
                    headers={"Authorization": api_key},
                    params={"query": clean_q, "orientation": "portrait", "per_page": min(max_results, 10)},
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                results = []
                for p in data.get("photos", []):
                    src = p.get("src", {})
                    img_url = src.get("large2x") or src.get("portrait") or src.get("large") or src.get("original")
                    if img_url:
                        results.append({
                            "video_id": f"pexels_img_{p['id']}",
                            "title": p.get("alt") or f"Pexels Photo: {clean_q.title()}",
                            "url": img_url,
                            "thumbnail_url": src.get("medium") or src.get("small") or img_url,
                            "duration_seconds": 0,
                            "view_count": 60000,
                            "channel": p.get("photographer", "Pexels Photographer"),
                            "query": clean_q,
                            "platform": "pexels",
                            "media_type": "image",
                            "start_timestamp": 0.0,
                            "is_hd": True,
                            "quality": "HD",
                        })
                return results
        except Exception as exc:
            logger.debug(f"pexels_photos_search: failed for query '{query}': {exc}")
            return []

    async def search_pixabay(
        self,
        query: str,
        max_results: int = 4,
    ) -> list[dict]:
        """Search Pixabay video API if configured."""
        api_key = _get_pixabay_api_key()
        if not api_key:
            return []

        clean_q = simplify_stock_query(query) or query

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://pixabay.com/api/videos/",
                    params={
                        "key": api_key,
                        "q": clean_q,
                        "video_type": "film",
                        "min_width": 720,
                        "min_height": 720,
                        "per_page": min(max_results, 10),
                    },
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                results = []
                for v in data.get("hits", []):
                    videos = v.get("videos", {})
                    # Prefer HD tiers: large (1080p) or medium (720p)
                    chosen = videos.get("large") or videos.get("medium") or videos.get("small") or {}
                    link = chosen.get("url")
                    if link:
                        h_val = int(chosen.get("height", 0))
                        w_val = int(chosen.get("width", 0))
                        is_hd = (min(h_val, w_val) >= 720) or max(h_val, w_val) >= 1280 or h_val >= 720 or chosen.get("quality") == "hd"
                        q_label = "1080p" if max(h_val, w_val) >= 1920 else ("720p" if is_hd else "SD")
                        results.append({
                            "video_id": f"pixabay_{v['id']}",
                            "title": f"Pixabay Stock: {v.get('tags', clean_q).title()}",
                            "url": link,
                            "thumbnail_url": v.get("userImageURL") or chosen.get("thumbnail") or "",
                            "duration_seconds": v.get("duration", 0),
                            "view_count": v.get("views", 10000),
                            "channel": v.get("user", "Pixabay Creator"),
                            "query": clean_q,
                            "platform": "pixabay",
                            "media_type": "video",
                            "start_timestamp": 0.0,
                            "is_hd": is_hd,
                            "quality": q_label,
                            "height": h_val,
                            "width": w_val,
                        })
                return results
        except Exception as exc:
            logger.debug(f"pixabay_search: failed for query '{query}': {exc}")
            return []

    async def search_pixabay_photos(
        self,
        query: str,
        max_results: int = 4,
    ) -> list[dict]:
        """Search Pixabay Photo API for vertical/portrait photos."""
        api_key = _get_pixabay_api_key()
        if not api_key:
            return []

        clean_q = simplify_stock_query(query) or query

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://pixabay.com/api/",
                    params={
                        "key": api_key,
                        "q": clean_q,
                        "image_type": "photo",
                        "orientation": "vertical",
                        "per_page": min(max_results, 10),
                    },
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                results = []
                for hit in data.get("hits", []):
                    img_url = hit.get("largeImageURL") or hit.get("webformatURL")
                    if img_url:
                        results.append({
                            "video_id": f"pixabay_img_{hit['id']}",
                            "title": f"Pixabay Photo: {hit.get('tags', clean_q).title()}",
                            "url": img_url,
                            "thumbnail_url": hit.get("webformatURL") or hit.get("previewURL") or img_url,
                            "duration_seconds": 0,
                            "view_count": hit.get("views", 15000),
                            "channel": hit.get("user", "Pixabay Photographer"),
                            "query": clean_q,
                            "platform": "pixabay",
                            "media_type": "image",
                            "start_timestamp": 0.0,
                            "is_hd": True,
                            "quality": "HD",
                        })
                return results
        except Exception as exc:
            logger.debug(f"pixabay_photos_search: failed for query '{query}': {exc}")
            return []

    async def search_wikimedia_photos(
        self,
        query: str,
        max_results: int = 4,
    ) -> list[dict]:
        """Search Wikimedia Commons for free open-access high-resolution images."""
        clean_q = simplify_stock_query(query) or query
        clean_q = clean_q.strip()
        if not clean_q:
            return []

        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(
                    "https://commons.wikimedia.org/w/api.php",
                    params={
                        "action": "query",
                        "generator": "search",
                        "gsrnamespace": "6",
                        "gsrsearch": clean_q,
                        "gsrlimit": min(max_results, 8),
                        "prop": "imageinfo",
                        "iiprop": "url|size|mime",
                        "format": "json",
                    },
                    headers={"User-Agent": "ClipHub/2.0 (VideoGenerator; automated bot)"},
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                pages = data.get("query", {}).get("pages", {})
                results = []
                for pid, page in pages.items():
                    info_list = page.get("imageinfo", [])
                    if not info_list:
                        continue
                    info = info_list[0]
                    mime = info.get("mime", "")
                    if not mime.startswith("image/"):
                        continue
                    img_url = info.get("url")
                    if not img_url:
                        continue
                    title = page.get("title", f"Wikimedia Image: {clean_q}").replace("File:", "").replace(".jpg", "").replace(".png", "")
                    results.append({
                        "video_id": f"wikimedia_img_{pid}",
                        "title": title.title()[:80],
                        "url": img_url,
                        "thumbnail_url": img_url,
                        "duration_seconds": 0,
                        "view_count": 25000,
                        "channel": "Wikimedia Commons",
                        "query": clean_q,
                        "platform": "wikimedia",
                        "media_type": "image",
                        "start_timestamp": 0.0,
                        "is_hd": True,
                        "quality": "HD",
                    })
                return results
        except Exception as exc:
            logger.debug(f"wikimedia_photos_search: failed for query '{query}': {exc}")
            return []

    async def search_for_single_scene(
        self,
        scene: dict,
        custom_query: Optional[str] = None,
        results_per_query: int = 5,
    ) -> list[dict]:
        """Search footage candidates for a single scene with multi-source parallel queries."""
        queries = [custom_query] if custom_query else scene.get("search_queries", [])
        if not queries and scene.get("visual"):
            queries = [scene["visual"][:80]]

        all_candidates = []
        seen_ids = set()

        tasks = []
        # Parallel tasks: Pexels (video + photo), Pixabay (video + photo), Wikimedia, YouTube across all queries (up to 4)
        for q in queries[:4]:
            if not q or not isinstance(q, str) or not q.strip():
                continue
            clean_q = q.strip()
            tasks.append(self.search_pexels(clean_q, max_results=4))
            tasks.append(self.search_pixabay(clean_q, max_results=4))
            tasks.append(self.search_pexels_photos(clean_q, max_results=3))
            tasks.append(self.search_pixabay_photos(clean_q, max_results=3))
            tasks.append(self.search_wikimedia_photos(clean_q, max_results=3))
            tasks.append(self.search(query=clean_q, max_results=max(results_per_query, 6), shorts_only=False))

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for resp in responses:
            if isinstance(resp, Exception) or not resp:
                continue
            if isinstance(resp, list):
                # Pexels, Pixabay, or Wikimedia list of dicts
                for r in resp:
                    if r.get("video_id") not in seen_ids:
                        seen_ids.add(r["video_id"])
                        all_candidates.append(r)
            elif isinstance(resp, YouTubeSearchResult):
                if resp.error:
                    continue
                for r in resp.results:
                    if r.video_id not in seen_ids:
                        seen_ids.add(r.video_id)
                        all_candidates.append({
                            "video_id": r.video_id,
                            "title": r.title,
                            "url": r.url,
                            "thumbnail_url": r.thumbnail_url,
                            "duration_seconds": r.duration_seconds,
                            "view_count": r.view_count,
                            "channel": r.channel,
                            "query": resp.query,
                            "platform": "youtube",
                            "media_type": "video",
                            "start_timestamp": 0.0,
                        })

        return all_candidates

    async def search_for_scenes(
        self,
        scenes: list[dict],
        results_per_scene: int = 5,
        shorts_only: bool = False,
    ) -> list[dict]:
        """Search YouTube and Pexels for footage for each scene."""
        for i, scene in enumerate(scenes):
            candidates = await self.search_for_single_scene(
                scene=scene,
                results_per_query=results_per_scene,
            )
            scene["footage_candidates"] = candidates
            await asyncio.sleep(0.1)

        return scenes

    async def _get_video_details(
        self, client: httpx.AsyncClient, video_ids: list[str]
    ) -> dict:
        """Get video contentDetails (duration) and statistics (views).

        Args:
            client: Active httpx client.
            video_ids: List of video IDs to look up.

        Returns:
            Dict mapping video_id → {duration: int, views: int}
        """
        params = {
            "part": "contentDetails,statistics",
            "id": ",".join(video_ids),
            "key": self._api_key,
        }

        try:
            resp = await client.get(YOUTUBE_VIDEOS_URL, params=params)
            if resp.status_code != 200:
                return {}

            data = resp.json()
            details = {}

            for item in data.get("items", []):
                vid_id = item["id"]
                duration_iso = item.get("contentDetails", {}).get("duration", "")
                views = int(
                    item.get("statistics", {}).get("viewCount", 0)
                )
                details[vid_id] = {
                    "duration": self._parse_iso_duration(duration_iso),
                    "views": views,
                }

            return details

        except Exception as exc:
            logger.warning(f"youtube_search: video details failed: {exc}")
            return {}

    @staticmethod
    def _parse_iso_duration(iso_duration: str) -> int:
        """Parse ISO 8601 duration (PT1M30S) to seconds."""
        if not iso_duration or not iso_duration.startswith("PT"):
            return 0

        import re
        hours = re.search(r"(\d+)H", iso_duration)
        minutes = re.search(r"(\d+)M", iso_duration)
        seconds = re.search(r"(\d+)S", iso_duration)

        total = 0
        if hours:
            total += int(hours.group(1)) * 3600
        if minutes:
            total += int(minutes.group(1)) * 60
        if seconds:
            total += int(seconds.group(1))

        return total
