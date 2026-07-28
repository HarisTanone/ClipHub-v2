"""
Migration v5.0 — Object image overlay configs (AI visual entities → photo card).

Style knobs only (position/size/anim/colors). Entity words come from AI per-clip,
not from this table.

Idempotent: safe to re-run. Seeds one global row (user_id NULL).

Usage:
    python -m database.migrations.v5_object_overlay
"""

from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings

COLUMNS = [
    "enabled",
    "max_per_clip",
    "box_size_ratio",
    "corner_radius",
    "position",
    "animation",
    "duration_sec",
    "margin_ratio",
    "text_color",
    "bg_color",
    "border_color",
    "font_scale",
    "opacity",
    "min_relevance",
    "show_label",
]

DEFAULTS = {
    "enabled": 1,
    "max_per_clip": 3,
    "box_size_ratio": 0.28,
    "corner_radius": 18,
    "position": "top_right",
    "animation": "slide_right",
    "duration_sec": 2.4,
    "margin_ratio": 0.04,
    "text_color": "255,255,255",
    "bg_color": "20,20,24",
    "border_color": "255,255,255",
    "font_scale": 0.55,
    "opacity": 0.95,
    "min_relevance": 0.35,
    "show_label": 1,
}


def migrate() -> None:
    db_path = settings.db_path
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='object_overlay_configs'"
    )
    exists = cur.fetchone() is not None

    if not exists:
        print("  [MIGRATE] Creating object_overlay_configs table...")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS object_overlay_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                max_per_clip INTEGER NOT NULL DEFAULT 3,
                box_size_ratio REAL NOT NULL DEFAULT 0.28,
                corner_radius INTEGER NOT NULL DEFAULT 18,
                position TEXT NOT NULL DEFAULT 'top_right',
                animation TEXT NOT NULL DEFAULT 'slide_right',
                duration_sec REAL NOT NULL DEFAULT 2.4,
                margin_ratio REAL NOT NULL DEFAULT 0.04,
                text_color TEXT NOT NULL DEFAULT '255,255,255',
                bg_color TEXT NOT NULL DEFAULT '20,20,24',
                border_color TEXT NOT NULL DEFAULT '255,255,255',
                font_scale REAL NOT NULL DEFAULT 0.55,
                opacity REAL NOT NULL DEFAULT 0.95,
                min_relevance REAL NOT NULL DEFAULT 0.35,
                show_label INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
        print("  [DONE] object_overlay_configs table created")
    else:
        print("  [OK] object_overlay_configs already exists")

    # Ensure global row with full defaults (SQLite NULL has no UNIQUE)
    cur.execute(
        "SELECT id FROM object_overlay_configs WHERE user_id IS NULL "
        "ORDER BY id DESC LIMIT 1"
    )
    if not cur.fetchone():
        cols = ", ".join(COLUMNS)
        placeholders = ", ".join(["?"] * len(COLUMNS))
        values = [DEFAULTS[c] for c in COLUMNS]
        cur.execute(
            f"INSERT INTO object_overlay_configs (user_id, {cols}) "
            f"VALUES (NULL, {placeholders})",
            values,
        )
        conn.commit()
        print("  [SEED] global object_overlay row inserted")

    # Drop duplicate global rows
    cur.execute(
        """
        DELETE FROM object_overlay_configs
        WHERE user_id IS NULL
          AND id NOT IN (
              SELECT MAX(id) FROM object_overlay_configs WHERE user_id IS NULL
          )
        """
    )
    if cur.rowcount:
        print(f"  [CLEANUP] removed {cur.rowcount} duplicate global row(s)")
        conn.commit()

    conn.close()
    print("  [DONE] object_overlay_configs migration complete")


if __name__ == "__main__":
    migrate()
    print("\nMigration v5 completed.")
