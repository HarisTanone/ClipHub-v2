"""Deepgram TTS — Text-to-Speech via Deepgram Aura API.

Converts narration text to speech audio (MP3).
Supports multiple voice models and speed control.

Usage:
    tts = DeepgramTTS()
    path = await tts.synthesize("Hello world", voice="aura-2-thalia-en", speed=1.0)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional
from uuid import uuid4

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Available Deepgram Aura voices
DEEPGRAM_VOICES = {
    "thalia": "aura-2-thalia-en",      # Female, warm
    "asteria": "aura-2-asteria-en",    # Female, professional
    "luna": "aura-2-luna-en",          # Female, soft
    "zeus": "aura-2-zeus-en",          # Male, deep
    "orion": "aura-2-orion-en",        # Male, clear
    "arcas": "aura-2-arcas-en",        # Male, energetic
    "perseus": "aura-2-perseus-en",    # Male, narrator
    "angus": "aura-2-angus-en",        # Male, storyteller
}

DEFAULT_VOICE = "aura-2-thalia-en"


def _get_deepgram_api_key(override_key: Optional[str] = None) -> str:
    """Retrieve Deepgram API key from override, runtime system config DB, or settings."""
    if override_key and override_key.strip():
        return override_key.strip()

    try:
        from src.infrastructure.system_config_store import get_system_setting
        for k in ["DEEPGRAM_API_KEY", "deepgram_api_key"]:
            db_key = get_system_setting(k)
            if db_key and str(db_key).strip():
                return str(db_key).strip()
    except Exception:
        pass

    return (
        getattr(settings, "DEEPGRAM_API_KEY", "")
        or os.getenv("DEEPGRAM_API_KEY", "")
    ).strip()


class DeepgramTTS:
    """Text-to-Speech via Deepgram Aura API.

    Generates MP3 audio from text narration. Designed for
    the AI Video Generator pipeline — one call per scene narration.
    """

    def __init__(self, output_dir: Optional[str] = None, api_key: Optional[str] = None):
        self._api_key = _get_deepgram_api_key(api_key)
        self._base_url = "https://api.deepgram.com/v1/speak"
        self._output_dir = output_dir or os.path.join(settings.OUTPUT_DIR, "tts")
        self._timeout = getattr(settings, "DEEPGRAM_TTS_TIMEOUT", 45)

    async def synthesize(
        self,
        text: str,
        voice: str = "",
        speed: float = 1.0,
        output_path: Optional[str] = None,
    ) -> Optional[str]:
        """Synthesize text to speech audio file.

        Args:
            text: Narration text to convert.
            voice: Deepgram model name (e.g. 'aura-2-thalia-en') or short key ('thalia').
            speed: Playback speed multiplier (0.5-2.0).
            output_path: Custom output path. Auto-generated if None.

        Returns:
            Path to generated MP3 file, or None on failure.
        """
        if not self._api_key:
            logger.error("deepgram_tts: DEEPGRAM_API_KEY not configured")
            return None

        if not text or not text.strip():
            logger.warning("deepgram_tts: empty text, skipping")
            return None

        # Resolve voice model
        model = self._resolve_voice(voice)

        # Ensure output dir exists
        os.makedirs(self._output_dir, exist_ok=True)

        # Generate output path
        if not output_path:
            filename = f"tts_{uuid4().hex[:8]}.mp3"
            output_path = os.path.join(self._output_dir, filename)

        # Build request
        url = f"{self._base_url}?model={model}&speed={speed}"
        headers = {
            "Authorization": f"Token {self._api_key}",
            "Content-Type": "text/plain",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, headers=headers, content=text.encode("utf-8"))

                if response.status_code != 200:
                    logger.error(
                        f"deepgram_tts: API error {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                    return None

                # Write audio to file
                with open(output_path, "wb") as f:
                    f.write(response.content)

                size_kb = len(response.content) // 1024
                logger.info(
                    f"deepgram_tts: generated {size_kb}KB audio "
                    f"(voice={model}, speed={speed}) → {output_path}"
                )
                return output_path

        except httpx.TimeoutException:
            logger.error(f"deepgram_tts: timeout after {self._timeout}s")
        except httpx.ConnectError as exc:
            logger.error(f"deepgram_tts: connection failed: {exc}")
        except Exception as exc:
            logger.error(f"deepgram_tts: unexpected error: {exc}")

        return None

    async def synthesize_scenes(
        self,
        scenes: list[dict],
        voice: str = "",
        speed: float = 1.0,
    ) -> list[dict]:
        """Synthesize TTS for multiple scenes sequentially.

        Args:
            scenes: List of scene dicts with 'narration' field.
            voice: Voice model for all scenes.
            speed: Speed multiplier.

        Returns:
            List of scene dicts enriched with 'tts_path' and 'tts_duration'.
        """
        results = []
        for i, scene in enumerate(scenes):
            narration = scene.get("narration", "")
            if not narration:
                scene["tts_path"] = None
                scene["tts_duration"] = 0.0
                results.append(scene)
                continue

            filename = f"tts_scene_{scene.get('id', i)}_{uuid4().hex[:6]}.mp3"
            out_path = os.path.join(self._output_dir, filename)

            path = await self.synthesize(
                text=narration,
                voice=voice,
                speed=speed,
                output_path=out_path,
            )

            if path:
                duration = await self._get_audio_duration(path)
                scene["tts_path"] = path
                scene["tts_duration"] = duration
            else:
                scene["tts_path"] = None
                scene["tts_duration"] = 0.0

            results.append(scene)

            # Small delay between API calls to avoid rate limits
            if i < len(scenes) - 1:
                await asyncio.sleep(0.3)

        return results

    async def _get_audio_duration(self, path: str) -> float:
        """Get audio duration in seconds via ffprobe."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)

            if proc.returncode == 0 and stdout:
                import json
                data = json.loads(stdout.decode())
                return float(data["format"]["duration"])
        except Exception as exc:
            logger.warning(f"deepgram_tts: ffprobe duration failed: {exc}")

        return 0.0

    def _resolve_voice(self, voice: str) -> str:
        """Resolve voice shorthand to full model name."""
        if not voice:
            return settings.DEEPGRAM_TTS_VOICE or DEFAULT_VOICE

        # Check if it's a shorthand key
        if voice in DEEPGRAM_VOICES:
            return DEEPGRAM_VOICES[voice]

        # Assume it's already a full model name
        if voice.startswith("aura-"):
            return voice

        # Fallback
        return DEFAULT_VOICE

    @staticmethod
    def list_voices() -> dict[str, str]:
        """Return available voice options."""
        return DEEPGRAM_VOICES.copy()
