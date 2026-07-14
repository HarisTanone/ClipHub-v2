"""Word-level transcription on trimmed clips.

Uses Groq Whisper through 9router first and preserves Faster-Whisper as the
local fallback for small trimmed clip files (45-180s each).

Key insight: Whisper on a trimmed clip returns 0-based timestamps.
No offset calculation or relativization needed.

Architecture:
1. For each trimmed clip_XX.mp4, extract audio as WAV (16kHz mono)
2. Transcribe through 9router with Groq word timestamps
3. Fall back to local Faster-Whisper on any error or missing word timestamps
4. Return words with 0-based timestamps (relative to clip start)
5. Cleanup intermediate WAV files
"""
import asyncio
import logging
import os
import subprocess
from pathlib import Path

from src.config import settings

logger = logging.getLogger(__name__)


class WordLevelTranscriptionError(Exception):
    """Raised when both Groq and Faster-Whisper fail for a clip."""
    pass


class WordLevelTranscriber:
    """Word-level transcription per trimmed clip.

    Primary: Groq Whisper through 9router (fast, word timestamps)
    Fallback: Faster-Whisper Medium (local, CPU/int8)

    Output format: [{word: str, start: float, end: float}]
    Timestamps are 0-based (relative to clip start) — no offset needed.
    """

    GROQ_MAX_FILE_SIZE_MB = 25
    MAX_CONCURRENT = 3

    def __init__(self):
        self._router_whisper = None
        self._faster_whisper_model = None
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)
        # Initialize class-level model lock (safe to call multiple times)
        if WordLevelTranscriber._fw_model_lock is None:
            WordLevelTranscriber._fw_model_lock = asyncio.Lock()

    # ─── Properties (lazy init) ───────────────────────────────────────────────

    def _get_router_whisper(self):
        if self._router_whisper is None:
            from src.infrastructure.groq_whisper import GroqWhisperTranscriber
            self._router_whisper = GroqWhisperTranscriber()
        return self._router_whisper

    # Class-level singleton: only ONE model instance across all WordLevelTranscriber instances
    _shared_fw_model = None
    _fw_model_lock: asyncio.Lock = None  # Initialized on first __init__

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
                # Check free VRAM before attempting GPU load
                free_mem = torch.cuda.mem_get_info()[0] / (1024**3)  # GB
                if free_mem < 2.5:
                    logger.warning(
                        f"word_level: insufficient VRAM ({free_mem:.1f}GB free), "
                        f"falling back to CPU/int8"
                    )
                else:
                    device = "cuda"
                    compute_type = "float16"
                    logger.info(
                        f"word_level: loading Faster-Whisper {model_size} "
                        f"(CUDA/float16, {free_mem:.1f}GB free)"
                    )
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
        """Transcribe one clip: 9router Groq first, then local Faster-Whisper.

        Returns: {words: [{word, start, end}], source: str}
        """
        async with self._semaphore:
            if not os.path.exists(clip_path):
                raise WordLevelTranscriptionError(f"Clip not found: {clip_path}")

            # Extract audio WAV (16kHz mono)
            audio_path = await self._extract_audio(clip_path)

            router = self._get_router_whisper()
            if router.is_available:
                try:
                    segments = await router.transcribe(audio_path, language)
                    words = self._flatten_router_words(segments)
                    if words:
                        # Keep the historical internal source label unchanged.
                        return {"words": words, "source": "groq"}
                    logger.warning(
                        f"word_level: clip {rank} 9router returned no word timestamps; "
                        "using local Whisper"
                    )
                except Exception as router_err:
                    logger.warning(
                        f"word_level: clip {rank} 9router failed ({router_err}); "
                        "using local Whisper"
                    )

            try:
                words = await self._faster_whisper_transcribe(audio_path, language)
                if words:
                    return {"words": words, "source": "faster_whisper"}
                raise WordLevelTranscriptionError("Faster-Whisper returned 0 words")
            except Exception as local_err:
                raise WordLevelTranscriptionError(
                    f"9router Groq and local Faster-Whisper both returned no usable words: {local_err}"
                ) from local_err

    @staticmethod
    def _flatten_router_words(segments: list[dict]) -> list[dict]:
        """Flatten standardized segments without altering word timestamps."""
        words: list[dict] = []
        last_start = -1.0
        for segment in segments or []:
            for word in segment.get("words", []) or []:
                text = str(word.get("word", "")).strip()
                try:
                    start = round(float(word.get("start", 0)), 3)
                    end = round(float(word.get("end", 0)), 3)
                except (TypeError, ValueError):
                    continue
                if not text or start < 0 or end < start or start < last_start:
                    continue
                words.append({"word": text, "start": start, "end": end})
                last_start = start
        return words

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

    # ─── Faster-Whisper Local Fallback ────────────────────────────────────────

    async def _faster_whisper_transcribe(
        self, audio_path: str, language: str
    ) -> list[dict]:
        """Local Faster-Whisper with singleton model (prevents concurrent CUDA OOM).

        Uses asyncio.Lock to ensure only one model load at a time,
        preventing 3x concurrent VRAM allocation that causes OOM.
        """
        # Ensure only one model load at a time
        if WordLevelTranscriber._shared_fw_model is None:
            if WordLevelTranscriber._fw_model_lock is None:
                WordLevelTranscriber._fw_model_lock = asyncio.Lock()
            async with WordLevelTranscriber._fw_model_lock:
                # Double-check after acquiring lock (another task may have loaded it)
                if WordLevelTranscriber._shared_fw_model is None:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, lambda: self.faster_whisper_model)

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
