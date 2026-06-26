"""JobService — Pipeline orchestrator v0.4 (16 steps).

Pipeline Steps:
  1. Validate              — yt-dlp validate URL, extract duration
  2. Download              — Download full video
  3. YouTube Transcript    — Fetch captions (language priority)
  4. Gemini Analysis       — Clip candidates + hooks + broll_suggestions
  5. Prepare Clips         — Time padding, overlap detection
  6. Aspect Ratio Router   — Set YOLO/AutoCenter/AutoGrid flags
  7. Trim Clips            — FFmpeg stream copy + FFprobe validation
  8. YOLO Seg + Reframe    — Conditional (9:16 only), passthrough for 16:9
  9. Whisper               — Word-level transcription per clip
  10. Gemini Highlights    — Mark highlight words
  11. B-Roll Injection     — Render + insert motion typography cutaways
  12. Hook Rendering       — Browser Render Engine (v3) or legacy (v2)
  13. Subtitle Rendering   — FFmpeg drawtext word-by-word
  14. Encode               — Optional NVENC/H.264
  15. CDN Upload           — Optional S3-compatible upload
  16. Assemble JSON        — Final metadata, DB update, SSE notify
"""
import asyncio
import json
import logging
import os
import secrets
import time
from typing import Any, Optional, TYPE_CHECKING

from src.config import settings
from src.domain.entities import (
    BRollSuggestion, Clip, Job, JobStatus, PipelineFlags, Subtitle, Word,
)
from src.domain.interfaces import (
    IAspectRatioRouter,
    IAssetFetcher,
    IBRollInjector,
    IBrowserRenderEngine,
    IDownloader,
    IGeminiAnalyzer,
    IJobRepository,
    IRenderer,
    ISubtitleRenderer,
    IValidator,
    IWhisperLocal,
    IYoloReframeEngine,
)
from src.domain.interfaces_remotion import IRemotionRenderer
from src.infrastructure.step_timer import StepTimer

if TYPE_CHECKING:
    from src.infrastructure.cleanup_manager import CleanupManager
    from src.infrastructure.gemini_retry_handler import GeminiRetryHandler
    from src.infrastructure.gemini_rate_limiter import GeminiRateLimiter
    from src.infrastructure.resource_monitor import ResourceMonitor
    from src.infrastructure.ffprobe_validator import FFprobeValidator
    from src.infrastructure.overlap_detector import OverlapDetector
    from src.infrastructure.checkpoint_manager import CheckpointManager
    from src.infrastructure.sse_progress_emitter import SSEProgressEmitter
    from src.infrastructure.url_deduplicator import URLDeduplicator
    from src.infrastructure.nvenc_encoder import NVENCEncoder
    from src.infrastructure.cdn_uploader import CDNUploader
    from src.infrastructure.batch_highlight_processor import BatchHighlightProcessor

logger = logging.getLogger(__name__)

MAX_CONCURRENT_JOBS = settings.MAX_CONCURRENT_JOBS
_pipeline_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)


