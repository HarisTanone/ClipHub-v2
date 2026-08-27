"""Auth routes — login, refresh token, user & role management (SQLite).

Endpoints:
- POST /auth/login              — Login → access + refresh tokens
- POST /auth/refresh            — Refresh access token
- POST /auth/logout             — Revoke refresh token
- GET  /auth/me                 — Current user profile
- POST /auth/users              — Create user (admin+)
- GET  /auth/users              — List users (admin+)
- PATCH /auth/users/{id}        — Update user (admin+)
- DELETE /auth/users/{id}       — Deactivate user (admin+)
- GET  /auth/roles              — List roles
- POST /auth/roles              — Create role (superadmin)
- PATCH /auth/roles/{id}        — Update role (superadmin)
- DELETE /auth/roles/{id}       — Delete role (superadmin)
- GET  /auth/permissions        — List permissions
"""
import datetime as dt
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.config import settings
from src.infrastructure.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from src.infrastructure.db_connection import get_dict_connection
from src.presentation.auth_deps import (
    CurrentUser,
    get_current_user,
    require_permission,
    require_any_permission,
    require_superadmin,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


# ─── Request/Response Models ─────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class CreateUserRequest(BaseModel):
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=6, max_length=72)
    full_name: str = Field(..., min_length=1, max_length=100)
    role_id: Optional[int] = Field(default=3, ge=1)  # Default: editor role
    is_premium: bool = False
    feature_codes: Optional[list[str]] = None  # Optional: grant features on creation


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None
    is_premium: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=6, max_length=72)


class CreateRoleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$")
    description: str = ""
    permission_ids: list[int] = []


class UpdateRoleRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$")
    description: Optional[str] = None
    permission_ids: Optional[list[int]] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_conn():
    """Get SQLite connection with dict-like Row factory."""
    return get_dict_connection()


def _get_user_permissions(conn, role_id: int) -> list[str]:
    """Get permission codes for a role. Superadmin gets all permission codes or ['*']."""
    cur = conn.cursor()
    cur.execute("SELECT name FROM roles WHERE id = ?", (role_id,))
    role = cur.fetchone()
    if role and role["name"] == "superadmin":
        cur.execute("SELECT code FROM permissions")
        return [row["code"] for row in cur.fetchall()] or ["*"]

    cur.execute(
        """SELECT p.code FROM permissions p
        JOIN role_permissions rp ON rp.permission_id = p.id
        WHERE rp.role_id = ?""",
        (role_id,),
    )
    return [row["code"] for row in cur.fetchall()]


