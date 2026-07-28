/**
 * Deterministic template + JSON → HTML (no LLM freestyle).
 * Hook/subtitle remain Remotion.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const TEMPLATES = path.join(ROOT, 'templates');

export function listTemplates() {
  if (!fs.existsSync(TEMPLATES)) return [];
  return fs.readdirSync(TEMPLATES).filter((n) =>
    fs.existsSync(path.join(TEMPLATES, n, 'index.html'))
  );
}

export function assembleHtml({
  template = 'lower_third_v1',
  baseSrc = '',
  events = [],
  duration = 0,
} = {}) {
  const tplPath = path.join(TEMPLATES, template, 'index.html');
  if (!fs.existsSync(tplPath)) {
    throw new Error(`Unknown template: ${template}`);
  }
  let html = fs.readFileSync(tplPath, 'utf8');
  const safeEvents = (Array.isArray(events) ? events : []).map((e) => ({
    label: String(e.label || e.word || e.name || '').slice(0, 80),
    sub: String(e.sub || e.query_en || e.query_id || '').slice(0, 120),
    start: Number(e.start ?? e.t0 ?? 0) || 0,
    end: Number(e.end ?? e.t1 ?? ((Number(e.start) || 0) + 2.4)) || 2.4,
    thumb: e.thumb || e.image_url || e.image || '',
  }));
  const eventsJson = JSON.stringify(safeEvents).replace(/</g, '\\u003c');
  html = html
    .replaceAll('{{BASE_SRC}}', String(baseSrc).replace(/"/g, '&quot;'))
    .replaceAll('{{EVENTS_JSON}}', eventsJson)
    .replaceAll('{{DURATION}}', String(Number(duration) || 0));
  return html;
}

export function writeComposition(outDir, opts) {
  fs.mkdirSync(outDir, { recursive: true });
  const html = assembleHtml(opts);
  const indexPath = path.join(outDir, 'index.html');
  fs.writeFileSync(indexPath, html, 'utf8');
  fs.writeFileSync(
    path.join(outDir, 'meta.json'),
    JSON.stringify({ template: opts.template || 'lower_third_v1', ...opts, events: opts.events || [] }, null, 2)
  );
  return indexPath;
}
