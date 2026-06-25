"""OverlapDetector — detects and resolves overlapping clip timestamps after padding."""
import copy
import logging
from typing import List

from src.domain.entities import Clip

logger = logging.getLogger(__name__)


class OverlapDetector:
    """Detects and resolves overlapping clip timestamps after padding.
    
    Merge if overlap > 3s, split at midpoint if overlap <= 3s.
    Repeat until no overlaps or max 50 iterations.
    """

    MERGE_THRESHOLD = 3.0  # seconds — overlaps > this get merged
    MIN_CLIP_DURATION = 0.5  # seconds — clips shorter than this get discarded
    MAX_ITERATIONS = 50

    def resolve_overlaps(self, clips: List[Clip]) -> List[Clip]:
        """Sort, detect, merge/split overlapping clips iteratively.
        
        Args:
            clips: List of Clip entities with start/end times.
            
        Returns:
            Resolved list with no overlaps (or best effort after MAX_ITERATIONS).
        """
        if len(clips) <= 1:
            return clips

        # Sort by start time
        result = sorted(copy.deepcopy(clips), key=lambda c: c.start)

        for iteration in range(self.MAX_ITERATIONS):
            changed = False
            new_result = []
            i = 0

            while i < len(result):
                if i == len(result) - 1:
                    new_result.append(result[i])
                    i += 1
                    continue

                current = result[i]
                next_clip = result[i + 1]

                overlap = current.end - next_clip.start
                if overlap <= 0:
                    # No overlap
                    new_result.append(current)
                    i += 1
                    continue

                changed = True

                if overlap > self.MERGE_THRESHOLD:
                    # Merge: take earlier start, later end, higher score metadata
                    merged = self._merge_clips(current, next_clip)
                    logger.info(
                        "overlap_merge",
                        extra={
                            "iteration": iteration,
                            "clip_a_start": current.start,
                            "clip_a_end": current.end,
                            "clip_b_start": next_clip.start,
                            "clip_b_end": next_clip.end,
                            "merged_start": merged.start,
                            "merged_end": merged.end,
                        },
                    )
                    new_result.append(merged)
                    i += 2  # Skip both clips
                else:
                    # Split at midpoint
                    midpoint = next_clip.start + (overlap / 2)
                    current.end = midpoint
                    next_clip.start = midpoint
                    new_result.append(current)
                    # Don't skip next_clip — let it be processed in next iteration
                    i += 1

            result = new_result

            # Remove short clips
            result = [c for c in result if (c.end - c.start) >= self.MIN_CLIP_DURATION]

            if not changed:
                break
        else:
            logger.warning(
                "overlap_max_iterations",
                extra={"max_iterations": self.MAX_ITERATIONS, "remaining_clips": len(result)},
            )

        return result

    def _merge_clips(self, clip_a: Clip, clip_b: Clip) -> Clip:
        """Merge two clips into one.
        
        Takes earlier start, later end.
        Preserves metadata from higher-scored clip.
        If equal scores, prefer earlier original start_time.
        """
        # Determine which clip's metadata to keep
        if clip_a.score > clip_b.score:
            primary = clip_a
        elif clip_b.score > clip_a.score:
            primary = clip_b
        else:
            # Equal scores — prefer earlier start time
            primary = clip_a if clip_a.start <= clip_b.start else clip_b

        merged = copy.deepcopy(primary)
        merged.start = min(clip_a.start, clip_b.start)
        merged.end = max(clip_a.end, clip_b.end)

        return merged
