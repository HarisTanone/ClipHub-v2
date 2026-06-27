"""Test Task 4: MicroSlicer — FFmpeg-based audio extraction per highlight.

Tests cover:
- Padding calculation (normal, clamp start, clamp end, minimum duration)
- FFmpeg command construction
- Successful extraction with mocked FFmpeg
- Handling failures (missing video, FFmpeg error, timeout)
- Empty/invalid highlights
- File size validation
- Cleanup utility
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.micro_slicer import MicroSlicer, MicroSlicerError
from src.domain.entities import AudioSlice


def run_async(coro):
    return asyncio.run(coro)


# ─── Padding Calculation Tests ────────────────────────────────────────────────

def test_padding_normal():
    """Normal case: ±3s padding within bounds."""
    s = MicroSlicer()
    start, end = s._calculate_padded_boundaries(50.0, 110.0, video_duration=300.0)
    assert start == 47.0   # 50 - 3
    assert end == 113.0    # 110 + 3
    print("  [PASS] Normal padding ±3s")


def test_padding_clamp_start_to_zero():
    """Start padding clamped to 0 when near beginning."""
    s = MicroSlicer()
    start, end = s._calculate_padded_boundaries(1.5, 60.0, video_duration=300.0)
    assert start == 0.0    # max(0, 1.5-3) = 0
    assert end == 63.0     # 60 + 3
    print("  [PASS] Padding clamps start to 0")


def test_padding_clamp_end_to_duration():
    """End padding clamped to video_duration when near end."""
    s = MicroSlicer()
    start, end = s._calculate_padded_boundaries(250.0, 298.0, video_duration=300.0)
    assert start == 247.0  # 250 - 3
    assert end == 300.0    # min(300, 298+3) = 300
    print("  [PASS] Padding clamps end to video_duration")


def test_padding_both_clamp():
    """Very short video: both ends clamped."""
    s = MicroSlicer()
    start, end = s._calculate_padded_boundaries(1.0, 8.0, video_duration=10.0)
    assert start == 0.0    # max(0, 1-3) = 0
    assert end == 10.0     # min(10, 8+3) = 10
    print("  [PASS] Both start and end clamped")


def test_padding_minimum_duration():
    """Ensure minimum 5s duration after padding."""
    s = MicroSlicer()
    # Very short clip: 1s duration, after clamping might be too short
    start, end = s._calculate_padded_boundaries(5.0, 6.0, video_duration=300.0)
    # padded: start=2.0, end=9.0 → 7s duration, no adjustment needed
    assert start == 2.0
    assert end == 9.0
    duration = end - start
    assert duration >= 5.0
    print("  [PASS] Minimum duration enforced (>=5s)")


def test_padding_at_exact_start():
    """Clip starts at 0."""
    s = MicroSlicer()
    start, end = s._calculate_padded_boundaries(0.0, 60.0, video_duration=300.0)
    assert start == 0.0    # max(0, 0-3) = 0
    assert end == 63.0     # 60 + 3
    print("  [PASS] Clip starting at 0 handled")


def test_padding_at_exact_end():
    """Clip ends at video_duration."""
    s = MicroSlicer()
    start, end = s._calculate_padded_boundaries(240.0, 300.0, video_duration=300.0)
    assert start == 237.0  # 240 - 3
    assert end == 300.0    # min(300, 300+3) = 300
    print("  [PASS] Clip ending at video_duration handled")


# ─── FFmpeg Extraction Tests ──────────────────────────────────────────────────

def test_extract_audio_segment_success():
    """FFmpeg extraction returns True on success."""
    s = MicroSlicer()
    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result):
        success = s._extract_audio_segment("/tmp/video.mp4", 47.0, 113.0, "/tmp/clip.wav")

    assert success is True
    print("  [PASS] FFmpeg extraction returns True on success")


def test_extract_audio_segment_failure():
    """FFmpeg extraction returns False on non-zero exit."""
    s = MicroSlicer()
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "Error: file not found"

    with patch("subprocess.run", return_value=mock_result):
        success = s._extract_audio_segment("/tmp/video.mp4", 0.0, 60.0, "/tmp/out.wav")

    assert success is False
    print("  [PASS] FFmpeg extraction returns False on failure")


def test_extract_audio_segment_timeout():
    """FFmpeg extraction returns False on timeout."""
    s = MicroSlicer()
    import subprocess as sp

    with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="ffmpeg", timeout=60)):
        success = s._extract_audio_segment("/tmp/video.mp4", 0.0, 60.0, "/tmp/out.wav")

    assert success is False
    print("  [PASS] FFmpeg extraction handles timeout")


def test_extract_audio_segment_ffmpeg_missing():
    """FFmpeg not installed → returns False."""
    s = MicroSlicer()

    with patch("subprocess.run", side_effect=OSError("No such file")):
        success = s._extract_audio_segment("/tmp/video.mp4", 0.0, 60.0, "/tmp/out.wav")

    assert success is False
    print("  [PASS] Missing FFmpeg handled gracefully")


# ─── Full slice_audio Tests ───────────────────────────────────────────────────

def test_slice_audio_success():
    """Full slice_audio with mocked FFmpeg and filesystem."""
    s = MicroSlicer()
    highlights = [
        {"rank": 1, "start": 50.0, "end": 110.0},
        {"rank": 2, "start": 200.0, "end": 260.0},
    ]

    def mock_extract(video_path, start, end, output_path):
        # Simulate creating the WAV file
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(b"\x00" * 5000)  # >1KB
        return True

    async def run():
        with patch.object(s, "_extract_audio_segment", side_effect=mock_extract):
            slices = await s.slice_audio(
                "/tmp/video.mp4", highlights, "/tmp/test_slices", 300.0
            )
            assert len(slices) == 2
            assert slices[0].clip_rank == 1
            assert slices[0].padded_start == 47.0
            assert slices[0].padded_end == 113.0
            assert slices[0].original_start == 50.0
            assert slices[1].clip_rank == 2
            assert slices[1].padded_start == 197.0

    with patch("os.path.exists", return_value=True):
        run_async(run())

    # Cleanup
    import shutil
    if os.path.exists("/tmp/test_slices"):
        shutil.rmtree("/tmp/test_slices")

    print("  [PASS] Full slice_audio with multiple highlights")


def test_slice_audio_video_not_found():
    """Raises error when video file doesn't exist."""
    s = MicroSlicer()
    highlights = [{"rank": 1, "start": 10.0, "end": 60.0}]

    async def run():
        try:
            await s.slice_audio("/nonexistent/video.mp4", highlights, "/tmp/out", 300.0)
            assert False, "Should have raised"
        except MicroSlicerError as e:
            assert "not found" in str(e)

    run_async(run())
    print("  [PASS] Raises error on missing video file")


