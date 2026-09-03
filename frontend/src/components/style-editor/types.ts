import type { Preset } from "@/lib/api";
import type { BackgroundMode } from "@/components/BackgroundTemplateSection";
import {
  type RenderEngine,
  defaultHfHookId,
  defaultHfSubtitleId,
} from "@/lib/renderEngines";

export type OptionMeta = {
  label: string;
  mood: string;
  accent: string;
  preview: string;
  desc: string;
};

export const PAGINATION_PAGE_SIZE = 6;

export type SubtitleVisualPreset = string;

// ─── Interfaces ─────────────────────────────────────────────────────────────

export interface HookStyle {
  animation: string;
  text: string;
  /** remotion = full custom (default); hyperframes = fixed fast templates */
  engine?: RenderEngine;
  /** HF template id when engine=hyperframes */
  hf_template?: string;
  fontFamily: string;
  fontSize: number;
  fontWeight: string;
  letterSpacing: number;
  lineHeight: number;
  color: string;
  gradientEnabled: boolean;
  gradientFrom: string;
  gradientTo: string;
  gradientAngle: number;
  shadowEnabled: boolean;
  shadowColor: string;
  shadowBlur: number;
  shadowX: number;
  shadowY: number;
  glowEnabled: boolean;
  glowColor: string;
  glowSize: number;
  bgColor: string;
  bgOpacity: number;
  position: "center" | "top" | "bottom";
  positionY: number; // fine-tune vertical %
  textAlign: "center" | "left" | "right";
  uppercase: boolean;
  italic: boolean;
  // Accent line
  lineEnabled: boolean;
  linePosition: "top" | "bottom" | "left" | "right" | "center-h" | "center-v" | "auto-bottom";
  lineColor: string;
  lineWidth: number;
  lineAutoWidth: boolean;
  lineThickness: number;
  lineOffset: number;
  // Border/box around text
  boxEnabled: boolean;
  boxColor: string;
  boxOpacity: number;
  boxPadding: number;
  boxRadius: number;
  strokeEnabled: boolean;
  strokeColor: string;
  strokeWidth: number;
  // Custom hook components
  badgeEnabled: boolean;
  badgeText: string;
  footerEnabled?: boolean;
  footerText?: string;
  decorativeElements: boolean;
  motionIntensity: number;
  // Duration
  duration: number;
  fadeIn: number;
  fadeOut: number;
  transitionStyle?: "cut" | "fade" | "slide" | "zoom";
  transitionDuration?: number;
}

export interface SubtitleStyle {
  enabled?: boolean;
  stylePreset: SubtitleVisualPreset;
  engine?: RenderEngine;
  hf_template?: string;
  fontFamily: string;
  fontSize: number;
  fontWeight: string;
  letterSpacing: number;
  lineHeight: number;
  textAlign?: "left" | "center" | "right";
  textOpacity?: number;
  color: string;
  highlightColor: string;
  highlightScale: number;
  highlightBold: boolean;
  highlightStyle: "scale" | "underline" | "background" | "strikethrough";
  highlightGlow: boolean;
  highlightGlowColor: string;
  highlightWords: string[];
  // Dual style (optional — separate font/style for highlight words)
  dualStyleEnabled: boolean;
  highlightFontFamily: string;
  highlightFontSize: number;
  highlightFontWeight: string;
  highlightLetterSpacing: number;
  highlightItalic: boolean;
  highlightUppercase: boolean;
  highlightStrokeEnabled: boolean;
  highlightStrokeColor: string;
  highlightStrokeWidth: number;
  highlightShadowEnabled: boolean;
  highlightShadowColor: string;
  highlightShadowBlur: number;
  // Common
  bgEnabled: boolean;
  bgColor: string;
  bgOpacity: number;
  bgRadius: number;
  bgPadding: number;
  position: "bottom" | "center" | "top";
  positionY: number;
  uppercase: boolean;
  capitalize: boolean;
  italic: boolean;
  strokeEnabled: boolean;
  strokeColor: string;
  strokeWidth: number;
  shadowEnabled: boolean;
  shadowColor: string;
  shadowBlur: number;
  shadowX?: number;
  shadowY?: number;
  shadowOpacity?: number;
  maxWordsPerLine: number;
  maxWidthPct?: number;
  wordSpacing: number;
  animationStyle: "pop" | "fade" | "slide" | "none";
  animationSpeed: number;
  lineTransition: "word_pop" | "emphasis" | "line_reveal" | "karaoke" | "typing";
  // Skia / Custom Shaders
  glowEnabled?: boolean;
  glowColor?: string;
  gradientEnabled?: boolean;
  gradientFrom?: string;
  gradientTo?: string;
  subjectAwarePositioning?: boolean;
  safeAreaMargin?: number;
}

export interface TextEmphasisStyle {
  effectMode: "auto" | "depth_cutout" | "hero_punch" | "side_rail" | "float_track" | "smart_gap" | "orbit_halo" | "z_parallax" | "word_cascade" | "split_impact" | "type_pulse" | "sticker_pop" | "mirror_echo";
  animation: "rise" | "impact" | "slide" | "static_glitch" | "glow" | "elastic" | "blur_in" | "flip_y";
  fontFamily: string;
  fontSize: number;
  fontWeight: string;
  letterSpacing: number;
  lineHeight: number;
  color: string;
  accentColor: string;
  uppercase: boolean;
  strokeEnabled: boolean;
  strokeColor: string;
  strokeWidth: number;
  shadowEnabled: boolean;
  shadowColor: string;
  shadowBlur: number;
  positionY: number;
  maxWidthPct: number;
  maskFeather: number;
  floatSpeed?: number;
  avoidPadding?: number;
  aroundHeadRadius?: number;
  depthIntensity?: number;
  depthParallax?: number;
  depthFade?: number;
  kineticStagger?: number;
  echoOffset?: number;
  stickerAngle?: number;
  typeSpeed?: number;
}

export interface WatermarkStyle {
  enabled: boolean;
  type: "image" | "text";
  /** data:image/...;base64,... for image type */
  imageDataUrl: string | null;
  text: string;
  fontFamily: string;
  fontSize: number;
  fontWeight: string;
  color: string;
  /** image width as % of video width */
  sizePct: number;
  /** 0..100 */
  opacity: number;
  position: "top-left" | "top-center" | "top-right" | "center-left" | "center" | "center-right" | "bottom-left" | "bottom-center" | "bottom-right";
  /** margin from edges, % of video dimension */
  marginPct: number;
}

export interface CtaStyle {
  enabled: boolean;
  ctaType: "card" | "text" | "both"; // Mode: Card, Plain Text, or Text + Icon
  template: "follow_badge" | "like_share" | "link_bio" | "subscribe_pill" | "comment_prompt" | "custom_card";
  duration: number; // 1.0 to 6.0s (default 3.0s)
  // Text fields
  text: string;
  headline: string;
  subhead: string;
  buttonText: string;
  // Icon / Platform
  selectedIcon: "tiktok" | "instagram" | "youtube" | "bell" | "link" | "share" | "message" | "zap" | "user_plus" | "heart" | "star";
  socialPlatform: "tiktok" | "instagram" | "youtube" | "general" | "custom";
  socialHandle: string;
  // Positioning & Layout
  position: "bottom" | "center" | "lower-third" | "top";
  bgBox: boolean; // whether plain text / both has background card/pill or is transparent
  animation: "slide_up" | "pop_in" | "fade_bounce" | "glow_pulse" | "glitch";
  // Styling
  primaryColor: string;
  textColor: string;
  backgroundColor: string;
  bgOpacity: number; // 0..100
  fontSize: number; // px
  fontFamily: string;
  fontWeight: string;
  showIcon: boolean;
  showArrow: boolean;
  avatarUrl: string | null;
}

