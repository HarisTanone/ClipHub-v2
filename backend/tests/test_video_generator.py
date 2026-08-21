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


def test_delete_video_generator_job(tmp_path):
    generator = VideoGenerator(output_dir=str(tmp_path))
    job = generator.create_job(topic="Test Delete Job")
    job_id = job.job_id

    assert generator.get_job(job_id) is not None

    deleted = generator.delete_job(job_id)
    assert deleted is True
    assert generator.get_job(job_id) is None


def test_story_agent_parses_truncated_json():
    from src.infrastructure.story_agent import StoryAgent

    agent = StoryAgent()
    # Truncated mid-string without closing array/braces
    truncated_raw = """```json
{
  "title": "The Programmer Who Never Sleeps",
  "hook": "At 3 AM, when the world is silent, one developer pushes thousands of commits.",
  "mood": "mysterious",
  "target_duration": 65,
  "scenes": [
    {
      "id": 1,
      "narration": "At 3 AM, when the world is completely silent, one developer is awake.",
      "visual": "Dark room illuminated only by glowing monitor",
      "search_queries": ["developer coding at night dark room"]
    },
    {
      "id": 2,
      "narration": "Lines of code fly across multiple screens like a digital symphony.",
      "visual": "Fast scrolling terminal code green text",
      "search_queries": ["matrix terminal code scrolling"]
    },
    {
      "id": 3,
      "narration": "Coffee cups pile up beside the keyboard
"""
    story = agent._parse_response(truncated_raw, "The Programmer")
    assert story["title"] == "The Programmer Who Never Sleeps"
    assert len(story["scenes"]) >= 2
    assert story["scenes"][0]["id"] == 1
    assert "developer" in story["scenes"][0]["narration"]


def test_retry_video_generator_job_in_place(tmp_path):
    from src.application.video_generator import VideoGenStatus

    generator = VideoGenerator(output_dir=str(tmp_path))
    job = generator.create_job(topic="Retry Test")
    job.status = VideoGenStatus.FAILED
    job.error = "Original failure reason"
    job.progress = 45
    generator._persist_job(job)

    retried = generator.retry_job(job.job_id)
    assert retried.job_id == job.job_id
    assert retried.status == VideoGenStatus.QUEUED
    assert retried.error is None
    assert retried.progress == 0

    fetched = generator.get_job(job.job_id)
    assert fetched is not None
    assert fetched.status == VideoGenStatus.QUEUED
    assert fetched.error is None


def test_normalize_subtitle_style_preserves_custom_words_per_line_and_font():
    # User specified maxWordsPerLine=1 (word by word) with meme_impact preset
    style = normalize_subtitle_style({
        "stylePreset": "meme_impact",
        "maxWordsPerLine": 1,
        "fontSize": 72,
        "fontFamily": "Montserrat",
    })
    assert style["maxWordsPerLine"] == 1
    assert style["fontSize"] == 72
    assert style["fontFamily"] == "Montserrat"

    # User specified maxWordsPerLine=6 with classic preset
    style6 = normalize_subtitle_style({
        "stylePreset": "classic",
        "maxWordsPerLine": 6,
    })
    assert style6["maxWordsPerLine"] == 6


def test_video_generator_preserves_hook_configuration():
    generator = VideoGenerator()
    job = generator.create_job(
        topic="Hook test",
        hook_enabled=True,
        custom_hook="CUSTOM HOOK HEADLINE",
        hook_style={"animation": "skia_neon_cyberpunk", "fontSize": 50},
    )

    assert job.hook_enabled is True
    assert job.custom_hook == "CUSTOM HOOK HEADLINE"
    assert job.hook_style["animation"] == "skia_neon_cyberpunk"

    fetched = generator.get_job(job.job_id)
    assert fetched is not None
    assert fetched.hook_enabled is True
    assert fetched.custom_hook == "CUSTOM HOOK HEADLINE"
    assert fetched.hook_style.get("animation") == "skia_neon_cyberpunk"


import pytest
from unittest.mock import AsyncMock
from src.domain.entities import VideoCandidate
from src.infrastructure.footage_downloader import FootageDownloader


