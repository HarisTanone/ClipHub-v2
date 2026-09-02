"""Application configuration — environment-based (local M1 vs production server)."""
import os
import shutil
from typing import Any, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    ALLOW_DIRECT_PROVIDER_FALLBACKS: bool = True
    # Legacy value retained for existing deployments. When 9router is
    # configured, Whisper calls are router-first with an automatic local fallback.
    TRANSCRIPTION_PROVIDER: str = "local"

    # Database (SQLite)
    DATABASE_URL: str = "sqlite+aiosqlite:///data/autoclip.db"

    # 9router / OpenAI-compatible chat completions API
    NINE_ROUTER_BASE_URL: str = ""
    NINE_ROUTER_API_KEY: str = ""
    NINE_ROUTER_MODEL: str = "CliperHub"
    NINE_ROUTER_PASS1_MODEL: str = "CliperHub"
    NINE_ROUTER_PASS2_MODEL: str = "CliperHub"
    NINE_ROUTER_AI_LAYER_MODEL: str = "CliperHub"
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
    GEMINI_MODEL: str = "gemini-3.6-flash"
    GEMINI_FALLBACK_MODEL: str = "gemini-3.7-flash"
    GEMINI_VIDEO_PROCESSING: str = "agentic"  # "agentic" (dynamic timeline + up to 88% token reduction) or "static" (fixed 1 FPS)

    # YouTube Data API v3 (for transcript/captions + search)
    YOUTUBE_API_KEY: str = ""
    YOUTUBE_COOKIES_PATH: str = ""

    # VidKraken Video Downloader API (Backup)
    VIDKRAKEN_API_KEY: str = "ce1bcba1-b808-470f-987c-072ca2d35488"
    VIDKRAKEN_BASE_URL: str = "https://vidkraken.com/api/v2"
    VIDKRAKEN_ENABLED: bool = True
    VIDKRAKEN_TIMEOUT: int = 180

    # Cobalt Video Downloader API (Self-Hosted / Fast REST)
    COBALT_API_URL: str = "http://localhost:9000"
    COBALT_ENABLED: bool = True
    COBALT_TIMEOUT: int = 180

    # ─── Deepgram TTS ─────────────────────────────────────────────────────
    DEEPGRAM_API_KEY: str = ""
    DEEPGRAM_TTS_VOICE: str = "aura-2-thalia-en"
    DEEPGRAM_TTS_SPEED: float = 1.0
    DEEPGRAM_TTS_TIMEOUT: int = 30

    # ─── ElevenLabs TTS ───────────────────────────────────────────────────
    ELEVENLABS_API_KEY: str = ""
    ELEVEN_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = "rUOpAdbAl56KxO00wR5D"
    ELEVENLABS_MODEL_ID: str = "eleven_multilingual_v2"
    ELEVENLABS_TTS_SPEED: float = 1.0
    ELEVENLABS_TTS_TIMEOUT: int = 45

    # ─── Video Generator TTS Provider ─────────────────────────────────────
    VIDEO_GEN_TTS_PROVIDER: str = "elevenlabs"  # "elevenlabs" | "deepgram"

    # ─── AI Video Generator ───────────────────────────────────────────────
    VIDEO_GEN_ENABLED: bool = True
    VIDEO_GEN_TARGET_DURATION: int = 65       # target seconds
    VIDEO_GEN_MIN_DURATION: int = 50
    VIDEO_GEN_MAX_DURATION: int = 90
    VIDEO_GEN_MAX_SCENES: int = 25
    VIDEO_GEN_BGM_DIR: str = "assets/bgm"    # folder with royalty-free MP3s
    VIDEO_GEN_BGM_VOLUME: float = 0.15       # background music volume (0-1)
    VIDEO_GEN_OUTPUT_DIR: str = "tmp/video_gen"

    # ─── Video Generator Subtitle Style ───────────────────────────────────
    VIDEO_GEN_SUB_FONT_SIZE: int = 54
    VIDEO_GEN_SUB_FONT_NAME: str = "DejaVu Sans"
    VIDEO_GEN_SUB_PRIMARY_COLOR: str = "&H00FFFFFF"  # ASS color: white
    VIDEO_GEN_SUB_HIGHLIGHT_COLOR: str = "&H0000CCFF"  # ASS color: yellow
    VIDEO_GEN_SUB_OUTLINE_COLOR: str = "&H00000000"  # ASS color: black
    VIDEO_GEN_SUB_BACK_COLOR: str = "&H80000000"     # ASS color: semi-transparent black bg
    VIDEO_GEN_SUB_OUTLINE: int = 3
    VIDEO_GEN_SUB_SHADOW: int = 1
    VIDEO_GEN_SUB_BG_OPACITY: float = 0.42
    VIDEO_GEN_SUB_MARGIN_V: int = 100               # vertical margin from bottom
    VIDEO_GEN_SUB_MARGIN_L: int = 40
    VIDEO_GEN_SUB_MARGIN_R: int = 40
    VIDEO_GEN_SUB_ALIGNMENT: int = 2                # 2 = bottom center (ASS alignment)
    VIDEO_GEN_SUB_BOLD: int = 1                     # 1 = bold, 0 = normal
    VIDEO_GEN_SUB_BORDER_STYLE: int = 3             # 3 = opaque box background

    # ─── Auth / JWT ───────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_REFRESH_SECRET_KEY: str = "change-me-refresh-in-production"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "HS256"

    # ─── Superadmin Seed ──────────────────────────────────────────────────
    SUPERADMIN_EMAIL: str = "admin@autocliper.com"
    SUPERADMIN_PASSWORD: str = "Admin@2024!Secure"

    # === Job Concurrency (Sequential safe execution) ===
    MAX_CONCURRENT_JOBS: int = 1
    MAX_WHISPER_PARALLEL: int = 1
    MAX_RENDER_WORKERS: int = 2

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
    USE_ARIA2C: bool = bool(shutil.which("aria2c")) or (PIPELINE_ENV != "local")

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
    YOLO_MODEL_VERSION: str = "v26"
    YOLO_MODEL_PATH: str = "models/yolo26n.pt"
    YOLO_SEG_MODEL: str = "models/yolo26n-seg.pt"
    TEXT_EMPHASIS_MAX_EVENTS: int = 2
    TEXT_EMPHASIS_SEG_CONFIDENCE: float = 0.35
    TEXT_EMPHASIS_MASK_FEATHER: int = 9

    # === Person-First Reframe Migration ===
    PERSON_DETECTOR: str = "rfdetr-large"       # rfdetr-medium | rfdetr-large | rfdetr-2xlarge
    PERSON_CONF_THRESHOLD: float = 0.35
    PERSON_TRACKER: str = "botsort"             # botsort | bytetrack
    TRACKER_MAX_LOST_FRAMES: int = 8
    FACE_DETECTOR: str = "retinaface"           # retinaface | scrfd
    FACE_REGION_HEAD_RATIO: float = 0.35
    FACE_CONFIDENCE: float = 0.55
    REFRAME_PIPELINE_MODE: str = "person_first"  # legacy | shadow | person_first


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

    # ─── ClipScout API ────────────────────────────────────────────────────
    CLIPSCOUT_API_URL: str = "https://www.clipscout.app/api/search"
    CLIPSCOUT_TIMEOUT: int = 15
    CLIPSCOUT_MAX_RETRIES: int = 2
    CLIPSCOUT_ENABLED_SOURCES: str = "pexels,pixabay,youtube_cc,youtube_protected"

    # ─── B-Roll Splice ────────────────────────────────────────────────────
    BROLL_SPLICE_ENABLED: bool = True
    BROLL_SPLICE_MAX_PER_CLIP: int = 3
    BROLL_SPLICE_CROSSFADE_SEC: float = 0.15
    BROLL_MAX_FOOTAGE_SIZE_MB: int = 50

    # ─── Top Behind Subject Overlay (portrait 9:16, additive to full-frame B-roll)
    TOP_OVERLAY_ENABLED: bool = True
    TOP_OVERLAY_SPLIT_RATIO: float = 0.65      # upper band for B-roll footage behind person
    TOP_OVERLAY_FADE_HEIGHT: float = 0.15      # smooth gradient fade height fraction
    TOP_OVERLAY_OPACITY: float = 1.0
    TOP_OVERLAY_PERSON_OUTLINE: bool = False   # clean natural silhouette cutout (no messy white border)
    TOP_OVERLAY_PERSON_SHADOW: bool = False    # no artificial dark halo on subject
    TOP_OVERLAY_OUTLINE_THICKNESS: int = 9     # px stroke @720p; organic bust glow (when enabled)
    TOP_OVERLAY_OUTLINE_COLOR: str = "255,255,255"
    # white | neon | black | gradient | comic
    TOP_OVERLAY_OUTLINE_STYLE: str = "white"
    TOP_OVERLAY_MAX_PER_CLIP: int = 3
    TOP_OVERLAY_SEG_CONFIDENCE: float = 0.25
    TOP_OVERLAY_MASK_FEATHER: int = 3          # subpixel anti-aliased matte edge feathering
    TOP_OVERLAY_MASK_STRIDE: int = 1
    TOP_OVERLAY_CROP_BIAS_Y: float = 0.08
    TOP_OVERLAY_SPEAKER_MASK_MODE: str = "dual_auto"
    TOP_OVERLAY_SMART_CROP: bool = True
    TOP_OVERLAY_SMART_CROP_CONF: float = 0.18
    # Natural 1:1 subject scale (100% full-resolution original subject, zero ghosting)
    TOP_OVERLAY_PERSON_SCALE: float = 1.0
    TOP_OVERLAY_PERSON_SHIFT_Y: float = 0.0    # 1:1 natural anchor
    TOP_OVERLAY_PERSON_ANCHOR: str = "natural" # natural|center|left|right
    TOP_OVERLAY_PERSON_EDGE_MARGIN: float = 0.03
    TOP_OVERLAY_BG_BLACK: float = 0.0          # clean backdrop without muddy dark wash
    TOP_OVERLAY_OUTLINE_BUST_RATIO: float = 0.48  # head→neck→shoulder
    TOP_OVERLAY_OUTLINE_EDGE_MARGIN: float = 0.05

    # ─── Object image+text overlay (noun mention → stock photo card) ─────

    OBJECT_OVERLAY_ENABLED: bool = True
    OBJECT_OVERLAY_MAX_PER_CLIP: int = 6
    OBJECT_OVERLAY_BOX_SIZE: float = 0.28       # fraction of min(frame w,h)
    OBJECT_OVERLAY_CORNER_RADIUS: int = 18
    OBJECT_OVERLAY_POSITION: str = "top_right"  # top_right|top_left|bottom_right|bottom_left|center_right|center_left
    OBJECT_OVERLAY_ANIMATION: str = "slide_right"  # slide_right|slide_left|slide_down|slide_up|fade|pop
    OBJECT_OVERLAY_DURATION: float = 2.4
    OBJECT_OVERLAY_MARGIN: float = 0.04
    OBJECT_OVERLAY_TEXT_COLOR: str = "255,255,255"
    OBJECT_OVERLAY_BG_COLOR: str = "20,20,24"
    OBJECT_OVERLAY_BORDER_COLOR: str = "255,255,255"
    OBJECT_OVERLAY_FONT_SCALE: float = 0.55
    OBJECT_OVERLAY_OPACITY: float = 0.95
    OBJECT_OVERLAY_MIN_RELEVANCE: float = 0.35
    OBJECT_OVERLAY_SHOW_LABEL: bool = True

    # ─── Timeout Settings (seconds) ─────────────────────────────────────
    GEMINI_TIMEOUT: int = 30  # Fast fail — skip to Groq fallback quickly
    GROQ_LLM_TIMEOUT: int = 120  # Full transcript analysis needs more time

    # ─── Remotion Render Engine (hook + subtitle — primary) ──────────────
    USE_REMOTION: bool = True
    REMOTION_PROJECT_PATH: str = "../remotion-renderer"
    REMOTION_SERVER_URL: str = "http://localhost:3002"
    REMOTION_SERVER_PORT: int = 3002
    REMOTION_CONCURRENCY: int = 2
    REMOTION_QUALITY: str = "medium"  # low, medium, high
    REMOTION_ENABLE_THREEJS: bool = True
    REMOTION_ENABLE_AI_LAYER: bool = True
    REMOTION_SUBTITLE_OFFSET: float = -0.5  # seconds — negative = subtitle earlier

    # ─── HyperFrames polish layer (AI lower-third; does NOT replace Remotion) ─
    HYPERFRAMES_ENABLED: bool = False
    HYPERFRAMES_SERVER_URL: str = "http://127.0.0.1:3003"
    HYPERFRAMES_SERVER_PORT: int = 3003
    HYPERFRAMES_PROJECT_PATH: str = "../hyperframes-renderer"
    HYPERFRAMES_TIMEOUT: int = 600
    HYPERFRAMES_DEFAULT_TEMPLATE: str = "lower_third_v1"

    # ─── Hermes agent (creative/template author; not per-clip batch) ───
    HERMES_ENABLED: bool = True
    HERMES_BIN: str = "hermes"
    HERMES_HOME: str = ""  # empty → ~/.hermes

    # === MinIO (Object Storage) ===
    MINIO_ENDPOINT: str = ""
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_BUCKET: str = ""
    MINIO_SECURE: bool = False
    TELEGRAM_BOT_NOTIFY_URL: str = ""  # URL to POST upload notifications to Telegram bot
    TELEGRAM_BOT_TOKEN: str = ""  # Bot token for direct Telegram API (alternative to notify URL)
    TELEGRAM_CHAT_ID: str = ""  # Chat/group ID to send notifications to

    # ─── Public Domain / Tunnel (Social Auto-Post & Repliz Media CDN) ───
    AUTOCLIPER_PUBLIC_URL: str = ""
    PUBLIC_BACKEND_URL: str = ""

    # ─── Repliz Social Media Management ─────────────────────────────────
    REPLIZ_ACCESS_KEY: str = ""
    REPLIZ_SECRET_KEY: str = ""
    REPLIZ_BASE_URL: str = "https://api.repliz.com"

    # ─── Google Drive (social upload) ────────────────────────────────────
    GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE: str = ""  # Path to service account JSON key (optional)
    GOOGLE_DRIVE_FOLDER_ID: str = ""  # Shared folder ID for uploads
    GOOGLE_DRIVE_DELEGATE_EMAIL: str = ""  # Email to impersonate (Workspace only)
    # OAuth2 flow (for Gmail personal accounts)
    GOOGLE_DRIVE_CLIENT_ID: str = ""
    GOOGLE_DRIVE_CLIENT_SECRET: str = ""
    GOOGLE_DRIVE_REFRESH_TOKEN: str = ""  # Obtained via one-time OAuth consent

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
    OLLAMA_BASE_URL: str = "http://localhost:11434"
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
        try:
            from src.infrastructure.model_settings_store import get_model_setting
            val = get_model_setting("NINE_ROUTER_MODEL")
            if val:
                return val
        except Exception:
            pass
        return self.NINE_ROUTER_MODEL or "CliperHub"

    def __getattribute__(self, name: str):
        if not name.startswith("_") and name.isupper():
            try:
                from src.infrastructure.system_config_store import get_system_setting, SYSTEM_SETTINGS_METADATA
                if name in SYSTEM_SETTINGS_METADATA:
                    val = get_system_setting(name)
                    if val is not None:
                        return val
            except Exception:
                pass
        return super().__getattribute__(name)

    def __setattr__(self, name: str, value: Any):
        super().__setattr__(name, value)
        if not name.startswith("_") and name.isupper():
            try:
                from src.infrastructure.system_config_store import _SETTINGS_CACHE
                _SETTINGS_CACHE[name] = value
            except Exception:
                pass

    def __delattr__(self, name: str):
        super().__delattr__(name)
        if not name.startswith("_") and name.isupper():
            try:
                from src.infrastructure.system_config_store import _SETTINGS_CACHE
                _SETTINGS_CACHE.pop(name, None)
            except Exception:
                pass

    def get_nine_router(self, key: str):
        """Get a 9router setting from DB first, fallback to .env."""
        try:
            from src.infrastructure.system_config_store import get_system_setting
            val = get_system_setting(key)
            if val is not None and val != "":
                return val
        except Exception:
            pass
        return getattr(self, key, "")

    @property
    def is_local(self) -> bool:
        return self.PIPELINE_ENV == "local"

    @property
    def db_path(self) -> str:
        """Extract SQLite file path from DATABASE_URL with robust path resolution."""
        url = self.DATABASE_URL
        raw_path = "data/autoclip.db"
        for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
            if url.startswith(prefix):
                raw_path = url[len(prefix):]
                break

        if os.path.isabs(raw_path):
            return raw_path

        # If running from project root, check backend/data/...
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        backend_candidate = os.path.join(backend_dir, raw_path)
        if os.path.exists(backend_candidate):
            return backend_candidate

        if os.path.exists(raw_path):
            return os.path.abspath(raw_path)

        return backend_candidate

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
