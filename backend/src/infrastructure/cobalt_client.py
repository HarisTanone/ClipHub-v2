"""Cobalt Video Downloader API Client (Self-Hosted / Fallback).

Integrates with Cobalt API (open-source video downloader) for fast, direct HD video downloads:
- Native 1080p and 720p resolution requests
- Bypasses YouTube datacenter bot detection
- Direct HTTP streaming to target output file
"""
import asyncio
import logging
import os
import shutil
import httpx
from typing import Optional
from src.config import settings

logger = logging.getLogger(__name__)


class CobaltClient:
    """Client for downloading YouTube videos via Cobalt REST API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.base_url = (base_url or getattr(settings, "COBALT_API_URL", "http://localhost:9000") or "http://localhost:9000").rstrip("/")
        self.timeout = timeout or getattr(settings, "COBALT_TIMEOUT", 180)

    @property
    def is_enabled(self) -> bool:
        return bool(getattr(settings, "COBALT_ENABLED", True) and self.base_url)

    async def check_health(self) -> bool:
        """Check if Cobalt instance is reachable and healthy."""
        if not self.is_enabled:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/serverInfo")
                return resp.status_code == 200
        except Exception:
            return False

    async def _request_download_url(self, clean_url: str, quality: str = "1080") -> str:
        """Send download request to Cobalt API."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "url": clean_url,
            "videoQuality": quality,  # "1080", "720"
            "youtubeVideoCodec": "h264",
            "downloadMode": "auto",
            "audioFormat": "mp3",
        }

        async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
            resp = await client.post(
                f"{self.base_url}/",
                headers=headers,
                json=payload,
            )
            if resp.status_code != 200:
                text = resp.text
                raise RuntimeError(f"Cobalt API error {resp.status_code}: {text[:200]}")

            data = resp.json()
            status = data.get("status")

            if status in ("redirect", "tunnel"):
                stream_url = data.get("url")
                if not stream_url:
                    raise RuntimeError("Cobalt response did not contain download URL")
                return stream_url
            elif status == "picker":
                picker = data.get("picker", [])
                if picker and isinstance(picker, list):
                    return picker[0].get("url", "")
                raise RuntimeError("Cobalt returned empty picker list")
            elif status == "error":
                err_text = data.get("text", "Unknown Cobalt error")
                raise RuntimeError(f"Cobalt returned error: {err_text}")
            else:
                stream_url = data.get("url")
                if stream_url:
                    return stream_url
                raise RuntimeError(f"Unexpected Cobalt status: {status}")

    async def _stream_to_file(self, stream_url: str, output_path: str) -> None:
        """Stream direct media from URL into local file."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        temp_path = f"{output_path}.cobalt_tmp"

        async with httpx.AsyncClient(timeout=float(self.timeout), follow_redirects=True) as client:
            async with client.stream("GET", stream_url) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"Cobalt CDN returned HTTP {resp.status_code}")

                total_bytes = 0
                with open(temp_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
                        total_bytes += len(chunk)

                if total_bytes == 0:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    raise RuntimeError("Cobalt stream returned 0 bytes")

                shutil.move(temp_path, output_path)

    async def download_video(self, clean_url: str, output_path: str) -> bool:
        """Download YouTube video via Cobalt with 1080p -> 720p quality hierarchy."""
        if not self.is_enabled:
            return False

        logger.info(f"[Cobalt Downloader] Starting download for: {clean_url}")
        
        # 1. Attempt 1080p
        try:
            logger.info("[Cobalt Downloader] Requesting 1080p stream...")
            dl_url_1080 = await self._request_download_url(clean_url, quality="1080")
            await self._stream_to_file(dl_url_1080, output_path)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"[Cobalt Downloader] 1080p download completed -> {output_path}")
                return True
        except Exception as e1080:
            logger.warning(f"[Cobalt Downloader] 1080p attempt failed ({e1080}). Retrying with 720p...")

        # 2. Attempt 720p
        try:
            logger.info("[Cobalt Downloader] Requesting 720p stream...")
            dl_url_720 = await self._request_download_url(clean_url, quality="720")
            await self._stream_to_file(dl_url_720, output_path)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"[Cobalt Downloader] 720p download completed -> {output_path}")
                return True
        except Exception as e720:
            logger.warning(f"[Cobalt Downloader] 720p attempt failed ({e720})")
            raise RuntimeError(f"Cobalt download failed: {e720}")

        return False
