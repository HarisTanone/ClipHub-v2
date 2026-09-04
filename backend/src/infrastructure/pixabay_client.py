"""PixabayClient — Fallback video footage search from Pixabay API."""

import logging
import os
import tempfile
from typing import Optional

import httpx

from src.config import settings
from src.domain.entities import AssetResult
from src.domain.interfaces import IAssetClient

logger = logging.getLogger(__name__)

BANNED_VIDEO_IDS = {"9038", 9038}
BANNED_TAGS = {"nerve cell", "neuron", "synapse", "brain cells"}


class PixabayClient(IAssetClient):
    """Pixabay Video API client — fallback footage source for B-roll overlay."""

    BASE_URL = "https://pixabay.com/api/videos/"
    BANNED_VIDEO_IDS = BANNED_VIDEO_IDS
    BANNED_TAGS = BANNED_TAGS


    def __init__(self, download_dir: str = ""):
        self._api_key = settings.PIXABAY_API_KEY
        self._download_dir = download_dir or os.path.join(settings.ASSET_CACHE_DIR, "footage")
        self._max_size = settings.ASSET_FETCH_MAX_VIDEO_SIZE_MB * 1024 * 1024  # bytes
        self._timeout = settings.ASSET_FETCH_TIMEOUT

    async def search(self, keyword: str, **kwargs) -> Optional[AssetResult]:
        """Search Pixabay for video matching keyword.

        Returns AssetResult with local path to downloaded video, or None.
        """
        if not self._api_key:
            logger.warning("[PixabayClient] No API key configured, skipping.")
            return None

        from src.infrastructure.pexels_client import expand_visual_queries
        queries = expand_visual_queries(keyword)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                hits = []
                for q in queries:
                    response = await client.get(
                        self.BASE_URL,
                        params={
                            "key": self._api_key,
                            "q": q,
                            "video_type": "film",
                            "min_width": 720,
                            "per_page": 5,
                        },
                    )

                    if response.status_code == 429:
                        logger.warning("[PixabayClient] Rate limited (HTTP 429).")
                        return None

                    if response.status_code != 200:
                        continue

                    data = response.json()
                    hits = data.get("hits", [])
                    if hits:
                        break

                if not hits:
                    logger.debug(f"[PixabayClient] No results for '{keyword}'")
                    return None

                # Select best video
                best = self._select_best_video(hits)
                if not best:
                    logger.debug(f"[PixabayClient] No suitable video for '{keyword}'")
                    return None

                video_url, video_id = best

                # Stream download
                local_path = await self._download_video(client, video_url, keyword)
                if not local_path:
                    return None

                return AssetResult(
                    local_path=local_path,
                    source_api="pixabay",
                    license_type="pixabay_license",
                    original_url=video_url,
                    asset_format="video",
                    asset_id=str(video_id),
                    is_fallback=False,
                    metadata={"keyword": keyword},
                )

        except httpx.TimeoutException:
            logger.warning(f"[PixabayClient] Timeout searching '{keyword}'")
            return None
        except Exception as e:
            logger.error(f"[PixabayClient] Unexpected error: {e}")
            return None

    def filter_banned_hits(self, hits: list[dict]) -> list[dict]:
        """Filter out banned video IDs and abstract tags."""
        filtered = []
        for hit in hits:
            video_id = hit.get("id", 0)
            if str(video_id) in BANNED_VIDEO_IDS or video_id in BANNED_VIDEO_IDS:
                logger.warning(f"[PixabayClient] Rejecting banned video ID: {video_id}")
                continue
            tags = str(hit.get("tags", "")).lower()
            if any(banned in tags for banned in BANNED_TAGS):
                logger.warning(f"[PixabayClient] Rejecting abstract banned tags '{tags}' for video {video_id}")
                continue
            filtered.append(hit)
        return filtered

    def _select_best_video(self, hits: list[dict]) -> Optional[tuple[str, int]]:
        """Pick highest resolution video under 1920px, shortest duration under 10s.

        Pixabay response has 'videos' dict with keys: large, medium, small, tiny.
        Each has: url, width, height, size (bytes).
        Also 'duration' at the hit level.

        Returns (download_url, video_id) or None.
        """
        MAX_DURATION = 10  # seconds
        MAX_HEIGHT = 1920

        best_url: Optional[str] = None
        best_id: int = 0
        best_score: float = -1  # higher is better (resolution)

        valid_hits = self.filter_banned_hits(hits)
        for hit in valid_hits:
            video_id = hit.get("id", 0)


            duration = hit.get("duration", 0)
            if duration > MAX_DURATION:
                continue

            videos = hit.get("videos", {})

            # Try resolution tiers from highest to lowest
            for tier in ("large", "medium", "small"):
                tier_data = videos.get(tier, {})
                url = tier_data.get("url", "")
                height = tier_data.get("height", 0)
                width = tier_data.get("width", 0)

                if not url or height > MAX_HEIGHT:
                    continue

                # Score: prefer highest resolution, shorter duration
                resolution_score = width * height
                duration_penalty = duration * 1000  # slight preference for shorter
                score = resolution_score - duration_penalty

                if score > best_score:
                    best_score = score
                    best_url = url
                    best_id = video_id

        if best_url:
            return (best_url, best_id)
        return None

    async def _download_video(
        self, client: httpx.AsyncClient, url: str, keyword: str
    ) -> Optional[str]:
        """Stream-download video to temp file. Abort if exceeds max size."""
        os.makedirs(self._download_dir, exist_ok=True)

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
