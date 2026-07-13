"""Helpers for exposing clip outputs as soon as each render is complete."""

from __future__ import annotations

import os
import re


_READY_DIR = ".ready"
_READY_RE = re.compile(r"^clip_(\d+)\.ready$")
_ROOT_FINAL_RE = re.compile(r"^clip_(\d+)_final\.mp4$")
_STRUCTURED_FINAL_RE = re.compile(r"^clip_(\d+)(?:_final)?\.mp4$")


def initialize_clip_readiness(output_dir: str) -> str:
    """Enable explicit ready markers before renderers start writing outputs."""
    ready_dir = os.path.join(output_dir, _READY_DIR)
    os.makedirs(ready_dir, exist_ok=True)
    return ready_dir


def mark_clip_ready(output_dir: str, rank: int) -> None:
    """Atomically mark a completed final render as safe for the UI to open."""
    ready_dir = initialize_clip_readiness(output_dir)
    marker_path = os.path.join(ready_dir, f"clip_{rank:02d}.ready")
    temporary_path = f"{marker_path}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as marker:
        marker.write("ready\n")
    os.replace(temporary_path, marker_path)


def final_clip_candidates(output_dir: str, rank: int) -> list[str]:
    """Return supported final-output locations, newest layout first."""
    return [
        os.path.join(output_dir, "final", f"clip_{rank:02d}_final.mp4"),
        os.path.join(output_dir, "final", f"clip_{rank}_final.mp4"),
        os.path.join(output_dir, "final", f"clip_{rank:02d}.mp4"),
        os.path.join(output_dir, "final", f"clip_{rank}.mp4"),
        os.path.join(output_dir, f"clip_{rank:02d}_final.mp4"),
        os.path.join(output_dir, f"clip_{rank}_final.mp4"),
    ]


def find_final_clip(output_dir: str, rank: int) -> str | None:
    """Find a non-empty final file for a clip rank."""
    for path in final_clip_candidates(output_dir, rank):
        try:
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                return path
        except OSError:
            continue
    return None


def discover_ready_clip_ranks(output_dir: str) -> list[int]:
    """Return completed ranks without exposing files still being written.

    New pipelines create ``.ready`` before rendering and add one marker only
    after each renderer reports success. Jobs produced before this mechanism
    retain compatibility through a filename scan.
    """
    if not os.path.isdir(output_dir):
        return []

    ready_dir = os.path.join(output_dir, _READY_DIR)
    if os.path.isdir(ready_dir):
        ready: set[int] = set()
        for filename in os.listdir(ready_dir):
            match = _READY_RE.match(filename)
            if not match:
                continue
            rank = int(match.group(1))
            if find_final_clip(output_dir, rank):
                ready.add(rank)
        return sorted(ready)

    # Compatibility for jobs created before explicit ready markers existed.
    ready: set[int] = set()
    for filename in os.listdir(output_dir):
        match = _ROOT_FINAL_RE.match(filename)
        if match:
            rank = int(match.group(1))
            if find_final_clip(output_dir, rank):
                ready.add(rank)

    final_dir = os.path.join(output_dir, "final")
    if os.path.isdir(final_dir):
        for filename in os.listdir(final_dir):
            match = _STRUCTURED_FINAL_RE.match(filename)
            if match:
                rank = int(match.group(1))
                if find_final_clip(output_dir, rank):
                    ready.add(rank)

    return sorted(ready)
