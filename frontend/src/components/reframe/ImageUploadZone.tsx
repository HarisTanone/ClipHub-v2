import { useRef, useState, useCallback } from "react";
import { Upload } from "lucide-react";

interface ImageUploadZoneProps {
  onUpload: (file: File) => void;
}

const ACCEPTED_TYPES = ["image/jpeg", "image/png"];

export function ImageUploadZone({ onUpload }: ImageUploadZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isValidFile = (file: File): boolean => {
    return ACCEPTED_TYPES.includes(file.type);
  };

  const handleFile = useCallback(
    (file: File) => {
      if (isValidFile(file)) {
        onUpload(file);
      } else {
        console.warn(
          `[ImageUploadZone] Rejected file type: ${file.type}. Only JPEG and PNG are accepted.`
        );
      }
    },
    [onUpload]
  );

  const handleDragEnter = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);

      const file = e.dataTransfer.files[0];
      if (file) {
        handleFile(file);
      }
    },
    [handleFile]
  );

  const handleClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        handleFile(file);
      }
      // Reset input so the same file can be re-selected
      e.target.value = "";
    },
    [handleFile]
  );

  return (
    <div
      data-testid="image-upload-zone"
      onClick={handleClick}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`
        flex flex-col items-center justify-center gap-2
        w-full min-h-[300px] rounded-lg cursor-pointer
        border-2 border-dashed transition-colors
        ${isDragOver
          ? "border-emerald-500 bg-emerald-500/5"
          : "border-zinc-700 bg-zinc-900/50 hover:border-zinc-600"
        }
      `}
    >
      <Upload className="w-8 h-8 text-zinc-500" />
      <p className="text-[11px] text-zinc-500">
        Drop gambar atau klik untuk browse
      </p>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png"
        onChange={handleFileChange}
        className="hidden"
        aria-label="Upload image"
      />
    </div>
  );
}
