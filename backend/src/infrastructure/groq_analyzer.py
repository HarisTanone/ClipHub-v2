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
import time
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


class GroqAnalyzerError(Exception):
    """Raised when highlight analysis fails after all retries."""
    pass


class GroqAnalyzer(IGroqAnalyzer):
    """TAHAP 2: Two-Pass highlight analysis with Segment ID anchoring."""

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
        """Two-Pass highlight analysis.

        Pass 1: Chunk → 8b scanning → raw candidates (with Segment IDs)
        Pass 2: All candidates → 70b re-ranking → final selection + hooks
        """
        loop = asyncio.get_event_loop()

        # Build segment map for ID → timestamp resolution
        segment_map = {}
        for i, seg in enumerate(transcript.segments):
            seg_id = f"S{i:04d}"
            segment_map[seg_id] = {"start": seg.start, "end": seg.end, "text": seg.text}

        # ─── Pass 1: Per-chunk scanning (8b) with Segment IDs ─────────
        chunks = self._chunk_transcript_with_ids(transcript.segments)
        logger.info(
            f"v2_analyzer: Pass 1 — {len(chunks)} chunks, {len(transcript.segments)} segments, "
            f"{video_duration:.0f}s video (target={max_clips} clips)"
        )

        all_candidates = []
        for i, (chunk_segments, chunk_text_with_ids) in enumerate(chunks):
            chunk_start = chunk_segments[0].start
            chunk_end = chunk_segments[-1].end

            logger.info(f"v2_analyzer: Pass 1 chunk {i+1}/{len(chunks)} [{chunk_start:.0f}s-{chunk_end:.0f}s]")

            try:
                candidates = await asyncio.wait_for(
                    loop.run_in_executor(
                        None, self._pass1_analyze_chunk,
                        chunk_text_with_ids, chunk_start, chunk_end,
                        video_duration, max_clips, i + 1, len(chunks),
                        segment_map,
                    ),
                    timeout=self._timeout,
                )
                all_candidates.extend(candidates)
                logger.info(f"v2_analyzer: Pass 1 chunk {i+1} → {len(candidates)} candidates")
            except asyncio.TimeoutError:
                logger.warning(f"v2_analyzer: Pass 1 chunk {i+1} timed out")
            except Exception as e:
                logger.warning(f"v2_analyzer: Pass 1 chunk {i+1} failed: {e}")

            # Rate limit delay between chunks
            if i < len(chunks) - 1:
                delay = 20
                logger.info(f"v2_analyzer: rate limit delay {delay}s")
                await asyncio.sleep(delay)

        if not all_candidates:
            raise GroqAnalyzerError("Pass 1 menghasilkan 0 kandidat dari semua chunks")

        logger.info(f"v2_analyzer: Pass 1 complete — {len(all_candidates)} total candidates")

        # ─── Pass 2: Global re-ranking (70b) ─────────────────────────
        logger.info("v2_analyzer: waiting 20s before Pass 2 (rate limit)")
        await asyncio.sleep(20)

        try:
            ranked_clips = await asyncio.wait_for(
                loop.run_in_executor(
                    None, self._pass2_global_rerank,
                    all_candidates, max_clips, video_duration,
                ),
                timeout=self._timeout,
            )
            logger.info(f"v2_analyzer: Pass 2 complete — {len(ranked_clips)} final clips (from {len(all_candidates)} candidates)")
        except Exception as e:
            logger.warning(f"v2_analyzer: Pass 2 failed ({e}), using Pass 1 ranking")
            ranked_clips = self._fallback_rank(all_candidates, max_clips, video_duration)

        if not ranked_clips:
            raise GroqAnalyzerError("Tidak ada clip yang valid setelah ranking")

        # ─── Creative Direction (separate call) ───────────────────────
        logger.info("v2_analyzer: waiting 20s before creative direction (rate limit)")
        await asyncio.sleep(20)
        try:
            creative_result = await asyncio.wait_for(
                loop.run_in_executor(
                    None, self._generate_creative_direction, ranked_clips, video_duration
                ),
                timeout=self._timeout,
            )
        except Exception as e:
            logger.warning(f"v2_analyzer: creative direction failed: {e}")
            creative_result = {"creative_direction": {}, "broll_suggestions": {}}

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
        """Split transcript into chunks, each with Segment ID formatted text.

        Returns list of (segments, formatted_text_with_ids).
        """
        if not segments:
            return []

        chunks = []
        current_segments: list[TranscriptSegment] = []
        current_duration = 0.0
        current_chars = 0
        global_idx = 0  # Track global segment index for IDs

        for seg in segments:
            seg_duration = seg.end - seg.start
            seg_chars = len(seg.text)

            would_exceed_time = (current_duration + seg_duration) > self._chunk_max_seconds
            would_exceed_chars = (current_chars + seg_chars) > self._chunk_max_chars

            if (would_exceed_time or would_exceed_chars) and current_segments:
                # Flush chunk
                text = self._format_segments_with_ids(current_segments, global_idx - len(current_segments))
                chunks.append((current_segments, text))
                current_segments = []
                current_duration = 0.0
                current_chars = 0

            current_segments.append(seg)
            current_duration += seg_duration
            current_chars += seg_chars
            global_idx += 1

        # Last chunk
        if current_segments:
            text = self._format_segments_with_ids(current_segments, global_idx - len(current_segments))
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
- Target: Temukan {clips_per_chunk} kandidat clip (durasi 30-90 detik per klip)

