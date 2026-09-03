"""
Migration v6 — Video Generator jobs table.

Stores video generation job state persistently so jobs survive server restarts
and can be queried historically.

Idempotent: safe to re-run.

Usage:
    python -m database.migrations.v6_video_generator
"""

from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings


def migrate():
    db_path = settings.db_path
    print(f"  [v6] video_generator_jobs → {db_path}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Create video_generator_jobs table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS video_generator_jobs (
            job_id TEXT PRIMARY KEY,
            user_id INTEGER,
            topic TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            progress INTEGER NOT NULL DEFAULT 0,
            target_duration INTEGER NOT NULL DEFAULT 65,
            tts_provider TEXT NOT NULL DEFAULT 'gemini',
            tts_model TEXT NOT NULL DEFAULT 'gemini-3.1-flash-tts-preview',
            voice TEXT NOT NULL DEFAULT '',
            speed REAL NOT NULL DEFAULT 1.0,
            instructions TEXT NOT NULL DEFAULT '',
            num_scenes INTEGER NOT NULL DEFAULT 0,
            subtitles_enabled INTEGER NOT NULL DEFAULT 1,
            subtitle_style_json TEXT,
            hook_enabled INTEGER NOT NULL DEFAULT 1,
            custom_hook TEXT,
            hook_style_json TEXT,
            include_bgm INTEGER NOT NULL DEFAULT 1,
            bgm_volume REAL NOT NULL DEFAULT 0.15,
            source_video_url TEXT,
            agentic_understanding INTEGER NOT NULL DEFAULT 1,
            title TEXT,
            story_json TEXT,
            scenes_json TEXT,
            timeline_json TEXT,
            output_path TEXT,
            error TEXT,
            created_at REAL NOT NULL,
            completed_at REAL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Ensure optional/new columns exist if table was already created
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(video_generator_jobs)")
    existing_cols = {row[1] for row in cur.fetchall()}

    columns_to_add = [
        ("num_scenes", "INTEGER NOT NULL DEFAULT 0"),
        ("subtitles_enabled", "INTEGER NOT NULL DEFAULT 1"),
        ("subtitle_style_json", "TEXT"),
        ("include_bgm", "INTEGER NOT NULL DEFAULT 1"),
        ("bgm_volume", "REAL NOT NULL DEFAULT 0.15"),
        ("scenes_json", "TEXT"),
        ("hook_enabled", "INTEGER NOT NULL DEFAULT 1"),
        ("custom_hook", "TEXT"),
        ("hook_style_json", "TEXT"),
        ("tts_provider", "TEXT NOT NULL DEFAULT 'gemini'"),
        ("tts_model", "TEXT NOT NULL DEFAULT 'gemini-3.1-flash-tts-preview'"),
        ("source_video_url", "TEXT"),
        ("agentic_understanding", "INTEGER NOT NULL DEFAULT 1"),
    ]

    for col_name, col_def in columns_to_add:
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE video_generator_jobs ADD COLUMN {col_name} {col_def}")

    # Index for listing by user
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_video_gen_jobs_user
        ON video_generator_jobs(user_id, created_at DESC)
    """)

    # Index for ordering all jobs created_at DESC
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_video_gen_jobs_created
        ON video_generator_jobs(created_at DESC)
    """)

    # Index for status filtering
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_video_gen_jobs_status
        ON video_generator_jobs(status)
    """)

    conn.commit()
    conn.close()
    print("  [v6] video_generator_jobs table created ✓")


if __name__ == "__main__":
    migrate()
