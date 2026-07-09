#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ARCHIVE="${1:-}"

if [ -z "$ARCHIVE" ]; then
    echo "Usage: scripts/restore-runtime-data.sh /path/to/autocliper-runtime.tar.gz"
    exit 1
fi

if [ ! -f "$ARCHIVE" ]; then
    echo "Archive not found: $ARCHIVE"
    exit 1
fi

cd "$PROJECT_DIR"

mkdir -p backend/data backend/tmp/output backend/tmp/downloads
tar -xzf "$ARCHIVE" -C "$PROJECT_DIR"

if [ -f backend/.env ]; then
    chmod 600 backend/.env 2>/dev/null || true
fi

echo "Runtime data restored into: $PROJECT_DIR"
echo "Run ./deploy.sh after checking backend/.env on the server."
