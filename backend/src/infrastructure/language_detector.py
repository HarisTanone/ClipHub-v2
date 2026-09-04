"""Language Detector — Detect Indonesian vs English for Video Topics & Prompts.

Analyzes input topics and user instructions to classify the target language:
- "id": Bahasa Indonesia
- "en": English
- "other": Other languages

Provides helper functions:
- detect_language(text: str) -> str
- is_indonesian(text: str) -> bool
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# High-frequency Indonesian function words and vocabulary markers
INDONESIAN_WORDS = {
    # Pronouns & determiners
    "yang", "di", "dan", "ini", "itu", "dari", "ke", "pada", "untuk", "dengan",
    "adalah", "sebagai", "oleh", "dalam", "atas", "bisa", "dapat", "tidak", "bukan",
    "tak", "ada", "akan", "telah", "sudah", "sedang", "lagi", "masih", "belum",
    "kami", "kita", "saya", "aku", "mereka", "dia", "kamu", "anda", "kalian",
    # Question words
    "apa", "siapa", "mengapa", "kenapa", "bagaimana", "gimana", "kapan", "dimana",
    "kemana", "darimana", "berapa",
    # Common verbs & nouns in viral/informational topics
    "cara", "tips", "trik", "fakta", "sejarah", "rahasia", "kisah", "cerita",
    "tempat", "wisata", "kuliner", "makanan", "minuman", "resep", "kota", "desa",
    "daerah", "indonesia", "nusantara", "orang", "anak", "bocah", "manusia",
    "bikin", "buat", "membuat", "menjadi", "jadi", "punya", "memiliki", "melihat",
    "lihat", "tahu", "ketahui", "viral", "heboh", "misteri", "keindahan", "alam",
    "gunung", "pantai", "laut", "hutan", "sungai", "budaya", "tradisi", "zaman",
    "dulu", "sekarang", "hari", "tahun", "bulan", "waktu", "dunia", "hidup",
    "mati", "hantu", "seram", "lucu", "kocak", "unik", "aneh", "terbesar",
    "terkecil", "tertua", "terbaru", "terbaik", "terburuk", "terindah", "paling",
    "sangat", "banget", "sekali", "cuma", "hanya", "saja", "juga", "pun",
}

# High-frequency English function words
ENGLISH_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it",
    "for", "not", "on", "with", "he", "as", "you", "do", "at", "this",
    "but", "his", "by", "from", "they", "we", "say", "her", "she", "or",
    "an", "will", "my", "one", "all", "would", "there", "their", "what",
    "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
    "when", "make", "can", "like", "time", "no", "just", "him", "know",
    "take", "people", "into", "year", "your", "good", "some", "could",
    "them", "see", "other", "than", "then", "now", "look", "only", "come",
    "its", "over", "think", "also", "back", "after", "use", "two", "how",
    "our", "work", "first", "well", "way", "even", "new", "want", "because",
    "any", "these", "give", "day", "most", "us", "history", "secret", "facts",
    "guide", "top", "best", "worst", "explore", "discover", "story", "mystery",
}


def detect_language(topic: str, instructions: Optional[str] = None) -> str:
    """Detect the language of a topic and optional instructions.

    Returns:
        "id" for Indonesian, "en" for English, or "other".
    """
    combined = f"{topic or ''} {instructions or ''}".strip().lower()
    if not combined:
        return "id"  # Default to Indonesian if empty

    # Tokenize words (letters only)
    words = re.findall(r"\b[a-z]{2,}\b", combined)
    if not words:
        return "id"

    id_count = sum(1 for w in words if w in INDONESIAN_WORDS)
    en_count = sum(1 for w in words if w in ENGLISH_WORDS)

    # Check Indonesian-specific morphological affixes
    # Prefix: me-, ber-, di-, pe-, se-, ke-, ter-
    # Suffix: -kan, -an, -i, -nya
    id_affix_count = sum(
        1 for w in words
        if (
            (w.startswith(("ber", "meng", "meny", "mem", "men", "ter", "per", "pen")) and len(w) > 4)
            or (w.endswith(("kan", "nya")) and len(w) > 4)
            or ("-" in w)  # Indonesian reduplication like jalan-jalan, anak-anak
        )
    )

    id_score = id_count * 1.5 + id_affix_count
    en_score = en_count * 1.5

    logger.debug(
        f"detect_language: text='{combined[:60]}' -> id_score={id_score}, en_score={en_score}"
    )

    if id_score >= en_score and id_score > 0:
        return "id"
    elif en_score > id_score:
        return "en"

    # Default heuristic: if any Indonesian word is present, favor Indonesian
    if id_count > 0:
        return "id"

    # If mostly English words or no matches, check Latin character ratio
    return "en" if en_score > 0 else "id"


def is_indonesian(topic: str, instructions: Optional[str] = None) -> bool:
    """Return True if the detected language is Indonesian."""
    return detect_language(topic, instructions) == "id"
