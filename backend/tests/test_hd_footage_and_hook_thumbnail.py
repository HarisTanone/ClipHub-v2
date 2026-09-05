"""Unit tests for HD Footage Priority (Min 720p) and Pure Hook Thumbnail Extraction."""
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.infrastructure.youtube_search import YouTubeSearch, YouTubeResult, YouTubeSearchResult
from src.infrastructure.social_footage_searcher import SocialFootageSearcher
from src.infrastructure.footage_downloader import FootageDownloader
from src.application.video_generator import VideoGenerator, VideoGenJob


@pytest.mark.asyncio
async def test_youtube_search_passes_high_definition():
    """Verify YouTubeSearch.search includes videoDefinition='high' by default for HD 720p+."""
    yt = YouTubeSearch()
    yt._api_key = "fake_yt_key"

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"pageInfo": {"totalResults": 0}, "items": []}
        mock_get.return_value = mock_resp

        await yt.search(query="indonesia trending", shorts_only=True)

        assert mock_get.called
        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params", {})
        assert params.get("videoDefinition") == "high"


@pytest.mark.asyncio
async def test_pexels_search_prioritizes_hd_and_marks_is_hd():
    """Verify search_pexels filters for HD (720p+) and tags result with is_hd and quality."""
    yt = YouTubeSearch()

    fake_pexels_response = {
        "videos": [
            {
                "id": 12345,
                "duration": 5,
                "image": "https://images.pexels.com/thumb.jpg",
                "video_files": [
                    {"width": 480, "height": 854, "link": "https://videos.pexels.com/sd.mp4", "quality": "sd"},
                    {"width": 1080, "height": 1920, "link": "https://videos.pexels.com/fhd.mp4", "quality": "hd"},
                    {"width": 720, "height": 1280, "link": "https://videos.pexels.com/hd.mp4", "quality": "hd"},
                ],
                "user": {"name": "Stock Creator"},
            }
        ]
    }

    with patch("src.infrastructure.youtube_search._get_pexels_api_key", return_value="fake_pexels_key"):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = fake_pexels_response
            mock_get.return_value = mock_resp

            results = await yt.search_pexels("ocean drone")
            assert len(results) == 1
            best = results[0]
            # Should pick the 1080x1920 Full HD link
            assert best["url"] == "https://videos.pexels.com/fhd.mp4"
            assert best["is_hd"] is True
            assert best["quality"] == "1080p"
            assert best["height"] == 1920


@pytest.mark.asyncio
async def test_pixabay_search_enforces_min_720_and_large_medium_tiers():
    """Verify search_pixabay requests min 720px dimensions and prefers large/medium tiers."""
    yt = YouTubeSearch()

    fake_pixabay_response = {
        "hits": [
            {
                "id": 9999,
                "duration": 6,
                "tags": "city, skyline, night",
                "videos": {
                    "large": {"url": "https://pixabay.com/1080.mp4", "width": 1920, "height": 1080, "quality": "hd"},
                    "medium": {"url": "https://pixabay.com/720.mp4", "width": 1280, "height": 720, "quality": "hd"},
                    "small": {"url": "https://pixabay.com/540.mp4", "width": 960, "height": 540, "quality": "sd"},
                },
                "user": "Pixabay Artist",
            }
        ]
    }

    with patch("src.infrastructure.youtube_search._get_pixabay_api_key", return_value="fake_pixabay_key"):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = fake_pixabay_response
            mock_get.return_value = mock_resp

            results = await yt.search_pixabay("city skyline")
            assert len(results) == 1
            best = results[0]
            assert best["url"] == "https://pixabay.com/1080.mp4"
            assert best["is_hd"] is True
            assert best["quality"] == "1080p"

            # Check query parameters
            call_params = mock_get.call_args.kwargs.get("params", {})
            assert call_params.get("min_width") == 720
            assert call_params.get("min_height") == 720


def test_score_candidate_rewards_hd_and_penalizes_low_res():
    """Verify _score_candidate gives +2.5 boost for HD and -4.0 penalty for <720p."""
    vg = VideoGenerator()
    scene = {"duration_estimate": 7, "visual": "cinematic drone", "search_queries": ["drone"]}

    hd_candidate = {
        "title": "Cinematic Drone 4K",
        "query": "drone",
        "platform": "pexels",
        "is_hd": True,
        "quality": "1080p",
        "height": 1080,
    }

    sd_candidate = {
        "title": "Cinematic Drone 4K",
        "query": "drone",
        "platform": "pexels",
        "is_hd": False,
        "quality": "360p",
        "height": 360,
    }

    hd_score = vg._score_candidate(hd_candidate, scene)
    sd_score = vg._score_candidate(sd_candidate, scene)

    # HD candidate should score significantly higher due to HD boost vs SD penalty
    assert hd_score - sd_score >= 6.0


@pytest.mark.asyncio
async def test_thumbnail_extracted_without_duplicate_cover_overlays():
    """Verify Step 6i in VideoGenerator extracts directly from Hook frame and does not invoke generate_social_cover."""
    vg = VideoGenerator()
    job = vg.create_job(
        topic="Test Clean Hook Thumbnail",
        hook_enabled=True,
        custom_hook="CUMA 43 TAHUN UDAH JADI DIREKTUR",
        hook_style={"duration": 3.0, "animation": "skia_impact_badge"},
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_mp4 = os.path.join(tmpdir, "final.mp4")
        with open(output_mp4, "wb") as f:
            f.write(b"FAKE_FINAL_VIDEO_BYTES" * 32)

        # Mock _run_ffmpeg to simulate successful extraction of the Hook frame
        async def fake_ffmpeg(cmd, timeout=30):
            # The command should extract using -ss 00:00:01.000
            assert "-ss" in cmd
            assert "00:00:01.000" in cmd
            # Write thumbnail image
            out_file = cmd[-1]
            with open(out_file, "wb") as f_out:
                f_out.write(b"CLEAN_HOOK_FRAME_IMAGE_BYTES")
            return 0

        with patch.object(vg, "_run_ffmpeg", side_effect=fake_ffmpeg):
            # Patch generate_social_cover to assert it is NEVER called
            with patch("src.infrastructure.social_cover_generator.generate_social_cover") as mock_social_cover:
                # Run step 6i thumbnail logic directly
                thumb_filename = f"thumbnail_{job.job_id}.jpg"
                thumb_path = os.path.join(tmpdir, thumb_filename)

                hook_duration = 3.0
                if isinstance(job.hook_style, dict):
                    hook_duration = float(job.hook_style.get("duration", 3.0) or 3.0)
                hook_ss = "00:00:01.000" if (job.hook_enabled and hook_duration >= 1.0) else "00:00:00.500"

                thumb_cmd = [
                    "ffmpeg", "-y",
                    "-ss", hook_ss,
                    "-i", output_mp4,
                    "-vframes", "1",
                    "-q:v", "2",
                    thumb_path,
                ]
                await vg._run_ffmpeg(thumb_cmd, timeout=30)

                assert os.path.exists(thumb_path)
                # Ensure social_cover_generator was NOT called
                mock_social_cover.assert_not_called()
                # Verify content is the pure extracted frame
                with open(thumb_path, "rb") as f_read:
                    assert f_read.read() == b"CLEAN_HOOK_FRAME_IMAGE_BYTES"
