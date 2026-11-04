"""Database store for AI Image Typography Templates, Fonts, Aspect Ratios, and Accent Presets.

Stores all layout configurations in SQLite tables:
1. `image_typography_templates` — aesthetic typography presets
2. `image_typography_fonts` — available system and custom fonts
3. `image_canvas_aspect_ratios` — canvas dimensions and aspect ratios
4. `image_accent_presets` — curated accent color presets

Allows full dynamic customization from database without changing code.
Zero emoji tolerance.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from src.infrastructure.db_connection import get_dict_connection

logger = logging.getLogger(__name__)

# ─── Default Seeds ───────────────────────────────────────────────────────────

DEFAULT_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "minimal_quote",
        "name": "Minimalist Aesthetic Quote",
        "vibe": "Pinterest Aesthetic, High-fashion, Editorial",
        "primary_font": "Playfair Display",
        "secondary_font": "Inter",
        "recommended_accent": "#EAB308",
        "layout_type": "minimal_quote",
        "is_builtin": 1,
        "is_active": 1,
        "sort_order": 0,
    },
    {
        "id": "bold_editorial",
        "name": "Bold Editorial Magazine",
        "vibe": "Vogue / GQ Masthead, High Contrast, Impact",
        "primary_font": "Anton",
        "secondary_font": "Lora",
        "recommended_accent": "#F59E0B",
        "layout_type": "bold_editorial",
        "is_builtin": 1,
        "is_active": 1,
        "sort_order": 1,
    },
    {
        "id": "skena_magazine",
        "name": "Skena Retro Indie",
        "vibe": "Indie Street Culture, Archival, Highlight Box",
        "primary_font": "Archivo Black",
        "secondary_font": "Oswald",
        "recommended_accent": "#10B981",
        "layout_type": "skena_magazine",
        "is_builtin": 1,
        "is_active": 1,
        "sort_order": 2,
    },
    {
        "id": "brutalist_poster",
        "name": "Neo-Brutalist Poster",
        "vibe": "Stark Borders, Geometric Frame, Monospace",
        "primary_font": "Black Ops One",
        "secondary_font": "Inter",
        "recommended_accent": "#06B6D4",
        "layout_type": "brutalist_poster",
        "is_builtin": 1,
        "is_active": 1,
        "sort_order": 3,
    },
    {
        "id": "luxury_gold",
        "name": "Luxury Gold & Noir",
        "vibe": "Executive, Deep Obsidian, Double Border, Gold",
        "primary_font": "Playfair Display",
        "secondary_font": "Merriweather",
        "recommended_accent": "#D4AF37",
        "layout_type": "luxury_gold",
        "is_builtin": 1,
        "is_active": 1,
        "sort_order": 4,
    },
    {
        "id": "cyberpunk_neon",
        "name": "Cyberpunk Neon Glow",
        "vibe": "Futuristic AI, Glowing Accents, Technical Tag",
        "primary_font": "Righteous",
        "secondary_font": "Titillium Web",
        "recommended_accent": "#00F0FF",
        "layout_type": "cyberpunk_neon",
        "is_builtin": 1,
        "is_active": 1,
        "sort_order": 5,
    },
    {
        "id": "aesthetic_carousel_card",
        "name": "Carousel Insight Card",
        "vibe": "IG & LinkedIn Hook, Slide Indicator, Bullet Points",
        "primary_font": "Poppins",
        "secondary_font": "Inter",
        "recommended_accent": "#8B5CF6",
        "layout_type": "aesthetic_carousel_card",
        "is_builtin": 1,
        "is_active": 1,
        "sort_order": 6,
    },
    {
        "id": "news_bulletin",
        "name": "News Bulletin & Breaking Card",
        "vibe": "Investigation, High Authority, Sharp Tag",
        "primary_font": "Bebas Neue",
        "secondary_font": "Roboto",
        "recommended_accent": "#EF4444",
        "layout_type": "news_bulletin",
        "is_builtin": 1,
        "is_active": 1,
        "sort_order": 7,
    },
    {
        "id": "poetic_whisper",
        "name": "Poetic Whisper",
        "vibe": "Tumblr / Book Aesthetic, Centered Serif, Soft Scrim",
        "primary_font": "Lora",
        "secondary_font": "Raleway",
        "recommended_accent": "#FCD34D",
        "layout_type": "poetic_whisper",
        "is_builtin": 1,
        "is_active": 1,
        "sort_order": 8,
    },
    {
        "id": "modern_business",
        "name": "Modern Business & Creator",
        "vibe": "Twitter/LinkedIn Card, Verified Tag, Clean Lines",
        "primary_font": "Montserrat",
        "secondary_font": "Inter",
        "recommended_accent": "#3B82F6",
        "layout_type": "modern_business",
        "is_builtin": 1,
        "is_active": 1,
        "sort_order": 9,
    },
    {
        "id": "cinematic_film",
        "name": "Cinematic Film Still",
        "vibe": "Movie Letterbox, Director Title, Dialogue Subtitle",
        "primary_font": "Playfair Display",
        "secondary_font": "Barlow Condensed",
        "recommended_accent": "#E2E8F0",
        "layout_type": "cinematic_film",
        "is_builtin": 1,
        "is_active": 1,
        "sort_order": 10,
    },
    {
        "id": "daily_stoic",
        "name": "Daily Stoic Maxim",
        "vibe": "Roman Numeral, Ancient Wisdom, Minimalist Divider",
        "primary_font": "Merriweather",
        "secondary_font": "Inter",
        "recommended_accent": "#F59E0B",
        "layout_type": "daily_stoic",
        "is_builtin": 1,
        "is_active": 1,
        "sort_order": 11,
    },
]

DEFAULT_FONTS: list[dict[str, Any]] = [
    {"id": "playfair_display", "font_name": "Playfair Display", "file_name": "PlayfairDisplay-Variable.ttf", "sort_order": 0},
    {"id": "inter", "font_name": "Inter", "file_name": "Inter-Variable.ttf", "sort_order": 1},
    {"id": "montserrat", "font_name": "Montserrat", "file_name": "Montserrat-Variable.ttf", "sort_order": 2},
    {"id": "anton", "font_name": "Anton", "file_name": "Anton-Regular.ttf", "sort_order": 3},
    {"id": "bebas_neue", "font_name": "Bebas Neue", "file_name": "BebasNeue-Regular.ttf", "sort_order": 4},
    {"id": "poppins", "font_name": "Poppins", "file_name": "Poppins-Bold.ttf", "sort_order": 5},
    {"id": "lora", "font_name": "Lora", "file_name": "Lora-Variable.ttf", "sort_order": 6},
    {"id": "archivo_black", "font_name": "Archivo Black", "file_name": "ArchivoBlack-Regular.ttf", "sort_order": 7},
    {"id": "righteous", "font_name": "Righteous", "file_name": "Righteous-Regular.ttf", "sort_order": 8},
    {"id": "oswald", "font_name": "Oswald", "file_name": "Oswald-Bold.ttf", "sort_order": 9},
    {"id": "merriweather", "font_name": "Merriweather", "file_name": "Merriweather-Bold.ttf", "sort_order": 10},
    {"id": "nunito", "font_name": "Nunito", "file_name": "Nunito-Variable.ttf", "sort_order": 11},
    {"id": "raleway", "font_name": "Raleway", "file_name": "Raleway-Variable.ttf", "sort_order": 12},
    {"id": "bungee", "font_name": "Bungee", "file_name": "Bungee-Regular.ttf", "sort_order": 13},
    {"id": "barlow_condensed", "font_name": "Barlow Condensed", "file_name": "BarlowCondensed-Bold.ttf", "sort_order": 14},
    {"id": "titillium_web", "font_name": "Titillium Web", "file_name": "TitilliumWeb-Bold.ttf", "sort_order": 15},
    {"id": "black_ops_one", "font_name": "Black Ops One", "file_name": "BlackOpsOne-Regular.ttf", "sort_order": 16},
    {"id": "roboto", "font_name": "Roboto", "file_name": "Roboto-Bold.ttf", "sort_order": 17},
    {"id": "lato", "font_name": "Lato", "file_name": "Lato-Bold.ttf", "sort_order": 18},
]

DEFAULT_ASPECT_RATIOS: list[dict[str, Any]] = [
    {
        "id": "9:16",
        "name": "9:16 (Story, Reels, TikTok)",
        "width": 1080,
        "height": 1920,
        "description": "Format vertikal layar penuh untuk konten pendek Instagram Reels, TikTok, YouTube Shorts",
        "sort_order": 0,
    },
    {
        "id": "1:1",
        "name": "1:1 (Persegi Instagram)",
        "width": 1080,
        "height": 1080,
        "description": "Format persegi standar feed Instagram, carousel post, dan LinkedIn",
        "sort_order": 1,
    },
    {
        "id": "4:5",
        "name": "4:5 (Portrait Feed Instagram)",
        "width": 1080,
        "height": 1350,
        "description": "Format portrait vertikal optimal feed Instagram dengan retensi layar maksimal",
        "sort_order": 2,
    },
    {
        "id": "16:9",
        "name": "16:9 (Landscape YouTube)",
        "width": 1920,
        "height": 1080,
        "description": "Format landscape sinematik layar lebar untuk thumbnail atau post YouTube & Twitter",
        "sort_order": 3,
    },
]

DEFAULT_ACCENTS: list[dict[str, Any]] = [
    {"id": "gold", "name": "Gold", "hex": "#D4AF37", "sort_order": 0},
    {"id": "amber", "name": "Amber", "hex": "#F59E0B", "sort_order": 1},
    {"id": "cyan", "name": "Cyan", "hex": "#06B6D4", "sort_order": 2},
    {"id": "emerald", "name": "Emerald", "hex": "#10B981", "sort_order": 3},
    {"id": "rose", "name": "Rose", "hex": "#F43F5E", "sort_order": 4},
    {"id": "purple", "name": "Purple", "hex": "#8B5CF6", "sort_order": 5},
    {"id": "white", "name": "White", "hex": "#FFFFFF", "sort_order": 6},
]


# ─── Table Creation & Seeding ────────────────────────────────────────────────

def ensure_all_typography_tables() -> None:
    """Create all image studio configuration tables in SQLite and seed defaults."""
    conn = get_dict_connection()
    try:
        # 1. Templates Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS image_typography_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                vibe TEXT NOT NULL DEFAULT '',
                primary_font TEXT NOT NULL DEFAULT 'Playfair Display',
                secondary_font TEXT NOT NULL DEFAULT 'Inter',
                recommended_accent TEXT NOT NULL DEFAULT '#EAB308',
                layout_type TEXT NOT NULL DEFAULT 'minimal_quote',
                is_builtin INTEGER NOT NULL DEFAULT 1,
                is_active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Fonts Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS image_typography_fonts (
                id TEXT PRIMARY KEY,
                font_name TEXT UNIQUE NOT NULL,
                file_name TEXT NOT NULL,
                is_builtin INTEGER NOT NULL DEFAULT 1,
                is_active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 3. Canvas Aspect Ratios Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS image_canvas_aspect_ratios (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                is_builtin INTEGER NOT NULL DEFAULT 1,
                is_active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 4. Accent Color Presets Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS image_accent_presets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                hex TEXT NOT NULL,
                is_builtin INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Seed Templates if empty
        cur = conn.execute("SELECT COUNT(*) as c FROM image_typography_templates")
        if cur.fetchone()["c"] == 0:
            for tpl in DEFAULT_TEMPLATES:
                conn.execute(
                    """
                    INSERT INTO image_typography_templates (
                        id, name, vibe, primary_font, secondary_font,
                        recommended_accent, layout_type, is_builtin, is_active, sort_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tpl["id"], tpl["name"], tpl["vibe"], tpl["primary_font"],
                        tpl["secondary_font"], tpl["recommended_accent"], tpl["layout_type"],
                        tpl["is_builtin"], tpl["is_active"], tpl["sort_order"],
                    ),
                )

        # Seed Fonts if empty
        cur = conn.execute("SELECT COUNT(*) as c FROM image_typography_fonts")
        if cur.fetchone()["c"] == 0:
            for f in DEFAULT_FONTS:
                conn.execute(
                    """
                    INSERT INTO image_typography_fonts (
                        id, font_name, file_name, is_builtin, is_active, sort_order
                    ) VALUES (?, ?, ?, 1, 1, ?)
                    """,
                    (f["id"], f["font_name"], f["file_name"], f["sort_order"]),
                )

        # Seed Aspect Ratios if empty
        cur = conn.execute("SELECT COUNT(*) as c FROM image_canvas_aspect_ratios")
        if cur.fetchone()["c"] == 0:
            for ar in DEFAULT_ASPECT_RATIOS:
                conn.execute(
                    """
                    INSERT INTO image_canvas_aspect_ratios (
                        id, name, width, height, description, is_builtin, is_active, sort_order
                    ) VALUES (?, ?, ?, ?, ?, 1, 1, ?)
                    """,
                    (ar["id"], ar["name"], ar["width"], ar["height"], ar["description"], ar["sort_order"]),
                )

        # Seed Accent Presets if empty
        cur = conn.execute("SELECT COUNT(*) as c FROM image_accent_presets")
        if cur.fetchone()["c"] == 0:
            for ac in DEFAULT_ACCENTS:
                conn.execute(
                    """
                    INSERT INTO image_accent_presets (
                        id, name, hex, is_builtin, sort_order
                    ) VALUES (?, ?, ?, 1, ?)
                    """,
                    (ac["id"], ac["name"], ac["hex"], ac["sort_order"]),
                )

        conn.commit()
    finally:
        conn.close()


