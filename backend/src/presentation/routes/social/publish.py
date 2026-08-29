"""Publish endpoint — upload video to Google Drive then schedule post via Repliz API.

Flow: Clip/Video output -> Google Drive (public direct link) -> Repliz Schedule API
"""
import logging
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.config import settings
from src.infrastructure.clip_outputs import find_final_clip
from src.infrastructure.gdrive_uploader import gdrive_uploader
from src.infrastructure.social_compliance import (
    ensure_social_compliant_video,
    ensure_social_compliant_thumbnail,
    validate_social_media_constraints,
)
from src.presentation.routes.auth import get_current_user
from src.presentation.routes.social.helpers import repliz_post

logger = logging.getLogger(__name__)
publish_router = APIRouter(prefix="/publish", tags=["social-publish"])


class PublishRequest(BaseModel):
    """Request to publish a clip or AI generated video to social media."""

    jobId: str
    clipRank: Optional[int] = None
    videoSource: Optional[str] = None  # "clip" or "video_generator"
    accountId: Optional[str] = None
    accountIds: Optional[List[str]] = None
    caption: str = ""
    title: str = ""
    topic: str = ""
    type: str = "video"  # "video", "reel", "story"
    tags: List[str] = Field(default_factory=list)
    firstReply: Optional[str] = ""
    isAiGenerated: bool = True
    isDraft: bool = False
    collaborators: List[str] = Field(default_factory=list)
    mentions: List[str] = Field(default_factory=list)
    targetCountries: List[str] = Field(default_factory=list)
    scheduleAt: str  # ISO 8601 UTC string



def get_supported_post_type(requested_type: Optional[str], platform: str = "") -> str:
    """Normalize post type to comply with Repliz official Supported Post Types specification.
    
    Repliz Documentation Matrix:
    - Facebook: text, image, video, reel, album, link, story
    - Instagram: image, video, album, story (NO 'reel')
    - TikTok: image, video, album (NO 'reel', NO 'story')
    - YouTube: video (NO 'reel', NO 'story')
    - Threads: text, image, video, album
    - LinkedIn: image, video, album
    """
    plat = (platform or "").lower().strip()
    req = (requested_type or "video").lower().strip()

    if plat == "facebook":
        if req in ("text", "image", "video", "reel", "album", "link", "story"):
            return req
        return "video"
    elif plat == "instagram":
        if req == "story":
            return "story"
        if req in ("image", "album"):
            return req
        return "video"  # In Repliz API, Instagram reels/videos use 'video'
    elif plat == "tiktok":
        if req in ("image", "album"):
            return req
        return "video"  # TikTok video is 'video'
    elif plat == "youtube":
        return "video"  # YouTube is always 'video'
    elif plat == "threads":
        if req in ("text", "image", "album"):
            return req
        return "video"
    elif plat == "linkedin":
        if req in ("image", "album"):
            return req
        return "video"

    # Default fallback for unknown platforms
    if req in ("reel", "story"):
        return "video"
    return req or "video"


