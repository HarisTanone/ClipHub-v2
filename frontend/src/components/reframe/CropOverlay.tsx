import { useMemo } from "react";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ReframeTuning {
  sample_interval_sec: number;
  max_samples: number;
  face_confidence: number;
  min_face_size_ratio: number;
  max_face_size_ratio: number;
  min_separation_ratio: number;
  min_coexist_ratio: number;
  dominance_single_crop: number;
  grid_base_zoom: number;
  grid_max_zoom: number;
  grid_face_margin: number;
  grid_enter_samples: number;
  grid_exit_samples: number;
  min_grid_segment_seconds: number;
  min_face_area_px: number;
  min_area_ratio_to_max: number;
  min_frame_ratio: number;
  ghost_iou_threshold: number;
  ghost_center_dist_ratio: number;
  ghost_center_dist_broad: number;
  min_pair_size_ratio: number;
}

type AspectRatio = "9:16" | "16:9" | "1:1";

interface CropOverlayProps {
  imageWidth: number;
  imageHeight: number;
  aspectRatio: AspectRatio;
  reframeTuning: ReframeTuning;
}

// ─── Face Box Types ──────────────────────────────────────────────────────────

interface FaceBox {
  x: number;
  y: number;
  w: number;
  h: number;
  label: "valid" | "ghost" | "filtered";
}

// ─── Aspect Ratio Map ────────────────────────────────────────────────────────

const RATIO_MAP: Record<AspectRatio, number> = {
  "9:16": 9 / 16,
  "16:9": 16 / 9,
  "1:1": 1,
};

// ─── Component ───────────────────────────────────────────────────────────────

