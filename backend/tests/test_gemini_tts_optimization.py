"""Tests for Gemini TTS optimization, key rotation, pacing, and 429 recovery."""
import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from src.infrastructure.auth import GeminiKeyRotator
from src.infrastructure.gemini_tts import GeminiTTS


@pytest.fixture(autouse=True)
def clean_rotator_state():
    """Ensure GeminiKeyRotator static rate-limit dictionary is reset between tests."""
    GeminiKeyRotator._shared_rate_limited.clear()
    yield
    GeminiKeyRotator._shared_rate_limited.clear()


def test_gemini_key_rotator_cooldown_and_round_robin():
    """Verify GeminiKeyRotator round-robin balancing and cooldown inspection."""
    keys = ["AIzaSyKey1_AAA", "AIzaSyKey2_BBB", "AIzaSyKey3_CCC"]
    rotator = GeminiKeyRotator(keys=keys)

    # 1. Initially all keys are healthy
    assert rotator.get_min_cooldown_remaining() == 0.0
    assert rotator.get_key_cooldown_remaining(keys[0]) == 0.0

    # 2. Round-robin load balancing
    assert rotator.get_round_robin_key(offset=0) == keys[0]
    assert rotator.get_round_robin_key(offset=1) == keys[1]
    assert rotator.get_round_robin_key(offset=2) == keys[2]
    assert rotator.get_round_robin_key(offset=3) == keys[0]

    # 3. Mark key 1 rate limited
    rotator.mark_rate_limited(key=keys[0], retry_after=40.0)
    assert rotator.get_key_cooldown_remaining(keys[0]) > 0.0
    # Still 0.0 because keys[1] and keys[2] are available
    assert rotator.get_min_cooldown_remaining() == 0.0

    # Round-robin now skips key[0] and rotates over healthy keys
    assert rotator.get_round_robin_key(offset=0) == keys[1]
    assert rotator.get_round_robin_key(offset=1) == keys[2]
    assert rotator.get_round_robin_key(offset=2) == keys[1]

    # 4. Mark remaining keys rate limited
    rotator.mark_rate_limited(key=keys[1], retry_after=10.0)
    rotator.mark_rate_limited(key=keys[2], retry_after=25.0)

    # Now all keys are cooling down; minimum cooldown should be ~10s
    min_cd = rotator.get_min_cooldown_remaining()
    assert 0.0 < min_cd <= 10.5


@pytest.mark.asyncio
async def test_gemini_tts_preferred_key_and_success():
    """Verify GeminiTTS uses preferred_key and produces output file."""
    keys = ["AIzaSyKey1_AAA", "AIzaSyKey2_BBB"]
    tts = GeminiTTS()

    # Minimal dummy wav payload (RIFF header + data)
    dummy_wav = b"RIFF" + b"\x00" * 36 + b"data" + b"\x00" * 100
    import base64
    b64_audio = base64.b64encode(dummy_wav).decode("utf-8")

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "candidates": [{
            "content": {
                "parts": [{
                    "inlineData": {
                        "mimeType": "audio/wav",
                        "data": b64_audio,
                    }
                }]
            }
        }]
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = os.path.join(tmpdir, "test_out.mp3")
        with patch("src.infrastructure.gemini_tts._get_gemini_api_keys", return_value=keys):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = fake_response
                res = await tts.synthesize(
                    text="Halo dunia ini tes suara.",
                    voice_id="Puck",
                    preferred_key=keys[1],
                    output_path=out_file,
                )
                assert res == out_file
                assert os.path.exists(out_file)
                # Verify preferred_key was used in URL query
                assert f"key={keys[1]}" in mock_post.call_args[0][0]


