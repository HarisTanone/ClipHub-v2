"""DB-backed FFmpeg hook styles store.

Reads hook animation styles from `ffmpeg_hook_styles` table.
Falls back to hardcoded defaults if DB unavailable.
"""
import json
import logging
from typing import Any, Optional

from src.infrastructure.db_connection import get_dict_connection

logger = logging.getLogger(__name__)

# Fallback defaults (used only when DB is unavailable)
_FALLBACK_STYLE = {
    "fontsize": 56, "fontcolor": "white", "borderw": 4,
    "bordercolor": "black", "duration": 3.0,
    "font_pref": ["Anton-Regular.ttf", "BebasNeue-Regular.ttf", "Poppins-Bold.ttf"],
    "bg_opacity": 0.6, "y_expr": "h*0.4-text_h/2", "effect": "",
}


def get_ffmpeg_hook_style(style_id: str) -> dict[str, Any]:
    """Get a single FFmpeg hook style by ID. DB first, fallback to hardcoded."""
    try:
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM ffmpeg_hook_styles WHERE id = ? AND is_active = 1",
                (style_id,),
            )
            row = cur.fetchone()
            if row:
                return _row_to_style(row)
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[ffmpeg_styles] DB read failed for {style_id}: {e}")

    return {**_FALLBACK_STYLE}


def get_all_ffmpeg_hook_styles() -> list[dict[str, Any]]:
    """Get all active FFmpeg hook styles."""
    try:
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM ffmpeg_hook_styles WHERE is_active = 1 ORDER BY name"
            )
            rows = cur.fetchall()
            return [_row_to_style(row, include_meta=True) for row in rows]
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[ffmpeg_styles] DB read all failed: {e}")
        return []


def _row_to_style(row, include_meta: bool = False) -> dict[str, Any]:
    """Convert a DB row to style dict."""
    font_pref = row["font_pref"]
    if isinstance(font_pref, str):
        try:
            font_pref = json.loads(font_pref)
        except (json.JSONDecodeError, TypeError):
            font_pref = ["Anton-Regular.ttf"]

    style = {
        "fontsize": row["fontsize"],
        "fontcolor": row["fontcolor"],
        "borderw": row["borderw"],
        "bordercolor": row["bordercolor"],
        "duration": row["duration"],
        "font_pref": font_pref,
        "bg_opacity": row["bg_opacity"],
        "y_expr": row["y_expr"],
        "effect": row["effect"] or "",
    }

    if include_meta:
        style["id"] = row["id"]
        style["name"] = row["name"]
        style["description"] = row["description"]
        style["is_system"] = bool(row["is_system"])

    return style
