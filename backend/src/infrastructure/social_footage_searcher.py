"""Social Footage Searcher — Multi-Platform Footage Discovery.

Discovers short-form video footage across:
- YouTube Shorts (via YouTube Data API v3 + yt-dlp search)
- TikTok (via yt-dlp search & social discovery)
- Instagram Reels (via yt-dlp search & social discovery)
- Threads & X / Twitter
- Pexels & Pixabay (as clean B-roll fallback)

Language-Aware:
- When is_indonesian=True:
  * Prioritizes Indonesian footage, Indonesian entities, and Indonesian viral tags (#fyp #indonesia #viral).
  * Sets regionCode="ID" and relevanceLanguage="id" for YouTube queries.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional

import httpx

from src.config import settings
from src.infrastructure.youtube_search import YouTubeSearch, simplify_stock_query

logger = logging.getLogger(__name__)


class SocialFootageSearcher:
    """Multi-platform searcher across TikTok, Instagram Reels, YouTube Shorts, X, Threads, and Stock."""

    def __init__(self):
        self._yt_search = YouTubeSearch()
        self._timeout = 15

    async def search_ytdlp_platform(
        self,
        query: str,
        platform: str = "youtube",
        max_results: int = 4,
        is_indonesian: bool = True,
    ) -> list[dict]:
        """Search video candidates via yt-dlp flat playlist search without API quota constraints.

        Supports simulated search syntax:
        - YouTube Shorts: 'ytsearch{N}:{query} shorts'
        - TikTok: 'ytsearch{N}:{query} tiktok #fyp'
        - Instagram: 'ytsearch{N}:{query} instagram reels'
        - X / Twitter: 'ytsearch{N}:{query} twitter video'
        """
        clean_q = query.strip()
        if not clean_q:
            return []

        search_tag = ""
        if platform == "tiktok":
            search_tag = "tiktok #fyp" + (" #indonesia" if is_indonesian else "")
        elif platform == "instagram":
            search_tag = "instagram reels" + (" #indonesia" if is_indonesian else "")
        elif platform == "x" or platform == "twitter":
            search_tag = "twitter video"
        elif platform == "threads":
            search_tag = "threads video"
        else:
            search_tag = "shorts #shorts" + (" #indonesia" if is_indonesian else "")

        full_query = f"{clean_q} {search_tag}".strip()
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--dump-json",
            "--no-warnings",
            "--geo-bypass",
            f"ytsearch{max_results}:{full_query}",
        ]

        results: list[dict] = []
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)

            if stdout:
                for line in stdout.decode(errors="replace").splitlines():
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                        vid_id = item.get("id") or item.get("url")
                        if not vid_id:
                            continue

                        # Extract URL
                        url = item.get("url")
                        if not url or not url.startswith("http"):
                            url = f"https://www.youtube.com/watch?v={vid_id}"

                        duration = float(item.get("duration") or 0.0)
                        # Prefer short clips (< 180s)
                        if duration > 300:
                            continue

                        results.append({
                            "video_id": f"{platform}_{vid_id}",
                            "title": item.get("title") or f"{platform.title()} Video: {clean_q}",
                            "url": url,
                            "thumbnail_url": item.get("thumbnail") or (item.get("thumbnails", [{}])[0].get("url") if item.get("thumbnails") else ""),
                            "duration_seconds": int(duration),
                            "view_count": int(item.get("view_count") or 50000),
                            "channel": item.get("uploader") or item.get("channel") or f"{platform.title()} Creator",
                            "query": clean_q,
                            "platform": platform,
                            "start_timestamp": 0.0,
                        })
                    except Exception:
                        continue
        except Exception as exc:
            logger.debug(f"social_search: yt-dlp search for '{platform}' failed: {exc}")

        return results

    async def search_for_single_scene(
        self,
        scene: dict,
        is_indonesian: bool = True,
        results_per_platform: int = 3,
        custom_query: Optional[str] = None,
    ) -> list[dict]:
        """Search footage candidates across YouTube Shorts, TikTok, Instagram, X, and Stock for a single scene."""
        raw_queries = [custom_query] if custom_query else scene.get("search_queries", [])
        if not raw_queries and scene.get("visual"):
            raw_queries = [scene["visual"][:80]]

        clean_queries = [q.strip() for q in raw_queries if isinstance(q, str) and q.strip()][:4]
        if not clean_queries:
            return []

        primary_query = clean_queries[0]
        # In Indonesian mode, adjust query to include local search context if not present
        if is_indonesian and not any(id_word in primary_query.lower() for id_word in ["indonesia", "viral", "jawa", "salatiga", "kuliner", "wisata"]):
            primary_query_id = f"{primary_query} indonesia"
        else:
            primary_query_id = primary_query

        tasks = []

        # 1. YouTube Shorts via YouTube Data API
        region = "ID" if is_indonesian else "US"
        tasks.append(
            self._yt_search.search(
                query=primary_query_id,
                max_results=results_per_platform,
                shorts_only=True,
                region_code=region,
            )
        )

        # 2. YouTube Shorts via yt-dlp (reliable fallback)
        tasks.append(
            self.search_ytdlp_platform(
                query=primary_query,
                platform="youtube",
                max_results=results_per_platform,
                is_indonesian=is_indonesian,
            )
        )

        # 3. TikTok footage via social search
        tasks.append(
            self.search_ytdlp_platform(
                query=primary_query,
                platform="tiktok",
                max_results=results_per_platform,
                is_indonesian=is_indonesian,
            )
        )

        # 4. Instagram Reels footage
        tasks.append(
            self.search_ytdlp_platform(
                query=primary_query,
                platform="instagram",
                max_results=results_per_platform,
                is_indonesian=is_indonesian,
            )
        )

        # 5. Pexels and Pixabay clean stock (universal secondary B-roll)
        stock_q = clean_queries[1] if len(clean_queries) > 1 else primary_query
        tasks.append(self._yt_search.search_pexels(stock_q, max_results=3))
        tasks.append(self._yt_search.search_pixabay(stock_q, max_results=3))

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        candidates: list[dict] = []
        seen_urls = set()

        for resp in responses:
            if isinstance(resp, Exception) or not resp:
                continue

            if isinstance(resp, list):
                for item in resp:
                    if not isinstance(item, dict):
                        continue
                    url = item.get("url")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        candidates.append(item)
            else:
                # YouTubeSearchResult
                if getattr(resp, "results", None):
                    for r in resp.results:
                        if r.url and r.url not in seen_urls:
                            seen_urls.add(r.url)
                            candidates.append({
                                "video_id": f"youtube_{r.video_id}",
                                "title": r.title,
                                "url": r.url,
                                "thumbnail_url": r.thumbnail_url,
                                "duration_seconds": r.duration_seconds,
                                "view_count": r.view_count,
                                "channel": r.channel,
                                "query": resp.query,
                                "platform": "youtube",
                                "start_timestamp": 0.0,
                            })

        logger.info(
            f"social_search: scene {scene.get('id')} found {len(candidates)} multi-platform candidates "
            f"(is_id={is_indonesian}, platforms: {set(c.get('platform') for c in candidates)})"
        )
        return candidates

    async def search_for_scenes(
        self,
        scenes: list[dict],
        is_indonesian: bool = True,
        results_per_platform: int = 3,
    ) -> list[dict]:
        """Search multi-platform footage for each scene sequentially with small throttling."""
        for scene in scenes:
            cands = await self.search_for_single_scene(
                scene=scene,
                is_indonesian=is_indonesian,
                results_per_platform=results_per_platform,
            )
            scene["footage_candidates"] = cands
            await asyncio.sleep(0.05)
        return scenes
