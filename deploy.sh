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
#   - IP: 192.168.168.58 / 103.122.34.166
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
PUBLIC_HOST="${PUBLIC_HOST:-100.64.5.96}"
PUBLIC_FRONTEND_URL="${PUBLIC_FRONTEND_URL:-http://$PUBLIC_HOST:$FRONTEND_PORT}"
PUBLIC_BACKEND_URL="${PUBLIC_BACKEND_URL:-http://$PUBLIC_HOST:$BACKEND_PORT}"
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
    echo "  ✅ Code updated"
else
    echo "  ⚠️  No .git found — skipping pull"
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

if [ -z "$MISSING" ]; then
    echo "  ✅ All system dependencies present"
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

    echo "  ✅ System packages installed"
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
    echo "  ✅ FFmpeg dev libraries installed"
fi

echo "  Python: $($PYTHON_BIN --version 2>/dev/null)"
echo "  Node:   $(node --version 2>/dev/null)"
echo "  FFmpeg: $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3)"

# ─── Step 2.5: 9router CLI ──────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 2.5: 9router CLI"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if command -v 9router &>/dev/null; then
    echo "  ✅ 9router CLI found: $(command -v 9router)"
else
    echo "  Installing 9router@$NINE_ROUTER_CLI_VERSION..."
    npm install -g "9router@$NINE_ROUTER_CLI_VERSION" --prefer-online 2>/dev/null || \
        sudo npm install -g "9router@$NINE_ROUTER_CLI_VERSION" --prefer-online
    echo "  ✅ 9router CLI installed"
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
echo "  ✅ Backend validation passed"

# Keep the server-side pre-deployment test gate ready. Test dependencies are
# isolated from runtime requirements but installed into the backend venv that
# test.sh and the systemd backend service consistently use.
if [ -f "requirements-dev.txt" ]; then
    echo "  Installing backend test dependencies..."
    ./venv/bin/pip install -r requirements-dev.txt -q
    echo "  ✅ Backend test dependencies ready"
fi

# GPU: Install PyTorch with CUDA 12.1 (compatible with NVIDIA driver 535+)
# This enables GPU acceleration for: Faster-Whisper, YOLO, torchaudio
if command -v nvidia-smi &>/dev/null; then
    echo "  Installing PyTorch with CUDA 12.1 (GPU detected)..."
    ./venv/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121 -q 2>/dev/null || \
        ./venv/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
    echo "  ✅ PyTorch CUDA 12.1 installed"
else
    echo "  ℹ️  No GPU detected — using CPU-only PyTorch"
fi

# Create .env from production template if not exists
if [ ! -f ".env" ]; then
    if [ -f ".env.production" ]; then
        echo "  Copying .env.production → .env"
        cp .env.production .env
    elif [ -f ".env.example" ]; then
        echo "  ⚠️  No .env found — copying from .env.example"
        echo "  ⚠️  EDIT .env WITH YOUR ACTUAL CREDENTIALS"
        cp .env.example .env
    fi
fi

