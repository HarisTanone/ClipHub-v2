import { useState, useCallback, useMemo } from "react";
import { ImageUploadZone } from "./ImageUploadZone";
import { AspectRatioSelector } from "./AspectRatioSelector";
import { type ReframeTuning } from "./CropOverlay";
import {
  computeSingleCropRect,
  computeGridCropRects,
  cropRectToBackgroundStyle,
  effectiveGridZoom,
  prefersSingleCrop,
  type AspectRatio,
} from "./reframeGeometry";

// ─── Types ───────────────────────────────────────────────────────────────────

interface ImagePreviewPanelProps {
  reframeTuning: ReframeTuning;
  aspectRatio: AspectRatio;
  onAspectRatioChange: (ratio: AspectRatio) => void;
}

// ─── Aspect Ratio CSS Map ────────────────────────────────────────────────────

const ASPECT_RATIO_CSS: Record<AspectRatio, string> = {
  "9:16": "9/16",
  "16:9": "16/9",
  "1:1": "1/1",
};

type PreviewMode = "single" | "grid";

// ─── Reframe Preview Renderer ────────────────────────────────────────────────
// Reshapes the uploaded image using the EXACT crop geometry the production
// reframe engine would apply (see reframeGeometry.ts). Each visible panel shows
// a sub-region of the source scaled to fill — identical to the FFmpeg
// `crop=...,scale=...` the renderer performs.

interface ReframePreviewRendererProps {
  uploadedImage: string;
  imageWidth: number;
  imageHeight: number;
  aspectRatio: AspectRatio;
  reframeTuning: ReframeTuning;
  mode: PreviewMode;
}

function ReframePreviewRenderer({
  uploadedImage,
  imageWidth,
  imageHeight,
  aspectRatio,
  reframeTuning,
  mode,
}: ReframePreviewRendererProps) {
  const aspectRatioCSS = ASPECT_RATIO_CSS[aspectRatio];

  const { singleStyle, topStyle, bottomStyle } = useMemo(() => {
    const w = imageWidth || 1920;
    const h = imageHeight || 1080;

    const singleRect = computeSingleCropRect(w, h, aspectRatio);
    const grid = computeGridCropRects(w, h, reframeTuning);

    return {
      singleStyle: {
        backgroundImage: `url(${uploadedImage})`,
        ...cropRectToBackgroundStyle(singleRect),
      } as React.CSSProperties,
      topStyle: {
        backgroundImage: `url(${uploadedImage})`,
        ...cropRectToBackgroundStyle(grid.top),
      } as React.CSSProperties,
      bottomStyle: {
        backgroundImage: `url(${uploadedImage})`,
        ...cropRectToBackgroundStyle(grid.bottom),
      } as React.CSSProperties,
    };
  }, [uploadedImage, imageWidth, imageHeight, aspectRatio, reframeTuning]);

  if (mode === "single") {
    return (
      <div
        className="bg-black rounded-lg overflow-hidden mx-auto"
        style={{ aspectRatio: aspectRatioCSS, maxHeight: "500px" }}
      >
        <div
          style={{
            width: "100%",
            height: "100%",
            transition: "background-position 0.3s ease, background-size 0.3s ease",
            ...singleStyle,
          }}
        />
      </div>
    );
  }

  // Grid mode: two stacked panels (top = left speaker, bottom = right speaker).
  return (
    <div
      className="bg-black rounded-lg overflow-hidden mx-auto flex flex-col"
      style={{ aspectRatio: aspectRatioCSS, maxHeight: "500px" }}
    >
      {/* Top panel — LEFT speaker */}
      <div
        style={{
          flex: 1,
          overflow: "hidden",
          transition: "background-position 0.3s ease, background-size 0.3s ease",
          ...topStyle,
        }}
      />

      {/* Divider */}
      <div style={{ height: "2px", background: "#1a1a1a", flexShrink: 0 }} />

      {/* Bottom panel — RIGHT speaker */}
      <div
        style={{
          flex: 1,
          overflow: "hidden",
          transition: "background-position 0.3s ease, background-size 0.3s ease",
          ...bottomStyle,
        }}
      />
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export function ImagePreviewPanel({
  reframeTuning,
  aspectRatio,
  onAspectRatioChange,
}: ImagePreviewPanelProps) {
  const [uploadedImage, setUploadedImage] = useState<string | null>(null);
  const [imageDims, setImageDims] = useState<{ w: number; h: number } | null>(null);
  // The static preview cannot know the runtime dominance ratio, so we let the
  // user flip between the two framing modes the engine can produce. The default
  // follows the configured threshold (`prefersSingleCrop`).
  const [modeOverride, setModeOverride] = useState<PreviewMode | null>(null);

  const mode: PreviewMode =
    modeOverride ?? (prefersSingleCrop(reframeTuning) ? "single" : "grid");

  const handleUpload = useCallback((file: File) => {
    const objectUrl = URL.createObjectURL(file);
    // Read natural dimensions so crop math uses the real source size.
    const img = new Image();
    img.onload = () => setImageDims({ w: img.naturalWidth, h: img.naturalHeight });
    img.src = objectUrl;
    setUploadedImage(objectUrl);
  }, []);

  const handleRemoveImage = useCallback(() => {
    if (uploadedImage) {
      URL.revokeObjectURL(uploadedImage);
    }
    setUploadedImage(null);
    setImageDims(null);
  }, [uploadedImage]);

  const gridZoom = effectiveGridZoom(reframeTuning);

  return (
    <div className="sticky top-4 space-y-3">
      {/* Aspect Ratio Selector */}
      <AspectRatioSelector value={aspectRatio} onChange={onAspectRatioChange} />

      {/* Mode toggle (only meaningful once an image is uploaded) */}
      {uploadedImage && (
        <div className="flex items-center gap-1 bg-zinc-800/80 rounded-lg p-0.5 w-fit">
          {(["single", "grid"] as PreviewMode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setModeOverride(m)}
              className={
                "px-3 py-1 text-[11px] font-medium rounded-md transition-colors " +
                (mode === m
                  ? "bg-zinc-700 text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300")
              }
            >
              {m === "single" ? "Single Crop" : "Grid Mode"}
            </button>
          ))}
        </div>
      )}

      {/* Preview Container */}
      <div className="relative rounded-lg overflow-hidden bg-zinc-900 border border-zinc-800">
        {uploadedImage ? (
          <div className="p-2">
            <ReframePreviewRenderer
              uploadedImage={uploadedImage}
              imageWidth={imageDims?.w ?? 1920}
              imageHeight={imageDims?.h ?? 1080}
              aspectRatio={aspectRatio}
              reframeTuning={reframeTuning}
              mode={mode}
            />
          </div>
        ) : (
          <ImageUploadZone onUpload={handleUpload} />
        )}
      </div>

      {/* Mode Label + Remove Button */}
      {uploadedImage && (
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-zinc-500 font-mono">
            {mode === "single"
              ? `Single Crop · ${aspectRatio}`
              : `Grid Mode · ${aspectRatio} · zoom ${gridZoom.toFixed(2)}x`}
          </span>
          <button
            type="button"
            onClick={handleRemoveImage}
            className="text-[10px] text-zinc-600 hover:text-red-400 transition-colors"
          >
            Hapus gambar
          </button>
        </div>
      )}
    </div>
  );
}
