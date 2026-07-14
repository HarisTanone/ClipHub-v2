"""Application configuration — environment-based (local M1 vs production server)."""
import os
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings

PIPELINE_ENV = os.getenv("PIPELINE_ENV", "local")


class Settings(BaseSettings):
    # Environment
    PIPELINE_ENV: str = "local"
    CORS_ORIGINS: str = ""

    # === Model routing ===
    # 9router is the default LLM gateway. Direct provider fallbacks stay off in
    # production so Gemini/Groq keys are not used accidentally.
    LLM_PROVIDER: str = "nine_router"
    FORCE_V2_PIPELINE: bool = True
    ALLOW_DIRECT_PROVIDER_FALLBACKS: bool = False
    # Legacy value retained for existing deployments. When 9router is
    # configured, Whisper calls are router-first with an automatic local fallback.
    TRANSCRIPTION_PROVIDER: str = "local"

    # Database (SQLite)
    DATABASE_URL: str = "sqlite+aiosqlite:///data/autoclip.db"

    # 9router / OpenAI-compatible chat completions API
    NINE_ROUTER_BASE_URL: str = ""
    NINE_ROUTER_API_KEY: str = ""
    NINE_ROUTER_MODEL: str = "ngentot"
    NINE_ROUTER_PASS1_MODEL: str = "ngentot"
    NINE_ROUTER_PASS2_MODEL: str = "ngentot"
    NINE_ROUTER_AI_LAYER_MODEL: str = "ngentot"
    NINE_ROUTER_TIMEOUT: int = 120
    NINE_ROUTER_MAX_RETRIES: int = 3
    NINE_ROUTER_TEMPERATURE: float = 0.3
    # Groq Whisper through 9router. This is independent from the LLM combo
    # model because 9router expects the provider-qualified audio model name.
    NINE_ROUTER_WHISPER_ENABLED: bool = True
    NINE_ROUTER_WHISPER_MODEL: str = "groq/whisper-large-v3-turbo"
    NINE_ROUTER_WHISPER_TIMEOUT: int = 120
    # Fail over to local Whisper immediately by default; do not add retry waits
    # to subtitle generation when the local 9router service is unavailable.
    NINE_ROUTER_WHISPER_MAX_RETRIES: int = 1

    # Gemini — supports multiple keys: "key1,key2,key3"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"
    GEMINI_FALLBACK_MODEL: str = "gemini-2.5-flash"

    # YouTube Data API v3 (for transcript/captions)
    YOUTUBE_API_KEY: str = ""

    # ─── Auth / JWT ───────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_REFRESH_SECRET_KEY: str = "change-me-refresh-in-production"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "HS256"

    # ─── Superadmin Seed ──────────────────────────────────────────────────
    SUPERADMIN_EMAIL: str = "admin@autocliper.com"
    SUPERADMIN_PASSWORD: str = "Admin@2024!Secure"

    # === Job Concurrency ===
    MAX_CONCURRENT_JOBS: int = 1 if PIPELINE_ENV == "local" else 8
    MAX_WHISPER_PARALLEL: int = 1 if PIPELINE_ENV == "local" else 4
    MAX_RENDER_WORKERS: int = 2 if PIPELINE_ENV == "local" else 6

    # === Limits ===
    MAX_VIDEO_DURATION: int = 300 if PIPELINE_ENV == "local" else 3600
    MAX_UPLOAD_SIZE_MB: int = 2048 if PIPELINE_ENV == "local" else 5120
    DOWNLOAD_TIMEOUT: int = 300 if PIPELINE_ENV == "local" else 600
    MIN_CLIP_DURATION: float = 45.0

    # === Paths ===
    OUTPUT_DIR: str = "tmp/output"
    DOWNLOAD_DIR: str = "tmp/downloads"
    WAV_DIR: str = "/tmp/pipeline/wav" if PIPELINE_ENV == "local" else "/dev/shm/pipeline_wav"

    # === Whisper (local whisper.cpp) ===
    WHISPER_MODEL_PATH: str = ""
    WHISPER_BINARY_PATH: str = ""
    WHISPER_THREADS: int = 4 if PIPELINE_ENV == "local" else 6
    WHISPER_USE_GPU: bool = True  # Auto-detect: uses CUDA if available, else CPU
    WHISPER_MODEL_SIZE: str = "medium"  # tiny, base, small, medium, large-v3

    # === GPU Acceleration ===
    USE_NVENC: bool = True              # Use h264_nvenc for FFmpeg encoding (auto-fallback to libx264)
    NVENC_QUALITY: str = "medium"       # low (fast), medium (balanced), high (best quality)
    GPU_WHISPER_DEVICE: str = "auto"    # "auto" (detect), "cuda", "cpu"

    # === VAD (Voice Activity Detection) ===
    VAD_ENABLED: bool = True
    VAD_MIN_SILENCE_MS: int = 300  # minimum silence gap duration to consider

    # === Whisper CoreML (Apple Silicon acceleration) ===
    WHISPER_USE_COREML: bool = False
    WHISPER_COREML_MODEL_PATH: str = ""

    # === Download ===
    USE_ARIA2C: bool = False if PIPELINE_ENV == "local" else True

    # Cleanup
    CLEANUP_MAX_AGE_DAYS: int = 7

    # === Resource Monitor Thresholds ===
    MIN_DISK_GB: float = 5.0
    MIN_RAM_GB: float = 2.0

    # === Dev/Testing ===
    VIDEO_FINAL_RESULT: Optional[int] = None  # None = follow AI recommendation

    @field_validator("VIDEO_FINAL_RESULT", mode="before")
    @classmethod
    def parse_empty_int(cls, v):
        if v == "" or v is None:
            return None
        return int(v)

    # === Default Style Preset ===
    DEFAULT_STYLE_PRESET: str = "bold_black"

    # === YOLO Models ===
    YOLO_MODEL_VERSION: str = "v11"
    YOLO_MODEL_PATH: str = "models/yolo11n.pt"
    YOLO_SEG_MODEL: str = "models/yolo11n-seg.pt"

    # === HuggingFace (Pyannote Speaker Diarization) ===
    HF_TOKEN: str = ""

    # === Speaker Diarization (PyAnnote) ===
    DIARIZATION_ENABLED: bool = True
    DIARIZATION_MODEL: str = "pyannote/speaker-diarization-3.1"
    DIARIZATION_TIMEOUT_SEC: int = 60
    DIARIZATION_MIN_SPEAKERS: int = 0  # 0 = auto
    DIARIZATION_MAX_SPEAKERS: int = 0  # 0 = auto/dynamic from visible people
    DIARIZATION_MAPPING_CONFIDENCE_THRESHOLD: float = 0.5

    # === Centering / Panning Tuning ===
    CENTERING_TRANSITION_SEC: float = 0.4       # Smooth transition duration when switching speakers
    CENTERING_FACE_MARGIN_RATIO: float = 0.6    # Extra margin around face bbox (0.6 = 60% of face width)
    MAPPING_MARGIN_THRESHOLD: float = 0.3       # Min margin between top1 and top2 for reliable mapping
    CENTERING_MAX_FACES: int = 12               # Detector capacity only; actual people count is auto-detected

    # === Hook Rendering ===
    HOOK_DEFAULT_STYLE: str = "zoom_punch"  # animation preset name

    # === Subtitle Style Override (from assets/subtitle/*.json) ===
    SUBTITLE_STYLE_ID: str = ""  # empty = use DB preset, set to JSON style id to override

    # === CDN / MinIO Storage ===
    CDN_ENABLED: bool = False
    CDN_ENDPOINT: str = ""
    CDN_BUCKET: str = ""
    CDN_ACCESS_KEY: str = ""
    CDN_SECRET_KEY: str = ""

    # ─── Asset Fetcher ────────────────────────────────────────────────────
    PEXELS_API_KEY: str = ""
    PIXABAY_API_KEY: str = ""
    GIPHY_API_KEY: str = ""
    ASSET_FETCH_ENABLED: bool = True
    ASSET_FETCH_TIMEOUT: int = 8          # seconds per API request
    ASSET_FETCH_MAX_CONCURRENT: int = 4
    ASSET_FETCH_MAX_VIDEO_SIZE_MB: int = 20
    ASSET_CACHE_DIR: str = "data/asset_cache"
    ASSET_CACHE_MAX_GB: float = 2.0
    LOTTIE_LIBRARY_DIR: str = "assets/lottie_library"

    # ─── Hook Engine ─────────────────────────────────────────────────────
    HOOK_ENABLE_JALUR_A: bool = False

    # ─── Timeout Settings (seconds) ─────────────────────────────────────
    GEMINI_TIMEOUT: int = 30  # Fast fail — skip to Groq fallback quickly
    GROQ_LLM_TIMEOUT: int = 120  # Full transcript analysis needs more time

    # ─── Remotion Render Engine ──────────────────────────────────────────
    USE_REMOTION: bool = True
    REMOTION_PROJECT_PATH: str = "../remotion-renderer"
    REMOTION_SERVER_URL: str = "http://localhost:3002"
    REMOTION_SERVER_PORT: int = 3002
    REMOTION_CONCURRENCY: int = 2
    REMOTION_QUALITY: str = "medium"  # low, medium, high
    REMOTION_ENABLE_THREEJS: bool = True
    REMOTION_ENABLE_AI_LAYER: bool = True
    REMOTION_SUBTITLE_OFFSET: float = -0.5  # seconds — negative = subtitle earlier

    # ─── Groq API (V2 Pipeline) ──────────────────────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_WHISPER_MODEL: str = "whisper-large-v3-turbo"
    GROQ_LLM_MODEL: str = "llama-3.1-8b-instant"
    GROQ_LLM_FALLBACK_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_MAX_RETRIES: int = 3
    GROQ_TIMEOUT: int = 60

    # ─── V2 Pipeline Settings ────────────────────────────────────────────
    V2_PIPELINE_ENABLED: bool = True
    V2_CHUNK_MAX_SECONDS: int = 600
    V2_CHUNK_MAX_CHARS: int = 4000
    V2_MAX_AUDIO_CHUNK_MB: int = 25  # Groq Whisper file size limit

    # ─── Word-Level Transcription (on trimmed clips) ─────────────────────
    WORD_LEVEL_GROQ_MODEL: str = "whisper-large-v3-turbo"
    WORD_LEVEL_MAX_CONCURRENT: int = 3        # Max parallel Groq Whisper calls
    WORD_LEVEL_MIN_DELAY: float = 1.5         # Seconds between Groq calls (rate limit)
    WORD_LEVEL_FALLBACK_LOCAL: bool = True     # Fallback to Faster-Whisper if Groq fails
    HARD_FAIL_NO_TRANSCRIPT: bool = True       # Fail job if YouTube has no transcript

    # ─── Deprecated (kept for backward compat, not used by pipeline) ─────
    V2_AUDIO_PADDING_SECONDS: float = 3.0     # Was used by MicroSlicer
    V2_VAD_SEARCH_RADIUS: float = 2.0         # Was used by Silero VAD
    V2_VAD_MIN_SILENCE_MS: int = 300           # Was used by Silero VAD

    # ─── Ollama (Local LLM) ──────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://100.64.5.96:11434"
    OLLAMA_MODEL: str = "mistral-nemo:12b"

    # ─── Gemini Multi-Key Support ─────────────────────────────────────────

    @property
    def gemini_api_keys(self) -> list[str]:
        """Parse comma-separated Gemini API keys. Returns list of valid keys."""
        if not self.GEMINI_API_KEY:
            return []
        keys = [k.strip() for k in self.GEMINI_API_KEY.split(",") if k.strip()]
        return keys

    @property
    def use_nine_router(self) -> bool:
        return self.LLM_PROVIDER.lower() in {"nine_router", "ninerouter", "9router"}

    @property
    def nine_router_model(self) -> str:
        return self.NINE_ROUTER_MODEL or "ngentot"

    @property
    def is_local(self) -> bool:
        return self.PIPELINE_ENV == "local"

    @property
    def db_path(self) -> str:
        """Extract SQLite file path from DATABASE_URL."""
        url = self.DATABASE_URL
        # Handle both sqlite+aiosqlite:///path and sqlite:///path
        for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
            if url.startswith(prefix):
                return url[len(prefix):]
        # Fallback
        return "data/autoclip.db"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