# Ensure .env has the 9router-first production keys, even on older servers.
if [ -f ".env" ]; then
    append_env_if_missing ".env" "LLM_PROVIDER" "nine_router"
    append_env_if_missing ".env" "FORCE_V2_PIPELINE" "true"
    append_env_if_missing ".env" "ALLOW_DIRECT_PROVIDER_FALLBACKS" "false"
    append_env_if_missing ".env" "TRANSCRIPTION_PROVIDER" "local"
    append_env_if_missing ".env" "NINE_ROUTER_BASE_URL" "$NINE_ROUTER_DEFAULT_BASE_URL"
    append_env_if_missing ".env" "NINE_ROUTER_API_KEY" ""
    append_env_if_missing ".env" "NINE_ROUTER_MODEL" "CliperHub"
    append_env_if_missing ".env" "NINE_ROUTER_PASS1_MODEL" "CliperHub"
    append_env_if_missing ".env" "NINE_ROUTER_PASS2_MODEL" "CliperHub"
    append_env_if_missing ".env" "NINE_ROUTER_AI_LAYER_MODEL" "CliperHub"
    append_env_if_missing ".env" "NINE_ROUTER_TIMEOUT" "120"
    append_env_if_missing ".env" "NINE_ROUTER_MAX_RETRIES" "3"
    set_env_value ".env" "CORS_ORIGINS" "$PUBLIC_FRONTEND_URL,http://$PUBLIC_HOST:3000"

    LLM_PROVIDER_VAL="$(env_value ".env" "LLM_PROVIDER" "nine_router")"
    NINE_ROUTER_BASE_URL_VAL="$(env_value ".env" "NINE_ROUTER_BASE_URL" "")"
    NINE_ROUTER_API_KEY_VAL="$(env_value ".env" "NINE_ROUTER_API_KEY" "")"

    if [ "$LLM_PROVIDER_VAL" = "nine_router" ] || [ "$LLM_PROVIDER_VAL" = "9router" ] || [ "$LLM_PROVIDER_VAL" = "ninerouter" ]; then
        if [ -z "$NINE_ROUTER_BASE_URL_VAL" ]; then
            echo "NINE_ROUTER_BASE_URL=$NINE_ROUTER_DEFAULT_BASE_URL" >> ".env"
            NINE_ROUTER_BASE_URL_VAL="$NINE_ROUTER_DEFAULT_BASE_URL"
        fi
        if [ -z "$NINE_ROUTER_API_KEY_VAL" ]; then
            echo "  ⚠️  NINE_ROUTER_API_KEY is empty. Continuing because some local 9router installs do not require auth."
        fi
        echo "  ✅ 9router configured (model=$(env_value ".env" "NINE_ROUTER_MODEL" "CliperHub"), url=$NINE_ROUTER_BASE_URL_VAL)"
    fi
fi

# Create directories
mkdir -p data data/asset_cache tmp/output tmp/downloads models

echo "  ✅ Backend ready"

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
        echo "  ✅ $MIGRATION_COUNT migration(s) executed"
    fi
else
    echo "  ⚠️  No migrations directory found"
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
    print('  ❌ reframe tuning verify failed: ' + ', '.join(bad))
    sys.exit(1)
print('  ✅ reframe tuning defaults OK')
" 2>&1 | sed 's/^/  /' || {
    echo "  ❌ Reframe tuning verification failed"
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
    print('  ❌ object overlay missing keys: ' + ', '.join(bad))
    sys.exit(1)
print(
    f'  object_overlay: enabled={cfg.get(\"enabled\")} '
    f'max={cfg.get(\"max_per_clip\")} '
    f'pos={cfg.get(\"position\")} '
    f'anim={cfg.get(\"animation\")}'
)
print(f'  OBJECT_OVERLAY_ENABLED={getattr(settings, \"OBJECT_OVERLAY_ENABLED\", None)}')
print('  ✅ object overlay config OK')
" 2>&1 | sed 's/^/  /' || {
    echo "  ❌ Object overlay verification failed"
    exit 1
}

