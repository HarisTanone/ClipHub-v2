"""Settings API routes — user preferences and system configuration.

Endpoints:
- GET  /api/settings           — Get current user settings
- PUT  /api/settings           — Update user settings
- GET  /api/settings/system    — Get system info (admin only)
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.config import settings
from src.infrastructure.db_connection import get_dict_connection
from src.presentation.auth_deps import CurrentUser, get_current_user

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger(__name__)


# ─── Schemas ──────────────────────────────────────────────────────────────────

class UserSettings(BaseModel):
    default_aspect_ratio: str = "9:16"
    default_hook_engine: str = "v3"
    default_style_preset: str = ""
    default_hook_style: str = ""
    whisper_model_size: str = "medium"
    autogrid_enabled: bool = False
    # Remotion settings
    use_remotion: bool = True
    remotion_ai_layer: bool = True
    remotion_quality: str = "medium"
    # Pipeline mode (superadmin override)
    pipeline_mode: str = "v1"  # "v1" (Gemini) or "v2" (Groq)


class SystemInfo(BaseModel):
    version: str
    mode: str
    max_concurrent_jobs: int
    max_whisper_parallel: int
    max_render_workers: int
    whisper_model_size: str
    gemini_model: str
    gemini_keys_count: int
    cdn_enabled: bool
    asset_fetch_enabled: bool


# ─── Ensure settings table exists ─────────────────────────────────────────────

def _ensure_settings_table():
    conn = get_dict_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                default_aspect_ratio TEXT NOT NULL DEFAULT '9:16',
                default_hook_engine TEXT NOT NULL DEFAULT 'v3',
                default_style_preset TEXT NOT NULL DEFAULT '',
                default_hook_style TEXT NOT NULL DEFAULT '',
                max_clips_per_job INTEGER NOT NULL DEFAULT 5,
                whisper_model_size TEXT NOT NULL DEFAULT 'medium',
                broll_enabled INTEGER NOT NULL DEFAULT 1,
                autogrid_enabled INTEGER NOT NULL DEFAULT 0,
                use_remotion INTEGER NOT NULL DEFAULT 0,
                remotion_ai_layer INTEGER NOT NULL DEFAULT 0,
                remotion_threejs INTEGER NOT NULL DEFAULT 0,
                remotion_quality TEXT NOT NULL DEFAULT 'medium',
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        # Add Remotion columns if they don't exist (migration for existing tables)
        try:
            conn.execute("ALTER TABLE user_settings ADD COLUMN use_remotion INTEGER NOT NULL DEFAULT 0")
        except:
            pass
        try:
            conn.execute("ALTER TABLE user_settings ADD COLUMN remotion_ai_layer INTEGER NOT NULL DEFAULT 0")
        except:
            pass
        try:
            conn.execute("ALTER TABLE user_settings ADD COLUMN remotion_threejs INTEGER NOT NULL DEFAULT 0")
        except:
            pass
        try:
            conn.execute("ALTER TABLE user_settings ADD COLUMN remotion_quality TEXT NOT NULL DEFAULT 'medium'")
        except:
            pass
        conn.commit()
    finally:
        conn.close()


_ensure_settings_table()


def _ensure_pipeline_override_column():
    """Ensure pipeline_override column exists on users table."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        columns = [row["name"] for row in cur.fetchall()]
        if "pipeline_override" not in columns:
            cur.execute("ALTER TABLE users ADD COLUMN pipeline_override TEXT DEFAULT NULL")
            conn.commit()
            logger.info("settings: added pipeline_override column to users table")
    except Exception as e:
        logger.warning(f"settings: pipeline_override migration failed: {e}")
    finally:
        conn.close()

