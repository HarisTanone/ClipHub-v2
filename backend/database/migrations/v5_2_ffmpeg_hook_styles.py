"""
Migration v5.2 — FFmpeg hook styles table (DB-driven, replaces hardcoded HOOK_STYLES).

Stores FFmpeg drawtext hook animation styles in DB so they can be managed
from the admin panel and extended without code changes.

Idempotent: safe to re-run.

Usage:
    python -m database.migrations.v5_2_ffmpeg_hook_styles
"""

from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings

DEFAULT_STYLES = [
    ("zoom_punch", "Zoom Punch", "Bold white text, quick scale-in", 56, "white", 4, "black", 3.0, '["Anton-Regular.ttf","BebasNeue-Regular.ttf","Poppins-Bold.ttf"]', 0.6, "h*0.4-text_h/2", ""),
    ("fade_scale", "Fade Scale", "Smooth fade + slight grow", 48, "white", 3, "black@0.8", 3.5, '["Inter-Bold.ttf","Poppins-Bold.ttf","Montserrat-Bold.ttf"]', 0.5, "h*0.42-text_h/2", ""),
    ("slide_punch_framer", "Slide Punch", "Slide from left with punch", 52, "white", 5, "black", 3.0, '["Poppins-Bold.ttf","Montserrat-Bold.ttf","Inter-Bold.ttf"]', 0.65, "h*0.38-text_h/2", ""),
    ("typewriter", "Typewriter", "Character-by-character reveal", 44, "#00FF88", 2, "black", 3.5, '["Inter-Bold.ttf","Poppins-Bold.ttf"]', 0.7, "h*0.45-text_h/2", ""),
    ("glitch_rgb", "Glitch RGB", "RGB split/chromatic aberration", 58, "white", 0, "black", 3.0, '["Anton-Regular.ttf","BlackOpsOne-Regular.ttf","BebasNeue-Regular.ttf"]', 0.7, "h*0.4-text_h/2", "glitch_rgb"),
    ("shake_neon", "Shake Neon", "Neon glow with random shake", 54, "#00FFCC", 0, "black", 3.0, '["Bungee-Regular.ttf","Anton-Regular.ttf","BlackOpsOne-Regular.ttf"]', 0.65, "h*0.4-text_h/2", "shake_neon"),
    ("cinematic_reveal", "Cinematic Reveal", "Cinematic letterbox + elegant fade-in", 62, "#FFD700", 0, "black", 3.5, '["PlayfairDisplay-Variable.ttf","Lora-Variable.ttf","Merriweather-Bold.ttf"]', 0.8, "h*0.42-text_h/2", "cinematic_reveal"),
    ("danger_bold", "Danger Bold", "Bold red with pulsing border", 70, "#FF2D2D", 6, "black", 3.0, '["BlackOpsOne-Regular.ttf","Anton-Regular.ttf","ArchivoBlack-Regular.ttf"]', 0.75, "h*0.38-text_h/2", "danger_bold"),
    ("minimal_white", "Minimal White", "Clean minimal white on transparent", 42, "white", 2, "black@0.5", 3.0, '["Inter-Bold.ttf","Poppins-Medium.ttf"]', 0.3, "h*0.5-text_h/2", ""),
    ("bold_yellow", "Bold Yellow", "Bold yellow with heavy stroke", 64, "#FFD700", 5, "black", 3.0, '["Anton-Regular.ttf","BebasNeue-Regular.ttf"]', 0.6, "h*0.4-text_h/2", ""),
    ("electric_blue", "Electric Blue", "Bright blue neon look", 54, "#00BFFF", 0, "black", 3.0, '["Bungee-Regular.ttf","Anton-Regular.ttf"]', 0.65, "h*0.4-text_h/2", "shake_neon"),
    ("fire_red", "Fire Red", "Aggressive red for dramatic moments", 66, "#FF4444", 5, "#220000", 2.5, '["BlackOpsOne-Regular.ttf","Anton-Regular.ttf"]', 0.7, "h*0.38-text_h/2", "danger_bold"),
]


def migrate():
    db_path = settings.db_path
    print(f"  [v5.2] ffmpeg_hook_styles → {db_path}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Create table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ffmpeg_hook_styles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            fontsize INTEGER NOT NULL DEFAULT 56,
            fontcolor TEXT NOT NULL DEFAULT 'white',
            borderw INTEGER NOT NULL DEFAULT 4,
            bordercolor TEXT NOT NULL DEFAULT 'black',
            duration REAL NOT NULL DEFAULT 3.0,
            font_pref TEXT NOT NULL DEFAULT '["Anton-Regular.ttf"]',
            bg_opacity REAL NOT NULL DEFAULT 0.6,
            y_expr TEXT NOT NULL DEFAULT 'h*0.4-text_h/2',
            effect TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            is_system INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Seed defaults
    for row in DEFAULT_STYLES:
        conn.execute(
            """INSERT OR IGNORE INTO ffmpeg_hook_styles
               (id, name, description, fontsize, fontcolor, borderw, bordercolor, duration, font_pref, bg_opacity, y_expr, effect)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            row,
        )

    conn.commit()

    # Report
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM ffmpeg_hook_styles")
    count = cur.fetchone()[0]
    print(f"  [v5.2] ✅ ffmpeg_hook_styles table ready ({count} styles)")
    conn.close()


if __name__ == "__main__":
    migrate()
