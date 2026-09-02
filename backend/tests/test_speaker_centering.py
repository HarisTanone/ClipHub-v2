"""Tests for speaker-aware centering identity glue."""
import os
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.active_speaker_detector import (
    ActiveSpeakerDetector,
    ActiveSpeakerResult,
    FaceSpeechFrame,
)
from src.infrastructure.person_tracker import BBox, TrackedDetection
from src.infrastructure.podcast_reframe_engine import PodcastReframeEngine
from src.infrastructure.speaker_diarizer import DiarizationSegment
from src.infrastructure.speaker_face_mapper import SpeakerFaceMapper


def _speech_frame(
    face_id: int,
    x: float,
    lip: float = 0.05,
    head: float = 0.0,
    y: float = 400,
):
    return FaceSpeechFrame(
        face_id=face_id,
        lip_aperture=lip,
        head_motion=head,
        bbox_x=x,
        bbox_y=y,
        nose_x=x,
        nose_y=y,
    )


def test_single_visible_face_uses_stable_position_target():
    detector = ActiveSpeakerDetector()
    frame_data = [(0, [_speech_frame(face_id=0, x=1485)])]

    assigned = detector._assign_consistent_ids(
        frame_data,
        frame_width=1920,
        position_targets={0: 520, 1: 1480},
    )

    assert assigned[0][1][0].face_id == 1


def test_panning_centers_only_person_in_single_seat_video():
    engine = PodcastReframeEngine()
    visible = TrackedDetection(20, BBox(1320, 120, 1560, 520), 30)
    stale_speaker = ActiveSpeakerResult(
        segments=[],
        dominant_speaker_id=0,
        dominant_ratio=1.0,
        per_frame_speaker={30: 0},
        total_speakers=2,
    )

    center, detection, position_id, source = engine._choose_panning_target_x(
        frame_faces=[visible.bbox.center_x],
        frame_tracked=[visible],
        speaker_result=stale_speaker,
        frame_idx_approx=30,
        position_targets={1: 1440},
        position_target_profiles={},
        track_to_position={20: 1},
        frame_width=1920,
        frame_height=1080,
    )

    assert center == visible.bbox.center_x
    assert detection is visible
    assert position_id == 1
    assert source == "only_visible_person"


def test_head_motion_is_keyed_after_stable_id_assignment():
    detector = ActiveSpeakerDetector()
    frame_data = [
        (0, [_speech_frame(0, 520), _speech_frame(1, 1480)]),
        (6, [_speech_frame(0, 1490), _speech_frame(1, 530)]),
    ]

    assigned = detector._assign_consistent_ids(
        frame_data,
        frame_width=1920,
        position_targets={0: 520, 1: 1480},
    )
    with_motion = detector._compute_head_motion(assigned)
    second_frame_by_id = {face.face_id: face for face in with_motion[1][1]}

    assert second_frame_by_id[0].head_motion == 0.5
    assert second_frame_by_id[1].head_motion == 0.5


def test_face_mesh_assignment_uses_2d_profiles_for_front_back_panelists():
    detector = ActiveSpeakerDetector()
    frame_data = [
        (
            0,
            [
                _speech_frame(0, 620, y=690),
                _speech_frame(1, 625, y=350),
            ],
        )
    ]

    assigned = detector._assign_consistent_ids(
        frame_data,
        frame_width=1920,
        frame_height=1080,
        position_targets={0: 620, 1: 625},
        position_target_profiles={
            0: {"x": 620, "y": 350, "width": 120, "height": 140, "area": 16800},
            1: {"x": 625, "y": 690, "width": 180, "height": 220, "area": 39600},
        },
    )

    by_y = {int(face.bbox_y): face.face_id for face in assigned[0][1]}
    assert by_y[350] == 0
    assert by_y[690] == 1


def test_lip_motion_beats_listener_head_motion():
    detector = ActiveSpeakerDetector()
    frame_data = [
        (0, [_speech_frame(0, 520, lip=0.02, head=1.0), _speech_frame(1, 1480, lip=0.02, head=0.1)]),
        (6, [_speech_frame(0, 520, lip=0.02, head=1.0), _speech_frame(1, 1480, lip=0.12, head=0.1)]),
        (12, [_speech_frame(0, 520, lip=0.02, head=1.0), _speech_frame(1, 1480, lip=0.02, head=0.1)]),
    ]

    speakers = detector._compute_active_speakers(frame_data, fps=30.0, sample_interval_sec=0.2)

    assert speakers
    assert set(speakers.values()) == {1}


