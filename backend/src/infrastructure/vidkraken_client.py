"""VidKraken Video Downloader Client.

Integrates with VidKraken API v2 for fast, high-quality video downloading:
1. Enqueue download job (tries 1080p first, then 720p on failure)
2. Poll download job status until COMPLETED or FAILED
3. Stream download media from proxy URL to target local file path
"""
import asyncio
import logging
import os
from typing import Any, Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class VidKrakenClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.api_key = api_key or getattr(settings, "VIDKRAKEN_API_KEY", "ce1bcba1-b808-470f-987c-072ca2d35488")
        self.base_url = (base_url or getattr(settings, "VIDKRAKEN_BASE_URL", "https://vidkraken.com/api/v2")).rstrip("/")
        self.timeout = timeout or getattr(settings, "VIDKRAKEN_TIMEOUT", 180)

    @property
    def is_enabled(self) -> bool:
        enabled = getattr(settings, "VIDKRAKEN_ENABLED", True)
        return bool(enabled and self.api_key)

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def enqueue_download(self, url: str, fmt: str = "1080") -> dict[str, Any]:
        """Send download request to VidKraken API.
        
        Endpoint: POST /api/v2/download
        Body: {"url": "<youtube_url>", "format": "<fmt>"}
        """
        endpoint = f"{self.base_url}/download"
        payload = {
            "url": url.strip(),
            "format": str(fmt),
        }
        logger.info(f"[VidKraken] Enqueueing download for {url} with format {fmt}...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(endpoint, json=payload, headers=self._get_headers())
            if resp.status_code not in (200, 201, 202):
                text = resp.text
                logger.warning(f"[VidKraken] Enqueue failed (HTTP {resp.status_code}): {text[:200]}")
                raise RuntimeError(f"VidKraken API error {resp.status_code}: {text[:200]}")
            data = resp.json()
            logger.info(f"[VidKraken] Job enqueued: jobId={data.get('jobId')} status={data.get('status')}")
            return data

    async def poll_job(
        self,
        job_id: str,
        timeout: Optional[int] = None,
        poll_interval: float = 2.0,
    ) -> dict[str, Any]:
        """Poll VidKraken job status until COMPLETED or FAILED.
        
        Endpoint: GET /api/v2/download/{jobId}
        """
        max_timeout = timeout or self.timeout
        endpoint = f"{self.base_url}/download/{job_id}"
        logger.info(f"[VidKraken] Polling job {job_id} (timeout={max_timeout}s)...")

        start_time = asyncio.get_event_loop().time()
        async with httpx.AsyncClient(timeout=20.0) as client:
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > max_timeout:
                    raise TimeoutError(f"VidKraken job {job_id} timed out after {int(elapsed)}s")

                try:
                    resp = await client.get(endpoint, headers=self._get_headers())
                    if resp.status_code == 200:
                        data = resp.json()
                        status = data.get("status", "").upper()

                        if status == "COMPLETED":
                            logger.info(
                                f"[VidKraken] Job {job_id} COMPLETED! "
                                f"Format: {data.get('actualFormat') or data.get('format')} "
                                f"Size: {data.get('fileSize')} bytes"
                            )
                            return data
                        elif status in ("FAILED", "ERROR"):
                            msg = data.get("message") or data.get("error") or "Unknown error"
                            logger.warning(f"[VidKraken] Job {job_id} FAILED: {msg}")
                            raise RuntimeError(f"VidKraken job failed: {msg}")
                        else:
                            logger.debug(f"[VidKraken] Job {job_id} in progress ({status})...")
                    else:
                        logger.warning(f"[VidKraken] Poll HTTP {resp.status_code}: {resp.text[:100]}")
                except (httpx.RequestError, httpx.TimeoutException) as e:
                    logger.debug(f"[VidKraken] Network transient error during poll: {e}")

                await asyncio.sleep(poll_interval)

    async def stream_download_file(
        self,
        download_url: str,
        output_path: str,
        timeout: float = 300.0,
    ) -> bool:
        """Stream media file from VidKraken CDN / proxy URL directly to local file."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        temp_path = f"{output_path}.tmp"
        logger.info(f"[VidKraken] Streaming video from {download_url} to {temp_path}...")

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout, connect=30.0),
                follow_redirects=True,
            ) as client:
                async with client.stream("GET", download_url) as resp:
                    if resp.status_code != 200:
                        raise RuntimeError(f"VidKraken CDN returned HTTP {resp.status_code}")

                    total_bytes = 0
                    with open(temp_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                                total_bytes += len(chunk)

            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(temp_path, output_path)
                logger.info(
                    f"[VidKraken] Successfully downloaded {round(total_bytes / (1024*1024), 2)} MB "
                    f"to {output_path}"
                )
                return True
            else:
                raise RuntimeError("VidKraken downloaded file is empty")
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise e

    async def download_video(self, url: str, output_path: str) -> bool:
        """Execute VidKraken download flow with 1080p -> 720p quality hierarchy.
        
        Returns True on success, or raises an Exception to trigger fallback.
        """
        if not self.is_enabled:
            raise RuntimeError("VidKraken is disabled or API key is missing")

        clean_url = url.strip()
        logger.info(f"[VidKraken] Starting download flow for: {clean_url}")

        # Attempt 1: 1080p format
        try:
            logger.info("[VidKraken] Attempting 1080p resolution...")
            job_data = await self.enqueue_download(clean_url, fmt="1080")
            job_id = job_data.get("jobId")
            if not job_id:
                raise RuntimeError("VidKraken did not return a jobId for format 1080")

            completed_data = await self.poll_job(job_id)
            download_url = completed_data.get("downloadUrl")
            if not download_url:
                raise RuntimeError("VidKraken completed job does not contain a downloadUrl")

            return await self.stream_download_file(download_url, output_path)
        except Exception as e1080:
            logger.warning(f"[VidKraken] 1080p download attempt failed: {e1080}. Retrying with 720p...")

        # Attempt 2: 720p format fallback
        try:
            logger.info("[VidKraken] Attempting 720p resolution...")
            job_data = await self.enqueue_download(clean_url, fmt="720")
            job_id = job_data.get("jobId")
            if not job_id:
                raise RuntimeError("VidKraken did not return a jobId for format 720")

            completed_data = await self.poll_job(job_id)
            download_url = completed_data.get("downloadUrl")
            if not download_url:
                raise RuntimeError("VidKraken completed job does not contain a downloadUrl")

            return await self.stream_download_file(download_url, output_path)
        except Exception as e720:
            logger.error(f"[VidKraken] 720p download attempt failed: {e720}")
            raise RuntimeError(f"VidKraken failed for both 1080p and 720p: {e720}")
