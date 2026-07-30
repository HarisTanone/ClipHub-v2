import { Check, ImagePlus, Upload } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import {
  CANVAS_TEMPLATES,
  buildCanvasConfig,
  gradientCss,
  type CanvasAccent,
  type CanvasTemplate,
} from "@/lib/canvasTemplates";

function Accents({ accents }: { accents: CanvasAccent[] }) {
  return (
    <>
      {accents.map((a, i) => {
        if (a.type === "soft-glow" || a.type === "blob") {
          return (
            <div
              key={i}
              className="absolute pointer-events-none"
              style={{
                left: `${(a.x || 0) * 100}%`,
                top: `${(a.y || 0) * 100}%`,
                width: `${(a.r || 0.2) * 200}%`,
                height: `${(a.r || 0.2) * 200}%`,
                transform: "translate(-50%, -50%)",
                borderRadius: "50%",
                background: a.color,
                filter: "blur(10px)",
              }}
            />
          );
        }
        if (a.type === "bar") {
          return (
            <div
              key={i}
              className="absolute pointer-events-none rounded-full"
              style={{
                left: `${(a.x || 0) * 100}%`,
                top: `${(a.y || 0) * 100}%`,
                width: `${(a.w || 0.1) * 100}%`,
                height: `${Math.max((a.h || 0.01) * 100, 1.5)}%`,
                background: a.color,
              }}
            />
          );
        }
        if (a.type === "line") {
          const dx = ((a.x2 || 0) - (a.x1 || 0)) * 100;
          const dy = ((a.y2 || 0) - (a.y1 || 0)) * 100;
          const len = Math.sqrt(dx * dx + dy * dy);
          const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
          return (
            <div
              key={i}
              className="absolute pointer-events-none rounded-full"
              style={{
                left: `${(a.x1 || 0) * 100}%`,
                top: `${(a.y1 || 0) * 100}%`,
                width: `${len}%`,
                height: a.w || 2,
                background: a.color,
                transformOrigin: "0 50%",
                transform: `rotate(${angle}deg)`,
              }}
            />
          );
        }
        if (a.type === "ring") {
          return (
            <div
              key={i}
              className="absolute pointer-events-none rounded-full"
              style={{
                left: `${(a.x || 0) * 100}%`,
                top: `${(a.y || 0) * 100}%`,
                width: `${(a.r || 0.3) * 200}%`,
                height: `${(a.r || 0.3) * 200}%`,
                transform: "translate(-50%, -50%)",
                border: `${a.stroke || 1}px solid ${a.color}`,
              }}
            />
          );
        }
        if (a.type === "frame") {
          return (
            <div
              key={i}
              className="absolute pointer-events-none rounded"
              style={{
                inset: `${(a.inset || 0.03) * 100}%`,
                border: `${a.stroke || 1}px solid ${a.color}`,
              }}
            />
          );
        }
        return null;
      })}
    </>
  );
}

