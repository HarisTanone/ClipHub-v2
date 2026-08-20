import asyncio
import logging
import os
import re
import sys
from typing import Optional

from src.config import settings
from src.domain.interfaces import IDownloader

logger = logging.getLogger(__name__)

# Pattern YouTube URL
YOUTUBE_PATTERN = re.compile(
    r"(youtube\.com/watch\?v=|youtu\.be/)([\w\-]{11})"
)


def _get_ytdlp_cmd() -> str:
    venv_bin = os.path.join(os.path.dirname(sys.executable), "yt-dlp")
    return venv_bin if os.path.exists(venv_bin) else "yt-dlp"


def _get_cookie_args() -> list[str]:
    """Retrieve cookies args from settings, local cookies.txt, or macOS browser."""
    cookies_path = getattr(settings, "YOUTUBE_COOKIES_PATH", "")
    if cookies_path and os.path.exists(cookies_path):
        return ["--cookies", cookies_path]
    if os.path.exists("cookies.txt"):
        return ["--cookies", "cookies.txt"]
    backend_cookies = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../cookies.txt")
    )
    if os.path.exists(backend_cookies):
        return ["--cookies", backend_cookies]
    if sys.platform == "darwin":
        return ["--cookies-from-browser", "chrome"]
    return []


def _get_extractor_args() -> list[str]:
    """Extractor arguments to bypass YouTube 403 Forbidden on cloud/VPS servers."""
    return ["--extractor-args", "youtube:player_client=android,web,web_creator,ios"]


class YouTubeDownloader(IDownloader):
    async def validate_url(
        self, url: str
    ) -> tuple[bool, Optional[str], Optional[float]]:
        """
        Validasi URL YouTube.
        Returns: (is_valid, error_message, duration_seconds)
        """
        if not url or not url.strip():
            return False, "URL tidak boleh kosong", None

        if len(url) > 2048:
            return False, "URL terlalu panjang (maksimal 2048 karakter)", None

        if not YOUTUBE_PATTERN.search(url):
            return False, "Format URL tidak valid. Gunakan youtube.com/watch?v= atau youtu.be/", None

        try:
            ytdlp_cmd = _get_ytdlp_cmd()

            env = os.environ.copy()
            homebrew_bin = "/opt/homebrew/bin"
            if homebrew_bin not in env.get("PATH", ""):
                env["PATH"] = f"{homebrew_bin}:{env.get('PATH', '')}"

            cmd_args = [
                ytdlp_cmd,
                "--geo-bypass",
                *_get_extractor_args(),
                *_get_cookie_args(),
                "--no-download",
                "--print", "%(duration)s\n%(title)s",
                "--no-warnings",
                url,
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=30
            )
        except asyncio.TimeoutError:
            return False, "Timeout saat memverifikasi video (30 detik)", None
        except FileNotFoundError:
            return False, "yt-dlp tidak ditemukan di sistem", None

        if proc.returncode != 0:
            err = stderr.decode().strip()
            if "Private video" in err or "private" in err.lower():
                return False, "Video bersifat private dan tidak dapat diakses", None
            if "unavailable" in err.lower() or "not available" in err.lower():
                return False, "Video tidak tersedia", None
            return False, f"Video tidak dapat diverifikasi: {err[:200]}", None

        try:
            lines = stdout.decode().strip().split("\n")
            duration = float(lines[0].strip())
            title = lines[1].strip() if len(lines) > 1 else ""
        except (ValueError, TypeError, IndexError):
            return False, "Gagal membaca durasi video", None

        if duration > settings.MAX_VIDEO_DURATION:
            menit = int(duration // 60)
            return (
                False,
                f"Video terlalu panjang ({menit} menit). Maksimal 60 menit.",
                duration,
            )

        return True, title, duration

    async def download_video(self, url: str, output_path: str) -> bool:
        """Download video YouTube menggunakan yt-dlp (+ aria2c di production)."""
        logger.info(f"Downloading video: {url} → {output_path}")

        ytdlp_cmd = _get_ytdlp_cmd()

        env = os.environ.copy()
        homebrew_bin = "/opt/homebrew/bin"
        if homebrew_bin not in env.get("PATH", ""):
            env["PATH"] = f"{homebrew_bin}:{env.get('PATH', '')}"

        cmd = [
            ytdlp_cmd,
            "--geo-bypass",
            *_get_extractor_args(),
            *_get_cookie_args(),
            "-f", "bestvideo[height<=2160]+bestaudio/bestvideo+bestaudio/best[height<=2160]/best",
            "--merge-output-format", "mp4",
            "--postprocessor-args", "merger:-c:v copy -c:a aac -b:a 192k",
            "-o", output_path,
            "--no-warnings",
            "--retries", "5",
            "--fragment-retries", "10",
        ]

        # aria2c multi-thread download (production only)
        if settings.USE_ARIA2C:
            cmd.extend([
                "--external-downloader", "aria2c",
                "--external-downloader-args", "-x 16 -s 16 -k 1M",
            ])

        cmd.append(url)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=settings.DOWNLOAD_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.error(f"Download timeout setelah {settings.DOWNLOAD_TIMEOUT}s")
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise TimeoutError(
                f"Download timeout setelah {settings.DOWNLOAD_TIMEOUT // 60} menit"
            )

        if proc.returncode != 0:
            err = stderr.decode().strip()
            # If 403 occurs on first attempt, retry once with fallback format and ios client
            if "403" in err or "Forbidden" in err:
                logger.warning("yt-dlp 403 Forbidden detected; retrying with ios player client fallback...")
                retry_cmd = [
                    ytdlp_cmd,
                    "--geo-bypass",
                    "--extractor-args", "youtube:player_client=ios,android",
                    *_get_cookie_args(),
                    "-f", "bestvideo[height<=2160]+bestaudio/bestvideo+bestaudio/best[height<=2160]/best",
                    "--merge-output-format", "mp4",
                    "--postprocessor-args", "merger:-c:v copy -c:a aac -b:a 192k",
                    "-o", output_path,
                    "--no-warnings",
                    url,
                ]
                retry_proc = await asyncio.create_subprocess_exec(
                    *retry_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                r_stdout, r_stderr = await asyncio.wait_for(
                    retry_proc.communicate(), timeout=settings.DOWNLOAD_TIMEOUT
                )
                if retry_proc.returncode == 0:
                    logger.info("yt-dlp fallback download succeeded!")
                    return True
                err = r_stderr.decode().strip()

            logger.error(f"yt-dlp gagal: {err[:300]}")
            raise RuntimeError(f"Download gagal: {err[:300]}")

        return True
