# AutoCliper Remotion Renderer

Node.js render server using Remotion + React for programmatic video generation.

## Tech Stack

- Remotion 4.0.242
- React 18
- Express (HTTP server, port 3002)
- TypeScript

## Compositions

| Composition | Description |
|-------------|-------------|
| ClipComposition | Main — video + hook + subtitle layers |

## Layers (z-order)

```
L1: Base Video (OffthreadVideo)
L3: Hook Text (fade_scale, slide_up, glitch, typewriter)
L5: Subtitles (word-by-word with highlight)
```

## API

### POST /render
Render a clip with scene graph + style config.

### GET /health
Server health check.

## Quick Start

```bash
# Install
npm install

# Start server (port 3002)
REMOTION_SERVER_PORT=3002 npx tsx src/server/index.ts

# Preview compositions
npm run dev
```

## Environment

```env
REMOTION_SERVER_PORT=3002
RENDERER_QUALITY=medium
```

## Integration

1. Python backend checks `USE_REMOTION=true`
2. Sends render request with video path + style config
3. This server renders via Remotion CLI
4. Returns final video path

## Notes

- Uses `OffthreadVideo` for stability
- `chromiumOptions: { gl: "angle" }` for headless
- CRF 18 for medium quality
- Concurrency limited to 2 on M1
