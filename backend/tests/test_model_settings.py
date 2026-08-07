"""Unit tests for model_settings_store and model_settings API routes."""
import asyncio
import json
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

import src.infrastructure.model_settings_store as store
from src.infrastructure.model_settings_store import (
    get_model_setting,
    get_all_model_settings,
    set_model_setting,
    bulk_set_model_settings,
    VALID_MODEL_KEYS,
)


def _make_test_db():
    """Create an in-memory DB with model_settings table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE model_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_by INTEGER DEFAULT NULL
        )
    """)
    conn.execute(
        "INSERT INTO model_settings (key, value, description) VALUES (?, ?, ?)",
        ("NINE_ROUTER_MODEL", "TestModel", "test desc"),
    )
    conn.execute(
        "INSERT INTO model_settings (key, value, description) VALUES (?, ?, ?)",
        ("NINE_ROUTER_TIMEOUT", "60", "timeout"),
    )
    conn.commit()
    return conn


class _NoCloseConnection:
    """Wrapper that prevents .close() from actually closing the in-memory DB."""

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        if name == "close":
            return lambda: None  # no-op close
        return getattr(self._conn, name)

    def cursor(self):
        return self._conn.cursor()

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def commit(self):
        return self._conn.commit()


class TestModelSettingsStore:
    """Test DB-backed model settings store."""

    def setup_method(self):
        self._real_conn = _make_test_db()
        self._conn = _NoCloseConnection(self._real_conn)
        # Skip _ensure_table DB call
        store._table_ensured = True

    def teardown_method(self):
        store._table_ensured = False
        self._real_conn.close()

    @patch("src.infrastructure.model_settings_store.get_dict_connection")
    def test_get_model_setting_from_db(self, mock_conn):
        mock_conn.return_value = self._conn
        val = get_model_setting("NINE_ROUTER_MODEL")
        assert val == "TestModel"

    @patch("src.infrastructure.model_settings_store.get_dict_connection")
    def test_get_model_setting_coerces_int(self, mock_conn):
        mock_conn.return_value = self._conn
        val = get_model_setting("NINE_ROUTER_TIMEOUT")
        assert val == 60
        assert isinstance(val, int)

    def test_get_model_setting_invalid_key_returns_none(self):
        val = get_model_setting("INVALID_KEY_XYZ")
        assert val is None

    @patch("src.infrastructure.model_settings_store.get_dict_connection")
    def test_set_model_setting(self, mock_conn):
        mock_conn.return_value = self._conn
        ok = set_model_setting("NINE_ROUTER_MODEL", "NewModel", user_id=1)
        assert ok is True
        # Verify
        cur = self._real_conn.cursor()
        cur.execute("SELECT value FROM model_settings WHERE key = ?", ("NINE_ROUTER_MODEL",))
        row = cur.fetchone()
        assert row["value"] == "NewModel"

    def test_set_model_setting_invalid_key(self):
        ok = set_model_setting("INVALID_KEY", "value")
        assert ok is False

    @patch("src.infrastructure.model_settings_store.get_dict_connection")
    def test_bulk_set(self, mock_conn):
        mock_conn.return_value = self._conn
        count = bulk_set_model_settings(
            {"NINE_ROUTER_MODEL": "BulkModel", "NINE_ROUTER_PASS1_MODEL": "Pass1"},
            user_id=1,
        )
        assert count == 2
        cur = self._real_conn.cursor()
        cur.execute("SELECT value FROM model_settings WHERE key = ?", ("NINE_ROUTER_MODEL",))
        assert cur.fetchone()["value"] == "BulkModel"
        cur.execute("SELECT value FROM model_settings WHERE key = ?", ("NINE_ROUTER_PASS1_MODEL",))
        assert cur.fetchone()["value"] == "Pass1"

    @patch("src.infrastructure.model_settings_store.get_dict_connection")
    def test_get_all_model_settings(self, mock_conn):
        mock_conn.return_value = self._conn
        all_s = get_all_model_settings()
        keys = {s["key"] for s in all_s}
        # Should contain all valid keys
        assert VALID_MODEL_KEYS.issubset(keys)
        # DB values should be present
        for s in all_s:
            if s["key"] == "NINE_ROUTER_MODEL":
                assert s["value"] == "TestModel"

    def test_valid_keys_whitelist(self):
        assert "NINE_ROUTER_MODEL" in VALID_MODEL_KEYS
        assert "NINE_ROUTER_PASS1_MODEL" in VALID_MODEL_KEYS
        assert "NINE_ROUTER_AI_LAYER_MODEL" in VALID_MODEL_KEYS
        assert "RANDOM_KEY" not in VALID_MODEL_KEYS

    @patch("src.infrastructure.model_settings_store.get_dict_connection")
    def test_bool_coercion(self, mock_conn):
        mock_conn.return_value = self._conn
        self._real_conn.execute(
            "INSERT OR REPLACE INTO model_settings (key, value) VALUES (?, ?)",
            ("NINE_ROUTER_WHISPER_ENABLED", "true"),
        )
        self._real_conn.commit()
        val = get_model_setting("NINE_ROUTER_WHISPER_ENABLED")
        assert val is True

    @patch("src.infrastructure.model_settings_store.get_dict_connection")
    def test_float_coercion(self, mock_conn):
        mock_conn.return_value = self._conn
        self._real_conn.execute(
            "INSERT OR REPLACE INTO model_settings (key, value) VALUES (?, ?)",
            ("NINE_ROUTER_TEMPERATURE", "0.7"),
        )
        self._real_conn.commit()
        val = get_model_setting("NINE_ROUTER_TEMPERATURE")
        assert val == 0.7
        assert isinstance(val, float)