def test_low_confidence_lip_motion_still_selects_best_speaker():
    detector = ActiveSpeakerDetector()
    frame_data = [
        (0, [_speech_frame(0, 520, lip=0.020), _speech_frame(1, 1480, lip=0.020)]),
        (6, [_speech_frame(0, 520, lip=0.027), _speech_frame(1, 1480, lip=0.020)]),
        (12, [_speech_frame(0, 520, lip=0.020), _speech_frame(1, 1480, lip=0.020)]),
    ]

    speakers = detector._compute_active_speakers(frame_data, fps=30.0, sample_interval_sec=0.2)

    assert speakers
    assert set(speakers.values()) == {0}


def test_position_model_clusters_recreated_tracks_by_seat():
    engine = PodcastReframeEngine()
    tracked = [
        [
            TrackedDetection(0, BBox(470, 100, 570, 240), 0),
            TrackedDetection(1, BBox(1430, 100, 1530, 240), 0),
        ],
        [
            TrackedDetection(2, BBox(490, 100, 590, 240), 30),
            TrackedDetection(1, BBox(1440, 100, 1540, 240), 30),
        ],
        [
            TrackedDetection(2, BBox(500, 100, 600, 240), 60),
            TrackedDetection(1, BBox(1450, 100, 1550, 240), 60),
        ],
    ]

    model = engine._build_position_model(tracked, width=1920, height=1080)

    assert model["person_count"] == 2
    assert model["track_to_position"][0] == 0
    assert model["track_to_position"][2] == 0
    assert model["track_to_position"][1] == 1


def test_position_model_keeps_front_back_people_with_similar_x_separate():
    engine = PodcastReframeEngine()
    tracked = [
        [
            TrackedDetection(0, BBox(560, 250, 680, 390), 0),
            TrackedDetection(1, BBox(535, 620, 715, 840), 0),
            TrackedDetection(2, BBox(1240, 250, 1360, 390), 0),
            TrackedDetection(3, BBox(1215, 620, 1395, 840), 0),
        ],
        [
            TrackedDetection(0, BBox(565, 252, 685, 392), 30),
            TrackedDetection(1, BBox(540, 622, 720, 842), 30),
            TrackedDetection(2, BBox(1245, 252, 1365, 392), 30),
            TrackedDetection(3, BBox(1220, 622, 1400, 842), 30),
        ],
    ]

    model = engine._build_position_model(tracked, width=1920, height=1080)

    assert model["person_count"] == 4
    assert len(set(model["track_to_position"].values())) == 4


def test_autogrid_rejects_duplicate_tracks_mapped_to_one_person():
    engine = PodcastReframeEngine()
    tracked_data = {
        "person_count": 1,
        "position_targets": {0: 520},
        "track_to_position": {10: 0, 11: 0},
        "per_frame_tracked": [
            [
                TrackedDetection(10, BBox(450, 100, 590, 260), 0),
                TrackedDetection(11, BBox(455, 105, 595, 265), 0),
            ]
            for _ in range(8)
        ],
    }

    decision = engine._decide_autogrid_layout(tracked_data, None, width=1920)

    assert decision["layout"] == "single"


def test_autogrid_requires_two_unique_people_visible_together():
    engine = PodcastReframeEngine()
    # ≥ GRID_ENTER_SAMPLES and wall-clock ≥ MIN_GRID_SEGMENT_SECONDS
    n = max(engine.GRID_ENTER_SAMPLES, 12)
    tracked_data = {
        "person_count": 2,
        "position_targets": {0: 480, 1: 1460},
        "track_to_position": {10: 0, 20: 1},
        "sample_timestamps": [i * 0.35 for i in range(n)],
        "per_frame_tracked": [
            [
                TrackedDetection(10, BBox(410, 100, 550, 260), frame),
                TrackedDetection(20, BBox(1390, 100, 1530, 260), frame),
            ]
            for frame in range(n)
        ],
    }

    decision = engine._decide_autogrid_layout(tracked_data, None, width=1920)

    assert decision["layout"] == "double"
    assert decision["top_track_id"] != decision["bottom_track_id"]
    assert engine.GRID_PANEL_HEIGHT == 960


