"""Feature Access Control — Premium toggle (simplified).

Premium = true → V1 pipeline (Gemini) + ALL features unlocked
Premium = false → V2 pipeline (Groq) + features locked

No more granular feature toggles. Single boolean per user.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.infrastructure.db_connection import get_dict_connection
from src.presentation.auth_deps import CurrentUser, get_current_user

router = APIRouter(prefix="/features", tags=["features"])
logger = logging.getLogger(__name__)

# All features that premium unlocks (for frontend reference)
ALL_PREMIUM_FEATURES = [
    "dual_subtitle",
    "smart_camera",
    "smart_subtitle_pos",
    "threejs_effects",
    "ai_layer",
]


def _ensure_column():
    """Ensure is_premium column exists on users table (migration-safe)."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        # Check if column exists
        cur.execute("PRAGMA table_info(users)")
        columns = [row["name"] for row in cur.fetchall()]
        if "is_premium" not in columns:
            cur.execute("ALTER TABLE users ADD COLUMN is_premium INTEGER NOT NULL DEFAULT 0")
            conn.commit()
            logger.info("features: added is_premium column to users table")
    except Exception as e:
        logger.warning(f"features: migration check failed: {e}")
    finally:
        conn.close()

_ensure_column()


class SetPremiumRequest(BaseModel):
    user_id: int
    is_premium: bool


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/available")
async def list_available_features():
    """List all features that premium unlocks."""
    return {
        "success": True,
        "data": ALL_PREMIUM_FEATURES,
        "description": "Premium = semua fitur aktif. Non-premium = terkunci.",
    }


@router.get("/my")
async def get_my_features(user: CurrentUser = Depends(get_current_user)):
    """Get current user premium status and feature access."""
    if user.is_superadmin:
        return {
            "success": True,
            "is_premium": True,
            "features": ALL_PREMIUM_FEATURES,
            "pipeline": "v1",
        }

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT is_premium FROM users WHERE id = ?", (user.id,))
        row = cur.fetchone()
        is_premium = bool(row["is_premium"]) if row else False

        return {
            "success": True,
            "is_premium": is_premium,
            "features": ALL_PREMIUM_FEATURES if is_premium else [],
            "pipeline": "v1" if is_premium else "v2",
        }
    finally:
        conn.close()


@router.get("/user/{user_id}")
async def get_user_premium_status(user_id: int, user: CurrentUser = Depends(get_current_user)):
    """Get premium status for a specific user (superadmin only)."""
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin only")

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, email, full_name, is_premium FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"User ID {user_id} not found")

        is_premium = bool(row["is_premium"])
        return {
            "success": True,
            "data": {
                "user_id": row["id"],
                "email": row["email"],
                "full_name": row["full_name"],
                "is_premium": is_premium,
                "features": ALL_PREMIUM_FEATURES if is_premium else [],
                "pipeline": "v1" if is_premium else "v2",
            },
        }
    finally:
        conn.close()


@router.post("/set-premium")
async def set_premium_status(body: SetPremiumRequest, user: CurrentUser = Depends(get_current_user)):
    """Set user premium status (superadmin only).

    is_premium=true → V1 pipeline + all features
    is_premium=false → V2 pipeline + features locked
    """
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin only")

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, email FROM users WHERE id = ?", (body.user_id,))
        target = cur.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail=f"User ID {body.user_id} not found")

        cur.execute(
            "UPDATE users SET is_premium = ?, updated_at = datetime('now') WHERE id = ?",
            (1 if body.is_premium else 0, body.user_id),
        )
        conn.commit()

        status = "Premium (V1 Gemini)" if body.is_premium else "Free (V2 Groq)"
        logger.info(f"features: user {target['email']} set to {status} by admin {user.id}")

        return {
            "success": True,
            "message": f"User '{target['email']}' → {status}",
            "data": {
                "user_id": body.user_id,
                "is_premium": body.is_premium,
                "pipeline": "v1" if body.is_premium else "v2",
                "features": ALL_PREMIUM_FEATURES if body.is_premium else [],
            },
        }
    finally:
        conn.close()


# ─── Legacy Compatibility (kept for backward compat with old frontend) ────────

@router.post("/grant")
async def grant_feature_legacy(body: dict, user: CurrentUser = Depends(get_current_user)):
    """Legacy: grant feature → now just sets premium=true."""
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin only")
    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(status_code=422, detail="user_id required")

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_premium = 1 WHERE id = ?", (user_id,))
        conn.commit()
        return {"success": True, "message": f"User {user_id} set to premium"}
    finally:
        conn.close()


@router.post("/revoke")
async def revoke_feature_legacy(body: dict, user: CurrentUser = Depends(get_current_user)):
    """Legacy: revoke feature → now just sets premium=false."""
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin only")
    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(status_code=422, detail="user_id required")

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_premium = 0 WHERE id = ?", (user_id,))
        conn.commit()
        return {"success": True, "message": f"User {user_id} set to free"}
    finally:
        conn.close()
