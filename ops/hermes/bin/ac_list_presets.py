"""
AutoCliper Tool: List Style Presets
Dipanggil oleh Hermes toolset autocliper_list_presets.

Shows both system presets (style_presets table) and user-saved presets (user_presets table).
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
            print(f"[ERROR] Gagal mengambil daftar presets: {e}")
        sys.exit(1)

    presets = result.get("data", [])

    # Also fetch user presets
    user_presets = []
    try:
        user_result = ac_auth.api_get("/presets")
        user_presets = user_result.get("data", [])
    except Exception:
        pass  # User presets optional

    if args.format == "json":
        print(json.dumps({"system": presets, "user": user_presets}, indent=2))
        return

    if not presets and not user_presets:
        print("Tidak ada style preset tersedia.")
        return

    # User presets (Prioritize user custom presets)
    if user_presets:
        print(f"<b>🎨 Preset Kustom Pengguna ({len(user_presets)}):</b>\n")
        for preset in user_presets:
            preset_id = preset.get("id", "unknown")
            preset_slug = preset.get("slug") or f"preset-{preset_id}"
            name = preset.get("name", "Unnamed")
            
            # Format visual details
            hook = preset.get("hook_style") or {}
            sub = preset.get("subtitle_style") or {}
            wm = preset.get("watermark_style") or {}
            cta = preset.get("cta_style") or {}
            
            hook_anim = hook.get("animation") or "default"
            sub_font = sub.get("fontFamily") or sub.get("stylePreset") or "default"
            sub_pos = sub.get("position") or "bottom"
            
            features = []
            if wm.get("enabled"):
                features.append("Watermark")
            if cta.get("enabled"):
                features.append("CTA")
            feat_str = f" | {', '.join(features)}" if features else ""

            print(f"• <b>{name}</b> (Slug: <code>{preset_slug}</code>)")
            print(f"   ↳ Hook: <i>{hook_anim}</i> | Subtitle: <i>{sub_font} ({sub_pos})</i>{feat_str}")
            print(f"   ↳ Command: <code>/submit &lt;url&gt; --preset {preset_slug}</code>\n")

    # System presets
    if presets:
        print("<b>⚙️ System Style Presets:</b>\n")
        for preset in presets:
            preset_id = preset.get("id", "unknown")
            name = preset.get("name", "Unnamed")
            desc = preset.get("description", "")
            desc_text = f" — {desc}" if desc else ""
            print(f"• <code>{preset_id}</code> — {name}{desc_text}")

    # Usage hint
    print("\n<b>💡 Cara Penggunaan:</b>")
    print("<code>/submit &lt;url&gt; --preset &lt;slug&gt;</code>")
    print("<code>/submit &lt;url&gt; --ratio 9:16 --preset &lt;slug&gt;</code>")


if __name__ == "__main__":
    main()
