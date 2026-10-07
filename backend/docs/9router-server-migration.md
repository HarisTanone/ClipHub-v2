# 9router — Migration Log

**Status: AKTIF (production-ready).**
9router is now the sole LLM gateway for all text/AI calls in the backend.

## Endpoint

- URL: `http://100.64.5.96:20128/v1` (OpenAI-compatible, tailscale)
- Env: `NINE_ROUTER_BASE_URL` (DB override from admin panel wins)
- Key / model / combination: configured via admin panel
  (`system_settings` table, exposed at `/api/settings`)
- Direct-provider fallbacks disabled by default
  (`ALLOW_DIRECT_PROVIDER_FALLBACKS=false`). Flip only for legacy rescue.

## Migrated call sites (all go through 9router now)

- `llm_router.route_chat` / `get_llm_chain` — always returns `nine_router`
- `NineRouterClient.chat` / `complete_json` — model passed as hint; 9router decides
- `subtitle_ai.py` — dropped direct `google.genai`, uses `get_nine_router_client()`
- `story_agent.py` — removed direct Gemini fallback + hardcoded model rotation
- `highlight_analyzer.py` — 9router primary; Groq/Gemini/Ollama gated behind flag
- `groq_transcriber.py` — audio via 9router `/audio/transcriptions` route;
  direct Groq Whisper gated behind flag
- `groq_analyzer.py` — LLM calls via `route_chat`; direct Groq gated
- `gemini_analyzer.py` — DEPRECATED; only for native multimodal video
- `gemini_agentic_video_service.py` — retained for native video understanding
  (9router cannot proxy video input)

## Direct-provider fallbacks (flagged)

`ALLOW_DIRECT_PROVIDER_FALLBACKS=true` (default `false`) unlocks legacy paths
in `groq_transcriber`, `groq_analyzer`, `highlight_analyzer`. Everything else
is unconditional 9router.

## Config surface

Backend reads (in order):
1. Admin-panel `system_settings` (highest priority — set from UI)
2. Env vars in `.env` / systemd `EnvironmentFile`
3. Defaults in `src/config.py`

`deploy.sh` writes `NINE_ROUTER_BASE_URL=http://100.64.5.96:20128/v1` and
`ALLOW_DIRECT_PROVIDER_FALLBACKS=false` into `backend/.env` on first deploy.
