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

    @patch("subprocess.run")
    def test_social_compliant_thumbnail_hook_sync(self, mock_run):
        """Verify compliant thumbnail extraction captures hook at seek and syncs to candidate_thumb."""
        with tempfile.TemporaryDirectory() as td:
            dummy_video = os.path.join(td, "clip_01_final.mp4")
            candidate_thumb = os.path.join(td, "clip_01.jpg")
            social_thumb = os.path.join(td, "clip_01_social.jpg")
            with open(dummy_video, "wb") as f:
                f.write(b"dummy video")

            def fake_ffmpeg(cmd, **kwargs):
                out = cmd[-1]
                with open(out, "wb") as f:
                    f.write(b"dummy image content")
                m = MagicMock()
                m.returncode = 0
                return m

            mock_run.side_effect = fake_ffmpeg

            res = ensure_social_compliant_thumbnail(
                thumb_path=candidate_thumb,
                video_path=dummy_video,
                output_path=social_thumb,
                seek=1.2,
            )
            self.assertEqual(res, social_thumb)
            self.assertTrue(os.path.exists(social_thumb))
            self.assertTrue(os.path.exists(candidate_thumb))
            cmd_args = mock_run.call_args[0][0]
            self.assertIn("-ss", cmd_args)
            idx = cmd_args.index("-ss")
            self.assertEqual(cmd_args[idx + 1], "1.20")

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
    def test_validate_all_platform_constraints(self, mock_size, mock_exists, mock_probe, mock_dur):
        from src.infrastructure.social_compliance import validate_social_media_constraints

        mock_probe.return_value = {
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920}]
        }

        # Instagram: min 3.0s, max 900s
        mock_dur.return_value = 2.0
        valid, err = validate_social_media_constraints("dummy.mp4", platform="instagram")
        self.assertFalse(valid)
        self.assertIn("below Reels minimum requirement", err)

        mock_dur.return_value = 60.0
        valid, err = validate_social_media_constraints("dummy.mp4", platform="instagram")
        self.assertTrue(valid)

        # Facebook: min 3.0s, max 900s
        mock_dur.return_value = 950.0
        valid, err = validate_social_media_constraints("dummy.mp4", platform="facebook")
        self.assertFalse(valid)
        self.assertIn("exceeds Reels maximum", err)

        # YouTube Shorts: max 180s
        mock_dur.return_value = 200.0
        valid, err = validate_social_media_constraints("dummy.mp4", platform="youtube")
        self.assertFalse(valid)
        self.assertIn("exceeds YouTube Shorts maximum", err)

        mock_dur.return_value = 55.0
        valid, err = validate_social_media_constraints("dummy.mp4", platform="youtube")
        self.assertTrue(valid)

    def test_get_supported_post_types_matrix(self):
        from src.presentation.routes.social.publish import get_supported_post_type

        # TikTok: must be 'video', never 'reel'
        self.assertEqual(get_supported_post_type("reel", "tiktok"), "video")
        self.assertEqual(get_supported_post_type("video", "tiktok"), "video")

        # Instagram: Repliz schema uses 'video' for reels
        self.assertEqual(get_supported_post_type("reel", "instagram"), "video")
        self.assertEqual(get_supported_post_type("story", "instagram"), "story")

        # Facebook: supports 'reel', 'video', 'story'
        self.assertEqual(get_supported_post_type("reel", "facebook"), "reel")
        self.assertEqual(get_supported_post_type("video", "facebook"), "video")

        # YouTube: must be 'video'
        self.assertEqual(get_supported_post_type("reel", "youtube"), "video")
        self.assertEqual(get_supported_post_type("video", "youtube"), "video")

        # Threads & LinkedIn
        self.assertEqual(get_supported_post_type("text", "threads"), "text")
        self.assertEqual(get_supported_post_type("video", "threads"), "video")
        self.assertEqual(get_supported_post_type("video", "linkedin"), "video")


if __name__ == "__main__":
    unittest.main()

