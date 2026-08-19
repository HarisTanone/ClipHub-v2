"""Publish endpoint — upload video to Google Drive then schedule post via Repliz.

Flow: clip final video → Google Drive (public link) → Repliz schedule API
"""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.config import settings
from src.presentation.routes.auth import get_current_user
from src.infrastructure.clip_outputs import find_final_clip
from src.infrastructure.gdrive_uploader import gdrive_uploader
from src.presentation.routes.social.helpers import repliz_post

logger = logging.getLogger(__name__)
publish_router = APIRouter(prefix="/publish", tags=["social-publish"])


class PublishRequest(BaseModel):
    """Request to publish a clip or AI generated video to social media (single or multiple accounts)."""
    jobId: str
    clipRank: int | None = None
    videoSource: str | None = None  # "clip" or "video_generator"
    accountId: str | None = None
    accountIds: list[str] | None = None
    caption: str = ""
    title: str = ""
    scheduleAt: str  # ISO 8601
    type: str = "video"  # video, reel


@publish_router.post("")
async def publish_clip(body: PublishRequest, _user=Depends(get_current_user)):
    """Upload clip or AI generated video to Google Drive once and schedule posts across all selected accounts via Repliz."""
    # Resolve target account IDs (support both accountIds list and legacy single accountId)
    target_account_ids: list[str] = []
    if body.accountIds:
        target_account_ids = [aid.strip() for aid in body.accountIds if aid and str(aid).strip()]
    elif body.accountId:
        target_account_ids = [body.accountId.strip()]

    if not target_account_ids:
        raise HTTPException(
            status_code=400,
            detail="Pilih minimal satu akun media sosial untuk posting."
        )

    # Check config
    if not gdrive_uploader.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Google Drive not configured. Set GOOGLE_DRIVE_CLIENT_ID, GOOGLE_DRIVE_CLIENT_SECRET, GOOGLE_DRIVE_REFRESH_TOKEN in .env"
        )
    if not settings.REPLIZ_ACCESS_KEY or not settings.REPLIZ_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Repliz credentials not configured")

    # Locate video file (from Video Generator or ClipHub clips)
    video_file = None
    upload_filename = ""

    is_video_gen = body.videoSource == "video_generator" or body.jobId.startswith("vg_")
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
            raise HTTPException(status_code=404, detail="Video generator job not found")
        if not vg_job.output_path or not os.path.exists(vg_job.output_path):
            raise HTTPException(status_code=404, detail="Final generated video not found or not ready")
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
                detail=f"Final video for clip #{clip_rank} not found"
            )
        video_file = clip_final
        upload_filename = f"{body.jobId}_clip{clip_rank}.mp4"

    # Upload to Google Drive ONCE
    try:
        drive_result = gdrive_uploader.upload_video(video_file, filename=upload_filename)
    except Exception as e:
        logger.error(f"Google Drive upload failed: {e}")
        raise HTTPException(status_code=502, detail=f"Google Drive upload failed: {str(e)}")

    # Schedule on Repliz for each account using the public Google Drive URL
    video_url = drive_result.get("direct_link") or drive_result.get("web_view_link")
    successful_schedules = []
    failed_schedules = []

    for acc_id in target_account_ids:
        try:
            payload = {
                "title": body.title,
                "description": body.caption,
                "type": body.type,
                "medias": [
                    {
                        "alt": "",
                        "customThumbnail": False,
                        "type": "video",
                        "thumbnail": "",
                        "url": video_url,
                    }
                ],
                "meta": {"title": "", "description": "", "url": ""},
                "additionalInfo": {
                    "isAiGenerated": False,
                    "isDraft": False,
                    "isAutoAddMusic": False,
                    "collaborators": [],
                    "mentions": [],
                    "music": {"id": "", "artist": "", "name": "", "thumbnail": ""},
                    "products": [],
                    "tags": [],
                    "targetCountries": [],
                },
                "replies": [],
                "accountId": acc_id,
                "scheduleAt": body.scheduleAt,
            }
            schedule_result = await repliz_post("/public/schedule", json_body=payload)
            successful_schedules.append({
                "accountId": acc_id,
                "result": schedule_result,
            })
            logger.info(f"Successfully scheduled post for account {acc_id} on clip {body.clipRank}")
        except HTTPException as he:
            logger.warning(f"Repliz schedule HTTP error for account {acc_id}: {he.detail}")
            failed_schedules.append({"accountId": acc_id, "error": str(he.detail)})
        except Exception as e:
            logger.error(f"Repliz schedule failed for account {acc_id}: {e}")
            failed_schedules.append({"accountId": acc_id, "error": str(e)})

    # If all accounts failed, return error
    if not successful_schedules and failed_schedules:
        first_err = failed_schedules[0]["error"]
        raise HTTPException(
            status_code=502,
            detail=f"Gagal posting ke semua akun: {first_err}"
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
    """Check if publishing is configured."""
    return {
        "gdrive_configured": gdrive_uploader.is_configured,
        "repliz_configured": bool(settings.REPLIZ_ACCESS_KEY and settings.REPLIZ_SECRET_KEY),
    }