def ensure_typography_templates_table() -> None:
    """Alias for backwards compatibility."""
    ensure_all_typography_tables()


# ─── Templates CRUD ──────────────────────────────────────────────────────────

def get_all_typography_templates(include_inactive: bool = False) -> list[dict[str, Any]]:
    """Fetch all typography templates from database."""
    ensure_all_typography_tables()
    conn = get_dict_connection()
    try:
        if include_inactive:
            cursor = conn.execute("SELECT * FROM image_typography_templates ORDER BY sort_order ASC, name ASC")
        else:
            cursor = conn.execute("SELECT * FROM image_typography_templates WHERE is_active = 1 ORDER BY sort_order ASC, name ASC")
        return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"[TypographyStore] Failed fetching templates: {e}")
        return DEFAULT_TEMPLATES
    finally:
        conn.close()


def get_typography_template(template_id: str) -> Optional[dict[str, Any]]:
    """Fetch a single typography template by its unique ID."""
    ensure_all_typography_tables()
    conn = get_dict_connection()
    try:
        cursor = conn.execute("SELECT * FROM image_typography_templates WHERE id = ?", (template_id,))
        row = cursor.fetchone()
        return dict(row) if row else next((t for t in DEFAULT_TEMPLATES if t["id"] == template_id), None)
    except Exception as e:
        logger.error(f"[TypographyStore] Failed fetching template {template_id}: {e}")
        return next((t for t in DEFAULT_TEMPLATES if t["id"] == template_id), None)
    finally:
        conn.close()


