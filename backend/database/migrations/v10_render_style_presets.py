"""
Migration v10 — render_style_presets table (DB-driven catalog).

Replaces hardcoded style catalogs:
  - SKIA_HOOK_PRESETS   (skia_hook_renderer.py)      → kind='hook',     engine='skia'
  - FFMPEG_STYLES       (subtitle_styles.py)         → kind='subtitle', engine='ffmpeg'
  - SKIA_STYLES         (subtitle_styles.py)         → kind='subtitle', engine='skia'
  - HOOK_STYLES         (hf_style_catalog.py)        → kind='hook',     engine='hyperframes'
  - SUBTITLE_STYLES     (hf_style_catalog.py)        → kind='subtitle', engine='hyperframes'

Idempotent: INSERT OR IGNORE. Existing rows are never overwritten (admin edits win).
Code fallback dicts remain ONLY as disaster recovery during transition —
lookup path is DB-first everywhere.

Usage:
    python -m database.migrations.v10_render_style_presets
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings


def migrate() -> None:
    db_path = settings.db_path
    print(f"  [v10] render_style_presets → {db_path}")

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS render_style_presets (
            id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('hook','subtitle')),
            engine TEXT NOT NULL CHECK (engine IN ('skia','ffmpeg','hyperframes','remotion')),
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '',
            config TEXT NOT NULL DEFAULT '{}',
            is_active INTEGER NOT NULL DEFAULT 1,
            is_system INTEGER NOT NULL DEFAULT 1,
            is_default INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 100,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (id, kind, engine)
        )
        """
    )

    from src.infrastructure.skia_hook_renderer import SKIA_HOOK_PRESETS
    from src.infrastructure.subtitle_styles import FFMPEG_STYLES, SKIA_STYLES
    from src.infrastructure.hf_style_catalog import HOOK_STYLES as HF_HOOKS, SUBTITLE_STYLES as HF_SUBS

    seeded = 0

    def _seed(rows):
        nonlocal seeded
        for row in rows:
            conn.execute(
                """INSERT OR IGNORE INTO render_style_presets
                   (id, kind, engine, name, description, category, config, is_default, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                row,
            )
            seeded += 1

    # 1. SKIA hook presets — full config JSON
    for i, (sid, cfg) in enumerate(SKIA_HOOK_PRESETS.items()):
        _seed([(sid, "hook", "skia", cfg.get("name", sid), cfg.get("description", ""), "hook",
                json.dumps({k: v for k, v in cfg.items() if k not in ("name", "description")}),
                1 if sid == "skia_impact_badge" else 0, i)])

    # 2. FFmpeg subtitle styles — full config JSON
    for i, (sid, cfg) in enumerate(FFMPEG_STYLES.items()):
        _seed([(sid, "subtitle", "ffmpeg", cfg.get("name", sid), cfg.get("description", ""),
                cfg.get("category", "subtitle"),
                json.dumps({k: v for k, v in cfg.items() if k not in ("id", "name", "description", "category")}),
                1 if sid == "classic_karaoke" else 0, i)])

    # 3. Skia subtitle styles — nested gradient/glow JSON
    for i, (sid, cfg) in enumerate(SKIA_STYLES.items()):
        _seed([(sid, "subtitle", "skia", cfg.get("name", sid), cfg.get("description", ""),
                cfg.get("category", "subtitle"),
                json.dumps({k: v for k, v in cfg.items() if k not in ("id", "name", "description", "category")}),
                1 if sid == "gradient_fill" else 0, i)])

    # 4. HF hook templates — metadata only (implementation lives in hyperframes-renderer)
    for i, s in enumerate(HF_HOOKS):
        _seed([(s["id"], "hook", "hyperframes", s["name"], s.get("description", ""), "hook",
                json.dumps({"design": s["design"], "accent": s["accent"]}),
                1 if s["id"] == "hook_cyber_hud" else 0, i)])

    # 5. HF subtitle templates — metadata only
    for i, s in enumerate(HF_SUBS):
        _seed([(s["id"], "subtitle", "hyperframes", s["name"], s.get("description", ""), "subtitle",
                json.dumps({"design": s["design"], "accent": s["accent"]}),
                0, i)])

    # 6. Remotion hook animations flagged graphical-card (route to Skia high-fidelity render)
    for sid in ("news_portal_pantau", "news_viralin_badge", "news_offset_box",
                "brutalist_bracket", "quote_strip_tape", "paper_clip_scrap",
                "trending_radar", "news_breaking_live"):
        _seed([(sid, "hook", "remotion", sid, "Graphical card hook — routed to Skia renderer", "hook",
                json.dumps({"graphical_card": True}), 0, 500)])

    conn.commit()

    cur = conn.cursor()
    cur.execute("SELECT engine, kind, COUNT(*) FROM render_style_presets WHERE is_active=1 GROUP BY engine, kind")
    for row in cur.fetchall():
        print(f"  [v10] {row[0]}/{row[1]}: {row[2]} presets")
    print(f"  [v10] ✅ render_style_presets table ready ({seeded} seed rows attempted)")
    conn.close()


if __name__ == "__main__":
    migrate()
