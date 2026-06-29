import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { makeTransform, scale as scaleFn, translateY as translateYFn } from "@remotion/animation-utils";

interface HookConfig {
  animation?: string;
  fontFamily?: string;
  fontSize?: number;
  fontWeight?: string;
  letterSpacing?: number;
  lineHeight?: number;
  color?: string;
  gradientEnabled?: boolean;
  gradientFrom?: string;
  gradientTo?: string;
  gradientAngle?: number;
  shadowEnabled?: boolean;
  shadowColor?: string;
  shadowBlur?: number;
  shadowX?: number;
  shadowY?: number;
  glowEnabled?: boolean;
  glowColor?: string;
  glowSize?: number;
  bgColor?: string;
  bgOpacity?: number;
  position?: string;
  positionY?: number;
  textAlign?: string;
  uppercase?: boolean;
  italic?: boolean;
  lineEnabled?: boolean;
  linePosition?: string;
  lineColor?: string;
  lineWidth?: number;
  lineThickness?: number;
  lineOffset?: number;
  boxEnabled?: boolean;
  boxColor?: string;
  boxOpacity?: number;
  boxPadding?: number;
  boxRadius?: number;
  strokeEnabled?: boolean;
  strokeWidth?: number;
  strokeColor?: string;
  duration?: number;
  fadeIn?: number;
  fadeOut?: number;
}

interface HookLayerProps {
  text: string;
  config: HookConfig;
}

/**
 * Hook layer that renders EXACTLY like the Custom Style Editor preview.
 * All styles come from config (hook_style_config).
 */
