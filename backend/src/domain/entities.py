from __future__ import annotations

"""Domain entities — pure Python dataclasses and enums (v0.4)."""
from dataclasses import dataclass, field, fields
from datetime import datetime
from enum import Enum

from typing import Any, Optional


# ─── Enums ────────────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    VALIDATING = "validating"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    PREPARING = "preparing"
    ROUTING = "routing"
    TRIMMING = "trimming"
    SEGMENTING = "segmenting"
    WHISPER = "whisper"
    HIGHLIGHTING = "highlighting"
    BROLL = "broll"
    HOOK_RENDERING = "hook_rendering"
    SUBTITLE_RENDERING = "subtitle_rendering"
    REMOTION_RENDERING = "remotion_rendering"  # v3.0 — Remotion render status
    ENCODING = "encoding"
    UPLOADING = "uploading"
    ASSEMBLING = "assembling"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    # ─── V2 Pipeline Statuses ─────────────────────────────────────────
    V2_TRANSCRIBING = "v2_transcribing"
    V2_ANALYZING = "v2_analyzing"
    V2_MICRO_SLICING = "v2_micro_slicing"
    V2_WORD_TRANSCRIBING = "v2_word_transcribing"
    V2_VAD_REFINING = "v2_vad_refining"


class AspectRatio(str, Enum):
    PORTRAIT = "9:16"
    LANDSCAPE = "16:9"
    SQUARE = "1:1"


class HookEngine(str, Enum):
    V2_LEGACY = "v2"
    V3_BROWSER = "v3"
    FFMPEG = "ffmpeg"  # Server-side FFmpeg drawtext (no browser/Remotion needed)


class BRollTemplate(str, Enum):
    WORD_POP = "word_pop_typography"
    LINE_REVEAL = "line_reveal_typography"
    PARTICLE_BURST = "particle_text_burst"


class BrollMotionStyle(str, Enum):
    """Motion-graphic style rendered in Remotion (preview == final).

    These styles supersede the legacy FFmpeg drawtext-only path. When a
    BRollSuggestion carries a ``motion_style``, the backend skips the FFmpeg
    overlay injection and instead emits a ``BrollEvent`` to the Remotion
    render props, guaranteeing the on-screen preview matches the exported clip.
    """
    # Image-based motion graphics
    KEN_BURNS = "ken_burns"               # slow zoom + pan (documentary)
    PARALLAX_ZOOM = "parallax_zoom"       # depth-based zoom
    LIGHT_SWEEP = "light_sweep"           # light sweep across image
    PARTICLE_FLOAT = "particle_float"     # floating particles + image
    DEPTH_PARALLAX = "depth_parallax"     # foreground/background parallax
    GLITCH_REVEAL = "glitch_reveal"       # glitch + reveal
    # Typography-only motion graphics
    TYPEWRITER = "typewriter"
    STROKE_DRAW = "stroke_draw"
    # Legacy compatibility (rendered as Remotion motion graphic, not FFmpeg)
    WORD_POP = "word_pop"
    LINE_REVEAL = "line_reveal"
    PARTICLE_BURST = "particle_burst"


# Map legacy BRollTemplate ids to the new BrollMotionStyle so old data still
# renders via the Remotion path with the closest matching animation.
LEGACY_TEMPLATE_TO_MOTION = {
    "word_pop_typography": BrollMotionStyle.WORD_POP,
    "line_reveal_typography": BrollMotionStyle.LINE_REVEAL,
    "particle_text_burst": BrollMotionStyle.PARTICLE_BURST,
}


class BrollPlacementMode(str, Enum):
    """3 B-Roll placement & compositing modes."""
    BEHIND_PERSON = "behind_person"  # Subject-aware B-roll behind speaker cutout (top safe-zone)
    SIDE_BROLL = "side_broll"        # Floating Picture-in-Picture card or split panel preserving 16:9
    FULL_BROLL = "full_broll"        # Full cutaway scene change (speaker temporarily hidden)


class VisualCategory(str, Enum):
    """Visual category for B-Roll asset resolution."""
    FOOTAGE = "footage"
    ICON = "icon"
    MOTION_GRAPHIC = "motion_graphic"
    REACTION = "reaction"


# ─── Core Entities ────────────────────────────────────────────────────────────

@dataclass
class Word:
    word: str
    start: float
    end: float
    highlight: bool = False


