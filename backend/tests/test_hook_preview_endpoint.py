"""Tests for unified /api/hook-preview endpoint."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.presentation.api import app
from src.presentation.auth_deps import CurrentUser


FAKE_USER = CurrentUser(user_id=1, email="test@test.com", role="superadmin", permissions=[])
FAKE_HASH = "a" * 64  # valid 64-char hex


def _auth_override():
    return FAKE_USER


def _client():
    app.dependency_overrides = {}
    from src.presentation.auth_deps import get_current_user
    app.dependency_overrides[get_current_user] = _auth_override
    return TestClient(app, raise_server_exceptions=False)


# ── POST /api/hook-preview ────────────────────────────────────────────────────

def test_post_hook_preview_returns_image_url_and_hash(tmp_path):
    fake_result = {
        "path": str(tmp_path / f"{FAKE_HASH}.png"),
        "hash": FAKE_HASH,
        "cache_hit": False,
        "engine": "remotion",
        "renderer_version": "hook-render-spec-v1",
    }
    with patch("src.presentation.routes.hook_preview._get_service") as mock_svc_factory:
        svc = MagicMock()
        svc.render = AsyncMock(return_value=fake_result)
        mock_svc_factory.return_value = svc

        client = _client()
        resp = client.post(
            "/api/hook-preview",
            json={
                "config": {"engine": "remotion", "animation": "podcast_lower_third", "duration": 3},
                "text": "INI HOOK",
                "frame": 15,
            },
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["image_url"].endswith(FAKE_HASH)
    assert data["hash"] == FAKE_HASH
    assert data["engine"] == "remotion"
    assert data["cache_hit"] is False


def test_post_hook_preview_empty_text_is_rejected():
    client = _client()
    resp = client.post(
        "/api/hook-preview",
        json={"config": {"engine": "remotion", "animation": "podcast_lower_third"}, "text": "   ", "frame": 0},
    )
    assert resp.status_code == 422


def test_post_hook_preview_unsupported_engine_returns_422():
    client = _client()
    resp = client.post(
        "/api/hook-preview",
        json={"config": {"engine": "magic_engine", "animation": "x"}, "text": "HOOK", "frame": 0},
    )
    assert resp.status_code == 422


def test_post_hook_preview_renderer_failure_returns_503():
    with patch("src.presentation.routes.hook_preview._get_service") as mock_svc_factory:
        svc = MagicMock()
        svc.render = AsyncMock(side_effect=RuntimeError("remotion renderer down"))
        mock_svc_factory.return_value = svc

        client = _client()
        resp = client.post(
            "/api/hook-preview",
            json={
                "config": {"engine": "remotion", "animation": "podcast_lower_third", "duration": 3},
                "text": "HOOK",
                "frame": 0,
            },
        )
    assert resp.status_code == 503


# ── GET /api/hook-preview/image/{hash} ───────────────────────────────────────

def test_get_image_returns_png_when_file_exists(tmp_path, monkeypatch):
    png_path = tmp_path / f"{FAKE_HASH}.png"
    png_path.write_bytes(b"\x89PNG\r\n")

    import src.presentation.routes.hook_preview as mod
    monkeypatch.setattr(mod, "_PREVIEW_CACHE_DIR", str(tmp_path))

    with patch("src.presentation.routes.hook_preview.decode_access_token", return_value={"sub": "1"}):
        client = _client()
        resp = client.get(f"/api/hook-preview/image/{FAKE_HASH}?token=fake")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")


def test_get_image_invalid_hash_returns_400_or_422():
    with patch("src.presentation.routes.hook_preview.decode_access_token", return_value={"sub": "1"}):
        client = _client()
        # path traversal attempt — FastAPI will 422 or route rejects with 400
        resp = client.get("/api/hook-preview/image/notahex?token=fake")
    assert resp.status_code in (400, 422)


def test_get_image_missing_artifact_returns_404(tmp_path, monkeypatch):
    import src.presentation.routes.hook_preview as mod
    monkeypatch.setattr(mod, "_PREVIEW_CACHE_DIR", str(tmp_path))

    with patch("src.presentation.routes.hook_preview.decode_access_token", return_value={"sub": "1"}):
        client = _client()
        resp = client.get(f"/api/hook-preview/image/{FAKE_HASH}?token=fake")
    assert resp.status_code == 404