export const HookLayer: React.FC<HookLayerProps> = ({ text, config }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const animation = config.animation || "fade_scale";
  const duration = config.duration || 3.0;
  const fadeIn = config.fadeIn || 0.3;
  const fadeOut = config.fadeOut || 0.3;
  const totalFrames = Math.floor(duration * fps);
  const fadeInFrames = Math.floor(fadeIn * fps);
  const fadeOutFrames = Math.floor(fadeOut * fps);

  // Opacity animation
  const opacity = interpolate(
    frame,
    [0, fadeInFrames, totalFrames - fadeOutFrames, totalFrames],
    [0, 1, 1, 0],
    { extrapolateRight: "clamp", extrapolateLeft: "clamp" }
  );

  // Animation-specific transforms using makeTransform (composable)
  let transform = "";
  if (animation === "fade_scale") {
    const s = spring({ frame, fps, config: { damping: 12, stiffness: 200 } });
    transform = makeTransform([scaleFn(s)]);
  } else if (animation === "slide_up") {
    const ty = interpolate(frame, [0, 15], [60, 0], { extrapolateRight: "clamp" });
    transform = makeTransform([translateYFn(ty), scaleFn(interpolate(frame, [0, 10], [0.9, 1], { extrapolateRight: "clamp" }))]);
  } else if (animation === "typewriter") {
    // handled in text display
  }

  // Typewriter text
  const displayText = animation === "typewriter"
    ? text.slice(0, Math.floor(interpolate(frame, [0, fps * 1.5], [0, text.length], { extrapolateRight: "clamp" })))
    : text;

  // Style values
  const fontFamily = config.fontFamily === "monospace" ? "monospace" : `'${config.fontFamily || "Poppins"}', sans-serif`;
  const fontSize = config.fontSize || 48;
  const fontWeight = Number(config.fontWeight || 800);
  const color = config.color || "#FFFFFF";
  const bgColor = config.bgColor || "#000000";
  const bgOpacity = config.bgOpacity ?? 0.6;
  const positionY = config.positionY ?? 50;
  const textAlign = (config.textAlign || "center") as any;

  // Text shadow
  const shadows: string[] = [];
  if (config.shadowEnabled !== false) {
    shadows.push(`${config.shadowX || 0}px ${config.shadowY || 4}px ${config.shadowBlur || 12}px ${config.shadowColor || "#000000"}`);
  }
  if (config.glowEnabled) {
    shadows.push(`0 0 ${config.glowSize || 20}px ${config.glowColor || "#FFCC00"}`);
  }

  // Glitch effect
  const isGlitch = animation === "glitch";
  const glitchActive = isGlitch && frame % 8 < 2;
  const glitchX = Math.sin(frame * 0.7) * 4;

  return (
    <AbsoluteFill style={{ opacity }}>
      {/* Background overlay */}
      <AbsoluteFill style={{ backgroundColor: bgColor, opacity: bgOpacity }} />

      {/* Glitch RGB layers */}
      {glitchActive && (
        <>
          <div style={{
            position: "absolute", top: `${positionY}%`, left: 0, right: 0,
            transform: `translateY(-50%) translateX(${glitchX - 3}px)`,
            textAlign, padding: "0 40px",
            color: "#ff0000", fontSize, fontWeight, fontFamily,
            opacity: 0.7, mixBlendMode: "screen",
          }}>
            {displayText}
          </div>
          <div style={{
            position: "absolute", top: `${positionY}%`, left: 0, right: 0,
            transform: `translateY(-50%) translateX(${glitchX + 3}px)`,
            textAlign, padding: "0 40px",
            color: "#00ffff", fontSize, fontWeight, fontFamily,
            opacity: 0.7, mixBlendMode: "screen",
          }}>
            {displayText}
          </div>
        </>
      )}

      {/* Main text */}
      <div style={{
        position: "absolute",
        top: `${positionY}%`,
        left: 0,
        right: 0,
        transform: `translateY(-50%) ${transform}`,
        textAlign,
        padding: "0 40px",
      }}>
        <span style={{
          display: "inline-block",
          color: config.gradientEnabled ? "transparent" : color,
          background: config.gradientEnabled ? `linear-gradient(${config.gradientAngle || 180}deg, ${config.gradientFrom || "#FFF"}, ${config.gradientTo || "#FFC"})` : undefined,
          WebkitBackgroundClip: config.gradientEnabled ? "text" : undefined,
          fontSize,
          fontWeight,
          fontFamily,
          fontStyle: config.italic ? "italic" : "normal",
          letterSpacing: config.letterSpacing || 0,
          lineHeight: config.lineHeight || 1.3,
          textShadow: shadows.length ? shadows.join(", ") : undefined,
          textTransform: config.uppercase ? "uppercase" : "none",
          // paintOrder: stroke renders behind fill — cleaner outline
          paintOrder: config.strokeEnabled !== false ? "stroke" : undefined,
          WebkitTextStroke: config.strokeEnabled !== false
            ? `${config.strokeWidth || Math.max(2, fontSize * 0.04)}px ${config.strokeColor || "rgba(0,0,0,0.8)"}`
            : undefined,
          ...(config.boxEnabled ? {
            backgroundColor: `${config.boxColor || "#FFF"}${Math.round((config.boxOpacity || 0.1) * 255).toString(16).padStart(2, "0")}`,
            padding: config.boxPadding || 20,
            borderRadius: config.boxRadius || 8,
          } : {}),
        }}>
          {config.uppercase ? displayText.toUpperCase() : displayText}
          {animation === "typewriter" && frame % 16 < 10 && <span style={{ opacity: 0.7 }}>|</span>}
        </span>
      </div>

      {/* Accent line */}
      {config.lineEnabled && <AccentLine config={config} />}
    </AbsoluteFill>
  );
};

function AccentLine({ config }: { config: HookConfig }) {
  const pos = config.linePosition || "bottom";
  const style: React.CSSProperties = {
    position: "absolute",
    backgroundColor: config.lineColor || "#FFCC00",
  };

  const offset = config.lineOffset || 12;
  const thickness = config.lineThickness || 4;
  const width = `${config.lineWidth || 60}%`;

  if (pos === "top") Object.assign(style, { top: offset, left: "50%", transform: "translateX(-50%)", width, height: thickness });
  if (pos === "bottom") Object.assign(style, { bottom: offset, left: "50%", transform: "translateX(-50%)", width, height: thickness });
  if (pos === "left") Object.assign(style, { left: offset, top: "50%", transform: "translateY(-50%)", height: width, width: thickness });
  if (pos === "right") Object.assign(style, { right: offset, top: "50%", transform: "translateY(-50%)", height: width, width: thickness });
  if (pos === "center-h") Object.assign(style, { top: `calc(50% + ${offset}px)`, left: "50%", transform: "translate(-50%, -50%)", width, height: thickness });
  if (pos === "center-v") Object.assign(style, { top: "50%", left: `calc(50% + ${offset}px)`, transform: "translate(-50%, -50%)", height: width, width: thickness });

  return <div style={style} />;
}
