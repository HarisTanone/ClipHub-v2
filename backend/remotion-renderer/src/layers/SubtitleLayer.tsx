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
  uppercase?: boolean;
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
}

interface SubtitleLayerProps {
  words: Word[];
  config: SubtitleConfig;
  fps: number;
}

/**
 * Enhanced subtitle layer — uses manual word grouping for reliability,
 * spring animations, and fitText for responsive sizing.
 */
export const SubtitleLayer: React.FC<SubtitleLayerProps> = ({ words, config, fps }) => {

  const fontFamily = config.fontFamily === "monospace" ? "monospace" : `'${config.fontFamily || "Poppins"}', sans-serif`;
  const fontSize = config.fontSize || 34;
  const color = config.color || "#FFFFFF";
  const highlightColor = config.highlightColor || "#FFCC00";
  const positionY = config.positionY ?? 85;

  // Group words into pages — manual grouping is most reliable with our word format
  const pages = useMemo(() => {
    const maxPerLine = config.maxWordsPerLine || 3;
    const result: any[] = [];
    let current: Word[] = [];

    for (const w of words) {
      // Break on gap > 0.5s or word count
      const gapTooLarge = current.length > 0 && w.start - current[current.length - 1].end > 0.5;
      if (current.length >= maxPerLine || gapTooLarge) {
        if (current.length > 0) {
          result.push({
            startMs: Math.round(current[0].start * 1000),
            endMs: Math.round(current[current.length - 1].end * 1000),
            tokens: current.map(cw => ({ text: cw.word + " ", fromMs: Math.round(cw.start * 1000), toMs: Math.round(cw.end * 1000) })),
          });
        }
        current = [];
      }
      current.push(w);
    }
    if (current.length > 0) {
      result.push({
        startMs: Math.round(current[0].start * 1000),
        endMs: Math.round(current[current.length - 1].end * 1000),
        tokens: current.map(cw => ({ text: cw.word + " ", fromMs: Math.round(cw.start * 1000), toMs: Math.round(cw.end * 1000) })),
      });
    }
    return result;
  }, [words, config.maxWordsPerLine]);

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
}: {
  page: any;
  config: SubtitleConfig;
  fontFamily: string;
  fontSize: number;
  color: string;
  highlightColor: string;
  positionY: number;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const timeInMs = (frame / fps) * 1000;
  const animStyle = config.animationStyle || "pop";
  const highlightWords = config.highlightWords || [];
  const highlightScale = config.highlightScale || 1.2;
  const highlightStyleType = config.highlightStyle || "scale";

  // Spring enter animation (from @remotion/animation-utils)
  const enter = spring({
    frame,
    fps,
    config: { damping: 200 },
    durationInFrames: 6,
  });

  // Compute enter transform using makeTransform (composable)
  const enterTransform = animStyle === "none" ? undefined : makeTransform([
    scale(interpolate(enter, [0, 1], [animStyle === "pop" ? 0.85 : 0.95, 1])),
    translateY(interpolate(enter, [0, 1], [animStyle === "slide" ? 20 : 8, 0])),
  ]);

  // Use user's configured fontSize directly — user's preference is king.
  // fitText is NOT used to shrink below the user's configured value.
  // CSS word wrapping handles overflow instead of font shrinking.
  const responsiveFontSize = fontSize;

  // Fade opacity
  const opacity = interpolate(frame, [0, 3], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ opacity }}>
      <div style={{
        position: "absolute",
        top: `${positionY}%`,
        transform: `translateY(-50%)`,
        left: 0, right: 0,
        display: "flex",
        justifyContent: "center",
        padding: "0 20px",
      }}>
        <div style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: config.wordSpacing || 6,
          transform: enterTransform,
          ...(config.bgEnabled === true ? {
            backgroundColor: hexToRgba(config.bgColor || "#000000", config.bgOpacity ?? 0.4),
            borderRadius: config.bgRadius || 8,
            padding: config.bgPadding || 12,
          } : {}),
        }}>
          {page.tokens?.map((t: any, i: number) => {
            const startRel = (t.fromMs || 0) - (page.startMs || 0);
            const endRel = (t.toMs || 0) - (page.startMs || 0);
            const isActive = startRel <= timeInMs && endRel > timeInMs;
            const wordText = (t.text || "").trim();
            if (!wordText) return null;
            const isKeyword = highlightWords.includes(wordText.toLowerCase());
            const shouldHighlight = isActive || isKeyword;
            const useDual = shouldHighlight && config.dualStyleEnabled;

            const wordFontSize = useDual
              ? (config.highlightFontSize || responsiveFontSize * highlightScale)
              : (shouldHighlight ? responsiveFontSize * highlightScale : responsiveFontSize);
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

            const wordUppercase = useDual ? config.highlightUppercase : config.uppercase;
            const displayText = wordUppercase ? wordText.toUpperCase() : wordText;

            return (
              <span
                key={`${t.fromMs}-${i}`}
                style={{
                  display: "inline-block",
                  color: wordColor,
                  fontSize: wordFontSize,
                  fontWeight: wordWeight,
                  fontFamily: wordFontFamily,
                  fontStyle: useDual ? (config.highlightItalic ? "italic" : "normal") : (config.italic ? "italic" : "normal"),
                  letterSpacing: useDual ? (config.highlightLetterSpacing || 0) : (config.letterSpacing || 0),
                  textShadow: shadows.length ? shadows.join(", ") : undefined,
                  paintOrder: (useDual ? config.highlightStrokeEnabled : config.strokeEnabled) ? "stroke" : undefined,
                  WebkitTextStroke: (useDual ? config.highlightStrokeEnabled : config.strokeEnabled)
                    ? `${(useDual ? (config.highlightStrokeWidth || 3) : (config.strokeWidth || 2))}px ${useDual ? (config.highlightStrokeColor || "#000") : (config.strokeColor || "#000")}`
                    : undefined,
                  // Highlight style decorations (only if NOT dual)
                  ...(!useDual && shouldHighlight && highlightStyleType === "underline" ? { textDecoration: "underline", textDecorationColor: highlightColor, textUnderlineOffset: "4px", textDecorationThickness: "3px" } : {}),
                  ...(!useDual && shouldHighlight && highlightStyleType === "background" ? { backgroundColor: `${highlightColor}30`, borderRadius: 4, padding: "2px 6px" } : {}),
                  ...(!useDual && shouldHighlight && highlightStyleType === "strikethrough" ? { textDecoration: "line-through", textDecorationColor: highlightColor, textDecorationThickness: "3px" } : {}),
                  transition: "color 0.05s",
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
