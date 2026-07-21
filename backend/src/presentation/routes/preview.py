"""Preview API routes — Style preview data for hook and subtitle customization.

Provides clip data needed for frontend to render a live preview of:
- Hook text with animation style
- Subtitle with word-level timing and highlight
- Style configuration (colors, fonts, positioning)
"""
import os
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.application.services import JobService
from src.config import settings
from src.presentation.dependencies import get_job_service
from src.presentation.auth_deps import CurrentUser, get_current_user
from src.presentation.routes.jobs import _check_job_ownership

router = APIRouter(tags=["preview"])
logger = logging.getLogger(__name__)


# ─── YouTube Metadata Preview ─────────────────────────────────────────────────

@router.get("/preview")
async def get_video_preview(url: str = Query(..., description="YouTube URL")):
    """Fetch YouTube video metadata for preview (title, thumbnail, duration)."""
    import re
    
    # Extract video ID
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
    ]
    video_id = None
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            break
    
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    
    # Check cache status for this video
    cache_info = _check_video_cache(video_id)
    
    # Try yt-dlp for metadata
    try:
        import subprocess
        import json
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-warnings",
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return {
                "success": True,
                "data": {
                    "video_id": video_id,
                    "title": data.get("title", ""),
                    "channel": data.get("channel", data.get("uploader", "")),
                    "channel_url": data.get("channel_url", ""),
                    "duration": data.get("duration", 0),
                    "duration_string": data.get("duration_string", ""),
                    "view_count": data.get("view_count"),
                    "like_count": data.get("like_count"),
                    "upload_date": data.get("upload_date", ""),
                    "thumbnail": data.get("thumbnail", f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"),
                    "description": (data.get("description", "") or "")[:200],
                    "cache": cache_info,
                },
            }
    except Exception as e:
        logger.warning(f"yt-dlp metadata failed: {e}")
    
    # Fallback: return basic info from video ID
    return {
        "success": True,
        "data": {
            "video_id": video_id,
            "title": f"YouTube Video ({video_id})",
            "channel": "",
            "channel_url": "",
            "duration": 0,
            "duration_string": "",
            "view_count": None,
            "like_count": None,
            "upload_date": "",
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            "description": "",
            "cache": cache_info,
        },
    }


def _check_video_cache(video_id: str) -> dict:
    """Check if this video has been processed before and what data is cached."""
    from src.infrastructure.db_connection import get_dict_connection
    
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        
        # Check transcript cache
        cur.execute("SELECT video_id, created_at FROM transcript_cache WHERE video_id = ?", (video_id,))
        transcript = cur.fetchone()
        has_transcript = transcript is not None
        
        # Check if any completed job exists for this URL
        cur.execute(
            "SELECT job_id, status, clips_total, clips_success, created_at FROM jobs "
            "WHERE youtube_url LIKE ? AND status = 'completed' ORDER BY created_at DESC LIMIT 1",
            (f"%{video_id}%",),
        )
        job_row = cur.fetchone()
        
        if job_row:
            return {
                "has_cache": True,
                "has_transcript": has_transcript,
                "last_job_id": job_row["job_id"],
                "last_status": job_row["status"],
                "clips_total": job_row["clips_total"],
                "clips_success": job_row["clips_success"],
                "processed_at": job_row["created_at"],
                "message": f"Sudah diproses ({job_row['clips_success']} clips). Aktifkan Force Reprocess untuk ulang dari awal.",
            }
        
        return {
            "has_cache": False,
            "has_transcript": has_transcript,
            "last_job_id": None,
            "message": "Belum pernah diproses" if not has_transcript else "Transcript tersedia, clip belum diproses",
        }
    except Exception as e:
        logger.warning(f"Cache check failed: {e}")
        return {"has_cache": False, "has_transcript": False, "message": None}
    finally:
        conn.close()


# ─── Clip Style Preview ───────────────────────────────────────────────────────

# ─── Request/Response Models ──────────────────────────────────────────────────

class StyleConfig(BaseModel):
    """Style configuration for preview."""
    primary_color: str = "#FFFFFF"
    secondary_color: str = "#FFCC00"
    background_accent: str = "#000000"
    hook_animation: str = "fade_scale"
    font_size: int = 36
    uppercase: bool = False
    subtitle_position: str = "bottom"


class PreviewResponse(BaseModel):
    """Full preview data for a clip — everything frontend needs to render preview."""
    success: bool = True
    clip_rank: int
    hook_text: str
    hook_animation: str
    words: list  # [{word, start, end}]
    duration: float
    style: StyleConfig
    thumbnail_url: Optional[str] = None
    video_url: Optional[str] = None


class UpdateStyleRequest(BaseModel):
    """Update style for a clip before re-render."""
    hook_text: Optional[str] = None
    hook_style: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    font_size: Optional[int] = None
    uppercase: Optional[bool] = None
    subtitle_position: Optional[str] = None


class AITextStillRequest(BaseModel):
    """Frame/style controls for a preview rendered by the final Remotion layer."""
    frame: int = 0
    text_emphasis_style_config: dict = Field(default_factory=dict)


# ─── Preview Endpoint ─────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/clips/{rank}/preview", response_model=PreviewResponse)
async def get_clip_preview(
    job_id: str,
    rank: int,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Get preview data for a clip — hook text, words, style config.
    
    Frontend uses this to render a live CSS/React preview of how
    the final video will look with current style settings.
    """
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await _check_job_ownership(job, user)
    
    # Get clip data
    clips_data = job.clips_data or {}
    clips = clips_data.get("clips", [])
    
    clip_info = None
    for c in clips:
        if c.get("rank") == rank:
            clip_info = c
            break
    
    if not clip_info:
        raise HTTPException(status_code=404, detail=f"Clip {rank} not found")
    
    # Extract hook text
    hook_text = clip_info.get("hook", "")
    
    # Extract words (word-level timestamps)
    words = clip_info.get("words", [])
    
    # Duration
    duration = clip_info.get("duration", 0)
    
    # Build style from job settings and creative direction
    creative = clips_data.get("creative_direction", {})
    style = StyleConfig(
        primary_color=creative.get("primary_color", "#FFFFFF"),
        secondary_color=creative.get("secondary_color", "#FFCC00"),
        background_accent=creative.get("background_accent", "#000000"),
        hook_animation=job.hook_style or "fade_scale",
        font_size=36,
        uppercase=creative.get("subtitle_uppercase", False),
        subtitle_position=creative.get("subtitle_position", "bottom"),
    )
    
    # URLs
    output_dir = f"tmp/output/{job_id}"
    thumb_path = f"{output_dir}/thumbnail/clip_{rank:02d}.jpg"
    video_path = f"{output_dir}/clip_{rank:02d}_final.mp4"
    
    thumbnail_url = f"/api/jobs/{job_id}/clips/{rank}/thumb" if os.path.exists(thumb_path) else None
    video_url = f"/api/jobs/{job_id}/clips/{rank}/final" if os.path.exists(video_path) else None
    
    return PreviewResponse(
        clip_rank=rank,
        hook_text=hook_text,
        hook_animation=style.hook_animation,
        words=words,
        duration=duration,
        style=style,
        thumbnail_url=thumbnail_url,
        video_url=video_url,
    )


@router.post("/jobs/{job_id}/clips/{rank}/ai-text-preview")
async def render_ai_text_preview(
    job_id: str,
    rank: int,
    body: AITextStillRequest,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Render AI Text with the exact Remotion composition used by final export."""
    job = await service.get_job(job_id)
    if not job or not job.clips_data:
        raise HTTPException(status_code=404, detail="Job not found")
    await _check_job_ownership(job, user)
    clip = next((item for item in job.clips_data.get("clips", []) if item.get("rank") == rank), None)
    if not clip:
        raise HTTPException(status_code=404, detail=f"Clip {rank} not found")

    adapter = getattr(service, "_remotion_adapter", None)
    if not adapter:
        raise HTTPException(status_code=503, detail="Remotion preview is unavailable")

    output_dir = os.path.join(settings.OUTPUT_DIR, job_id)
    video_candidates = [
        os.path.join(output_dir, f"clip_{rank:02d}_reframed.mp4"),
        os.path.join(output_dir, "raw", f"clip_{rank:02d}.mp4"),
        os.path.join(output_dir, "raw", f"clip_{rank}.mp4"),
        os.path.join(output_dir, "final", f"clip_{rank}_final.mp4"),
    ]
    video_path = next((path for path in video_candidates if os.path.exists(path)), None)
    if not video_path:
        raise HTTPException(status_code=404, detail="Clip video not found")

    from src.infrastructure.text_emphasis import normalise_text_emphasis_style
    creative = dict(job.clips_data.get("creative_direction") or {})
    creative["hook_style_config"] = (
        clip.get("hook_style_config_override")
        or job.clips_data.get("hook_style_config")
        or {}
    )
    creative["subtitle_style_config"] = (
        clip.get("subtitle_style_config_override")
        or job.clips_data.get("subtitle_style_config")
        or {}
    )
    creative["text_emphasis_style_config"] = normalise_text_emphasis_style(
        body.text_emphasis_style_config
        or job.clips_data.get("text_emphasis_style_config")
    )
    creative["reframe_layout"] = clip.get("reframe_layout") or clip.get("layout") or "single"
    events = (clip.get("text_emphasis_events") or [])[:2]
    duration = float(clip.get("duration") or max(0, float(clip.get("end", 0)) - float(clip.get("start", 0))) or 30.0)
    frame = max(0, min(int(body.frame), max(0, int(duration * 30) - 1)))
    result = await adapter.render_still(
        scene_graph=job.clips_data.get("scene_graphs", {}).get(str(rank), {"clip_rank": rank, "duration": duration, "layers": []}),
        creative_direction=creative,
        video_path=video_path,
        output_path=os.path.join(output_dir, "preview", f"ai_text_{rank}.jpg"),
        frame=frame,
        words=clip.get("words", []),
        hook_text="",
        hook_style="podcast_lower_third",
        text_emphasis_events=events,
    )
    if not result.get("success"):
        raise HTTPException(status_code=503, detail=result.get("error", "Remotion still render failed"))
    return {"success": True, "image": result["image"], "frame": frame}


@router.patch("/jobs/{job_id}/clips/{rank}/style", status_code=200)
async def update_clip_style(
    job_id: str,
    rank: int,
    body: UpdateStyleRequest,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Update style for a specific clip. Changes are applied on next re-render.
    
    This allows users to customize hook text, animation style, colors, etc.
    before triggering a re-render.
    """
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await _check_job_ownership(job, user)
    
    clips_data = job.clips_data or {}
    clips = clips_data.get("clips", [])
    
    clip_found = False
    for c in clips:
        if c.get("rank") == rank:
            clip_found = True
            # Update hook text
            if body.hook_text is not None:
                c["hook"] = body.hook_text
            # Update hook style
            if body.hook_style is not None:
                c["hook_style"] = body.hook_style
            # Update style overrides
            style_overrides = c.get("style_overrides", {})
            if body.primary_color is not None:
                style_overrides["primary_color"] = body.primary_color
            if body.secondary_color is not None:
                style_overrides["secondary_color"] = body.secondary_color
            if body.font_size is not None:
                style_overrides["font_size"] = body.font_size
            if body.uppercase is not None:
                style_overrides["uppercase"] = body.uppercase
            if body.subtitle_position is not None:
                style_overrides["subtitle_position"] = body.subtitle_position
            c["style_overrides"] = style_overrides
            break
    
    if not clip_found:
        raise HTTPException(status_code=404, detail=f"Clip {rank} not found")
    
    # Save updated clips_data
    from src.infrastructure.db_connection import get_dict_connection
    import json
    conn = get_dict_connection()
    try:
        conn.execute(
            "UPDATE jobs SET clips_data = ?, updated_at = datetime('now') WHERE job_id = ?",
            (json.dumps(clips_data), job_id),
        )
        conn.commit()
    finally:
        conn.close()
    
    return {"success": True, "message": f"Style updated for clip {rank}"}
