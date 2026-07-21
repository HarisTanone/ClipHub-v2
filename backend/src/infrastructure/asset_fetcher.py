"""AssetFetcher — Orchestrates free asset resolution with caching and fallback.

v2: ClipScout API as primary source for FOOTAGE category.
Fallback: existing Pexels/Pixabay/Giphy/Lottie direct API calls.
"""

import asyncio
import logging
import os
from typing import Optional

from src.config import settings
from src.domain.entities import (
    AssetResult, BRollSuggestion, CreativeDirection, SpliceSegment, VisualCategory,
)
from src.domain.interfaces import IAssetClient, IAssetFetcher
from src.infrastructure.asset_cache import AssetCache
from src.infrastructure.clipscout_ai_selector import ClipScoutAISelector
from src.infrastructure.clipscout_client import (
    ClipScoutClient,
    ClipScoutUnavailableError,
    build_segments_from_suggestions,
)
from src.infrastructure.footage_downloader import FootageDownloader
from src.infrastructure.footage_processor import FootageProcessor
from src.infrastructure.pexels_client import PexelsClient
from src.infrastructure.pixabay_client import PixabayClient
from src.infrastructure.iconify_client import IconifyClient
from src.infrastructure.giphy_client import GiphyClient
from src.infrastructure.lottie_library import LottieLibrary

logger = logging.getLogger(__name__)


