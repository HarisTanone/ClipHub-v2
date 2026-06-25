"""Remotion API routes — v3.0 Remotion integration."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.infrastructure.database import RemotionRenderModel, async_session

router = APIRouter(prefix="/remotion", tags=["Remotion"])


# ─── Response Models ──────────────────────────────────────────────────────────

class RemotionHealthResponse(BaseModel):
    status: str  # "healthy", "degraded", "unavailable"
    server_url: str
    port: int
    enabled: bool
    message: Optional[str] = None


class RemotionRenderStatus(BaseModel):
    job_id: str
    clip_rank: int
    render_job_id: Optional[str] = None
    status: str  # "queued", "rendering", "completed", "failed", "cancelled"
    progress: float
    current_frame: int
    total_frames: int
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    render_time_seconds: Optional[float] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class RemotionConfigResponse(BaseModel):
    use_remotion: bool
    ai_layer_enabled: bool
    threejs_enabled: bool
    quality: str
    concurrency: int
    server_port: int


class RemotionStatusResponse(BaseModel):
    success: bool = True
    health: RemotionHealthResponse
    config: RemotionConfigResponse
    active_jobs: int


# ─── Remotion Health & Status Endpoints ───────────────────────────────────────

@router.get("/health", response_model=RemotionHealthResponse)
async def check_remotion_health():
    """Check Remotion server health status."""
    if not settings.USE_REMOTION:
        return RemotionHealthResponse(
            status="disabled",
            server_url="",
            port=settings.REMOTION_SERVER_PORT,
            enabled=False,
            message="Remotion is disabled (USE_REMOTION=false)",
        )
    
    # Try to connect to Remotion server
    server_url = getattr(settings, 'REMOTION_SERVER_URL', f"http://localhost:{settings.REMOTION_SERVER_PORT}")
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{server_url}/health",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return RemotionHealthResponse(
                        status=data.get("status", "healthy"),
                        server_url=server_url,
                        port=settings.REMOTION_SERVER_PORT,
                        enabled=True,
                        message="Remotion server is running",
                    )
                else:
                    return RemotionHealthResponse(
                        status="degraded",
                        server_url=server_url,
                        port=settings.REMOTION_SERVER_PORT,
                        enabled=True,
                        message=f"Server returned status {resp.status}",
                    )
    except Exception as e:
        return RemotionHealthResponse(
            status="unavailable",
            server_url=server_url,
            port=settings.REMOTION_SERVER_PORT,
            enabled=True,
            message=f"Cannot connect to Remotion server: {str(e)}",
        )


@router.get("/status", response_model=RemotionStatusResponse)
async def get_remotion_status():
    """Get complete Remotion status including config and active jobs."""
    # Check health
    health = await check_remotion_health()
    
    # Count active renders
    async with async_session() as session:
        result = await session.execute(
            select(RemotionRenderModel)
            .where(RemotionRenderModel.status.in_(["queued", "rendering"]))
        )
        active_jobs = len(result.scalars().all())
    
    return RemotionStatusResponse(
        health=health,
        config=RemotionConfigResponse(
            use_remotion=settings.USE_REMOTION,
            ai_layer_enabled=settings.REMOTION_ENABLE_AI_LAYER,
            threejs_enabled=settings.REMOTION_ENABLE_THREEJS,
            quality=settings.REMOTION_QUALITY,
            concurrency=settings.REMOTION_CONCURRENCY,
            server_port=settings.REMOTION_SERVER_PORT,
        ),
        active_jobs=active_jobs,
    )


# ─── Render Job Status Endpoints ──────────────────────────────────────────────

@router.get("/renders/{job_id}", response_model=list[RemotionRenderStatus])
async def get_job_renders(job_id: str):
    """Get all Remotion render jobs for a specific job."""
    async with async_session() as session:
        result = await session.execute(
            select(RemotionRenderModel)
            .where(RemotionRenderModel.job_id == job_id)
            .order_by(RemotionRenderModel.clip_rank)
        )
        renders = result.scalars().all()
        
        return [
            RemotionRenderStatus(
                job_id=r.job_id,
                clip_rank=r.clip_rank,
                render_job_id=r.render_job_id,
                status=r.status,
                progress=r.progress,
                current_frame=r.current_frame,
                total_frames=r.total_frames,
                output_path=r.output_path,
                error_message=r.error_message,
                render_time_seconds=r.render_time_seconds,
                created_at=r.created_at,
                started_at=r.started_at,
                completed_at=r.completed_at,
            )
            for r in renders
        ]


@router.get("/renders/{job_id}/{clip_rank}", response_model=RemotionRenderStatus)
async def get_clip_render_status(job_id: str, clip_rank: int):
    """Get Remotion render status for a specific clip."""
    async with async_session() as session:
        result = await session.execute(
            select(RemotionRenderModel)
            .where(RemotionRenderModel.job_id == job_id)
            .where(RemotionRenderModel.clip_rank == clip_rank)
        )
        render = result.scalar_one_or_none()
        
        if not render:
            raise HTTPException(
                status_code=404, 
                detail=f"No render found for job {job_id} clip {clip_rank}"
            )
        
        return RemotionRenderStatus(
            job_id=render.job_id,
            clip_rank=render.clip_rank,
            render_job_id=render.render_job_id,
            status=render.status,
            progress=render.progress,
            current_frame=render.current_frame,
            total_frames=render.total_frames,
            output_path=render.output_path,
            error_message=render.error_message,
            render_time_seconds=render.render_time_seconds,
            created_at=render.created_at,
            started_at=render.started_at,
            completed_at=render.completed_at,
        )


# ─── Config Endpoint ──────────────────────────────────────────────────────────

@router.get("/config", response_model=RemotionConfigResponse)
async def get_remotion_config():
    """Get current Remotion configuration."""
    return RemotionConfigResponse(
        use_remotion=settings.USE_REMOTION,
        ai_layer_enabled=settings.REMOTION_ENABLE_AI_LAYER,
        threejs_enabled=settings.REMOTION_ENABLE_THREEJS,
        quality=settings.REMOTION_QUALITY,
        concurrency=settings.REMOTION_CONCURRENCY,
        server_port=settings.REMOTION_SERVER_PORT,
    )
