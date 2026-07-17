"""
Migration v4.0 — Add Reframe Tuning Configs Table

Stores dynamic reframe engine tuning parameters in DB.
Removes hardcoded constants from PodcastReframeEngine.

Usage:
    python -m database.migrations.v4_reframe_tuning
"""

import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings


def migrate():
    """Run migration to add reframe_tuning_configs table."""
    db_path = settings.db_path

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}, will be created by app startup")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Check if table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reframe_tuning_configs'")
    if cur.fetchone():
        print("  [OK] reframe_tuning_configs already exists")
        conn.close()
        return

    print("  [MIGRATE] Creating reframe_tuning_configs table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reframe_tuning_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT NULL,
            sample_interval_sec REAL NOT NULL DEFAULT 0.333,
            max_samples INTEGER NOT NULL DEFAULT 720,
            face_confidence REAL NOT NULL DEFAULT 0.55,
            min_face_size_ratio REAL NOT NULL DEFAULT 0.10,
            max_face_size_ratio REAL NOT NULL DEFAULT 0.50,
            min_separation_ratio REAL NOT NULL DEFAULT 0.20,
            min_coexist_ratio REAL NOT NULL DEFAULT 0.40,
            dominance_single_crop REAL NOT NULL DEFAULT 0.75,
            grid_base_zoom REAL NOT NULL DEFAULT 1.08,
            grid_max_zoom REAL NOT NULL DEFAULT 1.85,
            grid_face_margin REAL NOT NULL DEFAULT 0.35,
            grid_enter_samples INTEGER NOT NULL DEFAULT 4,
            grid_exit_samples INTEGER NOT NULL DEFAULT 2,
            min_grid_segment_seconds REAL NOT NULL DEFAULT 1.20,
            min_face_area_px INTEGER NOT NULL DEFAULT 4000,
            min_area_ratio_to_max REAL NOT NULL DEFAULT 0.25,
            min_frame_ratio REAL NOT NULL DEFAULT 0.15,
            ghost_iou_threshold REAL NOT NULL DEFAULT 0.25,
            ghost_center_dist_ratio REAL NOT NULL DEFAULT 0.08,
            ghost_center_dist_broad REAL NOT NULL DEFAULT 0.20,
            min_pair_size_ratio REAL NOT NULL DEFAULT 0.18,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id)
        )
    """)

    # Insert default global config (user_id=NULL)
    cur.execute("""
        INSERT OR IGNORE INTO reframe_tuning_configs (user_id) VALUES (NULL)
    """)

    conn.commit()
    conn.close()
    print("  [DONE] reframe_tuning_configs table created with default global config")


if __name__ == "__main__":
    migrate()
    print("\nMigration v4 completed.")