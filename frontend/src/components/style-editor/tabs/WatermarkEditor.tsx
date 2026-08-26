import { Upload } from "lucide-react";
import { cn } from "@/lib/utils";
import { buildCanvasConfig, gradientCss } from "@/lib/canvasTemplates";
import { CanvasAccents } from "@/components/BackgroundTemplateSection";
import type { BackgroundMode } from "@/components/BackgroundTemplateSection";
import type { WatermarkStyle } from "../types";
import { FONT_OPTIONS } from "../types";
import { useGoogleFont, downscaleImageDataUrl } from "../utils";
import { Section, RangeInput, SelectSmall, ColorPicker } from "../ui/CommonControls";

export const WATERMARK_POSITIONS: { id: WatermarkStyle["position"]; label: string }[] = [
  { id: "top-left", label: "TL" },
  { id: "top-center", label: "TC" },
  { id: "top-right", label: "TR" },
  { id: "center-left", label: "CL" },
  { id: "center", label: "C" },
  { id: "center-right", label: "CR" },
  { id: "bottom-left", label: "BL" },
  { id: "bottom-center", label: "BC" },
  { id: "bottom-right", label: "BR" },
];

export const WATERMARK_POS_CLASS: Record<WatermarkStyle["position"], string> = {
  "top-left": "left-2 top-2",
  "top-center": "left-1/2 -translate-x-1/2 top-2",
  "top-right": "right-2 top-2",
  "center-left": "left-2 top-1/2 -translate-y-1/2",
  center: "left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2",
  "center-right": "right-2 top-1/2 -translate-y-1/2",
  "bottom-left": "left-2 bottom-2",
  "bottom-center": "left-1/2 -translate-x-1/2 bottom-2",
  "bottom-right": "right-2 bottom-2",
};

