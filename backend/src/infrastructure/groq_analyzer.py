"""GroqAnalyzer — TAHAP 2: AI Highlight Analysis via Groq LLM (Two-Pass).

Architecture (Two-Pass + Segment ID):
  Pass 1 (8b per-chunk — fast scanning):
    - Chunk transcript with Segment IDs ([S0015 | 02:30] text)
    - Ask 8b to identify candidate clips using start_id/end_id
    - Generates ~5 candidates per chunk (over-generate)
    - Prevents timestamp hallucination via Segment ID anchoring

  Pass 2 (70b global — quality ranking):
    - Collect ALL candidates from Pass 1 (e.g. 15-20 clips)
    - Send summary to 70b for global re-ranking
    - 70b picks TOP N, assigns final scores, generates quality hooks
    - This gives global narrative understanding without full transcript

Benefits over single-pass:
  - No timestamp hallucination (Segment ID → exact Whisper timing)
  - Global comparison (70b sees all candidates at once)
  - Better hooks (70b generates hooks, not 8b)
  - Rate-limit friendly (Pass 2 is small payload for 70b)
"""
import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from functools import partial
from typing import Optional

from src.config import settings
from src.domain.entities import (
    HighlightAnalysisResult,
    HighlightCandidate,
    TranscriptResult,
    TranscriptSegment,
)
from src.domain.interfaces import IGroqAnalyzer

logger = logging.getLogger(__name__)


# ─── Metrics Data Class ──────────────────────────────────────────────────────

@dataclass
class AnalysisMetrics:
    """Structured metrics for a single analyze_highlights run."""
    video_duration: float = 0.0
    total_segments: int = 0
    chunks_processed: int = 0
    pass1_candidates_total: int = 0
    pass1_candidates_per_chunk: list[int] = field(default_factory=list)
    pass1_chunks_failed: int = 0
    pass1_time_seconds: float = 0.0
    pass2_model_used: str = ""
    pass2_fallback_triggered: bool = False
    pass2_time_seconds: float = 0.0
    validation_passed: int = 0
    validation_rejected: int = 0
    creative_direction_time_seconds: float = 0.0
    total_time_seconds: float = 0.0
    rate_limit_hits: int = 0
    final_clips_count: int = 0


class GroqAnalyzerError(Exception):
    """Raised when highlight analysis fails after all retries."""
    pass


