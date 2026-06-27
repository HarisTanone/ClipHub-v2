"""SileroVAD — TAHAP 5: Voice Activity Detection for natural cut refinement.

Uses Silero VAD (via torchaudio) to find silence boundaries near clip edges.
Ensures cuts don't happen mid-word by shifting to nearest silence gap.

Architecture:
1. Load audio segment around target cut point
2. Run Silero VAD → detect speech/silence regions
3. Find nearest silence gap within ±search_radius
4. Shift cut point to silence boundary (+0.1s padding)
5. Fallback: use original timestamp if no silence found
"""
import asyncio
import logging
import os
from typing import Optional

import torch
import torchaudio

from src.config import settings
from src.domain.entities import VADResult
from src.domain.interfaces import ISileroVAD

logger = logging.getLogger(__name__)


class SileroVADProcessor(ISileroVAD):
    """TAHAP 5 implementation: Silero VAD for natural cut refinement.

    Singleton model loading — loads once, reuses across all clips.
    """

    _model = None
    _utils = None

    def __init__(self):
        self._search_radius = settings.V2_VAD_SEARCH_RADIUS  # Default: 2.0s
        self._min_silence_ms = settings.V2_VAD_MIN_SILENCE_MS  # Default: 300ms
        self._sample_rate = 16000

    # ─── Model Loading (Singleton) ────────────────────────────────────────────

    def _ensure_model_loaded(self) -> None:
        """Load Silero VAD model if not already loaded (singleton)."""
        if SileroVADProcessor._model is not None:
            return

        try:
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            SileroVADProcessor._model = model
            SileroVADProcessor._utils = utils
            logger.info("v2_silero_vad: model loaded successfully")
        except Exception as e:
            logger.error(f"v2_silero_vad: model loading failed: {e}")
            raise

    # ─── Main Entry Point ─────────────────────────────────────────────────────

    async def refine_boundaries(
        self, audio_path: str, target_start: float, target_end: float,
        search_radius: float = 2.0
    ) -> tuple[float, float]:
        """Find nearest silence boundaries around target timestamps.

        Args:
            audio_path: Path to WAV audio file (16kHz mono)
            target_start: Desired start time in seconds (relative to audio file)
            target_end: Desired end time in seconds (relative to audio file)
            search_radius: How far to search for silence (seconds)

        Returns:
            Tuple of (refined_start, refined_end) in seconds
        """
        if not os.path.exists(audio_path):
            logger.warning(f"v2_silero_vad: file not found: {audio_path}")
            return target_start, target_end

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, self._refine_sync, audio_path, target_start, target_end, search_radius
            )
            return result
        except Exception as e:
            logger.warning(f"v2_silero_vad: refinement failed, using original: {e}")
            return target_start, target_end

    def _refine_sync(
        self, audio_path: str, target_start: float, target_end: float,
        search_radius: float
    ) -> tuple[float, float]:
        """Synchronous VAD refinement."""
        self._ensure_model_loaded()

        # Load audio
        waveform, sample_rate = torchaudio.load(audio_path)

        # Resample if needed
        if sample_rate != self._sample_rate:
            resampler = torchaudio.transforms.Resample(sample_rate, self._sample_rate)
            waveform = resampler(waveform)

        # Convert to mono if stereo
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        audio_duration = waveform.shape[1] / self._sample_rate

        # Get speech timestamps from Silero VAD
        speech_timestamps = self._get_speech_timestamps(waveform[0])

        if not speech_timestamps:
            # No speech detected at all — use original timestamps
            return target_start, target_end

        # Convert speech timestamps to silence gaps
        silence_gaps = self._find_silence_gaps(speech_timestamps, audio_duration)

        # Refine start: find nearest silence BEFORE target_start
        refined_start = self._find_nearest_silence(
            silence_gaps, target_start, direction="before", radius=search_radius
        )

        # Refine end: find nearest silence AFTER target_end
        refined_end = self._find_nearest_silence(
            silence_gaps, target_end, direction="after", radius=search_radius
        )

        return refined_start, refined_end

    # ─── VAD Processing ───────────────────────────────────────────────────────

    def _get_speech_timestamps(self, waveform: torch.Tensor) -> list[dict]:
        """Run Silero VAD on waveform, return speech segments.

        Returns list of {start: float, end: float} in seconds.
        """
        model = SileroVADProcessor._model
        utils = SileroVADProcessor._utils

        # get_speech_timestamps is part of Silero VAD utils
        get_speech_ts = utils[0]  # (get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks)

        speech_timestamps = get_speech_ts(
            waveform,
            model,
            sampling_rate=self._sample_rate,
            min_silence_duration_ms=self._min_silence_ms,
            speech_pad_ms=100,
            return_seconds=True,
        )

        return speech_timestamps

    def _find_silence_gaps(
        self, speech_timestamps: list[dict], audio_duration: float
    ) -> list[tuple[float, float]]:
        """Convert speech timestamps to silence gap intervals.

        A silence gap exists between consecutive speech segments,
        and at the start/end of audio if speech doesn't cover it.
        """
        gaps = []

        if not speech_timestamps:
            # Entire audio is silence
            return [(0.0, audio_duration)]

        # Gap before first speech
        first_start = speech_timestamps[0].get("start", 0)
        if first_start > 0.05:  # Minimum meaningful gap
            gaps.append((0.0, first_start))

        # Gaps between speech segments
        for i in range(len(speech_timestamps) - 1):
            current_end = speech_timestamps[i].get("end", 0)
            next_start = speech_timestamps[i + 1].get("start", 0)
            if next_start - current_end > 0.05:
                gaps.append((current_end, next_start))

        # Gap after last speech
        last_end = speech_timestamps[-1].get("end", 0)
        if audio_duration - last_end > 0.05:
            gaps.append((last_end, audio_duration))

        return gaps

    def _find_nearest_silence(
        self, silence_gaps: list[tuple[float, float]],
        target_time: float, direction: str, radius: float
    ) -> float:
        """Find the nearest silence gap boundary to target_time.

        Args:
            silence_gaps: List of (start, end) silence intervals
            target_time: The time we want to cut at
            direction: "before" (search backwards) or "after" (search forwards)
            radius: Maximum distance to search (seconds)

        Returns:
            Refined time at silence boundary, or original if none found.
        """
        best_time = target_time  # Fallback: original
        best_distance = float("inf")

        for gap_start, gap_end in silence_gaps:
            gap_midpoint = (gap_start + gap_end) / 2

            if direction == "before":
                # Looking for silence BEFORE or AT target_time
                # The cut point should be in the silence gap
                if gap_end <= target_time + 0.1 and gap_start >= target_time - radius:
                    # Use the end of the silence gap (right before speech resumes)
                    candidate = gap_end + 0.1  # Small padding after silence
                    distance = abs(target_time - candidate)
                    if distance < best_distance:
                        best_distance = distance
                        best_time = candidate

                # Also consider gap that contains target_time
                elif gap_start <= target_time <= gap_end:
                    best_time = target_time  # Already in silence, keep it
                    best_distance = 0
                    break

            elif direction == "after":
                # Looking for silence AFTER or AT target_time
                if gap_start >= target_time - 0.1 and gap_end <= target_time + radius:
                    # Use the start of the silence gap (just after speech ends)
                    candidate = gap_start - 0.1  # Small padding before silence
                    distance = abs(target_time - candidate)
                    if distance < best_distance:
                        best_distance = distance
                        best_time = candidate

                # Also consider gap that contains target_time
                elif gap_start <= target_time <= gap_end:
                    best_time = target_time  # Already in silence, keep it
                    best_distance = 0
                    break

        return round(best_time, 3)

    # ─── Full Clip Refinement ─────────────────────────────────────────────────

    async def refine_clip_boundaries(
        self, audio_path: str, original_start: float, original_end: float,
        padded_start: float
    ) -> VADResult:
        """Refine clip boundaries and return a VADResult.

        target_start/end are relative to the audio file (not absolute video time).
        The offset (padded_start) is used to convert back to absolute.
        """
        # Convert absolute times to audio-file-relative times
        relative_start = original_start - padded_start
        relative_end = original_end - padded_start

        refined_start_rel, refined_end_rel = await self.refine_boundaries(
            audio_path, relative_start, relative_end, self._search_radius
        )

        # Convert back to absolute video timestamps
        final_start = refined_start_rel + padded_start
        final_end = refined_end_rel + padded_start

        shift_start_ms = (final_start - original_start) * 1000
        shift_end_ms = (final_end - original_end) * 1000
        used_fallback = (
            abs(shift_start_ms) < 1.0 and abs(shift_end_ms) < 1.0
        )

        return VADResult(
            original_start=original_start,
            original_end=original_end,
            final_start=round(final_start, 3),
            final_end=round(final_end, 3),
            shift_start_ms=round(shift_start_ms, 1),
            shift_end_ms=round(shift_end_ms, 1),
            used_fallback=used_fallback,
        )
