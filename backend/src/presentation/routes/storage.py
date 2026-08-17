"""Storage management API — Thoroughly clear all processing data, video files, footages, thumbnails, DB job records, and MinIO objects."""
import glob
import logging
import os
import shutil

from fastapi import APIRouter, Depends, HTTPException

from src.config import settings
from src.infrastructure.db_connection import get_dict_connection
from src.presentation.auth_deps import CurrentUser, get_current_user

router = APIRouter(prefix="/storage", tags=["storage"])
logger = logging.getLogger(__name__)


@router.post("/clear")
async def clear_processing_data(user: CurrentUser = Depends(get_current_user)):
    """Clear all processing artifacts, temporary video files, AI Video Generator assets, analysis cache, DB jobs, and MinIO objects. Superadmin only."""
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin access required")

    removed_dirs = []
    removed_files_count = 0
    errors = []

    # 1. Target Directories to Thoroughly Purge
    target_dirs = [
        settings.OUTPUT_DIR,               # tmp/output
        settings.DOWNLOAD_DIR,             # tmp/downloads
        getattr(settings, "VIDEO_GEN_OUTPUT_DIR", "tmp/video_gen"),  # tmp/video_gen
        "tmp/video_generator",
        "tmp/footage",
        "tmp/broll",
        "tmp/cache",
        "tmp/checkpoints",
        "tmp/subtitles",
        "tmp/remotion",
        "tmp/renders",
        "tmp/analysis",
        "tmp/thumbnails",
        getattr(settings, "WAV_DIR", ""),
    ]

    for dir_path in target_dirs:
        if not dir_path or not os.path.exists(dir_path):
            continue
        try:
            # Count files before removing
            for _, _, files in os.walk(dir_path):
                removed_files_count += len(files)
            shutil.rmtree(dir_path, ignore_errors=True)
            removed_dirs.append(dir_path)
        except Exception as e:
            errors.append(f"dir '{dir_path}': {e}")

    # 2. Purge Any Temp Working Folders & Files Inside tmp/ Root
    tmp_root = "tmp"
    if os.path.exists(tmp_root):
        try:
            for entry in os.listdir(tmp_root):
                entry_path = os.path.join(tmp_root, entry)
                # Purge subdirectories matching job/clip/skia/generator prefixes
                if os.path.isdir(entry_path):
                    if any(entry.startswith(prefix) for prefix in (
                        "job_", "clip_", "skia_", "person_", "transcribe_", "silero_",
                        "remotion_", "footage_", "broll_", "video_gen", "thumb_", "analysis_"
                    )):
                        for _, _, files in os.walk(entry_path):
                            removed_files_count += len(files)
                        shutil.rmtree(entry_path, ignore_errors=True)
                        removed_dirs.append(entry_path)
                # Purge loose video, audio, image, and json artifacts inside tmp/ root
                elif os.path.isfile(entry_path):
                    ext = os.path.splitext(entry)[1].lower()
                    if ext in (
                        ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi",
                        ".wav", ".mp3", ".aac", ".flac", ".m4a", ".ogg",
                        ".png", ".jpg", ".jpeg", ".webp",
                        ".json", ".ass", ".srt", ".vtt", ".txt"
                    ) or any(entry.startswith(prefix) for prefix in ("job_", "clip_", "frame_", "thumb_", "chunk_")):
                        try:
                            os.remove(entry_path)
                            removed_files_count += 1
                        except OSError:
                            pass
        except Exception as e:
            errors.append(f"tmp_root cleanup: {e}")

    # 3. Re-create clean essential directories
    essential_dirs = [
        settings.OUTPUT_DIR,
        settings.DOWNLOAD_DIR,
        getattr(settings, "VIDEO_GEN_OUTPUT_DIR", "tmp/video_gen"),
        "tmp/cache",
        "tmp/checkpoints",
    ]
    for edir in essential_dirs:
        try:
            os.makedirs(edir, exist_ok=True)
        except Exception as e:
            errors.append(f"recreate '{edir}': {e}")

    # 4. Clear Job & Processing Records from Database
    # Tables strictly purged:
    tables_to_clear = [
        "jobs",
        "video_generator_jobs",
        "clip_plans",
        "source_assets",
        "asset_segments",
        "footage_clip_plans",
        "clip_allocations",
        "job_clip_brolls",
        "transcript_cache",
        "remotion_renders",
        "model_usage",
    ]
    db_deleted_counts = {}
    total_db_rows_deleted = 0

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        # Find existing tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = set(r["name"] if isinstance(r, dict) else r[0] for r in cur.fetchall())

        for tbl in tables_to_clear:
            if tbl in existing_tables:
                try:
                    cur.execute(f"DELETE FROM {tbl}")
                    count = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
                    db_deleted_counts[tbl] = count
                    total_db_rows_deleted += count
                except Exception as e:
                    errors.append(f"db table '{tbl}': {e}")
        conn.commit()
    except Exception as e:
        errors.append(f"db transaction: {e}")
    finally:
        conn.close()

    # 5. Clear ALL Objects in the MinIO Bucket (e.g. 'cliperhub')
    minio_deleted = 0
    try:
        from src.infrastructure.minio_service import get_minio_service
        minio_deleted = get_minio_service().clear_bucket()
        removed_dirs.append(f"minio:{getattr(settings, 'MINIO_BUCKET', 'cliperhub')}")
    except Exception as e:
        errors.append(f"minio: {e}")

    logger.info(
        f"Storage fully cleared by superadmin {user.id}: "
        f"db_rows={total_db_rows_deleted}, files={removed_files_count}, "
        f"minio_objs={minio_deleted}, dirs={removed_dirs}, errors={errors}"
    )

    return {
        "success": len(errors) == 0,
        "message": (
            f"Successfully cleared {total_db_rows_deleted} database records, "
            f"{removed_files_count} local files, and {minio_deleted} MinIO objects."
        ),
        "details": {
            "total_db_rows_deleted": total_db_rows_deleted,
            "db_deleted_by_table": db_deleted_counts,
            "local_files_deleted": removed_files_count,
            "minio_objects_deleted": minio_deleted,
            "dirs_cleared": removed_dirs,
            "errors": errors,
        },
    }
