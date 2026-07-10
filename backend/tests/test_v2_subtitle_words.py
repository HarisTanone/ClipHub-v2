"""Tests for V2 subtitle word preparation for Remotion."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.subtitle_words import (
    grid_subtitle_position_y,
    sanitize_subtitle_words,
)


def test_sanitize_subtitle_words_sorts_clamps_and_dedupes():
    raw_words = [
        {"word": "world", "start": 0.12, "end": 0.5},
        {"word": "hello", "start": -0.05, "end": 0.2},
        {"word": "hello", "start": -0.04, "end": 0.22},
        {"word": "late", "start": 9.9, "end": 12.0},
        {"word": "bad", "start": 10.2, "end": 10.4},
        {"word": "tiny", "start": 1.0, "end": 1.01},
        {"word": "", "start": 1.1, "end": 1.3},
    ]

    words = sanitize_subtitle_words(raw_words, clip_duration=10.0)

    assert [w["word"] for w in words] == ["hello", "world", "tiny", "late"]
    assert words[0]["start"] == 0.0
    assert words[-1]["end"] <= 10.0
    assert all(words[i]["start"] > words[i - 1]["start"] for i in range(1, len(words)))
    assert all(w["end"] > w["start"] for w in words)


def test_grid_subtitle_position_for_remotion():
    assert grid_subtitle_position_y("podcast_speaker_emphasis") == 52.0
    assert grid_subtitle_position_y("podcast_double_grid") == 43.0
    assert grid_subtitle_position_y("podcast_group_grid") == 52.0
    assert grid_subtitle_position_y("gaming_gameplay_facecam_grid") == 58.0
    assert grid_subtitle_position_y("podcast_dynamic_panning") is None


if __name__ == "__main__":
    test_sanitize_subtitle_words_sorts_clamps_and_dedupes()
    test_grid_subtitle_position_for_remotion()
    print("v2 subtitle word tests passed")
