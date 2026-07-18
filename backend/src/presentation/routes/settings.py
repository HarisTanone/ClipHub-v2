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
    llm_provider: str
    nine_router_model: str
    force_v2_pipeline: bool
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


# ─── Reframe Tuning Config ──────────────────────────────────────────────────────

REFRAME_TUNING_COLUMNS = [
    "sample_interval_sec", "max_samples", "face_confidence",
    "min_face_size_ratio", "max_face_size_ratio",
    "min_separation_ratio", "min_coexist_ratio",
    "dominance_single_crop", "grid_base_zoom", "grid_max_zoom",
    "grid_face_margin", "grid_enter_samples", "grid_exit_samples",
    "min_grid_segment_seconds",
    "min_face_area_px", "min_area_ratio_to_max", "min_frame_ratio",
    "ghost_iou_threshold", "ghost_center_dist_ratio",
    "ghost_center_dist_broad", "min_pair_size_ratio",
]

REFRAME_TUNING_DEFAULTS = {
    "sample_interval_sec": 0.333, "max_samples": 720, "face_confidence": 0.55,
    "min_face_size_ratio": 0.10, "max_face_size_ratio": 0.50,
    "min_separation_ratio": 0.05, "min_coexist_ratio": 0.40,
    "dominance_single_crop": 0.75, "grid_base_zoom": 1.08, "grid_max_zoom": 3.50,
    "grid_face_margin": 0.35, "grid_enter_samples": 4, "grid_exit_samples": 2,
    "min_grid_segment_seconds": 1.20,
    "min_face_area_px": 4000, "min_area_ratio_to_max": 0.25, "min_frame_ratio": 0.15,
    "ghost_iou_threshold": 0.25, "ghost_center_dist_ratio": 0.08,
    "ghost_center_dist_broad": 0.20, "min_pair_size_ratio": 0.18,
}


class ReframeTuningConfig(BaseModel):
    sample_interval_sec: float = 0.333
    max_samples: int = 720
    face_confidence: float = 0.55
    min_face_size_ratio: float = 0.10
    max_face_size_ratio: float = 0.50
    min_separation_ratio: float = 0.05
    min_coexist_ratio: float = 0.40
    dominance_single_crop: float = 0.75
    grid_base_zoom: float = 1.08
    grid_max_zoom: float = 3.50
    grid_face_margin: float = 0.35
    grid_enter_samples: int = 4
    grid_exit_samples: int = 2
    min_grid_segment_seconds: float = 1.20
    min_face_area_px: int = 4000
    min_area_ratio_to_max: float = 0.25
    min_frame_ratio: float = 0.15
    ghost_iou_threshold: float = 0.25
    ghost_center_dist_ratio: float = 0.08
    ghost_center_dist_broad: float = 0.20
    min_pair_size_ratio: float = 0.18


def _ensure_reframe_tuning_table():
    """Ensure reframe_tuning_configs table exists."""
    conn = get_dict_connection()
    try:
        conn.execute("""
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
        conn.execute("INSERT OR IGNORE INTO reframe_tuning_configs (user_id) VALUES (NULL)")

        # Fix: Clean up duplicate NULL rows (caused by SQLite NULL conflict bug)
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM reframe_tuning_configs 
            WHERE user_id IS NULL 
            AND id NOT IN (SELECT MAX(id) FROM reframe_tuning_configs WHERE user_id IS NULL)
        """)
        if cur.rowcount > 0:
            conn.commit()
            print(f"  [CLEANUP] Removed {cur.rowcount} duplicate global config rows")

        conn.commit()
    finally:
        conn.close()

_ensure_reframe_tuning_table()


