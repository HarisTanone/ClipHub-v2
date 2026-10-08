"""Unit tests for sentence and segment boundary-aware transcript chunking.

Verifies:
1. Chunks cut cleanly at sentence endings (., ?, !) within the 5-8 min window.
2. Chunks cut cleanly at natural speech pauses (gap >= 0.5s).
3. Overlap rewinds by 30-45s and starts at a sentence boundary.
4. Hard ceilings (8 min / 480s or safety character limit) are enforced.
5. Short videos (< 5 min) remain in a single chunk.
"""
from src.domain.entities import TranscriptSegment
from src.infrastructure.groq_analyzer import GroqAnalyzer


def test_sentence_boundary_cut_within_5_to_8_minutes():
    """Verify chunk flushes at terminal punctuation within 5-8 min window."""
    a = GroqAnalyzer()
    segs = []
    t = 0.0
    # Create segments of 10s each. At 320s (5m20s), place a sentence end '.'
    for i in range(50):
        text = f"kata nomor {i}"
        if i == 32:  # 32 * 10s = 320s to 330s
            text += "."
        segs.append(TranscriptSegment(text=text, start=t, end=t + 10.0))
        t += 10.0

    chunks = a._chunk_transcript_with_ids(segs)
    assert len(chunks) >= 2
    chunk1_segs = chunks[0][0]
    # Chunk 1 must cut right at segment 32 (330s) ending in '.'
    assert chunk1_segs[-1].text.endswith(".")
    assert chunk1_segs[-1].end == 330.0


def test_speech_pause_boundary_cut():
    """Verify chunk flushes at speech pause gap >= 0.5s within 5-8 min window."""
    a = GroqAnalyzer()
    segs = []
    t = 0.0
    for i in range(50):
        text = f"kata nomor {i}"  # No terminal punctuation
        dur = 10.0
        gap = 0.8 if i == 34 else 0.0  # 34 * 10s = 340s to 350s has pause after it
        segs.append(TranscriptSegment(text=text, start=t, end=t + dur))
        t += dur + gap

    chunks = a._chunk_transcript_with_ids(segs)
    assert len(chunks) >= 2
    chunk1_segs = chunks[0][0]
    # Chunk 1 cuts at segment 34 because gap after it is 0.8s
    assert chunk1_segs[-1].text == "kata nomor 34"


def test_sentence_boundary_overlap():
    """Verify overlap rewinds by 30-45s and starts at a new sentence."""
    a = GroqAnalyzer()
    segs = []
    t = 0.0
    # Segments of 5s each
    for i in range(80):
        text = f"kalimat {i}"
        if i % 6 == 0:  # Sentence ends every ~30s
            text += "."
        segs.append(TranscriptSegment(text=text, start=t, end=t + 5.0))
        t += 5.0

    chunks = a._chunk_transcript_with_ids(segs)
    assert len(chunks) >= 2
    chunk1_end = chunks[0][0][-1].end
    chunk2_start = chunks[1][0][0].start
    overlap_duration = chunk1_end - chunk2_start

    # Overlap must be around 30-45s sweet spot (between 25s and 55s)
    assert 25.0 <= overlap_duration <= 55.0

    # Chunk 2's starting segment must start after a sentence terminator
    # Find the segment before chunk 2's first segment in segs
    c2_first_seg = chunks[1][0][0]
    c2_idx = next(idx for idx, s in enumerate(segs) if s.start == c2_first_seg.start)
    assert c2_idx > 0
    prev_seg = segs[c2_idx - 1]
    assert prev_seg.text.endswith(".") or (c2_first_seg.start - prev_seg.end >= 0.5)


def test_hard_ceiling_8_minutes():
    """Verify monologue without punctuation cuts at 8 min ceiling."""
    a = GroqAnalyzer()
    segs = [
        TranscriptSegment(text="monolog tanpa titik", start=i * 10.0, end=(i + 1) * 10.0)
        for i in range(60)  # 600s total (10 min)
    ]
    chunks = a._chunk_transcript_with_ids(segs)
    assert len(chunks) >= 2
    for chunk_segs, _ in chunks:
        dur = chunk_segs[-1].end - chunk_segs[0].start
        assert dur <= 480.0  # Must never exceed 8 minutes


def test_short_video_single_chunk():
    """Verify videos under 5 minutes remain in a single chunk."""
    a = GroqAnalyzer()
    segs = [
        TranscriptSegment(text=f"segmen {i}.", start=i * 10.0, end=(i + 1) * 10.0)
        for i in range(25)  # 250s (4m10s)
    ]
    chunks = a._chunk_transcript_with_ids(segs)
    assert len(chunks) == 1
    assert len(chunks[0][0]) == 25
