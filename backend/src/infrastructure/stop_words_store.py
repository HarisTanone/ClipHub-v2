"""stop_words_store.py — Persistent, self-learning dictionary of abstract / non-visual words.

Maintains a persistent JSON registry of abstract Indonesian and English words that
should NOT be turned into object overlay cards.
Automatically learns and appends new abstract words detected during AI analysis.
"""

import json
import logging
import os
import re
import threading
from typing import Iterable, List, Optional, Set

logger = logging.getLogger(__name__)

# Default seed list in case json file is missing
DEFAULT_ABSTRACT_WORDS = {
    "ada", "adalah", "akhirnya", "akan", "akankah", "apakah", "bagaimana", "bagaimanapun",
    "bahagia", "bahkan", "bahwa", "baik", "banyak", "banget", "beberapa", "begitu", "begini",
    "belum", "benar", "berarti", "berbeda", "berharap", "berikutan", "bersama", "besok",
    "biasa", "biasanya", "bisa", "boleh", "bukan", "bukannya", "cenderung", "coba", "cukup",
    "dalam", "dan", "dapat", "dari", "daripada", "dengan", "depan", "dia", "dimana", "diri",
    "disini", "disitu", "dulu", "enggak", "gapapa", "hanya", "harus", "harusnya", "hingga",
    "ia", "ingin", "ini", "itu", "jadi", "jadinya", "jangan", "jauh", "jelas", "jika", "juga",
    "justru", "kala", "kalau", "kalian", "kami", "kamu", "kapan", "karena", "kadang",
    "kembali", "kemudian", "kemarin", "kenapa", "kenyataan", "kerap", "ketika", "kira",
    "kita", "kurang", "lagi", "lain", "lainnya", "lalu", "lama", "lebih", "lewat", "makanya",
    "maka", "malah", "mampu", "mana", "manakala", "masih", "mau", "memang", "membuat",
    "mempunyai", "menang", "mengapa", "mengenai", "menjadi", "menurut", "merasa", "mereka",
    "meski", "meskipun", "mikir", "mungkin", "namun", "nanti", "nyaman", "nyatanya", "oleh",
    "orang", "pada", "padahal", "paling", "pasti", "pastinya", "penting", "pernah", "pikir",
    "pokoknya", "pun", "punya", "rasa", "rasanya", "saat", "saja", "salah", "sama", "sampai",
    "sana", "sangat", "saya", "seakan", "sebab", "sebagai", "sebagaimana", "sebaliknya",
    "sebanyak", "sebelum", "sebenarnya", "sebuah", "secara", "sedang", "sedangkan", "sedih",
    "sedikit", "segala", "sehingga", "sejak", "sekali", "sekalian", "sekarang", "sekitar",
    "selain", "selalu", "selama", "seluruh", "semakin", "semata", "sementara", "sempat",
    "semua", "semula", "sendiri", "seolah", "seperti", "sering", "serta", "serupa", "sesaat",
    "sesuatu", "setelah", "setiap", "siapa", "sini", "situ", "suatu", "sudah", "sukses",
    "supaya", "tahu", "tanpa", "tapi", "tentang", "tentu", "tepat", "terhadap", "terlalu",
    "termasuk", "ternyata", "tersebut", "terus", "tetapi", "tidak", "tidakkah", "toh",
    "untuk", "wah", "wajar", "walau", "walaupun", "waktu", "yaitu", "yakni", "yang"
}


class StopWordsStore:
    """Thread-safe persistent store for abstract stop-words."""

    def __init__(self, file_path: Optional[str] = None):
        self._lock = threading.RLock()
        self._file_path = file_path or self._resolve_default_path()
        self._words: Set[str] = set()
        self._loaded = False
        self._load()

    def _resolve_default_path(self) -> str:
        """Resolve location of abstract_stop_words.json across different CWDs."""
        candidates = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "data", "abstract_stop_words.json")),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "assets", "data", "abstract_stop_words.json")),
            os.path.abspath(os.path.join(os.getcwd(), "assets", "data", "abstract_stop_words.json")),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        # Default to first candidate
        return candidates[0]

    def _load(self) -> None:
        """Load stop-words from JSON file with memory caching."""
        with self._lock:
            self._words = set(DEFAULT_ABSTRACT_WORDS)
            if os.path.exists(self._file_path):
                try:
                    with open(self._file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        raw_list = data.get("words", []) if isinstance(data, dict) else data
                        if isinstance(raw_list, list):
                            for w in raw_list:
                                clean = re.sub(r"[^\w\-]+", "", str(w or "").strip().lower(), flags=re.UNICODE)
                                if clean:
                                    self._words.add(clean)
                except Exception as exc:
                    logger.warning("StopWordsStore: failed to load %s: %s", self._file_path, exc)
            else:
                self._save()
            self._loaded = True

    def _save(self) -> None:
        """Persist words back to JSON sorted and pretty-printed."""
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
                payload = {
                    "version": "1.0.0",
                    "description": "Dynamic self-learning dictionary of abstract words, conjunctions, and non-physical tokens excluded from object image cards.",
                    "total_words": len(self._words),
                    "words": sorted(list(self._words)),
                }
                with open(self._file_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
            except Exception as exc:
                logger.warning("StopWordsStore: failed to save %s: %s", self._file_path, exc)

    def get_words(self) -> Set[str]:
        """Get copy of all abstract words."""
        with self._lock:
            if not self._loaded:
                self._load()
            return set(self._words)

    def is_abstract(self, word: str) -> bool:
        """Check if a word is an abstract / filler / stop word."""
        if not word:
            return True
        clean = re.sub(r"[^\w\-]+", "", str(word).strip().lower(), flags=re.UNICODE)
        with self._lock:
            if not self._loaded:
                self._load()
            return clean in self._words

    def learn_words(self, new_words: Iterable[str]) -> List[str]:
        """Dynamically add new abstract words to store and persist to JSON file."""
        if not new_words:
            return []
        added: List[str] = []
        with self._lock:
            if not self._loaded:
                self._load()
            for w in new_words:
                clean = re.sub(r"[^\w\-]+", "", str(w or "").strip().lower(), flags=re.UNICODE)
                if clean and len(clean) >= 2 and clean not in self._words:
                    self._words.add(clean)
                    added.append(clean)
            if added:
                self._save()
                logger.info("StopWordsStore: dynamically learned %d new abstract words: %s", len(added), added[:10])
        return added


# Singleton instance
_store_instance: Optional[StopWordsStore] = None


def get_stop_words_store() -> StopWordsStore:
    """Get or initialize singleton StopWordsStore."""
    global _store_instance
    if _store_instance is None:
        _store_instance = StopWordsStore()
    return _store_instance


def is_abstract_word(word: str) -> bool:
    """Helper to check if word is an abstract stop word."""
    return get_stop_words_store().is_abstract(word)


def get_abstract_stop_words() -> Set[str]:
    """Helper to get set of abstract stop words."""
    return get_stop_words_store().get_words()


def learn_abstract_words(words: Iterable[str]) -> List[str]:
    """Helper to add and persist new abstract words."""
    return get_stop_words_store().learn_words(words)
