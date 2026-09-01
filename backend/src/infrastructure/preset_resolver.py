"""Preset Resolver — Resolve style presets from user_presets (by slug/id/name) or style_presets table."""
import json
import logging
from typing import Any, Dict, Optional

from src.config import settings
from src.infrastructure.db_connection import get_dict_connection

logger = logging.getLogger(__name__)


def resolve_preset(
    preset_identifier: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve a preset by slug, ID (or 'user:ID'), or name.
    
    Searches user_presets first (matching user_id if provided or globally),
    then falls back to user default setting or system style_presets table.
    """
    key = str(preset_identifier or "").strip()

    # Strip prefixes like 'user:' or 'preset:'
    if key.lower().startswith("user:"):
        key = key[5:].strip()
    elif key.lower().startswith("preset:"):
        key = key[7:].strip()

    conn = get_dict_connection()
    try:
        cur = conn.cursor()

        # Handle empty or 'default' preset identifier: try user's default setting
        if not key or key.lower() in ("default", "none"):
            # Check user_settings for default_style_preset
            if user_id is not None:
                cur.execute(
                    "SELECT default_style_preset FROM user_settings WHERE user_id = ?",
                    (user_id,),
                )
                user_set = cur.fetchone()
                if user_set and user_set["default_style_preset"]:
                    key = str(user_set["default_style_preset"]).strip()

            # If still default or empty, check user's own latest preset in user_presets
            if user_id is not None and (not key or key.lower() in ("default", "none")):
                cur.execute(
                    "SELECT * FROM user_presets WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                    (user_id,),
                )
                fallback_user_p = cur.fetchone()
                if fallback_user_p:
                    return _format_user_preset_row(fallback_user_p)

            # Otherwise check system DEFAULT_STYLE_PRESET or style_presets
            if not key or key.lower() in ("default", "none"):
                sys_default = getattr(settings, "DEFAULT_STYLE_PRESET", "")
                if sys_default and sys_default.lower() not in ("default", "none", ""):
                    key = sys_default
                else:
                    cur.execute("SELECT * FROM style_presets ORDER BY id ASC LIMIT 1")
                    fallback_sys = cur.fetchone()
                    if fallback_sys:
                        key = str(fallback_sys["id"]).strip()
                    else:
                        return _get_builtin_default_preset()

        slug_norm_dash = key.strip().lower().replace(" ", "-").replace("_", "-")
        slug_norm_under = key.strip().lower().replace(" ", "_").replace("-", "_")

        row = None
        # 1. If user_id is provided, search strictly in this user's user_presets
        if user_id is not None:
            query = (
                "SELECT * FROM user_presets WHERE "
                "(slug = ? OR slug = ? OR slug = ? OR LOWER(name) = LOWER(?)"
                + (" OR id = ?" if key.isdigit() else "")
                + ") AND user_id = ?"
            )
            params = [key, slug_norm_dash, slug_norm_under, key]
            if key.isdigit():
                params.append(int(key))
            params.append(user_id)
            cur.execute(query, tuple(params))
            row = cur.fetchone()
        else:
            # When user_id is None (system background caller without user context)
            query = (
                "SELECT * FROM user_presets WHERE "
                "(slug = ? OR slug = ? OR slug = ? OR LOWER(name) = LOWER(?)"
                + (" OR id = ?" if key.isdigit() else "")
                + ") ORDER BY id DESC LIMIT 1"
            )
            params = [key, slug_norm_dash, slug_norm_under, key]
            if key.isdigit():
                params.append(int(key))
            cur.execute(query, tuple(params))
            row = cur.fetchone()

        if row:
            return _format_user_preset_row(row)

        # 2. Search system style_presets table
        cur.execute(
            "SELECT * FROM style_presets WHERE id = ? OR id = ? OR id = ? OR LOWER(name) = LOWER(?)",
            (key, slug_norm_under, slug_norm_dash, key),
        )
        sys_row = cur.fetchone()
        if sys_row:
            s_dict = dict(sys_row)
            logger.info(f"preset_resolver: resolved system preset '{s_dict.get('id')}'")
            return {
                "source": "system_preset",
                "id": s_dict.get("id"),
                "name": s_dict.get("name"),
                "slug": s_dict.get("id"),
                "hook_style_config": {
                    "animation": s_dict.get("hook_animation", "zoom_in"),
                    "primary_color": s_dict.get("primary_color", "#FFFFFF"),
                    "secondary_color": s_dict.get("secondary_color", "#FFCC00"),
                },
                "subtitle_style_config": {
                    "stylePreset": s_dict.get("id"),
                    "highlightColor": s_dict.get("secondary_color", "#FFCC00"),
                    "position": s_dict.get("subtitle_position", "bottom"),
                },
                "text_emphasis_style_config": {},
                "text_emphasis_enabled": bool(s_dict.get("enable_ai_layer", 0)),
                "watermark_config": {},
                "cta_config": {},
                "broll_config": {},
                "broll_enabled": False,
                "transition_style": "cut",
                "transition_duration": 0.35,
            }

        # 3. If specified preset not found, fall back to user's own latest preset (never another user's preset)
        if user_id is not None:
            cur.execute(
                "SELECT * FROM user_presets WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,),
            )
            last_user_p = cur.fetchone()
            if last_user_p:
                logger.info(f"preset_resolver: falling back to user's own active preset '{last_user_p['name']}' ({last_user_p['slug']})")
                return _format_user_preset_row(last_user_p)

        return _get_builtin_default_preset()
    except Exception as e:
        logger.warning(f"preset_resolver error for '{key}': {e}")
        return _get_builtin_default_preset()
    finally:
        conn.close()


def _get_builtin_default_preset() -> Dict[str, Any]:
    """Fallback preset definition when no database preset is configured."""
    return {
        "source": "builtin_default",
        "id": "default",
        "name": "Default Studio",
        "slug": "default",
        "hook_style_config": {
            "animation": "slide_up",
            "fontFamily": "Montserrat",
            "fontSize": 48,
            "color": "#FFFFFF",
        },
        "subtitle_style_config": {
            "fontFamily": "Montserrat",
            "fontSize": 38,
            "highlightColor": "#00FFCC",
            "position": "bottom",
        },
        "text_emphasis_style_config": {},
        "text_emphasis_enabled": False,
        "watermark_config": {},
        "cta_config": {},
        "broll_config": {},
        "broll_style_config": {},
        "broll_enabled": False,
        "broll_image_overlay": True,
        "broll_behind_person": True,
        "broll_video_footage": True,
        "autogrid_enabled": False,
        "transition_style": "cut",
        "transition_duration": 0.35,
        "hook_engine": "remotion",
        "subtitle_engine": "remotion",
        "autopost_config": {},
        "auto_post_social": False,
        "auto_post_platforms": "tiktok,instagram,youtube",
        "auto_post_account_ids": [],
        "auto_post_schedule_mode": "ai",
        "auto_post_custom_time": None,
    }



def _format_user_preset_row(row) -> Dict[str, Any]:
    """Format user_presets sqlite row into comprehensive preset dictionary."""
    r_dict = dict(row)

    def _parse_json(val):
        if isinstance(val, dict):
            return val
        if isinstance(val, str) and val.strip():
            try:
                return json.loads(val)
            except Exception:
                return {}
        return {}

    hook_style = _parse_json(r_dict.get("hook_style"))
    subtitle_style = _parse_json(r_dict.get("subtitle_style"))
    text_emphasis_style = _parse_json(r_dict.get("text_emphasis_style"))
    watermark_style = _parse_json(r_dict.get("watermark_style"))
    cta_style = _parse_json(r_dict.get("cta_style"))
    broll_style = _parse_json(r_dict.get("broll_style"))
    autopost_style = _parse_json(r_dict.get("autopost_style"))

    has_text_emphasis = bool(
        text_emphasis_style
        and text_emphasis_style.get("effectMode")
        and text_emphasis_style.get("effectMode") != "off"
    )

    logger.info(f"preset_resolver: resolved user preset '{r_dict.get('name')}' (slug: {r_dict.get('slug')})")
    raw_plats = autopost_style.get("platforms", "tiktok,instagram,youtube") if autopost_style else "tiktok,instagram,youtube"
    if isinstance(raw_plats, (list, tuple)):
        plat_str = ",".join(str(p) for p in raw_plats if p)
    else:
        plat_str = str(raw_plats or "")

    return {
        "source": "user_preset",
        "id": r_dict.get("id"),
        "name": r_dict.get("name"),
        "slug": r_dict.get("slug") or f"preset-{r_dict.get('id')}",
        "hook_style_config": hook_style,
        "subtitle_style_config": subtitle_style,
        "text_emphasis_style_config": text_emphasis_style,
        "text_emphasis_enabled": has_text_emphasis,
        "watermark_config": watermark_style,
        "cta_config": cta_style,
        "broll_config": broll_style,
        "broll_style_config": broll_style,
        "broll_enabled": bool(broll_style.get("enabled", False)) if broll_style else False,
        "broll_image_overlay": bool(broll_style.get("image_overlay", True)) if broll_style else True,
        "broll_behind_person": bool(broll_style.get("behind_person", True)) if broll_style else True,
        "broll_video_footage": bool(broll_style.get("video_footage", True)) if broll_style else True,
        "autogrid_enabled": bool(broll_style.get("autogrid_enabled", False)) if broll_style else False,
        "transition_style": hook_style.get("transitionStyle", "cut") if isinstance(hook_style, dict) else "cut",
        "transition_duration": float(hook_style.get("transitionDuration", 0.35)) if isinstance(hook_style, dict) else 0.35,
        "hook_engine": hook_style.get("engine", "remotion") if isinstance(hook_style, dict) else "remotion",
        "subtitle_engine": subtitle_style.get("engine", "remotion") if isinstance(subtitle_style, dict) else "remotion",
        "autopost_config": autopost_style,
        "auto_post_social": bool(autopost_style.get("enabled", False)) if autopost_style else False,
        "auto_post_platforms": plat_str,
        "auto_post_account_ids": autopost_style.get("account_ids", []) if autopost_style else [],
        "auto_post_schedule_mode": autopost_style.get("schedule_mode", "ai") if autopost_style else "ai",
        "auto_post_custom_time": autopost_style.get("custom_time") if autopost_style else None,
    }

