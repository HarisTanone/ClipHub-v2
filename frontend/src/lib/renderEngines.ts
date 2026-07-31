/** Dual render engines for hook + subtitle.
 * Remotion = full custom style (slower, premium).
 * HyperFrames = fixed templates (faster, limited look).
 */

export type RenderEngine = "remotion" | "hyperframes";

export const ENGINE_NOTES = {
  remotion: {
    label: "Remotion",
    badge: "Premium",
    speed: "Lebih lama",
    quality: "Hasil bagus · custom penuh",
    note: "Render lebih lama, tapi style bebas (font, animasi, glow, preset editor). Preview ≡ final bake.",
  },
  hyperframes: {
    label: "HyperFrames",
    badge: "Fast",
    speed: "Lebih cepat",
    quality: "Style HF-native fixed",
    note: "Render cepat. Visual HyperFrames khusus, berbeda dari preset Remotion, siap untuk bulk.",
  },
} as const;

export type HfStyleKind = "hook" | "subtitle" | "polish";

export interface HfStylePreset {
  id: string;
  name: string;
  kind: HfStyleKind;
  mood: string;
  accent: string;
  desc: string;
  preview: string;
}

/** Catalog mirrors hyperframes-renderer's fixed TPL registry. */
export const HF_HOOK_STYLES: HfStylePreset[] = [
  {
    id: "hook_chromatic_gate_v2",
    name: "Chromatic Gate",
    kind: "hook",
    mood: "Y2K",
    accent: "#FF2E88",
    desc: "Magenta/cyan gate · split RGB entrance",
    preview: "NO WAY BACK",
  },
  {
    id: "hook_orbit_stamp_v2",
    name: "Orbit Stamp",
    kind: "hook",
    mood: "Orbital",
    accent: "#8B5CF6",
    desc: "Circular stamp · orbiting proof marks",
    preview: "THE REAL STORY",
  },
  {
    id: "hook_pixel_ticker_v2",
    name: "Pixel Ticker",
    kind: "hook",
    mood: "Arcade",
    accent: "#F7FF58",
    desc: "Pixel counter · hard-edged ticker strip",
    preview: "LEVEL UP",
  },
  {
    id: "hook_blueprint_v2",
    name: "Blueprint Reveal",
    kind: "hook",
    mood: "Technical",
    accent: "#52C7FF",
    desc: "Blueprint grid · measured frame reveal",
    preview: "HOW IT WORKS",
  },
];

export const HF_SUBTITLE_STYLES: HfStylePreset[] = [
  {
    id: "sub_speech_capsule_v2",
    name: "Speech Capsule",
    kind: "subtitle",
    mood: "Dialogue",
    accent: "#FFFFFF",
    desc: "White speech capsule · black editorial type",
    preview: "langsung paham",
  },
  {
    id: "sub_signal_rail_v2",
    name: "Signal Rail",
    kind: "subtitle",
    mood: "Signal",
    accent: "#B7FF00",
    desc: "Lime timeline rail · caption locked above",
    preview: "sinyalnya masuk",
  },
  {
    id: "sub_vertical_caption_v2",
    name: "Vertical Caption",
    kind: "subtitle",
    mood: "Sidecar",
    accent: "#00D9FF",
    desc: "Side-mounted caption · vertical index rail",
    preview: "beda arah",
  },
  {
    id: "sub_notch_transcript_v2",
    name: "Notch Transcript",
    kind: "subtitle",
    mood: "Device",
    accent: "#FFB000",
    desc: "Black device notch · amber transcript cursor",
    preview: "rekaman aktif",
  },
];

export const HF_POLISH_STYLES: HfStylePreset[] = [
  {
    id: "lower_third_v1",
    name: "AI Lower Third",
    kind: "polish",
    mood: "Info",
    accent: "#22D3EE",
    desc: "Entity cards dari AI visual · post-bake",
    preview: "AI · label",
  },
  {
    id: "lower_third",
    name: "Lower Third Classic",
    kind: "polish",
    mood: "Info",
    accent: "#A78BFA",
    desc: "Legacy lower-third polish",
    preview: "classic",
  },
];

export function defaultHfHookId(): string {
  return HF_HOOK_STYLES[0].id;
}

export function defaultHfSubtitleId(): string {
  return HF_SUBTITLE_STYLES[0].id;
}

export function resolveEngine(raw: unknown): RenderEngine {
  return raw === "hyperframes" ? "hyperframes" : "remotion";
}