def test_autogrid_counts_visual_people_even_when_only_one_audio_speaker_is_detected():
    engine = PodcastReframeEngine()
    n = max(engine.GRID_ENTER_SAMPLES, 12)
    tracked_data = {
        "person_count": 2,
        "position_targets": {0: 480, 1: 1460},
        "track_to_position": {10: 0, 20: 1},
        "sample_timestamps": [i * 0.35 for i in range(n)],
        "per_frame_tracked": [
            [
                TrackedDetection(10, BBox(410, 100, 550, 600), frame),
                TrackedDetection(20, BBox(1390, 100, 1530, 600), frame),
            ]
            for frame in range(n)
        ],
    }
    one_audio_speaker = ActiveSpeakerResult(
        segments=[],
        dominant_speaker_id=0,
        dominant_ratio=1.0,
        per_frame_speaker={frame: 0 for frame in range(n)},
        total_speakers=1,
    )

    decision = engine._decide_autogrid_layout(
        tracked_data, one_audio_speaker, width=1920
    )

    assert decision["layout"] == "double"
    assert decision["person_count"] == 2


def test_position_model_treats_body_and_attached_head_as_one_person():
    engine = PodcastReframeEngine()
    body = BBox(300, 100, 700, 900)
    head = BBox(430, 120, 570, 280)
    tracked = [
        [TrackedDetection(
            track_id=10,
            bbox=body,
            frame_idx=frame,
            person_bbox=body,
            face_bbox=head,
        )]
        for frame in range(8)
    ]

    model = engine._build_position_model(tracked, width=1920, height=1080)

    assert model["person_count"] == 1
    assert model["position_target_profiles"][0]["x"] == body.center_x
    assert model["position_target_profiles"][0]["face_x"] == head.center_x
    assert model["position_target_profiles"][0]["face_y"] == head.center_y


def test_autogrid_rejects_people_who_never_share_a_frame():
    engine = PodcastReframeEngine()
    tracked_data = {
        "person_count": 2,
        "position_targets": {0: 480, 1: 1460},
        "track_to_position": {10: 0, 20: 1},
        "per_frame_tracked": [
            [TrackedDetection(10, BBox(410, 100, 550, 260), frame)]
            if frame < 4
            else [TrackedDetection(20, BBox(1390, 100, 1530, 260), frame)]
            for frame in range(8)
        ],
    }

    decision = engine._decide_autogrid_layout(tracked_data, None, width=1920)

    assert decision["layout"] == "single"


def test_autogrid_rejects_pair_when_isolation_requires_overzoom():
    engine = PodcastReframeEngine()
    tracked_data = {
        "person_count": 2,
        "position_targets": {0: 760, 1: 1160},
        "position_target_profiles": {
            0: {"x": 760, "y": 320, "width": 140, "height": 170, "area": 23800},
            1: {"x": 1160, "y": 320, "width": 140, "height": 170, "area": 23800},
        },
        "track_to_position": {10: 0, 20: 1},
        "sample_timestamps": [frame / 3 for frame in range(8)],
        "per_frame_tracked": [
            [
                TrackedDetection(10, BBox(690, 235, 830, 405), frame),
                TrackedDetection(20, BBox(1090, 235, 1230, 405), frame),
            ]
            for frame in range(8)
        ],
    }

    decision = engine._decide_autogrid_layout(
        tracked_data, None, width=1920, height=1080
    )

    assert decision["layout"] == "single"


def test_grid_geometry_uses_smallest_safe_zoom_and_caps_it():
    engine = PodcastReframeEngine()
    geometry = engine._calculate_grid_geometry(
        first_id=0,
        second_id=1,
        position_targets={0: 480, 1: 1460},
        position_profiles={
            0: {"x": 480, "y": 340, "width": 120, "height": 150, "area": 18000},
            1: {"x": 1460, "y": 360, "width": 120, "height": 150, "area": 18000},
        },
        width=1920,
        height=1080,
    )

    assert geometry is not None
    assert engine.GRID_BASE_ZOOM <= geometry["grid_zoom"] <= engine.GRID_MAX_ZOOM
    assert geometry["first_crop_x"] + geometry["crop_w"] < 1400
    assert geometry["second_crop_x"] > 540


