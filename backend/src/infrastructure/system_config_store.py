"""Dynamic Database-backed System Settings Store with Role-Based Access Control (RBAC).

Provides:
- In-memory cached lookup with zero-overhead performance.
- Automatic fallback: DB -> .env -> Pydantic Settings default.
- Role-based filtering: 'superadmin', 'editor', 'viewer'.
- Secret masking for sensitive credentials.
- Type coercion (bool, int, float, str, json).
"""
import json
import logging
import sqlite3
from typing import Any, Optional, Union

from src.infrastructure.db_connection import get_dict_connection

logger = logging.getLogger(__name__)

# Setting Metadata definition
# (category, data_type, min_role, is_secret, default_value, description)
SYSTEM_SETTINGS_METADATA: dict[str, dict[str, Any]] = {
    # ─── Group 1: AI & LLM Routing ──────────────────────────────────────────
    "LLM_PROVIDER": {
        "category": "ai_llm",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "nine_router",
        "description": "Provider utama LLM (nine_router, groq, gemini, ollama)",
    },
    "FORCE_V2_PIPELINE": {
        "category": "ai_llm",
        "data_type": "bool",
        "min_role": "superadmin",
        "is_secret": False,
        "default": True,
        "description": "Paksa semua job menggunakan pipeline V2 multi-stage",
    },
    "ALLOW_DIRECT_PROVIDER_FALLBACKS": {
        "category": "ai_llm",
        "data_type": "bool",
        "min_role": "superadmin",
        "is_secret": False,
        "default": True,
        "description": "Izinkan fallback langsung ke Gemini/Groq jika 9router gagal",
    },
    "TRANSCRIPTION_PROVIDER": {
        "category": "ai_llm",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "local",
        "description": "Provider transkripsi audio (local, nine_router, groq)",
    },
    "NINE_ROUTER_BASE_URL": {
        "category": "ai_llm",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "http://127.0.0.1:20128/v1",
        "description": "Base URL server 9router (OpenAI-compatible endpoint)",
    },
    "NINE_ROUTER_API_KEY": {
        "category": "ai_llm",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "API Key untuk 9router gateway",
    },
    "NINE_ROUTER_MODEL": {
        "category": "ai_llm",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "CliperHub",
        "description": "Model LLM default untuk analisis viral",
    },
    "NINE_ROUTER_PASS1_MODEL": {
        "category": "ai_llm",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "CliperHub",
        "description": "Model LLM untuk Pass 1 (Candidate Selection)",
    },
    "NINE_ROUTER_PASS2_MODEL": {
        "category": "ai_llm",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "CliperHub",
        "description": "Model LLM untuk Pass 2 (Refinement & Scoring)",
    },
    "NINE_ROUTER_AI_LAYER_MODEL": {
        "category": "ai_llm",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "CliperHub",
        "description": "Model LLM untuk AI Polish Layer",
    },
    "NINE_ROUTER_TIMEOUT": {
        "category": "ai_llm",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 120,
        "description": "Timeout request 9router (detik)",
    },
    "NINE_ROUTER_MAX_RETRIES": {
        "category": "ai_llm",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 3,
        "description": "Jumlah maksimal percobaan ulang 9router jika gagal",
    },
    "NINE_ROUTER_TEMPERATURE": {
        "category": "ai_llm",
        "data_type": "float",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 0.3,
        "description": "Kreativitas model LLM 9router (0.0 - 1.0)",
    },
    "NINE_ROUTER_WHISPER_ENABLED": {
        "category": "ai_llm",
        "data_type": "bool",
        "min_role": "superadmin",
        "is_secret": False,
        "default": True,
        "description": "Gunakan remote Whisper via 9router sebelum fallback lokal",
    },
    "NINE_ROUTER_WHISPER_MODEL": {
        "category": "ai_llm",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "groq/whisper-large-v3-turbo",
        "description": "Nama model remote Whisper pada 9router",
    },
    "NINE_ROUTER_WHISPER_TIMEOUT": {
        "category": "ai_llm",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 120,
        "description": "Timeout remote Whisper 9router (detik)",
    },
    "OLLAMA_BASE_URL": {
        "category": "ai_llm",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "http://localhost:11434",
        "description": "Base URL server lokal Ollama",
    },
    "OLLAMA_MODEL": {
        "category": "ai_llm",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "mistral-nemo:12b",
        "description": "Nama model lokal Ollama",
    },

    # ─── Group 2: API Keys & External Providers ──────────────────────────────
    "GEMINI_API_KEY": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "Google Gemini API Key (pisahkan koma untuk multi-key rotation)",
    },
    "GEMINI_MODEL": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "gemini-3.7-flash",
        "description": "Model primer Google Gemini",
    },
    "GEMINI_FALLBACK_MODEL": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "gemini-2.5-flash",
        "description": "Model cadangan Google Gemini",
    },
    "GROQ_API_KEY": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "Groq API Key (opsional fallback)",
    },
    "GROQ_LLM_MODEL": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "llama-3.1-8b-instant",
        "description": "Model primer Groq LLM",
    },
    "PEXELS_API_KEY": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "Pexels API Key untuk auto B-roll footage",
    },
    "PIXABAY_API_KEY": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "Pixabay API Key untuk stock footage & image",
    },
    "GIPHY_API_KEY": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "Giphy API Key untuk animasi stiker/GIF",
    },
    "HF_TOKEN": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "Hugging Face User Access Token untuk Pyannote Diarization",
    },
    "YOUTUBE_API_KEY": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "YouTube Data API v3 key untuk metadata & search",
    },
    "VIDKRAKEN_API_KEY": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "ce1bcba1-b808-470f-987c-072ca2d35488",
        "description": "VidKraken API Key untuk download video YouTube (Primary)",
    },
    "VIDKRAKEN_BASE_URL": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "https://vidkraken.com/api/v2",
        "description": "Base URL VidKraken API",
    },
    "VIDKRAKEN_ENABLED": {
        "category": "api_keys",
        "data_type": "bool",
        "min_role": "superadmin",
        "is_secret": False,
        "default": False,
        "description": "Aktifkan VidKraken sebagai downloader video YouTube",
    },
    "COBALT_API_URL": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "http://localhost:9000",
        "description": "Base URL Cobalt API Downloader (Self-Hosted / Fallback)",
    },
    "COBALT_ENABLED": {
        "category": "api_keys",
        "data_type": "bool",
        "min_role": "superadmin",
        "is_secret": False,
        "default": True,
        "description": "Aktifkan Cobalt API sebagai downloader video YouTube fallback",
    },
    "DEEPGRAM_API_KEY": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "Deepgram API Key untuk TTS voiceovers (opsional)",
    },
    "DEEPGRAM_TTS_VOICE": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "editor",
        "is_secret": False,
        "default": "aura-2-thalia-en",
        "description": "Voice ID Deepgram TTS",
    },
    "ELEVENLABS_API_KEY": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "ElevenLabs API Key (xi-api-key) untuk studio high-fidelity TTS",
    },
    "ELEVEN_API_KEY": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "ElevenLabs API Key alias",
    },
    "ELEVENLABS_VOICE_ID": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "editor",
        "is_secret": False,
        "default": "rUOpAdbAl56KxO00wR5D",
        "description": "Default Voice ID ElevenLabs (misal: rUOpAdbAl56KxO00wR5D / Adam / Rachel)",
    },
    "ELEVENLABS_MODEL_ID": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "editor",
        "is_secret": False,
        "default": "eleven_multilingual_v2",
        "description": "Default Model ElevenLabs (eleven_multilingual_v2 / eleven_flash_v2_5 / eleven_turbo_v2_5)",
    },
    "GEMINI_TTS_MODEL": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "editor",
        "is_secret": False,
        "default": "gemini-3.1-flash-tts-preview",
        "description": "Default Model Gemini TTS (gemini-3.1-flash-tts-preview / gemini-2.5-flash-preview-tts / gemini-2.5-pro-preview-tts)",
    },
    "GEMINI_TTS_VOICE": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "editor",
        "is_secret": False,
        "default": "Kore",
        "description": "Default Voice Gemini TTS (Kore, Puck, Fenrir, Aoede, Charon, Leda, Zephyr, Orus)",
    },
    "VIDEO_GEN_TTS_PROVIDER": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "editor",
        "is_secret": False,
        "default": "gemini",
        "description": "TTS Provider Utama untuk Video Generator: gemini (default) atau deepgram",
    },
    "CLIPSCOUT_API_URL": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "https://www.clipscout.app/api/search",
        "description": "Endpoint ClipScout AI Search Engine",
    },
    "CLIPSCOUT_ENABLED_SOURCES": {
        "category": "api_keys",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "pexels,pixabay,youtube_cc,youtube_protected",
        "description": "Sumber aset footage yang aktif pada ClipScout",
    },

    # ─── Group 3: Render Engines & System Limits ─────────────────────────────
    "USE_REMOTION": {
        "category": "render_limits",
        "data_type": "bool",
        "min_role": "superadmin",
        "is_secret": False,
        "default": True,
        "description": "Aktifkan engine rendering Remotion (React WebGL/Canvas)",
    },
    "REMOTION_SERVER_URL": {
        "category": "render_limits",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "http://localhost:3002",
        "description": "URL service Remotion Render Server",
    },
    "REMOTION_CONCURRENCY": {
        "category": "render_limits",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 2,
        "description": "Jumlah render frame paralel pada Remotion",
    },
    "REMOTION_QUALITY": {
        "category": "render_limits",
        "data_type": "string",
        "min_role": "editor",
        "is_secret": False,
        "default": "medium",
        "description": "Kualitas render Remotion (low, medium, high)",
    },
    "REMOTION_SUBTITLE_OFFSET": {
        "category": "render_limits",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": -0.5,
        "description": "Offset sinkronisasi subtitle Remotion dalam detik (negatif = lebih awal)",
    },
    "USE_NVENC": {
        "category": "render_limits",
        "data_type": "bool",
        "min_role": "superadmin",
        "is_secret": False,
        "default": True,
        "description": "Gunakan akselerasi hardware NVIDIA NVENC saat export final video",
    },
    "NVENC_QUALITY": {
        "category": "render_limits",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "medium",
        "description": "Preset kualitas NVENC (low, medium, high)",
    },
    "MAX_CONCURRENT_JOBS": {
        "category": "render_limits",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 1,
        "description": "Maksimal pemrosesan job video secara simultan (1 = antrean sekuensial aman)",
    },
    "MAX_WHISPER_PARALLEL": {
        "category": "render_limits",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 1,
        "description": "Maksimal proses transkripsi Whisper paralel",
    },
    "MAX_RENDER_WORKERS": {
        "category": "render_limits",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 4,
        "description": "Jumlah worker proses render klip FFmpeg paralel",
    },
    "MAX_VIDEO_DURATION": {
        "category": "render_limits",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 3600,
        "description": "Batas maksimal durasi video input dalam detik (3600 = 1 jam)",
    },
    "MAX_UPLOAD_SIZE_MB": {
        "category": "render_limits",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 4096,
        "description": "Maksimal ukuran file video upload (MB)",
    },
    "CLEANUP_MAX_AGE_DAYS": {
        "category": "render_limits",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 7,
        "description": "Otomatis hapus file temporary yang lebih lama dari N hari",
    },

    # ─── Group 4: Vision AI & Reframe Tuning ─────────────────────────────────
    "REFRAME_PIPELINE_MODE": {
        "category": "vision_reframe",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "person_first",
        "description": "Mode pipeline reframe (person_first, shadow, legacy)",
    },
    "PERSON_DETECTOR": {
        "category": "vision_reframe",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "rfdetr-large",
        "description": "Model deteksi subjek manusia (rfdetr-large, rfdetr-medium)",
    },
    "PERSON_CONF_THRESHOLD": {
        "category": "vision_reframe",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.35,
        "description": "Ambang batas confidence deteksi manusia (0.1 - 0.9)",
    },
    "PERSON_TRACKER": {
        "category": "vision_reframe",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "botsort",
        "description": "Algoritma multi-object tracking (botsort, bytetrack)",
    },
    "FACE_DETECTOR": {
        "category": "vision_reframe",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "retinaface",
        "description": "Model deteksi wajah (retinaface, scrfd)",
    },
    "FACE_CONFIDENCE": {
        "category": "vision_reframe",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.55,
        "description": "Ambang batas confidence deteksi wajah (0.1 - 0.9)",
    },
    "DIARIZATION_ENABLED": {
        "category": "vision_reframe",
        "data_type": "bool",
        "min_role": "editor",
        "is_secret": False,
        "default": True,
        "description": "Aktifkan speaker diarization untuk mendeteksi pembicara aktif",
    },

    # ─── Group 5: Visual Effects & B-Roll / Overlay ──────────────────────────
    "BROLL_SPLICE_ENABLED": {
        "category": "broll_effects",
        "data_type": "bool",
        "min_role": "editor",
        "is_secret": False,
        "default": True,
        "description": "Aktifkan auto insert B-Roll splice intercut",
    },
    "BROLL_SPLICE_MAX_PER_CLIP": {
        "category": "broll_effects",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 3,
        "description": "Maksimal footage B-roll per klip",
    },
    "BROLL_SPLICE_CROSSFADE_SEC": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.15,
        "description": "Durasi transisi crossfade B-roll dalam detik",
    },
    "TOP_OVERLAY_ENABLED": {
        "category": "broll_effects",
        "data_type": "bool",
        "min_role": "editor",
        "is_secret": False,
        "default": True,
        "description": "Aktifkan Top Behind Subject Overlay (B-Roll di belakang subjek)",
    },
    "TOP_OVERLAY_SPLIT_RATIO": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.65,
        "description": "Tinggi area overlay footage bagian atas (0.3 - 0.8)",
    },
    "TOP_OVERLAY_OPACITY": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 1.0,
        "description": "Transparansi footage overlay (0.1 - 1.0)",
    },
    "OBJECT_OVERLAY_ENABLED": {
        "category": "broll_effects",
        "data_type": "bool",
        "min_role": "editor",
        "is_secret": False,
        "default": True,
        "description": "Aktifkan kartu pop-up objek saat kata benda disebut",
    },
    "OBJECT_OVERLAY_MAX_PER_CLIP": {
        "category": "broll_effects",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 3,
        "description": "Maksimal kartu objek per klip",
    },
    "OBJECT_OVERLAY_BOX_SIZE": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.28,
        "description": "Ukuran box overlay objek proporsional layar",
    },
    "OBJECT_OVERLAY_CORNER_RADIUS": {
        "category": "broll_effects",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 18,
        "description": "Kelengkungan sudut kartu overlay objek (px)",
    },
    "OBJECT_OVERLAY_POSITION": {
        "category": "broll_effects",
        "data_type": "string",
        "min_role": "editor",
        "is_secret": False,
        "default": "top_right",
        "description": "Posisi munculnya kartu objek (top_right, top_left, bottom_right, bottom_left)",
    },
    "OBJECT_OVERLAY_ANIMATION": {
        "category": "broll_effects",
        "data_type": "string",
        "min_role": "editor",
        "is_secret": False,
        "default": "slide_right",
        "description": "Animasi masuk kartu objek (slide_right, slide_left, slide_down, pop, fade)",
    },
    "OBJECT_OVERLAY_DURATION": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 2.4,
        "description": "Durasi tampilan kartu objek (detik)",
    },
    "OBJECT_OVERLAY_MIN_RELEVANCE": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.35,
        "description": "Ambang batas relevansi kata objek untuk memicu overlay",
    },
    "OBJECT_OVERLAY_SHOW_LABEL": {
        "category": "broll_effects",
        "data_type": "bool",
        "min_role": "editor",
        "is_secret": False,
        "default": True,
        "description": "Tampilkan label teks nama objek di bawah kartu",
    },
    "ASSET_FETCH_ENABLED": {
        "category": "broll_effects",
        "data_type": "bool",
        "min_role": "editor",
        "is_secret": False,
        "default": True,
        "description": "Aktifkan auto fetcher stock asset (Pexels, Pixabay, Giphy)",
    },
    "BROLL_MAX_FOOTAGE_SIZE_MB": {
        "category": "broll_effects",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 50,
        "description": "Batas maksimal ukuran file footage B-Roll download (MB)",
    },
    "TOP_OVERLAY_FADE_HEIGHT": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.15,
        "description": "Ketinggian area gradien transisi lembut overlay atas",
    },
    "TOP_OVERLAY_MAX_PER_CLIP": {
        "category": "broll_effects",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 3,
        "description": "Maksimal segmen Top Behind Overlay per klip",
    },
    "TOP_OVERLAY_SEG_CONFIDENCE": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.35,
        "description": "Confidence threshold segmentasi subjek untuk top overlay",
    },
    "TOP_OVERLAY_MASK_FEATHER": {
        "category": "broll_effects",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 9,
        "description": "Feathering tepi matte segmentasi subjek (anti-aliasing)",
    },
    "TOP_OVERLAY_MASK_STRIDE": {
        "category": "broll_effects",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 2,
        "description": "Stride sampling frame untuk segmentasi overlay",
    },
    "TOP_OVERLAY_PERSON_OUTLINE": {
        "category": "broll_effects",
        "data_type": "bool",
        "min_role": "editor",
        "is_secret": False,
        "default": False,
        "description": "Garis tepi siluet subjek (outline neon/putih)",
    },
    "TOP_OVERLAY_PERSON_SHADOW": {
        "category": "broll_effects",
        "data_type": "bool",
        "min_role": "editor",
        "is_secret": False,
        "default": True,
        "description": "Bayangan ambient di belakang subjek",
    },
    "TOP_OVERLAY_OUTLINE_THICKNESS": {
        "category": "broll_effects",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 12,
        "description": "Ketebalan outline siluet subjek (px)",
    },
    "TOP_OVERLAY_OUTLINE_COLOR": {
        "category": "broll_effects",
        "data_type": "string",
        "min_role": "editor",
        "is_secret": False,
        "default": "255,255,255",
        "description": "Warna RGB outline siluet subjek (r,g,b)",
    },
    "TOP_OVERLAY_OUTLINE_STYLE": {
        "category": "broll_effects",
        "data_type": "string",
        "min_role": "editor",
        "is_secret": False,
        "default": "white",
        "description": "Style outline (white, neon, comic, gradient)",
    },
    "TOP_OVERLAY_CROP_BIAS_Y": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.08,
        "description": "Bias vertikal crop overlay",
    },
    "TOP_OVERLAY_SPEAKER_MASK_MODE": {
        "category": "broll_effects",
        "data_type": "string",
        "min_role": "editor",
        "is_secret": False,
        "default": "dual_auto",
        "description": "Mode masking pembicara (single, dual_auto)",
    },
    "TOP_OVERLAY_SMART_CROP": {
        "category": "broll_effects",
        "data_type": "bool",
        "min_role": "editor",
        "is_secret": False,
        "default": True,
        "description": "Aktifkan auto smart-crop fokus subjek",
    },
    "TOP_OVERLAY_SMART_CROP_CONF": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.18,
        "description": "Confidence threshold smart-crop",
    },
    "TOP_OVERLAY_PERSON_SCALE": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.82,
        "description": "Skala subjek manusia pada frame overlay",
    },
    "TOP_OVERLAY_PERSON_SHIFT_Y": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.30,
        "description": "Pergeseran posisi vertikal subjek manusia",
    },
    "TOP_OVERLAY_OUTLINE_BUST_RATIO": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.48,
        "description": "Rasio potongan bust outline (kepala ke pundak)",
    },
    "TOP_OVERLAY_OUTLINE_EDGE_MARGIN": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.04,
        "description": "Margin tepi outline",
    },
    "TOP_OVERLAY_PERSON_ANCHOR": {
        "category": "broll_effects",
        "data_type": "string",
        "min_role": "editor",
        "is_secret": False,
        "default": "natural",
        "description": "Anchor titik tumpu subjek (natural, center, bottom)",
    },
    "TOP_OVERLAY_PERSON_EDGE_MARGIN": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.03,
        "description": "Margin tepi subjek manusia",
    },
    "TOP_OVERLAY_BG_BLACK": {
        "category": "broll_effects",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.55,
        "description": "Level kegelapan backdrop belakang subjek (0.0 - 1.0)",
    },

    # ─── Vision AI & Diarization Models ──────────────────────────────────────
    "DIARIZATION_MODEL": {
        "category": "vision_reframe",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "pyannote/speaker-diarization-3.1",
        "description": "Model PyAnnote Speaker Diarization",
    },
    "DIARIZATION_TIMEOUT_SEC": {
        "category": "vision_reframe",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 60,
        "description": "Timeout proses diarization pembicara (detik)",
    },
    "DIARIZATION_MIN_SPEAKERS": {
        "category": "vision_reframe",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 2,
        "description": "Estimasi jumlah minimal pembicara",
    },
    "DIARIZATION_MAX_SPEAKERS": {
        "category": "vision_reframe",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 4,
        "description": "Estimasi jumlah maksimal pembicara",
    },
    "DIARIZATION_MAPPING_CONFIDENCE_THRESHOLD": {
        "category": "vision_reframe",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.5,
        "description": "Confidence threshold mapping suara ke wajah pembicara",
    },
    "YOLO_MODEL_VERSION": {
        "category": "vision_reframe",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "v26",
        "description": "Versi arsitektur YOLO (v8, v11, v26)",
    },
    "YOLO_MODEL_PATH": {
        "category": "vision_reframe",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "models/yolo26n.pt",
        "description": "Path bobot model YOLO Object Detection",
    },
    "YOLO_SEG_MODEL": {
        "category": "vision_reframe",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "models/yolo26n-seg.pt",
        "description": "Path bobot model YOLO Instance Segmentation",
    },
    "TEXT_EMPHASIS_MAX_EVENTS": {
        "category": "vision_reframe",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 2,
        "description": "Maksimal event penekanan teks per klip",
    },
    "TEXT_EMPHASIS_SEG_CONFIDENCE": {
        "category": "vision_reframe",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.35,
        "description": "Confidence threshold segmentasi untuk text emphasis",
    },
    "TEXT_EMPHASIS_MASK_FEATHER": {
        "category": "vision_reframe",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 9,
        "description": "Feathering mask text emphasis (px)",
    },

    # ─── Deepgram TTS Tuning ─────────────────────────────────────────────────
    "DEEPGRAM_TTS_SPEED": {
        "category": "api_keys",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 1.0,
        "description": "Kecepatan suara Deepgram TTS (0.5 - 2.0)",
    },
    "DEEPGRAM_TTS_TIMEOUT": {
        "category": "api_keys",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 30,
        "description": "Timeout request voiceover Deepgram TTS (detik)",
    },
    "CLIPSCOUT_TIMEOUT": {
        "category": "api_keys",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 15,
        "description": "Timeout request ClipScout search (detik)",
    },
    "CLIPSCOUT_MAX_RETRIES": {
        "category": "api_keys",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 2,
        "description": "Maksimal retry ClipScout jika timeout/error",
    },

    # ─── Render Engine & System Limits ───────────────────────────────────────
    "WHISPER_MODEL_SIZE": {
        "category": "render_limits",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "medium",
        "description": "Ukuran model Faster-Whisper lokal (tiny, base, small, medium, large-v3)",
    },
    "WHISPER_THREADS": {
        "category": "render_limits",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 8,
        "description": "Jumlah CPU threads untuk transkripsi Whisper lokal",
    },
    "REMOTION_SERVER_PORT": {
        "category": "render_limits",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 3002,
        "description": "Port port server Remotion Renderer",
    },
    "MIN_RAM_GB": {
        "category": "render_limits",
        "data_type": "float",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 4.0,
        "description": "Batas minimum sisa RAM sistem sebelum menerima job baru (GB)",
    },
    "MIN_DISK_GB": {
        "category": "render_limits",
        "data_type": "float",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 10.0,
        "description": "Batas minimum sisa disk storage sistem (GB)",
    },
    "VIDEO_FINAL_RESULT": {
        "category": "render_limits",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "",
        "description": "Override jumlah klip video yang dihasilkan (kosong = otomatis AI)",
    },
    "VIDEO_GEN_ENABLED": {
        "category": "render_limits",
        "data_type": "bool",
        "min_role": "superadmin",
        "is_secret": False,
        "default": True,
        "description": "Aktifkan engine AI Video Generator dari prompt narasi",
    },
    "VIDEO_GEN_TARGET_DURATION": {
        "category": "render_limits",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 65,
        "description": "Target durasi video AI Generator (detik)",
    },
    "VIDEO_GEN_MIN_DURATION": {
        "category": "render_limits",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 50,
        "description": "Batas minimum durasi video AI Generator (detik)",
    },
    "VIDEO_GEN_MAX_DURATION": {
        "category": "render_limits",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 90,
        "description": "Batas maksimal durasi video AI Generator (detik)",
    },
    "VIDEO_GEN_MAX_SCENES": {
        "category": "render_limits",
        "data_type": "int",
        "min_role": "editor",
        "is_secret": False,
        "default": 10,
        "description": "Maksimal adegan / visual cuts pada video AI Generator",
    },
    "VIDEO_GEN_BGM_DIR": {
        "category": "render_limits",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "assets/bgm",
        "description": "Direktori koleksi musik latar (BGM)",
    },
    "VIDEO_GEN_BGM_VOLUME": {
        "category": "render_limits",
        "data_type": "float",
        "min_role": "editor",
        "is_secret": False,
        "default": 0.15,
        "description": "Volume audio background music (0.0 - 1.0)",
    },
    "VIDEO_GEN_OUTPUT_DIR": {
        "category": "render_limits",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "tmp/video_gen",
        "description": "Folder output render AI Video Generator",
    },

    # ─── HyperFrames & Creative Agents ───────────────────────────────────────
    "HYPERFRAMES_ENABLED": {
        "category": "ai_llm",
        "data_type": "bool",
        "min_role": "superadmin",
        "is_secret": False,
        "default": True,
        "description": "Aktifkan engine HyperFrames polish layer (lower-third visual)",
    },
    "HYPERFRAMES_SERVER_URL": {
        "category": "render_limits",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "http://127.0.0.1:3003",
        "description": "URL endpoint service HyperFrames Renderer",
    },
    "HYPERFRAMES_SERVER_PORT": {
        "category": "render_limits",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 3003,
        "description": "Port server HyperFrames",
    },
    "HYPERFRAMES_PROJECT_PATH": {
        "category": "render_limits",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "../hyperframes-renderer",
        "description": "Lokasi direktori project template HyperFrames",
    },
    "HYPERFRAMES_TIMEOUT": {
        "category": "render_limits",
        "data_type": "int",
        "min_role": "superadmin",
        "is_secret": False,
        "default": 180,
        "description": "Batas timeout render klip HyperFrames (detik)",
    },
    "HYPERFRAMES_DEFAULT_TEMPLATE": {
        "category": "render_limits",
        "data_type": "string",
        "min_role": "editor",
        "is_secret": False,
        "default": "lower_third_v1",
        "description": "Template default HyperFrames overlay",
    },
    "HERMES_ENABLED": {
        "category": "ai_llm",
        "data_type": "bool",
        "min_role": "superadmin",
        "is_secret": False,
        "default": True,
        "description": "Aktifkan Hermes Autonomous Creative Agent",
    },
    "HERMES_BIN": {
        "category": "ai_llm",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "hermes",
        "description": "Executable binary name Hermes CLI",
    },
    "HERMES_HOME": {
        "category": "ai_llm",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "",
        "description": "Direktori home / state Hermes Agent",
    },

    # ─── Group 6: Storage / MinIO & CDN ──────────────────────────────────────
    "MINIO_ENDPOINT": {
        "category": "storage_cdn",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "",
        "description": "Host dan port endpoint MinIO Object Storage",
    },
    "MINIO_ACCESS_KEY": {
        "category": "storage_cdn",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "Access Key kredensial MinIO",
    },
    "MINIO_SECRET_KEY": {
        "category": "storage_cdn",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "Secret Key kredensial MinIO",
    },
    "MINIO_BUCKET": {
        "category": "storage_cdn",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "",
        "description": "Nama bucket penyimpanan MinIO",
    },
    "MINIO_SECURE": {
        "category": "storage_cdn",
        "data_type": "bool",
        "min_role": "superadmin",
        "is_secret": False,
        "default": False,
        "description": "Gunakan protokol HTTPS aman untuk koneksi MinIO",
    },
    "CDN_ENABLED": {
        "category": "storage_cdn",
        "data_type": "bool",
        "min_role": "superadmin",
        "is_secret": False,
        "default": False,
        "description": "Aktifkan upload file hasil ke MinIO/S3 CDN",
    },
    "CDN_ENDPOINT": {
        "category": "storage_cdn",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "",
        "description": "Endpoint URL MinIO / S3",
    },
    "CDN_BUCKET": {
        "category": "storage_cdn",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "",
        "description": "Nama bucket penyimpanan video",
    },
    "CDN_ACCESS_KEY": {
        "category": "storage_cdn",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "Access Key MinIO / S3",
    },
    "CDN_SECRET_KEY": {
        "category": "storage_cdn",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "Secret Key MinIO / S3",
    },

    # ─── Group 7: Integrations & Cloud Drives ────────────────────────────────
    "TELEGRAM_BOT_TOKEN": {
        "category": "integrations",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "Telegram Bot API Token untuk notifikasi instan",
    },
    "REPLIZ_ACCESS_KEY": {
        "category": "integrations",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "Access Key Repliz Social Automation",
    },
    "REPLIZ_SECRET_KEY": {
        "category": "integrations",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "Secret Key Repliz Social Automation",
    },
    "GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE": {
        "category": "integrations",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "credentials/gdrive-service-account.json",
        "description": "Path file service account JSON Google Drive",
    },
    "GOOGLE_DRIVE_FOLDER_ID": {
        "category": "integrations",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "",
        "description": "Folder ID target upload Google Drive",
    },
    "GOOGLE_DRIVE_CLIENT_ID": {
        "category": "integrations",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "OAuth Client ID Google Drive",
    },
    "GOOGLE_DRIVE_CLIENT_SECRET": {
        "category": "integrations",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "OAuth Client Secret Google Drive",
    },
    "GOOGLE_DRIVE_REFRESH_TOKEN": {
        "category": "integrations",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": True,
        "default": "",
        "description": "OAuth Refresh Token Google Drive",
    },
    "AUTOCLIPER_PUBLIC_URL": {
        "category": "integrations",
        "data_type": "string",
        "min_role": "superadmin",
        "is_secret": False,
        "default": "https://cliperhub-tunnel.trycloudflare.com",
        "description": "Public base URL / Tunnel domain untuk media streaming Repliz & sosial media",
    },
}

