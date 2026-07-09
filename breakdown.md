jelaskan alur mulai dari select user bicara sampai potong.
grid, yolo, mediapipeline dan lain jelaskan secara jelas dan lengkap.

Kiro
Alur Lengkap: Dari Deteksi Orang Sampai Video Terpotong
Overview Pipeline

Input: Video 16:9 (1920x1080) podcast 2 orang
Output: Video 9:16 (1080x1920) fokus ke pembicara

Step 1: Face Detection (MediaPipe) → posisi wajah per detik
Step 2: Person Tracking (IoU) → ID konsisten per orang
Step 3: Speaker Detection (Face Mesh + Head Motion + VAD) → siapa bicara
Step 4: Dynamic Panning (FFmpeg) → crop mengikuti pembicara
Step 1: Face Detection — MediaPipe Face Detection
Tujuan: Cari dimana wajah berada di setiap frame.

Model: mp.solutions.face_detection.FaceDetection(model_selection=1)

model_selection=1 = optimized untuk jarak 2-5 meter (podcast distance)
Confidence threshold: 0.55
Cara kerja:


Video 1920x1080 (140 detik, 30fps)
  │
  ▼
Sample tiap 1 detik (max 60 frame)
  │
  ▼
Per frame:
  1. Convert BGR → RGB
  2. Downscale ke max 1280px width (speed)
  3. MediaPipe detect → list of face bounding boxes
  4. Filter ukuran: buang face < 5% width atau > 50% width
  5. NMS Filter: buang face yang berdekatan < 10% width (same person detected 2x)
  │
  ▼
Output: per_frame_faces = [[cx1, cx2], [cx1], [cx1, cx2], ...]
        (center X position per wajah per frame)
Contoh output:


Frame 0:  [920]          → 1 wajah di x=920
Frame 30: [920]          → 1 wajah di x=920
Frame 60: [520, 1480]    → 2 wajah (wide shot!)
Frame 90: [1480]         → 1 wajah di x=1480
Step 2: Person Tracking — SimpleIoUTracker
Tujuan: Beri ID tetap ke setiap orang. Tanpa ini, "orang kiri" bisa berubah jadi "orang kanan" kalau posisi bergeser.

Cara kerja:


Frame N: detect face bbox A(100,200,300,400)
Frame N+1: detect face bbox B(110,205,310,405)

IoU(A, B) = 0.85 → sama orang! Track ID = 0

Frame N+2: detect face bbox C(1200,200,1400,400)
IoU(A, C) = 0.0 → orang baru! Track ID = 1
Algoritma matching:

python

# Per frame:
1. Hitung IoU matrix (detections × existing tracks)
2. Greedy match: highest IoU first
3. IoU > 0.20 → same person (update track)
4. No match by IoU → try center distance (< 25% frame width)
5. Still no match → create new track (ID baru)
6. Track not seen 8 frames → remove (orang pergi)
Output:

python

stable_positions = {
    Track_0: 520.0,    # orang kiri, median X across all frames
    Track_1: 1480.0,   # orang kanan
}
person_count = 2
Step 3: Speaker Detection — Multimodal (Face Mesh + Head Motion + VAD)
Tujuan: Tentukan siapa yang sedang bicara di setiap waktu.

3 komponen scoring:

A. Lip Aperture (40% weight)

MediaPipe Face Mesh → 468 landmarks per wajah

Landmark 13 = upper lip center (inner)
Landmark 14 = lower lip center (inner)
Landmark 78 = right mouth corner
Landmark 308 = left mouth corner

lip_aperture = |landmark[14].y - landmark[13].y| / |landmark[308].x - landmark[78].x|

Mulut terbuka (bicara): 0.2 - 0.5
Mulut tertutup (diam): 0.01 - 0.05
B. Head Motion (60% weight)

Landmark 1 = nose tip (hidung)

Per frame: track posisi hidung (x, y) per orang
head_motion = euclidean_distance(nose_now, nose_prev) / 20px

Orang bicara: kepala gerak-gerak kecil (mengangguk, dll) → score 0.1-0.5
Orang diam: kepala stabil → score 0.0-0.05
C. VAD Gate (Audio Check)

Silero VAD → detect kapan ada suara manusia di audio

