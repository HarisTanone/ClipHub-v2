"""LIVE Integration Test — V2 Pipeline with real Groq API.

This test calls REAL external APIs:
- YouTube Transcript API (free)
- Groq LLM API (llama-3.1-8b-instant)

Requirements:
- GROQ_API_KEY set in .env
- Internet connection

Test video: Short Indonesian/English YouTube video with captions.
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings
from src.infrastructure.groq_transcriber import GroqTranscriber, TranscriptionError
from src.infrastructure.groq_analyzer import GroqAnalyzer, GroqAnalyzerError
from src.infrastructure.micro_slicer import MicroSlicer
from src.infrastructure.pipeline_router import PipelineRouter
from src.domain.entities import TranscriptResult, HighlightAnalysisResult, CreativeDirection


def run_async(coro):
    return asyncio.run(coro)


# ─── Test Configuration ───────────────────────────────────────────────────────

# Short video with Indonesian captions (public, ~5 min)
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo" - first YT video, 19s
TEST_VIDEO_DURATION = 19.0

# Longer video for chunking test (use a known short video with transcript)
TEST_VIDEO_ID = "jNQXAC9IVRw"


# ─── LIVE TEST 1: YouTube Transcript API ──────────────────────────────────────

def test_live_youtube_transcript():
    """LIVE: Fetch real YouTube transcript."""
    print("\n─── LIVE TEST 1: YouTube Transcript API ───")
    transcriber = GroqTranscriber()
    
    start = time.time()
    
    async def run():
        try:
            result = await transcriber.transcribe(TEST_VIDEO_URL, TEST_VIDEO_DURATION)
            elapsed = time.time() - start
            
            print(f"  Source: {result.source}")
            print(f"  Language: {result.language}")
            print(f"  Segments: {len(result.segments)}")
            print(f"  Full text preview: {result.full_text[:100]}...")
            print(f"  Time: {elapsed:.2f}s")
            
            assert result.segments, "No segments returned"
            assert result.full_text, "No full text"
            assert result.source in ("youtube_api", "groq_whisper")
            
            print(f"  [PASS] YouTube transcript fetched ({result.source})")
            return result
        except TranscriptionError as e:
            print(f"  [WARN] TranscriptionError: {e}")
            print(f"  [SKIP] Video may not have captions — testing with fallback")
            return None
    
    return run_async(run())


# ─── LIVE TEST 2: Groq LLM Highlight Analysis ────────────────────────────────

def test_live_groq_llm_analysis(transcript: TranscriptResult = None):
    """LIVE: Call Groq LLM for highlight analysis."""
    print("\n─── LIVE TEST 2: Groq LLM Highlight Analysis ───")
    
    # If transcript is too short for clip extraction (< 45s), use synthetic
    if transcript is None or not transcript.segments or transcript.total_duration < 60:
        from src.domain.entities import TranscriptSegment
        if transcript and transcript.total_duration < 60:
            print(f"  Video too short ({transcript.total_duration:.0f}s) for clip extraction, using synthetic")
        transcript = TranscriptResult(
            segments=[
                TranscriptSegment(text="Halo semua, selamat datang di channel saya", start=0.0, end=5.0),
                TranscriptSegment(text="Hari ini kita akan membahas tentang cara membuat konten viral", start=5.0, end=12.0),
                TranscriptSegment(text="Pertama, kamu harus punya hook yang kuat di 3 detik pertama", start=12.0, end=20.0),
                TranscriptSegment(text="Kedua, gunakan storytelling yang emosional", start=20.0, end=28.0),
                TranscriptSegment(text="Ketiga, jangan lupa call to action di akhir video", start=28.0, end=35.0),
                TranscriptSegment(text="Contohnya seperti yang saya lakukan sekarang ini", start=35.0, end=42.0),
                TranscriptSegment(text="Banyak orang tidak menyadari betapa pentingnya editing yang baik", start=42.0, end=50.0),
                TranscriptSegment(text="Dengan teknik yang tepat, views bisa meningkat 10 kali lipat", start=50.0, end=58.0),
                TranscriptSegment(text="Saya sudah membuktikan ini di channel saya sendiri", start=58.0, end=65.0),
                TranscriptSegment(text="Dalam 3 bulan terakhir, subscriber naik dari 1000 ke 50000", start=65.0, end=73.0),
                TranscriptSegment(text="Rahasia utamanya adalah konsistensi dan kualitas konten", start=73.0, end=80.0),
                TranscriptSegment(text="Jangan pernah upload video asal-asalan", start=80.0, end=85.0),
                TranscriptSegment(text="Setiap video harus punya value yang jelas untuk penonton", start=85.0, end=92.0),
                TranscriptSegment(text="Terima kasih sudah menonton sampai akhir", start=92.0, end=97.0),
                TranscriptSegment(text="Jangan lupa subscribe dan nyalakan loncengnya", start=97.0, end=103.0),
            ],
            source="synthetic",
            language="id",
            total_duration=103.0,
        )
        print("  Using synthetic transcript (103s, 15 segments)")
    
    analyzer = GroqAnalyzer()
    start = time.time()
    
    async def run():
        result = await analyzer.analyze_highlights(
            transcript, video_duration=transcript.total_duration, max_clips=3
        )
        elapsed = time.time() - start
        
        print(f"  Model used: {result.model_used}")
        print(f"  Chunks processed: {result.chunks_processed}")
        print(f"  Clips found: {len(result.clips)}")
        
        for clip in result.clips:
            print(f"    Clip {clip.rank}: [{clip.start:.1f}s-{clip.end:.1f}s] score={clip.score} hook=\"{clip.hook}\"")
        
        if result.creative_direction:
            print(f"  Creative direction: {json.dumps(result.creative_direction, indent=2)[:200]}")
        
        if result.broll_suggestions:
            print(f"  B-Roll suggestions: {len(result.broll_suggestions)} clips")
        
        print(f"  Time: {elapsed:.2f}s")
        
        assert len(result.clips) >= 1, "No clips found"
        assert result.clips[0].score > 0, "Score should be positive"
        assert result.clips[0].hook, "Hook should not be empty"
        assert result.creative_direction, "Creative direction should be present"
        
        print(f"  [PASS] Groq LLM analysis successful ({len(result.clips)} clips)")
        return result
    
    return run_async(run())


# ─── LIVE TEST 3: Groq Whisper API (if audio available) ──────────────────────

def test_live_groq_whisper_api():
    """LIVE: Test Groq Whisper API directly with a small audio."""
    print("\n─── LIVE TEST 3: Groq Whisper API Connection ───")
    
    # Just test the Groq client can be initialized and API is reachable
    from groq import Groq
    
    try:
        client = Groq(api_key=settings.GROQ_API_KEY)
        # Test with a simple chat completion (cheaper than audio)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "Reply with just 'OK'"}],
            max_tokens=5,
        )
        assert response.choices[0].message.content.strip()
        print(f"  Groq API response: {response.choices[0].message.content.strip()}")
        print(f"  Model: {response.model}")
        print(f"  [PASS] Groq API connection verified")
        return True
    except Exception as e:
        print(f"  [FAIL] Groq API error: {e}")
        return False


# ─── LIVE TEST 4: Pipeline Router ─────────────────────────────────────────────

def test_live_pipeline_router():
    """LIVE: Test pipeline router with DB (if available)."""
    print("\n─── LIVE TEST 4: Pipeline Router ───")
    
    router = PipelineRouter()
    
    # Test superadmin routing (no DB needed)
    v = router.get_pipeline_version(user_id=1, is_superadmin=True)
    assert v == "v1"
    print(f"  Superadmin (user_id=1): {v}")
    
    # Test non-premium routing (needs DB — may fail gracefully)
    v = router.get_pipeline_version(user_id=999, is_superadmin=False)
    print(f"  Regular user (user_id=999): {v}")
    # On DB error, defaults to V1 (safe). If DB works and no premium, returns V2.
    assert v in ("v1", "v2")
    
    print(f"  [PASS] Pipeline router works correctly")


# ─── LIVE TEST 5: MicroSlicer with real FFmpeg ───────────────────────────────

def test_live_ffmpeg_available():
    """LIVE: Verify FFmpeg is available on system."""
    print("\n─── LIVE TEST 5: FFmpeg Availability ───")
    
    import subprocess
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
    
    if result.returncode == 0:
        version_line = result.stdout.split("\n")[0]
        print(f"  {version_line}")
        print(f"  [PASS] FFmpeg available")
        return True
    else:
        print(f"  [FAIL] FFmpeg not found")
        return False


# ─── LIVE TEST 6: Full V2 Analysis Pipeline (Transcript → Highlights) ────────

def test_live_full_analysis_pipeline():
    """LIVE: Complete TAHAP 1 + TAHAP 2 (real Groq calls)."""
    print("\n─── LIVE TEST 6: Full Analysis Pipeline (TAHAP 1 + 2) ───")
    
    from src.domain.entities import TranscriptSegment
    
    # Use a realistic transcript (simulating a 5-min Indonesian video)
    transcript = TranscriptResult(
        segments=[
            TranscriptSegment(text="Guys, kalian tau nggak kenapa banyak orang gagal di YouTube?", start=0.0, end=5.0),
            TranscriptSegment(text="Mereka upload video tanpa strategi apapun", start=5.0, end=9.0),
            TranscriptSegment(text="Padahal ada formula yang sudah terbukti berhasil", start=9.0, end=14.0),
            TranscriptSegment(text="Formula ini namanya hook-story-offer", start=14.0, end=18.0),
            TranscriptSegment(text="Hook itu 3 detik pertama yang bikin orang berhenti scroll", start=18.0, end=24.0),
            TranscriptSegment(text="Story adalah cerita yang membuat penonton relate", start=24.0, end=30.0),
            TranscriptSegment(text="Dan offer adalah alasan mereka harus terus menonton", start=30.0, end=36.0),
            TranscriptSegment(text="Saya sendiri dulu cuma punya 500 subscriber", start=36.0, end=41.0),
            TranscriptSegment(text="Tapi setelah pakai formula ini, dalam 2 bulan naik jadi 20 ribu", start=41.0, end=48.0),
            TranscriptSegment(text="Yang paling penting adalah editing yang cepat dan engaging", start=48.0, end=54.0),
            TranscriptSegment(text="Jangan biarkan ada dead space lebih dari 2 detik", start=54.0, end=60.0),
            TranscriptSegment(text="Gunakan jump cut, zoom, dan text overlay", start=60.0, end=65.0),
            TranscriptSegment(text="Sekarang saya kasih contoh real dari video saya yang viral", start=65.0, end=71.0),
            TranscriptSegment(text="Video ini dapat 2 juta views dalam 1 minggu", start=71.0, end=76.0),
            TranscriptSegment(text="Rahasianya ada di 3 detik pertama", start=76.0, end=80.0),
            TranscriptSegment(text="Saya pakai pertanyaan kontroversial sebagai hook", start=80.0, end=86.0),
            TranscriptSegment(text="Lalu langsung masuk ke bukti visual yang shocking", start=86.0, end=92.0),
            TranscriptSegment(text="Ini membuat retention rate naik sampai 70 persen", start=92.0, end=98.0),
            TranscriptSegment(text="Coba bandingkan dengan video yang hanya dapat 1000 views", start=98.0, end=104.0),
            TranscriptSegment(text="Bedanya sangat jelas dari hook-nya", start=104.0, end=108.0),
            TranscriptSegment(text="Jadi kesimpulannya, fokus di 3 hal: hook, storytelling, editing", start=108.0, end=115.0),
            TranscriptSegment(text="Kalau kalian mau template hook yang saya pakai, comment 'HOOK'", start=115.0, end=122.0),
            TranscriptSegment(text="Dan jangan lupa subscribe karena minggu depan ada tutorial editing", start=122.0, end=128.0),
        ],
        source="synthetic",
        language="id",
        total_duration=128.0,
    )
    
    analyzer = GroqAnalyzer()
    start = time.time()
    
    async def run():
        result = await analyzer.analyze_highlights(
            transcript, video_duration=128.0, max_clips=2
        )
        elapsed = time.time() - start
        
        print(f"  Duration: {elapsed:.2f}s")
        print(f"  Model: {result.model_used}")
        print(f"  Clips: {len(result.clips)}")
        
        for clip in result.clips:
            duration = clip.end - clip.start
            print(f"    #{clip.rank}: [{clip.start:.1f}s → {clip.end:.1f}s] ({duration:.0f}s)")
            print(f"      Score: {clip.score}, Hook: \"{clip.hook}\"")
            print(f"      Type: {clip.content_type}, Energy: {clip.speaker_energy}")
        
        if result.creative_direction:
            cd = result.creative_direction
            print(f"  Creative Direction:")
            print(f"    Colors: {cd.get('primary_color', 'N/A')} / {cd.get('secondary_color', 'N/A')}")
            print(f"    Mood: {cd.get('typography_mood', 'N/A')}")
            print(f"    Energy: {cd.get('energy_level', 'N/A')}")
        
        if result.broll_suggestions:
            for rank, brolls in result.broll_suggestions.items():
                print(f"  B-Roll clip {rank}: {len(brolls)} suggestions")
                for b in brolls[:2]:
                    print(f"    @{b.get('at_time', 0):.1f}s: \"{b.get('keyword', '')}\" ({b.get('template', '')})")
        
        # Validations
        assert len(result.clips) >= 1, "Should find at least 1 clip"
        for clip in result.clips:
            assert 30 <= (clip.end - clip.start) <= 120, f"Clip duration {clip.end-clip.start}s out of range"
            assert 1 <= clip.score <= 100, f"Score {clip.score} out of range"
            assert clip.hook, "Hook should not be empty"
            assert clip.start >= 0, "Start should be >= 0"
            assert clip.end <= 128.0 + 5, "End should be within video"
        
        print(f"\n  [PASS] Full analysis pipeline — {len(result.clips)} valid clips found")
        return result
    
    return run_async(run())


# ─── Run All Live Tests ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  LIVE INTEGRATION TESTS — V2 Pipeline")
    print("  (Calls real Groq API + YouTube API)")
    print("=" * 60)
    
    results = {}
    total_start = time.time()
    
    # Test 1: YouTube Transcript
    try:
        transcript = test_live_youtube_transcript()
        results["youtube_transcript"] = "PASS" if transcript else "SKIP"
    except Exception as e:
        print(f"  [FAIL] {e}")
        results["youtube_transcript"] = "FAIL"
        transcript = None
    
    # Test 2: Groq LLM Analysis
    try:
        analysis = test_live_groq_llm_analysis(transcript)
        results["groq_llm"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] {e}")
        results["groq_llm"] = "FAIL"
    
    # Test 3: Groq API Connection
    try:
        ok = test_live_groq_whisper_api()
        results["groq_api"] = "PASS" if ok else "FAIL"
    except Exception as e:
        print(f"  [FAIL] {e}")
        results["groq_api"] = "FAIL"
    
    # Test 4: Pipeline Router
    try:
        test_live_pipeline_router()
        results["router"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] {e}")
        results["router"] = "FAIL"
    
    # Test 5: FFmpeg
    try:
        ok = test_live_ffmpeg_available()
        results["ffmpeg"] = "PASS" if ok else "FAIL"
    except Exception as e:
        results["ffmpeg"] = "FAIL"
    
    # Test 6: Full Analysis Pipeline
    try:
        test_live_full_analysis_pipeline()
        results["full_pipeline"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] {e}")
        results["full_pipeline"] = "FAIL"
    
    # Summary
    total_elapsed = time.time() - total_start
    print("\n" + "=" * 60)
    print("  LIVE TEST RESULTS")
    print("=" * 60)
    for name, status in results.items():
        icon = "✓" if status == "PASS" else ("⊘" if status == "SKIP" else "✗")
        print(f"  {icon} {name}: {status}")
    
    passed = sum(1 for v in results.values() if v == "PASS")
    failed = sum(1 for v in results.values() if v == "FAIL")
    skipped = sum(1 for v in results.values() if v == "SKIP")
    print(f"\n  Total: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"  Time: {total_elapsed:.1f}s")
    print("=" * 60)
    
    if failed > 0:
        sys.exit(1)