export interface StyleEditorModalProps {
  open: boolean;
  onClose: () => void;
  hookStyle: HookStyle;
  subtitleStyle: SubtitleStyle;
  textEmphasisStyle?: TextEmphasisStyle;
  onHookChange: (style: HookStyle) => void;
  onSubtitleChange: (style: SubtitleStyle) => void;
  onTextEmphasisChange?: (style: TextEmphasisStyle) => void;
  watermarkStyle?: WatermarkStyle;
  onWatermarkChange?: (style: WatermarkStyle) => void;
  ctaStyle?: CtaStyle;
  onCtaChange?: (style: CtaStyle) => void;
  brollStyle?: Record<string, any>;
  onBrollChange?: (broll: Record<string, any>) => void;
  autopostStyle?: Record<string, any>;
  onAutopostChange?: (autopost: Record<string, any>) => void;
  onPresetLoad?: (preset: Preset) => void;
  aspectRatio?: string;
  inline?: boolean;
  activeTab?: "presets" | "hook" | "subtitle" | "transition" | "ai_text" | "other";
  thumbnailUrl?: string;
  isSuperadmin?: boolean;
  isPremium?: boolean;
  userFeatures?: string[];
  activePresetId?: number | null;
  onPresetSelect?: (id: number) => void;
  onProcess?: () => void;
  processing?: boolean;
  processProgress?: { stage: string; percentage: number };
  aiTextPreviewContext?: { jobId: string; clipRank: number; frame: number };
  aiTextEnabled?: boolean;
  /** Canvas bg for 16:9 / 1:1 live preview */
  canvasBackground?: {
    mode: BackgroundMode;
    templateId: string;
    imageDataUrl: string | null;
  } | null;
}

// ─── Default Values ─────────────────────────────────────────────────────────

export const DEFAULT_WATERMARK_STYLE: WatermarkStyle = {
  enabled: false,
  type: "text",
  imageDataUrl: null,
  text: "@yourchannel",
  fontFamily: "Poppins",
  fontSize: 28,
  fontWeight: "600",
  color: "#FFFFFF",
  sizePct: 20,
  opacity: 60,
  position: "bottom-right",
  marginPct: 3,
};

export const DEFAULT_CTA_STYLE: CtaStyle = {
  enabled: false,
  ctaType: "card",
  template: "follow_badge",
  duration: 3.0,
  text: "Jangan lupa follow untuk tips berikutnya!",
  headline: "Follow For More",
  subhead: "@yourchannel",
  buttonText: "FOLLOW",
  selectedIcon: "tiktok",
  socialPlatform: "tiktok",
  socialHandle: "@yourchannel",
  position: "bottom",
  bgBox: true,
  animation: "slide_up",
  primaryColor: "#10B981",
  textColor: "#FFFFFF",
  backgroundColor: "#0F172A",
  bgOpacity: 90,
  fontSize: 28,
  fontFamily: "Poppins",
  fontWeight: "700",
  showIcon: true,
  showArrow: true,
  avatarUrl: null,
};

export const DEFAULT_HOOK_STYLE: HookStyle = {
  animation: "podcast_lower_third",
  text: "",
  engine: "remotion",
  hf_template: defaultHfHookId(),
  fontFamily: "Barlow Condensed",
  fontSize: 52,
  fontWeight: "900",
  letterSpacing: 0,
  lineHeight: 1.3,
  color: "#FFFFFF",
  gradientEnabled: false,
  gradientFrom: "#FFFFFF",
  gradientTo: "#FFCC00",
  gradientAngle: 180,
  shadowEnabled: true,
  shadowColor: "#000000",
  shadowBlur: 12,
  shadowX: 0,
  shadowY: 4,
  glowEnabled: false,
  glowColor: "#16F2B3",
  glowSize: 24,
  bgColor: "#06111F",
  bgOpacity: 0.42,
  position: "bottom",
  positionY: 78,
  textAlign: "left",
  uppercase: true,
  italic: false,
  lineEnabled: false,
  linePosition: "bottom",
  lineColor: "#16F2B3",
  lineWidth: 60,
  lineAutoWidth: false,
  lineThickness: 4,
  lineOffset: 12,
  boxEnabled: false,
  boxColor: "#FFFFFF",
  boxOpacity: 0.1,
  boxPadding: 20,
  boxRadius: 8,
  strokeEnabled: false,
  strokeColor: "#000000",
  strokeWidth: 3,
  badgeEnabled: true,
  badgeText: "ON AIR",
  footerEnabled: true,
  footerText: "READ MORE AT chatgpt.com",
  decorativeElements: true,
  motionIntensity: 1.0,
  duration: 3.0,
  fadeIn: 0.3,
  fadeOut: 0.3,
};

export const DEFAULT_SUBTITLE_STYLE: SubtitleStyle = {
  enabled: true,
  stylePreset: "classic",
  engine: "ffmpeg",
  hf_template: defaultHfSubtitleId(),
  fontFamily: "Poppins",
  fontSize: 34,
  fontWeight: "700",
  letterSpacing: 0,
  lineHeight: 1.4,
  color: "#FFFFFF",
  highlightColor: "#FFCC00",
  highlightScale: 1.2,
  highlightBold: true,
  highlightStyle: "scale",
  highlightGlow: false,
  highlightGlowColor: "#FFCC00",
  highlightWords: [],
  dualStyleEnabled: false,
  highlightFontFamily: "Anton",
  highlightFontSize: 38,
  highlightFontWeight: "900",
  highlightLetterSpacing: 1,
  highlightItalic: false,
  highlightUppercase: true,
  highlightStrokeEnabled: true,
  highlightStrokeColor: "#000000",
  highlightStrokeWidth: 3,
  highlightShadowEnabled: true,
  highlightShadowColor: "#000000",
  highlightShadowBlur: 12,
  bgEnabled: true,
  bgColor: "#000000",
  bgOpacity: 0.4,
  bgRadius: 8,
  bgPadding: 12,
  position: "bottom",
  positionY: 85,
  uppercase: false,
  capitalize: false,
  italic: false,
  strokeEnabled: true,
  strokeColor: "#000000",
  strokeWidth: 2,
  shadowEnabled: true,
  shadowColor: "#000000",
  shadowBlur: 8,
  maxWordsPerLine: 3,
  wordSpacing: 6,
  animationStyle: "pop",
  animationSpeed: 1.0,
  lineTransition: "word_pop",
};

