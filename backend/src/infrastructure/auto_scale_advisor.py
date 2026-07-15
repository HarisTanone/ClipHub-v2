"""AutoScaleAdvisor — evaluates queue depth and emits scaling recommendations."""
import logging
import math
import os
from typing import Optional

from src.domain.entities import ScaleRecommendation

logger = logging.getLogger(__name__)


class AutoScaleAdvisor:
    """Evaluates queue depth and recommends worker scaling.
    
    Formula: recommended_workers = min(ceil(queue_depth / 5), 10)
    Scale-up when queue > SCALE_UP_THRESHOLD (default 15)
    Scale-down when queue < SCALE_DOWN_THRESHOLD for 5+ consecutive cycles
    """

    EVAL_INTERVAL = 60  # seconds
    MAX_WORKERS = 10

    def __init__(self):
        self._scale_up_threshold = self._parse_int_env("SCALE_UP_THRESHOLD", 15)
        self._scale_down_threshold = self._parse_int_env("SCALE_DOWN_THRESHOLD", 3)
        self._consecutive_low_cycles = 0
        self._last_recommendation: str = ""
        self._stable_cycles_since_log: int = 0
        # Only log every N stable cycles to reduce noise (4 workers × 60s = a lot of logs)
        self._stable_log_interval: int = 10  # Log stable state every 10 minutes

        logger.info("auto_scale_init", extra={
            "scale_up_threshold": self._scale_up_threshold,
            "scale_down_threshold": self._scale_down_threshold,
        })

    def evaluate(self, queue_depth: int, current_workers: int = 1) -> ScaleRecommendation:
        """Calculate scaling recommendation based on queue depth.
        
        Args:
            queue_depth: Current number of pending jobs.
            current_workers: Current number of active workers.
            
        Returns:
            ScaleRecommendation with recommended_workers and direction.
        """
        recommended = min(math.ceil(queue_depth / 5), self.MAX_WORKERS) if queue_depth > 0 else 1

        if queue_depth > self._scale_up_threshold:
            self._consecutive_low_cycles = 0
            recommendation = "scale_up"
        elif queue_depth < self._scale_down_threshold:
            self._consecutive_low_cycles += 1
            if self._consecutive_low_cycles >= 5:
                recommendation = "scale_down"
                recommended = 1
            else:
                recommendation = "stable"
        else:
            self._consecutive_low_cycles = 0
            recommendation = "stable"

        result = ScaleRecommendation(
            queue_depth=queue_depth,
            current_workers=current_workers,
            recommended_workers=recommended,
            recommendation=recommendation,
        )

        # Only log when state changes or periodically for stable state
        state_changed = recommendation != self._last_recommendation
        self._last_recommendation = recommendation

        if state_changed or recommendation != "stable":
            self._stable_cycles_since_log = 0
            logger.info("scale_evaluation", extra={
                "queue_depth": queue_depth,
                "recommended_workers": recommended,
                "recommendation": recommendation,
                "consecutive_low": self._consecutive_low_cycles,
            })
        else:
            self._stable_cycles_since_log += 1
            if self._stable_cycles_since_log >= self._stable_log_interval:
                self._stable_cycles_since_log = 0
                logger.debug("scale_evaluation", extra={
                    "queue_depth": queue_depth,
                    "recommended_workers": recommended,
                    "recommendation": recommendation,
                    "consecutive_low": self._consecutive_low_cycles,
                })

        return result

    @staticmethod
    def _parse_int_env(var_name: str, default: int) -> int:
        """Parse positive integer from env var."""
        val = os.getenv(var_name)
        if val is None:
            return default
        try:
            n = int(val)
            if n <= 0:
                return default
            return n
        except (ValueError, TypeError):
            return default
