"""Tests for strict multi-user data isolation:
- Presets: each user only sees their own presets.
- Preset resolver: user B never resolves or inherits user A's presets.
- Jobs / Clips: user B cannot see or access user A's jobs from panel, Autopilot, or Telegram.
- Hermes Autopilot: settings, quota, and run history are strictly isolated per user.
"""
import pytest
from httpx import AsyncClient, ASGITransport

from src.config import settings
from src.infrastructure.db_connection import get_dict_connection
from src.infrastructure.auth import create_access_token
from src.infrastructure.preset_resolver import resolve_preset
from src.infrastructure.autopilot_service import autopilot_service
from src.presentation.api import app


@pytest.fixture(autouse=True)
def setup_test_users():
    """Ensure test users exist in the users table."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users (id, email, hashed_password, full_name, role_id) VALUES (101, 'user_a@test.com', 'hash', 'User A', 2)")
        cur.execute("INSERT OR IGNORE INTO users (id, email, hashed_password, full_name, role_id) VALUES (102, 'user_b@test.com', 'hash', 'User B', 2)")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def user_a_token():
    return create_access_token(user_id=101, email="user_a@test.com", role="editor", permissions=["jobs:create", "jobs:read"])


@pytest.fixture
def user_b_token():
    return create_access_token(user_id=102, email="user_b@test.com", role="editor", permissions=["jobs:create", "jobs:read"])


@pytest.fixture
def user_admin_token():
    return create_access_token(user_id=999, email="admin_test@test.com", role="superadmin", permissions=["*"])


@pytest.mark.asyncio
async def test_preset_multi_user_isolation(user_a_token, user_b_token):
    """Verify that presets created by user A are never visible to user B."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. User A creates a unique preset
        res_a = await client.post(
            "/api/presets",
            headers={"Authorization": f"Bearer {user_a_token}"},
            json={
                "name": "Secret Preset User A",
                "hook_style": {"animation": "pov_stamp", "boxColor": "#FF1111"},
                "subtitle_style": {"stylePreset": "bold_impact", "highlightColor": "#FF1111"},
            }
        )
        assert res_a.status_code == 201, res_a.text
        data_a = res_a.json()
        preset_id = data_a["id"]
        preset_slug = data_a["slug"]

        # 2. User A can list and see it
        list_a = await client.get("/api/presets", headers={"Authorization": f"Bearer {user_a_token}"})
        assert list_a.status_code == 200
        slugs_a = [p["slug"] for p in list_a.json()["data"]]
        assert preset_slug in slugs_a

        # 3. User B lists presets -> MUST NOT contain User A's preset
        list_b = await client.get("/api/presets", headers={"Authorization": f"Bearer {user_b_token}"})
        assert list_b.status_code == 200
        slugs_b = [p["slug"] for p in list_b.json()["data"]]
        assert preset_slug not in slugs_b

        # 4. User B tries to fetch User A's preset by ID or slug -> MUST be 404
        get_b_by_id = await client.get(f"/api/presets/{preset_id}", headers={"Authorization": f"Bearer {user_b_token}"})
        assert get_b_by_id.status_code == 404

        get_b_by_slug = await client.get(f"/api/presets/{preset_slug}", headers={"Authorization": f"Bearer {user_b_token}"})
        assert get_b_by_slug.status_code == 404

        # 5. User B resolving preset slug via preset_resolver must not get User A's preset
        resolved_b = resolve_preset(preset_slug, user_id=102)
        assert resolved_b.get("slug") != preset_slug
        assert resolved_b.get("name") != "Secret Preset User A"

        # 6. User B with "default" must not inherit User A's preset
        resolved_b_default = resolve_preset("default", user_id=102)
        assert resolved_b_default.get("name") != "Secret Preset User A"


@pytest.mark.asyncio
async def test_job_and_clip_multi_user_isolation(user_a_token, user_b_token):
    """Verify that jobs and clips are strictly isolated between users."""
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        test_job_id = "job_user_a_isolation_test"
        cur.execute("""
            INSERT OR REPLACE INTO jobs (
                job_id, user_id, status, youtube_url, target_aspect_ratio, clips_total, clips_success, clips_failed,
                created_at, updated_at
            )
            VALUES (?, 101, 'completed', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', '9:16', 1, 1, 0, datetime('now'), datetime('now'))
        """, (test_job_id,))
        conn.commit()
    finally:
        conn.close()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. User A lists jobs -> sees own job
        list_a = await client.get("/api/jobs", headers={"Authorization": f"Bearer {user_a_token}"})
        assert list_a.status_code == 200
        jobs_a = [j["job_id"] for j in list_a.json()["data"]]
        assert test_job_id in jobs_a

        # 2. User B lists jobs -> MUST NOT see User A's job
        list_b = await client.get("/api/jobs", headers={"Authorization": f"Bearer {user_b_token}"})
        assert list_b.status_code == 200
        jobs_b = [j["job_id"] for j in list_b.json()["data"]]
        assert test_job_id not in jobs_b

        # 3. User B tries to view detail of User A's job -> 404
        detail_b = await client.get(f"/api/jobs/{test_job_id}/detail", headers={"Authorization": f"Bearer {user_b_token}"})
        assert detail_b.status_code == 404

        # 4. User B tries to trigger Telegram send for User A's job -> 404
        tg_b = await client.post(
            f"/api/telegram/send-clip/{test_job_id}/1",
            headers={"Authorization": f"Bearer {user_b_token}"},
            json={}
        )
        assert tg_b.status_code == 404


@pytest.mark.asyncio
async def test_autopilot_settings_and_history_isolation(user_a_token, user_b_token):
    """Verify that Hermes Autopilot settings and run history are strictly isolated."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. User A enables autopilot with custom niche
        save_a = await client.post(
            "/api/autopilot/settings",
            headers={"Authorization": f"Bearer {user_a_token}"},
            json={
                "enabled": True,
                "niche_query": "sains teknologi rahasia",
                "run_time": "09:30",
            }
        )
        assert save_a.status_code == 200
        data_a = save_a.json()["data"]
        assert data_a["enabled"] is True
        assert data_a["niche_query"] == "sains teknologi rahasia"

        # 2. User B fetches autopilot settings -> MUST be disabled with default/empty values
        get_b = await client.get(
            "/api/autopilot/settings",
            headers={"Authorization": f"Bearer {user_b_token}"}
        )
        assert get_b.status_code == 200
        data_b = get_b.json()["data"]
        assert data_b["enabled"] is False
        assert data_b["niche_query"] != "sains teknologi rahasia"
        assert data_b["last_job_id"] is None

        # 3. Insert fake run for User A in autopilot_runs
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO autopilot_runs (user_id, run_date, status, video_title, youtube_url, job_id, created_at)
                VALUES (101, '2026-09-01', 'completed', 'Secret Video User A', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'job_auto_101', datetime('now'))
            """)
            conn.commit()
        finally:
            conn.close()

        # 4. User A sees the run in history
        hist_a = await client.get("/api/autopilot/history", headers={"Authorization": f"Bearer {user_a_token}"})
        assert hist_a.status_code == 200
        items_a = [h["job_id"] for h in hist_a.json()["data"]]
        assert "job_auto_101" in items_a

        # 5. User B checks history -> MUST be empty (cannot see User A's run)
        hist_b = await client.get("/api/autopilot/history", headers={"Authorization": f"Bearer {user_b_token}"})
        assert hist_b.status_code == 200
        items_b = [h["job_id"] for h in hist_b.json()["data"]]
        assert "job_auto_101" not in items_b
