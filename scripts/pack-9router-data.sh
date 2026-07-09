#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUTPUT="${1:-$PROJECT_DIR/9router-data-$STAMP.tar.gz}"
NINE_ROUTER_DIR="${NINE_ROUTER_DIR:-$HOME/.9router}"

if [ ! -d "$NINE_ROUTER_DIR" ]; then
    echo "9router data directory not found: $NINE_ROUTER_DIR"
    exit 1
fi

PACKAGE_JSON=""
if command -v 9router >/dev/null 2>&1; then
    BIN_PATH="$(command -v 9router)"
    BIN_TARGET="$(readlink "$BIN_PATH" 2>/dev/null || true)"
    if [ -n "$BIN_TARGET" ]; then
        PACKAGE_DIR="$(cd "$(dirname "$BIN_PATH")" && cd "$(dirname "$BIN_TARGET")" && pwd)"
    else
        PACKAGE_DIR="$(cd "$(dirname "$BIN_PATH")/../lib/node_modules/9router" 2>/dev/null && pwd || true)"
    fi
    if [ -f "$PACKAGE_DIR/package.json" ]; then
        PACKAGE_JSON="$PACKAGE_DIR/package.json"
    fi
fi

VERSION="0.5.20"
if [ -n "$PACKAGE_JSON" ]; then
    VERSION="$(node -e "console.log(require(process.argv[1]).version)" "$PACKAGE_JSON")"
fi

if command -v sqlite3 >/dev/null 2>&1 && [ -f "$NINE_ROUTER_DIR/db/data.sqlite" ]; then
    sqlite3 "$NINE_ROUTER_DIR/db/data.sqlite" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null 2>&1 || true
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p "$TMP_DIR/.9router"

for name in db auth mitm jwt-secret machine-id; do
    if [ -e "$NINE_ROUTER_DIR/$name" ]; then
        cp -R "$NINE_ROUTER_DIR/$name" "$TMP_DIR/.9router/"
    fi
done

cat > "$TMP_DIR/9router-restore-manifest.env" <<EOF
NINE_ROUTER_CLI_VERSION=$VERSION
NINE_ROUTER_PORT=20128
NINE_ROUTER_HOST=127.0.0.1
NINE_ROUTER_BASE_URL=http://127.0.0.1:20128/v1
EOF

tar -czf "$OUTPUT" -C "$TMP_DIR" .
chmod 600 "$OUTPUT" 2>/dev/null || true

echo "Created 9router archive: $OUTPUT"
echo "Included 9router CLI version: $VERSION"
echo "This archive contains 9router database/secrets. Keep it private."
