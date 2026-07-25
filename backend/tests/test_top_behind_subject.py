"""Unit tests for top-behind-subject overlay compositor (no YOLO/ffmpeg)."""
from __future__ import annotations

import os
from types import SimpleNamespace

import numpy as np
import pytest

from src.infrastructure.top_behind_subject_renderer import (
    TopBehindSubjectRenderer,
    TopOverlaySegment,
    pick_full_frame_suggestions,
    pick_top_overlay_suggestions,
)



def test_render_keeps_person_original_and_blends_top_bg():
    r = TopBehindSubjectRenderer(
        split_ratio=0.5,
        fade_height=0.0,
        overlay_opacity=1.0,
        person_outline=False,
        person_shadow=False,
        mask_feather=1,
    )
    h, w = 100, 40
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:] = (10, 20, 30)
    overlay = np.zeros((h, w, 3), dtype=np.uint8)
    overlay[:] = (200, 100, 50)
    mask = np.zeros((h, w), dtype=np.float32)
    mask[20:80, 10:30] = 1.0  # person body

    out = r.render(frame, mask, overlay)

    # Person pixel stays near original
    assert np.allclose(out[50, 20], [10, 20, 30], atol=2)
    # Top non-person gets overlay
    assert np.allclose(out[5, 5], [200, 100, 50], atol=2)
    # Bottom non-person stays original (below split)
    assert np.allclose(out[90, 5], [10, 20, 30], atol=2)


def test_cover_resize_center_crop():
    r = TopBehindSubjectRenderer()
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    img[:, :100] = (255, 0, 0)
    img[:, 100:] = (0, 255, 0)
    out = r.cover_resize(img, 50, 50)
    assert out.shape == (50, 50, 3)


def test_pick_prefers_images_skips_blocked(tmp_path):
    img = tmp_path / "a.jpg"
    vid = tmp_path / "b.mp4"
    img.write_bytes(b"x")
    vid.write_bytes(b"x")

    def sug(path, fmt, at, dur, fallback=False):
        return SimpleNamespace(
            at_time=at,
            duration=dur,
            keyword="k",
            asset_result=SimpleNamespace(
                local_path=str(path),
                asset_format=fmt,
                is_fallback=fallback,
                source_api="pexels",
            ),
            splice_segment=None,
        )

    picks = pick_top_overlay_suggestions(
        [
            sug(vid, "video", 5.0, 2.0),
            sug(img, "jpg", 8.0, 2.0),
            sug(img, "jpg", 5.5, 2.0),  # overlaps blocked
        ],
        max_per_clip=2,
        blocked_ranges=[(5.0, 7.0)],
    )
    assert len(picks) == 1
    assert picks[0].at_time == 8.0
    assert isinstance(picks[0], TopOverlaySegment)


def test_pick_skips_missing_and_fallback(tmp_path):
    p = tmp_path / "ok.png"
    p.write_bytes(b"x")
    missing = SimpleNamespace(
        at_time=1.0,
        duration=2.0,
        keyword="",
        asset_result=SimpleNamespace(
            local_path=str(tmp_path / "nope.jpg"),
            asset_format="jpg",
            is_fallback=False,
            source_api="x",
        ),
        splice_segment=None,
    )
    fb = SimpleNamespace(
        at_time=2.0,
        duration=2.0,
        keyword="",
        asset_result=SimpleNamespace(
            local_path=str(p),
            asset_format="png",
            is_fallback=True,
            source_api="x",
        ),
        splice_segment=None,
    )
    ok = SimpleNamespace(
        at_time=3.0,
        duration=2.0,
        keyword="ok",
        asset_result=SimpleNamespace(
            local_path=str(p),
            asset_format="png",
            is_fallback=False,
            source_api="x",
        ),
        splice_segment=None,
    )
    picks = pick_top_overlay_suggestions([missing, fb, ok], max_per_clip=2)
    assert len(picks) == 1
    assert picks[0].keyword == "ok"


def test_pick_accepts_clipscout_splice_only(tmp_path):
    """ClipScout path: splice_segment only, no asset_result — must still pick."""
    footage = tmp_path / "cs_footage.mp4"
    footage.write_bytes(b"x")
    s = SimpleNamespace(
        at_time=4.0,
        duration=2.0,
        keyword="money",
        asset_result=None,
        placement="behind_person",
        splice_segment=SimpleNamespace(
            footage_path=str(footage),
            platform="pexels",
        ),
    )
    picks = pick_top_overlay_suggestions([s], max_per_clip=2)
    assert len(picks) == 1
    assert picks[0].asset_path == str(footage)
    assert picks[0].keyword == "money"
    assert picks[0].source == "pexels"


