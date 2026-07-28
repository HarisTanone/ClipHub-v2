/**
 * Deterministic template + JSON → HyperFrames-valid composition.
 * Hook/subtitle remain Remotion — this is polish lower-thirds only.
 *
 * Output must satisfy HF CLI:
 *  - root data-composition-id + data-width/height/duration
 *  - media paths relative to project dir (base.mp4)
 *  - timed elements class="clip" + GSAP timeline
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const TEMPLATES = path.join(ROOT, 'templates');

const ACCENTS = ['#22d3ee', '#a78bfa', '#f472b6', '#34d399'];

export function listTemplates() {
  if (!fs.existsSync(TEMPLATES)) return [];
  return fs.readdirSync(TEMPLATES).filter((n) =>
    fs.existsSync(path.join(TEMPLATES, n, 'index.html'))
  );
}

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escAttr(s) {
  return String(s ?? '').replace(/"/g, '&quot;').replace(/</g, '');
}

/**
 * Build a valid HyperFrames portrait composition from events.
 * baseRel = relative path inside work dir (usually "base.mp4").
 */
export function assembleHtml({
  template = 'lower_third_v1',
  baseSrc = 'base.mp4',
  events = [],
  duration = 0,
} = {}) {
  // Prefer generating HF-valid composition; keep template name for meta only.
  const safeEvents = (Array.isArray(events) ? events : [])
    .map((e) => ({
      label: String(e.label || e.word || e.name || '').slice(0, 48),
      sub: String(e.sub || e.query_en || e.query_id || '').slice(0, 80),
      start: Math.max(0, Number(e.start ?? e.t0 ?? 0) || 0),
      end: Math.max(
        0.5,
        Number(e.end ?? e.t1 ?? ((Number(e.start) || 0) + 2.4)) || 2.4,
      ),
      thumb: e.thumb || e.image_url || e.image || '',
    }))
    .filter((e) => e.label)
    .slice(0, 6);

  let dur = Number(duration) || 0;
  if (!dur || dur < 0.5) {
    dur = safeEvents.reduce((m, e) => Math.max(m, e.end), 6);
  }
  dur = Math.max(1, Math.ceil(dur * 10) / 10);

  // Media must be project-relative — never file:// for HF frame extract
  let mediaSrc = String(baseSrc || 'base.mp4');
  if (mediaSrc.startsWith('file://')) {
    mediaSrc = 'base.mp4';
  }
  // strip absolute paths → base.mp4 (server copies file into work dir)
  if (path.isAbsolute(mediaSrc) || mediaSrc.includes('://')) {
    if (!mediaSrc.startsWith('http')) mediaSrc = 'base.mp4';
  }

  const bottoms = [220, 360, 500, 640];
  const cards = safeEvents
    .map((ev, i) => {
      const id = `lt${i}`;
      const start = ev.start;
      const cardDur = Math.max(0.8, ev.end - ev.start);
      const accent = ACCENTS[i % ACCENTS.length];
      const bottom = bottoms[Math.min(i, bottoms.length - 1)];
      const thumbHtml = ev.thumb && !String(ev.thumb).startsWith('file://')
        ? `<img class="thumb" src="${escAttr(ev.thumb)}" alt="" width="88" height="88"/>`
        : (ev.thumb && String(ev.thumb).startsWith('file://')
          // local thumbs: server may copy as thumbs/N.jpg — leave empty if absolute file
          ? ''
          : '');
      return `
    <div id="${id}" class="clip lt" data-start="${start}" data-duration="${cardDur}" data-track-index="1"
         style="bottom:${bottom}px;border-left-color:${accent}">
      ${thumbHtml}
      <div class="meta">
        <div class="kicker">AI · visual</div>
        <div class="label">${esc(ev.label)}</div>
        ${ev.sub ? `<div class="sub">${esc(ev.sub)}</div>` : ''}
      </div>
    </div>`;
    })
    .join('\n');

  const gsapLines = safeEvents
    .map((_, i) => {
      const id = `#lt${i}`;
      const start = safeEvents[i].start;
      const end = safeEvents[i].end;
      return [
        `tl.from("${id}", { opacity: 0, y: 24, duration: 0.28 }, ${start});`,
        `tl.to("${id}", { opacity: 0, y: 12, duration: 0.2 }, ${Math.max(start, end - 0.2)});`,
      ].join('\n      ');
    })
    .join('\n      ');

  // Note: template file kept for listTemplates(); body is HF-native
  void template;

  return `<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=1080, height=1920" />
  <title>AutoCliper HF polish · lower_third</title>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      margin: 0; width: 1080px; height: 1920px;
      overflow: hidden; background: #000;
      font-family: Inter, system-ui, -apple-system, sans-serif;
    }
    .lt {
      position: absolute; left: 40px; right: 40px;
      display: flex; align-items: center; gap: 16px;
      padding: 16px 20px; border-radius: 18px;
      background: linear-gradient(135deg, rgba(12,12,16,0.92), rgba(30,20,50,0.88));
      border-left: 6px solid #22d3ee;
      box-shadow: 0 12px 40px rgba(0,0,0,0.45);
      color: #f8fafc;
    }
    .lt .thumb {
      width: 88px; height: 88px; border-radius: 14px;
      object-fit: cover; background: #1e293b; flex-shrink: 0;
    }
    .lt .meta { min-width: 0; flex: 1; }
    .lt .kicker {
      font-size: 14px; font-weight: 600; letter-spacing: 0.08em;
      text-transform: uppercase; opacity: 0.55; margin-bottom: 4px;
    }
    .lt .label {
      font-size: 38px; font-weight: 800; letter-spacing: -0.03em;
      line-height: 1.1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .lt .sub {
      margin-top: 6px; font-size: 20px; opacity: 0.78;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
  </style>
</head>
<body>
  <div id="root"
       data-composition-id="main"
       data-start="0"
       data-duration="${dur}"
       data-width="1080"
       data-height="1920"
       data-fps="30">
    <video id="a-roll" class="clip"
           src="${escAttr(mediaSrc)}"
           muted playsinline
           data-start="0"
           data-duration="${dur}"
           data-track-index="0"
           style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover"></video>
    <audio id="a-roll-audio"
           src="${escAttr(mediaSrc)}"
           data-start="0"
           data-duration="${dur}"
           data-track-index="2"
           data-volume="1"></audio>
${cards}
  </div>
  <script>
    window.__timelines = window.__timelines || {};
    const tl = gsap.timeline({ paused: true });
    ${gsapLines}
    window.__timelines["main"] = tl;
  </script>
</body>
</html>
`;
}

export function writeComposition(outDir, opts) {
  fs.mkdirSync(outDir, { recursive: true });
  // hyperframes.json so CLI treats dir as project
  const hfJson = path.join(outDir, 'hyperframes.json');
  if (!fs.existsSync(hfJson)) {
    fs.writeFileSync(
      hfJson,
      JSON.stringify(
        {
          $schema: 'https://hyperframes.heygen.com/schema/hyperframes.json',
          paths: { blocks: 'compositions', components: 'compositions/components', assets: 'assets' },
          media: { autoProxy: true },
        },
        null,
        2,
      ),
    );
  }
  const html = assembleHtml(opts);
  const indexPath = path.join(outDir, 'index.html');
  fs.writeFileSync(indexPath, html, 'utf8');
  fs.writeFileSync(
    path.join(outDir, 'meta.json'),
    JSON.stringify(
      {
        template: opts.template || 'lower_third_v1',
        duration: opts.duration,
        events: opts.events || [],
        baseSrc: opts.baseSrc,
      },
      null,
      2,
    ),
  );
  return indexPath;
}
