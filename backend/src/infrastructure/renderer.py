"""FFmpegRenderer — Video trimming only (subtitle/hook handled by Remotion)."""
import asyncio
import logging
import os

from src.domain.entities import Clip
from src.domain.interfaces import IRenderer
from src.infrastructure.gpu_encoder import get_video_encoder_args, get_encoder_name
from src.infrastructure.media_timeline import timeline_is_safe

logger = logging.getLogger(__name__)


class FFmpegRenderer(IRenderer):
    async def trim_clip(
        self,
        video_path: str,
        clip: Clip,
        output_path: str,
        normalize_timestamps: bool = False,
    ) -> bool:
        """
        Trim video segment menggunakan FFmpeg dengan PRECISE seeking.
        Re-encodes video for exact frame alignment (critical for subtitle sync).
        Uses NVENC GPU if available, falls back to libx264.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        duration = clip.end - clip.start
        encoder_args = get_video_encoder_args("medium")

        if normalize_timestamps:
            # Uploaded containers (especially MOV/MKV and phone recordings) may
            # have non-zero or discontinuous stream timestamps. Re-encoding only
            # the video while copying audio can retain an audio offset after a
            # non-zero seek. Reset both timelines and resample audio onto a clean
            # zero-based clock before word-level transcription and Remotion.
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(clip.start),
                "-i", video_path,
                "-t", str(duration),
                "-map", "0:v:0",
                "-map", "0:a:0?",
                "-vf", "setpts=PTS-STARTPTS",
                *encoder_args,
                "-c:a", "aac",
                "-b:a", "192k",
                "-af", "aresample=async=1:first_pts=0,asetpts=PTS-STARTPTS",
                "-movflags", "+faststart",
                output_path,
            ]
        else:
            # Preserve the existing YouTube path exactly.
            cmd = [
                "ffmpeg",
                "-ss", str(clip.start),
                "-i", video_path,
                "-t", str(duration),
                *encoder_args,
                "-c:a", "copy",
                "-avoid_negative_ts", "make_zero",
                "-movflags", "+faststart",
                "-y",
                output_path,
            ]

        logger.info(
            f"Trimming clip #{clip.rank}: {clip.start:.1f}s → {clip.end:.1f}s "
            f"({duration:.1f}s) → {output_path} [{get_encoder_name()}, "
            f"timeline={'normalized' if normalize_timestamps else 'preserved'}]"
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

        if os.path.exists(output_path) and not timeline_is_safe(
            output_path,
            expected_duration=duration,
        ):
            raise RuntimeError(
                f"FFmpeg trim menghasilkan timeline audio/video tidak sinkron untuk clip #{clip.rank}"
            )

        logger.info(f"Clip #{clip.rank} berhasil di-trim → {output_path}")
        return True
