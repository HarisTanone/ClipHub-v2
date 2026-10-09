"""9router OpenAI-compatible chat completions client.

The OpenAI-compatible gateway (9router) decides which combo/model to use based
on its own config. We do NOT force a specific upstream model from the backend —
that's the gateway's job. The `model` parameter is kept for backwards
compatibility but is treated as a *hint*: when set to one of the backend's
9router aliases (NINE_ROUTER_MODEL, NINE_ROUTER_PASS1_MODEL, etc.) we resolve
it to the actual model name configured in the panel; otherwise we let 9router
route on its default combo.
"""
from __future__ import annotations

import logging
import json
import time
from typing import Any, Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


import re


def normalize_nine_router_base_url(url: str) -> str:
    """Normalize 9router base URL ensuring it points to /v1 and strips web UI /dashboard."""
    cleaned = (url or "").strip().rstrip("/")
    if not cleaned:
        return ""
    # Strip web UI /dashboard paths (e.g. /dashboard, /dashboard/models, /dashboard/combos)
    cleaned = re.sub(r"/dashboard(?:/.*)?$", "", cleaned).rstrip("/")
    if not cleaned.endswith("/v1") and not cleaned.endswith("/chat/completions"):
        cleaned = f"{cleaned}/v1"
    return cleaned


class NineRouterError(RuntimeError):
    """Raised when the 9router API cannot return a usable response."""


