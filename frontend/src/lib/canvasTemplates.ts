/** Canvas background templates for 16:9 / 1:1 — mirrors backend canvas_templates. */

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
  aspectRatio: string;
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

const L16: CanvasLayout = {
  videoX: 0.08,
  videoY: 0.1,
  videoW: 0.84,
  videoH: 0.8,
  borderRadius: 18,
  shadow: "0 18px 60px rgba(0,0,0,0.55)",
};
const L11: CanvasLayout = {
  videoX: 0.1,
  videoY: 0.12,
  videoW: 0.8,
  videoH: 0.76,
  borderRadius: 22,
  shadow: "0 16px 48px rgba(0,0,0,0.5)",
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
        { offset: 0.45, color: "#0d0e10" },
        { offset: 1, color: "#050505" },
      ],
      angle: 160,
      vignette: 0.55,
    },
    [
      { type: "soft-glow", x: 0.5, y: 0.15, r: 0.35, color: "rgba(255,255,255,0.04)" },
      { type: "bar", x: 0.08, y: 0.92, w: 0.18, h: 0.006, color: "rgba(255,255,255,0.12)" },
    ],
    { videoX: 0.1, videoY: 0.12, videoW: 0.8, videoH: 0.76, borderRadius: 14 },
    { videoX: 0.12, videoY: 0.14, videoW: 0.76, videoH: 0.72, borderRadius: 16 },
  ),
  tpl(
    "modern-gradient",
    "Modern Gradient",
    "Modern",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#0b1220" },
        { offset: 0.5, color: "#12182b" },
        { offset: 1, color: "#1a0f2e" },
      ],
      angle: 135,
      vignette: 0.4,
    },
    [
      { type: "blob", x: 0.12, y: 0.18, r: 0.22, color: "rgba(99,102,241,0.18)" },
      { type: "blob", x: 0.88, y: 0.82, r: 0.28, color: "rgba(168,85,247,0.14)" },
      { type: "line", x1: 0.05, y1: 0.88, x2: 0.28, y2: 0.88, color: "rgba(129,140,248,0.45)", w: 2 },
    ],
    { videoX: 0.07, videoY: 0.09, videoW: 0.86, videoH: 0.82, borderRadius: 20 },
  ),
  tpl(
    "podcast-studio",
    "Podcast Studio",
    "Podcast",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#1c1410" },
        { offset: 0.55, color: "#120e0c" },
        { offset: 1, color: "#080706" },
      ],
      angle: 180,
      vignette: 0.5,
    },
    [
      { type: "soft-glow", x: 0.5, y: 0.35, r: 0.45, color: "rgba(251,146,60,0.08)" },
      { type: "ring", x: 0.5, y: 0.5, r: 0.42, color: "rgba(255,255,255,0.04)", stroke: 1 },
      { type: "bar", x: 0.42, y: 0.08, w: 0.16, h: 0.01, color: "rgba(251,146,60,0.55)" },
    ],
    { videoX: 0.14, videoY: 0.1, videoW: 0.72, videoH: 0.78, borderRadius: 12 },
    { videoX: 0.14, videoY: 0.12, videoW: 0.72, videoH: 0.7, borderRadius: 14 },
  ),
  tpl(
    "minimal-premium",
    "Minimal Premium",
    "Minimal",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#141414" },
        { offset: 1, color: "#0a0a0a" },
      ],
      angle: 180,
      vignette: 0.25,
    },
    [{ type: "frame", inset: 0.035, color: "rgba(255,255,255,0.08)", stroke: 1 }],
    { videoX: 0.06, videoY: 0.08, videoW: 0.88, videoH: 0.84, borderRadius: 8 },
    { videoX: 0.08, videoY: 0.08, videoW: 0.84, videoH: 0.84, borderRadius: 10 },
  ),
  tpl(
    "neon-glow",
    "Neon",
    "Creative",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#050510" },
        { offset: 0.5, color: "#0a0a1a" },
        { offset: 1, color: "#0d0518" },
      ],
      angle: 200,
      vignette: 0.45,
    },
    [
      { type: "blob", x: 0.15, y: 0.2, r: 0.2, color: "rgba(34,211,238,0.15)" },
      { type: "blob", x: 0.85, y: 0.75, r: 0.25, color: "rgba(236,72,153,0.12)" },
      { type: "line", x1: 0.72, y1: 0.1, x2: 0.92, y2: 0.1, color: "rgba(34,211,238,0.6)", w: 2 },
      { type: "line", x1: 0.08, y1: 0.9, x2: 0.28, y2: 0.9, color: "rgba(236,72,153,0.55)", w: 2 },
    ],
    { videoX: 0.09, videoY: 0.11, videoW: 0.82, videoH: 0.78, borderRadius: 16 },
  ),
  tpl(
    "gradient-depth",
    "Gradient Depth",
    "Modern",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#0f172a" },
        { offset: 0.4, color: "#1e1b4b" },
        { offset: 0.75, color: "#312e81" },
        { offset: 1, color: "#0f172a" },
      ],
      angle: 145,
      vignette: 0.5,
    },
    [
      { type: "soft-glow", x: 0.3, y: 0.25, r: 0.4, color: "rgba(99,102,241,0.12)" },
      { type: "soft-glow", x: 0.75, y: 0.7, r: 0.35, color: "rgba(14,165,233,0.1)" },
    ],
  ),
  tpl(
    "studio-soft",
    "Studio Soft",
    "Studio",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#1f1f23" },
        { offset: 0.5, color: "#16161a" },
        { offset: 1, color: "#0c0c0e" },
      ],
      angle: 170,
      vignette: 0.35,
    },
    [
      { type: "soft-glow", x: 0.5, y: 0.0, r: 0.55, color: "rgba(255,255,255,0.05)" },
      { type: "bar", x: 0.78, y: 0.9, w: 0.14, h: 0.005, color: "rgba(255,255,255,0.15)" },
    ],
    { videoX: 0.08, videoY: 0.1, videoW: 0.84, videoH: 0.8, borderRadius: 24 },
    { videoX: 0.1, videoY: 0.1, videoW: 0.8, videoH: 0.8, borderRadius: 28 },
  ),
  tpl(
    "creative-depth",
    "Creative",
    "Creative",
    {
      type: "gradient",
      stops: [
        { offset: 0, color: "#111827" },
        { offset: 0.55, color: "#1f2937" },
        { offset: 1, color: "#0b1020" },
      ],
      angle: 120,
      vignette: 0.4,
    },
    [
      { type: "blob", x: 0.9, y: 0.12, r: 0.18, color: "rgba(52,211,153,0.12)" },
      { type: "blob", x: 0.08, y: 0.85, r: 0.2, color: "rgba(59,130,246,0.12)" },
      { type: "frame", inset: 0.025, color: "rgba(255,255,255,0.06)", stroke: 1 },
    ],
    { videoX: 0.11, videoY: 0.12, videoW: 0.78, videoH: 0.76, borderRadius: 18 },
  ),
];

