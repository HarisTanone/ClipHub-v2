"""Storage management API — Clear processing data (output, downloads, job records)."""
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
    """Clear all processing artifacts. Superadmin only."""
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin access required")

    removed_dirs = []
    errors = []

    # 1. Remove output directory contents
    output_dir = settings.OUTPUT_DIR
    if os.path.exists(output_dir):
        try:
            shutil.rmtree(output_dir)
            os.makedirs(output_dir, exist_ok=True)
            removed_dirs.append("tmp/output")
        except Exception as e:
            errors.append(f"output: {e}")

    # 2. Remove downloads directory contents
    download_dir = settings.DOWNLOAD_DIR
    if os.path.exists(download_dir):
        try:
            shutil.rmtree(download_dir)
            os.makedirs(download_dir, exist_ok=True)
            removed_dirs.append("tmp/downloads")
        except Exception as e:
            errors.append(f"downloads: {e}")

    # 3. Clear job records from DB (but NOT users, presets, roles, permissions)
    jobs_deleted = 0
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM jobs")
        jobs_deleted = cur.rowcount
        conn.commit()
    except Exception as e:
        errors.append(f"db: {e}")
    finally:
        conn.close()

    # 4. Clear ALL objects in the MinIO bucket (cliperhub)
    minio_deleted = 0
    try:
        from src.infrastructure.minio_service import get_minio_service
        minio_deleted = get_minio_service().clear_bucket()
        removed_dirs.append(f"minio:{getattr(settings, 'MINIO_BUCKET', 'cliperhub')}")
    except Exception as e:
        errors.append(f"minio: {e}")

    logger.info(f"Storage cleared by user {user.id}: dirs={removed_dirs}, jobs={jobs_deleted}, minio={minio_deleted}, errors={errors}")

    return {
        "success": len(errors) == 0,
        "message": f"Cleared {jobs_deleted} jobs and {minio_deleted} MinIO objects, removed: {', '.join(removed_dirs) or 'nothing'}",
        "details": {
            "jobs_deleted": jobs_deleted,
            "minio_objects_deleted": minio_deleted,
            "dirs_cleared": removed_dirs,
            "errors": errors,
        },
    }
