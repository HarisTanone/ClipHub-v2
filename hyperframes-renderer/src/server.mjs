/**
 * AutoCliper HyperFrames polish service (:3003).
 * POST /render  { template, base_src|base_video, events, duration, out_path? }
 * GET  /health
 * GET  /templates
 *
 * Does NOT replace Remotion hook/subtitle.
 */
import express from 'express';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { assembleHtml, listTemplates, writeComposition } from './assemble.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PORT = Number(process.env.HYPERFRAMES_SERVER_PORT || process.env.PORT || 3003);
const WORK = process.env.HYPERFRAMES_WORK_DIR || path.join(ROOT, 'work');

fs.mkdirSync(WORK, { recursive: true });

const app = express();
app.use(express.json({ limit: '8mb' }));

app.get('/health', (_req, res) => {
  res.json({
    status: 'healthy',
    service: 'autocliper-hyperframes',
    templates: listTemplates(),
    note: 'polish layer only; hook+subtitle = Remotion',
  });
});

app.get('/templates', (_req, res) => {
  res.json({ templates: listTemplates() });
});

function runHyperframesRender(compositionDir, outFile, timeoutMs = 180000) {
  return new Promise((resolve, reject) => {
    // Prefer local node_modules bin, then npx
    const localBin = path.join(ROOT, 'node_modules', '.bin', 'hyperframes');
    const bin = fs.existsSync(localBin) ? localBin : 'npx';
    const args = fs.existsSync(localBin)
      ? ['render', compositionDir, '--out', outFile]
      : ['--yes', 'hyperframes', 'render', compositionDir, '--out', outFile];

    const child = spawn(bin, args, {
      cwd: ROOT,
      env: process.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill('SIGKILL');
      reject(new Error(`hyperframes render timeout ${timeoutMs}ms`));
    }, timeoutMs);
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    child.on('error', (err) => {
      clearTimeout(timer);
      reject(err);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code === 0 && fs.existsSync(outFile)) {
        resolve({ stdout, stderr, outFile });
      } else {
        // Fallback: if CLI missing/failed, write assembled HTML + stub note
        reject(new Error(`hyperframes exit ${code}: ${stderr || stdout || 'no output'}`));
      }
    });
  });
}

/** Lightweight ffmpeg overlay fallback when hyperframes CLI unavailable. */
function ffmpegLowerThirdFallback(baseVideo, events, outFile, timeoutMs = 120000) {
  return new Promise((resolve, reject) => {
    if (!baseVideo || !fs.existsSync(baseVideo)) {
      reject(new Error('base video missing for fallback'));
      return;
    }
    // passthrough copy if no events — still "success" for pipeline continuity
    if (!events?.length) {
      fs.copyFileSync(baseVideo, outFile);
      resolve({ mode: 'copy', outFile });
      return;
    }
    // Draw simple text labels (first 3) — polish-lite, not full HF
    const draws = events.slice(0, 3).map((e, i) => {
      const start = Number(e.start) || 0;
      const end = Number(e.end) || start + 2.4;
      const label = String(e.label || e.word || 'item').replace(/[:\\]/g, ' ').slice(0, 40);
      const y = 1600 - i * 90;
      return `drawtext=text='${label}':fontsize=36:fontcolor=white:box=1:boxcolor=black@0.7:boxborderw=12:x=48:y=${y}:enable='between(t\\,${start}\\,${end})'`;
    });
    const filter = draws.join(',');
    const args = [
      '-y', '-i', baseVideo,
      '-vf', filter,
      '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
      '-c:a', 'copy',
      outFile,
    ];
    const child = spawn('ffmpeg', args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill('SIGKILL');
      reject(new Error('ffmpeg fallback timeout'));
    }, timeoutMs);
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code === 0 && fs.existsSync(outFile)) resolve({ mode: 'ffmpeg_drawtext', outFile });
      else reject(new Error(`ffmpeg fallback exit ${code}: ${stderr.slice(-400)}`));
    });
  });
}

app.post('/render', async (req, res) => {
  const started = Date.now();
  try {
    const {
      template = 'lower_third_v1',
      base_src,
      base_video,
      events = [],
      duration = 0,
      out_path,
      job_id = 'adhoc',
      clip_id = '0',
    } = req.body || {};

    const base = base_video || base_src || '';
    const workDir = path.join(WORK, `${job_id}_${clip_id}_${Date.now()}`);
    fs.mkdirSync(workDir, { recursive: true });

    const indexPath = writeComposition(workDir, {
      template,
      baseSrc: base.startsWith('http') ? base : (base ? `file://${base}` : ''),
      events,
      duration,
    });

    const outFile = out_path || path.join(workDir, 'output.mp4');
    fs.mkdirSync(path.dirname(outFile), { recursive: true });

    let mode = 'hyperframes';
    try {
      await runHyperframesRender(workDir, outFile, Number(process.env.HYPERFRAMES_TIMEOUT || 180) * 1000);
    } catch (err) {
      mode = 'fallback';
      await ffmpegLowerThirdFallback(base, events, outFile);
      fs.writeFileSync(
        path.join(workDir, 'fallback.txt'),
        String(err?.message || err)
      );
    }

    res.json({
      ok: true,
      mode,
      template,
      out_path: outFile,
      composition: indexPath,
      events: events.length,
      ms: Date.now() - started,
    });
  } catch (err) {
    res.status(500).json({
      ok: false,
      error: String(err?.message || err),
      ms: Date.now() - started,
    });
  }
});

app.post('/assemble', (req, res) => {
  try {
    const html = assembleHtml(req.body || {});
    res.type('html').send(html);
  } catch (err) {
    res.status(400).json({ ok: false, error: String(err?.message || err) });
  }
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`[hyperframes] listening :${PORT} templates=${listTemplates().join(',') || '(none)'} work=${WORK}`);
});