# Detection floor — append only if missing (never overwrite ops override)
if [ -f ".env" ]; then
    append_env_if_missing ".env" "PERSON_CONF_THRESHOLD" "0.35"
    append_env_if_missing ".env" "REFRAME_PIPELINE_MODE" "person_first"
    append_env_if_missing ".env" "TOP_OVERLAY_ENABLED" "true"
    append_env_if_missing ".env" "TOP_OVERLAY_SPLIT_RATIO" "0.58"
    append_env_if_missing ".env" "TOP_OVERLAY_FADE_HEIGHT" "0.10"
    append_env_if_missing ".env" "TOP_OVERLAY_OPACITY" "1.0"
    append_env_if_missing ".env" "TOP_OVERLAY_PERSON_OUTLINE" "true"
    append_env_if_missing ".env" "TOP_OVERLAY_PERSON_SHADOW" "true"
    append_env_if_missing ".env" "TOP_OVERLAY_OUTLINE_THICKNESS" "12"
    append_env_if_missing ".env" "TOP_OVERLAY_OUTLINE_COLOR" "255,255,255"
    append_env_if_missing ".env" "TOP_OVERLAY_OUTLINE_STYLE" "white"
    append_env_if_missing ".env" "TOP_OVERLAY_MAX_PER_CLIP" "2"
    append_env_if_missing ".env" "TOP_OVERLAY_SEG_CONFIDENCE" "0.25"
    append_env_if_missing ".env" "TOP_OVERLAY_MASK_FEATHER" "1"
    append_env_if_missing ".env" "TOP_OVERLAY_MASK_STRIDE" "1"
    append_env_if_missing ".env" "TOP_OVERLAY_CROP_BIAS_Y" "0.08"
    append_env_if_missing ".env" "TOP_OVERLAY_SPEAKER_MASK_MODE" "dual_auto"
    append_env_if_missing ".env" "TOP_OVERLAY_SMART_CROP" "true"
    append_env_if_missing ".env" "TOP_OVERLAY_SMART_CROP_CONF" "0.18"
    append_env_if_missing ".env" "BROLL_SPLICE_ENABLED" "true"
    append_env_if_missing ".env" "ASSET_FETCH_ENABLED" "true"
    append_env_if_missing ".env" "USE_REMOTION" "true"
    append_env_if_missing ".env" "FORCE_V2_PIPELINE" "true"
    # HyperFrames polish (default OFF — Remotion owns hook/subtitle)
    append_env_if_missing ".env" "HYPERFRAMES_ENABLED" "false"
    append_env_if_missing ".env" "HYPERFRAMES_SERVER_URL" "http://127.0.0.1:$HYPERFRAMES_PORT"
    append_env_if_missing ".env" "HYPERFRAMES_SERVER_PORT" "$HYPERFRAMES_PORT"
    append_env_if_missing ".env" "HYPERFRAMES_PROJECT_PATH" "../hyperframes-renderer"
    append_env_if_missing ".env" "HYPERFRAMES_TIMEOUT" "180"
    append_env_if_missing ".env" "HYPERFRAMES_DEFAULT_TEMPLATE" "lower_third_v1"
    append_env_if_missing ".env" "HERMES_ENABLED" "true"
    append_env_if_missing ".env" "HERMES_BIN" "hermes"
    append_env_if_missing ".env" "HERMES_HOME" "$HERMES_HOME_DEPLOY"
    # Object image+text overlay (AI visual entities → stock photo card)
    append_env_if_missing ".env" "OBJECT_OVERLAY_ENABLED" "true"
    append_env_if_missing ".env" "OBJECT_OVERLAY_MAX_PER_CLIP" "3"
    append_env_if_missing ".env" "OBJECT_OVERLAY_BOX_SIZE" "0.28"
    append_env_if_missing ".env" "OBJECT_OVERLAY_CORNER_RADIUS" "18"
    append_env_if_missing ".env" "OBJECT_OVERLAY_POSITION" "top_right"
    append_env_if_missing ".env" "OBJECT_OVERLAY_ANIMATION" "slide_right"
    append_env_if_missing ".env" "OBJECT_OVERLAY_DURATION" "2.4"
    append_env_if_missing ".env" "OBJECT_OVERLAY_MIN_RELEVANCE" "0.35"
    append_env_if_missing ".env" "OBJECT_OVERLAY_SHOW_LABEL" "true"
fi

# Ensure music assets dir exists (AudioMixer duck bed)
mkdir -p "$BACKEND_DIR/assets/music"
if [ -z "$(ls -A "$BACKEND_DIR/assets/music" 2>/dev/null)" ]; then
    echo "  ⚠️  assets/music empty — music bed will skip until files added (non-fatal)"
else
    echo "  ✅ Music beds present ($(ls "$BACKEND_DIR/assets/music" | wc -l | tr -d ' ') file(s))"
fi

# Bootstrap DB schema if missing (init_db also runs on app start)
echo "  Ensuring SQLite schema..."
./venv/bin/python -c "
import asyncio, sys, os
sys.path.insert(0, '$BACKEND_DIR')
os.chdir('$BACKEND_DIR')
async def main():
    from src.infrastructure.database import init_db
    await init_db()
    print('  ✅ DB schema ready')
asyncio.run(main())
" 2>&1 | sed 's/^/  /' || echo "  ⚠️  DB bootstrap deferred to app startup"

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
        print(f'  ⚠️  RF-DETR download failed: {e2}')
        print('  Will fallback to Ultralytics YOLO at runtime')
