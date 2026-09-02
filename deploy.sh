#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# AutoCliper v3 — Full Server Deployment Script
#
# One command to rule them all:
#   ./deploy.sh
#
# Target Server:
#   - Ubuntu 24.04 LTS
#   - i7-13700K (24 threads)
#   - 62GB RAM
#   - 928GB NVMe
#   - Host: Linux Server (Ubuntu 24.04)
#
# What it does:
#   1. Git fetch + pull latest code
#   2. System dependencies (ffmpeg, Node.js 20, Python 3.11+)
#   3. Backend setup (Python venv, pip install)
#   4. Remotion server setup (Node.js, npm install) — hook+subtitle
#   4b. HyperFrames polish server (template+JSON, optional)
#   4c. Hermes config sync (same ops/hermes as local)
#   5. Frontend build (Vite production build)
#   6. Systemd services (9router, backend, remotion, hyperframes, frontend)
#   7. Nginx reverse proxy (optional)
#   8. Health check + DB side-tables
#
# Services & Ports:
#   - 9router LLM gateway          → :20128 (127.0.0.1)
#   - Backend (FastAPI/Uvicorn)    → :8000
#   - Remotion (hook+subtitle)     → :3002
#   - HyperFrames (polish)         → :3003
#   - Frontend (static/serve)      → :3001
#   - Hermes                       → CLI (config under $HERMES_HOME)
#
# Local == production config shape:
#   ops/hermes/config.yaml , ops/env/shared.env.example
#   scripts/sync-hermes-config.sh , pack/restore 9router+hermes
#
# Designed to be idempotent — safe to run multiple times.
# Second run is fast because it skips already-installed components.
# ═══════════════════════════════════════════════════════════════════════════════

set -e
export DEBIAN_FRONTEND=noninteractive

# ─── Configuration ───────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
REMOTION_DIR="$PROJECT_DIR/remotion-renderer"
HYPERFRAMES_DIR="$PROJECT_DIR/hyperframes-renderer"
FRONTEND_DIR="$PROJECT_DIR/frontend"
DEPLOY_USER="${SUDO_USER:-$(whoami)}"
DEPLOY_HOME="$(eval echo "~$DEPLOY_USER" 2>/dev/null || echo "$HOME")"
PYTHON_BIN="python3"

# Ports (avoiding conflicts with existing services)
BACKEND_PORT=8000
REMOTION_PORT=3002
HYPERFRAMES_PORT="${HYPERFRAMES_PORT:-3003}"
FRONTEND_PORT=3001
PUBLIC_HOST="${PUBLIC_HOST:-localhost}"
PUBLIC_FRONTEND_URL="${PUBLIC_FRONTEND_URL:-http://$PUBLIC_HOST:$FRONTEND_PORT}"
PUBLIC_BACKEND_URL="${PUBLIC_BACKEND_URL:-http://$PUBLIC_HOST:$BACKEND_PORT}"
AUTOCLIPER_PUBLIC_URL="${AUTOCLIPER_PUBLIC_URL:-https://jnck.cliperhub.web.id}"
NINE_ROUTER_PORT="${NINE_ROUTER_PORT:-20128}"
NINE_ROUTER_HOST="${NINE_ROUTER_HOST:-127.0.0.1}"
NINE_ROUTER_CLI_VERSION="${NINE_ROUTER_CLI_VERSION:-0.5.20}"
NINE_ROUTER_DEFAULT_BASE_URL="http://$NINE_ROUTER_HOST:$NINE_ROUTER_PORT/v1"
HERMES_HOME_DEPLOY="${HERMES_HOME:-$DEPLOY_HOME/.hermes}"
CLEAR_AI_CACHE_ON_DEPLOY="${CLEAR_AI_CACHE_ON_DEPLOY:-0}"

env_value() {
    local file="$1"
    local key="$2"
    local default_value="${3:-}"
    if [ ! -f "$file" ]; then
        echo "$default_value"
        return
    fi
    local value
    value="$(grep -E "^${key}=" "$file" 2>/dev/null | tail -n 1 | cut -d'=' -f2- | sed -e 's/^\"//' -e 's/\"$//' -e "s/^'//" -e "s/'$//")"
    if [ -z "$value" ]; then
        echo "$default_value"
    else
        echo "$value"
    fi
}

append_env_if_missing() {
    local file="$1"
    local key="$2"
    local value="$3"
    if ! grep -qE "^${key}=" "$file" 2>/dev/null; then
        echo "${key}=${value}" >> "$file"
    fi
}

set_env_value() {
    local file="$1"
    local key="$2"
    local value="$3"
    if grep -qE "^${key}=" "$file" 2>/dev/null; then
        sed -i.bak -E "s|^${key}=.*|${key}=${value}|" "$file"
        rm -f "$file.bak"
    else
        echo "${key}=${value}" >> "$file"
    fi
}

echo "═══════════════════════════════════════════════════════════════"
echo "  AutoCliper v3 — Server Deployment"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  Project:  $PROJECT_DIR"
echo "  User:     $DEPLOY_USER"
echo "  Python:   $($PYTHON_BIN --version 2>/dev/null || echo 'not found')"
echo "  Node:     $(node --version 2>/dev/null || echo 'not found')"
echo "  Public:   $PUBLIC_FRONTEND_URL"
echo ""

# ─── Step 1: Git Pull ───────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 1: Git Pull"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$PROJECT_DIR"
if [ -d ".git" ]; then
    echo "  Fetching latest..."
    git fetch origin 2>/dev/null || true

    if ! git diff --quiet 2>/dev/null; then
        echo "  Stashing local changes..."
        git stash 2>/dev/null || true
    fi

    git pull origin main 2>/dev/null || git pull 2>/dev/null || true
    sudo chown -R $DEPLOY_USER:$DEPLOY_USER "$PROJECT_DIR" 2>/dev/null || true
    echo "  [OK] Code updated"
else
    echo "  [WARN]  No .git found — skipping pull"
fi

# ─── Step 2: System Dependencies ────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 2: System Dependencies"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check if essential tools are already present
MISSING=""
command -v ffmpeg &>/dev/null || MISSING="$MISSING ffmpeg"
command -v node &>/dev/null || MISSING="$MISSING nodejs"
command -v python3 &>/dev/null || MISSING="$MISSING python3"
command -v aria2c &>/dev/null || MISSING="$MISSING aria2"

