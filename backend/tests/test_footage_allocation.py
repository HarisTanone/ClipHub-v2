"""Tests for the footage allocation engine (no-overlap interval solver).

Key invariant under test: the same source footage range never appears in more
than one final clip, while leftover ranges of a partially-used file stay
available to other clips.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.footage_allocation import (
    ClipRequest,
    SegmentCandidate,
    allocate_clips,
    verify_no_overlap,
)


def _seg(asset, start, end, score, role=""):
    return SegmentCandidate(asset_id=asset, start=start, end=end, score=score, role=role)


def test_no_duplicate_footage_across_clips():
    # Both clips want footage_B[0..6]; only one may get it.
    reqs = [
        ClipRequest(
            clip_id="clip1",
            candidates=[_seg("A", 0, 5, 0.9), _seg("B", 0, 6, 0.8)],
            priority=0,
        ),
        ClipRequest(
            clip_id="clip2",
            candidates=[_seg("B", 0, 6, 0.95), _seg("C", 0, 4, 0.7)],
            priority=1,
        ),
    ]
    allocs = allocate_clips(reqs)
    assert verify_no_overlap(allocs) == []
    used_b = [
        (a.clip_id, s.start, s.end)
        for a in allocs for s in a.segments if s.asset_id == "B"
    ]
    assert len(used_b) == 1  # B[0..6] assigned to exactly one clip


def test_leftover_range_reusable():
    # footage A is long; clip1 takes [10..18], clip2 can still use [0..8].
    reqs = [
        ClipRequest(
            clip_id="clip1",
            candidates=[_seg("A", 10, 18, 0.9)],
            priority=0,
        ),
        ClipRequest(
            clip_id="clip2",
            candidates=[_seg("A", 0, 8, 0.9)],
            priority=1,
        ),
    ]
    allocs = allocate_clips(reqs)
    assert verify_no_overlap(allocs) == []
    assert len(allocs[0].segments) == 1
    assert len(allocs[1].segments) == 1  # leftover range reused
    assert allocs[1].segments[0].start == 0


def test_overlapping_leftover_rejected():
    # clip1 takes A[10..18]; clip2's only candidate A[15..22] overlaps → unmet.
    reqs = [
        ClipRequest(clip_id="clip1", candidates=[_seg("A", 10, 18, 0.9)], priority=0),
        ClipRequest(clip_id="clip2", candidates=[_seg("A", 15, 22, 0.9)], priority=1),
    ]
    allocs = allocate_clips(reqs)
    assert verify_no_overlap(allocs) == []
    assert allocs[1].unmet is True
    assert len(allocs[1].segments) == 0


def test_target_duration_stops_allocation():
    reqs = [
        ClipRequest(
            clip_id="clip1",
            candidates=[
                _seg("A", 0, 5, 0.9),
                _seg("B", 0, 5, 0.8),
                _seg("C", 0, 5, 0.7),
            ],
            target_duration=8,
            priority=0,
        ),
    ]
    allocs = allocate_clips(reqs)
    # Takes 5s + 5s = 10s >= 8s target, then stops → 2 segments.
    assert len(allocs[0].segments) == 2
    assert allocs[0].total_duration >= 8


def test_narrative_order_preserved():
    # Candidates listed problem→process→result but scored out of order.
    reqs = [
        ClipRequest(
            clip_id="clip1",
            candidates=[
                _seg("A", 0, 3, 0.5, role="problem"),
                _seg("B", 0, 3, 0.9, role="process"),
                _seg("C", 0, 3, 0.7, role="result"),
            ],
            priority=0,
        ),
    ]
    allocs = allocate_clips(reqs)
    roles = [s.role for s in allocs[0].segments]
    assert roles == ["problem", "process", "result"]  # input order, not score


def test_min_segments_unmet_flag():
    reqs = [
        ClipRequest(
            clip_id="clip1",
            candidates=[_seg("A", 0, 3, 0.9)],
            min_segments=3,
            priority=0,
        ),
    ]
    allocs = allocate_clips(reqs)
    assert allocs[0].unmet is True


def test_priority_order_wins_contested_footage():
    # Lower priority value allocated first → gets the contested high-score seg.
    contested = ("B", 0, 6)
    reqs = [
        ClipRequest(
            clip_id="low_prio",
            candidates=[_seg(*contested, 0.9)],
            priority=5,
        ),
        ClipRequest(
            clip_id="high_prio",
            candidates=[_seg(*contested, 0.9)],
            priority=1,
        ),
    ]
    allocs = allocate_clips(reqs)
    assert verify_no_overlap(allocs) == []
    by_id = {a.clip_id: a for a in allocs}
    assert len(by_id["high_prio"].segments) == 1
    assert by_id["low_prio"].unmet is True


def test_deterministic():
    reqs = [
        ClipRequest(
            clip_id="c1",
            candidates=[_seg("A", 0, 5, 0.9), _seg("B", 0, 5, 0.9)],
            priority=0,
        ),
        ClipRequest(
            clip_id="c2",
            candidates=[_seg("A", 0, 5, 0.9), _seg("B", 0, 5, 0.9)],
            priority=1,
        ),
    ]
    r1 = allocate_clips([ClipRequest(**vars(r)) for r in reqs])
    r2 = allocate_clips([ClipRequest(**vars(r)) for r in reqs])
    sig = lambda res: [(a.clip_id, [(s.asset_id, s.start) for s in a.segments]) for a in res]
    assert sig(r1) == sig(r2)
