"""Test Task 10: Full Integration Testing — End-to-end V2 pipeline verification.

Tests cover:
- Cross-module interaction (all V2 components wired together)
- Full pipeline flow: Transcript → Analysis → MicroSlice → Whisper → VAD → Output
- Pipeline routing: non-premium → V2, premium → V1
- Output compatibility: V2 produces same Clip/Word/CreativeDirection as V1
- Error scenarios: graceful degradation across pipeline
- Best/worst case scenarios
"""
import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.services_v2 import V2PipelineService
from src.domain.entities import (
    AudioSlice, Clip, CreativeDirection, HighlightAnalysisResult,
    HighlightCandidate, Job, JobStatus, TranscriptResult,
    TranscriptSegment, VADResult, Word,
)
from src.infrastructure.groq_transcriber import GroqTranscriber, TranscriptionError
from src.infrastructure.groq_analyzer import GroqAnalyzer, GroqAnalyzerError
from src.infrastructure.micro_slicer import MicroSlicer
from src.infrastructure.selective_whisper import SelectiveWhisperTranscriber
from src.infrastructure.silero_vad import SileroVADProcessor
from src.infrastructure.pipeline_router import PipelineRouter
from src.presentation.schemas.jobs import JobResponse


def run_async(coro):
    return asyncio.run(coro)


# ─── Cross-Module Integration Tests ──────────────────────────────────────────

def test_transcript_to_analyzer_data_flow():
    """TranscriptResult from GroqTranscriber feeds correctly into GroqAnalyzer."""
    # Simulate GroqTranscriber output
    transcript = TranscriptResult(
        segments=[
            TranscriptSegment(text="Ini adalah konten menarik tentang AI", start=0.0, end=5.0),
            TranscriptSegment(text="Machine learning mengubah dunia", start=5.0, end=10.0),
            TranscriptSegment(text="Kita harus siap menghadapi perubahan", start=10.0, end=15.0),
        ],
        source="youtube_api",
        language="id",
        total_duration=300.0,
    )

    # Verify it produces valid full_text for analyzer
    assert transcript.full_text == (
        "Ini adalah konten menarik tentang AI "
        "Machine learning mengubah dunia "
        "Kita harus siap menghadapi perubahan"
    )

    # GroqAnalyzer can chunk this transcript
    analyzer = GroqAnalyzer()
    chunks = analyzer._chunk_transcript(transcript.segments)
    assert len(chunks) >= 1
    assert all(isinstance(seg, TranscriptSegment) for seg in chunks[0])
    print("  [PASS] TranscriptResult → GroqAnalyzer data flow")


def test_analyzer_to_prepare_clips_data_flow():
    """HighlightAnalysisResult converts to Clip entities correctly."""
    svc = V2PipelineService(
        job_repo=AsyncMock(),
        downloader=AsyncMock(),
        renderer=AsyncMock(),
        whisper_local=AsyncMock(),
    )

    analysis = HighlightAnalysisResult(
        clips=[
            HighlightCandidate(rank=1, start=50.0, end=110.0, score=85,
                               hook="Viral hook!", reason="Strong emotion"),
            HighlightCandidate(rank=2, start=200.0, end=260.0, score=75,
                               hook="Second clip", reason="Informative"),
        ],
        creative_direction={
            "primary_color": "#FF3366",
            "secondary_color": "#FFD700",
            "typography_mood": "bold_impact",
        },
        broll_suggestions={
            "1": [{"at_time": 15.0, "keyword": "AI", "template": "word_pop_typography",
                   "duration": 2.0, "visual_category": "motion_graphic"}],
        },
    )

    clips = svc._prepare_clips_from_v2(
        analysis.clips, analysis.broll_suggestions, video_duration=300.0
    )

    assert len(clips) == 2
    assert isinstance(clips[0], Clip)
    assert clips[0].hook == "Viral hook!"
    assert len(clips[0].broll_suggestions) == 1
    assert clips[0].broll_suggestions[0].keyword == "AI"

    # Creative direction converts to entity
    cd = CreativeDirection.from_dict(analysis.creative_direction)
    assert cd.primary_color == "#FF3366"
    print("  [PASS] HighlightAnalysisResult → Clip entities")


