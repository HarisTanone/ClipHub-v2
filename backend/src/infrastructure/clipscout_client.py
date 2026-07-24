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


def _expand_search_queries(keyword: str, placement: str = "", category: str = "") -> list[str]:
    """Multi-query variants for ClipScout — higher hit rate + subject-accurate stock."""
    base = " ".join(str(keyword or "").split())
    if not base:
        return []
    tokens = [t for t in base.split() if t]
    lower = base.lower()
    place = (placement or "").strip().lower()
    behind = place in {"behind_person", "behind", "top_overlay", "overlay"}
    cat = (category or "").strip().lower()

    queries: list[str] = [base]

    # Drop abstract/mood poison words that skew stock results.
    stop = {
        "dramatic", "cinematic", "beautiful", "success", "lifestyle",
        "epic", "mood", "vibes", "aesthetic", "background",
    }
    cleaned = [t for t in tokens if t.lower() not in stop]
    if cleaned and cleaned != tokens:
        queries.append(" ".join(cleaned))

    # Core subject (first 2-3 content words) — better stock match.
    if len(tokens) >= 3:
        queries.append(" ".join(tokens[:3]))
    if len(tokens) >= 2:
        queries.append(" ".join(tokens[:2]))

    # Behind-person / icon: fill-frame subject, avoid wide scenic.
    if behind or cat in {"icon", "motion_graphic"}:
        for suffix in ("close up", "macro detail", "isolated object", "fill frame"):
            if suffix not in lower:
                queries.append(f"{base} {suffix}")
    elif "close up" not in lower and "closeup" not in lower:
        queries.append(f"{base} close up")

    # Dedup preserve order, cap 5 (ClipScout batch budget).
    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        key = q.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= 5:
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

        segment = {
            "id": str(i + 1),
            "text": keyword,
            "topic": keyword,
            "searchQueries": queries or [keyword],
            "startIndex": 0,
            "endIndex": 0,
            "chapter": 1,
        }
        segments.append(segment)

    return segments
