"""CDNUploader — Unified wrapper around MinioService for S3/MinIO object storage."""
import logging
import os
from typing import Optional

from src.infrastructure.minio_service import get_minio_service

logger = logging.getLogger(__name__)


class CDNUploader:
    """Unified S3/MinIO storage uploader that delegates to MinioService."""

    def __init__(self):
        self._minio = get_minio_service()

    @property
    def enabled(self) -> bool:
        return self._minio.is_enabled and self._minio.is_configured

    async def upload(self, file_path: str, key: str) -> Optional[str]:
        """Upload to MinIO, return URL or None on failure."""
        if not self.enabled:
            return None
        if not os.path.exists(file_path):
            logger.error("cdn_file_not_found", extra={"path": file_path})
            return None

        try:
            bucket = self._minio.bucket
            self._minio.client.fput_object(bucket, key, file_path)
            cfg = self._minio._get_config()
            protocol = "https" if cfg["secure"] else "http"
            url = f"{protocol}://{cfg['endpoint']}/{bucket}/{key}"
            logger.info("cdn_upload_success", extra={"key": key, "url": url})
            return url
        except Exception as e:
            logger.warning(f"cdn_upload_failed: {e}")
            return None
