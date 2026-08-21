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


STORY_SYSTEM_PROMPT = """You are an expert AI video director and scriptwriter for viral vertical (9:16) short-form videos (TikTok, Instagram Reels, YouTube Shorts).
Your job is to create compelling, highly dynamic short-form video scripts from a given topic.

You must output VALID JSON only. No markdown, no explanation outside JSON.

The video will be rendered as a vertical (9:16) short-form video with:
- AI-generated narration (text-to-speech)
- High visual diversity of stock footage from YouTube, Pexels, and Pixabay matching each scene
- Subtitles auto-generated from narration
- Background music

Rules for High Retention & Target Duration Compliance:
1. THE HOOK (first 3 seconds): Must be punchy, curiosity-inducing, and visually explosive.
2. DYNAMIC & ASYMMETRICAL PACING: Vary the rhythm organically:
   - Use rapid 2.5s - 4.0s punchy cuts for the opening hook, fast action, and sudden twists.
   - Use medium 4.5s - 7.5s cuts for regular progression and character/subject focus.
   - Use immersive 8.0s - 12.0s shots for deep storytelling, technical explanations, or cinematic wide vistas.
3. TOTAL DURATION & NARRATION DENSITY (CRITICAL):
   - Spoken English/Indonesian speed is ~2.3 - 2.5 words per second.
   - The total word count across all scenes MUST reach the requested target word count so the final video matches the requested duration. Do not generate ultra-short 1-sentence summaries.
4. SPECIFIC VISUAL SEARCH QUERIES IN ENGLISH:
   - Provide 3 distinct, highly descriptive English visual search queries per scene (e.g. "bioluminescent jellyfish underwater abyss dark ocean 4k", "deep sea submersible robotics camera cinematic") even if the script narration is in Indonesian. Stock video engines index primarily in English.
5. HIGH VISUAL DIVERSITY: Never repeat visual concepts across adjacent scenes. Alternate between wide drone shots, macro close-ups, high-energy action, dramatic angles, and vivid environments.
6. SCENE COUNT: Generate {num_scenes} distinct scenes matching the target duration.
7. STRICT RULE: NEVER include generic subscribe, like, follow, or channel CTA. The final scene MUST be an insightful, memorable takeaway directly related to the topic."""

