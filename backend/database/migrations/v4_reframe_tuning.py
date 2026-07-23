"""
Migration v4.0 — Add Reframe Tuning Configs Table

Stores dynamic reframe engine tuning parameters in DB.
Removes hardcoded constants from PodcastReframeEngine.

Idempotent: safe to re-run. Always re-applies known safe default
fixes so deploy.sh does not leave stale hysteresis values behind.

Usage:
    python -m database.migrations.v4_reframe_tuning
"""

import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings


def _apply_safe_defaults(cur, conn) -> None:
    """Bump known-stale global defaults without wiping deliberate user overrides
    that are already at or above the safe floor."""
    # min_separation_ratio: 0.20 was too strict for face-to-face podcasts
    cur.execute(
        """
        UPDATE reframe_tuning_configs
        SET min_separation_ratio = 0.05, updated_at = datetime('now')
        WHERE min_separation_ratio > 0.05
        """
    )
    if cur.rowcount:
        print(f"  [FIX] min_separation_ratio → 0.05 ({cur.rowcount} row(s))")

    # grid_max_zoom floor for close-up panels
    cur.execute(
        """
        UPDATE reframe_tuning_configs
        SET grid_max_zoom = 2.20, updated_at = datetime('now')
        WHERE grid_max_zoom != 2.20
        """
    )
    if cur.rowcount:
        print(f"  [FIX] grid_max_zoom → 2.20 ({cur.rowcount} row(s))")

    # Anti-flicker hysteresis: enter=9, exit=6, min segment=3s
    cur.execute(
        """
        UPDATE reframe_tuning_configs
        SET min_grid_segment_seconds = 3.0,
            grid_enter_samples = 9,
            grid_exit_samples = 6,
            updated_at = datetime('now')
        WHERE min_grid_segment_seconds < 3.0
           OR grid_enter_samples < 9
           OR grid_exit_samples < 6
        """
    )
    if cur.rowcount:
        print(
            f"  [FIX] grid hysteresis → enter=9 exit=6 min_seg=3.0s "
            f"({cur.rowcount} row(s))"
        )

    # Drop duplicate global (user_id IS NULL) rows — SQLite NULL uniqueness quirk
    cur.execute(
        """
        DELETE FROM reframe_tuning_configs
        WHERE user_id IS NULL
          AND id NOT IN (
              SELECT MAX(id) FROM reframe_tuning_configs WHERE user_id IS NULL
          )
        """
    )
    if cur.rowcount:
        print(f"  [CLEANUP] removed {cur.rowcount} duplicate global config row(s)")

    conn.commit()


def migrate():
    """Create table if missing, then always apply safe default fixes."""
    db_path = settings.db_path

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}, will be created by app startup")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='reframe_tuning_configs'"
    )
    exists = cur.fetchone() is not None

    if not exists:
        print("  [MIGRATE] Creating reframe_tuning_configs table...")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reframe_tuning_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT NULL,
                sample_interval_sec REAL NOT NULL DEFAULT 0.333,
                max_samples INTEGER NOT NULL DEFAULT 720,
                face_confidence REAL NOT NULL DEFAULT 0.55,
                min_face_size_ratio REAL NOT NULL DEFAULT 0.10,
                max_face_size_ratio REAL NOT NULL DEFAULT 0.50,
                min_separation_ratio REAL NOT NULL DEFAULT 0.05,
                min_coexist_ratio REAL NOT NULL DEFAULT 0.40,
                dominance_single_crop REAL NOT NULL DEFAULT 0.75,
                grid_base_zoom REAL NOT NULL DEFAULT 1.08,
                grid_max_zoom REAL NOT NULL DEFAULT 2.20,
                grid_face_margin REAL NOT NULL DEFAULT 0.35,
                grid_enter_samples INTEGER NOT NULL DEFAULT 9,
                grid_exit_samples INTEGER NOT NULL DEFAULT 6,
                min_grid_segment_seconds REAL NOT NULL DEFAULT 3.0,
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
            """
        )
        cur.execute(
            "INSERT OR IGNORE INTO reframe_tuning_configs (user_id) VALUES (NULL)"
        )
        conn.commit()
        print("  [DONE] reframe_tuning_configs table created")
    else:
        print("  [OK] reframe_tuning_configs already exists")
        # Ensure global row exists even on older DBs that only had user rows
        cur.execute(
            "INSERT OR IGNORE INTO reframe_tuning_configs (user_id) VALUES (NULL)"
        )
        conn.commit()

    _apply_safe_defaults(cur, conn)
    conn.close()
    print("  [DONE] reframe_tuning_configs migration complete")


if __name__ == "__main__":
    migrate()
    print("\nMigration v4 completed.")
