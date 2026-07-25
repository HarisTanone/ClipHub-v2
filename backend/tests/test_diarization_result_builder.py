"""DiarizationResultBuilder — orphan track soft-map + 0-segment regression."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.diarization_result_builder import DiarizationResultBuilder
from src.infrastructure.speaker_diarizer import DiarizationResult, DiarizationSegment
from src.infrastructure.speaker_face_mapper import MappingResult, SpeakerFaceMapping


def _diarization():
    return DiarizationResult(
        segments=[
            DiarizationSegment(start=0.0, end=5.0, speaker="SPEAKER_00"),
            DiarizationSegment(start=5.0, end=12.0, speaker="SPEAKER_01"),
            DiarizationSegment(start=12.0, end=20.0, speaker="SPEAKER_00"),
        ],
        speaker_count=2,
        speakers=["SPEAKER_00", "SPEAKER_01"],
        total_speech_duration=20.0,
        audio_duration=20.0,
    )


def _mapping(track_a=10, track_b=99):
    return MappingResult(
        mappings={
            "SPEAKER_00": SpeakerFaceMapping("SPEAKER_00", track_a, 0.7, 8),
            "SPEAKER_01": SpeakerFaceMapping("SPEAKER_01", track_b, 0.6, 6),
        },
        overall_confidence=0.6,
        is_reliable=True,
    )


def test_builder_soft_maps_orphan_track_not_zero_segments():
    """Mapped track missing from track_to_position must not yield 0 segments.

    Prod clip2: mappings present, track orphan after reliable-filter → 0 segments.
    """
    diar = _diarization()
    mapping = _mapping(track_a=10, track_b=99)  # 99 not in track_to_position
    result = DiarizationResultBuilder.build(
        diarization=diar,
        mapping=mapping,
        fps=30.0,
        total_frames=600,
        stable_positions={10: 400.0},  # only track 10 known
        sample_interval_sec=1.0,
        track_to_position={10: 0},  # orphan 99
    )
    assert len(result.segments) == 3
    assert result.dominant_speaker_id is not None
    speaker_ids = {s.speaker_id for s in result.segments}
    assert 0 in speaker_ids
    assert len(speaker_ids) == 2  # orphan got a seat


def test_builder_empty_track_map_still_emits_from_mapping():
    """Empty track_to_position + non-empty mapping → soft seats for all tracks."""
    diar = _diarization()
    mapping = _mapping(track_a=7, track_b=8)
    result = DiarizationResultBuilder.build(
        diarization=diar,
        mapping=mapping,
        fps=25.0,
        total_frames=500,
        stable_positions={7: 300.0, 8: 900.0},
        sample_interval_sec=1.0,
        track_to_position={},  # fully empty (prod-style filter wipe)
    )
    assert len(result.segments) == 3
    assert len(result.per_frame_speaker) > 0


def test_builder_skips_unmapped_speakers_only():
    """Speakers without face mapping still skipped; mapped ones kept."""
    diar = _diarization()
    mapping = MappingResult(
        mappings={
            "SPEAKER_00": SpeakerFaceMapping("SPEAKER_00", 1, 0.8, 10),
            # SPEAKER_01 unmapped
        },
        overall_confidence=0.8,
        is_reliable=True,
        unmapped_speakers=["SPEAKER_01"],
    )
    result = DiarizationResultBuilder.build(
        diarization=diar,
        mapping=mapping,
        fps=30.0,
        total_frames=600,
        stable_positions={1: 500.0},
        track_to_position={1: 0},
    )
    assert len(result.segments) == 2  # only SPEAKER_00 turns
    assert all(s.speaker_id == 0 for s in result.segments)
