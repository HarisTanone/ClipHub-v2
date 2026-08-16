import React from "react";
import { AbsoluteFill, Img, OffthreadVideo, interpolate, useCurrentFrame } from "remotion";

export type CanvasAccent =
  | { type: "soft-glow"; x: number; y: number; r: number; color: string }
  | { type: "blob"; x: number; y: number; r: number; color: string }
  | { type: "bar"; x: number; y: number; w: number; h: number; color: string }
  | { type: "line"; x1: number; y1: number; x2: number; y2: number; color: string; w?: number }
  | { type: "ring"; x: number; y: number; r: number; color: string; stroke?: number }
  | { type: "frame"; inset: number; color: string; stroke?: number };

export interface CanvasLayout {
  videoX: number;
  videoY: number;
  videoW: number;
  videoH: number;
  borderRadius?: number;
  shadow?: string;
  ambientGlow?: boolean;
  ambientGlowColor?: string;
}

export interface CanvasConfig {
  aspectRatio?: string; // final canvas — always 9:16 for TikTok
  contentAspect?: string; // main video framing 16:9 / 1:1
  width?: number;
  height?: number;
  mode?: "template" | "upload" | "mirror";
  templateId?: string | null;
  templateName?: string;
  background?: {
    type?: string; // "gradient" | "solid" | "image" | "video_mirror" | "mesh"
    stops?: Array<{ offset: number; color: string }>;
    angle?: number;
    vignette?: number;
    color?: string;
    imageUrl?: string | null;
    blurAmount?: number;
    dimAmount?: number;
  };
  accents?: CanvasAccent[];
  layout?: CanvasLayout;
  backgroundImageUrl?: string | null;
  videoPath?: string;
}

function gradientCss(bg: CanvasConfig["background"]): string {
  if (!bg) return "#0a0a0a";
  if (bg.type === "solid" || (!bg.stops && bg.color)) return bg.color || "#0a0a0a";
  if (bg.type === "image" && bg.imageUrl) return "transparent";
  if (bg.type === "video_mirror") return "#050505";
  const stops = bg.stops || [
    { offset: 0, color: "#111" },
    { offset: 1, color: "#000" },
  ];
  const angle = bg.angle ?? 180;
  return `linear-gradient(${angle}deg, ${stops
    .map((s) => `${s.color} ${Math.round(s.offset * 100)}%`)
    .join(", ")})`;
}

