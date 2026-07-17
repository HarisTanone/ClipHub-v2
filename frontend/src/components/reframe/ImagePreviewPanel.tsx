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
// Simulates the ACTUAL reframe engine output:
// - Black background (like real 1080x1920 output)
// - objectFit: cover + objectPosition for real crop behavior
// - Grid mode splits into two panels (top/bottom), each cropped to a speaker

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
  const aspectRatioCSS = ASPECT_RATIO_CSS[aspectRatio];

  const zoomFactor = reframeTuning.grid_base_zoom;
  const margin = reframeTuning.grid_face_margin;

  if (isSingleCrop) {
    // Single crop mode: one panel showing cropped center of image
    return (
      <div
        className="bg-black rounded-lg overflow-hidden mx-auto"
        style={{ aspectRatio: aspectRatioCSS, maxHeight: "500px" }}
      >
        <div style={{ width: "100%", height: "100%", overflow: "hidden" }}>
          <img
            src={uploadedImage}
            alt="Reframe preview — single crop"
            draggable={false}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              objectPosition: "center center",
              transform: `scale(${zoomFactor})`,
              transformOrigin: "center center",
              transition: "transform 0.3s ease, object-position 0.3s ease",
            }}
          />
        </div>
      </div>
    );
  }

  // Grid mode: two stacked panels, each cropped to a different speaker
  // Top panel → left speaker (~25% horizontal position)
  // Bottom panel → right speaker (~75% horizontal position)
  const leftSpeakerPos = Math.max(0, Math.min(100, 25 - margin * 10));
  const rightSpeakerPos = Math.max(0, Math.min(100, 75 + margin * 10));

  return (
    <div
      className="bg-black rounded-lg overflow-hidden mx-auto flex flex-col"
      style={{ aspectRatio: aspectRatioCSS, maxHeight: "500px" }}
    >
      {/* Top panel — LEFT speaker */}
      <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
        <img
          src={uploadedImage}
          alt="Reframe preview — top speaker"
          draggable={false}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            objectPosition: `${leftSpeakerPos}% center`,
            transform: `scale(${zoomFactor * 1.1})`,
            transformOrigin: "25% center",
            transition: "all 0.3s ease",
          }}
        />
      </div>

      {/* Divider */}
      <div
        style={{ height: "2px", background: "#1a1a1a", flexShrink: 0 }}
      />

      {/* Bottom panel — RIGHT speaker */}
      <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
        <img
          src={uploadedImage}
          alt="Reframe preview — bottom speaker"
          draggable={false}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            objectPosition: `${rightSpeakerPos}% center`,
            transform: `scale(${zoomFactor * 1.1})`,
            transformOrigin: "75% center",
            transition: "all 0.3s ease",
          }}
        />
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
    return "Grid Mode";
  }, [reframeTuning.dominance_single_crop]);

  return (
    <div className="sticky top-4 space-y-3">
      {/* Aspect Ratio Selector */}
      <AspectRatioSelector value={aspectRatio} onChange={onAspectRatioChange} />

      {/* Preview Container */}
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
