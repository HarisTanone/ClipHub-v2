"""Video Generator API routes — superuser only.

POST /video-generator/generate  — create and start a video generation job
GET  /video-generator/jobs      — list all video gen jobs
GET  /video-generator/jobs/{id} — get job status/details
GET  /video-generator/jobs/{id}/download — download final video
GET  /video-generator/voices    — list available TTS voices
"""
import os

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from typing import Any, Optional

from src.config import settings
from src.application.video_generator import VideoGenStatus
from src.presentation.auth_deps import CurrentUser, require_superadmin, get_current_user, get_optional_user


router = APIRouter(prefix="/video-generator", tags=["video-generator"])


# ─── Request/Response Models ──────────────────────────────────────────────────

class GenerateVideoRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500, description="Video topic")
    target_duration: int = Field(default=0, ge=0, le=120, description="Target duration in seconds (0=default)")
    tts_provider: Optional[str] = Field(default="gemini", description="TTS provider: gemini or deepgram")
    tts_model: Optional[str] = Field(default="gemini-3.1-flash-tts-preview", description="Gemini TTS model ID")
    voice: str = Field(default="Kore", max_length=100, description="TTS voice model/ID (empty=default)")
    voice_style: Optional[str] = Field(default="", max_length=100, description="Voice style or regional accent (e.g. id_jakarta, id_formal, id_jawa)")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="TTS speed multiplier")
    instructions: str = Field(default="", max_length=1000, description="Additional instructions for AI")
    num_scenes: int = Field(default=0, ge=0, le=25, description="Number of scenes (0=auto)")
    preset_slug: Optional[str] = Field(default=None, description="Preset slug or ID to load styles from")
    subtitles_enabled: bool = Field(default=True, description="Burn captions into the final video")
    subtitle_style_config: dict[str, Any] = Field(default_factory=dict)
    subtitle_style: Optional[dict[str, Any]] = Field(default=None, exclude=True)
    hook_enabled: bool = Field(default=True, description="Burn opening hook title overlay into the video")
    custom_hook: Optional[str] = Field(default=None, max_length=250, description="Custom hook title text (empty=auto)")
    hook_style_config: dict[str, Any] = Field(default_factory=dict)
    hook_style: Optional[dict[str, Any]] = Field(default=None, exclude=True)
    include_bgm: bool = Field(default=True, description="Mix background music when available")
    bgm_volume: float = Field(default=0.15, ge=0.0, le=0.5)
    source_video_url: Optional[str] = Field(default=None, max_length=1000, description="Optional source video URL (YouTube, GCS, or MP4) to analyze with Gemini Video Understanding")
    agentic_understanding: bool = Field(default=True, description="Enable Gemini Video Understanding for dynamic timeline navigation and precision moment extraction")
    language: Optional[str] = Field(default=None, max_length=20, description="Target language ('id', 'en', or 'auto')")
    video_processing_mode: Optional[str] = Field(default="agentic", description="Gemini video processing mode: 'agentic' (dynamic timeline navigation) or 'static' (frame-by-frame 1 FPS)")
    media_resolution: Optional[str] = Field(default="low", description="Multimodal media resolution: 'low' (~66 tokens/frame, fast) or 'high' (~258 tokens/frame, fine detail)")
    fps: Optional[float] = Field(default=None, ge=0.1, le=30.0, description="Custom frame rate sampling for static processing mode (e.g. 0.5 for 1 frame every 2s)")
    start_offset: Optional[float] = Field(default=None, ge=0.0, description="Clipping start offset in seconds for static processing mode")
    end_offset: Optional[float] = Field(default=None, ge=0.0, description="Clipping end offset in seconds for static processing mode")
    watermark_config: Optional[dict[str, Any]] = Field(default=None, description="Brand watermark configuration (text/image overlay)")
    transition: Optional[str] = Field(default="dissolve", description="Scene transition style ('dissolve', 'fade', 'wipeleft', 'slideleft', 'cut')")
    cta_config: Optional[dict[str, Any]] = Field(default=None, description="Call to Action outro card configuration")
    ai_text_config: Optional[dict[str, Any]] = Field(default=None, description="AI text emphasis / kinetic typography overlay")
    aspect_ratio: Optional[str] = Field(default="9:16", description="Video aspect ratio: '9:16', '16:9', or '1:1'")

    @field_validator("source_video_url")
    @classmethod
    def validate_source_video_url(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        v = v.strip()
        # Allow local uploaded file path if safe and exists or in storage directory
        if v.startswith("/") and (os.path.exists(v) or "source_videos" in v or "uploads" in v):
            return v

        from urllib.parse import urlparse
        import ipaddress

        parsed = urlparse(v)
        if parsed.scheme in ("gs", "gcs"):
            return v

        if parsed.scheme not in ("http", "https"):
            raise ValueError("source_video_url must use http, https, or gs scheme")

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise ValueError("source_video_url must include a valid hostname")

        if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            raise ValueError("source_video_url cannot target local services")

        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise ValueError("source_video_url cannot target internal/private IP addresses")
        except ValueError as e:
            if "target internal/private" in str(e):
                raise

        return v


class SearchSceneRequest(BaseModel):
    scene_id: int
    query: str = Field(..., min_length=2, max_length=200)


class RenderSelectedRequest(BaseModel):
    job_id: str
    selected_scenes: list[dict[str, Any]] = Field(default_factory=list)
    preset_slug: Optional[str] = None
    hook_enabled: Optional[bool] = None
    custom_hook: Optional[str] = None
    hook_style_config: Optional[dict[str, Any]] = None
    subtitles_enabled: Optional[bool] = None
    subtitle_style_config: Optional[dict[str, Any]] = None
    include_bgm: Optional[bool] = None
    bgm_volume: Optional[float] = None
    aspect_ratio: Optional[str] = None
    watermark_config: Optional[dict[str, Any]] = None
    transition: Optional[str] = None
    cta_config: Optional[dict[str, Any]] = None
    ai_text_config: Optional[dict[str, Any]] = None


class JobStatusResponse(BaseModel):
    job_id: str
    user_id: Optional[int] = None
    topic: str
    status: str
    progress: int
    step_label: str = ""
    target_duration: int
    tts_provider: Optional[str] = "gemini"
    tts_model: Optional[str] = "gemini-3.1-flash-tts-preview"
    voice: str = "Kore"
    voice_style: Optional[str] = ""
    speed: float = 1.0
    num_scenes: int = 0
    subtitles_enabled: bool = True
    subtitle_style_config: dict[str, Any] = Field(default_factory=dict)
    hook_enabled: bool = True
    custom_hook: Optional[str] = None
    hook_style_config: dict[str, Any] = Field(default_factory=dict)
    include_bgm: bool = True
    bgm_volume: float = 0.15
    source_video_url: Optional[str] = None
    agentic_understanding: bool = True
    language: Optional[str] = "id"
    video_processing_mode: Optional[str] = "agentic"
    media_resolution: Optional[str] = "low"
    fps: Optional[float] = None
    start_offset: Optional[float] = None
    end_offset: Optional[float] = None
    watermark_config: Optional[dict[str, Any]] = None
    transition: Optional[str] = "dissolve"
    cta_config: Optional[dict[str, Any]] = None
    ai_text_config: Optional[dict[str, Any]] = None
    aspect_ratio: Optional[str] = "9:16"
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
    provider: str = "gemini"
    description: Optional[str] = None
    category: Optional[str] = None
    gender: Optional[str] = None
    accent: Optional[str] = None
    language: Optional[str] = None
    country: Optional[str] = None
    flag: Optional[str] = None
    preview_url: Optional[str] = None
    voice_id: Optional[str] = None
    style_id: Optional[str] = None


class TTSModelOption(BaseModel):
    model_id: str
    name: str
    description: Optional[str] = None
    free_tier: Optional[bool] = True
    languages: Optional[list[str]] = None


class TTSProviderOption(BaseModel):
    id: str
    name: str
    description: str
    is_configured: bool
    default_model: str
    default_voice: str


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=JobStatusResponse)
async def generate_video(
    req: GenerateVideoRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    """Start a video generation job in one-click auto mode."""
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

    hook_style, subtitle_style, watermark_config, cta_config, ai_text_config = _resolve_job_styles(req, user.id)

    job = vg.create_job(
        topic=req.topic,
        target_duration=target_duration,
        tts_provider=req.tts_provider,
        tts_model=req.tts_model,
        voice=req.voice,
        speed=req.speed,
        instructions=req.instructions,
        num_scenes=req.num_scenes,
        subtitles_enabled=req.subtitles_enabled,
        subtitle_style=subtitle_style,
        hook_enabled=req.hook_enabled,
        custom_hook=req.custom_hook,
        hook_style=hook_style,
        include_bgm=req.include_bgm,
        bgm_volume=req.bgm_volume,
        source_video_url=req.source_video_url,
        agentic_understanding=req.agentic_understanding,
        language=req.language,
        video_processing_mode=req.video_processing_mode,
        media_resolution=req.media_resolution,
        fps=req.fps,
        start_offset=req.start_offset,
        end_offset=req.end_offset,
        watermark_config=watermark_config,
        transition=req.transition,
        cta_config=cta_config,
        ai_text_config=ai_text_config,
        user_id=user.id,
    )

    background_tasks.add_task(vg.run_pipeline, job.job_id)
    return _job_to_response(job)


def _resolve_job_styles(
    req: GenerateVideoRequest, user_id: int
) -> tuple[dict, dict, Optional[dict], Optional[dict], Optional[dict]]:
    """Resolve hook, subtitle, watermark, cta, and ai_text styles from preset and explicit overrides."""
    import logging
    _log = logging.getLogger(__name__)

    hook_style = dict(req.hook_style_config or req.hook_style or {})
    subtitle_style = dict(req.subtitle_style_config or req.subtitle_style or {})
    watermark_config = req.watermark_config
    cta_config = req.cta_config
    ai_text_config = req.ai_text_config

    preset = None
    if req.preset_slug:
        try:
            from src.presentation.routes.presets import get_preset_by_slug
            preset = get_preset_by_slug(user_id, req.preset_slug)
            if preset:
                _log.info(f"video_generator: loaded preset '{req.preset_slug}' for job topic '{req.topic[:30]}'")
        except Exception as pe:
            _log.warning(f"video_generator: failed to resolve preset '{req.preset_slug}': {pe}")

    if preset:
        if preset.get("hook_style") and isinstance(preset["hook_style"], dict):
            hook_style = {**preset["hook_style"], **hook_style}
        if preset.get("subtitle_style") and isinstance(preset["subtitle_style"], dict):
            subtitle_style = {**preset["subtitle_style"], **subtitle_style}
        if not watermark_config and preset.get("watermark_style") and preset["watermark_style"].get("enabled"):
            watermark_config = preset["watermark_style"]
        if not cta_config and preset.get("cta_style") and preset["cta_style"].get("enabled"):
            cta_config = preset["cta_style"]
        if not ai_text_config and preset.get("text_emphasis_style"):
            ai_text_config = {"enabled": True, "style": preset["text_emphasis_style"]}

    return hook_style, subtitle_style, watermark_config, cta_config, ai_text_config


@router.post("/plan", response_model=JobStatusResponse)
async def plan_video(
    req: GenerateVideoRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    """Start interactive planning: generates script & searches footage candidates."""
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

    hook_style, subtitle_style, watermark_config, cta_config, ai_text_config = _resolve_job_styles(req, user.id)

    job = vg.create_job(
        topic=req.topic,
        target_duration=target_duration,
        tts_provider=req.tts_provider,
        tts_model=req.tts_model,
        voice=req.voice,
        speed=req.speed,
        instructions=req.instructions,
        num_scenes=req.num_scenes,
        subtitles_enabled=req.subtitles_enabled,
        subtitle_style=subtitle_style,
        hook_enabled=req.hook_enabled,
        custom_hook=req.custom_hook,
        hook_style=hook_style,
        include_bgm=req.include_bgm,
        bgm_volume=req.bgm_volume,
        source_video_url=req.source_video_url,
        agentic_understanding=req.agentic_understanding,
        language=req.language,
        video_processing_mode=req.video_processing_mode,
        media_resolution=req.media_resolution,
        fps=req.fps,
        start_offset=req.start_offset,
        end_offset=req.end_offset,
        watermark_config=watermark_config,
        transition=req.transition,
        cta_config=cta_config,
        ai_text_config=ai_text_config,
        user_id=user.id,
    )
    job.status = VideoGenStatus.PLANNING

    background_tasks.add_task(vg.plan_scenes_and_footage, job.job_id)
    return _job_to_response(job)


@router.post("/upload-source-video")
async def upload_source_video(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
):
    """Upload a source video directly to analyze with Gemini Video Understanding (Files API or Inline Data)."""
    import json
    from pathlib import Path
    import re
    import subprocess
    import uuid

    ext = Path(file.filename or "").suffix.lower()
    ALLOWED_EXTS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Format file '{ext}' tidak didukung. Format yang diizinkan: {', '.join(sorted(ALLOWED_EXTS))}",
        )

    upload_dir = Path(settings.STORAGE_PATH) / "source_videos"
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename or "video").stem)[:60]
    out_name = f"{safe_name}_{uuid.uuid4().hex[:8]}{ext}"
    dest_path = upload_dir / out_name

    content = await file.read()
    dest_path.write_bytes(content)
    size_bytes = len(content)

    duration = 0.0
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(dest_path)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode == 0:
            dur_data = json.loads(res.stdout or "{}")
            duration = float(dur_data.get("format", {}).get("duration", 0.0))
    except Exception:
        pass

    return {
        "file_path": str(dest_path),
        "filename": file.filename,
        "size_bytes": size_bytes,
        "duration": duration,
        "duration_mm_ss": f"{int(duration//60):02d}:{int(duration%60):02d}",
        "is_inline_eligible": size_bytes < 20 * 1024 * 1024,
    }


