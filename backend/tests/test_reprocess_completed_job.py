import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from src.domain.entities import Job, JobStatus
from src.presentation.routes.jobs import reprocess_job
from src.presentation.auth_deps import CurrentUser


@pytest.mark.asyncio
async def test_reprocess_completed_job_allowed():
    user = CurrentUser(1, "user@test.com", "user", [])

    completed_job = Job(
        job_id="job_d6d022584c65",
        youtube_url="https://www.youtube.com/watch?v=example",
        status=JobStatus.COMPLETED,
        user_id=1,
        clips_data={"source": {"type": "youtube"}},
    )

    fresh_job = Job(
        job_id="job_fresh999",
        youtube_url="https://www.youtube.com/watch?v=example",
        status=JobStatus.VALIDATING,
        user_id=1,
    )

    mock_service = MagicMock()
    mock_service.get_job = AsyncMock(return_value=completed_job)
    mock_service.create_job = AsyncMock(return_value=(fresh_job, None))

    response = await reprocess_job(
        job_id="job_d6d022584c65",
        service=mock_service,
        user=user,
    )

    assert response.job_id == "job_fresh999"
    assert response.status == "validating"
    mock_service.create_job.assert_called_once()
    _, kwargs = mock_service.create_job.call_args
    assert kwargs.get("force_reprocess") is True


@pytest.mark.asyncio
async def test_reprocess_failed_and_timeout_job_allowed():
    user = CurrentUser(1, "user@test.com", "user", [])
    fresh_job = Job(job_id="job_fresh888", youtube_url="https://youtube.com", status=JobStatus.VALIDATING, user_id=1)

    for allowed_status in [JobStatus.FAILED, JobStatus.TIMEOUT]:
        job = Job(
            job_id=f"job_{allowed_status.value}",
            youtube_url="https://youtube.com",
            status=allowed_status,
            user_id=1,
        )
        mock_service = MagicMock()
        mock_service.get_job = AsyncMock(return_value=job)
        mock_service.create_job = AsyncMock(return_value=(fresh_job, None))

        res = await reprocess_job(job_id=job.job_id, service=mock_service, user=user)
        assert res.job_id == "job_fresh888"


@pytest.mark.asyncio
async def test_reprocess_active_job_rejected_with_409():
    user = CurrentUser(1, "user@test.com", "user", [])
    in_progress_job = Job(
        job_id="job_active123",
        youtube_url="https://youtube.com",
        status=JobStatus.DOWNLOADING,
        user_id=1,
    )

    mock_service = MagicMock()
    mock_service.get_job = AsyncMock(return_value=in_progress_job)

    with pytest.raises(HTTPException) as exc_info:
        await reprocess_job(job_id="job_active123", service=mock_service, user=user)

    assert exc_info.value.status_code == 409
    assert "currently in progress" in exc_info.value.detail
