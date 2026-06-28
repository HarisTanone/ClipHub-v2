"""LocalTranscriber — Full audio transcription via Faster-Whisper (local).

Flow:
1. Extract audio from video (FFmpeg → WAV 16kHz mono)
2. Run Faster-Whisper medium with word_timestamps=True
3. Return TranscriptResult with word-level timing

No external API calls. Runs entirely on local CPU/GPU.
"""
import asyncio
import logging
import os
import subprocess
from typing import Optional

from src.config import settings
from src.domain.entities import TranscriptResult, TranscriptSegment, Word
from src.domain.interfaces import IWhisperLocal

logger = logging.getLogger(__name__)


class LocalTranscriber:
    """Full-audio local transcription using Faster-Whisper.
    
    Extracts audio from video, runs Whisper medium model,
    returns both segment-level and word-level timestamps.
    """

    def __init__(self, whisper_local: IWhisperLocal):
        self._whisper = whisper_local

    async def transcribe(self, video_path: str, video_duration: float) -> tuple[TranscriptResult, list[dict]]:
        """Transcribe full video audio locally.

        Args:
            video_path: Path to downloaded video file
            video_duration: Video duration in seconds

        Returns:
            Tuple of (TranscriptResult for LLM analysis, raw_segments with words for subtitle)
        """
        # Step 1: Extract audio from video
        audio_path = video_path.rsplit(".", 1)[0] + "_audio.wav"
        await self._extract_audio(video_path, audio_path)

        if not os.path.exists(audio_path):
            raise RuntimeError(f"Audio extraction failed: {audio_path}")

        logger.info(f"local_transcriber: audio extracted ({os.path.getsize(audio_path) / 1024 / 1024:.1f}MB)")

        # Step 2: Run Faster-Whisper on full audio
        try:
            raw_segments = await self._whisper.transcribe_clip(audio_path)
        finally:
            # Cleanup audio file
            if os.path.exists(audio_path):
                os.remove(audio_path)

        if not raw_segments:
            raise RuntimeError("Faster-Whisper returned empty transcript")

        # Step 3: Convert to TranscriptResult (for LLM analysis)
        segments = []
        for seg in raw_segments:
            text = seg.get("text", "").strip()
            if text:
                segments.append(TranscriptSegment(
                    text=text,
                    start=round(seg.get("start", 0), 2),
                    end=round(seg.get("end", 0), 2),
                ))

        transcript = TranscriptResult(
            segments=segments,
            source="faster_whisper_local",
            language="id",  # Will be detected by Whisper
            total_duration=video_duration,
        )

        logger.info(
            f"local_transcriber: {len(segments)} segments, "
            f"{sum(len(s.get('words', [])) for s in raw_segments)} words total"
        )

        return transcript, raw_segments

    async def _extract_audio(self, video_path: str, output_path: str) -> None:
        """Extract audio as WAV 16kHz mono (optimal for Whisper)."""
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            "-loglevel", "error",
            output_path,
        ]

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        )

        if result.returncode != 0:
            logger.error(f"local_transcriber: FFmpeg audio extract failed: {result.stderr[:200]}")
            raise RuntimeError("Audio extraction failed")
