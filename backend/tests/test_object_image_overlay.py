"""Object image+text overlay — unit checks (no network). AI entities, no lexicon."""
from __future__ import annotations

import numpy as np
import pytest


def test_bilingual_queries_from_ai_entity():
    from src.infrastructure.object_image_overlay import bilingual_queries

    id_q, en_q, label = bilingual_queries({
        "word": "rokok",
        "label": "Rokok",
        "query_id": "rokok kretek close up",
        "query_en": "cigarette pack smoking close up",
    })
    assert "rokok" in id_q.lower()
    assert "cigarette" in en_q.lower()
    assert label == "Rokok"

    # bare string: generic close-up only (no synonym table)
    id2, en2, lab2 = bilingual_queries("IQOS")
    assert "iqos" in id2.lower()
    assert "iqos" in en2.lower()
    assert "Iqos" in lab2 or "IQOS" in lab2


def test_pick_object_mentions_from_ai_objects():
    from src.infrastructure.object_image_overlay import pick_object_mentions

    words = [
        {"word": "hari", "start": 2.0, "end": 2.2},
        {"word": "ini", "start": 2.3, "end": 2.4},
        {"word": "rokok", "start": 5.0, "end": 5.4},
        {"word": "dan", "start": 5.5, "end": 5.6},
        {"word": "iqos", "start": 9.0, "end": 9.3},
    ]
    # Without AI objects, bare short words are not auto-lexicon-picked
    bare = pick_object_mentions(words, max_items=3, clip_duration=30.0)
    # Soft heuristic may still pick long/highlight — not required
    ai_objs = [
        {
            "word": "rokok", "start": 5.0, "end": 5.4, "label": "Rokok",
            "query_id": "rokok kretek", "query_en": "cigarette pack close up",
            "source": "ai",
        },
        {
            "word": "iqos", "start": 9.0, "end": 9.3, "label": "IQOS",
            "query_id": "iqos device", "query_en": "iqos heated tobacco close up",
            "source": "ai",
        },
    ]
    picks = pick_object_mentions(words, ai_objs, max_items=3, clip_duration=30.0)
    labels = {p["label"].lower() for p in picks}
    assert "rokok" in labels
    assert any("iqos" in x for x in labels)
    assert any(p["query_en"] for p in picks)
    assert all(p["at_time"] >= 1.5 for p in picks)


def test_score_image_relevance_prefers_match():
    from src.infrastructure.object_image_overlay import score_image_relevance

    good = score_image_relevance(
        word="rokok",
        label="Rokok",
        query_id="rokok kretek",
        query_en="cigarette pack smoking close up",
        photo_meta={"alt": "close up cigarette pack smoking product", "url": "x"},
        clip_hook="bahaya rokok",
    )
    bad = score_image_relevance(
        word="rokok",
        label="Rokok",
        query_id="rokok kretek",
        query_en="cigarette pack smoking close up",
        photo_meta={"alt": "mountain landscape sunset beach skyline", "url": "y"},
    )
    assert good > bad
    # hook-only match without entity token must stay weak (stops same junk reuse)
    hook_only = score_image_relevance(
        word="Itu",
        label="Itu",
        query_id="Itu close up",
        query_en="Itu product close up",
        photo_meta={"alt": "bahaya rokok cigarette pack", "url": "z"},
        clip_hook="Berhenti rokok, hidup baru",
    )
    assert hook_only < 0.25


def test_photo_queries_multi():
    from src.infrastructure.object_image_overlay import _photo_queries

    qs = _photo_queries(
        "rokok kretek close up",
        "cigarette pack close up",
        ["iqos device heated tobacco", "rokok electric"],
        word="Aikos",
        label="IQOS",
    )
    assert qs[0].lower() in ("aikos", "cigarette pack close up")  # bare word or EN first
    assert any("iqos" in q.lower() for q in qs)
    assert len(qs) == len(set(q.lower() for q in qs))


def test_fallback_picks_spoken_products():
    from src.infrastructure.groq_analyzer import GroqAnalyzer

    words = [
        {"word": "Nah", "start": 3.0, "end": 3.2},
        {"word": "Merokok", "start": 25.26, "end": 25.6},
        {"word": "Rokok", "start": 53.456, "end": 53.9},
        {"word": "Aikos.", "start": 69.438, "end": 69.858},
        {"word": "Shisha,", "start": 75.978, "end": 76.711},
        {"word": "pot.", "start": 77.444, "end": 78.178},
    ]
    fb = GroqAnalyzer._fallback_visual_entities_from_words(words, duration=127.0, limit=6)
    names = {o["word"].lower() for o in fb}
    assert "aikos" in names or "shisha" in names or "rokok" in names
    assert "nah" not in names


