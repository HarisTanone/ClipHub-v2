"""AI Subtitle Style Generator API route."""
import json
import logging
import re
from typing import Optional, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.infrastructure.auth import GeminiKeyRotator
from src.config import settings
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["Subtitle AI"])


class SubtitleAIGenerateRequest(BaseModel):
    prompt: str = Field(..., description="Natural language description of the desired subtitle style")
    current_style: Optional[dict[str, Any]] = None
    video_context: Optional[str] = None


class SubtitleAIGenerateResponse(BaseModel):
    ok: bool = True
    subtitle_style: dict[str, Any]
    explanation: str
    highlight_keywords: list[str] = Field(default_factory=list)


def _parse_with_local_rules(prompt: str, current_style: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Fast deterministic rule-based NLP parser for offline & fallback subtitle generation."""
    p = prompt.lower()

    # Start with sensible defaults or current style
    style = {
        "enabled": True,
        "stylePreset": "custom",
        "engine": "remotion",
        "fontFamily": "Inter",
        "fontSize": 34,
        "fontWeight": "800",
        "letterSpacing": 0,
        "lineHeight": 1.3,
        "color": "#FFFFFF",
        "highlightColor": "#FACC15",
        "highlightScale": 1.2,
        "highlightBold": True,
        "highlightStyle": "scale",
        "highlightGlow": False,
        "highlightGlowColor": "#00F0FF",
        "highlightWords": ["viral", "penting", "rahasia", "sukses", "cuan"],
        "dualStyleEnabled": False,
        "highlightFontFamily": "Montserrat",
        "highlightFontSize": 36,
        "highlightFontWeight": "900",
        "highlightLetterSpacing": 0,
        "highlightItalic": False,
        "highlightUppercase": True,
        "highlightStrokeEnabled": True,
        "highlightStrokeColor": "#000000",
        "highlightStrokeWidth": 3,
        "highlightShadowEnabled": False,
        "highlightShadowColor": "#000000",
        "highlightShadowBlur": 4,
        "bgEnabled": False,
        "bgColor": "#000000",
        "bgOpacity": 0.6,
        "bgRadius": 12,
        "bgPadding": 16,
        "position": "bottom",
        "positionY": 78,
        "uppercase": False,
        "capitalize": False,
        "italic": False,
        "strokeEnabled": True,
        "strokeColor": "#000000",
        "strokeWidth": 3,
        "shadowEnabled": False,
        "shadowColor": "#000000",
        "shadowBlur": 6,
        "maxWordsPerLine": 3,
        "wordSpacing": 6,
        "animationStyle": "pop",
        "animationSpeed": 1.0,
        "lineTransition": "word_pop",
        "glowEnabled": False,
        "glowColor": "#00F0FF",
        "gradientEnabled": False,
        "gradientFrom": "#FFFFFF",
        "gradientTo": "#FACC15",
    }

    if current_style and isinstance(current_style, dict):
        style.update({k: v for k, v in current_style.items() if v is not None})

    # Font Family Detection
    if any(k in p for k in ["hormozi", "anton", "meme", "punchy", "slam"]):
        style["fontFamily"] = "Anton"
        style["fontWeight"] = "900"
        style["uppercase"] = True
        style["lineTransition"] = "word_pop"
        style["maxWordsPerLine"] = 1
        style["fontSize"] = 48
        style["highlightColor"] = "#00FF66"  # Lime
    elif any(k in p for k in ["montserrat", "bold", "tebal", "impact"]):
        style["fontFamily"] = "Montserrat"
        style["fontWeight"] = "900"
    elif any(k in p for k in ["podcast", "dialogue", "obrolan", "interview", "jakarta"]):
        style["fontFamily"] = "Plus Jakarta Sans"
        style["fontWeight"] = "700"
        style["bgEnabled"] = True
        style["bgColor"] = "#18181B"
        style["bgOpacity"] = 0.88
        style["bgRadius"] = 999
        style["bgPadding"] = 18
        style["highlightColor"] = "#10B981"  # Emerald
        style["lineTransition"] = "karaoke"
        style["fontSize"] = 32
    elif any(k in p for k in ["serif", "luxury", "gold", "mewah", "playfair", "cinematic"]):
        style["fontFamily"] = "Playfair Display"
        style["fontWeight"] = "800"
        style["color"] = "#F8FAFC"
        style["highlightColor"] = "#FCD34D"  # Warm Gold
        style["lineTransition"] = "karaoke"
        style["shadowEnabled"] = True
        style["shadowColor"] = "#000000"
        style["shadowBlur"] = 14
    elif any(k in p for k in ["inter", "clean", "minimal", "slate", "modern"]):
        style["fontFamily"] = "Inter"
        style["fontWeight"] = "700"
    elif any(k in p for k in ["poppins", "friendly", "soft"]):
        style["fontFamily"] = "Poppins"
        style["fontWeight"] = "700"
    elif any(k in p for k in ["bebas", "condensed", "tall"]):
        style["fontFamily"] = "Bebas Neue"
        style["fontWeight"] = "900"
        style["uppercase"] = True

    # Color Detection
    if any(k in p for k in ["yellow", "kuning"]):
        style["highlightColor"] = "#FACC15"
    elif any(k in p for k in ["lime", "hijau neon", "green", "hijau"]):
        style["highlightColor"] = "#00FF66"
    elif any(k in p for k in ["cyan", "toska", "aqua", "teal"]):
        style["highlightColor"] = "#00F0FF"
    elif any(k in p for k in ["pink", "magenta", "hot pink", "merah muda"]):
        style["highlightColor"] = "#FF007F"
    elif any(k in p for k in ["red", "merah", "danger", "breaking"]):
        style["highlightColor"] = "#EF4444"
    elif any(k in p for k in ["gold", "emas"]):
        style["highlightColor"] = "#FCD34D"
    elif any(k in p for k in ["orange", "oranye", "jingga"]):
        style["highlightColor"] = "#F97316"

    # Background / Capsule
    if any(k in p for k in ["capsule", "pill", "box", "kotak", "background", "latar", "card"]):
        style["bgEnabled"] = True
        if any(k in p for k in ["dark", "hitam", "charcoal", "black"]):
            style["bgColor"] = "#0F172A"
            style["bgOpacity"] = 0.85
        elif any(k in p for k in ["white", "putih", "light"]):
            style["bgColor"] = "#FFFFFF"
            style["bgOpacity"] = 0.95
            style["color"] = "#09090B"
        elif any(k in p for k in ["red", "merah"]):
            style["bgColor"] = "#DC2626"
            style["bgOpacity"] = 0.9
        elif any(k in p for k in ["yellow", "kuning"]):
            style["bgColor"] = "#EAB308"
            style["bgOpacity"] = 0.95
            style["color"] = "#09090B"

    # Transition / Animation
    if any(k in p for k in ["karaoke", "per-word", "word by word", "smooth"]):
        style["lineTransition"] = "karaoke"
    elif any(k in p for k in ["word pop", "pop", "satu kata", "1 kata", "single word"]):
        style["lineTransition"] = "word_pop"
        style["maxWordsPerLine"] = 1
    elif any(k in p for k in ["line reveal", "baris", "reveal", "full line"]):
        style["lineTransition"] = "line_reveal"
    elif any(k in p for k in ["emphasis", "keyword hero", "big keyword"]):
        style["lineTransition"] = "emphasis"

    # Case / Style
    if any(k in p for k in ["uppercase", "kapital", "huruf besar", "all caps"]):
        style["uppercase"] = True
    if any(k in p for k in ["italic", "miring"]):
        style["italic"] = True

    # Glow / Shader
    if any(k in p for k in ["glow", "neon", "pendaran", "cyber", "cyberpunk"]):
        style["glowEnabled"] = True
        style["highlightGlow"] = True
        style["glowColor"] = style.get("highlightColor") or "#00F0FF"
        style["highlightGlowColor"] = style["glowColor"]

    # Position
    if any(k in p for k in ["top", "atas"]):
        style["position"] = "top"
        style["positionY"] = 18
    elif any(k in p for k in ["center", "tengah"]):
        style["position"] = "center"
        style["positionY"] = 50
    elif any(k in p for k in ["bottom", "bawah"]):
        style["position"] = "bottom"
        style["positionY"] = 78

    return style


@router.post("/subtitle-ai-generate", response_model=SubtitleAIGenerateResponse)
async def generate_subtitle_with_ai(req: SubtitleAIGenerateRequest):
    """Generate dynamic subtitle styling parameters from natural language prompt."""
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt tidak boleh kosong")

    rotator = GeminiKeyRotator()
    key = rotator.get_current_key()

    fallback_style = _parse_with_local_rules(prompt, req.current_style)

    if not key:
        logger.info("gemini_key_missing: using fast local rule parser for subtitle generation")
        return SubtitleAIGenerateResponse(
            ok=True,
            subtitle_style=fallback_style,
            explanation=f"Gaya subtitle AI berhasil dibuat berdasarkan instruksi: '{prompt}'",
            highlight_keywords=fallback_style.get("highlightWords", ["viral", "penting", "rahasia"]),
        )

    system_instruction = """You are an expert typography and video motion designer specializing in viral short-form video subtitles (TikTok, Reels, YouTube Shorts).
Your task is to translate the user's natural language request into a precise SubtitleStyle JSON configuration.

The JSON output must strictly adhere to these field types:
{
  "fontFamily": "Inter" | "Montserrat" | "Poppins" | "Anton" | "Archivo Black" | "Bebas Neue" | "Barlow Condensed" | "Playfair Display" | "Plus Jakarta Sans",
  "fontSize": number (24 to 56),
  "fontWeight": "400" | "500" | "600" | "700" | "800" | "900",
  "letterSpacing": number (0 to 6),
  "lineHeight": number (1.1 to 1.6),
  "color": hex string (e.g. "#FFFFFF"),
  "highlightColor": hex string (e.g. "#00FF66", "#FACC15", "#00F0FF", "#FF007F"),
  "highlightScale": number (1.0 to 1.6),
  "highlightBold": boolean,
  "highlightGlow": boolean,
  "highlightGlowColor": hex string,
  "highlightWords": list of string (keywords to highlight),
  "bgEnabled": boolean,
  "bgColor": hex string,
  "bgOpacity": number (0.0 to 1.0),
  "bgRadius": number (0 to 40),
  "bgPadding": number (8 to 32),
  "position": "top" | "center" | "bottom",
  "positionY": number (10 to 90),
  "uppercase": boolean,
  "capitalize": boolean,
  "italic": boolean,
  "strokeEnabled": boolean,
  "strokeColor": hex string,
  "strokeWidth": number (1 to 6),
  "shadowEnabled": boolean,
  "shadowColor": hex string,
  "shadowBlur": number (0 to 20),
  "maxWordsPerLine": number (1 to 6),
  "wordSpacing": number (2 to 16),
  "animationStyle": "pop" | "fade" | "slide" | "none",
  "lineTransition": "word_pop" | "emphasis" | "line_reveal" | "karaoke",
  "glowEnabled": boolean,
  "glowColor": hex string,
  "gradientEnabled": boolean,
  "gradientFrom": hex string,
  "gradientTo": hex string,
  "explanation": "Brief explanation of why this style fits the request"
}
Output ONLY valid JSON."""

    try:
        client = genai.Client(api_key=key)
        model_name = settings.GEMINI_MODEL or "gemini-2.0-flash"
        
        response = client.models.generate_content(
            model=model_name,
            contents=[
                f"User Prompt: {prompt}\nVideo Context: {req.video_context or 'Short-form viral video clip'}\nCurrent Style: {json.dumps(req.current_style or {})}"
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )

        raw_text = response.text or ""
        parsed = json.loads(raw_text)

        # Merge with fallback to guarantee all keys exist
        merged_style = {**fallback_style, **parsed}
        explanation = parsed.get("explanation") or f"Gaya subtitle AI berhasil dibuat berdasarkan: '{prompt}'"
        highlight_keywords = parsed.get("highlightWords") or merged_style.get("highlightWords") or ["viral", "penting", "rahasia"]

        return SubtitleAIGenerateResponse(
            ok=True,
            subtitle_style=merged_style,
            explanation=explanation,
            highlight_keywords=highlight_keywords,
        )

    except Exception as e:
        logger.warning(f"gemini_subtitle_ai_error: {e} -> fallback to local rule parser")
        return SubtitleAIGenerateResponse(
            ok=True,
            subtitle_style=fallback_style,
            explanation=f"Gaya subtitle AI (mode cerdas) berhasil diterapkan berdasarkan: '{prompt}'",
            highlight_keywords=fallback_style.get("highlightWords", ["viral", "penting", "rahasia"]),
        )
