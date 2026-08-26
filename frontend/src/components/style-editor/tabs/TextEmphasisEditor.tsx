import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { jobs } from "@/lib/api";
import { buildCanvasConfig } from "@/lib/canvasTemplates";
import type { BackgroundMode } from "@/components/BackgroundTemplateSection";
import type { TextEmphasisStyle } from "../types";
import { FONT_OPTIONS } from "../types";
import { useGoogleFont } from "../utils";
import { Section, SliderField, ColorField, MiniToggle } from "../ui/CommonControls";
import { CanvasPreviewFrame } from "../preview/CanvasPreviewFrame";

export function TextEmphasisEditor({
  style,
  onChange,
  thumbnailUrl,
  previewContext,
  aspectRatio,
  canvasBackground,
}: {
  style: TextEmphasisStyle;
  onChange: (style: TextEmphasisStyle) => void;
  thumbnailUrl?: string;
  previewContext?: { jobId: string; clipRank: number; frame: number };
  aspectRatio?: string;
  canvasBackground?: { mode: BackgroundMode; templateId: string; imageDataUrl: string | null } | null;
}) {
  useGoogleFont(style.fontFamily);
  const [exactPreview, setExactPreview] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const canvas = (aspectRatio === "16:9" || aspectRatio === "1:1")
    ? buildCanvasConfig(aspectRatio, {
      backgroundMode: canvasBackground?.mode || "template",
      templateId: canvasBackground?.templateId || "dark-studio",
      backgroundImageUrl: canvasBackground?.imageDataUrl || null,
    })
    : null;

  useEffect(() => {
    if (!previewContext) return;
    let active = true;
    const timer = window.setTimeout(async () => {
      setPreviewLoading(true);
      try {
        const result = await jobs.renderAITextPreview(previewContext.jobId, previewContext.clipRank, previewContext.frame, style);
        if (active) setExactPreview(result.image);
      } catch {
        if (active) setExactPreview(null);
      } finally {
        if (active) setPreviewLoading(false);
      }
    }, 350);
    return () => { active = false; window.clearTimeout(timer); };
  }, [previewContext?.jobId, previewContext?.clipRank, previewContext?.frame, style]);

  const update = <K extends keyof TextEmphasisStyle>(key: K, value: TextEmphasisStyle[K]) => onChange({ ...style, [key]: value });
  const previewEffect = style.effectMode === "auto" ? "hero_punch" : style.effectMode;
  // For auto_avoid, preview shows text at top (person assumed in bottom)
  const previewTop = previewEffect === "smart_gap" ? "22%" : `${style.positionY}%`;
  const previewAlign = previewEffect === "smart_gap" ? "justify-end text-right"
    : previewEffect === "side_rail" ? "justify-start text-left"
      : "justify-center text-center";
  const textStyle = {
    fontFamily: style.fontFamily === "monospace" ? "monospace" : `'${style.fontFamily}', sans-serif`,
    fontSize: Math.max(16, style.fontSize * 0.28),
    fontWeight: Number(style.fontWeight),
    letterSpacing: style.letterSpacing * 0.35,
    lineHeight: style.lineHeight,
    color: style.color,
    textTransform: style.uppercase ? ("uppercase" as const) : ("none" as const),
    WebkitTextStroke: style.strokeEnabled ? `${Math.max(0.5, style.strokeWidth * 0.35)}px ${style.strokeColor}` : undefined,
    paintOrder: style.strokeEnabled ? ("stroke" as const) : undefined,
    textShadow: style.shadowEnabled ? `0 3px ${Math.max(4, style.shadowBlur * 0.35)}px ${style.shadowColor}` : undefined,
  };

  // Kinetic typography preview: split words
  const kineticPreviewWords = previewEffect === "word_cascade"
    ? "Ide Besar yang Perlu Diingat".split(" ") : [];

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">AI Cinematic Text</h3>
          <p className="mt-1 max-w-xl text-xs leading-5 text-zinc-500">AI memilih maksimal 2 frasa paling kuat per clip. Subtitle berhenti hanya selama frasa tampil, lalu kembali ke timing aslinya.</p>
        </div>
        <span className="shrink-0 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-semibold text-emerald-400">MAX 2 / CLIP</span>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(280px,0.85fr)_minmax(360px,1.15fr)]">
        <div>
          <div className="sticky top-0">
            <CanvasPreviewFrame
              canvas={canvas}
              thumbnailUrl={thumbnailUrl}
              className="max-h-[520px] max-w-none w-full shadow-2xl rounded-2xl border-zinc-700"
            >
              {exactPreview && <img src={exactPreview} alt="Exact final-render AI Text preview" className="absolute inset-0 z-40 h-full w-full object-cover" />}
              {previewEffect === "hero_punch" && <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(0,0,0,.75)_100%)]" />}
              {previewEffect === "z_parallax" && <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,transparent_0%,rgba(0,0,0,.5)_100%)]" />}
              {previewEffect === "split_impact" && <div className="absolute inset-0 bg-gradient-to-r from-black/60 via-transparent to-rose-500/20" />}
              {previewEffect === "sticker_pop" && <div className="absolute inset-0 bg-black/25" />}
              {previewEffect === "orbit_halo" && (
                <div className="absolute left-1/2 top-[20%] z-20 h-12 w-12 -translate-x-1/2 rounded-full bg-gradient-to-br from-zinc-300 to-zinc-600 shadow-xl" />
              )}
              {(previewEffect === "float_track" || previewEffect === "smart_gap") && (
                <div className="absolute bottom-[12%] left-1/2 z-5 h-[55%] w-[42%] -translate-x-1/2 opacity-60">
                  <div className="absolute left-1/2 top-[8%] h-[20%] aspect-square -translate-x-1/2 rounded-full bg-gradient-to-br from-zinc-400 to-zinc-700 shadow-xl" />
                  <div className="absolute bottom-0 left-1/2 h-[78%] w-full -translate-x-1/2 rounded-t-[48%] bg-gradient-to-r from-zinc-800 via-zinc-500 to-zinc-800 shadow-2xl" />
                </div>
              )}
              {previewEffect === "z_parallax" && (
                <div className="absolute bottom-[15%] left-1/2 z-5 h-[60%] w-[46%] -translate-x-1/2 opacity-70" style={{ filter: "blur(0.5px)" }}>
                  <div className="absolute left-1/2 top-[6%] h-[18%] aspect-square -translate-x-1/2 rounded-full bg-gradient-to-br from-zinc-400 to-zinc-700 shadow-xl" />
                  <div className="absolute bottom-0 left-1/2 h-[80%] w-full -translate-x-1/2 rounded-t-[48%] bg-gradient-to-r from-zinc-800 via-zinc-500 to-zinc-800 shadow-2xl" />
                </div>
              )}
              <div className={cn("absolute inset-x-[7%] z-10 flex", previewAlign)} style={{ top: previewTop, transform: "translateY(-50%)" }}>
                <div style={{ ...textStyle, maxWidth: `${style.maxWidthPct}%` }}>
                  {previewEffect === "side_rail" && <div className="mb-2 h-1 w-10 rounded-full" style={{ backgroundColor: style.accentColor }} />}
                  {previewEffect === "word_cascade" ? (
                    <span>
                      {kineticPreviewWords.map((word, idx) => (
                        <span key={idx} style={{ display: "inline-block", marginRight: "0.25em", opacity: 0.6 + (idx % 3) * 0.2, transform: `translateY(${(2 - (idx % 3)) * 4}px)` }}>{word}</span>
                      ))}
                    </span>
                  ) : previewEffect === "split_impact" ? (
                    <span><span style={{ color: style.color }}>Ide Besar </span><span style={{ color: style.accentColor }}>yang Perlu</span></span>
                  ) : previewEffect === "type_pulse" ? (
                    <span>Ide Besar|</span>
                  ) : previewEffect === "sticker_pop" ? (
                    <span style={{ display: "inline-block", padding: "6px 10px", border: `2px solid ${style.accentColor}`, borderRadius: 8, transform: `rotate(${style.stickerAngle ?? -6}deg)`, background: `${style.accentColor}33` }}>Ide Besar</span>
                  ) : previewEffect === "mirror_echo" ? (
                    <span style={{ position: "relative", display: "inline-block" }}>
                      <span style={{ position: "absolute", left: -4, top: 2, opacity: 0.35, color: style.accentColor }}>Ide Besar</span>
                      <span style={{ position: "relative" }}>Ide Besar</span>
                    </span>
                  ) : (
                    "Ide Besar yang Perlu Diingat"
                  )}
                  {previewEffect === "hero_punch" && <div className="mx-auto mt-2 h-1 w-16 rounded-full" style={{ backgroundColor: style.accentColor, boxShadow: `0 0 10px ${style.accentColor}` }} />}
                  {previewEffect === "float_track" && <div className="mx-auto mt-2 h-1 w-12 rounded-full opacity-70" style={{ backgroundColor: style.accentColor }} />}
                </div>
              </div>
              {previewEffect === "depth_cutout" && (
                <div className="absolute bottom-0 left-1/2 z-20 h-[72%] w-[58%] -translate-x-1/2">
                  <div className="absolute left-1/2 top-[2%] h-[22%] aspect-square -translate-x-1/2 rounded-full bg-gradient-to-br from-zinc-300 to-zinc-600 shadow-xl" />
                  <div className="absolute bottom-0 left-1/2 h-[80%] w-full -translate-x-1/2 rounded-t-[48%] bg-gradient-to-r from-zinc-700 via-zinc-300 to-zinc-700 shadow-2xl" />
                </div>
              )}
              <div className="absolute bottom-3 left-3 z-50 rounded-md bg-black/60 px-2 py-1 text-[9px] text-zinc-400">{previewLoading ? "Rendering Remotion…" : exactPreview ? "Exact Remotion frame" : "Style simulation • proses clip untuk preview 1:1"}</div>
            </CanvasPreviewFrame>
          </div>
        </div>

        <div className="space-y-4">
          <Section title="Visual Mode">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {([
                ["auto", "AI Auto", "AI pilih mode terbaik"],
                ["hero_punch", "Hero Punch", "Hero center + vignette"],
                ["depth_cutout", "Depth Cutout", "Teks di belakang subjek"],
                ["side_rail", "Side Rail", "Label editorial sisi"],
                ["float_track", "Float Track", "Bob mengikuti orang"],
                ["smart_gap", "Smart Gap", "Auto isi ruang kosong"],
                ["orbit_halo", "Orbit Halo", "Orbit di sekitar kepala"],
                ["z_parallax", "Z Parallax", "Scale depth person"],
                ["word_cascade", "Word Cascade", "Kata-per-kata kinetic"],
                ["split_impact", "Split Impact", "Dua warna slam split"],
                ["type_pulse", "Type Pulse", "Typewriter + pulse"],
                ["sticker_pop", "Sticker Pop", "Comic sticker rotate"],
                ["mirror_echo", "Mirror Echo", "Ghost echo trail"],
              ] as const).map(([value, label, desc]) => (
                <button key={value} type="button" onClick={() => update("effectMode", value)} className={cn("rounded-xl border p-3 text-left transition-all", style.effectMode === value ? "border-emerald-500 bg-emerald-500/10" : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700")}>
                  <p className={cn("text-xs font-semibold", style.effectMode === value ? "text-emerald-300" : "text-zinc-300")}>{label}</p>
                  <p className="mt-1 text-[10px] text-zinc-600">{desc}</p>
                </button>
              ))}
            </div>
          </Section>

          <Section title="Animation &amp; Font">
            <div className="grid grid-cols-2 gap-3">
              <label className="space-y-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Animation
                <select value={style.animation} onChange={(e) => update("animation", e.target.value as TextEmphasisStyle["animation"])} className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-2 text-xs font-normal normal-case text-zinc-200 outline-none focus:border-emerald-500/60">
                  <option value="rise">Rise</option><option value="impact">Impact</option><option value="slide">Slide</option><option value="static_glitch">Static Glitch</option><option value="glow">Glow</option><option value="elastic">Elastic</option><option value="blur_in">Blur In</option><option value="flip_y">Flip Y</option>
                </select>
              </label>
              <label className="space-y-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Font
                <select value={style.fontFamily} onChange={(e) => update("fontFamily", e.target.value)} className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-2 text-xs font-normal normal-case text-zinc-200 outline-none focus:border-emerald-500/60">
                  {FONT_OPTIONS.map((font) => <option key={font} value={font}>{font}</option>)}
                </select>
              </label>
            </div>
          </Section>

          <Section title="Layout &amp; Sizing">
            <div className="grid grid-cols-2 gap-3">
              <SliderField label="Font Size" value={style.fontSize} min={32} max={160} suffix="px" onChange={(value) => update("fontSize", value)} />
              <SliderField label="Position" value={style.positionY} min={12} max={88} suffix="%" onChange={(value) => update("positionY", value)} />
              <SliderField label="Max Width" value={style.maxWidthPct} min={35} max={96} suffix="%" onChange={(value) => update("maxWidthPct", value)} />
              <SliderField label="Mask Feather" value={style.maskFeather} min={1} max={31} suffix="px" step={2} onChange={(value) => update("maskFeather", value % 2 === 0 ? value + 1 : value)} />
            </div>
          </Section>

          <Section title="Colors">
            <div className="grid grid-cols-2 gap-3">
              <ColorField label="Text" value={style.color} onChange={(value) => update("color", value)} />
              <ColorField label="Accent" value={style.accentColor} onChange={(value) => update("accentColor", value)} />
              <ColorField label="Stroke" value={style.strokeColor} onChange={(value) => update("strokeColor", value)} />
              <ColorField label="Shadow" value={style.shadowColor} onChange={(value) => update("shadowColor", value)} />
            </div>
          </Section>

          <Section title="Effects">
            <div className="grid grid-cols-3 gap-2">
              <MiniToggle label="Uppercase" checked={style.uppercase} onChange={(value) => update("uppercase", value)} />
              <MiniToggle label="Stroke" checked={style.strokeEnabled} onChange={(value) => update("strokeEnabled", value)} />
              <MiniToggle label="Shadow" checked={style.shadowEnabled} onChange={(value) => update("shadowEnabled", value)} />
            </div>
          </Section>

          {/* Effect-specific tuning sliders (conditional) */}
          {previewEffect === "float_track" && (
            <Section title="Float Track Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Bob Speed" value={style.floatSpeed ?? 1.2} min={0.5} max={3.0} step={0.1} suffix="x" onChange={(value) => update("floatSpeed", value)} />
              </div>
            </Section>
          )}
          {previewEffect === "smart_gap" && (
            <Section title="Smart Gap Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Avoid Padding" value={style.avoidPadding ?? 40} min={10} max={120} suffix="px" onChange={(value) => update("avoidPadding", value)} />
              </div>
            </Section>
          )}
          {previewEffect === "orbit_halo" && (
            <Section title="Orbit Halo Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Orbit Radius" value={style.aroundHeadRadius ?? 60} min={30} max={120} suffix="%" onChange={(value) => update("aroundHeadRadius", value)} />
              </div>
            </Section>
          )}
          {previewEffect === "z_parallax" && (
            <Section title="Z Parallax Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Depth Intensity" value={style.depthIntensity ?? 0.5} min={0.1} max={1.0} step={0.05} suffix="" onChange={(value) => update("depthIntensity", value)} />
                <SliderField label="Parallax Scale" value={style.depthParallax ?? 0.35} min={0.05} max={1.0} step={0.05} suffix="" onChange={(value) => update("depthParallax", value)} />
                <SliderField label="Fade Duration" value={style.depthFade ?? 0.45} min={0.1} max={1.5} step={0.05} suffix="s" onChange={(value) => update("depthFade", value)} />
              </div>
              <p className="mt-2 text-[11px] text-zinc-500">Depth Intensity mengatur kekuatan parallax; Parallax Scale mengatur jarak fg/bg; Fade Duration mengatur transisi masuk/keluar teks.</p>
            </Section>
          )}
          {previewEffect === "word_cascade" && (
            <Section title="Word Cascade Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Word Stagger" value={style.kineticStagger ?? 5} min={1} max={18} suffix="f" onChange={(value) => update("kineticStagger", value)} />
              </div>
            </Section>
          )}
          {previewEffect === "mirror_echo" && (
            <Section title="Mirror Echo Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Echo Offset" value={style.echoOffset ?? 10} min={4} max={28} suffix="px" onChange={(value) => update("echoOffset", value)} />
              </div>
            </Section>
          )}
          {previewEffect === "sticker_pop" && (
            <Section title="Sticker Pop Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Angle" value={style.stickerAngle ?? -6} min={-18} max={18} suffix="°" onChange={(value) => update("stickerAngle", value)} />
              </div>
            </Section>
          )}
          {previewEffect === "type_pulse" && (
            <Section title="Type Pulse Tuning">
              <div className="grid grid-cols-2 gap-3">
                <SliderField label="Type Speed" value={style.typeSpeed ?? 1.4} min={0.5} max={3} step={0.1} suffix="x" onChange={(value) => update("typeSpeed", value)} />
              </div>
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}
