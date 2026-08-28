"""Native Python Pytubefix Downloader with FFmpeg Muxing for HD Quality (1080p/720p).

Bypasses YouTube signature cipher and bot checks natively in Python:
- Extracts high-bitrate video stream (1080p / 720p) and best audio stream
- Muxes streams losslessly with FFmpeg AAC audio
- Ensures output is strictly HD (>= 720p)
"""
import asyncio
import logging
import os
import shutil
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)


class PytubefixDownloader:
    """Downloader using pytubefix for standalone YouTube video extraction."""

    async def download_video(self, url: str, output_path: str) -> bool:
        """Download video using pytubefix and merge video/audio with FFmpeg."""
        return await asyncio.to_thread(self._download_sync, url, output_path)

    def _download_sync(self, url: str, output_path: str) -> bool:
        try:
            from pytubefix import YouTube
            from pytubefix.cli import on_progress
        except ImportError:
            logger.warning("[Pytubefix Downloader] pytubefix package is not installed.")
            return False

        logger.info(f"[Pytubefix Downloader] Initializing YouTube stream search for: {url}")
        
        try:
            # Use 'WEB' or 'MWEB' client type for optimal stream availability
            yt = YouTube(url, on_progress_callback=on_progress, client="WEB")
        except Exception as init_err:
            logger.warning(f"[Pytubefix Downloader] Failed initializing YouTube client ({init_err}). Retrying with iOS client...")
            try:
                yt = YouTube(url, client="IOS")
            except Exception as ios_err:
                logger.error(f"[Pytubefix Downloader] Could not fetch video metadata: {ios_err}")
                return False

        # Find best HD video stream (1080p -> 720p)
        video_stream = None
        for target_res in ["1080p", "720p"]:
            # 1. Try MP4 progressive or adaptive
            v = yt.streams.filter(res=target_res, mime_type="video/mp4").first()
            if v:
                video_stream = v
                break
            # 2. Try WEBM adaptive
            v = yt.streams.filter(res=target_res).first()
            if v:
                video_stream = v
                break

        # Fallback: any stream with resolution >= 720p
        if not video_stream:
            for s in yt.streams.filter(only_video=True).order_by("resolution").desc():
                res_str = getattr(s, "resolution", "") or ""
                try:
                    h_val = int(res_str.replace("p", ""))
                    if 720 <= h_val <= 1080:
                        video_stream = s
                        break
                except Exception:
                    continue

        if not video_stream:
            logger.warning(f"[Pytubefix Downloader] No HD video stream (>= 720p) available for {url}")
            return False

        logger.info(f"[Pytubefix Downloader] Selected video stream: {video_stream.resolution} ({video_stream.mime_type}, fps={getattr(video_stream, 'fps', 30)})")

        # If progressive stream (video + audio together)
        if getattr(video_stream, "is_progressive", False):
            temp_dir = tempfile.mkdtemp(prefix="pytubefix_")
            try:
                downloaded_file = video_stream.download(output_path=temp_dir, filename="temp_prog.mp4")
                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                shutil.move(downloaded_file, output_path)
                logger.info(f"[Pytubefix Downloader] Downloaded progressive HD stream -> {output_path}")
                return True
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        # Adaptive stream (separate video and audio) -> download both and mux with FFmpeg
        audio_stream = yt.streams.filter(only_audio=True).order_by("abr").desc().first()
        if not audio_stream:
            logger.warning("[Pytubefix Downloader] No audio stream found.")
            return False

        logger.info(f"[Pytubefix Downloader] Selected audio stream: {getattr(audio_stream, 'abr', 'best')} ({audio_stream.mime_type})")

        temp_dir = tempfile.mkdtemp(prefix="pytubefix_")
        try:
            v_ext = "mp4" if "mp4" in video_stream.mime_type else "webm"
            a_ext = "m4a" if "mp4" in audio_stream.mime_type or "m4a" in audio_stream.mime_type else "webm"
            
            v_file = os.path.join(temp_dir, f"video.{v_ext}")
            a_file = os.path.join(temp_dir, f"audio.{a_ext}")

            logger.info("[Pytubefix Downloader] Downloading video track...")
            video_stream.download(output_path=temp_dir, filename=f"video.{v_ext}")

            logger.info("[Pytubefix Downloader] Downloading audio track...")
            audio_stream.download(output_path=temp_dir, filename=f"audio.{a_ext}")

            if not os.path.exists(v_file) or not os.path.exists(a_file):
                logger.error("[Pytubefix Downloader] Track files missing after download.")
                return False

            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

            # Mux with ffmpeg
            mux_cmd = [
                "ffmpeg",
                "-y",
                "-i", v_file,
                "-i", a_file,
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                output_path,
            ]
            import subprocess
            proc = subprocess.run(mux_cmd, capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                logger.error(f"[Pytubefix Downloader] FFmpeg mux failed: {proc.stderr[:300]}")
                return False

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"[Pytubefix Downloader] Successfully muxed HD video -> {output_path}")
                return True
        except Exception as mux_err:
            logger.error(f"[Pytubefix Downloader] Download/Mux error: {mux_err}")
            return False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return False
