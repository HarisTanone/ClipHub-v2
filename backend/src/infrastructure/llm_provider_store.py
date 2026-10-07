"""DB-backed LLM provider registry (DEPRECATED — 9router-only mode).

⚠ This table is NOT used for chat completion routing. Since the 9router-only
migration, ALL AI text/JSON/transcription calls go through 9router, whose
endpoint, key, and model/combination are configured from the admin panel
(system settings: NINE_ROUTER_BASE_URL, NINE_ROUTER_API_KEY, NINE_ROUTER_MODEL,
NINE_ROUTER_PASS1_MODEL, NINE_ROUTER_PASS2_MODEL, NINE_ROUTER_AI_LAYER_MODEL).

The `llm_providers` table is retained as an audit log of legacy rows and for
migration tooling. `llm_router.get_llm_chain()` ALWAYS returns
[{"kind": "nine_router"}] regardless of what rows live in this table.

Do NOT use this store for chat completions. Direct Gemini/Groq keys live in
system settings (GEMINI_API_KEY / GROQ_API_KEY) and are only reachable via
ALLOW_DIRECT_PROVIDER_FALLBACKS=true, which is off by default.
"""
import logging
from typing import Any, Optional

from src.infrastructure.db_connection import get_dict_connection

logger = logging.getLogger(__name__)

VALID_PROVIDER_TYPES = frozenset({"openai_compatible"})

_table_ensured = False

# In-memory cache of enabled providers for the router (invalidated on write).
_chain_cache: Optional[list[dict[str, Any]]] = None


def _ensure_table():
    """Create llm_providers table if it doesn't exist (runs once per process)."""
    global _table_ensured
    if _table_ensured:
        return
    conn = get_dict_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL DEFAULT 'openai_compatible',
                base_url TEXT NOT NULL DEFAULT '',
                api_key TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 0,
                priority INTEGER NOT NULL DEFAULT 100,
                last_status TEXT NOT NULL DEFAULT '',
                last_checked_at TEXT DEFAULT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_by INTEGER DEFAULT NULL,
                FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_llm_providers_priority "
            "ON llm_providers(enabled, priority)"
        )
        conn.commit()
    finally:
        conn.close()
    _table_ensured = True


def invalidate_chain_cache() -> None:
    """Drop the router's in-memory chain cache (call after any write)."""
    global _chain_cache
    _chain_cache = None


def mask_key(key: str) -> str:
    """Mask an API key for display: sk-abc...wxyz"""
    if not key:
        return ""
    if len(key) < 10:
        return "******"
    return f"{key[:6]}...{key[-4:]}"


def list_providers(include_disabled: bool = True) -> list[dict[str, Any]]:
    """List all providers. api_key is masked (never returns the raw key)."""
    _ensure_table()
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        sql = (
            "SELECT id, name, type, base_url, api_key, model, enabled, priority, "
            "last_status, last_checked_at, created_at, updated_at, updated_by "
            "FROM llm_providers"
        )
        if not include_disabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY priority, id"
        cur.execute(sql)
        rows = cur.fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "type": row["type"],
                "base_url": row["base_url"],
                "api_key": mask_key(row["api_key"]),
                "has_api_key": bool(row["api_key"]),
                "model": row["model"],
                "enabled": bool(row["enabled"]),
                "priority": row["priority"],
                "last_status": row["last_status"],
                "last_checked_at": row["last_checked_at"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "updated_by": row["updated_by"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def get_provider(provider_id: int) -> Optional[dict[str, Any]]:
    """Get one provider with the RAW api_key (internal use only)."""
    _ensure_table()
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM llm_providers WHERE id = ?", (provider_id,))
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def get_enabled_providers() -> list[dict[str, Any]]:
    """Enabled providers, priority order, raw api_key (router internal use)."""
    _ensure_table()
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, type, base_url, api_key, model, priority "
            "FROM llm_providers WHERE enabled = 1 ORDER BY priority, id"
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def add_provider(
    name: str,
    base_url: str,
    api_key: str,
    model: str = "",
    provider_type: str = "openai_compatible",
    enabled: bool = False,
    priority: int = 100,
    user_id: Optional[int] = None,
) -> Optional[int]:
    """Insert a provider. Returns new id, or None on conflict/error."""
    _ensure_table()
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO llm_providers
               (name, type, base_url, api_key, model, enabled, priority,
                created_at, updated_at, updated_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?)""",
            (
                name.strip(),
                provider_type,
                base_url.strip().rstrip("/"),
                api_key.strip(),
                model.strip(),
                1 if enabled else 0,
                priority,
                user_id,
            ),
        )
        conn.commit()
        invalidate_chain_cache()
        return int(cur.lastrowid) if cur.lastrowid is not None else None
    except Exception as e:
        logger.error(f"[llm_providers] add failed: {e}")
        return None
    finally:
        conn.close()


def update_provider(
    provider_id: int,
    *,
    name: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    enabled: Optional[bool] = None,
    priority: Optional[int] = None,
    user_id: Optional[int] = None,
) -> bool:
    """Update fields on a provider. api_key=None keeps the existing key
    (so the UI can submit the masked value unchanged)."""
    _ensure_table()
    sets: list[str] = ["updated_at = datetime('now')", "updated_by = ?"]
    params: list[Any] = [user_id]
    if name is not None:
        sets.append("name = ?")
        params.append(name.strip())
    if base_url is not None:
        sets.append("base_url = ?")
        params.append(base_url.strip().rstrip("/"))
    if api_key is not None:
        sets.append("api_key = ?")
        params.append(api_key.strip())
    if model is not None:
        sets.append("model = ?")
        params.append(model.strip())
    if enabled is not None:
        sets.append("enabled = ?")
        params.append(1 if enabled else 0)
    if priority is not None:
        sets.append("priority = ?")
        params.append(priority)
    params.append(provider_id)

    conn = get_dict_connection()
    try:
        conn.execute(
            f"UPDATE llm_providers SET {', '.join(sets)} WHERE id = ?", params
        )
        conn.commit()
        invalidate_chain_cache()
        return True
    except Exception as e:
        logger.error(f"[llm_providers] update failed: {e}")
        return False
    finally:
        conn.close()


def delete_provider(provider_id: int) -> bool:
    """Delete a provider row."""
    _ensure_table()
    conn = get_dict_connection()
    try:
        conn.execute("DELETE FROM llm_providers WHERE id = ?", (provider_id,))
        conn.commit()
        invalidate_chain_cache()
        return True
    except Exception as e:
        logger.error(f"[llm_providers] delete failed: {e}")
        return False
    finally:
        conn.close()


def set_provider_status(provider_id: int, status: str) -> None:
    """Record the last validation status (e.g. 'ok: 12 models', 'error: 401')."""
    _ensure_table()
    conn = get_dict_connection()
    try:
        conn.execute(
            "UPDATE llm_providers SET last_status = ?, "
            "last_checked_at = datetime('now') WHERE id = ?",
            (status[:500], provider_id),
        )
        conn.commit()
    except Exception as e:
        logger.warning(f"[llm_providers] status update failed: {e}")
    finally:
        conn.close()
