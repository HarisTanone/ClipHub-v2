/**
 * GhostDetectionPreview — SVG schematic showing valid vs ghost face filtering.
 *
 * Reactive preview that visualizes how Ghost Detection parameters affect
 * the false-positive filtering pipeline. Shows face bounding boxes with
 * valid/ghost states, IoU overlap regions, persistence indicators,
 * and size threshold bars.
 */

import { useMemo } from "react";

interface GhostDetectionPreviewProps {
  minFaceAreaPx: number;
  minAreaRatioToMax: number;
  minFrameRatio: number;
  ghostIouThreshold: number;
  ghostCenterDistRatio: number;
  ghostCenterDistBroad: number;
  minPairSizeRatio: number;
}

export function GhostDetectionPreview({
  minFaceAreaPx,
  minAreaRatioToMax,
  minFrameRatio,
  ghostIouThreshold,
  ghostCenterDistRatio,
  ghostCenterDistBroad,
  minPairSizeRatio,
}: GhostDetectionPreviewProps) {
  const svgContent = useMemo(() => {
    // Frame dimensions (16:9 aspect ratio within SVG viewBox)
    const frameX = 20;
    const frameY = 10;
    const frameW = 260;
    const frameH = 120;

    // Face sizes — large, medium, small
    // Normalize minFaceAreaPx (typical range ~2000-10000) to determine threshold
    const areaThreshold = Math.max(0.1, Math.min(0.9, minFaceAreaPx / 12000));

    // Large face (always valid)
    const largeFace = {
      x: frameX + 30,
      y: frameY + 15,
      w: 50,
      h: 60,
      valid: true,
    };

    // Medium face — valid if ratio to largest is above minAreaRatioToMax
    // minAreaRatioToMax typical range 0.05-0.5
    const mediumRatio = 0.4; // medium is 40% of large area
    const mediumValid = mediumRatio >= minAreaRatioToMax;
    const mediumFace = {
      x: frameX + 110,
      y: frameY + 25,
      w: 35,
      h: 42,
      valid: mediumValid,
    };

    // Small face — ghost if below area threshold
    const smallRatio = 0.15; // small is 15% of large area
    const smallValid = smallRatio >= minAreaRatioToMax && areaThreshold < 0.5;
    const smallFace = {
      x: frameX + 185,
      y: frameY + 40,
      w: 22,
      h: 26,
      valid: smallValid,
    };

    // IoU overlap pair — two boxes that overlap
    // Higher ghostIouThreshold = less aggressive duplicate removal
    const iouOverlapAmount = Math.max(5, (1 - ghostIouThreshold) * 30);
    const overlapFace1 = {
      x: frameX + 195,
      y: frameY + 12,
      w: 32,
      h: 38,
    };
    const overlapFace2 = {
      x: overlapFace1.x + overlapFace1.w - iouOverlapAmount,
      y: overlapFace1.y + 5,
      w: 32,
      h: 38,
    };

    // IoU overlap region coordinates
    const iouRegion = {
      x: overlapFace2.x,
      y: Math.max(overlapFace1.y, overlapFace2.y),
      w: iouOverlapAmount,
      h: Math.min(
        overlapFace1.y + overlapFace1.h,
        overlapFace2.y + overlapFace2.h
      ) - Math.max(overlapFace1.y, overlapFace2.y),
    };

    // Size threshold bar position
    const thresholdBarY = frameY + frameH - 10;
    const thresholdBarWidth = areaThreshold * frameW * 0.6;

    // Persistence indicator — frame count dots
    // minFrameRatio typical range 0.01-0.3
    const totalDots = 8;
    const activeDots = Math.max(1, Math.round(minFrameRatio * totalDots * 3));
    const persistenceY = frameY + frameH + 20;

    // Center distance indicators
    // ghostCenterDistRatio typical range 0.1-0.5
    const centerDistRadius = Math.max(8, ghostCenterDistRatio * 60);
    // ghostCenterDistBroad typical range 0.2-0.8
    const broadDistRadius = Math.max(12, ghostCenterDistBroad * 50);

    // Pair size ratio indicator
    // minPairSizeRatio typical range 0.3-0.9
    const pairValid = mediumRatio / 1.0 >= minPairSizeRatio;

    return {
      frameX,
      frameY,
      frameW,
      frameH,
      largeFace,
      mediumFace,
      smallFace,
      overlapFace1,
      overlapFace2,
      iouRegion,
      iouOverlapAmount,
      thresholdBarY,
      thresholdBarWidth,
      totalDots,
      activeDots,
      persistenceY,
      centerDistRadius,
      broadDistRadius,
      pairValid,
      areaThreshold,
    };
  }, [
    minFaceAreaPx,
    minAreaRatioToMax,
    minFrameRatio,
    ghostIouThreshold,
    ghostCenterDistRatio,
    ghostCenterDistBroad,
    minPairSizeRatio,
  ]);

  const {
    frameX,
    frameY,
    frameW,
    frameH,
    largeFace,
    mediumFace,
    smallFace,
    overlapFace1,
    overlapFace2,
    iouRegion,
    thresholdBarY,
    thresholdBarWidth,
    totalDots,
    activeDots,
    persistenceY,
    centerDistRadius,
    broadDistRadius,
    pairValid,
  } = svgContent;

  return (
    <svg
      data-testid="ghost-detection-preview"
      viewBox="0 0 300 200"
      className="w-full"
      style={{ maxHeight: 200 }}
      aria-label="Ghost Detection parameter preview"
    >
      {/* Video frame background */}
      <rect
        x={frameX}
        y={frameY}
        width={frameW}
        height={frameH}
        rx={6}
        fill="#18181b"
        stroke="#3f3f46"
        strokeWidth={1.5}
      />

      {/* ─── Large face (always valid) ─── */}
      <rect
        x={largeFace.x}
        y={largeFace.y}
        width={largeFace.w}
        height={largeFace.h}
        rx={2}
        fill="none"
        stroke="#10b981"
        strokeWidth={1.5}
      />
      <text
        x={largeFace.x + largeFace.w / 2}
        y={largeFace.y - 3}
        textAnchor="middle"
        fill="#10b981"
        fontSize={7}
        fontFamily="sans-serif"
      >
        valid
      </text>

      {/* ─── Medium face (conditional based on ratio) ─── */}
      <rect
        x={mediumFace.x}
        y={mediumFace.y}
        width={mediumFace.w}
        height={mediumFace.h}
        rx={2}
        fill="none"
        stroke={mediumFace.valid ? "#10b981" : "#f59e0b"}
        strokeWidth={1.3}
        strokeDasharray={mediumFace.valid ? "none" : "4 3"}
      />
      <text
        x={mediumFace.x + mediumFace.w / 2}
        y={mediumFace.y - 3}
        textAnchor="middle"
        fill={mediumFace.valid ? "#10b981" : "#f59e0b"}
        fontSize={7}
        fontFamily="sans-serif"
      >
        {mediumFace.valid ? "valid" : "uncertain"}
      </text>

      {/* ─── Small face (ghost) ─── */}
      <rect
        x={smallFace.x}
        y={smallFace.y}
        width={smallFace.w}
        height={smallFace.h}
        rx={2}
        fill="none"
        stroke={smallFace.valid ? "#f59e0b" : "#ef4444"}
        strokeWidth={1.2}
        strokeDasharray="4 3"
      />
      <text
        x={smallFace.x + smallFace.w / 2}
        y={smallFace.y - 3}
        textAnchor="middle"
        fill={smallFace.valid ? "#f59e0b" : "#ef4444"}
        fontSize={7}
        fontFamily="sans-serif"
      >
        {smallFace.valid ? "uncertain" : "ghost"}
      </text>

      {/* ─── IoU overlap pair ─── */}
      {/* First box (valid) */}
      <rect
        x={overlapFace1.x}
        y={overlapFace1.y}
        width={overlapFace1.w}
        height={overlapFace1.h}
        rx={2}
        fill="none"
        stroke="#10b981"
        strokeWidth={1.2}
      />
      {/* Second box (duplicate/ghost) */}
      <rect
        x={overlapFace2.x}
        y={overlapFace2.y}
        width={overlapFace2.w}
        height={overlapFace2.h}
        rx={2}
        fill="none"
        stroke="#ef4444"
        strokeWidth={1.2}
        strokeDasharray="3 2"
      />
      {/* IoU overlap region highlight */}
      <rect
        x={iouRegion.x}
        y={iouRegion.y}
        width={Math.max(0, iouRegion.w)}
        height={Math.max(0, iouRegion.h)}
        fill="#ef4444"
        fillOpacity={0.15}
        stroke="#ef4444"
        strokeWidth={0.5}
        strokeDasharray="2 1"
      />
      {/* IoU label */}
      <text
        x={overlapFace2.x + overlapFace2.w / 2}
        y={overlapFace2.y + overlapFace2.h + 9}
        textAnchor="middle"
        fill="#71717a"
        fontSize={6.5}
        fontFamily="sans-serif"
      >
        IoU overlap
      </text>

      {/* ─── Size threshold bar ─── */}
      <line
        x1={frameX + 10}
        y1={thresholdBarY}
        x2={frameX + 10 + thresholdBarWidth}
        y2={thresholdBarY}
        stroke="#f59e0b"
        strokeWidth={2}
        strokeLinecap="round"
      />
      <text
        x={frameX + 10}
        y={thresholdBarY - 4}
        fill="#71717a"
        fontSize={7}
        fontFamily="sans-serif"
      >
        min area threshold
      </text>

      {/* ─── Center distance indicator ─── */}
      {/* Inner radius (ghostCenterDistRatio) */}
      <circle
        cx={mediumFace.x + mediumFace.w / 2}
        cy={mediumFace.y + mediumFace.h / 2}
        r={centerDistRadius}
        fill="none"
        stroke="#a1a1aa"
        strokeWidth={0.5}
        strokeDasharray="2 2"
      />
      {/* Outer radius (ghostCenterDistBroad) */}
      <circle
        cx={mediumFace.x + mediumFace.w / 2}
        cy={mediumFace.y + mediumFace.h / 2}
        r={broadDistRadius}
        fill="none"
        stroke="#71717a"
        strokeWidth={0.4}
        strokeDasharray="1 2"
      />

      {/* ─── Persistence indicator (frame ratio dots) ─── */}
      {Array.from({ length: totalDots }, (_, i) => (
        <circle
          key={`dot-${i}`}
          cx={frameX + 10 + i * 12}
          cy={persistenceY}
          r={3}
          fill={i < activeDots ? "#10b981" : "#3f3f46"}
          fillOpacity={i < activeDots ? 0.8 : 0.4}
        />
      ))}
      <text
        x={frameX + 10 + totalDots * 12 + 6}
        y={persistenceY + 3}
        fill="#71717a"
        fontSize={7}
        fontFamily="sans-serif"
      >
        frame persistence
      </text>

      {/* ─── Pair size ratio indicator ─── */}
      <text
        x={frameX + frameW - 70}
        y={persistenceY + 3}
        fill={pairValid ? "#10b981" : "#ef4444"}
        fontSize={7}
        fontFamily="sans-serif"
      >
        pair: {pairValid ? "valid" : "rejected"}
      </text>

      {/* ─── Legend ─── */}
      <text
        x={frameX}
        y={192}
        fill="#71717a"
        fontSize={7.5}
        fontFamily="sans-serif"
      >
        {"✓ valid"}
      </text>
      <text
        x={frameX + 45}
        y={192}
        fill="#ef4444"
        fontSize={7.5}
        fontFamily="sans-serif"
      >
        {"✗ ghost"}
      </text>
      <text
        x={frameX + 90}
        y={192}
        fill="#f59e0b"
        fontSize={7.5}
        fontFamily="sans-serif"
      >
        {"~ overlap"}
      </text>
    </svg>
  );
}
