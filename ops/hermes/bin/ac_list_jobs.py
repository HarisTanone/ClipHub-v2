"""
AutoCliper Tool: List Job Terbaru
Dipanggil oleh Hermes toolset autocliper_list_jobs.
"""
import argparse
import json
import os
import sys
from pathlib import Path

_hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
_env_file = os.path.join(_hermes_home, ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent))
import ac_auth

STATUS_EMOJI = {
    "queued": "⏳",
    "processing": "⚙️",
    "completed": "✅",
    "failed": "❌",
    "timeout": "⏰",
}


def main():
    parser = argparse.ArgumentParser(description="List job AutoCliper terbaru")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--status", default="all")
    args = parser.parse_args()

    params = {"limit": args.limit}
    if args.status != "all":
        params["status"] = args.status

    result = ac_auth.api_get("/jobs", params)
    jobs = result.get("jobs") or result.get("data") or result.get("items") or []

    if not jobs:
        print("Tidak ada job ditemukan.")
        return

    # Filter status jika diminta
    if args.status != "all":
        jobs = [j for j in jobs if j.get("status") == args.status]

    print(f"\n{'Job ID':<36} {'Status':<12} {'Progress':<10} {'Dibuat':<20} URL")
    print("─" * 120)

    for job in jobs[:args.limit]:
        job_id = job.get("job_id", "")[:35]
        status = job.get("status", "unknown")
        emoji = STATUS_EMOJI.get(status, "❓")
        progress = job.get("render_progress") or 0
        created = (job.get("created_at") or "")[:16].replace("T", " ")
        url = job.get("youtube_url") or job.get("source_label") or ""
        url_short = url[:50] + "..." if len(url) > 50 else url

        print(f"{job_id:<36} {emoji} {status:<10} {progress:>3}%       {created:<20} {url_short}")

    print(f"\nTotal: {len(jobs)} job")
    print(json.dumps({"count": len(jobs), "jobs": [j.get("job_id") for j in jobs]}), file=sys.stderr)


if __name__ == "__main__":
    main()