export const DEFAULT_TEXT_EMPHASIS_STYLE: TextEmphasisStyle = {
  effectMode: "auto",
  animation: "impact",
  fontFamily: "Bebas Neue",
  fontSize: 104,
  fontWeight: "900",
  letterSpacing: 2,
  lineHeight: 0.9,
  color: "#FFFFFF",
  accentColor: "#FF3B5C",
  uppercase: true,
  strokeEnabled: true,
  strokeColor: "#0A0A0B",
  strokeWidth: 3,
  shadowEnabled: true,
  shadowColor: "#000000",
  shadowBlur: 28,
  positionY: 48,
  maxWidthPct: 86,
  maskFeather: 9,
  floatSpeed: 1.15,
  avoidPadding: 44,
  aroundHeadRadius: 58,
  depthIntensity: 0.55,
  depthParallax: 0.4,
  depthFade: 0.4,
  kineticStagger: 5,
  echoOffset: 10,
  stickerAngle: -6,
  typeSpeed: 1.4,
};

// ─── Normalizers ────────────────────────────────────────────────────────────

export function normaliseCtaStyle(raw: any): CtaStyle {
  if (!raw || typeof raw !== "object") return { ...DEFAULT_CTA_STYLE };
  const dur = typeof raw.duration === "number" ? raw.duration : (typeof raw.duration_sec === "number" ? raw.duration_sec : DEFAULT_CTA_STYLE.duration);
  const ctaType = ["card", "text", "both"].includes(raw.ctaType) ? raw.ctaType : (["card", "text", "both"].includes(raw.mode) ? raw.mode : "card");
  return {
    enabled: Boolean(raw.enabled),
    ctaType,
    template: ["follow_badge", "like_share", "link_bio", "subscribe_pill", "comment_prompt", "custom_card"].includes(raw.template) ? raw.template : "follow_badge",
    duration: Math.max(1.0, Math.min(6.0, dur || 3.0)),
    text: typeof raw.text === "string" && raw.text.trim() ? raw.text : (typeof raw.headline === "string" ? raw.headline : DEFAULT_CTA_STYLE.text),
    headline: typeof raw.headline === "string" ? raw.headline : (typeof raw.text === "string" ? raw.text : DEFAULT_CTA_STYLE.headline),
    subhead: typeof raw.subhead === "string" ? raw.subhead : (typeof raw.handle === "string" ? raw.handle : DEFAULT_CTA_STYLE.subhead),
    buttonText: typeof raw.buttonText === "string" ? raw.buttonText : DEFAULT_CTA_STYLE.buttonText,
    selectedIcon: ["tiktok", "instagram", "youtube", "bell", "link", "share", "message", "zap", "user_plus", "heart", "star"].includes(raw.selectedIcon) ? raw.selectedIcon : "tiktok",
    socialPlatform: ["tiktok", "instagram", "youtube", "general", "custom"].includes(raw.socialPlatform) ? raw.socialPlatform : (raw.type || "tiktok"),
    socialHandle: typeof raw.socialHandle === "string" ? raw.socialHandle : (typeof raw.handle === "string" ? raw.handle : DEFAULT_CTA_STYLE.socialHandle),
    position: ["bottom", "center", "lower-third", "top"].includes(raw.position) ? raw.position : "bottom",
    bgBox: raw.bgBox !== undefined ? Boolean(raw.bgBox) : true,
    animation: ["slide_up", "pop_in", "fade_bounce", "glow_pulse", "glitch"].includes(raw.animation) ? raw.animation : "slide_up",
    primaryColor: typeof raw.primaryColor === "string" ? raw.primaryColor : DEFAULT_CTA_STYLE.primaryColor,
    textColor: typeof raw.textColor === "string" ? raw.textColor : DEFAULT_CTA_STYLE.textColor,
    backgroundColor: typeof raw.backgroundColor === "string" ? raw.backgroundColor : DEFAULT_CTA_STYLE.backgroundColor,
    bgOpacity: typeof raw.bgOpacity === "number" ? Math.max(0, Math.min(100, raw.bgOpacity)) : DEFAULT_CTA_STYLE.bgOpacity,
    fontSize: typeof raw.fontSize === "number" ? Math.max(16, Math.min(60, raw.fontSize)) : DEFAULT_CTA_STYLE.fontSize,
    fontFamily: typeof raw.fontFamily === "string" ? raw.fontFamily : DEFAULT_CTA_STYLE.fontFamily,
    fontWeight: typeof raw.fontWeight === "string" ? raw.fontWeight : DEFAULT_CTA_STYLE.fontWeight,
    showIcon: raw.showIcon !== undefined ? Boolean(raw.showIcon) : true,
    showArrow: raw.showArrow !== undefined ? Boolean(raw.showArrow) : true,
    avatarUrl: typeof raw.avatarUrl === "string" ? raw.avatarUrl : null,
  };
}

const LEGACY_TE_EFFECT: Record<string, TextEmphasisStyle["effectMode"]> = {
  behind_person: "depth_cutout",
  spotlight: "hero_punch",
  side_label: "side_rail",
  floating_text: "float_track",
  auto_avoid: "smart_gap",
  around_head: "orbit_halo",
  depth_text: "z_parallax",
  kinetic_type: "word_cascade",
};

const LEGACY_TE_ANIM: Record<string, TextEmphasisStyle["animation"]> = {
  cinematic: "rise",
  slam: "impact",
  reveal: "slide",
  glitch: "static_glitch",
  neon: "glow",
};

export function normaliseTextEmphasisStyle(partial?: Partial<TextEmphasisStyle> | Record<string, unknown> | null): TextEmphasisStyle {
  const raw = { ...DEFAULT_TEXT_EMPHASIS_STYLE, ...(partial || {}) } as TextEmphasisStyle & Record<string, unknown>;
  const effectRaw = String(raw.effectMode || "auto");
  raw.effectMode = (LEGACY_TE_EFFECT[effectRaw] || effectRaw) as TextEmphasisStyle["effectMode"];
  const animRaw = String(raw.animation || "impact");
  raw.animation = (LEGACY_TE_ANIM[animRaw] || animRaw) as TextEmphasisStyle["animation"];
  return raw as TextEmphasisStyle;
}

// ─── Font and Preset Constants ──────────────────────────────────────────────

export const FONT_OPTIONS = [
  "Poppins",
  "Inter",
  "Montserrat",
  "Anton",
  "Bebas Neue",
  "Oswald",
  "Raleway",
  "Roboto",
  "Roboto Condensed",
  "Lato",
  "Nunito",
  "Playfair Display",
  "Merriweather",
  "Lora",
  "Barlow Condensed",
  "Archivo Black",
  "Black Ops One",
  "Bungee",
  "Righteous",
  "Titillium Web",
  "Noto Sans",
  "monospace",
];

export const HOOK_FONT_SUGGESTIONS = ["Barlow Condensed", "Anton", "Archivo Black", "Playfair Display", "Bungee", "Montserrat"];
export const SUBTITLE_FONT_SUGGESTIONS = ["Montserrat", "Poppins", "Inter", "Anton", "Bebas Neue", "Archivo Black", "Barlow Condensed", "Roboto Condensed", "Noto Sans"];
export const HIGHLIGHT_FONT_SUGGESTIONS = ["Anton", "Archivo Black", "Bebas Neue", "Bungee", "Barlow Condensed", "Black Ops One"];

