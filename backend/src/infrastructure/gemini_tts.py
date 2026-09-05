"""Gemini TTS — Text-to-Speech via Google Gemini API.

Supports:
- Gemini 3.1 Flash TTS (gemini-3.1-flash-tts-preview) [Free Tier]
- Gemini 2.5 Flash TTS (gemini-2.5-flash-preview-tts) [Free Tier]
- Gemini 2.5 Pro TTS (gemini-2.5-pro-preview-tts) [Studio Pro]
- Prebuilt Gemini Voices: Kore, Puck, Fenrir, Aoede, Charon, Leda, Zephyr, Orus, etc.
- Indonesian Regional Styles: Jakarta/Gaul, Formal/Berita, Storytelling, Jawa/Medok, Sunda, Batak, Timur
- Native English Accents & Styles: US Native, UK Native, Australian, Documentary Storyteller
- Direct REST API calling with raw PCM 24kHz decode to MP3/WAV.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import subprocess
import wave
from typing import Any, Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Available Gemini TTS Models
GEMINI_TTS_MODELS = [
    {
        "model_id": "gemini-3.1-flash-tts-preview",
        "name": "Gemini 3.1 Flash TTS",
        "description": "Model terbaru, sangat ekspresif, respons cepat & intonasi natural (Free Tier)",
        "free_tier": True,
        "languages": ["id", "en", "multi"],
    },
    {
        "model_id": "gemini-2.5-flash-preview-tts",
        "name": "Gemini 2.5 Flash TTS",
        "description": "Cepat, efisien, optimal untuk batch & volume tinggi (Free Tier)",
        "free_tier": True,
        "languages": ["id", "en", "multi"],
    },
    {
        "model_id": "gemini-2.5-pro-preview-tts",
        "name": "Gemini 2.5 Pro TTS",
        "description": "Kualitas studio audio tinggi, podcast & narasi mendalam",
        "free_tier": False,
        "languages": ["id", "en", "multi"],
    },
]

# Regional & Expressive Speaking Styles
GEMINI_VOICE_STYLES = [
    # Indonesian Styles
    {
        "id": "id_jakarta",
        "name": "Jakarta / Gaul Santai",
        "language": "id",
        "country": "Indonesia",
        "flag": "ID",
        "description": "Gaya bahasa santai, luwes, ekspresif, dan kekinian (cocok untuk Reels/TikTok)",
        "prompt_prefix": "Gunakan gaya bicara bahasa Indonesia gaul yang santai, luwes, ekspresif, tidak kaku, seperti kreator muda Indonesia berbicara pada audiensnya.",
    },
    {
        "id": "id_formal",
        "name": "Formal / Berita & Edukasi",
        "language": "id",
        "country": "Indonesia",
        "flag": "ID",
        "description": "Artikulasi jelas, berwibawa, standar EYD (cocok untuk dokumenter & berita)",
        "prompt_prefix": "Gunakan gaya bicara bahasa Indonesia formal yang jelas, artikulatif, berwibawa, dan elegan layaknya presenter berita atau narator dokumenter profesional.",
    },
    {
        "id": "id_storytelling",
        "name": "Storytelling / Naratif Emosional",
        "language": "id",
        "country": "Indonesia",
        "flag": "ID",
        "description": "Intonasi mendalam, pacing dramatis, menggugah emosi dan rasa penasaran",
        "prompt_prefix": "Gunakan gaya bicara bercerita (storytelling) dengan intonasi mendalam, penuh penjiwaan, variasi nada emosional, dan pacing yang memikat rasa penasaran pendengar.",
    },
    {
        "id": "id_jawa",
        "name": "Jawa / Medok Santun",
        "language": "id",
        "country": "Indonesia",
        "flag": "ID",
        "description": "Sentuhan aksen Jawa yang medok, hangat, ramah, dan bersahabat",
        "prompt_prefix": "Gunakan gaya bicara bahasa Indonesia dengan nuansa intonasi aksen Jawa yang medok santun, ramah, hangat, dan luwes.",
    },
    {
        "id": "id_sunda",
        "name": "Sunda / Riang & Lembut",
        "language": "id",
        "country": "Indonesia",
        "flag": "ID",
        "description": "Intonasi khas Parahyangan yang lembut, ramah, dan berirama manis",
        "prompt_prefix": "Gunakan gaya bicara bahasa Indonesia dengan cengkok dan intonasi khas Sunda yang lembut, riang, ramah, dan bersahabat.",
    },
    {
        "id": "id_batak",
        "name": "Batak / Medan (Tegas & Bertenaga)",
        "language": "id",
        "country": "Indonesia",
        "flag": "ID",
        "description": "Artikulasi tegas, lugas, energik, dan penuh percaya diri",
        "prompt_prefix": "Gunakan gaya bicara bahasa Indonesia dengan intonasi aksen Medan / Batak yang tegas, lugas, berenergi tinggi, dan meyakinkan.",
    },
    {
        "id": "id_timur",
        "name": "Indonesia Timur / Manado - Makassar",
        "language": "id",
        "country": "Indonesia",
        "flag": "ID",
        "description": "Irama ceria, bersemangat, dinamis, dan khas Indonesia Timur",
        "prompt_prefix": "Gunakan gaya bicara bahasa Indonesia dengan dialek dan intonasi khas Indonesia Timur yang dinamis, ceria, dan penuh semangat hidup.",
    },
    # English Styles
    {
        "id": "en_us_story",
        "name": "US Native · Storyteller",
        "language": "en",
        "country": "United States",
        "flag": "US",
        "description": "Engaging American storyteller with natural cadence and tone variation",
        "prompt_prefix": "Speak in natural American English with an engaging storytelling cadence, clear enunciation, and dynamic emotional rhythm.",
    },
    {
        "id": "en_us_energetic",
        "name": "US Native · Viral & Energetic",
        "language": "en",
        "country": "United States",
        "flag": "US",
        "description": "Fast-paced, hook-driven, high energy commercial delivery",
        "prompt_prefix": "Speak in upbeat, highly energetic, and confident American English tailored for viral short-form videos.",
    },
    {
        "id": "en_uk_documentary",
        "name": "UK Native · British Documentary",
        "language": "en",
        "country": "United Kingdom",
        "flag": "GB",
        "description": "Sophisticated British RP accent for educational and cinematic videos",
        "prompt_prefix": "Speak in a sophisticated, clear British RP accent suitable for prestigious documentary narration.",
    },
    {
        "id": "en_aus_casual",
        "name": "Australian · Friendly & Casual",
        "language": "en",
        "country": "Australia",
        "flag": "AU",
        "description": "Warm, laid-back Australian conversational accent",
        "prompt_prefix": "Speak in a natural, friendly Australian accent with warm and relaxed conversational delivery.",
    },
]

# Prebuilt Gemini Voices
GEMINI_PREBUILT_VOICES = [
    {
        "voice_id": "Kore",
        "name": "Kore (Female · Warm & Expressive)",
        "gender": "female",
        "tone": "Warm, soothing, clear, highly expressive",
        "recommended_for": "General narration, storytelling, explainer",
        "flag": "AI",
    },
    {
        "voice_id": "Puck",
        "name": "Puck (Male · Upbeat & Dynamic)",
        "gender": "male",
        "tone": "Energetic, dynamic, friendly, engaging",
        "recommended_for": "Viral shorts, tech reviews, energetic stories",
        "flag": "AI",
    },
    {
        "voice_id": "Fenrir",
        "name": "Fenrir (Male · Deep & Authoritative)",
        "gender": "male",
        "tone": "Deep, powerful, resonant, authoritative",
        "recommended_for": "Documentaries, cinematic trailers, history",
        "flag": "AI",
    },
    {
        "voice_id": "Aoede",
        "name": "Aoede (Female · Melodic & Elegant)",
        "gender": "female",
        "tone": "Melodic, gentle, articulate, refined",
        "recommended_for": "Luxury, education, calm storytelling, poetry",
        "flag": "AI",
    },
    {
        "voice_id": "Charon",
        "name": "Charon (Male · Serious & Mysterious)",
        "gender": "male",
        "tone": "Rich, grave, captivating, mysterious",
        "recommended_for": "Crime, suspense, deep philosophy, horror",
        "flag": "AI",
    },
    {
        "voice_id": "Leda",
        "name": "Leda (Female · Youthful & Casual)",
        "gender": "female",
        "tone": "Youthful, bright, conversational, modern",
        "recommended_for": "Lifestyle, humor, everyday tips, vlogs",
        "flag": "AI",
    },
    {
        "voice_id": "Zephyr",
        "name": "Zephyr (Male · Crisp & Tech)",
        "gender": "male",
        "tone": "Crisp, modern, precise, professional",
        "recommended_for": "Product demos, science, business explainers",
        "flag": "AI",
    },
    {
        "voice_id": "Orus",
        "name": "Orus (Male · Storybook & Rich)",
        "gender": "male",
        "tone": "Warm baritone, narrative, welcoming",
        "recommended_for": "Audiobooks, long-form stories, motivation",
        "flag": "AI",
    },
]


def _get_gemini_api_keys() -> list[str]:
    """Retrieve all available Gemini API keys from settings/env/database."""
    from src.infrastructure.system_config_store import get_system_setting

    keys: list[str] = []
    # Check system config DB
    db_key = get_system_setting("GEMINI_API_KEY")
    if db_key and str(db_key).strip():
        for k in str(db_key).split(","):
            if k.strip():
                keys.append(k.strip())

    # Check settings / env
    if settings.gemini_api_keys:
        for k in settings.gemini_api_keys:
            if k and k not in keys:
                keys.append(k)

    env_key = os.getenv("GEMINI_API_KEY", "")
    if env_key:
        for k in env_key.split(","):
            if k.strip() and k.strip() not in keys:
                keys.append(k.strip())

    return keys


class GeminiTTS:
    """Text-to-Speech via Google Gemini Audio Generative API."""

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.join(
            getattr(settings, "VIDEO_GEN_OUTPUT_DIR", "tmp/video_generator"), "tts"
        )
        os.makedirs(self.output_dir, exist_ok=True)
        self._key_index = 0

    def _get_api_key(self) -> str:
        from src.infrastructure.auth import get_gemini_key_rotator
        rotator = get_gemini_key_rotator()
        key = rotator.get_current_key()
        if not key:
            keys = _get_gemini_api_keys()
            if not keys:
                raise RuntimeError(
                    "Gemini API Key tidak ditemukan. Pastikan GEMINI_API_KEY sudah dikonfigurasi di Settings atau .env."
                )
            key = keys[self._key_index % len(keys)]
            self._key_index += 1
        return key

    @classmethod
    async def fetch_models(cls) -> list[dict[str, Any]]:
        """Return supported Gemini TTS models."""
        return GEMINI_TTS_MODELS

    @classmethod
    async def fetch_voices(
        cls,
        language: Optional[str] = None,
        style: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return combined voice options with style & accent metadata."""
        voices_list: list[dict[str, Any]] = []

        # Generate combinations of prebuilt voices and regional styles
        for v in GEMINI_PREBUILT_VOICES:
            for s in GEMINI_VOICE_STYLES:
                if language and language.lower() not in ["all", ""]:
                    if s["language"].lower() != language.lower():
                        continue

                key_id = f"{v['voice_id']}__{s['id']}"
                voices_list.append(
                    {
                        "key": f"{s['flag']} {v['voice_id']} · {s['name']}",
                        "voice_id": v["voice_id"],
                        "style_id": s["id"],
                        "model": key_id,
                        "provider": "gemini",
                        "description": f"{v['tone']} — {s['description']}",
                        "gender": v["gender"],
                        "accent": s["name"],
                        "language": s["language"],
                        "country": s["country"],
                        "flag": s["flag"],
                        "preview_url": None,
                    }
                )

        return voices_list

    async def synthesize(
        self,
        text: str,
        voice_id: str = "Kore",
        model_id: str = "gemini-3.1-flash-tts-preview",
        speed: float = 1.0,
        voice_style: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> Optional[str]:
        """Synthesize text to speech audio file using Gemini TTS API.

        Args:
            text: Text narration to speak.
            voice_id: Gemini prebuilt voice name (Kore, Puck, Fenrir, Aoede, etc.)
                      or combined key (e.g. 'Kore__id_jakarta').
            model_id: Gemini model ID ('gemini-3.1-flash-tts-preview', etc.)
            speed: Playback speed multiplier (0.85 - 1.3).
            voice_style: Optional style/accent identifier (e.g. 'id_jakarta', 'id_formal').
            output_path: Destination path for output MP3/WAV file.
        """
        if not text or not text.strip():
            logger.warning("gemini_tts: Empty text, skipping synthesis")
            return None

        # Parse combined voice key if passed (e.g., 'Kore__id_jakarta')
        actual_voice = voice_id.strip() if voice_id else "Kore"
        actual_style = voice_style

        if "__" in actual_voice:
            parts = actual_voice.split("__", 1)
            actual_voice = parts[0]
            if not actual_style:
                actual_style = parts[1]

        # Resolve style prompt instructions
        style_prompt = ""
        if actual_style:
            for s in GEMINI_VOICE_STYLES:
                if s["id"] == actual_style:
                    style_prompt = s["prompt_prefix"]
                    break

        clean_model = (model_id or "gemini-3.1-flash-tts-preview").strip()
        if not clean_model:
            clean_model = "gemini-3.1-flash-tts-preview"

        # Determine target output file path
        if not output_path:
            out_name = f"gemini_tts_{abs(hash(text)) % 10000000:07d}.mp3"
            output_path = os.path.join(self.output_dir, out_name)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # Build prompt: instruction + text
        full_prompt = text.strip()
        if style_prompt:
            full_prompt = f"[{style_prompt}] {full_prompt}"

        # API Request Body
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": full_prompt,
                        }
                    ],
                }
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": actual_voice,
                        }
                    }
                },
            },
        }

        # Multi-attempt with key rotation
        keys = _get_gemini_api_keys()
        max_attempts = max(1, min(len(keys) if keys else 1, 3))
        last_error = None

        for attempt in range(max_attempts):
            api_key = self._get_api_key()
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"

            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    resp = await client.post(
                        url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )

                if resp.status_code == 200:
                    data = resp.json()
                    audio_b64 = None
                    mime_type = "audio/pcm;rate=24000"

                    candidates = data.get("candidates", [])
                    if candidates and len(candidates) > 0:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for p in parts:
                            inline = p.get("inlineData") or p.get("inline_data")
                            if inline and (inline.get("data") or inline.get("bytes")):
                                audio_b64 = inline.get("data") or inline.get("bytes")
                                mime_type = inline.get("mimeType") or inline.get("mime_type") or mime_type
                                break

                    if not audio_b64:
                        logger.warning(
                            f"gemini_tts: No audio parts in response (model={clean_model}): {data}"
                        )
                        # Try fallback model if 3.1 preview had format issue
                        if clean_model != "gemini-2.5-flash-preview-tts":
                            clean_model = "gemini-2.5-flash-preview-tts"
                            continue
                        return None

                    audio_bytes = base64.b64decode(audio_b64)

                    # Save and convert audio bytes
                    await asyncio.to_thread(
                        self._save_and_convert_audio,
                        audio_bytes=audio_bytes,
                        mime_type=mime_type,
                        output_path=output_path,
                        speed=speed,
                    )

                    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                        logger.info(
                            f"gemini_tts: successfully generated audio -> {output_path} "
                            f"({os.path.getsize(output_path)} bytes, voice={actual_voice}, model={clean_model})"
                        )
                        return output_path

                elif resp.status_code in [400, 404]:
                    err_msg = resp.text
                    logger.warning(
                        f"gemini_tts: model {clean_model} returned {resp.status_code}: {err_msg[:200]}"
                    )
                    # If preview model name changed or not found, fallback to 2.5-flash
                    if clean_model != "gemini-2.5-flash-preview-tts":
                        clean_model = "gemini-2.5-flash-preview-tts"
                        continue
                    last_error = f"HTTP {resp.status_code}: {err_msg[:100]}"
                elif resp.status_code == 429:
                    from src.infrastructure.auth import get_gemini_key_rotator
                    get_gemini_key_rotator().mark_rate_limited(key=api_key, retry_after=60.0)
                    logger.warning(f"gemini_tts: attempt {attempt + 1} HTTP 429 rate limited on key ...{api_key[-6:]}")
                    last_error = "HTTP 429 Too Many Requests"
                    continue
                else:
                    logger.warning(
                        f"gemini_tts: attempt {attempt + 1} HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                    last_error = f"HTTP {resp.status_code}"

            except Exception as exc:
                logger.warning(f"gemini_tts: attempt {attempt + 1} failed: {exc}")
                last_error = str(exc)

        logger.error(f"gemini_tts: all synthesis attempts failed: {last_error}")
        return None

    def _save_and_convert_audio(
        self,
        audio_bytes: bytes,
        mime_type: str,
        output_path: str,
        speed: float = 1.0,
    ) -> None:
        """Convert raw PCM or WAV audio bytes to target format with optional tempo adjustment."""
        temp_wav = output_path + ".temp.wav"

        # Check if already a valid WAV container (starts with RIFF)
        if audio_bytes.startswith(b"RIFF"):
            with open(temp_wav, "wb") as f:
                f.write(audio_bytes)
        else:
            # Parse sample rate from mimeType if available (e.g. 'audio/pcm;rate=24000')
            sample_rate = 24000
            if "rate=" in mime_type:
                try:
                    sample_rate = int(mime_type.split("rate=")[1].split(";")[0].strip())
                except Exception:
                    sample_rate = 24000

            # Write raw PCM 16-bit mono to valid WAV
            with wave.open(temp_wav, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_bytes)

        # Convert to final MP3 with FFmpeg and apply speed / audio filters
        speed_filter = []
        if abs(speed - 1.0) > 0.03:
            # atempo supports values between 0.5 and 2.0
            safe_speed = max(0.5, min(2.0, speed))
            speed_filter = ["-filter:a", f"atempo={safe_speed:.3f}"]

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            temp_wav,
            *speed_filter,
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            output_path,
        ]

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=True,
            )
        except Exception as e:
            logger.warning(f"gemini_tts: ffmpeg conversion failed ({e}), keeping raw wav")
            if os.path.exists(temp_wav):
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(temp_wav, output_path)
            return
        finally:
            if os.path.exists(temp_wav):
                try:
                    os.remove(temp_wav)
                except Exception:
                    pass

    async def synthesize_scenes(
        self,
        scenes: list[dict[str, Any]],
        voice_id: str = "Kore",
        model_id: str = "gemini-3.1-flash-tts-preview",
        speed: float = 1.0,
        voice_style: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Synthesize narration for all scenes in parallel with concurrency limit."""
        sem = asyncio.Semaphore(4)

        async def _synth_scene(i: int, scene: dict[str, Any]):
            narration = (scene.get("narration") or "").strip()
            if not narration:
                return scene

            out_path = os.path.join(self.output_dir, f"scene_{i + 1:02d}_tts.mp3")

            async with sem:
                audio_path = await self.synthesize(
                    text=narration,
                    voice_id=voice_id,
                    model_id=model_id,
                    speed=speed,
                    voice_style=voice_style,
                    output_path=out_path,
                )

            if audio_path and os.path.exists(audio_path):
                # Probe duration via ffprobe
                dur = await self._probe_audio_duration(audio_path)
                scene["tts_path"] = audio_path
                scene["tts_duration"] = dur
                scene["audio_path"] = audio_path
                scene["audio_duration"] = dur
            return scene

        tasks = [_synth_scene(i, s) for i, s in enumerate(scenes)]
        return await asyncio.gather(*tasks)

    async def _probe_audio_duration(self, file_path: str, fallback: float = 5.0) -> float:
        """Probe audio duration in seconds via ffprobe."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                return float(stdout.decode().strip())
        except Exception:
            pass
        return fallback