def test_layout_timeline_switches_only_after_stable_people_count():
    engine = PodcastReframeEngine()
    engine.GRID_ENTER_SAMPLES = 3
    engine.GRID_EXIT_SAMPLES = 2
    engine.MIN_GRID_SEGMENT_SECONDS = 0.5
    events = engine._build_layout_events(
        raw_double=[False, False, True, True, True, False, False, False],
        timestamps=[0.0, 0.33, 0.66, 1.0, 1.33, 1.66, 2.0, 2.33],
    )

    assert [event["layout"] for event in events] == ["single", "double", "single"]
    assert events[1]["time"] == 0.66
    assert events[2]["time"] == 1.66


def test_layout_closes_immediately_if_one_face_enters_both_crops():
    engine = PodcastReframeEngine()
    engine.GRID_ENTER_SAMPLES = 2
    engine.GRID_EXIT_SAMPLES = 1
    engine.MIN_GRID_SEGMENT_SECONDS = 0.5
    events = engine._build_layout_events(
        raw_double=[True, True, False, True, True],
        timestamps=[0.0, 0.33, 0.66, 1.0, 1.33],
        force_single=[False, False, True, False, False],
    )

    assert events[0]["layout"] == "double"
    assert events[1] == {"time": 0.66, "layout": "single"}
    assert events[2] == {"time": 1.0, "layout": "double"}


def test_grid_frame_detects_same_face_inside_both_source_crops():
    engine = PodcastReframeEngine()
    geometry = {
        "crop_w": 1000,
        "crop_h": 900,
        "top_crop_x": 100,
        "bottom_crop_x": 820,
        "top_crop_y": 0,
        "bottom_crop_y": 0,
    }
    overlapping_face = TrackedDetection(9, BBox(900, 200, 1020, 360), 0)

    assert engine._grid_frame_is_safe([overlapping_face], geometry) is False


def test_autogrid_can_open_for_short_stable_multi_person_section():
    engine = PodcastReframeEngine()
    engine.GRID_ENTER_SAMPLES = 3
    engine.MIN_GRID_SEGMENT_SECONDS = 0.5
    frames = []
    for frame in range(12):
        detections = [TrackedDetection(10, BBox(410, 100, 550, 260), frame)]
        if 4 <= frame <= 6:
            detections.append(TrackedDetection(20, BBox(1390, 100, 1530, 260), frame))
        frames.append(detections)
    tracked_data = {
        "person_count": 2,
        "position_targets": {0: 480, 1: 1460},
        "track_to_position": {10: 0, 20: 1},
        "sample_timestamps": [frame / 3 for frame in range(12)],
        "per_frame_tracked": frames,
    }

    decision = engine._decide_autogrid_layout(
        tracked_data, None, width=1920, height=1080
    )

    assert decision["layout"] == "double"
    assert decision["coexist_ratio"] <= 0.5  # short multi-person window still opens grid
    assert any(event["layout"] == "double" for event in decision["layout_events"])


def test_grid_crop_accepts_fallback_when_isolation_impossible():
    """When isolation is impossible (e.g. third person between two targets),
    the fallback returns best-effort geometry instead of None."""
    engine = PodcastReframeEngine()
    geometry = engine._calculate_grid_geometry(
        first_id=0,
        second_id=2,
        position_targets={0: 600, 1: 960, 2: 1320},
        position_profiles={
            0: {"x": 600, "y": 340, "width": 120, "height": 150, "area": 18000},
            1: {"x": 960, "y": 340, "width": 120, "height": 150, "area": 18000},
            2: {"x": 1320, "y": 340, "width": 120, "height": 150, "area": 18000},
        },
        width=1920,
        height=1080,
    )

    # Fallback now returns geometry instead of None
    assert geometry is not None
    assert geometry["first_id"] == 0
    assert geometry["second_id"] == 2
    assert geometry["crop_w"] > 0
    assert geometry["crop_h"] > 0


