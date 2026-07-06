import { useState, useEffect } from "react";
import { X, Type, Sparkles, Bookmark, Trash2, Save, Download, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { FeatureLock } from "@/components/ui/FeatureLock";
import { presets as presetsApi, type Preset } from "@/lib/api";
import { cn } from "@/lib/utils";

type OptionMeta = {
  label: string;
  mood: string;
  accent: string;
  preview: string;
  desc: string;
};

const PAGINATION_PAGE_SIZE = 6;

type SubtitleVisualPreset =
  | "classic"
  | "dual_pop"
  | "neon_pulse"
  | "meme_impact"
  | "editorial_banner"
  | "spotlight_keyword"
  | "lower_third"
  | "bubble_chat"
  | "minimal_clean"
  | "breaking_tape"
  | "quote_box"
  | "documentary";

function useGoogleFont(fontFamily: string) {
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
  decorativeElements: boolean;
  motionIntensity: number;
  // Duration
  duration: number;
  fadeIn: number;
  fadeOut: number;
}

export interface SubtitleStyle {
  stylePreset: SubtitleVisualPreset;
  fontFamily: string;
  fontSize: number;
  fontWeight: string;
  letterSpacing: number;
  lineHeight: number;
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
  maxWordsPerLine: number;
  wordSpacing: number;
  animationStyle: "pop" | "fade" | "slide" | "none";
  animationSpeed: number;
  lineTransition: "word_pop" | "emphasis" | "line_reveal";
}

export const DEFAULT_HOOK_STYLE: HookStyle = {
  animation: "podcast_lower_third",
  text: "",
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
  decorativeElements: true,
  motionIntensity: 1.0,
  duration: 3.0,
  fadeIn: 0.3,
  fadeOut: 0.3,
};

export const DEFAULT_SUBTITLE_STYLE: SubtitleStyle = {
  stylePreset: "classic",
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
const SUBTITLE_FONT_SUGGESTIONS = ["Poppins", "Inter", "Montserrat", "Barlow Condensed", "Roboto Condensed", "Noto Sans"];
const HIGHLIGHT_FONT_SUGGESTIONS = ["Anton", "Archivo Black", "Bebas Neue", "Bungee", "Barlow Condensed", "Black Ops One"];

const HOOK_ANIMATIONS = [
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
];

const HOOK_ANIMATION_META: Record<string, OptionMeta> = {
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
};

const HIGHLIGHT_STYLE_META: Record<SubtitleStyle["highlightStyle"], OptionMeta> = {
  scale: { label: "Scale", mood: "Bigger word", accent: "#FACC15", preview: "Aa", desc: "Kata penting membesar." },
  underline: { label: "Underline", mood: "Marked", accent: "#38BDF8", preview: "__", desc: "Garis bawah untuk penekanan rapi." },
  background: { label: "Background", mood: "Tag", accent: "#34D399", preview: "BOX", desc: "Highlight seperti label kecil." },
  strikethrough: { label: "Strike", mood: "Contrarian", accent: "#FB7185", preview: "DEL", desc: "Cocok untuk kontra atau koreksi." },
};

const HOOK_PRESETS: { id: string; name: string; style: Partial<HookStyle> }[] = [
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
];

const SUBTITLE_PRESETS: { id: string; name: string; style: Partial<SubtitleStyle> }[] = [
  {
    id: "classic",
    name: "Classic Karaoke",
    style: {
      stylePreset: "classic",
      color: "#FFFFFF",
      highlightColor: "#FFCC00",
      fontSize: 34,
      bgEnabled: true,
      bgColor: "#000000",
      bgOpacity: 0.42,
      bgRadius: 8,
      animationStyle: "pop",
      lineTransition: "word_pop",
      maxWordsPerLine: 3,
    },
  },
  {
    id: "dual_pop",
    name: "Dual Font Pop",
    style: {
      stylePreset: "dual_pop",
      color: "#F8FAFC",
      highlightColor: "#FDE047",
      fontFamily: "Inter",
      fontWeight: "800",
      fontSize: 34,
      dualStyleEnabled: true,
      highlightFontFamily: "Bungee",
      highlightFontSize: 42,
      highlightFontWeight: "900",
      highlightLetterSpacing: 0,
      highlightUppercase: true,
      highlightStrokeEnabled: true,
      highlightStrokeWidth: 3,
      highlightShadowEnabled: true,
      bgColor: "#111827",
      bgOpacity: 0.66,
      bgRadius: 14,
      bgPadding: 14,
      animationStyle: "pop",
      lineTransition: "word_pop",
      maxWordsPerLine: 3,
    },
  },
  {
    id: "neon_pulse",
    name: "Neon Pulse",
    style: {
      stylePreset: "neon_pulse",
      color: "#ECFEFF",
      highlightColor: "#22D3EE",
      fontFamily: "Montserrat",
      fontWeight: "900",
      fontSize: 36,
      dualStyleEnabled: true,
      highlightFontFamily: "Black Ops One",
      highlightFontSize: 44,
      highlightFontWeight: "900",
      highlightGlow: true,
      highlightGlowColor: "#22D3EE",
      highlightShadowEnabled: true,
      highlightShadowBlur: 18,
      bgColor: "#020617",
      bgOpacity: 0.72,
      bgRadius: 10,
      strokeEnabled: true,
      strokeWidth: 2,
      shadowEnabled: true,
      shadowBlur: 16,
      animationStyle: "pop",
      lineTransition: "word_pop",
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
];

// ─── Modal ───────────────────────────────────────────────────────────────────

interface StyleEditorModalProps {
  open: boolean;
  onClose: () => void;
  hookStyle: HookStyle;
  subtitleStyle: SubtitleStyle;
  onHookChange: (style: HookStyle) => void;
  onSubtitleChange: (style: SubtitleStyle) => void;
  aspectRatio?: string;
  inline?: boolean;
  activeTab?: "presets" | "hook" | "subtitle";
  thumbnailUrl?: string;
  isSuperadmin?: boolean;
  isPremium?: boolean;
  userFeatures?: string[];
  activePresetId?: number | null;
  onPresetSelect?: (id: number) => void;
}

export function StyleEditorModal({ open, onClose, hookStyle, subtitleStyle, onHookChange, onSubtitleChange, aspectRatio = "9:16", inline, activeTab, thumbnailUrl, isSuperadmin, isPremium, userFeatures, activePresetId: externalActivePresetId, onPresetSelect }: StyleEditorModalProps) {
  const [tab, setTab] = useState<"presets" | "hook" | "subtitle">(activeTab || "hook");

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
      <div className="h-full overflow-hidden">
        <style>{animationStyles}</style>
        {tab === "presets" ? <PresetsTab hookStyle={hookStyle} subtitleStyle={subtitleStyle} onHookChange={onHookChange} onSubtitleChange={onSubtitleChange} externalActiveId={externalActivePresetId} onPresetSelect={onPresetSelect} /> : tab === "hook" ? <HookEditor style={hookStyle} onChange={onHookChange} aspectRatio={aspectRatio} thumbnailUrl={thumbnailUrl} /> : <SubtitleEditor style={subtitleStyle} onChange={onSubtitleChange} aspectRatio={aspectRatio} thumbnailUrl={thumbnailUrl} isSuperadmin={isSuperadmin} isPremium={isPremium} userFeatures={userFeatures} />}
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <style>{animationStyles}</style>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-[95vw] max-w-[1100px] h-[88vh] bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800 shrink-0">
          <div className="flex items-center gap-4">
            <h2 className="text-sm font-semibold text-zinc-100">Custom Style Editor</h2>
            <div className="flex bg-zinc-800 rounded-lg p-0.5">
              <button type="button" onClick={() => setTab("presets")} className={cn("px-3 py-1.5 text-xs font-medium rounded-md transition-colors", tab === "presets" ? "bg-emerald-600 text-white" : "text-zinc-400 hover:text-zinc-200")}>
                <Bookmark className="h-3 w-3 inline mr-1.5" />Presets
              </button>
              <button type="button" onClick={() => setTab("hook")} className={cn("px-3 py-1.5 text-xs font-medium rounded-md transition-colors", tab === "hook" ? "bg-emerald-600 text-white" : "text-zinc-400 hover:text-zinc-200")}>
                <Type className="h-3 w-3 inline mr-1.5" />Hook
              </button>
              <button type="button" onClick={() => setTab("subtitle")} className={cn("px-3 py-1.5 text-xs font-medium rounded-md transition-colors", tab === "subtitle" ? "bg-emerald-600 text-white" : "text-zinc-400 hover:text-zinc-200")}>
                <Sparkles className="h-3 w-3 inline mr-1.5" />Subtitle
              </button>
            </div>
          </div>
          <button type="button" onClick={onClose} className="p-1.5 rounded-lg text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"><X className="h-4 w-4" /></button>
        </div>
        <div className="flex-1 overflow-hidden">
          {tab === "presets" ? <PresetsTab hookStyle={hookStyle} subtitleStyle={subtitleStyle} onHookChange={onHookChange} onSubtitleChange={onSubtitleChange} externalActiveId={externalActivePresetId} onPresetSelect={onPresetSelect} /> : tab === "hook" ? <HookEditor style={hookStyle} onChange={onHookChange} aspectRatio={aspectRatio} thumbnailUrl={thumbnailUrl} /> : <SubtitleEditor style={subtitleStyle} onChange={onSubtitleChange} aspectRatio={aspectRatio} thumbnailUrl={thumbnailUrl} isSuperadmin={isSuperadmin} isPremium={isPremium} userFeatures={userFeatures} />}
        </div>
      </div>
    </div>
  );
}

// ─── Presets Tab ─────────────────────────────────────────────────────────────

function PresetsTab({ hookStyle, subtitleStyle, onHookChange, onSubtitleChange, externalActiveId, onPresetSelect }: { hookStyle: HookStyle; subtitleStyle: SubtitleStyle; onHookChange: (s: HookStyle) => void; onSubtitleChange: (s: SubtitleStyle) => void; externalActiveId?: number | null; onPresetSelect?: (id: number) => void }) {
  const [userPresets, setUserPresets] = useState<Preset[]>([]);
  const [loading, setLoading] = useState(true);
  const [saveName, setSaveName] = useState("");
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
    setActivePresetId(preset.id);
    if (onPresetSelect) onPresetSelect(preset.id);
    setStatusMsg(`Loaded "${preset.name}"`);
    setTimeout(() => setStatusMsg(""), 2000);
  }

  async function handleSave() {
    if (!saveName.trim()) return;
    setSaving(true);
    try {
      await presetsApi.create(saveName.trim(), hookStyle, subtitleStyle);
      setSaveName("");
      setStatusMsg(`Saved "${saveName.trim()}"`);
      setTimeout(() => setStatusMsg(""), 2000);
      const list = await presetsApi.list();
      setUserPresets(list);
    } catch { setStatusMsg("Failed to save"); }
    finally { setSaving(false); }
  }

  async function handleDelete(id: number, name: string) {
    if (!confirm(`Delete preset "${name}"?`)) return;
    try {
      await presetsApi.remove(id);
      setUserPresets((prev) => prev.filter((p) => p.id !== id));
      setStatusMsg(`Deleted "${name}"`);
      setTimeout(() => setStatusMsg(""), 2000);
    } catch { setStatusMsg("Failed to delete"); }
  }

  return (
    <div className="h-full p-5 overflow-y-auto">
      {/* Save current as preset */}
      <div className="mb-6">
        <h3 className="text-xs font-semibold text-zinc-200 mb-3 flex items-center gap-2">
          <Save className="h-3.5 w-3.5 text-emerald-400" />Save Current Style as Preset
        </h3>
        <div className="flex gap-2">
          <input type="text" value={saveName} onChange={(e) => setSaveName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), handleSave())} placeholder="Enter preset name..." className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50" />
          <Button type="button" size="sm" loading={saving} onClick={handleSave} icon={<Save className="h-3.5 w-3.5" />}>Save</Button>
        </div>
        {statusMsg && <p className="text-[11px] text-emerald-400 mt-2">{statusMsg}</p>}
      </div>

      {/* Preset list */}
      <div>
        <h3 className="text-xs font-semibold text-zinc-200 mb-3 flex items-center gap-2">
          <Bookmark className="h-3.5 w-3.5 text-emerald-400" />My Presets ({userPresets.length})
        </h3>
        {loading ? (
          <div className="flex items-center gap-2 py-4"><div className="h-4 w-4 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin" /><span className="text-xs text-zinc-500">Loading...</span></div>
        ) : userPresets.length === 0 ? (
          <div className="text-center py-8 border border-dashed border-zinc-800 rounded-xl">
            <Bookmark className="h-6 w-6 text-zinc-700 mx-auto mb-2" />
            <p className="text-xs text-zinc-500">No presets saved yet</p>
            <p className="text-[10px] text-zinc-600 mt-1">Configure your hook & subtitle styles, then save them here</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {userPresets.map((p) => (
              <div key={p.id} className={cn("relative group rounded-xl border p-3 transition-all",
                activePresetId === p.id
                  ? "border-emerald-500 bg-emerald-500/8 ring-1 ring-emerald-500/20"
                  : "border-zinc-800 bg-zinc-900/50 hover:border-emerald-500/40")}>
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <h4 className={cn("text-sm font-medium truncate pr-2", activePresetId === p.id ? "text-emerald-300" : "text-zinc-200")}>{p.name}</h4>
                    {activePresetId === p.id && <span className="shrink-0 text-[8px] bg-emerald-500/20 text-emerald-400 font-bold uppercase px-1.5 py-0.5 rounded-full">Active</span>}
                  </div>
                  <button type="button" onClick={() => handleDelete(p.id, p.name)} className="absolute top-2.5 right-2.5 p-1 rounded text-zinc-700 hover:text-red-400 hover:bg-zinc-800 opacity-0 group-hover:opacity-100 transition-all">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                <div className="space-y-1 text-[10px] text-zinc-500 mb-3">
                  <p>Hook: <span className="text-zinc-400">{(p.hook_style as any)?.animation?.replace(/_/g, " ") || "default"}</span></p>
                  <p>Font: <span className="text-zinc-400">{(p.hook_style as any)?.fontFamily || "Poppins"}</span></p>
                  <p>Highlight: <span style={{ color: (p.subtitle_style as any)?.highlightColor || "#FFCC00" }}>{(p.subtitle_style as any)?.highlightColor || "#FFCC00"}</span></p>
                  {p.owner_email && <p>Owner: <span className="text-zinc-400">{p.owner_name || p.owner_email}</span></p>}
                </div>
                <button type="button" onClick={() => loadPreset(p)} className={cn("w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg border text-[11px] font-medium transition-colors",
                  activePresetId === p.id
                    ? "border-emerald-500 bg-emerald-500/20 text-emerald-300"
                    : "border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10")}>
                  <Download className="h-3 w-3" />{activePresetId === p.id ? "Active" : "Load Preset"}
                </button>
                {p.created_at && <p className="text-[9px] text-zinc-700 mt-2 text-center">{new Date(p.created_at).toLocaleDateString()}</p>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Hook Preview Renderer (matches FFmpeg output visually) ──────────────────

function HookPreviewRenderer({ style }: { style: HookStyle }) {
  const text = style.text || getHookPreviewSample(style.animation);
  const fontSize = Math.max(style.fontSize * 0.32, 12);
  const fontFamily = style.fontFamily === "monospace" ? "monospace" : `'${style.fontFamily}', sans-serif`;
  const fontWeight = Number(style.fontWeight);
  const fontStyle = style.italic ? "italic" as const : "normal" as const;

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
    case "podcast_lower_third": {
      const accent = style.lineColor || "#16F2B3";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-3 right-3 animate-[podcastLowerPreview_2.8s_ease-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{
              display: "grid",
              gridTemplateColumns: "auto 1fr",
              gap: 8,
              alignItems: "center",
              background: "linear-gradient(90deg, rgba(6,17,31,0.94), rgba(20,28,44,0.78))",
              border: `1px solid ${accent}55`,
              borderLeft: `5px solid ${accent}`,
              borderRadius: 12,
              boxShadow: `0 12px 30px rgba(0,0,0,0.35), 0 0 18px ${accent}33`,
              padding: "10px 12px",
            }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "center" }}>
                <span style={{ width: 8, height: 8, borderRadius: 99, background: accent, boxShadow: `0 0 12px ${accent}`, animation: "podcastOnAirPulse_1s ease-in-out infinite" }} />
                <span style={{ color: accent, fontSize: 8, fontWeight: 900, letterSpacing: 0 }}>ON AIR</span>
              </div>
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
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-x-0 flex flex-col items-center justify-center gap-3 px-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
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
              <span style={{ display: "block", color: "#D71920", fontSize: 8, fontWeight: 900, letterSpacing: 0 }}>HOT TAKE</span>
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
  const isLightCard = presetKey === "bubble_chat" || presetKey === "breaking_tape" || presetKey === "quote_box";
  const previewBg = preset.style.bgEnabled === false
    ? "transparent"
    : preset.style.bgColor
      ? `${preset.style.bgColor}${Math.round((preset.style.bgOpacity ?? 0.45) * 255).toString(16).padStart(2, "0")}`
      : "rgba(0,0,0,0.28)";
  const previewRadius = presetKey === "breaking_tape" ? 2 : presetKey === "bubble_chat" ? 14 : preset.style.bgRadius ?? 6;
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

// ─── Hook Editor ─────────────────────────────────────────────────────────────

function HookEditor({ style, onChange, aspectRatio, thumbnailUrl }: { style: HookStyle; onChange: (s: HookStyle) => void; aspectRatio: string; thumbnailUrl?: string }) {
  const update = (patch: Partial<HookStyle>) => onChange({ ...style, ...patch });
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [presetPage, setPresetPage] = useState(1);
  const [animationPage, setAnimationPage] = useState(() => getPageForIndex(HOOK_ANIMATIONS.indexOf(style.animation)));
  useGoogleFont(style.fontFamily);
  const previewAspect = aspectRatio === "16:9" ? "16/9" : aspectRatio === "1:1" ? "1/1" : "9/16";
  const activeAnimation = HOOK_ANIMATION_META[style.animation] || HOOK_ANIMATION_META.podcast_lower_third;
  const visibleHookPresets = getPageItems(HOOK_PRESETS, presetPage);
  const visibleHookAnimations = getPageItems(HOOK_ANIMATIONS, animationPage);

  useEffect(() => {
    setAnimationPage(getPageForIndex(HOOK_ANIMATIONS.indexOf(style.animation)));
  }, [style.animation]);

  useEffect(() => {
    if (!HOOK_ANIMATIONS.includes(style.animation)) {
      update({ animation: DEFAULT_HOOK_STYLE.animation });
    }
  }, [style.animation]);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 h-full">
      <div className="xl:col-span-8 p-4 overflow-y-auto space-y-4 border-r border-zinc-800">
        {/* Presets */}
        <Section title="Quick Presets">
          <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-2">
            {visibleHookPresets.map(p => (
              <HookPresetCard
                key={p.id}
                preset={p}
                active={activePreset === p.id}
                onClick={() => {
                  onChange({ ...DEFAULT_HOOK_STYLE, ...p.style, text: style.text } as HookStyle);
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
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-2">
                <Checkbox label="Show badge / label" checked={style.badgeEnabled} onChange={(v) => update({ badgeEnabled: v })} />
                {style.badgeEnabled && (
                  <input
                    type="text"
                    value={style.badgeText}
                    onChange={(e) => update({ badgeText: e.target.value })}
                    placeholder="Badge text"
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:border-zinc-500 focus:outline-none"
                  />
                )}
              </div>
              <div className="space-y-2">
                <Checkbox label="Decorative motion elements" checked={style.decorativeElements} onChange={(v) => update({ decorativeElements: v })} />
                <RangeInput label={`Motion: ${style.motionIntensity.toFixed(1)}x`} min={0} max={20} value={Math.round(style.motionIntensity * 10)} onChange={(v) => update({ motionIntensity: v / 10 })} />
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
          </div>
          <RangeInput label={`BG Opacity: ${Math.round(style.bgOpacity * 100)}%`} min={0} max={100} value={Math.round(style.bgOpacity * 100)} onChange={(v) => update({ bgOpacity: v / 100 })} />
          <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
              <Checkbox label="Text gradient" checked={style.gradientEnabled} onChange={(v) => update({ gradientEnabled: v })} />
              {style.gradientEnabled && (
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
            {(["top", "center", "bottom"] as const).map(p => (
              <button key={p} type="button" onClick={() => update({ position: p, positionY: p === "top" ? 20 : p === "bottom" ? 80 : 50 })} className={cn("py-2 rounded-lg border text-[11px] font-medium capitalize transition-colors", style.position === p ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600")}>{p}</button>
            ))}
          </div>
          <RangeInput label={`Vertical: ${style.positionY}%`} min={5} max={95} value={style.positionY} onChange={(v) => update({ positionY: v })} />
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
              <Checkbox label="Box around text" checked={style.boxEnabled} onChange={(v) => update({ boxEnabled: v })} />
              {style.boxEnabled && (
                <div className="mt-2 space-y-2">
                  <ColorPicker label="Box Color" value={style.boxColor} onChange={(v) => update({ boxColor: v })} />
                  <RangeInput label={`Opacity: ${Math.round(style.boxOpacity * 100)}%`} min={0} max={100} value={Math.round(style.boxOpacity * 100)} onChange={(v) => update({ boxOpacity: v / 100 })} />
                  <RangeInput label={`Padding: ${style.boxPadding}px`} min={4} max={56} value={style.boxPadding} onChange={(v) => update({ boxPadding: v })} />
                  <RangeInput label={`Radius: ${style.boxRadius}px`} min={0} max={28} value={style.boxRadius} onChange={(v) => update({ boxRadius: v })} />
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
      </div>

      {/* Preview */}
      <div className="xl:col-span-4 p-4 flex flex-col items-center bg-zinc-950 overflow-y-auto">
        <div className="mb-3 flex w-full items-center justify-between gap-2">
          <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
          <span className="rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-[9px] text-zinc-400">{activeAnimation.label}</span>
        </div>
        <div className="relative w-full bg-zinc-900 rounded-lg overflow-hidden border border-zinc-800 shrink-0" style={{ aspectRatio: previewAspect }}>
          {thumbnailUrl && <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-cover" />}
          <HookPreviewRenderer style={style} />
          {/* Accent line */}
          {style.lineEnabled && <AccentLinePreview style={style} />}
          <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-600">{style.animation.replace(/_/g, " ")} | {style.duration}s</p>
        </div>
        <div className="mt-3 grid w-full grid-cols-2 gap-2 text-[10px]">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Font</span><p className="truncate text-zinc-300">{style.fontFamily}</p></div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Color</span><p className="truncate" style={{ color: style.gradientEnabled ? style.gradientTo : style.color }}>{style.gradientEnabled ? "Gradient" : style.color}</p></div>
        </div>
      </div>
    </div>
  );
}

// ─── Subtitle Editor ─────────────────────────────────────────────────────────

function SubtitleEditor({ style, onChange, aspectRatio, thumbnailUrl, isSuperadmin, isPremium, userFeatures }: { style: SubtitleStyle; onChange: (s: SubtitleStyle) => void; aspectRatio: string; thumbnailUrl?: string; isSuperadmin?: boolean; isPremium?: boolean; userFeatures?: string[] }) {
  const update = (patch: Partial<SubtitleStyle>) => onChange({ ...style, ...patch });
  const [newWord, setNewWord] = useState("");
  const [activeWordIdx, setActiveWordIdx] = useState(0);
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [presetPage, setPresetPage] = useState(1);
  const [timingPage, setTimingPage] = useState(1);
  useGoogleFont(style.fontFamily);
  useGoogleFont(style.dualStyleEnabled ? style.highlightFontFamily : "");
  const previewAspect = aspectRatio === "16:9" ? "16/9" : aspectRatio === "1:1" ? "1/1" : "9/16";
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
  const visibleSubtitlePresets = getPageItems(SUBTITLE_PRESETS, presetPage);
  const visibleSubtitleTiming = getPageItems(subtitleTimingOptions, timingPage);
  const activeTimingMeta = SUBTITLE_TRANSITION_META[style.lineTransition] || SUBTITLE_ANIMATION_META[style.animationStyle];

  // Cycle through words for animated preview
  useEffect(() => {
    const interval = setInterval(() => {
      setActiveWordIdx((prev) => (prev + 1) % 4);
    }, 800);
    return () => clearInterval(interval);
  }, []);

  function addHighlightWord() {
    if (newWord.trim() && !style.highlightWords.includes(newWord.trim().toLowerCase())) {
      update({ highlightWords: [...style.highlightWords, newWord.trim().toLowerCase()] });
      setNewWord("");
    }
  }

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 h-full">
      <div className="xl:col-span-8 p-4 overflow-y-auto space-y-4 border-r border-zinc-800">
        <Section title="Quick Presets">
          <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-2">
            {visibleSubtitlePresets.map(p => (
              <SubtitlePresetCard
                key={p.id}
                preset={p}
                active={activePreset === p.id}
                onClick={() => {
                  onChange({ ...DEFAULT_SUBTITLE_STYLE, ...p.style, highlightWords: style.highlightWords } as SubtitleStyle);
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
              <RangeInput label={`Words/line: ${style.maxWordsPerLine}`} min={2} max={6} value={style.maxWordsPerLine} onChange={(v) => update({ maxWordsPerLine: v })} />
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
                    <RangeInput label={`Blur: ${style.highlightShadowBlur}px`} min={0} max={24} value={style.highlightShadowBlur} onChange={(v) => update({ highlightShadowBlur: v })} />
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

        <Section title="Position">
          <div className="grid grid-cols-3 gap-2 mb-3">
            {(["top", "center", "bottom"] as const).map(p => (
              <button key={p} type="button" onClick={() => update({ position: p, positionY: p === "top" ? 15 : p === "bottom" ? 85 : 50 })} className={cn("py-2 rounded-lg border text-[11px] font-medium capitalize transition-colors", style.position === p ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600")}>{p}</button>
            ))}
          </div>
          <RangeInput label={`Vertical: ${style.positionY}%`} min={5} max={95} value={style.positionY} onChange={(v) => update({ positionY: v })} />
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
      </div>

      {/* Preview */}
      <div className="xl:col-span-4 p-4 flex flex-col items-center bg-zinc-950 overflow-y-auto">
        <div className="mb-3 flex w-full items-center justify-between gap-2">
          <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
          <span className="rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-[9px] text-zinc-400">{SUBTITLE_TRANSITION_META[style.lineTransition].label}</span>
        </div>
        <div className="relative w-full bg-zinc-900 rounded-lg overflow-hidden border border-zinc-800 shrink-0" style={{ aspectRatio: previewAspect }}>
          {thumbnailUrl && <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-cover" />}
          <div className="absolute inset-0 bg-gradient-to-b from-zinc-700/30 to-zinc-900/50" />
          <div className="absolute left-0 right-0 flex justify-center px-3" style={{ top: `${style.positionY}%`, transform: "translateY(-50%)" }}>
            {style.lineTransition === "emphasis" ? (
              /* Emphasis style preview: big keyword + small context */
              <div className="flex flex-col items-center gap-1">
                <span style={{
                  color: style.color,
                  fontSize: Math.max(style.fontSize * 0.25, 9),
                  fontFamily: `'${style.fontFamily}', sans-serif`,
                  fontWeight: Number(style.fontWeight),
                }}>gak banyak</span>
                <span style={{
                  color: style.highlightColor,
                  fontSize: Math.max(style.fontSize * 0.85, 20),
                  fontFamily: `'${style.fontFamily}', sans-serif`,
                  fontWeight: 900,
                  textShadow: style.highlightGlow ? `0 0 12px ${style.highlightGlowColor || style.highlightColor}, 0 0 24px ${style.highlightGlowColor || style.highlightColor}` : undefined,
                }}>Animasi</span>
              </div>
            ) : style.lineTransition === "line_reveal" ? (
              <div className={cn("overflow-hidden", getSubAnimationClass(style.animationStyle))} style={{
                backgroundColor: style.bgEnabled ? `${style.bgColor}${Math.round(style.bgOpacity * 255).toString(16).padStart(2, "0")}` : "transparent",
                padding: style.bgPadding * 0.42,
                borderRadius: style.bgRadius,
                borderLeft: `3px solid ${style.highlightColor}`,
              }}>
                <div style={{ width: "76%", height: 2, borderRadius: 99, backgroundColor: style.highlightColor, marginBottom: 5 }} />
                <div className="flex flex-wrap justify-center" style={{ gap: style.wordSpacing * 0.5 }}>
                  {["ini", "kata", "penting", "banget"].map((w, i) => {
                    const isHighlight = i === activeWordIdx;
                    return (
                      <span key={w} style={{
                        color: isHighlight ? style.highlightColor : style.color,
                        fontSize: Math.max(style.fontSize * 0.35, 10),
                        fontFamily: `'${style.fontFamily}', sans-serif`,
                        fontWeight: isHighlight ? 900 : Number(style.fontWeight),
                        letterSpacing: style.letterSpacing,
                        textTransform: style.uppercase ? "uppercase" : style.capitalize ? "capitalize" : "none",
                        WebkitTextStroke: style.strokeEnabled ? `${style.strokeWidth * 0.3}px ${style.strokeColor}` : undefined,
                        textShadow: style.shadowEnabled ? `0 0 ${style.shadowBlur}px ${style.shadowColor}` : undefined,
                      }}>{w}</span>
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
                    textShadow: [
                      (useDual ? style.highlightShadowEnabled : style.shadowEnabled) ? `0 0 ${useDual ? style.highlightShadowBlur : style.shadowBlur}px ${useDual ? style.highlightShadowColor : style.shadowColor}` : "",
                      shouldHighlight && style.highlightGlow ? `0 0 12px ${style.highlightGlowColor}` : "",
                    ].filter(Boolean).join(", ") || undefined,
                    WebkitTextStroke: (useDual ? style.highlightStrokeEnabled : style.strokeEnabled) ? `${(useDual ? style.highlightStrokeWidth : style.strokeWidth) * 0.3}px ${useDual ? style.highlightStrokeColor : style.strokeColor}` : undefined,
                    transition: "all 0.2s ease",
                    display: "inline-block",
                    // Highlight style decorations (only if NOT dual — dual uses its own complete style)
                    ...(!useDual && shouldHighlight && hlStyle === "underline" ? { textDecoration: "underline", textDecorationColor: style.highlightColor, textUnderlineOffset: "3px", textDecorationThickness: "2px" } : {}),
                    ...(!useDual && shouldHighlight && hlStyle === "background" ? { backgroundColor: `${style.highlightColor}30`, borderRadius: 3, padding: "1px 4px" } : {}),
                    ...(!useDual && shouldHighlight && hlStyle === "strikethrough" ? { textDecoration: "line-through", textDecorationColor: style.highlightColor, textDecorationThickness: "2px" } : {}),
                  };

                  return <span key={i} style={wordStyles}>{w}</span>;
                })}
              </div>
            )}
          </div>
          <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-600">{style.lineTransition === "emphasis" ? "emphasis" : style.animationStyle} | {style.position}</p>
        </div>
        <div className="mt-3 grid w-full grid-cols-2 gap-2 text-[10px]">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Font</span><p className="truncate text-zinc-300">{style.fontFamily}</p></div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Highlight</span><p className="truncate" style={{ color: style.highlightColor }}>{style.highlightColor}</p></div>
        </div>
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

function Checkbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="w-3.5 h-3.5 rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500/20" />
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
