"""Auth dependencies for FastAPI — token extraction, user resolution, permission guards."""
import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.infrastructure.auth import decode_access_token, has_permission, is_superadmin

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


# ─── Current User Data Structure ─────────────────────────────────────────────

class CurrentUser:
    """Resolved user from JWT token."""

    __slots__ = ("id", "email", "role", "permissions")

    def __init__(self, user_id: int, email: str, role: str, permissions: list[str]):
        self.id = user_id
        self.email = email
        self.role = role
        self.permissions = permissions

    @property
    def is_superadmin(self) -> bool:
        return is_superadmin(self.role)

    def has_perm(self, permission: str) -> bool:
        return has_permission(self.role, self.permissions, permission)


# ─── Dependencies ────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> CurrentUser:
    """Extract and validate current user from Bearer token. Raises 401 if invalid."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(
        user_id=int(payload["sub"]),
        email=payload["email"],
        role=payload["role"],
        permissions=payload.get("permissions", []),
    )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[CurrentUser]:
    """Same as get_current_user but returns None for unauthenticated requests."""
    if credentials is None:
        return None
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        return None
    return CurrentUser(
        user_id=int(payload["sub"]),
        email=payload["email"],
        role=payload["role"],
        permissions=payload.get("permissions", []),
    )


# ─── Permission Guard Factory ────────────────────────────────────────────────

def require_permission(permission: str):
    """Dependency factory — creates a guard that checks a specific permission."""

    async def _guard(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has_perm(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: requires '{permission}'",
            )
        return user

    return _guard


def require_any_permission(*permissions: str):
    """Dependency factory — checks if user has ANY of the listed permissions."""

    async def _guard(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.is_superadmin:
            return user
        for perm in permissions:
            if perm in user.permissions:
                return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: requires one of {permissions}",
        )

    return _guard


def require_superadmin():
    """Dependency — only superadmin can access."""

    async def _guard(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Superadmin access required",
            )
        return user

    return _guard
