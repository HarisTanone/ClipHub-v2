"""AlertingService — Telegram bot alerts for queue backlog."""
import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)


class AlertingService:
    """Telegram bot alerts for queue backlog.
    
    Checks queue depth periodically and sends Telegram alerts when
    the queue exceeds configured thresholds.
    """

    COOLDOWN = 300  # 5 minutes
    CHECK_INTERVAL = 60  # seconds
    RETRY_DELAY = 30  # seconds

    def __init__(self, job_queue=None):
        self._queue = job_queue
        self._threshold = int(os.getenv("ALERT_QUEUE_THRESHOLD", "10"))
        self._telegram_token = os.getenv("ALERT_TELEGRAM_TOKEN")
        self._telegram_chat_id = os.getenv("ALERT_TELEGRAM_CHAT_ID")
        self._last_alert_time: float = 0
        self._last_alert_depth: int = 0
        self._enabled = bool(self._telegram_token and self._telegram_chat_id)
        
        if not self._enabled:
            logger.info("alerting_disabled", extra={"reason": "missing telegram credentials"})

    async def check_and_alert(self, queue_depth: int) -> None:
        """Evaluate thresholds and send Telegram alert if needed.
        
        Args:
            queue_depth: Current number of pending jobs in queue.
        """
        # Warning log at threshold
        if queue_depth >= self._threshold:
            logger.warning("queue_backlog_warning", extra={
                "queue_depth": queue_depth,
                "threshold": self._threshold,
            })

        # Telegram alert at 2x threshold
        if queue_depth >= self._threshold * 2:
            if self._should_alert(queue_depth):
                await self._send_alert(queue_depth)

    def _should_alert(self, queue_depth: int) -> bool:
        """Check if we should send an alert (cooldown + increase check)."""
        now = time.time()
        
        # Cooldown check
        if now - self._last_alert_time < self.COOLDOWN:
            # Only re-alert if queue increased by 5+
            if queue_depth - self._last_alert_depth < 5:
                return False
        
        return True

    async def _send_alert(self, queue_depth: int) -> None:
        """Send Telegram alert with retry."""
        if not self._enabled:
            return

        message = (
            f"⚠️ AutoCliper Queue Alert\n"
            f"Queue depth: {queue_depth} (threshold: {self._threshold})\n"
            f"Action required: check pipeline health"
        )

        success = await self._send_telegram(message)
        if not success:
            logger.warning("alert_delivery_failed", extra={"retry_in": self.RETRY_DELAY})
            await asyncio.sleep(self.RETRY_DELAY)
            success = await self._send_telegram(message)
            if not success:
                logger.error("alert_delivery_failed_final", extra={"queue_depth": queue_depth})
                return

        self._last_alert_time = time.time()
        self._last_alert_depth = queue_depth
        logger.info("alert_sent", extra={"queue_depth": queue_depth})

    async def _send_telegram(self, message: str) -> bool:
        """Send message via Telegram Bot API."""
        try:
            import httpx
            url = f"https://api.telegram.org/bot{self._telegram_token}/sendMessage"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json={
                    "chat_id": self._telegram_chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                })
                return resp.status_code == 200
        except Exception as e:
            logger.error("telegram_send_error", extra={"error": str(e)})
            return False

    async def monitor_loop(self, get_queue_depth) -> None:
        """Background loop checking queue depth every 60s.
        
        Args:
            get_queue_depth: Callable that returns current queue depth.
        """
        while True:
            try:
                depth = get_queue_depth()
                await self.check_and_alert(depth)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("alerting_loop_error", extra={"error": str(e)})
            
            await asyncio.sleep(self.CHECK_INTERVAL)