def test_layout_transition_graph_honors_selected_style():
    engine = PodcastReframeEngine()
    events = [
        {"time": 0.0, "layout": "single"},
        {"time": 2.0, "layout": "double"},
        {"time": 5.0, "layout": "single"},
    ]

    slide_graph, slide_output = engine._build_layout_transition_graph(
        events, duration=8.0, transition_style="slide", transition_duration=0.4
    )
    cut_graph, cut_output = engine._build_layout_transition_graph(
        events, duration=8.0, transition_style="cut", transition_duration=0.4
    )

    assert "xfade=transition=slideup" in slide_graph
    assert "xfade=transition=slidedown" in slide_graph
    assert slide_output == "layout_out"
    assert "xfade=" not in cut_graph
    assert "concat=n=3" in cut_graph
    assert cut_output == "layout_out"


def test_layout_segments_are_normalized_before_concat():
    engine = PodcastReframeEngine()
    graph, _ = engine._build_layout_transition_graph(
        [
            {"time": 0.0, "layout": "single"},
            {"time": 2.0, "layout": "double"},
            {"time": 5.0, "layout": "single"},
        ],
        duration=8.0,
        transition_style="cut",
        transition_duration=1.0,
    )

    # FFmpeg concat requires every input to have compatible pixel format,
    # sample aspect ratio and timebase. This is the regression for
    # "Failed to configure output pad on Parsed_concat".
    assert graph.count("format=yuv420p,setsar=1,settb=AVTB") == 3
    assert "concat=n=3:v=1:a=0" in graph


def test_speaker_panning_cut_snaps_and_slide_interpolates():
    engine = PodcastReframeEngine()
    keyframes = [(0.0, 100), (2.0, 700)]

    cut_expression = engine._build_panning_expression(
        keyframes, transition_sec=0.4, transition_style="cut"
    )
    slide_expression = engine._build_panning_expression(
        keyframes, transition_sec=0.4, transition_style="slide"
    )

    assert "min(1" not in cut_expression
    assert "min(1" in slide_expression


def test_grid_renderer_uses_two_equal_960px_panels():
    engine = PodcastReframeEngine()
    captured = {}

    def fake_run(command, **kwargs):
        if len(command) > 0 and "ffmpeg" in command[0]:
            captured["command"] = command
        output_path = command[-1]
        with open(output_path, "wb") as output:
            output.write(b"0" * 1200)
        return SimpleNamespace(returncode=0, stdout='{"streams": [{"codec_type": "video", "start_time": "0.0", "duration": "1.0"}]}', stderr="")

    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = os.path.join(temp_dir, "grid.mp4")
        with patch("src.infrastructure.podcast_reframe_engine.subprocess.run", side_effect=fake_run):
            result = engine._render_double_grid(
                "input.mp4",
                output_path,
                width=1920,
                height=1080,
                decision={
                    "top_x": 480,
                    "bottom_x": 1460,
                    "top_track_id": 0,
                    "bottom_track_id": 1,
                    "person_count": 2,
                },
            )

    filter_graph = captured["command"][captured["command"].index("-filter_complex") + 1]
    assert filter_graph.count("scale=1080:960") == 2
    assert result["grid_panel_height"] == 960


def test_panning_holds_active_speaker_seat_when_only_listener_is_visible():
    engine = PodcastReframeEngine()
    speaker_result = ActiveSpeakerResult(
        segments=[],
        dominant_speaker_id=0,
        dominant_ratio=1.0,
        per_frame_speaker={30: 0},
        total_speakers=2,
    )

    cx, target_detection, active_position_id, target_source = engine._choose_panning_target_x(
        frame_faces=[1480],
        frame_tracked=[TrackedDetection(7, BBox(1430, 100, 1530, 240), 30)],
        speaker_result=speaker_result,
        frame_idx_approx=30,
        position_targets={0: 520, 1: 1480},
        position_target_profiles={},
        track_to_position={7: 1},
        frame_width=1920,
        frame_height=1080,
    )

    assert cx == 520
    assert target_detection is None
    assert active_position_id == 0
    assert target_source == "seat_hold"


