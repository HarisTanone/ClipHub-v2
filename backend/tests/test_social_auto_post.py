"""Comprehensive tests for SocialAutoPostService and Telegram Auto-Post Integration."""
import asyncio
import datetime as dt
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.social_auto_post_service import SocialAutoPostService
from src.infrastructure.telegram_service import TelegramService


class TestSocialAutoPost(unittest.TestCase):

    def setUp(self):
        self.service = SocialAutoPostService()
        self.tg_service = TelegramService()

    def test_calculate_ai_schedule_times_ordering(self):
        """Verify AI calculates future peak engagement hours in correct chronological order."""
        now = dt.datetime(2026, 8, 16, 10, 0, 0, tzinfo=dt.timezone.utc)
        times = self.service.calculate_ai_schedule_times(
            clip_count=3,
            peak_hours_str="11:30, 15:00, 18:30, 20:30",
            start_time=now,
        )

        self.assertEqual(len(times), 3)
        # Verify chronological order
        self.assertLess(times[0], times[1])
        self.assertLess(times[1], times[2])
        # First slot should be today ~11:30 (with jitter)
        self.assertEqual(times[0].date(), now.date())
        self.assertIn(times[0].hour, [11, 12])

    def test_calculate_ai_schedule_times_next_day_wrap(self):
        """Verify late-night jobs wrap slots cleanly to the next day's peak hours."""
        now = dt.datetime(2026, 8, 16, 23, 0, 0, tzinfo=dt.timezone.utc)
        times = self.service.calculate_ai_schedule_times(
            clip_count=2,
            peak_hours_str="11:30, 15:00, 18:30, 20:30",
            start_time=now,
        )

        self.assertEqual(len(times), 2)
        # Should be on the next day
        tomorrow = now.date() + dt.timedelta(days=1)
        self.assertEqual(times[0].date(), tomorrow)
        self.assertIn(times[0].hour, [11, 12])

    def test_extract_clip_caption_tiktok(self):
        """Verify TikTok caption extraction prioritizing tiktok key and adding tags."""
        clip = {
            "rank": 1,
            "hook": "Rahasia Mindset Juara",
            "captions": {
                "tiktok": "Tonton sampai habis trik rahasia ini!",
                "instagram": "Postingan Instagram khusus.",
            },
            "reason": "Topik sangat viral",
        }

        caption = self.service.extract_clip_caption(clip, platform="tiktok", include_hashtags=True)
        self.assertIn("Tonton sampai habis trik rahasia ini!", caption)
        self.assertIn("#fyp", caption)
        self.assertIn("#viral", caption)

    def test_extract_clip_caption_fallback_to_hook(self):
        """Verify caption falls back to hook when captions dict is empty."""
        clip = {
            "rank": 2,
            "hook": "5 Tips Finansial 2026",
            "reason": "Penting untuk pemula",
        }

        caption = self.service.extract_clip_caption(clip, platform="youtube", include_hashtags=True)
        self.assertIn("5 Tips Finansial 2026", caption)
        self.assertIn("#Shorts", caption)

    def test_telegram_settings_auto_post_fields(self):
        """Verify telegram_settings table handles auto_post options correctly."""
        updated = self.tg_service.update_settings({
            "is_enabled": True,
            "bot_token": "valid_token",
            "chat_id": "12345678",
            "auto_post_social": True,
            "auto_post_platforms": "tiktok,instagram",
            "auto_post_schedule_mode": "ai",
            "auto_post_interval_hours": 3,
            "auto_post_peak_hours": "12:00,18:00,21:00",
        })

        self.assertTrue(updated["auto_post_social"])
        self.assertEqual(updated["auto_post_platforms"], "tiktok,instagram")
        self.assertEqual(updated["auto_post_schedule_mode"], "ai")
        self.assertEqual(updated["auto_post_interval_hours"], 3)
        self.assertEqual(updated["auto_post_peak_hours"], "12:00,18:00,21:00")

    @patch("src.infrastructure.social_auto_post_service.repliz_post")
    @patch("src.infrastructure.social_auto_post_service.gdrive_uploader")
    @patch("src.infrastructure.social_auto_post_service.find_final_clip")
    @patch.object(SocialAutoPostService, "get_connected_accounts")
    def test_auto_schedule_job_clips_flow(self, mock_accounts, mock_find, mock_gdrive, mock_repliz_post):
        """Verify full auto_schedule_job_clips execution with mocked external services."""
        mock_accounts.return_value = [
            {"account_id": "acc_tt_123", "platform": "tiktok", "name": "My TikTok"},
            {"account_id": "acc_ig_456", "platform": "instagram", "name": "My Instagram"},
        ]
        mock_find.return_value = "/fake/path/clip_01_final.mp4"
        mock_gdrive.is_configured = True
        mock_gdrive.upload_video.return_value = {"direct_link": "https://drive.google.com/uc?id=123"}
        mock_repliz_post.return_value = {"_id": "sch_789", "status": "scheduled"}

        with patch("os.path.exists", return_value=True):
            clips = [
                {
                    "rank": 1,
                    "hook": "Cara Sukses di Usia Muda",
                    "captions": {"tiktok": "Wajib tahu tips ini!"},
                }
            ]

            async def _run():
                return await self.service.auto_schedule_job_clips(
                    job_id="job_test123",
                    clips=clips,
                    output_dir="/fake/path",
                    target_platforms=["tiktok", "instagram"],
                    schedule_mode="ai",
                    notify_telegram=False,
                )

            res = asyncio.run(_run())
            self.assertTrue(res["success"])
            self.assertEqual(res["scheduled_count"], 2)
            self.assertEqual(mock_repliz_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
