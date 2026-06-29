"""LocalTranscriber — Transcription with Groq API (primary) + Faster-Whisper (fallback).

Flow:
1. Try Groq Whisper API (cloud, ~30s for 1hr audio)
2. If Groq fails → fallback to local Faster-Whisper (CPU, ~20min for 1hr)
3. Return TranscriptResult with word-level timing

Groq handles compression (FLAC 16kHz mono) and chunking internally.
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
    """Transcription orchestrator: Groq API → Faster-Whisper fallback.
    
    Primary: Groq Whisper API (fast, accurate, zero CPU usage)
    Fallback: Local Faster-Whisper (slow but guaranteed to work offline)
    """

    def __init__(self, whisper_local: IWhisperLocal):
        self._whisper = whisper_local
        self._groq = None  # lazy init

    def _get_groq(self):
        """Lazy-init Groq Whisper transcriber."""
        if self._groq is None:
            from src.infrastructure.groq_whisper import GroqWhisperTranscriber
            self._groq = GroqWhisperTranscriber()
        return self._groq

    async def transcribe(self, video_path: str, video_duration: float) -> tuple[TranscriptResult, list[dict]]:
        """Transcribe full video audio.

        Strategy:
        1. If GROQ_API_KEY configured → use Groq Whisper API (fast)
        2. If Groq fails or unavailable → fallback to local Faster-Whisper

        Args:
            video_path: Path to downloaded video file
            video_duration: Video duration in seconds

        Returns:
            Tuple of (TranscriptResult for LLM analysis, raw_segments with words for subtitle)
        """
        # ─── Try Groq Whisper API first (primary) ─────────────────────────
        groq = self._get_groq()
        if groq.is_available:
            try:
                logger.info("local_transcriber: using Groq Whisper API (primary)")
                raw_segments = await groq.transcribe(video_path, language="id")

                if raw_segments:
                    transcript = self._build_transcript_result(raw_segments, video_duration, source="groq_whisper")
                    total_words = sum(len(s.get("words", [])) for s in raw_segments)
                    logger.info(
                        f"local_transcriber: Groq success — {len(raw_segments)} segments, "
                        f"{total_words} words"
                    )
                    return transcript, raw_segments
                else:
                    logger.warning("local_transcriber: Groq returned empty, falling back to local")
            except Exception as e:
                logger.warning(f"local_transcriber: Groq failed ({e}), falling back to local")
        else:
            logger.info("local_transcriber: Groq API key not set, using local Faster-Whisper")

        # ─── Fallback: Local Faster-Whisper ───────────────────────────────
        return await self._transcribe_local(video_path, video_duration)

    async def _transcribe_local(self, video_path: str, video_duration: float) -> tuple[TranscriptResult, list[dict]]:
        """Fallback: transcribe using local Faster-Whisper on CPU."""
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

        # Step 3: Convert to TranscriptResult
        transcript = self._build_transcript_result(raw_segments, video_duration, source="faster_whisper_local")

        logger.info(
            f"local_transcriber: {len(transcript.segments)} segments, "
            f"{sum(len(s.get('words', [])) for s in raw_segments)} words total"
        )

        return transcript, raw_segments

    def _build_transcript_result(
        self, raw_segments: list[dict], video_duration: float, source: str
    ) -> TranscriptResult:
        """Convert raw segments to TranscriptResult for LLM analysis."""
        segments = []
        for seg in raw_segments:
            text = seg.get("text", "").strip()
            if text:
                segments.append(TranscriptSegment(
                    text=text,
                    start=round(seg.get("start", 0), 2),
                    end=round(seg.get("end", 0), 2),
                ))

        return TranscriptResult(
            segments=segments,
            source=source,
            language="id",
            total_duration=video_duration,
        )

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
            None, lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        )

        if result.returncode != 0:
            logger.error(f"local_transcriber: FFmpeg audio extract failed: {result.stderr[:200]}")
            raise RuntimeError("Audio extraction failed")
