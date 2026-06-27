# Design Document — API Backend V2 (Non-Premium Pipeline)

## 1. Architecture Overview

### 1.1 High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         JOB CREATION (POST /api/jobs)                     │
│                                                                           │
│  ┌──────────────┐     ┌──────────────────┐     ┌─────────────────────┐  │
│  │ Auth Check   │────▶│ Premium Router   │────▶│ V1 (Gemini)         │  │
│  │ (JWT Token)  │     │ (user_features)  │     │ OR                  │  │
│  └──────────────┘     └──────────────────┘     │ V2 (Groq Pipeline) │  │
│                                                  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘

V2 Pipeline Flow:
┌─────────┐   ┌──────────────┐   ┌───────────────┐   ┌────────────────┐
│ TAHAP 1 │──▶│   TAHAP 2    │──▶│   TAHAP 3     │──▶│    TAHAP 4     │
│ Ingest  │   │ Highlight    │   │ Micro-Slice   │   │ Selective      │
│ + Trans │   │ Analysis     │   │ (Audio Cut)   │   │ Whisper        │
└─────────┘   └──────────────┘   └───────────────┘   └────────────────┘
     │                                                         │
     │                                                         ▼
     │              ┌──────────────────────────────────────────────┐
     │              │  TAHAP 5: Silero VAD → Natural Cut Refine    │
     │              └──────────────────────────────────────────────┘
     │                                    │
     ▼                                    ▼
┌──────────────────────────────────────────────────────────────────┐
│          EXISTING PIPELINE (Step 7+)                              │
│  Trim → YOLO → B-Roll → Hook → Subtitle → Encode → Assemble    │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Architecture

```
src/
├── domain/
│   ├── interfaces.py          ← Add: IGroqTranscriber, IGroqAnalyzer, IMicroSlicer, ISileroVAD
│   └── entities.py            ← Add: V2HighlightCandidate, TranscriptSegment
│
├── infrastructure/
│   ├── groq_transcriber.py    ← NEW: YouTube Transcript + Groq Whisper fallback
│   ├── groq_analyzer.py       ← NEW: Highlight analysis via Groq LLM
│   ├── micro_slicer.py        ← NEW: FFmpeg audio extraction per highlight
│   ├── selective_whisper.py   ← NEW: Faster-Whisper on short clips only
│   ├── silero_vad.py          ← NEW: Voice Activity Detection refinement
│   └── pipeline_router.py    ← NEW: Premium check → V1/V2 routing
│
├── application/
│   ├── services.py            ← MODIFY: Add pipeline routing at create_job
│   └── services_v2.py         ← NEW: V2PipelineService (orchestrator)
│
└── presentation/
    └── routes/jobs.py         ← MODIFY: Transparent routing (no API change)
```

---

## 2. Component Design

### 2.1 IGroqTranscriber (TAHAP 1)

**Interface:**
```python
class IGroqTranscriber(ABC):
    @abstractmethod
    async def transcribe(self, youtube_url: str, video_duration: float) -> TranscriptResult:
        """Get transcript: YouTube API first, Groq Whisper fallback."""
        ...
```

**TranscriptResult:**
```python
@dataclass
class TranscriptResult:
    segments: list[TranscriptSegment]   # [{text, start, end}]
    source: str                          # "youtube_api" | "groq_whisper"
    language: str                        # detected language
    total_duration: float
    full_text: str                       # concatenated text for LLM
```

**Implementation Flow:**
```
1. Try youtube-transcript-api → fetch captions
   ├── Success → return TranscriptResult(source="youtube_api")
   └── Fail (no captions) → 
       2. Download audio only (yt-dlp --extract-audio)
       3. Get file size → calculate chunks needed
       4. Split into ≤25MB chunks (FFmpeg)
       5. For each chunk → POST to Groq Whisper API
       6. Merge results → return TranscriptResult(source="groq_whisper")
```

**Groq Whisper API Call:**
```python
from groq import Groq

client = Groq(api_key=GROQ_API_KEY)

transcription = client.audio.transcriptions.create(
    file=open(chunk_path, "rb"),
    model="whisper-large-v3-turbo",
    response_format="verbose_json",   # includes timestamps
    timestamp_granularities=["segment"],
    language="id",                     # optional: auto-detect if omitted
)
```

