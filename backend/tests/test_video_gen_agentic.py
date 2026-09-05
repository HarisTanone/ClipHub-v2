"""Tests for Language Detection, Multi-Platform Footage Search, and Gemini Agentic Video Understanding."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.video_generator import VideoGenerator, VideoGenJob, VideoGenStatus
from src.infrastructure.gemini_agentic_video_service import GeminiAgenticVideoService
from src.infrastructure.language_detector import detect_language, is_indonesian
from src.infrastructure.social_footage_searcher import SocialFootageSearcher
from src.infrastructure.story_agent import StoryAgent


def test_language_detection_indonesian():
    assert detect_language("Sejarah Kota Salatiga yang Menakjubkan") == "id"
    assert is_indonesian("Wisata tersembunyi di lereng Gunung Merbabu") is True
    assert is_indonesian("Kuliner khas nusantara yang bikin nagih") is True
    assert is_indonesian("10 fakta unik tentang hewan di Indonesia") is True


def test_language_detection_english():
    assert detect_language("The Untold History of Ancient Rome") == "en"
    assert is_indonesian("Top 10 incredible scientific discoveries in deep space") is False
    assert detect_language("How to build high-performance distributed systems") == "en"


def test_video_generator_create_job_detects_language():
    generator = VideoGenerator()
    # Indonesian topic
    job_id = generator.create_job(topic="5 Tempat Wisata Paling Dingin di Jawa Tengah")
    assert job_id.language == "id"

    # English topic
    job_en = generator.create_job(topic="The Hidden Architecture of New York City")
    assert job_en.language == "en"

    # Explicit override
    job_override = generator.create_job(topic="A neutral topic", language="id")
    assert job_override.language == "id"


@pytest.mark.asyncio
async def test_story_agent_uses_language_directive(monkeypatch):
    agent = StoryAgent()
    mock_llm = MagicMock(return_value=json.dumps({
        "title": "Salatiga Indah",
        "hook": "Kota tertua?",
        "scenes": [
            {"id": 1, "narration": "Salatiga adalah salah satu kota tertua di Indonesia.", "visual": "Pemandangan kota sejuk", "search_queries": ["Salatiga drone"], "duration_estimate": 20.0},
            {"id": 2, "narration": "Dikelilingi gunung Merbabu dengan udara pegunungan.", "visual": "Gunung Merbabu", "search_queries": ["Merbabu Salatiga"], "duration_estimate": 20.0},
            {"id": 3, "narration": "Kuliner ronde dan enting-enting gepuk yang legendaris.", "visual": "Kuliner khas Salatiga", "search_queries": ["Kuliner Salatiga"], "duration_estimate": 25.0},
        ]
    }))
    monkeypatch.setattr(agent, "_call_llm", mock_llm)

    story = await agent.generate_story(
        topic="Pesona Kota Salatiga yang Asri",
        language="id",
        target_duration=65,
    )

    assert story["title"] == "Salatiga Indah"
    call_args = mock_llm.call_args[0][0]
    assert "BAHASA INDONESIA" in call_args


@pytest.mark.asyncio
async def test_social_footage_searcher_routes_platforms(monkeypatch):
    searcher = SocialFootageSearcher()

    mock_yt = MagicMock()
    mock_yt.search = AsyncMock(return_value=MagicMock(results=[]))
    mock_yt.search_pexels = AsyncMock(return_value=[{
        "video_id": "pexels_101",
        "title": "Pexels Stock Drone",
        "url": "https://images.pexels.com/video-files/101.mp4",
        "platform": "pexels",
        "duration_seconds": 15,
    }])
    mock_yt.search_pixabay = AsyncMock(return_value=[])
    mock_yt.search_pexels_photos = AsyncMock(return_value=[])
    mock_yt.search_pixabay_photos = AsyncMock(return_value=[])
    mock_yt.search_wikimedia_photos = AsyncMock(return_value=[])
    searcher._yt_search = mock_yt

    # Mock ytdlp platform search
    mock_ytdlp = AsyncMock(return_value=[
        {
            "video_id": "tiktok_202",
            "title": "TikTok Viral Salatiga",
            "url": "https://www.tiktok.com/@user/video/202",
            "platform": "tiktok",
            "duration_seconds": 25,
        }
    ])
    monkeypatch.setattr(searcher, "search_ytdlp_platform", mock_ytdlp)

    scene = {
        "id": 1,
        "narration": "Salatiga kota yang sejuk dan tenang di Jawa Tengah.",
        "visual": "Drone shot suasana kota Salatiga",
        "search_queries": ["Salatiga drone sejuk", "green mountain city drone"],
    }

    candidates = await searcher.search_for_single_scene(scene, is_indonesian=True, results_per_platform=2)
    assert len(candidates) >= 2
    platforms = {c.get("platform") for c in candidates}
    assert "tiktok" in platforms or "pexels" in platforms


def test_gemini_agentic_video_service_parse_json():
    service = GeminiAgenticVideoService()
    raw_json = """
    ```json
    {
      "is_relevant": true,
      "alignment_score": 9.4,
      "best_start_timestamp": 5.2,
      "best_end_timestamp": 12.0,
      "visual_summary": "Drone flyover of Salatiga highland valley",
      "reasoning": "Perfect visual match with the narration about mountain breeze"
    }
    ```
    """
    parsed = service._parse_json_response(raw_json, target_duration=6.5)
    assert parsed["is_relevant"] is True
    assert parsed["alignment_score"] == 9.4
    assert parsed["best_start_timestamp"] == 5.2
    assert parsed["best_end_timestamp"] == 12.0
    assert "Salatiga" in parsed["visual_summary"]


@pytest.mark.asyncio
async def test_gemini_agentic_alignment_sets_scene_timestamp(tmp_path, monkeypatch):
    service = GeminiAgenticVideoService()
    video_file = tmp_path / "sample_clip.mp4"
    video_file.write_bytes(b"dummy mp4 video bytes")

    mock_analysis = {
        "is_relevant": True,
        "alignment_score": 9.0,
        "best_start_timestamp": 3.8,
        "best_end_timestamp": 10.3,
        "visual_summary": "Highland city view",
        "reasoning": "Aligned",
    }
    monkeypatch.setattr(
        service,
        "analyze_footage_alignment",
        AsyncMock(return_value=mock_analysis),
    )

    scene = {
        "id": 1,
        "narration": "Menikmati udara sejuk pegunungan.",
        "visual": "Pemandangan lereng gunung",
        "duration_estimate": 6.5,
    }

    updated_scene = await service.align_scene_footage(scene, str(video_file), topic="Wisata Salatiga")
    assert updated_scene["start_timestamp"] == 3.8
    assert updated_scene["agentic_alignment"]["alignment_score"] == 9.0


def test_timeline_assembly_preserves_agentic_start_timestamp():
    generator = VideoGenerator()
    scenes = [
        {
            "id": 1,
            "narration": "Opening scene",
            "tts_duration": 5.5,
            "tts_path": "/tmp/audio1.mp3",
            "footage_path": "/tmp/foot1.mp4",
            "start_timestamp": 4.2,  # Set by Agentic Video Understanding
        },
        {
            "id": 2,
            "narration": "Second scene",
            "tts_duration": 6.0,
            "tts_path": "/tmp/audio2.mp3",
            "footage_path": "/tmp/foot2.mp4",
            "start_timestamp": 11.5, # Set by Agentic Video Understanding
        },
    ]

    timeline = generator._step_assemble_timeline(scenes)
    assert len(timeline) == 2
    assert timeline[0]["start_timestamp"] == 4.2
    assert timeline[0]["duration"] == 5.5
    assert timeline[1]["start_timestamp"] == 11.5
    assert timeline[1]["duration"] == 6.0
