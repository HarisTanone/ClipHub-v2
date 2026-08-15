"""Repository for clip planner + raw-footage assembly (v7 tables).

Plain sqlite3 (matches the v7 migration style) with a thin async-friendly wrapper
via ``asyncio.to_thread`` so it can be awaited from FastAPI handlers without
blocking the event loop. Kept separate from the SQLAlchemy ORM used for jobs to
avoid coupling the two schemas.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from typing import Any, Optional

from src.config import settings


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _dumps(obj: Any) -> Optional[str]:
    return json.dumps(obj, ensure_ascii=False) if obj is not None else None


def _loads(text: Optional[str]) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


# ─── Feature 1: YouTube clip plan ─────────────────────────────────────────────

def _save_plan(job_id: str, candidates: list[dict], transcript: Any,
               video_duration: float) -> None:
    conn = _conn()
    try:
        conn.execute(
            """
            INSERT INTO clip_plans
                (job_id, status, video_duration, transcript_json, candidates_json,
                 adjusted_json, updated_at)
            VALUES (?, 'plan_ready', ?, ?, ?, NULL, datetime('now'))
            ON CONFLICT(job_id) DO UPDATE SET
                status='plan_ready',
                video_duration=excluded.video_duration,
                transcript_json=excluded.transcript_json,
                candidates_json=excluded.candidates_json,
                updated_at=datetime('now')
            """,
            (job_id, video_duration, _dumps(transcript), _dumps(candidates)),
        )
        conn.commit()
    finally:
        conn.close()


def _get_plan(job_id: str) -> Optional[dict]:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM clip_plans WHERE job_id=?", (job_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "job_id": row["job_id"],
        "status": row["status"],
        "video_duration": row["video_duration"],
        "transcript": _loads(row["transcript_json"]),
        "candidates": _loads(row["candidates_json"]) or [],
        "adjusted": _loads(row["adjusted_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _update_adjusted(job_id: str, adjusted: list[dict]) -> bool:
    conn = _conn()
    try:
        cur = conn.execute(
            "UPDATE clip_plans SET adjusted_json=?, status='adjusted', "
            "updated_at=datetime('now') WHERE job_id=?",
            (_dumps(adjusted), job_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _set_plan_status(job_id: str, status: str) -> None:
    conn = _conn()
    try:
        conn.execute(
            "UPDATE clip_plans SET status=?, updated_at=datetime('now') WHERE job_id=?",
            (status, job_id),
        )
        conn.commit()
    finally:
        conn.close()


# ─── Feature 2: source assets + segments + allocations ────────────────────────

def _add_asset(project_id: str, file_path: str, filename: str, duration: float,
               fps: float, width: int, height: int, metadata: Any = None) -> str:
    asset_id = uuid.uuid4().hex
    conn = _conn()
    try:
        conn.execute(
            """INSERT INTO source_assets
               (asset_id, project_id, file_path, filename, duration, fps, width,
                height, status, metadata)
               VALUES (?,?,?,?,?,?,?,?, 'analyzed', ?)""",
            (asset_id, project_id, file_path, filename, duration, fps, width,
             height, _dumps(metadata)),
        )
        conn.commit()
    finally:
        conn.close()
    return asset_id


def _add_segments(project_id: str, segments: list[dict]) -> list[str]:
    ids: list[str] = []
    conn = _conn()
    try:
        for s in segments:
            sid = uuid.uuid4().hex
            ids.append(sid)
            conn.execute(
                """INSERT INTO asset_segments
                   (segment_id, asset_id, project_id, start_time, end_time,
                    description, transcript, scene_label, quality_score, metadata)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (sid, s["asset_id"], project_id, float(s["start_time"]),
                 float(s["end_time"]), s.get("description"), s.get("transcript"),
                 s.get("scene_label"), float(s.get("quality_score", 0) or 0),
                 _dumps(s.get("metadata"))),
            )
        conn.commit()
    finally:
        conn.close()
    return ids


def _list_segments(project_id: str) -> list[dict]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM asset_segments WHERE project_id=? ORDER BY asset_id, start_time",
            (project_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _save_allocations(project_id: str, clips: list[dict]) -> None:
    """Replace all clip plans + allocations for a project (transactional)."""
    conn = _conn()
    try:
        conn.execute("DELETE FROM clip_allocations WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM footage_clip_plans WHERE project_id=?", (project_id,))
        for seq, clip in enumerate(clips):
            conn.execute(
                """INSERT INTO footage_clip_plans
                   (clip_id, project_id, title, target_duration, sequence, status)
                   VALUES (?,?,?,?,?, 'planned')""",
                (clip["clip_id"], project_id, clip.get("title", ""),
                 float(clip.get("target_duration", 0) or 0), seq),
            )
            for i, seg in enumerate(clip.get("segments", [])):
                conn.execute(
                    """INSERT INTO clip_allocations
                       (clip_id, project_id, asset_id, source_start, source_end,
                        sequence, role, score)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (clip["clip_id"], project_id, seg["asset_id"],
                     float(seg["source_start"]), float(seg["source_end"]), i,
                     seg.get("role", ""), float(seg.get("score", 0) or 0)),
                )
        conn.commit()
    finally:
        conn.close()


def _get_project_plan(project_id: str) -> list[dict]:
    conn = _conn()
    try:
        clips = conn.execute(
            "SELECT * FROM footage_clip_plans WHERE project_id=? ORDER BY sequence",
            (project_id,),
        ).fetchall()
        out = []
        for c in clips:
            segs = conn.execute(
                "SELECT * FROM clip_allocations WHERE clip_id=? ORDER BY sequence",
                (c["clip_id"],),
            ).fetchall()
            out.append({
                "clip_id": c["clip_id"],
                "title": c["title"],
                "target_duration": c["target_duration"],
                "sequence": c["sequence"],
                "status": c["status"],
                "segments": [dict(s) for s in segs],
            })
        return out
    finally:
        conn.close()


# ─── Async wrappers ───────────────────────────────────────────────────────────

async def save_plan(job_id, candidates, transcript, video_duration):
    return await asyncio.to_thread(_save_plan, job_id, candidates, transcript, video_duration)


async def get_plan(job_id):
    return await asyncio.to_thread(_get_plan, job_id)


async def update_adjusted(job_id, adjusted):
    return await asyncio.to_thread(_update_adjusted, job_id, adjusted)


async def set_plan_status(job_id, status):
    return await asyncio.to_thread(_set_plan_status, job_id, status)


async def add_asset(project_id, file_path, filename, duration, fps, width, height, metadata=None):
    return await asyncio.to_thread(
        _add_asset, project_id, file_path, filename, duration, fps, width, height, metadata
    )


async def add_segments(project_id, segments):
    return await asyncio.to_thread(_add_segments, project_id, segments)


async def list_segments(project_id):
    return await asyncio.to_thread(_list_segments, project_id)


async def save_allocations(project_id, clips):
    return await asyncio.to_thread(_save_allocations, project_id, clips)


async def get_project_plan(project_id):
    return await asyncio.to_thread(_get_project_plan, project_id)
