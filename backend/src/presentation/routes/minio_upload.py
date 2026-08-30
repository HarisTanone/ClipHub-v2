"""MinIO upload routes — upload clips to object storage."""
import logging
import os
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from src.config import settings
from src.infrastructure.minio_service import get_minio_service
from src.presentation.auth_deps import CurrentUser, get_current_user

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
async def upload_clip_to_minio(
    job_id: str,
    clip_rank: int,
    user: CurrentUser = Depends(get_current_user),
) -> UploadResponse:
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
async def list_job_files(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """List all uploaded files for a job in MinIO."""
    try:
        minio_svc = get_minio_service()
        files = minio_svc.list_job_files(job_id)
        return {"success": True, "files": files, "total": len(files)}
    except Exception as e:
        return {"success": False, "error": str(e), "files": []}


@router.get("/url/{job_id}/{filename}")
async def get_download_url(
    job_id: str,
    filename: str,
    user: CurrentUser = Depends(get_current_user),
):
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
async def notify_telegram_upload(
    job_id: str,
    clip_rank: int,
    body: TelegramNotifyRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Send upload notification to Telegram bot with download link + caption."""
    try:
        import httpx

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

        # Method 1: TelegramService / Direct Telegram Bot API
        from src.infrastructure.telegram_service import telegram_service
        tg_cfg = telegram_service.get_settings()
        bot_token = tg_cfg.get("bot_token") or getattr(settings, "TELEGRAM_BOT_TOKEN", "") or os.getenv("ALERT_TELEGRAM_TOKEN", "")
        chat_id = tg_cfg.get("chat_id") or tg_cfg.get("group_id") or tg_cfg.get("channel_id") or getattr(settings, "TELEGRAM_CHAT_ID", "") or os.getenv("ALERT_TELEGRAM_CHAT_ID", "")

        if bot_token and chat_id:
            async with httpx.AsyncClient(timeout=10) as client:
                destinations = telegram_service._get_target_destinations(tg_cfg, explicit_target=None) if tg_cfg.get("bot_token") else [chat_id]
                if not destinations:
                    destinations = [chat_id]
                sent = False
                for cid in destinations:
                    payload = {
                        "chat_id": cid,
                        "text": message,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": False,
                    }
                    if tg_cfg.get("topic_id"):
                        try:
                            payload["message_thread_id"] = int(tg_cfg["topic_id"])
                        except ValueError:
                            pass
                    res = await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json=payload,
                    )
                    if res.status_code == 200:
                        sent = True
                if sent:
                    return {"success": True, "method": "telegram_api"}
                else:
                    logger.warning(f"[minio] Telegram API failed: {res.status_code} {res.text[:200]}")
                    return {"success": False, "error": f"Telegram API {res.status_code}"}

        # Method 2: Custom webhook URL (fallback)
        telegram_bot_url = getattr(settings, "TELEGRAM_BOT_NOTIFY_URL", "")
        if telegram_bot_url:
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
                return {"success": True, "method": "webhook"}
            else:
                return {"success": False, "error": f"Webhook returned {res.status_code}"}

        # No method configured
        logger.info(f"[minio] Telegram notify skipped (no token/url): {body.filename}")
        return {"success": False, "error": "Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID or TELEGRAM_BOT_NOTIFY_URL"}

    except Exception as e:
        logger.warning(f"[minio] Telegram notify failed: {e}")
        return {"success": False, "error": str(e)}
