"""GeminiRateLimiter — Global asyncio Semaphore limiting concurrent Gemini calls."""
import asyncio
import logging
import os
import time
from typing import Any, Callable, Awaitable

from src.domain.exceptions import RateLimiterTimeoutError, RateLimiterOverloadError

logger = logging.getLogger(__name__)


class GeminiRateLimiter:
    """Global asyncio Semaphore limiting concurrent Gemini calls.

    Features:
    - Max 3 concurrent Gemini API calls (configurable)
    - Max 50 pending requests in queue
    - Configurable timeout for semaphore acquisition
    - Singleton pattern
    - FIFO ordering via asyncio.Semaphore
    - Guaranteed release in finally block
    """

    _instance = None
    _lock = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        max_concurrent: int = 3,
        max_pending: int = 50,
        timeout: float | None = None,
    ):
        if self._initialized:
            return
        self._initialized = True

        self._max_concurrent = max_concurrent
        self._max_pending = max_pending
        self._timeout = timeout or float(
            os.getenv("GEMINI_RATE_LIMIT_TIMEOUT", "120")
        )
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._pending_count = 0

        logger.info(
            "rate_limiter_init",
            extra={
                "max_concurrent": max_concurrent,
                "max_pending": max_pending,
                "timeout": self._timeout,
            },
        )

    @classmethod
    def reset(cls):
        """Reset singleton instance (for testing)."""
        cls._instance = None

    @property
    def pending_count(self) -> int:
        return self._pending_count

    @property
    def available_permits(self) -> int:
        return self._semaphore._value

    async def acquire(self) -> None:
        """Acquire a permit from the semaphore.

        Raises:
            RateLimiterOverloadError: If pending queue is full.
            RateLimiterTimeoutError: If timeout expires while waiting.
        """
        if self._pending_count >= self._max_pending:
            raise RateLimiterOverloadError(max_pending=self._max_pending)

        self._pending_count += 1
        start = time.time()

        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            self._pending_count -= 1
            elapsed = time.time() - start
            raise RateLimiterTimeoutError(
                wait_duration=elapsed,
                max_timeout=self._timeout,
            )

    def release(self) -> None:
        """Release a permit back to the semaphore."""
        self._pending_count -= 1
        self._semaphore.release()

    async def execute(self, api_call: Callable[[], Awaitable[Any]]) -> Any:
        """Execute an API call with rate limiting.

        Acquires permit, executes call, releases permit in finally block.

        Args:
            api_call: Async callable to execute.

        Returns:
            Result of the API call.
        """
        await self.acquire()
        try:
            return await api_call()
        finally:
            self.release()
