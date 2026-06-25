"""GiphyClient — Search animated stickers from GIPHY Stickers API."""

import logging
import os
import tempfile
from typing import Optional

import httpx

from src.config import settings
from src.domain.entities import AssetResult
from src.domain.interfaces import IAssetClient

logger = logging.getLogger(__name__)


class GiphyClient(IAssetClient):
    """GIPHY Stickers API client — fetches animated GIF stickers for B-roll overlay."""

    BASE_URL = "https://api.giphy.com/v1/stickers/search"

    def __init__(self, download_dir: str = ""):
        self._api_key = settings.GIPHY_API_KEY
        self._download_dir = download_dir or os.path.join(settings.ASSET_CACHE_DIR, "stickers")
        self._timeout = settings.ASSET_FETCH_TIMEOUT

    async def search(self, keyword: str, **kwargs) -> Optional[AssetResult]:
        """Search GIPHY Stickers for animated GIF matching keyword.

        Returns AssetResult with local path to downloaded GIF, or None.
        """
        if not self._api_key:
            logger.warning("[GiphyClient] No API key configured, skipping.")
            return None

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    self.BASE_URL,
                    params={
                        "api_key": self._api_key,
                        "q": keyword,
                        "rating": "g",
                        "limit": 10,
                    },
                )

                if response.status_code == 429:
                    logger.warning("[GiphyClient] Rate limited (HTTP 429).")
                    return None

                if response.status_code != 200:
                    logger.warning(f"[GiphyClient] API error: HTTP {response.status_code}")
                    return None

                data = response.json()
                results = data.get("data", [])

                if not results:
                    logger.debug(f"[GiphyClient] No results for '{keyword}'")
                    return None

                # Select smallest sticker with acceptable dimensions
                selected = self._select_smallest(results)
                if not selected:
                    logger.debug(f"[GiphyClient] No suitable sticker for '{keyword}'")
                    return None

                gif_url, giphy_id = selected

                # Download GIF
                local_path = await self._download_gif(client, gif_url, keyword)
                if not local_path:
                    return None

                return AssetResult(
                    local_path=local_path,
                    source_api="giphy",
                    license_type="giphy_non_commercial",
                    original_url=gif_url,
                    asset_format="gif",
                    asset_id=giphy_id,
                    is_fallback=False,
                    metadata={"keyword": keyword},
                )

        except httpx.TimeoutException:
            logger.warning(f"[GiphyClient] Timeout searching '{keyword}'")
            return None
        except Exception as e:
            logger.error(f"[GiphyClient] Unexpected error: {e}")
            return None

    def _select_smallest(self, results: list[dict]) -> Optional[tuple[str, str]]:
        """Pick smallest file size sticker with minimum 200px dimension.

        Uses the 'fixed_height' rendition for consistent sizing.
        Returns (download_url, giphy_id) or None.
        """
        MIN_DIMENSION = 200

        best_url: Optional[str] = None
        best_id: str = ""
        best_size: float = float("inf")

        for item in results:
            giphy_id = item.get("id", "")
            images = item.get("images", {})

            # Try 'fixed_height' then 'downsized' for good balance of quality/size
            for rendition_key in ("fixed_height", "downsized", "original"):
                rendition = images.get(rendition_key, {})
                url = rendition.get("url", "")
                width = int(rendition.get("width", 0) or 0)
                height = int(rendition.get("height", 0) or 0)
                size = int(rendition.get("size", 0) or 0)

                if not url:
                    continue

                # Must have at least 200px in one dimension
                if width < MIN_DIMENSION and height < MIN_DIMENSION:
                    continue

                # Prefer smallest file
                if size > 0 and size < best_size:
                    best_size = size
                    best_url = url
                    best_id = giphy_id
                elif size == 0 and not best_url:
                    # No size info but we have a URL, use as fallback
                    best_url = url
                    best_id = giphy_id

        if best_url:
            return (best_url, best_id)
        return None

    async def _download_gif(
        self, client: httpx.AsyncClient, url: str, keyword: str
    ) -> Optional[str]:
        """Stream-download GIF to cache directory. Abort if exceeds 5MB."""
        MAX_GIF_SIZE = 5 * 1024 * 1024  # 5MB max for GIFs
        os.makedirs(self._download_dir, exist_ok=True)

        fd, temp_path = tempfile.mkstemp(suffix=".gif", dir=self._download_dir)
        os.close(fd)

        try:
            downloaded = 0
            async with client.stream("GET", url, timeout=30.0) as response:
                if response.status_code != 200:
                    os.unlink(temp_path)
                    return None

                with open(temp_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        downloaded += len(chunk)
                        if downloaded > MAX_GIF_SIZE:
                            logger.warning(f"[GiphyClient] GIF exceeds 5MB limit, aborting.")
                            break
                        f.write(chunk)

            if downloaded > MAX_GIF_SIZE:
                os.unlink(temp_path)
                return None

            logger.debug(f"[GiphyClient] Downloaded {downloaded // 1024}KB GIF for '{keyword}'")
            return temp_path

        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.warning(f"[GiphyClient] Download error: {e}")
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return None