if [ -z "$MISSING" ]; then
    echo "  [OK] All system dependencies present"
else
    echo "  Installing:$MISSING"
    sudo apt-get update -qq 2>/dev/null || true

    # Python
    if ! command -v python3 &>/dev/null; then
        sudo apt-get install -y python3 python3-pip python3-venv python3-dev 2>/dev/null
    fi

    # FFmpeg
    if ! command -v ffmpeg &>/dev/null; then
        sudo apt-get install -y ffmpeg 2>/dev/null
    fi

    # aria2 (high-speed parallel download engine)
    if ! command -v aria2c &>/dev/null; then
        sudo apt-get install -y aria2 2>/dev/null || true
    fi

    # Node.js 20 (via nodesource)
    if ! command -v node &>/dev/null; then
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - 2>/dev/null
        sudo apt-get install -y nodejs 2>/dev/null
    fi

    # Build tools for native modules
    sudo apt-get install -y build-essential cmake 2>/dev/null || true

    # FFmpeg development libraries (required by PyAV / faster-whisper)
    sudo apt-get install -y \
        libavformat-dev libavcodec-dev libavdevice-dev \
        libavutil-dev libavfilter-dev libswscale-dev \
        libswresample-dev pkg-config 2>/dev/null || true

    # Chromium deps for Remotion headless rendering
    sudo apt-get install -y --no-install-recommends \
        libnss3 libatk-bridge2.0-0t64 libdrm2 libxcomposite1 \
        libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
        libasound2t64 libxshmfence1 2>/dev/null || true

    echo "  [OK] System packages installed"
fi

# Always ensure aria2 is installed
if ! command -v aria2c &>/dev/null; then
    echo "  Installing aria2..."
    sudo apt-get install -y aria2 2>/dev/null || true
fi

# Always ensure FFmpeg dev libs + build tools are present (needed by PyAV/faster-whisper)
# This runs even if ffmpeg binary already exists, because dev headers may be missing
if ! pkg-config --exists libavformat 2>/dev/null; then
    echo "  Installing FFmpeg dev libraries (required for PyAV build)..."
    sudo apt-get update -qq 2>/dev/null || true
    sudo apt-get install -y \
        build-essential cmake pkg-config \
        libavformat-dev libavcodec-dev libavdevice-dev \
        libavutil-dev libavfilter-dev libswscale-dev \
        libswresample-dev 2>/dev/null || true
    echo "  [OK] FFmpeg dev libraries installed"
fi

echo "  Python: $($PYTHON_BIN --version 2>/dev/null)"
echo "  Node:   $(node --version 2>/dev/null)"
echo "  FFmpeg: $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3)"
echo "  aria2c: $(aria2c --version 2>/dev/null | head -1 | cut -d' ' -f3 || echo 'not found')"

# ─── Step 2.5: 9router CLI ──────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 2.5: 9router CLI"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if command -v 9router &>/dev/null; then
    echo "  [OK] 9router CLI found: $(command -v 9router)"
else
    echo "  Installing 9router@$NINE_ROUTER_CLI_VERSION..."
    npm install -g "9router@$NINE_ROUTER_CLI_VERSION" --prefer-online 2>/dev/null || \
        sudo npm install -g "9router@$NINE_ROUTER_CLI_VERSION" --prefer-online
    echo "  [OK] 9router CLI installed"
fi

# ─── Step 2.6: System Font Provisioning ──────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 2.6: Fontconfig & Custom Typography"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

