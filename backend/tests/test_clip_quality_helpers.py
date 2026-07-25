"""Tests for clip quality helpers (thumb, virality, CTA, dead-air)."""
from src.infrastructure.clip_quality_helpers import (
    smart_thumbnail_seek,
    virality_breakdown,
    suggest_cta,
    dead_air_gaps,
    retention_trim_hints,
)


def test_smart_thumbnail_prefers_peak_word_not_fixed_one_second():
    words = [
        {"word": "halo", "start": 0.5, "end": 0.7},
        {"word": "RAHASIA", "start": 2.0, "end": 2.8},  # longer token mid-hook
        {"word": "ini", "start": 3.0, "end": 3.2},
    ]
    seek = smart_thumbnail_seek(words, duration=20.0, hook="Rahasia gila")
    assert 1.5 <= seek <= 3.5
    assert seek != 1.0


def test_smart_thumbnail_fallback_without_words():
    seek = smart_thumbnail_seek(None, duration=40.0)
    assert seek == 10.0  # 25% of 40


def test_virality_breakdown_explainable_factors():
    v = virality_breakdown(
        score=80,
        hook="Kenapa BBM mahal banget?",
        reason="conflict energy shock",
        duration=30.0,
        words=[{"word": "a", "start": i * 0.3, "end": i * 0.3 + 0.2} for i in range(40)],
        broll_count=2,
    )
    assert v["total"] > 50
    assert "hook_punch" in v
    assert "retention" in v
    assert len(v["factors"]) == 3
    assert v["hook_punch"] > 60  # question + kenapa


def test_dead_air_gaps_detects_long_silence():
    words = [
        {"word": "satu", "start": 0.0, "end": 0.4},
        {"word": "dua", "start": 3.0, "end": 3.3},  # 2.6s gap
        {"word": "tiga", "start": 3.5, "end": 3.8},
    ]
    gaps = dead_air_gaps(words)
    assert len(gaps) == 1
    assert gaps[0]["duration"] >= 2.5


def test_retention_trim_suggests_cuts():
    words = [
        {"word": "a", "start": 0.0, "end": 0.5},
        {"word": "b", "start": 4.0, "end": 4.3},
    ]
    hints = retention_trim_hints(words, duration=10.0)
    assert hints["should_trim"] is True
    assert hints["suggested_cuts"]


def test_cta_question_hook_prefers_comment():
    cta = suggest_cta("Kenapa ini mahal?", "biasa", rank=2)
    assert cta["kind"] == "comment"
    assert cta["at"] == "end"
    assert cta["duration"] == 1.5


def test_cta_rank_one_save():
    cta = suggest_cta("Tips hemat", "tips", rank=1)
    assert cta["kind"] == "save"
