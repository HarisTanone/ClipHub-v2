import { useState, useEffect } from "react";
import { X, Type, Sparkles, Bookmark, Trash2, Save, Download, ChevronLeft, ChevronRight, MoveRight, Layers, Zap, Clapperboard, Upload, Image as ImageIcon, Palette, Check, EyeOff, Scissors, Maximize2, Loader2, Quote, Megaphone, Bell, Share2, ThumbsUp, Link2, MessageSquare, ArrowUpRight, UserPlus, Plus, Clock, Info, Heart, Star, RotateCcw, Copy } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { FeatureLock } from "@/components/ui/FeatureLock";
import { confirmDialog } from "@/components/ui/ConfirmDialog";
import { jobs, presets as presetsApi, subtitleStyles, type Preset } from "@/lib/api";
import { cn } from "@/lib/utils";
import { RangeSlider } from "@/components/ui/RangeSlider";
import { buildCanvasConfig, gradientCss, type CanvasConfig } from "@/lib/canvasTemplates";
import { CanvasAccents } from "@/components/BackgroundTemplateSection";
import type { BackgroundMode } from "@/components/BackgroundTemplateSection";
import { HfFixedStylePreview } from "@/components/HfFixedStylePreview";
import {
  ENGINE_NOTES,
  HF_HOOK_STYLES,
  HF_SUBTITLE_STYLES,
  type RenderEngine,
  resolveEngine,
  defaultHfHookId,
  defaultHfSubtitleId,
  type HfStylePreset,
  FFMPEG_HOOK_PRESETS,
  FFMPEG_SUBTITLE_PRESETS,
  SKIA_HOOK_PRESETS,
  SKIA_SUBTITLE_PRESETS,
} from "@/lib/renderEngines";

type OptionMeta = {
  label: string;
  mood: string;
  accent: string;
  preview: string;
  desc: string;
};

const PAGINATION_PAGE_SIZE = 6;

type SubtitleVisualPreset = string;

