/**
 * ZoomLayer — Auto zoom/punch-in effect on video at emphasis moments.
 *
 * Applies smooth scale transform to base video at specific timestamps
 * (triggered by prosody energy peaks or highlight words).
 *
 * Supports face-aware anchors (faceX, faceY) so zoom targets the speaker's face,
 * as well as multi-tier punch intensities and slow dolly-ins.
 */
import React, { useMemo } from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

export interface ZoomEvent {
  time: number;          // seconds — when to zoom
  intensity?: number;     // 0.0-1.0 — how much to zoom (default 0.5)
  duration?: number;      // seconds — zoom duration (default 0.5)
  anchorX?: number;       // 0-100 percentage — face/focus X origin (default 50)
  anchorY?: number;       // 0-100 percentage — face/focus Y origin (default 40 for face)
  faceX?: number;         // alias for anchorX
  faceY?: number;         // alias for anchorY
  mode?: "punch" | "slow_dolly" | "micro_punch" | "heavy_punch";
}

interface ZoomLayerProps {
  children: React.ReactNode;
  zoomEvents: ZoomEvent[];
  maxScale?: number;        // max zoom level (default 1.18)
  defaultDuration?: number; // default zoom duration in seconds
}

export const ZoomLayer: React.FC<ZoomLayerProps> = ({
  children,
  zoomEvents,
  maxScale = 1.18,
  defaultDuration = 0.5,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Pre-compute frame-based zoom events
  const frameEvents = useMemo(() => {
    return zoomEvents.map((e) => {
      const originX = e.anchorX ?? e.faceX ?? 50;
      const originY = e.anchorY ?? e.faceY ?? 40; // Default slightly above center (head zone)
      return {
        startFrame: Math.floor(e.time * fps),
        durationFrames: Math.floor((e.duration || defaultDuration) * fps),
        intensity: Math.min(1, Math.max(0, e.intensity ?? 0.5)),
        originX,
        originY,
        mode: e.mode || (e.intensity && e.intensity > 0.7 ? "heavy_punch" : "punch"),
      };
    });
  }, [zoomEvents, fps, defaultDuration]);

  // Calculate current zoom level and anchor origin
  let currentScale = 1.0;
  let currentOrigin = "50% 50%";

  for (const event of frameEvents) {
    const { startFrame, durationFrames, intensity, originX, originY, mode } = event;
    const endFrame = startFrame + durationFrames;

    if (frame >= startFrame && frame <= endFrame) {
      currentOrigin = `${originX}% ${originY}%`;

      if (mode === "slow_dolly") {
        // Slow cinematic push in
        const peakScale = 1.0 + (maxScale - 1.0) * intensity * 0.75;
        currentScale = interpolate(
          frame,
          [startFrame, endFrame],
          [1.0, peakScale],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) }
        );
      } else {
        // Dynamic punch: quick punch-in (40% duration) + gentle settle-out (60% duration)
        const punchDuration = Math.floor(durationFrames * 0.4);
        const peakScale = 1.0 + (maxScale - 1.0) * intensity;

        if (frame <= startFrame + punchDuration) {
          // Fast punch in with cubic ease out
          currentScale = interpolate(
            frame,
            [startFrame, startFrame + punchDuration],
            [1.0, peakScale],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.back(1.2)) }
          );
        } else {
          // Smooth recovery out
          currentScale = interpolate(
            frame,
            [startFrame + punchDuration, endFrame],
            [peakScale, 1.0],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.quad) }
          );
        }
      }
      break; // Only apply one zoom at a time
    }
  }

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        transform: `scale(${currentScale})`,
        transformOrigin: currentOrigin,
        overflow: "hidden",
        transition: "transform-origin 0.2s ease",
      }}
    >
      {children}
    </div>
  );
};