export const HOOK_ANIMATIONS = [
  "paper_clip_scrap",
  "trending_radar",
  "news_breaking_live",
  "news_viralin_badge",
  "news_portal_pantau",
  "news_offset_box",
  "brutalist_bracket",
  "quote_strip_tape",
  "podcast_lower_third",
  "quote_card",
  "waveform_pulse",
  "breaking_tape",
  "mic_drop",
  "split_panel",
  "kinetic_stack",
  "glass_flash",
  "marker_swipe",
  "signal_scan",
  "comment_reply",
  "search_prompt",
  "countdown_list",
  "pov_stamp",
];

export const HOOK_ANIMATION_META: Record<string, OptionMeta> = {
  paper_clip_scrap: { label: "Paper Clip Scrap", mood: "Editorial Physical", accent: "#EAB308", preview: "CLIP", desc: "Kartu sticky note pastel dengan klip kertas logam realistis dan washi tape." },
  trending_radar: { label: "Trending Radar", mood: "Viral Drop", accent: "#D946EF", preview: "VIRAL", desc: "Frame neon cyber dengan badge radar TRENDING NOW dan corner crosshairs." },
  news_breaking_live: { label: "Breaking News Live", mood: "Broadcast Urgent", accent: "#DC2626", preview: "BREAKING", desc: "Banner berita TV eksklusif dengan badge merah BREAKING dan indikator live." },
  news_viralin_badge: { label: "#VIRALIN Badge", mood: "Akurat News", accent: "#EAB308", preview: "#VIRAL", desc: "Kartu kuning dengan badge miring #VIRALIN dan tumpukan kertas putih." },
  news_portal_pantau: { label: "News Portal Notch", mood: "Breaking News", accent: "#DC2626", preview: "NEWS", desc: "Kartu berita putih dengan kategori merah dan speech bubble notch di bawah." },
  news_offset_box: { label: "Detik Red Box", mood: "Urgent Alert", accent: "#DC2626", preview: "ALERT", desc: "Kotak merah tebal dengan frame putih bertingkat di sudut kiri atas." },
  brutalist_bracket: { label: "Brutalist Bracket", mood: "Stop Frame", accent: "#000000", preview: "[ STOP ]", desc: "Kartu putih dengan sudut siku L hitam industrial dan aksen seru merah !!" },
  quote_strip_tape: { label: "Quote Tape Strips", mood: "Interview Quote", accent: "#0D9488", preview: "TAPE", desc: "Pita teks baris per baris dengan badge icon kutipan toska." },
  podcast_lower_third: { label: "On-Air Lower", mood: "Podcast live", accent: "#16F2B3", preview: "LIVE", desc: "Lower-third khas podcast dengan badge on-air." },
  quote_card: { label: "Quote Card", mood: "Editorial", accent: "#FF4D2D", preview: "QUOTE", desc: "Kartu quote untuk satu kalimat yang memorable." },
  waveform_pulse: { label: "Waveform", mood: "Audio pulse", accent: "#14F1D9", preview: "WAVE", desc: "Bar audio bergerak supaya terasa seperti momen suara." },
  breaking_tape: { label: "Breaking Tape", mood: "Hot take", accent: "#FFDD2D", preview: "TAKE", desc: "Tape diagonal untuk opini yang memancing komentar." },
  mic_drop: { label: "Mic Drop", mood: "Final answer", accent: "#FF4D7D", preview: "DROP", desc: "Badge jatuh dengan impact line." },
  split_panel: { label: "Split Panel", mood: "Debate card", accent: "#38BDF8", preview: "SPLIT", desc: "Panel dua sisi dengan rail warna untuk punchline argumentatif." },
  kinetic_stack: { label: "Kinetic Stack", mood: "Fast stack", accent: "#F97316", preview: "STACK", desc: "Baris teks bertumpuk, masuk bergantian, cocok untuk hook cepat." },
  glass_flash: { label: "Glass Flash", mood: "Premium glass", accent: "#C084FC", preview: "GLASS", desc: "Panel kaca dengan sweep cahaya dan glow lembut." },
  marker_swipe: { label: "Marker Swipe", mood: "Highlighted", accent: "#FDE047", preview: "MARK", desc: "Coretan marker bergerak di belakang teks." },
  signal_scan: { label: "Signal Scan", mood: "Tech signal", accent: "#22D3EE", preview: "SCAN", desc: "Scanline dan pulse digital untuk momen analisis." },
  comment_reply: { label: "Reply Comment", mood: "TikTok native", accent: "#F8FAFC", preview: "REPLY", desc: "Bubble balasan komentar sebagai konteks hook langsung." },
  search_prompt: { label: "Search Prompt", mood: "Discovery", accent: "#22D3EE", preview: "SEARCH", desc: "Search bar ala discovery untuk memancing rasa ingin tahu." },
  countdown_list: { label: "Countdown List", mood: "Retention", accent: "#FACC15", preview: "03", desc: "Nomor besar dan progress rail untuk hook listicle." },
  pov_stamp: { label: "POV Stamp", mood: "Creator POV", accent: "#FB7185", preview: "POV", desc: "Stamp POV yang menjaga konteks cerita sejak detik pertama." },
};

export const SUBTITLE_ANIMATION_META: Record<SubtitleStyle["animationStyle"], OptionMeta> = {
  pop: { label: "Pop", mood: "Punchy", accent: "#34D399", preview: "POP", desc: "Kata aktif membesar cepat dan jelas." },
  fade: { label: "Fade", mood: "Soft", accent: "#93C5FD", preview: "FADE", desc: "Masuk halus untuk podcast yang tenang." },
  slide: { label: "Slide", mood: "Clean motion", accent: "#FBBF24", preview: "SLIDE", desc: "Naik singkat, enak untuk dialog cepat." },
  none: { label: "None", mood: "Static", accent: "#A1A1AA", preview: "TEXT", desc: "Tanpa animasi tambahan." },
};

export const SUBTITLE_TRANSITION_META: Record<SubtitleStyle["lineTransition"], OptionMeta> = {
  word_pop: { label: "Word Pop", mood: "Readable", accent: "#34D399", preview: "word", desc: "Mode standar, highlight mengikuti kata aktif." },
  emphasis: { label: "Big Keyword", mood: "Keyword hero", accent: "#FACC15", preview: "BIG", desc: "Kata terkuat dibuat besar seperti punchline." },
  line_reveal: { label: "Line Reveal", mood: "Editorial", accent: "#A78BFA", preview: "LINE", desc: "Baris muncul rapi seperti caption editorial." },
  karaoke: { label: "Karaoke", mood: "Smooth", accent: "#38BDF8", preview: "KARAOKE", desc: "Kata demi kata tersorot berurutan." },
  typing: { label: "Typewriter", mood: "Dynamic typing", accent: "#10B981", preview: "TYPE...", desc: "Teks mengetik muncul kata demi kata dengan kursor aktif." },
};

