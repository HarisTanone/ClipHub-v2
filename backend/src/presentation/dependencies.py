"""Dependency Injection — wires infrastructure to application layer (v0.4)."""
import logging
from functools import lru_cache

from src.application.services import JobService
from src.infrastructure.downloader import YouTubeDownloader
from src.infrastructure.gemini_analyzer import GeminiAnalyzer
from src.infrastructure.renderer import FFmpegRenderer
from src.infrastructure.repositories import JobRepository
from src.infrastructure.validator import ClipValidator
from src.infrastructure.whisper_local import WhisperLocal

logger = logging.getLogger(__name__)


def _safe_import(factory, name: str):
    """Try to instantiate a component, return None on failure."""
    try:
        return factory()
    except Exception as e:
        logger.warning(f"[DI] {name} unavailable: {e}")
        return None


@lru_cache()
def get_job_service() -> JobService:
    """Singleton JobService with all v0.4 dependencies."""

    # ─── v0.4 Pipeline Components ─────────────────────────────────────────
    from src.infrastructure.aspect_ratio_router import AspectRatioRouter
    from src.infrastructure.browser_render_engine import BrowserRenderEngine
    from src.infrastructure.broll_injector import BRollInjector
    from src.infrastructure.subtitle_renderer import SubtitleRenderer
    from src.infrastructure.yolo_reframe_engine import YoloReframeEngine

    # ─── Infrastructure Components ────────────────────────────────────────
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

    # ─── Asset Fetcher ────────────────────────────────────────────────────
    from src.infrastructure.asset_fetcher import AssetFetcher

    # ─── v0.4 Core ────────────────────────────────────────────────────────
    aspect_router = _safe_import(AspectRatioRouter, "AspectRatioRouter")
    browser_render = _safe_import(BrowserRenderEngine, "BrowserRenderEngine")
    subtitle_renderer = _safe_import(SubtitleRenderer, "SubtitleRenderer")
    yolo_reframe = _safe_import(YoloReframeEngine, "YoloReframeEngine")

    # BRollInjector needs BrowserRenderEngine
    broll_injector = None
    if browser_render:
        broll_injector = _safe_import(lambda: BRollInjector(browser_render), "BRollInjector")

    # ─── Infrastructure ───────────────────────────────────────────────────
    cleanup_manager = _safe_import(CleanupManager, "CleanupManager")
    gemini_retry_handler = _safe_import(GeminiRetryHandler, "GeminiRetryHandler")
    gemini_rate_limiter = _safe_import(GeminiRateLimiter, "GeminiRateLimiter")
    resource_monitor = _safe_import(ResourceMonitor, "ResourceMonitor")
    ffprobe_validator = _safe_import(FFprobeValidator, "FFprobeValidator")
    overlap_detector = _safe_import(OverlapDetector, "OverlapDetector")
    checkpoint_manager = _safe_import(CheckpointManager, "CheckpointManager")
    sse_emitter = _safe_import(SSEProgressEmitter, "SSEProgressEmitter")
    url_deduplicator = _safe_import(URLDeduplicator, "URLDeduplicator")
    nvenc_encoder = _safe_import(NVENCEncoder, "NVENCEncoder")
    cdn_uploader = _safe_import(CDNUploader, "CDNUploader")
    batch_highlight = _safe_import(BatchHighlightProcessor, "BatchHighlightProcessor")
    asset_fetcher = _safe_import(AssetFetcher, "AssetFetcher")

    # ─── Remotion Integration (ALWAYS enabled for hook+subtitle) ──────
    from src.infrastructure.remotion_adapter import RemotionAdapter
    remotion_adapter = _safe_import(RemotionAdapter, "RemotionAdapter")

    return JobService(
        job_repo=JobRepository(),
        downloader=YouTubeDownloader(),
        gemini_analyzer=GeminiAnalyzer(),
        whisper_local=WhisperLocal(),
        renderer=FFmpegRenderer(),
        validator=ClipValidator(),
        # v0.4 pipeline
        aspect_ratio_router=aspect_router,
        browser_render_engine=browser_render,
        broll_injector=broll_injector,
        subtitle_renderer=subtitle_renderer,
        yolo_reframe_engine=yolo_reframe,
        # Infrastructure
        cleanup_manager=cleanup_manager,
        gemini_retry_handler=gemini_retry_handler,
        gemini_rate_limiter=gemini_rate_limiter,
        resource_monitor=resource_monitor,
        ffprobe_validator=ffprobe_validator,
        overlap_detector=overlap_detector,
        checkpoint_manager=checkpoint_manager,
        sse_emitter=sse_emitter,
        url_deduplicator=url_deduplicator,
        nvenc_encoder=nvenc_encoder,
        cdn_uploader=cdn_uploader,
        batch_highlight_processor=batch_highlight,
        asset_fetcher=asset_fetcher,
        # v3.0 Remotion integration
        remotion_adapter=remotion_adapter,
    )


