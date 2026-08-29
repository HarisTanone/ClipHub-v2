"""Unit tests for Social Compliance and Format Enforcement."""
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.infrastructure.social_compliance import (
    ensure_social_compliant_video,
    ensure_social_compliant_thumbnail,
    is_video_social_compliant,
)
from src.infrastructure.preset_resolver import resolve_preset


class TestSocialCompliance(unittest.TestCase):

    def test_social_compliant_video_fallback(self):
        """Verify non-existent paths return without error in tests."""
        self.assertEqual(ensure_social_compliant_video("non_existent.mp4"), "non_existent.mp4")

    def test_social_compliant_thumbnail_fallback(self):
        """Verify non-existent paths return None without error."""
        self.assertIsNone(ensure_social_compliant_thumbnail(None, None))

    def test_preset_resolver_default_fallback(self):
        """Verify resolve_preset('default') resolves to a valid preset dictionary instead of None."""
        res = resolve_preset("default", user_id=1)
        self.assertIsNotNone(res)
        self.assertIn("hook_style_config", res)
        self.assertIn("subtitle_style_config", res)


if __name__ == "__main__":
    unittest.main()
