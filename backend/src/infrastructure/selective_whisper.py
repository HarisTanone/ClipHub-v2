"""SelectiveWhisperTranscriber — TAHAP 4: Word-level transcription on short clips only.

Runs Faster-Whisper ONLY on micro-sliced audio clips (not the full video).
Maps local word timestamps → absolute video timestamps.

Architecture:
1. Reuse existing IWhisperLocal (faster-whisper backend)
2. Transcribe each AudioSlice (short clips, 30-120s each)
3. Apply time offset to map local → absolute timestamps
4. Filter words that fall within the original highlight range
5. Return Word objects compatible with subtitle rendering pipeline
"""
import asyncio
import logging
from typing import Optional

from src.config import settings
from src.domain.entities import AudioSlice, Word
from src.domain.interfaces import IWhisperLocal

logger = logging.getLogger(__name__)


class SelectiveWhisperTranscriber:
    """TAHAP 4 implementation: Word-level transcription on short clips.

    Wraps the existing IWhisperLocal to add:
    - Time offset mapping (local → absolute)
    - Word range filtering (keep only words within highlight bounds)
    - Timeout protection per clip
    - Fallback behavior (return empty on failure, don't crash)
    """

    CLIP_TIMEOUT = 300  # 5 min max per clip

    def __init__(self, whisper_local: IWhisperLocal):
        self._whisper = whisper_local

    # ─── Main Entry Point ─────────────────────────────────────────────────────

    async def transcribe_clip(self, audio_slice: AudioSlice) -> list[Word]:
        """Transcribe a single audio clip and return words with absolute timestamps.

        Args:
            audio_slice: AudioSlice from MicroSlicer with path and timing info

        Returns:
            List of Word objects with absolute video timestamps.
            Returns empty list on failure (non-fatal).
        """
        try:
            raw_segments = await asyncio.wait_for(
                self._whisper.transcribe_clip(audio_slice.audio_path),
                timeout=self.CLIP_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"v2_selective_whisper: clip_{audio_slice.clip_rank:03d} "
                f"timed out ({self.CLIP_TIMEOUT}s)"
            )
            return []
        except Exception as e:
            logger.warning(
                f"v2_selective_whisper: clip_{audio_slice.clip_rank:03d} "
                f"transcription failed: {e}"
            )
            return []

        if not raw_segments:
            logger.debug(
                f"v2_selective_whisper: clip_{audio_slice.clip_rank:03d} "
                f"returned no segments"
            )
            return []

        # Map local timestamps → absolute and filter to highlight range
        words = self._apply_offset_and_filter(
            raw_segments, audio_slice
        )

        logger.debug(
            f"v2_selective_whisper: clip_{audio_slice.clip_rank:03d} → "
            f"{len(words)} words [{audio_slice.original_start:.1f}s-{audio_slice.original_end:.1f}s]"
        )
        return words

    async def transcribe_all_clips(
        self, audio_slices: list[AudioSlice], max_parallel: int = 1
    ) -> dict[int, list[Word]]:
        """Transcribe all audio slices, returning words per clip rank.

        Args:
            audio_slices: List of AudioSlice from MicroSlicer
            max_parallel: Max concurrent Whisper processes (default 1 for CPU)

        Returns:
            Dict mapping clip_rank → list[Word]
        """
        semaphore = asyncio.Semaphore(max_parallel)
        results: dict[int, list[Word]] = {}

        async def process_one(audio_slice: AudioSlice):
            async with semaphore:
                words = await self.transcribe_clip(audio_slice)
                results[audio_slice.clip_rank] = words

        tasks = [process_one(s) for s in audio_slices]
        await asyncio.gather(*tasks)

        success_count = sum(1 for w in results.values() if w)
        logger.info(
            f"v2_selective_whisper: {success_count}/{len(audio_slices)} clips transcribed"
        )
        return results

    # ─── Offset Mapping & Filtering ───────────────────────────────────────────

    def _apply_offset_and_filter(
        self, raw_segments: list[dict], audio_slice: AudioSlice
    ) -> list[Word]:
        """Apply time offset and filter words to original highlight range.

        local_timestamp + padded_start = absolute_timestamp

        Only keeps words that fall within [original_start, original_end]
        (the actual highlight, not the padded region).
        """
        words = []
        offset = audio_slice.padded_start

        for segment in raw_segments:
            seg_words = segment.get("words", [])
            for w in seg_words:
                word_text = w.get("word", "").strip()
                if not word_text:
                    continue

                # Map to absolute timestamps
                abs_start = round(w.get("start", 0) + offset, 3)
                abs_end = round(w.get("end", 0) + offset, 3)

                # Filter: keep only words within the original highlight range
                # Use slight tolerance (±0.5s) at boundaries
                if abs_end < audio_slice.original_start - 0.5:
                    continue  # Word ends before highlight starts
                if abs_start > audio_slice.original_end + 0.5:
                    continue  # Word starts after highlight ends

                words.append(Word(
                    word=word_text,
                    start=abs_start,
                    end=abs_end,
                    highlight=False,
                ))

        return words

    # ─── Utility ──────────────────────────────────────────────────────────────

    @staticmethod
    def words_to_relative(words: list[Word], clip_start: float) -> list[Word]:
        """Convert absolute word timestamps to relative (from clip start).

        Used when subtitle renderer needs timestamps relative to clip.
        """
        return [
            Word(
                word=w.word,
                start=round(w.start - clip_start, 3),
                end=round(w.end - clip_start, 3),
                highlight=w.highlight,
            )
            for w in words
        ]