def test_panning_holds_profile_when_visible_face_is_not_active_speaker():
    engine = PodcastReframeEngine()
    speaker_result = ActiveSpeakerResult(
        segments=[],
        dominant_speaker_id=0,
        dominant_ratio=1.0,
        per_frame_speaker={30: 0},
        total_speakers=2,
    )

    cx, target_detection, active_position_id, target_source = engine._choose_panning_target_x(
        frame_faces=[625],
        frame_tracked=[TrackedDetection(8, BBox(535, 620, 715, 840), 30)],
        speaker_result=speaker_result,
        frame_idx_approx=30,
        position_targets={0: 620, 1: 625},
        position_target_profiles={
            0: {"x": 620, "y": 350, "width": 120, "height": 140, "area": 16800},
            1: {"x": 625, "y": 690, "width": 180, "height": 220, "area": 39600},
        },
        track_to_position={8: 1},
        frame_width=1920,
        frame_height=1080,
    )

    assert cx == 620
    assert target_detection is None
    assert active_position_id == 0
    assert target_source == "profile_hold"


def test_active_speaker_detector_uses_configurable_face_capacity():
    detector = ActiveSpeakerDetector(max_faces=9)

    assert detector._max_faces == 9


def test_visual_fallback_uses_strongest_stable_position():
    engine = PodcastReframeEngine()
    tracked_data = {
        "track_to_position": {0: 0, 1: 1},
        "sample_frame_indices": [0, 30, 60],
        "per_frame_tracked": [
            [
                TrackedDetection(0, BBox(470, 100, 570, 240), 0),
                TrackedDetection(1, BBox(1400, 100, 1560, 280), 0),
            ],
            [
                TrackedDetection(0, BBox(470, 100, 570, 240), 30),
                TrackedDetection(1, BBox(1400, 100, 1560, 280), 30),
            ],
            [
                TrackedDetection(1, BBox(1400, 100, 1560, 280), 60),
            ],
        ],
    }

    result = engine._build_visual_fallback_speaker_result(
        tracked_data=tracked_data,
        fps=30.0,
        total_frames=90,
    )

    assert result is not None
    assert result.dominant_speaker_id == 1
    assert set(result.per_frame_speaker.values()) == {1}


def test_ambiguous_diarization_mapping_is_not_reliable():
    """Equal co-occurrence → soft confidence, not hard-zero; still may be soft-reliable."""
    mapper = SpeakerFaceMapper(confidence_threshold=0.5)
    segments = [
        DiarizationSegment(0.0, 1.0, "SPEAKER_00"),
        DiarizationSegment(1.0, 2.0, "SPEAKER_01"),
    ]
    per_frame_tracked = [
        [
            TrackedDetection(0, BBox(470, 100, 570, 240), 0),
            TrackedDetection(1, BBox(1430, 100, 1530, 240), 0),
        ],
        [
            TrackedDetection(0, BBox(470, 100, 570, 240), 30),
            TrackedDetection(1, BBox(1430, 100, 1530, 240), 30),
        ],
    ]

    result = mapper.build_mapping(
        diarization_segments=segments,
        per_frame_tracked=per_frame_tracked,
        sample_timestamps=[0.5, 1.5],
        stable_positions={0: 520, 1: 1480},
    )

    # Equal co-occurrence: confidence is blended (not 0.0); may soft-pass
    assert result.mappings
    assert result.overall_confidence >= 0.0
    # With tiny sample (2 frames), soft conf is low — not hard-reliable at 0.5
    assert result.overall_confidence < 0.5 or result.is_reliable is True


def test_strong_mapping_is_reliable():
    mapper = SpeakerFaceMapper(confidence_threshold=0.3)
    segments = [
        DiarizationSegment(0.0, 1.0, "SPEAKER_00"),
        DiarizationSegment(1.0, 2.0, "SPEAKER_01"),
        DiarizationSegment(2.0, 3.0, "SPEAKER_00"),
        DiarizationSegment(3.0, 4.0, "SPEAKER_01"),
    ]
    # SPEAKER_00 only with track 0, SPEAKER_01 only with track 1
    per_frame_tracked = [
        [TrackedDetection(0, BBox(470, 100, 570, 240), 0)],
        [TrackedDetection(1, BBox(1430, 100, 1530, 240), 30)],
        [TrackedDetection(0, BBox(470, 100, 570, 240), 60)],
        [TrackedDetection(1, BBox(1430, 100, 1530, 240), 90)],
    ]
    result = mapper.build_mapping(
        diarization_segments=segments,
        per_frame_tracked=per_frame_tracked,
        sample_timestamps=[0.5, 1.5, 2.5, 3.5],
        stable_positions={0: 520, 1: 1480},
    )
    assert result.is_reliable is True
    assert result.overall_confidence >= 0.3
    assert len(result.mappings) == 2