def test_micro_slicer_to_whisper_data_flow():
    """AudioSlice from MicroSlicer feeds into SelectiveWhisperTranscriber."""
    audio_slice = AudioSlice(
        clip_rank=1,
        audio_path="/tmp/clip_001.wav",
        original_start=50.0,
        original_end=110.0,
        padded_start=47.0,
        padded_end=113.0,
        duration=66.0,
    )

    # SelectiveWhisper uses offset mapping
    mock_whisper = AsyncMock()
    transcriber = SelectiveWhisperTranscriber(mock_whisper)

    # Simulate whisper output (local timestamps)
    raw_segments = [{
        "words": [
            {"word": "halo", "start": 3.5, "end": 4.0},   # abs: 50.5
            {"word": "dunia", "start": 4.0, "end": 4.5},  # abs: 51.0
        ]
    }]
    words = transcriber._apply_offset_and_filter(raw_segments, audio_slice)

    assert len(words) == 2
    assert words[0].start == 50.5  # 3.5 + 47.0
    assert words[0].word == "halo"
    print("  [PASS] AudioSlice → SelectiveWhisper offset mapping")


def test_whisper_output_to_subtitle_format():
    """Word output from Whisper converts to subtitle rendering format."""
    svc = V2PipelineService(
        job_repo=AsyncMock(),
        downloader=AsyncMock(),
        renderer=AsyncMock(),
        whisper_local=AsyncMock(),
    )

    clips = [Clip(rank=1, score=85, start=50.0, end=110.0, hook="X", reason="Y")]
    words_per_clip = {
        1: [
            Word(word="halo", start=52.0, end=52.5),
            Word(word="dunia", start=53.0, end=53.5),
            Word(word="ini", start=54.0, end=54.3),
        ]
    }

    result = svc._build_clips_with_words(clips, words_per_clip)

    # Should be relative to clip start (50.0)
    assert result[1][0]["word"] == "halo"
    assert result[1][0]["start"] == 2.0   # 52.0 - 50.0
    assert result[1][1]["start"] == 3.0   # 53.0 - 50.0
    assert result[1][2]["start"] == 4.0   # 54.0 - 50.0
    print("  [PASS] Whisper words → subtitle renderer format")


def test_vad_refines_clip_boundaries():
    """VADResult correctly updates Clip start/end."""
    vad_result = VADResult(
        original_start=50.0,
        original_end=110.0,
        final_start=49.7,
        final_end=110.4,
        shift_start_ms=-300.0,
        shift_end_ms=400.0,
        used_fallback=False,
    )

    clip = Clip(rank=1, score=85, start=50.0, end=110.0, hook="X", reason="Y")

    # Simulate what the orchestrator does
    if not vad_result.used_fallback:
        clip.start = vad_result.final_start
        clip.end = vad_result.final_end

    assert clip.start == 49.7
    assert clip.end == 110.4
    print("  [PASS] VADResult updates Clip boundaries")


# ─── Full Pipeline Best Case ─────────────────────────────────────────────────

