import numpy as np
import pytest
from src.config import settings
from src.infrastructure.podcast_reframe_engine import PodcastReframeEngine
from src.infrastructure.person_tracker import BBox, TrackedDetection

def test_person_first_config_exist():
    """Verify that settings has our new configs with expected defaults."""
    assert hasattr(settings, "REFRAME_PIPELINE_MODE")
    assert hasattr(settings, "PERSON_DETECTOR")
    assert hasattr(settings, "PERSON_CONF_THRESHOLD")
    assert hasattr(settings, "PERSON_TRACKER")
    assert hasattr(settings, "TRACKER_MAX_LOST_FRAMES")
    assert hasattr(settings, "FACE_DETECTOR")
    assert hasattr(settings, "FACE_REGION_HEAD_RATIO")
    assert hasattr(settings, "FACE_CONFIDENCE")

def test_model_loaders():
    """Verify that the lazy loaders initialize the models without crash."""
    engine = PodcastReframeEngine()
    
    # 1. Person detector loader (RF-DETR or YOLO fallback)
    success_person = engine._load_person_detector()
    assert success_person is True
    assert hasattr(engine, "_person_detector")
    
    # 2. Crop face detector loader
    success_face = engine._load_crop_face_detector()
    assert success_face is True
    assert hasattr(engine, "_crop_face_detector")
    
    # 3. Person tracker loader
    success_tracker = engine._init_person_tracker(fps=30.0)
    assert success_tracker is True
    assert hasattr(engine, "_person_tracker")

def test_crop_face_mapping_coordinates():
    """Verify that crop coordinates are correctly translated back to full-frame coordinates."""
    # Person bbox
    p_x1, p_y1, p_x2, p_y2 = 100.0, 200.0, 500.0, 800.0
    p_h = p_y2 - p_y1
    p_w = p_x2 - p_x1
    
    # Head region crop coordinates (top 35% height)
    head_ratio = 0.35
    head_x1 = int(p_x1)
    head_y1 = int(p_y1)
    head_x2 = int(p_x2)
    head_y2 = int(p_y1 + head_ratio * p_h)
    
    # Let's say a face is detected relative to crop coordinates
    f_x1_rel, f_y1_rel, f_x2_rel, f_y2_rel = 10.0, 20.0, 80.0, 100.0
    
    # Mapped coordinates to full frame
    face_found = BBox(
        f_x1_rel + head_x1,
        f_y1_rel + head_y1,
        f_x2_rel + head_x1,
        f_y2_rel + head_y1
    )
    
    assert face_found.x1 == 110.0
    assert face_found.y1 == 220.0
    assert face_found.x2 == 180.0
    assert face_found.y2 == 300.0
    assert face_found.center_x == 145.0
    assert face_found.center_y == 260.0

def test_person_first_position_model():
    """Verify that position model clusters and builds stable seats correctly using face bboxes."""
    engine = PodcastReframeEngine()
    
    # Create mock tracked detections with face_bbox and bbox
    t1 = TrackedDetection(
        track_id=0,
        bbox=BBox(100.0, 200.0, 500.0, 800.0),
        frame_idx=0,
        face_bbox=BBox(240.0, 220.0, 360.0, 340.0) # center_x = 300.0
    )
    t2 = TrackedDetection(
        track_id=1,
        bbox=BBox(600.0, 200.0, 1000.0, 800.0),
        frame_idx=0,
        face_bbox=BBox(740.0, 220.0, 860.0, 340.0) # center_x = 800.0
    )
    
    per_frame_tracked = [[t1, t2], [t1, t2]]
    
    pos_model = engine._build_position_model_person_first(per_frame_tracked, 1920, 1080)
    
    assert pos_model["person_count"] == 2
    assert pos_model["stable_positions"][0] == 300.0
    assert pos_model["stable_positions"][1] == 800.0
    assert pos_model["track_to_position"][0] == 0
    assert pos_model["track_to_position"][1] == 1


def test_duplicate_nested_person_detections_are_suppressed_before_tracking():
    from src.infrastructure.person_detector import filter_duplicate_person_boxes

    engine = PodcastReframeEngine()
    detections = [
        (100.0, 80.0, 1300.0, 1000.0, 0.95),
        (800.0, 230.0, 1200.0, 780.0, 0.80),
    ]

    # Shared helper (person-first PersonDetector path) and engine wrapper
    # (legacy podcast path) must agree.
    assert filter_duplicate_person_boxes(detections) == [detections[0]]
    assert engine._filter_duplicate_person_detections(detections) == [detections[0]]


def test_separate_person_detections_are_preserved_before_tracking():
    from src.infrastructure.person_detector import filter_duplicate_person_boxes

    engine = PodcastReframeEngine()
    detections = [
        (100.0, 100.0, 700.0, 1000.0, 0.94),
        (1100.0, 120.0, 1750.0, 1000.0, 0.92),
    ]

    assert filter_duplicate_person_boxes(detections) == detections
    assert engine._filter_duplicate_person_detections(detections) == detections
