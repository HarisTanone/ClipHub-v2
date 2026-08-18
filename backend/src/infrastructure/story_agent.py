"""AI Story Agent — Generate structured video story from a topic.

Takes a user topic and generates a complete story breakdown with:
- Title, hook
- Scenes with narration, visual descriptions, and search queries
- Target duration control
- Mood and style hints

Uses 9Router/Gemini as the LLM backend (same as GroqAnalyzer).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)


STORY_SYSTEM_PROMPT = """You are an expert AI video director and scriptwriter.
Your job is to create compelling short-form video scripts (50-90 seconds) from a given topic.

You must output VALID JSON only. No markdown, no explanation outside JSON.

The video will be rendered as a vertical (9:16) short-form video with:
- AI-generated narration (text-to-speech)
- Stock footage from YouTube/Pexels matching each scene
- Subtitles auto-generated from narration
- Background music

Rules:
1. The HOOK (first 3 seconds) must be extremely attention-grabbing
2. Each scene narration should be 1-3 sentences, natural spoken language
3. Search queries should be specific and visual (not abstract concepts)
4. Total narration when spoken should fit within the target duration
5. Scenes should flow logically as a narrative
6. Visual descriptions should be concrete and searchable
7. Generate 6-10 scenes depending on target duration
8. STRICT RULE: NEVER include any generic subscribe, like, follow, share, or channel CTA (e.g. "Jangan lupa subscribe", "Don't forget to subscribe", "Like and subscribe"). The final scene MUST be a strong, punchy takeaway or conclusion related directly to the topic."""

STORY_USER_PROMPT = """Create a video script about: "{topic}"

Target duration: {target_duration} seconds (approximately {word_count} words of narration total)
Number of scenes: {num_scenes}

Additional instructions: {instructions}

Output this exact JSON structure:
{{
  "title": "Video title (short, catchy)",
  "hook": "The opening hook text (first 3 seconds, must grab attention)",
  "mood": "overall mood (dramatic, educational, mysterious, inspiring, funny)",
  "target_duration": {target_duration},
  "scenes": [
    {{
      "id": 1,
      "narration": "The spoken narration for this scene",
      "visual": "Description of what should be shown visually",
      "search_queries": ["youtube search query 1", "youtube search query 2", "stock footage query 3"],
      "duration_estimate": 7,
      "transition": "cut|fade|zoom"
    }}
  ]
}}

Important:
- Each scene's narration should be speakable in about duration_estimate seconds
- Average speaking rate is ~2.5 words per second
- search_queries MUST be highly specific visual YouTube search terms that match the narration context:
  * Use concrete visual nouns: "volcano erupting lava flow", NOT "volcano" alone
  * Include action/motion: "tsunami wave crashing coastline drone footage"
  * Add "footage", "cinematic", "drone", "timelapse", "4K" when appropriate
  * Each query should describe EXACTLY what should appear on screen during that narration
  * Avoid abstract concepts — always describe the VISUAL: "scientist in lab mixing chemicals" not "science experiment"
  * Include 3 search queries per scene: 1 very specific, 1 slightly broader, 1 with "stock footage" suffix
