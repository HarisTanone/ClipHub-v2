import { useState, useEffect } from "react";
import { Bookmark, Save, Trash2, Copy, Download } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { confirmDialog } from "@/components/ui/ConfirmDialog";
import { presets as presetsApi, type Preset } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { HookStyle, SubtitleStyle, TextEmphasisStyle, WatermarkStyle, CtaStyle } from "../types";
import {
  DEFAULT_HOOK_STYLE,
  DEFAULT_SUBTITLE_STYLE,
  DEFAULT_TEXT_EMPHASIS_STYLE,
  DEFAULT_WATERMARK_STYLE,
  DEFAULT_CTA_STYLE,
  normaliseTextEmphasisStyle,
  normaliseCtaStyle,
} from "../types";

export function PresetsTab({
  hookStyle,
  subtitleStyle,
  textEmphasisStyle,
  watermarkStyle = DEFAULT_WATERMARK_STYLE,
  ctaStyle = DEFAULT_CTA_STYLE,
  brollStyle,
  autopostStyle,
  onHookChange,
  onSubtitleChange,
  onTextEmphasisChange,
  onWatermarkChange,
  onCtaChange,
  onBrollChange,
  onAutopostChange,
  onPresetLoad,
  externalActiveId,
  onPresetSelect,
}: {
  hookStyle: HookStyle;
  subtitleStyle: SubtitleStyle;
  textEmphasisStyle: TextEmphasisStyle;
  watermarkStyle?: WatermarkStyle;
  ctaStyle?: CtaStyle;
  brollStyle?: Record<string, any>;
  autopostStyle?: Record<string, any>;
  onHookChange: (s: HookStyle) => void;
  onSubtitleChange: (s: SubtitleStyle) => void;
  onTextEmphasisChange: (s: TextEmphasisStyle) => void;
  onWatermarkChange?: (s: WatermarkStyle) => void;
  onCtaChange?: (s: CtaStyle) => void;
  onBrollChange?: (b: Record<string, any>) => void;
  onAutopostChange?: (a: Record<string, any>) => void;
  onPresetLoad?: (preset: Preset) => void;
  externalActiveId?: number | null;
  onPresetSelect?: (id: number) => void;
}) {
  const [userPresets, setUserPresets] = useState<Preset[]>([]);
  const [loading, setLoading] = useState(true);
  const [saveName, setSaveName] = useState("");
  const [saveSlug, setSaveSlug] = useState("");
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [activePresetId, setActivePresetId] = useState<number | null>(externalActiveId ?? null);

  // Sync from external
  useEffect(() => {
    if (externalActiveId !== undefined) setActivePresetId(externalActiveId);
  }, [externalActiveId]);

  useEffect(() => {
    presetsApi
      .list()
      .then((list) => {
        setUserPresets(list);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  function loadPreset(preset: Preset) {
    onHookChange({ ...DEFAULT_HOOK_STYLE, ...preset.hook_style } as HookStyle);
    onSubtitleChange({ ...DEFAULT_SUBTITLE_STYLE, ...preset.subtitle_style } as SubtitleStyle);
    if (preset.text_emphasis_style) onTextEmphasisChange(normaliseTextEmphasisStyle(preset.text_emphasis_style));
    if (preset.watermark_style && onWatermarkChange) onWatermarkChange({ ...DEFAULT_WATERMARK_STYLE, ...preset.watermark_style });
    if (preset.cta_style && onCtaChange) onCtaChange(normaliseCtaStyle(preset.cta_style));
    if (preset.broll_style && onBrollChange) onBrollChange(preset.broll_style);
    if (preset.autopost_style && onAutopostChange) onAutopostChange(preset.autopost_style);
    if (onPresetLoad) onPresetLoad(preset);
    setActivePresetId(preset.id);
    if (onPresetSelect) onPresetSelect(preset.id);
    setStatusMsg(`Loaded "${preset.name}" (${preset.slug || `preset-${preset.id}`})`);
    setTimeout(() => setStatusMsg(""), 2500);
  }

  async function handleSave() {
    if (!saveName.trim()) return;
    setSaving(true);
    try {
      const res = await presetsApi.create(
        saveName.trim(),
        hookStyle,
        subtitleStyle,
        textEmphasisStyle,
        watermarkStyle,
        ctaStyle,
        saveSlug.trim() || undefined,
        brollStyle || {},
        autopostStyle || {}
      );
      setSaveName("");
      setSaveSlug("");
      setStatusMsg(`Berhasil menyimpan preset dengan slug: ${res.slug || saveName.trim()}`);
      setTimeout(() => setStatusMsg(""), 3000);
      const list = await presetsApi.list();
      setUserPresets(list);
    } catch {
      setStatusMsg("Gagal menyimpan preset");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number, name: string) {
    if (!(await confirmDialog({ title: "Hapus Preset?", message: `Preset "${name}" akan dihapus permanen.`, confirmText: "Hapus", danger: true }))) return;
    try {
      await presetsApi.remove(id);
      setUserPresets((prev) => prev.filter((p) => p.id !== id));
      setStatusMsg(`Preset "${name}" dihapus`);
      setTimeout(() => setStatusMsg(""), 2000);
    } catch {
      setStatusMsg("Gagal menghapus");
    }
  }

  function copyPresetCommand(slug: string) {
    const cmd = `--preset ${slug}`;
    navigator.clipboard.writeText(cmd);
    setStatusMsg(`Copied: "${cmd}" ke clipboard!`);
    setTimeout(() => setStatusMsg(""), 2500);
  }

  return (
    <div className="h-full p-5 overflow-y-auto">
      {/* Save current as preset */}
      <div className="mb-6 bg-zinc-900/60 border border-zinc-800 p-4 rounded-xl">
        <h3 className="text-xs font-semibold text-zinc-200 mb-3 flex items-center gap-2">
          <Save className="h-3.5 w-3.5 text-emerald-400" />Simpan Style Saat Ini Sebagai Preset Baru
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-3">
          <div>
            <label className="block text-[10px] text-zinc-400 font-medium mb-1">Nama Preset</label>
            <input
              type="text"
              value={saveName}
              onChange={(e) => {
                const newName = e.target.value;
                setSaveName(newName);
                if (!saveSlug || saveSlug === saveName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "")) {
                  setSaveSlug(newName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, ""));
                }
              }}
              onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), handleSave())}
              placeholder="Contoh: Viral Gaming 01..."
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50"
            />
          </div>
          <div>
            <label className="block text-[10px] text-zinc-400 font-medium mb-1">Slug Telegram / CLI (Opsional)</label>
            <input
              type="text"
              value={saveSlug}
              onChange={(e) => setSaveSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
              onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), handleSave())}
              placeholder="contoh: slug-presets-01"
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50 font-mono text-xs"
            />
          </div>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-zinc-500">
            <span className="text-zinc-400 font-medium">Layers:</span>
            <span className="bg-zinc-800 px-1.5 py-0.5 rounded text-zinc-300">Hook</span>
            <span className="bg-zinc-800 px-1.5 py-0.5 rounded text-zinc-300">Subtitles</span>
            <span className={cn("px-1.5 py-0.5 rounded", textEmphasisStyle?.effectMode && (textEmphasisStyle.effectMode as string) !== "off" ? "bg-emerald-500/20 text-emerald-300" : "bg-zinc-800/60 text-zinc-500")}>AI Text</span>
            <span className={cn("px-1.5 py-0.5 rounded", watermarkStyle?.enabled ? "bg-emerald-500/20 text-emerald-300" : "bg-zinc-800/60 text-zinc-500")}>Watermark</span>
            <span className={cn("px-1.5 py-0.5 rounded", ctaStyle?.enabled ? "bg-emerald-500/20 text-emerald-300" : "bg-zinc-800/60 text-zinc-500")}>CTA</span>
            <span className={cn("px-1.5 py-0.5 rounded", brollStyle?.enabled ? "bg-amber-500/20 text-amber-300" : "bg-zinc-800/60 text-zinc-500")}>B-roll</span>
            <span className={cn("px-1.5 py-0.5 rounded", brollStyle?.autogrid_enabled ? "bg-cyan-500/20 text-cyan-300" : "bg-zinc-800/60 text-zinc-500")}>Auto-Grid</span>
          </div>
          <Button type="button" size="sm" loading={saving} onClick={handleSave} icon={<Save className="h-3.5 w-3.5" />}>Simpan Preset</Button>
        </div>
        {statusMsg && <p className="text-[11px] text-emerald-400 mt-2 font-medium">{statusMsg}</p>}
      </div>

      {/* Preset list */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-semibold text-zinc-200 flex items-center gap-2">
            <Bookmark className="h-3.5 w-3.5 text-emerald-400" />Daftar Preset Tersimpan ({userPresets.length})
          </h3>
          <span className="text-[10px] text-zinc-500">Klik slug untuk salin command Telegram / CLI</span>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 py-4">
            <div className="h-4 w-4 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin" />
            <span className="text-xs text-zinc-500">Memuat daftar preset...</span>
          </div>
        ) : userPresets.length === 0 ? (
          <div className="text-center py-8 border border-dashed border-zinc-800 rounded-xl bg-zinc-900/30">
            <Bookmark className="h-6 w-6 text-zinc-700 mx-auto mb-2" />
            <p className="text-xs text-zinc-400 font-medium">Belum ada preset yang disimpan</p>
            <p className="text-[10px] text-zinc-600 mt-1">Atur Hook, Subtitles, AI Text, Watermark, CTA, & B-roll, lalu simpan di sini</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {userPresets.map((p) => {
              const slugStr = p.slug || `preset-${p.id}`;
              const hasTextEmp = p.text_emphasis_style && p.text_emphasis_style.effectMode && p.text_emphasis_style.effectMode !== "off";
              const hasWatermark = p.watermark_style && p.watermark_style.enabled;
              const hasCta = p.cta_style && p.cta_style.enabled;
              const hasBroll = p.broll_style && p.broll_style.enabled;
              const hasAutoGrid = p.broll_style && p.broll_style.autogrid_enabled;
              const hasAutopost = p.autopost_style && p.autopost_style.enabled;

              return (
                <div
                  key={p.id}
                  className={cn(
                    "relative group rounded-xl border p-3.5 transition-all flex flex-col justify-between",
                    activePresetId === p.id
                      ? "border-emerald-500 bg-emerald-500/8 ring-1 ring-emerald-500/20 shadow-lg shadow-emerald-500/5"
                      : "border-zinc-800 bg-zinc-900/60 hover:border-emerald-500/40"
                  )}
                >
                  <div>
                    <div className="flex items-start justify-between gap-2 mb-1.5">
                      <h4 className={cn("text-sm font-medium truncate", activePresetId === p.id ? "text-emerald-300 font-semibold" : "text-zinc-200")}>{p.name}</h4>
                      <button type="button" onClick={() => handleDelete(p.id, p.name)} title="Hapus preset" className="p-1 rounded text-zinc-600 hover:text-red-400 hover:bg-zinc-800 opacity-0 group-hover:opacity-100 transition-all shrink-0">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>

                    {/* Slug Badge with Copy button */}
                    <div className="mb-2.5 flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => copyPresetCommand(slugStr)}
                        title="Klik untuk copy --preset command"
                        className="inline-flex items-center gap-1 text-[10px] font-mono bg-zinc-800 hover:bg-zinc-700 text-emerald-400 hover:text-emerald-300 px-2 py-0.5 rounded border border-zinc-700 hover:border-emerald-500/40 transition-colors"
                      >
                        <code>--preset {slugStr}</code>
                        <Copy className="h-2.5 w-2.5 opacity-60" />
                      </button>
                      {activePresetId === p.id && <span className="text-[8px] bg-emerald-500/20 text-emerald-400 font-bold uppercase px-1.5 py-0.5 rounded-full">Active</span>}
                    </div>

                    {/* Styles Summary */}
                    <div className="space-y-1 text-[10px] text-zinc-400 mb-3 bg-zinc-950/40 p-2 rounded-lg border border-zinc-800/50">
                      <p className="flex justify-between"><span className="text-zinc-500">Hook:</span><span className="text-zinc-300 font-medium truncate max-w-[120px]">{(p.hook_style as any)?.animation?.replace(/_/g, " ") || "default"}</span></p>
                      <p className="flex justify-between"><span className="text-zinc-500">Subtitle:</span><span className="text-zinc-300 font-medium truncate max-w-[120px]">{(p.subtitle_style as any)?.stylePreset || "clean"}</span></p>
                      <div className="flex flex-wrap items-center gap-1 pt-1 border-t border-zinc-800/60 mt-1">
                        {hasTextEmp && <span className="text-[8px] bg-emerald-500/10 text-emerald-400 px-1 py-0.2 rounded border border-emerald-500/20">AI Text</span>}
                        {hasWatermark && <span className="text-[8px] bg-blue-500/10 text-blue-400 px-1 py-0.2 rounded border border-blue-500/20">Watermark</span>}
                        {hasCta && <span className="text-[8px] bg-purple-500/10 text-purple-400 px-1 py-0.2 rounded border border-purple-500/20">CTA</span>}
                        {hasBroll && <span className="text-[8px] bg-amber-500/10 text-amber-400 px-1 py-0.2 rounded border border-amber-500/20">B-roll</span>}
                        {hasAutoGrid && <span className="text-[8px] bg-cyan-500/10 text-cyan-400 px-1 py-0.2 rounded border border-cyan-500/20">Auto-Grid</span>}
                        {hasAutopost && <span className="text-[8px] bg-rose-500/10 text-rose-400 px-1 py-0.2 rounded border border-rose-500/20">Auto-Post</span>}
                      </div>
                      {p.owner_email && <p className="text-[9px] text-zinc-500 pt-0.5">By: {p.owner_name || p.owner_email}</p>}
                    </div>
                  </div>

                  <div>
                    <button
                      type="button"
                      onClick={() => loadPreset(p)}
                      className={cn(
                        "w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg border text-[11px] font-medium transition-colors",
                        activePresetId === p.id
                          ? "border-emerald-500 bg-emerald-500/20 text-emerald-300 shadow-sm"
                          : "border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10"
                      )}
                    >
                      <Download className="h-3 w-3" />{activePresetId === p.id ? "Preset Aktif" : "Load Preset"}
                    </button>
                    {p.created_at && <p className="text-[8px] text-zinc-600 mt-1.5 text-center">{new Date(p.created_at).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" })}</p>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
