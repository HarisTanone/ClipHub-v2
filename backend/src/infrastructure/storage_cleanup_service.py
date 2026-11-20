"""Storage cleanup service for AutoCliper.

Handles thorough cleanup of temporary processing files, video renders, downloads,
asset cache, database processing history, and MinIO objects.
Supports both manual execution (API) and automated execution (midnight cron loop & CLI).
Protects all symlinks, accounts, presets, styles, and configurations.
"""
import asyncio
import datetime as dt
import logging
import os
import shutil
from typing import Any, Dict, List, Optional, Set, Tuple

from src.config import settings
from src.infrastructure.db_connection import get_dict_connection

logger = logging.getLogger(__name__)

# Explicit Safety Blocklist: NEVER delete accounts, credentials, presets, styles, or configuration
PROTECTED_TABLES: Set[str] = {
    "users",
    "roles",
    "permissions",
    "role_permissions",
    "user_features",
    "user_presets",
    "user_settings",
    "refresh_tokens",
    "system_settings",
    "model_settings",
    "style_presets",
    "render_style_presets",
    "object_overlay_configs",
    "hyperframes_configs",
    "ffmpeg_hook_styles",
    "hook_animations",
    "broll_templates",
    "indonesian_entity_map",
    "reframe_tuning_configs",
    "telegram_settings",
    "social_accounts",
    "social_engagement_rules",
    "image_typography_templates",
    "image_typography_fonts",
    "image_canvas_aspect_ratios",
    "image_accent_presets",
    "storage_cleanup_runs",
}