sudo apt-get install -y fontconfig fonts-dejavu-core 2>/dev/null || true
if [ -d "$BACKEND_DIR/assets/fonts" ]; then
    echo "  Installing custom typography into font directory..."
    USER_FONT_DIR="$HOME/.local/share/fonts/autocliper"
    if [ "$(uname -s)" = "Darwin" ]; then
        USER_FONT_DIR="$HOME/Library/Fonts"
    fi
    mkdir -p "$USER_FONT_DIR" 2>/dev/null || true
    cp -f "$BACKEND_DIR"/assets/fonts/*.ttf "$USER_FONT_DIR"/ 2>/dev/null || true
    if [ "$(uname -s)" != "Darwin" ]; then
        sudo mkdir -p /usr/local/share/fonts/autocliper 2>/dev/null || true
        sudo cp -f "$BACKEND_DIR"/assets/fonts/*.ttf /usr/local/share/fonts/autocliper/ 2>/dev/null || true
    fi
    fc-cache -f "$USER_FONT_DIR" 2>/dev/null || fc-cache -f 2>/dev/null || true
    echo "  [OK] Custom fonts cached ($(ls "$BACKEND_DIR/assets/fonts"/*.ttf 2>/dev/null | wc -l | tr -d ' ') fonts)"
fi

# ─── Step 2.8: Cloudflare Tunnel (cloudflared) ──────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 2.8: Cloudflare Tunnel (Repliz Media & Public Gateway)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if command -v cloudflared &>/dev/null; then
    echo "  [OK] cloudflared found: $(command -v cloudflared) ($(cloudflared --version 2>/dev/null | head -1 | cut -d' ' -f1-3))"
else
    echo "  Installing cloudflared binary/package..."
    ARCH="$(uname -m)"
    if [ "$ARCH" = "x86_64" ]; then
        CLOUDFLARED_PKG="cloudflared-linux-amd64.deb"
    elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
        CLOUDFLARED_PKG="cloudflared-linux-arm64.deb"
    else
        CLOUDFLARED_PKG="cloudflared-linux-amd64.deb"
    fi

    if command -v apt-get &>/dev/null; then
        curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/${CLOUDFLARED_PKG}" -o "/tmp/${CLOUDFLARED_PKG}" 2>/dev/null || true
        if [ -f "/tmp/${CLOUDFLARED_PKG}" ]; then
            sudo dpkg -i "/tmp/${CLOUDFLARED_PKG}" 2>/dev/null || true
            rm -f "/tmp/${CLOUDFLARED_PKG}"
        fi
    elif command -v brew &>/dev/null; then
        brew install cloudflared 2>/dev/null || true
    fi

    if command -v cloudflared &>/dev/null; then
        echo "  [OK] cloudflared installed: $(cloudflared --version 2>/dev/null | head -1)"
    else
        echo "  [INFO] cloudflared auto-download skipped (install manually if tunnel service is desired)"
    fi
fi

# ─── Step 3: Backend Setup ──────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 3: Backend (FastAPI — port $BACKEND_PORT)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$BACKEND_DIR"

# Create venv if missing
if [ ! -d "venv" ]; then
    echo "  Creating virtual environment..."
    $PYTHON_BIN -m venv venv
fi

# Install/update dependencies
echo "  Syncing Python dependencies..."
./venv/bin/pip install --upgrade pip setuptools wheel -q 2>/dev/null
# Pre-install packages with known source-build failures on Python 3.12
# These MUST be installed as binary wheels before requirements.txt runs
./venv/bin/pip install --only-binary=:all: \
    "numpy>=1.26.0,<2.0" \
    "pyyaml>=6.0.1" \
    "tokenizers>=0.19.0" \
    "Cython>=3.0" \
    -q 2>/dev/null || true
./venv/bin/pip install -r requirements.txt -q 2>/dev/null || \
    ./venv/bin/pip install -r requirements.txt

echo "  Validating backend imports and syntax..."
./venv/bin/python -m compileall -q src
./venv/bin/python -c "from src.presentation.api import app; assert app.routes"
echo "  [OK] Backend validation passed"

# Keep the server-side pre-deployment test gate ready. Test dependencies are
# isolated from runtime requirements but installed into the backend venv that
# test.sh and the systemd backend service consistently use.
if [ -f "requirements-dev.txt" ]; then
    echo "  Installing backend test dependencies..."
    ./venv/bin/pip install -r requirements-dev.txt -q
    echo "  [OK] Backend test dependencies ready"
fi

# GPU: Install PyTorch with CUDA 12.1 (compatible with NVIDIA driver 535+)
# This enables GPU acceleration for: Faster-Whisper, YOLO, torchaudio
if command -v nvidia-smi &>/dev/null; then
    echo "  Installing PyTorch with CUDA 12.1 (GPU detected)..."
    ./venv/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121 -q 2>/dev/null || \
        ./venv/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
    echo "  [OK] PyTorch CUDA 12.1 installed"
else
    echo "  [INFO]  No GPU detected — using CPU-only PyTorch"
fi

# Create .env from production template if not exists
if [ ! -f ".env" ]; then
    if [ -f ".env.production" ]; then
        echo "  Copying .env.production → .env"
        cp .env.production .env
    elif [ -f ".env.example" ]; then
        echo "  [WARN]  No .env found — copying from .env.example"
        echo "  [WARN]  EDIT .env WITH YOUR ACTUAL CREDENTIALS"
        cp .env.example .env
    fi
fi

if [ -f ".env" ]; then
    append_env_if_missing ".env" "AUTOCLIPER_PUBLIC_URL" "$AUTOCLIPER_PUBLIC_URL"
    append_env_if_missing ".env" "CORS_ORIGINS" "$PUBLIC_FRONTEND_URL,http://$PUBLIC_HOST:3000,$AUTOCLIPER_PUBLIC_URL,https://cliperhub-tunnel.trycloudflare.com,https://jnck.cliperhub.web.id"

    # Auto-generate cryptographically secure JWT keys if default or missing
    CURRENT_JWT="$(env_value ".env" "JWT_SECRET_KEY" "")"
    if [ -z "$CURRENT_JWT" ] || [ "$CURRENT_JWT" = "change-me-in-production" ]; then
        RANDOM_JWT="$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))')"
        set_env_value ".env" "JWT_SECRET_KEY" "$RANDOM_JWT"
        echo "  [SEC] Generated secure random JWT_SECRET_KEY"
    fi
    CURRENT_JWT_REFRESH="$(env_value ".env" "JWT_REFRESH_SECRET_KEY" "")"
    if [ -z "$CURRENT_JWT_REFRESH" ] || [ "$CURRENT_JWT_REFRESH" = "change-me-in-production-refresh" ]; then
        RANDOM_JWT_REFRESH="$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))')"
        set_env_value ".env" "JWT_REFRESH_SECRET_KEY" "$RANDOM_JWT_REFRESH"
        echo "  [SEC] Generated secure random JWT_REFRESH_SECRET_KEY"
    fi
fi

# Create directories
mkdir -p data data/asset_cache tmp/output tmp/downloads tmp/video_gen models

# Ensure yt-dlp & pytubefix are up-to-date (critical for YouTube cipher extraction & 1080p stream resolution)
echo "  Ensuring latest yt-dlp & pytubefix..."
./venv/bin/pip install --upgrade yt-dlp pytubefix -q 2>/dev/null || true
echo "  yt-dlp: $(./venv/bin/python -c 'import yt_dlp; print(yt_dlp.version.__version__)' 2>/dev/null || yt-dlp --version 2>/dev/null || echo 'not found')"

# Set permissions on cookies.txt if present
if [ -f "$PROJECT_DIR/cookies.txt" ]; then
    chmod 644 "$PROJECT_DIR/cookies.txt" 2>/dev/null || true
fi
if [ -f "$BACKEND_DIR/cookies.txt" ]; then
    chmod 644 "$BACKEND_DIR/cookies.txt" 2>/dev/null || true
fi

echo "  [OK] Backend ready"

# ─── Step 3.1: Database Migrations ──────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 3.1: Database Migrations"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$BACKEND_DIR"

# Run all migrations in order (each is idempotent — safe to run multiple times)
MIGRATION_DIR="$BACKEND_DIR/database/migrations"
if [ -d "$MIGRATION_DIR" ]; then
    MIGRATION_COUNT=0
    for migration in $(ls "$MIGRATION_DIR"/v*.py 2>/dev/null | sort -V); do
        migration_name="$(basename "$migration" .py)"
        echo "  Running $migration_name..."
        ./venv/bin/python -c "
import sys
sys.path.insert(0, '$BACKEND_DIR')
from database.migrations.${migration_name} import migrate
migrate()
" 2>&1 | sed 's/^/    /'
        MIGRATION_COUNT=$((MIGRATION_COUNT + 1))
    done
    if [ $MIGRATION_COUNT -eq 0 ]; then
        echo "  No migrations found"
    else
        echo "  [OK] $MIGRATION_COUNT migration(s) executed"
    fi
else
    echo "  [WARN]  No migrations directory found"
fi

# Verify reframe tuning defaults landed (anti-flicker + detection floor)
echo "  Verifying reframe tuning defaults..."
./venv/bin/python -c "
import sys
sys.path.insert(0, '$BACKEND_DIR')
from src.presentation.routes.settings import get_reframe_tuning, REFRAME_TUNING_DEFAULTS
from src.config import settings

cfg = get_reframe_tuning(None)
checks = {
    'grid_enter_samples': 9,
    'grid_exit_samples': 6,
    'min_grid_segment_seconds': 3.0,
    'min_separation_ratio': 0.05,
    'grid_max_zoom': 2.20,
}
bad = []
for k, floor in checks.items():
    val = cfg.get(k)
    if val is None:
        bad.append(f'{k}=missing')
    elif isinstance(floor, float):
        if float(val) < float(floor) - 1e-9 and k != 'grid_max_zoom':
            bad.append(f'{k}={val} (want>={floor})')
        if k == 'grid_max_zoom' and abs(float(val) - float(floor)) > 1e-9:
            # only warn if below floor; higher zoom ok
            if float(val) < float(floor):
                bad.append(f'{k}={val} (want>={floor})')
    else:
        if int(val) < int(floor):
            bad.append(f'{k}={val} (want>={floor})')

print(f'  reframe global: enter={cfg.get(\"grid_enter_samples\")} '
      f'exit={cfg.get(\"grid_exit_samples\")} '
      f'min_seg={cfg.get(\"min_grid_segment_seconds\")} '
      f'sep={cfg.get(\"min_separation_ratio\")} '
      f'max_zoom={cfg.get(\"grid_max_zoom\")}')
print(f'  PERSON_CONF_THRESHOLD={settings.PERSON_CONF_THRESHOLD}')
print(f'  REFRAME_PIPELINE_MODE={settings.REFRAME_PIPELINE_MODE}')
if bad:
    print('  [FAIL] reframe tuning verify failed: ' + ', '.join(bad))
    sys.exit(1)
print('  [OK] reframe tuning defaults OK')
" 2>&1 | sed 's/^/  /' || {
    echo "  [FAIL] Reframe tuning verification failed"
    exit 1
}

# Object overlay style table (AI entities → photo card; style only in DB)
echo "  Verifying object overlay config..."
./venv/bin/python -c "
import sys
sys.path.insert(0, '$BACKEND_DIR')
from src.presentation.routes.settings import (
    _ensure_object_overlay_table,
    get_object_overlay_config,
)
from src.config import settings

_ensure_object_overlay_table()
cfg = get_object_overlay_config(None)
need = ['enabled', 'max_per_clip', 'box_size_ratio', 'position', 'animation', 'show_label']
bad = [k for k in need if k not in cfg]
if bad:
    print('  [FAIL] object overlay missing keys: ' + ', '.join(bad))
    sys.exit(1)
print(
    f'  object_overlay: enabled={cfg.get(\"enabled\")} '
    f'max={cfg.get(\"max_per_clip\")} '
    f'pos={cfg.get(\"position\")} '
    f'anim={cfg.get(\"animation\")}'
)
print(f'  OBJECT_OVERLAY_ENABLED={getattr(settings, \"OBJECT_OVERLAY_ENABLED\", None)}')
print('  [OK] object overlay config OK')
" 2>&1 | sed 's/^/  /' || {
    echo "  [FAIL] Object overlay verification failed"
    exit 1
}

# Ensure music assets dir exists (AudioMixer duck bed)
mkdir -p "$BACKEND_DIR/assets/music"
# Ensure BGM dir for Video Generator
mkdir -p "$BACKEND_DIR/assets/bgm"
# Ensure video generator output dir
mkdir -p "$BACKEND_DIR/tmp/video_gen"
if [ -z "$(ls -A "$BACKEND_DIR/assets/music" 2>/dev/null)" ]; then
    echo "  [WARN]  assets/music empty — music bed will skip until files added (non-fatal)"
else
    echo "  [OK] Music beds present ($(ls "$BACKEND_DIR/assets/music" | wc -l | tr -d ' ') file(s))"
fi

# Bootstrap DB schema & seed dynamic system settings
echo "  Ensuring SQLite schema & system settings..."
./venv/bin/python -c "
import asyncio, sys, os
sys.path.insert(0, '$BACKEND_DIR')
os.chdir('$BACKEND_DIR')
async def main():
    from src.infrastructure.database import init_db
    await init_db()
    from src.infrastructure.db_seeder import seed_database
    seed_database()
    print('  [OK] DB schema, roles & system settings initialized')
asyncio.run(main())
" 2>&1 | sed 's/^/  /' || echo "  [WARN]  DB bootstrap deferred to app startup"

# ─── Step 3.2: Person-First Pipeline Models ──────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 3.2: Person-First Pipeline Models"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# RF-DETR Large — pre-download so first inference doesn't block
echo "  Checking RF-DETR Large model..."
./venv/bin/python3 -c "
try:
    from rfdetr import RFDETRLarge
    model = RFDETRLarge()
    print('  RF-DETR Large: already cached')
except Exception as e:
    print(f'  RF-DETR Large: download needed ({e})')
    try:
        from rfdetr import RFDETRLarge
        RFDETRLarge()
        print('  RF-DETR Large: downloaded OK')
    except Exception as e2:
        print(f'  [WARN]  RF-DETR download failed: {e2}')
        print('  Will fallback to Ultralytics YOLO at runtime')
" 2>&1 || echo "  [WARN]  RF-DETR pre-download skipped (non-fatal)"

# RetinaFace — pre-download model weights
echo "  Checking RetinaFace model..."
./venv/bin/python3 -c "
try:
    from retinaface.pre_trained_models import get_model
    model = get_model('resnet50_2020-07-20', max_size=640)
    print('  RetinaFace resnet50: ready')
except ImportError:
    print('  RetinaFace: package not available, will use MediaPipe fallback')
except Exception as e:
    print(f'  RetinaFace: {e}')
" 2>&1 || echo "  [WARN]  RetinaFace pre-download skipped (non-fatal)"

# Ultralytics YOLO — pre-download for tracker fallback + person detection fallback
echo "  Checking YOLO26n model (tracker fallback)..."
if [ ! -f "models/yolo26n.pt" ]; then
    ./venv/bin/python3 -c "
from ultralytics import YOLO
import shutil, os
model = YOLO('yolo26n.pt')
# Move to models/ dir if downloaded to cwd
if os.path.exists('yolo26n.pt') and not os.path.exists('models/yolo26n.pt'):
    shutil.move('yolo26n.pt', 'models/yolo26n.pt')
print('  YOLO26n: ready')
" 2>&1 || echo "  [WARN]  YOLO26n download skipped"
else
    echo "  YOLO26n: already present"
fi

# YOLO26n-seg — for text-behind-person effect + person segmentation
echo "  Checking YOLO26n-seg model..."
if [ ! -f "models/yolo26n-seg.pt" ]; then
    ./venv/bin/python3 -c "
from ultralytics import YOLO
import shutil, os
model = YOLO('yolo26n-seg.pt')
if os.path.exists('yolo26n-seg.pt') and not os.path.exists('models/yolo26n-seg.pt'):
    shutil.move('yolo26n-seg.pt', 'models/yolo26n-seg.pt')
print('  YOLO26n-seg: ready')
" 2>&1 || echo "  [WARN]  YOLO26n-seg download skipped"
else
    echo "  YOLO26n-seg: already present"
fi

echo "  [OK] Models provisioned"

# ─── Step 3.5: Optional cache clear ──────────────────────────────────────────
echo ""
if [ "$CLEAR_AI_CACHE_ON_DEPLOY" = "1" ]; then
    echo "  Clearing cached transcripts & analysis..."
    rm -rf "$BACKEND_DIR/tmp/cache/"*/transcript*.json 2>/dev/null || true
    rm -rf "$BACKEND_DIR/tmp/cache/"*/analysis*.json 2>/dev/null || true
    echo "  [OK] Cache cleared (transcripts + analysis)"
