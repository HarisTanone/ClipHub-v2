"""Tests for Hermes Trending Service and Hermes VideoGen Auto-Post."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.infrastructure.hermes_trending_service import hermes_trending_service
from src.infrastructure.hermes_videogen_service import hermes_videogen_service
from src.application.video_generator import VideoGenStatus


@pytest.mark.asyncio
async def test_trending_service_mock_gemini():
    """Verify hermes_trending_service returns structured topics from Gemini synthesis."""
    mock_json_text = """[
      {
        "topic": "Gemini 2.5 Flash Update",
        "angle": "Tech breakdown",
        "hook": "Fitur baru ini bikin editor video ketinggalan zaman!",
        "key_points": ["Model lebih cepat", "Mampu memahami video 2 jam", "Hemat biaya"],
        "recommended_cta": "Coba sekarang di cliperhub.web.id",
        "search_keywords": ["gemini ai update", "teknologi ai 2026", "gemini omni flash"],
        "traffic_estimate": "High"
      }
    ]"""

    with patch.object(hermes_trending_service, "fetch_google_trends", new=AsyncMock(return_value=[{"title": "Gemini AI", "traffic": "50K+", "summary": "AI Update"}])):
        with patch.object(hermes_trending_service, "fetch_youtube_trending", new=AsyncMock(return_value=[{"title": "AI Video Tools", "views": "100K"}])):
            with patch.object(hermes_trending_service, "fetch_tiktok_trending", new=AsyncMock(return_value=[{"title": "Viral Tech", "views": "50K"}])):
                with patch.object(hermes_trending_service, "_call_gemini_json", new=AsyncMock(return_value=mock_json_text)):
                    topics = await hermes_trending_service.get_trending_topics(region="ID", count=3, use_cache=False)

                    assert len(topics) >= 1
                    first = topics[0]
                    assert first["topic"] == "Gemini 2.5 Flash Update"
                    assert "hook" in first
                    assert "key_points" in first
                    assert "recommended_cta" in first
                    assert "search_keywords" in first


def test_videogen_settings_and_quota():
    """Verify settings CRUD and daily video quota logic (3-5 videos/day)."""
    user_id = 99991
    from src.infrastructure.db_connection import get_dict_connection
    conn = get_dict_connection()
    conn.execute("DELETE FROM hermes_videogen_settings WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    # Initial settings for fresh user
    settings = hermes_videogen_service.get_settings(user_id)
    assert settings["daily_video_count"] == 3

    assert settings["aspect_ratio"] == "9:16"
    assert "watermark_enabled" in settings
    assert "cta_enabled" in settings

    # Update settings
    updated = hermes_videogen_service.update_settings(user_id, {
        "enabled": True,
        "daily_video_count": 5,
        "target_region": "GLOBAL",
        "cta_text": "Follow for more daily AI updates!",
    })
    assert bool(updated["enabled"]) is True
    assert updated["daily_video_count"] == 5
    assert updated["target_region"] == "GLOBAL"
    assert updated["cta_text"] == "Follow for more daily AI updates!"

    # Check quota
    can_run, reason, quota = hermes_videogen_service.can_run_today(user_id)
    assert quota["daily_limit"] == 5
    assert quota["used_today"] == 0
    assert quota["remaining_today"] == 5
    assert can_run is True


@pytest.mark.asyncio
async def test_videogen_cycle_execution():
    """Verify run_daily_cycle creates jobs and logs run."""
    user_id = 99981
    hermes_videogen_service.update_settings(user_id, {
        "enabled": True,
        "daily_video_count": 3,
        "target_region": "ID",
    })

    mock_topics = [
        {
            "topic": "Trending Topic 1",
            "angle": "Analysis",
            "hook": "Kamu belum tahu fakta ini!",
            "key_points": ["Point A", "Point B"],
            "recommended_cta": "Cek profil!",
            "search_keywords": ["topic 1 viral"],
            "traffic_estimate": "High",
            "source": "Google Trends",
        }
    ]

    mock_job = MagicMock()
    mock_job.job_id = "test-job-uuid"
    mock_job.status = VideoGenStatus.COMPLETED
    mock_job.topic = "Trending Topic 1"
    mock_job.thumbnail_url = "/path/to/thumb.jpg"
    mock_job.output_path = "/path/to/video.mp4"
    mock_job.error = None

    with patch.object(hermes_trending_service, "get_trending_topics", new=AsyncMock(return_value=mock_topics)):
        with patch("src.application.video_generator.get_video_generator") as mock_get_vg:
            mock_vg = MagicMock()
            mock_vg.create_job.return_value = mock_job
            mock_vg.get_job.return_value = mock_job
            mock_vg.run_pipeline = AsyncMock(return_value=None)
            mock_get_vg.return_value = mock_vg

            result = await hermes_videogen_service.run_daily_cycle(user_id=user_id, count_override=1, force=True)
            assert result["success"] is True
            assert len(result["runs"]) == 1

            # Verify history was recorded
            history = hermes_videogen_service.get_runs(user_id=user_id)
            assert len(history) >= 1
            assert history[0]["status"] == "completed"
            assert history[0]["topic"] == "Trending Topic 1"


def test_hermes_settings_payload_validation():
    """Verify UpdateHermesVideoGenSettingsRequest and update_settings with comma-separated string & list."""
    from src.presentation.routes.hermes_videogen import UpdateHermesVideoGenSettingsRequest

    # Exact payload from frontend error report
    frontend_payload = {
        "user_id": 5,
        "enabled": True,
        "target_region": "ID",
        "daily_video_count": 3,
        "ai_text_enabled": True,
        "aspect_ratio": "9:16",
        "cta_button_text": "FOLLOW",
        "cta_enabled": True,
        "cta_headline": "Follow for more",
        "cta_text": "Follow for more",
        "hook_enabled": True,
        "last_run_at": None,
        "last_run_date": None,
        "niche_focus": "",
        "preset_slug": "default",
        "run_time": "04:00",
        "schedule_mode": "ai",
        "subtitles_enabled": True,
        "target_account_ids": ["6a9bca8162caae1e0411e31b"],
        "target_duration": 65,
        "target_platforms": "tiktok,instagram,youtube",
        "thumbnail_enabled": True,
        "today_videos_created": 0,
        "transition_style": "dissolve",
        "trending_sources": "google,youtube,tiktok,gemini",
        "tts_model": "gemini-3.1-flash-tts-preview",
        "tts_provider": "gemini",
        "voice": "Kore",
        "watermark_enabled": False,
        "watermark_text": "",
    }

    # 1. Pydantic validation must succeed with comma-separated string
    req = UpdateHermesVideoGenSettingsRequest(**frontend_payload)
    assert req.target_platforms == "tiktok,instagram,youtube"
    assert req.trending_sources == "google,youtube,tiktok,gemini"

    # 2. Service update must succeed
    user_id = 99995
    updated = hermes_videogen_service.update_settings(user_id, req.model_dump(exclude_unset=True))
    assert updated["target_platforms"] == "tiktok,instagram,youtube"
    assert updated["trending_sources"] == "google,youtube,tiktok,gemini"
    assert updated["target_account_ids"] == ["6a9bca8162caae1e0411e31b"]
    assert updated["voice"] == "Kore"
    assert updated["tts_provider"] == "gemini"
    assert updated["tts_model"] == "gemini-3.1-flash-tts-preview"
    assert updated["run_time"] == "04:00"

    # 3. Pydantic validation and service update must also succeed with list formats
    list_payload = {
        "target_platforms": ["tiktok", "instagram"],
        "trending_sources": ["google", "youtube"],
        "daily_video_count": 4,
    }
    req2 = UpdateHermesVideoGenSettingsRequest(**list_payload)
    assert req2.target_platforms == ["tiktok", "instagram"]
    updated2 = hermes_videogen_service.update_settings(user_id, req2.model_dump(exclude_unset=True))
    assert updated2["target_platforms"] == "tiktok,instagram"
    assert updated2["trending_sources"] == "google,youtube"
    assert updated2["daily_video_count"] == 4