export const HIGHLIGHT_STYLE_META: Record<SubtitleStyle["highlightStyle"], OptionMeta> = {
  scale: { label: "Scale", mood: "Bigger word", accent: "#FACC15", preview: "Aa", desc: "Kata penting membesar." },
  underline: { label: "Underline", mood: "Marked", accent: "#38BDF8", preview: "__", desc: "Garis bawah untuk penekanan rapi." },
  background: { label: "Background", mood: "Tag", accent: "#34D399", preview: "BOX", desc: "Highlight seperti label kecil." },
  strikethrough: { label: "Strike", mood: "Contrarian", accent: "#FB7185", preview: "DEL", desc: "Cocok untuk kontra atau koreksi." },
};

export type HookCapabilities = {
  badge: boolean;
  footer: boolean;
  decorative: boolean;
  gradient: boolean;
  panel: boolean;
  outline: boolean;
};

export const DEFAULT_HOOK_CAPABILITIES: HookCapabilities = {
  badge: true,
  footer: true,
  decorative: true,
  gradient: true,
  panel: false,
  outline: true,
};

export const HOOK_CAPABILITIES: Record<string, HookCapabilities> = {
  news_viralin_badge: { badge: true, footer: false, decorative: true, gradient: false, panel: true, outline: false },
  news_portal_pantau: { badge: true, footer: true, decorative: true, gradient: false, panel: true, outline: false },
  news_offset_box: { badge: false, footer: false, decorative: true, gradient: false, panel: true, outline: false },
  brutalist_bracket: { badge: false, footer: false, decorative: true, gradient: false, panel: true, outline: false },
  quote_strip_tape: { badge: true, footer: false, decorative: true, gradient: false, panel: true, outline: false },
  podcast_lower_third: { badge: true, footer: false, decorative: true, gradient: false, panel: false, outline: false },
  quote_card: { badge: false, footer: false, decorative: true, gradient: false, panel: true, outline: false },
  waveform_pulse: { badge: true, footer: false, decorative: true, gradient: true, panel: false, outline: false },
  breaking_tape: { badge: true, footer: false, decorative: true, gradient: false, panel: true, outline: false },
  mic_drop: { badge: true, footer: false, decorative: true, gradient: true, panel: true, outline: false },
  split_panel: { badge: true, footer: false, decorative: true, gradient: true, panel: true, outline: false },
  kinetic_stack: { badge: false, footer: false, decorative: false, gradient: false, panel: true, outline: false },
  glass_flash: { badge: true, footer: false, decorative: true, gradient: true, panel: true, outline: false },
  marker_swipe: { badge: true, footer: false, decorative: true, gradient: false, panel: true, outline: false },
  signal_scan: { badge: true, footer: false, decorative: true, gradient: true, panel: true, outline: false },
  comment_reply: { badge: true, footer: false, decorative: true, gradient: false, panel: true, outline: false },
  search_prompt: { badge: false, footer: false, decorative: true, gradient: false, panel: true, outline: false },
  countdown_list: { badge: true, footer: false, decorative: true, gradient: false, panel: true, outline: false },
  pov_stamp: { badge: true, footer: false, decorative: true, gradient: false, panel: true, outline: false },
};

export function hookCapabilities(animation: string): HookCapabilities {
  return HOOK_CAPABILITIES[animation] || DEFAULT_HOOK_CAPABILITIES;
}

