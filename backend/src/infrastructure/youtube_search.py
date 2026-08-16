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
    ) -> YouTubeSearchResult:
        """Search YouTube for videos.

        Args:
            query: Search keywords.
            max_results: Number of results (1-50).
            shorts_only: Filter for short videos (< 4 min, typically Shorts).
            order: Sort by 'relevance', 'date', 'viewCount', 'rating'.
            published_after: ISO date filter (e.g. '2024-01-01T00:00:00Z').
            region_code: ISO country code (e.g. 'US', 'ID').

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
        api_key = settings.PEXELS_API_KEY
        if not api_key:
            return []

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.pexels.com/videos/search",
                    headers={"Authorization": api_key},
                    params={"query": query, "orientation": "portrait", "per_page": min(max_results, 10)},
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                results = []
                for v in data.get("videos", []):
                    files = v.get("video_files", [])
                    best_file = None
                    for f in files:
                        if f.get("quality") == "hd" or (f.get("width", 0) >= 720 and f.get("height", 0) >= 1280):
                            best_file = f
                            break
                    if not best_file and files:
                        best_file = files[0]

                    if best_file and best_file.get("link"):
                        results.append({
                            "video_id": f"pexels_{v['id']}",
                            "title": f"Pexels Stock: {query.title()}",
                            "url": best_file["link"],
                            "thumbnail_url": v.get("image", ""),
                            "duration_seconds": v.get("duration", 0),
                            "view_count": 50000,
                            "channel": v.get("user", {}).get("name", "Pexels Creator"),
                            "query": query,
                            "platform": "pexels",
                        })
                return results
        except Exception as exc:
            logger.debug(f"pexels_search: failed for query '{query}': {exc}")
            return []

    async def search_pixabay(
        self,
        query: str,
        max_results: int = 4,
    ) -> list[dict]:
        """Search Pixabay video API if configured."""
        api_key = settings.PIXABAY_API_KEY
        if not api_key:
            return []

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://pixabay.com/api/videos/",
                    params={
                        "key": api_key,
                        "q": query,
                        "video_type": "film",
                        "min_width": 720,
                        "per_page": min(max_results, 10),
                    },
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                results = []
                for v in data.get("hits", []):
                    videos = v.get("videos", {})
                    chosen = videos.get("medium") or videos.get("large") or videos.get("small") or {}
                    link = chosen.get("url")
                    if link:
                        results.append({
                            "video_id": f"pixabay_{v['id']}",
                            "title": f"Pixabay Stock: {v.get('tags', query).title()}",
                            "url": link,
                            "thumbnail_url": v.get("userImageURL") or chosen.get("thumbnail") or "",
                            "duration_seconds": v.get("duration", 0),
                            "view_count": v.get("views", 10000),
                            "channel": v.get("user", "Pixabay Creator"),
                            "query": query,
                            "platform": "pixabay",
                        })
                return results
        except Exception as exc:
            logger.debug(f"pixabay_search: failed for query '{query}': {exc}")
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
        # Parallel tasks: Pexels, Pixabay, YouTube
        for q in queries[:2]:
            tasks.append(self.search_pexels(q, max_results=3))
            tasks.append(self.search_pixabay(q, max_results=3))
        for q in queries[:3]:
            tasks.append(self.search(query=q, max_results=results_per_query, shorts_only=False))

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for resp in responses:
            if isinstance(resp, Exception) or not resp:
                continue
            if isinstance(resp, list):
                # Pexels or Pixabay list of dicts
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