TRANSKRIP (format: [SegmentID | MM:SS] teks):
{chunk_text_with_ids}

ATURAN:
1. Gunakan SEGMENT ID yang ada di transkrip (contoh: S0015)
2. "start_id" = Segment ID di mana clip MULAI
3. "end_id" = Segment ID di mana clip BERAKHIR
4. Durasi clip harus 30-90 detik
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

        raw = self._call_groq_llm(prompt, model=self._model_pass1)
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
                start_id = str(clip.get("start_id", ""))
                end_id = str(clip.get("end_id", ""))
                score = int(clip.get("score", 50))

                # Resolve Segment IDs to actual timestamps
                if start_id in segment_map and end_id in segment_map:
                    start = segment_map[start_id]["start"]
                    end = segment_map[end_id]["end"]
                elif "start" in clip and "end" in clip:
                    # Fallback: use raw timestamps if IDs not found
                    start = float(clip["start"])
                    end = float(clip["end"])
                else:
                    continue

                # Validate duration
                duration = end - start
                if duration < 25 or duration > 120:
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

ATURAN HOOK:
- Hook HARUS 3-8 kata
- Hook membuat penasaran, BUKAN spoiler
- Bahasa sama dengan konten (Indonesia)
- Contoh bagus: "Ini gila sih ternyata...", "Jangan lakuin ini di Bali"
- Contoh JELEK: "Tips editing video", salinan transcript

OUTPUT FORMAT — RAW JSON (tanpa markdown):
{{"clips": [{{"candidate_idx": 1, "score": 95, "hook": "Hook 3-8 kata"}}]}}"""

        raw = self._call_groq_llm(prompt, model=self._model_pass2)
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
                if 0 <= idx < len(candidates):
                    candidate = candidates[idx]
                    candidate.score = int(clip_data.get("score", candidate.score))
                    candidate.hook = str(clip_data.get("hook", ""))[:60]
                    selected.append(candidate)
            except (ValueError, TypeError, IndexError):
                continue

        if not selected:
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

    def _call_groq_llm(self, prompt: str, model: Optional[str] = None) -> str:
        """Call Groq LLM with retry logic."""
        client = self._get_groq_client()
        use_model = model or self._model_pass1

        for attempt in range(max(self._max_retries, 5)):
            try:
                response = client.chat.completions.create(
                    model=use_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=3000,
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
                    wait = 60
                    logger.warning(f"v2_analyzer: rate limited, waiting {wait}s (attempt {attempt+1}, model={use_model})")
                    time.sleep(wait)
                    continue

                if "503" in error_str or "overloaded" in error_str:
                    # If 70b overloaded, fall back to 8b
                    if use_model == self._model_pass2:
                        logger.warning(f"v2_analyzer: 70b overloaded, falling back to 8b")
                        use_model = self._model_pass1
                        continue

                if attempt >= self._max_retries - 1:
                    raise GroqAnalyzerError(f"Groq LLM failed after {self._max_retries} attempts: {e}")

                logger.warning(f"v2_analyzer: attempt {attempt+1} failed: {e}")
                time.sleep(5)

        raise GroqAnalyzerError("Groq LLM max retries exceeded")

    # ─── JSON Parsing ─────────────────────────────────────────────────────────

    def _parse_json_response(self, raw_text: str) -> dict:
        """Parse JSON with tolerance for markdown fences."""
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start_idx = text.find("{")
            end_idx = text.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                try:
                    return json.loads(text[start_idx:end_idx])
                except json.JSONDecodeError:
                    pass
            logger.warning(f"v2_analyzer: failed to parse JSON: {text[:200]}")
            return {}

    # ─── Utility ──────────────────────────────────────────────────────────────

    def _overlaps_with_any(
        self, clip: HighlightCandidate, selected: list[HighlightCandidate]
    ) -> bool:
        """Check if clip overlaps with any selected clip."""
        for existing in selected:
            if clip.start < existing.end and clip.end > existing.start:
                return True
        return False