export function useGoogleFont(fontFamily: string) {
  useEffect(() => {
    if (!fontFamily || fontFamily === "monospace") return;
    const id = `gfont-${fontFamily.replace(/\s/g, "")}`;
    if (document.getElementById(id)) return;
    const link = document.createElement("link");
    link.id = id;
    link.rel = "stylesheet";
    link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(fontFamily)}:wght@400;500;600;700;800;900&display=swap`;
    document.head.appendChild(link);
  }, [fontFamily]);
}

// ─── Types ───────────────────────────────────────────────────────────────────

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

/** Map old AI-text effect/anim names so localStorage + presets keep working. */
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



// ─── Presets ─────────────────────────────────────────────────────────────────

const FONT_OPTIONS = [
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

const HOOK_FONT_SUGGESTIONS = ["Barlow Condensed", "Anton", "Archivo Black", "Playfair Display", "Bungee", "Montserrat"];
const SUBTITLE_FONT_SUGGESTIONS = ["Montserrat", "Poppins", "Inter", "Anton", "Bebas Neue", "Archivo Black", "Barlow Condensed", "Roboto Condensed", "Noto Sans"];
const HIGHLIGHT_FONT_SUGGESTIONS = ["Anton", "Archivo Black", "Bebas Neue", "Bungee", "Barlow Condensed", "Black Ops One"];

const HOOK_ANIMATIONS = [
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

const HOOK_ANIMATION_META: Record<string, OptionMeta> = {
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

const SUBTITLE_ANIMATION_META: Record<SubtitleStyle["animationStyle"], OptionMeta> = {
  pop: { label: "Pop", mood: "Punchy", accent: "#34D399", preview: "POP", desc: "Kata aktif membesar cepat dan jelas." },
  fade: { label: "Fade", mood: "Soft", accent: "#93C5FD", preview: "FADE", desc: "Masuk halus untuk podcast yang tenang." },
  slide: { label: "Slide", mood: "Clean motion", accent: "#FBBF24", preview: "SLIDE", desc: "Naik singkat, enak untuk dialog cepat." },
  none: { label: "None", mood: "Static", accent: "#A1A1AA", preview: "TEXT", desc: "Tanpa animasi tambahan." },
};

const SUBTITLE_TRANSITION_META: Record<SubtitleStyle["lineTransition"], OptionMeta> = {
  word_pop: { label: "Word Pop", mood: "Readable", accent: "#34D399", preview: "word", desc: "Mode standar, highlight mengikuti kata aktif." },
  emphasis: { label: "Big Keyword", mood: "Keyword hero", accent: "#FACC15", preview: "BIG", desc: "Kata terkuat dibuat besar seperti punchline." },
  line_reveal: { label: "Line Reveal", mood: "Editorial", accent: "#A78BFA", preview: "LINE", desc: "Baris muncul rapi seperti caption editorial." },
  karaoke: { label: "Karaoke", mood: "Smooth", accent: "#38BDF8", preview: "KARAOKE", desc: "Kata demi kata tersorot berurutan." },
  typing: { label: "Typewriter", mood: "Dynamic typing", accent: "#10B981", preview: "TYPE...", desc: "Teks mengetik muncul kata demi kata dengan kursor aktif." },
};

const HIGHLIGHT_STYLE_META: Record<SubtitleStyle["highlightStyle"], OptionMeta> = {
  scale: { label: "Scale", mood: "Bigger word", accent: "#FACC15", preview: "Aa", desc: "Kata penting membesar." },
  underline: { label: "Underline", mood: "Marked", accent: "#38BDF8", preview: "__", desc: "Garis bawah untuk penekanan rapi." },
  background: { label: "Background", mood: "Tag", accent: "#34D399", preview: "BOX", desc: "Highlight seperti label kecil." },
  strikethrough: { label: "Strike", mood: "Contrarian", accent: "#FB7185", preview: "DEL", desc: "Cocok untuk kontra atau koreksi." },
};

type HookCapabilities = {
  badge: boolean;
  footer: boolean;
  decorative: boolean;
  gradient: boolean;
  panel: boolean;
  outline: boolean;
};

const DEFAULT_HOOK_CAPABILITIES: HookCapabilities = {
  badge: true,
  footer: true,
  decorative: true,
  gradient: true,
  panel: false,
  outline: true,
};

const HOOK_CAPABILITIES: Record<string, HookCapabilities> = {
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

function hookCapabilities(animation: string): HookCapabilities {
  return HOOK_CAPABILITIES[animation] || DEFAULT_HOOK_CAPABILITIES;
}

const HOOK_PRESETS: { id: string; name: string; style: Partial<HookStyle> }[] = [
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

const SUBTITLE_PRESETS: { id: string; name: string; style: Partial<SubtitleStyle> }[] = [
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


// ─── Modal ───────────────────────────────────────────────────────────────────

interface StyleEditorModalProps {
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

export function StyleEditorModal({
  open,
  onClose,
  hookStyle,
  subtitleStyle,
  textEmphasisStyle = DEFAULT_TEXT_EMPHASIS_STYLE,
  onHookChange,
  onSubtitleChange,
  onTextEmphasisChange = () => { },
  watermarkStyle = DEFAULT_WATERMARK_STYLE,
  onWatermarkChange = () => { },
  ctaStyle = DEFAULT_CTA_STYLE,
  onCtaChange = () => { },
  brollStyle,
  onBrollChange,
  onPresetLoad,
  aspectRatio = "9:16",
  inline,
  activeTab,
  thumbnailUrl,
  isSuperadmin,
  isPremium,
  userFeatures,
  activePresetId: externalActivePresetId,
  onPresetSelect,
  onProcess,
  processing = false,
  processProgress,
  aiTextPreviewContext,
  aiTextEnabled = true,
  canvasBackground = null
}: StyleEditorModalProps) {
  const [tab, setTab] = useState<"presets" | "hook" | "subtitle" | "transition" | "ai_text" | "other">(activeTab || "hook");

  useEffect(() => { if (activeTab) setTab(activeTab); }, [activeTab]);

  if (!open) return null;

  const animationStyles = `
    @keyframes fadeScalePreview { 0%,100% { opacity:0.3; transform:translateY(-50%) scale(0.92); } 50% { opacity:1; transform:translateY(-50%) scale(1); } }
    @keyframes slideUpPreview { 0%,100% { opacity:0; transform:translateY(-40%); } 20%,80% { opacity:1; transform:translateY(-50%); } }
    @keyframes slidePunchPreview { 0% { opacity:0; transform:translateY(-50%) translateX(-50px); } 20% { opacity:1; transform:translateY(-50%) translateX(3px) scale(1.02); } 30%,80% { opacity:1; transform:translateY(-50%) translateX(0) scale(1); } 100% { opacity:0; transform:translateY(-50%); } }
    @keyframes glitchJitter { 0% { transform:translateY(-50%) translate(-2px,0); } 25% { transform:translateY(-50%) translate(2px,1px); } 50% { transform:translateY(-50%) translate(-1px,-1px); } 75% { transform:translateY(-50%) translate(1px,0); } 100% { transform:translateY(-50%); } }
    @keyframes typewriterReveal { 0% { width:0; } 50%,100% { width:100%; } }
    @keyframes glitchRedLayer {
      0%,100% { transform:translate(-4px,0); }
      25% { transform:translate(-1px,0); }
      50% { transform:translate(-7px,0); }
      75% { transform:translate(-2px,1px); }
    }
    @keyframes glitchCyanLayer {
      0%,100% { transform:translate(4px,0); }
      25% { transform:translate(1px,0); }
      50% { transform:translate(7px,0); }
      75% { transform:translate(2px,-1px); }
    }
    @keyframes shakeNeonGlow {
      0%,100% { transform:translate(0,0); }
      20% { transform:translate(2px,-1px); }
      40% { transform:translate(-1px,2px); }
      60% { transform:translate(1px,1px); }
      80% { transform:translate(-2px,-1px); }
    }
    @keyframes shakeNeonMain {
      0%,100% { transform:translate(0,0); }
      15% { transform:translate(1.5px,-1px); }
      30% { transform:translate(-1px,1px); }
      45% { transform:translate(1px,0.5px); }
      60% { transform:translate(-1.5px,-0.5px); }
      75% { transform:translate(0.5px,1px); }
      90% { transform:translate(-0.5px,-1px); }
    }
    @keyframes cinematicRevealText {
      0% { opacity:0; transform:translateY(-50%) scale(0.96); }
      25% { opacity:1; transform:translateY(-50%) scale(1); }
      75% { opacity:1; transform:translateY(-50%) scale(1); }
      100% { opacity:0; transform:translateY(-50%) scale(0.96); }
    }
    @keyframes dangerPulse {
      0%,100% { transform:translateY(-50%) scale(1); }
      25% { transform:translateY(-50%) scale(1.03); }
      50% { transform:translateY(-50%) scale(1); }
      75% { transform:translateY(-50%) scale(1.02); }
    }
    @keyframes boldSlamPreview {
      0% { transform:translateY(-50%) scale(0) rotate(-8deg); }
      20% { transform:translateY(-50%) scale(1.05) rotate(0deg); }
      30% { transform:translateY(-50%) scale(1) rotate(0deg); }
      50%,60% { transform:translateY(-50%) translate(2px,-1px) scale(1); }
      55% { transform:translateY(-50%) translate(-2px,1px) scale(1); }
      70% { transform:translateY(-50%) scale(1) rotate(0deg); }
      100% { transform:translateY(-50%) scale(1) rotate(0deg); }
    }
    @keyframes podcastLowerPreview {
      0% { opacity:0; transform:translateY(22px) scale(0.98); }
      18%,82% { opacity:1; transform:translateY(0) scale(1); }
      100% { opacity:0; transform:translateY(10px) scale(0.99); }
    }
    @keyframes podcastOnAirPulse {
      0%,100% { opacity:0.35; transform:scale(0.85); }
      50% { opacity:1; transform:scale(1.12); }
    }
    @keyframes quoteCardPreview {
      0% { opacity:0; transform:translateY(-50%) rotate(-2deg) scale(0.88); }
      20%,82% { opacity:1; transform:translateY(-50%) rotate(-1deg) scale(1); }
      100% { opacity:0; transform:translateY(-50%) rotate(1deg) scale(0.95); }
    }
    @keyframes waveformTextPreview {
      0%,100% { transform:translateY(-50%) scale(0.98); }
      50% { transform:translateY(-50%) scale(1.03); }
    }
    @keyframes waveformBarPreview {
      0%,100% { transform:scaleY(0.34); opacity:0.45; }
      50% { transform:scaleY(1); opacity:1; }
    }
    @keyframes breakingTapePreview {
      0% { opacity:0; transform:translateY(-50%) translateX(-70px) rotate(-4deg); }
      18%,82% { opacity:1; transform:translateY(-50%) translateX(0) rotate(-4deg); }
      100% { opacity:0; transform:translateY(-50%) translateX(55px) rotate(-4deg); }
    }
    @keyframes micDropPreview {
      0% { opacity:0; transform:translateY(-95%) scale(1.18) rotate(-8deg); }
      18% { opacity:1; transform:translateY(-50%) scale(0.94) rotate(2deg); }
      28%,78% { opacity:1; transform:translateY(-50%) scale(1) rotate(0deg); }
      100% { opacity:0; transform:translateY(-42%) scale(0.96); }
    }
    @keyframes splitPanelPreview {
      0% { opacity:0; transform:translateY(-50%) translateX(-32px); }
      18% { opacity:1; transform:translateY(-50%) translateX(0); }
      50% { opacity:1; transform:translateY(calc(-50% - 3px)) translateX(0); }
      82% { opacity:1; transform:translateY(-50%) translateX(0); }
      100% { opacity:0; transform:translateY(-50%) translateX(24px); }
    }
    @keyframes kineticStackPreview {
      0% { opacity:0; transform:translateY(-50%) scale(0.92) rotate(-2deg); }
      18%,78% { opacity:1; transform:translateY(-50%) scale(1) rotate(-1deg); }
      45% { opacity:1; transform:translateY(calc(-50% - 4px)) scale(1.02) rotate(1deg); }
      100% { opacity:0; transform:translateY(-42%) scale(0.96) rotate(2deg); }
    }
    @keyframes glassFlashPreview {
      0% { opacity:0; transform:translateY(-50%) scale(0.96); }
      20%,84% { opacity:1; transform:translateY(-50%) scale(1); }
      52% { opacity:1; transform:translateY(calc(-50% - 3px)) scale(1.01); }
      100% { opacity:0; transform:translateY(-50%) scale(0.97); }
    }
    @keyframes markerSwipePreview {
      0% { transform:scaleX(0); opacity:0; }
      18%,78% { transform:scaleX(1); opacity:1; }
      100% { transform:scaleX(0.15); opacity:0; }
    }
    @keyframes signalScanPreview {
      0% { opacity:0; transform:translateY(-50%) scale(0.98); }
      20%,82% { opacity:1; transform:translateY(-50%) scale(1); }
      50% { opacity:1; transform:translateY(calc(-50% - 2px)) scale(1.01); }
      100% { opacity:0; transform:translateY(-50%) scale(0.98); }
    }
    @keyframes signalScanLine {
      0% { transform:translateX(-120%); opacity:0; }
      18%,76% { opacity:1; }
      100% { transform:translateX(120%); opacity:0; }
    }
    @keyframes popIn { 0%,100% { transform:scale(0.9); opacity:0.5; } 50% { transform:scale(1.05); opacity:1; } }
    @keyframes fadeIn { 0%,100% { opacity:0.3; } 50% { opacity:1; } }
    @keyframes slideInUp { 0%,100% { transform:translateY(4px); opacity:0.4; } 50% { transform:translateY(0); opacity:1; } }
  `;

  // Inline mode: just render the content without overlay
  if (inline) {
    return (
      <div className="flex h-full min-h-0 flex-col overflow-hidden">
        <style>{animationStyles}</style>
        <div className="min-h-0 flex-1 overflow-hidden">
          {tab === "presets" ? (
            <PresetsTab
              hookStyle={hookStyle}
              subtitleStyle={subtitleStyle}
              textEmphasisStyle={textEmphasisStyle}
              watermarkStyle={watermarkStyle}
              ctaStyle={ctaStyle}
              brollStyle={brollStyle}
              onHookChange={onHookChange}
              onSubtitleChange={onSubtitleChange}
              onTextEmphasisChange={onTextEmphasisChange}
              onWatermarkChange={onWatermarkChange}
              onCtaChange={onCtaChange}
              onBrollChange={onBrollChange}
              onPresetLoad={onPresetLoad}
              externalActiveId={externalActivePresetId}
              onPresetSelect={onPresetSelect}
            />
          ) : tab === "hook" ? (
            <HookEditor
              style={hookStyle}
              onChange={onHookChange}
              aspectRatio={aspectRatio}
              thumbnailUrl={thumbnailUrl}
              canvasBackground={canvasBackground}
              isSuperadmin={isSuperadmin}
            />
          ) : tab === "other" ? (
            <OtherTab
              hookStyle={hookStyle}
              textEmphasisStyle={textEmphasisStyle}
              onHookChange={onHookChange}
              onTextEmphasisChange={onTextEmphasisChange}
              watermarkStyle={watermarkStyle}
              onWatermarkChange={onWatermarkChange}
              ctaStyle={ctaStyle}
              onCtaChange={onCtaChange}
              thumbnailUrl={thumbnailUrl}
              aiTextPreviewContext={aiTextPreviewContext}
              aiTextEnabled={aiTextEnabled}
              aspectRatio={aspectRatio}
              canvasBackground={canvasBackground}
            />
          ) : (
            <SubtitleEditor
              style={subtitleStyle}
              onChange={onSubtitleChange}
              aspectRatio={aspectRatio}
              thumbnailUrl={thumbnailUrl}
              isSuperadmin={isSuperadmin}
              isPremium={isPremium}
              userFeatures={userFeatures}
              canvasBackground={canvasBackground}
            />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <style>{animationStyles}</style>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-[95vw] max-w-[1100px] h-[92vh] sm:h-[88vh] bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl flex flex-col overflow-hidden">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between px-3.5 py-2.5 sm:px-5 sm:py-3 border-b border-zinc-800 shrink-0 gap-2">
          <div className="flex items-center gap-2 sm:gap-4 overflow-x-auto no-scrollbar">
            <h2 className="text-xs sm:text-sm font-semibold text-zinc-100 whitespace-nowrap">Custom Style Editor</h2>
            <div className="flex bg-zinc-800 rounded-lg p-0.5 shrink-0">
              <button type="button" onClick={() => setTab("presets")} className={cn("px-2.5 sm:px-3 py-1 sm:py-1.5 text-xs font-medium rounded-md transition-colors", tab === "presets" ? "bg-emerald-600 text-white" : "text-zinc-400 hover:text-zinc-200")}>
                <Bookmark className="h-3 w-3 inline mr-1" />Presets
              </button>
              <button type="button" onClick={() => setTab("hook")} className={cn("px-2.5 sm:px-3 py-1 sm:py-1.5 text-xs font-medium rounded-md transition-colors", tab === "hook" ? "bg-emerald-600 text-white" : "text-zinc-400 hover:text-zinc-200")}>
                <Type className="h-3 w-3 inline mr-1" />Hook
              </button>
              <button type="button" onClick={() => setTab("subtitle")} className={cn("px-2.5 sm:px-3 py-1 sm:py-1.5 text-xs font-medium rounded-md transition-colors", tab === "subtitle" ? "bg-emerald-600 text-white" : "text-zinc-400 hover:text-zinc-200")}>
                <Sparkles className="h-3 w-3 inline mr-1" />Subtitle
              </button>
              <button type="button" onClick={() => setTab("other")} className={cn("px-2.5 sm:px-3 py-1 sm:py-1.5 text-xs font-medium rounded-md transition-colors", tab === "other" ? "bg-emerald-600 text-white" : "text-zinc-400 hover:text-zinc-200")}>
                <Layers className="h-3 w-3 inline mr-1" />Other
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2 justify-end">
            {processing && processProgress && <div className="w-28 sm:w-36"><div className="flex justify-between text-[9px] text-zinc-400"><span className="capitalize">{processProgress.stage}</span><span>{processProgress.percentage}%</span></div><div className="mt-1 h-1 overflow-hidden rounded bg-zinc-800"><div className="h-full bg-emerald-500 transition-all" style={{ width: `${processProgress.percentage}%` }} /></div></div>}
            {onProcess && <Button type="button" size="sm" onClick={onProcess} loading={processing} icon={<Sparkles className="h-3.5 w-3.5" />}>{processing ? "Processing" : "Process Restyle"}</Button>}
            <button type="button" onClick={onClose} disabled={processing} className="p-1.5 rounded-lg text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-40"><X className="h-4 w-4" /></button>
          </div>
        </div>
        <div className="flex-1 overflow-hidden">
          {tab === "presets" ? (
            <PresetsTab
              hookStyle={hookStyle}
              subtitleStyle={subtitleStyle}
              textEmphasisStyle={textEmphasisStyle}
              watermarkStyle={watermarkStyle}
              ctaStyle={ctaStyle}
              brollStyle={brollStyle}
              onHookChange={onHookChange}
              onSubtitleChange={onSubtitleChange}
              onTextEmphasisChange={onTextEmphasisChange}
              onWatermarkChange={onWatermarkChange}
              onCtaChange={onCtaChange}
              onBrollChange={onBrollChange}
              onPresetLoad={onPresetLoad}
              externalActiveId={externalActivePresetId}
              onPresetSelect={onPresetSelect}
            />
          ) : tab === "hook" ? (
            <HookEditor
              style={hookStyle}
              onChange={onHookChange}
              aspectRatio={aspectRatio}
              thumbnailUrl={thumbnailUrl}
              canvasBackground={canvasBackground}
              isSuperadmin={isSuperadmin}
            />
          ) : tab === "other" ? (
            <OtherTab
              hookStyle={hookStyle}
              textEmphasisStyle={textEmphasisStyle}
              onHookChange={onHookChange}
              onTextEmphasisChange={onTextEmphasisChange}
              watermarkStyle={watermarkStyle}
              onWatermarkChange={onWatermarkChange}
              ctaStyle={ctaStyle}
              onCtaChange={onCtaChange}
              thumbnailUrl={thumbnailUrl}
              aiTextPreviewContext={aiTextPreviewContext}
              aiTextEnabled={aiTextEnabled}
              aspectRatio={aspectRatio}
              canvasBackground={canvasBackground}
            />
          ) : (
            <SubtitleEditor
              style={subtitleStyle}
              onChange={onSubtitleChange}
              aspectRatio={aspectRatio}
              thumbnailUrl={thumbnailUrl}
              isSuperadmin={isSuperadmin}
              isPremium={isPremium}
              userFeatures={userFeatures}
              canvasBackground={canvasBackground}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Other Tab (Transition + AI Text combined) ────────────────────────────────

function OtherTab({
  hookStyle,
  textEmphasisStyle,
  onHookChange,
  onTextEmphasisChange,
  watermarkStyle,
  onWatermarkChange,
  ctaStyle,
  onCtaChange,
  thumbnailUrl,
  aiTextPreviewContext,
  aiTextEnabled,
  aspectRatio,
  canvasBackground
}: {
  hookStyle: HookStyle;
  textEmphasisStyle: TextEmphasisStyle;
  onHookChange: (s: HookStyle) => void;
  onTextEmphasisChange: (s: TextEmphasisStyle) => void;
  watermarkStyle: WatermarkStyle;
  onWatermarkChange: (s: WatermarkStyle) => void;
  ctaStyle: CtaStyle;
  onCtaChange: (s: CtaStyle) => void;
  thumbnailUrl?: string;
  aiTextPreviewContext?: { jobId: string; clipRank: number; frame: number };
  aiTextEnabled: boolean;
  aspectRatio?: string;
  canvasBackground?: { mode: BackgroundMode; templateId: string; imageDataUrl: string | null } | null;
}) {
  const [subTab, setSubTab] = useState<"transition" | "ai_text" | "watermark" | "cta">("transition");

  useEffect(() => {
    if (!aiTextEnabled && subTab === "ai_text") setSubTab("transition");
  }, [aiTextEnabled, subTab]);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex items-center gap-1 px-4 pt-3 pb-2 shrink-0 border-b border-zinc-800/60">
        <button type="button" onClick={() => setSubTab("transition")} className={cn("flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors", subTab === "transition" ? "bg-emerald-600 text-white" : "bg-zinc-800/60 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800")}>
          <MoveRight className="h-3 w-3" />Transition
        </button>
        <button
          type="button"
          onClick={() => setSubTab("ai_text")}
          disabled={!aiTextEnabled}
          aria-disabled={!aiTextEnabled}
          title={!aiTextEnabled ? "Aktifkan AI Cinematic Text untuk membuka pengaturan AI Text" : undefined}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
            !aiTextEnabled
              ? "cursor-not-allowed bg-zinc-900/60 text-zinc-600 opacity-60"
              : subTab === "ai_text"
                ? "bg-emerald-600 text-white"
                : "bg-zinc-800/60 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800",
          )}
        >
          <Layers className="h-3 w-3" />AI Text
        </button>
        <button
          type="button"
          onClick={() => setSubTab("watermark")}
          className={cn("flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors", subTab === "watermark" ? "bg-emerald-600 text-white" : "bg-zinc-800/60 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800")}
        >
          <ImageIcon className="h-3 w-3" />Watermark
        </button>
        <button
          type="button"
          onClick={() => setSubTab("cta")}
          className={cn("flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors", subTab === "cta" ? "bg-emerald-600 text-white" : "bg-zinc-800/60 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800")}
        >
          <Megaphone className="h-3 w-3" />CTA End-Card
        </button>
        <span className="ml-auto text-[9px] text-zinc-600">
          {subTab === "cta" ? "Muncul di akhir video (1s-6s)" : subTab === "watermark" ? "Dirender server-side via FFmpeg" : aiTextEnabled ? "Applied to preview & final render" : "Aktifkan AI Cinematic Text untuk mengatur AI Text"}
        </span>
      </div>
      {subTab === "transition" ? (
        <TransitionEditor
          style={hookStyle}
          onChange={onHookChange}
          thumbnailUrl={thumbnailUrl}
          aspectRatio={aspectRatio}
          canvasBackground={canvasBackground}
        />
      ) : subTab === "ai_text" ? (
        <TextEmphasisEditor
          style={textEmphasisStyle}
          onChange={onTextEmphasisChange}
          thumbnailUrl={thumbnailUrl}
          previewContext={aiTextPreviewContext}
          aspectRatio={aspectRatio}
          canvasBackground={canvasBackground}
        />
      ) : subTab === "cta" ? (
        <CtaEditor
          style={ctaStyle}
          onChange={onCtaChange}
          thumbnailUrl={thumbnailUrl}
          aspectRatio={aspectRatio}
          canvasBackground={canvasBackground}
        />
      ) : (
        <WatermarkEditor
          style={watermarkStyle}
          onChange={onWatermarkChange}
          thumbnailUrl={thumbnailUrl}
          aspectRatio={aspectRatio}
          canvasBackground={canvasBackground}
        />
      )}
    </div>
  );
}

const WATERMARK_POSITIONS: { id: WatermarkStyle["position"]; label: string }[] = [
  { id: "top-left", label: "TL" },
  { id: "top-center", label: "TC" },
  { id: "top-right", label: "TR" },
  { id: "center-left", label: "CL" },
  { id: "center", label: "C" },
  { id: "center-right", label: "CR" },
  { id: "bottom-left", label: "BL" },
  { id: "bottom-center", label: "BC" },
  { id: "bottom-right", label: "BR" },
];

const WATERMARK_POS_CLASS: Record<WatermarkStyle["position"], string> = {
  "top-left": "left-2 top-2",
  "top-center": "left-1/2 -translate-x-1/2 top-2",
  "top-right": "right-2 top-2",
  "center-left": "left-2 top-1/2 -translate-y-1/2",
  center: "left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2",
  "center-right": "right-2 top-1/2 -translate-y-1/2",
  "bottom-left": "left-2 bottom-2",
  "bottom-center": "left-1/2 -translate-x-1/2 bottom-2",
  "bottom-right": "right-2 bottom-2",
};

/** Downscale an uploaded watermark image to a max of 512px so the data URL
 *  stays small (it is persisted in job payloads & presets). PNG is re-encoded
 *  to preserve alpha transparency. */
function downscaleImageDataUrl(file: File, maxSize = 512): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      try {
        const scale = Math.min(1, maxSize / Math.max(img.naturalWidth, img.naturalHeight));
        const w = Math.max(1, Math.round(img.naturalWidth * scale));
        const h = Math.max(1, Math.round(img.naturalHeight * scale));
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          // No canvas context — fall back to reading the raw file as a data URL
          URL.revokeObjectURL(url);
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result || ""));
          reader.onerror = () => reject(new Error("Gagal membaca gambar"));
          reader.readAsDataURL(file);
          return;
        }
        ctx.drawImage(img, 0, 0, w, h);
        URL.revokeObjectURL(url);
        resolve(canvas.toDataURL("image/png"));
      } catch { URL.revokeObjectURL(url); reject(new Error("Gagal memproses gambar")); }
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Gagal membaca gambar")); };
    img.src = url;
  });
}

function WatermarkEditor({ style, onChange, thumbnailUrl, aspectRatio, canvasBackground }: { style: WatermarkStyle; onChange: (s: WatermarkStyle) => void; thumbnailUrl?: string; aspectRatio?: string; canvasBackground?: { mode: BackgroundMode; templateId: string; imageDataUrl: string | null } | null }) {
  const update = (patch: Partial<WatermarkStyle>) => onChange({ ...style, ...patch });
  const posClass = WATERMARK_POS_CLASS[style.position];
  useGoogleFont(style.fontFamily);
  // Canvas (template/upload fill) only applies to 16:9 & 1:1 — matches the bake.
  const canvas = (aspectRatio === "16:9" || aspectRatio === "1:1")
    ? buildCanvasConfig(aspectRatio, {
      backgroundMode: canvasBackground?.mode || "template",
      templateId: canvasBackground?.templateId || "dark-studio",
      backgroundImageUrl: canvasBackground?.imageDataUrl || null,
    })
    : null;
  // Outer frame always 9:16 (final TikTok output); inner composition follows
  // the selected content aspect ratio.
  const outerAspect = "9/16";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 h-full min-h-0 overflow-hidden">
      {/* Left: settings (scrollable) */}
      <div className="lg:col-span-8 min-h-0 overflow-y-auto p-4 space-y-4">
        <Section title="Watermark">
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[11px] font-medium text-zinc-200">Tampilkan watermark di video akhir</p>
                <p className="text-[9px] text-zinc-500">Dirender server-side via FFmpeg — overlay untuk gambar, drawtext untuk teks.</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={style.enabled}
                onClick={() => update({ enabled: !style.enabled })}
                className={cn("relative h-5 w-9 shrink-0 rounded-full transition-colors", style.enabled ? "bg-emerald-600" : "bg-zinc-700")}
              >
                <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all", style.enabled ? "left-[18px]" : "left-0.5")} />
              </button>
            </div>
          </div>
        </Section>

        {style.enabled && (
          <>
            <Section title="Tipe Watermark">
              <div className="grid grid-cols-2 gap-2">
                {(["text", "image"] as const).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => update({ type: t })}
                    className={cn("rounded-xl border p-3 text-left transition-all", style.type === t ? "border-emerald-500 bg-emerald-500/10" : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700")}
                  >
                    <p className="text-[11px] font-semibold text-zinc-200">{t === "text" ? "Text" : "Gambar / Logo"}</p>
                    <p className="mt-0.5 text-[9px] text-zinc-500">{t === "text" ? "Teks watermark (drawtext)" : "Upload PNG/JPG/WebP (overlay)"}</p>
                  </button>
                ))}
              </div>
            </Section>

            {style.type === "text" ? (
              <Section title="Konten Teks">
                <input
                  type="text"
                  value={style.text}
                  onChange={(e) => update({ text: e.target.value })}
                  placeholder="mis. @channelmu"
                  maxLength={60}
                  className="w-full rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none transition-colors"
                />
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={FONT_OPTIONS} />
                  <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <RangeInput label={`Ukuran: ${style.fontSize}px`} min={10} max={120} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
                  <ColorPicker label="Warna" value={style.color} onChange={(v) => update({ color: v })} />
                </div>
              </Section>
            ) : (
              <Section title="Gambar Watermark">
                {style.imageDataUrl ? (
                  <div className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                    <img src={style.imageDataUrl} alt="Watermark" className="h-14 w-14 rounded-lg border border-zinc-700 bg-white/5 object-contain" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[10px] text-zinc-400">Gambar siap dipakai</p>
                      <button type="button" onClick={() => update({ imageDataUrl: null })} className="mt-1 text-[10px] font-medium text-red-400 hover:text-red-300">
                        Hapus gambar
                      </button>
                    </div>
                  </div>
                ) : (
                  <label className="flex min-h-20 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-zinc-700 bg-zinc-950/40 px-3 py-4 text-center transition-colors hover:border-zinc-500">
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (!file) return;
                        e.target.value = ""; // allow re-selecting the same file
                        void downscaleImageDataUrl(file)
                          .then((dataUrl) => update({ imageDataUrl: dataUrl }))
                          .catch(() => update({ imageDataUrl: null }));
                      }}
                    />
                    <Upload className="mb-1 h-4 w-4 text-zinc-500" />
                    <span className="text-[10px] text-zinc-400">Pilih gambar (PNG dengan transparansi disarankan)</span>
                  </label>
                )}
                <div className="mt-3">
                  <RangeInput label={`Ukuran: ${style.sizePct}% dari lebar video`} min={2} max={60} value={style.sizePct} onChange={(v) => update({ sizePct: v })} />
                </div>
              </Section>
            )}

            <Section title="Transparansi & Posisi">
              <div className="grid grid-cols-2 gap-3">
                <RangeInput label={`Opacity: ${style.opacity}%`} min={0} max={100} value={style.opacity} onChange={(v) => update({ opacity: v })} />
                <RangeInput label={`Jarak tepi: ${style.marginPct}%`} min={0} max={20} value={style.marginPct} onChange={(v) => update({ marginPct: v })} />
              </div>
              <div className="mt-3 grid grid-cols-3 gap-1.5">
                {WATERMARK_POSITIONS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => update({ position: p.id })}
                    className={cn("rounded-md border py-1.5 text-[9px] font-medium transition-colors", style.position === p.id ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-800 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300")}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </Section>
          </>
        )}
      </div>

      {/* Right: Live Preview — sticky & vertically centered, stays put while settings scroll */}
      <div className="lg:col-span-4 flex min-h-0 flex-col items-center justify-center overflow-hidden bg-zinc-950 p-4">
        <div className="mb-3 flex w-full items-center justify-between gap-2">
          <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
          <span className="rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-[9px] text-zinc-400">Watermark</span>
        </div>
        <div className="relative w-full max-w-[220px] max-h-[62vh] bg-zinc-900 rounded-lg overflow-hidden border border-zinc-800 shrink-0" style={{ aspectRatio: outerAspect }}>
          {canvas ? (
            /* Full 9:16 canvas with template — matches Remotion bake 1:1 */
            <div className="absolute inset-0" style={{ background: gradientCss(canvas.background) }}>
              {(canvas.backgroundImageUrl || canvas.background?.imageUrl) && (
                <img src={(canvas.backgroundImageUrl || canvas.background.imageUrl) as string} alt="" className="absolute inset-0 h-full w-full object-cover" />
              )}
              <CanvasAccents accents={canvas.accents || []} />
              {(canvas.background.vignette || 0) > 0 && (
                <div className="absolute inset-0 pointer-events-none" style={{ background: `radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,${canvas.background.vignette}) 100%)` }} />
              )}
              {/* Content slot — 16:9/1:1 band; template fills top/bottom (TikTok 9:16) */}
              <div
                className="absolute overflow-hidden bg-zinc-800"
                style={{
                  left: `${canvas.layout.videoX * 100}%`,
                  top: `${canvas.layout.videoY * 100}%`,
                  width: `${canvas.layout.videoW * 100}%`,
                  height: `${canvas.layout.videoH * 100}%`,
                  borderRadius: canvas.layout.borderRadius || 0,
                  boxShadow: canvas.layout.shadow,
                }}
              >
                {thumbnailUrl && <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-contain" />}
              </div>
            </div>
          ) : (
            <>
              {thumbnailUrl && <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-cover" />}
            </>
          )}
          {/* Watermark overlay — spans the full 9:16 frame */}
          <span className={cn("absolute z-10", posClass)} style={{ opacity: Math.max(0.05, style.opacity / 100) }}>
            {style.type === "image" && style.imageDataUrl ? (
              <img src={style.imageDataUrl} alt="" className="h-auto w-auto object-contain" style={{ maxWidth: `${Math.max(8, style.sizePct)}%`, maxHeight: 44 }} />
            ) : (
              <span
                className="font-semibold"
                style={{ fontSize: Math.max(6, Math.round(style.fontSize * 0.3)), fontFamily: `'${style.fontFamily}', sans-serif`, color: style.color }}
              >
                {style.text || "WATERMARK"}
              </span>
            )}
          </span>
          <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-600 z-10">
            {style.enabled ? `${style.type === "image" ? "image" : "text"} · ${style.position.replace(/-/g, " ")} · ${style.opacity}%` : "watermark off"}
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── CTA (Call to Action) End-Card Editor ──────────────────────────────────────

const TikTokSvg = ({ className = "h-3.5 w-3.5" }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor">
    <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.89 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.11V9.43a6.34 6.34 0 0 0-.79-.05 6.34 6.34 0 0 0-6.34 6.34 6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.34-6.34V8.71a8.21 8.21 0 0 0 4.76 1.52v-3.44a4.82 4.82 0 0 1-1-.1z" />
  </svg>
);

const InstagramSvg = ({ className = "h-3.5 w-3.5" }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
    <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
    <line x1="17.5" y1="6.5" x2="17.51" y2="6.5" />
  </svg>
);

const YouTubeSvg = ({ className = "h-3.5 w-3.5" }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor">
    <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
  </svg>
);

const CTA_ICON_OPTIONS: {
  id: CtaStyle["selectedIcon"];
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}[] = [
  { id: "tiktok", label: "TikTok", icon: TikTokSvg },
  { id: "instagram", label: "Instagram", icon: InstagramSvg },
  { id: "youtube", label: "YouTube", icon: YouTubeSvg },
  { id: "bell", label: "Bell", icon: Bell },
  { id: "link", label: "Link Bio", icon: Link2 },
  { id: "share", label: "Share", icon: Share2 },
  { id: "message", label: "Komentar", icon: MessageSquare },
  { id: "zap", label: "Flash / Zap", icon: Zap },
  { id: "user_plus", label: "Follow", icon: UserPlus },
  { id: "heart", label: "Like", icon: Heart },
  { id: "star", label: "Favorit", icon: Star },
];

const CTA_TEMPLATES_CONFIG: {
  id: CtaStyle["template"];
  name: string;
  desc: string;
  badge: string;
  icon: React.ComponentType<{ className?: string }>;
  defaults: Partial<CtaStyle>;
}[] = [
  {
    id: "follow_badge",
    name: "Follow & Like",
    desc: "Pill creator TikTok/IG interaktif dengan tombol follow dan checkmark.",
    badge: "Viral TikTok",
    icon: UserPlus,
    defaults: {
      headline: "Follow For More",
      subhead: "@yourchannel",
      buttonText: "FOLLOW",
      socialPlatform: "tiktok",
      primaryColor: "#FE2C55",
      textColor: "#FFFFFF",
      backgroundColor: "#0F172A",
      bgOpacity: 92,
      animation: "slide_up",
      position: "bottom",
    },
  },
  {
    id: "link_bio",
    name: "Link in Bio",
    desc: "Ajakan klik link di bio dengan tombol aksi dan panah aksentuasi.",
    badge: "High Conversion",
    icon: Link2,
    defaults: {
      headline: "Cek Link di Bio",
      subhead: "Dapatkan akses gratis hari ini",
      buttonText: "KLIK LINK",
      socialPlatform: "instagram",
      primaryColor: "#3B82F6",
      textColor: "#FFFFFF",
      backgroundColor: "#0F172A",
      bgOpacity: 92,
      animation: "pop_in",
      position: "bottom",
    },
  },
  {
    id: "subscribe_pill",
    name: "Subscribe & Bell",
    desc: "Tombol subscribe YouTube Shorts dengan icon lonceng notifikasi.",
    badge: "YouTube Shorts",
    icon: Bell,
    defaults: {
      headline: "Subscribe Channel Ini",
      subhead: "Nyalakan notifikasi update",
      buttonText: "SUBSCRIBE",
      socialPlatform: "youtube",
      primaryColor: "#EF4444",
      textColor: "#FFFFFF",
      backgroundColor: "#0F172A",
      bgOpacity: 92,
      animation: "fade_bounce",
      position: "bottom",
    },
  },
  {
    id: "like_share",
    name: "Like & Share",
    desc: "Mendorong viewer like, share ke teman, dan simpan video.",
    badge: "Engagement",
    icon: Share2,
    defaults: {
      headline: "Suka Konten Ini?",
      subhead: "Bagikan ke teman Anda",
      buttonText: "BAGIKAN",
      socialPlatform: "general",
      primaryColor: "#F59E0B",
      textColor: "#FFFFFF",
      backgroundColor: "#0F172A",
      bgOpacity: 92,
      animation: "glow_pulse",
      position: "bottom",
    },
  },
  {
    id: "comment_prompt",
    name: "Ketik di Komentar",
    desc: "Trigger interaksi algoritma dengan meminta viewer ketik keyword.",
    badge: "DM Trigger",
    icon: MessageSquare,
    defaults: {
      headline: "Ketik 'MAU' di Komentar",
      subhead: "Kami akan kirimkan materinya",
      buttonText: "KOMEN",
      socialPlatform: "instagram",
      primaryColor: "#8B5CF6",
      textColor: "#FFFFFF",
      backgroundColor: "#0F172A",
      bgOpacity: 92,
      animation: "pop_in",
      position: "bottom",
    },
  },
  {
    id: "custom_card",
    name: "Neon / Cyber Card",
    desc: "Tampilan modern futuristik dengan border glow dan badge aksen.",
    badge: "Exclusive",
    icon: Zap,
    defaults: {
      headline: "JOIN VIP COMMUNITY",
      subhead: "Daily alpha insights & tools",
      buttonText: "JOIN NOW",
      socialPlatform: "custom",
      primaryColor: "#06B6D4",
      textColor: "#FFFFFF",
      backgroundColor: "#050B14",
      bgOpacity: 95,
      animation: "glitch",
      position: "bottom",
    },
  },
];

const CTA_ANIMATIONS = [
  { id: "slide_up", label: "Slide Up", desc: "Meluncur naik dari bawah" },
  { id: "pop_in", label: "Pop In", desc: "Membal dinamis (bounce)" },
  { id: "fade_bounce", label: "Fade Bounce", desc: "Fade halus dengan micro bounce" },
  { id: "glow_pulse", label: "Glow Pulse", desc: "Pendaran cahaya berdenyut" },
  { id: "glitch", label: "Glitch Cyber", desc: "Efek glitch digital futuristik" },
] as const;

const CTA_POSITIONS = [
  { id: "bottom", label: "Bawah (Bottom)" },
  { id: "lower-third", label: "Lower-Third" },
  { id: "center", label: "Tengah (Center)" },
  { id: "top", label: "Atas (Top)" },
] as const;

const CTA_PLATFORMS = [
  { id: "tiktok", label: "TikTok" },
  { id: "instagram", label: "Instagram" },
  { id: "youtube", label: "YouTube" },
  { id: "general", label: "Umum / Global" },
  { id: "custom", label: "Custom" },
] as const;

const CTA_COLOR_SWATCHES = [
  "#10B981",
  "#FE2C55",
  "#3B82F6",
  "#EF4444",
  "#8B5CF6",
  "#F59E0B",
  "#EC4899",
  "#06B6D4",
  "#FFFFFF",
];

function CtaEditor({
  style,
  onChange,
  thumbnailUrl,
  aspectRatio,
  canvasBackground,
}: {
  style: CtaStyle;
  onChange: (s: CtaStyle) => void;
  thumbnailUrl?: string;
  aspectRatio?: string;
  canvasBackground?: { mode: BackgroundMode; templateId: string; imageDataUrl: string | null } | null;
}) {
  const update = (patch: Partial<CtaStyle>) => onChange({ ...style, ...patch });
  useGoogleFont(style.fontFamily);

  const canvas = (aspectRatio === "16:9" || aspectRatio === "1:1")
    ? buildCanvasConfig(aspectRatio, {
      backgroundMode: canvasBackground?.mode || "template",
      templateId: canvasBackground?.templateId || "dark-studio",
      backgroundImageUrl: canvasBackground?.imageDataUrl || null,
    })
    : null;
  const outerAspect = "9/16";

  const applyTemplate = (tmplId: CtaStyle["template"]) => {
    const tmpl = CTA_TEMPLATES_CONFIG.find((t) => t.id === tmplId);
    if (!tmpl) return;
    update({
      template: tmplId,
      ...tmpl.defaults,
      enabled: true,
      ctaType: "card",
    });
  };

  const SelectedIconComp = CTA_ICON_OPTIONS.find((i) => i.id === style.selectedIcon)?.icon || UserPlus;
  const [replayKey, setReplayKey] = useState(0);

  useEffect(() => {
    setReplayKey((k) => k + 1);
  }, [style.animation, style.position, style.template, style.ctaType, style.primaryColor]);

  const getCtaAnimStyle = (anim: string): React.CSSProperties => {
    switch (anim) {
      case "slide_up":
        return { animation: "ctaSlideUpPreview 0.75s cubic-bezier(0.16, 1, 0.3, 1) both" };
      case "pop_in":
        return { animation: "ctaPopInPreview 0.7s cubic-bezier(0.34, 1.56, 0.64, 1) both" };
      case "fade_bounce":
        return { animation: "ctaFadeBouncePreview 0.7s cubic-bezier(0.22, 1, 0.36, 1) both" };
      case "glow_pulse":
        return { animation: "ctaGlowPulsePreview 2.2s ease-in-out infinite" };
      case "glitch":
        return { animation: "ctaGlitchCyberPreview 2.8s ease-in-out infinite" };
      default:
        return { animation: "ctaSlideUpPreview 0.75s cubic-bezier(0.16, 1, 0.3, 1) both" };
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 h-full min-h-0 overflow-hidden">
      {/* Left: settings (scrollable) */}
      <div className="lg:col-span-8 min-h-0 overflow-y-auto p-4 space-y-4">
        {/* Master Switch */}
        <Section title="Call To Action (CTA) End-Card">
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-[11px] font-semibold text-zinc-200">Tampilkan CTA di akhir video</p>
                  <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-medium text-emerald-400 border border-emerald-500/20">
                    High Conversion
                  </span>
                </div>
                <p className="text-[9px] text-zinc-500 mt-0.5">
                  Muncul di detik-detik akhir video untuk meningkatkan engagement, follow, subscribe, atau ajakan aksi.
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={style.enabled}
                onClick={() => update({ enabled: !style.enabled })}
                className={cn("relative h-5 w-9 shrink-0 rounded-full transition-colors", style.enabled ? "bg-emerald-600" : "bg-zinc-700")}
              >
                <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all", style.enabled ? "left-[18px]" : "left-0.5")} />
              </button>
            </div>
          </div>
        </Section>

        {style.enabled && (
          <>
            {/* Mode Selector: Card vs Text vs Both */}
            <Section title="Pilih Format Tampilan CTA">
              <div className="grid grid-cols-3 gap-2">
                {[
                  { id: "card", label: "Design Creator Card", desc: "Card interaktif lengkap dengan tombol follow / aksi" },
                  { id: "text", label: "Teks Biasa", desc: "Pesan teks penutup bersih & minimalis" },
                  { id: "both", label: "Keduanya (Teks + Icon)", desc: "Pesan teks kustom dengan icon vektor aksen" },
                ].map((mode) => (
                  <button
                    key={mode.id}
                    type="button"
                    onClick={() => update({ ctaType: mode.id as any })}
                    className={cn(
                      "rounded-xl border p-2.5 text-left transition-all",
                      style.ctaType === mode.id
                        ? "border-emerald-500 bg-emerald-500/10 text-emerald-300 shadow-sm"
                        : "border-zinc-800 bg-zinc-950/40 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                    )}
                  >
                    <p className="text-[11px] font-bold">{mode.label}</p>
                    <p className="text-[8px] text-zinc-500 mt-0.5 leading-relaxed">{mode.desc}</p>
                  </button>
                ))}
              </div>
            </Section>

            {/* Timing Control */}
            <Section title="Durasi Kemunculan di Akhir Video">
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3.5 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-zinc-300">Durasi Tampil CTA:</span>
                  <span className="rounded-md bg-emerald-500/10 px-2.5 py-1 text-xs font-bold text-emerald-400 border border-emerald-500/20">
                    {style.duration.toFixed(1)} detik terakhir
                  </span>
                </div>
                <RangeSlider
                  label="Durasi Tampil CTA"
                  min={1.0}
                  max={6.0}
                  step={0.5}
                  value={style.duration}
                  onChange={(v) => update({ duration: v })}
                />
                <div className="flex items-center justify-between text-[9px] text-zinc-500">
                  <span>1.0s (Cepat)</span>
                  <span className="text-emerald-400/80 font-medium">Default: 3.0s</span>
                  <span>6.0s (Maksimal)</span>
                </div>
                <div className="text-[9px] text-zinc-400 bg-zinc-900/60 p-2.5 rounded-lg border border-zinc-800/80 flex items-start gap-2">
                  <Info className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  <span><strong>Timing Otomatis:</strong> Jika klip berdurasi 30 detik dan CTA diatur {style.duration.toFixed(1)}s, CTA akan muncul tepat pada detik ke-{(30 - style.duration).toFixed(1)}s hingga akhir video.</span>
                </div>
              </div>
            </Section>

            {/* Mode-Specific Content: Card Mode */}
            {style.ctaType === "card" && (
              <>
                {/* Template Presets */}
                <Section title="Pilih Template Card CTA">
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                    {CTA_TEMPLATES_CONFIG.map((tmpl) => {
                      const isSelected = style.template === tmpl.id;
                      const IconComp = tmpl.icon;
                      return (
                        <button
                          key={tmpl.id}
                          type="button"
                          onClick={() => applyTemplate(tmpl.id)}
                          className={cn(
                            "rounded-xl border p-3 text-left transition-all relative flex flex-col justify-between group",
                            isSelected
                              ? "border-emerald-500 bg-emerald-500/10 shadow-sm shadow-emerald-500/20"
                              : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700 hover:bg-zinc-900/40"
                          )}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className={cn("p-1.5 rounded-lg border transition-colors", isSelected ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" : "bg-zinc-900 text-zinc-400 border-zinc-800")}>
                              <IconComp className="h-4 w-4" />
                            </div>
                            <span className="rounded bg-zinc-800/80 px-1.5 py-0.5 text-[8px] font-semibold text-zinc-400 border border-zinc-700/50">
                              {tmpl.badge}
                            </span>
                          </div>
                          <div>
                            <p className={cn("text-[11px] font-bold", isSelected ? "text-emerald-300" : "text-zinc-200")}>
                              {tmpl.name}
                            </p>
                            <p className="text-[9px] text-zinc-500 mt-0.5 line-clamp-2 leading-relaxed">
                              {tmpl.desc}
                            </p>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </Section>

                {/* Content Customization */}
                <Section title="Konten Card CTA">
                  <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-950/40 p-3.5">
                    <div>
                      <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1">
                        Headline (Judul Utama Card)
                      </label>
                      <input
                        type="text"
                        value={style.headline}
                        onChange={(e) => update({ headline: e.target.value })}
                        placeholder="mis. Follow For More / Cek Link di Bio"
                        maxLength={60}
                        className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none transition-colors"
                      />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1">
                          Subhead (Keterangan / Slogan)
                        </label>
                        <input
                          type="text"
                          value={style.subhead}
                          onChange={(e) => update({ subhead: e.target.value })}
                          placeholder="mis. @yourchannel / Tips baru tiap hari"
                          maxLength={60}
                          className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none transition-colors"
                        />
                      </div>

                      <div>
                        <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1">
                          Teks Tombol / Action Badge
                        </label>
                        <input
                          type="text"
                          value={style.buttonText}
                          onChange={(e) => update({ buttonText: e.target.value })}
                          placeholder="mis. FOLLOW / KLIK LINK / SUBSCRIBE"
                          maxLength={30}
                          className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none transition-colors"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                      <SelectSmall
                        label="Platform Sosial"
                        value={style.socialPlatform}
                        onChange={(v) => update({ socialPlatform: v as any })}
                        options={CTA_PLATFORMS.map((p) => p.id)}
                      />
                      <div>
                        <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1">
                          Handle Akun Sosial
                        </label>
                        <input
                          type="text"
                          value={style.socialHandle}
                          onChange={(e) => update({ socialHandle: e.target.value })}
                          placeholder="@username"
                          maxLength={30}
                          className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none transition-colors"
                        />
                      </div>
                    </div>
                  </div>
                </Section>
              </>
            )}

            {/* Mode-Specific Content: Plain Text Mode */}
            {style.ctaType === "text" && (
              <Section title="Input Teks CTA">
                <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-950/40 p-3.5">
                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1">
                      Teks Pesan Penutup (CTA)
                    </label>
                    <textarea
                      rows={2}
                      value={style.text}
                      onChange={(e) => update({ text: e.target.value })}
                      placeholder="mis. Jangan lupa follow & share video ini ke teman kamu!"
                      maxLength={120}
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none transition-colors resize-none"
                    />
                  </div>
                  <div className="flex items-center justify-between pt-1">
                    <div>
                      <p className="text-[11px] font-medium text-zinc-200">Gunakan Background Box / Pill</p>
                      <p className="text-[9px] text-zinc-500">Beri latar belakang semi-transparan di belakang teks</p>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={style.bgBox}
                      onClick={() => update({ bgBox: !style.bgBox })}
                      className={cn("relative h-5 w-9 shrink-0 rounded-full transition-colors", style.bgBox ? "bg-emerald-600" : "bg-zinc-700")}
                    >
                      <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all", style.bgBox ? "left-[18px]" : "left-0.5")} />
                    </button>
                  </div>
                </div>
              </Section>
            )}

            {/* Mode-Specific Content: Both (Text + Icon) Mode */}
            {style.ctaType === "both" && (
              <Section title="Input Teks & Pilihan Icon Vector">
                <div className="space-y-3.5 rounded-lg border border-zinc-800 bg-zinc-950/40 p-3.5">
                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1">
                      Teks Pesan Penutup (CTA)
                    </label>
                    <input
                      type="text"
                      value={style.text}
                      onChange={(e) => update({ text: e.target.value })}
                      placeholder="mis. Follow untuk konten menarik berikutnya!"
                      maxLength={80}
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none transition-colors"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">
                      Pilih Icon Vector (Clean SVG)
                    </label>
                    <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                      {CTA_ICON_OPTIONS.map((item) => {
                        const isSelected = style.selectedIcon === item.id;
                        const IconComp = item.icon;
                        return (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => update({ selectedIcon: item.id })}
                            className={cn(
                              "flex items-center gap-2 rounded-lg border px-2.5 py-2 text-left transition-all",
                              isSelected
                                ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                                : "border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                            )}
                          >
                            <IconComp className="h-4 w-4 shrink-0 text-emerald-400" />
                            <span className="text-[10px] font-medium truncate">{item.label}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    <div>
                      <p className="text-[11px] font-medium text-zinc-200">Gunakan Background Box / Pill</p>
                      <p className="text-[9px] text-zinc-500">Tampilkan sebagai pill badge dengan latar transparan</p>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={style.bgBox}
                      onClick={() => update({ bgBox: !style.bgBox })}
                      className={cn("relative h-5 w-9 shrink-0 rounded-full transition-colors", style.bgBox ? "bg-emerald-600" : "bg-zinc-700")}
                    >
                      <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all", style.bgBox ? "left-[18px]" : "left-0.5")} />
                    </button>
                  </div>
                </div>
              </Section>
            )}

            {/* Styling, Positioning & Animation */}
            <Section title="Desain, Posisi & Animasi">
              <div className="space-y-3.5 rounded-lg border border-zinc-800 bg-zinc-950/40 p-3.5">
                {/* Position */}
                <div>
                  <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">
                    Posisi CTA di Video
                  </label>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {CTA_POSITIONS.map((pos) => (
                      <button
                        key={pos.id}
                        type="button"
                        onClick={() => update({ position: pos.id })}
                        className={cn(
                          "rounded-lg border py-2 text-[10px] font-medium transition-colors text-center",
                          style.position === pos.id
                            ? "border-emerald-500 bg-emerald-500/10 text-emerald-400 font-semibold"
                            : "border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                        )}
                      >
                        {pos.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Animation */}
                <div>
                  <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">
                    Animasi Muncul
                  </label>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                    {CTA_ANIMATIONS.map((anim) => (
                      <button
                        key={anim.id}
                        type="button"
                        onClick={() => update({ animation: anim.id })}
                        className={cn(
                          "rounded-lg border px-2.5 py-1.5 text-left transition-colors",
                          style.animation === anim.id
                            ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                            : "border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                        )}
                      >
                        <p className="text-[10px] font-semibold">{anim.label}</p>
                        <p className="text-[8px] text-zinc-500">{anim.desc}</p>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Color Pickers */}
                <div className="pt-1">
                  <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">
                    Warna Tombol / Aksen (Primary Color)
                  </label>
                  <div className="flex flex-wrap items-center gap-1.5 mb-2">
                    {CTA_COLOR_SWATCHES.map((hex) => (
                      <button
                        key={hex}
                        type="button"
                        onClick={() => update({ primaryColor: hex })}
                        className={cn(
                          "h-5 w-5 rounded-full border transition-transform",
                          style.primaryColor.toLowerCase() === hex.toLowerCase() ? "scale-125 border-white ring-2 ring-emerald-500/50" : "border-white/20 hover:scale-110"
                        )}
                        style={{ backgroundColor: hex }}
                      />
                    ))}
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                    <ColorPicker label="Warna Tombol / Aksen" value={style.primaryColor} onChange={(v) => update({ primaryColor: v })} />
                    <ColorPicker label="Warna Teks" value={style.textColor} onChange={(v) => update({ textColor: v })} />
                    <ColorPicker label="Warna Background" value={style.backgroundColor} onChange={(v) => update({ backgroundColor: v })} />
                  </div>
                </div>

                {/* Opacity & Typography */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                  <RangeInput
                    label={`Transparansi Background: ${style.bgOpacity}%`}
                    min={0}
                    max={100}
                    value={style.bgOpacity}
                    onChange={(v) => update({ bgOpacity: v })}
                  />
                  <RangeInput
                    label={`Ukuran Font: ${style.fontSize}px`}
                    min={18}
                    max={48}
                    value={style.fontSize}
                    onChange={(v) => update({ fontSize: v })}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <SelectSmall
                    label="Font Family"
                    value={style.fontFamily}
                    onChange={(v) => update({ fontFamily: v })}
                    options={FONT_OPTIONS}
                  />
                  <SelectSmall
                    label="Font Weight"
                    value={style.fontWeight}
                    onChange={(v) => update({ fontWeight: v })}
                    options={["400", "500", "600", "700", "800", "900"]}
                  />
                </div>
              </div>
            </Section>
          </>
        )}
      </div>

      {/* Right: Live Preview */}
      <div className="lg:col-span-4 flex min-h-0 flex-col items-center justify-center overflow-hidden bg-zinc-950 p-4">
        <div className="mb-3 flex w-full items-center justify-between gap-2">
          <p className="text-[9px] text-zinc-500 uppercase tracking-widest shrink-0 font-semibold">Live Mockup Preview</p>
          <span className="rounded-md border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[9px] font-medium text-emerald-400">
            {style.ctaType === "text" ? "Plain Text CTA" : style.ctaType === "both" ? "Text + Icon CTA" : "Creator Card CTA"}
          </span>
        </div>

        <div
          className="relative w-full max-w-[240px] max-h-[64vh] bg-zinc-900 rounded-xl overflow-hidden border border-zinc-800 shrink-0 shadow-2xl flex flex-col justify-between"
          style={{ aspectRatio: outerAspect }}
        >
          {/* Inject Dynamic Keyframes for CTA Preview Animations */}
          <style>{`
            @keyframes ctaSlideUpPreview {
              0% { transform: translateY(45px) scale(0.9); opacity: 0; }
              65% { transform: translateY(-4px) scale(1.02); opacity: 1; }
              100% { transform: translateY(0) scale(1); opacity: 1; }
            }
            @keyframes ctaPopInPreview {
              0% { transform: scale(0.15); opacity: 0; }
              55% { transform: scale(1.16); opacity: 1; }
              75% { transform: scale(0.94); opacity: 1; }
              100% { transform: scale(1); opacity: 1; }
            }
            @keyframes ctaFadeBouncePreview {
              0% { transform: scale(0.85) translateY(12px); opacity: 0; }
              65% { transform: scale(1.04) translateY(-2px); opacity: 1; }
              100% { transform: scale(1) translateY(0); opacity: 1; }
            }
            @keyframes ctaGlowPulsePreview {
              0%, 100% {
                transform: scale(0.97);
                box-shadow: 0 8px 25px rgba(0,0,0,0.6), 0 0 8px ${style.primaryColor}55;
              }
              50% {
                transform: scale(1.03);
                box-shadow: 0 12px 32px rgba(0,0,0,0.7), 0 0 22px ${style.primaryColor}cc, 0 0 35px ${style.primaryColor}66;
              }
            }
            @keyframes ctaGlitchCyberPreview {
              0%, 100% { transform: translate(0, 0); filter: none; clip-path: none; }
              12% { transform: translate(-3px, 1px); clip-path: inset(15% 0 45% 0); filter: drop-shadow(-2px 0 #00ffff) drop-shadow(2px 0 #ff0055); }
              24% { transform: translate(3px, -2px); clip-path: inset(50% 0 10% 0); filter: drop-shadow(2px 0 #00ffff) drop-shadow(-2px 0 #ff0055); }
              36% { transform: translate(-2px, -1px); clip-path: inset(25% 0 35% 0); }
              48% { transform: translate(1px, 2px); clip-path: none; filter: drop-shadow(-2px 0 #00ffff); }
              75% { transform: translate(0, 0); clip-path: none; filter: none; }
            }
          `}</style>

          {/* Background Canvas / Thumbnail */}
          {canvas ? (
            <div className="absolute inset-0" style={{ background: gradientCss(canvas.background) }}>
              {(canvas.backgroundImageUrl || canvas.background?.imageUrl) && (
                <img src={(canvas.backgroundImageUrl || canvas.background.imageUrl) as string} alt="" className="absolute inset-0 h-full w-full object-cover" />
              )}
              <CanvasAccents accents={canvas.accents || []} />
              {(canvas.background.vignette || 0) > 0 && (
                <div className="absolute inset-0 pointer-events-none" style={{ background: `radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,${canvas.background.vignette}) 100%)` }} />
              )}
              <div
                className="absolute overflow-hidden bg-zinc-800"
                style={{
                  left: `${canvas.layout.videoX * 100}%`,
                  top: `${canvas.layout.videoY * 100}%`,
                  width: `${canvas.layout.videoW * 100}%`,
                  height: `${canvas.layout.videoH * 100}%`,
                  borderRadius: canvas.layout.borderRadius || 0,
                  boxShadow: canvas.layout.shadow,
                }}
              >
                {thumbnailUrl ? (
                  <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-contain" />
                ) : (
                  <div className="w-full h-full bg-gradient-to-br from-zinc-800 to-zinc-900" />
                )}
              </div>
            </div>
          ) : (
            <>
              {thumbnailUrl ? (
                <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-cover" />
              ) : (
                <div className="absolute inset-0 bg-gradient-to-b from-zinc-800 via-zinc-900 to-black" />
              )}
            </>
          )}

          {/* Vignette overlay */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-black/30 pointer-events-none" />

          {/* Top Timing & Replay Indicator */}
          <div className="relative z-10 m-2 flex items-center justify-between gap-1">
            <span className="rounded bg-black/60 backdrop-blur-md px-2 py-0.5 text-[8px] font-medium text-zinc-300 border border-white/10 flex items-center gap-1">
              <Clock className="h-2.5 w-2.5 text-emerald-400" />
              {style.enabled ? `Muncul di ${style.duration.toFixed(1)}s terakhir` : "CTA Nonaktif"}
            </span>
            {style.enabled && (
              <button
                type="button"
                onClick={() => setReplayKey((k) => k + 1)}
                title="Putar Ulang Animasi"
                className="rounded bg-black/60 hover:bg-emerald-500/20 hover:text-emerald-300 hover:border-emerald-500/30 backdrop-blur-md px-1.5 py-0.5 text-[8px] font-medium text-zinc-400 border border-white/10 flex items-center gap-1 transition-all"
              >
                <RotateCcw className="h-2.5 w-2.5 text-emerald-400" />
                <span>Replay</span>
              </button>
            )}
          </div>

          {/* Animated CTA Preview based on Mode */}
          {style.enabled && (
            <div
              key={replayKey}
              className={cn(
                "absolute left-3 right-3 z-20",
                style.position === "top"
                  ? "top-10"
                  : style.position === "center"
                    ? "top-1/2 -translate-y-1/2"
                    : style.position === "lower-third"
                      ? "bottom-14"
                      : "bottom-4"
              )}
              style={getCtaAnimStyle(style.animation)}
            >
              {/* Card Mode Preview */}
              {style.ctaType === "card" && (
                <div
                  className="rounded-xl p-2.5 backdrop-blur-md flex items-center justify-between gap-2 transition-all shadow-xl"
                  style={{
                    backgroundColor: style.backgroundColor.startsWith("#")
                      ? `${style.backgroundColor}${Math.round((style.bgOpacity / 100) * 255).toString(16).padStart(2, "0")}`
                      : style.backgroundColor,
                    borderColor: `${style.primaryColor}55`,
                    borderWidth: "1.5px",
                    boxShadow: `0 8px 25px rgba(0,0,0,0.6), 0 0 15px ${style.primaryColor}33`,
                    color: style.textColor,
                    fontFamily: `'${style.fontFamily}', sans-serif`,
                  }}
                >
                  <div className="min-w-0 flex-1">
                    <p
                      className="truncate font-bold leading-tight"
                      style={{
                        fontSize: Math.max(9, Math.round(style.fontSize * 0.38)),
                        fontWeight: style.fontWeight as any,
                        color: style.textColor,
                      }}
                    >
                      {style.headline || "Follow For More"}
                    </p>
                    {(style.subhead || style.socialHandle) && (
                      <p className="truncate text-[8px] text-zinc-400 mt-0.5 font-medium">
                        {style.subhead || style.socialHandle}
                      </p>
                    )}
                  </div>

                  <div
                    className="rounded-full px-2.5 py-1 text-[8px] font-bold text-white shrink-0 flex items-center gap-1 shadow-md transition-transform hover:scale-105"
                    style={{
                      backgroundColor: style.primaryColor,
                      boxShadow: `0 2px 10px ${style.primaryColor}66`,
                    }}
                  >
                    {style.template === "subscribe_pill" && <Bell className="h-2.5 w-2.5" />}
                    {style.template === "follow_badge" && <Plus className="h-2.5 w-2.5" />}
                    {style.template === "link_bio" && <ArrowUpRight className="h-2.5 w-2.5" />}
                    {style.template === "like_share" && <Share2 className="h-2.5 w-2.5" />}
                    {style.template === "comment_prompt" && <MessageSquare className="h-2.5 w-2.5" />}
                    {style.template === "custom_card" && <Zap className="h-2.5 w-2.5" />}
                    <span>{style.buttonText || "FOLLOW"}</span>
                  </div>
                </div>
              )}

              {/* Plain Text Mode Preview */}
              {style.ctaType === "text" && (
                <div
                  className={cn(
                    "text-center transition-all",
                    style.bgBox ? "rounded-xl p-2.5 backdrop-blur-md shadow-xl border" : "p-1"
                  )}
                  style={{
                    backgroundColor: style.bgBox
                      ? (style.backgroundColor.startsWith("#")
                        ? `${style.backgroundColor}${Math.round((style.bgOpacity / 100) * 255).toString(16).padStart(2, "0")}`
                        : style.backgroundColor)
                      : "transparent",
                    borderColor: style.bgBox ? `${style.primaryColor}55` : "transparent",
                    boxShadow: style.bgBox ? `0 8px 25px rgba(0,0,0,0.6), 0 0 15px ${style.primaryColor}33` : "none",
                    fontFamily: `'${style.fontFamily}', sans-serif`,
                  }}
                >
                  <p
                    className="font-bold leading-snug"
                    style={{
                      fontSize: Math.max(9, Math.round(style.fontSize * 0.38)),
                      fontWeight: style.fontWeight as any,
                      color: style.textColor,
                      textShadow: style.bgBox ? "0 1px 4px rgba(0,0,0,0.5)" : "0 2px 8px rgba(0,0,0,0.9), 0 0 4px #000",
                    }}
                  >
                    {style.text || "Jangan lupa follow!"}
                  </p>
                </div>
              )}

              {/* Text + Icon (Both) Mode Preview */}
              {style.ctaType === "both" && (
                <div
                  className={cn(
                    "flex items-center justify-center gap-2 transition-all",
                    style.bgBox ? "rounded-full py-1.5 px-3 backdrop-blur-md shadow-xl border" : "p-1"
                  )}
                  style={{
                    backgroundColor: style.bgBox
                      ? (style.backgroundColor.startsWith("#")
                        ? `${style.backgroundColor}${Math.round((style.bgOpacity / 100) * 255).toString(16).padStart(2, "0")}`
                        : style.backgroundColor)
                      : "transparent",
                    borderColor: style.bgBox ? `${style.primaryColor}55` : "transparent",
                    boxShadow: style.bgBox ? `0 8px 25px rgba(0,0,0,0.6), 0 0 15px ${style.primaryColor}33` : "none",
                    fontFamily: `'${style.fontFamily}', sans-serif`,
                  }}
                >
                  <div
                    className="p-1 rounded-full text-white shrink-0 flex items-center justify-center"
                    style={{ backgroundColor: style.primaryColor }}
                  >
                    <SelectedIconComp className="h-3 w-3" />
                  </div>
                  <p
                    className="font-bold truncate text-left"
                    style={{
                      fontSize: Math.max(9, Math.round(style.fontSize * 0.36)),
                      fontWeight: style.fontWeight as any,
                      color: style.textColor,
                      textShadow: style.bgBox ? "0 1px 4px rgba(0,0,0,0.5)" : "0 2px 8px rgba(0,0,0,0.9), 0 0 4px #000",
                    }}
                  >
                    {style.text || "Follow untuk update!"}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Bottom helper text */}
          <p className="relative z-10 m-1.5 text-center text-[7px] text-zinc-500 font-medium">
            {style.enabled ? `${style.ctaType.toUpperCase()} · ${style.position} · ${style.animation}` : "CTA End-Card Nonaktif"}
          </p>
        </div>
      </div>
    </div>
  );
}

const TRANSITION_META: Record<string, { label: string; desc: string; icon: React.ComponentType<{ className?: string }> }> = {
  cut: { label: "Cut", desc: "Hard cut antar framing. Cepat & energik.", icon: Scissors },
  fade: { label: "Fade", desc: "Cross-fade halus. Cinematic & natural.", icon: Layers },
  slide: { label: "Slide", desc: "Geser horizontal. Dinamis & modern.", icon: MoveRight },
  zoom: { label: "Zoom", desc: "Zoom in/out transisi. Dramatis.", icon: Maximize2 },
};

function TransitionEditor({
  style,
  onChange,
  thumbnailUrl,
  aspectRatio,
  canvasBackground,
}: {
  style: HookStyle;
  onChange: (style: HookStyle) => void;
  thumbnailUrl?: string;
  aspectRatio?: string;
  canvasBackground?: { mode: BackgroundMode; templateId: string; imageDataUrl: string | null } | null;
}) {
  const active = style.transitionStyle || "cut";
  const duration = style.transitionDuration ?? 0.35;
  const durationInt = Math.round(duration * 100);
  const previewDur = Math.max(0.8, duration * 2);
  const update = (patch: Partial<HookStyle>) => onChange({ ...style, ...patch });
  const canvas = (aspectRatio === "16:9" || aspectRatio === "1:1")
    ? buildCanvasConfig(aspectRatio, {
      backgroundMode: canvasBackground?.mode || "template",
      templateId: canvasBackground?.templateId || "dark-studio",
      backgroundImageUrl: canvasBackground?.imageDataUrl || null,
    })
    : null;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 h-full">
      {/* Left: Live preview (sticky) */}
      <div className="xl:col-span-5 p-4 overflow-y-auto space-y-4 border-r border-zinc-800">
        <Section title="Live Preview">
          <div className="flex justify-center">
            <CanvasPreviewFrame canvas={canvas} thumbnailUrl={thumbnailUrl} className="max-w-[200px] rounded-xl border-zinc-700 shadow-2xl">
              <div className="absolute inset-0 flex items-center justify-center" style={{ animation: `${active === "cut" ? "transCut" : active === "fade" ? "transFade" : active === "slide" ? "transSlide" : "transZoom"} ${previewDur}s ease-in-out infinite` }}>
                <div className="h-full w-full bg-gradient-to-br from-emerald-500/60 to-blue-500/50" />
              </div>
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <span className="rounded-full bg-black/60 px-2.5 py-0.5 text-[9px] font-medium text-white backdrop-blur-sm">{active} · {duration.toFixed(2)}s</span>
              </div>
              <div className="absolute bottom-2 left-2 z-30 rounded-md bg-black/60 px-2 py-0.5 text-[8px] text-zinc-400">Preview transition</div>
            </CanvasPreviewFrame>
          </div>
        </Section>

        <Section title="Info">
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
            <p className="text-[10px] leading-relaxed text-zinc-400">
              Transisi diterapkan saat clip dimulai atau saat framing speaker berubah (single → grid, atau panning antar speaker). Pilihan ini mempengaruhi <span className="text-emerald-400">preview</span> dan <span className="text-emerald-400">final Remotion render</span>.
            </p>
          </div>
        </Section>
      </div>

      {/* Right: Controls */}
      <div className="xl:col-span-7 p-4 overflow-y-auto space-y-4">
        <style>{`
          @keyframes transCut { 0%,49% { opacity:1; } 50%,99% { opacity:0; } 100% { opacity:1; } }
          @keyframes transFade { 0%,100% { opacity:1; } 50% { opacity:0; } }
          @keyframes transSlide { 0% { transform:translateX(0); } 49% { transform:translateX(-100%); } 50% { transform:translateX(100%); } 100% { transform:translateX(0); } }
          @keyframes transZoom { 0%,100% { transform:scale(1); opacity:1; } 50% { transform:scale(1.5); opacity:0; } }
        `}</style>

        <Section title="Transition Style">
          <div className="grid grid-cols-2 gap-2">
            {(["cut", "fade", "slide", "zoom"] as const).map((value) => {
              const meta = TRANSITION_META[value];
              return (
                <button type="button" key={value} onClick={() => update({ transitionStyle: value })} className={cn("rounded-xl border p-3 text-left transition-all", active === value ? "border-emerald-500 bg-emerald-500/10" : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700")}>
                  <div className="mb-2 flex items-center justify-between">
                    <meta.icon className={cn("h-4 w-4", active === value ? "text-emerald-400" : "text-zinc-500")} />
                    {active === value && <span className="text-[8px] font-bold uppercase tracking-wider text-emerald-400">Active</span>}
                  </div>
                  <p className={cn("text-xs font-semibold", active === value ? "text-emerald-300" : "text-zinc-300")}>{meta.label}</p>
                  <p className="mt-0.5 text-[9px] leading-tight text-zinc-600">{meta.desc}</p>
                </button>
              );
            })}
          </div>
        </Section>

        <Section title="Timing">
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
            <RangeInput label={`Duration: ${duration.toFixed(2)}s`} min={15} max={100} value={durationInt} onChange={(v) => update({ transitionDuration: v / 100 })} />
            <p className="mt-2 text-[9px] text-zinc-600">Rentang 0.15s – 1.00s. Cut cepat untuk energi tinggi, fade lambat untuk vibe cinematic.</p>
          </div>
        </Section>
      </div>
    </div>
  );
}

function TextEmphasisEditor({
  style,
  onChange,
  thumbnailUrl,
  previewContext,
  aspectRatio,
  canvasBackground,
}: {
  style: TextEmphasisStyle;
  onChange: (style: TextEmphasisStyle) => void;
  thumbnailUrl?: string;
  previewContext?: { jobId: string; clipRank: number; frame: number };
  aspectRatio?: string;
  canvasBackground?: { mode: BackgroundMode; templateId: string; imageDataUrl: string | null } | null;
}) {
  useGoogleFont(style.fontFamily);
  const [exactPreview, setExactPreview] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const canvas = (aspectRatio === "16:9" || aspectRatio === "1:1")
    ? buildCanvasConfig(aspectRatio, {
      backgroundMode: canvasBackground?.mode || "template",
      templateId: canvasBackground?.templateId || "dark-studio",
      backgroundImageUrl: canvasBackground?.imageDataUrl || null,
    })
    : null;

  useEffect(() => {
    if (!previewContext) return;
    let active = true;
    const timer = window.setTimeout(async () => {
      setPreviewLoading(true);
      try {
        const result = await jobs.renderAITextPreview(previewContext.jobId, previewContext.clipRank, previewContext.frame, style);
        if (active) setExactPreview(result.image);
      } catch {
        if (active) setExactPreview(null);
      } finally {
        if (active) setPreviewLoading(false);
      }
    }, 350);
    return () => { active = false; window.clearTimeout(timer); };
  }, [previewContext?.jobId, previewContext?.clipRank, previewContext?.frame, style]);
  const update = <K extends keyof TextEmphasisStyle>(key: K, value: TextEmphasisStyle[K]) => onChange({ ...style, [key]: value });
  const previewEffect = style.effectMode === "auto" ? "hero_punch" : style.effectMode;
  // For auto_avoid, preview shows text at top (person assumed in bottom)
  const previewTop = previewEffect === "smart_gap" ? "22%" : `${style.positionY}%`;
  const previewAlign = previewEffect === "smart_gap" ? "justify-end text-right"
    : previewEffect === "side_rail" ? "justify-start text-left"
      : "justify-center text-center";
  const textStyle = {
    fontFamily: style.fontFamily === "monospace" ? "monospace" : `'${style.fontFamily}', sans-serif`,
    fontSize: Math.max(16, style.fontSize * 0.28),
    fontWeight: Number(style.fontWeight),
    letterSpacing: style.letterSpacing * 0.35,
    lineHeight: style.lineHeight,
    color: style.color,
    textTransform: style.uppercase ? "uppercase" as const : "none" as const,
    WebkitTextStroke: style.strokeEnabled ? `${Math.max(0.5, style.strokeWidth * 0.35)}px ${style.strokeColor}` : undefined,
    paintOrder: style.strokeEnabled ? "stroke" as const : undefined,
    textShadow: style.shadowEnabled ? `0 3px ${Math.max(4, style.shadowBlur * 0.35)}px ${style.shadowColor}` : undefined,
  };

  // Kinetic typography preview: split words
  const kineticPreviewWords = previewEffect === "word_cascade"
    ? "Ide Besar yang Perlu Diingat".split(" ") : [];

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">AI Cinematic Text</h3>
          <p className="mt-1 max-w-xl text-xs leading-5 text-zinc-500">AI memilih maksimal 2 frasa paling kuat per clip. Subtitle berhenti hanya selama frasa tampil, lalu kembali ke timing aslinya.</p>
        </div>
        <span className="shrink-0 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-semibold text-emerald-400">MAX 2 / CLIP</span>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(280px,0.85fr)_minmax(360px,1.15fr)]">
        <div>
          <div className="sticky top-0">
            <CanvasPreviewFrame
              canvas={canvas}
              thumbnailUrl={thumbnailUrl}
              className="max-h-[520px] max-w-none w-full shadow-2xl rounded-2xl border-zinc-700"
            >
              {exactPreview && <img src={exactPreview} alt="Exact final-render AI Text preview" className="absolute inset-0 z-40 h-full w-full object-cover" />}
              {previewEffect === "hero_punch" && <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(0,0,0,.75)_100%)]" />}
              {previewEffect === "z_parallax" && <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,transparent_0%,rgba(0,0,0,.5)_100%)]" />}
              {previewEffect === "split_impact" && <div className="absolute inset-0 bg-gradient-to-r from-black/60 via-transparent to-rose-500/20" />}
              {previewEffect === "sticker_pop" && <div className="absolute inset-0 bg-black/25" />}
              {previewEffect === "orbit_halo" && (
                <div className="absolute left-1/2 top-[20%] z-20 h-12 w-12 -translate-x-1/2 rounded-full bg-gradient-to-br from-zinc-300 to-zinc-600 shadow-xl" />
              )}
              {(previewEffect === "float_track" || previewEffect === "smart_gap") && (
                <div className="absolute bottom-[12%] left-1/2 z-5 h-[55%] w-[42%] -translate-x-1/2 opacity-60">
                  <div className="absolute left-1/2 top-[8%] h-[20%] aspect-square -translate-x-1/2 rounded-full bg-gradient-to-br from-zinc-400 to-zinc-700 shadow-xl" />
                  <div className="absolute bottom-0 left-1/2 h-[78%] w-full -translate-x-1/2 rounded-t-[48%] bg-gradient-to-r from-zinc-800 via-zinc-500 to-zinc-800 shadow-2xl" />
                </div>
              )}
              {previewEffect === "z_parallax" && (
                <div className="absolute bottom-[15%] left-1/2 z-5 h-[60%] w-[46%] -translate-x-1/2 opacity-70" style={{ filter: "blur(0.5px)" }}>
                  <div className="absolute left-1/2 top-[6%] h-[18%] aspect-square -translate-x-1/2 rounded-full bg-gradient-to-br from-zinc-400 to-zinc-700 shadow-xl" />
                  <div className="absolute bottom-0 left-1/2 h-[80%] w-full -translate-x-1/2 rounded-t-[48%] bg-gradient-to-r from-zinc-800 via-zinc-500 to-zinc-800 shadow-2xl" />
                </div>
              )}
              <div className={cn("absolute inset-x-[7%] z-10 flex", previewAlign)} style={{ top: previewTop, transform: "translateY(-50%)" }}>
                <div style={{ ...textStyle, maxWidth: `${style.maxWidthPct}%` }}>
                  {previewEffect === "side_rail" && <div className="mb-2 h-1 w-10 rounded-full" style={{ backgroundColor: style.accentColor }} />}
                  {previewEffect === "word_cascade" ? (
                    <span>
                      {kineticPreviewWords.map((word, idx) => (
                        <span key={idx} style={{ display: "inline-block", marginRight: "0.25em", opacity: 0.6 + (idx % 3) * 0.2, transform: `translateY(${(2 - (idx % 3)) * 4}px)` }}>{word}</span>
                      ))}
                    </span>
                  ) : previewEffect === "split_impact" ? (
                    <span><span style={{ color: style.color }}>Ide Besar </span><span style={{ color: style.accentColor }}>yang Perlu</span></span>
                  ) : previewEffect === "type_pulse" ? (
                    <span>Ide Besar|</span>
                  ) : previewEffect === "sticker_pop" ? (
                    <span style={{ display: "inline-block", padding: "6px 10px", border: `2px solid ${style.accentColor}`, borderRadius: 8, transform: `rotate(${style.stickerAngle ?? -6}deg)`, background: `${style.accentColor}33` }}>Ide Besar</span>
                  ) : previewEffect === "mirror_echo" ? (
                    <span style={{ position: "relative", display: "inline-block" }}>
                      <span style={{ position: "absolute", left: -4, top: 2, opacity: 0.35, color: style.accentColor }}>Ide Besar</span>
                      <span style={{ position: "relative" }}>Ide Besar</span>
                    </span>
                  ) : (
                    "Ide Besar yang Perlu Diingat"
                  )}
                  {previewEffect === "hero_punch" && <div className="mx-auto mt-2 h-1 w-16 rounded-full" style={{ backgroundColor: style.accentColor, boxShadow: `0 0 10px ${style.accentColor}` }} />}
                  {previewEffect === "float_track" && <div className="mx-auto mt-2 h-1 w-12 rounded-full opacity-70" style={{ backgroundColor: style.accentColor }} />}
                </div>
              </div>
              {previewEffect === "depth_cutout" && (
                <div className="absolute bottom-0 left-1/2 z-20 h-[72%] w-[58%] -translate-x-1/2">
                  <div className="absolute left-1/2 top-[2%] h-[22%] aspect-square -translate-x-1/2 rounded-full bg-gradient-to-br from-zinc-300 to-zinc-600 shadow-xl" />
                  <div className="absolute bottom-0 left-1/2 h-[80%] w-full -translate-x-1/2 rounded-t-[48%] bg-gradient-to-r from-zinc-700 via-zinc-300 to-zinc-700 shadow-2xl" />
                </div>
              )}
              <div className="absolute bottom-3 left-3 z-50 rounded-md bg-black/60 px-2 py-1 text-[9px] text-zinc-400">{previewLoading ? "Rendering Remotion…" : exactPreview ? "Exact Remotion frame" : "Style simulation • proses clip untuk preview 1:1"}</div>
            </CanvasPreviewFrame>
          </div>
        </div>

        <div className="space-y-4">
          <Section title="Visual Mode">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {([
                ["auto", "AI Auto", "AI pilih mode terbaik"],
                ["hero_punch", "Hero Punch", "Hero center + vignette"],
                ["depth_cutout", "Depth Cutout", "Teks di belakang subjek"],
                ["side_rail", "Side Rail", "Label editorial sisi"],
                ["float_track", "Float Track", "Bob mengikuti orang"],
                ["smart_gap", "Smart Gap", "Auto isi ruang kosong"],
                ["orbit_halo", "Orbit Halo", "Orbit di sekitar kepala"],
                ["z_parallax", "Z Parallax", "Scale depth person"],
                ["word_cascade", "Word Cascade", "Kata-per-kata kinetic"],
                ["split_impact", "Split Impact", "Dua warna slam split"],
                ["type_pulse", "Type Pulse", "Typewriter + pulse"],
                ["sticker_pop", "Sticker Pop", "Comic sticker rotate"],
                ["mirror_echo", "Mirror Echo", "Ghost echo trail"],
              ] as const).map(([value, label, desc]) => (
                <button key={value} type="button" onClick={() => update("effectMode", value)} className={cn("rounded-xl border p-3 text-left transition-all", style.effectMode === value ? "border-emerald-500 bg-emerald-500/10" : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700")}>
                  <p className={cn("text-xs font-semibold", style.effectMode === value ? "text-emerald-300" : "text-zinc-300")}>{label}</p>
                  <p className="mt-1 text-[10px] text-zinc-600">{desc}</p>
                </button>
              ))}
            </div>
          </Section>

          <Section title="Animation &amp; Font">
            <div className="grid grid-cols-2 gap-3">
              <label className="space-y-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Animation
                <select value={style.animation} onChange={(e) => update("animation", e.target.value as TextEmphasisStyle["animation"])} className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-2 text-xs font-normal normal-case text-zinc-200 outline-none focus:border-emerald-500/60">
                  <option value="rise">Rise</option><option value="impact">Impact</option><option value="slide">Slide</option><option value="static_glitch">Static Glitch</option><option value="glow">Glow</option><option value="elastic">Elastic</option><option value="blur_in">Blur In</option><option value="flip_y">Flip Y</option>
                </select>
              </label>
              <label className="space-y-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Font
                <select value={style.fontFamily} onChange={(e) => update("fontFamily", e.target.value)} className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-2 text-xs font-normal normal-case text-zinc-200 outline-none focus:border-emerald-500/60">
                  {FONT_OPTIONS.map((font) => <option key={font} value={font}>{font}</option>)}
                </select>
              </label>
            </div>
          </Section>

          <Section title="Layout &amp; Sizing">
            <div className="grid grid-cols-2 gap-3">
              <SliderField label="Font Size" value={style.fontSize} min={32} max={160} suffix="px" onChange={(value) => update("fontSize", value)} />
              <SliderField label="Position" value={style.positionY} min={12} max={88} suffix="%" onChange={(value) => update("positionY", value)} />
              <SliderField label="Max Width" value={style.maxWidthPct} min={35} max={96} suffix="%" onChange={(value) => update("maxWidthPct", value)} />
              <SliderField label="Mask Feather" value={style.maskFeather} min={1} max={31} suffix="px" step={2} onChange={(value) => update("maskFeather", value % 2 === 0 ? value + 1 : value)} />
            </div>
          </Section>

          <Section title="Colors">
            <div className="grid grid-cols-2 gap-3">
              <ColorField label="Text" value={style.color} onChange={(value) => update("color", value)} />
              <ColorField label="Accent" value={style.accentColor} onChange={(value) => update("accentColor", value)} />
              <ColorField label="Stroke" value={style.strokeColor} onChange={(value) => update("strokeColor", value)} />
              <ColorField label="Shadow" value={style.shadowColor} onChange={(value) => update("shadowColor", value)} />
            </div>
          </Section>

          <Section title="Effects">
            <div className="grid grid-cols-3 gap-2">
              <MiniToggle label="Uppercase" checked={style.uppercase} onChange={(value) => update("uppercase", value)} />
              <MiniToggle label="Stroke" checked={style.strokeEnabled} onChange={(value) => update("strokeEnabled", value)} />
              <MiniToggle label="Shadow" checked={style.shadowEnabled} onChange={(value) => update("shadowEnabled", value)} />
            </div>
          </Section>

          {/* Effect-specific tuning sliders (conditional) */}
          {previewEffect === "float_track" && (
            <Section title="Float Track Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Bob Speed" value={style.floatSpeed ?? 1.2} min={0.5} max={3.0} step={0.1} suffix="x" onChange={(value) => update("floatSpeed", value)} />
              </div>
            </Section>
          )}
          {previewEffect === "smart_gap" && (
            <Section title="Smart Gap Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Avoid Padding" value={style.avoidPadding ?? 40} min={10} max={120} suffix="px" onChange={(value) => update("avoidPadding", value)} />
              </div>
            </Section>
          )}
          {previewEffect === "orbit_halo" && (
            <Section title="Orbit Halo Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Orbit Radius" value={style.aroundHeadRadius ?? 60} min={30} max={120} suffix="%" onChange={(value) => update("aroundHeadRadius", value)} />
              </div>
            </Section>
          )}
          {previewEffect === "z_parallax" && (
            <Section title="Z Parallax Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Depth Intensity" value={style.depthIntensity ?? 0.5} min={0.1} max={1.0} step={0.05} suffix="" onChange={(value) => update("depthIntensity", value)} />
                <SliderField label="Parallax Scale" value={style.depthParallax ?? 0.35} min={0.05} max={1.0} step={0.05} suffix="" onChange={(value) => update("depthParallax", value)} />
                <SliderField label="Fade Duration" value={style.depthFade ?? 0.45} min={0.1} max={1.5} step={0.05} suffix="s" onChange={(value) => update("depthFade", value)} />
              </div>
              <p className="mt-2 text-[11px] text-zinc-500">Depth Intensity mengatur kekuatan parallax; Parallax Scale mengatur jarak fg/bg; Fade Duration mengatur transisi masuk/keluar teks.</p>
            </Section>
          )}
          {previewEffect === "word_cascade" && (
            <Section title="Word Cascade Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Word Stagger" value={style.kineticStagger ?? 5} min={1} max={18} suffix="f" onChange={(value) => update("kineticStagger", value)} />
              </div>
            </Section>
          )}
          {previewEffect === "mirror_echo" && (
            <Section title="Mirror Echo Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Echo Offset" value={style.echoOffset ?? 10} min={4} max={28} suffix="px" onChange={(value) => update("echoOffset", value)} />
              </div>
            </Section>
          )}
          {previewEffect === "sticker_pop" && (
            <Section title="Sticker Pop Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Angle" value={style.stickerAngle ?? -6} min={-18} max={18} suffix="°" onChange={(value) => update("stickerAngle", value)} />
              </div>
            </Section>
          )}
          {previewEffect === "type_pulse" && (
            <Section title="Type Pulse Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Type Speed" value={style.typeSpeed ?? 1.4} min={0.5} max={3} step={0.1} suffix="x" onChange={(value) => update("typeSpeed", value)} />
              </div>
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}

function SliderField({ label, value, min, max, suffix = "", step = 1, onChange }: { label: string; value: number; min: number; max: number; suffix?: string; step?: number; onChange: (value: number) => void }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
      <RangeSlider label={label} value={value} min={min} max={max} step={step} suffix={suffix} onChange={onChange} />
    </div>
  );
}

function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-950/40 p-2.5"><input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="h-7 w-9 cursor-pointer rounded border-0 bg-transparent" /><span><span className="block text-[9px] font-semibold uppercase tracking-wider text-zinc-500">{label}</span><span className="text-[10px] text-zinc-300">{value}</span></span></label>;
}

function MiniToggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <button type="button" onClick={() => onChange(!checked)} className={cn("rounded-lg border px-2 py-2 text-[10px] font-medium transition-colors", checked ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-300" : "border-zinc-800 text-zinc-500")}>{label}</button>;
}

// ─── Presets Tab ─────────────────────────────────────────────────────────────

function PresetsTab({
  hookStyle,
  subtitleStyle,
  textEmphasisStyle,
  watermarkStyle = DEFAULT_WATERMARK_STYLE,
  ctaStyle = DEFAULT_CTA_STYLE,
  brollStyle,
  onHookChange,
  onSubtitleChange,
  onTextEmphasisChange,
  onWatermarkChange,
  onCtaChange,
  onBrollChange,
  onPresetLoad,
  externalActiveId,
  onPresetSelect,
}: {
  hookStyle: HookStyle;
  subtitleStyle: SubtitleStyle;
  textEmphasisStyle: TextEmphasisStyle;
  watermarkStyle?: WatermarkStyle;
  ctaStyle?: CtaStyle;
  brollStyle?: Record<string, any>;
  onHookChange: (s: HookStyle) => void;
  onSubtitleChange: (s: SubtitleStyle) => void;
  onTextEmphasisChange: (s: TextEmphasisStyle) => void;
  onWatermarkChange?: (s: WatermarkStyle) => void;
  onCtaChange?: (s: CtaStyle) => void;
  onBrollChange?: (b: Record<string, any>) => void;
  onPresetLoad?: (preset: Preset) => void;
  externalActiveId?: number | null;
  onPresetSelect?: (id: number) => void;
}) {
  const [userPresets, setUserPresets] = useState<Preset[]>([]);
  const [loading, setLoading] = useState(true);
  const [saveName, setSaveName] = useState("");
  const [saveSlug, setSaveSlug] = useState("");
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [activePresetId, setActivePresetId] = useState<number | null>(externalActiveId ?? null);

  // Sync from external
  useEffect(() => { if (externalActiveId !== undefined) setActivePresetId(externalActiveId); }, [externalActiveId]);

  useEffect(() => {
    presetsApi.list().then((list) => { setUserPresets(list); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  function loadPreset(preset: Preset) {
    onHookChange({ ...DEFAULT_HOOK_STYLE, ...preset.hook_style } as HookStyle);
    onSubtitleChange({ ...DEFAULT_SUBTITLE_STYLE, ...preset.subtitle_style } as SubtitleStyle);
    if (preset.text_emphasis_style) onTextEmphasisChange(normaliseTextEmphasisStyle(preset.text_emphasis_style));
    if (preset.watermark_style && onWatermarkChange) onWatermarkChange({ ...DEFAULT_WATERMARK_STYLE, ...preset.watermark_style });
    if (preset.cta_style && onCtaChange) onCtaChange(normaliseCtaStyle(preset.cta_style));
    if (preset.broll_style && onBrollChange) onBrollChange(preset.broll_style);
    if (onPresetLoad) onPresetLoad(preset);
    setActivePresetId(preset.id);
    if (onPresetSelect) onPresetSelect(preset.id);
    setStatusMsg(`Loaded "${preset.name}" (${preset.slug || `preset-${preset.id}`})`);
    setTimeout(() => setStatusMsg(""), 2500);
  }

  async function handleSave() {
    if (!saveName.trim()) return;
    setSaving(true);
    try {
      const res = await presetsApi.create(
        saveName.trim(),
        hookStyle,
        subtitleStyle,
        textEmphasisStyle,
        watermarkStyle,
        ctaStyle,
        saveSlug.trim() || undefined,
        brollStyle || {}
      );
      setSaveName("");
      setSaveSlug("");
      setStatusMsg(`Berhasil menyimpan preset dengan slug: ${res.slug || saveName.trim()}`);
      setTimeout(() => setStatusMsg(""), 3000);
      const list = await presetsApi.list();
      setUserPresets(list);
    } catch { setStatusMsg("Gagal menyimpan preset"); }
    finally { setSaving(false); }
  }

  async function handleDelete(id: number, name: string) {
    if (!(await confirmDialog({ title: "Hapus Preset?", message: `Preset "${name}" akan dihapus permanen.`, confirmText: "Hapus", danger: true }))) return;
    try {
      await presetsApi.remove(id);
      setUserPresets((prev) => prev.filter((p) => p.id !== id));
      setStatusMsg(`Preset "${name}" dihapus`);
      setTimeout(() => setStatusMsg(""), 2000);
    } catch { setStatusMsg("Gagal menghapus"); }
  }

  function copyPresetCommand(slug: string) {
    const cmd = `--preset ${slug}`;
    navigator.clipboard.writeText(cmd);
    setStatusMsg(`Copied: "${cmd}" ke clipboard!`);
    setTimeout(() => setStatusMsg(""), 2500);
  }

  return (
    <div className="h-full p-5 overflow-y-auto">
      {/* Save current as preset */}
      <div className="mb-6 bg-zinc-900/60 border border-zinc-800 p-4 rounded-xl">
        <h3 className="text-xs font-semibold text-zinc-200 mb-3 flex items-center gap-2">
          <Save className="h-3.5 w-3.5 text-emerald-400" />Simpan Style Saat Ini Sebagai Preset Baru
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-3">
          <div>
            <label className="block text-[10px] text-zinc-400 font-medium mb-1">Nama Preset</label>
            <input
              type="text"
              value={saveName}
              onChange={(e) => {
                const newName = e.target.value;
                setSaveName(newName);
                if (!saveSlug || saveSlug === saveName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "")) {
                  setSaveSlug(newName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, ""));
                }
              }}
              onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), handleSave())}
              placeholder="Contoh: Viral Gaming 01..."
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50"
            />
          </div>
          <div>
            <label className="block text-[10px] text-zinc-400 font-medium mb-1">Slug Telegram / CLI (Opsional)</label>
            <input
              type="text"
              value={saveSlug}
              onChange={(e) => setSaveSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
              onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), handleSave())}
              placeholder="contoh: slug-presets-01"
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50 font-mono text-xs"
            />
          </div>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-zinc-500">
            <span className="text-zinc-400 font-medium">Layers:</span>
            <span className="bg-zinc-800 px-1.5 py-0.5 rounded text-zinc-300">Hook</span>
            <span className="bg-zinc-800 px-1.5 py-0.5 rounded text-zinc-300">Subtitles</span>
            <span className={cn("px-1.5 py-0.5 rounded", textEmphasisStyle?.effectMode && (textEmphasisStyle.effectMode as string) !== "off" ? "bg-emerald-500/20 text-emerald-300" : "bg-zinc-800/60 text-zinc-500")}>AI Text</span>
            <span className={cn("px-1.5 py-0.5 rounded", watermarkStyle?.enabled ? "bg-emerald-500/20 text-emerald-300" : "bg-zinc-800/60 text-zinc-500")}>Watermark</span>
            <span className={cn("px-1.5 py-0.5 rounded", ctaStyle?.enabled ? "bg-emerald-500/20 text-emerald-300" : "bg-zinc-800/60 text-zinc-500")}>CTA</span>
            <span className={cn("px-1.5 py-0.5 rounded", brollStyle?.enabled ? "bg-amber-500/20 text-amber-300" : "bg-zinc-800/60 text-zinc-500")}>B-roll</span>
            <span className={cn("px-1.5 py-0.5 rounded", brollStyle?.autogrid_enabled ? "bg-cyan-500/20 text-cyan-300" : "bg-zinc-800/60 text-zinc-500")}>Auto-Grid</span>
          </div>
          <Button type="button" size="sm" loading={saving} onClick={handleSave} icon={<Save className="h-3.5 w-3.5" />}>Simpan Preset</Button>
        </div>
        {statusMsg && <p className="text-[11px] text-emerald-400 mt-2 font-medium">{statusMsg}</p>}
      </div>

      {/* Preset list */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-semibold text-zinc-200 flex items-center gap-2">
            <Bookmark className="h-3.5 w-3.5 text-emerald-400" />Daftar Preset Tersimpan ({userPresets.length})
          </h3>
          <span className="text-[10px] text-zinc-500">Klik slug untuk salin command Telegram / CLI</span>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 py-4"><div className="h-4 w-4 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin" /><span className="text-xs text-zinc-500">Memuat daftar preset...</span></div>
        ) : userPresets.length === 0 ? (
          <div className="text-center py-8 border border-dashed border-zinc-800 rounded-xl bg-zinc-900/30">
            <Bookmark className="h-6 w-6 text-zinc-700 mx-auto mb-2" />
            <p className="text-xs text-zinc-400 font-medium">Belum ada preset yang disimpan</p>
            <p className="text-[10px] text-zinc-600 mt-1">Atur Hook, Subtitles, AI Text, Watermark, CTA, & B-roll, lalu simpan di sini</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {userPresets.map((p) => {
              const slugStr = p.slug || `preset-${p.id}`;
              const hasTextEmp = p.text_emphasis_style && p.text_emphasis_style.effectMode && p.text_emphasis_style.effectMode !== "off";
              const hasWatermark = p.watermark_style && p.watermark_style.enabled;
              const hasCta = p.cta_style && p.cta_style.enabled;
              const hasBroll = p.broll_style && p.broll_style.enabled;
              const hasAutoGrid = p.broll_style && p.broll_style.autogrid_enabled;
              const hasAutopost = p.autopost_style && p.autopost_style.enabled;

              return (
                <div key={p.id} className={cn("relative group rounded-xl border p-3.5 transition-all flex flex-col justify-between",
                  activePresetId === p.id
                    ? "border-emerald-500 bg-emerald-500/8 ring-1 ring-emerald-500/20 shadow-lg shadow-emerald-500/5"
                    : "border-zinc-800 bg-zinc-900/60 hover:border-emerald-500/40")}>
                  <div>
                    <div className="flex items-start justify-between gap-2 mb-1.5">
                      <h4 className={cn("text-sm font-medium truncate", activePresetId === p.id ? "text-emerald-300 font-semibold" : "text-zinc-200")}>{p.name}</h4>
                      <button type="button" onClick={() => handleDelete(p.id, p.name)} title="Hapus preset" className="p-1 rounded text-zinc-600 hover:text-red-400 hover:bg-zinc-800 opacity-0 group-hover:opacity-100 transition-all shrink-0">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>

                    {/* Slug Badge with Copy button */}
                    <div className="mb-2.5 flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => copyPresetCommand(slugStr)}
                        title="Klik untuk copy --preset command"
                        className="inline-flex items-center gap-1 text-[10px] font-mono bg-zinc-800 hover:bg-zinc-700 text-emerald-400 hover:text-emerald-300 px-2 py-0.5 rounded border border-zinc-700 hover:border-emerald-500/40 transition-colors"
                      >
                        <code>--preset {slugStr}</code>
                        <Copy className="h-2.5 w-2.5 opacity-60" />
                      </button>
                      {activePresetId === p.id && <span className="text-[8px] bg-emerald-500/20 text-emerald-400 font-bold uppercase px-1.5 py-0.5 rounded-full">Active</span>}
                    </div>

                    {/* Styles Summary */}
                    <div className="space-y-1 text-[10px] text-zinc-400 mb-3 bg-zinc-950/40 p-2 rounded-lg border border-zinc-800/50">
                      <p className="flex justify-between"><span className="text-zinc-500">Hook:</span><span className="text-zinc-300 font-medium truncate max-w-[120px]">{(p.hook_style as any)?.animation?.replace(/_/g, " ") || "default"}</span></p>
                      <p className="flex justify-between"><span className="text-zinc-500">Subtitle:</span><span className="text-zinc-300 font-medium truncate max-w-[120px]">{(p.subtitle_style as any)?.stylePreset || "clean"}</span></p>
                      <div className="flex flex-wrap items-center gap-1 pt-1 border-t border-zinc-800/60 mt-1">
                        {hasTextEmp && <span className="text-[8px] bg-emerald-500/10 text-emerald-400 px-1 py-0.2 rounded border border-emerald-500/20">AI Text</span>}
                        {hasWatermark && <span className="text-[8px] bg-blue-500/10 text-blue-400 px-1 py-0.2 rounded border border-blue-500/20">Watermark</span>}
                        {hasCta && <span className="text-[8px] bg-purple-500/10 text-purple-400 px-1 py-0.2 rounded border border-purple-500/20">CTA</span>}
                        {hasBroll && <span className="text-[8px] bg-amber-500/10 text-amber-400 px-1 py-0.2 rounded border border-amber-500/20">B-roll</span>}
                        {hasAutoGrid && <span className="text-[8px] bg-cyan-500/10 text-cyan-400 px-1 py-0.2 rounded border border-cyan-500/20">Auto-Grid</span>}
                        {hasAutopost && <span className="text-[8px] bg-rose-500/10 text-rose-400 px-1 py-0.2 rounded border border-rose-500/20">Auto-Post</span>}
                      </div>
                      {p.owner_email && <p className="text-[9px] text-zinc-500 pt-0.5">By: {p.owner_name || p.owner_email}</p>}
                    </div>
                  </div>

                  <div>
                    <button type="button" onClick={() => loadPreset(p)} className={cn("w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg border text-[11px] font-medium transition-colors",
                      activePresetId === p.id
                        ? "border-emerald-500 bg-emerald-500/20 text-emerald-300 shadow-sm"
                        : "border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10")}>
                      <Download className="h-3 w-3" />{activePresetId === p.id ? "Preset Aktif" : "Load Preset"}
                    </button>
                    {p.created_at && <p className="text-[8px] text-zinc-600 mt-1.5 text-center">{new Date(p.created_at).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" })}</p>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Hook Preview Renderer (matches Remotion output visually) ────────────────

export function HookPreviewRenderer({
  style,
  customText,
  scale = 1.0,
}: {
  style: HookStyle;
  customText?: string;
  scale?: number;
}) {
  const text = customText || style.text || getHookPreviewSample(style.animation);
  const fontSize = Math.max(style.fontSize * 0.32 * scale, 10);
  const fontFamily = style.fontFamily === "monospace" ? "monospace" : `'${style.fontFamily}', sans-serif`;
  const fontWeight = Number(style.fontWeight);
  const fontStyle = style.italic ? ("italic" as const) : ("normal" as const);

  const baseTextStyle: React.CSSProperties = {
    fontSize,
    fontWeight,
    fontFamily,
    fontStyle,
    letterSpacing: style.letterSpacing,
    lineHeight: style.lineHeight,
    textTransform: style.uppercase ? "uppercase" : "none",
    textAlign: style.textAlign,
    maxWidth: "90%",
    whiteSpace: "pre-line",
    wordBreak: "break-word",
    paintOrder: style.strokeEnabled ? "stroke" : undefined,
    WebkitTextStroke: style.strokeEnabled ? `${Math.max(style.strokeWidth * 0.32, 0.7)}px ${style.strokeColor}` : undefined,
  };

  const textShadow = [
    style.shadowEnabled ? `${style.shadowX}px ${style.shadowY}px ${style.shadowBlur}px ${style.shadowColor}` : "",
    style.glowEnabled ? `0 0 ${style.glowSize}px ${style.glowColor}` : "",
  ].filter(Boolean).join(", ") || undefined;

  const colorStyle: React.CSSProperties = style.gradientEnabled
    ? { background: `linear-gradient(${style.gradientAngle}deg, ${style.gradientFrom}, ${style.gradientTo})`, WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }
    : { color: style.color };

  const boxStyle: React.CSSProperties = style.boxEnabled
    ? { backgroundColor: `${style.boxColor}${Math.round(style.boxOpacity * 255).toString(16).padStart(2, "0")}`, padding: style.boxPadding * 0.4, borderRadius: style.boxRadius }
    : {};

  const posTop = `${style.positionY}%`;

  switch (style.animation) {
    case "news_viralin_badge": {
      const cardBg = style.boxColor || "#EAB308";
      const badgeBg = style.lineColor || "#1D4ED8";
      const badgeTitle = style.badgeText || "#VIRALIN";
      const badgeSub = (style as any).badgeSubText || "";
      const showBadge = style.badgeEnabled !== false;
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {/* White paper rotated card behind */}
            <div style={{ position: "absolute", inset: -4, background: "#FFFFFF", transform: "rotate(-3deg)", borderRadius: 8, boxShadow: "0 14px 30px rgba(0,0,0,0.45)" }} />
            {/* Main yellow card */}
            <div style={{ position: "relative", background: cardBg, padding: "28px 20px 20px 20px", borderRadius: 8, boxShadow: "0 16px 36px rgba(0,0,0,0.5)" }}>
              {/* Tilted Blue Badge */}
              {showBadge && (
                <div style={{ position: "absolute", top: -20, left: "50%", transform: "translateX(-50%) rotate(-3.5deg)", background: badgeBg, borderRadius: 6, padding: "4px 14px", boxShadow: "0 6px 16px rgba(0,0,0,0.4)", border: "1.5px solid rgba(255,255,255,0.2)", display: "flex", flexDirection: "column", alignItems: "center" }}>
                  <span style={{ color: "#FACC15", fontFamily: "'Montserrat', sans-serif", fontWeight: 900, fontSize: 13, fontStyle: "italic", lineHeight: 1.1, textTransform: "uppercase" }}>{badgeTitle}</span>
                  {badgeSub ? <span style={{ color: "#FFFFFF", fontFamily: "'Inter', sans-serif", fontWeight: 700, fontSize: 8, lineHeight: 1 }}>{badgeSub}</span> : null}
                </div>
              )}
              <p style={{ ...baseTextStyle, color: style.color || "#09090B", fontSize: Math.max(fontSize * 0.78, 12), fontWeight: 900, textAlign: "center", lineHeight: 1.2, marginTop: showBadge ? 4 : 0 }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "news_portal_pantau": {
      const cardBg = style.boxColor || "#FFFFFF";
      const accentColor = style.lineColor || "#DC2626";
      const categoryTag = style.badgeText || "INTERNASIONAL";
      const footerLabel = style.footerText || "READ MORE AT chatgpt.com";
      const showBadge = style.badgeEnabled !== false;
      const showFooter = style.footerEnabled !== false;
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ position: "relative", background: cardBg, borderRadius: "10px 10px 0 0", padding: "18px 18px 14px 18px", boxShadow: "0 18px 40px rgba(0,0,0,0.5)", borderBottom: `4px solid ${accentColor}` }}>
              {showBadge && (
                <div style={{ display: "inline-block", background: accentColor, color: "#FFFFFF", fontFamily: "'Inter', sans-serif", fontWeight: 900, fontSize: 10, letterSpacing: "0.05em", textTransform: "uppercase", padding: "3px 8px", borderRadius: 3, marginBottom: 8 }}>{categoryTag}</div>
              )}
              <p style={{ ...baseTextStyle, color: style.color || "#09090B", fontSize: Math.max(fontSize * 0.76, 12), fontWeight: 900, textAlign: "left", lineHeight: 1.18, textTransform: "uppercase" }}>{text}</p>
              {showFooter && (
                <div style={{ marginTop: 10, paddingTop: 6, borderTop: "1px solid rgba(0,0,0,0.08)", color: "#71717A", fontSize: 8, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.08em" }}>{footerLabel}</div>
              )}
              {/* Bottom speech notch */}
              <div style={{ position: "absolute", bottom: -12, right: 28, width: 0, height: 0, borderLeft: "10px solid transparent", borderRight: "10px solid transparent", borderTop: `12px solid ${accentColor}` }} />
            </div>
          </div>
        </>
      );
    }

    case "news_offset_box": {
      const cardBg = style.boxColor || "#DC2626";
      const offsetColor = style.lineColor || "#FFFFFF";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-5 right-5" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {/* White offset border sticking out top-left */}
            <div style={{ position: "absolute", top: -8, left: -8, width: "65%", height: "80%", borderTop: `3px solid ${offsetColor}`, borderLeft: `3px solid ${offsetColor}` }} />
            {/* Main red box */}
            <div style={{ position: "relative", background: cardBg, padding: "18px 18px", boxShadow: "0 16px 36px rgba(0,0,0,0.5)" }}>
              <p style={{ ...baseTextStyle, color: style.color || "#FFFFFF", fontSize: Math.max(fontSize * 0.78, 12), fontWeight: 900, textAlign: "center", lineHeight: 1.22 }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "brutalist_bracket": {
      const cardBg = style.boxColor || "#FFFFFF";
      const bracketColor = style.lineColor || "#000000";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-5 right-5" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {/* Left bracket */}
            <div style={{ position: "absolute", top: -10, left: -10, bottom: -10, width: 24, borderTop: `5px solid ${bracketColor}`, borderLeft: `5px solid ${bracketColor}`, borderBottom: `5px solid ${bracketColor}` }} />
            <div style={{ position: "relative", background: cardBg, padding: "18px 20px", boxShadow: "0 16px 36px rgba(0,0,0,0.5)" }}>
              <p style={{ ...baseTextStyle, color: style.color || "#09090B", fontSize: Math.max(fontSize * 0.78, 12), fontWeight: 900, textAlign: "left", lineHeight: 1.2 }}>
                {text.split(/(!!+|!\s*!)/g).map((part, idx) => {
                  if (part.includes("!")) return <span key={idx} style={{ color: "#EF4444", fontWeight: 900 }}> {part}</span>;
                  return <span key={idx}>{part}</span>;
                })}
              </p>
            </div>
          </div>
        </>
      );
    }

    case "quote_strip_tape": {
      const quoteBg = style.lineColor || "#0D9488";
      const tapeBg = style.boxColor || "#FFFFFF";
      const words = text.split(/\s+/).filter(Boolean);
      const lines: string[] = [];
      let cur = "";
      for (const w of words) {
        if ((cur + " " + w).trim().split(" ").length > 3) {
          lines.push(cur);
          cur = w;
        } else {
          cur = cur ? `${cur} ${w}` : w;
        }
      }
      if (cur) lines.push(cur);
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-5 right-5 flex flex-col items-start" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ background: quoteBg, color: "#FFFFFF", borderRadius: 3, padding: "4px 6px", marginBottom: 6, display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
              <Quote className="w-3.5 h-3.5 fill-current" />
            </div>
            <div className="flex flex-col items-start gap-1.5">
              {lines.map((line, lIdx) => (
                <span key={lIdx} style={{ background: tapeBg, color: style.color || "#09090B", padding: "4px 12px", fontFamily, fontSize: Math.max(fontSize * 0.72, 11), fontWeight: 900, textTransform: "uppercase", letterSpacing: "0.04em", boxShadow: "0 6px 16px rgba(0,0,0,0.4)" }}>
                  {line}
                </span>
              ))}
            </div>
          </div>
        </>
      );
    }

    case "podcast_lower_third": {
      const accent = style.lineColor || "#16F2B3";
      const showBadge = style.badgeEnabled !== false;
      const badgeLabel = style.badgeText || "ON AIR";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-3 right-3 animate-[podcastLowerPreview_2.8s_ease-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{
              display: "grid",
              gridTemplateColumns: showBadge ? "auto 1fr" : "1fr",
              gap: 8,
              alignItems: "center",
              background: "linear-gradient(90deg, rgba(6,17,31,0.94), rgba(20,28,44,0.78))",
              border: `1px solid ${accent}55`,
              borderLeft: `5px solid ${accent}`,
              borderRadius: 12,
              boxShadow: `0 12px 30px rgba(0,0,0,0.35), 0 0 18px ${accent}33`,
              padding: "10px 12px",
            }}>
              {showBadge && (
                <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "center" }}>
                  <span style={{ width: 8, height: 8, borderRadius: 99, background: accent, boxShadow: `0 0 12px ${accent}`, animation: "podcastOnAirPulse_1s ease-in-out infinite" }} />
                  <span style={{ color: accent, fontSize: 8, fontWeight: 900, letterSpacing: 0 }}>{badgeLabel}</span>
                </div>
              )}
              <p style={{ ...baseTextStyle, color: style.color, fontSize: Math.max(fontSize * 0.86, 12), textAlign: "left", lineHeight: 1.02, textShadow }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "quote_card": {
      const cardColor = `${style.boxColor}${Math.round((style.boxOpacity || 0.96) * 255).toString(16).padStart(2, "0")}`;
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4 animate-[quoteCardPreview_3s_ease-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{
              position: "relative",
              background: cardColor,
              borderRadius: 14,
              padding: "20px 18px 16px",
              boxShadow: "0 16px 30px rgba(0,0,0,0.38)",
              border: "1px solid rgba(255,255,255,0.72)",
            }}>
              <span style={{ position: "absolute", top: -13, left: 14, color: "#FF4D2D", fontSize: 36, fontFamily: "Georgia, serif", lineHeight: 1 }}>"</span>
              <p style={{ ...baseTextStyle, color: style.color || "#171717", fontSize: Math.max(fontSize * 0.82, 13), lineHeight: 1.12, textShadow: "none" }}>{text}</p>
              <div style={{ width: "38%", height: 3, background: "#FF4D2D", borderRadius: 99, margin: "10px auto 0" }} />
            </div>
          </div>
        </>
      );
    }

    case "waveform_pulse": {
      const bars = Array.from({ length: 13 });
      const waveColor = style.glowColor || style.color || "#14F1D9";
      const showBadge = style.badgeEnabled !== false;
      const badgeLabel = style.badgeText || "LIVE AUDIO";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-x-0 flex flex-col items-center justify-center gap-3 px-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {showBadge && (
              <span style={{ color: waveColor, fontSize: 8, fontWeight: 900, letterSpacing: 1, textTransform: "uppercase" }}>{badgeLabel}</span>
            )}
            <div style={{ display: "flex", gap: 4, height: 34, alignItems: "center" }}>
              {bars.map((_, i) => (
                <span key={i} style={{
                  width: 4,
                  height: 26 + (i % 4) * 6,
                  borderRadius: 99,
                  background: waveColor,
                  boxShadow: `0 0 12px ${waveColor}`,
                  transformOrigin: "center",
                  animation: `waveformBarPreview ${0.72 + (i % 3) * 0.14}s ease-in-out ${i * 0.04}s infinite`,
                }} />
              ))}
            </div>
            <p className="animate-[waveformTextPreview_1.1s_ease-in-out_infinite]" style={{ ...baseTextStyle, ...colorStyle, ...boxStyle, textShadow }}>{text}</p>
          </div>
        </>
      );
    }

    case "breaking_tape": {
      const tapeColor = style.boxColor || "#FFDD2D";
      const showBadge = style.badgeEnabled !== false;
      const badgeLabel = style.badgeText || "HOT TAKE";
      const badgeColor = style.lineColor || "#D71920";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-[-8%] right-[-8%] animate-[breakingTapePreview_2.5s_ease-out_infinite]" style={{ top: posTop, transform: "translateY(-50%) rotate(-4deg)" }}>
            <div style={{
              background: `linear-gradient(90deg, ${tapeColor}, #FFF06A, ${tapeColor})`,
              borderTop: "3px solid rgba(0,0,0,0.92)",
              borderBottom: "3px solid rgba(0,0,0,0.92)",
              boxShadow: "0 18px 28px rgba(0,0,0,0.32)",
              padding: "11px 28px",
              textAlign: "center",
            }}>
              {showBadge && (
                <span style={{ display: "block", color: badgeColor, fontSize: 8, fontWeight: 900, letterSpacing: 0, marginBottom: 2 }}>{badgeLabel}</span>
              )}
              <p style={{ ...baseTextStyle, color: style.color || "#111111", fontSize: Math.max(fontSize * 0.9, 14), lineHeight: 1, textShadow: "none" }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "mic_drop": {
      const accent = style.boxColor || style.gradientTo || "#FF4D7D";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-x-0 flex flex-col items-center justify-center px-4 animate-[micDropPreview_2.5s_cubic-bezier(.2,.85,.25,1)_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{
              position: "relative",
              borderRadius: 999,
              border: `3px solid ${accent}`,
              boxShadow: `0 0 26px ${accent}66, inset 0 0 18px rgba(255,255,255,0.08)`,
              padding: "18px 22px",
              background: "rgba(5,5,7,0.74)",
            }}>
              <span style={{ position: "absolute", left: "50%", bottom: -16, width: 46, height: 4, transform: "translateX(-50%)", borderRadius: 99, background: accent, boxShadow: `0 0 18px ${accent}` }} />
              <p style={{ ...baseTextStyle, ...colorStyle, textShadow, fontSize: Math.max(fontSize * 0.82, 14), lineHeight: 1.02 }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "split_panel": {
      const accent = style.lineColor || "#38BDF8";
      const panel = `${style.boxColor || "#0F172A"}${Math.round((style.boxOpacity || 0.86) * 255).toString(16).padStart(2, "0")}`;
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4 animate-[splitPanelPreview_2.6s_ease-in-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ display: "grid", gridTemplateColumns: style.badgeEnabled ? "48px 1fr" : "1fr", borderRadius: 12, overflow: "hidden", background: panel, boxShadow: `0 16px 32px rgba(0,0,0,0.34), 0 0 18px ${accent}33`, border: `1px solid ${accent}44` }}>
              {style.badgeEnabled && <div style={{ background: accent, color: "#06111F", display: "grid", placeItems: "center", fontSize: 8, fontWeight: 900, writingMode: "vertical-rl", textTransform: "uppercase", letterSpacing: 1 }}>{style.badgeText || "POINT"}</div>}
              <div style={{ padding: "16px 18px", position: "relative" }}>
                {style.decorativeElements && <span style={{ position: "absolute", left: 16, right: 16, bottom: 8, height: 2, borderRadius: 99, background: accent, opacity: 0.8 }} />}
                <p style={{ ...baseTextStyle, ...colorStyle, textShadow, fontSize: Math.max(fontSize * 0.9, 14), textAlign: "left" }}>{text}</p>
              </div>
            </div>
          </div>
        </>
      );
    }

    case "kinetic_stack": {
      const accent = style.boxColor || "#F97316";
      const words = text.split(/\s+/).filter(Boolean).slice(0, 5);
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-x-4 flex flex-col items-center gap-1.5 animate-[kineticStackPreview_2.4s_ease-in-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {words.map((word, i) => (
              <span key={`${word}-${i}`} style={{ ...baseTextStyle, color: style.color, background: i % 2 === 0 ? accent : "#F8FAFC", padding: "3px 12px", borderRadius: 5, boxShadow: `5px 5px 0 ${style.lineColor || "#111827"}`, transform: `translateX(${(i % 2 === 0 ? -1 : 1) * Math.min(24, 7 + i * 4)}px) rotate(${i % 2 === 0 ? -1.5 : 1.5}deg)`, fontSize: Math.max(fontSize * 0.82, 14), lineHeight: 1 }}>
                {word}
              </span>
            ))}
          </div>
        </>
      );
    }

    case "glass_flash": {
      const accent = style.lineColor || "#C084FC";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4 animate-[glassFlashPreview_2.8s_ease-in-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ position: "relative", overflow: "hidden", borderRadius: 18, padding: "22px 18px", background: `${style.boxColor || "#FFFFFF"}${Math.round((style.boxOpacity || 0.14) * 255).toString(16).padStart(2, "0")}`, border: `1px solid ${accent}55`, boxShadow: `0 18px 36px rgba(0,0,0,0.35), 0 0 22px ${accent}33`, backdropFilter: "blur(10px)" }}>
              {style.decorativeElements && <span className="absolute inset-y-[-20%] w-12 animate-[signalScanLine_2s_ease-in-out_infinite]" style={{ left: 0, background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.42), transparent)", transform: "skewX(-18deg)" }} />}
              {style.badgeEnabled && <span style={{ color: accent, fontSize: 8, fontWeight: 900, letterSpacing: 1.5 }}>{style.badgeText || "FOCUS"}</span>}
              <p style={{ ...baseTextStyle, ...colorStyle, textShadow, marginTop: style.badgeEnabled ? 5 : 0 }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "marker_swipe": {
      const accent = style.boxColor || style.lineColor || "#FDE047";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-x-4 flex justify-center" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ position: "relative", padding: "8px 12px" }}>
              {style.decorativeElements && <span className="absolute left-0 right-0 top-1/2 h-[54%] origin-left animate-[markerSwipePreview_2.4s_ease-in-out_infinite]" style={{ background: accent, borderRadius: 8, transform: "translateY(-50%)", opacity: style.boxOpacity || 0.86 }} />}
              <p className="relative" style={{ ...baseTextStyle, color: style.color, textShadow, fontSize: Math.max(fontSize, 16) }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "signal_scan": {
      const accent = style.lineColor || "#22D3EE";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4 animate-[signalScanPreview_2.5s_ease-in-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ position: "relative", overflow: "hidden", padding: "18px 18px", borderRadius: 10, border: `1px solid ${accent}66`, background: `${style.boxColor || "#0EA5E9"}${Math.round((style.boxOpacity || 0.16) * 255).toString(16).padStart(2, "0")}`, boxShadow: `0 0 22px ${accent}33` }}>
              {style.decorativeElements && <span className="absolute inset-y-0 w-10 animate-[signalScanLine_1.6s_linear_infinite]" style={{ left: 0, background: `linear-gradient(90deg, transparent, ${accent}77, transparent)` }} />}
              {style.badgeEnabled && <span style={{ color: accent, fontSize: 8, fontWeight: 900, letterSpacing: 1.3 }}>{style.badgeText || "SIGNAL"}</span>}
              <p style={{ ...baseTextStyle, ...colorStyle, textShadow, marginTop: style.badgeEnabled ? 4 : 0 }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "comment_reply": {
      const accent = style.lineColor || "#18181B";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-8" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ position: "relative", borderRadius: 14, padding: "14px 16px", background: `${style.boxColor || "#FFFFFF"}${Math.round((style.boxOpacity || 0.98) * 255).toString(16).padStart(2, "0")}`, boxShadow: "0 16px 32px rgba(0,0,0,.32)" }}>
              <span style={{ display: "block", marginBottom: 5, color: `${accent}99`, fontSize: 8, fontWeight: 700 }}>{style.badgeText || "replying to @viewer"}</span>
              <p style={{ ...baseTextStyle, color: style.color || "#18181B", fontSize: Math.max(fontSize * 0.78, 13), textAlign: "left", textShadow: "none" }}>{text}</p>
              <span style={{ position: "absolute", left: 20, bottom: -8, width: 18, height: 18, background: style.boxColor || "#FFFFFF", transform: "rotate(45deg)" }} />
            </div>
          </div>
        </>
      );
    }

    case "search_prompt": {
      const accent = style.lineColor || "#22D3EE";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ display: "grid", gridTemplateColumns: "28px 1fr 26px", alignItems: "center", gap: 8, borderRadius: 999, padding: "10px 13px", background: `${style.boxColor || "#0F172A"}${Math.round((style.boxOpacity || 0.94) * 255).toString(16).padStart(2, "0")}`, border: `1px solid ${accent}66`, boxShadow: `0 0 22px ${accent}22` }}>
              <span style={{ color: accent, fontSize: 17 }}>⌕</span>
              <p style={{ ...baseTextStyle, color: style.color, fontSize: Math.max(fontSize * 0.72, 12), textAlign: "left", textShadow }}> {text}</p>
              <span style={{ color: accent, fontSize: 14 }}>↗</span>
            </div>
          </div>
        </>
      );
    }

    case "countdown_list": {
      const accent = style.boxColor || "#FACC15";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ display: "grid", gridTemplateColumns: "70px 1fr", overflow: "hidden", borderRadius: 12, border: `3px solid ${style.lineColor || "#111827"}`, boxShadow: `7px 7px 0 ${style.lineColor || "#111827"}` }}>
              <span style={{ display: "grid", placeItems: "center", background: accent, color: "#111827", fontSize: 28, fontWeight: 1000 }}>{style.badgeText || "03"}</span>
              <p style={{ ...baseTextStyle, color: style.color || "#111827", background: "#F8FAFC", padding: "14px", fontSize: Math.max(fontSize * 0.74, 13), textAlign: "left", textShadow: "none" }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "pov_stamp": {
      const accent = style.boxColor || "#FB7185";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-x-5" style={{ top: posTop, transform: "translateY(-50%) rotate(-2deg)" }}>
            <span style={{ display: "inline-block", marginBottom: 6, padding: "4px 10px", borderRadius: 6, background: accent, color: "#FFFFFF", fontSize: 11, fontWeight: 1000, letterSpacing: 1 }}>{style.badgeText || "POV"}</span>
            <p style={{ ...baseTextStyle, color: style.color, padding: "12px 15px", border: `2px solid ${accent}`, borderRadius: 8, background: "rgba(18,7,12,.78)", textShadow, fontSize: Math.max(fontSize * 0.86, 14), textAlign: "left" }}>{text}</p>
          </div>
        </>
      );
    }

    case "glitch_rgb": {
      // 3 separate text layers matching FFmpeg: Red(-4+sin(t*15)*3), Cyan(+4-sin(t*15)*3), White(center)
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {/* Red channel — animated offset left */}
            <p className="absolute animate-[glitchRedLayer_0.8s_steps(4)_infinite]" style={{ ...baseTextStyle, color: "#FF0000", opacity: 0.7 }}>{text}</p>
            {/* Cyan channel — animated offset right */}
            <p className="absolute animate-[glitchCyanLayer_0.8s_steps(4)_infinite]" style={{ ...baseTextStyle, color: "#00FFFF", opacity: 0.7 }}>{text}</p>
            {/* Main text on top */}
            <p className="relative" style={{ ...baseTextStyle, ...colorStyle, ...boxStyle, textShadow }}>{text}</p>
          </div>
        </>
      );
    }

    case "shake_neon": {
      // Multiple glow layers + shake matching FFmpeg
      const neonColor = style.color || "#00FFCC";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {/* Glow layer 1: large dim blur */}
            <p className="absolute" style={{ ...baseTextStyle, color: neonColor, opacity: 0.3, filter: "blur(3px)", textShadow: `0 0 12px ${neonColor}, 0 0 24px ${neonColor}` }}>{text}</p>
            {/* Glow layer 2: medium, shaking */}
            <p className="absolute animate-[shakeNeonGlow_1.2s_ease-in-out_infinite]" style={{ ...baseTextStyle, color: neonColor, opacity: 0.5, textShadow: `0 0 6px ${neonColor}, 0 0 12px ${neonColor}` }}>{text}</p>
            {/* Main text: subtle shake */}
            <p className="relative animate-[shakeNeonMain_1.5s_ease-in-out_infinite]" style={{ ...baseTextStyle, color: neonColor, textShadow: `0 0 10px ${neonColor}, 0 0 20px ${neonColor}, 0 0 40px ${neonColor}`, ...boxStyle }}>{text}</p>
          </div>
        </>
      );
    }

    case "cinematic_reveal": {
      // Letterbox bars + dark overlay + elegant slow fade
      const revealColor = style.color || "#FFD700";
      return (
        <>
          {/* Letterbox bars */}
          <div className="absolute top-0 left-0 right-0 z-10" style={{ height: "12%", backgroundColor: "#000" }} />
          <div className="absolute bottom-0 left-0 right-0 z-10" style={{ height: "12%", backgroundColor: "#000" }} />
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4 animate-[cinematicRevealText_3.5s_ease-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <p style={{ ...baseTextStyle, color: revealColor, textShadow: `2px 2px 4px rgba(0,0,0,0.8)${style.glowEnabled ? `, 0 0 ${style.glowSize}px ${style.glowColor}` : ""}`, ...boxStyle }}>{text}</p>
          </div>
        </>
      );
    }

    case "danger_bold": {
      // Red glow behind + main text with thick border + pulse
      const dangerColor = style.color || "#FF2D2D";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4 animate-[dangerPulse_1.2s_ease-in-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {/* Red glow behind */}
            <p className="absolute" style={{ ...baseTextStyle, color: "#FF0000", opacity: 0.4, textShadow: `0 0 10px #FF0000, 0 0 20px #FF0000, 0 0 40px rgba(255,0,0,0.3)` }}>{text}</p>
            {/* Main text with stroke */}
            <p className="relative" style={{ ...baseTextStyle, color: dangerColor, WebkitTextStroke: "1.5px black", textShadow: `0 0 10px #FF0000, 0 0 20px rgba(255,0,0,0.5)`, ...boxStyle }}>{text}</p>
          </div>
        </>
      );
    }

    case "bold_slam": {
      // Bold slam: scale entrance + shake + rotated box
      const boldSlamColor = style.boxColor || "#FFE600";
      const boldSlamStroke = "#16130B";
      const boldSlamText = style.color || "#16130B";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4 animate-[boldSlamPreview_2s_ease-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{
              background: boldSlamColor,
              padding: "20px 36px",
              borderRadius: 16,
              border: `5px solid ${boldSlamStroke}`,
              boxShadow: `8px 8px 0px ${boldSlamStroke}`,
            }}>
              <p style={{ ...baseTextStyle, color: boldSlamText, textTransform: "uppercase" as const }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "typewriter": {
      // Character reveal animation
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <p className="overflow-hidden whitespace-nowrap animate-[typewriterReveal_3s_steps(20)_infinite]" style={{ ...baseTextStyle, ...colorStyle, ...boxStyle, textShadow, borderRight: "2px solid currentColor" }}>{text}</p>
          </div>
        </>
      );
    }

    case "slide_up":
    case "slide_punch_framer": {
      const animClass = style.animation === "slide_up"
        ? "animate-[slideUpPreview_2s_ease-in-out_infinite]"
        : "animate-[slidePunchPreview_2s_ease-out_infinite]";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className={cn("absolute inset-0 flex items-center justify-center px-4", animClass)} style={{ top: posTop, transform: "translateY(-50%)" }}>
            <p style={{ ...baseTextStyle, ...colorStyle, ...boxStyle, textShadow }}>{text}</p>
          </div>
        </>
      );
    }

    case "glitch": {
      // Simple glitch jitter
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4 animate-[glitchJitter_0.5s_steps(2)_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <p style={{ ...baseTextStyle, ...colorStyle, ...boxStyle, textShadow }}>{text}</p>
          </div>
        </>
      );
    }

    case "fade_scale":
    default: {
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4 animate-[fadeScalePreview_2.5s_ease-in-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <p style={{ ...baseTextStyle, ...colorStyle, ...boxStyle, textShadow }}>{text}</p>
          </div>
        </>
      );
    }
  }
}

function HookPresetCard({ preset, active, onClick }: { preset: { id: string; name: string; style: Partial<HookStyle> }; active: boolean; onClick: () => void }) {
  const animation = preset.style.animation || "podcast_lower_third";
  const meta = HOOK_ANIMATION_META[animation] || HOOK_ANIMATION_META.podcast_lower_third;
  const font = preset.style.fontFamily || "Poppins";
  const color = preset.style.gradientEnabled ? preset.style.gradientTo || meta.accent : preset.style.color || meta.accent;
  return (
    <button type="button" onClick={onClick}
      className={cn("group relative min-h-[98px] rounded-lg border p-3 text-left overflow-hidden transition-all",
        active ? "border-emerald-400 bg-emerald-500/10 ring-1 ring-emerald-400/25" : "border-zinc-800 bg-zinc-900/70 hover:border-zinc-600 hover:bg-zinc-900")}>
      <div className="absolute inset-x-0 top-0 h-1" style={{ background: `linear-gradient(90deg, ${meta.accent}, transparent)` }} />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className={cn("text-[12px] font-semibold truncate", active ? "text-emerald-300" : "text-zinc-200")}>{preset.name}</p>
          <p className="mt-0.5 text-[9px] text-zinc-500 truncate">{meta.label} / {font}</p>
        </div>
        <span className="rounded-md px-1.5 py-0.5 text-[8px] font-black" style={{ color, backgroundColor: `${color}18`, border: `1px solid ${color}44` }}>{meta.preview}</span>
      </div>
      <div className="mt-3 flex items-end gap-2">
        <div className="flex-1 min-w-0">
          <div className="h-8 rounded-md border border-white/10 bg-black/30 px-2 flex items-center overflow-hidden">
            <span style={{ color, fontFamily: font === "monospace" ? "monospace" : `'${font}', sans-serif`, fontWeight: Number(preset.style.fontWeight || 800), letterSpacing: 0 }} className="text-[11px] truncate">
              {getHookPreviewSample(animation)}
            </span>
          </div>
        </div>
        <span className="text-[8px] text-zinc-600 group-hover:text-zinc-400">{meta.mood}</span>
      </div>
    </button>
  );
}

function SubtitlePresetCard({ preset, active, onClick }: { preset: { id: string; name: string; style: Partial<SubtitleStyle> }; active: boolean; onClick: () => void }) {
  const transition = preset.style.lineTransition || "word_pop";
  const meta = SUBTITLE_TRANSITION_META[transition] || SUBTITLE_TRANSITION_META.word_pop;
  const font = preset.style.fontFamily || "Poppins";
  const color = preset.style.highlightColor || meta.accent;
  const presetKey = preset.style.stylePreset || "classic";
  const isLightCard = presetKey === "bubble_chat" || presetKey === "breaking_tape" || presetKey === "quote_box" || presetKey === "word_tiles";
  const previewBg = preset.style.bgEnabled === false
    ? "transparent"
    : preset.style.bgColor
      ? `${preset.style.bgColor}${Math.round((preset.style.bgOpacity ?? 0.45) * 255).toString(16).padStart(2, "0")}`
      : "rgba(0,0,0,0.28)";
  const previewRadius = presetKey === "caption_strip" ? 0 : presetKey === "breaking_tape" ? 2 : presetKey === "bubble_chat" || presetKey === "gradient_glass" ? 14 : preset.style.bgRadius ?? 6;
  const previewTransform = presetKey === "breaking_tape" ? "rotate(-1.5deg)" : undefined;
  return (
    <button type="button" onClick={onClick}
      className={cn("group min-h-[92px] rounded-lg border p-3 text-left transition-all",
        active ? "border-emerald-400 bg-emerald-500/10 ring-1 ring-emerald-400/25" : "border-zinc-800 bg-zinc-900/70 hover:border-zinc-600 hover:bg-zinc-900")}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className={cn("text-[12px] font-semibold truncate", active ? "text-emerald-300" : "text-zinc-200")}>{preset.name}</p>
          <p className="mt-0.5 text-[9px] text-zinc-500 truncate">{meta.label} / {font}</p>
        </div>
        <span className="h-5 min-w-5 rounded-full border" style={{ backgroundColor: `${color}22`, borderColor: `${color}66` }} />
      </div>
      <div
        className={cn(
          "relative mt-3 flex flex-wrap items-center justify-center gap-1.5 overflow-hidden border px-2 py-2",
          isLightCard ? "border-black/10" : "border-white/10",
          presetKey === "lower_third" && "justify-start",
        )}
        style={{
          backgroundColor: previewBg,
          borderRadius: previewRadius,
          transform: previewTransform,
          boxShadow: presetKey === "neon_pulse" ? `0 0 22px ${color}44` : undefined,
        }}
      >
        {(presetKey === "editorial_banner" || presetKey === "lower_third" || presetKey === "documentary") && (
          <span className="absolute left-0 top-0 h-full w-1.5" style={{ backgroundColor: color }} />
        )}
        {presetKey === "neon_pulse" && (
          <span className="absolute inset-x-3 top-1 h-0.5 rounded-full" style={{ backgroundColor: color, boxShadow: `0 0 12px ${color}` }} />
        )}
        {presetKey === "bubble_chat" && (
          <span className="absolute bottom-[-5px] left-7 h-3 w-3 rotate-45" style={{ backgroundColor: previewBg }} />
        )}
        {["ini", "kata", "penting"].map((word, index) => (
          <span
            key={word}
            style={{
              color: index === 1 ? color : preset.style.color || "#FFFFFF",
              fontFamily: index === 1 && preset.style.dualStyleEnabled ? `'${preset.style.highlightFontFamily || "Anton"}', sans-serif` : `'${font}', sans-serif`,
              fontWeight: index === 1 ? 900 : Number(preset.style.fontWeight || 700),
              WebkitTextStroke: presetKey === "meme_impact" && index !== 1 ? "0.5px #000" : undefined,
              textShadow: presetKey === "neon_pulse" && index === 1 ? `0 0 10px ${color}` : undefined,
              textTransform: preset.style.uppercase || (index === 1 && preset.style.highlightUppercase) ? "uppercase" : "none",
            }}
            className={cn("relative z-10 text-[11px]", index === 1 && "scale-110")}
          >
            {word}
          </span>
        ))}
      </div>
    </button>
  );
}

function MetaTile({ meta, active, onClick }: { meta: OptionMeta; active: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className={cn("rounded-lg border p-2.5 text-left transition-all min-h-[86px]",
        active ? "border-emerald-400 bg-emerald-500/10 ring-1 ring-emerald-400/20" : "border-zinc-800 bg-zinc-900/60 hover:border-zinc-600")}>
      <div className="flex items-center justify-between gap-2">
        <span className={cn("text-[11px] font-semibold", active ? "text-emerald-300" : "text-zinc-200")}>{meta.label}</span>
        <span className="rounded px-1.5 py-0.5 text-[8px] font-black" style={{ color: meta.accent, backgroundColor: `${meta.accent}18` }}>{meta.preview}</span>
      </div>
      <p className="mt-1 text-[9px] text-zinc-500">{meta.mood}</p>
      <p className="mt-1.5 line-clamp-2 text-[9px] leading-snug text-zinc-600">{meta.desc}</p>
    </button>
  );
}

function TimingOptionCard({ meta, active, onClick, kind }: { meta: OptionMeta; active: boolean; onClick: () => void; kind: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative min-h-[92px] overflow-hidden rounded-lg border p-3 text-left transition-all",
        active
          ? "border-emerald-400 bg-emerald-500/10 ring-1 ring-emerald-400/25"
          : "border-zinc-800 bg-zinc-900/70 hover:border-zinc-600 hover:bg-zinc-900"
      )}
    >
      <div className="absolute inset-x-0 top-0 h-1" style={{ background: `linear-gradient(90deg, ${meta.accent}, transparent)` }} />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className={cn("text-[12px] font-semibold", active ? "text-emerald-300" : "text-zinc-200")}>{meta.label}</p>
          <p className="mt-1 line-clamp-2 text-[9px] leading-snug text-zinc-500">{meta.desc}</p>
        </div>
        <span className="rounded-md px-1.5 py-0.5 text-[8px] font-black" style={{ color: meta.accent, backgroundColor: `${meta.accent}18`, border: `1px solid ${meta.accent}44` }}>{meta.preview}</span>
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-800">
          <div className="h-full w-2/3 rounded-full transition-all group-hover:w-full" style={{ backgroundColor: meta.accent }} />
        </div>
        <span className="rounded border border-zinc-800 bg-zinc-950/80 px-1.5 py-0.5 text-[8px] uppercase tracking-wide text-zinc-500">{kind}</span>
      </div>
    </button>
  );
}

