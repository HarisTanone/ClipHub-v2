#!/usr/bin/env bash
set -euo pipefail

ARCHIVE="${1:-}"
NINE_ROUTER_DIR="${NINE_ROUTER_DIR:-$HOME/.9router}"

if [ -z "$ARCHIVE" ]; then
    echo "Usage: scripts/restore-9router-data.sh /path/to/9router-data.tar.gz"
    exit 1
fi

if [ ! -f "$ARCHIVE" ]; then
    echo "Archive not found: $ARCHIVE"
    exit 1
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

tar -xzf "$ARCHIVE" -C "$TMP_DIR"

if [ -f "$TMP_DIR/9router-restore-manifest.env" ]; then
    # shellcheck disable=SC1091
    source "$TMP_DIR/9router-restore-manifest.env"
fi

NINE_ROUTER_CLI_VERSION="${NINE_ROUTER_CLI_VERSION:-0.5.20}"

if ! command -v npm >/dev/null 2>&1; then
    echo "npm not found. Install Node.js/npm first, then rerun this script."
    exit 1
fi

echo "Installing 9router@$NINE_ROUTER_CLI_VERSION if needed..."
if command -v 9router >/dev/null 2>&1; then
    npm install -g "9router@$NINE_ROUTER_CLI_VERSION" --prefer-online >/dev/null 2>&1 || \
        sudo npm install -g "9router@$NINE_ROUTER_CLI_VERSION" --prefer-online
else
    npm install -g "9router@$NINE_ROUTER_CLI_VERSION" --prefer-online || \
        sudo npm install -g "9router@$NINE_ROUTER_CLI_VERSION" --prefer-online
fi

if [ -d "$NINE_ROUTER_DIR" ]; then
    BACKUP="${NINE_ROUTER_DIR}.backup.$(date +%Y%m%d-%H%M%S)"
    echo "Existing 9router data found. Backing up to: $BACKUP"
    mv "$NINE_ROUTER_DIR" "$BACKUP"
fi

mkdir -p "$(dirname "$NINE_ROUTER_DIR")"
cp -R "$TMP_DIR/.9router" "$NINE_ROUTER_DIR"
chmod 700 "$NINE_ROUTER_DIR" 2>/dev/null || true
chmod 600 "$NINE_ROUTER_DIR"/jwt-secret "$NINE_ROUTER_DIR"/machine-id "$NINE_ROUTER_DIR"/auth/cli-secret 2>/dev/null || true

echo "9router data restored to: $NINE_ROUTER_DIR"
echo "Base URL for backend: ${NINE_ROUTER_BASE_URL:-http://127.0.0.1:20128/v1}"
echo "Run ./deploy.sh to install/start the 9router systemd service."
