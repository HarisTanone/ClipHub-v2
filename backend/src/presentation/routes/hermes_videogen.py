"""REST API routes for Hermes Video Generator Auto-Post configuration and execution."""
import logging
from typing import Optional, List, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from src.presentation.auth_deps import CurrentUser, get_current_user
from src.infrastructure.hermes_videogen_service import hermes_videogen_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hermes-videogen", tags=["Hermes VideoGen"])


class UpdateHermesVideoGenSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    target_region: Optional[str] = Field(None, description="Country/region code (ID, GLOBAL, US, JP, KR, etc.)")
    daily_video_count: Optional[int] = Field(None, ge=1, le=10, description="Jumlah video per hari (default: 3, range 3-5)")
    sources: Optional[List[str]] = Field(None, description="Sumber trending: google_trends, youtube, tiktok, gemini")
    aspect_ratio: Optional[str] = Field(None, description="9:16 (vertical), 16:9 (horizontal), 1:1 (square)")
    watermark_enabled: Optional[bool] = None
    watermark_text: Optional[str] = None
    watermark_position: Optional[str] = None
    watermark_opacity: Optional[float] = None
    subtitles_enabled: Optional[bool] = None
    subtitle_preset: Optional[str] = None
    hook_enabled: Optional[bool] = None
    hook_style: Optional[str] = None
    ai_text_enabled: Optional[bool] = None
    ai_text_preset: Optional[str] = None
    transitions_enabled: Optional[bool] = None
    transition_type: Optional[str] = None
    cta_enabled: Optional[bool] = None
    cta_text: Optional[str] = None
    target_platforms: Optional[List[str]] = None
    target_account_ids: Optional[List[str]] = None
    schedule_mode: Optional[str] = Field(None, description="ai, custom, instant")
    schedule_times: Optional[List[str]] = None


class TriggerHermesVideoGenRequest(BaseModel):
    force: bool = Field(False, description="Paksa eksekusi meskipun kuota hari ini sudah tercapai")
    region_override: Optional[str] = Field(None, description="Override region untuk run ini")
    count_override: Optional[int] = Field(None, ge=1, le=10, description="Override jumlah video untuk run ini (3-5)")


@router.get("/settings")
async def get_settings(user: CurrentUser = Depends(get_current_user)):
    """Get current Hermes VideoGen Auto-Post settings and today's quota status."""
    settings = hermes_videogen_service.get_settings(user_id=user.id)
    can_run, reason, quota_info = hermes_videogen_service.can_run_today(user_id=user.id)
    return {
        "success": True,
        "data": settings,
        "quota": quota_info,
        "can_run_today": can_run,
        "status_message": reason,
    }


@router.put("/settings")
@router.post("/settings")
async def update_settings(
    req: UpdateHermesVideoGenSettingsRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update Hermes VideoGen Auto-Post configuration."""
    update_data = req.model_dump(exclude_unset=True)
    updated = hermes_videogen_service.update_settings(user_id=user.id, data=update_data)
    can_run, reason, quota_info = hermes_videogen_service.can_run_today(user_id=user.id)
    return {
        "success": True,
        "message": "Pengaturan Hermes Video Generator Auto-Post berhasil disimpan",
        "data": updated,
        "quota": quota_info,
        "can_run_today": can_run,
        "status_message": reason,
    }


@router.post("/run")
async def trigger_run(
    req: TriggerHermesVideoGenRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    """Manually trigger Hermes VideoGen trending discovery + video generation + auto-post."""
    can_run, reason, quota = hermes_videogen_service.can_run_today(user_id=user.id)
    if not can_run and not req.force:
        raise HTTPException(
            status_code=429,
            detail=f"Hermes VideoGen tidak dapat dijalankan: {reason}. Gunakan force=true untuk memaksa.",
        )

    # Launch asynchronously via background tasks
    async def _execute():
        try:
            await hermes_videogen_service.run_daily_cycle(
                user_id=user.id,
                force=req.force,
                region_override=req.region_override,
                count_override=req.count_override,
            )
        except Exception as exc:
            logger.error(f"[HermesVideoGenRoute] Execution failed: {exc}", exc_info=True)

    background_tasks.add_task(_execute)

    return {
        "success": True,
        "message": "Hermes Video Generator Auto-Post telah dimulai di background.",
        "quota": quota,
    }


@router.get("/history")
async def get_history(
    limit: int = 20,
    user: CurrentUser = Depends(get_current_user),
):
    """Get history of Hermes VideoGen runs."""
    safe_limit = max(1, min(100, limit))
    runs = hermes_videogen_service.get_runs(user_id=user.id, limit=safe_limit)
    return {
        "success": True,
        "total": len(runs),
        "items": runs,
    }
