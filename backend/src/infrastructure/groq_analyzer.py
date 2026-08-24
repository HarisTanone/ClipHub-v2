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
from src.infrastructure.clipscout_client import sanitize_stock_keyword
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
            if segment.start >= min(3.0, max(0.2, video_duration * 0.05)) and segment.text.strip()
        ]
        if not eligible_segments or video_duration < 1.5 or max_suggestions <= 0:
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

        # Dual tracks: full_frame splice + behind_person top overlay (unconstrained dynamic AI analysis)
        prompt = f"""Kamu adalah visual director video pendek profesional. Analisa transkrip secara mendalam dan tentukan B-roll visual (baik full_frame footage maupun behind_person image/footage) yang dibutuhkan narasi transkrip secara bebas dan dinamis tanpa batasan kaku.

TRANSKRIP:
{chr(10).join(context_lines)}

DUA MODE PLACEMENT (otomatis, dinamis):
1) full_frame — stock VIDEO ganti layar penuh (clip→footage→clip). Person HILANG sementara. Pakai visual_category=footage.
2) behind_person — stock IMAGE/icon di BELAKANG person (top half). Person TETAP kelihatan. Pakai visual_category=icon atau motion_graphic atau footage.

ATURAN:
- at_time WAJIB salah satu timestamp di transkrip; jangan sebelum detik 3.
- JANGAN pakai waktu yang sama untuk full_frame dan behind_person (min jarak 4 detik).
- Tentukan jumlah B-roll dan Behind Person yang pas sesuai alur cerita transkrip (sebanyak yang dibutuhkan konteks cerita).
- keyword = query stock ENGLISH 3-8 kata, KONKRET visual dari konteks clip ini (analisa dinamis — jangan andalkan daftar kata domain tetap).
  LANGKAH: (1) baca kalimat di timestamp (2) ekstrak 1 fakta visual UTAMA (3) terjemah 1:1 ke query stock literal.
  Format: [concrete subject] [action OR state] [framing/detail]
  JELEK: abstract mood "success", "lifestyle", "viral", "city skyline generic", 1 kata generic.
  Dilarang: nama orang, brand, abstraksi, mood-only.
  behind_person: CLOSE-UP object/icon/subject (fill frame). LARANG wide landscape/cityscape.
  full_frame: boleh medium shot action; tetap mirror topik.
- duration 1.5-3.0 detik.
- visual_category: footage (video) | icon | motion_graphic | reaction
- placement: full_frame | behind_person
- template: word_pop_typography | line_reveal_typography | particle_text_burst
- motion_style: ken_burns | parallax_zoom | light_sweep | particle_float | depth_parallax | glitch_reveal | typewriter | stroke_draw


OUTPUT RAW JSON:
{{"items":[{{"at_time":12.5,"keyword":"concrete stock query from this transcript","duration":2.5,"visual_category":"footage","placement":"full_frame","template":"word_pop_typography","motion_style":"ken_burns"}},{{"at_time":20.0,"keyword":"another concrete closeup object","duration":2.0,"visual_category":"footage","placement":"behind_person","template":"word_pop_typography","motion_style":"ken_burns"}}]}}"""


        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(
                    self._call_groq_llm,
                    prompt,
                    self._model_pass1,
                    1600,
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

        allowed_templates = {
            "word_pop_typography",
            "line_reveal_typography",
            "particle_text_burst",
        }
        allowed_categories = {"footage", "icon", "motion_graphic", "reaction"}
        allowed_times = [float(segment.start) for segment in eligible_segments]
        suggestions = []

        for item in raw_items:
            if not isinstance(item, dict):
                continue
            raw_kw = " ".join(str(item.get("keyword") or "").split())[:80]
            keyword = sanitize_stock_keyword(raw_kw, placement=str(item.get("placement") or "")) or raw_kw
            if not keyword:
                continue
            try:
                requested_time = float(item.get("at_time"))
            except (TypeError, ValueError):
                continue

            # Anchor every suggestion to a timestamp Whisper actually produced.
            at_time = min(allowed_times, key=lambda timestamp: abs(timestamp - requested_time))
            tail = min(1.0, max(0.2, video_duration * 0.06))
            if at_time >= max(0.5, video_duration - tail):
                continue
            if any(abs(at_time - existing["at_time"]) < min(4.0, max(1.5, video_duration * 0.15)) for existing in suggestions):
                continue

            try:
                requested_duration = float(item.get("duration", 2.0))
            except (TypeError, ValueError):
                requested_duration = 2.0
            max_hold = min(3.0, max(0.8, video_duration * 0.35))
            duration = min(max_hold, max(0.8, requested_duration))
            duration = min(duration, video_duration - at_time)
            if duration < 0.6:
                continue

            template = str(item.get("template") or "word_pop_typography")
            if template not in allowed_templates:
                template = "word_pop_typography"
            visual_category = str(item.get("visual_category") or "footage")
            if visual_category not in allowed_categories:
                visual_category = "footage"
            placement = str(item.get("placement") or "").strip().lower()
            if placement in {"fullframe", "splice", "replace"}:
                placement = "full_frame"
            elif placement in {"behind", "top_overlay", "overlay", "top"}:
                placement = "behind_person"
            elif placement not in {"full_frame", "behind_person"}:
                placement = (
                    "behind_person"
                    if visual_category in {"icon", "motion_graphic"}
                    else "full_frame"
                )

            suggestions.append({
                "at_time": round(at_time, 3),
                "keyword": keyword,
                "template": template,
                "duration": round(duration, 3),
                "visual_category": visual_category,
                "placement": placement,
            })
            if max_suggestions and len(suggestions) >= max_suggestions:
                break

        return {"1": suggestions} if suggestions else {}


    async def analyze_visual_entities_for_clips(
        self,
        clips_words: dict[int, list[dict]],
        clip_durations: dict[int, float],
        clip_meta: dict | None = None,
        max_objects: int = 10,
    ) -> dict[int, list[dict]]:
        """Per-clip AI: multi-category visual entities + bilingual stock queries.

        Categories (AI-decided per mention, NO domain lexicon):
        brand | object | action | place | food | person | phenomenon |
        emotion | weather | tech | money | nature | building | sport | concept

        Returns {rank: [{word,start,end,label,entity_type,priority,
                         query_id,query_en,search_queries}, ...]}.
        """
        max_objects = max(1, min(int(max_objects), 12))
        if not clips_words:
            return {}

        eligible: dict[int, list[dict]] = {}
        for raw_rank, words in sorted(clips_words.items()):
            rank = int(raw_rank)
            duration = float(clip_durations.get(rank, 0.0) or 0.0)
            clean = [
                w for w in words
                if str(w.get("word") or "").strip()
                and float(w.get("start", -1) or -1) >= 0
            ]
            if clean and duration > 2.0:
                eligible[rank] = clean
        if not eligible:
            return {}

        meta = clip_meta or {}
        sem = asyncio.Semaphore(2)

        async def _one(rank: int, words: list[dict]) -> tuple[int, list[dict]]:
            async with sem:
                duration = float(clip_durations.get(rank, 0.0) or 0.0)
                m = meta.get(rank) or meta.get(str(rank)) or {}
                try:
                    items = await self._analyze_visual_entities_one_clip(
                        rank=rank,
                        words=words,
                        duration=duration,
                        max_objects=max_objects,
                        hook=str(m.get("hook") or ""),
                        reason=str(m.get("reason") or ""),
                    )
                except Exception as exc:
                    logger.warning(
                        "v2_analyzer: visual entities rank=%s failed: %s", rank, exc
                    )
                    items = []
                if not items:
                    items = self._fallback_visual_entities_from_words(
                        words, duration, limit=max_objects
                    )
                return rank, items

        logger.info(
            "v2_analyzer: visual entities per-clip model=%s clips=%d max=%d",
            self._model_pass1,
            len(eligible),
            max_objects,
        )
        pairs = await asyncio.gather(
            *[_one(rank, words) for rank, words in eligible.items()]
        )
        return {int(rank): items for rank, items in pairs if items}

    async def _analyze_visual_entities_one_clip(
        self,
        *,
        rank: int,
        words: list[dict],
        duration: float,
        max_objects: int = 10,
        hook: str = "",
        reason: str = "",
    ) -> list[dict]:
        """LLM extracts multi-category timed entities + stock search queries."""
        window_size = 10
        windows = [words[i : i + window_size] for i in range(0, len(words), window_size)]
        if len(windows) > 22:
            last = len(windows) - 1
            pick = sorted({round(i * last / 21) for i in range(22)})
            windows = [windows[i] for i in pick]
        lines: list[str] = []
        for window in windows:
            text = " ".join(str(w.get("word") or "").strip() for w in window).strip()
            if text:
                lines.append(f"[{float(window[0]['start']):.2f}s] {text[:280]}")
        context = "\n".join(lines)
        if len(context) > 9000:
            context = context[:9000]
        topic = " | ".join(x for x in (hook.strip(), reason.strip()) if x)[:300]

        prompt = f"""Kamu visual researcher short-form. Ekstrak maks {max_objects} ENTITAS visual dari transkrip word-by-word — tiap entitas → stock foto/footage BERBEDA, timed ke saat diucapkan.

CLIP #{rank} duration={duration:.1f}s
HOOK/TOPIC: {topic or "(n/a)"}

TRANSKRIP BERTIMESTAMP (word-level — gunakan start exact):
{context}

KATEGORI (pilih 1 per entitas — AI putuskan, bukan kamus tetap):
brand | object | action | place | food | person | phenomenon | emotion | weather | tech | money | nature | building | sport | concept

PRIORITAS (1–10, tinggi dulu):
10 named brand/produk (IQOS, merek) · 9 object konkret · 8 action (merokok→smoking) · 7 place · 6 food/person · 5 phenomenon/weather · 4 emotion/concept · 3 sinonim pendukung

ATURAN (WAJIB):
1. Ambil SEMUA merek/benda/aksi/tempat yang DIUCAPKAN (contoh: rokok, IQOS/Aikos ASR, Shisha, merokok, kalender, pod, vape). Jangan stop di 1 entitas.
2. Satu entitas per mention berbeda; sebarkan start di sepanjang clip. word = token/frasa 1-3 kata dari transkrip (ejaan ASR boleh).
3. start = detik float EXACT dari baris di mana kata itu muncul (bukan tebak).
4. JANGAN filler: itu, nah, karena, yang, dan, atau, sudah, masih, sangat, banget, lifestyle, mood, viral, sukses (kecuali proper noun).
5. label = label kartu singkat.
6. entity_type = salah satu kategori di atas.
7. priority = 1–10 integer.
8. query_id = stock ID 2-8 kata konkret (contoh: tepung terigu, rokok kretek, obat kapsul).
9. query_en = stock EN 2-8 kata konkret. Kata bahasa Indonesia berulang/majemuk (contoh: 'tepung-tepungan' → 'wheat flour baking dough', 'sayur-sayuran' → 'fresh green vegetables', 'buah-buahan' → 'fresh fruits assortment', 'obat-obatan' → 'medicine pills capsules pharmacy', 'goreng-gorengan' → 'fried snacks food', 'kacang-kacangan' → 'peanuts nuts legumes') WAJIB diterjemahkan ke kata benda konkret bahasa Inggris agar API foto stock internasional (Pexels/Pixabay) menemukan foto yang tepat, BUKAN salah foto serangga/hewan. ASR salah eja merek → PERBAIKI di query saja (word tetap ucapan).
10. search_queries = 3–6 variasi BERBEDA mencakup:
    - bare entity + product close-up
    - ACTION jika relevan (merokok → person smoking, cigarette smoke)
    - sinonim/konsep terkait (rokok → cigarette, tobacco; IQOS → heated tobacco device; tepung-tepungan → flour, wheat flour, baking powder)
    - adjective compound jika ada (rokok elektrik → electric cigarette)
    Campur ID+EN. Bukan copy query_en 4x.
11. Target ideal 4–{max_objects} jika transkrip kaya; objects:[] hanya jika benar-benar kosong.
12. Action lebih hidup daripada object diam — jika verb visual (merokok, mengetik, minum) sertakan sebagai entitas action terpisah ATAU perluas search_queries object-nya.
13. Deteksi juga kata-kata abstrak/perasaan/kata sambung non-visual di transkrip (misal: nyaman, mikir, bahagia, makanya, karena) dan sertakan di field "abstract_words": ["kata1", "kata2"] agar sistem terus belajar dan menyimpannya ke database stop-words JSON.

OUTPUT RAW JSON only:
{{"objects":[{{"word":"…","start":12.5,"label":"…","entity_type":"object","priority":9,"query_id":"…","query_en":"…","search_queries":["…","…","…"]}}],"abstract_words":["…","…"]}}
"""
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(
                    self._call_groq_llm,
                    prompt,
                    self._model_pass1,
                    2200,
                ),
                timeout=self._timeout,
            )
            parsed = self._parse_json_response(raw)
        except Exception as exc:
            logger.warning("v2_analyzer: visual entities clip %s LLM fail: %s", rank, exc)
            return []

        raw_objs = []
        if isinstance(parsed, dict):
            raw_objs = parsed.get("objects") or parsed.get("items") or parsed.get("entities") or []
            # Dynamic self-learning: persist newly discovered abstract words to JSON dictionary
            new_abstract = parsed.get("abstract_words") or parsed.get("filler_words") or []
            if isinstance(new_abstract, list) and new_abstract:
                try:
                    from src.infrastructure.stop_words_store import learn_abstract_words
                    learn_abstract_words(new_abstract)
                except Exception as exc:
                    logger.debug("v2_analyzer: failed to learn abstract words: %s", exc)
        if not isinstance(raw_objs, list):
            raw_objs = []
        out = self._normalize_visual_entities(
            raw_objs, words=words, duration=duration, max_objects=max_objects
        )
        # Thin AI → top-up offline proper/long (no domain lexicon)
        if len(out) < max(4, max_objects // 2):
            seen = {
                re.sub(r"[^\w\-]+", "", str(o.get("word") or ""), flags=re.UNICODE).lower()
                for o in out
            }
            for fb in self._fallback_visual_entities_from_words(
                words, duration, limit=max_objects
            ):
                low = re.sub(
                    r"[^\w\-]+", "", str(fb.get("word") or ""), flags=re.UNICODE
                ).lower()
                if not low or low in seen:
                    continue
                seen.add(low)
                out.append(fb)
                if len(out) >= max_objects:
                    break
        # Prefer higher priority first for downstream pick
        out.sort(key=lambda o: (-int(o.get("priority") or 5), float(o.get("start") or 0)))
        return out[:max_objects]

    def _normalize_visual_entities(
        self,
        raw_objs: list,
        *,
        words: list[dict],
        duration: float,
        max_objects: int,
    ) -> list[dict]:
        """Anchor AI objects to transcript times; keep dynamic queries as-is."""
        allowed_types = {
            "brand", "object", "action", "place", "food", "person",
            "phenomenon", "emotion", "weather", "tech", "money",
            "nature", "building", "sport", "concept",
        }
        allowed_times = [float(w["start"]) for w in words if "start" in w]
        word_index: dict[str, list[tuple[float, float, str]]] = {}
        for w in words:
            tok = re.sub(r"[^\w\-]+", "", str(w.get("word") or ""), flags=re.UNICODE).lower()
            if not tok:
                continue
            try:
                s = float(w.get("start", 0) or 0)
                e = float(w.get("end", s + 0.3) or s + 0.3)
            except (TypeError, ValueError):
                continue
            word_index.setdefault(tok, []).append((s, e, str(w.get("word") or "")))

        out: list[dict] = []
        seen: set[str] = set()
        for item in raw_objs:
            if not isinstance(item, dict):
                continue
            word = " ".join(str(item.get("word") or "").split())[:40]
            if not word:
                continue
            low = re.sub(r"[^\w\-]+", "", word, flags=re.UNICODE).lower()
            if not low or low in seen:
                continue
            try:
                start = float(item.get("start", -1))
            except (TypeError, ValueError):
                start = -1.0
            end = start + 0.4
            # Snap to nearest transcript mention of same token if possible
            hits = word_index.get(low) or []
            if not hits:
                # multi-word / partial
                parts = [p for p in re.split(r"[^\w]+", low) if len(p) >= 3]
                for p in parts:
                    if p in word_index:
                        hits = word_index[p]
                        break
                if not hits:
                    first = low.split("-")[0] if "-" in low else low[:12]
                    for k, v in word_index.items():
                        if first and (first in k or k in first):
                            hits = v
                            break
            if hits:
                if start < 0:
                    s, e, raw_w = hits[0]
                    start, end, word = s, e, raw_w
                else:
                    s, e, raw_w = min(hits, key=lambda t: abs(t[0] - start))
                    start, end = s, e
                    if len(word) < 2:
                        word = raw_w
            elif allowed_times and start >= 0:
                start = min(allowed_times, key=lambda t: abs(t - start))
                end = start + 0.4
            elif allowed_times:
                start = allowed_times[min(len(allowed_times) // 3, len(allowed_times) - 1)]
                end = start + 0.4
            else:
                continue
            if duration > 0 and start >= duration - 0.5:
                continue

            label = " ".join(str(item.get("label") or word).split())[:40] or word
            et = str(item.get("entity_type") or item.get("type") or "object").strip().lower()
            if et not in allowed_types:
                et = "object"
            try:
                priority = int(item.get("priority", 5) or 5)
            except (TypeError, ValueError):
                priority = 5
            priority = max(1, min(10, priority))

            query_id = " ".join(str(item.get("query_id") or "").split())[:80]
            query_en = " ".join(str(item.get("query_en") or "").split())[:80]
            sq_raw = item.get("search_queries") or []
            search_queries: list[str] = []
            if isinstance(sq_raw, list):
                for q in sq_raw:
                    q = " ".join(str(q or "").split())[:80]
                    if q and q.lower() not in {x.lower() for x in search_queries}:
                        search_queries.append(q)
            # Always keep bilingual pair if present
            for q in (word, query_id, query_en):
                if q and q.lower() not in {x.lower() for x in search_queries}:
                    search_queries.append(q)
            if not query_en and not query_id:
                continue
            if not query_en:
                query_en = search_queries[0] if search_queries else f"{word} close up"
            if not query_id:
                query_id = search_queries[1] if len(search_queries) > 1 else query_en

            seen.add(low)
            out.append({
                "word": word,
                "start": round(float(start), 3),
                "end": round(float(end), 3),
                "label": label,
                "entity_type": et,
                "priority": priority,
                "query_id": query_id,
                "query_en": query_en,
                "search_queries": search_queries[:8],
                "source": "ai",
            })
            if len(out) >= max_objects:
                break
        return out

    @staticmethod
    def _fallback_visual_entities_from_words(
        words: list[dict],
        duration: float,
        limit: int = 4,
    ) -> list[dict]:
        """Offline: concrete object/brand tokens only — strictly ignore abstract adjectives/verbs/conjunctions via dynamic JSON store."""
        from src.infrastructure.stop_words_store import is_abstract_word

        out: list[dict] = []
        seen: set[str] = set()
        for w in words or []:
            text = str(w.get("word") or "").strip().strip(".,!?;:\"'")
            clean = re.sub(r"[^\w\-]+", "", text, flags=re.UNICODE)
            low = clean.lower()
            if len(clean) < 4 or low in seen or is_abstract_word(low):
                continue
            try:
                s = float(w.get("start", 0) or 0)
                e = float(w.get("end", s + 0.3) or s + 0.3)
            except (TypeError, ValueError):
                continue
            # Skip very early chatter; leave room at end
            if s < 2.0 or (duration > 0 and s >= duration - 0.8):
                continue
            proper = clean[:1].isupper() and not clean.isupper()
            # Prefer brand-like / long content tokens (no membership ban lists)
            hit = (
                (proper and len(clean) >= 4)
                or len(clean) >= 6
                or (bool(w.get("highlight")) and len(clean) >= 5)
            )
            if not hit:
                continue
            seen.add(low)
            label = clean[:1].upper() + clean[1:] if clean else text
            # Generic bilingual — bare token first for stock APIs
            id_q = f"{clean} close up"
            en_q = clean
            out.append({
                "word": clean,
                "start": round(s, 3),
                "end": round(e, 3),
                "label": label,
                "entity_type": "object",
                "priority": 6 if proper else 5,
                "query_id": id_q,
                "query_en": en_q,
                "search_queries": [clean, id_q, f"{clean} isolated object"],
                "source": "fallback",
            })
            if len(out) >= max(0, int(limit)):
                break
        return out

    async def analyze_broll_for_clips(
        self,
        clips_words: dict[int, list[dict]],
        clip_durations: dict[int, float],
        max_suggestions: int = 99,
        clip_meta: dict | None = None,
        visual_entities: dict | None = None,
    ) -> dict:
        """Recover B-roll per clip (1 LLM call / clip) from word-level transcript.

        Per-clip prompts stay small → better keywords/objects than one mega-batch
        of clip_1…N. Optional clip_meta[rank]={hook,reason} seeds topic lock.
        visual_entities: AI-extracted objects/queries per rank (dynamic, no lexicon).
        Fallback: local words + AI/fallback visual entities.
        """
        max_suggestions = int(max_suggestions) if max_suggestions and int(max_suggestions) > 0 else 99
        if not clips_words:
            return {}

        eligible: dict[int, list[dict]] = {}
        for raw_rank, words in sorted(clips_words.items()):
            rank = int(raw_rank)
            duration = float(clip_durations.get(rank, 0.0) or 0.0)
            # Adaptive pad: short clips still get b-roll (any duration ≥ 1.5s)
            lead = min(3.0, max(0.2, duration * 0.08))
            tail = min(1.0, max(0.2, duration * 0.06))
            clean_words = [
                word
                for word in words
                if lead <= float(word.get("start", -1.0)) < max(lead + 0.1, duration - tail)
                and str(word.get("word") or "").strip()
            ]
            if clean_words and duration >= 1.5:
                eligible[rank] = clean_words
            if not eligible:
                return {}

        meta = clip_meta or {}
        entities = visual_entities or {}
        sem = asyncio.Semaphore(2)

        async def _one(rank: int, words: list[dict]) -> tuple[int, list[dict]]:
            async with sem:
                duration = float(clip_durations.get(rank, 0.0) or 0.0)
                m = meta.get(rank) or meta.get(str(rank)) or {}
                ents = entities.get(rank) or entities.get(str(rank)) or []
                try:
                    items = await self._analyze_broll_one_clip(
                        rank=rank,
                        words=words,
                        duration=duration,
                        max_items=max_suggestions,
                        hook=str(m.get("hook") or ""),
                        reason=str(m.get("reason") or ""),
                        visual_entities=ents,
                    )
                except Exception as exc:
                    logger.warning(
                        "v2_analyzer: per-clip B-roll rank=%s failed: %s", rank, exc
                    )
                    items = []
                if not items:
                    items = self._fallback_broll_from_words(
                        words,
                        duration,
                        limit=min(4, max_suggestions),
                        visual_entities=ents,
                    )
                return rank, items

        logger.info(
            "v2_analyzer: B-roll per-clip recovery model=%s clips=%d",
            self._model_pass1,
            len(eligible),
        )
        pairs = await asyncio.gather(
            *[_one(rank, words) for rank, words in eligible.items()]
        )
        return {str(rank): items for rank, items in pairs if items}

    async def _analyze_broll_one_clip(
        self,
        *,
        rank: int,
        words: list[dict],
        duration: float,
        max_items: int = 99,
        hook: str = "",
        reason: str = "",
        visual_entities: list[dict] | None = None,
    ) -> list[dict]:
        """Single-clip B-roll LLM call — seed from AI visual entities (dynamic)."""
        from src.infrastructure.clip_quality_helpers import extract_highlight_keywords

        max_items = int(max_items) if max_items and int(max_items) > 0 else 99
        # Compact transcript windows (this clip only)
        window_size = 8
        windows = [
            words[i : i + window_size] for i in range(0, len(words), window_size)
        ]
        if len(windows) > 20:
            last = len(windows) - 1
            pick = sorted({round(i * last / 19) for i in range(20)})
            windows = [windows[i] for i in pick]
        lines: list[str] = []
        for window in windows:
            text = " ".join(str(w.get("word") or "").strip() for w in window).strip()
            if text:
                lines.append(f"[{float(window[0]['start']):.2f}s] {text[:260]}")
        context = "\n".join(lines)
        if len(context) > 8000:
            context = context[:8000]

        seeds: list[str] = []
        for e in visual_entities or []:
            if not isinstance(e, dict):
                continue
            for key in ("query_en", "query_id", "label", "word"):
                val = " ".join(str(e.get(key) or "").split())
                if val and val.lower() not in {s.lower() for s in seeds}:
                    seeds.append(val)
            for q in e.get("search_queries") or []:
                q = " ".join(str(q or "").split())
                if q and q.lower() not in {s.lower() for s in seeds}:
                    seeds.append(q)
        for h in extract_highlight_keywords(words, limit=8):
            if h and h.lower() not in {s.lower() for s in seeds}:
                seeds.append(h)
        seed_txt = ", ".join(seeds[:14]) if seeds else "(none — derive from transcript)"
        topic = " | ".join(x for x in (hook.strip(), reason.strip()) if x)[:300]

        prompt = f"""Kamu visual director profesional untuk short clip. Tentukan B-roll visual (baik full_frame stock video maupun behind_person visual/icon) secara bebas dan dinamis sesuai alur narasi transkrip tanpa batasan kaku.

CLIP #{rank} duration={duration:.1f}s
HOOK/TOPIC: {topic or "(n/a)"}
AI VISUAL ENTITIES / SEARCH SEEDS (pakai & refine, jangan hardcode domain list): {seed_txt}

TRANSKRIP BERTIMESTAMP (clip ini saja):
{context}

PLACEMENT:
1) full_frame — stock VIDEO ganti layar (person hilang). visual_category=footage
2) behind_person — IMAGE/icon/footage di belakang person top-half. visual_category=icon|motion_graphic|footage

ATURAN:
- at_time = timestamp dari transkrip di atas; min 3.0s; max duration-1
- full_frame dan behind_person TIDAK boleh waktu sama (min jarak 4s)
- Tentukan jumlah B-roll visual sebanyak yang dibutuhkan narasi cerita secara dinamis.
- keyword = ENGLISH stock query 3-8 kata, KONKRET visual dari konteks clip ini (boleh refine seed di atas)
  JELEK: abstract mood "success", "lifestyle", "viral", "city skyline generic"
  behind_person: CLOSE-UP object fill-frame (bukan wide landscape)
- duration 1.5-3.0; min jarak 3.5s antar item placement sama
- placement + visual_category + template wajib
- Analisa dinamis dari transkrip — jangan andalkan daftar kata domain tetap

OUTPUT RAW JSON:
{{"items":[{{"at_time":12.5,"keyword":"concrete stock query from this clip","duration":2.5,"visual_category":"footage","placement":"full_frame","template":"word_pop_typography"}},{{"at_time":22.0,"keyword":"another concrete closeup object","duration":2.0,"visual_category":"footage","placement":"behind_person","template":"word_pop_typography"}}]}}
"""
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(
                    self._call_groq_llm,
                    prompt,
                    self._model_pass1,
                    1600,
                ),
                timeout=self._timeout,
            )
            parsed = self._parse_json_response(raw)
        except Exception as exc:
            logger.warning("v2_analyzer: B-roll clip %s LLM fail: %s", rank, exc)
            return []

        raw_items = []
        if isinstance(parsed, dict):
            if isinstance(parsed.get("items"), list):
                raw_items = parsed["items"]
            else:
                clips_map = parsed.get("clips") or {}
                if isinstance(clips_map, dict):
                    raw_items = clips_map.get(str(rank), clips_map.get(rank, []))
        if not isinstance(raw_items, list):
            return []
        return self._normalize_broll_items(
            raw_items, words=words, duration=duration, max_items=max_items
        )

    def _normalize_broll_items(
        self,
        raw_items: list,
        *,
        words: list[dict],
        duration: float,
        max_items: int = 99,
    ) -> list[dict]:
        """Anchor AI broll rows to real word timestamps + sanitize keywords."""
        allowed_templates = {
            "word_pop_typography",
            "line_reveal_typography",
            "particle_text_burst",
        }
        allowed_categories = {"footage", "icon", "motion_graphic", "reaction"}
        allowed_times = [float(w["start"]) for w in words if "start" in w]
        if not allowed_times:
            return []
        items: list[dict] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            raw_kw = " ".join(str(item.get("keyword") or "").split())[:80]
            keyword = (
                sanitize_stock_keyword(raw_kw, placement=str(item.get("placement") or ""))
                or raw_kw
            )
            if not keyword:
                continue
            try:
                requested_time = float(item.get("at_time"))
            except (TypeError, ValueError):
                continue
            at_time = min(allowed_times, key=lambda value: abs(value - requested_time))
            lead = min(3.0, max(0.2, duration * 0.08))
            tail = min(1.0, max(0.2, duration * 0.06))
            if at_time < lead or at_time >= max(lead + 0.1, duration - tail):
                continue
            if any(abs(at_time - existing["at_time"]) < min(3.5, max(1.5, duration * 0.12)) for existing in items):
                continue
            try:
                item_duration = float(item.get("duration", 2.25))
            except (TypeError, ValueError):
                item_duration = 2.25
            max_hold = min(3.5, max(0.8, duration * 0.35))
            item_duration = min(max_hold, max(0.8, item_duration), duration - at_time)
            if item_duration < 0.6:
                continue
            template = str(item.get("template") or "word_pop_typography")
            category = str(item.get("visual_category") or "footage")
            if category not in allowed_categories:
                category = "footage"
            placement = str(item.get("placement") or "").strip().lower()
            if placement in {"fullframe", "splice", "replace"}:
                placement = "full_frame"
            elif placement in {"behind", "top_overlay", "overlay", "top"}:
                placement = "behind_person"
            elif placement not in {"full_frame", "behind_person"}:
                placement = (
                    "behind_person"
                    if category in {"icon", "motion_graphic"}
                    else "full_frame"
                )
            # dual-track: avoid same placement stack < 3.5s
            if any(
                e["placement"] == placement and abs(at_time - e["at_time"]) < 3.5
                for e in items
            ):
                continue
            items.append({
                "at_time": round(at_time, 3),
                "keyword": keyword,
                "duration": round(item_duration, 3),
                "visual_category": category,
                "template": template if template in allowed_templates else "word_pop_typography",
                "placement": placement,
            })
            if max_items and len(items) >= max_items:
                break
        return items

    @staticmethod
    def _fallback_broll_from_words(
        words: list[dict],
        duration: float,
        limit: int = 1,
        visual_entities: list[dict] | None = None,
    ) -> list[dict]:
        """Pick sparse concrete phrases when AI broll call is down.

        Prefer AI visual_entities (dynamic queries). No domain synonym maps.
        """
        selected: list[dict] = []
        # 1) AI visual entities first (already have query_en) — no stopword list
        for o in visual_entities or []:
            if not isinstance(o, dict):
                continue
            try:
                start = float(o.get("start", 0) or 0)
            except (TypeError, ValueError):
                start = 0.0
            lead = min(3.0, max(0.2, duration * 0.08)) if duration > 0 else 0.2
            tail = min(1.0, max(0.2, duration * 0.06)) if duration > 0 else 0.2
            if start < lead or (duration > 0 and start >= duration - tail):
                start = max(lead, min(duration * 0.35, max(lead, duration - max(1.0, tail + 0.5)))) if duration > 1.5 else lead
            kw = (
                " ".join(str(o.get("query_en") or o.get("query_id") or o.get("word") or "").split())
            )
            if not kw:
                continue
            if any(abs(start - item["at_time"]) < min(8.0, max(1.5, duration * 0.2)) for item in selected):
                continue
            kw = sanitize_stock_keyword(kw, placement="behind_person") or kw
            placement = "behind_person" if len(selected) % 2 else "full_frame"
            hold = min(2.25, max(0.8, duration - start - 0.1)) if duration > 0 else 1.5
            selected.append({
                "at_time": round(start, 3),
                "keyword": kw[:80],
                "duration": round(hold, 3),
                "visual_category": "footage",
                "template": "word_pop_typography",
                "placement": placement,
            })
            if len(selected) >= max(0, int(limit)):
                return sorted(selected, key=lambda item: item["at_time"])

        content_words: list[tuple[int, str, float]] = []
        lead = min(3.0, max(0.2, duration * 0.08)) if duration > 0 else 0.2
        tail = min(1.0, max(0.2, duration * 0.06)) if duration > 0 else 0.2
        for index, word in enumerate(words):
            raw = str(word.get("word") or "").strip()
            token = re.sub(r"[^0-9A-Za-zÀ-ÿ]+", "", raw).lower()
            try:
                start = float(word.get("start", -1.0))
            except (TypeError, ValueError):
                continue
            if start < lead or start >= max(lead + 0.1, duration - tail):
                continue
            # Offline only: length gate. No hardcoded stop/mood lexicon —
            # primary path is AI visual_entities above.
            if len(token) < 4:
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

        for _score, start, keyword in sorted(candidates, reverse=True):
            if any(abs(start - item["at_time"]) < min(8.0, max(1.5, duration * 0.2)) for item in selected):
                continue
            placement = "behind_person" if len(selected) % 2 else "full_frame"
            hold = min(2.25, max(0.8, duration - start - 0.1)) if duration > 0 else 1.5
            selected.append({
                "at_time": round(start, 3),
                "keyword": keyword[:80],
                "duration": round(hold, 3),
                "visual_category": "footage",
                "template": "word_pop_typography",
                "placement": placement,
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
        """Per-clip cinematic text via 9router (1 LLM call / clip).

        Avoids one mega multi-clip prompt — each clip keeps full word IDs in a
        small context window. Model picks Whisper word IDs only; local anchor
        rebuilds text/timing + spacing rules.
        """
        if max_events <= 0 or not any(clips_words.values()):
            return {}

        safe_style = normalise_text_emphasis_style(style)
        max_ev = min(2, int(max_events))
        eligible = {
            int(rank): words
            for rank, words in clips_words.items()
            if words and any(str(w.get("word") or "").strip() for w in words)
        }
        if not eligible:
            return {}

        model = (
            settings.NINE_ROUTER_AI_LAYER_MODEL
            if settings.use_nine_router
            else self._model_pass1
        )
        sem = asyncio.Semaphore(2)
        logger.info(
            "v2_analyzer: text emphasis per-clip model=%s clips=%d",
            model,
            len(eligible),
        )

        async def _one(rank: int, words: list[dict]) -> tuple[int, list[dict]]:
            async with sem:
                single_words = {rank: words}
                single_durs = {rank: float(clip_durations.get(rank, 0.0) or 0.0)}
                single_min = {
                    rank: (min_start_by_clip or {}).get(rank, 1.0)
                }
                single_blocked = {
                    rank: (blocked_ranges_by_clip or {}).get(rank, [])
                }
                try:
                    parsed = await self._analyze_text_emphasis_one_clip(
                        rank=rank,
                        words=words,
                        style=safe_style,
                        model=model,
                        max_events=max_ev,
                    )
                except Exception as exc:
                    logger.warning(
                        "v2_analyzer: text emphasis rank=%s failed: %s", rank, exc
                    )
                    parsed = {}
                anchored = anchor_text_emphasis_response(
                    parsed or {},
                    single_words,
                    single_durs,
                    style=safe_style,
                    min_start_by_clip=single_min,
                    blocked_ranges_by_clip=single_blocked,
                    max_events=max_ev,
                )
                return rank, list(anchored.get(rank, []))

        pairs = await asyncio.gather(
            *[_one(rank, words) for rank, words in eligible.items()]
        )
        return {rank: events for rank, events in pairs if events}

    async def _analyze_text_emphasis_one_clip(
        self,
        *,
        rank: int,
        words: list[dict],
        style: dict,
        model: str,
        max_events: int = 2,
    ) -> dict:
        """Single-clip text-emphasis LLM; full words first, sampled fallback."""
        effect_instruction = (
            "Pilih effect paling cocok dari: depth_cutout, hero_punch, side_rail, "
            "float_track, smart_gap, orbit_halo, z_parallax, word_cascade, "
            "split_impact, type_pulse, sticker_pop, mirror_echo."
            if style.get("effectMode") == "auto"
            else f'Semua pilihan WAJIB memakai effect "{style.get("effectMode")}".'
        )
        # Prefer highlight seeds so AI locks onto punch words
        from src.infrastructure.clip_quality_helpers import extract_highlight_keywords
        seeds = extract_highlight_keywords(words, limit=8)
        seed_txt = ", ".join(seeds[:8]) if seeds else "(none)"

        context, _ = build_text_emphasis_context_full({rank: words})
        if not context:
            return {}

        # Cap very long clips — keep word IDs, just truncate section tail
        if len(context) > 10000:
            context = context[:10000]

        prompt = f"""Kamu senior motion editor 1 short clip. Pilih frasa cinematic text.

CLIP #{rank} saja. SEED HIGHLIGHT: {seed_txt}

TRANSKRIP WORD-ID (clip ini):
{context}

ATURAN:
- WAJIB 1–{max_events} event. Frasa 1-7 kata; start_word+end_word berurutan.
- Prioritas: angka, tesis, kontras, istilah inti, punchline. Hindari filler.
- Min jarak 6s antar event.
- Effects: depth_cutout | hero_punch | side_rail | float_track | smart_gap | orbit_halo | z_parallax | word_cascade | split_impact | type_pulse | sticker_pop | mirror_echo
- {effect_instruction}
- position: left | center | right
- Jangan rewrite teks / timestamp — pilih word ID saja.

OUTPUT RAW JSON:
{{"clips":{{"{rank}":[{{"start_word":"W0012","end_word":"W0015","effect":"hero_punch","position":"center","reason":"tesis"}}]}}}}
"""
        parsed = None
        last_error = None
        for attempt in range(2):
            try:
                raw = await asyncio.wait_for(
                    asyncio.to_thread(self._call_groq_llm, prompt, model, 1200),
                    timeout=self._timeout,
                )
                parsed = self._parse_json_response(raw)
                if parsed:
                    return parsed
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "v2_analyzer: text emphasis clip %s attempt %s/2: %s",
                    rank, attempt + 1, exc,
                )
                if attempt < 1:
                    await asyncio.sleep(2)

        # Sampled fallback for this clip only
        logger.warning(
            "v2_analyzer: text emphasis clip %s full fail (%s), sampled fallback",
            rank, last_error,
        )
        try:
            fallback_context, _ = build_text_emphasis_context({rank: words})
            if not fallback_context:
                return {}
            fallback_prompt = f"""Kamu senior motion editor 1 short clip. Pilih frasa cinematic.

CLIP #{rank}. SEED: {seed_txt}

TRANSKRIP WORD-ID (sampled):
{fallback_context}

ATURAN: 1–{max_events} event; frasa 1-7 kata; start/end word ID berurutan; jangan span [... gap ...].
Effects: depth_cutout|hero_punch|side_rail|float_track|smart_gap|orbit_halo|z_parallax|word_cascade|split_impact|type_pulse|sticker_pop|mirror_echo
{effect_instruction}
position: left|center|right. Jangan rewrite teks.

OUTPUT RAW JSON:
{{"clips":{{"{rank}":[{{"start_word":"W0012","end_word":"W0015","effect":"hero_punch","position":"center","reason":"angka"}}]}}}}
"""
            raw = await asyncio.wait_for(
                asyncio.to_thread(self._call_groq_llm, fallback_prompt, model, 1000),
                timeout=self._timeout,
            )
            return self._parse_json_response(raw) or {}
        except Exception as exc:
            logger.warning(
                "v2_analyzer: text emphasis clip %s sampled fallback failed: %s",
                rank, exc,
            )
            return {}

    async def _analyze_highlights_impl(
        self, transcript: TranscriptResult, video_duration: float, max_clips: int
    ) -> HighlightAnalysisResult:
        """Internal implementation (called within semaphore context)."""
        t_start = time.perf_counter()

        # Calibrate video_duration from transcript if provided duration is smaller than transcript bounds
        if transcript and transcript.segments:
            max_seg_end = max((float(s.end) for s in transcript.segments if getattr(s, 'end', None) is not None), default=0.0)
            if max_seg_end > video_duration:
                logger.info(f"v2_analyzer: calibrating video_duration from {video_duration:.1f}s to {max_seg_end:.1f}s based on transcript")
                video_duration = max_seg_end

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

        # Recovery: too few candidates vs target → diversify via alternate angles
        if len(all_candidates) < max(2, max_clips):
            logger.warning(
                f"v2_analyzer: low candidates ({len(all_candidates)} < target {max_clips}) "
                "→ diversify recovery pass"
            )
            recovered = self._diversify_low_candidates(
                all_candidates, transcript.segments, segment_map, max_clips, video_duration
            )
            if recovered:
                all_candidates = recovered
                metrics.pass1_candidates_total = len(all_candidates)
                logger.info(
                    f"v2_analyzer: diversify recovery → {len(all_candidates)} candidates"
                )

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

                # Apply overlap: rewind by CHUNK_OVERLAP_SECONDS (capped at half the
                # chunk limits so a rewind can never consume the entire chunk budget,
                # which would produce near-duplicate oversized chunks that exceed
                # the char/time limits)
                overlap_segments = []
                overlap_duration = 0.0
                overlap_chars = 0
                max_overlap_dur = min(self.CHUNK_OVERLAP_SECONDS, self._chunk_max_seconds / 2)
                max_overlap_chars = self._chunk_max_chars / 2
                for s in reversed(current_segments):
                    s_dur = s.end - s.start
                    s_chars = len(s.text)
                    if (
                        overlap_duration + s_dur > max_overlap_dur
                        or overlap_chars + s_chars > max_overlap_chars
                    ):
                        break
                    overlap_segments.insert(0, s)
                    overlap_duration += s_dur
                    overlap_chars += s_chars

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
2. "start_id" = Segment ID di mana clip MULAI — WAJIB di awal kalimat/ucapan lengkap (bukan di tengah kata/kalimat)
3. "end_id" = Segment ID di mana clip BERAKHIR — WAJIB di akhir kalimat penutup yang natural (bukan potong di tengah bicara)
4. Durasi clip MINIMUM 45 detik. Clip harus self-contained: satu unit bicara lengkap dari pembuka sampai penutup. Boleh lebih dari 90 detik jika topik belum tuntas.
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
3. Prioritaskan clip yang bisa berdiri sendiri (self-contained) — mulai di awal kalimat, berakhir di akhir kalimat, tidak potong di tengah ucapan
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

    def _diversify_low_candidates(
        self,
        candidates: list[HighlightCandidate],
        segments: list[TranscriptSegment],
        segment_map: dict,
        max_clips: int,
        video_duration: float,
    ) -> list[HighlightCandidate]:
        """When Pass1 under-delivers, seed alternate story/conflict/punchline windows.

        Deterministic (no extra LLM): split transcript into windows, score keyword
        density, keep non-overlapping slices until target*1.5 or end.
        """
        if not segments or video_duration <= 0:
            return candidates

        min_dur = float(getattr(self, "MIN_CLIP_DURATION", 45.0) or 45.0)
        max_dur = float(getattr(self, "MAX_CLIP_DURATION", 90.0) or 90.0)
        target_n = max(max_clips, 2)
        want = max(target_n, min(target_n * 2, 6))

        # Angles: story open / conflict / punchline / energy words
        angle_terms = {
            "story": ("cerita", "dulu", "awal", "pertama", "mulai", "waktu itu"),
            "conflict": ("tapi", "padahal", "masalah", "salah", "marah", "ribut", "konflik"),
            "punchline": ("ternyata", "akhirnya", "hasilnya", "gila", "wah", "banget"),
            "money": ("uang", "harga", "mahal", "rupiah", "bbm", "gaji", "utang"),
        }
        windows: list[HighlightCandidate] = list(candidates)
        used = [(c.start, c.end) for c in candidates]

        def overlaps(a0: float, a1: float) -> bool:
            return any(not (a1 <= b0 or a0 >= b1) for b0, b1 in used)

        # Build rolling windows of ~min_dur from segment starts
        n = len(segments)
        step = max(1, n // max(4, want))
        for i in range(0, n, step):
            s0 = segments[i]
            # extend until min_dur
            j = i
            while j + 1 < n and (segments[j].end - s0.start) < min_dur:
                j += 1
            end_t = min(video_duration, max(segments[j].end, s0.start + min_dur))
            start_t = max(0.0, s0.start)
            if end_t - start_t < min_dur * 0.85:
                continue
            if end_t - start_t > max_dur:
                end_t = start_t + max_dur
            if overlaps(start_t, end_t):
                continue
            blob = " ".join(
                segments[k].text for k in range(i, min(n, j + 1))
            ).lower()
            best_angle = "story"
            best_hits = 0
            for ang, terms in angle_terms.items():
                hits = sum(1 for t in terms if t in blob)
                if hits > best_hits:
                    best_hits = hits
                    best_angle = ang
            score = 55 + min(25, best_hits * 5)
            # Prefer mid/late video slightly for punch
            if start_t > video_duration * 0.4:
                score += 5
            windows.append(
                HighlightCandidate(
                    rank=0,
                    start=start_t,
                    end=end_t,
                    score=score,
                    hook=blob[:80].strip() or f"Momen {best_angle}",
                    reason=f"diversify:{best_angle}",
                    content_type=best_angle,
                    speaker_energy="medium",
                    hook_alt="",
                )
            )
            used.append((start_t, end_t))
            if len(windows) >= want:
                break

        # Dedup by time then keep highest scores
        windows.sort(key=lambda c: c.score, reverse=True)
        out: list[HighlightCandidate] = []
        kept: list[tuple[float, float]] = []
        for c in windows:
            if any(not (c.end <= a or c.start >= b) for a, b in kept):
                continue
            out.append(c)
            kept.append((c.start, c.end))
            if len(out) >= want:
                break
        return out if len(out) > len(candidates) else candidates

    # ─── Validation Safety Net ────────────────────────────────────────────────

    def _validate_final_clips(
        self, clips: list[HighlightCandidate], video_duration: float
    ) -> list[HighlightCandidate]:
        """Final safety net: validate all clips before returning to caller.

        Checks:
        - start < end
        - duration within MIN/MAX bounds
        - timestamps within video bounds (0 to effective_duration)
        - score within 1-100
        - hook is non-empty string
        """
        validated = []
        max_clip_end = max((float(c.end) for c in clips if getattr(c, 'end', None) is not None), default=video_duration)
        effective_duration = max(video_duration, max_clip_end)

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

            # Timestamps within video bounds (with 2s tolerance)
            if clip.start < -1.0 or clip.end > effective_duration + 2.0:
                logger.warning(
                    f"v2_analyzer: validate reject clip (out of video bounds): "
                    f"{clip.start:.0f}-{clip.end:.0f} (video={effective_duration:.0f}s)"
                )
                continue

            # Clamp to video bounds
            clip.start = max(0.0, clip.start)
            clip.end = min(effective_duration, clip.end)

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
        """Generate job-level creative direction only (colors/mood).

        B-roll keywords are planned later per-clip from word-level transcript
        (analyze_broll_for_clips) — multi-clip batch here was too coarse.
        """
        clips_context = "\n".join([
            f"  Clip {c.rank}: [{c.start:.0f}s → {c.end:.0f}s] "
            f"score={c.score}, type={c.content_type}, energy={c.speaker_energy}\n"
            f"    Hook: \"{c.hook}\"\n    Alasan: {c.reason}"
            for c in clips
        ])

        prompt = f"""Kamu adalah visual director viral shorts. Tentukan CREATIVE DIRECTION konsisten untuk SEMUA clips.

═══ CLIP TERPILIH ═══
{clips_context}

Tugas — visual identity saja (bukan B-roll):
- primary_color: hex aksen utama
- secondary_color: hex highlight
- background_accent: hex tint gelap
- typography_mood: "bold_impact" / "elegant_minimal" / "playful" / "dramatic"
- energy_level: "high" / "medium" / "chill"
- transition_style: "fast_cuts" / "smooth" / "kinetic"
- music_mood: "energetic" / "chill" / "dramatic" / "suspense"
- hook_animation: "fade_scale" / "slide_up" / "glitch" / "typewriter"

OUTPUT RAW JSON (tanpa markdown):
{{"creative_direction": {{"primary_color": "#FFFFFF", "secondary_color": "#FFD700", "background_accent": "#000000", "typography_mood": "bold_impact", "energy_level": "high", "transition_style": "fast_cuts", "music_mood": "energetic", "hook_animation": "fade_scale"}}, "broll_suggestions": {{}}}}"""

        raw = self._call_groq_llm(prompt, model=self._model_pass1)
        parsed = self._parse_json_response(raw)
        if not isinstance(parsed, dict):
            return {"creative_direction": {}, "broll_suggestions": {}}
        # Force empty broll here — filled later per-clip after Whisper
        parsed["broll_suggestions"] = {}
        return parsed

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

    def _extract_json_candidate(self, text: str) -> Optional[str]:
        """Pull JSON object from text. Does NOT require a closing brace.

        LLM responses are often truncated mid-object (`{"clips":[{...`), so a
        greedy `\\{.*\\}` regex falsely reports 'no JSON object found'. Prefer the
        first `{` slice; fall back to balanced `{...}` when present.
        """
        start = text.find("{")
        if start < 0:
            return None
        # Prefer complete outermost object when both braces exist
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match and match.start() == start:
            return match.group(0)
        # Truncated / unclosed — take everything from first `{`
        return text[start:]

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
        # Smart/curly quotes → plain (some providers emit these)
        text = (
            text.replace("\u201c", '"').replace("\u201d", '"')
            .replace("\u2018", "'").replace("\u2019", "'")
        )

        # First attempt: direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        candidate = self._extract_json_candidate(text)
        if not candidate:
            logger.warning(
                f"v2_analyzer: failed to parse JSON (no JSON object found): {text[:200]}"
            )
            return {}

        json_str = self._clean_json_string(candidate)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        repaired = self._repair_truncated_json(json_str)
        if repaired:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError as e:
                logger.warning(
                    f"v2_analyzer: JSON parse failed after repair: {e}\nRaw: {json_str[:200]}"
                )
        else:
            logger.warning(
                f"v2_analyzer: JSON parse failed after cleanup: truncated\nRaw: {json_str[:200]}"
            )

        return {}

    def _repair_truncated_json(self, json_str: str) -> Optional[str]:
        """Attempt to repair truncated JSON from LLM max_tokens cutoff.

        Common patterns:
        - {"clips": [{"start_id": "S0275", ...}, {"start_id": "S0300", ...   (cut off)
        - Missing closing brackets/braces (no `}` at all in the payload)
        - Cut mid-string value

        Strategy: keep last complete object when possible; else close open
        string + nest (stack order). Never require a pre-existing `}`.
        """
        open_braces = json_str.count("{") - json_str.count("}")
        open_brackets = json_str.count("[") - json_str.count("]")
        if open_braces == 0 and open_brackets == 0 and json_str.count('"') % 2 == 0:
            return None  # Not a truncation issue

        # Prefer last complete object in array
        last_complete = json_str.rfind("},")
        if last_complete == -1:
            last_complete = json_str.rfind("}")

        if last_complete != -1:
            candidate = json_str[: last_complete + 1]
            closed = self._close_json_structure(candidate)
            if closed is not None:
                return closed

        # No usable complete object — close mid-stream payload as-is
        return self._close_json_structure(json_str)

    def _close_json_structure(self, s: str) -> Optional[str]:
        """Close unclosed strings and nest braces/brackets in reverse order."""
        stack: list[str] = []
        in_string = False
        escape = False
        for ch in s:
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                stack.append("}")
            elif ch == "[":
                stack.append("]")
            elif ch in "}]":
                if stack and stack[-1] == ch:
                    stack.pop()
                else:
                    return None

        out = s
        if in_string:
            out += '"'  # close truncated string value
        # stack holds closers outer→inner; reverse to close inner first
        out += "".join(reversed(stack))
        return out

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
