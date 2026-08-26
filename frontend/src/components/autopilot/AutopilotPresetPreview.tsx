import React, { useState, useEffect, useMemo } from "react";
import {
  Palette, Sparkles, Layers, Sliders, CheckCircle2, ChevronLeft, ChevronRight,
  Eye, Play, Pause, RefreshCw, Volume2, ShieldCheck, Film, Zap, Tag, Send
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

export interface AutopilotPresetPreviewProps {
  selectedSlug: string;
  onSelectSlug: (slug: string) => void;
  presets: any[];
  onOpenEditor?: () => void;
}

export interface AutopilotPresetItem {
  slug: string;
  name: string;
  desc: string;
  isCustom: boolean;
  owner_name?: string;
  owner_email?: string;
  hook_style: Record<string, any>;
  subtitle_style: Record<string, any>;
  watermark_style: Record<string, any>;
  cta_style: Record<string, any>;
  broll_style: Record<string, any>;
  text_emphasis_style: Record<string, any>;
}

export function AutopilotPresetPreview({
  selectedSlug,
  onSelectSlug,
  presets = [],
  onOpenEditor,
}: AutopilotPresetPreviewProps) {
  // Built-in presets with complete 5-layer visual configs
  const builtInPresets: AutopilotPresetItem[] = useMemo(
    () => [
      {
        slug: "default",
        name: "Default Style (Built-in)",
        desc: "Classic clean subtitles with lower-third podcast hook",
        isCustom: false,
        hook_style: {
          animation: "podcast_lower_third",
          primary_color: "#FFFFFF",
          secondary_color: "#FFCC00",
          fontFamily: "Poppins",
          fontWeight: "800",
        },
        subtitle_style: {
          stylePreset: "classic",
          fontFamily: "Poppins",
          highlightColor: "#FFCC00",
          position: "bottom",
          positionY: 78,
          color: "#FFFFFF",
          fontWeight: "700",
          bgEnabled: true,
          bgColor: "#000000",
          bgOpacity: 0.5,
          bgRadius: 8,
        },
        watermark_style: { enabled: false, text: "@ClipHub", opacity: 80, position: "top-right" },
        cta_style: { enabled: false, headline: "Follow For More", buttonText: "FOLLOW" },
        broll_style: { enabled: true, autogrid_enabled: true },
        text_emphasis_style: { effectMode: "hero_punch" },
      },
      {
        slug: "bold_black",
        name: "Bold Black & Yellow",
        desc: "High contrast center pop with bold slam hook",
        isCustom: false,
        hook_style: {
          animation: "bold_slam",
          primary_color: "#FFCC00",
          secondary_color: "#FFFFFF",
          fontFamily: "Montserrat",
          fontWeight: "900",
        },
        subtitle_style: {
          stylePreset: "bold_yellow",
          fontFamily: "Montserrat",
          highlightColor: "#FFCC00",
          position: "center",
          positionY: 52,
          color: "#FFFFFF",
          fontWeight: "900",
          uppercase: true,
          bgEnabled: true,
          bgColor: "#111827",
          bgOpacity: 0.85,
          bgRadius: 6,
        },
        watermark_style: { enabled: false, text: "@ClipHub", opacity: 80, position: "top-right" },
        cta_style: { enabled: false, headline: "Follow For More", buttonText: "FOLLOW" },
        broll_style: { enabled: true, autogrid_enabled: true },
        text_emphasis_style: { effectMode: "hero_punch" },
      },
      {
        slug: "minimal_clean",
        name: "Minimal Clean White",
        desc: "Subtle cinematic reveal with sky blue keywords",
        isCustom: false,
        hook_style: {
          animation: "cinematic_reveal",
          primary_color: "#FFFFFF",
          secondary_color: "#38BDF8",
          fontFamily: "Inter",
          fontWeight: "700",
        },
        subtitle_style: {
          stylePreset: "minimal_clean",
          fontFamily: "Inter",
          highlightColor: "#38BDF8",
          position: "bottom",
          positionY: 80,
          color: "#F8FAFC",
          fontWeight: "600",
          bgEnabled: false,
        },
        watermark_style: { enabled: false, text: "@ClipHub", opacity: 80, position: "top-right" },
        cta_style: { enabled: false, headline: "Subscribe Now", buttonText: "SUBSCRIBE" },
        broll_style: { enabled: true, autogrid_enabled: true },
        text_emphasis_style: { effectMode: "hero_punch" },
      },
      {
        slug: "viral_red",
        name: "Viral Red & High Punch",
        desc: "Aggressive danger bold hook with energetic red highlights",
        isCustom: false,
        hook_style: {
          animation: "danger_bold",
          primary_color: "#EF4444",
          secondary_color: "#FFFFFF",
          fontFamily: "Impact",
          fontWeight: "900",
        },
        subtitle_style: {
          stylePreset: "emphasis_orange",
          fontFamily: "Impact",
          highlightColor: "#EF4444",
          position: "center",
          positionY: 54,
          color: "#FFFFFF",
          fontWeight: "900",
          uppercase: true,
          bgEnabled: true,
          bgColor: "#000000",
          bgOpacity: 0.75,
          bgRadius: 4,
        },
        watermark_style: { enabled: false, text: "@ClipHub", opacity: 80, position: "top-right" },
        cta_style: { enabled: false, headline: "Viral Clip Hub", buttonText: "SHARE" },
        broll_style: { enabled: true, autogrid_enabled: true },
        text_emphasis_style: { effectMode: "hero_punch" },
      },
    ],
    []
  );

  // Unified presets list
  const allPresets: AutopilotPresetItem[] = useMemo(() => {
    const custom: AutopilotPresetItem[] = (Array.isArray(presets) ? presets : []).map((p: any) => ({
      slug: p?.slug || p?.name || String(p?.id || ""),
      name: p?.name || "Preset Kustom",
      desc: p?.slug ? `Slug: ${p.slug}` : `Preset #${p?.id || ""}`,
      isCustom: true,
      owner_name: p?.owner_name,
      owner_email: p?.owner_email,
      hook_style: p?.hook_style || p?.hook_style_config || {},
      subtitle_style: p?.subtitle_style || p?.subtitle_style_config || {},
      watermark_style: p?.watermark_style || p?.watermark_config || {},
      cta_style: p?.cta_style || p?.cta_config || {},
      broll_style: p?.broll_style || p?.broll_config || {},
      text_emphasis_style: p?.text_emphasis_style || p?.text_emphasis_style_config || {},
    }));
    return [...builtInPresets, ...custom];
  }, [builtInPresets, presets]);

  // Pagination State (4 presets per page)
  const ITEMS_PER_PAGE = 4;
  const [currentPage, setCurrentPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(allPresets.length / ITEMS_PER_PAGE));

  // Auto switch page when active slug is outside current page view
  useEffect(() => {
    const activeIndex = allPresets.findIndex(
      (p) => p.slug === selectedSlug || p.name === selectedSlug
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
  const activePreset = useMemo(() => {
    return (
      allPresets.find((p) => p.slug === selectedSlug || p.name === selectedSlug) ||
      builtInPresets[0]
    );
  }, [allPresets, selectedSlug, builtInPresets]);

  // Live Karaoke animation simulation cycle
  const [activeWordIndex, setActiveWordIndex] = useState(1);
  const [isPlayingPreview, setIsPlayingPreview] = useState(true);
  const sampleWords = useMemo(
    () => [
      { text: "Inilah", normal: true },
      { text: "KATA KUNCI", normal: false },
      { text: "Viral", normal: true },
      { text: "Hari Ini!", normal: true },
    ],
    []
  );

  useEffect(() => {
    if (!isPlayingPreview) return;
    const interval = setInterval(() => {
      setActiveWordIndex((prev) => (prev + 1) % sampleWords.length);
    }, 1300);
    return () => clearInterval(interval);
  }, [isPlayingPreview, sampleWords.length]);

  // Styles extraction for rendering
  const hookCfg = activePreset.hook_style || {};
  const subCfg = activePreset.subtitle_style || {};
  const wmCfg = activePreset.watermark_style || {};
  const ctaCfg = activePreset.cta_style || {};
  const brollCfg = activePreset.broll_style || {};
  const teCfg = activePreset.text_emphasis_style || {};

  const highlightColor = subCfg.highlightColor || subCfg.secondary_color || "#FFCC00";
  const subFont = subCfg.fontFamily || "Poppins";
  const subColor = subCfg.color || "#FFFFFF";
  const subWeight = Number(subCfg.fontWeight || 700);
  const isUppercase = Boolean(subCfg.uppercase);
  const isDualFont = Boolean(subCfg.dualStyleEnabled);
  const dualFont = subCfg.highlightFontFamily || "Anton";

  // Subtitle Container Box Style
  const presetKey = subCfg.stylePreset || "classic";
  const isLightPanel = presetKey === "bubble_chat" || presetKey === "breaking_tape" || presetKey === "quote_box" || presetKey === "word_tiles";
  const previewBg = subCfg.bgEnabled === false
    ? "transparent"
    : subCfg.bgColor
      ? `${subCfg.bgColor}${Math.round((subCfg.bgOpacity ?? 0.6) * 255).toString(16).padStart(2, "0")}`
      : "rgba(0,0,0,0.55)";
  const previewRadius = presetKey === "caption_strip" ? 0 : presetKey === "breaking_tape" ? 2 : presetKey === "bubble_chat" ? 14 : subCfg.bgRadius ?? 8;

  // Subtitle position placement percentage
  const positionYPct = subCfg.positionY !== undefined
    ? subCfg.positionY
    : subCfg.position === "top"
      ? 20
      : subCfg.position === "center"
        ? 50
        : 78;

  // Hook details
  const hookAnim = hookCfg.animation || "podcast_lower_third";
  const hookColor = hookCfg.primary_color || "#FFFFFF";
  const hookAccent = hookCfg.secondary_color || highlightColor;
  const hookFont = hookCfg.fontFamily || subFont;

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
            onClick={onOpenEditor}
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
        {/* LEFT COLUMN: Presets List with Pagination */}
        <div className="lg:col-span-7 space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-zinc-300 flex items-center gap-1.5">
              <Layers className="h-3.5 w-3.5 text-violet-400" />
              Daftar Preset ({allPresets.length})
            </span>
            <div className="flex items-center gap-1 text-[11px] text-zinc-400">
              <span>Hal {currentPage} dari {totalPages}</span>
            </div>
          </div>

          {/* Paginated Preset Cards (4 cards per page) */}
          <div className="space-y-2">
            {paginatedPresets.map((p) => {
              const isSelected = p.slug === selectedSlug || p.name === selectedSlug;
              const pHighlight = p.subtitle_style?.highlightColor || p.subtitle_style?.secondary_color || "#FFCC00";
              const pFont = p.subtitle_style?.fontFamily || "Poppins";
              const pHook = p.hook_style?.animation || "podcast_lower_third";

              return (
                <button
                  key={p.slug}
                  type="button"
                  onClick={() => onSelectSlug(p.slug)}
                  className={cn(
                    "w-full p-3 rounded-xl border text-left transition-all flex items-center justify-between gap-3 group relative overflow-hidden",
                    isSelected
                      ? "border-violet-500 bg-gradient-to-r from-violet-950/40 via-zinc-900 to-zinc-900/90 shadow-md ring-1 ring-violet-500/40"
                      : "border-zinc-800 bg-zinc-900/50 hover:border-zinc-700 hover:bg-zinc-900"
                  )}
                >
                  {/* Left Color Indicator Accent Bar */}
                  <span
                    className={cn(
                      "absolute left-0 top-0 bottom-0 w-1 transition-all",
                      isSelected ? "opacity-100" : "opacity-0 group-hover:opacity-40"
                    )}
                    style={{ backgroundColor: pHighlight }}
                  />

                  <div className="min-w-0 flex-1 pl-1">
                    <div className="flex items-center gap-1.5 flex-wrap mb-0.5">
                      <span className={cn("text-xs font-bold truncate", isSelected ? "text-violet-200" : "text-zinc-200")}>
                        {p.name}
                      </span>
                      {p.isCustom ? (
                        <Badge variant="default" className="text-[8px] px-1 py-0 bg-violet-950/80 text-violet-300 border-violet-700/50">
                          Kustom
                        </Badge>
                      ) : (
                        <Badge variant="default" className="text-[8px] px-1 py-0 bg-zinc-800 text-zinc-400">
                          Built-in
                        </Badge>
                      )}
                      {(p.owner_name || p.owner_email) && (
                        <span className="text-[8px] px-1 py-0 rounded bg-blue-950/60 text-blue-300 border border-blue-700/40 font-mono truncate max-w-[120px]">
                          {p.owner_name || p.owner_email}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-zinc-400">
                      <span className="font-medium text-zinc-300">{pFont}</span>
                      <span>•</span>
                      <span className="truncate max-w-[120px] text-zinc-500">{pHook.replace(/_/g, " ")}</span>
                      <span>•</span>
                      <span className="font-mono text-[9px]" style={{ color: pHighlight }}>{pHighlight}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <span
                      className="w-4 h-4 rounded-full border border-white/20 shadow-sm"
                      style={{ backgroundColor: pHighlight }}
                    />
                    {isSelected ? (
                      <div className="w-5 h-5 rounded-full bg-violet-600/30 border border-violet-500 flex items-center justify-center text-violet-300">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                      </div>
                    ) : (
                      <div className="w-5 h-5 rounded-full border border-zinc-700 group-hover:border-zinc-500" />
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Pagination Navigation Footer */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-1 border-t border-zinc-800/60 text-xs">
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
                        "w-6 h-6 rounded-md text-[11px] font-medium transition-colors",
                        currentPage === pNum
                          ? "bg-violet-600 text-white font-bold"
                          : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
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
                <span className="flex items-center gap-1">
                  Berikutnya
                  <ChevronRight className="h-3 w-3" />
                </span>
              </Button>
            </div>
          )}
        </div>

        {/* RIGHT COLUMN: Live 9:16 Preview Card with High-Fidelity Rendering */}
        <div className="lg:col-span-5 space-y-3">
          <div className="rounded-2xl border border-zinc-800 bg-zinc-950/90 p-4 space-y-3 shadow-xl">
            {/* Preview Toolbar */}
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-zinc-200 flex items-center gap-1.5 truncate">
                <Eye className="h-3.5 w-3.5 text-violet-400 shrink-0" />
                <span className="text-violet-300 truncate">{activePreset.name}</span>
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

            {/* Visual 9:16 Mock Smartphone Screen */}
            <div className="relative mx-auto w-full max-w-[260px] aspect-[9/16] rounded-2xl border-2 border-zinc-700 bg-gradient-to-b from-zinc-900 via-zinc-950 to-black overflow-hidden flex flex-col justify-between p-3 shadow-2xl">
              {/* Background ambient lighting & grid */}
              <div className="absolute inset-0 bg-[radial-gradient(#ffffff08_1px,transparent_1px)] [background-size:10px_10px] opacity-50 pointer-events-none" />
              <div
                className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-32 h-32 rounded-full blur-3xl pointer-events-none opacity-20"
                style={{ backgroundColor: highlightColor }}
              />

              {/* TOP: Watermark & Ratio Badge */}
              <div className="relative z-10 flex items-start justify-between">
                <Badge variant="default" className="text-[8px] bg-black/60 backdrop-blur-md border-white/10 text-zinc-300 px-1.5 py-0.5">
                  Full HD
                </Badge>

                {wmCfg.enabled !== false && (
                  <div
                    className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-black/60 border border-white/15 backdrop-blur-sm text-zinc-200 tracking-wider shadow"
                    style={{ opacity: (wmCfg.opacity ?? 80) / 100 }}
                  >
                    {wmCfg.text || "@ClipHub"}
                  </div>
                )}
              </div>

              {/* UPPER-MID: Hook Overlay Preview */}
              <div className="relative z-10 my-auto text-center space-y-1">
                <div className="inline-block px-2.5 py-1.5 rounded-lg bg-zinc-900/95 border border-white/20 backdrop-blur-md shadow-xl max-w-[90%]">
                  <span
                    className="text-[8px] font-black uppercase tracking-widest flex items-center justify-center gap-1"
                    style={{ color: hookAccent }}
                  >
                    <Sparkles className="h-2.5 w-2.5 shrink-0" />
                    <span>{hookAnim.replace(/_/g, " ")}</span>
                  </span>
                  <p
                    className="text-[11px] font-black uppercase tracking-tight mt-0.5 line-clamp-2"
                    style={{
                      color: hookColor,
                      fontFamily: `'${hookFont}', sans-serif`,
                      textShadow: `0 2px 10px ${hookAccent}55`,
                    }}
                  >
                    Rahasia Sukses Viral
                  </p>
                </div>

                {/* AI Text 3D Badge */}
                {teCfg.effectMode && teCfg.effectMode !== "off" && (
                  <div className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-violet-500/20 border border-violet-500/40 text-[8px] font-bold text-violet-300 shadow">
                    <Sparkles className="h-2 w-2" />
                    <span>3D {teCfg.effectMode}</span>
                  </div>
                )}
              </div>

              {/* DYNAMIC POSITION: Subtitles Karaoke Box (Top / Center / Bottom) */}
              <div
                className="relative z-10 transition-all duration-300"
                style={{
                  marginTop: positionYPct < 40 ? "0px" : undefined,
                  marginBottom: positionYPct > 65 ? "0px" : undefined,
                }}
              >
                <div
                  className="text-center p-2 border backdrop-blur-md overflow-hidden transition-all"
                  style={{
                    backgroundColor: previewBg,
                    borderRadius: previewRadius,
                    borderColor: isLightPanel ? "rgba(0,0,0,0.15)" : "rgba(255,255,255,0.12)",
                    boxShadow: presetKey === "neon_pulse" ? `0 0 20px ${highlightColor}44` : undefined,
                  }}
                >
                  <div className="flex flex-wrap items-center justify-center gap-1">
                    {sampleWords.map((word, idx) => {
                      const isHighlighted = idx === activeWordIndex;
                      const wordFont = isHighlighted && isDualFont ? dualFont : subFont;

                      return (
                        <span
                          key={word.text}
                          style={{
                            color: isHighlighted ? highlightColor : subColor,
                            fontFamily: `'${wordFont}', sans-serif`,
                            fontWeight: isHighlighted ? 900 : subWeight,
                            textTransform: (isUppercase || (isHighlighted && subCfg.highlightUppercase)) ? "uppercase" : "none",
                            backgroundColor: isHighlighted ? `${highlightColor}20` : undefined,
                            borderRadius: isHighlighted ? "4px" : undefined,
                            padding: isHighlighted ? "0px 3px" : undefined,
                            boxShadow: isHighlighted ? `0 0 8px ${highlightColor}66` : undefined,
                            textShadow: isHighlighted ? `0 0 10px ${highlightColor}` : undefined,
                          }}
                          className={cn(
                            "relative z-10 text-[10px] transition-all duration-150 inline-block",
                            isHighlighted && "scale-110 font-bold"
                          )}
                        >
                          {word.text}
                        </span>
                      );
                    })}
                  </div>
                </div>

                {/* CTA End-Card Preview */}
                {ctaCfg.enabled && (
                  <div className="mt-2 p-1.5 rounded-lg bg-emerald-950/90 border border-emerald-500/40 flex items-center justify-between text-[8px] text-emerald-200">
                    <span className="font-bold truncate flex items-center gap-1">
                      <Send className="h-2.5 w-2.5 shrink-0 text-emerald-400" />
                      <span>{ctaCfg.headline || "Follow For More"}</span>
                    </span>
                    <span className="px-1.5 py-0.5 rounded bg-emerald-500 text-black font-extrabold uppercase text-[7px]">
                      {ctaCfg.buttonText || "FOLLOW"}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Preset Specs Summary Matrix */}
            <div className="grid grid-cols-2 gap-2 pt-2 border-t border-zinc-800 text-[10px]">
              <div className="p-2 rounded-lg bg-zinc-900/60 border border-zinc-800/60">
                <span className="text-zinc-500 block text-[9px]">Font Subtitle</span>
                <span className="font-semibold text-zinc-200">{subFont} {isDualFont && `+ ${dualFont}`}</span>
              </div>
              <div className="p-2 rounded-lg bg-zinc-900/60 border border-zinc-800/60">
                <span className="text-zinc-500 block text-[9px]">Warna Highlight</span>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className="w-2.5 h-2.5 rounded-full border border-white/20" style={{ backgroundColor: highlightColor }} />
                  <span className="font-mono text-zinc-200">{highlightColor}</span>
                </div>
              </div>
              <div className="p-2 rounded-lg bg-zinc-900/60 border border-zinc-800/60">
                <span className="text-zinc-500 block text-[9px]">Animasi Hook</span>
                <span className="font-semibold text-zinc-200 truncate block">{hookAnim.replace(/_/g, " ")}</span>
              </div>
              <div className="p-2 rounded-lg bg-zinc-900/60 border border-zinc-800/60">
                <span className="text-zinc-500 block text-[9px]">Status Rendering</span>
                <span className="font-semibold text-emerald-400">100% Remotion Parity</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
