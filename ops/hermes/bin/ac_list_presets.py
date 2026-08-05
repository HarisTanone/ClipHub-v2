"""
AutoCliper Tool: List Style Presets
Dipanggil oleh Hermes toolset autocliper_list_presets.
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Load .env dari HERMES_HOME
_hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
_env_file = os.path.join(_hermes_home, ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

# Tambah path bin ke sys.path supaya bisa import ac_auth
sys.path.insert(0, str(Path(__file__).parent))
import ac_auth


def main():
    parser = argparse.ArgumentParser(description="List style presets dari AutoCliper")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args()

    try:
        result = ac_auth.api_get("/style-presets")
    except Exception as e:
        if args.format == "json":
            print(json.dumps({"error": str(e)}))
        else:
            print(f"❌ Gagal mengambil daftar presets: {e}")
        sys.exit(1)

    presets = result.get("data", [])

    if args.format == "json":
        print(json.dumps(presets, indent=2))
        return

    # Format text untuk Telegram
    if not presets:
        print("❌ Tidak ada style preset tersedia.")
        return

    print("📋 <b>Daftar Style Preset IDs:</b>\n")
    for preset in presets:
        preset_id = preset.get("id", "unknown")
        name = preset.get("name", "Unnamed")
        print(f"• <code>{preset_id}</code> - {name}")


if __name__ == "__main__":
    main()
