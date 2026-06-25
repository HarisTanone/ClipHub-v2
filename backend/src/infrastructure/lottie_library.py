"""LottieLibrary — Local manifest-based search for pre-curated Lottie animations."""

import json
import logging
import os
from typing import Optional

from src.config import settings
from src.domain.entities import AssetResult
from src.domain.interfaces import IAssetClient

logger = logging.getLogger(__name__)


class LottieLibrary(IAssetClient):
    """Local Lottie animation library — searches pre-curated manifest for matching animations.

    No network requests needed. Matches by keyword substring or exact tag match.
    """

    def __init__(self, library_dir: str = ""):
        self._library_dir = library_dir or settings.LOTTIE_LIBRARY_DIR
        self._manifest: Optional[dict] = None

    def _load_manifest(self) -> list[dict]:
        """Load and cache the manifest.json file. Returns list of animation entries."""
        if self._manifest is not None:
            return self._manifest.get("animations", [])

        manifest_path = os.path.join(self._library_dir, "manifest.json")

        if not os.path.exists(manifest_path):
            logger.warning(f"[LottieLibrary] Manifest not found: {manifest_path}")
            return []

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                self._manifest = json.load(f)
            return self._manifest.get("animations", [])
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"[LottieLibrary] Failed to load manifest: {e}")
            self._manifest = {"animations": []}
            return []

    async def search(self, keyword: str, **kwargs) -> Optional[AssetResult]:
        """Search local Lottie manifest for animation matching keyword.

        Matches by:
        - Keyword substring match against animation keywords
        - Exact tag match against animation tags

        Returns AssetResult with local path to Lottie JSON file, or None.
        """
        animations = self._load_manifest()
        if not animations:
            logger.debug("[LottieLibrary] No animations in manifest.")
            return None

        keyword_lower = keyword.lower().strip()
        if not keyword_lower:
            return None

        # Score each animation: exact keyword > substring keyword > exact tag
        best_match: Optional[dict] = None
        best_score: int = 0

        for anim in animations:
            score = self._score_match(anim, keyword_lower)
            if score > best_score:
                best_score = score
                best_match = anim

        if not best_match:
            logger.debug(f"[LottieLibrary] No match for '{keyword}'")
            return None

        # Resolve local file path
        file_name = best_match.get("file", "")
        local_path = os.path.join(self._library_dir, file_name)

        # File may not exist yet (manifest is pre-curated, files added later)
        if not os.path.exists(local_path):
            logger.warning(
                f"[LottieLibrary] Matched '{best_match.get('id')}' but file missing: {local_path}"
            )
            return None

        return AssetResult(
            local_path=local_path,
            source_api="lottie",
            license_type="mit",
            original_url="",
            asset_format="lottie",
            asset_id=best_match.get("id", ""),
            is_fallback=False,
            metadata={
                "keyword": keyword,
                "matched_id": best_match.get("id", ""),
                "tags": best_match.get("tags", []),
            },
        )

    def _score_match(self, anim: dict, keyword_lower: str) -> int:
        """Score an animation entry against a search keyword.

        Returns:
            3 — exact keyword match
            2 — substring keyword match
            1 — exact tag match
            0 — no match
        """
        # Check keywords
        keywords = [kw.lower() for kw in anim.get("keywords", [])]
        for kw in keywords:
            if kw == keyword_lower:
                return 3
            if keyword_lower in kw or kw in keyword_lower:
                return 2

        # Check tags (exact match only)
        tags = [t.lower() for t in anim.get("tags", [])]
        if keyword_lower in tags:
            return 1

        return 0

    def render_to_png_sequence(
        self, lottie_path: str, output_dir: str, fps: int = 30
    ) -> list[str]:
        """Render Lottie animation to PNG frame sequence for FFmpeg overlay.

        TODO: Not yet implemented. Requires one of:
        - lottie-python package (pip install lottie)
        - Puppeteer/Playwright headless render
        - rlottie native binary

        Currently returns empty list (Lottie suggestions fall back to drawtext).
        """
        logger.warning(
            f"[LottieLibrary] render_to_png_sequence NOT IMPLEMENTED. "
            f"Lottie assets will use text fallback. Path: {lottie_path}"
        )
        return []