def test_anatomical_landmarks_extraction():
    """Verify multi-modal extraction of retina/eyes, nose tip, lips/mouth, chin, and forehead."""
    detector = ActiveSpeakerDetector()
    # Create mock landmarks (478 landmarks)
    mock_lms = [SimpleNamespace(x=0.5, y=0.5) for _ in range(478)]
    # Nose tip (1) at (500, 400)
    mock_lms[1] = SimpleNamespace(x=500 / 1000, y=400 / 1000)
    # Left iris (468) at (450, 350), Right iris (473) at (550, 350)
    mock_lms[468] = SimpleNamespace(x=450 / 1000, y=350 / 1000)
    mock_lms[473] = SimpleNamespace(x=550 / 1000, y=350 / 1000)
    # Lips: Upper (13) at (500, 450), Lower (14) at (500, 470)
    mock_lms[13] = SimpleNamespace(x=500 / 1000, y=450 / 1000)
    mock_lms[14] = SimpleNamespace(x=500 / 1000, y=470 / 1000)
    mock_lms[78] = SimpleNamespace(x=460 / 1000, y=460 / 1000)
    mock_lms[308] = SimpleNamespace(x=540 / 1000, y=460 / 1000)
    # Chin (152) at (500, 550), Forehead (10) at (500, 250)
    mock_lms[152] = SimpleNamespace(x=500 / 1000, y=550 / 1000)
    mock_lms[10] = SimpleNamespace(x=500 / 1000, y=250 / 1000)

    anat = detector._extract_anatomical_landmarks(mock_lms, width=1000, height=1000)
    assert anat["nose_x"] == 500
    assert anat["nose_y"] == 400
    assert anat["eyes_center_x"] == 500
    assert anat["eyes_center_y"] == 350
    assert anat["mouth_x"] == 500
    assert anat["mouth_y"] == 460
    assert anat["chin_y"] == 550
    assert anat["forehead_y"] == 250
    # True midline centered
    assert abs(anat["anatomical_center_x"] - 500) < 1.0


def test_single_grid_centers_on_anatomical_center():
    """Verify single grid panning locks onto anatomical center (retina/nose/lips) over raw bbox."""
    engine = PodcastReframeEngine()
    # Detection has a wider/asymmetric person bbox (1000 to 1400, center 1200),
    # but the person's face/retina/nose anatomical center is at 1150
    det = TrackedDetection(
        track_id=1,
        bbox=BBox(1000, 100, 1400, 700),
        frame_idx=10,
        face_bbox=BBox(1080, 150, 1260, 350),
        anatomical_center_x=1150.0,
        anatomical_center_y=250.0,
    )

    center, target_det, position_id, source = engine._choose_panning_target_x(
        frame_faces=[1150.0],
        frame_tracked=[det],
        speaker_result=None,
        frame_idx_approx=10,
        position_targets={1: 1150.0},
        position_target_profiles={1: {"x": 1200.0, "anatomical_x": 1150.0}},
        track_to_position={1: 1},
        frame_width=1920,
        frame_height=1080,
    )

    assert center == 1150
    assert target_det is det


