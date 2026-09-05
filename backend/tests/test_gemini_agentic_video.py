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

@pytest.mark.asyncio
async def test_agentic_video_service_derive_queries_with_gemini():
    from src.infrastructure.gemini_agentic_video_service import GeminiAgenticVideoService
    service = GeminiAgenticVideoService()
    service._key_rotator._keys = ["test_key"]

    mock_resp = MagicMock()
    mock_resp.text = '{"queries": ["boxing gym workout", "focused entrepreneur office"]}'

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        queries = await service.derive_contextual_queries(
            keyword="FIGHT TERUS",
            subtitle_text="kalau bisnis kamu drop, kamu harus fight terus jangan nyerah",
            context="motivasi bisnis",
            placement="behind_person",
        )

        assert "boxing gym workout" in queries
        assert "focused entrepreneur office" in queries
        mock_client.models.generate_content.assert_called_once()


@pytest.mark.asyncio
async def test_agentic_video_service_derive_queries_heuristic_fallback():
    from src.infrastructure.gemini_agentic_video_service import GeminiAgenticVideoService
    service = GeminiAgenticVideoService()
    service._key_rotator._keys = []

    queries = await service.derive_contextual_queries(
        keyword="bisnis",
        subtitle_text="ada banyak kesempatan bisnis dan peluang di toko ini",
        context="",
        placement="behind_person",
    )

    assert len(queries) > 0
    assert any("business" in q or "store" in q or "shop" in q for q in queries)


def test_gemini_rate_limit_error_detection():
    from src.infrastructure.auth import is_gemini_rate_limit_error

    err_msg = (
        "Error code: 429 - {'error': {'message': 'You exceeded your current quota, please check your plan and billing details. "
        "For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. "
        "* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.7-flash\\n"
        "Please retry in 49.65878073s.', 'code': 'too_many_requests'}}"
    )
    is_rl, retry_sec = is_gemini_rate_limit_error(Exception(err_msg))
    assert is_rl is True
    assert 50.0 <= retry_sec <= 55.0

    # Non-rate limit error
    is_rl_normal, retry_normal = is_gemini_rate_limit_error(ValueError("Invalid JSON"))
    assert is_rl_normal is False
    assert retry_normal == 0.0


def test_gemini_key_rotator_behavior():
    from src.infrastructure.auth import GeminiKeyRotator

    rotator = GeminiKeyRotator(keys=["key_alpha", "key_beta", "key_gamma"])
    rotator.reset()

    # Initial order
    avail = rotator.get_available_keys()
    assert avail == ["key_alpha", "key_beta", "key_gamma"]
    assert rotator.get_current_key() == "key_alpha"

    # Mark key_alpha rate-limited
    rotator.mark_rate_limited(key="key_alpha", retry_after=30.0)
    assert rotator.is_key_rate_limited("key_alpha") is True
    assert rotator.is_key_rate_limited("key_beta") is False

    # Healthy keys prioritized first
    avail_after = rotator.get_available_keys()
    assert avail_after[0] == "key_beta"
    assert avail_after[1] == "key_gamma"
    assert avail_after[2] == "key_alpha"
    assert rotator.get_current_key() == "key_beta"

    # Mark key_beta rate-limited too
    rotator.mark_rate_limited(key="key_beta", retry_after=30.0)
    avail_third = rotator.get_available_keys()
    assert avail_third[0] == "key_gamma"
    assert rotator.get_current_key() == "key_gamma"

    rotator.reset()


def test_agentic_video_service_auto_rotates_on_429(tmp_path):
    from src.infrastructure.gemini_agentic_video_service import GeminiAgenticVideoService
    from src.infrastructure.auth import GeminiKeyRotator

    service = GeminiAgenticVideoService()
    test_keys = ["gemini_key_1", "gemini_key_2"]
    service._key_rotator = GeminiKeyRotator(keys=test_keys)
    service._key_rotator.reset()

    dummy_video = tmp_path / "test.mp4"
    dummy_video.write_bytes(b"fake video data 1234567890")

    mock_resp = MagicMock()
    mock_resp.output_text = '{"is_relevant": true, "alignment_score": 8.8, "best_start_timestamp": 2.0, "best_end_timestamp": 6.0, "best_start_mm_ss": "00:02", "best_end_mm_ss": "00:06"}'
    mock_resp.steps = []

    created_clients = {}

    def mock_client_factory(api_key):
        client = MagicMock()
        if api_key == "gemini_key_1":
            # Simulate 429 quota error on key 1
            client.interactions.create.side_effect = Exception(
                "Error code: 429 - {'error': {'message': 'Quota exceeded. Please retry in 45s.', 'code': 'too_many_requests'}}"
            )
        else:
            # Key 2 succeeds
            client.interactions.create.return_value = mock_resp

        created_clients[api_key] = client
        return client

    with patch("google.genai.Client", side_effect=mock_client_factory):
        res = service._analyze_alignment_sync(
            video_path=str(dummy_video),
            prompt="Find best interval",
            target_duration=4.0,
            timeout=10,
            processing_mode="agentic",
        )

        assert res["alignment_score"] == 8.8
        assert res["best_start_timestamp"] == 2.0
        # Key 1 was rate limited and rotated
        assert service._key_rotator.is_key_rate_limited("gemini_key_1") is True
        # Key 1 should NOT have called generate_content fallback
        assert created_clients["gemini_key_1"].models.generate_content.called is False
        # Key 2 was called and succeeded
        assert created_clients["gemini_key_2"].interactions.create.called is True




