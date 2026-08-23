"""Settings API routes — user preferences and system configuration.

Endpoints:
- GET  /api/settings           — Get current user settings
- PUT  /api/settings           — Update user settings
- GET  /api/settings/system    — Get system info (admin only)
"""
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.config import settings
from src.infrastructure.db_connection import get_dict_connection
from src.presentation.auth_deps import CurrentUser, get_current_user, require_superadmin

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
TEST_SCRIPT_PATH = PROJECT_ROOT / "test.sh"
TEST_LOG_PATH = PROJECT_ROOT / "logs" / "test.log"
TEST_STATUS_PATH = PROJECT_ROOT / "logs" / "test-status.json"
TEST_VIDEO_PATH = PROJECT_ROOT / "clip_test_final.mp4"
MAX_TEST_LOG_BYTES = 200_000


def _read_test_status() -> dict:
    """Read test status defensively; test.sh writes this file atomically."""
    default = {
        "status": "idle",
        "stage": "not_started",
        "message": "No test run has been started",
        "log_available": TEST_LOG_PATH.is_file(),
        "video_available": TEST_VIDEO_PATH.is_file(),
        "deploy_requested": False,
    }
    if not TEST_STATUS_PATH.is_file():
        return default
    try:
        data = json.loads(TEST_STATUS_PATH.read_text(encoding="utf-8"))
        return {**default, **data} if isinstance(data, dict) else default
    except (OSError, json.JSONDecodeError):
        logger.warning("Unable to read test status file", exc_info=True)
        return default


def _read_test_log_tail() -> str:
    """Return a bounded UTF-8 tail so a large log cannot exhaust the API."""
    if not TEST_LOG_PATH.is_file():
        return ""
    try:
        with TEST_LOG_PATH.open("rb") as log_file:
            log_file.seek(0, os.SEEK_END)
            size = log_file.tell()
            log_file.seek(max(0, size - MAX_TEST_LOG_BYTES))
            content = log_file.read().decode("utf-8", errors="replace")
        return content if size <= MAX_TEST_LOG_BYTES else "[... log truncated ...]\n" + content
    except OSError:
        logger.warning("Unable to read test log", exc_info=True)
        return ""


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


# ─── Pre-deployment test gate (superadmin only) ───────────────────────────────

