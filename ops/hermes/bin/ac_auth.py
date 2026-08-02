"""
AutoCliper Auth Helper — shared by semua ac_*.py scripts.
Menyimpan JWT token di $HERMES_HOME/autocliper_token.json dengan auto-refresh.
"""
import json
import os
import sys
import time
from pathlib import Path

import httpx

# ─── Config dari environment ──────────────────────────────────────────────────
HERMES_HOME = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
AUTOCLIPER_API = os.environ.get("AUTOCLIPER_API_URL", "http://127.0.0.1:8000/api")
AUTOCLIPER_EMAIL = os.environ.get("AUTOCLIPER_EMAIL", "")
AUTOCLIPER_PASSWORD = os.environ.get("AUTOCLIPER_PASSWORD", "")
TOKEN_FILE = os.path.join(HERMES_HOME, "autocliper_token.json")


def _load_token() -> dict:
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_token(data: dict):
    os.makedirs(HERMES_HOME, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


def _is_expired(token_data: dict, buffer_sec: int = 120) -> bool:
    """Return True jika token sudah expired atau akan expired dalam buffer_sec."""
    exp = token_data.get("expires_at", 0)
    return time.time() + buffer_sec >= exp


def get_token() -> str:
    """Dapatkan valid access token, auto-login/refresh jika perlu."""
    if not AUTOCLIPER_EMAIL or not AUTOCLIPER_PASSWORD:
        print(
            "ERROR: Set AUTOCLIPER_EMAIL dan AUTOCLIPER_PASSWORD di $HERMES_HOME/.env",
            file=sys.stderr,
        )
        sys.exit(1)

    token_data = _load_token()

    # Coba refresh dulu kalau access token expired tapi refresh token masih ada
    if _is_expired(token_data) and token_data.get("refresh_token"):
        try:
            resp = httpx.post(
                f"{AUTOCLIPER_API}/auth/refresh",
                json={"refresh_token": token_data["refresh_token"]},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                token_data = {
                    "access_token": data["access_token"],
                    "refresh_token": data["refresh_token"],
                    "expires_at": time.time() + data.get("expires_in", 1800) - 60,
                }
                _save_token(token_data)
                return token_data["access_token"]
        except Exception:
            pass  # Fallback ke login ulang

    # Login ulang
    if _is_expired(token_data):
        try:
            resp = httpx.post(
                f"{AUTOCLIPER_API}/auth/login",
                json={"email": AUTOCLIPER_EMAIL, "password": AUTOCLIPER_PASSWORD},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            token_data = {
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "expires_at": time.time() + data.get("expires_in", 1800) - 60,
            }
            _save_token(token_data)
        except httpx.HTTPStatusError as e:
            print(f"ERROR: Login gagal ({e.response.status_code}): {e.response.text}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: Tidak bisa connect ke AutoCliper API: {e}", file=sys.stderr)
            sys.exit(1)

    return token_data["access_token"]


def get_headers() -> dict:
    return {"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"}


def api_get(path: str, params: dict = None) -> dict:
    """GET request ke AutoCliper API."""
    try:
        resp = httpx.get(
            f"{AUTOCLIPER_API}{path}",
            headers=get_headers(),
            params=params or {},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        print(f"ERROR: API {path} gagal ({e.response.status_code}): {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def api_post(path: str, body: dict) -> dict:
    """POST request ke AutoCliper API."""
    try:
        resp = httpx.post(
            f"{AUTOCLIPER_API}{path}",
            headers=get_headers(),
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        print(f"ERROR: API {path} gagal ({e.response.status_code}): {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
