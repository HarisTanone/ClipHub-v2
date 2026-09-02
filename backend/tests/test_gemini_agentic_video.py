"""Unit tests for Gemini Agentic Video Understanding integration."""
import os
import unittest
from unittest.mock import MagicMock, patch

import pytest
from src.config import settings
from src.infrastructure.gemini_analyzer import (
    GeminiAnalyzer,
    InteractionResponseAdapter,
)
from src.presentation.routes.settings import SystemInfo


class TestGeminiAgenticVideo(unittest.TestCase):
    def setUp(self):
        self.analyzer = GeminiAnalyzer()

    def test_interaction_response_adapter(self):
        adapter = InteractionResponseAdapter(text='{"clips": []}', steps=[{"type": "processing_call"}])
        self.assertEqual(adapter.text, '{"clips": []}')
        self.assertEqual(len(adapter.steps), 1)

    def test_resolve_video_source_youtube(self):
        mock_client = MagicMock()
        url = "https://www.youtube.com/watch?v=9hE5-98ZeCg"
        uri, mime = self.analyzer._resolve_video_source(mock_client, url)
        self.assertEqual(uri, url)
        self.assertEqual(mime, "video/mp4")
        mock_client.files.upload.assert_not_called()

    def test_resolve_video_source_gcs(self):
        mock_client = MagicMock()
        url = "gs://my-bucket/video.mp4"
        uri, mime = self.analyzer._resolve_video_source(mock_client, url)
        self.assertEqual(uri, url)
        self.assertEqual(mime, "video/mp4")
        mock_client.files.upload.assert_not_called()

    def test_resolve_video_source_local_file(self):
        mock_client = MagicMock()
        mock_file = MagicMock()
        mock_file.state.name = "ACTIVE"
        mock_file.uri = "https://generativelanguage.googleapis.com/v1beta/files/test1234"
        mock_file.mime_type = "video/mp4"
        mock_client.files.upload.return_value = mock_file

        with patch("os.path.isfile", return_value=True):
            uri, mime = self.analyzer._resolve_video_source(mock_client, "/path/to/local.mp4")
            self.assertEqual(uri, "https://generativelanguage.googleapis.com/v1beta/files/test1234")
            self.assertEqual(mime, "video/mp4")
            mock_client.files.upload.assert_called_once_with(file="/path/to/local.mp4")

    @patch("src.config.settings.GEMINI_API_KEY", "test_key_1")
    @patch("src.config.settings.GEMINI_VIDEO_PROCESSING", "agentic")
    @patch("src.config.settings.GEMINI_MODEL", "gemini-3.7-flash")
    @patch("src.config.settings.GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")
    def test_agentic_video_call_success(self):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            mock_step1 = MagicMock()
            mock_step1.type = "processing_call"
            mock_step2 = MagicMock()
            mock_step2.type = "processing_result"

            mock_interaction = MagicMock()
            mock_interaction.output_text = '{"clips": [{"rank": 1, "score": 95, "start": 10.0, "end": 55.0, "hook": "Viral Moment"}]}'
            mock_interaction.steps = [mock_step1, mock_step2]
            mock_client.interactions.create.return_value = mock_interaction

            res = self.analyzer._generate_with_video(
                "https://www.youtube.com/watch?v=example",
                "Analyze video viral moments",
                timeout=10,
            )

            self.assertIsNotNone(res)
            self.assertEqual(
                res.text,
                '{"clips": [{"rank": 1, "score": 95, "start": 10.0, "end": 55.0, "hook": "Viral Moment"}]}',
            )
            self.assertGreaterEqual(mock_client.interactions.create.call_count, 1)
            call_kwargs = mock_client.interactions.create.call_args.kwargs
            self.assertIn(call_kwargs["model"], ["gemini-3.7-flash", "gemini-3.6-flash"])
            self.assertEqual(call_kwargs["input"][0]["processing"], "agentic")
            self.assertEqual(call_kwargs["input"][0]["type"], "video")

    @patch("src.config.settings.GEMINI_API_KEY", "test_key_1")
    @patch("src.config.settings.GEMINI_VIDEO_PROCESSING", "agentic")
    @patch("src.config.settings.GEMINI_MODEL", "gemini-3.7-flash")
    @patch("src.config.settings.GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")
    def test_agentic_video_step_fallback_extraction(self):
        """When output_text is None, text is extracted from model_output step."""
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            mock_item = MagicMock()
            mock_item.type = "text"
            mock_item.text = '{"clips": [{"rank": 1, "score": 90}]}'

            mock_step = MagicMock()
            mock_step.type = "model_output"
            mock_step.content = [mock_item]

            mock_interaction = MagicMock()
            mock_interaction.output_text = None
            mock_interaction.steps = [mock_step]
            mock_client.interactions.create.return_value = mock_interaction

            res = self.analyzer._generate_with_video(
                "https://www.youtube.com/watch?v=example",
                "Analyze video viral moments",
                timeout=10,
            )

            self.assertIsNotNone(res)
            self.assertEqual(res.text, '{"clips": [{"rank": 1, "score": 90}]}')

    @patch("src.config.settings.GEMINI_API_KEY", "test_key_1")
    @patch("src.config.settings.GEMINI_VIDEO_PROCESSING", "agentic")
    @patch("src.config.settings.GEMINI_MODEL", "gemini-3.7-flash")
    @patch("src.config.settings.GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")
    def test_agentic_video_fallback_to_generate_content(self):
        """When interactions.create throws an error, it seamlessly falls back to generate_content."""
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            mock_client.interactions.create.side_effect = RuntimeError("Interactions API 404")

            mock_static_res = MagicMock()
            mock_static_res.text = '{"clips": [{"rank": 1, "score": 88}]}'
            mock_client.models.generate_content.return_value = mock_static_res

            res = self.analyzer._generate_with_video(
                "https://www.youtube.com/watch?v=example",
                "Analyze video viral moments",
                timeout=10,
            )

            self.assertIsNotNone(res)
            self.assertEqual(res.text, '{"clips": [{"rank": 1, "score": 88}]}')
            self.assertGreaterEqual(mock_client.interactions.create.call_count, 1)
            self.assertGreaterEqual(mock_client.models.generate_content.call_count, 1)

    def test_system_info_gemini_video_processing(self):
        info = SystemInfo(
            version="3.0.0",
            mode="production",
            llm_provider="9router",
            nine_router_model="groq/llama-3.3-70b",
            force_v2_pipeline=False,
            max_concurrent_jobs=5,
            max_whisper_parallel=2,
            max_render_workers=4,
            whisper_model_size="large-v3",
            gemini_model="gemini-3.6-flash",
            gemini_keys_count=3,
            gemini_video_processing="agentic",
            cdn_enabled=True,
            asset_fetch_enabled=True,
        )
        dumped = info.model_dump()
        self.assertEqual(dumped["gemini_video_processing"], "agentic")
