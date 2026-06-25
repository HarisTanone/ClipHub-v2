"""Domain exceptions — Custom exception hierarchy for pipeline errors."""


class PipelineError(Exception):
    """Base exception for pipeline errors."""
    pass


class GeminiExhaustedError(PipelineError):
    """All retry attempts for Gemini API exhausted."""

    def __init__(self, last_error: str, status_code: int, elapsed_seconds: float):
        self.last_error = last_error
        self.status_code = status_code
        self.elapsed_seconds = elapsed_seconds
        super().__init__(
            f"Gemini API exhausted after {elapsed_seconds:.1f}s. "
            f"Last error (HTTP {status_code}): {last_error}"
        )


class GeminiNonTransientError(PipelineError):
    """Non-retryable Gemini API error (400, 401, 403)."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(
            f"Gemini non-transient error (HTTP {status_code}): {message}"
        )


class InsufficientResourcesError(PipelineError):
    """Pre-job resource check failed."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(
            f"Insufficient resources: {'; '.join(errors)}"
        )


class RateLimiterTimeoutError(PipelineError):
    """Semaphore acquisition timeout."""

    def __init__(self, wait_duration: float, max_timeout: float):
        self.wait_duration = wait_duration
        self.max_timeout = max_timeout
        super().__init__(
            f"Rate limiter timeout: waited {wait_duration:.1f}s "
            f"(max: {max_timeout:.1f}s)"
        )


class RateLimiterOverloadError(PipelineError):
    """Pending queue at capacity."""

    def __init__(self, max_pending: int = 50):
        self.max_pending = max_pending
        super().__init__(
            f"Rate limiter overloaded: pending queue full ({max_pending} requests)"
        )


class InvalidYouTubeURLError(PipelineError):
    """URL does not match known YouTube patterns."""

    def __init__(self, url: str):
        self.url = url
        super().__init__(
            f"Invalid YouTube URL: {url}"
        )


class QueueFullError(PipelineError):
    """Job queue at maximum capacity."""

    def __init__(self, max_depth: int = 50):
        self.max_depth = max_depth
        super().__init__(
            f"Job queue full: maximum {max_depth} pending jobs reached"
        )
