"""FFmpegRenderer — Video trimming only (subtitle/hook handled by Remotion)."""
import asyncio
import logging
import os

from src.domain.entities import Clip
from src.domain.interfaces import IRenderer

logger = logging.getLogger(__name__)


class FFmpegRenderer(IRenderer):
    async def trim_clip(
        self, video_path: str, clip: Clip, output_path: str
    ) -> bool:
        """
        Trim video segment menggunakan FFmpeg.
        Hanya memotong video — subtitle dan hook overlay akan dihandle oleh Remotion.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        duration = clip.end - clip.start

        # Gunakan -ss sebelum -i untuk fast seeking, lalu -t untuk durasi
        # Stream copy — tidak re-encode, sangat cepat
        cmd = [
            "ffmpeg",
            "-ss", str(clip.start),
            "-i", video_path,
            "-t", str(duration),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-movflags", "+faststart",
            "-y",
            output_path,
        ]

        logger.info(
            f"Trimming clip #{clip.rank}: {clip.start:.1f}s → {clip.end:.1f}s "
            f"({duration:.1f}s) → {output_path}"
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error(f"FFmpeg trim gagal untuk clip #{clip.rank}: {err[:300]}")
            raise RuntimeError(
                f"FFmpeg trim gagal: {err[:300]}"
            )

        logger.info(f"Clip #{clip.rank} berhasil di-trim → {output_path}")
        return True
