"""Progress routes — SSE streaming + polling endpoint for frontend tracking.

Endpoints:
- GET /jobs/{job_id}/progress       — SSE stream (real-time)
- GET /jobs/{job_id}/progress/poll  — Polling endpoint (REST, for fallback)
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.application.services import JobService
from src.config import settings
from src.infrastructure.sse_progress_emitter import SSEProgressEmitter
from src.presentation.dependencies import get_job_service

router = APIRouter(tags=["progress"])

_sse_emitter = SSEProgressEmitter()


def get_sse_emitter() -> SSEProgressEmitter:
    """Get global SSE emitter instance."""
    return _sse_emitter


# ─── Pipeline step definitions for frontend ───────────────────────────────────

PIPELINE_STEPS = [
    {"number": 1, "name": "validate", "label": "Validating URL"},
    {"number": 2, "name": "download", "label": "Downloading Video"},
    {"number": 3, "name": "transcript", "label": "Fetching Transcript"},
    {"number": 4, "name": "gemini", "label": "AI Analysis (Gemini)"},
    {"number": 5, "name": "prepare", "label": "Preparing Clips"},
    {"number": 6, "name": "trim", "label": "Trimming Clips"},
    {"number": 7, "name": "whisper", "label": "Word-Level Timestamps"},
    {"number": 8, "name": "highlights", "label": "Highlight Detection"},
    {"number": 9, "name": "reframe", "label": "Reframe / Crop"},
    {"number": 10, "name": "visual_overlay", "label": "Subtitles & Overlay"},
    {"number": 11, "name": "thumbnail", "label": "Thumbnail Generation"},
    {"number": 12, "name": "finalize", "label": "Finalizing Output"},
    {"number": 13, "name": "cdn_upload", "label": "CDN Upload"},
    {"number": 14, "name": "assemble", "label": "Assembling Result"},
]


def _get_step_from_status(status: str) -> int:
    """Map job status to approximate current step number."""
    status_step_map = {
        "validating": 1,
        "downloading": 2,
        "transcribing": 3,
        "analyzing": 4,
        "rendering": 6,
        "whisper": 7,
        "assembling": 14,
        "processing": 6,
        "completed": 14,
        "failed": 0,
        "timeout": 0,
        "queued": 0,
    }
    return status_step_map.get(status, 0)


def _estimate_progress_pct(step_number: int, total_steps: int = 14) -> int:
    """Estimate overall progress percentage based on current step."""
    if step_number <= 0:
        return 0
    if step_number >= total_steps:
        return 100
    return int((step_number / total_steps) * 100)


# ─── SSE Streaming Endpoint ──────────────────────────────────────────────────

@router.get("/jobs/{job_id}/progress")
async def stream_job_progress(job_id: str):
    """SSE endpoint for streaming pipeline progress in real-time.

    Returns text/event-stream with events:
    - step_start: {step_number, step_name, total_steps, timestamp}
    - step_complete: {step_number, step_name, duration_seconds, timestamp}
    - job_done: {final_status, total_duration_seconds, clips_count, timestamp}
    """
    emitter = get_sse_emitter()

    if not emitter.can_connect(job_id):
        raise HTTPException(
            status_code=429,
            detail=f"Maximum connections ({emitter.MAX_CONNECTIONS_PER_JOB}) exceeded for job {job_id}",
        )

    return StreamingResponse(
        emitter.connect(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Polling Endpoint (REST fallback) ────────────────────────────────────────

@router.get("/jobs/{job_id}/progress/poll")
async def poll_job_progress(
    job_id: str,
    service: JobService = Depends(get_job_service),
):
    """Polling endpoint for job progress. Use when SSE is not available.

    Returns current progress state including:
    - Current step number and name
    - Overall percentage
    - All pipeline step definitions (for progress bar rendering)
    - Clip counts and status
    - Output file availability
    """
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Determine current step
    current_step = _get_step_from_status(job.status.value)
    progress_pct = _estimate_progress_pct(current_step)

    # Check SSE emitter for more precise step info
    emitter = get_sse_emitter()
    final_state = emitter.get_final_state(job_id)

    is_terminal = job.status.value in ("completed", "failed", "timeout")

    if is_terminal and job.status.value == "completed":
        progress_pct = 100
        current_step = 14

    # Check available outputs
    output_dir = f"{settings.OUTPUT_DIR}/{job_id}"
    available_clips = []
    if os.path.isdir(output_dir):
        final_dir = os.path.join(output_dir, "final")
        if os.path.isdir(final_dir):
            for f in sorted(os.listdir(final_dir)):
                if f.endswith("_final.mp4"):
                    try:
                        rank = int(f.split("_")[1])
                        available_clips.append(rank)
                    except (ValueError, IndexError):
                        pass

    return {
        "success": True,
        "data": {
            "job_id": job_id,
            "status": job.status.value,
            "is_terminal": is_terminal,
            "progress": {
                "current_step": current_step,
                "total_steps": 14,
                "percentage": progress_pct,
                "step_name": PIPELINE_STEPS[current_step - 1]["name"] if 1 <= current_step <= 14 else None,
                "step_label": PIPELINE_STEPS[current_step - 1]["label"] if 1 <= current_step <= 14 else None,
            },
            "clips": {
                "total": job.clips_total,
                "success": job.clips_success,
                "failed": job.clips_failed,
                "available": available_clips,
            },
            "error": job.error_message if is_terminal and job.status.value != "completed" else None,
            "timestamps": {
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            },
        },
        "pipeline_steps": PIPELINE_STEPS,
    }
