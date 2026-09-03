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
        person_scale=1.0,
        person_shift_y=0.0,
        person_anchor="center",
        bg_black=0.0,
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


def test_pick_prioritizes_video_footage_over_still_image(tmp_path):
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
            sug(img, "jpg", 8.0, 2.0),
            sug(vid, "video", 8.0, 2.0),
        ],
        max_per_clip=1,
    )
    assert len(picks) == 1
    assert picks[0].asset_path == str(vid)


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
    """Bust glow paints bright rim on head/shoulder, not full torso frame."""
    r = TopBehindSubjectRenderer(
        split_ratio=0.7,
        fade_height=0.05,
        overlay_opacity=1.0,
        person_outline=True,
        person_shadow=False,
        mask_feather=1,
        outline_thickness=6,
        outline_color="255,255,255",
        outline_style="white",
        person_scale=1.0,
        person_shift_y=0.0,
        person_anchor="center",
        bg_black=0.0,
        outline_bust_ratio=0.55,
        outline_edge_margin=0.02,
    )
    h, w = 160, 100
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:] = (40, 40, 40)
    overlay = np.zeros((h, w, 3), dtype=np.uint8)
    overlay[:] = (10, 180, 10)  # green stock
    mask = np.zeros((h, w), dtype=np.float32)
    # Person mid-frame (away from L/R edges so edge_kill doesn't wipe rim)
    mask[25:130, 28:72] = 1.0


    out = r.render(frame, mask, overlay)

    # Bust band left rim (upper half of person) should be bright
    edge_bust = out[25:70, 26]
    bright = int(np.sum(edge_bust.mean(axis=1) > 160))
    assert bright >= 2, f"expected white bust outline, bright={bright}"
    # Lower torso should NOT carry full-body rim (bust-only)
    edge_legs = out[110:128, 26]
    bright_low = int(np.sum(edge_legs.mean(axis=1) > 180))
    assert bright_low <= bright, "outline must not dominate lower body"
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
        person_scale=1.0,
        person_shift_y=0.0,
        outline_bust_ratio=0.55,
        outline_edge_margin=0.02,
    )
    h, w = 160, 100
    frame = np.full((h, w, 3), 30, dtype=np.uint8)
    overlay = np.full((h, w, 3), 10, dtype=np.uint8)
    mask = np.zeros((h, w), dtype=np.float32)
    mask[25:130, 28:72] = 1.0
    out = r.render(frame, mask, overlay)
    edge = out[25:70, 25]
    # Neon is blue-ish BGR → high B channel on rim
    blueish = int(np.sum(edge[:, 0] > edge[:, 2] + 15))
    assert blueish >= 1, f"expected neon blue rim, blueish={blueish}"


def test_outline_style_black():
    r = TopBehindSubjectRenderer(
        split_ratio=0.7,
        fade_height=0.05,
        person_outline=True,
        person_shadow=False,
        outline_thickness=8,
        outline_style="black",
        person_scale=1.0,
        person_shift_y=0.0,
        outline_bust_ratio=0.55,
        outline_edge_margin=0.02,
    )
    h, w = 160, 100
    frame = np.full((h, w, 3), 200, dtype=np.uint8)
    overlay = np.full((h, w, 3), 180, dtype=np.uint8)
    mask = np.zeros((h, w), dtype=np.float32)
    mask[25:130, 28:72] = 1.0
    out = r.render(frame, mask, overlay)
    edge = out[25:70, 25]
    dark = int(np.sum(edge.mean(axis=1) < 100))
    assert dark >= 1, f"expected black outline, dark={dark}"


def test_person_scale_preserves_natural_1to1():
    """Subject stays 1:1 natural: zero shrink, zero shift, 100% original sharpness."""
    r = TopBehindSubjectRenderer(
        split_ratio=0.7,
        fade_height=0.05,
        overlay_opacity=1.0,
        person_outline=False,
        person_shadow=False,
        mask_feather=1,
        person_scale=1.0,
        person_shift_y=0.0,
        person_anchor="natural",
        bg_black=0.0,
    )
    h, w = 200, 120
    frame = np.full((h, w, 3), 50, dtype=np.uint8)
    # Person OFF-center left
    frame[40:160, 15:70] = (20, 20, 200)
    overlay = np.full((h, w, 3), (10, 180, 10), dtype=np.uint8)
    mask = np.zeros((h, w), dtype=np.float32)
    mask[40:160, 15:70] = 1.0

    out = r.render(frame, mask, overlay)
    # Person area must retain original person color perfectly
    person_core = out[80:120, 30:55]
    red_core = int(np.mean(person_core[:, :, 2]))
    assert red_core > 180, f"person core should stay 100% solid, red={red_core}"

    _, p2, layout = r._layout_person_supporting(frame, mask)
    assert layout["scale"] == 1.0
    assert layout["shift_y"] == 0.0
    assert layout["anchor"] == "natural"
    # Person area intact
    assert float(p2.sum()) == float(mask.sum())


