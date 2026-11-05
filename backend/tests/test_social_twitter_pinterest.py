"""Tests for Twitter/X and Pinterest OAuth & boards routes via Repliz API."""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from src.presentation.api import app
from src.presentation.auth_deps import CurrentUser, get_current_user
from src.presentation.routes.auth import get_current_user as auth_get_current_user

class MockUser:
    id = 999
    email = "testuser@cliperhub.com"
    full_name = "Test Social User"
    role = "user"
    is_superadmin = False

mock_user = MockUser()


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[auth_get_current_user] = lambda: mock_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_twitter_authorize(client, monkeypatch):
    """Test Twitter/X authorize URL request."""
    async def mock_repliz_get(path, params=None):
        assert path == "/public/account/twitter/authorize"
        assert params["redirect"] == "https://myapp.com/callback"
        return {"url": "https://x.com/i/oauth2/authorize?client_id=123"}

    monkeypatch.setattr("src.presentation.routes.social.twitter.repliz_get", mock_repliz_get)

    res = client.get("/api/social/twitter/authorize?redirect=https://myapp.com/callback")
    assert res.status_code == 200
    data = res.json()
    assert "url" in data
    assert data["url"].startswith("https://x.com")


@pytest.mark.asyncio
async def test_twitter_connect(client, monkeypatch):
    """Test Twitter/X connect endpoint with account registration."""
    async def mock_repliz_post(path, json_body=None):
        assert path == "/public/account/twitter/connect"
        assert json_body["code"] == "auth_code_xyz"
        return {"accountId": "acc_tw_123", "status": "connected"}

    registered = []
    async def mock_register(user_id, acc_id, platform):
        registered.append((user_id, acc_id, platform))

    monkeypatch.setattr("src.presentation.routes.social.twitter.repliz_post", mock_repliz_post)
    monkeypatch.setattr("src.presentation.routes.social.twitter.register_account", mock_register)

    res = client.post("/api/social/twitter/connect", json={"code": "auth_code_xyz"})
    assert res.status_code == 200
    data = res.json()
    assert data["accountId"] == "acc_tw_123"
    assert len(registered) == 1
    assert registered[0] == (999, "acc_tw_123", "twitter")


@pytest.mark.asyncio
async def test_pinterest_authorize_and_boards(client, monkeypatch):
    """Test Pinterest authorize and boards listing endpoints."""
    async def mock_repliz_get(path, params=None):
        if path == "/public/account/pinterest/authorize":
            return {"url": "https://pinterest.com/oauth?client_id=456"}
        elif path == "/public/addon/pinterest/board":
            assert params["accountId"] == "acc_pin_456"
            return {"docs": [{"id": "board_1", "name": "Inspirasi Harian"}]}
        raise ValueError(f"Unexpected path: {path}")

    monkeypatch.setattr("src.presentation.routes.social.pinterest.repliz_get", mock_repliz_get)

    # 1. Authorize
    res_auth = client.get("/api/social/pinterest/authorize?redirect=https://myapp.com/callback")
    assert res_auth.status_code == 200
    assert "pinterest.com" in res_auth.json()["url"]

    # 2. Boards
    res_boards = client.get("/api/social/pinterest/boards?account_id=acc_pin_456")
    assert res_boards.status_code == 200
    assert len(res_boards.json()["docs"]) == 1
    assert res_boards.json()["docs"][0]["name"] == "Inspirasi Harian"
