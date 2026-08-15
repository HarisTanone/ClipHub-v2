"""Footage Allocation Engine — no-overlap interval solver for raw-footage assembly.

Problem
-------
User uploads N raw footage files and asks for K final short clips. An AI segment
analyzer (``analyze_visual_entities_for_clips`` / per-segment scoring) proposes,
for every desired clip, an ordered list of *candidate* source segments (each a
``(asset_id, start, end)`` time range plus a relevance score). Multiple clips may
want the same underlying footage range.

Hard requirement: **the same source footage range must never appear in more than
one final clip.** Ownership is tracked per *interval*, not per file — so if
clip #1 consumes ``footage_001[10s..18s]``, the ranges ``[0..10]`` and ``[18..end]``
of that same file remain available for other clips.

Design notes
------------
- Pure Python, deterministic, dependency-free. No domain lexicon / synonym /
  stopword maps — allocation is a numeric interval + score optimization only.
  All semantic meaning (what a segment *is*, how relevant it is to a clip) comes
  from the AI scores supplied by the caller.
- Greedy allocation ordered by (clip priority, candidate score) with an interval
  reservation ledger, followed by a conflict-resolution pass that lets a clip
  fall back to its next-best non-conflicting candidate.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Two ranges on the same asset closer than this (seconds) are treated as
# touching — prevents frame-accurate slivers that FFmpeg cannot cut cleanly.
_EPS = 0.04


@dataclass
class SegmentCandidate:
    """One AI-proposed source segment that could feed a clip slot.

    ``score`` is the AI relevance/quality score for using this segment in this
    slot (higher = better). ``role`` is a free-form AI label (e.g. "problem",
    "process", "result") used only for ordering within a clip, never matched
    against any hardcoded vocabulary.
    """
    asset_id: str
    start: float
    end: float
    score: float
    role: str = ""
    description: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def overlaps(self, other: "SegmentCandidate") -> bool:
        if self.asset_id != other.asset_id:
            return False
        return (self.start < other.end - _EPS) and (other.start < self.end - _EPS)


@dataclass
class ClipRequest:
    """A desired final clip and its ranked candidate segments.

    ``candidates`` may contain more segments than needed; the engine picks a
    non-overlapping subset. ``target_duration`` bounds how much footage the clip
    should consume (0 = unbounded, take all fitting candidates). ``min_segments``
    lets the caller demand a minimum number of distinct segments per clip.
    """
    clip_id: str
    candidates: list[SegmentCandidate]
    target_duration: float = 0.0
    priority: int = 0  # lower value = allocated first
    min_segments: int = 1
    title: str = ""


@dataclass
class ClipAllocation:
    clip_id: str
    title: str
    segments: list[SegmentCandidate] = field(default_factory=list)
    unmet: bool = False  # True if min_segments could not be satisfied

    @property
    def total_duration(self) -> float:
        return sum(s.duration for s in self.segments)


class _IntervalLedger:
    """Tracks reserved (used) time ranges per asset. O(n) per check."""

    def __init__(self) -> None:
        self._used: dict[str, list[tuple[float, float]]] = {}

    def is_free(self, cand: SegmentCandidate) -> bool:
        for (s, e) in self._used.get(cand.asset_id, ()):  # noqa: E741
            if (cand.start < e - _EPS) and (s < cand.end - _EPS):
                return False
        return True

    def reserve(self, cand: SegmentCandidate) -> None:
        self._used.setdefault(cand.asset_id, []).append((cand.start, cand.end))

    def free_ranges(self, asset_id: str, asset_duration: float) -> list[tuple[float, float]]:
        """Return the still-available ranges of an asset after reservations."""
        used = sorted(self._used.get(asset_id, []))
        free: list[tuple[float, float]] = []
        cursor = 0.0
        for (s, e) in used:
            if s - cursor > _EPS:
                free.append((cursor, s))
            cursor = max(cursor, e)
        if asset_duration - cursor > _EPS:
            free.append((cursor, asset_duration))
        return free


def allocate_clips(requests: list[ClipRequest]) -> list[ClipAllocation]:
    """Allocate non-overlapping source segments across all requested clips.

    Guarantees: no source (asset_id, time-range) is assigned to two clips.
    Strategy: process clips by ascending ``priority`` (ties broken by input
    order). Within a clip, greedily take highest-scoring candidates whose range
    is still free, skipping any that overlap already-picked segments (in this or
    another clip). Stops when target_duration is met (if > 0).

    Deterministic for a given input.
    """
    ledger = _IntervalLedger()
    order = sorted(range(len(requests)), key=lambda i: (requests[i].priority, i))
    results: dict[str, ClipAllocation] = {}

    for idx in order:
        req = requests[idx]
        alloc = ClipAllocation(clip_id=req.clip_id, title=req.title)
        # Highest score first; stable on ties for determinism.
        ranked = sorted(
            enumerate(req.candidates),
            key=lambda p: (-p[1].score, p[0]),
        )
        for _, cand in ranked:
            if cand.duration <= _EPS:
                continue
            if not ledger.is_free(cand):
                continue
            # Also guard against overlapping a segment already chosen for THIS clip.
            if any(cand.overlaps(chosen) for chosen in alloc.segments):
                continue
            alloc.segments.append(cand)
            ledger.reserve(cand)
            if req.target_duration > 0 and alloc.total_duration >= req.target_duration:
                break
        alloc.unmet = len(alloc.segments) < max(1, req.min_segments)
        # Preserve AI-intended narrative order (by candidate index / role), not
        # score order, in the final segment list.
        cand_index = {id(c): i for i, c in enumerate(req.candidates)}
        alloc.segments.sort(key=lambda c: cand_index.get(id(c), 0))
        results[req.clip_id] = alloc

    # Return in original request order.
    return [results[r.clip_id] for r in requests]


def verify_no_overlap(allocations: list[ClipAllocation]) -> list[str]:
    """Return a list of human-readable conflict messages. Empty = clean.

    Cross-checks every pair of allocated segments across all clips to prove the
    no-overlap invariant holds. Used by tests and as a runtime assertion before
    render.
    """
    conflicts: list[str] = []
    flat: list[tuple[str, SegmentCandidate]] = []
    for alloc in allocations:
        for seg in alloc.segments:
            flat.append((alloc.clip_id, seg))
    for i in range(len(flat)):
        cid_a, a = flat[i]
        for j in range(i + 1, len(flat)):
            cid_b, b = flat[j]
            if cid_a == cid_b:
                continue
            if a.overlaps(b):
                conflicts.append(
                    f"{cid_a} {a.asset_id}[{a.start:.2f}-{a.end:.2f}] overlaps "
                    f"{cid_b} {b.asset_id}[{b.start:.2f}-{b.end:.2f}]"
                )
    return conflicts