@publish_router.post("")
async def publish_clip(body: PublishRequest, _user=Depends(get_current_user)):
    """Upload clip or AI generated video to Google Drive once and schedule posts across all selected accounts via Repliz."""
    # 1. Resolve target account IDs
    target_account_ids: List[str] = []
    if body.accountIds:
        target_account_ids = [
            aid.strip() for aid in body.accountIds if aid and str(aid).strip()
        ]
    elif body.accountId:
        target_account_ids = [body.accountId.strip()]

    if not target_account_ids:
        raise HTTPException(
            status_code=400,
            detail="Pilih minimal satu akun media sosial untuk posting.",
        )

    # 2. Check credentials
    from src.infrastructure.social_compliance import resolve_public_media_base_url

    public_base = resolve_public_media_base_url()

    if not public_base and not gdrive_uploader.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Media URL host belum dikonfigurasi. Pastikan AUTOCLIPER_PUBLIC_URL atau Google Drive sudah terisi.",
        )
    if not settings.REPLIZ_ACCESS_KEY or not settings.REPLIZ_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="Repliz API credentials belum dikonfigurasi. Pastikan REPLIZ_ACCESS_KEY dan REPLIZ_SECRET_KEY sudah terisi.",
        )

    # 3. Locate video file (from Video Generator or ClipHub clips)
    video_file = None
    upload_filename = ""

    is_video_gen = (
        body.videoSource == "video_generator" or body.jobId.startswith("vg_")
    )
    if not is_video_gen:
        output_dir = os.path.join(settings.OUTPUT_DIR, body.jobId)
        if not os.path.isdir(output_dir):
            try:
                from src.application.video_generator import get_video_generator

                vg = get_video_generator()
                if vg.get_job(body.jobId):
                    is_video_gen = True
            except Exception:
                pass

    if is_video_gen:
        from src.application.video_generator import get_video_generator

        vg = get_video_generator()
        vg_job = vg.get_job(body.jobId)
        if not vg_job:
            raise HTTPException(
                status_code=404, detail="Video generator job not found"
            )
        if not vg_job.output_path or not os.path.exists(vg_job.output_path):
            raise HTTPException(
                status_code=404,
                detail="Final generated video not found or not ready",
            )
        video_file = vg_job.output_path
        upload_filename = f"videogen_{body.jobId}.mp4"
    else:
        output_dir = os.path.join(settings.OUTPUT_DIR, body.jobId)
        if not os.path.isdir(output_dir):
            raise HTTPException(status_code=404, detail="Job not found")

        clip_rank = body.clipRank or 1
        clip_final = find_final_clip(output_dir, clip_rank)
        if not clip_final:
            raise HTTPException(
                status_code=404,
                detail=f"Final video for clip #{clip_rank} not found",
            )
        video_file = clip_final
        upload_filename = f"{body.jobId}_clip{clip_rank}.mp4"

    # 4. Transcode to 100% compliant video format
    try:
        compliant_video = ensure_social_compliant_video(video_file)
    except Exception as e:
        logger.warning(f"Video compliance transcode fallback: {e}")
        compliant_video = video_file

    # 4a. Programmatic duration and format validation check (Mandatory TikTok/Meta API requirement)
    if os.path.exists(compliant_video):
        is_valid, constraint_err = validate_social_media_constraints(
            compliant_video, platform="tiktok"
        )
        if not is_valid and "minimum requirement of 3.0 seconds" in str(constraint_err):
            raise HTTPException(status_code=400, detail=constraint_err)

    # 4b. Ensure local compliant thumbnail (captured at hook frame 1.5s)
    thumb_url = None
    comp_thumb = None
    try:
        if not is_video_gen and body.clipRank is not None:
            rank_num = body.clipRank
            thumb_dir = os.path.join(settings.OUTPUT_DIR, body.jobId, "thumbnail")
            os.makedirs(thumb_dir, exist_ok=True)
            candidate_thumb = os.path.join(thumb_dir, f"clip_{rank_num:02d}.jpg")
            if not os.path.exists(candidate_thumb):
                candidate_thumb = os.path.join(thumb_dir, f"clip_{rank_num:02d}_thumb.jpg")

            comp_thumb = ensure_social_compliant_thumbnail(
                thumb_path=candidate_thumb if os.path.exists(candidate_thumb) else None,
                video_path=compliant_video,
                output_path=os.path.join(thumb_dir, f"clip_{rank_num:02d}_social.jpg"),
                seek=1.5,
            )
        elif is_video_gen:
            vg_thumb_out = os.path.join(settings.VIDEO_GEN_OUTPUT_DIR, body.jobId, "thumb.jpg")
            os.makedirs(os.path.dirname(vg_thumb_out), exist_ok=True)
            comp_thumb = ensure_social_compliant_thumbnail(
                video_path=compliant_video,
                output_path=vg_thumb_out,
                seek=1.5,
            )
    except Exception as e:
        logger.warning(f"Local thumbnail generation skipped: {e}")

    # 4c. Resolve video_url and thumb_url (prefer direct public domain / tunnel URL)
    drive_result = None
    video_url = ""

    if public_base:
        if is_video_gen:
            video_url = f"{public_base}/api/jobs/{body.jobId}/clips/1/final"
            thumb_url = f"{public_base}/api/jobs/{body.jobId}/clips/1/thumb"
        else:
            clip_rank = body.clipRank or 1
            video_url = f"{public_base}/api/jobs/{body.jobId}/clips/{clip_rank}/final"
            thumb_url = f"{public_base}/api/jobs/{body.jobId}/clips/{clip_rank}/thumb"
    elif gdrive_uploader.is_configured:
        try:
            drive_result = gdrive_uploader.upload_video(
                compliant_video, filename=upload_filename
            )
            video_url = drive_result.get("direct_link") or drive_result.get("web_view_link")
        except Exception as e:
            logger.error(f"Google Drive upload failed: {e}")
            raise HTTPException(
                status_code=502, detail=f"Google Drive upload failed: {str(e)}"
            )

        if comp_thumb and os.path.exists(comp_thumb):
            try:
                thumb_res = gdrive_uploader.upload_image(
                    comp_thumb, filename=f"{body.jobId}_thumb.jpg"
                )
                thumb_url = thumb_res.get("direct_link") or thumb_res.get("web_view_link")
            except Exception as e:
                logger.warning(f"Thumbnail upload to Drive failed: {e}")

    if not video_url:
        raise HTTPException(
            status_code=502,
            detail="Gagal mendapatkan URL publik untuk file video (AUTOCLIPER_PUBLIC_URL atau Google Drive).",
        )

    # 5. Extract hashtags for tags if tags list is empty
    tags = list(body.tags)
    if not tags and body.caption:
        hashtag_matches = re.findall(r"#(\w+)", body.caption)
        if hashtag_matches:
            tags = hashtag_matches[:10]

    # 6. Lookup account platform types from database if available
    account_platform_map = {}
    try:
        from sqlalchemy import select
        from src.infrastructure.database import SocialAccountModel, async_session

        async with async_session() as session:
            result = await session.execute(
                select(SocialAccountModel.account_id, SocialAccountModel.platform).where(
                    SocialAccountModel.account_id.in_(target_account_ids)
                )
            )
            for acc_id_row, plat_row in result.fetchall():
                account_platform_map[acc_id_row] = plat_row
    except Exception as e:
        logger.warning(f"Failed to lookup local social account platforms: {e}")

    # 7. Safe scheduleAt normalization (minimum 2min future threshold for immediate execution)
    import datetime as dt

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

    # 8. Schedule on Repliz for each target account
    successful_schedules = []
    failed_schedules = []

    post_title = (body.title or "Video")[:100]
    post_desc = (body.caption or "")
    if len(post_desc) > 2000:
        post_desc = post_desc[:1990].rstrip() + "..."

    media_obj: Dict[str, Any] = {
        "alt": post_title,
        "customThumbnail": bool(thumb_url),
        "type": "video",
        "thumbnail": thumb_url or "",
        "url": video_url,
    }

    replies = []
    if body.firstReply and body.firstReply.strip():
        replies.append({
            "title": "",
            "description": body.firstReply.strip(),
            "topic": "",
            "type": "text",
            "medias": [],
        })

    additional_info = {
        "isAiGenerated": bool(body.isAiGenerated),
        "isDraft": bool(body.isDraft),
        "isAutoAddMusic": False,
        "collaborators": body.collaborators or [],
        "mentions": body.mentions or [],
        "music": {
            "id": "",
            "artist": "",
            "name": "",
            "thumbnail": "",
        },
        "products": [],
        "tags": tags or [],
        "targetCountries": body.targetCountries or [],
    }

    for acc_id in target_account_ids:
        try:
            platform = account_platform_map.get(acc_id, "")
            post_type = get_supported_post_type(body.type, platform)

            payload = {
                "title": post_title,
                "description": post_desc,
                "topic": body.topic or "",
                "type": post_type,
                "medias": [media_obj],
                "meta": {"title": "", "description": "", "url": ""},
                "additionalInfo": additional_info,
                "replies": replies,
                "accountId": acc_id,
                "scheduleAt": normalized_schedule_at,
            }

            schedule_result = await repliz_post(
                "/public/schedule", json_body=payload
            )
            schedule_id = (
                schedule_result.get("scheduleId")
                or schedule_result.get("_id")
                or schedule_result.get("id")
                if isinstance(schedule_result, dict)
                else None
            )

            successful_schedules.append({
                "accountId": acc_id,
                "scheduleId": schedule_id,
                "result": schedule_result,
            })
            logger.info(
                f"Successfully scheduled post for account {acc_id} (scheduleId: {schedule_id})"
            )
        except HTTPException as he:
            logger.warning(
                f"Repliz schedule HTTP error for account {acc_id}: {he.detail}"
            )
            failed_schedules.append(
                {"accountId": acc_id, "error": str(he.detail)}
            )
        except Exception as e:
            logger.error(f"Repliz schedule failed for account {acc_id}: {e}")
            failed_schedules.append({"accountId": acc_id, "error": str(e)})

    # If all accounts failed, return error
    if not successful_schedules and failed_schedules:
        first_err = failed_schedules[0]["error"]
        raise HTTPException(
            status_code=502,
            detail=f"Gagal posting ke semua akun: {first_err}",
        )

    return {
        "success": True,
        "drive": drive_result,
        "schedules": successful_schedules,
        "errors": failed_schedules,
        "count": len(successful_schedules),
        "total": len(target_account_ids),
    }


@publish_router.get("/status")
async def publish_status(_user=Depends(get_current_user)):
    """Check if publishing credentials are configured."""
    from src.infrastructure.social_compliance import resolve_public_media_base_url

    public_url = resolve_public_media_base_url()
    return {
        "public_url_configured": bool(public_url),
        "public_url": public_url,
        "gdrive_configured": gdrive_uploader.is_configured,
        "repliz_configured": bool(
            settings.REPLIZ_ACCESS_KEY and settings.REPLIZ_SECRET_KEY
        ),
    }
