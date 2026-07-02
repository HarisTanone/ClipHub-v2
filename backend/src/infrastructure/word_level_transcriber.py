"""WordLevelTranscriber — Word-level transcription on TRIMMED clips.

Runs Groq Whisper API on small trimmed clip files (45-180s each).
Fallback: Faster-Whisper Medium local (CPU/int8).

Key insight: Whisper on a trimmed clip returns 0-based timestamps.
No offset calculation or relativization needed.

Architecture:
1. For each trimmed clip_XX.mp4, extract audio as WAV (16kHz mono)
2. Upload to Groq Whisper API with word-level granularity
3. If Groq fails (rate limit, error) → fallback to Faster-Whisper local
4. Return words with 0-based timestamps (relative to clip start)
5. Cleanup intermediate WAV files
"""
import asyncio
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)


class WordLevelTranscriptionError(Exception):
    """Raised when both Groq and Faster-Whisper fail for a clip."""
    pass


class WordLevelTranscriber:
    """Word-level transcription per trimmed clip.

    Primary: Groq Whisper API (fast, cloud, word timestamps)
    Fallback: Faster-Whisper Medium (local, CPU/int8)

    Output format: [{word: str, start: float, end: float}]
    Timestamps are 0-based (relative to clip start) — no offset needed.
    """

    GROQ_MODEL = "whisper-large-v3-turbo"
    GROQ_MAX_FILE_SIZE_MB = 25
    MAX_CONCURRENT = 3
    MIN_DELAY_BETWEEN_CALLS = 1.5  # seconds (rate limit protection)

    def __init__(self):
        self._groq_client = None
        self._faster_whisper_model = None
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)
        self._last_groq_call_time = 0.0
        self._rate_limit_lock = asyncio.Lock()

    # ─── Properties (lazy init) ───────────────────────────────────────────────

    @property
    def groq_client(self):
        if self._groq_client is None:
            from groq import Groq
            if not settings.GROQ_API_KEY:
                raise WordLevelTranscriptionError("GROQ_API_KEY not configured")
            self._groq_client = Groq(api_key=settings.GROQ_API_KEY)
        return self._groq_client

    # Class-level singleton: only ONE model instance across all WordLevelTranscriber instances
    _shared_fw_model = None
    _fw_model_lock = None  # Will be initialized on first use

    @property
    def faster_whisper_model(self):
        # Use class-level singleton to prevent concurrent model loading crash
        if WordLevelTranscriber._shared_fw_model is not None:
            return WordLevelTranscriber._shared_fw_model

        if self._faster_whisper_model is not None:
            return self._faster_whisper_model

        from faster_whisper import WhisperModel
        model_size = settings.WHISPER_MODEL_SIZE

        device = "cpu"
        compute_type = "int8"
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
                compute_type = "float16"
                logger.info(f"word_level: loading Faster-Whisper {model_size} (CUDA/float16)")
            else:
                logger.info(f"word_level: loading Faster-Whisper {model_size} (CPU/int8)")
        except ImportError:
            logger.info(f"word_level: loading Faster-Whisper {model_size} (CPU/int8, no torch)")

        model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            num_workers=1,
            cpu_threads=settings.WHISPER_THREADS,
        )
        # Store as class-level singleton
        WordLevelTranscriber._shared_fw_model = model
        self._faster_whisper_model = model
        return model

    # ─── Main Entry Point ─────────────────────────────────────────────────────

    async def transcribe_all_clips(
        self,
        clips_dir: str,
        clip_ranks: list[int],
        language: str = "id",
    ) -> dict[int, list[dict]]:
        """Transcribe all trimmed clips concurrently.

        Args:
            clips_dir: Directory containing clip_XX.mp4 files (from FFmpeg trim)
            clip_ranks: List of clip rank numbers [1, 2, 3, ...]
            language: Language hint for Whisper (prevents misdetection)

        Returns:
            Dict mapping clip_rank → list of word dicts [{word, start, end}]
            Words are 0-based (relative to clip start). No offset needed.
        """
        logger.info(
            f"word_level: starting transcription for {len(clip_ranks)} clips, "
            f"lang={language}, max_concurrent={self.MAX_CONCURRENT}"
        )

        tasks = []
        for rank in clip_ranks:
            clip_path = os.path.join(clips_dir, f"clip_{rank:02d}.mp4")
            tasks.append(self._transcribe_one(rank, clip_path, language))

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results: dict[int, list[dict]] = {}
        success_count = 0
        for rank, result in zip(clip_ranks, results_list):
            if isinstance(result, Exception):
                logger.error(f"word_level: clip {rank} FAILED: {result}")
                results[rank] = []
            else:
                results[rank] = result["words"]
                source = result["source"]
                word_count = len(result["words"])
                if word_count > 0:
                    success_count += 1
                    last_word = result["words"][-1]
                    logger.info(
                        f"word_level: clip {rank} → {word_count} words via {source}, "
                        f"coverage=0.0s-{last_word['end']:.1f}s"
                    )
                else:
                    logger.warning(f"word_level: clip {rank} → 0 words via {source}")

        # Cleanup WAV files
        self._cleanup_wav_files(clips_dir)

        logger.info(
            f"word_level: done — {success_count}/{len(clip_ranks)} clips with words, "
            f"{sum(len(w) for w in results.values())} total words"
        )
        return results

    # ─── Per-Clip Transcription ───────────────────────────────────────────────

    async def _transcribe_one(
        self, rank: int, clip_path: str, language: str
    ) -> dict:
        """Transcribe a single clip: Faster-Whisper GPU (primary) → Groq API (fallback).

        Returns: {words: [{word, start, end}], source: 'faster_whisper'|'groq'}
        """
        async with self._semaphore:
            if not os.path.exists(clip_path):
                raise WordLevelTranscriptionError(f"Clip not found: {clip_path}")

            # Extract audio WAV (16kHz mono)
            audio_path = await self._extract_audio(clip_path)

            try:
                # Primary: Faster-Whisper local GPU (no rate limit, no network)
                words = await self._faster_whisper_transcribe(audio_path, language)
                if words:
                    return {"words": words, "source": "faster_whisper"}
                raise WordLevelTranscriptionError("Faster-Whisper returned 0 words")
            except Exception as fw_err:
                logger.warning(
                    f"word_level: clip {rank} Faster-Whisper failed ({fw_err}), "
                    f"trying Groq API fallback..."
                )

                try:
                    # Fallback: Groq Whisper API (cloud)
                    words = await self._groq_transcribe(audio_path, language)
                    if words:
                        return {"words": words, "source": "groq"}
                    raise WordLevelTranscriptionError("Groq returned 0 words")
                except Exception as groq_err:
                    raise WordLevelTranscriptionError(
                        f"Both failed. FW: {fw_err} | Groq: {groq_err}"
                    )

    # ─── Audio Extraction ─────────────────────────────────────────────────────

    async def _extract_audio(self, clip_path: str) -> str:
        """Extract WAV (16kHz mono) from trimmed clip via FFmpeg."""
        audio_path = clip_path.rsplit(".", 1)[0] + "_wordlevel.wav"
        cmd = [
            "ffmpeg", "-y", "-i", clip_path,
            "-vn", "-ar", "16000", "-ac", "1",
            "-c:a", "pcm_s16le", "-loglevel", "error",
            audio_path,
        ]

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=60),
        )

        if result.returncode != 0:
            raise WordLevelTranscriptionError(
                f"FFmpeg audio extraction failed: {result.stderr[:200]}"
            )

        if not os.path.exists(audio_path):
            raise WordLevelTranscriptionError(f"Audio file not created: {audio_path}")

        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        if size_mb > self.GROQ_MAX_FILE_SIZE_MB:
            logger.warning(
                f"word_level: audio {size_mb:.1f}MB > {self.GROQ_MAX_FILE_SIZE_MB}MB limit"
            )

        return audio_path

    # ─── Groq Whisper API ─────────────────────────────────────────────────────

    async def _groq_transcribe(
        self, audio_path: str, language: str, max_retries: int = 2
    ) -> list[dict]:
        """Upload to Groq Whisper API with word-level granularity."""
        # Rate limit: enforce minimum delay between calls
        async with self._rate_limit_lock:
            now = time.monotonic()
            elapsed = now - self._last_groq_call_time
            if elapsed < self.MIN_DELAY_BETWEEN_CALLS:
                await asyncio.sleep(self.MIN_DELAY_BETWEEN_CALLS - elapsed)
            self._last_groq_call_time = time.monotonic()

        # Retry with backoff
        for attempt in range(max_retries + 1):
            try:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, self._groq_call_sync, audio_path, language
                )
            except Exception as e:
                error_str = str(e).lower()
                is_rate_limit = "429" in error_str or "rate" in error_str

                if is_rate_limit and attempt < max_retries:
                    wait = (2 ** attempt) * 5  # 5s, 10s
                    logger.warning(
                        f"word_level: Groq rate limited, wait {wait}s "
                        f"(attempt {attempt + 1}/{max_retries + 1})"
                    )
                    await asyncio.sleep(wait)
                    continue
                raise

    def _groq_call_sync(self, audio_path: str, language: str) -> list[dict]:
        """Blocking Groq Whisper API call (run in executor)."""
        with open(audio_path, "rb") as f:
            response = self.groq_client.audio.transcriptions.create(
                model=self.GROQ_MODEL,
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["word"],
                language=language,
                temperature=0.0,
            )

        words = []
        if hasattr(response, "words") and response.words:
            for w in response.words:
                # Groq may return words as dicts or objects — handle both
                if isinstance(w, dict):
                    word_text = (w.get("word", "") or "").strip()
                    w_start = w.get("start", 0)
                    w_end = w.get("end", 0)
                else:
                    word_text = (w.word or "").strip()
                    w_start = w.start
                    w_end = w.end
                if word_text:
                    words.append({
                        "word": word_text,
                        "start": round(float(w_start), 3),
                        "end": round(float(w_end), 3),
                    })

        return words

    # ─── Faster-Whisper Local Fallback ────────────────────────────────────────

    async def _faster_whisper_transcribe(
        self, audio_path: str, language: str
    ) -> list[dict]:
        """Local Faster-Whisper fallback (CPU/int8)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._faster_whisper_call_sync, audio_path, language
        )

    def _faster_whisper_call_sync(self, audio_path: str, language: str) -> list[dict]:
        """Blocking Faster-Whisper transcription."""
        segments, info = self.faster_whisper_model.transcribe(
            audio_path,
            word_timestamps=True,
            language=language,
            vad_filter=False,  # Clip already trimmed, no need for VAD
            beam_size=5,
            temperature=0.0,
        )

        words = []
        for seg in segments:
            if not seg.words:
                continue
            for w in seg.words:
                word_text = (w.word or "").strip()
                if word_text:
                    words.append({
                        "word": word_text,
                        "start": round(float(w.start), 3),
                        "end": round(float(w.end), 3),
                    })

        return words

    # ─── Cleanup ──────────────────────────────────────────────────────────────

    def _cleanup_wav_files(self, clips_dir: str) -> None:
        """Remove intermediate WAV files to save disk space."""
        for wav_file in Path(clips_dir).glob("*_wordlevel.wav"):
            try:
                wav_file.unlink()
                logger.debug(f"word_level: cleaned up {wav_file.name}")
            except OSError:
                pass
