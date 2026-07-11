/**
 * SubtitleLayer — Enhanced with official Remotion techniques:
 * - makeTransform for composable animations
 * - paintOrder: "stroke" for clean text outlines
 * - spring() for smooth enter animations
 * - User's configured fontSize is always respected (no fitText shrinking)
 * - hexToRgba for reliable background opacity
 */
import React, { useMemo } from "react";
import { AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { makeTransform, scale, translateY } from "@remotion/animation-utils";
import { hexToRgba } from "../utils/hexToRgba";
import type { Word } from "../types";

interface SubtitleConfig {
  stylePreset?: string;
  presetStyle?: string;
  subtitleStyle?: string;
  fontFamily?: string;
  fontSize?: number;
  fontWeight?: string;
  letterSpacing?: number;
  lineHeight?: number;
  color?: string;
  highlightColor?: string;
  highlightScale?: number;
  highlightBold?: boolean;
  highlightGlow?: boolean;
  highlightGlowColor?: string;
  highlightStyle?: string;
  highlightWords?: string[];
  // Dual style (separate font/style for highlight words)
  dualStyleEnabled?: boolean;
  highlightFontFamily?: string;
  highlightFontSize?: number;
  highlightFontWeight?: string;
  highlightLetterSpacing?: number;
  highlightItalic?: boolean;
  highlightUppercase?: boolean;
  highlightStrokeEnabled?: boolean;
  highlightStrokeColor?: string;
  highlightStrokeWidth?: number;
  highlightShadowEnabled?: boolean;
  highlightShadowColor?: string;
  highlightShadowBlur?: number;
  // Common
  bgEnabled?: boolean;
  bgColor?: string;
  bgOpacity?: number;
  bgRadius?: number;
  bgPadding?: number;
  position?: string;
  positionY?: number;
  maxWidthPct?: number;
  maxWidth?: number;
  uppercase?: boolean;
  capitalize?: boolean;
  italic?: boolean;
  strokeEnabled?: boolean;
  strokeColor?: string;
  strokeWidth?: number;
  shadowEnabled?: boolean;
  shadowColor?: string;
  shadowBlur?: number;
  maxWordsPerLine?: number;
  wordSpacing?: number;
  animationStyle?: string;
  animationSpeed?: number;
  lineTransition?: string;
}

interface SubtitleLayerProps {
  words: Word[];
  config: SubtitleConfig;
  fps: number;
}

export type SubtitlePageData = {
  startMs: number;
  endMs: number;
  tokens: Array<{ text: string; fromMs: number; toMs: number; highlight?: boolean }>;
};

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

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
  | "documentary"
  | "caption_strip"
  | "word_tiles"
  | "gradient_glass"
  | "comic_burst"
  | "terminal_type";

const SUBTITLE_VISUAL_PRESETS = new Set<SubtitleVisualPreset>([
  "classic",
  "dual_pop",
  "neon_pulse",
  "meme_impact",
  "editorial_banner",
  "spotlight_keyword",
  "lower_third",
  "bubble_chat",
  "minimal_clean",
  "breaking_tape",
  "quote_box",
  "documentary",
  "caption_strip",
  "word_tiles",
  "gradient_glass",
  "comic_burst",
  "terminal_type",
]);

const PRESET_ALIASES: Record<string, SubtitleVisualPreset> = {
  bold_yellow: "dual_pop",
  emphasis_orange: "spotlight_keyword",
  emphasis_green: "spotlight_keyword",
  neon: "neon_pulse",
  big_impact: "meme_impact",
  slide_clean: "editorial_banner",
  glow_purple: "neon_pulse",
};

export const resolveSubtitleVisualPreset = (config: SubtitleConfig): SubtitleVisualPreset => {
  const rawPreset = String(config.stylePreset || config.presetStyle || config.subtitleStyle || "").trim();
  if (SUBTITLE_VISUAL_PRESETS.has(rawPreset as SubtitleVisualPreset)) {
    return rawPreset as SubtitleVisualPreset;
  }
  if (PRESET_ALIASES[rawPreset]) return PRESET_ALIASES[rawPreset];

  const font = String(config.fontFamily || "").toLowerCase();
  if (config.lineTransition === "emphasis") return "spotlight_keyword";
  if (config.lineTransition === "line_reveal") return "editorial_banner";
  if (config.dualStyleEnabled) return "dual_pop";
  if (config.highlightGlow) return "neon_pulse";
  if (config.bgEnabled === false && config.animationStyle === "fade") return "minimal_clean";
  if (config.uppercase && (font.includes("anton") || font.includes("archivo") || font.includes("bebas"))) return "meme_impact";
  return "classic";
};

const defaultMaxWidthForPreset = (preset: SubtitleVisualPreset): number => {
  switch (preset) {
    case "lower_third":
      return 82;
    case "quote_box":
      return 80;
    case "minimal_clean":
      return 84;
    case "meme_impact":
      return 92;
    case "breaking_tape":
      return 88;
    case "caption_strip":
      return 96;
    case "terminal_type":
      return 86;
    default:
      return 90;
  }
};

export const resolveSubtitlePositionY = (config: SubtitleConfig): number => {
  if (typeof config.positionY === "number" && Number.isFinite(config.positionY)) {
    return clamp(config.positionY, 8, 94);
  }
  if (config.position === "top") return 18;
  if (config.position === "center") return 50;
  return 85;
};

export const normaliseSubtitleWords = (words: Word[]): Word[] => {
  let lastEnd = 0;
  const seen = new Set<string>();

  return [...words]
    .sort((a, b) => (Number(a.start) || 0) - (Number(b.start) || 0))
    .reduce<Word[]>((acc, word) => {
      const text = String(word.word || "").trim();
      if (!text) return acc;

      let start = Math.max(0, Number(word.start) || 0);
      let end = Math.max(0, Number(word.end) || 0);
      if (end <= start) end = start + 0.18;

      const dedupeKey = `${text.toLowerCase()}-${Math.round(start * 10)}`;
      if (seen.has(dedupeKey)) return acc;
      seen.add(dedupeKey);

      if (start < lastEnd) start = lastEnd + 0.01;
      if (end <= start) end = start + 0.18;

      const cleaned = {
        word: text,
        start: Number(start.toFixed(3)),
        end: Number(end.toFixed(3)),
        highlight: Boolean(word.highlight),
      };
      acc.push(cleaned);
      lastEnd = cleaned.end;
      return acc;
    }, []);
};

export const groupWordsToSubtitlePages = (
  words: Word[],
  maxWordsPerLine = 4,
): SubtitlePageData[] => {
  const maxPerLine = clamp(Math.round(maxWordsPerLine || 4), 1, 8);
  const PAUSE_THRESHOLD = 0.5;
  const result: SubtitlePageData[] = [];
  let current: Word[] = [];

  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    const nextWord = words[i + 1];

    current.push(w);

    const isLastWord = !nextWord;
    const hasPunctuation = /[.,!?;:]$/.test(w.word);
    const gapToNext = nextWord ? nextWord.start - w.end : Infinity;
    const pageIsFull = current.length >= maxPerLine;

    if (pageIsFull || (hasPunctuation && current.length >= 2) || gapToNext > PAUSE_THRESHOLD || isLastWord) {
      if (current.length > 0) {
        result.push({
          startMs: Math.round(current[0].start * 1000),
          endMs: Math.round(current[current.length - 1].end * 1000),
          tokens: current.map((cw) => ({
            text: `${cw.word} `,
            fromMs: Math.round(cw.start * 1000),
            toMs: Math.round(cw.end * 1000),
            highlight: Boolean(cw.highlight),
          })),
        });
      }
      current = [];
    }
  }

  return result;
};

