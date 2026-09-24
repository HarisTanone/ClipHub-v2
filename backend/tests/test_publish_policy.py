"""Focused regression tests for admin-configurable social publishing policy."""
import pytest
from pydantic import ValidationError

from src.presentation.routes.social.publish import (
    BatchPublishRequest,
    PublishRequest,
    calculate_batch_schedule_times,
    _publish_int_setting,
)


def test_publish_policy_metadata_has_bounds():
    from src.infrastructure.system_config_store import SYSTEM_SETTINGS_METADATA

    for key in (
        "PUBLISH_MIN_FUTURE_BUFFER_MINUTES",
        "PUBLISH_BATCH_MAX_CLIPS",
        "PUBLISH_CAPTION_MAX_CHARS",
        "PUBLISH_DEFAULT_MUSIC_VOLUME",
        "PUBLISH_DEFAULT_ORIGINAL_VOLUME",
    ):
        meta = SYSTEM_SETTINGS_METADATA[key]
        assert meta["min_value"] <= meta["default"] <= meta["max_value"]


def test_publish_policy_defaults_are_safe(monkeypatch):
    monkeypatch.setattr(
        "src.presentation.routes.social.publish._publish_setting",
        lambda key, default: default,
    )
    assert _publish_int_setting("PUBLISH_MIN_FUTURE_BUFFER_MINUTES", 2, 0, 1440) == 2
    assert _publish_int_setting("PUBLISH_BATCH_MAX_CLIPS", 50, 1, 200) == 50


def test_batch_request_has_transport_ceiling_and_runtime_policy_is_separate():
    request = BatchPublishRequest(
        jobId="job_policy",
        clipRanks=list(range(1, 51)),
        accountIds=["account-1"],
    )
    assert len(request.clipRanks) == 50
    with pytest.raises(ValidationError):
        BatchPublishRequest(
            jobId="job_policy",
            clipRanks=list(range(1, 202)),
            accountIds=["account-1"],
        )


def test_publish_request_allows_server_default_volume_resolution():
    request = PublishRequest(jobId="job_policy", scheduleAt="")
    assert request.originalVolume is None
    assert request.musicVolume is None


def test_batch_schedule_custom_requires_one_time_per_clip():
    with pytest.raises(Exception):
        calculate_batch_schedule_times(2, "custom", custom_schedule_times=["2026-01-01T00:00:00Z"])
