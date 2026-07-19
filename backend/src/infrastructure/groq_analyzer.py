"""GroqAnalyzer — TAHAP 2: AI Highlight Analysis via configured LLM router.

Architecture (Two-Pass + Segment ID):
    Pass 1 (router per-chunk — fast scanning):
    - Chunk transcript with Segment IDs ([S0015 | 02:30] text)
    - Ask 8b to identify candidate clips using start_id/end_id
    - Generates ~5 candidates per chunk (over-generate)
    - Prevents timestamp hallucination via Segment ID anchoring

    Pass 2 (router global — quality ranking):
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
from src.infrastructure.text_emphasis import (
    anchor_text_emphasis_response,
    build_text_emphasis_context,
    build_text_emphasis_context_full,
    normalise_text_emphasis_style,
)

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
    """TAHAP 2: Two-Pass highlight analysis with Segment ID anchoring.

    The historical class name is kept for interface compatibility. In 9router
    deployments, all LLM calls go through 9router's OpenAI-compatible API.
    """

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
        if settings.use_nine_router:
            self._model_pass1 = settings.NINE_ROUTER_PASS1_MODEL or settings.nine_router_model
            self._model_pass2 = settings.NINE_ROUTER_PASS2_MODEL or settings.nine_router_model
            self._max_retries = settings.NINE_ROUTER_MAX_RETRIES
            self._timeout = settings.NINE_ROUTER_TIMEOUT
        else:
            self._model_pass1 = settings.GROQ_LLM_MODEL  # 8b — fast scanning
            self._model_pass2 = settings.GROQ_LLM_FALLBACK_MODEL  # 70b — quality ranking
            self._max_retries = settings.GROQ_MAX_RETRIES
            self._timeout = settings.GROQ_TIMEOUT
        self._chunk_max_seconds = settings.V2_CHUNK_MAX_SECONDS
        self._chunk_max_chars = settings.V2_CHUNK_MAX_CHARS

    def _get_groq_client(self):
        """Lazy-init Groq client."""
        if not settings.ALLOW_DIRECT_PROVIDER_FALLBACKS:
            raise GroqAnalyzerError(
                "Direct Groq fallback disabled. Configure NINE_ROUTER_BASE_URL "
                "or set ALLOW_DIRECT_PROVIDER_FALLBACKS=true explicitly."
            )
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

    async def analyze_broll(
        self,
        transcript: TranscriptResult,
        video_duration: float,
        max_suggestions: int = 3,
    ) -> dict:
        """Generate lightweight B-roll suggestions without selecting or cutting clips.

        This is used by Direct Edit only when the user explicitly enables
        Auto B-roll. Suggested timestamps are anchored back to real transcript
        segment timestamps so an LLM cannot shift the audio/subtitle timeline.
        """
        eligible_segments = [
            segment
            for segment in transcript.segments
            if segment.start >= 3.0 and segment.text.strip()
        ]
        if not eligible_segments or video_duration <= 4.0 or max_suggestions <= 0:
            return {}

        # Keep this a single, small router call even for long Direct Edit videos.
        # Evenly sampled timestamped segments preserve coverage across the source.
        sample_limit = 60
        if len(eligible_segments) <= sample_limit:
            sampled_segments = eligible_segments
        else:
            last_index = len(eligible_segments) - 1
            sampled_indices = {
                round(i * last_index / (sample_limit - 1))
                for i in range(sample_limit)
            }
            sampled_segments = [eligible_segments[i] for i in sorted(sampled_indices)]

        context_lines = []
        context_chars = 0
        for segment in sampled_segments:
            line = f"[{segment.start:.2f}s] {segment.text.strip()[:220]}"
            if context_chars + len(line) > 12000:
                break
            context_lines.append(line)
            context_chars += len(line)
        if not context_lines:
            return {}

        prompt = f"""Kamu adalah visual director video pendek. Pilih maksimal {min(max_suggestions, 3)} B-roll yang benar-benar relevan berdasarkan transkrip bertimestamp berikut.

TRANSKRIP:
{chr(10).join(context_lines)}

