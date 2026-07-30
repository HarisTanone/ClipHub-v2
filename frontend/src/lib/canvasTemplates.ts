/** Canvas templates: content 16:9/1:1 on final TikTok 9:16 canvas.
 * Mirrors backend canvas_templates.py — keep in sync.
 */

export type AspectRatio = "9:16" | "16:9" | "1:1";

export interface CanvasLayout {
  videoX: number;
  videoY: number;
  videoW: number;
  videoH: number;
  borderRadius?: number;
  shadow?: string;
}

export interface CanvasAccent {
  type: "soft-glow" | "blob" | "bar" | "line" | "ring" | "frame";
  x?: number;
  y?: number;
  r?: number;
  w?: number;
  h?: number;
  x1?: number;
  y1?: number;
  x2?: number;
  y2?: number;
  inset?: number;
  color: string;
  stroke?: number;
}

export interface CanvasTemplate {
  id: string;
  name: string;
  category: string;
  supportedAspectRatios: AspectRatio[];
  background: {
    type: string;
    stops?: Array<{ offset: number; color: string }>;
    angle?: number;
    vignette?: number;
    color?: string;
    imageUrl?: string | null;
  };
  accents: CanvasAccent[];
  layout: Record<string, CanvasLayout>;
}

export interface CanvasConfig {
  aspectRatio: string; // final canvas always 9:16
  contentAspect?: string; // main video framing
  width: number;
  height: number;
  mode: "template" | "upload";
  templateId?: string | null;
  templateName?: string;
  background: CanvasTemplate["background"] & { imageUrl?: string | null };
  accents: CanvasAccent[];
  layout: CanvasLayout;
  backgroundImageUrl?: string | null;
}

/** Final TikTok canvas */
export const OUTPUT_RESOLUTION: [number, number] = [1080, 1920];

/** Intermediate content dims (pre-Remotion) */
export const CONTENT_RESOLUTION: Record<string, [number, number]> = {
  "9:16": [1080, 1920],
  "16:9": [1920, 1080],
  "1:1": [1080, 1080],
};

/** @deprecated use CONTENT_RESOLUTION — kept for callers */
export const ASPECT_RESOLUTION = CONTENT_RESOLUTION;

// 16:9 band on 9:16: full width, height ratio 9/16 of width → 0.3164 of canvas H
const L16: CanvasLayout = {
  videoX: 0.0,
  videoY: 0.3418,
  videoW: 1.0,
  videoH: 0.3164,
  borderRadius: 0,
  shadow: "0 12px 40px rgba(0,0,0,0.45)",
};
// 1:1 band on 9:16
const L11: CanvasLayout = {
  videoX: 0.0,
  videoY: 0.21875,
  videoW: 1.0,
  videoH: 0.5625,
  borderRadius: 0,
  shadow: "0 12px 40px rgba(0,0,0,0.4)",
};

function tpl(
  id: string,
  name: string,
  category: string,
  background: CanvasTemplate["background"],
  accents: CanvasAccent[] = [],
  layout16?: Partial<CanvasLayout>,
  layout11?: Partial<CanvasLayout>,
): CanvasTemplate {
  return {
    id,
    name,
    category,
    supportedAspectRatios: ["16:9", "1:1"],
    background,
    accents,
    layout: {
      "16:9": { ...L16, ...layout16 },
      "1:1": { ...L11, ...layout11 },
    },
  };
}

