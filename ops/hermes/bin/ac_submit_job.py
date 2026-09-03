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
    """Lookup preset slug or ID by name/slug from API."""
    res = lookup_preset_full(name)
    if res:
        return res.get("slug") or str(res.get("id"))
    return name


def lookup_preset_full(name: str) -> dict | None:
    """Lookup full preset object by slug, ID, or name from API."""
    key = str(name or "").strip()
    # Check user presets first (slug, id, or name)
    try:
        user_res = ac_auth.api_get("/presets")
        items = user_res if isinstance(user_res, list) else (user_res.get("data", []) if isinstance(user_res, dict) else [])
        if not key or key.lower() in ("default", "none"):
            # Return latest user preset if available
            if items:
                return items[0]
        for p in items:
            p_slug = str(p.get("slug", "")).lower()
            p_id = str(p.get("id"))
            p_name = str(p.get("name", "")).lower()
            if key.lower() in (p_slug, p_id, p_name):
                return p
    except Exception:
        pass

    # Check system style presets
    try:
        result = ac_auth.api_get("/style-presets")
        items = result if isinstance(result, list) else (result.get("data", []) if isinstance(result, dict) else [])
        for preset in items:
            if key and (preset.get("id") == key or preset.get("name", "").lower() == key.lower()):
                return {
                    "id": preset.get("id"),
                    "name": preset.get("name"),
                    "slug": preset.get("id"),
                    "hook_style": {
                        "animation": preset.get("hook_animation", "podcast_lower_third"),
                        "primary_color": preset.get("primary_color", "#FFFFFF"),
                        "secondary_color": preset.get("secondary_color", "#FFCC00"),
                    },
                    "subtitle_style": {
                        "stylePreset": preset.get("id"),
                        "highlightColor": preset.get("secondary_color", "#FFCC00"),
                        "position": preset.get("subtitle_position", "bottom"),
                    },
                    "watermark_style": {},
                    "cta_style": {},
                    "broll_style": {},
                }
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
  --style <ID>             Style preset ID / slug (lihat daftar di bawah)
  --ratio <RATIO>          Aspect ratio: 9:16, 16:9, 1:1 (default: 9:16)
  --force <true|false>     Force reprocess (default: false)
  --auto-post <true|false> Auto post ke social media setelah selesai
  --platforms <LIST>       Target platform (contoh: tiktok,instagram,youtube)

Gunakan ac_list_presets.py untuk melihat daftar preset lengkap Anda.
""")


def main():
    parser = argparse.ArgumentParser(
        description="Submit YouTube URL ke AutoCliper"
    )
    parser.add_argument("--url", required=True, help="YouTube URL")
    parser.add_argument("--style", default="", help="Style preset ID or slug or name")
    parser.add_argument("--ratio", default="9:16", help="Aspect ratio")
    parser.add_argument("--force", default="false", help="Force reprocess (true/false)")
    parser.add_argument("--auto-post", default="false", help="Auto post to social media upon completion (true/false)")
    parser.add_argument("--platforms", default="", help="Target social media platforms (comma-separated, e.g. tiktok,instagram,youtube)")
    parser.add_argument("--help-extended", action="store_true", help="Show extended help with preset IDs")
    
    if "--help-extended" in sys.argv:
        print_usage()
        return

    args = parser.parse_args()

    force = args.force.lower() in ("true", "1", "yes")
    auto_post = getattr(args, "auto_post", "false").lower() in ("true", "1", "yes")
    platforms = [p.strip() for p in getattr(args, "platforms", "").split(",") if p.strip()]

    # Lookup full preset details
    preset_obj = lookup_preset_full(args.style)
    preset_id = args.style
    if preset_obj:
        preset_id = preset_obj.get("slug") or str(preset_obj.get("id"))
        print(f"✓ Menggunakan Preset '{preset_obj.get('name')}' (Slug: {preset_id})")

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

    # Embed full resolved style configurations if available
    if preset_obj:
        hook_style = preset_obj.get("hook_style") or preset_obj.get("hook_style_config")
        if hook_style and isinstance(hook_style, dict):
            hook_style_dict = dict(hook_style)
            if not hook_style_dict.get("engine"):
                hook_style_dict["engine"] = "remotion"
            payload["hook_style_config"] = hook_style_dict
            if hook_style_dict.get("animation"):
                payload["hook_style"] = hook_style_dict["animation"]
        sub_style = preset_obj.get("subtitle_style") or preset_obj.get("subtitle_style_config")
        if sub_style and isinstance(sub_style, dict):
            payload["subtitle_style_config"] = sub_style
        wm_style = preset_obj.get("watermark_style") or preset_obj.get("watermark_config")
        if wm_style and isinstance(wm_style, dict):
            payload["watermark_config"] = wm_style
        cta_style = preset_obj.get("cta_style") or preset_obj.get("cta_config")
        if cta_style and isinstance(cta_style, dict):
            payload["cta_config"] = cta_style
        te_style = preset_obj.get("text_emphasis_style") or preset_obj.get("text_emphasis_style_config")
        if te_style and isinstance(te_style, dict):
            payload["text_emphasis_style_config"] = te_style
            effect_mode = te_style.get("effectMode")
            is_te_on = bool(
                te_style.get("enabled", True) is not False
                and (not effect_mode or effect_mode != "off")
            )
            payload["text_emphasis_enabled"] = is_te_on
        broll_style = preset_obj.get("broll_style") or preset_obj.get("broll_config")
        if broll_style and isinstance(broll_style, dict):
            payload["broll_enabled"] = bool(broll_style.get("enabled", True))
            payload["broll_image_overlay"] = bool(broll_style.get("image_overlay", True))
            payload["broll_behind_person"] = bool(broll_style.get("behind_person", True))
            payload["broll_video_footage"] = bool(broll_style.get("video_footage", True))
            payload["autogrid_enabled"] = bool(broll_style.get("autogrid_enabled", False))
            if broll_style.get("motion_style"):
                payload["broll_motion_style"] = broll_style.get("motion_style")
        autopost_style = preset_obj.get("autopost_style") or preset_obj.get("autopost_config")
        if autopost_style and isinstance(autopost_style, dict) and not auto_post:
            if autopost_style.get("enabled"):
                payload["auto_post_social"] = True
                payload["auto_post_platforms"] = autopost_style.get("platforms", "")
                payload["auto_post_account_ids"] = autopost_style.get("account_ids", [])
                payload["auto_post_schedule_mode"] = autopost_style.get("schedule_mode", "ai")
                payload["auto_post_custom_time"] = autopost_style.get("custom_time")

    print(f"Submitting: {args.url}")
    print(f"Style: {preset_id or 'auto'} | Ratio: {args.ratio} | Force: {force}")
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
