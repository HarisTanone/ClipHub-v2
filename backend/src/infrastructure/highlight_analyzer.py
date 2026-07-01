"""HighlightAnalyzer — Multi-LLM fallback chain for viral clip analysis.

Strategy:
1. Groq LLM (primary) — 128K context, fast, reliable JSON mode
2. Gemini (fallback) — 1M token context, but often timeout
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
        
        Chain: Groq LLM (primary) → Gemini (fallback) → Ollama (last resort)
        Groq is preferred: fast, 128K context, reliable JSON mode.
        """
        from src.infrastructure.model_status import ModelStatusTracker
        tracker = ModelStatusTracker()
        errors = []

        # ─── 1. Try Groq LLM (PRIMARY — fast, 128K context, JSON mode) ────
        if self._groq_key and tracker.is_available("groq_llm"):
            try:
                logger.info("highlight_analyzer: trying Groq LLM (primary)")
                result = await self._analyze_with_groq(transcript, video_duration, max_clips)
                if result and result.clips:
                    logger.info(f"highlight_analyzer: Groq LLM success — {len(result.clips)} clips")
                    tracker.mark_success("groq_llm")
                    return result
                logger.warning("highlight_analyzer: Groq LLM returned empty result")
            except Exception as e:
                errors.append(f"Groq: {e}")
                logger.warning(f"highlight_analyzer: Groq LLM failed: {e}")
                if "413" in str(e) or "429" in str(e) or "rate" in str(e).lower():
                    tracker.mark_rate_limited("groq_llm", 60, str(e)[:200])
                else:
                    tracker.mark_error("groq_llm", str(e)[:200])

        # ─── 2. Try Gemini (fallback — 1M context, but often timeout) ─────
        if self._gemini_keys and tracker.is_available("gemini"):
            try:
                logger.info("highlight_analyzer: trying Gemini (fallback)")
                result = await self._analyze_with_gemini(transcript, video_duration, max_clips)
                if result and result.clips:
                    logger.info(f"highlight_analyzer: Gemini success — {len(result.clips)} clips")
                    tracker.mark_success("gemini")
                    return result
                logger.warning("highlight_analyzer: Gemini returned empty result")
            except Exception as e:
                errors.append(f"Gemini: {e}")
                logger.warning(f"highlight_analyzer: Gemini failed: {e}")
                if "429" in str(e) or "quota" in str(e).lower():
                    tracker.mark_exhausted("gemini", str(e)[:200])
                else:
                    tracker.mark_error("gemini", str(e)[:200])

        # ─── 3. Ollama local (last resort — slow but guaranteed) ──────
        try:
            logger.info("highlight_analyzer: trying Ollama (last resort)")
            from src.infrastructure.ollama_analyzer import OllamaAnalyzer
            analyzer = OllamaAnalyzer()
            result = await analyzer.analyze_highlights(transcript, video_duration, max_clips)
            if result and result.clips:
                logger.info(f"highlight_analyzer: Ollama success — {len(result.clips)} clips")
                tracker.mark_success("ollama")
                return result
        except Exception as e:
            errors.append(f"Ollama: {e}")
            logger.error(f"highlight_analyzer: Ollama failed: {e}")
            tracker.mark_error("ollama", str(e)[:200])

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
                    timeout=settings.GEMINI_TIMEOUT,
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
                logger.warning(f"highlight_analyzer: Gemini key {key_idx + 1} timeout ({settings.GEMINI_TIMEOUT}s)")
                continue
            except Exception as e:
                logger.warning(f"highlight_analyzer: Gemini key {key_idx + 1} failed: {e}")
                continue

        return None

    # ─── Groq LLM Analysis ────────────────────────────────────────────────────

    async def _analyze_with_groq(
        self, transcript: TranscriptResult, video_duration: float, max_clips: int
    ) -> Optional[HighlightAnalysisResult]:
        """Use Groq LLM API for highlight analysis — PRIMARY engine.
        
        Enterprise-grade implementation:
        - Segment IDs for precise timestamp referencing (no hallucination)
        - JSON Schema enforcement (guaranteed structure at API level)
        - Full transcript with smart overflow handling
        - llama-3.3-70b-versatile (128K context)
        """
        from groq import Groq, RateLimitError, APIConnectionError

        client = Groq(api_key=self._groq_key)
        groq_model = "llama-3.3-70b-versatile"

        # Build indexed transcript: each segment gets an ID for precise referencing
        # This prevents LLM from hallucinating timestamps
        segment_map = {}  # id -> {start, end, text}
        transcript_lines = []
        for i, seg in enumerate(transcript.segments):
            seg_id = f"S{i:04d}"
            segment_map[seg_id] = {"start": seg.start, "end": seg.end, "text": seg.text}
            mins, secs = divmod(int(seg.start), 60)
            transcript_lines.append(f"[{seg_id} | {mins:02d}:{secs:02d}] {seg.text.strip()}")

        transcript_text = "\n".join(transcript_lines)

        # Smart overflow: if transcript too large, keep first 40% + last 40% with marker
        estimated_tokens = len(transcript_text.split()) * 1.3
        is_truncated = False
        if estimated_tokens > 100000:
            is_truncated = True
            lines = transcript_lines
            keep = int(len(lines) * 0.4)
            first_part = "\n".join(lines[:keep])
            last_part = "\n".join(lines[-keep:])
            
            # Get boundary timestamps for the gap
            gap_start_seg = transcript.segments[keep] if keep < len(transcript.segments) else None
            gap_end_seg = transcript.segments[-keep] if keep < len(transcript.segments) else None
            gap_info = ""
            if gap_start_seg and gap_end_seg:
                gap_info = f" (dari {gap_start_seg.start:.0f}s sampai {gap_end_seg.start:.0f}s)"
            
            transcript_text = (
                f"{first_part}\n\n"
                f"[=== BAGIAN TENGAH DIPOTONG{gap_info} — JANGAN buat clip yang menjembatani bagian ini ===]\n\n"
                f"{last_part}"
            )
            logger.info(f"highlight_analyzer: Groq transcript truncated (est {estimated_tokens:.0f} tokens → kept first+last 40%)")

        # System prompt with explicit rules
        truncation_warning = ""
        if is_truncated:
            truncation_warning = "\n7. JANGAN membuat clip yang start-nya di bagian SEBELUM potongan dan end-nya di bagian SETELAH potongan."

        system_prompt = f"""Kamu adalah AI analis konten viral spesialis podcast/video Indonesia.
Tugasmu: menganalisis transcript dan mengekstrak {max_clips} potongan (clip) terbaik untuk TikTok/Reels/Shorts.
Respons HARUS dalam format JSON valid.

ATURAN WAJIB:
1. Duration clip MINIMUM 45 detik. JANGAN potong di tengah cerita — end_id HARUS di kalimat penutup/konklusi yang natural. Boleh lebih dari 90 detik jika topik belum selesai.
2. Gunakan Segment ID (contoh: S0015) untuk menandai awal dan akhir clip.
3. start_id = ID segment AWAL clip, end_id = ID segment AKHIR clip.
4. Clip TIDAK BOLEH overlap satu sama lain.
5. Hook = 3-8 kata, membuat penasaran, BUKAN spoiler. Bahasa sama dengan transcript.
6. Score 0-100 berdasarkan potensi viral.{truncation_warning}

PENTING: Referensikan segment ID yang ada di transcript, JANGAN membuat ID baru."""

        user_prompt = f"""Video berdurasi {video_duration:.0f} detik ({len(transcript.segments)} segments). 
Temukan {max_clips} momen paling viral.

TRANSKRIP (format: [SegmentID | MM:SS] teks):
{transcript_text}

Ekstrak {max_clips} clip terbaik. Gunakan segment ID dari transcript di atas."""

        # JSON Schema for strict output structure
        clip_schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "clip_extraction",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "clips": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "rank": {"type": "integer"},
                                    "score": {"type": "integer"},
                                    "start_id": {"type": "string"},
                                    "end_id": {"type": "string"},
                                    "hook": {"type": "string"},
                                    "reason": {"type": "string"},
                                    "content_type": {"type": "string"},
                                    "speaker_energy": {"type": "string"},
                                },
                                "required": ["rank", "score", "start_id", "end_id", "hook", "reason", "content_type", "speaker_energy"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["clips"],
                    "additionalProperties": False,
                },
            },
        }

        for attempt in range(3):
            try:
                def _groq_call(m=groq_model, s=system_prompt, u=user_prompt, schema=clip_schema):
                    try:
                        # Try json_schema first (strict structure)
                        return client.chat.completions.create(
                            model=m,
                            messages=[
                                {"role": "system", "content": s},
                                {"role": "user", "content": u},
                            ],
                            temperature=0.3,
                            max_tokens=4096,
                            response_format=schema,
                        )
                    except Exception:
                        # Fallback to json_object if schema not supported
                        return client.chat.completions.create(
                            model=m,
                            messages=[
                                {"role": "system", "content": s},
                                {"role": "user", "content": u},
                            ],
                            temperature=0.3,
                            max_tokens=4096,
                            response_format={"type": "json_object"},
                        )

                response = await asyncio.wait_for(
                    asyncio.get_running_loop().run_in_executor(None, _groq_call),
                    timeout=settings.GROQ_LLM_TIMEOUT,
                )

                if not response.choices:
                    return None

                raw_text = response.choices[0].message.content or ""

                # Parse JSON
                try:
                    data = json.loads(raw_text)
                except json.JSONDecodeError:
                    logger.warning(f"highlight_analyzer: Groq JSON parse failed: {raw_text[:200]}")
                    clips = self._parse_llm_response(raw_text, video_duration)
                    if clips:
                        return self._build_result(clips, max_clips, video_duration, f"groq_{groq_model}")
                    return None

                raw_clips = data.get("clips", [])
                if not raw_clips:
                    logger.warning(f"highlight_analyzer: Groq JSON valid but no clips. Keys: {list(data.keys())}")
                    return None

                # Convert segment IDs back to timestamps
                candidates = []
                for i, c in enumerate(raw_clips):
                    try:
                        # Resolve segment IDs to actual timestamps
                        start_id = c.get("start_id", "")
                        end_id = c.get("end_id", "")
                        
                        # Handle both ID-based (new) and raw timestamp (fallback)
                        if start_id in segment_map and end_id in segment_map:
                            start = segment_map[start_id]["start"]
                            end = segment_map[end_id]["end"]
                        elif "start" in c and "end" in c:
                            # Fallback: model returned raw timestamps instead of IDs
                            start = float(c["start"])
                            end = float(c["end"])
                        else:
                            logger.debug(f"highlight_analyzer: Groq clip {i} has invalid IDs: {start_id}, {end_id}")
                            continue

                        duration = end - start

                        # Validate
                        if end <= start or start < 0 or end > video_duration + 10:
                            logger.debug(f"highlight_analyzer: Groq clip {i} rejected (range): {start:.1f}-{end:.1f}")
                            continue
                        if duration < 15 or duration > 300:
                            logger.debug(f"highlight_analyzer: Groq clip {i} rejected (duration {duration:.1f}s)")
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
                            hook_alt="",
                        ))
                    except (ValueError, TypeError) as e:
                        logger.debug(f"highlight_analyzer: Groq clip {i} parse error: {e}")
                        continue

                if candidates:
                    logger.info(f"highlight_analyzer: Groq produced {len(candidates)} valid clips from {len(raw_clips)} raw")
                    return self._build_result(candidates, max_clips, video_duration, f"groq_{groq_model}")

                logger.warning(f"highlight_analyzer: Groq {len(raw_clips)} raw clips but 0 passed validation")
                return None

            except asyncio.TimeoutError:
                logger.warning(f"highlight_analyzer: Groq LLM timeout attempt {attempt + 1}/{3} ({settings.GROQ_LLM_TIMEOUT}s)")
                continue
            except RateLimitError as e:
                wait = (attempt + 1) * 15
                logger.warning(f"highlight_analyzer: Groq rate limit (attempt {attempt + 1}), waiting {wait}s: {e}")
                await asyncio.sleep(wait)
            except APIConnectionError as e:
                logger.warning(f"highlight_analyzer: Groq connection error: {e}")
                break
            except Exception as e:
                logger.warning(f"highlight_analyzer: Groq unexpected error (attempt {attempt + 1}): {e}")
                if attempt == 2:
                    break
                continue

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
- Target: Temukan TEPAT {max_clips} momen terbaik (durasi MINIMUM 45 detik, biarkan cerita selesai utuh — jangan potong di bagian penting)
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
            logger.warning(f"highlight_analyzer: JSON parsed but 'clips' array is empty. Keys found: {list(data.keys())}")
            return []

        candidates = []
        for i, c in enumerate(raw_clips):
            try:
                start = float(c.get("start", 0))
                end = float(c.get("end", 0))

                # Validate timestamps
                if end <= start or start < 0 or end > video_duration + 10:
                    continue
                if end - start < 15 or end - start > 300:
                    # Hard reject: too short (<15s) or absurdly long (>5min)
                    continue
                duration = end - start
                if duration < 45:
                    # Soft filter: log warning but still include
                    logger.debug(f"highlight_analyzer: clip {start:.1f}-{end:.1f} is short ({duration:.1f}s < 45s)")

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
