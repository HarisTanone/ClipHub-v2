"""Regression tests: AutoClipService.create_job()'s URL-dedup cache must not
silently return a previously-completed (or still-active) job rendered with a
DIFFERENT style than the one explicitly requested now.

Reported bug: a user submitted a job for a YouTube URL with
`--style test-anjing`. That exact URL had completed before (with a
different/default style) within the 7-day dedup cache window. create_job()
returned the OLD job unchanged — the new style was silently never applied,
with no error surfaced anywhere.
"""
import pytest
from unittest.mock import AsyncMock, patch

from src.domain.entities import Job, JobStatus, CachedJobResult
from src.application.services import AutoClipService


def _init_bare(deduplicator, repo) -> AutoClipService:
    svc = AutoClipService.__new__(AutoClipService)
    svc._deduplicator = deduplicator
    svc._repo = repo
    return svc


@pytest.mark.asyncio
async def test_completed_job_cache_hit_skipped_when_requested_style_differs():
    """A completed job cached for this URL under style "default" must NOT be
    returned when the caller now explicitly asks for a different named style
    — the request must proceed to actually (re)render with the new style."""
    cached_job = Job(
        job_id="job_old_default_style",
        youtube_url="https://www.youtube.com/watch?v=abc12345678",
        status=JobStatus.COMPLETED,
        style_preset="default",
    )
    deduplicator = AsyncMock()
    deduplicator.check_dedup.return_value = CachedJobResult(
        job_id=cached_job.job_id, status="completed", output_path="", caption_response=None, requested_at="now",
    )
    repo = AsyncMock()
    repo.get_by_job_id.return_value = cached_job
    repo.get_by_url_active.return_value = None

    svc = _init_bare(deduplicator, repo)

    # A distinctive sentinel so we can tell whether create_job() progressed
    # PAST the dedup check into actually resolving a fresh render, instead
    # of mocking the entire rest of job creation.
    class _ProgressedPastDedup(Exception):
        pass

    with patch(
        "src.infrastructure.hook_manifest.resolve_hook_preset",
        side_effect=_ProgressedPastDedup,
    ), patch("src.infrastructure.downloader.get_canonical_youtube_url", side_effect=lambda u: u):
        with pytest.raises(_ProgressedPastDedup):
            await svc.create_job(
                youtube_url="https://www.youtube.com/watch?v=abc12345678",
                style_preset="test-anjing",
                force_reprocess=False,
            )

    deduplicator.check_dedup.assert_awaited_once()


@pytest.mark.asyncio
async def test_completed_job_cache_hit_reused_when_style_matches():
    """Same video, SAME requested style as the cached job: the cache hit is
    still the correct, intended behavior (avoid redundant reprocessing)."""
    cached_job = Job(
        job_id="job_old_same_style",
        youtube_url="https://www.youtube.com/watch?v=abc12345678",
        status=JobStatus.COMPLETED,
        style_preset="test-anjing",
    )
    deduplicator = AsyncMock()
    deduplicator.check_dedup.return_value = CachedJobResult(
        job_id=cached_job.job_id, status="completed", output_path="", caption_response=None, requested_at="now",
    )
    repo = AsyncMock()
    repo.get_by_job_id.return_value = cached_job

    svc = _init_bare(deduplicator, repo)

    with patch("src.infrastructure.downloader.get_canonical_youtube_url", side_effect=lambda u: u):
        job, is_cached = await svc.create_job(
            youtube_url="https://www.youtube.com/watch?v=abc12345678",
            style_preset="test-anjing",
            force_reprocess=False,
        )

    assert job.job_id == "job_old_same_style"
    assert is_cached is True


@pytest.mark.asyncio
async def test_completed_job_cache_hit_reused_when_no_style_explicitly_requested():
    """No explicit style requested (empty/"default"): any cached style is an
    acceptable match, since the caller didn't ask for anything specific."""
    cached_job = Job(
        job_id="job_old_whatever_style",
        youtube_url="https://www.youtube.com/watch?v=abc12345678",
        status=JobStatus.COMPLETED,
        style_preset="some_named_preset",
    )
    deduplicator = AsyncMock()
    deduplicator.check_dedup.return_value = CachedJobResult(
        job_id=cached_job.job_id, status="completed", output_path="", caption_response=None, requested_at="now",
    )
    repo = AsyncMock()
    repo.get_by_job_id.return_value = cached_job

    svc = _init_bare(deduplicator, repo)

    with patch("src.infrastructure.downloader.get_canonical_youtube_url", side_effect=lambda u: u):
        job, is_cached = await svc.create_job(
            youtube_url="https://www.youtube.com/watch?v=abc12345678",
            style_preset="",
            force_reprocess=False,
        )

    assert job.job_id == "job_old_whatever_style"
    assert is_cached is True


@pytest.mark.asyncio
async def test_active_job_reuse_also_skipped_when_requested_style_differs():
    """Same style-awareness guard applies to the in-progress (non-terminal)
    job lookup, not just the completed-job cache."""
    active_job = Job(
        job_id="job_active_default_style",
        youtube_url="https://www.youtube.com/watch?v=abc12345678",
        status=JobStatus.DOWNLOADING,
        style_preset="default",
    )
    deduplicator = AsyncMock()
    deduplicator.check_dedup.return_value = None
    repo = AsyncMock()
    repo.get_by_url_active.return_value = active_job

    svc = _init_bare(deduplicator, repo)

    class _ProgressedPastDedup(Exception):
        pass

    with patch(
        "src.infrastructure.hook_manifest.resolve_hook_preset",
        side_effect=_ProgressedPastDedup,
    ), patch("src.infrastructure.downloader.get_canonical_youtube_url", side_effect=lambda u: u):
        with pytest.raises(_ProgressedPastDedup):
            await svc.create_job(
                youtube_url="https://www.youtube.com/watch?v=abc12345678",
                style_preset="test-anjing",
                force_reprocess=False,
            )
