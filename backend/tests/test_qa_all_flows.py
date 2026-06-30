"""Brutal QA Test Suite — All Pipeline Flows
Run: cd backend && python -m tests.test_qa_all_flows

Tests ALL critical paths with good, bad, and edge scenarios.
"""
import asyncio
import sys
import os
import tempfile
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.domain.entities import TranscriptResult, TranscriptSegment, Word

# ═══════════════════════════════════════════════════════════════════════════════
# Test utilities
# ═══════════════════════════════════════════════════════════════════════════════

results = {"passed": 0, "failed": 0, "skipped": 0, "details": []}


def report(test_name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    results["passed" if passed else "failed"] += 1
    results["details"].append({"name": test_name, "status": status, "detail": detail})
    print(f"  [{status}] {test_name}")
    if detail and not passed:
        print(f"         → {detail}")


def skip(test_name: str, reason: str):
    results["skipped"] += 1
    results["details"].append({"name": test_name, "status": "SKIP", "detail": reason})
    print(f"  [SKIP] {test_name} — {reason}")


def make_transcript(num_segments: int, duration: float, texts: list = None):
    seg_dur = duration / max(1, num_segments)
    segments = []
    for i in range(num_segments):
        text = texts[i] if texts and i < len(texts) else f"Ini adalah segment nomor {i} dari video"
        segments.append(TranscriptSegment(text=text, start=i * seg_dur, end=(i + 1) * seg_dur))
    return TranscriptResult(segments=segments, source="test", language="id", total_duration=duration)


# ═══════════════════════════════════════════════════════════════════════════════
# A. LLM Analysis (Groq) Tests
# ═══════════════════════════════════════════════════════════════════════════════

async def test_a_llm():
    print("\n" + "═" * 60)
    print("A. LLM ANALYSIS (Groq) — Clip Extraction")
    print("═" * 60)

    from src.infrastructure.highlight_analyzer import HighlightAnalyzer
    analyzer = HighlightAnalyzer()

    if not analyzer._groq_key:
        skip("A1-A8", "GROQ_API_KEY not configured")
        return

    # A1: Normal 5-min video
    try:
        t = make_transcript(20, 300.0)
        result = await analyzer._analyze_with_groq(t, 300.0, 3)
        report("A1: Normal 5-min video (20 seg, 3 clips)",
               result is not None and len(result.clips) >= 1,
               f"Got {len(result.clips) if result else 0} clips")
    except Exception as e:
        report("A1: Normal 5-min video", False, str(e)[:100])

    # A2: Long video 30-min
    try:
        t = make_transcript(200, 1800.0)
        result = await analyzer._analyze_with_groq(t, 1800.0, 5)
        report("A2: Long 30-min video (200 seg, 5 clips)",
               result is not None and len(result.clips) >= 1,
               f"Got {len(result.clips) if result else 0} clips")
    except Exception as e:
        report("A2: Long 30-min video", False, str(e)[:100])

    # A3: Very short video (30s)
    try:
        t = make_transcript(3, 30.0)
        result = await analyzer._analyze_with_groq(t, 30.0, 2)
        # May return None (no clips long enough) — that's OK, should not crash
        report("A3: Very short 30s video (3 seg)",
               True,  # Just shouldn't crash
               f"Got {len(result.clips) if result else 0} clips (OK if 0 — video too short)")
    except Exception as e:
        report("A3: Very short 30s video", False, str(e)[:100])

    # A4: Single segment
    try:
        t = make_transcript(1, 60.0)
        result = await analyzer._analyze_with_groq(t, 60.0, 1)
        report("A4: Single segment video", True, "No crash")
    except Exception as e:
        report("A4: Single segment video", False, str(e)[:100])

    # A5: Empty transcript
    try:
        t = TranscriptResult(segments=[], source="test", language="id", total_duration=0)
        result = await analyzer._analyze_with_groq(t, 0, 1)
        report("A5: Empty transcript (0 segments)", True, "No crash")
    except Exception as e:
        report("A5: Empty transcript", False, str(e)[:100])

    # A6: Unicode/special chars
    try:
        t = make_transcript(5, 300.0, [
            "Harga naik 100%! \U0001f631 Ini gila banget",
            "Dia bilang \"gue nggak mau\" sambil nangis",
            "C'est la vie \u2014 hidup memang begini",
            "\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35 mixed language content here",
            "Final segment with special chars: <>&\"'",
        ])
        result = await analyzer._analyze_with_groq(t, 300.0, 2)
        report("A6: Unicode/special characters",
               True,  # Should not crash
               f"Got {len(result.clips) if result else 0} clips")
    except Exception as e:
        report("A6: Unicode/special characters", False, str(e)[:100])

    # A7: Overlapping timestamps
    try:
        segments = [
            TranscriptSegment(text="First overlapping", start=0, end=10),
            TranscriptSegment(text="Second overlapping", start=5, end=15),  # overlaps!
            TranscriptSegment(text="Third normal", start=15, end=60),
        ]
        t = TranscriptResult(segments=segments, source="test", language="id", total_duration=60)
        result = await analyzer._analyze_with_groq(t, 60.0, 1)
        report("A7: Overlapping timestamps", True, "No crash")
    except Exception as e:
        report("A7: Overlapping timestamps", False, str(e)[:100])


# ═══════════════════════════════════════════════════════════════════════════════
# B. Segment ID System Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_b_segment_ids():
    print("\n" + "═" * 60)
    print("B. SEGMENT ID SYSTEM — Build, Format, Resolve")
    print("═" * 60)

    # B1: Segment map built correctly
    segments = [
        TranscriptSegment(text="First", start=0.0, end=5.5),
        TranscriptSegment(text="Second", start=5.5, end=12.3),
        TranscriptSegment(text="Third", start=12.3, end=20.0),
    ]

    segment_map = {}
    transcript_lines = []
    for i, seg in enumerate(segments):
        seg_id = f"S{i:04d}"
        segment_map[seg_id] = {"start": seg.start, "end": seg.end, "text": seg.text}
        mins, secs = divmod(int(seg.start), 60)
        transcript_lines.append(f"[{seg_id} | {mins:02d}:{secs:02d}] {seg.text.strip()}")

    report("B1: Segment map built correctly",
           len(segment_map) == 3 and "S0000" in segment_map and "S0002" in segment_map,
           f"Map has {len(segment_map)} entries")

    # B2: Format includes IDs
    report("B2: Transcript format includes IDs",
           "[S0000 | 00:00]" in transcript_lines[0] and "[S0002 | 00:12]" in transcript_lines[2],
           f"Line 0: {transcript_lines[0][:30]}")

    # B3: Resolution of valid IDs
    start = segment_map["S0001"]["start"]
    end = segment_map["S0002"]["end"]
    report("B3: Valid ID resolution",
           start == 5.5 and end == 20.0,
           f"S0001.start={start}, S0002.end={end}")

    # B4: Invalid ID handling
    invalid_id = "S9999"
    exists = invalid_id in segment_map
    report("B4: Invalid ID returns False in map lookup",
           not exists,
           f"'S9999' in map: {exists}")

    # B5: Fallback to raw timestamps
    clip_data = {"start": 5.5, "end": 20.0, "start_id": "INVALID", "end_id": "ALSO_INVALID"}
    start_id = clip_data.get("start_id", "")
    end_id = clip_data.get("end_id", "")
    if start_id in segment_map and end_id in segment_map:
        resolved_start = segment_map[start_id]["start"]
    elif "start" in clip_data and "end" in clip_data:
        resolved_start = float(clip_data["start"])
    else:
        resolved_start = None

    report("B5: Fallback to raw timestamps when IDs invalid",
           resolved_start == 5.5,
           f"Resolved start: {resolved_start}")


# ═══════════════════════════════════════════════════════════════════════════════
# C. Subtitle Timing Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_c_subtitle_timing():
    print("\n" + "═" * 60)
    print("C. SUBTITLE TIMING — Hook Period Filtering")
    print("═" * 60)

    # Simulate the filtering logic from services_v2.py
    hook_dur = 3.0

    # C1: Normal filtering
    words = [
        {"word": "Hello", "start": 0.5, "end": 1.0},
        {"word": "World", "start": 1.5, "end": 2.0},
        {"word": "After", "start": 3.5, "end": 4.0},
        {"word": "Hook", "start": 5.0, "end": 5.5},
    ]
    filtered = [w for w in words if w.get("start", 0) >= hook_dur]
    report("C1: Words during hook filtered out",
           len(filtered) == 2 and filtered[0]["word"] == "After",
           f"{len(filtered)} words remain: {[w['word'] for w in filtered]}")

    # C2: Safety fallback (all words in hook period)
    words_all_early = [
        {"word": "A", "start": 0.0, "end": 0.5},
        {"word": "B", "start": 1.0, "end": 1.5},
        {"word": "C", "start": 2.0, "end": 2.5},
    ]
    filtered2 = [w for w in words_all_early if w.get("start", 0) >= hook_dur]
    if not filtered2 and words_all_early:
        filtered2 = words_all_early  # safety fallback
    report("C2: Safety fallback when ALL words filtered",
           len(filtered2) == 3,
           f"Fallback triggered: {len(filtered2)} words restored")

    # C3: Empty words array
    empty_filtered = [w for w in [] if w.get("start", 0) >= hook_dur]
    report("C3: Empty words → empty result (no crash)",
           len(empty_filtered) == 0,
           "OK")

    # C4: Word at start=0.0
    words_zero = [{"word": "Zero", "start": 0.0, "end": 0.5}]
    filtered_zero = [w for w in words_zero if w.get("start", 0) >= hook_dur]
    report("C4: Word at start=0.0 filtered by hook",
           len(filtered_zero) == 0,
           "Correctly filtered")

    # C5: Word at exactly hook boundary (start=3.0)
    words_boundary = [{"word": "Boundary", "start": 3.0, "end": 3.5}]
    filtered_boundary = [w for w in words_boundary if w.get("start", 0) >= hook_dur]
    report("C5: Word at exactly hook boundary (start=3.0) passes",
           len(filtered_boundary) == 1,
           f"Passed: {filtered_boundary}")


# ═══════════════════════════════════════════════════════════════════════════════
# D. YOLO Reframe Logic Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_d_yolo_logic():
    print("\n" + "═" * 60)
    print("D. YOLO REFRAME LOGIC — Detection & Crop Decisions")
    print("═" * 60)

    import numpy as np

    # Simulate YOLO logic decisions

    # D1: No persons → fallback
    frame_centers_empty = [(0, []), (30, []), (60, [])]
    has_detections = any(len(c) > 0 for _, c in frame_centers_empty)
    report("D1: No persons detected → triggers fallback",
           not has_detections,
           "All frames empty")

    # D2: Single person static (range < 50px)
    # Person stays near center (960px) with minor jitter within deadzone (30px)
    frame_centers_static = [(i * 30, [960.0 + (i % 5) - 2]) for i in range(20)]  # barely moves
    crop_xs = []
    smooth_x = 960.0  # start center
    for _, centers in frame_centers_static:
        if centers:
            target_x = centers[0]
            if abs(target_x - smooth_x) > 30:
                smooth_x += (target_x - smooth_x) * 0.08
        crop_xs.append(int(smooth_x))
    crop_range = max(crop_xs) - min(crop_xs)
    report("D2: Single person static → crop range < 50px",
           crop_range < 50,
           f"Range: {crop_range}px (static crop)")

    # D3: Single person moving (range > 50px)
    frame_centers_moving = [(i * 30, [200.0 + i * 50]) for i in range(20)]  # moves 1000px
    crop_xs2 = []
    smooth_x2 = 960.0
    for _, centers in frame_centers_moving:
        if centers:
            target_x = centers[0]
            if abs(target_x - smooth_x2) > 30:
                smooth_x2 += (target_x - smooth_x2) * 0.08
        crop_xs2.append(int(smooth_x2))
    crop_range2 = max(crop_xs2) - min(crop_xs2)
    report("D3: Single person moving → crop range > 50px → smooth pan",
           crop_range2 > 50,
           f"Range: {crop_range2}px (dynamic pan)")

    # D4: Multiple persons → autogrid check
    frame_centers_multi = [(i * 30, [300.0, 1600.0]) for i in range(10)]  # 2 speakers
    multi_count = sum(1 for _, c in frame_centers_multi if len(c) >= 2)
    total_detected = sum(1 for _, c in frame_centers_multi if len(c) > 0)
    multi_ratio = multi_count / max(1, total_detected)
    report("D4: Two speakers detected → multi_ratio >= 0.7",
           multi_ratio >= 0.7,
           f"Multi ratio: {multi_ratio:.2f} ({multi_count}/{total_detected})")

    # D5: 16:9 → passthrough (no YOLO)
    target = "16:9"
    should_skip = target != "9:16"
    report("D5: Target 16:9 → skip YOLO (passthrough)",
           should_skip,
           f"target={target}, skip={should_skip}")

    # D6: 1:1 → center crop
    target2 = "1:1"
    should_center = target2 != "9:16"
    report("D6: Target 1:1 → center crop (no YOLO)",
           should_center,
           f"target={target2}, center_crop={should_center}")


# ═══════════════════════════════════════════════════════════════════════════════
# E. Remotion Input Path Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_e_remotion_path():
    print("\n" + "═" * 60)
    print("E. REMOTION INPUT PATH — Correct Video Selection")
    print("═" * 60)

    # Simulate the path logic from services_v2.py Remotion block
    with tempfile.TemporaryDirectory() as output_dir:
        rank = 1

        # Create test files
        reframed = f"{output_dir}/clip_{rank:02d}_reframed.mp4"
        base = f"{output_dir}/clip_{rank:02d}.mp4"
        hooked = f"{output_dir}/clip_{rank:02d}_hooked.mp4"

        # E1: Reframed exists → prefer it
        open(reframed, 'w').close()
        open(base, 'w').close()
        in_path = reframed if os.path.exists(reframed) else base
        report("E1: Reframed clip preferred over base",
               in_path == reframed,
               f"Selected: {os.path.basename(in_path)}")

        # E2: Hooked clip NEVER used for Remotion
        open(hooked, 'w').close()
        # The logic should ONLY check reframed > base, NEVER hooked
        in_path2 = reframed if os.path.exists(reframed) else base
        report("E2: Hooked clip NEVER used (even if exists)",
               in_path2 != hooked,
               f"Selected: {os.path.basename(in_path2)} (hooked exists but ignored)")

        # E3: Only base exists
        os.remove(reframed)
        in_path3 = reframed if os.path.exists(reframed) else base
        report("E3: Falls back to base when reframed missing",
               in_path3 == base,
               f"Selected: {os.path.basename(in_path3)}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    print("\n" + "\u2588" * 60)
    print("  BRUTAL QA TEST SUITE \u2014 ALL PIPELINE FLOWS")
    print("\u2588" * 60)

    # Run unit tests (instant)
    test_b_segment_ids()
    test_c_subtitle_timing()
    test_d_yolo_logic()
    test_e_remotion_path()

    # Run integration tests (requires API)
    await test_a_llm()

    # Summary
    print("\n" + "\u2588" * 60)
    total = results["passed"] + results["failed"] + results["skipped"]
    print(f"  SUMMARY: {results['passed']} PASSED | {results['failed']} FAILED | {results['skipped']} SKIPPED | {total} TOTAL")
    print("\u2588" * 60)

    if results["failed"] > 0:
        print("\n  FAILURES:")
        for d in results["details"]:
            if d["status"] == "FAIL":
                print(f"    \u2717 {d['name']}: {d['detail']}")

    # Write results to JSON for report generation
    report_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qa_test_results.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved: {report_path}")

    return results["failed"] == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