- First scene should be the HOOK
- The final scene must be an insightful, memorable takeaway or punchy conclusion related to the topic. STRICTLY DO NOT mention subscribe, follow, or like buttons."""


class StoryAgent:
    """AI Story Generator — topic to structured scene breakdown.

    Uses the same LLM infrastructure as GroqAnalyzer (9Router or direct Groq).
    """

    def __init__(self):
        self._max_retries = 3

    async def generate_story(
        self,
        topic: str,
        target_duration: int = 0,
        num_scenes: int = 0,
        instructions: str = "",
        language: str = "english",
    ) -> dict:
        """Generate a structured video story from a topic.

        Args:
            topic: The video topic/subject.
            target_duration: Target video duration in seconds (default from config).
            num_scenes: Number of scenes (0 = auto based on duration).
            instructions: Additional user instructions for style/tone.
            language: Narration language (default: english).

        Returns:
            Structured story dict with title, hook, scenes, etc.

        Raises:
            StoryGenerationError on failure.
        """
        if not target_duration:
            target_duration = settings.VIDEO_GEN_TARGET_DURATION

        if not num_scenes:
            # Auto-calculate: ~8 seconds per scene average
            num_scenes = max(5, min(settings.VIDEO_GEN_MAX_SCENES, target_duration // 8))

        # Approximate word count for target duration (2.5 words/sec)
        word_count = int(target_duration * 2.5)

        prompt = STORY_USER_PROMPT.format(
            topic=topic,
            target_duration=target_duration,
            word_count=word_count,
            num_scenes=num_scenes,
            instructions=instructions or "None — use your best judgment",
        )

        last_error: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                raw_response = self._call_llm(prompt, attempt=attempt)
                story = self._parse_response(raw_response, topic)
                story = self._validate_and_fix(story, target_duration)

                if len(story.get("scenes", [])) >= 3:
                    logger.info(
                        f"story_agent: generated '{story.get('title', '')}' — "
                        f"{len(story.get('scenes', []))} scenes, "
                        f"target {target_duration}s (attempt {attempt + 1})"
                    )
                    return story

                logger.warning(
                    f"story_agent: parsed story had too few scenes ({len(story.get('scenes', []))}), "
                    f"retrying attempt {attempt + 1}..."
                )
            except Exception as e:
                last_error = e
                logger.warning(f"story_agent: attempt {attempt + 1} failed: {e}")
                time.sleep(1.5)

        # Fallback to direct Gemini if 9router output failed
        if getattr(settings, "ALLOW_DIRECT_PROVIDER_FALLBACKS", True) and settings.gemini_api_keys:
            try:
                logger.info("story_agent: attempting fallback to direct Gemini")
                raw_gemini = self._call_gemini(prompt)
                story = self._parse_response(raw_gemini, topic)
                story = self._validate_and_fix(story, target_duration)
                if len(story.get("scenes", [])) >= 2:
                    return story
            except Exception as gemini_err:
                logger.error(f"story_agent: direct Gemini fallback failed: {gemini_err}")

        raise StoryGenerationError(f"Story generation failed after {self._max_retries} attempts: {last_error}")

    def _call_llm(self, prompt: str, attempt: int = 0) -> str:
        """Call LLM via 9Router or Gemini fallback."""
        if settings.use_nine_router:
            return self._call_nine_router(prompt, attempt=attempt)
        else:
            return self._call_gemini(prompt)

    def _call_nine_router(self, prompt: str, attempt: int = 0) -> str:
        """Call 9Router for story generation."""
        from src.infrastructure.nine_router_client import get_nine_router_client

        client = get_nine_router_client()
        temp = 0.5 if attempt > 0 else 0.7

        for retry in range(self._max_retries):
            try:
                return client.chat(
                    messages=[
                        {"role": "system", "content": STORY_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    model=settings.get_nine_router("NINE_ROUTER_PASS2_MODEL")
                    or settings.nine_router_model,
                    temperature=temp,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                )
            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "rate" in error_str:
                    wait = min(5 * (2 ** retry), 30)
                    logger.warning(f"story_agent: rate limited, waiting {wait}s")
                    time.sleep(wait)
                    continue

                if retry >= self._max_retries - 1:
                    raise StoryGenerationError(f"LLM call failed: {e}")

                time.sleep(2)

        raise StoryGenerationError("LLM max retries exceeded")

    def _call_gemini(self, prompt: str) -> str:
        """Fallback: call Gemini directly."""
        import httpx

        keys = settings.gemini_api_keys
        if not keys:
            raise StoryGenerationError("No Gemini API key configured")

        api_key = keys[0]
        model = settings.GEMINI_MODEL
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
            f":generateContent?key={api_key}"
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{STORY_SYSTEM_PROMPT}\n\n{prompt}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json",
            },
        }

        for attempt in range(self._max_retries):
            try:
                with httpx.Client(timeout=settings.GEMINI_TIMEOUT) as client:
                    resp = client.post(url, json=payload)

                if resp.status_code == 429:
                    if len(keys) > 1:
                        api_key = keys[(attempt + 1) % len(keys)]
                        url = (
                            f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
                            f":generateContent?key={api_key}"
                        )
                    time.sleep(3 * (attempt + 1))
                    continue

                if resp.status_code != 200:
                    raise StoryGenerationError(
                        f"Gemini API error {resp.status_code}: {resp.text[:200]}"
                    )

                data = resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    raise StoryGenerationError("Gemini returned no candidates")

                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if not parts:
                    raise StoryGenerationError("Gemini returned empty parts")

                return parts[0].get("text", "")

            except httpx.TimeoutException:
                if attempt >= self._max_retries - 1:
                    raise StoryGenerationError("Gemini timeout")
                time.sleep(2)
            except StoryGenerationError:
                raise
            except Exception as e:
                if attempt >= self._max_retries - 1:
                    raise StoryGenerationError(f"Gemini error: {e}")
                time.sleep(2)

        raise StoryGenerationError("Gemini max retries exceeded")

    def _parse_response(self, raw: str, topic: str) -> dict:
        """Parse LLM JSON response to structured story dict with truncated JSON repair."""
        import re

        text = raw.strip()
        # Clean markdown fences
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        # 1. Direct JSON parse
        try:
            story = json.loads(text)
            if isinstance(story, dict) and story.get("scenes"):
                return story
        except json.JSONDecodeError:
            pass

        # 2. Extract outermost JSON block
        start_idx = text.find("{")
        if start_idx != -1:
            candidate = text[start_idx:]
            try:
                story = json.loads(candidate)
                if isinstance(story, dict) and story.get("scenes"):
                    return story
            except json.JSONDecodeError:
                pass

            # 3. Repair truncated JSON structure (unclosed quotes/braces/brackets)
            repaired = self._repair_truncated_json(candidate)
            if repaired:
                try:
                    story = json.loads(repaired)
                    if isinstance(story, dict) and story.get("scenes"):
                        logger.info("story_agent: successfully repaired truncated JSON response")
                        return story
                except json.JSONDecodeError:
                    pass

        # 4. Fallback: Regex extraction of scenes if JSON is heavily corrupted
        story = self._extract_story_with_regex(text, topic)
        if story and story.get("scenes"):
            logger.info("story_agent: recovered story using regex extraction fallback")
            return story

        raise StoryGenerationError(f"No JSON found in LLM response: {text[:300]}")

    def _repair_truncated_json(self, json_str: str) -> Optional[str]:
        """Attempt to repair truncated JSON by closing arrays, objects, and strings."""
        # Prefer cutting back to the last complete scene object if available
        last_scene_end = json_str.rfind("},")
        if last_scene_end != -1:
            cut = json_str[: last_scene_end + 1]
            closed = self._close_json_structure(cut)
            if closed:
                return closed

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
            out += '"'
        out += "".join(reversed(stack))
        return out

    def _extract_story_with_regex(self, text: str, topic: str) -> Optional[dict]:
        """Fallback regex extractor for partial or malformed LLM responses."""
        import re

        title_match = re.search(r'"title"\s*:\s*"([^"]+)"', text)
        hook_match = re.search(r'"hook"\s*:\s*"([^"]+)"', text)
        mood_match = re.search(r'"mood"\s*:\s*"([^"]+)"', text)

        # Find scene blocks
        scene_blocks = re.findall(
            r'\{\s*"id"\s*:\s*(\d+)[^}]*?"narration"\s*:\s*"([^"]+)"(?:[^}]*?"visual"\s*:\s*"([^"]+)")?',
            text,
            re.DOTALL,
        )
        if not scene_blocks:
            return None

        scenes = []
        for match in scene_blocks:
            scene_id = int(match[0])
            narration = match[1].strip()
            visual = match[2].strip() if len(match) > 2 and match[2] else ""
            if narration:
                scenes.append({
                    "id": scene_id,
                    "narration": narration,
                    "visual": visual,
                    "search_queries": [visual] if visual else [topic],
                    "duration_estimate": max(4, int(len(narration.split()) / 2.5)),
                    "transition": "cut",
                })

        if not scenes:
            return None

        return {
            "title": title_match.group(1) if title_match else topic,
            "hook": hook_match.group(1) if hook_match else (scenes[0]["narration"] if scenes else ""),
            "mood": mood_match.group(1) if mood_match else "educational",
            "scenes": scenes,
        }

    def _validate_and_fix(self, story: dict, target_duration: int) -> dict:
        """Validate story structure and fix common issues."""
        # Ensure required fields
        story.setdefault("title", "Untitled")
        story.setdefault("hook", story["scenes"][0].get("narration", ""))
        story.setdefault("mood", "educational")
        story.setdefault("target_duration", target_duration)

        # Validate scenes
        import re

        cta_patterns = [
            r"(?i)\b(jangan\s+lupa\s+(untuk\s+)?(subscribe|like|follow|share|dukung\s+channel\s+ini)[^.!?]*[.!?]?)",
            r"(?i)\b(don'?t\s+forget\s+to\s+(subscribe|like|follow|share)[^.!?]*[.!?]?)",
            r"(?i)\b(subscribe\s+(to\s+(our\s+)?channel|for\s+more|now)[^.!?]*[.!?]?)",
            r"(?i)\b(like\s+and\s+subscribe[^.!?]*[.!?]?)",
            r"(?i)\b(follow\s+for\s+more[^.!?]*[.!?]?)",
            r"(?i)\b(klik\s+tombol\s+subscribe[^.!?]*[.!?]?)",
        ]

        valid_scenes = []
        for i, scene in enumerate(story["scenes"]):
            if not isinstance(scene, dict):
                continue

            scene.setdefault("id", i + 1)
            raw_narration = str(scene.get("narration") or "").strip()

            # Sanitize subscribe / CTA phrases
            for pat in cta_patterns:
                raw_narration = re.sub(pat, "", raw_narration).strip()

            scene["narration"] = raw_narration
            scene.setdefault("visual", "")
            scene.setdefault("search_queries", [])
            scene.setdefault("duration_estimate", 7)
            scene.setdefault("transition", "cut")

            # Ensure search_queries is a list
            if isinstance(scene["search_queries"], str):
                scene["search_queries"] = [scene["search_queries"]]

            # Generate search queries from visual if empty
            if not scene["search_queries"] and scene["visual"]:
                scene["search_queries"] = [scene["visual"][:80]]

            # Skip empty scenes
            if scene["narration"] or scene["visual"]:
                valid_scenes.append(scene)

        story["scenes"] = valid_scenes

        # Calculate estimated total duration
        total_est = sum(s.get("duration_estimate", 7) for s in valid_scenes)
        story["estimated_duration"] = total_est

        # Warn if way off target
        if total_est > target_duration * 1.3:
            logger.warning(
                f"story_agent: estimated duration {total_est}s exceeds "
                f"target {target_duration}s by >30%"
            )
        elif total_est < target_duration * 0.6:
            logger.warning(
                f"story_agent: estimated duration {total_est}s is <60% of "
                f"target {target_duration}s"
            )

        return story


class StoryGenerationError(Exception):
    """Raised when story generation fails."""
    pass
