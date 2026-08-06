"""Model Settings API routes — superadmin only.

Endpoints:
- GET  /api/settings/models       — Get all model settings
- PUT  /api/settings/models       — Bulk update model settings
- POST /api/settings/models/test  — Test model connectivity
"""
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.infrastructure.model_settings_store import (
    get_all_model_settings,
    get_model_setting,
    bulk_set_model_settings,
    VALID_MODEL_KEYS,
)
from src.presentation.auth_deps import CurrentUser, require_superadmin

router = APIRouter(prefix="/settings/models", tags=["model-settings"])
logger = logging.getLogger(__name__)


# ─── Request/Response Models ──────────────────────────────────────────────────


class ModelSettingsUpdateRequest(BaseModel):
    settings: dict[str, str]  # key -> value


class ModelTestRequest(BaseModel):
    base_url: Optional[str] = None  # override for test
    api_key: Optional[str] = None
    model: Optional[str] = None
    prompt: str = "Say hello in one word."


# ─── GET /api/settings/models ─────────────────────────────────────────────────


@router.get("")
async def get_models_settings(user: CurrentUser = Depends(require_superadmin())):
    """Get all model settings (superadmin only)."""
    all_settings = get_all_model_settings()
    return {
        "success": True,
        "data": all_settings,
        "valid_keys": sorted(VALID_MODEL_KEYS),
    }


# ─── PUT /api/settings/models ─────────────────────────────────────────────────


@router.put("")
async def update_models_settings(
    body: ModelSettingsUpdateRequest,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Bulk update model settings (superadmin only)."""
    # Validate keys
    invalid_keys = set(body.settings.keys()) - VALID_MODEL_KEYS
    if invalid_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid setting keys: {sorted(invalid_keys)}",
        )

    count = bulk_set_model_settings(body.settings, user_id=user.id)
    return {
        "success": True,
        "updated": count,
        "message": f"{count} model setting(s) updated",
    }


# ─── POST /api/settings/models/test ──────────────────────────────────────────


@router.post("/test")
async def test_model_connection(
    body: ModelTestRequest,
    user: CurrentUser = Depends(require_superadmin()),
):
    """Test model connectivity by sending a simple chat completion request.

    Uses provided overrides or current DB settings.
    """
    base_url = (body.base_url or get_model_setting("NINE_ROUTER_BASE_URL") or "").rstrip("/")
    api_key = body.api_key if body.api_key is not None else get_model_setting("NINE_ROUTER_API_KEY")
    model = body.model or get_model_setting("NINE_ROUTER_MODEL") or "CliperHub"

    if not base_url:
        raise HTTPException(status_code=400, detail="base_url kosong, tidak bisa test")

    url = f"{base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": body.prompt}],
        "max_tokens": 50,
        "temperature": 0.1,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code >= 400:
            return {
                "success": False,
                "status_code": resp.status_code,
                "error": resp.text[:500],
                "model": model,
                "base_url": base_url,
            }

        data = resp.json()
        # Extract response text
        choices = data.get("choices", [])
        response_text = ""
        if choices:
            message = choices[0].get("message", {})
            response_text = message.get("content", "")

        return {
            "success": True,
            "model": model,
            "base_url": base_url,
            "response": response_text[:200],
            "usage": data.get("usage"),
            "latency_hint": f"{resp.elapsed.total_seconds():.2f}s" if hasattr(resp, "elapsed") else None,
        }
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "Request timeout (30s)",
            "model": model,
            "base_url": base_url,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)[:300],
            "model": model,
            "base_url": base_url,
        }


# ─── GET /api/settings/models/available ───────────────────────────────────────


@router.get("/available")
async def list_available_models(user: CurrentUser = Depends(require_superadmin())):
    """Query 9router /models endpoint to list available models."""
    base_url = (get_model_setting("NINE_ROUTER_BASE_URL") or "").rstrip("/")
    api_key = get_model_setting("NINE_ROUTER_API_KEY")

    if not base_url:
        raise HTTPException(status_code=400, detail="NINE_ROUTER_BASE_URL not configured")

    url = f"{base_url}/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code >= 400:
            return {"success": False, "error": resp.text[:300]}

        data = resp.json()
        models = data.get("data", [])
        return {
            "success": True,
            "models": [
                {"id": m.get("id"), "owned_by": m.get("owned_by", "")}
                for m in models
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


# ─── POST /api/settings/models/test-all ───────────────────────────────────────


@router.post("/test-all")
async def test_all_models(user: CurrentUser = Depends(require_superadmin())):
    """Test ALL available models from 9router — returns status per model.

    Fetches /models list, then sends a minimal chat completion to each one.
    Reports ✅ or ❌ per model with latency and error info.
    """
    base_url = (get_model_setting("NINE_ROUTER_BASE_URL") or "").rstrip("/")
    api_key = get_model_setting("NINE_ROUTER_API_KEY")

    if not base_url:
        raise HTTPException(status_code=400, detail="NINE_ROUTER_BASE_URL not configured")

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Step 1: Fetch available models
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base_url}/models", headers=headers)
        if resp.status_code >= 400:
            return {"success": False, "error": f"Failed to fetch /models: HTTP {resp.status_code}"}
        models_data = resp.json().get("data", [])
    except Exception as e:
        return {"success": False, "error": f"Failed to fetch /models: {str(e)[:200]}"}

    if not models_data:
        return {"success": True, "results": [], "message": "No models found on 9router"}

    # Step 2: Test each model
    results = []

    async with httpx.AsyncClient(timeout=30) as client:
        for m in models_data:
            model_id = m.get("id", "")
            if not model_id:
                continue

            payload = {
                "model": model_id,
                "messages": [{"role": "user", "content": "Reply with OK"}],
                "max_tokens": 5,
                "temperature": 0.0,
            }

            try:
                test_resp = await client.post(
                    f"{base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                latency = test_resp.elapsed.total_seconds() if hasattr(test_resp, "elapsed") else None

                if test_resp.status_code == 200:
                    body = test_resp.json()
                    choices = body.get("choices", [])
                    finish_reason = choices[0].get("finish_reason", "") if choices else ""
                    content = choices[0].get("message", {}).get("content", "") if choices else ""
                    is_ok = finish_reason == "stop" or bool(content.strip())
                    results.append({
                        "model": model_id,
                        "status": "ok" if is_ok else "warning",
                        "http_code": 200,
                        "response": content[:50],
                        "finish_reason": finish_reason,
                        "latency": f"{latency:.2f}s" if latency else None,
                    })
                else:
                    results.append({
                        "model": model_id,
                        "status": "error",
                        "http_code": test_resp.status_code,
                        "error": test_resp.text[:200],
                        "latency": f"{latency:.2f}s" if latency else None,
                    })
            except httpx.TimeoutException:
                results.append({
                    "model": model_id,
                    "status": "error",
                    "http_code": None,
                    "error": "Timeout (30s)",
                    "latency": None,
                })
            except Exception as e:
                results.append({
                    "model": model_id,
                    "status": "error",
                    "http_code": None,
                    "error": str(e)[:200],
                    "latency": None,
                })

    ok_count = sum(1 for r in results if r["status"] == "ok")
    return {
        "success": True,
        "total": len(results),
        "ok": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
    }
