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
  lineAutoWidth?: boolean;
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
  badgeEnabled?: boolean;
  badgeText?: string;
  badgeSubText?: string;
  footerText?: string;
  decorativeElements?: boolean;
  motionIntensity?: number;
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

  const animation = config.animation || "podcast_lower_third";
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
  } else if (animation === "bold_slam") {
    // MrBeast-style yellow card slam with bounce + shake
    const entrance = spring({ frame, fps, config: { damping: 9, stiffness: 180, mass: 0.6 } });
    const shakeX = frame > 14 && frame < 26 ? Math.sin(frame * 2.2) * 3 : 0;
    const shakeY = frame > 14 && frame < 26 ? Math.cos(frame * 1.8) * 3 : 0;
    const rotate = interpolate(frame, [0, 10], [-8, 0], { extrapolateRight: "clamp" });
    transform = `translate(${shakeX}px, ${shakeY}px) scale(${entrance}) rotate(${rotate}deg)`;
  }

  // Typewriter text
  const displayText = animation === "typewriter"
    ? text.slice(0, Math.floor(interpolate(frame, [0, fps * 1.5], [0, text.length], { extrapolateRight: "clamp" })))
    : text;
  const renderedText = config.uppercase ? displayText.toUpperCase() : displayText;

  // Style values
  const fontFamily = config.fontFamily === "monospace" ? "monospace" : `'${config.fontFamily || "Poppins"}', sans-serif`;
  const fontSize = config.fontSize || 48;
  const fontWeight = Number(config.fontWeight || 800);
  const color = config.color || "#FFFFFF";
  const bgColor = config.bgColor || "#000000";
  const bgOpacity = config.bgOpacity ?? 0.6;
  const positionY = config.positionY ?? 50;
  const textAlign = (config.textAlign || "center") as any;
  const badgeEnabled = config.badgeEnabled !== false;
  const badgeText = config.badgeText || "";
  const decorativeElements = config.decorativeElements !== false;
  const motionIntensity = Math.max(0, config.motionIntensity ?? 1);

  // Text shadow (only when explicitly enabled)
  const shadows: string[] = [];
  if (config.shadowEnabled) {
    shadows.push(`${config.shadowX || 0}px ${config.shadowY || 4}px ${config.shadowBlur || 12}px ${config.shadowColor || "#000000"}`);
  }
  if (config.glowEnabled) {
    const gc = config.glowColor || "#FFCC00";
    const gs = config.glowSize || 20;
    shadows.push(
      `0 0 ${Math.max(4, Math.round(gs * 0.4))}px ${gc}`,
      `0 0 ${gs}px ${hexToRgba(gc, 0.9)}`,
      `0 0 ${Math.round(gs * 2.2)}px ${hexToRgba(gc, 0.6)}`
    );
  }
  // shake_neon: add intense neon glow bloom to main text (matching preview behavior)
  if (animation === "shake_neon") {
    shadows.push(
      `0 0 8px ${color}`,
      `0 0 20px ${hexToRgba(color, 0.9)}`,
      `0 0 45px ${hexToRgba(color, 0.65)}`
    );
  }
  // danger_bold: add red alert glow to main text
  if (animation === "danger_bold") {
    shadows.push(
      `0 0 8px #FF0000`,
      `0 0 22px rgba(255, 0, 0, 0.85)`,
      `0 0 50px rgba(255, 0, 0, 0.5)`
    );
  }

  // Glitch effect
  const isGlitch = animation === "glitch";
  const glitchActive = isGlitch && frame % 8 < 2;
  const glitchX = Math.sin(frame * 0.7) * 4;
  const customRenderAnimations = new Set([
    "bold_slam",
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
    "news_viralin_badge",
    "news_portal_pantau",
    "news_offset_box",
    "brutalist_bracket",
    "quote_strip_tape",
  ]);

  return (
    <AbsoluteFill style={{ opacity }}>
      {/* Background overlay (only for standard centered animations without built-in card backgrounds) */}
      {!customRenderAnimations.has(animation) && bgOpacity > 0 && (
        <AbsoluteFill style={{ backgroundColor: hexToRgba(bgColor, bgOpacity) }} />
      )}

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

      {/* bold_slam animation: Yellow card with slam entrance */}
      {animation === "bold_slam" && (
        <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
          <div style={{
            transform: `${transform}`,
            background: config.boxColor || "#FFE600",
            padding: "48px 72px",
            borderRadius: 28,
            border: `10px solid ${config.strokeColor || "#16130B"}`,
            boxShadow: `14px 14px 0px ${config.strokeColor || "#16130B"}`,
          }}>
            {displayText.split("\n").map((line: string, i: number) => (
              <div key={i} style={{
                fontFamily: "'Arial Black', Impact, sans-serif",
                fontWeight: 900,
                fontSize: config.fontSize || 92,
                lineHeight: 1.15,
                color: config.color || "#16130B",
                textAlign: "center",
                textTransform: "uppercase",
                letterSpacing: 1,
              }}>
                {line}
              </div>
            ))}
          </div>
        </AbsoluteFill>
      )}

      {/* podcast_lower_third animation: podcast lower-third card with on-air badge */}
      {animation === "podcast_lower_third" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 13, stiffness: 170, mass: 0.7 } });
        const y = interpolate(Math.min(1, entrance), [0, 1], [96, 0]) + Math.sin(frame * 0.06) * 4 * motionIntensity;
        const accent = config.lineColor || "#16F2B3";
        const dotOpacity = 0.35 + Math.abs(Math.sin(frame * 0.18)) * 0.65;
        return (
          <AbsoluteFill>
            <div style={{
              position: "absolute",
              top: `${positionY}%`,
              left: "7%",
              right: "7%",
              transform: `translateY(calc(-50% + ${y}px))`,
              display: "grid",
              gridTemplateColumns: badgeEnabled ? "92px 1fr" : "1fr",
              alignItems: "center",
              gap: 22,
              padding: "30px 34px",
              borderRadius: 28,
              border: `2px solid ${accent}66`,
              borderLeft: `12px solid ${accent}`,
              background: "linear-gradient(90deg, rgba(6,17,31,0.96), rgba(16,24,39,0.82))",
              boxShadow: `0 24px 70px rgba(0,0,0,0.45), 0 0 38px ${accent}33`,
            }}>
              {badgeEnabled && <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
                <span style={{
                  width: 24,
                  height: 24,
                  borderRadius: 999,
                  backgroundColor: accent,
                  opacity: dotOpacity,
                  boxShadow: `0 0 26px ${accent}`,
                }} />
                <span style={{
                  color: accent,
                  fontFamily: "'Inter', sans-serif",
                  fontWeight: 900,
                  fontSize: 22,
                  letterSpacing: 0,
                }}>{badgeText || "ON AIR"}</span>
              </div>}
              <div style={{
                color,
                fontSize: config.fontSize || 64,
                fontWeight,
                fontFamily,
                lineHeight: 1.02,
                textAlign: "left",
                textShadow: shadows.length ? shadows.join(", ") : "0 4px 18px rgba(0,0,0,0.65)",
                textTransform: "uppercase",
              }}>{renderedText}</div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* quote_card animation: editorial pull-quote card */}
      {animation === "quote_card" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 16, stiffness: 120, mass: 0.8 } });
        const scale = 0.9 + Math.min(1, entrance) * 0.1 + Math.sin(frame * 0.055) * 0.01 * motionIntensity;
        const rotate = interpolate(frame, [0, 18], [-2.5, -0.8], { extrapolateRight: "clamp" }) + Math.sin(frame * 0.045) * 0.35 * motionIntensity;
        const y = Math.sin(frame * 0.05) * 5 * motionIntensity;
        const accent = config.lineColor || "#FF4D2D";
        return (
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
            <div style={{
              position: "relative",
              width: "78%",
              padding: "76px 72px 58px",
              borderRadius: 34,
              background: hexToRgba(config.boxColor || "#F5EFE1", config.boxOpacity ?? 0.96),
              border: "3px solid rgba(255,255,255,0.72)",
              boxShadow: "0 36px 90px rgba(0,0,0,0.42)",
              transform: `translateY(${y}px) scale(${scale}) rotate(${rotate}deg)`,
            }}>
              {decorativeElements && <div style={{
                position: "absolute",
                top: -38,
                left: 42,
                color: accent,
                fontFamily: "Georgia, serif",
                fontWeight: 900,
                fontSize: 132,
                lineHeight: 1,
              }}>"</div>}
              <div style={{
                color: config.color || "#171717",
                fontSize: config.fontSize || 58,
                fontWeight,
                fontFamily,
                lineHeight: config.lineHeight || 1.16,
                textAlign,
                textShadow: "none",
                whiteSpace: "pre-line",
              }}>{renderedText}</div>
              {decorativeElements && <div style={{
                width: "36%",
                height: 8,
                borderRadius: 999,
                margin: "34px auto 0",
                backgroundColor: accent,
              }} />}
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* waveform_pulse animation: pulsing audio waveform around hook text */}
      {animation === "waveform_pulse" && (() => {
        const waveColor = config.glowColor || config.gradientTo || color || "#14F1D9";
        const pulse = 1 + Math.sin(frame * 0.18) * 0.035 * motionIntensity;
        const bars = Array.from({ length: 17 });
        return (
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
            <div style={{ position: "absolute", top: `${positionY}%`, left: 0, right: 0, transform: `translateY(-50%) scale(${pulse})`, textAlign: "center" }}>
              {badgeEnabled && <div style={{ color: waveColor, fontFamily: "'Inter', sans-serif", fontWeight: 900, fontSize: 24, letterSpacing: 2, marginBottom: 12 }}>{badgeText || "LIVE AUDIO"}</div>}
              {decorativeElements && <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 9, height: 104, marginBottom: 20 }}>
                {bars.map((_, i) => {
                  const bar = 32 + Math.abs(Math.sin(frame * (0.12 + motionIntensity * 0.06) + i * 0.72)) * (42 + (i % 4) * 10);
                  return (
                    <span key={i} style={{
                      width: 10,
                      height: bar,
                      borderRadius: 999,
                      backgroundColor: waveColor,
                      boxShadow: `0 0 22px ${waveColor}`,
                      opacity: 0.42 + Math.abs(Math.sin(frame * 0.14 + i)) * 0.58,
                    }} />
                  );
                })}
              </div>}
              <div style={{
                display: "inline-block",
                padding: "0 54px",
                color: config.gradientEnabled ? "transparent" : color,
                background: config.gradientEnabled ? `linear-gradient(${config.gradientAngle || 180}deg, ${config.gradientFrom || "#FFF"}, ${config.gradientTo || waveColor})` : undefined,
                WebkitBackgroundClip: config.gradientEnabled ? "text" : undefined,
                fontSize,
                fontWeight,
                fontFamily,
                lineHeight: config.lineHeight || 1.12,
                textShadow: shadows.length ? shadows.join(", ") : `0 0 22px ${waveColor}`,
                textTransform: "uppercase",
              }}>{renderedText}</div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* breaking_tape animation: diagonal hot-take tape */}
      {animation === "breaking_tape" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 12, stiffness: 180, mass: 0.7 } });
        const x = interpolate(Math.min(1, entrance), [0, 1], [-260, 0]) + Math.sin(frame * 0.07) * 14 * motionIntensity;
        const tapeColor = config.boxColor || "#FFDD2D";
        return (
          <AbsoluteFill>
            <div style={{
              position: "absolute",
              top: `${positionY}%`,
              left: "-12%",
              right: "-12%",
              transform: `translateY(-50%) translateX(${x}px) rotate(-4deg)`,
              padding: "28px 80px",
              background: `linear-gradient(90deg, ${tapeColor}, #FFF06A, ${tapeColor})`,
              backgroundImage: decorativeElements ? `repeating-linear-gradient(135deg, rgba(0,0,0,0.06) 0 18px, transparent 18px 32px), linear-gradient(90deg, ${tapeColor}, #FFF06A, ${tapeColor})` : undefined,
              borderTop: "8px solid rgba(0,0,0,0.92)",
              borderBottom: "8px solid rgba(0,0,0,0.92)",
              boxShadow: "0 34px 70px rgba(0,0,0,0.42)",
              textAlign: "center",
            }}>
              {badgeEnabled && <div style={{
                color: config.lineColor || "#D71920",
                fontFamily: "'Inter', sans-serif",
                fontWeight: 900,
                fontSize: 26,
                letterSpacing: 0,
                marginBottom: 8,
              }}>{badgeText || "HOT TAKE"}</div>}
              <div style={{
                color: config.color || "#111111",
                fontSize: config.fontSize || 72,
                fontWeight,
                fontFamily,
                lineHeight: 0.98,
                textTransform: "uppercase",
                textShadow: "none",
              }}>{renderedText}</div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* mic_drop animation: falling badge with impact flash */}
      {animation === "mic_drop" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 8, stiffness: 210, mass: 0.65 } });
        const y = interpolate(Math.min(1, entrance), [0, 1], [-340, 0]) + Math.sin(frame * 0.07) * 6 * motionIntensity;
        const rotate = interpolate(frame, [0, 14], [-8, 0], { extrapolateRight: "clamp" });
        const accent = config.boxColor || config.gradientTo || "#FF4D7D";
        const impactScale = (frame > 10 && frame < 24 ? 1 + Math.sin((frame - 10) * 0.5) * 0.08 : 1) + Math.sin(frame * 0.08) * 0.012 * motionIntensity;
        return (
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
            <div style={{
              position: "absolute",
              top: `${positionY}%`,
              left: "50%",
              width: "78%",
              transform: `translate(-50%, calc(-50% + ${y}px)) rotate(${rotate}deg) scale(${impactScale})`,
              borderRadius: 999,
              border: `7px solid ${accent}`,
              background: "rgba(5,5,7,0.78)",
              boxShadow: `0 0 58px ${accent}66, inset 0 0 32px rgba(255,255,255,0.08)`,
              padding: "48px 62px",
              textAlign: "center",
            }}>
              {badgeEnabled && <div style={{
                color: accent,
                fontFamily: "'Inter', sans-serif",
                fontWeight: 900,
                fontSize: 24,
                letterSpacing: 2,
                marginBottom: 14,
              }}>{badgeText || "MIC DROP"}</div>}
              <div style={{
                color: config.gradientEnabled ? "transparent" : color,
                background: config.gradientEnabled ? `linear-gradient(${config.gradientAngle || 180}deg, ${config.gradientFrom || "#FFF"}, ${config.gradientTo || accent})` : undefined,
                WebkitBackgroundClip: config.gradientEnabled ? "text" : undefined,
                fontSize,
                fontWeight,
                fontFamily,
                lineHeight: 1.02,
                textShadow: shadows.length ? shadows.join(", ") : `0 0 26px ${accent}`,
                textTransform: "uppercase",
              }}>{renderedText}</div>
            </div>
            {decorativeElements && frame > 10 && frame < 28 && (
              <div style={{
                position: "absolute",
                top: `calc(${positionY}% + 130px)`,
                left: "50%",
                width: `${interpolate(frame, [10, 28], [120, 560], { extrapolateRight: "clamp" })}px`,
                height: 8,
                borderRadius: 999,
                backgroundColor: accent,
                opacity: interpolate(frame, [10, 28], [1, 0], { extrapolateRight: "clamp" }),
                transform: "translateX(-50%)",
                boxShadow: `0 0 30px ${accent}`,
              }} />
            )}
          </AbsoluteFill>
        );
      })()}

      {/* split_panel animation: two-tone debate panel with customizable label */}
      {animation === "split_panel" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 15, stiffness: 150, mass: 0.75 } });
        const x = interpolate(Math.min(1, entrance), [0, 1], [-180, 0]);
        const y = Math.sin(frame * 0.055) * 5 * motionIntensity;
        const accent = config.lineColor || "#38BDF8";
        return (
          <AbsoluteFill>
            <div style={{
              position: "absolute",
              top: `${positionY}%`,
              left: "8%",
              right: "8%",
              transform: `translateY(calc(-50% + ${y}px)) translateX(${x}px)`,
              display: "grid",
              gridTemplateColumns: badgeEnabled ? "118px 1fr" : "1fr",
              overflow: "hidden",
              borderRadius: 30,
              border: `2px solid ${accent}55`,
              background: hexToRgba(config.boxColor || "#0F172A", config.boxOpacity ?? 0.86),
              boxShadow: `0 30px 80px rgba(0,0,0,0.48), 0 0 34px ${accent}33`,
            }}>
              {badgeEnabled && <div style={{ display: "grid", placeItems: "center", background: accent, color: "#06111F", fontFamily: "'Inter', sans-serif", fontWeight: 900, fontSize: 24, letterSpacing: 2, textTransform: "uppercase", writingMode: "vertical-rl" }}>{badgeText || "POINT"}</div>}
              <div style={{ position: "relative", padding: "46px 54px" }}>
                {decorativeElements && <div style={{ position: "absolute", left: 54, right: 54, bottom: 28, height: 5, borderRadius: 999, background: accent, opacity: 0.8 }} />}
                <div style={{
                  color: config.gradientEnabled ? "transparent" : color,
                  background: config.gradientEnabled ? `linear-gradient(${config.gradientAngle || 180}deg, ${config.gradientFrom || "#FFF"}, ${config.gradientTo || accent})` : undefined,
                  WebkitBackgroundClip: config.gradientEnabled ? "text" : undefined,
                  fontSize,
                  fontWeight,
                  fontFamily,
                  lineHeight: config.lineHeight || 1.08,
                  textAlign: "left",
                  textShadow: shadows.length ? shadows.join(", ") : "0 5px 20px rgba(0,0,0,0.55)",
                  textTransform: config.uppercase ? "uppercase" : "none",
                }}>{renderedText}</div>
              </div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* kinetic_stack animation: stacked word cards */}
      {animation === "kinetic_stack" && (() => {
        const words = renderedText.split(/\s+/).filter(Boolean).slice(0, 7);
        const accent = config.boxColor || "#F97316";
        const stroke = config.lineColor || "#111827";
        return (
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
            <div style={{ position: "absolute", top: `${positionY}%`, left: 0, right: 0, transform: "translateY(-50%)", display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
              {words.map((word, index) => {
                const entrance = interpolate(frame, [index * 2, index * 2 + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
                const wiggle = Math.sin(frame * 0.09 + index) * 4 * motionIntensity;
                const side = index % 2 === 0 ? -1 : 1;
                return (
                  <div key={`${word}-${index}`} style={{
                    transform: `translateX(${side * (30 + index * 7) + wiggle}px) rotate(${side * (1.5 + index * 0.25)}deg) scale(${0.8 + entrance * 0.2})`,
                    opacity: entrance,
                    background: index % 2 === 0 ? accent : "#F8FAFC",
                    color: index % 2 === 0 ? (config.color || "#111827") : "#111827",
                    border: `5px solid ${stroke}`,
                    boxShadow: `10px 10px 0 ${stroke}`,
                    borderRadius: 12,
                    padding: "10px 28px",
                    fontFamily,
                    fontWeight,
                    fontSize: Math.max(42, fontSize * 0.85),
                    lineHeight: 0.95,
                    textTransform: "uppercase",
                  }}>{word}</div>
                );
              })}
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* glass_flash animation: glass panel with moving shine */}
      {animation === "glass_flash" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 18, stiffness: 120, mass: 0.9 } });
        const accent = config.lineColor || "#C084FC";
        const shine = interpolate(frame % Math.max(24, Math.round(54 / Math.max(0.25, motionIntensity))), [0, 18, 36], [-120, 20, 120], { extrapolateRight: "clamp" });
        return (
          <AbsoluteFill>
            <div style={{
              position: "absolute",
              top: `${positionY}%`,
              left: "8%",
              right: "8%",
              transform: `translateY(-50%) scale(${0.94 + Math.min(1, entrance) * 0.06})`,
              overflow: "hidden",
              borderRadius: 36,
              padding: "58px 60px",
              background: hexToRgba(config.boxColor || "#FFFFFF", config.boxOpacity ?? 0.14),
              border: `2px solid ${accent}66`,
              boxShadow: `0 30px 90px rgba(0,0,0,0.42), 0 0 48px ${accent}33`,
              backdropFilter: "blur(12px)",
            }}>
              {decorativeElements && <div style={{ position: "absolute", top: "-20%", bottom: "-20%", left: `${shine}%`, width: 110, transform: "skewX(-18deg)", background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.38), transparent)" }} />}
              {badgeEnabled && <div style={{ color: accent, fontFamily: "'Inter', sans-serif", fontWeight: 900, fontSize: 24, letterSpacing: 3, marginBottom: 18 }}>{badgeText || "FOCUS"}</div>}
              <div style={{
                color: config.gradientEnabled ? "transparent" : color,
                background: config.gradientEnabled ? `linear-gradient(${config.gradientAngle || 180}deg, ${config.gradientFrom || "#FFF"}, ${config.gradientTo || accent})` : undefined,
                WebkitBackgroundClip: config.gradientEnabled ? "text" : undefined,
                fontSize,
                fontWeight,
                fontFamily,
                lineHeight: config.lineHeight || 1.12,
                textAlign,
                textShadow: shadows.length ? shadows.join(", ") : `0 0 24px ${accent}55`,
              }}>{renderedText}</div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* marker_swipe animation: marker stroke behind text */}
      {animation === "marker_swipe" && (() => {
        const accent = config.boxColor || config.lineColor || "#FDE047";
        const sweep = interpolate(frame, [0, 14], [0, 1], { extrapolateRight: "clamp" });
        const bob = Math.sin(frame * 0.08) * 4 * motionIntensity;
        return (
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
            <div style={{ position: "absolute", top: `${positionY}%`, left: "7%", right: "7%", transform: `translateY(calc(-50% + ${bob}px))`, textAlign }}>
              <div style={{ position: "relative", display: "inline-block", padding: "12px 24px" }}>
                {decorativeElements && <div style={{ position: "absolute", left: 0, right: 0, top: "46%", height: "46%", transform: `translateY(-50%) scaleX(${sweep}) rotate(-1deg)`, transformOrigin: "left center", borderRadius: 14, background: hexToRgba(accent, config.boxOpacity ?? 0.86) }} />}
                {badgeEnabled && <div style={{ position: "relative", color: accent, fontFamily: "'Inter', sans-serif", fontWeight: 900, fontSize: 22, letterSpacing: 2, marginBottom: 10 }}>{badgeText || "MARKED"}</div>}
                <div style={{
                  position: "relative",
                  color,
                  fontSize,
                  fontWeight,
                  fontFamily,
                  lineHeight: config.lineHeight || 1.02,
                  textShadow: shadows.length ? shadows.join(", ") : "0 6px 18px rgba(0,0,0,0.5)",
                  textTransform: config.uppercase ? "uppercase" : "none",
                }}>{renderedText}</div>
              </div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* signal_scan animation: digital scanline panel */}
      {animation === "signal_scan" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 14, stiffness: 160, mass: 0.8 } });
        const accent = config.lineColor || "#22D3EE";
        const scan = interpolate(frame % Math.max(18, Math.round(42 / Math.max(0.25, motionIntensity))), [0, 21, 42], [-110, 15, 125], { extrapolateRight: "clamp" });
        return (
          <AbsoluteFill>
            <div style={{
              position: "absolute",
              top: `${positionY}%`,
              left: "8%",
              right: "8%",
              transform: `translateY(-50%) scale(${0.96 + Math.min(1, entrance) * 0.04})`,
              overflow: "hidden",
              padding: "46px 54px",
              borderRadius: 22,
              border: `2px solid ${accent}66`,
              background: hexToRgba(config.boxColor || "#0EA5E9", config.boxOpacity ?? 0.16),
              boxShadow: `0 0 42px ${accent}33, 0 24px 70px rgba(0,0,0,0.45)`,
            }}>
              {decorativeElements && <div style={{ position: "absolute", top: 0, bottom: 0, left: `${scan}%`, width: 90, background: `linear-gradient(90deg, transparent, ${accent}66, transparent)` }} />}
              {badgeEnabled && <div style={{ color: accent, fontFamily: "'Titillium Web', sans-serif", fontWeight: 900, fontSize: 24, letterSpacing: 3, marginBottom: 14 }}>{badgeText || "SIGNAL"}</div>}
              <div style={{
                color: config.gradientEnabled ? "transparent" : color,
                background: config.gradientEnabled ? `linear-gradient(${config.gradientAngle || 180}deg, ${config.gradientFrom || "#FFF"}, ${config.gradientTo || accent})` : undefined,
                WebkitBackgroundClip: config.gradientEnabled ? "text" : undefined,
                fontSize,
                fontWeight,
                fontFamily,
                lineHeight: config.lineHeight || 1.08,
                textAlign,
                textShadow: shadows.length ? shadows.join(", ") : `0 0 18px ${accent}`,
                textTransform: config.uppercase ? "uppercase" : "none",
              }}>{renderedText}</div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* TikTok-native reply bubble */}
      {animation === "comment_reply" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 16, stiffness: 150, mass: 0.75 } });
        const y = interpolate(Math.min(1, entrance), [0, 1], [-80, 0]);
        const panel = config.boxColor || "#FFFFFF";
        const accent = config.lineColor || "#18181B";
        return (
          <AbsoluteFill>
            <div style={{ position: "absolute", top: `${positionY}%`, left: "7%", right: "13%", transform: `translateY(calc(-50% + ${y}px))` }}>
              <div style={{ position: "relative", borderRadius: 28, padding: "34px 38px", background: hexToRgba(panel, config.boxOpacity ?? 0.98), boxShadow: "0 30px 72px rgba(0,0,0,.38)" }}>
                {badgeEnabled && <div style={{ color: hexToRgba(accent, 0.58), fontFamily: "'Inter', sans-serif", fontSize: 22, fontWeight: 700, marginBottom: 14 }}>{badgeText || "replying to @viewer"}</div>}
                <div style={{ color: config.color || "#18181B", fontFamily, fontSize, fontWeight, lineHeight: config.lineHeight || 1.14, textAlign: "left" }}>{renderedText}</div>
                {decorativeElements && <div style={{ position: "absolute", left: 54, bottom: -20, width: 42, height: 42, background: panel, transform: "rotate(45deg)", borderRadius: 4 }} />}
              </div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* TikTok discovery/search prompt */}
      {animation === "search_prompt" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 18, stiffness: 130, mass: 0.8 } });
        const accent = config.lineColor || "#22D3EE";
        return (
          <AbsoluteFill>
            <div style={{ position: "absolute", top: `${positionY}%`, left: "6%", right: "6%", transform: `translateY(-50%) scale(${0.94 + Math.min(1, entrance) * 0.06})`, display: "grid", gridTemplateColumns: "68px 1fr 58px", alignItems: "center", gap: 18, padding: "26px 32px", borderRadius: 999, background: hexToRgba(config.boxColor || "#0F172A", config.boxOpacity ?? 0.94), border: `2px solid ${accent}66`, boxShadow: `0 0 42px ${accent}22, 0 28px 64px rgba(0,0,0,.4)` }}>
              <span style={{ color: accent, fontSize: 48, lineHeight: 1 }}>⌕</span>
              <div style={{ color, fontFamily, fontSize, fontWeight, lineHeight: config.lineHeight || 1.12, textAlign: "left", textShadow: shadows.join(", ") || undefined }}>{renderedText}</div>
              <span style={{ color: accent, fontSize: 38 }}>↗</span>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* Numbered listicle/countdown hook */}
      {animation === "countdown_list" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 11, stiffness: 190, mass: 0.7 } });
        const accent = config.boxColor || "#FACC15";
        const ink = config.lineColor || "#111827";
        return (
          <AbsoluteFill>
            <div style={{ position: "absolute", top: `${positionY}%`, left: "7%", right: "7%", transform: `translateY(-50%) scale(${Math.min(1, entrance)})`, display: "grid", gridTemplateColumns: badgeEnabled ? "220px 1fr" : "1fr", overflow: "hidden", borderRadius: 26, border: `8px solid ${ink}`, boxShadow: `16px 16px 0 ${ink}` }}>
              {badgeEnabled && <div style={{ display: "grid", placeItems: "center", background: accent, color: ink, fontFamily: "'Archivo Black', sans-serif", fontSize: 104, fontWeight: 900 }}>{badgeText || "03"}</div>}
              <div style={{ color: config.color || ink, background: "#F8FAFC", padding: "48px 44px", fontFamily, fontSize, fontWeight, lineHeight: 1.04, textTransform: "uppercase", textAlign: "left" }}>{renderedText}</div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* Persistent creator point-of-view stamp */}
      {animation === "pov_stamp" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 14, stiffness: 155, mass: 0.8 } });
        const accent = config.boxColor || "#FB7185";
        const rotate = interpolate(frame, [0, 16], [-8, -2], { extrapolateRight: "clamp" });
        return (
          <AbsoluteFill>
            <div style={{ position: "absolute", top: `${positionY}%`, left: "8%", right: "8%", transform: `translateY(-50%) rotate(${rotate}deg) scale(${0.88 + Math.min(1, entrance) * 0.12})` }}>
              {badgeEnabled && <div style={{ display: "inline-block", marginBottom: 14, padding: "12px 24px", borderRadius: 12, background: accent, color: "#FFFFFF", fontFamily: "'Inter', sans-serif", fontSize: 30, fontWeight: 900, letterSpacing: 3 }}>{badgeText || "POV"}</div>}
              <div style={{ padding: "34px 40px", borderRadius: 18, border: `5px solid ${accent}`, background: "rgba(18,7,12,.8)", color, fontFamily, fontSize, fontWeight, fontStyle: config.italic ? "italic" : "normal", lineHeight: config.lineHeight || 1.08, textAlign: "left", textShadow: shadows.join(", ") || "0 6px 22px rgba(0,0,0,.5)" }}>{renderedText}</div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* 1. news_viralin_badge: Yellow card with tilted #VIRALIN blue badge and layered paper sheet */}
      {animation === "news_viralin_badge" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 12, stiffness: 170, mass: 0.75 } });
        const y = interpolate(Math.min(1, entrance), [0, 1], [-120, 0]);
        const scaleVal = interpolate(Math.min(1, entrance), [0, 1], [0.88, 1]);
        const cardBg = config.boxColor || "#EAB308"; // Akurat yellow
        const badgeBg = config.lineColor || "#1D4ED8"; // Royal blue
        const textColor = config.color || "#09090B";
        const badgeTitle = badgeText || "#VIRALIN";
        const badgeSub = (config as any).badgeSubText || "";

        return (
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
            <div style={{
              position: "absolute",
              top: `${positionY}%`,
              left: "6%",
              right: "6%",
              transform: `translateY(calc(-50% + ${y}px)) scale(${scaleVal})`,
            }}>
              {/* White paper background layer tilted underneath */}
              <div style={{
                position: "absolute",
                inset: -6,
                background: "#FFFFFF",
                transform: "rotate(-3deg)",
                borderRadius: 12,
                boxShadow: "0 24px 55px rgba(0,0,0,0.5)",
                zIndex: 1,
              }} />

              {/* Main Yellow Card */}
              <div style={{
                position: "relative",
                background: cardBg,
                padding: "54px 44px 40px 44px",
                borderRadius: 12,
                boxShadow: "0 28px 65px rgba(0,0,0,0.6)",
                zIndex: 2,
              }}>
                {/* Tilted Blue Badge Header */}
                {badgeEnabled && (
                  <div style={{
                    position: "absolute",
                    top: -36,
                    left: "50%",
                    transform: "translateX(-50%) rotate(-3.5deg)",
                    background: badgeBg,
                    borderRadius: 8,
                    padding: "10px 28px",
                    boxShadow: "0 12px 28px rgba(0,0,0,0.45), inset 0 0 12px rgba(255,255,255,0.2)",
                    border: "2px solid rgba(255,255,255,0.25)",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    zIndex: 3,
                  }}>
                    <div style={{
                      color: "#FACC15",
                      fontFamily: "'Montserrat', 'Barlow Condensed', sans-serif",
                      fontWeight: 900,
                      fontSize: 30,
                      fontStyle: "italic",
                      letterSpacing: "0.05em",
                      lineHeight: 1.1,
                      textTransform: "uppercase",
                      textShadow: "0 2px 4px rgba(0,0,0,0.4)",
                    }}>
                      {badgeTitle}
                    </div>
                    {badgeSub ? (
                      <div style={{
                        color: "#FFFFFF",
                        fontFamily: "'Inter', sans-serif",
                        fontWeight: 700,
                        fontSize: 14,
                        letterSpacing: "0.02em",
                        marginTop: 3,
                        opacity: 0.95,
                      }}>
                        {badgeSub}
                      </div>
                    ) : null}
                  </div>
                )}

                {/* Main Headline Text */}
                <div style={{
                  color: textColor,
                  fontFamily: fontFamily || "'Montserrat', 'Inter', sans-serif",
                  fontSize: config.fontSize || 56,
                  fontWeight: 900,
                  lineHeight: 1.22,
                  textAlign: "center",
                  textShadow: "0 1px 2px rgba(0,0,0,0.1)",
                  marginTop: badgeEnabled ? 8 : 0,
                }}>
                  {renderedText}
                </div>
              </div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* 2. news_portal_pantau: Clean white news card with red category pill and speech bubble notch */}
      {animation === "news_portal_pantau" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 14, stiffness: 180, mass: 0.7 } });
        const y = interpolate(Math.min(1, entrance), [0, 1], [-100, 0]);
        const scaleVal = interpolate(Math.min(1, entrance), [0, 1], [0.9, 1]);
        const cardBg = config.boxColor || "#FFFFFF";
        const accentColor = config.lineColor || "#DC2626"; // Crimson Red
        const categoryTag = badgeText || "INTERNASIONAL";
        const footerLabel = (config as any).footerText || (config as any).badgeSubText || "READ MORE AT chatgpt.com";

        return (
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
            <div style={{
              position: "absolute",
              top: `${positionY}%`,
              left: "6%",
              right: "6%",
              transform: `translateY(calc(-50% + ${y}px)) scale(${scaleVal})`,
            }}>
              <div style={{
                position: "relative",
                background: cardBg,
                borderRadius: "16px 16px 0 0",
                padding: "40px 44px 34px 44px",
                boxShadow: "0 32px 75px rgba(0,0,0,0.55)",
                borderBottom: `6px solid ${accentColor}`,
              }}>
                {/* Category Pill Tag */}
                {badgeEnabled && (
                  <div style={{
                    display: "inline-block",
                    background: accentColor,
                    color: "#FFFFFF",
                    fontFamily: "'Inter', 'Montserrat', sans-serif",
                    fontWeight: 900,
                    fontSize: 22,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    padding: "6px 16px",
                    borderRadius: 4,
                    marginBottom: 16,
                    boxShadow: `0 4px 14px ${accentColor}66`,
                  }}>
                    {categoryTag}
                  </div>
                )}

                {/* Main News Headline */}
                <div style={{
                  color: config.color || "#09090B",
                  fontFamily: fontFamily || "'Montserrat', 'Inter', sans-serif",
                  fontSize: config.fontSize || 56,
                  fontWeight: 900,
                  lineHeight: 1.18,
                  textAlign: "left",
                  textTransform: "uppercase",
                  letterSpacing: "-0.01em",
                }}>
                  {renderedText}
                </div>

                {/* Footer Brand Bar */}
                <div style={{
                  marginTop: 22,
                  paddingTop: 14,
                  borderTop: "1px solid rgba(0,0,0,0.08)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}>
                  <div style={{
                    color: "#52525B",
                    fontFamily: "'Inter', sans-serif",
                    fontWeight: 800,
                    fontSize: 16,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                  }}>
                    {footerLabel}
                  </div>
                </div>

                {/* Bottom Speech Notch Pointer */}
                <div style={{
                  position: "absolute",
                  bottom: -22,
                  right: 48,
                  width: 0,
                  height: 0,
                  borderLeft: "16px solid transparent",
                  borderRight: "16px solid transparent",
                  borderTop: `22px solid ${accentColor}`,
                  filter: "drop-shadow(0 4px 6px rgba(0,0,0,0.3))",
                }} />
              </div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* 3. news_offset_box: Detik-detik red breaking box with white offset border frame */}
      {animation === "news_offset_box" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 11, stiffness: 190, mass: 0.7 } });
        const y = interpolate(Math.min(1, entrance), [0, 1], [-80, 0]);
        const scaleVal = interpolate(Math.min(1, entrance), [0, 1], [0.92, 1]);
        const cardBg = config.boxColor || "#DC2626"; // Crimson Red
        const offsetColor = config.lineColor || "#FFFFFF";

        return (
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
            <div style={{
              position: "absolute",
              top: `${positionY}%`,
              left: "8%",
              right: "8%",
              transform: `translateY(calc(-50% + ${y}px)) scale(${scaleVal})`,
            }}>
              {/* White offset rectangular frame sticking out behind top-left */}
              <div style={{
                position: "absolute",
                top: -16,
                left: -16,
                width: "65%",
                height: "80%",
                borderTop: `6px solid ${offsetColor}`,
                borderLeft: `6px solid ${offsetColor}`,
                zIndex: 1,
                boxShadow: "0 12px 32px rgba(0,0,0,0.3)",
              }} />

              {/* Main Red Box */}
              <div style={{
                position: "relative",
                background: cardBg,
                padding: "42px 46px",
                boxShadow: "0 28px 65px rgba(0,0,0,0.6)",
                zIndex: 2,
              }}>
                <div style={{
                  color: config.color || "#FFFFFF",
                  fontFamily: fontFamily || "'Montserrat', 'Inter', sans-serif",
                  fontSize: config.fontSize || 58,
                  fontWeight: 900,
                  lineHeight: 1.24,
                  textAlign: "center",
                  textShadow: "0 2px 8px rgba(0,0,0,0.4)",
                }}>
                  {renderedText}
                </div>
              </div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* 4. brutalist_bracket: White box with industrial thick black L-bracket and red exclamation marks */}
      {animation === "brutalist_bracket" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 13, stiffness: 180, mass: 0.75 } });
        const x = interpolate(Math.min(1, entrance), [0, 1], [-90, 0]);
        const scaleVal = interpolate(Math.min(1, entrance), [0, 1], [0.92, 1]);
        const cardBg = config.boxColor || "#FFFFFF";
        const bracketColor = config.lineColor || "#000000";
        const accentColor = "#EF4444";

        return (
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
            <div style={{
              position: "absolute",
              top: `${positionY}%`,
              left: "8%",
              right: "8%",
              transform: `translateY(-50%) translateX(${x}px) scale(${scaleVal})`,
            }}>
              {/* Outer Thick Black L-Bracket */}
              <div style={{
                position: "absolute",
                top: -18,
                left: -18,
                bottom: -18,
                width: 48,
                borderTop: `8px solid ${bracketColor}`,
                borderLeft: `8px solid ${bracketColor}`,
                borderBottom: `8px solid ${bracketColor}`,
                zIndex: 1,
              }} />

              {/* Main White Card */}
              <div style={{
                position: "relative",
                background: cardBg,
                padding: "42px 46px",
                boxShadow: "0 28px 65px rgba(0,0,0,0.55)",
                zIndex: 2,
              }}>
                <div style={{
                  color: config.color || "#09090B",
                  fontFamily: fontFamily || "'Montserrat', 'Inter', sans-serif",
                  fontSize: config.fontSize || 58,
                  fontWeight: 900,
                  lineHeight: 1.2,
                  textAlign: "left",
                }}>
                  {renderedText.split(/(!!+|!\s*!)/g).map((part, idx) => {
                    if (part.includes("!")) {
                      return <span key={idx} style={{ color: accentColor, fontWeight: 900 }}> {part}</span>;
                    }
                    return <span key={idx}>{part}</span>;
                  })}
                </div>
              </div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* 5. quote_strip_tape: Multi-line white tape bars with teal quote icon badge */}
      {animation === "quote_strip_tape" && (() => {
        const entrance = spring({ frame, fps, config: { damping: 14, stiffness: 160, mass: 0.8 } });
        const x = interpolate(Math.min(1, entrance), [0, 1], [-100, 0]);
        const quoteBg = config.lineColor || "#0D9488"; // Teal quote badge
        const tapeBg = config.boxColor || "#FFFFFF";
        const textColor = config.color || "#09090B";

        const words = renderedText.split(/\s+/).filter(Boolean);
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
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
            <div style={{
              position: "absolute",
              top: `${positionY}%`,
              left: "8%",
              right: "8%",
              transform: `translateY(-50%) translateX(${x}px)`,
              display: "flex",
              flexDirection: "column",
              alignItems: "flex-start",
            }}>
              {/* Teal Quotation Mark Badge Box */}
              <div style={{
                background: quoteBg,
                color: "#FFFFFF",
                borderRadius: 6,
                padding: "10px 16px",
                marginBottom: 12,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: `0 8px 22px ${quoteBg}66`,
              }}>
                <span style={{ fontSize: 28, fontWeight: 900, lineHeight: 1, fontFamily: "serif" }}>❝</span>
              </div>

              {/* Individual Tape Strips per Line */}
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 10 }}>
                {lines.map((line, lIdx) => {
                  const lineEntrance = interpolate(frame, [lIdx * 3, lIdx * 3 + 12], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
                  return (
                    <div
                      key={lIdx}
                      style={{
                        background: tapeBg,
                        color: textColor,
                        padding: "12px 24px",
                        fontFamily: fontFamily || "'Montserrat', 'Inter', sans-serif",
                        fontSize: config.fontSize || 52,
                        fontWeight: 900,
                        textTransform: "uppercase",
                        letterSpacing: "0.04em",
                        lineHeight: 1.15,
                        boxShadow: "0 12px 30px rgba(0,0,0,0.5)",
                        transform: `scale(${0.88 + lineEntrance * 0.12})`,
                        opacity: lineEntrance,
                        transformOrigin: "left center",
                      }}
                    >
                      {line}
                    </div>
                  );
                })}
              </div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* Main text (skipped for custom card/layer renders) */}
      {!customRenderAnimations.has(animation) && (
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
            {renderedText}
            {animation === "typewriter" && frame % 16 < 10 && <span style={{ opacity: 0.7 }}>|</span>}
          </span>
        </div>
      )}

      {/* Accent line */}
      {config.lineEnabled && <AccentLine config={config} text={renderedText} positionY={positionY} />}
    </AbsoluteFill>
  );
};