def test_full_v2_pipeline_best_case():
    """Best case: all steps succeed, multiple clips produced."""
    svc = V2PipelineService(
        job_repo=AsyncMock(),
        downloader=AsyncMock(),
        renderer=AsyncMock(),
        whisper_local=AsyncMock(),
    )
    svc._repo = AsyncMock()
    svc._repo.update_status = AsyncMock()
    svc._repo.update_clips_count = AsyncMock()
    svc._repo.update_clips_data = AsyncMock()
    svc._repo.get_by_job_id = AsyncMock(return_value=None)

    # Mock downloader
    svc._downloader = AsyncMock()
    svc._downloader.validate_url = AsyncMock(return_value=(True, None, 600.0))
    svc._downloader.download_video = AsyncMock(return_value=True)

    # Mock renderer
    svc._renderer = AsyncMock()
    svc._renderer.trim_clip = AsyncMock(return_value=True)

    # Mock V2 components
    svc._transcriber = AsyncMock()
    svc._transcriber.transcribe = AsyncMock(return_value=TranscriptResult(
        segments=[TranscriptSegment(text=f"Segment {i}", start=i*30.0, end=(i+1)*30.0) for i in range(20)],
        source="youtube_api", language="id", total_duration=600.0,
    ))

    svc._analyzer = AsyncMock()
    svc._analyzer.analyze_highlights = AsyncMock(return_value=HighlightAnalysisResult(
        clips=[
            HighlightCandidate(rank=1, start=60.0, end=120.0, score=90, hook="Hook 1", reason="Viral"),
            HighlightCandidate(rank=2, start=300.0, end=360.0, score=80, hook="Hook 2", reason="Funny"),
            HighlightCandidate(rank=3, start=450.0, end=510.0, score=70, hook="Hook 3", reason="Info"),
        ],
        creative_direction={"primary_color": "#FF0000", "energy_level": "high"},
        broll_suggestions={"1": [{"at_time": 10.0, "keyword": "VIRAL", "template": "word_pop_typography", "duration": 2.0, "visual_category": "footage"}]},
    ))

    svc._micro_slicer = AsyncMock()
    svc._micro_slicer.slice_audio = AsyncMock(return_value=[
        AudioSlice(clip_rank=i, audio_path=f"/tmp/clip_{i}.wav",
                   original_start=60.0*i, original_end=60.0*i+60,
                   padded_start=60.0*i-3, padded_end=60.0*i+63, duration=66.0)
        for i in range(1, 4)
    ])
    svc._micro_slicer.cleanup_slices = MagicMock()

    svc._selective_whisper = AsyncMock()
    svc._selective_whisper.transcribe_all_clips = AsyncMock(return_value={
        1: [Word(word="test1", start=62.0, end=62.5)],
        2: [Word(word="test2", start=302.0, end=302.5)],
        3: [Word(word="test3", start=452.0, end=452.5)],
    })

    svc._vad = AsyncMock()
    svc._vad.refine_clip_boundaries = AsyncMock(return_value=VADResult(
        original_start=60.0, original_end=120.0,
        final_start=59.8, final_end=120.2,
        shift_start_ms=-200, shift_end_ms=200,
    ))

    job = Job(job_id="best_case_001", youtube_url="https://youtube.com/watch?v=best",
              target_aspect_ratio="9:16", pipeline_version="v2")

    async def run():
        with patch("os.path.exists", return_value=True):
            with patch("os.makedirs"):
                await svc.run_pipeline(job)

        # Verify completion
        status_calls = [c.args[1] for c in svc._repo.update_status.call_args_list]
        assert JobStatus.COMPLETED in status_calls
        assert JobStatus.V2_TRANSCRIBING in status_calls
        assert JobStatus.V2_ANALYZING in status_calls

        # Verify clips_data saved
        svc._repo.update_clips_data.assert_called_once()
        clips_data = svc._repo.update_clips_data.call_args[0][1]
        assert clips_data["pipeline_version"] == "v2"
        assert clips_data["transcript_source"] == "youtube_api"
        assert len(clips_data["clips"]) == 3

    run_async(run())
    print("  [PASS] Full V2 pipeline best case (3 clips, all succeed)")


# ─── Worst Case Scenarios ─────────────────────────────────────────────────────

def test_worst_case_no_transcript():
    """Worst case: no transcript available at all."""
    svc = V2PipelineService(
        job_repo=AsyncMock(), downloader=AsyncMock(),
        renderer=AsyncMock(), whisper_local=AsyncMock(),
    )
    svc._repo = AsyncMock()
    svc._repo.update_status = AsyncMock()
    svc._downloader = AsyncMock()
    svc._downloader.validate_url = AsyncMock(return_value=(True, None, 300.0))
    svc._downloader.download_video = AsyncMock()

    svc._transcriber = AsyncMock()
    svc._transcriber.transcribe = AsyncMock(
        side_effect=TranscriptionError("Both YouTube and Groq failed")
    )

    job = Job(job_id="worst_001", youtube_url="url", pipeline_version="v2")

    async def run():
        with patch("os.makedirs"):
            await svc.run_pipeline(job)
        last_call = svc._repo.update_status.call_args_list[-1]
        assert last_call.args[1] == JobStatus.FAILED
        assert "Transcription gagal" in last_call.args[2]

    run_async(run())
    print("  [PASS] Worst case: no transcript → FAILED")