def test_build_overlay_card_rounded():
    from src.infrastructure.object_image_overlay import build_overlay_card
    import cv2
    import tempfile
    import os

    img = np.zeros((200, 200, 3), dtype=np.uint8)
    img[:] = (40, 80, 200)
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "t.jpg")
        cv2.imwrite(path, img)
        card = build_overlay_card(path, "Rokok", box_px=120, corner_radius=16, show_label=True)
    assert card is not None
    assert card.shape[2] == 4
    assert card.shape[0] > 120  # label strip
    assert int(card[0, 0, 3]) < 50


def test_build_clip_analisa_uses_visual_entities():
    from src.infrastructure.clip_quality_helpers import build_clip_analisa

    p = build_clip_analisa(
        no=1, rank=1, start=0, end=20,
        hook="Rokok dan IQOS", reason="produk",
        score=90,
        words=[
            {"word": "rokok", "start": 4.0, "end": 4.3, "highlight": True},
            {"word": "iqos", "start": 6.0, "end": 6.4, "highlight": True},
        ],
        visual_entities=[{
            "word": "rokok", "start": 4.0, "end": 4.3, "label": "Rokok",
            "query_id": "rokok kretek close up",
            "query_en": "cigarette pack smoking close up",
            "source": "ai",
        }],
        object_overlay_events=[{"label": "Rokok", "at_time": 4.0}],
    )
    body = p["clips"][0]
    assert body["object_overlay_events"]
    assert body["visual_entities"]
    objs = body["objects"]
    assert objs
    assert any(o.get("query_en") for o in objs)
    assert any(o.get("source") == "ai" for o in objs)
    joined = " ".join(body["footage_keywords"]).lower()
    assert "cigarette" in joined or "rokok" in joined


def test_footage_keywords_from_analisa():
    from src.infrastructure.object_image_overlay import footage_keywords_from_analisa

    analisa = {
        "no": 1,
        "clips": [{
            "footage_keywords": ["rokok kretek", "cigarette pack", "Itu"],
            "objects": [
                {"word": "iqos", "query_en": "iqos device", "source": "ai"},
                {"word": "Nah", "query_en": "Nah product close up", "source": "heuristic"},
            ],
            "highlight_keywords": ["Pods"],
            "broll_suggestions": [{"keyword": "vape pen"}],
            "visual_entities": [{
                "word": "rokok", "query_en": "cigarette pack close up",
                "query_id": "rokok kretek", "source": "ai",
            }],
        }],
    }
    kws = footage_keywords_from_analisa(analisa)
    low = " ".join(kws).lower()
    assert "rokok" in low or "cigarette" in low
    assert "vape" in low
    # bare highlight / heuristic filler must not pollute
    assert "pods" not in low
    assert "nah product" not in low
    assert "itu" not in low.split()  # single-token "Itu" skipped


def test_anim_offsets():
    from src.infrastructure.object_image_overlay import _anim_offset

    dx, dy, a = _anim_offset(0.0, 2.4, "slide_right", 100, 120)
    assert dx > 0 and a < 1.0
    dx2, dy2, a2 = _anim_offset(1.0, 2.4, "slide_right", 100, 120)
    assert dx2 == 0 and a2 == 1.0
    _, dy3, _ = _anim_offset(0.0, 2.4, "slide_down", 100, 120)
    assert dy3 < 0


def test_style_normalise_clamps():
    from src.infrastructure.object_image_overlay import normalise_object_overlay_style

    s = normalise_object_overlay_style({
        "animation": "from_mars",
        "position": "somewhere",
        "box_size_ratio": 9.0,
        "max_per_clip": 99,
    })
    assert s["animation"] == "slide_right"
    assert s["position"] == "top_right"
    assert s["box_size_ratio"] <= 0.55
    assert s["max_per_clip"] <= 10


def test_extract_objects_prefers_visual_entities():
    from src.infrastructure.clip_quality_helpers import extract_objects

    words = [
        {"word": "Itu", "start": 3.0, "end": 3.2, "highlight": False},
        {"word": "rokok", "start": 4.0, "end": 4.3, "highlight": True},
        {"word": "Menyusahkan", "start": 5.0, "end": 5.4, "highlight": True},
        {"word": "Aikos.", "start": 69.4, "end": 69.8, "highlight": False},
        {"word": "Shisha,", "start": 76.0, "end": 76.5, "highlight": False},
    ]
    ve = [{
        "word": "1 Januari", "start": 14.9, "end": 15.2, "label": "Kalender 1 Januari",
        "query_en": "desk calendar showing january first",
        "query_id": "kalender meja menunjukkan tanggal satu januari",
        "source": "ai",
    }]
    out = extract_objects(words, footage_keywords=["Itu", "Menyusahkan"], visual_entities=ve)
    assert out[0]["source"] == "ai"
    assert "calendar" in out[0]["query_en"].lower() or "kalender" in out[0]["query_id"].lower()
    # no heuristic filler; thin AI top-up proper brands only
    assert not any(o.get("source") == "heuristic" for o in out)
    names = {o["word"].lower().rstrip(".,") for o in out}
    assert "aikos" in names or "shisha" in names or "menyusahkan" in names
    assert "itu" not in names
    assert "rokok" not in names  # lowercase, not proper top-up


