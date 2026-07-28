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
            "footage_keywords": ["rokok kretek", "cigarette pack"],
            "objects": [{"word": "iqos", "query_en": "iqos device"}],
            "highlight_keywords": ["Pods"],
            "broll_suggestions": [{"keyword": "vape pen"}],
        }],
    }
    kws = footage_keywords_from_analisa(analisa)
    low = " ".join(kws).lower()
    assert "rokok" in low or "cigarette" in low
    assert "iqos" in low
    assert "pods" in low or "vape" in low


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
    assert s["max_per_clip"] <= 6


def test_extract_objects_prefers_visual_entities():
    from src.infrastructure.clip_quality_helpers import extract_objects

    words = [{"word": "rokok", "start": 4.0, "end": 4.3}]
    ve = [{
        "word": "rokok", "start": 4.0, "end": 4.3, "label": "Rokok",
        "query_en": "cigarette pack close up", "query_id": "rokok close up",
        "source": "ai",
    }]
    out = extract_objects(words, visual_entities=ve)
    assert out and out[0]["source"] == "ai"
    assert "cigarette" in out[0]["query_en"]
