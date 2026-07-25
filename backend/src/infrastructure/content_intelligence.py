"""Content intelligence helpers for smart layout decisions.

This module intentionally stays lightweight: it combines metadata/title,
transcript text, and AI clip hints into a deterministic profile. The visual
engine still makes the final face-count/layout call, but this profile tells it
which strategy to prefer when Auto Grid is enabled.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


@dataclass
class ContentProfile:
    content_type: str = "general"
    confidence: float = 0.0
    source: str = "unknown"
    signals: list[str] = field(default_factory=list)
    autogrid_enabled: bool = False
    grid_strategy: str = "disabled"
    force_grid: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContentIntelligence:
    """Classify video content from metadata/transcript for smart features."""

    GAMING_TERMS = {
        "game", "gaming", "gameplay", "gamer", "streamer", "streaming",
        "facecam", "let's play", "lets play", "walkthrough", "playthrough",
        "speedrun", "esports", "ranked", "rank push", "mabar", "killstreak",
        "boss fight", "fps", "rpg", "mmorpg", "battle royale", "clutch",
        "valorant", "mobile legends", "mlbb", "pubg", "free fire", "ff",
        "minecraft", "roblox", "fortnite", "dota", "league of legends",
        "genshin", "honkai", "apex legends", "call of duty", "cod",
        "warzone", "fifa", "ea fc", "steam", "playstation", "ps5", "xbox",
        "nintendo", "switch",
    }
    PODCAST_TERMS = {
        "podcast", "interview", "wawancara", "talk show", "talkshow",
        "ngobrol", "obrolan", "bincang", "diskusi", "host", "co host",
        "co-host", "guest", "bintang tamu", "narasumber", "episode",
        "panel", "debat", "roundtable", "conversation", "studio",
        "speaker", "pembawa acara", "moderator", "tanya jawab", "q&a",
        "qa", "podcaster", "mic", "mikrofon", "live talk",
    }
    TALKING_HEAD_TERMS = {
        "tutorial", "review", "reaction", "commentary", "opini", "cerita",
        "storytime", "explainer", "tips", "edukasi", "motivasi",
        "cara", "how to", "step by step", "belajar", "rahasia",
        "fakta", "penjelasan", "analisa", "analisis",
    }
    # Soft dialogue cues (transcript-heavy multi-turn chat)
    DIALOGUE_CUES = {
        "iya", "betul", "benar", "setuju", "menurut saya", "menurutku",
        "kamu", "anda", "gue", "elu", "bro", "sis", "guys",
        "you know", "i mean", "right?", "exactly", "so basically",
    }

    def detect(
        self,
        *,
        metadata: dict[str, Any] | None = None,
        transcript_text: str = "",
        clip_hints: Iterable[dict[str, Any]] | None = None,
        autogrid_enabled: bool = False,
    ) -> ContentProfile:
        metadata = metadata or {}
        text_parts: list[str] = []

        for key in ("title", "description", "channel", "category"):
            value = metadata.get(key)
            if value:
                text_parts.append(str(value))

        tags = metadata.get("tags")
        if isinstance(tags, (list, tuple)):
            text_parts.extend(str(tag) for tag in tags)
        elif tags:
            text_parts.append(str(tags))

        if transcript_text:
            text_parts.append(transcript_text[:24000])

        if clip_hints:
            for hint in clip_hints:
                for key in ("content_type", "hook", "reason", "speaker_energy"):
                    value = hint.get(key)
                    if value:
                        text_parts.append(str(value))

        text = self._normalise(" ".join(text_parts))
        if not text:
            return ContentProfile(
                autogrid_enabled=autogrid_enabled,
                grid_strategy="visual_auto" if autogrid_enabled else "disabled",
                reason="no_metadata_or_transcript",
            )

        scores = {
            "gaming": self._score_terms(text, self.GAMING_TERMS),
            "podcast": self._score_terms(text, self.PODCAST_TERMS),
            "talking_head": self._score_terms(text, self.TALKING_HEAD_TERMS),
        }
        # Transcript dialogue density → podcast soft boost
        dialogue_hits = self._score_terms(text, self.DIALOGUE_CUES)
        if dialogue_hits >= 6:
            scores["podcast"] += min(6, dialogue_hits // 2)

        # Clip hints: multi-speaker energy / interview labels
        if clip_hints:
            for hint in clip_hints:
                ct = str(hint.get("content_type") or "").lower()
                if any(k in ct for k in ("podcast", "interview", "debate", "talk")):
                    scores["podcast"] += 4
                if "gaming" in ct or "gameplay" in ct:
                    scores["gaming"] += 4
                if any(k in ct for k in ("tutorial", "review", "explainer")):
                    scores["talking_head"] += 3

        content_type, score = max(scores.items(), key=lambda item: item[1])
        confidence = min(1.0, score / 8.0)

        if score <= 0:
            # Force soft classify from length/dialogue rather than dead general@0
            if dialogue_hits >= 3:
                content_type = "podcast"
                score = max(2, dialogue_hits)
                confidence = min(0.35, score / 12.0)
            elif len(text) > 400:
                content_type = "talking_head"
                score = 2
                confidence = 0.2
            else:
                content_type = "general"
                confidence = 0.0

        signals = self._matched_terms(text, {
            "gaming": self.GAMING_TERMS,
            "podcast": self.PODCAST_TERMS | self.DIALOGUE_CUES,
            "talking_head": self.TALKING_HEAD_TERMS,
        }.get(content_type, set()))

        grid_strategy = "disabled"
        force_grid = False
        reason = f"{content_type}_score_{score}"

        if autogrid_enabled:
            if content_type == "gaming" and confidence >= 0.2:
                grid_strategy = "gaming_gameplay_facecam"
                force_grid = True
                reason = "gaming_content_game_top_person_bottom"
            elif content_type == "podcast" and confidence >= 0.15:
                grid_strategy = "speaker_grid_auto"
                reason = "podcast_content_visual_face_count"
            else:
                grid_strategy = "visual_auto"
                reason = "visual_face_count"

        return ContentProfile(
            content_type=content_type,
            confidence=round(confidence, 3),
            source="metadata_transcript",
            signals=signals[:12],
            autogrid_enabled=autogrid_enabled,
            grid_strategy=grid_strategy,
            force_grid=force_grid,
            reason=reason,
        )

    def _score_terms(self, text: str, terms: set[str]) -> int:
        score = 0
        for term in terms:
            if " " in term or "-" in term:
                if term in text:
                    score += 3
            elif re.search(rf"\b{re.escape(term)}\b", text):
                score += 2
        return score

    def _matched_terms(self, text: str, terms: set[str]) -> list[str]:
        found = []
        for term in sorted(terms):
            if (" " in term or "-" in term) and term in text:
                found.append(term)
            elif re.search(rf"\b{re.escape(term)}\b", text):
                found.append(term)
        return found

    def _normalise(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r"https?://\S+", " ", text)
        text = re.sub(r"[_|/]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
