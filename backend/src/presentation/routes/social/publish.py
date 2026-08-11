"""Publish endpoint — upload video to Google Drive then schedule via Repliz.

Flow: clip final video → Google Drive (public link) → Repliz schedule API
"""
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.config import settings
from src.presentation.routes.auth import get_current_user
from src.infrastructure.gdrive_uploader import gdrive_uploader
from src.infrastructure.clip_outputs import find_final_clip
from src.presentation.routes.social.helpers import repliz_post

logger = logging.getLogger(__name__)
publish_router = APIRouter(prefix="/publish", tags=["social-publish"])


class PublishRequest(BaseModel):
    """Request to publish a clip to social media."""
    jobId: str
    clipRank: int
    accountId: str
    caption: str = ""
    title: str = ""
    scheduleAt: str  # ISO 8601
    type: str = "video"  # video, reel


@publish_router.post("")
async def publish_clip(body: PublishRequest, _user=Depends(get_current_user)):
    """Upload clip to Google Drive and schedule post via Repliz.

    1. Locate final video file on disk
    2. Upload to Google Drive (service account)
    3. Get public direct link
    4. Create schedule on Repliz with that link
    """
    # Check Google Drive configured
    if not gdrive_uploader.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Google Drive not configured. Set GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE in .env"
        )

    # Locate video file using same logic as the clip serving endpoint
    output_dir = os.path.join(settings.OUTPUT_DIR, body.jobId)
    if not os.path.isdir(output_dir):
        raise HTTPException(status_code=404, detail="Job not found")

    clip_final = find_final_clip(output_dir, body.clipRank)
    if not clip_final:
        raise HTTPException(
            status_code=404,
            detail=f"Final video for clip #{body.clipRank} not found"
        )

    # Upload to Google Drive
    try:
        filename = f"{body.jobId}_clip{body.clipRank}.mp4"
        drive_result = gdrive_uploader.upload_video(clip_final, filename=filename)
    except Exception as e:
        logger.error(f"Google Drive upload failed: {e}")
        raise HTTPException(status_code=502, detail=f"Google Drive upload failed: {str(e)}")

    # Schedule on Repliz
    video_url = drive_result["direct_link"]
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
            "accountId": body.accountId,
            "scheduleAt": body.scheduleAt,
        }
        schedule_result = await repliz_post("/public/schedule", json_body=payload)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Repliz schedule failed: {e}")
        raise HTTPException(status_code=502, detail=f"Schedule failed: {str(e)}")

    return {
        "success": True,
        "drive": drive_result,
        "schedule": schedule_result,
    }


@publish_router.get("/status")
async def publish_status(_user=Depends(get_current_user)):
    """Check if Google Drive publishing is configured."""
    return {
        "gdrive_configured": gdrive_uploader.is_configured,
        "repliz_configured": bool(settings.REPLIZ_ACCESS_KEY and settings.REPLIZ_SECRET_KEY),
    }
