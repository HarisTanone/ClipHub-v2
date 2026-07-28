# AutoCliper HyperFrames Renderer

Polish layer only (**lower-third / motion extras**).  
**Hook + subtitle stay on Remotion** (`remotion-renderer`).

## Design

- Templates under `templates/<name>/index.html`
- Assembler fills `{{BASE_SRC}}`, `{{EVENTS_JSON}}`, `{{DURATION}}` — no freestyle LLM HTML in batch
- Service `:3003` — `POST /render`, `GET /health`, `GET /templates`
- If `hyperframes` CLI fails → ffmpeg drawtext fallback (pipeline continues)

## Local

```bash
cd hyperframes-renderer
npm install
npm start
# curl localhost:3003/health
```

## Production

`deploy.sh` installs deps, writes `autocliper-hyperframes.service`, health-checks `:3003`.

## Hermes

Use Hermes + HF skills to **author new templates offline**, then commit under `templates/`.  
Do not call Hermes per clip in the job pipeline.
