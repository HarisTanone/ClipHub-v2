"""Migration v9 — indonesian_entity_map table + seed from hardcoded INDONESIAN_ENTITY_MAP.

Replaces hardcoded dict in src/infrastructure/object_image_overlay.py with DB table.
Idempotent.
"""
from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from src.config import settings
    _db_path = settings.db_path
except Exception:
    _db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "autoclip.db")

SEED = [
    ("tepung", "tepung", "wheat flour baking powder", "flour baking dough powder"),
    ("tepung-tepungan", "tepung", "wheat flour baking powder", "flour baking dough powder"),
    ("sayur", "sayuran", "fresh green vegetables", "healthy green vegetables food"),
    ("sayuran", "sayuran", "fresh green vegetables", "healthy green vegetables food"),
    ("sayur-sayuran", "sayuran", "fresh green vegetables", "healthy green vegetables food"),
    ("buah", "buah-buahan", "colorful fresh fruits", "fresh fruits healthy food"),
    ("buahan", "buah-buahan", "colorful fresh fruits", "fresh fruits healthy food"),
    ("buah-buahan", "buah-buahan", "colorful fresh fruits", "fresh fruits healthy food"),
    ("kacang", "kacang", "peanuts almonds nuts", "peanuts almonds nuts legumes"),
    ("kacangan", "kacang", "peanuts almonds nuts", "peanuts almonds nuts legumes"),
    ("kacang-kacangan", "kacang", "peanuts almonds nuts", "peanuts almonds nuts legumes"),
    ("gorengan", "gorengan", "fried snacks food", "asian fried snacks food street"),
    ("goreng-gorengan", "gorengan", "fried snacks food", "asian fried snacks food street"),
    ("obat", "obat", "medicine pills capsules", "medical pills capsules pharmacy"),
    ("obatan", "obat", "medicine pills capsules", "medical pills capsules pharmacy"),
    ("obat-obatan", "obat", "medicine pills capsules", "medical pills capsules pharmacy"),
    ("minuman", "minuman", "refreshing beverage drink", "cold drink iced beverage glass"),
    ("minum-minuman", "minuman", "refreshing beverage drink", "cold drink iced beverage glass"),
    ("manisan", "makanan manis", "sweet dessert pastry", "sweet desserts sugar cookies cake"),
    ("manis-manisan", "makanan manis", "sweet dessert pastry", "sweet desserts sugar cookies cake"),
    ("daging", "daging", "raw fresh beef steak", "beef meat raw steak butcher"),
    ("daging-dagingan", "daging", "fresh meat steak", "beef meat raw steak butcher"),
    ("ikan", "ikan", "fresh fish seafood", "fresh fish seafood market cooking"),
    ("ikan-ikanan", "ikan", "fresh fish seafood", "fresh fish seafood market cooking"),
    ("biji", "biji-bijian", "seeds grains cereals", "chia seeds cereal grains superfood"),
    ("bijian", "biji-bijian", "seeds grains cereals", "chia seeds cereal grains superfood"),
    ("biji-bijian", "biji-bijian", "seeds grains cereals", "chia seeds cereal grains superfood"),
    ("rokok", "rokok", "cigarette pack smoking", "cigarette pack smoking tobacco"),
    ("rokok-rokokan", "rokok", "cigarette pack smoking", "cigarette pack smoking tobacco"),
    ("merokok", "merokok", "smoking cigarette tobacco", "person smoking cigarette tobacco ash"),
    ("makan", "makanan", "eating delicious food", "eating food meal dish"),
    ("minum", "minuman", "drinking beverage glass", "person drinking water beverage glass"),
    ("tidur", "tidur", "sleeping in bed", "person sleeping bed bedroom"),
    ("gula", "gula", "white sugar sweetener", "refined white sugar bowl sweet"),
    ("garam", "garam", "sea salt seasoning", "white sea salt crystals kitchen"),
    ("nasi", "nasi", "cooked white rice bowl", "steamed white rice bowl asian food"),
    ("beras", "beras", "raw rice grains", "uncooked white rice grains raw"),
    ("roti", "roti", "fresh bakery bread", "bakery bread loaf sliced wheat"),
    ("mie", "mie", "noodles ramen bowl", "noodles ramen soup bowl food"),
    ("minyak", "minyak goreng", "cooking olive oil bottle", "cooking olive oil golden bottle"),
    ("susu", "susu", "fresh milk glass bottle", "fresh cow milk glass bottle dairy"),
    ("kopi", "kopi", "coffee cup espresso beans", "fresh hot coffee cup roasted beans"),
    ("teh", "teh", "hot tea cup teapot", "hot green tea cup herbal teapot"),
    ("telur", "telur", "chicken eggs carton", "raw fresh chicken eggs carton"),
    ("ayam", "daging ayam", "fresh chicken meat cooking", "raw fresh chicken meat poultry"),
    ("keju", "keju", "cheese block slice", "cheddar cheese block dairy food"),
    ("madu", "madu", "pure honey jar dipper", "organic pure honey jar golden"),
    ("cokelat", "cokelat", "chocolate bar dark sweet", "dark chocolate bar sweet dessert"),
    ("coklat", "cokelat", "chocolate bar dark sweet", "dark chocolate bar sweet dessert"),
    ("kentang", "kentang", "fresh potato vegetables", "raw fresh potato tubers market"),
    ("tomat", "tomat", "fresh red tomatoes", "ripe red tomatoes fresh vegetable"),
    ("cabai", "cabai", "red hot chili peppers", "fresh red spicy chili peppers"),
    ("cabe", "cabai", "red hot chili peppers", "fresh red spicy chili peppers"),
    ("bawang", "bawang", "fresh red onion garlic", "fresh onion garlic bulb kitchen"),
    ("pisang", "pisang", "fresh yellow bananas", "ripe yellow bananas bunch fruit"),
    ("jeruk", "jeruk", "fresh orange citrus fruit", "fresh orange citrus fruits slice"),
    ("apel", "apel", "fresh red apple fruit", "crisp red apple fruit orchard"),
]


def migrate():
    db_path = _db_path
    print(f"  [v9] indonesian_entity_map → {db_path}")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # Ensure schema
    with open(os.path.join(os.path.dirname(__file__), "..", "schema.sql"), "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM indonesian_entity_map")
    existing = cur.fetchone()[0]
    if existing >= len(SEED):
        print(f"  [v9] already seeded ({existing} rows)")
        conn.close()
        return
    for norm_key, base_word, query_en, query_tags in SEED:
        cur.execute(
            "INSERT OR IGNORE INTO indonesian_entity_map (norm_key, base_word, query_en, query_tags) VALUES (?, ?, ?, ?)",
            (norm_key, base_word, query_en, query_tags),
        )
    conn.commit()
    cur.execute("SELECT count(*) FROM indonesian_entity_map")
    print(f"  [v9] seeded → {cur.fetchone()[0]} rows")
    conn.close()


if __name__ == "__main__":
    migrate()
