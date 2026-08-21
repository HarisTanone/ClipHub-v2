"""EdgeTTS Helper — Zero-API-key Neural Text-to-Speech Fallback via Microsoft Edge TTS.

Provides high-fidelity, studio-quality neural voices in 70+ languages (Indonesian, English, etc.)
with 100% free uptime and no quota limitations.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# Recommended Neural Voices
DEFAULT_VOICE_MAP = {
    "id": "id-ID-ArdiNeural",
    "id-female": "id-ID-GadisNeural",
    "en": "en-US-ChristopherNeural",
    "en-female": "en-US-JennyNeural",
}


class EdgeTTSHelper:
    """Zero-configuration neural text-to-speech engine."""

    def __init__(self, output_dir: Optional[str] = None):
        from src.config import settings
        self._output_dir = output_dir or os.path.join(settings.OUTPUT_DIR, "tts")
        os.makedirs(self._output_dir, exist_ok=True)

    async def synthesize(
        self,
        text: str,
        voice: str = "",
        speed: float = 1.0,
        output_path: Optional[str] = None,
    ) -> Optional[str]:
        """Synthesize text to MP3 via edge-tts."""
        if not text or not text.strip():
            return None

        import edge_tts

        # Detect or resolve voice
        chosen_voice = self._resolve_voice(voice, text)

        # Calculate rate offset (e.g. speed 1.1 -> "+10%", speed 0.9 -> "-10%")
        rate_str = "+0%"
        if abs(speed - 1.0) > 0.03:
            pct = int((speed - 1.0) * 100)
            rate_str = f"{'+' if pct >= 0 else ''}{pct}%"

        if not output_path:
            output_path = os.path.join(self._output_dir, f"edge_{uuid4().hex[:8]}.mp3")

        try:
            communicate = edge_tts.Communicate(text.strip(), voice=chosen_voice, rate=rate_str)
            await communicate.save(output_path)

            if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                logger.info(f"edge_tts: synthesized ({os.path.getsize(output_path)} bytes) -> {output_path}")
                return output_path
        except Exception as exc:
            logger.error(f"edge_tts: synthesis failed: {exc}")

        return None

    async def synthesize_scenes(
        self,
        scenes: list[dict[str, Any]],
        voice: str = "",
        speed: float = 1.0,
    ) -> list[dict[str, Any]]:
        """Synthesize TTS audio for all scenes."""
        for i, scene in enumerate(scenes):
            narration = (scene.get("narration") or "").strip()
            if not narration:
                continue

            out_file = os.path.join(self._output_dir, f"scene_edge_tts_{i + 1}_{uuid4().hex[:6]}.mp3")
            path = await self.synthesize(
                text=narration,
                voice=voice,
                speed=speed,
                output_path=out_file,
            )
            if path and os.path.exists(path):
                dur = self._probe_audio_duration(path)
                scene["tts_path"] = path
                scene["tts_duration"] = dur
                scene["audio_path"] = path
                scene["audio_duration"] = dur
                logger.info(f"edge_tts: scene {i + 1} narration ({dur:.2f}s) -> {path}")

        return scenes

    def _resolve_voice(self, voice: str, text: str) -> str:
        if voice and ("Neural" in voice or "id-" in voice or "en-" in voice):
            return voice

        import re
        # Heuristic detection for Indonesian text vs English
        sample_words = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))
        id_words = {"yang", "dan", "di", "ini", "itu", "dengan", "untuk", "adalah", "pada", "ke", "tidak", "bisa", "dalam", "sekejap", "berhenti", "bumi", "kita", "kamu", "saya", "mereka", "akan", "dari", "rahasia", "fakta", "kenapa", "mengapa", "bagaimana"}
        is_indonesian = bool(sample_words & id_words)

        if is_indonesian:
            return "id-ID-ArdiNeural"
        return "en-US-ChristopherNeural"

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
