#!/usr/bin/env bash
# Sync project Hermes config → $HERMES_HOME (local and server identical).
# Usage:
#   scripts/sync-hermes-config.sh           # install into ~/.hermes or $HERMES_HOME
#   HERMES_HOME=/opt/autocliper/hermes scripts/sync-hermes-config.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_CFG="$PROJECT_DIR/ops/hermes/config.yaml"
SRC_ENV_EX="$PROJECT_DIR/ops/hermes/env.example"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

mkdir -p "$HERMES_HOME" "$HERMES_HOME/skills" "$HERMES_HOME/skills/bin" "$HERMES_HOME/cron" "$HERMES_HOME/memories"

if [ ! -f "$SRC_CFG" ]; then
  echo "Missing $SRC_CFG"
  exit 1
fi

# Backup existing config once per run
if [ -f "$HERMES_HOME/config.yaml" ]; then
  cp "$HERMES_HOME/config.yaml" "$HERMES_HOME/config.yaml.bak.$(date +%Y%m%d-%H%M%S)"
fi

cp "$SRC_CFG" "$HERMES_HOME/config.yaml"
echo "Hermes config → $HERMES_HOME/config.yaml"

# ─── AutoCliper custom toolset ────────────────────────────────────────────────
SRC_TOOLSET="$PROJECT_DIR/ops/hermes/autocliper_tools.yaml"
SRC_BIN_DIR="$PROJECT_DIR/ops/hermes/bin"
DEST_TOOLSET="$HERMES_HOME/skills/autocliper_tools.yaml"
DEST_BIN_DIR="$HERMES_HOME/skills/bin"

if [ -f "$SRC_TOOLSET" ]; then
  cp "$SRC_TOOLSET" "$DEST_TOOLSET"
  echo "AutoCliper toolset → $DEST_TOOLSET"
fi

if [ -d "$SRC_BIN_DIR" ]; then
  cp "$SRC_BIN_DIR"/ac_*.py "$DEST_BIN_DIR/" 2>/dev/null || true
  chmod +x "$DEST_BIN_DIR"/ac_*.py 2>/dev/null || true
  echo "AutoCliper tools ($(ls "$DEST_BIN_DIR"/ac_*.py 2>/dev/null | wc -l | tr -d ' ') scripts) → $DEST_BIN_DIR"
fi

# Seed .env only if missing (never overwrite secrets)
if [ ! -f "$HERMES_HOME/.env" ]; then
  if [ -f "$SRC_ENV_EX" ]; then
    cp "$SRC_ENV_EX" "$HERMES_HOME/.env"
    chmod 600 "$HERMES_HOME/.env" 2>/dev/null || true
    echo "Seeded $HERMES_HOME/.env from env.example — FILL API KEYS"
  fi
else
  # Ensure 9router base URL present
  if ! grep -qE '^OPENAI_BASE_URL=' "$HERMES_HOME/.env" 2>/dev/null; then
    echo 'OPENAI_BASE_URL=http://127.0.0.1:20128/v1' >> "$HERMES_HOME/.env"
  fi
  # Ensure AutoCliper API vars present (append-only, never overwrite)
  if ! grep -qE '^AUTOCLIPER_API_URL=' "$HERMES_HOME/.env" 2>/dev/null; then
    echo 'AUTOCLIPER_API_URL=http://127.0.0.1:8000/api' >> "$HERMES_HOME/.env"
  fi
  if ! grep -qE '^AUTOCLIPER_EMAIL=' "$HERMES_HOME/.env" 2>/dev/null; then
    echo 'AUTOCLIPER_EMAIL=' >> "$HERMES_HOME/.env"
    echo 'AUTOCLIPER_PASSWORD=' >> "$HERMES_HOME/.env"
    echo "  [WARN] Set AUTOCLIPER_EMAIL dan AUTOCLIPER_PASSWORD di $HERMES_HOME/.env"
  fi
  if ! grep -qE '^TELEGRAM_BOT_TOKEN=' "$HERMES_HOME/.env" 2>/dev/null; then
    echo '# Telegram Bot (dari @BotFather)' >> "$HERMES_HOME/.env"
    echo 'TELEGRAM_BOT_TOKEN=' >> "$HERMES_HOME/.env"
    echo 'TELEGRAM_ALLOWED_USERS=' >> "$HERMES_HOME/.env"
    echo "  [WARN] Set TELEGRAM_BOT_TOKEN di $HERMES_HOME/.env"
  fi
  # Sync public URLs from backend/.env if available
  if [ -f "$PROJECT_DIR/backend/.env" ]; then
    PUBLIC_BACKEND_VAL="$(grep -E '^PUBLIC_BACKEND_URL=' "$PROJECT_DIR/backend/.env" 2>/dev/null | tail -n 1 | cut -d'=' -f2- | tr -d '\"' | tr -d "'" || true)"
    if [ -n "$PUBLIC_BACKEND_VAL" ] && ! grep -qE '^PUBLIC_BACKEND_URL=' "$HERMES_HOME/.env" 2>/dev/null; then
      echo "PUBLIC_BACKEND_URL=$PUBLIC_BACKEND_VAL" >> "$HERMES_HOME/.env"
    fi
    PUBLIC_FRONTEND_VAL="$(grep -E '^PUBLIC_FRONTEND_URL=' "$PROJECT_DIR/backend/.env" 2>/dev/null | tail -n 1 | cut -d'=' -f2- | tr -d '\"' | tr -d "'" || true)"
    if [ -n "$PUBLIC_FRONTEND_VAL" ] && ! grep -qE '^PUBLIC_FRONTEND_URL=' "$HERMES_HOME/.env" 2>/dev/null; then
      echo "PUBLIC_FRONTEND_URL=$PUBLIC_FRONTEND_VAL" >> "$HERMES_HOME/.env"
    fi
  fi
  echo "Kept existing $HERMES_HOME/.env"
fi

# Point model.api_key via env if hermes supports it — document for operator
cat > "$HERMES_HOME/AUTOCLIPER.md" <<EOF
# AutoCliper Hermes profile

- config.yaml synced from repo ops/hermes/config.yaml
- LLM: custom provider → http://127.0.0.1:20128/v1 (9router)
- Hook + subtitle remain Remotion; Hermes used for creative/template/HF authoring
- AutoCliper tools: skills/bin/ac_*.py (viral_search, submit_job, job_status, dll)
- Telegram bot: ops/telegram/telegram_bot.py
- Re-sync: scripts/sync-hermes-config.sh
- Telegram setup: scripts/setup-telegram-bot.sh
EOF

echo "OK HERMES_HOME=$HERMES_HOME"
if command -v hermes >/dev/null 2>&1; then
  echo "hermes binary: $(command -v hermes)"
  hermes --version 2>/dev/null || true
else
  echo "WARN: hermes not on PATH — install: curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
fi
