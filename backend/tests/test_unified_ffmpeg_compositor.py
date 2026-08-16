"""Unit tests for UnifiedFFmpegCompositor 1-pass video compositing."""
import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.infrastructure.unified_ffmpeg_compositor import UnifiedFFmpegCompositor


@pytest.fixture
def compositor():
    return UnifiedFFmpegCompositor(font_dir="assets/fonts")


def test_build_hook_filter_chain(compositor, tmp_path):
    hook_text = "RAHASIA BESAR TERUNGKAP 🔥"
    style_config = {
        "animation": "zoom_punch",
        "duration": 3.5,
        "fontSize": 72,
        "color": "#FFCC00",
        "strokeWidth": 4,
        "strokeColor": "black",
        "bgOpacity": 0.6,
    }

    filters, files = compositor.build_hook_filter_chain(
        hook_text=hook_text,
        style_config=style_config,
        tmp_dir=str(tmp_path),
    )

    assert len(filters) >= 2  # drawbox + drawtext
    assert any("drawbox" in f for f in filters)
    assert any("drawtext" in f for f in filters)
    assert len(files) == 1
    assert os.path.exists(files[0])

    # Text inside file should be sanitized (emoji removed for drawtext safety)
    with open(files[0], "r", encoding="utf-8") as f:
        content = f.read()
        assert "RAHASIA BESAR TERUNGKAP" in content


def test_build_subtitle_filter_chain(compositor):
    words = [
        {"word": "Ini", "start": 0.0, "end": 0.4},
        {"word": "adalah", "start": 0.4, "end": 0.8},
        {"word": "contoh", "start": 0.8, "end": 1.2},
        {"word": "subtitle", "start": 1.2, "end": 1.6},
        {"word": "karaoke", "start": 1.6, "end": 2.0},
    ]
    style_config = {
        "font_size": 36,
        "highlight_color": "#FFFF00",
        "color": "#FFFFFF",
        "stroke_width": 3,
        "stroke_color": "#000000",
        "max_words_per_line": 3,
    }

    # Default word_pop mode: 1 drawtext per word (5 words = 5 filters)
    filters_word_pop = compositor.build_subtitle_filter_chain(
        words=words,
        style=style_config,
        start_offset=0.0,
    )
    assert len(filters_word_pop) == 5
    assert all("drawtext" in f for f in filters_word_pop)
    assert any("Ini" in f for f in filters_word_pop)
    assert any("karaoke" in f for f in filters_word_pop)

    # Line-based karaoke mode: 5 words / max 3 per line = 2 line filters
    karaoke_config = {**style_config, "line_transition": "none"}
    filters_line = compositor.build_subtitle_filter_chain(
        words=words,
        style=karaoke_config,
        start_offset=0.0,
    )
    assert len(filters_line) == 2
    assert any("Ini adalah contoh" in f for f in filters_line)
    assert any("subtitle karaoke" in f for f in filters_line)


def test_build_watermark_filter_chain_text(compositor, tmp_path):
    watermark_config = {
        "enabled": True,
        "type": "text",
        "text": "@mychannel",
        "fontSize": 28,
        "color": "#FFFFFF",
        "opacity": 80,
        "position": "top-right",
    }

    filter_str, inputs, files = compositor.build_watermark_filter_chain(
        watermark_config=watermark_config,
        tmp_dir=str(tmp_path),
    )

    assert filter_str is not None
    assert "drawtext" in filter_str
    assert "@mychannel" in filter_str
    assert len(inputs) == 0
    assert len(files) == 0


def test_build_watermark_filter_chain_disabled(compositor, tmp_path):
    watermark_config = {
        "enabled": False,
        "text": "test",
    }

    filter_str, inputs, files = compositor.build_watermark_filter_chain(
        watermark_config=watermark_config,
        tmp_dir=str(tmp_path),
    )

    assert filter_str is None
    assert inputs == []
    assert files == []


@pytest.mark.asyncio
async def test_render_single_pass_execution(compositor, tmp_path):
    input_file = tmp_path / "in.mp4"
    input_file.write_bytes(b"dummy-mp4-data")
    output_file = tmp_path / "out.mp4"

    # Mock subprocess creation
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    async def fake_proc(*args, **kwargs):
        # Simulate creating the output file
        output_file.write_bytes(b"rendered-mp4-data")
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_proc) as mock_exec:
        success = await compositor.render_single_pass(
            input_video=str(input_file),
            output_video=str(output_file),
            hook_text="KONTEN VIRAL",
            words=[{"word": "Halo", "start": 0.0, "end": 0.5}],
            watermark_config={"enabled": True, "type": "text", "text": "@cliphub"},
        )

        assert success is True
        assert mock_exec.called
        call_args = mock_exec.call_args[0]
        assert "ffmpeg" in call_args
        assert "-y" in call_args
        assert str(input_file) in call_args
        assert str(output_file) in call_args