ATURAN:
- at_time WAJIB memakai salah satu timestamp yang tertulis di transkrip.
- Jangan pilih bagian sebelum detik 3 agar tidak menimpa area hook.
- B-roll hanya mengganti visual; jangan mengubah durasi atau urutan ucapan.
- keyword berupa istilah pencarian stock footage yang konkret, maksimal 6 kata.
- duration antara 1.5 sampai 3.0 detik.
- visual_category: footage, icon, motion_graphic, atau reaction.
- template: word_pop_typography, line_reveal_typography, atau particle_text_burst.

OUTPUT RAW JSON:
{{"items":[{{"at_time":12.5,"keyword":"aging population","duration":2.5,"visual_category":"footage","template":"word_pop_typography"}}]}}"""

        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(
                    self._call_groq_llm,
                    prompt,
                    self._model_pass1,
                    1200,
                ),
                timeout=self._timeout,
            )
            parsed = self._parse_json_response(raw)
        except Exception as exc:
            logger.warning(f"v2_analyzer: direct B-roll analysis failed: {exc}")
            return {}

        raw_items = parsed.get("items", []) if isinstance(parsed, dict) else []
        if not isinstance(raw_items, list):
            return {}

        allowed_times = [float(segment.start) for segment in sampled_segments]
        allowed_templates = {
            "word_pop_typography",
            "line_reveal_typography",
            "particle_text_burst",
        }
        allowed_categories = {"footage", "icon", "motion_graphic", "reaction"}
        suggestions = []

        for item in raw_items:
            if not isinstance(item, dict):
                continue
            keyword = " ".join(str(item.get("keyword") or "").split())[:80]
            if not keyword:
                continue
            try:
                requested_time = float(item.get("at_time"))
            except (TypeError, ValueError):
                continue

            # Anchor every suggestion to a timestamp Whisper actually produced.
            at_time = min(allowed_times, key=lambda timestamp: abs(timestamp - requested_time))
            if at_time >= video_duration - 1.0:
                continue
            if any(abs(at_time - existing["at_time"]) < 4.0 for existing in suggestions):
                continue

            try:
                requested_duration = float(item.get("duration", 2.0))
            except (TypeError, ValueError):
                requested_duration = 2.0
            duration = min(3.0, max(1.5, requested_duration))
            duration = min(duration, video_duration - at_time)
            if duration < 1.0:
                continue

            template = str(item.get("template") or "word_pop_typography")
            if template not in allowed_templates:
                template = "word_pop_typography"
            visual_category = str(item.get("visual_category") or "footage")
            if visual_category not in allowed_categories:
                visual_category = "footage"

            suggestions.append({
                "at_time": round(at_time, 3),
                "keyword": keyword,
                "template": template,
                "duration": round(duration, 3),
                "visual_category": visual_category,
            })
            if len(suggestions) >= min(max_suggestions, 3):
                break

        return {"1": suggestions} if suggestions else {}

    async def analyze_broll_for_clips(
        self,
        clips_words: dict[int, list[dict]],
        clip_durations: dict[int, float],
        max_suggestions: int = 2,
    ) -> dict:
        """Recover B-roll suggestions from the final word-level transcript.

        Creative-direction generation is intentionally separate from highlight
        ranking and can fail independently. This method gives Analyze First a
        second, smaller router call and anchors every result to a real Whisper
        word timestamp. A conservative local fallback still produces one useful
        suggestion when the router returns malformed or empty JSON.
        """
        max_suggestions = max(0, min(int(max_suggestions), 2))
        eligible: dict[int, list[dict]] = {}
        context_lines: list[str] = []

        for raw_rank, words in sorted(clips_words.items()):
            rank = int(raw_rank)
            duration = float(clip_durations.get(rank, 0.0) or 0.0)
            clean_words = [
                word
                for word in words
                if 3.0 <= float(word.get("start", -1.0)) < duration - 1.0
                and str(word.get("word") or "").strip()
            ]
            if not clean_words or duration <= 4.0:
                continue
            eligible[rank] = clean_words

            # Give every clip coverage without letting a long transcript crowd
            # all other clips out of the prompt.
            window_size = 8
            windows = [
                clean_words[index:index + window_size]
                for index in range(0, len(clean_words), window_size)
            ]
            if len(windows) > 18:
                last_index = len(windows) - 1
                selected_indices = sorted({
                    round(index * last_index / 17)
                    for index in range(18)
                })
                windows = [windows[index] for index in selected_indices]
            for window in windows:
                text = " ".join(
                    str(word.get("word") or "").strip()
                    for word in window
                ).strip()
                if text:
                    context_lines.append(
                        f"Clip {rank} [{float(window[0]['start']):.2f}s] {text[:260]}"
                    )

        if not eligible or max_suggestions <= 0:
            return {}

        context = "\n".join(context_lines)
        if len(context) > 14000:
            context = context[:14000]
        prompt = f"""Kamu adalah visual director short video. Pilih maksimal {max_suggestions} momen B-roll yang benar-benar membantu pemahaman untuk setiap clip berikut.

