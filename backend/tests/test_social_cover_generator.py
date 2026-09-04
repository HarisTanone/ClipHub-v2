"""Tests for SocialCoverGenerator (TikTok viral thumbnail cover with Hook, Caption, and Hashtags)."""
import os
import pytest
from PIL import Image

from src.infrastructure.social_cover_generator import (
    generate_social_cover,
    _extract_hashtags_list,
    _wrap_text,
    _load_font,
    PRIMARY_HOOK_FONTS,
)


def test_extract_hashtags_dynamic():
    """Verify that hashtags are dynamically extracted from topic keywords and categories."""
    # Test with list input
    tags1 = _extract_hashtags_list(["ai", "#tech"], topic="Dummy Topic")
    assert "#ai" in [t.lower() for t in tags1]
    assert "#tech" in [t.lower() for t in tags1]

    # Test with string input
    tags2 = _extract_hashtags_list("#Gadget #Smartphone", topic="iPhone 16 Launch")
    assert "#Gadget" in tags2
    assert "#Smartphone" in tags2

    # Test derivation from topic keywords (no hardcoding)
    tags3 = _extract_hashtags_list(None, topic="Peluncuran Roket Antariksa SpaceX Terbaru")
    assert any("Roket" in t or "Antariksa" in t or "Spacex" in t for t in tags3)


def test_generate_social_cover_9_16(tmp_path):
    """Verify generation of full 9:16 vertical TikTok cover thumbnail."""
    out_file = str(tmp_path / "test_tiktok_cover.jpg")

    result = generate_social_cover(
        base_image_path=None,
        output_path=out_file,
        hook_text="RAHASIA AI YANG TIDAK PERNAH DIUNGKAP!",
        caption_text="Simak bagaimana algoritma ini bekerja dalam hitungan detik.",
        hashtags=["#AIViral", "#Teknologi", "#FYP"],
        category_badge="🔥 TRENDING HARI INI",
        aspect_ratio="9:16",
        watermark_text="@cliperhub",
        include_play_indicator=True,
    )

    assert os.path.exists(result)
    assert os.path.getsize(result) > 1000

    # Verify image dimensions
    with Image.open(result) as img:
        assert img.size == (1080, 1920)
        assert img.format == "JPEG"


def test_generate_social_cover_with_base_image(tmp_path):
    """Verify cover generation using an existing video keyframe as base."""
    base_file = str(tmp_path / "raw_frame.png")
    # Create dummy raw frame
    dummy_img = Image.new("RGB", (720, 1280), (60, 80, 120))
    dummy_img.save(base_file)

    out_file = str(tmp_path / "enhanced_thumb.jpg")
    result = generate_social_cover(
        base_image_path=base_file,
        output_path=out_file,
        hook_text="JANGAN SKIP! FAKTA MENGEJUTKAN",
        caption_text="Banyak yang belum tahu kabar terhangat hari ini.",
        hashtags=None,
        category_badge="VIRAL",
        aspect_ratio="9:16",
        watermark_text=None,
        include_play_indicator=True,
    )

    assert os.path.exists(result)
    with Image.open(result) as img:
        assert img.size == (1080, 1920)


def test_generate_social_cover_horizontal_16_9(tmp_path):
    """Verify horizontal YouTube-style 16:9 thumbnail cover."""
    out_file = str(tmp_path / "yt_cover.jpg")

    result = generate_social_cover(
        base_image_path=None,
        output_path=out_file,
        hook_text="KEMAJUAN TEKNOLOGI TERBARU",
        caption_text="Analisis mendalam tren digital global",
        hashtags=["#Tech", "#Shorts"],
        aspect_ratio="16:9",
        include_play_indicator=False,
    )

    assert os.path.exists(result)
    with Image.open(result) as img:
        assert img.size == (1920, 1080)
