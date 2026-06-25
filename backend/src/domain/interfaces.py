from __future__ import annotations

"""Domain interfaces — Abstract Base Classes for infrastructure (v0.4)."""
from abc import ABC, abstractmethod
from typing import Any, Optional

from .entities import Clip, Job, JobStatus, PipelineFlags, BRollSuggestion, AssetResult, CreativeDirection


# ─── Core Pipeline Interfaces ─────────────────────────────────────────────────

class IJobRepository(ABC):
    @abstractmethod
    async def create(self, job: Job) -> Job: ...

    @abstractmethod
    async def get_by_job_id(self, job_id: str) -> Optional[Job]: ...

    @abstractmethod
    async def update_status(self, job_id: str, status: JobStatus, error_message: Optional[str] = None) -> None: ...

    @abstractmethod
    async def update_render_progress(self, job_id: str, progress: str) -> None: ...

    @abstractmethod
    async def update_clips_count(self, job_id: str, total: int, success: int, failed: int) -> None: ...

    @abstractmethod
    async def update_clips_data(self, job_id: str, clips_data: dict) -> None: ...

    @abstractmethod
    async def get_by_url_active(self, url: str) -> Optional[Job]: ...


class IDownloader(ABC):
    @abstractmethod
    async def validate_url(self, url: str) -> tuple[bool, Optional[str], Optional[float]]: ...

    @abstractmethod
    async def download_video(self, url: str, output_path: str) -> bool: ...


class ITranscriptFetcher(ABC):
    @abstractmethod
    async def fetch_transcript(self, video_url: str) -> Optional[dict]: ...


class IGeminiAnalyzer(ABC):
    @abstractmethod
    async def analyze(self, transcript: dict, video_duration: float, max_clips: int) -> dict:
        """Analyze transcript → clip candidates + hooks + broll_suggestions."""
        ...


class IWhisperLocal(ABC):
    @abstractmethod
    async def transcribe_clip(self, audio_path: str) -> list[dict]: ...


class IRenderer(ABC):
    @abstractmethod
    async def trim_clip(self, video_path: str, clip: Clip, output_path: str) -> bool: ...


class IValidator(ABC):
    @abstractmethod
    def validate_clip_result(self, data: dict, video_duration: float) -> tuple[bool, list[str]]: ...

    @abstractmethod
    def validate_clip_timestamps(self, clip: Clip, video_duration: float) -> list[str]: ...


# ─── v0.4 New Interfaces ──────────────────────────────────────────────────────

class IAspectRatioRouter(ABC):
    """Step 6 — Determines pipeline behavior based on target aspect ratio."""

    @abstractmethod
    def route(self, aspect_ratio: str, autogrid_enabled: bool = False) -> PipelineFlags:
        """Return PipelineFlags controlling YOLO/AutoCenter/AutoGrid/HookMode."""
        ...


class IBrowserRenderEngine(ABC):
    """Headless Chrome + React + Framer Motion render service.

    Shared by Hook Rendering (Step 12) and B-Roll Injection (Step 11).
    """

    @abstractmethod
    async def render_hook(
        self,
        hook_text: str,
        style_config: dict,
        output_path: str,
        duration_ms: int = 3000,
        width: int = 1080,
        height: int = 1920,
    ) -> str:
        """Render hook animation → transparent video (WebM VP9 alpha) or PNG sequence."""
        ...

    @abstractmethod
    async def render_broll(
        self,
        keyword: str,
        template: str,
        output_path: str,
        duration_ms: int = 2000,
        width: int = 1080,
        height: int = 1920,
    ) -> str:
        """Render b-roll motion typography → full-frame video."""
        ...


class IBRollInjector(ABC):
    """Step 11 — Selects b-roll points and injects motion typography into clip."""

    @abstractmethod
    async def inject(
        self,
        clip_path: str,
        suggestions: list[BRollSuggestion],
        output_path: str,
    ) -> str:
        """Cut/transition from main footage → broll → back. Returns output path."""
        ...


class ISubtitleRenderer(ABC):
    """Step 13 — Word-by-word subtitle rendering via FFmpeg drawtext."""

    @abstractmethod
    def render_subtitles(
        self,
        video_path: str,
        words: list,
        style: Any,
        output_path: str,
        start_offset: float = 0.0,
    ) -> str:
        """Burn word-by-word subtitles onto video. Returns output path."""
        ...


class IYoloReframeEngine(ABC):
    """Step 8 — YOLO segmentation + auto-center + auto-grid (9:16 only)."""

    @abstractmethod
    async def process(
        self,
        video_path: str,
        output_path: str,
        target_aspect: str = "9:16",
        autogrid_enabled: bool = False,
    ) -> dict:
        """Reframe video with person detection. Returns {output_path, masks_dir, person_count}."""
        ...


# ─── Pipeline Infrastructure Interfaces ───────────────────────────────────────

from .entities import ResourceStatus, ResourceSummary, CheckpointData


class IResourceMonitor(ABC):
    @abstractmethod
    def check_resources(self) -> ResourceStatus: ...

    @abstractmethod
    async def monitor_loop(self, job_id: str, cancel_flag) -> ResourceSummary: ...


class ICheckpointManager(ABC):
    @abstractmethod
    def save(self, job_id: str, step_number: int, step_name: str, output_data) -> None: ...

    @abstractmethod
    def get_last_checkpoint(self, job_id: str) -> Optional[CheckpointData]: ...

    @abstractmethod
    def cleanup(self, job_id: str) -> None: ...


class ITranscriptCache(ABC):
    @abstractmethod
    async def get(self, video_id: str, model_hash: str) -> Optional[str]: ...

    @abstractmethod
    async def save(self, video_id: str, transcript_json: str, model_hash: str,
                   language: str, duration: float) -> None: ...


class ICDNUploader(ABC):
    @abstractmethod
    async def upload(self, file_path: str, key: str) -> Optional[str]: ...


class IHookRenderer(ABC):
    """Legacy v2 hook renderer interface (kept for fallback)."""
    @abstractmethod
    def render_hook(self, video_path: str, hook_text: str, style: Any, output_path: str) -> str: ...


class IThumbnailGenerator(ABC):
    @abstractmethod
    def generate(self, video_path: str, hook_text: str, output_path: str, style: Any = None) -> str: ...


# ─── Asset Fetcher Interfaces (v3.0) ─────────────────────────────────────────

class IAssetClient(ABC):
    """Interface for external asset API clients (Pexels, Pixabay, Iconify, GIPHY, Lottie)."""

    @abstractmethod
    async def search(self, keyword: str, **kwargs) -> Optional[AssetResult]:
        """Search for asset matching keyword. Returns AssetResult or None."""
        ...


class IAssetFetcher(ABC):
    """Interface for the asset fetcher orchestrator."""

    @abstractmethod
    async def fetch_assets(
        self,
        suggestions: list[BRollSuggestion],
        creative_direction: Optional[CreativeDirection] = None,
    ) -> list[BRollSuggestion]:
        """Resolve assets for all suggestions. Attaches asset_result to each. Returns updated list."""
        ...
