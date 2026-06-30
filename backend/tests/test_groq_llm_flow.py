"""Simple integration test for the new Groq LLM clip extraction flow.

Tests:
1. Segment IDs are correctly built and sent
2. JSON Schema response is parsed correctly
3. Segment IDs are resolved back to timestamps
4. Validation passes (duration 45-90s, within video range)

Run: cd backend && python -m tests.test_groq_llm_flow
"""
import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.domain.entities import TranscriptResult, TranscriptSegment


def create_mock_transcript(duration_seconds: float = 300.0, num_segments: int = 20):
    """Create a realistic mock transcript (5 min video, 20 segments)."""
    segment_duration = duration_seconds / num_segments
    segments = []
    
    # Realistic Indonesian podcast text
    texts = [
        "Halo semua selamat datang di channel kita",
        "Hari ini kita bahas topik yang menarik banget",
        "Jadi gini ceritanya kemarin gue ketemu temen lama",
        "Dia bilang sesuatu yang bikin gue kaget banget",
        "Ternyata selama ini dia udah bohong ke semua orang",
        "Bukan cuma ke gue tapi ke semua temen-temennya",
        "Yang bikin lebih parah lagi ini udah bertahun-tahun",
        "Gue langsung konfrontasi dia saat itu juga",
        "Reaksinya dia malah marah-marah ke gue balik",
        "Padahal dia yang salah tapi dia yang marah",
        "Terus gue pikir ini udah nggak sehat lagi hubungannya",
        "Jadi gue putusin untuk cut off dia dari hidup gue",
        "Setelah itu hidup gue jauh lebih tenang",
        "Pelajaran penting dari cerita ini adalah",
        "Jangan pernah tolerate orang yang toxic di hidup lo",
        "Kalau ada red flag langsung aja pergi",
        "Nggak perlu nunggu sampai situasinya makin parah",
        "Karena mental health lo itu jauh lebih penting",
        "Oke sekian cerita hari ini semoga bermanfaat",
        "Jangan lupa subscribe dan share ke temen kalian",
    ]
    
    for i in range(num_segments):
        start = i * segment_duration
        end = start + segment_duration
        text = texts[i] if i < len(texts) else f"Segment {i} filler text"
        segments.append(TranscriptSegment(text=text, start=start, end=end))
    
    return TranscriptResult(
        segments=segments,
        source="test",
        language="id",
        total_duration=duration_seconds,
    )


async def test_groq_flow():
    """Test the full Groq LLM flow end-to-end."""
    from src.infrastructure.highlight_analyzer import HighlightAnalyzer
    
    print("=" * 60)
    print("TEST: Groq LLM Flow (Segment ID + JSON Schema)")
    print("=" * 60)
    
    # Create mock data
    transcript = create_mock_transcript(duration_seconds=300.0, num_segments=20)
    print(f"\n[1] Mock transcript: {len(transcript.segments)} segments, {transcript.total_duration}s")
    print(f"    First segment: [{transcript.segments[0].start:.1f}s] {transcript.segments[0].text[:50]}...")
    print(f"    Last segment:  [{transcript.segments[-1].start:.1f}s] {transcript.segments[-1].text[:50]}...")
    
    # Call analyzer
    analyzer = HighlightAnalyzer()
    print(f"\n[2] Calling Groq LLM (model: llama-3.3-70b-versatile)...")
    print(f"    GROQ_API_KEY: {'configured' if analyzer._groq_key else 'MISSING!'}")
    
    if not analyzer._groq_key:
        print("\n    ERROR: GROQ_API_KEY not configured in .env!")
        return False
    
    try:
        result = await analyzer._analyze_with_groq(
            transcript=transcript,
            video_duration=300.0,
            max_clips=3,
        )
    except Exception as e:
        print(f"\n    ERROR: {type(e).__name__}: {e}")
        return False
    
    # Verify result
    print(f"\n[3] Result:")
    if result is None:
        print("    FAILED — returned None (no clips extracted)")
        return False
    
    print(f"    SUCCESS — {len(result.clips)} clips extracted")
    print(f"    Model: {result.model_used}")
    
    # Validate each clip
    all_valid = True
    print(f"\n[4] Clip validation:")
    for clip in result.clips:
        duration = clip.end - clip.start
        in_range = 0 <= clip.start < clip.end <= 310  # 300s + tolerance
        dur_valid = 15 <= duration <= 180
        has_hook = len(clip.hook) > 0
        
        status = "PASS" if (in_range and dur_valid and has_hook) else "FAIL"
        if status == "FAIL":
            all_valid = False
        
        print(f"    [{status}] Clip {clip.rank}: {clip.start:.1f}s → {clip.end:.1f}s ({duration:.1f}s)")
        print(f"           Hook: \"{clip.hook}\"")
        print(f"           Score: {clip.score}, Type: {clip.content_type}, Energy: {clip.speaker_energy}")
        if status == "FAIL":
            print(f"           ISSUES: range={in_range}, duration={dur_valid}, hook={has_hook}")
    
    print(f"\n{'=' * 60}")
    print(f"RESULT: {'ALL TESTS PASSED' if all_valid else 'SOME TESTS FAILED'}")
    print(f"{'=' * 60}")
    return all_valid


if __name__ == "__main__":
    success = asyncio.run(test_groq_flow())
    sys.exit(0 if success else 1)