/** Mini thumbnail of a template composition (bg + footage placeholder). */
export function TemplateThumb({
  template,
  aspectRatio,
  selected,
  onClick,
}: {
  template: CanvasTemplate;
  aspectRatio: "16:9" | "1:1";
  selected?: boolean;
  onClick?: () => void;
}) {
  const layout = template.layout[aspectRatio] || template.layout["16:9"];
  const vignette = template.background.vignette ?? 0;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-lg border text-left transition-all",
        selected
          ? "border-emerald-500 ring-1 ring-emerald-500/40 shadow-[0_0_0_1px_rgba(16,185,129,0.25)]"
          : "border-zinc-800 hover:border-zinc-600",
      )}
    >
      <div
        className={cn(
          "relative w-full overflow-hidden bg-zinc-950",
          aspectRatio === "1:1" ? "aspect-square" : "aspect-video",
        )}
        style={{ background: gradientCss(template.background) }}
      >
        <Accents accents={template.accents} />
        {vignette > 0 && (
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background: `radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,${vignette}) 100%)`,
            }}
          />
        )}
        {/* Footage placeholder — person/video area */}
        <div
          className="absolute overflow-hidden bg-zinc-700/80"
          style={{
            left: `${layout.videoX * 100}%`,
            top: `${layout.videoY * 100}%`,
            width: `${layout.videoW * 100}%`,
            height: `${layout.videoH * 100}%`,
            borderRadius: Math.max(4, (layout.borderRadius || 12) / 3),
            boxShadow: "0 4px 16px rgba(0,0,0,0.45)",
          }}
        >
          <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-b from-zinc-600/40 to-zinc-800/80">
            <div className="flex flex-col items-center gap-0.5 opacity-70">
              <div className="h-5 w-5 rounded-full bg-zinc-400/50" />
              <div className="h-6 w-8 rounded-t-full bg-zinc-400/40" />
            </div>
          </div>
        </div>
        {selected && (
          <div className="absolute right-1.5 top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500 text-white shadow">
            <Check className="h-3 w-3" strokeWidth={3} />
          </div>
        )}
      </div>
      <div className="px-2 py-1.5">
        <p className={cn("truncate text-[10px] font-medium", selected ? "text-emerald-300" : "text-zinc-300")}>
          {template.name}
        </p>
        <p className="truncate text-[9px] text-zinc-600">{template.category}</p>
      </div>
    </button>
  );
}

export type BackgroundMode = "template" | "upload";

interface BackgroundTemplateSectionProps {
  aspectRatio: "16:9" | "1:1";
  mode: BackgroundMode;
  onModeChange: (mode: BackgroundMode) => void;
  templateId: string;
  onTemplateChange: (id: string) => void;
  uploadPreviewUrl: string | null;
  onUpload: (file: File) => void;
  onClearUpload: () => void;
}

export function BackgroundTemplateSection({
  aspectRatio,
  mode,
  onModeChange,
  templateId,
  onTemplateChange,
  uploadPreviewUrl,
  onUpload,
  onClearUpload,
}: BackgroundTemplateSectionProps) {
  return (
    <div className="space-y-2.5">
      <label className="block text-[10px] font-medium uppercase tracking-wider text-zinc-500">Background</label>
      <div className="grid grid-cols-2 gap-1.5">
        <button
          type="button"
          onClick={() => onModeChange("template")}
          className={cn(
            "rounded-lg border px-2.5 py-2 text-left transition-all",
            mode === "template"
              ? "border-emerald-500/60 bg-emerald-500/8 text-emerald-400"
              : "border-zinc-800 text-zinc-500 hover:border-zinc-700",
          )}
        >
          <p className="text-[11px] font-medium">Template</p>
          <p className="text-[9px] opacity-70">Desain layout siap pakai</p>
        </button>
        <button
          type="button"
          onClick={() => onModeChange("upload")}
          className={cn(
            "rounded-lg border px-2.5 py-2 text-left transition-all",
            mode === "upload"
              ? "border-emerald-500/60 bg-emerald-500/8 text-emerald-400"
              : "border-zinc-800 text-zinc-500 hover:border-zinc-700",
          )}
        >
          <p className="text-[11px] font-medium flex items-center gap-1">
            <Upload className="h-3 w-3" /> Upload
          </p>
          <p className="text-[9px] opacity-70">Background sendiri</p>
        </button>
      </div>

      {mode === "template" && (
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-2">
          {CANVAS_TEMPLATES.map((t) => (
            <TemplateThumb
              key={t.id}
              template={t}
              aspectRatio={aspectRatio}
              selected={templateId === t.id}
              onClick={() => onTemplateChange(t.id)}
            />
          ))}
        </div>
      )}

      {mode === "upload" && (
        <div className="space-y-2">
          {uploadPreviewUrl ? (
            <div className="relative overflow-hidden rounded-lg border border-zinc-800">
              <div className={cn("relative w-full", aspectRatio === "1:1" ? "aspect-square" : "aspect-video")}>
                <img src={uploadPreviewUrl} alt="Background" className="absolute inset-0 h-full w-full object-cover" />
                <div className="absolute inset-[12%] overflow-hidden rounded-md border border-white/10 bg-zinc-800/70 shadow-lg">
                  <div className="flex h-full items-center justify-center">
                    <div className="flex flex-col items-center gap-0.5 opacity-60">
                      <div className="h-6 w-6 rounded-full bg-zinc-400/50" />
                      <div className="h-8 w-10 rounded-t-full bg-zinc-400/40" />
                    </div>
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={onClearUpload}
                className="absolute right-2 top-2 rounded-md bg-black/60 px-2 py-1 text-[10px] text-zinc-200 hover:bg-black/80"
              >
                Ganti
              </button>
            </div>
          ) : (
            <label className="flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-zinc-700 bg-zinc-950/50 px-3 py-6 text-zinc-500 transition-colors hover:border-emerald-500/40 hover:text-emerald-400">
              <ImagePlus className="h-5 w-5" />
              <span className="text-[11px] font-medium">Upload Background</span>
              <span className="text-[9px] text-zinc-600">JPG, PNG, WEBP</span>
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) onUpload(f);
                  e.target.value = "";
                }}
              />
            </label>
          )}
        </div>
      )}
    </div>
  );
}