/** Full-canvas designed background + accents (behind footage). */
export const CanvasBackgroundLayer: React.FC<{ config: CanvasConfig; videoPath?: string }> = ({
  config,
  videoPath,
}) => {
  const frame = useCurrentFrame();
  const bg = config.background || {};
  const accents = config.accents || [];
  const imageUrl = config.backgroundImageUrl || bg.imageUrl || null;
  const vignette = bg.vignette ?? 0.35;
  const isVideoMirror = bg.type === "video_mirror" || config.mode === "mirror" || config.templateId === "video-mirror";
  const activeVideoSrc = config.videoPath || videoPath;

  // Gentle breathing motion for video mirror
  const mirrorScale = interpolate(Math.sin(frame / 45), [-1, 1], [1.35, 1.42]);

  return (
    <AbsoluteFill style={{ background: gradientCss(bg), overflow: "hidden" }}>
      {/* ── Dynamic Blurred Video Mirror ── */}
      {isVideoMirror && activeVideoSrc ? (
        <AbsoluteFill style={{ overflow: "hidden" }}>
          <div
            style={{
              position: "absolute",
              inset: "-15%",
              width: "130%",
              height: "130%",
              transform: `scale(${mirrorScale})`,
              filter: `blur(${bg.blurAmount ?? 45}px) brightness(${bg.dimAmount ?? 0.6}) saturate(1.2)`,
              transformOrigin: "center center",
            }}
          >
            <OffthreadVideo
              src={activeVideoSrc}
              style={{
                width: "100%",
                height: "100%",
                objectFit: "cover",
              }}
            />
          </div>
        </AbsoluteFill>
      ) : null}

      {/* ── Background Image ── */}
      {imageUrl && !isVideoMirror ? (
        <Img
          src={imageUrl}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />
      ) : null}

      {/* ── Background Decorative Accents ── */}
      {accents.map((a, i) => {
        if (a.type === "soft-glow" || a.type === "blob") {
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: `${a.x * 100}%`,
                top: `${a.y * 100}%`,
                width: `${a.r * 200}%`,
                height: `${a.r * 200}%`,
                transform: "translate(-50%, -50%)",
                borderRadius: "50%",
                background: a.color,
                filter: "blur(40px)",
                pointerEvents: "none",
              }}
            />
          );
        }
        if (a.type === "bar") {
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: `${a.x * 100}%`,
                top: `${a.y * 100}%`,
                width: `${a.w * 100}%`,
                height: `${a.h * 100}%`,
                background: a.color,
                borderRadius: 99,
                pointerEvents: "none",
              }}
            />
          );
        }
        if (a.type === "line") {
          const dx = (a.x2 - a.x1) * 100;
          const dy = (a.y2 - a.y1) * 100;
          const len = Math.sqrt(dx * dx + dy * dy);
          const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: `${a.x1 * 100}%`,
                top: `${a.y1 * 100}%`,
                width: `${len}%`,
                height: a.w || 2,
                background: a.color,
                transformOrigin: "0 50%",
                transform: `rotate(${angle}deg)`,
                borderRadius: 99,
                pointerEvents: "none",
              }}
            />
          );
        }
        if (a.type === "ring") {
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: `${a.x * 100}%`,
                top: `${a.y * 100}%`,
                width: `${a.r * 200}%`,
                height: `${a.r * 200}%`,
                transform: "translate(-50%, -50%)",
                borderRadius: "50%",
                border: `${a.stroke || 1}px solid ${a.color}`,
                pointerEvents: "none",
              }}
            />
          );
        }
        if (a.type === "frame") {
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                inset: `${a.inset * 100}%`,
                border: `${a.stroke || 1}px solid ${a.color}`,
                borderRadius: 8,
                pointerEvents: "none",
              }}
            />
          );
        }
        return null;
      })}

      {/* ── Ambient Radial Vignette ── */}
      {vignette > 0 ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: `radial-gradient(ellipse at center, transparent 35%, rgba(0,0,0,${vignette}) 100%)`,
            pointerEvents: "none",
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
};

/** Style helper: position the footage window from layout fractions.
 * Content keeps native aspect (object-fit: contain) — never stretch/crop
 * into the 9:16 canvas. Template fills the letterbox zones.
 */
export function videoSlotStyle(layout?: CanvasLayout): React.CSSProperties {
  if (!layout) {
    return { width: "100%", height: "100%", objectFit: "cover" };
  }

  const glowColor = layout.ambientGlowColor || "rgba(0, 0, 0, 0.55)";
  const ambientShadow = layout.ambientGlow
    ? `0 0 50px ${glowColor}, ${layout.shadow || "0 16px 48px rgba(0,0,0,0.5)"}`
    : (layout.shadow || "0 12px 40px rgba(0,0,0,0.45)");

  return {
    position: "absolute",
    left: `${layout.videoX * 100}%`,
    top: `${layout.videoY * 100}%`,
    width: `${layout.videoW * 100}%`,
    height: `${layout.videoH * 100}%`,
    borderRadius: layout.borderRadius ?? 0,
    overflow: "hidden",
    boxShadow: ambientShadow,
  };
}

/** Video element style inside the slot.
 * Slot already sized to content aspect — cover fills slot without letterbox
 * inside the band. Template fills outer 9:16 zones.
 */
export function videoFitStyle(hasCanvas: boolean): React.CSSProperties {
  return {
    width: "100%",
    height: "100%",
    objectFit: "cover",
    backgroundColor: "transparent",
  };
}
