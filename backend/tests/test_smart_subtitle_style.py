"""Tests for smart editorial subtitle template and keyword highlighting."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.smart_subtitle_style import (
    apply_smart_word_highlights,
    build_smart_editorial_subtitle_style,
    smart_editorial_enabled,
)


def test_smart_editorial_enabled_requires_both_toggles():
    assert smart_editorial_enabled({"smart_camera": True}) is False
    assert smart_editorial_enabled({"smart_subtitle_position": True}) is False
    assert smart_editorial_enabled({
        "smart_camera": True,
        "smart_subtitle_position": True,
    }) is True


def test_build_smart_editorial_subtitle_style_uses_remotion_dual_highlight():
    style = build_smart_editorial_subtitle_style(
        {"positionY": 80, "highlightWords": ["manual"]},
        {"content_type": "gaming", "signals": ["valorant"]},
        position_y=58,
        max_width_pct=86,
    )

    assert style["smartTemplate"] == "editorial_pro_v1"
    assert style["stylePreset"] == "neon_pulse"
    assert style["dualStyleEnabled"] is True
    assert style["highlightGlow"] is True
    assert style["positionY"] == 58.0
    assert style["maxWidthPct"] == 86.0
    assert "manual" in style["highlightWords"]
    assert "valorant" in style["highlightWords"]


def test_apply_smart_word_highlights_marks_hook_keywords():
    words = [
        {"word": "ini", "start": 0.0, "end": 0.1},
        {"word": "valorant", "start": 0.2, "end": 0.4},
        {"word": "clutch", "start": 0.5, "end": 0.7},
        {"word": "terakhir", "start": 0.8, "end": 1.0},
        {"word": "banget", "start": 1.1, "end": 1.3},
    ]

    highlighted = apply_smart_word_highlights(
        words,
        hook_text="Valorant clutch terakhir",
        content_profile={"signals": ["valorant"]},
    )

    marked = [w["word"] for w in highlighted if w.get("highlight")]
    assert "valorant" in marked
    assert any(word in marked for word in ("clutch", "terakhir"))


if __name__ == "__main__":
    test_smart_editorial_enabled_requires_both_toggles()
    test_build_smart_editorial_subtitle_style_uses_remotion_dual_highlight()
    test_apply_smart_word_highlights_marks_hook_keywords()
    print("smart subtitle style tests passed")
