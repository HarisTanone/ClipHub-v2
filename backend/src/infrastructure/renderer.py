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
        Trim video segment menggunakan FFmpeg dengan PRECISE seeking.
        Re-encodes video for exact frame alignment (critical for subtitle sync).
        Audio copied precisely (unaffected by keyframe seek).
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        duration = clip.end - clip.start

        # -ss BEFORE -i = fast seek (to nearest keyframe)
        # Then re-encode video from exact timestamp (not stream copy)
        # This ensures subtitle timestamps match audio precisely
        cmd = [
            "ffmpeg",
            "-ss", str(clip.start),
            "-i", video_path,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "copy",
            "-avoid_negative_ts", "make_zero",
            "-movflags", "+faststart",
            "-y",
            output_path,
        ]

        logger.info(
            f"Trimming clip #{clip.rank}: {clip.start:.1f}s → {clip.end:.1f}s "
            f"({duration:.1f}s) → {output_path} [re-encode mode]"
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        # Dynamic timeout: 2x clip duration + 30s buffer (minimum 60s)
        trim_timeout = max(60, int(duration * 2 + 30))
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=trim_timeout)
        except asyncio.TimeoutError:
            proc.kill()
            logger.error(f"FFmpeg trim timeout after {trim_timeout}s for clip #{clip.rank} ({duration:.1f}s)")
            raise RuntimeError(
                f"FFmpeg trim timeout ({trim_timeout}s) for {duration:.1f}s clip"
            )

        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error(f"FFmpeg trim gagal untuk clip #{clip.rank}: {err[:300]}")
            raise RuntimeError(
                f"FFmpeg trim gagal: {err[:300]}"
            )

        logger.info(f"Clip #{clip.rank} berhasil di-trim → {output_path}")
        return True
