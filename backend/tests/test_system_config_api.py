import pytest
from httpx import AsyncClient, ASGITransport
from src.presentation.api import app
from src.infrastructure.auth import create_access_token


@pytest.fixture
def superadmin_headers():
    token = create_access_token(1, "admin@autocliper.com", "superadmin", ["system:admin"])
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_system_config_endpoint_superadmin(superadmin_headers):
    """Verify superadmin can fetch system config."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/settings/system-config", headers=superadmin_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["role"] == "superadmin"
        assert data["can_edit_secrets"] is True
        assert data["count"] > 50
        publish = {item["key"]: item for item in data["data"] if item["category"] == "social_publish"}
        assert publish["PUBLISH_BATCH_MAX_CLIPS"]["min_value"] == 1
        assert publish["PUBLISH_BATCH_MAX_CLIPS"]["max_value"] == 200


@pytest.mark.asyncio
async def test_put_system_config_endpoint_superadmin(superadmin_headers):
    """Verify superadmin can update system config."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.put(
            "/api/settings/system-config",
            headers=superadmin_headers,
            json={"settings": {"BROLL_SPLICE_MAX_PER_CLIP": 4, "REMOTION_CONCURRENCY": 3}},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["updated_count"] >= 1


@pytest.mark.asyncio
async def test_put_system_config_rejects_unknown_key(superadmin_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.put(
            "/api/settings/system-config",
            headers=superadmin_headers,
            json={"settings": {"PUBLISH_NOT_A_REAL_SETTING": 1}},
        )
        assert res.status_code == 400
        assert "Unknown system setting key" in res.json()["detail"]


@pytest.mark.asyncio
async def test_put_system_config_rejects_publish_value_outside_bounds(superadmin_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.put(
            "/api/settings/system-config",
            headers=superadmin_headers,
            json={"settings": {"PUBLISH_BATCH_MAX_CLIPS": 0}},
        )
        assert res.status_code == 422
        assert "PUBLISH_BATCH_MAX_CLIPS" in res.json()["detail"]
