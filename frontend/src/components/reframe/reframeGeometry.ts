import { type ReframeTuning } from "./CropOverlay";

// ─────────────────────────────────────────────────────────────────────────────
// Reframe geometry helpers.
//
// These functions mirror the crop math used by the PRODUCTION reframe engine
// (`backend/src/infrastructure/podcast_reframe_engine.py`) so the on-screen
// preview reshapes an uploaded image exactly the way the rendered clip will.
//
// Key production facts encoded here:
//   • The rendered output is ALWAYS 9:16 portrait.
//   • Single-crop mode:
//       crop_w = height * 9 / 16  (a 9:16 sub-rectangle of the source),
//       crop_h = height (full source height).
//       The crop is centered on the speaker, then scaled to fill the 9:16 frame.
//       NO extra zoom is applied in single-crop mode.
//   • Grid mode (2 people): two 9:8 panels stacked vertically (each panel is
//       exactly half of a 9:16 frame → 9:8). Each panel's source crop is:
//         base_crop_w = min(width, height * 9 / 8)
//         crop_w      = base_crop_w / grid_zoom
//         crop_h      = crop_w * 8 / 9
//       where grid_zoom starts at GRID_BASE_ZOOM (and can grow toward
//       GRID_MAX_ZOOM when isolating faces). For a static preview we use the
//       base zoom. The face is placed with the eyes ~38% down the panel.
// ─────────────────────────────────────────────────────────────────────────────

export type AspectRatio = "9:16" | "16:9" | "1:1";

/** Numerator/denominator of the target output ratio (width / height). */
const OUTPUT_RATIO: Record<AspectRatio, number> = {
  "9:16": 9 / 16,
  "16:9": 16 / 9,
  "1:1": 1,
};

/** A crop rectangle expressed as fractions (0..1) of the source image. */
export interface CropRect {
  /** Left edge as fraction of source width. */
  x: number;
  /** Top edge as fraction of source height. */
  y: number;
  /** Width as fraction of source width. */
  w: number;
  /** Height as fraction of source height. */
  h: number;
}

/**
 * Decide whether the engine would use single-crop framing for the current
 * config. In production the switch is driven by the runtime dominance ratio
 * (`dominant_ratio >= DOMINANCE_SINGLE_CROP`). The static preview has no
 * runtime dominance, so we treat the configured threshold as the intent:
 * a high threshold means "prefer grid" (only switch to single when one speaker
 * is overwhelmingly dominant), a low threshold means "prefer single crop".
 *
 * We surface both panels via a mode the caller can override, but by default we
 * show grid unless the threshold is set very high (>= 0.9), which effectively
 * disables grid.
 */
export function prefersSingleCrop(tuning: ReframeTuning): boolean {
  return tuning.dominance_single_crop >= 0.9;
}

/**
 * Compute the single-crop source rectangle for the given output aspect ratio.
 * Mirrors: crop_w = height * targetRatio, crop_h = height, centered.
 * When the source is TALLER than the target ratio we instead constrain by
 * width (crop_h = width / targetRatio), matching a cover-style fit.
 */
export function computeSingleCropRect(
  sourceW: number,
  sourceH: number,
  aspect: AspectRatio,
): CropRect {
  const targetRatio = OUTPUT_RATIO[aspect];
  const sourceRatio = sourceW / sourceH;

  let cropW: number;
  let cropH: number;
  if (sourceRatio > targetRatio) {
    // Source is wider than target → constrain by height (pillar crop).
    cropH = sourceH;
    cropW = cropH * targetRatio;
  } else {
    // Source is taller than target → constrain by width (letter crop).
    cropW = sourceW;
    cropH = cropW / targetRatio;
  }

  const x = (sourceW - cropW) / 2;
  const y = (sourceH - cropH) / 2;

  return {
    x: x / sourceW,
    y: y / sourceH,
    w: cropW / sourceW,
    h: cropH / sourceH,
  };
}

/**
 * Compute the two grid-panel source rectangles (top + bottom). Each panel is a
 * 9:8 window (half of 9:16). Mirrors the production `_compute_grid_geometry`
 * base-zoom sizing:
 *   base_crop_w = min(width, height * 9 / 8)
 *   crop_w      = base_crop_w / grid_zoom
 *   crop_h      = crop_w * 8 / 9
 *
 * For the preview we horizontally place the top panel toward the left third and
 * the bottom panel toward the right third — the two typical speaker positions —
 * and vertically place the crop so the face sits ~38% down (production
 * `_clamp_grid_y`).
 */
export function computeGridCropRects(
  sourceW: number,
  sourceH: number,
  tuning: ReframeTuning,
): { top: CropRect; bottom: CropRect } {
  const zoom = Math.max(1, tuning.grid_base_zoom);

  // Panel aspect is 9:8 (w:h). base_crop_w = min(width, height * 9/8).
  const baseCropW = Math.min(sourceW, sourceH * (9 / 8));
  let cropW = baseCropW / zoom;
  let cropH = cropW * (8 / 9);

  // Clamp so the crop fits inside the source.
  if (cropH > sourceH) {
    cropH = sourceH;
    cropW = cropH * (9 / 8);
  }
  if (cropW > sourceW) {
    cropW = sourceW;
    cropH = cropW * (8 / 9);
  }

  // Horizontal placement: left speaker ~1/3, right speaker ~2/3.
  const leftCenterX = sourceW * (1 / 3);
  const rightCenterX = sourceW * (2 / 3);

  const clampX = (centerX: number) =>
    Math.max(0, Math.min(centerX - cropW / 2, sourceW - cropW));

  // Vertical placement: eyes ~38% down the panel (production uses face_y - 0.38*crop_h,
  // with faces typically ~38% from the top of frame).
  const faceY = sourceH * 0.38;
  const cropY = Math.max(0, Math.min(faceY - cropH * 0.38, sourceH - cropH));

  const toFrac = (px: number, py: number): CropRect => ({
    x: px / sourceW,
    y: py / sourceH,
    w: cropW / sourceW,
    h: cropH / sourceH,
  });

  return {
    top: toFrac(clampX(leftCenterX), cropY),
    bottom: toFrac(clampX(rightCenterX), cropY),
  };
}

/**
 * Convert a source-relative CropRect into the CSS needed to render that crop
 * scaled to fill a panel of the given on-screen dimensions using a background
 * image. This reproduces "crop sub-region then scale to fill" exactly.
 */
export function cropRectToBackgroundStyle(
  crop: CropRect,
): React.CSSProperties {
  // background-size: the full image is scaled so the crop window fills 100%
  // of the panel. If the crop is `w` fraction wide, the image must be
  // (1 / w) * 100% wide.
  const bgWidthPct = (1 / crop.w) * 100;
  const bgHeightPct = (1 / crop.h) * 100;

  // background-position: place the crop's top-left at the panel's top-left.
  // With background-position percentages, P% aligns the P% point of the image
  // with the P% point of the container. The visible fraction is (1 - w), so:
  //   posX = crop.x / (1 - crop.w)
  const posXPct = crop.w < 1 ? (crop.x / (1 - crop.w)) * 100 : 0;
  const posYPct = crop.h < 1 ? (crop.y / (1 - crop.h)) * 100 : 0;

  return {
    backgroundSize: `${bgWidthPct}% ${bgHeightPct}%`,
    backgroundPosition: `${posXPct}% ${posYPct}%`,
    backgroundRepeat: "no-repeat",
  };
}

/** Effective grid zoom used by the preview (clamped to >= 1). */
export function effectiveGridZoom(tuning: ReframeTuning): number {
  return Math.max(1, tuning.grid_base_zoom);
}
