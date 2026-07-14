"""Focused tests for 9router Groq Whisper -> local Whisper fallback."""
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.groq_whisper import GroqWhisperTranscriber
from src.infrastructure.groq_transcriber import GroqTranscriber
from src.infrastructure.local_transcriber import LocalTranscriber
from src.infrastructure.word_level_transcriber import WordLevelTranscriber


def run(coroutine):
    return asyncio.run(coroutine)


def test_router_audio_url_accepts_base_chat_and_full_routes():
    assert GroqWhisperTranscriber(
        base_url="http://127.0.0.1:20128/v1"
    )._transcriptions_url() == "http://127.0.0.1:20128/v1/audio/transcriptions"
    assert GroqWhisperTranscriber(
        base_url="http://127.0.0.1:20128/v1/chat/completions"
    )._transcriptions_url() == "http://127.0.0.1:20128/v1/audio/transcriptions"
    assert GroqWhisperTranscriber(
        base_url="http://127.0.0.1:20128/v1/audio/transcriptions"
    )._transcriptions_url() == "http://127.0.0.1:20128/v1/audio/transcriptions"


def test_router_request_uses_expected_auth_model_and_output_shape(tmp_path, monkeypatch):
    audio_path = tmp_path / "test.wav"
    audio_path.write_bytes(b"RIFF-test-audio")
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "task": "transcribe",
                "language": "Indonesian",
                "segments": [
                    {"start": 0, "end": 1, "text": " dua setengah"},
                    {"start": 1, "end": 2, "text": " tahun lalu"},
                ],
                "words": [
                    {"word": "dua", "start": 0.0, "end": 0.4},
                    {"word": "setengah", "start": 0.4, "end": 1.0},
                    {"word": "tahun", "start": 1.0, "end": 1.5},
                    {"word": "lalu", "start": 1.5, "end": 2.0},
                ],
            }

    class FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, headers, files):
            captured["url"] = url
            captured["headers"] = headers
            captured["fields"] = [
                (name, value[1] if value[0] is None else value[0])
                for name, value in files
            ]
            return FakeResponse()

    monkeypatch.setattr(
        "src.infrastructure.groq_whisper.httpx.Client",
        FakeClient,
    )
    transcriber = GroqWhisperTranscriber(
        base_url="http://127.0.0.1:20128/v1",
        api_key="test-router-key",
        model="groq/whisper-large-v3-turbo",
        timeout=15,
        max_retries=1,
    )

    segments = transcriber._call_groq_api(str(audio_path), "id")

    assert captured["url"] == "http://127.0.0.1:20128/v1/audio/transcriptions"
    assert captured["headers"] == {"Authorization": "Bearer test-router-key"}
    assert ("model", "groq/whisper-large-v3-turbo") in captured["fields"]
    assert ("response_format", "verbose_json") in captured["fields"]
    assert captured["fields"].count(("timestamp_granularities[]", "word")) == 1
    assert [word["word"] for segment in segments for word in segment["words"]] == [
        "dua", "setengah", "tahun", "lalu"
    ]
    assert segments == [
        {
            "start": 0.0,
            "end": 1.0,
            "text": "dua setengah",
            "words": [
                {"word": "dua", "start": 0.0, "end": 0.4},
                {"word": "setengah", "start": 0.4, "end": 1.0},
            ],
        },
        {
            "start": 1.0,
            "end": 2.0,
            "text": "tahun lalu",
            "words": [
                {"word": "tahun", "start": 1.0, "end": 1.5},
                {"word": "lalu", "start": 1.5, "end": 2.0},
            ],
        },
    ]


