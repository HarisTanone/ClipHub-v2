# B-Roll — Cara Kerja & Efek di Video Final

Dokumen ini menjelaskan end-to-end apa yang terjadi ketika `broll_enabled=true` di job ClipHub V2.

---

## 1. Ringkasan 1 menit

**B-roll di V2 = ganti visual track sebentar, audio tetap utuh.**

Bukan overlay teks di atas video (mode lama). Mode produksi sekarang:

```
[clip asli] → [stock footage 1.5–3s] → [clip asli] → …
              ↑ audio speaker tetap jalan terus
```

- Audio / subtitle / lip-sync **tidak digeser**.
- Durasi clip final = durasi clip input (exact).
- Max **3 splice per clip** (`BROLL_SPLICE_MAX_PER_CLIP`).
- Gap antar B-roll minimal **1 detik** (splicer) / **6 detik** (AI recovery).
- Area hook (0–3 detik) **tidak boleh** kena B-roll.

Kalau asset gagal di-fetch → clip tetap lolos tanpa B-roll (non-fatal).

---

## 2. Toggle & config

| Sumber | Field | Default | Efek |
|--------|-------|---------|------|
| Job create API | `broll_enabled` | `false` (schema request) / DB default `1` | Master switch |
| Job create API | `broll_motion_style` | `null` | Legacy Remotion motion style (saat ini **tidak dipakai** di path splice) |
| Settings user | `broll_enabled` | `1` | Default UI |
| Env | `BROLL_SPLICE_ENABLED` | `true` | Path aktif = **video track replacement** |
| Env | `BROLL_SPLICE_MAX_PER_CLIP` | `3` | Cap splice points |
| Env | `BROLL_SPLICE_CROSSFADE_SEC` | `0.15` | Reserved (hard cut di implementasi saat ini) |
| Env | `ASSET_FETCH_ENABLED` | (settings) | Kalau false → semua asset = fallback text |
| Env | `ASSET_FETCH_TIMEOUT` | (settings) | Timeout per API call |
| Env | `BROLL_MAX_FOOTAGE_SIZE_MB` | `50` | Batas unduhan footage |

**File kunci:**
- Orchestrator: `backend/src/application/services_v2.py` → `_apply_brolls`, `_ensure_broll_suggestions`, `_parse_broll_suggestions`
- AI plan: `backend/src/infrastructure/groq_analyzer.py` → `analyze_broll`, `analyze_broll_for_clips`, `_generate_creative_direction`
- Asset: `backend/src/infrastructure/asset_fetcher.py`
- Process: `backend/src/infrastructure/footage_processor.py`
- Splice: `backend/src/infrastructure/video_splicer.py`
- Entities: `backend/src/domain/entities.py` → `BRollSuggestion`, `SpliceSegment`, `VisualCategory`
- Injector (legacy overlay, **tidak dipakai** di V2 splice path): `backend/src/infrastructure/broll_injector.py`

---

## 3. Posisi di pipeline V2

```
1  Validate
2  Download
3  Transcript
4  Highlight analysis  ← broll_suggestions sering lahir di sini (creative direction)
5  Prepare clips       ← _parse_broll_suggestions → Clip.broll_suggestions
6  Aspect router
7  Trim clips          ← clock dinormalisasi ke 0
8  YOLO / reframe
9  Word-level Whisper
10 Build subtitle words
11 Auto B-roll         ← _ensure_broll_suggestions + _apply_brolls
11.5 Text emphasis     ← blocked ranges = zona B-roll (supaya tidak nabrak)
12+ Remotion           ← input = clip_*_brolled.mp4 jika ada, else reframed/raw
     (hook + subtitle + text emphasis di atas video yang sudah di-splice)
```

Urutan penting:

1. B-roll **sebelum** Remotion.
2. Remotion pakai file `clip_XX_brolled.mp4` sebagai base video.
3. Hook/subtitle/text-emphasis dibakar **di atas** video yang sudah berisi splice.
4. `_build_broll_events()` **sengaja return `[]`** — tidak ada overlay B-roll di Remotion. Preview = final = replacement track.