else
    echo "  Keeping cached transcripts & analysis (set CLEAR_AI_CACHE_ON_DEPLOY=1 to clear)"
fi

# ─── Step 4: Remotion Server ────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 4: Remotion Server (Node.js — port $REMOTION_PORT)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "$REMOTION_DIR" ]; then
    cd "$REMOTION_DIR"

    # Remotion server needs tsx + typescript (in devDependencies) to run
    if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules/.package-lock.json" ]; then
        echo "  Installing npm dependencies (including tsx/typescript)..."
        npm install 2>/dev/null || npm install
    else
        echo "  [OK] npm dependencies up to date"
    fi

    # CRITICAL: Clear webpack/remotion bundler cache to force fresh bundle
    # Without this, old compositions may be cached and used even after code changes
    echo "  Clearing Remotion bundler cache..."
    rm -rf "$REMOTION_DIR/node_modules/.cache" 2>/dev/null || true
    rm -rf /tmp/remotion-* 2>/dev/null || true

    # CRITICAL: Fix ownership — prevents EPERM/EACCES when Remotion service
    # runs as $DEPLOY_USER but npm install/git pull ran as root/sudo
    echo "  Fixing file ownership..."
    chown -R $DEPLOY_USER:$DEPLOY_USER "$REMOTION_DIR"
    chmod +x "$REMOTION_DIR/node_modules/@remotion/compositor-linux-x64-gnu/remotion" 2>/dev/null || true
    chmod +x "$REMOTION_DIR/node_modules/@remotion/compositor-linux-x64-musl/remotion" 2>/dev/null || true

    echo "  Type-checking Remotion server and compositions..."
    npm run build
    echo "  [OK] Remotion ready (will re-bundle on service start)"
