# Requirements Document — API Backend V2 (Non-Premium Pipeline)

## 1. Overview

### 1.1 Problem Statement
Pipeline V1 menggunakan Gemini API yang memerlukan video understanding (mahal, butuh API key premium). User non-premium membutuhkan alternatif pipeline yang cost-effective tanpa mengorbankan kualitas output secara signifikan.

### 1.2 Solution
Membangun pipeline V2 yang menggunakan:
- **YouTube Transcript API** (gratis) sebagai sumber transkrip utama
- **Groq Whisper API** (fallback, sangat cepat) untuk video tanpa transkrip
- **Groq LLM** (llama-3.1-8b-instant) untuk highlight analysis berbasis teks
- **Faster-Whisper** (lokal) hanya pada clip pendek untuk word-level timestamps
- **Silero VAD** untuk natural cut refinement

### 1.3 Scope
- Backend Python pipeline baru (parallel dengan V1, bukan replace)
- Routing otomatis berdasarkan status premium user
- Kompatibel 100% dengan rendering pipeline existing (YOLO, subtitle, hook, B-Roll, Remotion)
- Output format identik dengan V1 (Clip, Word, BRollSuggestion, CreativeDirection)

---

## 2. Functional Requirements

### FR-01: Premium Status Check
- **Deskripsi**: Sistem harus cek apakah user memiliki feature "premium_pipeline" (atau setara)
- **Logika**:
  - Jika user memiliki feature `premium_pipeline` ATAU role `superadmin` → gunakan V1 (Gemini)
  - Jika tidak → otomatis gunakan V2 (Groq-based)
- **Acceptance Criteria**:
  - [x] User premium mendapat V1 pipeline
  - [x] User non-premium mendapat V2 pipeline
  - [x] Superadmin selalu mendapat V1
  - [x] Routing transparan (user tidak perlu pilih manual)

### FR-02: Ingestion & Text Extraction (TAHAP 1)
- **Deskripsi**: Mengambil transkrip dari YouTube video
- **Primary Path**: YouTube Transcript API (via `youtube-transcript-api` package)
  - Prioritas bahasa: ID → EN → auto-generated → any
  - Output: list of `{text, start, duration}`
- **Fallback Path**: Groq Whisper API (jika YouTube transcript tidak tersedia)
  - Download audio only via `yt-dlp` (format mp3/m4a, bukan video)
  - Split audio menjadi chunks ≤10 menit (FFmpeg/pydub) karena Groq max 25MB
  - Kirim chunks ke Groq Whisper API (`whisper-large-v3-turbo`)
  - Gabungkan hasil → `transcript_raw.json`
- **Acceptance Criteria**:
  - [x] Berhasil fetch transcript untuk video dengan captions
  - [x] Fallback ke Groq Whisper jika YouTube transcript kosong/error
  - [x] Audio splitting benar (tidak potong di tengah kata)
  - [x] Timeout handling (max 120s total untuk transcription)
  - [x] Output format konsisten: `{segments: [{text, start, end}]}`

### FR-03: AI Highlight Analysis (TAHAP 2)
- **Deskripsi**: Identifikasi momen viral dari transcript menggunakan Groq LLM
- **Dynamic Chunking Rules**:
  - 1 Chunk = max 10 menit (600 detik) ATAU max 4000 karakter (mana yang duluan)
  - Video <10 menit → 1 chunk (no splitting)
  - Video 30 menit → ~3 chunks
  - Video 80 menit → ~8 chunks
- **LLM Call**:
  - Model: `llama-3.1-8b-instant` (default) atau `llama-3.3-70b-versatile` (high quality)
  - Prompt: Structured JSON output → clip candidates dengan timestamps + scoring
  - Temperature: 0.3 (low creativity, high consistency)
- **Output**: `highlights.json` format:
  ```json
  [
    {"rank": 1, "start": 1250.0, "end": 1285.0, "score": 85, "hook": "...", "reason": "...", "content_type": "storytelling"},
    ...
  ]
  ```
- **Acceptance Criteria**:
  - [x] Dynamic chunking sesuai rules
  - [x] JSON output valid dan parseable
  - [x] Timestamps dalam range video duration
  - [x] Minimal 2 clips, maksimal sesuai duration formula
  - [x] Retry logic (max 3 attempts) jika Groq gagal
  - [x] Creative direction juga di-generate (colors, mood, style)

### FR-04: Micro-Slicing (TAHAP 3)
- **Deskripsi**: Potong audio berdasarkan highlight timestamps
- **Process**:
  - Loop through highlights
  - Tambah padding ±3 detik di awal/akhir
  - FFmpeg extract audio segment → `clip_N.wav` (16kHz mono)
- **Acceptance Criteria**:
  - [x] Output WAV 16kHz mono (optimal untuk Whisper)
  - [x] Padding ±3s benar
  - [x] Tidak melebihi batas video duration
  - [x] File cleanup setelah processing

### FR-05: Selective Word-Level Transcription (TAHAP 4)
- **Deskripsi**: Run Faster-Whisper HANYA pada clip audio pendek
- **Process**:
  - Load faster-whisper model (medium, cpu, float32)
  - Transcribe clip_N.wav dengan `word_timestamps=True`
  - Map word timestamps relative to original video
- **Output**: Word-level JSON per clip
  ```json
  [{"word": "Halo", "start": 1250.0, "end": 1250.5}, ...]
  ```
- **Acceptance Criteria**:
  - [x] Word-level timestamps presisi (±100ms)
  - [x] Timestamps di-offset ke posisi absolute dalam video
  - [x] Timeout per clip: max 300s
  - [x] Fallback: jika Whisper gagal, gunakan segment-level dari Tahap 1

