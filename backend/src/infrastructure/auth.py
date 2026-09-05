"""Auth infrastructure — JWT token management, password hashing, permission checks.

Provides:
- Password hashing/verification via bcrypt
- JWT access/refresh token creation and validation
- Permission checking for role-based access control
- Gemini multi-key rotation
"""
import hashlib
import logging
import re
import threading
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

    Supports:
    - Superadmin bypass (user_role == "superadmin")
    - Full wildcard ("*" or "system:admin")
    - Scope wildcard (e.g. "jobs:*" satisfies "jobs:create", "jobs:read", etc.)
    - Exact permission match (e.g. "jobs:create")
    """
    if user_role == "superadmin":
        return True
    if not user_permissions:
        return False
    if "*" in user_permissions or "system:admin" in user_permissions:
        return True
    if required_permission in user_permissions:
        return True
    if ":" in required_permission:
        scope = required_permission.split(":", 1)[0]
        if f"{scope}:*" in user_permissions:
            return True
    return False


def has_any_permission(user_role: str, user_permissions: list[str], *required_permissions: str) -> bool:
    """Check if user has AT LEAST ONE of the required permissions."""
    if user_role == "superadmin":
        return True
    return any(has_permission(user_role, user_permissions, p) for p in required_permissions)


def has_all_permissions(user_role: str, user_permissions: list[str], *required_permissions: str) -> bool:
    """Check if user has ALL of the required permissions."""
    if user_role == "superadmin":
        return True
    return all(has_permission(user_role, user_permissions, p) for p in required_permissions)


def is_superadmin(role: str) -> bool:
    """Check if role is superadmin (top-tier, unrestricted access)."""
    return role == "superadmin"


# ─── Gemini Multi-Key Rotation ───────────────────────────────────────────────

def is_gemini_rate_limit_error(exc: Exception) -> tuple[bool, float]:
    """Determines if an exception is a Gemini 429 / Quota / Rate Limit error.

    Returns:
        (is_rate_limited: bool, retry_after_seconds: float)
    """
    if not exc:
        return False, 0.0

    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None) or getattr(exc, "http_status", None)
    err_str = str(exc)
    err_lower = err_str.lower()

    is_429 = (
        status_code == 429
        or "429" in err_str
        or "too_many_requests" in err_lower
        or "resource_exhausted" in err_lower
        or "quota exceeded" in err_lower
        or "rate limit" in err_lower
        or "rate-limit" in err_lower
        or "exceeded your current quota" in err_lower
    )
    if not is_429:
        return False, 0.0

    # Extract retry time: e.g. "Please retry in 49.65878073s." or "retry_after: 50"
    retry_seconds = 60.0
    match = re.search(r"retry in ([\d\.]+)s", err_str, re.IGNORECASE)
    if not match:
        match = re.search(r"retry[-_\s]after[^\d]*([\d\.]+)", err_str, re.IGNORECASE)
    if match:
        try:
            parsed = float(match.group(1))
            # Add 2.0s buffer so we don't retry prematurely
            retry_seconds = max(10.0, min(parsed + 2.0, 180.0))
        except (ValueError, TypeError):
            pass

    return True, retry_seconds


class GeminiKeyRotator:
    """Manages multiple Gemini API keys with automatic rotation on rate limit.

    Usage:
        rotator = GeminiKeyRotator()
        key = rotator.get_current_key()
        # ... if rate limited:
        rotator.mark_rate_limited(key=key, retry_after=50.0)
        keys = rotator.get_available_keys()  # Returns healthy keys first
    """
    _shared_current_index: int = 0
    _shared_rate_limited: dict[str, tuple[datetime, float]] = {}  # key -> (limited_at, cooldown_seconds)
    _lock = threading.Lock()

    def __init__(self, keys: Optional[list[str]] = None, cooldown_seconds: float = 60.0):
        if keys is not None:
            self._keys = list(keys)
        else:
            self._keys = None
        self._cooldown_seconds = cooldown_seconds

        current_keys = self.keys
        if current_keys:
            logger.info(f"gemini_key_rotator_init: {len(current_keys)} keys loaded")
        else:
            logger.warning("gemini_key_rotator_init: no keys configured")

    @property
    def total_keys(self) -> int:
        return len(self.keys)

    @property
    def keys(self) -> list[str]:
        if self._keys is not None:
            return list(self._keys)
        try:
            from src.infrastructure.system_config_store import get_gemini_api_keys
            k_list = get_gemini_api_keys()
            if k_list:
                return k_list
        except Exception:
            pass
        return list(settings.gemini_api_keys)

    @property
    def current_index(self) -> int:
        with self._lock:
            k_len = len(self.keys)
            return (GeminiKeyRotator._shared_current_index % k_len) if k_len > 0 else 0

    @current_index.setter
    def current_index(self, val: int) -> None:
        with self._lock:
            GeminiKeyRotator._shared_current_index = val

    @property
    def _rate_limited(self) -> dict[int, datetime]:
        """Backward-compatibility: map index -> limited_at datetime."""
        res: dict[int, datetime] = {}
        all_keys = self.keys
        now = datetime.now(timezone.utc)
        for idx, k in enumerate(all_keys):
            if k in GeminiKeyRotator._shared_rate_limited:
                lim_at, cd = GeminiKeyRotator._shared_rate_limited[k]
                if (now - lim_at).total_seconds() <= cd:
                    res[idx] = lim_at
        return res

    def is_key_rate_limited(self, key: str) -> bool:
        """Check if a specific key is currently in rate limit cooldown."""
        if not key or key not in GeminiKeyRotator._shared_rate_limited:
            return False
        with self._lock:
            if key not in GeminiKeyRotator._shared_rate_limited:
                return False
            limited_at, cooldown = GeminiKeyRotator._shared_rate_limited[key]
            now = datetime.now(timezone.utc)
            if (now - limited_at).total_seconds() > cooldown:
                GeminiKeyRotator._shared_rate_limited.pop(key, None)
                return False
            return True

    def get_available_keys(self) -> list[str]:
        """Returns all keys ordered starting from current index, prioritizing healthy non-rate-limited keys."""
        all_keys = self.keys
        if not all_keys:
            return []

        with self._lock:
            now = datetime.now(timezone.utc)
            # Clean up expired entries
            for k in list(GeminiKeyRotator._shared_rate_limited.keys()):
                lim_at, cd = GeminiKeyRotator._shared_rate_limited[k]
                if (now - lim_at).total_seconds() > cd:
                    GeminiKeyRotator._shared_rate_limited.pop(k, None)

            n = len(all_keys)
            start_idx = GeminiKeyRotator._shared_current_index % n
            ordered = [all_keys[(start_idx + i) % n] for i in range(n)]

            healthy = [k for k in ordered if k not in GeminiKeyRotator._shared_rate_limited]
            limited = [k for k in ordered if k in GeminiKeyRotator._shared_rate_limited]

            if healthy:
                first_healthy = healthy[0]
                if first_healthy in all_keys:
                    GeminiKeyRotator._shared_current_index = all_keys.index(first_healthy)
                return healthy + limited

            # If all limited, sort limited keys by remaining cooldown
            limited.sort(
                key=lambda k: GeminiKeyRotator._shared_rate_limited[k][0].timestamp() + GeminiKeyRotator._shared_rate_limited[k][1]
            )
            return limited

    def get_current_key(self) -> Optional[str]:
        """Get current active API key. Returns None if no keys available."""
        avail = self.get_available_keys()
        if not avail:
            return None
        return avail[0]

    def mark_rate_limited(self, key: Optional[str] = None, retry_after: float = 60.0) -> None:
        """Mark current key or specific key as rate limited and switch to next."""
        all_keys = self.keys
        if not all_keys:
            return

        with self._lock:
            now = datetime.now(timezone.utc)
            cooldown = max(5.0, min(float(retry_after), 300.0))

            target_key = key
            if not target_key:
                cur_idx = GeminiKeyRotator._shared_current_index % len(all_keys)
                target_key = all_keys[cur_idx]

            GeminiKeyRotator._shared_rate_limited[target_key] = (now, cooldown)

            # Advance current index
            old_idx = all_keys.index(target_key) if target_key in all_keys else (GeminiKeyRotator._shared_current_index % len(all_keys))
            next_idx = (old_idx + 1) % len(all_keys)
            GeminiKeyRotator._shared_current_index = next_idx

            old_repr = f"...{target_key[-6:]}" if len(target_key) >= 6 else target_key
            next_key = all_keys[next_idx]
            next_repr = f"...{next_key[-6:]}" if len(next_key) >= 6 else next_key

            logger.warning(
                f"gemini_key_rotated: key[{old_idx}] ({old_repr}) rate-limited for {cooldown:.1f}s -> "
                f"rotating to key[{next_idx}] ({next_repr})"
            )

    def reset(self) -> None:
        """Reset all rate limit states."""
        with self._lock:
            GeminiKeyRotator._shared_rate_limited.clear()
            GeminiKeyRotator._shared_current_index = 0


_shared_rotator_instance: Optional[GeminiKeyRotator] = None


def get_gemini_key_rotator() -> GeminiKeyRotator:
    """Get the process-wide singleton GeminiKeyRotator instance."""
    global _shared_rotator_instance
    if _shared_rotator_instance is None:
        _shared_rotator_instance = GeminiKeyRotator()
    return _shared_rotator_instance
