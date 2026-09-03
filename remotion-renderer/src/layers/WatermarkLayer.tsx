import React from "react";
import { AbsoluteFill, Img, useVideoConfig } from "remotion";

export interface WatermarkConfig {
  enabled?: boolean;
  type?: "image" | "text";
  imageDataUrl?: string | null;
  text?: string;
  fontFamily?: string;
  fontSize?: number;
  fontWeight?: string;
  color?: string;
  sizePct?: number; // 5..100 % of video width
  opacity?: number; // 0..100
  position?:
    | "top-left"
    | "top-center"
    | "top-right"
    | "center-left"
    | "center"
    | "center-right"
    | "bottom-left"
    | "bottom-center"
    | "bottom-right";
  marginPct?: number; // 0..20 % of video dimension
}

export const WatermarkLayer: React.FC<{ watermark?: WatermarkConfig | null }> = ({
  watermark,
}) => {
  const { width, height } = useVideoConfig();

  if (!watermark || watermark.enabled === false) {
    return null;
  }

  const isEnabled =
    typeof watermark.enabled === "string"
      ? !["false", "0", "", "no", "off"].includes((watermark.enabled as string).toLowerCase().trim())
      : Boolean(watermark.enabled);

  if (!isEnabled) {
    return null;
  }

  const type = watermark.type || "text";
  const opacity = Math.max(0, Math.min(100, watermark.opacity ?? 60)) / 100;
  const position = watermark.position || "bottom-right";
  const marginPct = Math.max(0, Math.min(20, watermark.marginPct ?? 3)) / 100;
  const marginX = width * marginPct;
  const marginY = height * marginPct;

  // Resolve alignment styles
  let top: number | undefined;
  let bottom: number | undefined;
  let left: number | undefined;
  let right: number | undefined;
  let transformX = "0%";
  let transformY = "0%";

  if (position.includes("top")) {
    top = marginY;
  } else if (position.includes("bottom")) {
    bottom = marginY;
  } else {
    top = height / 2;
    transformY = "-50%";
  }

  if (position.includes("left")) {
    left = marginX;
  } else if (position.includes("right")) {
    right = marginX;
  } else {
    left = width / 2;
    transformX = "-50%";
  }

  const containerStyle: React.CSSProperties = {
    position: "absolute",
    top: top !== undefined ? `${top}px` : undefined,
    bottom: bottom !== undefined ? `${bottom}px` : undefined,
    left: left !== undefined ? `${left}px` : undefined,
    right: right !== undefined ? `${right}px` : undefined,
    transform: `translate(${transformX}, ${transformY})`,
    opacity,
    zIndex: 99,
    pointerEvents: "none",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  };

  if (type === "image" && watermark.imageDataUrl) {
    const sizePct = Math.max(5, Math.min(80, watermark.sizePct ?? 20)) / 100;
    const imgWidth = Math.round(width * sizePct);

    return (
      <AbsoluteFill style={{ pointerEvents: "none" }}>
        <div style={containerStyle}>
          <Img
            src={watermark.imageDataUrl}
            style={{
              width: `${imgWidth}px`,
              height: "auto",
              objectFit: "contain",
              filter: "drop-shadow(0 2px 8px rgba(0,0,0,0.6))",
            }}
          />
        </div>
      </AbsoluteFill>
    );
  }

  // Text watermark
  const text = watermark.text || "";
  if (!text.trim()) {
    return null;
  }

  const fontFamily = watermark.fontFamily || "Inter, sans-serif";
  const fontSize = watermark.fontSize || Math.round(width * 0.035);
  const fontWeight = watermark.fontWeight || "600";
  const color = watermark.color || "#FFFFFF";

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div style={containerStyle}>
        <span
          style={{
            fontFamily,
            fontSize: `${fontSize}px`,
            fontWeight,
            color,
            letterSpacing: "0.05em",
            textShadow: "0 2px 6px rgba(0,0,0,0.7), 0 0 2px rgba(0,0,0,0.9)",
            whiteSpace: "nowrap",
          }}
        >
          {text}
        </span>
      </div>
    </AbsoluteFill>
  );
};
