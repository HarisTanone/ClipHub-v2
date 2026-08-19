"""test_stop_words_store.py — Unit tests for persistent dynamic stop words store."""

import json
import os
import tempfile
import pytest

from src.infrastructure.stop_words_store import (
    StopWordsStore,
    get_stop_words_store,
    is_abstract_word,
    learn_abstract_words,
)


def test_stop_words_store_lifecycle():
    with tempfile.TemporaryDirectory() as tmp_dir:
        json_path = os.path.join(tmp_dir, "test_stop_words.json")
        store = StopWordsStore(file_path=json_path)

        # Initial seed words present
        assert store.is_abstract("nyaman") is True
        assert store.is_abstract("mikir") is True
        assert store.is_abstract("karena") is True
        assert store.is_abstract("laptop") is False
        assert store.is_abstract("mobil") is False

        # Learn new dynamic words
        new_words = ["bingung", "kepikiran", "pusing"]
        added = store.learn_words(new_words)
        assert set(added) == set(new_words)
        assert store.is_abstract("bingung") is True
        assert store.is_abstract("kepikiran") is True

        # Verify JSON file on disk was written and contains the new words
        assert os.path.exists(json_path)
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert "bingung" in data["words"]
            assert "kepikiran" in data["words"]
            assert data["total_words"] == len(store.get_words())

        # Reload new store instance from same file
        store2 = StopWordsStore(file_path=json_path)
        assert store2.is_abstract("bingung") is True
        assert store2.is_abstract("kepikiran") is True


def test_stop_words_store_case_and_punctuation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        json_path = os.path.join(tmp_dir, "test_stop_words.json")
        store = StopWordsStore(file_path=json_path)

        # Should handle uppercase, punctuation, and whitespace
        assert store.is_abstract("NYAMAN") is True
        assert store.is_abstract("  mikir...  ") is True
        assert store.is_abstract("karena!") is True

        # Learn with casing and symbols
        added = store.learn_words(["  GELISAH! ", "KHAWATIR..."])
        assert "gelisah" in added
        assert "khawatir" in added
        assert store.is_abstract("GELISAH") is True
        assert store.is_abstract("khawatir") is True
