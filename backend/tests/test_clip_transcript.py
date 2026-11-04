import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from fastapi.responses import Response

from src.presentation.routes.jobs import get_clip_transcript
from src.domain.entities import Job, JobStatus


@pytest.mark.asyncio
async def test_get_clip_transcript_job_not_found():
    service = MagicMock()
    service.get_job = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await get_clip_transcript(job_id="job_nonexistent", clip_rank=1, service=service)
    assert exc_info.value.status_code == 404
    assert "Job not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_clip_transcript_clip_not_found():
    service = MagicMock()
    mock_job = MagicMock()
    mock_job.job_id = "job_123"
    mock_job.clips_data = {"clips": [{"rank": 1}]}
    service.get_job = AsyncMock(return_value=mock_job)

    with pytest.raises(HTTPException) as exc_info:
        await get_clip_transcript(job_id="job_123", clip_rank=2, service=service)
    assert exc_info.value.status_code == 404
    assert "Clip #2 not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_clip_transcript_json_success():
    service = MagicMock()
    mock_job = MagicMock()
    mock_job.job_id = "job_test"
    mock_job.video_title = "Podcast Episode 10"
    mock_job.clips_data = {
        "clips": [
            {
                "rank": 3,
                "start": 10.0,
                "end": 25.5,
                "duration": 15.5,
                "hook": "Ini rahasia suksesnya",
                "words": [
                    {"word": "Ini", "start": 10.0, "end": 10.4},
                    {"word": "rahasia", "start": 10.5, "end": 11.2},
                    {"word": "suksesnya", "start": 11.3, "end": 12.0},
                ],
            }
        ]
    }
    service.get_job = AsyncMock(return_value=mock_job)

    result = await get_clip_transcript(job_id="job_test", clip_rank=3, download=False, service=service)
    assert result["success"] is True
    data = result["data"]
    assert data["job_id"] == "job_test"
    assert data["clip_rank"] == 3
    assert data["video_title"] == "Podcast Episode 10"
    assert data["start"] == 10.0
    assert data["end"] == 25.5
    assert data["duration"] == 15.5
    assert data["hook"] == "Ini rahasia suksesnya"
    assert data["full_text"] == "Ini rahasia suksesnya"
    assert data["word_count"] == 3
    assert len(data["words"]) == 3


@pytest.mark.asyncio
async def test_get_clip_transcript_download_attachment():
    service = MagicMock()
    mock_job = MagicMock()
    mock_job.job_id = "job_test"
    mock_job.video_title = "Podcast Episode 10"
    mock_job.clips_data = {
        "clips": [
            {
                "rank": 3,
                "start": 10.0,
                "end": 25.5,
                "duration": 15.5,
                "hook": "Ini rahasia suksesnya",
                "words": [
                    {"word": "Halo", "start": 10.0, "end": 10.5},
                    {"word": "dunia", "start": 10.6, "end": 11.0},
                ],
            }
        ]
    }
    service.get_job = AsyncMock(return_value=mock_job)

    response = await get_clip_transcript(job_id="job_test", clip_rank=3, download=True, service=service)
    assert isinstance(response, Response)
    assert response.media_type == "application/json; charset=utf-8"
    assert 'attachment; filename="transcript_job_test_clip_3.json"' in response.headers["Content-Disposition"]
    assert b'"Halo"' in response.body
    assert b'"dunia"' in response.body