else
    echo "  [WARN]  Remotion directory not found at $REMOTION_DIR"
fi

# ─── Step 4b: HyperFrames polish server ─────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 4b: HyperFrames polish (Node.js — port $HYPERFRAMES_PORT)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "$HYPERFRAMES_DIR" ]; then
    cd "$HYPERFRAMES_DIR"
    if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules/.package-lock.json" ] 2>/dev/null; then
        echo "  Installing HyperFrames npm dependencies..."
        npm install 2>/dev/null || npm install
    else
        echo "  [OK] HyperFrames npm dependencies up to date"
    fi
    mkdir -p "$HYPERFRAMES_DIR/work"
    chown -R $DEPLOY_USER:$DEPLOY_USER "$HYPERFRAMES_DIR" 2>/dev/null || true
    # Sanity: assembler loads
    node -e "import('./src/assemble.mjs').then(m => console.log('templates', m.listTemplates().join(',')))" \
        || echo "  [WARN]  HyperFrames assembler check failed (non-fatal until service start)"
    echo "  [OK] HyperFrames renderer ready (polish only; hook+subtitle = Remotion)"
else
    echo "  [WARN]  HyperFrames directory not found at $HYPERFRAMES_DIR"
fi

# ─── Step 4c: Hermes config (local == server) ───────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 4c: Hermes Agent config sync"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -x "$PROJECT_DIR/scripts/sync-hermes-config.sh" ]; then
    sudo -u "$DEPLOY_USER" env HERMES_HOME="$HERMES_HOME_DEPLOY" \
        "$PROJECT_DIR/scripts/sync-hermes-config.sh" \
        || HERMES_HOME="$HERMES_HOME_DEPLOY" bash "$PROJECT_DIR/scripts/sync-hermes-config.sh" || true
    echo "  [OK] Hermes config synced → $HERMES_HOME_DEPLOY"
else
    echo "  [WARN]  scripts/sync-hermes-config.sh missing"
fi
if command -v hermes &>/dev/null; then
    echo "  [OK] hermes binary: $(command -v hermes)"
else
    echo "  [INFO]  hermes not on PATH — optional install:"
    echo "     curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
fi

# ─── Step 4d: Telegram Bot Setup ───────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 4d: Telegram Bot Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

TELEGRAM_BOT_DIR="$PROJECT_DIR/ops/telegram"
if [ -d "$TELEGRAM_BOT_DIR" ]; then
    cd "$TELEGRAM_BOT_DIR"
    if [ ! -d "venv" ]; then
        echo "  Creating Telegram bot virtual environment..."
        $PYTHON_BIN -m venv venv
    fi
    ./venv/bin/pip install --upgrade pip -q 2>/dev/null || true
    if [ -f "requirements.txt" ]; then
        echo "  Syncing Telegram bot dependencies..."
        ./venv/bin/pip install -r requirements.txt -q 2>/dev/null || \
            ./venv/bin/pip install -r requirements.txt
    fi
    chown -R $DEPLOY_USER:$DEPLOY_USER "$TELEGRAM_BOT_DIR" 2>/dev/null || true
    echo "  [OK] Telegram Bot environment ready"
