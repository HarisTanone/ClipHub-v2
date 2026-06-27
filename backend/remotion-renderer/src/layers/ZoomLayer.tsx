/**
 * ZoomLayer — Auto zoom/punch-in effect on video at emphasis moments.
 *
 * Applies smooth scale transform to base video at specific timestamps
 * (triggered by prosody energy peaks or highlight words).
 *
 * Effect: scale 1.0 → 1.12 → 1.0 (ease-in-out, ~500ms total)
 */
import React, { useMemo } from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

interface ZoomEvent {
  time: number;      // seconds — when to zoom
  intensity?: number; // 0.0-1.0 — how much to zoom (default 0.5)
  duration?: number;  // seconds — zoom duration (default 0.5)
}

interface ZoomLayerProps {
  children: React.ReactNode;
  zoomEvents: ZoomEvent[];
  maxScale?: number;    // max zoom level (default 1.15)
  defaultDuration?: number; // default zoom duration in seconds
}

export const ZoomLayer: React.FC<ZoomLayerProps> = ({
  children,
  zoomEvents,
  maxScale = 1.15,
  defaultDuration = 0.5,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Pre-compute frame-based zoom events
  const frameEvents = useMemo(() => {
    return zoomEvents.map((e) => ({
      startFrame: Math.floor(e.time * fps),
      durationFrames: Math.floor((e.duration || defaultDuration) * fps),
      intensity: Math.min(1, Math.max(0, e.intensity ?? 0.5)),
    }));
  }, [zoomEvents, fps, defaultDuration]);

  // Calculate current zoom level
  let currentScale = 1.0;

  for (const event of frameEvents) {
    const { startFrame, durationFrames, intensity } = event;
    const endFrame = startFrame + durationFrames;

    if (frame >= startFrame && frame <= endFrame) {
      // Zoom in first half, zoom out second half
      const halfDuration = durationFrames / 2;
      const peakScale = 1.0 + (maxScale - 1.0) * intensity;

      if (frame <= startFrame + halfDuration) {
        // Zooming IN
        currentScale = interpolate(
          frame,
          [startFrame, startFrame + halfDuration],
          [1.0, peakScale],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) }
        );
      } else {
        // Zooming OUT
        currentScale = interpolate(
          frame,
          [startFrame + halfDuration, endFrame],
          [peakScale, 1.0],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.in(Easing.cubic) }
        );
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
        transformOrigin: "center center",
        overflow: "hidden",
      }}
    >
      {children}
    </div>
  );
};