TRANSKRIP CLIP BERTIMESTAMP:
{context}

ATURAN:
- at_time harus menyalin salah satu timestamp yang tersedia pada clip yang sama.
- Jangan pilih sebelum detik 3 dan jangan mengubah durasi/audio.
- keyword harus berupa query stock footage konkret dalam bahasa Inggris, 2-6 kata; hindari kata abstrak/generik.
- Utamakan footage. Pakai icon/motion_graphic/reaction hanya bila lebih tepat.
- duration 1.5-3.0 detik dan beri jarak minimal 6 detik antar-B-roll.
- Boleh kosong jika tidak ada visual yang relevan.

OUTPUT RAW JSON:
{{"clips":{{"1":[{{"at_time":12.5,"keyword":"elderly people city","duration":2.5,"visual_category":"footage","template":"word_pop_typography"}}]}}}}
"""

        parsed: dict = {}
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(
                    self._call_groq_llm,
                    prompt,
                    self._model_pass1,
                    1800,
                ),
                timeout=self._timeout,
            )
            parsed = self._parse_json_response(raw)
        except Exception as exc:
            logger.warning("v2_analyzer: clip B-roll recovery failed: %s", exc)

        raw_map = parsed.get("clips", {}) if isinstance(parsed, dict) else {}
        if not isinstance(raw_map, dict):
            raw_map = {}

        allowed_templates = {
            "word_pop_typography",
            "line_reveal_typography",
            "particle_text_burst",
        }
        allowed_categories = {"footage", "icon", "motion_graphic", "reaction"}
        result: dict[str, list[dict]] = {}

        for rank, words in eligible.items():
            duration = float(clip_durations.get(rank, 0.0) or 0.0)
            allowed_times = [float(word["start"]) for word in words]
            raw_items = raw_map.get(str(rank), raw_map.get(rank, []))
            if not isinstance(raw_items, list):
                raw_items = []
            items: list[dict] = []

            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                keyword = " ".join(str(item.get("keyword") or "").split())[:80]
                if not keyword:
                    continue
                try:
                    requested_time = float(item.get("at_time"))
                except (TypeError, ValueError):
                    continue
                at_time = min(allowed_times, key=lambda value: abs(value - requested_time))
                if at_time < 3.0 or at_time >= duration - 1.0:
                    continue
                if any(abs(at_time - existing["at_time"]) < 6.0 for existing in items):
                    continue
                try:
                    item_duration = float(item.get("duration", 2.25))
                except (TypeError, ValueError):
                    item_duration = 2.25
                item_duration = min(3.0, max(1.5, item_duration), duration - at_time)
                if item_duration < 1.0:
                    continue
                template = str(item.get("template") or "word_pop_typography")
                category = str(item.get("visual_category") or "footage")
                items.append({
                    "at_time": round(at_time, 3),
                    "keyword": keyword,
                    "duration": round(item_duration, 3),
                    "visual_category": category if category in allowed_categories else "footage",
                    "template": template if template in allowed_templates else "word_pop_typography",
                })
                if len(items) >= max_suggestions:
                    break

            if not items:
                items = self._fallback_broll_from_words(words, duration, limit=1)
            if items:
                result[str(rank)] = items

        return result

    @staticmethod
    def _fallback_broll_from_words(
        words: list[dict],
        duration: float,
        limit: int = 1,
    ) -> list[dict]:
        """Pick a sparse concrete phrase when the optional AI call is down."""
        stopwords = {
            "yang", "dan", "atau", "dari", "untuk", "dengan", "adalah", "itu",
            "ini", "ada", "akan", "bisa", "jadi", "juga", "karena", "kalau",
            "kita", "mereka", "saya", "aku", "kamu", "dia", "nya", "kan",
            "lagi", "sudah", "belum", "lebih", "paling", "satu", "sebuah",
            "the", "and", "that", "this", "with", "from", "have", "has",
            "was", "were", "are", "you", "your", "they", "their", "about",
            "basically", "gitu", "lah", "nih", "sih", "aja", "kayak",
        }
        content_words: list[tuple[int, str, float]] = []
        for index, word in enumerate(words):
            raw = str(word.get("word") or "").strip()
            token = re.sub(r"[^0-9A-Za-zÀ-ÿ]+", "", raw).lower()
            try:
                start = float(word.get("start", -1.0))
            except (TypeError, ValueError):
                continue
            if start < 3.0 or start >= duration - 1.0:
                continue
            if len(token) < 4 or token in stopwords:
                continue
            content_words.append((index, raw, start))

        candidates: list[tuple[float, float, str]] = []
        for position, (word_index, raw, start) in enumerate(content_words):
            phrase = [raw]
            for next_index, next_raw, next_start in content_words[position + 1:position + 3]:
                if next_index - word_index > 5 or next_start - start > 2.5:
                    break
                phrase.append(next_raw)
            keyword = " ".join(phrase[:3]).strip()
            unique_tokens = len({part.lower() for part in phrase})
            score = sum(len(part) for part in phrase) + unique_tokens * 3
            if any(char.isdigit() for char in keyword):
                score += 8
            candidates.append((float(score), start, keyword))

        selected: list[dict] = []
        for _score, start, keyword in sorted(candidates, reverse=True):
            if any(abs(start - item["at_time"]) < 8.0 for item in selected):
                continue
            selected.append({
                "at_time": round(start, 3),
                "keyword": keyword[:80],
                "duration": round(min(2.25, duration - start), 3),
                "visual_category": "footage",
                "template": "word_pop_typography",
            })
            if len(selected) >= max(0, int(limit)):
                break
        return sorted(selected, key=lambda item: item["at_time"])

    async def analyze_text_emphasis(
        self,
        clips_words: dict[int, list[dict]],
        clip_durations: dict[int, float],
        style: Optional[dict] = None,
        min_start_by_clip: Optional[dict[int, float]] = None,
        blocked_ranges_by_clip: Optional[dict[int, list[tuple[float, float]]]] = None,
        max_events: int = 2,
    ) -> dict[int, list[dict]]:
        """Choose sparse cinematic text moments through 9router.

        Sends the FULL word-level transcript per clip to the AI (no sampling).
        Enforces minimum 1 event per clip. Retries 9router up to 2 times;
        on double failure falls back to the sampled-context approach.

        The model selects only Whisper word IDs. ``anchor_text_emphasis_response``
        then reconstructs text/timing locally and enforces spacing, hook,
        B-roll, and duration rules.
        """
        if max_events <= 0 or not any(clips_words.values()):
            return {}

        # Build full context — all words per clip, no sampling
        context, _lookup = build_text_emphasis_context_full(clips_words)
        if not context:
            return {}

        safe_style = normalise_text_emphasis_style(style)
        effect_instruction = (
            "Pilih effect paling cocok dari behind_person, spotlight, side_label, "
            "floating_text, auto_avoid, around_head, depth_text, kinetic_type."
            if safe_style["effectMode"] == "auto"
            else f'Semua pilihan WAJIB memakai effect "{safe_style["effectMode"]}".'
        )
        prompt = f"""Kamu adalah senior motion editor video pendek. Pilih frasa yang layak ditonjolkan sebagai cinematic text.

