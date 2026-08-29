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
    if not gdrive_uploader.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Google Drive belum dikonfigurasi. Pastikan GOOGLE_DRIVE_CLIENT_ID, GOOGLE_DRIVE_CLIENT_SECRET, dan GOOGLE_DRIVE_REFRESH_TOKEN sudah terisi.",
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

    # 4. Transcode to 100% compliant video format and upload to Google Drive
    try:
        compliant_video = ensure_social_compliant_video(video_file)
    except Exception as e:
        logger.warning(f"Video compliance transcode fallback: {e}")
        compliant_video = video_file

    try:
        drive_result = gdrive_uploader.upload_video(
            compliant_video, filename=upload_filename
        )
    except Exception as e:
        logger.error(f"Google Drive upload failed: {e}")
        raise HTTPException(
            status_code=502, detail=f"Google Drive upload failed: {str(e)}"
        )

    video_url = drive_result.get("direct_link") or drive_result.get(
        "web_view_link"
    )
    if not video_url:
        raise HTTPException(
            status_code=502,
            detail="Gagal mendapatkan link download langsung dari Google Drive.",
        )

    # 4b. Optional compliant thumbnail (captured at hook frame 1.5s)
    thumb_url = None
    if gdrive_uploader.is_configured:
        try:
            if not is_video_gen and body.clipRank is not None:
                rank_num = body.clipRank
                thumb_dir = os.path.join(settings.OUTPUT_DIR, body.jobId, "thumbnail")
                candidate_thumb = os.path.join(thumb_dir, f"clip_{rank_num:02d}.jpg")
                if not os.path.exists(candidate_thumb):
                    candidate_thumb = os.path.join(thumb_dir, f"clip_{rank_num:02d}_thumb.jpg")

                comp_thumb = ensure_social_compliant_thumbnail(
                    thumb_path=candidate_thumb if os.path.exists(candidate_thumb) else None,
                    video_path=compliant_video,
                    output_path=os.path.join(thumb_dir, f"clip_{rank_num:02d}_social.jpg"),
                    seek=1.5,
                )
                if comp_thumb and os.path.exists(comp_thumb):
                    thumb_res = gdrive_uploader.upload_image(
                        comp_thumb, filename=f"{body.jobId}_clip{rank_num}_thumb.jpg"
                    )
                    thumb_url = thumb_res.get("direct_link") or thumb_res.get("web_view_link")
            elif is_video_gen:
                vg_thumb_out = os.path.join(settings.VIDEO_GEN_OUTPUT_DIR, body.jobId, "thumb.jpg")
                comp_thumb = ensure_social_compliant_thumbnail(
                    video_path=compliant_video,
                    output_path=vg_thumb_out,
                    seek=1.5,
                )
                if comp_thumb and os.path.exists(comp_thumb):
                    thumb_res = gdrive_uploader.upload_image(
                        comp_thumb, filename=f"vg_{body.jobId}_thumb.jpg"
                    )
                    thumb_url = thumb_res.get("direct_link") or thumb_res.get("web_view_link")
        except Exception as e:
            logger.warning(f"Thumbnail upload failed in publish route: {e}")

    # 5. Extract hashtags for tags if tags list is empty
    tags = list(body.tags)
    if not tags and body.caption:
        hashtag_matches = re.findall(r"#(\w+)", body.caption)
        if hashtag_matches:
            tags = hashtag_matches[:10]

    # 6. Schedule on Repliz for each target account
    successful_schedules = []
    failed_schedules = []

    media_obj: Dict[str, Any] = {
        "alt": body.title or "Video",
        "customThumbnail": bool(thumb_url),
        "type": "video",
        "url": video_url,
    }
    if thumb_url:
        media_obj["thumbnail"] = thumb_url

    for acc_id in target_account_ids:
        try:
            payload = {
                "title": body.title or "Video",
                "description": body.caption,
                "topic": body.topic or "",
                "type": body.type or "video",
                "medias": [media_obj],
                "meta": {"title": "", "description": "", "url": ""},
                "additionalInfo": {
                    "isAiGenerated": body.isAiGenerated,
                    "isDraft": body.isDraft,
                    "isAutoAddMusic": False,
                    "collaborators": body.collaborators,
                    "mentions": body.mentions,
                    "music": {
                        "id": "",
                        "artist": "",
                        "name": "",
                        "thumbnail": "",
                    },
                    "products": [],
                    "tags": tags,
                    "targetCountries": body.targetCountries,
                },
                "replies": (
                    [{"text": body.firstReply.strip(), "order": 1}]
                    if body.firstReply and body.firstReply.strip()
                    else []
                ),
                "accountId": acc_id,
                "scheduleAt": body.scheduleAt,
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
    return {
        "gdrive_configured": gdrive_uploader.is_configured,
        "repliz_configured": bool(
            settings.REPLIZ_ACCESS_KEY and settings.REPLIZ_SECRET_KEY
        ),
    }