@pytest.mark.asyncio
async def test_footage_downloader_download_segment_routing(monkeypatch, tmp_path):
    downloader = FootageDownloader(output_dir=str(tmp_path))

    mock_direct = AsyncMock(return_value="/tmp/direct.mp4")
    mock_yt = AsyncMock(return_value="/tmp/yt.mp4")
    monkeypatch.setattr(downloader, "_download_direct", mock_direct)
    monkeypatch.setattr(downloader, "_download_youtube", mock_yt)

    # 1. Pexels/Direct URL
    res_direct = await downloader.download_segment(
        url="https://images.pexels.com/videos/123/video.mp4",
        start_time=0.0,
        duration=7.5,
        scene_id=1,
        platform="pexels",
        video_id="pexels_123",
    )
    assert res_direct == "/tmp/direct.mp4"
    mock_direct.assert_called_once_with(
        url="https://images.pexels.com/videos/123/video.mp4",
        video_id="pexels_123",
    )

    # 2. YouTube URL
    res_yt = await downloader.download_segment(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        start_time=15.0,
        duration=8.0,
        scene_id=2,
        platform="youtube",
        video_id="dQw4w9WgXcQ",
    )
    assert res_yt == "/tmp/yt.mp4"
    mock_yt.assert_called_once_with(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        start_ts=15,
        duration_needed=8.0,
        video_id="dQw4w9WgXcQ",
    )

    # 3. download() with dict candidate
    dict_cand = {
        "platform": "pixabay",
        "url": "https://cdn.pixabay.com/video/123.mp4",
        "video_id": "pixabay_123",
        "start_timestamp": 0,
    }
    res_cand = await downloader.download(dict_cand, duration_needed=5.0)
    assert res_cand == "/tmp/direct.mp4"

    # 4. download() with VideoCandidate object
    vc = VideoCandidate(
        id="vc_456",
        platform="pexels",
        embed_url="https://images.pexels.com/videos/456.mp4",
    )
    res_vc = await downloader.download(vc, duration_needed=6.0)
    assert res_vc == "/tmp/direct.mp4"


def test_video_generator_multi_worker_db_sync(tmp_path):
    from src.application.video_generator import VideoGenStatus
    from src.infrastructure.db_connection import get_dict_connection

    # Simulate Worker 1
    worker1_generator = VideoGenerator(output_dir=str(tmp_path))
    job = worker1_generator.create_job(topic="Multi Worker Test")
    job.status = VideoGenStatus.AWAITING_SELECTION
    worker1_generator._jobs[job.job_id] = job
    worker1_generator._persist_job(job)

    # Simulate Worker 2 updating DB directly (rendering complete)
    conn = get_dict_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE video_generator_jobs SET status = ?, output_path = ? WHERE job_id = ?",
        (VideoGenStatus.COMPLETED.value, "/tmp/final_video.mp4", job.job_id),
    )
    conn.commit()
    conn.close()

    # Worker 1 receives stream/status request — must read fresh COMPLETED status from DB
    fetched = worker1_generator.get_job(job.job_id)
    assert fetched is not None
    assert fetched.status == VideoGenStatus.COMPLETED
    assert fetched.output_path == "/tmp/final_video.mp4"


import pytest


@pytest.mark.asyncio
async def test_elevenlabs_tts_models_and_voices():
    from src.infrastructure.elevenlabs_tts import ElevenLabsTTS

    # Models fetching test with fallback
    models = await ElevenLabsTTS.fetch_models(api_key="test-key")
    assert len(models) > 0
    assert any(m["model_id"] == "eleven_multilingual_v2" for m in models)

    # Voices fetching test with fallback
    voices = await ElevenLabsTTS.fetch_voices(api_key="test-key")
    assert len(voices) > 0
    assert any("rUOpAdbAl56KxO00wR5D" in str(v.get("voice_id")) for v in voices)


