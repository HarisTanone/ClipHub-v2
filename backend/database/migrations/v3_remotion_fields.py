"""
Migration v3.0 — Add Remotion Integration Fields

Run this script to migrate existing database to support Remotion features.
This adds new columns to the jobs table and creates new tables for
style_presets, remotion_renders, and hook_animations.

Usage:
    python -m database.migrations.v3_remotion_fields
"""

import sqlite3
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings


def migrate():
    """Run migration to add Remotion fields."""
    
    db_path = settings.db_path
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}, will be created by app startup")
        return
    
    print(f"Migrating database at {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # ─── Add new columns to jobs table ─────────────────────────────────────
    
    new_columns = [
        ("use_remotion", "INTEGER NOT NULL DEFAULT 0"),
        ("ai_layer_enabled", "INTEGER NOT NULL DEFAULT 0"),
        ("threejs_enabled", "INTEGER NOT NULL DEFAULT 0"),
        ("scene_graphs", "TEXT DEFAULT NULL"),
        ("remotion_quality", "TEXT DEFAULT 'medium'"),
    ]
    
    for col_name, col_def in new_columns:
        try:
            cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_def}")
            print(f"  ✓ Added column jobs.{col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print(f"  ○ Column jobs.{col_name} already exists")
            else:
                raise
    
    # ─── Create new tables ─────────────────────────────────────────────────
    
    # Style presets table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS style_presets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT NULL,
            primary_color TEXT NOT NULL DEFAULT '#ffffff',
            secondary_color TEXT NOT NULL DEFAULT '#ffcc00',
            background_accent TEXT NOT NULL DEFAULT '#000000',
            typography_mood TEXT NOT NULL DEFAULT 'bold_impact',
            hook_animation TEXT NOT NULL DEFAULT 'fade_scale',
            energy_level TEXT NOT NULL DEFAULT 'medium',
            transition_style TEXT NOT NULL DEFAULT 'smooth',
            subtitle_position TEXT NOT NULL DEFAULT 'bottom',
            subtitle_uppercase INTEGER NOT NULL DEFAULT 0,
            enable_threejs INTEGER NOT NULL DEFAULT 0,
            enable_ai_layer INTEGER NOT NULL DEFAULT 0,
            is_system INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    print("  ✓ Created table style_presets")
    
    # Remotion renders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS remotion_renders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            clip_rank INTEGER NOT NULL,
            render_job_id TEXT DEFAULT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            progress REAL NOT NULL DEFAULT 0.0,
            current_frame INTEGER NOT NULL DEFAULT 0,
            total_frames INTEGER NOT NULL DEFAULT 0,
            output_path TEXT DEFAULT NULL,
            error_message TEXT DEFAULT NULL,
            render_time_seconds REAL DEFAULT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            started_at TEXT DEFAULT NULL,
            completed_at TEXT DEFAULT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
        )
    """)
    print("  ✓ Created table remotion_renders")
    
    # Hook animations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hook_animations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT NULL,
            preview_url TEXT DEFAULT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    print("  ✓ Created table hook_animations")
    
    # ─── Create indexes ─────────────────────────────────────────────────────
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_style_presets_active ON style_presets(is_active)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_remotion_renders_job ON remotion_renders(job_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_remotion_renders_status ON remotion_renders(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_remotion_renders_job_clip ON remotion_renders(job_id, clip_rank)")
    print("  ✓ Created indexes")
    
    # ─── Seed default data ─────────────────────────────────────────────────
    
    # Style presets
    cursor.execute("""
        INSERT OR IGNORE INTO style_presets (id, name, description, primary_color, secondary_color, background_accent, typography_mood, hook_animation, energy_level, transition_style, subtitle_position, enable_threejs, enable_ai_layer, is_system) VALUES
            ('bold_black', 'Bold Black', 'Classic bold white text on dark background', '#ffffff', '#ffcc00', '#000000', 'bold_impact', 'fade_scale', 'medium', 'smooth', 'bottom', 0, 0, 1),
            ('neon_pop', 'Neon Pop', 'Vibrant neon colors with energetic animations', '#00ffcc', '#ff00ff', '#0a0a0a', 'playful', 'slide_up', 'high', 'kinetic', 'bottom', 1, 0, 1),
            ('cinematic_dark', 'Cinematic Dark', 'Dark cinematic mood with dramatic effects', '#e0e0e0', '#ff4444', '#0d0d0d', 'dramatic', 'fade_scale', 'low', 'smooth', 'bottom', 1, 1, 1),
            ('minimal_clean', 'Minimal Clean', 'Clean minimal style with subtle animations', '#333333', '#666666', '#ffffff', 'elegant_minimal', 'typewriter', 'low', 'smooth', 'center', 0, 0, 1),
            ('glitch_tech', 'Glitch Tech', 'Futuristic glitch effects for tech content', '#00ff00', '#ff0000', '#0a0a0a', 'bold_impact', 'glitch', 'high', 'kinetic', 'bottom', 1, 1, 1)
    """)
    print(f"  ✓ Inserted {cursor.rowcount} style presets")
    
    # Hook animations
    cursor.execute("""
        INSERT OR IGNORE INTO hook_animations (id, name, description) VALUES
            ('fade_scale', 'Fade & Scale', 'Text fades in with scale animation'),
            ('slide_up', 'Slide Up', 'Text slides up from bottom'),
            ('glitch', 'Glitch Effect', 'RGB glitch with digital distortion'),
            ('typewriter', 'Typewriter', 'Character-by-character reveal')
    """)
    print(f"  ✓ Inserted {cursor.rowcount} hook animations")
    
    # ─── Commit and close ───────────────────────────────────────────────────
    
    conn.commit()
    conn.close()
    
    print("\nMigration completed successfully!")


if __name__ == "__main__":
    migrate()
