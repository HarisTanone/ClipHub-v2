"""Footage Downloader — download video from Pexels/Pixabay/YouTube.

Supports two download strategies:
- Direct: stream download from Pexels/Pixabay embedUrl (chunk-based, not buffered)
- YouTube: yt-dlp with --download-sections for segment extraction

Resource constraints:
- Stream to disk (not buffer in memory)
- Max file size: BROLL_MAX_FOOTAGE_SIZE_MB (50MB default)
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import Optional
from uuid import uuid4

import httpx

from src.config import settings
from src.domain.entities import VideoCandidate

logger = logging.getLogger(__name__)


class FootageDownloader:
    """Download footage from various platforms for B-roll splice.

    Strategies:
    - Pexels/Pixabay: httpx async streaming download from embedUrl
    - YouTube: yt-dlp subprocess with --download-sections
    """

    def __init__(self, output_dir: Optional[str] = None):
        self._output_dir = output_dir or settings.OUTPUT_DIR
        self._max_size_bytes = settings.BROLL_MAX_FOOTAGE_SIZE_MB * 1024 * 1024

    async def download(
        self,
        candidate: VideoCandidate,
        duration_needed: float,
    ) -> Optional[str]:
        """Download footage to a temp file.

        Args:
            candidate: Selected VideoCandidate with source info.
            duration_needed: Required footage duration (seconds) for YouTube trimming.

        Returns:
            Path to downloaded file, or None on failure.
        """
        try:
            if candidate.platform in ("pexels", "pixabay"):
                return await self._download_direct(candidate.embed_url, candidate.id)
            elif candidate.platform == "youtube":
                return await self._download_youtube(
                    candidate.source_url,
                    candidate.start_timestamp,
                    duration_needed,
                    candidate.id,
                )
            else:
                logger.warning(f"footage_dl: unsupported platform '{candidate.platform}'")
                return None
        except Exception as exc:
            logger.warning(f"footage_dl: download failed for '{candidate.id}': {exc}")
            return None

    async def _download_direct(self, url: str, video_id: str) -> Optional[str]:
        """Stream download from direct video URL (Pexels/Pixabay).

        Downloads chunk-by-chunk to disk without buffering entire file in memory.
        Enforces max file size limit.
        """
        if not url:
            return None

        filename = f"footage_raw_{video_id.replace('/', '_')}_{uuid4().hex[:6]}.mp4"
        temp_path = os.path.join(self._output_dir, filename)
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    total_bytes = 0

                    with open(temp_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            total_bytes += len(chunk)
                            if total_bytes > self._max_size_bytes:
                                logger.warning(
                                    f"footage_dl: file too large ({total_bytes // (1024*1024)}MB > "
                                    f"{settings.BROLL_MAX_FOOTAGE_SIZE_MB}MB), aborting: {video_id}"
                                )
                                f.close()
                                os.remove(temp_path)
                                return None
                            f.write(chunk)

            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                logger.info(
                    f"footage_dl: downloaded {total_bytes // 1024}KB from {url[:60]}..."
                )
                return temp_path

        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
            logger.warning(f"footage_dl: direct download failed: {exc}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

        return None

    async def _download_youtube(
        self, url: str, start_ts: int, duration_needed: float, video_id: str
    ) -> Optional[str]:
        """Download YouTube segment via yt-dlp.

        Uses --download-sections to extract only the needed segment,
        minimizing download size and time.
        """
        if not url:
            return None

        filename = f"footage_yt_{video_id.replace('/', '_')}_{uuid4().hex[:6]}.mp4"
        temp_path = os.path.join(self._output_dir, filename)
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)

        # yt-dlp section format: *start-end (seconds)
        end_ts = start_ts + int(duration_needed) + 3  # Extra 3s buffer for trim
        section = f"*{start_ts}-{end_ts}"

        cmd = [
            "yt-dlp",
            "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "--download-sections", section,
            "--merge-output-format", "mp4",
            "--no-playlist",
            "--no-warnings",
            "-o", temp_path,
            url,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            if proc.returncode == 0 and os.path.exists(temp_path):
                size_mb = os.path.getsize(temp_path) / (1024 * 1024)
                if size_mb > settings.BROLL_MAX_FOOTAGE_SIZE_MB:
                    logger.warning(f"footage_dl: YouTube download too large ({size_mb:.1f}MB)")
                    os.remove(temp_path)
                    return None
                logger.info(f"footage_dl: YouTube segment downloaded ({size_mb:.1f}MB)")
                return temp_path
            else:
                error_msg = stderr.decode(errors="replace")[:200] if stderr else "unknown error"
                logger.warning(f"footage_dl: yt-dlp failed (rc={proc.returncode}): {error_msg}")

        except asyncio.TimeoutError:
            logger.warning(f"footage_dl: yt-dlp timed out for {url}")
        except FileNotFoundError:
            logger.warning("footage_dl: yt-dlp not found in PATH")
        except Exception as exc:
            logger.warning(f"footage_dl: YouTube download error: {exc}")

        if os.path.exists(temp_path):
            os.remove(temp_path)
        return None
