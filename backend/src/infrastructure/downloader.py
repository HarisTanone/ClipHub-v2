import asyncio
import json
import logging
import os
import re
import shutil
import sys
from typing import Optional

from src.config import settings
from src.domain.interfaces import IDownloader

logger = logging.getLogger(__name__)

# Pattern YouTube URL
YOUTUBE_PATTERN = re.compile(
    r"(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/shorts/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})"
)

# Hierarchical format preference enforcing >= 720p HD quality (never below 720p):
# Layer 1: 1080p H.264 (avc1) + AAC (mp4a) -> Primary target for optimal decode/encode speed & HD quality
# Layer 2: 1080p AV1 (av01) + AAC
# Layer 3: 1080p VP9 + AAC / Opus
# Layer 4: 1080p any codec + audio
# Layer 5: Higher than 1080p (1440p / 2160p) + bestaudio
# Layer 6: 720p H.264 (avc1) + AAC
# Layer 7: 720p AV1 / VP9 + audio
# Layer 8: Any stream with height >= 720
YOUTUBE_FORMAT_SELECTOR = (
    "bestvideo[height=1080][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
    "bestvideo[height=1080][vcodec^=av01]+bestaudio[acodec^=mp4a]/"
    "bestvideo[height=1080][vcodec^=vp9]+bestaudio[acodec^=mp4a]/"
    "bestvideo[height=1080]+bestaudio[acodec^=mp4a]/"
    "bestvideo[height=1080]+bestaudio/"
    "bestvideo[height>=1080]+bestaudio/"
    "bestvideo[height>=720][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
    "bestvideo[height>=720][vcodec^=av01]+bestaudio[acodec^=mp4a]/"
    "bestvideo[height>=720]+bestaudio[acodec^=mp4a]/"
    "bestvideo[height>=720]+bestaudio/"
    "best[height>=720]/"
    "bestvideo+bestaudio/best"
)
YOUTUBE_FORMAT_SORT = "res:1080,fps:60,vcodec:avc1,vcodec:av01,vcodec:vp9,br,size"


def extract_youtube_video_id(url: str) -> Optional[str]:
    """Extract clean 11-char YouTube video ID from any URL, share link, or dirty pasted text."""
    if not url:
        return None
    raw = str(url).strip()
    match = YOUTUBE_PATTERN.search(raw)
    if match:
        return match.group(1)
    # Check if raw string is an 11-char video ID directly
    if len(raw) == 11 and re.match(r"^[a-zA-Z0-9_-]{11}$", raw):
        return raw
    return None


def get_canonical_youtube_url(url: str) -> Optional[str]:
    """Normalize any pasted YouTube string into canonical https://www.youtube.com/watch?v={id}."""
    vid = extract_youtube_video_id(url)
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"
    return None


def _get_ytdlp_cmd() -> str:
    venv_bin = os.path.join(os.path.dirname(sys.executable), "yt-dlp")
    return venv_bin if os.path.exists(venv_bin) else "yt-dlp"


def _get_aria2c_cmd() -> Optional[str]:
    """Locate aria2c binary in system path or standard directories."""
    found = shutil.which("aria2c")
    if found:
        return found
    for p in ["/opt/homebrew/bin/aria2c", "/usr/bin/aria2c", "/usr/local/bin/aria2c"]:
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p
    return None


def _get_cookie_args() -> list[str]:
    """Retrieve cookies args from settings, local cookies.txt, backend cookies.txt, or macOS browser."""
    cookies_path = getattr(settings, "YOUTUBE_COOKIES_PATH", "")
    if cookies_path and os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 0:
        return ["--cookies", cookies_path]
    backend_cookies = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../cookies.txt")
    )
    if os.path.exists(backend_cookies) and os.path.getsize(backend_cookies) > 0:
        return ["--cookies", backend_cookies]
    if os.path.exists("cookies.txt") and os.path.getsize("cookies.txt") > 0:
        return ["--cookies", "cookies.txt"]
    if sys.platform == "darwin":
        return ["--cookies-from-browser", "chrome"]
    return []


def _get_extractor_args(has_cookies: bool = False) -> list[str]:
    """Extractor arguments.
    visionos,web_creator,web_safari,mweb delivers full 4K/1080p/720p HD streams without triggering GVS 360p caps or bot challenge lockouts."""
    if has_cookies:
        return ["--extractor-args", "youtube:player_client=web_creator,web_safari,mweb,ios"]
    return ["--extractor-args", "youtube:player_client=visionos,web_safari,mweb,web"]