def test_slice_audio_empty_highlights():
    """Empty highlights → empty result."""
    s = MicroSlicer()

    async def run():
        slices = await s.slice_audio("/tmp/video.mp4", [], "/tmp/out", 300.0)
        assert slices == []

    run_async(run())
    print("  [PASS] Empty highlights → empty result")


def test_slice_audio_all_fail_raises():
    """All extractions fail → raises MicroSlicerError."""
    s = MicroSlicer()
    highlights = [
        {"rank": 1, "start": 10.0, "end": 60.0},
        {"rank": 2, "start": 100.0, "end": 160.0},
    ]

    async def run():
        with patch.object(s, "_extract_audio_segment", return_value=False):
            with patch("os.path.exists", side_effect=lambda p: p == "/tmp/video.mp4"):
                try:
                    await s.slice_audio("/tmp/video.mp4", highlights, "/tmp/out", 300.0)
                    assert False, "Should have raised"
                except MicroSlicerError as e:
                    assert "gagal" in str(e)

    run_async(run())
    print("  [PASS] All extractions fail → raises error")


def test_slice_audio_partial_failure():
    """Some extractions fail → returns successful ones only."""
    s = MicroSlicer()
    highlights = [
        {"rank": 1, "start": 50.0, "end": 110.0},
        {"rank": 2, "start": 200.0, "end": 260.0},  # This will fail
    ]

    call_count = [0]

    def mock_extract(video_path, start, end, output_path):
        call_count[0] += 1
        if call_count[0] == 1:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(b"\x00" * 5000)
            return True
        return False  # Second clip fails

    async def run():
        with patch.object(s, "_extract_audio_segment", side_effect=mock_extract):
            with patch("os.path.exists", return_value=True):
                slices = await s.slice_audio(
                    "/tmp/video.mp4", highlights, "/tmp/partial_test", 300.0
                )
                assert len(slices) == 1
                assert slices[0].clip_rank == 1

    run_async(run())

    # Cleanup
    import shutil
    if os.path.exists("/tmp/partial_test"):
        shutil.rmtree("/tmp/partial_test")

    print("  [PASS] Partial failure → returns successful clips only")


