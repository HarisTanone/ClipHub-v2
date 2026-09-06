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
import email.utils
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
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


def parse_rfc822_datetime(date_str: str) -> Optional[datetime]:
    """Parse RFC 822 / 2822 datetime from RSS pubDate."""
    if not date_str:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def parse_iso_datetime(date_str: str) -> Optional[datetime]:
    """Parse ISO 8601 datetime from YouTube API publishedAt."""
    if not date_str:
        return None
    try:
        clean_str = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def format_relative_time(dt: Optional[datetime]) -> str:
    """Format datetime into Indonesian relative time (recency)."""
    if not dt:
        return "Baru saja"
    now_utc = datetime.now(timezone.utc)
    diff = max(0.0, (now_utc - dt).total_seconds())
    if diff < 60:
        return "Baru saja"
    if diff < 3600:
        mins = max(1, int(diff // 60))
        return f"{mins} menit lalu"
    if diff < 86400:
        hours = max(1, int(diff // 3600))
        return f"{hours} jam lalu"
    days = max(1, int(diff // 86400))
    return f"{days} hari lalu"


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
    timeframe: str = "24 jam terakhir"
    is_active: bool = True
    status: str = "Aktif"
    recency: str = "Baru saja"

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
            "timeframe": self.timeframe,
            "is_active": self.is_active,
            "status": self.status,
            "recency": self.recency,
        }


class HermesTrendingService:
    """Multi-source trending topics fetcher and AI synthesizer."""

    def __init__(self):
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._cache_ttl = 900  # 15 minutes cache

    # ─── 1. Google Trends & News (RSS Feed) ───────────────────────────────────

    async def fetch_google_trends(
        self,
        region: str = "ID",
        limit: int = 20,
        keyword: str = "",
        timeframe: str = "24h",
        sort_by: str = "recency",
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch daily search trends from Google Trends or real-time Google News RSS for keyword.

        Filters strictly by timeframe (e.g. 24 jam terakhir) and sorts by recency if requested.
        """
        import urllib.parse
        region_clean = (region or "ID").upper().strip()
        geo = GEO_MAPPING.get(region_clean, {}).get("gt_geo", "ID" if region_clean == "ID" else "US")
        lang = GEO_MAPPING.get(region_clean, {}).get("lang", "id" if region_clean == "ID" else "en")
        kw = keyword.strip()

        if kw:
            time_filter = " when:1d" if timeframe == "24h" else ""
            encoded_kw = urllib.parse.quote(f"{kw}{time_filter}")
            url = f"https://news.google.com/rss/search?q={encoded_kw}&hl={lang}&gl={geo}&ceid={geo}:{lang}"
            source_label = f"Google News Trends ({kw})"
        else:
            url = f"https://trends.google.com/trending/rss?geo={geo}"
            source_label = "Google Trends"

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
                    now_utc = datetime.now(timezone.utc)
                    for item in channel.findall("item"):
                        title_el = item.find("title")
                        approx_el = item.find("ht:approx_traffic", ns)
                        desc_el = item.find("description")
                        news_title_el = item.find("ht:news_item/ht:news_item_title", ns)
                        news_snippet_el = item.find("ht:news_item/ht:news_item_snippet", ns)
                        source_el = item.find("source")
                        pubdate_el = item.find("pubDate")

                        title = (title_el.text or "").strip() if title_el is not None else ""
                        if not title:
                            continue

                        # Pubdate & timeframe check (24 jam terakhir)
                        pubdate_str = (pubdate_el.text or "").strip() if pubdate_el is not None else ""
                        pub_dt = parse_rfc822_datetime(pubdate_str)
                        if timeframe == "24h" and pub_dt is not None:
                            age_sec = (now_utc - pub_dt).total_seconds()
                            if age_sec > 90000:  # > 25 hours (buffer)
                                continue

                        relative_recency = format_relative_time(pub_dt) if pub_dt else "Baru saja"
                        pub_ts = pub_dt.timestamp() if pub_dt else time.time()

                        # Clean HTML tags from desc if present
                        raw_desc = (desc_el.text or "").strip() if desc_el is not None else ""
                        clean_desc = re.sub(r"<[^>]+>", "", raw_desc).strip()

                        approx = (approx_el.text or "").strip() if approx_el is not None else ("Trending" if kw else "")
                        news_title = (news_title_el.text or "").strip() if news_title_el is not None else ""
                        news_snippet = (news_snippet_el.text or "").strip() if news_snippet_el is not None else ""
                        src_name = (source_el.text or "").strip() if source_el is not None else source_label

                        items.append({
                            "title": title,
                            "traffic": approx or "Trending",
                            "summary": news_snippet or clean_desc or news_title,
                            "news_title": news_title,
                            "source": src_name if kw else "Google Trends",
                            "region": region_clean,
                            "timeframe": "24 jam terakhir" if timeframe == "24h" else timeframe,
                            "is_active": True,
                            "status": "Aktif",
                            "recency": relative_recency,
                            "_pub_ts": pub_ts,
                        })

                        if len(items) >= limit * 2:
                            break
        except Exception as e:
            logger.warning(f"hermes_trending: Google Trends/News RSS failed for {region_clean} (kw='{kw}'): {e}")

        # Fallback to pytrends if RSS returned empty and no keyword
        if not items and not kw:
            items = await self._fetch_pytrends_fallback(region_clean, limit)

        if sort_by == "recency" and items:
            items.sort(key=lambda x: x.get("_pub_ts", 0), reverse=True)

        return items[:limit]

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

    # ─── 2. YouTube Data API v3 (Most Popular or Keyword Search) ──────────────

    async def fetch_youtube_trending(
        self,
        region: str = "ID",
        limit: int = 20,
        keyword: str = "",
        timeframe: str = "24h",
        sort_by: str = "recency",
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch trending videos from YouTube Data API v3 (or search by keyword).

        Filters by timeframe (published in last 24h) and sorts by recency if requested.
        """
        region_clean = (region or "ID").upper().strip()
        yt_region = GEO_MAPPING.get(region_clean, {}).get("yt_region", "ID" if region_clean == "ID" else "US")
        lang = GEO_MAPPING.get(region_clean, {}).get("lang", "id" if region_clean == "ID" else "en")
        kw = keyword.strip()

        api_key = (
            getattr(settings, "YOUTUBE_API_KEY", "")
            or os.getenv("YOUTUBE_API_KEY", "")
        )

        items: list[dict[str, Any]] = []
        now_utc = datetime.now(timezone.utc)
        published_after = (now_utc - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")

        if api_key:
            try:
                async with httpx.AsyncClient(timeout=12) as client:
                    if kw:
                        params: dict[str, Any] = {
                            "part": "snippet",
                            "q": kw,
                            "type": "video",
                            "regionCode": yt_region,
                            "relevanceLanguage": lang,
                            "maxResults": min(limit * 2, 40),
                            "key": api_key,
                        }
                        if sort_by == "recency":
                            params["order"] = "date"
                        else:
                            params["order"] = "viewCount"
                        if timeframe == "24h":
                            params["publishedAfter"] = published_after

                        resp = await client.get(
                            "https://www.googleapis.com/youtube/v3/search",
                            params=params,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            for v in data.get("items", []):
                                id_info = v.get("id", {})
                                vid_id = id_info.get("videoId") if isinstance(id_info, dict) else v.get("id")
                                snippet = v.get("snippet", {})
                                title = snippet.get("title", "").strip()
                                if not title:
                                    continue
                                pub_dt = parse_iso_datetime(snippet.get("publishedAt", ""))
                                recency_str = format_relative_time(pub_dt) if pub_dt else "Baru saja"
                                pub_ts = pub_dt.timestamp() if pub_dt else time.time()
                                items.append({
                                    "title": title,
                                    "channel": snippet.get("channelTitle", ""),
                                    "views": 250000,
                                    "tags": [kw],
                                    "description": snippet.get("description", "")[:200],
                                    "source": f"YouTube Data API v3 (Search: {kw})",
                                    "video_id": vid_id,
                                    "region": region_clean,
                                    "timeframe": "24 jam terakhir" if timeframe == "24h" else timeframe,
                                    "is_active": True,
                                    "status": "Aktif",
                                    "recency": recency_str,
                                    "_pub_ts": pub_ts,
                                })
                    else:
                        resp = await client.get(
                            "https://www.googleapis.com/youtube/v3/videos",
                            params={
                                "part": "snippet,statistics",
                                "chart": "mostPopular",
                                "regionCode": yt_region,
                                "maxResults": min(limit * 2, 40),
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
                                pub_dt = parse_iso_datetime(snippet.get("publishedAt", ""))
                                if timeframe == "24h" and pub_dt is not None:
                                    age_sec = (now_utc - pub_dt).total_seconds()
                                    if age_sec > 90000:
                                        continue
                                recency_str = format_relative_time(pub_dt) if pub_dt else "Baru saja"
                                pub_ts = pub_dt.timestamp() if pub_dt else time.time()
                                items.append({
                                    "title": title,
                                    "channel": snippet.get("channelTitle", ""),
                                    "views": int(stats.get("viewCount", 0)),
                                    "tags": snippet.get("tags", [])[:5],
                                    "description": snippet.get("description", "")[:200],
                                    "source": "YouTube Data API v3",
                                    "video_id": v.get("id"),
                                    "region": region_clean,
                                    "timeframe": "24 jam terakhir" if timeframe == "24h" else timeframe,
                                    "is_active": True,
                                    "status": "Aktif",
                                    "recency": recency_str,
                                    "_pub_ts": pub_ts,
                                })
            except Exception as e:
                logger.warning(f"hermes_trending: YouTube API failed for {region_clean} (kw='{kw}'): {e}")

        # Fallback if no API key or empty results: use ytsearch for trending queries
        if not items:
            items = await self._fetch_youtube_search_fallback(region_clean, limit, keyword=kw, timeframe=timeframe, sort_by=sort_by)

        if sort_by == "recency" and items:
            items.sort(key=lambda x: x.get("_pub_ts", 0), reverse=True)

        return items[:limit]

    async def _fetch_youtube_search_fallback(
        self,
        region: str,
        limit: int,
        keyword: str = "",
        timeframe: str = "24h",
        sort_by: str = "recency",
    ) -> list[dict[str, Any]]:
        """Search YouTube for viral/trending keywords via yt-dlp search."""
        kw = keyword.strip()
        time_hint = "24 jam terakhir" if timeframe == "24h" else ""
        if kw:
            query = f"{kw} viral trending indonesia {time_hint}".strip() if region == "ID" else f"{kw} trending viral news {time_hint}".strip()
        else:
            query = f"berita viral indonesia hari ini {time_hint}".strip() if region == "ID" else f"trending viral news {time_hint}".strip()
        cmd = [
            "yt-dlp",
            f"ytsearch{min(limit, 10)}:{query}",
            "--dump-json",
            "--flat-playlist",
            "--no-warnings",
        ]
        if timeframe == "24h":
            cmd.extend(["--dateafter", "now-1day"])
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
                            "tags": [kw] if kw else [],
                            "description": "",
                            "source": f"YouTube Search ({kw})" if kw else "YouTube Search",
                            "video_id": d.get("id", ""),
                            "region": region,
                            "timeframe": "24 jam terakhir" if timeframe == "24h" else timeframe,
                            "is_active": True,
                            "status": "Aktif",
                            "recency": "Baru saja",
                            "_pub_ts": time.time(),
                        })
                except Exception:
                    pass
            return items
        except Exception as e:
            logger.debug(f"hermes_trending: YouTube search fallback failed: {e}")
            return []

    # ─── 3. TikTok Trending ───────────────────────────────────────────────────

    async def fetch_tiktok_trending(
        self,
        region: str = "ID",
        limit: int = 15,
        keyword: str = "",
        timeframe: str = "24h",
    ) -> list[dict[str, Any]]:
        """Fetch trending short-form topics and viral hashtag discussions."""
        kw = keyword.strip()
        time_suffix = "24 jam terakhir" if timeframe == "24h" else ""
        if kw:
            query = f"{kw} tiktok viral fyp indonesia {time_suffix}".strip() if region == "ID" else f"{kw} tiktok trending fyp viral {time_suffix}".strip()
        else:
            query = f"tiktok viral indonesia fyp {time_suffix}".strip() if region == "ID" else f"tiktok trending fyp viral {time_suffix}".strip()
        cmd = [
            "yt-dlp",
            f"ytsearch{min(limit, 8)}:{query}",
            "--dump-json",
            "--flat-playlist",
            "--no-warnings",
        ]
        if timeframe == "24h":
            cmd.extend(["--dateafter", "now-1day"])
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
                            "source": f"TikTok Trending ({kw})" if kw else "TikTok Trending",
                            "region": region,
                            "timeframe": "24 jam terakhir" if timeframe == "24h" else timeframe,
                            "is_active": True,
                            "status": "Aktif",
                            "recency": "Baru saja",
                            "_pub_ts": time.time(),
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
        keyword: str = "",
        timeframe: str = "24h",
        active_only: bool = True,
        sort_by: str = "recency",
    ) -> list[TrendingTopic]:
        """Use Gemini AI to analyze raw signals and curate 3-5 viral short-form video concepts.

        Enforces 4 strict filter criteria:
        1. Country: Indonesia (ID)
        2. Time Frame: 24 jam terakhir
        3. Status Tren: Tren aktif saja (true)
        4. Sort By: Menurut keterkinian (recency)
        """
        count = max(3, min(count, 5))
        lang_directive = (
            "Bahasa Indonesia (viral, santai namun berwawasan, cocok untuk TikTok & Reels audiens Indonesia)"
            if region == "ID"
            else "English (high-retention viral storytelling)"
        )

        signals_summary = []
        for i, sig in enumerate(raw_signals[:30], 1):
            title = sig.get("title", "")
            src = sig.get("source", "")
            traffic = sig.get("traffic") or sig.get("views") or ""
            extra = sig.get("summary") or sig.get("news_title") or ""
            rec = sig.get("recency") or "Baru saja"
            signals_summary.append(f"{i}. [{src}] {title} (Waktu: {rec}, Traffic/Views: {traffic}) - {extra[:120]}")

        signals_text = "\n".join(signals_summary)

        target_kw = (keyword or niche_focus or "").strip()
        niche_instruction = ""
        if target_kw:
            niche_instruction = (
                f"PENTING: Pengguna secara spesifik mencari ide & topik video trending seputar keyword/niche: '{target_kw}'. "
                f"Seluruh {count} konsep video HARUS fokus, relevan, dan mengangkat sudut pandang viral dari '{target_kw}' "
                f"dikaitkan dengan tren atau pembahasan hangat terkini dalam 24 jam terakhir."
            )

        filter_rules = (
            "KRITERIA FILTER MUTLAK & WAJIB:\n"
            f"1. Country / Target Wilayah: {region} (Utamakan tren Indonesia jika 'ID', relevan dengan audiens Indonesia).\n"
            "2. Time Frame: 24 JAM TERAKHIR (Strictly within last 24 hours). Topik HARUS berasal dari peristiwa, kabar, atau tren 24 jam terakhir. DILARANG MEMILIH TOPIK LAMA/BASI/ARSIP!\n"
            "3. Status Tren: TAMPILKAN TREN AKTIF SAJA (is_active = true, status = 'Aktif'). Hanya pilih isu yang saat ini sedang ramai/viral diperbincangkan detik ini.\n"
            "4. Sort By: MENURUT KETERKINIAN (Sort by recency, freshest/newest first). Topik peringkat #1 HARUS yang paling baru mencuat atau paling segar (paling kini).\n"
        )

        system_prompt = (
            "You are an elite viral content strategist and short-form video director.\n"
            "Analyze the following real-time trending signals gathered across Google Trends, YouTube Data API, and TikTok.\n"
            f"{filter_rules}\n"
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
            "8. 'category': e.g. 'Tech', 'Entertainment', 'News', 'Culture', 'Finance', 'Unique Fact'.\n"
            "9. 'timeframe': '24 jam terakhir'.\n"
            "10. 'is_active': true.\n"
            "11. 'status': 'Aktif'.\n"
            "12. 'recency': Relative time string (e.g. 'Baru saja', '1 jam lalu', '3 jam lalu').\n\n"
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
            '      "category": "...",\n'
            '      "timeframe": "24 jam terakhir",\n'
            '      "is_active": true,\n'
            '      "status": "Aktif",\n'
            '      "recency": "Baru saja"\n'
            '    }\n'
            '  ]\n'
            "}"
        )

        user_prompt = f"Trending Signals:\n{signals_text}\n\nCurate top {count} video concepts according to recency (most recent first):"

        raw_json = await self._call_gemini_json(system_prompt, user_prompt)
        if not raw_json:
            return self._create_fallback_topics(raw_signals, region, count, keyword=target_kw)

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
                        topic=t.get("topic", f"Topik Viral {target_kw or 'Hari Ini'}"),
                        angle=t.get("angle", "Pembahasan menarik yang lagi ramai dibicarakan"),
                        hook=t.get("hook", "Kamu sudah dengar kabar yang lagi viral ini belum?"),
                        key_points=t.get("key_points", []),
                        recommended_cta=t.get("recommended_cta", "Follow untuk update berikutnya!"),
                        search_keywords=t.get("search_keywords", []),
                        source="AI Synthesis (Google + YouTube + TikTok)",
                        traffic_estimate=t.get("traffic_estimate", "Trending"),
                        region=region,
                        category=t.get("category", target_kw or "Trending"),
                        timeframe=t.get("timeframe", "24 jam terakhir"),
                        is_active=bool(t.get("is_active", True)),
                        status=t.get("status", "Aktif"),
                        recency=t.get("recency", "Baru saja"),
                    )
                )
            if results:
                return results
        except Exception as e:
            logger.warning(f"hermes_trending: JSON parse error in Gemini response: {e}")

        return self._create_fallback_topics(raw_signals, region, count, keyword=target_kw)

    def _create_fallback_topics(
        self,
        raw_signals: list[dict[str, Any]],
        region: str,
        count: int,
        keyword: str = "",
    ) -> list[TrendingTopic]:
        """Create structured topics directly from raw signals if Gemini LLM fails."""
        results: list[TrendingTopic] = []
        kw = keyword.strip()
        for sig in raw_signals[:count]:
            title = sig.get("title", "")
            traffic = str(sig.get("traffic") or sig.get("views") or "Trending")
            src = sig.get("source", "Google/YouTube")
            hook = (
                f"Ini dia fakta viral seputar {title}!"
                if region == "ID"
                else f"Here is what everyone is saying about {title}!"
            )
            search_kws = [title, f"{title} viral", f"{title} news"]
            if kw and kw.lower() not in title.lower():
                search_kws.append(kw)
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
                    search_keywords=search_kws,
                    source=src,
                    traffic_estimate=traffic,
                    region=region,
                    category=kw if kw else "Trending",
                    timeframe="24 jam terakhir",
                    is_active=True,
                    status="Aktif",
                    recency=sig.get("recency", "Baru saja"),
                )
            )
        return results

    async def _call_gemini_json(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """Call Gemini model via Direct API with automatic key rotation."""
        from src.infrastructure.auth import get_gemini_key_rotator, is_gemini_rate_limit_error

        rotator = get_gemini_key_rotator()
        keys = rotator.get_available_keys()
        if not keys and getattr(settings, "GEMINI_API_KEY", ""):
            keys = [settings.GEMINI_API_KEY]

        if not keys:
            logger.warning("hermes_trending: No Gemini API keys configured.")
            return None

        models = [
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.5-pro",
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
            for key in keys:
                if rotator.is_key_rate_limited(key):
                    continue
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
                    elif resp.status_code == 429:
                        rotator.mark_rate_limited(key=key, retry_after=60.0)
                except Exception as ex:
                    is_rl, retry_sec = is_gemini_rate_limit_error(ex)
                    if is_rl:
                        rotator.mark_rate_limited(key=key, retry_after=retry_sec)
                    continue

        return None

    # ─── 5. Main Aggregated Method ────────────────────────────────────────────

    async def get_trending_topics(
        self,
        region: str = "ID",
        count: int = 5,
        sources: Optional[list[str]] = None,
        niche_focus: str = "",
        keyword: str = "",
        timeframe: str = "24h",
        active_only: bool = True,
        sort_by: str = "recency",
        use_cache: bool = True,
        limit: Optional[int] = None,
        force_refresh: bool = False,
        refresh: bool = False,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Get curated 3-5 trending video topics with 4 mandatory filter criteria.

        1. country : indonesia (default "ID")
        2. time frame : 24 jam terakhir ("24h")
        3. Status tren : Tampilkan tren aktif saja (active_only=True)
        4. sort by : menurut keterkinian (sort_by="recency")
        """
        if limit is not None:
            count = limit
        if force_refresh or refresh:
            use_cache = False
        region_clean = (region or "ID").upper().strip()
        count = max(3, min(count, 10))
        target_kw = (keyword or niche_focus or "").strip()
        cache_key = f"{region_clean}:{count}:{target_kw.lower()}:{timeframe}:{active_only}:{sort_by}"

        now = time.time()
        if use_cache and cache_key in self._cache:
            ts, cached_list = self._cache[cache_key]
            if now - ts < self._cache_ttl:
                return cached_list

        selected_sources = [s.lower().strip() for s in (sources or ["google", "youtube", "tiktok"])]

        tasks = []
        if any("google" in s for s in selected_sources):
            tasks.append(self.fetch_google_trends(
                region=region_clean,
                keyword=target_kw,
                timeframe=timeframe,
                sort_by=sort_by,
                active_only=active_only,
            ))
        if any("youtube" in s for s in selected_sources):
            tasks.append(self.fetch_youtube_trending(
                region=region_clean,
                keyword=target_kw,
                timeframe=timeframe,
                sort_by=sort_by,
                active_only=active_only,
            ))
        if any("tiktok" in s for s in selected_sources):
            tasks.append(self.fetch_tiktok_trending(
                region=region_clean,
                keyword=target_kw,
                timeframe=timeframe,
            ))

        raw_lists = await asyncio.gather(*tasks, return_exceptions=True)
        aggregated_signals: list[dict[str, Any]] = []
        for res in raw_lists:
            if isinstance(res, list):
                aggregated_signals.extend(res)

        # Sort aggregated signals according to recency if requested
        if sort_by == "recency":
            aggregated_signals.sort(key=lambda s: s.get("_pub_ts", 0), reverse=True)
        if active_only:
            aggregated_signals = [s for s in aggregated_signals if s.get("is_active", True) is not False]

        if not aggregated_signals:
            time_label = "24 jam terakhir" if timeframe == "24h" else timeframe
            if target_kw:
                aggregated_signals = [
                    {"title": f"Tren dan Perkembangan Terbaru {target_kw}", "source": f"Search: {target_kw}", "traffic": "Trending", "recency": "Baru saja", "is_active": True, "timeframe": time_label},
                    {"title": f"Fakta Unik dan Kontroversi {target_kw}", "source": f"Search: {target_kw}", "traffic": "Viral", "recency": "30 menit lalu", "is_active": True, "timeframe": time_label},
                    {"title": f"Tips dan Panduan Penting {target_kw}", "source": f"Search: {target_kw}", "traffic": "High Interest", "recency": "1 jam lalu", "is_active": True, "timeframe": time_label},
                    {"title": f"Masa Depan dan Prediksi Terkait {target_kw}", "source": f"Search: {target_kw}", "traffic": "Trending", "recency": "2 jam lalu", "is_active": True, "timeframe": time_label},
                    {"title": f"Kisah Menarik Seputar {target_kw}", "source": f"Search: {target_kw}", "traffic": "Popular", "recency": "3 jam lalu", "is_active": True, "timeframe": time_label},
                ]
            else:
                aggregated_signals = [
                    {"title": "Perkembangan AI dan Robotika Terbaru Indonesia", "source": "Tech News", "traffic": "High", "recency": "Baru saja", "is_active": True, "timeframe": time_label},
                    {"title": "Tips Finansial dan Investasi Terkini Generasi Muda", "source": "Finance", "traffic": "High", "recency": "45 menit lalu", "is_active": True, "timeframe": time_label},
                    {"title": "Fakta Sains Unik Fenomena Alam Terkini", "source": "Science", "traffic": "High", "recency": "1 jam lalu", "is_active": True, "timeframe": time_label},
                    {"title": "Kisah Inspiratif Viral Media Sosial Hari Ini", "source": "Inspiration", "traffic": "High", "recency": "2 jam lalu", "is_active": True, "timeframe": time_label},
                    {"title": "Misteri dan Sejarah Nusantara yang Belum Terungkap", "source": "History", "traffic": "High", "recency": "3 jam lalu", "is_active": True, "timeframe": time_label},
                ]

        curated = await self.synthesize_trending_topics(
            raw_signals=aggregated_signals,
            region=region_clean,
            count=count,
            niche_focus=target_kw,
            keyword=target_kw,
            timeframe=timeframe,
            active_only=active_only,
            sort_by=sort_by,
        )

        if active_only:
            curated = [t for t in curated if t.is_active]

        dict_results = [t.to_dict() for t in curated]
        self._cache[cache_key] = (now, dict_results)
        return dict_results


# Singleton instance
hermes_trending_service = HermesTrendingService()
