"""Publish endpoint — upload video to Repliz Storage then schedule post.

Flow: clip final video → Repliz Storage (3-step upload) → Repliz schedule API
"""
import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.config import settings
from src.presentation.routes.auth import get_current_user
from src.infrastructure.clip_outputs import find_final_clip
from src.presentation.routes.social.helpers import repliz_post, repliz_get, repliz_auth_header

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


async def _upload_to_repliz_storage(file_path: str, filename: str) -> str:
    """Upload file to Repliz Storage (3-step flow) and return public URL.

    1. Init file → get presigned upload URL
    2. PUT binary to presigned URL
    3. Complete → file accessible at storage.repliz.com
    """
    file_size = os.path.getsize(file_path)
    ext = os.path.splitext(file_path)[1].lower()
    mime_map = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
    }
    mimetype = mime_map.get(ext, "video/mp4")

    # Step 1: Init
    init_data = await repliz_post("/public/storage/file/init", json_body={
        "filename": filename,
        "size": file_size,
        "mimetype": mimetype,
    })
    if not init_data or "upload" not in init_data:
        raise RuntimeError(f"Repliz storage init failed: {init_data}")

    file_id = init_data["id"]
    upload_url = init_data["upload"]
    public_url = init_data["url"]

    logger.info(f"Repliz storage init: id={file_id}, uploading {file_size} bytes")

    # Step 2: Upload binary to presigned URL (direct to Cloudflare R2)
    async with httpx.AsyncClient(timeout=300) as client:
        with open(file_path, "rb") as f:
            file_data = f.read()
        resp = await client.put(
            upload_url,
            content=file_data,
            headers={"Content-Type": mimetype},
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Repliz storage upload failed: HTTP {resp.status_code} - {resp.text[:200]}")

    logger.info(f"Repliz storage upload complete: {filename}")

    # Step 3: Complete
    headers = repliz_auth_header()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.REPLIZ_BASE_URL}/public/storage/file/{file_id}/complete",
            headers=headers,
        )
        if resp.status_code not in (200, 201, 204):
            raise RuntimeError(f"Repliz storage complete failed: HTTP {resp.status_code}")

    logger.info(f"Repliz storage file ready: {public_url}")
    return public_url


@publish_router.post("")
async def publish_clip(body: PublishRequest, _user=Depends(get_current_user)):
    """Upload clip to Repliz Storage and schedule post.

    1. Locate final video file on disk
    2. Upload to Repliz Storage (Cloudflare R2)
    3. Create schedule with storage.repliz.com URL
    """
    # Check Repliz configured
    if not settings.REPLIZ_ACCESS_KEY or not settings.REPLIZ_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="Repliz credentials not configured"
        )

    # Locate video file
    output_dir = os.path.join(settings.OUTPUT_DIR, body.jobId)
    if not os.path.isdir(output_dir):
        raise HTTPException(status_code=404, detail="Job not found")

    clip_final = find_final_clip(output_dir, body.clipRank)
    if not clip_final:
        raise HTTPException(
            status_code=404,
            detail=f"Final video for clip #{body.clipRank} not found"
        )

    # Upload to Repliz Storage
    try:
        filename = f"{body.jobId}_clip{body.clipRank}.mp4"
        video_url = await _upload_to_repliz_storage(clip_final, filename)
    except Exception as e:
        logger.error(f"Repliz storage upload failed: {e}")
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {str(e)}")

    # Schedule on Repliz
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
        "storage_url": video_url,
        "schedule": schedule_result,
    }


@publish_router.get("/status")
async def publish_status(_user=Depends(get_current_user)):
    """Check if publishing is configured."""
    return {
        "repliz_configured": bool(settings.REPLIZ_ACCESS_KEY and settings.REPLIZ_SECRET_KEY),
    }