" 2>&1 || echo "  ⚠️  RF-DETR pre-download skipped (non-fatal)"

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
" 2>&1 || echo "  ⚠️  RetinaFace pre-download skipped (non-fatal)"

# Ultralytics YOLO — pre-download for tracker fallback + person detection fallback
echo "  Checking YOLO11n model (tracker fallback)..."
if [ ! -f "models/yolo11n.pt" ]; then
    ./venv/bin/python3 -c "
from ultralytics import YOLO
import shutil, os
model = YOLO('yolo11n.pt')
# Move to models/ dir if downloaded to cwd
if os.path.exists('yolo11n.pt') and not os.path.exists('models/yolo11n.pt'):
    shutil.move('yolo11n.pt', 'models/yolo11n.pt')
print('  YOLO11n: ready')
" 2>&1 || echo "  ⚠️  YOLO11n download skipped"
else
    echo "  YOLO11n: already present"
fi

# YOLO11n-seg — for text-behind-person effect (existing feature)
echo "  Checking YOLO11n-seg model..."
if [ ! -f "models/yolo11n-seg.pt" ]; then
    ./venv/bin/python3 -c "
from ultralytics import YOLO
import shutil, os
model = YOLO('yolo11n-seg.pt')
if os.path.exists('yolo11n-seg.pt') and not os.path.exists('models/yolo11n-seg.pt'):
    shutil.move('yolo11n-seg.pt', 'models/yolo11n-seg.pt')
print('  YOLO11n-seg: ready')
" 2>&1 || echo "  ⚠️  YOLO11n-seg download skipped"
else
    echo "  YOLO11n-seg: already present"
fi

echo "  ✅ Models provisioned"

# ─── Step 3.5: Optional cache clear ──────────────────────────────────────────
echo ""
if [ "$CLEAR_AI_CACHE_ON_DEPLOY" = "1" ]; then
    echo "  Clearing cached transcripts & analysis..."
    rm -rf "$BACKEND_DIR/tmp/cache/"*/transcript*.json 2>/dev/null || true
    rm -rf "$BACKEND_DIR/tmp/cache/"*/analysis*.json 2>/dev/null || true
    echo "  ✅ Cache cleared (transcripts + analysis)"
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
        echo "  ✅ npm dependencies up to date"
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
    echo "  ✅ Remotion ready (will re-bundle on service start)"
else
    echo "  ⚠️  Remotion directory not found at $REMOTION_DIR"
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
        echo "  ✅ HyperFrames npm dependencies up to date"
    fi
    mkdir -p "$HYPERFRAMES_DIR/work"
    chown -R $DEPLOY_USER:$DEPLOY_USER "$HYPERFRAMES_DIR" 2>/dev/null || true
    # Sanity: assembler loads
    node -e "import('./src/assemble.mjs').then(m => console.log('templates', m.listTemplates().join(',')))" \
        || echo "  ⚠️  HyperFrames assembler check failed (non-fatal until service start)"
    echo "  ✅ HyperFrames renderer ready (polish only; hook+subtitle = Remotion)"
else
    echo "  ⚠️  HyperFrames directory not found at $HYPERFRAMES_DIR"
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
    echo "  ✅ Hermes config synced → $HERMES_HOME_DEPLOY"
else
    echo "  ⚠️  scripts/sync-hermes-config.sh missing"
fi
if command -v hermes &>/dev/null; then
    echo "  ✅ hermes binary: $(command -v hermes)"
else
    echo "  ℹ️  hermes not on PATH — optional install:"
    echo "     curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
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
        echo "  ✅ npm dependencies up to date"
    fi

    echo "  Type-checking and building production bundle..."
    VITE_API_URL="$PUBLIC_BACKEND_URL" npm run build

    if [ -d "dist" ] && [ -f "dist/index.html" ]; then
        echo "  ✅ Frontend built"
    else
        echo "  ❌ Frontend build did not produce dist/index.html"
        exit 1
    fi

    # Install serve globally for static file serving
    if ! command -v serve &>/dev/null; then
        echo "  Installing serve..."
        npm install -g serve 2>/dev/null || true
    fi
