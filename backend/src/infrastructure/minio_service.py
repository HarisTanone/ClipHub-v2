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
    """Handles video uploads to MinIO bucket with job-based folder structure.
    
    Dynamically resolves credentials from database (system_settings) with fallback to settings / .env.
    """

    def __init__(self):
        self._client: Optional[Minio] = None

    def reset_client(self) -> None:
        """Invalidate cached client so next call reloads credentials from database."""
        self._client = None
        logger.info("[minio] Client cache invalidated, will re-read settings on next access")

    def _get_config(self) -> dict:
        """Resolve MinIO settings dynamically from database (system_settings), falling back to settings / .env."""
        try:
            from src.infrastructure.system_config_store import get_system_setting
            endpoint = get_system_setting("MINIO_ENDPOINT") or getattr(settings, "MINIO_ENDPOINT", "") or "localhost:9000"
            access_key = get_system_setting("MINIO_ACCESS_KEY") or getattr(settings, "MINIO_ACCESS_KEY", "")
            secret_key = get_system_setting("MINIO_SECRET_KEY") or getattr(settings, "MINIO_SECRET_KEY", "")
            bucket = get_system_setting("MINIO_BUCKET") or getattr(settings, "MINIO_BUCKET", "") or "cliperhub"
            secure_val = get_system_setting("MINIO_SECURE")
            secure = secure_val if secure_val is not None and secure_val != "" else getattr(settings, "MINIO_SECURE", False)
            enabled_val = get_system_setting("MINIO_ENABLED")
            enabled = enabled_val if enabled_val is not None and enabled_val != "" else getattr(settings, "MINIO_ENABLED", True)
        except Exception:
            endpoint = getattr(settings, "MINIO_ENDPOINT", "") or "localhost:9000"
            access_key = getattr(settings, "MINIO_ACCESS_KEY", "")
            secret_key = getattr(settings, "MINIO_SECRET_KEY", "")
            bucket = getattr(settings, "MINIO_BUCKET", "") or "cliperhub"
            secure = getattr(settings, "MINIO_SECURE", False)
            enabled = getattr(settings, "MINIO_ENABLED", True)

        # Normalize endpoint (strip http:// or https:// if user entered URL)
        endpoint_clean = str(endpoint).strip()
        if endpoint_clean.startswith("http://"):
            endpoint_clean = endpoint_clean[len("http://"):]
        elif endpoint_clean.startswith("https://"):
            endpoint_clean = endpoint_clean[len("https://"):]
            secure = True
        endpoint_clean = endpoint_clean.rstrip("/")

        # Automatically translate known MinIO Web Console ports to S3 API ports:
        # e.g. Docker container console 9011 -> S3 API 9010
        # e.g. Standard default console 9001 -> S3 API 9000
        if endpoint_clean.endswith(":9011"):
            endpoint_clean = endpoint_clean[:-5] + ":9010"
        elif endpoint_clean.endswith(":9001"):
            endpoint_clean = endpoint_clean[:-5] + ":9000"

        return {
            "endpoint": endpoint_clean,
            "access_key": str(access_key).strip(),
            "secret_key": str(secret_key).strip(),
            "bucket": str(bucket).strip() or "cliperhub",
            "secure": bool(secure),
            "enabled": bool(enabled),
        }

    @property
    def bucket(self) -> str:
        return self._get_config()["bucket"]

    @property
    def _bucket(self) -> str:
        # backward compatibility for internal references
        return self.bucket

    @property
    def is_configured(self) -> bool:
        cfg = self._get_config()
        return bool(cfg["endpoint"] and cfg["access_key"] and cfg["secret_key"] and cfg["bucket"])

    @property
    def is_enabled(self) -> bool:
        return self._get_config()["enabled"]

    @property
    def client(self) -> Minio:
        cfg = self._get_config()
        if self._client is None or getattr(self, "_cached_config", None) != cfg:
            self._cached_config = cfg
            import urllib3
            http_client = urllib3.PoolManager(
                timeout=urllib3.Timeout(connect=5.0, read=30.0),
                retries=urllib3.Retry(total=2, backoff_factor=0.2),
            )

            self._client = Minio(
                cfg["endpoint"],
                access_key=cfg["access_key"],
                secret_key=cfg["secret_key"],
                secure=cfg["secure"],
                http_client=http_client,
            )

            # Ensure bucket exists
            try:
                if not self._client.bucket_exists(cfg["bucket"]):
                    self._client.make_bucket(cfg["bucket"])
                    logger.info(f"[minio] Created bucket: {cfg['bucket']}")
            except S3Error as e:
                logger.warning(f"[minio] Bucket check failed: {e}")
            except Exception as e:
                logger.warning(f"[minio] Bucket connection check failed: {e}")

        return self._client

    def test_connection(self) -> dict:
        """Test reachability and authentication to MinIO Object Storage."""
        self.reset_client()
        cfg = self._get_config()
        if not cfg["endpoint"]:
            return {"connected": False, "error": "Endpoint MinIO belum dikonfigurasi"}
        if not cfg["access_key"] or not cfg["secret_key"]:
            return {"connected": False, "error": "Access Key atau Secret Key MinIO belum diisi"}
        try:
            exists = self.client.bucket_exists(cfg["bucket"])
            return {
                "connected": True,
                "bucket_exists": exists,
                "bucket": cfg["bucket"],
                "endpoint": cfg["endpoint"],
                "secure": cfg["secure"],
                "enabled": cfg["enabled"],
            }
        except Exception as e:
            err_msg = str(e)
            if "S3 API Requests must be made to API port" in err_msg or (":9011" in cfg["endpoint"]):
                err_clean = (
                    f"Port yang digunakan ({cfg['endpoint']}) adalah port MinIO Web Console. "
                    "MinIO API memerlukan port S3 API (pada server ini port 9010). "
                    "Silakan ubah endpoint menjadi: 100.64.5.96:9010 (tanpa http://)"
                )
            elif "Connection timed out" in err_msg or "ConnectTimeoutError" in err_msg:
                err_clean = (
                    f"Koneksi ke MinIO ({cfg['endpoint']}) timed out. "
                    "Pastikan IP dan port dapat diakses dari server backend dan tidak terblokir firewall."
                )
            else:
                err_clean = err_msg

            logger.warning(f"[minio] test_connection failed: {err_clean}")
            return {
                "connected": False,
                "error": err_clean,
                "bucket": cfg["bucket"],
                "endpoint": cfg["endpoint"],
            }

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
                "bucket": "default",
                "size": 12345678,
                "url": "http://localhost:9000/default/job_abc123/clip_01_final.mp4",
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
            cfg = self._get_config()
            endpoint = cfg["endpoint"]
            secure = cfg["secure"]
            protocol = "https" if secure else "http"
            direct_url = f"{protocol}://{endpoint}/{self.bucket}/{object_name}"

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
            if not self.client.bucket_exists(self._bucket):
                logger.info(f"[minio] Bucket {self._bucket} does not exist.")
                return 0

            from minio.deleteobjects import DeleteObject

            objects = list(self.client.list_objects(self._bucket, recursive=True))
            if not objects:
                logger.info(f"[minio] Bucket {self._bucket} is already empty.")
                return 0

            delete_list = [DeleteObject(obj.object_name) for obj in objects if obj.object_name]
            errors = list(self.client.remove_objects(self._bucket, delete_list))
            error_names = {err.object_name for err in errors}
            deleted = len(delete_list) - len(error_names)
            if errors:
                for err in errors[:5]:
                    logger.warning(f"[minio] Delete object error for {err.object_name}: {err}")
            logger.info(f"[minio] Cleared {deleted} objects from bucket {self._bucket} (errors: {len(errors)})")
        except S3Error as e:
            logger.warning(f"[minio] Bucket clear S3 error: {e}")
            raise
        except Exception as e:
            logger.warning(f"[minio] Bucket clear failed: {e}")
            raise
        return deleted


# Singleton instance
_minio_service: Optional[MinioService] = None


def get_minio_service() -> MinioService:
    global _minio_service
    if _minio_service is None:
        _minio_service = MinioService()
    return _minio_service


def reset_minio_client() -> None:
    """Invalidate global singleton Minio client so settings reload from DB."""
    global _minio_service
    if _minio_service is not None:
        _minio_service.reset_client()