# Role hierarchy ranking
ROLE_LEVELS = {
    "superadmin": 3,
    "admin": 3,
    "editor": 2,
    "viewer": 1,
}

# In-memory settings cache
_SETTINGS_CACHE: dict[str, Any] = {}
_TABLE_ENSURED = False


def _ensure_settings_table():
    """Ensure system_settings table exists."""
    global _TABLE_ENSURED
    if _TABLE_ENSURED:
        return
    conn = get_dict_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'general',
                data_type TEXT NOT NULL DEFAULT 'string',
                min_role TEXT NOT NULL DEFAULT 'superadmin',
                is_secret INTEGER NOT NULL DEFAULT 0,
                description TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_by INTEGER DEFAULT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()
    _TABLE_ENSURED = True


def _coerce_value(val_str: str, data_type: str) -> Any:
    """Coerce string value to target data type."""
    if val_str is None or val_str == "":
        return None
    if data_type == "bool":
        return str(val_str).lower() in ("true", "1", "yes", "t", "on")
    if data_type == "int":
        try:
            return int(val_str)
        except (ValueError, TypeError):
            return 0
    if data_type == "float":
        try:
            return float(val_str)
        except (ValueError, TypeError):
            return 0.0
    if data_type == "json":
        try:
            return json.loads(val_str)
        except Exception:
            return {}
    return str(val_str)