# ─── Auth Endpoints ──────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """Authenticate with email/password. Returns JWT access + refresh tokens."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT u.id, u.email, u.hashed_password, u.is_active, u.role_id, r.name as role_name
            FROM users u LEFT JOIN roles r ON r.id = u.role_id
            WHERE u.email = ?""",
            (body.email,),
        )
        user = cur.fetchone()

        if not user or not verify_password(body.password, user["hashed_password"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not user["is_active"]:
            raise HTTPException(status_code=403, detail="Account is deactivated")

        permissions = _get_user_permissions(conn, user["role_id"]) if user["role_id"] else []
        role_name = user["role_name"] or "viewer"

        access_token = create_access_token(user["id"], user["email"], role_name, permissions)
        refresh_token = create_refresh_token(user["id"])

        token_h = hash_token(refresh_token)
        expires_at = (dt.datetime.utcnow() + dt.timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)).isoformat()

        cur.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
            (user["id"], token_h, expires_at),
        )
        cur.execute("UPDATE users SET last_login_at = datetime('now') WHERE id = ?", (user["id"],))
        conn.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    finally:
        conn.close()


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(body: RefreshRequest):
    """Get new access token using refresh token (auto-rotate refresh)."""
    payload = decode_refresh_token(body.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user_id = int(payload["sub"])
    token_h = hash_token(body.refresh_token)

    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM refresh_tokens WHERE token_hash = ? AND user_id = ? AND revoked = 0 AND expires_at > datetime('now')",
            (token_h, user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=401, detail="Refresh token revoked or expired")

        cur.execute(
            """SELECT u.id, u.email, u.is_active, u.role_id, r.name as role_name
            FROM users u LEFT JOIN roles r ON r.id = u.role_id WHERE u.id = ?""",
            (user_id,),
        )
        user = cur.fetchone()

        if not user or not user["is_active"]:
            raise HTTPException(status_code=403, detail="Account deactivated")

        permissions = _get_user_permissions(conn, user["role_id"]) if user["role_id"] else []
        role_name = user["role_name"] or "viewer"

        new_access = create_access_token(user["id"], user["email"], role_name, permissions)
        new_refresh = create_refresh_token(user["id"])
        new_hash = hash_token(new_refresh)
        expires_at = (dt.datetime.utcnow() + dt.timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)).isoformat()

        cur.execute("UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ?", (token_h,))
        try:
            cur.execute(
                "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
                (user_id, new_hash, expires_at),
            )
        except Exception:
            # Race condition: another concurrent request already inserted this hash.
            # Regenerate token with fresh hash to avoid collision.
            new_refresh = create_refresh_token(user["id"])
            new_hash = hash_token(new_refresh)
            cur.execute(
                "INSERT OR IGNORE INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
                (user_id, new_hash, expires_at),
            )
        conn.commit()

        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    finally:
        conn.close()


@router.post("/logout")
async def logout(body: RefreshRequest):
    """Revoke refresh token (logout)."""
    token_h = hash_token(body.refresh_token)
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ?", (token_h,))
        conn.commit()
        return {"success": True, "message": "Logged out"}
    finally:
        conn.close()


@router.get("/me")
async def get_me(user: CurrentUser = Depends(get_current_user)):
    """Get current user profile with premium status."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT u.id, u.email, u.full_name, u.is_active, u.role_id, r.name as role_name,
            u.created_at, u.last_login_at
            FROM users u LEFT JOIN roles r ON r.id = u.role_id WHERE u.id = ?""",
            (user.id,),
        )
        data = cur.fetchone()
        if not data:
            raise HTTPException(status_code=404, detail="User not found")

        # Determine premium status
        is_premium = False
        if user.is_superadmin:
            is_premium = True
        else:
            try:
                cur.execute("SELECT is_premium FROM users WHERE id = ?", (user.id,))
                prem_row = cur.fetchone()
                is_premium = bool(prem_row["is_premium"]) if prem_row else False
            except Exception:
                pass

        # Premium → all features unlocked, Non-premium → none
        from src.presentation.routes.features import ALL_PREMIUM_FEATURES
        features = ALL_PREMIUM_FEATURES if is_premium else []

        return {
            "success": True,
            "data": {
                "id": data["id"],
                "email": data["email"],
                "full_name": data["full_name"],
                "role": data["role_name"],
                "role_id": data["role_id"],
                "permissions": user.permissions,
                "is_superadmin": user.is_superadmin,
                "is_premium": is_premium,
                "is_active": bool(data["is_active"]),
                "features": features,
                "pipeline": "v1" if is_premium else "v2",
                "created_at": data["created_at"],
                "last_login_at": data["last_login_at"],
            },
        }
    finally:
        conn.close()


# ─── User Management ─────────────────────────────────────────────────────────

@router.post("/users", status_code=201)
async def create_user(body: CreateUserRequest, admin: CurrentUser = Depends(require_permission("users:create"))):
    """Create new user (admin/superadmin only). Optionally grant features or premium on creation."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email = ?", (body.email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Email already registered")

        cur.execute("SELECT id, name FROM roles WHERE id = ?", (body.role_id,))
        role = cur.fetchone()
        if not role:
            raise HTTPException(status_code=400, detail=f"Role ID {body.role_id} not found")

        if role["name"] == "superadmin" and not admin.is_superadmin:
            raise HTTPException(status_code=403, detail="Only superadmin can assign superadmin role")

        # Validate feature codes if provided
        if body.feature_codes:
            from src.presentation.routes.features import AVAILABLE_FEATURES
            invalid = [f for f in body.feature_codes if f not in AVAILABLE_FEATURES]
            if invalid:
                raise HTTPException(status_code=400, detail=f"Unknown features: {', '.join(invalid)}")

        hashed = hash_password(body.password)
        cur.execute(
            "INSERT INTO users (email, hashed_password, full_name, role_id, is_premium) VALUES (?,?,?,?,?)",
            (body.email, hashed, body.full_name, body.role_id, int(body.is_premium)),
        )
        new_user_id = cur.lastrowid

        # Grant features if specified
        granted_features = []
        if body.feature_codes:
            for code in body.feature_codes:
                cur.execute(
                    "INSERT OR IGNORE INTO user_features (user_id, feature_code, granted_by) VALUES (?, ?, ?)",
                    (new_user_id, code, admin.id),
                )
                granted_features.append(code)

        conn.commit()

        msg = f"User '{body.email}' created with role '{role['name']}'"
        if granted_features:
            msg += f" and {len(granted_features)} features granted"

        return {
            "success": True,
            "message": msg,
            "data": {
                "user_id": new_user_id,
                "email": body.email,
                "role": role["name"],
                "is_premium": body.is_premium,
                "features": granted_features,
            },
        }
    finally:
        conn.close()


@router.get("/users")
async def list_users(_: CurrentUser = Depends(require_permission("users:read"))):
    """List all users with roles, status, and premium flags."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT u.id, u.email, u.full_name, u.is_active, u.is_premium, u.role_id, r.name as role_name,
            u.created_at, u.last_login_at
            FROM users u LEFT JOIN roles r ON r.id = u.role_id ORDER BY u.id"""
        )
        users = cur.fetchall()
        return {
            "success": True,
            "data": [{
                "id": u["id"],
                "email": u["email"],
                "full_name": u["full_name"],
                "is_active": bool(u["is_active"]),
                "is_premium": bool(u["is_premium"]),
                "role": u["role_name"],
                "role_id": u["role_id"],
                "created_at": u["created_at"],
                "last_login_at": u["last_login_at"],
            } for u in users],
            "total": len(users),
        }
    finally:
        conn.close()


