"""Full-file transcription with 9router Groq Whisper and local fallback.

Flow:
1. Use Groq Whisper through 9router when configured
2. Fall back immediately to local Faster-Whisper on any unusable response
3. Return TranscriptResult with word-level timing
"""
import asyncio
import logging
import os
import subprocess

from src.domain.entities import TranscriptResult, TranscriptSegment
from src.domain.interfaces import IWhisperLocal

logger = logging.getLogger(__name__)


class LocalTranscriber:
    """Transcription orchestrator: 9router Groq Whisper -> local Whisper.
    
    The class name is retained for compatibility with existing pipeline imports.
    """

    def __init__(self, whisper_local: IWhisperLocal):
        self._whisper = whisper_local
        self._groq = None  # 9router Whisper client, lazy init

    def _get_groq(self):
        """Lazy-init the 9router-backed Groq Whisper transcriber."""
        if self._groq is None:
            from src.infrastructure.groq_whisper import GroqWhisperTranscriber
            self._groq = GroqWhisperTranscriber()
        return self._groq

    async def transcribe(self, video_path: str, video_duration: float) -> tuple[TranscriptResult, list[dict]]:
        """Transcribe full video audio.

        Strategy:
        1. Use Groq Whisper via 9router first
        2. Use the unchanged local Whisper path if 9router fails or is empty

        Args:
            video_path: Path to downloaded video file
            video_duration: Video duration in seconds

        Returns:
            Tuple of (TranscriptResult for LLM analysis, raw_segments with words for subtitle)
        """
        groq = self._get_groq()
        if groq.is_available:
            try:
                logger.info("local_transcriber: using Groq Whisper through 9router")
                raw_segments = await groq.transcribe(video_path, language="id")

                if raw_segments:
                    transcript = self._build_transcript_result(
                        raw_segments,
                        video_duration,
                        source="groq_whisper",
                    )
                    total_words = sum(len(s.get("words", [])) for s in raw_segments)
                    logger.info(
                        f"local_transcriber: 9router Groq success — {len(raw_segments)} segments, "
                        f"{total_words} words"
                    )
                    return transcript, raw_segments
                logger.warning("local_transcriber: 9router returned empty; using local Whisper")
            except Exception as e:
                logger.warning(
                    f"local_transcriber: 9router Groq failed ({e}); using local Whisper"
                )

        logger.info("local_transcriber: using local Faster-Whisper fallback")
        return await self._transcribe_local(video_path, video_duration)

    async def _transcribe_local(self, video_path: str, video_duration: float) -> tuple[TranscriptResult, list[dict]]:
        """Fallback: transcribe using local Faster-Whisper on CPU."""
        # Step 1: Extract audio from video
        base, _ = os.path.splitext(video_path)
        audio_path = base + "_audio.wav"
        await self._extract_audio(video_path, audio_path)

        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            raise RuntimeError(f"Audio extraction failed or produced empty file: {audio_path}")

        logger.info(f"local_transcriber: audio extracted ({os.path.getsize(audio_path) / 1024 / 1024:.1f}MB)")

        # Step 2: Run Faster-Whisper on full audio
        try:
            raw_segments = await self._whisper.transcribe_clip(audio_path)
        except Exception as e:
            raise RuntimeError(f"Faster-Whisper transcription error: {e}") from e
        finally:
            # Cleanup audio file
            if os.path.exists(audio_path):
                os.remove(audio_path)

        if not raw_segments:
            # Empty transcript is valid (music-only clips) — return empty result, don't crash
            logger.warning("local_transcriber: Faster-Whisper returned empty transcript (no speech detected)")
            return TranscriptResult(
                segments=[], source="faster_whisper_local",
                language="id", total_duration=video_duration,
            ), []

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

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        )

        if result.returncode != 0:
            logger.error(f"local_transcriber: FFmpeg audio extract failed: {result.stderr[:200]}")
            raise RuntimeError("Audio extraction failed")
