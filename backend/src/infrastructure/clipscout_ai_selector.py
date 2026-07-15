"""ClipScout AI Video Selector — 9router CliperHub selects best footage.

Uses the 9router CliperHub combo model to intelligently select the best
video from ClipScout search results based on relevance, license, duration,
and platform preferences.

Fallback: If AI selection fails, picks the video with highest relevanceScore.
"""
from __future__ import annotations

import json
import logging
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
        self._model = settings.NINE_ROUTER_AI_LAYER_MODEL

    def select_best(
        self,
        candidates: list[VideoCandidate],
        keyword: str,
        required_duration: float = 2.0,
    ) -> Optional[VideoCandidate]:
        """Select the best video from candidates using AI.

        Falls back to highest relevanceScore if AI fails.

        Args:
            candidates: List of VideoCandidate from ClipScout.
            keyword: The B-roll keyword/topic for context.
            required_duration: Minimum footage duration needed (seconds).

        Returns:
            Selected VideoCandidate, or None if no candidates.
        """
        if not candidates:
            return None

        # Filter: must have enough duration
        valid_candidates = [
            c for c in candidates
            if c.duration_seconds >= required_duration
        ]
        if not valid_candidates:
            # If none have enough duration, use all and hope for the best
            valid_candidates = candidates

        # Try AI selection
        try:
            client = get_nine_router_client()
            if not client.is_configured:
                logger.warning("clipscout_ai: 9router not configured, using relevance fallback")
                return self._fallback_select(valid_candidates)

            prompt = self._build_prompt(valid_candidates, keyword, required_duration)
            raw_response = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self._model,
                temperature=0.2,
                max_tokens=500,
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

        return self._fallback_select(valid_candidates)

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

        return f"""Kamu adalah video editor profesional. Pilih 1 video TERBAIK untuk B-roll footage dengan keyword: "{keyword}"

KANDIDAT:
{candidates_text}

PRIORITAS PEMILIHAN:
1. License "royalty-free" lebih aman daripada "standard" (tapi standard boleh dipilih jika jauh lebih relevan)
2. relevanceScore tertinggi
3. Durasi minimal {required_duration:.0f} detik
4. Platform pexels/pixabay lebih aman dari youtube (jika score sebanding)
5. Untuk YouTube: tentukan startTimestamp optimal dari snippet/context

OUTPUT JSON:
{{"selected_id": "<video_id>", "start_timestamp": <number>, "reason": "<alasan singkat>"}}
"""

    def _parse_response(
        self, raw_response: str, candidates: list[VideoCandidate]
    ) -> Optional[VideoCandidate]:
        """Parse AI response and find matching candidate."""
        try:
            data = json.loads(raw_response)
            selected_id = str(data.get("selected_id", ""))
            start_ts = data.get("start_timestamp")

            for candidate in candidates:
                if candidate.id == selected_id:
                    # Update startTimestamp if AI suggested a better one (YouTube)
                    if (
                        start_ts is not None
                        and candidate.platform == "youtube"
                        and isinstance(start_ts, (int, float))
                    ):
                        candidate.start_timestamp = int(start_ts)
                    return candidate

            # If exact ID not found, try partial match
            for candidate in candidates:
                if selected_id in candidate.id or candidate.id in selected_id:
                    if start_ts is not None and candidate.platform == "youtube":
                        candidate.start_timestamp = int(start_ts)
                    return candidate

        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning(f"clipscout_ai: failed to parse AI response: {exc}")

        return None

    def _fallback_select(self, candidates: list[VideoCandidate]) -> Optional[VideoCandidate]:
        """Fallback: select video with highest relevanceScore.

        Secondary sort: prefer royalty-free, then pexels/pixabay platform.
        """
        if not candidates:
            return None

        def sort_key(c: VideoCandidate) -> tuple:
            license_score = 1 if c.license == "royalty-free" else 0
            platform_score = 1 if c.platform in ("pexels", "pixabay") else 0
            return (c.relevance_score, license_score, platform_score)

        selected = max(candidates, key=sort_key)
        logger.info(
            f"clipscout_ai: fallback selected '{selected.id}' ({selected.platform}) "
            f"score={selected.relevance_score}"
        )
        return selected
