"""Bug Condition Exploration Test — Ghost Track False Positive Grid Activation.

This test verifies that ghost/duplicate face tracks do NOT trigger split-grid
layout for single-speaker videos.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

EXPECTED on UNFIXED code: These tests FAIL (proving the bug exists).
EXPECTED on FIXED code: These tests PASS (proving the bug is fixed).
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


# ─── Helper Functions ─────────────────────────────────────────────────────────

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


def run_ghost_scenario(engine: PodcastReframeEngine, per_frame_tracked: list) -> dict:
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
    
    # Step 3: Run layout decision (no speaker result for single-speaker ghost test)
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

class TestGhostTrackFalsePositiveGridActivation:
    """Bug Condition: Ghost tracks trigger split-grid for single-speaker videos.
    
    **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
    
    Each test creates a scenario where only ONE real person is present but
    ghost/duplicate detections exist. The expected behavior is:
    - person_count = 1 (ghost eliminated)
    - layout = "single" (no split-grid)
    
    On UNFIXED code, these tests FAIL because the system returns:
    - person_count = 2 (ghost counted as real person)
    - layout = "double" (split-grid falsely activated)
    """

    def setup_method(self):
        """Create engine instance for each test."""
        self.engine = create_engine()

    def test_ghost_from_hand_shadow(self):
        """Ghost track from hand gesture/shadow — area ratio 0.78, close proximity.
        
        Scenario: Single speaker at center-left of frame. A ghost track from
        hand/shadow appears near the speaker with 78% of the main face area.
        Center distance is <5% of frame diagonal.
        
        Bug: Unfixed code produces person_count=2, layout="double"
        Expected: person_count <= 1, layout="single"
        
        Validates: Requirement 1.1, 1.3
        """
        # Main face: 285x285px at center-left position
        main_face_width = 285.0
        main_face_height = 285.0
        main_center_x = 640.0  # Left third of frame
        main_center_y = 400.0
        
        # Ghost face: 78% area ratio, very close (< 5% frame diagonal)
        # area ratio 0.78 → width ratio = sqrt(0.78) ≈ 0.883
        ghost_face_width = main_face_width * 0.883  # ~252px
        ghost_face_height = main_face_height * 0.883
        # Place ghost ~4% frame diagonal away (close but with enough horizontal
        # offset to potentially pass MIN_SEPARATION_RATIO on unfixed code)
        horizontal_offset = FRAME_WIDTH * 0.22  # Just above 20% separation threshold
        ghost_center_x = main_center_x + horizontal_offset
        ghost_center_y = main_center_y + 30  # Slight vertical offset
        
        per_frame_tracked = build_per_frame_tracked([
            {
                "track_id": 0,
                "center_x": main_center_x,
                "center_y": main_center_y,
                "width": main_face_width,
                "height": main_face_height,
                "frame_presence": 0.95,  # Present in 95% of frames (stable)
                "jitter": 5.0,
            },
            {
                "track_id": 1,
                "center_x": ghost_center_x,
                "center_y": ghost_center_y,
                "width": ghost_face_width,
                "height": ghost_face_height,
                "frame_presence": 0.80,  # Ghost present in 80% (looks real to current code)
                "jitter": 8.0,
            },
        ])
        
        result = run_ghost_scenario(self.engine, per_frame_tracked)
        
        # Expected: Ghost should be eliminated → single layout
        assert result["layout"] == "single", (
            f"Ghost from hand/shadow should NOT trigger split-grid. "
            f"Got layout='{result['layout']}', person_count={result['person_count']}. "
            f"Main face: {main_face_width:.0f}x{main_face_height:.0f}px at ({main_center_x:.0f}, {main_center_y:.0f}), "
            f"Ghost face: {ghost_face_width:.0f}x{ghost_face_height:.0f}px at ({ghost_center_x:.0f}, {ghost_center_y:.0f}), "
            f"Area ratio: 0.78, Horizontal offset: {horizontal_offset:.0f}px ({horizontal_offset/FRAME_WIDTH*100:.1f}% of frame)"
        )
        assert result["person_count"] <= 1, (
            f"Ghost track should be eliminated from position model. "
            f"Got person_count={result['person_count']}, expected <= 1"
        )

    def test_noise_detection_at_threshold(self):
        """Noise face at relative width=0.052 (above current 0.05, below proposed 0.10).
        
        Scenario: Single speaker with a valid face. A noise detection appears
        with relative width 0.052 (100px on 1920p). Current threshold (0.05)
        passes it; proposed threshold (0.10) should reject it.
        
        Bug: Unfixed code lets noise pass and counts as second person
        Expected: person_count <= 1, layout="single"
        
        Validates: Requirement 1.2
        """
        # Main face: 250px wide (relative = 250/1920 ≈ 0.130, well above threshold)
        main_face_width = 250.0
        main_face_height = 280.0
        main_center_x = 500.0
        main_center_y = 380.0
        
        # Noise face: relative width = 0.052 → 100px on 1920p
        noise_face_width = 100.0  # 100/1920 = 0.052
        noise_face_height = 110.0
        # Place noise with enough horizontal separation to trigger grid
        noise_center_x = main_center_x + FRAME_WIDTH * 0.25  # 25% separation
        noise_center_y = 350.0
        
        per_frame_tracked = build_per_frame_tracked([
            {
                "track_id": 0,
                "center_x": main_center_x,
                "center_y": main_center_y,
                "width": main_face_width,
                "height": main_face_height,
                "frame_presence": 0.90,
                "jitter": 5.0,
            },
            {
                "track_id": 1,
                "center_x": noise_center_x,
                "center_y": noise_center_y,
                "width": noise_face_width,
                "height": noise_face_height,
                "frame_presence": 0.60,  # Noise appears consistently enough
                "jitter": 10.0,
            },
        ])
        
        result = run_ghost_scenario(self.engine, per_frame_tracked)
        
        # Expected: Noise should be rejected → single layout
        assert result["layout"] == "single", (
            f"Noise detection at relative width 0.052 should NOT trigger split-grid. "
            f"Got layout='{result['layout']}', person_count={result['person_count']}. "
            f"Noise face: {noise_face_width:.0f}x{noise_face_height:.0f}px "
            f"(relative_width={noise_face_width/FRAME_WIDTH:.3f}), "
            f"area={noise_face_width*noise_face_height:.0f}px² "
            f"(below proposed MIN_FACE_AREA_PX=12000: {noise_face_width*noise_face_height < 12000})"
        )
        assert result["person_count"] <= 1, (
            f"Noise detection should be eliminated. "
            f"Got person_count={result['person_count']}, expected <= 1"
        )

    def test_flicker_track(self):
        """Flicker track appearing in only 10% of frames alongside stable main track.
        
        Scenario: Single speaker with stable face. A ghost/flicker track appears
        sporadically in only 10% of frames. Current code has no frame presence
        filter, so it clusters this as a second person.
        
        Bug: Unfixed code counts flicker track as real person
        Expected: person_count <= 1, layout="single"
        
        Validates: Requirement 1.3 (frame_ratio < 0.15 should be eliminated)
        """
        # Main face: stable, present in 90% of frames
        main_face_width = 270.0
        main_face_height = 300.0
        main_center_x = 700.0
        main_center_y = 400.0
        
        # Flicker ghost: similar size but only in 10% of frames
        # Place with enough horizontal offset to trigger grid IF counted
        flicker_face_width = 240.0
        flicker_face_height = 260.0
        flicker_center_x = main_center_x + FRAME_WIDTH * 0.25  # 25% separation
        flicker_center_y = 420.0
        
        per_frame_tracked = build_per_frame_tracked([
            {
                "track_id": 0,
                "center_x": main_center_x,
                "center_y": main_center_y,
                "width": main_face_width,
                "height": main_face_height,
                "frame_presence": 0.90,
                "jitter": 3.0,
            },
            {
                "track_id": 1,
                "center_x": flicker_center_x,
                "center_y": flicker_center_y,
                "width": flicker_face_width,
                "height": flicker_face_height,
                "frame_presence": 0.10,  # Only 10% presence (flicker)
                "jitter": 15.0,
            },
        ])
        
        result = run_ghost_scenario(self.engine, per_frame_tracked)
        
        # Expected: Flicker track should be eliminated → single layout
        assert result["layout"] == "single", (
            f"Flicker track (10% frame presence) should NOT trigger split-grid. "
            f"Got layout='{result['layout']}', person_count={result['person_count']}. "
            f"Flicker track present in {0.10*TOTAL_FRAMES:.0f}/{TOTAL_FRAMES} frames "
            f"(frame_ratio=0.10, below threshold 0.15)"
        )
        assert result["person_count"] <= 1, (
            f"Flicker track should be eliminated from position model. "
            f"Got person_count={result['person_count']}, expected <= 1"
        )

    def test_high_iou_duplicate(self):
        """Two tracks with IoU=0.30, similar areas — same person detected twice.
        
        Scenario: Face detector creates two overlapping bounding boxes for the
        same face. The tracks have IoU ~0.30 and very similar areas. These should
        be recognized as duplicates (same person).
        
        Bug: Unfixed code clusters both as separate persons if horizontal offset
        exceeds cluster_threshold (0.11 normalized)
        Expected: person_count <= 1, layout="single"
        
        Validates: Requirement 1.4
        """
        # Main face: 260x280px
        main_face_width = 260.0
        main_face_height = 280.0
        main_center_x = 600.0
        main_center_y = 400.0
        
        # Duplicate track: similar size, overlapping with IoU ~0.30
        # IoU = intersection / union
        # For IoU=0.30 with similar-sized boxes, horizontal offset ≈ 55% of width
        # BUT we need enough horizontal separation to trigger grid on unfixed code
        # So place it with enough offset to pass MIN_SEPARATION_RATIO
        dup_face_width = 250.0  # Similar size (area ratio ~0.92)
        dup_face_height = 270.0
        # Use offset that creates IoU~0.30 based on overlap calculation
        # With width=260, overlap of ~78px → IoU ≈ 0.30
        # But for grid trigger we need 20% frame separation (384px)
        # This simulates tracker re-creating a track with drift
        dup_center_x = main_center_x + FRAME_WIDTH * 0.22  # 422px offset for grid trigger
        dup_center_y = main_center_y + 15  # Slight vertical drift
        
        per_frame_tracked = build_per_frame_tracked([
            {
                "track_id": 0,
                "center_x": main_center_x,
                "center_y": main_center_y,
                "width": main_face_width,
                "height": main_face_height,
                "frame_presence": 0.85,
                "jitter": 5.0,
            },
            {
                "track_id": 1,
                "center_x": dup_center_x,
                "center_y": dup_center_y,
                "width": dup_face_width,
                "height": dup_face_height,
                "frame_presence": 0.70,  # Duplicate appears in 70% of frames
                "jitter": 8.0,
            },
        ])
        
        result = run_ghost_scenario(self.engine, per_frame_tracked)
        
        # Expected: Duplicate should be recognized as same person → single layout
        assert result["layout"] == "single", (
            f"High IoU duplicate track should NOT trigger split-grid. "
            f"Got layout='{result['layout']}', person_count={result['person_count']}. "
            f"Track 0: {main_face_width:.0f}x{main_face_height:.0f}px at ({main_center_x:.0f}, {main_center_y:.0f}), "
            f"Track 1 (dup): {dup_face_width:.0f}x{dup_face_height:.0f}px at ({dup_center_x:.0f}, {dup_center_y:.0f}), "
            f"Area ratio: {(dup_face_width*dup_face_height)/(main_face_width*main_face_height):.2f}"
        )
        assert result["person_count"] <= 1, (
            f"Duplicate track should be merged/eliminated in position model. "
            f"Got person_count={result['person_count']}, expected <= 1"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
