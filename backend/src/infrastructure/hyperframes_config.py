"""Ensure hyperframes_configs side-table (style flags only; not freestyle HTML)."""
from __future__ import annotations

from src.infrastructure.db_connection import get_dict_connection

HYPERFRAMES_COLUMNS = (
    "enabled",
    "default_template",
    "server_url",
    "timeout_sec",
)

HYPERFRAMES_DEFAULTS = {
    "enabled": 0,  # off by default — Remotion owns hook/subtitle
    "default_template": "lower_third_v1",
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
                enabled INTEGER NOT NULL DEFAULT 0,
                default_template TEXT NOT NULL DEFAULT 'lower_third_v1',
                server_url TEXT NOT NULL DEFAULT 'http://127.0.0.1:3003',
                timeout_sec INTEGER NOT NULL DEFAULT 180,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        cur = conn.execute(
            "SELECT id FROM hyperframes_configs WHERE user_id IS NULL ORDER BY id DESC LIMIT 1"
        )
        if not cur.fetchone():
            cols = ", ".join(HYPERFRAMES_COLUMNS)
            placeholders = ", ".join(["?"] * len(HYPERFRAMES_COLUMNS))
            values = [HYPERFRAMES_DEFAULTS[c] for c in HYPERFRAMES_COLUMNS]
            conn.execute(
                f"INSERT INTO hyperframes_configs (user_id, {cols}) VALUES (NULL, {placeholders})",
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