---

## 4. Data model

### `BRollSuggestion`
```python
@dataclass
class BRollSuggestion:
    at_time: float              # detik dari awal clip (0-based)
    keyword: str                # query stock footage, max ~80 char
    template: str               # legacy: word_pop_typography | line_reveal_typography | particle_text_burst
    duration: float = 2.0       # 1.5–3.0s setelah clamp
    reason: str = ""
    visual_category: VisualCategory = FOOTAGE
    asset_result: Optional[AssetResult] = None
    splice_segment: Optional[SpliceSegment] = None   # diisi AssetFetcher
    motion_style: Optional[BrollMotionStyle] = None  # legacy Remotion path
```

### `SpliceSegment` (siap di-FFmpeg)
```python
@dataclass
class SpliceSegment:
    footage_path: str   # 1080x1920 H.264 30fps video-only
    at_time: float
    duration: float
    keyword: str
    source_id: str
    platform: str       # pexels | pixabay | youtube | …
```

### `VisualCategory`
| Value | Sumber (legacy) | Di mode splice |
|-------|-----------------|----------------|
| `footage` | ClipScout → Pexels/Pixabay | **Utama** — full-frame replace |
| `icon` | Iconify | Di-force ke footage search |
| `motion_graphic` | Lottie lokal | Di-force ke footage search |
| `reaction` | Giphy | Di-force ke footage search |

Saat `BROLL_SPLICE_ENABLED=true`, unresolved suggestion dipaksa `visual_category=footage`. Overlay icon/gif/lottie **tidak** masuk timeline final.

---

## 5. Dari mana suggestion datang?

Ada 3 jalur AI, semua optional & non-fatal:

### A. Creative direction (default Analyze First)
Setelah Pass 2 ranking, `_generate_creative_direction()` minta LLM:
```json
{
  "creative_direction": { "primary_color": "...", "energy_level": "..." },
  "broll_suggestions": {
    "1": [{ "at_time": 5.0, "keyword": "AGING POPULATION", "template": "word_pop_typography", "duration": 2.5, "visual_category": "footage" }],
    "2": [...]
  }
}
```
`at_time` = offset **di dalam clip** (bukan absolute video source).

### B. Recovery (`_ensure_broll_suggestions`)
Kalau clip belum punya suggestion setelah word-level:
- `analyze_broll_for_clips(words_per_clip, durations, max=2)`
- Anchor `at_time` ke timestamp Whisper nyata
- Gap antar B-roll ≥ 6s
- Fallback lokal `_fallback_broll_from_words` kalau router kosong/malformed (1 suggestion dari frasa konkret)

### C. Direct Edit (`analyze_broll`)
Upload + `processing_mode=direct` + `broll_enabled`:
- Sample ≤60 segment transcript
- Max 3 suggestion, anchor ke timestamp segment
- Tidak memotong/memilih clip — full video tetap 1 clip

### Clamp di `_parse_broll_suggestions`
| Rule | Nilai |
|------|-------|
| Max per clip | 3 |
| `at_time` min | 3.0s (hook zone) jika clip > 4s |
| `at_time` max | `clip_duration - 1.0` |
| duration | clamp 1.5–3.0, tidak boleh lewat akhir clip |
| keyword kosong | dibuang |
| template unknown | → `word_pop_typography` |
| motion_style | dari field baru, atau map legacy template |

---

## 6. Asset resolution (`AssetFetcher.fetch_assets`)

```
suggestions[]
    │
    ├─ BROLL_SPLICE_ENABLED?
    │     yes → ClipScout search(segments)
    │              → AI selector (9router CliperHub) pilih 1 video terbaik
    │              → FootageDownloader
    │              → FootageProcessor → 1080x1920 H.264 30fps, trim, -an
    │              → attach SpliceSegment
    │
    ├─ unresolved (no splice_segment & no asset_result)
    │     → force category=footage
    │     → legacy chain: Pexels → Pixabay (cache SHA-256, Semaphore 4, timeout)
    │     → video asset → process → SpliceSegment
    │
    └─ gagal total → AssetResult.fallback() (text)
                     di path splice: **di-skip** (tidak di-overlay)
```

