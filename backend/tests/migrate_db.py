"""Migrate existing SQLite DB — add missing columns."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "autoclip.db")
print(f"DB: {DB_PATH}")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Check jobs table
cur.execute("PRAGMA table_info(jobs)")
job_cols = [row[1] for row in cur.fetchall()]
print(f"Jobs columns ({len(job_cols)}): {job_cols}")

if "pipeline_version" not in job_cols:
    print("  [MIGRATE] Adding pipeline_version to jobs...")
    cur.execute("ALTER TABLE jobs ADD COLUMN pipeline_version TEXT NOT NULL DEFAULT 'v1'")
    conn.commit()
    print("  [DONE]")
else:
    print("  [OK] pipeline_version exists")

# Check users table
cur.execute("PRAGMA table_info(users)")
user_cols = [row[1] for row in cur.fetchall()]
print(f"\nUsers columns ({len(user_cols)}): {user_cols}")

if "is_premium" not in user_cols:
    print("  [MIGRATE] Adding is_premium to users...")
    cur.execute("ALTER TABLE users ADD COLUMN is_premium INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    print("  [DONE]")
else:
    print("  [OK] is_premium exists")

if "pipeline_override" not in user_cols:
    print("  [MIGRATE] Adding pipeline_override to users...")
    cur.execute("ALTER TABLE users ADD COLUMN pipeline_override TEXT DEFAULT NULL")
    conn.commit()
    print("  [DONE]")
else:
    print("  [OK] pipeline_override exists")

conn.close()
print("\n[OK] Migration complete")
