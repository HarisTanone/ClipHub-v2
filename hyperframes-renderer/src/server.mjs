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
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { assembleHtml, listTemplates, writeComposition } from './assemble.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PORT = Number(process.env.HYPERFRAMES_SERVER_PORT || process.env.PORT || 3003);
const WORK = process.env.HYPERFRAMES_WORK_DIR || path.join(ROOT, 'work');
const HF_TIMEOUT = Number(process.env.HYPERFRAMES_TIMEOUT || 180) * 1000;

fs.mkdirSync(WORK, { recursive: true });

const app = express();
app.use(express.json({ limit: '8mb' }));

app.get('/health', (_req, res) => {
  const localBin = path.join(ROOT, 'node_modules', '.bin', 'hyperframes');
  res.json({
    status: 'healthy',
    service: 'autocliper-hyperframes',
    templates: listTemplates(),
    cli: fs.existsSync(localBin) ? 'local' : 'npx',
    note: 'polish layer only; hook+subtitle = Remotion',
  });
});

app.get('/templates', (_req, res) => {
  res.json({ templates: listTemplates() });
});

function runHyperframesRender(compositionDir, outFile, timeoutMs = HF_TIMEOUT) {
  return new Promise((resolve, reject) => {
    const localBin = path.join(ROOT, 'node_modules', '.bin', 'hyperframes');
    const bin = fs.existsSync(localBin) ? localBin : 'npx';
    // HF v0.7 uses -o / --output (NOT --out)
    const args = fs.existsSync(localBin)
      ? ['render', compositionDir, '-o', outFile, '-q', 'draft', '-w', '1']
      : ['--yes', 'hyperframes', 'render', compositionDir, '-o', outFile, '-q', 'draft', '-w', '1'];

    const child = spawn(bin, args, {
      cwd: ROOT,
      env: {
        ...process.env,
        // first-run chrome download can be slow; keep gate soft for polish
        HF_VIDEO_COVERAGE_THRESHOLD: process.env.HF_VIDEO_COVERAGE_THRESHOLD || '0.5',
      },
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
      if (code === 0 && fs.existsSync(outFile) && fs.statSync(outFile).size > 1000) {
        resolve({ stdout, stderr, outFile });
      } else {
        reject(new Error(`hyperframes exit ${code}: ${(stderr || stdout || 'no output').slice(-800)}`));
      }
    });
  });
}

