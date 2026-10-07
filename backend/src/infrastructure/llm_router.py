"""System-wide LLM router — 9router-only.

All AI text generation goes through 9router (OpenAI-compatible /chat/completions).
Endpoint, key, and model/combination are configured from the admin panel
(system settings: NINE_ROUTER_BASE_URL, NINE_ROUTER_API_KEY, NINE_ROUTER_MODEL,
NINE_ROUTER_PASS1_MODEL, NINE_ROUTER_PASS2_MODEL, NINE_ROUTER_AI_LAYER_MODEL).

Direct Gemini/Groq API keys are NOT used for chat completions. They remain
available only for capabilities that 9router cannot proxy today
(e.g. Gemini video understanding / TTS) — those paths are gated by their own
flags and are not part of this router.
"""
import logging
from typing import Any, Optional

from src.infrastructure.nine_router_client import NineRouterError, NineRouterClient

logger = logging.getLogger(__name__)


class RouterClientError(RuntimeError):
    """Raised when 9router cannot return a usable response."""


def get_llm_chain() -> list[dict[str, Any]]:
    """Resolve the active provider chain.

    Single entry: 9router. Kept as a list so downstream code that iterates
    the chain keeps working without changes.
    """
    return [{"kind": "nine_router"}]


def route_chat(
    messages: list[dict[str, str]],
    max_tokens: int = 3000,
    temperature: Optional[float] = None,
    require_json: bool = False,
) -> str:
    """Route a chat completion through 9router.

    Endpoint/key/model all come from 9router config (DB-first via
    settings.get_nine_router). Raises RouterClientError when 9router fails.
    """
    errors: list[str] = []
    client = NineRouterClient(bypass_router=True)
    if not client.is_configured:
        raise RouterClientError("NINE_ROUTER_BASE_URL belum dikonfigurasi")

    try:
        return client.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"} if require_json else None,
        )
    except (NineRouterError, Exception) as exc:  # noqa: BLE001
        msg = f"9router: {str(exc)[:300]}"
        errors.append(msg)
        logger.warning(f"llm_router: {msg}")
        raise RouterClientError(msg)
