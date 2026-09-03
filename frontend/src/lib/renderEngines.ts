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
  // ── Page 1: Premier Hero Styles (User Top 6) ──
  {
    id: "hook_cyber_hud",
    name: "Cyberpunk Tech HUD",
    kind: "hook",
    mood: "Cyberpunk",
    accent: "#00F0FF",
    desc: "Futuristic tactical HUD box · glowing cyan brackets & telemetry",
    preview: "SYSTEM OVERRIDE",
  },
  {
    id: "hook_floating_badge",
    name: "Top Floating Badge",
    kind: "hook",
    mood: "Viral Badge",
    accent: "#10B981",
    desc: "Top-floating emerald capsule · live pulse beacon & neon rim",
    preview: "● INSIGHT 2026",
  },
  {
    id: "hook_kinetic_split",
    name: "Kinetic Duotone Split",
    kind: "hook",
    mood: "High Energy",
    accent: "#FF6B00",
    desc: "Aggressive hyper-orange duotone slice · bold kinetic index",
    preview: "01 // KEY SECRET",
  },
  {
    id: "hook_electric_surge",
    name: "Electric Plasma Shockwave",
    kind: "hook",
    mood: "Electric",
    accent: "#818CF8",
    desc: "High-voltage plasma nebula aura · electric shockwave glow",
    preview: "VIRAL REVEAL",
  },
  {
    id: "hook_glass_minimal",
    name: "Frosted Glassmorphism",
    kind: "hook",
    mood: "Ultra-Glass",
    accent: "#A78BFA",
    desc: "Apple-grade frosted glass · rainbow prismatic edge blur",
    preview: "MODERN ESSENCE",
  },
  {
    id: "hook_editorial_pill",
    name: "Editorial Minimal Pill",
    kind: "hook",
    mood: "Luxury Noir",
    accent: "#E2E8F0",
    desc: "Obsidian velvet capsule · champagne gold diamond & serif type",
    preview: "◆ THE PERSPECTIVE",
  },

  // ── Page 2: High-Converting & Cinematic ──
  {
    id: "hook_breaking_news",
    name: "Breaking News Live",
    kind: "hook",
    mood: "Urgent News",
    accent: "#EF4444",
    desc: "High-urgency bulletin · flashing live pill & heavy ticker block",
    preview: "● BREAKING ALERT",
  },
  {
    id: "hook_luxury_noir",
    name: "Luxury Obsidian & Gold",
    kind: "hook",
    mood: "Prestige Gold",
    accent: "#D4AF37",
    desc: "Rolex/VIP titanium slate · double gold bevel & Roman Cinzel type",
    preview: "PRIVATE ACCESS",
  },
  {
    id: "hook_retro_synth",
    name: "80s Retro Synthwave",
    kind: "hook",
    mood: "Synthwave",
    accent: "#F43F5E",
    desc: "Miami sunset dual chrome gradient · glowing grid reflection",
    preview: "NIGHT DRIVE 80s",
  },
  {
    id: "hook_chromatic_gate_v2",
    name: "Chromatic Gate Y2K",
    kind: "hook",
    mood: "Y2K Cyber",
    accent: "#FF2E88",
    desc: "Offset RGB glitch gate · brutalist polygon chamfered cut",
    preview: "NO TURNING BACK",
  },
  {
    id: "hook_gradient_aura",
    name: "Gradient Aura Mesh",
    kind: "hook",
    mood: "Mesh Aura",
    accent: "#38BDF8",
    desc: "Multi-spectrum laser aura · liquid smooth gradient halo",
    preview: "FUTURE HORIZON",
  },
  {
    id: "hook_warning_hazard",
    name: "Warning Industrial Hazard",
    kind: "hook",
    mood: "Caution",
    accent: "#F59E0B",
    desc: "Industrial diagonal hazard stripes · critical alert warning",
    preview: "JANGAN SKIP",
  },

  // ── Page 3: Creative Technical & Sci-Fi ──
  {
    id: "hook_orbit_stamp_v2",
    name: "Orbit Stamp Seal",
    kind: "hook",
    mood: "Orbital Seal",
    accent: "#8B5CF6",
    desc: "Rotating orbital seal of proof · violet neon certification",
    preview: "OFFICIAL PROOF",
  },
  {
    id: "hook_pixel_ticker_v2",
    name: "Arcade Pixel Ticker",
    kind: "hook",
    mood: "Arcade 8-Bit",
    accent: "#F7FF58",
    desc: "Hard-edged arcade ticker · neon yellow pixel counter",
    preview: "LEVEL 99 UNLOCKED",
  },
  {
    id: "hook_blueprint_v2",
    name: "Blueprint Arch Reveal",
    kind: "hook",
    mood: "Blueprint",
    accent: "#52C7FF",
    desc: "Cyan isometric blueprint grid · measured technical schematic",
    preview: "HOW IT WORKS",
  },
  {
    id: "hook_comic_pop",
    name: "Comic Pop Burst",
    kind: "hook",
    mood: "Comic Pop",
    accent: "#FACC15",
    desc: "Tilted comic action burst · halftone pop-art drop shadow",
    preview: "POW! RAHASIA",
  },
  {
    id: "hook_hologram_scan",
    name: "Sci-Fi Hologram Scanner",
    kind: "hook",
    mood: "Hologram",
    accent: "#06B6D4",
    desc: "Futuristic telemetry feed · vertical cyan laser scanline",
    preview: "DATA DECRYPTED",
  },
  {
    id: "hook_cinema_tape",
    name: "Caution Stencil Tape",
    kind: "hook",
    mood: "Cinema Stencil",
    accent: "#EAB308",
    desc: "Cinematic tape border · industrial stencil typography",
    preview: "RESTRICTED INTEL",
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
  lineTransition: "karaoke" | "word_pop" | "emphasis" | "line_reveal" | "typing";
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
    desc: "Word-by-word highlight. Clean white text, active word turns yellow.",
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
    id: "hormozi_pop",
    name: "Hormozi Pop",
    desc: "Bold center-screen word pop. Bright lime active word with thick black stroke.",
    category: "impact",
    color: "#FFFFFF",
    highlightColor: "#00FF66",
    fontFamily: "Montserrat",
    fontSize: 52,
    fontWeight: "900",
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
    id: "devon_clean",
    name: "Devon Clean",
    desc: "Subtle rounded dark pill background, crisp white typography with cyan active pop.",
    category: "clean",
    color: "#E2E8F0",
    highlightColor: "#00F0FF",
    fontFamily: "Inter",
    fontSize: 32,
    fontWeight: "700",
    lineTransition: "karaoke",
    strokeEnabled: false,
    strokeWidth: 0,
    strokeColor: "#000000",
    bgEnabled: true,
    bgColor: "#0F172A",
    bgOpacity: 0.75,
    bgRadius: 14,
    positionY: 80,
    uppercase: false,
    maxWordsPerLine: 4,
  },
  {
    id: "podcast_dialogue",
    name: "Podcast Dialogue",
    desc: "Dark charcoal dialogue pill with emerald active speaker highlight for interviews.",
    category: "clean",
    color: "#E2E8F0",
    highlightColor: "#10B981",
    fontFamily: "Plus Jakarta Sans",
    fontSize: 32,
    fontWeight: "700",
    lineTransition: "karaoke",
    strokeEnabled: false,
    strokeWidth: 0,
    strokeColor: "#000000",
    bgEnabled: true,
    bgColor: "#18181B",
    bgOpacity: 0.85,
    bgRadius: 20,
    positionY: 78,
    uppercase: false,
    maxWordsPerLine: 4,
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
    id: "tech_mono",
    name: "Tech Monospace",
    desc: "Clean monospace typography in dark terminal box with cyan active word highlight.",
    category: "tech",
    color: "#94A3B8",
    highlightColor: "#06B6D4",
    fontFamily: "Space Grotesk",
    fontSize: 30,
    fontWeight: "700",
    lineTransition: "word_pop",
    strokeEnabled: false,
    strokeWidth: 0,
    strokeColor: "#000000",
    bgEnabled: true,
    bgColor: "#090D16",
    bgOpacity: 0.8,
    bgRadius: 8,
    positionY: 80,
    uppercase: true,
    maxWordsPerLine: 3,
  },
  {
    id: "gold_luxury",
    name: "Gold Luxury",
    desc: "Champagne gold serif typography with soft ambient drop shadow for luxury/documentary.",
    category: "cinematic",
    color: "#CBD5E1",
    highlightColor: "#FCD34D",
    fontFamily: "Playfair Display",
    fontSize: 34,
    fontWeight: "700",
    lineTransition: "word_pop",
    strokeEnabled: true,
    strokeWidth: 2,
    strokeColor: "#000000",
    bgEnabled: false,
    bgColor: "#000000",
    bgOpacity: 0.0,
    bgRadius: 0,
    positionY: 80,
    uppercase: false,
    maxWordsPerLine: 3,
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
  { id: "paper_clip_scrap", name: "Paper Clip Scrap", desc: "Sticky note pastel dengan klip kertas logam realistis dan washi tape", color: "#1C1917", fontSize: 54, fontFamily: "Montserrat", fontWeight: "900", strokeEnabled: false, strokeWidth: 0, strokeColor: "#000000", bgOpacity: 1.0, positionY: 42 },
  { id: "trending_radar", name: "Trending Radar", desc: "Frame neon cyber dengan badge radar TRENDING NOW dan corner crosshairs", color: "#FFFFFF", fontSize: 54, fontFamily: "Montserrat", fontWeight: "900", strokeEnabled: false, strokeWidth: 0, strokeColor: "#000000", glowEnabled: true, glowColor: "#D946EF", glowSize: 24, bgOpacity: 0.94, positionY: 40 },
  { id: "news_breaking_live", name: "Breaking News Live", desc: "Banner berita TV eksklusif dengan badge merah BREAKING dan live dot", color: "#FFFFFF", fontSize: 52, fontFamily: "Montserrat", fontWeight: "900", strokeEnabled: false, strokeWidth: 0, strokeColor: "#000000", bgOpacity: 0.95, positionY: 44 },
  { id: "skia_neon_cyberpunk", name: "Neon Cyberpunk", desc: "Dual cyan & magenta glow with futuristic glass framing", color: "#00F0FF", fontSize: 56, fontFamily: "Montserrat", fontWeight: "900", strokeEnabled: false, strokeWidth: 0, strokeColor: "#000000", gradientEnabled: true, gradientFrom: "#00F0FF", gradientTo: "#FF007F", glowEnabled: true, glowColor: "#00F0FF", glowSize: 28, bgOpacity: 0.85, positionY: 38 },
  { id: "skia_frosted_pill", name: "Frosted Pill", desc: "Glassmorphic rounded capsule with subtle gradient border", color: "#FFFFFF", fontSize: 50, fontFamily: "Plus Jakarta Sans", fontWeight: "800", strokeEnabled: false, strokeWidth: 0, strokeColor: "#000000", bgOpacity: 0.75, positionY: 40 },
  { id: "skia_aurora_gradient", name: "Aurora Gradient", desc: "Vivid emerald-to-violet Northern Lights gradient fill", color: "#10B981", fontSize: 56, fontFamily: "Outfit", fontWeight: "800", strokeEnabled: false, strokeWidth: 0, strokeColor: "#000000", gradientEnabled: true, gradientFrom: "#10B981", gradientTo: "#8B5CF6", glowEnabled: true, glowColor: "#8B5CF6", glowSize: 22, bgOpacity: 0.7, positionY: 38 },
  { id: "skia_impact_badge", name: "Impact Hazard", desc: "High-voltage amber warning banner with bold outline", color: "#FACC15", fontSize: 62, fontFamily: "Anton", fontWeight: "700", strokeEnabled: true, strokeWidth: 5, strokeColor: "#000000", glowEnabled: true, glowColor: "#EAB308", glowSize: 18, bgOpacity: 0.8, positionY: 38 },
  { id: "skia_3d_chrome", name: "3D Chrome", desc: "Reflective metallic silver and gold bevel luster", color: "#F1F5F9", fontSize: 58, fontFamily: "Bebas Neue", fontWeight: "700", strokeEnabled: true, strokeWidth: 2, strokeColor: "#000000", gradientEnabled: true, gradientFrom: "#F8FAFC", gradientTo: "#FBBF24", bgOpacity: 0.75, positionY: 40 },
  { id: "skia_ruby_flame", name: "Ruby Flame", desc: "Fiery crimson-to-amber heat wave with outer aura", color: "#FF2E2E", fontSize: 60, fontFamily: "Bungee", fontWeight: "400", strokeEnabled: false, strokeWidth: 0, strokeColor: "#000000", gradientEnabled: true, gradientFrom: "#FF3366", gradientTo: "#FF9900", glowEnabled: true, glowColor: "#FF2E2E", glowSize: 26, bgOpacity: 0.75, positionY: 38 },
  { id: "skia_gold_prestige", name: "Gold Prestige", desc: "Luxury 24K specular gold with letterbox framing", color: "#FDE047", fontSize: 58, fontFamily: "Playfair Display", fontWeight: "700", strokeEnabled: false, strokeWidth: 0, strokeColor: "#000000", gradientEnabled: true, gradientFrom: "#FEF08A", gradientTo: "#CA8A04", bgOpacity: 0.85, positionY: 42 },
  { id: "skia_minimal_editorial", name: "Clean Editorial", desc: "Minimalist Swiss headline with crisp modern contrast", color: "#FFFFFF", fontSize: 48, fontFamily: "Inter", fontWeight: "800", strokeEnabled: false, strokeWidth: 0, strokeColor: "#000000", bgOpacity: 0.65, positionY: 42 },
  { id: "skia_zoom_punch", name: "Zoom Punch", desc: "Bold punch with GPU canvas text stroke & drop shadow", color: "#FFFFFF", fontSize: 58, fontFamily: "Anton", fontWeight: "700", strokeEnabled: true, strokeWidth: 5, strokeColor: "#000000", bgOpacity: 0.6, positionY: 40 },
  { id: "skia_glitch_rgb", name: "Glitch RGB", desc: "Chromatic RGB split channel rasterizer burst", color: "#FFFFFF", fontSize: 58, fontFamily: "Anton", fontWeight: "700", strokeEnabled: false, strokeWidth: 0, strokeColor: "#000000", bgOpacity: 0.7, positionY: 40 },
  { id: "skia_typewriter", name: "Typewriter Matrix", desc: "Monospace phosphor green with CRT terminal glow", color: "#22C55E", fontSize: 44, fontFamily: "Space Grotesk", fontWeight: "700", strokeEnabled: false, strokeWidth: 0, strokeColor: "#000000", glowEnabled: true, glowColor: "#22C55E", glowSize: 14, bgOpacity: 0.8, positionY: 44 },
  { id: "skia_fade_scale", name: "Fade Scale", desc: "Smooth GPU alpha & scale blending entrance", color: "#FFFFFF", fontSize: 50, fontFamily: "Poppins", fontWeight: "700", strokeEnabled: true, strokeWidth: 3, strokeColor: "#000000", bgOpacity: 0.5, positionY: 42 },
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
  lineTransition: "karaoke" | "word_pop" | "emphasis" | "line_reveal" | "typing";
  gradientEnabled?: boolean;
  gradientFrom?: string;
  gradientTo?: string;
  highlightGradientFrom?: string;
  highlightGradientTo?: string;
  glowEnabled?: boolean;
  glowColor?: string;
  glassmorphism?: boolean;
  activeWordBadge?: boolean;
  dualLayer?: boolean;
  retroChrome?: boolean;
  outlineStack?: boolean;
  positionY: number;
  maxWordsPerLine: number;
}

