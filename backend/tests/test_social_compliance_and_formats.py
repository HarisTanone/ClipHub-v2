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

    @patch("src.infrastructure.social_compliance.get_media_duration")
    @patch("src.infrastructure.social_compliance.probe_media")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=5 * 1024 * 1024)
    def test_validate_tiktok_duration_constraints(self, mock_size, mock_exists, mock_probe, mock_dur):
        from src.infrastructure.social_compliance import validate_social_media_constraints

        mock_probe.return_value = {
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920}]
        }

        # Case 1: Video under 3.0 seconds -> rejected
        mock_dur.return_value = 2.4
        valid, err = validate_social_media_constraints("dummy.mp4", platform="tiktok")
        self.assertFalse(valid)
        self.assertIn("below TikTok minimum requirement", err)

        # Case 2: Video over 600 seconds -> rejected
        mock_dur.return_value = 650.0
        valid, err = validate_social_media_constraints("dummy.mp4", platform="tiktok", max_duration_sec=600.0)
        self.assertFalse(valid)
        self.assertIn("exceeds TikTok maximum", err)

        # Case 3: Valid 45-second clip -> approved
        mock_dur.return_value = 45.0
        valid, err = validate_social_media_constraints("dummy.mp4", platform="tiktok")
        self.assertTrue(valid)
        self.assertIsNone(err)


if __name__ == "__main__":
    unittest.main()

