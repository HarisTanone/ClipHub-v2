"""Analyze-only API routes — download + AI analysis without full pipeline processing.

POST /api/jobs/analyze-only  → download video + Gemini analysis → return clips timestamps
GET  /api/jobs/{job_id}/source-video → stream downloaded source video for frontend preview
"""
import asyncio
import json
import logging
import os
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from src.application.services import JobService
from src.config import settings
from src.infrastructure.auth import decode_access_token, is_superadmin
from src.presentation.auth_deps import CurrentUser, get_current_user
from src.presentation.dependencies import get_job_service

router = APIRouter(prefix="/jobs", tags=["analyze"])
logger = logging.getLogger(__name__)


# ─── Request / Response Models ─────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    youtube_url: str

    @field_validator("youtube_url")
    @classmethod
    def url_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("URL tidak boleh kosong")
        return v.strip()


class ClipCandidate(BaseModel):
    rank: int
    start: float
    end: float
    duration: float
    score: int | None = None
    hook: str | None = None
    reason: str | None = None
    content_type: str | None = None
    speaker_energy: str | None = None


class AnalyzeResponse(BaseModel):
    success: bool = True
    job_id: str
    video_duration: float
    video_title: str = ""
    thumbnail: str = ""
    clips: list[ClipCandidate]
    creative_direction: dict | None = None


# ─── Analyze-Only Endpoint ─────────────────────────────────────────────────────

