#!/usr/bin/env bash
# Setup dan deploy Telegram Bot untuk AutoCliper
#
# Usage:
#   ./scripts/setup-telegram-bot.sh
#
# Prerequisites:
#   - HERMES_HOME tersedia (default ~/.hermes)
#   - TELEGRAM_BOT_TOKEN di $HERMES_HOME/.env
#   - TELEGRAM_ALLOWED_USERS di $HERMES_HOME/.env
#   - Python 3.11+ dengan venv support
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BOT_DIR="$PROJECT_DIR/ops/telegram"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
DEPLOY_USER="${SUDO_USER:-$(whoami)}"
VENV_DIR="$BOT_DIR/venv"
SERVICE_NAME="autocliper-telegram-bot"

echo "═══════════════════════════════════════════════════════════════"
echo "  AutoCliper Telegram Bot — Setup"
echo "═══════════════════════════════════════════════════════════════"
echo "  Bot dir   : $BOT_DIR"
echo "  HERMES_HOME: $HERMES_HOME"
echo "  User      : $DEPLOY_USER"
echo ""

# ─── 1. Pastikan HERMES_HOME/.env ada ────────────────────────────────────────
if [ ! -f "$HERMES_HOME/.env" ]; then
    echo "  ⚠️  $HERMES_HOME/.env tidak ditemukan"
    echo "  Jalankan scripts/sync-hermes-config.sh terlebih dahulu"
    exit 1
fi

# ─── 2. Validasi token ────────────────────────────────────────────────────────
BOT_TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$HERMES_HOME/.env" 2>/dev/null | cut -d'=' -f2- | tr -d '"'"'")"
if [ -z "$BOT_TOKEN" ]; then
    echo ""
    echo "  ❌ TELEGRAM_BOT_TOKEN belum di-set!"
    echo ""
    echo "  Cara mendapatkan token:"
    echo "    1. Buka Telegram, cari @BotFather"
    echo "    2. Kirim /newbot, ikuti instruksi"
    echo "    3. Copy token yang diberikan"
    echo "    4. Tambahkan ke $HERMES_HOME/.env:"
    echo "       TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHI..."
    echo ""
    echo "  Cara mendapat Telegram User ID:"
    echo "    1. Kirim pesan ke @userinfobot"
    echo "    2. Atau jalankan bot dulu, kirim /myid"
    echo "    3. Tambahkan ke $HERMES_HOME/.env:"
    echo "       TELEGRAM_ALLOWED_USERS=123456789,987654321"
    echo ""
    exit 1
fi
echo "  ✅ TELEGRAM_BOT_TOKEN ditemukan"

# ─── 3. Install Python venv untuk bot ────────────────────────────────────────
echo ""
echo "  Installing Python dependencies..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$BOT_DIR/requirements.txt" -q
echo "  ✅ Dependencies installed"

# ─── 4. Sync hermes config + toolset ────────────────────────────────────────
echo ""
echo "  Syncing Hermes config + AutoCliper toolset..."
if [ -x "$PROJECT_DIR/scripts/sync-hermes-config.sh" ]; then
    HERMES_HOME="$HERMES_HOME" bash "$PROJECT_DIR/scripts/sync-hermes-config.sh"
else
    echo "  ⚠️  sync-hermes-config.sh tidak ditemukan"
fi

# ─── 5. Systemd service ──────────────────────────────────────────────────────
echo ""
echo "  Installing systemd service: $SERVICE_NAME"

# Deteksi apakah running sebagai root
if [ "$(id -u)" -eq 0 ]; then
    SYSTEMD_DIR="/etc/systemd/system"
    SYSTEMD_SCOPE="system"
else
    SYSTEMD_DIR="$HOME/.config/systemd/user"
    SYSTEMD_SCOPE="user"
    mkdir -p "$SYSTEMD_DIR"
fi

PYTHON_BIN="$VENV_DIR/bin/python3"
BOT_SCRIPT="$BOT_DIR/telegram_bot.py"

cat > "$SYSTEMD_DIR/$SERVICE_NAME.service" << EOF
[Unit]
Description=AutoCliper Telegram Bot
After=network.target autocliper-backend.service
Wants=autocliper-backend.service

[Service]
Type=simple
User=$DEPLOY_USER
WorkingDirectory=$BOT_DIR
EnvironmentFile=-$BACKEND_DIR/.env
Environment=HERMES_HOME=$HERMES_HOME
Environment=AUTOCLIPER_API_URL=http://127.0.0.1:8000/api
ExecStart=$PYTHON_BIN $BOT_SCRIPT
Restart=always
RestartSec=10
TimeoutStopSec=15
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

[Install]
WantedBy=multi-user.target
EOF

echo "  ✅ Service file: $SYSTEMD_DIR/$SERVICE_NAME.service"

# ─── 6. Enable + start service ───────────────────────────────────────────────
if [ "$(id -u)" -eq 0 ]; then
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl restart "$SERVICE_NAME"
    sleep 2
    systemctl status "$SERVICE_NAME" --no-pager || true
else
    systemctl --user daemon-reload
    systemctl --user enable "$SERVICE_NAME"
    systemctl --user restart "$SERVICE_NAME"
    sleep 2
    systemctl --user status "$SERVICE_NAME" --no-pager || true
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ AutoCliper Telegram Bot berhasil di-deploy!"
echo ""
echo "  Cek log : journalctl -u $SERVICE_NAME -f"
echo "  Restart : systemctl restart $SERVICE_NAME"
echo "  Stop    : systemctl stop $SERVICE_NAME"
echo ""
echo "  Selanjutnya:"
echo "    1. Buka bot di Telegram, kirim /start"
echo "    2. Kirim /myid untuk dapat User ID kamu"
echo "    3. Tambahkan ID ke TELEGRAM_ALLOWED_USERS di $HERMES_HOME/.env"
echo "    4. Restart bot: systemctl restart $SERVICE_NAME"
echo "═══════════════════════════════════════════════════════════════"
