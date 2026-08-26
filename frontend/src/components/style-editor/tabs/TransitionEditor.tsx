import React from "react";
import { Scissors, Layers, MoveRight, Maximize2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { buildCanvasConfig } from "@/lib/canvasTemplates";
import type { BackgroundMode } from "@/components/BackgroundTemplateSection";
import type { HookStyle } from "../types";
import { Section, RangeInput } from "../ui/CommonControls";
import { CanvasPreviewFrame } from "../preview/CanvasPreviewFrame";

export const TRANSITION_META: Record<string, { label: string; desc: string; icon: React.ComponentType<{ className?: string }> }> = {
  cut: { label: "Cut", desc: "Hard cut antar framing. Cepat & energik.", icon: Scissors },
  fade: { label: "Fade", desc: "Cross-fade halus. Cinematic & natural.", icon: Layers },
  slide: { label: "Slide", desc: "Geser horizontal. Dinamis & modern.", icon: MoveRight },
  zoom: { label: "Zoom", desc: "Zoom in/out transisi. Dramatis.", icon: Maximize2 },
};

export function TransitionEditor({
  style,
  onChange,
  thumbnailUrl,
  aspectRatio,
  canvasBackground,
}: {
  style: HookStyle;
  onChange: (style: HookStyle) => void;
  thumbnailUrl?: string;
  aspectRatio?: string;
  canvasBackground?: { mode: BackgroundMode; templateId: string; imageDataUrl: string | null } | null;
}) {
  const active = style.transitionStyle || "cut";
  const duration = style.transitionDuration ?? 0.35;
  const durationInt = Math.round(duration * 100);
  const previewDur = Math.max(0.8, duration * 2);
  const update = (patch: Partial<HookStyle>) => onChange({ ...style, ...patch });
  const canvas = (aspectRatio === "16:9" || aspectRatio === "1:1")
    ? buildCanvasConfig(aspectRatio, {
      backgroundMode: canvasBackground?.mode || "template",
      templateId: canvasBackground?.templateId || "dark-studio",
      backgroundImageUrl: canvasBackground?.imageDataUrl || null,
    })
    : null;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 h-full">
      {/* Left: Live preview (sticky) */}
      <div className="xl:col-span-5 p-4 overflow-y-auto space-y-4 border-r border-zinc-800">
        <Section title="Live Preview">
          <div className="flex justify-center">
            <CanvasPreviewFrame canvas={canvas} thumbnailUrl={thumbnailUrl} className="max-w-[200px] rounded-xl border-zinc-700 shadow-2xl">
              <div className="absolute inset-0 flex items-center justify-center" style={{ animation: `${active === "cut" ? "transCut" : active === "fade" ? "transFade" : active === "slide" ? "transSlide" : "transZoom"} ${previewDur}s ease-in-out infinite` }}>
                <div className="h-full w-full bg-gradient-to-br from-emerald-500/60 to-blue-500/50" />
              </div>
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <span className="rounded-full bg-black/60 px-2.5 py-0.5 text-[9px] font-medium text-white backdrop-blur-sm">{active} · {duration.toFixed(2)}s</span>
              </div>
              <div className="absolute bottom-2 left-2 z-30 rounded-md bg-black/60 px-2 py-0.5 text-[8px] text-zinc-400">Preview transition</div>
            </CanvasPreviewFrame>
          </div>
        </Section>

        <Section title="Info">
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
            <p className="text-[10px] leading-relaxed text-zinc-400">
              Transisi diterapkan saat clip dimulai atau saat framing speaker berubah (single → grid, atau panning antar speaker). Pilihan ini mempengaruhi <span className="text-emerald-400">preview</span> dan <span className="text-emerald-400">final Remotion render</span>.
            </p>
          </div>
        </Section>
      </div>

      {/* Right: Controls */}
      <div className="xl:col-span-7 p-4 overflow-y-auto space-y-4">
        <style>{`
          @keyframes transCut { 0%,49% { opacity:1; } 50%,99% { opacity:0; } 100% { opacity:1; } }
          @keyframes transFade { 0%,100% { opacity:1; } 50% { opacity:0; } }
          @keyframes transSlide { 0% { transform:translateX(0); } 49% { transform:translateX(-100%); } 50% { transform:translateX(100%); } 100% { transform:translateX(0); } }
          @keyframes transZoom { 0%,100% { transform:scale(1); opacity:1; } 50% { transform:scale(1.5); opacity:0; } }
        `}</style>

        <Section title="Transition Style">
          <div className="grid grid-cols-2 gap-2">
            {(["cut", "fade", "slide", "zoom"] as const).map((value) => {
              const meta = TRANSITION_META[value];
              return (
                <button type="button" key={value} onClick={() => update({ transitionStyle: value })} className={cn("rounded-xl border p-3 text-left transition-all", active === value ? "border-emerald-500 bg-emerald-500/10" : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700")}>
                  <div className="mb-2 flex items-center justify-between">
                    <meta.icon className={cn("h-4 w-4", active === value ? "text-emerald-400" : "text-zinc-500")} />
                    {active === value && <span className="text-[8px] font-bold uppercase tracking-wider text-emerald-400">Active</span>}
                  </div>
                  <p className={cn("text-xs font-semibold", active === value ? "text-emerald-300" : "text-zinc-300")}>{meta.label}</p>
                  <p className="mt-0.5 text-[9px] leading-tight text-zinc-600">{meta.desc}</p>
                </button>
              );
            })}
          </div>
        </Section>

        <Section title="Timing">
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
            <RangeInput label={`Duration: ${duration.toFixed(2)}s`} min={15} max={100} value={durationInt} onChange={(v) => update({ transitionDuration: v / 100 })} />
            <p className="mt-2 text-[9px] text-zinc-600">Rentang 0.15s – 1.00s. Cut cepat untuk energi tinggi, fade lambat untuk vibe cinematic.</p>
          </div>
        </Section>
      </div>
    </div>
  );
}
