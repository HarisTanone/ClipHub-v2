# 9router Server Migration

Git moves the AutoCliper code. It does not move runtime data from apps installed outside this repo.

For this setup, the important external app is 9router. On the Mac it is installed as npm package `9router@0.5.20`, and its data is in:

```text
~/.9router
```

That folder contains the current 9router database, combo, auth secrets, and local state. To avoid setting up 9router again on the server, move that data with the 9router helper scripts.

## Mac: Export 9router

From the AutoCliper project root:

```bash
scripts/pack-9router-data.sh
```

This creates:

```text
9router-data-YYYYMMDD-HHMMSS.tar.gz
```

Copy it to the server:

```bash
scp 9router-data-*.tar.gz user@SERVER_IP:/tmp/
```

Keep this archive private. It contains 9router database/secrets.

## Server: Restore 9router

After the code is on the server:

```bash
scripts/restore-9router-data.sh /tmp/9router-data-YYYYMMDD-HHMMSS.tar.gz
```

The restore script installs the same 9router CLI version and restores data to `~/.9router`.

## Server: Deploy AutoCliper

Then run:

```bash
./deploy.sh
```

`deploy.sh` will:

- install `9router@0.5.20` if missing
- start `autocliper-9router` on `127.0.0.1:20128`
- set/use `NINE_ROUTER_BASE_URL=http://127.0.0.1:20128/v1`
- start backend, Remotion, and frontend

## Optional: AutoCliper Runtime Data

`scripts/pack-runtime-data.sh` is only for AutoCliper runtime data, not code and not 9router. Use it only if you also want to move existing AutoCliper users/jobs/rendered clips/cache from the Mac:

- `backend/data/`
- `backend/tmp/`
- `backend/.env`

If you only need code plus current 9router config/combo, use Git plus `pack-9router-data.sh`.

## Expected Env

The backend should point to local 9router on the server:

```env
LLM_PROVIDER=nine_router
FORCE_V2_PIPELINE=true
ALLOW_DIRECT_PROVIDER_FALLBACKS=false
TRANSCRIPTION_PROVIDER=local
NINE_ROUTER_BASE_URL=http://127.0.0.1:20128/v1
NINE_ROUTER_MODEL=ngentot
NINE_ROUTER_PASS1_MODEL=ngentot
NINE_ROUTER_PASS2_MODEL=ngentot
NINE_ROUTER_AI_LAYER_MODEL=ngentot
```
