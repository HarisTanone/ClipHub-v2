import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { makeTransform, scale as scaleFn, translateY as translateYFn } from "@remotion/animation-utils";
import { hexToRgba } from "../utils/hexToRgba";

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
  let opacity: number;
  if (animation === "cinematic_reveal") {
    // Cinematic: slower fade (1s in, 0.8s out) matching preview
    const fadeInSlow = Math.floor(1.0 * fps);
    const fadeOutSlow = Math.floor(0.8 * fps);
    opacity = interpolate(
      frame,
      [0, fadeInSlow, totalFrames - fadeOutSlow, totalFrames],
      [0, 1, 1, 0],
      { extrapolateRight: "clamp", extrapolateLeft: "clamp" }
    );
  } else {
    opacity = interpolate(
      frame,
      [0, fadeInFrames, totalFrames - fadeOutFrames, totalFrames],
      [0, 1, 1, 0],
      { extrapolateRight: "clamp", extrapolateLeft: "clamp" }
    );
  }

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
  } else if (animation === "glitch_rgb") {
    // No transform on main text — handled via separate RGB layers in render
  } else if (animation === "shake_neon") {
    // Subtle shake via sin/cos (matches preview: sin(t*30)*1.5, cos(t*35)*1)
    const shakeX = Math.sin(frame * 0.5) * 1.5;
    const shakeY = Math.cos(frame * 0.6) * 1;
    transform = `translate(${shakeX}px, ${shakeY}px)`;
  } else if (animation === "cinematic_reveal") {
    // No special transform — uses slow fade via opacity
  } else if (animation === "danger_bold") {
    // Pulse scale oscillation
    const pulse = 1 + Math.sin(frame * 0.17) * 0.02;
    transform = makeTransform([scaleFn(pulse)]);
  } else if (animation === "slide_punch_framer") {
    // Slide from left with bounce
    const slideProgress = Math.min(1, frame / (fps * 0.4));
    const slideX = (1 - slideProgress) * -100;
    const bounceScale = slideProgress >= 1 ? 1 : 0.95 + slideProgress * 0.05;
    transform = `translateX(${slideX}%) scale(${bounceScale})`;
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

  // Text shadow (only when explicitly enabled)
  const shadows: string[] = [];
  if (config.shadowEnabled) {
    shadows.push(`${config.shadowX || 0}px ${config.shadowY || 4}px ${config.shadowBlur || 12}px ${config.shadowColor || "#000000"}`);
  }
  if (config.glowEnabled) {
    shadows.push(`0 0 ${config.glowSize || 20}px ${config.glowColor || "#FFCC00"}`);
  }
  // shake_neon: add neon glow to main text (matching preview behavior)
  if (animation === "shake_neon") {
    shadows.push(`0 0 10px ${color}`, `0 0 20px ${color}`, `0 0 40px ${color}`);
  }
  // danger_bold: add red glow to main text
  if (animation === "danger_bold") {
    shadows.push(`0 0 10px #FF0000`, `0 0 20px rgba(255,0,0,0.5)`);
  }

  // Glitch effect
  const isGlitch = animation === "glitch";
  const glitchActive = isGlitch && frame % 8 < 2;
  const glitchX = Math.sin(frame * 0.7) * 4;

  return (
    <AbsoluteFill style={{ opacity }}>
      {/* Background overlay */}
      <AbsoluteFill style={{ backgroundColor: hexToRgba(bgColor, bgOpacity) }} />

      {/* Glitch RGB layers (legacy glitch animation) */}
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

      {/* glitch_rgb animation: persistent RGB channel separation */}
      {animation === "glitch_rgb" && (
        <>
          <div style={{
            position: "absolute", top: `${positionY}%`, left: 0, right: 0,
            transform: `translateY(-50%) translateX(${Math.sin(frame * 0.5) * 3 - 4}px)`,
            textAlign, padding: "0 40px",
            color: "#ff0000", fontSize, fontWeight, fontFamily,
            opacity: 0.5,
            mixBlendMode: "screen",
          }}>{displayText}</div>
          <div style={{
            position: "absolute", top: `${positionY}%`, left: 0, right: 0,
            transform: `translateY(-50%) translateX(${4 - Math.sin(frame * 0.5) * 3}px)`,
            textAlign, padding: "0 40px",
            color: "#00ffff", fontSize, fontWeight, fontFamily,
            opacity: 0.5,
            mixBlendMode: "screen",
          }}>{displayText}</div>
        </>
      )}

      {/* shake_neon animation: glow layers */}
      {animation === "shake_neon" && (
        <>
          <div style={{
            position: "absolute", top: `${positionY}%`, left: 0, right: 0,
            transform: `translateY(-50%)`,
            textAlign, padding: "0 40px",
            color: color, fontSize, fontWeight, fontFamily,
            opacity: 0.3,
            filter: "blur(4px)",
            textShadow: `0 0 12px ${color}, 0 0 24px ${color}`,
          }}>{displayText}</div>
          <div style={{
            position: "absolute", top: `${positionY}%`, left: 0, right: 0,
            transform: `translateY(-50%) translate(${Math.sin(frame * 0.8) * 2}px, ${Math.cos(frame * 0.6) * 2}px)`,
            textAlign, padding: "0 40px",
            color: color, fontSize, fontWeight, fontFamily,
            opacity: 0.35,
            filter: "blur(1.5px)",
            textShadow: `0 0 6px ${color}, 0 0 12px ${color}`,
          }}>{displayText}</div>
        </>
      )}

      {/* cinematic_reveal animation: letterbox bars */}
      {animation === "cinematic_reveal" && (
        <>
          <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: "12%", backgroundColor: "#000" }} />
          <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: "12%", backgroundColor: "#000" }} />
        </>
      )}

      {/* danger_bold animation: red glow behind main text */}
      {animation === "danger_bold" && (
        <div style={{
          position: "absolute", top: `${positionY}%`, left: 0, right: 0,
          transform: `translateY(-50%)`,
          textAlign, padding: "0 40px",
          color: "#FF0000", fontSize, fontWeight, fontFamily,
          opacity: 0.3,
          filter: "blur(3px)",
          textShadow: "0 0 10px #FF0000, 0 0 20px #FF0000, 0 0 40px rgba(255,0,0,0.3)",
        }}>{displayText}</div>
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
          // paintOrder: stroke renders behind fill — cleaner outline (only when explicitly enabled)
          paintOrder: config.strokeEnabled ? "stroke" : undefined,
          WebkitTextStroke: config.strokeEnabled
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
