"""Tests for V2 subtitle word preparation for Remotion."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.subtitle_words import sanitize_subtitle_words, mark_important_keywords


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


def test_important_keywords_are_capped_by_video_duration():
    words = [{"word": f"keyword{i}", "start": i * .2, "end": i * .2 + .15} for i in range(200)]
    marked = mark_important_keywords(words, 60)
    assert sum(bool(word["highlight"]) for word in marked) == 10


def test_existing_ai_keywords_are_preserved_within_quota():
    words = [{"word": "penting", "highlight": True}, {"word": "ordinary", "highlight": False}]
    marked = mark_important_keywords(words, 6)
    assert marked[0]["highlight"] is True


def test_sanitize_subtitle_words_suppresses_words_during_ai_text_blocked_ranges():
    raw_words = [
        {"word": "awal", "start": 1.0, "end": 1.5},
        {"word": "intro", "start": 1.6, "end": 2.0},
        # AI Text active from 3.0 to 6.0: these 3 words should be hidden
        {"word": "ini", "start": 3.2, "end": 3.6},
        {"word": "sedang", "start": 3.7, "end": 4.5},
        {"word": "fokus", "start": 4.6, "end": 5.8},
        # Reappear after AI Text ends at 6.0
        {"word": "kembali", "start": 6.2, "end": 6.8},
        {"word": "muncul", "start": 6.9, "end": 7.5},
    ]

    # Blocked range for AI Cinematic Text from 3.0s to 6.0s
    blocked = [(3.0, 6.0)]
    words = sanitize_subtitle_words(raw_words, clip_duration=10.0, blocked_ranges=blocked)

    words_text = [w["word"] for w in words]
    assert words_text == ["awal", "intro", "kembali", "muncul"]
    assert "ini" not in words_text
    assert "sedang" not in words_text
    assert "fokus" not in words_text
    assert words[0]["start"] == 1.0
    assert words[2]["start"] == 6.2


if __name__ == "__main__":
    test_sanitize_subtitle_words_sorts_clamps_and_dedupes()
    test_important_keywords_are_capped_by_video_duration()
    test_existing_ai_keywords_are_preserved_within_quota()
    test_sanitize_subtitle_words_suppresses_words_during_ai_text_blocked_ranges()
    print("v2 subtitle word tests passed")

