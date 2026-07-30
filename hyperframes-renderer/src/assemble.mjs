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

/** Per-template visual variants (hook / subtitle / polish). */
const TPL = {
  lower_third_v1: { kind: 'polish', accent: '#22d3ee', kicker: 'AI · visual', pos: 'bottom', y: 220 },
  lower_third: { kind: 'polish', accent: '#a78bfa', kicker: 'INFO', pos: 'bottom', y: 240 },
  hook_banner_v1: { kind: 'hook', accent: '#f97316', kicker: 'HOOK', pos: 'top', y: 160, big: true },
  hook_neon_v1: { kind: 'hook', accent: '#22d3ee', kicker: 'WATCH', pos: 'center', y: 820, glow: true },
  hook_tape_v1: { kind: 'hook', accent: '#facc15', kicker: 'BREAKING', pos: 'top', y: 200, tape: true },
  hook_lower_v1: { kind: 'hook', accent: '#34d399', kicker: 'ON AIR', pos: 'bottom', y: 280 },
  sub_caption_v1: { kind: 'sub', accent: '#f8fafc', kicker: '', pos: 'center', y: 980, clean: true },
  sub_neon_v1: { kind: 'sub', accent: '#a78bfa', kicker: '', pos: 'center', y: 1000, glow: true },
  sub_box_v1: { kind: 'sub', accent: '#38bdf8', kicker: '', pos: 'bottom', y: 260 },
  sub_minimal_v1: { kind: 'sub', accent: '#e2e8f0', kicker: '', pos: 'bottom', y: 220, clean: true },
};

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
  const tplKey = String(template || 'lower_third_v1');
  const meta = TPL[tplKey] || TPL.lower_third_v1;
  const isHook = meta.kind === 'hook';
  const isSub = meta.kind === 'sub';
  const maxEv = isHook ? 1 : isSub ? 48 : 6;

  const safeEvents = (Array.isArray(events) ? events : [])
    .map((e) => ({
      label: String(e.label || e.word || e.name || '').slice(0, isSub ? 42 : 48),
      sub: String(e.sub || e.query_en || e.query_id || '').slice(0, 80),
      start: Math.max(0, Number(e.start ?? e.t0 ?? 0) || 0),
      end: Math.max(
        0.5,
        Number(e.end ?? e.t1 ?? ((Number(e.start) || 0) + 2.4)) || 2.4,
      ),
      thumb: e.thumb || e.image_url || e.image || '',
    }))
    .filter((e) => e.label)
    .slice(0, maxEv);

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
  if (path.isAbsolute(mediaSrc) || mediaSrc.includes('://')) {
    if (!mediaSrc.startsWith('http')) mediaSrc = 'base.mp4';
  }

  const bottoms = isHook
    ? [meta.y || 200]
    : isSub
      ? [meta.y || 260]
      : [220, 360, 500, 640];

  const cards = safeEvents
    .map((ev, i) => {
      const id = `lt${i}`;
      const start = ev.start;
      const cardDur = Math.max(0.5, ev.end - ev.start);
      const accent = meta.accent || ACCENTS[i % ACCENTS.length];
      const bottom = bottoms[Math.min(i, bottoms.length - 1)];
      const showThumb = !isHook && !isSub && ev.thumb && !String(ev.thumb).startsWith('file://');
      const thumbHtml = showThumb
        ? `<img class="thumb" src="${escAttr(ev.thumb)}" alt="" width="88" height="88"/>`
        : '';
      const kicker = meta.kicker
        ? `<div class="kicker">${esc(meta.kicker)}</div>`
        : (ev.sub && !isSub ? `<div class="kicker">${esc(ev.sub)}</div>` : '');
      const cls = [
        'clip', 'lt',
        meta.glow ? 'glow' : '',
        meta.tape ? 'tape' : '',
        meta.big ? 'big' : '',
        meta.clean ? 'clean' : '',
        meta.pos === 'center' ? 'center' : '',
        meta.pos === 'top' ? 'top' : '',
      ].filter(Boolean).join(' ');
      return `
    <div id="${id}" class="${cls}" data-start="${start}" data-duration="${cardDur}" data-track-index="1"
         style="bottom:${bottom}px;border-left-color:${accent};--accent:${accent}">
      ${thumbHtml}
      <div class="meta">
        ${kicker}
        <div class="label">${esc(ev.label)}</div>
        ${ev.sub && !isHook && !isSub ? `<div class="sub">${esc(ev.sub)}</div>` : ''}
      </div>
    </div>`;
    })
    .join('\n');

  const gsapLines = safeEvents
    .map((_, i) => {
      const id = `#lt${i}`;
      const start = safeEvents[i].start;
      const end = safeEvents[i].end;
      const fromY = isHook ? (meta.pos === 'top' ? -30 : 28) : 18;
      return [
        `tl.from("${id}", { opacity: 0, y: ${fromY}, scale: 0.96, duration: 0.28 }, ${start});`,
        `tl.to("${id}", { opacity: 0, y: 10, duration: 0.18 }, ${Math.max(start, end - 0.2)});`,
      ].join('\n      ');
    })
    .join('\n      ');

  return `<!doctype html>
<html lang="en" data-resolution="portrait" data-template="${escAttr(tplKey)}">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=1080, height=1920" />
  <title>AutoCliper HF · ${esc(tplKey)}</title>
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
      border-left: 6px solid var(--accent, #22d3ee);
      box-shadow: 0 12px 40px rgba(0,0,0,0.45);
      color: #f8fafc;
    }
    .lt.top { left: 0; right: 0; border-radius: 0; border-left: none; border-bottom: 4px solid var(--accent); justify-content: center; text-align: center; }
    .lt.center { left: 60px; right: 60px; }
    .lt.big .label { font-size: 56px; letter-spacing: -0.04em; }
    .lt.glow { box-shadow: 0 0 40px color-mix(in srgb, var(--accent) 55%, transparent), 0 12px 40px rgba(0,0,0,0.45); backdrop-filter: blur(10px); }
    .lt.tape { background: var(--accent); color: #111; border-left: none; transform: rotate(-1.5deg); }
    .lt.tape .label { color: #111; font-weight: 900; }
    .lt.tape .kicker { color: #111; opacity: 0.7; }
    .lt.clean { background: rgba(0,0,0,0.55); border-left: none; border-radius: 12px; justify-content: center; text-align: center; }
    .lt .thumb {
      width: 88px; height: 88px; border-radius: 14px;
      object-fit: cover; background: #1e293b; flex-shrink: 0;
    }
    .lt .meta { min-width: 0; flex: 1; }
    .lt.top .meta, .lt.clean .meta, .lt.center .meta { text-align: center; }
    .lt .kicker {
      font-size: 14px; font-weight: 600; letter-spacing: 0.08em;
      text-transform: uppercase; opacity: 0.55; margin-bottom: 4px;
    }
    .lt .label {
      font-size: ${isSub ? '34px' : '38px'}; font-weight: 800; letter-spacing: -0.03em;
      line-height: 1.1; ${isSub ? '' : 'white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'}
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