/**
 * Enhanced subtitle layer — uses manual word grouping for reliability,
 * spring animations, and fitText for responsive sizing.
 */
export const SubtitleLayer: React.FC<SubtitleLayerProps> = ({ words, config, fps }) => {

  const fontFamily = config.fontFamily === "monospace" ? "monospace" : `'${config.fontFamily || "Poppins"}', sans-serif`;
  const fontSize = config.fontSize || 34;
  const color = config.color || "#FFFFFF";
  const highlightColor = config.highlightColor || "#FFCC00";
  const positionY = resolveSubtitlePositionY(config);
  const visualPreset = resolveSubtitleVisualPreset(config);
  const normalisedWords = useMemo(() => normaliseSubtitleWords(words), [words]);

  // Group words into pages — uses natural pauses + punctuation, not just word count
  const pages = useMemo(() => {
    return groupWordsToSubtitlePages(normalisedWords, config.maxWordsPerLine || 4);
  }, [normalisedWords, config.maxWordsPerLine]);

  return (
    <AbsoluteFill>
      {pages.map((page, index) => {
        const nextPage = pages[index + 1] ?? null;
        const startFrame = Math.round((page.startMs / 1000) * fps);
        // End at next page start (prevent double-render overlap) or natural end + small buffer
        const nextStartFrame = nextPage ? Math.round((nextPage.startMs / 1000) * fps) : Infinity;
        const naturalEnd = Math.round((page.endMs / 1000) * fps) + 2;
        const endFrame = Math.min(naturalEnd, nextStartFrame);
        const durationInFrames = endFrame - startFrame;
        if (durationInFrames <= 0) return null;

        return (
          <Sequence key={index} from={startFrame} durationInFrames={durationInFrames}>
            <SubtitlePage
              page={page}
              config={config}
              fontFamily={fontFamily}
              fontSize={fontSize}
              color={color}
              highlightColor={highlightColor}
              positionY={positionY}
              visualPreset={visualPreset}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

// Individual subtitle page with spring animation
function SubtitlePage({
  page,
  config,
  fontFamily,
  fontSize,
  color,
  highlightColor,
  positionY,
  visualPreset,
}: {
  page: SubtitlePageData;
  config: SubtitleConfig;
  fontFamily: string;
  fontSize: number;
  color: string;
  highlightColor: string;
  positionY: number;
  visualPreset: SubtitleVisualPreset;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const timeInMs = (frame / fps) * 1000;
  const animStyle = config.animationStyle || "pop";
  const lineTransition = config.lineTransition || "word_pop";
  const animationSpeed = config.animationSpeed || 1;
  const highlightWords = config.highlightWords || [];
  const highlightScale = config.highlightScale || 1.2;
  const highlightStyleType = config.highlightStyle || "scale";
  const maxWidthPct = clamp(Number(config.maxWidthPct ?? config.maxWidth ?? defaultMaxWidthForPreset(visualPreset)), 45, 96);
  const alignLeft = visualPreset === "lower_third" || visualPreset === "documentary" || visualPreset === "terminal_type";
  const isImpactPreset = visualPreset === "meme_impact" || visualPreset === "breaking_tape" || visualPreset === "comic_burst";
  const isLightPanel = visualPreset === "bubble_chat" || visualPreset === "breaking_tape" || visualPreset === "quote_box" || visualPreset === "word_tiles";
  const presetTransform = visualPreset === "breaking_tape" ? "rotate(-1.1deg)" : undefined;

  const presetPanelStyle: React.CSSProperties = (() => {
    switch (visualPreset) {
      case "neon_pulse":
        return {
          border: `1px solid ${hexToRgba(highlightColor, 0.52)}`,
          boxShadow: `0 0 28px ${hexToRgba(highlightColor, 0.32)}, inset 0 0 22px rgba(2,6,23,0.65)`,
        };
      case "meme_impact":
        return {
          filter: "drop-shadow(0 10px 18px rgba(0,0,0,0.55))",
        };
      case "editorial_banner":
        return {
          borderLeft: `9px solid ${highlightColor}`,
          boxShadow: "0 14px 30px rgba(0,0,0,0.34)",
        };
      case "lower_third":
        return {
          borderLeft: `10px solid ${highlightColor}`,
          boxShadow: "0 18px 34px rgba(0,0,0,0.42)",
        };
      case "bubble_chat":
        return {
          border: "1px solid rgba(17,24,39,0.12)",
          boxShadow: "0 18px 38px rgba(0,0,0,0.26)",
        };
      case "breaking_tape":
        return {
          border: "2px solid rgba(17,17,17,0.9)",
          boxShadow: "0 16px 28px rgba(0,0,0,0.35)",
        };
      case "quote_box":
        return {
          borderLeft: `7px solid ${highlightColor}`,
          boxShadow: "0 18px 40px rgba(0,0,0,0.28)",
        };
      case "documentary":
        return {
          borderLeft: `5px solid ${highlightColor}`,
          boxShadow: "0 16px 32px rgba(0,0,0,0.36)",
        };
      case "dual_pop":
        return {
          border: `1px solid ${hexToRgba(highlightColor, 0.34)}`,
          boxShadow: "0 12px 28px rgba(0,0,0,0.35)",
        };
      case "caption_strip":
        return {
          width: "100%",
          borderTop: `4px solid ${highlightColor}`,
          borderBottom: `4px solid ${hexToRgba(highlightColor, 0.45)}`,
          boxShadow: "0 16px 32px rgba(0,0,0,0.45)",
        };
      case "gradient_glass":
        return {
          background: `linear-gradient(120deg, ${hexToRgba(config.bgColor || "#312E81", 0.76)}, ${hexToRgba(highlightColor, 0.28)})`,
          border: `1px solid ${hexToRgba(highlightColor, 0.55)}`,
          boxShadow: `0 18px 44px rgba(0,0,0,0.38), 0 0 26px ${hexToRgba(highlightColor, 0.2)}`,
          backdropFilter: "blur(12px)",
        };
      case "comic_burst":
        return {
          filter: `drop-shadow(9px 10px 0 ${hexToRgba("#111827", 0.72)})`,
        };
      case "terminal_type":
        return {
          border: `2px solid ${hexToRgba(highlightColor, 0.55)}`,
          borderTop: `16px solid ${hexToRgba(highlightColor, 0.35)}`,
          boxShadow: `0 0 28px ${hexToRgba(highlightColor, 0.2)}, inset 0 0 24px rgba(0,0,0,0.48)`,
        };
      default:
        return {};
    }
  })();

  // Spring enter animation (from @remotion/animation-utils)
  const enter = spring({
    frame,
    fps,
    config: { damping: 200 },
    durationInFrames: Math.max(3, Math.round(6 / animationSpeed)),
  });

  // Compute enter transform using makeTransform (composable)
  const enterTransform = animStyle === "none" ? undefined : makeTransform([
    scale(interpolate(enter, [0, 1], [animStyle === "pop" ? 0.85 : 0.95, 1])),
    translateY(interpolate(enter, [0, 1], [animStyle === "slide" ? 20 : 8, 0])),
  ]);
  const combinedTransform = [enterTransform, presetTransform].filter(Boolean).join(" ") || undefined;

  // Use user's configured fontSize directly — user's preference is king.
  // fitText is NOT used to shrink below the user's configured value.
  // CSS word wrapping handles overflow instead of font shrinking.
  const responsiveFontSize = fontSize;

  // Fade opacity
  const opacity = interpolate(frame, [0, 3], [0, 1], { extrapolateRight: "clamp" });
  const tokens = page.tokens || [];
  const activeMatchIndex = tokens.findIndex((t: any) => {
    const startRel = (t.fromMs || 0) - (page.startMs || 0);
    const endRel = (t.toMs || 0) - (page.startMs || 0);
    return startRel <= timeInMs && endRel > timeInMs;
  });
  const fallbackIndex = tokens.reduce((best: number, token: any, index: number) => {
    const current = (token.text || "").trim();
    const bestText = (tokens[best]?.text || "").trim();
    return current.length > bestText.length ? index : best;
  }, 0);
  const emphasisIndex = activeMatchIndex >= 0 ? activeMatchIndex : fallbackIndex;
  const emphasisToken = tokens[emphasisIndex];
  const emphasisWord = (emphasisToken?.text || "").trim();
  const contextText = tokens
    .filter((_: any, index: number) => index !== emphasisIndex)
    .map((token: any) => (token.text || "").trim())
    .filter(Boolean)
    .join(" ");

  const applyCase = (word: string, uppercase?: boolean, capitalize?: boolean) => {
    if (uppercase) return word.toUpperCase();
    if (capitalize) return word.replace(/\b\w/g, (c) => c.toUpperCase());
    return word;
  };

  return (
    <AbsoluteFill style={{ opacity }}>
      <div style={{
        position: "absolute",
        top: `${positionY}%`,
        transform: `translateY(-50%)`,
        left: 0, right: 0,
        display: "flex",
        justifyContent: alignLeft ? "flex-start" : "center",
        padding: alignLeft ? "0 46px" : "0 24px",
      }}>
        <div style={{
          position: "relative",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: alignLeft ? "flex-start" : "center",
          alignItems: "baseline",
          gap: config.wordSpacing || 6,
          maxWidth: `${maxWidthPct}%`,
          lineHeight: config.lineHeight || 1.12,
          textAlign: alignLeft ? "left" : "center",
          colorScheme: isLightPanel ? "light" : "dark",
          overflowWrap: "anywhere",
          wordBreak: "break-word",
          transform: combinedTransform,
          overflow: visualPreset === "bubble_chat" ? "visible" : lineTransition === "line_reveal" ? "hidden" : undefined,
          ...(config.bgEnabled === true ? {
            backgroundColor: hexToRgba(config.bgColor || "#000000", config.bgOpacity ?? 0.4),
            borderRadius: config.bgRadius || 8,
            padding: config.bgPadding || 12,
          } : {}),
          ...presetPanelStyle,
        }}>
          {visualPreset === "neon_pulse" && (
            <div style={{
              position: "absolute",
              top: 6,
              left: 16,
              right: 16,
              height: 3,
              borderRadius: 999,
              background: `linear-gradient(90deg, transparent, ${highlightColor}, transparent)`,
              boxShadow: `0 0 16px ${highlightColor}`,
              zIndex: 0,
            }} />
          )}
          {visualPreset === "lower_third" && (
            <div style={{
              position: "absolute",
              top: 0,
              bottom: 0,
              left: 0,
              width: 72,
              background: `linear-gradient(90deg, ${hexToRgba(highlightColor, 0.22)}, transparent)`,
              zIndex: 0,
            }} />
          )}
          {visualPreset === "bubble_chat" && (
            <div style={{
              position: "absolute",
              bottom: -10,
              left: 34,
              width: 22,
              height: 22,
              transform: "rotate(45deg)",
              backgroundColor: hexToRgba(config.bgColor || "#F8FAFC", config.bgOpacity ?? 0.94),
              borderRight: "1px solid rgba(17,24,39,0.08)",
              borderBottom: "1px solid rgba(17,24,39,0.08)",
              zIndex: 0,
            }} />
          )}
          {visualPreset === "breaking_tape" && (
            <div style={{
              position: "absolute",
              inset: 0,
              backgroundImage: `repeating-linear-gradient(135deg, transparent 0 18px, ${hexToRgba("#111111", 0.08)} 18px 26px)`,
              zIndex: 0,
            }} />
          )}
          {visualPreset === "quote_box" && (
            <div style={{
              position: "absolute",
              inset: 9,
              border: `1px solid ${hexToRgba(highlightColor, 0.24)}`,
              zIndex: 0,
            }} />
          )}
          {visualPreset === "gradient_glass" && (
            <div style={{ position: "absolute", inset: 0, borderRadius: "inherit", background: "linear-gradient(115deg, rgba(255,255,255,.15), transparent 42%)", zIndex: 0 }} />
          )}
          {visualPreset === "terminal_type" && (
            <span style={{ position: "relative", zIndex: 1, color: highlightColor, fontFamily: "monospace", fontSize, fontWeight: 900, marginRight: 4 }}>&gt;</span>
          )}
          {lineTransition === "line_reveal" && (
            <div style={{
              width: "100%",
              height: 5,
              borderRadius: 999,
              backgroundColor: highlightColor,
              marginBottom: 8,
              transformOrigin: "left center",
              transform: `scaleX(${interpolate(enter, [0, 1], [0.15, 1])})`,
              position: "relative",
              zIndex: 1,
            }} />
          )}
          {lineTransition === "emphasis" ? (
            <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 8, textAlign: "center" }}>
              {contextText && (
                <span style={{
                  color,
                  fontSize: Math.max(18, fontSize * 0.48),
                  fontWeight: Number(config.fontWeight || 700),
                  fontFamily,
                  fontStyle: config.italic ? "italic" : "normal",
                  letterSpacing: config.letterSpacing || 0,
                  lineHeight: config.lineHeight || 1.12,
                  overflowWrap: "anywhere",
                  opacity: visualPreset === "spotlight_keyword" ? 0.88 : 1,
                  textShadow: config.shadowEnabled ? `0 0 ${config.shadowBlur || 8}px ${config.shadowColor || "#000"}` : undefined,
                  WebkitTextStroke: config.strokeEnabled ? `${Math.max(1, (config.strokeWidth || 2) * 0.55)}px ${config.strokeColor || "#000"}` : undefined,
                }}>{applyCase(contextText, config.uppercase, config.capitalize)}</span>
              )}
              <span style={{
                color: highlightColor,
                fontSize: config.dualStyleEnabled ? (config.highlightFontSize || fontSize * 1.35) : fontSize * highlightScale * 1.2,
                fontWeight: config.dualStyleEnabled ? Number(config.highlightFontWeight || 900) : 900,
                fontFamily: config.dualStyleEnabled ? `'${config.highlightFontFamily || "Anton"}', sans-serif` : fontFamily,
                fontStyle: config.dualStyleEnabled ? (config.highlightItalic ? "italic" : "normal") : (config.italic ? "italic" : "normal"),
                letterSpacing: config.dualStyleEnabled ? (config.highlightLetterSpacing || 0) : (config.letterSpacing || 0),
                lineHeight: config.lineHeight || 1.05,
                overflowWrap: "anywhere",
                textShadow: [
                  visualPreset === "spotlight_keyword" ? `0 0 30px ${hexToRgba(highlightColor, 0.65)}` : "",
                  config.highlightGlow ? `0 0 16px ${config.highlightGlowColor || highlightColor}` : "",
                  (config.dualStyleEnabled ? config.highlightShadowEnabled : config.shadowEnabled) ? `0 0 ${config.dualStyleEnabled ? (config.highlightShadowBlur || 12) : (config.shadowBlur || 8)}px ${config.dualStyleEnabled ? (config.highlightShadowColor || "#000") : (config.shadowColor || "#000")}` : "",
                ].filter(Boolean).join(", ") || undefined,
                paintOrder: (config.dualStyleEnabled ? config.highlightStrokeEnabled : config.strokeEnabled) ? "stroke" : undefined,
                WebkitTextStroke: (config.dualStyleEnabled ? config.highlightStrokeEnabled : config.strokeEnabled)
                  ? `${config.dualStyleEnabled ? (config.highlightStrokeWidth || 3) : (config.strokeWidth || 2)}px ${config.dualStyleEnabled ? (config.highlightStrokeColor || "#000") : (config.strokeColor || "#000")}`
                  : undefined,
                ...(visualPreset === "spotlight_keyword" ? {
                  padding: "0 18px",
                  borderRadius: 10,
                  background: `linear-gradient(90deg, transparent, ${hexToRgba(highlightColor, 0.16)}, transparent)`,
                } : {}),
                transform: `scale(${interpolate(enter, [0, 1], [0.86, 1])})`,
              }}>{applyCase(emphasisWord, config.dualStyleEnabled ? config.highlightUppercase : config.uppercase, config.capitalize)}</span>
            </div>
          ) : page.tokens?.map((t, i) => {
            const startRel = (t.fromMs || 0) - (page.startMs || 0);
            const endRel = (t.toMs || 0) - (page.startMs || 0);
            const isActive = startRel <= timeInMs && endRel > timeInMs;
            const wordText = (t.text || "").trim();
            if (!wordText) return null;
            const isKeyword = Boolean(t.highlight) || highlightWords.includes(wordText.toLowerCase());
            const shouldHighlight = isActive || isKeyword;
            const presetWantsDual = visualPreset === "dual_pop" || visualPreset === "neon_pulse" || visualPreset === "meme_impact";
            const useDual = shouldHighlight && (config.dualStyleEnabled === true || (config.dualStyleEnabled === undefined && presetWantsDual));

            const wordFontSize = useDual
              ? (config.highlightFontSize || responsiveFontSize * (isImpactPreset ? 1.22 : 1.12))
              : responsiveFontSize;
            const presetScale = shouldHighlight && isImpactPreset ? 1.1 : shouldHighlight && visualPreset === "neon_pulse" ? 1.06 : 1;
            const wordScale = shouldHighlight ? (useDual ? presetScale : highlightScale * presetScale) : 1;
            const wordColor = shouldHighlight ? highlightColor : color;
            const wordWeight = useDual
              ? Number(config.highlightFontWeight || 900)
              : (shouldHighlight && config.highlightBold !== false ? 900 : Number(config.fontWeight || 700));
            const wordFontFamily = useDual
              ? `'${config.highlightFontFamily || "Anton"}', sans-serif`
              : fontFamily;

            // Shadows
            const shadows: string[] = [];
            if (useDual ? config.highlightShadowEnabled : config.shadowEnabled === true) {
              shadows.push(`0 0 ${useDual ? (config.highlightShadowBlur || 12) : (config.shadowBlur || 8)}px ${useDual ? (config.highlightShadowColor || "#000") : (config.shadowColor || "#000")}`);
            }
            if (shouldHighlight && config.highlightGlow) {
              shadows.push(`0 0 12px ${config.highlightGlowColor || highlightColor}`);
            }
            if (shouldHighlight && visualPreset === "neon_pulse") {
              shadows.push(`0 0 24px ${highlightColor}`);
            }
            if (isImpactPreset) {
              shadows.push(`0 7px 16px ${hexToRgba("#000000", 0.5)}`);
            }

            const wordUppercase = useDual ? config.highlightUppercase : config.uppercase;
            const displayText = applyCase(wordText, wordUppercase, useDual ? false : config.capitalize);
            const presetBackground = visualPreset === "word_tiles"
              ? (shouldHighlight ? highlightColor : hexToRgba(color, 0.92))
              : shouldHighlight && visualPreset === "bubble_chat"
              ? hexToRgba(highlightColor, 0.16)
              : shouldHighlight && visualPreset === "breaking_tape"
                ? hexToRgba("#111111", 0.12)
                : undefined;
            const presetPadding = visualPreset === "word_tiles" ? "8px 12px" : presetBackground ? "2px 8px" : undefined;
            const textStroke = (useDual ? config.highlightStrokeEnabled : config.strokeEnabled)
              ? `${(useDual ? (config.highlightStrokeWidth || 3) : (config.strokeWidth || 2))}px ${useDual ? (config.highlightStrokeColor || "#000") : (config.strokeColor || "#000")}`
              : visualPreset === "meme_impact"
                ? `${shouldHighlight ? 4 : 3}px #000000`
                : visualPreset === "comic_burst"
                  ? `${shouldHighlight ? 5 : 4}px #111827`
                : undefined;
            const transformParts = [
              wordScale !== 1 ? `scale(${wordScale})` : "",
              shouldHighlight && visualPreset === "meme_impact" ? "translateY(-4px)" : "",
              shouldHighlight && visualPreset === "breaking_tape" ? "skewX(-4deg)" : "",
              shouldHighlight && visualPreset === "comic_burst" ? "rotate(-3deg) translateY(-5px)" : "",
            ].filter(Boolean);

            return (
              <span
                key={`${t.fromMs}-${i}`}
                style={{
                  position: "relative",
                  zIndex: 1,
                  display: "inline-block",
                  color: visualPreset === "word_tiles" ? (shouldHighlight ? "#18181B" : "#FFFFFF") : wordColor,
                  fontSize: wordFontSize,
                  fontWeight: wordWeight,
                  fontFamily: wordFontFamily,
                  fontStyle: useDual ? (config.highlightItalic ? "italic" : "normal") : (config.italic ? "italic" : "normal"),
                  letterSpacing: useDual ? (config.highlightLetterSpacing || 0) : (config.letterSpacing || 0),
                  textShadow: shadows.length ? shadows.join(", ") : undefined,
                  paintOrder: textStroke ? "stroke" : undefined,
                  WebkitTextStroke: textStroke,
                  backgroundColor: presetBackground,
                  borderRadius: presetBackground ? (visualPreset === "word_tiles" ? 7 : 8) : undefined,
                  padding: presetPadding,
                  // Highlight style decorations (only if NOT dual)
                  ...(!useDual && shouldHighlight && highlightStyleType === "underline" ? { textDecoration: "underline", textDecorationColor: highlightColor, textUnderlineOffset: "4px", textDecorationThickness: "3px" } : {}),
                  ...(!useDual && shouldHighlight && highlightStyleType === "background" ? { backgroundColor: `${highlightColor}30`, borderRadius: 4, padding: "2px 6px" } : {}),
                  ...(!useDual && shouldHighlight && highlightStyleType === "strikethrough" ? { textDecoration: "line-through", textDecorationColor: highlightColor, textDecorationThickness: "3px" } : {}),
                  transition: "transform 0.1s ease-out, color 0.05s",
                  transform: transformParts.length ? transformParts.join(" ") : undefined,
                  transformOrigin: "center bottom",
                  lineHeight: config.lineHeight || 1.12,
                  maxWidth: "100%",
                  overflowWrap: "anywhere",
                  wordBreak: "break-word",
                }}
              >
                {displayText}
              </span>
            );
          }) || (page.tokens?.map((t: any) => t.text).join("") || "")}
        </div>
      </div>
    </AbsoluteFill>
  );
}
