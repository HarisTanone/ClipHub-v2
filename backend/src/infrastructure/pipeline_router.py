"""PipelineRouter — Determines V1 (Gemini) vs V2 (Groq) pipeline based on user premium status.

Logic:
- Superadmin → always V1 (implicitly premium)
- User with is_premium=1 → V1
- Everyone else → V2 (if V2_PIPELINE_ENABLED=True)
- If V2 disabled globally → V1 for all
"""
import logging

from src.config import settings
from src.infrastructure.db_connection import get_dict_connection

logger = logging.getLogger(__name__)


class PipelineRouter:
    """Routes users to V1 (Gemini) or V2 (Groq) pipeline based on is_premium flag."""

    def should_use_v2(self, user_id: int, is_superadmin: bool = False) -> bool:
        """Determine if user should use V2 (non-premium) pipeline.

        Returns True if user should use V2, False for V1.
        """
        # Global kill switch
        if not settings.V2_PIPELINE_ENABLED:
            return False

        # Superadmin checks own pipeline_override preference
        if is_superadmin:
            override = self._get_superadmin_override(user_id)
            if override == "v2":
                return True
            return False  # Default V1 for superadmin

        # Check is_premium flag on user
        is_premium = self._check_user_premium(user_id)
        if is_premium:
            return False

        # Not premium → use V2
        return True

    def get_pipeline_version(self, user_id: int, is_superadmin: bool = False) -> str:
        """Get pipeline version string for a user. Returns "v1" or "v2"."""
        if self.should_use_v2(user_id, is_superadmin):
            return "v2"
        return "v1"

    def is_user_premium(self, user_id: int) -> bool:
        """Check if a user is premium (public helper)."""
        return self._check_user_premium(user_id)

    def set_superadmin_override(self, user_id: int, pipeline_mode: str) -> None:
        """Set superadmin pipeline preference (v1 or v2)."""
        try:
            conn = get_dict_connection()
            try:
                cur = conn.cursor()
                # Store in a simple key-value or directly on user record
                # We'll use a simple approach: store in users table as a text field
                cur.execute(
                    "UPDATE users SET pipeline_override = ? WHERE id = ?",
                    (pipeline_mode, user_id),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"pipeline_router: set override failed: {e}")

    def _get_superadmin_override(self, user_id: int) -> str:
        """Get superadmin's pipeline preference. Returns 'v1' or 'v2'."""
        try:
            conn = get_dict_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT pipeline_override FROM users WHERE id = ?", (user_id,))
                result = cur.fetchone()
                if result and result["pipeline_override"]:
                    return result["pipeline_override"]
                return "v1"  # Default for superadmin
            finally:
                conn.close()
        except Exception:
            return "v1"

    def _check_user_premium(self, user_id: int) -> bool:
        """Check is_premium flag directly on users table."""
        try:
            conn = get_dict_connection()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT is_premium FROM users WHERE id = ?",
                    (user_id,),
                )
                result = cur.fetchone()
                if result is None:
                    return False
                return bool(result["is_premium"])
            finally:
                conn.close()
        except Exception as e:
            # If DB check fails, default to V1 (safe fallback)
            logger.warning(f"pipeline_router: premium check failed for user {user_id}: {e}")
            return True  # Assume premium (V1) on error
