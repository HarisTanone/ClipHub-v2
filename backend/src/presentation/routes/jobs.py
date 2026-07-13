"""Job API routes — POST /jobs, GET /jobs/{id}, GET /jobs/{id}/error, GET /jobs/{id}/clips."""
import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from src.application.services import JobService
from src.config import settings
from src.infrastructure.clip_outputs import discover_ready_clip_ranks, find_final_clip
from src.presentation.auth_deps import CurrentUser, get_current_user, get_optional_user
from src.presentation.dependencies import get_job_service
from src.presentation.schemas.jobs import (
    ClipDataResponse,
    CreateJobRequest,
    JobErrorResponse,
    JobResponse,
    UploadJobOptions,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])

ALLOWED_UPLOAD_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}


async def _set_clip_operation(job_id: str, clip_rank: int, operation_id: str, **values):
    from src.infrastructure.database import async_session, JobModel
    from sqlalchemy import select, update
    async with async_session() as session:
        result = await session.execute(select(JobModel.clips_data).where(JobModel.job_id == job_id))
        data = dict(result.scalar_one_or_none() or {})
        operations = dict(data.get("operations") or {})
        operation = dict(operations.get(str(clip_rank)) or {})
        operation.update({"operation_id": operation_id, "clip_rank": clip_rank, **values, "updated_at": datetime.now(timezone.utc).isoformat()})
        operations[str(clip_rank)] = operation
        data["operations"] = operations
        await session.execute(update(JobModel).where(JobModel.job_id == job_id).values(clips_data=data))
        await session.commit()


@router.get("/{job_id}/clips/{clip_rank}/operation")
async def get_clip_operation(job_id: str, clip_rank: int, service: JobService = Depends(get_job_service), user: CurrentUser = Depends(get_current_user)):
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await _check_job_ownership(job, user)
    return {"success": True, "data": ((job.clips_data or {}).get("operations") or {}).get(str(clip_rank))}


def _safe_upload_filename(filename: str | None) -> str:
    """Return a filesystem-safe display filename."""
    raw = (filename or "uploaded_video").strip()
    stem = Path(raw).stem or "uploaded_video"
    ext = Path(raw).suffix.lower()
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "uploaded_video"
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        ext = ".mp4"
    return f"{safe_stem[:80]}{ext}"


def _source_from_clips_data(clips_data: dict | None, fallback_url: str) -> tuple[str, str]:
    source = (clips_data or {}).get("source") if isinstance(clips_data, dict) else None
    if isinstance(source, dict):
        source_type = str(source.get("type") or "youtube")
        source_label = str(source.get("filename") or source.get("label") or fallback_url)
        return source_type, source_label
    return "youtube", fallback_url


