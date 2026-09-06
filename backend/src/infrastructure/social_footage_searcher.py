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
import urllib.parse
from typing import Any, Optional

import httpx
import requests

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
            search_tag = "tiktok #fyp HD" + (" #indonesia" if is_indonesian else "")
        elif platform == "instagram":
            search_tag = "instagram reels HD" + (" #indonesia" if is_indonesian else "")
        elif platform == "x" or platform == "twitter":
            search_tag = "twitter video HD"
        elif platform == "threads":
            search_tag = "threads video HD"
        else:
            search_tag = "shorts #shorts HD" + (" #indonesia" if is_indonesian else "")

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

                        h = int(item.get("height") or 0)
                        w = int(item.get("width") or 0)
                        format_str = str(item.get("format_note", "") or item.get("format", "")).lower()
                        is_hd = (h >= 720 or w >= 720 or "hd" in format_str or "720" in format_str or "1080" in format_str or "4k" in format_str)
                        q_label = f"{h}p" if h > 0 else ("HD" if is_hd else "SD")

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
                            "media_type": "video",
                            "start_timestamp": 0.0,
                            "is_hd": is_hd,
                            "quality": q_label,
                            "height": h,
                            "width": w,
                        })
                    except Exception:
                        continue
        except Exception as exc:
            logger.debug(f"social_search: yt-dlp search for '{platform}' failed: {exc}")

        return results

    async def _probe_post_with_ytdlp(
        self,
        post_url: str,
        default_title: str,
        clean_q: str,
        platform_hint: str = "web",
    ) -> Optional[dict]:
        """Inspect and extract video stream format metadata via yt-dlp."""
        cmd = ["yt-dlp", "--dump-json", "--no-warnings", "--geo-bypass", post_url]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=12)
            if stdout:
                first_line = stdout.decode(errors="replace").strip().splitlines()[0]
                item = json.loads(first_line)
                dur = float(item.get("duration") or 0.0)
                if dur <= 0 or dur > 400:
                    return None

                h = int(item.get("height") or 0)
                w = int(item.get("width") or 0)
                is_hd = (h >= 720 or w >= 720)
                q_label = f"{h}p" if h > 0 else ("HD" if is_hd else "SD")

                # Detect platform
                plat = platform_hint
                low_url = post_url.lower()
                if "x.com" in low_url or "twitter.com" in low_url:
                    plat = "x"
                elif "tiktok.com" in low_url:
                    plat = "tiktok"
                elif "youtube.com" in low_url or "youtu.be" in low_url:
                    plat = "youtube"
                elif "instagram.com" in low_url:
                    plat = "instagram"

                return {
                    "video_id": f"{plat}_{item.get('id', '')}",
                    "title": item.get("title") or default_title or f"Video: {clean_q}",
                    "url": post_url,
                    "thumbnail_url": item.get("thumbnail") or (item.get("thumbnails", [{}])[0].get("url") if item.get("thumbnails") else ""),
                    "duration_seconds": int(dur),
                    "view_count": int(item.get("view_count") or 50000),
                    "channel": item.get("uploader") or item.get("channel") or f"Creator ({plat})",
                    "query": clean_q,
                    "platform": plat,
                    "media_type": "video",
                    "start_timestamp": 0.0,
                    "is_hd": is_hd,
                    "quality": q_label,
                    "height": h,
                    "width": w,
                }
        except Exception as e:
            logger.debug(f"social_search: yt-dlp probe failed for {post_url}: {e}")
            return None

    def _fetch_web_video_urls_sync(self, search_q: str) -> list[str]:
        """Synchronously query Yahoo Video and Web search index to discover active video URLs."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        urls_to_try = [
            f"https://video.search.yahoo.com/search/video?p={urllib.parse.quote(search_q)}",
            f"https://search.yahoo.com/search?p={urllib.parse.quote(search_q)}",
        ]

        found_urls: list[str] = []
        seen: set[str] = set()

        for u in urls_to_try:
            try:
                r = requests.get(u, headers=headers, timeout=8)
                if r.status_code == 200:
                    # 1. Yahoo video card direct reference URLs (most accurate)
                    refs = re.findall(r'data-referenceurl=[\"\']([^\"\']+)[\"\']', r.text)
                    for ref in refs:
                        if ref not in seen and any(p in ref.lower() for p in ["youtube.com/watch", "youtu.be", "tiktok.com", "instagram.com", "x.com", "twitter.com"]):
                            seen.add(ref)
                            found_urls.append(ref)

                    # 2. X status direct regex
                    for match in re.finditer(r"https?://(?:x\.com|twitter\.com)/([A-Za-z0-9_]+)/status/(\d+)", r.text):
                        username, sid = match.groups()
                        if username.lower() not in ("i", "search", "intent", "explore", "home"):
                            status_url = f"https://x.com/{username}/status/{sid}"
                            if status_url not in seen:
                                seen.add(status_url)
                                found_urls.append(status_url)

                    # 3. Yahoo RU= redirect links
                    for target in re.findall(r"/RU=([^/]+)/RK=", r.text):
                        unq = urllib.parse.unquote(target)
                        if any(p in unq.lower() for p in ["youtube.com/watch", "youtu.be", "tiktok.com", "instagram.com", "x.com", "twitter.com"]):
                            if unq not in seen:
                                seen.add(unq)
                                found_urls.append(unq)
            except Exception as e:
                logger.debug(f"social_search: search error on {u[:40]}: {e}")
                continue

        return found_urls

    async def _search_brave_video_api(self, query: str, max_results: int = 4) -> list[str]:
        """Fetch video post URLs from Brave Search API if API key is provided."""
        api_key = getattr(settings, "BRAVE_SEARCH_API_KEY", None)
        if not api_key:
            return []
        try:
            url = "https://api.search.brave.com/res/v1/videos/search"
            headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
            params = {"q": query, "count": max_results * 2, "freshness": "pd"}
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, headers=headers, params=params)
                if res.status_code == 200:
                    data = res.json()
                    return [item.get("url") for item in data.get("results", []) if item.get("url")]
        except Exception as e:
            logger.warning(f"social_search: Brave Video API error: {e}")
        return []

    async def _search_bing_video_api(self, query: str, max_results: int = 4) -> list[str]:
        """Fetch video post URLs from Bing Video Search API if API key is provided."""
        api_key = getattr(settings, "BING_SEARCH_API_KEY", None)
        if not api_key:
            return []
        try:
            url = "https://api.bing.microsoft.com/v7.0/videos/search"
            headers = {"Ocp-Apim-Subscription-Key": api_key}
            params = {
                "q": query,
                "count": max_results * 2,
                "freshness": "Day",
                "videoLength": "Short",
                "pricing": "free",
            }
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, headers=headers, params=params)
                if res.status_code == 200:
                    data = res.json()
                    return [item.get("contentUrl") for item in data.get("value", []) if item.get("contentUrl")]
        except Exception as e:
            logger.warning(f"social_search: Bing Video API error: {e}")
        return []

    async def _search_google_custom_search_api(self, query: str, max_results: int = 4) -> list[str]:
        """Fetch video URLs from Google Custom Search JSON API if API key + CX are provided."""
        api_key = getattr(settings, "GOOGLE_SEARCH_API_KEY", None)
        cx = getattr(settings, "GOOGLE_SEARCH_CX", None)
        if not api_key or not cx:
            return []
        try:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {"key": api_key, "cx": cx, "q": f"{query} video", "num": max_results, "dateRestrict": "d1"}
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, params=params)
                if res.status_code == 200:
                    data = res.json()
                    return [item.get("link") for item in data.get("items", []) if item.get("link")]
        except Exception as e:
            logger.warning(f"social_search: Google Custom Search API error: {e}")
        return []

    async def search_universal_video_candidates(
        self,
        query: str,
        max_results: int = 4,
        is_indonesian: bool = True,
    ) -> list[dict]:
        """Universal multi-platform video discovery (YouTube, TikTok, X, web).

        Uses official search API if keys are provided (Brave/Bing/Google),
        otherwise falls back seamlessly to the zero-cost web video index.
        """
        clean_q = query.strip()
        if not clean_q:
            return []

        # 1. Try official search engine APIs if configured
        urls: list[str] = []
        if getattr(settings, "BRAVE_SEARCH_API_KEY", None):
            urls = await self._search_brave_video_api(clean_q, max_results)
        elif getattr(settings, "BING_SEARCH_API_KEY", None):
            urls = await self._search_bing_video_api(clean_q, max_results)
        elif getattr(settings, "GOOGLE_SEARCH_API_KEY", None) and getattr(settings, "GOOGLE_SEARCH_CX", None):
            urls = await self._search_google_custom_search_api(clean_q, max_results)

        # 2. Fallback to zero-cost web video search index if no API keys configured or no results
        if not urls:
            search_q = f"{clean_q} video"
            urls = await asyncio.to_thread(self._fetch_web_video_urls_sync, search_q)

        if not urls:
            return []

        # Extract meaningful query keywords for relevance filtering
        q_tokens = set(re.findall(r"[a-zA-Z0-9]{3,}", clean_q.lower())) - {"video", "site", "com", "http", "https", "shorts", "clip"}

        # Probe video streams in parallel with yt-dlp
        probe_tasks = [
            self._probe_post_with_ytdlp(u, f"Video: {clean_q}", clean_q)
            for u in urls[: max_results * 3]
        ]
        probed = await asyncio.gather(*probe_tasks, return_exceptions=True)

        candidates: list[dict] = []
        seen = set()
        for cand in probed:
            if isinstance(cand, dict) and cand.get("url") and cand["url"] not in seen:
                title_lower = (cand.get("title") or "").lower()
                # Skip obvious spam or off-topic clickbait
                junk_markers = ["judi", "slot", "gacor", "tawuran", "ditembak", "tendangan", "bokep", "porno", "sepakbola", "highlight bola", "gameplay", "mobile legends", "roblox", "free fire"]
                if any(jm in title_lower for jm in junk_markers) and not any(jm in clean_q.lower() for jm in junk_markers):
                    continue

                # If we have distinct query tokens, require at least 1 keyword match in title
                if q_tokens:
                    title_tokens = set(re.findall(r"[a-zA-Z0-9]{3,}", title_lower))
                    if not (q_tokens & title_tokens):
                        # No keyword match with query - reject off-topic candidate
                        continue

                seen.add(cand["url"])
                candidates.append(cand)
                if len(candidates) >= max_results:
                    break

        return candidates

    async def search_x_video_posts(
        self,
        query: str,
        max_results: int = 4,
        is_indonesian: bool = True,
    ) -> list[dict]:
        """Search public X (Twitter) status posts containing video without requiring an X API key."""
        clean_q = query.strip()
        if not clean_q:
            return []

        search_q = f"site:x.com {clean_q} video"
        found_urls = await asyncio.to_thread(self._fetch_web_video_urls_sync, search_q)
        x_urls = [u for u in found_urls if "x.com" in u or "twitter.com" in u]

        if not x_urls:
            search_q_simple = f"site:x.com {clean_q}"
            found_urls = await asyncio.to_thread(self._fetch_web_video_urls_sync, search_q_simple)
            x_urls = [u for u in found_urls if "x.com" in u or "twitter.com" in u]

        if not x_urls:
            return []

        q_tokens = set(re.findall(r"[a-zA-Z0-9]{3,}", clean_q.lower())) - {"video", "site", "com", "http", "https", "shorts", "clip"}

        probe_tasks = [
            self._probe_post_with_ytdlp(u, f"X Video: {clean_q}", clean_q, platform_hint="x")
            for u in x_urls[: max_results * 3]
        ]
        probed = await asyncio.gather(*probe_tasks, return_exceptions=True)

        candidates: list[dict] = []
        seen = set()
        for cand in probed:
            if isinstance(cand, dict) and cand.get("url") and cand["url"] not in seen:
                title_lower = (cand.get("title") or "").lower()
                junk_markers = ["judi", "slot", "gacor", "tawuran", "ditembak", "tendangan", "bokep", "porno", "sepakbola", "highlight bola", "gameplay", "mobile legends", "roblox", "free fire"]
                if any(jm in title_lower for jm in junk_markers) and not any(jm in clean_q.lower() for jm in junk_markers):
                    continue

                if q_tokens:
                    title_tokens = set(re.findall(r"[a-zA-Z0-9]{3,}", title_lower))
                    if not (q_tokens & title_tokens):
                        continue

                seen.add(cand["url"])
                candidates.append(cand)
                if len(candidates) >= max_results:
                    break

        return candidates

    async def search_for_single_scene(
        self,
        scene: dict,
        is_indonesian: bool = True,
        results_per_platform: int = 3,
        custom_query: Optional[str] = None,
    ) -> list[dict]:
        """Search multi-source footage candidates across X, Universal Web Video, and Stock."""
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

        candidates: list[dict] = []
        seen_urls: set[str] = set()

        # ─── 1. Public Video Search (Universal & X Posts) ────────────────────────
        tasks = [
            self.search_universal_video_candidates(
                query=primary_query,
                max_results=results_per_platform,
                is_indonesian=is_indonesian,
            ),
            self.search_x_video_posts(
                query=primary_query,
                max_results=results_per_platform,
                is_indonesian=is_indonesian,
            ),
        ]

        # ─── 2. Clean Stock Footage (Pexels & Pixabay) ───────────────────────────
        stock_q = clean_queries[1] if len(clean_queries) > 1 else primary_query
        tasks.append(self._yt_search.search_pexels(stock_q, max_results=2))
        tasks.append(self._yt_search.search_pixabay(stock_q, max_results=2))

        responses = await asyncio.gather(*tasks, return_exceptions=True)
        for resp in responses:
            if isinstance(resp, Exception) or not resp:
                continue
            if isinstance(resp, list):
                for item in resp:
                    if isinstance(item, dict) and item.get("url") and item["url"] not in seen_urls:
                        seen_urls.add(item["url"])
                        candidates.append(item)

        # ─── 3. Fallback: If fewer than 2 candidates, query YouTube API & Social ──
        if len(candidates) < 2:
            logger.info(
                f"social_search: scene {scene.get('id')} has few candidates ({len(candidates)}), "
                f"triggering YouTube API & social fallbacks..."
            )
            fallback_tasks = [
                self._yt_search.search(
                    query=primary_query_id,
                    max_results=results_per_platform,
                    shorts_only=True,
                    region_code="ID" if is_indonesian else "US",
                    video_definition="high",
                ),
                self.search_ytdlp_platform(
                    query=primary_query,
                    platform="youtube",
                    max_results=results_per_platform,
                    is_indonesian=is_indonesian,
                ),
                self.search_ytdlp_platform(
                    query=primary_query,
                    platform="tiktok",
                    max_results=results_per_platform,
                    is_indonesian=is_indonesian,
                ),
                self._yt_search.search_wikimedia_photos(stock_q, max_results=2),
            ]
            fallback_resps = await asyncio.gather(*fallback_tasks, return_exceptions=True)
            for resp in fallback_resps:
                if isinstance(resp, Exception) or not resp:
                    continue
                if isinstance(resp, list):
                    for item in resp:
                        if isinstance(item, dict) and item.get("url") and item["url"] not in seen_urls:
                            seen_urls.add(item["url"])
                            candidates.append(item)
                elif getattr(resp, "results", None):
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
                                "media_type": "video",
                                "start_timestamp": 0.0,
                                "is_hd": getattr(r, "is_hd", True),
                                "quality": getattr(r, "quality", "HD"),
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
