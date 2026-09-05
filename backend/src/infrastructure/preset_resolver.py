"""Preset Resolver — Resolve style presets from user_presets (by slug/id/name) or style_presets table."""
import json
import logging
from typing import Any, Dict, Optional

from src.config import settings
from src.infrastructure.db_connection import get_dict_connection

logger = logging.getLogger(__name__)

# ─── Default Style Constants (100% Parity with Frontend style-editor/types.ts) ───

DEFAULT_HOOK_STYLE: Dict[str, Any] = {
    "animation": "podcast_lower_third",
    "text": "",
    "engine": "remotion",
    "fontFamily": "Barlow Condensed",
    "fontSize": 52,
    "fontWeight": "900",
    "letterSpacing": 0,
    "lineHeight": 1.3,
    "color": "#FFFFFF",
    "gradientEnabled": False,
    "gradientFrom": "#FFFFFF",
    "gradientTo": "#FFCC00",
    "gradientAngle": 180,
    "shadowEnabled": True,
    "shadowColor": "#000000",
    "shadowBlur": 12,
    "shadowX": 0,
    "shadowY": 4,
    "glowEnabled": False,
    "glowColor": "#16F2B3",
    "glowSize": 24,
    "bgColor": "#06111F",
    "bgOpacity": 0.42,
    "position": "bottom",
    "positionY": 78,
    "textAlign": "left",
    "uppercase": True,
    "italic": False,
    "lineEnabled": False,
    "linePosition": "bottom",
    "lineColor": "#16F2B3",
    "lineWidth": 60,
    "lineAutoWidth": False,
    "lineThickness": 4,
    "lineOffset": 12,
    "boxEnabled": False,
    "boxColor": "#FFFFFF",
    "boxOpacity": 0.1,
    "boxPadding": 20,
    "boxRadius": 8,
    "strokeEnabled": False,
    "strokeColor": "#000000",
    "strokeWidth": 3,
    "badgeEnabled": True,
    "badgeText": "ON AIR",
    "footerEnabled": True,
    "footerText": "READ MORE AT chatgpt.com",
    "decorativeElements": True,
    "motionIntensity": 1.0,
    "duration": 3.0,
    "fadeIn": 0.3,
    "fadeOut": 0.3,
    "transitionStyle": "cut",
    "transitionDuration": 0.35,
}

DEFAULT_SUBTITLE_STYLE: Dict[str, Any] = {
    "enabled": True,
    "stylePreset": "classic",
    "engine": "remotion",
    "fontFamily": "Poppins",
    "fontSize": 34,
    "fontWeight": "700",
    "letterSpacing": 0,
    "lineHeight": 1.4,
    "color": "#FFFFFF",
    "highlightColor": "#FFCC00",
    "highlightScale": 1.2,
    "highlightBold": True,
    "highlightStyle": "scale",
    "highlightGlow": False,
    "highlightGlowColor": "#FFCC00",
    "highlightWords": [],
    "dualStyleEnabled": False,
    "highlightFontFamily": "Anton",
    "highlightFontSize": 38,
    "highlightFontWeight": "900",
    "highlightLetterSpacing": 1,
    "highlightItalic": False,
    "highlightUppercase": True,
    "highlightStrokeEnabled": True,
    "highlightStrokeColor": "#000000",
    "highlightStrokeWidth": 3,
    "highlightShadowEnabled": True,
    "highlightShadowColor": "#000000",
    "highlightShadowBlur": 12,
    "bgEnabled": True,
    "bgColor": "#000000",
    "bgOpacity": 0.4,
    "bgRadius": 8,
    "bgPadding": 12,
    "position": "bottom",
    "positionY": 85,
    "uppercase": False,
    "capitalize": False,
    "italic": False,
    "strokeEnabled": True,
    "strokeColor": "#000000",
    "strokeWidth": 2,
    "shadowEnabled": True,
    "shadowColor": "#000000",
    "shadowBlur": 8,
    "maxWordsPerLine": 3,
    "wordSpacing": 4,
    "animationStyle": "pop",
    "animationSpeed": 1.0,
    "lineTransition": "word_pop",
}

DEFAULT_WATERMARK_STYLE: Dict[str, Any] = {
    "enabled": False,
    "type": "text",
    "imageDataUrl": None,
    "text": "@yourchannel",
    "fontFamily": "Poppins",
    "fontSize": 28,
    "fontWeight": "600",
    "color": "#FFFFFF",
    "sizePct": 20,
    "opacity": 60,
    "position": "bottom-right",
    "marginPct": 3,
}

