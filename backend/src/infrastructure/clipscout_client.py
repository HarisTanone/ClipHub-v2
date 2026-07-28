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


def extract_topic_entities(*texts: str) -> list[str]:
    """Content tokens ≥4 chars from free text (soft topic lock). No stop/mood lexicon."""
    blob = " ".join(str(t or "") for t in texts).lower()
    if not blob:
        return []
    tokens = re.findall(r"[a-z0-9]{4,}", blob)
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= 8:
            break
    return out


def lock_keyword_to_entities(
    keyword: str,
    entities: list[str],
    placement: str = "",
) -> str:
    """Keep AI/search keyword; lightly prepend first content token if totally off-topic."""
    clean = sanitize_stock_keyword(keyword, placement=placement)
    if not entities or not clean:
        return clean
    lower = clean.lower()
    if any(e in lower for e in entities[:4]):
        return clean
    # Soft lock: only if keyword is very short / generic
    if len(clean.split()) <= 2 and entities[0] not in lower:
        return sanitize_stock_keyword(f"{entities[0]} {clean}", placement=placement)
    return clean


def sanitize_stock_keyword(keyword: str, placement: str = "") -> str:
    """Normalize AI stock query. No mood/stopword strip — AI supplies concrete queries."""
    raw = " ".join(str(keyword or "").split())
    if not raw:
        return ""
    tokens = [t for t in re.findall(r"[A-Za-z0-9]+", raw) if t]
    base = " ".join(tokens) if tokens else raw
    # If still 1 weak word, pad visual framing (generic, not domain map)
    if len(base.split()) <= 1:
        base = f"{base} close up object" if base else "object close up"
    place = (placement or "").strip().lower()
    behind = place in {"behind_person", "behind", "top_overlay", "overlay"}
    if behind and "close up" not in base.lower() and "macro" not in base.lower():
        base = f"{base} close up"
    return " ".join(base.split())[:80]


def _expand_search_queries(
    keyword: str,
    placement: str = "",
    category: str = "",
    entities: Optional[list[str]] = None,
    extra_queries: Optional[list[str]] = None,
) -> list[str]:
    """Multi-query variants for ClipScout from AI keyword + analisa seeds (ID+EN).

    No hardcoded domain synonym table — extra_queries come from AI visual entities.
    """
    locked = lock_keyword_to_entities(keyword, entities or [], placement=placement)
    base = locked or sanitize_stock_keyword(keyword, placement=placement)
    if not base:
        return []
    tokens = [t for t in base.split() if t]
    lower = base.lower()
    place = (placement or "").strip().lower()
    behind = place in {"behind_person", "behind", "top_overlay", "overlay"}
    cat = (category or "").strip().lower()

    queries: list[str] = [base]

    # AI / analisa bilingual seeds (dynamic)
    for eq in extra_queries or []:
        eq = " ".join(str(eq or "").split())
        if eq and eq.lower() not in {q.lower() for q in queries}:
            queries.append(eq)

    if len(tokens) >= 3:
        queries.append(" ".join(tokens[:3]))
    if len(tokens) >= 2:
        queries.append(" ".join(tokens[:2]))

    # Behind-person / icon: fill-frame framing
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

    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        key = q.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= 8:
            break
    return out


def build_segments_from_suggestions(
    suggestions: list[BRollSuggestion],
    topic_text: str = "",
    analisa_extra_queries: Optional[list[str]] = None,
) -> list[dict]:
    """Build ClipScout segment payloads from BRollSuggestion list.

    Merges AI keyword + dynamic analisa seeds (ID+EN from visual entities).
    """
    texts = [topic_text]
    for s in suggestions:
        texts.append(str(getattr(s, "keyword", "") or ""))
        texts.append(str(getattr(s, "reason", "") or ""))
    for q in analisa_extra_queries or []:
        texts.append(str(q or ""))
    entities = extract_topic_entities(*texts)

    segments: list[dict] = []
    for i, suggestion in enumerate(suggestions):
        keyword = str(suggestion.keyword or "").strip()
        if not keyword:
            continue

        placement = str(getattr(suggestion, "placement", "") or "")
        cat = getattr(suggestion, "visual_category", None)
        cat_val = cat.value if hasattr(cat, "value") else str(cat or "")
        locked = lock_keyword_to_entities(keyword, entities, placement=placement)
        if locked and locked != keyword:
            suggestion.keyword = locked
        queries = _expand_search_queries(
            locked or keyword,
            placement=placement,
            category=cat_val,
            entities=entities,
            extra_queries=list(analisa_extra_queries or []),
        )
        topic = locked or sanitize_stock_keyword(keyword, placement=placement) or keyword

        segments.append({
            "id": str(i + 1),
            "text": topic,
            "topic": topic,
            "searchQueries": queries or [topic],
            "startIndex": 0,
            "endIndex": 0,
            "chapter": 1,
        })

    return segments