TRANSKRIP WORD-ID (lengkap per clip):
{context}

ATURAN KETAT:
- WAJIB minimal 1 event per clip, maksimal {min(2, max_events)} event per clip. Tidak boleh 0.
- Frasa 1-7 kata, harus memakai start_word dan end_word yang berurutan pada clip yang sama.
- Prioritaskan angka mengejutkan, tesis utama, kontras tajam, istilah inti, atau punchline.
- Hindari filler, salam, kalimat generik, dan jangan memilih dua frasa yang berdekatan (min 6 detik jarak).
- behind_person: pernyataan hero sangat kuat (teks di belakang subjek, butuh segmentasi orang).
- spotlight: angka/punchline (hero text + vignette).
- side_label: istilah atau konteks singkat (label editorial di sisi).
- floating_text: teks melayang mengikuti gerakan orang (gentle bob).
- auto_avoid: teks otomatis menghindari orang (ke area kosong terbesar).
- around_head: teks mengorbit di sekitar kepala orang.
- depth_text: teks dengan parallax kedalaman (dekat/jauh mengikuti posisi orang).
- kinetic_type: tipografi kinetik kata-per-kata (cocok untuk frasa pendek dan ritmis).
- {effect_instruction}
- position hanya left, center, atau right.
- Jangan membuat ulang teks dan jangan membuat timestamp.

