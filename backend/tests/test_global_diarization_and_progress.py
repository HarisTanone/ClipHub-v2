"""Unit tests for Global Diarization Slicing, Caching, and Real-Time Clip Progress Tracking."""
import pytest
from src.infrastructure.speaker_diarizer import (
    DiarizationResult,
    DiarizationSegment,
    slice_diarization,
    get_cached_global_diarization,
    set_cached_global_diarization,
    _GLOBAL_DIARIZATION_CACHE,
)
from src.infrastructure.sse_progress_emitter import SSEProgressEmitter


def test_slice_diarization_basic():
    global_res = DiarizationResult(
        segments=[
            DiarizationSegment(start=10.0, end=20.0, speaker="SPEAKER_00"),
            DiarizationSegment(start=25.0, end=35.0, speaker="SPEAKER_01"),
            DiarizationSegment(start=40.0, end=60.0, speaker="SPEAKER_00"),
            DiarizationSegment(start=70.0, end=80.0, speaker="SPEAKER_01"),
        ],
        speaker_count=2,
        speakers=["SPEAKER_00", "SPEAKER_01"],
        total_speech_duration=50.0,
        audio_duration=100.0,
    )

    # Slice clip from 20.0s to 50.0s (duration = 30s)
    # Overlapping segments:
    # - 25.0 to 35.0 -> rel: 5.0 to 15.0 (SPEAKER_01)
    # - 40.0 to 60.0 -> rel: 20.0 to 30.0 (SPEAKER_00 clamped to 50.0)
    sliced = slice_diarization(global_res, clip_start=20.0, clip_end=50.0)

    assert sliced.audio_duration == 30.0
    assert len(sliced.segments) == 2
    assert sliced.speaker_count == 2
    assert sliced.speakers == ["SPEAKER_00", "SPEAKER_01"]

    seg1 = sliced.segments[0]
    assert seg1.speaker == "SPEAKER_01"
    assert seg1.start == 5.0
    assert seg1.end == 15.0

    seg2 = sliced.segments[1]
    assert seg2.speaker == "SPEAKER_00"
    assert seg2.start == 20.0
    assert seg2.end == 30.0
    assert sliced.total_speech_duration == 20.0


def test_slice_diarization_out_of_bounds():
    global_res = DiarizationResult(
        segments=[
            DiarizationSegment(start=10.0, end=20.0, speaker="SPEAKER_00"),
        ],
        speaker_count=1,
        speakers=["SPEAKER_00"],
        total_speech_duration=10.0,
        audio_duration=50.0,
    )

    # Slice range with no speech (30.0s to 40.0s)
    sliced = slice_diarization(global_res, clip_start=30.0, clip_end=40.0)
    assert sliced.audio_duration == 10.0
    assert len(sliced.segments) == 0
    assert sliced.speaker_count == 0
    assert sliced.total_speech_duration == 0.0


def test_global_diarization_cache():
    _GLOBAL_DIARIZATION_CACHE.clear()
    key = "diarization_test_video.mp4"
    res = DiarizationResult(
        segments=[DiarizationSegment(start=0.0, end=5.0, speaker="SPEAKER_00")],
        speaker_count=1,
        speakers=["SPEAKER_00"],
        total_speech_duration=5.0,
        audio_duration=10.0,
    )

    set_cached_global_diarization(key, res)
    cached = get_cached_global_diarization(key)
    assert cached is not None
    assert cached.speaker_count == 1

    # Check non-existent key
    assert get_cached_global_diarization("non_existent") is None


def test_sse_emit_clip_progress():
    emitter = SSEProgressEmitter()
    job_id = "test_job_eta_01"

    emitter.emit_clip_progress(
        job_id=job_id,
        clip_rank=3,
        total_clips=12,
        stage="Reframing 9:16",
        eta_seconds=45,
    )

    state = emitter.get_current_state(job_id)
    assert state is not None
    assert state["active_clip"]["rank"] == 3
    assert state["active_clip"]["total"] == 12
    assert state["active_clip"]["stage"] == "Reframing 9:16"
    assert state["active_clip"]["eta_seconds"] == 45
    assert state["clips_progress"]["3"]["stage"] == "Reframing 9:16"
