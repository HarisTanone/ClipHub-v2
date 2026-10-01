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
from src.infrastructure.broll_subject_analyzer import BrollSubjectAnalyzer
from src.infrastructure.pexels_client import PexelsClient
from src.infrastructure.pixabay_client import PixabayClient
from src.infrastructure.iconify_client import IconifyClient
from src.infrastructure.gemini_agentic_video_service import GeminiAgenticVideoService
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
        self._subject_analyzer = BrollSubjectAnalyzer()
        self._agentic_service = GeminiAgenticVideoService()

        # Client chains per category (first = primary, rest = fallbacks)
        self._client_chains: dict[str, list[IAssetClient]] = {
            VisualCategory.FOOTAGE: [self._pexels, self._pixabay],
            VisualCategory.ICON: [self._iconify],
            VisualCategory.MOTION_GRAPHIC: [self._lottie],
            VisualCategory.REACTION: [self._giphy],
        }

        self._semaphore = asyncio.Semaphore(4)
        self._timeout = settings.ASSET_FETCH_TIMEOUT
        # Per-job used asset IDs — prevents same footage repeating across clips.
        self._used_ids: set[str] = set()

    def reset_used_ids(self):
        """Call at job start to clear cross-clip exclusion."""
        self._used_ids.clear()

    async def fetch_assets(
        self,
        suggestions: list[BRollSuggestion],
        creative_direction: Optional[CreativeDirection] = None,
        analisa_extra_queries: Optional[list[str]] = None,
        target_width: int = 1080,
        target_height: int = 1920,
    ) -> list[BRollSuggestion]:
        """Resolve assets for all suggestions.

        Strategy:
        1. If BROLL_SPLICE_ENABLED: try ClipScout first for footage suggestions
        2. For non-footage or ClipScout failures: fall through to legacy resolution
        3. Returns suggestions with asset_result and/or splice_segment attached
        analisa_extra_queries: ID+EN seeds from json_analisa (footage_keywords/objects).
        target_width/height: job output resolution for footage normalize.
        """
        self._target_w = max(2, int(target_width) // 2 * 2)
        self._target_h = max(2, int(target_height) // 2 * 2)
        if not suggestions:
            return suggestions

        # Fresh exclusion set per fetch batch (per-job) — kill repeated footage.
        self._used_ids.clear()

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
                    await self._fetch_via_clipscout(
                        footage_suggestions,
                        analisa_extra_queries=analisa_extra_queries,
                    )
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
                    width=getattr(self, "_target_w", 1080),
                    height=getattr(self, "_target_h", 1920),
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

    async def _fetch_via_clipscout(
        self,
        suggestions: list[BRollSuggestion],
        analisa_extra_queries: Optional[list[str]] = None,
    ) -> None:
        """Fetch footage via ClipScout API + AI selection + download + process.

        Attaches SpliceSegment to each suggestion that was successfully resolved.
        Raises ClipScoutUnavailableError if ClipScout API is unreachable.
        analisa_extra_queries: bilingual seeds from json_analisa.
        """
        # Build search segments from suggestions (+ ID/EN analisa seeds)
        topic_seed = " / ".join(analisa_extra_queries[:4]) if analisa_extra_queries else ""
        segments = build_segments_from_suggestions(
            suggestions,
            topic_text=topic_seed,
            analisa_extra_queries=analisa_extra_queries,
        )
        if not segments:
            return

        # Search ClipScout API (prioritizing landscape 16:9 for AI-aware reframing)
        raw_response = await self._clipscout.search(segments, orientation="horizontal")
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

            # Cross-clip exclusion: drop already-used asset IDs (kill repetition).
            if self._used_ids:
                before = len(candidates)
                candidates = [c for c in candidates if str(c.id) not in self._used_ids]
                if before != len(candidates):
                    logger.info(f"[AssetFetcher] Excluded {before - len(candidates)} used IDs for segment {segment_id}")
            if not candidates:
                continue

            # AI selects best video (pass-2 context = reason / clip topic sentence)
            # Include analisa seeds so AI can score fit to clip context.
            ctx = str(getattr(suggestion, "reason", "") or "")
            if analisa_extra_queries:
                ctx = (ctx + " | " + " / ".join(analisa_extra_queries[:6])).strip(" |")
            selected = self._ai_selector.select_best(
                candidates=candidates,
                keyword=suggestion.keyword,
                required_duration=suggestion.duration,
                placement=str(getattr(suggestion, "placement", "") or ""),
                context=ctx,
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

            # Run AI Subject & Composition Analysis
            target_w = getattr(self, "_target_w", 1080)
            target_h = getattr(self, "_target_h", 1920)
            analysis = self._subject_analyzer.analyze_video(
                video_path=raw_path,
                target_w=target_w,
                target_h=target_h,
                force_mode=getattr(suggestion, "placement", None) or None,
            )

            suggestion.smart_crop_x = analysis.smart_crop_x
            suggestion.smart_crop_y = analysis.smart_crop_y
            if not getattr(suggestion, "placement", ""):
                suggestion.placement = analysis.recommended_mode.value
            suggestion.layout_mode = analysis.recommended_mode.value
            if analysis.primary_subject:
                suggestion.subject_bbox = list(analysis.primary_subject.box)

            # Process to job resolution and trim with AI-aware crop & layout
            output_dir = os.path.join(settings.OUTPUT_DIR, "broll_footage")
            processed_path = await self._processor.process(
                raw_path=raw_path,
                target_duration=suggestion.duration,
                clip_rank=0,  # Will be set properly by pipeline
                index=i,
                output_dir=output_dir,
                width=target_w,
                height=target_h,
                crop_x=analysis.smart_crop_x,
                crop_y=analysis.smart_crop_y,
                layout_mode=suggestion.placement,
            )

            # Cleanup raw download
            if raw_path and os.path.exists(raw_path):
                try:
                    os.remove(raw_path)
                except OSError:
                    pass

            if not processed_path:
                continue

            # Attach splice segment + asset_result so top-behind-person can use
            # the same resolved footage without a second download.
            platform = (selected.platform or "pexels").lower()
            if platform not in AssetResult.VALID_SOURCES:
                platform = "pexels"
            suggestion.splice_segment = SpliceSegment(
                footage_path=processed_path,
                at_time=suggestion.at_time,
                duration=suggestion.duration,
                keyword=suggestion.keyword,
                source_id=selected.id,
                platform=selected.platform,
            )
            suggestion.asset_result = AssetResult(
                local_path=processed_path,
                source_api=platform,
                license_type="pexels_license" if platform == "pexels" else (
                    "pixabay_license" if platform == "pixabay" else "none"
                ),
                original_url=getattr(selected, "url", "") or "",
                asset_format="video",
                asset_id=str(selected.id or ""),
                is_fallback=False,
            )
            logger.info(
                f"[AssetFetcher] ClipScout splice ready: '{suggestion.keyword}' "
                f"→ {selected.platform}/{selected.id} ({suggestion.duration:.1f}s)"
            )


    async def _resolve_single(
        self, suggestion: BRollSuggestion, creative_direction: Optional[CreativeDirection]
    ) -> None:
        """Resolve a single suggestion via parallel Pexels+Pixabay pool → AI pick → download."""
        async with self._semaphore:
            keyword = suggestion.keyword
            category = suggestion.visual_category
            placement = str(getattr(suggestion, "placement", "") or "")

            try:
                cat_enum = VisualCategory(category) if isinstance(category, str) else category
            except ValueError:
                cat_enum = VisualCategory.FOOTAGE

            category_str = cat_enum.value

            # Non-footage categories: keep legacy chain path.
            if cat_enum != VisualCategory.FOOTAGE:
                await self._resolve_legacy(suggestion, creative_direction, cat_enum, category_str)
                return

            # 1. Cache check
            cached = self._cache.get(keyword, category_str)
            if cached and os.path.exists(cached.local_path) and os.path.getsize(cached.local_path) > 0:
                suggestion.asset_result = cached
                logger.debug(f"[AssetFetcher] Cache hit: {keyword} ({category_str})")
                return

            # 2. Parallel search both APIs (metadata only, no download yet)
            queries = self._build_queries(keyword, creative_direction, category_str, placement)
            base_query = queries[0] if queries else keyword

            pexels_cands, pixabay_cands = await asyncio.gather(
                self._pexels.search_candidates(base_query, exclude_ids=self._used_ids),
                self._pixabay.search_candidates(base_query, exclude_ids=self._used_ids),
                return_exceptions=True,
            )

            pool: list = []
            for c in (pexels_cands if isinstance(pexels_cands, list) else []):
                pool.append(c)
            for c in (pixabay_cands if isinstance(pixabay_cands, list) else []):
                pool.append(c)

            if not pool:
                # Retry with expanded queries if base query returned nothing
                for q in queries[1:]:
                    px, pb = await asyncio.gather(
                        self._pexels.search_candidates(q, exclude_ids=self._used_ids),
                        self._pixabay.search_candidates(q, exclude_ids=self._used_ids),
                        return_exceptions=True,
                    )
                    for c in (px if isinstance(px, list) else []):
                        pool.append(c)
                    for c in (pb if isinstance(pb, list) else []):
                        pool.append(c)
                    if pool:
                        break

            if not pool:
                suggestion.asset_result = AssetResult.fallback()
                logger.info(f"[AssetFetcher] No candidates from Pexels+Pixabay: '{keyword}'")
                return

            # 3. AI selects best from combined pool (9router / ClipScoutAISelector)
            ctx = str(getattr(suggestion, "reason", "") or "")
            selected = self._ai_selector.select_best(
                candidates=pool,
                keyword=keyword,
                required_duration=suggestion.duration,
                placement=placement,
                context=ctx,
            )

            if not selected:
                suggestion.asset_result = AssetResult.fallback()
                logger.info(f"[AssetFetcher] AI picker rejected all candidates: '{keyword}'")
                return

            # 4. Download only the selected candidate
            raw_path = await self._downloader.download_segment(
                url=selected.source_url,
                duration=suggestion.duration + 0.5,
                scene_id=selected.id,
                platform=selected.platform,
                video_id=selected.id,
            )
            if not raw_path:
                suggestion.asset_result = AssetResult.fallback()
                return

            # 5. Process footage
            output_dir = os.path.join(settings.OUTPUT_DIR, "broll_footage")
            processed_path = await self._processor.process(
                raw_path=raw_path,
                target_duration=suggestion.duration,
                clip_rank=0,
                index=0,
                output_dir=output_dir,
                width=getattr(self, "_target_w", 1080),
                height=getattr(self, "_target_h", 1920),
            )

            # Cleanup raw
            if raw_path and os.path.exists(raw_path):
                try:
                    os.remove(raw_path)
                except OSError:
                    pass

            if not processed_path:
                suggestion.asset_result = AssetResult.fallback()
                return

            # 6. Track used ID to prevent repetition across clips
            self._used_ids.add(selected.id)
            logger.info(
                f"[AssetFetcher] Pool resolved '{keyword}' -> "
                f"{selected.platform}/{selected.id} (pool={len(pool)}, used={len(self._used_ids)})"
            )

            platform = (selected.platform or "pexels").lower()
            if platform not in ("pexels", "pixabay"):
                platform = "pexels"

            result = AssetResult(
                local_path=processed_path,
                source_api=platform,
                license_type=f"{platform}_license",
                original_url=selected.source_url,
                asset_format="video",
                asset_id=str(selected.id),
                is_fallback=False,
                metadata={"keyword": keyword},
            )
            self._cache.put(keyword, category_str, result)
            suggestion.asset_result = result
            logger.info(
                f"[AssetFetcher] Resolved via pool: '{keyword}' -> "
                f"{platform}/{selected.id} (pool_size={len(pool)})"
            )

    async def _resolve_legacy(
        self, suggestion: BRollSuggestion, creative_direction: Optional[CreativeDirection],
        cat_enum, category_str: str,
    ) -> None:
        """Legacy chain resolution for non-footage categories (icons, reactions, etc)."""
        keyword = suggestion.keyword
        chain = self._client_chains.get(cat_enum, [])
        queries = self._build_queries(keyword, creative_direction, category_str, getattr(suggestion, "placement", "") or "")

        for client in chain:
            for query in queries:
                try:
                    result = await asyncio.wait_for(client.search(query), timeout=self._timeout)
                    if result and not result.is_fallback:
                        self._cache.put(keyword, category_str, result)
                        suggestion.asset_result = result
                        return
                except Exception:
                    break

        suggestion.asset_result = AssetResult.fallback()
        logger.info(f"[AssetFetcher] Fallback: {keyword} ({category_str}) — no relevant asset found, skipping")

    async def _extract_subtitle_queries(self, suggestion: BRollSuggestion) -> list[str]:
        """Extract visual search queries via Gemini Agentic Subtitle Understanding."""
        sub_text = str(getattr(suggestion, "subtitle_text", "") or "").strip()
        reason = str(getattr(suggestion, "reason", "") or "").strip()
        keyword = str(getattr(suggestion, "keyword", "") or "").strip()
        placement = str(getattr(suggestion, "placement", "behind_person") or "behind_person")

        return await self._agentic_service.derive_contextual_queries(
            keyword=keyword,
            subtitle_text=sub_text,
            context=reason,
            placement=placement,
        )

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
        placement: str = "",
    ) -> list[str]:
        """Precise query first, then close-up / subject-core fallbacks."""
        from src.infrastructure.clipscout_client import (
            sanitize_stock_keyword,
            _expand_search_queries,
        )
        base = sanitize_stock_keyword(keyword, placement=placement) or " ".join(str(keyword).split())
        # Reuse ClipScout multi-query expander (same sanitizer + synonyms).
        variants = _expand_search_queries(keyword, placement=placement, category=category_str)
        if base and base not in variants:
            variants.insert(0, base)

        augmented = self._build_query(base, creative_direction, category_str)
        if augmented and augmented not in variants:
            variants.append(augmented)

        return list(dict.fromkeys(q for q in variants if q))


