"""Preservation Property Tests — Legitimate Multi-Person Grid Layout Unchanged.

These tests verify that CURRENT CORRECT behavior is preserved after the ghost
detection fix is applied. They capture baseline behavior on UNFIXED code.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

EXPECTED on UNFIXED code: These tests PASS (captures correct baseline).
EXPECTED on FIXED code: These tests MUST STILL PASS (no regressions).
"""
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add backend to path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.infrastructure.person_tracker import BBox, TrackedDetection
from src.infrastructure.podcast_reframe_engine import PodcastReframeEngine


# ─── Constants ────────────────────────────────────────────────────────────────

FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
FRAME_DIAGONAL = (FRAME_WIDTH**2 + FRAME_HEIGHT**2) ** 0.5
TOTAL_FRAMES = 30  # Simulate 10 seconds at 3fps sampling


# ─── Helper Functions (reused from test_autogrid_ghost_detection.py) ──────────

def make_bbox(center_x: float, center_y: float, width: float, height: float) -> BBox:
    """Create a BBox from center + dimensions."""
    x1 = center_x - width / 2
    y1 = center_y - height / 2
    x2 = center_x + width / 2
    y2 = center_y + height / 2
    return BBox(x1=x1, y1=y1, x2=x2, y2=y2)


def make_tracked_detection(track_id: int, bbox: BBox, frame_idx: int) -> TrackedDetection:
    """Create a TrackedDetection instance."""
    return TrackedDetection(track_id=track_id, bbox=bbox, frame_idx=frame_idx)


def build_per_frame_tracked(
    track_configs: list,
    total_frames: int = TOTAL_FRAMES,
) -> list:
    """Build per_frame_tracked data from track configurations.

    Each track_config is a dict:
      - track_id: int
      - center_x: float (pixels)
      - center_y: float (pixels)
      - width: float (pixels)
      - height: float (pixels)
      - frame_presence: float (0.0 to 1.0, fraction of frames present)
      - jitter: float (optional, random positional jitter in pixels)
    """
    import random
    random.seed(42)

    per_frame_tracked = []
    for frame_idx in range(total_frames):
        frame_detections = []
        for config in track_configs:
            # Determine if this track appears in this frame
            presence_ratio = config.get("frame_presence", 1.0)
            # Use deterministic presence based on frame index
            frames_present = int(total_frames * presence_ratio)
            if frame_idx >= frames_present:
                continue

            jitter = config.get("jitter", 0.0)
            jitter_x = random.uniform(-jitter, jitter) if jitter > 0 else 0
            jitter_y = random.uniform(-jitter, jitter) if jitter > 0 else 0

            cx = config["center_x"] + jitter_x
            cy = config["center_y"] + jitter_y
            w = config["width"]
            h = config["height"]

            bbox = make_bbox(cx, cy, w, h)
            detection = make_tracked_detection(config["track_id"], bbox, frame_idx)
            frame_detections.append(detection)

        per_frame_tracked.append(frame_detections)

    return per_frame_tracked


def create_engine() -> PodcastReframeEngine:
    """Create PodcastReframeEngine instance without loading face detector."""
    with patch.object(PodcastReframeEngine, '_load_face_detector', return_value=False):
        engine = PodcastReframeEngine.__new__(PodcastReframeEngine)
        engine._face_detector = None
        engine._use_legacy_api = False
        engine._speaker_detector = None
        engine._tracker = None
        engine._hf_token = None
        engine._diarizer = None
        engine._face_mapper = None
        engine._result_builder = None
    return engine


def run_scenario(engine: PodcastReframeEngine, per_frame_tracked: list) -> dict:
    """Run per_frame_tracked through _build_position_model + _decide_autogrid_layout."""
    # Step 1: Build position model
    position_model = engine._build_position_model(
        per_frame_tracked=per_frame_tracked,
        width=FRAME_WIDTH,
        height=FRAME_HEIGHT,
    )

    # Step 2: Build tracked_data dict expected by _decide_autogrid_layout
    tracked_data = {
        "per_frame_tracked": per_frame_tracked,
        "person_count": position_model["person_count"],
        "position_targets": position_model["position_targets"],
        "position_target_profiles": position_model["position_target_profiles"],
        "track_to_position": position_model["track_to_position"],
    }

    # Step 3: Run layout decision (no speaker result for these tests)
    layout_result = engine._decide_autogrid_layout(
        tracked_data=tracked_data,
        speaker_result=None,
        width=FRAME_WIDTH,
        height=FRAME_HEIGHT,
    )

    return {
        "position_model": position_model,
        "layout_result": layout_result,
        "person_count": position_model["person_count"],
        "layout": layout_result["layout"],
    }


# ─── Test Cases ───────────────────────────────────────────────────────────────

