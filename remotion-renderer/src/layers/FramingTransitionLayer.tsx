import React from "react";
import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { FramingEvent, TransitionStyle } from "../types";

interface FramingTransitionLayerProps {
  children: React.ReactNode;
  events?: FramingEvent[];
  style?: TransitionStyle;
  duration?: number;
  entrance?: boolean;
}

/**
 * Applies the user's transition choice to the video layer only.
 * Layout changes are cross-faded by FFmpeg; speaker events receive a small,
 * deterministic accent here so hook and subtitle overlays remain readable.
 */
export const FramingTransitionLayer: React.FC<FramingTransitionLayerProps> = ({
  children,
  events = [],
  style = "cut",
  duration = 0.35,
  entrance = true,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const durationFrames = Math.max(1, Math.round(Math.min(1, Math.max(0.05, duration)) * fps));

  let opacity = 1;
  let translateX = 0;
  let scale = 1;
  let filter = "none";

  if (entrance && style !== "cut" && frame <= durationFrames) {
    const progress = interpolate(frame, [0, durationFrames], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    });
    if (style === "fade") opacity = progress;
    if (style === "slide") translateX = (1 - progress) * 100;
    if (style === "zoom") {
      scale = 1.08 - progress * 0.08;
      opacity = progress;
    }
    // 2-frame subtle optical flash on entrance
    if (frame <= 2) {
      filter = "brightness(1.25) saturate(1.1)";
    }
  }

  if (style !== "cut") {
    // Layout transitions are already rendered as real xfade/slide/zoom effects
    // in the reframe stage. Only accent speaker switches here.
    const speakerEvents = events.filter((event) => event.kind === "speaker");
    for (const event of speakerEvents) {
      const centerFrame = Math.round(Math.max(0, event.time) * fps);
      const startFrame = centerFrame - durationFrames / 2;
      const endFrame = centerFrame + durationFrames / 2;
      if (frame < startFrame || frame > endFrame) continue;

      const phase = interpolate(frame, [startFrame, centerFrame, endFrame], [0, 1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
        easing: Easing.inOut(Easing.cubic),
      });
      if (style === "fade") opacity = Math.min(opacity, 1 - phase * 0.45);
      // Speaker slide is already the actual bbox-aware crop interpolation in
      // FFmpeg; adding subtle whip blur during the peak phase gives a professional pan feel
      if (phase > 0.4) {
        filter = `blur(${Math.round(phase * 4)}px)`;
      }
      if (style === "zoom") scale = Math.max(scale, 1 + phase * 0.06);
      break;
    }
  }

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        opacity,
        overflow: "hidden",
        filter,
        transform: `translateX(${translateX}%) scale(${scale})`,
        transformOrigin: "center center",
      }}
    >
      {children}
    </div>
  );
};
