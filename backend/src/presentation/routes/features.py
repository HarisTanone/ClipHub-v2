"""Feature Access Control — Superadmin grants/revokes premium features to users."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.infrastructure.db_connection import get_dict_connection
from src.presentation.auth_deps import CurrentUser, get_current_user

router = APIRouter(prefix="/features", tags=["features"])
logger = logging.getLogger(__name__)

# Available premium features
AVAILABLE_FEATURES = {
    "dual_subtitle": "Dual Font Style (Highlight Words)",
    "smart_camera": "Smart Camera (Photography Principles)",
    "smart_subtitle_pos": "Smart Subtitle Positioning",
    "threejs_effects": "Three.js 3D Effects",
    "ai_layer": "AI Generated Layer",
}


def _ensure_table():
    conn = get_dict_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_features (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                feature_code TEXT NOT NULL,
                granted_by INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(user_id, feature_code),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (granted_by) REFERENCES users(id)
            )
        """)
        conn.commit()
    finally:
        conn.close()

_ensure_table()


class GrantFeatureRequest(BaseModel):
    user_id: int
    feature_code: str


class BatchGrantRequest(BaseModel):
    user_id: int
    feature_codes: list[str]


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/available")
async def list_available_features():
    """List all available premium features."""
    return {"success": True, "data": AVAILABLE_FEATURES}


@router.get("/my")
async def get_my_features(user: CurrentUser = Depends(get_current_user)):
    """Get features granted to current user."""
    if user.is_superadmin:
        return {"success": True, "data": list(AVAILABLE_FEATURES.keys()), "is_superadmin": True}

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT feature_code FROM user_features WHERE user_id = ?", (user.id,))
        features = [row["feature_code"] for row in cur.fetchall()]
        return {"success": True, "data": features}
    finally:
        conn.close()


@router.get("/user/{user_id}")
async def get_user_features(user_id: int, user: CurrentUser = Depends(get_current_user)):
    """Get features for a specific user (superadmin only)."""
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin only")

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT feature_code, created_at FROM user_features WHERE user_id = ?", (user_id,))
        features = [{"code": row["feature_code"], "name": AVAILABLE_FEATURES.get(row["feature_code"], row["feature_code"]), "granted_at": row["created_at"]} for row in cur.fetchall()]
        return {"success": True, "data": features}
    finally:
        conn.close()


@router.post("/grant")
async def grant_feature(body: GrantFeatureRequest, user: CurrentUser = Depends(get_current_user)):
    """Grant a premium feature to a user (superadmin only)."""
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin only")
    if body.feature_code not in AVAILABLE_FEATURES:
        raise HTTPException(status_code=400, detail=f"Unknown feature: {body.feature_code}")

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        # Validate user exists
        cur.execute("SELECT id FROM users WHERE id = ?", (body.user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail=f"User ID {body.user_id} not found")

        cur.execute(
            "INSERT OR IGNORE INTO user_features (user_id, feature_code, granted_by) VALUES (?, ?, ?)",
            (body.user_id, body.feature_code, user.id),
        )
        conn.commit()
        already_had = cur.rowcount == 0
        if already_had:
            return {"success": True, "message": f"User {body.user_id} already has feature '{body.feature_code}'"}
        return {"success": True, "message": f"Feature '{body.feature_code}' granted to user {body.user_id}"}
    finally:
        conn.close()


@router.post("/grant-batch")
async def grant_features_batch(body: BatchGrantRequest, user: CurrentUser = Depends(get_current_user)):
    """Grant multiple premium features to a user at once (superadmin only)."""
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin only")

    # Validate all feature codes
    invalid = [f for f in body.feature_codes if f not in AVAILABLE_FEATURES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown features: {', '.join(invalid)}")

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        # Validate user exists
        cur.execute("SELECT id FROM users WHERE id = ?", (body.user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail=f"User ID {body.user_id} not found")

        granted = []
        skipped = []
        for code in body.feature_codes:
            cur.execute(
                "INSERT OR IGNORE INTO user_features (user_id, feature_code, granted_by) VALUES (?, ?, ?)",
                (body.user_id, code, user.id),
            )
            if cur.rowcount > 0:
                granted.append(code)
            else:
                skipped.append(code)
        conn.commit()

        return {
            "success": True,
            "message": f"{len(granted)} features granted, {len(skipped)} already assigned",
            "data": {"granted": granted, "skipped": skipped},
        }
    finally:
        conn.close()


@router.post("/grant-all")
async def grant_all_features(body: dict, user: CurrentUser = Depends(get_current_user)):
    """Grant ALL premium features to a user (superadmin only). Body: {user_id: int}"""
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin only")

    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(status_code=422, detail="user_id is required")

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail=f"User ID {user_id} not found")

        granted = []
        for code in AVAILABLE_FEATURES:
            cur.execute(
                "INSERT OR IGNORE INTO user_features (user_id, feature_code, granted_by) VALUES (?, ?, ?)",
                (user_id, code, user.id),
            )
            if cur.rowcount > 0:
                granted.append(code)
        conn.commit()

        return {
            "success": True,
            "message": f"All features granted to user {user_id} ({len(granted)} new)",
            "data": {"granted": granted, "total_features": len(AVAILABLE_FEATURES)},
        }
    finally:
        conn.close()


@router.post("/revoke")
async def revoke_feature(body: GrantFeatureRequest, user: CurrentUser = Depends(get_current_user)):
    """Revoke a premium feature from a user (superadmin only)."""
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin only")

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        # Validate user exists
        cur.execute("SELECT id FROM users WHERE id = ?", (body.user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail=f"User ID {body.user_id} not found")

        cur.execute("DELETE FROM user_features WHERE user_id = ? AND feature_code = ?", (body.user_id, body.feature_code))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Feature not found for this user")
        return {"success": True, "message": f"Feature '{body.feature_code}' revoked from user {body.user_id}"}
    finally:
        conn.close()


@router.post("/revoke-all")
async def revoke_all_features(body: dict, user: CurrentUser = Depends(get_current_user)):
    """Revoke ALL premium features from a user (superadmin only). Body: {user_id: int}"""
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin only")

    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(status_code=422, detail="user_id is required")

    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail=f"User ID {user_id} not found")

        cur.execute("DELETE FROM user_features WHERE user_id = ?", (user_id,))
        conn.commit()
        return {"success": True, "message": f"All features revoked from user {user_id} ({cur.rowcount} removed)"}
    finally:
        conn.close()
