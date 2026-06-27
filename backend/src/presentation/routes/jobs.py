"""Job API routes — POST /jobs, GET /jobs/{id}, GET /jobs/{id}/error, GET /jobs/{id}/clips."""
import os
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from src.application.services import JobService
from src.config import settings
from src.presentation.auth_deps import CurrentUser, get_current_user, get_optional_user
from src.presentation.dependencies import get_job_service
from src.presentation.schemas.jobs import (
    ClipDataResponse,
    CreateJobRequest,
    JobErrorResponse,
    JobResponse,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _stream_video(file_path: str, request: Request, filename: str):
    """Serve video with proper HTTP Range request support for seeking/streaming."""
    file_size = os.path.getsize(file_path)
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
            with open(file_path, "rb") as f:
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
                "Content-Disposition": f'inline; filename="{filename}"',
            },
        )
    else:
        return FileResponse(
            file_path,
            media_type="video/mp4",
            filename=filename,
            headers={"Accept-Ranges": "bytes"},
        )


async def _check_job_ownership(job, user: CurrentUser):
    """Verify user owns this job. Superadmin bypasses."""
    if user.is_superadmin:
        return
    if job.user_id and job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")


@router.post("", status_code=201, response_model=JobResponse)
async def create_job(
    request: CreateJobRequest,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Buat job baru dari URL YouTube. Jika URL sudah ada yang aktif, return job yang ada.

    Jika force_reprocess=False (default), URL deduplication akan return cached result.
    Jika force_reprocess=True, skip dedup dan proses ulang dari awal.
    """
    job, is_cached = await service.create_job(
        request.youtube_url,
        force_reprocess=request.force_reprocess,
        style_preset=request.style_preset,
        target_aspect_ratio=request.target_aspect_ratio,
        hook_engine=request.hook_engine,
        hook_style=request.hook_style,
        broll_enabled=request.broll_enabled,
        autogrid_enabled=request.autogrid_enabled,
        # v3.0 Remotion fields
        use_remotion=request.use_remotion,
        ai_layer_enabled=request.ai_layer_enabled,
        threejs_enabled=request.threejs_enabled,
        remotion_quality=request.remotion_quality,
        # Custom style configs
        hook_style_config=request.hook_style_config,
        subtitle_style_config=request.subtitle_style_config,
        # Smart features
        smart_camera=request.smart_camera,
        smart_subtitle_position=request.smart_subtitle_position,
        # User ownership
        user_id=user.id,
        # V2 pipeline routing
        is_superadmin=user.is_superadmin,
    )
    return JobResponse(
        job_id=job.job_id,
        youtube_url=job.youtube_url,
        status=job.status.value,
        video_duration=job.video_duration,
        render_progress=job.render_progress,
        error_message=job.error_message,
        clips_data=job.clips_data,
        clips_total=job.clips_total,
        clips_success=job.clips_success,
        clips_failed=job.clips_failed,
        is_cached=is_cached,
        style_preset=job.style_preset,
        target_aspect_ratio=job.target_aspect_ratio,
        use_remotion=job.use_remotion,
        ai_layer_enabled=job.ai_layer_enabled,
        threejs_enabled=job.threejs_enabled,
        remotion_quality=job.remotion_quality,
        pipeline_version=job.pipeline_version,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Ambil status dan data job berdasarkan job_id."""
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    await _check_job_ownership(job, user)
    return JobResponse(
        job_id=job.job_id,
        youtube_url=job.youtube_url,
        status=job.status.value,
        video_duration=job.video_duration,
        render_progress=job.render_progress,
        error_message=job.error_message,
        clips_data=job.clips_data,
        clips_total=job.clips_total,
        clips_success=job.clips_success,
        clips_failed=job.clips_failed,
        pipeline_version=job.pipeline_version,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/{job_id}/error", response_model=JobErrorResponse)
async def get_job_error(
    job_id: str,
    service: JobService = Depends(get_job_service),
):
    """Ambil detail error untuk job yang gagal."""
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    if job.status.value not in ("failed", "timeout"):
        raise HTTPException(
            status_code=404,
            detail="Job tidak dalam status failed/timeout",
        )
    return JobErrorResponse(
        job_id=job.job_id,
        error_message=job.error_message,
        error_details=job.error_details,
    )


@router.get("/{job_id}/clips", response_model=ClipDataResponse)
async def get_job_clips(
    job_id: str,
    service: JobService = Depends(get_job_service),
):
    """
    Ambil clip data lengkap untuk Remotion rendering.
    Berisi subtitle, hook, word-level timestamps, dan highlight info.
    """
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")

    clips = None
    if job.clips_data and "clips" in job.clips_data:
        clips = job.clips_data["clips"]

    return ClipDataResponse(
        job_id=job.job_id,
        status=job.status.value,
        clips=clips,
    )


@router.get("/{job_id}/clips/{clip_rank}/video")
async def get_clip_video(
    job_id: str,
    clip_rank: int,
    request: Request,
    service: JobService = Depends(get_job_service),
):
    """Download trimmed clip video file."""
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")

    clip_path = f"{settings.OUTPUT_DIR}/{job_id}/clip_{clip_rank:02d}.mp4"
    if not os.path.exists(clip_path):
        raise HTTPException(status_code=404, detail="File clip tidak ditemukan")

    return _stream_video(clip_path, request, f"{job_id}_clip_{clip_rank:02d}.mp4")


@router.get("/{job_id}/clips/{clip_rank}/raw")
async def get_clip_raw(
    job_id: str,
    clip_rank: int,
    request: Request,
    service: JobService = Depends(get_job_service),
):
    """Download raw trimmed clip (raw/clip_{n}.mp4)."""
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")

    raw_path = f"{settings.OUTPUT_DIR}/{job_id}/raw/clip_{clip_rank}.mp4"
    if not os.path.exists(raw_path):
        raw_path = f"{settings.OUTPUT_DIR}/{job_id}/clip_{clip_rank:02d}.mp4"
    if not os.path.exists(raw_path):
        raise HTTPException(status_code=404, detail="File raw clip tidak ditemukan")

    return _stream_video(raw_path, request, f"clip_{clip_rank}_raw.mp4")


@router.get("/{job_id}/clips/{clip_rank}/final")
async def get_clip_final(
    job_id: str,
    clip_rank: int,
    request: Request,
    service: JobService = Depends(get_job_service),
):
    """Download final encoded clip (final/clip_{n}_final.mp4)."""
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")

    final_path = f"{settings.OUTPUT_DIR}/{job_id}/final/clip_{clip_rank}_final.mp4"
    if not os.path.exists(final_path):
        final_path = f"{settings.OUTPUT_DIR}/{job_id}/clip_{clip_rank:02d}_final.mp4"
    if not os.path.exists(final_path):
        raise HTTPException(status_code=404, detail="File final clip tidak ditemukan")

    return _stream_video(final_path, request, f"clip_{clip_rank}_final.mp4")


@router.get("/{job_id}/clips/{clip_rank}/thumb")
async def get_clip_thumb(
    job_id: str,
    clip_rank: int,
    service: JobService = Depends(get_job_service),
):
    """Download clip thumbnail. Auto-generates from video if not found."""
    import subprocess

    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")

    output_dir = f"{settings.OUTPUT_DIR}/{job_id}"

    # Check existing thumbnails
    thumb_candidates = [
        f"{output_dir}/thumbnail/clip_{clip_rank:02d}.jpg",
        f"{output_dir}/thumbnail/clip_{clip_rank}_thumb.jpg",
        f"{output_dir}/thumbnail/clip_{clip_rank:02d}_thumb.jpg",
        f"{output_dir}/clip_{clip_rank:02d}_thumb.jpg",
    ]
    for path in thumb_candidates:
        if os.path.exists(path):
            return FileResponse(path, media_type="image/jpeg", filename=f"clip_{clip_rank}_thumb.jpg")

    # Auto-generate thumbnail from video file
    video_candidates = [
        f"{output_dir}/clip_{clip_rank:02d}_final.mp4",
        f"{output_dir}/final/clip_{clip_rank:02d}.mp4",
        f"{output_dir}/final/clip_{clip_rank}_final.mp4",
        f"{output_dir}/final/clip_{clip_rank:02d}_final.mp4",
        f"{output_dir}/clip_{clip_rank:02d}.mp4",
        f"{output_dir}/raw/clip_{clip_rank:02d}.mp4",
        f"{output_dir}/raw/clip_{clip_rank}.mp4",
    ]
    source_video = None
    for vp in video_candidates:
        if os.path.exists(vp):
            source_video = vp
            break

    if not source_video:
        raise HTTPException(status_code=404, detail="No video source for thumbnail")

    # Generate thumbnail at 2 seconds (or 1s for short clips)
    os.makedirs(f"{output_dir}/thumbnail", exist_ok=True)
    thumb_path = f"{output_dir}/thumbnail/clip_{clip_rank:02d}_thumb.jpg"

    try:
        import asyncio
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "ffmpeg", "-y", "-ss", "2", "-i", source_video,
                "-vframes", "1", "-q:v", "3",
                "-vf", "scale='min(640,iw)':'min(360,ih)':force_original_aspect_ratio=decrease",
                thumb_path,
            ],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0 and os.path.exists(thumb_path):
            return FileResponse(thumb_path, media_type="image/jpeg", filename=f"clip_{clip_rank}_thumb.jpg")
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Thumbnail generation failed")


# ─── Additional Endpoints for Frontend Integration ────────────────────────────

@router.get("", response_model=None)
async def list_jobs(
    status: str = None,
    limit: int = 20,
    offset: int = 0,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """List jobs with optional status filter and pagination.

    Query params:
    - status: Filter by status (e.g. 'completed', 'failed', 'processing')
    - limit: Max results (default 20, max 100)
    - offset: Pagination offset

    Superadmin sees all jobs. Regular users see only their own.
    """
    from sqlalchemy import select, func, desc
    from src.infrastructure.database import JobModel, async_session

    limit = min(limit, 100)

    async with async_session() as session:
        query = select(JobModel).order_by(desc(JobModel.created_at))

        if status:
            query = query.where(JobModel.status == status)

        # User isolation: non-superadmin only sees own jobs
        if not user.is_superadmin:
            query = query.where(JobModel.user_id == user.id)

        # Count total
        count_query = select(func.count()).select_from(JobModel)
        if status:
            count_query = count_query.where(JobModel.status == status)
        if not user.is_superadmin:
            count_query = count_query.where(JobModel.user_id == user.id)
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        query = query.offset(offset).limit(limit)
        result = await session.execute(query)
        models = result.scalars().all()

    jobs = []
    for model in models:
        jobs.append({
            "job_id": model.job_id,
            "youtube_url": model.youtube_url,
            "status": model.status,
            "video_duration": model.video_duration,
            "clips_total": model.clips_total,
            "clips_success": model.clips_success,
            "clips_failed": model.clips_failed,
            "style_preset": model.style_preset,
            "target_aspect_ratio": model.target_aspect_ratio,
            "created_at": model.created_at.isoformat() if model.created_at else None,
            "updated_at": model.updated_at.isoformat() if model.updated_at else None,
        })

    return {
        "success": True,
        "data": jobs,
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        },
    }


@router.get("/{job_id}/detail")
async def get_job_detail(
    job_id: str,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Get comprehensive job detail including clips, files, and metadata."""
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await _check_job_ownership(job, user)

    # Gather available files (supports both structured subdirs and flat layout)
    output_dir = f"{settings.OUTPUT_DIR}/{job_id}"
    files = {"raw": [], "final": [], "thumbnails": []}

    if os.path.isdir(output_dir):
        raw_dir = os.path.join(output_dir, "raw")
        final_dir = os.path.join(output_dir, "final")
        thumb_dir = os.path.join(output_dir, "thumbnail")

        # Check structured subdirectories
        if os.path.isdir(raw_dir):
            files["raw"] = sorted([f for f in os.listdir(raw_dir) if f.endswith(".mp4")])
        if os.path.isdir(final_dir):
            files["final"] = sorted([f for f in os.listdir(final_dir) if f.endswith(".mp4")])
        if os.path.isdir(thumb_dir):
            files["thumbnails"] = sorted([f for f in os.listdir(thumb_dir) if f.endswith(".jpg")])

        # Fallback: scan flat layout (pipeline writes clip_01.mp4, clip_01_final.mp4 in root)
        if not files["raw"] and not files["final"]:
            root_files = os.listdir(output_dir)
            for f in sorted(root_files):
                if f.endswith("_final.mp4"):
                    files["final"].append(f)
                elif f.endswith(".mp4") and "_hooked" not in f and "_brolled" not in f and "_reframed" not in f:
                    files["raw"].append(f)
                elif f.endswith("_thumb.jpg"):
                    files["thumbnails"].append(f)

    # Extract clips info
    clips_info = []
    if job.clips_data and "clips" in job.clips_data:
        for clip in job.clips_data["clips"]:
            rank = clip.get("rank", 0)
            clips_info.append({
                "rank": rank,
                "score": clip.get("score"),
                "start": clip.get("start"),
                "end": clip.get("end"),
                "duration": round(clip.get("end", 0) - clip.get("start", 0), 1),
                "hook": clip.get("hook"),
                "reason": clip.get("reason"),
                "has_words": bool(clip.get("words")),
                "word_count": len(clip.get("words", [])),
                "has_final": any(f"clip_{rank}_final" in f or f"clip_{rank:02d}_final" in f for f in files["final"]),
                "has_thumbnail": True,  # Auto-generated on demand from video
            })

    return {
        "success": True,
        "data": {
            "job_id": job.job_id,
            "youtube_url": job.youtube_url,
            "status": job.status.value,
            "video_duration": job.video_duration,
            "style_preset": job.style_preset,
            "target_aspect_ratio": job.target_aspect_ratio,
            "error_message": job.error_message,
            "clips_total": job.clips_total,
            "clips_success": job.clips_success,
            "clips_failed": job.clips_failed,
            "clips": clips_info,
            "files": files,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        },
    }


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Cancel a running job. Only works for non-terminal jobs."""
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    terminal_statuses = {"completed", "failed", "timeout"}
    if job.status.value in terminal_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job in '{job.status.value}' status",
        )

    # Update status to failed with cancellation message
    from src.domain.entities import JobStatus
    await service._repo.update_status(job_id, JobStatus.FAILED, error_message="Cancelled by user")

    return {
        "success": True,
        "message": f"Job '{job_id}' cancelled",
        "previous_status": job.status.value,
    }


@router.get("/{job_id}/clips/{clip_rank}/detail")
async def get_clip_detail(
    job_id: str,
    clip_rank: int,
    service: JobService = Depends(get_job_service),
):
    """Get detailed information about a specific clip.

    Includes: timing, hook text, word timestamps, highlight info, file paths.
    """
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    clip_data = None
    if job.clips_data and "clips" in job.clips_data:
        for clip in job.clips_data["clips"]:
            if clip.get("rank") == clip_rank:
                clip_data = clip
                break

    if clip_data is None:
        raise HTTPException(status_code=404, detail=f"Clip #{clip_rank} not found")

    # Check file availability (supports both flat and structured layouts)
    output_dir = f"{settings.OUTPUT_DIR}/{job_id}"

    def _find_file(*candidates: str) -> bool:
        return any(os.path.exists(p) for p in candidates)

    has_raw = _find_file(
        f"{output_dir}/raw/clip_{clip_rank}.mp4",
        f"{output_dir}/raw/clip_{clip_rank:02d}.mp4",
        f"{output_dir}/clip_{clip_rank:02d}.mp4",
    )
    has_final = _find_file(
        f"{output_dir}/final/clip_{clip_rank}_final.mp4",
        f"{output_dir}/final/clip_{clip_rank:02d}_final.mp4",
        f"{output_dir}/clip_{clip_rank:02d}_final.mp4",
    )
    has_thumb = _find_file(
        f"{output_dir}/thumbnail/clip_{clip_rank}_thumb.jpg",
        f"{output_dir}/thumbnail/clip_{clip_rank:02d}_thumb.jpg",
        f"{output_dir}/clip_{clip_rank:02d}_thumb.jpg",
    )

    file_status = {"raw": has_raw, "final": has_final, "thumbnail": has_thumb or has_raw or has_final}

    return {
        "success": True,
        "data": {
            "job_id": job_id,
            "rank": clip_rank,
            "score": clip_data.get("score"),
            "start": clip_data.get("start"),
            "end": clip_data.get("end"),
            "duration": round(clip_data.get("end", 0) - clip_data.get("start", 0), 1),
            "hook": clip_data.get("hook"),
            "reason": clip_data.get("reason"),
            "words": clip_data.get("words", []),
            "highlights": clip_data.get("highlights", []),
            "file_status": file_status,
            "urls": {
                "raw": f"/api/jobs/{job_id}/clips/{clip_rank}/raw" if file_status["raw"] else None,
                "final": f"/api/jobs/{job_id}/clips/{clip_rank}/final" if file_status["final"] else None,
                "thumbnail": f"/api/jobs/{job_id}/clips/{clip_rank}/thumb" if file_status["thumbnail"] else None,
            },
        },
    }


# ─── Phase 6: Clip-Level Hook & Style Editing + Re-render ─────────────────────

from pydantic import BaseModel, Field
from typing import Optional as Opt


class EditHookRequest(BaseModel):
    """Edit hook text for a specific clip."""
    hook_text: str = Field(..., min_length=1, max_length=500)


class EditClipStyleRequest(BaseModel):
    """Override hook style for a specific clip."""
    hook_style: str = Field(..., min_length=1, max_length=50)
    hook_style_config: Opt[dict] = None  # Optional per-clip config overrides


class RerenderRequest(BaseModel):
    """Re-render a clip with optional style/hook overrides."""
    hook_text: Opt[str] = None  # Override hook text
    hook_style: Opt[str] = None  # Override hook style
    hook_style_config: Opt[dict] = None  # Optional config overrides


@router.patch("/{job_id}/clips/{clip_rank}/hook")
async def edit_clip_hook(
    job_id: str,
    clip_rank: int,
    body: EditHookRequest,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Edit hook text for a specific clip.

    Updates the hook text in clips_data JSON. Does NOT re-render automatically.
    Call POST .../rerender after editing to apply changes.
    """
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.clips_data or "clips" not in job.clips_data:
        raise HTTPException(status_code=400, detail="Job has no clips data")

    # Find clip
    clip_found = False
    old_hook = None
    for clip in job.clips_data["clips"]:
        if clip.get("rank") == clip_rank:
            old_hook = clip.get("hook")
            clip["hook"] = body.hook_text
            clip_found = True
            break

    if not clip_found:
        raise HTTPException(status_code=404, detail=f"Clip #{clip_rank} not found")

    # Persist updated clips_data
    from src.infrastructure.database import async_session, JobModel
    from sqlalchemy import update

    async with async_session() as session:
        await session.execute(
            update(JobModel)
            .where(JobModel.job_id == job_id)
            .values(clips_data=job.clips_data)
        )
        await session.commit()

    return {
        "success": True,
        "data": {
            "job_id": job_id,
            "clip_rank": clip_rank,
            "old_hook": old_hook,
            "new_hook": body.hook_text,
        },
        "message": f"Hook text updated for clip #{clip_rank}. Call /rerender to apply.",
    }


@router.patch("/{job_id}/clips/{clip_rank}/style")
async def edit_clip_style(
    job_id: str,
    clip_rank: int,
    body: EditClipStyleRequest,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Override hook style for a specific clip.

    Stores the style override in clips_data. Does NOT re-render automatically.
    Call POST .../rerender after editing to apply changes.
    """
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.clips_data or "clips" not in job.clips_data:
        raise HTTPException(status_code=400, detail="Job has no clips data")

    # Validate hook_style exists
    from src.infrastructure.hook_engine.styles.hook_style_renderer import HookStyleConfigLoader
    from src.infrastructure.hook_engine.styles import STYLE_REGISTRY
    all_db = HookStyleConfigLoader.get_all_configs()
    valid_styles = set(STYLE_REGISTRY.keys()) | set(all_db.keys())

    if body.hook_style not in valid_styles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid hook_style '{body.hook_style}'. Valid: {sorted(valid_styles)}",
        )

    # Find clip and set override
    clip_found = False
    for clip in job.clips_data["clips"]:
        if clip.get("rank") == clip_rank:
            clip["hook_style_override"] = body.hook_style
            if body.hook_style_config:
                clip["hook_style_config_override"] = body.hook_style_config
            clip_found = True
            break

    if not clip_found:
        raise HTTPException(status_code=404, detail=f"Clip #{clip_rank} not found")

    # Persist
    from src.infrastructure.database import async_session, JobModel
    from sqlalchemy import update

    async with async_session() as session:
        await session.execute(
            update(JobModel)
            .where(JobModel.job_id == job_id)
            .values(clips_data=job.clips_data)
        )
        await session.commit()

    return {
        "success": True,
        "data": {
            "job_id": job_id,
            "clip_rank": clip_rank,
            "hook_style": body.hook_style,
            "hook_style_config": body.hook_style_config,
        },
        "message": f"Style override set for clip #{clip_rank}. Call /rerender to apply.",
    }


@router.post("/{job_id}/clips/{clip_rank}/rerender")
async def rerender_clip(
    job_id: str,
    clip_rank: int,
    body: RerenderRequest = None,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Re-render a single clip with current or overridden hook/style.

    This triggers the hook rendering pipeline for just this one clip.
    Uses the clip's current hook_text and hook_style (or overrides from body).

    Returns immediately with status — rendering happens in background.
    """
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.clips_data or "clips" not in job.clips_data:
        raise HTTPException(status_code=400, detail="Job has no clips data")

    # Find clip
    clip_data = None
    for clip in job.clips_data["clips"]:
        if clip.get("rank") == clip_rank:
            clip_data = clip
            break

    if clip_data is None:
        raise HTTPException(status_code=404, detail=f"Clip #{clip_rank} not found")

    # Check source video exists
    output_dir = f"{settings.OUTPUT_DIR}/{job_id}"
    reframed_path = f"{output_dir}/clip_{clip_rank:02d}_reframed.mp4"
    raw_path = f"{output_dir}/raw/clip_{clip_rank}.mp4"
    source_path = reframed_path if os.path.exists(reframed_path) else raw_path

    if not os.path.exists(source_path):
        raise HTTPException(
            status_code=400,
            detail=f"Source video not found for clip #{clip_rank}. Run full pipeline first.",
        )

    # Determine hook_text and style
    hook_text = body.hook_text if (body and body.hook_text) else clip_data.get("hook", "")
    hook_style = body.hook_style if (body and body.hook_style) else clip_data.get("hook_style_override", job.style_preset)
    hook_config = body.hook_style_config if (body and body.hook_style_config) else clip_data.get("hook_style_config_override")

    if not hook_text:
        raise HTTPException(status_code=400, detail="No hook text available for this clip")

    # Update clip data with overrides if provided
    if body and body.hook_text:
        clip_data["hook"] = body.hook_text
    if body and body.hook_style:
        clip_data["hook_style_override"] = body.hook_style

    # Perform render (synchronous for now — could be async via queue)
    import logging
    logger = logging.getLogger(__name__)

    try:
        from src.infrastructure.hook_engine.styles import STYLE_REGISTRY
        from src.infrastructure.hook_engine.styles.hook_style_renderer import HookStyleRenderer

        # Only new styles support HookStyleRenderer
        if hook_style in STYLE_REGISTRY:
            renderer = HookStyleRenderer(
                style_name=hook_style,
                config_overrides=hook_config,
            )

            import cv2
            import numpy as np

            cap = cv2.VideoCapture(source_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = min(renderer.get_total_duration(), 4.0)
            total_frames = int(duration * fps)

            # Output path
            os.makedirs(f"{output_dir}/final", exist_ok=True)
            final_path = f"{output_dir}/final/clip_{clip_rank}_final.mp4"

            import subprocess
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-f", "rawvideo", "-vcodec", "rawvideo",
                "-s", f"{width}x{height}", "-pix_fmt", "bgr24",
                "-r", str(fps), "-i", "-",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                final_path,
            ]
            proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

            frame_idx = 0
            try:
                while frame_idx < total_frames:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    t = frame_idx / fps
                    result = renderer.process_frame(frame, t, hook_text)
                    proc.stdin.write(result.tobytes())
                    frame_idx += 1
            finally:
                cap.release()
                proc.stdin.close()
                proc.wait(timeout=120)

            if proc.returncode != 0:
                stderr = proc.stderr.read().decode()[-300:]
                raise RuntimeError(f"FFmpeg failed: {stderr}")

            # Persist updated clips_data
            from src.infrastructure.database import async_session, JobModel
            from sqlalchemy import update as sql_update

            async with async_session() as session:
                await session.execute(
                    sql_update(JobModel)
                    .where(JobModel.job_id == job_id)
                    .values(clips_data=job.clips_data)
                )
                await session.commit()

            return {
                "success": True,
                "data": {
                    "job_id": job_id,
                    "clip_rank": clip_rank,
                    "hook_text": hook_text,
                    "hook_style": hook_style,
                    "output_path": f"/api/jobs/{job_id}/clips/{clip_rank}/final",
                    "frames_rendered": frame_idx,
                    "duration": duration,
                },
                "message": f"Clip #{clip_rank} re-rendered successfully",
            }
        else:
            # Legacy style — use existing HookEngine
            return {
                "success": False,
                "message": f"Re-render for legacy style '{hook_style}' — use full pipeline. "
                           f"Only new styles ({', '.join(STYLE_REGISTRY.keys())}) support per-clip re-render.",
            }

    except Exception as e:
        logger.error(f"rerender_clip_error: job={job_id}, clip={clip_rank}, error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Re-render failed: {str(e)}")


# ─── Restyle: Full re-render chain (hook + broll + subtitle) from raw clip ────

class RestyleRequest(BaseModel):
    """Restyle a clip: re-apply hook + broll + subtitle from raw/reframed source."""
    hook_text: Opt[str] = None
    hook_style: Opt[str] = None
    subtitle_enabled: bool = True
    broll_enabled: bool = True


@router.post("/{job_id}/clips/{clip_rank}/restyle")
async def restyle_clip(
    job_id: str,
    clip_rank: int,
    body: RestyleRequest = None,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Full restyle: re-apply hook + broll + subtitle rendering to an existing raw clip.

    Unlike /rerender (hook-only), this runs the complete visual chain:
    1. Hook overlay (3s with selected style)
    2. B-Roll overlay (if broll_enabled and brolls exist)
    3. Subtitle burn (word-by-word if subtitle_enabled)

    Source: uses reframed clip if available, else raw clip.
    Output: replaces final/clip_{rank}_final.mp4
    """
    import asyncio
    import logging
    import shutil

    logger = logging.getLogger(__name__)

    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.clips_data or "clips" not in job.clips_data:
        raise HTTPException(status_code=400, detail="Job has no clips data")

    # Find clip data
    clip_data = None
    for clip in job.clips_data["clips"]:
        if clip.get("rank") == clip_rank:
            clip_data = clip
            break

    if clip_data is None:
        raise HTTPException(status_code=404, detail=f"Clip #{clip_rank} not found")

    # Find source video (reframed > raw)
    output_dir = f"{settings.OUTPUT_DIR}/{job_id}"
    reframed_path = f"{output_dir}/clip_{clip_rank:02d}_reframed.mp4"
    raw_path = f"{output_dir}/raw/clip_{clip_rank}.mp4"
    source_path = reframed_path if os.path.exists(reframed_path) else raw_path

    if not os.path.exists(source_path):
        raise HTTPException(status_code=400, detail="Raw clip not found. Run full pipeline first.")

    # Resolve parameters
    hook_text = (body.hook_text if body and body.hook_text else clip_data.get("hook", "")).strip()
    hook_style = (body.hook_style if body and body.hook_style else
                  clip_data.get("hook_style_override", job.hook_style or settings.HOOK_DEFAULT_STYLE))
    do_subtitle = body.subtitle_enabled if body else True
    do_broll = body.broll_enabled if body else True

    # Prepare paths
    os.makedirs(f"{output_dir}/final", exist_ok=True)
    hooked_path = f"{output_dir}/clip_{clip_rank:02d}_hooked.mp4"
    brolled_path = f"{output_dir}/clip_{clip_rank:02d}_brolled.mp4"
    final_path = f"{output_dir}/final/clip_{clip_rank}_final.mp4"

    try:
        current_path = source_path

        # Step 1: Hook rendering
        if hook_text:
            await service._render_hook_ffmpeg(current_path, hook_text, hooked_path, hook_style=hook_style)
            if os.path.exists(hooked_path):
                current_path = hooked_path
            logger.info(f"[restyle] hook applied clip {clip_rank} style={hook_style}")

        # Step 2: B-Roll overlay (if enabled and brolls exist for this clip)
        if do_broll and service._broll_injector:
            from src.domain.entities import BRollSuggestion, Clip
            broll_suggestions = []
            for bs in clip_data.get("broll_suggestions", []):
                broll_suggestions.append(BRollSuggestion(
                    keyword=bs.get("keyword", ""),
                    at_time=bs.get("at_time", 0),
                    duration=bs.get("duration", 2.0),
                    category=bs.get("category", "motion_graphic"),
                    visual_description=bs.get("visual_description", ""),
                ))

            if broll_suggestions:
                try:
                    temp_clip = Clip(
                        rank=clip_rank,
                        score=clip_data.get("score", 0),
                        start=clip_data.get("start", 0),
                        end=clip_data.get("end", 0),
                        hook=hook_text,
                        reason="",
                        broll_suggestions=broll_suggestions,
                    )
                    result = await service._broll_injector.inject_brolls(
                        current_path, temp_clip, brolled_path
                    )
                    if result and os.path.exists(brolled_path):
                        current_path = brolled_path
                    logger.info(f"[restyle] broll applied clip {clip_rank}")
                except Exception as e:
                    logger.warning(f"[restyle] broll failed clip {clip_rank}: {e}")

        # Step 3: Subtitle rendering (if enabled and words exist)
        if do_subtitle and clip_data.get("words"):
            try:
                if service._subtitle_renderer:
                    sub_out = final_path
                    await service._subtitle_renderer.render(
                        current_path, clip_data["words"], sub_out,
                        start_offset=3.0,
                    )
                    if os.path.exists(sub_out):
                        current_path = sub_out
                    logger.info(f"[restyle] subtitle applied clip {clip_rank}")
                else:
                    # No subtitle renderer, copy to final
                    shutil.copy2(current_path, final_path)
                    current_path = final_path
            except Exception as e:
                logger.warning(f"[restyle] subtitle failed clip {clip_rank}: {e}")
                shutil.copy2(current_path, final_path)
                current_path = final_path
        else:
            # Copy current to final
            if current_path != final_path:
                shutil.copy2(current_path, final_path)

        # Update clip_data with applied style
        clip_data["hook_style_override"] = hook_style
        if body and body.hook_text:
            clip_data["hook"] = body.hook_text

        # Persist
        from src.infrastructure.database import async_session, JobModel
        from sqlalchemy import update as sql_update
        async with async_session() as session:
            await session.execute(
                sql_update(JobModel).where(JobModel.job_id == job_id).values(clips_data=job.clips_data)
            )
            await session.commit()

        # Cleanup temp files
        for tmp in [hooked_path, brolled_path]:
            if tmp != final_path and os.path.exists(tmp):
                os.remove(tmp)

        return {
            "success": True,
            "data": {
                "job_id": job_id,
                "clip_rank": clip_rank,
                "hook_text": hook_text,
                "hook_style": hook_style,
                "subtitle_applied": do_subtitle and bool(clip_data.get("words")),
                "broll_applied": do_broll and bool(clip_data.get("broll_suggestions")),
                "output_url": f"/api/jobs/{job_id}/clips/{clip_rank}/final",
            },
            "message": f"Clip #{clip_rank} restyled successfully",
        }

    except Exception as e:
        logger.error(f"restyle_error: job={job_id}, clip={clip_rank}, error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Restyle failed: {str(e)}")