### 2.2 IGroqAnalyzer (TAHAP 2)

**Interface:**
```python
class IGroqAnalyzer(ABC):
    @abstractmethod
    async def analyze_highlights(
        self, transcript: TranscriptResult, video_duration: float, max_clips: int
    ) -> HighlightAnalysisResult:
        """Analyze transcript → viral highlight candidates."""
        ...
```

**HighlightAnalysisResult:**
```python
@dataclass
class HighlightAnalysisResult:
    clips: list[dict]                    # [{rank, start, end, score, hook, reason, content_type}]
    creative_direction: dict             # {primary_color, typography_mood, ...}
    broll_suggestions: dict              # {clip_rank: [{at_time, keyword, template, ...}]}
```

**Dynamic Chunking Algorithm:**
```python
def chunk_transcript(segments: list[TranscriptSegment], max_seconds=600, max_chars=4000):
    chunks = []
    current_chunk = []
    current_duration = 0
    current_chars = 0
    
    for seg in segments:
        seg_duration = seg.end - seg.start
        seg_chars = len(seg.text)
        
        if (current_duration + seg_duration > max_seconds or 
            current_chars + seg_chars > max_chars) and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_duration = 0
            current_chars = 0
        
        current_chunk.append(seg)
        current_duration += seg_duration
        current_chars += seg_chars
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks
```

**Groq LLM Call (per chunk):**
```python
response = client.chat.completions.create(
    model="llama-3.1-8b-instant",
    messages=[
        {"role": "system", "content": HIGHLIGHT_SYSTEM_PROMPT},
        {"role": "user", "content": f"Transkrip [{chunk_start}s - {chunk_end}s]:\n{chunk_text}"}
    ],
    temperature=0.3,
    max_tokens=2000,
    response_format={"type": "json_object"},
)
```

**Two-Phase LLM Strategy:**
- Phase A (per chunk): Identify clip candidates within each chunk
- Phase B (single call): Rank all candidates, generate creative direction + B-Roll suggestions

### 2.3 IMicroSlicer (TAHAP 3)

**Interface:**
```python
class IMicroSlicer(ABC):
    @abstractmethod
    async def slice_audio(
        self, video_path: str, highlights: list[dict], output_dir: str
    ) -> list[AudioSlice]:
        """Extract audio segments for each highlight with ±3s padding."""
        ...
```

**AudioSlice:**
```python
@dataclass
class AudioSlice:
    clip_rank: int
    audio_path: str           # path to extracted WAV
    original_start: float     # highlight start from Groq
    original_end: float       # highlight end from Groq
    padded_start: float       # with -3s padding
    padded_end: float         # with +3s padding
    duration: float
```

**FFmpeg Command:**
```bash
ffmpeg -y -i video.mp4 \
  -ss {padded_start} -to {padded_end} \
  -ar 16000 -ac 1 -c:a pcm_s16le \
  clip_{rank}.wav
```

### 2.4 SelectiveWhisperTranscriber (TAHAP 4)

**Reuses existing `IWhisperLocal` interface** but with added offset mapping:

```python
class SelectiveWhisperTranscriber:
    def __init__(self, whisper_local: IWhisperLocal):
        self._whisper = whisper_local
    
    async def transcribe_with_offset(
        self, audio_slice: AudioSlice
    ) -> list[Word]:
        """Transcribe short clip, map timestamps to absolute video position."""
        raw_words = await self._whisper.transcribe_clip(audio_slice.audio_path)
        
        # Offset adjustment: local timestamps → absolute video timestamps
        absolute_words = []
        for segment in raw_words:
            for word in segment.get("words", []):
                absolute_words.append(Word(
                    word=word["word"],
                    start=word["start"] + audio_slice.padded_start,
                    end=word["end"] + audio_slice.padded_start,
                ))
        
        return absolute_words
```

### 2.5 ISileroVAD (TAHAP 5)

**Interface:**
```python
class ISileroVAD(ABC):
    @abstractmethod
    async def refine_boundaries(
        self, audio_path: str, target_start: float, target_end: float,
        search_radius: float = 2.0
    ) -> tuple[float, float]:
        """Find nearest silence boundaries around target timestamps."""
        ...
```