function FontChips({ fonts, active, onSelect }: { fonts: string[]; active: string; onSelect: (font: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {fonts.map((font) => (
        <button key={font} type="button" onClick={() => onSelect(font)}
          className={cn("rounded-lg border px-2.5 py-1.5 text-[10px] transition-colors",
            active === font ? "border-emerald-500 bg-emerald-500/10 text-emerald-300" : "border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:border-zinc-600")}
          style={{ fontFamily: font === "monospace" ? "monospace" : `'${font}', sans-serif` }}>
          {font}
        </button>
      ))}
    </div>
  );
}

function getPageItems<T>(items: T[], page: number, pageSize = PAGINATION_PAGE_SIZE) {
  return items.slice((page - 1) * pageSize, page * pageSize);
}

function getPageForIndex(index: number, pageSize = PAGINATION_PAGE_SIZE) {
  return index < 0 ? 1 : Math.floor(index / pageSize) + 1;
}

function PaginationControls({ page, totalItems, onPageChange, label }: { page: number; totalItems: number; onPageChange: (page: number) => void; label: string }) {
  const totalPages = Math.max(1, Math.ceil(totalItems / PAGINATION_PAGE_SIZE));
  const start = totalItems === 0 ? 0 : (page - 1) * PAGINATION_PAGE_SIZE + 1;
  const end = Math.min(page * PAGINATION_PAGE_SIZE, totalItems);

  if (totalPages <= 1) {
    return (
      <div className="mt-2 flex justify-end text-[10px] text-zinc-600">
        {totalItems} {label}
      </div>
    );
  }

  return (
    <div className="mt-3 flex items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-950/50 px-2.5 py-2">
      <span className="text-[10px] text-zinc-500">
        {start}-{end} of {totalItems} {label}
      </span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page === 1}
          className="rounded-md p-1 text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-200 disabled:pointer-events-none disabled:opacity-30"
          aria-label={`Previous ${label} page`}
          title="Previous page"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
        <span className="min-w-10 text-center font-mono text-[10px] text-zinc-400">{page}/{totalPages}</span>
        <button
          type="button"
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
          disabled={page === totalPages}
          className="rounded-md p-1 text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-200 disabled:pointer-events-none disabled:opacity-30"
          aria-label={`Next ${label} page`}
          title="Next page"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

// ─── Engine picker (Remotion | HyperFrames | FFmpeg) ──────────────────────────────────

function EnginePicker({
  engine,
  onChange,
  kind,
  isSuperadmin = false,
}: {
  engine: RenderEngine;
  onChange: (e: RenderEngine) => void;
  kind: "hook" | "subtitle";
  isSuperadmin?: boolean;
}) {
  const allEngines = ["remotion", "hyperframes", "ffmpeg", "skia"] as RenderEngine[];
  // Gate: remotion/hyperframes hidden only for SUBTITLE when non-superadmin
  // Hook always shows all engines
  const engineOptions = allEngines.filter((id) => {
    if (kind === "hook") return true; // Hook: semua engine tersedia untuk semua user
    const meta = ENGINE_NOTES[id];
    if (meta.superuserOnly && !isSuperadmin) return false;
    return true;
  });

  const getIcon = (id: string) => {
    switch (id) {
      case "remotion": return Clapperboard;
      case "hyperframes": return Zap;
      case "ffmpeg": return Download;
      case "skia": return Palette;
      default: return Clapperboard;
    }
  };

  const getTheme = (id: string, active: boolean) => {
    if (!active) {
      return "border-zinc-800/90 bg-zinc-900/40 text-zinc-400 hover:border-zinc-700 hover:bg-zinc-900/80 hover:text-zinc-200";
    }
    switch (id) {
      case "remotion":
        return "border-emerald-500/60 bg-emerald-500/10 text-emerald-100 ring-1 ring-emerald-500/40 shadow-[0_0_15px_rgba(16,185,129,0.15)]";
      case "hyperframes":
        return "border-cyan-500/60 bg-cyan-500/10 text-cyan-100 ring-1 ring-cyan-500/40 shadow-[0_0_15px_rgba(6,182,212,0.15)]";
      case "ffmpeg":
        return "border-purple-500/60 bg-purple-500/10 text-purple-100 ring-1 ring-purple-500/40 shadow-[0_0_15px_rgba(168,85,247,0.15)]";
      case "skia":
        return "border-amber-500/60 bg-amber-500/10 text-amber-100 ring-1 ring-amber-500/40 shadow-[0_0_15px_rgba(245,158,11,0.15)]";
      default:
        return "border-emerald-500/60 bg-emerald-500/10 text-emerald-100";
    }
  };

  const getBadgeStyle = (id: string, active: boolean) => {
    if (!active) return "bg-zinc-800 text-zinc-500 border border-zinc-700/50";
    switch (id) {
      case "remotion": return "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
      case "hyperframes": return "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40";
      case "ffmpeg": return "bg-purple-500/20 text-purple-300 border border-purple-500/40";
      case "skia": return "bg-amber-500/20 text-amber-300 border border-amber-500/40";
      default: return "bg-white/10 text-white";
    }
  };

  const getIconColor = (id: string, active: boolean) => {
    if (!active) return "text-zinc-500";
    switch (id) {
      case "remotion": return "text-emerald-400";
      case "hyperframes": return "text-cyan-400";
      case "ffmpeg": return "text-purple-400";
      case "skia": return "text-amber-400";
      default: return "text-white";
    }
  };

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-3 space-y-3">
      <div className={cn("grid gap-2.5", engineOptions.length <= 2 ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-1 sm:grid-cols-2")}>
        {engineOptions.map((id) => {
          const meta = ENGINE_NOTES[id];
          const active = engine === id;
          const Icon = getIcon(id);
          return (
            <button
              key={id}
              type="button"
              onClick={() => onChange(id)}
              className={cn(
                "group relative flex flex-col justify-between gap-2 rounded-xl border p-3 text-left transition-all",
                getTheme(id, active),
              )}
            >
              <div className="flex items-center justify-between gap-2 w-full">
                <span className="flex items-center gap-2 text-xs font-bold tracking-tight">
                  <Icon className={cn("h-4 w-4 shrink-0 transition-colors", getIconColor(id, active))} />
                  <span className={active ? "text-zinc-100" : "text-zinc-300 group-hover:text-zinc-100"}>{meta.label}</span>
                </span>
                <span className={cn(
                  "rounded-full px-2 py-0.5 text-[9px] font-black uppercase tracking-wider shrink-0 transition-colors",
                  getBadgeStyle(id, active),
                )}>
                  {meta.badge}
                </span>
              </div>
              <p className="text-[10px] leading-snug text-zinc-400 opacity-90">
                <span className={cn("font-medium", active ? "text-zinc-300" : "text-zinc-400")}>{meta.speed}</span> · {meta.quality}
              </p>
            </button>
          );
        })}
      </div>
      <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/50 px-3 py-2.5 flex items-start gap-2">
        <div className={cn("mt-0.5 shrink-0", getIconColor(engine, true))}>
          <Sparkles className="w-3.5 h-3.5" />
        </div>
        <p className="text-[10px] leading-relaxed text-zinc-400">
          <span className="font-semibold text-zinc-200">Note · {kind}: </span>
          {ENGINE_NOTES[engine].note}
        </p>
      </div>
    </div>
  );
}

function HfStyleGrid({
  items,
  activeId,
  onSelect,
}: {
  items: HfStylePreset[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  const PAGE_SIZE = 6;
  const totalPages = Math.ceil(items.length / PAGE_SIZE) || 1;
  const activeIndex = items.findIndex((s) => s.id === activeId);
  const initialPage = activeIndex >= 0 ? Math.floor(activeIndex / PAGE_SIZE) + 1 : 1;
  const [page, setPage] = useState(initialPage);

  const startIndex = (page - 1) * PAGE_SIZE;
  const visibleItems = items.slice(startIndex, startIndex + PAGE_SIZE);

  return (
    <div className="space-y-3">
      {/* 2 lines x 3 columns grid = 6 items */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
        {visibleItems.map((s) => {
          const active = activeId === s.id;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => onSelect(s.id)}
              className={cn(
                "group relative rounded-xl border p-2.5 text-left transition-all flex flex-col justify-between gap-2 overflow-hidden",
                active
                  ? "border-cyan-500 bg-cyan-950/30 ring-1 ring-cyan-500/50 shadow-md shadow-cyan-500/10"
                  : "border-zinc-800 bg-zinc-950/60 hover:border-zinc-700 hover:bg-zinc-900/60",
              )}
            >
              <div>
                <div className="flex items-center justify-between gap-1.5 mb-1.5">
                  <p className="text-[11px] font-bold text-zinc-100 group-hover:text-white truncate">
                    {s.name}
                  </p>
                  <span
                    className="shrink-0 rounded px-1.5 py-0.5 text-[8px] font-black uppercase tracking-wider"
                    style={{
                      color: s.accent,
                      backgroundColor: `${s.accent}18`,
                      border: `1px solid ${s.accent}44`,
                    }}
                  >
                    {s.mood}
                  </span>
                </div>
                <p className="text-[9px] text-zinc-400 line-clamp-2 leading-relaxed">
                  {s.desc}
                </p>
              </div>

              <div
                className="mt-1 flex h-9 items-center justify-center rounded-lg text-[10px] font-black tracking-wide uppercase px-2 shadow-inner"
                style={{
                  background: `linear-gradient(135deg, ${s.accent}25, rgba(0,0,0,0.7))`,
                  color: s.accent,
                  border: `1px solid ${s.accent}33`,
                  textShadow: `0 0 10px ${s.accent}88`,
                }}
              >
                {s.preview}
              </div>
            </button>
          );
        })}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-2 border-t border-zinc-800/60">
          <span className="text-[10px] text-zinc-500 font-medium">
            Page {page} of {totalPages} ({items.length} styles)
          </span>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              disabled={page === 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="px-2 py-0.5 text-[10px] font-semibold rounded border border-zinc-800 bg-zinc-900 text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-zinc-800 transition-colors"
            >
              Prev
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPage(p)}
                className={cn(
                  "w-5 h-5 text-[9px] font-bold rounded transition-colors",
                  page === p
                    ? "bg-cyan-500 text-black shadow-sm"
                    : "border border-zinc-800 bg-zinc-900/80 text-zinc-400 hover:text-white hover:bg-zinc-800",
                )}
              >
                {p}
              </button>
            ))}
            <button
              type="button"
              disabled={page === totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="px-2 py-0.5 text-[10px] font-semibold rounded border border-zinc-800 bg-zinc-900 text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-zinc-800 transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function CanvasPreviewFrame({
  canvas,
  thumbnailUrl,
  children,
  className,
  aspectRatio = "9/16",
  dimOverlay = false,
}: {
  canvas?: CanvasConfig | null;
  thumbnailUrl?: string;
  children?: React.ReactNode;
  className?: string;
  aspectRatio?: string;
  dimOverlay?: boolean;
}) {
  return (
    <div
      className={cn("relative w-full max-w-[220px] bg-zinc-900 rounded-lg overflow-hidden border border-zinc-800 shrink-0", className)}
      style={{ aspectRatio }}
    >
      {canvas ? (
        <div className="absolute inset-0" style={{ background: gradientCss(canvas.background) }}>
          {(canvas.backgroundImageUrl || canvas.background?.imageUrl) && (
            <img
              src={(canvas.backgroundImageUrl || canvas.background.imageUrl) as string}
              alt=""
              className="absolute inset-0 h-full w-full object-cover"
            />
          )}
          <CanvasAccents accents={canvas.accents || []} />
          {(canvas.background.vignette || 0) > 0 && (
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                background: `radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,${canvas.background.vignette}) 100%)`,
              }}
            />
          )}
          <div
            className="absolute overflow-hidden bg-zinc-800"
            style={{
              left: `${canvas.layout.videoX * 100}%`,
              top: `${canvas.layout.videoY * 100}%`,
              width: `${canvas.layout.videoW * 100}%`,
              height: `${canvas.layout.videoH * 100}%`,
              borderRadius: canvas.layout.borderRadius || 0,
              boxShadow: canvas.layout.shadow,
            }}
          >
            {thumbnailUrl && (
              <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-contain" />
            )}
            {dimOverlay && <div className="absolute inset-0 bg-black/40" />}
          </div>
          {children}
        </div>
      ) : (
        <>
          {thumbnailUrl ? (
            <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-cover" />
          ) : (
            <div className="absolute inset-0 bg-gradient-to-br from-zinc-700 to-zinc-950" />
          )}
          {dimOverlay && <div className="absolute inset-0 bg-black/40" />}
          {children}
        </>
      )}
    </div>
  );
}