@router.post("/jobs/{job_id}/search-scene")
async def search_scene(
    job_id: str,
    req: SearchSceneRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Search alternative footage candidates for a specific scene."""
    from src.application.video_generator import get_video_generator

    vg = get_video_generator()
    job = vg.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not user.is_superadmin and job.user_id and job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        candidates = await vg.search_scene_footage(job_id, req.scene_id, req.query)
        return {"scene_id": req.scene_id, "candidates": candidates}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/render-selected", response_model=JobStatusResponse)
async def render_selected(
    req: RenderSelectedRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    """Start rendering with user-selected footage candidates for each scene."""
    from src.application.video_generator import get_video_generator

    vg = get_video_generator()
    job = vg.get_job(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not user.is_superadmin and job.user_id and job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")

    if req.preset_slug:
        try:
            from src.presentation.routes.presets import get_preset_by_slug
            preset = get_preset_by_slug(user.id, req.preset_slug)
            if preset:
                if preset.get("hook_style") and isinstance(preset["hook_style"], dict):
                    job.hook_style = {**preset["hook_style"], **(job.hook_style or {})}
                if preset.get("subtitle_style") and isinstance(preset["subtitle_style"], dict):
                    job.subtitle_style = {**preset["subtitle_style"], **(job.subtitle_style or {})}
                if not job.watermark_config and preset.get("watermark_style") and preset["watermark_style"].get("enabled"):
                    job.watermark_config = preset["watermark_style"]
                if not job.cta_config and preset.get("cta_style") and preset["cta_style"].get("enabled"):
                    job.cta_config = preset["cta_style"]
        except Exception as pe:
            logger.warning(f"render_selected: failed to resolve preset '{req.preset_slug}': {pe}")

    if req.hook_enabled is not None:
        job.hook_enabled = req.hook_enabled
    if req.custom_hook is not None:
        job.custom_hook = req.custom_hook
    if req.hook_style_config is not None:
        job.hook_style = {**(job.hook_style or {}), **req.hook_style_config}
    if req.subtitles_enabled is not None:
        job.subtitles_enabled = req.subtitles_enabled
    if req.subtitle_style_config is not None:
        job.subtitle_style = {**(job.subtitle_style or {}), **req.subtitle_style_config}
    if req.include_bgm is not None:
        job.include_bgm = req.include_bgm
    if req.bgm_volume is not None:
        job.bgm_volume = req.bgm_volume
    if req.aspect_ratio is not None:
        job.aspect_ratio = req.aspect_ratio
    if req.watermark_config is not None:
        job.watermark_config = req.watermark_config
    if req.transition is not None:
        job.transition = req.transition
    if req.cta_config is not None:
        job.cta_config = req.cta_config
    if req.ai_text_config is not None:
        job.ai_text_config = req.ai_text_config

    vg._persist_job(job)

    background_tasks.add_task(vg.render_with_selected_scenes, req.job_id, req.selected_scenes)
    return _job_to_response(job)


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    page: int = 1,
    limit: int = 10,
    status: Optional[str] = None,
    all_users: bool = True,
    user_id: Optional[int] = None,
    user: CurrentUser = Depends(get_current_user),
):
    """List all video generation jobs with pagination and optional status filter.
    
    Superadmin sees all jobs across all users by default. Regular users strictly see their own jobs.
    """
    from src.application.video_generator import get_video_generator
    import math

    safe_page = max(1, page)
    safe_limit = max(1, min(100, limit))
    offset = (safe_page - 1) * safe_limit

    if user.is_superadmin:
        if user_id is not None:
            filter_user_id = user_id
        elif not all_users:
            filter_user_id = user.id
        else:
            filter_user_id = None
    else:
        filter_user_id = user.id

    vg = get_video_generator()
    total = vg.count_jobs(user_id=filter_user_id, status=status)
    jobs = vg.list_jobs(user_id=filter_user_id, limit=safe_limit, offset=offset, status=status)
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
    user: CurrentUser = Depends(get_current_user),
):
    """Get video generation job status."""
    from src.application.video_generator import get_video_generator

    vg = get_video_generator()
    job = vg.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not user.is_superadmin and job.user_id and job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")

    return _job_to_response(job)


def _find_job_video_path(job_id: str, job_output_path: Optional[str] = None) -> Optional[str]:
    """Find video file on disk across known candidate locations with maximum resilience."""
    candidates = []
    if job_output_path:
        candidates.append(job_output_path)
        if not os.path.isabs(job_output_path):
            candidates.append(os.path.abspath(job_output_path))
            backend_base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            candidates.append(os.path.join(backend_base, job_output_path))

    out_dir = settings.VIDEO_GEN_OUTPUT_DIR
    candidates.extend([
        os.path.join(out_dir, job_id, f"final_{job_id}.mp4"),
        os.path.join(out_dir, job_id, f"output_{job_id}.mp4"),
        os.path.join(out_dir, job_id, f"{job_id}.mp4"),
        os.path.join(out_dir, job_id, "final.mp4"),
        os.path.join(out_dir, job_id, "output.mp4"),
        os.path.join(out_dir, f"final_{job_id}.mp4"),
        os.path.join(out_dir, f"output_{job_id}.mp4"),
        os.path.join(out_dir, f"{job_id}.mp4"),
        os.path.join("data", "video_generator_output", job_id, f"final_{job_id}.mp4"),
        os.path.join("data", "video_generator_output", job_id, f"output_{job_id}.mp4"),
        os.path.join("data", "video_generator_output", job_id, f"{job_id}.mp4"),
        os.path.join("data", "video_generator_output", job_id, "final.mp4"),
        os.path.join("data", "video_generator_output", job_id, "output.mp4"),
        os.path.join("data", "video_generator_output", f"final_{job_id}.mp4"),
        os.path.join("data", "video_generator_output", f"{job_id}.mp4"),
        os.path.join("backend", "data", "video_generator_output", job_id, f"final_{job_id}.mp4"),
        os.path.join("backend", "data", "video_generator_output", job_id, "final.mp4"),
        os.path.join(getattr(settings, "OUTPUT_DIR", "data/output"), job_id, f"final_{job_id}.mp4"),
        os.path.join(getattr(settings, "OUTPUT_DIR", "data/output"), job_id, "final.mp4"),
        os.path.join(getattr(settings, "OUTPUT_DIR", "data/output"), job_id, "final", "clip_01_final.mp4"),
        os.path.join(getattr(settings, "OUTPUT_DIR", "data/output"), job_id, "clip_01_final.mp4"),
        os.path.join(getattr(settings, "OUTPUT_DIR", "data/output"), job_id, "clip_01.mp4"),
        os.path.join("data", "output", job_id, "final.mp4"),
        os.path.join("data", "output", job_id, "output.mp4"),
    ])
    for p in candidates:
        if p and os.path.exists(p) and os.path.getsize(p) > 0:
            return p

    # Directory inspection fallback: if job directory exists, find first non-empty mp4
    search_dirs = [
        os.path.join(out_dir, job_id),
        os.path.join("data", "video_generator_output", job_id),
        os.path.join("backend", "data", "video_generator_output", job_id),
        os.path.join(getattr(settings, "OUTPUT_DIR", "data/output"), job_id),
    ]
    for sdir in search_dirs:
        if os.path.isdir(sdir):
            mp4s = [os.path.join(sdir, f) for f in os.listdir(sdir) if f.endswith(".mp4")]
            # Sort final/output first
            mp4s.sort(key=lambda x: (0 if "final" in x else 1 if "output" in x else 2))
            for fpath in mp4s:
                if os.path.getsize(fpath) > 0:
                    return fpath

    return None


@router.get("/jobs/{job_id}/video")
async def get_job_video(
    job_id: str,
    token: Optional[str] = Query(None),
    range: Optional[str] = Header(None, alias="range"),
):
    """Public media serving endpoint for social autopost (Repliz) and video playback.
    Supports HTTP Range requests and streaming chunks.
    """
    from src.application.video_generator import get_video_generator
    from starlette.responses import StreamingResponse

    vg = get_video_generator()
    job = vg.get_job(job_id)
    file_path = _find_job_video_path(job_id, job.output_path if job else None)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Video for job {job_id} not found")

    file_size = os.path.getsize(file_path)
    start, end = _parse_byte_range(range, file_size)
    chunk_size = end - start + 1

    def iter_file():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = chunk_size
            while remaining > 0:
                read_size = min(remaining, 1024 * 1024)
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


@router.get("/jobs/{job_id}/download")
async def download_video(
    job_id: str,
    token: Optional[str] = Query(None),
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """Download the final generated video with optional token or bearer auth."""
    from src.application.video_generator import get_video_generator
    from src.infrastructure.auth import decode_access_token

    eff_user = user
    if not eff_user and token:
        payload = decode_access_token(token)
        if payload:
            eff_user = CurrentUser(
                user_id=int(payload.get("sub") or payload.get("user_id") or 1),
                email=payload.get("email", ""),
                role=payload.get("role", "user"),
                permissions=payload.get("permissions", []),
            )

    vg = get_video_generator()
    job = vg.get_job(job_id)

    if eff_user and not eff_user.is_superadmin and job and job.user_id and job.user_id != eff_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to download this video")

    file_path = _find_job_video_path(job_id, job.output_path if job else None)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Output file for job {job_id} not found")

    filename = f"video_{job.job_id if job else job_id}.mp4"
    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=filename,
    )


@router.post("/jobs/{job_id}/retry", response_model=JobStatusResponse)
async def retry_video(
    job_id: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    """Retry a failed video generation job in place with the same settings (superuser or owner)."""
    from src.application.video_generator import get_video_generator

    vg = get_video_generator()
    job = vg.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not user.is_superadmin and job.user_id and job.user_id != user.id:
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
    user: CurrentUser = Depends(get_current_user),
):
    """Delete a video generation job and all its artifacts (superuser or owner)."""
    from src.application.video_generator import get_video_generator

    vg = get_video_generator()
    job = vg.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not user.is_superadmin and job.user_id and job.user_id != user.id:
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

    user_role = payload.get("role", "")
    token_user_id = payload.get("sub") or payload.get("user_id")

    vg = get_video_generator()
    job = vg.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    is_super = is_superadmin(user_role)
    is_owner = job.user_id and str(job.user_id) == str(token_user_id)
    if not is_super and not is_owner:
        raise HTTPException(status_code=403, detail="Superadmin or owner access required")

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
    user: CurrentUser = Depends(get_current_user),
):
    """Get the generated story/script for a job."""
    from src.application.video_generator import get_video_generator

    vg = get_video_generator()
    job = vg.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not user.is_superadmin and job.user_id and job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job.job_id,
        "story": job.story,
        "timeline": job.timeline,
    }


@router.get("/tts-providers", response_model=list[TTSProviderOption])
async def list_tts_providers(
    user: CurrentUser = Depends(get_current_user),
):
    """List available TTS providers and their configuration status."""
    from src.infrastructure.system_config_store import get_system_setting

    gemini_key = (
        get_system_setting("GEMINI_API_KEY")
        or getattr(settings, "GEMINI_API_KEY", "")
        or os.getenv("GEMINI_API_KEY", "")
    )
    deepgram_key = (
        get_system_setting("DEEPGRAM_API_KEY")
        or getattr(settings, "DEEPGRAM_API_KEY", "")
        or os.getenv("DEEPGRAM_API_KEY", "")
    )

    return [
        TTSProviderOption(
            id="gemini",
            name="Google Gemini (Flash TTS)",
            description="Native Indonesian & English speech synthesis with rich expressive regional styles (Free Tier & Pro)",
            is_configured=bool(gemini_key and str(gemini_key).strip()),
            default_model="gemini-3.1-flash-tts-preview",
            default_voice="Kore",
        ),
        TTSProviderOption(
            id="deepgram",
            name="Deepgram (Aura)",
            description="Fast Aura voice models (optional fallback)",
            is_configured=bool(deepgram_key and str(deepgram_key).strip()),
            default_model="aura-2-thalia-en",
            default_voice=settings.DEEPGRAM_TTS_VOICE,
        ),
    ]


@router.get("/models", response_model=list[TTSModelOption])
async def list_models(
    user: CurrentUser = Depends(get_current_user),
):
    """Fetch available text-to-speech models from Gemini TTS."""
    from src.infrastructure.gemini_tts import GeminiTTS

    raw_models = await GeminiTTS.fetch_models()
    return [
        TTSModelOption(
            model_id=m.get("model_id"),
            name=m.get("name") or m.get("model_id"),
            description=m.get("description"),
            free_tier=m.get("free_tier", True),
            languages=m.get("languages"),
        )
        for m in raw_models
    ]


VOICE_PREVIEW_SCRIPTS = {
    "id_jakarta": "Halo! Ini contoh suara saya dengan gaya santai dan luwes. Cocok banget buat video TikTok dan Reels kamu!",
    "id_formal": "Selamat datang. Ini adalah contoh artikulasi suara formal dan berwibawa untuk video dokumenter Anda.",
    "id_storytelling": "Bayangkan sebuah kisah yang tak pernah kamu dengar sebelumnya. Dengarkan intonasi cerita ini dengan seksama.",
    "id_jawa": "Sugeng rawuh. Iki conto suara aksen Jawa sing medok, ramah, lan sumeh kanggo video panjenengan.",
    "id_sunda": "Sampurasun! Ieu conto sora Sunda anu lemes, riang, tur darehdeh kanggo pidio anjeun.",
    "id_batak": "Horas! Ini contoh suara gaya Medan yang tegas, bertenaga, dan penuh percaya diri untuk video kamu!",
    "id_timur": "Halo semua! Ini contoh suara dengan dialek Indonesia Timur yang ceria dan penuh semangat!",
    "en_us_story": "Hello! This is a natural sample of my voice for engaging storytelling and captivating content.",
    "en_us_energetic": "Hey there! Check out this high-energy voice delivery tailored for viral short-form videos!",
    "en_uk_documentary": "Good day. This is a refined British voice sample designed for sophisticated documentary explainers.",
    "en_aus_casual": "G'day! Here's a relaxed and friendly Australian voice sample for your video.",
}
DEFAULT_PREVIEW_SCRIPT_ID = "Halo! Ini adalah contoh pratinjau kualitas suara saya untuk video Anda."
DEFAULT_PREVIEW_SCRIPT_EN = "Hello! This is a preview sample of my voice for your video."


@router.get("/voices/preview")
async def preview_voice(
    voice: str = Query(..., description="Voice model or combined key (e.g. Kore__id_jakarta or Kore)"),
    provider: str = Query("gemini", description="gemini or deepgram"),
    model: Optional[str] = Query(None, description="TTS model ID"),
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    """Generate and stream a voice preview sample on the fly (cached)."""
    from src.infrastructure.auth import decode_access_token

    # Support either Bearer header or token query param (for HTML Audio elements)
    jwt_token = token
    if not jwt_token and authorization and authorization.startswith("Bearer "):
        jwt_token = authorization.split("Bearer ")[1].strip()

    if not jwt_token:
        raise HTTPException(status_code=401, detail="Authentication token required (?token=)")

    payload = decode_access_token(jwt_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    cache_dir = os.path.join(getattr(settings, "VIDEO_GEN_OUTPUT_DIR", "tmp/video_generator"), "voice_previews")
    os.makedirs(cache_dir, exist_ok=True)

    safe_voice_key = "".join(c if c.isalnum() or c in "_-" else "_" for c in voice)
    cache_path = os.path.join(cache_dir, f"preview_{provider}_{safe_voice_key}.mp3")

    if not os.path.exists(cache_path) or os.path.getsize(cache_path) == 0:
        actual_voice = voice
        actual_style = None
        if "__" in voice:
            parts = voice.split("__", 1)
            actual_voice = parts[0]
            actual_style = parts[1]

        if provider.lower() == "deepgram":
            from src.infrastructure.deepgram_tts import DeepgramTTS
            tts = DeepgramTTS(output_dir=cache_dir)
            sample_text = DEFAULT_PREVIEW_SCRIPT_EN
            out_file = await tts.synthesize(text=sample_text, voice=actual_voice, output_path=cache_path)
            if not out_file or not os.path.exists(out_file):
                raise HTTPException(status_code=500, detail="Failed to synthesize Deepgram preview")
        else:
            from src.infrastructure.gemini_tts import GeminiTTS
            tts = GeminiTTS(output_dir=cache_dir)
            sample_text = VOICE_PREVIEW_SCRIPTS.get(
                actual_style or "",
                DEFAULT_PREVIEW_SCRIPT_ID if (actual_style and "id" in actual_style) else DEFAULT_PREVIEW_SCRIPT_EN
            )
            out_file = await tts.synthesize(
                text=sample_text,
                voice_id=actual_voice,
                model_id=model or "gemini-3.1-flash-tts-preview",
                voice_style=actual_style,
                output_path=cache_path,
            )
            if not out_file or not os.path.exists(out_file):
                raise HTTPException(status_code=500, detail="Failed to synthesize Gemini voice preview")

    return FileResponse(
        cache_path,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/voices", response_model=list[VoiceOption])
async def list_voices(
    provider: Optional[str] = Query(None, description="gemini or deepgram"),
    language: Optional[str] = Query(None, description="id, en, or all"),
    user: CurrentUser = Depends(get_current_user),
):
    """List available TTS voices for Gemini and/or Deepgram."""
    results: list[VoiceOption] = []
    prov_clean = (provider or "").strip().lower()

    if not prov_clean or prov_clean == "gemini":
        from src.infrastructure.gemini_tts import GeminiTTS
        gemini_voices = await GeminiTTS.fetch_voices(language=language)
        for v in gemini_voices:
            model_key = v.get("model") or v.get("voice_id")
            results.append(
                VoiceOption(
                    key=v.get("key"),
                    model=model_key,
                    provider="gemini",
                    description=v.get("description"),
                    category=v.get("category"),
                    gender=v.get("gender"),
                    accent=v.get("accent"),
                    language=v.get("language"),
                    country=v.get("country") or "Indonesia / Global",
                    flag=v.get("flag") or "ID",
                    preview_url=f"/api/video-generator/voices/preview?voice={model_key}&provider=gemini",
                    voice_id=v.get("voice_id"),
                    style_id=v.get("style_id"),
                )
            )

    if not prov_clean or prov_clean == "deepgram":
        from src.infrastructure.deepgram_tts import DEEPGRAM_VOICES
        for key, model in DEEPGRAM_VOICES.items():
            results.append(
                VoiceOption(
                    key=key,
                    model=model,
                    provider="deepgram",
                    description=f"Deepgram Aura voice: {key.capitalize()}",
                    category="aura",
                    gender="female" if key in ["thalia", "asteria", "luna", "stella", "hera"] else "male",
                    accent="american",
                    language="en",
                    country="United States",
                    flag="US",
                    preview_url=f"/api/video-generator/voices/preview?voice={model}&provider=deepgram",
                    voice_id=key,
                    style_id=None,
                )
            )

    return results


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
        user_id=getattr(job, "user_id", None),
        topic=job.topic,
        status=status_val,
        progress=job.progress,
        step_label=step_label,
        target_duration=job.target_duration,
        tts_provider=job.tts_provider,
        tts_model=job.tts_model,
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
        source_video_url=getattr(job, "source_video_url", None),
        agentic_understanding=getattr(job, "agentic_understanding", True),
        language=getattr(job, "language", "id") or "id",
        video_processing_mode=getattr(job, "video_processing_mode", "agentic") or "agentic",
        media_resolution=getattr(job, "media_resolution", "low") or "low",
        fps=getattr(job, "fps", None),
        start_offset=getattr(job, "start_offset", None),
        end_offset=getattr(job, "end_offset", None),
        watermark_config=getattr(job, "watermark_config", None),
        transition=getattr(job, "transition", "dissolve") or "dissolve",
        cta_config=getattr(job, "cta_config", None),
        ai_text_config=getattr(job, "ai_text_config", None),
        title=title,
        error=job.error,
        output_path=job.output_path,
        created_at=job.created_at,
        completed_at=job.completed_at,
        scenes_count=scenes_count,
        estimated_duration=estimated_duration,
        thumbnail_url=getattr(job, "thumbnail_url", None) or thumbnail_url,
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


@router.get("/trending-topics")
async def get_trending_topics_endpoint(
    region: str = Query("ID", description="Country code (e.g. ID, US, GLOBAL)"),
    limit: int = Query(5, ge=1, le=10, description="Number of topics to return (3-5)"),
    refresh: bool = Query(False, description="Bypass cache and fetch fresh trending topics"),
    user: CurrentUser = Depends(get_current_user),
):
    """Fetch multi-source trending topics synthesized by Gemini for viral short videos."""
    from src.infrastructure.hermes_trending_service import hermes_trending_service

    topics = await hermes_trending_service.get_trending_topics(
        region=region,
        count=limit,
        limit=limit,
        use_cache=not refresh,
    )
    return {"region": region, "count": len(topics), "topics": topics}


@router.get("/jobs/{job_id}/thumbnail")
async def get_job_thumbnail(
    job_id: str,
    token: Optional[str] = None,
    refresh: bool = Query(False),
):
    """Get the keyframe thumbnail for a generated video directly from the Hook segment."""
    from starlette.responses import FileResponse
    from src.application.video_generator import get_video_generator

    vg = get_video_generator()
    job = vg.get_job(job_id)

    video_path = _find_job_video_path(job_id, job.output_path if job else None)

    # 1. If refresh requested and video exists, re-extract clean Hook frame immediately
    if refresh and video_path and os.path.exists(video_path):
        out_thumb = os.path.join(os.path.dirname(video_path), f"thumbnail_{job_id}.jpg")
        try:
            import subprocess
            subprocess.run([
                "ffmpeg", "-y", "-ss", "00:00:01.000",
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                out_thumb
            ], capture_output=True, timeout=10)
            if os.path.exists(out_thumb) and os.path.getsize(out_thumb) > 0:
                return FileResponse(out_thumb, media_type="image/jpeg")
        except Exception:
            pass

    # 2. Check direct thumbnail candidate paths
    out_dir = settings.VIDEO_GEN_OUTPUT_DIR
    thumb_candidates = [
        os.path.join(out_dir, job_id, f"thumbnail_{job_id}.jpg"),
        os.path.join(out_dir, job_id, "thumbnail.jpg"),
        os.path.join(out_dir, job_id, "thumb.jpg"),
        os.path.join("data", "video_generator_output", job_id, f"thumbnail_{job_id}.jpg"),
        os.path.join("data", "video_generator_output", job_id, "thumbnail.jpg"),
        os.path.join("data", "video_generator_output", job_id, "thumb.jpg"),
        os.path.join("backend", "data", "video_generator_output", job_id, f"thumbnail_{job_id}.jpg"),
        os.path.join("backend", "data", "video_generator_output", job_id, "thumb.jpg"),
        os.path.join(getattr(settings, "OUTPUT_DIR", "data/output"), job_id, "thumbnail", "clip_01.jpg"),
        os.path.join(getattr(settings, "OUTPUT_DIR", "data/output"), job_id, "clip_01_thumb.jpg"),
        job.thumbnail_url if (job and job.thumbnail_url) else None,
    ]
    for tp in thumb_candidates:
        if tp and os.path.exists(tp) and os.path.getsize(tp) > 0:
            return FileResponse(tp, media_type="image/jpeg")

    # 3. Extract on-the-fly from video if thumbnail file is missing
    if video_path and os.path.exists(video_path):
        out_thumb = os.path.join(os.path.dirname(video_path), f"thumbnail_{job_id}.jpg")
        try:
            import subprocess
            subprocess.run([
                "ffmpeg", "-y", "-ss", "00:00:01.000",
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                out_thumb
            ], capture_output=True, timeout=10)
            if os.path.exists(out_thumb) and os.path.getsize(out_thumb) > 0:
                return FileResponse(out_thumb, media_type="image/jpeg")
        except Exception:
            pass

    raise HTTPException(status_code=404, detail="Thumbnail not found")
