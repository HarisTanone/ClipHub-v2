"""Test Task 1: Configuration, Dependencies, Entities, Interfaces."""
from src.config import settings
from src.domain.entities import (
    TranscriptSegment, TranscriptResult, AudioSlice,
    HighlightCandidate, HighlightAnalysisResult, VADResult,
    JobStatus, Job, Clip, Word, CreativeDirection, BRollSuggestion
)
from src.domain.interfaces import (
    IGroqTranscriber, IGroqAnalyzer, IMicroSlicer, ISileroVAD,
    IJobRepository, IDownloader, IGeminiAnalyzer, IWhisperLocal
)
from groq import Groq


def test_config_groq_settings():
    assert settings.GROQ_WHISPER_MODEL == "whisper-large-v3-turbo"
    assert settings.GROQ_LLM_MODEL == "llama-3.1-8b-instant"
    assert settings.GROQ_LLM_FALLBACK_MODEL == "llama-3.3-70b-versatile"
    assert settings.GROQ_MAX_RETRIES == 3
    assert settings.GROQ_TIMEOUT == 60
    print("  [PASS] Groq settings loaded correctly")


def test_config_v2_pipeline_settings():
    assert settings.V2_PIPELINE_ENABLED is True
    assert settings.V2_CHUNK_MAX_SECONDS == 600
    assert settings.V2_CHUNK_MAX_CHARS == 4000
    assert settings.V2_AUDIO_PADDING_SECONDS == 3.0
    assert settings.V2_VAD_SEARCH_RADIUS == 2.0
    assert settings.V2_VAD_MIN_SILENCE_MS == 300
    assert settings.V2_MAX_AUDIO_CHUNK_MB == 25
    print("  [PASS] V2 pipeline settings loaded correctly")


def test_transcript_segment_entity():
    seg = TranscriptSegment(text="Hello world", start=0.0, end=2.5)
    assert seg.text == "Hello world"
    assert seg.start == 0.0
    assert seg.end == 2.5
    print("  [PASS] TranscriptSegment entity works")


def test_transcript_result_entity():
    seg1 = TranscriptSegment(text="Hello", start=0.0, end=1.0)
    seg2 = TranscriptSegment(text="world", start=1.0, end=2.0)
    result = TranscriptResult(
        segments=[seg1, seg2],
        source="youtube_api",
        language="id",
        total_duration=120.0,
    )
    assert result.full_text == "Hello world"
    assert result.source == "youtube_api"
    assert len(result.segments) == 2
    print("  [PASS] TranscriptResult entity works (auto-generates full_text)")


def test_audio_slice_entity():
    audio = AudioSlice(
        clip_rank=1,
        audio_path="/tmp/clip_1.wav",
        original_start=10.0,
        original_end=50.0,
        padded_start=7.0,
        padded_end=53.0,
        duration=46.0,
    )
    assert audio.clip_rank == 1
    assert audio.duration == 46.0
    assert audio.padded_start == 7.0
    print("  [PASS] AudioSlice entity works")


def test_highlight_candidate_entity():
    h = HighlightCandidate(
        rank=1, start=10.0, end=55.0, score=85,
        hook="Test hook", reason="Viral moment"
    )
    assert h.content_type == "storytelling"  # default
    assert h.speaker_energy == "medium"      # default
    print("  [PASS] HighlightCandidate entity works")


def test_highlight_analysis_result_entity():
    h = HighlightCandidate(rank=1, start=10.0, end=55.0, score=85, hook="X", reason="Y")
    analysis = HighlightAnalysisResult(
        clips=[h],
        creative_direction={"primary_color": "#FF0000"},
        broll_suggestions={"1": [{"at_time": 5.0, "keyword": "TEST"}]},
    )
    assert len(analysis.clips) == 1
    assert analysis.creative_direction["primary_color"] == "#FF0000"
    print("  [PASS] HighlightAnalysisResult entity works")


def test_vad_result_entity():
    vad = VADResult(
        original_start=10.0, original_end=55.0,
        final_start=9.8, final_end=55.3,
        shift_start_ms=-200.0, shift_end_ms=300.0,
    )
    assert vad.used_fallback is False
    assert vad.shift_start_ms == -200.0
    print("  [PASS] VADResult entity works")


def test_v2_job_statuses():
    assert JobStatus.V2_TRANSCRIBING.value == "v2_transcribing"
    assert JobStatus.V2_ANALYZING.value == "v2_analyzing"
    assert JobStatus.V2_MICRO_SLICING.value == "v2_micro_slicing"
    assert JobStatus.V2_WORD_TRANSCRIBING.value == "v2_word_transcribing"
    assert JobStatus.V2_VAD_REFINING.value == "v2_vad_refining"
    print("  [PASS] V2 JobStatus enums registered")


def test_v2_interfaces_exist():
    """Verify all V2 interfaces are abstract and importable."""
    import inspect
    assert inspect.isabstract(IGroqTranscriber)
    assert inspect.isabstract(IGroqAnalyzer)
    assert inspect.isabstract(IMicroSlicer)
    assert inspect.isabstract(ISileroVAD)
    print("  [PASS] V2 Interfaces are valid ABCs")


def test_groq_sdk_importable():
    client = Groq(api_key="test_key")
    assert client is not None
    print("  [PASS] Groq SDK importable and instantiable")


def test_existing_entities_not_broken():
    """Verify existing V1 entities still work."""
    job = Job(job_id="test", youtube_url="https://youtube.com/watch?v=x")
    assert job.status == JobStatus.VALIDATING
    clip = Clip(rank=1, score=80, start=0, end=60, hook="test", reason="test")
    assert clip.rank == 1
    word = Word(word="hello", start=0.0, end=0.5)
    assert word.highlight is False
    print("  [PASS] Existing V1 entities not broken")


if __name__ == "__main__":
    print("\n=== Task 1 Tests: Config & Dependencies ===\n")
    test_config_groq_settings()
    test_config_v2_pipeline_settings()
    test_transcript_segment_entity()
    test_transcript_result_entity()
    test_audio_slice_entity()
    test_highlight_candidate_entity()
    test_highlight_analysis_result_entity()
    test_vad_result_entity()
    test_v2_job_statuses()
    test_v2_interfaces_exist()
    test_groq_sdk_importable()
    test_existing_entities_not_broken()
    print("\n=== ALL TASK 1 TESTS PASSED ===\n")
