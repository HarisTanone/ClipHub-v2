"""Test Task 5: SelectiveWhisperTranscriber — word-level on short clips.

Tests cover:
- Offset mapping (local → absolute timestamps)
- Word filtering (only keep words within highlight range)
- Timeout handling
- Whisper failure (returns empty, non-fatal)
- Batch processing (multiple clips)
- words_to_relative utility
- Edge cases (empty segments, no words)
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.selective_whisper import SelectiveWhisperTranscriber
from src.domain.entities import AudioSlice, Word


def run_async(coro):
    return asyncio.run(coro)


def make_slice(rank=1, original_start=50.0, original_end=110.0, padded_start=47.0, padded_end=113.0):
    """Helper to create AudioSlice for testing."""
    return AudioSlice(
        clip_rank=rank,
        audio_path=f"/tmp/clip_{rank:03d}.wav",
        original_start=original_start,
        original_end=original_end,
        padded_start=padded_start,
        padded_end=padded_end,
        duration=padded_end - padded_start,
    )


# ─── Offset Mapping Tests ────────────────────────────────────────────────────

def test_offset_mapping_basic():
    """Words at local 3.0s with padded_start=47.0 → absolute 50.0s."""
    mock_whisper = MagicMock()
    t = SelectiveWhisperTranscriber(mock_whisper)
    audio_slice = make_slice(padded_start=47.0, original_start=50.0, original_end=110.0)

    raw_segments = [{
        "start": 0.0, "end": 10.0, "text": "hello world",
        "words": [
            {"word": "hello", "start": 3.0, "end": 3.5},   # absolute: 50.0-50.5
            {"word": "world", "start": 3.5, "end": 4.0},   # absolute: 50.5-51.0
        ]
    }]

    words = t._apply_offset_and_filter(raw_segments, audio_slice)
    assert len(words) == 2
    assert words[0].word == "hello"
    assert words[0].start == 50.0  # 3.0 + 47.0
    assert words[0].end == 50.5    # 3.5 + 47.0
    assert words[1].start == 50.5
    print("  [PASS] Offset mapping: local → absolute timestamps")


def test_offset_filters_before_highlight():
    """Words in padding region BEFORE highlight are filtered out."""
    mock_whisper = MagicMock()
    t = SelectiveWhisperTranscriber(mock_whisper)
    # Highlight: 50.0-110.0, Padded: 47.0-113.0
    audio_slice = make_slice(padded_start=47.0, original_start=50.0, original_end=110.0)

    raw_segments = [{
        "words": [
            {"word": "padding", "start": 0.5, "end": 1.0},   # absolute: 47.5-48.0 → BEFORE highlight
            {"word": "real", "start": 4.0, "end": 4.5},      # absolute: 51.0-51.5 → IN highlight
        ]
    }]

    words = t._apply_offset_and_filter(raw_segments, audio_slice)
    assert len(words) == 1
    assert words[0].word == "real"
    print("  [PASS] Filters words before highlight range")


def test_offset_filters_after_highlight():
    """Words in padding region AFTER highlight are filtered out."""
    mock_whisper = MagicMock()
    t = SelectiveWhisperTranscriber(mock_whisper)
    audio_slice = make_slice(padded_start=47.0, original_start=50.0, original_end=110.0)

    raw_segments = [{
        "words": [
            {"word": "real", "start": 10.0, "end": 10.5},     # absolute: 57.0 → IN
            {"word": "after", "start": 64.0, "end": 64.5},    # absolute: 111.0 → AFTER (>110+0.5)
        ]
    }]

    words = t._apply_offset_and_filter(raw_segments, audio_slice)
    assert len(words) == 1
    assert words[0].word == "real"
    print("  [PASS] Filters words after highlight range")


def test_offset_boundary_tolerance():
    """Words within ±0.5s of highlight boundaries are kept."""
    mock_whisper = MagicMock()
    t = SelectiveWhisperTranscriber(mock_whisper)
    audio_slice = make_slice(padded_start=47.0, original_start=50.0, original_end=110.0)

    raw_segments = [{
        "words": [
            # Word ends at 49.8 (absolute) → 50.0-0.5=49.5, so 49.8 > 49.5 → KEPT
            {"word": "edge_start", "start": 2.5, "end": 2.8},  # abs: 49.5-49.8 → end < original_start-0.5? 49.8 < 49.5? NO → kept
            # Word starts at 110.3 → 110+0.5=110.5, so 110.3 < 110.5 → KEPT
            {"word": "edge_end", "start": 63.3, "end": 63.8},  # abs: 110.3-110.8 → start > original_end+0.5? 110.3 > 110.5? NO → kept
        ]
    }]

    words = t._apply_offset_and_filter(raw_segments, audio_slice)
    assert len(words) == 2
    print("  [PASS] Boundary tolerance ±0.5s works")


def test_offset_empty_words():
    """Empty word text is skipped."""
    mock_whisper = MagicMock()
    t = SelectiveWhisperTranscriber(mock_whisper)
    audio_slice = make_slice(padded_start=47.0, original_start=50.0, original_end=110.0)

    raw_segments = [{
        "words": [
            {"word": "", "start": 5.0, "end": 5.5},
            {"word": "  ", "start": 6.0, "end": 6.5},
            {"word": "valid", "start": 7.0, "end": 7.5},
        ]
    }]

    words = t._apply_offset_and_filter(raw_segments, audio_slice)
    assert len(words) == 1
    assert words[0].word == "valid"
    print("  [PASS] Empty/whitespace words filtered")


def test_offset_multiple_segments():
    """Handles multiple segments correctly."""
    mock_whisper = MagicMock()
    t = SelectiveWhisperTranscriber(mock_whisper)
    audio_slice = make_slice(padded_start=0.0, original_start=3.0, original_end=60.0)

    raw_segments = [
        {"words": [{"word": "seg1", "start": 5.0, "end": 5.5}]},
        {"words": [{"word": "seg2", "start": 10.0, "end": 10.5}]},
        {"words": [{"word": "seg3", "start": 15.0, "end": 15.5}]},
    ]

    words = t._apply_offset_and_filter(raw_segments, audio_slice)
    assert len(words) == 3
    assert words[0].word == "seg1"
    assert words[2].word == "seg3"
    print("  [PASS] Multiple segments merged correctly")


# ─── transcribe_clip Tests ────────────────────────────────────────────────────

def test_transcribe_clip_success():
    """Successful transcription returns offset words."""
    mock_whisper = AsyncMock()
    mock_whisper.transcribe_clip.return_value = [{
        "start": 0.0, "end": 10.0, "text": "hello world",
        "words": [
            {"word": "hello", "start": 3.0, "end": 3.5},
            {"word": "world", "start": 3.5, "end": 4.0},
        ]
    }]

    t = SelectiveWhisperTranscriber(mock_whisper)
    audio_slice = make_slice(padded_start=47.0, original_start=50.0, original_end=110.0)

    async def run():
        words = await t.transcribe_clip(audio_slice)
        assert len(words) == 2
        assert words[0].start == 50.0
        assert isinstance(words[0], Word)

    run_async(run())
    print("  [PASS] transcribe_clip returns offset words")


def test_transcribe_clip_timeout():
    """Timeout returns empty list (non-fatal)."""
    mock_whisper = AsyncMock()

    async def slow_transcribe(path):
        await asyncio.sleep(10)  # Too slow
        return []

    mock_whisper.transcribe_clip = slow_transcribe
    t = SelectiveWhisperTranscriber(mock_whisper)
    t.CLIP_TIMEOUT = 0.1  # Very short timeout for testing

    audio_slice = make_slice()

    async def run():
        words = await t.transcribe_clip(audio_slice)
        assert words == []

    run_async(run())
    print("  [PASS] Timeout → empty list (non-fatal)")


def test_transcribe_clip_whisper_error():
    """Whisper exception returns empty list (non-fatal)."""
    mock_whisper = AsyncMock()
    mock_whisper.transcribe_clip.side_effect = RuntimeError("Model crashed")

    t = SelectiveWhisperTranscriber(mock_whisper)
    audio_slice = make_slice()

    async def run():
        words = await t.transcribe_clip(audio_slice)
        assert words == []

    run_async(run())
    print("  [PASS] Whisper error → empty list (non-fatal)")


def test_transcribe_clip_empty_result():
    """Empty Whisper result → empty list."""
    mock_whisper = AsyncMock()
    mock_whisper.transcribe_clip.return_value = []

    t = SelectiveWhisperTranscriber(mock_whisper)
    audio_slice = make_slice()

    async def run():
        words = await t.transcribe_clip(audio_slice)
        assert words == []

    run_async(run())
    print("  [PASS] Empty Whisper result → empty list")


# ─── Batch Processing Tests ───────────────────────────────────────────────────

def test_transcribe_all_clips():
    """Batch transcription of multiple clips."""
    mock_whisper = AsyncMock()

    # Different results per clip (based on audio path)
    async def mock_transcribe(path):
        if "001" in path:
            return [{"words": [{"word": "clip1", "start": 5.0, "end": 5.5}]}]
        elif "002" in path:
            return [{"words": [{"word": "clip2", "start": 5.0, "end": 5.5}]}]
        return []

    mock_whisper.transcribe_clip = mock_transcribe
    t = SelectiveWhisperTranscriber(mock_whisper)

    slices = [
        make_slice(rank=1, padded_start=47.0, original_start=50.0, original_end=110.0),
        make_slice(rank=2, padded_start=197.0, original_start=200.0, original_end=260.0),
    ]

    async def run():
        results = await t.transcribe_all_clips(slices, max_parallel=2)
        assert 1 in results
        assert 2 in results
        assert len(results[1]) == 1
        assert results[1][0].word == "clip1"
        assert results[1][0].start == 52.0  # 5.0 + 47.0
        assert results[2][0].word == "clip2"
        assert results[2][0].start == 202.0  # 5.0 + 197.0

    run_async(run())
    print("  [PASS] Batch transcription of multiple clips")


def test_transcribe_all_clips_partial_failure():
    """Some clips fail → still returns results for successful ones."""
    mock_whisper = AsyncMock()

    async def mock_transcribe(path):
        if "001" in path:
            return [{"words": [{"word": "ok", "start": 5.0, "end": 5.5}]}]
        raise RuntimeError("clip 2 failed")

    mock_whisper.transcribe_clip = mock_transcribe
    t = SelectiveWhisperTranscriber(mock_whisper)

    slices = [
        make_slice(rank=1, padded_start=47.0, original_start=50.0, original_end=110.0),
        make_slice(rank=2, padded_start=197.0, original_start=200.0, original_end=260.0),
    ]

    async def run():
        results = await t.transcribe_all_clips(slices)
        assert 1 in results
        assert 2 in results
        assert len(results[1]) == 1  # Success
        assert results[2] == []      # Failed gracefully

    run_async(run())
    print("  [PASS] Partial failure handled gracefully")


# ─── Utility Tests ────────────────────────────────────────────────────────────

def test_words_to_relative():
    """Convert absolute → relative timestamps."""
    words = [
        Word(word="hello", start=50.0, end=50.5, highlight=False),
        Word(word="world", start=51.0, end=51.5, highlight=True),
    ]
    clip_start = 50.0
    relative = SelectiveWhisperTranscriber.words_to_relative(words, clip_start)

    assert relative[0].start == 0.0   # 50.0 - 50.0
    assert relative[0].end == 0.5
    assert relative[1].start == 1.0   # 51.0 - 50.0
    assert relative[1].end == 1.5
    assert relative[1].highlight is True  # Preserved
    print("  [PASS] words_to_relative converts correctly")


def test_words_to_relative_preserves_highlight():
    """Highlight flag preserved during conversion."""
    words = [
        Word(word="a", start=100.0, end=100.5, highlight=True),
        Word(word="b", start=101.0, end=101.5, highlight=False),
    ]
    relative = SelectiveWhisperTranscriber.words_to_relative(words, 100.0)
    assert relative[0].highlight is True
    assert relative[1].highlight is False
    print("  [PASS] Highlight flag preserved in conversion")


if __name__ == "__main__":
    print("\n=== Task 5 Tests: SelectiveWhisperTranscriber ===\n")
    # Offset mapping
    test_offset_mapping_basic()
    test_offset_filters_before_highlight()
    test_offset_filters_after_highlight()
    test_offset_boundary_tolerance()
    test_offset_empty_words()
    test_offset_multiple_segments()
    # transcribe_clip
    test_transcribe_clip_success()
    test_transcribe_clip_timeout()
    test_transcribe_clip_whisper_error()
    test_transcribe_clip_empty_result()
    # Batch
    test_transcribe_all_clips()
    test_transcribe_all_clips_partial_failure()
    # Utility
    test_words_to_relative()
    test_words_to_relative_preserves_highlight()
    print("\n=== ALL TASK 5 TESTS PASSED (14/14) ===\n")
