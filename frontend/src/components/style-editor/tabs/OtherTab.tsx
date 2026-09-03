import { useState, useEffect } from "react";
import { MoveRight, Layers, Image as ImageIcon, Megaphone } from "lucide-react";
import { cn } from "@/lib/utils";
import type { BackgroundMode } from "@/components/BackgroundTemplateSection";
import type { HookStyle, TextEmphasisStyle, WatermarkStyle, CtaStyle } from "../types";
import { TransitionEditor } from "./TransitionEditor";
import { TextEmphasisEditor } from "./TextEmphasisEditor";
import { WatermarkEditor } from "./WatermarkEditor";
import { CtaEditor } from "./CtaEditor";

export function OtherTab({
  hookStyle,
  textEmphasisStyle,
  onHookChange,
  onTextEmphasisChange,
  watermarkStyle,
  onWatermarkChange,
  ctaStyle,
  onCtaChange,
  thumbnailUrl,
  aiTextPreviewContext,
  aiTextEnabled,
  aspectRatio,
  canvasBackground,
  initialSubTab,
}: {
  hookStyle: HookStyle;
  textEmphasisStyle: TextEmphasisStyle;
  onHookChange: (s: HookStyle) => void;
  onTextEmphasisChange: (s: TextEmphasisStyle) => void;
  watermarkStyle: WatermarkStyle;
  onWatermarkChange: (s: WatermarkStyle) => void;
  ctaStyle: CtaStyle;
  onCtaChange: (s: CtaStyle) => void;
  thumbnailUrl?: string;
  aiTextPreviewContext?: { jobId: string; clipRank: number; frame: number };
  aiTextEnabled: boolean;
  aspectRatio?: string;
  canvasBackground?: { mode: BackgroundMode; templateId: string; imageDataUrl: string | null } | null;
  initialSubTab?: "transition" | "ai_text" | "watermark" | "cta";
}) {
  const [subTab, setSubTab] = useState<"transition" | "ai_text" | "watermark" | "cta">(initialSubTab || "transition");

  useEffect(() => {
    if (initialSubTab) {
      setSubTab(initialSubTab);
    }
  }, [initialSubTab]);

  useEffect(() => {
    if (!aiTextEnabled && subTab === "ai_text") setSubTab("transition");
  }, [aiTextEnabled, subTab]);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex items-center gap-1 px-4 pt-3 pb-2 shrink-0 border-b border-zinc-800/60">
        <button
          type="button"
          onClick={() => setSubTab("transition")}
          className={cn("flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors", subTab === "transition" ? "bg-emerald-600 text-white" : "bg-zinc-800/60 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800")}
        >
          <MoveRight className="h-3 w-3" />Transition
        </button>
        <button
          type="button"
          onClick={() => setSubTab("ai_text")}
          disabled={!aiTextEnabled}
          aria-disabled={!aiTextEnabled}
          title={!aiTextEnabled ? "Aktifkan AI Cinematic Text untuk membuka pengaturan AI Text" : undefined}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
            !aiTextEnabled
              ? "cursor-not-allowed bg-zinc-900/60 text-zinc-600 opacity-60"
              : subTab === "ai_text"
                ? "bg-emerald-600 text-white"
                : "bg-zinc-800/60 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
          )}
        >
          <Layers className="h-3 w-3" />AI Text
        </button>
        <button
          type="button"
          onClick={() => setSubTab("watermark")}
          className={cn("flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors", subTab === "watermark" ? "bg-emerald-600 text-white" : "bg-zinc-800/60 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800")}
        >
          <ImageIcon className="h-3 w-3" />Watermark
        </button>
        <button
          type="button"
          onClick={() => setSubTab("cta")}
          className={cn("flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors", subTab === "cta" ? "bg-emerald-600 text-white" : "bg-zinc-800/60 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800")}
        >
          <Megaphone className="h-3 w-3" />CTA End-Card
        </button>
        <span className="ml-auto text-[9px] text-zinc-600">
          {subTab === "cta" ? "Muncul di akhir video (1s-6s)" : subTab === "watermark" ? "Dirender server-side via FFmpeg" : aiTextEnabled ? "Applied to preview & final render" : "Aktifkan AI Cinematic Text untuk mengatur AI Text"}
        </span>
      </div>
      {subTab === "transition" ? (
        <TransitionEditor
          style={hookStyle}
          onChange={onHookChange}
          thumbnailUrl={thumbnailUrl}
          aspectRatio={aspectRatio}
          canvasBackground={canvasBackground}
        />
      ) : subTab === "ai_text" ? (
        <TextEmphasisEditor
          style={textEmphasisStyle}
          onChange={onTextEmphasisChange}
          thumbnailUrl={thumbnailUrl}
          previewContext={aiTextPreviewContext}
          aspectRatio={aspectRatio}
          canvasBackground={canvasBackground}
        />
      ) : subTab === "cta" ? (
        <CtaEditor
          style={ctaStyle}
          onChange={onCtaChange}
          thumbnailUrl={thumbnailUrl}
          aspectRatio={aspectRatio}
          canvasBackground={canvasBackground}
        />
      ) : (
        <WatermarkEditor
          style={watermarkStyle}
          onChange={onWatermarkChange}
          thumbnailUrl={thumbnailUrl}
          aspectRatio={aspectRatio}
          canvasBackground={canvasBackground}
        />
      )}
    </div>
  );
}
