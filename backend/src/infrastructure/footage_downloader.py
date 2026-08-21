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
from typing import Any, Optional, Union
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
        # Allow up to 150MB footage chunks to avoid aborting high-quality 1080p/4k stock video
        max_mb = max(150, getattr(settings, "BROLL_MAX_FOOTAGE_SIZE_MB", 50))
        self._max_size_bytes = max_mb * 1024 * 1024

    async def download_segment(
        self,
        url: str,
        start_time: float = 0.0,
        duration: float = 10.0,
        scene_id: Union[int, str] = 1,
        platform: Optional[str] = None,
        video_id: Optional[str] = None,
    ) -> Optional[str]:
        """Download footage segment for a scene.

        Automatically routes:
        - Direct HTTP/HTTPS stream download (Pexels, Pixabay, CDN)
        - yt-dlp with section extraction (YouTube)
        """
        if not url:
            return None

        vid_id = str(video_id or f"scene_{scene_id}")
        is_yt = (
            (platform and platform.lower() == "youtube")
            or "youtube.com" in url
            or "youtu.be" in url
        )

        if is_yt:
            return await self._download_youtube(
                url=url,
                start_ts=int(start_time),
                duration_needed=duration,
                video_id=vid_id,
            )
        else:
            return await self._download_direct(
                url=url,
                video_id=vid_id,
            )

    async def download(
        self,
        candidate: Union[VideoCandidate, dict[str, Any]],
        duration_needed: float = 10.0,
    ) -> Optional[str]:
        """Download footage to a temp file from a VideoCandidate or dict.

        Args:
            candidate: Selected VideoCandidate or candidate dict with source info.
            duration_needed: Required footage duration (seconds) for YouTube trimming.

        Returns:
            Path to downloaded file, or None on failure.
        """
        try:
            if isinstance(candidate, dict):
                platform = candidate.get("platform", "pexels")
                url = (
                    candidate.get("embed_url")
                    or candidate.get("url")
                    or candidate.get("source_url", "")
                )
                vid_id = candidate.get("id") or candidate.get("video_id") or "video"
                start_ts = float(candidate.get("start_timestamp") or 0.0)
            else:
                platform = candidate.platform
                url = (
                    candidate.embed_url
                    or candidate.source_url
                    or getattr(candidate, "url", "")
                )
                vid_id = candidate.id or getattr(candidate, "video_id", "video")
                start_ts = float(candidate.start_timestamp or 0.0)

            return await self.download_segment(
                url=url,
                start_time=start_ts,
                duration=duration_needed,
                platform=platform,
                video_id=vid_id,
            )
        except Exception as exc:
            cand_id = getattr(candidate, "id", None) or (
                candidate.get("id") if isinstance(candidate, dict) else "unknown"
            )
            logger.warning(f"footage_dl: download failed for '{cand_id}': {exc}")
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
            "--geo-bypass",
            "--extractor-args", "youtube:player_client=android,web,web_creator,ios",
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