export function WatermarkEditor({
  style,
  onChange,
  thumbnailUrl,
  aspectRatio,
  canvasBackground,
}: {
  style: WatermarkStyle;
  onChange: (s: WatermarkStyle) => void;
  thumbnailUrl?: string;
  aspectRatio?: string;
  canvasBackground?: { mode: BackgroundMode; templateId: string; imageDataUrl: string | null } | null;
}) {
  const update = (patch: Partial<WatermarkStyle>) => onChange({ ...style, ...patch });
  const posClass = WATERMARK_POS_CLASS[style.position];
  useGoogleFont(style.fontFamily);
  // Canvas (template/upload fill) only applies to 16:9 & 1:1 — matches the bake.
  const canvas = (aspectRatio === "16:9" || aspectRatio === "1:1")
    ? buildCanvasConfig(aspectRatio, {
      backgroundMode: canvasBackground?.mode || "template",
      templateId: canvasBackground?.templateId || "dark-studio",
      backgroundImageUrl: canvasBackground?.imageDataUrl || null,
    })
    : null;
  // Outer frame always 9:16 (final TikTok output); inner composition follows
  // the selected content aspect ratio.
  const outerAspect = "9/16";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 h-full min-h-0 overflow-hidden">
      {/* Left: settings (scrollable) */}
      <div className="lg:col-span-8 min-h-0 overflow-y-auto p-4 space-y-4">
        <Section title="Watermark">
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[11px] font-medium text-zinc-200">Tampilkan watermark di video akhir</p>
                <p className="text-[9px] text-zinc-500">Dirender server-side via FFmpeg — overlay untuk gambar, drawtext untuk teks.</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={style.enabled}
                onClick={() => update({ enabled: !style.enabled })}
                className={cn("relative h-5 w-9 shrink-0 rounded-full transition-colors", style.enabled ? "bg-emerald-600" : "bg-zinc-700")}
              >
                <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all", style.enabled ? "left-[18px]" : "left-0.5")} />
              </button>
            </div>
          </div>
        </Section>

        {style.enabled && (
          <>
            <Section title="Tipe Watermark">
              <div className="grid grid-cols-2 gap-2">
                {(["text", "image"] as const).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => update({ type: t })}
                    className={cn("rounded-xl border p-3 text-left transition-all", style.type === t ? "border-emerald-500 bg-emerald-500/10" : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700")}
                  >
                    <p className="text-[11px] font-semibold text-zinc-200">{t === "text" ? "Text" : "Gambar / Logo"}</p>
                    <p className="mt-0.5 text-[9px] text-zinc-500">{t === "text" ? "Teks watermark (drawtext)" : "Upload PNG/JPG/WebP (overlay)"}</p>
                  </button>
                ))}
              </div>
            </Section>

            {style.type === "text" ? (
              <Section title="Konten Teks">
                <input
                  type="text"
                  value={style.text}
                  onChange={(e) => update({ text: e.target.value })}
                  placeholder="mis. @channelmu"
                  maxLength={60}
                  className="w-full rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none transition-colors"
                />
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={FONT_OPTIONS} />
                  <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <RangeInput label={`Ukuran: ${style.fontSize}px`} min={10} max={120} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
                  <ColorPicker label="Warna" value={style.color} onChange={(v) => update({ color: v })} />
                </div>
              </Section>
            ) : (
              <Section title="Gambar Watermark">
                {style.imageDataUrl ? (
                  <div className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                    <img src={style.imageDataUrl} alt="Watermark" className="h-14 w-14 rounded-lg border border-zinc-700 bg-white/5 object-contain" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[10px] text-zinc-400">Gambar siap dipakai</p>
                      <button type="button" onClick={() => update({ imageDataUrl: null })} className="mt-1 text-[10px] font-medium text-red-400 hover:text-red-300">
                        Hapus gambar
                      </button>
                    </div>
                  </div>
                ) : (
                  <label className="flex min-h-20 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-zinc-700 bg-zinc-950/40 px-3 py-4 text-center transition-colors hover:border-zinc-500">
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (!file) return;
                        e.target.value = ""; // allow re-selecting the same file
                        void downscaleImageDataUrl(file)
                          .then((dataUrl) => update({ imageDataUrl: dataUrl }))
                          .catch(() => update({ imageDataUrl: null }));
                      }}
                    />
                    <Upload className="mb-1 h-4 w-4 text-zinc-500" />
                    <span className="text-[10px] text-zinc-400">Pilih gambar (PNG dengan transparansi disarankan)</span>
                  </label>
                )}
                <div className="mt-3">
                  <RangeInput label={`Ukuran: ${style.sizePct}% dari lebar video`} min={2} max={60} value={style.sizePct} onChange={(v) => update({ sizePct: v })} />
                </div>
              </Section>
            )}

            <Section title="Transparansi & Posisi">
              <div className="grid grid-cols-2 gap-3">
                <RangeInput label={`Opacity: ${style.opacity}%`} min={0} max={100} value={style.opacity} onChange={(v) => update({ opacity: v })} />
                <RangeInput label={`Jarak tepi: ${style.marginPct}%`} min={0} max={20} value={style.marginPct} onChange={(v) => update({ marginPct: v })} />
              </div>
              <div className="mt-3 grid grid-cols-3 gap-1.5">
                {WATERMARK_POSITIONS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => update({ position: p.id })}
                    className={cn("rounded-md border py-1.5 text-[9px] font-medium transition-colors", style.position === p.id ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-800 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300")}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </Section>
          </>
        )}
      </div>

      {/* Right: Live Preview — sticky & vertically centered, stays put while settings scroll */}
      <div className="lg:col-span-4 flex min-h-0 flex-col items-center justify-center overflow-hidden bg-zinc-950 p-4">
        <div className="mb-3 flex w-full items-center justify-between gap-2">
          <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
          <span className="rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-[9px] text-zinc-400">Watermark</span>
        </div>
        <div className="relative w-full max-w-[220px] max-h-[62vh] bg-zinc-900 rounded-lg overflow-hidden border border-zinc-800 shrink-0" style={{ aspectRatio: outerAspect }}>
          {canvas ? (
            /* Full 9:16 canvas with template — matches Remotion bake 1:1 */
            <div className="absolute inset-0" style={{ background: gradientCss(canvas.background) }}>
              {(canvas.backgroundImageUrl || canvas.background?.imageUrl) && (
                <img src={(canvas.backgroundImageUrl || canvas.background.imageUrl) as string} alt="" className="absolute inset-0 h-full w-full object-cover" />
              )}
              <CanvasAccents accents={canvas.accents || []} />
              {(canvas.background.vignette || 0) > 0 && (
                <div className="absolute inset-0 pointer-events-none" style={{ background: `radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,${canvas.background.vignette}) 100%)` }} />
              )}
              {/* Content slot — 16:9/1:1 band; template fills top/bottom (TikTok 9:16) */}
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
                {thumbnailUrl && <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-contain" />}
              </div>
            </div>
          ) : (
            <>
              {thumbnailUrl && <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-cover" />}
            </>
          )}
          {/* Watermark overlay — spans the full 9:16 frame */}
          <span className={cn("absolute z-10", posClass)} style={{ opacity: Math.max(0.05, style.opacity / 100) }}>
            {style.type === "image" && style.imageDataUrl ? (
              <img src={style.imageDataUrl} alt="" className="h-auto w-auto object-contain" style={{ maxWidth: `${Math.max(8, style.sizePct)}%`, maxHeight: 44 }} />
            ) : (
              <span
                className="font-semibold"
                style={{ fontSize: Math.max(6, Math.round(style.fontSize * 0.3)), fontFamily: `'${style.fontFamily}', sans-serif`, color: style.color }}
              >
                {style.text || "WATERMARK"}
              </span>
            )}
          </span>
          <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-600 z-10">
            {style.enabled ? `${style.type === "image" ? "image" : "text"} · ${style.position.replace(/-/g, " ")} · ${style.opacity}%` : "watermark off"}
          </p>
        </div>
      </div>
    </div>
  );
}