export const CANVAS_TEMPLATES: CanvasTemplate[] = [
  tpl(
    "dark-studio",
    "Dark Studio",
    "Studio",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#1a1b1e" },
        { offset: 0.35, color: "#0d0e10" },
        { offset: 0.65, color: "#0d0e10" },
        { offset: 1, color: "#050505" },
      ],
      angle: 180,
      vignette: 0.45,
    },
    [
      { type: "soft-glow", x: 0.5, y: 0.12, r: 0.4, color: "rgba(255,255,255,0.06)" },
      { type: "soft-glow", x: 0.5, y: 0.88, r: 0.35, color: "rgba(255,255,255,0.04)" },
      { type: "bar", x: 0.3, y: 0.06, w: 0.4, h: 0.004, color: "rgba(255,255,255,0.2)" },
      { type: "bar", x: 0.35, y: 0.94, w: 0.3, h: 0.004, color: "rgba(255,255,255,0.15)" },
      { type: "frame", inset: 0.02, color: "rgba(255,255,255,0.08)", stroke: 1 },
    ],
    { videoX: 0.0, videoY: 0.3418, videoW: 1.0, videoH: 0.3164, borderRadius: 0 },
    { videoX: 0.04, videoY: 0.24, videoW: 0.92, videoH: 0.52, borderRadius: 12 },
  ),
  tpl(
    "modern-gradient",
    "Modern Gradient",
    "Modern",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#0b1220" },
        { offset: 0.4, color: "#12182b" },
        { offset: 0.6, color: "#1a0f2e" },
        { offset: 1, color: "#0a0614" },
      ],
      angle: 180,
      vignette: 0.35,
    },
    [
      { type: "blob", x: 0.15, y: 0.1, r: 0.28, color: "rgba(99,102,241,0.22)" },
      { type: "blob", x: 0.85, y: 0.9, r: 0.3, color: "rgba(168,85,247,0.18)" },
      { type: "line", x1: 0.08, y1: 0.18, x2: 0.35, y2: 0.18, color: "rgba(129,140,248,0.55)", w: 2 },
      { type: "line", x1: 0.65, y1: 0.82, x2: 0.92, y2: 0.82, color: "rgba(168,85,247,0.5)", w: 2 },
      { type: "ring", x: 0.5, y: 0.12, r: 0.08, color: "rgba(99,102,241,0.25)", stroke: 1 },
    ],
    { borderRadius: 0 },
    { videoX: 0.05, videoY: 0.2469, videoW: 0.9, videoH: 0.5062, borderRadius: 16 },
  ),
  tpl(
    "podcast-studio",
    "Podcast Studio",
    "Podcast",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#2a1a10" },
        { offset: 0.35, color: "#120e0c" },
        { offset: 0.65, color: "#120e0c" },
        { offset: 1, color: "#1a1008" },
      ],
      angle: 180,
      vignette: 0.5,
    },
    [
      { type: "soft-glow", x: 0.5, y: 0.15, r: 0.45, color: "rgba(251,146,60,0.12)" },
      { type: "soft-glow", x: 0.5, y: 0.85, r: 0.4, color: "rgba(251,146,60,0.08)" },
      { type: "bar", x: 0.38, y: 0.08, w: 0.24, h: 0.008, color: "rgba(251,146,60,0.7)" },
      { type: "bar", x: 0.4, y: 0.92, w: 0.2, h: 0.006, color: "rgba(251,146,60,0.45)" },
      { type: "ring", x: 0.5, y: 0.5, r: 0.48, color: "rgba(255,255,255,0.03)", stroke: 1 },
    ],
    { videoX: 0.03, videoY: 0.35, videoW: 0.94, videoH: 0.3, borderRadius: 8 },
    { videoX: 0.06, videoY: 0.24, videoW: 0.88, videoH: 0.52, borderRadius: 10 },
  ),
  tpl(
    "minimal-premium",
    "Minimal Premium",
    "Minimal",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#181818" },
        { offset: 0.5, color: "#0c0c0c" },
        { offset: 1, color: "#181818" },
      ],
      angle: 180,
      vignette: 0.2,
    },
    [
      { type: "frame", inset: 0.025, color: "rgba(255,255,255,0.12)", stroke: 1 },
      { type: "bar", x: 0.42, y: 0.12, w: 0.16, h: 0.003, color: "rgba(255,255,255,0.25)" },
      { type: "bar", x: 0.42, y: 0.88, w: 0.16, h: 0.003, color: "rgba(255,255,255,0.2)" },
    ],
    { videoX: 0.0, videoY: 0.3418, videoW: 1.0, videoH: 0.3164, borderRadius: 0 },
    { videoX: 0.04, videoY: 0.23, videoW: 0.92, videoH: 0.54, borderRadius: 4 },
  ),
  tpl(
    "neon-glow",
    "Neon",
    "Creative",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#050510" },
        { offset: 0.4, color: "#0a0a1a" },
        { offset: 0.6, color: "#0a0a1a" },
        { offset: 1, color: "#0d0518" },
      ],
      angle: 180,
      vignette: 0.4,
    },
    [
      { type: "blob", x: 0.2, y: 0.1, r: 0.25, color: "rgba(34,211,238,0.2)" },
      { type: "blob", x: 0.8, y: 0.9, r: 0.28, color: "rgba(236,72,153,0.18)" },
      { type: "line", x1: 0.1, y1: 0.2, x2: 0.4, y2: 0.2, color: "rgba(34,211,238,0.7)", w: 2 },
      { type: "line", x1: 0.6, y1: 0.8, x2: 0.9, y2: 0.8, color: "rgba(236,72,153,0.65)", w: 2 },
      { type: "bar", x: 0.0, y: 0.0, w: 1.0, h: 0.006, color: "rgba(34,211,238,0.5)" },
      { type: "bar", x: 0.0, y: 0.994, w: 1.0, h: 0.006, color: "rgba(236,72,153,0.5)" },
    ],
    { videoX: 0.02, videoY: 0.35, videoW: 0.96, videoH: 0.3, borderRadius: 4 },
    { videoX: 0.05, videoY: 0.24, videoW: 0.9, videoH: 0.52, borderRadius: 12 },
  ),
  tpl(
    "gradient-depth",
    "Gradient Depth",
    "Modern",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#0f172a" },
        { offset: 0.3, color: "#1e1b4b" },
        { offset: 0.7, color: "#312e81" },
        { offset: 1, color: "#0f172a" },
      ],
      angle: 180,
      vignette: 0.45,
    },
    [
      { type: "soft-glow", x: 0.3, y: 0.12, r: 0.4, color: "rgba(99,102,241,0.18)" },
      { type: "soft-glow", x: 0.7, y: 0.88, r: 0.38, color: "rgba(14,165,233,0.14)" },
      { type: "frame", inset: 0.03, color: "rgba(129,140,248,0.15)", stroke: 1 },
    ],
  ),
  tpl(
    "studio-soft",
    "Studio Soft",
    "Studio",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#2a2a30" },
        { offset: 0.4, color: "#16161a" },
        { offset: 0.6, color: "#16161a" },
        { offset: 1, color: "#1f1f23" },
      ],
      angle: 180,
      vignette: 0.3,
    },
    [
      { type: "soft-glow", x: 0.5, y: 0.08, r: 0.5, color: "rgba(255,255,255,0.07)" },
      { type: "soft-glow", x: 0.5, y: 0.92, r: 0.4, color: "rgba(255,255,255,0.05)" },
      { type: "bar", x: 0.7, y: 0.14, w: 0.2, h: 0.005, color: "rgba(255,255,255,0.18)" },
      { type: "bar", x: 0.1, y: 0.86, w: 0.18, h: 0.005, color: "rgba(255,255,255,0.12)" },
    ],
    { videoX: 0.02, videoY: 0.348, videoW: 0.96, videoH: 0.304, borderRadius: 10 },
    { videoX: 0.05, videoY: 0.2469, videoW: 0.9, videoH: 0.5062, borderRadius: 18 },
  ),
  tpl(
    "creative-depth",
    "Creative",
    "Creative",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#0b1020" },
        { offset: 0.35, color: "#1f2937" },
        { offset: 0.65, color: "#111827" },
        { offset: 1, color: "#0b1020" },
      ],
      angle: 180,
      vignette: 0.35,
    },
    [
      { type: "blob", x: 0.88, y: 0.1, r: 0.22, color: "rgba(52,211,153,0.16)" },
      { type: "blob", x: 0.12, y: 0.9, r: 0.24, color: "rgba(59,130,246,0.16)" },
      { type: "frame", inset: 0.02, color: "rgba(255,255,255,0.07)", stroke: 1 },
      { type: "line", x1: 0.15, y1: 0.16, x2: 0.4, y2: 0.16, color: "rgba(52,211,153,0.5)", w: 2 },
      { type: "line", x1: 0.6, y1: 0.84, x2: 0.85, y2: 0.84, color: "rgba(59,130,246,0.5)", w: 2 },
    ],
    { videoX: 0.0, videoY: 0.3418, videoW: 1.0, videoH: 0.3164, borderRadius: 0 },
    { videoX: 0.06, videoY: 0.24, videoW: 0.88, videoH: 0.52, borderRadius: 14 },
  ),
  tpl(
    "cinematic-film",
    "Cinematic Film",
    "Film",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#1a1008" },
        { offset: 0.4, color: "#0a0806" },
        { offset: 0.6, color: "#0a0806" },
        { offset: 1, color: "#1a1008" },
      ],
      angle: 180,
      vignette: 0.55,
    },
    [
      { type: "bar", x: 0.0, y: 0.0, w: 1.0, h: 0.3418, color: "rgba(12,8,4,0.92)" },
      { type: "bar", x: 0.0, y: 0.6582, w: 1.0, h: 0.3418, color: "rgba(12,8,4,0.92)" },
      { type: "line", x1: 0.0, y1: 0.3418, x2: 1.0, y2: 0.3418, color: "rgba(212,175,55,0.35)", w: 1 },
      { type: "line", x1: 0.0, y1: 0.6582, x2: 1.0, y2: 0.6582, color: "rgba(212,175,55,0.35)", w: 1 },
      { type: "bar", x: 0.35, y: 0.12, w: 0.3, h: 0.004, color: "rgba(212,175,55,0.5)" },
      { type: "bar", x: 0.38, y: 0.88, w: 0.24, h: 0.004, color: "rgba(212,175,55,0.4)" },
    ],
    { videoX: 0.0, videoY: 0.3418, videoW: 1.0, videoH: 0.3164, borderRadius: 0 },
    { videoX: 0.08, videoY: 0.2638, videoW: 0.84, videoH: 0.4725, borderRadius: 4 },
  ),
  tpl(
    "brand-border",
    "Brand Border",
    "Brand",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#0f172a" },
        { offset: 0.5, color: "#020617" },
        { offset: 1, color: "#0f172a" },
      ],
      angle: 180,
      vignette: 0.3,
    },
    [
      { type: "frame", inset: 0.018, color: "rgba(56,189,248,0.45)", stroke: 3 },
      { type: "frame", inset: 0.035, color: "rgba(255,255,255,0.08)", stroke: 1 },
      { type: "bar", x: 0.25, y: 0.1, w: 0.5, h: 0.01, color: "rgba(56,189,248,0.6)" },
      { type: "bar", x: 0.3, y: 0.89, w: 0.4, h: 0.008, color: "rgba(56,189,248,0.4)" },
      { type: "soft-glow", x: 0.5, y: 0.1, r: 0.3, color: "rgba(56,189,248,0.1)" },
      { type: "soft-glow", x: 0.5, y: 0.9, r: 0.28, color: "rgba(56,189,248,0.08)" },
    ],
    { videoX: 0.04, videoY: 0.36, videoW: 0.92, videoH: 0.28, borderRadius: 6 },
    { videoX: 0.08, videoY: 0.26, videoW: 0.84, videoH: 0.48, borderRadius: 10 },
  ),
];

