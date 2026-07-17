/**
 * SamplingDetectionPreview — SVG schematic showing face detection overlay.
 *
 * Reactive preview that visualizes how Sampling & Detection parameters affect
 * the face detection pipeline. Shows face bounding boxes (confident vs uncertain),
 * min/max size indicators, and a timeline with sample frame markers.
 */

import { useMemo } from "react";

interface SamplingDetectionPreviewProps {
  faceConfidence: number;
  minFaceSizeRatio: number;
  maxFaceSizeRatio: number;
  sampleIntervalSec: number;
  maxSamples: number;
}

export function SamplingDetectionPreview({
  faceConfidence,
  minFaceSizeRatio,
  maxFaceSizeRatio,
  sampleIntervalSec,
  maxSamples,
}: SamplingDetectionPreviewProps) {
  const svgContent = useMemo(() => {
    // Frame dimensions (16:9 aspect ratio within SVG viewBox)
    const frameX = 20;
    const frameY = 10;
    const frameW = 260;
    const frameH = 146;

    // Determine number of bounding boxes based on confidence threshold
    // Lower confidence = more boxes (including uncertain ones)
    const confidentBoxCount = faceConfidence > 0.7 ? 1 : faceConfidence > 0.4 ? 2 : 3;
    const uncertainBoxCount = faceConfidence < 0.6 ? 2 : faceConfidence < 0.8 ? 1 : 0;

    // Face bounding boxes scaled by min/max face size ratio
    const minBoxSize = Math.max(20, minFaceSizeRatio * frameW * 0.8);
    const maxBoxSize = Math.min(frameH * 0.7, maxFaceSizeRatio * frameW * 0.8);

    // Generate confident face boxes
    const confidentBoxes = Array.from({ length: confidentBoxCount }, (_, i) => {
      const size = minBoxSize + ((maxBoxSize - minBoxSize) * (confidentBoxCount - i)) / confidentBoxCount;
      const x = frameX + 30 + i * 70;
      const y = frameY + 20 + i * 15;
      return { x, y, size: Math.min(size, frameH - 40), confident: true };
    });

    // Generate uncertain (dashed) face boxes
    const uncertainBoxes = Array.from({ length: uncertainBoxCount }, (_, i) => {
      const size = minBoxSize * 0.7;
      const x = frameX + frameW - 80 - i * 50;
      const y = frameY + frameH - size - 20 - i * 10;
      return { x, y, size: Math.min(size, 40), confident: false };
    });

    // Timeline markers — spacing reflects sampleIntervalSec, count reflects maxSamples
    const timelineY = frameY + frameH + 18;
    const timelineW = frameW;
    // More interval = fewer ticks; cap by maxSamples
    const tickCount = Math.min(maxSamples, Math.max(3, Math.floor(20 / sampleIntervalSec)));
    const tickSpacing = timelineW / (tickCount + 1);

    const ticks = Array.from({ length: tickCount }, (_, i) => ({
      x: frameX + tickSpacing * (i + 1),
    }));

    return {
      frameX,
      frameY,
      frameW,
      frameH,
      confidentBoxes,
      uncertainBoxes,
      minBoxSize,
      maxBoxSize,
      timelineY,
      timelineW,
      ticks,
      tickCount,
    };
  }, [faceConfidence, minFaceSizeRatio, maxFaceSizeRatio, sampleIntervalSec, maxSamples]);

  const {
    frameX,
    frameY,
    frameW,
    frameH,
    confidentBoxes,
    uncertainBoxes,
    minBoxSize,
    maxBoxSize,
    timelineY,
    timelineW,
    ticks,
  } = svgContent;

  return (
    <svg
      data-testid="sampling-detection-preview"
      viewBox="0 0 300 200"
      className="w-full"
      style={{ maxHeight: 200 }}
      aria-label="Sampling & Detection parameter preview"
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

      {/* Confident face bounding boxes (solid green) */}
      {confidentBoxes.map((box, i) => (
        <rect
          key={`conf-${i}`}
          x={box.x}
          y={box.y}
          width={box.size}
          height={box.size * 1.2}
          rx={2}
          fill="none"
          stroke="#10b981"
          strokeWidth={1.5}
        />
      ))}

      {/* Uncertain face bounding boxes (dashed amber) */}
      {uncertainBoxes.map((box, i) => (
        <rect
          key={`uncert-${i}`}
          x={box.x}
          y={box.y}
          width={box.size}
          height={box.size * 1.2}
          rx={2}
          fill="none"
          stroke="#f59e0b"
          strokeWidth={1.2}
          strokeDasharray="4 3"
        />
      ))}

      {/* Min size indicator */}
      <line
        x1={frameX + frameW - 45}
        y1={frameY + 8}
        x2={frameX + frameW - 45 + minBoxSize * 0.4}
        y2={frameY + 8}
        stroke="#a1a1aa"
        strokeWidth={1}
        markerEnd="url(#arrowMin)"
      />
      <text
        x={frameX + frameW - 45}
        y={frameY + 6}
        fill="#71717a"
        fontSize={8}
        fontFamily="sans-serif"
      >
        min size
      </text>

      {/* Max size indicator */}
      <line
        x1={frameX + 8}
        y1={frameY + frameH - 8}
        x2={frameX + 8 + maxBoxSize * 0.35}
        y2={frameY + frameH - 8}
        stroke="#a1a1aa"
        strokeWidth={1}
        markerEnd="url(#arrowMax)"
      />
      <text
        x={frameX + 8}
        y={frameY + frameH - 12}
        fill="#71717a"
        fontSize={8}
        fontFamily="sans-serif"
      >
        max size
      </text>

      {/* Confidence label */}
      <text
        x={frameX + 6}
        y={frameY + 14}
        fill="#71717a"
        fontSize={9}
        fontFamily="sans-serif"
      >
        conf: {faceConfidence.toFixed(2)}
      </text>

      {/* Timeline bar */}
      <line
        x1={frameX}
        y1={timelineY}
        x2={frameX + timelineW}
        y2={timelineY}
        stroke="#3f3f46"
        strokeWidth={1.5}
      />

      {/* Timeline tick marks */}
      {ticks.map((tick, i) => (
        <line
          key={`tick-${i}`}
          x1={tick.x}
          y1={timelineY - 4}
          x2={tick.x}
          y2={timelineY + 4}
          stroke="#10b981"
          strokeWidth={1.5}
        />
      ))}

      {/* Timeline labels */}
      <text
        x={frameX}
        y={timelineY + 14}
        fill="#71717a"
        fontSize={8}
        fontFamily="sans-serif"
      >
        interval: {sampleIntervalSec.toFixed(1)}s
      </text>
      <text
        x={frameX + timelineW - 60}
        y={timelineY + 14}
        fill="#71717a"
        fontSize={8}
        fontFamily="sans-serif"
      >
        samples: {ticks.length}
      </text>

      {/* Arrow markers for size indicators */}
      <defs>
        <marker
          id="arrowMin"
          markerWidth={6}
          markerHeight={4}
          refX={5}
          refY={2}
          orient="auto"
        >
          <path d="M0,0 L6,2 L0,4" fill="#a1a1aa" />
        </marker>
        <marker
          id="arrowMax"
          markerWidth={6}
          markerHeight={4}
          refX={5}
          refY={2}
          orient="auto"
        >
          <path d="M0,0 L6,2 L0,4" fill="#a1a1aa" />
        </marker>
      </defs>
    </svg>
  );
}
