import httpx

from src.infrastructure.nine_router_client import NineRouterClient


def _response(text: str, content_type: str = "application/json") -> httpx.Response:
    return httpx.Response(200, headers={"content-type": content_type}, text=text)


def test_extract_json_response_content():
    client = NineRouterClient(base_url="http://127.0.0.1:20128/v1")
    response = _response(
        '{"choices":[{"message":{"role":"assistant","content":"JSON OK"}}]}'
    )

    assert client._extract_response_content(response) == "JSON OK"


def test_extract_sse_combo_response_content():
    client = NineRouterClient(base_url="http://127.0.0.1:20128/v1")
    response = _response(
        "\n".join(
            [
                'data: {"choices":[{"delta":{"role":"assistant"},"finish_reason":null}]}',
                'data: {"choices":[{"delta":{"content":"9router "},"finish_reason":null}]}',
                'data: {"choices":[{"delta":{"content":"server OK."},"finish_reason":null}]}',
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            ]
        ),
        "text/event-stream",
    )

    assert client._extract_response_content(response) == "9router server OK."


def test_extract_json_with_trailing_sse_done_marker():
    client = NineRouterClient(base_url="http://127.0.0.1:20128/v1")
    response = _response(
        '{"choices":[{"message":{"content":"Provider OK"}}]}\n'
        "data: [DONE]\n",
        "text/event-stream",
    )

    assert client._extract_response_content(response) == "Provider OK"


def test_normalize_nine_router_base_url():
    from src.infrastructure.nine_router_client import normalize_nine_router_base_url

    # Strips /dashboard web UI path
    assert normalize_nine_router_base_url("http://100.64.5.96:20128/dashboard") == "http://100.64.5.96:20128/v1"
    assert normalize_nine_router_base_url("http://100.64.5.96:20128/dashboard/") == "http://100.64.5.96:20128/v1"
    assert normalize_nine_router_base_url("http://100.64.5.96:20128/dashboard/models") == "http://100.64.5.96:20128/v1"

    # Preserves clean endpoints
    assert normalize_nine_router_base_url("http://100.64.5.96:20128/v1") == "http://100.64.5.96:20128/v1"
    assert normalize_nine_router_base_url("http://100.64.5.96:20128") == "http://100.64.5.96:20128/v1"
    assert normalize_nine_router_base_url("http://100.64.5.96:20128/v1/chat/completions") == "http://100.64.5.96:20128/v1/chat/completions"
    assert normalize_nine_router_base_url("") == ""


def test_nine_router_client_normalizes_base_url():
    client = NineRouterClient(base_url="http://100.64.5.96:20128/dashboard")
    assert client.base_url == "http://100.64.5.96:20128/v1"
    assert client._chat_url() == "http://100.64.5.96:20128/v1/chat/completions"


def test_resolve_model_hint_verbatim_passthrough():
    client = NineRouterClient(base_url="http://127.0.0.1:20128/v1")

    # Explicit model names pass through directly as configured in DB/settings
    assert client._resolve_model_hint("Claude") == "Claude"
    assert client._resolve_model_hint("CliperHub") == "CliperHub"
    assert client._resolve_model_hint("Gemini") == "Gemini"
    assert client._resolve_model_hint("gemini/gemini-3.8-flash") == "gemini/gemini-3.8-flash"
    assert client._resolve_model_hint("kr/claude-sonnet-4.6") == "kr/claude-sonnet-4.6"



