import React, { useState, useEffect, useMemo } from "react";
import {
  Palette, Sparkles, Layers, Sliders, CheckCircle2, ChevronLeft, ChevronRight,
  Eye, Play, Pause, Copy, Check, Download, Bookmark, Send, ShieldCheck,
  Film, User, Clapperboard, Split, Megaphone, Image as ImageIcon, Share2, X as XIcon
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import type { Preset } from "@/lib/api";
import {
  DEFAULT_HOOK_STYLE,
  DEFAULT_SUBTITLE_STYLE,
  DEFAULT_TEXT_EMPHASIS_STYLE,
  DEFAULT_WATERMARK_STYLE,
  DEFAULT_CTA_STYLE,
  type HookStyle,
  type SubtitleStyle,
} from "../style-editor/types";
import { useGoogleFont } from "../style-editor/utils";
import { CanvasPreviewFrame } from "../style-editor/preview/CanvasPreviewFrame";
import { HookPreviewRenderer } from "../style-editor/preview/HookPreviewRenderer";

export interface AutopilotPresetPreviewProps {
  selectedSlug: string;
  onSelectSlug: (slug: string) => void;
  presets?: Preset[];
  onOpenEditor?: (preset?: Preset) => void;
}

export function AutopilotPresetPreview({
  selectedSlug,
  onSelectSlug,
  presets = [],
  onOpenEditor,
}: AutopilotPresetPreviewProps) {
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  // Use only user-owned presets (or all user presets if superadmin) from presets prop
  const allPresets = useMemo(() => {
    return Array.isArray(presets) ? presets : [];
  }, [presets]);

  // Pagination State (4 presets per page)
  const ITEMS_PER_PAGE = 4;
  const [currentPage, setCurrentPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(allPresets.length / ITEMS_PER_PAGE));

  // Auto switch page when active slug is outside current page view
  useEffect(() => {
    if (allPresets.length === 0) return;
    const activeIndex = allPresets.findIndex(
      (p) => p.slug === selectedSlug || p.name === selectedSlug || String(p.id) === selectedSlug
    );
    if (activeIndex !== -1) {
      const pageOfActive = Math.floor(activeIndex / ITEMS_PER_PAGE) + 1;
      if (pageOfActive !== currentPage) {
        setCurrentPage(pageOfActive);
      }
    }
  }, [selectedSlug, allPresets]);

  // Sliced Presets for Current Page
  const paginatedPresets = useMemo(() => {
    const start = (currentPage - 1) * ITEMS_PER_PAGE;
    return allPresets.slice(start, start + ITEMS_PER_PAGE);
  }, [allPresets, currentPage]);

  // Currently active preset object
  const activePreset: Preset | null = useMemo(() => {
    if (allPresets.length === 0) return null;
    return (
      allPresets.find((p) => p.slug === selectedSlug || p.name === selectedSlug || String(p.id) === selectedSlug) ||
      allPresets[0]
    );
  }, [allPresets, selectedSlug]);

  // Extract visual layer configs for active preset
  const hookStyle: HookStyle = useMemo(() => ({
    ...DEFAULT_HOOK_STYLE,
    ...(activePreset?.hook_style || {}),
  }), [activePreset]);

  const subStyle: SubtitleStyle = useMemo(() => ({
    ...DEFAULT_SUBTITLE_STYLE,
    ...(activePreset?.subtitle_style || {}),
  }), [activePreset]);

  const wmStyle = useMemo(() => ({
    ...DEFAULT_WATERMARK_STYLE,
    ...(activePreset?.watermark_style || {}),
  }), [activePreset]);

  const ctaStyle = useMemo(() => ({
    ...DEFAULT_CTA_STYLE,
    ...(activePreset?.cta_style || {}),
  }), [activePreset]);

  const brollStyle = useMemo(() => activePreset?.broll_style || {}, [activePreset]);
  const teStyle = useMemo(() => activePreset?.text_emphasis_style || {}, [activePreset]);
  const autopostStyle = useMemo(() => activePreset?.autopost_style || {}, [activePreset]);

  // Dynamic Google Font loader (unconditional top-level hooks)
  useGoogleFont(subStyle.fontFamily || "Poppins");
  useGoogleFont(subStyle.highlightFontFamily);
  useGoogleFont(hookStyle.fontFamily);

  // Live Karaoke animation simulation cycle
  const [activeWordIndex, setActiveWordIndex] = useState(1);
  const [isPlayingPreview, setIsPlayingPreview] = useState(true);
  const sampleWords = useMemo(
    () => ["Inilah", "KATA KUNCI", "Viral", "Hari Ini!"],
    []
  );

  useEffect(() => {
    if (!isPlayingPreview) return;
    const interval = setInterval(() => {
      setActiveWordIndex((prev) => (prev + 1) % sampleWords.length);
    }, 1200);
    return () => clearInterval(interval);
  }, [isPlayingPreview, sampleWords.length]);

  function copyPresetCommand(slug: string) {
    const cmd = `--preset ${slug}`;
    navigator.clipboard.writeText(cmd);
    setCopyFeedback(slug);
    setTimeout(() => setCopyFeedback(null), 2000);
  }

  const highlightColor = subStyle.highlightColor || "#FFCC00";
  const subFont = subStyle.fontFamily || "Poppins";
  const subColor = subStyle.color || "#FFFFFF";
  const subWeight = Number(subStyle.fontWeight || 700);
  const isUppercase = Boolean(subStyle.uppercase);
  const isDualFont = Boolean(subStyle.dualStyleEnabled);
  const dualFont = subStyle.highlightFontFamily || "Anton";

  // Subtitle Container Box Style
  const presetKey = subStyle.stylePreset || "classic";
  const isLightPanel = presetKey === "bubble_chat" || presetKey === "breaking_tape" || presetKey === "quote_box" || presetKey === "word_tiles";
  const previewBg = subStyle.bgEnabled === false
    ? "transparent"
    : subStyle.bgColor
      ? `${subStyle.bgColor}${Math.round((subStyle.bgOpacity ?? 0.6) * 255).toString(16).padStart(2, "0")}`
      : "rgba(0,0,0,0.55)";
  const previewRadius = presetKey === "caption_strip" ? 0 : presetKey === "breaking_tape" ? 2 : presetKey === "bubble_chat" ? 14 : subStyle.bgRadius ?? 8;

  // Subtitle position placement percentage
  const positionYPct = subStyle.positionY !== undefined
    ? subStyle.positionY
    : subStyle.position === "top"
      ? 20
      : subStyle.position === "center"
        ? 50
        : 78;

  // Active Preset Feature Inspection
  const activeHasTextEmp = Boolean(
    (activePreset?.text_emphasis_style && activePreset.text_emphasis_style.effectMode && activePreset.text_emphasis_style.effectMode !== "off") ||
    activePreset?.text_emphasis_style?.enabled ||
    (activePreset as any)?.ai_text_enabled
  );
  const activeTextEmpMode = (activePreset?.text_emphasis_style as any)?.effectMode || "keyword_pop";

  const activeBrollObj = (activePreset?.broll_style as any) || {};
  const activeHasBroll = Boolean(activeBrollObj.enabled ?? (activePreset as any)?.broll_enabled);
  const activeHasBehindPerson = activeHasBroll && Boolean(activeBrollObj.behind_person ?? (activePreset as any)?.broll_behind_person ?? true);
  const activeHasFloatingCard = activeHasBroll && Boolean(activeBrollObj.image_overlay ?? (activePreset as any)?.broll_image_overlay ?? true);
  const activeHasCutaway = activeHasBroll && Boolean(activeBrollObj.video_footage ?? (activePreset as any)?.broll_video_footage ?? true);

  const activeHasAutoGrid = Boolean(
    activeBrollObj.autogrid_enabled ??
    (activePreset as any)?.autogrid_enabled ??
    (activePreset as any)?.reframe_style?.autogrid_enabled ??
    true
  );

  return (
    <div className="space-y-4">
      {/* Top Section Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800/80 pb-3">
        <div className="flex items-center gap-2">
          <Palette className="h-4 w-4 text-violet-400" />
          <h3 className="text-xs font-semibold text-zinc-200">
            2. Preset Style Visual Rendering (5 Layer)
          </h3>
        </div>
        {onOpenEditor && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onOpenEditor(activePreset || undefined)}
            className="h-7 text-[11px] text-violet-300 hover:text-violet-200 hover:bg-violet-950/40 border border-violet-500/30"
            icon={<Sliders className="h-3 w-3" />}
          >
            Buka Style Editor
          </Button>
        )}
      </div>

      <p className="text-[11px] text-zinc-400">
        Pilih preset visual di sebelah kiri untuk melihat live render preview 5-layer (Subtitle, Hook, Watermark, CTA, B-Roll) di sebelah kanan.
      </p>

      {/* Main 2-Column Side-by-Side Layout: Presets (Left) | Preview (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* LEFT COLUMN: Presets List with Pagination matching /jobs/new */}
        <div className="lg:col-span-7 space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-zinc-300 flex items-center gap-1.5">
              <Bookmark className="h-3.5 w-3.5 text-emerald-400" />
              Daftar Preset Tersimpan ({allPresets.length})
            </span>
            <span className="text-[10px] text-zinc-500 hidden sm:inline">
              Klik slug untuk salin command Telegram / CLI
            </span>
          </div>

          {allPresets.length === 0 ? (
            <div className="text-center py-8 border border-dashed border-zinc-800 rounded-xl bg-zinc-900/30 p-4 space-y-2">
              <Bookmark className="h-6 w-6 text-zinc-600 mx-auto" />
              <p className="text-xs text-zinc-300 font-medium">Belum ada preset tersimpan</p>
              <p className="text-[10px] text-zinc-500 max-w-sm mx-auto">
                Buat preset kustom di halaman <strong>New Job</strong> atau klik tombol <strong>Buka Style Editor</strong> di atas untuk menyimpan konfigurasi style Anda.
              </p>
              {onOpenEditor && (
                <Button
                  type="button"
                  size="xs"
                  variant="secondary"
                  onClick={() => onOpenEditor(undefined)}
                  className="mt-2 text-[11px]"
                  icon={<Sliders className="h-3 w-3" />}
                >
                  Buat Preset Sekarang
                </Button>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {paginatedPresets.map((p) => {
                const slugStr = p.slug || `preset-${p.id}`;
                const isSelected = activePreset?.id === p.id || p.slug === selectedSlug || p.name === selectedSlug;
                const brollObj = (p.broll_style as any) || {};
                const hasTextEmp = Boolean(
                  (p.text_emphasis_style && p.text_emphasis_style.effectMode && p.text_emphasis_style.effectMode !== "off") ||
                  p.text_emphasis_style?.enabled ||
                  (p as any)?.ai_text_enabled
                );
                const hasWatermark = Boolean(p.watermark_style && p.watermark_style.enabled);
                const hasCta = Boolean(p.cta_style && p.cta_style.enabled);
                const hasBroll = Boolean(brollObj.enabled ?? (p as any)?.broll_enabled);
                const hasBehindPerson = hasBroll && Boolean(brollObj.behind_person ?? (p as any)?.broll_behind_person ?? true);
                const hasFloatingCard = hasBroll && Boolean(brollObj.image_overlay ?? (p as any)?.broll_image_overlay ?? true);
                const hasCutaway = hasBroll && Boolean(brollObj.video_footage ?? (p as any)?.broll_video_footage ?? true);
                const hasAutoGrid = Boolean(brollObj.autogrid_enabled ?? (p as any)?.autogrid_enabled ?? true);
                const hasAutopost = Boolean(p.autopost_style && p.autopost_style.enabled);

                return (
                  <div
                    key={p.id}
                    className={cn(
                      "relative group rounded-xl border p-3.5 transition-all flex flex-col justify-between text-left",
                      isSelected
                        ? "border-emerald-500 bg-emerald-500/10 ring-1 ring-emerald-500/30 shadow-md shadow-emerald-500/5"
                        : "border-zinc-800 bg-zinc-900/60 hover:border-emerald-500/40 hover:bg-zinc-900/80"
                    )}
                  >
                    <div>
                      {/* Top Header: Title & Active Badge */}
                      <div className="flex items-start justify-between gap-2 mb-1.5">
                        <h4 className={cn("text-xs font-bold truncate", isSelected ? "text-emerald-300" : "text-zinc-200")}>
                          {p.name}
                        </h4>
                        {isSelected && (
                          <span className="text-[8px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold uppercase px-1.5 py-0.5 rounded-full shrink-0">
                            Aktif
                          </span>
                        )}
                      </div>

                      {/* Slug with Copy command */}
                      <div className="mb-2.5 flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => copyPresetCommand(slugStr)}
                          title="Klik untuk copy --preset command"
                          className="inline-flex items-center gap-1 text-[10px] font-mono bg-zinc-800 hover:bg-zinc-700 text-emerald-400 hover:text-emerald-300 px-2 py-0.5 rounded border border-zinc-700 hover:border-emerald-500/40 transition-colors"
                        >
                          <code>--preset {slugStr}</code>
                          {copyFeedback === slugStr ? (
                            <Check className="h-2.5 w-2.5 text-emerald-300 shrink-0" />
                          ) : (
                            <Copy className="h-2.5 w-2.5 opacity-60 shrink-0" />
                          )}
                        </button>
                      </div>

                      {/* Styles Summary & Enabled Layers */}
                      <div className="space-y-1 text-[10px] text-zinc-400 mb-3 bg-zinc-950/50 p-2.5 rounded-lg border border-zinc-800/60">
                        <p className="flex justify-between">
                          <span className="text-zinc-500">Hook:</span>
                          <span className="text-zinc-300 font-medium truncate max-w-[110px]">
                            {(p.hook_style as any)?.animation?.replace(/_/g, " ") || "default"}
                          </span>
                        </p>
                        <p className="flex justify-between">
                          <span className="text-zinc-500">Subtitle:</span>
                          <span className="text-zinc-300 font-medium truncate max-w-[110px]">
                            {(p.subtitle_style as any)?.stylePreset?.replace(/_/g, " ") || "classic"}
                          </span>
                        </p>
                        <div className="flex flex-wrap items-center gap-1 pt-1.5 border-t border-zinc-800/60 mt-1.5">
                          {hasTextEmp && (
                            <span className="text-[8px] bg-emerald-500/15 text-emerald-300 px-1.5 py-0.5 rounded border border-emerald-500/30 inline-flex items-center gap-1 font-medium">
                              <Sparkles className="h-2.5 w-2.5 shrink-0" />
                              AI Text
                            </span>
                          )}
                          {hasBroll && (
                            <span className="text-[8px] bg-amber-500/15 text-amber-300 px-1.5 py-0.5 rounded border border-amber-500/30 inline-flex items-center gap-1 font-medium">
                              <Film className="h-2.5 w-2.5 shrink-0" />
                              B-Roll
                            </span>
                          )}
                          {hasBehindPerson && (
                            <span className="text-[8px] bg-blue-500/15 text-blue-300 px-1.5 py-0.5 rounded border border-blue-500/30 inline-flex items-center gap-1 font-medium">
                              <User className="h-2.5 w-2.5 shrink-0" />
                              Behind 16:9
                            </span>
                          )}
                          {hasFloatingCard && (
                            <span className="text-[8px] bg-purple-500/15 text-purple-300 px-1.5 py-0.5 rounded border border-purple-500/30 inline-flex items-center gap-1 font-medium">
                              <Layers className="h-2.5 w-2.5 shrink-0" />
                              Floating Card
                            </span>
                          )}
                          {hasCutaway && (
                            <span className="text-[8px] bg-indigo-500/15 text-indigo-300 px-1.5 py-0.5 rounded border border-indigo-500/30 inline-flex items-center gap-1 font-medium">
                              <Clapperboard className="h-2.5 w-2.5 shrink-0" />
                              Cutaway
                            </span>
                          )}
                          {hasAutoGrid && (
                            <span className="text-[8px] bg-cyan-500/15 text-cyan-300 px-1.5 py-0.5 rounded border border-cyan-500/30 inline-flex items-center gap-1 font-medium">
                              <Split className="h-2.5 w-2.5 shrink-0" />
                              Auto-Grid
                            </span>
                          )}
                          {hasCta && (
                            <span className="text-[8px] bg-violet-500/15 text-violet-300 px-1.5 py-0.5 rounded border border-violet-500/30 inline-flex items-center gap-1 font-medium">
                              <Megaphone className="h-2.5 w-2.5 shrink-0" />
                              CTA
                            </span>
                          )}
                          {hasWatermark && (
                            <span className="text-[8px] bg-sky-500/15 text-sky-300 px-1.5 py-0.5 rounded border border-sky-500/30 inline-flex items-center gap-1 font-medium">
                              <ImageIcon className="h-2.5 w-2.5 shrink-0" />
                              Watermark
                            </span>
                          )}
                          {hasAutopost && (
                            <span className="text-[8px] bg-rose-500/15 text-rose-300 px-1.5 py-0.5 rounded border border-rose-500/30 inline-flex items-center gap-1 font-medium">
                              <Share2 className="h-2.5 w-2.5 shrink-0" />
                              Auto-Post
                            </span>
                          )}
                        </div>
                        {(p.owner_name || p.owner_email) && (
                          <div className="pt-1 border-t border-zinc-800/60 mt-1 flex items-center gap-1 text-[9px] text-blue-300 font-mono truncate">
                            <ShieldCheck className="h-2.5 w-2.5 text-blue-400 shrink-0" />
                            <span className="truncate">By: {p.owner_name || p.owner_email}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Bottom Action: Load/Pilih Preset Button */}
                    <div>
                      <button
                        type="button"
                        onClick={() => onSelectSlug(slugStr)}
                        className={cn(
                          "w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg border text-[11px] font-medium transition-colors",
                          isSelected
                            ? "border-emerald-500 bg-emerald-500/20 text-emerald-300 shadow-sm"
                            : "border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 hover:border-emerald-500/60"
                        )}
                      >
                        <Download className="h-3 w-3" />
                        {isSelected ? "Preset Aktif" : "Load Preset"}
                      </button>
                      {p.created_at && (
                        <p className="text-[8px] text-zinc-600 mt-1.5 text-center">
                          {new Date(p.created_at).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" })}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Pagination Navigation Footer */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-2 border-t border-zinc-800/60 text-xs">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                className="h-7 px-2.5 text-[11px] text-zinc-400 hover:text-zinc-200 disabled:opacity-30"
                icon={<ChevronLeft className="h-3 w-3" />}
              >
                Sebelumnya
              </Button>

              <div className="flex items-center gap-1">
                {Array.from({ length: totalPages }).map((_, idx) => {
                  const pNum = idx + 1;
                  return (
                    <button
                      key={pNum}
                      type="button"
                      onClick={() => setCurrentPage(pNum)}
                      className={cn(
                        "h-6 min-w-6 px-1.5 rounded text-[11px] font-medium transition-colors",
                        currentPage === pNum
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                          : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60"
                      )}
                    >
                      {pNum}
                    </button>
                  );
                })}
              </div>

              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={currentPage >= totalPages}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                className="h-7 px-2.5 text-[11px] text-zinc-400 hover:text-zinc-200 disabled:opacity-30"
              >
                <span>Berikutnya</span>
                <ChevronRight className="h-3 w-3 ml-1" />
              </Button>
            </div>
          )}
        </div>

        {/* RIGHT COLUMN: Live 9:16 Preview Card with Exact Style Editor Parity */}
        <div className="lg:col-span-5 space-y-3">
          <div className="rounded-2xl border border-zinc-800 bg-zinc-950/90 p-4 space-y-3 shadow-xl">
            {/* Preview Toolbar */}
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-zinc-200 flex items-center gap-1.5 truncate">
                <Eye className="h-3.5 w-3.5 text-violet-400 shrink-0" />
                <span className="text-violet-300 truncate">
                  {activePreset ? activePreset.name : "Preview Visual 9:16"}
                </span>
              </span>

              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  type="button"
                  onClick={() => setIsPlayingPreview(!isPlayingPreview)}
                  className="p-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors text-[10px] flex items-center gap-1 px-1.5"
                  title={isPlayingPreview ? "Jeda animasi kata" : "Putar animasi kata"}
                >
                  {isPlayingPreview ? <Pause className="h-2.5 w-2.5" /> : <Play className="h-2.5 w-2.5" />}
                  <span>{isPlayingPreview ? "Live" : "Pause"}</span>
                </button>
                <Badge variant="default" className="text-[9px] font-mono text-zinc-400 bg-zinc-900 border-zinc-800">
                  9:16
                </Badge>
              </div>
            </div>

            {/* Official CanvasPreviewFrame (Matching Hook & Subtitle Editors) */}
            <div className="flex justify-center">
              <CanvasPreviewFrame
                aspectRatio="9/16"
                className="w-full max-w-[240px] shadow-2xl border-zinc-700"
              >
                {/* 1. TOP-BAR: Watermark & B-Roll / Auto-Grid Status */}
                <div className="absolute top-2 left-2 right-2 flex items-center justify-between z-20 pointer-events-none">
                  <div className="flex items-center gap-1">
                    {activeHasAutoGrid && (
                      <span className="text-[8px] font-bold px-1.5 py-0.5 rounded bg-cyan-500/30 text-cyan-200 border border-cyan-500/40 backdrop-blur-sm shadow-sm">
                        Auto-Grid
                      </span>
                    )}
                    {activeHasBroll && (
                      <span className="text-[8px] font-bold px-1.5 py-0.5 rounded bg-amber-500/30 text-amber-200 border border-amber-500/40 backdrop-blur-sm shadow-sm">
                        {activeHasBehindPerson ? "Behind 16:9" : "B-Roll"}
                      </span>
                    )}
                  </div>

                  {wmStyle.enabled && (
                    <div
                      className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-black/60 border border-white/15 backdrop-blur-sm text-zinc-200 tracking-wider shadow"
                      style={{ opacity: (wmStyle.opacity ?? 80) / 100 }}
                    >
                      {wmStyle.text || "@ClipHub"}
                    </div>
                  )}
                </div>

                {/* 2. UPPER-MID: Hook Overlay (Rendered with HookPreviewRenderer for 100% parity) */}
                <div className="absolute top-12 left-0 right-0 z-15 flex justify-center px-2 pointer-events-none">
                  <HookPreviewRenderer style={hookStyle} scale={0.88} />
                </div>

                {/* 3. DYNAMIC POSITION: Subtitles Karaoke Box */}
                <div
                  className="absolute left-0 right-0 flex justify-center px-3 z-15 pointer-events-none"
                  style={{ top: `${positionYPct}%`, transform: "translateY(-50%)" }}
                >
                  <div
                    className="flex flex-wrap justify-center items-center text-center transition-all max-w-[92%]"
                    style={{
                      backgroundColor: previewBg,
                      borderRadius: `${previewRadius}px`,
                      padding: subStyle.bgEnabled ? `${Math.round((subStyle.bgPadding ?? 12) * 0.35)}px ${Math.round((subStyle.bgPadding ?? 12) * 0.65)}px` : "0px",
                      gap: "4px",
                      boxShadow: presetKey === "neon_pulse" ? `0 0 20px ${highlightColor}44` : undefined,
                    }}
                  >
                    {sampleWords.map((word, idx) => {
                      const isHighlighted = idx === activeWordIndex;
                      const wordFont = isHighlighted && isDualFont ? dualFont : subFont;
                      const fontSize = Math.min(Math.max((subStyle.fontSize || 38) * 0.24, 10), 16);
                      const strokeWidth = subStyle.strokeEnabled ? Math.max((subStyle.strokeWidth || 3) * 0.25, 0.6) : 0;

                      return (
                        <span
                          key={`${word}-${idx}`}
                          style={{
                            color: isHighlighted ? highlightColor : subColor,
                            fontSize: fontSize,
                            fontFamily: `'${wordFont}', sans-serif`,
                            fontWeight: isHighlighted ? (subStyle.highlightBold ? 900 : 800) : subWeight,
                            textTransform: (isUppercase || (isHighlighted && subStyle.highlightUppercase)) ? "uppercase" : "none",
                            letterSpacing: `${subStyle.letterSpacing || 0}px`,
                            paintOrder: strokeWidth > 0 ? "stroke fill" : undefined,
                            WebkitTextStroke: strokeWidth > 0 ? `${strokeWidth}px ${subStyle.strokeColor || "#000000"}` : undefined,
                            textShadow: subStyle.shadowEnabled
                              ? `1px 1px ${(subStyle.shadowBlur || 4) * 0.5}px ${subStyle.shadowColor || "#000000"}`
                              : (isHighlighted && subStyle.highlightGlow
                                ? `0 0 10px ${subStyle.highlightGlowColor || highlightColor}`
                                : "0 2px 4px rgba(0,0,0,0.8)"),
                            backgroundColor: isHighlighted && !subStyle.bgEnabled ? `${highlightColor}25` : undefined,
                            borderRadius: isHighlighted ? "3px" : undefined,
                            padding: isHighlighted ? "0px 2px" : undefined,
                            transform: isHighlighted ? "scale(1.08)" : "scale(1)",
                            transition: "all 0.15s ease-out",
                            display: "inline-block",
                          }}
                        >
                          {word}
                        </span>
                      );
                    })}
                  </div>
                </div>

                {/* 4. BOTTOM: CTA End-Card Preview */}
                {ctaStyle.enabled && (
                  <div className="absolute bottom-2 left-2 right-2 z-20 pointer-events-none">
                    <div
                      className="px-2.5 py-2 rounded-xl border flex items-center justify-between text-[8px] backdrop-blur-md shadow-xl"
                      style={{
                        backgroundColor: ctaStyle.backgroundColor || "rgba(10, 25, 47, 0.92)",
                        borderColor: ctaStyle.primaryColor || "rgba(220, 38, 38, 0.6)",
                        color: ctaStyle.textColor || "#ffffff",
                      }}
                    >
                      <div className="flex items-center gap-1.5 truncate max-w-[70%]">
                        <Send className="h-3 w-3 shrink-0" style={{ color: ctaStyle.primaryColor || "#dc2626" }} />
                        <div className="flex flex-col justify-center min-w-0">
                          <span className="font-bold truncate text-[8.5px] leading-snug">
                            {ctaStyle.headline || "Follow For More"}
                          </span>
                          {(ctaStyle.subhead || ctaStyle.socialHandle) && (
                            <span className="text-[7px] text-zinc-300 truncate mt-0.5 opacity-80">
                              {ctaStyle.subhead || ctaStyle.socialHandle}
                            </span>
                          )}
                        </div>
                      </div>
                      <span
                        className="px-2 py-0.5 rounded-lg font-extrabold uppercase text-[7px] shrink-0"
                        style={{
                          backgroundColor: ctaStyle.primaryColor || "#dc2626",
                          color: "#ffffff",
                        }}
                      >
                        {ctaStyle.buttonText || "+ FOLLOW"}
                      </span>
                    </div>
                  </div>
                )}
              </CanvasPreviewFrame>
            </div>

            {/* Preset Specs Summary Matrix */}
            <div className="space-y-2 pt-2 border-t border-zinc-800">
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-semibold text-zinc-300 flex items-center gap-1.5">
                  <Sliders className="h-3 w-3 text-violet-400" />
                  Konfigurasi Aktif Preset
                </span>
                <span className="text-[9px] font-mono text-zinc-500">
                  Engine: {hookStyle.engine || "Remotion"} / {subStyle.engine || "Remotion"}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[10px]">
                {/* 1. Hook & Animasi */}
                <div className="p-2 rounded-lg bg-zinc-900/60 border border-zinc-800/60">
                  <span className="text-zinc-500 block text-[9px]">Hook & Animasi</span>
                  <span className="font-semibold text-zinc-200 truncate block capitalize">
                    {hookStyle.animation.replace(/_/g, " ")}
                  </span>
                  <span className="text-[8px] text-violet-300 block font-mono mt-0.5">
                    Engine: {hookStyle.engine || "remotion"}
                  </span>
                </div>

                {/* 2. Subtitle & Style */}
                <div className="p-2 rounded-lg bg-zinc-900/60 border border-zinc-800/60">
                  <span className="text-zinc-500 block text-[9px]">Subtitle & Transisi</span>
                  <span className="font-semibold text-zinc-200 truncate block capitalize">
                    {subStyle.stylePreset?.replace(/_/g, " ") || "classic"}
                  </span>
                  <span className="text-[8px] text-zinc-400 block font-mono mt-0.5 truncate">
                    {subFont} • {subStyle.lineTransition || "word_pop"}
                  </span>
                </div>

                {/* 3. AI Cinematic Text */}
                <div className="p-2 rounded-lg bg-zinc-900/60 border border-zinc-800/60">
                  <span className="text-zinc-500 block text-[9px]">AI Cinematic Text</span>
                  <span className={cn("font-semibold truncate block", activeHasTextEmp ? "text-emerald-400" : "text-zinc-500")}>
                    {activeHasTextEmp ? "Aktif" : "Nonaktif"}
                  </span>
                  <span className="text-[8px] text-zinc-400 block mt-0.5">
                    {activeHasTextEmp ? (activeTextEmpMode.replace(/_/g, " ") || "Emphasis / Pop") : "Standar Subtitle"}
                  </span>
                </div>

                {/* 4. Auto-Grid 2-Panel */}
                <div className="p-2 rounded-lg bg-zinc-900/60 border border-zinc-800/60">
                  <span className="text-zinc-500 block text-[9px]">Auto-Grid 2-Panel</span>
                  <span className={cn("font-semibold truncate block", activeHasAutoGrid ? "text-cyan-400" : "text-zinc-500")}>
                    {activeHasAutoGrid ? "Aktif (Auto Split)" : "Nonaktif"}
                  </span>
                  <span className="text-[8px] text-zinc-400 block mt-0.5 truncate">
                    {activeHasAutoGrid ? "Speaker-Aware Dynamic" : "Single Shot Only"}
                  </span>
                </div>

                {/* 5. B-Roll Architecture */}
                <div className="p-2 rounded-lg bg-zinc-900/60 border border-zinc-800/60 col-span-2">
                  <div className="flex items-center justify-between">
                    <span className="text-zinc-500 block text-[9px]">B-Roll & Visual Placements</span>
                    <span className={cn("text-[9px] font-semibold", activeHasBroll ? "text-amber-400" : "text-zinc-500")}>
                      {activeHasBroll ? "B-Roll Aktif" : "Nonaktif"}
                    </span>
                  </div>
                  {activeHasBroll ? (
                    <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                      <span className={cn("text-[8px] px-1.5 py-0.5 rounded border font-medium inline-flex items-center gap-1", activeHasBehindPerson ? "bg-blue-500/15 text-blue-300 border-blue-500/30" : "bg-zinc-800/40 text-zinc-500 border-zinc-800")}>
                        {activeHasBehindPerson ? (
                          <Check className="h-2.5 w-2.5 shrink-0 text-blue-400" />
                        ) : (
                          <XIcon className="h-2.5 w-2.5 shrink-0 text-zinc-500" />
                        )}
                        <span>Behind Person 16:9</span>
                      </span>
                      <span className={cn("text-[8px] px-1.5 py-0.5 rounded border font-medium inline-flex items-center gap-1", activeHasFloatingCard ? "bg-purple-500/15 text-purple-300 border-purple-500/30" : "bg-zinc-800/40 text-zinc-500 border-zinc-800")}>
                        {activeHasFloatingCard ? (
                          <Check className="h-2.5 w-2.5 shrink-0 text-purple-400" />
                        ) : (
                          <XIcon className="h-2.5 w-2.5 shrink-0 text-zinc-500" />
                        )}
                        <span>Floating Object Card</span>
                      </span>
                      <span className={cn("text-[8px] px-1.5 py-0.5 rounded border font-medium inline-flex items-center gap-1", activeHasCutaway ? "bg-indigo-500/15 text-indigo-300 border-indigo-500/30" : "bg-zinc-800/40 text-zinc-500 border-zinc-800")}>
                        {activeHasCutaway ? (
                          <Check className="h-2.5 w-2.5 shrink-0 text-indigo-400" />
                        ) : (
                          <XIcon className="h-2.5 w-2.5 shrink-0 text-zinc-500" />
                        )}
                        <span>Full Frame Cutaway</span>
                      </span>
                    </div>
                  ) : (
                    <span className="text-[8px] text-zinc-500 block mt-0.5">
                      Tanpa B-Roll stock visual overlay
                    </span>
                  )}
                </div>

                {/* 6. CTA End-Card */}
                <div className="p-2 rounded-lg bg-zinc-900/60 border border-zinc-800/60">
                  <span className="text-zinc-500 block text-[9px]">CTA End-Card</span>
                  <span className={cn("font-semibold truncate block", ctaStyle.enabled ? "text-violet-300" : "text-zinc-500")}>
                    {ctaStyle.enabled ? (ctaStyle.headline || "Follow For More") : "Nonaktif"}
                  </span>
                  <span className="text-[8px] text-zinc-400 block mt-0.5 truncate">
                    {ctaStyle.enabled ? (ctaStyle.subhead || ctaStyle.socialHandle || "@handle") : "Tanpa CTA"}
                  </span>
                </div>

                {/* 7. Watermark & Auto-Post */}
                <div className="p-2 rounded-lg bg-zinc-900/60 border border-zinc-800/60">
                  <span className="text-zinc-500 block text-[9px]">Watermark & Auto-Post</span>
                  <span className="font-semibold text-zinc-200 truncate block">
                    {wmStyle.enabled ? (wmStyle.text || "@ClipHub") : "Tanpa Watermark"}
                  </span>
                  <span className={cn("text-[8px] mt-0.5 font-medium inline-flex items-center gap-1", autopostStyle?.enabled ? "text-rose-400" : "text-zinc-500")}>
                    <Share2 className="h-2.5 w-2.5 shrink-0" />
                    <span>{autopostStyle?.enabled ? "Auto-Post Aktif" : "Manual Publish"}</span>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
