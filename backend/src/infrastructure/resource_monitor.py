"""ResourceMonitor — checks disk/RAM before job start, monitors during execution."""
import asyncio
import logging
import os
import shutil
import time
from typing import Optional

from src.domain.entities import ResourceStatus, ResourceSummary
from src.domain.exceptions import InsufficientResourcesError

logger = logging.getLogger(__name__)


class ResourceMonitor:
    """Checks disk/RAM before job start and monitors during execution.

    Reads thresholds from environment variables:
    - MIN_DISK_GB (default: 5)
    - MIN_RAM_GB (default: 2)
    """

    DEFAULT_MIN_DISK_GB = 5.0
    DEFAULT_MIN_RAM_GB = 2.0

    def __init__(self, output_path: Optional[str] = None, min_disk_gb: Optional[float] = None, min_ram_gb: Optional[float] = None):
        """Initialize with optional output path for disk checks.

        Args:
            output_path: Directory to check disk space on. Defaults to cwd.
            min_disk_gb: Override minimum disk threshold. Reads from settings/env if None.
            min_ram_gb: Override minimum RAM threshold. Reads from settings/env if None.
        """
        self._output_path = output_path or os.getcwd()
        if min_disk_gb is not None:
            self._min_disk_gb = min_disk_gb
        elif min_ram_gb is not None and min_disk_gb is None:
            # Only ram override provided, read disk from settings
            try:
                from src.config import settings
                self._min_disk_gb = getattr(settings, "MIN_DISK_GB", self.DEFAULT_MIN_DISK_GB)
            except Exception:
                self._min_disk_gb = self._parse_threshold("MIN_DISK_GB", self.DEFAULT_MIN_DISK_GB)
        else:
            try:
                from src.config import settings
                self._min_disk_gb = getattr(settings, "MIN_DISK_GB", self.DEFAULT_MIN_DISK_GB)
            except Exception:
                self._min_disk_gb = self._parse_threshold("MIN_DISK_GB", self.DEFAULT_MIN_DISK_GB)
        
        if min_ram_gb is not None:
            self._min_ram_gb = min_ram_gb
        else:
            try:
                from src.config import settings
                self._min_ram_gb = getattr(settings, "MIN_RAM_GB", self.DEFAULT_MIN_RAM_GB)
            except Exception:
                self._min_ram_gb = self._parse_threshold("MIN_RAM_GB", self.DEFAULT_MIN_RAM_GB)

    def check_resources(self) -> ResourceStatus:
        """Pre-job resource validation.

        Checks available disk space and RAM against configured thresholds.

        Returns:
            ResourceStatus with current values and sufficiency flag.
        """
        errors = []

        # Check disk space
        try:
            disk_usage = shutil.disk_usage(self._output_path)
            disk_free_gb = disk_usage.free / (1024 ** 3)
        except OSError as e:
            disk_free_gb = 0.0
            errors.append(f"Cannot check disk space: {e}")

        # Check RAM — use psutil if available, otherwise fallback
        ram_available_gb = self._get_available_ram_gb()
        cpu_percent = self._get_cpu_percent()

        # Validate against thresholds
        if disk_free_gb < self._min_disk_gb:
            errors.append(
                f"Insufficient disk space: {disk_free_gb:.1f} GB available, "
                f"minimum {self._min_disk_gb:.1f} GB required"
            )

        if ram_available_gb < self._min_ram_gb:
            errors.append(
                f"Insufficient RAM: {ram_available_gb:.1f} GB available, "
                f"minimum {self._min_ram_gb:.1f} GB required"
            )

        is_sufficient = len(errors) == 0

        status = ResourceStatus(
            disk_free_gb=round(disk_free_gb, 2),
            ram_available_gb=round(ram_available_gb, 2),
            cpu_percent=round(cpu_percent, 1),
            is_sufficient=is_sufficient,
            errors=errors,
        )

        if is_sufficient:
            logger.info(
                "resource_check_passed",
                extra={
                    "disk_free_gb": status.disk_free_gb,
                    "ram_available_gb": status.ram_available_gb,
                },
            )
        else:
            logger.warning(
                "resource_check_failed",
                extra={"errors": errors},
            )

        return status

    def check_and_raise(self) -> ResourceStatus:
        """Check resources and raise InsufficientResourcesError if not sufficient."""
        status = self.check_resources()
        if not status.is_sufficient:
            raise InsufficientResourcesError(errors=status.errors)
        return status

    def _get_available_ram_gb(self) -> float:
        """Get available RAM in GB using psutil or fallback."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            return mem.available / (1024 ** 3)
        except ImportError:
            # Fallback: read from /proc/meminfo on Linux or sysctl on macOS
            return self._fallback_ram_gb()

    def _get_cpu_percent(self) -> float:
        """Get current CPU usage percent."""
        try:
            import psutil
            return psutil.cpu_percent(interval=0.1)
        except ImportError:
            return 0.0

    def _fallback_ram_gb(self) -> float:
        """Fallback RAM check without psutil."""
        try:
            import subprocess
            # macOS
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                total_bytes = int(result.stdout.strip())
                # Approximate available as 50% of total (conservative)
                return (total_bytes * 0.5) / (1024 ** 3)
        except Exception:
            pass
        return 4.0  # Safe default assumption

    @staticmethod
    def _parse_threshold(env_var: str, default: float) -> float:
        """Parse threshold from env var with fallback to default.

        Invalid values (non-numeric, non-positive) use the default.
        """
        val = os.getenv(env_var)
        if val is None:
            return default
        try:
            n = float(val)
            if n <= 0:
                return default
            return n
        except (ValueError, TypeError):
            return default

    async def monitor_loop(self, job_id: str, cancel_flag: asyncio.Event) -> ResourceSummary:
        """Background monitoring during job execution (30s intervals).

        Samples CPU, RAM, disk. Warns on high RAM. Signals cancel on critical disk.
        Self-restarts on exception within 5s.

        Args:
            job_id: Job being monitored.
            cancel_flag: Shared asyncio.Event — set this to signal job cancellation.

        Returns:
            ResourceSummary with peak values and totals.
        """
        ram_warn_pct = self._parse_threshold("MONITOR_RAM_WARN_PERCENT", 85.0)
        disk_critical_gb = self._parse_threshold("MONITOR_DISK_CRITICAL_GB", 2.0)

        peak_ram = 0.0
        peak_cpu = 0.0
        min_disk = float("inf")
        samples = 0
        start_time = time.time()

        while not cancel_flag.is_set():
            try:
                status = self.check_resources()
                samples += 1

                # Track peaks
                ram_pct = self._get_ram_percent()
                cpu_pct = status.cpu_percent
                peak_ram = max(peak_ram, ram_pct)
                peak_cpu = max(peak_cpu, cpu_pct)
                min_disk = min(min_disk, status.disk_free_gb)

                logger.info(
                    "resource_sample",
                    extra={
                        "job_id": job_id,
                        "cpu_percent": cpu_pct,
                        "ram_percent": ram_pct,
                        "ram_available_gb": status.ram_available_gb,
                        "disk_free_gb": status.disk_free_gb,
                    },
                )

                # High RAM warning
                if ram_pct > ram_warn_pct:
                    logger.warning(
                        "high_memory_pressure",
                        extra={
                            "job_id": job_id,
                            "ram_percent": ram_pct,
                            "threshold": ram_warn_pct,
                        },
                    )

                # Critical disk — signal cancellation
                if status.disk_free_gb < disk_critical_gb:
                    logger.critical(
                        "disk_critical",
                        extra={
                            "job_id": job_id,
                            "disk_free_gb": status.disk_free_gb,
                            "threshold_gb": disk_critical_gb,
                        },
                    )
                    cancel_flag.set()
                    break

                await asyncio.sleep(30)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "monitor_loop_error",
                    extra={"job_id": job_id, "error": str(e)},
                )
                await asyncio.sleep(5)  # Self-restart after 5s

        duration = time.time() - start_time
        summary = ResourceSummary(
            job_id=job_id,
            peak_ram_percent=round(peak_ram, 1),
            peak_cpu_percent=round(peak_cpu, 1),
            min_disk_free_gb=round(min_disk, 2) if min_disk != float("inf") else 0.0,
            total_duration_seconds=round(duration, 1),
            samples_collected=samples,
        )

        logger.info(
            "resource_monitor_summary",
            extra={
                "job_id": job_id,
                "peak_ram_percent": summary.peak_ram_percent,
                "peak_cpu_percent": summary.peak_cpu_percent,
                "min_disk_free_gb": summary.min_disk_free_gb,
                "total_duration": summary.total_duration_seconds,
                "samples": summary.samples_collected,
            },
        )

        return summary

    def _get_ram_percent(self) -> float:
        """Get RAM usage percentage."""
        try:
            import psutil
            return psutil.virtual_memory().percent
        except ImportError:
            return 0.0
