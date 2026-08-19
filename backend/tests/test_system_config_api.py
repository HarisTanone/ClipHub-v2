import pytest
from httpx import AsyncClient, ASGITransport
from src.presentation.api import app
from src.infrastructure.auth import create_access_token


@pytest.mark.asyncio
async def test_get_system_config_endpoint_superadmin():
    """Verify superadmin can fetch system config."""
    token = create_access_token(1, "admin@autocliper.com", "superadmin", ["system:admin"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/settings/system-config", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["role"] == "superadmin"
        assert data["can_edit_secrets"] is True
        assert data["count"] > 50


@pytest.mark.asyncio
async def test_put_system_config_endpoint_superadmin():
    """Verify superadmin can update system config."""
    token = create_access_token(1, "admin@autocliper.com", "superadmin", ["system:admin"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.put(
            "/api/settings/system-config",
            headers={"Authorization": f"Bearer {token}"},
            json={"settings": {"BROLL_SPLICE_MAX_PER_CLIP": 4, "REMOTION_CONCURRENCY": 3}},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["updated_count"] >= 1
