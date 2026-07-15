"""Pydantic schemas for job API endpoints."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class JobOptionsBase(BaseModel):
    force_reprocess: bool = False
    style_preset: str = ""
    target_aspect_ratio: str = "9:16"  # "9:16", "16:9", "1:1"
    hook_engine: str = "v3"  # "v2" (legacy) or "v3" (Browser Render Engine)
    hook_style: str = ""  # e.g. "slide_punch_framer"
    broll_enabled: bool = False  # B-Roll disabled by default
    autogrid_enabled: bool = False  # Enable multi-speaker grid (9:16 only)
    text_emphasis_enabled: bool = False  # Optional sparse AI cinematic text
    text_emphasis_style_config: Optional[dict] = None
    custom_style: Optional[dict] = None
    # v3.0 Remotion fields
    use_remotion: Optional[bool] = None  # Override USE_REMOTION setting
    ai_layer_enabled: Optional[bool] = None  # Override REMOTION_ENABLE_AI_LAYER
    threejs_enabled: Optional[bool] = None  # Override REMOTION_ENABLE_THREEJS
    remotion_quality: Optional[str] = None  # "low", "medium", "high"
    # Full style configs from Custom Style Editor
    hook_style_config: Optional[dict] = None
    subtitle_style_config: Optional[dict] = None
    processing_mode: str = "analyze"  # analyze viral moments | direct full-video edit
    @field_validator("target_aspect_ratio")
    @classmethod
    def valid_aspect(cls, v: str) -> str:
        if v not in ("9:16", "16:9", "1:1"):
            raise ValueError("aspect_ratio harus '9:16', '16:9', atau '1:1'")
        return v

    @field_validator("hook_engine")
    @classmethod
    def valid_engine(cls, v: str) -> str:
        if v not in ("v2", "v3"):
            raise ValueError("hook_engine harus 'v2' atau 'v3'")
        return v
    
    @field_validator("remotion_quality")
    @classmethod
    def valid_quality(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("low", "medium", "high"):
            raise ValueError("remotion_quality harus 'low', 'medium', atau 'high'")
        return v

    @field_validator("processing_mode")
    @classmethod
    def valid_processing_mode(cls, v: str) -> str:
        if v not in ("analyze", "direct"):
            raise ValueError("processing_mode harus 'analyze' atau 'direct'")
        return v

    @field_validator("text_emphasis_style_config")
    @classmethod
    def valid_text_emphasis_style(cls, value: Optional[dict]) -> Optional[dict]:
        if value is None:
            return None
        allowed_effects = {"auto", "behind_person", "spotlight", "side_label"}
        effect = str(value.get("effectMode", "auto"))
        if effect not in allowed_effects:
            raise ValueError("effectMode harus auto, behind_person, spotlight, atau side_label")
        return value


class CreateJobRequest(JobOptionsBase):
    youtube_url: str

    @field_validator("youtube_url")
    @classmethod
    def url_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("URL tidak boleh kosong")
        return v.strip()


class UploadJobOptions(JobOptionsBase):
    force_reprocess: bool = True
    custom_hook: Optional[str] = Field(default=None, max_length=500)

    @field_validator("custom_hook")
    @classmethod
    def normalize_custom_hook(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class JobResponse(BaseModel):
    job_id: str
    youtube_url: str
    source_type: str = "youtube"
    source_label: Optional[str] = None
    status: str
    video_duration: Optional[float] = None
    render_progress: Optional[str] = None
    error_message: Optional[str] = None
    clips_data: Optional[Any] = None
    clips_total: int = 0
    clips_success: int = 0
    clips_failed: int = 0
    is_cached: bool = False
    # v0.4 fields
    style_preset: Optional[str] = None
    target_aspect_ratio: Optional[str] = None
    # v3.0 Remotion fields
    use_remotion: bool = False
    ai_layer_enabled: bool = False
    threejs_enabled: bool = False
    remotion_quality: str = "medium"
    # V2 pipeline
    pipeline_version: str = "v1"  # "v1" (Gemini) or "v2" (Groq)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class JobErrorResponse(BaseModel):
    job_id: str
    error_message: Optional[str] = None
    error_details: Optional[dict] = None


class ClipDataResponse(BaseModel):
    """Response untuk Remotion — berisi clip data lengkap dengan subtitle dan hook."""
    job_id: str
    status: str
    clips: Optional[list[dict]] = None
    video_url: Optional[str] = None


class ErrorResponse(BaseModel):
    detail: str