**FootageProcessor output:**
- Scale+center-crop → 1080×1920
- `libx264` preset fast, CRF 20, 30 fps, yuv420p
- **Tanpa audio** (`-an`)
- Nama: `clip_{rank:02d}_broll_footage_{index:02d}.mp4`

---

## 7. Video splice (`VideoSplicer.splice`)

### Kontrak
1. **Audio stream original di-copy** (`-c:a copy`) — tidak re-encode.
2. Durasi output = durasi input (toleransi drift ≤ 0.1s start, ≤ 0.25s end/duration).
3. Subtitle timing aman karena clock audio tidak berubah.
4. Overlap segment (< 1s gap) → **abort, return clip asli**.
5. Max `BROLL_SPLICE_MAX_PER_CLIP` segment.

### Algoritma
```
input: clip_XX_reframed.mp4 (atau clip_XX.mp4)
segments sorted by at_time

untuk tiap segment i:
  extract video-only [prev_end → at_time]   → part_before_i.mp4
  append footage_path (sudah 1080x1920)
  prev_end = at_time + duration

extract video-only [prev_end → clip_end]    → part_after_final.mp4

concat demuxer: [before][footage][between][footage]…[after]
map:
  0:v  = video dari concat
  1:a? = audio dari clip original
-c:v copy  (fallback re-encode libx264 jika codec mismatch)
-c:a copy

validate A/V sync → rename ke clip_XX_brolled.mp4
cleanup temp + broll_footage/
```

### Contoh timeline (clip 30s, 2 B-roll)

```
t=0.0 ──────────────── t=5.0 ── t=7.5 ──────── t=14.0 ── t=16.5 ──────── t=30.0
│     main video      │  BROLL  │  main video  │  BROLL  │   main video   │
│   (speaker on cam)  │ stock A │              │ stock B │                │
└─────────────────────┴─────────┴──────────────┴─────────┴────────────────┘
Audio: ═══════════════════════════════════════════════════════════════════
       (terus, tidak putus, tidak digeser)
```

Penonton **mendengar** speaker bilang "aging population" sambil **melihat** stock footage lansia di kota selama ~2.5s, lalu kembali ke wajah speaker.

---

## 8. Apa yang terjadi di video final (Remotion)

Input Remotion per clip (prioritas):
1. `clip_XX_brolled.mp4` ← **jika splice sukses**
2. `clip_XX_reframed.mp4`
3. `clip_XX.mp4` (raw trim)

Remotion menambahkan **di atas** base itu:
- Hook text (0–~3s)
- Word-by-word subtitles
- Text emphasis events (max 2/clip), **blocked** di range B-roll

`broll_events` yang dikirim ke Remotion = **`[]`** (`_build_broll_events` always empty).
Alasan: B-roll sudah baked ke video track. Overlay ganda akan bikin preview ≠ final.

Output: `clip_XX_final.mp4` → copy ke `final/clip_XX.mp4`.

Metadata di `clips_data`:
```json
{
  "broll_enabled": true,
  "clips": [{
    "rank": 1,
    "broll_applied": true,
    "broll_suggestions": [
      {
        "at_time": 5.0,
        "keyword": "aging population",
        "template": "word_pop_typography",
        "duration": 2.5,
        "visual_category": "footage",
        "asset_source": "pexels"
      }
    ]
  }]
}
```

---

## 9. Layer z-order di final

```
z↑  subtitle words          (Remotion)
    text emphasis           (Remotion, max 2)
    hook text 0–3s          (Remotion)
    ─────────────────────────────────────
    video track:
      main → B-roll stock → main → …   (VideoSplicer, pre-Remotion)
    ─────────────────────────────────────
z↓  audio original          (stream copy, never modified)
```

---

## 10. Restyle path

