#!/usr/bin/env bash
# Pack Hermes home (config + skills + non-secret state) for server restore.
# Secrets (.env, auth.json) included — keep archive private.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUTPUT="${1:-$PROJECT_DIR/hermes-data-$STAMP.tar.gz}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

if [ ! -d "$HERMES_HOME" ]; then
  echo "HERMES_HOME not found: $HERMES_HOME"
  exit 1
fi

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

mkdir -p "$TMP_DIR/.hermes"
# Include config, skills, SOUL, memories, plugins list — skip huge caches
for name in config.yaml .env auth.json SOUL.md skills memories plugins cron; do
  if [ -e "$HERMES_HOME/$name" ]; then
    cp -R "$HERMES_HOME/$name" "$TMP_DIR/.hermes/"
  fi
done

# Prefer project ops config as source of truth if present
if [ -f "$PROJECT_DIR/ops/hermes/config.yaml" ]; then
  cp "$PROJECT_DIR/ops/hermes/config.yaml" "$TMP_DIR/.hermes/config.yaml"
fi

cat > "$TMP_DIR/hermes-restore-manifest.env" <<EOF
HERMES_HOME_DEFAULT=\$HOME/.hermes
NINE_ROUTER_BASE_URL=http://127.0.0.1:20128/v1
EOF

tar -czf "$OUTPUT" -C "$TMP_DIR" .
chmod 600 "$OUTPUT" 2>/dev/null || true
echo "Created hermes archive: $OUTPUT"
echo "Contains secrets (.env/auth). Keep private."
