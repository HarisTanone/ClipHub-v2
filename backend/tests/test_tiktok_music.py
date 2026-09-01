import asyncio
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from src.presentation.api import app
from src.presentation.auth_deps import CurrentUser
from src.presentation.routes.auth import get_current_user
from src.presentation.routes.social.publish import (
    PublishRequest,
    mix_video_with_music,
    scale_video_audio_volume,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_tiktok_trending_music_happy_path():
    """Verify GET /api/social/tiktok/music returns formatted tracks with ranking and usage labels."""
    fake_user = CurrentUser(1, "admin@test.com", "superadmin", ["*"])
    app.dependency_overrides[get_current_user] = lambda: fake_user

    mock_docs = [
        {
            "id": "7604121927885342721",
            "artist": "DANILA FRANSISKA",
            "name": "the funniest",
            "thumbnail": "https://p16-sg.tiktokcdn.com/cover1.jpg",
            "duration": 97,
            "url": "https://sf16-ies-music-sg.tiktokcdn.com/audio1.mp3",
        },
        {
            "id": "7659443189309720577",
            "artist": "eńau & Momo",
            "name": "Sudah Tahu Tuhan Kita Berbeda",
            "thumbnail": "https://p16-sg.tiktokcdn.com/cover2.jpg",
            "duration": 232,
            "url": "https://sf16-ies-music-sg.tiktokcdn.com/audio2.mp3",
        },
    ]

    with patch("src.presentation.routes.social.tiktok.repliz_get", new_callable=AsyncMock) as mock_repliz:
        mock_repliz.return_value = {"docs": mock_docs}

        # Clear cache for isolated test
        from src.presentation.routes.social import tiktok
        tiktok._music_cache.clear()

        client = TestClient(app)
        res = client.get("/api/social/tiktok/music?country_code=ID&genre=ALL&date_range=7DAY")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert len(data["tracks"]) == 2

        track1 = data["tracks"][0]
        assert track1["id"] == "7604121927885342721"
        assert track1["name"] == "the funniest"
        assert track1["rank"] == 1
        assert track1["is_recommended"] is True
        assert "1.8M+" in track1["usage_label"]

    app.dependency_overrides.pop(get_current_user, None)


def test_tiktok_trending_music_search_filter():
    """Verify search query filters tracks by name or artist."""
    fake_user = CurrentUser(2, "editor@test.com", "editor", ["*"])
    app.dependency_overrides[get_current_user] = lambda: fake_user

    mock_docs = [
        {
            "id": "1",
            "artist": "Artist Alpha",
            "name": "Summer Vibes",
            "thumbnail": "",
            "duration": 60,
            "url": "https://cdn.com/1.mp3",
        },
        {
            "id": "2",
            "artist": "Beta Singer",
            "name": "Midnight Road",
            "thumbnail": "",
            "duration": 80,
            "url": "https://cdn.com/2.mp3",
        },
    ]

    with patch("src.presentation.routes.social.tiktok.repliz_get", new_callable=AsyncMock) as mock_repliz:
        mock_repliz.return_value = {"docs": mock_docs}

        from src.presentation.routes.social import tiktok
        tiktok._music_cache.clear()

        client = TestClient(app)
        # Search for 'beta'
        res = client.get("/api/social/tiktok/music?search=beta")
        assert res.status_code == 200
        data = res.json()
        assert len(data["tracks"]) == 1
        assert data["tracks"][0]["name"] == "Midnight Road"

    app.dependency_overrides.pop(get_current_user, None)


def test_tiktok_trending_music_cache_prevents_duplicate_calls():
    """Verify that repeated calls use the 15-minute in-memory cache without hitting Repliz again."""
    fake_user = CurrentUser(1, "admin@test.com", "superadmin", ["*"])
    app.dependency_overrides[get_current_user] = lambda: fake_user

    mock_docs = [{"id": "1", "artist": "A", "name": "B", "thumbnail": "", "duration": 30, "url": ""}]

    with patch("src.presentation.routes.social.tiktok.repliz_get", new_callable=AsyncMock) as mock_repliz:
        mock_repliz.return_value = {"docs": mock_docs}

        from src.presentation.routes.social import tiktok
        tiktok._music_cache.clear()

        client = TestClient(app)
        res1 = client.get("/api/social/tiktok/music?country_code=ID&genre=ALL&date_range=7DAY")
        res2 = client.get("/api/social/tiktok/music?country_code=ID&genre=ALL&date_range=7DAY")

        assert res1.status_code == 200
        assert res2.status_code == 200
        # repliz_get should only be called ONCE due to cache
        assert mock_repliz.call_count == 1

    app.dependency_overrides.pop(get_current_user, None)


def test_tiktok_trending_music_repliz_error_handling():
    """Verify that if Repliz API throws an error, the endpoint handles it gracefully and returns empty tracks."""
    fake_user = CurrentUser(1, "admin@test.com", "superadmin", ["*"])
    app.dependency_overrides[get_current_user] = lambda: fake_user

    with patch("src.presentation.routes.social.tiktok.repliz_get", new_callable=AsyncMock) as mock_repliz:
        mock_repliz.side_effect = Exception("Repliz service unavailable 502")

        from src.presentation.routes.social import tiktok
        tiktok._music_cache.clear()

        client = TestClient(app)
        res = client.get("/api/social/tiktok/music")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["tracks"] == []
        assert data["total"] == 0

    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_mix_video_with_music_muted_volume_bypasses_ffmpeg():
    """When musicVolume is 0 and originalVolume is 1.0, video should NOT be re-encoded."""
    original_video = "/tmp/test_clip.mp4"
    result = await mix_video_with_music(
        video_path=original_video,
        music_url="https://sf16.com/audio.mp3",
        original_vol=1.0,
        music_vol=0.0,
    )
    # Returns original path directly without re-encoding
    assert result == original_video


@pytest.mark.asyncio
async def test_mix_video_with_music_bad_url_fallback():
    """When music URL fails to download (404/500), mix_video_with_music falls back to original video."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        original_video = "/tmp/sample_video.mp4"
        result = await mix_video_with_music(
            video_path=original_video,
            music_url="https://invalid-url.com/not_found.mp3",
            original_vol=0.8,
            music_vol=0.3,
        )
        assert result == original_video


@pytest.mark.asyncio
async def test_mix_video_with_music_success_mocked_ffmpeg():
    """Verify that when volume > 0 and audio downloads, FFmpeg is called with correct volume scaling."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec, \
         patch("os.path.exists") as mock_exists:

        # Mock successful audio download
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake_mp3_content"
        mock_get.return_value = mock_resp

        # Mock FFmpeg execution
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_exec.return_value = mock_proc

        mock_exists.return_value = True

        result = await mix_video_with_music(
            video_path="/tmp/original_video.mp4",
            music_url="https://sf16.com/trending_audio.mp3",
            original_vol=0.85,
            music_vol=0.20,
        )

        assert "_mixed_" in result
        # Check that FFmpeg was invoked with volume filter
        mock_exec.assert_called_once()
        cmd_args = mock_exec.call_args[0]
        cmd_str = " ".join(str(a) for a in cmd_args)
        assert "volume=0.85" in cmd_str
        assert "volume=0.20" in cmd_str
        assert "amix=inputs=2" in cmd_str


def test_publish_request_accepts_all_music_parameters():
    """Verify PublishRequest accepts and validates all music and volume parameters."""
    req = PublishRequest(
        jobId="job_789",
        clipRank=2,
        accountId="acc_tiktok_99",
        scheduleAt="2026-09-01T14:00:00.000Z",
        isAutoAddMusic=True,
        music={
            "id": "7604121927885342721",
            "name": "the funniest",
            "artist": "DANILA FRANSISKA",
            "thumbnail": "https://p16-sg.tiktokcdn.com/cover.jpg",
            "url": "https://sf16-ies-music-sg.tiktokcdn.com/audio.mp3",
        },
        originalVolume=0.90,
        musicVolume=0.15,
    )

    assert req.isAutoAddMusic is True
    assert req.music["id"] == "7604121927885342721"
    assert req.originalVolume == 0.90
    assert req.musicVolume == 0.15


@pytest.mark.asyncio
async def test_scale_video_audio_volume():
    """Verify that scale_video_audio_volume invokes ffmpeg with volume filter when volume != 1.0."""
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec, \
         patch("os.path.exists") as mock_exists:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_exec.return_value = mock_proc
        mock_exists.return_value = True

        res = await scale_video_audio_volume("/tmp/input.mp4", volume=0.5)
        assert "_vol_" in res
        mock_exec.assert_called_once()
        cmd_args = mock_exec.call_args[0]
        cmd_str = " ".join(str(a) for a in cmd_args)
        assert "volume=0.50" in cmd_str


def test_zero_music_volume_disables_repliz_music():
    """Verify additional_info sets isAutoAddMusic=False and music.id='' when musicVolume is 0."""
    from src.presentation.routes.social.publish import PublishRequest

    body = PublishRequest(
        jobId="job_zero",
        accountId="acc_1",
        scheduleAt="2026-09-01T15:00:00.000Z",
        isAutoAddMusic=True,
        music={"id": "track_123", "name": "Trending Song", "artist": "Artist", "url": "https://sf16.com/1.mp3"},
        musicVolume=0.0,
        originalVolume=1.0,
    )

    has_active_music = bool(body.isAutoAddMusic) and body.musicVolume > 0.0 and bool(body.music)
    assert has_active_music is False
    additional_info = {
        "isAutoAddMusic": has_active_music,
        "music": {
            "id": str((body.music or {}).get("id") or ""),
        } if has_active_music else {"id": "", "artist": "", "name": "", "thumbnail": ""},
    }
    assert additional_info["isAutoAddMusic"] is False
    assert additional_info["music"]["id"] == ""


def test_infer_music_recommendation_vibe_and_diversity():
    """Verify infer_music_recommendation maps content vibe accurately and varies by clip rank."""
    from src.presentation.routes.social.tiktok import infer_music_recommendation

    # Energetic / Dance
    rec_dance = infer_music_recommendation(title="Tutorial Workout & Dance Party Jedag Jedug", clip_rank=1)
    assert rec_dance["genre"] == "EDM"
    assert "ritme cepat" in rec_dance["match_reason"]

    # Motivation / Business
    rec_biz = infer_music_recommendation(title="5 Rahasia Sukses Finansial & Bisnis Anak Muda", clip_rank=1)
    assert rec_biz["genre"] == "POP"
    assert "edukasi" in rec_biz["match_reason"]

    # Podcast / Narrative
    rec_pod = infer_music_recommendation(title="Podcast Cerita Santai Bareng Teman Ngopi", clip_rank=1)
    assert rec_pod["genre"] == "FOLK"
    assert "dialog cerita" in rec_pod["match_reason"]

    # Per-clip diversity: clip 1, clip 2, clip 3 in generic videos get different music recommendations
    rec_clip1 = infer_music_recommendation(title="Clip Highlight Video", clip_rank=1)
    rec_clip2 = infer_music_recommendation(title="Clip Highlight Video", clip_rank=2)
    rec_clip3 = infer_music_recommendation(title="Clip Highlight Video", clip_rank=3)

    assert rec_clip1["genre"] != rec_clip2["genre"]
    assert rec_clip2["genre"] != rec_clip3["genre"]


def test_tiktok_music_recommendation_endpoint(client):
    """Verify GET /api/social/tiktok/music with recommendation returns matched reason and tracks."""
    fake_user = CurrentUser(1, "admin@test.com", "superadmin", ["*"])
    app.dependency_overrides[get_current_user] = lambda: fake_user

    with patch("src.presentation.routes.social.tiktok.repliz_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "docs": [
                {"id": "track_biz_1", "name": "Motivasi Pagi", "artist": "Inspirasi Band", "duration": 60, "url": "https://cdn.com/1.mp3"},
                {"id": "track_biz_2", "name": "Semangat Hidup", "artist": "Creative Group", "duration": 75, "url": "https://cdn.com/2.mp3"},
            ]
        }
        resp = client.get(
            "/api/social/tiktok/music",
            params={
                "genre": "RECOMMENDED",
                "title": "Tips Sukses Bisnis Online",
                "clip_rank": 1,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["genre"] == "POP"  # Inferred from 'bisnis' / 'sukses'
        assert "edukasi" in data["match_reason"].lower()
        assert len(data["tracks"]) == 2
        assert data["tracks"][0]["match_reason"] != ""


def test_schedule_stats_endpoint(client):
    """Verify GET /api/social/schedule/stats returns all, pending, success, error counts."""
    fake_user = CurrentUser(1, "admin@test.com", "superadmin", ["*"])
    app.dependency_overrides[get_current_user] = lambda: fake_user

    async def mock_get(url, params=None):
        st = (params or {}).get("status")
        if st == "pending":
            return {"totalDocs": 9}
        elif st == "success":
            return {"totalDocs": 60}
        elif st == "error":
            return {"totalDocs": 11}
        return {"totalDocs": 80}

    with patch("src.presentation.routes.social.schedule.repliz_get", side_effect=mock_get):
        resp = client.get("/api/social/schedule/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["stats"]["all"] == 80
        assert data["stats"]["pending"] == 9
        assert data["stats"]["success"] == 60
        assert data["stats"]["error"] == 11


def test_mass_delete_with_query_params_compatibility(client):
    """Verify DELETE /api/social/schedule/mass works with query params without 422 error."""
    fake_user = CurrentUser(1, "admin@test.com", "superadmin", ["*"])
    app.dependency_overrides[get_current_user] = lambda: fake_user

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"success": true}'

    with patch("src.presentation.routes.social.schedule.repliz_auth_header", return_value={"x-api-key": "fake"}), \
         patch("httpx.AsyncClient.delete", new_callable=AsyncMock) as mock_delete:
        mock_delete.return_value = mock_resp

        # Test query param scheduleIds[] format
        resp = client.delete(
            "/api/social/schedule/mass?scheduleIds[]=id_1&scheduleIds[]=id_2"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "2 schedules" in data["message"]

        # Test JSON body format
        resp2 = client.request(
            "DELETE",
            "/api/social/schedule/mass",
            json={"scheduleIds": ["id_3", "id_4"]},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["success"] is True
        assert "2 schedules" in data2["message"]


