"""AutoCliper Tool: Hermes Social Media Publish & Schedule Trigger.

Memungkinkan Hermes Agent untuk mempublikasikan atau menjadwalkan klip/video tertentu
ke akun media sosial yang terhubung.
"""
import argparse
import datetime as dt
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


def publish_post(
    job_id: str,
    clip_rank: int = 1,
    video_source: str = "clip",
    account_ids: list[str] = None,
    caption: str = "",
    title: str = "",
    schedule_at: str = "",
    post_type: str = "video",
) -> dict:
    """Submit publish/schedule request ke AutoCliper backend."""
    try:
        # Default schedule_at = 2 minutes from now if empty
        if not schedule_at:
            sched_dt = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
            schedule_at = sched_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        payload = {
            "jobId": job_id,
            "clipRank": clip_rank,
            "videoSource": video_source,
            "accountIds": account_ids or [],
            "caption": caption,
            "title": title,
            "scheduleAt": schedule_at,
            "type": post_type,
            "isAiGenerated": True,
        }

        # If no accountIds specified, fetch all connected accounts
        if not payload["accountIds"]:
            accounts_res = ac_auth.api_get("/social/accounts?page=1&limit=50")
            if isinstance(accounts_res, dict) and "docs" in accounts_res:
                payload["accountIds"] = [
                    str(a.get("_id") or a.get("id"))
                    for a in accounts_res["docs"]
                    if a.get("isConnected", True)
                ]

        if not payload["accountIds"]:
            return {"error": "Tidak ada akun media sosial yang terhubung atau dipilih"}

        res = ac_auth.api_post("/social/publish", payload)
        return res if isinstance(res, dict) else {"data": res}
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="AutoCliper Social Publish Tool")
    parser.add_argument("--job-id", required=True, help="Job ID AutoCliper")
    parser.add_argument("--clip-rank", type=int, default=1, help="Rank klip yang akan diposting (default: 1)")
    parser.add_argument("--source", choices=["clip", "video_generator"], default="clip", help="Sumber video: 'clip' atau 'video_generator'")
    parser.add_argument("--accounts", type=str, default="", help="Daftar Account ID dipisahkan koma (kosong = semua akun terhubung)")
    parser.add_argument("--caption", type=str, default="", help="Caption / deskripsi postingan")
    parser.add_argument("--title", type=str, default="", help="Judul konten (untuk YouTube/video)")
    parser.add_argument("--schedule-at", type=str, default="", help="Waktu jadwal ISO 8601 UTC (kosong = segera/2 menit)")
    parser.add_argument("--type", choices=["video", "reel", "story"], default="video", help="Tipe postingan")
    parser.add_argument("--json", action="store_true", help="Output format JSON")

    args = parser.parse_args()

    account_ids = [aid.strip() for aid in args.accounts.split(",") if aid.strip()] if args.accounts else []
    result = publish_post(
        job_id=args.job_id,
        clip_rank=args.clip_rank,
        video_source=args.source,
        account_ids=account_ids,
        caption=args.caption,
        title=args.title,
        schedule_at=args.schedule_at,
        post_type=args.type,
    )

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if "error" in result:
        print(f"❌ Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    count = result.get("count", 0)
    total = result.get("total", 0)
    print(f"🚀 Berhasil Menjadwalkan Postingan Media Sosial!")
    print(f"  🆔 Job ID: {args.job_id} (Clip #{args.clip_rank})")
    print(f"  📱 Akun Berhasil: {count}/{total}")
    schedules = result.get("schedules", [])
    for s in schedules:
        sid = s.get("scheduleId") or s.get("result", {}).get("scheduleId", "-")
        print(f"  • Account: {s.get('accountId')} | Schedule ID: {sid}")

    errors = result.get("errors", [])
    if errors:
        print("  ⚠️ Gagal di beberapa akun:")
        for err in errors:
            print(f"    - {err.get('accountId')}: {err.get('error')}")


if __name__ == "__main__":
    main()
