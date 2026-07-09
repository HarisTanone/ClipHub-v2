#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUTPUT="${1:-$PROJECT_DIR/autocliper-runtime-$STAMP.tar.gz}"

cd "$PROJECT_DIR"

mkdir -p backend/data backend/tmp/output backend/tmp/downloads

if command -v sqlite3 >/dev/null 2>&1 && [ -f backend/data/autoclip.db ]; then
    sqlite3 backend/data/autoclip.db "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null 2>&1 || true
fi

INCLUDES=(
    "backend/data"
    "backend/tmp"
)

if [ -f backend/.env ]; then
    INCLUDES+=("backend/.env")
fi

tar -czf "$OUTPUT" \
    --exclude='backend/tmp/**/*.part' \
    --exclude='backend/tmp/**/*.tmp' \
    "${INCLUDES[@]}"

chmod 600 "$OUTPUT" 2>/dev/null || true

echo "Created runtime archive: $OUTPUT"
echo "This archive may contain secrets from backend/.env. Keep it private."
