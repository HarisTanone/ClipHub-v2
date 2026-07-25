import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

export interface CTAProps {
  text?: string;
  type?: string;
  duration_sec?: number;
  position?: string;
}

/**
 * End-card CTA — last N seconds, bottom pill.
 * Soft fade-in; no heavy animation (safe on short clips).
 */
export const CTALayer: React.FC<{ cta?: CTAProps | null; clipDurationSec: number }> = ({
  cta,
  clipDurationSec,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!cta?.text) return null;

  const durationSec = Math.min(
    Math.max(Number(cta.duration_sec ?? (cta as any).duration ?? 1.5) || 1.5, 0.8),
    3.0
  );
  const startSec = Math.max(0, clipDurationSec - durationSec);
  const startFrame = Math.floor(startSec * fps);
  if (frame < startFrame) return null;

  const local = frame - startFrame;
  const fadeFrames = Math.max(1, Math.floor(fps * 0.25));
  const opacity = interpolate(local, [0, fadeFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const y = interpolate(local, [0, fadeFrames], [12, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ pointerEvents: "none", zIndex: 20 }}>
      <div
        style={{
          position: "absolute",
          left: "50%",
          bottom: "7%",
          transform: `translateX(-50%) translateY(${y}px)`,
          opacity,
          maxWidth: "86%",
          padding: "12px 22px",
          borderRadius: 999,
          background: "rgba(16, 185, 129, 0.92)",
          boxShadow: "0 8px 28px rgba(0,0,0,0.45)",
          border: "1px solid rgba(255,255,255,0.18)",
          color: "#fff",
          fontFamily: "Inter, system-ui, sans-serif",
          fontWeight: 700,
          fontSize: 28,
          letterSpacing: 0.2,
          textAlign: "center",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {cta.text}
      </div>
    </AbsoluteFill>
  );
};
