"""IconifyClient — SVG icon search + download from Iconify API (free, no key required)."""

import logging
import os
import tempfile
from typing import Optional

import httpx

from src.config import settings
from src.domain.entities import AssetResult
from src.domain.interfaces import IAssetClient

logger = logging.getLogger(__name__)


class IconifyClient(IAssetClient):
    """Iconify SVG icon API client — fetches free SVG icons for B-roll overlay.

    No API key required. Searches multiple popular icon sets.
    """

    SEARCH_URL = "https://api.iconify.design/search"
    ICON_URL_TEMPLATE = "https://api.iconify.design/{prefix}/{name}.svg"

    # Popular icon set prefixes to try
    PREFERRED_PREFIXES = ("mdi", "fluent", "ph", "lucide", "tabler")

    def __init__(self, download_dir: str = ""):
        self._download_dir = download_dir or os.path.join(settings.ASSET_CACHE_DIR, "icons")
        self._timeout = settings.ASSET_FETCH_TIMEOUT

    async def search(self, keyword: str, **kwargs) -> Optional[AssetResult]:
        """Search Iconify for SVG icon matching keyword.

        Tries multiple icon set prefixes for best results.
        Returns AssetResult with local path to SVG file, or None.
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # Search across all icon sets
                response = await client.get(
                    self.SEARCH_URL,
                    params={"query": keyword, "limit": 5},
                )

                if response.status_code != 200:
                    logger.warning(f"[IconifyClient] Search API error: HTTP {response.status_code}")
                    return None

                data = response.json()
                icons = data.get("icons", [])

                if not icons:
                    logger.debug(f"[IconifyClient] No results for '{keyword}'")
                    return None

                # Pick the best icon — prefer icons from known prefixes
                selected = self._select_best_icon(icons)
                if not selected:
                    # Fallback: just use first result
                    selected = icons[0]

                # Parse prefix:name format
                prefix, name = self._parse_icon_id(selected)
                if not prefix or not name:
                    logger.warning(f"[IconifyClient] Could not parse icon id: {selected}")
                    return None

                # Download SVG content
                svg_url = self.ICON_URL_TEMPLATE.format(prefix=prefix, name=name)
                svg_response = await client.get(svg_url)

                if svg_response.status_code != 200:
                    logger.warning(f"[IconifyClient] SVG download failed: HTTP {svg_response.status_code}")
                    return None

                svg_content = svg_response.text
                if not svg_content or "<svg" not in svg_content:
                    logger.warning(f"[IconifyClient] Invalid SVG content for {prefix}:{name}")
                    return None

                # Save SVG to disk
                local_path = self._save_svg(svg_content, prefix, name)
                if not local_path:
                    return None

                return AssetResult(
                    local_path=local_path,
                    source_api="iconify",
                    license_type="mit",
                    original_url=svg_url,
                    asset_format="svg",
                    asset_id=f"{prefix}:{name}",
                    is_fallback=False,
                    metadata={"keyword": keyword, "prefix": prefix, "name": name},
                )

        except httpx.TimeoutException:
            logger.warning(f"[IconifyClient] Timeout searching '{keyword}'")
            return None
        except Exception as e:
            logger.error(f"[IconifyClient] Unexpected error: {e}")
            return None

    def _select_best_icon(self, icons: list[str]) -> Optional[str]:
        """Select icon from a preferred prefix set.

        Icons are in format 'prefix:name'. Prefer icons from well-known sets.
        """
        for preferred in self.PREFERRED_PREFIXES:
            for icon_id in icons:
                if icon_id.startswith(f"{preferred}:"):
                    return icon_id
        return None

    def _parse_icon_id(self, icon_id: str) -> tuple[str, str]:
        """Parse 'prefix:name' into (prefix, name). Returns ('', '') on failure."""
        if ":" not in icon_id:
            return ("", "")
        parts = icon_id.split(":", 1)
        return (parts[0], parts[1])

    def _save_svg(self, svg_content: str, prefix: str, name: str) -> Optional[str]:
        """Save SVG content to cache directory. Returns file path or None."""
        os.makedirs(self._download_dir, exist_ok=True)

        safe_name = f"{prefix}_{name}.svg".replace("/", "_")
        file_path = os.path.join(self._download_dir, safe_name)

        # If already cached, return existing
        if os.path.exists(file_path):
            logger.debug(f"[IconifyClient] Cache hit: {file_path}")
            return file_path

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(svg_content)
            logger.debug(f"[IconifyClient] Saved SVG: {file_path}")
            return file_path
        except OSError as e:
            logger.error(f"[IconifyClient] Failed to write SVG: {e}")
            return None