OUTPUT RAW JSON SAJA:
{{"clips":{{"1":[{{"start_word":"W0012","end_word":"W0015","effect":"behind_person","position":"center","reason":"tesis utama"}}]}}}}
"""
        model = (
            settings.NINE_ROUTER_AI_LAYER_MODEL
            if settings.use_nine_router
            else self._model_pass1
        )

        # Retry 9router up to 2 attempts with full context
        parsed = None
        last_error = None
        for attempt in range(2):
            try:
                raw = await asyncio.wait_for(
                    asyncio.to_thread(self._call_groq_llm, prompt, model, 2400),
                    timeout=self._timeout,
                )
                parsed = self._parse_json_response(raw)
                if parsed:
                    break
            except Exception as exc:
                last_error = exc
                logger.warning(
                    f"v2_analyzer: text emphasis attempt {attempt + 1}/2 failed: {exc}"
                )
                if attempt < 1:
                    await asyncio.sleep(3)

        # If both 9router attempts failed, fallback to sampled context approach
        if parsed is None:
            logger.warning(
                f"v2_analyzer: text emphasis 9router failed 2x ({last_error}), "
                f"using sampled fallback"
            )
            try:
                fallback_context, _ = build_text_emphasis_context(clips_words)
                if fallback_context:
                    fallback_prompt = f"""Kamu adalah senior motion editor video pendek. Pilih frasa yang layak ditonjolkan sebagai cinematic text.

TRANSKRIP WORD-ID:
{fallback_context}

ATURAN KETAT:
- WAJIB minimal 1 event per clip, maksimal {min(2, max_events)} event per clip. Tidak boleh 0.
- Frasa 1-7 kata, harus memakai start_word dan end_word yang berurutan pada clip yang sama.
- Jangan melewati penanda [... gap ...].
- Prioritaskan angka mengejutkan, tesis utama, kontras tajam, istilah inti, atau punchline.
- Hindari filler, salam, kalimat generik, dan jangan memilih dua frasa yang berdekatan.
- behind_person: pernyataan hero sangat kuat (teks di belakang subjek).
- spotlight: angka/punchline (hero text + vignette).
- side_label: istilah atau konteks singkat (label editorial di sisi).
- floating_text: teks melayang mengikuti gerakan orang.
- auto_avoid: teks otomatis menghindari orang.
- around_head: teks mengorbit di sekitar kepala orang.
- depth_text: teks dengan parallax kedalaman.
- kinetic_type: tipografi kinetik kata-per-kata.
- {effect_instruction}
- position hanya left, center, atau right.
- Jangan membuat ulang teks dan jangan membuat timestamp.