_ensure_pipeline_override_column()


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("")
async def get_settings(user: CurrentUser = Depends(get_current_user)):
    """Get current user's pipeline settings."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM user_settings WHERE user_id = ?", (user.id,))
        row = cur.fetchone()

        # Get pipeline_mode from users.pipeline_override (superadmin)
        pipeline_mode = "v1"
        if user.is_superadmin:
            try:
                cur.execute("SELECT pipeline_override FROM users WHERE id = ?", (user.id,))
                prow = cur.fetchone()
                if prow and prow["pipeline_override"]:
                    pipeline_mode = prow["pipeline_override"]
            except Exception:
                pass  # Column may not exist yet

        if not row:
            defaults = UserSettings(pipeline_mode=pipeline_mode).model_dump()
            return {"success": True, "data": defaults}

        return {
            "success": True,
            "data": {
                "default_aspect_ratio": row["default_aspect_ratio"],
                "default_hook_engine": row["default_hook_engine"],
                "default_style_preset": row["default_style_preset"],
                "default_hook_style": row["default_hook_style"],
                "whisper_model_size": row["whisper_model_size"],
                "autogrid_enabled": bool(row["autogrid_enabled"]),
                "use_remotion": bool(row["use_remotion"]) if "use_remotion" in row.keys() else False,
                "remotion_ai_layer": bool(row["remotion_ai_layer"]) if "remotion_ai_layer" in row.keys() else False,
                "remotion_quality": row["remotion_quality"] if "remotion_quality" in row.keys() else "medium",
                "pipeline_mode": pipeline_mode,
            },
        }
    finally:
        conn.close()


@router.put("")
async def update_settings(body: UserSettings, user: CurrentUser = Depends(get_current_user)):
    """Update current user's pipeline settings."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO user_settings
            (user_id, default_aspect_ratio, default_hook_engine, default_style_preset,
             default_hook_style, whisper_model_size, autogrid_enabled,
             use_remotion, remotion_ai_layer, remotion_quality, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                default_aspect_ratio = excluded.default_aspect_ratio,
                default_hook_engine = excluded.default_hook_engine,
                default_style_preset = excluded.default_style_preset,
                default_hook_style = excluded.default_hook_style,
                whisper_model_size = excluded.whisper_model_size,
                autogrid_enabled = excluded.autogrid_enabled,
                use_remotion = excluded.use_remotion,
                remotion_ai_layer = excluded.remotion_ai_layer,
                remotion_quality = excluded.remotion_quality,
                updated_at = datetime('now')
            """,
            (
                user.id, body.default_aspect_ratio, body.default_hook_engine,
                body.default_style_preset, body.default_hook_style,
                body.whisper_model_size, int(body.autogrid_enabled),
                int(body.use_remotion), int(body.remotion_ai_layer),
                body.remotion_quality,
            ),
        )

        # Save pipeline_mode override for superadmin
        if user.is_superadmin and body.pipeline_mode in ("v1", "v2"):
            cur.execute(
                "UPDATE users SET pipeline_override = ? WHERE id = ?",
                (body.pipeline_mode, user.id),
            )

        conn.commit()
        return {"success": True, "message": "Settings saved"}
    finally:
        conn.close()


@router.get("/system")
async def get_system_info(user: CurrentUser = Depends(get_current_user)):
    """Get system configuration info (available to all authenticated users)."""
    return {
        "success": True,
        "data": SystemInfo(
            version="0.4.0",
            mode=settings.PIPELINE_ENV,
            max_concurrent_jobs=settings.MAX_CONCURRENT_JOBS,
            max_whisper_parallel=settings.MAX_WHISPER_PARALLEL,
            max_render_workers=settings.MAX_RENDER_WORKERS,
            whisper_model_size=settings.WHISPER_MODEL_SIZE,
            gemini_model=settings.GEMINI_MODEL,
            gemini_keys_count=len(settings.gemini_api_keys),
            cdn_enabled=settings.CDN_ENABLED,
            asset_fetch_enabled=settings.ASSET_FETCH_ENABLED,
        ).model_dump(),
    }
