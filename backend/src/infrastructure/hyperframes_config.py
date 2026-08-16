"""Ensure hyperframes_configs side-table (style flags only; not freestyle HTML)."""
from __future__ import annotations

from src.infrastructure.db_connection import get_dict_connection

HYPERFRAMES_COLUMNS = (
    "enabled",
    "mode",
    "default_template",
    "position",
    "server_url",
    "timeout_sec",
)

HYPERFRAMES_DEFAULTS = {
    "enabled": 1,  # 1 = ON, 0 = OFF
    "mode": "auto",  # "auto" (AI picks/rotates style) or "manual" (specific style)
    "default_template": "hook_cyber_hud",
    "position": "safe_upper",  # "safe_upper", "top", "floating_badge"
    "server_url": "http://127.0.0.1:3003",
    "timeout_sec": 180,
}


def ensure_hyperframes_table() -> None:
    conn = get_dict_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hyperframes_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                mode TEXT NOT NULL DEFAULT 'auto',
                default_template TEXT NOT NULL DEFAULT 'hook_cyber_hud',
                position TEXT NOT NULL DEFAULT 'safe_upper',
                server_url TEXT NOT NULL DEFAULT 'http://127.0.0.1:3003',
                timeout_sec INTEGER NOT NULL DEFAULT 180,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        # Migrate missing columns if table already exists from older version
        cur = conn.execute("PRAGMA table_info(hyperframes_configs)")
        cols = {row["name"] for row in cur.fetchall()}
        if "mode" not in cols:
            conn.execute("ALTER TABLE hyperframes_configs ADD COLUMN mode TEXT NOT NULL DEFAULT 'auto'")
        if "position" not in cols:
            conn.execute("ALTER TABLE hyperframes_configs ADD COLUMN position TEXT NOT NULL DEFAULT 'safe_upper'")

        cur = conn.execute(
            "SELECT id, enabled FROM hyperframes_configs WHERE user_id IS NULL ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            col_names = ", ".join(HYPERFRAMES_COLUMNS)
            placeholders = ", ".join(["?"] * len(HYPERFRAMES_COLUMNS))
            values = [HYPERFRAMES_DEFAULTS[c] for c in HYPERFRAMES_COLUMNS]
            conn.execute(
                f"INSERT INTO hyperframes_configs (user_id, {col_names}) VALUES (NULL, {placeholders})",
                values,
            )
        conn.execute(
            """
            DELETE FROM hyperframes_configs
            WHERE user_id IS NULL
              AND id NOT IN (SELECT MAX(id) FROM hyperframes_configs WHERE user_id IS NULL)
            """
        )
        conn.commit()
    finally:
        conn.close()


def get_hyperframes_config(user_id: int | None = None) -> dict:
    ensure_hyperframes_table()
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        row = None
        if user_id is not None:
            cur.execute(
                "SELECT * FROM hyperframes_configs WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
        if not row:
            cur.execute(
                "SELECT * FROM hyperframes_configs WHERE user_id IS NULL ORDER BY id DESC LIMIT 1"
            )
            row = cur.fetchone()
        data = dict(HYPERFRAMES_DEFAULTS)
        if row:
            for k in HYPERFRAMES_COLUMNS:
                if k in row.keys() and row[k] is not None:
                    data[k] = row[k]
        data["enabled"] = bool(int(data.get("enabled") or 0))
        return data
    finally:
        conn.close()
