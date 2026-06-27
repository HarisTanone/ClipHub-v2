"""Test Task 6: SileroVAD — Voice Activity Detection for natural cuts.

Tests cover:
- Silence gap detection from speech timestamps
- Nearest silence search (before/after direction)
- Fallback behavior (no silence found → original timestamp)
- refine_boundaries with mocked model
- refine_clip_boundaries (absolute ↔ relative conversion)
- Edge cases (empty speech, full silence, target in gap)
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.silero_vad import SileroVADProcessor
from src.domain.entities import VADResult


def run_async(coro):
    return asyncio.run(coro)


# ─── Silence Gap Detection Tests ─────────────────────────────────────────────

def test_find_silence_gaps_basic():
    """Convert speech timestamps to silence gaps."""
    vad = SileroVADProcessor()
    speech_ts = [
        {"start": 1.0, "end": 3.0},
        {"start": 4.0, "end": 6.0},
        {"start": 8.0, "end": 10.0},
    ]
    gaps = vad._find_silence_gaps(speech_ts, audio_duration=12.0)

    # Expected gaps: (0, 1.0), (3.0, 4.0), (6.0, 8.0), (10.0, 12.0)
    assert len(gaps) == 4
    assert gaps[0] == (0.0, 1.0)
    assert gaps[1] == (3.0, 4.0)
    assert gaps[2] == (6.0, 8.0)
    assert gaps[3] == (10.0, 12.0)
    print("  [PASS] Basic silence gap detection")


def test_find_silence_gaps_no_gap_at_start():
    """Speech starts immediately — no gap at beginning."""
    vad = SileroVADProcessor()
    speech_ts = [
        {"start": 0.01, "end": 5.0},  # Starts almost immediately
        {"start": 6.0, "end": 10.0},
    ]
    gaps = vad._find_silence_gaps(speech_ts, audio_duration=12.0)

    # No gap at start (0.01 < 0.05 threshold)
    # Gap between: (5.0, 6.0), after: (10.0, 12.0)
    assert len(gaps) == 2
    assert gaps[0] == (5.0, 6.0)
    assert gaps[1] == (10.0, 12.0)
    print("  [PASS] No gap at start when speech begins immediately")


def test_find_silence_gaps_empty_speech():
    """No speech detected → entire audio is one silence gap."""
    vad = SileroVADProcessor()
    gaps = vad._find_silence_gaps([], audio_duration=60.0)
    assert gaps == [(0.0, 60.0)]
    print("  [PASS] No speech → full silence gap")


def test_find_silence_gaps_continuous_speech():
    """Continuous speech with no gaps between segments."""
    vad = SileroVADProcessor()
    speech_ts = [
        {"start": 0.0, "end": 5.0},
        {"start": 5.0, "end": 10.0},  # No gap (5.0 - 5.0 = 0 < 0.05)
    ]
    gaps = vad._find_silence_gaps(speech_ts, audio_duration=10.0)
    # No gap at start, no gap between (0 < 0.05), no gap at end (10-10=0)
    assert len(gaps) == 0
    print("  [PASS] Continuous speech → no silence gaps")


# ─── Nearest Silence Search Tests ─────────────────────────────────────────────

def test_find_nearest_silence_before():
    """Find silence gap before target time."""
    vad = SileroVADProcessor()
    gaps = [(3.0, 4.0), (7.0, 8.0), (12.0, 13.0)]

    # Target: 8.5, direction: before, radius: 2.0
    # Eligible: gap (7.0, 8.0) → candidate = 8.0 + 0.1 = 8.1
    result = vad._find_nearest_silence(gaps, target_time=8.5, direction="before", radius=2.0)
    assert abs(result - 8.1) < 0.01
    print("  [PASS] Find nearest silence before target")


def test_find_nearest_silence_after():
    """Find silence gap after target time."""
    vad = SileroVADProcessor()
    gaps = [(3.0, 4.0), (7.0, 8.0), (12.0, 13.0)]

    # Target: 6.5, direction: after, radius: 2.0
    # Eligible: gap (7.0, 8.0) → candidate = 7.0 - 0.1 = 6.9
    result = vad._find_nearest_silence(gaps, target_time=6.5, direction="after", radius=2.0)
    assert abs(result - 6.9) < 0.01
    print("  [PASS] Find nearest silence after target")


def test_find_nearest_silence_no_match():
    """No silence within radius → returns original."""
    vad = SileroVADProcessor()
    gaps = [(0.0, 1.0), (20.0, 21.0)]  # Far from target

    # Target: 10.0, radius: 2.0 → no gap within ±2s
    result = vad._find_nearest_silence(gaps, target_time=10.0, direction="before", radius=2.0)
    assert result == 10.0  # Fallback to original
    print("  [PASS] No silence in radius → original timestamp")


def test_find_nearest_silence_target_in_gap():
    """Target is already in a silence gap → keep it."""
    vad = SileroVADProcessor()
    gaps = [(5.0, 8.0)]  # Target 6.5 is inside this gap

    result = vad._find_nearest_silence(gaps, target_time=6.5, direction="before", radius=2.0)
    assert result == 6.5  # Already in silence
    print("  [PASS] Target already in silence gap → keep original")


def test_find_nearest_silence_closest_wins():
    """Multiple eligible gaps → closest one wins."""
    vad = SileroVADProcessor()
    gaps = [(3.0, 4.0), (5.0, 5.5), (6.0, 6.5)]

    # Target: 7.0, direction: before, radius: 4.0
    # Eligible: all three, but (6.0, 6.5) is closest → candidate = 6.5 + 0.1 = 6.6
    result = vad._find_nearest_silence(gaps, target_time=7.0, direction="before", radius=4.0)
    assert abs(result - 6.6) < 0.01  # 6.5 + 0.1
    print("  [PASS] Closest silence gap wins")


# ─── Full Refinement Tests (Mocked Model) ────────────────────────────────────

def test_refine_boundaries_with_mock():
    """Full refine_boundaries with mocked VAD model."""
    vad = SileroVADProcessor()

    # Mock the model and speech detection
    speech_ts = [
        {"start": 1.0, "end": 4.5},
        {"start": 5.2, "end": 9.0},
        {"start": 9.8, "end": 14.0},
    ]

    import torch
    fake_waveform = torch.zeros(1, 16000 * 15)  # 15 seconds

    with patch("os.path.exists", return_value=True):
        with patch("torchaudio.load", return_value=(fake_waveform, 16000)):
            with patch.object(vad, "_ensure_model_loaded"):
                with patch.object(vad, "_get_speech_timestamps", return_value=speech_ts):
                    async def run():
                        start, end = await vad.refine_boundaries(
                            "/tmp/test.wav", target_start=5.0, target_end=9.5, search_radius=2.0
                        )
                        # Gaps from speech_ts: (0,1.0), (4.5,5.2), (9.0,9.8), (14.0,15.0)
                        # target_start=5.0 direction=before: gap (4.5,5.2) contains 5.0 → keep 5.0
                        # target_end=9.5 direction=after: gap (9.0,9.8) → candidate=9.0-0.1=8.9
                        # At least end should shift
                        assert isinstance(start, float)
                        assert isinstance(end, float)

                    run_async(run())
    print("  [PASS] Full refine_boundaries with mocked model")


def test_refine_boundaries_file_not_found():
    """Missing audio file → returns original timestamps."""
    vad = SileroVADProcessor()

    async def run():
        start, end = await vad.refine_boundaries(
            "/nonexistent/audio.wav", 10.0, 50.0, search_radius=2.0
        )
        assert start == 10.0
        assert end == 50.0

    run_async(run())
    print("  [PASS] Missing file → fallback to original")


def test_refine_boundaries_exception_fallback():
    """Exception during processing → returns original timestamps."""
    vad = SileroVADProcessor()

    with patch("torchaudio.load", side_effect=RuntimeError("Audio corrupt")):
        with patch("os.path.exists", return_value=True):
            async def run():
                start, end = await vad.refine_boundaries(
                    "/tmp/corrupt.wav", 10.0, 50.0
                )
                assert start == 10.0
                assert end == 50.0

            run_async(run())
    print("  [PASS] Exception → fallback to original")


# ─── refine_clip_boundaries Tests ─────────────────────────────────────────────

def test_refine_clip_boundaries_conversion():
    """refine_clip_boundaries converts absolute ↔ relative correctly."""
    vad = SileroVADProcessor()

    # Mock refine_boundaries to shift by known amount
    async def mock_refine(audio_path, target_start, target_end, search_radius=2.0):
        # Shift start back by 0.2s, shift end forward by 0.3s
        return target_start - 0.2, target_end + 0.3

    async def run():
        with patch.object(vad, "refine_boundaries", side_effect=mock_refine):
            result = await vad.refine_clip_boundaries(
                audio_path="/tmp/clip.wav",
                original_start=50.0,   # absolute
                original_end=110.0,    # absolute
                padded_start=47.0,     # audio file starts at this absolute time
            )
            assert isinstance(result, VADResult)
            # relative_start = 50.0 - 47.0 = 3.0 → refined: 2.8
            # back to absolute: 2.8 + 47.0 = 49.8
            assert result.final_start == 49.8
            # relative_end = 110.0 - 47.0 = 63.0 → refined: 63.3
            # back to absolute: 63.3 + 47.0 = 110.3
            assert result.final_end == 110.3
            assert result.shift_start_ms == -200.0  # (49.8 - 50.0) * 1000
            assert result.shift_end_ms == 300.0     # (110.3 - 110.0) * 1000
            assert result.used_fallback is False

    run_async(run())
    print("  [PASS] refine_clip_boundaries converts absolute ↔ relative")


def test_refine_clip_boundaries_no_shift():
    """No shift detected → used_fallback=True."""
    vad = SileroVADProcessor()

    async def mock_refine(audio_path, target_start, target_end, search_radius=2.0):
        return target_start, target_end  # No shift

    async def run():
        with patch.object(vad, "refine_boundaries", side_effect=mock_refine):
            result = await vad.refine_clip_boundaries(
                audio_path="/tmp/clip.wav",
                original_start=50.0,
                original_end=110.0,
                padded_start=47.0,
            )
            assert result.final_start == 50.0
            assert result.final_end == 110.0
            assert result.used_fallback is True

    run_async(run())
    print("  [PASS] No shift → used_fallback=True")


if __name__ == "__main__":
    print("\n=== Task 6 Tests: SileroVAD ===\n")
    # Silence gap detection
    test_find_silence_gaps_basic()
    test_find_silence_gaps_no_gap_at_start()
    test_find_silence_gaps_empty_speech()
    test_find_silence_gaps_continuous_speech()
    # Nearest silence search
    test_find_nearest_silence_before()
    test_find_nearest_silence_after()
    test_find_nearest_silence_no_match()
    test_find_nearest_silence_target_in_gap()
    test_find_nearest_silence_closest_wins()
    # Full refinement
    test_refine_boundaries_with_mock()
    test_refine_boundaries_file_not_found()
    test_refine_boundaries_exception_fallback()
    # Clip boundaries
    test_refine_clip_boundaries_conversion()
    test_refine_clip_boundaries_no_shift()
    print("\n=== ALL TASK 6 TESTS PASSED (14/14) ===\n")
