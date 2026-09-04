"""Gemini Agentic Video Understanding Service.

Follows official Gemini Agentic Video Understanding principles:
https://ai.google.dev/gemini-api/docs/video-understanding#agentic-video-understanding

Key Capabilities:
1. Agentic Video & Narrative Alignment:
   Inspects video footage dynamically across its timeline using Gemini's Agentic Video
   Understanding (processing="agentic") to verify that the video visually matches the spoken
   narration, calculates semantic alignment scores, and identifies the exact best timestamp
   interval [best_start_timestamp, best_end_timestamp] for seamless visual-audio harmony.
2. Multi-Candidate Curated Selection:
   Evaluates multiple candidate footage files for a scene and picks the footage with the highest
   semantic harmony with the story and narration.
3. Dynamic Subtitle & Context Reasoning:
   Generates targeted English visual search queries when local keywords require stock b-roll.
4. Candidate Verification:
   Filters out banned or abstract nonsense visuals.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Optional

from google import genai
from google.genai import types

from src.config import settings

logger = logging.getLogger(__name__)

ALIGNMENT_AGENTIC_PROMPT = """You are an expert film director and short-form video editor conducting Gemini Video Understanding.
Your mission is to dynamically inspect this video's timeline, audio, and visual moments to determine how well it aligns with a specific scene in our vertical (9:16) short-form video.

SCENE CONTEXT:
- Overall Topic: "{topic}"
- Scene Spoken Narration: "{narration}"
- Scene Visual Goal: "{visual_goal}"
- Target Scene Duration: {target_duration:.1f} seconds

VIDEO UNDERSTANDING INSTRUCTIONS:
1. Dynamically inspect the video content: Look at visual actions, subjects, camera movement, on-screen text, audio, and speech.
2. Evaluate semantic and aesthetic alignment ("selaras dan masuk akal"):
   - Does this footage actually show what is described in the narration and visual goal?
   - alignment_score: 0.0 (completely irrelevant) to 10.0 (perfect, stunning match).
   - is_relevant: true if alignment_score >= 5.0, false otherwise.
3. Identify the EXACT BEST continuous interval:
   - Find [best_start_timestamp, best_end_timestamp] in seconds and MM:SS (window size approximately {target_duration:.1f}s) where visual action is most compelling and synchronized with narration.
   - If the video is shorter than the target duration, start at 0.0.

