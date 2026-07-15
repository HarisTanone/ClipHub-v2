"""AssetFetcher — Orchestrates free asset resolution with caching and fallback."""

import asyncio
import logging
import os
from typing import Optional

from src.config import settings
from src.domain.entities import AssetResult, BRollSuggestion, CreativeDirection, VisualCategory
from src.domain.interfaces import IAssetClient, IAssetFetcher
from src.infrastructure.asset_cache import AssetCache
from src.infrastructure.pexels_client import PexelsClient
from src.infrastructure.pixabay_client import PixabayClient
from src.infrastructure.iconify_client import IconifyClient
from src.infrastructure.giphy_client import GiphyClient
from src.infrastructure.lottie_library import LottieLibrary

logger = logging.getLogger(__name__)


class AssetFetcher(IAssetFetcher):
    """Resolves B-roll suggestions to real visual assets via free APIs.

    Category routing:
    - footage -> PexelsClient, then PixabayClient as fallback
    - icon -> IconifyClient
    - motion_graphic -> LottieLibrary (local)
    - reaction -> GiphyClient

    Features:
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
        """Resolve assets for all suggestions concurrently (max 4 at a time).

        Attaches AssetResult to each suggestion's asset_result field.
        Returns the same list with asset_results attached.
        """
        if not suggestions:
            return suggestions

        if not settings.ASSET_FETCH_ENABLED:
            for suggestion in suggestions:
                suggestion.asset_result = AssetResult.fallback()
            logger.info("[AssetFetcher] Disabled by ASSET_FETCH_ENABLED=false")
            return suggestions

        tasks = [
            self._resolve_single(s, creative_direction)
            for s in suggestions
        ]

        # Gather with return_exceptions to not crash on individual failures
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log any unexpected exceptions and assign fallback
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"[AssetFetcher] Suggestion {i} failed: {result}")
                suggestions[i].asset_result = AssetResult.fallback()

        return suggestions

    async def _resolve_single(
        self, suggestion: BRollSuggestion, creative_direction: Optional[CreativeDirection]
    ) -> None:
        """Resolve a single suggestion: cache -> client chain -> fallback."""
        async with self._semaphore:
            keyword = suggestion.keyword
            category = suggestion.visual_category

            # Normalize category to VisualCategory enum for reliable dict lookup
            # (handles both enum values and raw strings from Gemini)
            try:
                cat_enum = VisualCategory(category) if isinstance(category, str) else category
            except ValueError:
                cat_enum = VisualCategory.FOOTAGE

            # Use enum .value (plain string) for cache paths
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
                            # Cache using the original semantic keyword so later
                            # jobs reuse the same licensed asset.
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
        # For footage searches, append mood/energy for more relevant results
        if category_str == VisualCategory.FOOTAGE.value and creative_direction:
            mood = creative_direction.energy_level
            if mood and mood != "high":  # "high" is too generic to help
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
