# AutoCliper Backend

Python FastAPI backend — pipeline orchestrator for YouTube to short-form video clips.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI + Uvicorn (port 8000) |
| Database | SQLite + aiosqlite (WAL mode) |
| AI Analysis | Gemini 3.5 Flash (multi-key rotation) |
| Transcription | whisper.cpp medium model |
| Video | FFmpeg (trim, reframe, encode) |
| Render Engine | Remotion (via Node.js server on port 3002) |
| Auth | JWT (access + refresh tokens, bcrypt) |
| Download | yt-dlp |

## Architecture

```
src/
├── application/
│   └── services.py        # Pipeline orchestrator (16 steps)
├── domain/
│   ├── entities.py        # Job, Clip, CreativeDirection
│   ├── interfaces.py      # Abstract interfaces
│   └── scene_graph.py     # Structured timeline per clip
├── infrastructure/
│   ├── remotion_adapter.py    # HTTP bridge to Remotion server
│   ├── subtitle_renderer.py   # FFmpeg subtitle fallback
│   ├── yolo_reframe_engine.py # Person detection + crop
│   ├── renderer.py            # FFmpeg hook/broll render
│   ├── db_connection.py       # SQLite connection
│   └── auth.py                # JWT + bcrypt
├── presentation/
│   ├── api.py             # FastAPI app + CORS + lifespan
│   ├── routes/            # All API routes
│   └── auth_deps.py       # Auth dependencies
└── config.py              # Settings from .env
```

## Pipeline Flow

```
URL → Validate → Download → Gemini Analysis → Prepare Clips →
Aspect Router → Trim → YOLO Reframe → Whisper Transcription →
Scene Graph → Remotion Render → Thumbnail → Assemble JSON → Done
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/jobs` | Create job, start pipeline |
| GET | `/api/jobs` | List jobs (paginated) |
| GET | `/api/jobs/{id}/detail` | Full detail + clips |
| GET | `/api/jobs/{id}/clips/{n}/final` | Download final video |
| PATCH | `/api/jobs/{id}/clips/{n}/hook` | Edit hook text |
| POST | `/api/jobs/{id}/clips/{n}/restyle` | Re-render with new style |
| GET | `/api/presets` | List user presets |
| POST | `/api/presets` | Save preset |
| POST | `/api/storage/clear` | Clear processing data |
| GET | `/health` | Health check |

## Quick Start

```bash
# Create venv
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy env
cp .env.example .env
# Edit .env with your API keys

# Create directories
mkdir -p tmp/output tmp/downloads

# Run
python main.py
```

## Environment Variables

See `.env.example` for full list. Key ones:

```env
GEMINI_API_KEY=your_key
USE_REMOTION=true
REMOTION_SERVER_PORT=3002
SUPERADMIN_EMAIL=admin@autocliper.com
SUPERADMIN_PASSWORD=YourSecurePassword
JWT_SECRET_KEY=random-64-char-hex
```

## Output Structure

```
tmp/output/{job_id}/
├── clip_01_reframed.mp4   # After YOLO reframe
├── clip_01_final.mp4      # Final rendered (Remotion)
├── thumbnail/
│   └── clip_01.jpg        # Thumbnail at 1s
└── meta_job_xxx.json      # Job metadata
```

## Logs (Production)

```bash
# Live log backend (streaming, Ctrl+C untuk stop)
sudo journalctl -u autocliper-backend -f

# 50 baris terakhir
sudo journalctl -u autocliper-backend -n 50 --no-pager

# Remotion log
sudo journalctl -u autocliper-remotion -f

# Frontend log
sudo journalctl -u autocliper-frontend -f

# Status semua services
sudo systemctl status autocliper-backend autocliper-remotion autocliper-frontend
```
