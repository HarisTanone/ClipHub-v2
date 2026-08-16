import assert from 'node:assert/strict';
import { assembleHtml } from './assemble.mjs';

const expectedDesign = {
  hook_chromatic_gate_v2: 'chromatic-gate',
  hook_orbit_stamp_v2: 'orbit-stamp',
  hook_pixel_ticker_v2: 'pixel-ticker',
  hook_blueprint_v2: 'blueprint-reveal',
  hook_neon_matrix: 'neon-matrix',
  hook_warning_hazard: 'warning-hazard',
  hook_sticker_scrapbook: 'sticker-scrapbook',
  hook_cinematic_minimal: 'cinematic-minimal',
  hook_electric_surge: 'electric-surge',
  sub_speech_capsule_v2: 'speech-capsule',
  sub_signal_rail_v2: 'signal-rail',
  sub_vertical_caption_v2: 'vertical-caption',
  sub_notch_transcript_v2: 'notch-transcript',
};

const outputs = Object.entries(expectedDesign).map(([template, design]) => {
  const html = assembleHtml({
    template,
    baseSrc: 'base.mp4',
    duration: 6,
    events: [{ label: 'Distinct HyperFrames style', start: 0.5, end: 3 }],
  });
  assert.match(html, new RegExp(`data-design="${design}"`), template);
  assert.match(html, new RegExp(`hf-${template}`), template);
  return html;
});

assert.equal(new Set(Object.values(expectedDesign)).size, outputs.length);
console.log(`assemble styles: ${outputs.length} distinct templates`);
