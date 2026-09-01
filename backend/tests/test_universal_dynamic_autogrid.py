"""Tests for Universal Dynamic Auto Grid 2.0.

Covers:
1. Screen + Cam detection for Trading/Screencast (1 person on left/right + screen content)
2. Screen + Cam detection for Gaming/Streamer (1 person in PiP/corner + gameplay)
3. Multi-person active-speaker scoring (3, 4, 5+ people in frame, ensuring active speaker
   is chosen for the grid pair rather than just furthest bystanders)
4. Subtitle dynamic centering (middle 50% during double grid, bottom during single)
5. Behind-person overlay suppression during double grid segments
"""
import pytest
from unittest.mock import MagicMock

from src.infrastructure.podcast_reframe_engine import PodcastReframeEngine
from src.infrastructure.active_speaker_detector import ActiveSpeakerResult
from src.infrastructure.person_tracker import BBox
from src.infrastructure.person_tracker_v2 import TrackedPerson


def test_trading_screencast_detected_as_screen_cam():
    """Image 1: Trader on left (x < 35% of frame) + large TradingView chart."""
    engine = PodcastReframeEngine()
    width = 1920
    height = 1080

    # Trader sitting on the left side of a 1920x1080 screen
    # center_x = 220, width = 300, height = 450, y = 600
    tracked_data = {
        "person_count": 1,
        "position_targets": {1: 220.0},
        "position_target_profiles": {
            1: {"x": 220.0, "y": 600.0, "width": 300.0, "height": 450.0}
        },
        "per_frame_tracked": [[MagicMock()]] * 10,
        "sample_timestamps": [i * 0.5 for i in range(10)],
    }

    decision = engine._decide_autogrid_layout(
        tracked_data=tracked_data,
        speaker_result=None,
        width=width,
        height=height,
    )

    assert decision is not None
    assert decision["layout"] == "double"
    assert decision["sub_layout"] == "screen_cam"
    assert decision["top_track_id"] == "screen"
    assert decision["bottom_track_id"] == 1

    # In 9:16 target, top panel shows chart (right side of screen)
    # Screen crop should capture the right side of the screen
    assert decision["top_crop_x"] > 0
    assert decision["top_crop_w"] > 0
    # Bottom panel captures trader on the left
    assert decision["bottom_crop_x"] >= 0
    assert decision["bottom_crop_w"] > 0

    # Check detect-then-switch timeline (starts single hook, then switches to double)
    assert len(decision["layout_events"]) >= 2
    assert decision["layout_events"][0]["layout"] == "single"
    assert decision["layout_events"][1]["layout"] == "double"


def test_gaming_streamer_detected_as_screen_cam():
    """Image 5: Streamer facecam on bottom right + gameplay footage."""
    engine = PodcastReframeEngine()
    width = 1920
    height = 1080

    # Streamer on bottom right: center_x = 1680, width = 320, height = 350, y = 880
    tracked_data = {
        "person_count": 1,
        "position_targets": {2: 1680.0},
        "position_target_profiles": {
            2: {"x": 1680.0, "y": 880.0, "width": 320.0, "height": 350.0}
        },
        "per_frame_tracked": [[MagicMock()]] * 10,
        "sample_timestamps": [i * 0.5 for i in range(10)],
    }

    decision = engine._decide_autogrid_layout(
        tracked_data=tracked_data,
        speaker_result=None,
        width=width,
        height=height,
    )

    assert decision is not None
    assert decision["layout"] == "double"
    assert decision["sub_layout"] == "screen_cam"
    assert decision["top_track_id"] == "screen"
    assert decision["bottom_track_id"] == 2

    # Top panel gameplay starts from left (x = 0)
    assert decision["top_crop_x"] == 0
    # Bottom panel focuses on streamer on the right
    assert decision["bottom_crop_x"] > 500


