"""StepTimer — Context manager untuk logging durasi setiap step pipeline."""
import logging
import time

logger = logging.getLogger(__name__)


class StepTimer:
    """Async context manager untuk track durasi step.

    Usage:
        async with StepTimer(job_id, "download"):
            await download_video(...)
    """

    def __init__(self, job_id: str, step_name: str):
        self.job_id = job_id
        self.step = step_name
        self.start = 0.0
        self.elapsed = 0.0

    async def __aenter__(self):
        self.start = time.time()
        logger.info(f"[{self.job_id}] ▶ {self.step}")
        return self

    async def __aexit__(self, *args):
        self.elapsed = time.time() - self.start
        logger.info(f"[{self.job_id}] ✓ {self.step} — {self.elapsed:.1f}s")
