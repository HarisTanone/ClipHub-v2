"""Unit tests for model_settings_store and model_settings API routes."""
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
