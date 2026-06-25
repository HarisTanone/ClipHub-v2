"""GeminiRetryHandler — Exponential backoff with jitter for transient Gemini errors."""
import asyncio
import logging
import random
import time
from typing import Any, Callable, Awaitable

from src.domain.exceptions import GeminiExhaustedError, GeminiNonTransientError

logger = logging.getLogger(__name__)


class GeminiRetryHandler:
    """Exponential backoff with jitter for transient Gemini errors.

    Retries transient errors (429, 500, 503) up to 5 times.
    Immediately raises for non-transient errors (400, 401, 403).
    """

    MAX_RETRIES = 5
    BASE_DELAY = 2.0  # seconds
    MAX_JITTER = 1.0  # seconds

    TRANSIENT_CODES = {429, 500, 503}
    NON_TRANSIENT_CODES = {400, 401, 403}

    async def execute_with_retry(self, api_call: Callable[[], Awaitable[Any]]) -> Any:
        """Execute API call with retry logic.

        Args:
            api_call: Async callable that makes the Gemini API request.
                      Should raise an exception with a `status_code` attribute on failure.

        Returns:
            The result of the successful API call.

        Raises:
            GeminiExhaustedError: All retry attempts exhausted.
            GeminiNonTransientError: Non-retryable error encountered.
        """
        start_time = time.time()
        last_error: str = ""
        last_status_code: int = 0

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return await api_call()
            except Exception as e:
                status_code = getattr(e, "status_code", 0)
                error_message = str(e)
                last_error = error_message
                last_status_code = status_code

                # Non-transient: fail immediately
                if status_code in self.NON_TRANSIENT_CODES:
                    raise GeminiNonTransientError(
                        status_code=status_code,
                        message=error_message,
                    )

                # Calculate backoff delay
                delay = self._calculate_delay(attempt)

                logger.warning(
                    "gemini_retry",
                    extra={
                        "attempt": attempt,
                        "max_retries": self.MAX_RETRIES,
                        "status_code": status_code,
                        "error_type": type(e).__name__,
                        "wait_seconds": round(delay, 2),
                    },
                )

                # Last attempt exhausted — raise
                if attempt == self.MAX_RETRIES:
                    elapsed = time.time() - start_time
                    raise GeminiExhaustedError(
                        last_error=last_error,
                        status_code=last_status_code,
                        elapsed_seconds=elapsed,
                    )

                await asyncio.sleep(delay)

        # Safety fallback (should not reach here)
        elapsed = time.time() - start_time
        raise GeminiExhaustedError(
            last_error=last_error,
            status_code=last_status_code,
            elapsed_seconds=elapsed,
        )

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter.

        Delay = 2^attempt + random(0, 1)
        For attempts 1-5: 2, 4, 8, 16, 32 seconds + 0-1s jitter
        """
        base = self.BASE_DELAY ** attempt  # 2^1=2, 2^2=4, 2^3=8, 2^4=16, 2^5=32
        jitter = random.uniform(0, self.MAX_JITTER)
        return base + jitter
