"""GroqTranscriber — TAHAP 1: Ingestion & Text Extraction.

Primary: YouTube Transcript API (free, instant).
Fallback: Groq Whisper API (fast, free tier — 28,800 audio-sec/day).

Architecture:
1. Try youtube-transcript-api → fetch captions (id → en → auto → any)
2. If no captions → download audio only (yt-dlp)
3. Split audio into ≤25MB chunks (FFmpeg)
4. Send chunks to Groq Whisper API (whisper-large-v3-turbo)
5. Merge results → TranscriptResult
"""
import asyncio
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from src.config import settings
from src.domain.entities import TranscriptResult, TranscriptSegment
from src.domain.interfaces import IGroqTranscriber

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Raised when both YouTube API and Groq Whisper fail."""
    pass


class GroqTranscriber(IGroqTranscriber):
    """TAHAP 1 implementation: YouTube Transcript + Groq Whisper fallback."""

    # Language priority for YouTube captions
    LANGUAGE_PRIORITY = ["id", "en", "en-US", "en-GB"]

    def __init__(self):
        self._groq_client = None
        self._model = settings.GROQ_WHISPER_MODEL
        self._max_chunk_mb = settings.V2_MAX_AUDIO_CHUNK_MB
        self._timeout = settings.GROQ_TIMEOUT
        self._max_retries = settings.GROQ_MAX_RETRIES

    def _get_groq_client(self):
        """Lazy-init Groq client."""
        if self._groq_client is None:
            from groq import Groq
            if not settings.GROQ_API_KEY:
                raise TranscriptionError("GROQ_API_KEY not configured")
            self._groq_client = Groq(api_key=settings.GROQ_API_KEY)
        return self._groq_client

    # ─── Main Entry Point ─────────────────────────────────────────────────────

    async def transcribe(self, youtube_url: str, video_duration: float) -> TranscriptResult:
        """Get transcript: YouTube API first, Groq Whisper fallback.

        Returns TranscriptResult with segments, source, and language.
        Raises TranscriptionError if all methods fail.
        """
        video_id = self._extract_video_id(youtube_url)

        # ─── Path 1: YouTube Transcript API (free, instant) ───────────
        logger.info(f"v2_transcriber: trying YouTube API for {video_id}")
        try:
            result = await self._fetch_youtube_transcript(video_id, video_duration)
            if result and result.segments:
                logger.info(
                    f"v2_transcriber: YouTube API success — "
                    f"{len(result.segments)} segments, lang={result.language}"
                )
                return result
        except Exception as e:
            logger.info(f"v2_transcriber: YouTube API failed — {e}")

        # ─── Path 2: Groq Whisper API (fallback) ─────────────────────
        logger.info(f"v2_transcriber: falling back to Groq Whisper for {video_id}")
        try:
            result = await self._transcribe_via_groq_whisper(youtube_url, video_duration)
            if result and result.segments:
                logger.info(
                    f"v2_transcriber: Groq Whisper success — "
                    f"{len(result.segments)} segments, lang={result.language}"
                )
                return result
        except Exception as e:
            logger.error(f"v2_transcriber: Groq Whisper also failed — {e}")
            raise TranscriptionError(
                f"Transcription gagal: YouTube API dan Groq Whisper keduanya gagal. "
                f"Detail: {e}"
            ) from e

        raise TranscriptionError("Transcription gagal: tidak ada transcript yang tersedia")

    # ─── YouTube Transcript API ───────────────────────────────────────────────

    async def _fetch_youtube_transcript(
        self, video_id: str, video_duration: float
    ) -> Optional[TranscriptResult]:
        """Fetch transcript from YouTube captions API.

        Language priority: id → en → en-US → en-GB → auto-generated → any
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._fetch_youtube_transcript_sync, video_id, video_duration
        )

    def _fetch_youtube_transcript_sync(
        self, video_id: str, video_duration: float
    ) -> Optional[TranscriptResult]:
        """Sync implementation of YouTube transcript fetch."""
        from youtube_transcript_api import YouTubeTranscriptApi

        ytt_api = YouTubeTranscriptApi()

        try:
            transcript_list = ytt_api.list(video_id)
        except Exception as e:
            raise RuntimeError(f"No transcripts available: {e}")

        # Try manually created transcripts first (better quality)
        transcript = None
        language = "unknown"

        # Priority 1: Manual transcripts in preferred languages
        try:
            transcript = transcript_list.find_manually_created_transcript(
                self.LANGUAGE_PRIORITY
            )
            language = transcript.language_code
        except Exception:
            pass

        # Priority 2: Auto-generated transcripts in preferred languages
        if transcript is None:
            try:
                transcript = transcript_list.find_generated_transcript(
                    self.LANGUAGE_PRIORITY
                )
                language = transcript.language_code
            except Exception:
                pass

        # Priority 3: Any available transcript
        if transcript is None:
            try:
                for t in transcript_list:
                    transcript = t
                    language = t.language_code
                    break
            except Exception:
                pass

        if transcript is None:
            raise RuntimeError("No suitable transcript found")

        # Fetch the actual transcript data (returns FetchedTranscript)
        fetched = transcript.fetch()
        if not fetched:
            raise RuntimeError("Transcript fetch returned empty data")

        # Convert to TranscriptSegment list
        # FetchedTranscript is iterable, each snippet has .text, .start, .duration
        segments = []
        for snippet in fetched:
            text = snippet.text.strip() if hasattr(snippet, 'text') else ""
            if not text or text == "[Music]" or text == "[Musik]":
                continue

            start = float(snippet.start) if hasattr(snippet, 'start') else 0.0
            duration_val = float(snippet.duration) if hasattr(snippet, 'duration') else 0.0
            end = start + duration_val

            segments.append(TranscriptSegment(
                text=text,
                start=round(start, 2),
                end=round(end, 2),
            ))

        if not segments:
            raise RuntimeError("All transcript segments were empty/filtered")

        return TranscriptResult(
            segments=segments,
            source="youtube_api",
            language=language,
            total_duration=video_duration,
        )

    # ─── Groq Whisper API (Fallback) ─────────────────────────────────────────

    async def _transcribe_via_groq_whisper(
        self, youtube_url: str, video_duration: float
    ) -> TranscriptResult:
        """Download audio → split into chunks → transcribe via Groq Whisper.

        Steps:
        1. Download audio only (yt-dlp, mp3 format)
        2. Get file size, calculate number of chunks needed
        3. Split into ≤25MB chunks using FFmpeg
        4. Send each chunk to Groq Whisper API
        5. Merge results with corrected timestamps
        """
        audio_dir = tempfile.mkdtemp(prefix="v2_audio_")

        try:
            # Step 1: Download audio only
            audio_path = await self._download_audio(youtube_url, audio_dir)
            if not audio_path or not os.path.exists(audio_path):
                raise TranscriptionError("Audio download failed")

            file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
            logger.info(f"v2_transcriber: audio downloaded — {file_size_mb:.1f}MB")

            # Step 2: Split into chunks if needed
            if file_size_mb <= self._max_chunk_mb:
                # Small enough — send as single chunk
                chunks = [(audio_path, 0.0)]
            else:
                chunks = await self._split_audio_into_chunks(
                    audio_path, video_duration, audio_dir
                )
                logger.info(f"v2_transcriber: split into {len(chunks)} chunks")

            # Step 3: Transcribe each chunk via Groq
            all_segments = []
            detected_language = "unknown"

            for chunk_path, chunk_offset in chunks:
                segments, lang = await self._groq_whisper_transcribe_chunk(
                    chunk_path, chunk_offset
                )
                all_segments.extend(segments)
                if lang and lang != "unknown":
                    detected_language = lang

            if not all_segments:
                raise TranscriptionError("Groq Whisper returned empty transcript")

            # Sort segments by start time
            all_segments.sort(key=lambda s: s.start)

            return TranscriptResult(
                segments=all_segments,
                source="groq_whisper",
                language=detected_language,
                total_duration=video_duration,
            )

        finally:
            # Cleanup temp files
            self._cleanup_dir(audio_dir)

    async def _download_audio(self, youtube_url: str, output_dir: str) -> Optional[str]:
        """Download audio only using yt-dlp (no video)."""
        output_template = os.path.join(output_dir, "audio.%(ext)s")
        cmd = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "5",  # Medium quality (smaller file)
            "--no-playlist",
            "--no-warnings",
            "-o", output_template,
            youtube_url,
        ]

        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._run_subprocess, cmd),
                timeout=180,  # 3 min max for download
            )
            if result.returncode != 0:
                logger.error(f"yt-dlp audio download failed: {result.stderr[:200]}")
                return None
        except asyncio.TimeoutError:
            logger.error("yt-dlp audio download timed out (180s)")
            return None

        # Find the downloaded file
        for f in os.listdir(output_dir):
            if f.startswith("audio."):
                return os.path.join(output_dir, f)
        return None

    async def _split_audio_into_chunks(
        self, audio_path: str, total_duration: float, output_dir: str
    ) -> list[tuple[str, float]]:
        """Split audio into time-based chunks that stay under max file size.

        Strategy: Split by time (10 min chunks). Each chunk will be under 25MB
        for a 128kbps mp3 (10 min × 128kbps ÷ 8 = ~9.6MB).

        Returns: list of (chunk_path, time_offset_seconds)
        """
        chunk_duration = 600  # 10 minutes per chunk
        num_chunks = max(1, int(total_duration / chunk_duration) + 1)
        chunks = []

        loop = asyncio.get_event_loop()

        for i in range(num_chunks):
            start_time = i * chunk_duration
            if start_time >= total_duration:
                break

            chunk_path = os.path.join(output_dir, f"chunk_{i:03d}.mp3")
            cmd = [
                "ffmpeg", "-y",
                "-i", audio_path,
                "-ss", str(start_time),
                "-t", str(chunk_duration),
                "-ar", "16000",        # 16kHz for Whisper
                "-ac", "1",            # Mono
                "-b:a", "64k",         # Low bitrate to stay under 25MB
                chunk_path,
            ]

            result = await loop.run_in_executor(None, self._run_subprocess, cmd)
            if result.returncode == 0 and os.path.exists(chunk_path):
                chunk_size_mb = os.path.getsize(chunk_path) / (1024 * 1024)
                if chunk_size_mb > 0.01:  # Skip empty chunks
                    chunks.append((chunk_path, start_time))
                    logger.debug(
                        f"v2_transcriber: chunk {i} — "
                        f"offset={start_time}s, size={chunk_size_mb:.1f}MB"
                    )

        if not chunks:
            raise TranscriptionError("FFmpeg failed to create any audio chunks")

        return chunks

    async def _groq_whisper_transcribe_chunk(
        self, chunk_path: str, time_offset: float
    ) -> tuple[list[TranscriptSegment], str]:
        """Transcribe a single audio chunk via Groq Whisper API.

        Returns: (segments_with_absolute_timestamps, detected_language)
        """
        loop = asyncio.get_event_loop()

        for attempt in range(self._max_retries):
            try:
                segments, language = await asyncio.wait_for(
                    loop.run_in_executor(
                        None, self._groq_whisper_call_sync, chunk_path, time_offset
                    ),
                    timeout=self._timeout,
                )
                return segments, language

            except asyncio.TimeoutError:
                logger.warning(
                    f"v2_transcriber: Groq Whisper timeout (attempt {attempt + 1})"
                )
                if attempt == self._max_retries - 1:
                    raise TranscriptionError(
                        f"Groq Whisper timeout after {self._max_retries} attempts"
                    )

            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "rate" in error_str:
                    wait_time = (attempt + 1) * 10
                    logger.warning(
                        f"v2_transcriber: Groq rate limited, waiting {wait_time}s"
                    )
                    await asyncio.sleep(wait_time)
                    continue

                if attempt == self._max_retries - 1:
                    raise
                logger.warning(
                    f"v2_transcriber: Groq Whisper attempt {attempt + 1} failed: {e}"
                )
                await asyncio.sleep(2)

        return [], "unknown"

    def _groq_whisper_call_sync(
        self, chunk_path: str, time_offset: float
    ) -> tuple[list[TranscriptSegment], str]:
        """Synchronous Groq Whisper API call."""
        client = self._get_groq_client()

        with open(chunk_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(chunk_path), audio_file),
                model=self._model,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        # Parse response
        segments = []
        language = getattr(transcription, "language", "unknown") or "unknown"

        # Handle verbose_json response which has segments
        raw_segments = getattr(transcription, "segments", None)
        if raw_segments:
            for seg in raw_segments:
                text = seg.get("text", "").strip() if isinstance(seg, dict) else getattr(seg, "text", "").strip()
                start = (seg.get("start", 0) if isinstance(seg, dict) else getattr(seg, "start", 0))
                end = (seg.get("end", 0) if isinstance(seg, dict) else getattr(seg, "end", 0))

                if not text:
                    continue

                # Apply time offset for absolute positioning
                segments.append(TranscriptSegment(
                    text=text,
                    start=round(start + time_offset, 2),
                    end=round(end + time_offset, 2),
                ))
        else:
            # Fallback: treat entire transcription as single segment
            text = getattr(transcription, "text", "").strip()
            if text:
                segments.append(TranscriptSegment(
                    text=text,
                    start=round(time_offset, 2),
                    end=round(time_offset + 600, 2),  # Estimate 10 min chunk
                ))

        return segments, language

    # ─── Utilities ────────────────────────────────────────────────────────────

    def _extract_video_id(self, url: str) -> str:
        """Extract video ID from YouTube URL."""
        patterns = [
            r"(?:v=)([a-zA-Z0-9_-]{11})",
            r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
            r"(?:embed/)([a-zA-Z0-9_-]{11})",
            r"(?:shorts/)([a-zA-Z0-9_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        # Fallback: assume it's already a video ID
        return url.split("?")[0].split("/")[-1][:11]

    def _run_subprocess(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """Run subprocess with captured output."""
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

    def _cleanup_dir(self, dir_path: str) -> None:
        """Remove temp directory and all contents."""
        try:
            import shutil
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Cleanup failed for {dir_path}: {e}")
