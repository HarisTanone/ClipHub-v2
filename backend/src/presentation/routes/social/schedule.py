"""Schedule endpoints — create, list, get, update, delete, retry scheduled posts via Repliz API.

Follows official Repliz Schedule API documentation:
- POST /public/schedule (Create Schedule)
- GET /public/schedule (List Schedules with filters)
- GET /public/schedule/{scheduleId} (Get One Schedule)
- PUT /public/schedule/{scheduleId} (Update Schedule)
- DELETE /public/schedule/{scheduleId} (Remove Schedule)
- DELETE /public/schedule/mass (Mass Remove Schedules)
- PUT /public/schedule/{scheduleId}/retry (Retry Schedule)
"""
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.config import settings
from src.presentation.routes.auth import get_current_user
from src.presentation.routes.social.helpers import (
    repliz_auth_header,
    repliz_delete,
    repliz_get,
    repliz_post,
    repliz_put,
)

schedule_router = APIRouter(prefix="/schedule", tags=["social-schedule"])


class ScheduleMediaItem(BaseModel):
    url: str
    type: str = "video"  # "video" or "image"
    thumbnail: str = ""
    alt: str = ""
    customThumbnail: bool = False


class ScheduleMeta(BaseModel):
    title: str = ""
    description: str = ""
    url: str = ""


class ScheduleAdditionalInfo(BaseModel):
    isAiGenerated: bool = False
    isDraft: bool = False
    isAutoAddMusic: bool = False
    collaborators: List[str] = Field(default_factory=list)
    mentions: List[str] = Field(default_factory=list)
    music: Dict[str, Any] = Field(
        default_factory=lambda: {"id": "", "artist": "", "name": "", "thumbnail": ""}
    )
    products: List[Dict[str, Any]] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    targetCountries: List[str] = Field(default_factory=list)


class ScheduleCreateRequest(BaseModel):
    title: str = ""
    description: str = ""
    topic: str = ""
    type: str = "video"  # text, image, video, reel, album, link, story
    medias: List[Dict[str, Any]] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(
        default_factory=lambda: {"title": "", "description": "", "url": ""}
    )
    additionalInfo: Dict[str, Any] = Field(default_factory=dict)
    replies: List[Dict[str, Any]] = Field(default_factory=list)
    accountId: str
    scheduleAt: str  # ISO 8601 UTC datetime
    templateId: Optional[str] = None


class ScheduleUpdateRequest(BaseModel):
    title: str = ""
    description: str = ""
    topic: str = ""
    type: str = "video"
    medias: List[Dict[str, Any]] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
    additionalInfo: Dict[str, Any] = Field(default_factory=dict)
    replies: List[Dict[str, Any]] = Field(default_factory=list)
    scheduleAt: str
    templateId: Optional[str] = None


class MassDeleteScheduleRequest(BaseModel):
    scheduleIds: List[str]


@schedule_router.post("")
async def create_schedule(body: ScheduleCreateRequest, _user=Depends(get_current_user)):
    """Create a scheduled post in Repliz."""
    import datetime as dt

    # Sanitize medias: omit empty thumbnail string to avoid Repliz/TikTok validation failure
    sanitized_medias = []
    for m in body.medias:
        m_copy = dict(m)
        thumb = m_copy.get("thumbnail")
        if not thumb or not str(thumb).strip():
            m_copy.pop("thumbnail", None)
            m_copy["customThumbnail"] = False
        else:
            m_copy["customThumbnail"] = True
        sanitized_medias.append(m_copy)

    # Normalize scheduleAt to ensure minimum 20min future buffer for TikTok API compliance
    raw_schedule_at = body.scheduleAt
    normalized_schedule_at = raw_schedule_at
    if raw_schedule_at:
        try:
            parsed_dt = dt.datetime.fromisoformat(raw_schedule_at.replace("Z", "+00:00"))
            min_future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=20)
            if parsed_dt < min_future:
                parsed_dt = min_future
            normalized_schedule_at = parsed_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        except Exception:
            normalized_schedule_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    else:
        normalized_schedule_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    payload = {
        "title": (body.title or "Video")[:100],
        "description": (body.description or "")[:2000],
        "topic": body.topic,
        "type": body.type,
        "medias": sanitized_medias,
        "meta": body.meta or {"title": "", "description": "", "url": ""},
        "additionalInfo": {
            "isAiGenerated": body.additionalInfo.get("isAiGenerated", False),
            "isDraft": body.additionalInfo.get("isDraft", False),
            "isAutoAddMusic": body.additionalInfo.get("isAutoAddMusic", False),
            "collaborators": body.additionalInfo.get("collaborators", []),
            "mentions": body.additionalInfo.get("mentions", []),
            "music": body.additionalInfo.get(
                "music", {"id": "", "artist": "", "name": "", "thumbnail": ""}
            ),
            "products": body.additionalInfo.get("products", []),
            "tags": body.additionalInfo.get("tags", []),
            "targetCountries": body.additionalInfo.get("targetCountries", []),
        },
        "replies": body.replies,
        "accountId": body.accountId,
        "scheduleAt": normalized_schedule_at,
    }
    if body.templateId:
        payload["templateId"] = body.templateId

    return await repliz_post("/public/schedule", json_body=payload)


