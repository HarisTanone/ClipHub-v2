import { useState, useEffect } from "react";
import { EyeOff, Check, Zap, Palette, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { FeatureLock } from "@/components/ui/FeatureLock";
import { buildCanvasConfig } from "@/lib/canvasTemplates";
import { cn } from "@/lib/utils";
import {
  defaultHfSubtitleId,
  HF_SUBTITLE_STYLES,
  FFMPEG_SUBTITLE_PRESETS,
  SKIA_SUBTITLE_PRESETS,
} from "@/lib/renderEngines";
import type { SubtitleStyle, OptionMeta } from "../types";
import {
  DEFAULT_SUBTITLE_STYLE,
  SUBTITLE_PRESETS,
  SUBTITLE_TRANSITION_META,
  SUBTITLE_ANIMATION_META,
  HIGHLIGHT_STYLE_META,
  FONT_OPTIONS,
  SUBTITLE_FONT_SUGGESTIONS,
  HIGHLIGHT_FONT_SUGGESTIONS,
} from "../types";
import { useGoogleFont, getPageItems, getSubAnimationClass } from "../utils";
import { Section, ColorPicker, RangeInput, Checkbox, SelectSmall } from "../ui/CommonControls";
import { TimingOptionCard, MetaTile, FontChips } from "../ui/MetaTile";
import { PaginationControls } from "../ui/PaginationControls";
import { EnginePicker } from "../ui/EnginePicker";
import { SubtitlePresetCard } from "../cards/SubtitlePresetCard";
import { CanvasPreviewFrame } from "../preview/CanvasPreviewFrame";
import { HfStyleGrid } from "../preview/HfStyleGrid";
import { HfLivePreview } from "../preview/HfLivePreview";
import { SkiaSubtitleLivePreview } from "../preview/SkiaSubtitleLivePreview";

export function SubtitleEditor({
  style,
  onChange,
  isSuperadmin = false,
  isPremium = false,
  userFeatures = [],
  aspectRatio = "9:16",
  thumbnailUrl,
  canvasBackground,
}: {
  style: SubtitleStyle;
  onChange: (style: SubtitleStyle) => void;
  isSuperadmin?: boolean;
  isPremium?: boolean;
  userFeatures?: string[];
  aspectRatio?: string;
  thumbnailUrl?: string;
  canvasBackground?: any;
}) {
  const engine = style.engine || "remotion";
  const [activeWordIdx, setActiveWordIdx] = useState(0);
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [newWord, setNewWord] = useState("");
  const [presetPage, setPresetPage] = useState(1);
  const [timingPage, setTimingPage] = useState(1);
  const hfId = style.hf_template || defaultHfSubtitleId();
  const hfPreset = HF_SUBTITLE_STYLES.find((h) => h.id === hfId) || HF_SUBTITLE_STYLES[0];
  useGoogleFont(style.fontFamily);
  if (style.dualStyleEnabled && style.highlightFontFamily) {
    useGoogleFont(style.highlightFontFamily);
  }
  const update = (patch: Partial<SubtitleStyle>) => onChange({ ...style, ...patch });

  function addHighlightWord() {
    if (newWord.trim() && !(style.highlightWords || []).includes(newWord.trim().toLowerCase())) {
      update({ highlightWords: [...(style.highlightWords || []), newWord.trim().toLowerCase()] });
      setNewWord("");
    }
  }
  const canvas = (aspectRatio === "16:9" || aspectRatio === "1:1")
    ? buildCanvasConfig(aspectRatio, {
      backgroundMode: canvasBackground?.mode || "template",
      templateId: canvasBackground?.templateId || "dark-studio",
      backgroundImageUrl: canvasBackground?.imageDataUrl || null,
    })
    : null;

  const subtitleTimingOptions: Array<
    { kind: "transition"; id: SubtitleStyle["lineTransition"]; meta: OptionMeta } |
    { kind: "animation"; id: SubtitleStyle["animationStyle"]; meta: OptionMeta }
  > = [
    { kind: "transition", id: "word_pop", meta: SUBTITLE_TRANSITION_META.word_pop },
    { kind: "transition", id: "emphasis", meta: SUBTITLE_TRANSITION_META.emphasis },
    { kind: "transition", id: "line_reveal", meta: SUBTITLE_TRANSITION_META.line_reveal },
    { kind: "animation", id: "pop", meta: SUBTITLE_ANIMATION_META.pop },
    { kind: "animation", id: "fade", meta: SUBTITLE_ANIMATION_META.fade },
    { kind: "animation", id: "slide", meta: SUBTITLE_ANIMATION_META.slide },
    { kind: "animation", id: "none", meta: SUBTITLE_ANIMATION_META.none },
  ];
  const [ffmpegSubPage, setFfmpegSubPage] = useState(1);
  const [skiaSubPage, setSkiaSubPage] = useState(1);
  const visibleSubtitlePresets = getPageItems(SUBTITLE_PRESETS, presetPage);
  const visibleSubtitleTiming = getPageItems(subtitleTimingOptions, timingPage);
  const visibleFfmpegSubs = getPageItems(FFMPEG_SUBTITLE_PRESETS, ffmpegSubPage);
  const visibleSkiaSubs = getPageItems(SKIA_SUBTITLE_PRESETS, skiaSubPage);
  const activeTimingMeta = SUBTITLE_TRANSITION_META[style.lineTransition] || SUBTITLE_ANIMATION_META[style.animationStyle];

  useEffect(() => {
    if (!isSuperadmin && (engine === "remotion" || engine === "hyperframes")) {
      update({ engine: "ffmpeg" });
    }
  }, [engine, isSuperadmin]);

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveWordIdx((prev) => (prev + 1) % 4);
    }, 800);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 h-full min-h-0 overflow-hidden">
      <div className="lg:col-span-8 p-4 overflow-y-auto space-y-4 border-r border-zinc-800 min-h-0">
        <Section title="Subtitle Toggle">
          <div className="flex items-center justify-between p-3.5 rounded-xl border border-zinc-800 bg-zinc-900/60 backdrop-blur">
            <div className="flex items-center gap-3">
              <div className={cn(
                "w-9 h-9 rounded-lg flex items-center justify-center border transition-colors",
                style.enabled !== false
                  ? "bg-purple-500/10 border-purple-500/30 text-purple-400"
                  : "bg-zinc-800/80 border-zinc-700 text-zinc-500"
              )}>
                {style.enabled !== false ? <Check className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
              </div>
              <div>
                <p className="text-xs font-semibold text-zinc-200">
                  {style.enabled !== false ? "Gunakan Subtitle (Active)" : "Subtitle Dinonaktifkan (Disabled)"}
                </p>
                <p className="text-[11px] text-zinc-400">
                  {style.enabled !== false
                    ? "Subtitle karaoke / word-pop akan dirender pada video final."
                    : "Video final akan dirender bersih tanpa subtitle overlay."}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => update({ enabled: style.enabled === false ? true : false })}
              className={cn(
                "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none",
                style.enabled !== false ? "bg-purple-600 ring-2 ring-purple-500/30" : "bg-zinc-700"
              )}
            >
              <span
                className={cn(
                  "pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out",
                  style.enabled !== false ? "translate-x-5" : "translate-x-0"
                )}
              />
            </button>
          </div>
        </Section>

        <Section title="Render Engine">
          <EnginePicker
            engine={engine}
            kind="subtitle"
            isSuperadmin={isSuperadmin}
            onChange={(e) => update({
              engine: e,
              hf_template: style.hf_template || defaultHfSubtitleId(),
            })}
          />
        </Section>

        {engine === "hyperframes" ? (
          <Section title="HyperFrames Subtitle Styles">
            <HfStyleGrid
              items={HF_SUBTITLE_STYLES}
              activeId={hfId}
              onSelect={(id) => update({ engine: "hyperframes", hf_template: id })}
            />
          </Section>
        ) : engine === "ffmpeg" ? (
          <>
            <Section title="FFmpeg Drawtext">
              <div className="rounded-lg border border-purple-500/20 bg-purple-500/5 p-3">
                <p className="text-[10px] text-purple-300 mb-1"><Zap className="inline w-3 h-3 mr-1" />Server-side render · no browser needed</p>
                <p className="text-[9px] text-zinc-500">FFmpeg drawtext subtitle. 12 Preset gaya subtitle dengan performa instan.</p>
              </div>
            </Section>

            <Section title="FFmpeg Subtitle Presets">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {visibleFfmpegSubs.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => {
                      update({
                        stylePreset: p.id,
                        color: p.color,
                        highlightColor: p.highlightColor,
                        fontFamily: p.fontFamily,
                        fontSize: p.fontSize,
                        fontWeight: p.fontWeight,
                        lineTransition: p.lineTransition,
                        strokeEnabled: p.strokeEnabled,
                        strokeWidth: p.strokeWidth,
                        strokeColor: p.strokeColor,
                        bgEnabled: p.bgEnabled,
                        bgColor: p.bgColor,
                        bgOpacity: p.bgOpacity,
                        bgRadius: p.bgRadius,
                        position: p.positionY <= 35 ? "top" : p.positionY >= 65 ? "bottom" : "center",
                        positionY: p.positionY,
                        uppercase: p.uppercase,
                        maxWordsPerLine: p.maxWordsPerLine,
                        engine: "ffmpeg",
                      });
                      setActivePreset(p.id);
                    }}
                    className={cn(
                      "group overflow-hidden rounded-xl border text-left transition-all p-3",
                      activePreset === p.id || style.stylePreset === p.id
                        ? "border-purple-500 bg-purple-500/10 ring-1 ring-purple-500/40"
                        : "border-zinc-700/80 bg-zinc-900/40 hover:border-zinc-500 hover:bg-zinc-900"
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[11px] font-semibold text-zinc-200">{p.name}</p>
                      <span className="rounded px-1.5 py-0.5 text-[8px] font-bold uppercase text-purple-400 bg-purple-500/10 border border-purple-500/30">
                        {p.category}
                      </span>
                    </div>
                    <p className="text-[9px] text-zinc-500 mt-1 line-clamp-2">{p.desc}</p>
                  </button>
                ))}
              </div>
              <PaginationControls page={ffmpegSubPage} totalItems={FFMPEG_SUBTITLE_PRESETS.length} onPageChange={setFfmpegSubPage} label="presets" />
            </Section>

            <Section title="Line Transition">
              <div className="grid grid-cols-3 gap-2">
                {([
                  { id: "word_pop", name: "Word Pop", desc: "Satu kata per frame" },
                  { id: "emphasis", name: "Emphasis", desc: "Highlight kata aktif" },
                  { id: "line_reveal", name: "Line Reveal", desc: "Full line timed" },
                ] as const).map((mode) => (
                  <button
                    key={mode.id}
                    type="button"
                    onClick={() => update({ lineTransition: mode.id })}
                    className={cn(
                      "py-2 px-2 rounded-lg border text-center transition-colors",
                      style.lineTransition === mode.id
                        ? "border-purple-500 bg-purple-500/10"
                        : "border-zinc-700 hover:border-zinc-600"
                    )}
                  >
                    <p className="text-[10px] font-medium text-zinc-200">{mode.name}</p>
                    <p className="text-[8px] text-zinc-500 mt-0.5">{mode.desc}</p>
                  </button>
                ))}
              </div>
            </Section>

            <Section title="Typography">
              <FontChips fonts={SUBTITLE_FONT_SUGGESTIONS} active={style.fontFamily} onSelect={(fontFamily) => update({ fontFamily })} />
              <div className="grid grid-cols-3 gap-3 mt-3">
                <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={FONT_OPTIONS.filter((font) => font !== "monospace")} />
                <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                <RangeInput label={`Size: ${style.fontSize}px`} min={20} max={60} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
              </div>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <RangeInput label={`Spacing: ${style.letterSpacing}px`} min={0} max={8} value={style.letterSpacing} onChange={(v) => update({ letterSpacing: v })} />
                <RangeInput label={`Line H: ${style.lineHeight}`} min={10} max={24} value={Math.round(style.lineHeight * 10)} onChange={(v) => update({ lineHeight: v / 10 })} />
              </div>
              <div className="flex gap-4 mt-3">
                <Checkbox label="UPPERCASE" checked={style.uppercase} onChange={(v) => update({ uppercase: v, capitalize: v ? false : style.capitalize })} />
                <Checkbox label="Capitalize" checked={style.capitalize} onChange={(v) => update({ capitalize: v, uppercase: v ? false : style.uppercase })} />
                <Checkbox label="Italic" checked={style.italic} onChange={(v) => update({ italic: v })} />
              </div>
            </Section>

            <Section title="Colors">
              <div className="grid grid-cols-3 gap-3">
                <ColorPicker label="Text" value={style.color} onChange={(v) => update({ color: v })} />
                <ColorPicker label="Highlight" value={style.highlightColor} onChange={(v) => update({ highlightColor: v })} />
                <ColorPicker label="BG" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
              </div>
            </Section>

            <Section title="Background & Stroke">
              <div className="grid grid-cols-2 gap-3">
                <div><Checkbox label="Background" checked={style.bgEnabled} onChange={(v) => update({ bgEnabled: v })} /></div>
                <div><Checkbox label="Stroke/Outline" checked={style.strokeEnabled} onChange={(v) => update({ strokeEnabled: v })} /></div>
              </div>
              {style.bgEnabled && (
                <div className="grid grid-cols-3 gap-3 mt-2">
                  <RangeInput label={`Opacity: ${Math.round(style.bgOpacity * 100)}%`} min={0} max={100} value={Math.round(style.bgOpacity * 100)} onChange={(v) => update({ bgOpacity: v / 100 })} />
                  <RangeInput label={`Radius: ${style.bgRadius}px`} min={0} max={24} value={style.bgRadius} onChange={(v) => update({ bgRadius: v })} />
                  <RangeInput label={`Padding: ${style.bgPadding}px`} min={4} max={32} value={style.bgPadding} onChange={(v) => update({ bgPadding: v })} />
                </div>
              )}
              {style.strokeEnabled && (
                <div className="grid grid-cols-2 gap-3 mt-2">
                  <ColorPicker label="Stroke" value={style.strokeColor} onChange={(v) => update({ strokeColor: v })} />
                  <RangeInput label={`Width: ${style.strokeWidth}px`} min={1} max={6} value={style.strokeWidth} onChange={(v) => update({ strokeWidth: v })} />
                </div>
              )}
              <div className="mt-2"><Checkbox label="Text shadow" checked={style.shadowEnabled} onChange={(v) => update({ shadowEnabled: v })} /></div>
              {style.shadowEnabled && (
                <div className="grid grid-cols-2 gap-3 mt-2">
                  <ColorPicker label="Shadow" value={style.shadowColor} onChange={(v) => update({ shadowColor: v })} />
                  <RangeInput label={`Blur: ${style.shadowBlur}px`} min={0} max={20} value={style.shadowBlur} onChange={(v) => update({ shadowBlur: v })} />
                </div>
              )}
            </Section>

            <Section title="Position">
              <div className="grid grid-cols-3 gap-2 mb-3">
                {(["top", "center", "bottom"] as const).map((p) => {
                  const isSelected = (style.positionY != null ? (style.positionY <= 35 ? "top" : style.positionY >= 65 ? "bottom" : "center") : style.position) === p;
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => update({ position: p, positionY: p === "top" ? 15 : p === "bottom" ? 85 : 50 })}
                      className={cn(
                        "py-2 rounded-lg border text-[11px] font-medium capitalize transition-colors",
                        isSelected ? "border-purple-500 bg-purple-500/10 text-purple-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600"
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

            <Section title="Line Settings">
              <div className="grid grid-cols-2 gap-3">
                <RangeInput label={`Words/line: ${style.maxWordsPerLine}`} min={1} max={6} value={style.maxWordsPerLine} onChange={(v) => update({ maxWordsPerLine: v })} />
                <RangeInput label={`Word gap: ${style.wordSpacing}px`} min={2} max={18} value={style.wordSpacing} onChange={(v) => update({ wordSpacing: v })} />
              </div>
            </Section>
          </>
        ) : engine === "skia" ? (
          <>
            <Section title="Skia Render Engine">
              <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                <p className="text-[10px] text-amber-400 mb-1"><Palette className="inline w-3 h-3 mr-1" />Canvas GPU Rendering</p>
                <p className="text-[9px] text-zinc-500">Subtitle dengan 12 preset visual modern & clean (Glassmorphism, Clean Editorial, Podcast Pro, Kinetic Word Box, dll).</p>
              </div>
            </Section>

            <Section title="Skia Subtitle Presets">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {visibleSkiaSubs.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => {
                      update({
                        stylePreset: p.id,
                        color: p.color,
                        highlightColor: p.highlightColor,
                        fontFamily: p.fontFamily,
                        fontSize: p.fontSize,
                        fontWeight: p.fontWeight,
                        uppercase: p.uppercase,
                        lineTransition: p.lineTransition,
                        gradientEnabled: p.gradientEnabled,
                        gradientFrom: p.gradientFrom,
                        gradientTo: p.gradientTo,
                        glowEnabled: p.glowEnabled,
                        glowColor: p.glowColor,
                        position: p.positionY <= 35 ? "top" : p.positionY >= 65 ? "bottom" : "center",
                        positionY: p.positionY,
                        maxWordsPerLine: p.maxWordsPerLine,
                        engine: "skia",
                      });
                      setActivePreset(p.id);
                    }}
                    className={cn(
                      "group overflow-hidden rounded-xl border text-left transition-all p-3",
                      activePreset === p.id || style.stylePreset === p.id
                        ? "border-amber-500 bg-amber-500/10 ring-1 ring-amber-500/40"
                        : "border-zinc-700/80 bg-zinc-900/40 hover:border-zinc-500 hover:bg-zinc-900"
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[11px] font-semibold text-zinc-200">{p.name}</p>
                      <span className="rounded px-1.5 py-0.5 text-[8px] font-bold uppercase text-amber-400 bg-amber-500/10 border border-amber-500/30">
                        {p.category}
                      </span>
                    </div>
                    <p className="text-[9px] text-zinc-500 mt-1 line-clamp-2">{p.desc}</p>
                  </button>
                ))}
              </div>
              <PaginationControls page={skiaSubPage} totalItems={SKIA_SUBTITLE_PRESETS.length} onPageChange={setSkiaSubPage} label="presets" />
            </Section>

            <Section title="Line Transition">
              <div className="grid grid-cols-3 gap-2">
                {([
                  { id: "karaoke", name: "Karaoke", desc: "Per-word highlight" },
                  { id: "word_pop", name: "Word Pop", desc: "Satu kata per frame" },
                  { id: "line_reveal", name: "Line Reveal", desc: "Full line reveal" },
                ] as const).map((mode) => (
                  <button
                    key={mode.id}
                    type="button"
                    onClick={() => update({ lineTransition: mode.id })}
                    className={cn(
                      "py-2 px-2 rounded-lg border text-center transition-colors",
                      style.lineTransition === mode.id
                        ? "border-amber-500 bg-amber-500/10"
                        : "border-zinc-700 hover:border-zinc-600"
                    )}
                  >
                    <p className="text-[10px] font-medium text-zinc-200">{mode.name}</p>
                    <p className="text-[8px] text-zinc-500 mt-0.5">{mode.desc}</p>
                  </button>
                ))}
              </div>
            </Section>

            <Section title="Typography">
              <FontChips fonts={SUBTITLE_FONT_SUGGESTIONS} active={style.fontFamily} onSelect={(fontFamily) => update({ fontFamily })} />
              <div className="grid grid-cols-3 gap-3 mt-3">
                <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={FONT_OPTIONS.filter((font) => font !== "monospace")} />
                <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                <RangeInput label={`Size: ${style.fontSize}px`} min={20} max={60} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
              </div>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <RangeInput label={`Spacing: ${style.letterSpacing}px`} min={0} max={8} value={style.letterSpacing} onChange={(v) => update({ letterSpacing: v })} />
                <RangeInput label={`Line H: ${style.lineHeight}`} min={10} max={24} value={Math.round(style.lineHeight * 10)} onChange={(v) => update({ lineHeight: v / 10 })} />
              </div>
              <div className="flex gap-4 mt-3">
                <Checkbox label="UPPERCASE" checked={style.uppercase} onChange={(v) => update({ uppercase: v, capitalize: v ? false : style.capitalize })} />
                <Checkbox label="Italic" checked={style.italic} onChange={(v) => update({ italic: v })} />
              </div>
            </Section>

            <Section title="Colors & GPU Effects">
              <div className="grid grid-cols-3 gap-3">
                <ColorPicker label="Text" value={style.color} onChange={(v) => update({ color: v })} />
                <ColorPicker label="Highlight" value={style.highlightColor} onChange={(v) => update({ highlightColor: v })} />
                <ColorPicker label="BG" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
              </div>
              <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Glow shader" checked={!!style.glowEnabled} onChange={(v) => update({ glowEnabled: v })} />
                  {style.glowEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Glow Color" value={style.glowColor || "#00FFFF"} onChange={(v) => update({ glowColor: v })} />
                    </div>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Gradient shader" checked={!!style.gradientEnabled} onChange={(v) => update({ gradientEnabled: v })} />
                  {style.gradientEnabled && (
                    <div className="mt-2 space-y-2">
                      <ColorPicker label="Grad From" value={style.gradientFrom || "#667EEA"} onChange={(v) => update({ gradientFrom: v })} />
                      <ColorPicker label="Grad To" value={style.gradientTo || "#764BA2"} onChange={(v) => update({ gradientTo: v })} />
                    </div>
                  )}
                </div>
              </div>
            </Section>

            <Section title="Backdrop & Card Capsule">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Enable Card/Pill Capsule" checked={style.bgEnabled} onChange={(v) => update({ bgEnabled: v })} />
                  {style.bgEnabled && (
                    <div className="mt-3 space-y-3">
                      <ColorPicker label="Capsule Color" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
                      <RangeInput label={`Opacity: ${Math.round(style.bgOpacity * 100)}%`} min={10} max={100} value={Math.round(style.bgOpacity * 100)} onChange={(v) => update({ bgOpacity: v / 100 })} />
                      <RangeInput label={`Radius: ${style.bgRadius}px`} min={0} max={40} value={style.bgRadius} onChange={(v) => update({ bgRadius: v })} />
                      <RangeInput label={`Padding: ${style.bgPadding}px`} min={4} max={32} value={style.bgPadding} onChange={(v) => update({ bgPadding: v })} />
                    </div>
                  )}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                  <Checkbox label="Active Word Scale" checked={style.highlightBold} onChange={(v) => update({ highlightBold: v })} />
                  <div className="mt-3 space-y-3">
                    <RangeInput label={`Highlight Scale: ${style.highlightScale.toFixed(1)}x`} min={10} max={16} value={Math.round(style.highlightScale * 10)} onChange={(v) => update({ highlightScale: v / 10 })} />
                    <Checkbox label="Text Outline / Stroke" checked={style.strokeEnabled} onChange={(v) => update({ strokeEnabled: v })} />
                    {style.strokeEnabled && (
                      <div className="mt-2 space-y-2">
                        <ColorPicker label="Outline Color" value={style.strokeColor} onChange={(v) => update({ strokeColor: v })} />
                        <RangeInput label={`Width: ${style.strokeWidth}px`} min={1} max={8} value={style.strokeWidth} onChange={(v) => update({ strokeWidth: v })} />
                      </div>
                    )}
                  </div>
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
                      onClick={() => update({ position: p, positionY: p === "top" ? 15 : p === "bottom" ? 85 : 50 })}
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

            <Section title="Line Settings">
              <div className="grid grid-cols-2 gap-3">
                <RangeInput label={`Words/line: ${style.maxWordsPerLine}`} min={1} max={6} value={style.maxWordsPerLine} onChange={(v) => update({ maxWordsPerLine: v })} />
                <RangeInput label={`Word gap: ${style.wordSpacing}px`} min={2} max={18} value={style.wordSpacing} onChange={(v) => update({ wordSpacing: v })} />
              </div>
            </Section>
          </>
        ) : (
          <>
            <Section title="Quick Presets">
              <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-2">
                {visibleSubtitlePresets.map((p) => (
                  <SubtitlePresetCard
                    key={p.id}
                    preset={p}
                    active={activePreset === p.id}
                    onClick={() => {
                      onChange({ ...DEFAULT_SUBTITLE_STYLE, ...p.style, highlightWords: style.highlightWords, engine: "remotion" } as SubtitleStyle);
                      setActivePreset(p.id);
                    }}
                  />
                ))}
              </div>
              <PaginationControls page={presetPage} totalItems={SUBTITLE_PRESETS.length} onPageChange={setPresetPage} label="presets" />
            </Section>

            <Section title="Animation & Timing">
              <div className="mb-3 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950/70">
                <div className="flex items-center justify-between gap-3 border-b border-zinc-800 px-3 py-2">
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold text-zinc-200">{activeTimingMeta.label}</p>
                    <p className="truncate text-[9px] text-zinc-500">{activeTimingMeta.desc}</p>
                  </div>
                  <span className="rounded-md px-2 py-1 text-[9px] font-black" style={{ color: activeTimingMeta.accent, backgroundColor: `${activeTimingMeta.accent}18`, border: `1px solid ${activeTimingMeta.accent}44` }}>{activeTimingMeta.mood}</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3">
                  <RangeInput label={`Speed: ${style.animationSpeed.toFixed(1)}x`} min={5} max={20} value={Math.round(style.animationSpeed * 10)} onChange={(v) => update({ animationSpeed: v / 10 })} />
                  <RangeInput label={`Words/line: ${style.maxWordsPerLine}`} min={1} max={6} value={style.maxWordsPerLine} onChange={(v) => update({ maxWordsPerLine: v })} />
                  <RangeInput label={`Word gap: ${style.wordSpacing}px`} min={2} max={18} value={style.wordSpacing} onChange={(v) => update({ wordSpacing: v })} />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3 gap-2">
                {visibleSubtitleTiming.map((option) => (
                  <div key={`${option.kind}-${option.id}`} className="relative">
                    <TimingOptionCard
                      meta={option.meta}
                      active={option.kind === "transition" ? style.lineTransition === option.id : style.animationStyle === option.id}
                      onClick={() => option.kind === "transition" ? update({ lineTransition: option.id }) : update({ animationStyle: option.id })}
                      kind={option.kind === "transition" ? "line" : "motion"}
                    />
                  </div>
                ))}
              </div>
              <PaginationControls page={timingPage} totalItems={subtitleTimingOptions.length} onPageChange={setTimingPage} label="timing options" />
            </Section>

            <Section title="Typography">
              <FontChips fonts={SUBTITLE_FONT_SUGGESTIONS} active={style.fontFamily} onSelect={(fontFamily) => update({ fontFamily })} />
              <div className="grid grid-cols-3 gap-3 mt-3">
                <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={FONT_OPTIONS.filter((font) => font !== "monospace")} />
                <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                <RangeInput label={`Size: ${style.fontSize}px`} min={20} max={60} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
              </div>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <RangeInput label={`Spacing: ${style.letterSpacing}px`} min={0} max={8} value={style.letterSpacing} onChange={(v) => update({ letterSpacing: v })} />
                <RangeInput label={`Line H: ${style.lineHeight}`} min={10} max={24} value={Math.round(style.lineHeight * 10)} onChange={(v) => update({ lineHeight: v / 10 })} />
              </div>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <RangeInput
                  label={`Opacity: ${Math.round((style.textOpacity ?? 1.0) * 100)}%`}
                  min={20}
                  max={100}
                  value={Math.round((style.textOpacity ?? 1.0) * 100)}
                  onChange={(v) => update({ textOpacity: v / 100 })}
                />
                <div>
                  <p className="text-[9px] text-zinc-400 mb-1">Alignment</p>
                  <div className="grid grid-cols-3 gap-1">
                    {(["left", "center", "right"] as const).map((align) => (
                      <button
                        key={align}
                        type="button"
                        onClick={() => update({ textAlign: align })}
                        className={cn(
                          "py-1 rounded border text-[10px] capitalize transition-colors",
                          (style.textAlign || "center") === align
                            ? "border-purple-500 bg-purple-500/20 text-purple-300 font-bold"
                            : "border-zinc-700 text-zinc-400 hover:border-zinc-600"
                        )}
                      >
                        {align}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex gap-4 mt-3">
                <Checkbox label="UPPERCASE" checked={style.uppercase} onChange={(v) => update({ uppercase: v, capitalize: v ? false : style.capitalize })} />
                <Checkbox label="Capitalize" checked={style.capitalize} onChange={(v) => update({ capitalize: v, uppercase: v ? false : style.uppercase })} />
                <Checkbox label="Italic" checked={style.italic} onChange={(v) => update({ italic: v })} />
              </div>
            </Section>

            <Section title="Colors">
              <div className="grid grid-cols-3 gap-3">
                <ColorPicker label="Text" value={style.color} onChange={(v) => update({ color: v })} />
                <ColorPicker label="Highlight" value={style.highlightColor} onChange={(v) => update({ highlightColor: v })} />
                <ColorPicker label="BG" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
              </div>
            </Section>

            <Section title="Highlight Effect">
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 mb-3">
                {(["scale", "underline", "background", "strikethrough"] as const).map((s) => (
                  <MetaTile key={s} meta={HIGHLIGHT_STYLE_META[s]} active={style.highlightStyle === s} onClick={() => update({ highlightStyle: s })} />
                ))}
              </div>
              <div className="grid grid-cols-3 gap-3">
                <RangeInput label={`Scale: ${style.highlightScale.toFixed(1)}x`} min={10} max={20} value={Math.round(style.highlightScale * 10)} onChange={(v) => update({ highlightScale: v / 10 })} />
                <div className="flex flex-col justify-end"><Checkbox label="Bold" checked={style.highlightBold} onChange={(v) => update({ highlightBold: v })} /></div>
                <div className="flex flex-col justify-end"><Checkbox label="Glow" checked={style.highlightGlow} onChange={(v) => update({ highlightGlow: v })} /></div>
              </div>
              {style.highlightGlow && (
                <div className="grid grid-cols-2 gap-3 mt-2">
                  <ColorPicker label="Glow Color" value={style.highlightGlowColor} onChange={(v) => update({ highlightGlowColor: v })} />
                </div>
              )}
            </Section>

            <Section title="Dual Font Style (Highlight Words)">
              <FeatureLock featureName="Dual Font Style" featureCode="dual_subtitle" isSuperadmin={isSuperadmin} isPremium={isPremium} userFeatures={userFeatures}>
                <Checkbox label="Use separate style for highlight words" checked={style.dualStyleEnabled} onChange={(v) => update({ dualStyleEnabled: v })} />
                <p className="text-[9px] text-zinc-600 mt-1 mb-2">Kata-kata penting (MAKANYA, JANGAN, dll) akan menggunakan font & style berbeda dari teks normal.</p>
                {style.dualStyleEnabled && (
                  <div className="mt-3 p-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 space-y-3">
                    <p className="text-[10px] text-emerald-400 font-medium uppercase tracking-wider">Highlight Word Style</p>
                    <FontChips fonts={HIGHLIGHT_FONT_SUGGESTIONS} active={style.highlightFontFamily} onSelect={(highlightFontFamily) => update({ highlightFontFamily })} />
                    <div className="grid grid-cols-3 gap-3">
                      <SelectSmall label="Font" value={style.highlightFontFamily} onChange={(v) => update({ highlightFontFamily: v })} options={FONT_OPTIONS.filter((font) => font !== "monospace")} />
                      <SelectSmall label="Weight" value={style.highlightFontWeight} onChange={(v) => update({ highlightFontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                      <RangeInput label={`Size: ${style.highlightFontSize}px`} min={24} max={64} value={style.highlightFontSize} onChange={(v) => update({ highlightFontSize: v })} />
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                      <RangeInput label={`Spacing: ${style.highlightLetterSpacing}px`} min={0} max={8} value={style.highlightLetterSpacing} onChange={(v) => update({ highlightLetterSpacing: v })} />
                      <div className="flex flex-col justify-end"><Checkbox label="UPPERCASE" checked={style.highlightUppercase} onChange={(v) => update({ highlightUppercase: v })} /></div>
                      <div className="flex flex-col justify-end"><Checkbox label="Italic" checked={style.highlightItalic} onChange={(v) => update({ highlightItalic: v })} /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div><Checkbox label="Stroke" checked={style.highlightStrokeEnabled} onChange={(v) => update({ highlightStrokeEnabled: v })} /></div>
                      <div><Checkbox label="Shadow" checked={style.highlightShadowEnabled} onChange={(v) => update({ highlightShadowEnabled: v })} /></div>
                    </div>
                    {style.highlightStrokeEnabled && (
                      <div className="grid grid-cols-2 gap-3">
                        <ColorPicker label="Stroke Color" value={style.highlightStrokeColor} onChange={(v) => update({ highlightStrokeColor: v })} />
                        <RangeInput label={`Width: ${style.highlightStrokeWidth}px`} min={1} max={6} value={style.highlightStrokeWidth} onChange={(v) => update({ highlightStrokeWidth: v })} />
                      </div>
                    )}
                    {style.highlightShadowEnabled && (
                      <div className="grid grid-cols-2 gap-3">
                        <ColorPicker label="Shadow Color" value={style.highlightShadowColor} onChange={(v) => update({ highlightShadowColor: v })} />
                        <RangeInput label={`Blur: ${style.highlightShadowBlur}px`} min={0} max={20} value={style.highlightShadowBlur} onChange={(v) => update({ highlightShadowBlur: v })} />
                      </div>
                    )}
                  </div>
                )}
              </FeatureLock>
            </Section>

            <Section title="Background & Stroke">
              <div className="grid grid-cols-2 gap-3">
                <div><Checkbox label="Background" checked={style.bgEnabled} onChange={(v) => update({ bgEnabled: v })} /></div>
                <div><Checkbox label="Stroke/Outline" checked={style.strokeEnabled} onChange={(v) => update({ strokeEnabled: v })} /></div>
              </div>
              {style.bgEnabled && (
                <div className="grid grid-cols-3 gap-3 mt-2">
                  <RangeInput label={`Opacity: ${Math.round(style.bgOpacity * 100)}%`} min={0} max={100} value={Math.round(style.bgOpacity * 100)} onChange={(v) => update({ bgOpacity: v / 100 })} />
                  <RangeInput label={`Radius: ${style.bgRadius}px`} min={0} max={24} value={style.bgRadius} onChange={(v) => update({ bgRadius: v })} />
                  <RangeInput label={`Padding: ${style.bgPadding}px`} min={4} max={32} value={style.bgPadding} onChange={(v) => update({ bgPadding: v })} />
                </div>
              )}
              {style.strokeEnabled && (
                <div className="grid grid-cols-2 gap-3 mt-2">
                  <ColorPicker label="Stroke" value={style.strokeColor} onChange={(v) => update({ strokeColor: v })} />
                  <RangeInput label={`Width: ${style.strokeWidth}px`} min={1} max={6} value={style.strokeWidth} onChange={(v) => update({ strokeWidth: v })} />
                </div>
              )}
              <div className="mt-2"><Checkbox label="Text shadow" checked={style.shadowEnabled} onChange={(v) => update({ shadowEnabled: v })} /></div>
              {style.shadowEnabled && (
                <div className="grid grid-cols-2 gap-3 mt-2">
                  <ColorPicker label="Shadow" value={style.shadowColor} onChange={(v) => update({ shadowColor: v })} />
                  <RangeInput label={`Blur: ${style.shadowBlur}px`} min={0} max={20} value={style.shadowBlur} onChange={(v) => update({ shadowBlur: v })} />
                </div>
              )}
            </Section>

            <Section title="Position & Layout">
              <div className="grid grid-cols-3 gap-2 mb-3">
                {(["top", "center", "bottom"] as const).map((p) => {
                  const isSelected = (style.positionY != null ? (style.positionY <= 35 ? "top" : style.positionY >= 65 ? "bottom" : "center") : style.position) === p;
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => update({ position: p, positionY: p === "top" ? 15 : p === "bottom" ? 85 : 50 })}
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
              <div className="mt-3 space-y-2 pt-2 border-t border-zinc-800">
                <Checkbox
                  label="Person-Aware (Hindari wajah/subjek otomatis)"
                  checked={!!style.subjectAwarePositioning}
                  onChange={(v) => update({ subjectAwarePositioning: v })}
                />
                <RangeInput
                  label={`Safe Area Margin: ${style.safeAreaMargin || 40}px`}
                  min={10}
                  max={100}
                  value={style.safeAreaMargin || 40}
                  onChange={(v) => update({ safeAreaMargin: v })}
                />
              </div>
            </Section>

            <Section title="Highlight Words (kata penting)">
              <p className="text-[10px] text-zinc-500 mb-2">AI auto-detect dari transkrip. Tambah manual jika perlu.</p>
              <div className="flex gap-2">
                <input type="text" value={newWord} onChange={(e) => setNewWord(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addHighlightWord())} placeholder="Tambah kata..." className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500" />
                <Button type="button" size="xs" onClick={addHighlightWord}>Add</Button>
              </div>
              {style.highlightWords.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {style.highlightWords.map((w) => (
                    <span key={w} className="flex items-center gap-1 bg-yellow-500/10 border border-yellow-500/30 text-yellow-400 text-[10px] font-medium px-2 py-0.5 rounded-full">
                      {w}<button type="button" onClick={() => update({ highlightWords: style.highlightWords.filter((x) => x !== w) })} className="hover:text-red-400"><X className="h-2.5 w-2.5" /></button>
                    </span>
                  ))}
                </div>
              )}
            </Section>
          </>
        )}
      </div>

      {/* Preview — fixed col, vertically centered while left controls scroll */}
      <div className="lg:col-span-4 flex min-h-0 flex-col items-center justify-center overflow-hidden bg-zinc-950 p-4">
        {style.enabled === false ? (
          <div className="flex flex-col items-center justify-center w-full max-w-[240px]">
            <div className="mb-3 flex w-full items-center justify-between gap-2">
              <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
              <span className="rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-[9px] text-zinc-400 font-medium">Subtitle Disabled</span>
            </div>
            <CanvasPreviewFrame canvas={canvas} thumbnailUrl={thumbnailUrl}>
              <div className="absolute inset-0 flex flex-col items-center justify-center p-4 text-center bg-black/40 backdrop-blur-[2px]">
                <div className="w-10 h-10 rounded-full bg-zinc-900/90 border border-zinc-700/80 flex items-center justify-center mb-2 shadow-lg">
                  <EyeOff className="w-5 h-5 text-zinc-400" />
                </div>
                <p className="text-xs font-bold text-zinc-200">No Subtitles</p>
                <p className="text-[10px] text-zinc-400 mt-1 leading-snug">
                  Video akan dirender bersih tanpa subtitle overlay
                </p>
              </div>
            </CanvasPreviewFrame>
            <div className="mt-3 w-full rounded-lg border border-zinc-800 bg-zinc-900/60 p-2.5 text-center">
              <p className="text-[10px] text-zinc-400">Audio & visual tetap utuh 100%</p>
            </div>
          </div>
        ) : engine === "hyperframes" ? (
          <HfLivePreview
            preset={hfPreset}
            sample={hfPreset?.preview || "subtitle words"}
            kind="subtitle"
            aspectRatio={aspectRatio}
            thumbnailUrl={thumbnailUrl}
            canvas={canvas}
          />
        ) : engine === "ffmpeg" ? (
          <>
            <div className="mb-3 flex w-full items-center justify-between gap-2">
              <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
              <span className="rounded-md border border-purple-500/30 bg-purple-500/10 px-2 py-1 text-[9px] text-purple-300">
                <Zap className="inline w-3 h-3 mr-1" />FFmpeg Drawtext
              </span>
            </div>
            <CanvasPreviewFrame canvas={canvas} thumbnailUrl={thumbnailUrl}>
              {(() => {
                const posTop = style.position === "top"
                  ? (style.positionY != null && style.positionY <= 35 ? style.positionY : 15)
                  : style.position === "center"
                    ? (style.positionY != null && style.positionY > 35 && style.positionY < 65 ? style.positionY : 50)
                    : (style.positionY != null && style.positionY >= 65 ? style.positionY : 82);
                return (
                  <div className="absolute left-0 right-0 flex justify-center px-3 pointer-events-none" style={{ top: `${posTop}%`, transform: "translateY(-50%)" }}>
                    {(() => {
                      const isWordPop = style.lineTransition === "word_pop";
                      const sampleWords = ["ini", "kata", "penting", "banget", "untuk", "kamu"];
                      const count = Math.max(1, Math.min(6, style.maxWordsPerLine || 4));
                      const words = sampleWords.slice(0, count);
                      const displayWords = isWordPop ? [words[activeWordIdx % words.length]] : words;
                      const bgAlpha = Math.round(Math.max(0, Math.min(1, style.bgOpacity ?? 0.75)) * 255).toString(16).padStart(2, "0");

                      return (
                        <div
                          className="flex flex-wrap justify-center items-center"
                          style={{
                            gap: isWordPop ? 0 : Math.max(3, (style.wordSpacing ?? 6) * 0.6),
                            maxWidth: "92%",
                            backgroundColor: style.bgEnabled ? `${style.bgColor || "#000000"}${bgAlpha}` : "transparent",
                            padding: style.bgEnabled ? `${Math.round((style.bgPadding ?? 12) * 0.35)}px ${Math.round((style.bgPadding ?? 12) * 0.65)}px` : "0px",
                            borderRadius: `${style.bgRadius ? Math.min(style.bgRadius, 14) : 4}px`,
                          }}
                        >
                          {displayWords.map((w, i) => {
                            const isActive = isWordPop ? true : (i === activeWordIdx % words.length);
                            const fontSize = Math.min(Math.max((style.fontSize || 38) * 0.22, 10), 16);
                            const strokeWidth = style.strokeEnabled ? Math.max((style.strokeWidth || 3) * 0.25, 0.6) : 0;

                            return (
                              <span
                                key={`${w}-${i}`}
                                style={{
                                  color: isActive ? (style.highlightColor || "#FFCC00") : (style.color || "#FFFFFF"),
                                  fontSize: fontSize,
                                  fontFamily: `'${style.fontFamily || "Poppins"}', sans-serif`,
                                  fontWeight: isActive ? 900 : Number(style.fontWeight || 700),
                                  textTransform: style.uppercase ? "uppercase" : style.capitalize ? "capitalize" : "none",
                                  fontStyle: style.italic ? "italic" : "normal",
                                  letterSpacing: `${style.letterSpacing || 0}px`,
                                  paintOrder: strokeWidth > 0 ? "stroke fill" : undefined,
                                  WebkitTextStroke: strokeWidth > 0 ? `${strokeWidth}px ${style.strokeColor || "#000000"}` : undefined,
                                  textShadow: style.shadowEnabled ? `1px 1px 0px ${style.shadowColor || "#000000"}` : "0 2px 4px rgba(0,0,0,0.8)",
                                  wordBreak: "break-word",
                                }}
                              >
                                {w}
                              </span>
                            );
                          })}
                        </div>
                      );
                    })()}
                  </div>
                );
              })()}
              <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-500 z-10">
                ffmpeg {style.lineTransition || "word_pop"} · {style.stylePreset || "classic"}
              </p>
            </CanvasPreviewFrame>
            <div className="mt-3 grid w-full grid-cols-2 gap-2 text-[10px]">
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Font</span><p className="truncate text-zinc-300">{style.fontFamily}</p></div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Preset</span><p className="truncate text-purple-300">{style.stylePreset || "classic"}</p></div>
            </div>
          </>
        ) : engine === "skia" ? (
          <SkiaSubtitleLivePreview style={style} thumbnailUrl={thumbnailUrl} activeWordIdx={activeWordIdx} canvas={canvas} />
        ) : (
          <>
            <div className="mb-3 flex w-full items-center justify-between gap-2">
              <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
              <span className={cn("rounded-md border px-2 py-1 text-[9px]", "border-zinc-800 bg-zinc-900 text-zinc-400")}>{SUBTITLE_TRANSITION_META[style.lineTransition].label}</span>
            </div>
            <CanvasPreviewFrame canvas={canvas} thumbnailUrl={thumbnailUrl}>
              <div className="absolute inset-0 bg-gradient-to-b from-zinc-700/10 to-transparent pointer-events-none" />
              {(() => {
                const posTop = style.position === "top"
                  ? (style.positionY != null && style.positionY <= 35 ? style.positionY : 15)
                  : style.position === "center"
                    ? (style.positionY != null && style.positionY > 35 && style.positionY < 65 ? style.positionY : 50)
                    : (style.positionY != null && style.positionY >= 65 ? style.positionY : 82);
                const sampleWords = ["ini", "kata", "penting", "banget", "untuk", "kamu"];
                const count = Math.max(1, Math.min(6, style.maxWordsPerLine || 4));
                const words = sampleWords.slice(0, count);
                const isWordPop = style.lineTransition === "word_pop";
                const displayWords = isWordPop ? [words[activeWordIdx % words.length]] : words;

                return (
                  <div className="absolute left-0 right-0 flex justify-center px-3" style={{ top: `${posTop}%`, transform: "translateY(-50%)" }}>
                    {style.lineTransition === "emphasis" ? (
                      <div className="flex flex-col items-center gap-1">
                        <span style={{ color: style.color, fontSize: Math.max(style.fontSize * 0.25, 9), fontFamily: `'${style.fontFamily}', sans-serif`, fontWeight: Number(style.fontWeight) }}>gak banyak</span>
                        <span style={{ color: style.highlightColor, fontSize: Math.max(style.fontSize * 0.85, 20), fontFamily: `'${style.fontFamily}', sans-serif`, fontWeight: 900, textShadow: style.highlightGlow ? `0 0 12px ${style.highlightGlowColor || style.highlightColor}, 0 0 24px ${style.highlightGlowColor || style.highlightColor}` : undefined }}>Animasi</span>
                      </div>
                    ) : style.lineTransition === "line_reveal" ? (
                      <div className={cn("overflow-hidden", getSubAnimationClass(style.animationStyle))} style={{ backgroundColor: style.bgEnabled ? `${style.bgColor}${Math.round(style.bgOpacity * 255).toString(16).padStart(2, "0")}` : "transparent", padding: style.bgPadding * 0.42, borderRadius: style.bgRadius, borderLeft: `3px solid ${style.highlightColor}` }}>
                        <div style={{ width: "76%", height: 2, borderRadius: 99, backgroundColor: style.highlightColor, marginBottom: 5 }} />
                        <div className="flex flex-wrap justify-center" style={{ gap: style.wordSpacing * 0.5 }}>
                          {displayWords.map((w, i) => {
                            const isHighlight = i === activeWordIdx % displayWords.length;
                            return (
                              <span key={`${w}-${i}`} style={{ color: isHighlight ? style.highlightColor : style.color, fontSize: Math.max(style.fontSize * 0.35, 10), fontFamily: `'${style.fontFamily}', sans-serif`, fontWeight: isHighlight ? 900 : Number(style.fontWeight), letterSpacing: style.letterSpacing, textTransform: style.uppercase ? "uppercase" : style.capitalize ? "capitalize" : "none", WebkitTextStroke: style.strokeEnabled ? `${style.strokeWidth * 0.3}px ${style.strokeColor}` : undefined, textShadow: style.shadowEnabled ? `0 0 ${style.shadowBlur}px ${style.shadowColor}` : undefined }}>{w}</span>
                            );
                          })}
                        </div>
                      </div>
                    ) : (
                      <div className={cn("flex flex-wrap justify-center", getSubAnimationClass(style.animationStyle))} style={{ gap: isWordPop ? 0 : style.wordSpacing * 0.5, backgroundColor: style.bgEnabled ? `${style.bgColor}${Math.round(style.bgOpacity * 255).toString(16).padStart(2, "0")}` : "transparent", padding: style.bgPadding * 0.4, borderRadius: style.bgRadius }}>
                        {displayWords.map((w, i) => {
                          const isHighlight = isWordPop ? true : (i === activeWordIdx % displayWords.length);
                          const isKeyword = style.highlightWords.includes(w);
                          const shouldHighlight = isHighlight || isKeyword;
                          const useDual = shouldHighlight && style.dualStyleEnabled;
                          const fs = Math.max((shouldHighlight ? (useDual ? style.highlightFontSize : style.fontSize * style.highlightScale) : style.fontSize) * 0.35, 10);
                          const hlStyle = style.highlightStyle || "scale";
                          const wordStyles: React.CSSProperties = {
                            color: shouldHighlight ? style.highlightColor : style.color,
                            fontSize: fs,
                            fontWeight: useDual ? Number(style.highlightFontWeight) : (shouldHighlight && style.highlightBold ? 900 : Number(style.fontWeight)),
                            fontFamily: useDual ? `'${style.highlightFontFamily}', sans-serif` : `'${style.fontFamily}', sans-serif`,
                            fontStyle: useDual ? (style.highlightItalic ? "italic" : "normal") : (style.italic ? "italic" : "normal"),
                            letterSpacing: useDual ? style.highlightLetterSpacing : style.letterSpacing,
                            textTransform: useDual ? (style.highlightUppercase ? "uppercase" : "none") : (style.uppercase ? "uppercase" : style.capitalize ? "capitalize" : "none"),
                            textShadow: [(useDual ? style.highlightShadowEnabled : style.shadowEnabled) ? `0 0 ${useDual ? style.highlightShadowBlur : style.shadowBlur}px ${useDual ? style.highlightShadowColor : style.shadowColor}` : "", shouldHighlight && style.highlightGlow ? `0 0 12px ${style.highlightGlowColor}` : ""].filter(Boolean).join(", ") || undefined,
                            WebkitTextStroke: (useDual ? style.highlightStrokeEnabled : style.strokeEnabled) ? `${(useDual ? style.highlightStrokeWidth : style.strokeWidth) * 0.3}px ${useDual ? style.highlightStrokeColor : style.strokeColor}` : undefined,
                            transition: "all 0.2s ease",
                            display: "inline-block",
                            ...(!useDual && shouldHighlight && hlStyle === "underline" ? { textDecoration: "underline", textDecorationColor: style.highlightColor, textUnderlineOffset: "3px", textDecorationThickness: "2px" } : {}),
                            ...(!useDual && shouldHighlight && hlStyle === "background" ? { backgroundColor: `${style.highlightColor}30`, borderRadius: 3, padding: "1px 4px" } : {}),
                            ...(!useDual && shouldHighlight && hlStyle === "strikethrough" ? { textDecoration: "line-through", textDecorationColor: style.highlightColor, textDecorationThickness: "2px" } : {}),
                          };
                          return <span key={`${w}-${i}`} style={wordStyles}>{w}</span>;
                        })}
                      </div>
                    )}
                  </div>
                );
              })()}
              <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-600 z-10">{style.lineTransition === "emphasis" ? "emphasis" : style.animationStyle} | {style.position}</p>
            </CanvasPreviewFrame>
            <div className="mt-3 grid w-full grid-cols-2 gap-2 text-[10px]">
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Font</span><p className="truncate text-zinc-300">{style.fontFamily}</p></div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2"><span className="text-zinc-600">Highlight</span><p className="truncate" style={{ color: style.highlightColor }}>{style.highlightColor}</p></div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