OUTPUT STRICT RAW JSON ONLY (no markdown code fences, no commentary outside JSON):
{{
  "is_relevant": true,
  "alignment_score": 8.5,
  "best_start_timestamp": 2.0,
  "best_end_timestamp": 8.5,
  "best_start_mm_ss": "00:02",
  "best_end_mm_ss": "00:08",
  "visual_summary": "Brief 1-sentence description of what is visible in this chosen interval",
  "reasoning": "Why this segment aligns with the narration"
}}"""


class GeminiAgenticVideoService:
    """Agentic Video & Subtitle Reasoner powered by Gemini."""

    BANNED_VISUAL_TERMS = {
        "neuron", "neurons", "synapse", "nerve cell", "neural network",
        "brain cells", "abstract glowing", "floating balls", "yellow black abstract",
        "talking head", "talking-head", "podcast host", "interview face",
    }

    def __init__(self):
        from src.infrastructure.auth import GeminiKeyRotator
        self._key_rotator = GeminiKeyRotator()
        self._model = settings.GEMINI_MODEL or "gemini-3.8-flash"
        self._fallback_model = settings.GEMINI_FALLBACK_MODEL or "gemini-3.7-flash"

    async def analyze_footage_alignment(
        self,
        video_path: str,
        narration: str,
        visual_goal: str,
        topic: str = "",
        target_duration: float = 6.5,
        timeout: int = 120,
        processing_mode: str = "agentic",
        media_resolution: str = "low",
        fps: Optional[float] = None,
        start_offset: Optional[float] = None,
        end_offset: Optional[float] = None,
    ) -> dict[str, Any]:
        """Analyze a video file/URL using Gemini Video Understanding (File API, Inline Data, or YouTube URL).

        Inspects the video dynamically or statically, verifies narrative alignment, and extracts the best continuous timestamp.
        """
        is_url = (
            video_path.startswith("http://")
            or video_path.startswith("https://")
            or video_path.startswith("gs://")
        )
        if not is_url and (not os.path.isfile(video_path) or os.path.getsize(video_path) == 0):
            return {
                "is_relevant": False,
                "alignment_score": 0.0,
                "best_start_timestamp": 0.0,
                "best_end_timestamp": target_duration,
                "best_start_mm_ss": "00:00",
                "best_end_mm_ss": f"{int(target_duration//60):02d}:{int(target_duration%60):02d}",
                "visual_summary": "File not found or empty",
                "reasoning": "Local video file unavailable",
                "processing_mode": processing_mode,
                "media_resolution": media_resolution,
            }

        keys = self._key_rotator.keys
        if not keys:
            logger.warning("[GeminiAgenticVideo] No Gemini API key configured, using default timestamps")
            return {
                "is_relevant": True,
                "alignment_score": 7.0,
                "best_start_timestamp": 0.0,
                "best_end_timestamp": target_duration,
                "best_start_mm_ss": "00:00",
                "best_end_mm_ss": f"{int(target_duration//60):02d}:{int(target_duration%60):02d}",
                "visual_summary": "Heuristic fallback (no API key)",
                "reasoning": "Default heuristic start timestamp",
                "processing_mode": processing_mode,
                "media_resolution": media_resolution,
            }

        prompt = ALIGNMENT_AGENTIC_PROMPT.format(
            topic=topic or "Short video scene",
            narration=narration or visual_goal,
            visual_goal=visual_goal or narration,
            target_duration=target_duration,
        )

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._analyze_alignment_sync,
            video_path,
            prompt,
            target_duration,
            timeout,
            processing_mode,
            media_resolution,
            fps,
            start_offset,
            end_offset,
        )

    def _analyze_alignment_sync(
        self,
        video_path: str,
        prompt: str,
        target_duration: float,
        timeout: int,
        processing_mode: str = "agentic",
        media_resolution: str = "low",
        fps: Optional[float] = None,
        start_offset: Optional[float] = None,
        end_offset: Optional[float] = None,
    ) -> dict[str, Any]:
        """Synchronous worker for Video Understanding via Interactions API or Files API."""
        import base64
        keys = self._key_rotator.keys
        errors = []

        models_to_try = [
            self._model,
            self._fallback_model,
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-2.5-flash",
        ]
        models_to_try = list(dict.fromkeys([m for m in models_to_try if m]))

        # Check input type
        is_url = (
            video_path.startswith("http://")
            or video_path.startswith("https://")
            or video_path.startswith("gs://")
        )
        file_size = 0 if is_url else os.path.getsize(video_path)
        # Inline data is recommended for smaller videos (<20MB)
        use_inline = (not is_url) and (file_size > 0) and (file_size < 20 * 1024 * 1024)

        inline_base64 = ""
        if use_inline:
            try:
                with open(video_path, "rb") as f:
                    inline_base64 = base64.b64encode(f.read()).decode("utf-8")
                logger.info(f"[GeminiVideoUnderstanding] Using Inline Data ({file_size / 1024 / 1024:.2f}MB < 20MB)")
            except Exception as read_err:
                logger.warning(f"[GeminiVideoUnderstanding] Failed reading inline bytes: {read_err}, falling back to File API")
                use_inline = False

        # Build processing configuration
        if processing_mode == "static":
            proc_config: dict[str, Any] = {"type": "static"}
            if fps and fps > 0:
                proc_config["fps"] = float(fps)
            if start_offset is not None and end_offset is not None and end_offset > start_offset:
                proc_config["start_offset"] = float(start_offset)
                proc_config["end_offset"] = float(end_offset)
            processing_spec: Any = proc_config
        else:
            processing_spec = "agentic"

        for k in keys:
            client = genai.Client(api_key=k)
            video_file = None
            try:
                # 1. Prepare video input
                if is_url:
                    video_input: dict[str, Any] = {
                        "type": "video",
                        "uri": video_path,
                        "processing": processing_spec,
                    }
                    if not video_path.startswith("https://www.youtube.com") and not video_path.startswith("https://youtu.be"):
                        video_input["mime_type"] = "video/mp4"
                elif use_inline and inline_base64:
                    video_input = {
                        "type": "video",
                        "data": inline_base64,
                        "mime_type": "video/mp4",
                        "processing": processing_spec,
                    }
                else:
                    # Upload video to Google Files API (large files / reusable)
                    logger.info(f"[GeminiVideoUnderstanding] Uploading {os.path.basename(video_path)} ({file_size / 1024 / 1024:.1f}MB) via Files API...")
                    video_file = client.files.upload(file=video_path)

                    poll_start = time.time()
                    while getattr(getattr(video_file, "state", None), "name", "") == "PROCESSING":
                        if time.time() - poll_start > 90:
                            raise TimeoutError("Gemini file upload processing timeout (>90s)")
                        time.sleep(2)
                        video_file = client.files.get(name=video_file.name)

                    if getattr(getattr(video_file, "state", None), "name", "") == "FAILED":
                        raise RuntimeError("Gemini file upload processing failed on server")

                    mime_type = getattr(video_file, "mime_type", "video/mp4") or "video/mp4"
                    video_input = {
                        "type": "video",
                        "uri": video_file.uri,
                        "mime_type": mime_type,
                        "processing": processing_spec,
                    }

                if media_resolution in ("low", "high"):
                    video_input["media_resolution"] = media_resolution

                # 2. Call Interactions API with text prompt placed AFTER video input
                for model_id in models_to_try:
                    try:
                        logger.info(
                            f"[GeminiVideoUnderstanding] Calling interactions.create model={model_id} "
                            f"mode={processing_mode} resolution={media_resolution}..."
                        )
                        interaction = client.interactions.create(
                            model=model_id,
                            input=[
                                video_input,
                                {"type": "text", "text": prompt},
                            ],
                        )

                        output_text = getattr(interaction, "output_text", "")
                        thought_steps: list[str] = []
                        agentic_calls_count = 0

                        if hasattr(interaction, "steps"):
                            for step in (getattr(interaction, "steps", None) or []):
                                stype = getattr(step, "type", "")
                                if stype == "thought":
                                    for item in (getattr(step, "summary", None) or []):
                                        t = getattr(item, "text", "")
                                        if t:
                                            thought_steps.append(t)
                                elif stype in ("processing_call", "processing_result"):
                                    agentic_calls_count += 1
                                elif stype == "model_output" and not output_text:
                                    for item in (getattr(step, "content", None) or []):
                                        if getattr(item, "type", "") == "text":
                                            output_text = getattr(item, "text", "")
                                            break

                        if output_text and output_text.strip():
                            parsed = self._parse_json_response(output_text, target_duration)
                            parsed["processing_mode"] = processing_mode
                            parsed["media_resolution"] = media_resolution
                            parsed["thought_steps"] = thought_steps
                            parsed["agentic_calls_count"] = agentic_calls_count
                            logger.info(
                                f"[GeminiVideoUnderstanding] Success ({model_id}): "
                                f"score={parsed.get('alignment_score')}, interval={parsed.get('best_start_mm_ss')}-{parsed.get('best_end_mm_ss')}"
                            )
                            return parsed
                    except Exception as interaction_err:
                        logger.warning(
                            f"[GeminiVideoUnderstanding] interactions.create on {model_id} failed: {interaction_err}. "
                            f"Trying generate_content fallback..."
                        )
                        # Fallback to generate_content
                        try:
                            contents = []
                            if video_file:
                                contents.append(types.Part.from_uri(file_uri=video_file.uri, mime_type="video/mp4"))
                            elif is_url:
                                contents.append(types.Part.from_uri(file_uri=video_path, mime_type="video/mp4"))
                            elif use_inline and inline_base64:
                                contents.append(types.Part.from_bytes(data=base64.b64decode(inline_base64), mime_type="video/mp4"))
                            contents.append(types.Part.from_text(text=prompt))

                            res = client.models.generate_content(
                                model=model_id,
                                contents=contents,
                            )
                            if res and getattr(res, "text", None):
                                parsed = self._parse_json_response(res.text, target_duration)
                                parsed["processing_mode"] = processing_mode
                                parsed["media_resolution"] = media_resolution
                                parsed["thought_steps"] = []
                                parsed["agentic_calls_count"] = 0
                                logger.info(f"[GeminiVideoUnderstanding] generate_content fallback success ({model_id})")
                                return parsed
                        except Exception as gen_err:
                            errors.append(gen_err)
                            continue

            except Exception as key_err:
                logger.warning(f"[GeminiVideoUnderstanding] Key failed: {key_err}")
                errors.append(key_err)
                continue

        # Heuristic fallback if all keys/models failed
        logger.warning(f"[GeminiVideoUnderstanding] All calls failed ({len(errors)} errors); using heuristic fallback")
        return {
            "is_relevant": True,
            "alignment_score": 6.5,
            "best_start_timestamp": 0.0,
            "best_end_timestamp": target_duration,
            "best_start_mm_ss": "00:00",
            "best_end_mm_ss": f"{int(target_duration//60):02d}:{int(target_duration%60):02d}",
            "visual_summary": "Heuristic fallback",
            "reasoning": "Gemini API unavailable or rate-limited",
            "processing_mode": processing_mode,
            "media_resolution": media_resolution,
            "thought_steps": [],
            "agentic_calls_count": 0,
        }

    def _parse_json_response(self, text: str, target_duration: float) -> dict[str, Any]:
        """Parse structured alignment response with resilience against markdown formatting and MM:SS timestamps."""
        clean = text.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:])
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()

        data: dict[str, Any] = {}
        try:
            data = json.loads(clean)
        except Exception:
            start = clean.find("{")
            end = clean.rfind("}")
            if start != -1 and end != -1:
                try:
                    data = json.loads(clean[start : end + 1])
                except Exception:
                    pass

        score = float(data.get("alignment_score") or 7.0)

        # Helper to parse MM:SS or float
        def _parse_ts(val: Any, default: float) -> float:
            if val is None:
                return default
            if isinstance(val, (int, float)):
                return float(val)
            s = str(val).strip()
            if ":" in s:
                parts = s.split(":")
                try:
                    if len(parts) == 2:
                        return float(parts[0]) * 60 + float(parts[1])
                    if len(parts) == 3:
                        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                except Exception:
                    return default
            try:
                return float(s)
            except Exception:
                return default

        start_ts = max(0.0, _parse_ts(data.get("best_start_timestamp"), 0.0))
        end_ts = max(start_ts + 2.0, _parse_ts(data.get("best_end_timestamp"), start_ts + target_duration))

        start_mm_ss = data.get("best_start_mm_ss") or f"{int(start_ts//60):02d}:{int(start_ts%60):02d}"
        end_mm_ss = data.get("best_end_mm_ss") or f"{int(end_ts//60):02d}:{int(end_ts%60):02d}"

        return {
            "is_relevant": bool(data.get("is_relevant", score >= 5.0)),
            "alignment_score": min(10.0, max(0.0, score)),
            "best_start_timestamp": start_ts,
            "best_end_timestamp": end_ts,
            "best_start_mm_ss": start_mm_ss,
            "best_end_mm_ss": end_mm_ss,
            "visual_summary": str(data.get("visual_summary") or "Visual scene alignment"),
            "reasoning": str(data.get("reasoning") or "Evaluated via Gemini Video Understanding"),
        }

    async def align_scene_footage(
        self,
        scene: dict,
        local_footage_path: str,
        topic: str = "",
        processing_mode: str = "agentic",
        media_resolution: str = "low",
        fps: Optional[float] = None,
        start_offset: Optional[float] = None,
        end_offset: Optional[float] = None,
    ) -> dict:
        """Run Video Understanding on a downloaded footage file and update scene timestamps."""
        target_duration = float(scene.get("duration_estimate") or 6.5)
        narration = scene.get("narration", "")
        visual_goal = scene.get("visual", "")

        analysis = await self.analyze_footage_alignment(
            video_path=local_footage_path,
            narration=narration,
            visual_goal=visual_goal,
            topic=topic,
            target_duration=target_duration,
            processing_mode=processing_mode,
            media_resolution=media_resolution,
            fps=fps,
            start_offset=start_offset,
            end_offset=end_offset,
        )

        # Update scene with agentic timestamp and analysis
        scene["agentic_alignment"] = analysis
        if analysis.get("best_start_timestamp") is not None:
            scene["start_timestamp"] = float(analysis["best_start_timestamp"])
        if analysis.get("best_end_timestamp") is not None:
            scene["end_timestamp"] = float(analysis["best_end_timestamp"])
        if analysis.get("best_start_mm_ss"):
            scene["start_mm_ss"] = analysis["best_start_mm_ss"]
        if analysis.get("best_end_mm_ss"):
            scene["end_mm_ss"] = analysis["best_end_mm_ss"]
        if analysis.get("alignment_score") is not None:
            scene["alignment_score"] = float(analysis["alignment_score"])
        if analysis.get("visual_summary"):
            scene["visual_summary"] = analysis["visual_summary"]
        if analysis.get("reasoning"):
            scene["alignment_reasoning"] = analysis["reasoning"]

        logger.info(
            f"[GeminiAgenticVideo] Scene {scene.get('id')} aligned: "
            f"score={analysis.get('alignment_score')}/10, start={scene.get('start_timestamp')}s ({scene.get('start_mm_ss')})"
        )
        return scene

    async def derive_contextual_queries(
        self,
        keyword: str,
        subtitle_text: str,
        context: str = "",
        placement: str = "behind_person",
    ) -> list[str]:
        """Use Gemini Agentic Subtitle Reasoning to generate concrete English visual stock queries."""
        sub = (subtitle_text or "").strip()
        ctx = (context or "").strip()
        kw = (keyword or "").strip()

        combined_speech = f"{sub} {ctx}".strip()
        if not combined_speech and not kw:
            return []

        keys = self._key_rotator.keys
        if keys:
            prompt = f"""Kamu visual researcher & director video pendek profesional dengan kemampuan Agentic Video Understanding.