class NineRouterClient:
    """Small sync client for OpenAI-compatible /chat/completions routers."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        bypass_router: bool = False,
    ):
        raw_url = base_url or settings.get_nine_router("NINE_ROUTER_BASE_URL") or settings.NINE_ROUTER_BASE_URL
        self.base_url = normalize_nine_router_base_url(raw_url)
        self.api_key = api_key if api_key is not None else (settings.get_nine_router("NINE_ROUTER_API_KEY") or settings.NINE_ROUTER_API_KEY)
        self.timeout = int(timeout or settings.get_nine_router("NINE_ROUTER_TIMEOUT") or settings.NINE_ROUTER_TIMEOUT)
        self.max_retries = int(max_retries or settings.get_nine_router("NINE_ROUTER_MAX_RETRIES") or settings.NINE_ROUTER_MAX_RETRIES)
        # When True, this client is used *directly* against 9router without
        # being wrapped by llm_router (which would add another hop).
        # Kept for compatibility with llm_router.route_chat.
        self._bypass_router = bypass_router

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 3000,
        response_format: Optional[dict[str, Any]] = None,
    ) -> str:
        """Call 9router and return the first message content as text."""
        if not self.base_url:
            raise NineRouterError("NINE_ROUTER_BASE_URL belum dikonfigurasi")

        payload: dict[str, Any] = {
            "model": self._resolve_model_hint(model),
            "messages": messages,
            "temperature": (
                settings.NINE_ROUTER_TEMPERATURE
                if temperature is None
                else temperature
            ),
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        try:
            return self._post_chat(payload)
        except NineRouterError as exc:
            # Some OpenAI-compatible routers do not support response_format.
            if response_format and "response_format" in str(exc).lower():
                logger.info("nine_router: retrying without response_format")
                payload.pop("response_format", None)
                return self._post_chat(payload)
            raise

    def _resolve_model_hint(self, model: Optional[str]) -> str:
        """Resolve backend-side aliases to the model name configured in the panel.

        Backend callers sometimes pass aliases like "nine_router", "gemini-flash",
        "story", "pass1", "pass2", "ai_layer" — these are mapped to the actual
        9router model name stored in system settings. Any other string is
        treated as an upstream model name and passed through verbatim so the
        9router combo can decide whether to use it.
        """
        hints = {
            "nine_router": settings.get_nine_router("NINE_ROUTER_MODEL"),
            "gemini-flash": settings.get_nine_router("NINE_ROUTER_MODEL"),
            "story": settings.get_nine_router("NINE_ROUTER_MODEL"),
            "pass1": settings.get_nine_router("NINE_ROUTER_PASS1_MODEL"),
            "pass2": settings.get_nine_router("NINE_ROUTER_PASS2_MODEL"),
            "ai_layer": settings.get_nine_router("NINE_ROUTER_AI_LAYER_MODEL"),
        }
        resolved = model
        if resolved and resolved.lower() in hints:
            val = hints[resolved.lower()]
            if val:
                resolved = val

        if not resolved:
            resolved = settings.get_nine_router("NINE_ROUTER_MODEL") or settings.NINE_ROUTER_MODEL or "CliperHub"

        # Case & alias normalization for known 9router combos:
        # 9router combo matching is case-sensitive ("Claude", "CliperHub").
        # If user specifies "claude", "cliperhub", or "gemini", map to exact registered combo name.
        combo_normalization = {
            "claude": "Claude",
            "cliperhub": "CliperHub",
            "gemini": "CliperHub",
        }
        if resolved and resolved.lower() in combo_normalization:
            return combo_normalization[resolved.lower()]

        return resolved

    def complete_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 3000,
        temperature: Optional[float] = None,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

    def _post_chat(self, payload: dict[str, Any]) -> str:
        url = self._chat_url()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        last_error = ""
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(url, headers=headers, json=payload)

                if response.status_code in {429, 500, 502, 503, 504}:
                    last_error = self._safe_error(response)
                    self._sleep_before_retry(attempt, response.status_code)
                    continue

                if response.status_code >= 400:
                    raise NineRouterError(self._safe_error(response))

                content = self._extract_response_content(response)
                content_strip = content.strip()
                lowered = content_strip.lower()
                if (
                    ("is no longer available" in lowered or "please switch to" in lowered or "model not found" in lowered)
                    and not (content_strip.startswith("{") and content_strip.endswith("}"))
                ):
                    last_error = f"Upstream model error: {content_strip}"
                    logger.warning(f"nine_router: upstream model error on attempt {attempt + 1}: {content_strip}")
                    self._sleep_before_retry(attempt, 503)
                    continue

                return content

            except httpx.TimeoutException as exc:
                last_error = f"timeout: {exc}"
                self._sleep_before_retry(attempt, 408)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                self._sleep_before_retry(attempt, 0)

        raise NineRouterError(
            f"9router gagal setelah {self.max_retries} percobaan: {last_error}"
        )

    def _chat_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def _extract_content(self, data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise NineRouterError("9router response kosong: tidak ada choices")

        choice = choices[0]
        message = choice.get("message") or {}
        content = (
            message.get("content")
            or choice.get("text")
            or message.get("reasoning_content")
            or message.get("thought")
            or ""
        )
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            content = "".join(parts)

        if not content:
            raise NineRouterError("9router response kosong: content tidak ada")
        return str(content)

    def _extract_response_content(self, response: httpx.Response) -> str:
        text = response.text
        try:
            return self._extract_content(response.json())
        except (ValueError, NineRouterError):
            pass

        # Some 9router combos return text/event-stream. Decode the chunks and
        # concatenate assistant delta content.
        sse_content = self._extract_sse_content(text)
        if sse_content:
            return sse_content

        # Be tolerant of routers that emit a JSON object followed by a trailing
        # SSE marker such as "data: [DONE]".
        try:
            data, _ = json.JSONDecoder().raw_decode(text.lstrip())
            if isinstance(data, dict):
                return self._extract_content(data)
        except (ValueError, TypeError, NineRouterError):
            pass

        raise NineRouterError(
            f"9router response tidak bisa diparse: {text[:500]}"
        )

    def _extract_sse_content(self, text: str) -> str:
        parts: list[str] = []
        reasoning_parts: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue

            raw_event = line[5:].strip()
            if not raw_event or raw_event == "[DONE]":
                continue

            try:
                event = json.loads(raw_event)
            except ValueError:
                continue

            choices = event.get("choices") or []
            if not choices:
                continue

            choice = choices[0]
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                parts.append(self._stringify_content(content))
                continue

            reasoning = delta.get("reasoning_content") or delta.get("thought") or delta.get("reasoning")
            if reasoning:
                reasoning_parts.append(self._stringify_content(reasoning))
                continue

            message = choice.get("message") or {}
            content = message.get("content") or choice.get("text")
            if content:
                parts.append(self._stringify_content(content))
                continue

            msg_reasoning = message.get("reasoning_content") or message.get("thought") or message.get("reasoning")
            if msg_reasoning:
                reasoning_parts.append(self._stringify_content(msg_reasoning))

        final = "".join(parts).strip()
        if not final and reasoning_parts:
            final = "".join(reasoning_parts).strip()
        return final

    def _stringify_content(self, content: Any) -> str:
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            return "".join(parts)
        return str(content)

    def _safe_error(self, response: httpx.Response) -> str:
        try:
            data = response.json()
            message = data.get("error", data)
        except ValueError:
            message = response.text[:500]
        return f"HTTP {response.status_code}: {message}"

    def _sleep_before_retry(self, attempt: int, status_code: int) -> None:
        if attempt >= self.max_retries - 1:
            return
        delay = min(5 * (2 ** attempt), 60)
        logger.warning(
            "nine_router: retrying in %ss (attempt %s/%s, status=%s)",
            delay,
            attempt + 1,
            self.max_retries,
            status_code,
        )
        time.sleep(delay)


_client: Optional[NineRouterClient] = None


def get_nine_router_client() -> NineRouterClient:
    global _client
    if _client is None:
        _client = NineRouterClient()
    return _client
