"""Monitoring routes — dashboard metrics and health check endpoints."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.infrastructure.monitoring_dashboard import MonitoringDashboard

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

# Global instance (would be injected in production)
_dashboard = MonitoringDashboard()


@router.get("/dashboard")
async def get_dashboard_metrics():
    """Get aggregated monitoring metrics."""
    metrics = await _dashboard.get_metrics()
    return {
        "success": True,
        "data": {
            "active_jobs": metrics.active_jobs,
            "queued_jobs": metrics.queued_jobs,
            "completed_jobs_24h": metrics.completed_jobs_24h,
            "failed_jobs_24h": metrics.failed_jobs_24h,
            "average_processing_time_seconds": metrics.average_processing_time_seconds,
            "cpu_percent": metrics.cpu_percent,
            "ram_percent": metrics.ram_percent,
            "disk_free_gb": metrics.disk_free_gb,
            "step_durations": metrics.step_durations,
        },
    }


@router.get("/health")
async def health_check():
    """Health check — returns 200 if healthy, 503 if degraded."""
    status = await _dashboard.health_check()

    response_data = {
        "healthy": status.healthy,
        "mysql": status.details.get("mysql", "unknown"),
        "redis": status.details.get("redis", "unknown"),
    }

    if status.healthy:
        return JSONResponse(content=response_data, status_code=200)
    else:
        return JSONResponse(content=response_data, status_code=503)
