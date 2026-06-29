"""HighlightAnalyzer — Multi-LLM fallback chain for viral clip analysis.

Strategy:
1. Gemini (primary) — 1M token context, fast, accurate
2. Groq LLM (fallback) — 128K context, very fast
3. Ollama local (last resort) — unlimited, slow but guaranteed

Each LLM receives the same prompt and returns the same HighlightAnalysisResult.
If one fails, the next in chain is tried automatically.
"""
import asyncio
import json
import logging
from typing import Optional

from src.config import settings
from src.domain.entities import (
    HighlightAnalysisResult,
    HighlightCandidate,
    TranscriptResult,
)

logger = logging.getLogger(__name__)


class HighlightAnalyzerError(Exception):
    """Raised when all LLM backends fail."""
    pass


class HighlightAnalyzer:
    """Multi-LLM highlight analyzer with automatic fallback chain."""

    def __init__(self):
        self._gemini_keys = settings.gemini_api_keys
        self._groq_key = settings.GROQ_API_KEY
        self._ollama_url = settings.OLLAMA_BASE_URL

    async def analyze_highlights(
        self, transcript: TranscriptResult, video_duration: float, max_clips: int
    ) -> HighlightAnalysisResult:
        """Analyze transcript for viral clips using best available LLM.
        
        Chain: Gemini → Groq LLM → Ollama (local)
        """
        errors = []

        # ─── 1. Try Gemini (primary — 1M context, very fast) ─────────
        if self._gemini_keys:
            try:
                logger.info("highlight_analyzer: trying Gemini (primary)")
                result = await self._analyze_with_gemini(transcript, video_duration, max_clips)
                if result and result.clips:
                    logger.info(f"highlight_analyzer: Gemini success — {len(result.clips)} clips")
                    return result
                logger.warning("highlight_analyzer: Gemini returned empty result")
            except Exception as e:
                errors.append(f"Gemini: {e}")
                logger.warning(f"highlight_analyzer: Gemini failed: {e}")

        # ─── 2. Try Groq LLM (fast, 128K context) ────────────────────
        if self._groq_key:
            try:
                logger.info("highlight_analyzer: trying Groq LLM (fallback 1)")
                result = await self._analyze_with_groq(transcript, video_duration, max_clips)
                if result and result.clips:
                    logger.info(f"highlight_analyzer: Groq LLM success — {len(result.clips)} clips")
                    return result
                logger.warning("highlight_analyzer: Groq LLM returned empty result")
            except Exception as e:
                errors.append(f"Groq: {e}")
                logger.warning(f"highlight_analyzer: Groq LLM failed: {e}")

        # ─── 3. Ollama local (last resort — slow but guaranteed) ──────
        try:
            logger.info("highlight_analyzer: trying Ollama (last resort)")
            from src.infrastructure.ollama_analyzer import OllamaAnalyzer
            analyzer = OllamaAnalyzer()
            result = await analyzer.analyze_highlights(transcript, video_duration, max_clips)
            if result and result.clips:
                logger.info(f"highlight_analyzer: Ollama success — {len(result.clips)} clips")
                return result
        except Exception as e:
            errors.append(f"Ollama: {e}")
            logger.error(f"highlight_analyzer: Ollama failed: {e}")

        # All failed
        raise HighlightAnalyzerError(
            f"All LLM backends failed: {'; '.join(errors)}"
        )

    # ─── Gemini Analysis ──────────────────────────────────────────────────────

    async def _analyze_with_gemini(
        self, transcript: TranscriptResult, video_duration: float, max_clips: int
    ) -> Optional[HighlightAnalysisResult]:
        """Use Gemini API for highlight analysis (1M token context).
        
        Uses per-call configure to avoid global state race conditions
        when MAX_CONCURRENT_JOBS > 1. Each key is tried sequentially.
        """
        import google.generativeai as genai

        prompt = self._build_prompt(transcript, video_duration, max_clips)

        # Rotate through available keys
        for key_idx, api_key in enumerate(self._gemini_keys):
            try:
                # Thread-safe: each call configures + generates atomically in executor
                def _gemini_call(key=api_key, p=prompt):
                    genai.configure(api_key=key)
                    model = genai.GenerativeModel(settings.GEMINI_MODEL or "gemini-2.0-flash")
                    return model.generate_content(
                        p,
                        generation_config=genai.GenerationConfig(
                            temperature=0.3,
                            max_output_tokens=4096,
                        ),
                    )

                response = await asyncio.wait_for(
                    asyncio.get_running_loop().run_in_executor(None, _gemini_call),
                    timeout=120,  # 2 min timeout for Gemini API
                )

                # Safety filter check — response.text raises ValueError if blocked
                if not response or not response.candidates:
                    continue
                try:
                    text = response.text
                except (ValueError, AttributeError):
                    logger.warning(f"highlight_analyzer: Gemini key {key_idx + 1} response blocked by safety filter")
                    continue

                if not text:
                    continue

                clips = self._parse_llm_response(text, video_duration)
                if clips:
                    return self._build_result(clips, max_clips, video_duration, "gemini")
            except asyncio.TimeoutError:
                logger.warning(f"highlight_analyzer: Gemini key {key_idx + 1} timeout (120s)")
                continue
            except Exception as e:
                logger.warning(f"highlight_analyzer: Gemini key {key_idx + 1} failed: {e}")
                continue

        return None

    # ─── Groq LLM Analysis ────────────────────────────────────────────────────

    async def _analyze_with_groq(
        self, transcript: TranscriptResult, video_duration: float, max_clips: int
    ) -> Optional[HighlightAnalysisResult]:
        """Use Groq LLM API for highlight analysis.
        
        Uses llama-3.1-8b-instant (20K TPM on free tier) with aggressive truncation.
        """
        from groq import Groq, RateLimitError, APIConnectionError

        # Free tier TPM limits: 8b=20K, 70b=12K. Use 8b for higher limit.
        client = Groq(api_key=self._groq_key)
        groq_model = settings.GROQ_LLM_MODEL or "llama-3.1-8b-instant"

        # Truncate transcript to fit within TPM limit (~8K tokens input max)
        max_input_chars = 24000  # ~8K tokens × 3 chars/token
        prompt = self._build_prompt(transcript, video_duration, max_clips, max_chars=max_input_chars)

        for attempt in range(3):
            try:
                # Capture variables explicitly to avoid late-binding issues
                def _groq_call(m=groq_model, p=prompt):
                    return client.chat.completions.create(
                        model=m,
                        messages=[
                            {"role": "system", "content": "Kamu adalah AI analis konten viral. Output HANYA raw JSON tanpa markdown."},
                            {"role": "user", "content": p},
                        ],
                        temperature=0.3,
                        max_tokens=4096,
                    )

                response = await asyncio.wait_for(
                    asyncio.get_running_loop().run_in_executor(None, _groq_call),
                    timeout=90,  # 90s timeout for Groq LLM
                )

                if not response.choices:
                    return None

                raw_text = response.choices[0].message.content or ""
                clips = self._parse_llm_response(raw_text, video_duration)
                if clips:
                    return self._build_result(clips, max_clips, video_duration, f"groq_{groq_model}")
                return None

            except asyncio.TimeoutError:
                logger.warning(f"highlight_analyzer: Groq LLM timeout (attempt {attempt + 1})")
                continue
            except RateLimitError:
                wait = (attempt + 1) * 15
                logger.warning(f"highlight_analyzer: Groq rate limit, waiting {wait}s")
                await asyncio.sleep(wait)
            except APIConnectionError as e:
                logger.warning(f"highlight_analyzer: Groq connection error: {e}")
                break
            except Exception as e:
                logger.warning(f"highlight_analyzer: Groq error: {e}")
                break

        return None

    # ─── Shared: Build Analysis Prompt ────────────────────────────────────────

    def _build_prompt(
        self, transcript: TranscriptResult, video_duration: float, max_clips: int,
        max_chars: int = 0
    ) -> str:
        """Build the analysis prompt (shared across all LLMs)."""
        # Build condensed transcript with timestamps
        lines = []
        total_chars = 0
        for seg in transcript.segments:
            line = f"[{seg.start:.1f}s] {seg.text}"
            if max_chars and total_chars + len(line) > max_chars:
                break
            lines.append(line)
            total_chars += len(line)

        transcript_text = "\n".join(lines)

        return f"""Kamu adalah AI analis konten viral profesional untuk platform TikTok/Reels/Shorts.
Baca SELURUH transkrip video berikut dan identifikasi momen-momen PALING MENARIK untuk dijadikan short clip viral.

VIDEO INFO:
- Durasi total: {video_duration:.0f} detik
- Target: Temukan TEPAT {max_clips} momen terbaik (durasi 45-90 detik per klip)
- Format timestamp: detik (contoh: 125.5)

TRANSKRIP LENGKAP:
{transcript_text}

KRITERIA PEMILIHAN CLIP (prioritas tinggi ke rendah):
1. HOOK KUAT di awal — kalimat pembuka yang membuat orang berhenti scroll
2. KONFLIK / DRAMA / EMOSI — momen dengan intensitas tinggi
3. PUNCHLINE / INSIGHT — "aha moment" atau twist yang mengejutkan
4. STORYTELLING ARC — clip harus punya awal, tengah, akhir yang memuaskan
5. RE-WATCH VALUE — momen yang membuat orang ingin tonton ulang atau share

ATURAN HOOK TEXT:
- Hook text 3-8 kata, HARUS membuat penasaran
- JANGAN gunakan spoiler
- Contoh BAGUS: "Ternyata dia bohong selama ini...", "Gue hampir mati karena ini"
- Contoh BURUK: "Tips editing video", "Cara membuat konten"

OUTPUT FORMAT — HANYA RAW JSON (tanpa penjelasan, tanpa markdown, tanpa komentar):
{{"clips": [{{"rank": 1, "score": 90, "start": 120.0, "end": 180.0, "hook": "hook text viral", "reason": "alasan singkat", "content_type": "storytelling", "speaker_energy": "high"}}]}}"""

    # ─── Shared: Parse LLM Response ───────────────────────────────────────────

    def _parse_llm_response(self, raw_text: str, video_duration: float) -> list[HighlightCandidate]:
        """Parse JSON from LLM response into HighlightCandidate list."""
        # Clean markdown/code block wrappers
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.replace("```json", "").replace("```", "").strip()

        # Try to find JSON object
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start == -1 or json_end <= json_start:
            logger.warning(f"highlight_analyzer: no JSON found in response ({len(raw_text)} chars)")
            return []

        try:
            data = json.loads(text[json_start:json_end])
        except json.JSONDecodeError:
            # Try fixing common issues
            try:
                import re
                fixed = re.sub(r',\s*([}\]])', r'\1', text[json_start:json_end])
                data = json.loads(fixed)
            except json.JSONDecodeError:
                logger.error(f"highlight_analyzer: failed to parse JSON: {text[:200]}")
                return []

        raw_clips = data.get("clips", [])
        if not raw_clips:
            return []

        candidates = []
        for i, c in enumerate(raw_clips):
            try:
                start = float(c.get("start", 0))
                end = float(c.get("end", 0))

                # Validate timestamps
                if end <= start or start < 0 or end > video_duration + 10:
                    continue
                if end - start < 10 or end - start > 180:
                    continue

                candidates.append(HighlightCandidate(
                    rank=c.get("rank", i + 1),
                    start=round(start, 2),
                    end=round(end, 2),
                    score=min(100, max(0, int(c.get("score", 70)))),
                    hook=c.get("hook", ""),
                    reason=c.get("reason", ""),
                    content_type=c.get("content_type", "general"),
                    speaker_energy=c.get("speaker_energy", "medium"),
                    hook_alt=c.get("hook_alt", ""),
                ))
            except (ValueError, TypeError):
                continue

        return candidates

    # ─── Shared: Build Result ─────────────────────────────────────────────────

    def _build_result(
        self, clips: list[HighlightCandidate], max_clips: int,
        video_duration: float, model_used: str
    ) -> HighlightAnalysisResult:
        """Build final result from parsed candidates."""
        # Sort by score descending, take top N
        clips.sort(key=lambda c: c.score, reverse=True)
        ranked = clips[:max_clips]

        # Re-assign ranks
        for i, clip in enumerate(ranked):
            clip.rank = i + 1

        return HighlightAnalysisResult(
            clips=ranked,
            creative_direction={},
            broll_suggestions={},
            model_used=model_used,
            chunks_processed=1,
        )