def mask_secret_value(value: str) -> str:
    """Mask sensitive string (e.g. API keys)."""
    if not value or len(value) < 6:
        return "******" if value else ""
    return f"{value[:3]}...{value[-4:]}"


def get_system_setting(key: str, default: Any = None) -> Any:
    """Get a system setting with in-memory caching and .env fallback."""
    if key in _SETTINGS_CACHE:
        return _SETTINGS_CACHE[key]

    meta = SYSTEM_SETTINGS_METADATA.get(key)
    target_type = meta["data_type"] if meta else "string"

    try:
        _ensure_settings_table()
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
            row = cur.fetchone()
            if row and row["value"] != "":
                coerced = _coerce_value(row["value"], target_type)
                _SETTINGS_CACHE[key] = coerced
                return coerced
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"[system_config_store] DB lookup error for {key}: {exc}")

    fallback = meta["default"] if meta else default
    _SETTINGS_CACHE[key] = fallback
    return fallback


def set_system_setting(key: str, value: Any, user_id: Optional[int] = None) -> bool:
    """Upsert a system setting in DB and invalidate in-memory cache."""
    _ensure_settings_table()
    meta = SYSTEM_SETTINGS_METADATA.get(key, {})
    category = meta.get("category", "general")
    data_type = meta.get("data_type", "string")
    min_role = meta.get("min_role", "superadmin")
    is_secret = 1 if meta.get("is_secret") else 0
    description = meta.get("description", "")

    # Convert value to string for storage
    if isinstance(value, bool):
        val_str = "true" if value else "false"
    elif isinstance(value, (dict, list)):
        val_str = json.dumps(value)
    else:
        val_str = str(value) if value is not None else ""

    conn = get_dict_connection()
    try:
        conn.execute("""
            INSERT INTO system_settings (key, value, category, data_type, min_role, is_secret, description, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = datetime('now'),
                updated_by = excluded.updated_by
        """, (key, val_str, category, data_type, min_role, is_secret, description, user_id))
        conn.commit()
        # Invalidate / update cache
        _SETTINGS_CACHE[key] = _coerce_value(val_str, data_type)
        logger.info(f"[system_config_store] Set {key} by user_id={user_id}")
        return True
    except Exception as exc:
        logger.error(f"[system_config_store] Failed to save {key}: {exc}")
        return False
    finally:
        conn.close()


