"""REST API routes for Hermes Autopilot configuration and execution."""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.presentation.auth_deps import CurrentUser, get_current_user
from src.infrastructure.autopilot_service import autopilot_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/autopilot", tags=["Autopilot"])


class UpdateAutopilotSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    niche_query: Optional[str] = Field(None, description="Topik atau kata kunci pencarian video viral")
    preset_slug: Optional[str] = Field(None, description="Preset style slug untuk rendering klip")
    target_platforms: Optional[str] = Field(None, description="Comma-separated platform target (tiktok,instagram,youtube)")
    target_account_ids: Optional[List[str]] = Field(None, description="List spesifik account ID untuk target posting")
    schedule_mode: Optional[str] = Field(None, description="Mode jadwal posting: 'ai', 'custom', 'instant'")
    custom_schedule_time: Optional[str] = Field(None, description="Jam mulai jadwal posting manual")
    run_time: Optional[str] = Field(None, description="Waktu eksekusi autopilot harian (HH:MM WIB)")
    min_duration_sec: Optional[int] = Field(None, description="Durasi minimal video (detik)")
    max_duration_sec: Optional[int] = Field(None, description="Durasi maksimal video (detik)")


class TriggerAutopilotRequest(BaseModel):
    force: bool = Field(False, description="Paksa jalankan meskipun kuota hari ini sudah tercapai")


@router.get("/settings")
async def get_autopilot_settings(user: CurrentUser = Depends(get_current_user)):
    """Get current autopilot configuration and today's quota status."""
    settings = autopilot_service.get_settings(user_id=user.id)
    can_run, reason, quota_info = autopilot_service.can_run_today(user_id=user.id)
    return {
        "success": True,
        "data": settings,
        "quota": quota_info,
        "can_run_today": can_run,
        "status_message": reason,
    }


@router.post("/settings")
async def update_autopilot_settings(
    req: UpdateAutopilotSettingsRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update autopilot configuration."""
    update_data = req.model_dump(exclude_unset=True)
    updated = autopilot_service.update_settings(user_id=user.id, data=update_data)
    can_run, reason, quota_info = autopilot_service.can_run_today(user_id=user.id)
    return {
        "success": True,
        "message": "Pengaturan Hermes Autopilot berhasil disimpan",
        "data": updated,
        "quota": quota_info,
        "can_run_today": can_run,
    }


@router.post("/run")
async def trigger_autopilot_now(
    req: TriggerAutopilotRequest = TriggerAutopilotRequest(),
    user: CurrentUser = Depends(get_current_user),
):
    """Trigger an immediate autopilot run.

    Enforces 1 video/day quota unless force=True.
    """
    res = await autopilot_service.run_autopilot_step(
        user_id=user.id,
        force=req.force,
        trigger_source="web_dashboard",
        notify_telegram=True,
    )
    if not res.get("success"):
        raise HTTPException(
            status_code=400 if res.get("status") == "quota_exceeded" else 500,
            detail=res.get("message", "Gagal menjalankan autopilot"),
        )
    return res


@router.get("/history")
async def get_autopilot_history(
    limit: int = 20,
    user: CurrentUser = Depends(get_current_user),
):
    """Get recent autopilot run records."""
    history = autopilot_service.get_history(user_id=user.id, limit=limit)
    return {
        "success": True,
        "data": history,
    }
