"""Tests for Video Generator endpoints, Repliz streaming, candidate resolution, and user attribution."""
import os
import shutil
import tempfile
import pytest
from httpx import AsyncClient, ASGITransport

from src.presentation.api import app
from src.infrastructure.auth import create_access_token
from src.config import settings
from src.infrastructure.database import async_session, JobModel
from src.infrastructure.db_connection import get_dict_connection


@pytest.fixture
def test_user_token():
    return create_access_token(user_id=1, email="admin@autocliper.com", role="superadmin", permissions=["*"])


@pytest.fixture
def regular_user_token():
    return create_access_token(user_id=2, email="user1@test.com", role="editor", permissions=["jobs:read", "jobs:write"])


@pytest.mark.asyncio
async def test_videogen_list_jobs_default_limit(test_user_token):
    """Verify default limit in GET /api/video-generator/jobs is now 10 (was 8)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/video-generator/jobs", headers={"Authorization": f"Bearer {test_user_token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["limit"] == 10


@pytest.mark.asyncio
async def test_repliz_video_and_download_endpoints():
    """Verify /api/video-generator/jobs/{job_id}/video and download endpoints with fallback candidate paths."""
    job_id = "test_repliz_vg_01"
    vg_dir = os.path.join(settings.VIDEO_GEN_OUTPUT_DIR, job_id)
    os.makedirs(vg_dir, exist_ok=True)
    video_file = os.path.join(vg_dir, f"final_{job_id}.mp4")

    # Create a dummy mp4 content with 1024 bytes
    fake_content = b"TEST_MP4_CONTENT_" * 64
    with open(video_file, "wb") as f:
        f.write(fake_content)

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Public endpoint /api/video-generator/jobs/{job_id}/video (No Auth required for Repliz)
            res = await client.get(f"/api/video-generator/jobs/{job_id}/video")
            assert res.status_code == 200
            assert res.headers["content-type"] == "video/mp4"
            assert res.headers["accept-ranges"] == "bytes"
            assert res.content == fake_content

            # 2. HTTP Byte-Range Request (Repliz chunked crawler support)
            range_header = {"range": "bytes=0-15"}
            res_range = await client.get(f"/api/video-generator/jobs/{job_id}/video", headers=range_header)
            assert res_range.status_code == 206
            assert res_range.headers["content-range"].startswith("bytes 0-15/")
            assert res_range.content == fake_content[:16]

            # 3. Download endpoint /jobs/{job_id}/download without auth
            res_down = await client.get(f"/api/video-generator/jobs/{job_id}/download")
            assert res_down.status_code == 200
            assert res_down.headers["content-type"] == "video/mp4"

            # 4. Fallback in /api/jobs/{job_id}/clips/1/video
            res_clip_vid = await client.get(f"/api/jobs/{job_id}/clips/1/video")
            assert res_clip_vid.status_code in (200, 206)
            assert res_clip_vid.content == fake_content

            # 5. Fallback in /api/jobs/{job_id}/clips/1/final
            res_clip_fin = await client.get(f"/api/jobs/{job_id}/clips/1/final")
            assert res_clip_fin.status_code in (200, 206)
            assert res_clip_fin.content == fake_content
    finally:
        shutil.rmtree(vg_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_thumbnail_candidate_resolution():
    """Verify /api/video-generator/jobs/{job_id}/thumbnail and /api/jobs/{job_id}/clips/1/thumb."""
    job_id = "test_repliz_thumb_01"
    vg_dir = os.path.join(settings.VIDEO_GEN_OUTPUT_DIR, job_id)
    os.makedirs(vg_dir, exist_ok=True)
    thumb_file = os.path.join(vg_dir, f"thumbnail_{job_id}.jpg")

    fake_thumb = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 50
    with open(thumb_file, "wb") as f:
        f.write(fake_thumb)

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Video generator thumbnail
            res_thumb = await client.get(f"/api/video-generator/jobs/{job_id}/thumbnail")
            assert res_thumb.status_code == 200
            assert res_thumb.headers["content-type"] == "image/jpeg"
            assert res_thumb.content == fake_thumb

            # 2. Jobs route clip thumb fallback
            res_job_thumb = await client.get(f"/api/jobs/{job_id}/clips/1/thumb")
            assert res_job_thumb.status_code == 200
            assert res_job_thumb.headers["content-type"] == "image/jpeg"
            assert res_job_thumb.content == fake_thumb
    finally:
        shutil.rmtree(vg_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_user_attribution_on_jobs_api(test_user_token):
    """Verify user attribution (user_id, user_email, user_name) is returned in list_jobs, get_job, and get_job_detail."""
    job_id = "job_test_user_attr_99"

    # Ensure a test user exists in sqlite
    conn = get_dict_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users (id, email, hashed_password, full_name, role_id) VALUES (?, ?, ?, ?, ?)",
        (999, "creator99@example.com", "hash", "Creator Ninety Nine", 2)
    )
    conn.commit()
    conn.close()

    # Insert test job
    async with async_session() as session:
        job = JobModel(
            job_id=job_id,
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            video_title="Attribution Test Video",
            status="completed",
            user_id=999,
        )
        session.add(job)
        await session.commit()

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {test_user_token}"}

            # 1. Test GET /api/jobs (list_jobs)
            res_list = await client.get("/api/jobs?limit=50", headers=headers)
            assert res_list.status_code == 200
            data_list = res_list.json()
            matching = [j for j in data_list["data"] if j["job_id"] == job_id]
            assert len(matching) == 1
            item = matching[0]
            assert item["user_id"] == 999
            assert item["user_email"] == "creator99@example.com"
            assert item["user_name"] == "Creator Ninety Nine"

            # 2. Test GET /api/jobs/{job_id} (get_job)
            res_get = await client.get(f"/api/jobs/{job_id}", headers=headers)
            assert res_get.status_code == 200
            job_resp = res_get.json()
            assert job_resp["user_id"] == 999
            assert job_resp["user_email"] == "creator99@example.com"
            assert job_resp["user_name"] == "Creator Ninety Nine"

            # 3. Test GET /api/jobs/{job_id}/detail (get_job_detail)
            res_detail = await client.get(f"/api/jobs/{job_id}/detail", headers=headers)
            assert res_detail.status_code == 200
            detail_data = res_detail.json()["data"]
            assert detail_data["user_id"] == 999
            assert detail_data["user_email"] == "creator99@example.com"
            assert detail_data["user_name"] == "Creator Ninety Nine"
    finally:
        async with async_session() as session:
            from sqlalchemy import delete
            await session.execute(delete(JobModel).where(JobModel.job_id == job_id))
            await session.commit()
