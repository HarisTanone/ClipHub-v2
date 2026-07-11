"""AspectRatioRouter — Step 6: Set pipeline flags based on target aspect ratio.

Rules (per new_flow.md v0.4):
- 9:16 → YOLO segmentation ON, AutoCenter ON, AutoGrid ON (optional), hook: text_behind
- 16:9 → YOLO OFF, AutoCenter OFF, AutoGrid OFF, hook: text_front only
- 1:1  → fallback to 9:16 policy (conservative)
"""
import logging

from src.domain.entities import PipelineFlags
from src.domain.interfaces import IAspectRatioRouter

logger = logging.getLogger(__name__)


class AspectRatioRouter(IAspectRatioRouter):
    """Determines pipeline behavior based on target aspect ratio."""

    def route(self, aspect_ratio: str, autogrid_enabled: bool = False) -> PipelineFlags:
        """Return PipelineFlags controlling YOLO/AutoCenter/AutoGrid/HookMode.

        Args:
            aspect_ratio: "9:16", "16:9", or "1:1"
            autogrid_enabled: Whether multi-speaker grid is requested (from DB/job)

        Returns:
            PipelineFlags with appropriate settings
        """
        if aspect_ratio != "9:16":
            logger.info(f"aspect_ratio_router: {aspect_ratio} → detection OFF, native framing")
            return PipelineFlags.for_landscape()

        elif aspect_ratio == "9:16":
            logger.info(f"aspect_ratio_router: 9:16 → YOLO ON, autocenter ON, autogrid={autogrid_enabled}")
            return PipelineFlags.for_portrait(autogrid=autogrid_enabled)