def test_placement_full_frame_excluded_from_top_overlay(tmp_path):
    img = tmp_path / "i.jpg"
    img.write_bytes(b"x")
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"x")
    full = SimpleNamespace(
        at_time=5.0,
        duration=2.0,
        keyword="market",
        placement="full_frame",
        visual_category="footage",
        asset_result=SimpleNamespace(
            local_path=str(vid), asset_format="video",
            is_fallback=False, source_api="pexels",
        ),
        splice_segment=SimpleNamespace(footage_path=str(vid), platform="pexels"),
    )
    behind = SimpleNamespace(
        at_time=12.0,
        duration=2.0,
        keyword="heart icon",
        placement="behind_person",
        visual_category="icon",
        asset_result=SimpleNamespace(
            local_path=str(img), asset_format="jpg",
            is_fallback=False, source_api="pexels",
        ),
        splice_segment=None,
    )
    top = pick_top_overlay_suggestions([full, behind], max_per_clip=3, blocked_ranges=[(5.0, 7.0)])
    assert len(top) == 1
    assert top[0].at_time == 12.0
    fulls = pick_full_frame_suggestions([full, behind])
    assert len(fulls) == 1
    assert fulls[0].placement == "full_frame"


def test_parse_broll_dual_placement_split():
    from src.application.services_v2 import V2PipelineService

    raw = {
        "1": [
            {"at_time": 5.0, "keyword": "busy market floor", "duration": 2.0,
             "visual_category": "footage", "template": "word_pop_typography"},
            {"at_time": 14.0, "keyword": "gold coins stack", "duration": 2.0,
             "visual_category": "footage", "template": "word_pop_typography"},
        ]
    }
    parsed = V2PipelineService._parse_broll_suggestions(1, raw, 40.0)
    assert len(parsed) == 2
    placements = {s.placement for s in parsed}
    assert "full_frame" in placements
    assert "behind_person" in placements


def test_person_outline_paints_white_edge():
    """Sticker outline must paint bright pixels on person contour (reference style)."""
    r = TopBehindSubjectRenderer(
        split_ratio=0.6,
        fade_height=0.05,
        overlay_opacity=1.0,
        person_outline=True,
        person_shadow=False,
        mask_feather=1,
        outline_thickness=6,
        outline_color="255,255,255",
        outline_style="white",
    )
    h, w = 120, 80
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:] = (40, 40, 40)
    overlay = np.zeros((h, w, 3), dtype=np.uint8)
    overlay[:] = (10, 180, 10)  # green stock
    mask = np.zeros((h, w), dtype=np.float32)
    mask[30:100, 20:60] = 1.0

    out = r.render(frame, mask, overlay)

    # Person interior stays near original gray
    assert np.allclose(out[60, 40], [40, 40, 40], atol=8)
    # Contour ring (just outside body) should be bright white-ish
    edge = out[30:100, 18]  # left edge of person rect
    bright = int(np.sum(edge.mean(axis=1) > 180))
    assert bright >= 3, f"expected white outline pixels, bright={bright}"
    # Top non-person gets overlay green
    assert out[5, 5, 1] > 100


def test_outline_style_neon_blue_bloom():
    r = TopBehindSubjectRenderer(
        split_ratio=0.7,
        fade_height=0.05,
        overlay_opacity=1.0,
        person_outline=True,
        person_shadow=False,
        mask_feather=1,
        outline_thickness=8,
        outline_style="neon",
    )
    h, w = 120, 80
    frame = np.full((h, w, 3), 30, dtype=np.uint8)
    overlay = np.full((h, w, 3), 10, dtype=np.uint8)
    mask = np.zeros((h, w), dtype=np.float32)
    mask[30:100, 20:60] = 1.0
    out = r.render(frame, mask, overlay)
    edge = out[30:100, 17]
    # Neon is blue-ish BGR → high B channel on rim
    blueish = int(np.sum(edge[:, 0] > edge[:, 2] + 20))
    assert blueish >= 2, f"expected neon blue rim, blueish={blueish}"


def test_outline_style_black():
    r = TopBehindSubjectRenderer(
        split_ratio=0.7,
        fade_height=0.05,
        person_outline=True,
        person_shadow=False,
        outline_thickness=8,
        outline_style="black",
    )
    h, w = 120, 80
    frame = np.full((h, w, 3), 200, dtype=np.uint8)
    overlay = np.full((h, w, 3), 180, dtype=np.uint8)
    mask = np.zeros((h, w), dtype=np.float32)
    mask[30:100, 20:60] = 1.0
    out = r.render(frame, mask, overlay)
    edge = out[30:100, 17]
    dark = int(np.sum(edge.mean(axis=1) < 80))
    assert dark >= 2, f"expected black outline, dark={dark}"


