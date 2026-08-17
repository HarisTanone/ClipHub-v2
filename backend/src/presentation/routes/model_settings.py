"""Model Settings API routes — superadmin only.

Endpoints:
- GET  /api/settings/models       — Get all model settings
- PUT  /api/settings/models       — Bulk update model settings
- POST /api/settings/models/test  — Test model connectivity
- GET  /api/settings/models/available — List models from 9router
- POST /api/settings/models/test-all  — Test every model from 9router
"""
import json
import logging
from typing import Any, Optional

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


# ─── Response parsing helpers ─────────────────────────────────────────────────


def _stringify_content(content: Any) -> str:
    """Flatten content that may be a list of {text} parts or a plain string."""
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content or "")


def _extract_chat_response(resp: httpx.Response) -> tuple[bool, str, str, Optional[dict]]:
    """Robustly parse a /chat/completions response (JSON body or SSE stream).

    Returns ``(streamed, text, finish_reason, usage)``.

    Some 9router combos (reasoning models, e.g. ``ag/gemini-3.6-flash-high``)
    always stream and return ``Content-Type: text/event-stream`` even when
    ``stream`` is not requested. A naive ``resp.json()`` on that body raises
    ``JSONDecodeError: Expecting value: line 1 column 1 (char 0)``, so we
    fall back to decoding SSE ``data:`` chunks (and tolerate a JSON object
    followed by a trailing ``data: [DONE]`` marker).

    Raises ``ValueError`` with a human-readable message when nothing can be
    parsed, so the UI never shows a raw JSONDecodeError string.
    """
    text = resp.text or ""
    content_type = resp.headers.get("content-type", "")
    is_sse = "text/event-stream" in content_type

    # 1. Plain JSON body.
    if not is_sse:
        try:
            data = resp.json()
        except ValueError:
            data = None
        if isinstance(data, dict) and data.get("choices"):
            choice = data["choices"][0]
            message = choice.get("message") or {}
            content = message.get("content") or choice.get("text") or ""
            return (
                False,
                _stringify_content(content),
                str(choice.get("finish_reason") or ""),
                data.get("usage"),
            )

    # 2. SSE stream: concatenate delta chunks, keep finish_reason + usage.
    parts: list[str] = []
    finish_reason = ""
    usage: Optional[dict] = None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        choices = event.get("choices") or []
        if choices:
            choice = choices[0]
            delta = choice.get("delta") or {}
            content = (
                delta.get("content")
                or (choice.get("message") or {}).get("content")
                or choice.get("text")
            )
            if content:
                parts.append(_stringify_content(content))
            if choice.get("finish_reason"):
                finish_reason = str(choice.get("finish_reason"))
        if event.get("usage"):
            usage = event.get("usage")

    if parts or finish_reason:
        return True, "".join(parts).strip(), finish_reason, usage

    # 3. Tolerant raw decode: JSON object followed by a trailing SSE marker.
    try:
        data, _ = json.JSONDecoder().raw_decode(text.lstrip())
    except (ValueError, TypeError):
        data = None
    if isinstance(data, dict):
        if data.get("choices"):
            choice = data["choices"][0]
            message = choice.get("message") or {}
            content = message.get("content") or choice.get("text") or ""
            return (
                False,
                _stringify_content(content),
                str(choice.get("finish_reason") or ""),
                data.get("usage"),
            )
        raise ValueError(
            f"Response JSON tidak mengandung 'choices' "
            f"(HTTP {resp.status_code}, content-type: {content_type or 'unknown'}): "
            f"{text[:300]}"
        )

    if not text:
        raise ValueError(
            f"9router mengembalikan response kosong (HTTP {resp.status_code}, "
            f"content-type: {content_type or 'unknown'})"
        )
    raise ValueError(
        f"Response tidak bisa diparse sebagai JSON "
        f"(HTTP {resp.status_code}, content-type: {content_type or 'unknown'}): "
        f"{text[:300]}"
    )


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
                "error": resp.text[:500] or f"HTTP {resp.status_code}",
                "model": model,
                "base_url": base_url,
                "content_type": resp.headers.get("content-type", ""),
            }

        try:
            streamed, response_text, finish_reason, usage = _extract_chat_response(resp)
        except ValueError as e:
            # Never surface raw JSONDecodeError strings like
            # "Expecting value: line 1 column 1 (char 0)" to the user.
            return {
                "success": False,
                "error": str(e)[:500],
                "model": model,
                "base_url": base_url,
                "status_code": resp.status_code,
                "content_type": resp.headers.get("content-type", ""),
            }

        # A response with no content (e.g. finish_reason "length") is not a
        # successful connection — report it instead of showing "Connected".
        if not (finish_reason == "stop" or bool(response_text.strip())):
            return {
                "success": False,
                "error": (
                    f"Model merespon tapi tidak ada konten "
                    f"(finish_reason: {finish_reason or 'unknown'})"
                ),
                "model": model,
                "base_url": base_url,
                "streamed": streamed,
                "finish_reason": finish_reason,
                "status_code": resp.status_code,
                "content_type": resp.headers.get("content-type", ""),
            }

        return {
            "success": True,
            "model": model,
            "base_url": base_url,
            "response": response_text[:200],
            "streamed": streamed,
            "finish_reason": finish_reason,
            "usage": usage,
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
    Reports success or failure per model with latency and error info.
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
                # Reasoning models (e.g. ag/gemini-*) spend tokens on thinking;
                # give them the same headroom as the single-model test.
                "max_tokens": 50,
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
                    try:
                        streamed, content, finish_reason, _usage = _extract_chat_response(test_resp)
                    except ValueError as e:
                        results.append({
                            "model": model_id,
                            "status": "error",
                            "http_code": 200,
                            "error": str(e)[:200],
                            "latency": f"{latency:.2f}s" if latency else None,
                        })
                        continue
                    is_ok = finish_reason == "stop" or bool(content.strip())
                    results.append({
                        "model": model_id,
                        "status": "ok" if is_ok else "warning",
                        "http_code": 200,
                        "response": content[:50],
                        "streamed": streamed,
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
