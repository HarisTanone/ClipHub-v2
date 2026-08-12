"""Video Generator API routes — superuser only.

POST /video-generator/generate  — create and start a video generation job
GET  /video-generator/jobs      — list all video gen jobs
GET  /video-generator/jobs/{id} — get job status/details
GET  /video-generator/jobs/{id}/download — download final video
GET  /video-generator/voices    — list available TTS voices
"""
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional

from src.config import settings
from src.application.video_generator import VideoGenStatus
from src.presentation.auth_deps import CurrentUser, require_superadmin

router = APIRouter(prefix="/video-generator", tags=["video-generator"])


# ─── Request/Response Models ──────────────────────────────────────────────────

class GenerateVideoRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500, description="Video topic")
    target_duration: int = Field(default=0, ge=0, le=120, description="Target duration in seconds (0=default)")
    voice: str = Field(default="", description="TTS voice model (empty=default)")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="TTS speed multiplier")
    instructions: str = Field(default="", max_length=1000, description="Additional instructions for AI")
    num_scenes: int = Field(default=0, ge=0, le=15, description="Number of scenes (0=auto)")


class JobStatusResponse(BaseModel):
    job_id: str
    topic: str
    status: str
    progress: int
    target_duration: int
    voice: str
    title: Optional[str] = None
    error: Optional[str] = None
    output_path: Optional[str] = None
    created_at: float
    completed_at: Optional[float] = None
    scenes_count: int = 0
    estimated_duration: Optional[float] = None


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
    """Start a video generation job (superuser only).

    Creates an AI-generated short video from a topic.
    Returns immediately with job_id — processing happens in background.
    """
    if not settings.VIDEO_GEN_ENABLED:
        raise HTTPException(status_code=503, detail="Video Generator is disabled")

    from src.application.video_generator import get_video_generator

    vg = get_video_generator()

    job = vg.create_job(
        topic=req.topic,
        target_duration=req.target_duration,
        voice=req.voice,
        speed=req.speed,
        instructions=req.instructions,
        user_id=user.id,
    )

    # Run pipeline in background
    background_tasks.add_task(vg.run_pipeline, job.job_id)

    return _job_to_response(job)


@router.get("/jobs", response_model=list[JobStatusResponse])
async def list_jobs(
    user: CurrentUser = Depends(require_superadmin()),
):
    """List all video generation jobs (superuser only)."""
    from src.application.video_generator import get_video_generator

    vg = get_video_generator()
    jobs = vg.list_jobs()

    return [_job_to_response(j) for j in jobs]


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
    title = None

    if job.story:
        scenes_count = len(job.story.get("scenes", []))
        estimated_duration = job.story.get("estimated_duration")
        title = job.story.get("title")

    return JobStatusResponse(
        job_id=job.job_id,
        topic=job.topic,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        progress=job.progress,
        target_duration=job.target_duration,
        voice=job.voice,
        title=title,
        error=job.error,
        output_path=job.output_path,
        created_at=job.created_at,
        completed_at=job.completed_at,
        scenes_count=scenes_count,
        estimated_duration=estimated_duration,
    )
