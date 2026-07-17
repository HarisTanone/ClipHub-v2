import { useState, useCallback } from "react";
import { ImageUploadZone } from "./ImageUploadZone";
import { AspectRatioSelector } from "./AspectRatioSelector";
import { CropOverlay, type ReframeTuning } from "./CropOverlay";

// ─── Types ───────────────────────────────────────────────────────────────────

interface ImagePreviewPanelProps {
  reframeTuning: ReframeTuning;
  aspectRatio: "9:16" | "16:9" | "1:1";
  onAspectRatioChange: (ratio: "9:16" | "16:9" | "1:1") => void;
}

// ─── Component ───────────────────────────────────────────────────────────────

export function ImagePreviewPanel({
  reframeTuning,
  aspectRatio,
  onAspectRatioChange,
}: ImagePreviewPanelProps) {
  const [uploadedImage, setUploadedImage] = useState<string | null>(null);
  const [imageDimensions, setImageDimensions] = useState<{
    width: number;
    height: number;
  } | null>(null);

  const handleUpload = useCallback((file: File) => {
    const objectUrl = URL.createObjectURL(file);
    setUploadedImage(objectUrl);
  }, []);

  const handleImageLoad = useCallback(
    (e: React.SyntheticEvent<HTMLImageElement>) => {
      const img = e.currentTarget;
      setImageDimensions({
        width: img.naturalWidth,
        height: img.naturalHeight,
      });
    },
    []
  );

  const handleRemoveImage = useCallback(() => {
    if (uploadedImage) {
      URL.revokeObjectURL(uploadedImage);
    }
    setUploadedImage(null);
    setImageDimensions(null);
  }, [uploadedImage]);

  return (
    <div className="sticky top-4 space-y-3">
      {/* Aspect Ratio Selector */}
      <AspectRatioSelector value={aspectRatio} onChange={onAspectRatioChange} />

      {/* Image Container */}
      <div className="relative rounded-lg overflow-hidden bg-zinc-900 border border-zinc-800">
        {uploadedImage ? (
          <>
            <img
              src={uploadedImage}
              alt="Preview frame"
              onLoad={handleImageLoad}
              className="w-full h-auto object-contain"
            />
            {imageDimensions && (
              <CropOverlay
                imageWidth={imageDimensions.width}
                imageHeight={imageDimensions.height}
                aspectRatio={aspectRatio}
                reframeTuning={reframeTuning}
              />
            )}
          </>
        ) : (
          <ImageUploadZone onUpload={handleUpload} />
        )}
      </div>

      {/* Remove Button */}
      {uploadedImage && (
        <button
          type="button"
          onClick={handleRemoveImage}
          className="text-[10px] text-zinc-600 hover:text-red-400 transition-colors"
        >
          Hapus gambar
        </button>
      )}
    </div>
  );
}
