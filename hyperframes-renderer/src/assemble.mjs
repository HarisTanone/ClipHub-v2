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

const ACCENTS = ['#22d3ee', '#a78bfa', '#f472b6', '#34d399', '#facc15', '#00f0ff', '#ef4444', '#10b981'];

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

/** 
 * HyperFrames-native styles (12 distinct hook/polish designs + legacy).
 * Portrait coordinates (1080x1920):
 *  - bottom: 1480-1650px lands in the upper third (safe from karaoke subtitles at bottom).
 */
const TPL = {
  // ─── 12 Distinct Hook & Polish Styles ──────────────────────────────────
  hook_cyber_hud: { kind: 'hook', design: 'cyber-hud', accent: '#00f0ff', y: 1540 },
  hook_glass_minimal: { kind: 'hook', design: 'glass-minimal', accent: '#a78bfa', y: 1560 },
  hook_breaking_news: { kind: 'hook', design: 'breaking-news', accent: '#ef4444', y: 1620 },
  hook_retro_synth: { kind: 'hook', design: 'retro-synth', accent: '#f43f5e', y: 1520 },
  hook_comic_pop: { kind: 'hook', design: 'comic-pop', accent: '#facc15', y: 1550 },
  hook_editorial_pill: { kind: 'hook', design: 'editorial-pill', accent: '#e2e8f0', y: 1600 },
  hook_gradient_aura: { kind: 'hook', design: 'gradient-aura', accent: '#38bdf8', y: 1540 },
  hook_cinema_tape: { kind: 'hook', design: 'cinema-tape', accent: '#eab308', y: 1640 },
  hook_hologram_scan: { kind: 'hook', design: 'hologram-scan', accent: '#06b6d4', y: 1540 },
  hook_luxury_noir: { kind: 'hook', design: 'luxury-noir', accent: '#d4af37', y: 1560 },
  hook_floating_badge: { kind: 'hook', design: 'floating-badge', accent: '#10b981', y: 1650 },
  hook_kinetic_split: { kind: 'hook', design: 'kinetic-split', accent: '#f97316', y: 1530 },

  // Polish lower-third templates (safe upper placement)
  lower_third_v1: { kind: 'polish', design: 'entity-card', accent: '#22d3ee', y: 1520 },
  lower_third: { kind: 'polish', design: 'glass-minimal', accent: '#a78bfa', y: 1540 },

  // Additional v2 Hook & Subtitle Templates
  hook_chromatic_gate_v2: { kind: 'hook', design: 'chromatic-gate', accent: '#ff2e88', y: 1480 },
  hook_orbit_stamp_v2: { kind: 'hook', design: 'orbit-stamp', accent: '#8b5cf6', y: 1460 },
  hook_pixel_ticker_v2: { kind: 'hook', design: 'pixel-ticker', accent: '#f7ff58', y: 1540 },
  hook_blueprint_v2: { kind: 'hook', design: 'blueprint-reveal', accent: '#52c7ff', y: 1480 },
  hook_neon_matrix: { kind: 'hook', design: 'neon-matrix', accent: '#10b981', y: 1540 },
  hook_warning_hazard: { kind: 'hook', design: 'warning-hazard', accent: '#f59e0b', y: 1550 },
  hook_sticker_scrapbook: { kind: 'hook', design: 'sticker-scrapbook', accent: '#ec4899', y: 1530 },
  hook_cinematic_minimal: { kind: 'hook', design: 'cinematic-minimal', accent: '#f8fafc', y: 1560 },
  hook_electric_surge: { kind: 'hook', design: 'electric-surge', accent: '#818cf8', y: 1540 },

  sub_speech_capsule_v2: { kind: 'sub', design: 'speech-capsule', accent: '#ffffff', y: 330 },
  sub_signal_rail_v2: { kind: 'sub', design: 'signal-rail', accent: '#b7ff00', y: 280 },
  sub_vertical_caption_v2: { kind: 'sub', design: 'vertical-caption', accent: '#00d9ff', y: 520 },
  sub_notch_transcript_v2: { kind: 'sub', design: 'notch-transcript', accent: '#ffb000', y: 260 },

  // Legacy fallback styles
  hook_banner_v1: { kind: 'hook', design: 'legacy-banner', accent: '#f97316', y: 1560 },
  hook_neon_v1: { kind: 'hook', design: 'legacy-neon', accent: '#22d3ee', y: 1520 },
  hook_tape_v1: { kind: 'hook', design: 'cinema-tape', accent: '#facc15', y: 1600 },
  hook_lower_v1: { kind: 'hook', design: 'entity-card', accent: '#34d399', y: 1540 },
  sub_caption_v1: { kind: 'sub', design: 'legacy-caption', accent: '#f8fafc', y: 980 },
  sub_neon_v1: { kind: 'sub', design: 'legacy-neon-sub', accent: '#a78bfa', y: 1000 },
  sub_box_v1: { kind: 'sub', design: 'legacy-box', accent: '#38bdf8', y: 260 },
  sub_minimal_v1: { kind: 'sub', design: 'legacy-minimal', accent: '#e2e8f0', y: 220 },
};

