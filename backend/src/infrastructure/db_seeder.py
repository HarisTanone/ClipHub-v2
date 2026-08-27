"""Database seeder — ensures schema, roles, permissions, and superadmin exist.

Run automatically on server startup via lifespan.
"""
import logging
import sqlite3

from src.config import settings
from src.infrastructure.auth import hash_password, verify_password
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

-- Dynamic System Settings with RBAC
CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    data_type TEXT NOT NULL DEFAULT 'string',
    min_role TEXT NOT NULL DEFAULT 'superadmin',
    is_secret INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by INTEGER DEFAULT NULL,
    FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
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

        # 2. Seed roles (System roles)
        system_roles = [
            ("superadmin", "Full system access with all capabilities", 1),
            ("admin", "Administrative management for users, roles, settings, styles, and automation", 1),
            ("editor", "Creator and editor: can create/manage jobs, edit styles, generate videos, and publish", 1),
            ("viewer", "Read-only access to view jobs, clips, styles, and presets", 1),
        ]
        for rname, rdesc, is_sys in system_roles:
            cur.execute("SELECT id FROM roles WHERE name = ?", (rname,))
            rrow = cur.fetchone()
            if not rrow:
                cur.execute("INSERT INTO roles (name, description, is_system) VALUES (?, ?, ?)", (rname, rdesc, is_sys))
            else:
                cur.execute("UPDATE roles SET description = ?, is_system = ? WHERE id = ?", (rdesc, is_sys, rrow["id"]))

        # Get role ID mapping
        cur.execute("SELECT id, name FROM roles")
        role_map = {row["name"]: row["id"] for row in cur.fetchall()}
        superadmin_role_id = role_map.get("superadmin")
        admin_role_id = role_map.get("admin")
        editor_role_id = role_map.get("editor")
        viewer_role_id = role_map.get("viewer")

        # 3. Seed comprehensive permissions
        permissions = [
            # Jobs
            ("jobs:create", "Create Jobs", "jobs", "Create new video clipping jobs and upload files"),
            ("jobs:read", "View Jobs", "jobs", "View jobs, status, and rendered clips"),
            ("jobs:update", "Update Jobs", "jobs", "Edit clips, operations, and titles"),
            ("jobs:delete", "Delete Jobs", "jobs", "Delete jobs and rendered outputs"),
            ("jobs:export", "Export Media", "jobs", "Download clips, media assets, and transcripts"),
            # Styles & Presets
            ("styles:read", "View Styles", "styles", "View style presets and subtitle configurations"),
            ("styles:create", "Create Styles", "styles", "Create new style presets"),
            ("styles:update", "Update Styles", "styles", "Edit style presets and subtitle formatting"),
            ("styles:delete", "Delete Styles", "styles", "Delete custom style presets"),
            ("brolls:read", "View B-Rolls", "styles", "View B-Roll motion typography templates"),
            ("brolls:manage", "Manage B-Rolls", "styles", "Configure and edit B-Roll templates"),
            # Autopilot
            ("autopilot:read", "View Autopilot", "autopilot", "View autopilot schedule and task logs"),
            ("autopilot:manage", "Manage Autopilot", "autopilot", "Configure autopilot settings and topics"),
            ("autopilot:trigger", "Trigger Autopilot", "autopilot", "Manually trigger autopilot clipping run"),
            # Video Generator
            ("videogen:create", "Generate Videos", "video_gen", "Create AI-generated videos from prompts"),
            ("videogen:read", "View Video Gen", "video_gen", "View AI generated video history"),
            # Social & Telegram
            ("social:read", "View Social Accounts", "social", "View connected social accounts"),
            ("social:manage", "Manage Social Accounts", "social", "Connect and manage social accounts"),
            ("social:publish", "Publish to Social", "social", "Publish and schedule clips to social media"),
            ("telegram:manage", "Manage Telegram Bot", "social", "Configure Telegram bot settings and notifications"),
            # AI Models & System Settings
            ("models:read", "View AI Models", "settings", "View 9router LLM and AI models status"),
            ("models:update", "Update AI Models", "settings", "Configure 9router and LLM routing"),
            ("models:test", "Test AI Models", "settings", "Run benchmark and model tests"),
            ("settings:read", "View Settings", "settings", "View system and studio settings"),
            ("settings:update", "Update Settings", "settings", "Edit preferences and visual studio tuning"),
            ("settings:system", "System Config", "settings", "Manage dynamic database system configs"),
            # User & Role Access Control (RBAC)
            ("users:read", "View Users", "rbac", "View registered users and accounts"),
            ("users:create", "Create Users", "rbac", "Register new users with roles"),
            ("users:update", "Update Users", "rbac", "Edit user profile, role, and premium status"),
            ("users:delete", "Deactivate Users", "rbac", "Deactivate or remove user accounts"),
            ("roles:read", "View Roles", "rbac", "View roles and permission matrices"),
            ("roles:create", "Create Roles", "rbac", "Create custom roles"),
            ("roles:update", "Update Roles", "rbac", "Modify role permissions and descriptions"),
            ("roles:delete", "Delete Roles", "rbac", "Delete custom non-system roles"),
            # System Ops
            ("system:monitoring", "System Monitoring", "system", "View system metrics and health"),
            ("system:testing", "Test & Deploy", "system", "Run pre-deployment test scripts"),
            ("system:admin", "System Administration", "system", "Unrestricted administrator control"),
        ]

        for code, name, category, desc in permissions:
            cur.execute(
                """INSERT INTO permissions (code, name, category, description)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET name = excluded.name, category = excluded.category, description = excluded.description""",
                (code, name, category, desc),
            )

        # 4. Seed role-permission mappings
        # Superadmin gets ALL permissions
        if superadmin_role_id:
            cur.execute("SELECT id FROM permissions")
            all_perm_ids = [row["id"] for row in cur.fetchall()]
            for pid in all_perm_ids:
                cur.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)", (superadmin_role_id, pid))

        # Admin role permissions (all rbac, jobs, styles, autopilot, social, models:read, settings, system:monitoring)
        if admin_role_id:
            cur.execute(
                """SELECT id FROM permissions WHERE category IN ('jobs', 'styles', 'autopilot', 'video_gen', 'social', 'rbac')
                OR code IN ('models:read', 'models:test', 'settings:read', 'settings:update', 'settings:system', 'system:monitoring')"""
            )
            admin_perm_ids = [row["id"] for row in cur.fetchall()]
            for pid in admin_perm_ids:
                cur.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)", (admin_role_id, pid))

        # Editor role permissions
        if editor_role_id:
            cur.execute(
                """SELECT id FROM permissions WHERE code IN (
                    'jobs:create', 'jobs:read', 'jobs:update', 'jobs:delete', 'jobs:export',
                    'styles:read', 'styles:create', 'styles:update', 'brolls:read',
                    'autopilot:read', 'videogen:create', 'videogen:read',
                    'social:read', 'social:publish',
                    'settings:read', 'settings:update'
                )"""
            )
            editor_perm_ids = [row["id"] for row in cur.fetchall()]
            for pid in editor_perm_ids:
                cur.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)", (editor_role_id, pid))

        # Viewer role permissions
        if viewer_role_id:
            cur.execute(
                """SELECT id FROM permissions WHERE code IN (
                    'jobs:read', 'jobs:export', 'styles:read', 'brolls:read',
                    'videogen:read', 'social:read', 'autopilot:read', 'settings:read'
                )"""
            )
            viewer_perm_ids = [row["id"] for row in cur.fetchall()]
            for pid in viewer_perm_ids:
                cur.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)", (viewer_role_id, pid))

        # 5. Seed superadmin user
        cur.execute("SELECT id, hashed_password FROM users WHERE email = ?", (settings.SUPERADMIN_EMAIL,))
        existing = cur.fetchone()
        if not existing:
            hashed = hash_password(settings.SUPERADMIN_PASSWORD)
            cur.execute(
                "INSERT INTO users (email, hashed_password, full_name, is_active, role_id) VALUES (?, ?, ?, 1, ?)",
                (settings.SUPERADMIN_EMAIL, hashed, "Super Admin", superadmin_role_id),
            )
            logger.info(f"db_seeder: superadmin created ({settings.SUPERADMIN_EMAIL})")
        else:
            if not verify_password(settings.SUPERADMIN_PASSWORD, existing["hashed_password"]):
                new_hash = hash_password(settings.SUPERADMIN_PASSWORD)
                cur.execute(
                    "UPDATE users SET hashed_password = ? WHERE email = ?",
                    (new_hash, settings.SUPERADMIN_EMAIL),
                )
                logger.info("db_seeder: superadmin password updated")
            if superadmin_role_id:
                cur.execute("UPDATE users SET role_id = ? WHERE email = ?", (superadmin_role_id, settings.SUPERADMIN_EMAIL))
            logger.info(f"db_seeder: superadmin already exists ({settings.SUPERADMIN_EMAIL})")

        # 6. Seed B-Roll templates
        templates = [
            # Legacy (FFmpeg overlay compatible)
            ("word_pop_typography", "Word Pop", "WordPopBroll", "Kata kunci muncul dengan scale/pop", 2000),
            ("line_reveal_typography", "Line Reveal", "LineRevealBroll", "Baris teks reveal dengan mask wipe", 2500),
            ("particle_text_burst", "Particle Burst", "ParticleBurstBroll", "Teks terbentuk dari partikel", 3000),
            # v3.1 Remotion motion-graphic styles (preview == final)
            ("ken_burns", "Ken Burns", "KenBurnsBroll", "Zoom + pan lambat gaya dokumenter (Remotion)", 2500),
            ("parallax_zoom", "Parallax Zoom", "ParallaxZoomBroll", "Zoom berbasis kedalaman (Remotion)", 2500),
            ("light_sweep", "Light Sweep", "LightSweepBroll", "Sapuan cahaya + reveal teks (Remotion)", 2500),
            ("particle_float", "Particle Float", "ParticleFloatBroll", "Partikel melayang + teks (Remotion)", 2500),
            ("depth_parallax", "Depth Parallax", "DepthParallaxBroll", "Parallax fg/bg cinematic (Remotion)", 2500),
            ("glitch_reveal", "Glitch Reveal", "GlitchRevealBroll", "Glitch + reveal energetik (Remotion)", 2000),
            ("typewriter", "Typewriter", "TypewriterBroll", "Ketik huruf per huruf (Remotion)", 2500),
            ("stroke_draw", "Stroke Draw", "StrokeDrawBroll", "Teks tergambar dari outline (Remotion)", 2500),
        ]
        for tid, name, component, desc, duration in templates:
            cur.execute(
                "INSERT OR IGNORE INTO broll_templates (id, name, component, description, default_duration_ms) VALUES (?, ?, ?, ?, ?)",
                (tid, name, component, desc, duration),
            )

        conn.commit()

        # 7. Seed dynamic system settings defaults
        try:
            from src.infrastructure.system_config_store import seed_system_settings_defaults
            seed_system_settings_defaults()
            logger.info("db_seeder: system settings defaults initialized")
        except Exception as err:
            logger.warning(f"db_seeder: warning seeding system settings: {err}")

        logger.info("db_seeder: seed complete")

    except Exception as e:
        logger.error(f"db_seeder: error — {e}")
        raise
    finally:
        conn.close()
