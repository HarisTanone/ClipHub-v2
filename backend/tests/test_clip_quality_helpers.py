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


def test_extract_highlight_and_objects():
    from src.infrastructure.clip_quality_helpers import (
        extract_highlight_keywords,
        extract_objects,
    )
    words = [
        {"word": "saya", "start": 0.0, "end": 0.2, "highlight": False},
        {"word": "IHSG", "start": 1.0, "end": 1.3, "highlight": True},
        {"word": "Rokok", "start": 2.0, "end": 2.4, "highlight": False},
        {"word": "turun", "start": 3.0, "end": 3.3, "highlight": False},
    ]
    hl = extract_highlight_keywords(words)
    assert "IHSG" in hl
    # offline (no AI): proper/highlight + multi-word footage only
    objs = extract_objects(words, ["vape stock"])
    names = {o["word"].lower() for o in objs}
    assert "ihsg" in names
    assert "rokok" in names
    assert any("vape" in o["word"].lower() for o in objs)
    # AI present → exclusive if already ≥3; thin AI may top-up proper only (tested separately)
    ve = [{
        "word": "IHSG", "start": 1.0, "end": 1.3, "label": "IHSG",
        "query_en": "stock market chart indonesia", "source": "ai",
    }, {
        "word": "Rokok", "start": 2.0, "end": 2.4, "label": "Rokok",
        "query_en": "cigarette", "source": "ai",
    }, {
        "word": "Chart", "start": 3.5, "end": 3.8, "label": "Chart",
        "query_en": "stock chart", "source": "ai",
    }]
    ai_full = extract_objects(words, ["vape stock", "Itu"], visual_entities=ve)
    assert len(ai_full) == 3
    assert all(o.get("source") == "ai" for o in ai_full)
    assert not any("vape" in o["word"].lower() for o in ai_full)


def test_write_split_job_meta(tmp_path):
    import json
    from src.infrastructure.clip_quality_helpers import (
        build_clip_analisa,
        write_split_job_meta,
    )
    p1 = build_clip_analisa(
        no=1, rank=1, start=23.0, end=50.0,
        hook="Pejabat salah bicara, IHSG turun", reason="shock",
        score=95,
        words=[
            {"word": "saya", "start": 3.0, "end": 3.1, "highlight": False},
            {"word": "IHSG", "start": 4.0, "end": 4.3, "highlight": True},
        ],
        broll_suggestions=[{"at_time": 5.0, "keyword": "IHSG chart", "template": "x", "duration": 2.0}],
    )
    p2 = build_clip_analisa(
        no=2, rank=2, start=100.0, end=130.0,
        hook="Part 2", score=80, words=[],
    )
    meta_path = write_split_job_meta(
        str(tmp_path),
        job_id="job_e7ed746ac408",
        youtube_url="https://www.youtube.com/watch?v=hEBos5g0qoA",
        aspect_ratio="9:16",
        created_at="2026-07-23",
        clip_payloads=[p1, p2],
        clips_total=2,
        clips_success=2,
    )
    meta = json.loads(open(meta_path).read())
    assert meta["job_id"] == "job_e7ed746ac408"
    assert meta["clips"] == [
        {"no": 1, "path": "json_analisa/clip_1.json"},
        {"no": 2, "path": "json_analisa/clip_2.json"},
    ]
    assert "words" not in meta["clips"][0]
    c1 = json.loads(open(tmp_path / "json_analisa" / "clip_1.json").read())
    assert c1["no"] == 1
    body = c1["clips"][0]
    assert body["hook"].startswith("Pejabat")
    assert "IHSG" in body["highlight_keywords"] or any(
        "ihsg" in k.lower() for k in body["highlight_keywords"]
    )
    assert body["footage_keywords"]
    assert body["objects"]
    assert body["words"]
    assert "virality" in body
    assert "cta" in body
