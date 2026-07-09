"""AI Layer Generator — Uses 9router to generate dynamic layer events.

This module integrates the configured 9router LLM to analyze transcript + prosody data
and generate AI-enhanced layer events for Remotion rendering.

Capabilities:
- Dynamic animation selection based on text emotion
- VFX/Three.js triggering from prosody peaks
- B-Roll keyword generation with context awareness
- Smart subtitle chunking with highlight detection
- Color palette suggestions based on content mood
"""

import asyncio
import json
import logging
from typing import Any, Optional
from dataclasses import dataclass, asdict

from src.config import settings
from src.domain.entities import CreativeDirection

logger = logging.getLogger(__name__)


@dataclass
class AILayerEvent:
    """AI-generated event for Remotion layers."""
    event_type: str
    start_time: float
    duration: float
    content: dict
    confidence: float = 1.0


@dataclass
class AILayerOutput:
    """Complete AI layer output for a clip."""
    clip_rank: int
    events: list[AILayerEvent]
    color_palette_suggestion: Optional[dict] = None
    animation_override: Optional[dict] = None


class AILayerGenerator:
    """Generates AI-enhanced layer events using Gemini Flash.
    
    Usage:
        generator = AILayerGenerator()
        result = await generator.generate_layer_events(
            transcript=transcript_text,
            words=word_timestamps,
            prosody=prosody_data,
            creative_direction=creative_direction,
        )
    """
    
    SYSTEM_PROMPT = """You are an AI video editor assistant for AutoCliper. Your job is to analyze transcript and audio data, then generate structured layer events for a React/Remotion video renderer.

You MUST output valid JSON that matches this TypeScript interface:

interface AILayerOutput {
  clip_rank: number;
  events: AILayerEvent[];
  color_palette_suggestion?: { primary: string; secondary: string; accent: string };
  animation_override?: { hook_animation?: string; transition_style?: string };
}

interface AILayerEvent {
  event_type: 'THREEJS_EFFECT' | 'COLOR_SHIFT' | 'EMPHASIS_WORD' | 'TRANSITION_HINT' | 'BROLL_KEYWORD';
  start_time: number;  // seconds
  duration: number;    // seconds
  content: {
    effect_name?: string;        // For THREEJS_EFFECT: 'particle_burst', 'camera_shake', 'zoom_punch'
    intensity?: number;          // 0.0 - 1.0
    color_hex?: string;          // For COLOR_SHIFT
    word_index?: number;         // For EMPHASIS_WORD
    transition_type?: string;    // For TRANSITION_HINT: 'fade', 'slide', 'zoom'
    keyword?: string;            // For BROLL_KEYWORD
    asset_suggestion?: string;   // e.g., 'rocket launching', 'confetti explosion'
  };
  confidence: number;  // 0.0 - 1.0
}

Rules:
1. Be conservative - only suggest events when confident (> 0.7)
2. Match event timing to natural speech pauses and emphasis
3. Use 'THREEJS_EFFECT' for high-energy moments (based on prosody peaks)
4. Use 'EMPHASIS_WORD' to highlight important keywords
5. Use 'BROLL_KEYWORD' when visual context would enhance understanding
6. Consider the overall mood and energy_level from creative_direction
7. Keep events non-overlapping when possible
8. Maximum 5 events per 15-second clip

Analyze the transcript and generate appropriate layer events."""

    def __init__(self):
        self.client = None
        self._initialized = False
        
    def _ensure_initialized(self):
        """Lazy initialization of the 9router client."""
        if self._initialized:
            return
            
        if not settings.use_nine_router:
            logger.warning("[AILayer] LLM_PROVIDER is not nine_router")
            return
            
        try:
            from src.infrastructure.nine_router_client import get_nine_router_client

            client = get_nine_router_client()
            if not client.is_configured:
                logger.warning("[AILayer] NINE_ROUTER_BASE_URL not configured")
                return
            self.client = client
            self._initialized = True
            logger.info("[AILayer] 9router initialized")
        except Exception as e:
            logger.error(f"[AILayer] Failed to initialize 9router: {e}")
            
    async def generate_layer_events(
        self,
        clip_rank: int,
        transcript: str,
        words: list[dict],
        prosody: Optional[dict] = None,
        creative_direction: Optional[CreativeDirection] = None,
    ) -> Optional[AILayerOutput]:
        """Generate AI-enhanced layer events for a clip.
        
        Args:
            clip_rank: Clip number
            transcript: Full transcript text
            words: Word-level timestamps from Whisper
            prosody: Prosody analysis (energy peaks, silence gaps)
            creative_direction: Visual identity for the clip
            
        Returns:
            AILayerOutput with events and suggestions, or None on failure
        """
        self._ensure_initialized()
        
        if not self.client:
            logger.warning("[AILayer] Model not initialized, skipping AI layer")
            return None
            
        # Build prompt with context
        prompt = self._build_prompt(
            clip_rank=clip_rank,
            transcript=transcript,
            words=words,
            prosody=prosody,
            creative_direction=creative_direction,
        )
        
        try:
            logger.info(f"[AILayer] Generating events for clip {clip_rank}")
            
            response_text = await self._call_router_json(prompt, max_tokens=2048)

            if not response_text:
                logger.warning(f"[AILayer] Empty response for clip {clip_rank}")
                return None
                
            # Parse JSON response
            data = self._parse_json_response(response_text)
            
            # Convert to AILayerOutput
            events = [
                AILayerEvent(
                    event_type=e.get("event_type", "EMPHASIS_WORD"),
                    start_time=e.get("start_time", 0),
                    duration=e.get("duration", 0.5),
                    content=e.get("content", {}),
                    confidence=e.get("confidence", 0.8),
                )
                for e in data.get("events", [])
                if e.get("confidence", 0) >= 0.7  # Filter low confidence
            ]
            
            output = AILayerOutput(
                clip_rank=clip_rank,
                events=events,
                color_palette_suggestion=data.get("color_palette_suggestion"),
                animation_override=data.get("animation_override"),
            )
            
            logger.info(f"[AILayer] Generated {len(events)} events for clip {clip_rank}")
            return output
            
        except json.JSONDecodeError as e:
            logger.error(f"[AILayer] JSON parse error: {e}")
            return None
        except Exception as e:
            logger.error(f"[AILayer] Generation error: {e}")
            return None
            
    def _build_prompt(
        self,
        clip_rank: int,
        transcript: str,
        words: list[dict],
        prosody: Optional[dict],
        creative_direction: Optional[CreativeDirection],
    ) -> str:
        """Build the prompt for Gemini."""
        
        # Word summary (first 50 words for context)
        word_summary = " ".join([w.get("word", "") for w in words[:50]])
        
        # Prosody peaks
        prosody_info = ""
        if prosody:
            peaks = prosody.get("energy_peaks", [])
            if peaks:
                peak_times = [f"{p.get('time', 0):.1f}s" for p in peaks[:5]]
                prosody_info = f"Energy peaks at: {', '.join(peak_times)}"
                
        # Creative direction
        cd_info = ""
        if creative_direction:
            cd_info = f"""
Current creative direction:
- Mood: {creative_direction.typography_mood}
- Energy: {creative_direction.energy_level}
- Colors: {creative_direction.primary_color} / {creative_direction.secondary_color}
- Hook animation: {creative_direction.hook_animation}
"""
        
        prompt = f"""
Clip #{clip_rank}

Transcript:
"{transcript}"

Word timing summary:
{word_summary}

{prosody_info}

{cd_info}

Generate AI layer events for this clip. Focus on enhancing the viewing experience with subtle effects that complement the content.
"""
        return prompt.strip()
        
    async def generate_broll_keywords(
        self,
        transcript: str,
        max_keywords: int = 5,
    ) -> list[dict]:
        """Generate B-Roll keyword suggestions from transcript.
        
        Returns list of:
        {
            "keyword": "rocket launching",
            "time_suggestion": 5.2,
            "visual_category": "footage",
            "search_prompt": "rocket launching from launchpad, cinematic"
        }
        """
        self._ensure_initialized()
        
        if not self.client:
            return []
            
        prompt = f"""Analyze this transcript and suggest {max_keywords} B-Roll visual keywords that would enhance the video.

Transcript:
"{transcript}"

For each keyword, provide:
1. keyword: Short search term
2. time_suggestion: When to show it (in seconds, estimate based on context)
3. visual_category: "footage", "icon", or "motion_graphic"
4. search_prompt: Detailed search prompt for stock footage APIs

Output as JSON object: {"items": [...]}."""

        try:
            response_text = await self._call_router_json(prompt, max_tokens=1200)
            data = self._parse_json_response(response_text)
            if isinstance(data, dict):
                items = data.get("items", [])
            elif isinstance(data, list):
                items = data
            else:
                items = []
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.error(f"[AILayer] B-Roll generation error: {e}")
            return []
            
    async def analyze_emotion_timeline(
        self,
        words: list[dict],
        transcript: str,
    ) -> list[dict]:
        """Analyze emotion changes throughout the clip.
        
        Returns list of:
        {
            "start_time": 0.0,
            "end_time": 3.5,
            "emotion": "excited",
            "intensity": 0.8,
            "suggested_effect": "particle_burst"
        }
        """
        self._ensure_initialized()
        
        if not self.client:
            return []
            
        prompt = f"""Analyze the emotional tone throughout this transcript and identify emotion segments.

Transcript:
"{transcript}"

Word count: {len(words)}

For each distinct emotional segment, provide:
1. start_time / end_time (seconds)
2. emotion: neutral, excited, serious, playful, dramatic, tense, happy, sad
3. intensity: 0.0 - 1.0
4. suggested_effect: matching Three.js effect

Output as JSON object: {"items": [...]}."""

        try:
            response_text = await self._call_router_json(prompt, max_tokens=1600)
            data = self._parse_json_response(response_text)
            if isinstance(data, dict):
                items = data.get("items", [])
            elif isinstance(data, list):
                items = data
            else:
                items = []
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.error(f"[AILayer] Emotion analysis error: {e}")
            return []

    async def _call_router_json(self, prompt: str, max_tokens: int) -> str:
        """Run a JSON-focused 9router request off the event loop."""
        if not self.client:
            return ""
        return await asyncio.to_thread(
            self.client.chat,
            model=settings.NINE_ROUTER_AI_LAYER_MODEL or settings.nine_router_model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

    def _parse_json_response(self, raw_text: str) -> Any:
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return json.loads(text)


# Singleton instance
_ai_layer_generator: Optional[AILayerGenerator] = None


def get_ai_layer_generator() -> Optional[AILayerGenerator]:
    """Get or create AI layer generator instance."""
    global _ai_layer_generator
    
    if not settings.REMOTION_ENABLE_AI_LAYER:
        return None
        
    if _ai_layer_generator is None:
        _ai_layer_generator = AILayerGenerator()
        
    return _ai_layer_generator
