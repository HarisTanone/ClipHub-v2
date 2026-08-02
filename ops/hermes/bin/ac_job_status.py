"""
AutoCliper Tool: Cek Status Job
Dipanggil oleh Hermes toolset autocliper_job_status.
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
    "downloading": "⬇️",
    "transcribing": "📝",
    "analyzing": "🧠",
    "trimming": "✂️",
    "rendering": "🎬",
    "completed": "✅",
    "failed": "❌",
    "timeout": "⏰",
}


def main():
    parser = argparse.ArgumentParser(description="Cek status job AutoCliper")
    parser.add_argument("--job-id", required=True, help="Job ID")
    args = parser.parse_args()

    # Ambil status dari progress poll endpoint (lebih detail)
    progress = ac_auth.api_get(f"/jobs/{args.job_id}/progress/poll")
    data = progress.get("data", {})

    status = data.get("status", "unknown")
    emoji = STATUS_EMOJI.get(status, "❓")
    is_terminal = data.get("is_terminal", False)

    prog = data.get("progress", {})
    pct = prog.get("percentage", 0)
    step_label = prog.get("step_label", "")
    current_step = prog.get("current_step", 0)
    total_steps = prog.get("total_steps", 16)

    clips = data.get("clips", {})
    available_clips = clips.get("available", [])
    clips_total = clips.get("total", 0)
    clips_success = clips.get("success", 0)

    timestamps = data.get("timestamps", {})
    created_at = timestamps.get("created_at", "")[:19].replace("T", " ") if timestamps.get("created_at") else ""

    error = data.get("error")
    eta = data.get("eta")

    # ─── Format output ────────────────────────────────────────────────────────
    print(f"\n{emoji} Job: {args.job_id}")
    print(f"Status: {status.upper()}")

    if created_at:
        print(f"Dibuat: {created_at}")

    if not is_terminal:
        # Progress bar ASCII
        bar_len = 20
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\nProgress: [{bar}] {pct}%")
        print(f"Step {current_step}/{total_steps}: {step_label}")

        if eta:
            remaining = eta.get("remaining_seconds", 0)
            m, s = divmod(remaining, 60)
            print(f"ETA: ~{m}m {s}s")
    elif status == "completed":
        print(f"\nSelesai! {clips_success}/{clips_total} klip berhasil.")
        if available_clips:
            api_url = os.environ.get("AUTOCLIPER_API_URL", "http://127.0.0.1:8000/api")
            print(f"\nKlip tersedia ({len(available_clips)}):")
            for rank in available_clips:
                print(f"  Klip #{rank}: {api_url}/jobs/{args.job_id}/clips/{rank}/final")
    elif status == "failed":
        print(f"\nError: {error or 'Tidak ada detail error'}")
    elif status == "timeout":
        print("\nJob timeout — coba submit ulang.")

    # Metadata ke stderr
    print(json.dumps({
        "job_id": args.job_id,
        "status": status,
        "progress_pct": pct,
        "clips_available": available_clips,
        "is_terminal": is_terminal,
    }), file=sys.stderr)


if __name__ == "__main__":
    main()