fi

# Continue frontend step marker — original Step 5 follows in file

# ─── Step 5: Frontend Build ─────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 5: Frontend Build (Vite — port $FRONTEND_PORT)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "$FRONTEND_DIR" ]; then
    cd "$FRONTEND_DIR"

    # Previous deploys may have created dist/node_modules as root. Vite clears
    # dist before build, so stale ownership causes EACCES on unlink.
    echo "  Fixing frontend file ownership..."
    sudo chown -R $DEPLOY_USER:$DEPLOY_USER "$FRONTEND_DIR"

    if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules/.package-lock.json" ]; then
        echo "  Installing npm dependencies..."
        npm install 2>/dev/null || npm install
    else
        echo "  [OK] npm dependencies up to date"
    fi

    echo "  Type-checking and building production bundle..."
    npm run build

    if [ -d "dist" ] && [ -f "dist/index.html" ]; then
        echo "  [OK] Frontend built"
    else
        echo "  [FAIL] Frontend build did not produce dist/index.html"
        exit 1
    fi

    # Install serve globally for static file serving
    if ! command -v serve &>/dev/null; then
        echo "  Installing serve..."
        npm install -g serve 2>/dev/null || true
    fi
else
    echo "  [WARN]  Frontend directory not found at $FRONTEND_DIR"
fi

# ─── Step 6: Systemd Services ───────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 6: Systemd Services"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Backend service
sudo tee /etc/systemd/system/autocliper-backend.service > /dev/null << EOF
[Unit]
Description=AutoCliper Backend (FastAPI)
After=network.target

[Service]
Type=simple
User=$DEPLOY_USER
WorkingDirectory=$BACKEND_DIR
EnvironmentFile=-$BACKEND_DIR/.env
Environment=PATH=$BACKEND_DIR/venv/bin:/usr/local/bin:/usr/bin
# Kill any stale process on port before starting (prevents EADDRINUSE)
ExecStartPre=/bin/sh -c '/usr/bin/fuser -k $BACKEND_PORT/tcp 2>/dev/null || true'
ExecStartPre=/bin/sleep 1
ExecStart=$BACKEND_DIR/venv/bin/python -m uvicorn src.presentation.api:app --host 0.0.0.0 --port $BACKEND_PORT --workers ${BACKEND_WORKERS:-2}
Restart=always
RestartSec=5
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 9router service
NINE_ROUTER_BIN="$(command -v 9router || true)"
if [ -n "$NINE_ROUTER_BIN" ]; then
    sudo tee /etc/systemd/system/autocliper-9router.service > /dev/null << EOF
[Unit]
Description=AutoCliper 9router LLM Gateway
After=network.target

[Service]
Type=simple
User=$DEPLOY_USER
WorkingDirectory=$PROJECT_DIR
Environment=HOME=$DEPLOY_HOME
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=$NINE_ROUTER_BIN --host $NINE_ROUTER_HOST --port $NINE_ROUTER_PORT --no-browser --skip-update --log
Restart=always
RestartSec=5
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
else
    echo "  [WARN]  9router binary not found — skipping autocliper-9router.service"
fi

# Remotion service
sudo tee /etc/systemd/system/autocliper-remotion.service > /dev/null << EOF
[Unit]
Description=AutoCliper Remotion Renderer (Node.js)
After=network.target

[Service]
Type=simple
User=$DEPLOY_USER
WorkingDirectory=$REMOTION_DIR
Environment=REMOTION_SERVER_PORT=$REMOTION_PORT
Environment=NODE_ENV=production
Environment=PATH=/usr/local/bin:/usr/bin
# Kill any stale process on port before starting (prevents EADDRINUSE)
ExecStartPre=/bin/sh -c '/usr/bin/fuser -k $REMOTION_PORT/tcp 2>/dev/null || true'
ExecStartPre=/bin/sleep 1
ExecStart=/usr/bin/npx tsx src/server/index.ts
ExecStop=/bin/sh -c '/usr/bin/fuser -k $REMOTION_PORT/tcp 2>/dev/null || true'
Restart=always
RestartSec=5
# Give process time to release port on stop
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# HyperFrames polish service (does NOT replace Remotion)
if [ -d "$HYPERFRAMES_DIR" ] && [ -f "$HYPERFRAMES_DIR/src/server.mjs" ]; then
    sudo tee /etc/systemd/system/autocliper-hyperframes.service > /dev/null << EOF
[Unit]
Description=AutoCliper HyperFrames Polish Renderer
After=network.target

[Service]
Type=simple
User=$DEPLOY_USER
WorkingDirectory=$HYPERFRAMES_DIR
Environment=NODE_ENV=production
Environment=HYPERFRAMES_SERVER_PORT=$HYPERFRAMES_PORT
Environment=HYPERFRAMES_WORK_DIR=$HYPERFRAMES_DIR/work
Environment=PATH=/usr/local/bin:/usr/bin
ExecStartPre=/bin/sh -c '/usr/bin/fuser -k $HYPERFRAMES_PORT/tcp 2>/dev/null || true'
ExecStartPre=/bin/sleep 1
ExecStart=/usr/bin/node src/server.mjs
Restart=always
RestartSec=5
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    echo "  [OK] autocliper-hyperframes.service written"
else
    echo "  [WARN]  HyperFrames server missing — skipping autocliper-hyperframes.service"
fi

# Frontend service
sudo tee /etc/systemd/system/autocliper-frontend.service > /dev/null << EOF
[Unit]
Description=AutoCliper Frontend (Static)
After=network.target

[Service]
Type=simple
User=$DEPLOY_USER
WorkingDirectory=$FRONTEND_DIR
# Kill any stale process on port before starting (prevents EADDRINUSE)
ExecStartPre=/bin/sh -c '/usr/bin/fuser -k $FRONTEND_PORT/tcp 2>/dev/null || true'
ExecStartPre=/bin/sleep 1
ExecStart=/usr/bin/npx --yes serve dist -l $FRONTEND_PORT -s --no-clipboard
Restart=always
RestartSec=5
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Telegram Bot service
if [ -d "$TELEGRAM_BOT_DIR" ] && [ -f "$TELEGRAM_BOT_DIR/telegram_bot.py" ]; then
    sudo tee /etc/systemd/system/autocliper-telegram-bot.service > /dev/null << EOF
