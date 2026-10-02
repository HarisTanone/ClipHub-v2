"""LLM provider registry API routes — superadmin only.

Endpoints:
- GET    /api/settings/llm-providers          — list (masked keys)
- POST   /api/settings/llm-providers          — add provider
- PUT    /api/settings/llm-providers/{id}     — update provider
- DELETE /api/settings/llm-providers/{id}     — remove provider
- POST   /api/settings/llm-providers/{id}/validate — probe endpoint + list models
- PUT    /api/settings/llm-providers/mode     — LLM_ROTATE_ALL toggle
- GET    /api/settings/llm-providers/hermes   — Hermes config.yaml + env snippet
"""
import logging
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.infrastructure import llm_provider_store as store
from src.presentation.auth_deps import CurrentUser, require_superadmin

router = APIRouter(prefix="/settings/llm-providers", tags=["llm-providers"])
logger = logging.getLogger(__name__)


class ProviderCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    base_url: str = Field(min_length=1)
    api_key: str = ""
    model: str = ""
    enabled: bool = False
    priority: int = 100


class ProviderUpdateRequest(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None


class RotateModeRequest(BaseModel):
    rotate_all: bool


def _probe_models(base_url: str, api_key: str) -> dict[str, Any]:
    """GET {base}/models against an OpenAI-compatible endpoint."""
    url = f"{base_url.rstrip('/')}/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = httpx.get(url, headers=headers, timeout=15)
    except httpx.TimeoutException:
        return {"valid": False, "error": "timeout (15s)"}
    except Exception as e:
        return {"valid": False, "error": str(e)[:300]}

    if resp.status_code >= 400:
        detail = resp.text[:300]
        if resp.status_code in (401, 403):
            detail = "API key ditolak (401/403)"
        return {"valid": False, "error": f"HTTP {resp.status_code}: {detail}"}

    try:
        data = resp.json()
    except ValueError:
        return {"valid": False, "error": "response bukan JSON valid"}

    models = data.get("data") or data.get("models") or []
    ids = []
    for m in models:
        if isinstance(m, dict):
            mid = m.get("id") or m.get("name") or ""
        else:
            mid = str(m)
        mid = str(mid).strip()
        if mid:
            ids.append(mid)
    if not ids:
        return {"valid": False, "error": "endpoint valid tapi tidak ada model"}
    return {"valid": True, "models": ids}


@router.get("")
async def list_providers(user: CurrentUser = Depends(require_superadmin())):
    providers = store.list_providers(include_disabled=True)
    return {
        "success": True,
        "data": providers,
        "rotate_all": _get_rotate_all(),
    }


def _get_rotate_all() -> bool:
    from src.infrastructure.system_config_store import get_system_setting
    return bool(get_system_setting("LLM_ROTATE_ALL", False))


@router.post("")
async def add_provider(
    body: ProviderCreateRequest,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Add provider. `validate=auto` — probes endpoint, stores model count status."""
    if body.base_url and not body.base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="base_url harus http(s) URL")

    existing = [p for p in store.list_providers() if p["name"] == body.name.strip()]
    if existing:
        raise HTTPException(status_code=409, detail=f"Provider '{body.name}' sudah ada")

    provider_id = store.add_provider(
        name=body.name,
        base_url=body.base_url,
        api_key=body.api_key,
        model=body.model,
        enabled=body.enabled,
        priority=body.priority,
        user_id=user.id,
    )
    if provider_id is None:
        raise HTTPException(status_code=500, detail="Gagal menyimpan provider")

    # Auto-validate on add: probe /models and record the status + model list.
    probe = _probe_models(body.base_url, body.api_key)
    if probe["valid"]:
        store.set_provider_status(
            provider_id, f"ok: {len(probe.get('models', []))} model"
        )
    else:
        store.set_provider_status(provider_id, f"error: {probe.get('error', '?')[:200]}")

    return {
        "success": True,
        "id": provider_id,
        "validation": probe,
    }


@router.put("/mode")
async def set_rotate_mode(
    body: RotateModeRequest,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Toggle LLM_ROTATE_ALL: false = Gemini only, true = rotate semua."""
    from src.infrastructure.system_config_store import set_system_setting
    ok = set_system_setting("LLM_ROTATE_ALL", body.rotate_all, user_id=user.id)
    if not ok:
        raise HTTPException(status_code=500, detail="Gagal menyimpan mode rotasi")
    return {"success": True, "rotate_all": body.rotate_all}


@router.put("/{provider_id}")
async def update_provider(
    provider_id: int,
    body: ProviderUpdateRequest,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Update provider. api_key yang dikirim = masked value diabaikan."""
    row = store.get_provider(provider_id)
    if not row:
        raise HTTPException(status_code=404, detail="Provider tidak ditemukan")

    masked = store.mask_key(row["api_key"])
    new_key = body.api_key
    if new_key is not None and new_key.strip() and new_key.strip() != masked:
        pass  # real key — update
    else:
        new_key = None  # masked unchanged / empty → keep existing

    ok = store.update_provider(
        provider_id,
        name=body.name,
        base_url=body.base_url,
        api_key=new_key,
        model=body.model,
        enabled=body.enabled,
        priority=body.priority,
        user_id=user.id,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Gagal update provider")
    return {"success": True}


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: int,
    user: CurrentUser = Depends(require_superadmin()),
):
    if not store.get_provider(provider_id):
        raise HTTPException(status_code=404, detail="Provider tidak ditemukan")
    store.delete_provider(provider_id)
    return {"success": True}


@router.post("/{provider_id}/validate")
async def validate_provider(
    provider_id: int,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Probe endpoint + list all available models (for the model picker)."""
    row = store.get_provider(provider_id)
    if not row:
        raise HTTPException(status_code=404, detail="Provider tidak ditemukan")

    probe = _probe_models(row["base_url"], row["api_key"])
    if probe["valid"]:
        store.set_provider_status(provider_id, f"ok: {len(probe['models'])} model")
    else:
        store.set_provider_status(provider_id, f"error: {probe.get('error', '?')[:200]}")
    return {"success": probe["valid"], **probe}


@router.get("/hermes")
async def hermes_export(user: CurrentUser = Depends(require_superadmin())):
    """Generate Hermes config.yaml + .env snippet from the current chain.

    Output mirrors what scripts/sync-hermes-config.sh deploys, but model section
    is driven by the DB (Gemini native provider + fallback chain).
    """
    from src.infrastructure.system_config_store import get_system_setting

    rotate_all = bool(get_system_setting("LLM_ROTATE_ALL", False))
    providers = store.list_providers(include_disabled=False) if rotate_all else []
    gemini_key_env = "GEMINI_API_KEY"

    lines = [
        "# AutoCliper Hermes profile — generated by /api/settings/llm-providers/hermes",
        "# Synced by: scripts/sync-hermes-config.sh",
        "# Secrets live in $HERMES_HOME/.env (never commit).",
        "",
        "model:",
        "  default: gemini-3.7-flash",
        "  provider: gemini",
        "",
        "providers: {}",
    ]
    if rotate_all and providers:
        lines.append("fallback_providers:")
        for p in providers:
            model = p["model"] or "<set-model>"
            lines.append(f"  - provider: custom:{p['name']}")
            lines.append(f"    model: {model}")
            lines.append(f"    base_url: {p['base_url']}")
            lines.append(f"    key_env: LLM_{p['name'].upper().replace('-', '_').replace(' ', '_')}_KEY")
        lines.append("")
    else:
        lines += ["fallback_providers: []", ""]

    return {
        "success": True,
        "config_yaml": "\n".join(lines),
        "env_keys": [gemini_key_env],
        "custom_env_keys": [
            f"LLM_{p['name'].upper().replace('-', '_').replace(' ', '_')}_KEY"
            for p in providers
        ],
    }