export const ASPECT_RESOLUTION: Record<string, [number, number]> = {
  "9:16": [1080, 1920],
  "16:9": [1920, 1080],
  "1:1": [1080, 1080],
};

export function getTemplate(id: string | null | undefined): CanvasTemplate | undefined {
  if (!id) return undefined;
  return CANVAS_TEMPLATES.find((t) => t.id === id);
}

export function buildCanvasConfig(
  aspectRatio: string,
  opts: {
    backgroundMode?: "template" | "upload" | null;
    templateId?: string | null;
    backgroundImageUrl?: string | null;
  } = {},
): CanvasConfig | null {
  if (aspectRatio === "9:16") return null;
  const mode = opts.backgroundMode === "upload" ? "upload" : "template";
  const [width, height] = ASPECT_RESOLUTION[aspectRatio] || ASPECT_RESOLUTION["16:9"];
  if (mode === "upload") {
    const layout = aspectRatio === "1:1" ? L11 : L16;
    return {
      aspectRatio,
      width,
      height,
      mode,
      templateId: null,
      background: {
        type: opts.backgroundImageUrl ? "image" : "solid",
        color: "#0a0a0a",
        imageUrl: opts.backgroundImageUrl || null,
        vignette: 0.3,
      },
      accents: [],
      layout,
      backgroundImageUrl: opts.backgroundImageUrl || null,
    };
  }
  const tplItem = getTemplate(opts.templateId) || CANVAS_TEMPLATES[0];
  const layout = tplItem.layout[aspectRatio] || tplItem.layout["16:9"];
  return {
    aspectRatio,
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
