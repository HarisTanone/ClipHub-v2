"""ClipScout API client — multi-source video search for B-roll footage.

Primary source for B-roll footage. Searches Pexels, Pixabay, YouTube CC,
and YouTube protected videos in a single API call. Returns ranked video
candidates for AI selection.

Fallback: If ClipScout fails after max retries, the pipeline falls through
to the legacy AssetFetcher (individual Pexels/Pixabay API calls).
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional


import httpx

from src.config import settings
from src.domain.entities import BRollSuggestion, VideoCandidate
from src.domain.interfaces import IClipScoutClient

logger = logging.getLogger(__name__)


class ClipScoutUnavailableError(RuntimeError):
    """Raised when ClipScout API is unreachable after max retries."""


class ClipScoutClient(IClipScoutClient):
    """HTTP client for ClipScout multi-source video search API.

    Features:
    - Retry 2x with 3s delay between attempts
    - Timeout 15s per request
    - Parses response into VideoCandidate dataclass list
    - Supports multi-segment batch requests
    """

    def __init__(self):
        self._base_url = settings.CLIPSCOUT_API_URL
        self._timeout = settings.CLIPSCOUT_TIMEOUT
        self._max_retries = settings.CLIPSCOUT_MAX_RETRIES
        self._enabled_sources = [
            s.strip() for s in settings.CLIPSCOUT_ENABLED_SOURCES.split(",") if s.strip()
        ]

    async def search(self, segments: list[dict], orientation: str = "vertical") -> dict:
        """Search ClipScout API with segments.

        Args:
            segments: List of segment dicts with keys: id, text, topic, searchQueries
            orientation: Video orientation ("vertical" for 9:16)

        Returns:
            Raw response dict from ClipScout API.

        Raises:
            ClipScoutUnavailableError: After max_retries failed attempts.
        """
        payload = {
            "segments": segments,
            "orientation": orientation,
            "enabledSources": self._enabled_sources,
            "deductCreditsPerSegment": False,
            "creditsToCharge": 0,
        }

        last_error: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        self._base_url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    response.raise_for_status()
                    data = response.json()
                    logger.info(
                        f"clipscout: search success (attempt {attempt + 1}), "
                        f"{len(segments)} segments, "
                        f"{sum(len(r.get('videos', [])) for r in data.get('results', []))} videos"
                    )
                    return data

            except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = exc
                logger.warning(
                    f"clipscout: attempt {attempt + 1}/{self._max_retries} failed: {exc}"
                )
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(3)

        raise ClipScoutUnavailableError(
            f"ClipScout API failed after {self._max_retries} attempts: {last_error}"
        )

    def parse_video_candidates(self, raw_response: dict) -> dict[str, list[VideoCandidate]]:
        """Parse ClipScout response into VideoCandidate objects grouped by segment ID.

        Args:
            raw_response: Raw JSON response from ClipScout API.

        Returns:
            Dict mapping segment_id -> list of VideoCandidate.
        """
        results: dict[str, list[VideoCandidate]] = {}

        for result in raw_response.get("results", []):
            segment_id = str(result.get("segmentId", ""))
            candidates: list[VideoCandidate] = []

            for video in result.get("videos", []):
                try:
                    candidate = VideoCandidate(
                        id=str(video.get("id", "")),
                        title=str(video.get("title", ""))[:200],
                        thumbnail_url=str(video.get("thumbnailUrl", "")),
                        source_url=str(video.get("sourceUrl", "")),
                        embed_url=str(video.get("embedUrl", "")),
                        platform=str(video.get("platform", "unknown")),
                        license=str(video.get("license", "standard")),
                        duration_seconds=int(video.get("durationSeconds", 0)),
                        start_timestamp=int(video.get("startTimestamp", 0)),
                        relevance_score=float(video.get("relevanceScore", 0.0)),
                        transcript_snippet=str(video.get("transcriptSnippet", ""))[:500],
                        transcript_reason=str(video.get("transcriptReason", ""))[:300],
                        channel_or_author=str(video.get("channelOrAuthor", "")),
                    )
                    candidates.append(candidate)
                except (TypeError, ValueError) as exc:
                    logger.warning(f"clipscout: skipping malformed video entry: {exc}")
                    continue

            if candidates:
                results[segment_id] = candidates

        return results


# Abstract/mood poison → kill or rewrite for stock search accuracy.
_KEYWORD_STOP = {
    "dramatic", "cinematic", "beautiful", "success", "lifestyle",
    "epic", "mood", "vibes", "aesthetic", "background", "viral",
    "amazing", "best", "top", "cool", "nice", "great", "awesome",
}
# ID/EN abstract topic → concrete English stock query (1:1 visual).
_TOPIC_SYNONYMS: dict[str, str] = {
    "rupiah": "indonesian rupiah banknotes",
    "uang": "cash banknotes counting hands",
    "money": "cash banknotes counting hands",
    "dompet": "empty wallet hands close up",
    "wallet": "empty wallet hands close up",
    "bbm": "fuel nozzle pumping gas car",
    "bensin": "fuel nozzle pumping gas car",
    "fuel": "fuel nozzle pumping gas car",
    "minyak": "oil pump jack working sunset",
    "oil": "oil pump jack working sunset",
    "inflasi": "price tag grocery shopping inflation",
    "inflation": "price tag grocery shopping inflation",
    "ekonomi": "stock market chart trading screen",
    "economy": "stock market chart trading screen",
    "kurs": "usd idr currency exchange chart",
    "currency": "usd idr currency exchange chart",
    "bank": "bank building exterior modern",
    "saham": "stock market chart candlestick",
    "stock": "stock market chart candlestick",
    "gaji": "paycheck salary envelope cash",
    "salary": "paycheck salary envelope cash",
    "hutang": "debt bill unpaid invoice stack",
    "debt": "debt bill unpaid invoice stack",
    "emas": "gold bars bullion close up",
    "gold": "gold bars bullion close up",
    "crypto": "bitcoin cryptocurrency coin close up",
    "bitcoin": "bitcoin cryptocurrency coin close up",
    "listrik": "electric power meter close up",
    "electricity": "electric power meter close up",
    "pajak": "tax form documents stamp",
    "tax": "tax form documents stamp",
}


def sanitize_stock_keyword(keyword: str, placement: str = "") -> str:
    """Force concrete English stock query — kill abstract/mood noise."""
    raw = " ".join(str(keyword or "").split())
    if not raw:
        return ""
    lower = raw.lower()
    tokens = [t for t in re.findall(r"[A-Za-z0-9]+", lower) if t]

    # Exact multi-word topic hits first.
    for needle, replacement in _TOPIC_SYNONYMS.items():
        if needle in lower and len(needle) >= 3:
            base = replacement
            break
    else:
        # Single-token synonym rewrite.
        mapped = []
        for t in tokens:
            if t in _KEYWORD_STOP:
                continue
            mapped.append(_TOPIC_SYNONYMS.get(t, t))
        # Flatten synonym phrases.
        flat: list[str] = []
        for m in mapped:
            flat.extend(m.split())
        # Drop remaining stop words after expand.
        flat = [t for t in flat if t not in _KEYWORD_STOP]
        base = " ".join(dict.fromkeys(flat)) if flat else raw
        # If still 1 generic word, pad with visual framing.
        if len(base.split()) <= 1:
            base = f"{base} close up object" if base else "object close up"

    place = (placement or "").strip().lower()
    behind = place in {"behind_person", "behind", "top_overlay", "overlay"}
    if behind and "close up" not in base.lower() and "macro" not in base.lower():
        base = f"{base} close up"
    return " ".join(base.split())[:80]


def _expand_search_queries(keyword: str, placement: str = "", category: str = "") -> list[str]:
    """Multi-query variants for ClipScout — higher hit rate + subject-accurate stock."""
    base = sanitize_stock_keyword(keyword, placement=placement)
    if not base:
        return []
    tokens = [t for t in base.split() if t]
    lower = base.lower()
    place = (placement or "").strip().lower()
    behind = place in {"behind_person", "behind", "top_overlay", "overlay"}
    cat = (category or "").strip().lower()

    queries: list[str] = [base]

    cleaned = [t for t in tokens if t.lower() not in _KEYWORD_STOP]
    if cleaned and cleaned != tokens:
        queries.append(" ".join(cleaned))

    # Core subject (first 2-3 content words) — better stock match.
    if len(tokens) >= 3:
        queries.append(" ".join(tokens[:3]))
    if len(tokens) >= 2:
        queries.append(" ".join(tokens[:2]))

    # Domain synonym variants (second concrete angle).
    for needle, replacement in _TOPIC_SYNONYMS.items():
        if needle in lower and replacement.lower() not in lower:
            queries.append(replacement)
            break

    # Behind-person / icon: fill-frame subject, avoid wide scenic.
    if behind or cat in {"icon", "motion_graphic"}:
        for suffix in ("close up", "macro detail", "isolated object", "fill frame"):
            if suffix not in lower:
                queries.append(f"{base} {suffix}")
        scenic = {"skyline", "cityscape", "landscape", "aerial", "panorama"}
        if any(s in lower for s in scenic):
            core = [t for t in tokens if t.lower() not in scenic]
            if core:
                queries.insert(1, " ".join(core) + " close up")
    elif "close up" not in lower and "closeup" not in lower:
        queries.append(f"{base} close up")

    # Dedup preserve order, cap 6 (ClipScout batch budget).
    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        key = q.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= 6:
            break
    return out


def build_segments_from_suggestions(
    suggestions: list[BRollSuggestion],
) -> list[dict]:
    """Build ClipScout segment payloads from BRollSuggestion list.

    Each suggestion becomes one segment in the batch request.
    Maps keyword/topic/searchQueries from the suggestion metadata.
    Sends multiple searchQueries (close-up / core-subject) for accuracy.

    Args:
        suggestions: List of B-roll suggestions from AI analysis.

    Returns:
        List of segment dicts ready for ClipScout API.
    """
    segments: list[dict] = []
    for i, suggestion in enumerate(suggestions):
        keyword = str(suggestion.keyword or "").strip()
        if not keyword:
            continue

        placement = str(getattr(suggestion, "placement", "") or "")
        cat = getattr(suggestion, "visual_category", None)
        cat_val = cat.value if hasattr(cat, "value") else str(cat or "")
        queries = _expand_search_queries(keyword, placement=placement, category=cat_val)
        topic = sanitize_stock_keyword(keyword, placement=placement) or keyword

        segment = {
            "id": str(i + 1),
            "text": topic,
            "topic": topic,
            "searchQueries": queries or [topic],
            "startIndex": 0,
            "endIndex": 0,
            "chapter": 1,
        }

        segments.append(segment)

    return segments