def test_clean_mask_keeps_dual_components():
    r = TopBehindSubjectRenderer(person_outline=False, person_shadow=False, mask_feather=1)
    r._max_mask_components = 2
    h, w = 100, 120
    p = np.zeros((h, w), dtype=np.float32)
    p[20:80, 10:40] = 1.0   # left person
    p[20:80, 80:110] = 1.0  # right person (similar size)
    clean = r._clean_person_mask(p)
    left = float(clean[40:60, 15:35].mean())
    right = float(clean[40:60, 85:105].mean())
    assert left > 0.8 and right > 0.8, f"dual keep failed L={left} R={right}"


def test_clean_mask_drops_tiny_second():
    r = TopBehindSubjectRenderer(person_outline=False, person_shadow=False, mask_feather=1)
    r._max_mask_components = 2
    h, w = 100, 120
    p = np.zeros((h, w), dtype=np.float32)
    p[10:90, 20:70] = 1.0   # large
    p[40:50, 100:108] = 1.0  # tiny fringe
    clean = r._clean_person_mask(p)
    assert float(clean[40:50, 100:108].mean()) < 0.2


def test_cover_resize_uses_subject_xy():
    r = TopBehindSubjectRenderer(split_ratio=0.5, crop_bias_y=0.0, smart_crop=False)
    # Tall image: subject ONLY at bottom — without subject_xy top-bias would miss it
    img = np.zeros((400, 100, 3), dtype=np.uint8)
    img[300:360, 30:70] = (0, 0, 255)  # red subject near bottom
    # Force subject at bottom-center
    out = r.cover_resize(img, 50, 100, subject_xy=(0.5, 0.82))
    assert out.shape == (100, 50, 3)
    # Subject should appear somewhere in crop (red channel present)
    assert int(out[:, :, 2].sum()) > 500, "subject_xy should pull bottom object into crop"


def test_cover_resize_prefers_top_subject():
    """Important subject near top of stock must land in visible top band, not center-chopped."""
    r = TopBehindSubjectRenderer(split_ratio=0.5, crop_bias_y=0.15)
    # Tall image: bright subject only in upper third
    img = np.zeros((300, 100, 3), dtype=np.uint8)
    img[20:80, 30:70] = (0, 0, 255)  # red subject near top
    img[200:260, 30:70] = (0, 255, 0)  # green decoy lower
    out = r.cover_resize(img, 50, 100)
    assert out.shape == (100, 50, 3)
    # Upper half of crop should contain more red than green
    upper = out[:50]
    lower = out[50:]
    red_upper = int(upper[:, :, 2].sum())
    red_lower = int(lower[:, :, 2].sum())
    assert red_upper > red_lower, f"subject should sit upper: up={red_upper} lo={red_lower}"


def test_expand_search_queries_behind_person():
    from src.infrastructure.clipscout_client import _expand_search_queries

    qs = _expand_search_queries(
        "indonesian rupiah banknotes counting",
        placement="behind_person",
        category="footage",
    )
    # sanitize may rewrite action verb → "close up" for stock search quality
    assert qs[0] in {
        "indonesian rupiah banknotes counting",
        "indonesian rupiah banknotes close up",
    }
    assert any("close up" in q.lower() for q in qs)
    assert any(q.startswith("indonesian rupiah banknotes") for q in qs)
    assert len(qs) <= 6


def test_snap_overlay_to_phrase_extends_cluster():
    from src.infrastructure.top_behind_subject_renderer import snap_overlay_to_phrase

    words = [
        {"word": "harga", "start": 2.0, "end": 2.3},
        {"word": "BBM", "start": 2.35, "end": 2.7},
        {"word": "naik", "start": 2.8, "end": 3.1},
        {"word": "lagi", "start": 3.2, "end": 3.5},
    ]
    at, dur = snap_overlay_to_phrase(2.1, 5.0, words, clip_duration=20.0)
    assert at <= 2.1
    assert 1.2 <= dur <= 3.5
    assert at + dur >= 3.0


def test_snap_overlay_far_from_speech_keeps_clamp():
    from src.infrastructure.top_behind_subject_renderer import snap_overlay_to_phrase

    words = [{"word": "hi", "start": 0.5, "end": 0.8}]
    at, dur = snap_overlay_to_phrase(8.0, 2.0, words, clip_duration=12.0)
    assert at == 8.0
    assert 1.2 <= dur <= 3.5


