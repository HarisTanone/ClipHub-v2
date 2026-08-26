import React from "react";
import { cn } from "@/lib/utils";
import { gradientCss, type CanvasConfig } from "@/lib/canvasTemplates";
import { CanvasAccents } from "@/components/BackgroundTemplateSection";

export function CanvasPreviewFrame({
  canvas,
  thumbnailUrl,
  children,
  className,
  aspectRatio = "9/16",
  dimOverlay = false,
}: {
  canvas?: CanvasConfig | null;
  thumbnailUrl?: string;
  children?: React.ReactNode;
  className?: string;
  aspectRatio?: string;
  dimOverlay?: boolean;
}) {
  return (
    <div
      className={cn("relative w-full max-w-[220px] bg-zinc-900 rounded-lg overflow-hidden border border-zinc-800 shrink-0", className)}
      style={{ aspectRatio }}
    >
      {canvas ? (
        <div className="absolute inset-0" style={{ background: gradientCss(canvas.background) }}>
          {(canvas.backgroundImageUrl || canvas.background?.imageUrl) && (
            <img
              src={(canvas.backgroundImageUrl || canvas.background.imageUrl) as string}
              alt=""
              className="absolute inset-0 h-full w-full object-cover"
            />
          )}
          <CanvasAccents accents={canvas.accents || []} />
          {(canvas.background.vignette || 0) > 0 && (
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                background: `radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,${canvas.background.vignette}) 100%)`,
              }}
            />
          )}
          <div
            className="absolute overflow-hidden bg-zinc-800"
            style={{
              left: `${canvas.layout.videoX * 100}%`,
              top: `${canvas.layout.videoY * 100}%`,
              width: `${canvas.layout.videoW * 100}%`,
              height: `${canvas.layout.videoH * 100}%`,
              borderRadius: canvas.layout.borderRadius || 0,
              boxShadow: canvas.layout.shadow,
            }}
          >
            {thumbnailUrl && (
              <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-contain" />
            )}
            {dimOverlay && <div className="absolute inset-0 bg-black/40" />}
          </div>
          {children}
        </div>
      ) : (
        <>
          {thumbnailUrl ? (
            <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-cover" />
          ) : (
            <div className="absolute inset-0 bg-gradient-to-br from-zinc-700 to-zinc-950" />
          )}
          {dimOverlay && <div className="absolute inset-0 bg-black/40" />}
          {children}
        </>
      )}
    </div>
  );
}
