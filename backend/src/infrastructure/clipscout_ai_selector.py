"""ClipScout AI Video Selector — 9router CliperHub selects best footage.

Uses the 9router CliperHub combo model to intelligently select the best
video from ClipScout search results based on relevance, license, duration,
and platform preferences.

Fallback: If AI selection fails, picks the video with highest relevanceScore.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from src.config import settings
from src.domain.entities import VideoCandidate
from src.infrastructure.nine_router_client import get_nine_router_client

logger = logging.getLogger(__name__)


class ClipScoutAISelector:
    """AI-powered video selection from ClipScout results.

    Uses 9router CliperHub combo model to evaluate and select the best
    video candidate per B-roll segment.
    """

    def __init__(self):
        # Prefer AI-layer model, then main combo — always CliperHub from .env
        self._model = (
            settings.NINE_ROUTER_AI_LAYER_MODEL
            or settings.NINE_ROUTER_MODEL
            or settings.nine_router_model
        )

    def select_best(
        self,
        candidates: list[VideoCandidate],
        keyword: str,
        required_duration: float = 2.0,
    ) -> Optional[VideoCandidate]:
        """Select the best video from candidates using AI.

        Falls back to highest relevanceScore if AI fails.
        """
        if not candidates:
            return None

        valid_candidates = [
            c for c in candidates
            if c.duration_seconds >= required_duration
        ]
        if not valid_candidates:
            valid_candidates = candidates

        try:
            client = get_nine_router_client()
            if not client.is_configured:
                logger.warning("clipscout_ai: 9router not configured, using relevance fallback")
                return self._fallback_select(valid_candidates, keyword)

            prompt = self._build_prompt(valid_candidates, keyword, required_duration)
            raw_response = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self._model,
                temperature=0.1,
                max_tokens=400,
                response_format={"type": "json_object"},
            )

            selected = self._parse_response(raw_response, valid_candidates)
            if selected:
                logger.info(
                    f"clipscout_ai: selected '{selected.id}' ({selected.platform}) "
                    f"for keyword '{keyword}' (score={selected.relevance_score})"
                )
                return selected

        except Exception as exc:
            logger.warning(f"clipscout_ai: AI selection failed ({exc}), using relevance fallback")

        return self._fallback_select(valid_candidates, keyword)


    def _build_prompt(
        self,
        candidates: list[VideoCandidate],
        keyword: str,
        required_duration: float,
    ) -> str:
        """Build the AI selection prompt with candidate metadata."""
        candidates_text = ""
        for i, c in enumerate(candidates):
            license_tag = "royalty-free" if c.license == "royalty-free" else "standard"
            snippet = f" | snippet: \"{c.transcript_snippet[:100]}\"" if c.transcript_snippet else ""
            reason = f" | reason: \"{c.transcript_reason[:100]}\"" if c.transcript_reason else ""
            candidates_text += (
                f"{i+1}. ID: {c.id}\n"
                f"   Title: {c.title}\n"
                f"   Platform: {c.platform} | License: {license_tag}\n"
                f"   Duration: {c.duration_seconds}s | startTimestamp: {c.start_timestamp}s\n"
                f"   Relevance: {c.relevance_score}{snippet}{reason}\n\n"
            )

        return f"""You are a senior B-roll editor. Pick EXACTLY 1 video that best MATCHES the visual keyword.

KEYWORD (must match literally what is shown on screen): "{keyword}"

CANDIDATES:
{candidates_text}

SELECTION RULES (strict):
1. Visual match first: subject in the video must match keyword (object/action/scene). Ignore generic pretty clips.
2. Prefer royalty-free license when relevance is close.
3. Duration >= {required_duration:.1f}s preferred.
4. Prefer pexels/pixabay over youtube when relevance is equal.
5. For youtube: set start_timestamp to the second where the keyword subject is most visible.
6. Reject mismatch (e.g. keyword "fuel nozzle" but clip is city skyline).