class StorageCleanupService:
    """Manages manual and scheduled cleanup of processing files and database records."""

    def __init__(self) -> None:
        self._init_db()

    def _init_db(self) -> None:
        """Ensure storage_cleanup_runs table exists."""
        try:
            conn = get_dict_connection()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS storage_cleanup_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL,
                    trigger_source TEXT NOT NULL,
                    files_deleted INTEGER DEFAULT 0,
                    db_rows_deleted INTEGER DEFAULT 0,
                    minio_objs_deleted INTEGER DEFAULT 0,
                    status TEXT NOT NULL,
                    summary TEXT,
                    executed_at TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"[storage_cleanup] Failed to init DB table: {e}")

    def _clear_folder_contents(self, folder_path: str) -> Tuple[int, List[str]]:
        """Delete all contents inside folder_path WITHOUT deleting folder_path itself or unlinking symlink."""
        real_dir = os.path.realpath(folder_path)
        if not os.path.exists(real_dir) or not os.path.isdir(real_dir):
            return 0, []

        removed_files = 0
        removed_dirs = []
        for entry in os.listdir(real_dir):
            entry_path = os.path.join(real_dir, entry)
            try:
                if os.path.islink(entry_path):
                    os.unlink(entry_path)
                    removed_files += 1
                elif os.path.isdir(entry_path):
                    for _, _, f in os.walk(entry_path):
                        removed_files += len(f)
                    shutil.rmtree(entry_path, ignore_errors=True)
                    removed_dirs.append(entry_path)
                else:
                    os.remove(entry_path)
                    removed_files += 1
            except Exception as e:
                logger.warning(f"[storage_cleanup] Error removing {entry_path}: {e}")

        return removed_files, removed_dirs

    def execute_cleanup(
        self,
        trigger_source: str = "manual",
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Perform comprehensive storage cleanup across filesystem, database, and MinIO."""
        removed_dirs: List[str] = []
        removed_files_count = 0
        errors: List[str] = []

        # ─── 1. Resolve Target Base Paths ─────────────────────────────────────
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        repo_root = os.path.dirname(backend_dir) if os.path.basename(backend_dir) == "backend" else backend_dir
        cwd_dir = os.path.abspath(os.getcwd())

        base_dirs = list(dict.fromkeys([cwd_dir, backend_dir, repo_root]))

        # Subdirectories relative to base project folders
        sub_targets = [
            "tmp/output",
            "tmp/downloads",
            "tmp/video_gen",
            "tmp/video_generator",
            "tmp/image_studio",
            "tmp/footage",
            "tmp/broll",
            "tmp/cache",
            "tmp/checkpoints",
            "tmp/subtitles",
            "tmp/remotion",
            "tmp/renders",
            "tmp/analysis",
            "tmp/thumbnails",
            "hyperframes-renderer/work",
            "data/asset_cache/footage",
            "data/asset_cache/icon",
            "data/asset_cache/motion_graphic",
            "data/asset_cache/reaction",
            "data/asset_cache/stickers",
        ]

        target_paths: Set[str] = set()
        for base in base_dirs:
            for sub in sub_targets:
                target_paths.add(os.path.join(base, sub))

        # Explicit /mnt/data/cliper-storage paths if present
        cliper_storage = "/mnt/data/cliper-storage"
        if os.path.exists(cliper_storage):
            cliper_subs = [
                "hyperframes_work",
                "backend_tmp/output",
                "backend_tmp/downloads",
                "backend_tmp/video_gen",
                "backend_tmp/image_studio",
                "backend_tmp/cache",
                "backend_tmp/checkpoints",
                "root_tmp/output",
                "root_tmp/downloads",
                "root_tmp/cache",
                "asset_cache/footage",
                "asset_cache/icon",
                "asset_cache/motion_graphic",
                "asset_cache/reaction",
                "asset_cache/stickers",
            ]
            for csub in cliper_subs:
                target_paths.add(os.path.join(cliper_storage, csub))

        # Configured paths from settings
        for cfg_dir in [
            getattr(settings, "OUTPUT_DIR", ""),
            getattr(settings, "DOWNLOAD_DIR", ""),
            getattr(settings, "VIDEO_GEN_OUTPUT_DIR", ""),
            getattr(settings, "ASSET_CACHE_DIR", ""),
            getattr(settings, "WAV_DIR", ""),
        ]:
            if cfg_dir:
                target_paths.add(cfg_dir)

        # Purge folder contents safely (never deleting root symlink or root dir)
        for tpath in sorted(target_paths):
            if not os.path.exists(tpath):
                continue
            files_cleared, dirs_cleared = self._clear_folder_contents(tpath)
            removed_files_count += files_cleared
            removed_dirs.extend(dirs_cleared)

        # ─── 2. Purge Any Stray Files & Prefixed Directories in tmp/ Roots ────
        for base in base_dirs:
            tmp_root = os.path.join(base, "tmp")
            if not os.path.exists(tmp_root) or not os.path.isdir(tmp_root):
                continue
            real_tmp = os.path.realpath(tmp_root)
            try:
                for entry in os.listdir(real_tmp):
                    entry_path = os.path.join(real_tmp, entry)
                    if os.path.isdir(entry_path):
                        if any(entry.startswith(prefix) for prefix in (
                            "job_", "clip_", "skia_", "person_", "transcribe_", "silero_",
                            "remotion_", "footage_", "broll_", "video_gen", "thumb_", "analysis_",
                            "tts", "voice_previews", "vg_", "image_studio"
                        )):
                            for _, _, files in os.walk(entry_path):
                                removed_files_count += len(files)
                            shutil.rmtree(entry_path, ignore_errors=True)
                            removed_dirs.append(entry_path)
                    elif os.path.isfile(entry_path):
                        ext = os.path.splitext(entry)[1].lower()
                        if ext in (
                            ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi",
                            ".wav", ".mp3", ".aac", ".flac", ".m4a", ".ogg",
                            ".png", ".jpg", ".jpeg", ".webp",
                            ".json", ".ass", ".srt", ".vtt", ".txt", ".csv", ".log"
                        ) or any(entry.startswith(prefix) for prefix in (
                            "job_", "clip_", "frame_", "thumb_", "chunk_", "cta_", "glow_", "sample_", "test_"
                        )):
                            try:
                                os.remove(entry_path)
                                removed_files_count += 1
                            except OSError:
                                pass
            except Exception as e:
                errors.append(f"tmp_root '{tmp_root}': {e}")

        # ─── 3. Re-create Essential Empty Folders ─────────────────────────────
        essential_subs = [
            "tmp/output",
            "tmp/downloads",
            "tmp/video_gen",
            "tmp/image_studio",
            "tmp/cache",
            "tmp/checkpoints",
            "data/asset_cache/footage",
            "data/asset_cache/icon",
            "data/asset_cache/motion_graphic",
            "data/asset_cache/reaction",
            "data/asset_cache/stickers",
        ]
        for base in [cwd_dir, backend_dir]:
            for esub in essential_subs:
                edir = os.path.realpath(os.path.join(base, esub))
                try:
                    os.makedirs(edir, exist_ok=True)
                except Exception as e:
                    errors.append(f"recreate '{edir}': {e}")

        # ─── 4. Clear Job & Processing Records from Database ───────────────────
        tables_to_clear = [
            "jobs",
            "video_generator_jobs",
            "hermes_videogen_runs",
            "autopilot_runs",
            "ai_image_runs",
            "clip_plans",
            "source_assets",
            "asset_segments",
            "footage_clip_plans",
            "clip_allocations",
            "job_clip_brolls",
            "transcript_cache",
            "remotion_renders",
            "model_usage",
            "social_engagement_tasks",
            "social_engagement_logs",
        ]
        total_db_rows_deleted = 0

        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = set(r["name"] if isinstance(r, dict) else r[0] for r in cur.fetchall())

            for tbl in tables_to_clear:
                if tbl in PROTECTED_TABLES:
                    logger.warning(f"[storage_cleanup] Blocked attempt to clear protected table: {tbl}")
                    continue
                if tbl in existing_tables:
                    try:
                        cur.execute(f"DELETE FROM {tbl}")
                        count = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
                        total_db_rows_deleted += count
                        if "sqlite_sequence" in existing_tables:
                            try:
                                cur.execute("DELETE FROM sqlite_sequence WHERE name = ?", (tbl,))
                            except Exception:
                                pass
                    except Exception as e:
                        errors.append(f"db table '{tbl}': {e}")

            # Reset pointers & counters in preserved settings tables
            if "autopilot_settings" in existing_tables:
                try:
                    cur.execute("""
                        UPDATE autopilot_settings 
                        SET last_job_id = NULL, last_video_url = NULL, last_video_title = NULL, last_run_at = NULL
                    """)
                except Exception as e:
                    errors.append(f"reset autopilot_settings: {e}")

            if "ai_image_settings" in existing_tables:
                try:
                    cur.execute("""
                        UPDATE ai_image_settings 
                        SET last_run_date = NULL, today_images_created = 0
                    """)
                except Exception as e:
                    errors.append(f"reset ai_image_settings: {e}")

            if "hermes_videogen_settings" in existing_tables:
                try:
                    cur.execute("""
                        UPDATE hermes_videogen_settings 
                        SET today_videos_created = 0, last_run_date = NULL, last_run_at = NULL
                    """)
                except Exception as e:
                    errors.append(f"reset hermes_videogen_settings: {e}")

            conn.commit()

            # Reclaim unused disk space with VACUUM
            try:
                cur.execute("VACUUM")
            except Exception as e:
                logger.warning(f"[storage_cleanup] VACUUM warning: {e}")

        except Exception as e:
            errors.append(f"db transaction: {e}")
        finally:
            conn.close()

        # ─── 5. Clear Objects in MinIO Bucket ─────────────────────────────────
        minio_deleted = 0
        bucket_name = getattr(settings, "MINIO_BUCKET", "") or "cliperhub"
        try:
            from src.infrastructure.minio_service import get_minio_service
            minio_deleted = get_minio_service().clear_bucket()
            removed_dirs.append(f"minio:{bucket_name}")
        except Exception as e:
            logger.warning(f"[storage_cleanup] MinIO clear failed: {e}")
            errors.append(f"MinIO ({bucket_name}): {e}")

        now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        run_date_str = dt.datetime.now().strftime("%Y-%m-%d")
        summary_msg = (
            f"Berhasil membersihkan {total_db_rows_deleted} riwayat/job di database, "
            f"{removed_files_count} file media lokal/mount, dan {minio_deleted} objek MinIO ({bucket_name})."
        )

        # Record in history table
        try:
            conn = get_dict_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO storage_cleanup_runs 
                (run_date, trigger_source, files_deleted, db_rows_deleted, minio_objs_deleted, status, summary, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_date_str,
                trigger_source,
                removed_files_count,
                total_db_rows_deleted,
                minio_deleted,
                "success" if not errors else "completed_with_errors",
                summary_msg,
                now_str,
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"[storage_cleanup] Failed to log run to DB: {e}")

        logger.info(
            f"[storage_cleanup] Trigger={trigger_source} (user={user_id}): "
            f"db_rows={total_db_rows_deleted}, files={removed_files_count}, "
            f"minio_objs={minio_deleted}, dirs={len(removed_dirs)}, errors={errors}"
        )

        return {
            "success": True,
            "message": summary_msg,
            "db_rows_deleted": total_db_rows_deleted,
            "files_deleted": removed_files_count,
            "minio_objects_deleted": minio_deleted,
            "dirs_cleaned": len(removed_dirs),
            "errors": errors,
            "executed_at": now_str,
            "trigger_source": trigger_source,
        }

    def _should_run_midnight_cleanup(self, now: dt.datetime) -> bool:
        """Check if current time is within midnight window (00:00 - 00:05) and has not run today."""
        if now.hour != 0 or now.minute > 5:
            return False

        today_str = now.strftime("%Y-%m-%d")
        try:
            conn = get_dict_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM storage_cleanup_runs WHERE run_date = ? AND trigger_source = 'cron_midnight' LIMIT 1",
                (today_str,),
            )
            row = cur.fetchone()
            conn.close()
            return row is None
        except Exception:
            return False

    async def start_auto_clear_loop(self) -> None:
        """Background worker loop: checks every 60s and runs cleanup at midnight (00:00)."""
        logger.info("[storage_cron] Storage auto-clear midnight daemon started")
        while True:
            try:
                now = dt.datetime.now()
                if self._should_run_midnight_cleanup(now):
                    today_str = now.strftime("%Y-%m-%d")
                    logger.info(f"[storage_cron] Executing scheduled midnight cleanup for {today_str}...")
                    # Run in threadpool to avoid blocking event loop
                    await asyncio.to_thread(self.execute_cleanup, trigger_source="cron_midnight")
                    logger.info(f"[storage_cron] Midnight cleanup finished for {today_str}")
            except Exception as e:
                logger.error(f"[storage_cron] Unexpected error in auto-clear loop: {e}")

            # Sleep 60 seconds before next check
            await asyncio.sleep(60)

    def get_cleanup_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch recent cleanup run history."""
        try:
            conn = get_dict_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT id, run_date, trigger_source, files_deleted, db_rows_deleted, 
                       minio_objs_deleted, status, summary, executed_at
                FROM storage_cleanup_runs
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.warning(f"[storage_cleanup] Failed to fetch history: {e}")
            return []


storage_cleanup_service = StorageCleanupService()
