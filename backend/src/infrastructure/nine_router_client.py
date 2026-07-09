"""9router OpenAI-compatible chat completions client."""
from __future__ import annotations

import logging
import json
import time
from typing import Any, Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


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
    ):
        self.base_url = (base_url or settings.NINE_ROUTER_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.NINE_ROUTER_API_KEY
        self.timeout = timeout or settings.NINE_ROUTER_TIMEOUT
        self.max_retries = max_retries or settings.NINE_ROUTER_MAX_RETRIES

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
            "model": model or settings.nine_router_model,
            "messages": messages,
            "temperature": (
                settings.NINE_ROUTER_TEMPERATURE
                if temperature is None
                else temperature
            ),
            "max_tokens": max_tokens,
            "stream": False,
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
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
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

                return self._extract_response_content(response)

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
        content = message.get("content") or choice.get("text") or ""
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

        # Some 9router combos return text/event-stream even when stream=false.
        # Decode the chunks and concatenate assistant delta content.
        sse_content = self._extract_sse_content(text)
        if sse_content:
            return sse_content

        # Be tolerant of routers that emit a JSON object followed by a trailing
        # SSE marker such as "data: [DONE]".
        try:
            data, _ = json.JSONDecoder().raw_decode(text.lstrip())
            if isinstance(data, dict):
                return self._extract_content(data)
        except (ValueError, TypeError):
            pass

        raise NineRouterError(
            f"9router response tidak bisa diparse: {text[:500]}"
        )

    def _extract_sse_content(self, text: str) -> str:
        parts: list[str] = []
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

            message = choice.get("message") or {}
            content = message.get("content") or choice.get("text")
            if content:
                parts.append(self._stringify_content(content))

        return "".join(parts).strip()

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