OUTPUT RAW JSON SAJA:
{{"clips":{{"1":[{{"start_word":"W0012","end_word":"W0015","effect":"behind_person","position":"center","reason":"tesis utama"}}]}}}}
"""
                    raw = await asyncio.wait_for(
                        asyncio.to_thread(self._call_groq_llm, fallback_prompt, model, 1800),
                        timeout=self._timeout,
                    )
                    parsed = self._parse_json_response(raw)
            except Exception as exc:
                logger.warning(f"v2_analyzer: text emphasis sampled fallback also failed: {exc}")
                parsed = {}

        return anchor_text_emphasis_response(
            parsed or {},
            clips_words,
            clip_durations,
            style=safe_style,
            min_start_by_clip=min_start_by_clip,
            blocked_ranges_by_clip=blocked_ranges_by_clip,
            max_events=min(2, max_events),
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
        candidates = self._parse_pass1_response(raw, segment_map, chunk_start, chunk_end)

        # Retry once with stricter prompt if JSON parse returned 0 candidates
        if not candidates and raw and raw.strip():
            logger.info(f"v2_analyzer: Pass 1 chunk {chunk_num} retry (0 candidates from first attempt)")
            retry_prompt = (
                "PENTING: Jawab HANYA dengan JSON valid. Jangan gunakan markdown, "
                "jangan tambahkan penjelasan. Format:\n"
                '{"clips": [{"start_id": "SXXXX", "end_id": "SXXXX", "score": 80, '
                '"summary": "...", "content_type": "storytelling", "speaker_energy": "high"}]}\n\n'
                + prompt
            )
            raw_retry = self._call_groq_llm(retry_prompt, model=self._model_pass1, max_tokens=1500)
            candidates = self._parse_pass1_response(raw_retry, segment_map, chunk_start, chunk_end)

        return candidates

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
        """Call the configured LLM router with exponential backoff retry logic.

        Args:
            prompt: The prompt to send
            model: Model to use (defaults to pass1 model)
            max_tokens: Max tokens for response (varies by use case)
        """
        use_model = model or self._model_pass1
        total_attempts = max(self._max_retries, 5)

        if settings.use_nine_router:
            from src.infrastructure.nine_router_client import get_nine_router_client

            client = get_nine_router_client()
            for attempt in range(total_attempts):
                try:
                    return client.chat(
                        model=use_model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3,
                        max_tokens=max_tokens,
                        response_format={"type": "json_object"},
                    )
                except Exception as e:
                    error_str = str(e).lower()

                    if "429" in error_str or "rate" in error_str:
                        wait = min(30 * (2 ** attempt), 240)
                        logger.warning(
                            f"v2_analyzer: 9router rate limited, waiting {wait}s "
                            f"(attempt {attempt+1}/{total_attempts}, model={use_model})"
                        )
                        time.sleep(wait)
                        continue

                    if "503" in error_str or "overloaded" in error_str:
                        if use_model == self._model_pass2 and self._model_pass1 != self._model_pass2:
                            logger.warning(
                                f"v2_analyzer: {self._model_pass2} overloaded, "
                                f"falling back to {self._model_pass1}"
                            )
                            use_model = self._model_pass1
                            time.sleep(5)
                            continue

                    if attempt >= total_attempts - 1:
                        raise GroqAnalyzerError(
                            f"9router LLM failed after {total_attempts} attempts: {e}"
                        )

                    wait = min(5 * (2 ** attempt), 60)
                    logger.warning(f"v2_analyzer: attempt {attempt+1} failed: {e}, retry in {wait}s")
                    time.sleep(wait)

            raise GroqAnalyzerError("9router LLM max retries exceeded")

        client = self._get_groq_client()

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
        """Parse JSON with tolerance for markdown fences, trailing commas, and truncation."""
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
            except json.JSONDecodeError:
                pass

            # Third attempt: repair truncated JSON (LLM cut off mid-response)
            repaired = self._repair_truncated_json(json_str)
            if repaired:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError as e:
                    logger.warning(f"v2_analyzer: JSON parse failed after repair: {e}\nRaw: {json_str[:200]}")
            else:
                logger.warning(f"v2_analyzer: JSON parse failed after cleanup: truncated\nRaw: {json_str[:200]}")
        else:
            logger.warning(f"v2_analyzer: failed to parse JSON (no JSON object found): {text[:200]}")

        return {}

    def _repair_truncated_json(self, json_str: str) -> Optional[str]:
        """Attempt to repair truncated JSON from LLM max_tokens cutoff.

        Common patterns:
        - {"clips": [{"start_id": "S0275", ...}, {"start_id": "S0300", ...   (cut off)
        - Missing closing brackets/braces

        Strategy: find last complete object in array, close the structure.
        """
        # Count open vs close braces/brackets
        open_braces = json_str.count('{') - json_str.count('}')
        open_brackets = json_str.count('[') - json_str.count(']')

        if open_braces == 0 and open_brackets == 0:
            return None  # Not a truncation issue

        # Find the last complete object boundary ("},")
        # Truncate to last complete item and close the structure
        last_complete = json_str.rfind('},')
        if last_complete == -1:
            last_complete = json_str.rfind('}')

        if last_complete == -1:
            return None  # No complete object found

        # Keep up to and including the last complete "}"
        repaired = json_str[:last_complete + 1]

        # Close any remaining open brackets/braces
        open_braces = repaired.count('{') - repaired.count('}')
        open_brackets = repaired.count('[') - repaired.count(']')
        repaired += ']' * open_brackets + '}' * open_braces

        return repaired

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
