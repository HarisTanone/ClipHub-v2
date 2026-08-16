"""Comprehensive unit tests for TelegramService, Telegram API routes, and tools."""
import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.telegram_service import TelegramService
from src.presentation.routes.telegram import (
    TelegramSettingsRequest,
    TelegramTestRequest,
    TelegramSendClipRequest,
)


class TestTelegramService(unittest.TestCase):
    """Test suite for TelegramService infrastructure."""

    def setUp(self):
        self.service = TelegramService()

    def test_get_settings_default(self):
        """Verify default settings structure and types."""
        settings = self.service.get_settings(mask_token=False)
        self.assertIn("is_enabled", settings)
        self.assertIn("bot_token", settings)
        self.assertIn("chat_id", settings)
        self.assertIn("notify_on_job_start", settings)
        self.assertIn("notify_on_job_complete", settings)
        self.assertIn("notify_on_job_failed", settings)
        self.assertIn("send_video_files", settings)
        self.assertIn("notify_target", settings)

    def test_update_settings(self):
        """Verify updating settings in SQLite."""
        new_cfg = {
            "is_enabled": True,
            "bot_token": "123456789:ABCDEF_TEST_TOKEN_12345",
            "bot_username": "AutoCliperTestBot",
            "chat_id": "12345678",
            "group_id": "-100123456789",
            "channel_id": "-100987654321",
            "topic_id": "42",
            "allowed_users": "12345678,87654321",
            "notify_on_job_start": True,
            "notify_on_job_complete": True,
            "notify_on_job_failed": True,
            "send_video_files": True,
            "include_caption": True,
            "include_hashtags": True,
            "include_virality_score": True,
            "notify_target": "all",
        }
        res = self.service.update_settings(new_cfg)
        self.assertTrue(res["is_enabled"])
        self.assertEqual(res["bot_token"], "123456789:ABCDEF_TEST_TOKEN_12345")
        self.assertEqual(res["bot_username"], "AutoCliperTestBot")
        self.assertEqual(res["chat_id"], "12345678")
        self.assertEqual(res["group_id"], "-100123456789")
        self.assertEqual(res["topic_id"], "42")

        # Test token masking
        masked = self.service.get_settings(mask_token=True)
        self.assertIn("bot_token_masked", masked)
        self.assertTrue(masked["bot_token_masked"].startswith("1234"))
        self.assertTrue(masked["bot_token_masked"].endswith("2345"))

    def test_get_target_destinations(self):
        """Verify target destination resolver."""
        cfg = {
            "notify_target": "all",
            "chat_id": "111",
            "group_id": "222",
            "channel_id": "333",
        }
        destinations = self.service._get_target_destinations(cfg)
        self.assertEqual(destinations, ["111", "222", "333"])

        # Specific chat only
        cfg["notify_target"] = "chat"
        self.assertEqual(self.service._get_target_destinations(cfg), ["111"])

        # Specific group only
        cfg["notify_target"] = "group"
        self.assertEqual(self.service._get_target_destinations(cfg), ["222"])

        # Specific channel only
        cfg["notify_target"] = "channel"
        self.assertEqual(self.service._get_target_destinations(cfg), ["333"])

        # Explicit target override
        self.assertEqual(self.service._get_target_destinations(cfg, explicit_target="999"), ["999"])

    @patch("httpx.AsyncClient.get")
    @patch("httpx.AsyncClient.post")
    def test_test_connection_success(self, mock_post, mock_get):
        """Verify test_connection with mocked Telegram API responses."""
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            "ok": True,
            "result": {
                "id": 123456789,
                "first_name": "AutoCliper Bot",
                "username": "autocliper_test_bot",
            },
        }
        mock_get.return_value = mock_get_resp

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_post_resp

        async def _run():
            return await self.service.test_connection(
                bot_token="test_token",
                target_id="12345678",
            )

        res = asyncio.run(_run())
        self.assertTrue(res["success"])
        self.assertEqual(res["bot_username"], "autocliper_test_bot")
        self.assertEqual(res["bot_name"], "AutoCliper Bot")
        self.assertTrue(res["message_sent"])

    @patch("httpx.AsyncClient.post")
    def test_send_message_disabled(self, mock_post):
        """Verify send_message does nothing if disabled and no explicit target."""
        self.service.update_settings({"is_enabled": False, "bot_token": ""})

        async def _run():
            return await self.service.send_message("<b>Hello</b>")

        res = asyncio.run(_run())
        self.assertFalse(res)
        mock_post.assert_not_called()

    @patch("httpx.AsyncClient.post")
    def test_notify_job_started(self, mock_post):
        """Verify notify_job_started sends message when enabled."""
        self.service.update_settings({
            "is_enabled": True,
            "bot_token": "valid_token",
            "chat_id": "12345678",
            "notify_on_job_start": True,
        })
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        async def _run():
            return await self.service.notify_job_started(
                job_id="job_abc1234567",
                title="Amazing Podcast Episode",
                source_url="https://youtube.com/watch?v=123",
            )

        res = asyncio.run(_run())
        self.assertTrue(res)
        mock_post.assert_called()

    @patch("httpx.AsyncClient.post")
    def test_notify_job_failed(self, mock_post):
        """Verify notify_job_failed sends message when enabled."""
        self.service.update_settings({
            "is_enabled": True,
            "bot_token": "valid_token",
            "chat_id": "12345678",
            "notify_on_job_failed": True,
        })
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        async def _run():
            return await self.service.notify_job_failed(
                job_id="job_abc1234567",
                error="Video download failed: 404 Not Found",
                title="Amazing Podcast Episode",
            )

        res = asyncio.run(_run())
        self.assertTrue(res)
        mock_post.assert_called()

    @patch("httpx.AsyncClient.post")
    def test_notify_job_completed(self, mock_post):
        """Verify notify_job_completed sends message when enabled."""
        self.service.update_settings({
            "is_enabled": True,
            "bot_token": "valid_token",
            "chat_id": "12345678",
            "notify_on_job_complete": True,
            "send_video_files": False,
        })
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        clips = [
            {"rank": 1, "hook": "The most insane hack", "virality_score": 95},
            {"rank": 2, "hook": "Why everyone gets this wrong", "virality_score": 88},
        ]

        async def _run():
            return await self.service.notify_job_completed(
                job_id="job_abc1234567",
                title="Amazing Podcast Episode",
                clips_count=2,
                clips=clips,
            )

        res = asyncio.run(_run())
        self.assertTrue(res)
        mock_post.assert_called()

    def test_send_video_missing_file(self):
        """Verify send_video returns error if file does not exist."""
        self.service.update_settings({
            "is_enabled": True,
            "bot_token": "valid_token",
            "chat_id": "12345678",
        })

        async def _run():
            return await self.service.send_video(
                video_path="/nonexistent/path/video.mp4",
                caption="Test caption",
            )

        res = asyncio.run(_run())
        self.assertFalse(res["success"])
        self.assertIn("File video tidak ditemukan", res["error"])


if __name__ == "__main__":
    unittest.main()