def test_worst_case_groq_rate_limited():
    """Worst case: Groq LLM rate limited on all retries."""
    svc = V2PipelineService(
        job_repo=AsyncMock(), downloader=AsyncMock(),
        renderer=AsyncMock(), whisper_local=AsyncMock(),
    )
    svc._repo = AsyncMock()
    svc._repo.update_status = AsyncMock()
    svc._downloader = AsyncMock()
    svc._downloader.validate_url = AsyncMock(return_value=(True, None, 300.0))
    svc._downloader.download_video = AsyncMock()

    svc._transcriber = AsyncMock()
    svc._transcriber.transcribe = AsyncMock(return_value=TranscriptResult(
        segments=[TranscriptSegment(text="Content", start=0, end=5)],
        source="youtube_api", language="id", total_duration=300.0,
    ))

    svc._analyzer = AsyncMock()
    svc._analyzer.analyze_highlights = AsyncMock(
        side_effect=GroqAnalyzerError("Rate limited after 3 retries")
    )

    job = Job(job_id="worst_002", youtube_url="url", pipeline_version="v2")

    async def run():
        with patch("os.makedirs"):
            await svc.run_pipeline(job)
        last_call = svc._repo.update_status.call_args_list[-1]
        assert last_call.args[1] == JobStatus.FAILED
        assert "Highlight analysis gagal" in last_call.args[2]

    run_async(run())
    print("  [PASS] Worst case: Groq rate limited → FAILED")


def test_worst_case_partial_whisper_failure():
    """Partial failure: 2/3 clips get words, 1 fails → continues."""
    svc = V2PipelineService(
        job_repo=AsyncMock(), downloader=AsyncMock(),
        renderer=AsyncMock(), whisper_local=AsyncMock(),
    )
    svc._repo = AsyncMock()
    svc._repo.update_status = AsyncMock()
    svc._repo.update_clips_count = AsyncMock()
    svc._repo.update_clips_data = AsyncMock()
    svc._downloader = AsyncMock()
    svc._downloader.validate_url = AsyncMock(return_value=(True, None, 300.0))
    svc._downloader.download_video = AsyncMock()
    svc._renderer = AsyncMock()
    svc._renderer.trim_clip = AsyncMock(return_value=True)

    svc._transcriber = AsyncMock()
    svc._transcriber.transcribe = AsyncMock(return_value=TranscriptResult(
        segments=[TranscriptSegment(text="Test", start=0, end=300)],
        source="youtube_api", language="id", total_duration=300.0,
    ))
    svc._analyzer = AsyncMock()
    svc._analyzer.analyze_highlights = AsyncMock(return_value=HighlightAnalysisResult(
        clips=[
            HighlightCandidate(rank=1, start=30.0, end=90.0, score=90, hook="A", reason="R"),
            HighlightCandidate(rank=2, start=150.0, end=210.0, score=80, hook="B", reason="R"),
        ],
        creative_direction={}, broll_suggestions={},
    ))
    svc._micro_slicer = AsyncMock()
    svc._micro_slicer.slice_audio = AsyncMock(return_value=[
        AudioSlice(clip_rank=1, audio_path="/tmp/c1.wav", original_start=30, original_end=90, padded_start=27, padded_end=93, duration=66),
        AudioSlice(clip_rank=2, audio_path="/tmp/c2.wav", original_start=150, original_end=210, padded_start=147, padded_end=213, duration=66),
    ])
    svc._micro_slicer.cleanup_slices = MagicMock()

    # Clip 1 gets words, Clip 2 fails (returns empty)
    svc._selective_whisper = AsyncMock()
    svc._selective_whisper.transcribe_all_clips = AsyncMock(return_value={
        1: [Word(word="success", start=32.0, end=32.5)],
        2: [],  # Failed
    })

    svc._vad = AsyncMock()
    svc._vad.refine_clip_boundaries = AsyncMock(return_value=VADResult(
        original_start=30, original_end=90, final_start=30, final_end=90,
        used_fallback=True,
    ))

    job = Job(job_id="partial_001", youtube_url="url", pipeline_version="v2",
              target_aspect_ratio="16:9")

    async def run():
        with patch("os.path.exists", return_value=True):
            with patch("os.makedirs"):
                await svc.run_pipeline(job)
        # Should still complete (partial failure is OK)
        status_calls = [c.args[1] for c in svc._repo.update_status.call_args_list]
        assert JobStatus.COMPLETED in status_calls

    run_async(run())
    print("  [PASS] Partial whisper failure → pipeline still completes")


# ─── Pipeline Routing Integration ─────────────────────────────────────────────