### FR-06: Voice Activity Detection (TAHAP 5)
- **Deskripsi**: Refine cut points menggunakan Silero VAD
- **Process**:
  - Load Silero VAD model
  - Detect speech/silence boundaries di sekitar timestamp start/end
  - Geser cut point ke silence terdekat (+0.1s padding)
- **Acceptance Criteria**:
  - [x] Tidak memotong kata di tengah
  - [x] Final timestamp di titik hening (silence gap)
  - [x] Jika tidak ada silence gap dalam ±2s, gunakan original timestamp
  - [x] Output: `{final_start, final_end}` per clip

### FR-07: Pipeline Output Compatibility
- **Deskripsi**: Output V2 harus kompatibel dengan pipeline lanjutan
- **Output yang harus dihasilkan**:
  - `clips: list[Clip]` — dengan start, end, hook, score, rank
  - `words: list[Word]` per clip — word-level timestamps
  - `creative_direction: CreativeDirection` — warna, mood, style
  - `broll_suggestions: list[BRollSuggestion]` per clip
- **Downstream compatibility**:
  - Step 7 (Trim Clips) ✓
  - Step 8 (YOLO Reframe) ✓
  - Step 10 (Highlights marking) — SKIP (sudah dari Groq)
  - Step 11 (B-Roll Injection) ✓
  - Step 12 (Hook Rendering) ✓
  - Step 13 (Subtitle Rendering) ✓
  - Remotion rendering ✓

### FR-08: Error Handling & Graceful Degradation
- **Scenarios**:
  - YouTube Transcript gagal → Fallback ke Groq Whisper
  - Groq Whisper gagal → Job FAILED dengan pesan jelas
  - Groq LLM gagal → Retry 3x, lalu FAILED
  - Faster-Whisper gagal per clip → Skip clip, log warning
  - Silero VAD gagal → Gunakan timestamp Whisper tanpa refinement
- **Acceptance Criteria**:
  - [x] Setiap step failure tidak crash seluruh pipeline
  - [x] Error message informatif untuk user
  - [x] Partial results masih bisa dilanjutkan

---

## 3. Non-Functional Requirements

### NFR-01: Performance
| Metric | Target |
|--------|--------|
| Total pipeline time (5 min video) | < 60 detik |
| Total pipeline time (30 min video) | < 3 menit |
| Total pipeline time (60 min video) | < 5 menit |
| Groq Whisper throughput | ~60 detik per 1 jam audio |
| Groq LLM response | < 5 detik per chunk |
| Faster-Whisper (1 min clip, CPU) | < 15 detik |
| Silero VAD per clip | < 1 detik |

### NFR-02: Cost Efficiency
| Resource | Cost |
|----------|------|
| YouTube Transcript API | FREE |
| Groq Whisper (fallback) | FREE tier: 28,800 audio-seconds/day |
| Groq LLM | FREE tier: 30 RPM, 14,400 tokens/min |
| Faster-Whisper | LOCAL (0 cost, CPU only) |
| Silero VAD | LOCAL (0 cost) |

### NFR-03: Reliability
- Retry mechanism pada semua external API calls
- Circuit breaker pattern jika Groq rate-limited
- Graceful degradation (setiap step punya fallback)

### NFR-04: Scalability
- Semaphore limit untuk concurrent Groq calls
- Queue-based processing untuk multiple jobs
- Stateless design (resumable pipeline)

### NFR-05: Security
- Groq API key stored in .env (tidak hardcoded)
- Input validation pada semua timestamps
- No PII leakage dalam logs

---

## 4. Constraints

### Technical Constraints
- Python 3.11+ (existing stack)
- FastAPI (existing framework)
- SQLite database (existing)
- FFmpeg required (existing dependency)
- macOS M1 development environment (CPU mode untuk Whisper)
- Groq API free tier limits (30 RPM, 25MB file upload)

### Business Constraints
- V2 output quality boleh sedikit di bawah V1 (no video understanding)
- V2 TIDAK boleh mengganggu V1 pipeline (isolated)
- Existing frontend harus tetap work tanpa perubahan
- Job creation API tetap sama (automatic routing di backend)

---

## 5. Dependencies

### External Services
| Service | Purpose | Required |
|---------|---------|----------|
| YouTube Transcript API | Primary transcript source | Yes |
| Groq API (Whisper) | Fallback transcription | Yes (if no YT transcript) |
| Groq API (LLM) | Highlight analysis | Yes |

### Internal Dependencies
| Component | Purpose |
|-----------|---------|
| `IDownloader` (existing) | Download video/audio |
| `IWhisperLocal` (existing) | Word-level transcription |
| `IRenderer` (existing) | FFmpeg trim |
| `IJobRepository` (existing) | Job persistence |
| `IAssetFetcher` (existing) | B-Roll asset resolution |
| Feature access system (existing) | Premium check |

### New Dependencies (pip)
| Package | Version | Purpose |
|---------|---------|---------|
| `groq` | >= 0.9.0 | Groq SDK for Whisper + LLM |
| `silero-vad` | via torch hub | VAD model |
| `pydub` | >= 0.25.0 | Audio splitting (alternative to FFmpeg) |

---

## 6. Out of Scope
- Frontend UI changes (routing is transparent)
- Payment/subscription system
- Groq billing management
- Video quality analysis (V2 is text-only analysis)
- Multi-language simultaneous transcription
- Real-time processing / streaming
