"""DB-backed render style presets store.

Reads hook/subtitle style presets from `render_style_presets` table.
DB is canonical. Code dicts (SKIA_HOOK_PRESETS, FFMPEG_STYLES, SKIA_STYLES,
HF catalogs) serve as disaster-recovery fallback ONLY when DB is unavailable.

Precedence:
  1. Active DB row
  2. Hardcoded fallback (transitional, remove after production soak)
"""
import json
import logging
from typing import Any, Optional

from src.infrastructure.db_connection import get_dict_connection

logger = logging.getLogger(__name__)

_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}


def _row_to_preset(row) -> dict[str, Any]:
    config = row["config"]
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except (json.JSONDecodeError, TypeError):
            config = {}
    return {
        "id": row["id"],
        "kind": row["kind"],
        "engine": row["engine"],
        "name": row["name"],
        "description": row["description"],
        "category": row["category"],
        "config": config,
        "is_system": bool(row["is_system"]),
        "is_default": bool(row["is_default"]),
    }


def _reset_cache() -> None:
    _CACHE.clear()


def get_style_preset(preset_id: str, kind: str, engine: str) -> Optional[dict[str, Any]]:
    """Get a single style preset by (id, kind, engine). Returns None if not found."""
    cache_key = (preset_id, kind, engine)
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    try:
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM render_style_presets WHERE id = ? AND kind = ? AND engine = ? AND is_active = 1",
                (preset_id, kind, engine),
            )
            row = cur.fetchone()
            if row:
                preset = _row_to_preset(row)
                _CACHE[cache_key] = preset
                return preset
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[style_presets] DB read failed for {preset_id}/{kind}/{engine}: {e}")
    return None


def get_style_config(preset_id: str, kind: str, engine: str, fallback: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Get merged config dict for a preset. Falls back to provided code dict, then {}."""
    preset = get_style_preset(preset_id, kind, engine)
    if preset:
        return dict(preset["config"])
    if fallback is not None:
        return dict(fallback)
    return {}


def list_style_presets(kind: Optional[str] = None, engine: Optional[str] = None) -> list[dict[str, Any]]:
    """List active presets, optionally filtered by kind and/or engine."""
    try:
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            sql = "SELECT * FROM render_style_presets WHERE is_active = 1"
            params: list[Any] = []
            if kind:
                sql += " AND kind = ?"
                params.append(kind)
            if engine:
                sql += " AND engine = ?"
                params.append(engine)
            sql += " ORDER BY sort_order, name"
            cur.execute(sql, params)
            return [_row_to_preset(row) for row in cur.fetchall()]
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[style_presets] DB list failed: {e}")
        return []
