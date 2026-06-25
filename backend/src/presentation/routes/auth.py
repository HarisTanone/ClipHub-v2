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
    password: str = Field(..., min_length=8, max_length=72)
    full_name: str = Field(..., min_length=1, max_length=100)
    role_id: int = Field(..., ge=1)


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=72)


class CreateRoleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z_]+$")
    description: str = ""
    permission_ids: list[int] = []


class UpdateRoleRequest(BaseModel):
    description: Optional[str] = None
    permission_ids: Optional[list[int]] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_conn():
    """Get SQLite connection with dict-like Row factory."""
    return get_dict_connection()


def _get_user_permissions(conn, role_id: int) -> list[str]:
    """Get permission codes for a role."""
    cur = conn.cursor()
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
        cur.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
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
    """Get current user profile with permissions."""
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
                "is_active": bool(data["is_active"]),
                "created_at": data["created_at"],
                "last_login_at": data["last_login_at"],
            },
        }
    finally:
        conn.close()


# ─── User Management ─────────────────────────────────────────────────────────

@router.post("/users", status_code=201)
async def create_user(body: CreateUserRequest, admin: CurrentUser = Depends(require_permission("users:create"))):
    """Create new user (admin/superadmin only)."""
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

        hashed = hash_password(body.password)
        cur.execute(
            "INSERT INTO users (email, hashed_password, full_name, role_id) VALUES (?,?,?,?)",
            (body.email, hashed, body.full_name, body.role_id),
        )
        conn.commit()
        return {"success": True, "message": f"User '{body.email}' created with role '{role['name']}'"}
    finally:
        conn.close()


@router.get("/users")
async def list_users(_: CurrentUser = Depends(require_permission("users:read"))):
    """List all users."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT u.id, u.email, u.full_name, u.is_active, u.role_id, r.name as role_name,
            u.created_at, u.last_login_at
            FROM users u LEFT JOIN roles r ON r.id = u.role_id ORDER BY u.id"""
        )
        users = cur.fetchall()
        return {
            "success": True,
            "data": [{
                "id": u["id"], "email": u["email"], "full_name": u["full_name"],
                "is_active": bool(u["is_active"]), "role": u["role_name"], "role_id": u["role_id"],
                "created_at": u["created_at"],
                "last_login_at": u["last_login_at"],
            } for u in users],
            "total": len(users),
        }
    finally:
        conn.close()


@router.patch("/users/{user_id}")
async def update_user(user_id: int, body: UpdateUserRequest, admin: CurrentUser = Depends(require_permission("users:update"))):
    """Update user (admin+)."""
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

        updates, params = [], []
        if body.full_name is not None:
            updates.append("full_name = ?"); params.append(body.full_name)
        if body.role_id is not None:
            updates.append("role_id = ?"); params.append(body.role_id)
        if body.is_active is not None:
            updates.append("is_active = ?"); params.append(int(body.is_active))
        if body.password is not None:
            updates.append("hashed_password = ?"); params.append(hash_password(body.password))

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

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
        cur.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        cur.execute("UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        return {"success": True, "message": f"User #{user_id} deactivated"}
    finally:
        conn.close()


# ─── Role Management ─────────────────────────────────────────────────────────

@router.get("/roles")
async def list_roles(_: CurrentUser = Depends(require_permission("roles:read"))):
    """List roles with permissions."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, description, is_system FROM roles ORDER BY id")
        roles = cur.fetchall()
        result = []
        for role in roles:
            cur.execute(
                """SELECT p.id, p.code, p.name, p.category FROM permissions p
                JOIN role_permissions rp ON rp.permission_id = p.id WHERE rp.role_id = ?""",
                (role["id"],),
            )
            perms = [dict(p) for p in cur.fetchall()]
            result.append({**dict(role), "is_system": bool(role["is_system"]), "permissions": perms})
        return {"success": True, "data": result, "total": len(result)}
    finally:
        conn.close()


@router.post("/roles", status_code=201)
async def create_role(body: CreateRoleRequest, _: CurrentUser = Depends(require_superadmin())):
    """Create custom role (superadmin only)."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM roles WHERE name = ?", (body.name,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail=f"Role '{body.name}' already exists")
        cur.execute("INSERT INTO roles (name, description) VALUES (?, ?)", (body.name, body.description))
        role_id = cur.lastrowid
        for pid in body.permission_ids:
            try:
                cur.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", (role_id, pid))
            except Exception:
                pass
        conn.commit()
        return {"success": True, "data": {"id": role_id, "name": body.name}}
    finally:
        conn.close()


@router.patch("/roles/{role_id}")
async def update_role(role_id: int, body: UpdateRoleRequest, _: CurrentUser = Depends(require_superadmin())):
    """Update role (superadmin only)."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM roles WHERE id = ?", (role_id,))
        role = cur.fetchone()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        if body.description is not None:
            cur.execute("UPDATE roles SET description = ? WHERE id = ?", (body.description, role_id))
        if body.permission_ids is not None:
            cur.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
            for pid in body.permission_ids:
                try:
                    cur.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", (role_id, pid))
                except Exception:
                    pass
        conn.commit()
        return {"success": True, "message": f"Role '{role['name']}' updated"}
    finally:
        conn.close()


@router.delete("/roles/{role_id}")
async def delete_role(role_id: int, _: CurrentUser = Depends(require_superadmin())):
    """Delete custom role (superadmin only). System roles protected."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, is_system FROM roles WHERE id = ?", (role_id,))
        role = cur.fetchone()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        if role["is_system"]:
            raise HTTPException(status_code=403, detail=f"Cannot delete system role '{role['name']}'")
        cur.execute("UPDATE users SET role_id = NULL WHERE role_id = ?", (role_id,))
        cur.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
        cur.execute("DELETE FROM roles WHERE id = ?", (role_id,))
        conn.commit()
        return {"success": True, "message": f"Role '{role['name']}' deleted"}
    finally:
        conn.close()


@router.get("/permissions")
async def list_permissions(_: CurrentUser = Depends(require_permission("roles:read"))):
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
