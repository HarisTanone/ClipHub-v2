"""GroqWhisperTranscriber — Cloud-based transcription via Groq Whisper API.

Primary transcription method for V2 pipeline (non-premium users).
Uses Groq's whisper-large-v3-turbo for fast, accurate word-level transcription.

Flow:
1. Compress audio to FLAC 16kHz mono (minimizes file size)
2. If file > 25MB: chunk into segments
3. Send to Groq API with word-level timestamps
4. Return unified word-level JSON

Speed: ~216x real-time (1 hour audio ≈ 16-30 seconds)
Cost: Free tier supports ~20 RPM, ~2000 RPD
"""
import asyncio
import json
import logging
import os
import subprocess
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)

# Max file size for Groq free tier (bytes)
GROQ_MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
CHUNK_DURATION_SECONDS = 600  # 10 minutes per chunk


class GroqWhisperTranscriber:
    """Transcribe audio using Groq's Whisper API with word-level timestamps."""

    def __init__(self):
        self._api_key = settings.GROQ_API_KEY
        self._model = settings.GROQ_WHISPER_MODEL or "whisper-large-v3-turbo"
        self._max_retries = settings.GROQ_MAX_RETRIES or 3
        self._client = None

    @property
    def is_available(self) -> bool:
        """Check if Groq Whisper is configured and available."""
        return bool(self._api_key)

    def _get_client(self):
        """Lazy-init Groq client."""
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("GROQ_API_KEY not configured")
            from groq import Groq
            self._client = Groq(api_key=self._api_key)
        return self._client

    async def transcribe(self, video_path: str, language: str = "id") -> list[dict]:
        """Transcribe video/audio file via Groq Whisper API.

        Args:
            video_path: Path to video or audio file
            language: ISO-639-1 language code (default: Indonesian)

        Returns:
            List of segment dicts: [{start, end, text, words: [{word, start, end}]}]
            Empty list on failure.
        """
        if not self.is_available:
            logger.warning("groq_whisper: API key not configured")
            return []

        # Step 1: Compress to FLAC 16kHz mono
        base, _ = os.path.splitext(video_path)
        flac_path = base + "_groq.flac"
        try:
            await self._compress_to_flac(video_path, flac_path)

            if not os.path.exists(flac_path):
                logger.error("groq_whisper: FLAC compression failed")
                return []

            file_size = os.path.getsize(flac_path)
            file_size_mb = file_size / (1024 * 1024)
            logger.info(f"groq_whisper: compressed to FLAC ({file_size_mb:.1f}MB)")

            # Step 2: Decide single or chunked transcription
            if file_size <= GROQ_MAX_FILE_SIZE:
                # Single request — most common case
                segments = await self._transcribe_single(flac_path, language)
            else:
                # File too large — chunk it
                logger.info(f"groq_whisper: file {file_size_mb:.1f}MB > 25MB, chunking...")
                segments = await self._transcribe_chunked(video_path, language)

            if segments:
                total_words = sum(len(s.get("words", [])) for s in segments)
                logger.info(
                    f"groq_whisper: {len(segments)} segments, {total_words} words, "
                    f"model={self._model}"
                )
            return segments

        except Exception as e:
            logger.error(f"groq_whisper: unexpected error: {e}")
            return []
        finally:
            # Cleanup FLAC
            if os.path.exists(flac_path):
                os.remove(flac_path)

    async def _compress_to_flac(self, input_path: str, output_path: str) -> None:
        """Compress audio to FLAC 16kHz mono — optimal for Groq API.
        
        16kHz mono FLAC for 1 hour of speech ≈ 8-15 MB (well under 25MB limit).
        """
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-ar", "16000",   # 16kHz (optimal for speech recognition)
            "-ac", "1",       # Mono
            "-map", "0:a",    # Audio track only
            "-c:a", "flac",   # Lossless compression
            "-loglevel", "error",
            output_path,
        ]
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        )
        if result.returncode != 0:
            logger.error(f"groq_whisper: ffmpeg flac failed: {result.stderr[:200]}")

    async def _transcribe_single(self, flac_path: str, language: str) -> list[dict]:
        """Send single file to Groq API and get word-level transcription."""
        loop = asyncio.get_running_loop()
        # Dynamic timeout: 120s base + 1s per MB (large files take longer to upload)
        file_size_mb = os.path.getsize(flac_path) / (1024 * 1024)
        timeout = max(120, int(120 + file_size_mb * 2))
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self._call_groq_api, flac_path, language),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.error(f"groq_whisper: single transcription timeout ({timeout}s)")
            return []

    def _call_groq_api(self, audio_path: str, language: str) -> list[dict]:
        """Synchronous Groq API call with retry logic."""
        import time as _time
        from groq import RateLimitError, APIConnectionError, APIStatusError

        for attempt in range(self._max_retries):
            try:
                client = self._get_client()
                start_time = _time.time()

                with open(audio_path, "rb") as f:
                    transcription = client.audio.transcriptions.create(
                        file=f,
                        model=self._model,
                        response_format="verbose_json",
                        timestamp_granularities=["word", "segment"],
                        language=language,
                        temperature=0.0,
                    )

                elapsed = _time.time() - start_time
                logger.info(f"groq_whisper: API response in {elapsed:.1f}s")

                # Parse response into our segment format
                return self._parse_response(transcription)

            except RateLimitError as e:
                wait = (attempt + 1) * 10
                logger.warning(f"groq_whisper: rate limit hit, waiting {wait}s (attempt {attempt + 1})")
                _time.sleep(wait)
            except APIConnectionError as e:
                wait = (attempt + 1) * 5
                logger.warning(f"groq_whisper: connection error, retry in {wait}s (attempt {attempt + 1})")
                _time.sleep(wait)
            except APIStatusError as e:
                logger.error(f"groq_whisper: API status error (attempt {attempt + 1}): {e.status_code} {e.message}")
                if attempt == self._max_retries - 1:
                    return []
                _time.sleep(3)
            except Exception as e:
                logger.error(f"groq_whisper: unexpected error (attempt {attempt + 1}): {type(e).__name__}: {e}")
                if attempt == self._max_retries - 1:
                    return []
                _time.sleep(3)

        return []

    def _parse_response(self, transcription) -> list[dict]:
        """Parse Groq transcription response into standardized segment format.
        
        Groq SDK returns a Pydantic model with:
        - transcription.text (full text)
        - transcription.segments (list of segments with timing)
        - transcription.words (list of words with timing)
        """
        segments = []

        # Get raw data — handle Pydantic v2 model (groq SDK >=0.9)
        if hasattr(transcription, "segments"):
            raw_segments = transcription.segments or []
            raw_words = getattr(transcription, "words", None) or []
        elif isinstance(transcription, dict):
            raw_segments = transcription.get("segments", [])
            raw_words = transcription.get("words", [])
        else:
            # Pydantic v2: use model_dump() if available
            try:
                if hasattr(transcription, "model_dump"):
                    data = transcription.model_dump()
                else:
                    data = json.loads(str(transcription))
                raw_segments = data.get("segments", [])
                raw_words = data.get("words", [])
            except (json.JSONDecodeError, AttributeError, TypeError):
                logger.error("groq_whisper: failed to parse response")
                return []

        # Build word list
        all_words = []
        for w in raw_words:
            word_data = self._extract_word(w)
            if word_data:
                all_words.append(word_data)

        # Build segments with their words (half-open interval matching)
        for seg in raw_segments:
            seg_start = self._get_float(seg, "start", 0)
            seg_end = self._get_float(seg, "end", 0)
            seg_text = self._get_str(seg, "text", "").strip()

            if not seg_text:
                continue

            # Find words belonging to this segment (word start within segment bounds)
            seg_words = [
                w for w in all_words
                if w["start"] >= seg_start - 0.01 and w["start"] < seg_end + 0.01
            ]

            segments.append({
                "start": round(seg_start, 3),
                "end": round(seg_end, 3),
                "text": seg_text,
                "words": seg_words,
            })

        # If no segments but we have words, create segments from word groups
        if not segments and all_words:
            segments = self._words_to_segments(all_words)

        return segments

    def _extract_word(self, w) -> Optional[dict]:
        """Extract word data from Groq word object."""
        if isinstance(w, dict):
            word = w.get("word", "").strip()
            start = w.get("start", 0)
            end = w.get("end", 0)
        elif hasattr(w, "word"):
            word = (w.word or "").strip()
            start = getattr(w, "start", 0) or 0
            end = getattr(w, "end", 0) or 0
        else:
            return None

        if not word:
            return None
        return {"word": word, "start": round(float(start), 3), "end": round(float(end), 3)}

    def _get_float(self, obj, key: str, default: float) -> float:
        """Get float from dict or object attribute."""
        if isinstance(obj, dict):
            return float(obj.get(key, default))
        return float(getattr(obj, key, default))

    def _get_str(self, obj, key: str, default: str) -> str:
        """Get string from dict or object attribute."""
        if isinstance(obj, dict):
            return str(obj.get(key, default))
        return str(getattr(obj, key, default))

    def _words_to_segments(self, words: list[dict], max_per_segment: int = 30) -> list[dict]:
        """Group words into segments when API returns words without segments."""
        segments = []
        for i in range(0, len(words), max_per_segment):
            chunk = words[i:i + max_per_segment]
            segments.append({
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"],
                "text": " ".join(w["word"] for w in chunk),
                "words": chunk,
            })
        return segments

    # ─── Chunked Transcription (for files > 25MB) ────────────────────────────

    async def _transcribe_chunked(self, video_path: str, language: str) -> list[dict]:
        """Split audio into chunks and transcribe each sequentially.

        Used when compressed FLAC exceeds 25MB (very long videos > 2hrs).
        """
        # Get audio duration
        duration = await self._get_duration(video_path)
        if duration <= 0:
            return []

        # Calculate chunks
        num_chunks = max(1, int(duration / CHUNK_DURATION_SECONDS) + 1)
        chunk_duration = duration / num_chunks
        logger.info(f"groq_whisper: chunking {duration:.0f}s into {num_chunks} parts ({chunk_duration:.0f}s each)")

        all_segments = []
        for i in range(num_chunks):
            start_time = i * chunk_duration
            end_time = min((i + 1) * chunk_duration, duration)

            # Extract chunk as FLAC
            chunk_base, _ = os.path.splitext(video_path)
            chunk_path = f"{chunk_base}_chunk{i:02d}.flac"
            try:
                await self._extract_chunk_flac(video_path, chunk_path, start_time, end_time)

                if not os.path.exists(chunk_path):
                    continue

                # Transcribe chunk
                loop = asyncio.get_event_loop()
                chunk_segments = await loop.run_in_executor(
                    None, self._call_groq_api, chunk_path, language
                )

                # Offset timestamps by chunk start time
                for seg in chunk_segments:
                    seg["start"] = round(seg["start"] + start_time, 3)
                    seg["end"] = round(seg["end"] + start_time, 3)
                    for w in seg.get("words", []):
                        w["start"] = round(w["start"] + start_time, 3)
                        w["end"] = round(w["end"] + start_time, 3)

                all_segments.extend(chunk_segments)
                logger.info(f"groq_whisper: chunk {i + 1}/{num_chunks} done ({len(chunk_segments)} segments)")

                # Small delay between chunks to respect rate limit (20 RPM = 3s gap)
                if i < num_chunks - 1:
                    await asyncio.sleep(3)

            finally:
                if os.path.exists(chunk_path):
                    os.remove(chunk_path)

        return all_segments

    async def _extract_chunk_flac(
        self, input_path: str, output_path: str, start: float, end: float
    ) -> None:
        """Extract a time slice as FLAC 16kHz mono."""
        duration = end - start
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-ss", str(start),
            "-t", str(duration),
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "flac",
            "-loglevel", "error",
            output_path,
        ]
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: subprocess.run(cmd, capture_output=True, timeout=120)
        )

    async def _get_duration(self, file_path: str) -> float:
        """Get media duration using ffprobe."""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            file_path,
        ]
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        )
        if result.returncode != 0:
            return 0
        try:
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
        except (json.JSONDecodeError, ValueError):
            return 0