@dataclass
class Subtitle:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class BRollSuggestion:
    """B-Roll suggestion from AI analysis.

    Three placement modes (auto-chosen by AI or BrollSubjectAnalyzer):
      behind_person  — stock image/video BEHIND person cutout with subject-aware offset (person stays)
      side_broll     — floating Picture-in-Picture card or split preserving 16:9 context
      full_frame / full_broll — timeline splice: clip → stock video → clip (person gone)
    """
    at_time: float
    keyword: str
    template: str  # BRollTemplate value (legacy id, kept for DB compat)
    duration: float = 2.0
    reason: str = ""
    visual_category: VisualCategory = VisualCategory.FOOTAGE
    asset_result: Optional[AssetResult] = None
    splice_segment: object = None  # Optional[SpliceSegment] — forward ref, set by ClipScout flow
    # v3.1: Remotion motion-graphic style. When set, the suggestion is rendered
    # as a Remotion BrollLayer event (preview == final) instead of via the
    # legacy FFmpeg drawtext/overlay path.
    motion_style: Optional[BrollMotionStyle] = None
    # behind_person | side_broll | full_frame | full_broll
    placement: str = ""
    # AI-aware composition metadata
    subject_bbox: Optional[list[float]] = None  # [bx1, by1, bx2, by2] normalized
    smart_crop_x: Optional[int] = None
    smart_crop_y: Optional[int] = None
    layout_mode: Optional[str] = None
    search_queries: Optional[list[str]] = None
    subtitle_text: str = ""


@dataclass
class Clip:
    rank: int
    score: int
    start: float
    end: float
    hook: str
    reason: str
    subtitles: list[Subtitle] = field(default_factory=list)
    broll_suggestions: list[BRollSuggestion] = field(default_factory=list)
    # Sparse AI-selected cinematic text events.  Kept separate from subtitles
    # so hiding an ordinary caption never changes its Whisper timing.
    text_emphasis_events: list[dict] = field(default_factory=list)
    # Top-behind-subject overlay windows (image/video behind person, top ~50%).
    # Additive to full-frame B-roll splice; never co-timed with text emphasis.
    top_overlay_events: list[dict] = field(default_factory=list)
    # Noun image+text cards — small rounded photo + label (AI visual entities).
    object_overlay_events: list[dict] = field(default_factory=list)
    # Dynamic AI visual entities (query_id/query_en) — no domain lexicon.
    visual_entities: list[dict] = field(default_factory=list)
    # Final HyperFrames hook/subtitle/polish render stamp.
    hyperframes_polish: dict | None = None


# ─── Creative Direction (v2.0 — per-job visual identity) ─────────────────────