Kalau di detik T TIDAK ada suara → score SEMUA orang = 0
  → Tidak ada yang dianggap bicara
  → Camera HOLD (tidak pindah)

Kalau ada suara → proses lip + head scoring normal
Scoring per frame:
python

# Per frame, per wajah:
score = lip_variance * 0.40 + head_motion_mean * 0.60

# Wajah dengan score TERTINGGI = active speaker
# Score < 0.002 → no one speaking (silence)
Hysteresis (Anti-flicker):

Tidak boleh switch speaker sebelum speaker baru hold 0.3 detik.
Mencegah:
  Frame 1: Speaker A
  Frame 2: Speaker B (noise)
  Frame 3: Speaker A
  → Tanpa hysteresis: camera snap 3x dalam 0.6 detik (pusing)
  → Dengan hysteresis: camera HOLD di A (ignore frame 2 noise)
Output:

python

ActiveSpeakerResult(
    dominant_speaker_id = 0,      # orang kiri bicara paling banyak
    dominant_ratio = 0.70,         # 70% dari waktu
    per_frame_speaker = {          # siapa bicara di frame mana
        0: 0, 30: 0, 60: 1, 90: 0, 120: 0, ...
    },
    segments = [
        SpeakerSegment(speaker_id=0, start=0.0, end=31.0),
        SpeakerSegment(speaker_id=1, start=31.0, end=36.0),
        SpeakerSegment(speaker_id=0, start=36.0, end=60.0),
    ]
)
Step 4: Dynamic Panning — FFmpeg Single Pass
Tujuan: Potong frame 16:9 menjadi 9:16 yang mengikuti pembicara aktif.

A. Build Keyframes
python

# Per detik: tentukan target crop_x berdasarkan siapa bicara
for each second:
    if speaker_result says speaker_0 is active:
        target face = stable_positions[speaker_0]  # misal x=520
    else:
        target face = stable_positions[speaker_1]  # misal x=1480

    crop_x = face_cx - crop_width/2  # center face di tengah crop
    crop_x = clamp(0, max_x)         # jangan keluar frame

    keyframes.append((time, crop_x))
B. Stabilize (Dead Zone + Hold Min + Cluster Lock)
python

# Cluster Lock: kalau semua gerakan < 200px spread → lock diam
if max(all_x) - min(all_x) < 200:
    return [(0.0, median)]  # 1 posisi, camera DIAM

# Dead Zone + Hold Min:
for each keyframe:
    if movement < 250px → IGNORE (micro-jitter)
    if time_since_last_pan < 5.0s → IGNORE (terlalu cepat)
    else → ADD keyframe (camera boleh pindah)
Contoh transformasi:


145 raw keyframes (1 per detik)
  → Cluster lock? spread=944px > 200 → NO
  → Apply dead zone + hold min
  → 5 stabilized keyframes

[0]  t=0.0s   → x=637  (hold 105 detik)
[1]  t=105.5s → x=238  (snap ke orang kiri)
[2]  t=111.3s → x=1178 (snap ke orang kanan)
[3]  t=121.0s → x=648  (kembali center)
[4]  t=139.3s → x=579  (akhir)
C. Build FFmpeg Expression (Instant Cut)
python

# Nested if: hold X sampai time T, lalu snap ke X berikutnya
expr = "if(lt(t,105.50),637,if(lt(t,111.30),238,if(lt(t,121.00),1178,if(lt(t,139.30),648,579))))"
D. Render (Single FFmpeg Command)
bash

ffmpeg -y -i input.mp4 \
  -vf "crop=607:1080:'if(lt(t,105.50),637,...789)':0,scale=1080:1920,format=yuv420p,setsar=1" \
  -c:v h264_nvenc -preset p4 -cq 22 \
  -c:a copy \                    ← AUDIO TIDAK DIPROSES = ZERO DESYNC
  -movflags +faststart \
  output.mp4
Kenapa zero desync:

1 command FFmpeg, tidak ada trim, tidak ada concat
Audio stream-copied mentah (-c:a copy)
Hanya video yang di-crop (posisi berubah per frame berdasarkan expression t)
Video dan audio tetap aligned karena tidak ada pemrosesan terpisah
Flow Diagram Lengkap

