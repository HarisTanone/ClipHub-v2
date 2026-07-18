/**
 * Remotion Render Server
 *
 * Express server that receives render requests from the Python backend
 * and uses Remotion's renderMedia API to produce final clips.
 *
 * Endpoints:
 *   GET  /health          — Server health check
 *   POST /render          — Render a clip composition to mp4
 *   GET  /status/:renderId — Check render status
 *   GET  /media/*         — Serve local video files for Remotion browser
 */
import express from "express";
import path from "path";
import fs from "fs";
import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";
import { z } from "zod";
import type { RenderResponse } from "../types";

const app = express();
app.use(express.json({ limit: "50mb" }));

const PORT = parseInt(process.env.REMOTION_SERVER_PORT || "3002", 10);

// ─── State ───────────────────────────────────────────────────────────────────

let bundled: string | null = null;
let bundleReady = false;
const activeRenders = new Map<string, { status: string; progress: number }>();

// ─── Static file serving for video assets ────────────────────────────────────
// Remotion's browser needs to access local video files via HTTP URL

app.get("/media/*", (req: any, res: any) => {
  const requestedPath = req.params["0"] || req.params[0] || "";
  if (!requestedPath) {
    return res.status(400).send("No file path");
  }

  // Always treat as absolute path (prepend / if missing)
  const fullPath = requestedPath.startsWith("/")
    ? requestedPath
    : "/" + requestedPath;

  if (!fs.existsSync(fullPath)) {
    console.error(`[media] File not found: ${fullPath}`);
    return res.status(404).send("File not found");
  }

  const ext = path.extname(fullPath).toLowerCase();
  const mimeTypes: Record<string, string> = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
  };

  res.setHeader("Content-Type", mimeTypes[ext] || "application/octet-stream");
  res.setHeader("Accept-Ranges", "bytes");
  res.setHeader("Access-Control-Allow-Origin", "*");

  const stat = fs.statSync(fullPath);
  const range = req.headers.range;

  if (range) {
    const parts = range.replace(/bytes=/, "").split("-");
    const start = parseInt(parts[0], 10);
    const end = parts[1] ? parseInt(parts[1], 10) : stat.size - 1;
    res.status(206);
    res.setHeader("Content-Range", `bytes ${start}-${end}/${stat.size}`);
    res.setHeader("Content-Length", String(end - start + 1));
    fs.createReadStream(fullPath, { start, end }).pipe(res);
  } else {
    res.setHeader("Content-Length", String(stat.size));
    fs.createReadStream(fullPath).pipe(res);
  }
});

// ─── Bundle on startup ───────────────────────────────────────────────────────

async function initBundle() {
  console.log("[remotion-server] Bundling compositions...");
  const entryPoint = path.resolve(__dirname, "../index.ts");
  try {
    bundled = await bundle({
      entryPoint,
      onProgress: (p) => {
        if (p === 100) console.log("[remotion-server] Bundle ready");
      },
    });
    bundleReady = true;
    console.log(`[remotion-server] Bundle path: ${bundled}`);
  } catch (err) {
    console.error("[remotion-server] Bundle failed:", err);
  }
}

// ─── Routes ──────────────────────────────────────────────────────────────────

app.get("/health", (_req, res) => {
  res.json({
    status: bundleReady ? "healthy" : "starting",
    bundleReady,
    activeRenders: activeRenders.size,
    uptime: process.uptime(),
  });
});

// Render request schema validation
const RenderRequestSchema = z.object({
  compositionId: z.string().default("ClipComposition"),
  outputPath: z.string(),
  props: z.object({
    sceneGraph: z.any(),
    creativeDirection: z.any(),
    videoPath: z.string(),
    words: z.array(z.any()).default([]),
    hookText: z.string().default(""),
    hookAnimation: z.enum([
      "fade_scale",
      "slide_up",
      "glitch",
      "typewriter",
      "glitch_rgb",
      "shake_neon",
      "cinematic_reveal",
      "danger_bold",
      "slide_punch_framer",
      "bold_slam",
      "podcast_lower_third",
      "quote_card",
      "waveform_pulse",
      "breaking_tape",
      "mic_drop",
      "split_panel",
      "kinetic_stack",
      "glass_flash",
      "marker_swipe",
      "signal_scan",
    ]).default("podcast_lower_third"),
    textEmphasisEvents: z.array(z.any()).max(2).default([]),
    enableThreeJS: z.boolean().default(false),
    enableAI: z.boolean().default(false),
  }),
  durationInFrames: z.number().int().positive(),
  fps: z.number().default(30),
  width: z.number().default(1080),
  height: z.number().default(1920),
  codec: z.string().default("h264"),
  quality: z.enum(["low", "medium", "high"]).default("medium"),
  concurrency: z.number().default(2),
});