@dataclass
class CreativeDirection:
    """Per-job visual identity applied consistently across all clips.

    Generated by Gemini during analysis to ensure visual cohesion.
    """
    # Color system
    primary_color: str = "#FFFFFF"           # Main text/accent color
    secondary_color: str = "#FFD700"         # Highlight/emphasis color
    background_accent: str = "#000000"       # B-roll/overlay background tint
    # Typography mood
    typography_mood: str = "bold_impact"      # bold_impact / elegant_minimal / playful / dramatic
    # Pacing & energy
    energy_level: str = "high"               # high / medium / chill
    transition_style: str = "fast_cuts"      # fast_cuts / smooth / kinetic
    # Audio mood
    music_mood: str = "energetic"            # energetic / chill / dramatic / suspense / none
    # Subtitle style hints
    subtitle_position: str = "bottom"        # top / center / bottom
    subtitle_uppercase: bool = False
    # Hook style
    hook_animation: str = "fade_scale"       # fade_scale / slide_up / glitch / typewriter

    @classmethod
    def from_dict(cls, data: dict) -> "CreativeDirection":
        """Create from Gemini response dict, ignoring unknown fields."""
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class AssetResult:
    """Resolved visual asset from Free Asset Fetcher."""
    local_path: str
    source_api: str           # "pexels" | "pixabay" | "iconify" | "lottie" | "giphy" | "fallback"
    license_type: str         # "pexels_license" | "pixabay_license" | "mit" | "giphy_non_commercial" | "none"
    original_url: str
    asset_format: str         # "video" | "png" | "svg" | "gif" | "lottie" | "text"
    asset_id: str = ""
    is_fallback: bool = False
    metadata: dict = field(default_factory=dict)

    VALID_SOURCES = ("pexels", "pixabay", "iconify", "lottie", "giphy", "fallback")
    VALID_FORMATS = ("video", "png", "svg", "gif", "lottie", "text")
    VALID_LICENSES = ("pexels_license", "pixabay_license", "mit", "giphy_non_commercial", "none")

    def __post_init__(self):
        if self.source_api not in self.VALID_SOURCES:
            raise ValueError(f"Invalid source_api: {self.source_api}. Must be one of {self.VALID_SOURCES}")
        if self.asset_format not in self.VALID_FORMATS:
            raise ValueError(f"Invalid asset_format: {self.asset_format}. Must be one of {self.VALID_FORMATS}")
        if self.license_type not in self.VALID_LICENSES:
            raise ValueError(f"Invalid license_type: {self.license_type}. Must be one of {self.VALID_LICENSES}")

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict for API responses and DB storage."""
        return {
            "local_path": self.local_path,
            "source_api": self.source_api,
            "license_type": self.license_type,
            "original_url": self.original_url,
            "asset_format": self.asset_format,
            "asset_id": self.asset_id,
            "is_fallback": self.is_fallback,
            "metadata": self.metadata,
        }

    @classmethod
    def fallback(cls) -> AssetResult:
        """Create a fallback result indicating text-overlay should be used."""
        return cls(
            local_path="",
            source_api="fallback",
            license_type="none",
            original_url="",
            asset_format="text",
            is_fallback=True,
        )


@dataclass
class ClipResult:
    version: str
    video_id: str
    language: str
    error: Optional[str]
    clips: list[Clip]


@dataclass
class Job:
    job_id: str
    youtube_url: str
    status: JobStatus = JobStatus.VALIDATING
    video_duration: Optional[float] = None
    render_progress: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Optional[dict] = None
    clips_data: Optional[dict] = None
    clips_total: int = 0
    clips_success: int = 0
    clips_failed: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # ─── v0.4 fields ──────────────────────────────────────────────────────
    style_preset: str = "bold_black"
    target_aspect_ratio: str = "9:16"
    hook_engine: str = "v3"  # "v2" (legacy) or "v3" (Browser Render Engine)
    hook_style: str = ""
    custom_style: Optional[dict] = None
    broll_enabled: bool = True
    autogrid_enabled: bool = True
    # Sub-types (default True for back-compat). Only applied when broll_enabled.
    broll_image_overlay: bool = True
    broll_behind_person: bool = True
    broll_video_footage: bool = True
    # Deprecated motion style (Remotion B-roll FX); unused when subtypes used.
    broll_motion_style: Optional[str] = None
    # ─── v3.0 Remotion fields ─────────────────────────────────────────────
    use_remotion: bool = False
    ai_layer_enabled: bool = False
    threejs_enabled: bool = False
    scene_graphs: Optional[dict] = None
    remotion_quality: str = "medium"
    user_id: Optional[int] = None
    pipeline_version: str = "v1"  # "v1" (Gemini) or "v2" (Groq)
    video_title: Optional[str] = None


# ─── Aspect Ratio Routing ─────────────────────────────────────────────────────

@dataclass
class PipelineFlags:
    """Flags set by AspectRatioRouter (Step 6) controlling pipeline behavior."""
    yolo_enabled: bool = True
    autocenter_enabled: bool = True
    autogrid_enabled: bool = True
    hook_render_mode: str = "text_behind"  # "text_behind" or "text_front"

    @classmethod
    def for_portrait(cls, autogrid: bool = True) -> "PipelineFlags":
        """9:16 — full YOLO pipeline."""
        return cls(
            yolo_enabled=True,
            autocenter_enabled=True,
            autogrid_enabled=autogrid,
            hook_render_mode="text_behind",
        )

    @classmethod
    def for_landscape(cls) -> "PipelineFlags":
        """16:9 / 1:1 — no YOLO, no autocenter, no autogrid; raw framing."""
        return cls(
            yolo_enabled=False,
            autocenter_enabled=False,
            autogrid_enabled=False,
            hook_render_mode="text_front",
        )


# ─── Pipeline Infrastructure Entities ─────────────────────────────────────────

@dataclass
class CleanupResult:
    files_deleted: int
    files_failed: int
    failed_paths: list[str] = field(default_factory=list)


@dataclass
class FFprobeResult:
    valid: bool
    duration: float
    has_video: bool
    has_audio: bool
    error: Optional[str] = None


@dataclass
class ResourceStatus:
    disk_free_gb: float
    ram_available_gb: float
    cpu_percent: float
    is_sufficient: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class ResourceSummary:
    job_id: str
    peak_ram_percent: float
    peak_cpu_percent: float
    min_disk_free_gb: float
    total_duration_seconds: float
    samples_collected: int


@dataclass
class CheckpointData:
    job_id: str
    step_number: int
    step_name: str
    timestamp: str
    output_data: Any


@dataclass
class CachedJobResult:
    job_id: str
    status: str
    output_path: str
    caption_response: Optional[str]
    requested_at: str
    is_cached: bool = True


@dataclass
class TranscriptCacheEntry:
    video_id: str
    transcript_json: str
    whisper_model_hash: str
    language: str
    duration_seconds: float
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class ScaleRecommendation:
    queue_depth: int
    current_workers: int
    recommended_workers: int
    recommendation: str


# ─── V2 Pipeline Entities (Groq-based, Non-Premium) ──────────────────────────

@dataclass
class TranscriptSegment:
    """A single transcript segment with text and timing."""
    text: str
    start: float
    end: float


@dataclass
class TranscriptResult:
    """Result from TAHAP 1: Ingestion & Text Extraction."""
    segments: list[TranscriptSegment]
    source: str                  # "youtube_api" | "groq_whisper"
    language: str                # detected/specified language code
    total_duration: float
    full_text: str = ""          # concatenated text for LLM analysis

    def __post_init__(self):
        if not self.full_text and self.segments:
            self.full_text = " ".join(seg.text for seg in self.segments)


@dataclass
class AudioSlice:
    """A sliced audio segment extracted for word-level transcription (TAHAP 3)."""
    clip_rank: int
    audio_path: str              # path to extracted WAV file
    original_start: float        # highlight start from Groq LLM
    original_end: float          # highlight end from Groq LLM
    padded_start: float          # with -padding applied
    padded_end: float            # with +padding applied
    duration: float              # padded_end - padded_start


@dataclass
class HighlightCandidate:
    """A single highlight candidate from Groq LLM analysis (TAHAP 2)."""
    rank: int
    start: float
    end: float
    score: int
    hook: str
    reason: str
    content_type: str = "storytelling"      # storytelling/tutorial/rant/debate
    speaker_energy: str = "medium"          # high/medium/low
    hook_alt: str = ""


@dataclass
class HighlightAnalysisResult:
    """Combined result from TAHAP 2: AI Highlight Analysis."""
    clips: list[HighlightCandidate]
    creative_direction: dict           # raw dict → will be mapped to CreativeDirection
    broll_suggestions: dict            # {clip_rank_str: [{at_time, keyword, template, ...}]}
    model_used: str = ""               # which Groq model was used
    chunks_processed: int = 0          # how many transcript chunks were analyzed


@dataclass
class VADResult:
    """Result from TAHAP 5: Voice Activity Detection refinement."""
    original_start: float
    original_end: float
    final_start: float
    final_end: float
    shift_start_ms: float = 0.0        # how much start was shifted (ms)
    shift_end_ms: float = 0.0          # how much end was shifted (ms)
    used_fallback: bool = False        # True if VAD couldn't find silence


@dataclass
class DashboardMetrics:
    active_jobs: int
    queued_jobs: int
    completed_jobs_24h: int
    failed_jobs_24h: int
    average_processing_time_seconds: float
    cpu_percent: float
    ram_percent: float
    disk_free_gb: float
    step_durations: dict
    scaling: Optional[ScaleRecommendation] = None


@dataclass
class ConcurrencyConfig:
    env: str
    max_concurrent_jobs: int
    max_whisper_parallel: int

    @classmethod
    def from_env(cls) -> "ConcurrencyConfig":
        import os
        env = os.getenv("PIPELINE_ENV", "local").lower()
        if env not in ("production", "local"):
            env = "local"
        defaults = {"production": (4, 2), "local": (1, 1)}
        default_jobs, default_whisper = defaults[env]

        def _parse_int(var_name: str, default: int) -> int:
            val = os.getenv(var_name)
            if val is None:
                return default
            try:
                n = int(val)
                return n if 1 <= n <= 16 else 1
            except (ValueError, TypeError):
                return 1

        return cls(
            env=env,
            max_concurrent_jobs=_parse_int("MAX_CONCURRENT_JOBS", default_jobs),
            max_whisper_parallel=_parse_int("MAX_WHISPER_PARALLEL", default_whisper),
        )


# ─── Visual Style Entities ────────────────────────────────────────────────────

@dataclass
class SubtitleStyleConfig:
    """Configuration for subtitle word-by-word rendering (FFmpeg drawtext / Skia / Remotion)."""
    enabled: bool = True
    font_family: str = "Poppins"
    font_size: int = 34
    font_weight: str = "Bold"
    uppercase: bool = False
    capitalize: bool = False
    italic: bool = False
    text_opacity: float = 1.0
    text_align: str = "center"  # left | center | right
    letter_spacing: float = 0.0
    color: str = "#FFFFFF"
    highlight_color: str = "#FFCC00"
    highlight_words: bool = True
    highlight_words_list: list[str] = field(default_factory=list)
    background_color: str = ""
    background_opacity: float = 0.3
    stroke_enabled: bool = True
    stroke_color: str = "#000000"
    stroke_width: int = 3
    shadow_enabled: bool = False
    shadow_color: str = "black@0.7"
    shadow_blur: int = 4
    shadow_opacity: float = 0.8
    shadow_x: int = 1
    shadow_y: int = 2
    position: str = "bottom"
    position_y: str = ""
    position_x: str = "(w-text_w)/2"
    max_words_per_line: int = 3
    word_spacing: int = 6
    line_spacing: float = 1.3
    padding_bottom: int = 120
    start_offset: float = 0.0
    timing_offset: float = 0.0
    word_padding: float = 0.05
    line_transition: str = "word_pop"  # word_pop | emphasis | line_reveal | karaoke | typing
    animation_style: str = "pop"       # pop | fade | slide | none
    animation_speed: float = 1.0
    fade_in: float = 0.1
    fade_out: float = 0.1
    highlight_style: str = "scale"
    highlight_scale: float = 1.2
    highlight_bold: bool = True
    highlight_glow: bool = False
    highlight_glow_color: str = "#00FFFF"
    # Dual Style
    dual_style_enabled: bool = False
    highlight_font_family: str = ""
    highlight_font_weight: str = ""
    highlight_font_size: int = 0
    # Additional styling and preset compatibility fields
    engine: str = "remotion"
    stylePreset: str = ""
    style_id: str = ""
    id: str = ""
    hf_template: str = ""
    template_mode: str = ""
    preset: str = ""
    effect: str = ""
    glow_enabled: bool = False
    glow_color: str = ""
    glow_radius: int = 0
    gradient_enabled: bool = False
    gradient_from: str = ""
    gradient_to: str = ""
    active_scale: float = 1.0
    bg_enabled: bool = False
    bg_color: str = ""
    bg_opacity: float = 0.0
    bg_radius: int = 12
    bg_padding: int = 24
    bg_padding_x: int = 24
    bg_padding_y: int = 14
    bg_blur: bool = False
    box_enabled: bool = False
    box_color: str = ""
    box_opacity: float = 0.0
    box_border_width: int = 0
    box_border_color: str = ""
    box_corner_radius: int = 0
    box_padding_x: int = 0
    box_padding_y: int = 0
    subject_aware_positioning: bool = False
    safe_area_margin: int = 40
    max_width_pct: int = 90
    # Badge and Footer text components (for news portal, speech notch, comment reply, etc.)
    badge_enabled: bool = True
    badge_text: str = ""
    footer_enabled: bool = True
    footer_text: str = ""

    @classmethod
    def from_dict(cls, data: dict | Any) -> SubtitleStyleConfig:
        if isinstance(data, cls):
            return data
        if not isinstance(data, dict):
            return cls()
        known = {f.name for f in fields(cls)}
        # Map camelCase to snake_case
        camel_map = {
            "fontFamily": "font_family",
            "fontSize": "font_size",
            "fontWeight": "font_weight",
            "letterSpacing": "letter_spacing",
            "lineHeight": "line_spacing",
            "highlightColor": "highlight_color",
            "highlightScale": "highlight_scale",
            "highlightBold": "highlight_bold",
            "highlightStyle": "highlight_style",
            "highlightGlow": "highlight_glow",
            "highlightGlowColor": "highlight_glow_color",
            "highlightWords": "highlight_words_list",
            "dualStyleEnabled": "dual_style_enabled",
            "highlightFontFamily": "highlight_font_family",
            "highlightFontSize": "highlight_font_size",
            "highlightFontWeight": "highlight_font_weight",
            "bgEnabled": "bg_enabled",
            "bgColor": "bg_color",
            "bgOpacity": "bg_opacity",
            "bgRadius": "bg_radius",
            "bgPadding": "bg_padding",
            "positionY": "position_y",
            "subtitle_position_y": "position_y",
            "strokeEnabled": "stroke_enabled",
            "strokeColor": "stroke_color",
            "strokeWidth": "stroke_width",
            "shadowEnabled": "shadow_enabled",
            "shadowColor": "shadow_color",
            "shadowBlur": "shadow_blur",
            "maxWordsPerLine": "max_words_per_line",
            "wordSpacing": "word_spacing",
            "animationStyle": "animation_style",
            "animationSpeed": "animation_speed",
            "lineTransition": "line_transition",
            "glowEnabled": "glow_enabled",
            "glowColor": "glow_color",
            "gradientEnabled": "gradient_enabled",
            "gradientFrom": "gradient_from",
            "gradientTo": "gradient_to",
            "subjectAwarePositioning": "subject_aware_positioning",
            "safeAreaMargin": "safe_area_margin",
            "maxWidthPct": "max_width_pct",
            "badgeEnabled": "badge_enabled",
            "badgeText": "badge_text",
            "footerEnabled": "footer_enabled",
            "footerText": "footer_text",
        }
        normalized = {}
        for k, v in data.items():
            mapped_k = camel_map.get(k, k)
            normalized[mapped_k] = v

        filtered = {k: v for k, v in normalized.items() if k in known}
        # map common aliases
        if "text_color" in data and "color" not in filtered:
            filtered["color"] = data["text_color"]
        if "stylePreset" in data and "stylePreset" not in filtered:
            filtered["stylePreset"] = str(data["stylePreset"])
        if "highlight_words" not in filtered:
            filtered["highlight_words"] = bool(data.get("highlight_words", True))
        return cls(**filtered)


@dataclass
class HookStyleConfig:
    """Hook style configuration — supports both v2 (legacy) and v3 (browser) engines."""
    # ─── Common fields ────────────────────────────────────────────────────
    engine: str = "v3"  # "v2" or "v3"
    duration_ms: int = 3000
    render_mode: str = "text_behind"  # "text_behind" or "text_front"
    requires_segmentation: bool = True

    # ─── v3 Browser Render Engine fields ──────────────────────────────────
    component: str = "SlidePunchHook"  # React component name
    props: dict = field(default_factory=dict)
    framer_motion: dict = field(default_factory=dict)

    # ─── v2 Legacy fields (kept for backward compat) ─────────────────────
    font_family: str = "Anton"
    font_size: int = 80
    color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    stroke_width: int = 4
    uppercase: bool = True
    animation: str = "zoom_punch"
    position: str = "center"
    hf_template: str = ""
    template_mode: str = ""

    @classmethod
    def from_dict(cls, data: dict | Any) -> HookStyleConfig:
        if isinstance(data, cls):
            return data
        if not isinstance(data, dict):
            return cls()
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class StylePreset:
    """Visual style preset combining hook + subtitle configs."""
    id: str
    name: str
    hook: HookStyleConfig
    subtitle: SubtitleStyleConfig
    hook_render_path: str = "overlay"
    raw_hook_json: Optional[dict] = None


# ─── ClipScout B-Roll Splice Entities ─────────────────────────────────────────


@dataclass
class VideoCandidate:
    """A video result from ClipScout API, before AI selection."""
    id: str = ""
    title: str = ""
    thumbnail_url: str = ""
    source_url: str = ""
    embed_url: str = ""
    platform: str = "pexels"           # "pexels", "pixabay", "youtube"
    license: str = "royalty-free"      # "royalty-free", "standard"
    duration_seconds: int = 0
    start_timestamp: int = 0           # Relevant for YouTube (start point in source video)
    relevance_score: float = 1.0
    transcript_snippet: str = ""
    transcript_reason: str = ""
    channel_or_author: str = ""
    preview_url: str = ""              # Optional alias for preview/thumbnail URL

    def __post_init__(self):
        if not self.thumbnail_url and self.preview_url:
            self.thumbnail_url = self.preview_url
        elif not self.preview_url and self.thumbnail_url:
            self.preview_url = self.thumbnail_url


@dataclass
class SpliceSegment:
    """A prepared footage segment ready for splicing into a clip."""
    footage_path: str       # Path to processed footage file (1080x1920 H.264)
    at_time: float          # When in the clip to start the splice (seconds)
    duration: float         # Duration of the splice (seconds)
    keyword: str            # B-roll keyword for logging/debugging
    source_id: str          # VideoCandidate.id for traceability
    platform: str           # Source platform for logging
