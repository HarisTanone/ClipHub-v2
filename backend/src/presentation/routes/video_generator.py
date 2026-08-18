"""Video Generator API routes — superuser only.

POST /video-generator/generate  — create and start a video generation job
GET  /video-generator/jobs      — list all video gen jobs
GET  /video-generator/jobs/{id} — get job status/details
GET  /video-generator/jobs/{id}/download — download final video
GET  /video-generator/voices    — list available TTS voices
"""
import os

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Any, Optional

from src.config import settings
from src.application.video_generator import VideoGenStatus
from src.presentation.auth_deps import CurrentUser, require_superadmin

router = APIRouter(prefix="/video-generator", tags=["video-generator"])


# ─── Request/Response Models ──────────────────────────────────────────────────

class GenerateVideoRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500, description="Video topic")
    target_duration: int = Field(default=0, ge=0, le=120, description="Target duration in seconds (0=default)")
    voice: str = Field(default="", max_length=100, description="TTS voice model (empty=default)")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="TTS speed multiplier")
    instructions: str = Field(default="", max_length=1000, description="Additional instructions for AI")
    num_scenes: int = Field(default=0, ge=0, le=25, description="Number of scenes (0=auto)")
    subtitles_enabled: bool = Field(default=True, description="Burn captions into the final video")
    subtitle_style_config: dict[str, Any] = Field(default_factory=dict)
    subtitle_style: Optional[dict[str, Any]] = Field(default=None, exclude=True)
    hook_enabled: bool = Field(default=True, description="Burn opening hook title overlay into the video")
    custom_hook: Optional[str] = Field(default=None, max_length=250, description="Custom hook title text (empty=auto)")
    hook_style_config: dict[str, Any] = Field(default_factory=dict)
    hook_style: Optional[dict[str, Any]] = Field(default=None, exclude=True)
    include_bgm: bool = Field(default=True, description="Mix background music when available")
    bgm_volume: float = Field(default=0.15, ge=0.0, le=0.5)


class SearchSceneRequest(BaseModel):
    scene_id: int
    query: str = Field(..., min_length=2, max_length=200)


class RenderSelectedRequest(BaseModel):
    job_id: str
    selected_scenes: list[dict[str, Any]] = Field(default_factory=list)


class JobStatusResponse(BaseModel):
    job_id: str
    topic: str
    status: str
    progress: int
    step_label: str = ""
    target_duration: int
    voice: str
    speed: float = 1.0
    num_scenes: int = 0
    subtitles_enabled: bool = True
    subtitle_style_config: dict[str, Any] = Field(default_factory=dict)
    hook_enabled: bool = True
    custom_hook: Optional[str] = None
    hook_style_config: dict[str, Any] = Field(default_factory=dict)
    include_bgm: bool = True
    bgm_volume: float = 0.15
    title: Optional[str] = None
    error: Optional[str] = None
    output_path: Optional[str] = None
    created_at: float
    completed_at: Optional[float] = None
    scenes_count: int = 0
    estimated_duration: Optional[float] = None
    thumbnail_url: Optional[str] = None
    scenes: Optional[list[dict[str, Any]]] = None