app.post("/render", async (req, res) => {
  if (!bundleReady || !bundled) {
    return res.status(503).json({
      success: false,
      error: "Server not ready - bundle still compiling",
    } satisfies RenderResponse);
  }

  // Validate request
  const parsed = RenderRequestSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({
      success: false,
      error: `Invalid request: ${parsed.error.message}`,
    } satisfies RenderResponse);
  }

  const request = parsed.data;
  const renderId = `render_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

  activeRenders.set(renderId, { status: "rendering", progress: 0 });

  const startTime = Date.now();

  try {
    // Quality presets
    const qualityConfig = {
      low: { crf: 28, concurrency: 4 },
      medium: { crf: 18, concurrency: 2 },
      high: { crf: 12, concurrency: 1 },
    }[request.quality];

    // Convert local video path to HTTP URL served by this server
    const propsWithUrl = { ...request.props };
    if (propsWithUrl.videoPath && propsWithUrl.videoPath.startsWith("/")) {
      propsWithUrl.videoPath = `http://localhost:${PORT}/media${propsWithUrl.videoPath}`;
    }
    propsWithUrl.textEmphasisEvents = (propsWithUrl.textEmphasisEvents || []).slice(0, 2).map((event: any) => ({
      ...event,
      foreground_frames: (event.foreground_frames || []).map((item: any) => ({
        ...item,
        path: typeof item.path === "string" && item.path.startsWith("/")
          ? `http://localhost:${PORT}/media${item.path}`
          : item.path,
      })),
    }));

    console.log(`[remotion-server] Rendering: ${path.basename(request.outputPath)}`);
    console.log(`[remotion-server]   Video URL: ${propsWithUrl.videoPath}`);
    console.log(`[remotion-server]   Duration: ${request.durationInFrames} frames @ ${request.fps}fps`);
    console.log(`[remotion-server]   Quality: ${request.quality} (crf=${qualityConfig.crf})`);
    console.log(`[remotion-server]   Hook: "${propsWithUrl.hookText?.slice(0, 40)}..." anim=${propsWithUrl.hookAnimation}`);
    console.log(`[remotion-server]   Hook config: color=${propsWithUrl.creativeDirection?.hook_style_config?.color || 'NOT SET'}, glow=${propsWithUrl.creativeDirection?.hook_style_config?.glowEnabled || false}`);
    console.log(`[remotion-server]   Words: ${propsWithUrl.words?.length || 0}, firstWord: ${propsWithUrl.words?.[0]?.start != null ? propsWithUrl.words[0].start.toFixed(1) : 'N/A'}s`);

    // Select composition
    const composition = await selectComposition({
      serveUrl: bundled,
      id: request.compositionId,
      inputProps: propsWithUrl,
      chromiumOptions: { gl: "angle" },
    });

    // Override duration/dimensions
    const finalComposition = {
      ...composition,
      durationInFrames: request.durationInFrames,
      fps: request.fps,
      width: request.width,
      height: request.height,
    };

    // Ensure output directory exists
    const outputDir = path.dirname(request.outputPath);
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }

    // Render
    await renderMedia({
      composition: finalComposition,
      serveUrl: bundled,
      codec: request.codec as any,
      outputLocation: request.outputPath,
      inputProps: propsWithUrl,
      concurrency: request.concurrency || qualityConfig.concurrency,
      crf: qualityConfig.crf,
      pixelFormat: "yuv420p",
      chromiumOptions: { gl: "angle" },
      onProgress: ({ progress }) => {
        activeRenders.set(renderId, {
          status: "rendering",
          progress: Math.round(progress * 100),
        });
      },
    });

    const renderTime = (Date.now() - startTime) / 1000;
    activeRenders.delete(renderId);

    console.log(
      `[remotion-server] Render complete: ${path.basename(request.outputPath)} (${renderTime.toFixed(1)}s)`
    );

    return res.json({
      success: true,
      outputPath: request.outputPath,
      renderTimeSeconds: renderTime,
    } satisfies RenderResponse);
  } catch (err: any) {
    activeRenders.delete(renderId);
    console.error(`[remotion-server] Render failed:`, err.message);

    return res.status(500).json({
      success: false,
      error: err.message || "Render failed",
    } satisfies RenderResponse);
  }
});

