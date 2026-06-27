"""GroqAnalyzer — TAHAP 2: AI Highlight Analysis via Groq LLM.

Uses Groq LLM (llama-3.1-8b-instant) to identify viral moments from transcript.
Dynamic chunking for long videos (max 600s or 4000 chars per chunk).

Architecture:
1. Chunk transcript based on time/char limits
2. Analyze each chunk → identify clip candidates
3. Merge + rank all candidates globally
4. Generate creative direction + B-Roll suggestions (single final call)
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
    """TAHAP 2 implementation: Dynamic chunking + Groq LLM highlight analysis."""

    def __init__(self):
        self._groq_client = None
        self._model = settings.GROQ_LLM_MODEL
        self._fallback_model = settings.GROQ_LLM_FALLBACK_MODEL
        self._max_retries = settings.GROQ_MAX_RETRIES
        self._timeout = settings.GROQ_TIMEOUT
        self._chunk_max_seconds = settings.V2_CHUNK_MAX_SECONDS
        self._chunk_max_chars = settings.V2_CHUNK_MAX_CHARS
        self._using_fallback = False

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
        """Analyze transcript → viral highlight candidates + creative direction.

        Phase A: Chunk transcript → analyze each chunk for candidates
        Phase B: Merge + rank → generate creative direction + B-Roll
        """
        loop = asyncio.get_event_loop()

        # ─── Phase A: Chunk Analysis ─────────────────────────────────
        chunks = self._chunk_transcript(transcript.segments)
        logger.info(
            f"v2_analyzer: {len(chunks)} chunks from {video_duration:.0f}s video "
            f"(max_clips={max_clips})"
        )

        all_candidates = []
        for i, chunk in enumerate(chunks):
            chunk_start = chunk[0].start
            chunk_end = chunk[-1].end
            chunk_text = " ".join(seg.text for seg in chunk)

            logger.debug(f"v2_analyzer: analyzing chunk {i+1}/{len(chunks)} [{chunk_start:.0f}s-{chunk_end:.0f}s]")

            try:
                candidates = await asyncio.wait_for(
                    loop.run_in_executor(
                        None, self._analyze_chunk, chunk_text, chunk_start, chunk_end,
                        video_duration, max_clips, i + 1, len(chunks)
                    ),
                    timeout=self._timeout,
                )
                all_candidates.extend(candidates)
            except asyncio.TimeoutError:
                logger.warning(f"v2_analyzer: chunk {i+1} timed out, skipping")
            except Exception as e:
                logger.warning(f"v2_analyzer: chunk {i+1} failed: {e}")

        if not all_candidates:
            raise GroqAnalyzerError("Groq LLM tidak menghasilkan clip candidates dari semua chunks")

        # ─── Phase B: Rank + Creative Direction ───────────────────────
        ranked_clips = self._rank_and_merge(all_candidates, max_clips, video_duration)
        logger.info(f"v2_analyzer: {len(ranked_clips)} clips selected from {len(all_candidates)} candidates")

        # Generate creative direction + B-Roll in single call
        try:
            creative_result = await asyncio.wait_for(
                loop.run_in_executor(
                    None, self._generate_creative_direction, ranked_clips, video_duration
                ),
                timeout=self._timeout,
            )
        except Exception as e:
            logger.warning(f"v2_analyzer: creative direction generation failed: {e}")
            creative_result = {"creative_direction": {}, "broll_suggestions": {}}

        return HighlightAnalysisResult(
            clips=ranked_clips,
            creative_direction=creative_result.get("creative_direction", {}),
            broll_suggestions=creative_result.get("broll_suggestions", {}),
            model_used=self._model if not self._using_fallback else self._fallback_model,
            chunks_processed=len(chunks),
        )

    # ─── Dynamic Chunking ─────────────────────────────────────────────────────

    def _chunk_transcript(
        self, segments: list[TranscriptSegment]
    ) -> list[list[TranscriptSegment]]:
        """Split transcript into chunks respecting time and char limits.

        Rules:
        - Max 600 seconds per chunk
        - Max 4000 characters per chunk
        - Whichever limit is hit first triggers a new chunk
        - Tries to split at sentence boundaries
        """
        if not segments:
            return []

        chunks = []
        current_chunk: list[TranscriptSegment] = []
        current_duration = 0.0
        current_chars = 0
        chunk_start_time = segments[0].start

        for seg in segments:
            seg_duration = seg.end - seg.start
            seg_chars = len(seg.text)

            # Check if adding this segment exceeds limits
            would_exceed_time = (current_duration + seg_duration) > self._chunk_max_seconds
            would_exceed_chars = (current_chars + seg_chars) > self._chunk_max_chars

            if (would_exceed_time or would_exceed_chars) and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_duration = 0.0
                current_chars = 0

            current_chunk.append(seg)
            current_duration += seg_duration
            current_chars += seg_chars

        # Don't forget the last chunk
        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    # ─── Chunk Analysis (Groq LLM Call) ───────────────────────────────────────

    def _analyze_chunk(
        self, chunk_text: str, chunk_start: float, chunk_end: float,
        video_duration: float, max_clips: int, chunk_num: int, total_chunks: int
    ) -> list[HighlightCandidate]:
        """Analyze a single transcript chunk → identify clip candidates."""
        clips_per_chunk = max(2, max_clips // max(1, total_chunks) + 1)

        prompt = self._build_chunk_analysis_prompt(
            chunk_text, chunk_start, chunk_end,
            video_duration, clips_per_chunk, chunk_num, total_chunks
        )

        raw_response = self._call_groq_llm(prompt)
        return self._parse_chunk_response(raw_response, chunk_start, chunk_end)

    def _build_chunk_analysis_prompt(
        self, text: str, start: float, end: float,
        video_duration: float, max_clips: int, chunk_num: int, total_chunks: int
    ) -> str:
        return f"""Kamu adalah AI analis konten viral profesional. Analisis transkrip berikut dan identifikasi momen paling menarik.