/** Live canvas frame used inside style previews (outer shell always phone-like). */
export function CanvasLiveFrame({
  aspectRatio,
  canvas,
  thumbnailUrl,
  children,
  className,
}: {
  aspectRatio: string;
  canvas: ReturnType<typeof buildCanvasConfig>;
  thumbnailUrl?: string;
  children?: ReactNode;
  className?: string;
}) {
  // Outer UI always 9:16 phone frame; inner composition matches selected aspect
  const isPortrait = aspectRatio === "9:16" || !canvas;
  return (
    <div
      className={cn(
        "relative w-full overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950",
        className,
      )}
      style={{ aspectRatio: "9/16" }}
    >
      {isPortrait ? (
        <div className="absolute inset-0">
          {thumbnailUrl ? (
            <img src={thumbnailUrl} alt="" className="absolute inset-0 h-full w-full object-cover" />
          ) : (
            <div className="absolute inset-0 bg-zinc-900" />
          )}
          {children}
        </div>
      ) : (
        <div className="absolute inset-0 flex items-center justify-center p-3">
          <div
            className="relative overflow-hidden rounded-md shadow-2xl"
            style={{
              width: aspectRatio === "1:1" ? "88%" : "100%",
              aspectRatio: aspectRatio === "1:1" ? "1/1" : "16/9",
              background: gradientCss(canvas?.background),
            }}
          >
            {canvas?.backgroundImageUrl || canvas?.background?.imageUrl ? (
              <img
                src={(canvas.backgroundImageUrl || canvas.background.imageUrl) as string}
                alt=""
                className="absolute inset-0 h-full w-full object-cover"
              />
            ) : null}
            <Accents accents={canvas?.accents || []} />
            {(canvas?.background.vignette || 0) > 0 && (
              <div
                className="absolute inset-0 pointer-events-none"
                style={{
                  background: `radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,${canvas?.background.vignette}) 100%)`,
                }}
              />
            )}
            <div
              className="absolute overflow-hidden bg-zinc-800"
              style={{
                left: `${(canvas?.layout.videoX || 0.1) * 100}%`,
                top: `${(canvas?.layout.videoY || 0.1) * 100}%`,
                width: `${(canvas?.layout.videoW || 0.8) * 100}%`,
                height: `${(canvas?.layout.videoH || 0.8) * 100}%`,
                borderRadius: Math.max(4, (canvas?.layout.borderRadius || 12) / 2),
                boxShadow: canvas?.layout.shadow,
              }}
            >
              {thumbnailUrl ? (
                <img src={thumbnailUrl} alt="" className="absolute inset-0 h-full w-full object-cover" />
              ) : (
                <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-b from-zinc-600/30 to-zinc-900/80">
                  <div className="flex flex-col items-center gap-1 opacity-60">
                    <div className="h-8 w-8 rounded-full bg-zinc-400/40" />
                    <div className="h-10 w-14 rounded-t-full bg-zinc-400/30" />
                  </div>
                </div>
              )}
              {/* Scale children into footage slot */}
              <div className="absolute inset-0 pointer-events-none">{children}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