@lru_cache()
def get_v2_pipeline_service():
    """Singleton V2PipelineService for non-premium users."""
    from src.application.services_v2 import V2PipelineService
    from src.infrastructure.aspect_ratio_router import AspectRatioRouter
    from src.infrastructure.browser_render_engine import BrowserRenderEngine
    from src.infrastructure.broll_injector import BRollInjector
    from src.infrastructure.subtitle_renderer import SubtitleRenderer
    from src.infrastructure.yolo_reframe_engine import YoloReframeEngine
    from src.infrastructure.resource_monitor import ResourceMonitor
    from src.infrastructure.overlap_detector import OverlapDetector
    from src.infrastructure.sse_progress_emitter import SSEProgressEmitter
    from src.infrastructure.asset_fetcher import AssetFetcher

    aspect_router = _safe_import(AspectRatioRouter, "V2-AspectRatioRouter")
    browser_render = _safe_import(BrowserRenderEngine, "V2-BrowserRenderEngine")
    subtitle_renderer = _safe_import(SubtitleRenderer, "V2-SubtitleRenderer")
    yolo_reframe = _safe_import(YoloReframeEngine, "V2-YoloReframeEngine")
    broll_injector = None
    if browser_render:
        broll_injector = _safe_import(lambda: BRollInjector(browser_render), "V2-BRollInjector")
    resource_monitor = _safe_import(ResourceMonitor, "V2-ResourceMonitor")
    overlap_detector = _safe_import(OverlapDetector, "V2-OverlapDetector")
    sse_emitter = _safe_import(SSEProgressEmitter, "V2-SSEProgressEmitter")
    asset_fetcher = _safe_import(AssetFetcher, "V2-AssetFetcher")

    # ─── Remotion Integration (ALWAYS enabled for hook+subtitle) ──────
    from src.infrastructure.remotion_adapter import RemotionAdapter
    remotion_adapter = _safe_import(RemotionAdapter, "V2-RemotionAdapter")

    return V2PipelineService(
        job_repo=JobRepository(),
        downloader=YouTubeDownloader(),
        renderer=FFmpegRenderer(),
        whisper_local=WhisperLocal(),
        # Shared pipeline components
        aspect_ratio_router=aspect_router,
        yolo_reframe_engine=yolo_reframe,
        browser_render_engine=browser_render,
        broll_injector=broll_injector,
        subtitle_renderer=subtitle_renderer,
        asset_fetcher=asset_fetcher,
        # Infrastructure
        sse_emitter=sse_emitter,
        overlap_detector=overlap_detector,
        resource_monitor=resource_monitor,
        # Remotion integration
        remotion_adapter=remotion_adapter,
    )


@lru_cache()
def get_pipeline_router():
    """Singleton PipelineRouter instance."""
    from src.infrastructure.pipeline_router import PipelineRouter
    return PipelineRouter()
