"""HyperFrames HTTP client — optional polish layer (NOT hook/subtitle).

Hook + subtitle stay on Remotion. This adapter only calls the
hyperframes-renderer service for template+JSON compositions
(e.g. lower_third_v1 from visual_entities / object_overlay_events).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import aiohttp
from aiohttp import ClientTimeout

from src.config import settings

logger = logging.getLogger(__name__)


class HyperFramesAdapter:
    def __init__(self) -> None:
        self.base_url = (
            getattr(settings, "HYPERFRAMES_SERVER_URL", None)
            or f"http://127.0.0.1:{getattr(settings, 'HYPERFRAMES_SERVER_PORT', 3003)}"
        ).rstrip("/")
        self.timeout = ClientTimeout(
            total=int(getattr(settings, "HYPERFRAMES_TIMEOUT", 180) or 180)
        )
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def enabled(self) -> bool:
        return bool(getattr(settings, "HYPERFRAMES_ENABLED", False))

    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def health(self) -> dict[str, Any]:
        try:
            session = await self._session_get()
            async with session.get(f"{self.base_url}/health") as resp:
                data = await resp.json(content_type=None)
                data["http_status"] = resp.status
                return data
        except Exception as e:
            return {"status": "down", "error": str(e), "url": self.base_url}

    async def list_templates(self) -> list[str]:
        try:
            session = await self._session_get()
            async with session.get(f"{self.base_url}/templates") as resp:
                data = await resp.json(content_type=None)
                return list(data.get("templates") or [])
        except Exception:
            return []

    async def render_polish(
        self,
        *,
        base_video: str,
        events: list[dict],
        output_path: str,
        template: str | None = None,
        duration: float = 0,
        job_id: str = "job",
        clip_id: str | int = "0",
    ) -> dict[str, Any]:
        """Apply polish template over base video. Returns server JSON."""
        if not self.enabled:
            return {"ok": False, "skipped": True, "reason": "HYPERFRAMES_ENABLED=false"}

        tpl = template or getattr(settings, "HYPERFRAMES_DEFAULT_TEMPLATE", "lower_third_v1")
        payload = {
            "template": tpl,
            "base_video": base_video,
            "base_src": base_video,
            "events": events or [],
            "duration": duration,
            "out_path": output_path,
            "job_id": str(job_id),
            "clip_id": str(clip_id),
        }
        session = await self._session_get()
        async with session.post(f"{self.base_url}/render", json=payload) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400 or not data.get("ok"):
                logger.warning(
                    "hyperframes_render_failed status=%s body=%s",
                    resp.status,
                    data,
                )
            return data


_adapter: Optional[HyperFramesAdapter] = None


def get_hyperframes_adapter() -> HyperFramesAdapter:
    global _adapter
    if _adapter is None:
        _adapter = HyperFramesAdapter()
    return _adapter
