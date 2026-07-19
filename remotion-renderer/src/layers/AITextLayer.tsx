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
  const enter = spring({ frame: localFrame, fps, config: { damping: 16, stiffness: 190, mass: 0.7 } });
  const exitOpacity = interpolate(localFrame, [Math.max(0, eventDuration - 8), eventDuration], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const animation = style.animation || "cinematic";
  const glitchOffset = animation === "glitch" ? interpolate(enter, [0, 0.3, 0.6, 1], [-6, 4, -3, 0]) : 0;
  const neonGlow = animation === "neon" ? interpolate(enter, [0, 1], [4, 28]) : 0;
  const transform = animation === "slam"
    ? `scale(${interpolate(enter, [0, 1], [1.4, 1])}) rotate(${interpolate(enter, [0, 1], [-3, 0])}deg)`
    : animation === "reveal"
      ? `translateY(${interpolate(enter, [0, 1], [42, 0])}px)`
      : animation === "glitch"
        ? `translateX(${glitchOffset}px) translateY(${interpolate(enter, [0, 1], [10, 0])}px)`
        : animation === "neon"
          ? `scale(${interpolate(enter, [0, 1], [0.92, 1])})`
          : `scale(${interpolate(enter, [0, 1], [0.88, 1])}) translateY(${interpolate(enter, [0, 1], [18, 0])}px)`;

  const effect = active.effect || "spotlight";
  const position = active.position || (effect === "side_label" ? "left" : "center");
  const positionY = clamp(Number(style.positionY ?? 50), 12, 88);
  const textAlign = position === "left" ? "left" : position === "right" ? "right" : "center";
  const alignItems = position === "left" ? "flex-start" : position === "right" ? "flex-end" : "center";
  const needsForeground = effect === "behind_person" || effect === "depth_text" || effect === "around_head" || effect === "auto_avoid" || effect === "floating_text";
  const foreground = needsForeground
    ? active.foreground_frames?.find((item) => item.frame === frame)
    : undefined;

  const sourceWidth = Number(active.source_width || compositionWidth);
  const sourceHeight = Number(active.source_height || compositionHeight);
  const coverScale = Math.max(compositionWidth / sourceWidth, compositionHeight / sourceHeight);
  const coverOffsetX = (compositionWidth - sourceWidth * coverScale) / 2;
  const coverOffsetY = (compositionHeight - sourceHeight * coverScale) / 2;
  const accent = style.accentColor || "#FFD400";

  // ─── Effect-specific transforms ──────────────────────────────────────
  // Floating Text Following Person: gentle vertical bob
  const floatSpeed = clamp(Number(style.floatSpeed ?? 1.2), 0.5, 3.0);
  const floatOffset = effect === "floating_text" && foreground
    ? Math.sin(localFrame / fps * floatSpeed * Math.PI * 2) * 12 : 0;

  // Auto Avoid Person: move text to largest empty space
  let avoidPositionY = positionY;
  let avoidAlign: "flex-start" | "center" | "flex-end" = alignItems;
  if (effect === "auto_avoid" && foreground) {
    const personCenterY = (foreground.y + foreground.height / 2) * coverScale + coverOffsetY;
    const personCenterX = (foreground.x + foreground.width / 2) * coverScale + coverOffsetX;
    if (personCenterY < compositionHeight * 0.5) { avoidPositionY = 75; } else { avoidPositionY = 25; }
    if (personCenterX < compositionWidth * 0.5) { avoidAlign = "flex-end"; } else { avoidAlign = "flex-start"; }
  }

  // Around Head: text orbits the person's head
  const headRadius = clamp(Number(style.aroundHeadRadius ?? 60), 30, 120) / 100;
  let aroundTop = `${positionY}%`;
  let aroundLeft = "50%";
  let aroundTransform = `translateY(-50%) ${transform}`;
  if (effect === "around_head" && foreground && foreground.head_x !== undefined && foreground.head_y !== undefined) {
    const headCx = (foreground.head_x + (foreground.head_width || 0) / 2) * coverScale + coverOffsetX;
    const headCy = (foreground.head_y + (foreground.head_height || 0) / 2) * coverScale + coverOffsetY;
    const angle = (localFrame / fps) * 0.8;
    const orbitRadius = (foreground.head_width || 100) * coverScale * headRadius;
    aroundLeft = `${headCx + Math.cos(angle) * orbitRadius}px`;
    aroundTop = `${headCy + Math.sin(angle) * orbitRadius * 0.6}px`;
    aroundTransform = `translate(-50%, -50%) ${transform}`;
  }

  // Dynamic Depth Text: scale based on estimated person depth
  const depthIntensity = clamp(Number(style.depthIntensity ?? 0.5), 0.1, 1.0);
  const depthParallax = clamp(Number(style.depthParallax ?? 0.35), 0.05, 1.0);
  const depthFadeSec = clamp(Number(style.depthFade ?? 0.45), 0.1, 1.5);
  const depthFadeFrames = Math.max(1, Math.round(depthFadeSec * fps));
  let depthScale = 1;
  if (effect === "depth_text" && foreground && foreground.depth_z !== undefined) {
    depthScale = 0.7 + foreground.depth_z * depthIntensity * (1 + depthParallax);
  }
  const depthEnter = effect === "depth_text"
    ? interpolate(localFrame, [0, depthFadeFrames], [0, 1], { extrapolateRight: "clamp" })
    : enter;
  const depthExitOpacity = effect === "depth_text"
    ? interpolate(localFrame, [Math.max(0, eventDuration - depthFadeFrames), eventDuration], [1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : exitOpacity;

  // Smart Kinetic Typography: words animate in sequence
  const kineticStagger = Math.max(1, Math.round(Number(style.kineticStagger ?? 6)));
  const kineticWords = effect === "kinetic_type" ? (active.text || "").split(" ") : [];
  const kineticProgress = (idx: number) => {
    if (localFrame < idx * kineticStagger) return 0;
    if (localFrame > idx * kineticStagger + 12) return 1;
    return (localFrame - idx * kineticStagger) / 12;
  };

  const effectivePositionY = effect === "auto_avoid" ? avoidPositionY : positionY;
  const effectiveAlignItems = effect === "auto_avoid" ? avoidAlign : alignItems;
  const effectiveTop = effect === "around_head" ? aroundTop : `${effectivePositionY}%`;
  const effectiveTransform = effect === "around_head"
    ? aroundTransform
    : effect === "depth_text"
      ? `${transform} scale(${depthScale})`
      : effect === "floating_text"
        ? `${transform} translateY(${floatOffset}px)`
        : transform;

  return (
    <AbsoluteFill style={{ pointerEvents: "none", opacity: effect === "depth_text" ? depthExitOpacity : exitOpacity }}>
      {effect === "spotlight" && (
        <AbsoluteFill style={{
          background: "radial-gradient(circle at center, rgba(0,0,0,0.05) 0%, rgba(0,0,0,0.68) 100%)",
          opacity: interpolate(enter, [0, 1], [0, 1]),
        }} />
      )}
      {effect === "depth_text" && (
        <AbsoluteFill style={{
          background: "radial-gradient(circle at 50% 40%, rgba(0,0,0,0.0) 0%, rgba(0,0,0,0.45) 100%)",
          opacity: interpolate(depthEnter, [0, 1], [0, depthIntensity]),
        }} />
      )}

      <AbsoluteFill style={{ zIndex: 1, justifyContent: "flex-start", alignItems: effectiveAlignItems, padding: "0 7%" }}>
        <div style={{
          position: "absolute",
          top: effectiveTop,
          left: effect === "around_head" ? aroundLeft : undefined,
          transform: effectiveTransform,
          maxWidth: `${clamp(Number(style.maxWidthPct ?? 82), 35, 96)}%`,
          textAlign,
          color: style.color || "#FFFFFF",
          fontFamily: `'${style.fontFamily || "Anton"}', sans-serif`,
          fontSize: clamp(Number(style.fontSize ?? 92), 32, 160),
          fontWeight: Number(style.fontWeight || 900),
          letterSpacing: Number(style.letterSpacing ?? 1),
          lineHeight: Number(style.lineHeight ?? 0.95),
          textTransform: style.uppercase === false ? "none" : "uppercase",
          overflowWrap: "anywhere",
          paintOrder: style.strokeEnabled === false ? undefined : "stroke",
          WebkitTextStroke: style.strokeEnabled === false
            ? undefined
            : `${Number(style.strokeWidth ?? 2)}px ${style.strokeColor || "#09090B"}`,
          textShadow: animation === "neon"
            ? `0 0 ${neonGlow}px ${accent}, 0 0 ${neonGlow * 2}px ${accent}, 0 4px ${Number(style.shadowBlur ?? 22)}px ${style.shadowColor || "#000000"}`
            : style.shadowEnabled === false
              ? undefined
              : `0 8px ${Number(style.shadowBlur ?? 22)}px ${style.shadowColor || "#000000"}`,
        }}>
          {effect === "side_label" && (
            <div style={{ width: 80, height: 7, borderRadius: 999, background: accent, marginBottom: 18, marginLeft: position === "right" ? "auto" : 0 }} />
          )}
          {effect === "kinetic_type" ? (
            <span>
              {kineticWords.map((word, idx) => {
                const p = kineticProgress(idx);
                return (
                  <span key={idx} style={{
                    display: "inline-block",
                    opacity: p,
                    transform: `translateY(${(1 - p) * 24}px) scale(${0.8 + p * 0.2})`,
                    marginRight: "0.25em",
                  }}>
                    {word}
                  </span>
                );
              })}
            </span>
          ) : (
            active.text
          )}
          {effect === "spotlight" && (
            <div style={{ height: 6, borderRadius: 999, margin: "18px auto 0", width: "42%", background: accent, boxShadow: `0 0 24px ${accent}` }} />
          )}
          {effect === "floating_text" && foreground && (
            <div style={{ height: 4, borderRadius: 999, margin: "12px auto 0", width: "30%", background: accent, opacity: 0.7 }} />
          )}
        </div>
      </AbsoluteFill>

      {foreground && foreground.path && effect === "behind_person" && (
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