def create_typography_template(data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new custom typography template into database."""
    ensure_all_typography_tables()
    raw_id = (data.get("id") or "").strip().lower()
    if not raw_id:
        name = (data.get("name") or "custom_template").strip().lower()
        raw_id = re.sub(r"[^a-z0-9]+", "_", name).strip("_")

    template_id = raw_id
    counter = 1
    while get_typography_template(template_id) is not None:
        template_id = f"{raw_id}_{counter}"
        counter += 1

    name = (data.get("name") or "Custom Aesthetic").strip()
    vibe = (data.get("vibe") or "Custom Typography Layout").strip()
    primary_font = (data.get("primary_font") or "Playfair Display").strip()
    secondary_font = (data.get("secondary_font") or "Inter").strip()
    recommended_accent = (data.get("recommended_accent") or "#EAB308").strip()
    layout_type = (data.get("layout_type") or "minimal_quote").strip()
    is_builtin = 1 if data.get("is_builtin") else 0
    is_active = 1 if data.get("is_active", True) else 0
    sort_order = int(data.get("sort_order") or 50)

    conn = get_dict_connection()
    try:
        conn.execute(
            """
            INSERT INTO image_typography_templates (
                id, name, vibe, primary_font, secondary_font,
                recommended_accent, layout_type, is_builtin, is_active, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                template_id, name, vibe, primary_font, secondary_font,
                recommended_accent, layout_type, is_builtin, is_active, sort_order,
            ),
        )
        conn.commit()
        created = get_typography_template(template_id)
        return created or {
            "id": template_id, "name": name, "vibe": vibe,
            "primary_font": primary_font, "secondary_font": secondary_font,
            "recommended_accent": recommended_accent, "layout_type": layout_type,
            "is_builtin": is_builtin, "is_active": is_active, "sort_order": sort_order,
        }
    finally:
        conn.close()


