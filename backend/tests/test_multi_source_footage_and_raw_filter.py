import asyncio
import os
import cv2
import numpy as np
import pytest

from src.application.video_generator import VideoGenerator
from src.infrastructure.social_footage_searcher import SocialFootageSearcher


@pytest.mark.asyncio
async def test_searcher_universal_and_x_discovery():
    searcher = SocialFootageSearcher()

    # 1. Test universal video candidates
    candidates = await searcher.search_universal_video_candidates(
        query="krakatau detik detik",
        max_results=2,
        is_indonesian=True,
    )
    assert isinstance(candidates, list)
    # The zero-cost video search index should discover video candidates
    if candidates:
        cand = candidates[0]
        assert "url" in cand
        assert "platform" in cand
        assert cand.get("duration_seconds", 0) > 0

    # 2. Test X status video posts discovery
    x_candidates = await searcher.search_x_video_posts(
        query="krakatau",
        max_results=2,
        is_indonesian=True,
    )
    assert isinstance(x_candidates, list)
    for c in x_candidates:
        assert c["platform"] == "x"
        assert "status" in c["url"] or "x.com" in c["url"]


def test_candidate_scoring_raw_vs_edited():
    gen = VideoGenerator()
    scene = {
        "visual": "Erupsi Gunung Anak Krakatau menyemburkan lava merah",
        "narration": "Detik-detik erupsi Gunung Krakatau terekam kamera warga",
        "search_queries": ["krakatau erupsi lava", "gunung krakatau"],
        "duration_estimate": 7,
    }

    # Clean authentic footage from X
    raw_x_cand = {
        "title": "Detik-detik Erupsi Gunung Anak Krakatau Terekam CCTV Warga",
        "query": "krakatau erupsi lava",
        "platform": "x",
        "duration_seconds": 15,
        "is_hd": True,
        "quality": "1080p",
        "height": 1920,
        "view_count": 50000,
    }

    # Edited template / jedag jedug video
    edited_cand = {
        "title": "KRAKATAU JEDAG JEDUG CAPCUT PRESET VIRAL SUB INDO REMIX",
        "query": "krakatau erupsi lava",
        "platform": "tiktok",
        "duration_seconds": 15,
        "is_hd": True,
        "quality": "1080p",
        "height": 1920,
        "view_count": 50000,
    }

    raw_score = gen._score_candidate(raw_x_cand, scene)
    edited_score = gen._score_candidate(edited_cand, scene)

    # Raw candidate should receive high positive score, edited should receive negative score
    assert raw_score > 15.0
    assert edited_score < 0.0
    assert raw_score > edited_score


def test_opencv_burned_in_subtitle_detection():
    gen = VideoGenerator()

    # Create temporary clean and subtitle test videos
    os.makedirs("tmp", exist_ok=True)
    clean_path = "tmp/test_unit_clean.mp4"
    subtitle_path = "tmp/test_unit_sub.mp4"

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")

    # Clean video (pure landscape/abstract animation)
    v_clean = cv2.VideoWriter(clean_path, fourcc, 10, (720, 1280))
    for _ in range(15):
        frame = np.zeros((1280, 720, 3), dtype=np.uint8)
        cv2.circle(frame, (360, 640), 120, (100, 180, 70), -1)
        v_clean.write(frame)
    v_clean.release()

    # Subtitle video (burned-in lower third text line)
    v_sub = cv2.VideoWriter(subtitle_path, fourcc, 10, (720, 1280))
    for _ in range(15):
        frame = np.zeros((1280, 720, 3), dtype=np.uint8)
        cv2.circle(frame, (360, 640), 120, (100, 180, 70), -1)
        cv2.putText(
            frame,
            "DETIK DETIK ERUPSI KRAKATAU SAKSI MATA",
            (40, 1150),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.85,
            (255, 255, 255),
            2,
        )
        v_sub.write(frame)
    v_sub.release()

    try:
        clean_has_text, clean_density = gen.check_video_has_burned_in_text(clean_path)
        sub_has_text, sub_density = gen.check_video_has_burned_in_text(subtitle_path)

        assert clean_has_text is False
        assert sub_has_text is True
        assert sub_density > clean_density
    finally:
        if os.path.exists(clean_path):
            os.remove(clean_path)
        if os.path.exists(subtitle_path):
            os.remove(subtitle_path)