function cardBody(meta, ev, i) {
  const label = `<div class="label">${esc(ev.label)}</div>`;
  const subText = ev.sub ? `<div class="sub-text">${esc(ev.sub)}</div>` : '';
  
  switch (meta.design) {
    case 'cyber-hud':
      return `<div class="hud-tag"><span>SYS//HOOK</span><i></i><b>#0${i + 1}</b></div><div class="hud-content">${label}${subText}</div><div class="hud-corners"><s></s><s></s></div>`;
    
    case 'glass-minimal':
      return `<div class="glass-pill"><span class="glass-dot"></span><div class="glass-content">${label}${subText}</div></div>`;
    
    case 'breaking-news':
      return `<div class="news-badge"><span>● LIVE</span><b>UPDATE</b></div><div class="news-content">${label}</div>`;
    
    case 'retro-synth':
      return `<div class="synth-tubes"><i></i></div><div class="synth-content"><span class="synth-tag">TOPIC // REVEAL</span>${label}${subText}</div><div class="synth-glow"></div>`;
    
    case 'comic-pop':
      return `<div class="comic-burst"><span class="comic-tag">HEY!</span>${label}</div>`;
    
    case 'editorial-pill':
      return `<div class="edit-dot"></div><div class="edit-content"><span class="edit-kicker">FOCUS</span>${label}</div>`;
    
    case 'gradient-aura':
      return `<div class="aura-mesh"></div><div class="aura-content">${label}${subText}</div>`;
    
    case 'cinema-tape':
      return `<div class="tape-stripes"></div><div class="tape-text">${label}</div><div class="tape-stripes"></div>`;
    
    case 'hologram-scan':
      return `<div class="holo-scanline"></div><div class="holo-header"><span class="holo-dot"></span><b>DATA_FEED // 0${i + 1}</b></div>${label}${subText}`;
    
    case 'luxury-noir':
      return `<div class="noir-border"></div><div class="noir-content"><span class="noir-tag">INSIGHT</span>${label}${subText}</div>`;
    
    case 'floating-badge':
      return `<div class="float-dot"></div><div class="float-text"><span class="float-tag">TOPIC</span>${label}</div>`;
    
    case 'kinetic-split':
      return `<div class="split-side"><b>0${i + 1}</b></div><div class="split-main">${label}${subText}</div>`;

    case 'chromatic-gate':
      return `<div class="gate-code">HF//${String(i + 1).padStart(2, '0')}</div><div class="gate-copy">${label}</div><div class="gate-bars"><i></i><i></i><i></i></div>`;
    case 'orbit-stamp':
      return `<div class="orbit-ring orbit-a"></div><div class="orbit-ring orbit-b"></div><div class="orbit-copy"><span>HYPER / SIGNAL</span>${label}<b>● VERIFIED</b></div>`;
    case 'pixel-ticker':
      return `<div class="pixel-count">0${i + 1}</div><div class="pixel-copy"><span>HF_BREAKPOINT</span>${label}</div><div class="pixel-grid">${'<i></i>'.repeat(8)}</div>`;
    case 'blueprint-reveal':
      return `<div class="blueprint-grid"></div><div class="blueprint-index">FIG. ${String(i + 1).padStart(2, '0')}</div><div class="blueprint-copy">${label}<span>1080 / 1920 · LOCKED</span></div><div class="blueprint-cross">+</div>`;
    case 'neon-matrix':
      return `<div class="matrix-header"><span>[SYS_ALERT::ROOT]</span><span class="matrix-status">ONLINE</span></div><div class="matrix-copy">&gt; ${label}<span class="matrix-cursor">_</span></div>`;
    case 'warning-hazard':
      return `<div class="hazard-badge"><span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block;vertical-align:-1px;margin-right:4px;"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>CRITICAL NOTICE</span><span>! ! !</span></div><div class="hazard-content">${label}</div><div class="hazard-bar"></div>`;
    case 'sticker-scrapbook':
      return `<div class="scrapbook-tape">TAPE</div><div class="scrapbook-body">${label}</div>`;
    case 'cinematic-minimal':
      return `<div class="cine-kicker">ESSENTIAL DOSSIER</div><div class="cine-body">${label}</div>`;
    case 'electric-surge':
      return `<div class="surge-header"><span><svg width="12" height="12" viewBox="0 0 24 24" fill="#facc15" stroke="#facc15" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block;vertical-align:-1px;margin-right:4px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>VOLTAGE SURGE</span></div><div class="surge-content">${label}</div>`;
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
  template = 'hook_cyber_hud',
  baseSrc = 'base.mp4',
  events = [],
  duration = 0,
} = {}) {
  const tplKey = String(template || 'hook_cyber_hud');
  const meta = TPL[tplKey] || TPL.hook_cyber_hud;
  const isHook = meta.kind === 'hook';
  const isSub = meta.kind === 'sub';
  const maxEv = isHook ? 1 : isSub ? 48 : 6;

  const safeEvents = (Array.isArray(events) ? events : [])
    .map((e) => ({
      label: String(e.label || e.word || e.name || '').slice(0, isSub ? 42 : 56),
      sub: String(e.sub || e.query_en || e.query_id || '').slice(0, 80),
      start: Math.max(0, Number(e.start ?? e.t0 ?? 0) || 0),
      end: Math.max(
        0.5,
        Number(e.end ?? e.t1 ?? ((Number(e.start) || 0) + 2.8)) || 2.8,
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
      const bottom = isHook || isSub ? (meta.y || 1540) : [1560, 1420, 1280, 1140][Math.min(i, 3)];
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
        'cyber-hud': `{ opacity: 0, scale: 0.9, y: -20, duration: 0.32, ease: "back.out(1.7)" }`,
        'glass-minimal': `{ opacity: 0, y: -30, backdropFilter: "blur(0px)", duration: 0.36, ease: "power2.out" }`,
        'breaking-news': `{ opacity: 0, x: -100, duration: 0.28, ease: "power3.out" }`,
        'retro-synth': `{ opacity: 0, scale: 0.85, duration: 0.34, ease: "elastic.out(1, 0.75)" }`,
        'comic-pop': `{ opacity: 0, scale: 0.4, rotation: -12, duration: 0.3, ease: "back.out(2)" }`,
        'editorial-pill': `{ opacity: 0, y: -25, duration: 0.3, ease: "power2.out" }`,
        'gradient-aura': `{ opacity: 0, scale: 0.92, duration: 0.4, ease: "power2.out" }`,
        'cinema-tape': `{ opacity: 0, x: 120, duration: 0.26, ease: "power2.out" }`,
        'hologram-scan': `{ opacity: 0, scaleY: 0.2, duration: 0.32, ease: "expo.out" }`,
        'luxury-noir': `{ opacity: 0, y: -20, duration: 0.38, ease: "power3.out" }`,
        'floating-badge': `{ opacity: 0, x: -50, scale: 0.8, duration: 0.28, ease: "back.out(1.5)" }`,
        'kinetic-split': `{ opacity: 0, x: -80, duration: 0.32, ease: "power2.out" }`,
        'chromatic-gate': `{ opacity: 0, x: -150, skewX: -12, duration: 0.34 }`,
        'orbit-stamp': `{ opacity: 0, rotation: -18, scale: 0.55, duration: 0.42 }`,
        'pixel-ticker': `{ opacity: 0, x: 180, duration: 0.24 }`,
        'blueprint-reveal': `{ opacity: 0, scaleX: 0.12, transformOrigin: "left center", duration: 0.38 }`,
        'neon-matrix': `{ opacity: 0, scaleY: 0.1, duration: 0.28, ease: "steps(6)" }`,
        'warning-hazard': `{ opacity: 0, scale: 1.25, y: -40, duration: 0.3, ease: "bounce.out" }`,
        'sticker-scrapbook': `{ opacity: 0, rotation: 14, scale: 0.5, duration: 0.35, ease: "back.out(2)" }`,
        'cinematic-minimal': `{ opacity: 0, letterSpacing: "0.2em", duration: 0.45, ease: "power2.out" }`,
        'electric-surge': `{ opacity: 0, scale: 0.8, x: -30, duration: 0.25, ease: "rough({strength: 2, points: 10})" }`,
      };
      const entrance = entrances[meta.design] || `{ opacity: 0, y: -20, scale: 0.96, duration: 0.28 }`;
      return [
        `tl.from("${id}", ${entrance}, ${start});`,
        `tl.to("${id}", { opacity: 0, y: -15, duration: 0.22 }, ${Math.max(start, end - 0.25)});`,
      ].join('\n      ');
    })
    .join('\n      ');

  return `<!doctype html>
<html lang="en" data-resolution="portrait" data-template="${escAttr(tplKey)}" data-design="${escAttr(meta.design)}">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=1080, height=1920" />
  <title>AutoCliper HF · ${esc(tplKey)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@700;900&family=Inter:wght@400;600;800;900&family=Space+Grotesk:wght@700;900&family=Syne:wght@800;900&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      margin: 0; width: 1080px; height: 1920px;
      overflow: hidden; background: #000;
      font-family: Inter, system-ui, -apple-system, sans-serif;
    }
    .hf-card {
      position: absolute; left: 56px; right: 56px; color: #fff;
      z-index: 20;
    }
    .hf-card .label { overflow-wrap: anywhere; }
    .hf-card .sub-text { font-size: 20px; opacity: 0.8; margin-top: 4px; font-weight: 500; }
    .hf-card .thumb {
      width: 88px; height: 88px; border-radius: 14px;
      object-fit: cover; background: #1e293b; flex-shrink: 0;
    }

    /* ─── 1. Cyberpunk Tech HUD ────────────────────────────────────────── */
    .design-cyber-hud {
      background: rgba(6, 10, 20, 0.95); border: 2px solid var(--accent);
      border-radius: 18px; padding: 24px 32px;
      box-shadow: 0 0 35px rgba(0,240,255,0.4), inset 0 0 18px rgba(0,240,255,0.18);
      position: relative;
    }
    .design-cyber-hud .hud-tag {
      display: flex; align-items: center; justify-content: space-between;
      color: var(--accent); font: 900 16px monospace; letter-spacing: 0.18em; margin-bottom: 10px;
      border-bottom: 1px solid rgba(0,240,255,0.3); padding-bottom: 6px;
    }
    .design-cyber-hud .hud-tag span { display: flex; align-items: center; gap: 8px; }
    .design-cyber-hud .hud-tag i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #00f0ff; box-shadow: 0 0 10px #00f0ff; }
    .design-cyber-hud .hud-tag b { background: rgba(0,240,255,0.2); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(0,240,255,0.4); font-size: 13px; }
    .design-cyber-hud .label { font-family: 'Space Grotesk', Inter, sans-serif; font-size: 48px; font-weight: 950; line-height: 1.15; color: #fff; text-shadow: 0 0 16px rgba(0,240,255,0.7); }
    .design-cyber-hud .hud-corners s { position: absolute; width: 14px; height: 14px; border: 3px solid #00f0ff; filter: drop-shadow(0 0 4px #00f0ff); }
    .design-cyber-hud .hud-corners s:nth-child(1) { top: -3px; left: -3px; border-right: 0; border-bottom: 0; }
    .design-cyber-hud .hud-corners s:nth-child(2) { bottom: -3px; right: -3px; border-left: 0; border-top: 0; }

    /* ─── 2. Frosted Glassmorphism ─────────────────────────────────────── */
    .design-glass-minimal {
      display: flex; align-items: center; gap: 20px;
      background: rgba(255, 255, 255, 0.14); backdrop-filter: blur(40px); -webkit-backdrop-filter: blur(40px);
      border: 1.5px solid rgba(255, 255, 255, 0.38); border-radius: 32px; padding: 26px 38px;
      box-shadow: 0 24px 60px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.45);
    }
    .design-glass-minimal .glass-dot { width: 16px; height: 16px; border-radius: 50%; background: #a78bfa; box-shadow: 0 0 20px #a78bfa; flex-shrink: 0; }
    .design-glass-minimal .label { font-size: 46px; font-weight: 900; line-height: 1.15; color: #ffffff; letter-spacing: -0.02em; text-shadow: 0 2px 10px rgba(0,0,0,0.3); }

    /* ─── 3. Breaking News Live Banner ─────────────────────────────────── */
    .design-breaking-news {
      display: grid; grid-template-columns: 160px 1fr;
      background: #0d0d12; border: 3px solid #ef4444; border-radius: 14px; overflow: hidden;
      box-shadow: 0 16px 40px rgba(239,68,68,0.3);
    }
    .design-breaking-news .news-badge {
      background: #ef4444; color: #fff; padding: 18px 20px; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center;
    }
    .design-breaking-news .news-badge span { font: 900 13px monospace; letter-spacing: 0.12em; color: #fef08a; }
    .design-breaking-news .news-badge b { font: 950 20px/1 Inter, sans-serif; letter-spacing: -0.02em; text-transform: uppercase; margin-top: 3px; }
    .design-breaking-news .news-content { padding: 22px 28px; display: flex; align-items: center; }
    .design-breaking-news .label { font-size: 42px; font-weight: 900; line-height: 1.15; text-transform: uppercase; letter-spacing: -0.02em; color: #fff; }

    /* ─── 4. Retro 80s Synthwave ───────────────────────────────────────── */
    .design-retro-synth {
      background: linear-gradient(135deg, rgba(20,8,35,0.94), rgba(40,10,60,0.92));
      border: 3px solid #f43f5e; border-radius: 20px; padding: 26px 32px;
      box-shadow: 0 0 35px rgba(244,63,94,0.4), inset 0 0 20px rgba(0,240,255,0.2);
    }
    .design-retro-synth .synth-tag { display: block; font: 900 14px monospace; color: #00f0ff; letter-spacing: 0.22em; text-shadow: 0 0 8px #00f0ff; margin-bottom: 6px; }
    .design-retro-synth .label { font-family: 'Syne', sans-serif; font-size: 48px; font-weight: 900; line-height: 1.15; font-style: italic; background: linear-gradient(to right, #fff, #f472b6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }

    /* ─── 5. Comic Pop Burst ───────────────────────────────────────────── */
    .design-comic-pop {
      background: #facc15; border: 5px solid #000; border-radius: 22px; padding: 24px 32px;
      color: #000; transform: rotate(-2.5deg);
      box-shadow: 12px 12px 0 #000;
    }
    .design-comic-pop .comic-tag { display: inline-block; background: #ef4444; color: #fff; font: 950 16px Inter; padding: 4px 10px; border-radius: 8px; border: 2px solid #000; margin-bottom: 6px; }
    .design-comic-pop .label { font-size: 48px; font-weight: 950; line-height: 1.1; letter-spacing: -0.03em; text-transform: uppercase; color: #000; }

    /* ─── 6. Editorial Minimal Pill ────────────────────────────────────── */
    .design-editorial-pill {
      display: flex; align-items: center; gap: 22px;
      background: rgba(10, 10, 12, 0.96); border: 1.5px solid rgba(212,175,55,0.45);
      border-radius: 60px; padding: 22px 40px;
      box-shadow: 0 18px 45px rgba(0,0,0,0.75), 0 0 20px rgba(212,175,55,0.15);
    }
    .design-editorial-pill .edit-dot { width: 16px; height: 16px; border-radius: 50%; background: #d4af37; box-shadow: 0 0 16px #d4af37; flex-shrink: 0; }
    .design-editorial-pill .edit-kicker { display: block; font: 800 13px monospace; color: #d4af37; letter-spacing: 0.28em; text-transform: uppercase; margin-bottom: 2px; }
    .design-editorial-pill .label { font-size: 42px; font-weight: 850; line-height: 1.15; color: #f8fafc; }

    /* ─── 7. Gradient Aura Glow ────────────────────────────────────────── */
    .design-gradient-aura {
      background: rgba(14, 16, 26, 0.92); border-radius: 24px; padding: 26px 36px;
      border: 1px solid rgba(56, 189, 248, 0.4);
      box-shadow: 0 0 50px rgba(56, 189, 248, 0.3), inset 0 0 25px rgba(167, 139, 250, 0.2);
    }
    .design-gradient-aura .label { font-family: 'Space Grotesk', sans-serif; font-size: 46px; font-weight: 900; line-height: 1.15; background: linear-gradient(135deg, #38bdf8, #c084fc, #f472b6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }

    /* ─── 8. Caution Stencil Tape ──────────────────────────────────────── */
    .design-cinema-tape {
      background: #000; border-top: 6px solid #eab308; border-bottom: 6px solid #eab308;
      padding: 24px 32px;
      box-shadow: 0 16px 40px rgba(0,0,0,0.7);
    }
    .design-cinema-tape .tape-text .label { font: 900 46px/1.15 monospace; letter-spacing: 0.05em; color: #eab308; text-transform: uppercase; }

    /* ─── 9. Sci-Fi Hologram Scanner ───────────────────────────────────── */
    .design-hologram-scan {
      background: rgba(6, 25, 45, 0.9); border: 2px solid #06b6d4; border-radius: 18px; padding: 24px 30px;
      box-shadow: 0 0 35px rgba(6,182,212,0.3); position: relative; overflow: hidden;
    }
    .design-hologram-scan .holo-header { display: flex; align-items: center; gap: 8px; color: #06b6d4; font: 800 14px monospace; letter-spacing: 0.16em; margin-bottom: 6px; }
    .design-hologram-scan .holo-dot { width: 8px; height: 8px; border-radius: 50%; background: #06b6d4; }
    .design-hologram-scan .label { font-size: 44px; font-weight: 850; line-height: 1.15; color: #e0f2fe; }

    /* ─── 10. Luxury Obsidian & Gold ───────────────────────────────────── */
    .design-luxury-noir {
      background: linear-gradient(145deg, #09090b, #18181b); border: 2px solid #d4af37;
      border-radius: 20px; padding: 28px 36px;
      box-shadow: 0 20px 50px rgba(0,0,0,0.7), inset 0 0 15px rgba(212,175,55,0.15);
    }
    .design-luxury-noir .noir-tag { display: block; font: 700 13px 'Cinzel', serif; letter-spacing: 0.3em; color: #d4af37; margin-bottom: 6px; }
    .design-luxury-noir .label { font-family: 'Cinzel', serif; font-size: 44px; font-weight: 900; line-height: 1.18; color: #fef08a; letter-spacing: 0.02em; }

    /* ─── 11. Top Floating Badge ───────────────────────────────────────── */
    .design-floating-badge {
      left: 56px; right: auto; max-width: 880px;
      display: flex; align-items: center; gap: 18px;
      background: rgba(6, 22, 16, 0.95); border: 2px solid #10b981; border-radius: 50px; padding: 18px 32px;
      box-shadow: 0 16px 45px rgba(0,0,0,0.7), 0 0 30px rgba(16,185,129,0.35);
    }
    .design-floating-badge .float-dot { width: 14px; height: 14px; border-radius: 50%; background: #10b981; box-shadow: 0 0 16px #10b981; flex-shrink: 0; }
    .design-floating-badge .float-tag { font: 900 15px monospace; color: #10b981; letter-spacing: 0.18em; margin-right: 8px; text-transform: uppercase; }
    .design-floating-badge .label { font-size: 40px; font-weight: 900; line-height: 1.15; color: #fff; }

    /* ─── 12. Kinetic Duotone Split ────────────────────────────────────── */
    .design-kinetic-split {
      display: grid; grid-template-columns: 96px 1fr;
      background: #0f1013; border-radius: 20px; overflow: hidden; border: 2px solid rgba(255,107,0,0.4);
      box-shadow: 0 20px 50px rgba(0,0,0,0.8);
    }
    .design-kinetic-split .split-side { background: linear-gradient(180deg, #ff6b00, #ea580c); color: #fff; display: grid; place-items: center; font: 950 36px/1 monospace; text-shadow: 0 2px 8px rgba(0,0,0,0.4); }
    .design-kinetic-split .split-main { padding: 24px 32px; display: flex; flex-direction: column; justify-content: center; background: rgba(18, 19, 24, 0.95); }
    .design-kinetic-split .label { font-size: 44px; font-weight: 950; line-height: 1.15; color: #fff; letter-spacing: -0.02em; }

    /* ─── Shared Base Polish / Legacy ──────────────────────────────────── */
    .design-entity-card {
      display: flex; align-items: center; gap: 18px; padding: 22px 28px;
      border-radius: 20px; background: rgba(8,10,16,.92); border-left: 7px solid var(--accent);
      box-shadow: 0 18px 50px rgba(0,0,0,.5);
    }
    .design-entity-card .label { font-size: 42px; font-weight: 850; line-height: 1.2; }
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

    /* ─── 17. Matrix Rain Cyber Term ───────────────────────────────────── */
    .design-neon-matrix {
      background: rgba(0, 0, 0, 0.95); border: 2px solid #10b981;
      border-radius: 14px; padding: 22px 28px;
      box-shadow: 0 0 30px rgba(16,185,129,0.4), inset 0 0 15px rgba(16,185,129,0.2);
    }
    .design-neon-matrix .matrix-header {
      display: flex; justify-content: space-between; align-items: center;
      border-bottom: 1px solid rgba(16,185,129,0.3); padding-bottom: 8px; margin-bottom: 10px;
      color: #10b981; font: 800 16px monospace; letter-spacing: 0.12em;
    }
    .design-neon-matrix .matrix-status { color: #6ee7b7; font-weight: 900; }
    .design-neon-matrix .matrix-copy .label {
      font: 900 44px/1.2 monospace; color: #6ee7b7; text-transform: uppercase;
      text-shadow: 0 0 12px #10b981;
    }
    .design-neon-matrix .matrix-cursor { display: inline-block; color: #10b981; }

    /* ─── 18. Warning Industrial Hazard ────────────────────────────────── */
    .design-warning-hazard {
      background: #09090b; border: 4px solid #f59e0b; border-radius: 20px; padding: 22px 28px;
      box-shadow: 0 0 35px rgba(245,158,11,0.35);
    }
    .design-warning-hazard .hazard-badge {
      display: flex; justify-content: space-between; align-items: center;
      background: #f59e0b; color: #000; padding: 6px 14px; border-radius: 6px;
      font: 900 16px monospace; margin-bottom: 12px;
    }
    .design-warning-hazard .label {
      font-size: 46px; font-weight: 950; line-height: 1.15; text-transform: uppercase;
      color: #fde68a; border-left: 6px solid #f59e0b; padding-left: 14px; margin-bottom: 12px;
    }
    .design-warning-hazard .hazard-bar {
      height: 10px; width: 100%; border-radius: 4px;
      background: repeating-linear-gradient(45deg, #f59e0b, #f59e0b 12px, #000 12px, #000 24px);
    }

    /* ─── 19. Y2K Scrapbook Sticker ────────────────────────────────────── */
    .design-sticker-scrapbook {
      background: linear-gradient(135deg, #db2777, #be185d);
      border: 4px dashed #fff; border-radius: 26px; padding: 24px 34px;
      transform: rotate(2.5deg);
      box-shadow: 0 16px 0 rgba(0,0,0,0.6), 0 0 35px rgba(236,72,153,0.5);
    }
    .design-sticker-scrapbook .scrapbook-tape {
      position: absolute; top: -14px; left: 50%; transform: translateX(-50%);
      background: rgba(255,255,255,0.7); color: #000; font: 900 12px monospace;
      padding: 4px 16px; border-radius: 4px; backdrop-filter: blur(4px);
    }
    .design-sticker-scrapbook .label {
      font-size: 48px; font-weight: 950; line-height: 1.15; text-align: center;
      text-transform: uppercase; color: #fef08a; text-shadow: 0 4px 12px rgba(0,0,0,0.8);
    }

    /* ─── 20. Ultra Modern Serif Slate ─────────────────────────────────── */
    .design-cinematic-minimal {
      background: rgba(0,0,0,0.88); border-top: 2px solid rgba(255,255,255,0.4);
      border-bottom: 2px solid rgba(255,255,255,0.4); padding: 26px 36px;
      text-align: center; backdrop-filter: blur(20px);
      box-shadow: 0 20px 50px rgba(0,0,0,0.8);
    }
    .design-cinematic-minimal .cine-kicker {
      font: 700 14px 'Cinzel', serif; letter-spacing: 0.35em; color: #a1a1aa;
      text-transform: uppercase; margin-bottom: 8px;
    }
    .design-cinematic-minimal .label {
      font-family: 'Cinzel', serif; font-size: 46px; font-weight: 700;
      line-height: 1.2; letter-spacing: 0.04em; color: #f4f4f5;
    }

    /* ─── 21. Electric Plasma Shockwave ────────────────────────────────── */
    .design-electric-surge {
      background: linear-gradient(135deg, #0f172a, #1e1b4b);
      border: 3px solid #818cf8; border-radius: 20px; padding: 24px 32px;
      box-shadow: 0 0 40px rgba(129,140,248,0.5), inset 0 0 20px rgba(99,102,241,0.3);
    }
    .design-electric-surge .surge-header {
      color: #a5b4fc; font: 900 15px monospace; letter-spacing: 0.18em; margin-bottom: 6px;
    }
    .design-electric-surge .label {
      font-family: 'Space Grotesk', sans-serif; font-size: 48px; font-weight: 950;
      font-style: italic; text-transform: uppercase; line-height: 1.15;
      background: linear-gradient(to right, #c7d2fe, #fff, #67e8f9);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      filter: drop-shadow(0 0 12px rgba(129,140,248,0.6));
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
        template: opts.template || 'hook_cyber_hud',
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
