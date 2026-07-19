"""Remotion-specific interfaces — extends core domain interfaces for Remotion render engine."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass
from enum import Enum


class RemotionRenderStatus(str, Enum):
    """Status for Remotion render jobs."""
    QUEUED = "queued"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RemotionRenderProgress:
    """Progress tracking for Remotion render."""
    job_id: str
    clip_rank: int
    status: RemotionRenderStatus
    progress: float  # 0.0 - 1.0
    current_frame: int
    total_frames: int
    eta_seconds: Optional[float] = None
    error_message: Optional[str] = None


@dataclass
class RemotionRenderConfig:
    """Configuration for Remotion render."""
    concurrency: int = 2
    quality: str = "high"  # low, medium, high
    enable_threejs: bool = True
    enable_ai_layer: bool = True
    output_format: str = "mp4"  # mp4, webm
    codec: str = "h264"  # h264, vp8, vp9
    framerate: int = 30
    resolution: tuple[int, int] = (1080, 1920)  # width, height


@dataclass
class RemotionRenderRequest:
    """Request payload for Remotion render."""
    scene_graph: dict
    creative_direction: dict
    video_path: str
    output_path: str
    clip_rank: int
    config: RemotionRenderConfig


@dataclass
class RemotionRenderResult:
    """Result from Remotion render."""
    success: bool
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    render_time_seconds: Optional[float] = None
    file_size_bytes: Optional[int] = None


class IRemotionRenderer(ABC):
    """Remotion render engine adapter.
    
    Bridges Python backend to Node.js Remotion server via HTTP.
    Handles scene graph serialization, render progress tracking,
    and error handling.
    """
    
    @abstractmethod
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
        text_emphasis_events: Optional[list[dict]] = None,
        broll_events: Optional[list[dict]] = None,
    ) -> RemotionRenderResult:
        """Render full clip composition via Remotion.
        
        Args:
            scene_graph: Structured timeline with layers and events
            creative_direction: Visual identity (colors, typography, etc.)
            video_path: Path to input video clip
            output_path: Path for output rendered video
            clip_rank: Clip number (for logging/tracking)
            config: Optional render configuration
            broll_events: Remotion BrollEvent dicts (motion-graphic B-roll)
            
        Returns:
            RemotionRenderResult with success status and output path
        """
        ...
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if Remotion server is running and healthy.
        
        Returns:
            True if server responds to /health endpoint
        """
        ...
    
    @abstractmethod
    async def get_render_progress(self, job_id: str, clip_rank: int) -> RemotionRenderProgress:
        """Get render progress for ongoing job.
        
        Args:
            job_id: Job identifier
            clip_rank: Clip number
            
        Returns:
            RemotionRenderProgress with current status and ETA
        """
        ...
    
    @abstractmethod
    async def cancel_render(self, job_id: str, clip_rank: int) -> bool:
        """Cancel ongoing render.
        
        Args:
            job_id: Job identifier
            clip_rank: Clip number
            
        Returns:
            True if render was cancelled successfully
        """
        ...
    
    @abstractmethod
    async def start_server(self) -> bool:
        """Start Remotion server if not running.
        
        Spawns Node.js process for Remotion render server.
        
        Returns:
            True if server started successfully
        """
        ...
    
    @abstractmethod
    async def stop_server(self) -> bool:
        """Stop Remotion server.
        
        Returns:
            True if server stopped successfully
        """
        ...


class IRemotionCompositionBuilder(ABC):
    """Builds Remotion composition from scene graph.
    
    Transforms scene graph events into Remotion Sequence/Composition
    structure with proper timing and layering.
    """
    
    @abstractmethod
    def build_composition(
        self,
        scene_graph: dict,
        creative_direction: dict,
    ) -> dict:
        """Build Remotion composition structure.
        
        Args:
            scene_graph: Scene graph with layers and events
            creative_direction: Visual identity
            
        Returns:
            Remotion composition structure (for React props)
        """
        ...
    
    @abstractmethod
    def validate_scene_graph(self, scene_graph: dict) -> tuple[bool, list[str]]:
        """Validate scene graph structure for Remotion.
        
        Args:
            scene_graph: Scene graph to validate
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        ...


class IThreeJSAssetManager(ABC):
    """Manages Three.js assets for 3D layer.
    
    Handles loading, caching, and optimization of 3D models,
    textures, and shader effects.
    """
    
    @abstractmethod
    async def load_model(self, model_id: str) -> Optional[str]:
        """Load 3D model by ID.
        
        Args:
            model_id: Model identifier
            
        Returns:
            Path to loaded model or None if not found
        """
        ...
    
    @abstractmethod
    async def load_texture(self, texture_id: str) -> Optional[str]:
        """Load texture by ID.
        
        Args:
            texture_id: Texture identifier
            
        Returns:
            Path to loaded texture or None if not found
        """
        ...
    
    @abstractmethod
    async def get_shader_effect(self, effect_id: str) -> Optional[dict]:
        """Get shader effect configuration.
        
        Args:
            effect_id: Effect identifier (e.g., 'particle_burst', 'glitch')
            
        Returns:
            Shader effect configuration dict or None
        """
        ...


class IAIAssetGenerator(ABC):
    """Generates AI assets for Remotion compositions.
    
    Optional layer for AI-generated backgrounds, effects,
    and dynamic content.
    """
    
    @abstractmethod
    async def generate_background(
        self,
        prompt: str,
        style: str,
        resolution: tuple[int, int],
    ) -> Optional[str]:
        """Generate background image/video.
        
        Args:
            prompt: Text prompt for generation
            style: Style preset (e.g., 'cinematic', 'minimal')
            resolution: Output resolution (width, height)
            
        Returns:
            Path to generated asset or None
        """
        ...
    
    @abstractmethod
    async def generate_effect(
        self,
        effect_type: str,
        params: dict,
    ) -> Optional[dict]:
        """Generate effect configuration.
        
        Args:
            effect_type: Type of effect (e.g., 'particles', 'glow')
            params: Effect parameters
            
        Returns:
            Effect configuration dict or None
        """
        ...