# ─── Model test endpoint: robust JSON / SSE response parsing ─────────────────
#
# 9router returns HTTP 200 with Content-Type: text/event-stream for some
# models (e.g. ag/gemini-3.6-flash-high) even when stream is not requested.
# A naive resp.json() on that body raises ``JSONDecodeError: Expecting value:
# line 1 column 1 (char 0)`` — the exact error the user saw in the AI Models
# settings tab. These tests lock in the SSE-tolerant parsing.


def _run(coro):
    return asyncio.run(coro)


class _FakeSSEResponse:
    status_code = 200
    headers = {"content-type": "text/event-stream"}
    text = (
        'data: {"choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}\n\n'
        'data: {"choices":[{"index":0,"delta":{"content":"OK"},"finish_reason":null}]}\n\n'
        'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"total_tokens":5}}\n\n'
        "data: [DONE]\n\n"
    )


class _FakeJSONResponse:
    status_code = 200
    headers = {"content-type": "application/json"}
    text = ""

    def json(self):
        return {
            "choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 3},
        }


class _FakeEmptyResponse:
    status_code = 200
    headers = {"content-type": "application/json"}
    text = ""

    def json(self):
        # Mirrors real httpx: raising JSONDecodeError on a non-JSON body.
        raise json.JSONDecodeError("Expecting value", self.text, 0)


class _FakeGarbageResponse:
    status_code = 200
    headers = {"content-type": "text/plain"}
    text = "some plain text error"

    def json(self):
        raise json.JSONDecodeError("Expecting value", self.text, 0)


class _FakeModelsResponse:
    status_code = 200
    headers = {"content-type": "application/json"}
    text = ""

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def _patch_async_client(responses):
    """Patch httpx.AsyncClient in model_settings with a fake that pops responses."""

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, json=None, headers=None):
            return responses.pop(0)

    return patch("src.presentation.routes.model_settings.httpx.AsyncClient", FakeClient)


def test_extract_chat_response_handles_sse_stream():
    from src.presentation.routes.model_settings import _extract_chat_response

    streamed, text, finish, usage = _extract_chat_response(_FakeSSEResponse())
    assert streamed is True
    assert text == "OK"
    assert finish == "stop"
    assert usage == {"total_tokens": 5}


def test_extract_chat_response_handles_plain_json():
    from src.presentation.routes.model_settings import _extract_chat_response

    streamed, text, finish, usage = _extract_chat_response(_FakeJSONResponse())
    assert streamed is False
    assert text == "Hello"
    assert finish == "stop"
    assert usage == {"total_tokens": 3}


def test_extract_chat_response_empty_body_raises_friendly_error():
    from src.presentation.routes.model_settings import _extract_chat_response

    with pytest.raises(ValueError, match="kosong"):
        _extract_chat_response(_FakeEmptyResponse())


def test_extract_chat_response_garbage_body_raises_friendly_error():
    from src.presentation.routes.model_settings import _extract_chat_response

    with pytest.raises(ValueError, match="tidak bisa diparse"):
        _extract_chat_response(_FakeGarbageResponse())


