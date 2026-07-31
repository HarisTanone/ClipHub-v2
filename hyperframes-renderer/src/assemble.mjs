/**
 * Deterministic template + JSON → HyperFrames-valid composition.
 * Hook/subtitle templates own a distinct visual language from Remotion.
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
  const disk = fs.existsSync(TEMPLATES)
    ? fs.readdirSync(TEMPLATES).filter((n) => fs.existsSync(path.join(TEMPLATES, n, 'index.html')))
    : [];
  return [...new Set([...disk, ...Object.keys(TPL)])].sort();
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

/** HyperFrames-native styles. Legacy v1 IDs remain for existing saved jobs. */
const TPL = {
  lower_third_v1: { kind: 'polish', design: 'entity-card', accent: '#22d3ee', y: 220 },
  lower_third: { kind: 'polish', design: 'entity-card', accent: '#a78bfa', y: 240 },

  hook_chromatic_gate_v2: { kind: 'hook', design: 'chromatic-gate', accent: '#ff2e88', y: 760 },
  hook_orbit_stamp_v2: { kind: 'hook', design: 'orbit-stamp', accent: '#8b5cf6', y: 650 },
  hook_pixel_ticker_v2: { kind: 'hook', design: 'pixel-ticker', accent: '#f7ff58', y: 1320 },
  hook_blueprint_v2: { kind: 'hook', design: 'blueprint-reveal', accent: '#52c7ff', y: 720 },

  sub_speech_capsule_v2: { kind: 'sub', design: 'speech-capsule', accent: '#ffffff', y: 330 },
  sub_signal_rail_v2: { kind: 'sub', design: 'signal-rail', accent: '#b7ff00', y: 280 },
  sub_vertical_caption_v2: { kind: 'sub', design: 'vertical-caption', accent: '#00d9ff', y: 520 },
  sub_notch_transcript_v2: { kind: 'sub', design: 'notch-transcript', accent: '#ffb000', y: 260 },

  hook_banner_v1: { kind: 'hook', design: 'legacy-banner', accent: '#f97316', y: 160 },
  hook_neon_v1: { kind: 'hook', design: 'legacy-neon', accent: '#22d3ee', y: 820 },
  hook_tape_v1: { kind: 'hook', design: 'legacy-tape', accent: '#facc15', y: 200 },
  hook_lower_v1: { kind: 'hook', design: 'legacy-lower', accent: '#34d399', y: 280 },
  sub_caption_v1: { kind: 'sub', design: 'legacy-caption', accent: '#f8fafc', y: 980 },
  sub_neon_v1: { kind: 'sub', design: 'legacy-neon-sub', accent: '#a78bfa', y: 1000 },
  sub_box_v1: { kind: 'sub', design: 'legacy-box', accent: '#38bdf8', y: 260 },
  sub_minimal_v1: { kind: 'sub', design: 'legacy-minimal', accent: '#e2e8f0', y: 220 },
};

