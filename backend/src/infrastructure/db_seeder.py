"""Database seeder — ensures schema, roles, permissions, and superadmin exist.

Run automatically on server startup via lifespan.
"""
import logging
import sqlite3

from src.config import settings
from src.infrastructure.auth import hash_password
from src.infrastructure.db_connection import get_dict_connection

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
-- Roles
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    is_system INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Permissions
CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Role-Permission mapping
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
);

-- Users
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    full_name TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    is_premium INTEGER NOT NULL DEFAULT 0,
    role_id INTEGER DEFAULT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at TEXT DEFAULT NULL,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE SET NULL
);

-- Refresh tokens
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- B-Roll templates
CREATE TABLE IF NOT EXISTS broll_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    component TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'motion_typography',
    description TEXT DEFAULT NULL,
    default_duration_ms INTEGER NOT NULL DEFAULT 2000,
    config TEXT NOT NULL DEFAULT '{}',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Job Clip B-Rolls
CREATE TABLE IF NOT EXISTS job_clip_brolls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    clip_rank INTEGER NOT NULL,
    template_id TEXT NOT NULL,
    at_time REAL NOT NULL,
    keyword_text TEXT NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 2000,
    rendered_path TEXT DEFAULT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (template_id) REFERENCES broll_templates(id) ON DELETE CASCADE
);

-- Transcript cache
CREATE TABLE IF NOT EXISTS transcript_cache (
    video_id TEXT PRIMARY KEY,
    transcript_json TEXT NOT NULL,
    whisper_model_hash TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'auto',
    duration_seconds REAL NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""


def seed_database() -> None:
    """Ensure all tables, roles, permissions, and superadmin user exist."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()

        # 1. Create all tables
        cur.executescript(SCHEMA_SQL)
        logger.info("db_seeder: tables ensured")

        # 2. Seed roles
        cur.execute("INSERT OR IGNORE INTO roles (id, name, description, is_system) VALUES (1, 'superadmin', 'Full system access', 1)")
        cur.execute("INSERT OR IGNORE INTO roles (id, name, description, is_system) VALUES (2, 'editor', 'Can create and manage jobs', 1)")
        cur.execute("INSERT OR IGNORE INTO roles (id, name, description, is_system) VALUES (3, 'viewer', 'Read-only access', 1)")

        # 3. Seed permissions
        permissions = [
            ("jobs:create", "Create Jobs", "jobs"),
            ("jobs:read", "View Jobs", "jobs"),
            ("jobs:delete", "Delete Jobs", "jobs"),
            ("styles:update", "Update Styles", "styles"),
            ("system:admin", "System Administration", "system"),
        ]
        for code, name, category in permissions:
            cur.execute(
                "INSERT OR IGNORE INTO permissions (code, name, category) VALUES (?, ?, ?)",
                (code, name, category),
            )

        # 4. Seed role-permission mappings
        # Superadmin gets all permissions
        cur.execute("SELECT id FROM permissions")
        all_perm_ids = [row["id"] for row in cur.fetchall()]
        for pid in all_perm_ids:
            cur.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (1, ?)", (pid,))

        # Editor gets create, read, styles
        cur.execute("SELECT id FROM permissions WHERE code IN ('jobs:create', 'jobs:read', 'styles:update')")
        editor_perm_ids = [row["id"] for row in cur.fetchall()]
        for pid in editor_perm_ids:
            cur.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (2, ?)", (pid,))

        # Viewer gets read only
        cur.execute("SELECT id FROM permissions WHERE code = 'jobs:read'")
        viewer_perm = cur.fetchone()
        if viewer_perm:
            cur.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (3, ?)", (viewer_perm["id"],))

        # 5. Seed superadmin user
        cur.execute("SELECT id FROM users WHERE email = ?", (settings.SUPERADMIN_EMAIL,))
        existing = cur.fetchone()
        if not existing:
            hashed = hash_password(settings.SUPERADMIN_PASSWORD)
            cur.execute(
                "INSERT INTO users (email, hashed_password, full_name, is_active, role_id) VALUES (?, ?, ?, 1, 1)",
                (settings.SUPERADMIN_EMAIL, hashed, "Super Admin"),
            )
            logger.info(f"db_seeder: superadmin created ({settings.SUPERADMIN_EMAIL})")
        else:
            logger.info(f"db_seeder: superadmin already exists ({settings.SUPERADMIN_EMAIL})")

        # 6. Seed B-Roll templates
        templates = [
            ("word_pop_typography", "Word Pop", "WordPopBroll", "Kata kunci muncul dengan scale/pop", 2000),
            ("line_reveal_typography", "Line Reveal", "LineRevealBroll", "Baris teks reveal dengan mask wipe", 2500),
            ("particle_text_burst", "Particle Burst", "ParticleBurstBroll", "Teks terbentuk dari partikel", 3000),
        ]
        for tid, name, component, desc, duration in templates:
            cur.execute(
                "INSERT OR IGNORE INTO broll_templates (id, name, component, description, default_duration_ms) VALUES (?, ?, ?, ?, ?)",
                (tid, name, component, desc, duration),
            )

        conn.commit()
        logger.info("db_seeder: seed complete")

    except Exception as e:
        logger.error(f"db_seeder: error — {e}")
        raise
    finally:
        conn.close()
