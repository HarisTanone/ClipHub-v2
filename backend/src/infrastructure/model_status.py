"""ModelStatusTracker — Track LLM/API model availability and rate limit state.

Provides real-time status of all models used in the pipeline:
- Gemini (4 keys)
- Groq Whisper
- Groq LLM
- Ollama

Tracks: availability, last error, cooldown timer, usage count.
Exposed via /api/models/status endpoint.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelState:
    """State of a single model/API."""
    name: str
    provider: str  # "gemini", "groq", "ollama"
    purpose: str  # "transcription", "analysis", "analysis_fallback"
    status: str = "available"  # available, rate_limited, error, exhausted
    last_error: str = ""
    cooldown_until: float = 0  # unix timestamp when cooldown expires
    requests_today: int = 0
    requests_limit: int = 0  # 0 = unlimited
    tokens_used: int = 0
    tokens_limit: int = 0  # 0 = unlimited
    last_success: float = 0
    last_failure: float = 0


class ModelStatusTracker:
    """Singleton tracker for all model states."""

    _instance: Optional["ModelStatusTracker"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._models: dict[str, ModelState] = {}
        self._init_models()

    def _init_models(self):
        """Initialize all tracked models."""
        self._models = {
            "gemini": ModelState(
                name="Gemini 3.5 Flash",
                provider="gemini",
                purpose="analysis",
                requests_limit=20,  # per day free tier
                tokens_limit=1000000,
            ),
            "groq_whisper": ModelState(
                name="Groq Whisper Large V3 Turbo",
                provider="groq",
                purpose="transcription",
                requests_limit=2000,  # per day
                tokens_limit=0,  # no token limit for audio
            ),
            "groq_llm": ModelState(
                name="Groq LLama 3.3 70B",
                provider="groq",
                purpose="analysis_fallback",
                requests_limit=30,  # per minute
                tokens_limit=12000,  # TPM
            ),
            "ollama": ModelState(
                name="Ollama Mistral Nemo 12B",
                provider="ollama",
                purpose="analysis_fallback",
                requests_limit=0,  # unlimited (local)
                tokens_limit=0,
            ),
        }

    def mark_success(self, model_key: str, tokens_used: int = 0):
        """Mark model as successfully used."""
        if model_key not in self._models:
            return
        m = self._models[model_key]
        m.status = "available"
        m.last_success = time.time()
        m.requests_today += 1
        m.tokens_used += tokens_used
        m.last_error = ""

    def mark_rate_limited(self, model_key: str, retry_after: float = 60, error_msg: str = ""):
        """Mark model as rate limited with cooldown."""
        if model_key not in self._models:
            return
        m = self._models[model_key]
        m.status = "rate_limited"
        m.cooldown_until = time.time() + retry_after
        m.last_failure = time.time()
        m.last_error = error_msg[:200]
        logger.info(f"model_status: {model_key} rate limited for {retry_after:.0f}s")

    def mark_exhausted(self, model_key: str, error_msg: str = ""):
        """Mark model as exhausted (daily quota hit)."""
        if model_key not in self._models:
            return
        m = self._models[model_key]
        m.status = "exhausted"
        m.last_failure = time.time()
        m.last_error = error_msg[:200]
        # Cooldown until end of current hour (quota usually resets hourly/daily)
        m.cooldown_until = time.time() + 3600
        logger.info(f"model_status: {model_key} exhausted")

    def mark_error(self, model_key: str, error_msg: str = ""):
        """Mark model as having an error."""
        if model_key not in self._models:
            return
        m = self._models[model_key]
        m.status = "error"
        m.last_failure = time.time()
        m.last_error = error_msg[:200]
        m.cooldown_until = time.time() + 30  # short cooldown on error

    def is_available(self, model_key: str) -> bool:
        """Check if model is currently available (not in cooldown)."""
        if model_key not in self._models:
            return True
        m = self._models[model_key]
        # Auto-recover from cooldown
        if m.cooldown_until > 0 and time.time() >= m.cooldown_until:
            m.status = "available"
            m.cooldown_until = 0
        return m.status == "available"

    def get_all_status(self) -> list[dict]:
        """Get status of all models for API response."""
        now = time.time()
        result = []
        for key, m in self._models.items():
            # Auto-recover expired cooldowns
            if m.cooldown_until > 0 and now >= m.cooldown_until:
                m.status = "available"
                m.cooldown_until = 0

            cooldown_remaining = max(0, m.cooldown_until - now) if m.cooldown_until > 0 else 0

            result.append({
                "key": key,
                "name": m.name,
                "provider": m.provider,
                "purpose": m.purpose,
                "status": m.status,
                "last_error": m.last_error,
                "cooldown_remaining": round(cooldown_remaining),
                "requests_today": m.requests_today,
                "requests_limit": m.requests_limit,
                "tokens_used": m.tokens_used,
                "tokens_limit": m.tokens_limit,
                "last_success": round(m.last_success) if m.last_success else None,
                "last_failure": round(m.last_failure) if m.last_failure else None,
            })
        return result

    def reset_daily(self):
        """Reset daily counters (call at midnight)."""
        for m in self._models.values():
            m.requests_today = 0
            m.tokens_used = 0
            if m.status == "exhausted":
                m.status = "available"
                m.cooldown_until = 0
