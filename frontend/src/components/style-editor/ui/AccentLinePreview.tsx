import React from "react";
import type { HookStyle } from "../types";

export function AccentLinePreview({ style }: { style: HookStyle }) {
  const pos = style.linePosition;
  const base: React.CSSProperties = { backgroundColor: style.lineColor, position: "absolute" };
  // Auto-adjust: calculate width/height based on approximate text length
  const textLen = (style.text || "Hook text preview here").length;
  const autoWidthPct = Math.min(Math.max(textLen * 2.5, 20), 70); // 20-70% based on text
  const autoHeightPct = Math.min(Math.max(textLen * 1.5, 15), 50); // 15-50% for vertical
  const autoW = style.lineAutoWidth ? `${autoWidthPct}%` : `${style.lineWidth}%`;
  const autoH = style.lineAutoWidth ? `${autoHeightPct}%` : `${style.lineWidth}%`;

  if (pos === "top") Object.assign(base, { top: style.lineOffset, left: "50%", transform: "translateX(-50%)", width: autoW, height: style.lineThickness });
  if (pos === "bottom") Object.assign(base, { bottom: style.lineOffset, left: "50%", transform: "translateX(-50%)", width: autoW, height: style.lineThickness });
  if (pos === "left") Object.assign(base, { left: style.lineOffset, top: "50%", transform: "translateY(-50%)", height: autoH, width: style.lineThickness });
  if (pos === "right") Object.assign(base, { right: style.lineOffset, top: "50%", transform: "translateY(-50%)", height: autoH, width: style.lineThickness });
  if (pos === "center-h") Object.assign(base, { top: `calc(50% + ${style.lineOffset}px)`, left: "50%", transform: "translate(-50%, -50%)", width: autoW, height: style.lineThickness });
  if (pos === "center-v") Object.assign(base, { top: "50%", left: `calc(50% + ${style.lineOffset}px)`, transform: "translate(-50%, -50%)", height: autoH, width: style.lineThickness });
  if (pos === "auto-bottom") Object.assign(base, { top: `calc(${style.positionY}% + ${style.lineOffset + 20}px)`, left: "50%", transform: "translateX(-50%)", width: autoW, height: style.lineThickness });
  return <div style={base} />;
}
