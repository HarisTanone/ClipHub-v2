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

/** Exported for StyleEditor live preview ≡ Remotion bake. */
export function CanvasAccents({ accents }: { accents: CanvasAccent[] }) {
  return <Accents accents={accents} />;
}

/** Mini thumb: always 9:16 phone frame with content slot + template fill.
 *  When a video thumbnail is available it is shown in the content slot (same as
 *  the Live Preview) instead of a generic silhouette placeholder. */
export function TemplateThumb({
  template,
  aspectRatio,
  selected,
  onClick,
  thumbnailUrl,
}: {
  template: CanvasTemplate;
  aspectRatio: "16:9" | "1:1";
  selected?: boolean;
  onClick?: () => void;
  thumbnailUrl?: string;
}) {
  const layout = template.layout[aspectRatio] || template.layout["16:9"];
  const vignette = template.background.vignette ?? 0;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative flex w-full flex-col overflow-hidden rounded-lg border text-left transition-all",
        selected
          ? "border-emerald-500 ring-1 ring-emerald-500/40 shadow-[0_0_0_1px_rgba(16,185,129,0.25)]"
          : "border-zinc-800 hover:border-zinc-600",
      )}
    >
      {/* Always phone 9:16 — matches final TikTok output */}
      <div
        className="relative w-full overflow-hidden bg-zinc-950 aspect-[9/16]"
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
        {/* Content slot — 16:9 or 1:1 band, template fills top/bottom */}
        <div
          className="absolute overflow-hidden bg-zinc-700/80"
          style={{
            left: `${layout.videoX * 100}%`,
            top: `${layout.videoY * 100}%`,
            width: `${layout.videoW * 100}%`,
            height: `${layout.videoH * 100}%`,
            borderRadius: Math.max(0, (layout.borderRadius || 0) / 3),
            boxShadow: "0 4px 16px rgba(0,0,0,0.45)",
          }}
        >
          {thumbnailUrl ? (
            <img src={thumbnailUrl} alt="" className="absolute inset-0 h-full w-full object-contain" />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-b from-zinc-600/40 to-zinc-800/80">
              <div className="flex flex-col items-center gap-0.5 opacity-70">
                <div className="h-3 w-3 rounded-full bg-zinc-400/50" />
                <div className="h-4 w-6 rounded-t-full bg-zinc-400/40" />
              </div>
            </div>
          )}
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
  /** Real video thumbnail — shown inside the content slot of template thumbs
   *  and the upload preview so all previews match the Live Preview. */
  thumbnailUrl?: string;
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
  thumbnailUrl,
}: BackgroundTemplateSectionProps) {
  return (
    <div className="space-y-2.5">
      <div>
        <label className="block text-[10px] font-medium uppercase tracking-wider text-zinc-500">
          Background Template
        </label>
        <p className="mt-0.5 text-[9px] text-zinc-600 leading-snug">
          Output TikTok = 9:16. Video {aspectRatio} di tengah; template isi area atas & bawah (bukan black bar).
        </p>
      </div>
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
          <p className="text-[9px] opacity-70">Theme + border siap pakai</p>
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
        <div className="flex gap-1.5 overflow-x-auto pb-1 snap-x mobile-h-scroll">
          {CANVAS_TEMPLATES.map((t) => (
            <div
              key={t.id}
              className="shrink-0 w-[calc((100%-0.75rem)/3)] min-w-[88px] snap-start"
            >
              <TemplateThumb
                template={t}
                aspectRatio={aspectRatio}
                selected={templateId === t.id}
                onClick={() => onTemplateChange(t.id)}
                thumbnailUrl={thumbnailUrl}
              />
            </div>
          ))}
        </div>
      )}

      {mode === "upload" && (
        <div className="space-y-2">
          {uploadPreviewUrl ? (
            <div className="relative overflow-hidden rounded-lg border border-zinc-800">
              <div className="relative w-full aspect-[9/16]">
                <img src={uploadPreviewUrl} alt="Background" className="absolute inset-0 h-full w-full object-cover" />
                {/* Content slot preview */}
                <div
                  className="absolute overflow-hidden rounded-sm border border-white/10 bg-zinc-800/70 shadow-lg"
                  style={
                    aspectRatio === "1:1"
                      ? { left: "4%", top: "24%", width: "92%", height: "52%" }
                      : { left: "0%", top: "34%", width: "100%", height: "32%" }
                  }
                >
                  {thumbnailUrl ? (
                    <img src={thumbnailUrl} alt="" className="absolute inset-0 h-full w-full object-contain" />
                  ) : (
                    <div className="flex h-full items-center justify-center">
                      <div className="flex flex-col items-center gap-0.5 opacity-60">
                        <div className="h-4 w-4 rounded-full bg-zinc-400/50" />
                        <div className="h-5 w-8 rounded-t-full bg-zinc-400/40" />
                      </div>
                    </div>
                  )}
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
              <span className="text-[9px] text-zinc-600">JPG, PNG, WEBP — full 9:16 canvas</span>
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

/**
 * Live canvas frame for style previews.
 * Outer shell always 9:16 (TikTok). When canvas config present, template fills
 * full frame and content sits in video slot — preview ≡ final bake.
 */
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
        /* Full 9:16 canvas with template — matches Remotion bake 1:1 */
        <div className="absolute inset-0" style={{ background: gradientCss(canvas?.background) }}>
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
              left: `${(canvas?.layout.videoX || 0) * 100}%`,
              top: `${(canvas?.layout.videoY || 0.34) * 100}%`,
              width: `${(canvas?.layout.videoW || 1) * 100}%`,
              height: `${(canvas?.layout.videoH || 0.32) * 100}%`,
              borderRadius: canvas?.layout.borderRadius || 0,
              boxShadow: canvas?.layout.shadow,
            }}
          >
            {thumbnailUrl ? (
              <img src={thumbnailUrl} alt="" className="absolute inset-0 h-full w-full object-contain" />
            ) : (
              <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-b from-zinc-600/30 to-zinc-900/80">
                <div className="flex flex-col items-center gap-1 opacity-60">
                  <div className="h-6 w-6 rounded-full bg-zinc-400/40" />
                  <div className="h-8 w-12 rounded-t-full bg-zinc-400/30" />
                </div>
              </div>
            )}
          </div>
          {/* Overlays (hook/subtitle/AI text) span full 9:16 safe area */}
          <div className="absolute inset-0 pointer-events-none">{children}</div>
        </div>
      )}
    </div>
  );
}
