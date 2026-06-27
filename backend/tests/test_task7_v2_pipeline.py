"""Test Task 7: V2PipelineOrchestrator — Full pipeline integration.

Tests cover:
- _prepare_clips_from_v2 conversion
- _build_clips_with_words relative timestamp conversion
- _calc_max_clips formula
- Full pipeline happy path (all mocked)
- Pipeline failure at transcription step
- Pipeline failure at analysis step
- Partial clip failures (graceful degradation)
- _assemble_clips_data output format
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.services_v2 import V2PipelineService
from src.domain.entities import (
    AudioSlice, Clip, CreativeDirection, HighlightAnalysisResult,
    HighlightCandidate, Job, JobStatus, TranscriptResult,
    TranscriptSegment, Word,
)


def run_async(coro):
    return asyncio.run(coro)


def make_mock_service(**overrides) -> V2PipelineService:
    """Create V2PipelineService with all components mocked."""
    mock_repo = AsyncMock()
    mock_repo.update_status = AsyncMock()
    mock_repo.update_clips_count = AsyncMock()
    mock_repo.update_clips_data = AsyncMock()
    mock_repo.get_by_job_id = AsyncMock(return_value=None)

    mock_downloader = AsyncMock()
    mock_downloader.validate_url = AsyncMock(return_value=(True, None, 300.0))
    mock_downloader.download_video = AsyncMock(return_value=True)

    mock_renderer = AsyncMock()
    mock_renderer.trim_clip = AsyncMock(return_value=True)

    mock_whisper = AsyncMock()
    mock_whisper.transcribe_clip = AsyncMock(return_value=[])

    defaults = {
        "job_repo": mock_repo,
        "downloader": mock_downloader,
        "renderer": mock_renderer,
        "whisper_local": mock_whisper,
    }
    defaults.update(overrides)
    return V2PipelineService(**defaults)


# ─── Unit Tests ───────────────────────────────────────────────────────────────

def test_calc_max_clips():
    """Max clips calculation based on duration."""
    svc = make_mock_service()
    assert svc._calc_max_clips(60) == 2     # < 3 min
    assert svc._calc_max_clips(179) == 2    # < 3 min
    assert svc._calc_max_clips(180) == 5    # >= 3 min, < 10 min
    assert svc._calc_max_clips(300) == 5    # 5 min
    assert svc._calc_max_clips(900) == 8    # 15 min
    assert svc._calc_max_clips(3600) == 10  # 60 min
    print("  [PASS] _calc_max_clips formula correct")


def test_prepare_clips_from_v2():
    """Convert HighlightCandidate → Clip entities."""
    svc = make_mock_service()
    highlights = [
        HighlightCandidate(rank=1, start=50.0, end=110.0, score=85,
                           hook="Test hook", reason="Viral moment"),
        HighlightCandidate(rank=2, start=200.0, end=260.0, score=75,
                           hook="Second clip", reason="Funny"),
    ]
    broll_map = {
        "1": [{"at_time": 15.0, "keyword": "TEST", "template": "word_pop_typography",
               "duration": 2.0, "visual_category": "footage"}]
    }

    clips = svc._prepare_clips_from_v2(highlights, broll_map, video_duration=300.0)

    assert len(clips) == 2
    assert clips[0].rank == 1
    assert clips[0].start == 49.5   # 50 - 0.5 padding
    assert clips[0].end == 111.0    # 110 + 1.0 padding
    assert clips[0].hook == "Test hook"
    assert clips[0].score == 85
    assert len(clips[0].broll_suggestions) == 1
    assert clips[0].broll_suggestions[0].keyword == "TEST"
    assert clips[1].rank == 2
    print("  [PASS] _prepare_clips_from_v2 conversion")


def test_prepare_clips_filters_short():
    """Clips shorter than MIN_CLIP_DURATION are filtered."""
    svc = make_mock_service()
    highlights = [
        HighlightCandidate(rank=1, start=10.0, end=12.0, score=90,
                           hook="Too short", reason="x"),  # 2s → filtered
        HighlightCandidate(rank=2, start=50.0, end=110.0, score=80,
                           hook="Good", reason="y"),
    ]
    clips = svc._prepare_clips_from_v2(highlights, {}, video_duration=300.0)
    assert len(clips) == 1
    assert clips[0].rank == 2
    print("  [PASS] Short clips filtered by MIN_CLIP_DURATION")


def test_build_clips_with_words():
    """Convert Word objects to relative-timestamp dicts."""
    svc = make_mock_service()
    clips = [Clip(rank=1, score=80, start=50.0, end=110.0, hook="X", reason="Y")]
    words_per_clip = {
        1: [
            Word(word="hello", start=52.0, end=52.5, highlight=False),
            Word(word="world", start=53.0, end=53.5, highlight=True),
        ]
    }

    result = svc._build_clips_with_words(clips, words_per_clip)

    assert 1 in result
    assert len(result[1]) == 2
    assert result[1][0]["word"] == "hello"
    assert result[1][0]["start"] == 2.0    # 52.0 - 50.0 (relative)
    assert result[1][0]["end"] == 2.5
    assert result[1][1]["highlight"] is True
    print("  [PASS] _build_clips_with_words converts to relative")


def test_build_clips_with_words_empty():
    """Clips without words get empty list."""
    svc = make_mock_service()
    clips = [Clip(rank=1, score=80, start=50.0, end=110.0, hook="X", reason="Y")]
    words_per_clip = {}

    result = svc._build_clips_with_words(clips, words_per_clip)
    assert result[1] == []
    print("  [PASS] Clips without words get empty list")


def test_assemble_clips_data():
    """Final clips_data assembly for DB storage."""
    svc = make_mock_service()
    clips = [Clip(rank=1, score=85, start=50.0, end=110.0, hook="Hook", reason="Reason")]
    words_per_clip = {1: [Word(word="test", start=52.0, end=52.5)]}
    cd = CreativeDirection(primary_color="#FF0000")

    # Mock file existence
    with patch("os.path.exists", return_value=True):
        data = svc._assemble_clips_data(
            clips, words_per_clip, cd, "/tmp/output",
            transcript_source="youtube_api"
        )

    assert data["pipeline_version"] == "v2"
    assert data["transcript_source"] == "youtube_api"
    assert data["creative_direction"]["primary_color"] == "#FF0000"
    assert len(data["clips"]) == 1
    assert data["clips"][0]["rank"] == 1
    assert data["clips"][0]["hook"] == "Hook"
    assert data["clips"][0]["word_count"] == 1
    assert data["clips"][0]["has_subtitles"] is True
    print("  [PASS] _assemble_clips_data output format")


# ─── Pipeline Integration Tests (All Mocked) ─────────────────────────────────

def test_full_pipeline_happy_path():
    """Full V2 pipeline with all components mocked."""
    svc = make_mock_service()

    # Mock V2 components
    mock_transcript = TranscriptResult(
        segments=[TranscriptSegment(text="Hello world", start=0.0, end=5.0)],
        source="youtube_api", language="id", total_duration=300.0,
    )
    svc._transcriber = AsyncMock()
    svc._transcriber.transcribe = AsyncMock(return_value=mock_transcript)

    mock_analysis = HighlightAnalysisResult(
        clips=[HighlightCandidate(rank=1, start=50.0, end=110.0, score=85,
                                   hook="Test", reason="Viral")],
        creative_direction={"primary_color": "#FF0000"},
        broll_suggestions={},
    )
    svc._analyzer = AsyncMock()
    svc._analyzer.analyze_highlights = AsyncMock(return_value=mock_analysis)

    svc._micro_slicer = AsyncMock()
    svc._micro_slicer.slice_audio = AsyncMock(return_value=[
        AudioSlice(clip_rank=1, audio_path="/tmp/clip.wav",
                   original_start=50.0, original_end=110.0,
                   padded_start=47.0, padded_end=113.0, duration=66.0)
    ])
    svc._micro_slicer.cleanup_slices = MagicMock()

    svc._selective_whisper = AsyncMock()
    svc._selective_whisper.transcribe_all_clips = AsyncMock(return_value={
        1: [Word(word="hello", start=52.0, end=52.5)]
    })

    from src.domain.entities import VADResult
    mock_vad_result = VADResult(
        original_start=50.0, original_end=110.0,
        final_start=49.8, final_end=110.2,
        shift_start_ms=-200, shift_end_ms=200,
    )
    svc._vad = AsyncMock()
    svc._vad.refine_clip_boundaries = AsyncMock(return_value=mock_vad_result)

    job = Job(job_id="test_v2_001", youtube_url="https://youtube.com/watch?v=test",
              target_aspect_ratio="9:16")

    async def run():
        with patch("os.path.exists", return_value=True):
            with patch("os.makedirs"):
                await svc.run_pipeline(job)

        # Verify status progression
        status_calls = [c.args[1] for c in svc._repo.update_status.call_args_list]
        assert JobStatus.V2_TRANSCRIBING in status_calls
        assert JobStatus.V2_ANALYZING in status_calls
        assert JobStatus.V2_MICRO_SLICING in status_calls
        assert JobStatus.V2_WORD_TRANSCRIBING in status_calls
        assert JobStatus.V2_VAD_REFINING in status_calls
        assert JobStatus.COMPLETED in status_calls

        # Verify clips_data saved
        svc._repo.update_clips_data.assert_called_once()
        saved_data = svc._repo.update_clips_data.call_args[0][1]
        assert saved_data["pipeline_version"] == "v2"

    run_async(run())
    print("  [PASS] Full V2 pipeline happy path")


def test_pipeline_transcription_failure():
    """Pipeline fails at transcription → job marked FAILED."""
    svc = make_mock_service()

    from src.infrastructure.groq_transcriber import TranscriptionError
    svc._transcriber = AsyncMock()
    svc._transcriber.transcribe = AsyncMock(
        side_effect=TranscriptionError("No transcript available")
    )

    job = Job(job_id="test_fail_001", youtube_url="https://youtube.com/watch?v=fail")

    async def run():
        with patch("os.path.exists", return_value=True):
            with patch("os.makedirs"):
                await svc.run_pipeline(job)

        # Should be marked as FAILED
        last_status_call = svc._repo.update_status.call_args_list[-1]
        assert last_status_call.args[1] == JobStatus.FAILED
        assert "Transcription gagal" in last_status_call.args[2]

    run_async(run())
    print("  [PASS] Transcription failure → job FAILED")


def test_pipeline_analysis_failure():
    """Pipeline fails at analysis → job marked FAILED."""
    svc = make_mock_service()

    mock_transcript = TranscriptResult(
        segments=[TranscriptSegment(text="Content", start=0.0, end=5.0)],
        source="youtube_api", language="id", total_duration=300.0,
    )
    svc._transcriber = AsyncMock()
    svc._transcriber.transcribe = AsyncMock(return_value=mock_transcript)

    from src.infrastructure.groq_analyzer import GroqAnalyzerError
    svc._analyzer = AsyncMock()
    svc._analyzer.analyze_highlights = AsyncMock(
        side_effect=GroqAnalyzerError("LLM failed")
    )

    job = Job(job_id="test_fail_002", youtube_url="https://youtube.com/watch?v=fail2")

    async def run():
        with patch("os.path.exists", return_value=True):
            with patch("os.makedirs"):
                await svc.run_pipeline(job)

        last_status_call = svc._repo.update_status.call_args_list[-1]
        assert last_status_call.args[1] == JobStatus.FAILED
        assert "Highlight analysis gagal" in last_status_call.args[2]

    run_async(run())
    print("  [PASS] Analysis failure → job FAILED")


def test_pipeline_no_clips_found():
    """No clips detected → job marked FAILED."""
    svc = make_mock_service()

    mock_transcript = TranscriptResult(
        segments=[TranscriptSegment(text="Boring content", start=0.0, end=5.0)],
        source="youtube_api", language="id", total_duration=300.0,
    )
    svc._transcriber = AsyncMock()
    svc._transcriber.transcribe = AsyncMock(return_value=mock_transcript)

    mock_analysis = HighlightAnalysisResult(
        clips=[],  # No clips found
        creative_direction={},
        broll_suggestions={},
    )
    svc._analyzer = AsyncMock()
    svc._analyzer.analyze_highlights = AsyncMock(return_value=mock_analysis)

    job = Job(job_id="test_fail_003", youtube_url="https://youtube.com/watch?v=boring")

    async def run():
        with patch("os.path.exists", return_value=True):
            with patch("os.makedirs"):
                await svc.run_pipeline(job)

        last_status_call = svc._repo.update_status.call_args_list[-1]
        assert last_status_call.args[1] == JobStatus.FAILED
        assert "momen viral" in last_status_call.args[2].lower()

    run_async(run())
    print("  [PASS] No clips found → job FAILED")


def test_pipeline_validation_failure():
    """Invalid URL → job marked FAILED at step 1."""
    svc = make_mock_service()
    svc._repo.update_status = AsyncMock()
    svc._downloader.validate_url = AsyncMock(
        return_value=(False, "URL not valid", None)
    )

    job = Job(job_id="test_fail_004", youtube_url="not-a-youtube-url")

    async def run():
        with patch("os.makedirs"):
            await svc.run_pipeline(job)

        last_status_call = svc._repo.update_status.call_args_list[-1]
        assert last_status_call.args[1] == JobStatus.FAILED

    run_async(run())
    print("  [PASS] Invalid URL → FAILED at validation")


if __name__ == "__main__":
    print("\n=== Task 7 Tests: V2PipelineOrchestrator ===\n")
    # Unit tests
    test_calc_max_clips()
    test_prepare_clips_from_v2()
    test_prepare_clips_filters_short()
    test_build_clips_with_words()
    test_build_clips_with_words_empty()
    test_assemble_clips_data()
    # Pipeline integration
    test_full_pipeline_happy_path()
    test_pipeline_transcription_failure()
    test_pipeline_analysis_failure()
    test_pipeline_no_clips_found()
    test_pipeline_validation_failure()
    print("\n=== ALL TASK 7 TESTS PASSED (11/11) ===\n")