[Unit]
Description=AutoCliper Telegram Bot
After=network.target autocliper-backend.service
Wants=autocliper-backend.service

[Service]
Type=simple
User=$DEPLOY_USER
WorkingDirectory=$TELEGRAM_BOT_DIR
Environment=HERMES_HOME=$HERMES_HOME_DEPLOY
Environment=PATH=$TELEGRAM_BOT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$TELEGRAM_BOT_DIR/venv/bin/python3 $TELEGRAM_BOT_DIR/telegram_bot.py
Restart=always
RestartSec=5
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    echo "  [OK] autocliper-telegram-bot.service written"
fi

# Cloudflare Tunnel service (autocliper-tunnel)
CLOUDFLARED_BIN="$(command -v cloudflared || true)"
if [ -n "$CLOUDFLARED_BIN" ]; then
    sudo tee /etc/systemd/system/autocliper-tunnel.service > /dev/null << EOF
[Unit]
Description=AutoCliper Cloudflare Tunnel (Repliz Media & Public Gateway)
After=network.target autocliper-backend.service
Wants=autocliper-backend.service

[Service]
Type=simple
User=$DEPLOY_USER
EnvironmentFile=-$BACKEND_DIR/.env
ExecStart=/bin/bash -c 'if [ -n "$$CLOUDFLARE_TUNNEL_TOKEN" ]; then exec '"$CLOUDFLARED_BIN"' tunnel run --token "$$CLOUDFLARE_TUNNEL_TOKEN"; else exec '"$CLOUDFLARED_BIN"' tunnel --url http://127.0.0.1:'"$BACKEND_PORT"' --no-autoupdate; fi'
Restart=always
RestartSec=5
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    echo "  [OK] autocliper-tunnel.service written"
fi

# Reload and restart (Remotion FIRST — must be ready before backend)
sudo systemctl daemon-reload
sudo systemctl enable autocliper-9router autocliper-backend autocliper-remotion autocliper-hyperframes autocliper-frontend autocliper-telegram-bot autocliper-tunnel 2>/dev/null || true

# Start Remotion first and wait for bundle to be ready
echo "  Stopping services (cleanup stale ports)..."
sudo systemctl stop autocliper-9router 2>/dev/null || true
sudo systemctl stop autocliper-remotion 2>/dev/null || true
sudo systemctl stop autocliper-hyperframes 2>/dev/null || true
sudo systemctl stop autocliper-telegram-bot 2>/dev/null || true
sudo systemctl stop autocliper-tunnel 2>/dev/null || true
sudo systemctl stop autocliper-backend 2>/dev/null || true
sudo systemctl stop autocliper-frontend 2>/dev/null || true
sleep 2

echo "  Starting 9router..."
sudo systemctl start autocliper-9router 2>/dev/null || true
NINE_ROUTER_READY=0
for i in $(seq 1 40); do
    if curl -s "http://$NINE_ROUTER_HOST:$NINE_ROUTER_PORT" >/dev/null 2>&1; then
        NINE_ROUTER_READY=1
        echo "  [OK] 9router ready (${i}s)"
        break
    fi
    sleep 1
done
if [ $NINE_ROUTER_READY -eq 0 ]; then
    echo "  [WARN]  9router not responding yet — check logs: sudo journalctl -u autocliper-9router -n 30"
fi

echo "  Starting Remotion server (bundling compositions)..."
sudo systemctl start autocliper-remotion
REMOTION_READY=0
for i in $(seq 1 60); do
    if curl -s "http://localhost:$REMOTION_PORT/health" 2>/dev/null | grep -q "healthy"; then
        REMOTION_READY=1
        echo "  [OK] Remotion bundled and ready (${i}s)"
        break
    fi
    sleep 1
done
if [ $REMOTION_READY -eq 0 ]; then
    echo "  [WARN]  Remotion not ready after 60s — check logs: sudo journalctl -u autocliper-remotion -n 30"
fi

echo "  Starting HyperFrames polish server..."
sudo systemctl start autocliper-hyperframes 2>/dev/null || true
HF_READY=0
for i in $(seq 1 30); do
    if curl -s "http://localhost:$HYPERFRAMES_PORT/health" 2>/dev/null | grep -q "healthy"; then
        HF_READY=1
        echo "  [OK] HyperFrames ready (${i}s)"
        break
    fi
    sleep 1
done
if [ $HF_READY -eq 0 ]; then
    echo "  [WARN]  HyperFrames not ready — check: sudo journalctl -u autocliper-hyperframes -n 30"
fi

# Now restart backend (Remotion is ready to handle render requests)
sudo systemctl start autocliper-backend
sudo systemctl start autocliper-frontend

if [ -f "/etc/systemd/system/autocliper-telegram-bot.service" ]; then
    echo "  Starting Telegram Bot..."
    sudo systemctl start autocliper-telegram-bot 2>/dev/null || true
fi

if [ -f "/etc/systemd/system/autocliper-tunnel.service" ]; then
    echo "  Starting Cloudflare Tunnel..."
    sudo systemctl start autocliper-tunnel 2>/dev/null || true
    # Auto-detect dynamic trycloudflare quick tunnel URL
    sleep 3
    DETECTED_TUNNEL_URL="$(sudo journalctl -u autocliper-tunnel -n 50 --no-pager 2>/dev/null | grep -oE 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' | tail -n 1)"
    if [ -n "$DETECTED_TUNNEL_URL" ]; then
        AUTOCLIPER_PUBLIC_URL="$DETECTED_TUNNEL_URL"
        set_env_value "$BACKEND_DIR/.env" "AUTOCLIPER_PUBLIC_URL" "$DETECTED_TUNNEL_URL"
        echo "  [OK] Cloudflare Tunnel live at: $DETECTED_TUNNEL_URL"
        sudo systemctl restart autocliper-backend 2>/dev/null || true
    fi
fi

echo "  [OK] All services registered and started"

# ─── Step 7: Nginx (optional — only if nginx is installed) ──────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 7: Nginx Reverse Proxy (optional)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Nginx reverse proxy
if ! command -v nginx &>/dev/null; then
    echo "  Installing Nginx..."
    sudo apt-get update -qq 2>/dev/null || true
    sudo apt-get install -y nginx 2>/dev/null || true
fi

