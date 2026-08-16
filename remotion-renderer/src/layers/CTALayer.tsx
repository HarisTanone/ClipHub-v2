import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

export interface CTAProps {
  text?: string;
  type?: "standard" | "tiktok" | "youtube" | "instagram" | string;
  duration_sec?: number;
  position?: string;
  handle?: string;
  avatarUrl?: string;
}

/**
 * End-card CTA — last N seconds, interactive creator mock pill.
 * Features bouncy spring entrance, platform styles (TikTok / YouTube / IG), and ambient glow.
 */
export const CTALayer: React.FC<{ cta?: CTAProps | null; clipDurationSec: number }> = ({
  cta,
  clipDurationSec,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!cta?.text && !cta?.handle) return null;

  const durationSec = Math.min(
    Math.max(Number(cta.duration_sec ?? (cta as any).duration ?? 1.8) || 1.8, 0.8),
    3.5
  );
  const startSec = Math.max(0, clipDurationSec - durationSec);
  const startFrame = Math.floor(startSec * fps);
  if (frame < startFrame) return null;

  const local = frame - startFrame;
  const bounce = spring({ frame: local, fps, config: { damping: 12, stiffness: 220, mass: 0.6 } });
  const y = interpolate(bounce, [0, 1], [30, 0]);
  const ctaType = cta.type || "standard";
  const ctaText = cta.text || (ctaType === "tiktok" ? "Follow for more" : ctaType === "youtube" ? "Subscribe" : "Follow Us");

  // TikTok follow transition: switch from "+" to "✓" after 25 frames
  const isFollowed = ctaType === "tiktok" && local > 24;
  const bellSwing = ctaType === "youtube" ? Math.sin(local * 0.6) * 15 : 0;

  return (
    <AbsoluteFill style={{ pointerEvents: "none", zIndex: 25 }}>
      <div
        style={{
          position: "absolute",
          left: "50%",
          bottom: "8%",
          transform: `translateX(-50%) translateY(${y}px) scale(${bounce})`,
          maxWidth: "88%",
          display: "inline-flex",
          alignItems: "center",
          gap: 12,
          padding: "12px 24px",
          borderRadius: 999,
          background: ctaType === "tiktok"
            ? "linear-gradient(135deg, rgba(254,44,85,0.95), rgba(238,29,82,0.95))"
            : ctaType === "youtube"
              ? "linear-gradient(135deg, rgba(255,0,0,0.95), rgba(200,0,0,0.95))"
              : "linear-gradient(135deg, rgba(16,185,129,0.95), rgba(5,150,105,0.95))",
          boxShadow: ctaType === "tiktok"
            ? "0 12px 35px rgba(254,44,85,0.4), 0 4px 15px rgba(0,0,0,0.5)"
            : ctaType === "youtube"
              ? "0 12px 35px rgba(255,0,0,0.4), 0 4px 15px rgba(0,0,0,0.5)"
              : "0 12px 35px rgba(16,185,129,0.4), 0 4px 15px rgba(0,0,0,0.5)",
          border: "1px solid rgba(255,255,255,0.25)",
          color: "#fff",
          fontFamily: "Inter, system-ui, sans-serif",
          fontWeight: 700,
        }}
      >
        {ctaType === "tiktok" && (
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: "50%",
              background: isFollowed ? "#10B981" : "#fff",
              color: isFollowed ? "#fff" : "#FE2C55",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 16,
              fontWeight: 900,
              transition: "all 0.2s ease",
            }}
          >
            {isFollowed ? "✓" : "+"}
          </div>
        )}

        {ctaType === "youtube" && (
          <div
            style={{
              transform: `rotate(${bellSwing}deg)`,
              transformOrigin: "top center",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
          </div>
        )}

        <span
          style={{
            fontSize: 26,
            letterSpacing: 0.3,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            textShadow: "0 2px 8px rgba(0,0,0,0.4)",
          }}
        >
          {ctaText}
        </span>
      </div>
    </AbsoluteFill>
  );
};
