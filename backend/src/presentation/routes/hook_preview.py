"""Native Hook preview endpoint — single unified entry for all 4 engines.

POST /api/hook-preview
  - Resolves canonical HookManifest from (preset, explicit config override)
  - Dispatches to NativeHookPreviewService (Remotion/HyperFrames/Skia/FFmpeg)
  - Returns a signed image URL + stable manifest hash for cache busting

GET /api/hook-preview/image/{cache_hash}
  - Serves the cached PNG artifact so <img src="..."> works in browser
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.config import settings
from src.infrastructure.hook_manifest import (
    HookManifestError,
    resolve_hook_preset,
)
from src.infrastructure.hook_preview import NativeHookPreviewService
from src.infrastructure.auth import decode_access_token
from src.presentation.auth_deps import CurrentUser, get_current_user

router = APIRouter(tags=["hook-preview"])
logger = logging.getLogger(__name__)

_PREVIEW_CACHE_DIR = os.path.join(settings.OUTPUT_DIR, "_hook_preview_cache")
_service: Optional[NativeHookPreviewService] = None


def _get_service() -> NativeHookPreviewService:
    global _service
    if _service is None:
        _service = NativeHookPreviewService(
            cache_dir=_PREVIEW_CACHE_DIR,
            font_dir=getattr(settings, "FONT_DIR", "assets/fonts"),
        )
    return _service


# ─── Request / Response models ───────────────────────────────────────────────

class HookPreviewRequest(BaseModel):
    """All parameters needed to resolve + render one Hook preview frame."""
    preset: Optional[str] = None
    config: dict = Field(default_factory=dict)
    text: str
    frame: int = 30


class HookPreviewResponse(BaseModel):
    success: bool = True
    image_url: str
    hash: str
    engine: str
    cache_hit: bool
    manifest: Optional[dict] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/hook-preview", response_model=HookPreviewResponse)
async def render_hook_preview(
    body: HookPreviewRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Resolve canonical Hook manifest then render a native still frame.

    The response image_url points to GET /api/hook-preview/image/{hash}.
    The frontend should poll this URL and display the image directly —
    no CSS simulation, no fallback to a different engine.
    """
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="Hook text tidak boleh kosong")

    try:
        manifest = resolve_hook_preset(
            user_id=getattr(user, "id", None),
            preset_slug=body.preset,
            explicit_override=body.config or None,
        )
    except HookManifestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    svc = _get_service()
    try:
        result = await svc.render(manifest, body.text, frame=body.frame)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("hook_preview_render_failed engine=%s err=%s", manifest.get("engine"), exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    cache_hash = result["hash"]
    return HookPreviewResponse(
        image_url=f"/api/hook-preview/image/{cache_hash}",
        hash=cache_hash,
        engine=result["engine"],
        cache_hit=result["cache_hit"],
        manifest=manifest,
    )


@router.get("/hook-preview/image/{cache_hash}")
async def serve_hook_preview_image(
    cache_hash: str,
    request: Request,
    token: str = Query(default=""),
):
    """Serve cached native Hook preview PNG artifact.

    Supports ?token= query-param auth so <img src="...?token=jwt"> works
    in browser contexts that cannot set Authorization headers.
    """
    authorization = request.headers.get("authorization", "")
    bearer = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if decode_access_token(bearer or token) is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if len(cache_hash) != 64 or any(char not in "0123456789abcdef" for char in cache_hash):
        raise HTTPException(status_code=400, detail="Invalid cache hash")
    path = os.path.join(_PREVIEW_CACHE_DIR, f"{cache_hash}.png")
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise HTTPException(status_code=404, detail="Preview artifact not found or expired")
    return FileResponse(path, media_type="image/png", filename=f"hook_preview_{cache_hash}.png")
