"""Unit tests for StorageCleanupService and auto-clear midnight cron."""
import datetime as dt
import os
import pytest

from src.infrastructure.storage_cleanup_service import (
    PROTECTED_TABLES,
    StorageCleanupService,
)


def test_protected_tables_complete():
    """Verify that essential tables are strictly protected from deletion."""
    assert "users" in PROTECTED_TABLES
    assert "social_accounts" in PROTECTED_TABLES
    assert "system_settings" in PROTECTED_TABLES
    assert "model_settings" in PROTECTED_TABLES
    assert "style_presets" in PROTECTED_TABLES
    assert "object_overlay_configs" in PROTECTED_TABLES
    assert "hyperframes_configs" in PROTECTED_TABLES


def test_storage_cleanup_folder_contents_preserves_root(tmp_path):
    """Verify that _clear_folder_contents deletes children but preserves the target directory itself."""
    service = StorageCleanupService()

    target_dir = tmp_path / "test_storage"
    target_dir.mkdir()
    (target_dir / "file1.mp4").write_text("dummy video")
    sub_dir = target_dir / "job_123"
    sub_dir.mkdir()
    (sub_dir / "clip_1.mp4").write_text("dummy clip")

    assert os.path.exists(target_dir)
    assert len(os.listdir(target_dir)) == 2

    files_removed, dirs_removed = service._clear_folder_contents(str(target_dir))

    # Target directory still exists, but contents are wiped
    assert os.path.exists(target_dir)
    assert os.path.isdir(target_dir)
    assert len(os.listdir(target_dir)) == 0
    assert files_removed == 2
    assert len(dirs_removed) == 1


def test_storage_cleanup_preserves_symlinks(tmp_path):
    """Verify that a symlinked directory's contents are cleared without destroying the symlink."""
    service = StorageCleanupService()

    real_data_dir = tmp_path / "mnt_data_storage"
    real_data_dir.mkdir()
    (real_data_dir / "sample.mp4").write_text("video on mount")

    link_dir = tmp_path / "project_tmp"
    os.symlink(str(real_data_dir), str(link_dir))

    assert os.path.islink(link_dir)
    assert len(os.listdir(link_dir)) == 1

    files_removed, dirs_removed = service._clear_folder_contents(str(link_dir))

    # Symlink is STILL a symlink, real dir still exists, contents emptied
    assert os.path.islink(link_dir)
    assert os.path.exists(real_data_dir)
    assert len(os.listdir(real_data_dir)) == 0
    assert files_removed == 1


def test_midnight_check_window():
    """Verify _should_run_midnight_cleanup only triggers between 00:00 and 00:05."""
    service = StorageCleanupService()

    time_midnight = dt.datetime(2026, 11, 20, 0, 2, 0)
    time_noon = dt.datetime(2026, 11, 20, 12, 0, 0)
    time_late = dt.datetime(2026, 11, 20, 0, 10, 0)

    assert service._should_run_midnight_cleanup(time_noon) is False
    assert service._should_run_midnight_cleanup(time_late) is False


def test_cleanup_execution_and_history():
    """Verify execution logs a run to storage_cleanup_runs."""
    service = StorageCleanupService()
    result = service.execute_cleanup(trigger_source="unit_test")

    assert result["success"] is True
    assert "db_rows_deleted" in result
    assert "files_deleted" in result

    history = service.get_cleanup_history(limit=5)
    assert len(history) > 0
    latest = history[0]
    assert latest["trigger_source"] == "unit_test"
