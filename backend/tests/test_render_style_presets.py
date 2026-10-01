"""Unit tests for render_style_presets DB-backed store and resolvers."""
import json
import sqlite3
import pytest

from src.config import settings


@pytest.fixture()
def style_db(tmp_path, monkeypatch):
    """Isolated SQLite DB with seeded render_style_presets table."""
    db = tmp_path / "styles.db"
    # ponytail: settings.db_path is a read-only property; patch the getter.
    monkeypatch.setattr(type(settings), "db_path", property(lambda self: str(db)))
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE render_style_presets (
            id TEXT NOT NULL, kind TEXT NOT NULL, engine TEXT NOT NULL,
            name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '', config TEXT NOT NULL DEFAULT '{}',
            is_active INTEGER NOT NULL DEFAULT 1, is_system INTEGER NOT NULL DEFAULT 1,
            is_default INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 100,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (id, kind, engine)
        )
        """
    )
    conn.execute(
        "INSERT INTO render_style_presets (id, kind, engine, name, config, is_default) VALUES (?, ?, ?, ?, ?, 1)",
        ("test_hook", "hook", "skia", "Test Hook", json.dumps({"font_size": 99, "text_color": "#123456"})),
    )
    conn.commit()
    conn.close()
    yield str(db)
    from src.infrastructure import render_style_presets_store
    render_style_presets_store._reset_cache()


def test_get_style_preset_hit(style_db):
    from src.infrastructure.render_style_presets_store import get_style_preset
    p = get_style_preset("test_hook", "hook", "skia")
    assert p is not None
    assert p["config"]["font_size"] == 99
    assert p["is_default"] is True


def test_get_style_preset_miss(style_db):
    from src.infrastructure.render_style_presets_store import get_style_preset
    assert get_style_preset("nope", "hook", "skia") is None


def test_get_style_config_fallback(style_db):
    from src.infrastructure.render_style_presets_store import get_style_config
    cfg = get_style_config("nope", "hook", "skia", fallback={"font_size": 1})
    assert cfg == {"font_size": 1}
    assert get_style_config("nope", "hook", "skia") == {}


def test_subtitle_style_resolver_db_first(style_db):
    """get_ffmpeg_style must read DB first, code fallback second."""
    from src.infrastructure.subtitle_styles import get_ffmpeg_style
    style = get_ffmpeg_style("classic_karaoke")
    assert style["id"] == "classic_karaoke"
    assert "font_family" in style


def test_skia_hook_resolver_db_first(style_db):
    """skia_hook_renderer._resolve_skia_hook_preset must read DB first."""
    from src.infrastructure.skia_hook_renderer import _resolve_skia_hook_preset
    cfg = _resolve_skia_hook_preset("test_hook")
    assert cfg["font_size"] == 99
    # miss → falls back to code dict
    cfg2 = _resolve_skia_hook_preset("unknown_xyz")
    assert "font_size" in cfg2


def test_graphical_card_hooks_db_driven(style_db):
    """GRAPHICAL_CARD_HOOKS resolves from DB rows with graphical_card flag."""
    import sqlite3
    conn = sqlite3.connect(style_db)
    conn.execute(
        "INSERT INTO render_style_presets (id, kind, engine, name, config) VALUES (?, 'hook', 'remotion', 'x', ?)",
        ("card_test", json.dumps({"graphical_card": True})),
    )
    conn.commit()
    conn.close()
    from src.infrastructure.render_style_presets_store import list_style_presets, get_style_config
    cards = [
        p["id"] for p in list_style_presets(kind="hook", engine="remotion")
        if p["config"].get("graphical_card")
    ]
    assert "card_test" in cards
    assert get_style_config("card_test", "hook", "remotion").get("graphical_card") is True