export const SKIA_SUBTITLE_PRESETS: SkiaSubtitlePreset[] = [
  {
    id: "glassmorphism",
    name: "Glassmorphism",
    desc: "Real frosted glass: backdrop blur + rounded card + inner border glow.",
    category: "glass",
    color: "#FFFFFF",
    highlightColor: "#38BDF8",
    fontFamily: "Inter",
    fontSize: 32,
    fontWeight: "600",
    uppercase: false,
    lineTransition: "karaoke",
    glassmorphism: true,
    positionY: 78,
    maxWordsPerLine: 4,
  },
  {
    id: "clean_editorial",
    name: "Clean Editorial",
    desc: "Minimalist Swiss typography with a sleek slate pill and crisp word-by-word active highlight.",
    category: "clean",
    color: "#CBD5E1",
    highlightColor: "#38BDF8",
    fontFamily: "Inter",
    fontSize: 34,
    fontWeight: "700",
    uppercase: false,
    lineTransition: "karaoke",
    positionY: 80,
    maxWordsPerLine: 4,
  },
  {
    id: "podcast_pro",
    name: "Podcast Pro",
    desc: "Dialogue-optimized floating dark capsule with emerald active speaker highlight.",
    category: "clean",
    color: "#E2E8F0",
    highlightColor: "#10B981",
    fontFamily: "Plus Jakarta Sans",
    fontSize: 32,
    fontWeight: "800",
    uppercase: false,
    lineTransition: "karaoke",
    positionY: 78,
    maxWordsPerLine: 4,
  },
  {
    id: "kinetic_word_box",
    name: "Kinetic Word Box",
    desc: "Clean sans-serif text where active word is encased in a dynamic glowing solid pill badge.",
    category: "kinetic",
    color: "#E2E8F0",
    highlightColor: "#FFFFFF",
    fontFamily: "Plus Jakarta Sans",
    fontSize: 34,
    fontWeight: "800",
    uppercase: false,
    lineTransition: "word_pop",
    activeWordBadge: true,
    positionY: 78,
    maxWordsPerLine: 3,
  },
  {
    id: "neon_tube",
    name: "Neon Tube",
    desc: "Hollow text with triple-pass outer glow (tight, medium, wide) in cyan & hot pink.",
    category: "neon",
    color: "#00FFFF",
    highlightColor: "#FF007F",
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
    id: "gradient_fill",
    name: "Gradient Fill",
    desc: "Multi-stop linear gradient text with angle shift and specular shimmer on active words.",
    category: "gradient",
    color: "#6366F1",
    highlightColor: "#EC4899",
    fontFamily: "Poppins",
    fontSize: 38,
    fontWeight: "700",
    uppercase: false,
    lineTransition: "word_pop",
    gradientEnabled: true,
    gradientFrom: "#6366F1",
    gradientTo: "#EC4899",
    highlightGradientFrom: "#F5576C",
    highlightGradientTo: "#FF9A76",
    positionY: 80,
    maxWordsPerLine: 3,
  },
  {
    id: "cinematic_slate",
    name: "Cinematic Slate",
    desc: "Muted dark tones with warm champagne gold highlight for documentary & high-end clips.",
    category: "cinematic",
    color: "#CBD5E1",
    highlightColor: "#FCD34D",
    fontFamily: "Playfair Display",
    fontSize: 34,
    fontWeight: "700",
    uppercase: false,
    lineTransition: "word_pop",
    positionY: 78,
    maxWordsPerLine: 3,
  },
  {
    id: "modern_mono",
    name: "Modern Mono",
    desc: "Clean monospace typography with cyber cyan active word punch for tech and tutorial clips.",
    category: "tech",
    color: "#94A3B8",
    highlightColor: "#06B6D4",
    fontFamily: "Space Grotesk",
    fontSize: 32,
    fontWeight: "700",
    uppercase: true,
    lineTransition: "word_pop",
    positionY: 80,
    maxWordsPerLine: 3,
  },
  {
    id: "bold_impact_stroke",
    name: "Bold Impact",
    desc: "Anton heavy shorts punch with solid 3.5px black stroke and electric yellow active word.",
    category: "impact",
    color: "#FFFFFF",
    highlightColor: "#FACC15",
    fontFamily: "Anton",
    fontSize: 44,
    fontWeight: "800",
    uppercase: true,
    lineTransition: "word_pop",
    positionY: 78,
    maxWordsPerLine: 2,
  },
  {
    id: "dual_layer",
    name: "Dual Layer Depth",
    desc: "Blurred purple backlight shadow layer behind sharp white text on top for 3D depth.",
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
    id: "retro_chrome",
    name: "Retro Chrome",
    desc: "80s metallic chrome reflection gradient with gold highlight and hard drop shadow.",
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
    desc: "3D anaglyphic red and blue offset stroke outline stack without fill.",
    category: "3d",
    color: "#00FFFF",
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