function HfLivePreview({
  preset,
  sample,
  kind,
  aspectRatio,
  thumbnailUrl,
  canvas,
}: {
  preset: HfStylePreset | undefined;
  sample: string;
  kind: "hook" | "subtitle";
  aspectRatio: string;
  thumbnailUrl?: string;
  canvas?: CanvasConfig | null;
}) {
  const accent = preset?.accent || "#22d3ee";
  const label = sample || preset?.preview || (kind === "hook" ? "HOOK TEXT" : "subtitle words");
  return (
    <div className="w-full max-w-[220px]">
      <p className="mb-2 text-center text-[10px] font-medium uppercase tracking-wider text-zinc-500">
        Live Preview · HyperFrames
      </p>
      <CanvasPreviewFrame
        canvas={canvas || null}
        thumbnailUrl={thumbnailUrl}
        className="mx-auto shadow-xl rounded-xl"
      >
        <HfFixedStylePreview id={preset?.id || ""} label={label} accent={accent} />
        <div className="absolute left-2 top-2 rounded bg-cyan-500/20 px-1.5 py-0.5 text-[8px] font-bold uppercase text-cyan-300">
          HF · {preset?.name || "template"}
        </div>
      </CanvasPreviewFrame>
      <p className="mt-2 text-center text-[9px] text-zinc-500">
        Fast template · style fixed · {aspectRatio} content → 9:16 out
      </p>
    </div>
  );
}