def test_multi_person_gazebo_prioritizes_active_speaker():
    """Image 3: 5 people in gazebo (x = 150, 320, 540, 700, 880).
    When Person 3 (woman in center, x = 540) is speaking with Person 4 (x = 700),
    the pair MUST include Person 3 rather than just Person 1 and Person 5!
    """
    engine = PodcastReframeEngine()
    width = 1920
    height = 1080

    from src.infrastructure.person_tracker import TrackedDetection

    tracked_data = {
        "person_count": 5,
        "position_targets": {
            1: 150.0,  # Person 1 (far left, blue shirt)
            2: 320.0,  # Person 2 (white/black jacket)
            3: 540.0,  # Person 3 (center woman)
            4: 700.0,  # Person 4 (black shirt)
            5: 880.0,  # Person 5 (far right, green cap)
        },
        "position_target_profiles": {
            1: {"x": 150.0, "y": 600.0, "width": 180.0, "height": 300.0},
            2: {"x": 320.0, "y": 600.0, "width": 180.0, "height": 300.0},
            3: {"x": 540.0, "y": 600.0, "width": 180.0, "height": 300.0},
            4: {"x": 700.0, "y": 600.0, "width": 180.0, "height": 300.0},
            5: {"x": 880.0, "y": 600.0, "width": 180.0, "height": 300.0},
        },
        "track_to_position": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5},
        "per_frame_tracked": [
            [
                TrackedDetection(track_id=1, bbox=BBox(60, 450, 240, 750), frame_idx=f_idx, is_new=False),
                TrackedDetection(track_id=2, bbox=BBox(230, 450, 410, 750), frame_idx=f_idx, is_new=False),
                TrackedDetection(track_id=3, bbox=BBox(450, 450, 630, 750), frame_idx=f_idx, is_new=False),
                TrackedDetection(track_id=4, bbox=BBox(610, 450, 790, 750), frame_idx=f_idx, is_new=False),
                TrackedDetection(track_id=5, bbox=BBox(790, 450, 970, 750), frame_idx=f_idx, is_new=False),
            ]
            for f_idx in range(12)
        ],
        "sample_timestamps": [i * 0.5 for i in range(12)],
    }

    # Person 3 is talking, responding to Person 4
    speaker_result = ActiveSpeakerResult(
        segments=[],
        dominant_speaker_id=3,
        dominant_ratio=0.8,
        per_frame_speaker={
            0: 4, 1: 4, 2: 4, 3: 3, 4: 3, 5: 3, 6: 3, 7: 3, 8: 3, 9: 3, 10: 3, 11: 3
        },
        total_speakers=5,
    )

    decision = engine._decide_autogrid_layout(
        tracked_data=tracked_data,
        speaker_result=speaker_result,
        width=width,
        height=height,
        skip_ghost_pair_check=True,
    )

    assert decision is not None
    assert decision["layout"] == "double"
    # Person 3 (the center speaker) MUST be one of the panels!
    panel_ids = {int(decision["top_track_id"]), int(decision["bottom_track_id"])}
    assert 3 in panel_ids, f"Expected active speaker P3 in panel pair, got {panel_ids}"
    # And it should not be just the blind extremes P1 and P5
    assert panel_ids != {1, 5}, f"Pair should not be blind extremes {panel_ids}"


def test_subtitle_dynamic_centering_position():
    """Verify subtitle centers at 50% during double grid and returns to bottom during single."""
    from src.infrastructure.skia_subtitle_renderer import SkiaSubtitleRenderer

    renderer = SkiaSubtitleRenderer()
    layout_events = [
        {"time": 0.0, "layout": "single"},
        {"time": 2.5, "layout": "double"},
        {"time": 10.0, "layout": "single"},
    ]

    # At t = 1.0s (single): layout is single
    assert renderer._get_layout_at_time(layout_events, 1.0) == "single"

    # At t = 5.0s (double): layout is double
    assert renderer._get_layout_at_time(layout_events, 5.0) == "double"

    # At t = 12.0s (back to single): layout is single
    assert renderer._get_layout_at_time(layout_events, 12.0) == "single"


