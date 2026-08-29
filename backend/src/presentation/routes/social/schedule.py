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
from src.infrastructure.database import async_session, SocialAccountModel
from src.presentation.auth_deps import CurrentUser
from src.presentation.routes.auth import get_current_user
from src.presentation.routes.social.helpers import (
    repliz_auth_header,
    repliz_delete,
    repliz_get,
    repliz_post,
    repliz_put,
)
from sqlalchemy import select

schedule_router = APIRouter(prefix="/schedule", tags=["social-schedule"])


def _extract_user_info(user: Any) -> tuple[int, bool]:
    """Extract (user_id, is_superadmin) safely whether user is CurrentUser, dict, or model."""
    if isinstance(user, dict):
        uid = user.get("id", 0)
        is_super = bool(
            user.get("is_superadmin")
            or user.get("role") in ("superadmin", "admin")
            or str(uid).lower() == "admin"
        )
        try:
            uid_int = int(uid)
        except (ValueError, TypeError):
            uid_int = 0
        return uid_int, is_super

    uid = getattr(user, "id", 0)
    is_super = bool(
        getattr(user, "is_superadmin", False)
        or getattr(user, "role", "") in ("superadmin", "admin")
    )
    try:
        uid_int = int(uid)
    except (ValueError, TypeError):
        uid_int = 0
    return uid_int, is_super


async def _get_user_account_ids(user: Any) -> list[str]:
    """Get account IDs owned by this user. Superadmin gets empty (meaning unrestricted)."""
    user_id, is_super = _extract_user_info(user)
    if is_super:
        return []
    async with async_session() as session:
        result = await session.execute(
            select(SocialAccountModel.account_id).where(SocialAccountModel.user_id == user_id)
        )
        return [row[0] for row in result.fetchall()]


