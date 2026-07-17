import { useState, useCallback, useMemo } from "react";
import { ImageUploadZone } from "./ImageUploadZone";
import { AspectRatioSelector } from "./AspectRatioSelector";
import { type ReframeTuning } from "./CropOverlay";

// ─── Types ───────────────────────────────────────────────────────────────────

interface ImagePreviewPanelProps {
  reframeTuning: ReframeTuning;
  aspectRatio: "9:16" | "16:9" | "1:1";
  onAspectRatioChange: (ratio: "9:16" | "16:9" | "1:1") => void;
}

// ─── Aspect Ratio CSS Map ────────────────────────────────────────────────────

const ASPECT_RATIO_CSS: Record<"9:16" | "16:9" | "1:1", string> = {
  "9:16": "9/16",
  "16:9": "16/9",
  "1:1": "1/1",
};

// ─── Reframe Preview Renderer ────────────────────────────────────────────────

interface ReframePreviewRendererProps {
  uploadedImage: string;
  aspectRatio: "9:16" | "16:9" | "1:1";
  reframeTuning: ReframeTuning;
}

function ReframePreviewRenderer({
  uploadedImage,
  aspectRatio,
  reframeTuning,
}: ReframePreviewRendererProps) {
  const isSingleCrop = reframeTuning.dominance_single_crop > 0.75;

  // Calculate effective zoom considering face margin
  const effectiveZoom = useMemo(() => {
    const baseZoom = reframeTuning.grid_base_zoom;
    // Face margin reduces effective zoom slightly (more breathing room = less zoom)
    const marginFactor = 1 - reframeTuning.grid_face_margin * 0.3;
    return baseZoom * marginFactor;
  }, [reframeTuning.grid_base_zoom, reframeTuning.grid_face_margin]);

  const panelStyles = useMemo(() => {
    const transition =
      "transform 0.3s ease, object-position 0.3s ease, opacity 0.3s ease";

    if (isSingleCrop) {
      // Single crop: one zoomed view centered on face area
      return {
        single: {
          transform: `scale(${effectiveZoom})`,
          transformOrigin: "center center",
          width: "100%" as const,
          height: "100%" as const,
          objectFit: "cover" as const,
          transition,
        },
      };
    } else {
      // Grid mode: two panels, left speaker and right speaker (side by side in typical podcast)
      return {
        top: {
          transform: `scale(${effectiveZoom * 1.2})`,
          transformOrigin: "30% center",
          width: "100%" as const,
          height: "100%" as const,
          objectFit: "cover" as const,
          transition,
        },
        bottom: {
          transform: `scale(${effectiveZoom * 1.2})`,
          transformOrigin: "70% center",
          width: "100%" as const,
          height: "100%" as const,
          objectFit: "cover" as const,
          transition,
        },
      };
    }
  }, [isSingleCrop, effectiveZoom]);

  const aspectRatioCSS = ASPECT_RATIO_CSS[aspectRatio];

  if (isSingleCrop) {
    // Single crop mode: one panel with zoomed image
    return (
      <div
        className="relative w-full mx-auto border border-emerald-500/40 rounded-md"
        style={{ aspectRatio: aspectRatioCSS, maxHeight: "500px" }}
      >
        <div className="absolute inset-0 overflow-hidden rounded-md">
          <img
            src={uploadedImage}
            alt="Reframe preview — single crop"
            style={panelStyles.single}
            draggable={false}
          />
        </div>
        {/* Max zoom indicator overlay */}
        <div
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
          style={{ opacity: 0.4 }}
        >
          <div
            className="border border-dashed border-blue-400 rounded-sm"
            style={{
              width: `${(1 / reframeTuning.grid_max_zoom) * 100}%`,
              height: `${(1 / reframeTuning.grid_max_zoom) * 100}%`,
              transition: "width 0.3s ease, height 0.3s ease",
            }}
          />
        </div>
      </div>
    );
  }

  // Grid mode: two panels stacked vertically
  return (
    <div
      className="relative w-full mx-auto border border-emerald-500/40 rounded-md"
      style={{ aspectRatio: aspectRatioCSS, maxHeight: "500px" }}
    >
      <div
        className="absolute inset-0 flex flex-col rounded-md"
        style={{ gap: "2px" }}
      >
        {/* Top panel — speaker 1 */}
        <div className="flex-1 overflow-hidden rounded-t-md relative">
          <img
            src={uploadedImage}
            alt="Reframe preview — top speaker"
            style={(panelStyles as { top: React.CSSProperties; bottom: React.CSSProperties }).top}
            draggable={false}
          />
          {/* Max zoom indicator */}
          <div
            className="absolute inset-0 flex items-center justify-center pointer-events-none"
            style={{ opacity: 0.3 }}
          >
            <div
              className="border border-dashed border-blue-400 rounded-sm"
              style={{
                width: `${(1 / reframeTuning.grid_max_zoom) * 100}%`,
                height: `${(1 / reframeTuning.grid_max_zoom) * 100}%`,
                transition: "width 0.3s ease, height 0.3s ease",
              }}
            />
          </div>
        </div>

        {/* Divider line */}
        <div className="h-[2px] bg-blue-500/60 flex-shrink-0" />

        {/* Bottom panel — speaker 2 */}
        <div className="flex-1 overflow-hidden rounded-b-md relative">
          <img
            src={uploadedImage}
            alt="Reframe preview — bottom speaker"
            style={(panelStyles as { top: React.CSSProperties; bottom: React.CSSProperties }).bottom}
            draggable={false}
          />
          {/* Max zoom indicator */}
          <div
            className="absolute inset-0 flex items-center justify-center pointer-events-none"
            style={{ opacity: 0.3 }}
          >
            <div
              className="border border-dashed border-blue-400 rounded-sm"
              style={{
                width: `${(1 / reframeTuning.grid_max_zoom) * 100}%`,
                height: `${(1 / reframeTuning.grid_max_zoom) * 100}%`,
                transition: "width 0.3s ease, height 0.3s ease",
              }}
            />
          </div>
        </div>
      </div>
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

  const handleUpload = useCallback((file: File) => {
    const objectUrl = URL.createObjectURL(file);
    setUploadedImage(objectUrl);
  }, []);

  const handleRemoveImage = useCallback(() => {
    if (uploadedImage) {
      URL.revokeObjectURL(uploadedImage);
    }
    setUploadedImage(null);
  }, [uploadedImage]);

  // Determine current mode label
  const modeLabel = useMemo(() => {
    if (reframeTuning.dominance_single_crop > 0.75) {
      return "Single Crop";
    }
    return "Grid Mode (2 speakers)";
  }, [reframeTuning.dominance_single_crop]);

  return (
    <div className="sticky top-4 space-y-3">
      {/* Aspect Ratio Selector */}
      <AspectRatioSelector value={aspectRatio} onChange={onAspectRatioChange} />

      {/* Image Container */}
      <div className="relative rounded-lg overflow-hidden bg-zinc-900 border border-zinc-800">
        {uploadedImage ? (
          <div className="p-2">
            <ReframePreviewRenderer
              uploadedImage={uploadedImage}
              aspectRatio={aspectRatio}
              reframeTuning={reframeTuning}
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
            {modeLabel} · zoom {reframeTuning.grid_base_zoom.toFixed(2)}x
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