Tugasmu adalah menganalisa ucapan pembicara pada potongan video berikut, memahami konteks topiknya secara mendalam, dan merumuskan 3-4 kueri pencarian video stock bahasa Inggris (Pexels/Pixabay) yang SANGAT KONKRET dan RELEVAN untuk ditampilkan sebagai B-roll ({placement}).

KATA KUNCI AWAL: {kw or "(none)"}
TEKS SUBTITLE / UCAPAN PEMBICARA DI DETIK INI:
"{combined_speech}"
PLACEMENT: {placement} (video latar di belakang pembicara, pembicara tetap terlihat di depan)

PANDUAN VISUAL CONCRETE (SANGAT PENTING):
1. Pahami apa yang sebenarnya sedang diceritakan atau dianalogikan pembicara.
2. DILARANG KERAS visual abstrak tanpa makna (DILARANG: neuron, sel saraf, brain synapse, bola-bola bercahaya kuning hitam, partikel abstrak acak).
3. DILARANG kueri generik seperti "aesthetic", "cinematic", "mood". Berikan nama benda, tempat, atau aktivitas nyata!
4. Kueri harus dalam BAHASA INGGRIS (3-6 kata per kueri) agar mesin pencari video stock internasional dapat menemukannya dengan akurat.

OUTPUT RAW JSON ONLY (tanpa markdown):
{{"queries": ["english query 1", "english query 2", "english query 3"]}}"""

            for k in keys:
                try:
                    client = genai.Client(api_key=k)
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=self._model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.2,
                            response_mime_type="application/json",
                        ),
                    )
                    text = getattr(response, "text", "") or ""
                    data = json.loads(text)
                    queries = data.get("queries", [])
                    if isinstance(queries, list) and queries:
                        clean_queries = [
                            q.strip().lower()
                            for q in queries
                            if isinstance(q, str) and q.strip() and not any(b in q.lower() for b in self.BANNED_VISUAL_TERMS)
                        ]
                        if clean_queries:
                            logger.info(
                                f"[GeminiAgenticVideo] Subtitle '{combined_speech[:40]}' -> "
                                f"Queries: {clean_queries}"
                            )
                            return clean_queries
                except Exception as exc:
                    logger.debug(f"[GeminiAgenticVideo] Key failed: {exc}")
                    continue

        return self._fallback_heuristic_queries(kw, combined_speech)

    def verify_candidate(
        self,
        candidate_title: str,
        candidate_tags: str,
    ) -> bool:
        """Verify that candidate footage is NOT banned or abstract nonsense."""
        blob = f"{candidate_title} {candidate_tags}".lower()
        if any(banned in blob for banned in self.BANNED_VISUAL_TERMS):
            logger.warning(f"[GeminiAgenticVideo] Rejected candidate with banned term: '{blob[:60]}'")
            return False
        return True

    def _fallback_heuristic_queries(self, keyword: str, spoken_text: str) -> list[str]:
        """Deterministic fallback when Gemini API is offline."""
        from src.infrastructure.pexels_client import ID_TO_EN_VISUAL_MAP, expand_visual_queries

        blob = f"{keyword} {spoken_text}".lower()
        found: list[str] = []

        for k, v in ID_TO_EN_VISUAL_MAP.items():
            if re.search(rf"\b{re.escape(k)}\b", blob):
                if v not in found:
                    found.append(v)
            if len(found) >= 4:
                break

        if not found and keyword:
            found = expand_visual_queries(keyword)

        return [q for q in found if not any(b in q for b in self.BANNED_VISUAL_TERMS)]