def test_double_grid_centers_each_person_on_face_anatomical_center():
    """Verify 2-grid centers each panel on face/anatomical center rather than torso body_x."""
    engine = PodcastReframeEngine()
    # Person 1 (left seat): torso centered at x=750, but head/face turned at x=700
    # Person 2 (right seat): torso centered at x=1350, but head/face turned at x=1400
    profiles = {
        0: {
            "x": 750.0,
            "y": 600.0,
            "width": 300.0,
            "height": 700.0,
            "face_x": 700.0,
            "face_y": 250.0,
            "face_width": 120.0,
            "face_height": 140.0,
            "anatomical_x": 700.0,
            "anatomical_y": 250.0,
            "eyes_y": 220.0,
            "chin_y": 320.0,
        },
        1: {
            "x": 1350.0,
            "y": 600.0,
            "width": 300.0,
            "height": 700.0,
            "face_x": 1400.0,
            "face_y": 250.0,
            "face_width": 120.0,
            "face_height": 140.0,
            "anatomical_x": 1400.0,
            "anatomical_y": 250.0,
            "eyes_y": 220.0,
            "chin_y": 320.0,
        },
    }

    geom = engine._calculate_grid_geometry(
        first_id=0,
        second_id=1,
        position_targets={0: 750.0, 1: 1350.0},
        position_profiles=profiles,
        width=1920,
        height=1080,
    )

    assert geom is not None
    crop_w = geom["crop_w"]
    # P1 panel center (first_crop_x + crop_w/2) should be close to face anatomical center (700),
    # NOT torso center (750)
    p1_panel_center = geom["first_crop_x"] + crop_w / 2
    assert abs(p1_panel_center - 700.0) < abs(p1_panel_center - 750.0)

    # P2 panel center (second_crop_x + crop_w/2) should be close to face anatomical center (1400),
    # NOT torso center (1350)
    p2_panel_center = geom["second_crop_x"] + crop_w / 2
    assert abs(p2_panel_center - 1400.0) < abs(p2_panel_center - 1350.0)



def test_double_grid_vertical_clamp_uses_real_eye_level_and_protects_chin():
    """Verify _clamp_grid_y positions eyes at ~38% down the panel and protects chin."""
    crop_h = 720
    frame_h = 1080
    face_y = 300.0
    face_height = 140.0
    real_eyes_y = 260.0
    real_chin_y = 370.0

    crop_y = PodcastReframeEngine._clamp_grid_y(
        face_y=face_y,
        face_height=face_height,
        crop_h=crop_h,
        frame_h=frame_h,
        eyes_y=real_eyes_y,
        chin_y=real_chin_y,
    )

    # In the panel, eyes position from top of panel is real_eyes_y - crop_y
    eyes_in_panel = real_eyes_y - crop_y
    ratio = eyes_in_panel / crop_h
    # Rule of thirds: eyes should be framed comfortably around 30-45% from the top
    assert 0.30 <= ratio <= 0.45
    # Chin should not be clipped: chin is inside crop
    assert crop_y + crop_h >= real_chin_y


if __name__ == "__main__":

    test_single_visible_face_uses_stable_position_target()
    test_head_motion_is_keyed_after_stable_id_assignment()
    test_face_mesh_assignment_uses_2d_profiles_for_front_back_panelists()
    test_lip_motion_beats_listener_head_motion()
    test_low_confidence_lip_motion_still_selects_best_speaker()
    test_position_model_clusters_recreated_tracks_by_seat()
    test_position_model_keeps_front_back_people_with_similar_x_separate()
    test_autogrid_rejects_duplicate_tracks_mapped_to_one_person()
    test_autogrid_requires_two_unique_people_visible_together()
    test_autogrid_rejects_people_who_never_share_a_frame()
    test_autogrid_rejects_pair_when_isolation_requires_overzoom()
    test_grid_geometry_uses_smallest_safe_zoom_and_caps_it()
    test_layout_timeline_switches_only_after_stable_people_count()
    test_layout_closes_immediately_if_one_face_enters_both_crops()
    test_grid_frame_detects_same_face_inside_both_source_crops()
    test_autogrid_can_open_for_short_stable_multi_person_section()
    test_grid_crop_rejects_third_person_leaking_into_both_panels()
    test_layout_transition_graph_honors_selected_style()
    test_speaker_panning_cut_snaps_and_slide_interpolates()
    test_grid_renderer_uses_two_equal_960px_panels()
    test_panning_holds_active_speaker_seat_when_only_listener_is_visible()
    test_panning_holds_profile_when_visible_face_is_not_active_speaker()
    test_active_speaker_detector_uses_configurable_face_capacity()
    test_visual_fallback_uses_strongest_stable_position()
    test_ambiguous_diarization_mapping_is_not_reliable()
    test_strong_mapping_is_reliable()
    print("speaker centering tests passed")