function AccentLine({ config, text, positionY }: { config: HookConfig; text: string; positionY: number }) {
  const pos = config.linePosition || "bottom";
  const style: React.CSSProperties = {
    position: "absolute",
    backgroundColor: config.lineColor || "#FFCC00",
  };

  const offset = config.lineOffset || 12;
  const thickness = config.lineThickness || 4;
  const textLen = text.replace(/\s+/g, "").length || 12;
  const autoWidth = `${Math.min(Math.max(textLen * 2.2, 20), 72)}%`;
  const autoHeight = `${Math.min(Math.max(textLen * 1.45, 16), 54)}%`;
  const width = config.lineAutoWidth ? autoWidth : `${config.lineWidth || 60}%`;
  const height = config.lineAutoWidth ? autoHeight : `${config.lineWidth || 60}%`;

  if (pos === "top") Object.assign(style, { top: offset, left: "50%", transform: "translateX(-50%)", width, height: thickness });
  if (pos === "bottom") Object.assign(style, { bottom: offset, left: "50%", transform: "translateX(-50%)", width, height: thickness });
  if (pos === "left") Object.assign(style, { left: offset, top: "50%", transform: "translateY(-50%)", height, width: thickness });
  if (pos === "right") Object.assign(style, { right: offset, top: "50%", transform: "translateY(-50%)", height, width: thickness });
  if (pos === "center-h") Object.assign(style, { top: `calc(50% + ${offset}px)`, left: "50%", transform: "translate(-50%, -50%)", width, height: thickness });
  if (pos === "center-v") Object.assign(style, { top: "50%", left: `calc(50% + ${offset}px)`, transform: "translate(-50%, -50%)", height, width: thickness });
  if (pos === "auto-bottom") Object.assign(style, { top: `calc(${positionY}% + ${offset + 56}px)`, left: "50%", transform: "translateX(-50%)", width, height: thickness });

  return <div style={style} />;
}
