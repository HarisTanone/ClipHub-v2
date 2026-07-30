import React from "react";
import { AbsoluteFill, Img } from "remotion";

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
}

export interface CanvasConfig {
  aspectRatio?: string;
  width?: number;
  height?: number;
  mode?: "template" | "upload";
  templateId?: string | null;
  templateName?: string;
  background?: {
    type?: string;
    stops?: Array<{ offset: number; color: string }>;
    angle?: number;
    vignette?: number;
    color?: string;
    imageUrl?: string | null;
  };
  accents?: CanvasAccent[];
  layout?: CanvasLayout;
  backgroundImageUrl?: string | null;
}

function gradientCss(bg: CanvasConfig["background"]): string {
  if (!bg) return "#0a0a0a";
  if (bg.type === "solid" || (!bg.stops && bg.color)) return bg.color || "#0a0a0a";
  if (bg.type === "image" && bg.imageUrl) return "transparent";
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
export const CanvasBackgroundLayer: React.FC<{ config: CanvasConfig }> = ({ config }) => {
  const bg = config.background || {};
  const accents = config.accents || [];
  const imageUrl = config.backgroundImageUrl || bg.imageUrl || null;
  const vignette = bg.vignette ?? 0;

  return (
    <AbsoluteFill style={{ background: gradientCss(bg), overflow: "hidden" }}>
      {imageUrl ? (
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

      {vignette > 0 ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: `radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,${vignette}) 100%)`,
            pointerEvents: "none",
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
};

/** Style helper: position the footage window from layout fractions. */
export function videoSlotStyle(layout?: CanvasLayout): React.CSSProperties {
  if (!layout) {
    return { width: "100%", height: "100%", objectFit: "cover" };
  }
  return {
    position: "absolute",
    left: `${layout.videoX * 100}%`,
    top: `${layout.videoY * 100}%`,
    width: `${layout.videoW * 100}%`,
    height: `${layout.videoH * 100}%`,
    borderRadius: layout.borderRadius ?? 16,
    overflow: "hidden",
    boxShadow: layout.shadow || "0 16px 48px rgba(0,0,0,0.45)",
  };
}
