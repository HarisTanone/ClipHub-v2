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


def _speech_frame(face_id: int, x: float, lip: float = 0.05, head: float = 0.0):
    return FaceSpeechFrame(
        face_id=face_id,
        lip_aperture=lip,
        head_motion=head,
        bbox_x=x,
        bbox_y=400,
        nose_x=x,
        nose_y=400,
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

    model = engine._build_position_model(tracked, width=1920)

    assert model["person_count"] == 2
    assert model["track_to_position"][0] == 0
    assert model["track_to_position"][2] == 0
    assert model["track_to_position"][1] == 1


def test_panning_holds_active_speaker_seat_when_only_listener_is_visible():
    engine = PodcastReframeEngine()
    speaker_result = ActiveSpeakerResult(
        segments=[],
        dominant_speaker_id=0,
        dominant_ratio=1.0,
        per_frame_speaker={30: 0},
        total_speakers=2,
    )

    cx, target_detection = engine._choose_panning_target_x(
        frame_faces=[1480],
        frame_tracked=[TrackedDetection(7, BBox(1430, 100, 1530, 240), 30)],
        speaker_result=speaker_result,
        frame_idx_approx=30,
        position_targets={0: 520, 1: 1480},
        track_to_position={7: 1},
        frame_width=1920,
    )

    assert cx == 520
    assert target_detection is None


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
    test_lip_motion_beats_listener_head_motion()
    test_position_model_clusters_recreated_tracks_by_seat()
    test_panning_holds_active_speaker_seat_when_only_listener_is_visible()
    test_ambiguous_diarization_mapping_is_not_reliable()
    print("speaker centering tests passed")
