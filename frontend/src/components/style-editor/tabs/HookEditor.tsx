import { useState, useEffect } from "react";
import { Zap, Palette, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { buildCanvasConfig } from "@/lib/canvasTemplates";
import type { BackgroundMode } from "@/components/BackgroundTemplateSection";
import {
  resolveEngine,
  defaultHfHookId,
  HF_HOOK_STYLES,
  FFMPEG_HOOK_PRESETS,
  SKIA_HOOK_PRESETS,
} from "@/lib/renderEngines";
import type { HookStyle } from "../types";
import {
  DEFAULT_HOOK_STYLE,
  HOOK_PRESETS,
  HOOK_ANIMATIONS,
  HOOK_ANIMATION_META,
  HOOK_CAPABILITIES,
  hookCapabilities,
  FONT_OPTIONS,
  HOOK_FONT_SUGGESTIONS,
} from "../types";
import { useGoogleFont, getPageItems, getPageForIndex, getHookPreviewSample } from "../utils";
import { Section, UnavailableHint, ColorPicker, RangeInput, Checkbox, SelectSmall } from "../ui/CommonControls";
import { TimingOptionCard, FontChips } from "../ui/MetaTile";
import { PaginationControls } from "../ui/PaginationControls";
import { EnginePicker } from "../ui/EnginePicker";
import { AccentLinePreview } from "../ui/AccentLinePreview";
import { HookPresetCard } from "../cards/HookPresetCard";
import { CanvasPreviewFrame } from "../preview/CanvasPreviewFrame";
import { HookPreviewRenderer } from "../preview/HookPreviewRenderer";
import { HfStyleGrid } from "../preview/HfStyleGrid";
import { HfLivePreview } from "../preview/HfLivePreview";
import { SkiaHookLivePreview } from "../preview/SkiaHookLivePreview";

export function HookEditor({
  style,
  onChange,
  aspectRatio,
  thumbnailUrl,
  canvasBackground,
  isSuperadmin,
}: {
  style: HookStyle;
  onChange: (s: HookStyle) => void;
  aspectRatio: string;
  thumbnailUrl?: string;
  canvasBackground?: { mode: BackgroundMode; templateId: string; imageDataUrl: string | null } | null;
  isSuperadmin?: boolean;
}) {
  const update = (patch: Partial<HookStyle>) => onChange({ ...style, ...patch });
  const engine = resolveEngine(style.engine);
  const hfId = style.hf_template || defaultHfHookId();
  const hfPreset = HF_HOOK_STYLES.find((s) => s.id === hfId) || HF_HOOK_STYLES[0];
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [presetPage, setPresetPage] = useState(1);
  const [animationPage, setAnimationPage] = useState(() => getPageForIndex(HOOK_ANIMATIONS.indexOf(style.animation)));
  const [ffmpegHookPage, setFfmpegHookPage] = useState(1);
  const [skiaHookPage, setSkiaHookPage] = useState(1);
  useGoogleFont(style.fontFamily);
  const canvas = (aspectRatio === "16:9" || aspectRatio === "1:1")
    ? buildCanvasConfig(aspectRatio, {
      backgroundMode: canvasBackground?.mode || "template",
      templateId: canvasBackground?.templateId || "dark-studio",
      backgroundImageUrl: canvasBackground?.imageDataUrl || null,
    })
    : null;

  const activeAnimation = HOOK_ANIMATION_META[style.animation] || HOOK_ANIMATION_META.podcast_lower_third;
  const capabilities = hookCapabilities(style.animation);
  const isModernHookStyle = Boolean(HOOK_CAPABILITIES[style.animation]);
  const visibleHookPresets = getPageItems(HOOK_PRESETS, presetPage);
  const visibleHookAnimations = getPageItems(HOOK_ANIMATIONS, animationPage);
  const visibleFfmpegHooks = getPageItems(FFMPEG_HOOK_PRESETS, ffmpegHookPage);
  const visibleSkiaHooks = getPageItems(SKIA_HOOK_PRESETS, skiaHookPage);

  useEffect(() => {
    setAnimationPage(getPageForIndex(HOOK_ANIMATIONS.indexOf(style.animation)));
  }, [style.animation]);

  useEffect(() => {
    if (engine === "remotion" && !HOOK_ANIMATIONS.includes(style.animation)) {
      update({ animation: DEFAULT_HOOK_STYLE.animation });
    }
  }, [style.animation, engine]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 h-full min-h-0 overflow-hidden">
      {/* Left scrolls; right Live Preview stays put */}
      <div className="lg:col-span-8 p-4 overflow-y-auto space-y-4 border-r border-zinc-800 min-h-0">
        <Section title="Render Engine">
          <EnginePicker
            engine={engine}
            kind="hook"
            isSuperadmin={isSuperadmin}
            onChange={(e) => update({
              engine: e,
              hf_template: style.hf_template || defaultHfHookId(),
            })}
          />
        </Section>

        {engine === "hyperframes" ? (
          <>
            <Section title="HyperFrames Hook Styles">
              <HfStyleGrid
                items={HF_HOOK_STYLES}
                activeId={hfId}
                onSelect={(id) => update({ engine: "hyperframes", hf_template: id })}
              />
            </Section>
            <Section title="Hook Text">
              <textarea value={style.text} onChange={(e) => update({ text: e.target.value })} placeholder="Leave empty for AI-generated hook..." rows={2} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 resize-none focus:outline-none focus:border-zinc-500" />
            </Section>
            <Section title="Duration">
              <RangeInput label={`Duration: ${style.duration}s`} min={15} max={60} value={Math.round(style.duration * 10)} onChange={(v) => update({ duration: v / 10 })} />
            </Section>
          </>
        ) : engine === "ffmpeg" ? (
          <>
            <Section title="FFmpeg Drawtext">
              <div className="rounded-lg border border-purple-500/20 bg-purple-500/5 p-3">
                <p className="text-[10px] text-purple-300 mb-1"><Zap className="inline w-3 h-3 mr-1" />Server-side render · no browser needed</p>
                <p className="text-[9px] text-zinc-500">FFmpeg drawtext filter. 12 Preset unik dengan server-side overlay cepat.</p>
              </div>
            </Section>

            <Section title="Hook Style Preset">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {visibleFfmpegHooks.map((preset) => (
                  <button
                    key={preset.id}
                    type="button"
                    onClick={() => update({
                      animation: preset.id,
                      color: preset.color,
                      fontSize: preset.fontSize,
                      fontFamily: preset.fontFamily,
                      fontWeight: preset.fontWeight,
                      strokeEnabled: preset.strokeEnabled,
                      strokeWidth: preset.strokeWidth,
                      strokeColor: preset.strokeColor,
                      bgOpacity: preset.bgOpacity,
                      position: preset.positionY <= 35 ? "top" : preset.positionY >= 65 ? "bottom" : "center",
                      positionY: preset.positionY,
                    })}
                    className={cn(
                      "group overflow-hidden rounded-xl border text-left transition-all",
                      style.animation === preset.id
                        ? "border-purple-500 bg-purple-500/10 ring-1 ring-purple-500/40"
                        : "border-zinc-700/80 bg-zinc-900/40 hover:border-zinc-500 hover:bg-zinc-900"
                    )}
                  >
                    <span
                      className="block relative w-full overflow-hidden bg-zinc-950"
                      style={{ aspectRatio: "16/9" }}
                    >
                      <span
                        className="absolute left-0 right-0 flex justify-center px-2"
                        style={{ top: `${preset.positionY}%`, transform: "translateY(-50%)" }}
                      >
                        <span
                          className="truncate whitespace-nowrap font-semibold"
                          style={{
                            fontSize: Math.max(preset.fontSize * 0.24, 12),
                            fontWeight: Number(preset.fontWeight),
                            fontFamily: `'${preset.fontFamily}', sans-serif`,
                            color: preset.color,
                            textTransform: "uppercase",
                            letterSpacing: "0.02em",
                            padding: "2px 6px",
                            backgroundColor: preset.bgOpacity > 0 ? `#000${Math.round(Math.min(1, preset.bgOpacity) * 255).toString(16).padStart(2, "0")}` : "transparent",
                            paintOrder: preset.strokeEnabled ? "stroke" : undefined,
                            WebkitTextStroke: preset.strokeEnabled ? `${Math.max(preset.strokeWidth * 0.18, 0.6)}px ${preset.strokeColor}` : undefined,
                          }}
                        >
                          HOOK
                        </span>
                      </span>
                      {style.animation === preset.id && (
                        <span className="absolute top-1.5 right-1.5 z-10 flex h-4 w-4 items-center justify-center rounded-full bg-purple-500 text-white shadow">
                          <Check className="h-2.5 w-2.5 stroke-[3]" />
                        </span>
                      )}
                    </span>
                    <span className="block px-2.5 py-1.5">
                      <span className="flex items-center gap-1.5">
                        <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: preset.color }} />
                        <span className={cn("truncate text-[10px] font-semibold", style.animation === preset.id ? "text-purple-300" : "text-zinc-300 group-hover:text-zinc-100")}>
                          {preset.name}
                        </span>
                      </span>
                      <span className="mt-0.5 block truncate text-[8px] text-zinc-600">{preset.desc}</span>
                    </span>
                  </button>
                ))}
              </div>
              <PaginationControls page={ffmpegHookPage} totalItems={FFMPEG_HOOK_PRESETS.length} onPageChange={setFfmpegHookPage} label="presets" />
            </Section>

            <Section title="Hook Text">
              <textarea value={style.text} onChange={(e) => update({ text: e.target.value })} placeholder="Leave empty for AI-generated hook..." rows={2} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 resize-none focus:outline-none focus:border-zinc-500" />
            </Section>

            <Section title="Typography">
              <FontChips fonts={HOOK_FONT_SUGGESTIONS} active={style.fontFamily} onSelect={(fontFamily) => update({ fontFamily })} />
              <div className="grid grid-cols-3 gap-3 mt-3">
                <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={FONT_OPTIONS} />
                <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                <RangeInput label={`Size: ${style.fontSize}px`} min={24} max={96} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
              </div>
              <div className="flex gap-4 mt-3">
                <Checkbox label="UPPERCASE" checked={style.uppercase} onChange={(v) => update({ uppercase: v })} />
              </div>
            </Section>

            <Section title="Colors">
              <div className="grid grid-cols-2 gap-3">
                <ColorPicker label="Text Color" value={style.color} onChange={(v) => update({ color: v })} />
                <ColorPicker label="Background" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
              </div>
              <RangeInput label={`BG Opacity: ${Math.round(style.bgOpacity * 100)}%`} min={0} max={100} value={Math.round(style.bgOpacity * 100)} onChange={(v) => update({ bgOpacity: v / 100 })} />
            </Section>

            <Section title="Stroke & Shadow">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text outline" checked={style.strokeEnabled} onChange={(v) => update({ strokeEnabled: v })} />
                  {style.strokeEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Outline" value={style.strokeColor} onChange={(v) => update({ strokeColor: v })} />
                      <RangeInput label={`Width: ${style.strokeWidth}px`} min={1} max={10} value={style.strokeWidth} onChange={(v) => update({ strokeWidth: v })} />
                    </div>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text shadow" checked={style.shadowEnabled} onChange={(v) => update({ shadowEnabled: v })} />
                  {style.shadowEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Shadow" value={style.shadowColor} onChange={(v) => update({ shadowColor: v })} />
                      <RangeInput label={`Blur: ${style.shadowBlur}`} min={0} max={40} value={style.shadowBlur} onChange={(v) => update({ shadowBlur: v })} />
                    </div>
                  )}
                </div>
              </div>
            </Section>

            <Section title="Position">
              <div className="grid grid-cols-3 gap-2 mb-3">
                {(["top", "center", "bottom"] as const).map((p) => {
                  const isSelected = (style.positionY != null ? (style.positionY <= 35 ? "top" : style.positionY >= 65 ? "bottom" : "center") : style.position) === p;
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => update({ position: p, positionY: p === "top" ? 20 : p === "bottom" ? 80 : 50 })}
                      className={cn(
                        "py-2 rounded-lg border text-[11px] font-medium capitalize transition-colors",
                        isSelected ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600"
                      )}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
              <RangeInput
                label={`Vertical: ${style.positionY}%`}
                min={5}
                max={95}
                value={style.positionY}
                onChange={(v) => update({
                  positionY: v,
                  position: v <= 35 ? "top" : v >= 65 ? "bottom" : "center",
                })}
              />
            </Section>

            <Section title="Duration">
              <RangeInput label={`Duration: ${style.duration}s`} min={15} max={60} value={Math.round(style.duration * 10)} onChange={(v) => update({ duration: v / 10 })} />
              <div className="grid grid-cols-2 gap-3 mt-3">
                <RangeInput label={`Fade In: ${style.fadeIn}s`} min={1} max={15} value={Math.round(style.fadeIn * 10)} onChange={(v) => update({ fadeIn: v / 10 })} />
                <RangeInput label={`Fade Out: ${style.fadeOut}s`} min={1} max={15} value={Math.round(style.fadeOut * 10)} onChange={(v) => update({ fadeOut: v / 10 })} />
              </div>
            </Section>
          </>
        ) : engine === "skia" ? (
          <>
            <Section title="Skia Render Engine">
              <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                <p className="text-[10px] text-amber-400 mb-1"><Palette className="inline w-3 h-3 mr-1" />Canvas GPU Rendering</p>
                <p className="text-[9px] text-zinc-500">Hook animation dirender cepat via GPU Skia Canvas. 12 Preset dengan efek shader khusus.</p>
              </div>
            </Section>

            <Section title="Skia Hook Presets">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {visibleSkiaHooks.map((preset) => (
                  <button
                    key={preset.id}
                    type="button"
                    onClick={() => update({
                      animation: preset.id,
                      color: preset.color,
                      fontSize: preset.fontSize,
                      fontFamily: preset.fontFamily,
                      fontWeight: preset.fontWeight,
                      strokeEnabled: preset.strokeEnabled,
                      strokeWidth: preset.strokeWidth,
                      strokeColor: preset.strokeColor,
                      gradientEnabled: preset.gradientEnabled,
                      gradientFrom: preset.gradientFrom,
                      gradientTo: preset.gradientTo,
                      glowEnabled: preset.glowEnabled,
                      glowColor: preset.glowColor,
                      glowSize: preset.glowSize,
                      bgOpacity: preset.bgOpacity,
                      position: preset.positionY <= 35 ? "top" : preset.positionY >= 65 ? "bottom" : "center",
                      positionY: preset.positionY,
                    })}
                    className={cn(
                      "group overflow-hidden rounded-xl border text-left transition-all",
                      style.animation === preset.id || style.animation === preset.id.replace("skia_", "")
                        ? "border-amber-500 bg-amber-500/10 ring-1 ring-amber-500/40"
                        : "border-zinc-700/80 bg-zinc-900/40 hover:border-zinc-500 hover:bg-zinc-900"
                    )}
                  >
                    <span
                      className="block relative w-full overflow-hidden bg-zinc-950"
                      style={{ aspectRatio: "16/9" }}
                    >
                      <span
                        className="absolute left-0 right-0 flex justify-center px-2"
                        style={{ top: `${preset.positionY}%`, transform: "translateY(-50%)" }}
                      >
                        <span
                          className="truncate whitespace-nowrap font-semibold"
                          style={{
                            fontSize: Math.max(preset.fontSize * 0.24, 12),
                            fontWeight: Number(preset.fontWeight),
                            fontFamily: `'${preset.fontFamily}', sans-serif`,
                            color: preset.color,
                            textTransform: "uppercase",
                            letterSpacing: "0.02em",
                            padding: "2px 6px",
                            backgroundColor: preset.bgOpacity > 0 ? `#000${Math.round(Math.min(1, preset.bgOpacity) * 255).toString(16).padStart(2, "0")}` : "transparent",
                            paintOrder: preset.strokeEnabled ? "stroke" : undefined,
                            WebkitTextStroke: preset.strokeEnabled ? `${Math.max(preset.strokeWidth * 0.18, 0.6)}px ${preset.strokeColor}` : undefined,
                          }}
                        >
                          SKIA
                        </span>
                      </span>
                      {(style.animation === preset.id || style.animation === preset.id.replace("skia_", "")) && (
                        <span className="absolute top-1.5 right-1.5 z-10 flex h-4 w-4 items-center justify-center rounded-full bg-amber-500 text-black shadow">
                          <Check className="h-2.5 w-2.5 stroke-[3]" />
                        </span>
                      )}
                    </span>
                    <span className="block px-2.5 py-1.5">
                      <span className="flex items-center gap-1.5">
                        <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: preset.color }} />
                        <span className={cn("truncate text-[10px] font-semibold", (style.animation === preset.id || style.animation === preset.id.replace("skia_", "")) ? "text-amber-300" : "text-zinc-300 group-hover:text-zinc-100")}>
                          {preset.name}
                        </span>
                      </span>
                      <span className="mt-0.5 block truncate text-[8px] text-zinc-600">{preset.desc}</span>
                    </span>
                  </button>
                ))}
              </div>
              <PaginationControls page={skiaHookPage} totalItems={SKIA_HOOK_PRESETS.length} onPageChange={setSkiaHookPage} label="presets" />
            </Section>

            <Section title="Hook Text">
              <textarea value={style.text} onChange={(e) => update({ text: e.target.value })} placeholder="Leave empty for AI-generated hook..." rows={2} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 resize-none focus:outline-none focus:border-zinc-500" />
            </Section>

            <Section title="Typography">
              <FontChips fonts={HOOK_FONT_SUGGESTIONS} active={style.fontFamily} onSelect={(fontFamily) => update({ fontFamily })} />
              <div className="grid grid-cols-3 gap-3 mt-3">
                <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={FONT_OPTIONS} />
                <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                <RangeInput label={`Size: ${style.fontSize}px`} min={24} max={96} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
              </div>
              <div className="flex gap-4 mt-3">
                <Checkbox label="UPPERCASE" checked={style.uppercase} onChange={(v) => update({ uppercase: v })} />
                <Checkbox label="Italic" checked={style.italic} onChange={(v) => update({ italic: v })} />
              </div>
            </Section>

            <Section title="Colors & GPU Effects">
              <div className="grid grid-cols-2 gap-3">
                <ColorPicker label="Text Color" value={style.color} onChange={(v) => update({ color: v })} />
                <ColorPicker label="Background" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
              </div>
              <RangeInput label={`BG Opacity: ${Math.round(style.bgOpacity * 100)}%`} min={0} max={100} value={Math.round(style.bgOpacity * 100)} onChange={(v) => update({ bgOpacity: v / 100 })} />
              <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text gradient" checked={style.gradientEnabled} onChange={(v) => update({ gradientEnabled: v })} />
                  {style.gradientEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="From" value={style.gradientFrom} onChange={(v) => update({ gradientFrom: v })} />
                      <ColorPicker label="To" value={style.gradientTo} onChange={(v) => update({ gradientTo: v })} />
                    </div>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text glow" checked={style.glowEnabled} onChange={(v) => update({ glowEnabled: v })} />
                  {style.glowEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Glow Color" value={style.glowColor} onChange={(v) => update({ glowColor: v })} />
                      <RangeInput label={`Glow Size: ${style.glowSize}px`} min={5} max={70} value={style.glowSize} onChange={(v) => update({ glowSize: v })} />
                    </div>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text outline" checked={style.strokeEnabled} onChange={(v) => update({ strokeEnabled: v })} />
                  {style.strokeEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Outline" value={style.strokeColor} onChange={(v) => update({ strokeColor: v })} />
                      <RangeInput label={`Width: ${style.strokeWidth}px`} min={1} max={10} value={style.strokeWidth} onChange={(v) => update({ strokeWidth: v })} />
                    </div>
                  )}
                </div>
              </div>
            </Section>

            <Section title="Position">
              <div className="grid grid-cols-3 gap-2 mb-3">
                {(["top", "center", "bottom"] as const).map((p) => {
                  const isSelected = (style.positionY != null ? (style.positionY <= 35 ? "top" : style.positionY >= 65 ? "bottom" : "center") : style.position) === p;
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => update({ position: p, positionY: p === "top" ? 20 : p === "bottom" ? 80 : 50 })}
                      className={cn(
                        "py-2 rounded-lg border text-[11px] font-medium capitalize transition-colors",
                        isSelected ? "border-amber-500 bg-amber-500/10 text-amber-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600"
                      )}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
              <RangeInput
                label={`Vertical: ${style.positionY}%`}
                min={5}
                max={95}
                value={style.positionY}
                onChange={(v) => update({
                  positionY: v,
                  position: v <= 35 ? "top" : v >= 65 ? "bottom" : "center",
                })}
              />
            </Section>

            <Section title="Timing">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3 border border-zinc-800 rounded-lg bg-zinc-950/50">
                <RangeInput label={`Duration: ${style.duration}s`} min={15} max={60} value={Math.round(style.duration * 10)} onChange={(v) => update({ duration: v / 10 })} />
                <RangeInput label={`Fade In: ${style.fadeIn}s`} min={1} max={15} value={Math.round(style.fadeIn * 10)} onChange={(v) => update({ fadeIn: v / 10 })} />
                <RangeInput label={`Fade Out: ${style.fadeOut}s`} min={1} max={15} value={Math.round(style.fadeOut * 10)} onChange={(v) => update({ fadeOut: v / 10 })} />
              </div>
            </Section>
          </>
        ) : (
          <>
            {/* Remotion Quick Presets */}
            <Section title="Quick Presets">
              <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-2">
                {visibleHookPresets.map((p) => (
                  <HookPresetCard
                    key={p.id}
                    preset={p}
                    active={activePreset === p.id}
                    onClick={() => {
                      onChange({ ...DEFAULT_HOOK_STYLE, ...p.style, text: style.text, engine: "remotion" } as HookStyle);
                      setActivePreset(p.id);
                    }}
                  />
                ))}
              </div>
              <PaginationControls page={presetPage} totalItems={HOOK_PRESETS.length} onPageChange={setPresetPage} label="presets" />
            </Section>

            <Section title="Hook Text">
              <textarea value={style.text} onChange={(e) => update({ text: e.target.value })} placeholder="Leave empty for AI-generated hook..." rows={2} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 resize-none focus:outline-none focus:border-zinc-500" />
            </Section>

            <Section title="Animation & Timing">
              <div className="mb-3 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950/70">
                <div className="flex items-center justify-between gap-3 border-b border-zinc-800 px-3 py-2">
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold text-zinc-200">{activeAnimation.label}</p>
                    <p className="truncate text-[9px] text-zinc-500">{activeAnimation.desc}</p>
                  </div>
                  <span className="rounded-md px-2 py-1 text-[9px] font-black" style={{ color: activeAnimation.accent, backgroundColor: `${activeAnimation.accent}18`, border: `1px solid ${activeAnimation.accent}44` }}>{activeAnimation.mood}</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3">
                  <RangeInput label={`Duration: ${style.duration}s`} min={15} max={60} value={Math.round(style.duration * 10)} onChange={(v) => update({ duration: v / 10 })} />
                  <RangeInput label={`Fade In: ${style.fadeIn}s`} min={1} max={15} value={Math.round(style.fadeIn * 10)} onChange={(v) => update({ fadeIn: v / 10 })} />
                  <RangeInput label={`Fade Out: ${style.fadeOut}s`} min={1} max={15} value={Math.round(style.fadeOut * 10)} onChange={(v) => update({ fadeOut: v / 10 })} />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3 gap-2">
                {visibleHookAnimations.map((a) => (
                  <TimingOptionCard key={a} meta={HOOK_ANIMATION_META[a] || HOOK_ANIMATION_META.podcast_lower_third} active={style.animation === a} onClick={() => update({ animation: a })} kind="hook" />
                ))}
              </div>
              <PaginationControls page={animationPage} totalItems={HOOK_ANIMATIONS.length} onPageChange={setAnimationPage} label="animations" />
            </Section>

            <Section title="Hook Components">
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3 space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Checkbox label="Show badge / category label" checked={style.badgeEnabled} onChange={(v) => update({ badgeEnabled: v })} disabled={!capabilities.badge} />
                    {!capabilities.badge && <UnavailableHint text="Style ini tidak memakai badge." />}
                    {style.badgeEnabled && capabilities.badge && (
                      <input
                        type="text"
                        value={style.badgeText}
                        onChange={(e) => update({ badgeText: e.target.value })}
                        placeholder="Badge text (mis: INTERNASIONAL, HOT TAKE)"
                        className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:border-zinc-500 focus:outline-none"
                      />
                    )}
                  </div>
                  <div className="space-y-2">
                    <Checkbox label="Decorative motion elements" checked={style.decorativeElements} onChange={(v) => update({ decorativeElements: v })} disabled={!capabilities.decorative} />
                    {!capabilities.decorative && <UnavailableHint text="Style ini memakai motion utama tanpa dekorasi tambahan." />}
                    <RangeInput label={`Motion: ${style.motionIntensity.toFixed(1)}x`} min={0} max={20} value={Math.round(style.motionIntensity * 10)} onChange={(v) => update({ motionIntensity: v / 10 })} />
                  </div>
                </div>

                {/* Footer / Source Bar Label (e.g. READ MORE AT chatgpt.com) */}
                <div className="pt-2 border-t border-zinc-800/80">
                  <div className="space-y-2">
                    <Checkbox label="Show footer / source label" checked={style.footerEnabled !== false} onChange={(v) => update({ footerEnabled: v })} disabled={!capabilities.footer} />
                    {!capabilities.footer && <UnavailableHint text="Style ini tidak memakai footer bar." />}
                    {style.footerEnabled !== false && capabilities.footer && (
                      <input
                        type="text"
                        value={style.footerText || ""}
                        onChange={(e) => update({ footerText: e.target.value })}
                        placeholder="Footer text (mis: READ MORE AT chatgpt.com, SWIPE UP FOR MORE)"
                        className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:border-zinc-500 focus:outline-none"
                      />
                    )}
                  </div>
                </div>
              </div>
            </Section>

            <Section title="Typography">
              <FontChips fonts={HOOK_FONT_SUGGESTIONS} active={style.fontFamily} onSelect={(fontFamily) => update({ fontFamily })} />
              <div className="grid grid-cols-3 gap-3 mt-3">
                <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={FONT_OPTIONS} />
                <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                <SelectSmall label="Align" value={style.textAlign} onChange={(v) => update({ textAlign: v as any })} options={["center", "left", "right"]} />
              </div>
              <div className="grid grid-cols-3 gap-3 mt-3">
                <RangeInput label={`Size: ${style.fontSize}px`} min={24} max={96} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
                <RangeInput label={`Spacing: ${style.letterSpacing}px`} min={0} max={12} value={style.letterSpacing} onChange={(v) => update({ letterSpacing: v })} />
                <RangeInput label={`Line H: ${style.lineHeight}`} min={10} max={24} value={Math.round(style.lineHeight * 10)} onChange={(v) => update({ lineHeight: v / 10 })} />
              </div>
              <div className="flex gap-4 mt-3">
                <Checkbox label="UPPERCASE" checked={style.uppercase} onChange={(v) => update({ uppercase: v })} />
                <Checkbox label="Italic" checked={style.italic} onChange={(v) => update({ italic: v })} />
              </div>
            </Section>

            <Section title="Colors & Effects">
              <div className="grid grid-cols-2 gap-3">
                <ColorPicker label="Text Color" value={style.color} onChange={(v) => update({ color: v })} />
                <ColorPicker label="Background" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
                {isModernHookStyle && <ColorPicker label="Template Accent" value={style.lineColor} onChange={(v) => update({ lineColor: v })} />}
              </div>
              <RangeInput label={`BG Opacity: ${Math.round(style.bgOpacity * 100)}%`} min={0} max={100} value={Math.round(style.bgOpacity * 100)} onChange={(v) => update({ bgOpacity: v / 100 })} />
              <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text gradient" checked={style.gradientEnabled} onChange={(v) => update({ gradientEnabled: v })} disabled={!capabilities.gradient} />
                  {!capabilities.gradient && <UnavailableHint text="Style ini memakai warna solid dari template." />}
                  {style.gradientEnabled && capabilities.gradient && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="From" value={style.gradientFrom} onChange={(v) => update({ gradientFrom: v })} />
                      <ColorPicker label="To" value={style.gradientTo} onChange={(v) => update({ gradientTo: v })} />
                      <RangeInput label={`Angle: ${style.gradientAngle}deg`} min={0} max={360} value={style.gradientAngle} onChange={(v) => update({ gradientAngle: v })} />
                    </div>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text shadow" checked={style.shadowEnabled} onChange={(v) => update({ shadowEnabled: v })} />
                  {style.shadowEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Shadow" value={style.shadowColor} onChange={(v) => update({ shadowColor: v })} />
                      <RangeInput label={`Blur: ${style.shadowBlur}`} min={0} max={40} value={style.shadowBlur} onChange={(v) => update({ shadowBlur: v })} />
                      <div className="grid grid-cols-2 gap-2">
                        <RangeInput label={`X: ${style.shadowX}`} min={-10} max={10} value={style.shadowX} onChange={(v) => update({ shadowX: v })} />
                        <RangeInput label={`Y: ${style.shadowY}`} min={-10} max={10} value={style.shadowY} onChange={(v) => update({ shadowY: v })} />
                      </div>
                    </div>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text glow" checked={style.glowEnabled} onChange={(v) => update({ glowEnabled: v })} />
                  {style.glowEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Glow Color" value={style.glowColor} onChange={(v) => update({ glowColor: v })} />
                      <RangeInput label={`Glow Size: ${style.glowSize}px`} min={5} max={70} value={style.glowSize} onChange={(v) => update({ glowSize: v })} />
                    </div>
                  )}
                </div>
              </div>
            </Section>

            <Section title="Position">
              <div className="grid grid-cols-3 gap-2 mb-3">
                {(["top", "center", "bottom"] as const).map((p) => {
                  const isSelected = (style.positionY != null ? (style.positionY <= 35 ? "top" : style.positionY >= 65 ? "bottom" : "center") : style.position) === p;
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => update({ position: p, positionY: p === "top" ? 20 : p === "bottom" ? 80 : 50 })}
                      className={cn(
                        "py-2 rounded-lg border text-[11px] font-medium capitalize transition-colors",
                        isSelected ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600"
                      )}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
              <RangeInput
                label={`Vertical: ${style.positionY}%`}
                min={5}
                max={95}
                value={style.positionY}
                onChange={(v) => update({
                  positionY: v,
                  position: v <= 35 ? "top" : v >= 65 ? "bottom" : "center",
                })}
              />
            </Section>

            <Section title="Accent Line">
              <Checkbox label="Enable accent line" checked={style.lineEnabled} onChange={(v) => update({ lineEnabled: v })} />
              {style.lineEnabled && (
                <div className="mt-3 space-y-3">
                  <div className="grid grid-cols-7 gap-2">
                    {(["top", "center-h", "bottom", "left", "center-v", "right", "auto-bottom"] as const).map((p) => (
                      <button key={p} type="button" onClick={() => update({ linePosition: p })} className={cn("py-1.5 rounded-lg border text-[10px] font-medium capitalize transition-colors", style.linePosition === p ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-700 text-zinc-400")}>{p.replace("-h", " <>").replace("-v", " ^").replace("auto-bottom", "Auto")}</button>
                    ))}
                  </div>
                  <Checkbox label="Auto-adjust width (match text)" checked={style.lineAutoWidth} onChange={(v) => update({ lineAutoWidth: v, lineWidth: v ? 80 : style.lineWidth })} />
                  <div className="grid grid-cols-4 gap-3">
                    <ColorPicker label="Color" value={style.lineColor} onChange={(v) => update({ lineColor: v })} />
                    {!style.lineAutoWidth && <RangeInput label={`Width: ${style.lineWidth}%`} min={10} max={100} value={style.lineWidth} onChange={(v) => update({ lineWidth: v })} />}
                    <RangeInput label={`Thick: ${style.lineThickness}px`} min={1} max={12} value={style.lineThickness} onChange={(v) => update({ lineThickness: v })} />
                    <RangeInput label={`Offset: ${style.lineOffset}px`} min={0} max={40} value={style.lineOffset} onChange={(v) => update({ lineOffset: v })} />
                  </div>
                </div>
              )}
            </Section>

            <Section title="Text Box / Outline">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  {capabilities.panel ? (
                    <div className="space-y-2">
                      <p className="text-[10px] font-medium text-zinc-400">Panel / accent surface</p>
                      <ColorPicker label="Panel Color" value={style.boxColor} onChange={(v) => update({ boxColor: v })} />
                      <RangeInput label={`Opacity: ${Math.round(style.boxOpacity * 100)}%`} min={0} max={100} value={Math.round(style.boxOpacity * 100)} onChange={(v) => update({ boxOpacity: v / 100 })} />
                    </div>
                  ) : isModernHookStyle ? (
                    <UnavailableHint text="Template hook ini tidak memakai box/panel tambahan." />
                  ) : (
                    <>
                      <Checkbox label="Box around text" checked={style.boxEnabled} onChange={(v) => update({ boxEnabled: v })} />
                      {style.boxEnabled && (
                        <div className="mt-2 space-y-2">
                          <ColorPicker label="Box Color" value={style.boxColor} onChange={(v) => update({ boxColor: v })} />
                          <RangeInput label={`Opacity: ${Math.round(style.boxOpacity * 100)}%`} min={0} max={100} value={Math.round(style.boxOpacity * 100)} onChange={(v) => update({ boxOpacity: v / 100 })} />
                          <RangeInput label={`Padding: ${style.boxPadding}px`} min={4} max={56} value={style.boxPadding} onChange={(v) => update({ boxPadding: v })} />
                          <RangeInput label={`Radius: ${style.boxRadius}px`} min={0} max={28} value={style.boxRadius} onChange={(v) => update({ boxRadius: v })} />
                        </div>
                      )}
                    </>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Text outline" checked={style.strokeEnabled} onChange={(v) => update({ strokeEnabled: v })} disabled={!capabilities.outline} />
                  {!capabilities.outline && <UnavailableHint text="Outline tidak dipakai oleh template hook ini." />}
                  {style.strokeEnabled && capabilities.outline && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Outline" value={style.strokeColor} onChange={(v) => update({ strokeColor: v })} />
                      <RangeInput label={`Width: ${style.strokeWidth}px`} min={1} max={10} value={style.strokeWidth} onChange={(v) => update({ strokeWidth: v })} />
                    </div>
                  )}
                </div>
              </div>
            </Section>
          </>
        )}
      </div>

      <div className="lg:col-span-4 flex min-h-0 flex-col items-center justify-center overflow-hidden bg-zinc-950 p-4">
        {engine === "hyperframes" ? (
          <HfLivePreview
            preset={hfPreset}
            sample={style.text || hfPreset?.preview || "HOOK TEXT"}
            kind="hook"
            aspectRatio={aspectRatio}
            thumbnailUrl={thumbnailUrl}
            canvas={canvas}
          />
        ) : engine === "ffmpeg" ? (
          <>
            <div className="mb-3 flex w-full items-center justify-between gap-2">
              <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
              <span className="rounded-md border border-purple-500/30 bg-purple-500/10 px-2 py-1 text-[9px] text-purple-300">FFmpeg Drawtext</span>
            </div>
            <CanvasPreviewFrame canvas={canvas} thumbnailUrl={thumbnailUrl}>
              <div className="absolute left-0 right-0 flex items-center justify-center px-3 pointer-events-none" style={{ top: `${style.positionY}%`, transform: "translateY(-50%)" }}>
                <p style={{ fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16), fontWeight: Number(style.fontWeight), fontFamily: style.fontFamily === "monospace" ? "monospace" : `'${style.fontFamily}', sans-serif`, color: style.color, textTransform: style.uppercase ? ("uppercase" as const) : ("none" as const), textAlign: "center" as const, maxWidth: "92%", whiteSpace: "pre-line" as const, wordBreak: "break-word" as const, padding: "4px 8px", backgroundColor: style.bgOpacity > 0 ? `${style.bgColor || "black"}${Math.round(style.bgOpacity * 255).toString(16).padStart(2, "0")}` : "transparent", paintOrder: style.strokeEnabled ? ("stroke" as const) : undefined, WebkitTextStroke: style.strokeEnabled ? `${Math.max(style.strokeWidth * 0.25, 0.6)}px ${style.strokeColor}` : undefined, textShadow: style.shadowEnabled ? `2px 2px 0px ${style.shadowColor}` : undefined }}>
                  {style.text || getHookPreviewSample(style.animation || "zoom_punch")}
                </p>
              </div>
              <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-600 z-10">ffmpeg {style.animation || "zoom_punch"} | {style.duration}s</p>
            </CanvasPreviewFrame>
            <div className="mt-3 grid w-full grid-cols-2 gap-2 text-[10px]">
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Font</span><p className="truncate text-zinc-300">{style.fontFamily}</p></div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Color</span><p className="truncate" style={{ color: style.color }}>{style.color}</p></div>
            </div>
          </>
        ) : engine === "skia" ? (
          <SkiaHookLivePreview style={style} thumbnailUrl={thumbnailUrl} aspectRatio={aspectRatio} canvas={canvas} />
        ) : (
          <>
            <div className="mb-3 flex w-full items-center justify-between gap-2">
              <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
              <span className="rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-[9px] text-zinc-400">{activeAnimation.label}</span>
            </div>
            <CanvasPreviewFrame canvas={canvas} thumbnailUrl={thumbnailUrl}>
              <HookPreviewRenderer style={style} />
              {style.lineEnabled && <AccentLinePreview style={style} />}
              <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-600 z-10">{style.animation.replace(/_/g, " ")} | {style.duration}s</p>
            </CanvasPreviewFrame>
            <div className="mt-3 grid w-full grid-cols-2 gap-2 text-[10px]">
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Font</span><p className="truncate text-zinc-300">{style.fontFamily}</p></div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Style</span><p className="truncate text-zinc-300">{activeAnimation.label}</p></div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