**Algorithm:**
```
1. Load audio segment (target_start - 2s) to (target_end + 2s)
2. Run Silero VAD → get speech segments
3. Find silence gap nearest to target_start:
   - Search backwards from target_start
   - Find first silence ≥ 300ms
   - Set final_start = silence_midpoint + 0.1s
4. Find silence gap nearest to target_end:
   - Search forwards from target_end
   - Find first silence ≥ 300ms
   - Set final_end = silence_midpoint - 0.1s
5. If no silence found within radius → keep original timestamp
```

### 2.6 Pipeline Router

**Implementation:**
```python
class PipelineRouter:
    """Determines which pipeline to use based on user premium status."""
    
    PREMIUM_FEATURE_CODE = "premium_pipeline"
    
    def should_use_v2(self, user: CurrentUser) -> bool:
        """Check if user should use V2 (non-premium) pipeline."""
        if user.is_superadmin:
            return False  # Superadmin always gets V1
        
        # Check user_features table
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM user_features WHERE user_id = ? AND feature_code = ?",
                (user.id, self.PREMIUM_FEATURE_CODE)
            )
            has_premium = cur.fetchone() is not None
            return not has_premium  # V2 if NOT premium
        finally:
            conn.close()
```

---

## 3. Data Flow Detail

### 3.1 Complete V2 Pipeline Sequence

```
┌─────────────────────────────────────────────────────────────────────┐
│ Step 1: Validate (existing)                                          │
│ Step 2: Download (existing)                                          │
├─────────────────────────────────────────────────────────────────────┤
│ Step 3: V2 Transcript (TAHAP 1)                                      │
│   Input:  youtube_url, video_duration                                │
│   Output: TranscriptResult {segments, source, language, full_text}   │
├─────────────────────────────────────────────────────────────────────┤
│ Step 4: V2 Highlight Analysis (TAHAP 2)                              │
│   Input:  TranscriptResult, video_duration, max_clips                │
│   Output: HighlightAnalysisResult {clips, creative_direction, broll} │
├─────────────────────────────────────────────────────────────────────┤
│ Step 5: Prepare Clips (existing — time padding, overlap detection)   │
├─────────────────────────────────────────────────────────────────────┤
│ Step 6: Aspect Ratio Router (existing)                               │
├─────────────────────────────────────────────────────────────────────┤
│ Step 7: Trim Clips (existing — FFmpeg stream copy)                   │
├─────────────────────────────────────────────────────────────────────┤
│ Step 7.5: V2 Micro-Slicing (TAHAP 3) — audio extraction             │
│   Input:  video_path, highlights                                     │
│   Output: list[AudioSlice]                                           │
├─────────────────────────────────────────────────────────────────────┤
│ Step 8: YOLO Reframe (existing — conditional on 9:16)                │
├─────────────────────────────────────────────────────────────────────┤
│ Step 9: V2 Selective Whisper (TAHAP 4) — word-level per clip         │
│   Input:  AudioSlice per clip                                        │
│   Output: list[Word] per clip (absolute timestamps)                  │
├─────────────────────────────────────────────────────────────────────┤
│ Step 9.5: V2 Silero VAD (TAHAP 5) — refine cut boundaries           │
│   Input:  audio_path, target_start, target_end                       │
│   Output: final_start, final_end (refined)                           │
├─────────────────────────────────────────────────────────────────────┤
│ Step 10: Highlight Words (use Groq result instead of Gemini)         │
├─────────────────────────────────────────────────────────────────────┤
│ Step 11+: B-Roll, Hook, Subtitle, Encode, Upload, Assemble (reuse)  │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Model Mapping (V2 → Existing Entities)

| V2 Output | Maps To | Used By |
|-----------|---------|---------|
| `HighlightAnalysisResult.clips` | `list[Clip]` | Trim, YOLO, Subtitle |
| `HighlightAnalysisResult.creative_direction` | `CreativeDirection` | Hook, B-Roll, Remotion |
| `HighlightAnalysisResult.broll_suggestions` | `list[BRollSuggestion]` | B-Roll Injection |
| `SelectiveWhisper.words` | `list[Word]` per clip | Subtitle Rendering |
| `SileroVAD.final_start/end` | Updates `Clip.start/end` | Trim Clips |

---

## 4. API Contract

### 4.1 No API Changes Required

V2 routing is transparent. The existing `POST /api/jobs` endpoint remains identical:

```json
// Request (unchanged)
POST /api/jobs
{
  "youtube_url": "https://youtube.com/watch?v=xxx",
  "style_preset": "bold_black",
  "target_aspect_ratio": "9:16",
  "hook_engine": "v3",
  "broll_enabled": true
}