export function getTemplate(id: string | null | undefined): CanvasTemplate | undefined {
  if (!id) return undefined;
  return CANVAS_TEMPLATES.find((t) => t.id === id);
}

/**
 * Build canvas config for preview + bake.
 * contentAspect = main video framing (16:9 / 1:1).
 * Final canvas always 9:16 TikTok. null for full-bleed 9:16 content.
 */
export function buildCanvasConfig(
  contentAspect: string,
  opts: {
    backgroundMode?: "template" | "upload" | null;
    templateId?: string | null;
    backgroundImageUrl?: string | null;
  } = {},
): CanvasConfig | null {
  if (contentAspect === "9:16") return null;
  const mode = opts.backgroundMode === "upload" ? "upload" : "template";
  const [width, height] = OUTPUT_RESOLUTION;
  if (mode === "upload") {
    const layout =
      contentAspect === "1:1"
        ? { ...L11, videoX: 0.04, videoY: 0.24, videoW: 0.92, videoH: 0.52, borderRadius: 12 }
        : { ...L16 };
    return {
      aspectRatio: "9:16",
      contentAspect,
      width,
      height,
      mode,
      templateId: null,
      background: {
        type: opts.backgroundImageUrl ? "image" : "gradient",
        color: "#0a0a0a",
        imageUrl: opts.backgroundImageUrl || null,
        stops: [
          { offset: 0, color: "#1a1a1a" },
          { offset: 0.5, color: "#0a0a0a" },
          { offset: 1, color: "#1a1a1a" },
        ],
        angle: 180,
        vignette: 0.35,
      },
      accents: [{ type: "frame", inset: 0.02, color: "rgba(255,255,255,0.08)", stroke: 1 }],
      layout,
      backgroundImageUrl: opts.backgroundImageUrl || null,
    };
  }
  const tplItem = getTemplate(opts.templateId) || CANVAS_TEMPLATES[0];
  const layout = tplItem.layout[contentAspect] || tplItem.layout["16:9"];
  return {
    aspectRatio: "9:16",
    contentAspect,
    width,
    height,
    mode: "template",
    templateId: tplItem.id,
    templateName: tplItem.name,
    background: tplItem.background,
    accents: tplItem.accents,
    layout,
  };
}

export function gradientCss(bg: CanvasTemplate["background"] | undefined): string {
  if (!bg) return "#0a0a0a";
  if (bg.type === "solid" || (!bg.stops && bg.color)) return bg.color || "#0a0a0a";
  if (bg.type === "image") return "transparent";
  const stops = bg.stops || [
    { offset: 0, color: "#111" },
    { offset: 1, color: "#000" },
  ];
  const angle = bg.angle ?? 180;
  return `linear-gradient(${angle}deg, ${stops.map((s) => `${s.color} ${Math.round(s.offset * 100)}%`).join(", ")})`;
}