@router.patch("/users/{user_id}")
async def update_user(user_id: int, body: UpdateUserRequest, admin: CurrentUser = Depends(require_permission("users:update"))):
    """Update user profile, role, status, or premium flag."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, role_id FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        cur.execute("SELECT name FROM roles WHERE id = ?", (user["role_id"],))
        crole = cur.fetchone()
        if crole and crole["name"] == "superadmin" and not admin.is_superadmin:
            raise HTTPException(status_code=403, detail="Cannot modify superadmin")

        if body.role_id is not None:
            cur.execute("SELECT id, name FROM roles WHERE id = ?", (body.role_id,))
            target_role = cur.fetchone()
            if not target_role:
                raise HTTPException(status_code=400, detail=f"Role ID {body.role_id} not found")
            if target_role["name"] == "superadmin" and not admin.is_superadmin:
                raise HTTPException(status_code=403, detail="Only superadmin can assign superadmin role")

        updates, params = [], []
        if body.full_name is not None:
            updates.append("full_name = ?"); params.append(body.full_name)
        if body.role_id is not None:
            updates.append("role_id = ?"); params.append(body.role_id)
        if body.is_active is not None:
            updates.append("is_active = ?"); params.append(int(body.is_active))
        if body.is_premium is not None:
            updates.append("is_premium = ?"); params.append(int(body.is_premium))
        if body.password is not None:
            updates.append("hashed_password = ?"); params.append(hash_password(body.password))

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = datetime('now')")
        params.append(user_id)
        cur.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        return {"success": True, "message": f"User #{user_id} updated"}
    finally:
        conn.close()


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, admin: CurrentUser = Depends(require_permission("users:delete"))):
    """Deactivate user (soft delete)."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_active = 0, updated_at = datetime('now') WHERE id = ?", (user_id,))
        cur.execute("UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        return {"success": True, "message": f"User #{user_id} deactivated"}
    finally:
        conn.close()


# ─── Role Management ─────────────────────────────────────────────────────────

@router.get("/roles")
async def list_roles(_: CurrentUser = Depends(require_any_permission("roles:read", "users:read"))):
    """List roles with assigned permissions and user count."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, description, is_system, created_at, updated_at FROM roles ORDER BY id")
        roles = cur.fetchall()
        result = []
        for role in roles:
            cur.execute(
                """SELECT p.id, p.code, p.name, p.category, p.description FROM permissions p
                JOIN role_permissions rp ON rp.permission_id = p.id WHERE rp.role_id = ?
                ORDER BY p.category, p.code""",
                (role["id"],),
            )
            perms = [dict(p) for p in cur.fetchall()]
            cur.execute("SELECT COUNT(*) as cnt FROM users WHERE role_id = ?", (role["id"],))
            user_cnt = cur.fetchone()["cnt"]
            result.append({
                **dict(role),
                "is_system": bool(role["is_system"]),
                "user_count": user_cnt,
                "permissions": perms,
            })
        return {"success": True, "data": result, "total": len(result)}
    finally:
        conn.close()


@router.post("/roles", status_code=201)
async def create_role(body: CreateRoleRequest, admin: CurrentUser = Depends(require_any_permission("roles:create", "system:admin"))):
    """Create custom role (admin/superadmin)."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        role_name = body.name.lower().strip()
        cur.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail=f"Role '{role_name}' already exists")

        cur.execute("INSERT INTO roles (name, description, is_system) VALUES (?, ?, 0)", (role_name, body.description))
        role_id = cur.lastrowid
        for pid in body.permission_ids:
            try:
                cur.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", (role_id, pid))
            except Exception:
                pass
        conn.commit()
        return {"success": True, "data": {"id": role_id, "name": role_name}, "message": f"Role '{role_name}' created"}
    finally:
        conn.close()