async def _user_owns_account(user: Any, account_id: str) -> bool:
    """Check if user owns this account (superadmin owns all)."""
    user_id, is_super = _extract_user_info(user)
    if is_super:
        return True
    async with async_session() as session:
        result = await session.execute(
            select(SocialAccountModel.id).where(
                SocialAccountModel.user_id == user_id,
                SocialAccountModel.account_id == account_id,
            )
        )
        return result.first() is not None


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

    # Sanitize medias: ensure compliant fields
    sanitized_medias = []
    for m in body.medias:
        m_copy = dict(m)
        thumb = m_copy.get("thumbnail")
        if thumb and str(thumb).strip():
            m_copy["thumbnail"] = str(thumb).strip()
            m_copy["customThumbnail"] = True
        else:
            m_copy["thumbnail"] = ""
            m_copy["customThumbnail"] = False
        if not m_copy.get("alt"):
            m_copy["alt"] = (body.title or "Media")[:100]
        if not m_copy.get("type"):
            m_copy["type"] = "video"
        sanitized_medias.append(m_copy)

    # Sanitize replies (Threads nested posts support)
    sanitized_replies = []
    for r in body.replies:
        if isinstance(r, dict):
            if "description" in r or "text" in r:
                sanitized_replies.append({
                    "title": r.get("title", ""),
                    "description": r.get("description") or r.get("text", ""),
                    "topic": r.get("topic", ""),
                    "type": r.get("type", "text"),
                    "medias": r.get("medias", []),
                })
            else:
                sanitized_replies.append(r)

    # Normalize scheduleAt to ensure minimum 2min future buffer for worker execution
    raw_schedule_at = body.scheduleAt
    now_utc = dt.datetime.now(dt.timezone.utc)
    min_future = now_utc + dt.timedelta(minutes=2)
    if raw_schedule_at:
        try:
            parsed_dt = dt.datetime.fromisoformat(raw_schedule_at.replace("Z", "+00:00"))
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=dt.timezone.utc)
            if parsed_dt < min_future:
                parsed_dt = min_future
            normalized_schedule_at = parsed_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        except Exception:
            normalized_schedule_at = min_future.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    else:
        normalized_schedule_at = min_future.strftime("%Y-%m-%dT%H:%M:%S.000Z")

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
        "replies": sanitized_replies,
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
    user_id: Optional[int] = Query(
        None, description="Filter by user ID (superadmin only)"
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
    """Retrieve a paginated list of scheduled posts from Repliz (filtered by user ownership unless superadmin)."""
    _, is_super = _extract_user_info(_user)
    user_account_ids: list[str] = []

    real_user_id = user_id if isinstance(user_id, int) else None
    if is_super and real_user_id is not None:
        async with async_session() as session:
            result = await session.execute(
                select(SocialAccountModel.account_id).where(SocialAccountModel.user_id == real_user_id)
            )
            user_account_ids = [row[0] for row in result.fetchall()]
            if not user_account_ids:
                return {
                    "data": {
                        "docs": [],
                        "totalDocs": 0,
                        "limit": limit,
                        "page": page,
                        "totalPages": 0,
                        "pagingCounter": 1,
                        "hasPrevPage": False,
                        "hasNextPage": False,
                        "prevPage": None,
                        "nextPage": None,
                    }
                }
    elif not is_super:
        user_account_ids = await _get_user_account_ids(_user)
        if not user_account_ids:
            return {
                "data": {
                    "docs": [],
                    "totalDocs": 0,
                    "limit": limit,
                    "page": page,
                    "totalPages": 0,
                    "pagingCounter": 1,
                    "hasPrevPage": False,
                    "hasNextPage": False,
                    "prevPage": None,
                    "nextPage": None,
                }
            }

    params: Dict[str, Any] = {"page": page, "limit": limit}
    if status and status != "all":
        params["status"] = status
    if from_date:
        params["fromDate"] = from_date
    if to_date:
        params["toDate"] = to_date
    if sort:
        params["sort"] = sort

    target_account_ids: list[str] = []
    if account_ids and isinstance(account_ids, str):
        raw_ids = [aid.strip() for aid in account_ids.split(",") if aid.strip()]
        if is_super and real_user_id is None:
            target_account_ids = raw_ids
        else:
            target_account_ids = [aid for aid in raw_ids if aid in user_account_ids]
    elif user_account_ids:
        target_account_ids = user_account_ids

    if target_account_ids:
        for i, aid in enumerate(target_account_ids):
            params[f"accountIds[{i}]"] = aid

    res = await repliz_get("/public/schedule", params=params)
    if isinstance(res, dict):
        container = res.get("data") if isinstance(res.get("data"), dict) else res
        docs = container.get("docs") if isinstance(container, dict) else None
        if isinstance(docs, list):
            # Enforce strict client-side account filtering as defense in depth
            if user_account_ids:
                docs = [d for d in docs if str(d.get("accountId") or d.get("account_id") or "") in user_account_ids]
                container["docs"] = docs
                if container.get("totalDocs", 0) > len(docs):
                    container["totalDocs"] = len(docs)

            docs.sort(
                key=lambda d: str(d.get("scheduleAt") or d.get("createdAt") or ""),
                reverse=True,
            )
    return res


@schedule_router.get("/{schedule_id}")
async def get_schedule(schedule_id: str, _user=Depends(get_current_user)):
    """Get full details for a specific scheduled post with ownership check."""
    _, is_super = _extract_user_info(_user)
    res = await repliz_get(f"/public/schedule/{schedule_id}")
    if not is_super and isinstance(res, dict) and isinstance(res.get("data"), dict):
        doc = res["data"]
        acc_id = str(doc.get("accountId") or doc.get("account_id") or "")
        if acc_id and not await _user_owns_account(_user, acc_id):
            raise HTTPException(
                status_code=403, detail="Akses ditolak: Jadwal ini bukan milik akun Anda."
            )
    return res


@schedule_router.put("/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    body: ScheduleUpdateRequest,
    _user=Depends(get_current_user),
):
    """Update an existing scheduled post with ownership verification."""
    _, is_super = _extract_user_info(_user)
    if not is_super:
        sched_info = await repliz_get(f"/public/schedule/{schedule_id}")
        if isinstance(sched_info, dict) and isinstance(sched_info.get("data"), dict):
            acc_id = str(sched_info["data"].get("accountId") or sched_info["data"].get("account_id") or "")
            if acc_id and not await _user_owns_account(_user, acc_id):
                raise HTTPException(
                    status_code=403, detail="Akses ditolak: Anda tidak memiliki izin untuk mengubah jadwal ini."
                )

    # Sanitize medias: ensure compliant fields
    sanitized_medias = []
    for m in body.medias:
        m_copy = dict(m)
        thumb = m_copy.get("thumbnail")
        if thumb and str(thumb).strip():
            m_copy["thumbnail"] = str(thumb).strip()
            m_copy["customThumbnail"] = True
        else:
            m_copy["thumbnail"] = ""
            m_copy["customThumbnail"] = False
        if not m_copy.get("alt"):
            m_copy["alt"] = (body.title or "Media")[:100]
        if not m_copy.get("type"):
            m_copy["type"] = "video"
        sanitized_medias.append(m_copy)

    # Sanitize replies (Threads nested posts support)
    sanitized_replies = []
    for r in body.replies:
        if isinstance(r, dict):
            if "description" in r or "text" in r:
                sanitized_replies.append({
                    "title": r.get("title", ""),
                    "description": r.get("description") or r.get("text", ""),
                    "topic": r.get("topic", ""),
                    "type": r.get("type", "text"),
                    "medias": r.get("medias", []),
                })
            else:
                sanitized_replies.append(r)

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
        "replies": sanitized_replies,
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

    target_ids = body.scheduleIds
    _, is_super = _extract_user_info(_user)
    if not is_super:
        user_account_ids = await _get_user_account_ids(_user)
        valid_ids = []
        for sid in target_ids:
            try:
                s_data = await repliz_get(f"/public/schedule/{sid}")
                if isinstance(s_data, dict) and isinstance(s_data.get("data"), dict):
                    acc_id = str(s_data["data"].get("accountId") or s_data["data"].get("account_id") or "")
                    if acc_id in user_account_ids:
                        valid_ids.append(sid)
            except Exception:
                pass
        target_ids = valid_ids
        if not target_ids:
            return {"success": True, "message": "Tidak ada jadwal milik Anda yang dapat dibatalkan"}

    params = [("scheduleIds[]", sid) for sid in target_ids if sid]
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
        "message": f"Successfully removed {len(target_ids)} schedules",
    }


