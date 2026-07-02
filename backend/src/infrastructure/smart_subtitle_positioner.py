"""Smart Subtitle Positioner — Face-aware subtitle placement.

Avoids overlapping faces/gestures by dynamically adjusting subtitle Y position.

Safe Zone System:
┌─────────┐
│ Header  │  0-15%   (title/logo area)
├─────────┤
│ Face    │  15-55%  (primary content — NEVER place subtitle here)
├─────────┤
│ Gesture │  55-75%  (hands/body — avoid if possible)
├─────────┤
│ Subtitle│  75-95%  (default subtitle zone)
└─────────┘

Level 1: Default bottom center
Level 2: If face overlaps subtitle zone → move up
Level 3: Multi-person → limit subtitle width to 70%
Level 4: Keyword highlight sizing (handled by Remotion)
Level 5: Safe zone enforcement with dynamic repositioning
"""
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SafeZone:
    """Frame divided into semantic zones."""
    header_end: float = 0.15       # 0-15%
    face_end: float = 0.55         # 15-55%
    gesture_end: float = 0.75      # 55-75%
    subtitle_start: float = 0.75   # 75-95%
    subtitle_end: float = 0.95     # Bottom boundary


@dataclass
class SubtitlePosition:
    """Computed subtitle position for a clip."""
    position_y: float              # 0-100% (CSS-style)
    max_width_pct: float           # Max width percentage
    reason: str                    # Why this position
    level: int                     # Which level rule applied


