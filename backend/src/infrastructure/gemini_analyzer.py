"""GeminiAnalyzer — Multi-phase YouTube video analysis via Gemini.

v2.0 Decomposed Analysis:
  Phase 1 (video): Clip selection + scoring + creative direction
  Phase 2 (text):  Hook refinement + b-roll placement per clip

This decomposition improves output quality because each call has a focused task.
Phase 1 requires video understanding (expensive). Phase 2 is text-only (cheap & fast).
"""
import asyncio
import json
import logging
import time
from typing import Optional

from google import genai
from google.genai import types

from src.config import settings
from src.domain.interfaces import IGeminiAnalyzer

logger = logging.getLogger(__name__)

RETRY_DELAYS = [5, 15, 30]
MAX_RETRIES = 3


class GeminiAnalyzer(IGeminiAnalyzer):
    def __init__(self):
        from src.infrastructure.auth import GeminiKeyRotator
        self._key_rotator = GeminiKeyRotator()
        self._model = settings.GEMINI_MODEL
        self._fallback_model = settings.GEMINI_FALLBACK_MODEL
        self._using_fallback = False
        self._consecutive_503 = 0
        self._client = None
        self._init_client()

    def _switch_to_fallback(self) -> None:
        """Switch to fallback model after repeated 503 errors."""
        if not self._using_fallback and self._fallback_model and self._fallback_model != self._model:
            logger.warning(f"Switching from {self._model} → {self._fallback_model} (repeated 503)")
            self._model = self._fallback_model
            self._using_fallback = True
            self._consecutive_503 = 0

    def _init_client(self) -> None:
        key = self._key_rotator.get_current_key()
        if key:
            self._client = genai.Client(api_key=key)
        else:
            self._client = None

    async def analyze(
        self, video_url: str, video_duration: float, max_clips: int
    ) -> dict:
        """Multi-phase video analysis.

        Phase 1: Video understanding → clip candidates + creative direction
        Phase 2: Text refinement → optimized hooks + b-roll placement

        Returns combined result dict.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._analyze_multi_phase, video_url, video_duration, max_clips
        )

    # ─── Multi-Phase Analysis ─────────────────────────────────────────────────

    def _analyze_multi_phase(self, video_url: str, video_duration: float, max_clips: int) -> dict:
        """Run decomposed multi-phase analysis."""

        # ═══ Phase 1: Video Understanding (clip selection + creative direction) ═══
        logger.info("gemini_phase_1: clip selection + creative direction")
        phase1_result = self._phase1_clip_selection(video_url, video_duration, max_clips)

        if not phase1_result or "clips" not in phase1_result:
            raise RuntimeError("Gemini Phase 1 gagal: tidak ada clips")

        clips = phase1_result["clips"]
        creative_direction = phase1_result.get("creative_direction", {})
        logger.info(f"gemini_phase_1: {len(clips)} clips found, creative_direction={bool(creative_direction)}")

        # ═══ Phase 2: Creative Enrichment (hooks + b-roll) — text-only, cheap ═══
        logger.info("gemini_phase_2: hook refinement + b-roll placement")
        try:
            phase2_result = self._phase2_creative_enrichment(clips, video_duration)
            if phase2_result:
                # Merge phase 2 into phase 1 results
                enriched_clips = phase2_result.get("clips", [])
                broll_suggestions = phase2_result.get("broll_suggestions", {})

                # Update hooks from phase 2 (better quality due to focused prompt)
                for ec in enriched_clips:
                    rank = ec.get("rank")
                    for clip in clips:
                        if clip.get("rank") == rank:
                            if ec.get("hook"):
                                clip["hook"] = ec["hook"]
                            if ec.get("hook_alt"):
                                clip["hook_alt"] = ec["hook_alt"]
                            break

                phase1_result["broll_suggestions"] = broll_suggestions
                logger.info(f"gemini_phase_2: enriched {len(enriched_clips)} clips, {len(broll_suggestions)} broll maps")
        except Exception as e:
            logger.warning(f"gemini_phase_2 failed (non-critical, using phase1 hooks): {e}")
            # Phase 2 failure is non-critical — phase 1 already has basic hooks
            if "broll_suggestions" not in phase1_result:
                phase1_result["broll_suggestions"] = {}

        phase1_result["creative_direction"] = creative_direction
        return phase1_result

    # ─── Phase 1: Clip Selection (Video Understanding) ────────────────────────

    def _phase1_clip_selection(self, video_url: str, video_duration: float, max_clips: int) -> dict:
        """Phase 1: Watch video → select best viral moments + define visual style.

        This is the expensive call (processes video). Focused on:
        - Finding the BEST moments (timestamps + scoring)
        - Understanding the video's mood/tone (creative direction)
        - Initial hook suggestions (will be refined in phase 2)
        """
        prompt = f"""Kamu adalah AI analis video viral profesional. Tonton video ini dan analisis secara mendalam.