@router.post("/analyze-only", response_model=AnalyzeResponse)
async def analyze_only(
    body: AnalyzeRequest,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Download video + run AI analysis only.

    Returns clip candidates with timestamps (start/end/score/hook) so the user
    can review and adjust timeframes before submitting for full processing.
    The downloaded video is kept at {DOWNLOAD_DIR}/{job_id}.mp4 for streaming.
    """
    url = body.youtube_url

    # ─── Step 1: Validate ───────────────────────────────────────────
    downloader = service._downloader
    valid, error_or_title, duration = await downloader.validate_url(url)
    if not valid:
        raise HTTPException(status_code=400, detail=error_or_title or "URL tidak valid")

    video_title = error_or_title or ""
    if not duration or duration <= 0:
        raise HTTPException(status_code=400, detail="Gagal membaca durasi video")

    # Generate a temporary job_id for this analyze session
    import secrets
    job_id = f"analyze_{secrets.token_hex(6)}"

    # Check cache and prepare paths
    from src.infrastructure.cache_manager import CacheManager
    cache = CacheManager()
    try:
        cache.cleanup_expired_analyze_sessions(86400)
    except Exception:
        pass
    video_id = cache.extract_video_id(url)

    video_path = os.path.join(settings.DOWNLOAD_DIR, f"{job_id}.mp4")
    os.makedirs(settings.DOWNLOAD_DIR, exist_ok=True)

    # ─── Task A: Video Download / Cache Link (Parallel) ─────────────
    async def _prepare_video():
        cached_video = cache.get_video_path(video_id) if video_id else None
        if cached_video and os.path.exists(cached_video):
            import shutil
            try:
                os.link(cached_video, video_path)
            except OSError:
                shutil.copy2(cached_video, video_path)
            logger.info(f"[{job_id}] Download SKIPPED (cached: {video_id})")
        else:
            logger.info(f"[{job_id}] Downloading video in parallel: {url}")
            await downloader.download_video(url, video_path)
            if video_id and os.path.exists(video_path):
                cache.save_video(video_id, video_path)

        if not os.path.exists(video_path):
            raise HTTPException(status_code=500, detail="Download gagal — file tidak ditemukan")

    # ─── Task B: AI Analysis (Gemini in Parallel) ───────────────────
    async def _run_gemini():
        cached_analysis = cache.load_analysis(video_id, "v1") if video_id else None
        if cached_analysis and "clips" in cached_analysis:
            logger.info(f"[{job_id}] Gemini analysis SKIPPED (cached: {len(cached_analysis['clips'])} clips)")
            return cached_analysis

        logger.info(f"[{job_id}] Running Gemini analysis in parallel...")
        # In analyze-review step, request a rich set of 8-10 candidate clips for the user to choose from
        max_clips = min(10, max(5, int(duration / 70))) if duration >= 300 else service._calc_max_clips(duration)
        gemini_call = lambda: service._gemini.analyze(url, duration, max_clips)
        result = await service._gemini_call(gemini_call)

        if video_id and result and "clips" in result:
            cache.save_analysis(video_id, result, version="v1")
        return result

    # ─── Execute Video Download and Gemini Analysis Concurrently ─────
    _, gemini_result = await asyncio.gather(_prepare_video(), _run_gemini())

    if not gemini_result or "clips" not in gemini_result or not gemini_result["clips"]:
        raise HTTPException(status_code=500, detail="AI analysis gagal — tidak ada clip candidates")

    # ─── Build response ─────────────────────────────────────────────
    raw_clips = gemini_result["clips"]
    clips_out: list[ClipCandidate] = []
    for i, c in enumerate(raw_clips, start=1):
        start = float(c.get("start", 0))
        end = float(c.get("end", 0))
        clips_out.append(ClipCandidate(
            rank=c.get("rank", i),
            start=start,
            end=end,
            duration=round(end - start, 2),
            score=c.get("score"),
            hook=c.get("hook"),
            reason=c.get("reason"),
            content_type=c.get("content_type"),
            speaker_energy=c.get("speaker_energy"),
        ))

    # Thumbnail from YouTube
    thumbnail = ""
    if video_id:
        thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

    # Store analyze session metadata for source-video streaming
    meta_path = os.path.join(settings.DOWNLOAD_DIR, f"{job_id}.meta.json")
    with open(meta_path, "w") as f:
        json.dump({
            "job_id": job_id,
            "youtube_url": url,
            "video_id": video_id,
            "video_title": video_title,
            "video_duration": duration,
            "video_path": video_path,
            "clips": [c.model_dump() for c in clips_out],
            "creative_direction": gemini_result.get("creative_direction"),
            "created_at": time.time(),
        }, f)

    return AnalyzeResponse(
        success=True,
        job_id=job_id,
        video_duration=duration,
        video_title=video_title,
        thumbnail=thumbnail,
        clips=clips_out,
        creative_direction=gemini_result.get("creative_direction"),
    )


# ─── Source Video Streaming ────────────────────────────────────────────────────

@router.get("/{job_id}/source-video")
async def stream_source_video(
    job_id: str,
    request: Request,
    token: str = Query(default=""),
):
    """Stream the downloaded source video for frontend preview/scrubbing.

    Supports HTTP Range requests for efficient seeking.
    Works with both analyze_{id} temporary sessions and real job_{id} jobs.
    Accepts auth via Bearer header OR ?token= query param (for <video src>).
    """
    # Resolve user from Bearer header or query param token
    resolved_user = None
    # Try Bearer header first
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        bearer_token = auth_header[7:]
        payload = decode_access_token(bearer_token)
        if payload:
            resolved_user = CurrentUser(
                user_id=payload.get("user_id", 0),
                email=payload.get("email", ""),
                role=payload.get("role", ""),
                permissions=payload.get("permissions", []),
            )
    # Fallback to query param token
    if resolved_user is None and token:
        payload = decode_access_token(token)
        if payload:
            resolved_user = CurrentUser(
                user_id=payload.get("user_id", 0),
                email=payload.get("email", ""),
                role=payload.get("role", ""),
                permissions=payload.get("permissions", []),
            )
    if resolved_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Try analyze session path first, then regular job path
    video_path = os.path.join(settings.DOWNLOAD_DIR, f"{job_id}.mp4")
    if not os.path.exists(video_path):
        # Fallback: check if it's a real job with downloaded video
        alt_path = os.path.join(settings.DOWNLOAD_DIR, f"{job_id}.mp4")
        if not os.path.exists(alt_path):
            raise HTTPException(status_code=404, detail="Source video not found")
        video_path = alt_path

    file_size = os.path.getsize(video_path)
    range_header = request.headers.get("range")

    if range_header:
        # Parse range: "bytes=0-" or "bytes=1024-2048"
        range_str = range_header.replace("bytes=", "")
        parts = range_str.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        def iter_range():
            with open(video_path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            iter_range(),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
                "Content-Disposition": f'inline; filename="{job_id}.mp4"',
                "Cache-Control": "public, max-age=3600",
            },
        )
    else:
        def iter_file():
            with open(video_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    yield chunk

        return StreamingResponse(
            iter_file(),
            media_type="video/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
                "Content-Disposition": f'inline; filename="{job_id}.mp4"',
                "Cache-Control": "public, max-age=3600",
            },
        )
