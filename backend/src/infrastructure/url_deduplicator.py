"""URLDeduplicator — extracts video_id, checks cache and active jobs."""
import logging
import re
from typing import Optional

from src.domain.entities import CachedJobResult
from src.domain.exceptions import InvalidYouTubeURLError

logger = logging.getLogger(__name__)


# YouTube URL patterns that can contain a video_id
YOUTUBE_PATTERNS = [
    # Standard watch URL: youtube.com/watch?v=VIDEO_ID
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})"),
    # Short URL: youtu.be/VIDEO_ID
    re.compile(r"(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})"),
    # Shorts: youtube.com/shorts/VIDEO_ID
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})"),
    # Embed: youtube.com/embed/VIDEO_ID
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})"),
    # Live: youtube.com/live/VIDEO_ID
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/live/([a-zA-Z0-9_-]{11})"),
]


class URLDeduplicator:
    """Extracts video_id, checks cache and active jobs for deduplication.

    Attributes:
        CACHE_TTL_DAYS: Days to consider cached results valid.
    """

    CACHE_TTL_DAYS = 7

    def __init__(self, db_session=None):
        """Initialize with optional database session for cache checks.

        Args:
            db_session: Async database session (SQLAlchemy or similar).
        """
        self._db = db_session

    def extract_video_id(self, url: str) -> str:
        """Extract 11-char YouTube video_id from URL.

        Args:
            url: YouTube URL in any supported format.

        Returns:
            11-character video_id string.

        Raises:
            InvalidYouTubeURLError: If URL doesn't match known patterns.
        """
        if not url or not isinstance(url, str):
            raise InvalidYouTubeURLError(url=str(url))

        url = url.strip()

        for pattern in YOUTUBE_PATTERNS:
            match = pattern.search(url)
            if match:
                video_id = match.group(1)
                logger.debug("video_id_extracted", extra={"url": url, "video_id": video_id})
                return video_id

        raise InvalidYouTubeURLError(url=url)

    async def check_cache(self, video_id: str) -> Optional[CachedJobResult]:
        """Check DB for completed job within TTL.

        Args:
            video_id: 11-char YouTube video identifier.

        Returns:
            CachedJobResult if found, None otherwise.
        """
        from src.infrastructure.db_connection import get_dict_connection
        from datetime import datetime, timedelta

        try:
            conn = get_dict_connection()
            cur = conn.cursor()
            cutoff = (datetime.utcnow() - timedelta(days=self.CACHE_TTL_DAYS)).isoformat()
            cur.execute(
                """SELECT job_id, status, created_at FROM jobs
                WHERE video_id = ? AND status = 'completed' AND created_at > ?
                ORDER BY created_at DESC LIMIT 1""",
                (video_id, cutoff),
            )
            row = cur.fetchone()
            conn.close()

            if row:
                logger.info("cache_hit", extra={"video_id": video_id, "job_id": row["job_id"]})
                return CachedJobResult(
                    job_id=row["job_id"],
                    status="completed",
                    output_path="",
                    caption_response=None,
                    requested_at=row["created_at"] or "",
                    is_cached=True,
                )
        except Exception as e:
            logger.warning(f"cache_check_error: {e}")

        return None

    async def check_active(self, video_id: str) -> Optional[dict]:
        """Check for pending/processing jobs with same video_id.

        Args:
            video_id: 11-char YouTube video identifier.

        Returns:
            Dict with job_id and status if active job exists, None otherwise.
        """
        from src.infrastructure.db_connection import get_dict_connection

        try:
            conn = get_dict_connection()
            cur = conn.cursor()
            cur.execute(
                """SELECT job_id, status FROM jobs
                WHERE video_id = ? AND status NOT IN ('completed', 'failed', 'timeout')
                ORDER BY created_at DESC LIMIT 1""",
                (video_id,),
            )
            row = cur.fetchone()
            conn.close()

            if row:
                logger.info("active_job_found", extra={"video_id": video_id, "job_id": row["job_id"]})
                return {"job_id": row["job_id"], "status": row["status"]}
        except Exception as e:
            logger.warning(f"active_check_error: {e}")

        return None

    async def check_dedup(self, url: str, force_reprocess: bool = False) -> Optional[CachedJobResult]:
        """Full deduplication check — extract video_id, check cache and active jobs.

        Args:
            url: YouTube URL.
            force_reprocess: If True, bypass cache and active checks.

        Returns:
            CachedJobResult if cached/active result found, None to proceed with new job.

        Raises:
            InvalidYouTubeURLError: If URL format is invalid.
        """
        video_id = self.extract_video_id(url)

        if force_reprocess:
            logger.info("dedup_bypass", extra={"video_id": video_id, "reason": "force_reprocess"})
            return None

        # Check for cached result
        cached = await self.check_cache(video_id)
        if cached:
            logger.info("dedup_cache_hit", extra={"video_id": video_id, "job_id": cached.job_id})
            return cached

        # Check for active job
        active = await self.check_active(video_id)
        if active:
            logger.info("dedup_active_job", extra={"video_id": video_id, "active_job": active})
            # Return as cached result with active status
            return CachedJobResult(
                job_id=active.get("job_id", ""),
                status=active.get("status", "processing"),
                output_path="",
                caption_response=None,
                requested_at="",
                is_cached=False,
            )

        return None
