"""Hermes Trending Service — Multi-Source Trending Topic Discovery & AI Synthesis.

Discovers trending topics across:
1. Google Trends (Daily search trends RSS & Pytrends)
2. YouTube Data API v3 (mostPopular chart per regionCode)
3. TikTok Trending (viral hashtags and short-form queries)
4. Gemini AI Synthesis (curating and synthesizing 3-5 high-retention video concepts)

Supports Indonesia (ID), Worldwide (GLOBAL), and custom country targets.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Geo mapping for Google Trends & YouTube
GEO_MAPPING: dict[str, dict[str, str]] = {
    "ID": {"yt_region": "ID", "gt_geo": "ID", "name": "Indonesia", "lang": "id"},
    "GLOBAL": {"yt_region": "US", "gt_geo": "US", "name": "Worldwide / Global", "lang": "en"},
    "US": {"yt_region": "US", "gt_geo": "US", "name": "United States", "lang": "en"},
    "MY": {"yt_region": "MY", "gt_geo": "MY", "name": "Malaysia", "lang": "ms"},
    "SG": {"yt_region": "SG", "gt_geo": "SG", "name": "Singapore", "lang": "en"},
    "JP": {"yt_region": "JP", "gt_geo": "JP", "name": "Japan", "lang": "ja"},
    "GB": {"yt_region": "GB", "gt_geo": "GB", "name": "United Kingdom", "lang": "en"},
}


@dataclass
class TrendingTopic:
    topic: str
    angle: str
    hook: str
    key_points: list[str] = field(default_factory=list)
    recommended_cta: str = "Follow untuk update berikutnya!"
    search_keywords: list[str] = field(default_factory=list)
    source: str = "Multi-source"
    traffic_estimate: str = ""
    region: str = "ID"
    category: str = "Trending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "angle": self.angle,
            "hook": self.hook,
            "key_points": self.key_points,
            "recommended_cta": self.recommended_cta,
            "search_keywords": self.search_keywords,
            "source": self.source,
            "traffic_estimate": self.traffic_estimate,
            "region": self.region,
            "category": self.category,
        }


class HermesTrendingService:
    """Multi-source trending topics fetcher and AI synthesizer."""

    def __init__(self):
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._cache_ttl = 900  # 15 minutes cache

    # ─── 1. Google Trends (RSS Feed) ──────────────────────────────────────────

    async def fetch_google_trends(self, region: str = "ID", limit: int = 20) -> list[dict[str, Any]]:
        """Fetch daily search trends from Google Trends official RSS feed.

        Extremely fast, reliable, requires no authentication, zero rate limits.
        """
        region_clean = (region or "ID").upper().strip()
        geo = GEO_MAPPING.get(region_clean, {}).get("gt_geo", "ID" if region_clean == "ID" else "US")

        url = f"https://trends.google.com/trending/rss?geo={geo}"
        items: list[dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                        "Accept": "application/rss+xml, application/xml, text/xml, */*",
                    },
                )

            if resp.status_code == 200 and resp.text:
                root = ET.fromstring(resp.text)
                channel = root.find("channel")
                if channel is not None:
                    # Namespace for ht:* elements
                    ns = {"ht": "https://trends.google.com/trending/rss"}
                    for item in channel.findall("item"):
                        title_el = item.find("title")
                        approx_el = item.find("ht:approx_traffic", ns)
                        desc_el = item.find("description")
                        news_title_el = item.find("ht:news_item/ht:news_item_title", ns)
                        news_snippet_el = item.find("ht:news_item/ht:news_item_snippet", ns)

                        title = (title_el.text or "").strip() if title_el is not None else ""
                        if not title:
                            continue

                        approx = (approx_el.text or "").strip() if approx_el is not None else ""
                        desc = (desc_el.text or "").strip() if desc_el is not None else ""
                        news_title = (news_title_el.text or "").strip() if news_title_el is not None else ""
                        news_snippet = (news_snippet_el.text or "").strip() if news_snippet_el is not None else ""

                        items.append({
                            "title": title,
                            "traffic": approx,
                            "summary": news_snippet or desc or news_title,
                            "news_title": news_title,
                            "source": "Google Trends",
                            "region": region_clean,
                        })

                        if len(items) >= limit:
                            break
        except Exception as e:
            logger.warning(f"hermes_trending: Google Trends RSS failed for {region_clean}: {e}")

        # Fallback to pytrends if RSS returned empty
        if not items:
            items = await self._fetch_pytrends_fallback(region_clean, limit)

        return items

    async def _fetch_pytrends_fallback(self, region: str, limit: int) -> list[dict[str, Any]]:
        """Fallback via pytrends library if available."""
        try:
            from pytrends.request import TrendReq

            pn = "indonesia" if region == "ID" else "united_states"
            pytrend = TrendReq(hl="id-ID" if region == "ID" else "en-US", tz=420)
            df = pytrend.trending_searches(pn=pn)
            results: list[dict[str, Any]] = []
            for _, row in df.head(limit).iterrows():
                topic_name = str(row[0]).strip()
                if topic_name:
                    results.append({
                        "title": topic_name,
                        "traffic": "Trending",
                        "summary": f"Top search keyword on Google {region}",
                        "source": "Google Trends (Pytrends)",
                        "region": region,
                    })
            return results
        except Exception as e:
            logger.debug(f"hermes_trending: pytrends fallback failed: {e}")
            return []

    # ─── 2. YouTube Data API v3 (Most Popular Chart) ──────────────────────────

    async def fetch_youtube_trending(self, region: str = "ID", limit: int = 20) -> list[dict[str, Any]]:
        """Fetch trending / most popular videos from YouTube Data API v3."""
        region_clean = (region or "ID").upper().strip()
        yt_region = GEO_MAPPING.get(region_clean, {}).get("yt_region", "ID" if region_clean == "ID" else "US")

        api_key = (
            getattr(settings, "YOUTUBE_API_KEY", "")
            or os.getenv("YOUTUBE_API_KEY", "")
        )

        items: list[dict[str, Any]] = []

        if api_key:
            try:
                async with httpx.AsyncClient(timeout=12) as client:
                    resp = await client.get(
                        "https://www.googleapis.com/youtube/v3/videos",
                        params={
                            "part": "snippet,statistics",
                            "chart": "mostPopular",
                            "regionCode": yt_region,
                            "maxResults": min(limit, 30),
                            "key": api_key,
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        for v in data.get("items", []):
                            snippet = v.get("snippet", {})
                            stats = v.get("statistics", {})
                            title = snippet.get("title", "").strip()
                            if not title:
                                continue
                            items.append({
                                "title": title,
                                "channel": snippet.get("channelTitle", ""),
                                "views": int(stats.get("viewCount", 0)),
                                "tags": snippet.get("tags", [])[:5],
                                "description": snippet.get("description", "")[:200],
                                "source": "YouTube Data API v3",
                                "video_id": v.get("id"),
                                "region": region_clean,
                            })
            except Exception as e:
                logger.warning(f"hermes_trending: YouTube API mostPopular failed: {e}")

        # Fallback if no API key or empty results: use ytsearch for trending queries
        if not items:
            items = await self._fetch_youtube_search_fallback(region_clean, limit)

        return items

    async def _fetch_youtube_search_fallback(self, region: str, limit: int) -> list[dict[str, Any]]:
        """Search YouTube for viral/trending keywords via yt-dlp search."""
        query = "berita viral hari ini" if region == "ID" else "trending viral news"
        cmd = [
            "yt-dlp",
            f"ytsearch{min(limit, 10)}:{query}",
            "--dump-json",
            "--flat-playlist",
            "--no-warnings",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
            items: list[dict[str, Any]] = []
            for line in stdout.decode(errors="replace").strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                    title = d.get("title", "").strip()
                    if title:
                        items.append({
                            "title": title,
                            "channel": d.get("uploader", "") or d.get("channel", ""),
                            "views": d.get("view_count", 0) or 100000,
                            "tags": [],
                            "description": "",
                            "source": "YouTube Search",
                            "video_id": d.get("id", ""),
                            "region": region,
                        })
                except Exception:
                    pass
            return items
        except Exception as e:
            logger.debug(f"hermes_trending: YouTube search fallback failed: {e}")
            return []

    # ─── 3. TikTok Trending ───────────────────────────────────────────────────

    async def fetch_tiktok_trending(self, region: str = "ID", limit: int = 15) -> list[dict[str, Any]]:
        """Fetch trending short-form topics and viral hashtag discussions."""
        query = "tiktok viral indonesia fyp" if region == "ID" else "tiktok trending fyp viral"
        cmd = [
            "yt-dlp",
            f"ytsearch{min(limit, 8)}:{query}",
            "--dump-json",
            "--flat-playlist",
            "--no-warnings",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
            items: list[dict[str, Any]] = []
            for line in stdout.decode(errors="replace").strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                    title = d.get("title", "").strip()
                    if title:
                        items.append({
                            "title": title,
                            "channel": d.get("uploader", ""),
                            "views": d.get("view_count", 0) or 50000,
                            "source": "TikTok Trending",
                            "region": region,
                        })
                except Exception:
                    pass
            return items
        except Exception as e:
            logger.debug(f"hermes_trending: TikTok trending failed: {e}")
            return []

    # ─── 4. Gemini AI Synthesis & Curation ────────────────────────────────────

    async def synthesize_trending_topics(
        self,
        raw_signals: list[dict[str, Any]],
        region: str = "ID",
        count: int = 5,
        niche_focus: str = "",
    ) -> list[TrendingTopic]:
        """Use Gemini AI to analyze raw signals and curate 3-5 viral short-form video concepts."""
        count = max(3, min(count, 5))
        lang_directive = (
            "Bahasa Indonesia (viral, santai namun berwawasan, cocok untuk TikTok & Reels)"
            if region == "ID"
            else "English (high-retention viral storytelling)"
        )

        signals_summary = []
        for i, sig in enumerate(raw_signals[:30], 1):
            title = sig.get("title", "")
            src = sig.get("source", "")
            traffic = sig.get("traffic") or sig.get("views") or ""
            extra = sig.get("summary") or sig.get("news_title") or ""
            signals_summary.append(f"{i}. [{src}] {title} (Traffic/Views: {traffic}) - {extra[:120]}")

        signals_text = "\n".join(signals_summary)

        niche_instruction = ""
        if niche_focus and niche_focus.strip():
            niche_instruction = f"Fokuskan atau saring topik yang relevan dengan niche: '{niche_focus.strip()}'."

        system_prompt = (
            "You are an elite viral content strategist and short-form video director.\n"
            "Analyze the following real-time trending signals gathered across Google Trends, YouTube Data API, and TikTok.\n"
            f"Select exactly {count} most viral, engaging, and discussion-worthy topics for target region: {region}.\n"
            f"{niche_instruction}\n\n"
            "Requirements for each topic:\n"
            "1. 'topic': Clear, catchy topic title.\n"
            "2. 'angle': Unique perspective, controversy, or curiosity angle that sparks comments.\n"
            "3. 'hook': Compelling opening 3-second hook question/statement.\n"
            "4. 'key_points': 3 to 4 concise bullet points explaining what happened and why it matters.\n"
            "5. 'recommended_cta': High-conversion Call-To-Action outro (e.g. 'Komen pendapatmu di bawah!', 'Follow untuk fakta viral berikutnya!').\n"
            "6. 'search_keywords': 3 to 4 visual search queries to find matching footage.\n"
            "7. 'traffic_estimate': Estimated traffic/views (e.g. '500K+ Searches', '1.2M Views').\n"
            "8. 'category': e.g. 'Tech', 'Entertainment', 'News', 'Culture', 'Finance', 'Unique Fact'.\n\n"
            f"Language directive: {lang_directive}.\n"
            "Output VALID JSON only matching the schema:\n"
            "{\n"
            '  "topics": [\n'
            '    {\n'
            '      "topic": "...",\n'
            '      "angle": "...",\n'
            '      "hook": "...",\n'
            '      "key_points": ["...", "..."],\n'
            '      "recommended_cta": "...",\n'
            '      "search_keywords": ["...", "..."],\n'
            '      "traffic_estimate": "...",\n'
            '      "category": "..."\n'
            '    }\n'
            '  ]\n'
            "}"
        )

        user_prompt = f"Trending Signals:\n{signals_text}\n\nCurate top {count} video concepts:"

        raw_json = await self._call_gemini_json(system_prompt, user_prompt)
        if not raw_json:
            return self._create_fallback_topics(raw_signals, region, count)

        try:
            data = json.loads(raw_json)
            if isinstance(data, list):
                topics_data = data
            elif isinstance(data, dict):
                topics_data = data.get("topics") or data.get("items") or [data]
            else:
                topics_data = []

            results: list[TrendingTopic] = []
            for t in topics_data[:count]:
                if not isinstance(t, dict):
                    continue
                results.append(
                    TrendingTopic(
                        topic=t.get("topic", "Topik Viral Hari Ini"),
                        angle=t.get("angle", "Pembahasan menarik yang lagi ramai dibicarakan"),
                        hook=t.get("hook", "Kamu sudah dengar kabar yang lagi viral ini belum?"),
                        key_points=t.get("key_points", []),
                        recommended_cta=t.get("recommended_cta", "Follow untuk update berikutnya!"),
                        search_keywords=t.get("search_keywords", []),
                        source="AI Synthesis (Google + YouTube + TikTok)",
                        traffic_estimate=t.get("traffic_estimate", "Trending"),
                        region=region,
                        category=t.get("category", "Trending"),
                    )
                )
            if results:
                return results
        except Exception as e:
            logger.warning(f"hermes_trending: JSON parse error in Gemini response: {e}")

        return self._create_fallback_topics(raw_signals, region, count)

    def _create_fallback_topics(
        self,
        raw_signals: list[dict[str, Any]],
        region: str,
        count: int,
    ) -> list[TrendingTopic]:
        """Create structured topics directly from raw signals if Gemini LLM fails."""
        results: list[TrendingTopic] = []
        for sig in raw_signals[:count]:
            title = sig.get("title", "")
            traffic = str(sig.get("traffic") or sig.get("views") or "Trending")
            src = sig.get("source", "Google/YouTube")
            hook = (
                f"Ini dia yang lagi ramai banget dibahas hari ini: {title}!"
                if region == "ID"
                else f"Here is the story taking over the internet today: {title}!"
            )
            results.append(
                TrendingTopic(
                    topic=title,
                    angle=f"Fakta dan perkembangan terkini seputar {title}",
                    hook=hook,
                    key_points=[
                        f"Pembahasan viral dari {src}",
                        f"Mendapat sorotan tinggi dengan estimasi {traffic}",
                        "Reaksi warganet dan netizen di media sosial",
                    ],
                    recommended_cta="Komen pendapatmu di bawah dan follow untuk info terbaru!",
                    search_keywords=[title, f"{title} viral", f"{title} news"],
                    source=src,
                    traffic_estimate=traffic,
                    region=region,
                    category="Trending",
                )
            )
        return results

    async def _call_gemini_json(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """Call Gemini model via Direct API or 9Router."""
        from src.infrastructure.system_config_store import get_gemini_api_keys

        keys = get_gemini_api_keys()
        if not keys and getattr(settings, "GEMINI_API_KEY", ""):
            keys = [settings.GEMINI_API_KEY]

        if not keys:
            logger.warning("hermes_trending: No Gemini API keys configured.")
            return None

        models = [
            "gemini-2.5-flash",
            "gemini-3.8-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
        ]

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}],
                }
            ],
            "generationConfig": {
                "temperature": 0.5,
                "responseMimeType": "application/json",
            },
        }

        for model in models:
            for key in keys[:3]:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                try:
                    async with httpx.AsyncClient(timeout=25) as client:
                        resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                return parts[0].get("text", "")
                except Exception:
                    continue

        return None

    # ─── 5. Main Aggregated Method ────────────────────────────────────────────

    async def get_trending_topics(
        self,
        region: str = "ID",
        count: int = 5,
        sources: Optional[list[str]] = None,
        niche_focus: str = "",
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """Get curated 3-5 trending video topics for the target region.

        Combines Google Trends, YouTube, and TikTok, then curates with Gemini.
        """
        region_clean = (region or "ID").upper().strip()
        count = max(3, min(count, 5))
        cache_key = f"{region_clean}:{count}:{niche_focus.strip()}"

        now = time.time()
        if use_cache and cache_key in self._cache:
            ts, cached_list = self._cache[cache_key]
            if now - ts < self._cache_ttl:
                return cached_list

        selected_sources = [s.lower().strip() for s in (sources or ["google", "youtube", "tiktok"])]

        tasks = []
        if any("google" in s for s in selected_sources):
            tasks.append(self.fetch_google_trends(region=region_clean))
        if any("youtube" in s for s in selected_sources):
            tasks.append(self.fetch_youtube_trending(region=region_clean))
        if any("tiktok" in s for s in selected_sources):
            tasks.append(self.fetch_tiktok_trending(region=region_clean))

        raw_lists = await asyncio.gather(*tasks, return_exceptions=True)
        aggregated_signals: list[dict[str, Any]] = []
        for res in raw_lists:
            if isinstance(res, list):
                aggregated_signals.extend(res)

        if not aggregated_signals:
            # Fallback default trending signals
            aggregated_signals = [
                {"title": "Perkembangan AI dan Robotika Terbaru", "source": "Tech News", "traffic": "High"},
                {"title": "Tips Finansial dan Investasi Generasi Muda", "source": "Finance", "traffic": "High"},
                {"title": "Fakta Sains Unik Luar Angkasa dan Bumi", "source": "Science", "traffic": "High"},
                {"title": "Kisah Inspiratif dan Motivasi Hidup", "source": "Inspiration", "traffic": "High"},
                {"title": "Misteri dan Sejarah Dunia yang Belum Terungkap", "source": "History", "traffic": "High"},
            ]

        curated = await self.synthesize_trending_topics(
            raw_signals=aggregated_signals,
            region=region_clean,
            count=count,
            niche_focus=niche_focus,
        )

        dict_results = [t.to_dict() for t in curated]
        self._cache[cache_key] = (now, dict_results)
        return dict_results


# Singleton instance
hermes_trending_service = HermesTrendingService()