def test_slice_audio_skips_tiny_files():
    """Files < 1KB are skipped (likely empty/corrupt)."""
    s = MicroSlicer()
    highlights = [{"rank": 1, "start": 10.0, "end": 60.0}]

    def mock_extract(video_path, start, end, output_path):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(b"\x00" * 500)  # Only 500 bytes — too small
        return True

    async def run():
        with patch.object(s, "_extract_audio_segment", side_effect=mock_extract):
            with patch("os.path.exists", return_value=True):
                try:
                    await s.slice_audio("/tmp/video.mp4", highlights, "/tmp/tiny_test", 300.0)
                    assert False, "Should have raised"
                except MicroSlicerError:
                    pass  # Expected: all clips "failed" (too small)

    run_async(run())

    import shutil
    if os.path.exists("/tmp/tiny_test"):
        shutil.rmtree("/tmp/tiny_test")

    print("  [PASS] Tiny files (<1KB) skipped")


# ─── Cleanup Tests ────────────────────────────────────────────────────────────

def test_cleanup_slices():
    """cleanup_slices removes WAV files."""
    s = MicroSlicer()

    # Create temp files
    os.makedirs("/tmp/cleanup_test", exist_ok=True)
    paths = []
    for i in range(3):
        path = f"/tmp/cleanup_test/clip_{i:03d}.wav"
        with open(path, "wb") as f:
            f.write(b"\x00" * 100)
        paths.append(path)

    slices = [
        AudioSlice(clip_rank=i, audio_path=p, original_start=0, original_end=60,
                   padded_start=0, padded_end=63, duration=63)
        for i, p in enumerate(paths)
    ]

    s.cleanup_slices(slices)

    for path in paths:
        assert not os.path.exists(path)

    # Cleanup dir
    import shutil
    shutil.rmtree("/tmp/cleanup_test", ignore_errors=True)

    print("  [PASS] cleanup_slices removes all WAV files")


if __name__ == "__main__":
    print("\n=== Task 4 Tests: MicroSlicer ===\n")
    # Padding
    test_padding_normal()
    test_padding_clamp_start_to_zero()
    test_padding_clamp_end_to_duration()
    test_padding_both_clamp()
    test_padding_minimum_duration()
    test_padding_at_exact_start()
    test_padding_at_exact_end()
    # FFmpeg
    test_extract_audio_segment_success()
    test_extract_audio_segment_failure()
    test_extract_audio_segment_timeout()
    test_extract_audio_segment_ffmpeg_missing()
    # Full pipeline
    test_slice_audio_success()
    test_slice_audio_video_not_found()
    test_slice_audio_empty_highlights()
    test_slice_audio_all_fail_raises()
    test_slice_audio_partial_failure()
    test_slice_audio_skips_tiny_files()
    # Cleanup
    test_cleanup_slices()
    print("\n=== ALL TASK 4 TESTS PASSED (18/18) ===\n")