KONTEKS:
- Video total: {video_duration:.0f} detik
- Chunk ini: [{start:.1f}s - {end:.1f}s] (bagian {chunk_num} dari {total_chunks})
- Target: Temukan MAKSIMAL {max_clips} momen viral (durasi 45-90 detik per klip)

TRANSKRIP:
{text}

ATURAN PENTING:
1. Timestamp 'start' dan 'end' HARUS dalam rentang [{start:.1f}, {end:.1f}]
2. Durasi setiap klip: 45-90 detik
3. Klip TIDAK BOLEH OVERLAP
4. 'start' = awal kalimat (jangan potong tengah kata)
5. 'end' = setelah kalimat selesai
6. Skor 1-100 berdasarkan potensi viral
7. Hook = teks singkat <60 karakter, bahasa sama dengan transkrip, bikin penasaran

KRITERIA VIRAL:
- Kekuatan emosional tinggi
- Bisa berdiri sendiri (tanpa konteks tambahan)
- Memicu komentar/share
- Ada premis → konklusi
- Plot twist / surprise / kontroversi

OUTPUT FORMAT — RAW JSON (tanpa markdown, tanpa penjelasan):
{{"clips": [{{"rank": 1, "score": <int 1-100>, "start": <float>, "end": <float>, "hook": "<max 60 char>", "reason": "<alasan singkat>", "content_type": "<storytelling|tutorial|rant|debate|humor>", "speaker_energy": "<high|medium|low>"}}]}}"""

    # ─── Creative Direction Generation ────────────────────────────────────────

    def _generate_creative_direction(
        self, clips: list[HighlightCandidate], video_duration: float
    ) -> dict:
        """Generate creative direction + B-Roll suggestions for selected clips."""
        clips_context = "\n".join([
            f"  Clip {c.rank}: [{c.start:.1f}s → {c.end:.1f}s] "
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

TIPS B-ROLL:
- Jangan di 3 detik pertama (area hook)
- Keyword harus memperkuat apa yang dibicarakan
- visual_category sesuai konten (data→motion_graphic, tempat→footage, dll)

OUTPUT FORMAT — RAW JSON (tanpa markdown):
{{"creative_direction": {{"primary_color": "<hex>", "secondary_color": "<hex>", "background_accent": "<hex>", "typography_mood": "<mood>", "energy_level": "<level>", "transition_style": "<style>", "music_mood": "<mood>", "hook_animation": "<anim>"}}, "broll_suggestions": {{"1": [{{"at_time": <float>, "keyword": "<UPPERCASE>", "template": "<template>", "duration": <float>, "visual_category": "<category>"}}]}}}}"""

        raw = self._call_groq_llm(prompt)
        return self._parse_json_response(raw)

    # ─── Groq LLM API Call ────────────────────────────────────────────────────

    def _call_groq_llm(self, prompt: str) -> str:
        """Call Groq LLM with retry logic and model fallback."""
        client = self._get_groq_client()
        model = self._model if not self._using_fallback else self._fallback_model

        for attempt in range(self._max_retries):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "user", "content": prompt},
                    ],
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

                # Rate limit → wait and retry
                if "429" in error_str or "rate" in error_str:
                    wait = (attempt + 1) * 5
                    logger.warning(f"v2_analyzer: rate limited, waiting {wait}s (attempt {attempt+1})")
                    time.sleep(wait)
                    continue

                # Model overloaded → try fallback model
                if "503" in error_str or "overloaded" in error_str:
                    if not self._using_fallback and self._fallback_model != self._model:
                        logger.warning(f"v2_analyzer: switching to fallback model {self._fallback_model}")
                        self._using_fallback = True
                        model = self._fallback_model
                        continue

                # Last attempt
                if attempt == self._max_retries - 1:
                    raise GroqAnalyzerError(f"Groq LLM failed after {self._max_retries} attempts: {e}")

                logger.warning(f"v2_analyzer: attempt {attempt+1} failed: {e}")
                time.sleep(2)

        raise GroqAnalyzerError("Groq LLM failed: max retries exceeded")

    # ─── Response Parsing ─────────────────────────────────────────────────────

    def _parse_chunk_response(
        self, raw_text: str, chunk_start: float, chunk_end: float
    ) -> list[HighlightCandidate]:
        """Parse Groq LLM chunk analysis response → list of candidates."""
        data = self._parse_json_response(raw_text)
        if not data or "clips" not in data:
            return []

        candidates = []
        for clip in data["clips"]:
            try:
                start = float(clip.get("start", 0))
                end = float(clip.get("end", 0))
                score = int(clip.get("score", 50))

                # Validate timestamps within chunk bounds (with tolerance)
                if start < chunk_start - 5:
                    start = chunk_start
                if end > chunk_end + 5:
                    end = chunk_end

                # Validate duration (45-90s target, allow 30-120s with tolerance)
                duration = end - start
                if duration < 30 or duration > 120:
                    continue

                # Clamp score
                score = max(1, min(100, score))

                candidates.append(HighlightCandidate(
                    rank=0,  # Will be assigned during ranking
                    start=round(start, 2),
                    end=round(end, 2),
                    score=score,
                    hook=str(clip.get("hook", ""))[:60],
                    reason=str(clip.get("reason", "")),
                    content_type=str(clip.get("content_type", "storytelling")),
                    speaker_energy=str(clip.get("speaker_energy", "medium")),
                ))
            except (ValueError, TypeError, KeyError) as e:
                logger.debug(f"v2_analyzer: skipping invalid clip: {e}")
                continue

        return candidates

    def _parse_json_response(self, raw_text: str) -> dict:
        """Parse JSON response with tolerance for markdown fences."""
        text = raw_text.strip()

        # Remove markdown code fences
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
            # Try to extract JSON object from response text
            start_idx = text.find("{")
            end_idx = text.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                try:
                    return json.loads(text[start_idx:end_idx])
                except json.JSONDecodeError:
                    pass

            logger.warning(f"v2_analyzer: failed to parse JSON response: {text[:200]}")
            return {}

    # ─── Ranking & Merge ──────────────────────────────────────────────────────

    def _rank_and_merge(
        self, candidates: list[HighlightCandidate], max_clips: int, video_duration: float
    ) -> list[HighlightCandidate]:
        """Merge candidates from all chunks, remove overlaps, rank by score."""
        if not candidates:
            return []

        # Sort by score (descending)
        sorted_clips = sorted(candidates, key=lambda c: c.score, reverse=True)

        # Remove overlapping clips (keep higher score)
        selected = []
        for clip in sorted_clips:
            if len(selected) >= max_clips:
                break
            if not self._overlaps_with_any(clip, selected):
                selected.append(clip)

        # Sort by start time and assign ranks
        selected.sort(key=lambda c: c.start)
        for i, clip in enumerate(selected):
            clip.rank = i + 1

        return selected

    def _overlaps_with_any(
        self, clip: HighlightCandidate, selected: list[HighlightCandidate]
    ) -> bool:
        """Check if clip overlaps with any already selected clip."""
        for existing in selected:
            # Overlap if: clip.start < existing.end AND clip.end > existing.start
            if clip.start < existing.end and clip.end > existing.start:
                return True
        return False