class AssetFetcher(IAssetFetcher):
    """Resolves B-roll suggestions to real visual assets via free APIs.

    v2 routing (when BROLL_SPLICE_ENABLED):
    - footage -> ClipScout (primary) -> Pexels/Pixabay (fallback) -> drawtext

    Legacy routing:
    - footage -> PexelsClient, then PixabayClient as fallback
    - icon -> IconifyClient
    - motion_graphic -> LottieLibrary (local)
    - reaction -> GiphyClient

    Features:
    - ClipScout multi-source search (Pexels, Pixabay, YouTube CC/protected)
    - AI-powered video selection via 9router CliperHub
    - SHA-256 cache: avoid re-fetching same keywords
    - Semaphore(4): max 4 concurrent API requests
    - 8s timeout per request
    - Graceful fallback: if all sources fail, returns text-overlay mode
    """

    def __init__(self):
        self._cache = AssetCache(
            cache_dir=settings.ASSET_CACHE_DIR,
            max_size_gb=settings.ASSET_CACHE_MAX_GB,
        )
        self._pexels = PexelsClient()
        self._pixabay = PixabayClient()
        self._iconify = IconifyClient()
        self._giphy = GiphyClient()
        self._lottie = LottieLibrary()

        # ClipScout components (primary source for footage)
        self._clipscout = ClipScoutClient()
        self._ai_selector = ClipScoutAISelector()
        self._downloader = FootageDownloader()
        self._processor = FootageProcessor()

        # Client chains per category (first = primary, rest = fallbacks)
        self._client_chains: dict[str, list[IAssetClient]] = {
            VisualCategory.FOOTAGE: [self._pexels, self._pixabay],
            VisualCategory.ICON: [self._iconify],
            VisualCategory.MOTION_GRAPHIC: [self._lottie],
            VisualCategory.REACTION: [self._giphy],
        }

        self._semaphore = asyncio.Semaphore(4)
        self._timeout = settings.ASSET_FETCH_TIMEOUT

    async def fetch_assets(
        self,
        suggestions: list[BRollSuggestion],
        creative_direction: Optional[CreativeDirection] = None,
    ) -> list[BRollSuggestion]:
        """Resolve assets for all suggestions.

        Strategy:
        1. If BROLL_SPLICE_ENABLED: try ClipScout first for footage suggestions
        2. For non-footage or ClipScout failures: fall through to legacy resolution
        3. Returns suggestions with asset_result and/or splice_segment attached
        """
        if not suggestions:
            return suggestions

        if not settings.ASSET_FETCH_ENABLED:
            for suggestion in suggestions:
                suggestion.asset_result = AssetResult.fallback()
            logger.info("[AssetFetcher] Disabled by ASSET_FETCH_ENABLED=false")
            return suggestions

        # In splice mode the product contract is full-frame footage.  AI visual
        # categories are useful hints for overlay mode, but must not prevent a
        # B-roll event from searching footage and ending as 0 timeline splices.
        if settings.BROLL_SPLICE_ENABLED:
            footage_suggestions = list(suggestions)
            if footage_suggestions:
                try:
                    await self._fetch_via_clipscout(footage_suggestions)
                    # Check which ones got splice segments
                    resolved_count = sum(
                        1 for s in footage_suggestions if s.splice_segment
                    )
                    logger.info(
                        f"[AssetFetcher] ClipScout resolved {resolved_count}/{len(footage_suggestions)} footage"
                    )
                except ClipScoutUnavailableError as exc:
                    logger.warning(f"[AssetFetcher] ClipScout unavailable: {exc}")
                except Exception as exc:
                    logger.warning(f"[AssetFetcher] ClipScout error: {exc}")

        # Legacy resolution for remaining unresolved suggestions
        unresolved = [
            s for s in suggestions
            if not s.asset_result and not s.splice_segment
        ]
        if unresolved:
            if settings.BROLL_SPLICE_ENABLED:
                for suggestion in unresolved:
                    suggestion.visual_category = VisualCategory.FOOTAGE
            tasks = [
                self._resolve_single(s, creative_direction)
                for s in unresolved
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning(f"[AssetFetcher] Legacy suggestion {i} failed: {result}")
                    unresolved[i].asset_result = AssetResult.fallback()

        # Direct Pexels/Pixabay clients return downloaded video AssetResults.
        # Convert those into normalized splice segments as a second route when
        # ClipScout is unavailable or has no candidates.
        if settings.BROLL_SPLICE_ENABLED:
            for index, suggestion in enumerate(suggestions):
                if suggestion.splice_segment:
                    continue
                asset = suggestion.asset_result
                if not asset or asset.is_fallback or asset.asset_format != "video":
                    continue
                processed_path = await self._processor.process(
                    raw_path=asset.local_path,
                    target_duration=suggestion.duration,
                    clip_rank=0,
                    index=index,
                    output_dir=os.path.join(settings.OUTPUT_DIR, "broll_footage"),
                )
                if processed_path:
                    suggestion.splice_segment = SpliceSegment(
                        footage_path=processed_path,
                        at_time=suggestion.at_time,
                        duration=suggestion.duration,
                        keyword=suggestion.keyword,
                        source_id=asset.asset_id,
                        platform=asset.source_api,
                    )
                    logger.info(
                        "[AssetFetcher] Direct footage splice ready: '%s' -> %s",
                        suggestion.keyword,
                        asset.source_api,
                    )

        return suggestions

    async def _fetch_via_clipscout(
        self, suggestions: list[BRollSuggestion]
    ) -> None:
        """Fetch footage via ClipScout API + AI selection + download + process.

        Attaches SpliceSegment to each suggestion that was successfully resolved.
        Raises ClipScoutUnavailableError if ClipScout API is unreachable.
        """
        # Build search segments from suggestions
        segments = build_segments_from_suggestions(suggestions)
        if not segments:
            return

        # Search ClipScout API (retry 2x internally)
        raw_response = await self._clipscout.search(segments)
        candidates_by_segment = self._clipscout.parse_video_candidates(raw_response)

        if not candidates_by_segment:
            logger.warning("[AssetFetcher] ClipScout returned no video candidates")
            return

        # For each suggestion, select best video and download/process
        for i, suggestion in enumerate(suggestions):
            segment_id = str(i + 1)
            candidates = candidates_by_segment.get(segment_id, [])
            if not candidates:
                continue

            # AI selects best video
            selected = self._ai_selector.select_best(
                candidates=candidates,
                keyword=suggestion.keyword,
                required_duration=suggestion.duration,
            )
            if not selected:
                continue

            # Download footage
            raw_path = await self._downloader.download(
                candidate=selected,
                duration_needed=suggestion.duration + 0.5,  # Extra 0.5s buffer
            )
            if not raw_path:
                continue

            # Process to 1080x1920 and trim
            output_dir = os.path.join(settings.OUTPUT_DIR, "broll_footage")
            processed_path = await self._processor.process(
                raw_path=raw_path,
                target_duration=suggestion.duration,
                clip_rank=0,  # Will be set properly by pipeline
                index=i,
                output_dir=output_dir,
            )

            # Cleanup raw download
            if raw_path and os.path.exists(raw_path):
                try:
                    os.remove(raw_path)
                except OSError:
                    pass

            if not processed_path:
                continue

            # Attach splice segment to suggestion
            suggestion.splice_segment = SpliceSegment(
                footage_path=processed_path,
                at_time=suggestion.at_time,
                duration=suggestion.duration,
                keyword=suggestion.keyword,
                source_id=selected.id,
                platform=selected.platform,
            )
            logger.info(
                f"[AssetFetcher] ClipScout splice ready: '{suggestion.keyword}' "
                f"→ {selected.platform}/{selected.id} ({suggestion.duration:.1f}s)"
            )

    async def _resolve_single(
        self, suggestion: BRollSuggestion, creative_direction: Optional[CreativeDirection]
    ) -> None:
        """Resolve a single suggestion: cache -> client chain -> fallback."""
        async with self._semaphore:
            keyword = suggestion.keyword
            category = suggestion.visual_category

            # Normalize category to VisualCategory enum for reliable dict lookup
            try:
                cat_enum = VisualCategory(category) if isinstance(category, str) else category
            except ValueError:
                cat_enum = VisualCategory.FOOTAGE

            category_str = cat_enum.value

            # 1. Check cache first
            cached = self._cache.get(keyword, category_str)
            if cached and os.path.exists(cached.local_path) and os.path.getsize(cached.local_path) > 0:
                suggestion.asset_result = cached
                logger.debug(f"[AssetFetcher] Cache hit: {keyword} ({category_str})")
                return

            # 2. Get client chain for this category
            chain = self._client_chains.get(cat_enum, self._client_chains[VisualCategory.FOOTAGE])
            queries = self._build_queries(keyword, creative_direction, category_str)

            # 3. Try each client in chain
            for client in chain:
                for query in queries:
                    try:
                        result = await asyncio.wait_for(
                            client.search(query),
                            timeout=self._timeout,
                        )
                        if result and not result.is_fallback:
                            self._cache.put(keyword, category_str, result)
                            suggestion.asset_result = result
                            logger.info(
                                f"[AssetFetcher] Resolved: {keyword} -> "
                                f"{result.source_api} ({result.asset_format}, query='{query}')"
                            )
                            return
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"[AssetFetcher] Timeout: {client.__class__.__name__} for '{query}'"
                        )
                        break
                    except Exception as e:
                        logger.warning(
                            f"[AssetFetcher] Error: {client.__class__.__name__} for '{query}': {e}"
                        )
                        break

            # 4. All clients failed — fallback mode
            suggestion.asset_result = AssetResult.fallback()
            logger.info(f"[AssetFetcher] Fallback: {keyword} ({category_str}) — no asset found")

    def _build_query(
        self, keyword: str, creative_direction: Optional[CreativeDirection], category_str: str
    ) -> str:
        """Build search query, optionally augmented with creative direction mood."""
        if category_str == VisualCategory.FOOTAGE.value and creative_direction:
            mood = creative_direction.energy_level
            if mood and mood != "high":
                return f"{keyword} {mood}"
        return keyword

    def _build_queries(
        self,
        keyword: str,
        creative_direction: Optional[CreativeDirection],
        category_str: str,
    ) -> list[str]:
        """Try the precise query first, then one optional mood variant."""
        base = " ".join(str(keyword).split())
        augmented = self._build_query(base, creative_direction, category_str)
        return list(dict.fromkeys(query for query in (base, augmented) if query))