def test_word_level_uses_router_first(tmp_path):
    clip_path = tmp_path / "clip_01.mp4"
    audio_path = tmp_path / "clip_01_wordlevel.wav"
    clip_path.write_bytes(b"clip")
    audio_path.write_bytes(b"audio")

    transcriber = WordLevelTranscriber()
    transcriber._extract_audio = AsyncMock(return_value=str(audio_path))
    transcriber._router_whisper = type(
        "Router",
        (),
        {
            "is_available": True,
            "transcribe": AsyncMock(return_value=[{
                "start": 0,
                "end": 1,
                "text": "halo semua",
                "words": [
                    {"word": "halo", "start": 0.0, "end": 0.4},
                    {"word": "semua", "start": 0.4, "end": 1.0},
                ],
            }]),
        },
    )()
    transcriber._faster_whisper_transcribe = AsyncMock()

    result = run(transcriber._transcribe_one(1, str(clip_path), "id"))

    assert result["source"] == "groq"
    assert result["words"][1] == {"word": "semua", "start": 0.4, "end": 1.0}
    transcriber._faster_whisper_transcribe.assert_not_awaited()


def test_word_level_falls_back_when_router_has_no_word_timestamps(tmp_path):
    clip_path = tmp_path / "clip_01.mp4"
    audio_path = tmp_path / "clip_01_wordlevel.wav"
    clip_path.write_bytes(b"clip")
    audio_path.write_bytes(b"audio")

    transcriber = WordLevelTranscriber()
    transcriber._extract_audio = AsyncMock(return_value=str(audio_path))
    transcriber._router_whisper = type(
        "Router",
        (),
        {
            "is_available": True,
            "transcribe": AsyncMock(return_value=[{
                "start": 0,
                "end": 1,
                "text": "halo semua",
                "words": [],
            }]),
        },
    )()
    local_words = [{"word": "halo", "start": 0.0, "end": 0.5}]
    transcriber._faster_whisper_transcribe = AsyncMock(return_value=local_words)

    result = run(transcriber._transcribe_one(1, str(clip_path), "id"))

    assert result == {"source": "faster_whisper", "words": local_words}
    transcriber._faster_whisper_transcribe.assert_awaited_once()


def test_full_file_transcriber_falls_back_to_local_on_router_error(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")

    local_segments = [{
        "start": 0,
        "end": 1,
        "text": "hasil lokal",
        "words": [{"word": "hasil", "start": 0, "end": 0.5}],
    }]
    local = type(
        "Local",
        (),
        {"transcribe_clip": AsyncMock(return_value=local_segments)},
    )()
    router = type(
        "Router",
        (),
        {
            "is_available": True,
            "transcribe": AsyncMock(return_value=[]),
        },
    )()
    transcriber = LocalTranscriber(local)
    transcriber._groq = router
    transcriber._extract_audio = AsyncMock(
        side_effect=lambda _input, output: Path(output).write_bytes(b"audio")
    )

    transcript, raw_segments = run(transcriber.transcribe(str(video_path), 1.0))

    assert transcript.source == "faster_whisper_local"
    assert transcript.segments[0].text == "hasil lokal"
    assert raw_segments == local_segments
    local.transcribe_clip.assert_awaited_once()


def test_youtube_whisper_fallback_downloads_once_and_reuses_audio(tmp_path):
    raw_local = [{"start": 0, "end": 1, "text": "fallback lokal", "words": []}]
    local = type(
        "Local",
        (),
        {"transcribe_clip": AsyncMock(return_value=raw_local)},
    )()
    router = type(
        "Router",
        (),
        {"is_available": True, "transcribe": AsyncMock(return_value=[])},
    )()
    transcriber = GroqTranscriber()
    transcriber._router_whisper = router

    async def fake_download(_url, output_dir):
        audio_path = Path(output_dir) / "audio.mp3"
        audio_path.write_bytes(b"audio")
        return str(audio_path)

    transcriber._download_audio = AsyncMock(side_effect=fake_download)

    with patch(
        "src.infrastructure.whisper_local.WhisperLocal",
        return_value=local,
    ):
        result = run(transcriber._transcribe_via_whisper_fallbacks(
            "https://youtube.example/video",
            1.0,
            "video-id",
        ))

    assert result.source == "local_whisper"
    assert result.segments[0].text == "fallback lokal"
    transcriber._download_audio.assert_awaited_once()
    router.transcribe.assert_awaited_once()
    local.transcribe_clip.assert_awaited_once()
