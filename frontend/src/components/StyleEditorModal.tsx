import { useState, useEffect } from "react";
import { Bookmark, Type, Sparkles, Layers, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import {
  DEFAULT_TEXT_EMPHASIS_STYLE,
  DEFAULT_WATERMARK_STYLE,
  DEFAULT_CTA_STYLE,
} from "./style-editor/types";
import type { StyleEditorModalProps } from "./style-editor/types";
import { STYLE_EDITOR_KEYFRAMES } from "./style-editor/utils";
import { PresetsTab } from "./style-editor/tabs/PresetsTab";
import { HookEditor } from "./style-editor/tabs/HookEditor";
import { SubtitleEditor } from "./style-editor/tabs/SubtitleEditor";
import { OtherTab } from "./style-editor/tabs/OtherTab";

// Re-export all types, defaults, constants, presets, UI components and utilities for complete backwards compatibility
export * from "./style-editor";

export function StyleEditorModal({
  open,
  onClose,
  hookStyle,
  subtitleStyle,
  textEmphasisStyle = DEFAULT_TEXT_EMPHASIS_STYLE,
  onHookChange,
  onSubtitleChange,
  onTextEmphasisChange = () => { },
  watermarkStyle = DEFAULT_WATERMARK_STYLE,
  onWatermarkChange = () => { },
  ctaStyle = DEFAULT_CTA_STYLE,
  onCtaChange = () => { },
  brollStyle,
  onBrollChange,
  onPresetLoad,
  aspectRatio = "9:16",
  inline,
  activeTab,
  thumbnailUrl,
  isSuperadmin,
  isPremium,
  userFeatures,
  activePresetId: externalActivePresetId,
  onPresetSelect,
  onProcess,
  processing = false,
  processProgress,
  aiTextPreviewContext,
  aiTextEnabled = true,
  canvasBackground = null,
}: StyleEditorModalProps) {
  const [tab, setTab] = useState<"presets" | "hook" | "subtitle" | "transition" | "ai_text" | "other">(activeTab || "hook");

  useEffect(() => {
    if (activeTab) setTab(activeTab);
  }, [activeTab]);

  if (!open) return null;

  // Inline mode: just render the content without overlay
  if (inline) {
    return (
      <div className="flex h-full min-h-0 flex-col overflow-hidden">
        <style>{STYLE_EDITOR_KEYFRAMES}</style>
        <div className="min-h-0 flex-1 overflow-hidden">
          {tab === "presets" ? (
            <PresetsTab
              hookStyle={hookStyle}
              subtitleStyle={subtitleStyle}
              textEmphasisStyle={textEmphasisStyle}
              watermarkStyle={watermarkStyle}
              ctaStyle={ctaStyle}
              brollStyle={brollStyle}
              onHookChange={onHookChange}
              onSubtitleChange={onSubtitleChange}
              onTextEmphasisChange={onTextEmphasisChange}
              onWatermarkChange={onWatermarkChange}
              onCtaChange={onCtaChange}
              onBrollChange={onBrollChange}
              onPresetLoad={onPresetLoad}
              externalActiveId={externalActivePresetId}
              onPresetSelect={onPresetSelect}
            />
          ) : tab === "hook" ? (
            <HookEditor
              style={hookStyle}
              onChange={onHookChange}
              aspectRatio={aspectRatio}
              thumbnailUrl={thumbnailUrl}
              canvasBackground={canvasBackground}
              isSuperadmin={isSuperadmin}
            />
          ) : tab === "other" ? (
            <OtherTab
              hookStyle={hookStyle}
              textEmphasisStyle={textEmphasisStyle}
              onHookChange={onHookChange}
              onTextEmphasisChange={onTextEmphasisChange}
              watermarkStyle={watermarkStyle}
              onWatermarkChange={onWatermarkChange}
              ctaStyle={ctaStyle}
              onCtaChange={onCtaChange}
              thumbnailUrl={thumbnailUrl}
              aiTextPreviewContext={aiTextPreviewContext}
              aiTextEnabled={aiTextEnabled}
              aspectRatio={aspectRatio}
              canvasBackground={canvasBackground}
            />
          ) : (
            <SubtitleEditor
              style={subtitleStyle}
              onChange={onSubtitleChange}
              aspectRatio={aspectRatio}
              thumbnailUrl={thumbnailUrl}
              isSuperadmin={isSuperadmin}
              isPremium={isPremium}
              userFeatures={userFeatures}
              canvasBackground={canvasBackground}
            />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <style>{STYLE_EDITOR_KEYFRAMES}</style>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-[95vw] max-w-[1100px] h-[92vh] sm:h-[88vh] bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl flex flex-col overflow-hidden">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between px-3.5 py-2.5 sm:px-5 sm:py-3 border-b border-zinc-800 shrink-0 gap-2">
          <div className="flex items-center gap-2 sm:gap-4 overflow-x-auto no-scrollbar">
            <h2 className="text-xs sm:text-sm font-semibold text-zinc-100 whitespace-nowrap">Custom Style Editor</h2>
            <div className="flex bg-zinc-800 rounded-lg p-0.5 shrink-0">
              <button type="button" onClick={() => setTab("presets")} className={cn("px-2.5 sm:px-3 py-1 sm:py-1.5 text-xs font-medium rounded-md transition-colors", tab === "presets" ? "bg-emerald-600 text-white" : "text-zinc-400 hover:text-zinc-200")}>
                <Bookmark className="h-3 w-3 inline mr-1" />Presets
              </button>
              <button type="button" onClick={() => setTab("hook")} className={cn("px-2.5 sm:px-3 py-1 sm:py-1.5 text-xs font-medium rounded-md transition-colors", tab === "hook" ? "bg-emerald-600 text-white" : "text-zinc-400 hover:text-zinc-200")}>
                <Type className="h-3 w-3 inline mr-1" />Hook
              </button>
              <button type="button" onClick={() => setTab("subtitle")} className={cn("px-2.5 sm:px-3 py-1 sm:py-1.5 text-xs font-medium rounded-md transition-colors", tab === "subtitle" ? "bg-emerald-600 text-white" : "text-zinc-400 hover:text-zinc-200")}>
                <Sparkles className="h-3 w-3 inline mr-1" />Subtitle
              </button>
              <button type="button" onClick={() => setTab("other")} className={cn("px-2.5 sm:px-3 py-1 sm:py-1.5 text-xs font-medium rounded-md transition-colors", tab === "other" ? "bg-emerald-600 text-white" : "text-zinc-400 hover:text-zinc-200")}>
                <Layers className="h-3 w-3 inline mr-1" />Other
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2 justify-end">
            {processing && processProgress && (
              <div className="w-28 sm:w-36">
                <div className="flex justify-between text-[9px] text-zinc-400">
                  <span className="capitalize">{processProgress.stage}</span>
                  <span>{processProgress.percentage}%</span>
                </div>
                <div className="mt-1 h-1 overflow-hidden rounded bg-zinc-800">
                  <div className="h-full bg-emerald-500 transition-all" style={{ width: `${processProgress.percentage}%` }} />
                </div>
              </div>
            )}
            {onProcess && (
              <Button type="button" size="sm" onClick={onProcess} loading={processing} icon={<Sparkles className="h-3.5 w-3.5" />}>
                {processing ? "Processing" : "Process Restyle"}
              </Button>
            )}
            <button type="button" onClick={onClose} disabled={processing} className="p-1.5 rounded-lg text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-40">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-hidden">
          {tab === "presets" ? (
            <PresetsTab
              hookStyle={hookStyle}
              subtitleStyle={subtitleStyle}
              textEmphasisStyle={textEmphasisStyle}
              watermarkStyle={watermarkStyle}
              ctaStyle={ctaStyle}
              brollStyle={brollStyle}
              onHookChange={onHookChange}
              onSubtitleChange={onSubtitleChange}
              onTextEmphasisChange={onTextEmphasisChange}
              onWatermarkChange={onWatermarkChange}
              onCtaChange={onCtaChange}
              onBrollChange={onBrollChange}
              onPresetLoad={onPresetLoad}
              externalActiveId={externalActivePresetId}
              onPresetSelect={onPresetSelect}
            />
          ) : tab === "hook" ? (
            <HookEditor
              style={hookStyle}
              onChange={onHookChange}
              aspectRatio={aspectRatio}
              thumbnailUrl={thumbnailUrl}
              canvasBackground={canvasBackground}
              isSuperadmin={isSuperadmin}
            />
          ) : tab === "other" ? (
            <OtherTab
              hookStyle={hookStyle}
              textEmphasisStyle={textEmphasisStyle}
              onHookChange={onHookChange}
              onTextEmphasisChange={onTextEmphasisChange}
              watermarkStyle={watermarkStyle}
              onWatermarkChange={onWatermarkChange}
              ctaStyle={ctaStyle}
              onCtaChange={onCtaChange}
              thumbnailUrl={thumbnailUrl}
              aiTextPreviewContext={aiTextPreviewContext}
              aiTextEnabled={aiTextEnabled}
              aspectRatio={aspectRatio}
              canvasBackground={canvasBackground}
            />
          ) : (
            <SubtitleEditor
              style={subtitleStyle}
              onChange={onSubtitleChange}
              aspectRatio={aspectRatio}
              thumbnailUrl={thumbnailUrl}
              isSuperadmin={isSuperadmin}
              isPremium={isPremium}
              userFeatures={userFeatures}
              canvasBackground={canvasBackground}
            />
          )}
        </div>
      </div>
    </div>
  );
}

export default StyleEditorModal;