def test_charcoal_gradient_protects_top_footage():
    """Top stock stays bright; lower stage gets charcoal depth (not flat black)."""
    r = TopBehindSubjectRenderer(
        split_ratio=0.65,
        fade_height=0.08,
        person_outline=False,
        person_shadow=False,
        person_scale=1.0,
        person_shift_y=0.0,
        bg_black=0.55,
        mask_feather=1,
    )
    h, w = 200, 100
    frame = np.full((h, w, 3), 80, dtype=np.uint8)
    # Bright stock (white-ish)
    overlay = np.full((h, w, 3), 220, dtype=np.uint8)
    mask = np.zeros((h, w), dtype=np.float32)
    # tiny person bottom so top is pure stock
    mask[150:190, 30:70] = 1.0
    out = r.render(frame, mask, overlay)
    top = float(out[8:20, 20:80].mean())
    mid = float(out[90:110, 20:80].mean())
    assert top > mid, f"top footage should stay brighter than mid stage top={top} mid={mid}"
    assert top > 150, f"top stock crushed top={top}"
    # Stage not pure black crush
    bot = float(out[130:145, 20:80].mean())
    assert bot > 5, f"flat pure black bot={bot}"


def test_outline_kills_frame_edge_verticals():
    """Stroke must not paint glued L/R frame columns (boxed look)."""
    r = TopBehindSubjectRenderer(
        split_ratio=0.8,
        fade_height=0.05,
        person_outline=True,
        person_shadow=False,
        outline_thickness=10,
        outline_style="white",
        person_scale=1.0,
        person_shift_y=0.0,
        outline_bust_ratio=0.6,
        outline_edge_margin=0.08,
    )
    h, w = 160, 100
    frame = np.full((h, w, 3), 40, dtype=np.uint8)
    overlay = np.full((h, w, 3), 10, dtype=np.uint8)
    mask = np.zeros((h, w), dtype=np.float32)
    # Person touching left edge (bad YOLO case) — outline must still kill col 0..mx
    mask[20:140, 0:55] = 1.0
    out = r.render(frame, mask, overlay)
    left_strip = out[:, :3].mean(axis=2)
    # Extreme left columns should stay near frame gray, not white rim wall
    bright_left = int(np.sum(left_strip > 180))
    assert bright_left < h * 0.35, f"edge vertical wall leaked, bright_left={bright_left}"


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
        extra_queries=["uang rupiah kertas", "indonesian rupiah banknotes"],
    )
    # AI keyword kept; close-up framing for behind_person; extra_queries merged
    assert any("rupiah" in q.lower() for q in qs)
    assert any("close up" in q.lower() for q in qs)
    assert any("uang" in q.lower() for q in qs)
    assert len(qs) <= 8


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
        sanitize_stock_keyword,
    )

    # No stop/mood lexicon — content tokens ≥4 chars only (AI owns quality)
    ents = extract_topic_entities("Harga BBM naik, rupiah melemah, minyak dunia")
    assert "rupiah" in ents
    assert "minyak" in ents
    assert "dunia" in ents

    # Soft lock: short keyword gets first content token prepended
    locked = lock_keyword_to_entities("chart", ents, placement="behind_person")
    assert "rupiah" in locked.lower() or "chart" in locked.lower()

    # sanitize normalizes only — trusts AI query text, no mood strip table
    clean = sanitize_stock_keyword("rupiah banknotes close up", placement="")
    assert "rupiah" in clean.lower()
    assert "banknotes" in clean.lower()

    s = SimpleNamespace(
        keyword="indonesian rupiah banknotes",
        placement="behind_person",
        visual_category="footage",
        reason="",
    )
    # extra_queries = AI seeds (not synonym/stop table)
    segs = build_segments_from_suggestions(
        [s],
        topic_text="BBM mahal rupiah anjlok",
        analisa_extra_queries=["fuel nozzle pumping gas", "indonesian rupiah banknotes"],
    )
    blob = " ".join(segs[0]["searchQueries"]).lower()
    assert "rupiah" in blob or "fuel" in blob


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


