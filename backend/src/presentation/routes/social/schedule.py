"""Schedule endpoints - create, list, get, update, delete scheduled posts."""
from typing import Optional, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.presentation.routes.auth import get_current_user
from src.presentation.routes.social.helpers import repliz_get, repliz_post, repliz_put, repliz_delete

schedule_router = APIRouter(prefix="/schedule", tags=["social-schedule"])


class ScheduleCreateRequest(BaseModel):
    title: str = ""
    description: str = ""
    topic: str = ""
    type: str = "video"
    medias: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}
    additionalInfo: dict[str, Any] = {}
    replies: list[dict[str, Any]] = []
    accountId: str
    scheduleAt: str
    templateId: Optional[str] = None


@schedule_router.post("")
async def create_schedule(body: ScheduleCreateRequest, _user=Depends(get_current_user)):
    """Create a scheduled post."""
    payload = body.model_dump(exclude_none=True)
    return await repliz_post("/public/schedule", json_body=payload)


@schedule_router.get("")
async def list_schedules(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    _user=Depends(get_current_user),
):
    """List scheduled posts."""
    params: dict = {"page": page, "limit": limit}
    if status:
        params["status"] = status
    return await repliz_get("/public/schedule", params=params)


@schedule_router.get("/{schedule_id}")
async def get_schedule(schedule_id: str, _user=Depends(get_current_user)):
    """Get one scheduled post."""
    return await repliz_get(f"/public/schedule/{schedule_id}")


@schedule_router.put("/{schedule_id}")
async def update_schedule(schedule_id: str, body: ScheduleCreateRequest, _user=Depends(get_current_user)):
    """Update a scheduled post."""
    payload = body.model_dump(exclude_none=True)
    payload.pop("accountId", None)  # accountId not updatable
    return await repliz_put(f"/public/schedule/{schedule_id}", json_body=payload)


@schedule_router.delete("/{schedule_id}")
async def remove_schedule(schedule_id: str, _user=Depends(get_current_user)):
    """Remove a scheduled post."""
    await repliz_delete(f"/public/schedule/{schedule_id}")
    return {"success": True, "message": "Schedule removed"}


@schedule_router.put("/{schedule_id}/retry")
async def retry_schedule(schedule_id: str, _user=Depends(get_current_user)):
    """Retry a failed scheduled post."""
    return await repliz_put(f"/public/schedule/{schedule_id}/retry", json_body={})
