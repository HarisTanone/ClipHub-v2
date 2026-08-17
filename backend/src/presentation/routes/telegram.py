"""Telegram API routes — Superadmin configuration, testing, and clip delivery."""
import logging
import os
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.config import settings
from src.infrastructure.telegram_service import telegram_service
from src.presentation.auth_deps import CurrentUser, get_current_user

router = APIRouter(prefix="/telegram", tags=["telegram"])
logger = logging.getLogger(__name__)


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class TelegramSettingsRequest(BaseModel):
    is_enabled: bool = False
    bot_token: str = ""
    bot_username: str = ""
    chat_id: str = ""
    group_id: str = ""
    channel_id: str = ""
    topic_id: str = ""
    allowed_users: str = ""
    notify_on_job_start: bool = True
    notify_on_job_complete: bool = True
    notify_on_job_failed: bool = True
    send_video_files: bool = True
    include_caption: bool = True
    include_hashtags: bool = True
    include_virality_score: bool = True
    notify_target: str = "all"
    auto_post_social: bool = False
    auto_post_platforms: str = ""
    auto_post_schedule_mode: str = "ai"
    auto_post_interval_hours: int = 4
    auto_post_peak_hours: str = "11:30,15:00,18:30,20:30"


class TelegramTestRequest(BaseModel):
    bot_token: Optional[str] = None
    target_id: Optional[str] = None


class TelegramSendClipRequest(BaseModel):
    custom_caption: Optional[str] = None
    target_id: Optional[str] = None


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/settings")
async def get_telegram_settings(user: CurrentUser = Depends(get_current_user)):
    """Get current Telegram configuration (Superadmin only)."""
    if not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required for Telegram settings"
        )
    return {
        "success": True,
        "data": telegram_service.get_settings(mask_token=False)
    }


@router.put("/settings")
async def update_telegram_settings(
    body: TelegramSettingsRequest,
    user: CurrentUser = Depends(get_current_user)
):
    """Update Telegram configuration (Superadmin only)."""
    if not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required for Telegram settings"
        )
    updated = telegram_service.update_settings(body.model_dump())
    return {
        "success": True,
        "data": updated,
        "message": "Pengaturan Telegram berhasil disimpan"
    }


@router.post("/test")
async def test_telegram_connection(
    body: TelegramTestRequest,
    user: CurrentUser = Depends(get_current_user)
):
    """Test Telegram Bot API connection & send test ping (Superadmin only)."""
    if not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required for testing Telegram"
        )
    result = await telegram_service.test_connection(
        bot_token=body.bot_token,
        target_id=body.target_id
    )
    return result


@router.post("/test-video")
async def test_telegram_video(
    body: TelegramTestRequest,
    user: CurrentUser = Depends(get_current_user)
):
    """Send a test video clip to verify media upload permissions (Superadmin only)."""
    if not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required for testing Telegram video"
        )

    # Look for candidate test video
    candidates = [
        os.path.join(os.path.dirname(settings.DOWNLOAD_DIR), "clip_01.mp4"),
        os.path.join(os.path.dirname(settings.DOWNLOAD_DIR), "clip_test_final.mp4"),
    ]
    # Check output dirs
    if os.path.exists(settings.OUTPUT_DIR):
        for job_folder in os.listdir(settings.OUTPUT_DIR):
            job_path = os.path.join(settings.OUTPUT_DIR, job_folder)
            if os.path.isdir(job_path):
                for f in os.listdir(job_path):
                    if f.endswith(".mp4"):
                        candidates.append(os.path.join(job_path, f))

    test_video = next((c for c in candidates if os.path.exists(c)), None)
    if not test_video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tidak ada sample video yang ditemukan di server untuk test upload."
        )

    result = await telegram_service.send_video(
        video_path=test_video,
        caption="<b>[ClipHub] Test Video</b>\n\nKoneksi pengiriman video klip ke Telegram berhasil!",
        target_id=body.target_id
    )
    return result


@router.post("/send-clip/{job_id}/{clip_rank}")
async def send_clip_to_telegram(
    job_id: str,
    clip_rank: int,
    body: TelegramSendClipRequest,
    user: CurrentUser = Depends(get_current_user)
):
    """Send a specific rendered video clip to Telegram."""
    result = await telegram_service.send_clip_by_rank(
        job_id=job_id,
        clip_rank=clip_rank,
        custom_caption=body.custom_caption,
        target_id=body.target_id
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Gagal mengirim video ke Telegram")
        )
    return {
        "success": True,
        "message": f"Clip #{clip_rank} berhasil dikirim ke Telegram!"
    }


@router.get("/social-accounts")
async def get_telegram_social_accounts(user: CurrentUser = Depends(get_current_user)):
    """Get all connected social accounts available for Telegram auto-posting."""
    from src.infrastructure.social_auto_post_service import social_auto_post_service
    accounts = await social_auto_post_service.get_connected_accounts(
        user_id=None if user.is_superadmin else user.id
    )
    return {
        "success": True,
        "accounts": accounts
    }


@router.post("/trigger-auto-post/{job_id}")
async def trigger_job_auto_post(
    job_id: str,
    user: CurrentUser = Depends(get_current_user)
):
    """Manually trigger AI social auto-posting for a completed job."""
    from src.infrastructure.social_auto_post_service import social_auto_post_service
    from src.infrastructure.repositories import JobRepository
    from src.infrastructure.database import async_session

    async with async_session() as session:
        repo = JobRepository(session)
        job = await repo.get_by_job_id(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job tidak ditemukan")

        clips_data = job.clips_data or {}
        clips = clips_data.get("clips", [])
        if not clips:
            raise HTTPException(status_code=400, detail="Tidak ada klip pada job ini")

        output_dir = os.path.join(settings.OUTPUT_DIR, job_id)
        cfg = telegram_service.get_settings()
        platforms = [p.strip() for p in cfg.get("auto_post_platforms", "").split(",") if p.strip()]

        result = await social_auto_post_service.auto_schedule_job_clips(
            job_id=job_id,
            clips=clips,
            output_dir=output_dir,
            target_platforms=platforms or None,
            schedule_mode=cfg.get("auto_post_schedule_mode", "ai"),
            notify_telegram=True,
        )
        return result

