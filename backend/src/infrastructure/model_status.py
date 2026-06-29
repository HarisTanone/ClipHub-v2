"""ModelStatusTracker — Track LLM/API model availability and rate limit state.

Persists usage counters to SQLite (survives restart).
Provides real-time status of all models used in the pipeline.
"""
import logging
import time
from dataclasses import dataclass
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ModelState:
    """State of a single model/API."""
    name: str
    provider: str
    purpose: str
    status: str = "available"
    last_error: str = ""
    cooldown_until: float = 0
    requests_today: int = 0
    requests_limit: int = 0
    tokens_used: int = 0
    tokens_limit: int = 0
    last_success: float = 0
    last_failure: float = 0


class ModelStatusTracker:
    """Singleton tracker for all model states. Persists to SQLite."""

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
        self._ensure_db_table()
        self._load_from_db()

    def _init_models(self):
        """Initialize all tracked models."""
        self._models = {
            "gemini": ModelState(
                name="Gemini 3.5 Flash", provider="gemini", purpose="analysis",
                requests_limit=20, tokens_limit=1000000,
            ),
            "groq_whisper": ModelState(
                name="Groq Whisper Large V3 Turbo", provider="groq", purpose="transcription",
                requests_limit=2000, tokens_limit=0,
            ),
            "groq_llm": ModelState(
                name="Groq LLama 3.3 70B", provider="groq", purpose="analysis_fallback",
                requests_limit=30, tokens_limit=12000,
            ),
            "ollama": ModelState(
                name="Ollama Mistral Nemo 12B", provider="ollama", purpose="analysis_fallback",
                requests_limit=0, tokens_limit=0,
            ),
        }

    def _ensure_db_table(self):
        """Create model_usage table if not exists."""
        try:
            from src.infrastructure.db_connection import get_dict_connection
            conn = get_dict_connection()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS model_usage (
                        model_key TEXT PRIMARY KEY,
                        requests_today INTEGER DEFAULT 0,
                        tokens_used INTEGER DEFAULT 0,
                        last_success REAL DEFAULT 0,
                        last_failure REAL DEFAULT 0,
                        last_error TEXT DEFAULT '',
                        status TEXT DEFAULT 'available',
                        cooldown_until REAL DEFAULT 0,
                        updated_date TEXT DEFAULT ''
                    )
                """)
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"model_status: db init failed (non-critical): {e}")

    def _load_from_db(self):
        """Load persisted usage counters from DB."""
        try:
            from src.infrastructure.db_connection import get_dict_connection
            import datetime
            today = datetime.date.today().isoformat()
            conn = get_dict_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM model_usage")
                rows = cur.fetchall()
                for row in rows:
                    key = row["model_key"]
                    if key in self._models:
                        m = self._models[key]
                        # Reset counters if date changed (new day)
                        if row["updated_date"] == today:
                            m.requests_today = row["requests_today"]
                            m.tokens_used = row["tokens_used"]
                        m.last_success = row["last_success"]
                        m.last_failure = row["last_failure"]
                        m.last_error = row["last_error"] or ""
                        m.status = row["status"] or "available"
                        m.cooldown_until = row["cooldown_until"]
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"model_status: db load failed (non-critical): {e}")

    def _save_to_db(self, model_key: str):
        """Persist model state to DB."""
        try:
            from src.infrastructure.db_connection import get_dict_connection
            import datetime
            m = self._models[model_key]
            today = datetime.date.today().isoformat()
            conn = get_dict_connection()
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO model_usage 
                    (model_key, requests_today, tokens_used, last_success, last_failure, last_error, status, cooldown_until, updated_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (model_key, m.requests_today, m.tokens_used, m.last_success, m.last_failure, m.last_error, m.status, m.cooldown_until, today))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"model_status: db save failed (non-critical): {e}")

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
        self._save_to_db(model_key)

    def mark_rate_limited(self, model_key: str, retry_after: float = 60, error_msg: str = ""):
        """Mark model as rate limited with cooldown."""
        if model_key not in self._models:
            return
        m = self._models[model_key]
        m.status = "rate_limited"
        m.cooldown_until = time.time() + retry_after
        m.last_failure = time.time()
        m.last_error = error_msg[:200]
        self._save_to_db(model_key)

    def mark_exhausted(self, model_key: str, error_msg: str = ""):
        """Mark model as exhausted (daily quota hit)."""
        if model_key not in self._models:
            return
        m = self._models[model_key]
        m.status = "exhausted"
        m.last_failure = time.time()
        m.last_error = error_msg[:200]
        m.cooldown_until = time.time() + 3600
        self._save_to_db(model_key)

    def mark_error(self, model_key: str, error_msg: str = ""):
        """Mark model as having an error."""
        if model_key not in self._models:
            return
        m = self._models[model_key]
        m.status = "error"
        m.last_failure = time.time()
        m.last_error = error_msg[:200]
        m.cooldown_until = time.time() + 30
        self._save_to_db(model_key)

    def is_available(self, model_key: str) -> bool:
        """Check if model is currently available (not in cooldown)."""
        if model_key not in self._models:
            return True
        m = self._models[model_key]
        if m.cooldown_until > 0 and time.time() >= m.cooldown_until:
            m.status = "available"
            m.cooldown_until = 0
            self._save_to_db(model_key)
        return m.status == "available"

    def get_all_status(self) -> list[dict]:
        """Get status of all models for API response."""
        now = time.time()
        result = []
        for key, m in self._models.items():
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
