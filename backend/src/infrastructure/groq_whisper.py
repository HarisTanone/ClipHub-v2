"""Groq Whisper transcription through 9router's OpenAI-compatible endpoint.

Flow:
1. Send already prepared, small audio files without re-encoding
2. Compress other media to FLAC 16kHz mono (minimizes file size)
3. If file > 25MB: chunk into segments
4. Send to 9router ``/v1/audio/transcriptions`` with word timestamps
5. Return unified word-level JSON
"""
import asyncio
import json
import logging
import math
import mimetypes
import os
import subprocess
import time
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Max file size for Groq free tier (bytes)
GROQ_MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
CHUNK_DURATION_SECONDS = 600  # 10 minutes per chunk
SUPPORTED_UPLOAD_EXTENSIONS = {
    ".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".webm"
}


class NineRouterWhisperError(RuntimeError):
    """Raised when 9router cannot provide a usable transcription response."""


class GroqWhisperTranscriber:
    """Transcribe audio with Groq Whisper routed through local 9router.

    The historical class name is retained so callers do not need to change
    their output handling. No direct Groq credential is used here.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        self._base_url = (base_url or settings.NINE_ROUTER_BASE_URL).rstrip("/")
        self._api_key = (
            settings.NINE_ROUTER_API_KEY if api_key is None else api_key
        )
        self._model = (
            model or settings.NINE_ROUTER_WHISPER_MODEL
            or "groq/whisper-large-v3-turbo"
        )
        self._timeout = timeout or settings.NINE_ROUTER_WHISPER_TIMEOUT
        self._max_retries = max(
            1,
            max_retries or settings.NINE_ROUTER_WHISPER_MAX_RETRIES,
        )

    @property
    def is_available(self) -> bool:
        """Return whether the 9router Whisper route is enabled/configured."""
        return bool(settings.NINE_ROUTER_WHISPER_ENABLED and self._base_url)

    def _transcriptions_url(self) -> str:
        """Resolve a base, chat, or full audio URL to the transcription route."""
        base_url = self._base_url
        if base_url.endswith("/audio/transcriptions"):
            return base_url
        if base_url.endswith("/chat/completions"):
            base_url = base_url[: -len("/chat/completions")]
        return f"{base_url}/audio/transcriptions"

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
            logger.info("nine_router_whisper: route is not configured; using local fallback")
            return []

        if not os.path.exists(video_path) or os.path.getsize(video_path) <= 0:
            logger.warning("nine_router_whisper: input file is missing or empty")
            return []

        # Already prepared audio (including the WAV generated for word-level
        # subtitles) is uploaded directly, avoiding a second FFmpeg pass.
        base, _ = os.path.splitext(video_path)
        flac_path = base + "_groq.flac"
        upload_path = video_path
        cleanup_upload = False
        try:
            extension = os.path.splitext(video_path)[1].lower()
            if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
                await self._compress_to_flac(video_path, flac_path)
                if not os.path.exists(flac_path) or os.path.getsize(flac_path) <= 0:
                    logger.error("nine_router_whisper: FLAC compression failed")
                    return []
                upload_path = flac_path
                cleanup_upload = True

            file_size = os.path.getsize(upload_path)
            file_size_mb = file_size / (1024 * 1024)
            logger.info(
                "nine_router_whisper: prepared %s (%.1fMB)",
                os.path.basename(upload_path),
                file_size_mb,
            )

            # Step 2: Decide single or chunked transcription
            if file_size <= GROQ_MAX_FILE_SIZE:
                segments = await self._transcribe_single(upload_path, language)
            else:
                logger.info(
                    "nine_router_whisper: file %.1fMB > 25MB, chunking",
                    file_size_mb,
                )
                segments = await self._transcribe_chunked(video_path, language)

            if segments:
                total_words = sum(len(s.get("words", [])) for s in segments)
                logger.info(
                    f"nine_router_whisper: {len(segments)} segments, {total_words} words, "
                    f"model={self._model}"
                )
                # Track usage
                try:
                    from src.infrastructure.model_status import ModelStatusTracker
                    # Preserve the existing status key consumed by the UI.
                    ModelStatusTracker().mark_success("groq_whisper")
                except Exception:
                    pass
            return segments

        except Exception as e:
            logger.warning(f"nine_router_whisper: failed, using local fallback: {e}")
            return []
        finally:
            if cleanup_upload and os.path.exists(flac_path):
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
            logger.error(f"nine_router_whisper: ffmpeg flac failed: {result.stderr[:200]}")

    async def _transcribe_single(self, flac_path: str, language: str) -> list[dict]:
        """Send single file to Groq API and get word-level transcription."""
        loop = asyncio.get_running_loop()
        # Dynamic timeout preserves the configured floor while allowing uploads
        # a little extra time for larger payloads.
        file_size_mb = os.path.getsize(flac_path) / (1024 * 1024)
        timeout = max(self._timeout, int(self._timeout + file_size_mb * 2))
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self._call_groq_api, flac_path, language),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"nine_router_whisper: request timeout ({timeout}s)")
            return []

    def _call_groq_api(self, audio_path: str, language: str) -> list[dict]:
        """Post multipart audio to 9router and normalize its JSON response."""
        last_error = "unknown error"
        for attempt in range(self._max_retries):
            try:
                start_time = time.monotonic()
                headers = {}
                if self._api_key:
                    headers["Authorization"] = f"Bearer {self._api_key}"

                with open(audio_path, "rb") as f:
                    mime_type = mimetypes.guess_type(audio_path)[0] or "application/octet-stream"
                    multipart = [
                        ("file", (os.path.basename(audio_path), f, mime_type)),
                        ("model", (None, self._model)),
                        ("language", (None, language)),
                        ("response_format", (None, "verbose_json")),
                        ("temperature", (None, "0")),
                        # Word timing keeps the existing subtitle output shape;
                        # segment timing keeps transcript-analysis compatibility.
                        ("timestamp_granularities[]", (None, "word")),
                        ("timestamp_granularities[]", (None, "segment")),
                    ]
                    with httpx.Client(timeout=self._timeout) as client:
                        response = client.post(
                            self._transcriptions_url(),
                            headers=headers,
                            files=multipart,
                        )

                if response.status_code >= 400:
                    try:
                        detail = response.json()
                    except ValueError:
                        detail = response.text[:500]
                    raise NineRouterWhisperError(
                        f"HTTP {response.status_code}: {detail}"
                    )

                try:
                    transcription = response.json()
                except ValueError as exc:
                    raise NineRouterWhisperError("response is not valid JSON") from exc
                if not isinstance(transcription, dict):
                    raise NineRouterWhisperError("response JSON is not an object")

                elapsed = time.monotonic() - start_time
                logger.info(f"nine_router_whisper: API response in {elapsed:.1f}s")
                segments = self._parse_response(transcription)
                if not segments:
                    raise NineRouterWhisperError("response has no usable segments")
                return segments

            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    "nine_router_whisper: attempt %s/%s failed: %s",
                    attempt + 1,
                    self._max_retries,
                    last_error,
                )
                if attempt < self._max_retries - 1:
                    time.sleep(min(2 ** attempt, 5))

        logger.warning(f"nine_router_whisper: exhausted attempts: {last_error}")
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
            raw_segments = transcription.get("segments") or []
            raw_words = transcription.get("words") or []
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
                logger.error("nine_router_whisper: failed to parse response")
                return []

        # Some OpenAI-compatible gateways return words at the top level, while
        # others nest them under each segment.
        if not raw_words:
            nested_words = []
            for segment in raw_segments:
                if isinstance(segment, dict):
                    nested_words.extend(segment.get("words") or [])
                else:
                    nested_words.extend(getattr(segment, "words", None) or [])
            raw_words = nested_words

        # If still no words, synthesize word-level timing from segment text.
        # This provides approximate word timestamps when the API only returns
        # segment-level timing (common with 9router/Groq free tier).
        if not raw_words and raw_segments:
            raw_words = self._synthesize_words_from_segments(raw_segments)

        all_words = []
        for w in raw_words:
            word_data = self._extract_word(w)
            if word_data:
                all_words.append(word_data)
        all_words.sort(key=lambda item: (item["start"], item["end"]))

        # Assign each word once using its midpoint. This avoids duplicated words
        # where adjacent API segments share a boundary timestamp.
        assigned_word_indexes: set[int] = set()
        for seg in raw_segments:
            seg_start = self._get_float(seg, "start", 0)
            seg_end = self._get_float(seg, "end", 0)
            seg_text = self._get_str(seg, "text", "").strip()

            if not seg_text or seg_end < seg_start:
                continue

            seg_words = []
            for word_index, word in enumerate(all_words):
                if word_index in assigned_word_indexes:
                    continue
                midpoint = (word["start"] + word["end"]) / 2
                if seg_start - 0.02 <= midpoint <= seg_end + 0.02:
                    seg_words.append(word)
                    assigned_word_indexes.add(word_index)

            segments.append({
                "start": round(seg_start, 3),
                "end": round(seg_end, 3),
                "text": seg_text,
                "words": seg_words,
            })

        # Do not silently lose valid word timestamps because of a small router
        # boundary mismatch. Attach any unmatched word to the nearest segment.
        if segments and len(assigned_word_indexes) < len(all_words):
            for word_index, word in enumerate(all_words):
                if word_index in assigned_word_indexes:
                    continue
                midpoint = (word["start"] + word["end"]) / 2

                def distance(segment: dict) -> float:
                    if segment["start"] <= midpoint <= segment["end"]:
                        return 0.0
                    return min(
                        abs(midpoint - segment["start"]),
                        abs(midpoint - segment["end"]),
                    )

                nearest = min(segments, key=distance)
                nearest["words"].append(word)
            for segment in segments:
                segment["words"].sort(key=lambda item: (item["start"], item["end"]))

        # If no segments but we have words, create segments from word groups
        if not segments and all_words:
            segments = self._words_to_segments(all_words)

        segments.sort(key=lambda item: (item["start"], item["end"]))
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
        try:
            start_value = float(start)
            end_value = float(end)
        except (TypeError, ValueError):
            return None
        if (
            not math.isfinite(start_value)
            or not math.isfinite(end_value)
            or start_value < 0
            or end_value < start_value
        ):
            return None
        return {
            "word": word,
            "start": round(start_value, 3),
            "end": round(end_value, 3),
        }

    def _get_float(self, obj, key: str, default: float) -> float:
        """Get float from dict or object attribute."""
        try:
            value = obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)
            number = float(value)
            return number if math.isfinite(number) else default
        except (TypeError, ValueError):
            return default

    def _get_str(self, obj, key: str, default: str) -> str:
        """Get string from dict or object attribute."""
        value = obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)
        return default if value is None else str(value)

    def _synthesize_words_from_segments(self, raw_segments: list) -> list[dict]:
        """Synthesize word-level timing from segment text when API omits words.

        Distributes words evenly across each segment's time span. This is an
        approximation but sufficient for subtitle display (local Whisper fallback
        provides precise timing if this path is taken for word-level transcription).
        """
        synthesized = []
        for seg in raw_segments:
            seg_start = self._get_float(seg, "start", 0)
            seg_end = self._get_float(seg, "end", 0)
            seg_text = self._get_str(seg, "text", "").strip()

            if not seg_text or seg_end <= seg_start:
                continue

            words = seg_text.split()
            if not words:
                continue

            duration = seg_end - seg_start
            word_duration = duration / len(words)

            for i, word in enumerate(words):
                w_start = round(seg_start + i * word_duration, 3)
                w_end = round(seg_start + (i + 1) * word_duration, 3)
                synthesized.append({"word": word, "start": w_start, "end": w_end})

        return synthesized

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
        num_chunks = max(1, math.ceil(duration / CHUNK_DURATION_SECONDS))
        chunk_duration = duration / num_chunks
        logger.info(
            f"nine_router_whisper: chunking {duration:.0f}s into "
            f"{num_chunks} parts ({chunk_duration:.0f}s each)"
        )

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
                logger.info(
                    f"nine_router_whisper: chunk {i + 1}/{num_chunks} done "
                    f"({len(chunk_segments)} segments)"
                )

            finally:
                if os.path.exists(chunk_path):
                    os.remove(chunk_path)

        # Deduplicate words at chunk boundaries (fix non-monotonic timestamps)
        all_segments = self._deduplicate_chunk_boundaries(all_segments)
        return all_segments

    def _deduplicate_chunk_boundaries(self, segments: list[dict]) -> list[dict]:
        """Remove duplicate/overlapping words at chunk boundaries.
        
        When audio is chunked, words at boundaries can appear in both chunks
        with slightly different timestamps, causing non-monotonic order.
        Fix: sort segments by start time, deduplicate overlapping words.
        """
        if not segments:
            return segments

        # Sort segments by start time
        segments.sort(key=lambda s: s["start"])

        # Deduplicate words within each segment (sort + remove overlaps)
        for seg in segments:
            words = seg.get("words", [])
            if not words:
                continue
            # Sort words by start time
            words.sort(key=lambda w: w["start"])
            # Remove duplicate words (same word within 0.5s = likely duplicate)
            deduped = [words[0]]
            for w in words[1:]:
                prev = deduped[-1]
                if w["start"] < prev["start"]:
                    continue  # Skip non-monotonic
                if w["word"] == prev["word"] and abs(w["start"] - prev["start"]) < 0.5:
                    continue  # Skip duplicate
                deduped.append(w)
            seg["words"] = deduped

        # Remove duplicate segments (overlapping at chunk boundaries)
        deduped_segments = [segments[0]]
        for seg in segments[1:]:
            prev = deduped_segments[-1]
            # If this segment starts before previous ends → overlap from chunking
            if seg["start"] < prev["end"] - 0.3:
                # Merge: keep the one with more words
                if len(seg.get("words", [])) > len(prev.get("words", [])):
                    deduped_segments[-1] = seg
                continue
            deduped_segments.append(seg)

        return deduped_segments

    async def _extract_chunk_flac(
        self, input_path: str, output_path: str, start: float, end: float
    ) -> None:
        """Extract a time slice as FLAC 16kHz mono."""
        duration = end - start
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),       # Fast seek BEFORE input
            "-i", input_path,
            "-t", str(duration),
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "flac",
            "-loglevel", "error",
            output_path,
        ]
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, lambda: subprocess.run(cmd, capture_output=True, timeout=900)
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
