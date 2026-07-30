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
    quality: "Style template fixed",
    note: "Render lebih cepat. Style terbatas template siap-pakai (bukan freestyle editor). Cocok bulk.",
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

/** Catalog mirrors hyperframes-renderer/templates/* (id = folder name). */
export const HF_HOOK_STYLES: HfStylePreset[] = [
  {
    id: "hook_banner_v1",
    name: "Banner Slam",
    kind: "hook",
    mood: "Bold",
    accent: "#F97316",
    desc: "Full-width top banner · punch in 0.3s",
    preview: "HOOK TEXT",
  },
  {
    id: "hook_neon_v1",
    name: "Neon Glass",
    kind: "hook",
    mood: "Neon",
    accent: "#22D3EE",
    desc: "Glass card + cyan glow · center",
    preview: "WATCH THIS",
  },
  {
    id: "hook_tape_v1",
    name: "Breaking Tape",
    kind: "hook",
    mood: "News",
    accent: "#FACC15",
    desc: "Yellow tape bar · urgency",
    preview: "BREAKING",
  },
  {
    id: "hook_lower_v1",
    name: "On-Air Lower",
    kind: "hook",
    mood: "Podcast",
    accent: "#34D399",
    desc: "Lower-third badge · broadcast",
    preview: "ON AIR",
  },
];

export const HF_SUBTITLE_STYLES: HfStylePreset[] = [
  {
    id: "sub_caption_v1",
    name: "Caption Pop",
    kind: "subtitle",
    mood: "TikTok",
    accent: "#F8FAFC",
    desc: "Center word-pop · bold white",
    preview: "word by word",
  },
  {
    id: "sub_neon_v1",
    name: "Neon Karaoke",
    kind: "subtitle",
    mood: "Neon",
    accent: "#A78BFA",
    desc: "Active word glow · karaoke",
    preview: "active · rest",
  },
  {
    id: "sub_box_v1",
    name: "Box Strip",
    kind: "subtitle",
    mood: "Clean",
    accent: "#38BDF8",
    desc: "Bottom box · dual line",
    preview: "clean strip",
  },
  {
    id: "sub_minimal_v1",
    name: "Minimal",
    kind: "subtitle",
    mood: "Doc",
    accent: "#E2E8F0",
    desc: "Thin caption · documentary",
    preview: "minimal",
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
