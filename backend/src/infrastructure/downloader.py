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
    android_creator,web_safari,android,mweb delivers full 4K/1080p/720p HD streams without triggering bot page reload challenges or GVS PO Token blocks."""
    if has_cookies:
        return ["--extractor-args", "youtube:player_client=web_safari,mweb,tv,ios"]
    return ["--extractor-args", "youtube:player_client=android_creator,android,web_safari,mweb"]


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
                return True, title, min(120.0, float(settings.MAX_VIDEO_DURATION))
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
                return True, title, min(120.0, float(settings.MAX_VIDEO_DURATION))

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
                return True, o_title, min(120.0, float(settings.MAX_VIDEO_DURATION))
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
        Download video YouTube dengan arsitektur 4-layer (yt-dlp + aria2c + FFmpeg normalization).
        Target utama: 1080p H.264 (AVC1) + AAC untuk proses pipeline tercepat dan kualitas HD optimal.
        """
        clean_url = get_canonical_youtube_url(url) or url.strip()
        logger.info(f"[AutoCliper Downloader] Memulai download: {clean_url} → {output_path}")

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
            "--retries", "10",
            "--fragment-retries", "10",
        ]

        # Check aria2c multi-connection download engine
        aria2c_cmd = _get_aria2c_cmd()
        if settings.USE_ARIA2C and aria2c_cmd:
            logger.info(f"[AutoCliper Downloader] Menggunakan aria2c accelerator ({aria2c_cmd}) dengan 16 koneksi paralel.")
            cmd.extend([
                "--downloader", "aria2c",
                "--downloader-args", "aria2c:-x 16 -s 16 -k 1M -j 16 --max-tries=10 --retry-wait=5 --summary-interval=0",
            ])
        else:
            cmd.extend(["--concurrent-fragments", "16"])

        cmd.append(clean_url)

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
            logger.error(f"[AutoCliper Downloader] Timeout setelah {settings.DOWNLOAD_TIMEOUT}s")
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise TimeoutError(
                f"Download timeout setelah {settings.DOWNLOAD_TIMEOUT // 60} menit"
            )

        if proc.returncode != 0:
            err = stderr.decode().strip()
            # If 403 / SABR / unavailable / bot challenge / ffmpeg code 183 occurs, retry with alternative client tiers
            # Tier A uses cookies, Tier B drops cookies (critical bypass if cookies cause IP-lockout 403 or HLS segment failure)
            client_tiers = [
                ("youtube:player_client=web_safari,mweb,tv,ios", _get_cookie_args()),
                ("youtube:player_client=android_creator,android,web_safari", _get_cookie_args()),
                ("youtube:player_client=android_creator,android,web_safari", []),
                ("youtube:player_client=android_creator,android,android_sdkless", []),
                ("youtube:player_client=visionos,web_safari", []),
                ("youtube:player_client=tv_embedded,mweb", []),
            ]
            for client_arg, active_cookie_args in client_tiers:
                cookie_label = "with cookies" if active_cookie_args else "without cookies"
                logger.warning(f"[AutoCliper Downloader] Mencoba download fallback dengan {client_arg} ({cookie_label})...")
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
                    clean_url,
                ]
                try:
                    retry_proc = await asyncio.create_subprocess_exec(
                        *retry_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=env,
                    )
                    r_stdout, r_stderr = await asyncio.wait_for(
                        retry_proc.communicate(), timeout=settings.DOWNLOAD_TIMEOUT
                    )
                    if retry_proc.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                        logger.info(f"[AutoCliper Downloader] Fallback download berhasil dengan {client_arg} ({cookie_label})!")
                        await self._validate_media_file(output_path)
                        return True
                    err = r_stderr.decode().strip()
                except Exception as ex:
                    logger.debug(f"[AutoCliper Downloader] Retry {client_arg} error: {ex}")

            logger.error(f"[AutoCliper Downloader] Gagal mengunduh: {err[:300]}")
            raise RuntimeError(f"Download gagal: {err[:300]}")

        # Layer 3 & 4 Validation: Verify output video specs with ffprobe
        await self._validate_media_file(output_path)
        return True

    async def _validate_media_file(self, file_path: str) -> None:
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
        except Exception as e:
            logger.debug(f"[AutoCliper Downloader] ffprobe validation non-fatal error: {e}")