OUTPUT — raw JSON only, no markdown, no extra text:
{{"selected_id":"<exact ID from list>","start_timestamp":0,"reason":"one short sentence"}}
"""

    def _parse_json_tolerant(self, raw_response: str) -> dict:
        """Parse model JSON with fence/extra-text/truncation tolerance."""
        text = (raw_response or "").strip()
        if not text:
            return {}

        if text.startswith("```"):
            lines = text.split("\n")
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Strip leading junk before first {
        brace = text.find("{")
        if brace > 0:
            text = text[brace:]
        elif brace < 0:
            # No object — try selected_id bare patterns below
            text = text

        # Prefer raw_decode: accepts trailing junk ("Extra data" cases)
        for candidate in (text,):
            try:
                data, _end = json.JSONDecoder().raw_decode(candidate.lstrip())
                if isinstance(data, dict) and data:
                    return data
            except json.JSONDecodeError:
                pass

        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass

        # Extract first balanced-ish object; also try non-greedy
        for pattern in (r"\{[^{}]*\}", r"\{.*\}"):
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                continue
            chunk = re.sub(r",\s*([}\]])", r"\1", match.group(0))
            try:
                data, _ = json.JSONDecoder().raw_decode(chunk)
                if isinstance(data, dict) and data:
                    return data
            except json.JSONDecodeError:
                open_b = chunk.count("{") - chunk.count("}")
                open_a = chunk.count("[") - chunk.count("]")
                repaired = chunk + ("]" * max(0, open_a)) + ("}" * max(0, open_b))
                repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
                try:
                    data = json.loads(repaired)
                    if isinstance(data, dict) and data:
                        return data
                except json.JSONDecodeError:
                    continue

        # Regex fallback: selected_id with/without quotes
        mid = re.search(
            r'"?selected_id"?\s*[:=]\s*"([^"]+)"',
            text,
            re.IGNORECASE,
        ) or re.search(
            r'"?selected_id"?\s*[:=]\s*([A-Za-z0-9_\-]+)',
            text,
            re.IGNORECASE,
        )
        if mid:
            out: dict = {"selected_id": mid.group(1)}
            mts = re.search(r'"?start_timestamp"?\s*[:=]\s*(-?\d+(?:\.\d+)?)', text)
            if mts:
                out["start_timestamp"] = float(mts.group(1))
            return out

        return {}


    def _parse_response(
        self, raw_response: str, candidates: list[VideoCandidate]
    ) -> Optional[VideoCandidate]:
        """Parse AI response and find matching candidate."""
        try:
            data = self._parse_json_tolerant(raw_response)
            if not data:
                raise ValueError(f"empty/unparseable: {str(raw_response)[:120]!r}")

            selected_id = str(data.get("selected_id", "")).strip()
            start_ts = data.get("start_timestamp")

            if not selected_id:
                raise ValueError("missing selected_id")

            for candidate in candidates:
                if candidate.id == selected_id:
                    if (
                        start_ts is not None
                        and candidate.platform == "youtube"
                        and isinstance(start_ts, (int, float))
                    ):
                        candidate.start_timestamp = int(start_ts)
                    return candidate

            for candidate in candidates:
                if selected_id in candidate.id or candidate.id in selected_id:
                    if start_ts is not None and candidate.platform == "youtube":
                        try:
                            candidate.start_timestamp = int(start_ts)
                        except (TypeError, ValueError):
                            pass
                    return candidate

            # Index fallback: selected_id as "1"/"2"
            if selected_id.isdigit():
                idx = int(selected_id) - 1
                if 0 <= idx < len(candidates):
                    return candidates[idx]

        except Exception as exc:
            logger.warning(f"clipscout_ai: failed to parse AI response: {exc}")

        return None

    def _fallback_select(
        self,
        candidates: list[VideoCandidate],
        keyword: str = "",
    ) -> Optional[VideoCandidate]:
        """Fallback: keyword token match + relevance + license + platform."""
        if not candidates:
            return None

        tokens = {
            t for t in re.findall(r"[a-z0-9]+", (keyword or "").lower()) if len(t) > 2
        }

        def token_hits(c: VideoCandidate) -> float:
            if not tokens:
                return 0.0
            hay = " ".join(
                [
                    c.title or "",
                    c.transcript_snippet or "",
                    c.transcript_reason or "",
                    c.platform or "",
                ]
            ).lower()
            hits = sum(1 for t in tokens if t in hay)
            return hits / max(1, len(tokens))

        def sort_key(c: VideoCandidate) -> tuple:
            license_score = 1 if c.license == "royalty-free" else 0
            platform_score = 1 if c.platform in ("pexels", "pixabay") else 0
            return (token_hits(c), c.relevance_score, license_score, platform_score)

        selected = max(candidates, key=sort_key)
        logger.info(
            f"clipscout_ai: fallback selected '{selected.id}' ({selected.platform}) "
            f"score={selected.relevance_score} keyword_hits={token_hits(selected):.2f}"
        )
        return selected

