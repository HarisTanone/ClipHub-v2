"""B-Roll API routes — Template management and per-clip b-roll CRUD.

Endpoints:
- GET    /api/broll-templates              — List all b-roll templates
- GET    /api/broll-templates/{id}         — Get single template
- PATCH  /api/jobs/{job_id}/clips/{rank}/broll    — Add/override broll for clip
- DELETE /api/jobs/{job_id}/clips/{rank}/broll/{broll_id} — Remove broll from clip
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from src.infrastructure.db_connection import get_dict_connection
from src.presentation.auth_deps import CurrentUser, get_current_user

router = APIRouter(prefix="/api", tags=["brolls"])
logger = logging.getLogger(__name__)


# ─── Response Models ──────────────────────────────────────────────────────────

class BRollTemplateResponse(BaseModel):
    id: str
    name: str
    component: str
    category: str
    description: Optional[str] = None
    default_duration_ms: int


class AddBRollRequest(BaseModel):
    template_id: str
    at_time: float = Field(..., ge=0.0)
    keyword_text: str = Field(..., min_length=1, max_length=200)
    duration_ms: int = Field(default=2000, ge=500, le=5000)


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("/broll-templates")
async def list_broll_templates():
    """List all available b-roll motion typography templates."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, component, category, description, default_duration_ms FROM broll_templates WHERE is_active = 1")
        rows = cur.fetchall()
        templates = [dict(r) for r in rows]
        return {"success": True, "data": templates, "total": len(templates)}
    finally:
        conn.close()


@router.get("/broll-templates/{template_id}")
async def get_broll_template(template_id: str):
    """Get single b-roll template by ID."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, component, category, description, default_duration_ms, config FROM broll_templates WHERE id = ?", (template_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
        return {"success": True, "data": dict(row)}
    finally:
        conn.close()


@router.patch("/jobs/{job_id}/clips/{rank}/broll")
async def add_clip_broll(job_id: str, rank: int, body: AddBRollRequest, user: CurrentUser = Depends(get_current_user)):
    """Add or override b-roll for a specific clip."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()

        # Validate template exists
        cur.execute("SELECT id FROM broll_templates WHERE id = ?", (body.template_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail=f"Template '{body.template_id}' not found")

        # Check max brolls per clip
        cur.execute(
            "SELECT COUNT(*) as cnt FROM job_clip_brolls WHERE job_id = ? AND clip_rank = ?",
            (job_id, rank),
        )
        count = cur.fetchone()["cnt"]
        if count >= 3:
            raise HTTPException(status_code=400, detail="Maximum 3 b-rolls per clip")

        cur.execute(
            """INSERT INTO job_clip_brolls (job_id, clip_rank, template_id, at_time, keyword_text, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (job_id, rank, body.template_id, body.at_time, body.keyword_text, body.duration_ms),
        )
        broll_id = cur.lastrowid
        conn.commit()

        return {
            "success": True,
            "data": {"id": broll_id, "job_id": job_id, "clip_rank": rank, **body.model_dump()},
            "message": f"B-roll added to clip #{rank}",
        }
    finally:
        conn.close()


@router.delete("/jobs/{job_id}/clips/{rank}/broll/{broll_id}")
async def delete_clip_broll(job_id: str, rank: int, broll_id: int, user: CurrentUser = Depends(get_current_user)):
    """Remove a specific b-roll from a clip."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM job_clip_brolls WHERE id = ? AND job_id = ? AND clip_rank = ?",
            (broll_id, job_id, rank),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="B-roll not found")
        conn.commit()
        return {"success": True, "message": f"B-roll #{broll_id} removed from clip #{rank}"}
    finally:
        conn.close()


@router.get("/jobs/{job_id}/clips/{rank}/broll")
async def list_clip_brolls(job_id: str, rank: int):
    """List all b-rolls for a specific clip."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT b.id, b.template_id, b.at_time, b.keyword_text, b.duration_ms, b.rendered_path,
            t.name as template_name, t.component
            FROM job_clip_brolls b
            JOIN broll_templates t ON t.id = b.template_id
            WHERE b.job_id = ? AND b.clip_rank = ?
            ORDER BY b.at_time""",
            (job_id, rank),
        )
        rows = cur.fetchall()
        return {"success": True, "data": [dict(r) for r in rows], "total": len(rows)}
    finally:
        conn.close()
