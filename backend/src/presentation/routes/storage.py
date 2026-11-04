"""Storage management API — Thoroughly clear all processing data, video files, footages, thumbnails, DB job records, and MinIO objects."""
import logging
import os
import shutil

from fastapi import APIRouter, Depends, HTTPException

from src.config import settings
from src.infrastructure.db_connection import get_dict_connection
from src.presentation.auth_deps import CurrentUser, get_current_user

router = APIRouter(prefix="/storage", tags=["storage"])
logger = logging.getLogger(__name__)

# Explicit Safety Blocklist: NEVER delete accounts, credentials, presets, styles, or configuration under any circumstances
PROTECTED_TABLES = {
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
}


@router.post("/clear")
async def clear_processing_data(user: CurrentUser = Depends(get_current_user)):
    """Clear all processing artifacts, temporary video files, AI Video Generator assets,

    AI Image Studio assets, analysis cache, downloaded footage, DB job records, and MinIO objects.
    Superadmin only.
    """
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin access required")

    removed_dirs = []
    removed_files_count = 0
    errors = []

    # 1. Resolve all relevant base directories (cwd, backend dir, repo root)
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    repo_root = os.path.dirname(backend_dir) if os.path.basename(backend_dir) == "backend" else backend_dir
    cwd_dir = os.path.abspath(os.getcwd())

    base_dirs = list(dict.fromkeys([cwd_dir, backend_dir, repo_root]))

    # Target subdirectory names to thoroughly purge
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
        "data/asset_cache",
    ]

    target_paths = set()
    for base in base_dirs:
        for sub in sub_targets:
            target_paths.add(os.path.realpath(os.path.join(base, sub)))

    # Also include configured settings dirs
    for cfg_dir in [
        getattr(settings, "OUTPUT_DIR", ""),
        getattr(settings, "DOWNLOAD_DIR", ""),
        getattr(settings, "VIDEO_GEN_OUTPUT_DIR", ""),
        getattr(settings, "ASSET_CACHE_DIR", ""),
        getattr(settings, "WAV_DIR", ""),
    ]:
        if cfg_dir:
            target_paths.add(os.path.realpath(cfg_dir))

    for dir_path in sorted(target_paths):
        if not os.path.exists(dir_path):
            continue
        try:
            for _, _, files in os.walk(dir_path):
                removed_files_count += len(files)
            shutil.rmtree(dir_path, ignore_errors=True)
            removed_dirs.append(dir_path)
        except Exception as e:
            errors.append(f"dir '{dir_path}': {e}")

    # 2. Purge Any Temp Working Folders & Files Inside tmp/ Roots
    for base in base_dirs:
        tmp_root = os.path.realpath(os.path.join(base, "tmp"))
        if not os.path.exists(tmp_root):
            continue
        try:
            for entry in os.listdir(tmp_root):
                entry_path = os.path.join(tmp_root, entry)
                if os.path.isdir(entry_path):
                    # Purge subdirectories matching processing prefixes
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

    # 3. Re-create clean essential empty directories
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

    # 4. Clear Job & Processing Records from Database
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
    db_deleted_counts = {}
    total_db_rows_deleted = 0

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = set(r["name"] if isinstance(r, dict) else r[0] for r in cur.fetchall())

        for tbl in tables_to_clear:
            if tbl in PROTECTED_TABLES:
                logger.warning(f"[storage] Safety blocked attempt to clear protected table: {tbl}")
                continue
            if tbl in existing_tables:
                try:
                    cur.execute(f"DELETE FROM {tbl}")
                    count = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
                    db_deleted_counts[tbl] = count
                    total_db_rows_deleted += count
                    # Reset sqlite autoincrement sequence
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
            logger.warning(f"VACUUM warning: {e}")

    except Exception as e:
        errors.append(f"db transaction: {e}")
    finally:
        conn.close()

    # 5. Clear ALL Objects in the MinIO Bucket
    minio_deleted = 0
    bucket_name = getattr(settings, "MINIO_BUCKET", "") or "cliperhub"
    try:
        from src.infrastructure.minio_service import get_minio_service
        minio_deleted = get_minio_service().clear_bucket()
        removed_dirs.append(f"minio:{bucket_name}")
    except Exception as e:
        logger.warning(f"[storage] MinIO clear failed or unreachable: {e}")
        errors.append(f"MinIO ({bucket_name}): {e}")

    logger.info(
        f"Storage fully cleared by superadmin {user.id}: "
        f"db_rows={total_db_rows_deleted}, files={removed_files_count}, "
        f"minio_objs={minio_deleted}, dirs={len(removed_dirs)}, errors={errors}"
    )

    msg_summary = (
        f"Berhasil membersihkan {total_db_rows_deleted} riwayat/job di database, "
        f"{removed_files_count} file media lokal, dan {minio_deleted} objek MinIO ({bucket_name})."
    )
    if errors:
        msg_summary += f" Catatan: {'; '.join(errors)}"

    success = (len(errors) == 0) or (total_db_rows_deleted > 0 or removed_files_count > 0 or minio_deleted > 0)

    return {
        "success": success,
        "message": msg_summary,
        "details": {
            "total_db_rows_deleted": total_db_rows_deleted,
            "db_deleted_by_table": db_deleted_counts,
            "local_files_deleted": removed_files_count,
            "minio_objects_deleted": minio_deleted,
            "dirs_cleared": removed_dirs,
            "errors": errors,
        },
    }