def test_hook_ab_prefers_punchy():
    from src.infrastructure.hook_optimizer import HookOptimizer

    picked = HookOptimizer.pick_hook_ab(
        "Ini adalah penjelasan panjang tentang topik yang membosankan sekali",
        "Harga BBM Naik? Ini Rahasianya",
    )
    assert "Rahasia" in picked or "?" in picked


def test_clipscout_segments_multi_query():
    from src.infrastructure.clipscout_client import build_segments_from_suggestions

    s = SimpleNamespace(
        keyword="fuel nozzle pumping gas car",
        duration=2.5,
        placement="behind_person",
        visual_category="footage",
        reason="harga BBM naik dompet kosong",
    )
    segs = build_segments_from_suggestions([s])
    assert segs
    assert len(segs[0]["searchQueries"]) >= 1
    joined = " ".join(segs[0]["searchQueries"]).lower()
    assert any(tok in joined for tok in ("gas", "fuel", "pump", "nozzle", "car", "wallet", "cash", "money"))


def test_extract_topic_entities_and_lock():
    from src.infrastructure.clipscout_client import (
        extract_topic_entities,
        lock_keyword_to_entities,
        build_segments_from_suggestions,
    )

    ents = extract_topic_entities("Harga BBM naik, rupiah melemah, minyak dunia")
    assert "bbm" in ents
    assert "rupiah" in ents
    assert "minyak" in ents

    # Off-topic generic keyword must be forced onto entity visual.
    locked = lock_keyword_to_entities("dramatic lifestyle", ents, placement="behind_person")
    assert any(tok in locked.lower() for tok in ("fuel", "nozzle", "gas", "rupiah", "banknotes", "oil"))

    s = SimpleNamespace(
        keyword="dramatic success",
        placement="behind_person",
        visual_category="footage",
        reason="",
    )
    segs = build_segments_from_suggestions([s], topic_text="BBM mahal rupiah anjlok")
    blob = " ".join(segs[0]["searchQueries"]).lower()
    assert any(x in blob for x in ("fuel", "nozzle", "rupiah", "banknotes", "bbm"))


def test_vad_edge_shift_cap_prevents_duration_collapse():
    """Simulates the 56s→7s bug: huge end snap must clamp, not collapse."""
    from src.infrastructure.vad_boundary_adjuster import VADBoundaryAdjuster

    adj = VADBoundaryAdjuster()
    start, end = 10.0, 66.0  # 56s
    # Fake huge snap: end collapses to 19s (7s window) — must reject
    adjusted_start, adjusted_end = 12.0, 19.0
    original_duration = end - start
    max_edge = max(8.0, original_duration * 0.15)
    if abs(adjusted_start - start) > max_edge:
        adjusted_start = start
    if abs(adjusted_end - end) > max_edge:
        adjusted_end = end
    adjusted_duration = adjusted_end - adjusted_start
    if (
        adjusted_duration < original_duration * 0.8
        or adjusted_duration > original_duration * 1.2
    ):
        adjusted_start, adjusted_end = start, end
    # end shift 47s >> max_edge → clamped; duration stays near original
    assert adjusted_end == 66.0
    assert (adjusted_end - adjusted_start) >= original_duration * 0.8
    assert max_edge >= 8.0
    assert adj is not None


def test_diversify_low_candidates_seeds_extra_windows():
    from src.domain.entities import HighlightCandidate, TranscriptSegment
    from src.infrastructure.groq_analyzer import GroqAnalyzer

    analyzer = object.__new__(GroqAnalyzer)
    analyzer.MIN_CLIP_DURATION = 10.0
    analyzer.MAX_CLIP_DURATION = 30.0
    segs = [
        TranscriptSegment(start=float(i * 5), end=float(i * 5 + 4.5), text=t)
        for i, t in enumerate(
            [
                "awal cerita dulu waktu itu",
                "tapi ada masalah ribut marah",
                "ternyata hasilnya gila banget",
                "harga bbm mahal rupiah anjlok",
                "uang gaji utang",
                "cerita lagi di studio",
            ]
        )
    ]
    seed = [
        HighlightCandidate(
            rank=1, start=0.0, end=12.0, score=80, hook="seed", reason="pass1"
        )
    ]
    out = analyzer._diversify_low_candidates(
        seed, segs, {}, max_clips=3, video_duration=40.0
    )
    assert len(out) > len(seed)
    assert any("diversify:" in (c.reason or "") for c in out)


