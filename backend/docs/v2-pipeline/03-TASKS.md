# Task Breakdown — API Backend V2 (Non-Premium Pipeline)

## Implementation Order & Dependencies

```
Task 1 (Config)
    │
    ├── Task 2 (GroqTranscriber) ─── independent
    ├── Task 3 (GroqAnalyzer) ────── depends on Task 2 output format
    ├── Task 4 (MicroSlicer) ─────── independent
    ├── Task 5 (SelectiveWhisper) ── depends on Task 4 output
    ├── Task 6 (SileroVAD) ───────── depends on Task 4 output
    │
    ▼
Task 7 (Orchestrator) ── depends on Tasks 2-6
    │
    ▼
Task 8 (Premium Router) ── depends on Task 7
    │
    ▼
Task 9 (API Integration) ── depends on Task 8
    │
    ▼
Task 10 (Full Integration Test) ── depends on all
```

---

## Task 1: Add Groq Configuration & Dependencies

### Files to Create/Modify
| Action | File |
|--------|------|
| MODIFY | `backend/requirements.txt` |
| MODIFY | `backend/src/config.py` |
| MODIFY | `backend/.env.example` |
| MODIFY | `backend/src/domain/entities.py` |
| MODIFY | `backend/src/domain/interfaces.py` |

### Subtasks
1. Add `groq>=0.9.0` and `pydub>=0.25.0` to requirements.txt
2. Add Groq + V2 settings to `Settings` class in config.py
3. Add `.env.example` entries for GROQ_API_KEY and V2 params
4. Add new domain entities: `TranscriptSegment`, `TranscriptResult`, `AudioSlice`, `HighlightAnalysisResult`
5. Add new interfaces: `IGroqTranscriber`, `IGroqAnalyzer`, `IMicroSlicer`, `ISileroVAD`

### Testing
```bash
# Verify import works
python -c "from groq import Groq; print('OK')"
python -c "from src.config import settings; print(settings.GROQ_API_KEY)"
python -c "from src.domain.interfaces import IGroqTranscriber; print('OK')"
```

### Acceptance
- [ ] `pip install -r requirements.txt` tanpa error
- [ ] Settings load dari .env tanpa crash
- [ ] Domain entities importable
- [ ] Interfaces definisi lengkap

---

## Task 2: Implement IGroqTranscriber (TAHAP 1)

### Files to Create
| Action | File |
|--------|------|
| CREATE | `backend/src/infrastructure/groq_transcriber.py` |

### Subtasks
1. Implement `_fetch_youtube_transcript()`:
   - Use `youtube-transcript-api` (existing dependency)
   - Language priority: id → en → auto → any
   - Convert to `TranscriptResult`
2. Implement `_transcribe_via_groq_whisper()`:
   - Download audio only via subprocess yt-dlp
   - Calculate chunk count based on file size (max 25MB)
   - Split audio with FFmpeg
   - Call Groq Whisper API per chunk
   - Merge results
3. Implement `transcribe()` main method:
   - Try YouTube first → fallback Groq
   - Error handling + logging

### Testing (Unit)
```python
# Test 1: YouTube transcript available
async def test_youtube_transcript_success():
    transcriber = GroqTranscriber(groq_api_key="test")
    # Mock youtube_transcript_api to return data
    result = await transcriber.transcribe("https://youtube.com/watch?v=TEST", 300.0)
    assert result.source == "youtube_api"
    assert len(result.segments) > 0

# Test 2: YouTube fails → Groq Whisper
async def test_groq_whisper_fallback():
    # Mock youtube_transcript_api to raise NoTranscriptFound
    # Mock Groq API to return transcript
    result = await transcriber.transcribe(url, 300.0)
    assert result.source == "groq_whisper"

# Test 3: Both fail → raises error
async def test_both_fail():
    with pytest.raises(TranscriptionError):
        await transcriber.transcribe(url, 300.0)

# Test 4: Audio chunk splitting
def test_audio_chunking():
    chunks = transcriber._calculate_chunks(file_size_bytes=75_000_000, max_chunk_bytes=25_000_000)
    assert chunks == 3
```