app.get("/status/:renderId", (req, res) => {
  const render = activeRenders.get(req.params.renderId);
  if (!render) {
    return res.json({ status: "not_found" });
  }
  return res.json(render);
});

// ─── Still frame preview ─────────────────────────────────────────────────────
// Renders a single frame PNG so the frontend can preview style changes
// without committing to a full video render.

const StillRequestSchema = z.object({
  compositionId: z.string().default("ClipComposition"),
  outputPath: z.string(),
  props: z.object({
    sceneGraph: z.any(),
    creativeDirection: z.any(),
    videoPath: z.string(),
    words: z.array(z.any()).default([]),
    hookText: z.string().default(""),
    hookAnimation: z.enum([
      "fade_scale",
      "slide_up",
      "glitch",
      "typewriter",
      "glitch_rgb",
      "shake_neon",
      "cinematic_reveal",
      "danger_bold",
      "slide_punch_framer",
      "bold_slam",
      "podcast_lower_third",
      "quote_card",
      "waveform_pulse",
      "breaking_tape",
      "mic_drop",
      "split_panel",
      "kinetic_stack",
      "glass_flash",
      "marker_swipe",
      "signal_scan",
    ]).default("podcast_lower_third"),
    textEmphasisEvents: z.array(z.any()).max(2).default([]),
    enableThreeJS: z.boolean().default(false),
    enableAI: z.boolean().default(false),
  }),
  frame: z.number().int().min(0).default(60),
  fps: z.number().default(30),
  width: z.number().default(1080),
  height: z.number().default(1920),
});

app.post("/render-still", async (req, res) => {
  if (!bundleReady || !bundled) {
    return res.status(503).json({ success: false, error: "Server not ready - bundle still compiling" });
  }

  const parsed = StillRequestSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ success: false, error: `Invalid request: ${parsed.error.message}` });
  }

  const request = parsed.data;

  try {
    const propsWithUrl = { ...request.props };
    if (propsWithUrl.videoPath && propsWithUrl.videoPath.startsWith("/")) {
      propsWithUrl.videoPath = `http://localhost:${PORT}/media${propsWithUrl.videoPath}`;
    }
    propsWithUrl.textEmphasisEvents = (propsWithUrl.textEmphasisEvents || []).slice(0, 2).map((event: any) => ({
      ...event,
      foreground_frames: (event.foreground_frames || []).map((item: any) => ({
        ...item,
        path: typeof item.path === "string" && item.path.startsWith("/")
          ? `http://localhost:${PORT}/media${item.path}`
          : item.path,
      })),
    }));

    const composition = await selectComposition({
      serveUrl: bundled,
      id: request.compositionId,
      inputProps: propsWithUrl,
      chromiumOptions: { gl: "angle" },
    });

    const finalComposition = {
      ...composition,
      durationInFrames: Math.max(request.frame + 1, 2),
      fps: request.fps,
      width: request.width,
      height: request.height,
    };

    const outputDir = path.dirname(request.outputPath);
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }

    await renderStill({
      composition: finalComposition,
      serveUrl: bundled,
      frame: request.frame,
      output: request.outputPath,
      imageFormat: "jpeg",
      quality: 80,
      inputProps: propsWithUrl,
      chromiumOptions: { gl: "angle" },
    });

    const imageData = fs.readFileSync(request.outputPath, { encoding: "base64" });
    const dataUrl = `data:image/jpeg;base64,${imageData}`;

    return res.json({ success: true, image: dataUrl });
  } catch (err: any) {
    console.error("[remotion-server] Still render failed:", err.message);
    return res.status(500).json({ success: false, error: err.message || "Still render failed" });
  }
});

// ─── Start server ────────────────────────────────────────────────────────────

app.listen(PORT, async () => {
  console.log(`[remotion-server] Listening on http://localhost:${PORT}`);
  console.log(`[remotion-server] Media files served at http://localhost:${PORT}/media/...`);
  await initBundle();
});