class JobService:
    """Pipeline orchestrator — 15 steps, v0.4 architecture (no transcript step)."""

    def __init__(
        self,
        job_repo: IJobRepository,
        downloader: IDownloader,
        gemini_analyzer: IGeminiAnalyzer,
        whisper_local: IWhisperLocal,
        renderer: IRenderer,
        validator: IValidator,
        # ─── v0.4 components ──────────────────────────────────────────
        aspect_ratio_router: Optional[IAspectRatioRouter] = None,
        browser_render_engine: Optional[IBrowserRenderEngine] = None,
        broll_injector: Optional[IBRollInjector] = None,
        subtitle_renderer: Optional[ISubtitleRenderer] = None,
        yolo_reframe_engine: Optional[IYoloReframeEngine] = None,
        # ─── Infrastructure (optional) ────────────────────────────────
        cleanup_manager: Optional["CleanupManager"] = None,
        gemini_retry_handler: Optional["GeminiRetryHandler"] = None,
        gemini_rate_limiter: Optional["GeminiRateLimiter"] = None,
        resource_monitor: Optional["ResourceMonitor"] = None,
        ffprobe_validator: Optional["FFprobeValidator"] = None,
        overlap_detector: Optional["OverlapDetector"] = None,
        checkpoint_manager: Optional["CheckpointManager"] = None,
        sse_emitter: Optional["SSEProgressEmitter"] = None,
        url_deduplicator: Optional["URLDeduplicator"] = None,
        nvenc_encoder: Optional["NVENCEncoder"] = None,
        cdn_uploader: Optional["CDNUploader"] = None,
        batch_highlight_processor: Optional["BatchHighlightProcessor"] = None,
        asset_fetcher: Optional[IAssetFetcher] = None,
        # ─── v3.0 Remotion integration ───────────────────────────────────────
        remotion_adapter: Optional["IRemotionRenderer"] = None,
    ):
        self._repo = job_repo
        self._downloader = downloader
        self._gemini = gemini_analyzer
        self._whisper = whisper_local
        self._renderer = renderer
        self._validator = validator

        # v0.4 components
        self._aspect_router = aspect_ratio_router
        self._browser_render = browser_render_engine
        self._broll_injector = broll_injector
        self._subtitle_renderer = subtitle_renderer
        self._yolo_reframe = yolo_reframe_engine

        # v3.0 Remotion integration
        self._remotion_adapter = remotion_adapter

        # Infrastructure
        self._cleanup = cleanup_manager
        self._retry_handler = gemini_retry_handler
        self._rate_limiter = gemini_rate_limiter
        self._resource_monitor = resource_monitor
        self._ffprobe = ffprobe_validator
        self._overlap_detector = overlap_detector
        self._checkpoint = checkpoint_manager
        self._sse = sse_emitter
        self._deduplicator = url_deduplicator
        self._nvenc = nvenc_encoder
        self._cdn = cdn_uploader
        self._batch_highlight = batch_highlight_processor
        self._asset_fetcher: Optional[IAssetFetcher] = asset_fetcher

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _generate_job_id(self) -> str:
        return f"job_{secrets.token_hex(6)}"

    def _calc_max_clips(self, duration: float) -> int:
        if duration < 180:
            n = 2
        elif duration < 600:
            n = 5
        elif duration < 1800:
            n = 8
        else:
            n = 10
        limit = settings.VIDEO_FINAL_RESULT
        if limit and limit > 0:
            n = min(n, limit)
        return n

    def _emit(self, job_id: str, step: int, name: str, event: str = "start", duration: float = 0):
        if not self._sse:
            return
        try:
            if event == "start":
                self._sse.emit_step_start(job_id, step, name)
            elif event == "complete":
                self._sse.emit_step_complete(job_id, step, name, duration)
            elif event == "done":
                self._sse.emit_job_done(job_id, name, duration, step)
        except Exception:
            pass

    async def _gemini_call(self, api_call) -> Any:
        async def _rate_limited():
            if self._rate_limiter:
                return await self._rate_limiter.execute(api_call)
            return await api_call()
        if self._retry_handler:
            return await self._retry_handler.execute_with_retry(_rate_limited)
        return await _rate_limited()

    # ─── Public API ───────────────────────────────────────────────────────────

    async def create_job(
        self,
        youtube_url: str,
        force_reprocess: bool = False,
        style_preset: str = "",
        target_aspect_ratio: str = "9:16",
        hook_engine: str = "v3",
        hook_style: str = "",
        broll_enabled: bool = False,
        autogrid_enabled: bool = False,
        # v3.0 Remotion fields
        use_remotion: Optional[bool] = None,
        ai_layer_enabled: Optional[bool] = None,
        threejs_enabled: Optional[bool] = None,
        remotion_quality: Optional[str] = None,
        # Custom style configs from frontend editor
        hook_style_config: Optional[dict] = None,
        subtitle_style_config: Optional[dict] = None,
        # Smart features (premium)
        smart_camera: Optional[bool] = None,
        smart_subtitle_position: Optional[bool] = None,
    ) -> tuple[Job, bool]:
        """Create job and start pipeline in background."""

        # URL deduplication
        if not force_reprocess and self._deduplicator:
            try:
                cached = await self._deduplicator.check_dedup(youtube_url)
                if cached:
                    existing = await self._repo.get_by_job_id(cached.job_id)
                    if existing:
                        return existing, True
            except Exception as e:
                logger.warning(f"URL dedup failed: {e}")

        existing = await self._repo.get_by_url_active(youtube_url)
        if existing:
            return existing, False

        job_id = self._generate_job_id()

        # Store style configs in clips_data for later use during render
        initial_clips_data = {}
        if hook_style_config:
            initial_clips_data["hook_style_config"] = hook_style_config
        if subtitle_style_config:
            initial_clips_data["subtitle_style_config"] = subtitle_style_config
        if smart_camera:
            initial_clips_data["smart_camera"] = True
        if smart_subtitle_position:
            initial_clips_data["smart_subtitle_position"] = True

        job = Job(
            job_id=job_id,
            youtube_url=youtube_url,
            style_preset=style_preset or settings.DEFAULT_STYLE_PRESET,
            target_aspect_ratio=target_aspect_ratio,
            hook_engine=hook_engine,
            hook_style=hook_style or (hook_style_config.get("animation", "") if hook_style_config else ""),
            broll_enabled=broll_enabled,
            autogrid_enabled=autogrid_enabled,
            # v3.0 Remotion fields - use settings default if not specified
            use_remotion=use_remotion if use_remotion is not None else settings.USE_REMOTION,
            ai_layer_enabled=ai_layer_enabled if ai_layer_enabled is not None else settings.REMOTION_ENABLE_AI_LAYER,
            threejs_enabled=threejs_enabled if threejs_enabled is not None else settings.REMOTION_ENABLE_THREEJS,
            remotion_quality=remotion_quality or settings.REMOTION_QUALITY,
            clips_data=initial_clips_data if initial_clips_data else None,
        )
        await self._repo.create(job)

        # Persist style configs immediately so they survive pipeline
        if initial_clips_data:
            await self._repo.update_clips_data(job.job_id, initial_clips_data)

        asyncio.create_task(self._run_guarded(job))
        return job, False

    async def get_job(self, job_id: str) -> Optional[Job]:
        return await self._repo.get_by_job_id(job_id)

    async def _run_guarded(self, job: Job) -> None:
        async with _pipeline_semaphore:
            await self._run_pipeline(job)

    # ─── Pipeline (16 Steps) ─────────────────────────────────────────────────

    async def _run_pipeline(self, job: Job) -> None:
        job_id = job.job_id
        url = job.youtube_url
        video_path = f"{settings.DOWNLOAD_DIR}/{job_id}.mp4"
        output_dir = f"{settings.OUTPUT_DIR}/{job_id}"
        os.makedirs(output_dir, exist_ok=True)

        # Re-read clips_data from DB to ensure style configs are available
        fresh_job = await self._repo.get_by_job_id(job_id)
        if fresh_job and fresh_job.clips_data:
            job.clips_data = fresh_job.clips_data
        pipeline_start = time.time()

        try:
            # Pre-job: resource check
            if self._resource_monitor:
                try:
                    self._resource_monitor.check_and_raise()
                except Exception as e:
                    await self._repo.update_status(job_id, JobStatus.FAILED, str(e)[:512])
                    return

            # ═══ Step 1: Validate ═══
            self._emit(job_id, 1, "validate", "start")
            await self._repo.update_status(job_id, JobStatus.VALIDATING)
            valid, error, duration = await self._downloader.validate_url(url)
            if not valid:
                await self._repo.update_status(job_id, JobStatus.FAILED, error)
                return
            self._emit(job_id, 1, "validate", "complete", time.time() - pipeline_start)

            # ═══ Step 2: Download ═══
            self._emit(job_id, 2, "download", "start")
            await self._repo.update_status(job_id, JobStatus.DOWNLOADING)
            await self._downloader.download_video(url, video_path)
            self._emit(job_id, 2, "download", "complete")

            # ═══ Step 3: Gemini Analysis (direct video URL — no transcript needed) ═══
            self._emit(job_id, 3, "gemini_analysis", "start")
            await self._repo.update_status(job_id, JobStatus.ANALYZING)
            max_clips = self._calc_max_clips(duration)
            gemini_result = await self._gemini_call(
                lambda: self._gemini.analyze(url, duration, max_clips)
            )
            if "clips" not in gemini_result or not gemini_result["clips"]:
                await self._repo.update_status(job_id, JobStatus.FAILED, "Gemini tidak menghasilkan clip candidates")
                return
            raw_clips = gemini_result["clips"]
            broll_suggestions_map = gemini_result.get("broll_suggestions", {})

            # Parse creative direction (v2.0 — unified visual identity)
            from src.domain.entities import CreativeDirection
            creative_dir_raw = gemini_result.get("creative_direction", {})
            creative_direction = CreativeDirection.from_dict(creative_dir_raw) if creative_dir_raw else CreativeDirection()
            logger.info(f"[{job_id}] Creative direction: mood={creative_direction.typography_mood}, energy={creative_direction.energy_level}, colors={creative_direction.primary_color}/{creative_direction.secondary_color}")
            self._emit(job_id, 3, "gemini_analysis", "complete")

            # ═══ Step 4: Prepare Clips ═══
            self._emit(job_id, 4, "prepare_clips", "start")
            await self._repo.update_status(job_id, JobStatus.PREPARING)
            clips = self._prepare_clips(raw_clips, duration, broll_suggestions_map)
            if self._overlap_detector and clips:
                try:
                    clips = self._overlap_detector.resolve_overlaps(clips)
                except Exception:
                    pass
            limit = settings.VIDEO_FINAL_RESULT
            if limit and limit > 0 and clips:
                clips = clips[:limit]
            if not clips:
                await self._repo.update_status(job_id, JobStatus.FAILED, "Tidak ada clip valid")
                return
            clips_count = len(clips)
            await self._repo.update_clips_count(job_id, clips_count, 0, 0)
            self._emit(job_id, 4, "prepare_clips", "complete")

            # ═══ Step 5: Aspect Ratio Router ═══
            self._emit(job_id, 5, "aspect_router", "start")
            await self._repo.update_status(job_id, JobStatus.ROUTING)
            if self._aspect_router:
                flags = self._aspect_router.route(job.target_aspect_ratio, job.autogrid_enabled)
            else:
                flags = PipelineFlags.for_portrait() if job.target_aspect_ratio == "9:16" else PipelineFlags.for_landscape()
            logger.info(f"[{job_id}] Pipeline flags: yolo={flags.yolo_enabled}, hook_mode={flags.hook_render_mode}")
            self._emit(job_id, 5, "aspect_router", "complete")

            # ═══ Step 6: Trim Clips ═══
            self._emit(job_id, 6, "trim", "start")
            await self._repo.update_status(job_id, JobStatus.TRIMMING)
            trim_results = await self._trim_all_clips(job_id, video_path, clips, output_dir)
            self._emit(job_id, 6, "trim", "complete")

            # ═══ Step 7: YOLO Seg + AutoCenter + AutoGrid (conditional) ═══
            self._emit(job_id, 7, "yolo_reframe", "start")
            await self._repo.update_status(job_id, JobStatus.SEGMENTING)
            reframe_data = {}
            if flags.yolo_enabled and self._yolo_reframe:
                for clip in clips:
                    if not trim_results.get(clip.rank):
                        continue
                    in_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                    out_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
                    try:
                        result = await self._yolo_reframe.process(
                            in_path, out_path, job.target_aspect_ratio, flags.autogrid_enabled
                        )
                        reframe_data[clip.rank] = result
                    except Exception as e:
                        logger.warning(f"[{job_id}] YOLO reframe failed clip {clip.rank}: {e}")
            else:
                logger.info(f"[{job_id}] Step 8 passthrough (yolo_enabled=False)")
            self._emit(job_id, 7, "yolo_reframe", "complete")

            # ═══ Step 7.5: Center-crop fallback for 9:16 (when YOLO unavailable) ═══
            if flags.yolo_enabled and not reframe_data and job.target_aspect_ratio == "9:16":
                import subprocess
                logger.info(f"[{job_id}] Applying center-crop fallback for 9:16")
                for clip in clips:
                    if not trim_results.get(clip.rank):
                        continue
                    in_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                    out_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
                    # Center crop to 9:16: crop center portion of 16:9, then scale to fill 1080x1920
                    crop_cmd = [
                        "ffmpeg", "-y", "-i", in_path,
                        "-vf", "crop=ih*9/16:ih,scale=1080:1920",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                        "-c:a", "copy",
                        "-movflags", "+faststart",
                        out_path,
                    ]
                    try:
                        result = await asyncio.to_thread(
                            subprocess.run, crop_cmd, capture_output=True, text=True, timeout=60
                        )
                        if result.returncode == 0 and os.path.exists(out_path):
                            reframe_data[clip.rank] = {"method": "center_crop_fallback"}
                            logger.info(f"[{job_id}] Center-crop fallback clip {clip.rank}")
                        else:
                            logger.warning(f"[{job_id}] Center-crop fallback failed: {result.stderr[-200:]}")
                    except Exception as e:
                        logger.warning(f"[{job_id}] Center-crop fallback error: {e}")

            # ═══ Step 8: Whisper (word-level) ═══
            self._emit(job_id, 8, "whisper", "start")
            await self._repo.update_status(job_id, JobStatus.WHISPER)
            clips_with_words = await self._whisper_all_clips(job_id, clips, output_dir, trim_results)
            self._emit(job_id, 8, "whisper", "complete")

            # ═══ Step 8.5: Prosody Analysis (detect silence gaps + energy peaks) ═══
            from src.infrastructure.prosody_analyzer import ProsodyAnalyzer
            prosody_analyzer = ProsodyAnalyzer()
            prosody_results = {}
            for clip in clips:
                if not trim_results.get(clip.rank):
                    continue
                clip_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                words = self._get_words_for_clip(clip, clips_with_words)
                try:
                    prosody = prosody_analyzer.analyze(clip_path, words)
                    prosody_results[clip.rank] = prosody
                except Exception as e:
                    logger.warning(f"[{job_id}] Prosody analysis clip {clip.rank} failed: {e}")

            # ═══ Step 8.6: Compose Scene Graphs (structured timeline per clip) ═══
            from src.domain.scene_graph import SceneGraphComposer, SceneGraphValidator
            from dataclasses import asdict
            composer = SceneGraphComposer()
            validator = SceneGraphValidator()
            scene_graphs = {}
            cd_dict = asdict(creative_direction) if creative_direction else {}
            for clip in clips:
                if not trim_results.get(clip.rank):
                    continue
                words = self._get_words_for_clip(clip, clips_with_words)
                broll_raw = [{"at_time": b.at_time, "keyword": b.keyword, "template": b.template, "duration": b.duration} for b in clip.broll_suggestions]
                prosody = prosody_results.get(clip.rank)
                sg = composer.compose(
                    clip_rank=clip.rank,
                    clip_duration=clip.end - clip.start,
                    hook_text=clip.hook,
                    words=words,
                    broll_suggestions=broll_raw,
                    prosody=prosody,
                    creative_direction=cd_dict,
                )
                issues = validator.validate(sg)
                if issues:
                    logger.warning(f"[{job_id}] Scene graph clip {clip.rank} issues: {issues[:3]}")
                scene_graphs[clip.rank] = sg
            logger.info(f"[{job_id}] Scene graphs composed: {len(scene_graphs)} clips")

            # ═══ Step 9: Gemini Highlights ═══
            self._emit(job_id, 9, "highlights", "start")
            await self._repo.update_status(job_id, JobStatus.HIGHLIGHTING)
            if self._batch_highlight:
                try:
                    await self._batch_highlight.process_batch(clips_with_words)
                except Exception as e:
                    logger.warning(f"[{job_id}] Highlight failed: {e}")
            self._emit(job_id, 9, "highlights", "complete")

            # ═══ Step 9.5: Asset Fetching (resolve B-roll to real visual assets) ═══
            if job.broll_enabled and self._asset_fetcher:
                self._emit(job_id, 10, "asset_fetch", "start")
                all_suggestions = []
                for clip in clips:
                    all_suggestions.extend(clip.broll_suggestions)
                if all_suggestions:
                    await self._asset_fetcher.fetch_assets(all_suggestions, creative_direction)
                    real_count = sum(1 for s in all_suggestions if s.asset_result and not s.asset_result.is_fallback)
                    logger.info(f"[{job_id}] Assets: {real_count} real, {len(all_suggestions) - real_count} fallback")
                self._emit(job_id, 10, "asset_fetch", "complete")

            # ═══ Step 9.6: AI Layer Generation (optional, uses Gemini Flash) ═══
            # Generate AI-enhanced layer events for Remotion rendering
            ai_layer_outputs = {}
            if settings.REMOTION_ENABLE_AI_LAYER:
                self._emit(job_id, 9.5, "ai_layer_gen", "start")
                from src.infrastructure.ai_layer_generator import get_ai_layer_generator
                ai_generator = get_ai_layer_generator()
                if ai_generator:
                    for clip in clips:
                        if not trim_results.get(clip.rank):
                            continue
                        words = self._get_words_for_clip(clip, clips_with_words)
                        prosody = prosody_results.get(clip.rank)
                        
                        # Build transcript from words
                        transcript = " ".join([w["word"] for w in words])
                        
                        try:
                            ai_output = await ai_generator.generate_layer_events(
                                clip_rank=clip.rank,
                                transcript=transcript,
                                words=[{"word": w["word"], "start": w["start"], "end": w["end"]} for w in words],
                                prosody=prosody.__dict__ if prosody else {},
                                creative_direction=creative_direction,
                            )
                            if ai_output:
                                ai_layer_outputs[clip.rank] = ai_output
                                logger.info(f"[{job_id}] AI layer generated {len(ai_output.events)} events for clip {clip.rank}")
                        except Exception as e:
                            logger.warning(f"[{job_id}] AI layer generation failed for clip {clip.rank}: {e}")
                self._emit(job_id, 9.5, "ai_layer_gen", "complete")

            # ═══ Step 10-12: Render Pipeline Router ═══
            # If USE_REMOTION=true and adapter available, use Remotion for all rendering
            # Otherwise, fall back to FFmpeg-based rendering (Step 10: Hook, Step 11: B-Roll, Step 12: Subtitle)
            
            use_remotion = False
            if settings.USE_REMOTION and self._remotion_adapter:
                # ═══ Remotion Path — Single unified render call ═══
                self._emit(job_id, 10, "remotion_render", "start")
                await self._repo.update_status(job_id, JobStatus.REMOTION_RENDERING)
                
                # Check Remotion server health
                if await self._remotion_adapter.health_check():
                    use_remotion = True
                    # Server healthy, proceed with Remotion render
                    for clip in clips:
                        if not trim_results.get(clip.rank):
                            continue
                        
                        scene_graph = scene_graphs.get(clip.rank)
                        if not scene_graph:
                            logger.warning(f"[{job_id}] No scene graph for clip {clip.rank}")
                            continue
                        
                        in_path = self._best_clip_path(output_dir, clip.rank, reframe_data)
                        out_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"
                        
                        # Get words and hook for this clip
                        clip_words = self._get_words_for_clip(clip, clips_with_words)
                        clip_hook = clip.hook or ""
                        
                        try:
                            from src.domain.interfaces_remotion import RemotionRenderConfig
                            render_config = RemotionRenderConfig(
                                concurrency=settings.REMOTION_CONCURRENCY,
                                quality=settings.REMOTION_QUALITY,
                                enable_threejs=settings.REMOTION_ENABLE_THREEJS,
                                enable_ai_layer=settings.REMOTION_ENABLE_AI_LAYER,
                            )
                            # Merge custom style configs into creative direction
                            cd_dict = asdict(creative_direction) if creative_direction else {}
                            if job.clips_data:
                                if job.clips_data.get("hook_style_config"):
                                    cd_dict["hook_style_config"] = job.clips_data["hook_style_config"]
                                if job.clips_data.get("subtitle_style_config"):
                                    cd_dict["subtitle_style_config"] = job.clips_data["subtitle_style_config"]
                            else:
                                # Try re-read from DB as last resort
                                _fresh = await self._repo.get_by_job_id(job_id)
                                if _fresh and _fresh.clips_data:
                                    if _fresh.clips_data.get("hook_style_config"):
                                        cd_dict["hook_style_config"] = _fresh.clips_data["hook_style_config"]
                                    if _fresh.clips_data.get("subtitle_style_config"):
                                        cd_dict["subtitle_style_config"] = _fresh.clips_data["subtitle_style_config"]
                                    job.clips_data = _fresh.clips_data
                            
                            result = await self._remotion_adapter.render_clip(
                                scene_graph=scene_graph.to_dict(),
                                creative_direction=cd_dict,
                                video_path=in_path,
                                output_path=out_path,
                                clip_rank=clip.rank,
                                config=render_config,
                                words=clip_words,
                                hook_text=clip_hook,
                                hook_style=job.hook_style or "fade_scale",
                            )
                            if result.success:
                                logger.info(f"[{job_id}] Remotion rendered clip {clip.rank} ({result.render_time_seconds:.1f}s)")
                            else:
                                logger.error(f"[{job_id}] Remotion render failed clip {clip.rank}: {result.error_message}")
                                # Copy base clip as fallback
                                if os.path.exists(in_path) and not os.path.exists(out_path):
                                    import shutil
                                    shutil.copy2(in_path, out_path)
                        except Exception as e:
                            logger.exception(f"[{job_id}] Remotion render error clip {clip.rank}: {e}")
                            # Fallback: copy base clip
                            if os.path.exists(in_path) and not os.path.exists(out_path):
                                import shutil
                                shutil.copy2(in_path, out_path)
                    
                    self._emit(job_id, 12, "remotion_render", "complete")
                else:
                    # Try to start server
                    logger.warning(f"[{job_id}] Remotion server not healthy, attempting to start...")
                    started = await self._remotion_adapter.start_server()
                    if started and await self._remotion_adapter.health_check():
                        use_remotion = True
                        # Server started, proceed with Remotion render
                        for clip in clips:
                            if not trim_results.get(clip.rank):
                                continue
                            
                            scene_graph = scene_graphs.get(clip.rank)
                            if not scene_graph:
                                logger.warning(f"[{job_id}] No scene graph for clip {clip.rank}")
                                continue
                            
                            in_path = self._best_clip_path(output_dir, clip.rank, reframe_data)
                            out_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"
                            
                            # Get words and hook for this clip
                            clip_words = self._get_words_for_clip(clip, clips_with_words)
                            clip_hook = clip.hook or ""
                            
                            try:
                                from src.domain.interfaces_remotion import RemotionRenderConfig
                                render_config = RemotionRenderConfig(
                                    concurrency=settings.REMOTION_CONCURRENCY,
                                    quality=settings.REMOTION_QUALITY,
                                    enable_threejs=settings.REMOTION_ENABLE_THREEJS,
                                    enable_ai_layer=settings.REMOTION_ENABLE_AI_LAYER,
                                )
                                # Merge custom style configs
                                cd_dict = asdict(creative_direction) if creative_direction else {}
                                if job.clips_data:
                                    if job.clips_data.get("hook_style_config"):
                                        cd_dict["hook_style_config"] = job.clips_data["hook_style_config"]
                                    if job.clips_data.get("subtitle_style_config"):
                                        cd_dict["subtitle_style_config"] = job.clips_data["subtitle_style_config"]
                                
                                result = await self._remotion_adapter.render_clip(
                                    scene_graph=scene_graph.to_dict(),
                                    creative_direction=cd_dict,
                                    video_path=in_path,
                                    output_path=out_path,
                                    clip_rank=clip.rank,
                                    config=render_config,
                                    words=clip_words,
                                    hook_text=clip_hook,
                                    hook_style=job.hook_style or "fade_scale",
                                )
                                if result.success:
                                    logger.info(f"[{job_id}] Remotion rendered clip {clip.rank} ({result.render_time_seconds:.1f}s)")
                                else:
                                    logger.error(f"[{job_id}] Remotion render failed clip {clip.rank}: {result.error_message}")
                                    if os.path.exists(in_path) and not os.path.exists(out_path):
                                        import shutil
                                        shutil.copy2(in_path, out_path)
                            except Exception as e:
                                logger.exception(f"[{job_id}] Remotion render error clip {clip.rank}: {e}")
                                if os.path.exists(in_path) and not os.path.exists(out_path):
                                    import shutil
                                    shutil.copy2(in_path, out_path)
                        
                        self._emit(job_id, 12, "remotion_render", "complete")
                    else:
                        logger.error(f"[{job_id}] Failed to start Remotion server, falling back to FFmpeg")
            
            if not use_remotion:
                # ═══ FFmpeg Path — Multi-step rendering (Hook → B-Roll → Subtitle) ═══
                
                # ═══ Step 10: Hook Rendering (burn hook text onto first 3s of clip) ═══
                self._emit(job_id, 10, "hook_render", "start")
                await self._repo.update_status(job_id, JobStatus.HOOK_RENDERING)
                for clip in clips:
                    if not trim_results.get(clip.rank):
                        continue
                    in_path = self._best_clip_path(output_dir, clip.rank, reframe_data)
                    out_path = f"{output_dir}/clip_{clip.rank:02d}_hooked.mp4"
                    try:
                        # Use per-clip hook_style override if set, else job-level hook_style
                        clip_style = None
                        if job.clips_data and "clips" in job.clips_data:
                            for cd in job.clips_data["clips"]:
                                if cd.get("rank") == clip.rank and cd.get("hook_style"):
                                    clip_style = cd["hook_style"]
                                    break
                        hook_style = clip_style or job.hook_style or settings.HOOK_DEFAULT_STYLE
                        await self._render_hook_ffmpeg(in_path, clip.hook, out_path, hook_style=hook_style)
                        logger.info(f"[{job_id}] Hook rendered clip {clip.rank} (style={hook_style})")
                    except Exception as e:
                        logger.warning(f"[{job_id}] Hook render failed clip {clip.rank}: {e}")
                self._emit(job_id, 10, "hook_render", "complete")

                # ═══ Step 11: B-Roll Overlay (motion typography on top of video) ═══
                # B-roll is OVERLAID on top of the video (not inserted).
                # Original audio continues uninterrupted. Timeline does NOT change.
                # Subtitles rendered AFTER this step will appear on top of b-roll too.
                self._emit(job_id, 11, "broll", "start")
                await self._repo.update_status(job_id, JobStatus.BROLL)
                if job.broll_enabled and self._broll_injector:
                    for clip in clips:
                        if not trim_results.get(clip.rank) or not clip.broll_suggestions:
                            continue
                        hooked_path = f"{output_dir}/clip_{clip.rank:02d}_hooked.mp4"
                        in_path = hooked_path if os.path.exists(hooked_path) else self._best_clip_path(output_dir, clip.rank, reframe_data)
                        out_path = f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4"
                        try:
                            result = await self._broll_injector.inject(in_path, clip.broll_suggestions, out_path)
                            if result != in_path:
                                logger.info(f"[{job_id}] B-roll overlaid clip {clip.rank}")
                        except Exception as e:
                            logger.warning(f"[{job_id}] B-roll overlay failed clip {clip.rank}: {e}")
                else:
                    logger.info(f"[{job_id}] Step 11 skipped (broll_enabled={job.broll_enabled})")
                self._emit(job_id, 11, "broll", "complete")

                # ═══ Step 12: Subtitle Rendering (word-by-word, rendered LAST) ═══
                # Subtitles are rendered on top of everything (hook + b-roll).
                # Since b-roll is overlay (no timeline change), whisper timestamps still match.
                self._emit(job_id, 12, "subtitle", "start")
                await self._repo.update_status(job_id, JobStatus.SUBTITLE_RENDERING)
                for clip in clips:
                    if not trim_results.get(clip.rank):
                        continue
                    words = self._get_words_for_clip(clip, clips_with_words)
                    # Use best available: brolled > hooked > reframed > raw
                    brolled_path = f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4"
                    hooked_path = f"{output_dir}/clip_{clip.rank:02d}_hooked.mp4"
                    in_path = brolled_path if os.path.exists(brolled_path) else (
                        hooked_path if os.path.exists(hooked_path) else
                        self._best_clip_path(output_dir, clip.rank, reframe_data)
                    )
                    out_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"
                    if words and self._subtitle_renderer:
                        try:
                            # Build style from creative direction
                            from src.domain.entities import SubtitleStyleConfig
                            sub_style = SubtitleStyleConfig(
                                color=creative_direction.primary_color,
                                highlight_color=creative_direction.secondary_color,
                                uppercase=creative_direction.subtitle_uppercase,
                                position=creative_direction.subtitle_position,
                            )
                            self._subtitle_renderer.render_subtitles(
                                video_path=in_path,
                                words=words,
                                style=sub_style,
                                output_path=out_path,
                                start_offset=0.0,
                            )
                            logger.info(f"[{job_id}] Subtitle rendered clip {clip.rank}")
                        except Exception as e:
                            logger.warning(f"[{job_id}] Subtitle render failed clip {clip.rank}: {e}")
                            if os.path.exists(in_path) and not os.path.exists(out_path):
                                import shutil
                                shutil.copy2(in_path, out_path)
                    else:
                        # No words / no renderer — copy best available as final
                        if os.path.exists(in_path) and not os.path.exists(out_path):
                            import shutil
                            shutil.copy2(in_path, out_path)
                self._emit(job_id, 12, "subtitle", "complete")

            # ═══ Step 13: Audio Post-Production (ducking + normalization) ═══
            self._emit(job_id, 13, "audio_mix", "start")
            await self._repo.update_status(job_id, JobStatus.ENCODING)
            from src.infrastructure.audio_mixer import AudioMixer, AudioMixConfig
            audio_mixer = AudioMixer()
            for clip in clips:
                if not trim_results.get(clip.rank):
                    continue
                final_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"
                if not os.path.exists(final_path):
                    continue
                mixed_path = f"{output_dir}/clip_{clip.rank:02d}_mixed.mp4"
                mix_cfg = AudioMixConfig(
                    music_mood=creative_direction.music_mood,
                    music_enabled=True,
                )
                result = audio_mixer.mix_audio(final_path, mixed_path, mix_cfg)
                if result == mixed_path and os.path.exists(mixed_path):
                    # Replace final with mixed version
                    os.replace(mixed_path, final_path)
                    logger.info(f"[{job_id}] Audio mixed clip {clip.rank}")
                else:
                    logger.info(f"[{job_id}] Audio mix skipped clip {clip.rank} (no music available)")
            self._emit(job_id, 13, "audio_mix", "complete")

            # ═══ Step 14: CDN Upload (optional) ═══
            self._emit(job_id, 14, "cdn_upload", "start")
            await self._repo.update_status(job_id, JobStatus.UPLOADING)
            if self._cdn:
                logger.info(f"[{job_id}] CDN upload step")
                # TODO: upload final clips to CDN
            self._emit(job_id, 14, "cdn_upload", "complete")

            # ═══ Step 14.5: Thumbnails + Folder Structure ═══
            self._emit(job_id, 14.5, "thumbnails", "start")
            import subprocess
            import shutil
            thumb_dir = f"{output_dir}/thumbnail"
            raw_dir = f"{output_dir}/raw"
            final_dir = f"{output_dir}/final"
            os.makedirs(thumb_dir, exist_ok=True)
            os.makedirs(raw_dir, exist_ok=True)
            os.makedirs(final_dir, exist_ok=True)

            for clip in clips:
                if not trim_results.get(clip.rank):
                    continue
                rank = clip.rank

                # Generate thumbnail from final video (seek to 1s)
                final_path = f"{output_dir}/clip_{rank:02d}_final.mp4"
                thumb_path = f"{thumb_dir}/clip_{rank:02d}.jpg"
                if os.path.exists(final_path):
                    thumb_cmd = [
                        "ffmpeg", "-y", "-i", final_path,
                        "-ss", "1", "-frames:v", "1",
                        "-vf", "scale=360:-1",
                        "-q:v", "3",
                        thumb_path,
                    ]
                    try:
                        await asyncio.to_thread(subprocess.run, thumb_cmd, capture_output=True, text=True, timeout=15)
                    except Exception:
                        pass

                # Move raw clip to raw/ folder
                raw_src = f"{output_dir}/clip_{rank:02d}.mp4"
                if os.path.exists(raw_src):
                    shutil.copy2(raw_src, f"{raw_dir}/clip_{rank:02d}.mp4")

                # Move final clip to final/ folder
                if os.path.exists(final_path):
                    shutil.copy2(final_path, f"{final_dir}/clip_{rank:02d}.mp4")

            # Generate meta JSON
            import json as json_mod
            meta = {
                "job_id": job_id,
                "youtube_url": job.youtube_url,
                "aspect_ratio": job.target_aspect_ratio,
                "clips_total": clips_count,
                "clips_success": sum(1 for c in clips if trim_results.get(c.rank)),
                "created_at": str(job.created_at) if job.created_at else None,
                "clips": [
                    {
                        "rank": c.rank,
                        "start": c.start,
                        "end": c.end,
                        "duration": c.end - c.start,
                        "hook": c.hook,
                        "score": c.score,
                        "words": self._get_words_for_clip(c, clips_with_words),
                    }
                    for c in clips
                ],
            }
            meta_path = f"{output_dir}/meta_{job_id}.json"
            with open(meta_path, "w") as f:
                json_mod.dump(meta, f, indent=2, default=str)

            self._emit(job_id, 14.5, "thumbnails", "complete")
            logger.info(f"[{job_id}] Thumbnails generated + folder structured")

            # ═══ Step 15: Assemble JSON (include scene_graphs) ═══
            self._emit(job_id, 15, "assemble", "start")
            await self._repo.update_status(job_id, JobStatus.ASSEMBLING)

            clips_data = self._assemble_clips_data(job, clips, clips_with_words, reframe_data, creative_direction)
            # Include scene graphs in output
            clips_data["scene_graphs"] = {
                str(rank): sg.to_dict() for rank, sg in scene_graphs.items()
            }
            # Preserve style configs from job creation
            if job.clips_data:
                if job.clips_data.get("hook_style_config"):
                    clips_data["hook_style_config"] = job.clips_data["hook_style_config"]
                if job.clips_data.get("subtitle_style_config"):
                    clips_data["subtitle_style_config"] = job.clips_data["subtitle_style_config"]
            await self._repo.update_clips_data(job_id, clips_data)

            success_count = sum(1 for c in clips if trim_results.get(c.rank))
            failed_count = clips_count - success_count
            await self._repo.update_clips_count(job_id, clips_count, success_count, failed_count)
            await self._repo.update_status(job_id, JobStatus.COMPLETED)

            total_duration = time.time() - pipeline_start
            self._emit(job_id, 15, "assemble", "complete", total_duration)
            self._emit(job_id, success_count, JobStatus.COMPLETED.value, "done", total_duration)
            logger.info(f"[{job_id}] Pipeline completed in {total_duration:.1f}s — {success_count}/{clips_count} clips")

        except Exception as e:
            logger.exception(f"[{job_id}] Pipeline failed: {e}")
            await self._repo.update_status(job_id, JobStatus.FAILED, str(e)[:512])
        finally:
            # Cleanup temp files
            if self._cleanup:
                try:
                    self._cleanup.cleanup_job_directory(output_dir)
                except Exception:
                    pass

    # ─── Pipeline Helpers ─────────────────────────────────────────────────────

    def _best_clip_path(self, output_dir: str, rank: int, reframe_data: dict) -> str:
        """Get best available clip path. Always verify file exists AND has content."""
        reframed_path = f"{output_dir}/clip_{rank:02d}_reframed.mp4"
        raw_path = f"{output_dir}/clip_{rank:02d}.mp4"
        if os.path.exists(reframed_path) and os.path.getsize(reframed_path) > 1000:
            return reframed_path
        return raw_path

    def _prepare_clips(self, raw_clips: list[dict], duration: float, broll_map: dict = None) -> list[Clip]:
        """Convert raw Gemini output to Clip entities with validation."""
        clips = []
        for i, rc in enumerate(raw_clips, 1):
            start = float(rc.get("start", 0))
            end = float(rc.get("end", 0))
            # Padding
            start = max(0, start - 0.5)
            end = min(duration, end + 1.0)
            if end - start < settings.MIN_CLIP_DURATION:
                continue

            # Parse broll suggestions for this clip
            broll_suggestions = []
            if broll_map and str(i) in broll_map:
                for bs in broll_map[str(i)]:
                    # Parse visual_category with safe fallback
                    try:
                        from src.domain.entities import VisualCategory
                        visual_category = VisualCategory(bs.get("visual_category", "footage"))
                    except (ValueError, KeyError):
                        from src.domain.entities import VisualCategory
                        visual_category = VisualCategory.FOOTAGE

                    broll_suggestions.append(BRollSuggestion(
                        at_time=float(bs.get("at_time", 0)),
                        keyword=bs.get("keyword", ""),
                        template=bs.get("template", "word_pop_typography"),
                        duration=float(bs.get("duration", 2.0)),
                        reason=bs.get("reason", ""),
                        visual_category=visual_category,
                    ))

            clips.append(Clip(
                rank=i,
                score=int(rc.get("score", 0)),
                start=start,
                end=end,
                hook=rc.get("hook", rc.get("hook_text", "")),
                reason=rc.get("reason", ""),
                broll_suggestions=broll_suggestions,
            ))
        return clips

    async def _render_hook_ffmpeg(self, video_path: str, hook_text: str, output_path: str, hook_style: str = "zoom_punch") -> None:
        """Burn hook text onto first 3 seconds of video using FFmpeg drawtext.

        Uses textfile= approach to avoid all text escaping issues.
        Renders with style-specific parameters for font, animation, and color.

        Supported hook_style values:
          - zoom_punch: Bold white text, quick scale-in (default)
          - fade_scale: Smooth fade + slight grow
          - slide_punch_framer: Slide from left with punch
          - typewriter: Character-by-character reveal
        """
        import subprocess
        import shutil

        if not hook_text or not hook_text.strip():
            shutil.copy2(video_path, output_path)
            return

        # ─── Style-specific parameters ─────────────────────────────────────
        HOOK_STYLES = {
            "zoom_punch": {
                "fontsize": 56, "fontcolor": "white", "borderw": 4,
                "bordercolor": "black", "duration": 3.0,
                "font_pref": ["Anton-Regular.ttf", "BebasNeue-Regular.ttf", "Poppins-Bold.ttf"],
                "bg_opacity": 0.6, "y_expr": "h*0.4-text_h/2",
            },
            "fade_scale": {
                "fontsize": 48, "fontcolor": "white", "borderw": 3,
                "bordercolor": "black@0.8", "duration": 3.5,
                "font_pref": ["Inter-Bold.ttf", "Poppins-Bold.ttf", "Montserrat-Bold.ttf"],
                "bg_opacity": 0.5, "y_expr": "h*0.42-text_h/2",
            },
            "slide_punch_framer": {
                "fontsize": 52, "fontcolor": "white", "borderw": 5,
                "bordercolor": "black", "duration": 3.0,
                "font_pref": ["Poppins-Bold.ttf", "Montserrat-Bold.ttf", "Inter-Bold.ttf"],
                "bg_opacity": 0.65, "y_expr": "h*0.38-text_h/2",
            },
            "typewriter": {
                "fontsize": 44, "fontcolor": "#00FF88", "borderw": 2,
                "bordercolor": "black", "duration": 3.5,
                "font_pref": ["Inter-Bold.ttf", "Poppins-Bold.ttf"],
                "bg_opacity": 0.7, "y_expr": "h*0.45-text_h/2",
            },
        }

        style = HOOK_STYLES.get(hook_style, HOOK_STYLES["zoom_punch"])
        duration = style["duration"]
        fontsize = style["fontsize"]
        fontcolor = style["fontcolor"]
        borderw = style["borderw"]
        bordercolor = style["bordercolor"]
        bg_opacity = style["bg_opacity"]
        y_expr = style["y_expr"]

        # Multi-line split if text is long (max ~6 words per line)
        words_list = hook_text.strip().split()
        if len(words_list) > 4:
            mid = len(words_list) // 2
            display_text = " ".join(words_list[:mid]) + "\n" + " ".join(words_list[mid:])
        else:
            display_text = hook_text.strip()

        # Sanitize text: replace unsupported Unicode characters
        display_text = self._sanitize_hook_text(display_text)

        # Write text to temp file — avoids all FFmpeg text escaping issues
        text_file = output_path.rsplit(".", 1)[0] + "_hook.txt"
        try:
            with open(text_file, "w", encoding="utf-8") as f:
                f.write(display_text)

            # Resolve font explicitly — use style-preferred fonts
            font_path = self._resolve_hook_font(style.get("font_pref"))
            font_opt = f":fontfile='{font_path}'" if font_path else ""

            # Alpha fade expression — escape commas to avoid filter parser confusion
            alpha_expr = (
                f"if(lt(t\\,0.5)\\,t/0.5\\,"
                f"if(gt(t\\,{duration - 0.5})\\,({duration}-t)/0.5\\,1))"
            )

            filter_complex = (
                f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{bg_opacity}:t=fill"
                f":enable='between(t,0,{duration})',"
                f"drawtext=textfile='{text_file}'"
                f":fontsize={fontsize}{font_opt}"
                f":fontcolor={fontcolor}:borderw={borderw}:bordercolor={bordercolor}"
                f":x=(w-text_w)/2:y={y_expr}"
                f":alpha='{alpha_expr}'"
                f":enable='between(t,0,{duration})'"
            )

            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-vf", filter_complex,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "copy",
                "-movflags", "+faststart",
                output_path,
            ]

            logger.debug(f"Hook cmd: {' '.join(cmd)}")
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=120
            )

            if result.returncode != 0:
                logger.error(f"Hook FFmpeg failed: {result.stderr[-300:]}")
                shutil.copy2(video_path, output_path)
            else:
                logger.info(f"Hook rendered: {os.path.basename(output_path)}")
        except Exception as e:
            logger.error(f"Hook render exception: {e}")
            shutil.copy2(video_path, output_path)
        finally:
            if os.path.exists(text_file):
                os.remove(text_file)

    @staticmethod
    def _sanitize_hook_text(text: str) -> str:
        """Remove or replace characters that can't be rendered by standard fonts.

        Handles: emoji, special Unicode symbols, zero-width chars, fancy quotes.
        """
        replacements = {
            '\u2018': "'", '\u2019': "'",  # smart quotes
            '\u201C': '"', '\u201D': '"',
            '\u2014': '-', '\u2013': '-',  # em/en dash
            '\u2026': '...',  # ellipsis
            '\u00A0': ' ',  # non-breaking space
            '\u200B': '', '\u200C': '', '\u200D': '',  # zero-width chars
            '\uFEFF': '',  # BOM
        }
        result = []
        for ch in text:
            if ch in replacements:
                result.append(replacements[ch])
            elif ch == '\n':
                result.append(ch)
            elif ord(ch) < 0x0080:  # ASCII
                result.append(ch)
            elif 0x0080 <= ord(ch) <= 0x024F:  # Latin Extended
                result.append(ch)
            elif 0x0400 <= ord(ch) <= 0x04FF:  # Cyrillic
                result.append(ch)
            elif ord(ch) > 0x2000 and ord(ch) < 0x206F:  # General punctuation
                result.append(ch)
            else:
                # Skip emoji and other unsupported chars
                result.append('')
        return "".join(result).strip()

    def _resolve_hook_font(self, preferred: list[str] = None) -> str:
        """Resolve font file path for hook text rendering."""
        font_dir = "assets/fonts"
        # Use preferred list if provided, else defaults (NotoSans as final fallback for Unicode)
        candidates = preferred or [
            "Poppins-Bold.ttf",
            "Montserrat-Bold.ttf",
            "Inter-Bold.ttf",
            "BebasNeue-Regular.ttf",
            "Anton-Regular.ttf",
        ]
        # Always add NotoSans as final fallback
        candidates.append("NotoSans-Variable.ttf")
        for name in candidates:
            path = os.path.join(font_dir, name)
            if os.path.exists(path):
                return os.path.abspath(path)
        # Try any .ttf file
        if os.path.isdir(font_dir):
            for f in os.listdir(font_dir):
                if f.endswith(".ttf"):
                    return os.path.abspath(os.path.join(font_dir, f))
        return ""

    async def _trim_all_clips(self, job_id: str, video_path: str, clips: list[Clip], output_dir: str) -> dict[int, bool]:
        """Trim all clips using FFmpeg."""
        results = {}
        for clip in clips:
            out_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
            try:
                success = await self._renderer.trim_clip(video_path, clip, out_path)
                results[clip.rank] = success and os.path.exists(out_path)
            except Exception as e:
                logger.warning(f"[{job_id}] Trim clip {clip.rank} failed: {e}")
                results[clip.rank] = False
        return results

    async def _whisper_all_clips(self, job_id: str, clips: list[Clip], output_dir: str, trim_results: dict) -> list[dict]:
        """Run Whisper on all successfully trimmed clips."""
        results = []
        for clip in clips:
            if not trim_results.get(clip.rank):
                results.append({"rank": clip.rank, "words": [], "_success": False})
                continue
            clip_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
            try:
                words = await self._whisper.transcribe_clip(clip_path)
                results.append({"rank": clip.rank, "words": words, "_success": True})
            except Exception as e:
                logger.warning(f"[{job_id}] Whisper clip {clip.rank} failed: {e}")
                results.append({"rank": clip.rank, "words": [], "_success": False})
        return results

    def _get_words_for_clip(self, clip: Clip, clips_with_words: list[dict]) -> list[dict]:
        """Get flat word list for a specific clip rank.

        Whisper returns segments [{start, end, text, words: [{word, start, end}]}].
        Subtitle renderer expects a flat list [{word, start, end}].
        This method flattens segments → words.
        """
        for cw in clips_with_words:
            if cw["rank"] == clip.rank and cw.get("_success"):
                segments = cw.get("words", [])
                if not segments:
                    return []
                # Check if already flat (word dicts have "word" key, segments have "text" key)
                if segments and "word" in segments[0]:
                    return segments  # Already flat
                # Flatten segments → words
                flat_words = []
                for seg in segments:
                    seg_words = seg.get("words", [])
                    flat_words.extend(seg_words)
                return flat_words
        return []

    def _assemble_clips_data(self, job: Job, clips: list[Clip], clips_with_words: list[dict], reframe_data: dict, creative_direction=None) -> dict:
        """Build final JSON output for the job."""
        assembled_clips = []
        for clip in clips:
            words = self._get_words_for_clip(clip, clips_with_words)
            assembled_clips.append({
                "rank": clip.rank,
                "score": clip.score,
                "start": clip.start,
                "end": clip.end,
                "hook": clip.hook,
                "reason": clip.reason,
                "duration": round(clip.end - clip.start, 2),
                "words": words,
                "broll_suggestions": [
                    {"at_time": b.at_time, "keyword": b.keyword, "template": b.template, "duration": b.duration}
                    for b in clip.broll_suggestions
                ],
                "reframe": reframe_data.get(clip.rank, {}),
            })

        # Serialize creative direction
        cd_dict = {}
        if creative_direction:
            from dataclasses import asdict
            cd_dict = asdict(creative_direction)

        return {
            "version": "2.0.0",
            "video_id": job.job_id,
            "aspect_ratio": job.target_aspect_ratio,
            "hook_engine": job.hook_engine,
            "broll_enabled": job.broll_enabled,
            "creative_direction": cd_dict,
            "clips": assembled_clips,
        }