@router.post("/test-run", status_code=202)
async def start_test_run(user: CurrentUser = Depends(require_superadmin())):
    """Start test.sh without deployment; execution continues after this request."""
    current = _read_test_status()
    if current.get("status") in {"running", "deploying"}:
        pid = current.get("pid")
        if isinstance(pid, int):
            try:
                os.kill(pid, 0)
                raise HTTPException(status_code=409, detail="A test run is already active")
            except ProcessLookupError:
                pass
            except PermissionError:
                raise HTTPException(status_code=409, detail="A test run is already active")

    if not TEST_SCRIPT_PATH.is_file():
        raise HTTPException(status_code=503, detail="test.sh was not found on the server")

    TEST_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    initial_status = {
        "status": "running",
        "stage": "initializing",
        "message": "Starting test process",
        "log_available": TEST_LOG_PATH.is_file(),
        "video_available": TEST_VIDEO_PATH.is_file(),
        "deploy_requested": False,
    }
    try:
        temp_path = TEST_STATUS_PATH.with_suffix(".json.api.tmp")
        temp_path.write_text(json.dumps(initial_status), encoding="utf-8")
        os.replace(temp_path, TEST_STATUS_PATH)
        process = subprocess.Popen(
            ["bash", str(TEST_SCRIPT_PATH), "--no-deploy"],
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        initial_status["pid"] = process.pid
        initial_status["message"] = "Test process started"
        # Persist the PID only if test.sh has not already advanced the status.
        # This prevents a very fast shell failure from being overwritten as running.
        persisted = json.loads(TEST_STATUS_PATH.read_text(encoding="utf-8"))
        if persisted.get("message") == "Starting test process" and "pid" not in persisted:
            temp_path.write_text(json.dumps(initial_status), encoding="utf-8")
            os.replace(temp_path, TEST_STATUS_PATH)
    except OSError as exc:
        logger.exception("Unable to start test.sh")
        raise HTTPException(status_code=500, detail=f"Unable to start tests: {exc}")

    return {"success": True, "data": initial_status}


@router.get("/test-run/status")
async def get_test_run_status(user: CurrentUser = Depends(require_superadmin())):
    """Return current state and the bounded tail of the console log."""
    status_data = _read_test_status()
    if TEST_VIDEO_PATH.is_file():
        status_data["video_version"] = int(TEST_VIDEO_PATH.stat().st_mtime)
    return {"success": True, "data": status_data, "log": _read_test_log_tail()}


@router.get("/test-run/video")
async def get_test_run_video(user: CurrentUser = Depends(require_superadmin())):
    """Return the latest smoke-test output for authenticated preview."""
    if not TEST_VIDEO_PATH.is_file():
        raise HTTPException(status_code=404, detail="clip_test_final.mp4 is not available")
    return FileResponse(
        TEST_VIDEO_PATH,
        media_type="video/mp4",
        filename="clip_test_final.mp4",
        headers={"Cache-Control": "no-store"},
    )


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
        try:
            conn.execute("ALTER TABLE user_settings ADD COLUMN broll_motion_style TEXT")
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
    "dominance_single_crop": 0.75, "grid_base_zoom": 1.08, "grid_max_zoom": 2.20,
    "grid_face_margin": 0.35, "grid_enter_samples": 9, "grid_exit_samples": 6,
    "min_grid_segment_seconds": 3.0,
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
    grid_max_zoom: float = 2.20
    grid_face_margin: float = 0.35
    grid_enter_samples: int = 9
    grid_exit_samples: int = 6
    min_grid_segment_seconds: float = 3.0
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

        # Fix: Update stale DEFAULT 0.20 → 0.05 for min_separation_ratio
        # The original migration/schema used DEFAULT 0.20 which is too strict for
        # face-to-face podcast setups. Fix ANY value higher than 0.05.
        cur.execute("""
            UPDATE reframe_tuning_configs
            SET min_separation_ratio = 0.05, updated_at = datetime('now')
            WHERE min_separation_ratio > 0.05
        """)
        if cur.rowcount > 0:
            conn.commit()
            print(f"  [FIX] Updated {cur.rowcount} row(s): min_separation_ratio → 0.05")

        # Fix: Update stale grid_max_zoom → 2.20
        cur.execute("""
            UPDATE reframe_tuning_configs
            SET grid_max_zoom = 2.20, updated_at = datetime('now')
            WHERE grid_max_zoom != 2.20
        """)
        if cur.rowcount > 0:
            conn.commit()
            print(f"  [FIX] Updated {cur.rowcount} row(s): grid_max_zoom → 2.20")

        # Fix: min grid segment 3s + enter/exit hysteresis (stop single↔grid flicker)
        cur.execute("""
            UPDATE reframe_tuning_configs
            SET min_grid_segment_seconds = 3.0,
                grid_enter_samples = 9,
                grid_exit_samples = 6,
                updated_at = datetime('now')
            WHERE min_grid_segment_seconds < 3.0
               OR grid_enter_samples < 9
               OR grid_exit_samples < 6
        """)
        if cur.rowcount > 0:
            conn.commit()
            print(
                f"  [FIX] Updated {cur.rowcount} row(s): "
                f"min_grid_segment=3.0s enter=9 exit=6"
            )

        conn.commit()
    finally:
        conn.close()

_ensure_reframe_tuning_table()


# ─── Object Image Overlay Config (noun → photo card) ─────────────────────────

OBJECT_OVERLAY_COLUMNS = [
    "enabled", "max_per_clip", "box_size_ratio", "corner_radius",
    "position", "animation", "duration_sec", "margin_ratio",
    "text_color", "bg_color", "border_color", "font_scale",
    "opacity", "min_relevance", "show_label",
]

OBJECT_OVERLAY_DEFAULTS = {
    "enabled": 1,
    "max_per_clip": 6,
    "box_size_ratio": 0.28,
    "corner_radius": 18,
    "position": "top_right",
    "animation": "slide_right",
    "duration_sec": 2.4,
    "margin_ratio": 0.04,
    "text_color": "255,255,255",
    "bg_color": "20,20,24",
    "border_color": "255,255,255",
    "font_scale": 0.55,
    "opacity": 0.95,
    "min_relevance": 0.35,
    "show_label": 1,
}


class ObjectOverlayConfig(BaseModel):
    enabled: bool = True
    max_per_clip: int = 6
    box_size_ratio: float = 0.28
    corner_radius: int = 18
    position: str = "top_right"
    animation: str = "slide_right"
    duration_sec: float = 2.4
    margin_ratio: float = 0.04
    text_color: str = "255,255,255"
    bg_color: str = "20,20,24"
    border_color: str = "255,255,255"
    font_scale: float = 0.55
    opacity: float = 0.95
    min_relevance: float = 0.35
    show_label: bool = True


def _ensure_object_overlay_table():
    conn = get_dict_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS object_overlay_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                max_per_clip INTEGER NOT NULL DEFAULT 3,
                box_size_ratio REAL NOT NULL DEFAULT 0.28,
                corner_radius INTEGER NOT NULL DEFAULT 18,
                position TEXT NOT NULL DEFAULT 'top_right',
                animation TEXT NOT NULL DEFAULT 'slide_right',
                duration_sec REAL NOT NULL DEFAULT 2.4,
                margin_ratio REAL NOT NULL DEFAULT 0.04,
                text_color TEXT NOT NULL DEFAULT '255,255,255',
                bg_color TEXT NOT NULL DEFAULT '20,20,24',
                border_color TEXT NOT NULL DEFAULT '255,255,255',
                font_scale REAL NOT NULL DEFAULT 0.55,
                opacity REAL NOT NULL DEFAULT 0.95,
                min_relevance REAL NOT NULL DEFAULT 0.35,
                show_label INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        # single global row (user_id NULL) — no UNIQUE on NULL, so check first
        cur = conn.execute(
            "SELECT id FROM object_overlay_configs WHERE user_id IS NULL ORDER BY id DESC LIMIT 1"
        )
        if not cur.fetchone():
            cols = ", ".join(OBJECT_OVERLAY_COLUMNS)
            placeholders = ", ".join(["?"] * len(OBJECT_OVERLAY_COLUMNS))
            values = [OBJECT_OVERLAY_DEFAULTS[c] for c in OBJECT_OVERLAY_COLUMNS]
            conn.execute(
                f"INSERT INTO object_overlay_configs (user_id, {cols}) VALUES (NULL, {placeholders})",
                values,
            )
        conn.execute(
            """
            DELETE FROM object_overlay_configs
            WHERE user_id IS NULL
              AND id NOT IN (SELECT MAX(id) FROM object_overlay_configs WHERE user_id IS NULL)
            """
        )
        conn.commit()
    finally:
        conn.close()


_ensure_object_overlay_table()


def get_object_overlay_config(user_id: int | None = None) -> dict:
    """user → global → defaults. Bools as Python bool."""
    from src.infrastructure.object_image_overlay import normalise_object_overlay_style

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        row = None
        if user_id is not None:
            cur.execute(
                "SELECT * FROM object_overlay_configs WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
        if not row:
            cur.execute(
                "SELECT * FROM object_overlay_configs WHERE user_id IS NULL ORDER BY id DESC LIMIT 1"
            )
            row = cur.fetchone()
        raw = dict(OBJECT_OVERLAY_DEFAULTS)
        if row:
            for k in OBJECT_OVERLAY_COLUMNS:
                if k in row.keys() and row[k] is not None:
                    raw[k] = row[k]
        # int flags → bool for API
        raw["enabled"] = bool(int(raw.get("enabled", 1)))
        raw["show_label"] = bool(int(raw.get("show_label", 1)))
        return normalise_object_overlay_style(raw)
    finally:
        conn.close()


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


@router.get("/render-engines")
async def get_render_engines_catalogue(user: CurrentUser = Depends(get_current_user)):
    """Remotion vs HyperFrames notes + HF hook/subtitle/polish template ids."""
    from src.infrastructure.hf_style_catalog import catalogue
    from src.infrastructure.hyperframes_adapter import get_hyperframes_adapter

    cat = catalogue()
    live: list[str] = []
    try:
        live = await get_hyperframes_adapter().list_templates()
    except Exception:
        live = []
    return {
        "success": True,
        "data": {
            **cat,
            "live_templates": live,
            "default_engine": "remotion",
        },
    }


@router.get("/stack")
async def get_production_stack_status(user: CurrentUser = Depends(get_current_user)):
    """Local==prod stack readiness: 9router, remotion, hyperframes, hermes flags."""
    from src.config import settings as app_settings
    from src.infrastructure.hyperframes_adapter import get_hyperframes_adapter

    hf = get_hyperframes_adapter()
    hf_health = await hf.health()
    remotion_ok = False
    remotion_err = None
    try:
        import aiohttp
        from aiohttp import ClientTimeout
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=3)) as s:
            async with s.get(f"{app_settings.REMOTION_SERVER_URL.rstrip('/')}/health") as r:
                remotion_ok = r.status < 400
    except Exception as e:
        remotion_err = str(e)

    nine_ok = False
    try:
        import aiohttp
        from aiohttp import ClientTimeout
        base = (app_settings.NINE_ROUTER_BASE_URL or "http://127.0.0.1:20128/v1").rstrip("/")
        root = base[:-3] if base.endswith("/v1") else base
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=3)) as s:
            async with s.get(root) as r:
                nine_ok = r.status < 500
    except Exception:
        nine_ok = False

    hermes_home = app_settings.HERMES_HOME or os.path.expanduser("~/.hermes")
    return {
        "success": True,
        "data": {
            "nine_router": {
                "ok": nine_ok,
                "base_url": app_settings.NINE_ROUTER_BASE_URL,
                "model": app_settings.NINE_ROUTER_MODEL,
                "provider": app_settings.LLM_PROVIDER,
            },
            "remotion": {
                "enabled": bool(app_settings.USE_REMOTION),
                "ok": remotion_ok,
                "url": app_settings.REMOTION_SERVER_URL,
                "role": "hook+subtitle when selected; canvas/AI text",
                "error": remotion_err,
            },
            "hyperframes": {
                "enabled": bool(app_settings.HYPERFRAMES_ENABLED),
                "url": app_settings.HYPERFRAMES_SERVER_URL,
                "template": app_settings.HYPERFRAMES_DEFAULT_TEMPLATE,
                "health": hf_health,
                "role": "hook+subtitle fixed styles; optional lower-third polish",
            },
            "hermes": {
                "enabled": bool(app_settings.HERMES_ENABLED),
                "bin": app_settings.HERMES_BIN,
                "home": hermes_home,
                "config_exists": os.path.isfile(os.path.join(hermes_home, "config.yaml")),
                "role": "creative/template author; not per-clip batch",
            },
            "object_overlay": get_object_overlay_config(
                None if user.is_superadmin else user.id
            ),
            "hyperframes_db": __import__(
                "src.infrastructure.hyperframes_config", fromlist=["get_hyperframes_config"]
            ).get_hyperframes_config(None if user.is_superadmin else user.id),
        },
    }


