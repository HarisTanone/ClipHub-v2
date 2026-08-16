"""DB-backed model settings store.

Reads model config from `model_settings` table (superadmin-managed).
Falls back to .env / pydantic Settings defaults when no DB row exists.

Usage:
    from src.infrastructure.model_settings_store import get_model_setting, get_all_model_settings

    model = get_model_setting("NINE_ROUTER_MODEL")  # DB first, then .env
"""
import logging
import sqlite3
from typing import Any, Optional

from src.config import settings
from src.infrastructure.db_connection import get_dict_connection

logger = logging.getLogger(__name__)

# Keys that are valid model settings (whitelist)
VALID_MODEL_KEYS = frozenset([
    "NINE_ROUTER_BASE_URL",
    "NINE_ROUTER_API_KEY",
    "NINE_ROUTER_MODEL",
    "NINE_ROUTER_PASS1_MODEL",
    "NINE_ROUTER_PASS2_MODEL",
    "NINE_ROUTER_AI_LAYER_MODEL",
    "NINE_ROUTER_MODEL_PASS1",
    "NINE_ROUTER_MODEL_PASS2",
    "NINE_ROUTER_MODEL_AI_LAYER",
    "NINE_ROUTER_TIMEOUT",
    "NINE_ROUTER_MAX_RETRIES",
    "NINE_ROUTER_TEMPERATURE",
    "NINE_ROUTER_WHISPER_ENABLED",
    "NINE_ROUTER_WHISPER_MODEL",
    "NINE_ROUTER_WHISPER_TIMEOUT",
    "NINE_ROUTER_WHISPER_MAX_RETRIES",
])

# Type coercion map
_TYPE_MAP: dict[str, type] = {
    "NINE_ROUTER_TIMEOUT": int,
    "NINE_ROUTER_MAX_RETRIES": int,
    "NINE_ROUTER_TEMPERATURE": float,
    "NINE_ROUTER_WHISPER_ENABLED": bool,
    "NINE_ROUTER_WHISPER_TIMEOUT": int,
    "NINE_ROUTER_WHISPER_MAX_RETRIES": int,
}


def _coerce(key: str, value: str) -> Any:
    """Coerce string value from DB to the expected Python type."""
    target_type = _TYPE_MAP.get(key)
    if target_type is None:
        return value
    if target_type is bool:
        return value.lower() in ("true", "1", "yes")
    try:
        return target_type(value)
    except (ValueError, TypeError):
        return value


_table_ensured = False


def _ensure_table():
    """Create model_settings table if it doesn't exist (runs once per process)."""
    global _table_ensured
    if _table_ensured:
        return
    conn = get_dict_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS model_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_by INTEGER DEFAULT NULL,
                FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()
    _table_ensured = True


def get_model_setting(key: str) -> Any:
    """Get a single model setting. DB first, fallback to .env/Settings default."""
    if key not in VALID_MODEL_KEYS:
        # Return from settings directly for unknown keys
        return getattr(settings, key, None)

    try:
        _ensure_table()
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT value FROM model_settings WHERE key = ?", (key,))
            row = cur.fetchone()
            if row and row["value"] != "":
                return _coerce(key, row["value"])
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[model_settings] DB read failed for {key}: {e}")

    # Fallback to .env
    return getattr(settings, key, "")


def get_all_model_settings() -> list[dict[str, Any]]:
    """Get all model settings as list of dicts with key, value, description, updated_at."""
    _ensure_table()
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT key, value, description, updated_at, updated_by FROM model_settings ORDER BY key"
        )
        rows = cur.fetchall()
        result = []
        for row in rows:
            result.append({
                "key": row["key"],
                "value": row["value"],
                "description": row["description"],
                "updated_at": row["updated_at"],
                "updated_by": row["updated_by"],
            })
        # Add any valid keys not yet in DB (from .env)
        existing_keys = {r["key"] for r in result}
        for key in sorted(VALID_MODEL_KEYS - existing_keys):
            env_val = getattr(settings, key, "")
            result.append({
                "key": key,
                "value": str(env_val) if env_val is not None else "",
                "description": "",
                "updated_at": None,
                "updated_by": None,
            })
        return result
    finally:
        conn.close()


def set_model_setting(key: str, value: str, user_id: Optional[int] = None) -> bool:
    """Upsert a model setting. Returns True on success."""
    if key not in VALID_MODEL_KEYS:
        return False
    _ensure_table()
    conn = get_dict_connection()
    try:
        conn.execute(
            """INSERT INTO model_settings (key, value, updated_at, updated_by)
               VALUES (?, ?, datetime('now'), ?)
               ON CONFLICT(key) DO UPDATE SET
                   value = excluded.value,
                   updated_at = datetime('now'),
                   updated_by = excluded.updated_by""",
            (key, value, user_id),
        )
        conn.commit()
        logger.info(f"[model_settings] Updated {key} by user {user_id}")
        return True
    except Exception as e:
        logger.error(f"[model_settings] Failed to set {key}: {e}")
        return False
    finally:
        conn.close()


def bulk_set_model_settings(
    updates: dict[str, str], user_id: Optional[int] = None
) -> int:
    """Bulk upsert model settings. Returns count of successfully updated keys."""
    _ensure_table()
    count = 0
    conn = get_dict_connection()
    try:
        for key, value in updates.items():
            if key not in VALID_MODEL_KEYS:
                continue
            conn.execute(
                """INSERT INTO model_settings (key, value, updated_at, updated_by)
                   VALUES (?, ?, datetime('now'), ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value = excluded.value,
                       updated_at = datetime('now'),
                       updated_by = excluded.updated_by""",
                (key, value, user_id),
            )
            count += 1
        conn.commit()
        logger.info(f"[model_settings] Bulk updated {count} keys by user {user_id}")
    except Exception as e:
        logger.error(f"[model_settings] Bulk set failed: {e}")
    finally:
        conn.close()
    return count
