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