@router.get("/object-overlay")
async def get_object_overlay_endpoint(user: CurrentUser = Depends(get_current_user)):
    """Get object image+text overlay style (DB-backed)."""
    target = None if user.is_superadmin else user.id
    return {
        "success": True,
        "data": get_object_overlay_config(target),
        "is_global": target is None,
    }


@router.put("/object-overlay")
async def update_object_overlay_endpoint(
    body: ObjectOverlayConfig,
    user: CurrentUser = Depends(get_current_user),
):
    """Save object overlay style. Superadmin = global; others = per-user."""
    if not user.is_superadmin and not getattr(user, "is_premium", False):
        raise HTTPException(status_code=403, detail="Premium required to tune object overlay")

    target_user_id = None if user.is_superadmin else user.id
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        values = []
        for c in OBJECT_OVERLAY_COLUMNS:
            v = getattr(body, c)
            if c in ("enabled", "show_label"):
                values.append(1 if v else 0)
            else:
                values.append(v)

        if target_user_id is None:
            cur.execute("SELECT id FROM object_overlay_configs WHERE user_id IS NULL LIMIT 1")
        else:
            cur.execute(
                "SELECT id FROM object_overlay_configs WHERE user_id = ? LIMIT 1",
                (target_user_id,),
            )
        existing = cur.fetchone()
        if existing:
            update_set = ", ".join([f"{c} = ?" for c in OBJECT_OVERLAY_COLUMNS])
            if target_user_id is None:
                cur.execute(
                    f"UPDATE object_overlay_configs SET {update_set}, updated_at = datetime('now') WHERE user_id IS NULL",
                    values,
                )
            else:
                cur.execute(
                    f"UPDATE object_overlay_configs SET {update_set}, updated_at = datetime('now') WHERE user_id = ?",
                    values + [target_user_id],
                )
        else:
            cols = ", ".join(OBJECT_OVERLAY_COLUMNS)
            placeholders = ", ".join(["?"] * len(OBJECT_OVERLAY_COLUMNS))
            cur.execute(
                f"INSERT INTO object_overlay_configs (user_id, {cols}) VALUES (?, {placeholders})",
                [target_user_id] + values,
            )
        conn.commit()
        return {"success": True, "message": "Object overlay settings saved", "data": body.model_dump()}
    finally:
        conn.close()


