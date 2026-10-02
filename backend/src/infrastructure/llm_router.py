"""System-wide LLM router: Gemini-first failover chain across custom providers.

Chain logic (resolved fresh per call, cheap — one cached DB read):
- LLM_ROTATE_ALL = false -> [gemini] only
- LLM_ROTATE_ALL = true  -> [gemini] + enabled llm_providers rows (priority order)
- 9router stays as the final unconditional fallback (existing behaviour).

Gemini native path reuses GeminiKeyRotator (multi-key + cooldown). Custom
providers speak OpenAI-compatible /chat/completions via RouterClient.
"""
import logging
import time
from typing import Any, Optional

import httpx

from src.config import settings
from src.infrastructure import llm_provider_store
from src.infrastructure.nine_router_client import NineRouterError, NineRouterClient

logger = logging.getLogger(__name__)

# Errors that should move on to the next provider in the chain.
_TRANSIENT_MARKERS = ("429", "502", "503", "504", "overloaded", "rate limit", "quota", "timeout")


class RouterClient:
    """Minimal OpenAI-compatible chat client for one custom provider."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: int = 3000,
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        url = f"{self.base_url}/chat/completions"
        last_err = ""
        for attempt in range(2):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    if resp.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                        time.sleep(2)
                        continue
                    raise RouterClientError(last_err)
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    raise RouterClientError("response kosong: tidak ada choices")
                message = choices[0].get("message") or {}
                content = message.get("content") or choices[0].get("text") or ""
                if isinstance(content, list):
                    content = "".join(
                        str(p.get("text", "")) if isinstance(p, dict) else str(p)
                        for p in content
                    )
                if not content:
                    raise RouterClientError("response kosong: content tidak ada")
                return str(content)
            except httpx.TimeoutException as exc:
                last_err = f"timeout: {exc}"
                if attempt == 0:
                    continue
                raise RouterClientError(last_err)
            except httpx.HTTPError as exc:
                last_err = str(exc)
                if attempt == 0:
                    continue
                raise RouterClientError(last_err)
        raise RouterClientError(last_err or "request gagal")


class RouterClientError(RuntimeError):
    pass


def _get_gemini_keys() -> list[str]:
    """Gemini keys from system settings (.env fallback) — reuse rotator source."""
    try:
        from src.infrastructure.system_config_store import get_gemini_api_keys
        keys = get_gemini_api_keys()
        if keys:
            return keys
    except Exception:
        pass
    return settings.gemini_api_keys


def _resolve_gemini_models() -> tuple[str, str]:
    """(primary, fallback) model — DB setting menang, lalu .env, lalu default."""
    from src.infrastructure.system_config_store import get_system_setting

    primary = (
        str(get_system_setting("GEMINI_MODEL") or "").strip()
        or getattr(settings, "GEMINI_MODEL", "")
        or "gemini-3.7-flash"
    )
    fallback = (
        str(get_system_setting("GEMINI_FALLBACK_MODEL") or "").strip()
        or getattr(settings, "GEMINI_FALLBACK_MODEL", "")
        or primary
    )
    return primary, fallback


def _gemini_generate(messages: list[dict[str, str]], max_tokens: int) -> str:
    """Native Gemini call with the existing key rotator. Raises on failure.

    Model-level errors (model deprecated/not found) retry with the fallback
    model (GEMINI_FALLBACK_MODEL).
    """
    from google import genai
    from google.genai import types as genai_types

    from src.infrastructure.auth import get_gemini_key_rotator

    keys = _get_gemini_keys()
    if not keys:
        raise RouterClientError("GEMINI_API_KEY kosong — Gemini tidak dikonfigurasi")

    rotator = get_gemini_key_rotator()
    prompt_parts: list[str] = []
    system_prompt = ""
    for msg in messages:
        if msg.get("role") == "system":
            system_prompt = msg.get("content", "")
        else:
            prompt_parts.append(f"{msg.get('role', 'user')}: {msg.get('content', '')}")

    primary_model, fallback_model = _resolve_gemini_models()
    contents = "\n\n".join(prompt_parts)

    def _call_model(model_id: str) -> str:
        last_err = ""
        for key in rotator.get_available_keys() or keys:
            try:
                client = genai.Client(api_key=key)
                config: dict[str, Any] = {"max_output_tokens": max_tokens}
                if system_prompt:
                    config["system_instruction"] = system_prompt
                response = client.models.generate_content(
                    model=model_id,
                    contents=contents,
                    config=genai_types.GenerateContentConfig(**config),
                )
                text = (response.text or "").strip()
                if not text:
                    raise RouterClientError("Gemini response kosong")
                return text
            except RouterClientError:
                raise
            except Exception as exc:
                last_err = str(exc)
                if any(m in last_err.lower() for m in _TRANSIENT_MARKERS):
                    rotator.mark_rate_limited(key=key, retry_after=30.0)
                    continue
                raise RouterClientError(f"Gemini error: {last_err[:300]}")
        raise RouterClientError(f"Gemini gagal semua key [{model_id}]: {last_err[:300]}")

    try:
        return _call_model(primary_model)
    except RouterClientError as exc:
        # Model-level failure → retry with fallback model once.
        err = str(exc).lower()
        model_err = any(
            m in err
            for m in ("404", "not found", "not supported", "deprecated", "invalid model")
        )
        if fallback_model and fallback_model != primary_model and model_err:
            logger.warning(
                f"llm_router: Gemini model {primary_model} gagal ({str(exc)[:120]}), "
                f"fallback ke {fallback_model}"
            )
            return _call_model(fallback_model)
        raise


def get_llm_chain() -> list[dict[str, Any]]:
    """Resolve the active provider chain.

    Returns ordered entries:
      {"kind": "gemini"} or
      {"kind": "custom", "id", "name", "base_url", "api_key", "model"}
    """
    from src.infrastructure.system_config_store import get_system_setting

    rotate_all = bool(get_system_setting("LLM_ROTATE_ALL", False))
    chain: list[dict[str, Any]] = [{"kind": "gemini"}]
    if rotate_all:
        for p in llm_provider_store.get_enabled_providers():
            chain.append({
                "kind": "custom",
                "id": p["id"],
                "name": p["name"],
                "base_url": p["base_url"],
                "api_key": p["api_key"],
                "model": p["model"],
            })
    return chain


def route_chat(
    messages: list[dict[str, str]],
    max_tokens: int = 3000,
    temperature: Optional[float] = None,
    require_json: bool = False,
) -> str:
    """Route a chat completion through the failover chain.

    Tries each entry in order; first success wins. Final fallback: 9router
    (existing client, unconditional — preserves current behaviour when the
    chain is down entirely).
    """
    chain = get_llm_chain()
    errors: list[str] = []

    for entry in chain:
        try:
            if entry["kind"] == "gemini":
                return _gemini_generate(messages, max_tokens)
            client = RouterClient(
                base_url=entry["base_url"],
                api_key=entry["api_key"],
                model=entry["model"],
                timeout=int(getattr(settings, "NINE_ROUTER_TIMEOUT", 120) or 120),
            )
            return client.chat(messages, temperature=temperature, max_tokens=max_tokens)
        except (RouterClientError, NineRouterError) as exc:
            msg = f"{entry.get('name', entry['kind'])}: {str(exc)[:200]}"
            errors.append(msg)
            logger.warning(f"llm_router: {msg}")
            continue
        except Exception as exc:
            msg = f"{entry.get('name', entry['kind'])}: {str(exc)[:200]}"
            errors.append(msg)
            logger.warning(f"llm_router: unexpected {msg}")
            continue

    # Final fallback: 9router (unchanged legacy path). Not attempted when
    # empty base_url — the caller (NineRouterClient.chat) checks that and
    # raises NineRouterError, preserving the old unconfigured behaviour.
    try:
        legacy = NineRouterClient(bypass_router=True)
        if legacy.is_configured:
            return legacy.chat(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"} if require_json else None,
            )
    except Exception as exc:
        errors.append(f"9router: {str(exc)[:200]}")

    raise RouterClientError(
        "Semua LLM provider gagal: " + " | ".join(errors) if errors else "tidak ada provider"
    )
