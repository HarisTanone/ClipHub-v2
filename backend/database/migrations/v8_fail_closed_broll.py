"""Migration v8 — Fail-closed broll_enabled default.

Fixes fail-OPEN: jobs.broll_enabled DEFAULT 1 meant every new job
got b-roll ON unless explicitly set. Fail-closed is DEFAULT 0.
Idempotent: safe to re-run. SQLite cannot ALTER COLUMN DEFAULT
without recreate, so we handle it via recreate-if-needed + pragma.
"""
from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from src.config import settings
    _db_path = settings.db_path
except Exception:
    _db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "autoclip.db")


def migrate():
    db_path = _db_path
    print(f"  [v8] fail-closed broll_enabled DEFAULT 0 → {db_path}")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    cur = conn.cursor()
    # Check existing table sql
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'")
    row = cur.fetchone()
    if not row or not row[0]:
        conn.close()
        print("  [v8] jobs table not yet created — schema.sql will apply with DEFAULT 0")
        return
    sql = row[0]
    if "broll_enabled INTEGER NOT NULL DEFAULT 0" in sql:
        conn.close()
        print("  [v8] already DEFAULT 0 — nothing to do")
        return
    # Recreate jobs table preserving data with corrected default
    # SQLite: create new table, copy, drop old, rename
    print("  [v8] migrating jobs.broll_enabled DEFAULT 1 → 0 (recreate)")
    # Get current schema, patch DEFAULT
    new_sql = sql.replace(
        "broll_enabled INTEGER NOT NULL DEFAULT 1",
        "broll_enabled INTEGER NOT NULL DEFAULT 0",
    )
    # Rename old
    cur.execute("ALTER TABLE jobs RENAME TO jobs_old_v8")
    cur.execute(new_sql)
    # Copy data
    cur.execute("INSERT INTO jobs SELECT * FROM jobs_old_v8")
    cur.execute("DROP TABLE jobs_old_v8")
    # Recreate indices
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_job_id ON jobs(job_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_video_id ON jobs(video_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id)")
    conn.commit()
    conn.close()
    print("  [v8] done — jobs.broll_enabled now DEFAULT 0")


if __name__ == "__main__":
    migrate()