@router.patch("/roles/{role_id}")
async def update_role(role_id: int, body: UpdateRoleRequest, admin: CurrentUser = Depends(require_any_permission("roles:update", "system:admin"))):
    """Update role name, description, or permission mappings."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, is_system FROM roles WHERE id = ?", (role_id,))
        role = cur.fetchone()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")

        if role["is_system"] and body.name is not None and body.name != role["name"]:
            raise HTTPException(status_code=400, detail="Cannot rename system role")

        if body.name is not None and not role["is_system"]:
            new_name = body.name.lower().strip()
            cur.execute("SELECT id FROM roles WHERE name = ? AND id != ?", (new_name, role_id))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail=f"Role '{new_name}' already exists")
            cur.execute("UPDATE roles SET name = ? WHERE id = ?", (new_name, role_id))

        if body.description is not None:
            cur.execute("UPDATE roles SET description = ? WHERE id = ?", (body.description, role_id))

        if body.permission_ids is not None:
            if role["name"] == "superadmin" and not admin.is_superadmin:
                raise HTTPException(status_code=403, detail="Cannot modify superadmin permissions")
            cur.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
            for pid in body.permission_ids:
                try:
                    cur.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", (role_id, pid))
                except Exception:
                    pass

        cur.execute("UPDATE roles SET updated_at = datetime('now') WHERE id = ?", (role_id,))
        conn.commit()
        return {"success": True, "message": f"Role '{role['name']}' updated"}
    finally:
        conn.close()


@router.delete("/roles/{role_id}")
async def delete_role(role_id: int, admin: CurrentUser = Depends(require_any_permission("roles:delete", "system:admin"))):
    """Delete custom role. System roles protected."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, is_system FROM roles WHERE id = ?", (role_id,))
        role = cur.fetchone()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        if role["is_system"]:
            raise HTTPException(status_code=403, detail=f"Cannot delete system role '{role['name']}'")

        # Reassign users with this role to viewer (role_id=4)
        cur.execute("UPDATE users SET role_id = 4 WHERE role_id = ?", (role_id,))
        cur.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
        cur.execute("DELETE FROM roles WHERE id = ?", (role_id,))
        conn.commit()
        return {"success": True, "message": f"Role '{role['name']}' deleted"}
    finally:
        conn.close()


@router.get("/permissions")
async def list_permissions(_: CurrentUser = Depends(require_any_permission("roles:read", "users:read"))):
    """List all permissions grouped by category."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, code, name, description, category FROM permissions ORDER BY category, code")
        perms = cur.fetchall()
        grouped = {}
        for p in perms:
            grouped.setdefault(p["category"], []).append(dict(p))
        return {"success": True, "data": grouped, "total": len(perms)}
    finally:
        conn.close()
