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

        # Handle empty or 'default' preset identifier: try user's default setting or latest preset
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

            # If still default, check most recent user_preset for user_id
            if not key or key.lower() in ("default", "none"):
                if user_id is not None:
                    cur.execute(
                        "SELECT * FROM user_presets WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                        (user_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        return _format_user_preset_row(row)

                # Fallback to system default setting
                sys_default = getattr(settings, "DEFAULT_STYLE_PRESET", "")
                if sys_default and sys_default.lower() not in ("default", ""):
                    key = sys_default
                else:
                    return None

        # 1. Search user_presets by slug
        query = "SELECT * FROM user_presets WHERE slug = ?"
        params = [key]
        if user_id is not None:
            query += " AND (user_id = ? OR user_id = 1)"
            params.append(user_id)
        cur.execute(query, tuple(params))
        row = cur.fetchone()

        # 2. If not found, try by ID if numeric
        if not row and key.isdigit():
            query = "SELECT * FROM user_presets WHERE id = ?"
            params = [int(key)]
            if user_id is not None:
                query += " AND (user_id = ? OR user_id = 1)"
                params.append(user_id)
            cur.execute(query, tuple(params))
            row = cur.fetchone()

        # 3. If not found, try by name (case-insensitive)
        if not row:
            query = "SELECT * FROM user_presets WHERE LOWER(name) = LOWER(?)"
            params = [key]
            if user_id is not None:
                query += " AND (user_id = ? OR user_id = 1)"
                params.append(user_id)
            cur.execute(query, tuple(params))
            row = cur.fetchone()

        # 4. Fallback search without user_id filter if not found
        if not row:
            cur.execute(
                "SELECT * FROM user_presets WHERE slug = ? OR (id = ? AND ? GLOB '[0-9]*') OR LOWER(name) = LOWER(?)",
                (key, int(key) if key.isdigit() else -1, key, key),
            )
            row = cur.fetchone()

        if row:
            return _format_user_preset_row(row)

        # 5. Search system style_presets table
        cur.execute("SELECT * FROM style_presets WHERE id = ? OR LOWER(name) = LOWER(?)", (key, key))
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

        return None
    except Exception as e:
        logger.warning(f"preset_resolver error for '{key}': {e}")
        return None
    finally:
        conn.close()


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
        "auto_post_platforms": autopost_style.get("platforms", "tiktok,instagram,youtube") if autopost_style else "tiktok,instagram,youtube",
        "auto_post_account_ids": autopost_style.get("account_ids", []) if autopost_style else [],
        "auto_post_schedule_mode": autopost_style.get("schedule_mode", "ai") if autopost_style else "ai",
        "auto_post_custom_time": autopost_style.get("custom_time") if autopost_style else None,
    }