def update_typography_template(template_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Update fields of an existing typography template in database."""
    ensure_all_typography_tables()
    allowed_keys = [
        "name", "vibe", "primary_font", "secondary_font",
        "recommended_accent", "layout_type", "is_active", "sort_order"
    ]
    fields = []
    values = []
    for k in allowed_keys:
        if k in data:
            v = data[k]
            if isinstance(v, bool):
                v = 1 if v else 0
            fields.append(f"{k} = ?")
            values.append(v)

    if not fields:
        return get_typography_template(template_id)

    fields.append("updated_at = CURRENT_TIMESTAMP")
    values.append(template_id)

    conn = get_dict_connection()
    try:
        conn.execute(f"UPDATE image_typography_templates SET {', '.join(fields)} WHERE id = ?", tuple(values))
        conn.commit()
        return get_typography_template(template_id)
    finally:
        conn.close()


def delete_typography_template(template_id: str) -> bool:
    """Delete a typography template from database."""
    ensure_all_typography_tables()
    conn = get_dict_connection()
    try:
        cursor = conn.execute("DELETE FROM image_typography_templates WHERE id = ?", (template_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def reset_typography_templates() -> list[dict[str, Any]]:
    """Reset image_typography_templates to factory default presets."""
    conn = get_dict_connection()
    try:
        conn.execute("DROP TABLE IF EXISTS image_typography_templates")
        conn.commit()
    finally:
        conn.close()
    ensure_all_typography_tables()
    return get_all_typography_templates(include_inactive=True)


# ─── Fonts CRUD ──────────────────────────────────────────────────────────────

def get_all_typography_fonts(include_inactive: bool = False) -> list[dict[str, Any]]:
    """Fetch all fonts from database."""
    ensure_all_typography_tables()
    conn = get_dict_connection()
    try:
        if include_inactive:
            cursor = conn.execute("SELECT * FROM image_typography_fonts ORDER BY sort_order ASC, font_name ASC")
        else:
            cursor = conn.execute("SELECT * FROM image_typography_fonts WHERE is_active = 1 ORDER BY sort_order ASC, font_name ASC")
        return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"[TypographyStore] Failed fetching fonts: {e}")
        return DEFAULT_FONTS
    finally:
        conn.close()


def get_typography_fonts_dict(include_inactive: bool = False) -> dict[str, str]:
    """Fetch map of font_name -> file_name from database."""
    fonts = get_all_typography_fonts(include_inactive=include_inactive)
    return {f["font_name"]: f["file_name"] for f in fonts}


def get_typography_font(font_id_or_name: str) -> Optional[dict[str, Any]]:
    """Fetch a font by its ID or font_name."""
    ensure_all_typography_tables()
    conn = get_dict_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM image_typography_fonts WHERE id = ? OR font_name = ?",
            (font_id_or_name, font_id_or_name),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_typography_font(data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new custom font into database."""
    ensure_all_typography_tables()
    font_name = (data.get("font_name") or "").strip()
    file_name = (data.get("file_name") or "").strip()
    if not font_name or not file_name:
        raise ValueError("font_name and file_name are required")

    font_id = (data.get("id") or "").strip().lower() or re.sub(r"[^a-z0-9]+", "_", font_name.lower()).strip("_")
    sort_order = int(data.get("sort_order") or 50)
    is_active = 1 if data.get("is_active", True) else 0

    conn = get_dict_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO image_typography_fonts (
                id, font_name, file_name, is_builtin, is_active, sort_order
            ) VALUES (?, ?, ?, 0, ?, ?)
            """,
            (font_id, font_name, file_name, is_active, sort_order),
        )
        conn.commit()
        return get_typography_font(font_id) or {"id": font_id, "font_name": font_name, "file_name": file_name}
    finally:
        conn.close()


def update_typography_font(font_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Update font fields in database."""
    ensure_all_typography_tables()
    allowed_keys = ["font_name", "file_name", "is_active", "sort_order"]
    fields = []
    values = []
    for k in allowed_keys:
        if k in data:
            v = data[k]
            if isinstance(v, bool):
                v = 1 if v else 0
            fields.append(f"{k} = ?")
            values.append(v)

    if not fields:
        return get_typography_font(font_id)

    fields.append("updated_at = CURRENT_TIMESTAMP")
    values.append(font_id)

    conn = get_dict_connection()
    try:
        conn.execute(f"UPDATE image_typography_fonts SET {', '.join(fields)} WHERE id = ?", tuple(values))
        conn.commit()
        return get_typography_font(font_id)
    finally:
        conn.close()


def delete_typography_font(font_id: str) -> bool:
    """Delete a custom font from database."""
    ensure_all_typography_tables()
    conn = get_dict_connection()
    try:
        cursor = conn.execute("DELETE FROM image_typography_fonts WHERE id = ?", (font_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def reset_typography_fonts() -> list[dict[str, Any]]:
    """Reset image_typography_fonts to factory defaults."""
    conn = get_dict_connection()
    try:
        conn.execute("DROP TABLE IF EXISTS image_typography_fonts")
        conn.commit()
    finally:
        conn.close()
    ensure_all_typography_tables()
    return get_all_typography_fonts(include_inactive=True)


# ─── Aspect Ratios & Resolutions CRUD ────────────────────────────────────────

def get_all_aspect_ratios(include_inactive: bool = False) -> list[dict[str, Any]]:
    """Fetch all canvas aspect ratios and dimensions from database."""
    ensure_all_typography_tables()
    conn = get_dict_connection()
    try:
        if include_inactive:
            cursor = conn.execute("SELECT * FROM image_canvas_aspect_ratios ORDER BY sort_order ASC, id ASC")
        else:
            cursor = conn.execute("SELECT * FROM image_canvas_aspect_ratios WHERE is_active = 1 ORDER BY sort_order ASC, id ASC")
        return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"[TypographyStore] Failed fetching aspect ratios: {e}")
        return DEFAULT_ASPECT_RATIOS
    finally:
        conn.close()


def get_resolutions_dict(include_inactive: bool = False) -> dict[str, tuple[int, int]]:
    """Fetch map of aspect ratio ID (e.g. '9:16') -> (width, height) from database."""
    items = get_all_aspect_ratios(include_inactive=include_inactive)
    return {ar["id"]: (int(ar["width"]), int(ar["height"])) for ar in items}


def get_aspect_ratio(aspect_id: str) -> Optional[dict[str, Any]]:
    """Fetch a single aspect ratio by its ID (e.g. '9:16')."""
    ensure_all_typography_tables()
    conn = get_dict_connection()
    try:
        cursor = conn.execute("SELECT * FROM image_canvas_aspect_ratios WHERE id = ?", (aspect_id,))
        row = cursor.fetchone()
        return dict(row) if row else next((ar for ar in DEFAULT_ASPECT_RATIOS if ar["id"] == aspect_id), None)
    finally:
        conn.close()


def create_aspect_ratio(data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new canvas aspect ratio and dimension into database."""
    ensure_all_typography_tables()
    aspect_id = (data.get("id") or "").strip()
    name = (data.get("name") or aspect_id).strip()
    width = int(data.get("width") or 1080)
    height = int(data.get("height") or 1920)
    description = (data.get("description") or "").strip()
    is_active = 1 if data.get("is_active", True) else 0
    sort_order = int(data.get("sort_order") or 50)

    if not aspect_id:
        raise ValueError("aspect ratio id is required (e.g. '3:4')")

    conn = get_dict_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO image_canvas_aspect_ratios (
                id, name, width, height, description, is_builtin, is_active, sort_order
            ) VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (aspect_id, name, width, height, description, is_active, sort_order),
        )
        conn.commit()
        return get_aspect_ratio(aspect_id) or {"id": aspect_id, "name": name, "width": width, "height": height}
    finally:
        conn.close()


def update_aspect_ratio(aspect_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Update aspect ratio in database."""
    ensure_all_typography_tables()
    allowed_keys = ["name", "width", "height", "description", "is_active", "sort_order"]
    fields = []
    values = []
    for k in allowed_keys:
        if k in data:
            v = data[k]
            if isinstance(v, bool):
                v = 1 if v else 0
            fields.append(f"{k} = ?")
            values.append(v)

    if not fields:
        return get_aspect_ratio(aspect_id)

    fields.append("updated_at = CURRENT_TIMESTAMP")
    values.append(aspect_id)

    conn = get_dict_connection()
    try:
        conn.execute(f"UPDATE image_canvas_aspect_ratios SET {', '.join(fields)} WHERE id = ?", tuple(values))
        conn.commit()
        return get_aspect_ratio(aspect_id)
    finally:
        conn.close()


def delete_aspect_ratio(aspect_id: str) -> bool:
    """Delete a custom aspect ratio from database."""
    ensure_all_typography_tables()
    conn = get_dict_connection()
    try:
        cursor = conn.execute("DELETE FROM image_canvas_aspect_ratios WHERE id = ?", (aspect_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def reset_aspect_ratios() -> list[dict[str, Any]]:
    """Reset aspect ratios to factory defaults."""
    conn = get_dict_connection()
    try:
        conn.execute("DROP TABLE IF EXISTS image_canvas_aspect_ratios")
        conn.commit()
    finally:
        conn.close()
    ensure_all_typography_tables()
    return get_all_aspect_ratios(include_inactive=True)


# ─── Accent Presets CRUD ─────────────────────────────────────────────────────

def get_all_accent_presets() -> list[dict[str, Any]]:
    """Fetch all accent color presets from database."""
    ensure_all_typography_tables()
    conn = get_dict_connection()
    try:
        cursor = conn.execute("SELECT * FROM image_accent_presets ORDER BY sort_order ASC, id ASC")
        return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"[TypographyStore] Failed fetching accent presets: {e}")
        return DEFAULT_ACCENTS
    finally:
        conn.close()
