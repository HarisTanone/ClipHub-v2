"""
AutoCliper Tool: Ganti Model LLM Hermes
Dipanggil oleh Hermes toolset autocliper_switch_model.

Mengganti model.default di $HERMES_HOME/config.yaml secara langsung.
Daftar model diambil live dari 9router /v1/models endpoint.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import httpx

_hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
_env_file = os.path.join(_hermes_home, ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

# 9router base URL (OpenAI-compatible)
NINE_ROUTER_BASE_URL = os.environ.get(
    "OPENAI_BASE_URL",
    os.environ.get("NINE_ROUTER_BASE_URL", "http://127.0.0.1:20128/v1"),
).rstrip("/")

# Alias pendek → nama lengkap (shortcut saja, model apapun dari 9router diterima)
KNOWN_ALIASES = {
    "grok": "gcli/grok-4.5-high",
    "grok-high": "gcli/grok-4.5-high",
    "grok-fast": "gcli/grok-4.5-fast",
    "gemini": "gcli/gemini-2.5-pro",
    "gemini-pro": "gcli/gemini-2.5-pro",
    "gemini-flash": "gcli/gemini-2.5-flash",
    "gpt4o": "openai/gpt-4o",
    "gpt-4o": "openai/gpt-4o",
    "llama": "groq/llama-3.3-70b",
    "llama70b": "groq/llama-3.3-70b",
    "cliper": "CliperHub",
    "cliperhub": "CliperHub",
    "default": "gcli/grok-4.5-high",
}


def fetch_9router_models() -> list[str]:
    """Ambil daftar model dari 9router /v1/models endpoint."""
    api_key = (
        os.environ.get("NINE_ROUTER_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("HERMES_CUSTOM_127_0_0_1_20128_API_KEY")
        or ""
    )
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = httpx.get(f"{NINE_ROUTER_BASE_URL}/models", headers=headers, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        # OpenAI format: {"data": [{"id": "model-name", ...}, ...]}
        models = data.get("data", [])
        return sorted([m["id"] for m in models if m.get("id")])
    except httpx.ConnectError:
        return []  # 9router tidak jalan
    except Exception:
        return []


def print_available_models(models: list[str]):
    """Tampilkan model dari 9router dan alias yang tersedia."""
    if models:
        print(f"\n📡 Model tersedia dari 9router ({NINE_ROUTER_BASE_URL}):")
        for m in models:
            # Cari alias yang match
            aliases = [a for a, full in KNOWN_ALIASES.items() if full == m]
            alias_str = f"  (alias: {', '.join(aliases)})" if aliases else ""
            print(f"  • {m}{alias_str}")
    else:
        print("\n[WARN] Tidak bisa connect ke 9router — daftar model tidak tersedia.")
        print(f"       URL: {NINE_ROUTER_BASE_URL}/models")

    # Tampilkan alias yang tidak match model manapun di 9router (bisa jadi combo/special)
    shown_full = set()
    extra_aliases = []
    for alias, full in sorted(KNOWN_ALIASES.items()):
        if full not in shown_full and full not in models:
            extra_aliases.append((alias, full))
            shown_full.add(full)

    if extra_aliases:
        print("\nAlias shortcut (non-9router / combo):")
        for alias, full in extra_aliases:
            print(f"  • {alias:<15} -> {full}")

    print("\nBisa pakai nama model langsung dari 9router atau alias di atas.")


def main():
    parser = argparse.ArgumentParser(description="Ganti model LLM Hermes")
    parser.add_argument(
        "--model", required=False, default=None,
        help="Nama model (alias pendek atau nama dari 9router /v1/models)",
    )
    parser.add_argument(
        "--list", default="false", nargs="?", const="true", dest="list_models",
        help="Tampilkan semua model yang tersedia dari 9router (true/false)",
    )
    args = parser.parse_args()

    want_list = args.list_models.lower() in ("true", "1", "yes")

    # Fetch model dari 9router
    available_models = fetch_9router_models()

    # Mode list: tampilkan model dan keluar
    if want_list:
        print_available_models(available_models)
        return

    if not args.model:
        parser.error("--model diperlukan (atau gunakan --list untuk lihat model)")

    # Resolve alias → nama lengkap, kalau bukan alias pakai apa adanya
    model = KNOWN_ALIASES.get(args.model.lower(), args.model)
    is_alias = args.model.lower() in KNOWN_ALIASES

    if available_models and model not in available_models:
        print(f"[WARN] Model '{model}' tidak ditemukan di 9router.")
        print(f"       Model tersedia: {', '.join(available_models[:10])}")
        print(f"       Tetap dipakai — mungkin model baru atau combo.\n")

    config_path = os.path.join(_hermes_home, "config.yaml")
    if not os.path.exists(config_path):
        print(f"ERROR: Config tidak ditemukan: {config_path}", file=sys.stderr)
        sys.exit(1)

    # Baca config
    with open(config_path) as f:
        content = f.read()

    # Cari model saat ini
    current_model = None
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("default:") and "model:" not in stripped:
            current_model = stripped.split(":", 1)[1].strip()
            break

    # Ganti nilai default model
    import re
    new_content = re.sub(
        r"^(\s*default:\s*)(.+)$",
        lambda m: f"{m.group(1)}{model}",
        content,
        count=1,
        flags=re.MULTILINE,
    )

    if new_content == content:
        # Fallback: tambah default di bawah model:
        new_content = re.sub(
            r"(model:\s*\n)",
            f"\\1  default: {model}\n",
            content,
            count=1,
        )

    # Backup dan simpan
    backup_path = f"{config_path}.bak"
    with open(backup_path, "w") as f:
        f.write(content)

    with open(config_path, "w") as f:
        f.write(new_content)

    print(f"[OK] Model berhasil diganti!")
    print(f"Sebelum : {current_model or 'tidak diketahui'}")
    print(f"Sekarang: {model}")
    if is_alias:
        print(f"  (alias '{args.model}' → {model})")
    print(f"\nConfig disimpan: {config_path}")
    print(f"Backup  : {backup_path}")
    print(f"\nPerubahan berlaku pada session Hermes berikutnya.")

    # Tampilkan model tersedia
    print_available_models(available_models)

    # Metadata ke stderr untuk Hermes
    print(json.dumps({
        "previous_model": current_model,
        "new_model": model,
        "is_alias": is_alias,
        "available_models": available_models,
    }), file=sys.stderr)


if __name__ == "__main__":
    main()
