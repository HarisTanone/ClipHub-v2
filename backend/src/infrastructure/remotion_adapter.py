"""Remotion HTTP client — bridges Python backend to Node.js Remotion server.

This adapter handles:
- Scene graph serialization and transmission
- Render progress tracking via polling
- Error handling and retry logic
- Server health monitoring
"""
import asyncio
import logging
import os
from typing import Optional

import aiohttp
from aiohttp import ClientError, ClientTimeout

from src.config import settings
from src.domain.interfaces_remotion import (
    IRemotionRenderer,
    RemotionRenderConfig,
    RemotionRenderProgress,
    RemotionRenderResult,
    RemotionRenderStatus,
)

logger = logging.getLogger(__name__)


class RemotionAdapter(IRemotionRenderer):
    """HTTP client for Remotion Node.js render server.
    
    Communicates with Remotion server via REST API:
    - POST /render — Start render job
    - GET /progress/:jobId/:clipRank — Get render progress
    - POST /cancel/:jobId/:clipRank — Cancel render
    - GET /health — Health check
    """
    
    def __init__(self):
        self.base_url = getattr(settings, 'REMOTION_SERVER_URL', f"http://localhost:{settings.REMOTION_SERVER_PORT}")
        self.timeout = ClientTimeout(total=300)  # 5 min timeout for render
        self._session: Optional[aiohttp.ClientSession] = None
        self._server_process: Optional[asyncio.subprocess.Process] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session
    
    async def render_clip(
        self,
        scene_graph: dict,
        creative_direction: dict,
        video_path: str,
        output_path: str,
        clip_rank: int,
        config: Optional[RemotionRenderConfig] = None,
        words: Optional[list] = None,
        hook_text: Optional[str] = None,
        hook_style: Optional[str] = None,
    ) -> RemotionRenderResult:
        """Render clip via Remotion server.
        
        Args:
            scene_graph: Scene graph dict from AI analysis
            creative_direction: Creative direction dict
            video_path: Local path to input video
            output_path: Local path for output render
            clip_rank: Clip number
            config: Render configuration
            words: Word-level timestamps from Whisper [{word, start, end}]
            hook_text: Hook text to display in first 3 seconds
            hook_style: Hook animation style (fade_scale, slide_up, glitch, typewriter)
        """
        import time

        if config is None:
            config = RemotionRenderConfig(
                concurrency=settings.REMOTION_CONCURRENCY,
                quality=settings.REMOTION_QUALITY,
                enable_threejs=settings.REMOTION_ENABLE_THREEJS,
                enable_ai_layer=settings.REMOTION_ENABLE_AI_LAYER,
            )
        
        # Calculate duration in frames from scene graph
        clip_duration = scene_graph.get("duration") or scene_graph.get("clip_duration", 30)
        fps = config.framerate
        duration_in_frames = int(clip_duration * fps)
        
        # Use directly passed words (from Whisper), fallback to scene_graph
        render_words = words or []
        if not render_words:
            for layer in scene_graph.get("layers", []):
                if layer.get("layer_id") == "L5_subtitle":
                    for event in layer.get("events", []):
                        content = event.get("content")
                        if isinstance(content, list):
                            render_words = content
                        break
        
        # Use directly passed hook text, fallback to scene_graph
        render_hook_text = hook_text or ""
        render_hook_animation = hook_style or "fade_scale"
        if not render_hook_text:
            for layer in scene_graph.get("layers", []):
                if layer.get("layer_id") == "L3_hook":
                    events = layer.get("events", [])
                    if events:
                        render_hook_text = events[0].get("content", "")
                        render_hook_animation = events[0].get("event_type", "fade_scale")
                    break
        
        # Validate hook animation
        valid_animations = ("fade_scale", "slide_up", "glitch", "typewriter")
        if render_hook_animation not in valid_animations:
            render_hook_animation = "fade_scale"

        # Choose composition based on style config
        hook_cfg = creative_direction.get("hook_style_config", {})
        template_mode = hook_cfg.get("template_mode", "custom")
        if template_mode == "tiktok":
            composition_id = "TikTokComposition"
        elif template_mode == "creative":
            composition_id = "CreativeComposition"
        else:
            composition_id = "ClipComposition"

        # Build Remotion render request
        payload = {
            "compositionId": composition_id,
            "outputPath": os.path.abspath(output_path),
            "props": {
                "sceneGraph": scene_graph,
                "creativeDirection": creative_direction,
                "videoPath": os.path.abspath(video_path) if video_path else "",
                "words": render_words,
                "hookText": render_hook_text,
                "hookAnimation": render_hook_animation,
                "enableThreeJS": config.enable_threejs,
                "enableAI": config.enable_ai_layer,
            },
            "durationInFrames": duration_in_frames,
            "fps": fps,
            "width": config.resolution[0],
            "height": config.resolution[1],
            "codec": config.codec,
            "quality": config.quality,
            "concurrency": config.concurrency,
        }
        
        logger.info(f"[Remotion] Render clip {clip_rank}: hook='{render_hook_text[:30]}...', words={len(render_words)}, threejs={config.enable_threejs}")
        
        start_time = time.time()
        
        try:
            session = await self._get_session()
            
            # Send render request (server returns synchronously when done)
            async with session.post(
                f"{self.base_url}/render",
                json=payload,
                timeout=ClientTimeout(total=600),  # 10 min for render
            ) as resp:
                result = await resp.json()
                
                if resp.status == 200 and result.get("success"):
                    render_time = result.get("renderTimeSeconds", time.time() - start_time)
                    file_size = 0
                    if os.path.exists(output_path):
                        file_size = os.path.getsize(output_path)
                    
                    return RemotionRenderResult(
                        success=True,
                        output_path=output_path,
                        render_time_seconds=render_time,
                        file_size_bytes=file_size,
                    )
                else:
                    error = result.get("error", f"HTTP {resp.status}")
                    logger.error(f"[Remotion] Render failed: {error}")
                    return RemotionRenderResult(
                        success=False,
                        error_message=error,
                    )
            
        except asyncio.TimeoutError:
            render_time = time.time() - start_time
            logger.error(f"[Remotion] Render timeout after {render_time:.1f}s")
            return RemotionRenderResult(
                success=False,
                error_message=f"Render timeout after {render_time:.1f}s",
            )
        except ClientError as e:
            logger.error(f"[Remotion] HTTP error: {e}")
            return RemotionRenderResult(
                success=False,
                error_message=f"HTTP error: {e}",
            )
        except Exception as e:
            logger.exception(f"[Remotion] Unexpected error: {e}")
            return RemotionRenderResult(
                success=False,
                error_message=f"Unexpected error: {e}",
            )
    
    async def _poll_render_progress(
        self,
        job_id: str,
        clip_rank: int,
        output_path: str,
        poll_interval: float = 2.0,
        max_wait_seconds: float = 600.0,
    ) -> RemotionRenderResult:
        """Poll server for render progress until completion or timeout."""
        start_time = asyncio.get_event_loop().time()
        session = await self._get_session()
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait_seconds:
                logger.error(f"[Remotion] Render timeout after {elapsed:.1f}s")
                return RemotionRenderResult(
                    success=False,
                    error_message=f"Render timeout after {elapsed:.1f}s",
                )
            
            try:
                async with session.get(f"{self.base_url}/progress/{job_id}/{clip_rank}") as resp:
                    if resp.status != 200:
                        logger.warning(f"[Remotion] Progress check failed: {resp.status}")
                        await asyncio.sleep(poll_interval)
                        continue
                    
                    data = await resp.json()
                    status = RemotionRenderStatus(data.get("status", "rendering"))
                    progress = data.get("progress", 0.0)
                    
                    logger.debug(f"[Remotion] Progress: {progress*100:.1f}%, status={status.value}")
                    
                    if status == RemotionRenderStatus.COMPLETED:
                        # Verify file exists
                        if os.path.exists(output_path):
                            file_size = os.path.getsize(output_path)
                            render_time = asyncio.get_event_loop().time() - start_time
                            logger.info(f"[Remotion] Render completed: {output_path} ({file_size} bytes, {render_time:.1f}s)")
                            return RemotionRenderResult(
                                success=True,
                                output_path=output_path,
                                render_time_seconds=render_time,
                                file_size_bytes=file_size,
                            )
                        else:
                            logger.error(f"[Remotion] Output file not found: {output_path}")
                            return RemotionRenderResult(
                                success=False,
                                error_message="Output file not found",
                            )
                    
                    elif status == RemotionRenderStatus.FAILED:
                        error = data.get("error_message", "Unknown error")
                        logger.error(f"[Remotion] Render failed: {error}")
                        return RemotionRenderResult(
                            success=False,
                            error_message=error,
                        )
                    
                    elif status == RemotionRenderStatus.CANCELLED:
                        logger.warning(f"[Remotion] Render cancelled")
                        return RemotionRenderResult(
                            success=False,
                            error_message="Render cancelled",
                        )
                    
                    # Still rendering, wait and poll again
                    await asyncio.sleep(poll_interval)
                    
            except ClientError as e:
                logger.warning(f"[Remotion] Progress check error: {e}")
                await asyncio.sleep(poll_interval)
    
    async def health_check(self) -> bool:
        """Check if Remotion server is healthy."""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/health") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("status") == "healthy"
                return False
        except Exception as e:
            logger.debug(f"[Remotion] Health check failed: {e}")
            return False
    
    async def get_render_progress(self, job_id: str, clip_rank: int) -> RemotionRenderProgress:
        """Get current render progress."""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/progress/{job_id}/{clip_rank}") as resp:
                if resp.status != 200:
                    return RemotionRenderProgress(
                        job_id=job_id,
                        clip_rank=clip_rank,
                        status=RemotionRenderStatus.FAILED,
                        progress=0.0,
                        current_frame=0,
                        total_frames=0,
                        error_message="Failed to get progress",
                    )
                
                data = await resp.json()
                return RemotionRenderProgress(
                    job_id=job_id,
                    clip_rank=clip_rank,
                    status=RemotionRenderStatus(data.get("status", "rendering")),
                    progress=data.get("progress", 0.0),
                    current_frame=data.get("current_frame", 0),
                    total_frames=data.get("total_frames", 0),
                    eta_seconds=data.get("eta_seconds"),
                    error_message=data.get("error_message"),
                )
        except Exception as e:
            logger.error(f"[Remotion] Get progress error: {e}")
            return RemotionRenderProgress(
                job_id=job_id,
                clip_rank=clip_rank,
                status=RemotionRenderStatus.FAILED,
                progress=0.0,
                current_frame=0,
                total_frames=0,
                error_message=str(e),
            )
    
    async def cancel_render(self, job_id: str, clip_rank: int) -> bool:
        """Cancel ongoing render."""
        try:
            session = await self._get_session()
            async with session.post(f"{self.base_url}/cancel/{job_id}/{clip_rank}") as resp:
                if resp.status == 200:
                    logger.info(f"[Remotion] Render cancelled: {job_id}/{clip_rank}")
                    return True
                return False
        except Exception as e:
            logger.error(f"[Remotion] Cancel error: {e}")
            return False
    
    async def start_server(self) -> bool:
        """Start Remotion server if not running.
        
        Spawns Node.js process for Remotion render server.
        """
        # Check if already running
        if await self.health_check():
            logger.info("[Remotion] Server already running")
            return True
        
        # Get project path
        project_path = settings.REMOTION_PROJECT_PATH
        if not os.path.isabs(project_path):
            # Make relative to backend directory
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            project_path = os.path.join(backend_dir, project_path)
        
        if not os.path.exists(project_path):
            logger.error(f"[Remotion] Project path not found: {project_path}")
            return False
        
        # Start server
        try:
            logger.info(f"[Remotion] Starting server at {project_path}")
            self._server_process = await asyncio.create_subprocess_exec(
                "npm", "start",
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            # Wait for server to be healthy
            for _ in range(30):  # 30 seconds max
                await asyncio.sleep(1)
                if await self.health_check():
                    logger.info("[Remotion] Server started successfully")
                    return True
            
            logger.error("[Remotion] Server failed to start within 30s")
            return False
            
        except Exception as e:
            logger.error(f"[Remotion] Failed to start server: {e}")
            return False
    
    async def stop_server(self) -> bool:
        """Stop Remotion server."""
        if self._server_process is None:
            return True
        
        try:
            self._server_process.terminate()
            await self._server_process.wait()
            self._server_process = None
            logger.info("[Remotion] Server stopped")
            return True
        except Exception as e:
            logger.error(f"[Remotion] Failed to stop server: {e}")
            return False
    
    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
