#!/usr/bin/env bash
# Restore Hermes home from pack-hermes-data.sh archive.
set -euo pipefail

ARCHIVE="${1:-}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

if [ -z "$ARCHIVE" ] || [ ! -f "$ARCHIVE" ]; then
  echo "Usage: scripts/restore-hermes-data.sh /path/to/hermes-data.tar.gz"
  exit 1
fi

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

tar -xzf "$ARCHIVE" -C "$TMP_DIR"

if [ -d "$HERMES_HOME" ]; then
  BACKUP="${HERMES_HOME}.backup.$(date +%Y%m%d-%H%M%S)"
  echo "Backing up existing Hermes → $BACKUP"
  mv "$HERMES_HOME" "$BACKUP"
fi

mkdir -p "$(dirname "$HERMES_HOME")"
if [ -d "$TMP_DIR/.hermes" ]; then
  cp -R "$TMP_DIR/.hermes" "$HERMES_HOME"
else
  echo "Archive missing .hermes/"
  exit 1
fi
chmod 700 "$HERMES_HOME" 2>/dev/null || true
chmod 600 "$HERMES_HOME/.env" "$HERMES_HOME/auth.json" 2>/dev/null || true

echo "Hermes restored → $HERMES_HOME"
echo "Ensure 9router is running on 127.0.0.1:20128"
echo "Re-sync from repo (optional): scripts/sync-hermes-config.sh"
