/** Triple render engines for hook + subtitle.
 * Remotion = full custom style (slower, premium).
 * HyperFrames = fixed templates (faster, limited look).
 * FFmpeg = server-side drawtext (fastest, no browser needed).
 * Skia = GPU-accelerated canvas (rich gradients, glassmorphism, glow, badges).
 */

export type RenderEngine = "remotion" | "hyperframes" | "ffmpeg" | "skia";

export const ENGINE_NOTES = {
  remotion: {
    label: "Remotion",
    badge: "Premium",
    speed: "Lebih lama",
    quality: "Hasil bagus · custom penuh",
    note: "Render lebih lama, tapi style bebas (font, animasi, glow, preset editor). Preview ≡ final bake.",
    superuserOnly: true,
  },
  hyperframes: {
    label: "HyperFrames",
    badge: "Fast",
    speed: "Lebih cepat",
    quality: "Style HF-native fixed",
    note: "Render cepat. Visual HyperFrames khusus, berbeda dari preset Remotion, siap untuk bulk.",
    superuserOnly: true,
  },
  ffmpeg: {
    label: "FFmpeg",
    badge: "Fastest",
    speed: "Paling cepat",
    quality: "Drawtext server-side · full custom",
    note: "Render tercepat. Text overlay via FFmpeg drawtext. 10+ styles berbeda, full customizable.",
    superuserOnly: false,
  },
  skia: {
    label: "Skia",
    badge: "GPU",
    speed: "Cepat",
    quality: "Canvas GPU · gradient & effects",
    note: "Render GPU-accelerated via Skia/CanvasKit. Gradient, rounded bg, glow, blur. Lebih ringan dari Remotion.",
    superuserOnly: false,
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
  if (raw === "hyperframes" || raw === "hf" || raw === "hyperframe") return "hyperframes";
  if (raw === "ffmpeg" || raw === "drawtext") return "ffmpeg";
  if (raw === "skia" || raw === "canvaskit" || raw === "skia-python") return "skia";
  return "remotion";
}

// ─── FFmpeg Hook Presets ───────────────────────────────────────────────────

export interface FFmpegHookPreset {
  id: string;
  name: string;
  desc: string;
  color: string;
  fontSize: number;
  fontFamily: string;
  fontWeight: string;
  strokeEnabled: boolean;
  strokeWidth: number;
  strokeColor: string;
  bgOpacity: number;
  positionY: number;
}

export const FFMPEG_HOOK_PRESETS: FFmpegHookPreset[] = [
  { id: "zoom_punch", name: "Zoom Punch", desc: "Bold white + quick scale-in", color: "white", fontSize: 56, fontFamily: "Anton", fontWeight: "700", strokeEnabled: true, strokeWidth: 4, strokeColor: "black", bgOpacity: 0.6, positionY: 40 },
  { id: "fade_scale", name: "Fade Scale", desc: "Smooth fade + slight grow", color: "white", fontSize: 48, fontFamily: "Inter", fontWeight: "700", strokeEnabled: true, strokeWidth: 3, strokeColor: "black", bgOpacity: 0.5, positionY: 42 },
  { id: "slide_punch_framer", name: "Slide Punch", desc: "Slide from left with punch", color: "white", fontSize: 52, fontFamily: "Poppins", fontWeight: "700", strokeEnabled: true, strokeWidth: 5, strokeColor: "black", bgOpacity: 0.65, positionY: 38 },
  { id: "typewriter", name: "Typewriter", desc: "Character-by-character", color: "#00FF88", fontSize: 44, fontFamily: "Inter", fontWeight: "700", strokeEnabled: true, strokeWidth: 2, strokeColor: "black", bgOpacity: 0.7, positionY: 45 },
  { id: "glitch_rgb", name: "Glitch RGB", desc: "RGB split chromatic aberr.", color: "white", fontSize: 58, fontFamily: "Anton", fontWeight: "700", strokeEnabled: false, strokeWidth: 0, strokeColor: "black", bgOpacity: 0.7, positionY: 40 },
  { id: "shake_neon", name: "Shake Neon", desc: "Neon glow + random shake", color: "#00FFCC", fontSize: 54, fontFamily: "Bungee", fontWeight: "400", strokeEnabled: false, strokeWidth: 0, strokeColor: "black", bgOpacity: 0.65, positionY: 40 },
  { id: "cinematic_reveal", name: "Cinematic", desc: "Letterbox + elegant fade", color: "#FFD700", fontSize: 62, fontFamily: "Playfair Display", fontWeight: "700", strokeEnabled: false, strokeWidth: 0, strokeColor: "black", bgOpacity: 0.8, positionY: 42 },
  { id: "danger_bold", name: "Danger Bold", desc: "Bold red pulsing border", color: "#FF2D2D", fontSize: 70, fontFamily: "Anton", fontWeight: "700", strokeEnabled: true, strokeWidth: 6, strokeColor: "black", bgOpacity: 0.75, positionY: 38 },
  { id: "minimal_white", name: "Minimal", desc: "Clean minimal white", color: "white", fontSize: 42, fontFamily: "Inter", fontWeight: "700", strokeEnabled: true, strokeWidth: 2, strokeColor: "rgba(0,0,0,0.5)", bgOpacity: 0.3, positionY: 50 },
  { id: "bold_yellow", name: "Bold Yellow", desc: "Bold yellow heavy stroke", color: "#FFD700", fontSize: 64, fontFamily: "Anton", fontWeight: "700", strokeEnabled: true, strokeWidth: 5, strokeColor: "black", bgOpacity: 0.6, positionY: 40 },
  { id: "electric_blue", name: "Electric Blue", desc: "Bright blue neon look", color: "#00BFFF", fontSize: 54, fontFamily: "Bungee", fontWeight: "400", strokeEnabled: false, strokeWidth: 0, strokeColor: "black", bgOpacity: 0.65, positionY: 40 },
  { id: "fire_red", name: "Fire Red", desc: "Aggressive red dramatic", color: "#FF4444", fontSize: 66, fontFamily: "Anton", fontWeight: "700", strokeEnabled: true, strokeWidth: 5, strokeColor: "#220000", bgOpacity: 0.7, positionY: 38 },
];

// ─── FFmpeg Subtitle Presets (matching backend FFMPEG_STYLES) ──────────────

export interface FFmpegSubtitlePreset {
  id: string;
  name: string;
  desc: string;
  category: string;
  color: string;
  highlightColor: string;
  fontFamily: string;
  fontSize: number;
  fontWeight: string;
  lineTransition: "karaoke" | "word_pop" | "emphasis" | "line_reveal";
  strokeEnabled: boolean;
  strokeWidth: number;
  strokeColor: string;
  bgEnabled: boolean;
  bgColor: string;
  bgOpacity: number;
  bgRadius: number;
  positionY: number;
  uppercase: boolean;
  maxWordsPerLine: number;
}

export const FFMPEG_SUBTITLE_PRESETS: FFmpegSubtitlePreset[] = [
  {
    id: "classic_karaoke",
    name: "Classic Karaoke",
    desc: "Word-by-word highlight. Clean white, active word turns yellow.",
    category: "karaoke",
    color: "#FFFFFF",
    highlightColor: "#FFCC00",
    fontFamily: "Poppins",
    fontSize: 38,
    fontWeight: "700",
    lineTransition: "karaoke",
    strokeEnabled: true,
    strokeWidth: 3,
    strokeColor: "#000000",
    bgEnabled: false,
    bgColor: "#000000",
    bgOpacity: 0.0,
    bgRadius: 0,
    positionY: 82,
    uppercase: false,
    maxWordsPerLine: 3,
  },
  {
    id: "neon_glow",
    name: "Neon Glow",
    desc: "Glowing neon text on dark background with heavy stroke.",
    category: "glow",
    color: "#00FFAA",
    highlightColor: "#FF00FF",
    fontFamily: "Montserrat",
    fontSize: 42,
    fontWeight: "900",
    lineTransition: "word_pop",
    strokeEnabled: true,
    strokeWidth: 4,
    strokeColor: "#00FFAA",
    bgEnabled: true,
    bgColor: "#000000",
    bgOpacity: 0.7,
    bgRadius: 8,
    positionY: 50,
    uppercase: true,
    maxWordsPerLine: 2,
  },
  {
    id: "typewriter_mono",
    name: "Typewriter",
    desc: "Monospace retro terminal look, one word at a time in green.",
    category: "minimal",
    color: "#00FF00",
    highlightColor: "#FFFFFF",
    fontFamily: "monospace",
    fontSize: 32,
    fontWeight: "600",
    lineTransition: "word_pop",
    strokeEnabled: false,
    strokeWidth: 0,
    strokeColor: "#000000",
    bgEnabled: true,
    bgColor: "#0D0D0D",
    bgOpacity: 0.85,
    bgRadius: 6,
    positionY: 50,
    uppercase: false,
    maxWordsPerLine: 1,
  },
  {
    id: "bold_impact",
    name: "Bold Impact",
    desc: "Massive uppercase font with thick black outline.",
    category: "impact",
    color: "#FFFFFF",
    highlightColor: "#FF3333",
    fontFamily: "Anton",
    fontSize: 54,
    fontWeight: "700",
    lineTransition: "word_pop",
    strokeEnabled: true,
    strokeWidth: 5,
    strokeColor: "#000000",
    bgEnabled: false,
    bgColor: "#000000",
    bgOpacity: 0.0,
    bgRadius: 0,
    positionY: 50,
    uppercase: true,
    maxWordsPerLine: 2,
  },
  {
    id: "pastel_bubble",
    name: "Pastel Bubble",
    desc: "Rounded pill background, soft pink lifestyle aesthetic.",
    category: "aesthetic",
    color: "#2D2D2D",
    highlightColor: "#E91E63",
    fontFamily: "Nunito",
    fontSize: 30,
    fontWeight: "800",
    lineTransition: "line_reveal",
    strokeEnabled: false,
    strokeWidth: 0,
    strokeColor: "#000000",
    bgEnabled: true,
    bgColor: "#FFF0F5",
    bgOpacity: 0.92,
    bgRadius: 20,
    positionY: 82,
    uppercase: false,
    maxWordsPerLine: 4,
  },
  {
    id: "cinematic_bar",
    name: "Cinematic Bar",
    desc: "Full-width dark bar at bottom. Uppercase film subtitle style.",
    category: "cinematic",
    color: "#E0E0E0",
    highlightColor: "#FFD700",
    fontFamily: "Oswald",
    fontSize: 28,
    fontWeight: "600",
    lineTransition: "line_reveal",
    strokeEnabled: false,
    strokeWidth: 0,
    strokeColor: "#000000",
    bgEnabled: true,
    bgColor: "#1A1A1A",
    bgOpacity: 0.8,
    bgRadius: 0,
    positionY: 88,
    uppercase: true,
    maxWordsPerLine: 5,
  },
  {
    id: "fire_emphasis",
    name: "Fire Emphasis",
    desc: "Big keyword pops in orange-red, high energy hype content.",
    category: "emphasis",
    color: "#FFFFFF",
    highlightColor: "#FF4500",
    fontFamily: "Bebas Neue",
    fontSize: 36,
    fontWeight: "700",
    lineTransition: "emphasis",
    strokeEnabled: true,
    strokeWidth: 4,
    strokeColor: "#000000",
    bgEnabled: false,
    bgColor: "#000000",
    bgOpacity: 0.0,
    bgRadius: 0,
    positionY: 80,
    uppercase: true,
    maxWordsPerLine: 3,
  },
  {
    id: "glass_blur",
    name: "Glass Blur",
    desc: "Frosted translucent panel with white text & sky blue highlight.",
    category: "glass",
    color: "#FFFFFF",
    highlightColor: "#60A5FA",
    fontFamily: "Inter",
    fontSize: 30,
    fontWeight: "600",
    lineTransition: "karaoke",
    strokeEnabled: false,
    strokeWidth: 0,
    strokeColor: "#000000",
    bgEnabled: true,
    bgColor: "#FFFFFF",
    bgOpacity: 0.35,
    bgRadius: 16,
    positionY: 80,
    uppercase: false,
    maxWordsPerLine: 4,
  },
  {
    id: "street_graffiti",
    name: "Street Graffiti",
    desc: "Raw urban vibe, bright yellow text with red highlight & heavy shadow.",
    category: "urban",
    color: "#FFEB3B",
    highlightColor: "#FF1744",
    fontFamily: "Permanent Marker",
    fontSize: 40,
    fontWeight: "600",
    lineTransition: "word_pop",
    strokeEnabled: true,
    strokeWidth: 4,
    strokeColor: "#000000",
    bgEnabled: false,
    bgColor: "#000000",
    bgOpacity: 0.0,
    bgRadius: 0,
    positionY: 50,
    uppercase: true,
    maxWordsPerLine: 2,
  },
  {
    id: "minimal_lower",
    name: "Minimal Lower",
    desc: "Clean lowercase documentary style at the bottom of the screen.",
    category: "minimal",
    color: "#CCCCCC",
    highlightColor: "#FFFFFF",
    fontFamily: "Inter",
    fontSize: 24,
    fontWeight: "500",
    lineTransition: "line_reveal",
    strokeEnabled: false,
    strokeWidth: 0,
    strokeColor: "#000000",
    bgEnabled: false,
    bgColor: "#000000",
    bgOpacity: 0.0,
    bgRadius: 0,
    positionY: 90,
    uppercase: false,
    maxWordsPerLine: 5,
  },
];

// ─── Skia Hook Presets ─────────────────────────────────────────────────────

export interface SkiaHookPreset {
  id: string;
  name: string;
  desc: string;
  color: string;
  fontSize: number;
  fontFamily: string;
  fontWeight: string;
  strokeEnabled: boolean;
  strokeWidth: number;
  strokeColor: string;
  gradientEnabled?: boolean;
  gradientFrom?: string;
  gradientTo?: string;
  glowEnabled?: boolean;
  glowColor?: string;
  glowSize?: number;
  bgOpacity: number;
  positionY: number;
}

export const SKIA_HOOK_PRESETS: SkiaHookPreset[] = [
  { id: "skia_zoom_punch", name: "Zoom Punch", desc: "Bold punch with GPU canvas text stroke", color: "#FFFFFF", fontSize: 56, fontFamily: "Anton", fontWeight: "700", strokeEnabled: true, strokeWidth: 4, strokeColor: "#000000", bgOpacity: 0.6, positionY: 40 },
  { id: "skia_fade_scale", name: "Fade Scale", desc: "Smooth GPU alpha & scale blending", color: "#FFFFFF", fontSize: 48, fontFamily: "Inter", fontWeight: "700", strokeEnabled: true, strokeWidth: 3, strokeColor: "#000000", bgOpacity: 0.5, positionY: 42 },
  { id: "skia_glitch_rgb", name: "Glitch RGB", desc: "Chromatic RGB split channel rasterizer", color: "#FFFFFF", fontSize: 58, fontFamily: "Anton", fontWeight: "700", strokeEnabled: false, strokeWidth: 0, strokeColor: "#000000", bgOpacity: 0.7, positionY: 40 },
  { id: "skia_shake_neon", name: "Shake Neon", desc: "Multi-pass GPU glow shader + kinetic jitter", color: "#00FFCC", fontSize: 54, fontFamily: "Bungee", fontWeight: "400", strokeEnabled: false, strokeWidth: 0, strokeColor: "#000000", glowEnabled: true, glowColor: "#00FFCC", glowSize: 20, bgOpacity: 0.65, positionY: 40 },
  { id: "skia_cinematic", name: "Cinematic Gold", desc: "Gold gradient letterbox with soft bokeh", color: "#FFD700", fontSize: 60, fontFamily: "Playfair Display", fontWeight: "700", strokeEnabled: false, strokeWidth: 0, strokeColor: "#000000", gradientEnabled: true, gradientFrom: "#FFE066", gradientTo: "#FF9900", bgOpacity: 0.8, positionY: 42 },
  { id: "skia_danger_bold", name: "Danger Alert", desc: "Pulsing red GPU glow with heavy outline", color: "#FF2D2D", fontSize: 68, fontFamily: "Anton", fontWeight: "700", strokeEnabled: true, strokeWidth: 6, strokeColor: "#000000", glowEnabled: true, glowColor: "#FF0000", glowSize: 24, bgOpacity: 0.75, positionY: 38 },
  { id: "skia_slide_punch", name: "Slide Punch", desc: "Poppins dynamic entrance with drop shadow", color: "#FFFFFF", fontSize: 52, fontFamily: "Poppins", fontWeight: "700", strokeEnabled: true, strokeWidth: 4, strokeColor: "#000000", bgOpacity: 0.6, positionY: 38 },
  { id: "skia_typewriter", name: "Typewriter Terminal", desc: "Monospace phosphor green with cursor glow", color: "#00FF88", fontSize: 44, fontFamily: "monospace", fontWeight: "700", strokeEnabled: false, strokeWidth: 0, strokeColor: "#000000", glowEnabled: true, glowColor: "#00FF88", glowSize: 12, bgOpacity: 0.75, positionY: 45 },
];

// ─── Skia Subtitle Presets (matching backend SKIA_STYLES) ──────────────────

export interface SkiaSubtitlePreset {
  id: string;
  name: string;
  desc: string;
  category: string;
  color: string;
  highlightColor: string;
  fontFamily: string;
  fontSize: number;
  fontWeight: string;
  uppercase: boolean;
  lineTransition: "karaoke" | "word_pop" | "emphasis" | "line_reveal";
  gradientEnabled?: boolean;
  gradientFrom?: string;
  gradientTo?: string;
  highlightGradientFrom?: string;
  highlightGradientTo?: string;
  glowEnabled?: boolean;
  glowColor?: string;
  glassmorphism?: boolean;
  perWordBadge?: boolean;
  pathWave?: boolean;
  charStagger?: boolean;
  dualLayer?: boolean;
  maskReveal?: boolean;
  retroChrome?: boolean;
  outlineStack?: boolean;
  positionY: number;
  maxWordsPerLine: number;
}

export const SKIA_SUBTITLE_PRESETS: SkiaSubtitlePreset[] = [
  {
    id: "gradient_fill",
    name: "Gradient Fill",
    desc: "Multi-stop linear gradient text with angle shift on active words.",
    category: "gradient",
    color: "#667EEA",
    highlightColor: "#F5576C",
    fontFamily: "Poppins",
    fontSize: 38,
    fontWeight: "700",
    uppercase: false,
    lineTransition: "word_pop",
    gradientEnabled: true,
    gradientFrom: "#667EEA",
    gradientTo: "#F093FB",
    highlightGradientFrom: "#F5576C",
    highlightGradientTo: "#FF9A76",
    positionY: 80,
    maxWordsPerLine: 3,
  },
  {
    id: "glassmorphism",
    name: "Glassmorphism",
    desc: "Real frosted glass: backdrop blur + rounded card + inner border glow.",
    category: "glass",
    color: "#FFFFFF",
    highlightColor: "#38BDF8",
    fontFamily: "Inter",
    fontSize: 30,
    fontWeight: "600",
    uppercase: false,
    lineTransition: "karaoke",
    glassmorphism: true,
    positionY: 78,
    maxWordsPerLine: 4,
  },
  {
    id: "neon_tube",
    name: "Neon Tube",
    desc: "Hollow text with triple-pass outer glow (tight, medium, wide).",
    category: "neon",
    color: "#00FFFF",
    highlightColor: "#FF00FF",
    fontFamily: "Montserrat",
    fontSize: 42,
    fontWeight: "900",
    uppercase: true,
    lineTransition: "word_pop",
    glowEnabled: true,
    glowColor: "#00FFFF",
    positionY: 50,
    maxWordsPerLine: 2,
  },
  {
    id: "per_word_badge",
    name: "Per-Word Badge",
    desc: "Each word in its own pill-shaped badge with unique palette colors & subtle tilt.",
    category: "badge",
    color: "#FFFFFF",
    highlightColor: "#FFFFFF",
    fontFamily: "Nunito",
    fontSize: 28,
    fontWeight: "800",
    uppercase: false,
    lineTransition: "word_pop",
    perWordBadge: true,
    positionY: 78,
    maxWordsPerLine: 3,
  },
  {
    id: "path_wave",
    name: "Path Wave",
    desc: "Text rendered along a sine-wave bezier path with undulating curve.",
    category: "kinetic",
    color: "#FFFFFF",
    highlightColor: "#F97316",
    fontFamily: "Fredoka",
    fontSize: 34,
    fontWeight: "700",
    uppercase: false,
    lineTransition: "karaoke",
    pathWave: true,
    positionY: 76,
    maxWordsPerLine: 4,
  },
  {
    id: "char_stagger",
    name: "Char Stagger",
    desc: "Per-character staggered vertical scatter + kinetic type offset.",
    category: "kinetic",
    color: "#E2E8F0",
    highlightColor: "#FFFFFF",
    fontFamily: "Space Grotesk",
    fontSize: 36,
    fontWeight: "700",
    uppercase: true,
    lineTransition: "word_pop",
    charStagger: true,
    positionY: 80,
    maxWordsPerLine: 2,
  },
  {
    id: "dual_layer",
    name: "Dual Layer",
    desc: "Blurred purple color layer behind + sharp white text on top for depth.",
    category: "depth",
    color: "#FFFFFF",
    highlightColor: "#FBBF24",
    fontFamily: "Outfit",
    fontSize: 38,
    fontWeight: "700",
    uppercase: false,
    lineTransition: "word_pop",
    dualLayer: true,
    positionY: 76,
    maxWordsPerLine: 3,
  },
  {
    id: "mask_reveal",
    name: "Mask Reveal",
    desc: "Text stencil acting as clip mask revealing animated gradient beneath.",
    category: "mask",
    color: "#FF0080",
    highlightColor: "#FFFFFF",
    fontFamily: "Anton",
    fontSize: 48,
    fontWeight: "700",
    uppercase: true,
    lineTransition: "word_pop",
    maskReveal: true,
    positionY: 50,
    maxWordsPerLine: 2,
  },
  {
    id: "retro_chrome",
    name: "Retro Chrome",
    desc: "80s metallic chrome reflection gradient with gold highlight.",
    category: "retro",
    color: "#E8E8E8",
    highlightColor: "#FFD700",
    fontFamily: "Bebas Neue",
    fontSize: 46,
    fontWeight: "700",
    uppercase: true,
    lineTransition: "word_pop",
    retroChrome: true,
    positionY: 50,
    maxWordsPerLine: 3,
  },
  {
    id: "outline_stack",
    name: "Outline Stack",
    desc: "3D anaglyphic red, green, and blue offset outline stack without fill.",
    category: "3d",
    color: "#00FF00",
    highlightColor: "#FFFFFF",
    fontFamily: "Archivo Black",
    fontSize: 42,
    fontWeight: "700",
    uppercase: true,
    lineTransition: "word_pop",
    outlineStack: true,
    positionY: 50,
    maxWordsPerLine: 2,
  },
];
