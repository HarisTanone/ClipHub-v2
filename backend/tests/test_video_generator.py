from fastapi import HTTPException

from src.application.video_gen_captions import (
    ffmpeg_subtitle_filter,
    normalize_subtitle_style,
    write_ass_subtitles,
)
from src.application.video_generator import VideoGenerator
from src.presentation.routes.video_generator import _parse_byte_range


def test_caption_writer_outputs_timed_karaoke_ass(tmp_path):
    output_path = tmp_path / "captions.ass"
    cue_count = write_ass_subtitles(
        [
            {
                "start_time": 0,
                "duration": 4.2,
                "narration": "This {safe} caption stays in sync.",
            },
            {
                "start_time": 4.2,
                "duration": 2.8,
                "narration": "Every spoken word gets a cue.",
            },
        ],
        output_path,
        {
            "fontFamily": "Poppins",
            "fontSize": 58,
            "color": "#FFFFFF",
            "highlightColor": "#FFCC00",
            "lineTransition": "word_pop",
            "maxWordsPerLine": 3,
        },
    )

    content = output_path.read_text(encoding="utf-8")

    assert cue_count >= 3
    assert "PlayResX: 1080" in content
    assert "Style: Caption,Poppins,58" in content
    assert "&H0000CCFF&" in content
    assert r"\k" in content
    assert r"\{safe\}" in content
    assert "Dialogue: 0,0:00:00.00" in content


def test_caption_style_is_bounded_and_sanitized():
    style = normalize_subtitle_style(
        {
            "fontFamily": "Unsafe; Font <script>",
            "fontSize": 1000,
            "fontWeight": "9999",
            "position": "middle",
            "positionY": -10,
            "maxWordsPerLine": 99,
            "lineTransition": "invalid",
            "color": "not-a-color",
        }
    )

    assert style["fontFamily"] == "Unsafe Font script"
    assert style["fontSize"] == 140
    assert style["fontWeight"] == 950
    assert style["position"] == "bottom"
    assert style["positionY"] == 5
    assert style["maxWordsPerLine"] == 8
    assert style["lineTransition"] == "word_pop"


def test_caption_filter_escapes_ffmpeg_path_characters():
    subtitle_filter = ffmpeg_subtitle_filter("/tmp/video:demo/caption's.ass")

    assert "video\\:demo" in subtitle_filter
    assert "caption\\'s.ass" in subtitle_filter
    assert "original_size=1080x1920" in subtitle_filter


def test_video_generator_preserves_render_choices():
    generator = VideoGenerator()
    job = generator.create_job(
        topic="A precise topic",
        target_duration=65,
        voice="aura-2-orion-en",
        speed=1.15,
        num_scenes=8,
        subtitles_enabled=True,
        subtitle_style={"stylePreset": "neon_pulse", "highlightColor": "#22D3EE"},
        include_bgm=False,
        bgm_volume=0.3,
    )

    assert job.target_duration == 65
    assert job.voice == "aura-2-orion-en"
    assert job.speed == 1.15
    assert job.num_scenes == 8
    assert job.subtitles_enabled is True
    assert job.subtitle_style["stylePreset"] == "neon_pulse"
    assert job.include_bgm is False
    assert job.bgm_volume == 0.3


def test_byte_range_supports_standard_and_suffix_ranges():
    assert _parse_byte_range(None, 1000) == (0, 999)
    assert _parse_byte_range("bytes=100-499", 1000) == (100, 499)
    assert _parse_byte_range("bytes=950-", 1000) == (950, 999)
    assert _parse_byte_range("bytes=-64", 1000) == (936, 999)


def test_byte_range_rejects_invalid_ranges():
    for value in ("bytes=", "bytes=1000-", "bytes=600-500", "items=0-10", "bytes=0-1,4-5"):
        try:
            _parse_byte_range(value, 1000)
        except HTTPException as exc:
            assert exc.status_code == 416
            assert exc.headers == {"Content-Range": "bytes */1000"}
        else:
            raise AssertionError(f"Expected range {value!r} to be rejected")