def test_video_generator_tts_provider_persistence(tmp_path):
    generator = VideoGenerator(output_dir=str(tmp_path))

    job1 = generator.create_job(
        topic="ElevenLabs Test",
        tts_provider="elevenlabs",
        tts_model="eleven_turbo_v2_5",
        voice="rUOpAdbAl56KxO00wR5D",
    )
    assert job1.tts_provider == "elevenlabs"
    assert job1.tts_model == "eleven_turbo_v2_5"
    assert job1.voice == "rUOpAdbAl56KxO00wR5D"

    # Verify DB persistence and retrieval
    fetched1 = generator.get_job(job1.job_id)
    assert fetched1 is not None
    assert fetched1.tts_provider == "elevenlabs"
    assert fetched1.tts_model == "eleven_turbo_v2_5"

    job2 = generator.create_job(
        topic="Deepgram Test",
        tts_provider="deepgram",
        voice="aura-2-thalia-en",
    )
    assert job2.tts_provider == "deepgram"
    fetched2 = generator.get_job(job2.job_id)
    assert fetched2 is not None
    assert fetched2.tts_provider == "deepgram"


def test_system_config_contains_elevenlabs_keys():
    from src.infrastructure.system_config_store import SYSTEM_SETTINGS_METADATA, get_all_settings_for_role

    keys = set(SYSTEM_SETTINGS_METADATA.keys())

    assert "ELEVENLABS_API_KEY" in keys
    assert "ELEVENLABS_VOICE_ID" in keys
    assert "ELEVENLABS_MODEL_ID" in keys
    assert "VIDEO_GEN_TTS_PROVIDER" in keys
    assert "DEEPGRAM_API_KEY" in keys

    settings_list = get_all_settings_for_role("superadmin")
    rendered_keys = {item["key"] for item in settings_list}
    assert "ELEVENLABS_API_KEY" in rendered_keys
    assert "VIDEO_GEN_TTS_PROVIDER" in rendered_keys


def test_story_agent_minimum_six_scenes():
    from src.infrastructure.story_agent import StoryAgent

    agent = StoryAgent()
    # Mock story with only 2 long scenes
    short_story = {
        "title": "Ocean Depths",
        "hook": "Deep ocean creatures live in extreme dark.",
        "scenes": [
            {
                "id": 1,
                "narration": "Deep below the surface lies a world where sunlight never reaches. Creatures have evolved bizarre glowing bioluminescence to hunt and communicate.",
                "visual": "Bioluminescent anglerfish swimming in pitch black ocean water",
                "search_queries": ["bioluminescent anglerfish dark ocean 4k", "deep sea creatures abyss"],
            },
            {
                "id": 2,
                "narration": "Massive pressures could crush a submarine in seconds. Yet flexible cell membranes allow these deep sea dwellers to thrive in the Mariana Trench.",
                "visual": "Mariana trench floor with extreme pressure submersible camera exploration",
                "search_queries": ["mariana trench sea floor 4k", "submarine underwater exploration"],
            },
        ],
    }

    fixed = agent._validate_and_fix(short_story, target_duration=60)
    assert len(fixed["scenes"]) >= 6
    for i, sc in enumerate(fixed["scenes"]):
        assert sc["id"] == i + 1
        assert len(sc["narration"]) > 0
        assert len(sc["search_queries"]) > 0


def test_video_generator_semantic_scoring(tmp_path):
    generator = VideoGenerator(output_dir=str(tmp_path))
    scene = {
        "visual": "Cyberpunk neon reflection in human eye",
        "narration": "Can artificial intelligence truly develop genuine human emotions and consciousness?",
        "search_queries": ["cyberpunk neon human eye reflection", "ai consciousness digital brain 4k"],
        "duration_estimate": 6.5,
    }

    cand_relevant = {
        "title": "Macro Close Up Eye Glowing Smartphone Screen Reflection Cinematic",
        "query": "cyberpunk neon reflection human pupil vertical",
        "platform": "pexels",
        "duration_seconds": 12,
        "view_count": 50000,
    }

    cand_irrelevant = {
        "title": "How to bake chocolate cake easy recipe",
        "query": "baking cake kitchen",
        "platform": "youtube",
        "duration_seconds": 300,
        "view_count": 1000,
    }

    score_rel = generator._score_candidate(cand_relevant, scene)
    score_irrel = generator._score_candidate(cand_irrelevant, scene)
    assert score_rel > score_irrel
    assert score_rel > 5.0