def bulk_set_system_settings(updates: dict[str, Any], user_id: Optional[int] = None) -> int:
    """Bulk update multiple system settings transactionally."""
    _ensure_settings_table()
    count = 0
    conn = get_dict_connection()
    try:
        for key, value in updates.items():
            meta = SYSTEM_SETTINGS_METADATA.get(key, {})
            category = meta.get("category", "general")
            data_type = meta.get("data_type", "string")
            min_role = meta.get("min_role", "superadmin")
            is_secret = 1 if meta.get("is_secret") else 0
            description = meta.get("description", "")

            if isinstance(value, bool):
                val_str = "true" if value else "false"
            elif isinstance(value, (dict, list)):
                val_str = json.dumps(value)
            else:
                val_str = str(value) if value is not None else ""

            conn.execute("""
                INSERT INTO system_settings (key, value, category, data_type, min_role, is_secret, description, updated_at, updated_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = datetime('now'),
                    updated_by = excluded.updated_by
            """, (key, val_str, category, data_type, min_role, is_secret, description, user_id))
            _SETTINGS_CACHE[key] = _coerce_value(val_str, data_type)
            count += 1
        conn.commit()
        logger.info(f"[system_config_store] Bulk updated {count} settings by user_id={user_id}")
        return count
    except Exception as exc:
        logger.error(f"[system_config_store] Bulk update failed: {exc}")
        return 0
    finally:
        conn.close()


