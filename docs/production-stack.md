# AutoCliper Production Stack (local == server)

One config shape on Mac and Ubuntu. Secrets stay host-local; structure is in git.

## Services & ports

| Service | Port | Role |
|---------|------|------|
| 9router | 20128 | LLM gateway (Hermes + backend) |
| Backend | 8000 | FastAPI pipeline |
| Remotion | 3002 | Hook + subtitle render (**kept**) |
| HyperFrames | 3003 | Optional polish (lower-third templates) |
| Frontend | 3001 | UI |
| Hermes | CLI | Creative / template author (not per-clip batch) |

## Shared config in repo

```
ops/hermes/config.yaml      # Hermes → 9router :20128
ops/hermes/env.example      # secrets template
ops/env/shared.env.example  # backend env shape
```

## Local setup

```bash
# 1) 9router data (if migrating machine)
scripts/pack-9router-data.sh
# on target: scripts/restore-9router-data.sh /path/to/9router-data-*.tar.gz

# 2) Hermes config (same file local + server)
scripts/sync-hermes-config.sh
# optional full home migrate:
scripts/pack-hermes-data.sh
scripts/restore-hermes-data.sh /path/to/hermes-data-*.tar.gz

# 3) HyperFrames renderer deps
cd hyperframes-renderer && npm install

# 4) Deploy / start services
./deploy.sh   # server (systemd)
# local: start 9router, backend, remotion, hyperframes, frontend as usual
```

## Invariants

- Hook + subtitle = **Remotion only** (not HyperFrames).
- HyperFrames = template + JSON fill (no freestyle HTML per clip in batch).
- Hermes uses `model.base_url: http://127.0.0.1:20128/v1` (9router).
- Backend `LLM_PROVIDER=nine_router` + same base URL.
- DB: SQLAlchemy `init_db` + side tables (`object_overlay_configs`, etc.) on startup/deploy.

## Env keys (backend)

See `ops/env/shared.env.example`. Deploy appends missing keys only (never clobber ops overrides).
