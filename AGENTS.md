# Hermes / Claude Code / Codex / OpenCode — Project Rules

Repo: `autocliper-backend-v01` (alias ClipHub-v2).
Pipeline: Remotion :3002 (hook/sub/AI text) + HF :3003 (polish) + FFmpeg drawtext.
DB: `hyperframes_configs` + `object_overlay_configs`. MinIO bucket `cliperhub` endpoint `103.103.22.205:9000`.

## Non-Negotiable Rules

1. **Final canvas ALWAYS 1080×1920.** Aspect framing hanya di dalam tracking 9:16, 16:9, 1:1.
   - Remotion resolution = `output_resolution_for_job(9:16)`.
   - 9:16: autogrid + YOLO subject tracking.
   - 16:9 / 1:1: passthrough + template fill, no black bars, no upscale hack.
   - B-roll splice wajib pakai `resolution_for_aspect`.

2. **AI text emphasis = Remotion ONLY.** Component `AITextLayer`. Server side: drawtext FFmpeg / HF polish JANGAN dipakai untuk AI text.
   - Preview editor HARUS ≡ final bake (normalise style FE+BE, path Remotion sama).
   - `render_still` untuk preview still.
   - Style sumber kebenaran = DB `object_overlay_configs`, bukan hardcode.

3. **JANGAN hardcode lexicon/synonym/stopword/mood map.** Dilarang:
   - `OBJECT_LEXICON`, `_TOPIC_SYNONYMS`, `_OBJECT_HINT`, `_KEYWORD_STOP`
   - Stopword function list (kata hubung, partikel, dll)
   - Kamus entity domain / sinonim statis
   - Mood map statis untuk restyle prompt
   - Entity visual / query HARUS datang dinamis dari `analyze_visual_entities_for_clips(per_clip)`.
   - Fallback offline HANYA untuk `len()` length-filter + proper noun detection — BUKAN kamus domain.

4. **Engine flag = `style.engine` di DB.** Tiga nilai:
   - `remotion` (default, AI text layer hidup)
   - `hyperframes` (legacy engine :3003)
   - `ffmpeg` (server drawtext, DB `ffmpeg_hook_styles`)
   `resolve_engine()` return value harus respected — jangan override dari hardcode.

5. **Ownership per engine = strict.** Tidak boleh cross-call engine ownership:
   - Remotion job → only via `:3002` API
   - HF job → only via `:3003` API
   - FFmpeg → only via subprocess direct call dari backend
   Jangan re-render engine lain di tengah pipeline tanpa intent.

## Verifikasi Wajib per Perubahan Render

End-to-end test harus lewat SEMUA step ini sebelum dianggap "selesai":

- [ ] `cd backend && ./venv/bin/python -m pytest tests/test_<scope>.py -v` (bukan `python3 -m pytest`)
- [ ] Build Remotion fresh: `cd remotion-renderer && npm run build && npx ts-node src/render.ts --job=<id>` untuk sample job
- [ ] B-roll splice produces valid mp4 (ffprobe ok, duration match)
- [ ] Inline preview = file final 1:1 (sama style, sama path, sama pixel sampling)
- [ ] MinIO upload ok + signed URL returns video playable inline di UI
- [ ] UI VideoFrame 9:16 (~270px phone frame), bukan download-only
- [ ] Lucide SVG icons only (Zap, Check, FileText) — ZERO emoji
- [ ] `git status` bersih sebelum `git commit`

## Backend Conventions

- Python venv: `backend/venv/bin/python` (JANGAN `python3` system)
- pytest: `./venv/bin/python -m pytest` (bukan `python3 -m pytest`)
- Background job: pakai `ops/hermes` scheduler; cron jobs lewat `hermes cron` CLI
- Secrets: `.env` lokal, JANGAN commit; production lewat shared.env systemd
- Folder 1-file-per-module (lihat `autocliper-render-pipeline` skill)
- TypeScript strict di `frontend/` dan `remotion-renderer/`

## Deploy

- `deploy.sh` systemd service `autocliper-hyperframes`
- Hermes config: `scripts/sync-hermes-config.sh` (sync dari `ops/hermes/config.yaml`)
- Telegram bot: `ops/telegram/telegram_bot.py` (Bot API)

## Skill Auto-Load (saat masuk repo ini)

Wajib pakai skill ini kalau topiknya match:

- `autocliper-render-pipeline` — render pipeline lintas layer
- `autocliper-behind-person` — portrait top-behind-person B-roll
- `autocliper-video-generator` — topic → story → footage → TTS → render
- `systematic-debugging` — saat debug render bug / aspect mismatch / preview ≠ bake
- `requesting-code-review` — sebelum commit perubahan engine / object_overlay
- `simplify-code` — setelah perubahan besar
- `hermes-agent` — kalau perlu config / tools / skills
- `dogfood` — exploratory QA UI

JANGAN asumsikan project lain punya rule ini. `customer-api`, `live-chat-backend`, dll pakai konvensi sendiri (lihat memory).
