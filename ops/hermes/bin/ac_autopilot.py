"""
AutoCliper Tool: Hermes Autopilot Status & Manual Trigger
Dipanggil oleh Hermes toolset autocliper_autopilot.

Mengecek status kuota harian (maksimal 1 video/hari) dan memicu
pencarian video viral otomatis + rendering dengan preset + social auto-post.
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

import ac_auth


def get_status() -> dict:
    """Ambil status autopilot dan kuota hari ini."""
    try:
        res = ac_auth.api_get("/autopilot/settings")
        return res if isinstance(res, dict) else {"data": res}
    except Exception as e:
        return {"error": str(e)}


def trigger_run(force: bool = False) -> dict:
    """Jalankan siklus autopilot hari ini (1 video/hari)."""
    try:
        res = ac_auth.api_post("/autopilot/run", {"force": force})
        return res if isinstance(res, dict) else {"data": res}
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="AutoCliper Autopilot Management Tool")
    parser.add_argument(
        "--action",
        choices=["status", "run"],
        default="status",
        help="Aksi yang akan dijalankan: 'status' (cek kuota & config) atau 'run' (jalankan 1 video hari ini)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Paksa jalankan meskipun kuota hari ini sudah tercapai",
    )
    parser.add_argument("--json", action="store_true", help="Output format JSON")

    args = parser.parse_args()

    if args.action == "run":
        result = trigger_run(force=args.force)
    else:
        result = get_status()

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if "error" in result:
        print(f"❌ Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.action == "run":
        if result.get("success"):
            vid = result.get("video", {})
            print(f"🚀 Autopilot Berhasil Dijalankan!")
            print(f"  🎬 Video: {vid.get('title')}")
            print(f"  🔗 URL: {vid.get('url')}")
            print(f"  🔥 Virality Score: {vid.get('virality_score')}/100")
            print(f"  🎨 Preset: {result.get('preset_slug')}")
            print(f"  📱 Target: {', '.join(result.get('target_platforms', []))}")
            print(f"  🆔 Job ID: {result.get('job_id')}")
        else:
            print(f"⚠️ {result.get('message', 'Tidak dapat menjalankan autopilot')}")
    else:
        data = result.get("data", {})
        quota = result.get("quota", {})
        print("🤖 Hermes Autopilot Status")
        print(f"  Status: {'🟢 AKTIF' if data.get('enabled') else '⚪ NONAKTIF'}")
        print(f"  Niche: {data.get('niche_query')}")
        print(f"  Preset: {data.get('preset_slug')}")
        print(f"  Platforms: {data.get('target_platforms')}")
        print(f"  Jadwal Harian: {data.get('run_time')} WIB")
        print(f"  Kuota Hari Ini: {quota.get('today_runs', 0)}/{quota.get('max_daily_videos', 1)} video")
        print(f"  Kesiapan: {'✅ Siap Jalan' if result.get('can_run_today') else '⏳ Kuota Hari Ini Selesai'}")


if __name__ == "__main__":
    main()