@schedule_router.get("")
async def list_schedules(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(
        None, description="Filter by status: pending, process, error, success"
    ),
    account_ids: Optional[str] = Query(
        None, alias="accountIds", description="Comma-separated account IDs"
    ),
    from_date: Optional[str] = Query(
        None, alias="fromDate", description="ISO 8601 start date"
    ),
    to_date: Optional[str] = Query(
        None, alias="toDate", description="ISO 8601 end date"
    ),
    sort: Optional[str] = Query(
        "-scheduleAt", description="Sort order (default newest: -scheduleAt)"
    ),
    _user=Depends(get_current_user),
):
    """Retrieve a paginated list of scheduled posts from Repliz (sorted newest first)."""
    params: Dict[str, Any] = {"page": page, "limit": limit}
    if status:
        params["status"] = status
    if from_date:
        params["fromDate"] = from_date
    if to_date:
        params["toDate"] = to_date
    if sort:
        params["sort"] = sort
    if account_ids:
        raw_ids = [aid.strip() for aid in account_ids.split(",") if aid.strip()]
        for i, aid in enumerate(raw_ids):
            params[f"accountIds[{i}]"] = aid

    res = await repliz_get("/public/schedule", params=params)
    if isinstance(res, dict) and isinstance(res.get("data"), dict):
        docs = res["data"].get("docs")
        if isinstance(docs, list):
            docs.sort(
                key=lambda d: str(d.get("scheduleAt") or d.get("createdAt") or ""),
                reverse=True,
            )
    return res


@schedule_router.get("/{schedule_id}")
async def get_schedule(schedule_id: str, _user=Depends(get_current_user)):
    """Get full details for a specific scheduled post."""
    return await repliz_get(f"/public/schedule/{schedule_id}")


@schedule_router.put("/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    body: ScheduleUpdateRequest,
    _user=Depends(get_current_user),
):
    """Update an existing scheduled post."""
    # Sanitize medias: omit empty thumbnail string to avoid Repliz/TikTok validation failure
    sanitized_medias = []
    for m in body.medias:
        m_copy = dict(m)
        thumb = m_copy.get("thumbnail")
        if not thumb or not str(thumb).strip():
            m_copy.pop("thumbnail", None)
            m_copy["customThumbnail"] = False
        else:
            m_copy["customThumbnail"] = True
        sanitized_medias.append(m_copy)

    payload = {
        "title": (body.title or "Video")[:100],
        "description": (body.description or "")[:2000],
        "topic": body.topic,
        "type": body.type,
        "medias": sanitized_medias,
        "meta": body.meta or {"title": "", "description": "", "url": ""},
        "additionalInfo": {
            "isAiGenerated": body.additionalInfo.get("isAiGenerated", False),
            "isDraft": body.additionalInfo.get("isDraft", False),
            "isAutoAddMusic": body.additionalInfo.get("isAutoAddMusic", False),
            "collaborators": body.additionalInfo.get("collaborators", []),
            "mentions": body.additionalInfo.get("mentions", []),
            "music": body.additionalInfo.get(
                "music", {"id": "", "artist": "", "name": "", "thumbnail": ""}
            ),
            "products": body.additionalInfo.get("products", []),
            "tags": body.additionalInfo.get("tags", []),
            "targetCountries": body.additionalInfo.get("targetCountries", []),
        },
        "replies": body.replies,
        "scheduleAt": body.scheduleAt,
    }
    if body.templateId:
        payload["templateId"] = body.templateId

    res = await repliz_put(f"/public/schedule/{schedule_id}", json_body=payload)
    return res or {"success": True, "message": "Schedule updated"}


@schedule_router.delete("/mass")
async def mass_delete_schedules(
    body: MassDeleteScheduleRequest,
    _user=Depends(get_current_user),
):
    """Cancel and remove multiple scheduled posts at once."""
    if not body.scheduleIds:
        return {"success": True, "message": "No schedules to delete"}

    params = [("scheduleIds[]", sid) for sid in body.scheduleIds if sid]
    url = f"{settings.REPLIZ_BASE_URL}/public/schedule/mass"
    headers = repliz_auth_header()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.delete(url, headers=headers, params=params)

    if resp.status_code == 401:
        raise HTTPException(
            status_code=502, detail="Repliz auth failed - check credentials"
        )
    if resp.status_code not in (200, 204):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    return {
        "success": True,
        "message": f"Successfully removed {len(body.scheduleIds)} schedules",
    }


@schedule_router.delete("/{schedule_id}")
async def remove_schedule(schedule_id: str, _user=Depends(get_current_user)):
    """Cancel and remove a scheduled post."""
    await repliz_delete(f"/public/schedule/{schedule_id}")
    return {"success": True, "message": "Schedule removed"}


@schedule_router.put("/{schedule_id}/retry")
async def retry_schedule(schedule_id: str, _user=Depends(get_current_user)):
    """Retry / re-queue a failed scheduled post."""
    res = await repliz_put(f"/public/schedule/{schedule_id}/retry", json_body={})
    return res or {"success": True, "message": "Schedule retried"}
