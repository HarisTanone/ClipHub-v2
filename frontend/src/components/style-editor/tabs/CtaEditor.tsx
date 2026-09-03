import React, { useState, useEffect } from "react";
import {
  Bell,
  Link2,
  Share2,
  MessageSquare,
  Zap,
  UserPlus,
  Heart,
  Star,
  Clock,
  RotateCcw,
  Info,
  Plus,
  ArrowUpRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { RangeSlider } from "@/components/ui/RangeSlider";
import { buildCanvasConfig, gradientCss } from "@/lib/canvasTemplates";
import { CanvasAccents } from "@/components/BackgroundTemplateSection";
import type { BackgroundMode } from "@/components/BackgroundTemplateSection";
import type { CtaStyle } from "../types";
import { FONT_OPTIONS } from "../types";
import { useGoogleFont } from "../utils";
import { Section, RangeInput, SelectSmall, ColorPicker } from "../ui/CommonControls";

export const TikTokSvg = ({ className = "h-3.5 w-3.5" }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor">
    <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.89 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.11V9.43a6.34 6.34 0 0 0-.79-.05 6.34 6.34 0 0 0-6.34 6.34 6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.34-6.34V8.71a8.21 8.21 0 0 0 4.76 1.52v-3.44a4.82 4.82 0 0 1-1-.1z" />
  </svg>
);

export const InstagramSvg = ({ className = "h-3.5 w-3.5" }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
    <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
    <line x1="17.5" y1="6.5" x2="17.51" y2="6.5" />
  </svg>
);

export const YouTubeSvg = ({ className = "h-3.5 w-3.5" }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor">
    <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
  </svg>
);

export const CTA_ICON_OPTIONS: {
  id: CtaStyle["selectedIcon"];
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}[] = [
  { id: "tiktok", label: "TikTok", icon: TikTokSvg },
  { id: "instagram", label: "Instagram", icon: InstagramSvg },
  { id: "youtube", label: "YouTube", icon: YouTubeSvg },
  { id: "bell", label: "Bell", icon: Bell },
  { id: "link", label: "Link Bio", icon: Link2 },
  { id: "share", label: "Share", icon: Share2 },
  { id: "message", label: "Komentar", icon: MessageSquare },
  { id: "zap", label: "Flash / Zap", icon: Zap },
  { id: "user_plus", label: "Follow", icon: UserPlus },
  { id: "heart", label: "Like", icon: Heart },
  { id: "star", label: "Favorit", icon: Star },
];

export const CTA_TEMPLATES_CONFIG: {
  id: CtaStyle["template"];
  name: string;
  desc: string;
  badge: string;
  icon: React.ComponentType<{ className?: string }>;
  defaults: Partial<CtaStyle>;
}[] = [
  {
    id: "follow_badge",
    name: "Follow & Like",
    desc: "Pill creator TikTok/IG interaktif dengan tombol follow dan checkmark.",
    badge: "Viral TikTok",
    icon: UserPlus,
    defaults: {
      headline: "Follow For More",
      subhead: "@yourchannel",
      buttonText: "FOLLOW",
      socialPlatform: "tiktok",
      primaryColor: "#FE2C55",
      textColor: "#FFFFFF",
      backgroundColor: "#0F172A",
      bgOpacity: 92,
      animation: "slide_up",
      position: "bottom",
    },
  },
  {
    id: "link_bio",
    name: "Link in Bio",
    desc: "Ajakan klik link di bio dengan tombol aksi dan panah aksentuasi.",
    badge: "High Conversion",
    icon: Link2,
    defaults: {
      headline: "Cek Link di Bio",
      subhead: "Dapatkan akses gratis hari ini",
      buttonText: "KLIK LINK",
      socialPlatform: "instagram",
      primaryColor: "#3B82F6",
      textColor: "#FFFFFF",
      backgroundColor: "#0F172A",
      bgOpacity: 92,
      animation: "pop_in",
      position: "bottom",
    },
  },
  {
    id: "subscribe_pill",
    name: "Subscribe & Bell",
    desc: "Tombol subscribe YouTube Shorts dengan icon lonceng notifikasi.",
    badge: "YouTube Shorts",
    icon: Bell,
    defaults: {
      headline: "Subscribe Channel Ini",
      subhead: "Nyalakan notifikasi update",
      buttonText: "SUBSCRIBE",
      socialPlatform: "youtube",
      primaryColor: "#EF4444",
      textColor: "#FFFFFF",
      backgroundColor: "#0F172A",
      bgOpacity: 92,
      animation: "fade_bounce",
      position: "bottom",
    },
  },
  {
    id: "like_share",
    name: "Like & Share",
    desc: "Mendorong viewer like, share ke teman, dan simpan video.",
    badge: "Engagement",
    icon: Share2,
    defaults: {
      headline: "Suka Konten Ini?",
      subhead: "Bagikan ke teman Anda",
      buttonText: "BAGIKAN",
      socialPlatform: "general",
      primaryColor: "#F59E0B",
      textColor: "#FFFFFF",
      backgroundColor: "#0F172A",
      bgOpacity: 92,
      animation: "glow_pulse",
      position: "bottom",
    },
  },
  {
    id: "comment_prompt",
    name: "Ketik di Komentar",
    desc: "Trigger interaksi algoritma dengan meminta viewer ketik keyword.",
    badge: "DM Trigger",
    icon: MessageSquare,
    defaults: {
      headline: "Ketik 'MAU' di Komentar",
      subhead: "Kami akan kirimkan materinya",
      buttonText: "KOMEN",
      socialPlatform: "instagram",
      primaryColor: "#8B5CF6",
      textColor: "#FFFFFF",
      backgroundColor: "#0F172A",
      bgOpacity: 92,
      animation: "pop_in",
      position: "bottom",
    },
  },
  {
    id: "custom_card",
    name: "Neon / Cyber Card",
    desc: "Tampilan modern futuristik dengan border glow dan badge aksen.",
    badge: "Exclusive",
    icon: Zap,
    defaults: {
      headline: "JOIN VIP COMMUNITY",
      subhead: "Daily alpha insights & tools",
      buttonText: "JOIN NOW",
      socialPlatform: "custom",
      primaryColor: "#06B6D4",
      textColor: "#FFFFFF",
      backgroundColor: "#050B14",
      bgOpacity: 95,
      animation: "glitch",
      position: "bottom",
    },
  },
];

export const CTA_ANIMATIONS = [
  { id: "slide_up", label: "Slide Up", desc: "Meluncur naik dari bawah" },
  { id: "pop_in", label: "Pop In", desc: "Membal dinamis (bounce)" },
  { id: "fade_bounce", label: "Fade Bounce", desc: "Fade halus dengan micro bounce" },
  { id: "glow_pulse", label: "Glow Pulse", desc: "Pendaran cahaya berdenyut" },
  { id: "glitch", label: "Glitch Cyber", desc: "Efek glitch digital futuristik" },
] as const;

export const CTA_POSITIONS = [
  { id: "bottom", label: "Bawah (Bottom)" },
  { id: "lower-third", label: "Lower-Third" },
  { id: "center", label: "Tengah (Center)" },
  { id: "top", label: "Atas (Top)" },
] as const;

export const CTA_PLATFORMS = [
  { id: "tiktok", label: "TikTok" },
  { id: "instagram", label: "Instagram" },
  { id: "youtube", label: "YouTube" },
  { id: "general", label: "Umum / Global" },
  { id: "custom", label: "Custom" },
] as const;

export const CTA_COLOR_SWATCHES = [
  "#10B981",
  "#FE2C55",
  "#3B82F6",
  "#EF4444",
  "#8B5CF6",
  "#F59E0B",
  "#EC4899",
  "#06B6D4",
  "#FFFFFF",
];

export function CtaEditor({
  style,
  onChange,
  thumbnailUrl,
  aspectRatio,
  canvasBackground,
}: {
  style: CtaStyle;
  onChange: (s: CtaStyle) => void;
  thumbnailUrl?: string;
  aspectRatio?: string;
  canvasBackground?: { mode: BackgroundMode; templateId: string; imageDataUrl: string | null } | null;
}) {
  const update = (patch: Partial<CtaStyle>) => onChange({ ...style, ...patch });
  useGoogleFont(style.fontFamily);

  const canvas = (aspectRatio === "16:9" || aspectRatio === "1:1")
    ? buildCanvasConfig(aspectRatio, {
      backgroundMode: canvasBackground?.mode || "template",
      templateId: canvasBackground?.templateId || "dark-studio",
      backgroundImageUrl: canvasBackground?.imageDataUrl || null,
    })
    : null;
  const outerAspect = "9/16";

  const applyTemplate = (tmplId: CtaStyle["template"]) => {
    const tmpl = CTA_TEMPLATES_CONFIG.find((t) => t.id === tmplId);
    if (!tmpl) return;
    update({
      template: tmplId,
      ...tmpl.defaults,
      enabled: true,
      ctaType: "card",
    });
  };

  const SelectedIconComp = CTA_ICON_OPTIONS.find((i) => i.id === style.selectedIcon)?.icon || UserPlus;
  const [replayKey, setReplayKey] = useState(0);

  useEffect(() => {
    setReplayKey((k) => k + 1);
  }, [style.animation, style.position, style.template, style.ctaType, style.primaryColor]);

  const getCtaAnimStyle = (anim: string): React.CSSProperties => {
    switch (anim) {
      case "slide_up":
        return { animation: "ctaSlideUpPreview 0.75s cubic-bezier(0.16, 1, 0.3, 1) both" };
      case "pop_in":
        return { animation: "ctaPopInPreview 0.7s cubic-bezier(0.34, 1.56, 0.64, 1) both" };
      case "fade_bounce":
        return { animation: "ctaFadeBouncePreview 0.7s cubic-bezier(0.22, 1, 0.36, 1) both" };
      case "glow_pulse":
        return { animation: "ctaGlowPulsePreview 2.2s ease-in-out infinite" };
      case "glitch":
        return { animation: "ctaGlitchCyberPreview 2.8s ease-in-out infinite" };
      default:
        return { animation: "ctaSlideUpPreview 0.75s cubic-bezier(0.16, 1, 0.3, 1) both" };
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 h-full min-h-0 overflow-hidden">
      {/* Left: settings (scrollable) */}
      <div className="lg:col-span-8 min-h-0 overflow-y-auto p-4 space-y-4">
        {/* Master Switch */}
        <Section title="Call To Action (CTA) End-Card">
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-[11px] font-semibold text-zinc-200">Tampilkan CTA di akhir video</p>
                  <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-medium text-emerald-400 border border-emerald-500/20">
                    High Conversion
                  </span>
                </div>
                <p className="text-[9px] text-zinc-500 mt-0.5">
                  Muncul di detik-detik akhir video untuk meningkatkan engagement, follow, subscribe, atau ajakan aksi.
                </p>
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
            {/* Mode Selector: Card vs Text vs Both */}
            <Section title="Pilih Format Tampilan CTA">
              <div className="grid grid-cols-3 gap-2">
                {[
                  { id: "card", label: "Design Creator Card", desc: "Card interaktif lengkap dengan tombol follow / aksi" },
                  { id: "text", label: "Teks Biasa", desc: "Pesan teks penutup bersih & minimalis" },
                  { id: "both", label: "Keduanya (Teks + Icon)", desc: "Pesan teks kustom dengan icon vektor aksen" },
                ].map((mode) => (
                  <button
                    key={mode.id}
                    type="button"
                    onClick={() => update({ ctaType: mode.id as any })}
                    className={cn(
                      "rounded-xl border p-2.5 text-left transition-all",
                      style.ctaType === mode.id
                        ? "border-emerald-500 bg-emerald-500/10 text-emerald-300 shadow-sm"
                        : "border-zinc-800 bg-zinc-950/40 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                    )}
                  >
                    <p className="text-[11px] font-bold">{mode.label}</p>
                    <p className="text-[8px] text-zinc-500 mt-0.5 leading-relaxed">{mode.desc}</p>
                  </button>
                ))}
              </div>
            </Section>

            {/* Timing Control */}
            <Section title="Durasi Kemunculan di Akhir Video">
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3.5 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-zinc-300">Durasi Tampil CTA:</span>
                  <span className="rounded-md bg-emerald-500/10 px-2.5 py-1 text-xs font-bold text-emerald-400 border border-emerald-500/20">
                    {style.duration.toFixed(1)} detik terakhir
                  </span>
                </div>
                <RangeSlider
                  label="Durasi Tampil CTA"
                  min={1.0}
                  max={6.0}
                  step={0.5}
                  value={style.duration}
                  onChange={(v) => update({ duration: v })}
                />
                <div className="flex items-center justify-between text-[9px] text-zinc-500">
                  <span>1.0s (Cepat)</span>
                  <span className="text-emerald-400/80 font-medium">Default: 3.0s</span>
                  <span>6.0s (Maksimal)</span>
                </div>
                <div className="text-[9px] text-zinc-400 bg-zinc-900/60 p-2.5 rounded-lg border border-zinc-800/80 flex items-start gap-2">
                  <Info className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  <span><strong>Timing Otomatis:</strong> Jika klip berdurasi 30 detik dan CTA diatur {style.duration.toFixed(1)}s, CTA akan muncul tepat pada detik ke-{(30 - style.duration).toFixed(1)}s hingga akhir video.</span>
                </div>
              </div>
            </Section>

            {/* Mode-Specific Content: Card Mode */}
            {style.ctaType === "card" && (
              <>
                {/* Template Presets */}
                <Section title="Pilih Template Card CTA">
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                    {CTA_TEMPLATES_CONFIG.map((tmpl) => {
                      const isSelected = style.template === tmpl.id;
                      const IconComp = tmpl.icon;
                      return (
                        <button
                          key={tmpl.id}
                          type="button"
                          onClick={() => applyTemplate(tmpl.id)}
                          className={cn(
                            "rounded-xl border p-3 text-left transition-all relative flex flex-col justify-between group",
                            isSelected
                              ? "border-emerald-500 bg-emerald-500/10 shadow-sm shadow-emerald-500/20"
                              : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700 hover:bg-zinc-900/40"
                          )}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className={cn("p-1.5 rounded-lg border transition-colors", isSelected ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" : "bg-zinc-900 text-zinc-400 border-zinc-800")}>
                              <IconComp className="h-4 w-4" />
                            </div>
                            <span className="rounded bg-zinc-800/80 px-1.5 py-0.5 text-[8px] font-semibold text-zinc-400 border border-zinc-700/50">
                              {tmpl.badge}
                            </span>
                          </div>
                          <div>
                            <p className={cn("text-[11px] font-bold", isSelected ? "text-emerald-300" : "text-zinc-200")}>
                              {tmpl.name}
                            </p>
                            <p className="text-[9px] text-zinc-500 mt-0.5 line-clamp-2 leading-relaxed">
                              {tmpl.desc}
                            </p>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </Section>

                {/* Content Customization */}
                <Section title="Konten Card CTA">
                  <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-950/40 p-3.5">
                    <div>
                      <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1">
                        Headline (Judul Utama Card)
                      </label>
                      <input
                        type="text"
                        value={style.headline}
                        onChange={(e) => update({ headline: e.target.value })}
                        placeholder="mis. Follow For More / Cek Link di Bio"
                        maxLength={60}
                        className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none transition-colors"
                      />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1">
                          Subhead (Keterangan / Slogan)
                        </label>
                        <input
                          type="text"
                          value={style.subhead}
                          onChange={(e) => update({ subhead: e.target.value })}
                          placeholder="mis. @yourchannel / Tips baru tiap hari"
                          maxLength={60}
                          className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none transition-colors"
                        />
                      </div>

                      <div>
                        <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1">
                          Teks Tombol / Action Badge
                        </label>
                        <input
                          type="text"
                          value={style.buttonText}
                          onChange={(e) => update({ buttonText: e.target.value })}
                          placeholder="mis. FOLLOW / KLIK LINK / SUBSCRIBE"
                          maxLength={30}
                          className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none transition-colors"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                      <SelectSmall
                        label="Platform Sosial"
                        value={style.socialPlatform}
                        onChange={(v) => update({ socialPlatform: v as any })}
                        options={CTA_PLATFORMS.map((p) => p.id)}
                      />
                      <div>
                        <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1">
                          Handle Akun Sosial
                        </label>
                        <input
                          type="text"
                          value={style.socialHandle}
                          onChange={(e) => update({ socialHandle: e.target.value })}
                          placeholder="@username"
                          maxLength={30}
                          className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none transition-colors"
                        />
                      </div>
                    </div>
                  </div>
                </Section>
              </>
            )}

            {/* Mode-Specific Content: Plain Text Mode */}
            {style.ctaType === "text" && (
              <Section title="Input Teks CTA">
                <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-950/40 p-3.5">
                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1">
                      Teks Pesan Penutup (CTA)
                    </label>
                    <textarea
                      rows={2}
                      value={style.text}
                      onChange={(e) => update({ text: e.target.value })}
                      placeholder="mis. Jangan lupa follow & share video ini ke teman kamu!"
                      maxLength={120}
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none transition-colors resize-none"
                    />
                  </div>
                  <div className="flex items-center justify-between pt-1">
                    <div>
                      <p className="text-[11px] font-medium text-zinc-200">Gunakan Background Box / Pill</p>
                      <p className="text-[9px] text-zinc-500">Beri latar belakang semi-transparan di belakang teks</p>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={style.bgBox}
                      onClick={() => update({ bgBox: !style.bgBox })}
                      className={cn("relative h-5 w-9 shrink-0 rounded-full transition-colors", style.bgBox ? "bg-emerald-600" : "bg-zinc-700")}
                    >
                      <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all", style.bgBox ? "left-[18px]" : "left-0.5")} />
                    </button>
                  </div>
                </div>
              </Section>
            )}

            {/* Mode-Specific Content: Both (Text + Icon) Mode */}
            {style.ctaType === "both" && (
              <Section title="Input Teks & Pilihan Icon Vector">
                <div className="space-y-3.5 rounded-lg border border-zinc-800 bg-zinc-950/40 p-3.5">
                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1">
                      Teks Pesan Penutup (CTA)
                    </label>
                    <input
                      type="text"
                      value={style.text}
                      onChange={(e) => update({ text: e.target.value })}
                      placeholder="mis. Follow untuk konten menarik berikutnya!"
                      maxLength={80}
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none transition-colors"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">
                      Pilih Icon Vector (Clean SVG)
                    </label>
                    <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                      {CTA_ICON_OPTIONS.map((item) => {
                        const isSelected = style.selectedIcon === item.id;
                        const IconComp = item.icon;
                        return (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => update({ selectedIcon: item.id })}
                            className={cn(
                              "flex items-center gap-2 rounded-lg border px-2.5 py-2 text-left transition-all",
                              isSelected
                                ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                                : "border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                            )}
                          >
                            <IconComp className="h-4 w-4 shrink-0 text-emerald-400" />
                            <span className="text-[10px] font-medium truncate">{item.label}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    <div>
                      <p className="text-[11px] font-medium text-zinc-200">Gunakan Background Box / Pill</p>
                      <p className="text-[9px] text-zinc-500">Tampilkan sebagai pill badge dengan latar transparan</p>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={style.bgBox}
                      onClick={() => update({ bgBox: !style.bgBox })}
                      className={cn("relative h-5 w-9 shrink-0 rounded-full transition-colors", style.bgBox ? "bg-emerald-600" : "bg-zinc-700")}
                    >
                      <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all", style.bgBox ? "left-[18px]" : "left-0.5")} />
                    </button>
                  </div>
                </div>
              </Section>
            )}

            {/* Styling, Positioning & Animation */}
            <Section title="Desain, Posisi & Animasi">
              <div className="space-y-3.5 rounded-lg border border-zinc-800 bg-zinc-950/40 p-3.5">
                {/* Position */}
                <div>
                  <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">
                    Posisi CTA di Video
                  </label>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {CTA_POSITIONS.map((pos) => (
                      <button
                        key={pos.id}
                        type="button"
                        onClick={() => update({ position: pos.id })}
                        className={cn(
                          "rounded-lg border py-2 text-[10px] font-medium transition-colors text-center",
                          style.position === pos.id
                            ? "border-emerald-500 bg-emerald-500/10 text-emerald-400 font-semibold"
                            : "border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                        )}
                      >
                        {pos.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Animation */}
                <div>
                  <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">
                    Animasi Muncul
                  </label>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                    {CTA_ANIMATIONS.map((anim) => (
                      <button
                        key={anim.id}
                        type="button"
                        onClick={() => update({ animation: anim.id })}
                        className={cn(
                          "rounded-lg border px-2.5 py-1.5 text-left transition-colors",
                          style.animation === anim.id
                            ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                            : "border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                        )}
                      >
                        <p className="text-[10px] font-semibold">{anim.label}</p>
                        <p className="text-[8px] text-zinc-500">{anim.desc}</p>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Color Pickers */}
                <div className="pt-1">
                  <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">
                    Warna Tombol / Aksen (Primary Color)
                  </label>
                  <div className="flex flex-wrap items-center gap-1.5 mb-2">
                    {CTA_COLOR_SWATCHES.map((hex) => (
                      <button
                        key={hex}
                        type="button"
                        onClick={() => update({ primaryColor: hex })}
                        className={cn(
                          "h-5 w-5 rounded-full border transition-transform",
                          style.primaryColor.toLowerCase() === hex.toLowerCase() ? "scale-125 border-white ring-2 ring-emerald-500/50" : "border-white/20 hover:scale-110"
                        )}
                        style={{ backgroundColor: hex }}
                      />
                    ))}
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                    <ColorPicker label="Warna Tombol / Aksen" value={style.primaryColor} onChange={(v) => update({ primaryColor: v })} />
                    <ColorPicker label="Warna Teks" value={style.textColor} onChange={(v) => update({ textColor: v })} />
                    <ColorPicker label="Warna Background" value={style.backgroundColor} onChange={(v) => update({ backgroundColor: v })} />
                  </div>
                </div>

                {/* Opacity & Typography */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                  <RangeInput
                    label={`Transparansi Background: ${style.bgOpacity}%`}
                    min={0}
                    max={100}
                    value={style.bgOpacity}
                    onChange={(v) => update({ bgOpacity: v })}
                  />
                  <RangeInput
                    label={`Ukuran Font: ${style.fontSize}px`}
                    min={18}
                    max={48}
                    value={style.fontSize}
                    onChange={(v) => update({ fontSize: v })}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <SelectSmall
                    label="Font Family"
                    value={style.fontFamily}
                    onChange={(v) => update({ fontFamily: v })}
                    options={FONT_OPTIONS}
                  />
                  <SelectSmall
                    label="Font Weight"
                    value={style.fontWeight}
                    onChange={(v) => update({ fontWeight: v })}
                    options={["400", "500", "600", "700", "800", "900"]}
                  />
                </div>
              </div>
            </Section>
          </>
        )}
      </div>

      {/* Right: Live Preview */}
      <div className="lg:col-span-4 flex min-h-0 flex-col items-center justify-center overflow-hidden bg-zinc-950 p-4">
        <div className="mb-3 flex w-full items-center justify-between gap-2">
          <p className="text-[9px] text-zinc-500 uppercase tracking-widest shrink-0 font-semibold">Live Mockup Preview</p>
          <span className="rounded-md border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[9px] font-medium text-emerald-400">
            {style.ctaType === "text" ? "Plain Text CTA" : style.ctaType === "both" ? "Text + Icon CTA" : "Creator Card CTA"}
          </span>
        </div>

        <div
          className="relative w-full max-w-[240px] max-h-[64vh] bg-zinc-900 rounded-xl overflow-hidden border border-zinc-800 shrink-0 shadow-2xl flex flex-col justify-between"
          style={{ aspectRatio: outerAspect }}
        >
          {/* Inject Dynamic Keyframes for CTA Preview Animations */}
          <style>{`
            @keyframes ctaSlideUpPreview {
              0% { transform: translateY(45px) scale(0.9); opacity: 0; }
              65% { transform: translateY(-4px) scale(1.02); opacity: 1; }
              100% { transform: translateY(0) scale(1); opacity: 1; }
            }
            @keyframes ctaPopInPreview {
              0% { transform: scale(0.15); opacity: 0; }
              55% { transform: scale(1.16); opacity: 1; }
              75% { transform: scale(0.94); opacity: 1; }
              100% { transform: scale(1); opacity: 1; }
            }
            @keyframes ctaFadeBouncePreview {
              0% { transform: scale(0.85) translateY(12px); opacity: 0; }
              65% { transform: scale(1.04) translateY(-2px); opacity: 1; }
              100% { transform: scale(1) translateY(0); opacity: 1; }
            }
            @keyframes ctaGlowPulsePreview {
              0%, 100% {
                transform: scale(0.97);
                box-shadow: 0 8px 25px rgba(0,0,0,0.6), 0 0 8px ${style.primaryColor}55;
              }
              50% {
                transform: scale(1.03);
                box-shadow: 0 12px 32px rgba(0,0,0,0.7), 0 0 22px ${style.primaryColor}cc, 0 0 35px ${style.primaryColor}66;
              }
            }
            @keyframes ctaGlitchCyberPreview {
              0%, 100% { transform: translate(0, 0); filter: none; clip-path: none; }
              12% { transform: translate(-3px, 1px); clip-path: inset(15% 0 45% 0); filter: drop-shadow(-2px 0 #00ffff) drop-shadow(2px 0 #ff0055); }
              24% { transform: translate(3px, -2px); clip-path: inset(50% 0 10% 0); filter: drop-shadow(2px 0 #00ffff) drop-shadow(-2px 0 #ff0055); }
              36% { transform: translate(-2px, -1px); clip-path: inset(25% 0 35% 0); }
              48% { transform: translate(1px, 2px); clip-path: none; filter: drop-shadow(-2px 0 #00ffff); }
              75% { transform: translate(0, 0); clip-path: none; filter: none; }
            }
          `}</style>

          {/* Background Canvas / Thumbnail */}
          {canvas ? (
            <div className="absolute inset-0" style={{ background: gradientCss(canvas.background) }}>
              {(canvas.backgroundImageUrl || canvas.background?.imageUrl) && (
                <img src={(canvas.backgroundImageUrl || canvas.background.imageUrl) as string} alt="" className="absolute inset-0 h-full w-full object-cover" />
              )}
              <CanvasAccents accents={canvas.accents || []} />
              {(canvas.background.vignette || 0) > 0 && (
                <div className="absolute inset-0 pointer-events-none" style={{ background: `radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,${canvas.background.vignette}) 100%)` }} />
              )}
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
                {thumbnailUrl ? (
                  <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-contain" />
                ) : (
                  <div className="w-full h-full bg-gradient-to-br from-zinc-800 to-zinc-900" />
                )}
              </div>
            </div>
          ) : (
            <>
              {thumbnailUrl ? (
                <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-cover" />
              ) : (
                <div className="absolute inset-0 bg-gradient-to-b from-zinc-800 via-zinc-900 to-black" />
              )}
            </>
          )}

          {/* Vignette overlay */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-black/30 pointer-events-none" />

          {/* Top Timing & Replay Indicator */}
          <div className="relative z-10 m-2 flex items-center justify-between gap-1">
            <span className="rounded bg-black/60 backdrop-blur-md px-2 py-0.5 text-[8px] font-medium text-zinc-300 border border-white/10 flex items-center gap-1">
              <Clock className="h-2.5 w-2.5 text-emerald-400" />
              {style.enabled ? `Muncul di ${style.duration.toFixed(1)}s terakhir` : "CTA Nonaktif"}
            </span>
            {style.enabled && (
              <button
                type="button"
                onClick={() => setReplayKey((k) => k + 1)}
                title="Putar Ulang Animasi"
                className="rounded bg-black/60 hover:bg-emerald-500/20 hover:text-emerald-300 hover:border-emerald-500/30 backdrop-blur-md px-1.5 py-0.5 text-[8px] font-medium text-zinc-400 border border-white/10 flex items-center gap-1 transition-all"
              >
                <RotateCcw className="h-2.5 w-2.5 text-emerald-400" />
                <span>Replay</span>
              </button>
            )}
          </div>

          {/* Animated CTA Preview based on Mode */}
          {style.enabled && (
            <div
              key={replayKey}
              className={cn(
                "absolute left-3 right-3 z-20",
                style.position === "top"
                  ? "top-10"
                  : style.position === "center"
                    ? "top-1/2 -translate-y-1/2"
                    : style.position === "lower-third"
                      ? "bottom-14"
                      : "bottom-4"
              )}
              style={getCtaAnimStyle(style.animation)}
            >
              {/* Card Mode Preview */}
              {style.ctaType === "card" && (
                <div
                  className="rounded-xl p-2.5 backdrop-blur-md flex items-center justify-between gap-2 transition-all shadow-xl"
                  style={{
                    backgroundColor: style.backgroundColor.startsWith("#")
                      ? `${style.backgroundColor}${Math.round((style.bgOpacity / 100) * 255).toString(16).padStart(2, "0")}`
                      : style.backgroundColor,
                    borderColor: `${style.primaryColor}55`,
                    borderWidth: "1.5px",
                    boxShadow: `0 8px 25px rgba(0,0,0,0.6), 0 0 15px ${style.primaryColor}33`,
                    color: style.textColor,
                    fontFamily: `'${style.fontFamily}', sans-serif`,
                  }}
                >
                  <div className="min-w-0 flex-1">
                    <p
                      className="truncate font-bold leading-snug"
                      style={{
                        fontSize: Math.max(9, Math.round(style.fontSize * 0.38)),
                        fontWeight: style.fontWeight as any,
                        color: style.textColor,
                      }}
                    >
                      {style.headline || "Follow For More"}
                    </p>
                    {(style.subhead || style.socialHandle) && (
                      <p className="truncate text-[8px] text-zinc-400 mt-1.5 font-medium leading-none">
                        {style.subhead || style.socialHandle}
                      </p>
                    )}
                  </div>

                  <div
                    className="rounded-full px-2.5 py-1 text-[8px] font-bold text-white shrink-0 flex items-center gap-1 shadow-md transition-transform hover:scale-105"
                    style={{
                      backgroundColor: style.primaryColor,
                      boxShadow: `0 2px 10px ${style.primaryColor}66`,
                    }}
                  >
                    {style.template === "subscribe_pill" && <Bell className="h-2.5 w-2.5" />}
                    {style.template === "follow_badge" && <Plus className="h-2.5 w-2.5" />}
                    {style.template === "link_bio" && <ArrowUpRight className="h-2.5 w-2.5" />}
                    {style.template === "like_share" && <Share2 className="h-2.5 w-2.5" />}
                    {style.template === "comment_prompt" && <MessageSquare className="h-2.5 w-2.5" />}
                    {style.template === "custom_card" && <Zap className="h-2.5 w-2.5" />}
                    <span>{style.buttonText || "FOLLOW"}</span>
                  </div>
                </div>
              )}

              {/* Plain Text Mode Preview */}
              {style.ctaType === "text" && (
                <div
                  className={cn(
                    "text-center transition-all",
                    style.bgBox ? "rounded-xl p-2.5 backdrop-blur-md shadow-xl border" : "p-1"
                  )}
                  style={{
                    backgroundColor: style.bgBox
                      ? (style.backgroundColor.startsWith("#")
                        ? `${style.backgroundColor}${Math.round((style.bgOpacity / 100) * 255).toString(16).padStart(2, "0")}`
                        : style.backgroundColor)
                      : "transparent",
                    borderColor: style.bgBox ? `${style.primaryColor}55` : "transparent",
                    boxShadow: style.bgBox ? `0 8px 25px rgba(0,0,0,0.6), 0 0 15px ${style.primaryColor}33` : "none",
                    fontFamily: `'${style.fontFamily}', sans-serif`,
                  }}
                >
                  <p
                    className="font-bold leading-snug"
                    style={{
                      fontSize: Math.max(9, Math.round(style.fontSize * 0.38)),
                      fontWeight: style.fontWeight as any,
                      color: style.textColor,
                      textShadow: style.bgBox ? "0 1px 4px rgba(0,0,0,0.5)" : "0 2px 8px rgba(0,0,0,0.9), 0 0 4px #000",
                    }}
                  >
                    {style.text || "Jangan lupa follow!"}
                  </p>
                </div>
              )}

              {/* Text + Icon (Both) Mode Preview */}
              {style.ctaType === "both" && (
                <div
                  className={cn(
                    "flex items-center justify-center gap-2 transition-all",
                    style.bgBox ? "rounded-full py-1.5 px-3 backdrop-blur-md shadow-xl border" : "p-1"
                  )}
                  style={{
                    backgroundColor: style.bgBox
                      ? (style.backgroundColor.startsWith("#")
                        ? `${style.backgroundColor}${Math.round((style.bgOpacity / 100) * 255).toString(16).padStart(2, "0")}`
                        : style.backgroundColor)
                      : "transparent",
                    borderColor: style.bgBox ? `${style.primaryColor}55` : "transparent",
                    boxShadow: style.bgBox ? `0 8px 25px rgba(0,0,0,0.6), 0 0 15px ${style.primaryColor}33` : "none",
                    fontFamily: `'${style.fontFamily}', sans-serif`,
                  }}
                >
                  <div
                    className="p-1 rounded-full text-white shrink-0 flex items-center justify-center"
                    style={{ backgroundColor: style.primaryColor }}
                  >
                    <SelectedIconComp className="h-3 w-3" />
                  </div>
                  <p
                    className="font-bold truncate text-left"
                    style={{
                      fontSize: Math.max(9, Math.round(style.fontSize * 0.36)),
                      fontWeight: style.fontWeight as any,
                      color: style.textColor,
                      textShadow: style.bgBox ? "0 1px 4px rgba(0,0,0,0.5)" : "0 2px 8px rgba(0,0,0,0.9), 0 0 4px #000",
                    }}
                  >
                    {style.text || "Follow untuk update!"}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Bottom helper text */}
          <p className="relative z-10 m-1.5 text-center text-[7px] text-zinc-500 font-medium">
            {style.enabled ? `${style.ctaType.toUpperCase()} · ${style.position} · ${style.animation}` : "CTA End-Card Nonaktif"}
          </p>
        </div>
      </div>
    </div>
  );
}