function cardBody(meta, ev, i) {
  const label = `<div class="label">${esc(ev.label)}</div>`;
  switch (meta.design) {
    case 'chromatic-gate':
      return `<div class="gate-code">HF//${String(i + 1).padStart(2, '0')}</div><div class="gate-copy">${label}</div><div class="gate-bars"><i></i><i></i><i></i></div>`;
    case 'orbit-stamp':
      return `<div class="orbit-ring orbit-a"></div><div class="orbit-ring orbit-b"></div><div class="orbit-copy"><span>HYPER / SIGNAL</span>${label}<b>● VERIFIED</b></div>`;
    case 'pixel-ticker':
      return `<div class="pixel-count">0${i + 1}</div><div class="pixel-copy"><span>HF_BREAKPOINT</span>${label}</div><div class="pixel-grid">${'<i></i>'.repeat(8)}</div>`;
    case 'blueprint-reveal':
      return `<div class="blueprint-grid"></div><div class="blueprint-index">FIG. ${String(i + 1).padStart(2, '0')}</div><div class="blueprint-copy">${label}<span>1080 / 1920 · LOCKED</span></div><div class="blueprint-cross">+</div>`;
    case 'speech-capsule':
      return `<div class="capsule-dot"></div>${label}<div class="capsule-tail"></div>`;
    case 'signal-rail':
      return `${label}<div class="signal-track"><i></i><b></b></div><span class="signal-code">HF LIVE TRANSCRIPT</span>`;
    case 'vertical-caption':
      return `<div class="vertical-index">${String(i + 1).padStart(2, '0')} / HF</div><div class="vertical-copy">${label}</div>`;
    case 'notch-transcript':
      return `<div class="notch-status"><i></i> REC</div>${label}<div class="notch-cursor"></div>`;
    default: {
      const kicker = meta.kind === 'hook' ? '<div class="legacy-kicker">HOOK</div>' : '';
      const sub = ev.sub && meta.kind === 'polish' ? `<div class="legacy-sub">${esc(ev.sub)}</div>` : '';
      return `${kicker}${label}${sub}`;
    }
  }
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

  const cards = safeEvents
    .map((ev, i) => {
      const id = `lt${i}`;
      const start = ev.start;
      const cardDur = Math.max(0.5, ev.end - ev.start);
      const accent = meta.accent || ACCENTS[i % ACCENTS.length];
      const bottom = isHook || isSub ? (meta.y || 260) : [220, 360, 500, 640][Math.min(i, 3)];
      const showThumb = !isHook && !isSub && ev.thumb && !String(ev.thumb).startsWith('file://');
      const thumbHtml = showThumb
        ? `<img class="thumb" src="${escAttr(ev.thumb)}" alt="" width="88" height="88"/>`
        : '';
      return `
    <div id="${id}" class="clip hf-card hf-${escAttr(tplKey)} design-${escAttr(meta.design)}"
         data-design="${escAttr(meta.design)}" data-start="${start}" data-duration="${cardDur}" data-track-index="1"
         data-layout-allow-overflow data-layout-allow-overlap
         style="bottom:${bottom}px;--accent:${accent}">
      ${thumbHtml}
      ${cardBody(meta, ev, i)}
    </div>`;
    })
    .join('\n');

  const gsapLines = safeEvents
    .map((_, i) => {
      const id = `#lt${i}`;
      const start = safeEvents[i].start;
      const end = safeEvents[i].end;
      const entrances = {
        'chromatic-gate': `{ opacity: 0, x: -150, skewX: -12, duration: 0.34 }`,
        'orbit-stamp': `{ opacity: 0, rotation: -18, scale: 0.55, duration: 0.42 }`,
        'pixel-ticker': `{ opacity: 0, x: 180, duration: 0.24 }`,
        'blueprint-reveal': `{ opacity: 0, scaleX: 0.12, transformOrigin: "left center", duration: 0.38 }`,
        'speech-capsule': `{ opacity: 0, y: 42, scale: 0.88, duration: 0.24 }`,
        'signal-rail': `{ opacity: 0, x: -70, duration: 0.22 }`,
        'vertical-caption': `{ opacity: 0, x: -120, duration: 0.3 }`,
        'notch-transcript': `{ opacity: 0, y: 70, duration: 0.28 }`,
      };
      const entrance = entrances[meta.design] || `{ opacity: 0, y: 28, scale: 0.96, duration: 0.28 }`;
      return [
        `tl.from("${id}", ${entrance}, ${start});`,
        `tl.to("${id}", { opacity: 0, y: 10, duration: 0.18 }, ${Math.max(start, end - 0.2)});`,
      ].join('\n      ');
    })
    .join('\n      ');

  return `<!doctype html>
<html lang="en" data-resolution="portrait" data-template="${escAttr(tplKey)}" data-design="${escAttr(meta.design)}">
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
    .hf-card {
      position: absolute; left: 64px; right: 64px; color: #fff;
      font-family: Inter, Arial, sans-serif;
    }
    .hf-card .label { overflow-wrap: anywhere; }
    .hf-card .thumb {
      width: 88px; height: 88px; border-radius: 14px;
      object-fit: cover; background: #1e293b; flex-shrink: 0;
    }
    .design-entity-card, [class*="design-legacy-"] {
      display: flex; align-items: center; gap: 18px; padding: 22px 26px;
      border-radius: 20px; background: rgba(8,10,16,.88); border-left: 7px solid var(--accent);
      box-shadow: 0 18px 50px rgba(0,0,0,.5);
    }
    .design-entity-card .label, [class*="design-legacy-"] .label { font-size: 42px; font-weight: 850; line-height: 1.2; }
    .legacy-kicker, .legacy-sub { font-size: 20px; opacity: .7; letter-spacing: .12em; }

    .design-chromatic-gate {
      display: grid; grid-template-columns: 110px 1fr 32px; align-items: stretch;
      min-height: 240px; background: #09090b; border: 3px solid #ff2e88;
      box-shadow: -16px 16px 0 #00e5ff, 18px -18px 0 rgba(255,46,136,.24);
      clip-path: polygon(0 0, 94% 0, 100% 22%, 100% 100%, 6% 100%, 0 76%);
    }
    .gate-code { writing-mode: vertical-rl; transform: rotate(180deg); padding: 28px 34px; background: #ff2e88; color: #09090b; font: 900 22px monospace; letter-spacing: .2em; }
    .gate-copy { display: flex; align-items: center; padding: 34px 38px; }
    .gate-copy .label { font-size: 64px; font-weight: 950; line-height: 1.18; letter-spacing: -.045em; text-transform: uppercase; }
    .gate-bars { display: flex; flex-direction: column; justify-content: center; gap: 12px; }
    .gate-bars i { width: 14px; height: 34px; background: #00e5ff; }

    .design-orbit-stamp { width: 760px; height: 430px; left: 160px; right: auto; display: grid; place-items: center; }
    .orbit-ring { position: absolute; inset: 16px 180px; border-radius: 50%; border: 4px solid var(--accent); }
    .orbit-b { inset: 58px 135px; border-style: dashed; transform: rotate(28deg); opacity: .65; }
    .orbit-copy { z-index: 1; width: 560px; padding: 42px; text-align: center; background: rgba(9,9,18,.86); border-radius: 50%; border: 2px solid #fff; }
    .orbit-copy span, .orbit-copy b { display: block; font: 800 16px monospace; letter-spacing: .18em; color: var(--accent); }
    .orbit-copy .label { margin: 18px 0; font-size: 58px; font-weight: 900; line-height: 1.18; }

    .design-pixel-ticker { display: grid; grid-template-columns: 132px 1fr 108px; min-height: 190px; background: #090b0d; border: 5px solid #f7ff58; box-shadow: 14px 14px 0 #ff2e88; }
    .pixel-count { display: grid; place-items: center; background: #f7ff58; color: #090b0d; font: 900 66px monospace; }
    .pixel-copy { padding: 30px 34px; }
    .pixel-copy span { color: #f7ff58; font: 800 16px monospace; letter-spacing: .14em; }
    .pixel-copy .label { margin-top: 12px; font: 900 52px/1.2 monospace; text-transform: uppercase; }
    .pixel-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 7px; padding: 26px; }
    .pixel-grid i { background: #ff2e88; }

    .design-blueprint-reveal { min-height: 280px; overflow: hidden; padding: 38px 48px; background: rgba(5,35,62,.91); border: 3px solid #52c7ff; }
    .blueprint-grid { position: absolute; inset: 0; opacity: .3; background-image: linear-gradient(#52c7ff 1px,transparent 1px),linear-gradient(90deg,#52c7ff 1px,transparent 1px); background-size: 30px 30px; }
    .blueprint-index { position: relative; color: #52c7ff; font: 800 19px monospace; letter-spacing: .18em; }
    .blueprint-copy { position: relative; margin-top: 24px; border-left: 5px solid #fff; padding-left: 30px; }
    .blueprint-copy .label { font-size: 60px; font-weight: 850; line-height: 1.18; }
    .blueprint-copy span { display: block; margin-top: 16px; color: #52c7ff; font: 700 16px monospace; }
    .blueprint-cross { position: absolute; right: 30px; top: 16px; color: #52c7ff; font: 300 80px monospace; }

    .design-speech-capsule { left: 130px; right: 130px; display: flex; align-items: center; gap: 22px; padding: 26px 36px; border-radius: 70px; background: #fff; color: #0a0a0a; box-shadow: 0 14px 0 rgba(0,0,0,.6); }
    .capsule-dot { width: 18px; height: 18px; flex: 0 0 auto; border-radius: 50%; background: #ff2e88; }
    .design-speech-capsule .label { flex: 1; text-align: center; font-size: 42px; font-weight: 850; line-height: 1.22; }
    .capsule-tail { position: absolute; left: 96px; bottom: -28px; border: 18px solid transparent; border-top: 30px solid #fff; transform: rotate(12deg); }

    .design-signal-rail { padding: 22px 28px 28px; background: rgba(5,8,8,.9); border-top: 2px solid #b7ff00; }
    .design-signal-rail .label { font: 800 42px/1.22 monospace; text-transform: uppercase; }
    .signal-track { position: relative; height: 10px; margin-top: 18px; background: #243020; }
    .signal-track i { display: block; width: 68%; height: 100%; background: #b7ff00; }
    .signal-track b { position: absolute; left: 68%; top: -7px; width: 24px; height: 24px; border-radius: 50%; background: #fff; box-shadow: 0 0 20px #b7ff00; }
    .signal-code { display: block; margin-top: 14px; color: #b7ff00; font: 700 14px monospace; letter-spacing: .18em; }

    .design-vertical-caption { left: 42px; right: auto; width: 720px; display: grid; grid-template-columns: 88px 1fr; background: rgba(7,10,14,.9); border: 2px solid #00d9ff; }
    .vertical-index { writing-mode: vertical-rl; transform: rotate(180deg); padding: 22px 28px; background: #00d9ff; color: #061015; font: 900 18px monospace; letter-spacing: .16em; }
    .vertical-copy { padding: 34px; }
    .vertical-copy .label { font-size: 44px; font-weight: 850; line-height: 1.22; }

    .design-notch-transcript { left: 120px; right: 120px; display: grid; grid-template-columns: 90px 1fr 20px; align-items: center; gap: 20px; padding: 24px 30px; border-radius: 36px 36px 12px 12px; background: #050505; border-bottom: 3px solid #ffb000; }
    .notch-status { color: #ffb000; font: 800 16px monospace; }
    .notch-status i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #ff385c; }
    .design-notch-transcript .label { font: 750 38px/1.22 monospace; }
    .notch-cursor { width: 5px; height: 48px; background: #ffb000; box-shadow: 0 0 16px #ffb000; }
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
