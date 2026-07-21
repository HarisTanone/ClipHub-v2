"""Unit tests for the superadmin server-test control plane."""
import asyncio
import json
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from src.presentation.auth_deps import CurrentUser, require_superadmin
from src.presentation.routes import settings as settings_routes


def _user(role: str) -> CurrentUser:
    return CurrentUser(user_id=1, email="admin@example.com", role=role, permissions=[])


def test_test_run_guard_rejects_non_superadmin():
    guard = require_superadmin()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(guard(_user("user")))
    assert exc.value.status_code == 403


def test_test_status_returns_log_and_video_version(tmp_path, monkeypatch):
    status_path = tmp_path / "test-status.json"
    log_path = tmp_path / "test.log"
    video_path = tmp_path / "clip_test_final.mp4"
    status_path.write_text(json.dumps({"status": "passed", "stage": "completed"}))
    log_path.write_text("all tests passed\n")
    video_path.write_bytes(b"video")

    monkeypatch.setattr(settings_routes, "TEST_STATUS_PATH", status_path)
    monkeypatch.setattr(settings_routes, "TEST_LOG_PATH", log_path)
    monkeypatch.setattr(settings_routes, "TEST_VIDEO_PATH", video_path)

    response = asyncio.run(settings_routes.get_test_run_status(_user("superadmin")))
    assert response["data"]["status"] == "passed"
    assert response["data"]["video_available"] is True
    assert isinstance(response["data"]["video_version"], int)
    assert response["log"] == "all tests passed\n"


def test_start_test_run_uses_no_deploy(tmp_path, monkeypatch):
    script_path = tmp_path / "test.sh"
    script_path.write_text("#!/usr/bin/env bash\n")
    status_path = tmp_path / "logs" / "test-status.json"
    popen = Mock(return_value=Mock(pid=4321))

    monkeypatch.setattr(settings_routes, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(settings_routes, "TEST_SCRIPT_PATH", script_path)
    monkeypatch.setattr(settings_routes, "TEST_STATUS_PATH", status_path)
    monkeypatch.setattr(settings_routes, "TEST_LOG_PATH", tmp_path / "logs" / "test.log")
    monkeypatch.setattr(settings_routes, "TEST_VIDEO_PATH", tmp_path / "clip_test_final.mp4")
    monkeypatch.setattr(settings_routes.subprocess, "Popen", popen)

    response = asyncio.run(settings_routes.start_test_run(_user("superadmin")))
    assert response["success"] is True
    assert response["data"]["deploy_requested"] is False
    assert json.loads(status_path.read_text())["pid"] == 4321
    command = popen.call_args.args[0]
    assert command == ["bash", str(script_path), "--no-deploy"]


def test_fast_shell_failure_is_not_overwritten(tmp_path, monkeypatch):
    script_path = tmp_path / "test.sh"
    script_path.write_text("#!/usr/bin/env bash\n")
    status_path = tmp_path / "logs" / "test-status.json"

    def fail_immediately(*args, **kwargs):
        status_path.write_text(json.dumps({
            "status": "failed",
            "stage": "environment validation",
            "message": "Test failed; inspect the log",
        }))
        return Mock(pid=4322)

    monkeypatch.setattr(settings_routes, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(settings_routes, "TEST_SCRIPT_PATH", script_path)
    monkeypatch.setattr(settings_routes, "TEST_STATUS_PATH", status_path)
    monkeypatch.setattr(settings_routes, "TEST_LOG_PATH", tmp_path / "logs" / "test.log")
    monkeypatch.setattr(settings_routes, "TEST_VIDEO_PATH", tmp_path / "clip_test_final.mp4")
    monkeypatch.setattr(settings_routes.subprocess, "Popen", fail_immediately)

    asyncio.run(settings_routes.start_test_run(_user("superadmin")))
    persisted = json.loads(status_path.read_text())
    assert persisted["status"] == "failed"
    assert persisted["stage"] == "environment validation"