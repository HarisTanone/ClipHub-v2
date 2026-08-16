import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { TextEmphasisEvent, TextEmphasisStyleConfig } from "../types";

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

/** Map old effect names so baked jobs / presets keep rendering. */
const LEGACY_EFFECT: Record<string, string> = {
  behind_person: "depth_cutout",
  spotlight: "hero_punch",
  side_label: "side_rail",
  floating_text: "float_track",
  auto_avoid: "smart_gap",
  around_head: "orbit_halo",
  depth_text: "z_parallax",
  kinetic_type: "word_cascade",
};

const LEGACY_ANIM: Record<string, string> = {
  cinematic: "rise",
  slam: "impact",
  reveal: "slide",
  glitch: "static_glitch",
  neon: "glow",
};

const resolveEffect = (raw?: string) => {
  const name = String(raw || "hero_punch");
  return LEGACY_EFFECT[name] || name;
};

const resolveAnim = (raw?: string) => {
  const name = String(raw || "impact");
  return LEGACY_ANIM[name] || name;
};

export const isFrameInTextEmphasis = (
  frame: number,
  fps: number,
  events: TextEmphasisEvent[] | undefined,
): boolean => (events || []).slice(0, 2).some((event) => {
  const start = Math.round(Number(event.start || 0) * fps);
  const end = Math.round(Number(event.end || 0) * fps);
  return frame >= start && frame < end;
});