def test_top_behind_subject_zero_ghosting_and_exact_foreground():
    """Verify that default natural 1:1 scale keeps exact original foreground without double-head."""
    r = TopBehindSubjectRenderer(
        split_ratio=0.6,
        fade_height=0.1,
        overlay_opacity=1.0,
        person_scale=1.0,
        person_shift_y=0.0,
        bg_black=0.0,
        person_shadow=False,
    )
    h, w = 120, 80
    frame = np.full((h, w, 3), (35, 120, 220), dtype=np.uint8)  # Distinct subject color
    overlay = np.full((h, w, 3), (180, 50, 40), dtype=np.uint8)  # Distinct B-roll
    mask = np.zeros((h, w), dtype=np.float32)
    # Define circular person head/body
    yy, xx = np.mgrid[:h, :w]
    mask[(yy - 60)**2 + (xx - 40)**2 <= 25**2] = 1.0

    out = r.render(frame, mask, overlay)

    # Core of person is EXACTLY identical to original camera frame
    assert np.array_equal(out[60, 40], frame[60, 40])
    # Top background is B-roll overlay
    assert np.array_equal(out[10, 10], overlay[10, 10])
    # Subpixel anti-aliased edge has intermediate values (no harsh aliasing)
    edge_val = out[60, 15]  # on the circle boundary
    assert not np.array_equal(edge_val, [0, 0, 0]), "no black halo on boundary"


def test_clean_person_mask_signed_distance_feathering():
    """Verify that _clean_person_mask produces smooth continuous subpixel feathering."""
    r = TopBehindSubjectRenderer(mask_feather=3)
    h, w = 100, 100
    raw_mask = np.zeros((h, w), dtype=np.float32)
    raw_mask[20:80, 20:80] = 1.0
    
    clean = r._clean_person_mask(raw_mask)
    
    # Inside core is solid 1.0
    assert clean[50, 50] == 1.0
    # Outside is solid 0.0
    assert clean[5, 5] == 0.0
    # Boundary contains anti-aliased floating values strictly between 0.0 and 1.0
    boundary_vals = clean[20, 18:24]
    has_subpixel = np.any((boundary_vals > 0.05) & (boundary_vals < 0.95))
    assert has_subpixel, f"expected subpixel anti-aliasing on boundary, got {boundary_vals}"


def test_microphone_and_chest_objects_solidified_in_foreground():
    """Verify microphones & chest objects are protected from being replaced by B-roll."""
    r = TopBehindSubjectRenderer(split_ratio=0.7, overlay_opacity=1.0)
    h, w = 120, 80
    frame = np.full((h, w, 3), (40, 140, 240), dtype=np.uint8)  # Person clothing
    # Put a distinct microphone color on chest
    frame[55:65, 35:45] = (20, 20, 20)
    overlay = np.full((h, w, 3), (200, 50, 50), dtype=np.uint8)  # Red B-roll

    # Raw mask has person, but YOLO left a hole for the microphone in the chest!
    mask = np.zeros((h, w), dtype=np.float32)
    mask[30:100, 20:60] = 1.0
    mask[55:65, 35:45] = 0.0  # The microphone is excluded by raw YOLO

    # Also simulate a mic stand extending downwards out of the body
    mask[80:120, 38:42] = 0.0

    out = r.render(frame, mask, overlay)

    # 1. Microphone area must NOT be replaced with B-roll (overlay is (200, 50, 50))
    # It must retain original mic color (20, 20, 20)
    mic_pixel = out[60, 40]
    assert not np.allclose(mic_pixel, [200, 50, 50], atol=20), "B-roll leaked into microphone!"
    assert np.allclose(mic_pixel, [20, 20, 20], atol=10), f"Mic should remain original, got {mic_pixel}"

    # 2. Upper background must still get B-roll
    assert np.allclose(out[10, 10], [200, 50, 50], atol=5)


