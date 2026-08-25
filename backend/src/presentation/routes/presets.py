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


# ─── Helper Functions ─────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convert text into clean lowercase slug (e.g. 'Gaming Style 01' -> 'gaming-style-01')."""
    import re
    cleaned = re.sub(r"[^a-zA-Z0-9\s_-]", "", str(text or "").lower())
    slug = re.sub(r"[\s_-]+", "-", cleaned).strip("-")
    return slug or "preset"


def _generate_unique_slug(conn, base_slug: str, user_id: Optional[int] = None, exclude_id: Optional[int] = None) -> str:
    """Generate a unique slug in user_presets."""
    slug = base_slug
    counter = 1
    while True:
        query = "SELECT id FROM user_presets WHERE slug = ?"
        params = [slug]
        if exclude_id is not None:
            query += " AND id != ?"
            params.append(exclude_id)
        cur = conn.cursor()
        cur.execute(query, tuple(params))
        if not cur.fetchone():
            return slug
        counter += 1
        slug = f"{base_slug}-{counter:02d}"


# ─── Ensure table ─────────────────────────────────────────────────────────────

def _ensure_presets_table():
    conn = get_dict_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                slug TEXT NOT NULL DEFAULT '',
                hook_style JSON NOT NULL DEFAULT '{}',
                subtitle_style JSON NOT NULL DEFAULT '{}',
                text_emphasis_style JSON NOT NULL DEFAULT '{}',
                watermark_style JSON NOT NULL DEFAULT '{}',
                cta_style JSON NOT NULL DEFAULT '{}',
                broll_style JSON NOT NULL DEFAULT '{}',
                autopost_style JSON NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(user_presets)").fetchall()}
        if "slug" not in columns:
            conn.execute("ALTER TABLE user_presets ADD COLUMN slug TEXT NOT NULL DEFAULT ''")
            # Populate existing rows with slugs
            rows = conn.execute("SELECT id, name FROM user_presets").fetchall()
            for r in rows:
                r_dict = dict(r)
                base = slugify(r_dict["name"]) or f"preset-{r_dict['id']}"
                gen_slug = f"{base}-{r_dict['id']:02d}"
                conn.execute("UPDATE user_presets SET slug = ? WHERE id = ?", (gen_slug, r_dict["id"]))
        if "text_emphasis_style" not in columns:
            conn.execute("ALTER TABLE user_presets ADD COLUMN text_emphasis_style JSON NOT NULL DEFAULT '{}'")
        if "watermark_style" not in columns:
            conn.execute("ALTER TABLE user_presets ADD COLUMN watermark_style JSON NOT NULL DEFAULT '{}'")
        if "cta_style" not in columns:
            conn.execute("ALTER TABLE user_presets ADD COLUMN cta_style JSON NOT NULL DEFAULT '{}'")
        if "broll_style" not in columns:
            conn.execute("ALTER TABLE user_presets ADD COLUMN broll_style JSON NOT NULL DEFAULT '{}'")
        if "autopost_style" not in columns:
            conn.execute("ALTER TABLE user_presets ADD COLUMN autopost_style JSON NOT NULL DEFAULT '{}'")
        conn.commit()
    finally:
        conn.close()

_ensure_presets_table()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class CreatePresetRequest(BaseModel):
    name: str
    slug: Optional[str] = None
    hook_style: dict = {}
    subtitle_style: dict = {}
    text_emphasis_style: dict = {}
    watermark_style: dict = {}
    cta_style: dict = {}
    broll_style: dict = {}
    autopost_style: dict = {}

class PresetResponse(BaseModel):
    id: int
    name: str
    slug: str = ""
    hook_style: dict
    subtitle_style: dict
    text_emphasis_style: dict
    watermark_style: dict
    cta_style: dict = {}
    broll_style: dict = {}
    autopost_style: dict = {}
    created_at: Optional[str] = None


def _format_preset_dict(row, is_superadmin: bool = False) -> dict:
    """Safely format a database row (sqlite3.Row or dict) into a preset dict."""
    r = dict(row)

    def _parse_json_field(val):
        if isinstance(val, dict):
            return val
        if isinstance(val, str) and val.strip():
            try:
                return json.loads(val)
            except Exception:
                return {}
        return {}

    preset = {
        "id": r["id"],
        "name": r["name"],
        "slug": r.get("slug") or f"preset-{r['id']}",
        "hook_style": _parse_json_field(r.get("hook_style")),
        "subtitle_style": _parse_json_field(r.get("subtitle_style")),
        "text_emphasis_style": _parse_json_field(r.get("text_emphasis_style")),
        "watermark_style": _parse_json_field(r.get("watermark_style")),
        "cta_style": _parse_json_field(r.get("cta_style")),
        "broll_style": _parse_json_field(r.get("broll_style")),
        "autopost_style": _parse_json_field(r.get("autopost_style")),
        "created_at": r.get("created_at"),
    }
    if is_superadmin:
        preset["owner_email"] = r.get("owner_email")
        preset["owner_name"] = r.get("owner_name")
    return preset


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
        presets = [_format_preset_dict(row, is_superadmin=user.is_superadmin) for row in rows]
        return {"success": True, "data": presets, "total": len(presets)}
    finally:
        conn.close()


@router.get("/{slug_or_id}")
async def get_preset_by_slug_or_id(slug_or_id: str, user: CurrentUser = Depends(get_current_user)):
    """Retrieve a single preset by ID or slug."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        is_id = slug_or_id.isdigit()
        if is_id:
            cur.execute("SELECT * FROM user_presets WHERE id = ?", (int(slug_or_id),))
        else:
            cur.execute("SELECT * FROM user_presets WHERE slug = ?", (slug_or_id,))
        row = cur.fetchone()
        if not row:
            # Fallback by name lookup
            cur.execute("SELECT * FROM user_presets WHERE LOWER(name) = LOWER(?)", (slug_or_id,))
            row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Preset '{slug_or_id}' tidak ditemukan")

        r_dict = dict(row)
        # Access check (owner or superadmin)
        if r_dict["user_id"] != user.id and not user.is_superadmin:
            raise HTTPException(status_code=403, detail="Akses ditolak ke preset ini")

        return {
            "success": True,
            "data": _format_preset_dict(row, is_superadmin=user.is_superadmin),
        }
    finally:
        conn.close()


@router.post("", status_code=201)
async def create_preset(body: CreatePresetRequest, user: CurrentUser = Depends(get_current_user)):
    """Save a new preset for the current user."""
    name_clean = body.name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Name is required")

    conn = get_dict_connection()
    try:
        raw_slug = slugify(body.slug.strip()) if body.slug and body.slug.strip() else slugify(name_clean)
        unique_slug = _generate_unique_slug(conn, raw_slug)

        cur = conn.cursor()
        cur.execute(
            "INSERT INTO user_presets (user_id, name, slug, hook_style, subtitle_style, text_emphasis_style, watermark_style, cta_style, broll_style, autopost_style) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user.id,
                name_clean,
                unique_slug,
                json.dumps(body.hook_style),
                json.dumps(body.subtitle_style),
                json.dumps(body.text_emphasis_style),
                json.dumps(body.watermark_style),
                json.dumps(body.cta_style),
                json.dumps(body.broll_style),
                json.dumps(body.autopost_style),
            ),
        )
        conn.commit()
        return {
            "success": True,
            "id": cur.lastrowid,
            "slug": unique_slug,
            "message": f"Preset '{name_clean}' berhasil disimpan dengan slug: {unique_slug}",
        }
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
