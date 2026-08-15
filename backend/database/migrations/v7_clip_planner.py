"""
Migration v7 — Clip Planner + Raw Footage Assembly.

Adds persistence for two new features:

Feature 1 (YouTube AI Clip Planner):
  - clip_plans        — one row per job: AI-recommended clip windows the user can
                        drag/adjust before render. Stores the frozen transcript so
                        render can resume without re-analyzing.

Feature 2 (Raw Footage → AI Assembly, no-overlap):
  - source_assets     — uploaded footage files (one row per file) for a project.
  - asset_segments    — AI-detected shot/scene segments within an asset, with
                        per-segment description + quality score (from AI, no
                        hardcoded lexicon).
  - clip_allocations  — final non-overlapping segment→clip assignments produced
                        by the allocation engine.

Idempotent: safe to re-run.

Usage:
    python -m database.migrations.v7_clip_planner
"""
from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings


def migrate():
    db_path = settings.db_path
    print(f"  [v7] clip_planner + footage_assembly → {db_path}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # ─── Feature 1: YouTube clip plan (adjustable before render) ──────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clip_plans (
            job_id          TEXT PRIMARY KEY,
            status          TEXT NOT NULL DEFAULT 'plan_ready',
            video_duration  REAL,
            transcript_json TEXT,          -- frozen transcript for resume-render
            candidates_json TEXT NOT NULL, -- [{clip_id,start,end,score,hook,reason,...}]
            adjusted_json   TEXT,          -- user-edited windows (overrides candidates)
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ─── Feature 2: raw footage source assets ─────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS source_assets (
            asset_id    TEXT PRIMARY KEY,
            project_id  TEXT NOT NULL,
            file_path   TEXT NOT NULL,
            filename    TEXT,
            duration    REAL,
            fps         REAL,
            width       INTEGER,
            height      INTEGER,
            status      TEXT NOT NULL DEFAULT 'uploaded',
            metadata    TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_assets_project ON source_assets(project_id)"
    )

    # AI-detected shot/scene segments. description/score come from AI analysis.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS asset_segments (
            segment_id    TEXT PRIMARY KEY,
            asset_id      TEXT NOT NULL,
            project_id    TEXT NOT NULL,
            start_time    REAL NOT NULL,
            end_time      REAL NOT NULL,
            description   TEXT,
            transcript    TEXT,
            scene_label   TEXT,
            quality_score REAL DEFAULT 0,
            metadata      TEXT,
            FOREIGN KEY (asset_id) REFERENCES source_assets(asset_id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_asset_segments_asset ON asset_segments(asset_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_asset_segments_project ON asset_segments(project_id)"
    )

    # A planned final clip for a footage-assembly project.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS footage_clip_plans (
            clip_id         TEXT PRIMARY KEY,
            project_id      TEXT NOT NULL,
            title           TEXT,
            target_duration REAL DEFAULT 0,
            sequence        INTEGER DEFAULT 0,
            status          TEXT NOT NULL DEFAULT 'planned',
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_footage_clip_plans_project ON footage_clip_plans(project_id)"
    )

    # Final non-overlapping segment→clip assignments from the allocation engine.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clip_allocations (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            clip_id      TEXT NOT NULL,
            project_id   TEXT NOT NULL,
            asset_id     TEXT NOT NULL,
            source_start REAL NOT NULL,
            source_end   REAL NOT NULL,
            sequence     INTEGER NOT NULL DEFAULT 0,
            role         TEXT,
            score        REAL DEFAULT 0,
            FOREIGN KEY (clip_id) REFERENCES footage_clip_plans(clip_id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_clip_allocations_clip ON clip_allocations(clip_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_clip_allocations_project ON clip_allocations(project_id)"
    )

    conn.commit()
    conn.close()
    print("  [v7] clip_planner + footage_assembly tables created ✓")


if __name__ == "__main__":
    migrate()
