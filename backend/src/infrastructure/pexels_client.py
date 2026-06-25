"""PexelsClient — Search and download portrait video footage from Pexels API."""

import logging
import os
import tempfile
from typing import Optional

import httpx

from src.config import settings
from src.domain.entities import AssetResult
from src.domain.interfaces import IAssetClient

logger = logging.getLogger(__name__)


class PexelsClient(IAssetClient):
    """Pexels Video API client — fetches short portrait footage for B-roll overlay."""

    BASE_URL = "https://api.pexels.com/videos/search"

    def __init__(self, download_dir: str = ""):
        self._api_key = settings.PEXELS_API_KEY
        self._download_dir = download_dir or os.path.join(settings.ASSET_CACHE_DIR, "footage")
        self._max_size = settings.ASSET_FETCH_MAX_VIDEO_SIZE_MB * 1024 * 1024  # bytes
        self._timeout = settings.ASSET_FETCH_TIMEOUT

    async def search(self, keyword: str, **kwargs) -> Optional[AssetResult]:
        """Search Pexels for portrait video matching keyword.

        Returns AssetResult with local path to downloaded video, or None.
        """
        if not self._api_key:
            logger.warning("[PexelsClient] No API key configured, skipping.")
            return None

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # Search for videos
                response = await client.get(
                    self.BASE_URL,
                    headers={"Authorization": self._api_key},
                    params={
                        "query": keyword,
                        "orientation": "portrait",
                        "per_page": 5,
                    },
                )

                if response.status_code == 429:
                    logger.warning("[PexelsClient] Rate limited (HTTP 429).")
                    return None

                if response.status_code != 200:
                    logger.warning(f"[PexelsClient] API error: HTTP {response.status_code}")
                    return None

                data = response.json()
                videos = data.get("videos", [])

                if not videos:
                    logger.debug(f"[PexelsClient] No results for '{keyword}'")
                    return None

                # Select best video file
                best = self._select_best_video(videos)
                if not best:
                    logger.debug(f"[PexelsClient] No suitable video file for '{keyword}'")
                    return None

                video_url, video_id = best

                # Stream download to disk
                local_path = await self._download_video(client, video_url, keyword)
                if not local_path:
                    return None

                return AssetResult(
                    local_path=local_path,
                    source_api="pexels",
                    license_type="pexels_license",
                    original_url=video_url,
                    asset_format="video",
                    asset_id=str(video_id),
                    is_fallback=False,
                    metadata={"keyword": keyword},
                )

        except httpx.TimeoutException:
            logger.warning(f"[PexelsClient] Timeout searching '{keyword}'")
            return None
        except Exception as e:
            logger.error(f"[PexelsClient] Unexpected error: {e}")
            return None

    def _select_best_video(self, videos: list[dict]) -> Optional[tuple[str, int]]:
        """Pick video file closest to 1080x1920, duration < 10 seconds.

        Returns (download_url, video_id) or None.
        """
        TARGET_WIDTH = 1080
        TARGET_HEIGHT = 1920
        MAX_DURATION = 10  # seconds

        best_url: Optional[str] = None
        best_id: int = 0
        best_score: float = float("inf")

        for video in videos:
            duration = video.get("duration", 0)
            if duration > MAX_DURATION:
                continue

            video_id = video.get("id", 0)
            video_files = video.get("video_files", [])

            for vf in video_files:
                width = vf.get("width", 0)
                height = vf.get("height", 0)
                link = vf.get("link", "")

                if not link or height > 1920:
                    continue

                # Score: distance from target resolution
                score = abs(width - TARGET_WIDTH) + abs(height - TARGET_HEIGHT)

                if score < best_score:
                    best_score = score
                    best_url = link
                    best_id = video_id

        if best_url:
            return (best_url, best_id)
        return None

    async def _download_video(
        self, client: httpx.AsyncClient, url: str, keyword: str
    ) -> Optional[str]:
        """Stream-download video to temp file. Abort if exceeds max size."""
        os.makedirs(self._download_dir, exist_ok=True)

        # Create temp file in download dir
        fd, temp_path = tempfile.mkstemp(suffix=".mp4", dir=self._download_dir)
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
                        if downloaded > self._max_size:
                            logger.warning(
                                f"[{self.__class__.__name__}] Download exceeds "
                                f"{self._max_size // (1024*1024)}MB limit, aborting."
                            )
                            break
                        f.write(chunk)

            if downloaded > self._max_size:
                os.unlink(temp_path)
                return None

            logger.debug(f"[{self.__class__.__name__}] Downloaded {downloaded // 1024}KB for '{keyword}'")
            return temp_path

        except (httpx.TimeoutException, httpx.HTTPError, OSError) as e:
            logger.warning(f"[{self.__class__.__name__}] Download error: {e}")
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return None
