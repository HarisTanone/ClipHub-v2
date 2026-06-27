"""MicroSlicer — TAHAP 3: Extract short audio segments from video.

Extracts audio clips based on highlight timestamps with ±padding.
Output: WAV 16kHz mono files optimized for Faster-Whisper transcription.

Architecture:
1. For each highlight, calculate padded boundaries (±3s, clamped to video duration)
2. Use FFmpeg to extract audio segment as WAV (16kHz mono PCM)
3. Return list of AudioSlice with paths and timing metadata
"""
import asyncio
import logging
import os
import subprocess
from typing import Optional

from src.config import settings
from src.domain.entities import AudioSlice
from src.domain.interfaces import IMicroSlicer

logger = logging.getLogger(__name__)


class MicroSlicerError(Exception):
    """Raised when audio extraction fails critically."""
    pass


class MicroSlicer(IMicroSlicer):
    """TAHAP 3 implementation: FFmpeg-based audio extraction per highlight."""

    def __init__(self):
        self._padding = settings.V2_AUDIO_PADDING_SECONDS  # Default: 3.0s

    # ─── Main Entry Point ─────────────────────────────────────────────────────

    async def slice_audio(
        self, video_path: str, highlights: list[dict], output_dir: str, video_duration: float
    ) -> list[AudioSlice]:
        """Extract audio segments for each highlight with ±padding.

        Args:
            video_path: Path to full downloaded video
            highlights: List of dicts with at least {start, end, rank}
            output_dir: Directory to write WAV files
            video_duration: Total video duration for boundary clamping

        Returns:
            List of AudioSlice objects (one per successful extraction)
        """
        if not highlights:
            return []

        if not os.path.exists(video_path):
            raise MicroSlicerError(f"Video file not found: {video_path}")

        os.makedirs(output_dir, exist_ok=True)

        loop = asyncio.get_event_loop()
        slices = []

        for highlight in highlights:
            rank = highlight.get("rank", 0)
            original_start = float(highlight.get("start", 0))
            original_end = float(highlight.get("end", 0))

            # Calculate padded boundaries
            padded_start, padded_end = self._calculate_padded_boundaries(
                original_start, original_end, video_duration
            )
            duration = padded_end - padded_start

            # Output path
            audio_path = os.path.join(output_dir, f"clip_{rank:03d}.wav")

            # Extract audio via FFmpeg
            try:
                success = await loop.run_in_executor(
                    None, self._extract_audio_segment,
                    video_path, padded_start, padded_end, audio_path
                )

                if success and os.path.exists(audio_path):
                    # Verify file is not empty
                    file_size = os.path.getsize(audio_path)
                    if file_size < 1000:  # < 1KB is suspicious
                        logger.warning(
                            f"v2_micro_slicer: clip_{rank:03d}.wav too small ({file_size}B), skipping"
                        )
                        continue

                    slices.append(AudioSlice(
                        clip_rank=rank,
                        audio_path=audio_path,
                        original_start=original_start,
                        original_end=original_end,
                        padded_start=padded_start,
                        padded_end=padded_end,
                        duration=round(duration, 2),
                    ))
                    logger.debug(
                        f"v2_micro_slicer: clip_{rank:03d} extracted "
                        f"[{padded_start:.1f}s-{padded_end:.1f}s] ({duration:.1f}s)"
                    )
                else:
                    logger.warning(f"v2_micro_slicer: FFmpeg failed for clip_{rank:03d}")

            except Exception as e:
                logger.warning(f"v2_micro_slicer: clip_{rank:03d} extraction error: {e}")
                continue

        if not slices:
            raise MicroSlicerError(
                "Semua audio extraction gagal — tidak ada clip yang berhasil dipotong"
            )

        logger.info(f"v2_micro_slicer: {len(slices)}/{len(highlights)} clips extracted successfully")
        return slices

    # ─── Padding Calculation ──────────────────────────────────────────────────

    def _calculate_padded_boundaries(
        self, start: float, end: float, video_duration: float
    ) -> tuple[float, float]:
        """Calculate padded start/end with clamping to video bounds.

        Adds ±padding (default 3s) and clamps to [0, video_duration].
        """
        padded_start = max(0.0, start - self._padding)
        padded_end = min(video_duration, end + self._padding)

        # Ensure minimum duration (at least 5 seconds)
        if padded_end - padded_start < 5.0:
            padded_end = min(video_duration, padded_start + 5.0)

        return round(padded_start, 2), round(padded_end, 2)

    # ─── FFmpeg Audio Extraction ──────────────────────────────────────────────

    def _extract_audio_segment(
        self, video_path: str, start: float, end: float, output_path: str
    ) -> bool:
        """Extract audio segment as WAV 16kHz mono using FFmpeg.

        Output format optimized for Faster-Whisper:
        - Sample rate: 16000 Hz
        - Channels: 1 (mono)
        - Codec: PCM signed 16-bit little-endian
        """
        duration = end - start
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ss", f"{start:.3f}",
            "-t", f"{duration:.3f}",
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            "-loglevel", "error",
            output_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,  # 60s max per clip extraction
            )

            if result.returncode != 0:
                logger.debug(f"FFmpeg stderr: {result.stderr[:200]}")
                return False

            return True

        except subprocess.TimeoutExpired:
            logger.warning(f"FFmpeg timeout extracting {output_path}")
            return False
        except OSError as e:
            logger.error(f"FFmpeg not found or not executable: {e}")
            return False

    # ─── Utility ──────────────────────────────────────────────────────────────

    def cleanup_slices(self, slices: list[AudioSlice]) -> None:
        """Remove all extracted WAV files (call after pipeline completes)."""
        for s in slices:
            try:
                if os.path.exists(s.audio_path):
                    os.remove(s.audio_path)
            except OSError:
                pass
