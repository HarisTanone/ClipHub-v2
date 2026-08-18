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


def lookup_preset_by_name(name: str) -> str | None:
    """Lookup preset ID by name from API."""
    try:
        result = ac_auth.api_get("/style-presets")
        presets = result.get("data", [])
        for preset in presets:
            if preset.get("id") == name or preset.get("name", "").lower() == name.lower():
                return preset.get("id")
    except Exception:
        pass
    return None


def print_usage():
    """Print detailed usage with preset IDs."""
    print("""
AutoCliper Submit Job Tool
==========================

Usage: ac_submit_job.py --url <youtube_url> [options]

Options:
  --url <URL>              YouTube URL yang akan diproses (WAJIB)
  --style <ID>             Style preset ID (lihat daftar di bawah)
  --ratio <RATIO>          Aspect ratio: 9:16, 16:9, 1:1 (default: 9:16)
  --force <true|false>     Force reprocess (default: false)

Daftar Style Preset IDs yang tersedia:
  • bold_black   - Bold Black style
  • viral        - Viral style dengan highlight tinggi
  • minimal      - Minimal clean style
  • default      - Default style
  • neon_glow    - Neon glow effect
  • retro        - Retro aesthetic
  • tech         - Tech/ futuristik style
  • podcast      - Podcast lower third style

Contoh penggunaan:
  ac_submit_job.py --url https://youtu.be/abc123 --style bold_black --ratio 9:16
  ac_submit_job.py --url https://youtube.com/watch?v=abc123 --style viral --force true
""")


def main():
    parser = argparse.ArgumentParser(
        description="Submit YouTube URL ke AutoCliper"
    )
    parser.add_argument("--url", required=True, help="YouTube URL")
    parser.add_argument("--style", default="", help="Style preset ID or name")
    parser.add_argument("--ratio", default="9:16", help="Aspect ratio")
    parser.add_argument("--force", default="false", help="Force reprocess (true/false)")
    parser.add_argument("--auto-post", default="false", help="Auto post to social media upon completion (true/false)")
    parser.add_argument("--platforms", default="", help="Target social media platforms (comma-separated, e.g. tiktok,instagram,youtube)")
    parser.add_argument("--help-extended", action="store_true", help="Show extended help with preset IDs")
    
    # If user asks for extended help
    if "--help-extended" in sys.argv:
        print_usage()
        return

    args = parser.parse_args()

    force = args.force.lower() in ("true", "1", "yes")
    auto_post = getattr(args, "auto_post", "false").lower() in ("true", "1", "yes")
    platforms = [p.strip() for p in getattr(args, "platforms", "").split(",") if p.strip()]

    # Lookup preset ID jika yang diberikan adalah nama
    preset_id = args.style
    if args.style and args.style.lower() not in ("default", ""):
        found_id = lookup_preset_by_name(args.style)
        if found_id:
            preset_id = found_id
            print(f"✓ Mencocokkan '{args.style}' -> ID: {preset_id}")

    payload = {
        "youtube_url": args.url,
        "style_preset": preset_id,
        "target_aspect_ratio": args.ratio,
        "force_reprocess": force,
        "broll_enabled": True,
        "use_remotion": True,
        "auto_post_social": auto_post,
        "auto_post_platforms": ",".join(platforms),
    }

    print(f"Submitting: {args.url}")
    print(f"Style: {preset_id} | Ratio: {args.ratio} | Force: {force}")
    print("Menghubungi AutoCliper API...")

    result = ac_auth.api_post("/jobs", payload)

    job_id = result.get("job_id", "unknown")
    status = result.get("status", "unknown")
    is_cached = result.get("is_cached", False)

    if is_cached:
        print(f"\n[OK] Job sudah ada (cached): {job_id}")
        print(f"Status: {status}")
        print(f"Gunakan force_reprocess=true untuk proses ulang.")
    else:
        print(f"\n[OK] Job berhasil dibuat!")
        print(f"Job ID: {job_id}")
        print(f"Status: {status}")
        print(f"\nPantau progress dengan: autocliper_job_status job_id={job_id}")

    dashboard_url = ac_auth.get_public_dashboard_url()
    print(f"Dashboard: {dashboard_url}")

    # Metadata ke stderr untuk Hermes
    print(json.dumps({"job_id": job_id, "status": status, "is_cached": is_cached}), file=sys.stderr)


if __name__ == "__main__":
    main()