def test_model_connection_streaming_model_reports_connected():
    from src.presentation.routes.model_settings import (
        ModelTestRequest,
        test_model_connection,
    )

    request = ModelTestRequest(
        base_url="http://127.0.0.1:20128/v1",
        api_key="test-key",
        model="ag/gemini-3.6-flash-high",
        prompt="Reply with OK",
    )
    with _patch_async_client([_FakeSSEResponse()]):
        result = _run(test_model_connection(request, user=None))

    assert result["success"] is True
    assert result["response"] == "OK"
    assert result["streamed"] is True
    assert result["finish_reason"] == "stop"
    assert result["usage"] == {"total_tokens": 5}


def test_model_connection_non_json_body_returns_friendly_error():
    from src.presentation.routes.model_settings import (
        ModelTestRequest,
        test_model_connection,
    )

    request = ModelTestRequest(
        base_url="http://127.0.0.1:20128/v1",
        api_key="test-key",
        model="ag/gemini-3.6-flash-high",
        prompt="Reply with OK",
    )
    with _patch_async_client([_FakeGarbageResponse()]):
        result = _run(test_model_connection(request, user=None))

    assert result["success"] is False
    assert "Expecting value" not in result["error"]
    assert "some plain text error" in result["error"]


def test_model_connection_empty_body_returns_friendly_error():
    from src.presentation.routes.model_settings import (
        ModelTestRequest,
        test_model_connection,
    )

    request = ModelTestRequest(
        base_url="http://127.0.0.1:20128/v1",
        api_key="test-key",
        model="ag/gemini-3.6-flash-high",
        prompt="Reply with OK",
    )
    with _patch_async_client([_FakeEmptyResponse()]):
        result = _run(test_model_connection(request, user=None))

    assert result["success"] is False
    assert "Expecting value" not in result["error"]
    assert "kosong" in result["error"]


class _FakeJSONNoChoicesResponse:
    status_code = 200
    headers = {"content-type": "application/json"}
    text = '{"object":"list","data":[]}'

    def json(self):
        return {"object": "list", "data": []}


def test_extract_chat_response_json_without_choices_raises_friendly_error():
    from src.presentation.routes.model_settings import _extract_chat_response

    with pytest.raises(ValueError, match="tidak mengandung 'choices'"):
        _extract_chat_response(_FakeJSONNoChoicesResponse())


def test_model_connection_empty_content_not_reported_connected():
    from src.presentation.routes.model_settings import (
        ModelTestRequest,
        test_model_connection,
    )

    class _FakeEmptyContentResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}
        text = (
            'data: {"choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"index":0,"delta":{},"finish_reason":"length"}],"usage":{"total_tokens":50}}\n\n'
            "data: [DONE]\n\n"
        )

    request = ModelTestRequest(
        base_url="http://127.0.0.1:20128/v1",
        api_key="test-key",
        model="ag/gemini-3.6-flash-high",
        prompt="Reply with OK",
    )
    with _patch_async_client([_FakeEmptyContentResponse()]):
        result = _run(test_model_connection(request, user=None))

    assert result["success"] is False
    assert "tidak ada konten" in result["error"]


def test_test_all_models_handles_streaming_and_garbage():
    from src.presentation.routes.model_settings import test_all_models

    def fake_get_model_setting(key):
        return {
            "NINE_ROUTER_BASE_URL": "http://127.0.0.1:20128/v1",
            "NINE_ROUTER_API_KEY": "test-key",
        }.get(key)

    models_body = {
        "object": "list",
        "data": [
            {"id": "ag/gemini-3.6-flash-high", "object": "model", "owned_by": "ag"},
            {"id": "broken-model", "object": "model"},
        ],
    }

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers=None):
            return _FakeModelsResponse(models_body)

        async def post(self, url, json=None, headers=None):
            if json and json.get("model") == "ag/gemini-3.6-flash-high":
                return _FakeSSEResponse()
            return _FakeGarbageResponse()

    with patch(
        "src.presentation.routes.model_settings.get_model_setting",
        side_effect=fake_get_model_setting,
    ), patch(
        "src.presentation.routes.model_settings.httpx.AsyncClient",
        FakeClient,
    ):
        result = _run(test_all_models(user=None))

    assert result["success"] is True
    assert result["total"] == 2
    by_model = {r["model"]: r for r in result["results"]}
    assert by_model["ag/gemini-3.6-flash-high"]["status"] == "ok"
    assert by_model["ag/gemini-3.6-flash-high"]["streamed"] is True
    assert by_model["broken-model"]["status"] == "error"
    assert "Expecting value" not in by_model["broken-model"]["error"]