/** Portrait-aware ffmpeg lower-third when HF CLI fails. */
function ffmpegLowerThirdFallback(baseVideo, events, outFile, timeoutMs = 120000) {
  return new Promise((resolve, reject) => {
    if (!baseVideo || !fs.existsSync(baseVideo)) {
      reject(new Error('base video missing for fallback'));
      return;
    }
    if (!events?.length) {
      fs.copyFileSync(baseVideo, outFile);
      resolve({ mode: 'copy', outFile });
      return;
    }

    // Probe height for y placement (default 9:16 1920)
    const probe = spawn('ffprobe', [
      '-v', 'error', '-select_streams', 'v:0',
      '-show_entries', 'stream=width,height', '-of', 'csv=p=0', baseVideo,
    ]);
    let probeOut = '';
    probe.stdout.on('data', (d) => { probeOut += d.toString(); });
    probe.on('close', () => {
      const parts = probeOut.trim().split(',');
      const h = Number(parts[1]) || 1920;
      const draws = [];
      events.slice(0, 4).forEach((e, i) => {
        const start = Number(e.start) || 0;
        const end = Number(e.end) || start + 2.4;
        const label = String(e.label || e.word || 'item')
          .replace(/[':\\]/g, ' ')
          .replace(/%/g, '')
          .slice(0, 36);
        const sub = String(e.sub || '')
          .replace(/[':\\]/g, ' ')
          .replace(/%/g, '')
          .slice(0, 48);
        const boxH = 110;
        const y = Math.max(40, h - 280 - i * (boxH + 24));
        const enable = `between(t\\,${start.toFixed(3)}\\,${end.toFixed(3)})`;
        draws.push(
          `drawbox=x=36:y=${y}:w=iw-72:h=${boxH}:color=black@0.72:t=fill:enable='${enable}'`,
        );
        draws.push(
          `drawbox=x=36:y=${y}:w=8:h=${boxH}:color=0x22d3ee:t=fill:enable='${enable}'`,
        );
        draws.push(
          `drawtext=text='${label}':fontsize=42:fontcolor=white:x=60:y=${y + 28}:enable='${enable}'`,
        );
        if (sub) {
          draws.push(
            `drawtext=text='${sub}':fontsize=24:fontcolor=white@0.8:x=60:y=${y + 72}:enable='${enable}'`,
          );
        }
      });
      const filter = draws.join(',');
      const args = [
        '-y', '-i', baseVideo,
        '-vf', filter,
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
        '-c:a', 'copy',
        '-movflags', '+faststart',
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
        if (code === 0 && fs.existsSync(outFile)) {
          resolve({ mode: 'ffmpeg_drawtext', outFile });
        } else {
          reject(new Error(`ffmpeg fallback exit ${code}: ${stderr.slice(-500)}`));
        }
      });
    });
  });
}

function stageBaseVideo(workDir, baseAbs) {
  const dest = path.join(workDir, 'base.mp4');
  if (!baseAbs || !fs.existsSync(baseAbs)) {
    throw new Error(`base video missing: ${baseAbs}`);
  }
  // hardlink if possible (fast), else copy
  try {
    if (fs.existsSync(dest)) fs.unlinkSync(dest);
    fs.linkSync(baseAbs, dest);
  } catch {
    fs.copyFileSync(baseAbs, dest);
  }
  return dest;
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

    const baseIn = base_video || base_src || '';
    const baseAbs = baseIn.startsWith('file://')
      ? baseIn.replace(/^file:\/\//, '')
      : path.resolve(baseIn);

    const workDir = path.join(WORK, `${job_id}_${clip_id}_${Date.now()}`);
    fs.mkdirSync(workDir, { recursive: true });

    const staged = stageBaseVideo(workDir, baseAbs);

    // Probe duration if missing
    let dur = Number(duration) || 0;
    if (!dur) {
      try {
        const out = await new Promise((resolve) => {
          const p = spawn('ffprobe', [
            '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'csv=p=0', staged,
          ]);
          let s = '';
          p.stdout.on('data', (d) => { s += d.toString(); });
          p.on('close', () => resolve(s));
        });
        dur = parseFloat(out) || 6;
      } catch {
        dur = 6;
      }
    }

    const indexPath = writeComposition(workDir, {
      template,
      baseSrc: 'base.mp4', // project-relative — required by HF frame extract
      events,
      duration: dur,
    });

    const outFile = out_path || path.join(workDir, 'output.mp4');
    fs.mkdirSync(path.dirname(outFile), { recursive: true });

    let mode = 'hyperframes';
    let errMsg = '';
    try {
      await runHyperframesRender(workDir, outFile, HF_TIMEOUT);
    } catch (err) {
      errMsg = String(err?.message || err);
      mode = 'fallback';
      await ffmpegLowerThirdFallback(staged, events, outFile);
      fs.writeFileSync(path.join(workDir, 'fallback.txt'), errMsg);
    }

    if (!fs.existsSync(outFile) || fs.statSync(outFile).size < 500) {
      res.status(500).json({
        ok: false,
        error: errMsg || 'render produced empty file',
        ms: Date.now() - started,
      });
      return;
    }

    res.json({
      ok: true,
      mode,
      template,
      out_path: outFile,
      composition: indexPath,
      events: Array.isArray(events) ? events.length : 0,
      duration: dur,
      fallback_error: mode === 'fallback' ? errMsg.slice(0, 400) : undefined,
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
  console.log(
    `[hyperframes] listening :${PORT} templates=${listTemplates().join(',') || '(none)'} work=${WORK}`,
  );
});