// ─── Skia Live Previews ──────────────────────────────────────────────────────

function SkiaHookLivePreview({
  style,
  thumbnailUrl,
  aspectRatio = "9:16",
  canvas,
}: {
  style: HookStyle;
  thumbnailUrl?: string;
  aspectRatio?: string;
  canvas?: CanvasConfig | null;
}) {
  const presetId = style.animation || "skia_zoom_punch";
  const preset = SKIA_HOOK_PRESETS.find(p => p.id === presetId || p.id === `skia_${presetId}`) || SKIA_HOOK_PRESETS[0];
  const sample = style.text || getHookPreviewSample(presetId);
  const posTop = `${style.positionY ?? 40}%`;

  return (
    <>
      <div className="mb-3 flex w-full items-center justify-between gap-2">
        <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
        <span className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[9px] text-amber-300">
          <Palette className="inline w-3 h-3 mr-1" />Skia Canvas GPU
        </span>
      </div>
      <CanvasPreviewFrame canvas={canvas || null} thumbnailUrl={thumbnailUrl} dimOverlay>
        <div className="absolute left-0 right-0 flex items-center justify-center px-3 pointer-events-none" style={{ top: posTop, transform: "translateY(-50%)" }}>
          {presetId === "skia_neon_cyberpunk" ? (
            <div
              style={{
                position: "relative",
                padding: "8px 14px",
                maxWidth: "92%",
                background: "rgba(10, 15, 30, 0.85)",
                borderRadius: "10px",
                border: "1.5px solid #00F0FF",
                boxShadow: "0 0 16px rgba(0,240,255,0.4), inset 0 0 12px rgba(255,0,127,0.25)",
                backdropFilter: "blur(8px)",
                boxSizing: "border-box",
              }}
            >
              <div style={{ position: "absolute", top: -2, left: -2, width: 6, height: 6, borderTop: "2px solid #FF007F", borderLeft: "2px solid #FF007F" }} />
              <div style={{ position: "absolute", bottom: -2, right: -2, width: 6, height: 6, borderBottom: "2px solid #FF007F", borderRight: "2px solid #FF007F" }} />
              <p
                style={{
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                  fontWeight: 900,
                  fontFamily: `'${style.fontFamily || "Montserrat"}', sans-serif`,
                  background: "linear-gradient(135deg, #00F0FF, #FF007F)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  textTransform: "uppercase",
                  letterSpacing: "0.03em",
                  textAlign: "center",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "skia_frosted_pill" ? (
            <div
              style={{
                padding: "6px 14px",
                maxWidth: "92%",
                background: "rgba(255, 255, 255, 0.15)",
                borderRadius: "999px",
                border: "1px solid rgba(255, 255, 255, 0.35)",
                boxShadow: "0 8px 24px rgba(0, 0, 0, 0.4)",
                backdropFilter: "blur(12px)",
                boxSizing: "border-box",
              }}
            >
              <p
                style={{
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 15),
                  fontWeight: 800,
                  fontFamily: `'${style.fontFamily || "Plus Jakarta Sans"}', sans-serif`,
                  color: "#FFFFFF",
                  textAlign: "center",
                  letterSpacing: "-0.01em",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "skia_aurora_gradient" ? (
            <div
              style={{
                position: "relative",
                padding: "6px 14px",
                maxWidth: "92%",
                borderRadius: "8px",
                background: "rgba(5, 15, 10, 0.8)",
                boxShadow: "0 0 20px rgba(16, 185, 129, 0.35)",
                boxSizing: "border-box",
              }}
            >
              <p
                style={{
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                  fontWeight: 900,
                  fontFamily: `'${style.fontFamily || "Outfit"}', sans-serif`,
                  background: "linear-gradient(135deg, #10B981 0%, #38BDF8 50%, #8B5CF6 100%)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  textAlign: "center",
                  textTransform: "uppercase",
                  letterSpacing: "0.03em",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "skia_impact_badge" ? (
            <div
              style={{
                background: "linear-gradient(135deg, #FACC15, #EAB308)",
                padding: "5px 12px",
                maxWidth: "92%",
                borderRadius: "5px",
                transform: "rotate(-1.5deg)",
                boxShadow: "0 4px 0 #713F12, 0 8px 18px rgba(0,0,0,0.5)",
                boxSizing: "border-box",
              }}
            >
              <p
                style={{
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                  fontWeight: 900,
                  fontFamily: `'${style.fontFamily || "Anton"}', sans-serif`,
                  color: "#000000",
                  textTransform: "uppercase",
                  letterSpacing: "0.02em",
                  textAlign: "center",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "skia_3d_chrome" ? (
            <p
              style={{
                fontSize: Math.min(Math.max(style.fontSize * 0.24, 12), 17),
                fontWeight: 900,
                maxWidth: "92%",
                fontFamily: `'${style.fontFamily || "Bebas Neue"}', sans-serif`,
                background: "linear-gradient(180deg, #FFFFFF 0%, #E2E8F0 30%, #FBBF24 50%, #78350F 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                textAlign: "center",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
                filter: "drop-shadow(0 3px 8px rgba(0,0,0,0.85))",
                wordBreak: "break-word",
              }}
            >
              {sample}
            </p>
          ) : presetId === "skia_ruby_flame" ? (
            <p
              style={{
                fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                fontWeight: 900,
                maxWidth: "92%",
                fontFamily: `'${style.fontFamily || "Bungee"}', sans-serif`,
                background: "linear-gradient(135deg, #FF3366, #FF9900)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                textAlign: "center",
                textTransform: "uppercase",
                filter: "drop-shadow(0 0 12px rgba(255, 46, 46, 0.6))",
                wordBreak: "break-word",
              }}
            >
              {sample}
            </p>
          ) : presetId === "skia_gold_prestige" ? (
            <div className="w-full text-center px-2" style={{ maxWidth: "92%" }}>
              <p style={{
                fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                fontWeight: 800,
                fontFamily: `'${style.fontFamily || "Playfair Display"}', serif`,
                background: "linear-gradient(135deg, #FEF08A, #CA8A04)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                textAlign: "center",
                letterSpacing: "0.03em",
                filter: "drop-shadow(0 2px 6px rgba(202, 138, 4, 0.4))",
                wordBreak: "break-word",
              }}>
                {sample}
              </p>
            </div>
          ) : presetId === "skia_minimal_editorial" ? (
            <div
              style={{
                backgroundColor: "rgba(15, 23, 42, 0.75)",
                borderRadius: "8px",
                border: "1px solid rgba(255, 255, 255, 0.2)",
                padding: "5px 12px",
                maxWidth: "92%",
                boxSizing: "border-box",
              }}
            >
              <p
                style={{
                  color: "#FFFFFF",
                  fontFamily: `'${style.fontFamily || "Inter"}', sans-serif`,
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 15),
                  fontWeight: 800,
                  textAlign: "center",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "skia_glitch_rgb" ? (
            <div className="relative text-center px-2" style={{ maxWidth: "92%" }}>
              <p style={{
                position: "absolute",
                inset: 0,
                color: "#FF0000",
                opacity: 0.7,
                transform: "translate(-2px, 0)",
                fontFamily: `'${style.fontFamily || "Anton"}', sans-serif`,
                fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                fontWeight: 900,
                textTransform: "uppercase",
                wordBreak: "break-word",
              }}>{sample}</p>
              <p style={{
                position: "absolute",
                inset: 0,
                color: "#00FFFF",
                opacity: 0.7,
                transform: "translate(2px, 0)",
                fontFamily: `'${style.fontFamily || "Anton"}', sans-serif`,
                fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                fontWeight: 900,
                textTransform: "uppercase",
                wordBreak: "break-word",
              }}>{sample}</p>
              <p style={{
                position: "relative",
                color: style.color || "#FFFFFF",
                fontFamily: `'${style.fontFamily || "Anton"}', sans-serif`,
                fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                fontWeight: 900,
                textTransform: "uppercase",
                wordBreak: "break-word",
              }}>{sample}</p>
            </div>
          ) : presetId === "skia_typewriter" ? (
            <div
              style={{
                backgroundColor: "rgba(9, 13, 22, 0.85)",
                borderRadius: "6px",
                border: "1px solid rgba(34, 197, 94, 0.4)",
                padding: "5px 10px",
                maxWidth: "92%",
                boxSizing: "border-box",
                boxShadow: "0 0 12px rgba(34, 197, 94, 0.25)",
              }}
            >
              <p
                style={{
                  color: "#22C55E",
                  fontFamily: `'${style.fontFamily || "Space Grotesk"}', monospace`,
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 14),
                  fontWeight: 700,
                  textTransform: "uppercase",
                  textAlign: "center",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "skia_fade_scale" ? (
            <p
              style={{
                fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                fontWeight: 800,
                maxWidth: "92%",
                fontFamily: `'${style.fontFamily || "Poppins"}', sans-serif`,
                color: style.color || "#FFFFFF",
                textAlign: "center",
                paintOrder: style.strokeEnabled ? "stroke" : undefined,
                WebkitTextStroke: style.strokeEnabled ? `${Math.max(style.strokeWidth * 0.25, 0.6)}px ${style.strokeColor || "#000"}` : undefined,
                textShadow: "0 4px 12px rgba(0,0,0,0.6)",
                wordBreak: "break-word",
              }}
            >
              {sample}
            </p>
          ) : (
            <p style={{
              fontSize: Math.min(Math.max(style.fontSize * 0.24, 12), 17),
              fontWeight: 900,
              fontFamily: style.fontFamily === "monospace" ? "monospace" : `'${style.fontFamily || "Anton"}', sans-serif`,
              color: style.color || "#FFFFFF",
              textTransform: style.uppercase ? "uppercase" : "none",
              textAlign: "center",
              maxWidth: "92%",
              whiteSpace: "pre-line",
              wordBreak: "break-word",
              padding: "4px 8px",
              backgroundColor: style.bgOpacity > 0 ? `${style.bgColor || "black"}${Math.round(style.bgOpacity * 255).toString(16).padStart(2, "0")}` : "transparent",
              paintOrder: style.strokeEnabled ? "stroke" : undefined,
              WebkitTextStroke: style.strokeEnabled ? `${Math.max(style.strokeWidth * 0.25, 0.6)}px ${style.strokeColor || "#000"}` : undefined,
              textShadow: style.shadowEnabled ? `2px 2px 0px ${style.shadowColor || "#000"}` : undefined,
            }}>
              {sample}
            </p>
          )}
        </div>
        <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-500 z-10">
          skia gpu · {preset.name} | {style.duration}s
        </p>
      </CanvasPreviewFrame>
      <div className="mt-3 grid w-full grid-cols-2 gap-2 text-[10px]">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Font</span><p className="truncate text-zinc-300">{style.fontFamily}</p></div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Preset</span><p className="truncate text-amber-400">{preset.name}</p></div>
      </div>
    </>
  );
}

function SkiaSubtitleLivePreview({
  style,
  thumbnailUrl,
  activeWordIdx,
  canvas,
}: {
  style: SubtitleStyle;
  thumbnailUrl?: string;
  activeWordIdx: number;
  canvas?: CanvasConfig | null;
}) {
  const presetId = style.stylePreset || "clean_editorial";
  const preset = SKIA_SUBTITLE_PRESETS.find(p => p.id === presetId) || SKIA_SUBTITLE_PRESETS[0];
  const posTop = `${style.positionY ?? 78}%`;
  const sampleWords = ["ini", "kata", "penting", "banget", "untuk", "kamu"];
  const count = Math.max(1, Math.min(6, style.maxWordsPerLine || 4));
  const words = sampleWords.slice(0, count);

  // Ensure all preset Google Fonts are available in the DOM
  useGoogleFont(style.fontFamily || "Inter");
  useGoogleFont("Inter");
  useGoogleFont("Plus Jakarta Sans");
  useGoogleFont("Montserrat");
  useGoogleFont("Poppins");
  useGoogleFont("Playfair Display");
  useGoogleFont("Space Grotesk");
  useGoogleFont("Anton");
  useGoogleFont("Outfit");
  useGoogleFont("Bebas Neue");
  useGoogleFont("Archivo Black");

  return (
    <>
      <div className="mb-3 flex w-full items-center justify-between gap-2">
        <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
        <span className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[9px] text-amber-300">
          <Palette className="inline w-3 h-3 mr-1" />Skia Canvas GPU
        </span>
      </div>
      <CanvasPreviewFrame canvas={canvas || null} thumbnailUrl={thumbnailUrl} dimOverlay>
        <div className="absolute left-0 right-0 flex justify-center px-3 pointer-events-none" style={{ top: posTop, transform: "translateY(-50%)" }}>
          {(() => {
            const isWordPop = style.lineTransition === "word_pop";
            const isLineReveal = style.lineTransition === "line_reveal";
            const displayWords = isWordPop ? [words[activeWordIdx % words.length]] : words;

            // Card / Capsule background styles
            const hasBg = style.bgEnabled || presetId === "glassmorphism" || presetId === "clean_editorial" || presetId === "podcast_pro" || presetId === "modern_mono";
            const bgOpacity = style.bgOpacity ?? (presetId === "glassmorphism" ? 0.25 : 0.75);
            const bgHex = style.bgColor || (presetId === "podcast_pro" ? "#121216" : presetId === "modern_mono" ? "#080c14" : presetId === "clean_editorial" ? "#0f172a" : "#1e293b");
            const bgAlpha = Math.round(Math.max(0, Math.min(1, bgOpacity)) * 255).toString(16).padStart(2, "0");
            const bgRadius = style.bgRadius ?? (presetId === "podcast_pro" ? 999 : presetId === "glassmorphism" ? 16 : 12);
            const bgPadding = style.bgPadding ?? 16;

            const containerStyle: React.CSSProperties = {
              display: "flex",
              flexWrap: isWordPop ? "nowrap" : "wrap",
              alignItems: "center",
              justifyContent: "center",
              maxWidth: "94%",
              gap: isWordPop ? 0 : Math.max(3, (style.wordSpacing ?? 6) * 0.6),
              ...(hasBg ? {
                backgroundColor: presetId === "glassmorphism" ? undefined : `${bgHex}${bgAlpha}`,
                background: presetId === "glassmorphism"
                  ? `linear-gradient(135deg, rgba(255, 255, 255, ${bgOpacity}) 0%, rgba(255, 255, 255, ${bgOpacity * 0.3}) 100%)`
                  : undefined,
                backdropFilter: "blur(12px)",
                WebkitBackdropFilter: "blur(12px)",
                border: presetId === "glassmorphism"
                  ? "1.5px solid rgba(255, 255, 255, 0.55)"
                  : presetId === "podcast_pro"
                    ? "1.5px solid rgba(16, 185, 129, 0.5)"
                    : presetId === "modern_mono"
                      ? "1.5px solid #06B6D4"
                      : "1px solid rgba(255, 255, 255, 0.12)",
                boxShadow: presetId === "glassmorphism"
                  ? "0 8px 32px 0 rgba(0, 0, 0, 0.45), inset 0 0 12px rgba(255, 255, 255, 0.25)"
                  : presetId === "podcast_pro"
                    ? "0 0 16px rgba(16, 185, 129, 0.35)"
                    : presetId === "modern_mono"
                      ? "0 0 16px rgba(6, 182, 212, 0.35)"
                      : "0 8px 24px rgba(0,0,0,0.5)",
                borderRadius: `${bgRadius}px`,
                padding: `${Math.round(bgPadding * 0.35)}px ${Math.round(bgPadding * 0.65)}px`,
              } : {}),
              ...(isLineReveal ? {
                borderLeft: `3px solid ${style.highlightColor || "#38BDF8"}`,
              } : {}),
              ...(presetId === "cinematic_slate" ? {
                borderTop: "1.5px solid rgba(252, 211, 77, 0.6)",
                borderBottom: "1.5px solid rgba(252, 211, 77, 0.6)",
                padding: "6px 14px",
              } : {}),
            };

            return (
              <div style={containerStyle}>
                {presetId === "podcast_pro" && (
                  <div className="flex items-center gap-1 shrink-0 mr-1">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_#10B981]" />
                    <span className="text-[7px] font-bold text-emerald-400 tracking-wider">MIC</span>
                  </div>
                )}
                {presetId === "modern_mono" && (
                  <div className="flex items-center gap-1 w-full border-b border-cyan-500/30 pb-1 mb-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                    <span className="w-1.5 h-1.5 rounded-full bg-yellow-500" />
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                    <span className="text-[7px] text-cyan-400 font-mono ml-1 font-bold">TERMINAL v2.0</span>
                  </div>
                )}
                {displayWords.map((w, i) => {
                  const isActive = isWordPop ? true : (i === activeWordIdx % words.length);
                  const isKeyword = style.highlightWords?.includes(w.toLowerCase());
                  const shouldHighlight = isActive || isKeyword;

                  const fontSize = Math.min(Math.max((style.fontSize || 42) * 0.23, 10), 17);
                  const fontWeight = shouldHighlight
                    ? (style.highlightBold !== false ? 900 : Number(style.fontWeight || 700))
                    : Number(style.fontWeight || 600);

                  // Colors & Gradients
                  const gradActive = style.gradientEnabled
                    ? `linear-gradient(135deg, ${style.gradientFrom || "#667EEA"} 0%, ${style.gradientTo || "#764BA2"} 100%)`
                    : presetId === "retro_chrome"
                      ? "linear-gradient(180deg, #FFF9C4 0%, #FFFFFF 35%, #F57F17 50%, #FFD54F 60%, #E65100 100%)"
                      : null;

                  const gradInactive = style.gradientEnabled
                    ? `linear-gradient(135deg, ${style.gradientFrom || "#667EEA"}80 0%, ${style.gradientTo || "#764BA2"}80 100%)`
                    : presetId === "retro_chrome"
                      ? "linear-gradient(180deg, #E0E0E0 0%, #FFFFFF 40%, #757575 50%, #BDBDBD 60%, #424242 100%)"
                      : null;

                  const grad = shouldHighlight ? gradActive : gradInactive;

                  // Text shadows & Glow
                  const glowColor = style.glowColor || style.highlightColor || "#00FFFF";
                  const shadowParts: string[] = [];
                  if (shouldHighlight && style.glowEnabled) {
                    shadowParts.push(`0 0 10px ${glowColor}`, `0 0 20px ${glowColor}B3`);
                  } else if (shouldHighlight && (presetId === "neon_tube" || presetId === "glassmorphism")) {
                    shadowParts.push(`0 0 10px ${style.highlightColor || "#38BDF8"}`);
                  } else if (style.shadowEnabled) {
                    shadowParts.push(`0 0 ${style.shadowBlur || 8}px ${style.shadowColor || "#000000"}`);
                  } else {
                    shadowParts.push("0 2px 6px rgba(0,0,0,0.8)");
                  }

                  // Active scale
                  const scaleVal = shouldHighlight && (style.highlightBold !== false || isWordPop)
                    ? (style.highlightScale || 1.15)
                    : 1.0;

                  // Stroke / Outline
                  const strokeWidth = style.strokeEnabled ? (style.strokeWidth || 3) * 0.25 : 0;
                  const strokeColor = style.strokeColor || "#000000";

                  const wordStyle: React.CSSProperties = {
                    fontFamily: `'${style.fontFamily || "Inter"}', sans-serif`,
                    fontSize: fontSize,
                    fontWeight: fontWeight,
                    letterSpacing: `${style.letterSpacing || 0}px`,
                    textTransform: style.uppercase ? "uppercase" : style.capitalize ? "capitalize" : "none",
                    fontStyle: style.italic ? "italic" : "normal",
                    transform: `scale(${scaleVal})`,
                    transition: "transform 0.15s ease, color 0.15s ease",
                    display: "inline-block",
                    wordBreak: "break-word",
                    textShadow: shadowParts.join(", ") || undefined,
                    ...(grad ? {
                      background: grad,
                      WebkitBackgroundClip: "text",
                      WebkitTextFillColor: "transparent",
                    } : {
                      color: shouldHighlight ? (style.highlightColor || "#38BDF8") : (style.color || "#FFFFFF"),
                    }),
                    ...(strokeWidth > 0 ? {
                      WebkitTextStroke: `${strokeWidth}px ${strokeColor}`,
                      paintOrder: "stroke fill",
                    } : {}),
                    ...(presetId === "kinetic_word_box" && shouldHighlight ? {
                      backgroundColor: style.highlightColor || "#FF0055",
                      color: "#FFFFFF",
                      WebkitTextFillColor: "#FFFFFF",
                      borderRadius: "6px",
                      padding: "2px 6px",
                      boxShadow: `0 4px 14px ${style.highlightColor || "#FF0055"}B3`,
                    } : {}),
                    ...(presetId === "clean_editorial" && shouldHighlight ? {
                      borderBottom: `2.5px solid ${style.highlightColor || "#38BDF8"}`,
                      paddingBottom: 2,
                    } : {}),
                  };

                  return (
                    <span key={`${w}-${i}`} style={wordStyle}>
                      {w}
                      {presetId === "modern_mono" && shouldHighlight && <span className="animate-pulse text-cyan-400 ml-0.5">_</span>}
                    </span>
                  );
                })}
              </div>
            );
          })()}
        </div>
        <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-500 z-10">
          skia gpu · {preset.name}
        </p>
      </CanvasPreviewFrame>
      <div className="mt-3 grid w-full grid-cols-2 gap-2 text-[10px]">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Font</span><p className="truncate text-zinc-300">{style.fontFamily}</p></div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Preset</span><p className="truncate text-amber-400">{preset.name}</p></div>
      </div>
    </>
  );
}

// ─── Hook Editor ─────────────────────────────────────────────────────────────

function HookEditor({ style, onChange, aspectRatio, thumbnailUrl, canvasBackground, isSuperadmin }: { style: HookStyle; onChange: (s: HookStyle) => void; aspectRatio: string; thumbnailUrl?: string; canvasBackground?: { mode: BackgroundMode; templateId: string; imageDataUrl: string | null } | null; isSuperadmin?: boolean }) {
  const update = (patch: Partial<HookStyle>) => onChange({ ...style, ...patch });
  const engine = resolveEngine(style.engine);
  const hfId = style.hf_template || defaultHfHookId();
  const hfPreset = HF_HOOK_STYLES.find((s) => s.id === hfId) || HF_HOOK_STYLES[0];
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [presetPage, setPresetPage] = useState(1);
  const [animationPage, setAnimationPage] = useState(() => getPageForIndex(HOOK_ANIMATIONS.indexOf(style.animation)));
  const [ffmpegHookPage, setFfmpegHookPage] = useState(1);
  const [skiaHookPage, setSkiaHookPage] = useState(1);
  useGoogleFont(style.fontFamily);
  const canvas = (aspectRatio === "16:9" || aspectRatio === "1:1")
    ? buildCanvasConfig(aspectRatio, {
      backgroundMode: canvasBackground?.mode || "template",
      templateId: canvasBackground?.templateId || "dark-studio",
      backgroundImageUrl: canvasBackground?.imageDataUrl || null,
    })
    : null;
  // Outer UI shell always phone-like 9:16; inner composition matches selected aspect
  const outerAspect = "9/16";
  const activeAnimation = HOOK_ANIMATION_META[style.animation] || HOOK_ANIMATION_META.podcast_lower_third;
  const capabilities = hookCapabilities(style.animation);
  const isModernHookStyle = Boolean(HOOK_CAPABILITIES[style.animation]);
  const visibleHookPresets = getPageItems(HOOK_PRESETS, presetPage);
  const visibleHookAnimations = getPageItems(HOOK_ANIMATIONS, animationPage);
  const visibleFfmpegHooks = getPageItems(FFMPEG_HOOK_PRESETS, ffmpegHookPage);
  const visibleSkiaHooks = getPageItems(SKIA_HOOK_PRESETS, skiaHookPage);

  useEffect(() => {
    setAnimationPage(getPageForIndex(HOOK_ANIMATIONS.indexOf(style.animation)));
  }, [style.animation]);

  useEffect(() => {
    if (engine === "remotion" && !HOOK_ANIMATIONS.includes(style.animation)) {
      update({ animation: DEFAULT_HOOK_STYLE.animation });
    }
  }, [style.animation, engine]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 h-full min-h-0 overflow-hidden">
      {/* Left scrolls; right Live Preview stays put */}
      <div className="lg:col-span-8 p-4 overflow-y-auto space-y-4 border-r border-zinc-800 min-h-0">
        <Section title="Render Engine">
          <EnginePicker
            engine={engine}
            kind="hook"
            isSuperadmin={isSuperadmin}
            onChange={(e) => update({
              engine: e,
              hf_template: style.hf_template || defaultHfHookId(),
            })}
          />
        </Section>

        {engine === "hyperframes" ? (
          <>
            <Section title="HyperFrames Hook Styles">
              <HfStyleGrid
                items={HF_HOOK_STYLES}
                activeId={hfId}
                onSelect={(id) => update({ engine: "hyperframes", hf_template: id })}
              />
            </Section>
            <Section title="Hook Text">
              <textarea value={style.text} onChange={(e) => update({ text: e.target.value })} placeholder="Leave empty for AI-generated hook..." rows={2} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 resize-none focus:outline-none focus:border-zinc-500" />
            </Section>
            <Section title="Duration">
              <RangeInput label={`Duration: ${style.duration}s`} min={15} max={60} value={Math.round(style.duration * 10)} onChange={(v) => update({ duration: v / 10 })} />
            </Section>
          </>
        ) : engine === "ffmpeg" ? (
          <>
            <Section title="FFmpeg Drawtext">
              <div className="rounded-lg border border-purple-500/20 bg-purple-500/5 p-3">
                <p className="text-[10px] text-purple-300 mb-1"><Zap className="inline w-3 h-3 mr-1" />Server-side render · no browser needed</p>
                <p className="text-[9px] text-zinc-500">FFmpeg drawtext filter. 12 Preset unik dengan server-side overlay cepat.</p>
              </div>
            </Section>

            <Section title="Hook Style Preset">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {visibleFfmpegHooks.map(preset => (
                  <button
                    key={preset.id}
                    type="button"
                    onClick={() => update({
                      animation: preset.id,
                      color: preset.color,
                      fontSize: preset.fontSize,
                      fontFamily: preset.fontFamily,
                      fontWeight: preset.fontWeight,
                      strokeEnabled: preset.strokeEnabled,
                      strokeWidth: preset.strokeWidth,
                      strokeColor: preset.strokeColor,
                      bgOpacity: preset.bgOpacity,
                      position: preset.positionY <= 35 ? "top" : preset.positionY >= 65 ? "bottom" : "center",
                      positionY: preset.positionY,
                    })}
                    className={cn(
                      "group overflow-hidden rounded-xl border text-left transition-all",
                      style.animation === preset.id
                        ? "border-purple-500 bg-purple-500/10 ring-1 ring-purple-500/40"
                        : "border-zinc-700/80 bg-zinc-900/40 hover:border-zinc-500 hover:bg-zinc-900"
                    )}
                  >
                    <span
                      className="block relative w-full overflow-hidden bg-zinc-950"
                      style={{ aspectRatio: "16/9" }}
                    >
                      <span
                        className="absolute left-0 right-0 flex justify-center px-2"
                        style={{ top: `${preset.positionY}%`, transform: "translateY(-50%)" }}
                      >
                        <span
                          className="truncate whitespace-nowrap font-semibold"
                          style={{
                            fontSize: Math.max(preset.fontSize * 0.24, 12),
                            fontWeight: Number(preset.fontWeight),
                            fontFamily: `'${preset.fontFamily}', sans-serif`,
                            color: preset.color,
                            textTransform: "uppercase",
                            letterSpacing: "0.02em",
                            padding: "2px 6px",
                            backgroundColor: preset.bgOpacity > 0 ? `#000${Math.round(Math.min(1, preset.bgOpacity) * 255).toString(16).padStart(2, "0")}` : "transparent",
                            paintOrder: preset.strokeEnabled ? "stroke" : undefined,
                            WebkitTextStroke: preset.strokeEnabled ? `${Math.max(preset.strokeWidth * 0.18, 0.6)}px ${preset.strokeColor}` : undefined,
                          }}
                        >
                          HOOK
                        </span>
                      </span>
                      {style.animation === preset.id && (
                        <span className="absolute top-1.5 right-1.5 z-10 flex h-4 w-4 items-center justify-center rounded-full bg-purple-500 text-white shadow">
                          <Check className="h-2.5 w-2.5 stroke-[3]" />
                        </span>
                      )}
                    </span>
                    <span className="block px-2.5 py-1.5">
                      <span className="flex items-center gap-1.5">
                        <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: preset.color }} />
                        <span className={cn("truncate text-[10px] font-semibold", style.animation === preset.id ? "text-purple-300" : "text-zinc-300 group-hover:text-zinc-100")}>
                          {preset.name}
                        </span>
                      </span>
                      <span className="mt-0.5 block truncate text-[8px] text-zinc-600">{preset.desc}</span>
                    </span>
                  </button>
                ))}
              </div>
              <PaginationControls page={ffmpegHookPage} totalItems={FFMPEG_HOOK_PRESETS.length} onPageChange={setFfmpegHookPage} label="presets" />
            </Section>

            <Section title="Hook Text">
              <textarea value={style.text} onChange={(e) => update({ text: e.target.value })} placeholder="Leave empty for AI-generated hook..." rows={2} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 resize-none focus:outline-none focus:border-zinc-500" />
            </Section>

            <Section title="Typography">
              <FontChips fonts={HOOK_FONT_SUGGESTIONS} active={style.fontFamily} onSelect={(fontFamily) => update({ fontFamily })} />
              <div className="grid grid-cols-3 gap-3 mt-3">
                <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={FONT_OPTIONS} />
                <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                <RangeInput label={`Size: ${style.fontSize}px`} min={24} max={96} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
              </div>
              <div className="flex gap-4 mt-3">
                <Checkbox label="UPPERCASE" checked={style.uppercase} onChange={(v) => update({ uppercase: v })} />
              </div>
            </Section>

            <Section title="Colors">
              <div className="grid grid-cols-2 gap-3">
                <ColorPicker label="Text Color" value={style.color} onChange={(v) => update({ color: v })} />
                <ColorPicker label="Background" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
              </div>
              <RangeInput label={`BG Opacity: ${Math.round(style.bgOpacity * 100)}%`} min={0} max={100} value={Math.round(style.bgOpacity * 100)} onChange={(v) => update({ bgOpacity: v / 100 })} />
            </Section>

            <Section title="Stroke & Shadow">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text outline" checked={style.strokeEnabled} onChange={(v) => update({ strokeEnabled: v })} />
                  {style.strokeEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Outline" value={style.strokeColor} onChange={(v) => update({ strokeColor: v })} />
                      <RangeInput label={`Width: ${style.strokeWidth}px`} min={1} max={10} value={style.strokeWidth} onChange={(v) => update({ strokeWidth: v })} />
                    </div>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text shadow" checked={style.shadowEnabled} onChange={(v) => update({ shadowEnabled: v })} />
                  {style.shadowEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Shadow" value={style.shadowColor} onChange={(v) => update({ shadowColor: v })} />
                      <RangeInput label={`Blur: ${style.shadowBlur}`} min={0} max={40} value={style.shadowBlur} onChange={(v) => update({ shadowBlur: v })} />
                    </div>
                  )}
                </div>
              </div>
            </Section>

            <Section title="Position">
              <div className="grid grid-cols-3 gap-2 mb-3">
                {(["top", "center", "bottom"] as const).map(p => {
                  const isSelected = (style.positionY != null ? (style.positionY <= 35 ? "top" : style.positionY >= 65 ? "bottom" : "center") : style.position) === p;
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => update({ position: p, positionY: p === "top" ? 20 : p === "bottom" ? 80 : 50 })}
                      className={cn(
                        "py-2 rounded-lg border text-[11px] font-medium capitalize transition-colors",
                        isSelected ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600"
                      )}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
              <RangeInput
                label={`Vertical: ${style.positionY}%`}
                min={5}
                max={95}
                value={style.positionY}
                onChange={(v) => update({
                  positionY: v,
                  position: v <= 35 ? "top" : v >= 65 ? "bottom" : "center",
                })}
              />
            </Section>

            <Section title="Duration">
              <RangeInput label={`Duration: ${style.duration}s`} min={15} max={60} value={Math.round(style.duration * 10)} onChange={(v) => update({ duration: v / 10 })} />
              <div className="grid grid-cols-2 gap-3 mt-3">
                <RangeInput label={`Fade In: ${style.fadeIn}s`} min={1} max={15} value={Math.round(style.fadeIn * 10)} onChange={(v) => update({ fadeIn: v / 10 })} />
                <RangeInput label={`Fade Out: ${style.fadeOut}s`} min={1} max={15} value={Math.round(style.fadeOut * 10)} onChange={(v) => update({ fadeOut: v / 10 })} />
              </div>
            </Section>
          </>
        ) : engine === "skia" ? (
          <>
            <Section title="Skia Render Engine">
              <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                <p className="text-[10px] text-amber-400 mb-1"><Palette className="inline w-3 h-3 mr-1" />Canvas GPU Rendering</p>
                <p className="text-[9px] text-zinc-500">Hook animation dirender cepat via GPU Skia Canvas. 12 Preset dengan efek shader khusus.</p>
              </div>
            </Section>

            <Section title="Skia Hook Presets">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {visibleSkiaHooks.map(preset => (
                  <button
                    key={preset.id}
                    type="button"
                    onClick={() => update({
                      animation: preset.id,
                      color: preset.color,
                      fontSize: preset.fontSize,
                      fontFamily: preset.fontFamily,
                      fontWeight: preset.fontWeight,
                      strokeEnabled: preset.strokeEnabled,
                      strokeWidth: preset.strokeWidth,
                      strokeColor: preset.strokeColor,
                      gradientEnabled: preset.gradientEnabled,
                      gradientFrom: preset.gradientFrom,
                      gradientTo: preset.gradientTo,
                      glowEnabled: preset.glowEnabled,
                      glowColor: preset.glowColor,
                      glowSize: preset.glowSize,
                      bgOpacity: preset.bgOpacity,
                      position: preset.positionY <= 35 ? "top" : preset.positionY >= 65 ? "bottom" : "center",
                      positionY: preset.positionY,
                    })}
                    className={cn(
                      "group overflow-hidden rounded-xl border text-left transition-all",
                      style.animation === preset.id || style.animation === preset.id.replace("skia_", "")
                        ? "border-amber-500 bg-amber-500/10 ring-1 ring-amber-500/40"
                        : "border-zinc-700/80 bg-zinc-900/40 hover:border-zinc-500 hover:bg-zinc-900"
                    )}
                  >
                    <span
                      className="block relative w-full overflow-hidden bg-zinc-950"
                      style={{ aspectRatio: "16/9" }}
                    >
                      <span
                        className="absolute left-0 right-0 flex justify-center px-2"
                        style={{ top: `${preset.positionY}%`, transform: "translateY(-50%)" }}
                      >
                        <span
                          className="truncate whitespace-nowrap font-semibold"
                          style={{
                            fontSize: Math.max(preset.fontSize * 0.24, 12),
                            fontWeight: Number(preset.fontWeight),
                            fontFamily: `'${preset.fontFamily}', sans-serif`,
                            color: preset.color,
                            textTransform: "uppercase",
                            letterSpacing: "0.02em",
                            padding: "2px 6px",
                            backgroundColor: preset.bgOpacity > 0 ? `#000${Math.round(Math.min(1, preset.bgOpacity) * 255).toString(16).padStart(2, "0")}` : "transparent",
                            paintOrder: preset.strokeEnabled ? "stroke" : undefined,
                            WebkitTextStroke: preset.strokeEnabled ? `${Math.max(preset.strokeWidth * 0.18, 0.6)}px ${preset.strokeColor}` : undefined,
                          }}
                        >
                          SKIA
                        </span>
                      </span>
                      {(style.animation === preset.id || style.animation === preset.id.replace("skia_", "")) && (
                        <span className="absolute top-1.5 right-1.5 z-10 flex h-4 w-4 items-center justify-center rounded-full bg-amber-500 text-black shadow">
                          <Check className="h-2.5 w-2.5 stroke-[3]" />
                        </span>
                      )}
                    </span>
                    <span className="block px-2.5 py-1.5">
                      <span className="flex items-center gap-1.5">
                        <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: preset.color }} />
                        <span className={cn("truncate text-[10px] font-semibold", (style.animation === preset.id || style.animation === preset.id.replace("skia_", "")) ? "text-amber-300" : "text-zinc-300 group-hover:text-zinc-100")}>
                          {preset.name}
                        </span>
                      </span>
                      <span className="mt-0.5 block truncate text-[8px] text-zinc-600">{preset.desc}</span>
                    </span>
                  </button>
                ))}
              </div>
              <PaginationControls page={skiaHookPage} totalItems={SKIA_HOOK_PRESETS.length} onPageChange={setSkiaHookPage} label="presets" />
            </Section>

            <Section title="Hook Text">
              <textarea value={style.text} onChange={(e) => update({ text: e.target.value })} placeholder="Leave empty for AI-generated hook..." rows={2} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 resize-none focus:outline-none focus:border-zinc-500" />
            </Section>

            <Section title="Typography">
              <FontChips fonts={HOOK_FONT_SUGGESTIONS} active={style.fontFamily} onSelect={(fontFamily) => update({ fontFamily })} />
              <div className="grid grid-cols-3 gap-3 mt-3">
                <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={FONT_OPTIONS} />
                <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                <RangeInput label={`Size: ${style.fontSize}px`} min={24} max={96} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
              </div>
              <div className="flex gap-4 mt-3">
                <Checkbox label="UPPERCASE" checked={style.uppercase} onChange={(v) => update({ uppercase: v })} />
                <Checkbox label="Italic" checked={style.italic} onChange={(v) => update({ italic: v })} />
              </div>
            </Section>

            <Section title="Colors & GPU Effects">
              <div className="grid grid-cols-2 gap-3">
                <ColorPicker label="Text Color" value={style.color} onChange={(v) => update({ color: v })} />
                <ColorPicker label="Background" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
              </div>
              <RangeInput label={`BG Opacity: ${Math.round(style.bgOpacity * 100)}%`} min={0} max={100} value={Math.round(style.bgOpacity * 100)} onChange={(v) => update({ bgOpacity: v / 100 })} />
              <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text gradient" checked={style.gradientEnabled} onChange={(v) => update({ gradientEnabled: v })} />
                  {style.gradientEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="From" value={style.gradientFrom} onChange={(v) => update({ gradientFrom: v })} />
                      <ColorPicker label="To" value={style.gradientTo} onChange={(v) => update({ gradientTo: v })} />
                    </div>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text glow" checked={style.glowEnabled} onChange={(v) => update({ glowEnabled: v })} />
                  {style.glowEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Glow Color" value={style.glowColor} onChange={(v) => update({ glowColor: v })} />
                      <RangeInput label={`Glow Size: ${style.glowSize}px`} min={5} max={70} value={style.glowSize} onChange={(v) => update({ glowSize: v })} />
                    </div>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text outline" checked={style.strokeEnabled} onChange={(v) => update({ strokeEnabled: v })} />
                  {style.strokeEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Outline" value={style.strokeColor} onChange={(v) => update({ strokeColor: v })} />
                      <RangeInput label={`Width: ${style.strokeWidth}px`} min={1} max={10} value={style.strokeWidth} onChange={(v) => update({ strokeWidth: v })} />
                    </div>
                  )}
                </div>
              </div>
            </Section>

            <Section title="Position">
              <div className="grid grid-cols-3 gap-2 mb-3">
                {(["top", "center", "bottom"] as const).map(p => {
                  const isSelected = (style.positionY != null ? (style.positionY <= 35 ? "top" : style.positionY >= 65 ? "bottom" : "center") : style.position) === p;
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => update({ position: p, positionY: p === "top" ? 20 : p === "bottom" ? 80 : 50 })}
                      className={cn(
                        "py-2 rounded-lg border text-[11px] font-medium capitalize transition-colors",
                        isSelected ? "border-amber-500 bg-amber-500/10 text-amber-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600"
                      )}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
              <RangeInput
                label={`Vertical: ${style.positionY}%`}
                min={5}
                max={95}
                value={style.positionY}
                onChange={(v) => update({
                  positionY: v,
                  position: v <= 35 ? "top" : v >= 65 ? "bottom" : "center",
                })}
              />
            </Section>

            <Section title="Timing">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3 border border-zinc-800 rounded-lg bg-zinc-950/50">
                <RangeInput label={`Duration: ${style.duration}s`} min={15} max={60} value={Math.round(style.duration * 10)} onChange={(v) => update({ duration: v / 10 })} />
                <RangeInput label={`Fade In: ${style.fadeIn}s`} min={1} max={15} value={Math.round(style.fadeIn * 10)} onChange={(v) => update({ fadeIn: v / 10 })} />
                <RangeInput label={`Fade Out: ${style.fadeOut}s`} min={1} max={15} value={Math.round(style.fadeOut * 10)} onChange={(v) => update({ fadeOut: v / 10 })} />
              </div>
            </Section>
          </>
        ) : (
          <>
            {/* Remotion Quick Presets */}
            <Section title="Quick Presets">
              <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-2">
                {visibleHookPresets.map(p => (
                  <HookPresetCard
                    key={p.id}
                    preset={p}
                    active={activePreset === p.id}
                    onClick={() => {
                      onChange({ ...DEFAULT_HOOK_STYLE, ...p.style, text: style.text, engine: "remotion" } as HookStyle);
                      setActivePreset(p.id);
                    }}
                  />
                ))}
              </div>
              <PaginationControls page={presetPage} totalItems={HOOK_PRESETS.length} onPageChange={setPresetPage} label="presets" />
            </Section>

            <Section title="Hook Text">
              <textarea value={style.text} onChange={(e) => update({ text: e.target.value })} placeholder="Leave empty for AI-generated hook..." rows={2} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 resize-none focus:outline-none focus:border-zinc-500" />
            </Section>

            <Section title="Animation & Timing">
              <div className="mb-3 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950/70">
                <div className="flex items-center justify-between gap-3 border-b border-zinc-800 px-3 py-2">
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold text-zinc-200">{activeAnimation.label}</p>
                    <p className="truncate text-[9px] text-zinc-500">{activeAnimation.desc}</p>
                  </div>
                  <span className="rounded-md px-2 py-1 text-[9px] font-black" style={{ color: activeAnimation.accent, backgroundColor: `${activeAnimation.accent}18`, border: `1px solid ${activeAnimation.accent}44` }}>{activeAnimation.mood}</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3">
                  <RangeInput label={`Duration: ${style.duration}s`} min={15} max={60} value={Math.round(style.duration * 10)} onChange={(v) => update({ duration: v / 10 })} />
                  <RangeInput label={`Fade In: ${style.fadeIn}s`} min={1} max={15} value={Math.round(style.fadeIn * 10)} onChange={(v) => update({ fadeIn: v / 10 })} />
                  <RangeInput label={`Fade Out: ${style.fadeOut}s`} min={1} max={15} value={Math.round(style.fadeOut * 10)} onChange={(v) => update({ fadeOut: v / 10 })} />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3 gap-2">
                {visibleHookAnimations.map(a => (
                  <TimingOptionCard key={a} meta={HOOK_ANIMATION_META[a] || HOOK_ANIMATION_META.podcast_lower_third} active={style.animation === a} onClick={() => update({ animation: a })} kind="hook" />
                ))}
              </div>
              <PaginationControls page={animationPage} totalItems={HOOK_ANIMATIONS.length} onPageChange={setAnimationPage} label="animations" />
            </Section>

            <Section title="Hook Components">
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3 space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Checkbox label="Show badge / category label" checked={style.badgeEnabled} onChange={(v) => update({ badgeEnabled: v })} disabled={!capabilities.badge} />
                    {!capabilities.badge && <UnavailableHint text="Style ini tidak memakai badge." />}
                    {style.badgeEnabled && capabilities.badge && (
                      <input
                        type="text"
                        value={style.badgeText}
                        onChange={(e) => update({ badgeText: e.target.value })}
                        placeholder="Badge text (mis: INTERNASIONAL, HOT TAKE)"
                        className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:border-zinc-500 focus:outline-none"
                      />
                    )}
                  </div>
                  <div className="space-y-2">
                    <Checkbox label="Decorative motion elements" checked={style.decorativeElements} onChange={(v) => update({ decorativeElements: v })} disabled={!capabilities.decorative} />
                    {!capabilities.decorative && <UnavailableHint text="Style ini memakai motion utama tanpa dekorasi tambahan." />}
                    <RangeInput label={`Motion: ${style.motionIntensity.toFixed(1)}x`} min={0} max={20} value={Math.round(style.motionIntensity * 10)} onChange={(v) => update({ motionIntensity: v / 10 })} />
                  </div>
                </div>

                {/* Footer / Source Bar Label (e.g. READ MORE AT chatgpt.com) */}
                <div className="pt-2 border-t border-zinc-800/80">
                  <div className="space-y-2">
                    <Checkbox label="Show footer / source label" checked={style.footerEnabled !== false} onChange={(v) => update({ footerEnabled: v })} disabled={!capabilities.footer} />
                    {!capabilities.footer && <UnavailableHint text="Style ini tidak memakai footer bar." />}
                    {style.footerEnabled !== false && capabilities.footer && (
                      <input
                        type="text"
                        value={style.footerText || ""}
                        onChange={(e) => update({ footerText: e.target.value })}
                        placeholder="Footer text (mis: READ MORE AT chatgpt.com, SWIPE UP FOR MORE)"
                        className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:border-zinc-500 focus:outline-none"
                      />
                    )}
                  </div>
                </div>
              </div>
            </Section>

            <Section title="Typography">
              <FontChips fonts={HOOK_FONT_SUGGESTIONS} active={style.fontFamily} onSelect={(fontFamily) => update({ fontFamily })} />
              <div className="grid grid-cols-3 gap-3 mt-3">
                <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={FONT_OPTIONS} />
                <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                <SelectSmall label="Align" value={style.textAlign} onChange={(v) => update({ textAlign: v as any })} options={["center", "left", "right"]} />
              </div>
              <div className="grid grid-cols-3 gap-3 mt-3">
                <RangeInput label={`Size: ${style.fontSize}px`} min={24} max={96} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
                <RangeInput label={`Spacing: ${style.letterSpacing}px`} min={0} max={12} value={style.letterSpacing} onChange={(v) => update({ letterSpacing: v })} />
                <RangeInput label={`Line H: ${style.lineHeight}`} min={10} max={24} value={Math.round(style.lineHeight * 10)} onChange={(v) => update({ lineHeight: v / 10 })} />
              </div>
              <div className="flex gap-4 mt-3">
                <Checkbox label="UPPERCASE" checked={style.uppercase} onChange={(v) => update({ uppercase: v })} />
                <Checkbox label="Italic" checked={style.italic} onChange={(v) => update({ italic: v })} />
              </div>
            </Section>

            <Section title="Colors & Effects">
              <div className="grid grid-cols-2 gap-3">
                <ColorPicker label="Text Color" value={style.color} onChange={(v) => update({ color: v })} />
                <ColorPicker label="Background" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
                {isModernHookStyle && <ColorPicker label="Template Accent" value={style.lineColor} onChange={(v) => update({ lineColor: v })} />}
              </div>
              <RangeInput label={`BG Opacity: ${Math.round(style.bgOpacity * 100)}%`} min={0} max={100} value={Math.round(style.bgOpacity * 100)} onChange={(v) => update({ bgOpacity: v / 100 })} />
              <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text gradient" checked={style.gradientEnabled} onChange={(v) => update({ gradientEnabled: v })} disabled={!capabilities.gradient} />
                  {!capabilities.gradient && <UnavailableHint text="Style ini memakai warna solid dari template." />}
                  {style.gradientEnabled && capabilities.gradient && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="From" value={style.gradientFrom} onChange={(v) => update({ gradientFrom: v })} />
                      <ColorPicker label="To" value={style.gradientTo} onChange={(v) => update({ gradientTo: v })} />
                      <RangeInput label={`Angle: ${style.gradientAngle}deg`} min={0} max={360} value={style.gradientAngle} onChange={(v) => update({ gradientAngle: v })} />
                    </div>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text shadow" checked={style.shadowEnabled} onChange={(v) => update({ shadowEnabled: v })} />
                  {style.shadowEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Shadow" value={style.shadowColor} onChange={(v) => update({ shadowColor: v })} />
                      <RangeInput label={`Blur: ${style.shadowBlur}`} min={0} max={40} value={style.shadowBlur} onChange={(v) => update({ shadowBlur: v })} />
                      <div className="grid grid-cols-2 gap-2">
                        <RangeInput label={`X: ${style.shadowX}`} min={-10} max={10} value={style.shadowX} onChange={(v) => update({ shadowX: v })} />
                        <RangeInput label={`Y: ${style.shadowY}`} min={-10} max={10} value={style.shadowY} onChange={(v) => update({ shadowY: v })} />
                      </div>
                    </div>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text glow" checked={style.glowEnabled} onChange={(v) => update({ glowEnabled: v })} />
                  {style.glowEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Glow Color" value={style.glowColor} onChange={(v) => update({ glowColor: v })} />
                      <RangeInput label={`Glow Size: ${style.glowSize}px`} min={5} max={70} value={style.glowSize} onChange={(v) => update({ glowSize: v })} />
                    </div>
                  )}
                </div>
              </div>
            </Section>

            <Section title="Position">
              <div className="grid grid-cols-3 gap-2 mb-3">
                {(["top", "center", "bottom"] as const).map(p => {
                  const isSelected = (style.positionY != null ? (style.positionY <= 35 ? "top" : style.positionY >= 65 ? "bottom" : "center") : style.position) === p;
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => update({ position: p, positionY: p === "top" ? 20 : p === "bottom" ? 80 : 50 })}
                      className={cn(
                        "py-2 rounded-lg border text-[11px] font-medium capitalize transition-colors",
                        isSelected ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600"
                      )}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
              <RangeInput
                label={`Vertical: ${style.positionY}%`}
                min={5}
                max={95}
                value={style.positionY}
                onChange={(v) => update({
                  positionY: v,
                  position: v <= 35 ? "top" : v >= 65 ? "bottom" : "center",
                })}
              />
            </Section>

            <Section title="Accent Line">
              <Checkbox label="Enable accent line" checked={style.lineEnabled} onChange={(v) => update({ lineEnabled: v })} />
              {style.lineEnabled && (
                <div className="mt-3 space-y-3">
                  <div className="grid grid-cols-7 gap-2">
                    {(["top", "center-h", "bottom", "left", "center-v", "right", "auto-bottom"] as const).map(p => (
                      <button key={p} type="button" onClick={() => update({ linePosition: p })} className={cn("py-1.5 rounded-lg border text-[10px] font-medium capitalize transition-colors", style.linePosition === p ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-700 text-zinc-400")}>{p.replace("-h", " <>").replace("-v", " ^").replace("auto-bottom", "Auto")}</button>
                    ))}
                  </div>
                  <Checkbox label="Auto-adjust width (match text)" checked={style.lineAutoWidth} onChange={(v) => update({ lineAutoWidth: v, lineWidth: v ? 80 : style.lineWidth })} />
                  <div className="grid grid-cols-4 gap-3">
                    <ColorPicker label="Color" value={style.lineColor} onChange={(v) => update({ lineColor: v })} />
                    {!style.lineAutoWidth && <RangeInput label={`Width: ${style.lineWidth}%`} min={10} max={100} value={style.lineWidth} onChange={(v) => update({ lineWidth: v })} />}
                    <RangeInput label={`Thick: ${style.lineThickness}px`} min={1} max={12} value={style.lineThickness} onChange={(v) => update({ lineThickness: v })} />
                    <RangeInput label={`Offset: ${style.lineOffset}px`} min={0} max={40} value={style.lineOffset} onChange={(v) => update({ lineOffset: v })} />
                  </div>
                </div>
              )}
            </Section>

            <Section title="Text Box / Outline">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  {capabilities.panel ? (
                    <div className="space-y-2">
                      <p className="text-[10px] font-medium text-zinc-400">Panel / accent surface</p>
                      <ColorPicker label="Panel Color" value={style.boxColor} onChange={(v) => update({ boxColor: v })} />
                      <RangeInput label={`Opacity: ${Math.round(style.boxOpacity * 100)}%`} min={0} max={100} value={Math.round(style.boxOpacity * 100)} onChange={(v) => update({ boxOpacity: v / 100 })} />
                    </div>
                  ) : isModernHookStyle ? (
                    <UnavailableHint text="Template hook ini tidak memakai box/panel tambahan." />
                  ) : (
                    <>
                      <Checkbox label="Box around text" checked={style.boxEnabled} onChange={(v) => update({ boxEnabled: v })} />
                      {style.boxEnabled && (
                        <div className="mt-2 space-y-2">
                          <ColorPicker label="Box Color" value={style.boxColor} onChange={(v) => update({ boxColor: v })} />
                          <RangeInput label={`Opacity: ${Math.round(style.boxOpacity * 100)}%`} min={0} max={100} value={Math.round(style.boxOpacity * 100)} onChange={(v) => update({ boxOpacity: v / 100 })} />
                          <RangeInput label={`Padding: ${style.boxPadding}px`} min={4} max={56} value={style.boxPadding} onChange={(v) => update({ boxPadding: v })} />
                          <RangeInput label={`Radius: ${style.boxRadius}px`} min={0} max={28} value={style.boxRadius} onChange={(v) => update({ boxRadius: v })} />
                        </div>
                      )}
                    </>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text outline" checked={style.strokeEnabled} onChange={(v) => update({ strokeEnabled: v })} disabled={!capabilities.outline} />
                  {!capabilities.outline && <UnavailableHint text="Outline tidak dipakai oleh template hook ini." />}
                  {style.strokeEnabled && capabilities.outline && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Outline" value={style.strokeColor} onChange={(v) => update({ strokeColor: v })} />
                      <RangeInput label={`Width: ${style.strokeWidth}px`} min={1} max={10} value={style.strokeWidth} onChange={(v) => update({ strokeWidth: v })} />
                    </div>
                  )}
                </div>
              </div>
            </Section>
          </>
        )}
      </div>

      <div className="lg:col-span-4 flex min-h-0 flex-col items-center justify-center overflow-hidden bg-zinc-950 p-4">
        {engine === "hyperframes" ? (
          <HfLivePreview
            preset={hfPreset}
            sample={style.text || hfPreset?.preview || "HOOK TEXT"}
            kind="hook"
            aspectRatio={aspectRatio}
            thumbnailUrl={thumbnailUrl}
            canvas={canvas}
          />
        ) : engine === "ffmpeg" ? (
          <>
            <div className="mb-3 flex w-full items-center justify-between gap-2">
              <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
              <span className="rounded-md border border-purple-500/30 bg-purple-500/10 px-2 py-1 text-[9px] text-purple-300">FFmpeg Drawtext</span>
            </div>
            <CanvasPreviewFrame canvas={canvas} thumbnailUrl={thumbnailUrl}>
              <div className="absolute left-0 right-0 flex items-center justify-center px-3 pointer-events-none" style={{ top: `${style.positionY}%`, transform: "translateY(-50%)" }}>
                <p style={{ fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16), fontWeight: Number(style.fontWeight), fontFamily: style.fontFamily === "monospace" ? "monospace" : `'${style.fontFamily}', sans-serif`, color: style.color, textTransform: style.uppercase ? "uppercase" as const : "none" as const, textAlign: "center" as const, maxWidth: "92%", whiteSpace: "pre-line" as const, wordBreak: "break-word" as const, padding: "4px 8px", backgroundColor: style.bgOpacity > 0 ? `${style.bgColor || "black"}${Math.round(style.bgOpacity * 255).toString(16).padStart(2, "0")}` : "transparent", paintOrder: style.strokeEnabled ? "stroke" as const : undefined, WebkitTextStroke: style.strokeEnabled ? `${Math.max(style.strokeWidth * 0.25, 0.6)}px ${style.strokeColor}` : undefined, textShadow: style.shadowEnabled ? `2px 2px 0px ${style.shadowColor}` : undefined }}>
                  {style.text || getHookPreviewSample(style.animation || "zoom_punch")}
                </p>
              </div>
              <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-600 z-10">ffmpeg {style.animation || "zoom_punch"} | {style.duration}s</p>
            </CanvasPreviewFrame>
            <div className="mt-3 grid w-full grid-cols-2 gap-2 text-[10px]">
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Font</span><p className="truncate text-zinc-300">{style.fontFamily}</p></div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Color</span><p className="truncate" style={{ color: style.color }}>{style.color}</p></div>
            </div>
          </>
        ) : engine === "skia" ? (
          <SkiaHookLivePreview style={style} thumbnailUrl={thumbnailUrl} aspectRatio={aspectRatio} canvas={canvas} />
        ) : (
          <>
            <div className="mb-3 flex w-full items-center justify-between gap-2">
              <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
              <span className="rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-[9px] text-zinc-400">{activeAnimation.label}</span>
            </div>
            <CanvasPreviewFrame canvas={canvas} thumbnailUrl={thumbnailUrl}>
              <HookPreviewRenderer style={style} />
              {style.lineEnabled && <AccentLinePreview style={style} />}
              <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-600 z-10">{style.animation.replace(/_/g, " ")} | {style.duration}s</p>
            </CanvasPreviewFrame>
            <div className="mt-3 grid w-full grid-cols-2 gap-2 text-[10px]">
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Font</span><p className="truncate text-zinc-300">{style.fontFamily}</p></div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Style</span><p className="truncate text-zinc-300">{activeAnimation.label}</p></div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Subtitle Editor ─────────────────────────────────────────────────────────

export function SubtitleEditor({
  style,
  onChange,
  isSuperadmin = false,
  isPremium = false,
  userFeatures = [],
  aspectRatio = "9:16",
  thumbnailUrl,
  canvasBackground,
}: {
  style: SubtitleStyle;
  onChange: (style: SubtitleStyle) => void;
  isSuperadmin?: boolean;
  isPremium?: boolean;
  userFeatures?: string[];
  aspectRatio?: string;
  thumbnailUrl?: string;
  canvasBackground?: any;
}) {
  const engine = style.engine || "remotion";
  const [activeWordIdx, setActiveWordIdx] = useState(0);
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [newWord, setNewWord] = useState("");
  const [presetPage, setPresetPage] = useState(1);
  const [timingPage, setTimingPage] = useState(1);
  const hfId = style.hf_template || defaultHfSubtitleId();
  const hfPreset = HF_SUBTITLE_STYLES.find((h) => h.id === hfId) || HF_SUBTITLE_STYLES[0];
  useGoogleFont(style.fontFamily);
  if (style.dualStyleEnabled && style.highlightFontFamily) {
    useGoogleFont(style.highlightFontFamily);
  }
  const update = (patch: Partial<SubtitleStyle>) => onChange({ ...style, ...patch });

  function addHighlightWord() {
    if (newWord.trim() && !(style.highlightWords || []).includes(newWord.trim().toLowerCase())) {
      update({ highlightWords: [...(style.highlightWords || []), newWord.trim().toLowerCase()] });
      setNewWord("");
    }
  }
  const canvas = (aspectRatio === "16:9" || aspectRatio === "1:1")
    ? buildCanvasConfig(aspectRatio, {
      backgroundMode: canvasBackground?.mode || "template",
      templateId: canvasBackground?.templateId || "dark-studio",
      backgroundImageUrl: canvasBackground?.imageDataUrl || null,
    })
    : null;
  const outerAspect = "9/16";
  const subtitleTimingOptions: Array<
    { kind: "transition"; id: SubtitleStyle["lineTransition"]; meta: OptionMeta } |
    { kind: "animation"; id: SubtitleStyle["animationStyle"]; meta: OptionMeta }
  > = [
      { kind: "transition", id: "word_pop", meta: SUBTITLE_TRANSITION_META.word_pop },
      { kind: "transition", id: "emphasis", meta: SUBTITLE_TRANSITION_META.emphasis },
      { kind: "transition", id: "line_reveal", meta: SUBTITLE_TRANSITION_META.line_reveal },
      { kind: "animation", id: "pop", meta: SUBTITLE_ANIMATION_META.pop },
      { kind: "animation", id: "fade", meta: SUBTITLE_ANIMATION_META.fade },
      { kind: "animation", id: "slide", meta: SUBTITLE_ANIMATION_META.slide },
      { kind: "animation", id: "none", meta: SUBTITLE_ANIMATION_META.none },
    ];
  const [ffmpegSubPage, setFfmpegSubPage] = useState(1);
  const [skiaSubPage, setSkiaSubPage] = useState(1);
  const visibleSubtitlePresets = getPageItems(SUBTITLE_PRESETS, presetPage);
  const visibleSubtitleTiming = getPageItems(subtitleTimingOptions, timingPage);
  const visibleFfmpegSubs = getPageItems(FFMPEG_SUBTITLE_PRESETS, ffmpegSubPage);
  const visibleSkiaSubs = getPageItems(SKIA_SUBTITLE_PRESETS, skiaSubPage);
  const activeTimingMeta = SUBTITLE_TRANSITION_META[style.lineTransition] || SUBTITLE_ANIMATION_META[style.animationStyle];

  useEffect(() => {
    if (!isSuperadmin && (engine === "remotion" || engine === "hyperframes")) {
      update({ engine: "ffmpeg" });
    }
  }, [engine, isSuperadmin]);

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveWordIdx((prev) => (prev + 1) % 4);
    }, 800);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 h-full min-h-0 overflow-hidden">
      <div className="lg:col-span-8 p-4 overflow-y-auto space-y-4 border-r border-zinc-800 min-h-0">
        <Section title="Subtitle Toggle">
          <div className="flex items-center justify-between p-3.5 rounded-xl border border-zinc-800 bg-zinc-900/60 backdrop-blur">
            <div className="flex items-center gap-3">
              <div className={cn(
                "w-9 h-9 rounded-lg flex items-center justify-center border transition-colors",
                style.enabled !== false
                  ? "bg-purple-500/10 border-purple-500/30 text-purple-400"
                  : "bg-zinc-800/80 border-zinc-700 text-zinc-500"
              )}>
                {style.enabled !== false ? <Check className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
              </div>
              <div>
                <p className="text-xs font-semibold text-zinc-200">
                  {style.enabled !== false ? "Gunakan Subtitle (Active)" : "Subtitle Dinonaktifkan (Disabled)"}
                </p>
                <p className="text-[11px] text-zinc-400">
                  {style.enabled !== false
                    ? "Subtitle karaoke / word-pop akan dirender pada video final."
                    : "Video final akan dirender bersih tanpa subtitle overlay."}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => update({ enabled: style.enabled === false ? true : false })}
              className={cn(
                "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none",
                style.enabled !== false ? "bg-purple-600 ring-2 ring-purple-500/30" : "bg-zinc-700"
              )}
            >
              <span
                className={cn(
                  "pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out",
                  style.enabled !== false ? "translate-x-5" : "translate-x-0"
                )}
              />
            </button>
          </div>
        </Section>

        <Section title="Render Engine">
          <EnginePicker
            engine={engine}
            kind="subtitle"
            isSuperadmin={isSuperadmin}
            onChange={(e) => update({
              engine: e,
              hf_template: style.hf_template || defaultHfSubtitleId(),
            })}
          />
        </Section>

        {engine === "hyperframes" ? (
          <Section title="HyperFrames Subtitle Styles">
            <HfStyleGrid
              items={HF_SUBTITLE_STYLES}
              activeId={hfId}
              onSelect={(id) => update({ engine: "hyperframes", hf_template: id })}
            />
          </Section>
        ) : engine === "ffmpeg" ? (
          <>
            <Section title="FFmpeg Drawtext">
              <div className="rounded-lg border border-purple-500/20 bg-purple-500/5 p-3">
                <p className="text-[10px] text-purple-300 mb-1"><Zap className="inline w-3 h-3 mr-1" />Server-side render · no browser needed</p>
                <p className="text-[9px] text-zinc-500">FFmpeg drawtext subtitle. 12 Preset gaya subtitle dengan performa instan.</p>
              </div>
            </Section>

            <Section title="FFmpeg Subtitle Presets">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {visibleFfmpegSubs.map(p => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => {
                      update({
                        stylePreset: p.id,
                        color: p.color,
                        highlightColor: p.highlightColor,
                        fontFamily: p.fontFamily,
                        fontSize: p.fontSize,
                        fontWeight: p.fontWeight,
                        lineTransition: p.lineTransition,
                        strokeEnabled: p.strokeEnabled,
                        strokeWidth: p.strokeWidth,
                        strokeColor: p.strokeColor,
                        bgEnabled: p.bgEnabled,
                        bgColor: p.bgColor,
                        bgOpacity: p.bgOpacity,
                        bgRadius: p.bgRadius,
                        position: p.positionY <= 35 ? "top" : p.positionY >= 65 ? "bottom" : "center",
                        positionY: p.positionY,
                        uppercase: p.uppercase,
                        maxWordsPerLine: p.maxWordsPerLine,
                        engine: "ffmpeg",
                      });
                      setActivePreset(p.id);
                    }}
                    className={cn(
                      "group overflow-hidden rounded-xl border text-left transition-all p-3",
                      activePreset === p.id || style.stylePreset === p.id
                        ? "border-purple-500 bg-purple-500/10 ring-1 ring-purple-500/40"
                        : "border-zinc-700/80 bg-zinc-900/40 hover:border-zinc-500 hover:bg-zinc-900"
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[11px] font-semibold text-zinc-200">{p.name}</p>
                      <span className="rounded px-1.5 py-0.5 text-[8px] font-bold uppercase text-purple-400 bg-purple-500/10 border border-purple-500/30">
                        {p.category}
                      </span>
                    </div>
                    <p className="text-[9px] text-zinc-500 mt-1 line-clamp-2">{p.desc}</p>
                  </button>
                ))}
              </div>
              <PaginationControls page={ffmpegSubPage} totalItems={FFMPEG_SUBTITLE_PRESETS.length} onPageChange={setFfmpegSubPage} label="presets" />
            </Section>

            <Section title="Line Transition">
              <div className="grid grid-cols-3 gap-2">
                {([
                  { id: "word_pop", name: "Word Pop", desc: "Satu kata per frame" },
                  { id: "emphasis", name: "Emphasis", desc: "Highlight kata aktif" },
                  { id: "line_reveal", name: "Line Reveal", desc: "Full line timed" },
                ] as const).map(mode => (
                  <button
                    key={mode.id}
                    type="button"
                    onClick={() => update({ lineTransition: mode.id })}
                    className={cn(
                      "py-2 px-2 rounded-lg border text-center transition-colors",
                      style.lineTransition === mode.id
                        ? "border-purple-500 bg-purple-500/10"
                        : "border-zinc-700 hover:border-zinc-600"
                    )}
                  >
                    <p className="text-[10px] font-medium text-zinc-200">{mode.name}</p>
                    <p className="text-[8px] text-zinc-500 mt-0.5">{mode.desc}</p>
                  </button>
                ))}
              </div>
            </Section>

            <Section title="Typography">
              <FontChips fonts={SUBTITLE_FONT_SUGGESTIONS} active={style.fontFamily} onSelect={(fontFamily) => update({ fontFamily })} />
              <div className="grid grid-cols-3 gap-3 mt-3">
                <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={FONT_OPTIONS.filter((font) => font !== "monospace")} />
                <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                <RangeInput label={`Size: ${style.fontSize}px`} min={20} max={60} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
              </div>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <RangeInput label={`Spacing: ${style.letterSpacing}px`} min={0} max={8} value={style.letterSpacing} onChange={(v) => update({ letterSpacing: v })} />
                <RangeInput label={`Line H: ${style.lineHeight}`} min={10} max={24} value={Math.round(style.lineHeight * 10)} onChange={(v) => update({ lineHeight: v / 10 })} />
              </div>
              <div className="flex gap-4 mt-3">
                <Checkbox label="UPPERCASE" checked={style.uppercase} onChange={(v) => update({ uppercase: v, capitalize: v ? false : style.capitalize })} />
                <Checkbox label="Capitalize" checked={style.capitalize} onChange={(v) => update({ capitalize: v, uppercase: v ? false : style.uppercase })} />
                <Checkbox label="Italic" checked={style.italic} onChange={(v) => update({ italic: v })} />
              </div>
            </Section>

            <Section title="Colors">
              <div className="grid grid-cols-3 gap-3">
                <ColorPicker label="Text" value={style.color} onChange={(v) => update({ color: v })} />
                <ColorPicker label="Highlight" value={style.highlightColor} onChange={(v) => update({ highlightColor: v })} />
                <ColorPicker label="BG" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
              </div>
            </Section>

            <Section title="Background & Stroke">
              <div className="grid grid-cols-2 gap-3">
                <div><Checkbox label="Background" checked={style.bgEnabled} onChange={(v) => update({ bgEnabled: v })} /></div>
                <div><Checkbox label="Stroke/Outline" checked={style.strokeEnabled} onChange={(v) => update({ strokeEnabled: v })} /></div>
              </div>
              {style.bgEnabled && (
                <div className="grid grid-cols-3 gap-3 mt-2">
                  <RangeInput label={`Opacity: ${Math.round(style.bgOpacity * 100)}%`} min={0} max={100} value={Math.round(style.bgOpacity * 100)} onChange={(v) => update({ bgOpacity: v / 100 })} />
                  <RangeInput label={`Radius: ${style.bgRadius}px`} min={0} max={24} value={style.bgRadius} onChange={(v) => update({ bgRadius: v })} />
                  <RangeInput label={`Padding: ${style.bgPadding}px`} min={4} max={32} value={style.bgPadding} onChange={(v) => update({ bgPadding: v })} />
                </div>
              )}
              {style.strokeEnabled && (
                <div className="grid grid-cols-2 gap-3 mt-2">
                  <ColorPicker label="Stroke" value={style.strokeColor} onChange={(v) => update({ strokeColor: v })} />
                  <RangeInput label={`Width: ${style.strokeWidth}px`} min={1} max={6} value={style.strokeWidth} onChange={(v) => update({ strokeWidth: v })} />
                </div>
              )}
              <div className="mt-2"><Checkbox label="Text shadow" checked={style.shadowEnabled} onChange={(v) => update({ shadowEnabled: v })} /></div>
              {style.shadowEnabled && (
                <div className="grid grid-cols-2 gap-3 mt-2">
                  <ColorPicker label="Shadow" value={style.shadowColor} onChange={(v) => update({ shadowColor: v })} />
                  <RangeInput label={`Blur: ${style.shadowBlur}px`} min={0} max={20} value={style.shadowBlur} onChange={(v) => update({ shadowBlur: v })} />
                </div>
              )}
            </Section>

            <Section title="Position">
              <div className="grid grid-cols-3 gap-2 mb-3">
                {(["top", "center", "bottom"] as const).map(p => {
                  const isSelected = (style.positionY != null ? (style.positionY <= 35 ? "top" : style.positionY >= 65 ? "bottom" : "center") : style.position) === p;
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => update({ position: p, positionY: p === "top" ? 15 : p === "bottom" ? 85 : 50 })}
                      className={cn(
                        "py-2 rounded-lg border text-[11px] font-medium capitalize transition-colors",
                        isSelected ? "border-purple-500 bg-purple-500/10 text-purple-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600"
                      )}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
              <RangeInput
                label={`Vertical: ${style.positionY}%`}
                min={5}
                max={95}
                value={style.positionY}
                onChange={(v) => update({
                  positionY: v,
                  position: v <= 35 ? "top" : v >= 65 ? "bottom" : "center",
                })}
              />
            </Section>

            <Section title="Line Settings">
              <div className="grid grid-cols-2 gap-3">
                <RangeInput label={`Words/line: ${style.maxWordsPerLine}`} min={1} max={6} value={style.maxWordsPerLine} onChange={(v) => update({ maxWordsPerLine: v })} />
                <RangeInput label={`Word gap: ${style.wordSpacing}px`} min={2} max={18} value={style.wordSpacing} onChange={(v) => update({ wordSpacing: v })} />
              </div>
            </Section>
          </>
        ) : engine === "skia" ? (
          <>
            <Section title="Skia Render Engine">
              <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                <p className="text-[10px] text-amber-400 mb-1"><Palette className="inline w-3 h-3 mr-1" />Canvas GPU Rendering</p>
                <p className="text-[9px] text-zinc-500">Subtitle dengan 12 preset visual modern & clean (Glassmorphism, Clean Editorial, Podcast Pro, Kinetic Word Box, dll).</p>
              </div>
            </Section>

            <Section title="Skia Subtitle Presets">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {visibleSkiaSubs.map(p => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => {
                      update({
                        stylePreset: p.id,
                        color: p.color,
                        highlightColor: p.highlightColor,
                        fontFamily: p.fontFamily,
                        fontSize: p.fontSize,
                        fontWeight: p.fontWeight,
                        uppercase: p.uppercase,
                        lineTransition: p.lineTransition,
                        gradientEnabled: p.gradientEnabled,
                        gradientFrom: p.gradientFrom,
                        gradientTo: p.gradientTo,
                        glowEnabled: p.glowEnabled,
                        glowColor: p.glowColor,
                        position: p.positionY <= 35 ? "top" : p.positionY >= 65 ? "bottom" : "center",
                        positionY: p.positionY,
                        maxWordsPerLine: p.maxWordsPerLine,
                        engine: "skia",
                      });
                      setActivePreset(p.id);
                    }}
                    className={cn(
                      "group overflow-hidden rounded-xl border text-left transition-all p-3",
                      activePreset === p.id || style.stylePreset === p.id
                        ? "border-amber-500 bg-amber-500/10 ring-1 ring-amber-500/40"
                        : "border-zinc-700/80 bg-zinc-900/40 hover:border-zinc-500 hover:bg-zinc-900"
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[11px] font-semibold text-zinc-200">{p.name}</p>
                      <span className="rounded px-1.5 py-0.5 text-[8px] font-bold uppercase text-amber-400 bg-amber-500/10 border border-amber-500/30">
                        {p.category}
                      </span>
                    </div>
                    <p className="text-[9px] text-zinc-500 mt-1 line-clamp-2">{p.desc}</p>
                  </button>
                ))}
              </div>
              <PaginationControls page={skiaSubPage} totalItems={SKIA_SUBTITLE_PRESETS.length} onPageChange={setSkiaSubPage} label="presets" />
            </Section>

            <Section title="Line Transition">
              <div className="grid grid-cols-3 gap-2">
                {([
                  { id: "karaoke", name: "Karaoke", desc: "Per-word highlight" },
                  { id: "word_pop", name: "Word Pop", desc: "Satu kata per frame" },
                  { id: "line_reveal", name: "Line Reveal", desc: "Full line reveal" },
                ] as const).map(mode => (
                  <button
                    key={mode.id}
                    type="button"
                    onClick={() => update({ lineTransition: mode.id })}
                    className={cn(
                      "py-2 px-2 rounded-lg border text-center transition-colors",
                      style.lineTransition === mode.id
                        ? "border-amber-500 bg-amber-500/10"
                        : "border-zinc-700 hover:border-zinc-600"
                    )}
                  >
                    <p className="text-[10px] font-medium text-zinc-200">{mode.name}</p>
                    <p className="text-[8px] text-zinc-500 mt-0.5">{mode.desc}</p>
                  </button>
                ))}
              </div>
            </Section>

            <Section title="Typography">
              <FontChips fonts={SUBTITLE_FONT_SUGGESTIONS} active={style.fontFamily} onSelect={(fontFamily) => update({ fontFamily })} />
              <div className="grid grid-cols-3 gap-3 mt-3">
                <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={FONT_OPTIONS.filter((font) => font !== "monospace")} />
                <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                <RangeInput label={`Size: ${style.fontSize}px`} min={20} max={60} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
              </div>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <RangeInput label={`Spacing: ${style.letterSpacing}px`} min={0} max={8} value={style.letterSpacing} onChange={(v) => update({ letterSpacing: v })} />
                <RangeInput label={`Line H: ${style.lineHeight}`} min={10} max={24} value={Math.round(style.lineHeight * 10)} onChange={(v) => update({ lineHeight: v / 10 })} />
              </div>
              <div className="flex gap-4 mt-3">
                <Checkbox label="UPPERCASE" checked={style.uppercase} onChange={(v) => update({ uppercase: v, capitalize: v ? false : style.capitalize })} />
                <Checkbox label="Italic" checked={style.italic} onChange={(v) => update({ italic: v })} />
              </div>
            </Section>

            <Section title="Colors & GPU Effects">
              <div className="grid grid-cols-3 gap-3">
                <ColorPicker label="Text" value={style.color} onChange={(v) => update({ color: v })} />
                <ColorPicker label="Highlight" value={style.highlightColor} onChange={(v) => update({ highlightColor: v })} />
                <ColorPicker label="BG" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
              </div>
              <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Glow shader" checked={!!style.glowEnabled} onChange={(v) => update({ glowEnabled: v })} />
                  {style.glowEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Glow Color" value={style.glowColor || "#00FFFF"} onChange={(v) => update({ glowColor: v })} />
                    </div>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Gradient shader" checked={!!style.gradientEnabled} onChange={(v) => update({ gradientEnabled: v })} />
                  {style.gradientEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Grad From" value={style.gradientFrom || "#667EEA"} onChange={(v) => update({ gradientFrom: v })} />
                      <ColorPicker label="Grad To" value={style.gradientTo || "#764BA2"} onChange={(v) => update({ gradientTo: v })} />
                    </div>
                  )}
                </div>
              </div>
            </Section>

            <Section title="Backdrop & Card Capsule">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Enable Card/Pill Capsule" checked={style.bgEnabled} onChange={(v) => update({ bgEnabled: v })} />
                  {style.bgEnabled && (
                    <div className="mt-3 space-y-3">
                      <ColorPicker label="Capsule Color" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
                      <RangeInput label={`Opacity: ${Math.round(style.bgOpacity * 100)}%`} min={10} max={100} value={Math.round(style.bgOpacity * 100)} onChange={(v) => update({ bgOpacity: v / 100 })} />
                      <RangeInput label={`Radius: ${style.bgRadius}px`} min={0} max={40} value={style.bgRadius} onChange={(v) => update({ bgRadius: v })} />
                      <RangeInput label={`Padding: ${style.bgPadding}px`} min={4} max={32} value={style.bgPadding} onChange={(v) => update({ bgPadding: v })} />
                    </div>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Active Word Scale" checked={style.highlightBold} onChange={(v) => update({ highlightBold: v })} />
                  <div className="mt-3 space-y-3">
                    <RangeInput label={`Highlight Scale: ${style.highlightScale.toFixed(1)}x`} min={10} max={16} value={Math.round(style.highlightScale * 10)} onChange={(v) => update({ highlightScale: v / 10 })} />
                    <Checkbox label="Text Outline / Stroke" checked={style.strokeEnabled} onChange={(v) => update({ strokeEnabled: v })} />
                    {style.strokeEnabled && (
                      <div className="mt-2 space-y-2">
                        <ColorPicker label="Outline Color" value={style.strokeColor} onChange={(v) => update({ strokeColor: v })} />
                        <RangeInput label={`Width: ${style.strokeWidth}px`} min={1} max={8} value={style.strokeWidth} onChange={(v) => update({ strokeWidth: v })} />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </Section>

            <Section title="Position">
              <div className="grid grid-cols-3 gap-2 mb-3">
                {(["top", "center", "bottom"] as const).map(p => {
                  const isSelected = (style.positionY != null ? (style.positionY <= 35 ? "top" : style.positionY >= 65 ? "bottom" : "center") : style.position) === p;
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => update({ position: p, positionY: p === "top" ? 15 : p === "bottom" ? 85 : 50 })}
                      className={cn(
                        "py-2 rounded-lg border text-[11px] font-medium capitalize transition-colors",
                        isSelected ? "border-amber-500 bg-amber-500/10 text-amber-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600"
                      )}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
              <RangeInput
                label={`Vertical: ${style.positionY}%`}
                min={5}
                max={95}
                value={style.positionY}
                onChange={(v) => update({
                  positionY: v,
                  position: v <= 35 ? "top" : v >= 65 ? "bottom" : "center",
                })}
              />
            </Section>

            <Section title="Line Settings">
              <div className="grid grid-cols-2 gap-3">
                <RangeInput label={`Words/line: ${style.maxWordsPerLine}`} min={1} max={6} value={style.maxWordsPerLine} onChange={(v) => update({ maxWordsPerLine: v })} />
                <RangeInput label={`Word gap: ${style.wordSpacing}px`} min={2} max={18} value={style.wordSpacing} onChange={(v) => update({ wordSpacing: v })} />
              </div>
            </Section>
          </>
        ) : (
          <>
            <Section title="Quick Presets">
              <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-2">
                {visibleSubtitlePresets.map(p => (
                  <SubtitlePresetCard
                    key={p.id}
                    preset={p}
                    active={activePreset === p.id}
                    onClick={() => {
                      onChange({ ...DEFAULT_SUBTITLE_STYLE, ...p.style, highlightWords: style.highlightWords, engine: "remotion" } as SubtitleStyle);
                      setActivePreset(p.id);
                    }}
                  />
                ))}
              </div>
              <PaginationControls page={presetPage} totalItems={SUBTITLE_PRESETS.length} onPageChange={setPresetPage} label="presets" />
            </Section>

            <Section title="Animation & Timing">
              <div className="mb-3 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950/70">
                <div className="flex items-center justify-between gap-3 border-b border-zinc-800 px-3 py-2">
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold text-zinc-200">{activeTimingMeta.label}</p>
                    <p className="truncate text-[9px] text-zinc-500">{activeTimingMeta.desc}</p>
                  </div>
                  <span className="rounded-md px-2 py-1 text-[9px] font-black" style={{ color: activeTimingMeta.accent, backgroundColor: `${activeTimingMeta.accent}18`, border: `1px solid ${activeTimingMeta.accent}44` }}>{activeTimingMeta.mood}</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3">
                  <RangeInput label={`Speed: ${style.animationSpeed.toFixed(1)}x`} min={5} max={20} value={Math.round(style.animationSpeed * 10)} onChange={(v) => update({ animationSpeed: v / 10 })} />
                  <RangeInput label={`Words/line: ${style.maxWordsPerLine}`} min={1} max={6} value={style.maxWordsPerLine} onChange={(v) => update({ maxWordsPerLine: v })} />
                  <RangeInput label={`Word gap: ${style.wordSpacing}px`} min={2} max={18} value={style.wordSpacing} onChange={(v) => update({ wordSpacing: v })} />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3 gap-2">
                {visibleSubtitleTiming.map((option) => (
                  <div key={`${option.kind}-${option.id}`} className="relative">
                    <TimingOptionCard
                      meta={option.meta}
                      active={option.kind === "transition" ? style.lineTransition === option.id : style.animationStyle === option.id}
                      onClick={() => option.kind === "transition" ? update({ lineTransition: option.id }) : update({ animationStyle: option.id })}
                      kind={option.kind === "transition" ? "line" : "motion"}
                    />
                  </div>
                ))}
              </div>
              <PaginationControls page={timingPage} totalItems={subtitleTimingOptions.length} onPageChange={setTimingPage} label="timing options" />
            </Section>

            <Section title="Typography">
              <FontChips fonts={SUBTITLE_FONT_SUGGESTIONS} active={style.fontFamily} onSelect={(fontFamily) => update({ fontFamily })} />
              <div className="grid grid-cols-3 gap-3 mt-3">
                <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={FONT_OPTIONS.filter((font) => font !== "monospace")} />
                <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                <RangeInput label={`Size: ${style.fontSize}px`} min={20} max={60} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
              </div>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <RangeInput label={`Spacing: ${style.letterSpacing}px`} min={0} max={8} value={style.letterSpacing} onChange={(v) => update({ letterSpacing: v })} />
                <RangeInput label={`Line H: ${style.lineHeight}`} min={10} max={24} value={Math.round(style.lineHeight * 10)} onChange={(v) => update({ lineHeight: v / 10 })} />
              </div>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <RangeInput
                  label={`Opacity: ${Math.round((style.textOpacity ?? 1.0) * 100)}%`}
                  min={20}
                  max={100}
                  value={Math.round((style.textOpacity ?? 1.0) * 100)}
                  onChange={(v) => update({ textOpacity: v / 100 })}
                />
                <div>
                  <p className="text-[9px] text-zinc-400 mb-1">Alignment</p>
                  <div className="grid grid-cols-3 gap-1">
                    {(["left", "center", "right"] as const).map((align) => (
                      <button
                        key={align}
                        type="button"
                        onClick={() => update({ textAlign: align })}
                        className={cn(
                          "py-1 rounded border text-[10px] capitalize transition-colors",
                          (style.textAlign || "center") === align
                            ? "border-purple-500 bg-purple-500/20 text-purple-300 font-bold"
                            : "border-zinc-700 text-zinc-400 hover:border-zinc-600"
                        )}
                      >
                        {align}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex gap-4 mt-3">
                <Checkbox label="UPPERCASE" checked={style.uppercase} onChange={(v) => update({ uppercase: v, capitalize: v ? false : style.capitalize })} />
                <Checkbox label="Capitalize" checked={style.capitalize} onChange={(v) => update({ capitalize: v, uppercase: v ? false : style.uppercase })} />
                <Checkbox label="Italic" checked={style.italic} onChange={(v) => update({ italic: v })} />
              </div>
            </Section>

            <Section title="Colors">
              <div className="grid grid-cols-3 gap-3">
                <ColorPicker label="Text" value={style.color} onChange={(v) => update({ color: v })} />
                <ColorPicker label="Highlight" value={style.highlightColor} onChange={(v) => update({ highlightColor: v })} />
                <ColorPicker label="BG" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
              </div>
            </Section>

            <Section title="Highlight Effect">
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 mb-3">
                {(["scale", "underline", "background", "strikethrough"] as const).map(s => (
                  <MetaTile key={s} meta={HIGHLIGHT_STYLE_META[s]} active={style.highlightStyle === s} onClick={() => update({ highlightStyle: s })} />
                ))}
              </div>
              <div className="grid grid-cols-3 gap-3">
                <RangeInput label={`Scale: ${style.highlightScale.toFixed(1)}x`} min={10} max={20} value={Math.round(style.highlightScale * 10)} onChange={(v) => update({ highlightScale: v / 10 })} />
                <div className="flex flex-col justify-end"><Checkbox label="Bold" checked={style.highlightBold} onChange={(v) => update({ highlightBold: v })} /></div>
                <div className="flex flex-col justify-end"><Checkbox label="Glow" checked={style.highlightGlow} onChange={(v) => update({ highlightGlow: v })} /></div>
              </div>
              {style.highlightGlow && (
                <div className="grid grid-cols-2 gap-3 mt-2">
                  <ColorPicker label="Glow Color" value={style.highlightGlowColor} onChange={(v) => update({ highlightGlowColor: v })} />
                </div>
              )}
            </Section>

            <Section title="Dual Font Style (Highlight Words)">
              <FeatureLock featureName="Dual Font Style" featureCode="dual_subtitle" isSuperadmin={isSuperadmin} isPremium={isPremium} userFeatures={userFeatures}>
                <Checkbox label="Use separate style for highlight words" checked={style.dualStyleEnabled} onChange={(v) => update({ dualStyleEnabled: v })} />
                <p className="text-[9px] text-zinc-600 mt-1 mb-2">Kata-kata penting (MAKANYA, JANGAN, dll) akan menggunakan font & style berbeda dari teks normal.</p>
                {style.dualStyleEnabled && (
                  <div className="mt-3 p-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 space-y-3">
                    <p className="text-[10px] text-emerald-400 font-medium uppercase tracking-wider">Highlight Word Style</p>
                    <FontChips fonts={HIGHLIGHT_FONT_SUGGESTIONS} active={style.highlightFontFamily} onSelect={(highlightFontFamily) => update({ highlightFontFamily })} />
                    <div className="grid grid-cols-3 gap-3">
                      <SelectSmall label="Font" value={style.highlightFontFamily} onChange={(v) => update({ highlightFontFamily: v })} options={FONT_OPTIONS.filter((font) => font !== "monospace")} />
                      <SelectSmall label="Weight" value={style.highlightFontWeight} onChange={(v) => update({ highlightFontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                      <RangeInput label={`Size: ${style.highlightFontSize}px`} min={24} max={64} value={style.highlightFontSize} onChange={(v) => update({ highlightFontSize: v })} />
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                      <RangeInput label={`Spacing: ${style.highlightLetterSpacing}px`} min={0} max={8} value={style.highlightLetterSpacing} onChange={(v) => update({ highlightLetterSpacing: v })} />
                      <div className="flex flex-col justify-end"><Checkbox label="UPPERCASE" checked={style.highlightUppercase} onChange={(v) => update({ highlightUppercase: v })} /></div>
                      <div className="flex flex-col justify-end"><Checkbox label="Italic" checked={style.highlightItalic} onChange={(v) => update({ highlightItalic: v })} /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div><Checkbox label="Stroke" checked={style.highlightStrokeEnabled} onChange={(v) => update({ highlightStrokeEnabled: v })} /></div>
                      <div><Checkbox label="Shadow" checked={style.highlightShadowEnabled} onChange={(v) => update({ highlightShadowEnabled: v })} /></div>
                    </div>
                    {style.highlightStrokeEnabled && (
                      <div className="grid grid-cols-2 gap-3">
                        <ColorPicker label="Stroke Color" value={style.highlightStrokeColor} onChange={(v) => update({ highlightStrokeColor: v })} />
                        <RangeInput label={`Width: ${style.highlightStrokeWidth}px`} min={1} max={6} value={style.highlightStrokeWidth} onChange={(v) => update({ highlightStrokeWidth: v })} />
                      </div>
                    )}
                    {style.highlightShadowEnabled && (
                      <div className="grid grid-cols-2 gap-3">
                        <ColorPicker label="Shadow Color" value={style.highlightShadowColor} onChange={(v) => update({ highlightShadowColor: v })} />
                        <RangeInput label={`Blur: ${style.highlightShadowBlur}px`} min={0} max={20} value={style.highlightShadowBlur} onChange={(v) => update({ highlightShadowBlur: v })} />
                      </div>
                    )}
                  </div>
                )}
              </FeatureLock>
            </Section>

            <Section title="Background & Stroke">
              <div className="grid grid-cols-2 gap-3">
                <div><Checkbox label="Background" checked={style.bgEnabled} onChange={(v) => update({ bgEnabled: v })} /></div>
                <div><Checkbox label="Stroke/Outline" checked={style.strokeEnabled} onChange={(v) => update({ strokeEnabled: v })} /></div>
              </div>
              {style.bgEnabled && (
                <div className="grid grid-cols-3 gap-3 mt-2">
                  <RangeInput label={`Opacity: ${Math.round(style.bgOpacity * 100)}%`} min={0} max={100} value={Math.round(style.bgOpacity * 100)} onChange={(v) => update({ bgOpacity: v / 100 })} />
                  <RangeInput label={`Radius: ${style.bgRadius}px`} min={0} max={24} value={style.bgRadius} onChange={(v) => update({ bgRadius: v })} />
                  <RangeInput label={`Padding: ${style.bgPadding}px`} min={4} max={32} value={style.bgPadding} onChange={(v) => update({ bgPadding: v })} />
                </div>
              )}
              {style.strokeEnabled && (
                <div className="grid grid-cols-2 gap-3 mt-2">
                  <ColorPicker label="Stroke" value={style.strokeColor} onChange={(v) => update({ strokeColor: v })} />
                  <RangeInput label={`Width: ${style.strokeWidth}px`} min={1} max={6} value={style.strokeWidth} onChange={(v) => update({ strokeWidth: v })} />
                </div>
              )}
              <div className="mt-2"><Checkbox label="Text shadow" checked={style.shadowEnabled} onChange={(v) => update({ shadowEnabled: v })} /></div>
              {style.shadowEnabled && (
                <div className="grid grid-cols-2 gap-3 mt-2">
                  <ColorPicker label="Shadow" value={style.shadowColor} onChange={(v) => update({ shadowColor: v })} />
                  <RangeInput label={`Blur: ${style.shadowBlur}px`} min={0} max={20} value={style.shadowBlur} onChange={(v) => update({ shadowBlur: v })} />
                </div>
              )}
            </Section>

            <Section title="Position & Layout">
              <div className="grid grid-cols-3 gap-2 mb-3">
                {(["top", "center", "bottom"] as const).map(p => {
                  const isSelected = (style.positionY != null ? (style.positionY <= 35 ? "top" : style.positionY >= 65 ? "bottom" : "center") : style.position) === p;
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => update({ position: p, positionY: p === "top" ? 15 : p === "bottom" ? 85 : 50 })}
                      className={cn(
                        "py-2 rounded-lg border text-[11px] font-medium capitalize transition-colors",
                        isSelected ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600"
                      )}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
              <RangeInput
                label={`Vertical: ${style.positionY}%`}
                min={5}
                max={95}
                value={style.positionY}
                onChange={(v) => update({
                  positionY: v,
                  position: v <= 35 ? "top" : v >= 65 ? "bottom" : "center",
                })}
              />
              <div className="mt-3 space-y-2 pt-2 border-t border-zinc-800">
                <Checkbox
                  label="Person-Aware (Hindari wajah/subjek otomatis)"
                  checked={!!style.subjectAwarePositioning}
                  onChange={(v) => update({ subjectAwarePositioning: v })}
                />
                <RangeInput
                  label={`Safe Area Margin: ${style.safeAreaMargin || 40}px`}
                  min={10}
                  max={100}
                  value={style.safeAreaMargin || 40}
                  onChange={(v) => update({ safeAreaMargin: v })}
                />
              </div>
            </Section>

            <Section title="Highlight Words (kata penting)">
              <p className="text-[10px] text-zinc-500 mb-2">AI auto-detect dari transkrip. Tambah manual jika perlu.</p>
              <div className="flex gap-2">
                <input type="text" value={newWord} onChange={(e) => setNewWord(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addHighlightWord())} placeholder="Tambah kata..." className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500" />
                <Button type="button" size="xs" onClick={addHighlightWord}>Add</Button>
              </div>
              {style.highlightWords.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {style.highlightWords.map(w => (
                    <span key={w} className="flex items-center gap-1 bg-yellow-500/10 border border-yellow-500/30 text-yellow-400 text-[10px] font-medium px-2 py-0.5 rounded-full">
                      {w}<button type="button" onClick={() => update({ highlightWords: style.highlightWords.filter(x => x !== w) })} className="hover:text-red-400"><X className="h-2.5 w-2.5" /></button>
                    </span>
                  ))}
                </div>
              )}
            </Section>
          </>
        )}
      </div>

      {/* Preview — fixed col, vertically centered while left controls scroll */}
      <div className="lg:col-span-4 flex min-h-0 flex-col items-center justify-center overflow-hidden bg-zinc-950 p-4">
        {style.enabled === false ? (
          <div className="flex flex-col items-center justify-center w-full max-w-[240px]">
            <div className="mb-3 flex w-full items-center justify-between gap-2">
              <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
              <span className="rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-[9px] text-zinc-400 font-medium">Subtitle Disabled</span>
            </div>
            <CanvasPreviewFrame canvas={canvas} thumbnailUrl={thumbnailUrl}>
              <div className="absolute inset-0 flex flex-col items-center justify-center p-4 text-center bg-black/40 backdrop-blur-[2px]">
                <div className="w-10 h-10 rounded-full bg-zinc-900/90 border border-zinc-700/80 flex items-center justify-center mb-2 shadow-lg">
                  <EyeOff className="w-5 h-5 text-zinc-400" />
                </div>
                <p className="text-xs font-bold text-zinc-200">No Subtitles</p>
                <p className="text-[10px] text-zinc-400 mt-1 leading-snug">
                  Video akan dirender bersih tanpa subtitle overlay
                </p>
              </div>
            </CanvasPreviewFrame>
            <div className="mt-3 w-full rounded-lg border border-zinc-800 bg-zinc-900/60 p-2.5 text-center">
              <p className="text-[10px] text-zinc-400">Audio & visual tetap utuh 100%</p>
            </div>
          </div>
        ) : engine === "hyperframes" ? (
          <HfLivePreview
            preset={hfPreset}
            sample={hfPreset?.preview || "subtitle words"}
            kind="subtitle"
            aspectRatio={aspectRatio}
            thumbnailUrl={thumbnailUrl}
            canvas={canvas}
          />
        ) : engine === "ffmpeg" ? (
          <>
            <div className="mb-3 flex w-full items-center justify-between gap-2">
              <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
              <span className="rounded-md border border-purple-500/30 bg-purple-500/10 px-2 py-1 text-[9px] text-purple-300">
                <Zap className="inline w-3 h-3 mr-1" />FFmpeg Drawtext
              </span>
            </div>
            <CanvasPreviewFrame canvas={canvas} thumbnailUrl={thumbnailUrl}>
              <div className="absolute left-0 right-0 flex justify-center px-3 pointer-events-none" style={{ top: `${style.positionY ?? 78}%`, transform: "translateY(-50%)" }}>
                {(() => {
                  const isWordPop = style.lineTransition === "word_pop";
                  const sampleWords = ["ini", "kata", "penting", "banget", "untuk", "kamu"];
                  const count = Math.max(1, Math.min(6, style.maxWordsPerLine || 4));
                  const words = sampleWords.slice(0, count);
                  const displayWords = isWordPop ? [words[activeWordIdx % words.length]] : words;
                  const bgAlpha = Math.round(Math.max(0, Math.min(1, style.bgOpacity ?? 0.75)) * 255).toString(16).padStart(2, "0");

                  return (
                    <div
                      className="flex flex-wrap justify-center items-center"
                      style={{
                        gap: isWordPop ? 0 : Math.max(3, (style.wordSpacing ?? 6) * 0.6),
                        maxWidth: "92%",
                        backgroundColor: style.bgEnabled ? `${style.bgColor || "#000000"}${bgAlpha}` : "transparent",
                        padding: style.bgEnabled ? `${Math.round((style.bgPadding ?? 12) * 0.35)}px ${Math.round((style.bgPadding ?? 12) * 0.65)}px` : "0px",
                        borderRadius: `${style.bgRadius ? Math.min(style.bgRadius, 14) : 4}px`,
                      }}
                    >
                      {displayWords.map((w, i) => {
                        const isActive = isWordPop ? true : (i === activeWordIdx % words.length);
                        const fontSize = Math.min(Math.max((style.fontSize || 38) * 0.22, 10), 16);
                        const strokeWidth = style.strokeEnabled ? Math.max((style.strokeWidth || 3) * 0.25, 0.6) : 0;

                        return (
                          <span
                            key={`${w}-${i}`}
                            style={{
                              color: isActive ? (style.highlightColor || "#FFCC00") : (style.color || "#FFFFFF"),
                              fontSize: fontSize,
                              fontFamily: `'${style.fontFamily || "Poppins"}', sans-serif`,
                              fontWeight: isActive ? 900 : Number(style.fontWeight || 700),
                              textTransform: style.uppercase ? "uppercase" : style.capitalize ? "capitalize" : "none",
                              fontStyle: style.italic ? "italic" : "normal",
                              letterSpacing: `${style.letterSpacing || 0}px`,
                              paintOrder: strokeWidth > 0 ? "stroke fill" : undefined,
                              WebkitTextStroke: strokeWidth > 0 ? `${strokeWidth}px ${style.strokeColor || "#000000"}` : undefined,
                              textShadow: style.shadowEnabled ? `1px 1px 0px ${style.shadowColor || "#000000"}` : "0 2px 4px rgba(0,0,0,0.8)",
                              wordBreak: "break-word",
                            }}
                          >
                            {w}
                          </span>
                        );
                      })}
                    </div>
                  );
                })()}
              </div>
              <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-500 z-10">
                ffmpeg {style.lineTransition || "word_pop"} · {style.stylePreset || "classic"}
              </p>
            </CanvasPreviewFrame>
            <div className="mt-3 grid w-full grid-cols-2 gap-2 text-[10px]">
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Font</span><p className="truncate text-zinc-300">{style.fontFamily}</p></div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Preset</span><p className="truncate text-purple-300">{style.stylePreset || "classic"}</p></div>
            </div>
          </>
        ) : engine === "skia" ? (
          <SkiaSubtitleLivePreview style={style} thumbnailUrl={thumbnailUrl} activeWordIdx={activeWordIdx} canvas={canvas} />
        ) : (
          <>
            <div className="mb-3 flex w-full items-center justify-between gap-2">
              <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
              <span className={cn("rounded-md border px-2 py-1 text-[9px]", "border-zinc-800 bg-zinc-900 text-zinc-400")}>{SUBTITLE_TRANSITION_META[style.lineTransition].label}</span>
            </div>
            <CanvasPreviewFrame canvas={canvas} thumbnailUrl={thumbnailUrl}>
              <div className="absolute inset-0 bg-gradient-to-b from-zinc-700/10 to-transparent pointer-events-none" />
              <div className="absolute left-0 right-0 flex justify-center px-3" style={{ top: `${style.positionY}%`, transform: "translateY(-50%)" }}>
                {style.lineTransition === "emphasis" ? (
                  <div className="flex flex-col items-center gap-1">
                    <span style={{ color: style.color, fontSize: Math.max(style.fontSize * 0.25, 9), fontFamily: `'${style.fontFamily}', sans-serif`, fontWeight: Number(style.fontWeight) }}>gak banyak</span>
                    <span style={{ color: style.highlightColor, fontSize: Math.max(style.fontSize * 0.85, 20), fontFamily: `'${style.fontFamily}', sans-serif`, fontWeight: 900, textShadow: style.highlightGlow ? `0 0 12px ${style.highlightGlowColor || style.highlightColor}, 0 0 24px ${style.highlightGlowColor || style.highlightColor}` : undefined }}>Animasi</span>
                  </div>
                ) : style.lineTransition === "line_reveal" ? (
                  <div className={cn("overflow-hidden", getSubAnimationClass(style.animationStyle))} style={{ backgroundColor: style.bgEnabled ? `${style.bgColor}${Math.round(style.bgOpacity * 255).toString(16).padStart(2, "0")}` : "transparent", padding: style.bgPadding * 0.42, borderRadius: style.bgRadius, borderLeft: `3px solid ${style.highlightColor}` }}>
                    <div style={{ width: "76%", height: 2, borderRadius: 99, backgroundColor: style.highlightColor, marginBottom: 5 }} />
                    <div className="flex flex-wrap justify-center" style={{ gap: style.wordSpacing * 0.5 }}>
                      {["ini", "kata", "penting", "banget"].map((w, i) => {
                        const isHighlight = i === activeWordIdx;
                        return (
                          <span key={w} style={{ color: isHighlight ? style.highlightColor : style.color, fontSize: Math.max(style.fontSize * 0.35, 10), fontFamily: `'${style.fontFamily}', sans-serif`, fontWeight: isHighlight ? 900 : Number(style.fontWeight), letterSpacing: style.letterSpacing, textTransform: style.uppercase ? "uppercase" : style.capitalize ? "capitalize" : "none", WebkitTextStroke: style.strokeEnabled ? `${style.strokeWidth * 0.3}px ${style.strokeColor}` : undefined, textShadow: style.shadowEnabled ? `0 0 ${style.shadowBlur}px ${style.shadowColor}` : undefined }}>{w}</span>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div className={cn("flex flex-wrap justify-center", getSubAnimationClass(style.animationStyle))} style={{ gap: style.wordSpacing * 0.5, backgroundColor: style.bgEnabled ? `${style.bgColor}${Math.round(style.bgOpacity * 255).toString(16).padStart(2, "0")}` : "transparent", padding: style.bgPadding * 0.4, borderRadius: style.bgRadius }}>
                    {["ini", "kata", "penting", "banget"].map((w, i) => {
                      const isHighlight = i === activeWordIdx;
                      const isKeyword = style.highlightWords.includes(w);
                      const shouldHighlight = isHighlight || isKeyword;
                      const useDual = shouldHighlight && style.dualStyleEnabled;
                      const fs = Math.max((shouldHighlight ? (useDual ? style.highlightFontSize : style.fontSize * style.highlightScale) : style.fontSize) * 0.35, 10);
                      const hlStyle = style.highlightStyle || "scale";
                      const wordStyles: React.CSSProperties = {
                        color: shouldHighlight ? style.highlightColor : style.color,
                        fontSize: fs,
                        fontWeight: useDual ? Number(style.highlightFontWeight) : (shouldHighlight && style.highlightBold ? 900 : Number(style.fontWeight)),
                        fontFamily: useDual ? `'${style.highlightFontFamily}', sans-serif` : `'${style.fontFamily}', sans-serif`,
                        fontStyle: useDual ? (style.highlightItalic ? "italic" : "normal") : (style.italic ? "italic" : "normal"),
                        letterSpacing: useDual ? style.highlightLetterSpacing : style.letterSpacing,
                        textTransform: useDual ? (style.highlightUppercase ? "uppercase" : "none") : (style.uppercase ? "uppercase" : style.capitalize ? "capitalize" : "none"),
                        textShadow: [(useDual ? style.highlightShadowEnabled : style.shadowEnabled) ? `0 0 ${useDual ? style.highlightShadowBlur : style.shadowBlur}px ${useDual ? style.highlightShadowColor : style.shadowColor}` : "", shouldHighlight && style.highlightGlow ? `0 0 12px ${style.highlightGlowColor}` : ""].filter(Boolean).join(", ") || undefined,
                        WebkitTextStroke: (useDual ? style.highlightStrokeEnabled : style.strokeEnabled) ? `${(useDual ? style.highlightStrokeWidth : style.strokeWidth) * 0.3}px ${useDual ? style.highlightStrokeColor : style.strokeColor}` : undefined,
                        transition: "all 0.2s ease",
                        display: "inline-block",
                        ...(!useDual && shouldHighlight && hlStyle === "underline" ? { textDecoration: "underline", textDecorationColor: style.highlightColor, textUnderlineOffset: "3px", textDecorationThickness: "2px" } : {}),
                        ...(!useDual && shouldHighlight && hlStyle === "background" ? { backgroundColor: `${style.highlightColor}30`, borderRadius: 3, padding: "1px 4px" } : {}),
                        ...(!useDual && shouldHighlight && hlStyle === "strikethrough" ? { textDecoration: "line-through", textDecorationColor: style.highlightColor, textDecorationThickness: "2px" } : {}),
                      };
                      return <span key={i} style={wordStyles}>{w}</span>;
                    })}
                  </div>
                )}
              </div>
              <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-600 z-10">{style.lineTransition === "emphasis" ? "emphasis" : style.animationStyle} | {style.position}</p>
            </CanvasPreviewFrame>
            <div className="mt-3 grid w-full grid-cols-2 gap-2 text-[10px]">
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Font</span><p className="truncate text-zinc-300">{style.fontFamily}</p></div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Highlight</span><p className="truncate" style={{ color: style.highlightColor }}>{style.highlightColor}</p></div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Animation helpers ───────────────────────────────────────────────────────

// Kept for potential external use — subtitle editor uses getSubAnimationClass
function getHookAnimationClass(animation: string): string {
  switch (animation) {
    case "fade_scale": return "animate-[fadeScalePreview_2.5s_ease-in-out_infinite]";
    case "slide_up": return "animate-[slideUpPreview_2s_ease-in-out_infinite]";
    case "slide_punch_framer": return "animate-[slidePunchPreview_2s_ease-out_infinite]";
    case "glitch": return "animate-[glitchJitter_0.5s_steps(2)_infinite]";
    case "typewriter": return "animate-[typewriterReveal_3s_steps(20)_infinite]";
    case "glitch_rgb": return ""; // uses DOM-based multi-layer render
    case "shake_neon": return ""; // uses DOM-based multi-layer render
    case "cinematic_reveal": return "animate-[cinematicRevealText_3.5s_ease-out_infinite]";
    case "danger_bold": return "animate-[dangerPulse_1.2s_ease-in-out_infinite]";
    case "bold_slam": return "animate-[boldSlamPreview_2s_ease-out_infinite]";
    case "podcast_lower_third": return "animate-[podcastLowerPreview_2.8s_ease-out_infinite]";
    case "quote_card": return "animate-[quoteCardPreview_3s_ease-out_infinite]";
    case "waveform_pulse": return "animate-[waveformTextPreview_1.1s_ease-in-out_infinite]";
    case "breaking_tape": return "animate-[breakingTapePreview_2.5s_ease-out_infinite]";
    case "mic_drop": return "animate-[micDropPreview_2.5s_cubic-bezier(.2,.85,.25,1)_infinite]";
    case "split_panel": return "animate-[splitPanelPreview_2.6s_ease-in-out_infinite]";
    case "kinetic_stack": return "animate-[kineticStackPreview_2.4s_ease-in-out_infinite]";
    case "glass_flash": return "animate-[glassFlashPreview_2.8s_ease-in-out_infinite]";
    case "marker_swipe": return "animate-[markerSwipePreview_2.4s_ease-in-out_infinite]";
    case "signal_scan": return "animate-[signalScanPreview_2.5s_ease-in-out_infinite]";
    case "comment_reply": return "animate-[slideUpPreview_2.4s_ease-in-out_infinite]";
    case "search_prompt": return "animate-[fadeScalePreview_2.5s_ease-in-out_infinite]";
    case "countdown_list": return "animate-[slidePunchPreview_2.4s_ease-out_infinite]";
    case "pov_stamp": return "animate-[fadeScalePreview_2.5s_ease-in-out_infinite]";
    default: return "";
  }
}

function getHookPreviewSample(animation: string): string {
  switch (animation) {
    case "podcast_lower_third": return "bagian ini bikin hostnya diam";
    case "quote_card": return "kalimat ini mengubah cara lihat topiknya";
    case "waveform_pulse": return "dengerin 5 detik ini dulu";
    case "breaking_tape": return "opini ini bakal kebelah dua";
    case "mic_drop": return "ini jawaban paling brutalnya";
    case "split_panel": return "dua sisi ini bikin debat panas";
    case "kinetic_stack": return "ini alasan orang salah paham";
    case "glass_flash": return "bagian kecil ini paling mahal";
    case "marker_swipe": return "kalimat ini wajib ditandai";
    case "signal_scan": return "sinyalnya kelihatan dari sini";
    case "comment_reply": return "gimana caranya mulai dari nol?";
    case "search_prompt": return "cara naik jabatan tanpa burnout";
    case "countdown_list": return "3 kesalahan yang bikin kamu stuck";
    case "pov_stamp": return "kamu akhirnya berani bilang tidak";
    case "cinematic_reveal": return "mereka gak cerita bagian ini";
    case "danger_bold": return "jangan skip bagian ini";
    case "shake_neon": return "ini yang bikin rame";
    case "glitch_rgb": return "ada yang janggal di sini";
    default: return "hook podcast yang bikin berhenti scroll";
  }
}

function getSubAnimationClass(animation: string): string {
  switch (animation) {
    case "pop": return "animate-[popIn_1.5s_ease-in-out_infinite]";
    case "fade": return "animate-[fadeIn_2s_ease-in-out_infinite]";
    case "slide": return "animate-[slideInUp_1.5s_ease-in-out_infinite]";
    default: return "";
  }
}

// ─── Shared ──────────────────────────────────────────────────────────────────

function AccentLinePreview({ style }: { style: HookStyle }) {
  const pos = style.linePosition;
  const base: React.CSSProperties = { backgroundColor: style.lineColor, position: "absolute" };
  // Auto-adjust: calculate width/height based on approximate text length
  const textLen = (style.text || "Hook text preview here").length;
  const autoWidthPct = Math.min(Math.max(textLen * 2.5, 20), 70); // 20-70% based on text
  const autoHeightPct = Math.min(Math.max(textLen * 1.5, 15), 50); // 15-50% for vertical
  const autoW = style.lineAutoWidth ? `${autoWidthPct}%` : `${style.lineWidth}%`;
  const autoH = style.lineAutoWidth ? `${autoHeightPct}%` : `${style.lineWidth}%`;

  if (pos === "top") Object.assign(base, { top: style.lineOffset, left: "50%", transform: "translateX(-50%)", width: autoW, height: style.lineThickness });
  if (pos === "bottom") Object.assign(base, { bottom: style.lineOffset, left: "50%", transform: "translateX(-50%)", width: autoW, height: style.lineThickness });
  if (pos === "left") Object.assign(base, { left: style.lineOffset, top: "50%", transform: "translateY(-50%)", height: autoH, width: style.lineThickness });
  if (pos === "right") Object.assign(base, { right: style.lineOffset, top: "50%", transform: "translateY(-50%)", height: autoH, width: style.lineThickness });
  if (pos === "center-h") Object.assign(base, { top: `calc(50% + ${style.lineOffset}px)`, left: "50%", transform: "translate(-50%, -50%)", width: autoW, height: style.lineThickness });
  if (pos === "center-v") Object.assign(base, { top: "50%", left: `calc(50% + ${style.lineOffset}px)`, transform: "translate(-50%, -50%)", height: autoH, width: style.lineThickness });
  if (pos === "auto-bottom") Object.assign(base, { top: `calc(${style.positionY}% + ${style.lineOffset + 20}px)`, left: "50%", transform: "translateX(-50%)", width: autoW, height: style.lineThickness });
  return <div style={base} />;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <div><h4 className="text-[11px] font-semibold text-zinc-300 mb-2 uppercase tracking-wider">{title}</h4>{children}</div>;
}

function UnavailableHint({ text }: { text: string }) {
  return <p className="rounded-md border border-zinc-800 bg-zinc-900/60 px-2 py-1 text-[9px] text-zinc-600">{text}</p>;
}

function ColorPicker({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="text-[10px] text-zinc-500 block mb-1">{label}</label>
      <div className="flex items-center gap-2 bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5">
        <input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="w-5 h-5 rounded border-0 cursor-pointer bg-transparent" />
        <span className="text-[10px] text-zinc-400 font-mono">{value}</span>
      </div>
    </div>
  );
}

function RangeInput({ label, min, max, value, onChange }: { label: string; min: number; max: number; value: number; onChange: (v: number) => void }) {
  const percent = ((value - min) / (max - min)) * 100;
  return (
    <div>
      <label className="text-[10px] text-zinc-500 block mb-1">{label}</label>
      <div className="relative w-full h-6 flex items-center">
        <div className="absolute left-0 right-0 h-2 bg-zinc-700 rounded-full" />
        <div className="absolute left-0 h-2 bg-emerald-600 rounded-full" style={{ width: `${percent}%` }} />
        <input type="range" min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))} className="absolute w-full h-6 opacity-0 cursor-pointer z-10" />
        <div className="absolute w-4 h-4 bg-emerald-500 rounded-full shadow-lg border-2 border-emerald-400 pointer-events-none" style={{ left: `calc(${percent}% - 8px)` }} />
      </div>
    </div>
  );
}

function Checkbox({ label, checked, onChange, disabled }: { label: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className={cn("flex items-center gap-2", disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer")}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} className="w-3.5 h-3.5 rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500/20 disabled:cursor-not-allowed" />
      <span className="text-[11px] text-zinc-400">{label}</span>
    </label>
  );
}

function SelectSmall({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <div>
      <label className="text-[10px] text-zinc-500 block mb-1">{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5 text-[11px] text-zinc-300 focus:outline-none focus:border-zinc-500">
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}
