"""MinIO upload routes — upload clips to object storage."""
import logging
import os
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from src.config import settings
from src.infrastructure.minio_service import get_minio_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/minio", tags=["MinIO Upload"])


class UploadResponse(BaseModel):
    success: bool
    object_name: Optional[str] = None
    url: Optional[str] = None
    presigned_url: Optional[str] = None
    size: Optional[int] = None
    filename: Optional[str] = None
    error: Optional[str] = None


@router.post("/upload/{job_id}/{clip_rank}")
async def upload_clip_to_minio(job_id: str, clip_rank: int) -> UploadResponse:
    """Upload a rendered clip to MinIO bucket under job_{id}/ folder.

    Looks for the final clip at the standard output path.
    """
    output_dir = os.path.join(settings.OUTPUT_DIR, job_id)

    # Find the clip file (try final > hooked > trimmed)
    candidates = [
        f"clip_{clip_rank:02d}_final.mp4",
        f"clip_{clip_rank:02d}_hooked.mp4",
        f"clip_{clip_rank:02d}.mp4",
    ]

    clip_path = None
    for candidate in candidates:
        path = os.path.join(output_dir, candidate)
        if os.path.exists(path):
            clip_path = path
            break

    if not clip_path:
        raise HTTPException(
            status_code=404,
            detail=f"Clip file not found for job {job_id} clip {clip_rank}. "
                   f"Checked: {', '.join(candidates)}"
        )

    try:
        minio_svc = get_minio_service()
        result = minio_svc.upload_clip(
            job_id=job_id,
            clip_rank=clip_rank,
            file_path=clip_path,
        )
        return UploadResponse(
            success=True,
            object_name=result["object_name"],
            url=result["url"],
            presigned_url=result["presigned_url"],
            size=result["size"],
            filename=result["filename"],
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[minio] Upload error job={job_id} clip={clip_rank}: {e}")
        return UploadResponse(success=False, error=str(e))


@router.get("/files/{job_id}")
async def list_job_files(job_id: str):
    """List all uploaded files for a job in MinIO."""
    try:
        minio_svc = get_minio_service()
        files = minio_svc.list_job_files(job_id)
        return {"success": True, "files": files, "total": len(files)}
    except Exception as e:
        return {"success": False, "error": str(e), "files": []}


@router.get("/url/{job_id}/{filename}")
async def get_download_url(job_id: str, filename: str):
    """Get presigned download URL for a specific file."""
    try:
        minio_svc = get_minio_service()
        object_name = f"job_{job_id}/{filename}"
        url = minio_svc.get_presigned_url(object_name)
        return {"success": True, "url": url, "object_name": object_name}
    except Exception as e:
        return {"success": False, "error": str(e)}


class TelegramNotifyRequest(BaseModel):
    url: str
    filename: str
    caption: str = ""


@router.post("/notify-telegram/{job_id}/{clip_rank}")
async def notify_telegram_upload(job_id: str, clip_rank: int, body: TelegramNotifyRequest):
    """Send upload notification to Telegram bot with download link + caption."""
    try:
        import httpx

        telegram_bot_url = getattr(settings, "TELEGRAM_BOT_NOTIFY_URL", "")
        if not telegram_bot_url:
            logger.info(f"[minio] Telegram notify skipped (no TELEGRAM_BOT_NOTIFY_URL): {body.filename}")
            return {"success": False, "error": "TELEGRAM_BOT_NOTIFY_URL not configured"}

        caption_text = body.caption.strip() if body.caption else ""
        message = (
            f"<b>Clip Uploaded</b>\n\n"
            f"Job: <code>{job_id}</code>\n"
            f"Clip: #{clip_rank}\n"
            f"File: {body.filename}\n\n"
        )
        if caption_text:
            message += f"<b>Caption:</b>\n{caption_text}\n\n"
        message += f'<a href="{body.url}">Download Link</a> (7 hari)'

        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(telegram_bot_url, json={
                "job_id": job_id,
                "clip_rank": clip_rank,
                "message": message,
                "url": body.url,
                "filename": body.filename,
                "caption": caption_text,
            })

        if res.status_code == 200:
            return {"success": True}
        else:
            return {"success": False, "error": f"Telegram returned {res.status_code}"}

    except Exception as e:
        logger.warning(f"[minio] Telegram notify failed: {e}")
        return {"success": False, "error": str(e)}
