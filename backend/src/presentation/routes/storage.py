"""Storage management API — Thoroughly clear all processing data, video files, footages, thumbnails, DB job records, and MinIO objects."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from src.infrastructure.storage_cleanup_service import PROTECTED_TABLES, storage_cleanup_service
from src.presentation.auth_deps import CurrentUser, get_current_user

router = APIRouter(prefix="/storage", tags=["storage"])
logger = logging.getLogger(__name__)


@router.post("/clear")
async def clear_processing_data(user: CurrentUser = Depends(get_current_user)):
    """Clear all processing artifacts, temporary video files, AI Video Generator assets,

    AI Image Studio assets, analysis cache, downloaded footage, DB job records, and MinIO objects.
    Superadmin only.
    """
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin access required")

    result = storage_cleanup_service.execute_cleanup(trigger_source="manual_web", user_id=user.id)

    return {
        "success": result["success"],
        "message": result["message"],
        "details": {
            "total_db_rows_deleted": result["db_rows_deleted"],
            "local_files_deleted": result["files_deleted"],
            "minio_objects_deleted": result["minio_objects_deleted"],
            "dirs_cleared": result["dirs_cleaned"],
            "errors": result["errors"],
            "executed_at": result["executed_at"],
            "trigger_source": result["trigger_source"],
        },
    }


@router.get("/history")
async def get_cleanup_history(
    limit: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
):
    """Retrieve history of storage cleanup runs (manual and automated midnight cron runs). Superadmin only."""
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin access required")

    history = storage_cleanup_service.get_cleanup_history(limit=limit)
    return {"success": True, "data": history}
