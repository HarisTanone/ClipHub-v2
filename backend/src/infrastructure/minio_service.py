"""MinIO object storage service — upload clips to bucket, generate presigned URLs."""
import logging
import os
from io import BytesIO
from typing import Optional

from minio import Minio
from minio.error import S3Error

from src.config import settings

logger = logging.getLogger(__name__)


class MinioService:
    """Handles video uploads to MinIO bucket with job-based folder structure."""

    def __init__(self):
        self._client: Optional[Minio] = None
        self._bucket = getattr(settings, "MINIO_BUCKET", "cliperhub")

    @property
    def client(self) -> Minio:
        if self._client is None:
            endpoint = getattr(settings, "MINIO_ENDPOINT", "103.103.22.205:9000")
            access_key = getattr(settings, "MINIO_ACCESS_KEY", "admin")
            secret_key = getattr(settings, "MINIO_SECRET_KEY", "admin1234")
            secure = getattr(settings, "MINIO_SECURE", False)

            self._client = Minio(
                endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure,
            )

            # Ensure bucket exists
            try:
                if not self._client.bucket_exists(self._bucket):
                    self._client.make_bucket(self._bucket)
                    logger.info(f"[minio] Created bucket: {self._bucket}")
            except S3Error as e:
                logger.warning(f"[minio] Bucket check failed: {e}")

        return self._client

    def ensure_job_folder(self, job_id: str) -> str:
        """Create a folder marker for job (MinIO uses prefix-based 'folders').
        Returns the folder prefix string."""
        prefix = f"job_{job_id}/"
        # MinIO doesn't need explicit folder creation — prefix is enough
        return prefix

    def upload_clip(
        self,
        job_id: str,
        clip_rank: int,
        file_path: str,
        content_type: str = "video/mp4",
        on_progress: Optional[object] = None,
    ) -> dict:
        """Upload a clip file to MinIO under job folder.

        Returns:
            {
                "object_name": "job_abc123/clip_01_final.mp4",
                "bucket": "cliperhub",
                "size": 12345678,
                "url": "http://103.103.22.205:9000/cliperhub/job_abc123/clip_01_final.mp4",
                "presigned_url": "http://...(7 days expiry)",
            }
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Clip file not found: {file_path}")

        filename = os.path.basename(file_path)
        object_name = f"job_{job_id}/{filename}"
        file_size = os.path.getsize(file_path)

        logger.info(f"[minio] Uploading {object_name} ({file_size / 1024 / 1024:.1f}MB)")

        try:
            # Upload with progress tracking
            self.client.fput_object(
                self._bucket,
                object_name,
                file_path,
                content_type=content_type,
            )

            # Generate presigned URL (7 days)
            from datetime import timedelta
            presigned_url = self.client.presigned_get_object(
                self._bucket,
                object_name,
                expires=timedelta(days=7),
            )

            # Direct URL (public if bucket policy allows)
            endpoint = getattr(settings, "MINIO_ENDPOINT", "103.103.22.205:9000")
            secure = getattr(settings, "MINIO_SECURE", False)
            protocol = "https" if secure else "http"
            direct_url = f"{protocol}://{endpoint}/{self._bucket}/{object_name}"

            result = {
                "object_name": object_name,
                "bucket": self._bucket,
                "size": file_size,
                "url": direct_url,
                "presigned_url": presigned_url,
                "filename": filename,
            }

            logger.info(f"[minio] Upload complete: {object_name}")
            return result

        except S3Error as e:
            logger.error(f"[minio] Upload failed: {e}")
            raise

    def get_presigned_url(self, object_name: str, expires_days: int = 7) -> str:
        """Get a presigned download URL for an object."""
        from datetime import timedelta
        return self.client.presigned_get_object(
            self._bucket,
            object_name,
            expires=timedelta(days=expires_days),
        )

    def list_job_files(self, job_id: str) -> list[dict]:
        """List all files in a job folder."""
        prefix = f"job_{job_id}/"
        objects = []
        try:
            for obj in self.client.list_objects(self._bucket, prefix=prefix):
                objects.append({
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                })
        except S3Error as e:
            logger.warning(f"[minio] List failed for {prefix}: {e}")
        return objects

    def delete_job_folder(self, job_id: str) -> int:
        """Delete all files in a job folder. Returns count deleted."""
        prefix = f"job_{job_id}/"
        deleted = 0
        try:
            objects = list(self.client.list_objects(self._bucket, prefix=prefix, recursive=True))
            for obj in objects:
                if obj.object_name:
                    self.client.remove_object(self._bucket, obj.object_name)
                    deleted += 1
            logger.info(f"[minio] Deleted {deleted} objects from {prefix}")
        except S3Error as e:
            logger.warning(f"[minio] Delete failed for {prefix}: {e}")
        return deleted

    def clear_bucket(self) -> int:
        """Delete ALL objects in the bucket (e.g. 'cliperhub'). Returns count deleted."""
        deleted = 0
        try:
            objects = list(self.client.list_objects(self._bucket, recursive=True))
            for obj in objects:
                if obj.object_name:
                    self.client.remove_object(self._bucket, obj.object_name)
                    deleted += 1
            logger.info(f"[minio] Cleared {deleted} objects from bucket {self._bucket}")
        except S3Error as e:
            logger.warning(f"[minio] Bucket clear failed: {e}")
        return deleted


# Singleton instance
_minio_service: Optional[MinioService] = None


def get_minio_service() -> MinioService:
    global _minio_service
    if _minio_service is None:
        _minio_service = MinioService()
    return _minio_service
