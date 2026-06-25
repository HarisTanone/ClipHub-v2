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
#   4. Remotion server setup (Node.js, npm install)
#   5. Frontend build (Vite production build)
#   6. Systemd services (auto-restart, boot-enabled)
#   7. Nginx reverse proxy (optional)
#   8. Health check
#
# Services & Ports:
#   - Backend (FastAPI/Uvicorn)    → :8000
#   - Remotion (Node.js/Express)   → :3002
#   - Frontend (static/serve)      → :3001
#
# Designed to be idempotent — safe to run multiple times.
# Second run is fast because it skips already-installed components.
# ═══════════════════════════════════════════════════════════════════════════════

set -e
export DEBIAN_FRONTEND=noninteractive

# ─── Configuration ───────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
REMOTION_DIR="$BACKEND_DIR/remotion-renderer"
FRONTEND_DIR="$PROJECT_DIR/frontend"
DEPLOY_USER="${SUDO_USER:-$(whoami)}"
PYTHON_BIN="python3"

# Ports (avoiding conflicts with existing services)
BACKEND_PORT=8000
REMOTION_PORT=3002
FRONTEND_PORT=3001

echo "═══════════════════════════════════════════════════════════════"
echo "  AutoCliper v3 — Server Deployment"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  Project:  $PROJECT_DIR"
echo "  User:     $DEPLOY_USER"
echo "  Python:   $($PYTHON_BIN --version 2>/dev/null || echo 'not found')"
echo "  Node:     $(node --version 2>/dev/null || echo 'not found')"
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

    # Chromium deps for Remotion headless rendering
    sudo apt-get install -y --no-install-recommends \
        libnss3 libatk-bridge2.0-0t64 libdrm2 libxcomposite1 \
        libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
        libasound2t64 libxshmfence1 2>/dev/null || true

    echo "  ✅ System packages installed"
fi

echo "  Python: $($PYTHON_BIN --version 2>/dev/null)"
echo "  Node:   $(node --version 2>/dev/null)"
echo "  FFmpeg: $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3)"

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
./venv/bin/pip install --upgrade pip -q 2>/dev/null
./venv/bin/pip install -r requirements.txt -q 2>/dev/null || \
    ./venv/bin/pip install -r requirements.txt

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

# Create directories
mkdir -p tmp/output tmp/downloads

echo "  ✅ Backend ready"

# ─── Step 4: Remotion Server ────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 4: Remotion Server (Node.js — port $REMOTION_PORT)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "$REMOTION_DIR" ]; then
    cd "$REMOTION_DIR"

    if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules/.package-lock.json" ]; then
        echo "  Installing npm dependencies..."
        npm install --omit=dev 2>/dev/null || npm install
    else
        echo "  ✅ npm dependencies up to date"
    fi

    echo "  ✅ Remotion ready"
else
    echo "  ⚠️  Remotion directory not found at $REMOTION_DIR"
fi

# ─── Step 5: Frontend Build ─────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 5: Frontend Build (Vite — port $FRONTEND_PORT)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "$FRONTEND_DIR" ]; then
    cd "$FRONTEND_DIR"

    if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules/.package-lock.json" ]; then
        echo "  Installing npm dependencies..."
        npm install 2>/dev/null || npm install
    else
        echo "  ✅ npm dependencies up to date"
    fi

    echo "  Building production bundle..."
    npx vite build 2>/dev/null || npx vite build

    if [ -d "dist" ] && [ -f "dist/index.html" ]; then
        echo "  ✅ Frontend built"
    else
        echo "  ⚠️  Frontend build may have failed"
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
Environment=PATH=$BACKEND_DIR/venv/bin:/usr/local/bin:/usr/bin
ExecStart=$BACKEND_DIR/venv/bin/python -m uvicorn src.presentation.api:app --host 0.0.0.0 --port $BACKEND_PORT --workers 4
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

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
ExecStart=/usr/bin/npx tsx src/server/index.ts
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Frontend service
sudo tee /etc/systemd/system/autocliper-frontend.service > /dev/null << EOF
[Unit]
Description=AutoCliper Frontend (Static)
After=network.target

[Service]
Type=simple
User=$DEPLOY_USER
WorkingDirectory=$FRONTEND_DIR
ExecStart=/usr/bin/npx --yes serve dist -l $FRONTEND_PORT -s --no-clipboard
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl enable autocliper-backend autocliper-remotion autocliper-frontend 2>/dev/null || true
sudo systemctl restart autocliper-backend
sudo systemctl restart autocliper-remotion
sudo systemctl restart autocliper-frontend

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
check_service "autocliper-remotion" "$REMOTION_PORT"
check_service "autocliper-frontend" "$FRONTEND_PORT"

# API health check
if curl -s "http://localhost:$BACKEND_PORT/health" | grep -q "ok" 2>/dev/null; then
    echo "  ✅ Backend API responding"
else
    echo "  ⚠️  Backend API not responding yet (may still be starting)"
fi

# ─── Done ────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ Deployment Complete!"
echo ""
echo "  Services:"
echo "    Backend:   http://192.168.168.58:$BACKEND_PORT"
echo "    Remotion:  http://192.168.168.58:$REMOTION_PORT"
echo "    Frontend:  http://192.168.168.58:$FRONTEND_PORT"
echo ""
echo "  Logs:"
echo "    sudo journalctl -u autocliper-backend -f"
echo "    sudo journalctl -u autocliper-remotion -f"
echo "    sudo journalctl -u autocliper-frontend -f"
echo ""
echo "  Management:"
echo "    sudo systemctl status autocliper-backend"
echo "    sudo systemctl restart autocliper-backend"
echo "    sudo systemctl stop autocliper-backend"
echo ""
echo "  Next run will be fast (skips installed components)."
echo "═══════════════════════════════════════════════════════════════"
