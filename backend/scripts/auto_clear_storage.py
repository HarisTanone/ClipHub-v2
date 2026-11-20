#!/usr/bin/env python3
"""CLI runner for AutoCliper midnight storage cleanup.

Can be run standalone or invoked via system cron at 00:00 every day:
0 0 * * * /home/backend/project/ClipHub-v2/backend/venv/bin/python /home/backend/project/ClipHub-v2/backend/scripts/auto_clear_storage.py >> /home/backend/project/ClipHub-v2/logs/auto_clear.log 2>&1
"""
import os
import sys

# Ensure backend root is in PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.storage_cleanup_service import storage_cleanup_service


def main():
    print("[storage_cron] Starting storage cleanup via CLI...")
    result = storage_cleanup_service.execute_cleanup(trigger_source="cron_midnight_cli")
    print(f"[storage_cron] Completed: {result.get('message')}")
    print(
        f"Details: db_rows={result.get('db_rows_deleted')}, "
        f"files={result.get('files_deleted')}, "
        f"minio={result.get('minio_objects_deleted')}"
    )
    if result.get("errors"):
        print(f"Errors: {result.get('errors')}")


if __name__ == "__main__":
    main()
