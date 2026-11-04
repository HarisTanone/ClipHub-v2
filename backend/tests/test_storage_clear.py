"""Tests for Storage Danger Zone cleanup route — verifying complete database, filesystem, and MinIO purge."""
import os
import shutil
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.infrastructure.db_connection import get_dict_connection
from src.presentation.auth_deps import CurrentUser
from src.presentation.routes.storage import clear_processing_data


@pytest.mark.asyncio
async def test_clear_storage_forbidden_for_non_superadmin():
    editor = CurrentUser(user_id=2, email="editor@example.com", role="editor", permissions=["jobs:create"])
    with pytest.raises(HTTPException) as exc:
        await clear_processing_data(editor)
    assert exc.value.status_code == 403
    assert "Superadmin access required" in exc.value.detail


@pytest.mark.asyncio
async def test_protected_tables_safety_guard():
    """Verify that protected tables like users, presets, styles, and settings are never deleted."""
    from src.presentation.routes.storage import PROTECTED_TABLES

    assert "users" in PROTECTED_TABLES
    assert "user_presets" in PROTECTED_TABLES
    assert "style_presets" in PROTECTED_TABLES
    assert "system_settings" in PROTECTED_TABLES
    assert "model_settings" in PROTECTED_TABLES
    assert "image_typography_templates" in PROTECTED_TABLES
    assert "image_typography_fonts" in PROTECTED_TABLES
    assert "social_accounts" in PROTECTED_TABLES


@pytest.mark.asyncio
async def test_clear_storage_full_purge():
    superadmin = CurrentUser(user_id=1, email="admin@example.com", role="superadmin", permissions=["*"])

    # 1. Setup dummy test files in tmp subdirectories
    test_files = [
        "tmp/output/test_job_123/clip_1.mp4",
        "tmp/downloads/sample_footage.mp4",
        "tmp/video_gen/voice_sample.wav",
        "tmp/image_studio/generated_test.png",
        "data/asset_cache/footage/cache_item.mp4",
    ]
    created_files = []
    for rel_path in test_files:
        full_path = os.path.abspath(rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write("test dummy content")
        created_files.append(full_path)

    # 2. Insert dummy records into database processing tables
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = set(r["name"] if isinstance(r, dict) else r[0] for r in cur.fetchall())

        if "jobs" in tables:
            cur.execute(
                "INSERT INTO jobs (job_id, user_id, status, youtube_url, target_aspect_ratio, clips_total, clips_success, clips_failed, created_at, updated_at) "
                "VALUES ('test_clear_job', 1, 'completed', 'https://youtube.com/watch?v=clear', '9:16', 1, 1, 0, '2026-11-04 12:00:00', '2026-11-04 12:00:00')"
            )
        if "video_generator_jobs" in tables:
            cur.execute(
                "INSERT INTO video_generator_jobs (job_id, user_id, topic, status, created_at) "
                "VALUES ('vg_test_clear', 1, 'Topic test', 'completed', 1730000000.0)"
            )
        if "ai_image_runs" in tables:
            cur.execute(
                "INSERT INTO ai_image_runs (user_id, run_date, session_name, topic, prompt) "
                "VALUES (1, '2026-11-04', 'Test Session', 'Topic AI', 'test prompt')"
            )
        if "autopilot_settings" in tables:
            cur.execute(
                "UPDATE autopilot_settings SET last_job_id = 'test_clear_job', last_video_title = 'Old Video' WHERE user_id = 1"
            )
        if "ai_image_settings" in tables:
            cur.execute(
                "UPDATE ai_image_settings SET today_images_created = 15, last_run_date = '2026-11-04' WHERE user_id = 1"
            )
        conn.commit()
    finally:
        conn.close()

    # 3. Mock MinIO clear_bucket to verify integration
    mock_minio = MagicMock()
    mock_minio.clear_bucket.return_value = 42

    with patch("src.infrastructure.minio_service.get_minio_service", return_value=mock_minio):
        result = await clear_processing_data(superadmin)

    # 4. Verify API response
    assert result["success"] is True
    assert result["details"]["minio_objects_deleted"] == 42
    assert result["details"]["local_files_deleted"] >= len(test_files)
    assert result["details"]["total_db_rows_deleted"] >= 1
    mock_minio.clear_bucket.assert_called_once()

    # 5. Verify local test files were deleted
    for full_path in created_files:
        assert not os.path.exists(full_path), f"File {full_path} should have been deleted"

    # 6. Verify essential directories exist and are ready for new jobs
    assert os.path.exists(os.path.abspath("tmp/output"))
    assert os.path.exists(os.path.abspath("tmp/downloads"))
    assert os.path.exists(os.path.abspath("tmp/video_gen"))
    assert os.path.exists(os.path.abspath("tmp/image_studio"))
    assert os.path.exists(os.path.abspath("data/asset_cache/footage"))

    # 7. Verify database tables are completely purged
    verify_conn = get_dict_connection()
    try:
        vcur = verify_conn.cursor()
        vcur.execute("SELECT count(*) as cnt FROM jobs WHERE job_id = 'test_clear_job'")
        row = vcur.fetchone()
        assert (row["cnt"] if isinstance(row, dict) else row[0]) == 0

        if "video_generator_jobs" in tables:
            vcur.execute("SELECT count(*) as cnt FROM video_generator_jobs WHERE job_id = 'vg_test_clear'")
            row = vcur.fetchone()
            assert (row["cnt"] if isinstance(row, dict) else row[0]) == 0

        if "ai_image_runs" in tables:
            vcur.execute("SELECT count(*) as cnt FROM ai_image_runs WHERE topic = 'Topic AI'")
            row = vcur.fetchone()
            assert (row["cnt"] if isinstance(row, dict) else row[0]) == 0

        # Verify settings reset
        if "autopilot_settings" in tables:
            vcur.execute("SELECT last_job_id, last_video_title FROM autopilot_settings WHERE user_id = 1")
            row = vcur.fetchone()
            if row:
                last_job = row["last_job_id"] if isinstance(row, dict) else row[0]
                assert last_job is None

        if "ai_image_settings" in tables:
            vcur.execute("SELECT today_images_created FROM ai_image_settings WHERE user_id = 1")
            row = vcur.fetchone()
            if row:
                cnt = row["today_images_created"] if isinstance(row, dict) else row[0]
                assert cnt == 0

        # Verify user accounts & presets are preserved
        vcur.execute("SELECT count(*) as cnt FROM users")
        row = vcur.fetchone()
        user_count = row["cnt"] if isinstance(row, dict) else row[0]
        assert user_count > 0, "Users table must be preserved"

    finally:
        verify_conn.close()