@pytest.mark.asyncio
async def test_gemini_tts_429_retry_and_recovery():
    """Verify GeminiTTS marks key rate-limited on 429 and retries on next key."""
    keys = ["AIzaSyKey1_AAA", "AIzaSyKey2_BBB"]
    tts = GeminiTTS()

    import base64
    dummy_wav = b"RIFF" + b"\x00" * 36 + b"data" + b"\x00" * 100
    b64_audio = base64.b64encode(dummy_wav).decode("utf-8")

    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.text = "Resource has been exhausted (e.g. check quota)."

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {
        "candidates": [{
            "content": {
                "parts": [{
                    "inlineData": {
                        "mimeType": "audio/wav",
                        "data": b64_audio,
                    }
                }]
            }
        }]
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = os.path.join(tmpdir, "test_retry.mp3")
        with patch("src.infrastructure.gemini_tts._get_gemini_api_keys", return_value=keys):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                # 1st call fails with 429, 2nd succeeds with 200
                mock_post.side_effect = [resp_429, resp_200]
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    res = await tts.synthesize(
                        text="Tes retry rate limit.",
                        voice_id="Kore",
                        output_path=out_file,
                    )
                    assert res == out_file
                    assert os.path.exists(out_file)
                    assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_gemini_tts_synthesize_scenes_with_recovery_pass():
    """Verify synthesize_scenes completes and invokes Pass 2 recovery for any missing scene."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tts = GeminiTTS(output_dir=tmpdir)

        scenes = [
            {"narration": "Scene 1 narasi pertama"},
            {"narration": "Scene 2 narasi kedua"},
        ]

        call_count = 0

        async def fake_synthesize(text, **kwargs):
            nonlocal call_count
            call_count += 1
            out = kwargs.get("output_path")
            # Fail scene 2 on Pass 1, then succeed on Pass 2 recovery
            if "Scene 2" in text and call_count == 2:
                return None
            with open(out, "wb") as f:
                f.write(b"AUDIO_DATA")
            return out

        with patch.object(tts, "synthesize", side_effect=fake_synthesize):
            with patch.object(tts, "_probe_audio_duration", new_callable=AsyncMock, return_value=4.2):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    results = await tts.synthesize_scenes(scenes=scenes, voice_id="Puck")
                    assert len(results) == 2
                    assert results[0].get("tts_path") is not None
                    assert results[1].get("tts_path") is not None
                    assert results[0].get("audio_duration") == 4.2
                    assert results[1].get("audio_duration") == 4.2
                    # Scene 1 (1 call) + Scene 2 pass 1 (1 call) + Scene 2 pass 2 recovery (1 call) = 3 calls
                    assert call_count == 3


def test_no_deprecated_gemini_3_5_models():
    """Verify gemini-3.5 models are completely eradicated from analyzer and agentic video service."""
    from src.infrastructure.gemini_analyzer import GeminiAnalyzer
    from src.infrastructure.gemini_agentic_video_service import GeminiAgenticVideoService
    import inspect

    src_analyzer = inspect.getsource(GeminiAnalyzer)
    assert "gemini-3.5-flash" not in src_analyzer
    assert "gemini-3.5-flash-lite" not in src_analyzer

    src_service = inspect.getsource(GeminiAgenticVideoService)
    assert "gemini-3.5-flash" not in src_service
    assert "gemini-3.5-flash-lite" not in src_service


def test_strip_vocal_tags():
    """Verify strip_vocal_tags removes inline vocal and emotion tags while preserving clean spoken words."""
    from src.application.video_gen_captions import strip_vocal_tags

    raw = "<thoughtful> Kadang, seseorang pergi bukan karena sudah tidak sayang. <sigh> Mereka hanya lelah <short pause> menunggu."
    cleaned = strip_vocal_tags(raw)
    assert cleaned == "Kadang, seseorang pergi bukan karena sudah tidak sayang. Mereka hanya lelah menunggu."

    style_tag = "<style: sad> Dan yang paling menyakitkan, kita masih berharap."
    assert strip_vocal_tags(style_tag) == "Dan yang paling menyakitkan, kita masih berharap."

    bracket_style = "[style: gentle] Mungkin dia hanya menemukan seseorang yang lebih baik."
    assert strip_vocal_tags(bracket_style) == "Mungkin dia hanya menemukan seseorang yang lebih baik."

    empty_or_none = strip_vocal_tags("")
    assert empty_or_none == ""


def test_story_agent_tagged_narration_validation():
    """Verify StoryAgent._validate_and_fix cleanly separates narration and tagged_narration."""
    from src.infrastructure.story_agent import StoryAgent

    agent = StoryAgent()
    story = {
        "title": "Ketika Seseorang Pergi",
        "scenes": [
            {
                "id": 1,
                "narration": "Kadang seseorang pergi bukan karena tidak sayang.",
                "tagged_narration": "<thoughtful> Kadang seseorang pergi <short pause> bukan karena tidak sayang.",
                "visual": "A person walking away into the mist",
            },
            {
                "id": 2,
                "narration": "<sigh> Mereka hanya lelah menunggu sesuatu yang tidak pernah berubah.",
                "visual": "Rain falling against a window pane",
            },
            {"id": 3, "narration": "Dan kita masih terus berharap.", "visual": "V3"},
            {"id": 4, "narration": "Mungkin dia tidak benar melupakan.", "visual": "V4"},
            {"id": 5, "narration": "Hanya rasa nyaman yang berbeda.", "visual": "V5"},
            {"id": 6, "narration": "Jangan terus menyalahkan diri.", "visual": "V6"},
        ],
    }

    fixed = agent._validate_and_fix(story, target_duration=30)
    scenes = fixed["scenes"]

    # Scene 1: narration should remain clean, tagged_narration preserved
    assert "<" not in scenes[0]["narration"]
    assert scenes[0]["narration"] == "Kadang seseorang pergi bukan karena tidak sayang."
    assert "<thoughtful>" in scenes[0]["tagged_narration"]
    assert "<short pause>" in scenes[0]["tagged_narration"]

    # Scene 2: inline tag in narration should be extracted to tagged_narration and stripped from narration
    assert "<" not in scenes[1]["narration"]
    assert scenes[1]["narration"] == "Mereka hanya lelah menunggu sesuatu yang tidak pernah berubah."
    assert "<sigh>" in scenes[1]["tagged_narration"]


@pytest.mark.asyncio
async def test_gemini_tts_synthesize_scenes_uses_tagged_narration():
    """Verify GeminiTTS synthesize_scenes prioritizes tagged_narration over raw narration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tts = GeminiTTS(output_dir=tmpdir)
        scenes = [
            {
                "narration": "Teks bersih tanpa tag.",
                "tagged_narration": "<sad> Teks dengan tag emosi. <sigh>",
            }
        ]

        captured_texts = []

        async def fake_synthesize(text, **kwargs):
            captured_texts.append(text)
            out = kwargs.get("output_path", os.path.join(tmpdir, "out.mp3"))
            with open(out, "wb") as f:
                f.write(b"AUDIO")
            return out

        with patch.object(tts, "synthesize", side_effect=fake_synthesize):
            with patch.object(tts, "_probe_audio_duration", new_callable=AsyncMock, return_value=3.5):
                await tts.synthesize_scenes(scenes=scenes, voice_id="Kore")

        assert len(captured_texts) == 1
        # Must use tagged_narration with the emotional tags
        assert captured_texts[0] == "<sad> Teks dengan tag emosi. <sigh>"
        assert "<sad>" in captured_texts[0]


def test_story_agent_tag_script_emotions():
    """Verify StoryAgent.tag_script_emotions routes through NineRouter and returns tagged script."""
    from src.infrastructure.story_agent import StoryAgent

    agent = StoryAgent()
    mock_client = MagicMock()
    mock_client.chat.return_value = "<thoughtful> Kadang seseorang pergi. <sigh> Mereka hanya lelah."

    with patch("src.infrastructure.nine_router_client.get_nine_router_client", return_value=mock_client):
        res = agent.tag_script_emotions("Kadang seseorang pergi. Mereka hanya lelah.", mood="sad")
        assert res == "<thoughtful> Kadang seseorang pergi. <sigh> Mereka hanya lelah."
        assert mock_client.chat.called


def test_hermes_videogen_voice_style_settings():
    """Verify Hermes VideoGen settings correctly persists and retrieves voice_style."""
    from src.infrastructure.hermes_videogen_service import hermes_videogen_service

    # Update with voice_style
    updated = hermes_videogen_service.update_settings(
        user_id=9999,
        data={"voice": "Kore", "voice_style": "id_jakarta", "tts_provider": "gemini"},
    )
    assert updated.get("voice_style") == "id_jakarta"

    # Fetch settings
    fetched = hermes_videogen_service.get_settings(user_id=9999)
    assert fetched.get("voice_style") == "id_jakarta"
    assert fetched.get("voice") == "Kore"


@pytest.mark.asyncio
async def test_video_generator_parallel_alignment_step():
    """Verify _step_align_scenes_with_agentic_video executes scenes concurrently."""
    from src.application.video_generator import VideoGenerator, VideoGenJob

    vg = VideoGenerator()
    job = VideoGenJob(job_id="test_align_job", topic="Test Topic", agentic_understanding=True)

    scenes = [
        {"id": 1, "footage_path": "/tmp/fake_1.mp4", "duration": 5.0},
        {"id": 2, "footage_path": "/tmp/fake_2.mp4", "duration": 6.0},
        {"id": 3, "footage_path": "/tmp/fake_3.jpg", "duration": 5.0, "media_type": "image"},
    ]

    mock_align = AsyncMock()

    with patch("os.path.exists", return_value=True), \
         patch("src.infrastructure.gemini_agentic_video_service.GeminiAgenticVideoService.align_scene_footage", mock_align):
        await vg._step_align_scenes_with_agentic_video(job, scenes)

        # Image scene should be bypassed immediately
        assert scenes[2]["agentic_alignment"]["processing_mode"] == "static_image"
        # Video scenes should have been aligned concurrently
        assert mock_align.await_count == 2