class JobListResponse(BaseModel):
    items: list[JobStatusResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class VoiceOption(BaseModel):
    key: str
    model: str


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=JobStatusResponse)
async def generate_video(
    req: GenerateVideoRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Start a video generation job in one-click auto mode (superuser only)."""
    if not settings.VIDEO_GEN_ENABLED:
        raise HTTPException(status_code=503, detail="Video Generator is disabled")

    target_duration = req.target_duration or settings.VIDEO_GEN_TARGET_DURATION
    if not settings.VIDEO_GEN_MIN_DURATION <= target_duration <= settings.VIDEO_GEN_MAX_DURATION:
        raise HTTPException(
            status_code=422,
            detail=(
                f"target_duration must be between {settings.VIDEO_GEN_MIN_DURATION} "
                f"and {settings.VIDEO_GEN_MAX_DURATION} seconds"
            ),
        )
    if req.num_scenes > settings.VIDEO_GEN_MAX_SCENES:
        raise HTTPException(
            status_code=422,
            detail=f"num_scenes must not exceed {settings.VIDEO_GEN_MAX_SCENES}",
        )

    from src.application.video_generator import get_video_generator

    vg = get_video_generator()

    job = vg.create_job(
        topic=req.topic,
        target_duration=target_duration,
        voice=req.voice,
        speed=req.speed,
        instructions=req.instructions,
        num_scenes=req.num_scenes,
        subtitles_enabled=req.subtitles_enabled,
        subtitle_style=req.subtitle_style_config or req.subtitle_style,
        hook_enabled=req.hook_enabled,
        custom_hook=req.custom_hook,
        hook_style=req.hook_style_config or req.hook_style,
        include_bgm=req.include_bgm,
        bgm_volume=req.bgm_volume,
        user_id=user.id,
    )

    background_tasks.add_task(vg.run_pipeline, job.job_id)
    return _job_to_response(job)


@router.post("/plan", response_model=JobStatusResponse)
async def plan_video(
    req: GenerateVideoRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Start interactive planning: generates script & searches footage candidates (superuser only)."""
    if not settings.VIDEO_GEN_ENABLED:
        raise HTTPException(status_code=503, detail="Video Generator is disabled")

    target_duration = req.target_duration or settings.VIDEO_GEN_TARGET_DURATION
    if not settings.VIDEO_GEN_MIN_DURATION <= target_duration <= settings.VIDEO_GEN_MAX_DURATION:
        raise HTTPException(
            status_code=422,
            detail=f"target_duration must be between {settings.VIDEO_GEN_MIN_DURATION} and {settings.VIDEO_GEN_MAX_DURATION} seconds",
        )

    from src.application.video_generator import get_video_generator

    vg = get_video_generator()

    job = vg.create_job(
        topic=req.topic,
        target_duration=target_duration,
        voice=req.voice,
        speed=req.speed,
        instructions=req.instructions,
        num_scenes=req.num_scenes,
        subtitles_enabled=req.subtitles_enabled,
        subtitle_style=req.subtitle_style_config or req.subtitle_style,
        hook_enabled=req.hook_enabled,
        custom_hook=req.custom_hook,
        hook_style=req.hook_style_config or req.hook_style,
        include_bgm=req.include_bgm,
        bgm_volume=req.bgm_volume,
        user_id=user.id,
    )
    job.status = VideoGenStatus.PLANNING

    background_tasks.add_task(vg.plan_scenes_and_footage, job.job_id)
    return _job_to_response(job)


@router.post("/jobs/{job_id}/search-scene")
async def search_scene(
    job_id: str,
    req: SearchSceneRequest,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Search alternative footage candidates for a specific scene (superuser only)."""
    from src.application.video_generator import get_video_generator

    vg = get_video_generator()
    try:
        candidates = await vg.search_scene_footage(job_id, req.scene_id, req.query)
        return {"scene_id": req.scene_id, "candidates": candidates}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/render-selected", response_model=JobStatusResponse)
async def render_selected(
    req: RenderSelectedRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Start rendering with user-selected footage candidates for each scene (superuser only)."""
    from src.application.video_generator import get_video_generator

    vg = get_video_generator()
    job = vg.get_job(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    background_tasks.add_task(vg.render_with_selected_scenes, req.job_id, req.selected_scenes)
    return _job_to_response(job)


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    page: int = 1,
    limit: int = 8,
    user: CurrentUser = Depends(require_superadmin()),
):
    """List all video generation jobs with pagination (superuser only).
    
    Default page=1, limit=8 (2 rows of 4 videos).
    """
    from src.application.video_generator import get_video_generator
    import math

    safe_page = max(1, page)
    safe_limit = max(1, min(100, limit))
    offset = (safe_page - 1) * safe_limit

    vg = get_video_generator()
    total = vg.count_jobs()
    jobs = vg.list_jobs(limit=safe_limit, offset=offset)
    total_pages = max(1, math.ceil(total / safe_limit)) if total > 0 else 1

    return JobListResponse(
        items=[_job_to_response(j) for j in jobs],
        total=total,
        page=safe_page,
        limit=safe_limit,
        total_pages=total_pages,
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Get video generation job status (superuser only)."""
    from src.application.video_generator import get_video_generator

    vg = get_video_generator()
    job = vg.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return _job_to_response(job)


@router.get("/jobs/{job_id}/download")
async def download_video(
    job_id: str,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Download the final generated video (superuser only)."""
    from src.application.video_generator import get_video_generator

    vg = get_video_generator()
    job = vg.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != VideoGenStatus.COMPLETED:
        raise HTTPException(status_code=400, detail=f"Job not completed (status: {job.status})")

    if not job.output_path or not os.path.exists(job.output_path):
        raise HTTPException(status_code=404, detail="Output file not found")

    filename = f"video_{job.job_id}.mp4"
    return FileResponse(
        path=job.output_path,
        media_type="video/mp4",
        filename=filename,
    )


@router.post("/jobs/{job_id}/retry", response_model=JobStatusResponse)
async def retry_video(
    job_id: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Retry a failed video generation job in place with the same settings (superuser only)."""
    from src.application.video_generator import get_video_generator

    vg = get_video_generator()
    job = vg.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != VideoGenStatus.FAILED:
        raise HTTPException(status_code=400, detail="Only failed jobs can be retried")

    retried_job = vg.retry_job(job_id)

    # If the job already had curated scenes or was rendered with custom footage, resume render
    if retried_job.scenes_with_footage and any(s.get("selected_footage") for s in retried_job.scenes_with_footage):
        background_tasks.add_task(vg.render_with_selected_scenes, retried_job.job_id, retried_job.scenes_with_footage)
    else:
        background_tasks.add_task(vg.run_pipeline, retried_job.job_id)

    return _job_to_response(retried_job)


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Delete a video generation job and all its artifacts (superuser only)."""
    from src.application.video_generator import get_video_generator

    vg = get_video_generator()
    job = vg.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    vg.delete_job(job_id)
    return {"success": True, "message": f"Job {job_id} deleted successfully"}


@router.get("/jobs/{job_id}/stream")
async def stream_video(
    job_id: str,
    token: Optional[str] = None,
    range: Optional[str] = Header(None, alias="range"),
):
    """Stream the generated video with Range support (for HTML5 video player).

    Auth via query param ?token=<jwt> since <video> element cannot send headers.
    """
    from src.application.video_generator import get_video_generator
    from src.infrastructure.auth import decode_access_token, is_superadmin
    from starlette.responses import StreamingResponse

    # Auth via query param token (HTML5 video can't send Bearer header)
    if not token:
        raise HTTPException(status_code=401, detail="Token required (?token=)")

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if not is_superadmin(payload.get("role", "")):
        raise HTTPException(status_code=403, detail="Superadmin access required")

    vg = get_video_generator()
    job = vg.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != VideoGenStatus.COMPLETED:
        raise HTTPException(status_code=400, detail=f"Job not completed (status: {job.status})")

    file_path = job.output_path
    if not file_path or not os.path.exists(file_path):
        # Fallback check standard work dir
        candidate = os.path.join(settings.VIDEO_GEN_OUTPUT_DIR, job_id, f"final_{job_id}.mp4")
        if os.path.exists(candidate):
            file_path = candidate
        else:
            raise HTTPException(status_code=404, detail="Output file not found")

    file_size = os.path.getsize(file_path)

    start, end = _parse_byte_range(range, file_size)

    chunk_size = end - start + 1

    def iter_file():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = chunk_size
            while remaining > 0:
                read_size = min(remaining, 1024 * 1024)  # 1MB chunks
                data = f.read(read_size)
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
        "Content-Type": "video/mp4",
    }

    status_code = 206 if range else 200
    if range:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    return StreamingResponse(
        iter_file(),
        status_code=status_code,
        headers=headers,
        media_type="video/mp4",
    )


@router.get("/jobs/{job_id}/story")
async def get_job_story(
    job_id: str,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Get the generated story/script for a job (superuser only)."""
    from src.application.video_generator import get_video_generator

    vg = get_video_generator()
    job = vg.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job.job_id,
        "story": job.story,
        "timeline": job.timeline,
    }


@router.get("/voices", response_model=list[VoiceOption])
async def list_voices(
    user: CurrentUser = Depends(require_superadmin()),
):
    """List available TTS voices."""
    from src.infrastructure.deepgram_tts import DEEPGRAM_VOICES

    return [
        VoiceOption(key=key, model=model)
        for key, model in DEEPGRAM_VOICES.items()
    ]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _job_to_response(job) -> JobStatusResponse:
    """Convert VideoGenJob to response model."""
    scenes_count = 0
    estimated_duration = None
    title = job.title
    thumbnail_url = None

    if job.story:
        scenes_count = len(job.story.get("scenes", []))
        estimated_duration = job.story.get("estimated_duration")
        if not title:
            title = job.story.get("title")

    # Get thumbnail from first scene's footage source
    if job.scenes_with_footage:
        for scene in job.scenes_with_footage:
            src = scene.get("footage_source", {})
            if src and src.get("thumbnail_url"):
                thumbnail_url = src["thumbnail_url"]
                break

    # Human-readable step label
    status_val = job.status.value if hasattr(job.status, "value") else str(job.status)
    step_labels = {
        "queued": "Waiting in queue...",
        "planning": "Planning scenes...",
        "generating_story": "AI writing story & scenes...",
        "searching_footage": "Searching candidate footage...",
        "awaiting_selection": "Ready for footage selection",
        "downloading": "Downloading video clips...",
        "generating_tts": "Generating narration audio...",
        "assembling": "Assembling timeline...",
        "rendering": "Rendering final video...",
        "completed": "Done",
        "failed": "Failed",
    }
    step_label = step_labels.get(status_val, status_val)

    return JobStatusResponse(
        job_id=job.job_id,
        topic=job.topic,
        status=status_val,
        progress=job.progress,
        step_label=step_label,
        target_duration=job.target_duration,
        voice=job.voice,
        speed=job.speed,
        num_scenes=job.num_scenes,
        subtitles_enabled=job.subtitles_enabled,
        subtitle_style_config=job.subtitle_style,
        hook_enabled=job.hook_enabled,
        custom_hook=job.custom_hook,
        hook_style_config=job.hook_style,
        include_bgm=job.include_bgm,
        bgm_volume=job.bgm_volume,
        title=title,
        error=job.error,
        output_path=job.output_path,
        created_at=job.created_at,
        completed_at=job.completed_at,
        scenes_count=scenes_count,
        estimated_duration=estimated_duration,
        thumbnail_url=thumbnail_url,
        scenes=job.scenes_with_footage,
    )


def _parse_byte_range(range_header: Optional[str], file_size: int) -> tuple[int, int]:
    """Parse one HTTP byte range or raise a standards-compliant 416 response."""
    if file_size <= 0:
        raise HTTPException(status_code=404, detail="Output file is empty")
    if not range_header:
        return 0, file_size - 1
    if not range_header.startswith("bytes=") or "," in range_header:
        _raise_invalid_range(file_size)

    start_text, separator, end_text = range_header[6:].strip().partition("-")
    if not separator or (not start_text and not end_text):
        _raise_invalid_range(file_size)

    try:
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else file_size - 1
        else:
            suffix_length = int(end_text)
            if suffix_length <= 0:
                _raise_invalid_range(file_size)
            start = max(file_size - suffix_length, 0)
            end = file_size - 1
    except ValueError:
        _raise_invalid_range(file_size)

    if start < 0 or start >= file_size or end < start:
        _raise_invalid_range(file_size)
    return start, min(end, file_size - 1)


def _raise_invalid_range(file_size: int) -> None:
    raise HTTPException(
        status_code=416,
        detail="Requested range not satisfiable",
        headers={"Content-Range": f"bytes */{file_size}"},
    )
