"""ElevenLabs TTS — Text-to-Speech via ElevenLabs API.

Supports:
- Model querying via GET https://api.elevenlabs.io/v1/models
- Voice querying via GET https://api.elevenlabs.io/v1/voices
- High-fidelity speech synthesis via POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}
- Word-level timing & duration measurement via ffprobe
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from typing import Any, Optional
from uuid import uuid4

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Fallback default models if API is unreachable
DEFAULT_ELEVENLABS_MODELS = [
    {
        "model_id": "eleven_multilingual_v2",
        "name": "Eleven Multilingual v2",
        "description": "State-of-the-art multilingual model in 29 languages with rich emotions and natural cadence.",
        "can_do_text_to_speech": True,
    },
    {
        "model_id": "eleven_flash_v2_5",
        "name": "Eleven Flash v2.5",
        "description": "Ultra low latency model in 32 languages (including Indonesian).",
        "can_do_text_to_speech": True,
    },
    {
        "model_id": "eleven_turbo_v2_5",
        "name": "Eleven Turbo v2.5",
        "description": "High quality, low latency model in 32 languages. Best for fast rendering.",
        "can_do_text_to_speech": True,
    },
    {
        "model_id": "eleven_monolingual_v1",
        "name": "Eleven English v1",
        "description": "Standard English model.",
        "can_do_text_to_speech": True,
    },
]

def _map_country_and_flag(language: str = "", accent: str = "") -> tuple[str, str]:
    """Map language/accent to standard country name and flag emoji."""
    acc = (accent or "").lower()
    lang = (language or "").lower()

    if "indonesia" in acc or "indonesia" in lang or lang == "id":
        return ("Indonesia", "🇮🇩")
    if "british" in acc or "uk" in acc or "england" in acc or lang == "en-gb":
        return ("United Kingdom", "🇬🇧")
    if "australian" in acc or "australia" in acc or lang == "en-au":
        return ("Australia", "🇦🇺")
    if "american" in acc or "us" in acc or "usa" in acc or lang == "en-us":
        return ("United States", "🇺🇸")
    if "canadian" in acc or "canada" in acc or lang == "en-ca":
        return ("Canada", "🇨🇦")
    if "indian" in acc or "india" in acc or "hi" in lang:
        return ("India", "🇮🇳")
    if "japanese" in acc or "japan" in acc or "ja" in lang:
        return ("Japan", "🇯🇵")
    if "german" in acc or "germany" in acc or "de" in lang:
        return ("Germany", "🇩🇪")
    if "french" in acc or "france" in acc or "fr" in lang:
        return ("France", "🇫🇷")
    if "spanish" in acc or "spain" in acc or "es" in lang:
        return ("Spain", "🇪🇸")
    if "italian" in acc or "italy" in acc or "it" in lang:
        return ("Italy", "🇮🇹")
    if "korean" in acc or "korea" in acc or "ko" in lang:
        return ("South Korea", "🇰🇷")
    if "chinese" in acc or "china" in acc or "zh" in lang:
        return ("China", "🇨🇳")
    if "arabic" in acc or "arab" in acc or "ar" in lang:
        return ("Middle East", "🇸🇦")
    if "portuguese" in acc or "brazil" in acc or "pt" in lang:
        return ("Brazil / Portugal", "🇧🇷")
    if "filipino" in acc or "philippines" in acc or "fil" in lang:
        return ("Philippines", "🇵🇭")
    return ("Global / Multi", "🌐")


# Fallback default voices if API is unreachable
DEFAULT_ELEVENLABS_VOICES = [
    {
        "voice_id": "rUOpAdbAl56KxO00wR5D",
        "name": "Indonesian / Studio Narrator",
        "category": "custom",
        "gender": "male",
        "accent": "indonesian",
        "language": "id",
        "country": "Indonesia",
        "flag": "🇮🇩",
        "preview_url": "https://storage.googleapis.com/eleven-public-prod/premade/voices/pNInz6obpgDQGcFmaJgB/d6905d7a-dd26-4187-bfff-1bd3a5ea7cac.mp3",
    },
    {
        "voice_id": "21m00Tcm4TlvDq8ikWAM",
        "name": "Rachel - Calm, Professional",
        "category": "premade",
        "gender": "female",
        "accent": "american",
        "language": "en",
        "country": "United States",
        "flag": "🇺🇸",
        "preview_url": "https://storage.googleapis.com/eleven-public-prod/premade/voices/21m00Tcm4TlvDq8ikWAM/b11eb610-c128-4420-ba31-744037eb89e1.mp3",
    },
    {
        "voice_id": "AZnzlk1XvdvUeBnXmlld",
        "name": "Domi - Strong, Engaging",
        "category": "premade",
        "gender": "female",
        "accent": "american",
        "language": "en",
        "country": "United States",
        "flag": "🇺🇸",
        "preview_url": "https://storage.googleapis.com/eleven-public-prod/premade/voices/AZnzlk1XvdvUeBnXmlld/507e1507-7590-482d-8472-7360c704f057.mp3",
    },
    {
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "name": "Bella - Expressive, Warm",
        "category": "premade",
        "gender": "female",
        "accent": "american",
        "language": "en",
        "country": "United States",
        "flag": "🇺🇸",
        "preview_url": "https://storage.googleapis.com/eleven-public-prod/premade/voices/EXAVITQu4vr4xnSDxMaL/01d5ee4e-7255-46c5-ab1a-619ab5478440.mp3",
    },
    {
        "voice_id": "ErXwobaYiN019PkySvjV",
        "name": "Antoni - Confident, Storyteller",
        "category": "premade",
        "gender": "male",
        "accent": "american",
        "language": "en",
        "country": "United States",
        "flag": "🇺🇸",
        "preview_url": "https://storage.googleapis.com/eleven-public-prod/premade/voices/ErXwobaYiN019PkySvjV/38d8f8f0-0412-42c2-b52b-4e08bf60cb7d.mp3",
    },
    {
        "voice_id": "MF3mGyEYCl7XYWbV9V6O",
        "name": "Elli - Clear, Youthful",
        "category": "premade",
        "gender": "female",
        "accent": "american",
        "language": "en",
        "country": "United States",
        "flag": "🇺🇸",
        "preview_url": "https://storage.googleapis.com/eleven-public-prod/premade/voices/MF3mGyEYCl7XYWbV9V6O/d86c7104-e53b-4c55-83e9-38b4df568019.mp3",
    },
    {
        "voice_id": "TxGEqnHWrfWFTfGW9XjX",
        "name": "Josh - Deep, Engaging",
        "category": "premade",
        "gender": "male",
        "accent": "american",
        "language": "en",
        "country": "United States",
        "flag": "🇺🇸",
        "preview_url": "https://storage.googleapis.com/eleven-public-prod/premade/voices/TxGEqnHWrfWFTfGW9XjX/a0e5b746-13cb-4f81-a9c4-a5e2f75d5069.mp3",
    },
    {
        "voice_id": "pNInz6obpgDQGcFmaJgB",
        "name": "Adam - Dominant, Firm",
        "category": "premade",
        "gender": "male",
        "accent": "american",
        "language": "en",
        "country": "United States",
        "flag": "🇺🇸",
        "preview_url": "https://storage.googleapis.com/eleven-public-prod/premade/voices/pNInz6obpgDQGcFmaJgB/d6905d7a-dd26-4187-bfff-1bd3a5ea7cac.mp3",
    },
    {
        "voice_id": "yoZ06aMxZJJ28mfd3POQ",
        "name": "Sam - Casual, Natural",
        "category": "premade",
        "gender": "male",
        "accent": "american",
        "language": "en",
        "country": "United States",
        "flag": "🇺🇸",
        "preview_url": "https://storage.googleapis.com/eleven-public-prod/premade/voices/yoZ06aMxZJJ28mfd3POQ/c69e20a7-bc63-4ce2-a08b-626a427f71aa.mp3",
    },
]

# In-memory cache for models and voices
_CACHE: dict[str, tuple[float, Any]] = {}
CACHE_TTL = 3600  # 1 hour


def _get_configured_api_key(override_key: Optional[str] = None) -> str:
    """Retrieve ElevenLabs API key from override, runtime system config DB, or settings."""
    if override_key and override_key.strip():
        return override_key.strip()

    try:
        from src.infrastructure.system_config_store import get_system_setting
        db_key = get_system_setting("ELEVENLABS_API_KEY") or get_system_setting("ELEVEN_API_KEY")
        if db_key and str(db_key).strip():
            return str(db_key).strip()
    except Exception:
        pass

    return (
        getattr(settings, "ELEVENLABS_API_KEY", "")
        or getattr(settings, "ELEVEN_API_KEY", "")
        or os.getenv("ELEVENLABS_API_KEY", "")
        or os.getenv("ELEVEN_API_KEY", "")
    ).strip()


class ElevenLabsTTS:
    """Text-to-Speech via ElevenLabs API."""

    def __init__(self, output_dir: Optional[str] = None, api_key: Optional[str] = None):
        self._api_key = _get_configured_api_key(api_key)
        self._base_url = "https://api.elevenlabs.io/v1"
        self._output_dir = output_dir or os.path.join(settings.OUTPUT_DIR, "tts")
        self._timeout = getattr(settings, "ELEVENLABS_TTS_TIMEOUT", 45)

    @classmethod
    async def fetch_models(cls, api_key: Optional[str] = None) -> list[dict[str, Any]]:
        """Fetch available text-to-speech models from ElevenLabs API."""
        key = _get_configured_api_key(api_key)
        cache_key = f"models_{key[:8] if key else 'none'}"

        now = time.time()
        if cache_key in _CACHE:
            cached_time, cached_data = _CACHE[cache_key]
            if now - cached_time < CACHE_TTL:
                return cached_data

        if not key:
            return DEFAULT_ELEVENLABS_MODELS

        url = "https://api.elevenlabs.io/v1/models"
        headers = {"xi-api-key": key}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    raw_models = resp.json()
                    if isinstance(raw_models, list):
                        # Filter to models that support text-to-speech
                        tts_models = [
                            {
                                "model_id": m.get("model_id"),
                                "name": m.get("name") or m.get("model_id"),
                                "description": m.get("description", ""),
                                "can_do_text_to_speech": m.get("can_do_text_to_speech", True),
                                "languages": [l.get("name") for l in m.get("languages", []) if isinstance(l, dict) and l.get("name")],
                            }
                            for m in raw_models
                            if m.get("can_do_text_to_speech", True)
                        ]
                        if tts_models:
                            _CACHE[cache_key] = (now, tts_models)
                            return tts_models
                else:
                    logger.warning(f"elevenlabs: fetch_models returned HTTP {resp.status_code}")
        except Exception as exc:
            logger.warning(f"elevenlabs: fetch_models failed: {exc}")

        return DEFAULT_ELEVENLABS_MODELS

    @classmethod
    async def fetch_voices(cls, api_key: Optional[str] = None) -> list[dict[str, Any]]:
        """Fetch available voices from ElevenLabs API."""
        key = _get_configured_api_key(api_key)
        cache_key = f"voices_{key[:8] if key else 'none'}"

        now = time.time()
        if cache_key in _CACHE:
            cached_time, cached_data = _CACHE[cache_key]
            if now - cached_time < CACHE_TTL:
                return cached_data

        if not key:
            return DEFAULT_ELEVENLABS_VOICES

        url = "https://api.elevenlabs.io/v1/voices"
        headers = {"xi-api-key": key}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    voices_raw = data.get("voices", []) if isinstance(data, dict) else data
                    parsed_voices = []
                    for v in voices_raw:
                        labels = v.get("labels") or {}
                        desc = v.get("description") or ""
                        preview_url = v.get("preview_url") or ""
                        gender = labels.get("gender") or ""
                        accent = labels.get("accent") or ""
                        lang = labels.get("language") or ""
                        country, flag = _map_country_and_flag(language=lang, accent=accent)

                        parsed_voices.append({
                            "voice_id": v.get("voice_id"),
                            "name": v.get("name"),
                            "category": v.get("category", "premade"),
                            "description": desc,
                            "gender": gender,
                            "accent": accent,
                            "language": lang,
                            "country": country,
                            "flag": flag,
                            "preview_url": preview_url,
                        })
                    if parsed_voices:
                        _CACHE[cache_key] = (now, parsed_voices)
                        return parsed_voices
                else:
                    logger.warning(f"elevenlabs: fetch_voices returned HTTP {resp.status_code}")
        except Exception as exc:
            logger.warning(f"elevenlabs: fetch_voices failed: {exc}")

        return DEFAULT_ELEVENLABS_VOICES

    async def synthesize(
        self,
        text: str,
        voice_id: str = "",
        model_id: str = "eleven_multilingual_v2",
        speed: float = 1.0,
        output_path: Optional[str] = None,
    ) -> Optional[str]:
        """Synthesize text to speech audio file via ElevenLabs.

        Args:
            text: Narration script text.
            voice_id: ElevenLabs voice ID (e.g. 'rUOpAdbAl56KxO00wR5D' or '21m00Tcm4TlvDq8ikWAM').
            model_id: ElevenLabs model ID (e.g. 'eleven_multilingual_v2' or 'eleven_flash_v2_5').
            speed: Playback speed multiplier (0.7-1.5).
            output_path: Custom output MP3 path.

        Returns:
            Path to generated MP3 file, or None on failure.
        """
        api_key = self._api_key or _get_configured_api_key()
        if not api_key:
            logger.error("elevenlabs_tts: ELEVENLABS_API_KEY not configured")
            return None

        if not text or not text.strip():
            logger.warning("elevenlabs_tts: empty text, skipping")
            return None

        # Resolve voice_id default
        chosen_voice_id = voice_id.strip() if voice_id and voice_id.strip() else getattr(settings, "ELEVENLABS_VOICE_ID", "rUOpAdbAl56KxO00wR5D")
        chosen_model_id = model_id.strip() if model_id and model_id.strip() else getattr(settings, "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

        os.makedirs(self._output_dir, exist_ok=True)
        if not output_path:
            output_path = os.path.join(self._output_dir, f"eleven_{uuid4().hex[:8]}.mp3")

        url = f"{self._base_url}/text-to-speech/{chosen_voice_id}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text.strip(),
            "model_id": chosen_model_id,
            "voice_settings": {
                "stability": 0.50,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
                "speed": max(0.7, min(1.5, float(speed))),
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                logger.info(f"elevenlabs_tts: synthesizing {len(text)} chars with voice={chosen_voice_id} model={chosen_model_id}")
                resp = await client.post(url, headers=headers, json=payload)

                if resp.status_code == 200:
                    with open(output_path, "wb") as f:
                        f.write(resp.content)
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                        logger.info(f"elevenlabs_tts: generated audio -> {output_path} ({os.path.getsize(output_path)} bytes)")
                        return output_path
                else:
                    err_body = resp.text[:300]
                    logger.error(f"elevenlabs_tts: request failed HTTP {resp.status_code}: {err_body}")
                    return None
        except Exception as exc:
            logger.error(f"elevenlabs_tts: synthesis error: {exc}")
            return None

        return None

    async def synthesize_scenes(
        self,
        scenes: list[dict[str, Any]],
        voice_id: str = "",
        model_id: str = "eleven_multilingual_v2",
        speed: float = 1.0,
    ) -> list[dict[str, Any]]:
        """Synthesize TTS audio for all scenes sequentially/concurrently and measure duration."""
        for i, scene in enumerate(scenes):
            narration = (scene.get("narration") or "").strip()
            if not narration:
                continue
            out_file = os.path.join(self._output_dir, f"scene_tts_{i + 1}_{uuid4().hex[:6]}.mp3")
            path = await self.synthesize(
                text=narration,
                voice_id=voice_id,
                model_id=model_id,
                speed=speed,
                output_path=out_file,
            )
            if path and os.path.exists(path):
                dur = self._probe_audio_duration(path)
                scene["tts_path"] = path
                scene["tts_duration"] = dur
                scene["audio_path"] = path
                scene["audio_duration"] = dur
                logger.info(f"elevenlabs_tts: scene {i + 1} narration ({dur:.2f}s) -> {path}")
            else:
                logger.warning(f"elevenlabs_tts: scene {i + 1} TTS returned empty")

        return scenes

    @staticmethod
    def _probe_audio_duration(audio_path: str) -> float:
        """Measure audio duration via ffprobe in seconds."""
        if not audio_path or not os.path.exists(audio_path):
            return 0.0
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                return max(0.5, float(res.stdout.strip()))
        except Exception:
            pass
        return 5.0