class TestPreservationLegitimateMultiPerson:
    """Preservation: Legitimate multi-person split-grid layout must remain unchanged.

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

    These tests capture the CURRENT CORRECT behavior of the system for scenarios
    that do NOT involve ghost tracks. After the fix is applied, these tests must
    continue to pass — confirming no regressions in legitimate multi-person handling.
    """

    def setup_method(self):
        """Create engine instance for each test."""
        self.engine = create_engine()

    def test_legitimate_2person_split_grid(self):
        """Two real speakers with clear horizontal separation → layout="double".

        Scenario:
          - Track A: center_x=400, face_width=260px, present in 80%+ frames
          - Track B: center_x=1400, face_width=240px, present in 80%+ frames
          - Horizontal separation = 1000px = 52% of frame width (>20% threshold)
          - Face size ratio = 240/260 ≈ 0.92 (comparable sizes)
          - Both tracks present >40% frames (MIN_COEXIST_RATIO satisfied)

        Expected: layout="double" (split-grid activated for legitimate 2-person)

        Validates: Requirement 3.1
        """
        per_frame_tracked = build_per_frame_tracked([
            {
                "track_id": 0,
                "center_x": 400.0,
                "center_y": 400.0,
                "width": 260.0,
                "height": 290.0,
                "frame_presence": 0.85,
                "jitter": 5.0,
            },
            {
                "track_id": 1,
                "center_x": 1400.0,
                "center_y": 420.0,
                "width": 240.0,
                "height": 270.0,
                "frame_presence": 0.85,
                "jitter": 5.0,
            },
        ])

        result = run_scenario(self.engine, per_frame_tracked)

        # Legitimate 2-person must trigger split-grid
        assert result["person_count"] == 2, (
            f"Two legitimate speakers should produce person_count=2. "
            f"Got person_count={result['person_count']}."
        )
        assert result["layout"] == "double", (
            f"Two legitimate speakers with 52% horizontal separation should produce "
            f"layout='double'. Got layout='{result['layout']}'."
        )

    def test_single_stable_face_single_layout(self):
        """Single face track with valid size and high presence → layout="single".

        Scenario:
          - Track A: center_x=960, face_width=250px, present in 90% frames
          - No other tracks
          - Relative width = 250/1920 ≈ 0.130 (well above any threshold)

        Expected: layout="single" (single-person crop/reframe)

        Validates: Requirement 3.2
        """
        per_frame_tracked = build_per_frame_tracked([
            {
                "track_id": 0,
                "center_x": 960.0,
                "center_y": 400.0,
                "width": 250.0,
                "height": 280.0,
                "frame_presence": 0.90,
                "jitter": 3.0,
            },
        ])

        result = run_scenario(self.engine, per_frame_tracked)

        assert result["person_count"] == 1, (
            f"Single stable face should produce person_count=1. "
            f"Got person_count={result['person_count']}."
        )
        assert result["layout"] == "single", (
            f"Single stable face should produce layout='single'. "
            f"Got layout='{result['layout']}'."
        )

    def test_3person_panel_clustering(self):
        """Three distinct speakers at well-separated positions → person_count=3.

        Scenario:
          - Track A: center_x=300, face_width=220px
          - Track B: center_x=960, face_width=230px
          - Track C: center_x=1620, face_width=210px
          - All present 80%+ frames
          - x-distances between positions:
            A→B = 660px (normalized = 660/1920 ≈ 0.34, > cluster_threshold 0.11)
            B→C = 660px (normalized ≈ 0.34, > cluster_threshold 0.11)
            A→C = 1320px (normalized ≈ 0.69, > cluster_threshold 0.11)

        Expected: person_count=3 (three distinct positions clustered correctly)

        Validates: Requirement 3.3
        """
        per_frame_tracked = build_per_frame_tracked([
            {
                "track_id": 0,
                "center_x": 300.0,
                "center_y": 400.0,
                "width": 220.0,
                "height": 250.0,
                "frame_presence": 0.85,
                "jitter": 5.0,
            },
            {
                "track_id": 1,
                "center_x": 960.0,
                "center_y": 410.0,
                "width": 230.0,
                "height": 260.0,
                "frame_presence": 0.80,
                "jitter": 5.0,
            },
            {
                "track_id": 2,
                "center_x": 1620.0,
                "center_y": 395.0,
                "width": 210.0,
                "height": 240.0,
                "frame_presence": 0.80,
                "jitter": 5.0,
            },
        ])

        result = run_scenario(self.engine, per_frame_tracked)

        assert result["person_count"] == 3, (
            f"Three well-separated speakers should produce person_count=3. "
            f"Got person_count={result['person_count']}. "
            f"Position targets: {result['position_model']['position_targets']}"
        )

    def test_hysteresis_brief_disappearance(self):
        """Face disappears briefly (<GRID_EXIT_SAMPLES) → grid layout maintained.

        Scenario:
          - Track A: present in frames 0-29 (100% presence)
          - Track B: present in frames 0-24 (83% presence), disappears frames 25-29
            (brief 5-frame gap = 1.67s at 3fps, but within hysteresis tolerance)
          - Clear horizontal separation (>20% frame width)
          - The disappearance is brief enough that the grid should still activate
            because pair_hits accumulate from the co-visible frames

        The key insight: _decide_autogrid_layout counts pair_hits (frames where
        both faces are co-visible with sufficient separation). With 25 co-visible
        frames out of 30 valid frames, coexist_ratio = 25/30 ≈ 83% which exceeds
        GRID_ENTER_SAMPLES (2) and MIN_COEXIST_RATIO (40%).

        Expected: layout="double" (grid activated despite brief disappearance)

        Validates: Requirement 3.5
        """
        per_frame_tracked = build_per_frame_tracked([
            {
                "track_id": 0,
                "center_x": 450.0,
                "center_y": 400.0,
                "width": 250.0,
                "height": 280.0,
                "frame_presence": 1.0,  # Present in all 30 frames
                "jitter": 4.0,
            },
            {
                "track_id": 1,
                "center_x": 1450.0,
                "center_y": 410.0,
                "width": 240.0,
                "height": 270.0,
                "frame_presence": 0.83,  # Present in 25/30 frames (disappears last 5)
                "jitter": 4.0,
            },
        ])

        result = run_scenario(self.engine, per_frame_tracked)

        # Despite brief disappearance, the pair has enough co-visible frames
        assert result["person_count"] == 2, (
            f"Two speakers (one with brief disappearance) should produce person_count=2. "
            f"Got person_count={result['person_count']}."
        )
        assert result["layout"] == "double", (
            f"Grid should remain active despite brief face disappearance. "
            f"Got layout='{result['layout']}'. "
            f"Track B present in 83% of frames, well above MIN_COEXIST_RATIO=40%."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
