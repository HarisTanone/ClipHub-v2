"""VAD Boundary Adjuster — Snap clip boundaries to nearest silence using Silero VAD.

Prevents cutting speech mid-sentence by finding the closest silence gap
to each clip's start/end point. No window limit — finds nearest regardless of distance.

Strategy:
  - Start: snap to gap_end (video starts when speech begins)
  - End: snap to gap_start (video ends when speech finishes)
  - Safety: clip duration change max 30% from original
"""
import asyncio
import logging
import os
import subprocess
from typing import Optional

import numpy as np

from src.config import settings

logger = logging.getLogger(__name__)


class VADBoundaryAdjuster:
    """Adjust clip boundaries to nearest silence gap using Silero VAD."""

    def __init__(self):
        self._model = None
        self._get_speech_timestamps = None

    def _load_model(self) -> bool:
        """Lazy-load Silero VAD model."""
        if self._model is not None:
            return True
        try:
            import torch
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                trust_repo=True,
                verbose=False,
            )
            self._model = model
            self._get_speech_timestamps = utils[0]  # get_speech_timestamps function
            logger.info("vad: Silero VAD model loaded")
            return True
        except Exception as e:
            logger.warning(f"vad: failed to load model: {e}")
            return False

    async def adjust_clip_boundaries(
        self,
        audio_path: str,
        start: float,
        end: float,
    ) -> tuple[float, float]:
        """Adjust start/end to nearest silence boundaries.

        Args:
            audio_path: Path to source video/audio file
            start: Original start time (seconds)
            end: Original end time (seconds)

        Returns:
            (adjusted_start, adjusted_end) — snapped to silence gaps
        """
        if not settings.VAD_ENABLED:
            return start, end

        if not self._load_model():
            return start, end

        try:
            result = await asyncio.to_thread(
                self._adjust_sync, audio_path, start, end
            )
            return result
        except Exception as e:
            logger.warning(f"vad: adjustment failed, using original: {e}")
            return start, end

    def _adjust_sync(self, audio_path: str, start: float, end: float) -> tuple[float, float]:
        """Synchronous VAD processing."""
        import torch
        import torchaudio

        # Extract audio segment around clip (add 10s buffer on each side)
        buffer = 10.0
        extract_start = max(0, start - buffer)
        extract_end = end + buffer

        # Convert to WAV 16kHz mono for VAD
        wav_path = audio_path.rsplit(".", 1)[0] + "_vad_temp.wav"
        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", audio_path,
                "-ss", str(extract_start),
                "-to", str(extract_end),
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                wav_path,
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode != 0 or not os.path.exists(wav_path):
                return start, end

            # Load audio
            waveform, sample_rate = torchaudio.load(wav_path)
            if sample_rate != 16000:
                waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)

            # Run VAD — get speech timestamps
            speech_timestamps = self._get_speech_timestamps(
                waveform.squeeze(),
                self._model,
                sampling_rate=16000,
                min_silence_duration_ms=settings.VAD_MIN_SILENCE_MS,
                return_seconds=True,
            )

            if not speech_timestamps:
                # No speech detected — keep original
                return start, end

            # Convert speech timestamps to absolute time (add extract_start offset)
            speech_segments = [
                (seg["start"] + extract_start, seg["end"] + extract_start)
                for seg in speech_timestamps
            ]

            # Derive silence gaps from speech segments
            silence_gaps = self._derive_silence_gaps(speech_segments, extract_start, extract_end)

            if not silence_gaps:
                return start, end

            # Find nearest silence for start and end
            adjusted_start = self._snap_start(start, silence_gaps)
            adjusted_end = self._snap_end(end, silence_gaps)

            # Safety guard: don't change duration more than 30%
            original_duration = end - start
            adjusted_duration = adjusted_end - adjusted_start

            if adjusted_duration <= 0:
                return start, end

            if adjusted_duration < original_duration * 0.7 or adjusted_duration > original_duration * 1.3:
                logger.info(f"vad: adjustment too large ({original_duration:.1f}s → {adjusted_duration:.1f}s), keeping original")
                return start, end

            # Ensure minimum clip duration (5s)
            if adjusted_duration < 5.0:
                return start, end

            logger.info(
                f"vad: adjusted boundaries "
                f"start {start:.2f}→{adjusted_start:.2f} ({adjusted_start-start:+.2f}s), "
                f"end {end:.2f}→{adjusted_end:.2f} ({adjusted_end-end:+.2f}s)"
            )
            return adjusted_start, adjusted_end

        finally:
            # Cleanup temp file
            if os.path.exists(wav_path):
                os.remove(wav_path)

    def _derive_silence_gaps(
        self,
        speech_segments: list[tuple[float, float]],
        audio_start: float,
        audio_end: float,
    ) -> list[tuple[float, float]]:
        """Derive silence gaps from speech segments.

        Returns list of (gap_start, gap_end) where no one is speaking.
        Only includes gaps >= MIN_SILENCE_MS.
        """
        min_silence = settings.VAD_MIN_SILENCE_MS / 1000.0
        gaps = []

        # Gap before first speech
        if speech_segments and speech_segments[0][0] > audio_start + min_silence:
            gaps.append((audio_start, speech_segments[0][0]))

        # Gaps between speech segments
        for i in range(len(speech_segments) - 1):
            gap_start = speech_segments[i][1]
            gap_end = speech_segments[i + 1][0]
            if (gap_end - gap_start) >= min_silence:
                gaps.append((gap_start, gap_end))

        # Gap after last speech
        if speech_segments and speech_segments[-1][1] < audio_end - min_silence:
            gaps.append((speech_segments[-1][1], audio_end))

        return gaps

    def _snap_start(self, target: float, silence_gaps: list[tuple[float, float]]) -> float:
        """Find nearest silence gap to target, return gap_end (speech starts here)."""
        if not silence_gaps:
            return target

        # Find gap whose end is closest to target
        best_gap = min(silence_gaps, key=lambda g: abs(g[1] - target))
        return best_gap[1]

    def _snap_end(self, target: float, silence_gaps: list[tuple[float, float]]) -> float:
        """Find nearest silence gap to target, return gap_start (speech ends here)."""
        if not silence_gaps:
            return target

        # Find gap whose start is closest to target
        best_gap = min(silence_gaps, key=lambda g: abs(g[0] - target))
        return best_gap[0]