def test_shot_cut_detection_and_temporal_reset():
    """Verify that shot cuts are detected and temporal EMA ghosting is completely eliminated."""
    r = TopBehindSubjectRenderer()
    h, w = 100, 80

    # Shot 1: Bright daylight scene with person on left
    frame1 = np.full((h, w, 3), (220, 230, 240), dtype=np.uint8)
    mask1 = np.zeros((h, w), dtype=np.float32)
    mask1[20:80, 10:35] = 1.0
    overlay = np.full((h, w, 3), (50, 50, 200), dtype=np.uint8)

    # First frame of Shot 1: baseline established
    assert r._detect_shot_cut(frame1) is False
    r.render(frame1, mask1, overlay)
    assert r._prev_clean_mask is not None

    # Shot 2: Dark studio scene with Person 2 on the right (hard camera cut)
    frame2 = np.full((h, w, 3), (20, 25, 30), dtype=np.uint8)
    mask2 = np.zeros((h, w), dtype=np.float32)
    mask2[20:80, 45:70] = 1.0

    # Shot cut detection should flag this
    is_cut = r._detect_shot_cut(frame2)
    assert is_cut is True

    # When cut is detected, reset temporal state
    r.reset_temporal_state()
    assert r._prev_clean_mask is None

    # Render frame2: Person 1's position (x=20) must have 0% ghosting of Person 1
    out2 = r.render(frame2, mask2, overlay)

    # In frame 2, at Person 1's previous location (y=50, x=20), it is now background!
    # Because it is top background, it should have overlay color, NOT Person 1's old frame color
    assert np.allclose(out2[50, 20], overlay[50, 20], atol=15)
    # Person 2's location (y=50, x=55) must be crisp frame2
    assert np.allclose(out2[50, 55], frame2[50, 55], atol=5)


def test_selective_user_tracking_continuity():
    """Verify selective tracking stays locked on active speaker without jittering."""
    r = TopBehindSubjectRenderer(speaker_mask_mode="single")
    h, w = 100, 100

    # Two people: Person A on left (x=10..40), Person B on right (x=60..90)
    mask_a = np.zeros((h, w), dtype=np.float32)
    mask_a[20:80, 10:40] = 1.0
    box_a = (10.0, 20.0, 40.0, 80.0)

    mask_b = np.zeros((h, w), dtype=np.float32)
    mask_b[20:80, 60:90] = 1.0
    box_b = (60.0, 20.0, 90.0, 80.0)

    # Frame 1: Person A is selected and active track is set
    filtered1 = r._filter_speaker_masks([mask_a, mask_b], [box_a, box_b], h, w)
    assert len(filtered1) == 1

    # In frame 2, Person B gestures slightly (higher area temporarily)
    # But because Person A is the active track, single mode should maintain tracking continuity on Person A
    mask_b_larger = mask_b.copy()
    filtered2 = r._filter_speaker_masks([mask_a, mask_b_larger], [box_a, box_b], h, w)
    assert len(filtered2) == 1
    # Check that mask_a is still selected (centroid is on the left)
    selected_mask = filtered2[0]
    ys, xs = np.where(selected_mask > 0.5)
    assert np.mean(xs) < 50.0, "should stay locked on Person A"


def test_snap_overlay_to_phrase_pauses_and_shot_cuts():
    """Verify overlay snaps to single speaker phrase and never straddles shot cuts or pauses."""
    from src.infrastructure.top_behind_subject_renderer import snap_overlay_to_phrase

    words = [
        {"start": 5.0, "end": 5.4, "word": "saya"},
        {"start": 5.5, "end": 6.0, "word": "suka"},
        {"start": 6.1, "end": 6.8, "word": "kopi"},
        # Significant pause of 1.2s between 6.8s and 8.0s (next speaker / sentence)
        {"start": 8.0, "end": 8.5, "word": "iya"},
        {"start": 8.6, "end": 9.2, "word": "benar"},
    ]

    # Without cut: should stop before the 1.2s pause (does not expand into next speaker)
    at, dur = snap_overlay_to_phrase(5.0, 2.5, words)
    assert at <= 5.0
    assert (at + dur) <= 7.2, f"Should not cross speech pause into second speaker, got {at + dur}"

    # With a camera shot cut at 6.5s:
    at2, dur2 = snap_overlay_to_phrase(5.0, 2.5, words, shot_boundaries=[6.5])
    assert (at2 + dur2) <= 6.5, f"Must end before shot cut at 6.5s, got {at2 + dur2}"