def get_all_settings_for_role(role_name: str, unmask_secrets: bool = False) -> list[dict[str, Any]]:
    """Retrieve all configuration keys allowed for the specified user role."""
    _ensure_settings_table()
    user_level = ROLE_LEVELS.get(role_name.lower(), 1)

    # Read all stored settings in DB
    db_values: dict[str, dict[str, Any]] = {}
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT key, value, updated_at, updated_by FROM system_settings")
        for row in cur.fetchall():
            db_values[row["key"]] = {
                "value": row["value"],
                "updated_at": row["updated_at"],
                "updated_by": row["updated_by"],
            }
    finally:
        conn.close()

    result = []
    for key, meta in SYSTEM_SETTINGS_METADATA.items():
        req_role = meta["min_role"]
        req_level = ROLE_LEVELS.get(req_role, 3)

        # Skip if user role level is insufficient
        if user_level < req_level:
            continue

        raw_val = db_values.get(key, {}).get("value")
        if raw_val is None or raw_val == "":
            val = meta["default"]
        else:
            val = _coerce_value(raw_val, meta["data_type"])

        # Format / mask value
        is_secret = meta["is_secret"]
        display_val = val
        if is_secret and not unmask_secrets:
            display_val = mask_secret_value(str(val or ""))

        result.append({
            "key": key,
            "value": display_val,
            "raw_value": val if (user_level >= 3 or not is_secret) else "",
            "category": meta["category"],
            "data_type": meta["data_type"],
            "min_role": meta["min_role"],
            "is_secret": is_secret,
            "description": meta["description"],
            "updated_at": db_values.get(key, {}).get("updated_at"),
            "updated_by": db_values.get(key, {}).get("updated_by"),
        })

    return result


def seed_system_settings_defaults():
    """Seed initial defaults from SYSTEM_SETTINGS_METADATA into DB if not present."""
    _ensure_settings_table()
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT key FROM system_settings")
        existing_keys = {r["key"] for r in cur.fetchall()}

        for key, meta in SYSTEM_SETTINGS_METADATA.items():
            if key not in existing_keys:
                env_val = meta["default"]
                if isinstance(env_val, bool):
                    val_str = "true" if env_val else "false"
                elif isinstance(env_val, (dict, list)):
                    val_str = json.dumps(env_val)
                else:
                    val_str = str(env_val) if env_val is not None else ""

                cur.execute("""
                    INSERT OR IGNORE INTO system_settings
                    (key, value, category, data_type, min_role, is_secret, description, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """, (
                    key,
                    val_str,
                    meta["category"],
                    meta["data_type"],
                    meta["min_role"],
                    1 if meta["is_secret"] else 0,
                    meta["description"],
                ))
        conn.commit()
    finally:
        conn.close()
