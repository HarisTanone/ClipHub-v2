"""HyperFrames HTTP client — optional polish layer (NOT hook/subtitle).

Hook + subtitle stay on Remotion. This adapter only calls the
hyperframes-renderer service for template+JSON compositions
(e.g. lower_third_v1 from visual_entities / object_overlay_events).
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional
from urllib.parse import quote

import aiohttp
from aiohttp import ClientTimeout

from src.config import settings

logger = logging.getLogger(__name__)


def _abs_file_url(path: str) -> str:
    p = os.path.abspath(str(path or "").strip())
    if not p or not os.path.exists(p):
        return ""
    # file:// with encoded spaces; keep path absolute for headless render
    return "file://" + quote(p, safe="/:")


def events_from_clip_ai(
    *,
    object_overlay_events: list[dict] | None = None,
    visual_entities: list[dict] | None = None,
    clip_hook: str = "",
    clip_duration: float = 0.0,
    max_events: int = 4,
) -> list[dict[str, Any]]:
    """Map AI object cards / visual entities → HF lower-third events.

    Prefers resolved stock cards (label + local thumb). Falls back to VE
    text-only when overlay bake skipped. Distinct labels only.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(
        *,
        label: str,
        sub: str,
        start: float,
        end: float,
        thumb: str = "",
    ) -> None:
        lab = " ".join(str(label or "").split())
        if not lab or len(lab) < 2:
            return
        low = lab.lower()
        if low in seen:
            return
        if clip_duration > 0 and start >= clip_duration - 0.4:
            return
        seen.add(low)
        en = max(start + 0.8, float(end))
        if clip_duration > 0:
            en = min(en, clip_duration - 0.05)
        out.append({
            "label": lab[:80],
            "sub": " ".join(str(sub or "").split())[:120],
            "start": round(max(0.0, float(start)), 3),
            "end": round(en, 3),
            "thumb": thumb or "",
            "word": lab,
        })

    for e in object_overlay_events or []:
        if not isinstance(e, dict):
            continue
        label = str(e.get("label") or e.get("word") or "").strip()
        sub = str(
            e.get("query_en") or e.get("query_id") or e.get("sub") or clip_hook or ""
        ).strip()
        try:
            start = float(e.get("at_time", e.get("start", 0)) or 0)
            dur = float(e.get("duration", 2.4) or 2.4)
        except (TypeError, ValueError):
            start, dur = 0.0, 2.4
        thumb = ""
        ip = str(e.get("image_path") or e.get("thumb") or e.get("image_url") or "")
        if ip and not ip.startswith("http"):
            thumb = _abs_file_url(ip)
        elif ip.startswith("http"):
            thumb = ip
        _add(label=label, sub=sub, start=start, end=start + dur, thumb=thumb)
        if len(out) >= max_events:
            return out

    if out:
        return out

    # Text-only from AI visual entities (no stock bake yet)
    for ve in visual_entities or []:
        if not isinstance(ve, dict):
            continue
        label = str(ve.get("label") or ve.get("word") or "").strip()
        sub = str(ve.get("query_en") or ve.get("query_id") or clip_hook or "").strip()
        try:
            start = float(ve.get("start", 0) or 0)
            end = float(ve.get("end", start + 2.4) or start + 2.4)
        except (TypeError, ValueError):
            continue
        if end <= start:
            end = start + 2.4
        _add(label=label, sub=sub, start=start, end=end)
        if len(out) >= max_events:
            break
    return out


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
        if bool(getattr(settings, "HYPERFRAMES_ENABLED", False)):
            return True
        try:
            from src.infrastructure.hyperframes_config import get_hyperframes_config
            return bool(get_hyperframes_config(None).get("enabled"))
        except Exception:
            return False

    def effective_config(self, user_id: int | None = None) -> dict[str, Any]:
        cfg = {
            "enabled": self.enabled,
            "default_template": getattr(settings, "HYPERFRAMES_DEFAULT_TEMPLATE", "lower_third_v1"),
            "server_url": self.base_url,
            "timeout_sec": int(getattr(settings, "HYPERFRAMES_TIMEOUT", 180) or 180),
        }
        try:
            from src.infrastructure.hyperframes_config import get_hyperframes_config
            db = get_hyperframes_config(user_id)
            if db.get("default_template"):
                cfg["default_template"] = db["default_template"]
            if db.get("server_url"):
                cfg["server_url"] = str(db["server_url"]).rstrip("/")
                self.base_url = cfg["server_url"]
            if db.get("timeout_sec"):
                cfg["timeout_sec"] = int(db["timeout_sec"])
            # env OR db enables polish
            cfg["enabled"] = bool(cfg["enabled"] or db.get("enabled"))
        except Exception:
            pass
        return cfg

    async def _session_get(self) -> aiohttp.ClientSession:
        # Recreate if closed or bound to a dead loop (multi asyncio.run / tests)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        dead = False
        if self._session is not None and not self._session.closed:
            try:
                sess_loop = getattr(self._session, "_loop", None)
                if sess_loop is not None and (sess_loop.is_closed() or sess_loop is not loop):
                    dead = True
            except Exception:
                dead = True
        if self._session is None or self._session.closed or dead:
            if self._session is not None and not self._session.closed:
                try:
                    await self._session.close()
                except Exception:
                    pass
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

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
        user_id: int | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Apply polish/hook/sub template over base video. Returns server JSON.

        force=True bypasses HYPERFRAMES_ENABLED (user explicitly chose HF engine).
        """
        cfg = self.effective_config(user_id)
        if not cfg.get("enabled") and not force:
            # Still allow when template is hook/sub (engine choice) — force flag
            # from call sites that already decided HF path.
            tpl_peek = str(template or "")
            if not (tpl_peek.startswith("hook_") or tpl_peek.startswith("sub_")):
                return {"ok": False, "skipped": True, "reason": "HYPERFRAMES_ENABLED=false"}

        base = os.path.abspath(base_video)
        out = os.path.abspath(output_path)
        if not os.path.exists(base):
            return {"ok": False, "error": f"base missing: {base}"}

        tpl = template or cfg.get("default_template") or "lower_third_v1"
        payload = {
            "template": tpl,
            "base_video": base,
            "base_src": base,
            "events": events or [],
            "duration": float(duration or 0),
            "out_path": out,
            "job_id": str(job_id),
            "clip_id": str(clip_id),
        }
        session = await self._session_get()
        try:
            async with session.post(f"{self.base_url}/render", json=payload) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400 or not data.get("ok"):
                    logger.warning(
                        "hyperframes_render_failed status=%s body=%s",
                        resp.status,
                        data,
                    )
                return data if isinstance(data, dict) else {"ok": False, "error": str(data)}
        except Exception as e:
            logger.warning("hyperframes_render_error: %s", e)
            return {"ok": False, "error": str(e)}


_adapter: Optional[HyperFramesAdapter] = None


def get_hyperframes_adapter() -> HyperFramesAdapter:
    global _adapter
    if _adapter is None:
        _adapter = HyperFramesAdapter()
    return _adapter