export function CropOverlay({
  imageWidth,
  imageHeight,
  aspectRatio,
  reframeTuning,
}: CropOverlayProps) {
  const geometry = useMemo(() => {
    // 1. Calculate aspect ratio crop frame
    const targetRatio = RATIO_MAP[aspectRatio];

    let cropW: number;
    let cropH: number;
    if (imageWidth / imageHeight > targetRatio) {
      // Image is wider — fit by height
      cropH = imageHeight;
      cropW = cropH * targetRatio;
    } else {
      // Image is taller — fit by width
      cropW = imageWidth;
      cropH = cropW / targetRatio;
    }

    const cropX = (imageWidth - cropW) / 2;
    const cropY = (imageHeight - cropH) / 2;

    // 2. Determine mode
    const isSingleCrop = reframeTuning.dominance_single_crop > 0.75;

    // 3. Calculate inner crop rectangle(s) based on zoom
    const baseZoomFactor = 1 / reframeTuning.grid_base_zoom;
    const maxZoomFactor = 1 / reframeTuning.grid_max_zoom;

    let singleCrop: { x: number; y: number; w: number; h: number } | null =
      null;
    let gridPanels: {
      top: { x: number; y: number; w: number; h: number };
      bottom: { x: number; y: number; w: number; h: number };
      splitY: number;
      maxZoomTop: { x: number; y: number; w: number; h: number };
      maxZoomBottom: { x: number; y: number; w: number; h: number };
      marginTop: number;
      marginBottom: number;
    } | null = null;

    if (isSingleCrop) {
      // Single centered crop rectangle inside the crop frame
      const innerW = cropW * baseZoomFactor;
      const innerH = cropH * baseZoomFactor;
      singleCrop = {
        x: cropX + (cropW - innerW) / 2,
        y: cropY + (cropH - innerH) / 2,
        w: innerW,
        h: innerH,
      };
    } else {
      // Grid mode: top and bottom panels
      const panelH = cropH / 2;
      const splitY = cropY + panelH;

      // Base zoom crop per panel
      const panelCropW = cropW * baseZoomFactor;
      const panelCropH = panelH * baseZoomFactor;

      const topCrop = {
        x: cropX + (cropW - panelCropW) / 2,
        y: cropY + (panelH - panelCropH) / 2,
        w: panelCropW,
        h: panelCropH,
      };

      const bottomCrop = {
        x: cropX + (cropW - panelCropW) / 2,
        y: splitY + (panelH - panelCropH) / 2,
        w: panelCropW,
        h: panelCropH,
      };

      // Max zoom rectangles (dashed)
      const maxZoomW = cropW * maxZoomFactor;
      const maxZoomH = panelH * maxZoomFactor;

      const maxZoomTop = {
        x: cropX + (cropW - maxZoomW) / 2,
        y: cropY + (panelH - maxZoomH) / 2,
        w: maxZoomW,
        h: maxZoomH,
      };

      const maxZoomBottom = {
        x: cropX + (cropW - maxZoomW) / 2,
        y: splitY + (panelH - maxZoomH) / 2,
        w: maxZoomW,
        h: maxZoomH,
      };

      // Margin indicators (relative to panel)
      const marginPx = reframeTuning.grid_face_margin * panelCropH;

      gridPanels = {
        top: topCrop,
        bottom: bottomCrop,
        splitY,
        maxZoomTop,
        maxZoomBottom,
        marginTop: marginPx,
        marginBottom: marginPx,
      };
    }

    // 4. Generate simulated face bounding boxes for ghost detection
    const maxFaceArea = cropW * cropH * 0.04; // ~4% of crop area for largest face
    const rawFaces = [
      { x: cropX + cropW * 0.2, y: cropY + cropH * 0.2, size: 1.0 },
      { x: cropX + cropW * 0.6, y: cropY + cropH * 0.3, size: 0.5 },
      { x: cropX + cropW * 0.8, y: cropY + cropH * 0.6, size: 0.2 },
      { x: cropX + cropW * 0.15, y: cropY + cropH * 0.7, size: 0.12 },
    ];

    // Normalize min_face_area_px relative to image dimensions
    // The param is in absolute pixels for a 1920x1080 frame; normalize to overlay coordinate space
    const referenceArea = 1920 * 1080;
    const imageArea = imageWidth * imageHeight;
    const normalizedMinFaceArea =
      reframeTuning.min_face_area_px * (imageArea / referenceArea);

    const faceBoxes: FaceBox[] = rawFaces.map((f) => {
      const pixelArea = f.size * maxFaceArea;
      const faceSize = Math.sqrt(pixelArea);
      const areaRatio = f.size;

      let label: FaceBox["label"];
      if (
        pixelArea < normalizedMinFaceArea ||
        areaRatio < reframeTuning.min_area_ratio_to_max
      ) {
        label = "ghost";
      } else if (areaRatio < reframeTuning.min_area_ratio_to_max * 1.5) {
        label = "filtered";
      } else {
        label = "valid";
      }

      return {
        x: f.x - faceSize / 2,
        y: f.y - faceSize / 2,
        w: faceSize,
        h: faceSize,
        label,
      };
    });

    return {
      cropX,
      cropY,
      cropW,
      cropH,
      isSingleCrop,
      singleCrop,
      gridPanels,
      faceBoxes,
    };
  }, [imageWidth, imageHeight, aspectRatio, reframeTuning]);

  const { cropX, cropY, cropW, cropH, isSingleCrop, singleCrop, gridPanels, faceBoxes } =
    geometry;

  // ─── SVG path for darkened area outside crop zone (cutout) ─────────────────
  const darkOverlayPath = [
    // Outer rectangle (full image)
    `M 0 0 H ${imageWidth} V ${imageHeight} H 0 Z`,
    // Inner cutout (crop zone) — drawn counter-clockwise for even-odd fill
    `M ${cropX} ${cropY} V ${cropY + cropH} H ${cropX + cropW} V ${cropY} Z`,
  ].join(" ");

  return (
    <svg
      data-testid="crop-overlay"
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
      viewBox={`0 0 ${imageWidth} ${imageHeight}`}
      preserveAspectRatio="xMidYMid meet"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Darkened overlay outside crop zone */}
      <path
        d={darkOverlayPath}
        fill="rgba(0,0,0,0.5)"
        fillRule="evenodd"
      />

      {/* Crop frame border */}
      <rect
        x={cropX}
        y={cropY}
        width={cropW}
        height={cropH}
        fill="none"
        stroke="#10b981"
        strokeWidth={2}
      />

      {/* ─── Single-Crop Mode ─────────────────────────────────────────── */}
      {isSingleCrop && singleCrop && (
        <>
          {/* Inner crop rectangle */}
          <rect
            x={singleCrop.x}
            y={singleCrop.y}
            width={singleCrop.w}
            height={singleCrop.h}
            fill="none"
            stroke="#10b981"
            strokeWidth={1.5}
          />
          {/* Simulated face circle at center */}
          <circle
            cx={singleCrop.x + singleCrop.w / 2}
            cy={singleCrop.y + singleCrop.h * 0.35}
            r={Math.min(singleCrop.w, singleCrop.h) * 0.12}
            fill="none"
            stroke="#10b981"
            strokeWidth={1}
            strokeDasharray="4 2"
          />
        </>
      )}

      {/* ─── Grid Mode ────────────────────────────────────────────────── */}
      {!isSingleCrop && gridPanels && (
        <>
          {/* Horizontal split-line */}
          <line
            x1={cropX}
            y1={gridPanels.splitY}
            x2={cropX + cropW}
            y2={gridPanels.splitY}
            stroke="#3b82f6"
            strokeWidth={2}
          />

          {/* Top panel: base zoom crop */}
          <rect
            x={gridPanels.top.x}
            y={gridPanels.top.y}
            width={gridPanels.top.w}
            height={gridPanels.top.h}
            fill="none"
            stroke="#10b981"
            strokeWidth={1.5}
          />

          {/* Bottom panel: base zoom crop */}
          <rect
            x={gridPanels.bottom.x}
            y={gridPanels.bottom.y}
            width={gridPanels.bottom.w}
            height={gridPanels.bottom.h}
            fill="none"
            stroke="#10b981"
            strokeWidth={1.5}
          />

          {/* Top panel: max zoom rectangle (dashed, blue) */}
          <rect
            x={gridPanels.maxZoomTop.x}
            y={gridPanels.maxZoomTop.y}
            width={gridPanels.maxZoomTop.w}
            height={gridPanels.maxZoomTop.h}
            fill="none"
            stroke="#3b82f6"
            strokeWidth={1}
            strokeDasharray="6 3"
          />

          {/* Bottom panel: max zoom rectangle (dashed, blue) */}
          <rect
            x={gridPanels.maxZoomBottom.x}
            y={gridPanels.maxZoomBottom.y}
            width={gridPanels.maxZoomBottom.w}
            height={gridPanels.maxZoomBottom.h}
            fill="none"
            stroke="#3b82f6"
            strokeWidth={1}
            strokeDasharray="6 3"
          />

          {/* Margin indicators (amber) — top panel */}
          <line
            x1={gridPanels.top.x}
            y1={gridPanels.top.y + gridPanels.marginTop}
            x2={gridPanels.top.x + gridPanels.top.w}
            y2={gridPanels.top.y + gridPanels.marginTop}
            stroke="#f59e0b"
            strokeWidth={1}
            strokeDasharray="4 2"
          />
          <line
            x1={gridPanels.top.x}
            y1={gridPanels.top.y + gridPanels.top.h - gridPanels.marginTop}
            x2={gridPanels.top.x + gridPanels.top.w}
            y2={gridPanels.top.y + gridPanels.top.h - gridPanels.marginTop}
            stroke="#f59e0b"
            strokeWidth={1}
            strokeDasharray="4 2"
          />

          {/* Margin indicators (amber) — bottom panel */}
          <line
            x1={gridPanels.bottom.x}
            y1={gridPanels.bottom.y + gridPanels.marginBottom}
            x2={gridPanels.bottom.x + gridPanels.bottom.w}
            y2={gridPanels.bottom.y + gridPanels.marginBottom}
            stroke="#f59e0b"
            strokeWidth={1}
            strokeDasharray="4 2"
          />
          <line
            x1={gridPanels.bottom.x}
            y1={gridPanels.bottom.y + gridPanels.bottom.h - gridPanels.marginBottom}
            x2={gridPanels.bottom.x + gridPanels.bottom.w}
            y2={gridPanels.bottom.y + gridPanels.bottom.h - gridPanels.marginBottom}
            stroke="#f59e0b"
            strokeWidth={1}
            strokeDasharray="4 2"
          />

          {/* Simulated face circles in each panel */}
          <circle
            cx={gridPanels.top.x + gridPanels.top.w / 2}
            cy={gridPanels.top.y + gridPanels.top.h * 0.4}
            r={Math.min(gridPanels.top.w, gridPanels.top.h) * 0.12}
            fill="none"
            stroke="#10b981"
            strokeWidth={1}
            strokeDasharray="4 2"
          />
          <circle
            cx={gridPanels.bottom.x + gridPanels.bottom.w / 2}
            cy={gridPanels.bottom.y + gridPanels.bottom.h * 0.4}
            r={Math.min(gridPanels.bottom.w, gridPanels.bottom.h) * 0.12}
            fill="none"
            stroke="#10b981"
            strokeWidth={1}
            strokeDasharray="4 2"
          />
        </>
      )}

      {/* ─── Ghost Detection Face Boxes ───────────────────────────────── */}
      {faceBoxes.map((face, i) => {
        const strokeColor =
          face.label === "valid"
            ? "#10b981"
            : face.label === "ghost"
            ? "#ef4444"
            : "#f59e0b";
        const isDashed = face.label !== "valid";

        return (
          <g key={i}>
            <rect
              x={face.x}
              y={face.y}
              width={face.w}
              height={face.h}
              fill="none"
              stroke={strokeColor}
              strokeWidth={1.5}
              strokeDasharray={isDashed ? "5 3" : undefined}
            />
            <text
              x={face.x + face.w / 2}
              y={face.y - 4}
              textAnchor="middle"
              fill={strokeColor}
              fontSize={Math.max(10, face.w * 0.15)}
              fontFamily="sans-serif"
            >
              {face.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