def test_score_calendar_query_not_diluted():
    from src.infrastructure.object_image_overlay import score_image_relevance

    sc = score_image_relevance(
        word="1 Januari",
        label="Kalender 1 Januari",
        query_id="kalender meja menunjukkan tanggal satu januari",
        query_en="desk calendar showing january first",
        photo_meta={
            "alt": "calendar, a book, date, january, february, week, month, desk",
            "url": "x",
            "query": "desk calendar january",
        },
        search_queries=["desk calendar january", "kalender 1 januari"],
    )
    assert sc >= 0.35
    hook_only = score_image_relevance(
        word="Itu",
        label="Itu",
        query_id="Itu close up",
        query_en="Itu product close up",
        photo_meta={"alt": "cigarette pack smoking", "url": "y", "query": "Itu close up"},
        clip_hook="Berhenti rokok",
    )
    assert hook_only < 0.25


def test_pick_drops_heuristic_when_ai_present():
    from src.infrastructure.object_image_overlay import pick_object_mentions

    objects = [
        {
            "word": "1 Januari", "start": 14.9, "end": 15.2, "label": "Kalender",
            "query_id": "kalender 1 januari", "query_en": "desk calendar january",
            "source": "ai",
        },
        {
            "word": "Itu", "start": 3.12, "end": 3.36, "label": "Itu",
            "query_id": "Itu close up", "query_en": "Itu product close up",
            "source": "heuristic",
        },
        {
            "word": "Nah", "start": 10.64, "end": 11.1, "label": "Nah",
            "query_en": "Nah product close up", "source": "heuristic",
        },
    ]
    picks = pick_object_mentions([], objects, max_items=3, clip_duration=30.0)
    assert len(picks) == 1
    assert picks[0]["source"] == "ai"


def test_pick_spreads_brands_not_rokok_family():
    from src.infrastructure.object_image_overlay import pick_object_mentions

    objects = [
        {"word": "1 Januari", "start": 14.9, "end": 15.2, "label": "Kalender",
         "query_en": "desk calendar january", "source": "ai"},
        {"word": "Merokok", "start": 25.26, "end": 25.6, "label": "Merokok",
         "query_en": "Merokok", "source": "fallback"},
        {"word": "Rokok", "start": 53.4, "end": 53.9, "label": "Rokok",
         "query_en": "Rokok", "source": "fallback"},
        {"word": "Aikos", "start": 69.4, "end": 69.8, "label": "Aikos",
         "query_en": "Aikos", "source": "fallback"},
        {"word": "Shisha", "start": 76.0, "end": 76.7, "label": "Shisha",
         "query_en": "Shisha", "source": "fallback"},
    ]
    picks = pick_object_mentions([], objects, max_items=3, clip_duration=127.0)
    words = {p["word"].lower() for p in picks}
    # merokok/rokok same family → at most one; late brands get a slot
    assert not ({"merokok", "rokok"} <= words)
    assert any(w in words for w in ("aikos", "shisha", "1 januari", "januari"))
    assert len(picks) == 3
    times = [p["at_time"] for p in picks]
    assert max(times) - min(times) > 20


def test_words_from_analisa_fallback():
    from src.infrastructure.object_image_overlay import words_from_analisa

    analisa = {"clips": [{"words": [
        {"word": "Aikos.", "start": 69.4, "end": 69.8},
        {"word": "Shisha", "start": 76.0, "end": 76.5},
    ]}]}
    ws = words_from_analisa(analisa)
    assert len(ws) == 2
    assert ws[0]["word"] == "Aikos."
    assert abs(ws[1]["start"] - 76.0) < 0.01


def test_api_trusted_clears_default_min_relevance():
    from src.infrastructure.object_image_overlay import score_image_relevance

    # ID bare query "Merokok" → EN alt cigarette (no entity token in alt)
    sc = score_image_relevance(
        word="Merokok",
        label="Merokok",
        query_id="Merokok close up",
        query_en="Merokok",
        photo_meta={
            "alt": "cigarette, smoke, burning cigarette, smoking, ash",
            "url": "x",
            "query": "Merokok",
        },
    )
    assert sc >= 0.35  # must pass default OBJECT_OVERLAY_MIN_RELEVANCE