export const HOOK_PRESETS: { id: string; name: string; style: Partial<HookStyle> }[] = [
  { id: "news_viralin_badge_preset", name: "#VIRALIN Akurat Badge", style: { animation: "news_viralin_badge", color: "#09090B", boxColor: "#EAB308", lineColor: "#1D4ED8", fontSize: 46, fontFamily: "Montserrat", fontWeight: "900", uppercase: false, badgeEnabled: true, badgeText: "#VIRALIN", position: "center", positionY: 48, decorativeElements: true, motionIntensity: 1.0 } },
  { id: "news_portal_pantau_preset", name: "News Portal Speech Notch", style: { animation: "news_portal_pantau", color: "#09090B", boxColor: "#FFFFFF", lineColor: "#DC2626", fontSize: 44, fontFamily: "Inter", fontWeight: "900", uppercase: true, badgeEnabled: true, badgeText: "INTERNASIONAL", footerEnabled: true, footerText: "READ MORE AT chatgpt.com", position: "center", positionY: 50, decorativeElements: true, motionIntensity: 1.0 } },
  { id: "news_offset_box_preset", name: "Detik Red Breaking Box", style: { animation: "news_offset_box", color: "#FFFFFF", boxColor: "#DC2626", lineColor: "#FFFFFF", fontSize: 44, fontFamily: "Montserrat", fontWeight: "900", uppercase: false, position: "center", positionY: 50, decorativeElements: true, motionIntensity: 1.0 } },
  { id: "brutalist_bracket_preset", name: "Brutalist Bracket Frame", style: { animation: "brutalist_bracket", color: "#09090B", boxColor: "#FFFFFF", lineColor: "#000000", fontSize: 46, fontFamily: "Montserrat", fontWeight: "900", uppercase: false, position: "center", positionY: 50, decorativeElements: true, motionIntensity: 1.0 } },
  { id: "quote_strip_tape_preset", name: "Quote Tape Strips", style: { animation: "quote_strip_tape", color: "#09090B", boxColor: "#FFFFFF", lineColor: "#0D9488", fontSize: 42, fontFamily: "Montserrat", fontWeight: "900", uppercase: true, position: "center", positionY: 52, decorativeElements: true, motionIntensity: 1.0 } },
  { id: "podcast_lower_third_preset", name: "On-Air Lower", style: { animation: "podcast_lower_third", color: "#F8FAFC", bgColor: "#06111F", bgOpacity: 0.42, fontSize: 46, fontFamily: "Barlow Condensed", fontWeight: "900", uppercase: true, position: "bottom", positionY: 78, shadowEnabled: true, shadowBlur: 18, lineEnabled: false, lineColor: "#16F2B3", badgeEnabled: true, badgeText: "ON AIR", decorativeElements: true, motionIntensity: 1.0 } },
  { id: "quote_card_preset", name: "Quote Card", style: { animation: "quote_card", color: "#171717", bgColor: "#0B0F14", bgOpacity: 0.32, boxColor: "#F5EFE1", boxOpacity: 0.96, fontSize: 44, fontFamily: "Playfair Display", fontWeight: "800", lineHeight: 1.18, position: "center", positionY: 50, shadowEnabled: true, shadowBlur: 22, shadowY: 8, lineColor: "#FF4D2D", badgeEnabled: false, badgeText: "QUOTE", decorativeElements: true, motionIntensity: 0.7 } },
  { id: "waveform_pulse_preset", name: "Waveform Pulse", style: { animation: "waveform_pulse", color: "#EAFDF7", bgColor: "#020617", bgOpacity: 0.58, fontSize: 50, fontFamily: "Montserrat", fontWeight: "900", uppercase: true, glowEnabled: true, glowColor: "#14F1D9", glowSize: 28, gradientEnabled: true, gradientFrom: "#FFFFFF", gradientTo: "#14F1D9", lineColor: "#14F1D9", badgeEnabled: true, badgeText: "LIVE AUDIO", decorativeElements: true, motionIntensity: 1.2 } },
  { id: "breaking_tape_preset", name: "Breaking Tape", style: { animation: "breaking_tape", color: "#111111", bgColor: "#130A03", bgOpacity: 0.46, boxColor: "#FFDD2D", fontSize: 52, fontFamily: "Archivo Black", fontWeight: "900", uppercase: true, lineEnabled: false, lineColor: "#FF4D2D", badgeEnabled: true, badgeText: "HOT TAKE", decorativeElements: true, motionIntensity: 1.0 } },
  { id: "mic_drop_preset", name: "Mic Drop", style: { animation: "mic_drop", color: "#FFFFFF", bgColor: "#050507", bgOpacity: 0.52, fontSize: 58, fontFamily: "Anton", fontWeight: "900", uppercase: true, gradientEnabled: true, gradientFrom: "#FFFFFF", gradientTo: "#FF4D7D", glowEnabled: true, glowColor: "#FF4D7D", glowSize: 30, boxColor: "#FF4D7D", lineColor: "#FF4D7D", badgeEnabled: true, badgeText: "MIC DROP", decorativeElements: true, motionIntensity: 1.15 } },
  { id: "split_panel_preset", name: "Split Panel", style: { animation: "split_panel", color: "#F8FAFC", bgColor: "#07111F", bgOpacity: 0.46, boxColor: "#0F172A", boxOpacity: 0.86, fontSize: 50, fontFamily: "Inter", fontWeight: "900", lineColor: "#38BDF8", shadowEnabled: true, shadowBlur: 20, badgeEnabled: true, badgeText: "POINT", decorativeElements: true, motionIntensity: 0.95, position: "center", positionY: 54 } },
  { id: "kinetic_stack_preset", name: "Kinetic Stack", style: { animation: "kinetic_stack", color: "#111827", bgColor: "#140D06", bgOpacity: 0.34, boxColor: "#F97316", boxOpacity: 0.95, fontSize: 54, fontFamily: "Archivo Black", fontWeight: "900", uppercase: true, lineColor: "#111827", shadowEnabled: true, shadowBlur: 22, badgeEnabled: false, badgeText: "STACK", decorativeElements: true, motionIntensity: 1.2, position: "center", positionY: 52 } },
  { id: "glass_flash_preset", name: "Glass Flash", style: { animation: "glass_flash", color: "#F8FAFC", bgColor: "#050816", bgOpacity: 0.52, boxColor: "#FFFFFF", boxOpacity: 0.12, fontSize: 48, fontFamily: "Montserrat", fontWeight: "800", lineColor: "#C084FC", glowEnabled: true, glowColor: "#C084FC", glowSize: 24, badgeEnabled: true, badgeText: "FOCUS", decorativeElements: true, motionIntensity: 0.8 } },
  { id: "marker_swipe_preset", name: "Marker Swipe", style: { animation: "marker_swipe", color: "#F8FAFC", bgColor: "#080A0F", bgOpacity: 0.48, boxColor: "#FDE047", boxOpacity: 0.86, fontSize: 52, fontFamily: "Bebas Neue", fontWeight: "900", uppercase: true, lineColor: "#FDE047", shadowEnabled: true, shadowBlur: 18, badgeEnabled: false, badgeText: "MARKED", decorativeElements: true, motionIntensity: 1.0 } },
  { id: "signal_scan_preset", name: "Signal Scan", style: { animation: "signal_scan", color: "#E0F2FE", bgColor: "#020617", bgOpacity: 0.62, boxColor: "#0EA5E9", boxOpacity: 0.16, fontSize: 46, fontFamily: "Titillium Web", fontWeight: "900", uppercase: true, lineColor: "#22D3EE", glowEnabled: true, glowColor: "#22D3EE", glowSize: 20, badgeEnabled: true, badgeText: "SIGNAL", decorativeElements: true, motionIntensity: 1.05 } },
  { id: "comment_reply_preset", name: "Reply to Comment", style: { animation: "comment_reply", color: "#18181B", bgColor: "#000000", bgOpacity: 0.18, boxColor: "#FFFFFF", boxOpacity: 0.98, fontSize: 42, fontFamily: "Inter", fontWeight: "800", lineHeight: 1.14, uppercase: false, position: "top", positionY: 24, lineColor: "#18181B", badgeEnabled: true, badgeText: "replying to @viewer", decorativeElements: true, motionIntensity: 0.8 } },
  { id: "search_prompt_preset", name: "Search Prompt", style: { animation: "search_prompt", color: "#F8FAFC", bgColor: "#020617", bgOpacity: 0.34, boxColor: "#0F172A", boxOpacity: 0.94, fontSize: 43, fontFamily: "Inter", fontWeight: "800", lineHeight: 1.12, position: "top", positionY: 20, lineColor: "#22D3EE", badgeEnabled: false, badgeText: "", decorativeElements: true, motionIntensity: 0.85 } },
  { id: "countdown_list_preset", name: "Countdown List", style: { animation: "countdown_list", color: "#111827", bgColor: "#050505", bgOpacity: 0.38, boxColor: "#FACC15", boxOpacity: 0.98, fontSize: 48, fontFamily: "Archivo Black", fontWeight: "900", uppercase: true, position: "center", positionY: 50, lineColor: "#111827", badgeEnabled: true, badgeText: "03", decorativeElements: true, motionIntensity: 1.0 } },
  { id: "pov_stamp_preset", name: "POV Stamp", style: { animation: "pov_stamp", color: "#FFFFFF", bgColor: "#12070C", bgOpacity: 0.38, boxColor: "#FB7185", boxOpacity: 0.96, fontSize: 50, fontFamily: "Montserrat", fontWeight: "900", uppercase: false, italic: true, position: "center", positionY: 48, lineColor: "#FFFFFF", badgeEnabled: true, badgeText: "POV", decorativeElements: true, motionIntensity: 0.9 } },
];