DURASI VIDEO: {video_duration:.1f} detik
TARGET: Temukan maksimal {max_clips} momen PALING VIRAL (durasi 45-90 detik per klip).

═══ TUGAS 1: CLIP SELECTION ═══
Identifikasi momen-momen yang:
- Punya kekuatan emosional tinggi
- Bisa berdiri sendiri tanpa konteks tambahan
- Memicu komentar/share
- Punya struktur cerita utuh (premis → konklusi)

ATURAN:
- Klip TIDAK BOLEH OVERLAP
- 'start' = awal kalimat baru (jangan potong di tengah)
- 'end' = setelah kalimat selesai utuh (+1 detik toleransi)
- Skor 1-100 berdasarkan potensi viral

═══ TUGAS 2: CREATIVE DIRECTION ═══
Tentukan visual identity berdasarkan tone video:
- primary_color: warna utama aksen (hex, pilih yang cocok dengan mood)
- secondary_color: warna highlight/emphasis (hex)
- background_accent: warna tint overlay (hex gelap)
- typography_mood: "bold_impact" / "elegant_minimal" / "playful" / "dramatic"
- energy_level: "high" / "medium" / "chill"
- transition_style: "fast_cuts" / "smooth" / "kinetic"
- music_mood: "energetic" / "chill" / "dramatic" / "suspense"
- hook_animation: "fade_scale" / "slide_up" / "glitch" / "typewriter"

═══ TUGAS 3: INITIAL HOOKS ═══
Untuk setiap clip, buat hook text:
- Maksimal 60 karakter
- Bahasa SAMA dengan video
- Brutal, singkat, bikin jempol berhenti
- OPEN LOOP (picu penasaran, jangan spoiler)

OUTPUT FORMAT — RAW JSON (tanpa markdown):
{{"clips": [{{"rank": 1, "score": <int>, "start": <float>, "end": <float>, "hook": "<max 60 char>", "reason": "<alasan singkat>", "content_type": "<storytelling/tutorial/rant/debate>", "speaker_energy": "<high/medium/low>"}}], "creative_direction": {{"primary_color": "<hex>", "secondary_color": "<hex>", "background_accent": "<hex>", "typography_mood": "<mood>", "energy_level": "<level>", "transition_style": "<style>", "music_mood": "<mood>", "hook_animation": "<anim>"}}}}"""

        result = self._call_with_retry(video_url, prompt)
        return self._parse_response(result)

    # ─── Phase 2: Creative Enrichment (Text-Only, Cheap) ──────────────────────

    def _phase2_creative_enrichment(self, clips: list[dict], video_duration: float) -> dict:
        """Phase 2: Refine hooks + generate b-roll suggestions.

        This is a TEXT-ONLY call (no video processing). Much cheaper and faster.
        Takes the clip timestamps and context from Phase 1, and focuses purely on:
        - Better hook alternatives
        - Precise b-roll keyword/timing placement
        """
        # Build context from phase 1 clips
        clips_context = "\n".join([
            f"  Clip {c['rank']}: [{c['start']:.1f}s → {c['end']:.1f}s] "
            f"score={c.get('score', 0)}, content={c.get('content_type', 'unknown')}, "
            f"energy={c.get('speaker_energy', 'medium')}\n"
            f"    Hook saat ini: \"{c.get('hook', '')}\"\n"
            f"    Alasan: {c.get('reason', '')}"
            for c in clips
        ])

        prompt = f"""Kamu adalah copywriter viral dan motion graphics director. Tugasmu SPESIFIK:

═══ KONTEKS ═══
Video berdurasi {video_duration:.1f} detik telah dianalisis. Berikut clip yang terpilih:
{clips_context}

═══ TUGAS 1: HOOK REFINEMENT ═══
Untuk SETIAP clip, buat hook yang LEBIH BAIK dari versi saat ini:
- Lebih brutal dan clickbait
- Tetap di bawah 60 karakter
- Bahasa yang sama
- Beri juga hook_alt (versi alternatif)

═══ TUGAS 2: B-ROLL TYPOGRAPHY PLACEMENT ═══
Untuk SETIAP clip, tentukan 1-2 momen di mana motion typography harus muncul:
- "at_time": offset DALAM clip (detik dari awal clip, bukan dari awal video)
- "keyword": kata/angka kunci yang ditampilkan (MAKS 20 karakter, UPPERCASE)
- "template": "word_pop_typography" / "line_reveal_typography" / "particle_text_burst"
- "duration": 1.5 - 3.0 detik
- "visual_category": "footage" / "icon" / "motion_graphic" / "reaction"