export const HideDuringTextEmphasis: React.FC<{
  events?: TextEmphasisEvent[];
  children: React.ReactNode;
}> = ({ events, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return isFrameInTextEmphasis(frame, fps, events) ? null : <>{children}</>;
};

const buildEnterTransform = (
  animation: string,
  enter: number,
  glitchOffset: number,
): string => {
  switch (animation) {
    case "impact":
      return `scale(${interpolate(enter, [0, 1], [1.55, 1])}) rotate(${interpolate(enter, [0, 1], [-4, 0])}deg)`;
    case "slide":
      return `translateY(${interpolate(enter, [0, 1], [56, 0])}px)`;
    case "static_glitch":
      return `translateX(${glitchOffset}px) translateY(${interpolate(enter, [0, 1], [12, 0])}px)`;
    case "glow":
      return `scale(${interpolate(enter, [0, 1], [0.9, 1])})`;
    case "elastic":
      return `scale(${interpolate(enter, [0, 0.55, 1], [0.55, 1.12, 1])})`;
    case "blur_in":
      return `scale(${interpolate(enter, [0, 1], [1.08, 1])}) translateY(${interpolate(enter, [0, 1], [8, 0])}px)`;
    case "flip_y":
      return `perspective(600px) rotateX(${interpolate(enter, [0, 1], [75, 0])}deg)`;
    case "rise":
    default:
      return `scale(${interpolate(enter, [0, 1], [0.86, 1])}) translateY(${interpolate(enter, [0, 1], [22, 0])}px)`;
  }
};

export const AITextLayer: React.FC<{
  events?: TextEmphasisEvent[];
  style?: TextEmphasisStyleConfig;
}> = ({ events = [], style = {} }) => {
  const frame = useCurrentFrame();
  const { fps, width: compositionWidth, height: compositionHeight } = useVideoConfig();
  const active = events.slice(0, 2).find((event) => {
    const start = Math.round(Number(event.start || 0) * fps);
    const end = Math.round(Number(event.end || 0) * fps);
    return frame >= start && frame < end;
  });
  if (!active) return null;

  const startFrame = Math.round(active.start * fps);
  const endFrame = Math.max(startFrame + 1, Math.round(active.end * fps));
  const localFrame = frame - startFrame;
  const eventDuration = endFrame - startFrame;
  const enter = spring({ frame: localFrame, fps, config: { damping: 12, stiffness: 190, mass: 0.7 } });
  const exitOpacity = interpolate(localFrame, [Math.max(0, eventDuration - 8), eventDuration], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const animation = resolveAnim(style.animation);
  const glitchOffset = animation === "static_glitch" ? interpolate(enter, [0, 0.3, 0.6, 1], [-8, 5, -4, 0]) : 0;
  const neonGlow = animation === "glow" ? interpolate(enter, [0, 1], [6, 34]) : 0;
  const blurPx = animation === "blur_in" ? interpolate(enter, [0, 1], [10, 0]) : 0;
  const transform = buildEnterTransform(animation, enter, glitchOffset);

  const effect = resolveEffect(active.effect);
  const position = active.position || (effect === "side_rail" ? "left" : "center");
  const positionY = clamp(Number(style.positionY ?? 48), 12, 88);
  const textAlign = position === "left" ? "left" : position === "right" ? "right" : "center";
  const alignItems = position === "left" ? "flex-start" : position === "right" ? "flex-end" : "center";
  const needsForeground = effect === "depth_cutout" || effect === "z_parallax" || effect === "orbit_halo" || effect === "smart_gap" || effect === "float_track";
  const foreground = needsForeground
    ? active.foreground_frames?.find((item) => item.frame === frame)
    : undefined;

  const sourceWidth = Number(active.source_width || compositionWidth);
  const sourceHeight = Number(active.source_height || compositionHeight);
  const coverScale = Math.max(compositionWidth / sourceWidth, compositionHeight / sourceHeight);
  const coverOffsetX = (compositionWidth - sourceWidth * coverScale) / 2;
  const coverOffsetY = (compositionHeight - sourceHeight * coverScale) / 2;
  const accent = style.accentColor || "#FF3B5C";
  const color = style.color || "#FFFFFF";
  const text = active.text || "";

  // Floating bob
  const floatSpeed = clamp(Number(style.floatSpeed ?? 1.15), 0.5, 3.0);
  const floatOffset = effect === "float_track" && foreground
    ? Math.sin(localFrame / fps * floatSpeed * Math.PI * 2) * 14 : 0;

  // Smart gap: largest empty band
  let avoidPositionY = positionY;
  let avoidAlign: "flex-start" | "center" | "flex-end" = alignItems;
  if (effect === "smart_gap" && foreground) {
    const personCenterY = (foreground.y + foreground.height / 2) * coverScale + coverOffsetY;
    const personCenterX = (foreground.x + foreground.width / 2) * coverScale + coverOffsetX;
    if (personCenterY < compositionHeight * 0.5) { avoidPositionY = 78; } else { avoidPositionY = 22; }
    if (personCenterX < compositionWidth * 0.5) { avoidAlign = "flex-end"; } else { avoidAlign = "flex-start"; }
  }

  // Orbit halo around head
  const headRadius = clamp(Number(style.aroundHeadRadius ?? 58), 30, 120) / 100;
  let aroundTop = `${positionY}%`;
  let aroundLeft = "50%";
  let aroundTransform = `translateY(-50%) ${transform}`;
  if (effect === "orbit_halo" && foreground && foreground.head_x !== undefined && foreground.head_y !== undefined) {
    const headCx = (foreground.head_x + (foreground.head_width || 0) / 2) * coverScale + coverOffsetX;
    const headCy = (foreground.head_y + (foreground.head_height || 0) / 2) * coverScale + coverOffsetY;
    const angle = (localFrame / fps) * 0.85;
    const orbitRadius = (foreground.head_width || 100) * coverScale * headRadius;
    aroundLeft = `${headCx + Math.cos(angle) * orbitRadius}px`;
    aroundTop = `${headCy + Math.sin(angle) * orbitRadius * 0.55}px`;
    aroundTransform = `translate(-50%, -50%) ${transform}`;
  }

  // Z parallax depth
  const depthIntensity = clamp(Number(style.depthIntensity ?? 0.55), 0.1, 1.0);
  const depthParallax = clamp(Number(style.depthParallax ?? 0.4), 0.05, 1.0);
  const depthFadeSec = clamp(Number(style.depthFade ?? 0.4), 0.1, 1.5);
  const depthFadeFrames = Math.max(1, Math.round(depthFadeSec * fps));
  let depthScale = 1;
  if (effect === "z_parallax" && foreground && foreground.depth_z !== undefined) {
    depthScale = 0.68 + foreground.depth_z * depthIntensity * (1 + depthParallax);
  }
  const depthEnter = effect === "z_parallax"
    ? interpolate(localFrame, [0, depthFadeFrames], [0, 1], { extrapolateRight: "clamp" })
    : enter;
  const depthExitOpacity = effect === "z_parallax"
    ? interpolate(localFrame, [Math.max(0, eventDuration - depthFadeFrames), eventDuration], [1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : exitOpacity;

  // Word cascade
  const kineticStagger = Math.max(1, Math.round(Number(style.kineticStagger ?? 5)));
  const kineticWords = effect === "word_cascade" ? text.split(" ") : [];
  const kineticProgress = (idx: number) => {
    if (localFrame < idx * kineticStagger) return 0;
    if (localFrame > idx * kineticStagger + 10) return 1;
    return (localFrame - idx * kineticStagger) / 10;
  };

  // Type pulse — reveal characters
  const typeSpeed = clamp(Number(style.typeSpeed ?? 1.4), 0.5, 3.0);
  const typeChars = effect === "type_pulse"
    ? Math.min(text.length, Math.floor(localFrame * typeSpeed * 1.6) + 1)
    : text.length;
  const typePulse = effect === "type_pulse"
    ? 0.85 + 0.15 * Math.sin(localFrame / fps * Math.PI * 4)
    : 1;

  // Sticker pop angle
  const stickerAngle = clamp(Number(style.stickerAngle ?? -6), -18, 18);
  const stickerEnter = effect === "sticker_pop"
    ? spring({ frame: localFrame, fps, config: { damping: 11, stiffness: 260, mass: 0.55 } })
    : enter;

  // Mirror echo offset
  const echoOffset = clamp(Number(style.echoOffset ?? 10), 4, 28);
  const echoOpacity = effect === "mirror_echo"
    ? interpolate(enter, [0, 1], [0, 0.45])
    : 0;

  // Split impact dual color
  const mid = Math.ceil(text.length / 2);
  const splitLeft = effect === "split_impact" ? text.slice(0, mid) : "";
  const splitRight = effect === "split_impact" ? text.slice(mid) : "";

  const effectivePositionY = effect === "smart_gap" ? avoidPositionY : positionY;
  const effectiveAlignItems = effect === "smart_gap" ? avoidAlign : alignItems;
  const effectiveTop = effect === "orbit_halo" ? aroundTop : `${effectivePositionY}%`;

  let effectiveTransform = transform;
  if (effect === "orbit_halo") effectiveTransform = aroundTransform;
  else if (effect === "z_parallax") effectiveTransform = `${transform} scale(${depthScale})`;
  else if (effect === "float_track") effectiveTransform = `${transform} translateY(${floatOffset}px)`;
  else if (effect === "sticker_pop") {
    effectiveTransform = `scale(${interpolate(stickerEnter, [0, 1], [0.4, 1])}) rotate(${interpolate(stickerEnter, [0, 1], [stickerAngle - 12, stickerAngle])}deg)`;
  } else if (effect === "type_pulse") {
    effectiveTransform = `${transform} scale(${typePulse})`;
  } else if (effect === "split_impact") {
    effectiveTransform = `scale(${interpolate(enter, [0, 1], [1.35, 1])})`;
  }

  // 2-frame Chromatic Aberration burst during impact entrance
  const isImpactBurst = localFrame <= 3 && (animation === "impact" || animation === "static_glitch");
  const chromaticTextShadow = isImpactBurst
    ? `-4px 0 rgba(255, 0, 80, 0.85), 4px 0 rgba(0, 240, 255, 0.85), 0 10px 30px rgba(0,0,0,0.85)`
    : undefined;

  const baseTextStyle: React.CSSProperties = {
    color,
    fontFamily: `'${style.fontFamily || "Bebas Neue"}', sans-serif`,
    fontSize: clamp(Number(style.fontSize ?? 104), 32, 160),
    fontWeight: Number(style.fontWeight || 900),
    letterSpacing: Number(style.letterSpacing ?? 2),
    lineHeight: Number(style.lineHeight ?? 0.9),
    textTransform: style.uppercase === false ? "none" : "uppercase",
    overflowWrap: "anywhere",
    paintOrder: style.strokeEnabled === false ? undefined : "stroke",
    WebkitTextStroke: style.strokeEnabled === false
      ? undefined
      : `${Number(style.strokeWidth ?? 3)}px ${style.strokeColor || "#0A0A0B"}`,
    textShadow: chromaticTextShadow
      || (animation === "glow"
        ? `0 0 ${neonGlow}px ${accent}, 0 0 ${neonGlow * 2}px ${accent}, 0 6px ${Number(style.shadowBlur ?? 28)}px ${style.shadowColor || "#000000"}`
        : style.shadowEnabled === false
          ? undefined
          : `0 10px ${Number(style.shadowBlur ?? 28)}px ${style.shadowColor || "#000000"}`),
    filter: blurPx > 0.2 ? `blur(${blurPx}px)` : undefined,
  };

  const renderBody = () => {
    if (effect === "word_cascade") {
      return (
        <span>
          {kineticWords.map((word, idx) => {
            const p = kineticProgress(idx);
            return (
              <span key={idx} style={{
                display: "inline-block",
                opacity: p,
                transform: `translateY(${(1 - p) * 28}px) scale(${0.75 + p * 0.25})`,
                marginRight: "0.22em",
              }}>
                {word}
              </span>
            );
          })}
        </span>
      );
    }
    if (effect === "type_pulse") {
      return (
        <span>
          {text.slice(0, typeChars)}
          <span style={{ opacity: localFrame % 10 < 6 ? 1 : 0, color: accent }}>|</span>
        </span>
      );
    }
    if (effect === "split_impact") {
      return (
        <span style={{ display: "inline-flex", alignItems: "baseline", gap: 0 }}>
          <span style={{
            color,
            transform: `translateX(${interpolate(enter, [0, 1], [-40, 0])}px)`,
            display: "inline-block",
          }}>{splitLeft}</span>
          <span style={{
            color: accent,
            transform: `translateX(${interpolate(enter, [0, 1], [40, 0])}px)`,
            display: "inline-block",
          }}>{splitRight}</span>
        </span>
      );
    }
    if (effect === "mirror_echo") {
      return (
        <span style={{ position: "relative", display: "inline-block" }}>
          <span style={{
            position: "absolute",
            left: -echoOffset,
            top: echoOffset * 0.4,
            opacity: echoOpacity,
            color: accent,
            WebkitTextStroke: "0px transparent",
            filter: "blur(1px)",
            pointerEvents: "none",
          }}>{text}</span>
          <span style={{
            position: "absolute",
            left: echoOffset,
            top: -echoOffset * 0.3,
            opacity: echoOpacity * 0.7,
            color: accent,
            WebkitTextStroke: "0px transparent",
            filter: "blur(2px)",
            pointerEvents: "none",
          }}>{text}</span>
          <span style={{ position: "relative" }}>{text}</span>
        </span>
      );
    }
    if (effect === "sticker_pop") {
      return (
        <span style={{
          display: "inline-block",
          padding: "10px 18px",
          background: `linear-gradient(135deg, ${accent}22, ${accent}55)`,
          border: `3px solid ${accent}`,
          borderRadius: 14,
          boxShadow: `0 8px 0 ${accent}99, 0 14px 28px rgba(0,0,0,0.45)`,
        }}>{text}</span>
      );
    }
    return text;
  };

  return (
    <AbsoluteFill style={{ pointerEvents: "none", opacity: effect === "z_parallax" ? depthExitOpacity : exitOpacity }}>
      {effect === "hero_punch" && (
        <AbsoluteFill style={{
          background: "radial-gradient(circle at center, rgba(0,0,0,0.02) 0%, rgba(0,0,0,0.72) 100%)",
          opacity: interpolate(enter, [0, 1], [0, 1]),
        }} />
      )}
      {effect === "z_parallax" && (
        <AbsoluteFill style={{
          background: "radial-gradient(circle at 50% 40%, rgba(0,0,0,0.0) 0%, rgba(0,0,0,0.5) 100%)",
          opacity: interpolate(depthEnter, [0, 1], [0, depthIntensity]),
        }} />
      )}
      {effect === "split_impact" && (
        <AbsoluteFill style={{
          background: `linear-gradient(90deg, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.15) 50%, ${accent}22 100%)`,
          opacity: interpolate(enter, [0, 1], [0, 1]),
        }} />
      )}

      <AbsoluteFill style={{ zIndex: 1, justifyContent: "flex-start", alignItems: effectiveAlignItems, padding: "0 6%" }}>
        <div style={{
          position: "absolute",
          top: effectiveTop,
          left: effect === "orbit_halo" ? aroundLeft : undefined,
          transform: effectiveTransform,
          maxWidth: `${clamp(Number(style.maxWidthPct ?? 86), 35, 96)}%`,
          textAlign,
          ...baseTextStyle,
        }}>
          {effect === "side_rail" && (
            <div style={{
              width: 72,
              height: 8,
              borderRadius: 999,
              background: `linear-gradient(90deg, ${accent}, ${accent}00)`,
              marginBottom: 16,
              marginLeft: position === "right" ? "auto" : 0,
              boxShadow: `0 0 18px ${accent}`,
            }} />
          )}
          {renderBody()}
          {effect === "hero_punch" && (
            <div style={{
              height: 7,
              borderRadius: 999,
              margin: "16px auto 0",
              width: "48%",
              background: `linear-gradient(90deg, transparent, ${accent}, transparent)`,
              boxShadow: `0 0 28px ${accent}`,
            }} />
          )}
          {effect === "float_track" && foreground && (
            <div style={{ height: 4, borderRadius: 999, margin: "12px auto 0", width: "28%", background: accent, opacity: 0.75 }} />
          )}
        </div>
      </AbsoluteFill>

      {foreground && foreground.path && effect === "depth_cutout" && (
        <Img
          src={foreground.path}
          style={{
            position: "absolute",
            zIndex: 2,
            left: foreground.x * coverScale + coverOffsetX,
            top: foreground.y * coverScale + coverOffsetY,
            width: foreground.width * coverScale,
            height: foreground.height * coverScale,
            objectFit: "fill",
          }}
        />
      )}
    </AbsoluteFill>
  );
};