export const SUBTITLE_PRESETS: { id: string; name: string; style: Partial<SubtitleStyle> }[] = [
  {
    id: "clean",
    name: "Clean",
    style: {
      stylePreset: "minimal_clean",
      color: "#F8FAFC",
      highlightColor: "#38BDF8",
      fontFamily: "Inter",
      fontWeight: "700",
      fontSize: 32,
      bgEnabled: true,
      bgColor: "#0F172A",
      bgOpacity: 0.75,
      bgRadius: 12,
      bgPadding: 16,
      strokeEnabled: false,
      animationStyle: "fade",
      lineTransition: "karaoke",
      maxWordsPerLine: 4,
      wordSpacing: 6,
    },
  },
  {
    id: "bold",
    name: "Bold",
    style: {
      stylePreset: "meme_impact",
      color: "#FFFFFF",
      highlightColor: "#FF3D3D",
      fontFamily: "Archivo Black",
      fontWeight: "900",
      fontSize: 44,
      uppercase: true,
      bgEnabled: false,
      strokeEnabled: true,
      strokeColor: "#000000",
      strokeWidth: 4,
      shadowEnabled: true,
      shadowColor: "#000000",
      shadowBlur: 14,
      animationStyle: "pop",
      lineTransition: "word_pop",
      highlightScale: 1.25,
      maxWordsPerLine: 3,
    },
  },
  {
    id: "minimal",
    name: "Minimal",
    style: {
      stylePreset: "minimal_clean",
      color: "#FFFFFF",
      highlightColor: "#FACC15",
      fontFamily: "Poppins",
      fontWeight: "600",
      fontSize: 32,
      bgEnabled: false,
      strokeEnabled: true,
      strokeColor: "#000000",
      strokeWidth: 2,
      shadowEnabled: false,
      animationStyle: "fade",
      lineTransition: "karaoke",
      maxWordsPerLine: 4,
      wordSpacing: 6,
    },
  },
  {
    id: "podcast",
    name: "Podcast",
    style: {
      stylePreset: "lower_third",
      color: "#E2E8F0",
      highlightColor: "#10B981",
      fontFamily: "Plus Jakarta Sans",
      fontWeight: "700",
      fontSize: 32,
      bgEnabled: true,
      bgColor: "#18181B",
      bgOpacity: 0.9,
      bgRadius: 999,
      bgPadding: 18,
      strokeEnabled: false,
      shadowEnabled: true,
      shadowBlur: 12,
      animationStyle: "pop",
      lineTransition: "karaoke",
      maxWordsPerLine: 4,
      wordSpacing: 6,
    },
  },
  {
    id: "highlight",
    name: "Highlight",
    style: {
      stylePreset: "spotlight_keyword",
      color: "#F8FAFC",
      highlightColor: "#FACC15",
      fontFamily: "Montserrat",
      fontWeight: "900",
      fontSize: 36,
      bgEnabled: false,
      strokeEnabled: true,
      strokeColor: "#000000",
      strokeWidth: 3,
      highlightScale: 1.3,
      highlightBold: true,
      animationStyle: "pop",
      lineTransition: "emphasis",
      maxWordsPerLine: 3,
    },
  },
  {
    id: "karaoke",
    name: "Karaoke",
    style: {
      stylePreset: "classic",
      color: "#FFFFFF",
      highlightColor: "#22D3EE",
      fontFamily: "Inter",
      fontWeight: "800",
      fontSize: 34,
      bgEnabled: true,
      bgColor: "#000000",
      bgOpacity: 0.5,
      bgRadius: 8,
      bgPadding: 14,
      strokeEnabled: true,
      strokeColor: "#000000",
      strokeWidth: 2,
      animationStyle: "pop",
      lineTransition: "karaoke",
      maxWordsPerLine: 3,
    },
  },
  {
    id: "pop",
    name: "Pop (Hormozi)",
    style: {
      stylePreset: "meme_impact",
      color: "#FFFFFF",
      highlightColor: "#00FF66",
      fontFamily: "Anton",
      fontWeight: "900",
      fontSize: 50,
      uppercase: true,
      bgEnabled: false,
      strokeEnabled: true,
      strokeColor: "#000000",
      strokeWidth: 5,
      shadowEnabled: true,
      shadowBlur: 16,
      animationStyle: "pop",
      lineTransition: "word_pop",
      highlightScale: 1.25,
      maxWordsPerLine: 1,
    },
  },
  {
    id: "gaming",
    name: "Gaming (Cyber)",
    style: {
      stylePreset: "neon_pulse",
      color: "#ECFEFF",
      highlightColor: "#FF007F",
      fontFamily: "Montserrat",
      fontWeight: "900",
      fontSize: 38,
      uppercase: true,
      glowEnabled: true,
      glowColor: "#00F0FF",
      highlightGlow: true,
      highlightGlowColor: "#FF007F",
      bgEnabled: true,
      bgColor: "#020617",
      bgOpacity: 0.8,
      bgRadius: 10,
      strokeEnabled: true,
      strokeColor: "#000000",
      strokeWidth: 3,
      animationStyle: "pop",
      lineTransition: "karaoke",
      maxWordsPerLine: 3,
    },
  },
  {
    id: "cinematic",
    name: "Cinematic (Gold)",
    style: {
      stylePreset: "quote_box",
      color: "#F8FAFC",
      highlightColor: "#FCD34D",
      fontFamily: "Playfair Display",
      fontWeight: "800",
      fontSize: 34,
      italic: false,
      bgEnabled: true,
      bgColor: "#0B0F14",
      bgOpacity: 0.75,
      bgRadius: 6,
      bgPadding: 16,
      strokeEnabled: true,
      strokeColor: "#000000",
      strokeWidth: 2,
      shadowEnabled: true,
      shadowColor: "#000000",
      shadowBlur: 16,
      animationStyle: "fade",
      lineTransition: "karaoke",
      maxWordsPerLine: 4,
    },
  },
  {
    id: "custom",
    name: "Custom Playground",
    style: {
      stylePreset: "classic",
      color: "#FFFFFF",
      highlightColor: "#FACC15",
      fontFamily: "Inter",
      fontWeight: "700",
      fontSize: 34,
      bgEnabled: true,
      bgColor: "#000000",
      bgOpacity: 0.5,
      bgRadius: 10,
      bgPadding: 14,
      strokeEnabled: true,
      strokeColor: "#000000",
      strokeWidth: 2,
      animationStyle: "pop",
      lineTransition: "word_pop",
      maxWordsPerLine: 3,
    },
  },
  {
    id: "meme_impact",
    name: "Meme Impact",
    style: {
      stylePreset: "meme_impact",
      color: "#FFFFFF",
      highlightColor: "#FF3D3D",
      fontFamily: "Anton",
      fontSize: 48,
      fontWeight: "900",
      uppercase: true,
      dualStyleEnabled: true,
      highlightFontFamily: "Archivo Black",
      highlightFontSize: 58,
      highlightFontWeight: "900",
      highlightUppercase: true,
      bgEnabled: false,
      strokeEnabled: true,
      strokeWidth: 5,
      shadowEnabled: true,
      shadowBlur: 18,
      maxWordsPerLine: 2,
      animationStyle: "pop",
      lineTransition: "word_pop",
    },
  },
  {
    id: "spotlight_keyword",
    name: "Keyword Spotlight",
    style: {
      stylePreset: "spotlight_keyword",
      color: "#F8FAFC",
      highlightColor: "#F97316",
      fontFamily: "Poppins",
      fontSize: 32,
      fontWeight: "700",
      dualStyleEnabled: true,
      highlightFontFamily: "Anton",
      highlightFontSize: 72,
      highlightFontWeight: "900",
      highlightLetterSpacing: 1,
      highlightUppercase: true,
      highlightGlow: true,
      highlightGlowColor: "#F97316",
      bgEnabled: false,
      strokeEnabled: false,
      position: "center",
      positionY: 54,
      animationStyle: "pop",
      lineTransition: "emphasis",
      maxWordsPerLine: 4,
    },
  },
  {
    id: "editorial_banner",
    name: "Editorial Banner",
    style: {
      stylePreset: "editorial_banner",
      color: "#E5E7EB",
      highlightColor: "#A78BFA",
      fontFamily: "Inter",
      fontSize: 32,
      fontWeight: "800",
      bgColor: "#111827",
      bgOpacity: 0.78,
      bgRadius: 6,
      bgPadding: 16,
      strokeEnabled: false,
      shadowEnabled: true,
      shadowBlur: 14,
      animationStyle: "slide",
      lineTransition: "line_reveal",
      maxWordsPerLine: 5,
      wordSpacing: 8,
    },
  },
  {
    id: "lower_third",
    name: "On-Air Lower",
    style: {
      stylePreset: "lower_third",
      color: "#F8FAFC",
      highlightColor: "#16F2B3",
      fontFamily: "Barlow Condensed",
      fontSize: 40,
      fontWeight: "900",
      uppercase: true,
      bgColor: "#06111F",
      bgOpacity: 0.82,
      bgRadius: 6,
      bgPadding: 16,
      strokeEnabled: false,
      shadowEnabled: true,
      shadowBlur: 18,
      position: "bottom",
      positionY: 78,
      animationStyle: "slide",
      lineTransition: "line_reveal",
      maxWordsPerLine: 5,
    },
  },
  {
    id: "bubble_chat",
    name: "Bubble Chat",
    style: {
      stylePreset: "bubble_chat",
      color: "#111827",
      highlightColor: "#DB2777",
      fontFamily: "Nunito",
      fontSize: 34,
      fontWeight: "900",
      bgColor: "#F8FAFC",
      bgOpacity: 0.94,
      bgRadius: 22,
      bgPadding: 16,
      strokeEnabled: false,
      shadowEnabled: true,
      shadowColor: "#000000",
      shadowBlur: 18,
      highlightStyle: "background",
      animationStyle: "pop",
      lineTransition: "word_pop",
    },
  },
  {
    id: "breaking_tape",
    name: "Breaking Tape",
    style: {
      stylePreset: "breaking_tape",
      color: "#111111",
      highlightColor: "#FF2D2D",
      fontFamily: "Archivo Black",
      fontSize: 40,
      fontWeight: "900",
      uppercase: true,
      bgColor: "#FFDD2D",
      bgOpacity: 0.96,
      bgRadius: 2,
      bgPadding: 14,
      strokeEnabled: false,
      shadowEnabled: true,
      shadowBlur: 20,
      maxWordsPerLine: 4,
      animationStyle: "slide",
      lineTransition: "word_pop",
    },
  },
  {
    id: "quote_box",
    name: "Quote Box",
    style: {
      stylePreset: "quote_box",
      color: "#1F2937",
      highlightColor: "#E11D48",
      fontFamily: "Playfair Display",
      fontSize: 35,
      fontWeight: "800",
      lineHeight: 1.22,
      bgColor: "#F4F4F5",
      bgOpacity: 0.92,
      bgRadius: 4,
      bgPadding: 18,
      strokeEnabled: false,
      shadowEnabled: true,
      shadowBlur: 20,
      animationStyle: "fade",
      lineTransition: "line_reveal",
      maxWordsPerLine: 5,
    },
  },
  {
    id: "minimal_clean",
    name: "Minimal Clean",
    style: {
      stylePreset: "minimal_clean",
      color: "#F4F4F5",
      highlightColor: "#FFFFFF",
      fontFamily: "Inter",
      fontSize: 30,
      fontWeight: "700",
      bgEnabled: false,
      strokeEnabled: false,
      shadowEnabled: true,
      shadowBlur: 10,
      animationStyle: "fade",
      lineTransition: "word_pop",
      maxWordsPerLine: 5,
    },
  },
  {
    id: "documentary",
    name: "Documentary",
    style: {
      stylePreset: "documentary",
      color: "#E5E7EB",
      highlightColor: "#FBBF24",
      fontFamily: "Montserrat",
      fontSize: 31,
      fontWeight: "700",
      letterSpacing: 1,
      bgColor: "#0F172A",
      bgOpacity: 0.64,
      bgRadius: 4,
      bgPadding: 13,
      strokeEnabled: false,
      shadowEnabled: true,
      shadowBlur: 16,
      animationStyle: "fade",
      lineTransition: "line_reveal",
      maxWordsPerLine: 6,
    },
  },
  {
    id: "caption_strip",
    name: "Full-Width Strip",
    style: {
      stylePreset: "caption_strip",
      color: "#FFFFFF",
      highlightColor: "#FACC15",
      fontFamily: "Inter",
      fontSize: 34,
      fontWeight: "900",
      bgColor: "#09090B",
      bgOpacity: 0.9,
      bgRadius: 0,
      bgPadding: 18,
      strokeEnabled: false,
      position: "bottom",
      positionY: 82,
      uppercase: true,
      animationStyle: "slide",
      lineTransition: "word_pop",
      maxWordsPerLine: 5,
    },
  },
  {
    id: "word_tiles",
    name: "Word Tiles",
    style: {
      stylePreset: "word_tiles",
      color: "#18181B",
      highlightColor: "#FFFFFF",
      fontFamily: "Montserrat",
      fontSize: 31,
      fontWeight: "900",
      bgEnabled: false,
      strokeEnabled: false,
      shadowEnabled: true,
      shadowBlur: 16,
      highlightStyle: "background",
      animationStyle: "pop",
      lineTransition: "word_pop",
      maxWordsPerLine: 4,
      wordSpacing: 8,
    },
  },
  {
    id: "gradient_glass",
    name: "Gradient Glass",
    style: {
      stylePreset: "gradient_glass",
      color: "#F8FAFC",
      highlightColor: "#C4B5FD",
      fontFamily: "Poppins",
      fontSize: 33,
      fontWeight: "800",
      bgColor: "#312E81",
      bgOpacity: 0.58,
      bgRadius: 24,
      bgPadding: 18,
      highlightGlow: true,
      highlightGlowColor: "#A78BFA",
      strokeEnabled: false,
      shadowEnabled: true,
      shadowBlur: 18,
      animationStyle: "fade",
      lineTransition: "word_pop",
      maxWordsPerLine: 4,
    },
  },
  {
    id: "comic_burst",
    name: "Comic Burst",
    style: {
      stylePreset: "comic_burst",
      color: "#FFFFFF",
      highlightColor: "#FDE047",
      fontFamily: "Bungee",
      fontSize: 40,
      fontWeight: "900",
      uppercase: true,
      bgEnabled: false,
      strokeEnabled: true,
      strokeColor: "#111827",
      strokeWidth: 5,
      shadowEnabled: true,
      shadowBlur: 18,
      animationStyle: "pop",
      lineTransition: "word_pop",
      maxWordsPerLine: 3,
      wordSpacing: 7,
    },
  },
  {
    id: "terminal_type",
    name: "Terminal Type",
    style: {
      stylePreset: "terminal_type",
      color: "#BBF7D0",
      highlightColor: "#4ADE80",
      fontFamily: "monospace",
      fontSize: 30,
      fontWeight: "700",
      letterSpacing: 1,
      bgColor: "#052E16",
      bgOpacity: 0.88,
      bgRadius: 4,
      bgPadding: 16,
      strokeEnabled: false,
      shadowEnabled: true,
      shadowColor: "#16A34A",
      shadowBlur: 10,
      animationStyle: "slide",
      lineTransition: "line_reveal",
      maxWordsPerLine: 5,
    },
  },
];
