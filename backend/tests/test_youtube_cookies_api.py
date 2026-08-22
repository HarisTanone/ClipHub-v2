import os
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock, mock_open

from src.presentation.api import app
from src.infrastructure.auth import create_access_token


@pytest.mark.asyncio
async def test_youtube_cookies_crud_api():
    token = create_access_token(1, "admin@autocliper.com", "superadmin", ["system:admin"])
    headers = {"Authorization": f"Bearer {token}"}

    sample_netscape_content = (
        "# Netscape HTTP Cookie File\n"
        "# https://curl.se/docs/http-cookies.html\n"
        ".youtube.com\tTRUE\t/\tTRUE\t1787432761\tSID\tsample_session_id_12345\n"
        ".youtube.com\tTRUE\t/\tTRUE\t1787432761\tHSID\tsample_hsid_67890\n"
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Save cookies
        save_resp = await client.post(
            "/api/settings/youtube-cookies",
            headers=headers,
            json={"content": sample_netscape_content},
        )
        assert save_resp.status_code == 200
        save_data = save_resp.json()
        assert save_data["success"] is True
        assert save_data["data"]["cookie_count"] == 2

        # 2. Get status
        get_resp = await client.get("/api/settings/youtube-cookies", headers=headers)
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["success"] is True
        assert get_data["data"]["exists"] is True
        assert get_data["data"]["cookie_count"] == 2

        # 3. Test probe mock
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            
            async def async_comm(*args, **kwargs):
                return (b'{"title": "Test YouTube Video", "formats": [1, 2, 3]}', b"")
            
            mock_proc.communicate = async_comm
            mock_exec.return_value = mock_proc

            test_resp = await client.post("/api/settings/youtube-cookies/test", headers=headers)
            assert test_resp.status_code == 200
            test_data = test_resp.json()
            assert test_data["success"] is True
            assert "Test YouTube Video" in test_data["title"]

        # 4. Delete cookies
        del_resp = await client.delete("/api/settings/youtube-cookies", headers=headers)
        assert del_resp.status_code == 200
        del_data = del_resp.json()
        assert del_data["success"] is True


@pytest.mark.asyncio
async def test_youtube_cookies_auto_extract_api():
    token = create_access_token(1, "admin@autocliper.com", "superadmin", ["system:admin"])
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    mock_stat = MagicMock()
    mock_stat.st_size = 128
    mock_stat.st_mtime = 1787432761

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("asyncio.create_subprocess_exec") as mock_exec, \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=128), \
             patch("os.stat", return_value=mock_stat), \
             patch("builtins.open", mock_open(read_data=".youtube.com\tTRUE\t/\tTRUE\t1787432761\tSID\tsample\n")):
            
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            
            async def async_comm(*args, **kwargs):
                return (b'{"title": "Test YouTube Video"}', b"")
            
            mock_proc.communicate = async_comm
            mock_exec.return_value = mock_proc

            resp = await client.post(
                "/api/settings/youtube-cookies/auto-extract",
                headers=headers,
                json={"browser": "chrome"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["browser_used"] == "chrome"
