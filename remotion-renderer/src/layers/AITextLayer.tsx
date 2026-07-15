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
  const transform = animation === "slam"
    ? `scale(${interpolate(enter, [0, 1], [1.4, 1])}) rotate(${interpolate(enter, [0, 1], [-3, 0])}deg)`
    : animation === "reveal"
      ? `translateY(${interpolate(enter, [0, 1], [42, 0])}px)`
      : `scale(${interpolate(enter, [0, 1], [0.88, 1])}) translateY(${interpolate(enter, [0, 1], [18, 0])}px)`;

  const effect = active.effect || "spotlight";
  const position = active.position || (effect === "side_label" ? "left" : "center");
  const positionY = clamp(Number(style.positionY ?? 50), 12, 88);
  const textAlign = position === "left" ? "left" : position === "right" ? "right" : "center";
  const alignItems = position === "left" ? "flex-start" : position === "right" ? "flex-end" : "center";
  const foreground = effect === "behind_person"
    ? active.foreground_frames?.find((item) => item.frame === frame)
    : undefined;

  const sourceWidth = Number(active.source_width || compositionWidth);
  const sourceHeight = Number(active.source_height || compositionHeight);
  const coverScale = Math.max(compositionWidth / sourceWidth, compositionHeight / sourceHeight);
  const coverOffsetX = (compositionWidth - sourceWidth * coverScale) / 2;
  const coverOffsetY = (compositionHeight - sourceHeight * coverScale) / 2;
  const accent = style.accentColor || "#FFD400";

  return (
    <AbsoluteFill style={{ pointerEvents: "none", opacity: exitOpacity }}>
      {effect === "spotlight" && (
        <AbsoluteFill style={{
          background: "radial-gradient(circle at center, rgba(0,0,0,0.05) 0%, rgba(0,0,0,0.68) 100%)",
          opacity: interpolate(enter, [0, 1], [0, 1]),
        }} />
      )}

      <AbsoluteFill style={{ zIndex: 1, justifyContent: "flex-start", alignItems, padding: "0 7%" }}>
        <div style={{
          position: "absolute",
          top: `${positionY}%`,
          transform: `translateY(-50%) ${transform}`,
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
          textShadow: style.shadowEnabled === false
            ? undefined
            : `0 8px ${Number(style.shadowBlur ?? 22)}px ${style.shadowColor || "#000000"}`,
        }}>
          {effect === "side_label" && (
            <div style={{ width: 80, height: 7, borderRadius: 999, background: accent, marginBottom: 18, marginLeft: position === "right" ? "auto" : 0 }} />
          )}
          {active.text}
          {effect === "spotlight" && (
            <div style={{ height: 6, borderRadius: 999, margin: "18px auto 0", width: "42%", background: accent, boxShadow: `0 0 24px ${accent}` }} />
          )}
        </div>
      </AbsoluteFill>

      {foreground && (
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