if command -v nginx &>/dev/null; then
    # Clean any stale/conflicting conf.d configs
    sudo rm -f /etc/nginx/conf.d/autocliper_security.conf 2>/dev/null || true

    # Clean site configuration
    sudo tee /etc/nginx/sites-available/autocliper > /dev/null << 'EOF'
server {
    listen 80 default_server;
    server_name _;

    client_max_body_size 500M;
    client_header_buffer_size 8k;
    large_client_header_buffers 4 32k;

    # Security Headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Block sensitive files
    location ~ /\.(?!well-known) {
        return 404;
    }
    location ~* \.(sqlite|sqlite3|db|sql|log|sh|py|bak|env|yml|yaml|md)$ {
        return 404;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    # Backend health
    location /health {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Video files (streaming)
    location ~* /api/jobs/.*/clips/.*/(?:final|raw|thumb) {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
        proxy_buffering off;
    }

    # Frontend (Vite Static / SPA)
    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
    # Remove default debian/ubuntu nginx site to avoid port 80 conflict
    sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
    sudo ln -sf /etc/nginx/sites-available/autocliper /etc/nginx/sites-enabled/ 2>/dev/null
    sudo systemctl enable nginx 2>/dev/null || true
    if sudo nginx -t; then
        sudo systemctl restart nginx
        echo "  [OK] Nginx configured and active on port 80"
    else
        echo "  [WARN] Nginx config test failed — check: sudo nginx -t"
    fi
else
    echo "  [WARN]  Nginx not installed — access services directly via ports"
fi

# ─── Step 8: Health Check ────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 8: Health Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

sleep 4

check_service() {
    if sudo systemctl is-active --quiet "$1" 2>/dev/null; then
        echo "  [OK] $1 — RUNNING (port $2)"
    else
        echo "  [FAIL] $1 — FAILED"
        echo "     → sudo journalctl -u $1 -n 15 --no-pager"
    fi
}

check_service "autocliper-backend" "$BACKEND_PORT"
check_service "autocliper-9router" "$NINE_ROUTER_PORT"
check_service "autocliper-remotion" "$REMOTION_PORT"
check_service "autocliper-hyperframes" "$HYPERFRAMES_PORT"
check_service "autocliper-frontend" "$FRONTEND_PORT"
if [ -f "/etc/systemd/system/autocliper-telegram-bot.service" ]; then
    check_service "autocliper-telegram-bot" "Polling"
fi
if [ -f "/etc/systemd/system/autocliper-tunnel.service" ]; then
    check_service "autocliper-tunnel" "Tunnel"
fi

# API health check
if curl -s "http://localhost:$BACKEND_PORT/health" | grep -q "ok" 2>/dev/null; then
    echo "  [OK] Backend API responding"
else
    echo "  [WARN]  Backend API not responding yet (may still be starting)"
fi

if curl -s "http://localhost:$HYPERFRAMES_PORT/health" 2>/dev/null | grep -q "healthy"; then
    echo "  [OK] HyperFrames API responding"
else
    echo "  [WARN]  HyperFrames API not responding"
fi

# Zero-touch readiness (no manual DB/.env after deploy)
echo ""
echo "  Production readiness:"
if [ -f "$HERMES_HOME_DEPLOY/config.yaml" ]; then
    echo "  [OK] Hermes config at $HERMES_HOME_DEPLOY/config.yaml"
else
    echo "  [WARN]  Hermes config missing — run scripts/sync-hermes-config.sh"
fi
if [ -d "$BACKEND_DIR/assets/music" ]; then
    echo "  [OK] assets/music ready"
else
    echo "  [WARN]  assets/music missing"
fi
if [ -f "$BACKEND_DIR/data/autocliper.db" ] || [ -f "$BACKEND_DIR/data/autoclip.db" ] || [ -f "$BACKEND_DIR/autocliper.db" ] || ls "$BACKEND_DIR"/data/*.db >/dev/null 2>&1; then
    echo "  [OK] SQLite DB present"
else
    echo "  [INFO]  SQLite path may be under DATA_DIR — app init_db handles create"
fi

sudo chown -R $DEPLOY_USER:$DEPLOY_USER "$PROJECT_DIR" 2>/dev/null || true

# ─── Done ────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  [OK] Deployment Complete!"
echo ""
echo "  Services:"
echo "    9router:      http://127.0.0.1:$NINE_ROUTER_PORT"
echo "    Backend:      $PUBLIC_BACKEND_URL"
echo "    Public CDN:   $AUTOCLIPER_PUBLIC_URL"
echo "    Remotion:     http://$PUBLIC_HOST:$REMOTION_PORT   (hook+subtitle)"
echo "    HyperFrames:  http://$PUBLIC_HOST:$HYPERFRAMES_PORT  (polish)"
echo "    Frontend:     $PUBLIC_FRONTEND_URL"
echo "    Telegram Bot: $(systemctl is-active autocliper-telegram-bot 2>/dev/null || echo 'not active')"
echo "    Tunnel:       $(systemctl is-active autocliper-tunnel 2>/dev/null || echo 'not active')"
echo "    Hermes home:  $HERMES_HOME_DEPLOY"
echo ""
echo "  Open:"
echo "    $PUBLIC_FRONTEND_URL"
echo ""
echo "  Logs:"
echo "    sudo journalctl -u autocliper-backend -f"
echo "    sudo journalctl -u autocliper-tunnel -f"
echo "    sudo journalctl -u autocliper-telegram-bot -f"
echo "    sudo journalctl -u autocliper-remotion -f"
echo "    sudo journalctl -u autocliper-hyperframes -f"
echo "    sudo journalctl -u autocliper-9router -f"
echo "    sudo journalctl -u autocliper-frontend -f"
echo ""
echo "  Management:"
echo "    sudo systemctl status autocliper-9router"
echo "    sudo systemctl status autocliper-backend"
echo "    sudo systemctl status autocliper-hyperframes"
echo "    sudo systemctl restart autocliper-backend"
echo ""
echo "  Migrate local→server (same config):"
echo "    scripts/pack-9router-data.sh && scripts/pack-hermes-data.sh"
echo "    # scp archives → server → restore-*.sh → ./deploy.sh"
echo ""
echo "  Docs: docs/production-stack.md"
echo ""
echo " sudo journalctl -u autocliper-backend -f"
echo "  Next run will be fast (skips installed components)."
echo "═══════════════════════════════════════════════════════════════"
