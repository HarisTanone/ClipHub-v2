"""Test Task 9: API routes and frontend integration.

Tests cover:
- JobResponse schema includes pipeline_version field
- create_job passes is_superadmin for routing
- V2 pipeline routing in services.py (mock)
- Job entity round-trip with pipeline_version
- Schema validation (pipeline_version field default)
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.presentation.schemas.jobs import JobResponse, CreateJobRequest
from src.domain.entities import Job, JobStatus


def run_async(coro):
    return asyncio.run(coro)


# ─── Schema Tests ─────────────────────────────────────────────────────────────

def test_job_response_has_pipeline_version():
    """JobResponse schema includes pipeline_version."""
    response = JobResponse(
        job_id="test_001",
        youtube_url="https://youtube.com/watch?v=x",
        status="validating",
        pipeline_version="v2",
    )
    assert response.pipeline_version == "v2"
    print("  [PASS] JobResponse includes pipeline_version field")


def test_job_response_default_pipeline_version():
    """JobResponse defaults to v1 if not specified."""
    response = JobResponse(
        job_id="test_002",
        youtube_url="https://youtube.com/watch?v=y",
        status="completed",
    )
    assert response.pipeline_version == "v1"
    print("  [PASS] JobResponse defaults pipeline_version to 'v1'")


def test_job_response_serialization():
    """JobResponse serializes pipeline_version in JSON."""
    response = JobResponse(
        job_id="test_003",
        youtube_url="url",
        status="v2_transcribing",
        pipeline_version="v2",
    )
    data = response.model_dump()
    assert "pipeline_version" in data
    assert data["pipeline_version"] == "v2"
    print("  [PASS] pipeline_version serializes in JSON response")


def test_create_job_request_valid():
    """CreateJobRequest validates correctly."""
    req = CreateJobRequest(
        youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        target_aspect_ratio="9:16",
        hook_engine="v3",
    )
    assert req.youtube_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    print("  [PASS] CreateJobRequest validates correctly")


# ─── Service Routing Tests ────────────────────────────────────────────────────

def test_create_job_routes_v2_for_non_premium():
    """create_job routes to V2 for non-premium user."""
    from src.application.services import JobService

    # Create minimal service with mocks
    mock_repo = AsyncMock()
    mock_repo.get_by_url_active = AsyncMock(return_value=None)
    mock_repo.create = AsyncMock()
    mock_repo.update_clips_data = AsyncMock()

    mock_downloader = AsyncMock()
    mock_gemini = AsyncMock()
    mock_whisper = AsyncMock()
    mock_renderer = AsyncMock()
    mock_validator = MagicMock()

    service = JobService(
        job_repo=mock_repo,
        downloader=mock_downloader,
        gemini_analyzer=mock_gemini,
        whisper_local=mock_whisper,
        renderer=mock_renderer,
        validator=mock_validator,
    )

    async def run():
        with patch("src.infrastructure.pipeline_router.PipelineRouter.get_pipeline_version", return_value="v2"):
            with patch("asyncio.create_task") as mock_task:
                job, is_cached = await service.create_job(
                    youtube_url="https://youtube.com/watch?v=test",
                    user_id=5,
                    is_superadmin=False,
                )
                assert job.pipeline_version == "v2"
                mock_task.assert_called_once()

    run_async(run())
    print("  [PASS] create_job routes to V2 for non-premium user")


def test_create_job_routes_v1_for_premium():
    """create_job routes to V1 for premium/superadmin user."""
    from src.application.services import JobService

    mock_repo = AsyncMock()
    mock_repo.get_by_url_active = AsyncMock(return_value=None)
    mock_repo.create = AsyncMock()
    mock_repo.update_clips_data = AsyncMock()

    service = JobService(
        job_repo=mock_repo,
        downloader=AsyncMock(),
        gemini_analyzer=AsyncMock(),
        whisper_local=AsyncMock(),
        renderer=AsyncMock(),
        validator=MagicMock(),
    )

    async def run():
        with patch("src.infrastructure.pipeline_router.PipelineRouter.get_pipeline_version", return_value="v1"):
            with patch("asyncio.create_task") as mock_task:
                job, _ = await service.create_job(
                    youtube_url="https://youtube.com/watch?v=premium",
                    user_id=1,
                    is_superadmin=True,
                )
                assert job.pipeline_version == "v1"
                mock_task.assert_called_once()

    run_async(run())
    print("  [PASS] create_job routes to V1 for premium/superadmin")


def test_create_job_stores_pipeline_version():
    """Job entity has pipeline_version set before repo.create()."""
    from src.application.services import JobService

    created_jobs = []
    mock_repo = AsyncMock()
    mock_repo.get_by_url_active = AsyncMock(return_value=None)
    mock_repo.create = AsyncMock(side_effect=lambda job: created_jobs.append(job))
    mock_repo.update_clips_data = AsyncMock()

    service = JobService(
        job_repo=mock_repo,
        downloader=AsyncMock(),
        gemini_analyzer=AsyncMock(),
        whisper_local=AsyncMock(),
        renderer=AsyncMock(),
        validator=MagicMock(),
    )

    async def run():
        with patch("src.infrastructure.pipeline_router.PipelineRouter.get_pipeline_version", return_value="v2"):
            with patch("asyncio.create_task"):
                await service.create_job(
                    youtube_url="https://youtube.com/watch?v=store",
                    user_id=5,
                )

        assert len(created_jobs) == 1
        assert created_jobs[0].pipeline_version == "v2"

    run_async(run())
    print("  [PASS] pipeline_version stored in job before DB create")


# ─── V2 Status Compatibility ─────────────────────────────────────────────────

def test_v2_statuses_serialize_in_response():
    """V2 job statuses serialize correctly in JobResponse."""
    for status in ["v2_transcribing", "v2_analyzing", "v2_micro_slicing",
                   "v2_word_transcribing", "v2_vad_refining"]:
        response = JobResponse(
            job_id="test",
            youtube_url="url",
            status=status,
            pipeline_version="v2",
        )
        assert response.status == status
    print("  [PASS] V2 job statuses serialize correctly")


def test_job_entity_round_trip():
    """Job entity with pipeline_version round-trips correctly."""
    job = Job(
        job_id="test_rt",
        youtube_url="https://youtube.com/watch?v=rt",
        pipeline_version="v2",
        status=JobStatus.V2_TRANSCRIBING,
    )
    assert job.pipeline_version == "v2"
    assert job.status == JobStatus.V2_TRANSCRIBING
    assert job.status.value == "v2_transcribing"

    # Convert to response
    response = JobResponse(
        job_id=job.job_id,
        youtube_url=job.youtube_url,
        status=job.status.value,
        pipeline_version=job.pipeline_version,
    )
    assert response.pipeline_version == "v2"
    assert response.status == "v2_transcribing"
    print("  [PASS] Job entity → JobResponse round-trip works")


if __name__ == "__main__":
    print("\n=== Task 9 Tests: API Routes & Frontend Integration ===\n")
    # Schema
    test_job_response_has_pipeline_version()
    test_job_response_default_pipeline_version()
    test_job_response_serialization()
    test_create_job_request_valid()
    # Service routing
    test_create_job_routes_v2_for_non_premium()
    test_create_job_routes_v1_for_premium()
    test_create_job_stores_pipeline_version()
    # V2 compatibility
    test_v2_statuses_serialize_in_response()
    test_job_entity_round_trip()
    print("\n=== ALL TASK 9 TESTS PASSED (9/9) ===\n")
