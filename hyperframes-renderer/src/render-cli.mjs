#!/usr/bin/env node
import path from 'node:path';
import os from 'node:os';
import { writeComposition } from './assemble.mjs';

const args = process.argv.slice(2);
function get(flag, def = '') {
  const i = args.indexOf(flag);
  return i >= 0 ? args[i + 1] : def;
}

const template = get('--template', 'lower_third_v1');
const out = get('--out', path.join(os.tmpdir(), 'hf-out.mp4'));
const base = get('--base', '');
const label = get('--label', 'Sample Entity');
const work = path.join(os.tmpdir(), `hf-cli-${Date.now()}`);

const index = writeComposition(work, {
  template,
  baseSrc: base,
  duration: 5,
  events: [{ label, sub: 'autocliper polish', start: 0.5, end: 3.5 }],
});
console.log(JSON.stringify({ composition: index, out, template, work }, null, 2));
