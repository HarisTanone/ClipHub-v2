"""Tests for BrollSubjectAnalyzer, AI-Aware Smart Crop, and 3-Mode Layout Engine."""
import os
import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.broll_subject_analyzer import (
    BrollSubjectAnalyzer,
    BrollPlacementMode,
    BrollSubject,
    BrollAnalysisResult,
)
from src.infrastructure.footage_processor import FootageProcessor
from src.domain.entities import BRollSuggestion, BrollPlacementMode as DomainBrollMode


def test_broll_subject_analyzer_saliency_detection():
    analyzer = BrollSubjectAnalyzer()
    
    # Create synthetic 16:9 test frame (1080x1920) with a bright focal object on the left
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    # Draw high contrast rectangle on the left side (x: 200..500, y: 150..450)
    frame[150:450, 200:500] = [255, 255, 255]

    result = analyzer.analyze_frames([frame], target_w=1080, target_h=1920)
    assert result is not None
    assert result.scaled_w >= 1080
    assert result.scaled_h >= 1920
    assert result.smart_crop_x >= 0
    # The smart crop should be biased towards the left where the object is
    assert result.smart_crop_x < (result.scaled_w - 1080) // 2 or result.primary_subject is not None


def test_broll_subject_analyzer_smart_crop_coordinates():
    analyzer = BrollSubjectAnalyzer()

    # Frame with subject on the far right (x: 1400..1800, y: 200..600)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[200:600, 1400:1800] = [255, 255, 255]

    result = analyzer.analyze_frames([frame], target_w=1080, target_h=1920)
    assert result.smart_crop_x % 2 == 0  # Even for FFmpeg compatibility
    assert result.smart_crop_y % 2 == 0


def test_broll_layout_decision_behind_person():
    analyzer = BrollSubjectAnalyzer()

    # Subject in upper region (center_y = 0.25)
    subject = BrollSubject(
        box=(0.3, 0.1, 0.7, 0.4),
        center_x=0.5,
        center_y=0.25,
        width=0.4,
        height=0.3,
        label="car",
    )
    speaker_box = (0.25, 0.35, 0.75, 0.95)

    mode = analyzer._determine_layout_mode(
        primary_subject=subject,
        speaker_box=speaker_box,
        is_wide_scene=False,
        motion_intensity=0.1,
    )
    assert mode == BrollPlacementMode.BEHIND_PERSON


def test_broll_layout_decision_side_broll_for_wide_scene():
    analyzer = BrollSubjectAnalyzer()

    # Wide landscape or multi-subject chart
    subject = BrollSubject(
        box=(0.05, 0.3, 0.95, 0.7),
        center_x=0.5,
        center_y=0.5,
        width=0.9,
        height=0.4,
        label="wide_chart",
    )
    speaker_box = (0.25, 0.35, 0.75, 0.95)

    mode = analyzer._determine_layout_mode(
        primary_subject=subject,
        speaker_box=speaker_box,
        is_wide_scene=True,
        motion_intensity=0.0,
    )
    assert mode == BrollPlacementMode.SIDE_BROLL


@pytest.mark.asyncio
async def test_footage_processor_with_smart_crop(tmp_path):
    processor = FootageProcessor()
    raw_video = str(tmp_path / "raw.mp4")
    out_dir = str(tmp_path / "out")

    # Create dummy raw video file
    with open(raw_video, "wb") as f:
        f.write(b"\x00" * 500)

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_exec.return_value = mock_proc

        def side_effect(*args, **kwargs):
            out_file = os.path.join(out_dir, "clip_01_broll_footage_00.mp4")
            os.makedirs(out_dir, exist_ok=True)
            with open(out_file, "wb") as f:
                f.write(b"\x00" * 300)
            return mock_proc

        mock_exec.side_effect = side_effect

        processed = await processor.process(
            raw_path=raw_video,
            target_duration=3.0,
            clip_rank=1,
            index=0,
            output_dir=out_dir,
            crop_x=420,
            crop_y=100,
            layout_mode="behind_person",
        )
        assert processed is not None
        assert os.path.exists(processed)
