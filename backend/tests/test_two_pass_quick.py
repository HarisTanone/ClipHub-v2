"""Quick test for Two-Pass GroqAnalyzer core functions."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.groq_analyzer import GroqAnalyzer
from src.domain.entities import TranscriptSegment, HighlightCandidate

a = GroqAnalyzer()

if __name__ == "__main__":
    # Test 1: Chunking with Segment IDs
    segs = [TranscriptSegment(text=f"Segment {i}", start=i*30.0, end=(i+1)*30.0) for i in range(10)]
    chunks = a._chunk_transcript_with_ids(segs)
    assert len(chunks) > 0
    assert "[S0000 |" in chunks[0][1]
    print(f"  [PASS] Chunking with IDs: {len(chunks)} chunks, first line has S0000")

    # Test 2: Parse Pass 1 response with Segment IDs
    raw = json.dumps({"clips": [{"start_id": "S0001", "end_id": "S0003", "score": 85, "summary": "test moment", "content_type": "storytelling", "speaker_energy": "high"}]})
    seg_map = {f"S{i:04d}": {"start": i*30.0, "end": (i+1)*30.0, "text": f"Seg {i}"} for i in range(10)}
    candidates = a._parse_pass1_response(raw, seg_map, 0.0, 300.0)
    assert len(candidates) == 1
    assert candidates[0].start == 30.0  # S0001 start
    assert candidates[0].end == 120.0   # S0003 end
    assert candidates[0].score == 85
    assert candidates[0].hook == ""  # No hook in Pass 1
    assert candidates[0].reason == "test moment"
    print(f"  [PASS] Parse Pass 1: S0001→S0003 resolved to 30.0-120.0s")

    # Test 3: Fallback to raw timestamps when no IDs
    raw2 = json.dumps({"clips": [{"start": 50.0, "end": 110.0, "score": 75, "summary": "fallback", "content_type": "humor", "speaker_energy": "medium"}]})
    candidates2 = a._parse_pass1_response(raw2, seg_map, 0.0, 300.0)
    assert len(candidates2) == 1
    assert candidates2[0].start == 50.0
    assert candidates2[0].end == 110.0
    print(f"  [PASS] Fallback raw timestamps: 50.0-110.0s")

    # Test 4: Duration filter
    raw3 = json.dumps({"clips": [
        {"start": 10.0, "end": 20.0, "score": 90, "summary": "too short"},  # 10s < 25s
        {"start": 10.0, "end": 200.0, "score": 90, "summary": "too long"},  # 190s > 120s
        {"start": 50.0, "end": 100.0, "score": 80, "summary": "good"},      # 50s ✓
    ]})
    candidates3 = a._parse_pass1_response(raw3, {}, 0.0, 300.0)
    assert len(candidates3) == 1
    assert candidates3[0].reason == "good"
    print(f"  [PASS] Duration filter: only valid clips pass")

    # Test 5: Deduplicate overlapping
    test_clips = [
        HighlightCandidate(rank=0, start=50.0, end=110.0, score=90, hook="", reason="A"),
        HighlightCandidate(rank=0, start=80.0, end=140.0, score=85, hook="", reason="B"),  # overlaps A
        HighlightCandidate(rank=0, start=200.0, end=260.0, score=80, hook="", reason="C"),
    ]
    deduped = a._deduplicate_candidates(test_clips)
    assert len(deduped) == 2  # A (higher score) wins over B
    assert deduped[0].reason == "A"
    assert deduped[1].reason == "C"
    print(f"  [PASS] Deduplicate: overlapping removed, higher score kept")

    # Test 6: Fallback rank
    ranked = a._fallback_rank(test_clips, 2, 600.0)
    assert len(ranked) == 2
    assert ranked[0].rank == 1
    assert ranked[1].rank == 2
    assert ranked[0].hook != ""  # Fallback generates placeholder hook
    print(f"  [PASS] Fallback rank: 2 clips, ranks assigned, hooks generated")

    print("\n=== ALL TWO-PASS CORE TESTS PASSED (6/6) ===")
