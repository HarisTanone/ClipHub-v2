"""User Style Presets API — Save/List/Delete custom hook+subtitle presets per user."""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.infrastructure.db_connection import get_dict_connection
from src.presentation.auth_deps import CurrentUser, get_current_user

router = APIRouter(prefix="/presets", tags=["presets"])
logger = logging.getLogger(__name__)


# ─── Ensure table ─────────────────────────────────────────────────────────────

def _ensure_presets_table():
    conn = get_dict_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                hook_style JSON NOT NULL DEFAULT '{}',
                subtitle_style JSON NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
    finally:
        conn.close()

_ensure_presets_table()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class CreatePresetRequest(BaseModel):
    name: str
    hook_style: dict = {}
    subtitle_style: dict = {}

class PresetResponse(BaseModel):
    id: int
    name: str
    hook_style: dict
    subtitle_style: dict
    created_at: Optional[str] = None


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("")
async def list_presets(user: CurrentUser = Depends(get_current_user)):
    """List presets. Superadmin sees ALL presets (with owner info), others see only their own."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        if user.is_superadmin:
            cur.execute(
                "SELECT p.*, u.email as owner_email, u.full_name as owner_name "
                "FROM user_presets p JOIN users u ON p.user_id = u.id "
                "ORDER BY p.created_at DESC"
            )
        else:
            cur.execute("SELECT * FROM user_presets WHERE user_id = ? ORDER BY created_at DESC", (user.id,))
        rows = cur.fetchall()
        presets = []
        for row in rows:
            preset = {
                "id": row["id"],
                "name": row["name"],
                "hook_style": json.loads(row["hook_style"]) if isinstance(row["hook_style"], str) else row["hook_style"],
                "subtitle_style": json.loads(row["subtitle_style"]) if isinstance(row["subtitle_style"], str) else row["subtitle_style"],
                "created_at": row["created_at"],
            }
            if user.is_superadmin:
                preset["owner_email"] = row["owner_email"]
                preset["owner_name"] = row["owner_name"]
            presets.append(preset)
        return {"success": True, "data": presets, "total": len(presets)}
    finally:
        conn.close()


@router.post("", status_code=201)
async def create_preset(body: CreatePresetRequest, user: CurrentUser = Depends(get_current_user)):
    """Save a new preset for the current user."""
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO user_presets (user_id, name, hook_style, subtitle_style) VALUES (?, ?, ?, ?)",
            (user.id, body.name.strip(), json.dumps(body.hook_style), json.dumps(body.subtitle_style)),
        )
        conn.commit()
        return {"success": True, "id": cur.lastrowid, "message": f"Preset '{body.name}' saved"}
    finally:
        conn.close()


@router.delete("/{preset_id}")
async def delete_preset(preset_id: int, user: CurrentUser = Depends(get_current_user)):
    """Delete a preset. Superadmin can delete any preset, others only their own."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        if user.is_superadmin:
            cur.execute("DELETE FROM user_presets WHERE id = ?", (preset_id,))
        else:
            cur.execute("DELETE FROM user_presets WHERE id = ? AND user_id = ?", (preset_id, user.id))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Preset not found")
        return {"success": True, "message": "Preset deleted"}
    finally:
        conn.close()