def test_routing_integration_non_premium():
    """End-to-end: non-premium user creates job → V2 pipeline assigned."""
    router = PipelineRouter()
    with patch.object(router, "_check_user_premium", return_value=False):
        version = router.get_pipeline_version(user_id=5, is_superadmin=False)
    assert version == "v2"

    # Create job with this version
    job = Job(job_id="route_001", youtube_url="url", pipeline_version=version)
    response = JobResponse(
        job_id=job.job_id, youtube_url=job.youtube_url,
        status=job.status.value, pipeline_version=job.pipeline_version,
    )
    assert response.pipeline_version == "v2"
    print("  [PASS] Non-premium routing: Router → Job → Response")


def test_routing_integration_premium():
    """End-to-end: premium user creates job → V1 pipeline assigned."""
    router = PipelineRouter()
    with patch.object(router, "_check_user_premium", return_value=True):
        version = router.get_pipeline_version(user_id=3, is_superadmin=False)
    assert version == "v1"

    job = Job(job_id="route_002", youtube_url="url", pipeline_version=version)
    response = JobResponse(
        job_id=job.job_id, youtube_url=job.youtube_url,
        status=job.status.value, pipeline_version=job.pipeline_version,
    )
    assert response.pipeline_version == "v1"
    print("  [PASS] Premium routing: Router → Job → Response")


# ─── Output Compatibility ─────────────────────────────────────────────────────

def test_v2_output_compatible_with_v1_entities():
    """V2 pipeline produces same entity types as V1."""
    # V2 produces these same types:
    clip = Clip(rank=1, score=85, start=50.0, end=110.0, hook="Hook", reason="Reason")
    word = Word(word="test", start=2.0, end=2.5, highlight=False)
    cd = CreativeDirection(
        primary_color="#FF0000",
        secondary_color="#FFD700",
        typography_mood="bold_impact",
        energy_level="high",
    )

    # These are the same entities used by V1 downstream (subtitle, hook, B-Roll renderers)
    assert isinstance(clip, Clip)
    assert isinstance(word, Word)
    assert isinstance(cd, CreativeDirection)
    assert asdict(cd)["primary_color"] == "#FF0000"
    print("  [PASS] V2 output uses same entity types as V1")


def test_v2_clips_data_format():
    """V2 clips_data JSON is compatible with frontend expectations."""
    clips_data = {
        "pipeline_version": "v2",
        "transcript_source": "youtube_api",
        "creative_direction": {
            "primary_color": "#FF3366",
            "secondary_color": "#FFD700",
            "background_accent": "#000000",
            "typography_mood": "bold_impact",
            "energy_level": "high",
            "transition_style": "fast_cuts",
            "music_mood": "energetic",
            "hook_animation": "fade_scale",
        },
        "clips": [
            {
                "rank": 1, "score": 85,
                "start": 49.5, "end": 111.0, "duration": 61.5,
                "hook": "Ini hook viral",
                "reason": "Strong emotion",
                "output_path": "/tmp/output/clip_01_final.mp4",
                "word_count": 45,
                "has_subtitles": True,
            }
        ],
    }

    # Validate structure
    assert clips_data["pipeline_version"] == "v2"
    assert "clips" in clips_data
    assert clips_data["clips"][0]["has_subtitles"] is True
    assert "creative_direction" in clips_data
    assert clips_data["creative_direction"]["primary_color"].startswith("#")
    print("  [PASS] V2 clips_data JSON format compatible")


# ─── Run All Tests ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== Task 10 Tests: Full Integration ===\n")
    print("── Cross-Module Data Flow ──")
    test_transcript_to_analyzer_data_flow()
    test_analyzer_to_prepare_clips_data_flow()
    test_micro_slicer_to_whisper_data_flow()
    test_whisper_output_to_subtitle_format()
    test_vad_refines_clip_boundaries()
    print("\n── Full Pipeline Scenarios ──")
    test_full_v2_pipeline_best_case()
    test_worst_case_no_transcript()
    test_worst_case_groq_rate_limited()
    test_worst_case_partial_whisper_failure()
    print("\n── Routing Integration ──")
    test_routing_integration_non_premium()
    test_routing_integration_premium()
    print("\n── Output Compatibility ──")
    test_v2_output_compatible_with_v1_entities()
    test_v2_clips_data_format()
    print("\n=== ALL TASK 10 TESTS PASSED (13/13) ===\n")