┌─────────────────────────────────────────────────────────────────────────┐
│ INPUT: podcast.mp4 (1920x1080, 16:9)                                    │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 1: MediaPipe Face Detection                                         │
│ • Sample 1fps (60 frames untuk video 60 detik)                           │
│ • Detect face bounding box (xmin, ymin, width, height)                   │
│ • NMS filter: buang duplicate < 10% width                                │
│ Output: per_frame_faces = [[cx], [cx, cx], [cx], ...]                    │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 2: IoU Person Tracker                                               │
│ • Match bbox antar frame via IoU > 0.20                                  │
│ • Assign persistent Track ID (0, 1, 2...)                                │
│ • Track lost > 8 frames → remove                                         │
│ Output: stable_positions = {T0: 520px, T1: 1480px}                       │
│         person_count = 2                                                 │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 3: Multimodal Speaker Detection                                     │
│                                                                          │
│ ┌──────────────────────────────────────────────────────────────────┐    │
│ │ A. Face Mesh (468 landmarks) → lip aperture per face             │    │
│ │ B. Nose tracking → head motion per face                          │    │
│ │ C. Silero VAD → is audio active at time T?                       │    │
│ │                                                                    │    │
│ │ Score = lip_variance × 0.40 + head_mean × 0.60                   │    │
│ │ VAD gate: if no audio → score = 0 for ALL faces                  │    │
│ │ Hysteresis: hold 0.3s before switch                               │    │
│ └──────────────────────────────────────────────────────────────────┘    │
│ Output: per_frame_speaker = {frame: speaker_id, ...}                     │
│         dominant_speaker_id = 0, dominant_ratio = 70%                    │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 4: Dynamic Panning                                                  │
│                                                                          │
│ ┌──────────────────────────────────────────────────────────────────┐    │
│ │ A. Build raw keyframes: (time, crop_x) per second                │    │
│ │    → crop_x = active_speaker_cx - crop_w/2                       │    │
│ │                                                                    │    │
│ │ B. Stabilize:                                                      │    │
│ │    • Cluster lock: spread < 200px → LOCK (camera diam)           │    │
│ │    • Dead zone: ignore movement < 250px                           │    │
│ │    • Hold min: wait 5s between pans                               │    │
│ │    • Result: 145 raw → 4-6 keyframes                             │    │
│ │                                                                    │    │
│ │ C. Build FFmpeg expression:                                        │    │
│ │    'if(lt(t,31.00),574,if(lt(t,36.00),1024,558))'               │    │
│ │                                                                    │    │
│ │ D. Render single pass:                                             │    │
│ │    crop(607:1080:expr:0) → scale(1080:1920) → encode             │    │
│ │    Audio: -c:a copy (ZERO DESYNC)                                 │    │
│ └──────────────────────────────────────────────────────────────────┘    │
│ Output: video 9:16 (1080x1920) dengan camera tracking pembicara         │
└─────────────────────────────────────────────────────────────────────────┘
Yang TIDAK Digunakan (Clarification)
Tech	Status	Kenapa
YOLO (ultralytics)	❌ Tidak dipakai di podcast engine	Hanya di SmartCameraEngine (non-podcast path). Podcast pakai MediaPipe karena lebih ringan dan accurate untuk face
Grid split (50/50, 60/40)	❌ Disabled	Menyebabkan audio desync (FFmpeg concat). Diganti dengan dynamic panning
Pyannote Speaker Diarization	❌ Tidak dipakai	Unreliable, crash 2x, audio-only (tidak bisa map ke wajah). Diganti lip+head multimodal
OpenPose / Skeleton	❌ Tidak ada	Overkill untuk podcast. Head motion dari nose tip sudah cukup
Dynamic segment switching	❌ Reverted	FFmpeg trim+concat = audio desync. Single pass panning menggantikan ini
File Mapping
File	Fungsi
podcast_reframe_engine.py	Orchestrator: pipeline, panning, render
active_speaker_detector.py	Face Mesh lip + head motion + VAD scoring
person_tracker.py	IoU-based persistent face ID tracking
smart_subtitle_positioner.py	Subtitle Y position (grid-aware)
gpu_encoder.py	Auto-detect NVENC / fallback libx264
silero_vad.py	Voice Activity Detection untuk VAD gate
Elapsed time: 1m 41s