// Response (unchanged)
{
  "job_id": "job_abc123",
  "youtube_url": "...",
  "status": "validating",
  "pipeline_version": "v2"   // ← NEW: optional field for transparency
}
```

### 4.2 New Optional Response Field

Add `pipeline_version` to `JobResponse` schema:
- `"v1"` — Gemini pipeline (premium)
- `"v2"` — Groq pipeline (non-premium)

### 4.3 New SSE Progress Events

V2 pipeline emits SSE events for new steps:
```
event: step_start
data: {"job_id": "...", "step": 3, "name": "v2_transcript"}

event: step_start
data: {"job_id": "...", "step": 4, "name": "v2_highlight_analysis"}

event: step_start
data: {"job_id": "...", "step": "7.5", "name": "v2_micro_slice"}

event: step_start
data: {"job_id": "...", "step": "9.5", "name": "v2_vad_refine"}
```

---

## 5. Database Changes

### 5.1 Jobs Table — New Column

```sql
ALTER TABLE jobs ADD COLUMN pipeline_version TEXT NOT NULL DEFAULT 'v1';
```

Values: `"v1"` (Gemini) | `"v2"` (Groq)

### 5.2 Feature Registration

Add new feature to `AVAILABLE_FEATURES` in `features.py`:
```python
AVAILABLE_FEATURES = {
    ...existing...,
    "premium_pipeline": "Premium Pipeline (Gemini Video Analysis)",
}
```

### 5.3 No Other Schema Changes

V2 uses same `clips_data` JSON field for storing results. Output entities (`Clip`, `Word`, `BRollSuggestion`, `CreativeDirection`) are shared between V1 and V2.

---

## 6. Configuration

### 6.1 New .env Variables

```env
# ─── Groq API ─────────────────────────────────────────────────────────────────
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GROQ_WHISPER_MODEL=whisper-large-v3-turbo
GROQ_LLM_MODEL=llama-3.1-8b-instant
GROQ_LLM_FALLBACK_MODEL=llama-3.3-70b-versatile
GROQ_MAX_RETRIES=3
GROQ_TIMEOUT=60

# ─── V2 Pipeline Tuning ──────────────────────────────────────────────────────
V2_CHUNK_MAX_SECONDS=600
V2_CHUNK_MAX_CHARS=4000
V2_AUDIO_PADDING_SECONDS=3.0
V2_VAD_SEARCH_RADIUS=2.0
V2_VAD_MIN_SILENCE_MS=300
```

### 6.2 Settings Class Addition

```python
class Settings(BaseSettings):
    ...existing...
    
    # ─── Groq API ─────────────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_WHISPER_MODEL: str = "whisper-large-v3-turbo"
    GROQ_LLM_MODEL: str = "llama-3.1-8b-instant"
    GROQ_LLM_FALLBACK_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_MAX_RETRIES: int = 3
    GROQ_TIMEOUT: int = 60
    
    # ─── V2 Pipeline ─────────────────────────────────────────────────
    V2_CHUNK_MAX_SECONDS: int = 600
    V2_CHUNK_MAX_CHARS: int = 4000
    V2_AUDIO_PADDING_SECONDS: float = 3.0
    V2_VAD_SEARCH_RADIUS: float = 2.0
    V2_VAD_MIN_SILENCE_MS: int = 300
```

---

## 7. Error Handling Strategy

### 7.1 Per-Component Fallback Chain

```
TAHAP 1 (Transcript):
  YouTube API → Groq Whisper → FAILED (no transcript possible)

TAHAP 2 (Highlights):
  Groq LLM (8b) → Groq LLM (70b fallback) → Retry 3x → FAILED

TAHAP 3 (Micro-Slice):
  FFmpeg → FAILED per clip (skip clip, continue others)

TAHAP 4 (Selective Whisper):
  Faster-Whisper → Fallback to segment-level timestamps from TAHAP 1

TAHAP 5 (VAD):
  Silero VAD → Fallback to TAHAP 4 timestamps (no refinement)