Endpoint restyle **tidak** re-run ClipScout/splice:
- Kalau `clip_XX_brolled.mp4` sudah ada → dipakai sebagai base.
- Remotion re-render hook/subtitle/text-emphasis di atasnya.
- Overlay path deprecated tidak dihidupkan ulang.

---

## 11. Failure modes (semua non-fatal kecuali noted)

| Kondisi | Perilaku |
|---------|----------|
| `broll_enabled=false` | Step 11 skip total |
| AI 0 suggestion | Log "no relevant suggestions", lanjut |
| ClipScout down | Fallback Pexels/Pixabay |
| Semua asset gagal | Tidak ada `clip_*_brolled.mp4`, Remotion pakai reframed/raw |
| Segment overlap | Splicer abort → clip original |
| A/V drift > toleransi | Hapus output splice, fallback original |
| `BRollInjector` null | Warning, skip (V2 splice tetap jalan via `VideoSplicer`) |
| Remotion down | **Fatal** untuk hook/subtitle (bukan B-roll) |

---

## 12. API terkait

| Method | Path | Fungsi |
|--------|------|--------|
| GET | `/api/broll-templates` | List template (legacy + motion styles) |
| GET | `/api/broll-templates/{id}` | Detail template |
| PATCH | `/api/jobs/{id}/clips/{rank}/broll` | Manual add/override broll row di DB |
| DELETE | `/api/jobs/{id}/clips/{rank}/broll/{broll_id}` | Hapus manual broll |
| GET | `/api/jobs/{id}/clips/{rank}/broll` | List broll per clip |

Template di DB (`broll_templates`) masih di-seed (Word Pop, Ken Burns, dll.) untuk UI/manual. **Pipeline otomatis V2 tidak merender template itu sebagai overlay** — hanya keyword → stock footage splice.

---

## 13. Checklist "apa yang user lihat" saat B-roll ON

1. Progress SSE step `broll` (11) + sub-event `broll_splice`.
2. Di timeline final, beberapa momen visual **cut ke stock footage** 1.5–3 detik.
3. Suara speaker **tetap** di momen itu (seolah voice-over).
4. Subtitle tetap sinkron (karena audio tidak digeser).
5. Hook 3 detik pertama bersih (tanpa B-roll).
6. Text emphasis tidak menimpa zona B-roll.
7. File intermediate: `clip_XX_brolled.mp4` (dihapus dari folder footage temp setelah sukses).
8. Flag `broll_applied: true` di response job detail.

Kalau B-roll OFF: langkah 11 no-op, Remotion langsung dari reframed/raw, tidak ada cut ke stock.

---

## 14. Diagram alur ringkas

```
job.broll_enabled?
        │ no ──► skip
        ▼ yes
AI plan (creative / recovery / direct)
        │
        ▼
_parse_broll_suggestions  (clamp time/dur/keyword)
        │
        ▼
AssetFetcher
  ClipScout → AI pick → download → process 1080x1920
  else Pexels/Pixabay → process
        │
        ▼  SpliceSegment[]
VideoSplicer
  split main video-only parts
  concat with footage
  map original audio copy
  validate duration/sync
        │
        ▼  clip_XX_brolled.mp4
Remotion (hook + subtitle + text emphasis)
        │
        ▼  clip_XX_final.mp4
```

---

## 15. Catatan legacy (jangan bingung)

| Komponen | Status di V2 production |
|----------|-------------------------|
| `BRollInjector` overlay/drawtext | Masih di-DI, **tidak dipanggil** di `_apply_brolls` V2 |
| Remotion `BrollLayer` / `brollEvents` | Payload dikirim kosong |
| `BrollMotionStyle` (ken_burns, dll.) | Parsed & disimpan, **tidak di-render** di path splice |
| Scene graph `L2_broll` | Model konseptual; render aktual = pre-baked splice |
| Manual `job_clip_brolls` table | API ada; path auto pipeline V2 utamanya pakai `Clip.broll_suggestions` in-memory |

Keputusan desain: **satu kontrak timeline** — `Clip → B-roll stock → Clip`. Overlay motion-graphic di-nonaktifkan supaya preview UI = file final.
