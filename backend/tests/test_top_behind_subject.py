"""Unit tests for top-behind-subject overlay compositor (no YOLO/ffmpeg)."""
from __future__ import annotations

import os
from types import SimpleNamespace

import numpy as np
import pytest

from src.infrastructure.top_behind_subject_renderer import (
    TopBehindSubjectRenderer,
    TopOverlaySegment,
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
