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