@router.post("/object-overlay/reset")
async def reset_object_overlay_endpoint(user: CurrentUser = Depends(get_current_user)):
    if not user.is_superadmin and not getattr(user, "is_premium", False):
        raise HTTPException(status_code=403, detail="Premium required to reset object overlay")
    target_user_id = None if user.is_superadmin else user.id
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM object_overlay_configs WHERE user_id IS ?", (target_user_id,))
        cols = ", ".join(OBJECT_OVERLAY_COLUMNS)
        placeholders = ", ".join(["?"] * len(OBJECT_OVERLAY_COLUMNS))
        values = [OBJECT_OVERLAY_DEFAULTS[c] for c in OBJECT_OVERLAY_COLUMNS]
        cur.execute(
            f"INSERT INTO object_overlay_configs (user_id, {cols}) VALUES (?, {placeholders})",
            [target_user_id] + values,
        )
        conn.commit()
        return {
            "success": True,
            "message": "Object overlay reset",
            "data": get_object_overlay_config(target_user_id),
        }
    finally:
        conn.close()


# ─── HyperFrames Hook & Polish Config Endpoints ──────────────────────────────

@router.get("/hyperframes")
async def get_hyperframes_endpoint(user: CurrentUser = Depends(get_current_user)):
    """Get hyperframes hook & polish settings (DB-backed)."""
    from src.infrastructure.hyperframes_config import get_hyperframes_config
    from src.infrastructure.hf_style_catalog import catalogue

    target = None if user.is_superadmin else user.id
    cfg = get_hyperframes_config(target)
    cat = catalogue()
    return {
        "success": True,
        "data": cfg,
        "catalogue": cat,
        "is_global": target is None,
    }


class HyperFramesUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[str] = None  # "auto" or "manual"
    default_template: Optional[str] = None
    position: Optional[str] = None


@router.put("/hyperframes")
async def update_hyperframes_endpoint(
    req: HyperFramesUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update hyperframes settings (DB-backed)."""
    from src.infrastructure.hyperframes_config import (
        ensure_hyperframes_table,
        get_hyperframes_config,
        HYPERFRAMES_COLUMNS,
        HYPERFRAMES_DEFAULTS,
    )

    if not user.is_superadmin and not getattr(user, "is_premium", False):
        raise HTTPException(status_code=403, detail="Premium required to customize HyperFrames")

    ensure_hyperframes_table()
    target_user_id = None if user.is_superadmin else user.id
    current = get_hyperframes_config(target_user_id)
    updates = req.model_dump(exclude_unset=True)

    for k, v in updates.items():
        if k in HYPERFRAMES_COLUMNS:
            current[k] = v

    if "enabled" in current:
        current["enabled"] = 1 if current["enabled"] else 0

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        if target_user_id is None:
            cur.execute("SELECT id FROM hyperframes_configs WHERE user_id IS NULL LIMIT 1")
        else:
            cur.execute("SELECT id FROM hyperframes_configs WHERE user_id = ? LIMIT 1", (target_user_id,))
        row = cur.fetchone()

        update_set = ", ".join([f"{c} = ?" for c in HYPERFRAMES_COLUMNS])
        vals = [current.get(c, HYPERFRAMES_DEFAULTS.get(c)) for c in HYPERFRAMES_COLUMNS]

        if row:
            if target_user_id is None:
                cur.execute(
                    f"UPDATE hyperframes_configs SET {update_set}, updated_at = datetime('now') WHERE user_id IS NULL",
                    vals,
                )
            else:
                cur.execute(
                    f"UPDATE hyperframes_configs SET {update_set}, updated_at = datetime('now') WHERE user_id = ?",
                    vals + [target_user_id],
                )
        else:
            cols = ", ".join(HYPERFRAMES_COLUMNS)
            placeholders = ", ".join(["?"] * len(HYPERFRAMES_COLUMNS))
            cur.execute(
                f"INSERT INTO hyperframes_configs (user_id, {cols}) VALUES (?, {placeholders})",
                [target_user_id] + vals,
            )
        conn.commit()
        return {
            "success": True,
            "message": "HyperFrames settings updated",
            "data": get_hyperframes_config(target_user_id),
        }
    finally:
        conn.close()


@router.post("/hyperframes/reset")
async def reset_hyperframes_endpoint(user: CurrentUser = Depends(get_current_user)):
    """Reset hyperframes settings to defaults."""
    from src.infrastructure.hyperframes_config import (
        ensure_hyperframes_table,
        get_hyperframes_config,
        HYPERFRAMES_COLUMNS,
        HYPERFRAMES_DEFAULTS,
    )

    if not user.is_superadmin and not getattr(user, "is_premium", False):
        raise HTTPException(status_code=403, detail="Premium required to reset HyperFrames")

    ensure_hyperframes_table()
    target_user_id = None if user.is_superadmin else user.id
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM hyperframes_configs WHERE user_id IS ?", (target_user_id,))
        cols = ", ".join(HYPERFRAMES_COLUMNS)
        placeholders = ", ".join(["?"] * len(HYPERFRAMES_COLUMNS))
        values = [HYPERFRAMES_DEFAULTS[c] for c in HYPERFRAMES_COLUMNS]
        cur.execute(
            f"INSERT INTO hyperframes_configs (user_id, {cols}) VALUES (?, {placeholders})",
            [target_user_id] + values,
        )
        conn.commit()
        return {
            "success": True,
            "message": "HyperFrames settings reset",
            "data": get_hyperframes_config(target_user_id),
        }
    finally:
        conn.close()


# ─── Dynamic Database System Config with RBAC ─────────────────────────────────

class SystemConfigUpdateRequest(BaseModel):
    settings: Dict[str, Any] = Field(default_factory=dict)


class SystemConfigResetRequest(BaseModel):
    key: Optional[str] = None


@router.get("/system-config")
async def get_system_config_endpoint(
    unmask: bool = False,
    user: CurrentUser = Depends(get_current_user),
):
    """Retrieve dynamic system settings filtered by current user role."""
    from src.infrastructure.system_config_store import (
        get_all_settings_for_role,
        ROLE_LEVELS,
    )

    user_role = getattr(user, "role", "viewer") or "viewer"
    can_unmask = user.is_superadmin or ROLE_LEVELS.get(user_role.lower(), 1) >= 3

    items = get_all_settings_for_role(user_role, unmask_secrets=(unmask and can_unmask))
    return {
        "success": True,
        "role": user_role,
        "can_edit_secrets": can_unmask,
        "count": len(items),
        "data": items,
    }


@router.put("/system-config")
async def update_system_config_endpoint(
    req: SystemConfigUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Bulk update dynamic system settings with role permission validation."""
    from src.infrastructure.system_config_store import (
        SYSTEM_SETTINGS_METADATA,
        ROLE_LEVELS,
        bulk_set_system_settings,
    )

    user_role = getattr(user, "role", "viewer") or "viewer"
    user_level = ROLE_LEVELS.get(user_role.lower(), 1)

    # Validate permissions for each requested key
    denied_keys = []
    allowed_updates = {}

    for k, v in req.settings.items():
        if k not in SYSTEM_SETTINGS_METADATA:
            continue
        req_role = SYSTEM_SETTINGS_METADATA[k]["min_role"]
        req_level = ROLE_LEVELS.get(req_role, 3)

        if user_level < req_level:
            denied_keys.append(k)
        else:
            # Don't update if secret is passed as masked placeholder
            if SYSTEM_SETTINGS_METADATA[k]["is_secret"] and isinstance(v, str) and ("..." in v or "******" in v):
                continue
            allowed_updates[k] = v

    if denied_keys:
        raise HTTPException(
            status_code=403,
            detail=f"Forbidden: Your role '{user_role}' cannot modify: {', '.join(denied_keys)}"
        )

    updated_count = bulk_set_system_settings(allowed_updates, user_id=user.id)
    return {
        "success": True,
        "message": f"{updated_count} system settings successfully updated",
        "updated_count": updated_count,
    }


@router.post("/system-config/reset")
async def reset_system_config_endpoint(
    req: SystemConfigResetRequest,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Reset one or all system settings to system metadata defaults (superadmin only)."""
    from src.infrastructure.system_config_store import (
        SYSTEM_SETTINGS_METADATA,
        set_system_setting,
        seed_system_settings_defaults,
    )

    if req.key:
        if req.key not in SYSTEM_SETTINGS_METADATA:
            raise HTTPException(status_code=404, detail=f"Unknown setting key '{req.key}'")
        default_val = SYSTEM_SETTINGS_METADATA[req.key]["default"]
        set_system_setting(req.key, default_val, user_id=user.id)
        return {
            "success": True,
            "message": f"Setting '{req.key}' reset to default",
            "key": req.key,
            "value": default_val,
        }

    seed_system_settings_defaults()
    return {
        "success": True,
        "message": "All system settings reset to defaults",
    }


# ─── YouTube Cookies Management Endpoints ─────────────────────────────────────

class YouTubeCookiesUpdateRequest(BaseModel):
    content: str = Field(..., description="Raw cookies.txt content in Netscape format")


def _count_valid_cookies(lines: list[str]) -> int:
    """Accurately count active cookies in Netscape format including HttpOnly entries."""
    count = 0
    for l in lines:
        s = l.strip()
        if not s:
            continue
        if s.startswith("#HttpOnly_"):
            count += 1
        elif not s.startswith("#") and ("\t" in s or " " in s):
            count += 1
    return count


@router.get("/youtube-cookies")
async def get_youtube_cookies_status(user: CurrentUser = Depends(get_current_user)):
    """Get current status and metadata of YouTube cookies.txt on the server."""
    backend_dir_cookies = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../cookies.txt")
    )
    backend_cookies = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../../cookies.txt")
    )
    root_cookies = os.path.abspath("cookies.txt")

    target_path = None
    for p in [backend_dir_cookies, backend_cookies, root_cookies]:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            target_path = p
            break

    if not target_path or not os.path.exists(target_path):
        return {
            "success": True,
            "data": {
                "exists": False,
                "size_bytes": 0,
                "line_count": 0,
                "cookie_count": 0,
                "last_modified": None,
                "path": backend_dir_cookies,
            }
        }

    try:
        stat = os.stat(target_path)
        with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        cookie_count = _count_valid_cookies(lines)

        return {
            "success": True,
            "data": {
                "exists": True,
                "size_bytes": stat.st_size,
                "line_count": len(lines),
                "cookie_count": cookie_count,
                "last_modified": stat.st_mtime,
                "path": target_path,
            }
        }
    except Exception as e:
        logger.error(f"Error reading youtube cookies status: {e}")
        return {
            "success": True,
            "data": {
                "exists": False,
                "error": str(e),
                "path": backend_dir_cookies,
            }
        }


@router.post("/youtube-cookies")
async def save_youtube_cookies(
    req: YouTubeCookiesUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Save raw cookies.txt content to server cookies file."""
    if not req.content or not req.content.strip():
        raise HTTPException(status_code=400, detail="Cookies content cannot be empty")

    cleaned_content = req.content.strip() + "\n"

    # Save to backend/cookies.txt and root cookies.txt
    backend_dir_cookies = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../cookies.txt")
    )
    backend_cookies = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../../cookies.txt")
    )
    root_cookies = os.path.abspath("cookies.txt")

    for p in [backend_dir_cookies, backend_cookies, root_cookies]:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(cleaned_content)
            try:
                os.chmod(p, 0o644)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Failed writing cookies to {p}: {e}")

    lines = cleaned_content.splitlines()
    cookie_count = _count_valid_cookies(lines)

    return {
        "success": True,
        "message": f"YouTube cookies berhasil disimpan ke server ({cookie_count} cookies aktif)",
        "data": {
            "exists": True,
            "size_bytes": len(cleaned_content.encode("utf-8")),
            "line_count": len(lines),
            "cookie_count": cookie_count,
        }
    }


