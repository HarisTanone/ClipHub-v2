"""CDNUploader — S3-compatible upload with retry and fallback to local serving."""
import asyncio
import logging
import os
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)


class CDNUploader:
    """S3-compatible upload (MinIO/AWS S3) with retry and fallback to local serving."""
    MAX_RETRIES = 3
    BACKOFF_BASE = 2.0

    def __init__(self):
        self._enabled = settings.CDN_ENABLED
        self._endpoint = settings.CDN_ENDPOINT
        self._bucket = settings.CDN_BUCKET
        self._access_key = settings.CDN_ACCESS_KEY
        self._secret_key = settings.CDN_SECRET_KEY

        if self._enabled:
            missing = []
            if not self._endpoint:
                missing.append("CDN_ENDPOINT")
            if not self._bucket:
                missing.append("CDN_BUCKET")
            if not self._access_key:
                missing.append("CDN_ACCESS_KEY")
            if not self._secret_key:
                missing.append("CDN_SECRET_KEY")
            if missing:
                logger.warning("cdn_disabled_missing_vars", extra={"missing": missing})
                self._enabled = False
            else:
                logger.info("cdn_enabled", extra={"endpoint": self._endpoint, "bucket": self._bucket})

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def upload(self, file_path: str, key: str) -> Optional[str]:
        """Upload to CDN, return URL or None on failure (fallback to local)."""
        if not self._enabled:
            return None
        if not os.path.exists(file_path):
            logger.error("cdn_file_not_found", extra={"path": file_path})
            return None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                url = await self._do_upload(file_path, key)
                logger.info("cdn_upload_success", extra={"key": key, "attempt": attempt})
                return url
            except Exception as e:
                delay = self.BACKOFF_BASE ** attempt
                logger.warning("cdn_upload_retry", extra={
                    "attempt": attempt, "error": str(e), "delay": delay
                })
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(delay)

        logger.error("cdn_upload_exhausted", extra={"key": key, "fallback": "local"})
        return None

    async def _do_upload(self, file_path: str, key: str) -> str:
        """Perform actual S3 upload via aiobotocore."""
        try:
            import aiobotocore
            from aiobotocore.session import AioSession
            session = AioSession()
            async with session.create_client(
                's3',
                endpoint_url=self._endpoint,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
            ) as client:
                with open(file_path, 'rb') as f:
                    await client.put_object(Bucket=self._bucket, Key=key, Body=f)
                return f"{self._endpoint}/{self._bucket}/{key}"
        except ImportError:
            raise RuntimeError("aiobotocore not installed")
