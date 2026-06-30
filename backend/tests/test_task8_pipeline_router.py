"""Test Task 8: PipelineRouter — Premium check and pipeline routing.

Tests cover:
- Non-premium user → V2
- Premium user → V1
- Superadmin → always V1
- V2 disabled globally → V1 for all
- DB error → safe fallback to V1
- Feature registration in AVAILABLE_FEATURES
- pipeline_version field in Job entity
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.pipeline_router import PipelineRouter
from src.domain.entities import Job, JobStatus


def run_async(coro):
    return asyncio.run(coro)


# ─── Routing Logic Tests ──────────────────────────────────────────────────────

def test_non_premium_user_gets_v2():
    """User without premium → V2."""
    router = PipelineRouter()
    with patch.object(router, "_check_user_premium", return_value=False):
        assert router.should_use_v2(user_id=5, is_superadmin=False) is True
    print("  [PASS] Non-premium user → V2")


def test_premium_user_gets_v1():
    """User WITH is_premium=true → V1."""
    router = PipelineRouter()
    with patch.object(router, "_check_user_premium", return_value=True):
        assert router.should_use_v2(user_id=3, is_superadmin=False) is False
    print("  [PASS] Premium user → V1")


def test_superadmin_always_v1():
    """Superadmin always gets V1 regardless of features."""
    router = PipelineRouter()
    with patch.object(router, "_check_user_premium", return_value=False):
        assert router.should_use_v2(user_id=1, is_superadmin=True) is False
    print("  [PASS] Superadmin → always V1")


def test_v2_disabled_globally():
    """V2_PIPELINE_ENABLED=False → everyone gets V1."""
    router = PipelineRouter()
    with patch("src.infrastructure.pipeline_router.settings") as mock_settings:
        mock_settings.V2_PIPELINE_ENABLED = False
        assert router.should_use_v2(user_id=99, is_superadmin=False) is False
    print("  [PASS] V2 disabled globally → V1 for all")


def test_db_error_defaults_to_v2():
    """Database error during premium check → defaults to V2 (non-premium safe)."""
    router = PipelineRouter()
    with patch(
        "src.infrastructure.pipeline_router.get_dict_connection",
        side_effect=Exception("DB connection failed")
    ):
        # DB error → _check_user_premium returns False → should_use_v2 returns True
        # Rationale: better to give free pipeline than crash
        assert router.should_use_v2(user_id=5, is_superadmin=False) is True
    print("  [PASS] DB error → safe fallback to V2 (non-premium)")


def test_get_pipeline_version_v1():
    """get_pipeline_version returns 'v1' for premium users."""
    router = PipelineRouter()
    with patch.object(router, "_check_user_premium", return_value=True):
        assert router.get_pipeline_version(user_id=3, is_superadmin=False) == "v1"
    print("  [PASS] get_pipeline_version returns 'v1' for premium")


def test_get_pipeline_version_v2():
    """get_pipeline_version returns 'v2' for non-premium users."""
    router = PipelineRouter()
    with patch.object(router, "_check_user_premium", return_value=False):
        assert router.get_pipeline_version(user_id=5, is_superadmin=False) == "v2"
    print("  [PASS] get_pipeline_version returns 'v2' for non-premium")


# ─── DB Check Mock Tests ──────────────────────────────────────────────────────

def test_check_premium_feature_found():
    """User has is_premium=1 in DB → True."""
    router = PipelineRouter()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {"is_premium": 1}
    mock_conn.cursor.return_value = mock_cursor

    with patch(
        "src.infrastructure.pipeline_router.get_dict_connection",
        return_value=mock_conn
    ):
        assert router._check_user_premium(user_id=3) is True
    print("  [PASS] Premium user found in DB")


def test_check_premium_feature_not_found():
    """User has is_premium=0 → False."""
    router = PipelineRouter()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {"is_premium": 0}
    mock_conn.cursor.return_value = mock_cursor

    with patch(
        "src.infrastructure.pipeline_router.get_dict_connection",
        return_value=mock_conn
    ):
        assert router._check_user_premium(user_id=5) is False
    print("  [PASS] Non-premium user in DB")


# ─── Feature Registration Tests ───────────────────────────────────────────────

def test_premium_pipeline_in_available_features():
    """ALL_PREMIUM_FEATURES is registered for premium unlock."""
    from src.presentation.routes.features import ALL_PREMIUM_FEATURES
    assert "dual_subtitle" in ALL_PREMIUM_FEATURES
    assert "smart_camera" in ALL_PREMIUM_FEATURES
    assert "ai_layer" in ALL_PREMIUM_FEATURES
    assert len(ALL_PREMIUM_FEATURES) == 5
    print("  [PASS] ALL_PREMIUM_FEATURES has 5 features")


# ─── Job Entity Tests ─────────────────────────────────────────────────────────

def test_job_entity_has_pipeline_version():
    """Job entity includes pipeline_version field."""
    job = Job(job_id="test", youtube_url="https://youtube.com/watch?v=x")
    assert hasattr(job, "pipeline_version")
    assert job.pipeline_version == "v1"  # Default

    job_v2 = Job(job_id="test2", youtube_url="url", pipeline_version="v2")
    assert job_v2.pipeline_version == "v2"
    print("  [PASS] Job entity has pipeline_version field")


if __name__ == "__main__":
    print("\n=== Task 8 Tests: PipelineRouter ===\n")
    # Routing logic
    test_non_premium_user_gets_v2()
    test_premium_user_gets_v1()
    test_superadmin_always_v1()
    test_v2_disabled_globally()
    test_db_error_defaults_to_v2()
    test_get_pipeline_version_v1()
    test_get_pipeline_version_v2()
    # DB check
    test_check_premium_feature_found()
    test_check_premium_feature_not_found()
    # Feature registration
    test_premium_pipeline_in_available_features()
    # Job entity
    test_job_entity_has_pipeline_version()
    print("\n=== ALL TASK 8 TESTS PASSED (11/11) ===\n")