else
    echo "  ⚠️  Frontend directory not found at $FRONTEND_DIR"
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
ExecStart=$BACKEND_DIR/venv/bin/python -m uvicorn src.presentation.api:app --host 0.0.0.0 --port $BACKEND_PORT --workers 4
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
    echo "  ⚠️  9router binary not found — skipping autocliper-9router.service"
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
    echo "  ✅ autocliper-hyperframes.service written"
else
    echo "  ⚠️  HyperFrames server missing — skipping autocliper-hyperframes.service"
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

# Reload and restart (Remotion FIRST — must be ready before backend)
sudo systemctl daemon-reload
sudo systemctl enable autocliper-9router autocliper-backend autocliper-remotion autocliper-hyperframes autocliper-frontend 2>/dev/null || true

# Start Remotion first and wait for bundle to be ready
echo "  Stopping services (cleanup stale ports)..."
sudo systemctl stop autocliper-9router 2>/dev/null || true
sudo systemctl stop autocliper-remotion 2>/dev/null || true
sudo systemctl stop autocliper-hyperframes 2>/dev/null || true
sudo systemctl stop autocliper-backend 2>/dev/null || true
sudo systemctl stop autocliper-frontend 2>/dev/null || true
sleep 2

echo "  Starting 9router..."
sudo systemctl start autocliper-9router 2>/dev/null || true
NINE_ROUTER_READY=0
for i in $(seq 1 40); do
    if curl -s "http://$NINE_ROUTER_HOST:$NINE_ROUTER_PORT" >/dev/null 2>&1; then
        NINE_ROUTER_READY=1
        echo "  ✅ 9router ready (${i}s)"
        break
    fi
    sleep 1
done
if [ $NINE_ROUTER_READY -eq 0 ]; then
    echo "  ⚠️  9router not responding yet — check logs: sudo journalctl -u autocliper-9router -n 30"
fi

echo "  Starting Remotion server (bundling compositions)..."
sudo systemctl start autocliper-remotion
REMOTION_READY=0
for i in $(seq 1 60); do
    if curl -s "http://localhost:$REMOTION_PORT/health" 2>/dev/null | grep -q "healthy"; then
        REMOTION_READY=1
        echo "  ✅ Remotion bundled and ready (${i}s)"
        break
    fi
    sleep 1
done
if [ $REMOTION_READY -eq 0 ]; then
    echo "  ⚠️  Remotion not ready after 60s — check logs: sudo journalctl -u autocliper-remotion -n 30"
fi

echo "  Starting HyperFrames polish server..."
sudo systemctl start autocliper-hyperframes 2>/dev/null || true
HF_READY=0
for i in $(seq 1 30); do
    if curl -s "http://localhost:$HYPERFRAMES_PORT/health" 2>/dev/null | grep -q "healthy"; then
        HF_READY=1
        echo "  ✅ HyperFrames ready (${i}s)"
        break
    fi
    sleep 1
done
if [ $HF_READY -eq 0 ]; then
    echo "  ⚠️  HyperFrames not ready — check: sudo journalctl -u autocliper-hyperframes -n 30"
fi

# Now restart backend (Remotion is ready to handle render requests)
sudo systemctl start autocliper-backend
sudo systemctl start autocliper-frontend

echo "  ✅ All services registered and started"

# ─── Step 7: Nginx (optional — only if nginx is installed) ──────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 7: Nginx Reverse Proxy (optional)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if command -v nginx &>/dev/null; then
    if [ ! -f "/etc/nginx/sites-available/autocliper" ]; then
        sudo tee /etc/nginx/sites-available/autocliper > /dev/null << 'EOF'
server {
    listen 80;
    server_name autocliper.local _;

    # Security: block .git exposure
    location ~ /\.git {
        deny all;
        return 404;
    }

    # Frontend
    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
        client_max_body_size 500M;
    }

    # Backend health
    location /health {
        proxy_pass http://127.0.0.1:8000;
    }

    # Video files (large responses)
    location ~* /api/jobs/.*/clips/.*/(?:final|raw|thumb) {
        proxy_pass http://127.0.0.1:8000;
        proxy_read_timeout 600s;
        proxy_buffering off;
    }
}
EOF
        sudo ln -sf /etc/nginx/sites-available/autocliper /etc/nginx/sites-enabled/ 2>/dev/null
        sudo nginx -t 2>/dev/null && sudo systemctl reload nginx 2>/dev/null
        echo "  ✅ Nginx configured"
    else
        echo "  ✅ Nginx config already exists"
    fi
