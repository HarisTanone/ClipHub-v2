from __future__ import annotations

"""Domain interfaces — Abstract Base Classes for infrastructure (v0.4)."""
from abc import ABC, abstractmethod
from typing import Any, Optional

from .entities import (
    Clip, Job, JobStatus, PipelineFlags, BRollSuggestion, AssetResult, CreativeDirection,
    TranscriptResult, AudioSlice, HighlightAnalysisResult,
)


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
    async def update_video_title(self, job_id: str, title: str) -> None: ...

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
    async def trim_clip(
        self,
        video_path: str,
        clip: Clip,
        output_path: str,
        normalize_timestamps: bool = False,
    ) -> bool: ...


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
    """Step 8 — Audio-Visual reframing (MediaPipe + Speaker Diarization).

    Legacy name kept for backward compatibility. Use IReframeEngine alias for new code.
    """

    @abstractmethod
    async def process(
        self,
        video_path: str,
        output_path: str,
        target_aspect: str = "9:16",
        autogrid_enabled: bool = False,
        **kwargs,
    ) -> dict:
        """Reframe video with speaker-aware framing. Returns {output_path, person_count, method}."""
        ...


# Semantic alias — prefer this in new code
IReframeEngine = IYoloReframeEngine


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


# ─── V2 Pipeline Interfaces (Groq-based, Non-Premium) ────────────────────────

class IGroqTranscriber(ABC):
    """TAHAP 1: Ingestion & Text Extraction.

    Primary: YouTube Transcript API (free).
    Fallback: Groq Whisper API (fast, free tier).
    """

    @abstractmethod
    async def transcribe(self, youtube_url: str, video_duration: float) -> TranscriptResult:
        """Get transcript: YouTube API first, Groq Whisper fallback.

        Args:
            youtube_url: Full YouTube URL
            video_duration: Video duration in seconds

        Returns:
            TranscriptResult with segments, source, language

        Raises:
            TranscriptionError: If both YouTube API and Groq Whisper fail
        """
        ...


class IGroqAnalyzer(ABC):
    """TAHAP 2: AI Highlight Analysis.

    Uses Groq LLM (llama-3.1-8b-instant) to identify viral moments
    from transcript text. Dynamic chunking for long videos.
    """

    @abstractmethod
    async def analyze_highlights(
        self, transcript: TranscriptResult, video_duration: float, max_clips: int
    ) -> HighlightAnalysisResult:
        """Analyze transcript → viral highlight candidates + creative direction.

        Args:
            transcript: TranscriptResult from TAHAP 1
            video_duration: Total video duration in seconds
            max_clips: Maximum number of clips to extract

        Returns:
            HighlightAnalysisResult with clips, creative_direction, broll_suggestions
        """
        ...


class IMicroSlicer(ABC):
    """TAHAP 3: Micro-Slicing.

    Extracts short audio segments from video based on highlight timestamps.
    Adds ±padding for Whisper context.
    """

    @abstractmethod
    async def slice_audio(
        self, video_path: str, highlights: list[dict], output_dir: str, video_duration: float
    ) -> list[AudioSlice]:
        """Extract audio segments for each highlight with padding.

        Args:
            video_path: Path to downloaded video file
            highlights: List of {start, end, rank} from Groq analysis
            output_dir: Directory to write WAV files
            video_duration: Total video duration for boundary clamping

        Returns:
            List of AudioSlice with paths and timing info
        """
        ...


class ISileroVAD(ABC):
    """TAHAP 5: Voice Activity Detection.

    Refines clip boundaries by finding silence gaps near cut points.
    Ensures cuts don't happen mid-word.
    """

    @abstractmethod
    async def refine_boundaries(
        self, audio_path: str, target_start: float, target_end: float,
        search_radius: float = 2.0
    ) -> tuple[float, float]:
        """Find nearest silence boundaries around target timestamps.

        Args:
            audio_path: Path to audio file (WAV 16kHz mono)
            target_start: Desired start time in seconds (relative to audio file)
            target_end: Desired end time in seconds (relative to audio file)
            search_radius: How far to search for silence (seconds)

        Returns:
            Tuple of (refined_start, refined_end) in seconds
        """
        ...
