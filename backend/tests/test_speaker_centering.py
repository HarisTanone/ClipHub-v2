"""Tests for speaker-aware centering identity glue."""
import os
import sys

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

    assert result.is_reliable is False


if __name__ == "__main__":
    test_single_visible_face_uses_stable_position_target()
    test_head_motion_is_keyed_after_stable_id_assignment()
    test_face_mesh_assignment_uses_2d_profiles_for_front_back_panelists()
    test_lip_motion_beats_listener_head_motion()
    test_low_confidence_lip_motion_still_selects_best_speaker()
    test_position_model_clusters_recreated_tracks_by_seat()
    test_position_model_keeps_front_back_people_with_similar_x_separate()
    test_panning_holds_active_speaker_seat_when_only_listener_is_visible()
    test_panning_holds_profile_when_visible_face_is_not_active_speaker()
    test_active_speaker_detector_uses_configurable_face_capacity()
    test_visual_fallback_uses_strongest_stable_position()
    test_ambiguous_diarization_mapping_is_not_reliable()
    print("speaker centering tests passed")
