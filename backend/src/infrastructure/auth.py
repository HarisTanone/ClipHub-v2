"""Auth infrastructure — JWT token management, password hashing, permission checks.

Provides:
- Password hashing/verification via bcrypt
- JWT access/refresh token creation and validation
- Permission checking for role-based access control
- Gemini multi-key rotation
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from src.config import settings

logger = logging.getLogger(__name__)


# ─── Password Hashing ────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ─── JWT Token Management ────────────────────────────────────────────────────

def create_access_token(user_id: int, email: str, role: str, permissions: list[str]) -> str:
    """Create JWT access token with user info and permissions."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "permissions": permissions,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    """Create JWT refresh token (longer-lived, used to get new access tokens)."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_REFRESH_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate access token. Returns payload or None."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def decode_refresh_token(token: str) -> Optional[dict]:
    """Decode and validate refresh token. Returns payload or None."""
    try:
        payload = jwt.decode(token, settings.JWT_REFRESH_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        return payload
    except JWTError:
        return None


def hash_token(token: str) -> str:
    """Hash a token for storage (refresh token tracking)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ─── Permission Checking ─────────────────────────────────────────────────────

def has_permission(user_role: str, user_permissions: list[str], required_permission: str) -> bool:
    """Check if user has required permission.

    Superadmin bypasses all permission checks.
    """
    if user_role == "superadmin":
        return True
    return required_permission in user_permissions


def is_superadmin(role: str) -> bool:
    """Check if role is superadmin (top-tier, unrestricted access)."""
    return role == "superadmin"


# ─── Gemini Multi-Key Rotation ───────────────────────────────────────────────

class GeminiKeyRotator:
    """Manages multiple Gemini API keys with automatic rotation on rate limit.

    Usage:
        rotator = GeminiKeyRotator()
        key = rotator.get_current_key()
        # ... if rate limited:
        rotator.mark_rate_limited()
        key = rotator.get_current_key()  # Returns next key
    """

    def __init__(self):
        self._keys = settings.gemini_api_keys
        self._current_index = 0
        self._rate_limited: dict[int, datetime] = {}
        self._cooldown_seconds = 60

        if self._keys:
            logger.info(f"gemini_key_rotator_init: {len(self._keys)} keys loaded")
        else:
            logger.warning("gemini_key_rotator_init: no keys configured")

    @property
    def total_keys(self) -> int:
        return len(self._keys)

    @property
    def current_index(self) -> int:
        return self._current_index

    def get_current_key(self) -> Optional[str]:
        """Get current active API key. Returns None if no keys available."""
        if not self._keys:
            return None

        now = datetime.now(timezone.utc)
        tried = 0
        while tried < len(self._keys):
            idx = self._current_index
            limited_at = self._rate_limited.get(idx)

            if limited_at is None or (now - limited_at).total_seconds() > self._cooldown_seconds:
                if idx in self._rate_limited:
                    del self._rate_limited[idx]
                key = self._keys[idx]
                logger.debug(f"gemini_using_key: key[{idx}] ...{key[-6:]}")
                return key

            self._current_index = (self._current_index + 1) % len(self._keys)
            tried += 1

        logger.warning("gemini_all_keys_rate_limited")
        return self._keys[self._current_index]

    def mark_rate_limited(self) -> None:
        """Mark current key as rate limited and switch to next."""
        key = self._keys[self._current_index]
        self._rate_limited[self._current_index] = datetime.now(timezone.utc)
        old_idx = self._current_index
        self._current_index = (self._current_index + 1) % len(self._keys)
        logger.info(f"gemini_key_rotated: key[{old_idx}] (...{key[-6:]}) → key[{self._current_index}] (...{self._keys[self._current_index][-6:]})")

    def reset(self) -> None:
        """Reset all rate limit states."""
        self._rate_limited.clear()
        self._current_index = 0
