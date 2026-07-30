"""AspectRatioRouter — Step 6: Set pipeline flags based on target aspect ratio.

Rules:
- 9:16 → YOLO ON, AutoCenter ON, AutoGrid optional, hook: text_behind
- 16:9 / 1:1 → YOLO OFF, AutoCenter OFF, AutoGrid OFF, raw framing, hook: text_front
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
            autogrid_enabled: Multi-speaker grid request (honoured only for 9:16)

        Returns:
            PipelineFlags with appropriate settings
        """
        if aspect_ratio == "9:16":
            logger.info(
                f"aspect_ratio_router: 9:16 → YOLO ON, autocenter ON, "
                f"autogrid={bool(autogrid_enabled)}"
            )
            return PipelineFlags.for_portrait(autogrid=bool(autogrid_enabled))

        logger.info(
            f"aspect_ratio_router: {aspect_ratio} → YOLO/autocenter/autogrid OFF, raw framing"
        )
        return PipelineFlags.for_landscape()
