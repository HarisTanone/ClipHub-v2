import { HfFixedStylePreview } from "@/components/HfFixedStylePreview";
import type { CanvasConfig } from "@/lib/canvasTemplates";
import type { HfStylePreset } from "@/lib/renderEngines";
import { CanvasPreviewFrame } from "./CanvasPreviewFrame";

export function HfLivePreview({
  preset,
  sample,
  kind,
  aspectRatio,
  thumbnailUrl,
  canvas,
}: {
  preset: HfStylePreset | undefined;
  sample: string;
  kind: "hook" | "subtitle";
  aspectRatio: string;
  thumbnailUrl?: string;
  canvas?: CanvasConfig | null;
}) {
  const accent = preset?.accent || "#22d3ee";
  const label = sample || preset?.preview || (kind === "hook" ? "HOOK TEXT" : "subtitle words");
  return (
    <div className="w-full max-w-[220px]">
      <p className="mb-2 text-center text-[10px] font-medium uppercase tracking-wider text-zinc-500">
        Live Preview · HyperFrames
      </p>
      <CanvasPreviewFrame
        canvas={canvas || null}
        thumbnailUrl={thumbnailUrl}
        className="max-h-[62vh] shadow-2xl"
      >
        <div className="absolute inset-0 flex items-center justify-center p-3">
          {preset ? (
            <HfFixedStylePreview id={preset?.id || ""} label={label} accent={accent} />
          ) : (
            <span className="text-xs text-zinc-500">Pilih template</span>
          )}
        </div>
        <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-500 z-10">
          fixed template · {preset?.name || "none"}
        </p>
      </CanvasPreviewFrame>
      {preset && (
        <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-900/60 p-2.5 text-[10px] space-y-1">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-zinc-200">{preset.name}</span>
            <span
              className="text-[9px] font-black uppercase px-1.5 py-0.5 rounded"
              style={{ color: accent, backgroundColor: `${accent}18` }}
            >
              {preset.mood}
            </span>
          </div>
          <p className="text-zinc-500 text-[9px]">{preset.desc}</p>
        </div>
      )}
    </div>
  );
}
