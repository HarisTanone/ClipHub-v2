"""MonitoringDashboard — aggregates metrics for monitoring endpoints."""
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from src.domain.entities import DashboardMetrics, ScaleRecommendation

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """Health check result."""
    healthy: bool
    mysql_connected: bool
    redis_connected: bool
    details: Dict[str, str] = field(default_factory=dict)


class MonitoringDashboard:
    """Aggregates metrics for /monitoring/dashboard endpoint.
    
    Collects queue stats, job stats, resource usage, and per-step durations.
    """

    def __init__(self, job_queue=None, db_session=None):
        self._queue = job_queue
        self._db = db_session

    async def get_metrics(self) -> DashboardMetrics:
        """Collect queue stats, job stats, resource usage, per-step durations."""
        # System resources
        cpu_percent = self._get_cpu_percent()
        ram_percent = self._get_ram_percent()
        disk_free_gb = self._get_disk_free_gb()

        # Queue stats (from job_queue if available)
        active_jobs = 0
        queued_jobs = 0
        if self._queue:
            active_jobs = getattr(self._queue, 'processing_count', 0)
            queued_jobs = getattr(self._queue, 'pending_count', 0)

        # Query DB for real 24h stats
        completed_24h = 0
        failed_24h = 0
        avg_time = 0.0

        try:
            from src.infrastructure.db_connection import get_dict_connection
            conn = get_dict_connection()
            cur = conn.cursor()

            # Active jobs (non-terminal)
            cur.execute("SELECT COUNT(*) as cnt FROM jobs WHERE status NOT IN ('completed', 'failed', 'timeout')")
            row = cur.fetchone()
            active_jobs = max(active_jobs, row["cnt"] if row else 0)

            # Completed in last 24h
            cur.execute("SELECT COUNT(*) as cnt FROM jobs WHERE status = 'completed' AND updated_at > datetime('now', '-1 day')")
            row = cur.fetchone()
            completed_24h = row["cnt"] if row else 0

            # Failed in last 24h
            cur.execute("SELECT COUNT(*) as cnt FROM jobs WHERE status IN ('failed', 'timeout') AND updated_at > datetime('now', '-1 day')")
            row = cur.fetchone()
            failed_24h = row["cnt"] if row else 0

            # Average processing time (completed jobs in last 24h)
            cur.execute("""
                SELECT AVG(julianday(updated_at) - julianday(created_at)) * 86400 as avg_sec
                FROM jobs WHERE status = 'completed' AND updated_at > datetime('now', '-1 day')
            """)
            row = cur.fetchone()
            avg_time = round(row["avg_sec"], 1) if row and row["avg_sec"] else 0.0

            conn.close()
        except Exception as e:
            logger.warning(f"monitoring_db_error: {e}")

        step_durations: Dict[str, float] = {}

        return DashboardMetrics(
            active_jobs=active_jobs,
            queued_jobs=queued_jobs,
            completed_jobs_24h=completed_24h,
            failed_jobs_24h=failed_24h,
            average_processing_time_seconds=avg_time,
            cpu_percent=cpu_percent,
            ram_percent=ram_percent,
            disk_free_gb=disk_free_gb,
            step_durations=step_durations,
            scaling=None,
        )

    async def health_check(self) -> HealthStatus:
        """Check SQLite connectivity and system resources."""
        db_ok = await self._check_sqlite()

        return HealthStatus(
            healthy=db_ok,
            mysql_connected=db_ok,  # kept for interface compatibility
            redis_connected=True,    # no Redis required in local mode
            details={
                "sqlite": "connected" if db_ok else "unreachable",
                "mode": os.getenv("PIPELINE_ENV", "local"),
            },
        )

    async def _check_sqlite(self) -> bool:
        """Check SQLite database connectivity."""
        try:
            from src.infrastructure.db_connection import get_dict_connection
            conn = get_dict_connection()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            conn.close()
            return True
        except Exception:
            return False

    async def _check_mysql(self) -> bool:
        """Legacy: MySQL check (not used in SQLite mode)."""
        return False

    async def _check_redis(self) -> bool:
        """Legacy: Redis check (not required in local mode)."""
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            return True  # Redis optional in local mode
        try:
            import redis.asyncio as aioredis
            import asyncio
            r = aioredis.from_url(redis_url)
            await asyncio.wait_for(r.ping(), timeout=3.0)
            await r.close()
            return True
        except Exception:
            return False

    def _get_cpu_percent(self) -> float:
        try:
            import psutil
            return psutil.cpu_percent(interval=0.1)
        except ImportError:
            return 0.0

    def _get_ram_percent(self) -> float:
        try:
            import psutil
            return psutil.virtual_memory().percent
        except ImportError:
            return 0.0

    def _get_disk_free_gb(self) -> float:
        try:
            usage = shutil.disk_usage(os.getcwd())
            return round(usage.free / (1024 ** 3), 2)
        except OSError:
            return 0.0