def _probe_video_duration(video_path: str) -> float:
    """Return video duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            video_path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-300:] or "ffprobe failed")

    data = json.loads(result.stdout or "{}")
    duration = float((data.get("format") or {}).get("duration") or 0)
    if duration <= 0:
        raise RuntimeError("durasi video tidak terbaca")
    return duration


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


def _probe_video_dimensions(video_path: str) -> tuple[int, int]:
    """Return source video dimensions using ffprobe."""
    import json
    import subprocess

    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            video_path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-300:] or "ffprobe failed")

    data = json.loads(result.stdout or "{}")
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError("video stream not found")

    width = int(streams[0].get("width") or 0)
    height = int(streams[0].get("height") or 0)
    if width <= 0 or height <= 0:
        raise RuntimeError("invalid video dimensions")
    return width, height


def _quality_variant_path(final_path: str, quality: str) -> str:
    final_dir = os.path.dirname(final_path)
    base_dir = os.path.dirname(final_dir) if os.path.basename(final_dir) == "final" else final_dir
    variant_dir = os.path.join(base_dir, "preview_quality")
    os.makedirs(variant_dir, exist_ok=True)

    name = os.path.splitext(os.path.basename(final_path))[0]
    return os.path.join(variant_dir, f"{name}_{quality}p.mp4")


def _ensure_preview_quality_variant(final_path: str, quality: str) -> str:
    """Create/cache a lower-resolution final preview video."""
    import subprocess

    allowed = {"720", "480", "360", "320"}
    if quality not in allowed:
        raise ValueError(f"Invalid quality '{quality}'")

    width, height = _probe_video_dimensions(final_path)
    target = int(quality)
    source_reference = width if height >= width else height
    if target >= source_reference:
        return final_path

    variant_path = _quality_variant_path(final_path, quality)
    if (
        os.path.exists(variant_path)
        and os.path.getsize(variant_path) > 0
        and os.path.getmtime(variant_path) >= os.path.getmtime(final_path)
    ):
        return variant_path

    tmp_path = f"{variant_path}.tmp.{os.getpid()}"
    scale_expr = f"{target}:-2" if height >= width else f"-2:{target}"
    crf = {"720": "24", "480": "27", "360": "30", "320": "31"}[quality]

    cmd = [
        "ffmpeg", "-y",
        "-i", final_path,
        "-vf", f"scale={scale_expr}:flags=lanczos,format=yuv420p",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", crf,
        "-c:a", "copy",
        "-movflags", "+faststart",
        tmp_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise RuntimeError(result.stderr[-500:] or "ffmpeg quality transcode failed")

    os.replace(tmp_path, variant_path)
    return variant_path


async def _check_job_ownership(job, user: CurrentUser):
    """Verify user owns this job. Superadmin bypasses."""
    if user.is_superadmin:
        return
    if job.user_id and job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")


async def _fetch_and_store_youtube_title(job_id: str, youtube_url: str, service: JobService):
    """Best-effort: fetch YouTube video title via oEmbed and store it."""
    import httpx
    match = re.search(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})", youtube_url)
    if not match:
        return
    video_id = match.group(1)
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.get(f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json")
        if resp.status_code == 200:
            title = resp.json().get("title", "")
            if title:
                await service._repo.update_video_title(job_id, title)


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
        # User ownership
        user_id=user.id,
        # V2 pipeline routing
        is_superadmin=user.is_superadmin,
    )

    # Quick YouTube title fetch via oEmbed (non-blocking, best-effort)
    if not getattr(job, "video_title", None) and not is_cached:
        try:
            await _fetch_and_store_youtube_title(job.job_id, request.youtube_url, service)
        except Exception:
            pass

    return JobResponse(
        job_id=job.job_id,
        youtube_url=job.youtube_url,
        source_type="youtube",
        source_label=job.youtube_url,
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


@router.post("/upload", status_code=201, response_model=JobResponse)
async def create_job_from_upload(
    file: UploadFile = File(...),
    options_json: str = Form("{}"),
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Buat job baru dari file video upload manual."""
    original_name = file.filename or "uploaded_video.mp4"
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Format file tidak didukung. Gunakan: {allowed}")

    content_type = (file.content_type or "").lower()
    if content_type and not (
        content_type.startswith("video/")
        or content_type in {"application/octet-stream", "application/x-matroska"}
    ):
        raise HTTPException(status_code=400, detail="File upload harus berupa video")

    try:
        options = UploadJobOptions(**json.loads(options_json or "{}"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Options upload tidak valid")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    upload_id = uuid.uuid4().hex
    safe_name = _safe_upload_filename(original_name)
    upload_dir = os.path.join(settings.DOWNLOAD_DIR, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    upload_path = os.path.join(upload_dir, f"{upload_id}_{safe_name}")
    tmp_path = f"{upload_path}.tmp"

    max_bytes = max(1, int(settings.MAX_UPLOAD_SIZE_MB)) * 1024 * 1024
    written = 0
    try:
        with open(tmp_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File terlalu besar. Maksimal {settings.MAX_UPLOAD_SIZE_MB}MB",
                    )
                out.write(chunk)
        os.replace(tmp_path, upload_path)

        if written <= 0:
            raise HTTPException(status_code=400, detail="File upload kosong")

        try:
            duration = _probe_video_duration(upload_path)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Video tidak bisa dibaca: {e}")

        if duration > settings.MAX_VIDEO_DURATION:
            menit = int(duration // 60)
            raise HTTPException(
                status_code=400,
                detail=f"Video terlalu panjang ({menit} menit). Maksimal {settings.MAX_VIDEO_DURATION // 60} menit.",
            )

        pseudo_url = f"upload://{upload_id}/{safe_name}"
        job, is_cached = await service.create_job(
            pseudo_url,
            force_reprocess=True,
            style_preset=options.style_preset,
            target_aspect_ratio=options.target_aspect_ratio,
            hook_engine=options.hook_engine,
            hook_style=options.hook_style,
            broll_enabled=options.broll_enabled,
            autogrid_enabled=options.autogrid_enabled,
            use_remotion=options.use_remotion,
            ai_layer_enabled=options.ai_layer_enabled,
            threejs_enabled=options.threejs_enabled,
            remotion_quality=options.remotion_quality,
            hook_style_config=options.hook_style_config,
            subtitle_style_config=options.subtitle_style_config,
            user_id=user.id,
            is_superadmin=user.is_superadmin,
            source_type="upload",
            source_video_path=upload_path,
            source_filename=safe_name,
            source_duration=duration,
            source_size_bytes=written,
            processing_mode=options.processing_mode,
        )
        return JobResponse(
            job_id=job.job_id,
            youtube_url=job.youtube_url,
            source_type="upload",
            source_label=safe_name,
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
    except HTTPException:
        if os.path.exists(upload_path):
            try:
                os.remove(upload_path)
            except OSError:
                pass
        raise
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        await file.close()


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
    source_type, source_label = _source_from_clips_data(job.clips_data, job.youtube_url)
    return JobResponse(
        job_id=job.job_id,
        youtube_url=job.youtube_url,
        source_type=source_type,
        source_label=source_label,
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
    quality: str = "original",
    service: JobService = Depends(get_job_service),
):
    """Stream final clip, optionally as cached preview quality."""
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")

    output_dir = f"{settings.OUTPUT_DIR}/{job_id}"
    final_path = find_final_clip(output_dir, clip_rank)
    if not final_path:
        raise HTTPException(status_code=404, detail="File final clip tidak ditemukan")

    quality = (quality or "original").lower().replace("p", "")
    if quality in {"auto", "source"}:
        quality = "original"
    if quality != "original":
        if quality not in {"720", "480", "360", "320"}:
            raise HTTPException(status_code=400, detail="Quality harus original, 720, 480, 360, atau 320")
        try:
            preview_path = _ensure_preview_quality_variant(final_path, quality)
            if preview_path == final_path:
                quality = "original"
            final_path = preview_path
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gagal membuat preview quality {quality}p: {e}")

    filename_suffix = "" if quality == "original" else f"_{quality}p"
    return _stream_video(final_path, request, f"clip_{clip_rank}_final{filename_suffix}.mp4")


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


@router.get("/{job_id}/source-thumb")
async def get_source_thumbnail(job_id: str, service: JobService = Depends(get_job_service), user: CurrentUser = Depends(get_current_user)):
    """Return a smart thumbnail from uploaded source — picks best frame with face focus."""
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await _check_job_ownership(job, user)
    source = (job.clips_data or {}).get("source", {}) if isinstance(job.clips_data, dict) else {}
    source_path = source.get("path") if isinstance(source, dict) else None
    if not source_path or not os.path.exists(source_path):
        raise HTTPException(status_code=404, detail="Upload source not available")
    thumb_dir = os.path.join(settings.OUTPUT_DIR, job_id, "thumbnail")
    os.makedirs(thumb_dir, exist_ok=True)
    thumb_path = os.path.join(thumb_dir, "source.jpg")
    if os.path.exists(thumb_path) and os.path.getmtime(thumb_path) >= os.path.getmtime(source_path):
        return FileResponse(thumb_path, media_type="image/jpeg", filename="source.jpg")

    # Get video duration for smart timestamp selection
    duration = (source.get("duration") or job.video_duration or 30)

    # Strategy: use FFmpeg thumbnail filter which analyzes N frames and picks
    # the most representative one (avoids black frames, transitions, blur).
    # Then crop to upper-center (where faces typically are in talking-head videos).
    try:
        # First try: thumbnail filter (picks best frame from first 30s)
        seek = min(1, duration * 0.1)
        analyze_duration = min(30, duration * 0.5)
        result = subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(seek),
            "-i", source_path,
            "-t", str(analyze_duration),
            "-vf", "thumbnail=300,crop=in_w:in_w*9/16:0:(in_h-in_w*9/16)/4,scale=480:852",
            "-frames:v", "1",
            "-q:v", "2",
            thumb_path,
        ], capture_output=True, text=True, timeout=60)

        # If crop filter fails (e.g. landscape video), fallback to simple scale
        if result.returncode != 0 or not os.path.exists(thumb_path):
            result = subprocess.run([
                "ffmpeg", "-y",
                "-ss", str(min(3, duration * 0.15)),
                "-i", source_path,
                "-vf", "thumbnail=100,scale=640:-2",
                "-frames:v", "1",
                "-q:v", "2",
                thumb_path,
            ], capture_output=True, text=True, timeout=60)

        # Final fallback: just grab a frame at 3s
        if result.returncode != 0 or not os.path.exists(thumb_path):
            subprocess.run([
                "ffmpeg", "-y",
                "-ss", str(min(3, duration * 0.1)),
                "-i", source_path,
                "-frames:v", "1",
                "-vf", "scale=640:-2",
                "-q:v", "3",
                thumb_path,
            ], capture_output=True, text=True, timeout=60)

    except subprocess.TimeoutExpired:
        # Ultra fallback
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "1", "-i", source_path, "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "3", thumb_path],
            capture_output=True, text=True, timeout=30
        )

    if not os.path.exists(thumb_path):
        raise HTTPException(status_code=500, detail="Could not generate source thumbnail")
    return FileResponse(thumb_path, media_type="image/jpeg", filename="source.jpg")


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
        source_type, source_label = _source_from_clips_data(model.clips_data, model.youtube_url)
        # Check for active restyle/operations
        operations = (model.clips_data or {}).get("operations", {}) if isinstance(model.clips_data, dict) else {}
        active_ops = [op for op in operations.values() if isinstance(op, dict) and op.get("status") == "running"]
        jobs.append({
            "job_id": model.job_id,
            "youtube_url": model.youtube_url,
            "source_type": source_type,
            "source_label": source_label,
            "video_title": getattr(model, "video_title", None) or "",
            "status": model.status,
            "video_duration": model.video_duration,
            "clips_total": model.clips_total,
            "clips_success": model.clips_success,
            "clips_failed": model.clips_failed,
            "style_preset": model.style_preset,
            "target_aspect_ratio": model.target_aspect_ratio,
            "pipeline_version": getattr(model, "pipeline_version", "v1"),
            "active_operations": len(active_ops),
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
    source_type, source_label = _source_from_clips_data(job.clips_data, job.youtube_url)

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

    ready_ranks = set(discover_ready_clip_ranks(output_dir))
    is_terminal = job.status.value in ("completed", "failed", "timeout")

    # Extract clips info. Candidate metadata is stored as soon as AI analysis
    # finishes, while readiness is resolved independently for every final file.
    clips_info = []
    clip_candidates = (
        job.clips_data.get("clips", [])
        if isinstance(job.clips_data, dict)
        else []
    )
    if not clip_candidates and job.clips_total > 0:
        # Running jobs created by an older worker may only have the count. Keep
        # the UI useful by exposing ranked placeholders until metadata arrives.
        clip_candidates = [
            {"rank": rank, "start": 0, "end": 0}
            for rank in range(1, job.clips_total + 1)
        ]

    for clip in clip_candidates:
        rank = clip.get("rank", 0)
        start = float(clip.get("start") or 0)
        end = float(clip.get("end") or 0)
        has_final = rank in ready_ranks
        clips_info.append({
            "rank": rank,
            "score": clip.get("score"),
            "start": start,
            "end": end,
            "duration": round(max(0, end - start), 1),
            "hook": clip.get("hook"),
            "reason": clip.get("reason"),
            "has_words": bool(clip.get("words")),
            "word_count": len(clip.get("words", [])),
            "has_final": has_final,
            "has_thumbnail": True,  # Auto-generated on demand from video
            "render_status": "ready" if has_final else ("unavailable" if is_terminal else "processing"),
        })

    return {
        "success": True,
        "data": {
            "job_id": job.job_id,
            "youtube_url": job.youtube_url,
            "source_type": source_type,
            "source_label": source_label,
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


@router.post("/{job_id}/reprocess", status_code=201, response_model=JobResponse)
async def reprocess_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Create a fresh tracked job using the failed job's source and settings."""
    old = await service.get_job(job_id)
    if not old:
        raise HTTPException(status_code=404, detail="Job not found")
    await _check_job_ownership(old, user)
    if old.status.value not in {"failed", "timeout"}:
        raise HTTPException(status_code=409, detail="Only failed or timed-out jobs can be reprocessed")

    source_type, source_label = _source_from_clips_data(old.clips_data, old.youtube_url)
    source = (old.clips_data or {}).get("source", {}) if isinstance(old.clips_data, dict) else {}
    source_path = source.get("path") if isinstance(source, dict) else None
    if source_type == "upload" and (not source_path or not os.path.exists(source_path)):
        raise HTTPException(status_code=410, detail="Original upload is no longer available. Upload the video again.")

    fresh, _ = await service.create_job(
        old.youtube_url,
        force_reprocess=True,
        style_preset=old.style_preset or "",
        target_aspect_ratio=old.target_aspect_ratio or "9:16",
        hook_engine=old.hook_engine,
        hook_style=old.hook_style,
        broll_enabled=bool(old.broll_enabled),
        autogrid_enabled=bool(old.autogrid_enabled),
        use_remotion=bool(old.use_remotion),
        ai_layer_enabled=bool(old.ai_layer_enabled),
        threejs_enabled=bool(old.threejs_enabled),
        remotion_quality=old.remotion_quality,
        hook_style_config=(old.clips_data or {}).get("hook_style_config"),
        subtitle_style_config=(old.clips_data or {}).get("subtitle_style_config"),
        user_id=user.id,
        is_superadmin=user.is_superadmin,
        source_type=source_type,
        source_video_path=source_path,
        source_filename=source_label,
        source_duration=source.get("duration") if isinstance(source, dict) else None,
        source_size_bytes=source.get("size_bytes") if isinstance(source, dict) else None,
        processing_mode=(old.clips_data or {}).get("processing_mode", "analyze"),
    )
    return JobResponse(
        job_id=fresh.job_id, youtube_url=fresh.youtube_url, source_type=source_type,
        source_label=source_label, status=fresh.status.value, video_duration=fresh.video_duration,
        clips_data=fresh.clips_data, clips_total=fresh.clips_total, clips_success=fresh.clips_success,
        clips_failed=fresh.clips_failed, style_preset=fresh.style_preset,
        target_aspect_ratio=fresh.target_aspect_ratio, use_remotion=fresh.use_remotion,
        ai_layer_enabled=fresh.ai_layer_enabled, threejs_enabled=fresh.threejs_enabled,
        remotion_quality=fresh.remotion_quality, pipeline_version=fresh.pipeline_version,
        created_at=fresh.created_at, updated_at=fresh.updated_at,
    )


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Delete a job and all its output files.

    Only works for completed/failed/timeout jobs (terminal states).
    Superadmin can delete any job. Regular users can only delete their own.
    """
    import shutil

    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await _check_job_ownership(job, user)

    terminal_statuses = {"completed", "failed", "timeout"}
    if job.status.value not in terminal_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete job in '{job.status.value}' status. Cancel it first.",
        )

    # Delete output files
    output_dir = f"{settings.OUTPUT_DIR}/{job_id}"
    if os.path.isdir(output_dir):
        shutil.rmtree(output_dir, ignore_errors=True)

    # Delete download file
    download_path = f"{settings.DOWNLOAD_DIR}/{job_id}.mp4"
    if os.path.exists(download_path):
        os.remove(download_path)

    # Delete from database
    from src.infrastructure.database import async_session, JobModel
    from sqlalchemy import delete as sql_delete
    async with async_session() as session:
        await session.execute(sql_delete(JobModel).where(JobModel.job_id == job_id))
        await session.commit()

    return {"success": True, "message": f"Job '{job_id}' deleted"}


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
            "hook_style": clip_data.get("hook_style_override"),
            "hook_style_config": (
                clip_data.get("hook_style_config_override")
                or (job.clips_data or {}).get("hook_style_config")
                or {}
            ),
            "subtitle_style_config": (
                clip_data.get("subtitle_style_config_override")
                or (job.clips_data or {}).get("subtitle_style_config")
                or {}
            ),
            "reframe_layout": clip_data.get("reframe_layout") or clip_data.get("layout") or "single",
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
    subtitle_style_config: Opt[dict] = None  # Optional per-clip subtitle config overrides


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
            if body.subtitle_style_config:
                clip["subtitle_style_config_override"] = body.subtitle_style_config
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
            "subtitle_style_config": body.subtitle_style_config,
        },
        "message": f"Style override set for clip #{clip_rank}. Call /restyle to apply with Remotion.",
    }


@router.post("/{job_id}/clips/{clip_rank}/rerender")
async def rerender_clip(
    job_id: str,
    clip_rank: int,
    body: RerenderRequest = None,
    service: JobService = Depends(get_job_service),
    user: CurrentUser = Depends(get_current_user),
):
    """Deprecated hook-only rerender endpoint.

    Hook/subtitle rendering is Remotion-only through /restyle so output matches preview.
    """
    raise HTTPException(
        status_code=410,
        detail="Hook-only /rerender is disabled. Use /restyle; it renders hook and subtitle via Remotion.",
    )


# ─── Restyle: Full re-render chain (hook + broll + subtitle) from raw clip ────

class RestyleRequest(BaseModel):
    """Restyle a clip: re-apply hook + broll + subtitle from raw/reframed source."""
    hook_text: Opt[str] = None
    hook_style: Opt[str] = None
    hook_style_config: Opt[dict] = None
    subtitle_style_config: Opt[dict] = None
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

    Source: always the requested rank's raw clip, then re-centered.
    Output: replaces final/clip_{rank}_final.mp4
    """
    import logging
    import shutil

    logger = logging.getLogger(__name__)
    operation_id = f"restyle_{uuid.uuid4().hex[:12]}"

    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await _check_job_ownership(job, user)
    await _set_clip_operation(job_id, clip_rank, operation_id, type="restyle", status="running", stage="prepare", percentage=5, started_at=datetime.now(timezone.utc).isoformat(), error=None)

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

    # Always start from this rank's raw clip. Reusing an older reframed file
    # would accumulate crops and can make preview/output drift after restyles.
    output_dir = f"{settings.OUTPUT_DIR}/{job_id}"
    raw_candidates = [
        f"{output_dir}/raw/clip_{clip_rank:02d}.mp4",
        f"{output_dir}/raw/clip_{clip_rank}.mp4",
        f"{output_dir}/clip_{clip_rank:02d}.mp4",
    ]
    raw_path = next((path for path in raw_candidates if os.path.exists(path)), None)
    if raw_path is None:
        raise HTTPException(status_code=400, detail="Raw clip not found. Run full pipeline first.")

    # Resolve parameters
    root_style_data = job.clips_data if isinstance(job.clips_data, dict) else {}
    hook_config = (
        body.hook_style_config if body and body.hook_style_config is not None
        else clip_data.get("hook_style_config_override")
        or root_style_data.get("hook_style_config")
        or {}
    )
    subtitle_config = (
        body.subtitle_style_config if body and body.subtitle_style_config is not None
        else clip_data.get("subtitle_style_config_override")
        or root_style_data.get("subtitle_style_config")
        or {}
    )
    hook_text = (body.hook_text if body and body.hook_text else clip_data.get("hook", "")).strip()
    hook_style = (
        body.hook_style if body and body.hook_style
        else clip_data.get("hook_style_override")
        or hook_config.get("animation")
        or job.hook_style
        or settings.HOOK_DEFAULT_STYLE
    )
    do_subtitle = body.subtitle_enabled if body else True
    do_broll = body.broll_enabled if body else True

    # Prepare paths
    os.makedirs(f"{output_dir}/final", exist_ok=True)
    brolled_path = f"{output_dir}/clip_{clip_rank:02d}_brolled.mp4"
    restyle_reframed_path = f"{output_dir}/clip_{clip_rank:02d}_restyle_reframed.mp4"
    canonical_reframed_path = f"{output_dir}/clip_{clip_rank:02d}_reframed.mp4"
    final_path = f"{output_dir}/final/clip_{clip_rank}_final.mp4"
    staged_final_path = f"{output_dir}/final/clip_{clip_rank}_final.restyle.mp4"

    try:
        await _set_clip_operation(job_id, clip_rank, operation_id, stage="reframe", percentage=20)
        current_path = raw_path
        reframe_result = None

        # Re-run centering/crop for the active clip only. Auto-grid is still
        # conservative inside the reframe engine and requires unique people.
        reframe_engine = getattr(service, "_yolo_reframe", None)
        if reframe_engine:
            try:
                reframe_result = await reframe_engine.process(
                    raw_path,
                    restyle_reframed_path,
                    job.target_aspect_ratio or "9:16",
                    bool(job.autogrid_enabled),
                    content_profile=(job.clips_data or {}).get("content_profile", {}),
                )
                candidate_path = (
                    reframe_result.get("output_path")
                    if isinstance(reframe_result, dict)
                    else None
                )
                if candidate_path and os.path.exists(candidate_path):
                    current_path = candidate_path
                elif os.path.exists(restyle_reframed_path):
                    current_path = restyle_reframed_path
            except Exception as e:
                logger.warning(f"[restyle] person centering failed clip {clip_rank}: {e}")

        if (job.target_aspect_ratio or "9:16") == "9:16" and current_path == raw_path:
            raise HTTPException(
                status_code=503,
                detail="Person centering is unavailable; the existing final clip was preserved.",
            )

        # Step 1: B-Roll overlay (if enabled and brolls exist for this clip).
        # Remotion is applied after this so hook/subtitle remain on top.
        if do_broll and service._broll_injector:
            await _set_clip_operation(job_id, clip_rank, operation_id, stage="assets", percentage=40)
            from src.domain.entities import BRollSuggestion, Clip, VisualCategory
            broll_suggestions = []
            for bs in clip_data.get("broll_suggestions", []):
                try:
                    visual_category = VisualCategory(bs.get("visual_category", "footage"))
                except (ValueError, KeyError):
                    visual_category = VisualCategory.FOOTAGE

                broll_suggestions.append(BRollSuggestion(
                    at_time=float(bs.get("at_time", 0)),
                    keyword=bs.get("keyword", ""),
                    template=bs.get("template", "word_pop_typography"),
                    duration=float(bs.get("duration", 2.0)),
                    reason=bs.get("reason", ""),
                    visual_category=visual_category,
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

        # Step 2: Remotion renders hook + subtitle with the same style config
        # used by the live preview. FFmpeg fallback is intentionally disabled
        # for hook/subtitle so the final video cannot diverge from preview.
        remotion_rendered = False
        clip_duration = float(
            clip_data.get("duration")
            or max(0.0, float(clip_data.get("end", 0)) - float(clip_data.get("start", 0)))
            or 30.0
        )
        render_words = clip_data.get("words") or []
        if do_subtitle and render_words:
            try:
                from src.infrastructure.subtitle_words import sanitize_subtitle_words
                render_words = sanitize_subtitle_words(render_words, clip_duration)
            except Exception as e:
                logger.warning(f"[restyle] subtitle word sanitize failed clip {clip_rank}: {e}")
        else:
            render_words = []

        remotion_adapter = getattr(service, "_remotion_adapter", None)
        if remotion_adapter and (hook_text or render_words):
            await _set_clip_operation(job_id, clip_rank, operation_id, stage="render", percentage=55)
            try:
                remotion_ready = await remotion_adapter.health_check()
                if not remotion_ready and hasattr(remotion_adapter, "start_server"):
                    started = await remotion_adapter.start_server()
                    remotion_ready = bool(started and await remotion_adapter.health_check())

                if remotion_ready:
                    from src.domain.interfaces_remotion import RemotionRenderConfig
                    render_config = RemotionRenderConfig(
                        concurrency=settings.REMOTION_CONCURRENCY,
                        quality=settings.REMOTION_QUALITY,
                        enable_threejs=settings.REMOTION_ENABLE_THREEJS,
                        enable_ai_layer=settings.REMOTION_ENABLE_AI_LAYER,
                    )
                    creative_direction = {
                        "hook_style_config": hook_config,
                        "subtitle_style_config": subtitle_config,
                    }
                    result = await remotion_adapter.render_clip(
                        scene_graph={
                            "clip_rank": clip_rank,
                            "duration": clip_duration,
                            "layers": [],
                        },
                        creative_direction=creative_direction,
                        video_path=current_path,
                        output_path=staged_final_path,
                        clip_rank=clip_rank,
                        config=render_config,
                        words=render_words,
                        hook_text=hook_text,
                        hook_style=hook_style,
                    )
                    remotion_rendered = bool(result.success and os.path.exists(staged_final_path))
                    if remotion_rendered:
                        current_path = staged_final_path
                        logger.info(f"[restyle] remotion applied clip {clip_rank} style={hook_style}")
                    else:
                        logger.warning(
                            f"[restyle] remotion failed clip {clip_rank}: "
                            f"{getattr(result, 'error_message', 'unknown error')}"
                        )
            except Exception as e:
                logger.warning(f"[restyle] remotion failed clip {clip_rank}: {e}")

        if (hook_text or render_words) and not remotion_rendered:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Remotion render failed or is unavailable. "
                    "Hook/subtitle FFmpeg fallback is disabled so output matches preview."
                ),
            )

        if not hook_text and not render_words and current_path != staged_final_path:
            shutil.copy2(current_path, staged_final_path)
            current_path = staged_final_path

        if not os.path.exists(staged_final_path):
            raise HTTPException(status_code=503, detail="Restyle did not produce a final video")

        # Keep the old final playable until the replacement is complete.
        os.replace(staged_final_path, final_path)
        await _set_clip_operation(job_id, clip_rank, operation_id, stage="finalize", percentage=92)
        current_path = final_path
        if os.path.exists(restyle_reframed_path):
            os.replace(restyle_reframed_path, canonical_reframed_path)
        # Keep legacy file layouts synchronized for thumbnails and older routes.
        for compatibility_path in (
            f"{output_dir}/clip_{clip_rank:02d}_final.mp4",
            f"{output_dir}/final/clip_{clip_rank:02d}.mp4",
        ):
            try:
                shutil.copy2(final_path, compatibility_path)
            except Exception as e:
                logger.warning(f"[restyle] compatibility copy failed: {compatibility_path}: {e}")
        for thumbnail_path in (
            f"{output_dir}/thumbnail/clip_{clip_rank:02d}.jpg",
            f"{output_dir}/thumbnail/clip_{clip_rank}_thumb.jpg",
            f"{output_dir}/thumbnail/clip_{clip_rank:02d}_thumb.jpg",
            f"{output_dir}/clip_{clip_rank:02d}_thumb.jpg",
        ):
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)

        # Update clip_data with applied style
        clip_data["hook_style_override"] = hook_style
        if hook_config:
            clip_data["hook_style_config_override"] = hook_config
        if subtitle_config:
            clip_data["subtitle_style_config_override"] = subtitle_config
        if body and body.hook_text:
            clip_data["hook"] = body.hook_text

        # Persist
        from src.infrastructure.database import async_session, JobModel
        from sqlalchemy import select as sql_select, update as sql_update
        async with async_session() as session:
            current_data = (await session.execute(sql_select(JobModel.clips_data).where(JobModel.job_id == job_id))).scalar_one_or_none() or {}
            # Preserve operation tracking written during this request; job is an
            # older snapshot loaded before those progress updates.
            if current_data.get("operations"):
                job.clips_data["operations"] = current_data["operations"]
            await session.execute(
                sql_update(JobModel).where(JobModel.job_id == job_id).values(clips_data=job.clips_data)
            )
            await session.commit()

        # Cleanup temp files
        for tmp in [brolled_path, restyle_reframed_path, staged_final_path]:
            if tmp != final_path and os.path.exists(tmp):
                os.remove(tmp)

        await _set_clip_operation(job_id, clip_rank, operation_id, status="completed", stage="done", percentage=100, completed_at=datetime.now(timezone.utc).isoformat())
        return {
            "success": True,
            "data": {
                "job_id": job_id,
                "clip_rank": clip_rank,
                "hook_text": hook_text,
                "hook_style": hook_style,
                "hook_style_config": hook_config,
                "subtitle_style_config": subtitle_config,
                "subtitle_applied": do_subtitle and bool(clip_data.get("words")),
                "broll_applied": do_broll and bool(clip_data.get("broll_suggestions")),
                "reframe_method": reframe_result.get("method") if isinstance(reframe_result, dict) else None,
                "output_url": f"/api/jobs/{job_id}/clips/{clip_rank}/final",
            },
            "message": f"Clip #{clip_rank} restyled successfully",
        }

    except HTTPException as e:
        await _set_clip_operation(job_id, clip_rank, operation_id, status="failed", stage="failed", error=str(e.detail), completed_at=datetime.now(timezone.utc).isoformat())
        for tmp in [brolled_path, restyle_reframed_path, staged_final_path]:
            if os.path.exists(tmp):
                os.remove(tmp)
        raise
    except Exception as e:
        await _set_clip_operation(job_id, clip_rank, operation_id, status="failed", stage="failed", error=str(e), completed_at=datetime.now(timezone.utc).isoformat())
        for tmp in [brolled_path, restyle_reframed_path, staged_final_path]:
            if os.path.exists(tmp):
                os.remove(tmp)
        logger.error(f"restyle_error: job={job_id}, clip={clip_rank}, error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Restyle failed: {str(e)}")