def get_reframe_tuning(user_id: int | None = None) -> dict:
    """Load reframe tuning config from DB. Lookup: user-specific → global → defaults."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        if user_id is not None:
            cur.execute("SELECT * FROM reframe_tuning_configs WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
            row = cur.fetchone()
            if row:
                return {k: row[k] for k in REFRAME_TUNING_COLUMNS}
        cur.execute("SELECT * FROM reframe_tuning_configs WHERE user_id IS NULL ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            return {k: row[k] for k in REFRAME_TUNING_COLUMNS}
        return dict(REFRAME_TUNING_DEFAULTS)
    finally:
        conn.close()


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
            llm_provider=settings.LLM_PROVIDER,
            nine_router_model=settings.NINE_ROUTER_PASS2_MODEL or settings.nine_router_model,
            force_v2_pipeline=settings.FORCE_V2_PIPELINE,
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


@router.get("/reframe-tuning")
async def get_reframe_tuning_endpoint(user: CurrentUser = Depends(get_current_user)):
    """Get reframe tuning config. Superadmin sees global; regular users see their override or global."""
    target_user_id = None if user.is_superadmin else user.id
    config = get_reframe_tuning(target_user_id)
    return {"success": True, "data": config, "is_global": target_user_id is None}


@router.put("/reframe-tuning")
async def update_reframe_tuning_endpoint(body: ReframeTuningConfig, user: CurrentUser = Depends(get_current_user)):
    """Update reframe tuning config. Superadmin updates global; regular users update their own override."""
    if not user.is_superadmin and not getattr(user, "is_premium", False):
        raise HTTPException(status_code=403, detail="Premium required to tune reframe settings")

    target_user_id = None if user.is_superadmin else user.id
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        values = [getattr(body, c) for c in REFRAME_TUNING_COLUMNS]

        # SQLite: NULL != NULL so ON CONFLICT(user_id) doesn't work for global config.
        # Use explicit check-then-update/insert instead.
        if target_user_id is None:
            cur.execute("SELECT id FROM reframe_tuning_configs WHERE user_id IS NULL LIMIT 1")
        else:
            cur.execute("SELECT id FROM reframe_tuning_configs WHERE user_id = ? LIMIT 1", (target_user_id,))

        existing = cur.fetchone()

        if existing:
            # UPDATE existing row
            update_set = ", ".join([f"{c} = ?" for c in REFRAME_TUNING_COLUMNS])
            if target_user_id is None:
                cur.execute(
                    f"UPDATE reframe_tuning_configs SET {update_set}, updated_at = datetime('now') WHERE user_id IS NULL",
                    values,
                )
            else:
                cur.execute(
                    f"UPDATE reframe_tuning_configs SET {update_set}, updated_at = datetime('now') WHERE user_id = ?",
                    values + [target_user_id],
                )
        else:
            # INSERT new row
            cols = ", ".join(REFRAME_TUNING_COLUMNS)
            placeholders = ", ".join(["?"] * len(REFRAME_TUNING_COLUMNS))
            cur.execute(
                f"INSERT INTO reframe_tuning_configs (user_id, {cols}) VALUES (?, {placeholders})",
                [target_user_id] + values,
            )

        conn.commit()
        return {"success": True, "message": "Reframe tuning saved"}
    finally:
        conn.close()


@router.post("/reframe-tuning/reset")
async def reset_reframe_tuning_endpoint(user: CurrentUser = Depends(get_current_user)):
    """Reset reframe tuning to defaults. Superadmin resets global; users reset their override."""
    if not user.is_superadmin and not getattr(user, "is_premium", False):
        raise HTTPException(status_code=403, detail="Premium required to reset reframe settings")

    target_user_id = None if user.is_superadmin else user.id
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM reframe_tuning_configs WHERE user_id IS ?", (target_user_id,))
        cols = ", ".join(REFRAME_TUNING_COLUMNS)
        placeholders = ", ".join(["?"] * len(REFRAME_TUNING_COLUMNS))
        values = [REFRAME_TUNING_DEFAULTS[c] for c in REFRAME_TUNING_COLUMNS]
        cur.execute(
            f"INSERT INTO reframe_tuning_configs (user_id, {cols}) VALUES (?, {placeholders})",
            [target_user_id] + values,
        )
        conn.commit()
        return {"success": True, "message": "Reframe tuning reset to defaults", "data": dict(REFRAME_TUNING_DEFAULTS)}
    finally:
        conn.close()


# ─── Model Status Endpoint ────────────────────────────────────────────────────

@router.get("/models")
async def get_model_status(user: CurrentUser = Depends(get_current_user)):
    """Get real-time status of all LLM/API models used in pipeline."""
    from src.infrastructure.model_status import ModelStatusTracker
    tracker = ModelStatusTracker()
    return {
        "success": True,
        "models": tracker.get_all_status(),
    }
