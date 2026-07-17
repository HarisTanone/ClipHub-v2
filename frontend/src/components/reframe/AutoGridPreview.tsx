/**
 * AutoGridPreview — SVG schematic showing grid layout with zoom/margins.
 *
 * Reactive preview that visualizes how Auto Grid / Split-Screen parameters
 * affect the split-screen composition pipeline. Shows single-crop vs grid
 * split based on dominance, zoom crop rectangles, and face margin indicators.
 */

import { useMemo } from "react";

interface AutoGridPreviewProps {
  dominanceSingleCrop: number;
  gridBaseZoom: number;
  gridMaxZoom: number;
  gridFaceMargin: number;
  gridEnterSamples: number;
  gridExitSamples: number;
  minGridSegmentSeconds: number;
}

export function AutoGridPreview({
  dominanceSingleCrop,
  gridBaseZoom,
  gridMaxZoom,
  gridFaceMargin,
  gridEnterSamples,
  gridExitSamples,
  minGridSegmentSeconds,
}: AutoGridPreviewProps) {
  const svgContent = useMemo(() => {
    // 9:16 output frame dimensions within SVG viewBox
    const frameX = 90;
    const frameY = 10;
    const frameW = 120;
    const frameH = 170;

    // Determine mode: single crop vs grid split
    const isSingleCrop = dominanceSingleCrop > 0.75;

    // Grid panel dimensions (top + bottom in 9:16 frame)
    const panelGap = 4;
    const panelH = (frameH - panelGap) / 2;
    const topPanelY = frameY;
    const bottomPanelY = frameY + panelH + panelGap;

    // Face circle radius (base for indicators)
    const baseFaceRadius = 14;

    // Zoom visualization: crop rectangle shrinks as zoom increases
    // gridBaseZoom typically 1.0-2.0, gridMaxZoom typically 1.2-3.0
    const baseZoomFactor = Math.max(0.3, 1 / gridBaseZoom);
    const maxZoomFactor = Math.max(0.2, 1 / gridMaxZoom);

    // Margin indicator size (gridFaceMargin typically 0.05-0.5)
    const marginSize = Math.max(3, gridFaceMargin * 40);

    // Enter/exit sample counts for confirmation indicator
    const enterCount = Math.round(gridEnterSamples);
    const exitCount = Math.round(gridExitSamples);

    // Min segment duration
    const minSegment = minGridSegmentSeconds;

    return {
      frameX,
      frameY,
      frameW,
      frameH,
      isSingleCrop,
      panelGap,
      panelH,
      topPanelY,
      bottomPanelY,
      baseFaceRadius,
      baseZoomFactor,
      maxZoomFactor,
      marginSize,
      enterCount,
      exitCount,
      minSegment,
    };
  }, [
    dominanceSingleCrop,
    gridBaseZoom,
    gridMaxZoom,
    gridFaceMargin,
    gridEnterSamples,
    gridExitSamples,
    minGridSegmentSeconds,
  ]);

  const {
    frameX,
    frameY,
    frameW,
    frameH,
    isSingleCrop,
    panelH,
    topPanelY,
    bottomPanelY,
    baseFaceRadius,
    baseZoomFactor,
    maxZoomFactor,
    marginSize,
    enterCount,
    exitCount,
    minSegment,
  } = svgContent;

  // Center of each panel for face placement
  const panelCenterX = frameX + frameW / 2;
  const topFaceCenterY = topPanelY + panelH / 2;
  const bottomFaceCenterY = bottomPanelY + panelH / 2;

  // Crop rectangle dimensions based on zoom
  const baseCropW = frameW * baseZoomFactor;
  const baseCropH = panelH * baseZoomFactor;
  const maxCropW = frameW * maxZoomFactor;
  const maxCropH = panelH * maxZoomFactor;

  return (
    <svg
      data-testid="auto-grid-preview"
      viewBox="0 0 300 200"
      className="w-full"
      style={{ maxHeight: 200 }}
      aria-label="Auto Grid parameter preview"
    >
      {/* 9:16 Output frame */}
      <rect
        x={frameX}
        y={frameY}
        width={frameW}
        height={frameH}
        rx={4}
        fill="#18181b"
        stroke="#3f3f46"
        strokeWidth={1.5}
      />

      {isSingleCrop ? (
        /* ─── Single-Crop Mode ─────────────────────────────────── */
        <>
          {/* Single face circle centered in full frame */}
          <circle
            cx={panelCenterX}
            cy={frameY + frameH / 2}
            r={baseFaceRadius + 4}
            fill="none"
            stroke="#10b981"
            strokeWidth={1.5}
          />
          {/* Face fill */}
          <circle
            cx={panelCenterX}
            cy={frameY + frameH / 2}
            r={baseFaceRadius}
            fill="#10b981"
            fillOpacity={0.15}
          />

          {/* Base zoom crop rectangle (full frame single crop) */}
          <rect
            x={panelCenterX - (frameW * baseZoomFactor) / 2}
            y={frameY + frameH / 2 - (frameH * baseZoomFactor) / 2}
            width={frameW * baseZoomFactor}
            height={frameH * baseZoomFactor}
            rx={3}
            fill="none"
            stroke="#10b981"
            strokeWidth={1.2}
          />

          {/* Label */}
          <text
            x={frameX + frameW / 2}
            y={frameY + frameH - 8}
            textAnchor="middle"
            fill="#71717a"
            fontSize={8}
            fontFamily="sans-serif"
          >
            single crop
          </text>

          {/* Dominance indicator (left side) */}
          <text
            x={20}
            y={frameY + frameH / 2 - 10}
            fill="#71717a"
            fontSize={8}
            fontFamily="sans-serif"
          >
            dominance
          </text>
          <text
            x={20}
            y={frameY + frameH / 2 + 2}
            fill="#a1a1aa"
            fontSize={9}
            fontFamily="sans-serif"
            fontWeight="bold"
          >
            {dominanceSingleCrop.toFixed(2)}
          </text>
          <text
            x={20}
            y={frameY + frameH / 2 + 14}
            fill="#10b981"
            fontSize={7}
            fontFamily="sans-serif"
          >
            {">"} 0.75 → single
          </text>
        </>
      ) : (
        /* ─── Grid / Split-Screen Mode ─────────────────────────── */
        <>
          {/* Horizontal divider between panels */}
          <line
            x1={frameX}
            y1={topPanelY + panelH + 2}
            x2={frameX + frameW}
            y2={topPanelY + panelH + 2}
            stroke="#3b82f6"
            strokeWidth={1.5}
          />

          {/* ── Top Panel ── */}
          {/* Face circle */}
          <circle
            cx={panelCenterX}
            cy={topFaceCenterY}
            r={baseFaceRadius}
            fill="#10b981"
            fillOpacity={0.15}
            stroke="#10b981"
            strokeWidth={1}
          />

          {/* Base zoom crop (solid emerald) */}
          <rect
            x={panelCenterX - baseCropW / 2}
            y={topFaceCenterY - baseCropH / 2}
            width={baseCropW}
            height={baseCropH}
            rx={2}
            fill="none"
            stroke="#10b981"
            strokeWidth={1.2}
          />

          {/* Max zoom crop (dashed blue) */}
          <rect
            x={panelCenterX - maxCropW / 2}
            y={topFaceCenterY - maxCropH / 2}
            width={maxCropW}
            height={maxCropH}
            rx={2}
            fill="none"
            stroke="#3b82f6"
            strokeWidth={1}
            strokeDasharray="3 2"
          />

          {/* Margin indicators (top panel) */}
          {/* Left margin */}
          <line
            x1={panelCenterX - baseFaceRadius - marginSize}
            y1={topFaceCenterY - 4}
            x2={panelCenterX - baseFaceRadius}
            y2={topFaceCenterY - 4}
            stroke="#f59e0b"
            strokeWidth={1}
            markerEnd="url(#marginArrow)"
          />
          {/* Right margin */}
          <line
            x1={panelCenterX + baseFaceRadius}
            y1={topFaceCenterY - 4}
            x2={panelCenterX + baseFaceRadius + marginSize}
            y2={topFaceCenterY - 4}
            stroke="#f59e0b"
            strokeWidth={1}
            markerStart="url(#marginArrowReverse)"
          />

          {/* ── Bottom Panel ── */}
          {/* Face circle */}
          <circle
            cx={panelCenterX}
            cy={bottomFaceCenterY}
            r={baseFaceRadius}
            fill="#10b981"
            fillOpacity={0.15}
            stroke="#10b981"
            strokeWidth={1}
          />

          {/* Base zoom crop (solid emerald) */}
          <rect
            x={panelCenterX - baseCropW / 2}
            y={bottomFaceCenterY - baseCropH / 2}
            width={baseCropW}
            height={baseCropH}
            rx={2}
            fill="none"
            stroke="#10b981"
            strokeWidth={1.2}
          />

          {/* Max zoom crop (dashed blue) */}
          <rect
            x={panelCenterX - maxCropW / 2}
            y={bottomFaceCenterY - maxCropH / 2}
            width={maxCropW}
            height={maxCropH}
            rx={2}
            fill="none"
            stroke="#3b82f6"
            strokeWidth={1}
            strokeDasharray="3 2"
          />

          {/* Margin indicators (bottom panel) */}
          <line
            x1={panelCenterX - baseFaceRadius - marginSize}
            y1={bottomFaceCenterY - 4}
            x2={panelCenterX - baseFaceRadius}
            y2={bottomFaceCenterY - 4}
            stroke="#f59e0b"
            strokeWidth={1}
            markerEnd="url(#marginArrow)"
          />
          <line
            x1={panelCenterX + baseFaceRadius}
            y1={bottomFaceCenterY - 4}
            x2={panelCenterX + baseFaceRadius + marginSize}
            y2={bottomFaceCenterY - 4}
            stroke="#f59e0b"
            strokeWidth={1}
            markerStart="url(#marginArrowReverse)"
          />

          {/* Dominance indicator (left side) */}
          <text
            x={20}
            y={frameY + 20}
            fill="#71717a"
            fontSize={8}
            fontFamily="sans-serif"
          >
            dominance
          </text>
          <text
            x={20}
            y={frameY + 32}
            fill="#a1a1aa"
            fontSize={9}
            fontFamily="sans-serif"
            fontWeight="bold"
          >
            {dominanceSingleCrop.toFixed(2)}
          </text>
          <text
            x={20}
            y={frameY + 44}
            fill="#3b82f6"
            fontSize={7}
            fontFamily="sans-serif"
          >
            {"≤"} 0.75 → grid
          </text>

          {/* Legend (left side) */}
          <line x1={20} y1={frameY + 60} x2={38} y2={frameY + 60} stroke="#10b981" strokeWidth={1.2} />
          <text x={41} y={frameY + 63} fill="#71717a" fontSize={7} fontFamily="sans-serif">
            base zoom
          </text>

          <line x1={20} y1={frameY + 72} x2={38} y2={frameY + 72} stroke="#3b82f6" strokeWidth={1} strokeDasharray="3 2" />
          <text x={41} y={frameY + 75} fill="#71717a" fontSize={7} fontFamily="sans-serif">
            max zoom
          </text>

          <line x1={20} y1={frameY + 84} x2={38} y2={frameY + 84} stroke="#f59e0b" strokeWidth={1} />
          <text x={41} y={frameY + 87} fill="#71717a" fontSize={7} fontFamily="sans-serif">
            margin
          </text>
        </>
      )}

      {/* ─── Bottom Timing Indicators ─────────────────────────────── */}
      <text
        x={20}
        y={192}
        fill="#71717a"
        fontSize={7.5}
        fontFamily="sans-serif"
      >
        enter: {enterCount}f | exit: {exitCount}f | min: {minSegment.toFixed(1)}s
      </text>

      {/* Confirmation dots (enter samples) */}
      {Array.from({ length: Math.min(enterCount, 8) }, (_, i) => (
        <circle
          key={`enter-${i}`}
          cx={220 + i * 8}
          cy={189}
          r={2.5}
          fill="#10b981"
          fillOpacity={0.8}
        />
      ))}

      {/* Arrow markers for margin indicators */}
      <defs>
        <marker
          id="marginArrow"
          markerWidth={5}
          markerHeight={4}
          refX={4}
          refY={2}
          orient="auto"
        >
          <path d="M0,0 L5,2 L0,4" fill="#f59e0b" />
        </marker>
        <marker
          id="marginArrowReverse"
          markerWidth={5}
          markerHeight={4}
          refX={1}
          refY={2}
          orient="auto"
        >
          <path d="M5,0 L0,2 L5,4" fill="#f59e0b" />
        </marker>
      </defs>
    </svg>
  );
}
