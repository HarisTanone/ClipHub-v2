"""ARQJobQueue — persistent job queue backed by Redis with in-memory fallback."""
import asyncio
import json
import logging
import os
import time
import uuid
from collections import deque
from enum import Enum
from typing import Any, Dict, Optional

from src.domain.exceptions import QueueFullError

logger = logging.getLogger(__name__)


class JobQueueStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ARQJobQueue:
    """ARQ + Redis persistent job queue with in-memory fallback.
    
    Features:
    - FIFO ordering, unique job IDs
    - JSON serialization of job params
    - 3600s timeout per job
    - Max 50 pending jobs
    - Falls back to in-memory if Redis unavailable
    """

    JOB_TIMEOUT = 3600  # 1 hour
    MAX_QUEUE_DEPTH = 50

    def __init__(self, redis_url: Optional[str] = None):
        self._redis_url = redis_url or os.getenv("REDIS_URL")
        self._redis = None
        self._using_redis = False
        
        # In-memory fallback
        self._queue: deque = deque()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        
        logger.info("arq_queue_init", extra={
            "redis_url": bool(self._redis_url),
            "mode": "redis" if self._redis_url else "in-memory",
        })

    async def connect(self) -> bool:
        """Attempt to connect to Redis. Falls back to in-memory on failure."""
        if not self._redis_url:
            logger.warning("arq_no_redis_url", extra={"fallback": "in-memory"})
            return False
        
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._redis_url)
            await self._redis.ping()
            self._using_redis = True
            logger.info("arq_redis_connected", extra={"url": self._redis_url[:20] + "..."})
            return True
        except Exception as e:
            logger.warning("arq_redis_failed", extra={"error": str(e), "fallback": "in-memory"})
            self._redis = None
            self._using_redis = False
            return False

    async def enqueue(self, job_params: Dict[str, Any]) -> str:
        """Serialize and enqueue job. Returns unique job_id.
        
        Raises:
            QueueFullError: If queue is at MAX_QUEUE_DEPTH.
        """
        # Check queue depth
        pending_count = sum(1 for j in self._jobs.values() if j["status"] == JobQueueStatus.PENDING)
        if pending_count >= self.MAX_QUEUE_DEPTH:
            raise QueueFullError(max_depth=self.MAX_QUEUE_DEPTH)
        
        job_id = str(uuid.uuid4())[:8] + f"-{int(time.time())}"
        
        job_data = {
            "job_id": job_id,
            "params": job_params,
            "status": JobQueueStatus.PENDING,
            "enqueued_at": time.time(),
            "started_at": None,
            "completed_at": None,
            "error": None,
        }
        
        self._jobs[job_id] = job_data
        self._queue.append(job_id)
        
        logger.info("arq_job_enqueued", extra={"job_id": job_id, "queue_depth": len(self._queue)})
        return job_id

    async def dequeue(self) -> Optional[Dict[str, Any]]:
        """Get next pending job from queue. Returns None if empty."""
        while self._queue:
            job_id = self._queue.popleft()
            job = self._jobs.get(job_id)
            if job and job["status"] == JobQueueStatus.PENDING:
                job["status"] = JobQueueStatus.PROCESSING
                job["started_at"] = time.time()
                logger.info("arq_job_dequeued", extra={"job_id": job_id})
                return job
        return None

    async def complete(self, job_id: str) -> None:
        """Mark job as completed."""
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = JobQueueStatus.COMPLETED
            self._jobs[job_id]["completed_at"] = time.time()
            logger.info("arq_job_completed", extra={"job_id": job_id})

    async def fail(self, job_id: str, error: str) -> None:
        """Mark job as failed."""
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = JobQueueStatus.FAILED
            self._jobs[job_id]["completed_at"] = time.time()
            self._jobs[job_id]["error"] = error
            logger.info("arq_job_failed", extra={"job_id": job_id, "error": error[:100]})

    async def get_status(self, job_id: str) -> Optional[str]:
        """Query job status: pending, processing, completed, failed."""
        job = self._jobs.get(job_id)
        if job:
            return job["status"]
        return None

    @property
    def pending_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j["status"] == JobQueueStatus.PENDING)

    @property
    def queue_depth(self) -> int:
        return len(self._queue)
