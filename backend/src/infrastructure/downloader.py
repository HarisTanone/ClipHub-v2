"""YouTubeDownloader — yt-dlp subprocess wrapper."""
import asyncio
import logging
import re
from typing import Optional

from src.config import settings
from src.domain.interfaces import IDownloader

logger = logging.getLogger(__name__)

# Pattern YouTube URL
YOUTUBE_PATTERN = re.compile(
    r"(youtube\.com/watch\?v=|youtu\.be/)([\w\-]{11})"
)


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
            import os
            import sys
            venv_bin = os.path.join(os.path.dirname(sys.executable), "yt-dlp")
            ytdlp_cmd = venv_bin if os.path.exists(venv_bin) else "yt-dlp"

            env = os.environ.copy()
            homebrew_bin = "/opt/homebrew/bin"
            if homebrew_bin not in env.get("PATH", ""):
                env["PATH"] = f"{homebrew_bin}:{env.get('PATH', '')}"

            # Build command — only use cookies on local (Mac with Chrome)
            cmd_args = [ytdlp_cmd]
            if sys.platform == "darwin":
                cmd_args += ["--cookies-from-browser", "chrome"]
            cmd_args += [
                "--geo-bypass",
                "--no-download",
                "--print", "duration",
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
            duration = float(stdout.decode().strip())
        except (ValueError, TypeError):
            return False, "Gagal membaca durasi video", None

        if duration > settings.MAX_VIDEO_DURATION:
            menit = int(duration // 60)
            return (
                False,
                f"Video terlalu panjang ({menit} menit). Maksimal 60 menit.",
                duration,
            )

        return True, None, duration

    async def download_video(self, url: str, output_path: str) -> bool:
        """Download video YouTube menggunakan yt-dlp (+ aria2c di production)."""
        logger.info(f"Downloading video: {url} → {output_path}")

        import os
        import sys
        # Use venv yt-dlp binary path
        venv_bin = os.path.join(os.path.dirname(sys.executable), "yt-dlp")
        ytdlp_cmd = venv_bin if os.path.exists(venv_bin) else "yt-dlp"

        # Ensure /opt/homebrew/bin in PATH for deno (required by yt-dlp JS solver)
        env = os.environ.copy()
        homebrew_bin = "/opt/homebrew/bin"
        if homebrew_bin not in env.get("PATH", ""):
            env["PATH"] = f"{homebrew_bin}:{env.get('PATH', '')}"

        cmd = [
            ytdlp_cmd,
        ]
        if sys.platform == "darwin":
            cmd += ["--cookies-from-browser", "chrome"]
        cmd += [
            "--geo-bypass",
            "--extractor-args", "youtube:player_client=ios,web",
            "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "--merge-output-format", "mp4",
            "-o", output_path,
            "--no-warnings",
            "--retries", "3",
            "--fragment-retries", "5",
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
            logger.error(f"yt-dlp gagal: {err[:300]}")
            raise RuntimeError(f"Download gagal: {err[:300]}")

        return True