class SmartSubtitlePositioner:
    """Compute optimal subtitle position based on detected persons."""

    SAFE_ZONE = SafeZone()

    def compute_position(
        self,
        person_boxes: list[dict],
        frame_width: int,
        frame_height: int,
        person_count: int = 1,
    ) -> SubtitlePosition:
        """Compute optimal subtitle Y position.

        Args:
            person_boxes: List of {x1, y1, x2, y2} normalized (0-1) or pixel values
            frame_width: Video frame width
            frame_height: Video frame height
            person_count: Number of detected persons

        Returns:
            SubtitlePosition with Y percentage and max width
        """
        if not person_boxes:
            # Level 1: No detection — default bottom
            return SubtitlePosition(
                position_y=85.0,
                max_width_pct=90.0,
                reason="default_bottom",
                level=1,
            )

        # Normalize boxes to 0-1 if in pixel coordinates
        normalized = self._normalize_boxes(person_boxes, frame_width, frame_height)

        # Check if any person's body extends into subtitle zone
        subtitle_zone_start = self.SAFE_ZONE.subtitle_start
        face_overlap = False
        body_in_subtitle_zone = False

        for box in normalized:
            box_bottom = box["y2"]
            box_top = box["y1"]

            # Face region (top 40% of person box)
            face_bottom_y = box_top + (box_bottom - box_top) * 0.4

            # Does face extend into subtitle area?
            if face_bottom_y > subtitle_zone_start:
                face_overlap = True

            # Does body extend into subtitle area?
            if box_bottom > subtitle_zone_start:
                body_in_subtitle_zone = True

        # Level 5: Face overlaps subtitle zone — move subtitle UP significantly
        if face_overlap:
            # Find safe Y above all faces
            highest_face_bottom = max(
                box["y1"] + (box["y2"] - box["y1"]) * 0.4
                for box in normalized
            )
            # Place subtitle just below face zone but above gesture
            safe_y = min(highest_face_bottom * 100 + 5, 70.0)
            return SubtitlePosition(
                position_y=safe_y,
                max_width_pct=80.0 if person_count >= 2 else 90.0,
                reason="face_overlap_shift_up",
                level=5,
            )

        # Level 2: Body in subtitle zone — nudge up slightly
        if body_in_subtitle_zone:
            return SubtitlePosition(
                position_y=75.0,  # Upper bottom
                max_width_pct=85.0 if person_count >= 2 else 90.0,
                reason="body_overlap_nudge",
                level=2,
            )

        # Level 3: Multi-person — limit width
        if person_count >= 2:
            return SubtitlePosition(
                position_y=85.0,
                max_width_pct=70.0,
                reason="multi_person_width_limit",
                level=3,
            )

        # Level 1: Default — nothing in the way
        return SubtitlePosition(
            position_y=85.0,
            max_width_pct=90.0,
            reason="default_clear",
            level=1,
        )

    def compute_for_clip(
        self,
        detections_per_frame: list[list[dict]],
        frame_width: int,
        frame_height: int,
    ) -> SubtitlePosition:
        """Compute a single stable position for entire clip.

        Uses majority voting across frames to avoid jumping.
        """
        if not detections_per_frame:
            return SubtitlePosition(85.0, 90.0, "no_detections", 1)

        positions = []
        for frame_dets in detections_per_frame:
            person_count = len(frame_dets)
            pos = self.compute_position(frame_dets, frame_width, frame_height, person_count)
            positions.append(pos)

        # Use median Y position for stability
        y_values = [p.position_y for p in positions]
        width_values = [p.max_width_pct for p in positions]
        levels = [p.level for p in positions]

        median_y = float(np.median(y_values))
        median_width = float(np.median(width_values))
        max_level = max(levels)

        # Round to nearest 5% for clean positioning
        final_y = round(median_y / 5) * 5
        final_y = max(65.0, min(90.0, final_y))

        reasons = set(p.reason for p in positions)
        reason = f"median_from_{len(positions)}_frames"
        if "face_overlap_shift_up" in reasons:
            reason = "face_aware_shifted"

        return SubtitlePosition(
            position_y=final_y,
            max_width_pct=median_width,
            reason=reason,
            level=max_level,
        )

    def _normalize_boxes(self, boxes: list[dict], w: int, h: int) -> list[dict]:
        """Normalize pixel coordinates to 0-1 range."""
        normalized = []
        for box in boxes:
            x1 = box.get("x1", 0)
            y1 = box.get("y1", 0)
            x2 = box.get("x2", 0)
            y2 = box.get("y2", 0)

            # If values > 1, assume pixel coordinates
            if x2 > 1 or y2 > 1:
                normalized.append({
                    "x1": x1 / w,
                    "y1": y1 / h,
                    "x2": x2 / w,
                    "y2": y2 / h,
                })
            else:
                normalized.append(box)
        return normalized

    # ─── Grid-Aware Subtitle Positioning ──────────────────────────────────

    def compute_for_grid(self, grid_layout: str, person_count: int = 2) -> SubtitlePosition:
        """Compute subtitle position for grid layouts.

        When grid is active, subtitles should be:
        - Centered horizontally (full width available since each panel shows 1 person)
        - Positioned at bottom of the ACTIVE SPEAKER panel (top panel)

        Grid layouts:
        - "speaker_emphasis": 60% top (active) / 40% bottom (listener)
          → subtitle at ~52% (bottom of active panel = 60%, with margin)
        - "double": 50% top / 50% bottom
          → subtitle at ~43% (bottom of top panel = 50%, with margin)
        - "single" or None: normal positioning (no grid)

        Args:
            grid_layout: "speaker_emphasis", "double", or "single"
            person_count: Number of detected persons

        Returns:
            SubtitlePosition centered for the grid layout
        """
        if grid_layout == "speaker_emphasis":
            # Active speaker panel is top 60% (0-60% of output)
            # Place subtitle at bottom of active panel with margin
            return SubtitlePosition(
                position_y=52.0,       # Just above panel boundary (60% - 8% margin)
                max_width_pct=85.0,    # Wider allowed — no horizontal face conflict
                reason="grid_speaker_emphasis_centered",
                level=6,
            )
        elif grid_layout == "double":
            # Top panel is 50% (0-50% of output)
            # Place subtitle at bottom of top panel
            return SubtitlePosition(
                position_y=43.0,       # Just above panel boundary (50% - 7% margin)
                max_width_pct=85.0,
                reason="grid_double_centered",
                level=6,
            )
        else:
            # No grid — return default position
            return SubtitlePosition(
                position_y=85.0,
                max_width_pct=90.0,
                reason="no_grid_default",
                level=1,
            )