PANDUAN VISUAL_CATEGORY:
- "footage": Tempat, aktivitas, objek fisik → video footage nyata
- "icon": Konsep abstrak, simbol, topik umum → icon/ikon vektor
- "motion_graphic": Data, angka, statistik, proses → animasi grafis
- "reaction": Ekspresi emosi, humor, surprise → sticker animasi

TIPS B-ROLL PLACEMENT:
- Tempatkan di momen paling impactful (angka, nama tempat, frasa kunci)
- Jangan di 3 detik pertama (area hook)
- Jangan di akhir clip (biar ending clean)
- Keyword harus memperkuat apa yang sedang dibicarakan

OUTPUT FORMAT — RAW JSON (tanpa markdown):
{{"clips": [{{"rank": 1, "hook": "<refined hook>", "hook_alt": "<alternative hook>"}}], "broll_suggestions": {{"1": [{{"at_time": <float>, "keyword": "<UPPERCASE>", "template": "<template>", "duration": <float>, "visual_category": "<category>"}}]}}}}"""

        result = self._call_text_only(prompt)
        return self._parse_response(result)

    # ─── API Call Methods ─────────────────────────────────────────────────────

    def _call_with_retry(self, video_url: str, prompt: str) -> str:
        """Call Gemini with YouTube URL as video content + text prompt."""
        for attempt in range(MAX_RETRIES):
            try:
                if not self._client:
                    self._init_client()
                if not self._client:
                    raise RuntimeError("No Gemini API key configured")

                response = self._generate_with_video(video_url, prompt, timeout=300)
                if response and response.text:
                    return response.text
                raise ValueError("Respons Gemini kosong")

            except TimeoutError:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Gemini attempt {attempt + 1} timeout. Retry...")
                    self._key_rotator.mark_rate_limited()
                    self._init_client()
                    continue
                raise RuntimeError("Gemini timeout setelah semua percobaan")

            except Exception as e:
                error_str = str(e).lower()

                if "api key" in error_str or "permission" in error_str:
                    raise RuntimeError(f"Gemini auth error: {e}")

                if "429" in error_str or "rate" in error_str or "quota" in error_str:
                    self._key_rotator.mark_rate_limited()
                    self._init_client()
                    logger.warning(f"Gemini rate limited, rotated to key[{self._key_rotator.current_index}]")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
                        continue

                if "503" in error_str or "unavailable" in error_str:
                    self._consecutive_503 += 1
                    if self._consecutive_503 >= 3:
                        self._switch_to_fallback()

                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(f"Gemini attempt {attempt + 1} failed: {e}. Retry {delay}s...")
                    time.sleep(delay)
                else:
                    raise RuntimeError(f"Gemini gagal setelah {MAX_RETRIES} percobaan: {e}")

    def _call_text_only(self, prompt: str) -> str:
        """Call Gemini with text-only prompt (no video, much cheaper/faster)."""
        for attempt in range(2):  # Fewer retries for text-only
            try:
                if not self._client:
                    self._init_client()
                if not self._client:
                    raise RuntimeError("No Gemini API key configured")

                response = self._client.models.generate_content(
                    model=self._model,
                    contents=[types.Part.from_text(text=prompt)],
                )
                if response and response.text:
                    return response.text
                raise ValueError("Respons Gemini kosong (text-only)")

            except Exception as e:
                if "429" in str(e).lower() or "rate" in str(e).lower():
                    self._key_rotator.mark_rate_limited()
                    self._init_client()
                if attempt == 0:
                    time.sleep(3)
                    continue
                raise

    def _generate_with_video(self, video_url: str, prompt: str, timeout: int = 300):
        """Send YouTube URL + prompt to Gemini. Gemini processes the video directly."""
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        def _call():
            contents = [
                types.Part.from_uri(file_uri=video_url, mime_type="video/mp4"),
                types.Part.from_text(text=prompt),
            ]
            return self._client.models.generate_content(
                model=self._model,
                contents=contents,
            )

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call)
            try:
                return future.result(timeout=timeout)
            except FuturesTimeout:
                logger.error(f"Gemini API call timed out after {timeout}s")
                raise TimeoutError(f"Gemini API timeout ({timeout}s)")

    def _parse_response(self, raw_text: str) -> dict:
        """Parse Gemini JSON response with tolerance for markdown fences."""
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
            raise ValueError(f"Gagal parse Gemini response: {text[:500]}")