@schedule_router.delete("/{schedule_id}")
async def remove_schedule(schedule_id: str, _user=Depends(get_current_user)):
    """Cancel and remove a scheduled post with ownership check."""
    _, is_super = _extract_user_info(_user)
    if not is_super:
        sched_info = await repliz_get(f"/public/schedule/{schedule_id}")
        if isinstance(sched_info, dict) and isinstance(sched_info.get("data"), dict):
            acc_id = str(sched_info["data"].get("accountId") or sched_info["data"].get("account_id") or "")
            if acc_id and not await _user_owns_account(_user, acc_id):
                raise HTTPException(
                    status_code=403, detail="Akses ditolak: Anda tidak memiliki izin untuk membatalkan jadwal ini."
                )

    await repliz_delete(f"/public/schedule/{schedule_id}")
    return {"success": True, "message": "Schedule removed"}


@schedule_router.put("/{schedule_id}/retry")
async def retry_schedule(schedule_id: str, _user=Depends(get_current_user)):
    """Retry / re-queue a failed scheduled post with ownership check."""
    _, is_super = _extract_user_info(_user)
    if not is_super:
        sched_info = await repliz_get(f"/public/schedule/{schedule_id}")
        if isinstance(sched_info, dict) and isinstance(sched_info.get("data"), dict):
            acc_id = str(sched_info["data"].get("accountId") or sched_info["data"].get("account_id") or "")
            if acc_id and not await _user_owns_account(_user, acc_id):
                raise HTTPException(
                    status_code=403, detail="Akses ditolak: Anda tidak memiliki izin untuk me-retry jadwal ini."
                )

    res = await repliz_put(f"/public/schedule/{schedule_id}/retry", json_body={})
    return res or {"success": True, "message": "Schedule retried"}
