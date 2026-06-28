"""OllamaAnalyzer — Analyze Faster-Whisper JSON transcript using local Ollama LLM.

Uses local Ollama server (mistral-nemo:12b) to identify viral clip candidates.
No API rate limits, no external dependencies, full privacy.

Flow:
1. Receive word-level transcript JSON from Faster-Whisper
2. Chunk transcript into segments (by time, ~10 min each)
3. Send each chunk to Ollama for analysis
4. Merge + rank candidates globally
5. Generate creative direction
"""
import asyncio
import json
import logging
import time
from typing import Optional

import httpx

from src.config import settings
from src.domain.entities import (
    HighlightAnalysisResult,
    HighlightCandidate,
    TranscriptResult,
    TranscriptSegment,
)

logger = logging.getLogger(__name__)


class OllamaAnalyzerError(Exception):
    """Raised when Ollama analysis fails."""
    pass


class OllamaAnalyzer:
    """Analyze transcript using local Ollama LLM (mistral-nemo:12b)."""

    def __init__(self):
        self._base_url = getattr(settings, "OLLAMA_BASE_URL", "http://100.64.5.96:11434")
        self._model = getattr(settings, "OLLAMA_MODEL", "mistral-nemo:12b")
        self._chunk_max_seconds = settings.V2_CHUNK_MAX_SECONDS  # 600s
        self._chunk_max_chars = settings.V2_CHUNK_MAX_CHARS       # 4000

    # ─── Main Entry Point ─────────────────────────────────────────────────────

    async def analyze_highlights(
        self, transcript: TranscriptResult, video_duration: float, max_clips: int
    ) -> HighlightAnalysisResult:
        """Analyze transcript → viral highlight candidates + creative direction."""

        chunks = self._chunk_transcript(transcript.segments)
        logger.info(
            f"ollama_analyzer: {len(chunks)} chunks from {video_duration:.0f}s video "
            f"(max_clips={max_clips}, model={self._model})"
        )

        # ─── Phase A: Analyze each chunk ──────────────────────────────
        all_candidates = []
        for i, chunk in enumerate(chunks):
            chunk_start = chunk[0].start
            chunk_end = chunk[-1].end
            chunk_text = " ".join(seg.text for seg in chunk)

            logger.info(f"ollama_analyzer: chunk {i+1}/{len(chunks)} [{chunk_start:.0f}s-{chunk_end:.0f}s]")

            try:
                candidates = await self._analyze_chunk(
                    chunk_text, chunk_start, chunk_end,
                    video_duration, max_clips, i + 1, len(chunks)
                )
                all_candidates.extend(candidates)
            except Exception as e:
                logger.warning(f"ollama_analyzer: chunk {i+1} failed: {e}")

        if not all_candidates:
            raise OllamaAnalyzerError("Ollama tidak menghasilkan clip candidates")

        # ─── Phase B: Rank + Creative Direction ───────────────────────
        ranked_clips = self._rank_and_merge(all_candidates, max_clips, video_duration)
        logger.info(f"ollama_analyzer: {len(ranked_clips)} clips selected from {len(all_candidates)} candidates")

        # Generate creative direction
        try:
            creative_result = await self._generate_creative_direction(ranked_clips, video_duration)
        except Exception as e:
            logger.warning(f"ollama_analyzer: creative direction failed: {e}")
            creative_result = {"creative_direction": {}, "broll_suggestions": {}}

        return HighlightAnalysisResult(
            clips=ranked_clips,
            creative_direction=creative_result.get("creative_direction", {}),
            broll_suggestions=creative_result.get("broll_suggestions", {}),
            model_used=self._model,
            chunks_processed=len(chunks),
        )

    # ─── Ollama API Call ──────────────────────────────────────────────────────

    async def _call_ollama(self, prompt: str, timeout: float = 120.0) -> str:
        """Call local Ollama API. No rate limits!"""
        url = f"{self._base_url}/api/generate"
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 3000,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
        except httpx.TimeoutException:
            raise OllamaAnalyzerError(f"Ollama timeout ({timeout}s)")
        except httpx.HTTPStatusError as e:
            raise OllamaAnalyzerError(f"Ollama HTTP error: {e.response.status_code}")
        except httpx.ConnectError:
            raise OllamaAnalyzerError(f"Ollama not reachable at {self._base_url}")

    # ─── Chunk Analysis ───────────────────────────────────────────────────────

    async def _analyze_chunk(
        self, chunk_text: str, chunk_start: float, chunk_end: float,
        video_duration: float, max_clips: int, chunk_num: int, total_chunks: int
    ) -> list[HighlightCandidate]:
        """Analyze a single transcript chunk via Ollama."""
        clips_per_chunk = max(2, max_clips // max(1, total_chunks) + 1)

        prompt = f"""Kamu adalah AI analis konten viral. Analisis transkrip berikut dan identifikasi momen paling menarik untuk dijadikan short clip.

KONTEKS:
- Video total: {video_duration:.0f} detik
- Bagian ini: [{chunk_start:.1f}s - {chunk_end:.1f}s] (chunk {chunk_num} dari {total_chunks})
- Target: MAKSIMAL {clips_per_chunk} momen viral (durasi 45-90 detik per klip)

TRANSKRIP:
{chunk_text}

ATURAN:
1. Timestamp 'start' dan 'end' HARUS dalam rentang [{chunk_start:.1f}, {chunk_end:.1f}]
2. Durasi setiap klip: 45-90 detik
3. Klip TIDAK BOLEH OVERLAP
4. Skor 1-100 berdasarkan potensi viral
5. Hook = teks singkat <60 karakter, bahasa sama dengan transkrip

OUTPUT HANYA JSON (tanpa penjelasan lain):
{{"clips": [{{"rank": 1, "score": 85, "start": 0.0, "end": 60.0, "hook": "teks hook", "reason": "alasan singkat", "content_type": "storytelling", "speaker_energy": "high"}}]}}"""

        raw = await self._call_ollama(prompt)
        return self._parse_chunk_response(raw, chunk_start, chunk_end)

    # ─── Creative Direction ───────────────────────────────────────────────────

    async def _generate_creative_direction(
        self, clips: list[HighlightCandidate], video_duration: float
    ) -> dict:
        """Generate creative direction using Ollama."""
        clips_context = "\n".join([
            f"Clip {c.rank}: [{c.start:.1f}s-{c.end:.1f}s] score={c.score}, hook=\"{c.hook}\""
            for c in clips
        ])

        prompt = f"""Berdasarkan clip viral berikut, tentukan visual style yang cocok.

CLIPS:
{clips_context}

Berikan JSON dengan format:
{{"creative_direction": {{"primary_color": "#FFFFFF", "secondary_color": "#FFD700", "background_accent": "#000000", "typography_mood": "bold_impact", "energy_level": "high", "transition_style": "fast_cuts", "music_mood": "energetic", "hook_animation": "fade_scale"}}, "broll_suggestions": {{}}}}

OUTPUT HANYA JSON:"""

        raw = await self._call_ollama(prompt, timeout=60.0)
        return self._parse_json_response(raw)

    # ─── Parsing ──────────────────────────────────────────────────────────────

    def _parse_chunk_response(
        self, raw_text: str, chunk_start: float, chunk_end: float
    ) -> list[HighlightCandidate]:
        """Parse Ollama response → list of candidates."""
        data = self._parse_json_response(raw_text)
        if not data or "clips" not in data:
            return []

        candidates = []
        for clip in data["clips"]:
            try:
                start = float(clip.get("start", 0))
                end = float(clip.get("end", 0))
                score = int(clip.get("score", 50))

                # Validate timestamps
                if start < chunk_start - 5:
                    start = chunk_start
                if end > chunk_end + 5:
                    end = chunk_end

                duration = end - start
                if duration < 30 or duration > 120:
                    continue

                score = max(1, min(100, score))

                candidates.append(HighlightCandidate(
                    rank=0,
                    start=round(start, 2),
                    end=round(end, 2),
                    score=score,
                    hook=str(clip.get("hook", ""))[:60],
                    reason=str(clip.get("reason", "")),
                    content_type=str(clip.get("content_type", "storytelling")),
                    speaker_energy=str(clip.get("speaker_energy", "medium")),
                ))
            except (ValueError, TypeError):
                continue

        return candidates

    def _parse_json_response(self, raw_text: str) -> dict:
        """Parse JSON from Ollama response (tolerant of markdown fences)."""
        text = raw_text.strip()

        # Remove markdown fences
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
            # Try to extract JSON object
            start_idx = text.find("{")
            end_idx = text.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                try:
                    return json.loads(text[start_idx:end_idx])
                except json.JSONDecodeError:
                    pass
            logger.warning(f"ollama_analyzer: failed to parse JSON: {text[:200]}")
            return {}

    # ─── Chunking & Ranking (same logic as before) ────────────────────────────

    def _chunk_transcript(self, segments: list[TranscriptSegment]) -> list[list[TranscriptSegment]]:
        """Split transcript into chunks (max 600s or 4000 chars)."""
        if not segments:
            return []

        chunks = []
        current_chunk = []
        current_duration = 0.0
        current_chars = 0

        for seg in segments:
            seg_duration = seg.end - seg.start
            seg_chars = len(seg.text)

            if (current_duration + seg_duration > self._chunk_max_seconds or
                current_chars + seg_chars > self._chunk_max_chars) and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_duration = 0.0
                current_chars = 0

            current_chunk.append(seg)
            current_duration += seg_duration
            current_chars += seg_chars

        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    def _rank_and_merge(
        self, candidates: list[HighlightCandidate], max_clips: int, video_duration: float
    ) -> list[HighlightCandidate]:
        """Sort by score, remove overlaps, assign ranks."""
        if not candidates:
            return []

        sorted_clips = sorted(candidates, key=lambda c: c.score, reverse=True)
        selected = []
        for clip in sorted_clips:
            if len(selected) >= max_clips:
                break
            if not any(clip.start < e.end and clip.end > e.start for e in selected):
                selected.append(clip)

        selected.sort(key=lambda c: c.start)
        for i, clip in enumerate(selected):
            clip.rank = i + 1
        return selected
