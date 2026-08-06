"""
Migration v5.1 — Model settings table (superadmin-managed, replaces .env for 9router models).

Stores 9router model config in DB so superadmin can change models from frontend
without editing .env or restarting server.

Idempotent: safe to re-run. Seeds default values from .env if rows don't exist.

Usage:
    python -m database.migrations.v5_1_model_settings
"""

from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings

DEFAULT_SETTINGS = [
    ("NINE_ROUTER_BASE_URL", "http://127.0.0.1:20128/v1", "9router API base URL"),
    ("NINE_ROUTER_API_KEY", "", "9router API key (kosong jika local tanpa auth)"),
    ("NINE_ROUTER_MODEL", "CliperHub", "Default model untuk general LLM calls"),
    ("NINE_ROUTER_PASS1_MODEL", "CliperHub", "Model untuk transcript analysis pass 1"),
    ("NINE_ROUTER_PASS2_MODEL", "CliperHub", "Model untuk highlight analysis pass 2"),
    ("NINE_ROUTER_AI_LAYER_MODEL", "CliperHub", "Model untuk AI text layer generation"),
    ("NINE_ROUTER_TIMEOUT", "120", "Timeout per request (detik)"),
    ("NINE_ROUTER_MAX_RETRIES", "3", "Max retry per request"),
    ("NINE_ROUTER_TEMPERATURE", "0.3", "Default temperature"),
    ("NINE_ROUTER_WHISPER_ENABLED", "true", "Enable whisper via 9router"),
    ("NINE_ROUTER_WHISPER_MODEL", "groq/whisper-large-v3-turbo", "Whisper model name"),
    ("NINE_ROUTER_WHISPER_TIMEOUT", "120", "Whisper request timeout"),
    ("NINE_ROUTER_WHISPER_MAX_RETRIES", "1", "Whisper max retries"),
]


def migrate():
    db_path = settings.db_path
    print(f"  [v5.1] model_settings → {db_path}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Create table
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

    # Seed defaults — use .env values if available, otherwise hardcoded defaults
    for key, default_value, description in DEFAULT_SETTINGS:
        # Try to get current .env value
        env_value = getattr(settings, key, None)
        value = str(env_value) if env_value is not None and env_value != "" else default_value
        # Boolean fix
        if isinstance(env_value, bool):
            value = "true" if env_value else "false"

        conn.execute(
            """INSERT OR IGNORE INTO model_settings (key, value, description)
               VALUES (?, ?, ?)""",
            (key, value, description),
        )

    conn.commit()

    # Report
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM model_settings")
    count = cur.fetchone()[0]
    print(f"  [v5.1] ✅ model_settings table ready ({count} keys)")
    conn.close()


if __name__ == "__main__":
    migrate()
