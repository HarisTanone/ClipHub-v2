"""Progress routes — SSE streaming + polling endpoint for frontend tracking.

Endpoints:
- GET /jobs/{job_id}/progress       — SSE stream (real-time)
- GET /jobs/{job_id}/progress/poll  — Polling endpoint (REST, for fallback)
"""
import os
import statistics
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
    {"number": 3, "name": "transcript", "label": "Fetching / Transcribing Transcript"},
    {"number": 4, "name": "analysis", "label": "AI Highlight Analysis"},
    {"number": 5, "name": "prepare", "label": "Preparing Clips"},
    {"number": 6, "name": "aspect_router", "label": "Routing Aspect Ratio"},
    {"number": 7, "name": "trim", "label": "Trimming Clips"},
    {"number": 8, "name": "reframe", "label": "Smart Reframe / Crop"},
    {"number": 9, "name": "word_level", "label": "Word-Level Timestamps"},
    {"number": 10, "name": "highlights", "label": "Highlight / Subtitle Data"},
    {"number": 11, "name": "assets", "label": "Visual Assets"},
    {"number": 12, "name": "subtitle", "label": "Subtitles & Overlay"},
    {"number": 13, "name": "remotion_render", "label": "Remotion Rendering"},
    {"number": 14, "name": "thumbnail", "label": "Thumbnail Generation"},
    {"number": 15, "name": "finalize", "label": "Finalizing Output"},
    {"number": 16, "name": "assemble", "label": "Assembling Result"},
]


def _get_step_from_status(status: str) -> int:
    """Map job status to approximate current step number."""
    status_step_map = {
        "validating": 1,
        "downloading": 2,
        "transcribing": 3,
        "v2_transcribing": 3,
        "analyzing": 4,
        "v2_analyzing": 4,
        "preparing": 5,
        "routing": 6,
        "trimming": 7,
        "segmenting": 8,
        "whisper": 9,
        "v2_word_transcribing": 9,
        "highlighting": 10,
        "v2_micro_slicing": 10,
        "v2_vad_refining": 10,
        "broll": 11,
        "subtitle_rendering": 12,
        "hook_rendering": 13,
        "remotion_rendering": 13,
        "rendering": 13,
        "encoding": 15,
        "uploading": 15,
        "assembling": 16,
        "processing": 6,
        "completed": 16,
        "failed": 0,
        "timeout": 0,
        "queued": 0,
    }
    return status_step_map.get(status, 0)


def _estimate_progress_pct(step_number: int, total_steps: int = len(PIPELINE_STEPS)) -> int:
    """Estimate overall progress percentage based on current step."""
    if step_number <= 0:
        return 0
    if step_number >= total_steps:
        return 100
    return int((step_number / total_steps) * 100)


def _step_info(step_number: int):
    if 1 <= step_number <= len(PIPELINE_STEPS):
        step = PIPELINE_STEPS[step_number - 1]
        return step["name"], step["label"]
    return None, None


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

    total_steps = len(PIPELINE_STEPS)
    current_step = _get_step_from_status(job.status.value)
    progress_pct = _estimate_progress_pct(current_step, total_steps)
    step_name, step_label = _step_info(current_step)

    # Prefer the latest SSE/log state so polling matches live progress.
    emitter = get_sse_emitter()
    latest_state = emitter.get_current_state(job_id) or emitter.get_final_state(job_id)
    if latest_state:
        try:
            latest_step = int(float(latest_state.get("step_number", current_step) or current_step))
            current_step = max(0, min(total_steps, latest_step))
        except (TypeError, ValueError):
            pass
        try:
            progress_pct = int(latest_state.get("percentage", progress_pct))
            progress_pct = max(0, min(100, progress_pct))
        except (TypeError, ValueError):
            pass
        latest_name = latest_state.get("step_name")
        fallback_name, fallback_label = _step_info(current_step)
        step_name = latest_name or fallback_name
        step_label = fallback_label

    is_terminal = job.status.value in ("completed", "failed", "timeout")

    # Data-driven ETA from completed jobs on this actual server. Processing is
    # server-side, so browser device specs are intentionally not fabricated.
    eta = None
    if not is_terminal and job.created_at and job.video_duration and progress_pct > 0:
        try:
            from sqlalchemy import select
            from src.infrastructure.database import JobModel, async_session
            async with async_session() as session:
                rows = (await session.execute(select(JobModel).where(JobModel.status == "completed").where(JobModel.video_duration > 0).order_by(JobModel.updated_at.desc()).limit(30))).scalars().all()
            ratios = [max(0.0, (row.updated_at - row.created_at).total_seconds()) / row.video_duration for row in rows if row.created_at and row.updated_at and row.video_duration]
            if len(ratios) >= 2:
                elapsed = max(0.0, (datetime.now(timezone.utc).replace(tzinfo=None) - job.created_at.replace(tzinfo=None)).total_seconds())
                historical_total = statistics.median(ratios) * job.video_duration
                progress_total = elapsed / max(progress_pct / 100.0, 0.01)
                estimated_total = historical_total * 0.65 + progress_total * 0.35
                eta = {"remaining_seconds": max(0, round(estimated_total - elapsed)), "estimated_total_seconds": round(estimated_total), "elapsed_seconds": round(elapsed), "sample_count": len(ratios), "basis": "median completed jobs + current measured progress"}
        except Exception:
            eta = None

    if is_terminal and job.status.value == "completed":
        progress_pct = 100
        current_step = total_steps
        step_name, step_label = _step_info(current_step)

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
                "total_steps": total_steps,
                "percentage": progress_pct,
                "step_name": step_name,
                "step_label": step_label,
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
            "eta": eta,
        },
        "pipeline_steps": PIPELINE_STEPS,
    }
