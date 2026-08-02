"""
AutoCliper Tool: Submit Job ke Pipeline
Dipanggil oleh Hermes toolset autocliper_submit_job.
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
    parser = argparse.ArgumentParser(description="Submit YouTube URL ke AutoCliper")
    parser.add_argument("--url", required=True, help="YouTube URL")
    parser.add_argument("--style", default="default", help="Style preset")
    parser.add_argument("--ratio", default="9:16", help="Aspect ratio")
    parser.add_argument("--force", default="false", help="Force reprocess (true/false)")
    args = parser.parse_args()

    force = args.force.lower() in ("true", "1", "yes")

    payload = {
        "youtube_url": args.url,
        "style_preset": args.style,
        "target_aspect_ratio": args.ratio,
        "force_reprocess": force,
        "broll_enabled": True,
        "use_remotion": True,
    }

    print(f"Submitting: {args.url}")
    print(f"Style: {args.style} | Ratio: {args.ratio} | Force: {force}")
    print("Menghubungi AutoCliper API...")

    result = ac_auth.api_post("/jobs", payload)

    job_id = result.get("job_id", "unknown")
    status = result.get("status", "unknown")
    is_cached = result.get("is_cached", False)

    if is_cached:
        print(f"\n✅ Job sudah ada (cached): {job_id}")
        print(f"Status: {status}")
        print(f"Gunakan force_reprocess=true untuk proses ulang.")
    else:
        print(f"\n✅ Job berhasil dibuat!")
        print(f"Job ID: {job_id}")
        print(f"Status: {status}")
        print(f"\nPantau progress dengan: autocliper_job_status job_id={job_id}")

    api_url = os.environ.get("AUTOCLIPER_API_URL", "http://127.0.0.1:8000/api")
    base_url = api_url.replace("/api", "")
    print(f"Dashboard: {base_url}")

    # Metadata ke stderr untuk Hermes
    print(json.dumps({"job_id": job_id, "status": status, "is_cached": is_cached}), file=sys.stderr)


if __name__ == "__main__":
    main()