DEFAULT_CTA_STYLE: Dict[str, Any] = {
    "enabled": False,
    "ctaType": "card",
    "template": "follow_badge",
    "duration": 3.0,
    "text": "Jangan lupa follow untuk tips berikutnya!",
    "headline": "Follow For More",
    "subhead": "@yourchannel",
    "buttonText": "FOLLOW",
    "selectedIcon": "tiktok",
    "socialPlatform": "tiktok",
    "socialHandle": "@yourchannel",
    "position": "bottom",
    "bgBox": True,
    "animation": "slide_up",
    "primaryColor": "#10B981",
    "textColor": "#FFFFFF",
    "backgroundColor": "#0F172A",
    "bgOpacity": 90,
    "fontSize": 28,
    "fontFamily": "Poppins",
    "fontWeight": "700",
    "showIcon": True,
    "showArrow": True,
    "avatarUrl": None,
}


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

        # Handle 'active', 'current', 'auto': resolve the user's active / configured preset
        if key.lower() in ("active", "current", "auto"):
            # 1. Check user_settings for default_style_preset
            if user_id is not None:
                cur.execute(
                    "SELECT default_style_preset FROM user_settings WHERE user_id = ?",
                    (user_id,),
                )
                user_set = cur.fetchone()
                if user_set and user_set["default_style_preset"]:
                    cand = str(user_set["default_style_preset"]).strip()
                    if cand.lower() not in ("active", "current", "auto", "default", "none", ""):
                        key = cand

            # 2. Check autopilot_settings for preset_slug if still active/auto
            if user_id is not None and key.lower() in ("active", "current", "auto"):
                cur.execute(
                    "SELECT preset_slug FROM autopilot_settings WHERE user_id = ?",
                    (user_id,),
                )
                auto_set = cur.fetchone()
                if auto_set and auto_set["preset_slug"]:
                    cand_auto = str(auto_set["preset_slug"]).strip()
                    if cand_auto.lower() not in ("active", "current", "auto", "default", "none", ""):
                        key = cand_auto

            # 3. If still active/auto, find the user's latest custom preset
            if user_id is not None and key.lower() in ("active", "current", "auto"):
                cur.execute(
                    "SELECT * FROM user_presets WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                    (user_id,),
                )
                fallback_user_p = cur.fetchone()
                if fallback_user_p:
                    return _format_user_preset_row(fallback_user_p)

            # 4. If user has no custom presets, find latest custom preset globally
            if key.lower() in ("active", "current", "auto"):
                cur.execute("SELECT * FROM user_presets ORDER BY id DESC LIMIT 1")
                global_latest = cur.fetchone()
                if global_latest:
                    logger.info(f"preset_resolver: 'active' resolved to global latest preset '{global_latest['name']}' ({global_latest['slug']})")
                    return _format_user_preset_row(global_latest)
                return _get_builtin_default_preset()

        # Handle 'default', 'none', or empty string
        if not key or key.lower() in ("default", "none"):
            # Check user_settings for default_style_preset
            if user_id is not None:
                cur.execute(
                    "SELECT default_style_preset FROM user_settings WHERE user_id = ?",
                    (user_id,),
                )
                user_set = cur.fetchone()
                if user_set and user_set["default_style_preset"]:
                    cand = str(user_set["default_style_preset"]).strip()
                    if cand.lower() not in ("default", "none", ""):
                        key = cand

            if not key or key.lower() in ("default", "none"):
                # Return standard clean Studio Default with all 5 layers merged
                return _get_builtin_default_preset()

        slug_norm_dash = key.strip().lower().replace(" ", "-").replace("_", "-")
        slug_norm_under = key.strip().lower().replace(" ", "_").replace("-", "_")
        slug_norm_space = key.strip().lower().replace("-", " ").replace("_", " ")

        row = None
        # 1. Search in user's own user_presets if user_id is provided
        if user_id is not None:
            query = (
                "SELECT * FROM user_presets WHERE "
                "(slug = ? OR slug = ? OR slug = ? OR LOWER(name) = ? OR LOWER(name) = ?"
                + (" OR id = ?" if key.isdigit() else "")
                + ") AND user_id = ?"
            )
            params = [key, slug_norm_dash, slug_norm_under, key.lower(), slug_norm_space]
            if key.isdigit():
                params.append(int(key))
            params.append(user_id)
            cur.execute(query, tuple(params))
            row = cur.fetchone()

        # 2. Global search in user_presets across all users (when user_id is None or admin user_id == 1)
        if not row and (user_id is None or user_id == 1):
            query_global = (
                "SELECT * FROM user_presets WHERE "
                "(slug = ? OR slug = ? OR slug = ? OR LOWER(name) = ? OR LOWER(name) = ?"
                + (" OR id = ?" if key.isdigit() else "")
                + ") ORDER BY (user_id = 1) DESC, id DESC LIMIT 1"
            )
            params_g = [key, slug_norm_dash, slug_norm_under, key.lower(), slug_norm_space]
            if key.isdigit():
                params_g.append(int(key))
            cur.execute(query_global, tuple(params_g))
            row = cur.fetchone()
            if row:
                logger.info(
                    f"preset_resolver: resolved preset '{key}' globally from user_presets "
                    f"(id: {row['id']}, name: '{row['name']}', owner user_id: {row['user_id']})"
                )

        if row:
            return _format_user_preset_row(row)

        # 3. Search system style_presets table
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
                    **DEFAULT_HOOK_STYLE,
                    "animation": s_dict.get("hook_animation", "podcast_lower_third"),
                    "color": s_dict.get("primary_color", "#FFFFFF"),
                },
                "subtitle_style_config": {
                    **DEFAULT_SUBTITLE_STYLE,
                    "stylePreset": s_dict.get("id"),
                    "highlightColor": s_dict.get("secondary_color", "#FFCC00"),
                    "position": s_dict.get("subtitle_position", "bottom"),
                },
                "text_emphasis_style_config": {},
                "text_emphasis_enabled": bool(s_dict.get("enable_ai_layer", 0)),
                "watermark_config": dict(DEFAULT_WATERMARK_STYLE),
                "cta_config": dict(DEFAULT_CTA_STYLE),
                "broll_config": {},
                "broll_enabled": False,
                "transition_style": "cut",
                "transition_duration": 0.35,
            }

        # 4. If specified preset not found, log warning and return standard studio default
        logger.warning(f"preset_resolver: Preset '{key}' not found in database. Falling back to clean Studio Default.")
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
        "hook_style_config": dict(DEFAULT_HOOK_STYLE),
        "subtitle_style_config": dict(DEFAULT_SUBTITLE_STYLE),
        "text_emphasis_style_config": {},
        "text_emphasis_enabled": False,
        "watermark_config": dict(DEFAULT_WATERMARK_STYLE),
        "cta_config": dict(DEFAULT_CTA_STYLE),
        "broll_config": {"enabled": True, "image_overlay": True, "behind_person": True, "video_footage": True},
        "broll_style_config": {"enabled": True, "image_overlay": True, "behind_person": True, "video_footage": True},
        "broll_enabled": True,
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
    """Format user_presets sqlite row into comprehensive preset dictionary.
    
    Merges saved user styles with full layer defaults to ensure 100% parity
    with AutopilotPresetPreview.tsx.
    """
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

    # 100% visual parity merge with frontend style defaults
    merged_hook_style = {**DEFAULT_HOOK_STYLE, **(hook_style or {})}
    merged_subtitle_style = {**DEFAULT_SUBTITLE_STYLE, **(subtitle_style or {})}
    merged_watermark_style = {**DEFAULT_WATERMARK_STYLE, **(watermark_style or {})} if watermark_style else dict(DEFAULT_WATERMARK_STYLE)
    merged_cta_style = {**DEFAULT_CTA_STYLE, **(cta_style or {})} if cta_style else dict(DEFAULT_CTA_STYLE)

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

    # B-Roll enabled logic:
    # If broll_style explicitly defines 'enabled', respect it.
    # If broll_style contains options (image_overlay, etc.) but no explicit 'enabled', treat as True.
    # If broll_style is empty or None, treat as False.
    if isinstance(broll_style, dict) and broll_style:
        broll_enabled = bool(broll_style.get("enabled", True))
    else:
        broll_enabled = False

    return {
        "source": "user_preset",
        "id": r_dict.get("id"),
        "name": r_dict.get("name"),
        "slug": r_dict.get("slug") or f"preset-{r_dict.get('id')}",
        "hook_style_config": merged_hook_style,
        "subtitle_style_config": merged_subtitle_style,
        "text_emphasis_style_config": text_emphasis_style,
        "text_emphasis_enabled": has_text_emphasis,
        "watermark_config": merged_watermark_style,
        "cta_config": merged_cta_style,
        "broll_config": broll_style,
        "broll_style_config": broll_style,
        "broll_enabled": broll_enabled,
        "broll_image_overlay": bool(broll_style.get("image_overlay", True)) if broll_style else True,
        "broll_behind_person": bool(broll_style.get("behind_person", True)) if broll_style else True,
        "broll_video_footage": bool(broll_style.get("video_footage", True)) if broll_style else True,
        "autogrid_enabled": bool(broll_style.get("autogrid_enabled", False)) if broll_style else False,
        "transition_style": merged_hook_style.get("transitionStyle") or merged_hook_style.get("transition_style") or "cut",
        "transition_duration": float(merged_hook_style.get("transitionDuration") or merged_hook_style.get("transition_duration") or 0.35),
        "hook_engine": merged_hook_style.get("engine", "remotion"),
        "subtitle_engine": merged_subtitle_style.get("engine", "remotion"),
        "autopost_config": autopost_style,
        "auto_post_social": bool(autopost_style.get("enabled", False)) if autopost_style else False,
        "auto_post_platforms": plat_str,
        "auto_post_account_ids": autopost_style.get("account_ids", []) if autopost_style else [],
        "auto_post_schedule_mode": autopost_style.get("schedule_mode", "ai") if autopost_style else "ai",
        "auto_post_custom_time": autopost_style.get("custom_time") if autopost_style else None,
    }
