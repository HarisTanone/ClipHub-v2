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
  # Dynamically inherit superadmin credentials from backend/.env if not explicitly set in HERMES_HOME/.env
  python3 -c "
import os
hermes_env = '$HERMES_HOME/.env'
be_env = '$PROJECT_DIR/backend/.env'
Q = chr(34) + chr(39) + ' '
defaults = {
    'GEMINI_API_KEY': '',
    'GEMINI_MODEL': '',
    'GEMINI_FALLBACK_MODEL': '',
    'AUTOCLIPER_API_URL': 'http://127.0.0.1:8000/api',
}
if os.path.exists(be_env):
    with open(be_env, 'r') as f:
        for line in f:
            line = line.strip()
            key, sep, val = line.partition('=')
            val = val.strip().strip(Q)
            if key in defaults and val:
                defaults[key] = val
            elif key == 'SUPERADMIN_EMAIL' and val:
                defaults['AUTOCLIPER_EMAIL'] = val
            elif key == 'SUPERADMIN_PASSWORD' and val:
                defaults['AUTOCLIPER_PASSWORD'] = val

# DB fallback: panel-managed GEMINI_* live in system_settings when .env has none.
for _db in ('$PROJECT_DIR/backend/data/autoclip.db', '$PROJECT_DIR/backend/data/autocliper.db', '$PROJECT_DIR/backend/autocliper.db'):
    if not os.path.exists(_db):
        continue
    try:
        import sqlite3 as _sq
        _conn = _sq.connect(_db)
        for _k in ('GEMINI_API_KEY', 'GEMINI_MODEL', 'GEMINI_FALLBACK_MODEL'):
            if defaults.get(_k):
                continue
            try:
                _row = _conn.execute('SELECT value FROM system_settings WHERE key=?', (_k,)).fetchone()
            except Exception:
                _row = None
            if _row and _row[0]:
                _v = str(_row[0]).strip().strip(Q)
                if _k == 'GEMINI_API_KEY':
                    _v = _v.split(',')[0].strip()
                defaults[_k] = _v
        _conn.close()
    except Exception:
        pass

if os.path.exists(hermes_env):
    with open(hermes_env, 'r') as f:
        lines = f.readlines()
    keys_found = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        matched = False
        for k, v in defaults.items():
            if stripped.startswith(k + '='):
                val = stripped.split('=', 1)[1].strip(Q)
                if not val and v:
                    new_lines.append(k + '=' + v + os.linesep)
                else:
                    new_lines.append(line)
                keys_found.add(k)
                matched = True
                break
        if not matched:
            new_lines.append(line)
    for k, v in defaults.items():
        if k not in keys_found and v:
            new_lines.append(k + '=' + v + os.linesep)
    with open(hermes_env, 'w') as f:
        f.writelines(new_lines)
" 2>/dev/null || true
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
- LLM: native Gemini (GEMINI_API_KEY/GEMINI_MODEL/GEMINI_FALLBACK_MODEL di \$HERMES_HOME/.env)
- Rotate mode (DeepSeek/GLM/custom): UI Settings → LLM Providers (DB llm_providers, LLM_ROTATE_ALL)
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