else
    echo "  ⚠️  Nginx not installed — access services directly via ports"
fi

# ─── Step 8: Health Check ────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 8: Health Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

sleep 4

check_service() {
    if sudo systemctl is-active --quiet "$1" 2>/dev/null; then
        echo "  ✅ $1 — RUNNING (port $2)"
    else
        echo "  ❌ $1 — FAILED"
        echo "     → sudo journalctl -u $1 -n 15 --no-pager"
    fi
}

check_service "autocliper-backend" "$BACKEND_PORT"
check_service "autocliper-9router" "$NINE_ROUTER_PORT"
check_service "autocliper-remotion" "$REMOTION_PORT"
check_service "autocliper-hyperframes" "$HYPERFRAMES_PORT"
check_service "autocliper-frontend" "$FRONTEND_PORT"

# API health check
if curl -s "http://localhost:$BACKEND_PORT/health" | grep -q "ok" 2>/dev/null; then
    echo "  ✅ Backend API responding"
else
    echo "  ⚠️  Backend API not responding yet (may still be starting)"
fi

if curl -s "http://localhost:$HYPERFRAMES_PORT/health" 2>/dev/null | grep -q "healthy"; then
    echo "  ✅ HyperFrames API responding"
else
    echo "  ⚠️  HyperFrames API not responding"
fi

# Zero-touch readiness (no manual DB/.env after deploy)
echo ""
echo "  Production readiness:"
if [ -f "$BACKEND_DIR/.env" ]; then
    for k in TOP_OVERLAY_ENABLED TOP_OVERLAY_PERSON_OUTLINE TOP_OVERLAY_SMART_CROP USE_REMOTION FORCE_V2_PIPELINE HYPERFRAMES_SERVER_URL HERMES_ENABLED; do
        if grep -q "^${k}=" "$BACKEND_DIR/.env" 2>/dev/null; then
            echo "  ✅ .env has $k"
        else
            echo "  ⚠️  .env missing $k (append_env should have set it — re-run deploy)"
        fi
    done
fi
if [ -f "$HERMES_HOME_DEPLOY/config.yaml" ]; then
    echo "  ✅ Hermes config at $HERMES_HOME_DEPLOY/config.yaml"
else
    echo "  ⚠️  Hermes config missing — run scripts/sync-hermes-config.sh"
fi
if [ -d "$BACKEND_DIR/assets/music" ]; then
    echo "  ✅ assets/music ready"
else
    echo "  ⚠️  assets/music missing"
fi
if [ -f "$BACKEND_DIR/data/autocliper.db" ] || [ -f "$BACKEND_DIR/data/autoclip.db" ] || [ -f "$BACKEND_DIR/autocliper.db" ] || ls "$BACKEND_DIR"/data/*.db >/dev/null 2>&1; then
    echo "  ✅ SQLite DB present"
else
    echo "  ℹ️  SQLite path may be under DATA_DIR — app init_db handles create"
fi

# ─── Done ────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ Deployment Complete!"
echo ""
echo "  Services:"
echo "    9router:      http://127.0.0.1:$NINE_ROUTER_PORT"
echo "    Backend:      $PUBLIC_BACKEND_URL"
echo "    Remotion:     http://$PUBLIC_HOST:$REMOTION_PORT   (hook+subtitle)"
echo "    HyperFrames:  http://$PUBLIC_HOST:$HYPERFRAMES_PORT  (polish)"
echo "    Frontend:     $PUBLIC_FRONTEND_URL"
echo "    Hermes home:  $HERMES_HOME_DEPLOY"
echo ""
echo "  Open:"
echo "    $PUBLIC_FRONTEND_URL"
echo ""
echo "  Logs:"
echo "    sudo journalctl -u autocliper-9router -f"
echo "    sudo journalctl -u autocliper-backend -f"
echo "    sudo journalctl -u autocliper-remotion -f"
echo "    sudo journalctl -u autocliper-hyperframes -f"
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
