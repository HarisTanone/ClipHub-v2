"""LLM provider registry + router tests.

Covers: CRUD, key masking round-trip (masked value must NOT clobber the real
key), mode toggle (LLM_ROTATE_ALL), Hermes config export, auth guard, and the
chain resolution (off → gemini only, on → gemini + enabled customs).
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from src.infrastructure import llm_provider_store as store
from src.infrastructure.auth import create_access_token
from src.presentation.api import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    token = create_access_token(
        user_id=1, email="admin@test.com", role="superadmin", permissions=[]
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def clean_t_providers():
    for r in store.list_providers(include_disabled=True):
        if r["name"].startswith("t-"):
            store.delete_provider(r["id"])
    yield
    for r in store.list_providers(include_disabled=True):
        if r["name"].startswith("t-"):
            store.delete_provider(r["id"])


def _add(client, auth_headers, name="t-deepseek"):
    r = client.post(
        "/api/settings/llm-providers",
        headers=auth_headers,
        json={
            "name": name,
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "sk-test123",
            "model": "deepseek-chat",
            "enabled": True,
            "priority": 10,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_add_lists_masked_key(client, auth_headers):
    pid = _add(client, auth_headers)
    r = client.get("/api/settings/llm-providers", headers=auth_headers)
    data = {p["name"]: p for p in r.json()["data"]}
    assert data["t-deepseek"]["api_key"] == "sk-tes...t123"


def test_update_masked_key_does_not_clobber(client, auth_headers):
    pid = _add(client, auth_headers)
    r = client.put(
        f"/api/settings/llm-providers/{pid}",
        headers=auth_headers,
        json={"model": "deepseek-reasoner", "api_key": "sk-tes...t123"},
    )
    assert r.status_code == 200
    conn = sqlite3.connect(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "autoclip.db")
    )
    real, model = conn.execute(
        "SELECT api_key, model FROM llm_providers WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert real == "sk-test123"  # masked value ignored
    assert model == "deepseek-reasoner"  # real update applied


def test_mode_toggle(client, auth_headers):
    r = client.put(
        "/api/settings/llm-providers/mode", headers=auth_headers, json={"rotate_all": True}
    )
    assert r.status_code == 200 and r.json()["rotate_all"] is True
    r = client.put(
        "/api/settings/llm-providers/mode", headers=auth_headers, json={"rotate_all": False}
    )
    assert r.status_code == 200 and r.json()["rotate_all"] is False


def test_hermes_export_shape(client, auth_headers):
    _add(client, auth_headers)
    r = client.get("/api/settings/llm-providers/hermes", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["env_keys"] == ["GEMINI_API_KEY"]
    # rotate off → no custom providers listed
    assert body["custom_env_keys"] == []
    assert "model:" in body["config_yaml"]


def test_auth_guard(client):
    r = client.get("/api/settings/llm-providers")
    assert r.status_code in (401, 403)


def test_chain_is_nine_router_only():
    """Chain is always 9router regardless of LLM_ROTATE_ALL (deprecated)."""
    from src.infrastructure import llm_router
    from src.infrastructure.system_config_store import set_system_setting

    set_system_setting("LLM_ROTATE_ALL", False)
    assert [c["kind"] for c in llm_router.get_llm_chain()] == ["nine_router"]

    set_system_setting("LLM_ROTATE_ALL", True)
    assert [c["kind"] for c in llm_router.get_llm_chain()] == ["nine_router"]
