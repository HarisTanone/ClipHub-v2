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
from src.infrastructure.clip_outputs import initialize_clip_readiness, mark_clip_ready
from src.infrastructure.content_intelligence import ContentIntelligence
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

_active_job_tasks: dict[str, asyncio.Task] = {}


def register_active_job_task(job_id: str, task: asyncio.Task) -> None:
    _active_job_tasks[job_id] = task
    task.add_done_callback(lambda _: _active_job_tasks.pop(job_id, None))


def cancel_active_job_task(job_id: str) -> bool:
    task = _active_job_tasks.pop(job_id, None)
    if task and not task.done():
        task.cancel()
        return True
    return False


def is_job_active(job_id: str) -> bool:
    task = _active_job_tasks.get(job_id)
    return task is not None and not task.done()


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

    def _probe_local_duration(self, video_path: str) -> float:
        import subprocess
        import json
        try:
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
            if result.returncode == 0:
                data = json.loads(result.stdout or "{}")
                duration = float((data.get("format") or {}).get("duration") or 0)
                if duration > 0:
                    return duration
        except Exception:
            pass
        return 0.0

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
        broll_image_overlay: bool = True,
        broll_behind_person: bool = True,
        broll_video_footage: bool = True,
        broll_motion_style: Optional[str] = None,
        text_emphasis_enabled: bool = False,
        # v3.0 Remotion fields
        use_remotion: Optional[bool] = None,
        ai_layer_enabled: Optional[bool] = None,
        threejs_enabled: Optional[bool] = None,
        remotion_quality: Optional[str] = None,
        # Custom style configs from frontend editor
        hook_style_config: Optional[dict] = None,
        subtitle_style_config: Optional[dict] = None,
        text_emphasis_style_config: Optional[dict] = None,
        watermark_config: Optional[dict] = None,
        cta_config: Optional[dict] = None,
        # Canvas background (16:9 / 1:1 only)
        background_mode: Optional[str] = None,
        background_template_id: Optional[str] = None,
        background_image_data_url: Optional[str] = None,
        # AI Auto-Post options
        auto_post_social: bool = False,
        auto_post_platforms: str = "",
        auto_post_account_ids: Optional[list] = None,
        auto_post_schedule_mode: str = "ai",
        auto_post_custom_time: Optional[str] = None,
        # User ownership
        user_id: Optional[int] = None,
        # V2 pipeline routing
        is_superadmin: bool = False,
        # Local upload source
        source_type: str = "youtube",
        source_video_path: Optional[str] = None,
        source_filename: Optional[str] = None,
        source_duration: Optional[float] = None,
        source_size_bytes: Optional[int] = None,
        processing_mode: str = "analyze",
        custom_hook: Optional[str] = None,
        # User-adjusted clip timestamps from analyze-review
        custom_clips: Optional[list] = None,
        source_job_id: Optional[str] = None,
    ) -> tuple[Job, bool]:
        """Create job and start pipeline in background."""
        is_upload_source = source_type == "upload"
        if not is_upload_source:
            from src.infrastructure.downloader import get_canonical_youtube_url
            youtube_url = get_canonical_youtube_url(youtube_url) or str(youtube_url).strip()

        # ─── Determine pipeline version (V1 Gemini or V2 Groq) ────────
        from src.infrastructure.pipeline_router import PipelineRouter
        router = PipelineRouter()
        pipeline_version = router.get_pipeline_version(
            user_id=user_id or 0, is_superadmin=is_superadmin
        )
        if is_upload_source:
            pipeline_version = "v2"

        # URL deduplication
        if not is_upload_source and not force_reprocess and self._deduplicator:
            try:
                cached = await self._deduplicator.check_dedup(youtube_url)
                if cached:
                    existing = await self._repo.get_by_job_id(cached.job_id)
                    if existing:
                        return existing, True
            except Exception as e:
                logger.warning(f"URL dedup failed: {e}")

        existing = None if is_upload_source else await self._repo.get_by_url_active(youtube_url)
        if existing:
            return existing, False

        job_id = self._generate_job_id()

        # Resolve preset styles if style_preset is provided (by slug, ID, or name) or fallback to default
        resolved_preset = None
        try:
            from src.infrastructure.preset_resolver import resolve_preset
            resolved_preset = resolve_preset(style_preset, user_id=user_id)
            if resolved_preset:
                if not hook_style_config and resolved_preset.get("hook_style_config"):
                    hook_style_config = resolved_preset["hook_style_config"]
                if not subtitle_style_config and resolved_preset.get("subtitle_style_config"):
                    subtitle_style_config = resolved_preset["subtitle_style_config"]
                if not watermark_config and resolved_preset.get("watermark_config"):
                    watermark_config = resolved_preset["watermark_config"]
                if not cta_config and resolved_preset.get("cta_config"):
                    cta_config = resolved_preset["cta_config"]
                if not text_emphasis_style_config and resolved_preset.get("text_emphasis_style_config"):
                    text_emphasis_style_config = resolved_preset["text_emphasis_style_config"]
                    text_emphasis_enabled = text_emphasis_enabled or resolved_preset.get("text_emphasis_enabled", False)
                if not broll_motion_style and resolved_preset.get("broll_config"):
                    broll_cfg = resolved_preset.get("broll_config", {})
                    if isinstance(broll_cfg, dict):
                        broll_motion_style = broll_cfg.get("motion_style") or broll_motion_style
                broll_enabled = broll_enabled or resolved_preset.get("broll_enabled", False)
                broll_image_overlay = broll_image_overlay if broll_enabled else resolved_preset.get("broll_image_overlay", True)
                broll_behind_person = broll_behind_person if broll_enabled else resolved_preset.get("broll_behind_person", True)
                broll_video_footage = broll_video_footage if broll_enabled else resolved_preset.get("broll_video_footage", True)
                autogrid_enabled = autogrid_enabled or resolved_preset.get("autogrid_enabled", False)
                if not auto_post_social and resolved_preset.get("auto_post_social"):
                    auto_post_social = True
                    auto_post_platforms = auto_post_platforms or resolved_preset.get("auto_post_platforms", "")
                    auto_post_account_ids = auto_post_account_ids or resolved_preset.get("auto_post_account_ids", [])
                    auto_post_schedule_mode = auto_post_schedule_mode or resolved_preset.get("auto_post_schedule_mode", "ai")
                    auto_post_custom_time = auto_post_custom_time or resolved_preset.get("auto_post_custom_time")
        except Exception as e:
            logger.warning(f"Preset resolution failed for '{style_preset}': {e}")

        # Store style configs in clips_data for later use during render
        initial_clips_data = {}
        if force_reprocess:
            initial_clips_data["force_reprocess"] = True
        if resolved_preset:
            initial_clips_data["style_preset_slug"] = resolved_preset.get("slug")
            initial_clips_data["style_preset_name"] = resolved_preset.get("name")
            if resolved_preset.get("broll_config"):
                initial_clips_data["broll_style_config"] = resolved_preset["broll_config"]
        if hook_style_config:
            initial_clips_data["hook_style_config"] = hook_style_config
            if isinstance(hook_style_config, dict) and hook_style_config.get("engine"):
                initial_clips_data["hook_engine"] = hook_style_config["engine"]
            else:
                from src.infrastructure.hf_style_catalog import resolve_engine
                initial_clips_data["hook_engine"] = resolve_engine(hook_style_config)
        elif resolved_preset and resolved_preset.get("hook_engine"):
            initial_clips_data["hook_engine"] = resolved_preset["hook_engine"]

        if subtitle_style_config:
            initial_clips_data["subtitle_style_config"] = subtitle_style_config
            if isinstance(subtitle_style_config, dict) and subtitle_style_config.get("engine"):
                initial_clips_data["subtitle_engine"] = subtitle_style_config["engine"]
            else:
                from src.infrastructure.hf_style_catalog import resolve_engine
                initial_clips_data["subtitle_engine"] = resolve_engine(subtitle_style_config)
        elif resolved_preset and resolved_preset.get("subtitle_engine"):
            initial_clips_data["subtitle_engine"] = resolved_preset["subtitle_engine"]

        if watermark_config:
            initial_clips_data["watermark_config"] = watermark_config
        if cta_config:
            initial_clips_data["cta_config"] = cta_config
        # Persist explicit false as well, but activate if style config has active effect
        te_is_active = bool(
            text_emphasis_enabled
            or (
                text_emphasis_style_config
                and isinstance(text_emphasis_style_config, dict)
                and text_emphasis_style_config.get("enabled", True) is not False
                and (not text_emphasis_style_config.get("effectMode") or text_emphasis_style_config.get("effectMode") != "off")
            )
        )
        initial_clips_data["text_emphasis_enabled"] = te_is_active
        if text_emphasis_style_config:
            initial_clips_data["text_emphasis_style_config"] = text_emphasis_style_config
        # B-roll sub-types (explicit false must persist)
        initial_clips_data["broll_enabled"] = bool(broll_enabled)
        initial_clips_data["broll_image_overlay"] = bool(broll_image_overlay) if broll_enabled else False
        initial_clips_data["broll_behind_person"] = bool(broll_behind_person) if broll_enabled else False
        initial_clips_data["broll_video_footage"] = bool(broll_video_footage) if broll_enabled else False
        initial_clips_data["autogrid_enabled"] = bool(autogrid_enabled)
        # Background/template only for landscape/square; clear on 9:16
        if target_aspect_ratio in ("16:9", "1:1"):
            mode = background_mode or "template"
            initial_clips_data["background_mode"] = mode
            if mode == "template":
                initial_clips_data["background_template_id"] = background_template_id or "dark-studio"
            elif mode == "upload" and background_image_data_url:
                # Keep data URL in clips_data (job-scoped). Remotion receives it as image src.
                initial_clips_data["background_image_data_url"] = background_image_data_url
            from src.infrastructure.canvas_templates import build_canvas_config
            canvas = build_canvas_config(
                target_aspect_ratio,
                background_mode=initial_clips_data.get("background_mode"),
                background_template_id=initial_clips_data.get("background_template_id"),
                background_image_url=initial_clips_data.get("background_image_data_url"),
            )
            if canvas:
                initial_clips_data["canvas_config"] = canvas
        # AI Auto-Post configurations
        if auto_post_social:
            initial_clips_data["auto_post_social"] = True
            initial_clips_data["auto_post_platforms"] = auto_post_platforms
            initial_clips_data["auto_post_account_ids"] = auto_post_account_ids or []
            initial_clips_data["auto_post_schedule_mode"] = auto_post_schedule_mode
            initial_clips_data["auto_post_custom_time"] = auto_post_custom_time

        if is_upload_source:
            initial_clips_data["source"] = {
                "type": "upload",
                "path": source_video_path,
                "filename": source_filename or os.path.basename(source_video_path or "uploaded_video.mp4"),
                "duration": source_duration,
                "size_bytes": source_size_bytes,
            }
            initial_clips_data["source_type"] = "upload"
            initial_clips_data["processing_mode"] = processing_mode
            normalized_custom_hook = str(custom_hook or "").strip()
            if processing_mode == "direct" and normalized_custom_hook:
                initial_clips_data["custom_hook"] = normalized_custom_hook

        # User-adjusted clip timestamps from analyze-review step
        if custom_clips:
            initial_clips_data["custom_clips"] = custom_clips
        if source_job_id:
            initial_clips_data["source_job_id"] = source_job_id

        final_style_preset = (
            resolved_preset.get("slug")
            if resolved_preset
            else (style_preset or settings.DEFAULT_STYLE_PRESET)
        )

        job = Job(
            job_id=job_id,
            youtube_url=youtube_url,
            video_duration=source_duration if is_upload_source else None,
            style_preset=final_style_preset,
            target_aspect_ratio=target_aspect_ratio,
            hook_engine=hook_engine,
            hook_style=hook_style or (hook_style_config.get("animation", "") if hook_style_config else ""),
            broll_enabled=broll_enabled,
            # Computer-vision framing features are portrait-only. Enforce this
            # server-side as API clients must not be able to bypass the UI lock.
            autogrid_enabled=autogrid_enabled and target_aspect_ratio == "9:16",
            broll_image_overlay=bool(broll_image_overlay) if broll_enabled else False,
            broll_behind_person=bool(broll_behind_person) if broll_enabled else False,
            broll_video_footage=bool(broll_video_footage) if broll_enabled else False,
            broll_motion_style=broll_motion_style or None,
            # v3.0 Remotion fields - use settings default if not specified
            use_remotion=use_remotion if use_remotion is not None else settings.USE_REMOTION,
            ai_layer_enabled=ai_layer_enabled if ai_layer_enabled is not None else settings.REMOTION_ENABLE_AI_LAYER,
            threejs_enabled=threejs_enabled if threejs_enabled is not None else settings.REMOTION_ENABLE_THREEJS,
            remotion_quality=remotion_quality or settings.REMOTION_QUALITY,
            clips_data=initial_clips_data if initial_clips_data else None,
            user_id=user_id,
            pipeline_version=pipeline_version,
        )
        await self._repo.create(job)

        # Persist style configs immediately so they survive pipeline
        if initial_clips_data:
            await self._repo.update_clips_data(job.job_id, initial_clips_data)

        # ─── Route to appropriate pipeline ────────────────────────────
        if pipeline_version == "v2":
            task = asyncio.create_task(self._run_v2_guarded(job))
        else:
            task = asyncio.create_task(self._run_guarded(job))
        register_active_job_task(job.job_id, task)
        return job, False

    async def get_job(self, job_id: str) -> Optional[Job]:
        return await self._repo.get_by_job_id(job_id)

    async def _run_guarded(self, job: Job) -> None:
        async with _pipeline_semaphore:
            await self._run_pipeline(job)

    async def _run_v2_guarded(self, job: Job) -> None:
        """Run V2 pipeline with semaphore protection."""
        async with _pipeline_semaphore:
            from src.application.services_v2 import V2PipelineService
            from src.presentation.dependencies import get_v2_pipeline_service
            v2_service = get_v2_pipeline_service()
            await v2_service.run_pipeline(job)

    # ─── Pipeline (16 Steps) ─────────────────────────────────────────────────

    async def _run_pipeline(self, job: Job) -> None:
        job_id = job.job_id
        url = job.youtube_url
        video_path = f"{settings.DOWNLOAD_DIR}/{job_id}.mp4"
        output_dir = f"{settings.OUTPUT_DIR}/{job_id}"
        os.makedirs(output_dir, exist_ok=True)
        video_title = ""

        # Re-read clips_data from DB to ensure style configs are available
        fresh_job = await self._repo.get_by_job_id(job_id)
        if fresh_job and fresh_job.clips_data:
            job.clips_data = fresh_job.clips_data
        pipeline_start = time.time()

        # ─── Cache setup ──────────────────────────────────────────────
        from src.infrastructure.cache_manager import CacheManager
        cache = CacheManager()
        video_id = cache.extract_video_id(url)
        force_reprocess = bool(job.clips_data and job.clips_data.get("force_reprocess"))
        if force_reprocess and video_id:
            cache.invalidate(video_id)

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
            valid, error_or_title, duration = await self._downloader.validate_url(url)
            if not valid:
                await self._repo.update_status(job_id, JobStatus.FAILED, error_or_title)
                return
            video_title = error_or_title or ""
            # Save video title
            if error_or_title and valid:
                try:
                    await self._repo.update_video_title(job_id, error_or_title)
                except Exception:
                    pass
            self._emit(job_id, 1, "validate", "complete", time.time() - pipeline_start)

            # ═══ Step 2: Download (SKIP if cached or from analyze session) ═══
            source_job_id = (job.clips_data or {}).get("source_job_id")
            source_video_path = os.path.join(settings.DOWNLOAD_DIR, f"{source_job_id}.mp4") if source_job_id else None
            cached_video = cache.get_video_path(video_id) if video_id else None

            if source_video_path and os.path.exists(source_video_path):
                import shutil
                if not os.path.exists(video_path):
                    try:
                        os.link(source_video_path, video_path)
                    except OSError:
                        shutil.copy2(source_video_path, video_path)
                if video_id and not cache.get_video_path(video_id):
                    cache.save_video(video_id, video_path)
                logger.info(f"[{job_id}] Download SKIPPED (reused from analyze session: {source_job_id})")
                self._emit(job_id, 2, "download", "complete")
            elif cached_video:
                import shutil
                if not os.path.exists(video_path):
                    try:
                        os.link(cached_video, video_path)
                    except OSError:
                        shutil.copy2(cached_video, video_path)
                logger.info(f"[{job_id}] Download SKIPPED (cached: {video_id})")
                self._emit(job_id, 2, "download", "complete")
            else:
                self._emit(job_id, 2, "download", "start")
                await self._repo.update_status(job_id, JobStatus.DOWNLOADING)
                await self._downloader.download_video(url, video_path)
                if video_id and os.path.exists(video_path):
                    cache.save_video(video_id, video_path)
                self._emit(job_id, 2, "download", "complete")

            # Calibrate duration to actual downloaded video file
            if os.path.exists(video_path):
                probed_duration = self._probe_local_duration(video_path)
                if probed_duration > 0:
                    duration = probed_duration
                    job.video_duration = duration
                    logger.info(f"[{job_id}] Video duration calibrated via ffprobe: {duration:.1f}s")

            # ═══ Step 3: Gemini Analysis (SKIP if custom_clips or cached) ═══
            user_custom_clips = (job.clips_data or {}).get("custom_clips")
            if user_custom_clips:
                # User reviewed/edited clips in the preview step — use them directly!
                gemini_result = {"clips": user_custom_clips}
                logger.info(f"[{job_id}] Gemini analysis SKIPPED (using {len(user_custom_clips)} custom clips from preview)")
                self._emit(job_id, 3, "gemini_analysis", "complete")
            elif cached_analysis := (cache.load_analysis(video_id, "v1") if video_id else None):
                gemini_result = cached_analysis
                logger.info(f"[{job_id}] Gemini analysis SKIPPED (cached: {len(gemini_result.get('clips', []))} clips)")
                self._emit(job_id, 3, "gemini_analysis", "complete")
            else:
                self._emit(job_id, 3, "gemini_analysis", "start")
                await self._repo.update_status(job_id, JobStatus.ANALYZING)
                max_clips = self._calc_max_clips(duration)
                gemini_result = None

                # Primary: Ultra-Fast Groq Whisper + LLM HighlightAnalyzer
                try:
                    logger.info(f"[{job_id}] Analyzing highlights with Groq Whisper + LLM...")
                    from src.infrastructure.local_transcriber import LocalTranscriber
                    from src.infrastructure.highlight_analyzer import HighlightAnalyzer
                    transcriber = LocalTranscriber(self._whisper)
                    transcript_result, _ = await transcriber.transcribe(video_path, duration)
                    if transcript_result and transcript_result.segments:
                        analyzer = HighlightAnalyzer()
                        highlight_result = await analyzer.analyze_highlights(
                            transcript_result, duration, max_clips=max_clips or 8
                        )
                        if highlight_result and highlight_result.clips:
                            clips_data = [
                                {
                                    "rank": c.rank,
                                    "start": c.start,
                                    "end": c.end,
                                    "score": c.score,
                                    "hook": c.hook,
                                    "reason": c.reason,
                                    "content_type": c.content_type,
                                    "speaker_energy": c.speaker_energy,
                                }
                                for c in highlight_result.clips
                            ]
                            clips_data.sort(key=lambda x: float(x.get("start", 0)))
                            for idx, c in enumerate(clips_data, start=1):
                                c["rank"] = idx

                            gemini_result = {
                                "clips": clips_data,
                                "creative_direction": {
                                    "primary_color": "#FFCC00",
                                    "secondary_color": "#FF3366",
                                    "background_accent": "#111827",
                                    "typography_mood": "bold_impact",
                                    "energy_level": "high",
                                    "transition_style": "fast_cuts",
                                    "music_mood": "energetic",
                                    "hook_animation": "fade_scale",
                                },
                            }
                            logger.info(f"[{job_id}] Groq Whisper + LLM analysis SUCCESS: {len(clips_data)} clips")
                except Exception as e:
                    logger.warning(f"[{job_id}] Groq Whisper analysis error ({e}). Trying Gemini Multimodal fallback...")

                # Fallback: Gemini Multimodal
                if not gemini_result or "clips" not in gemini_result or not gemini_result["clips"]:
                    try:
                        gemini_result = await self._gemini_call(
                            lambda: self._gemini.analyze(url, duration, max_clips)
                        )
                    except Exception as gemini_err:
                        logger.error(f"[{job_id}] Gemini fallback failed: {gemini_err}")

                # Save to cache
                if video_id and gemini_result and "clips" in gemini_result:
                    cache.save_analysis(video_id, gemini_result, version="v1")
                self._emit(job_id, 3, "gemini_analysis", "complete")

            if not gemini_result or "clips" not in gemini_result or not gemini_result["clips"]:
                await self._repo.update_status(job_id, JobStatus.FAILED, "Analisis AI gagal menghasilkan klip kandidat")
                return
            raw_clips = gemini_result["clips"]
            broll_suggestions_map = gemini_result.get("broll_suggestions", {})

            # Parse creative direction (v2.0 — unified visual identity)
            from src.domain.entities import CreativeDirection
            creative_dir_raw = gemini_result.get("creative_direction", {})
            creative_direction = CreativeDirection.from_dict(creative_dir_raw) if creative_dir_raw else CreativeDirection()
            logger.info(f"[{job_id}] Creative direction: mood={creative_direction.typography_mood}, energy={creative_direction.energy_level}, colors={creative_direction.primary_color}/{creative_direction.secondary_color}")
            self._emit(job_id, 3, "gemini_analysis", "complete")

            content_text = " ".join(
                " ".join(
                    str(clip.get(key, ""))
                    for key in ("content_type", "hook", "reason", "speaker_energy")
                )
                for clip in raw_clips
                if isinstance(clip, dict)
            )
            content_profile = ContentIntelligence().detect(
                metadata={"title": video_title, "url": url},
                transcript_text=content_text,
                clip_hints=raw_clips,
                autogrid_enabled=job.autogrid_enabled,
            )
            merged_clips_data = dict(job.clips_data or {})
            merged_clips_data["content_profile"] = content_profile.to_dict()
            job.clips_data = merged_clips_data
            await self._repo.update_clips_data(job_id, merged_clips_data)
            logger.info(
                f"[{job_id}] Content profile: type={content_profile.content_type}, "
                f"confidence={content_profile.confidence}, grid={content_profile.grid_strategy}"
            )

            # ═══ Step 4: Prepare Clips ═══
            self._emit(job_id, 4, "prepare_clips", "start")
            await self._repo.update_status(job_id, JobStatus.PREPARING)
            clips = self._prepare_clips(raw_clips, duration, broll_suggestions_map)
            if not user_custom_clips and self._overlap_detector and clips:
                try:
                    clips = self._overlap_detector.resolve_overlaps(clips)
                except Exception:
                    pass
            limit = settings.VIDEO_FINAL_RESULT
            if not user_custom_clips and limit and limit > 0 and clips:
                clips = clips[:limit]
            if not clips:
                await self._repo.update_status(job_id, JobStatus.FAILED, "Tidak ada clip valid")
                return
            clips_count = len(clips)
            await self._repo.update_clips_count(job_id, clips_count, 0, 0)
            self._emit(job_id, 4, "prepare_clips", "complete")

            # ═══ Step 4.5: Hook Optimizer (AI rewrite for viral hooks) ═══
            if not user_custom_clips:
                try:
                    from src.infrastructure.hook_optimizer import HookOptimizer
                    optimizer = HookOptimizer()
                    optimized = optimizer.optimize_hooks(clips)
                    if optimized:
                        for clip in clips:
                            if clip.rank in optimized:
                                original = clip.hook
                                clip.hook = optimized[clip.rank]
                                logger.info(f"[{job_id}] Hook optimized clip {clip.rank}: '{original}' → '{clip.hook}'")
                        logger.info(f"[{job_id}] Hook optimizer: {len(optimized)}/{clips_count} hooks rewritten")
                except Exception as e:
                    logger.warning(f"[{job_id}] Hook optimizer failed (non-critical): {e}")

            # Persist the AI recommendations before any rendering starts. This
            # lets the job page show all clip slots immediately as processing.
            pending_clips_data = self._assemble_clips_data(
                job, clips, [], {}, creative_direction
            )
            merged_clips_data = dict(job.clips_data or {})
            merged_clips_data.update(pending_clips_data)
            job.clips_data = merged_clips_data
            await self._repo.update_clips_data(job_id, merged_clips_data)

            # ═══ Step 5: Aspect Ratio Router ═══
            self._emit(job_id, 5, "aspect_router", "start")
            await self._repo.update_status(job_id, JobStatus.ROUTING)
            if self._aspect_router:
                flags = self._aspect_router.route(job.target_aspect_ratio, job.autogrid_enabled)
            else:
                flags = PipelineFlags.for_portrait() if job.target_aspect_ratio == "9:16" else PipelineFlags.for_landscape()
            logger.info(f"[{job_id}] Pipeline flags: yolo={flags.yolo_enabled}, hook_mode={flags.hook_render_mode}")
            self._emit(job_id, 5, "aspect_router", "complete")

            # ═══ Step 6: VAD Boundary Adjustment + Trim Clips ═══
            self._emit(job_id, 6, "trim", "start")
            await self._repo.update_status(job_id, JobStatus.TRIMMING)

            # VAD: snap clip boundaries to nearest silence (prevents cutting mid-speech)
            if settings.VAD_ENABLED:
                try:
                    from src.infrastructure.vad_boundary_adjuster import VADBoundaryAdjuster
                    vad = VADBoundaryAdjuster()
                    for clip in clips:
                        adj_start, adj_end = await vad.adjust_clip_boundaries(
                            video_path, clip.start, clip.end
                        )
                        if adj_start != clip.start or adj_end != clip.end:
                            clip.start = adj_start
                            clip.end = adj_end
                    logger.info(f"[{job_id}] VAD boundary adjustment applied to {len(clips)} clips")
                except Exception as e:
                    logger.warning(f"[{job_id}] VAD adjustment failed (non-critical): {e}")

            trim_results = await self._trim_all_clips(job_id, video_path, clips, output_dir)
            self._emit(job_id, 6, "trim", "complete")

            # ═══ Step 7: YOLO Seg + AutoCenter + AutoGrid (conditional) ═══
            self._emit(job_id, 7, "yolo_reframe", "start")
            await self._repo.update_status(job_id, JobStatus.SEGMENTING)
            reframe_data = {}
            if flags.yolo_enabled and self._yolo_reframe:
                cd_data = job.clips_data or {}
                hook_style_cfg = cd_data.get("hook_style_config", {})
                reframe_cfg = cd_data.get("reframe_style", {}) or cd_data.get("reframe_config", {})
                broll_cfg = cd_data.get("broll_style_config", {}) or cd_data.get("broll_config", {})
                resolved_transition_style = (
                    cd_data.get("transition_style")
                    or cd_data.get("transitionStyle")
                    or reframe_cfg.get("transition_style")
                    or reframe_cfg.get("transitionStyle")
                    or hook_style_cfg.get("transitionStyle")
                    or hook_style_cfg.get("transition_style")
                    or broll_cfg.get("transition_style")
                    or broll_cfg.get("transitionStyle")
                    or "slide"
                )
                resolved_transition_duration = float(
                    cd_data.get("transition_duration")
                    or cd_data.get("transitionDuration")
                    or reframe_cfg.get("transition_duration")
                    or reframe_cfg.get("transitionDuration")
                    or hook_style_cfg.get("transitionDuration")
                    or hook_style_cfg.get("transition_duration")
                    or 0.35
                )
                for clip in clips:
                    if not trim_results.get(clip.rank):
                        continue
                    in_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                    out_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
                    try:
                        result = await self._yolo_reframe.process(
                            in_path,
                            out_path,
                            job.target_aspect_ratio,
                            flags.autogrid_enabled,
                            content_profile=(job.clips_data or {}).get("content_profile", {}),
                            transition_style=resolved_transition_style,
                            transition_duration=resolved_transition_duration,
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
                    from src.infrastructure.gpu_encoder import get_video_encoder_args
                    crop_cmd = [
                        "ffmpeg", "-y", "-i", in_path,
                        "-vf", "crop=ih*9/16:ih,scale=1080:1920:flags=lanczos+accurate_rnd+full_chroma_int+full_chroma_inp,unsharp=lx=3:ly=3:la=0.5:cx=3:cy=3:ca=0.25,format=yuv420p,setsar=1",
                        *get_video_encoder_args("medium"),
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

            # ═══ Steps 10-12: Engine Router — Remotion / FFmpeg ═══
            # Three rendering engines:
            #   1. Remotion   — All-in-one hook+subtitle via browser render (default, best quality)
            #   2. FFmpeg     — Lightweight server-side drawtext (no browser needed)
            #   3. HyperFrames — AI-powered lower-third polish layer (additive, runs after others)
            #
            # Engine selection priority:
            #   a) If job.hook_engine == "ffmpeg" → use FFmpeg path explicitly
            #   b) If Remotion adapter available → use Remotion path
            #   c) Else → fall back to FFmpeg path
            #
            # Note: HyperFrames is always additive if enabled (runs after main render)

            initialize_clip_readiness(output_dir)
            render_engine = self._select_render_engine(job)

            if render_engine == "ffmpeg":
                await self._run_ffmpeg_render_path(
                    job_id=job_id,
                    job=job,
                    clips=clips,
                    output_dir=output_dir,
                    reframe_data=reframe_data,
                    trim_results=trim_results,
                    clips_with_words=clips_with_words,
                    creative_direction=creative_direction,
                )
            else:
                # Remotion render path (default)
                await self._run_remotion_render_path(
                    job_id=job_id,
                    job=job,
                    clips=clips,
                    output_dir=output_dir,
                    reframe_data=reframe_data,
                    trim_results=trim_results,
                    clips_with_words=clips_with_words,
                    scene_graphs=scene_graphs,
                    prosody_results=prosody_results,
                    creative_direction=creative_direction,
                )

            # ═══ Step 13: Audio Post-Production (ducking + normalization) ═══
            # Common to both engine paths — runs on whatever produced _final.mp4
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

                # Generate thumbnail from final video (capturing hook moment)
                final_path = f"{output_dir}/clip_{rank:02d}_final.mp4"
                thumb_path = f"{thumb_dir}/clip_{rank:02d}.jpg"
                if os.path.exists(final_path):
                    from src.infrastructure.clip_quality_helpers import (
                        generate_smart_thumbnail,
                        smart_thumbnail_seek,
                    )
                    words = self._get_words_for_clip(clip, clips_with_words)
                    dur = max(0.5, float(clip.end) - float(clip.start))
                    seek = smart_thumbnail_seek(words, dur, hook=clip.hook or "")
                    ok = generate_smart_thumbnail(final_path, thumb_path, seek=seek, width=1080)
                    if not ok:
                        thumb_cmd = [
                            "ffmpeg", "-y",
                            "-ss", f"{max(0.2, float(seek)):.2f}",
                            "-i", final_path,
                            "-frames:v", "1",
                            "-vf", "scale='min(1080,iw)':-2",
                            "-q:v", "2",
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

            # Generate meta JSON — slim index + per-clip json_analisa/
            from src.infrastructure.clip_quality_helpers import (
                build_clip_analisa,
                write_split_job_meta,
            )
            payloads = []
            for c in clips:
                words = self._get_words_for_clip(c, clips_with_words)
                broll_dicts = [
                    {
                        "at_time": s.at_time,
                        "keyword": s.keyword,
                        "template": s.template,
                        "duration": s.duration,
                        "reason": getattr(s, "reason", "") or "",
                        "placement": getattr(s, "placement", "") or "",
                    }
                    for s in (c.broll_suggestions or [])
                ]
                payloads.append(build_clip_analisa(
                    no=c.rank,
                    rank=c.rank,
                    start=c.start,
                    end=c.end,
                    hook=c.hook or "",
                    reason=c.reason or "",
                    score=c.score,
                    words=words,
                    broll_suggestions=broll_dicts,
                    text_emphasis_events=list(getattr(c, "text_emphasis_events", None) or [])[:2],
                    top_overlay_events=list(getattr(c, "top_overlay_events", None) or []),
                ))
            write_split_job_meta(
                output_dir,
                job_id=job_id,
                youtube_url=job.youtube_url,
                aspect_ratio=job.target_aspect_ratio,
                created_at=str(job.created_at) if job.created_at else None,
                clip_payloads=payloads,
                clips_total=clips_count,
                clips_success=sum(1 for c in clips if trim_results.get(c.rank)),
            )

            self._emit(job_id, 14.5, "thumbnails", "complete")
            logger.info(f"[{job_id}] Thumbnails + json_analisa split written")

            # ═══ Step 15: Assemble JSON (include scene_graphs) ═══
            self._emit(job_id, 15, "assemble", "start")
            await self._repo.update_status(job_id, JobStatus.ASSEMBLING)

            clips_data = self._assemble_clips_data(job, clips, clips_with_words, reframe_data, creative_direction)
            # Include scene graphs in output
            clips_data["scene_graphs"] = {
                str(rank): sg.to_dict() for rank, sg in scene_graphs.items()
            }
            # Preserve style configs & auto_post settings from job creation
            if job.clips_data:
                for k in (
                    "hook_style_config",
                    "subtitle_style_config",
                    "content_profile",
                    "source",
                    "source_type",
                    "watermark_config",
                    "cta_config",
                    "text_emphasis_style_config",
                    "text_emphasis_enabled",
                    "auto_post_social",
                    "auto_post_platforms",
                    "auto_post_account_ids",
                    "auto_post_schedule_mode",
                    "auto_post_custom_time",
                ):
                    if job.clips_data.get(k) is not None:
                        clips_data[k] = job.clips_data[k]
            await self._repo.update_clips_data(job_id, clips_data)

            success_count = sum(1 for c in clips if trim_results.get(c.rank))
            failed_count = clips_count - success_count
            await self._repo.update_clips_count(job_id, clips_count, success_count, failed_count)
            await self._repo.update_status(job_id, JobStatus.COMPLETED)

            total_duration = time.time() - pipeline_start
            self._emit(job_id, 15, "assemble", "complete", total_duration)
            self._emit(job_id, success_count, JobStatus.COMPLETED.value, "done", total_duration)
            logger.info(f"[{job_id}] Pipeline completed in {total_duration:.1f}s — {success_count}/{clips_count} clips")

            # Telegram notification on job completion
            try:
                from src.infrastructure.telegram_service import telegram_service
                clips_list = [asdict(c) if hasattr(c, "__dataclass_fields__") else (c if isinstance(c, dict) else c.__dict__) for c in clips]
                asyncio.create_task(telegram_service.notify_job_completed(
                    job_id=job_id,
                    title=job.title or job.youtube_url or "Video",
                    clips_count=len(clips_list),
                    clips=clips_list,
                    output_dir=output_dir,
                ))
            except Exception:
                pass

            # Direct AI Auto-Post trigger for job-specific auto-post
            if (job.clips_data or {}).get("auto_post_social") and output_dir and os.path.exists(output_dir):
                try:
                    from src.infrastructure.social_auto_post_service import social_auto_post_service
                    clips_list = [asdict(c) if hasattr(c, "__dataclass_fields__") else (c if isinstance(c, dict) else c.__dict__) for c in clips]
                    raw_plats = (job.clips_data or {}).get("auto_post_platforms", "")
                    target_plats = [p.strip() for p in raw_plats.split(",") if p.strip()] if raw_plats else None
                    target_accs = (job.clips_data or {}).get("auto_post_account_ids") or None
                    sched_mode = (job.clips_data or {}).get("auto_post_schedule_mode", "ai")
                    custom_time = (job.clips_data or {}).get("auto_post_custom_time")
                    asyncio.create_task(social_auto_post_service.auto_schedule_job_clips(
                        job_id=job_id,
                        clips=clips_list,
                        output_dir=output_dir,
                        user_id=job.user_id,
                        target_platforms=target_plats,
                        target_account_ids=target_accs,
                        schedule_mode=sched_mode,
                        custom_schedule_time=custom_time,
                        notify_telegram=True,
                    ))
                except Exception as e:
                    logger.warning(f"Failed to auto-post job {job_id}: {e}")

        except asyncio.CancelledError:
            logger.info(f"[{job_id}] Pipeline cancelled by user.")
            try:
                await self._repo.update_status(job_id, JobStatus.FAILED, "Cancelled by user")
            except Exception:
                pass
            return
        except Exception as e:
            logger.exception(f"[{job_id}] Pipeline failed: {e}")
            await self._repo.update_status(job_id, JobStatus.FAILED, str(e)[:512])
            # Telegram notification on job failure
            try:
                from src.infrastructure.telegram_service import telegram_service
                asyncio.create_task(telegram_service.notify_job_failed(
                    job_id=job_id,
                    error=str(e),
                    title=job.title or ""
                ))
            except Exception:
                pass
        finally:
            # Cleanup temp files
            if self._cleanup:
                try:
                    self._cleanup.cleanup_job_directory(output_dir)
                except Exception:
                    pass

    # ─── Pipeline Helpers ─────────────────────────────────────────────────────

    # ═══ Engine Router Methods ═══════════════════════════════════════════════

    def _select_render_engine(self, job: Job) -> str:
        """Select the rendering engine based on job configuration and available adapters.

        Returns:
            "ffmpeg" if hook_engine == "ffmpeg" or Remotion unavailable,
            "remotion" if Remotion adapter is available (will check health at render time),
        """
        # Explicit FFmpeg engine request
        if job.hook_engine == "ffmpeg":
            logger.info(f"[{job.job_id}] Explicit FFmpeg engine requested")
            return "ffmpeg"

        # Default: Remotion path
        if self._remotion_adapter is not None:
            return "remotion"

        logger.warning(f"[{job.job_id}] No Remotion adapter — falling back to FFmpeg engine")
        return "ffmpeg"

    async def _run_ffmpeg_render_path(
        self,
        job_id: str,
        job: Job,
        clips: list[Clip],
        output_dir: str,
        reframe_data: dict,
        trim_results: dict,
        clips_with_words: list[dict],
        creative_direction,
    ) -> None:
        """FFmpeg render path — Hook → B-Roll → Subtitle, all via FFmpeg drawtext.

        This is the lightweight server-side path that requires no browser/Remotion.
        Three sequential steps:
          1. Hook rendering (burn hook text onto first ~3s of each clip)
          2. B-Roll overlay (motion typography on top of video)
          3. Subtitle rendering (word-by-word drawtext, rendered LAST)
        Original audio is preserved throughout — no timeline changes.
        """
        import shutil

        # Get custom style configs from job
        hook_style_config = {}
        subtitle_style_config = {}
        if job.clips_data:
            hook_style_config = job.clips_data.get("hook_style_config", {}) or {}
            subtitle_style_config = job.clips_data.get("subtitle_style_config", {}) or {}

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
                await self._render_hook_ffmpeg(
                    in_path, clip.hook, out_path,
                    hook_style=hook_style,
                    style_config=hook_style_config,
                )
                logger.info(f"[{job_id}] Hook rendered clip {clip.rank} (style={hook_style})")
            except Exception as e:
                logger.warning(f"[{job_id}] Hook render failed clip {clip.rank}: {e}")
        self._emit(job_id, 10, "hook_render", "complete")

        # ═══ Step 11: B-Roll Overlay (motion typography on top of video) ═══
        # B-roll is OVERLAID on top of the video (not inserted).
        # Original audio continues uninterrupted. Timeline does NOT change.
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
            sub_enabled = (subtitle_style_config or {}).get("enabled", True) is not False
            if words and self._subtitle_renderer and sub_enabled:
                try:
                    # Build style from subtitle_style_config
                    from src.domain.entities import SubtitleStyleConfig
                    
                    # Extract properties from subtitle_style_config
                    color = subtitle_style_config.get("color", creative_direction.primary_color)
                    highlight_color = subtitle_style_config.get("highlightColor", creative_direction.secondary_color)
                    uppercase = subtitle_style_config.get("uppercase", creative_direction.subtitle_uppercase)
                    position = subtitle_style_config.get("position", creative_direction.subtitle_position)
                    
                    sub_style = SubtitleStyleConfig(
                        enabled=sub_enabled,
                        color=color,
                        highlight_color=highlight_color,
                        uppercase=uppercase,
                        position=position,
                        start_offset=3.0,  # Subtitle starts after 3s hook
                    )
                    self._subtitle_renderer.render_subtitles(
                        video_path=in_path,
                        words=words,
                        style=sub_style,
                        output_path=out_path,
                        start_offset=3.0,  # Subtitle starts after 3s hook
                    )
                    logger.info(f"[{job_id}] Subtitle rendered clip {clip.rank}")
                except Exception as e:
                    logger.warning(f"[{job_id}] Subtitle render failed clip {clip.rank}: {e}")
                    if os.path.exists(in_path) and not os.path.exists(out_path):
                        shutil.copy2(in_path, out_path)
            else:
                # No words / no renderer — copy best available as final
                if os.path.exists(in_path) and not os.path.exists(out_path):
                    shutil.copy2(in_path, out_path)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                # Watermark (FFmpeg overlay/drawtext) — final pass on top of everything
                await self._apply_watermark(job, clip.rank, output_dir, out_path, job_id)
                mark_clip_ready(output_dir, clip.rank)
        self._emit(job_id, 12, "subtitle", "complete")

    async def _run_remotion_render_path(
        self,
        job_id: str,
        job: Job,
        clips: list[Clip],
        output_dir: str,
        reframe_data: dict,
        trim_results: dict,
        clips_with_words: list[dict],
        scene_graphs: dict,
        prosody_results: dict,
        creative_direction,
    ) -> None:
        """Remotion render path — all-in-one hook+subtitle via browser render.

        Remotion is the primary rendering engine. It handles hook, subtitle,
        B-roll motion graphics, and scene graph execution in a single pass.
        FFmpeg fallback is used only for catastrophic Remotion failures.
        """
        import shutil
        use_remotion = False

        if self._remotion_adapter:
            self._emit(job_id, 10, "remotion_render", "start")
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
                        from src.infrastructure.canvas_templates import (
                            build_canvas_config,
                            output_resolution_for_job,
                        )
                        res = output_resolution_for_job(job.target_aspect_ratio)
                        render_config = RemotionRenderConfig(
                            concurrency=settings.REMOTION_CONCURRENCY,
                            quality=settings.REMOTION_QUALITY,
                            enable_threejs=settings.REMOTION_ENABLE_THREEJS,
                            enable_ai_layer=settings.REMOTION_ENABLE_AI_LAYER,
                            resolution=res,
                        )
                        # Merge custom style configs into creative direction
                        cd_dict = asdict(creative_direction) if creative_direction else {}
                        if job.clips_data:
                            if job.clips_data.get("hook_style_config"):
                                cd_dict["hook_style_config"] = job.clips_data["hook_style_config"]
                            if job.clips_data.get("subtitle_style_config"):
                                cd_dict["subtitle_style_config"] = job.clips_data["subtitle_style_config"]
                            canvas = job.clips_data.get("canvas_config")
                            if not canvas and (job.target_aspect_ratio or "") in ("16:9", "1:1"):
                                canvas = build_canvas_config(
                                    job.target_aspect_ratio,
                                    background_mode=job.clips_data.get("background_mode"),
                                    background_template_id=job.clips_data.get("background_template_id"),
                                    background_image_url=job.clips_data.get("background_image_data_url"),
                                )
                            if canvas:
                                cd_dict["canvas_config"] = canvas
                        else:
                            # Try re-read from DB as last resort
                            _fresh = await self._repo.get_by_job_id(job_id)
                            if _fresh and _fresh.clips_data:
                                if _fresh.clips_data.get("hook_style_config"):
                                    cd_dict["hook_style_config"] = _fresh.clips_data["hook_style_config"]
                                if _fresh.clips_data.get("subtitle_style_config"):
                                    cd_dict["subtitle_style_config"] = _fresh.clips_data["subtitle_style_config"]
                                job.clips_data = _fresh.clips_data

                        # Add zoom events from prosody analysis
                        prosody = prosody_results.get(clip.rank)
                        if prosody and prosody.energy_peaks:
                            cd_dict["zoom_events"] = [
                                {"time": peak.time, "intensity": peak.intensity, "duration": 0.5}
                                for peak in prosody.energy_peaks[:8]
                                if peak.time > (cd_dict.get("hook_style_config", {}).get("duration", 3.0))
                            ]
                        self._apply_reframe_metadata(
                            cd_dict, job, reframe_data.get(clip.rank)
                        )
                        
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
                                shutil.copy2(in_path, out_path)
                    except Exception as e:
                        logger.exception(f"[{job_id}] Remotion render error clip {clip.rank}: {e}")
                        if os.path.exists(in_path) and not os.path.exists(out_path):
                            shutil.copy2(in_path, out_path)
                    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                        # Watermark (FFmpeg overlay/drawtext) — final pass on top of everything
                        await self._apply_watermark(job, clip.rank, output_dir, out_path, job_id)
                        mark_clip_ready(output_dir, clip.rank)
                
                self._emit(job_id, 12, "remotion_render", "complete")
            else:
                # Server not running — start it and wait
                logger.info(f"[{job_id}] Remotion server not running — starting...")
                started = await self._remotion_adapter.start_server()
                if started and await self._remotion_adapter.health_check():
                    use_remotion = True
                    logger.info(f"[{job_id}] Remotion server started successfully")
                    for clip in clips:
                        if not trim_results.get(clip.rank):
                            continue
                        
                        scene_graph = scene_graphs.get(clip.rank)
                        if not scene_graph:
                            logger.warning(f"[{job_id}] No scene graph for clip {clip.rank}")
                            continue
                        
                        in_path = self._best_clip_path(output_dir, clip.rank, reframe_data)
                        out_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"
                        
                        clip_words = self._get_words_for_clip(clip, clips_with_words)
                        clip_hook = clip.hook or ""
                        
                        try:
                            from src.domain.interfaces_remotion import RemotionRenderConfig
                            from src.infrastructure.canvas_templates import (
                                build_canvas_config,
                                output_resolution_for_job,
                            )
                            res = output_resolution_for_job(job.target_aspect_ratio)
                            render_config = RemotionRenderConfig(
                                concurrency=settings.REMOTION_CONCURRENCY,
                                quality=settings.REMOTION_QUALITY,
                                enable_threejs=settings.REMOTION_ENABLE_THREEJS,
                                enable_ai_layer=settings.REMOTION_ENABLE_AI_LAYER,
                                resolution=res,
                            )
                            cd_dict = asdict(creative_direction) if creative_direction else {}
                            if job.clips_data:
                                if job.clips_data.get("hook_style_config"):
                                    cd_dict["hook_style_config"] = job.clips_data["hook_style_config"]
                                if job.clips_data.get("subtitle_style_config"):
                                    cd_dict["subtitle_style_config"] = job.clips_data["subtitle_style_config"]
                                canvas = job.clips_data.get("canvas_config")
                                if not canvas and (job.target_aspect_ratio or "") in ("16:9", "1:1"):
                                    canvas = build_canvas_config(
                                        job.target_aspect_ratio,
                                        background_mode=job.clips_data.get("background_mode"),
                                        background_template_id=job.clips_data.get("background_template_id"),
                                        background_image_url=job.clips_data.get("background_image_data_url"),
                                    )
                                if canvas:
                                    cd_dict["canvas_config"] = canvas
                            self._apply_reframe_metadata(cd_dict, job, reframe_data.get(clip.rank))
                            
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
                                    shutil.copy2(in_path, out_path)
                        except Exception as e:
                            logger.exception(f"[{job_id}] Remotion render error clip {clip.rank}: {e}")
                            if os.path.exists(in_path) and not os.path.exists(out_path):
                                shutil.copy2(in_path, out_path)
                        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                            # Watermark (FFmpeg overlay/drawtext) — final pass on top of everything
                            await self._apply_watermark(job, clip.rank, output_dir, out_path, job_id)
                            mark_clip_ready(output_dir, clip.rank)
                    
                    self._emit(job_id, 12, "remotion_render", "complete")
                else:
                    logger.error(f"[{job_id}] Failed to start Remotion server — will attempt FFmpeg fallback")
        else:
            logger.warning(f"[{job_id}] No Remotion adapter configured — using FFmpeg fallback")
        
        if not use_remotion:
            # ═══ Fallback: FFmpeg Multi-step rendering (Hook → B-Roll → Subtitle) ═══
            # Delegate to the shared FFmpeg render path
            await self._run_ffmpeg_render_path(
                job_id=job_id,
                job=job,
                clips=clips,
                output_dir=output_dir,
                reframe_data=reframe_data,
                trim_results=trim_results,
                clips_with_words=clips_with_words,
                creative_direction=creative_direction,
            )

    def _apply_reframe_metadata(
        self,
        creative_direction: dict,
        job: Job,
        clip_reframe: Optional[dict],
    ) -> None:
        """Attach read-only reframe information without overriding user style."""
        clips_data = job.clips_data or {}
        creative_direction["content_profile"] = clips_data.get("content_profile", {})
        creative_direction["reframe_method"] = (
            str(clip_reframe.get("method", "") or "")
            if isinstance(clip_reframe, dict)
            else ""
        )
        if not isinstance(clip_reframe, dict):
            return
        for key in (
            "layout",
            "layout_mode",
            "layout_events",
            "framing_events",
            "subtitle_position_y",
            "transition_style",
            "transition_duration",
        ):
            if clip_reframe.get(key) is not None:
                target_key = "reframe_layout" if key == "layout" else key
                creative_direction[target_key] = clip_reframe[key]

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

    async def _render_hook_ffmpeg(self, video_path: str, hook_text: str, output_path: str, hook_style: str = "zoom_punch", style_config: dict | None = None) -> None:
        """Burn hook text onto first 3 seconds of video using FFmpeg drawtext.

        Uses textfile= approach to avoid all text escaping issues.
        Renders with style-specific parameters for font, animation, and color.

        If style_config is provided (from frontend StyleEditorModal), it overrides
        the preset values for font, color, size, duration, stroke, shadow, etc.

        Supported hook_style values:
          - zoom_punch: Bold white text, quick scale-in (default)
          - fade_scale: Smooth fade + slight grow
          - slide_punch_framer: Slide from left with punch
          - typewriter: Character-by-character reveal
          - glitch_rgb: RGB split/chromatic aberration effect
          - shake_neon: Neon glow with random shake
          - cinematic_reveal: Cinematic letterbox + elegant fade-in
          - danger_bold: Bold red with pulsing border
        """
        import subprocess
        import shutil

        if not hook_text or not hook_text.strip():
            shutil.copy2(video_path, output_path)
            return

        # If Skia engine or preset is requested, delegate to SkiaHookRenderer
        if str(hook_style).startswith("skia_") or (style_config and style_config.get("engine") == "skia"):
            try:
                from src.infrastructure.skia_hook_renderer import SkiaHookRenderer
                fonts_dir = getattr(self, "_fonts_dir", "assets/fonts")
                renderer = SkiaHookRenderer(font_dir=fonts_dir)
                await renderer.render_hook(video_path, hook_text, output_path, hook_style=hook_style, style_config=style_config)
                if os.path.exists(output_path):
                    return
            except Exception as e:
                logger.warning(f"SkiaHookRenderer failed ({e}), falling back to FFmpeg drawtext")

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
            # ─── NEW: Kinetic Typography Styles ───────────────────────────
            "glitch_rgb": {
                "fontsize": 58, "fontcolor": "white", "borderw": 0,
                "bordercolor": "black", "duration": 3.0,
                "font_pref": ["Anton-Regular.ttf", "BlackOpsOne-Regular.ttf", "BebasNeue-Regular.ttf"],
                "bg_opacity": 0.7, "y_expr": "h*0.4-text_h/2",
                "effect": "glitch_rgb",
            },
            "shake_neon": {
                "fontsize": 54, "fontcolor": "#00FFCC", "borderw": 0,
                "bordercolor": "black", "duration": 3.0,
                "font_pref": ["Bungee-Regular.ttf", "Anton-Regular.ttf", "BlackOpsOne-Regular.ttf"],
                "bg_opacity": 0.65, "y_expr": "h*0.4-text_h/2",
                "effect": "shake_neon",
            },
            "cinematic_reveal": {
                "fontsize": 62, "fontcolor": "#FFD700", "borderw": 0,
                "bordercolor": "black", "duration": 3.5,
                "font_pref": ["PlayfairDisplay-Variable.ttf", "Lora-Variable.ttf", "Merriweather-Bold.ttf"],
                "bg_opacity": 0.8, "y_expr": "h*0.42-text_h/2",
                "effect": "cinematic_reveal",
            },
            "danger_bold": {
                "fontsize": 70, "fontcolor": "#FF2D2D", "borderw": 6,
                "bordercolor": "black", "duration": 3.0,
                "font_pref": ["BlackOpsOne-Regular.ttf", "Anton-Regular.ttf", "ArchivoBlack-Regular.ttf"],
                "bg_opacity": 0.75, "y_expr": "h*0.38-text_h/2",
                "effect": "danger_bold",
            },
        }

        style = HOOK_STYLES.get(hook_style, HOOK_STYLES["zoom_punch"])

        # Route through high-fidelity PIL frame renderer for exact 1:1 visual match to preview
        try:
            from src.infrastructure.skia_hook_renderer import SkiaHookRenderer
            fonts_dir = getattr(self, "_fonts_dir", "assets/fonts")
            skia_hook = SkiaHookRenderer(font_dir=fonts_dir)
            await skia_hook.render_hook(
                video_path=video_path,
                hook_text=hook_text,
                output_path=output_path,
                hook_style=hook_style,
                style_config=style_config,
            )
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"Hook high-fidelity rendered: {os.path.basename(output_path)}")
                return
        except Exception as e:
            logger.warning(f"Hook high-fidelity render failed ({e}), falling back to drawtext")

        # Try DB-driven style first (overrides hardcoded)
        try:
            from src.infrastructure.ffmpeg_styles_store import get_ffmpeg_hook_style
            db_style = get_ffmpeg_hook_style(hook_style)
            if db_style:
                style = db_style
        except Exception:
            pass

        duration = style["duration"]
        fontsize = style["fontsize"]
        fontcolor = style["fontcolor"]
        borderw = style["borderw"]
        bordercolor = style["bordercolor"]
        bg_opacity = style["bg_opacity"]
        y_expr = style["y_expr"]

        # Apply style_config overrides from frontend (StyleEditorModal FFmpeg tab)
        if style_config:
            if style_config.get("duration"):
                duration = float(style_config["duration"])
            if style_config.get("fontSize"):
                fontsize = int(style_config["fontSize"])
            if style_config.get("color"):
                fontcolor = style_config["color"]
            if style_config.get("strokeEnabled") and style_config.get("strokeWidth"):
                borderw = int(style_config["strokeWidth"])
                bordercolor = style_config.get("strokeColor", "black")
            elif style_config.get("strokeEnabled") is False:
                borderw = 0
            if style_config.get("bgOpacity") is not None:
                bg_opacity = float(style_config["bgOpacity"])
            if style_config.get("positionY"):
                pos_y = int(style_config["positionY"])
                y_expr = f"h*{pos_y / 100:.2f}-text_h/2"
            if style_config.get("animation"):
                # Map animation name to effect if it exists in HOOK_STYLES
                anim_style = HOOK_STYLES.get(style_config["animation"])
                if anim_style and anim_style.get("effect"):
                    style = {**style, "effect": anim_style["effect"]}
            # Override font_pref with custom fontFamily
            if style_config.get("fontFamily"):
                style = {**style, "font_pref": [style_config["fontFamily"]]}

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
            font_path = self._resolve_hook_font(style.get("font_pref") or [])
            font_opt = f":fontfile='{font_path}'" if font_path else ""

            # Alpha fade expression — escape commas to avoid filter parser confusion
            alpha_expr = (
                f"if(lt(t\\,0.5)\\,t/0.5\\,"
                f"if(gt(t\\,{duration - 0.5})\\,({duration}-t)/0.5\\,1))"
            )

            # ─── Build filter based on effect type ────────────────────
            effect = style.get("effect", "")

            if effect == "glitch_rgb":
                # RGB Split / Chromatic Aberration — 3 text layers with color offset
                filter_complex = (
                    f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{bg_opacity}:t=fill"
                    f":enable='between(t,0,{duration})',"
                    # Red channel — offset left
                    f"drawtext=textfile='{text_file}'"
                    f":fontsize={fontsize}{font_opt}"
                    f":fontcolor=#FF0000@0.7:borderw=0"
                    f":x=(w-text_w)/2-4+sin(t*15)*3:y={y_expr}"
                    f":alpha='{alpha_expr}'"
                    f":enable='between(t,0,{duration})',"
                    # Cyan channel — offset right
                    f"drawtext=textfile='{text_file}'"
                    f":fontsize={fontsize}{font_opt}"
                    f":fontcolor=#00FFFF@0.7:borderw=0"
                    f":x=(w-text_w)/2+4-sin(t*15)*3:y={y_expr}"
                    f":alpha='{alpha_expr}'"
                    f":enable='between(t,0,{duration})',"
                    # Main white text on top
                    f"drawtext=textfile='{text_file}'"
                    f":fontsize={fontsize}{font_opt}"
                    f":fontcolor=white:borderw=0"
                    f":x=(w-text_w)/2:y={y_expr}"
                    f":alpha='{alpha_expr}'"
                    f":enable='between(t,0,{duration})'"
                )

            elif effect == "shake_neon":
                # Neon glow with random shake — multiple glow layers + shaking text
                glow_color = fontcolor  # e.g. #00FFCC
                filter_complex = (
                    f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{bg_opacity}:t=fill"
                    f":enable='between(t,0,{duration})',"
                    # Glow layer 1 (large, dim)
                    f"drawtext=textfile='{text_file}'"
                    f":fontsize={fontsize}{font_opt}"
                    f":fontcolor={glow_color}@0.3:borderw=12:bordercolor={glow_color}@0.15"
                    f":x=(w-text_w)/2:y={y_expr}"
                    f":alpha='{alpha_expr}'"
                    f":enable='between(t,0,{duration})',"
                    # Glow layer 2 (medium)
                    f"drawtext=textfile='{text_file}'"
                    f":fontsize={fontsize}{font_opt}"
                    f":fontcolor={glow_color}@0.5:borderw=6:bordercolor={glow_color}@0.3"
                    f":x=(w-text_w)/2+sin(t*25)*2:y={y_expr}+cos(t*20)*2"
                    f":alpha='{alpha_expr}'"
                    f":enable='between(t,0,{duration})',"
                    # Main text with subtle shake
                    f"drawtext=textfile='{text_file}'"
                    f":fontsize={fontsize}{font_opt}"
                    f":fontcolor={glow_color}:borderw=0"
                    f":x=(w-text_w)/2+sin(t*30)*1.5:y={y_expr}+cos(t*35)*1"
                    f":alpha='{alpha_expr}'"
                    f":enable='between(t,0,{duration})'"
                )

            elif effect == "cinematic_reveal":
                # Cinematic letterbox + elegant fade-in from center
                filter_complex = (
                    # Letterbox bars (cinematic feel)
                    f"drawbox=x=0:y=0:w=iw:h=ih*0.12:color=black:t=fill"
                    f":enable='between(t,0,{duration})',"
                    f"drawbox=x=0:y=ih*0.88:w=iw:h=ih*0.12:color=black:t=fill"
                    f":enable='between(t,0,{duration})',"
                    # Dark overlay
                    f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{bg_opacity}:t=fill"
                    f":enable='between(t,0,{duration})',"
                    # Main text with slow scale-in feel (fontsize expression not supported,
                    # so we use alpha + position animation for elegance)
                    f"drawtext=textfile='{text_file}'"
                    f":fontsize={fontsize}{font_opt}"
                    f":fontcolor={fontcolor}:borderw=0"
                    f":shadowx=2:shadowy=2:shadowcolor=black@0.8"
                    f":x=(w-text_w)/2:y={y_expr}"
                    f":alpha='if(lt(t\\,1.0)\\,t/1.0\\,"
                    f"if(gt(t\\,{duration - 0.8})\\,({duration}-t)/0.8\\,1))'"
                    f":enable='between(t,0,{duration})'"
                )

            elif effect == "danger_bold":
                # Bold red with pulsing border + flash effect
                filter_complex = (
                    f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{bg_opacity}:t=fill"
                    f":enable='between(t,0,{duration})',"
                    # Red glow behind
                    f"drawtext=textfile='{text_file}'"
                    f":fontsize={fontsize}{font_opt}"
                    f":fontcolor=#FF0000@0.4:borderw=10:bordercolor=#FF0000@0.2"
                    f":x=(w-text_w)/2:y={y_expr}"
                    f":alpha='{alpha_expr}'"
                    f":enable='between(t,0,{duration})',"
                    # Main text with thick border (pulse simulated by borderw)
                    f"drawtext=textfile='{text_file}'"
                    f":fontsize={fontsize}{font_opt}"
                    f":fontcolor={fontcolor}:borderw={borderw}:bordercolor=black"
                    f":x=(w-text_w)/2:y={y_expr}"
                    f":alpha='{alpha_expr}'"
                    f":enable='between(t,0,{duration})'"
                )

            else:
                # Default: original simple style (zoom_punch, fade_scale, etc.)
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
        font_dirs = [
            getattr(self, "_fonts_dir", "assets/fonts"),
            "assets/fonts",
            "backend/assets/fonts",
            "/usr/share/fonts/truetype",
            "/System/Library/Fonts",
            "/Library/Fonts",
        ]
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
        for fdir in font_dirs:
            if not fdir or not os.path.isdir(fdir):
                continue
            for name in candidates:
                path = os.path.join(fdir, name)
                if os.path.exists(path):
                    return os.path.abspath(path)
            # Try any .ttf file in the directory
            try:
                for f in os.listdir(fdir):
                    if f.endswith(".ttf") or f.endswith(".otf"):
                        return os.path.abspath(os.path.join(fdir, f))
            except OSError:
                pass
        return ""

    async def _apply_watermark(self, job, clip_rank: int, output_dir: str, final_path: str, job_id: str) -> None:
        """Apply the user-configured watermark (FFmpeg) to a finished clip, in place."""
        from src.infrastructure.watermark_renderer import apply_watermark_for_job
        await apply_watermark_for_job(
            job, clip_rank, output_dir, final_path,
            fonts_dir=getattr(self, "_fonts_dir", "assets/fonts"),
            job_id=job_id,
        )

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
        """Run 9router Groq Whisper first, then the existing local fallback."""
        from src.infrastructure.groq_whisper import GroqWhisperTranscriber

        router_whisper = GroqWhisperTranscriber()
        results = []
        for clip in clips:
            if not trim_results.get(clip.rank):
                results.append({"rank": clip.rank, "words": [], "_success": False})
                continue
            clip_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
            try:
                segments = []
                if router_whisper.is_available:
                    segments = await router_whisper.transcribe(clip_path, language="id")
                    has_word_timestamps = any(
                        segment.get("words") for segment in segments
                    )
                    if not has_word_timestamps:
                        logger.warning(
                            f"[{job_id}] 9router Whisper clip {clip.rank} returned "
                            "no word timestamps; using local Whisper"
                        )
                        segments = []

                if not segments:
                    segments = await self._whisper.transcribe_clip(clip_path)

                results.append({
                    "rank": clip.rank,
                    "words": segments,
                    "_success": bool(segments),
                })
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
            try:
                from src.infrastructure.clip_quality_helpers import share_pack_for_clip
                captions, hashtags, hook_alts = share_pack_for_clip(
                    hook=clip.hook or "",
                    reason=clip.reason or "",
                    score=clip.score,
                    duration=clip.end - clip.start,
                    words=words,
                    visual_entities=list(getattr(clip, "visual_entities", None) or []),
                    rank=clip.rank,
                )
            except Exception:
                captions, hashtags, hook_alts = {}, [], []
            assembled_clips.append({
                "rank": clip.rank,
                "score": clip.score,
                "start": clip.start,
                "end": clip.end,
                "hook": clip.hook,
                "reason": clip.reason,
                "duration": round(clip.end - clip.start, 2),
                "words": words,
                "captions": captions,
                "hashtags": hashtags,
                "hook_alts": hook_alts,
                "text_emphasis_events": [
                    {
                        key: value
                        for key, value in event.items()
                        if key != "foreground_frames"
                    }
                    for event in clip.text_emphasis_events[:2]
                ],
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


# Backward-compatible alias
AutoClipService = JobService