class GroqAnalyzer(IGroqAnalyzer):
    """TAHAP 2: Two-Pass highlight analysis with Segment ID anchoring."""

    # ─── Duration Constants ───────────────────────────────────────────────────
    MIN_CLIP_DURATION = 45.0   # Minimum valid clip duration (seconds) — enforced hard
    MAX_CLIP_DURATION = 300.0  # Sanity max (5 min) — no artificial cap, AI decides based on content
    PROMPT_MIN_DURATION = 45   # Instructed min in prompts (seconds)
    PROMPT_MAX_DURATION = 180   # Soft suggestion to AI (seconds)
    OVERLAP_THRESHOLD = 0.5    # 50% overlap required to consider as duplicate
    CHUNK_OVERLAP_SECONDS = 60 # Overlap between consecutive chunks (seconds)

    # ─── Concurrency Control ──────────────────────────────────────────────────
    # Limits concurrent video analyses to prevent Groq rate limit exhaustion
    _analysis_semaphore: asyncio.Semaphore = asyncio.Semaphore(2)

    # ─── Whisper Hallucination Guard ──────────────────────────────────────────
    # Patterns indicating non-speech content (music, silence, applause, etc.)
    NON_SPEECH_PATTERNS = [
        "[musik]", "[music]", "[tepuk tangan]", "[applause]",
        "[silence]", "[hening]", "[tertawa]", "[laughter]",
        "[sound effect]", "[sfx]", "[no speech]",
        "♪", "♫", "🎵", "🎶",
    ]
    # Minimum ratio of actual words vs total text to consider as speech
    MIN_SPEECH_RATIO = 0.3

    def __init__(self):
        self._groq_client = None
        self._model_pass1 = settings.GROQ_LLM_MODEL  # 8b — fast scanning
        self._model_pass2 = settings.GROQ_LLM_FALLBACK_MODEL  # 70b — quality ranking
        self._max_retries = settings.GROQ_MAX_RETRIES
        self._timeout = settings.GROQ_TIMEOUT
        self._chunk_max_seconds = settings.V2_CHUNK_MAX_SECONDS
        self._chunk_max_chars = settings.V2_CHUNK_MAX_CHARS

    def _get_groq_client(self):
        """Lazy-init Groq client."""
        if self._groq_client is None:
            from groq import Groq
            if not settings.GROQ_API_KEY:
                raise GroqAnalyzerError("GROQ_API_KEY not configured")
            self._groq_client = Groq(api_key=settings.GROQ_API_KEY)
        return self._groq_client

    # ─── Main Entry Point ─────────────────────────────────────────────────────

    async def analyze_highlights(
        self, transcript: TranscriptResult, video_duration: float, max_clips: int
    ) -> HighlightAnalysisResult:
        """Two-Pass highlight analysis with concurrency control.

        Pass 1: Chunk → 8b scanning → raw candidates (with Segment IDs)
        Pass 2: All candidates → 70b re-ranking → final selection + hooks

        Uses asyncio.Semaphore to limit concurrent analyses (prevents rate limit
        exhaustion when multiple users upload videos simultaneously).
        """
        async with self._analysis_semaphore:
            return await self._analyze_highlights_impl(
                transcript, video_duration, max_clips
            )

    async def _analyze_highlights_impl(
        self, transcript: TranscriptResult, video_duration: float, max_clips: int
    ) -> HighlightAnalysisResult:
        """Internal implementation (called within semaphore context)."""
        t_start = time.perf_counter()
        metrics = AnalysisMetrics(
            video_duration=video_duration,
            total_segments=len(transcript.segments),
        )
        loop = asyncio.get_running_loop()

        # Build segment map for ID → timestamp resolution
        segment_map = {}
        for i, seg in enumerate(transcript.segments):
            seg_id = f"S{i:04d}"
            segment_map[seg_id] = {"start": seg.start, "end": seg.end, "text": seg.text}

        # ─── Pass 1: Per-chunk scanning (8b) with Segment IDs ─────────
        chunks = self._chunk_transcript_with_ids(transcript.segments)
        metrics.chunks_processed = len(chunks)
        logger.info(
            f"v2_analyzer: Pass 1 — {len(chunks)} chunks, {len(transcript.segments)} segments, "
            f"{video_duration:.0f}s video (target={max_clips} clips)"
        )

        t_pass1_start = time.perf_counter()
        all_candidates = []
        for i, (chunk_segments, chunk_text_with_ids) in enumerate(chunks):
            chunk_start = chunk_segments[0].start
            chunk_end = chunk_segments[-1].end

            logger.info(f"v2_analyzer: Pass 1 chunk {i+1}/{len(chunks)} [{chunk_start:.0f}s-{chunk_end:.0f}s]")

            try:
                candidates = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        partial(
                            self._pass1_analyze_chunk,
                            chunk_text_with_ids, chunk_start, chunk_end,
                            video_duration, max_clips, i + 1, len(chunks),
                            segment_map,
                        ),
                    ),
                    timeout=self._timeout,
                )
                all_candidates.extend(candidates)
                metrics.pass1_candidates_per_chunk.append(len(candidates))
                logger.info(f"v2_analyzer: Pass 1 chunk {i+1} → {len(candidates)} candidates")
            except asyncio.TimeoutError:
                logger.warning(f"v2_analyzer: Pass 1 chunk {i+1} timed out")
                metrics.pass1_chunks_failed += 1
                metrics.pass1_candidates_per_chunk.append(0)
            except Exception as e:
                logger.warning(f"v2_analyzer: Pass 1 chunk {i+1} failed: {e}")
                metrics.pass1_chunks_failed += 1
                metrics.pass1_candidates_per_chunk.append(0)

            # Rate limit delay between chunks
            if i < len(chunks) - 1:
                delay = 20
                logger.info(f"v2_analyzer: rate limit delay {delay}s")
                await asyncio.sleep(delay)

        metrics.pass1_time_seconds = time.perf_counter() - t_pass1_start
        metrics.pass1_candidates_total = len(all_candidates)

        if not all_candidates:
            self._log_metrics(metrics)
            raise GroqAnalyzerError("Pass 1 menghasilkan 0 kandidat dari semua chunks")

        logger.info(f"v2_analyzer: Pass 1 complete — {len(all_candidates)} total candidates")

        # ─── Pass 2: Global re-ranking (70b) ─────────────────────────
        logger.info("v2_analyzer: waiting 20s before Pass 2 (rate limit)")
        await asyncio.sleep(20)

        t_pass2_start = time.perf_counter()
        metrics.pass2_model_used = self._model_pass2
        try:
            ranked_clips = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    partial(self._pass2_global_rerank, all_candidates, max_clips, video_duration),
                ),
                timeout=self._timeout,
            )
            logger.info(f"v2_analyzer: Pass 2 complete — {len(ranked_clips)} final clips (from {len(all_candidates)} candidates)")
        except Exception as e:
            logger.warning(f"v2_analyzer: Pass 2 failed ({e}), using Pass 1 ranking")
            metrics.pass2_fallback_triggered = True
            ranked_clips = self._fallback_rank(all_candidates, max_clips, video_duration)

        metrics.pass2_time_seconds = time.perf_counter() - t_pass2_start

        if not ranked_clips:
            self._log_metrics(metrics)
            raise GroqAnalyzerError("Tidak ada clip yang valid setelah ranking")

        # ─── Validate Final Clips (Safety Net) ───────────────────────
        pre_validation_count = len(ranked_clips)
        ranked_clips = self._validate_final_clips(ranked_clips, video_duration)
        metrics.validation_passed = len(ranked_clips)
        metrics.validation_rejected = pre_validation_count - len(ranked_clips)
        if not ranked_clips:
            self._log_metrics(metrics)
            raise GroqAnalyzerError("Semua clip gagal validasi akhir")

        # ─── Creative Direction (separate call) ───────────────────────
        logger.info("v2_analyzer: waiting 20s before creative direction (rate limit)")
        await asyncio.sleep(20)
        t_creative_start = time.perf_counter()
        try:
            creative_result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    partial(self._generate_creative_direction, ranked_clips, video_duration),
                ),
                timeout=self._timeout,
            )
        except Exception as e:
            logger.warning(f"v2_analyzer: creative direction failed: {e}")
            creative_result = {"creative_direction": {}, "broll_suggestions": {}}
        metrics.creative_direction_time_seconds = time.perf_counter() - t_creative_start

        # ─── Finalize Metrics ─────────────────────────────────────────
        metrics.final_clips_count = len(ranked_clips)
        metrics.total_time_seconds = time.perf_counter() - t_start
        self._log_metrics(metrics)

        return HighlightAnalysisResult(
            clips=ranked_clips,
            creative_direction=creative_result.get("creative_direction", {}),
            broll_suggestions=creative_result.get("broll_suggestions", {}),
            model_used=f"{self._model_pass1}+{self._model_pass2}",
            chunks_processed=len(chunks),
        )

    # ─── Chunking with Segment IDs ────────────────────────────────────────────

    def _chunk_transcript_with_ids(
        self, segments: list[TranscriptSegment]
    ) -> list[tuple[list[TranscriptSegment], str]]:
        """Split transcript into chunks with overlap, each with Segment ID formatted text.

        Applies CHUNK_OVERLAP_SECONDS overlap between consecutive chunks to ensure
        clip boundaries that span chunk edges are still detected.

        Returns list of (segments, formatted_text_with_ids).
        """
        if not segments:
            return []

        chunks = []
        current_segments: list[TranscriptSegment] = []
        current_duration = 0.0
        current_chars = 0
        chunk_start_idx = 0  # Track where this chunk starts in global index
        global_idx = 0

        for seg in segments:
            seg_duration = seg.end - seg.start
            seg_chars = len(seg.text)

            would_exceed_time = (current_duration + seg_duration) > self._chunk_max_seconds
            would_exceed_chars = (current_chars + seg_chars) > self._chunk_max_chars

            if (would_exceed_time or would_exceed_chars) and current_segments:
                # Flush chunk
                text = self._format_segments_with_ids(current_segments, chunk_start_idx)
                chunks.append((list(current_segments), text))

                # Apply overlap: rewind by CHUNK_OVERLAP_SECONDS
                # Find how many trailing segments fit within the overlap window
                overlap_segments = []
                overlap_duration = 0.0
                for s in reversed(current_segments):
                    s_dur = s.end - s.start
                    if overlap_duration + s_dur > self.CHUNK_OVERLAP_SECONDS:
                        break
                    overlap_segments.insert(0, s)
                    overlap_duration += s_dur

                # Start new chunk from overlap segments
                chunk_start_idx = global_idx - len(overlap_segments)
                current_segments = list(overlap_segments)
                current_duration = overlap_duration
                current_chars = sum(len(s.text) for s in overlap_segments)

            current_segments.append(seg)
            current_duration += seg_duration
            current_chars += seg_chars
            global_idx += 1

        # Last chunk
        if current_segments:
            text = self._format_segments_with_ids(current_segments, chunk_start_idx)
            chunks.append((current_segments, text))

        return chunks

    def _format_segments_with_ids(self, segments: list[TranscriptSegment], start_idx: int) -> str:
        """Format segments with Segment IDs: [S0015 | 02:30] text"""
        lines = []
        for i, seg in enumerate(segments):
            seg_id = f"S{start_idx + i:04d}"
            mins, secs = divmod(int(seg.start), 60)
            lines.append(f"[{seg_id} | {mins:02d}:{secs:02d}] {seg.text.strip()}")
        return "\n".join(lines)

    # ─── Pass 1: Chunk Analysis (8b) ─────────────────────────────────────────

    def _pass1_analyze_chunk(
        self, chunk_text_with_ids: str, chunk_start: float, chunk_end: float,
        video_duration: float, max_clips: int, chunk_num: int, total_chunks: int,
        segment_map: dict,
    ) -> list[HighlightCandidate]:
        """Pass 1: Fast scanning with 8b model. Uses Segment IDs for precision."""
        clips_per_chunk = max(4, (max_clips // max(1, total_chunks)) + 3)

        prompt = f"""Kamu adalah AI pendeteksi momen viral. Scan transkrip berikut dan temukan momen paling menarik.

KONTEKS:
- Video total: {video_duration:.0f} detik
- Bagian ini: [{chunk_start:.0f}s - {chunk_end:.0f}s] (chunk {chunk_num}/{total_chunks})
- Target: Temukan {clips_per_chunk} kandidat clip (durasi MINIMUM 45 detik, idealnya 60-90 detik, BOLEH lebih panjang jika cerita belum selesai)

TRANSKRIP (format: [SegmentID | MM:SS] teks):
{chunk_text_with_ids}

ATURAN:
1. Gunakan SEGMENT ID yang ada di transkrip (contoh: S0015)
2. "start_id" = Segment ID di mana clip MULAI
3. "end_id" = Segment ID di mana clip BERAKHIR
4. Durasi clip MINIMUM 45 detik. Jangan potong di tengah cerita/argumen — pastikan clip berakhir di kalimat penutup yang natural. Boleh lebih dari 90 detik jika topik belum tuntas.
5. Score 1-100 berdasarkan potensi viral
6. "summary" = ringkasan 1 kalimat apa yang terjadi di clip ini

KRITERIA VIRAL:
- Emosi tinggi (marah, terkejut, bahagia)
- Cerita menarik yang bisa berdiri sendiri
- Plot twist atau pengakuan mengejutkan
- Humor atau momen lucu
- Kontroversi atau pendapat kuat

OUTPUT FORMAT — RAW JSON (tanpa markdown):
{{"clips": [{{"start_id": "S0001", "end_id": "S0010", "score": 85, "summary": "ringkasan singkat", "content_type": "storytelling", "speaker_energy": "high"}}]}}"""

        raw = self._call_groq_llm(prompt, model=self._model_pass1, max_tokens=1500)
        return self._parse_pass1_response(raw, segment_map, chunk_start, chunk_end)

    def _parse_pass1_response(
        self, raw_text: str, segment_map: dict, chunk_start: float, chunk_end: float
    ) -> list[HighlightCandidate]:
        """Parse Pass 1 response: resolve Segment IDs → timestamps."""
        data = self._parse_json_response(raw_text)
        if not data or "clips" not in data:
            return []

        candidates = []
        for clip in data.get("clips", []):
            try:
                # Normalize Segment IDs: uppercase, strip whitespace
                start_id = str(clip.get("start_id", "")).strip().upper()
                end_id = str(clip.get("end_id", "")).strip().upper()
                score = int(clip.get("score", 50))

                # Resolve Segment IDs to actual timestamps
                if start_id in segment_map and end_id in segment_map:
                    start = segment_map[start_id]["start"]
                    end = segment_map[end_id]["end"]

                    # ─── Whisper Hallucination Guard ───────────────────
                    # Check if the clip's segments are mostly non-speech
                    if self._is_non_speech_clip(start_id, end_id, segment_map):
                        logger.debug(
                            f"v2_analyzer: skip non-speech clip {start:.0f}-{end:.0f} "
                            f"(detected music/silence/applause)"
                        )
                        continue

                elif "start" in clip and "end" in clip:
                    # Fallback: use raw timestamps if IDs not found
                    start = float(clip["start"])
                    end = float(clip["end"])
                    logger.debug(
                        f"v2_analyzer: Segment IDs not found ({start_id}, {end_id}), "
                        f"using raw timestamps {start:.1f}-{end:.1f}"
                    )
                else:
                    logger.debug(f"v2_analyzer: skipping clip, no valid IDs or timestamps")
                    continue

                # Validate duration using class constants
                duration = end - start
                if duration < self.MIN_CLIP_DURATION or duration > self.MAX_CLIP_DURATION:
                    logger.debug(
                        f"v2_analyzer: skip clip {start:.0f}-{end:.0f} "
                        f"(duration {duration:.0f}s outside {self.MIN_CLIP_DURATION}-{self.MAX_CLIP_DURATION}s)"
                    )
                    continue

                # Clamp score
                score = max(1, min(100, score))

                candidates.append(HighlightCandidate(
                    rank=0,
                    start=round(start, 2),
                    end=round(end, 2),
                    score=score,
                    hook="",  # Hook will be generated in Pass 2
                    reason=str(clip.get("summary", clip.get("reason", ""))),
                    content_type=str(clip.get("content_type", "storytelling")),
                    speaker_energy=str(clip.get("speaker_energy", "medium")),
                ))
            except (ValueError, TypeError, KeyError) as e:
                logger.debug(f"v2_analyzer: Pass 1 skip invalid clip: {e}")
                continue

        return candidates

    # ─── Pass 2: Global Re-ranking (70b) ──────────────────────────────────────

    def _pass2_global_rerank(
        self, candidates: list[HighlightCandidate], max_clips: int, video_duration: float
    ) -> list[HighlightCandidate]:
        """Pass 2: Global re-ranking with 70b. Picks TOP N and generates hooks."""
        # Deduplicate and sort by score first
        deduped = self._deduplicate_candidates(candidates)

        # Build candidates summary for 70b
        candidates_text = "\n".join([
            f"  [{i+1}] {c.start:.0f}s-{c.end:.0f}s (score={c.score}): {c.reason}"
            for i, c in enumerate(deduped[:20])  # Max 20 candidates for context
        ])

        prompt = f"""Kamu adalah editor senior konten viral TikTok/Reels Indonesia.

Dari {len(deduped)} kandidat clip di bawah ini (video total {video_duration:.0f} detik), 
PILIH {max_clips} clip TERBAIK dan buat hook text yang viral.

KANDIDAT (format: [nomor] waktu (score): deskripsi):
{candidates_text}

TUGAS:
1. Pilih TEPAT {max_clips} clip terbaik berdasarkan potensi viral global
2. Beri score final 1-100 (re-evaluate secara keseluruhan)
3. Buat HOOK untuk masing-masing clip

ATURAN SELEKSI:
1. Pilih clip dengan score tertinggi DAN diversity konten terbaik
2. Hindari clip yang terlalu mirip (topic/scene sama)
3. Prioritaskan clip yang bisa berdiri sendiri (self-contained)
4. SPREAD CLIP: Pastikan clip terpilih berasal dari bagian video yang BERBEDA-BEDA (awal, tengah, akhir). Jangan mengambil semua clip dari 1 chunk yang sama.
5. Jika 2 clip bagus tapi terlalu berdekatan (< 60 detik gap), pilih yang score lebih tinggi

ATURAN HOOK:
- Hook HARUS 3-8 kata
- Hook membuat penasaran, BUKAN spoiler
- Bahasa sama dengan konten (Indonesia)
- Contoh bagus: "Ini gila sih ternyata...", "Jangan lakuin ini di Bali"
- Contoh JELEK: "Tips editing video", salinan transcript

OUTPUT FORMAT — RAW JSON (tanpa markdown):
{{"clips": [{{"candidate_idx": 1, "score": 95, "hook": "Hook 3-8 kata"}}]}}"""

        raw = self._call_groq_llm(prompt, model=self._model_pass2, max_tokens=2000)
        return self._parse_pass2_response(raw, deduped, max_clips, video_duration)

    def _parse_pass2_response(
        self, raw_text: str, candidates: list[HighlightCandidate],
        max_clips: int, video_duration: float
    ) -> list[HighlightCandidate]:
        """Parse Pass 2 response: apply 70b selections to candidates."""
        data = self._parse_json_response(raw_text)
        if not data or "clips" not in data:
            # Fallback to simple ranking if 70b fails to parse
            return self._fallback_rank(candidates, max_clips, video_duration)

        selected = []
        for clip_data in data.get("clips", []):
            try:
                idx = int(clip_data.get("candidate_idx", 0)) - 1  # 1-indexed → 0-indexed
                if idx < 0 or idx >= len(candidates):
                    logger.warning(
                        f"v2_analyzer: Pass 2 returned out-of-range candidate_idx={idx+1} "
                        f"(valid range: 1-{len(candidates)}), skipping"
                    )
                    continue
                candidate = candidates[idx]
                candidate.score = int(clip_data.get("score", candidate.score))
                candidate.hook = str(clip_data.get("hook", ""))[:60]
                selected.append(candidate)
            except (ValueError, TypeError) as e:
                logger.debug(f"v2_analyzer: Pass 2 skip invalid entry: {e}")
                continue

        if not selected:
            logger.warning("v2_analyzer: Pass 2 produced 0 valid selections, using fallback")
            return self._fallback_rank(candidates, max_clips, video_duration)

        # Sort by start time and assign ranks
        selected = selected[:max_clips]
        selected.sort(key=lambda c: c.start)
        for i, clip in enumerate(selected):
            clip.rank = i + 1

        return selected

    def _deduplicate_candidates(self, candidates: list[HighlightCandidate]) -> list[HighlightCandidate]:
        """Remove overlapping candidates, keep higher score."""
        sorted_clips = sorted(candidates, key=lambda c: c.score, reverse=True)
        deduped = []
        for clip in sorted_clips:
            if not self._overlaps_with_any(clip, deduped):
                deduped.append(clip)
        return deduped

    def _fallback_rank(
        self, candidates: list[HighlightCandidate], max_clips: int, video_duration: float
    ) -> list[HighlightCandidate]:
        """Simple score-based ranking fallback when Pass 2 fails."""
        deduped = self._deduplicate_candidates(candidates)
        selected = deduped[:max_clips]
        selected.sort(key=lambda c: c.start)
        for i, clip in enumerate(selected):
            clip.rank = i + 1
            if not clip.hook:
                clip.hook = clip.reason[:60] if clip.reason else f"Momen viral #{i+1}"
        return selected

    # ─── Validation Safety Net ────────────────────────────────────────────────

    def _validate_final_clips(
        self, clips: list[HighlightCandidate], video_duration: float
    ) -> list[HighlightCandidate]:
        """Final safety net: validate all clips before returning to caller.

        Checks:
        - start < end
        - duration within MIN/MAX bounds
        - timestamps within video bounds (0 to video_duration)
        - score within 1-100
        - hook is non-empty string
        """
        validated = []
        for clip in clips:
            # Basic sanity checks
            if clip.start >= clip.end:
                logger.warning(f"v2_analyzer: validate reject clip (start >= end): {clip.start}-{clip.end}")
                continue

            duration = clip.end - clip.start
            if duration < self.MIN_CLIP_DURATION or duration > self.MAX_CLIP_DURATION:
                logger.warning(
                    f"v2_analyzer: validate reject clip (duration {duration:.0f}s): "
                    f"{clip.start:.0f}-{clip.end:.0f}"
                )
                continue

            # Timestamps within video bounds (with 1s tolerance)
            if clip.start < -1.0 or clip.end > video_duration + 1.0:
                logger.warning(
                    f"v2_analyzer: validate reject clip (out of video bounds): "
                    f"{clip.start:.0f}-{clip.end:.0f} (video={video_duration:.0f}s)"
                )
                continue

            # Clamp to video bounds
            clip.start = max(0.0, clip.start)
            clip.end = min(video_duration, clip.end)

            # Ensure score is valid
            clip.score = max(1, min(100, clip.score))

            # Ensure hook exists
            if not clip.hook or not clip.hook.strip():
                clip.hook = clip.reason[:60] if clip.reason else f"Momen viral #{len(validated)+1}"

            validated.append(clip)

        # Re-assign ranks
        for i, clip in enumerate(validated):
            clip.rank = i + 1

        if len(validated) < len(clips):
            logger.info(
                f"v2_analyzer: validation passed {len(validated)}/{len(clips)} clips"
            )

        return validated

    # ─── Creative Direction (unchanged) ───────────────────────────────────────

    def _generate_creative_direction(
        self, clips: list[HighlightCandidate], video_duration: float
    ) -> dict:
        """Generate creative direction + B-Roll suggestions for selected clips."""
        clips_context = "\n".join([
            f"  Clip {c.rank}: [{c.start:.0f}s → {c.end:.0f}s] "
            f"score={c.score}, type={c.content_type}, energy={c.speaker_energy}\n"
            f"    Hook: \"{c.hook}\"\n    Alasan: {c.reason}"
            for c in clips
        ])

        prompt = f"""Kamu adalah visual director dan copywriter viral. Berdasarkan clip yang terpilih, tentukan:

═══ CLIP TERPILIH ═══
{clips_context}

═══ TUGAS 1: CREATIVE DIRECTION ═══
Tentukan visual identity yang konsisten untuk SEMUA clips:
- primary_color: warna utama aksen (hex, cocok dengan mood)
- secondary_color: warna highlight/emphasis (hex)
- background_accent: warna tint overlay (hex gelap)
- typography_mood: "bold_impact" / "elegant_minimal" / "playful" / "dramatic"
- energy_level: "high" / "medium" / "chill"
- transition_style: "fast_cuts" / "smooth" / "kinetic"
- music_mood: "energetic" / "chill" / "dramatic" / "suspense"
- hook_animation: "fade_scale" / "slide_up" / "glitch" / "typewriter"

═══ TUGAS 2: B-ROLL SUGGESTIONS ═══
Untuk SETIAP clip, tentukan 1-2 momen B-Roll:
- "at_time": offset DALAM clip (detik dari awal clip)
- "keyword": kata kunci yang ditampilkan (MAKS 20 karakter, UPPERCASE)
- "template": "word_pop_typography" / "line_reveal_typography" / "particle_text_burst"
- "duration": 1.5 - 3.0 detik
- "visual_category": "footage" / "icon" / "motion_graphic" / "reaction"

OUTPUT FORMAT — RAW JSON (tanpa markdown):
{{"creative_direction": {{"primary_color": "<hex>", "secondary_color": "<hex>", "background_accent": "<hex>", "typography_mood": "<mood>", "energy_level": "<level>", "transition_style": "<style>", "music_mood": "<mood>", "hook_animation": "<anim>"}}, "broll_suggestions": {{"1": [{{"at_time": <float>, "keyword": "<UPPERCASE>", "template": "<template>", "duration": <float>, "visual_category": "<category>"}}]}}}}"""

        raw = self._call_groq_llm(prompt, model=self._model_pass1)
        return self._parse_json_response(raw)

    # ─── Groq LLM API Call ────────────────────────────────────────────────────

    def _call_groq_llm(
        self, prompt: str, model: Optional[str] = None, max_tokens: int = 3000
    ) -> str:
        """Call Groq LLM with exponential backoff retry logic.

        Args:
            prompt: The prompt to send
            model: Model to use (defaults to pass1 model)
            max_tokens: Max tokens for response (varies by use case)
        """
        client = self._get_groq_client()
        use_model = model or self._model_pass1
        total_attempts = max(self._max_retries, 5)

        for attempt in range(total_attempts):
            try:
                response = client.chat.completions.create(
                    model=use_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )

                if response and response.choices:
                    content = response.choices[0].message.content
                    if content:
                        return content

                raise ValueError("Groq response empty")

            except Exception as e:
                error_str = str(e).lower()

                if "429" in error_str or "rate" in error_str:
                    # Exponential backoff: 30s, 60s, 120s, 240s (capped)
                    wait = min(30 * (2 ** attempt), 240)
                    logger.warning(
                        f"v2_analyzer: rate limited, waiting {wait}s "
                        f"(attempt {attempt+1}/{total_attempts}, model={use_model})"
                    )
                    time.sleep(wait)
                    continue

                if "503" in error_str or "overloaded" in error_str:
                    # Auto-fallback: 70b → 8b when overloaded
                    if use_model == self._model_pass2:
                        logger.warning(
                            f"v2_analyzer: {self._model_pass2} overloaded, "
                            f"falling back to {self._model_pass1}"
                        )
                        use_model = self._model_pass1
                        time.sleep(5)
                        continue

                if attempt >= total_attempts - 1:
                    raise GroqAnalyzerError(
                        f"Groq LLM failed after {total_attempts} attempts: {e}"
                    )

                # General error: exponential backoff 5s, 10s, 20s...
                wait = min(5 * (2 ** attempt), 60)
                logger.warning(f"v2_analyzer: attempt {attempt+1} failed: {e}, retry in {wait}s")
                time.sleep(wait)

        raise GroqAnalyzerError("Groq LLM max retries exceeded")

    # ─── JSON Parsing ─────────────────────────────────────────────────────────

    def _clean_json_string(self, json_str: str) -> str:
        """Clean common LLM JSON issues: trailing commas, comments."""
        # Remove trailing commas before } or ]
        # e.g. {"a": 1,} → {"a": 1}
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
        # Remove single-line comments (// ...)
        json_str = re.sub(r'//[^\n]*', '', json_str)
        return json_str

    def _parse_json_response(self, raw_text: str) -> dict:
        """Parse JSON with tolerance for markdown fences and trailing commas."""
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        # First attempt: direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Second attempt: extract outermost { ... } and clean
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            json_str = self._clean_json_string(match.group(0))
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"v2_analyzer: JSON parse failed after cleanup: {e}\nRaw: {json_str[:200]}")

        logger.warning(f"v2_analyzer: failed to parse JSON: {text[:200]}")
        return {}

    # ─── Utility ──────────────────────────────────────────────────────────────

    def _overlaps_with_any(
        self, clip: HighlightCandidate, selected: list[HighlightCandidate]
    ) -> bool:
        """Check if clip overlaps 50%+ with any selected clip.

        Uses OVERLAP_THRESHOLD (0.5) — clips that share less than 50% overlap
        are allowed, enabling adjacent but distinct moments to coexist.
        """
        for existing in selected:
            overlap_start = max(clip.start, existing.start)
            overlap_end = min(clip.end, existing.end)
            overlap_duration = max(0.0, overlap_end - overlap_start)

            if overlap_duration <= 0:
                continue

            # Calculate overlap ratio relative to the shorter clip
            clip_duration = clip.end - clip.start
            existing_duration = existing.end - existing.start
            shorter_duration = min(clip_duration, existing_duration)

            if shorter_duration > 0:
                overlap_ratio = overlap_duration / shorter_duration
                if overlap_ratio >= self.OVERLAP_THRESHOLD:
                    return True

        return False

    # ─── Whisper Hallucination Guard ──────────────────────────────────────────

    def _is_non_speech_clip(
        self, start_id: str, end_id: str, segment_map: dict
    ) -> bool:
        """Check if a clip's segments are mostly non-speech content.

        Examines all segments between start_id and end_id. If the ratio of
        segments containing non-speech patterns exceeds (1 - MIN_SPEECH_RATIO),
        the clip is considered non-speech (music, silence, etc.).
        """
        # Extract numeric indices from segment IDs
        try:
            start_idx = int(start_id[1:])  # "S0015" → 15
            end_idx = int(end_id[1:])      # "S0025" → 25
        except (ValueError, IndexError):
            return False

        if start_idx > end_idx:
            return False

        total_segments = 0
        non_speech_segments = 0

        for idx in range(start_idx, end_idx + 1):
            seg_id = f"S{idx:04d}"
            if seg_id not in segment_map:
                continue

            total_segments += 1
            seg_text = segment_map[seg_id]["text"].lower().strip()

            # Check against non-speech patterns
            is_non_speech = any(
                pattern in seg_text for pattern in self.NON_SPEECH_PATTERNS
            )

            # Also check if segment is very short text (likely filler)
            # e.g., "...", single word repeated
            if not is_non_speech and len(seg_text) < 5:
                is_non_speech = True

            if is_non_speech:
                non_speech_segments += 1

        if total_segments == 0:
            return False

        speech_ratio = 1.0 - (non_speech_segments / total_segments)
        return speech_ratio < self.MIN_SPEECH_RATIO

    # ─── Metrics Logging ──────────────────────────────────────────────────────

    def _log_metrics(self, metrics: "AnalysisMetrics") -> None:
        """Log structured metrics for monitoring and alerting.

        Outputs a single structured log line that can be parsed by
        log aggregators (Grafana Loki, CloudWatch, Datadog, etc.).
        """
        # Determine health status
        health = "healthy"
        alerts = []

        if metrics.pass1_candidates_total < 3:
            health = "degraded"
            alerts.append("low_candidates")

        if metrics.pass2_fallback_triggered:
            health = "degraded"
            alerts.append("pass2_fallback")

        if metrics.pass1_chunks_failed > 0:
            alerts.append(f"chunks_failed={metrics.pass1_chunks_failed}")

        if metrics.validation_rejected > 0:
            alerts.append(f"validation_rejected={metrics.validation_rejected}")

        avg_candidates_per_chunk = (
            metrics.pass1_candidates_total / max(1, metrics.chunks_processed)
        )

        # Structured log (single line, parseable)
        logger.info(
            f"v2_analyzer_metrics: "
            f"health={health} "
            f"video_duration={metrics.video_duration:.0f}s "
            f"total_segments={metrics.total_segments} "
            f"chunks={metrics.chunks_processed} "
            f"pass1_candidates={metrics.pass1_candidates_total} "
            f"pass1_avg_per_chunk={avg_candidates_per_chunk:.1f} "
            f"pass1_per_chunk={metrics.pass1_candidates_per_chunk} "
            f"pass1_failed={metrics.pass1_chunks_failed} "
            f"pass1_time={metrics.pass1_time_seconds:.1f}s "
            f"pass2_model={metrics.pass2_model_used} "
            f"pass2_fallback={metrics.pass2_fallback_triggered} "
            f"pass2_time={metrics.pass2_time_seconds:.1f}s "
            f"validated={metrics.validation_passed}/{metrics.validation_passed + metrics.validation_rejected} "
            f"creative_time={metrics.creative_direction_time_seconds:.1f}s "
            f"final_clips={metrics.final_clips_count} "
            f"total_time={metrics.total_time_seconds:.1f}s "
            f"alerts={alerts if alerts else 'none'}"
        )

        # Alert-level log for degraded health
        if health == "degraded":
            logger.warning(
                f"v2_analyzer_alert: DEGRADED — {', '.join(alerts)} "
                f"(video={metrics.video_duration:.0f}s, "
                f"candidates={metrics.pass1_candidates_total}, "
                f"final={metrics.final_clips_count})"
            )