def test_simplify_stock_query():
    from src.infrastructure.youtube_search import simplify_stock_query

    # Verifies stripping of filmmaking filler buzzwords
    raw_query = "slow motion cybernetic digital face scan tracking data 4k"
    simplified = simplify_stock_query(raw_query)
    assert "4k" not in simplified
    assert "slow" not in simplified
    assert "motion" not in simplified
    assert "cybernetic" in simplified or "digital" in simplified or "face" in simplified

    raw_query2 = "macro close up deep ocean submarine abyss cinematic b-roll"
    simplified2 = simplify_stock_query(raw_query2)
    assert "cinematic" not in simplified2
    assert "b-roll" not in simplified2
    assert "submarine" in simplified2 or "ocean" in simplified2


@pytest.mark.asyncio
async def test_ai_director_curation_pass():
    from src.infrastructure.story_agent import StoryAgent

    agent = StoryAgent()
    scenes = [
        {
            "id": 1,
            "narration": "Deep sea exploration in the Mariana Trench.",
            "visual": "Submarine in dark ocean water",
            "footage_candidates": [
                {
                    "video_id": "pexels_101",
                    "title": "Submarine diving in dark deep ocean water",
                    "platform": "pexels",
                },
                {
                    "video_id": "pexels_102",
                    "title": "Woman surfing on sunny beach",
                    "platform": "pexels",
                },
            ],
        }
    ]

    # Test parsing curation JSON response
    mock_curation = '{"curation": [{"scene_id": 1, "chosen_option_index": 0, "reason": "Accurate submarine ocean shot"}]}'
    parsed = agent._parse_curation_response(mock_curation)
    assert len(parsed.get("curation", [])) == 1
    assert parsed["curation"][0]["chosen_option_index"] == 0


def test_all_style_editor_hook_presets():
    from src.infrastructure.skia_hook_renderer import SkiaHookRenderer, SKIA_HOOK_PRESETS

    renderer = SkiaHookRenderer()
    sample_text = "WHAT IF EARTH STOPPED SPINNING... RIGHT NOW?"

    expected_hook_presets = [
        "news_viralin_badge", "news_portal_pantau", "news_offset_box",
        "brutalist_bracket", "quote_strip_tape", "podcast_lower_third",
        "quote_card", "waveform_pulse", "breaking_tape", "mic_drop",
        "split_panel", "kinetic_stack", "glass_flash", "marker_swipe",
        "signal_scan", "comment_reply", "search_prompt", "countdown_list", "pov_stamp",
        "skia_impact_badge", "skia_neon_cyberpunk", "skia_frosted_pill",
    ]

    for preset_id in expected_hook_presets:
        assert preset_id in SKIA_HOOK_PRESETS
        frame = renderer.generate_hook_frame(sample_text, hook_style=preset_id)
        assert frame.size == (1080, 1920)
        assert frame.mode == "RGBA"


def test_all_style_editor_subtitle_presets():
    from src.application.video_gen_captions import normalize_subtitle_style, ALL_SUBTITLE_PRESETS

    presets_to_test = [
        "hormozi_pop", "neon_glow", "devon_clean", "podcast_dialogue",
        "cinematic_slate", "fire_emphasis", "tech_mono", "gold_luxury",
        "glass_blur", "classic_karaoke", "bold_impact",
    ]

    for p in presets_to_test:
        assert p in ALL_SUBTITLE_PRESETS
        cfg = normalize_subtitle_style({"stylePreset": p, "fontSize": 56})
        assert cfg["stylePreset"] == p
        assert cfg["fontSize"] == 56
        assert cfg["color"] is not None
        assert cfg["highlightColor"] is not None
        assert cfg["fontFamily"] is not None


@pytest.mark.asyncio
async def test_edge_tts_helper():
    from src.infrastructure.edge_tts_helper import EdgeTTSHelper

    helper = EdgeTTSHelper()
    voice = helper._resolve_voice("", "Bumi berhenti berputar dalam sekejap.")
    assert "id-ID" in voice

    voice_en = helper._resolve_voice("", "What if the earth stopped spinning right now?")
    assert "en-US" in voice_en