```

### 7.2 Circuit Breaker for Groq

```python
class GroqCircuitBreaker:
    """Prevent hammering Groq when rate-limited."""
    
    MAX_FAILURES = 5
    RESET_TIMEOUT = 60  # seconds
    
    def __init__(self):
        self._failures = 0
        self._last_failure_time = 0
        self._state = "closed"  # closed | open | half-open
    
    def can_proceed(self) -> bool:
        if self._state == "closed":
            return True
        if self._state == "open":
            if time.time() - self._last_failure_time > self.RESET_TIMEOUT:
                self._state = "half-open"
                return True
            return False
        return True  # half-open: allow one try
    
    def record_failure(self):
        self._failures += 1
        self._last_failure_time = time.time()
        if self._failures >= self.MAX_FAILURES:
            self._state = "open"
    
    def record_success(self):
        self._failures = 0
        self._state = "closed"
```

---

## 8. Performance Optimization

### 8.1 Parallelization Strategy

```
Sequential (must be in order):
  TAHAP 1 → TAHAP 2 → TAHAP 3

Parallel per clip (after TAHAP 3):
  ┌── Clip 1: Whisper → VAD ──┐
  ├── Clip 2: Whisper → VAD ──┤── Merge → Continue pipeline
  ├── Clip 3: Whisper → VAD ──┤
  └── Clip N: Whisper → VAD ──┘
```

**Concurrency limits:**
- Groq API calls: sequential (respect rate limit)
- Faster-Whisper: `MAX_WHISPER_PARALLEL` (from settings, default 1 on M1)
- FFmpeg micro-slice: parallel (I/O bound, safe)

### 8.2 Caching

- YouTube transcript → cache in `transcript_cache` table (existing)
- Groq highlight results → cache in `clips_data` JSON on Job
- Audio slices → temporary, cleanup after pipeline

### 8.3 Memory Management

- Silero VAD model: load once, reuse across clips (singleton)
- Faster-Whisper model: already singleton in existing `WhisperLocal`
- Audio chunks: process one at a time, delete after Groq upload

---

## 9. Testing Strategy

### 9.1 Unit Tests (per component)

| Component | Test Focus |
|-----------|------------|
| `GroqTranscriber` | YouTube API mock, Groq mock, chunking logic |
| `GroqAnalyzer` | Dynamic chunking math, JSON parsing, fallback |
| `MicroSlicer` | Padding calculation, boundary checks |
| `SelectiveWhisper` | Offset mapping, timeout handling |
| `SileroVAD` | Silence detection, fallback behavior |
| `PipelineRouter` | Premium check logic |

### 9.2 Integration Tests

| Scenario | Description |
|----------|-------------|
| Happy path (YT transcript) | Video with captions → full pipeline |
| Fallback path (Groq Whisper) | Video without captions → Groq transcription |
| Short video (<5 min) | Single chunk, minimal processing |
| Long video (>60 min) | Multi-chunk, many clips |
| Rate limit handling | Groq 429 → circuit breaker → retry |
| Partial failure | Some clips fail Whisper → skip gracefully |

### 9.3 API Tests

| Endpoint | Test |
|----------|------|
| `POST /api/jobs` | Non-premium user → V2 pipeline triggered |
| `POST /api/jobs` | Premium user → V1 pipeline triggered |
| `GET /api/jobs/{id}` | Returns `pipeline_version` field |

---

## 10. Deployment Considerations

### 10.1 Feature Flag

V2 pipeline can be disabled entirely via environment:
```env
V2_PIPELINE_ENABLED=true   # Set to false to force all users to V1
```

### 10.2 Gradual Rollout

1. Deploy with V2 disabled
2. Enable for test users (grant `premium_pipeline` to everyone initially)
3. Remove `premium_pipeline` from non-paying users → they get V2
4. Monitor error rates and performance

### 10.3 Monitoring

New log events:
```
v2_pipeline_start: {job_id, user_id, video_duration}
v2_transcript_source: {job_id, source: "youtube_api"|"groq_whisper"}
v2_highlight_chunks: {job_id, chunk_count, total_duration}
v2_clips_found: {job_id, clip_count, avg_score}
v2_vad_refinement: {job_id, clip_rank, shift_start_ms, shift_end_ms}
v2_pipeline_complete: {job_id, total_duration_s, clips_success}
```