### Acceptance
- [ ] YouTube transcript fetched correctly for video with captions
- [ ] Groq Whisper API called correctly with chunked audio
- [ ] TranscriptResult output format matches spec
- [ ] Error handling: timeout, rate limit, no transcript

---

## Task 3: Implement IGroqHighlightAnalyzer (TAHAP 2)

### Files to Create
| Action | File |
|--------|------|
| CREATE | `backend/src/infrastructure/groq_analyzer.py` |

### Subtasks
1. Implement `_chunk_transcript()`:
   - Dynamic chunking: max 600s OR 4000 chars
   - Respect sentence boundaries (don't split mid-sentence)
2. Implement `_analyze_chunk()`:
   - Groq LLM call with structured prompt
   - JSON response parsing with tolerance
   - Retry logic (3 attempts)
3. Implement `_rank_and_merge()`:
   - Merge candidates from all chunks
   - Global ranking by score
   - Limit to max_clips
4. Implement `_generate_creative_direction()`:
   - Single LLM call with all clip context
   - Generate colors, mood, typography, B-Roll suggestions
5. Implement `analyze_highlights()` main method:
   - Chunk → analyze each → merge → rank → creative direction

### Prompt Design (key)
```
System: "Kamu adalah AI analis konten viral. Tugasmu mengidentifikasi momen paling menarik."
User: "Transkrip [{start}s - {end}s]: {text}\n\nTemukan momen viral (45-90 detik)..."
Output: JSON {clips: [{rank, start, end, score, hook, reason, content_type, speaker_energy}]}
```

### Testing (Unit)
```python
# Test 1: Dynamic chunking correctness
def test_chunk_transcript_short_video():
    segments = [TranscriptSegment(text="Hello", start=0, end=5)] * 10  # 50s total
    chunks = analyzer._chunk_transcript(segments)
    assert len(chunks) == 1  # Under 600s, single chunk

def test_chunk_transcript_long_video():
    segments = make_segments(duration=1800)  # 30 min
    chunks = analyzer._chunk_transcript(segments)
    assert len(chunks) == 3  # ~10 min each

# Test 2: JSON parsing with tolerance
def test_parse_llm_response_clean():
    raw = '{"clips": [{"rank": 1, "start": 10.0, "end": 55.0}]}'
    result = analyzer._parse_response(raw)
    assert result["clips"][0]["start"] == 10.0

def test_parse_llm_response_with_markdown():
    raw = '```json\n{"clips": [...]}\n```'
    result = analyzer._parse_response(raw)
    assert "clips" in result

# Test 3: Clip ranking
def test_rank_and_merge():
    candidates = [{"score": 50}, {"score": 90}, {"score": 70}]
    ranked = analyzer._rank_and_merge(candidates, max_clips=2)
    assert ranked[0]["score"] == 90
    assert len(ranked) == 2

# Test 4: Overlap detection
def test_no_overlapping_clips():
    clips = analyzer._remove_overlaps(candidates)
    for i in range(len(clips) - 1):
        assert clips[i]["end"] <= clips[i+1]["start"]
```

### Acceptance
- [ ] Dynamic chunking respects both time and char limits
- [ ] Groq LLM responses parsed correctly (with/without markdown)
- [ ] Clips ranked by score, limited to max_clips
- [ ] No overlapping clips in output
- [ ] Creative direction generated with valid hex colors
- [ ] B-Roll suggestions include at_time, keyword, template, visual_category

---

## Task 4: Implement MicroSlicer (TAHAP 3)

### Files to Create
| Action | File |
|--------|------|
| CREATE | `backend/src/infrastructure/micro_slicer.py` |

### Subtasks
1. Implement `_calculate_padded_boundaries()`:
   - Add ±3s padding
   - Clamp to [0, video_duration]
2. Implement `_extract_audio_segment()`:
   - FFmpeg subprocess call
   - Output: WAV 16kHz mono
   - Error handling
3. Implement `slice_audio()` main method:
   - Loop highlights
   - Extract each → AudioSlice

### Testing (Unit)
```python
# Test 1: Padding calculation
def test_padding_normal():
    start, end = slicer._calculate_padded_boundaries(10.0, 50.0, video_duration=120.0)
    assert start == 7.0   # 10 - 3
    assert end == 53.0    # 50 + 3

def test_padding_clamp_start():
    start, end = slicer._calculate_padded_boundaries(1.0, 50.0, video_duration=120.0)
    assert start == 0.0   # clamped, not -2

def test_padding_clamp_end():
    start, end = slicer._calculate_padded_boundaries(100.0, 119.0, video_duration=120.0)
    assert end == 120.0   # clamped

# Test 2: FFmpeg command construction
def test_ffmpeg_command():
    cmd = slicer._build_ffmpeg_command("video.mp4", 7.0, 53.0, "clip_1.wav")
    assert "-ar" in cmd and "16000" in cmd
    assert "-ac" in cmd and "1" in cmd

# Test 3: Full slice (integration with real FFmpeg)
async def test_slice_produces_wav():
    slices = await slicer.slice_audio("test_video.mp4", highlights, "tmp/")
    for s in slices:
        assert os.path.exists(s.audio_path)
        assert s.audio_path.endswith(".wav")
```

### Acceptance
- [ ] Padding ±3s correctly applied
- [ ] Boundaries clamped to video duration
- [ ] Output WAV files: 16kHz, mono, PCM
- [ ] Error handling: FFmpeg failure per clip doesn't crash pipeline

---

## Task 5: Implement SelectiveWhisperTranscriber (TAHAP 4)

### Files to Create
| Action | File |
|--------|------|
| CREATE | `backend/src/infrastructure/selective_whisper.py` |

### Subtasks
1. Implement timestamp offset mapping:
   - Local whisper timestamps → absolute video timestamps
   - `absolute_start = local_start + audio_slice.padded_start`
2. Implement `transcribe_with_offset()`:
   - Call existing `IWhisperLocal.transcribe_clip()`
   - Map all word timestamps to absolute
3. Implement batch processing:
   - Process clips with concurrency limit (semaphore)
   - Timeout per clip (300s)

### Testing (Unit)
```python
# Test 1: Offset mapping
def test_offset_mapping():
    # Whisper returns word at local 5.0s
    # Audio slice padded_start = 47.0s
    # Expected absolute: 52.0s
    words = [{"word": "test", "start": 5.0, "end": 5.5}]
    mapped = transcriber._apply_offset(words, padded_start=47.0)
    assert mapped[0].start == 52.0
    assert mapped[0].end == 52.5

# Test 2: Word boundary matching
def test_find_clip_words():
    # Given highlight: start=50.0, end=85.0
    # After whisper + offset, find words within this range
    all_words = [Word("a", 48.0, 48.5), Word("b", 51.0, 51.5), Word("c", 84.0, 84.5), Word("d", 87.0, 87.5)]
    clip_words = transcriber._filter_words_in_range(all_words, 50.0, 85.0)
    assert len(clip_words) == 2  # "b" and "c"

# Test 3: Timeout handling
async def test_whisper_timeout():
    # Mock whisper to take > 300s
    result = await transcriber.transcribe_with_offset(slow_slice)
    assert result == []  # Empty on timeout
```

### Acceptance
- [ ] Word timestamps correctly offset to absolute video position
- [ ] Words filtered to clip range
- [ ] Timeout per clip: returns empty list (not crash)
- [ ] Fallback: use segment-level from TAHAP 1 if word-level fails

---

## Task 6: Implement SileroVAD (TAHAP 5)

### Files to Create
| Action | File |
|--------|------|
| CREATE | `backend/src/infrastructure/silero_vad.py` |

### Subtasks
1. Implement VAD model loading:
   - torch.hub.load Silero VAD (cached)
   - Singleton pattern (load once, reuse)
2. Implement `_detect_speech_segments()`:
   - Load audio, run VAD
   - Output: list of speech intervals
3. Implement `_find_nearest_silence()`:
   - Given target time, find closest silence gap
   - Search within ±search_radius
4. Implement `refine_boundaries()`:
   - Refine start → nearest silence before
   - Refine end → nearest silence after

### Testing (Unit)
```python
# Test 1: Silence detection
def test_find_silence_at_start():
    # Speech segments: [(1.0, 3.0), (3.5, 5.0)]
    # Silence gaps: [(0, 1.0), (3.0, 3.5)]
    # Target start: 2.5 → nearest silence before = 0.0-1.0 gap too far, but 3.0-3.5 is close
    silence = vad._find_nearest_silence(
        speech_segments=[(1.0, 3.0), (3.5, 5.0)],
        target_time=2.5,
        direction="before",
        radius=2.0
    )
    # No silence before 2.5 within 2s except gap at 0-1.0 (too far)
    # Actually (0, 1.0) end at 1.0, which is 1.5s before target → within radius
    assert silence == 1.0  # end of silence gap

# Test 2: No silence found → use original
def test_no_silence_fallback():
    # Continuous speech, no gaps
    result = vad._find_nearest_silence(
        speech_segments=[(0, 60.0)],
        target_time=30.0,
        direction="before",
        radius=2.0
    )
    assert result is None  # Fallback: use original timestamp

# Test 3: Full refinement
async def test_refine_boundaries():
    final_start, final_end = await vad.refine_boundaries(
        audio_path="clip.wav",
        target_start=10.0,
        target_end=55.0,
    )
    # Should be slightly shifted to silence points
    assert final_start <= 10.0  # Moved back to silence
    assert final_end >= 55.0    # Moved forward to silence (or same)
```

### Acceptance
- [ ] Silero model loads successfully (torch hub)
- [ ] Speech/silence detection accurate (>90% match)
- [ ] Boundaries refined to silence gaps
- [ ] Fallback to original timestamps if no silence found
- [ ] Performance: < 1 second per clip

---

## Task 7: Implement V2PipelineOrchestrator

### Files to Create
| Action | File |
|--------|------|
| CREATE | `backend/src/application/services_v2.py` |

### Subtasks
1. Implement `V2PipelineService` class:
   - Constructor: inject all V2 components + shared components
   - Implement `_run_v2_pipeline()` method
2. Pipeline orchestration:
   - Step 1-2: Validate + Download (reuse existing)
   - Step 3: V2 Transcript (TAHAP 1)
   - Step 4: V2 Highlight Analysis (TAHAP 2)
   - Step 5: Prepare Clips (reuse existing)
   - Step 6: Aspect Ratio Router (reuse existing)
   - Step 7: Trim Clips (reuse existing)
   - Step 7.5: Micro-Slice (TAHAP 3)
   - Step 8: YOLO Reframe (reuse existing)
   - Step 9: Selective Whisper (TAHAP 4)
   - Step 9.5: Silero VAD (TAHAP 5)
   - Step 10+: Reuse existing pipeline steps
3. SSE progress events for V2 steps
4. Error handling + cleanup

### Testing (Integration)
```python
# Test 1: Full pipeline mock (all components mocked)
async def test_v2_pipeline_happy_path():
    service = V2PipelineService(
        groq_transcriber=MockGroqTranscriber(),
        groq_analyzer=MockGroqAnalyzer(),
        micro_slicer=MockMicroSlicer(),
        selective_whisper=MockSelectiveWhisper(),
        silero_vad=MockSileroVAD(),
        ...existing_mocks...
    )
    job = Job(job_id="test_001", youtube_url="...", pipeline_version="v2")
    await service._run_v2_pipeline(job)
    assert job.status == JobStatus.COMPLETED

# Test 2: TAHAP 1 failure → job fails
async def test_v2_pipeline_transcript_failure():
    service = V2PipelineService(
        groq_transcriber=FailingTranscriber(),
        ...
    )
    await service._run_v2_pipeline(job)
    assert job.status == JobStatus.FAILED
    assert "transcript" in job.error_message.lower()

# Test 3: Partial clip failure → continues
async def test_v2_pipeline_partial_clip_failure():
    # 3 clips, middle one fails whisper
    service = V2PipelineService(...)
    await service._run_v2_pipeline(job)
    assert job.clips_success == 2
    assert job.clips_failed == 1
```

### Acceptance
- [ ] Full V2 pipeline executes in correct order
- [ ] Output format identical to V1 (Clip, Word, CreativeDirection)
- [ ] SSE progress events emitted correctly
- [ ] Partial failures handled gracefully
- [ ] Cleanup of temp files on completion

---

## Task 8: Implement Premium Check & Pipeline Routing

### Files to Create/Modify
| Action | File |
|--------|------|
| CREATE | `backend/src/infrastructure/pipeline_router.py` |
| MODIFY | `backend/src/application/services.py` |
| MODIFY | `backend/src/presentation/routes/features.py` |
| MODIFY | `backend/src/infrastructure/database.py` |

### Subtasks
1. Add `premium_pipeline` to `AVAILABLE_FEATURES`
2. Add `pipeline_version` column to JobModel
3. Implement `PipelineRouter.should_use_v2(user_id)`
4. Modify `JobService.create_job()` to call router
5. Route to `V2PipelineService` or existing `_run_pipeline`

### Testing (Unit + Integration)
```python
# Test 1: Non-premium user → V2
def test_route_non_premium():
    router = PipelineRouter()
    # User without premium_pipeline feature
    assert router.should_use_v2(user_id=5) == True

# Test 2: Premium user → V1
def test_route_premium():
    # Grant premium_pipeline feature
    assert router.should_use_v2(user_id=1) == False  # superadmin

# Test 3: Superadmin always V1
def test_superadmin_always_v1():
    assert router.should_use_v2(user_id=1) == False

# Test 4: Job creation routes correctly
async def test_create_job_routes_to_v2():
    # Non-premium user creates job
    job, _ = await service.create_job(url, user_id=5)
    assert job.pipeline_version == "v2"

# Test 5: Integration — V1 user still works
async def test_create_job_routes_to_v1():
    # Premium user creates job
    job, _ = await service.create_job(url, user_id=1)
    assert job.pipeline_version == "v1"
```

### Acceptance
- [ ] Premium feature registered in AVAILABLE_FEATURES
- [ ] pipeline_version stored in DB for each job
- [ ] Non-premium users automatically get V2
- [ ] Superadmin/premium users get V1
- [ ] No regression in existing V1 pipeline

---

## Task 9: API Routes & Frontend Integration

### Files to Modify
| Action | File |
|--------|------|
| MODIFY | `backend/src/presentation/schemas/jobs.py` |
| MODIFY | `backend/src/presentation/routes/jobs.py` |
| MODIFY | `backend/src/presentation/dependencies.py` |

### Subtasks
1. Add `pipeline_version` field to `JobResponse` schema
2. Update `get_job_service()` dependency to inject V2 components
3. Ensure SSE progress events work for V2 step names
4. Test API response format compatibility

### Testing (API)
```python
# Test 1: POST /api/jobs returns pipeline_version
async def test_create_job_response_has_version():
    response = await client.post("/api/jobs", json={"youtube_url": "..."}, headers=auth)
    assert response.status_code == 201
    assert "pipeline_version" in response.json()

# Test 2: GET /api/jobs/{id} shows V2 status steps
async def test_get_job_v2_progress():
    response = await client.get(f"/api/jobs/{job_id}", headers=auth)
    data = response.json()
    assert data["pipeline_version"] == "v2"

# Test 3: SSE stream includes V2 events
async def test_sse_v2_events():
    # Connect to SSE endpoint
    # Verify v2_transcript, v2_highlight_analysis events appear
    pass

# Test 4: Existing V1 endpoints not broken
async def test_v1_compatibility():
    # Premium user creates job → V1 behavior unchanged
    response = await client.post("/api/jobs", json={"youtube_url": "..."}, headers=premium_auth)
    assert response.json()["pipeline_version"] == "v1"
```

### Acceptance
- [ ] API response includes pipeline_version
- [ ] No breaking changes to existing API contract
- [ ] Frontend displays V2 progress correctly
- [ ] SSE events for V2 steps work

---

## Task 10: Full Integration Testing

### Test Scenarios

| # | Scenario | Pipeline | Expected |
|---|----------|----------|----------|
| 1 | Short video (3 min), has YT transcript | V2 | Fast completion, YT source |
| 2 | Medium video (15 min), has YT transcript | V2 | Multi-chunk analysis |
| 3 | Video without transcript (Groq fallback) | V2 | Groq Whisper used |
| 4 | Long video (60 min) | V2 | 8+ chunks, multiple clips |
| 5 | Premium user, same video | V1 | Gemini pipeline |
| 6 | Groq rate limited | V2 | Circuit breaker + retry |
| 7 | Partial clip failure | V2 | Some clips succeed |
| 8 | Invalid URL | Both | Validation error |
| 9 | Concurrent jobs (2) | V2 | Semaphore works |
| 10 | Re-process same URL | V2 | Dedup works |

### End-to-End Test Script
```python
"""E2E test for V2 pipeline."""
import httpx
import asyncio
import time

BASE_URL = "http://localhost:8000/api"

async def test_v2_e2e():
    async with httpx.AsyncClient() as client:
        # 1. Login as non-premium user
        login = await client.post(f"{BASE_URL}/auth/login", json={
            "email": "test@example.com",
            "password": "TestPass123!"
        })
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Create job
        job_resp = await client.post(f"{BASE_URL}/jobs", json={
            "youtube_url": "https://www.youtube.com/watch?v=TEST_VIDEO",
            "target_aspect_ratio": "9:16",
        }, headers=headers)
        assert job_resp.status_code == 201
        job_id = job_resp.json()["job_id"]
        assert job_resp.json()["pipeline_version"] == "v2"
        
        # 3. Poll until complete
        for _ in range(120):  # max 2 min wait
            status = await client.get(f"{BASE_URL}/jobs/{job_id}", headers=headers)
            data = status.json()
            if data["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(1)
        
        # 4. Assert success
        assert data["status"] == "completed"
        assert data["clips_success"] >= 1
        assert data["clips_data"] is not None

        # 5. Verify clip files exist
        clips = data["clips_data"]["clips"]
        for clip in clips:
            assert "output_path" in clip or "video_url" in clip
```

### Performance Benchmarks
| Video Duration | Target Time | Max Time |
|----------------|-------------|----------|
| 5 min | < 45s | 90s |
| 15 min | < 90s | 180s |
| 30 min | < 150s | 300s |
| 60 min | < 300s | 600s |

### Rollback Plan
If V2 causes issues:
1. Set `V2_PIPELINE_ENABLED=false` in .env
2. Grant `premium_pipeline` to all users (forces V1)
3. No data migration needed (same schema)

---

## Summary Timeline

| Task | Estimated Effort | Dependencies |
|------|-----------------|--------------|
| Task 1: Config & Dependencies | 30 min | None |
| Task 2: GroqTranscriber | 2 hr | Task 1 |
| Task 3: GroqAnalyzer | 3 hr | Task 1 |
| Task 4: MicroSlicer | 1 hr | Task 1 |
| Task 5: SelectiveWhisper | 1.5 hr | Task 1, 4 |
| Task 6: SileroVAD | 1.5 hr | Task 1, 4 |
| Task 7: V2 Orchestrator | 3 hr | Tasks 2-6 |
| Task 8: Premium Router | 1 hr | Task 7 |
| Task 9: API Integration | 1 hr | Task 8 |
| Task 10: Integration Test | 2 hr | All |
| **TOTAL** | **~17 hr** | |