@router.delete("/youtube-cookies")
async def delete_youtube_cookies(user: CurrentUser = Depends(get_current_user)):
    """Delete cookies.txt from the server."""
    backend_dir_cookies = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../cookies.txt")
    )
    backend_cookies = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../../cookies.txt")
    )
    root_cookies = os.path.abspath("cookies.txt")

    deleted = False
    for p in [backend_dir_cookies, backend_cookies, root_cookies]:
        if os.path.exists(p):
            try:
                os.remove(p)
                deleted = True
            except Exception as e:
                logger.warning(f"Failed deleting cookies from {p}: {e}")

    return {
        "success": True,
        "message": "YouTube cookies berhasil dihapus dari server" if deleted else "Tidak ada file cookies yang aktif",
    }


@router.post("/youtube-cookies/test")
async def test_youtube_cookies(user: CurrentUser = Depends(get_current_user)):
    """Test YouTube cookies by probing a video with yt-dlp."""
    import asyncio
    from src.infrastructure.downloader import _get_ytdlp_cmd, _get_cookie_args

    cookie_args = _get_cookie_args()
    if not cookie_args:
        return {
            "success": False,
            "message": "Tidak ada file cookies.txt yang aktif di server. Silakan upload cookies terlebih dahulu.",
        }

    ytdlp_cmd = _get_ytdlp_cmd()
    test_url = "https://www.youtube.com/watch?v=0CXYYF4V9WM"

    cmd = [
        ytdlp_cmd,
        "--geo-bypass",
        "--extractor-args", "youtube:player_client=web_safari,mweb,tv,ios",
        *cookie_args,
        "--dump-json",
        "--no-download",
        "--no-warnings",
        test_url,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=25)

        if proc.returncode == 0:
            data = json.loads(stdout.decode())
            title = data.get("title", "YouTube Video")
            formats = len(data.get("formats", []))
            return {
                "success": True,
                "message": f"Koneksi YouTube berhasil diverifikasi dengan cookies! ({formats} format video HD terdeteksi)",
                "title": title,
                "formats_count": formats,
            }
        else:
            err = stderr.decode().strip()
            return {
                "success": False,
                "message": f"Uji coba koneksi gagal: {err[:200]}",
            }
    except asyncio.TimeoutError:
        return {
            "success": False,
            "message": "Uji coba timeout (20 detik). Server YouTube lambat merespons.",
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error saat menguji cookies: {str(e)}",
        }