STORY_USER_PROMPT = """Create a dynamic, rich vertical video script about: "{topic}"

Target duration: {target_duration} seconds (approximately {word_count} words of narration total)
Number of scenes to generate: {num_scenes} scenes

Additional instructions: {instructions}

Output this exact JSON structure:
{{
  "title": "Video title (short, catchy, max 6 words)",
  "hook": "The opening hook text (first 3 seconds, must grab instant attention)",
  "mood": "overall mood (dramatic, educational, mysterious, inspiring, funny, energetic)",
  "target_duration": {target_duration},
  "scenes": [
    {{
      "id": 1,
      "narration": "The spoken narration for this scene (rich and descriptive, approximately {words_per_scene} words to maintain pacing)",
      "visual": "Concrete description of the exact visual footage and camera movement to display",
      "search_queries": [
        "cinematic 4k specific visual query in English",
        "action motion drone stock b-roll query in English",
        "subject macro footage query in English"
      ],
      "duration_estimate": 6.5,
      "transition": "cut|zoom|fade"
    }}
  ]
}}

Important Guidelines:
- Narration Volume: To meet the {target_duration}s duration, ensure all {num_scenes} scenes have complete, engaging storytelling sentences (total ~{word_count} words across the script).
- Search Queries: MUST always be in descriptive English keywords for stock video indexing (Pexels, Pixabay, YouTube).
- First scene is the opening HOOK.
- Final scene is a punchy, thought-provoking conclusion or takeaway. No CTAs."""


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
            # Auto-calculate: minimum 6 scenes for 45-120s target videos with balanced pacing (~6.5 - 8.0s per scene)
            calculated_scenes = max(6, min(16, int(round(target_duration / 7.0))))
            num_scenes = calculated_scenes

        # Approximate word count for target duration (2.3 words/sec)
        word_count = max(50, int(target_duration * 2.3))
        words_per_scene = max(12, int(word_count / max(1, num_scenes)))

        prompt = STORY_USER_PROMPT.format(
            topic=topic,
            target_duration=target_duration,
            word_count=word_count,
            num_scenes=num_scenes,
            words_per_scene=words_per_scene,
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
                    max_tokens=8192,
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
            
            # Dynamic duration computation based on narration or AI estimate (2.5s - 12s)
            dur_est = scene.get("duration_estimate")
            if dur_est is None or not isinstance(dur_est, (int, float)):
                words = len(raw_narration.split())
                scene["duration_estimate"] = max(2.5, min(12.0, round(words / 2.5, 1))) if words > 0 else 5.0
            else:
                scene["duration_estimate"] = max(2.0, min(14.0, float(dur_est)))

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

        # Enforce minimum 6 scenes (for 45-120s final videos) by splitting long scenes into distinct visual beats
        if len(valid_scenes) < 6 and valid_scenes:
            expanded: list[dict] = []
            for sc in valid_scenes:
                narr = sc.get("narration", "").strip()
                sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', narr) if s.strip()]
                if len(sentences) >= 2 and (len(expanded) + len(valid_scenes) - len(expanded)) < 8:
                    mid = len(sentences) // 2
                    p1_narr = " ".join(sentences[:mid]).strip()
                    p2_narr = " ".join(sentences[mid:]).strip()

                    sq = sc.get("search_queries", [])
                    sq1 = [sq[0]] if sq else [sc.get("visual", "")]
                    sq2 = sq[1:] if len(sq) > 1 else [f"cinematic detail {sc.get('visual', '')[:50]}"]

                    sc1 = dict(sc)
                    sc1["narration"] = p1_narr
                    sc1["search_queries"] = sq1
                    sc1["duration_estimate"] = max(3.0, round(len(p1_narr.split()) / 2.3, 1))

                    sc2 = dict(sc)
                    sc2["narration"] = p2_narr
                    sc2["search_queries"] = sq2
                    sc2["visual"] = f"Close up / dynamic angle of {sc.get('visual', '')[:60]}"
                    sc2["duration_estimate"] = max(3.0, round(len(p2_narr.split()) / 2.3, 1))

                    expanded.append(sc1)
                    expanded.append(sc2)
                else:
                    expanded.append(sc)

            # If still < 6, split longest scenes by word count
            while len(expanded) < 6 and expanded:
                longest_idx = max(range(len(expanded)), key=lambda idx: len(expanded[idx].get("narration", "").split()))
                target = expanded[longest_idx]
                words = target.get("narration", "").split()
                if len(words) >= 6:
                    mid = len(words) // 2
                    w1 = " ".join(words[:mid])
                    w2 = " ".join(words[mid:])

                    s1 = dict(target)
                    s1["narration"] = w1
                    s1["duration_estimate"] = max(2.5, round(len(w1.split()) / 2.3, 1))

                    s2 = dict(target)
                    s2["narration"] = w2
                    s2["visual"] = f"Cinematic perspective cut: {target.get('visual', '')[:50]}"
                    s2["search_queries"] = [f"cinematic broll {w2[:30]}", target.get("visual", "")[:50]]
                    s2["duration_estimate"] = max(2.5, round(len(w2.split()) / 2.3, 1))

                    expanded = expanded[:longest_idx] + [s1, s2] + expanded[longest_idx + 1:]
                else:
                    break

            for idx, sc in enumerate(expanded):
                sc["id"] = idx + 1
            valid_scenes = expanded

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

    async def curate_scene_footages(self, scenes: list[dict]) -> list[dict]:
        """AI Video Director Curation Pass: evaluate candidate footage options per scene and pick the most contextually relevant video.

        Args:
            scenes: List of scene dictionaries with 'narration', 'visual', and 'footage_candidates'.

        Returns:
            Updated scenes list with 'selected_footage' set to the AI-curated best match.
        """
        if not scenes:
            return scenes

        curation_payload = []
        for s in scenes:
            cands = s.get("footage_candidates", [])
            if not cands:
                continue
            cand_summaries = []
            for idx, c in enumerate(cands[:6]):
                cand_summaries.append({
                    "option_index": idx,
                    "video_id": c.get("video_id"),
                    "title": c.get("title", "")[:80],
                    "platform": c.get("platform", ""),
                    "query": c.get("query", ""),
                })
            curation_payload.append({
                "scene_id": s.get("id"),
                "narration": s.get("narration", "")[:120],
                "visual_goal": s.get("visual", "")[:120],
                "options": cand_summaries,
            })

        if not curation_payload:
            return scenes

        prompt = (
            "You are an award-winning video director and documentary film editor.\n"
            "Evaluate the candidate stock videos for each scene and pick the ONE option that best matches "
            "the visual goal, narrative context, and mood of that scene.\n\n"
            f"Scenes and Candidates:\n{json.dumps(curation_payload, indent=2)}\n\n"
            "Output JSON mapping scene_id to the chosen option_index and reasoning:\n"
            '{\n  "curation": [\n    {"scene_id": 1, "chosen_option_index": 0, "reason": "Accurately depicts dark ocean submarine"}\n  ]\n}'
        )

        try:
            raw_response = self._call_llm(prompt, attempt=0)
            parsed = self._parse_curation_response(raw_response)
            choice_map = {
                item["scene_id"]: item["chosen_option_index"]
                for item in parsed.get("curation", [])
                if isinstance(item, dict) and "scene_id" in item and "chosen_option_index" in item
            }

            for s in scenes:
                s_id = s.get("id")
                cands = s.get("footage_candidates", [])
                if s_id in choice_map and cands:
                    chosen_idx = choice_map[s_id]
                    if isinstance(chosen_idx, int) and 0 <= chosen_idx < len(cands):
                        s["selected_footage"] = cands[chosen_idx]
                        s["footage_source"] = cands[chosen_idx]
                        logger.info(
                            f"story_agent (AI Director): Curated scene {s_id} -> '{cands[chosen_idx].get('title', '')[:50]}'"
                        )

        except Exception as cur_err:
            logger.warning(f"story_agent: AI Director curation pass fallback ({cur_err})")

        return scenes

    def _parse_curation_response(self, raw: str) -> dict:
        """Parse AI curation JSON response."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            return json.loads(text)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start : end + 1])
                except Exception:
                    pass
        return {}


class StoryGenerationError(Exception):
    """Raised when story generation fails."""
    pass