class YouTubeDownloader(IDownloader):
    async def validate_url(
        self, url: str
    ) -> tuple[bool, Optional[str], Optional[float]]:
        """
        Validasi URL YouTube.
        Returns: (is_valid, error_message, duration_seconds)
        """
        if not url or not str(url).strip():
            return False, "URL tidak boleh kosong", None

        video_id = extract_youtube_video_id(url)
        if not video_id:
            return False, "Format URL tidak valid. Gunakan link YouTube (youtube.com/watch?v= atau youtu.be/)", None

        clean_url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            ytdlp_cmd = _get_ytdlp_cmd()

            env = os.environ.copy()
            homebrew_bin = "/opt/homebrew/bin"
            if homebrew_bin not in env.get("PATH", ""):
                env["PATH"] = f"{homebrew_bin}:{env.get('PATH', '')}"

            cookie_args = _get_cookie_args()
            extractor_args = _get_extractor_args(has_cookies=bool(cookie_args))

            cmd_args = [
                ytdlp_cmd,
                "--geo-bypass",
                *extractor_args,
                *cookie_args,
                "--no-download",
                "--print", "%(duration)s\n%(title)s",
                "--no-warnings",
                clean_url,
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
            # Fallback to oEmbed validation on timeout
            oembed_ok, title = await self._validate_via_oembed(video_id)
            if oembed_ok:
                return True, title, float(settings.MAX_VIDEO_DURATION)
            return False, "Timeout saat memverifikasi video (30 detik)", None
        except FileNotFoundError:
            return False, "yt-dlp tidak ditemukan di sistem", None

        if proc.returncode != 0:
            err = stderr.decode().strip()

            # YouTube datacenter IP challenge (BotGuard) often causes yt-dlp to report "Video unavailable"
            # Always verify with official YouTube oEmbed API first before rejecting!
            oembed_ok, title = await self._validate_via_oembed(video_id)
            if oembed_ok:
                logger.info(f"validate_url: yt-dlp challenged on VPS, successfully verified via official oEmbed: {title}")
                return True, title, float(settings.MAX_VIDEO_DURATION)

            if "Private video" in err or "private" in err.lower():
                return False, "Video bersifat private dan tidak dapat diakses", None
            if "unavailable" in err.lower() or "not available" in err.lower():
                return False, "Video tidak tersedia atau telah dihapus dari YouTube", None

            return False, f"Video tidak dapat diverifikasi: {err[:200]}", None

        try:
            lines = stdout.decode().strip().split("\n")
            duration = float(lines[0].strip())
            title = lines[1].strip() if len(lines) > 1 else ""
        except (ValueError, TypeError, IndexError):
            # Fallback to oEmbed
            oembed_ok, o_title = await self._validate_via_oembed(video_id)
            if oembed_ok:
                return True, o_title, float(settings.MAX_VIDEO_DURATION)
            return False, "Gagal membaca durasi video", None

        if duration > settings.MAX_VIDEO_DURATION:
            menit = int(duration // 60)
            return (
                False,
                f"Video terlalu panjang ({menit} menit). Maksimal 60 menit.",
                duration,
            )

        return True, title, duration

    async def _validate_via_oembed(self, video_id: str) -> tuple[bool, str]:
        """Official YouTube oEmbed validation fallback (100% resilient on datacenter VPS)."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(
                    f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    title = data.get("title") or f"YouTube Video ({video_id})"
                    return True, title
        except Exception as e:
            logger.debug(f"oEmbed fallback error: {e}")
        return False, ""

    async def download_video(self, url: str, output_path: str) -> bool:
        """
        Download video YouTube dengan 3 Engine Terpisah (Multi-Tool Fallback):
        1. Engine 1: yt-dlp Multi-Tier HD Engine (1080p -> 720p) + aria2c / concurrent stream
        2. Engine 2: Native Python Pytubefix HD Engine (Adaptive stream + FFmpeg AAC Mux)
        3. Engine 3: Cobalt API (Self-Hosted / Fast REST Downloader)
        4. Engine 4: VidKraken API (Secondary Cloud Backup)

        Aturan Mutlak: Minimal resolusi harus 720p (HD) s/d 1080p. Jika di bawah 720p,
        file ditolak dan otomatis berpindah ke fallback engine berikutnya.
        """
        clean_url = get_canonical_youtube_url(url) or url.strip()
        logger.info(f"[AutoCliper Downloader] Memulai download HD: {clean_url} → {output_path}")

        # ─── ENGINE 1: yt-dlp Multi-Tier HD Engine ────────────────────────────────
        try:
            logger.info(f"[AutoCliper Downloader] [Engine 1/3: yt-dlp HD] Mencoba mengunduh {clean_url}...")
            ytdlp_ok = await self._download_via_ytdlp(clean_url, output_path)
            if ytdlp_ok and await self._is_valid_hd_file(output_path):
                logger.info(f"[AutoCliper Downloader] [Engine 1/3: yt-dlp] SUKSES mengunduh video HD! → {output_path}")
                return True
        except Exception as e_ytdlp:
            logger.warning(f"[AutoCliper Downloader] [Engine 1/3: yt-dlp] Gagal ({e_ytdlp}). Beralih ke Engine 2...")

        # Pastikan file non-HD/corrupt dibersihkan sebelum engine berikutnya
        self._cleanup_file(output_path)

        # ─── ENGINE 2: Native Python Pytubefix HD Engine ──────────────────────────
        try:
            from src.infrastructure.pytubefix_downloader import PytubefixDownloader
            logger.info(f"[AutoCliper Downloader] [Engine 2/3: Pytubefix HD] Mencoba mengunduh {clean_url}...")
            pytube_dl = PytubefixDownloader()
            pytube_ok = await pytube_dl.download_video(clean_url, output_path)
            if pytube_ok and await self._is_valid_hd_file(output_path):
                logger.info(f"[AutoCliper Downloader] [Engine 2/3: Pytubefix] SUKSES mengunduh video HD! → {output_path}")
                return True
        except Exception as e_pytube:
            logger.warning(f"[AutoCliper Downloader] [Engine 2/3: Pytubefix] Gagal ({e_pytube}). Beralih ke Engine 3...")

        self._cleanup_file(output_path)

        # ─── ENGINE 3: Cobalt API (Self-Hosted / Fast Microservice) ───────────────
        try:
            from src.infrastructure.cobalt_client import CobaltClient
            cobalt_cl = CobaltClient()
            if cobalt_cl.is_enabled:
                logger.info(f"[AutoCliper Downloader] [Engine 3/3: Cobalt HD] Mencoba mengunduh {clean_url} via {cobalt_cl.base_url}...")
                cobalt_ok = await cobalt_cl.download_video(clean_url, output_path)
                if cobalt_ok and await self._is_valid_hd_file(output_path):
                    logger.info(f"[AutoCliper Downloader] [Engine 3/3: Cobalt API] SUKSES mengunduh video HD! → {output_path}")
                    return True
        except Exception as e_cobalt:
            logger.warning(f"[AutoCliper Downloader] [Engine 3/3: Cobalt API] Gagal ({e_cobalt}).")

        self._cleanup_file(output_path)

        # ─── ENGINE 4 (Optional Backup): VidKraken API ────────────────────────────
        try:
            from src.infrastructure.vidkraken_client import VidKrakenClient
            vk_client = VidKrakenClient()
            if vk_client.is_enabled:
                logger.info(f"[AutoCliper Downloader] [Engine Backup: VidKraken] Mencoba mengunduh {clean_url}...")
                vk_ok = await vk_client.download_video(clean_url, output_path)
                if vk_ok and await self._is_valid_hd_file(output_path):
                    logger.info(f"[AutoCliper Downloader] [Engine Backup: VidKraken] SUKSES mengunduh video HD! → {output_path}")
                    return True
        except Exception as e_vk:
            logger.warning(f"[AutoCliper Downloader] [Engine Backup: VidKraken] Gagal ({e_vk}).")

        self._cleanup_file(output_path)

        logger.error(f"[AutoCliper Downloader] Semua engine download (yt-dlp, pytubefix, Cobalt, VidKraken) gagal menghasilkan video HD (>= 720p).")
        raise RuntimeError(f"Gagal mengunduh video YouTube dalam format HD (minimal 720p - 1080p). Seluruh fallback downloader gagal.")

    def _cleanup_file(self, path: str) -> None:
        """Hapus file jika ada dan tidak memenuhi syarat HD."""
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    async def _is_valid_hd_file(self, output_path: str) -> bool:
        """Validasi bahwa file video terunduh dan resolusinya minimal 720p."""
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return False
        h = await self._validate_media_file(output_path)
        if h is not None and h >= 720:
            return True
        logger.warning(f"[AutoCliper Downloader] Resolusi video terdeteksi ({h}p) di bawah batas HD (720p). Menolak file dan beralih ke fallback lain...")
        self._cleanup_file(output_path)
        return False

    async def _download_via_ytdlp(self, clean_url: str, output_path: str) -> bool:
        """Download via yt-dlp dengan rotasi client tier HD."""
        ytdlp_cmd = _get_ytdlp_cmd()

        env = os.environ.copy()
        homebrew_bin = "/opt/homebrew/bin"
        if homebrew_bin not in env.get("PATH", ""):
            env["PATH"] = f"{homebrew_bin}:{env.get('PATH', '')}"

        cookie_args = _get_cookie_args()
        extractor_args = _get_extractor_args(has_cookies=bool(cookie_args))

        cmd = [
            ytdlp_cmd,
            "--geo-bypass",
            *extractor_args,
            *cookie_args,
            "--format-sort", YOUTUBE_FORMAT_SORT,
            "-f", YOUTUBE_FORMAT_SELECTOR,
            "--merge-output-format", "mp4",
            "--postprocessor-args", "merger:-c:v copy -c:a aac -b:a 192k",
            "-o", output_path,
            "--no-warnings",
            "--retries", "5",
            "--fragment-retries", "5",
        ]

        aria2c_cmd = _get_aria2c_cmd()
        if settings.USE_ARIA2C and aria2c_cmd:
            cmd.extend([
                "--downloader", "aria2c",
                "--downloader-args", "aria2c:-x 4 -s 4 -k 1M -j 4 --max-tries=3 --retry-wait=2 --summary-interval=0",
            ])
        else:
            cmd.extend(["--concurrent-fragments", "8"])

        cmd.append(clean_url)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            await asyncio.wait_for(proc.communicate(), timeout=settings.DOWNLOAD_TIMEOUT)
            if proc.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
        except Exception as e:
            logger.debug(f"[yt-dlp Engine] Primary tier error: {e}")

        # Alternative HD client tiers
        client_tiers = [
            ("youtube:player_client=web_creator,web_safari,mweb", _get_cookie_args()),
            ("youtube:player_client=visionos,web_safari,mweb", []),
            ("youtube:player_client=visionos,web", []),
            ("youtube:player_client=web_safari,mweb,ios", _get_cookie_args()),
        ]

        for client_arg, active_cookie_args in client_tiers:
            retry_cmd = [
                ytdlp_cmd,
                "--geo-bypass",
                "--extractor-args", client_arg,
                *active_cookie_args,
                "--format-sort", YOUTUBE_FORMAT_SORT,
                "-f", YOUTUBE_FORMAT_SELECTOR,
                "--merge-output-format", "mp4",
                "--postprocessor-args", "merger:-c:v copy -c:a aac -b:a 192k",
                "-o", output_path,
                "--no-warnings",
                "--retries", "3",
                "--fragment-retries", "3",
                "--concurrent-fragments", "8",
                clean_url,
            ]
            try:
                retry_proc = await asyncio.create_subprocess_exec(
                    *retry_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                await asyncio.wait_for(retry_proc.communicate(), timeout=settings.DOWNLOAD_TIMEOUT)
                if retry_proc.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return True
            except Exception as ex:
                logger.debug(f"[yt-dlp Engine] Retry {client_arg} error: {ex}")

        return False

    async def _validate_media_file(self, file_path: str) -> Optional[int]:
        """Memverifikasi file hasil unduhan dengan ffprobe (resolusi, codec, durasi, bitrate)."""
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            raise RuntimeError(f"File hasil unduhan tidak ditemukan atau kosong: {file_path}")

        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,codec_name,bit_rate,r_frame_rate:format=duration,size",
                "-of", "json",
                file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                data = json.loads(stdout.decode())
                streams = data.get("streams", [])
                fmt = data.get("format", {})
                if streams:
                    v = streams[0]
                    w = v.get("width")
                    h = v.get("height")
                    codec = v.get("codec_name")
                    fps = v.get("r_frame_rate", "30/1")
                    size_mb = round(int(fmt.get("size", 0)) / (1024 * 1024), 2)
                    dur = round(float(fmt.get("duration", 0)), 1)
                    logger.info(
                        f"[AutoCliper Downloader] Verifikasi Sukses: {w}x{h} @ {fps}fps "
                        f"(Codec: {codec}, Ukuran: {size_mb} MB, Durasi: {dur}s) → {file_path}"
                    )
                    return int(h) if h else None
        except Exception as e:
            logger.debug(f"[AutoCliper Downloader] ffprobe validation non-fatal error: {e}")
        return None