class AutoExtractCookiesRequest(BaseModel):
    browser: Optional[str] = Field(default="auto", description="Browser to extract from: auto, chrome, brave, edge, firefox, safari")


@router.post("/youtube-cookies/auto-extract")
async def auto_extract_youtube_cookies(
    req: AutoExtractCookiesRequest = AutoExtractCookiesRequest(),
    user: CurrentUser = Depends(get_current_user),
):
    """Automatically extract YouTube cookies from installed browsers using yt-dlp without any extension."""
    import asyncio
    from src.infrastructure.downloader import _get_ytdlp_cmd

    ytdlp_cmd = _get_ytdlp_cmd()

    backend_dir_cookies = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../cookies.txt")
    )
    root_cookies = os.path.abspath("cookies.txt")

    # Priority list of browsers to probe
    requested_browser = (req.browser or "auto").lower().strip()
    if requested_browser == "auto":
        browsers_to_try = ["chrome", "brave", "edge", "firefox", "safari", "chromium", "opera"]
    else:
        browsers_to_try = [requested_browser]

    test_url = "https://www.youtube.com/watch?v=0CXYYF4V9WM"
    success_browser = None
    last_err = ""

    for b in browsers_to_try:
        logger.info(f"Attempting auto-extracting YouTube cookies from browser: {b}")
        cmd = [
            ytdlp_cmd,
            "--cookies-from-browser", b,
            "--cookies", backend_dir_cookies,
            "--dump-json",
            "--no-download",
            "--no-warnings",
            test_url,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode == 0 and os.path.exists(backend_dir_cookies) and os.path.getsize(backend_dir_cookies) > 0:
                success_browser = b
                try:
                    import shutil
                    shutil.copy2(backend_dir_cookies, root_cookies)
                    os.chmod(backend_dir_cookies, 0o644)
                    os.chmod(root_cookies, 0o644)
                except Exception:
                    pass
                break
            else:
                last_err = stderr.decode().strip()
        except Exception as e:
            last_err = str(e)
            logger.debug(f"Auto-extract from {b} failed: {e}")

    if not success_browser or not os.path.exists(backend_dir_cookies):
        return {
            "success": False,
            "message": f"Gagal mengekstrak cookies otomatis dari browser ({requested_browser}): {last_err[:200] if last_err else 'Tidak ada browser aktif dengan login YouTube'}. Anda dapat mengunggah file cookies.txt secara manual.",
        }

    stat = os.stat(backend_dir_cookies)
    with open(backend_dir_cookies, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    cookie_count = sum(1 for l in lines if l.strip() and not l.strip().startswith("#"))

    return {
        "success": True,
        "message": f"Berhasil mengambil {cookie_count} cookies otomatis dari browser {success_browser.capitalize()}! YouTube session kini aktif.",
        "browser_used": success_browser,
        "data": {
            "exists": True,
            "size_bytes": stat.st_size,
            "line_count": len(lines),
            "cookie_count": cookie_count,
            "last_modified": stat.st_mtime,
            "path": backend_dir_cookies,
        }
    }