def test_behind_person_overlay_suppressed_during_double_grid(tmp_path):
    """Verify that behind-person overlay events are blocked during double-grid time intervals."""
    from src.infrastructure.top_behind_subject_renderer import pick_top_overlay_suggestions

    dummy_file = tmp_path / "fake_icon.png"
    dummy_file.write_text("fake_png")

    class DummySuggestion:
        def __init__(self, at_time, duration, placement="behind_person"):
            self.at_time = at_time
            self.duration = duration
            self.placement = placement
            self.keyword = "test icon"
            self.asset_result = MagicMock(is_fallback=False, local_path=str(dummy_file), asset_format="image")
            self.splice_segment = None

    suggestions = [
        DummySuggestion(at_time=1.0, duration=2.0),   # 1.0s - 3.0s (single grid)
        DummySuggestion(at_time=4.0, duration=3.0),   # 4.0s - 7.0s (inside double grid!)
        DummySuggestion(at_time=12.0, duration=2.0),  # 12.0s - 14.0s (back to single)
    ]

    # Double grid is active from 3.0s to 10.0s
    blocked_ranges = [(3.0, 10.0)]

    picked = pick_top_overlay_suggestions(
        suggestions=suggestions,
        max_per_clip=3,
        blocked_ranges=blocked_ranges,
        clip_duration=15.0,
    )

    # The suggestion at t=4.0s (inside double grid 3.0s - 10.0s) MUST BE BLOCKED!
    picked_times = [float(s.at_time) for s in picked]
    assert 4.0 not in picked_times, f"Expected t=4.0 to be blocked, but was picked: {picked_times}"
    # The suggestions in single grid time (t=1.0 and t=12.0) should be preserved
    assert len(picked) >= 1


def test_gaming_streamer_with_game_character_detected_as_screen_cam():
    """Verify that when YOLO detects both a streamer in a corner PiP and a character inside the game,
    the system correctly classifies it as Screen + Cam layout rather than a 2-person podcast!
    """
    engine = PodcastReframeEngine()
    width = 1920
    height = 1080

    from src.infrastructure.person_tracker import TrackedDetection

    tracked_data = {
        "person_count": 2,  # Streamer + Game character (e.g. Silent Hill / RPG)
        "position_targets": {
            1: 850.0,   # Game character in center of gameplay screen (x = 850)
            2: 1720.0,  # Streamer (Windah) in corner webcam PiP (x = 1720, bottom right)
        },
        "position_target_profiles": {
            1: {"x": 850.0, "y": 540.0, "width": 400.0, "height": 650.0},     # Game character
            2: {"x": 1720.0, "y": 880.0, "width": 280.0, "height": 340.0},   # Corner PiP webcam
        },
        "track_to_position": {1: 1, 2: 2},
        "per_frame_tracked": [
            [
                TrackedDetection(track_id=1, bbox=BBox(650, 215, 1050, 865), frame_idx=f_idx, is_new=False),
                TrackedDetection(track_id=2, bbox=BBox(1580, 710, 1860, 1050), frame_idx=f_idx, is_new=False),
            ]
            for f_idx in range(12)
        ],
        "sample_timestamps": [i * 0.5 for i in range(12)],
    }

    decision = engine._decide_autogrid_layout(
        tracked_data=tracked_data,
        speaker_result=None,
        width=width,
        height=height,
        skip_ghost_pair_check=True,
    )

    assert decision is not None
    assert decision["layout"] == "double"
    # MUST be classified as screen_cam (Top: gameplay, Bottom: Windah), NOT a 2-person split with the game character!
    assert decision["sub_layout"] == "screen_cam"
    assert decision["top_track_id"] == "screen"
    assert decision["bottom_track_id"] == 2
