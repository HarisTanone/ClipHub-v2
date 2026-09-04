import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Download,
  ExternalLink,
  Film,
  Globe,
  MapPin,
  Layers,
  Loader2,
  Palette,
  Play,
  Pause,
  RefreshCw,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Sparkles,
  Type,
  Video,
  Volume2,
  X,
  Trash2,
  Bookmark,
  MessageSquare,
  Flame,
  Heart,
  Share2,
  Music,
  Mic,
  Gauge,
  Lightbulb,
  Radio,
  Wand2,
  Compass,
  Upload,
  FileVideo,
  Cloud,
  Info,
  TrendingUp,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { RangeSlider } from "@/components/ui/RangeSlider";
import { Toggle } from "@/components/ui/Toggle";
import { useToast } from "@/components/ui/Toast";
import { confirmDialog } from "@/components/ui/ConfirmDialog";
import {
  DEFAULT_HOOK_STYLE,
  DEFAULT_SUBTITLE_STYLE,
  StyleEditorModal,
  HookPreviewRenderer,
  useGoogleFont,
  type HookStyle,
  type SubtitleStyle,
} from "@/components/StyleEditorModal";
import { ScheduleModal } from "@/components/ScheduleModal";
import {
  API_BASE,
  getToken,
  presets as presetsApi,
  hermesVideoGenApi,
  type Preset,
  type TrendingTopicItem,
} from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

// ─── Interfaces ───────────────────────────────────────────────────────────────

export interface FootageCandidate {
  video_id: string;
  title: string;
  url: string;
  thumbnail_url: string;
  duration_seconds: number;
  view_count: number;
  channel: string;
  query?: string;
  platform?: string;
}

export interface SceneItem {
  id: number;
  narration: string;
  visual: string;
  search_queries: string[];
  duration_estimate: number;
  transition?: string;
  footage_candidates?: FootageCandidate[];
  selected_footage?: FootageCandidate | null;
  footage_source?: FootageCandidate | null;
  start_timestamp?: number;
  end_timestamp?: number;
  start_mm_ss?: string;
  end_mm_ss?: string;
  alignment_score?: number;
  visual_summary?: string;
  alignment_reasoning?: string;
}

export interface VideoJob {
  job_id: string;
  topic: string;
  status: string;
  progress: number;
  step_label: string;
  target_duration: number;
  voice: string;
  speed: number;
  num_scenes: number;
  hook_enabled?: boolean;
  custom_hook?: string | null;
  hook_style_config?: Record<string, unknown>;
  subtitles_enabled: boolean;
  subtitle_style_config: Record<string, unknown>;
  include_bgm: boolean;
  bgm_volume: number;
  title: string | null;
  source_video_url?: string | null;
  agentic_understanding?: boolean;
  language?: string;
  video_processing_mode?: string;
  media_resolution?: string;
  fps?: number | null;
  start_offset?: number | null;
  end_offset?: number | null;
  error: string | null;
  output_path: string | null;
  created_at: number;
  completed_at: number | null;
  scenes_count: number;
  estimated_duration: number | null;
  thumbnail_url: string | null;
  scenes?: SceneItem[];
  aspect_ratio?: string;
  watermark_config?: Record<string, unknown>;
  transition?: string;
  cta_config?: Record<string, unknown>;
  ai_text_config?: Record<string, unknown>;
}

interface VoiceOption {
  key: string;
  model: string;
  provider?: string;
  description?: string;
  category?: string;
  gender?: string;
  accent?: string;
  language?: string;
  country?: string;
  flag?: string;
  preview_url?: string;
}

interface TTSModelOption {
  model_id: string;
  name: string;
  description?: string;
  free_tier?: boolean;
  languages?: string[];
}

interface TTSProviderOption {
  id: string;
  name: string;
  description: string;
  is_configured: boolean;
  default_model: string;
  default_voice: string;
}

interface JobListResponse {
  items: VideoJob[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}



function loadHookStyle(): HookStyle {
  try {
    const saved = localStorage.getItem("autocliper_video_generator_hook_style");
    return {
      ...DEFAULT_HOOK_STYLE,
      animation: "skia_impact_badge",
      fontFamily: "Anton",
      fontSize: 54,
      fontWeight: "800",
      position: "top",
      positionY: 15,
      boxEnabled: true,
      boxRadius: 14,
      bgColor: "#FACC15",
      color: "#000000",
      uppercase: true,
      ...(saved ? JSON.parse(saved) : {}),
    } as HookStyle;
  } catch {
    return {
      ...DEFAULT_HOOK_STYLE,
      animation: "skia_impact_badge",
      fontFamily: "Anton",
      fontSize: 54,
      fontWeight: "800",
      position: "top",
      positionY: 15,
      boxEnabled: true,
      boxRadius: 14,
      bgColor: "#FACC15",
      color: "#000000",
      uppercase: true,
    } as HookStyle;
  }
}

function loadSubtitleStyle(): SubtitleStyle {
  try {
    const saved = localStorage.getItem("autocliper_video_generator_subtitle_style");
    return {
      ...DEFAULT_SUBTITLE_STYLE,
      fontFamily: "Montserrat",
      fontSize: 54,
      fontWeight: "800",
      positionY: 84,
      maxWordsPerLine: 3,
      ...(saved ? JSON.parse(saved) : {}),
    } as SubtitleStyle;
  } catch {
    return {
      ...DEFAULT_SUBTITLE_STYLE,
      fontFamily: "Montserrat",
      fontSize: 54,
      fontWeight: "800",
      positionY: 84,
      maxWordsPerLine: 3,
    };
  }
}

async function fetchApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (response.status === 401 && token) {
    const refreshToken = localStorage.getItem("refresh_token");
    if (refreshToken) {
      try {
        const refreshRes = await fetch(`${API_BASE}/api/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (refreshRes.ok) {
          const data = await refreshRes.json();
          localStorage.setItem("access_token", data.access_token);
          localStorage.setItem("refresh_token", data.refresh_token);
          headers.set("Authorization", `Bearer ${data.access_token}`);
          response = await fetch(`${API_BASE}${path}`, { ...options, headers });
        }
      } catch {
        // ignore refresh failure
      }
    }
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || response.statusText);
  }
  return response.json() as Promise<T>;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function isProcessing(status: string): boolean {
  return !["completed", "failed", "awaiting_selection"].includes(status);
}

function formatViews(views: number): string {
  if (!views) return "";
  if (views >= 1000000) return `${(views / 1000000).toFixed(1)}M`;
  if (views >= 1000) return `${(views / 1000).toFixed(0)}K`;
  return String(views);
}

function StatusBadge({ status }: { status: string }) {
  const statusMap: Record<string, { icon: typeof CheckCircle2; className: string; label: string }> = {
    completed: { icon: CheckCircle2, className: "text-emerald-300 bg-emerald-500/10", label: "Completed" },
    failed: { icon: AlertCircle, className: "text-red-300 bg-red-500/10", label: "Failed" },
    queued: { icon: Clock, className: "text-zinc-300 bg-zinc-500/10", label: "Queued" },
    awaiting_selection: { icon: Layers, className: "text-amber-300 bg-amber-500/15 border border-amber-500/30", label: "Footage Ready" },
  };
  const entry = statusMap[status] || {
    icon: Loader2,
    className: "text-violet-300 bg-violet-500/10",
    label: "Processing",
  };
  const Icon = entry.icon;

  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[11px] font-medium", entry.className)}>
      <Icon className={cn("h-3 w-3", isProcessing(status) && "animate-spin")} />
      {entry.label}
    </span>
  );
}

function ProgressIndicator({ progress, stepLabel }: { progress: number; stepLabel: string }) {
  return (
    <div className="mt-3 space-y-1.5">
      <div className="flex items-center justify-between gap-3 text-[11px]">
        <span className="truncate text-zinc-400">{stepLabel || "Preparing generation..."}</span>
        <span className="shrink-0 tabular-nums text-zinc-500">{progress}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-zinc-800">
        <div
          className="h-full rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-400 transition-all duration-700 ease-out"
          style={{ width: `${Math.max(0, Math.min(progress, 100))}%` }}
        />
      </div>
    </div>
  );
}

function LiveVideoPreview({
  hookEnabled,
  customHook,
  hookStyle,
  subtitlesEnabled,
  subtitleStyle,
  topic,
  onCustomizeHook,
  onCustomizeSubtitle,
  aspectRatio = "9:16",
  watermarkEnabled = false,
  watermarkText = "",
  watermarkPosition = "bottom-right",
  watermarkOpacity = 0.75,
  ctaEnabled = false,
  ctaHeadline = "",
  ctaButtonText = "",
  aiTextEnabled = true,
}: {
  hookEnabled: boolean;
  customHook: string;
  hookStyle: HookStyle;
  subtitlesEnabled: boolean;
  subtitleStyle: SubtitleStyle;
  topic: string;
  onCustomizeHook: () => void;
  onCustomizeSubtitle: () => void;
  aspectRatio?: string;
  watermarkEnabled?: boolean;
  watermarkText?: string;
  watermarkPosition?: string;
  watermarkOpacity?: number;
  ctaEnabled?: boolean;
  ctaHeadline?: string;
  ctaButtonText?: string;
  aiTextEnabled?: boolean;
}) {
  const [activeWordIdx, setActiveWordIdx] = useState(0);
  const [previewMode, setPreviewMode] = useState<"full" | "hook" | "subtitles">("full");
  const [isPlaying, setIsPlaying] = useState(true);

  // Load Google Fonts for preview
  useGoogleFont(subtitleStyle.fontFamily || "Inter");
  useGoogleFont(hookStyle.fontFamily || "Montserrat");
  useGoogleFont("Inter");
  useGoogleFont("Montserrat");
  useGoogleFont("Anton");
  useGoogleFont("Archivo Black");
  useGoogleFont("Playfair Display");
  useGoogleFont("Space Grotesk");
  useGoogleFont("Barlow Condensed");
  useGoogleFont("Bebas Neue");
  useGoogleFont("Plus Jakarta Sans");
  useGoogleFont("Outfit");

  const hookText =
    customHook.trim() ||
    (topic.trim() ? topic.trim().slice(0, 52).toUpperCase() : "CAN AI REPLACE PROGRAMMERS?");

  const wordsCount = Math.max(1, Math.min(8, subtitleStyle.maxWordsPerLine || 3));

  // Dynamic sample words adapted from topic if available
  const sampleWords = useMemo(() => {
    if (topic.trim()) {
      const clean = topic
        .trim()
        .replace(/[^\w\s]/gi, "")
        .split(/\s+/)
        .filter(Boolean);
      if (clean.length >= wordsCount) {
        return clean.slice(0, wordsCount);
      }
      if (clean.length > 0) {
        const fillers = ["in", "this", "exclusive", "story", "now", "today", "deep", "mind"];
        return [...clean, ...fillers].slice(0, wordsCount);
      }
    }
    return ["Unveiling", "the", "hidden", "truth", "right", "now", "today", "here"].slice(0, wordsCount);
  }, [topic, wordsCount]);

  // Animate karaoke active word cycle
  useEffect(() => {
    if (!isPlaying) return;
    const timer = setInterval(() => {
      setActiveWordIdx((prev) => (prev + 1) % wordsCount);
    }, 600);
    return () => clearInterval(timer);
  }, [isPlaying, wordsCount]);

  // Subtitle styling calculations
  const subPosTop = `${subtitleStyle.positionY ?? (subtitleStyle.position === "top" ? 18 : subtitleStyle.position === "center" ? 50 : 80)}%`;
  const isWordPop = subtitleStyle.lineTransition === "word_pop";
  const isTyping = subtitleStyle.lineTransition === "typing";
  const currentSubIdx = activeWordIdx % sampleWords.length;
  const displayWords = isWordPop
    ? [sampleWords[currentSubIdx]]
    : isTyping
    ? sampleWords.slice(0, currentSubIdx + 1)
    : sampleWords;

  const hasSubBg = subtitleStyle.bgEnabled || Boolean(subtitleStyle.bgColor && subtitleStyle.bgOpacity > 0);
  const subBgHex = subtitleStyle.bgColor || "#000000";
  const subBgOpacity = subtitleStyle.bgOpacity ?? 0.75;
  const subBgAlpha = Math.round(Math.max(0, Math.min(1, subBgOpacity)) * 255).toString(16).padStart(2, "0");
  const subBgRadius = subtitleStyle.bgRadius ?? 10;
  const subBgPadding = subtitleStyle.bgPadding ?? 14;

  const subContainerStyle: React.CSSProperties = {
    display: "flex",
    flexWrap: isWordPop ? "nowrap" : "wrap",
    alignItems: "center",
    justifyContent: "center",
    maxWidth: "92%",
    gap: isWordPop ? 0 : "4px 8px",
    ...(hasSubBg
      ? {
          backgroundColor: `${subBgHex}${subBgAlpha}`,
          backdropFilter: "blur(8px)",
          WebkitBackdropFilter: "blur(8px)",
          borderRadius: `${subBgRadius}px`,
          padding: `${Math.round(subBgPadding * 0.35)}px ${Math.round(subBgPadding * 0.65)}px`,
          boxShadow: "0 8px 24px rgba(0,0,0,0.6)",
        }
      : {}),
  };

  return (
    <div className="flex flex-col items-center gap-3">
      {/* Mode Switcher Tabs */}
      <div className="flex items-center gap-1 rounded-xl bg-zinc-950/80 p-1 border border-zinc-800/80 text-[11px]">
        <button
          type="button"
          onClick={() => setPreviewMode("full")}
          className={cn(
            "flex items-center gap-1 px-2.5 py-1 rounded-lg font-medium transition",
            previewMode === "full"
              ? "bg-violet-500/20 text-violet-200 border border-violet-500/40 shadow-xs"
              : "text-zinc-400 hover:text-zinc-200"
          )}
        >
          <Film className="h-3 w-3" /> Full View
        </button>
        <button
          type="button"
          onClick={() => setPreviewMode("hook")}
          className={cn(
            "flex items-center gap-1 px-2.5 py-1 rounded-lg font-medium transition",
            previewMode === "hook"
              ? "bg-violet-500/20 text-violet-200 border border-violet-500/40 shadow-xs"
              : "text-zinc-400 hover:text-zinc-200"
          )}
        >
          <Sparkles className="h-3 w-3 text-violet-400" /> Hook (0-3s)
        </button>
        <button
          type="button"
          onClick={() => setPreviewMode("subtitles")}
          className={cn(
            "flex items-center gap-1 px-2.5 py-1 rounded-lg font-medium transition",
            previewMode === "subtitles"
              ? "bg-violet-500/20 text-violet-200 border border-violet-500/40 shadow-xs"
              : "text-zinc-400 hover:text-zinc-200"
          )}
        >
          <Type className="h-3 w-3 text-violet-400" /> Captions
        </button>
      </div>

      {/* Realistic Device Mockup Frame */}
      <div
        className={cn(
          "relative shrink-0 overflow-hidden rounded-[32px] border-[5px] border-zinc-800/90 bg-zinc-950 shadow-2xl ring-1 ring-white/15 transition-all duration-300",
          aspectRatio === "16:9"
            ? "aspect-[16/9] w-[310px] sm:w-[350px]"
            : aspectRatio === "1:1"
            ? "aspect-square w-[240px] sm:w-[260px]"
            : "aspect-[9/16] w-[230px] sm:w-[250px]"
        )}
      >
        {/* Dynamic Island Notch (visible in vertical 9:16) */}
        {aspectRatio === "9:16" && (
          <div className="absolute left-1/2 top-2 z-30 flex h-4 w-20 -translate-x-1/2 items-center justify-between rounded-full bg-black px-2.5 border border-zinc-800/80 shadow-md">
            <div className="h-1.5 w-1.5 rounded-full bg-zinc-700" />
            <div className="h-1.5 w-1.5 rounded-full bg-emerald-500/70" />
          </div>
        )}

        {/* Top Status Bar */}
        <div className="absolute left-0 right-0 top-1.5 z-20 flex items-center justify-between px-5 text-[9px] font-medium text-zinc-400">
          <span className="font-semibold text-zinc-300">9:41</span>
          <div className="flex items-center gap-1 text-[8px]">
            <span className="tracking-tight text-zinc-400 font-bold">5G</span>
            <div className="h-2 w-3 rounded-xs border border-zinc-400/80 p-0.5">
              <div className="h-full w-full bg-zinc-300 rounded-[1px]" />
            </div>
          </div>
        </div>

        {/* Dynamic Animated Cinematic Background */}
        <div className="absolute inset-0 bg-cover bg-center overflow-hidden">
          <div
            className="absolute inset-0 transition-transform duration-1000 scale-105"
            style={{
              backgroundImage: "radial-gradient(circle at 50% 30%, #4338ca 0%, #1e1b4b 45%, #09090b 85%, #000000 100%)",
            }}
          />
          {/* Subtle Cyber Grid Overlay */}
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff08_1px,transparent_1px),linear-gradient(to_bottom,#ffffff08_1px,transparent_1px)] bg-[size:16px_16px] opacity-30" />
          <div className="absolute inset-0 bg-gradient-to-b from-black/50 via-transparent to-black/85" />
        </div>

        {/* Right Side Social Overlay (TikTok / Reels style for 9:16) */}
        {aspectRatio === "9:16" && (
          <div className="absolute right-2 bottom-16 z-20 flex flex-col items-center gap-3">
            <div className="relative flex h-7 w-7 items-center justify-center rounded-full border border-white/30 bg-zinc-800 text-[10px] font-bold text-white shadow-md">
              AI
            </div>
            <div className="flex flex-col items-center">
              <Heart className="h-4 w-4 text-rose-500 fill-rose-500 drop-shadow-md" />
              <span className="text-[8px] font-medium text-white/90 drop-shadow">184K</span>
            </div>
            <div className="flex flex-col items-center">
              <MessageSquare className="h-4 w-4 text-white drop-shadow-md" />
              <span className="text-[8px] font-medium text-white/90 drop-shadow">1.4K</span>
            </div>
            <div className="flex flex-col items-center">
              <Bookmark className="h-4 w-4 text-amber-400 fill-amber-400 drop-shadow-md" />
              <span className="text-[8px] font-medium text-white/90 drop-shadow">12K</span>
            </div>
            <div className="flex flex-col items-center">
              <Share2 className="h-4 w-4 text-white drop-shadow-md" />
            </div>
            {/* Spinning Music Vinyl */}
            <div className="relative flex h-6 w-6 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900 shadow-md animate-[spin_4s_linear_infinite]">
              <Music className="h-3 w-3 text-violet-300" />
            </div>
          </div>
        )}

        {/* Bottom Metadata Safe Area */}
        <div className="absolute left-3 right-12 bottom-3 z-20 space-y-1 text-left">
          <p className="text-[10px] font-semibold text-white drop-shadow-sm flex items-center gap-1">
            @autoclipper <CheckCircle2 className="h-2.5 w-2.5 text-blue-400 inline fill-blue-400" />
          </p>
          <p className="text-[9px] text-white/80 line-clamp-1 drop-shadow-sm">
            {topic.trim() ? topic.trim() : "Watch how this AI video generator builds high-converting clips"}
          </p>
          <div className="flex items-center gap-1 text-[8px] text-white/70">
            <Music className="h-2.5 w-2.5 animate-pulse text-violet-300" />
            <span className="truncate">Deepgram Aura · AutoCliper Mix</span>
          </div>
          {/* Timeline Bar */}
          <div className="h-0.5 w-full bg-white/20 rounded-full overflow-hidden mt-1">
            <div className="h-full w-1/3 bg-white/90 rounded-full animate-pulse" />
          </div>
        </div>

        {/* Opening Hook Overlay (100% Visual match with StyleEditorModal) */}
        {hookEnabled && (previewMode === "full" || previewMode === "hook") ? (
          <div
            onClick={onCustomizeHook}
            className="absolute inset-0 z-20 cursor-pointer transition-all hover:scale-[1.02]"
            title="Click to customize opening hook in Style Editor"
          >
            <HookPreviewRenderer style={hookStyle} customText={hookText} scale={0.88} />
          </div>
        ) : null}

        {/* Karaoke Subtitles Overlay (100% Visual match with StyleEditorModal) */}
        {subtitlesEnabled && (previewMode === "full" || previewMode === "subtitles") ? (
          <div
            onClick={onCustomizeSubtitle}
            className="absolute left-0 right-0 z-20 flex justify-center px-3 cursor-pointer transition-all hover:scale-[1.03]"
            style={{ top: subPosTop, transform: "translateY(-50%)" }}
            title="Click to customize captions in Style Editor"
          >
            <div style={subContainerStyle}>
              {displayWords.map((w, idx) => {
                const isActive = isWordPop ? true : idx === currentSubIdx;
                const textFormatted = subtitleStyle.uppercase
                  ? w.toUpperCase()
                  : subtitleStyle.capitalize
                  ? w.charAt(0).toUpperCase() + w.slice(1)
                  : w;

                const fontSize = Math.min(Math.max((subtitleStyle.fontSize || 48) * 0.23, 11), 18);
                const fontWeight = isActive ? 900 : Number(subtitleStyle.fontWeight || 800);
                const textColor = isActive ? subtitleStyle.highlightColor || "#FACC15" : subtitleStyle.color || "#FFFFFF";

                const textShadow =
                  subtitleStyle.strokeEnabled || subtitleStyle.shadowEnabled
                    ? `0 1.5px ${Math.max(2, (subtitleStyle.shadowBlur || 8) * 0.3)}px ${subtitleStyle.strokeColor || "#000000"}`
                    : undefined;

                return (
                  <span
                    key={idx}
                    className={cn(
                      "transition-all duration-150 inline-block",
                      isActive && "scale-110 drop-shadow-[0_2px_10px_rgba(250,204,21,0.6)]"
                    )}
                    style={{
                      fontFamily: subtitleStyle.fontFamily
                        ? `'${subtitleStyle.fontFamily}', sans-serif`
                        : "Montserrat, sans-serif",
                      fontSize: `${fontSize}px`,
                      fontWeight,
                      fontStyle: subtitleStyle.italic ? "italic" : "normal",
                      color: textColor,
                      textShadow,
                      WebkitTextStroke: subtitleStyle.strokeEnabled
                        ? `${Math.max(0.6, (subtitleStyle.strokeWidth || 3.5) * 0.22)}px ${subtitleStyle.strokeColor || "#000000"}`
                        : undefined,
                      letterSpacing: `${subtitleStyle.letterSpacing || 0}px`,
                    }}
                  >
                    {textFormatted}
                  </span>
                );
              })}
            </div>
          </div>
        ) : null}

        {/* Watermark Branding */}
        {watermarkEnabled && watermarkText.trim() ? (
          <div
            className={cn(
              "absolute z-25 px-2 py-0.5 rounded text-[9px] font-mono font-semibold tracking-wider pointer-events-none select-none shadow-xs",
              watermarkPosition === "top-left" && "top-8 left-3",
              watermarkPosition === "top-right" && "top-8 right-3",
              watermarkPosition === "bottom-left" && "bottom-14 left-3",
              (!watermarkPosition || watermarkPosition === "bottom-right") && "bottom-14 right-3"
            )}
            style={{
              color: "rgba(255, 255, 255, 0.95)",
              backgroundColor: "rgba(0, 0, 0, 0.55)",
              opacity: watermarkOpacity ?? 0.75,
            }}
          >
            {watermarkText.trim()}
          </div>
        ) : null}

        {/* Call to Action (CTA) Outro Preview */}
        {ctaEnabled ? (
          <div className="absolute inset-x-3 bottom-12 z-25 flex flex-col items-center gap-1 rounded-xl bg-gradient-to-r from-violet-600/90 to-indigo-600/90 p-2 text-center text-white shadow-lg backdrop-blur-xs">
            <span className="text-[10px] font-bold line-clamp-1">{ctaHeadline || "Follow & Subscribe!"}</span>
            <span className="rounded-full bg-white px-2 py-0.5 text-[8px] font-bold text-zinc-900 shadow-xs">
              {ctaButtonText || "Follow Sekarang"}
            </span>
          </div>
        ) : null}

        {/* AI Motion Text Badge */}
        {aiTextEnabled ? (
          <div className="absolute top-8 left-3 z-20 flex items-center gap-1 rounded-full bg-violet-500/20 border border-violet-500/40 px-1.5 py-0.5 text-[8px] text-violet-200">
            <Sparkles className="h-2 w-2" /> AI Motion
          </div>
        ) : null}
      </div>

      {/* Quick Action Trigger Buttons */}
      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="xs"
          variant="outline"
          onClick={onCustomizeHook}
          icon={<Sparkles className="h-3 w-3 text-violet-400" />}
        >
          Hook Style
        </Button>
        <Button
          type="button"
          size="xs"
          variant="outline"
          onClick={onCustomizeSubtitle}
          icon={<Palette className="h-3 w-3 text-violet-400" />}
        >
          Subtitle Style
        </Button>
        <button
          type="button"
          onClick={() => setIsPlaying((p) => !p)}
          className="flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900/80 px-2 py-1 text-[11px] text-zinc-400 hover:text-zinc-200 transition"
          title="Play/Pause live karaoke preview"
        >
          {isPlaying ? <Pause className="h-3 w-3 text-zinc-300" /> : <Play className="h-3 w-3 text-zinc-400" />}
          {isPlaying ? "Playing" : "Paused"}
        </button>
      </div>
    </div>
  );
}

function VideoModal({
  job,
  onClose,
  onDownload,
  onPublishSocial,
}: {
  job: VideoJob;
  onClose: () => void;
  onDownload: (jobId: string) => void;
  onPublishSocial: (job: VideoJob) => void;
}) {
  const token = getToken();
  const streamUrl = `${API_BASE}/api/video-generator/jobs/${job.job_id}/stream?token=${encodeURIComponent(token || "")}`;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Video preview" className="relative w-full max-w-[320px] max-h-[90vh] flex flex-col" onClick={(event) => event.stopPropagation()}>
        <button type="button" aria-label="Close preview" onClick={onClose} className="absolute -top-9 right-0 rounded-lg p-1 text-zinc-400 transition-colors hover:bg-white/10 hover:text-white">
          <X className="h-5 w-5" />
        </button>
        <div className="mb-2.5">
          <p className="truncate text-xs font-semibold text-zinc-100">{job.title || job.topic}</p>
          <p className="text-[11px] text-zinc-500">{job.scenes_count || "—"} scenes · {job.target_duration}s target</p>
        </div>
        <div className="aspect-[9/16] max-h-[68vh] overflow-hidden rounded-xl border border-zinc-700/80 bg-black shadow-2xl flex items-center justify-center">
          <video src={streamUrl} controls autoPlay playsInline preload="metadata" className="h-full w-full object-contain" />
        </div>
        <div className="mt-3 flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="flex-1 text-violet-400 border-violet-500/30 hover:bg-violet-500/10 hover:text-violet-300"
            onClick={() => {
              onClose();
              onPublishSocial(job);
            }}
            icon={<Share2 className="h-4 w-4" />}
          >
            Post to Social
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => onDownload(job.job_id)}
            icon={<Download className="h-4 w-4" />}
          >
            Download
          </Button>
        </div>
      </div>
    </div>
  );
}

// ─── Scene & Footage Studio Modal/Drawer (Interactive Footage Picker) ──────────

function SceneFootageStudioModal({
  job,
  onClose,
  onStartRender,
  onUpdateJob,
}: {
  job: VideoJob;
  onClose: () => void;
  onStartRender: (jobId: string, updatedScenes: SceneItem[]) => Promise<void>;
  onUpdateJob?: (job: VideoJob) => void;
}) {
  const toast = useToast();
  const [currentJob, setCurrentJob] = useState<VideoJob>(job);
  const [scenes, setScenes] = useState<SceneItem[]>(() => {
    return (job.scenes || []).map((s) => ({
      ...s,
      selected_footage: s.selected_footage || s.footage_source || (s.footage_candidates?.[0] || null),
    }));
  });

  // Keep currentJob in sync with prop
  useEffect(() => {
    setCurrentJob(job);
  }, [job]);

  // Active polling when job is still in planning / processing state
  useEffect(() => {
    const shouldPoll = isProcessing(currentJob.status) || !currentJob.scenes || currentJob.scenes.length === 0;
    if (!shouldPoll) return;

    let isMounted = true;
    const interval = window.setInterval(async () => {
      try {
        const updated = await fetchApi<VideoJob>(`/api/video-generator/jobs/${currentJob.job_id}`);
        if (isMounted && updated) {
          setCurrentJob(updated);
          onUpdateJob?.(updated);
        }
      } catch {
        // ignore transient network errors
      }
    }, 2000);

    return () => {
      isMounted = false;
      window.clearInterval(interval);
    };
  }, [currentJob.job_id, currentJob.status, currentJob.scenes, onUpdateJob]);

  // Sync internal scenes when currentJob.scenes updates (e.g. from planning background task or polling)
  useEffect(() => {
    if (currentJob.scenes && currentJob.scenes.length > 0) {
      setScenes((prev) => {
        if (prev.length === 0) {
          return currentJob.scenes!.map((s) => ({
            ...s,
            selected_footage: s.selected_footage || s.footage_source || (s.footage_candidates?.[0] || null),
          }));
        }
        // Preserve user selections for existing scenes while bringing in any new candidates
        return currentJob.scenes!.map((s) => {
          const existing = prev.find((p) => p.id === s.id);
          return {
            ...s,
            narration: existing?.narration ?? s.narration,
            selected_footage:
              existing?.selected_footage !== undefined
                ? existing.selected_footage
                : s.selected_footage || s.footage_source || (s.footage_candidates?.[0] || null),
          };
        });
      });
    }
  }, [currentJob.scenes]);
  const [searchingSceneId, setSearchingSceneId] = useState<number | null>(null);
  const [sceneSearchQueries, setSceneSearchQueries] = useState<Record<number, string>>({});
  const [isRendering, setIsRendering] = useState(false);

  const selectedCount = scenes.filter((s) => s.selected_footage).length;

  const handleSelectFootage = (sceneId: number, candidate: FootageCandidate) => {
    setScenes((prev) =>
      prev.map((s) => {
        if (s.id !== sceneId) return s;
        // Toggle selection if clicking the already selected candidate
        const isCurrent =
          s.selected_footage?.video_id === candidate.video_id ||
          s.selected_footage?.url === candidate.url;
        return {
          ...s,
          selected_footage: isCurrent ? null : candidate,
        };
      })
    );
  };

  const handleUpdateNarration = (sceneId: number, text: string) => {
    setScenes((prev) =>
      prev.map((s) => (s.id === sceneId ? { ...s, narration: text } : s))
    );
  };

  const handleAutoSelectAll = () => {
    setScenes((prev) =>
      prev.map((s) => ({
        ...s,
        selected_footage: s.footage_candidates?.[0] || null,
      }))
    );
    toast.success("Auto-selected best footage candidates for all scenes");
  };

  const handleClearAll = () => {
    setScenes((prev) =>
      prev.map((s) => ({
        ...s,
        selected_footage: null,
      }))
    );
    toast.info("Cleared footage selections (will use auto fallback)");
  };

  const handleSearchCustomForScene = async (sceneId: number) => {
    const query = sceneSearchQueries[sceneId]?.trim();
    if (!query) return;

    setSearchingSceneId(sceneId);
    try {
      const res = await fetchApi<{ scene_id: number; candidates: FootageCandidate[] }>(
        `/api/video-generator/jobs/${currentJob.job_id}/search-scene`,
        {
          method: "POST",
          body: JSON.stringify({ scene_id: sceneId, query }),
        }
      );
      setScenes((prev) =>
        prev.map((s) => {
          if (s.id === sceneId) {
            const newCandidates = res.candidates || [];
            return {
              ...s,
              footage_candidates: newCandidates,
              selected_footage: newCandidates[0] || s.selected_footage,
            };
          }
          return s;
        })
      );
      toast.success(`Found ${res.candidates?.length || 0} new footage candidates`);
    } catch (e: any) {
      toast.error(errorMessage(e, "Failed to search footage for scene"));
    } finally {
      setSearchingSceneId(null);
    }
  };

  const handleConfirmRender = async () => {
    setIsRendering(true);
    try {
      await onStartRender(currentJob.job_id, scenes);
      onClose();
    } catch (e: any) {
      toast.error(errorMessage(e, "Render launch failed"));
    } finally {
      setIsRendering(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-3 sm:p-6 backdrop-blur-md">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Scene & Footage Studio"
        className="flex flex-col h-[92vh] w-full max-w-5xl rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-zinc-800 p-3 sm:px-5 sm:py-3.5 bg-zinc-900/60 shrink-0 gap-2.5">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-8 w-8 rounded-lg bg-violet-500/15 border border-violet-500/30 flex items-center justify-center text-violet-300 shrink-0">
              <Layers className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-zinc-100 truncate">
                Footage Studio: {currentJob.title || currentJob.topic}
              </h2>
              <p className="text-[11px] text-zinc-400">
                Select footage 1 by 1 per scene or search custom footage before rendering.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap shrink-0 justify-between sm:justify-end w-full sm:w-auto">
            <span className="text-xs text-zinc-400 bg-zinc-800/80 px-2.5 py-1 rounded-md tabular-nums">
              {selectedCount} / {scenes.length} selected
            </span>
            <Button size="xs" variant="ghost" onClick={handleAutoSelectAll}>
              Auto-Select Top
            </Button>
            <Button size="xs" variant="ghost" onClick={handleClearAll} className="text-zinc-500 hover:text-zinc-300">
              Clear All
            </Button>
            <button
              type="button"
              onClick={onClose}
              className="p-1 rounded-lg text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition ml-auto sm:ml-0"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Scene List */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4">
          {scenes.length === 0 ? (
            isProcessing(currentJob.status) ? (
              <div className="py-16 text-center space-y-3">
                <Loader2 className="mx-auto h-9 w-9 animate-spin text-violet-400" />
                <div>
                  <p className="text-sm font-semibold text-zinc-200">
                    {currentJob.step_label || "AI is planning scenes & finding footage candidates..."}
                  </p>
                  <p className="text-xs text-zinc-400 mt-1">
                    This takes ~5-15 seconds. Footage candidates will appear here automatically.
                  </p>
                </div>
                <div className="max-w-xs mx-auto pt-2">
                  <ProgressIndicator progress={currentJob.progress} stepLabel={currentJob.step_label} />
                </div>
              </div>
            ) : (
              <div className="py-12 text-center text-zinc-500">
                <Film className="mx-auto h-8 w-8 mb-2 opacity-50" />
                <p className="text-sm">No scenes generated for this job.</p>
                {currentJob.error && (
                  <p className="text-xs text-red-400 mt-2 max-w-md mx-auto">{currentJob.error}</p>
                )}
              </div>
            )
          ) : (
            scenes.map((scene, idx) => {
              const isSelectedSome = Boolean(scene.selected_footage);
              const candidates = scene.footage_candidates || [];

              return (
                <div
                  key={scene.id || idx}
                  className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-4 space-y-3.5 transition"
                >
                  {/* Scene header & narration */}
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div className="space-y-1.5 flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center justify-center px-2 py-0.5 rounded text-[10px] font-bold bg-violet-500/20 text-violet-300 border border-violet-500/30">
                          Scene {idx + 1}
                        </span>
                        {idx === 0 && (
                          <span className="text-[10px] font-medium text-amber-300 bg-amber-500/10 px-1.5 py-0.2 rounded border border-amber-500/20">
                            Hook
                          </span>
                        )}
                        {idx === scenes.length - 1 && (
                          <span className="text-[10px] font-medium text-emerald-300 bg-emerald-500/10 px-1.5 py-0.2 rounded border border-emerald-500/20">
                            Conclusion
                          </span>
                        )}
                        <span className="text-[11px] text-zinc-500">
                          ~{scene.duration_estimate || 7}s
                        </span>
                      </div>

                      {/* Editable narration */}
                      <div>
                        <label className="text-[10px] font-medium text-zinc-400 block mb-1">
                          Narration Script:
                        </label>
                        <textarea
                          rows={2}
                          value={scene.narration}
                          onChange={(e) => handleUpdateNarration(scene.id, e.target.value)}
                          className="w-full resize-none rounded-lg border border-zinc-800 bg-zinc-950/80 px-3 py-1.5 text-xs text-zinc-200 focus:border-violet-500/60 outline-none leading-relaxed transition"
                        />
                      </div>
                      {scene.visual && (
                        <p className="text-[11px] text-zinc-500 leading-tight">
                          <span className="text-zinc-400 font-medium">Visual cue:</span> {scene.visual}
                        </p>
                      )}
                      {/* Gemini Video Understanding Alignment Summary */}
                      {(scene.alignment_score !== undefined || scene.start_mm_ss || scene.visual_summary) && (
                        <div className="rounded-lg border border-violet-500/30 bg-violet-950/20 p-2.5 space-y-1 text-xs">
                          <div className="flex items-center justify-between gap-2 flex-wrap">
                            <div className="flex items-center gap-1.5 font-medium text-violet-300">
                              <Sparkles className="h-3.5 w-3.5 text-violet-400" />
                              <span>Gemini Video Alignment</span>
                            </div>
                            <div className="flex items-center gap-1.5">
                              {scene.alignment_score !== undefined && (
                                <span className={cn(
                                  "px-2 py-0.5 rounded text-[10px] font-bold border",
                                  scene.alignment_score >= 8
                                    ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                                    : scene.alignment_score >= 5
                                    ? "bg-amber-500/20 text-amber-300 border-amber-500/30"
                                    : "bg-red-500/20 text-red-300 border-red-500/30"
                                )}>
                                  Score {scene.alignment_score.toFixed(1)}/10
                                </span>
                              )}
                              {(scene.start_mm_ss || scene.start_timestamp !== undefined) && (
                                <span className="font-mono text-[10px] bg-black/40 px-2 py-0.5 rounded border border-white/10 text-zinc-300">
                                  Interval: {scene.start_mm_ss || `${scene.start_timestamp?.toFixed(1)}s`} - {scene.end_mm_ss || `${scene.end_timestamp?.toFixed(1)}s`}
                                </span>
                              )}
                            </div>
                          </div>
                          {scene.visual_summary && (
                            <p className="text-[11px] text-zinc-300">
                              <span className="text-zinc-500 font-medium">Visual:</span> {scene.visual_summary}
                            </p>
                          )}
                          {scene.alignment_reasoning && (
                            <p className="text-[10px] text-zinc-400 italic">
                              "{scene.alignment_reasoning}"
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Footage Selection Row */}
                  <div className="space-y-2 pt-2 border-t border-zinc-800/60">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <p className="text-[11px] font-medium text-zinc-300 flex items-center gap-1.5">
                        <Video className="h-3.5 w-3.5 text-violet-400" />
                        Select Footage ({candidates.length} candidates):
                      </p>

                      {/* Scene specific re-search bar */}
                      <div className="flex items-center gap-1.5">
                        <input
                          type="text"
                          placeholder="Search other footage for this scene..."
                          value={sceneSearchQueries[scene.id] || ""}
                          onChange={(e) =>
                            setSceneSearchQueries((prev) => ({
                              ...prev,
                              [scene.id]: e.target.value,
                            }))
                          }
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleSearchCustomForScene(scene.id);
                          }}
                          className="rounded-md border border-zinc-800 bg-zinc-950 px-2.5 py-1 text-[11px] text-zinc-200 placeholder:text-zinc-600 outline-none focus:border-zinc-700 w-full sm:w-64 flex-1 sm:flex-initial"
                        />
                        <Button
                          size="xs"
                          variant="outline"
                          loading={searchingSceneId === scene.id}
                          disabled={searchingSceneId === scene.id || !sceneSearchQueries[scene.id]?.trim()}
                          onClick={() => handleSearchCustomForScene(scene.id)}
                          icon={<Search className="h-3 w-3" />}
                        >
                          Search
                        </Button>
                      </div>
                    </div>

                    {/* Candidate Cards Grid */}
                    {candidates.length === 0 ? (
                      <p className="text-xs text-zinc-600 py-3">No footage candidates found. Try searching with keywords above.</p>
                    ) : (
                      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
                        {candidates.map((cand) => {
                          const isSelected =
                            scene.selected_footage?.video_id === cand.video_id ||
                            scene.selected_footage?.url === cand.url;

                          const pLower = (cand.platform || "").toLowerCase();
                          const platformLabel =
                            pLower === "pexels"
                              ? "Pexels"
                              : pLower === "pixabay"
                              ? "Pixabay"
                              : pLower === "tiktok"
                              ? "TikTok"
                              : pLower === "instagram"
                              ? "Reels"
                              : pLower === "threads"
                              ? "Threads"
                              : pLower === "twitter" || pLower === "x"
                              ? "X"
                              : "YouTube";

                          const platformColor =
                            pLower === "pexels"
                              ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/30"
                              : pLower === "pixabay"
                              ? "bg-sky-950/80 text-sky-300 border-sky-500/30"
                              : pLower === "tiktok"
                              ? "bg-cyan-950/80 text-cyan-300 border-cyan-500/30"
                              : pLower === "instagram"
                              ? "bg-pink-950/80 text-pink-300 border-pink-500/30"
                              : pLower === "threads"
                              ? "bg-zinc-800 text-zinc-200 border-zinc-600"
                              : pLower === "twitter" || pLower === "x"
                              ? "bg-slate-900 text-slate-200 border-slate-700"
                              : "bg-red-950/80 text-red-300 border-red-500/30";

                          return (
                            <div
                              key={cand.video_id}
                              onClick={() => handleSelectFootage(scene.id, cand)}
                              className={cn(
                                "group relative flex flex-col rounded-lg border overflow-hidden cursor-pointer text-left transition-all",
                                isSelected
                                  ? "border-violet-500 bg-violet-500/10 ring-1 ring-violet-500 shadow-md"
                                  : "border-zinc-800 bg-zinc-950/60 hover:border-zinc-700"
                              )}
                            >
                              {/* Thumbnail */}
                              <div className="relative aspect-[16/9] w-full bg-zinc-900 overflow-hidden">
                                {cand.thumbnail_url ? (
                                  <img
                                    src={cand.thumbnail_url}
                                    alt=""
                                    className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-300"
                                  />
                                ) : (
                                  <div className="h-full w-full flex items-center justify-center text-zinc-700">
                                    <Film className="h-6 w-6" />
                                  </div>
                                )}

                                {/* Selected badge */}
                                {isSelected && (
                                  <div className="absolute top-1.5 right-1.5 h-5 w-5 rounded-full bg-violet-500 text-white flex items-center justify-center shadow">
                                    <Check className="h-3.5 w-3.5 stroke-[3]" />
                                  </div>
                                )}

                                {/* Platform badge */}
                                <span
                                  className={cn(
                                    "absolute bottom-1 left-1 px-1.5 py-0.2 rounded text-[9px] font-semibold border backdrop-blur-xs",
                                    platformColor
                                  )}
                                >
                                  {platformLabel}
                                </span>

                                {cand.duration_seconds > 0 && (
                                  <span className="absolute bottom-1 right-1 px-1.5 py-0.2 rounded text-[9px] tabular-nums bg-black/75 text-zinc-300">
                                    {cand.duration_seconds}s
                                  </span>
                                )}
                              </div>

                              {/* Card Content */}
                              <div className="p-2 flex-1 flex flex-col justify-between">
                                <p className="text-[11px] font-medium text-zinc-200 line-clamp-2 leading-tight" title={cand.title}>
                                  {cand.title}
                                </p>
                                <div className="mt-1 flex items-center justify-between text-[10px] text-zinc-500">
                                  <span className="truncate max-w-[80px]">{cand.channel}</span>
                                  {cand.view_count > 0 && <span>{formatViews(cand.view_count)} views</span>}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-zinc-800 px-5 py-3.5 bg-zinc-900/80 shrink-0">
          <p className="text-xs text-zinc-400">
            {selectedCount === scenes.length
              ? "All scenes configured. Ready to render final video."
              : `${scenes.length - selectedCount} scene(s) remaining without selected footage.`}
          </p>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              size="sm"
              variant="primary"
              disabled={isRendering || selectedCount === 0}
              loading={isRendering}
              onClick={handleConfirmRender}
              icon={<Sparkles className="h-3.5 w-3.5" />}
            >
              Render Video ({selectedCount}/{scenes.length} scenes)
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function VideoCard({
  job,
  onPlay,
  onDownload,
  onPublishSocial,
  onRetry,
  onDelete,
  onOpenStudio,
  isRetrying,
}: {
  job: VideoJob;
  onPlay: (job: VideoJob) => void;
  onDownload: (jobId: string) => void;
  onPublishSocial?: (job: VideoJob) => void;
  onRetry: (jobId: string) => void;
  onDelete: (jobId: string) => void;
  onOpenStudio: (job: VideoJob) => void;
  isRetrying?: boolean;
}) {
  const completed = job.status === "completed";
  const isAwaitingSelection = job.status === "awaiting_selection";
  const processing = isProcessing(job.status);

  return (
    <Card className="group overflow-hidden p-0 flex flex-col justify-between border border-zinc-800/80 bg-zinc-900/60 hover:border-violet-500/40 transition-all duration-200 shadow-xs hover:shadow-md">
      {/* Compact Preview Banner (Constrained height h-40 sm:h-44, not oversized aspect-[9/16]) */}
      <div className="relative h-40 sm:h-44 w-full overflow-hidden bg-zinc-950 flex items-center justify-center">
        {/* Ambient Blurred Background from Thumbnail */}
        {job.thumbnail_url ? (
          <img
            src={job.thumbnail_url}
            alt=""
            aria-hidden="true"
            className="absolute inset-0 h-full w-full object-cover blur-md opacity-25 scale-110"
          />
        ) : (
          <div className="absolute inset-0 bg-gradient-to-br from-violet-950/20 via-zinc-900 to-black opacity-60" />
        )}

        {/* Centered Crisp 9:16 Miniature Vertical Phone Frame */}
        <button
          type="button"
          disabled={!completed}
          onClick={() => completed && onPlay(job)}
          className={cn(
            "relative z-10 h-32 sm:h-36 w-[72px] sm:w-[81px] rounded-lg overflow-hidden border border-white/15 bg-black shadow-lg flex items-center justify-center transition-transform duration-200",
            completed ? "cursor-pointer group-hover:scale-105 group-hover:border-violet-400/60" : ""
          )}
        >
          {job.thumbnail_url ? (
            <img
              src={job.thumbnail_url}
              alt={job.title || job.topic}
              className="h-full w-full object-cover"
            />
          ) : (
            <Film className="h-6 w-6 text-zinc-600" />
          )}

          {completed && (
            <span className="absolute inset-0 flex items-center justify-center bg-black/35 opacity-80 group-hover:opacity-100 transition-opacity">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/25 text-white backdrop-blur-xs shadow-md pl-0.5 group-hover:scale-110 transition-transform">
                <Play className="h-4 w-4 fill-white" />
              </span>
            </span>
          )}

          {isAwaitingSelection && (
            <span className="absolute inset-0 flex flex-col items-center justify-center bg-black/75 p-1 text-center">
              <Layers className="h-5 w-5 text-amber-300 animate-pulse" />
              <span className="text-[9px] font-semibold text-amber-200 mt-1 leading-tight">Ready</span>
            </span>
          )}

          {processing && (
            <span className="absolute inset-0 flex flex-col items-center justify-center bg-black/75 p-1 text-center">
              <Loader2 className="h-5 w-5 animate-spin text-violet-300" />
              <span className="text-[9px] text-violet-200 mt-1">{job.progress}%</span>
            </span>
          )}

          {job.status === "failed" && (
            <span className="absolute inset-0 flex flex-col items-center justify-center bg-black/75 p-1 text-center">
              <AlertCircle className="h-5 w-5 text-red-400" />
            </span>
          )}
        </button>

        {/* Top Badges */}
        <div className="absolute top-2 left-2 z-20">
          <StatusBadge status={job.status} />
        </div>

        <div className="absolute top-2 right-2 z-20 flex items-center gap-1">
          {job.source_video_url && (
            <span
              className="rounded-md bg-black/60 px-1.5 py-0.5 text-[9px] font-medium text-violet-300 border border-violet-500/30 backdrop-blur-xs flex items-center gap-1"
              title={`Gemini Video Understanding (${job.video_processing_mode || "agentic"}, ${job.media_resolution || "low"} res)`}
            >
              <Sparkles className="h-2.5 w-2.5" />
              {job.video_processing_mode === "static" ? "Static Vision" : "Agentic Vision"}
            </span>
          )}
          <span className="rounded-md bg-black/60 px-1.5 py-0.5 text-[9px] font-medium text-zinc-300 border border-white/10 backdrop-blur-xs">
            9:16
          </span>
        </div>

        {/* Bottom Banner Pill */}
        <div className="absolute bottom-1.5 left-2 right-2 z-20 flex items-center justify-between text-[10px] text-zinc-400 px-1">
          <span className="flex items-center gap-1 bg-black/50 px-1.5 py-0.5 rounded border border-white/5 backdrop-blur-xs">
            <Clock className="h-2.5 w-2.5 text-zinc-400" /> {job.target_duration}s
          </span>
          <span className="flex items-center gap-1 bg-black/50 px-1.5 py-0.5 rounded border border-white/5 backdrop-blur-xs">
            <Layers className="h-2.5 w-2.5 text-zinc-400" /> {job.scenes_count || "—"} scenes
          </span>
        </div>
      </div>

      {/* Card Content & Actions */}
      <div className="p-2.5 space-y-2">
        <div>
          <p
            className="truncate text-xs font-semibold text-zinc-200 hover:text-white transition-colors"
            title={job.title || job.topic}
          >
            {job.title || job.topic}
          </p>
          <div className="mt-0.5 flex items-center justify-between text-[10px] text-zinc-500">
            <span className="truncate max-w-[120px]">
              {job.voice ? `Voice: ${job.voice}` : "Default Voice"}
            </span>
            <span>
              {job.created_at ? new Date(job.created_at * 1000).toLocaleDateString() : ""}
            </span>
          </div>
        </div>

        {processing && (
          <div className="space-y-1">
            <ProgressIndicator progress={job.progress} stepLabel={job.step_label} />
          </div>
        )}

        {job.error && (
          <p className="line-clamp-2 text-[10px] leading-3.5 text-red-400" title={job.error}>
            {job.error}
          </p>
        )}

        {/* Action Buttons */}
        <div className="pt-1 flex items-center justify-between gap-1 border-t border-zinc-800/60">
          <div className="flex flex-wrap items-center gap-1">
            {isAwaitingSelection && (
              <Button
                type="button"
                size="xs"
                variant="primary"
                onClick={() => onOpenStudio(job)}
                className="h-6 px-2 text-[10px]"
                icon={<Layers className="h-2.5 w-2.5" />}
              >
                Studio
              </Button>
            )}

            {completed && (
              <>
                <Button
                  type="button"
                  size="xs"
                  variant="outline"
                  onClick={() => onPlay(job)}
                  className="h-6 px-2 text-[10px] text-zinc-200 hover:text-white"
                  icon={<Play className="h-2.5 w-2.5 text-violet-400" />}
                >
                  Watch
                </Button>
                <Button
                  type="button"
                  size="xs"
                  variant="outline"
                  onClick={() => onDownload(job.job_id)}
                  className="h-6 px-1.5 text-[10px] text-zinc-300"
                  icon={<Download className="h-2.5 w-2.5" />}
                >
                  Download
                </Button>
                <Button
                  type="button"
                  size="xs"
                  variant="outline"
                  className="h-6 px-1.5 text-[10px] text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10"
                  onClick={() => onPublishSocial?.(job)}
                  icon={<Share2 className="h-2.5 w-2.5" />}
                >
                  Post
                </Button>
              </>
            )}

            {job.status === "failed" && (
              <Button
                type="button"
                size="xs"
                variant="outline"
                loading={isRetrying}
                disabled={isRetrying}
                onClick={() => onRetry(job.job_id)}
                className="h-6 px-2 text-[10px]"
                icon={<RotateCcw className="h-2.5 w-2.5" />}
              >
                Retry
              </Button>
            )}
          </div>

          <button
            type="button"
            className="p-1 rounded text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition ml-auto"
            onClick={() => onDelete(job.job_id)}
            title="Delete Job"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      </div>
    </Card>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

function TrendingRadarModal({
  isOpen,
  onClose,
  topics,
  isLoading,
  region,
  onRegionChange,
  onRefresh,
  onSelectTopic,
}: {
  isOpen: boolean;
  onClose: () => void;
  topics: TrendingTopicItem[];
  isLoading: boolean;
  region: string;
  onRegionChange: (reg: string) => void;
  onRefresh: () => void;
  onSelectTopic: (t: TrendingTopicItem) => void;
}) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-3 sm:p-4">
      <div className="relative w-full max-w-3xl max-h-[85vh] flex flex-col rounded-2xl border border-zinc-800 bg-zinc-900 shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4 bg-zinc-900/90">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400">
              <Flame className="h-5 w-5 fill-amber-400" />
            </div>
            <div>
              <h3 className="text-base font-bold text-zinc-100 flex items-center gap-2">
                Hermes Trending Radar
                <span className="text-[10px] font-semibold text-amber-300 bg-amber-500/15 border border-amber-500/30 px-2 py-0.5 rounded-full">
                  Multi-Source Real-Time
                </span>
              </h3>
              <p className="text-xs text-zinc-400">
                Agregasi algoritma YouTube Data API v3, Google Trends, TikTok & Gemini AI
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Region & Actions Filter Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800/80 px-5 py-3 bg-zinc-950/40">
          <div className="flex flex-wrap items-center gap-1.5">
            {[
              { id: "ID", label: "Indonesia", isGlobal: false },
              { id: "GLOBAL", label: "Worldwide", isGlobal: true },
              { id: "US", label: "United States", isGlobal: false },
              { id: "MY", label: "Malaysia", isGlobal: false },
              { id: "SG", label: "Singapore", isGlobal: false },
              { id: "GB", label: "UK", isGlobal: false },
              { id: "JP", label: "Japan", isGlobal: false },
            ].map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => onRegionChange(r.id)}
                className={cn(
                  "rounded-lg px-2.5 py-1 text-xs font-medium transition inline-flex items-center gap-1.5",
                  region === r.id
                    ? "bg-amber-500/20 text-amber-200 border border-amber-500/40 shadow-xs"
                    : "border border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700"
                )}
              >
                {r.isGlobal ? (
                  <Globe className="h-3 w-3 text-amber-400" />
                ) : (
                  <MapPin className="h-3 w-3 text-zinc-400" />
                )}
                <span>{r.label}</span>
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={onRefresh}
            disabled={isLoading}
            className="flex items-center gap-1.5 rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-1 text-xs text-zinc-300 hover:border-zinc-700 hover:text-white transition"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isLoading && "animate-spin text-amber-400")} />
            <span>{isLoading ? "Memindai..." : "Pindai Ulang"}</span>
          </button>
        </div>

        {/* Modal Body: Topic Cards List */}
        <div className="flex-1 overflow-y-auto p-5 space-y-3.5">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-16 text-center space-y-3">
              <Loader2 className="h-8 w-8 animate-spin text-amber-400" />
              <p className="text-sm font-medium text-zinc-200">
                Menghubungkan ke YouTube Data API, Google Trends & TikTok...
              </p>
              <p className="text-xs text-zinc-500 max-w-sm">
                Gemini AI sedang memvalidasi topik paling ramai, menganalisis hook viral, dan menyusun poin pembahasan.
              </p>
            </div>
          ) : topics.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center space-y-2">
              <AlertCircle className="h-8 w-8 text-zinc-500" />
              <p className="text-sm text-zinc-300">Belum ada topik trending untuk wilayah ini.</p>
              <Button size="sm" variant="outline" onClick={onRefresh}>
                Coba Pindai Lagi
              </Button>
            </div>
          ) : (
            topics.map((t, idx) => (
              <div
                key={idx}
                className="group relative rounded-xl border border-zinc-800/90 bg-zinc-900/60 p-4 hover:border-amber-500/50 hover:bg-zinc-900 transition-all space-y-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-amber-500/15 border border-amber-500/30 text-xs font-bold text-amber-300">
                      #{idx + 1}
                    </span>
                    <div>
                      <h4 className="text-sm font-bold text-zinc-100 group-hover:text-amber-200 transition-colors">
                        {t.topic}
                      </h4>
                      <p className="text-xs text-zinc-400 mt-0.5">{t.angle}</p>
                    </div>
                  </div>

                  <Button
                    type="button"
                    size="xs"
                    variant="primary"
                    onClick={() => {
                      onSelectTopic(t);
                      onClose();
                    }}
                    icon={<Sparkles className="h-3 w-3" />}
                  >
                    Gunakan Topik
                  </Button>
                </div>

                {/* Hook Box */}
                {t.hook && (
                  <div className="rounded-lg border border-violet-500/20 bg-violet-950/20 px-3 py-2 text-xs">
                    <span className="font-semibold text-violet-300">Suggested Hook: </span>
                    <span className="text-zinc-200 font-medium italic">"{t.hook}"</span>
                  </div>
                )}

                {/* Key Points */}
                {t.key_points && t.key_points.length > 0 && (
                  <div className="space-y-1 text-xs text-zinc-400">
                    <span className="font-medium text-zinc-300">Poin Pembahasan Narasi:</span>
                    <ul className="list-disc list-inside space-y-0.5 pl-1">
                      {t.key_points.map((pt, ptIdx) => (
                        <li key={ptIdx}>{pt}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Metadata Tags */}
                <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-zinc-800/60 text-[10px]">
                  {t.source && (
                    <span className="rounded bg-zinc-800 px-2 py-0.5 text-zinc-300 font-medium">
                      Sumber: {t.source}
                    </span>
                  )}
                  {t.traffic_estimate && (
                    <span className="rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 px-2 py-0.5">
                      Estimasi: {t.traffic_estimate}
                    </span>
                  )}
                  {t.search_keywords && t.search_keywords.map((kw, kwIdx) => (
                    <span key={kwIdx} className="rounded bg-zinc-800/80 px-1.5 py-0.5 text-zinc-400">
                      #{kw}
                    </span>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between border-t border-zinc-800 px-5 py-3 bg-zinc-900/90 text-xs text-zinc-500">
          <span>Menampilkan {topics.length} topik trending harian paling ramai.</span>
          <Button size="xs" variant="outline" onClick={onClose}>
            Tutup
          </Button>
        </div>
      </div>
    </div>
  );
}

const CREATIVE_TONES = [
  { label: "Viral Hook", prompt: "Fast-paced viral storytelling with punchy surprising facts." },
  { label: "Cinematic", prompt: "Atmospheric, mysterious mood with dramatic tension and deep questions." },
  { label: "Explainer", prompt: "Clear, authoritative breakdown focusing on technical mechanics." },
  { label: "Storytelling", prompt: "Reflective narrative ending with a thought-provoking conclusion." },
];

export function VideoGeneratorPage() {
  const { user } = useAuth();
  const toast = useToast();

  // Basic narrative state
  const [topic, setTopic] = useState("");
  const [sourceVideoUrl, setSourceVideoUrl] = useState("");
  const [isAgenticVideoMode, setIsAgenticVideoMode] = useState(false);
  const [agenticUnderstanding, setAgenticUnderstanding] = useState(true);
  const [videoInputMethod, setVideoInputMethod] = useState<"youtube" | "upload" | "cloud">("youtube");
  const [videoProcessingMode, setVideoProcessingMode] = useState<"agentic" | "static">("agentic");
  const [mediaResolution, setMediaResolution] = useState<"low" | "high">("low");
  const [staticFps, setStaticFps] = useState<number>(1.0);
  const [startOffsetStr, setStartOffsetStr] = useState<string>("");
  const [endOffsetStr, setEndOffsetStr] = useState<string>("");
  const [uploadedVideoFile, setUploadedVideoFile] = useState<{
    filename: string;
    size_bytes: number;
    duration: number;
    duration_mm_ss: string;
    is_inline_eligible: boolean;
  } | null>(null);
  const [isUploadingSourceVideo, setIsUploadingSourceVideo] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const parseMmSsToSeconds = (val: string): number | undefined => {
    if (!val || !val.trim()) return undefined;
    const parts = val.trim().split(":");
    if (parts.length === 2) {
      const m = parseFloat(parts[0]);
      const s = parseFloat(parts[1]);
      if (!isNaN(m) && !isNaN(s)) return m * 60 + s;
    }
    const n = parseFloat(val);
    return isNaN(n) ? undefined : n;
  };

  const handleUploadSourceVideo = async (file: File) => {
    if (!file) return;
    setIsUploadingSourceVideo(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const token = getToken();
      const res = await fetch(`${API_BASE}/api/video-generator/upload-source-video`, {
        method: "POST",
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Upload failed" }));
        throw new Error(err.detail || "Gagal mengunggah video");
      }
      const data = await res.json();
      setSourceVideoUrl(data.file_path);
      setUploadedVideoFile({
        filename: data.filename,
        size_bytes: data.size_bytes,
        duration: data.duration,
        duration_mm_ss: data.duration_mm_ss,
        is_inline_eligible: data.is_inline_eligible,
      });
      toast.success(`Video '${file.name}' siap dianalisis Gemini!`);
    } catch (err: any) {
      toast.error(err.message || "Gagal mengunggah video");
    } finally {
      setIsUploadingSourceVideo(false);
    }
  };
  const [targetDuration, setTargetDuration] = useState(65);
  const [ttsProvider, setTtsProvider] = useState<"gemini" | "deepgram">("gemini");
  const [ttsModel, setTtsModel] = useState<string>("gemini-3.1-flash-tts-preview");
  const [ttsModels, setTtsModels] = useState<TTSModelOption[]>([]);
  const [ttsProviders, setTtsProviders] = useState<TTSProviderOption[]>([]);
  const [voice, setVoice] = useState("Kore");
  const [customVoiceId, setCustomVoiceId] = useState("");
  const [selectedCountry, setSelectedCountry] = useState<string>("All");
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);
  const audioPreviewRef = useRef<HTMLAudioElement | null>(null);
  const [speed, setSpeed] = useState(1);
  const [numScenes, setNumScenes] = useState(0);
  const [instructions, setInstructions] = useState("");

  // Hook Overlay state
  const [hookEnabled, setHookEnabled] = useState<boolean>(() => {
    const saved = localStorage.getItem("autocliper_video_generator_hook_enabled");
    return saved !== null ? saved === "true" : true;
  });
  const [customHook, setCustomHook] = useState<string>("");
  const [hookStyle, setHookStyle] = useState<HookStyle>(loadHookStyle);

  // Subtitle / Captions state
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(true);
  const [subtitleStyle, setSubtitleStyle] = useState<SubtitleStyle>(loadSubtitleStyle);

  // Background Music state
  const [includeBgm, setIncludeBgm] = useState(true);
  const [bgmVolume, setBgmVolume] = useState(0.15);

  // Presets & Editor Modal state
  const [userPresets, setUserPresets] = useState<Preset[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<string>("");
  const [showStyleEditor, setShowStyleEditor] = useState(false);
  const [activeStyleTab, setActiveStyleTab] = useState<"presets" | "hook" | "subtitle">("subtitle");

  // Dynamic Trending Topics state (Multi-source Hermes engine)
  const [trendingTopics, setTrendingTopics] = useState<TrendingTopicItem[]>([]);
  const [isLoadingTrending, setIsLoadingTrending] = useState(false);
  const [trendingRegion, setTrendingRegion] = useState("ID");
  const [showTrendingModal, setShowTrendingModal] = useState(false);

  // Aspect Ratio & Visual Elements state
  const [aspectRatio, setAspectRatio] = useState<"9:16" | "16:9" | "1:1">("9:16");
  const [transitionStyle, setTransitionStyle] = useState<string>("fade");
  const [watermarkEnabled, setWatermarkEnabled] = useState<boolean>(false);
  const [watermarkText, setWatermarkText] = useState<string>("");
  const [watermarkPosition, setWatermarkPosition] = useState<string>("bottom-right");
  const [watermarkOpacity, setWatermarkOpacity] = useState<number>(0.75);
  const [ctaEnabled, setCtaEnabled] = useState<boolean>(false);
  const [ctaHeadline, setCtaHeadline] = useState<string>("Follow & Subscribe untuk Konten Menarik Lainnya!");
  const [ctaButtonText, setCtaButtonText] = useState<string>("Follow Sekarang");
  const [aiTextEnabled, setAiTextEnabled] = useState<boolean>(true);

  // Job and list state
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [jobs, setJobs] = useState<VideoJob[]>([]);
  const [totalJobs, setTotalJobs] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const [activeJob, setActiveJob] = useState<VideoJob | null>(null);
  const [studioJob, setStudioJob] = useState<VideoJob | null>(null);
  const [publishJob, setPublishJob] = useState<VideoJob | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPlanning, setIsPlanning] = useState(false);
  const [isRetrying, setIsRetrying] = useState<string | null>(null);
  const [loadError, setLoadError] = useState("");

  const handleTogglePlayVoice = useCallback((voiceOpt?: VoiceOption | null) => {
    if (!voiceOpt) return;

    if (playingVoiceId === voiceOpt.model) {
      if (audioPreviewRef.current) {
        audioPreviewRef.current.pause();
        audioPreviewRef.current.currentTime = 0;
      }
      setPlayingVoiceId(null);
      return;
    }

    if (!voiceOpt.preview_url) {
      toast.error("Audio preview belum tersedia untuk suara ini.");
      return;
    }

    if (audioPreviewRef.current) {
      audioPreviewRef.current.pause();
    }

    const token = getToken();
    const rawUrl = voiceOpt.preview_url;
    let fullUrl = rawUrl.startsWith("http") ? rawUrl : `${API_BASE}${rawUrl}`;
    if (token) {
      fullUrl = fullUrl.includes("?")
        ? `${fullUrl}&token=${encodeURIComponent(token)}`
        : `${fullUrl}?token=${encodeURIComponent(token)}`;
    }

    const audio = new Audio(fullUrl);
    audioPreviewRef.current = audio;
    setPlayingVoiceId(voiceOpt.model);

    audio.play().catch(() => {
      setPlayingVoiceId(null);
      toast.error("Gagal memutar audio preview.");
    });

    audio.onended = () => {
      setPlayingVoiceId(null);
    };
    audio.onerror = () => {
      setPlayingVoiceId(null);
    };
  }, [playingVoiceId, toast]);

  useEffect(() => {
    return () => {
      if (audioPreviewRef.current) {
        audioPreviewRef.current.pause();
      }
    };
  }, []);

  const availableCountries = useMemo(() => {
    const list = voices
      .filter((v) => !v.provider || v.provider === ttsProvider)
      .map((v) => v.country || "Global / Multi")
      .filter(Boolean);
    const unique = Array.from(new Set(list));
    unique.sort((a, b) => {
      if (a === "Indonesia") return -1;
      if (b === "Indonesia") return 1;
      return a.localeCompare(b);
    });
    return ["All", ...unique];
  }, [voices, ttsProvider]);

  const filteredVoices = useMemo(() => {
    return voices.filter((v) => {
      const matchProvider = !v.provider || v.provider === ttsProvider;
      if (!matchProvider) return false;
      if (selectedCountry === "All") return true;
      return (v.country || "Global / Multi") === selectedCountry;
    });
  }, [voices, ttsProvider, selectedCountry]);

  const activeVoiceOption = useMemo(() => {
    if (customVoiceId) return null;
    return voices.find((v) => v.model === voice && (!v.provider || v.provider === ttsProvider)) || filteredVoices[0] || null;
  }, [voices, voice, customVoiceId, ttsProvider, filteredVoices]);

  const loadJobs = useCallback(async (targetPage = page) => {
    try {
      const response = await fetchApi<JobListResponse>(`/api/video-generator/jobs?page=${targetPage}&limit=8`);
      setJobs(response.items || []);
      setTotalJobs(response.total || 0);
      setPage(response.page || 1);
      setTotalPages(response.total_pages || 1);
      setLoadError("");
    } catch (error) {
      setLoadError(errorMessage(error, "Unable to load generated videos."));
    } finally {
      setIsLoading(false);
    }
  }, [page]);

  const loadVoices = useCallback(async () => {
    try {
      const response = await fetchApi<VoiceOption[]>("/api/video-generator/voices");
      setVoices(response || []);
    } catch {
      setVoices([]);
    }
  }, []);

  const loadTTSModels = useCallback(async () => {
    try {
      const response = await fetchApi<TTSModelOption[]>("/api/video-generator/models");
      if (response && response.length > 0) {
        setTtsModels(response);
      } else {
        setTtsModels([
          { model_id: "gemini-3.1-flash-tts-preview", name: "Gemini 3.1 Flash TTS", description: "Model terbaru, sangat ekspresif, respons cepat & intonasi natural (Free Tier)", free_tier: true },
          { model_id: "gemini-2.5-flash-preview-tts", name: "Gemini 2.5 Flash TTS", description: "Cepat, efisien, optimal untuk batch & volume tinggi (Free Tier)", free_tier: true },
          { model_id: "gemini-2.5-pro-preview-tts", name: "Gemini 2.5 Pro TTS", description: "Kualitas studio audio tinggi, podcast & narasi mendalam", free_tier: false },
        ]);
      }
    } catch {
      setTtsModels([
        { model_id: "gemini-3.1-flash-tts-preview", name: "Gemini 3.1 Flash TTS", description: "Model terbaru, sangat ekspresif, respons cepat & intonasi natural (Free Tier)", free_tier: true },
        { model_id: "gemini-2.5-flash-preview-tts", name: "Gemini 2.5 Flash TTS", description: "Cepat, efisien, optimal untuk batch & volume tinggi (Free Tier)", free_tier: true },
        { model_id: "gemini-2.5-pro-preview-tts", name: "Gemini 2.5 Pro TTS", description: "Kualitas studio audio tinggi, podcast & narasi mendalam", free_tier: false },
      ]);
    }
  }, []);

  const loadTTSProviders = useCallback(async () => {
    try {
      const response = await fetchApi<TTSProviderOption[]>("/api/video-generator/tts-providers");
      setTtsProviders(response || []);
    } catch {
      setTtsProviders([]);
    }
  }, []);

  const loadUserPresets = useCallback(async () => {
    try {
      const list = await presetsApi.list();
      setUserPresets(list || []);
    } catch {
      setUserPresets([]);
    }
  }, []);

  const loadTrendingTopics = useCallback(async (region = trendingRegion, refresh = false) => {
    setIsLoadingTrending(true);
    try {
      const data = await hermesVideoGenApi.getTrendingTopics(region, 5, refresh);
      setTrendingTopics(data.topics || []);
    } catch (err) {
      console.error("Failed to load trending topics:", err);
    } finally {
      setIsLoadingTrending(false);
    }
  }, [trendingRegion]);

  const handleSelectTrendingTopic = (t: TrendingTopicItem) => {
    setTopic(t.topic);
    if (t.hook) {
      setCustomHook(t.hook);
    }
    const points = t.key_points && t.key_points.length > 0 ? `Poin pembahasan: ${t.key_points.join(", ")}.` : "";
    const angleText = t.angle ? ` Angle: ${t.angle}.` : "";
    const kwText = t.search_keywords && t.search_keywords.length > 0 ? ` Keywords: ${t.search_keywords.join(", ")}.` : "";
    setInstructions(`${angleText}${points}${kwText}`.trim());
    if (t.recommended_cta) {
      setCtaHeadline(t.recommended_cta);
    }
    toast.success(`Topik "${t.topic}" dipilih! Hook & narasi disesuaikan.`);
  };

  useEffect(() => {
    void loadJobs();
    void loadVoices();
    void loadTTSModels();
    void loadTTSProviders();
    void loadUserPresets();
    void loadTrendingTopics();
  }, [loadJobs, loadVoices, loadTTSModels, loadTTSProviders, loadUserPresets, loadTrendingTopics]);

  useEffect(() => {
    localStorage.setItem("autocliper_video_generator_hook_enabled", String(hookEnabled));
  }, [hookEnabled]);

  useEffect(() => {
    localStorage.setItem("autocliper_video_generator_hook_style", JSON.stringify(hookStyle));
  }, [hookStyle]);

  useEffect(() => {
    localStorage.setItem("autocliper_video_generator_subtitle_style", JSON.stringify(subtitleStyle));
  }, [subtitleStyle]);

  const hasProcessingJob = useMemo(() => {
    return (
      jobs.some((job) => isProcessing(job.status)) ||
      (studioJob ? isProcessing(studioJob.status) : false) ||
      (activeJob ? isProcessing(activeJob.status) : false) ||
      isPlanning ||
      isSubmitting
    );
  }, [jobs, studioJob, activeJob, isPlanning, isSubmitting]);

  useEffect(() => {
    if (!hasProcessingJob) return undefined;
    const timer = window.setInterval(() => {
      void loadJobs();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [hasProcessingJob, loadJobs]);

  const handleUpdateStudioJob = useCallback((updatedJob: VideoJob) => {
    setStudioJob((prev) => (prev?.job_id === updatedJob.job_id ? updatedJob : prev));
    setJobs((prev) => {
      const idx = prev.findIndex((j) => j.job_id === updatedJob.job_id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = updatedJob;
        return next;
      }
      return [updatedJob, ...prev];
    });
  }, []);

  useEffect(() => {
    if (!activeJob) return;
    const updatedJob = jobs.find((job) => job.job_id === activeJob.job_id);
    if (updatedJob && updatedJob !== activeJob) setActiveJob(updatedJob);
  }, [activeJob, jobs]);

  useEffect(() => {
    if (!studioJob) return;
    const updatedJob = jobs.find((job) => job.job_id === studioJob.job_id);
    if (updatedJob && updatedJob !== studioJob) setStudioJob(updatedJob);
  }, [studioJob, jobs]);

  // Preset Selection Handler
  const handleSelectPreset = (presetId: string) => {
    setSelectedPresetId(presetId);
    if (!presetId) return;

    const matched = userPresets.find((p) => String(p.id) === presetId);
    if (matched) {
      if (matched.hook_style && Object.keys(matched.hook_style).length > 0) {
        setHookStyle((prev) => ({ ...prev, ...matched.hook_style }));
      }
      if (matched.subtitle_style && Object.keys(matched.subtitle_style).length > 0) {
        setSubtitleStyle((prev) => ({ ...prev, ...matched.subtitle_style, engine: "ffmpeg" }));
      }
      toast.success(`Preset "${matched.name}" loaded for Hook & Subtitles`);
    }
  };

  // One-click quick generation (Auto mode)
  const handleQuickSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const effectiveTopic = topic.trim() || (isAgenticVideoMode && sourceVideoUrl.trim() ? "Source Video Highlights" : "");
    if (!effectiveTopic || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const selectedVoice = customVoiceId.trim() || voice;
      await fetchApi<VideoJob>("/api/video-generator/generate", {
        method: "POST",
        body: JSON.stringify({
          topic: effectiveTopic,
          target_duration: targetDuration,
          tts_provider: ttsProvider,
          tts_model: ttsProvider === "gemini" ? ttsModel : undefined,
          voice: selectedVoice,
          speed,
          num_scenes: numScenes,
          instructions: instructions.trim(),
          hook_enabled: hookEnabled,
          custom_hook: customHook.trim() || undefined,
          hook_style_config: hookStyle,
          subtitles_enabled: subtitlesEnabled,
          subtitle_style_config: { ...subtitleStyle, engine: subtitleStyle.engine || "remotion" },
          include_bgm: includeBgm,
          bgm_volume: bgmVolume,
          aspect_ratio: aspectRatio,
          transition: transitionStyle,
          watermark_config: watermarkEnabled && watermarkText.trim() ? {
            text: watermarkText.trim(),
            position: watermarkPosition,
            opacity: watermarkOpacity,
          } : undefined,
          cta_config: ctaEnabled && ctaHeadline.trim() ? {
            headline: ctaHeadline.trim(),
            button_text: ctaButtonText.trim(),
          } : undefined,
          ai_text_config: {
            enabled: aiTextEnabled,
          },
          source_video_url: isAgenticVideoMode && sourceVideoUrl.trim() ? sourceVideoUrl.trim() : undefined,
          agentic_understanding: agenticUnderstanding,
          video_processing_mode: isAgenticVideoMode ? videoProcessingMode : "agentic",
          media_resolution: isAgenticVideoMode ? mediaResolution : "low",
          fps: isAgenticVideoMode && videoProcessingMode === "static" ? staticFps : undefined,
          start_offset: isAgenticVideoMode && videoProcessingMode === "static" ? parseMmSsToSeconds(startOffsetStr) : undefined,
          end_offset: isAgenticVideoMode && videoProcessingMode === "static" ? parseMmSsToSeconds(endOffsetStr) : undefined,
        }),
      });
      setPage(1);
      void loadJobs(1);
      setTopic("");
      setInstructions("");
      toast.success("Video generation started in background.");
    } catch (error) {
      toast.error(errorMessage(error, "Failed to start video generation."));
    } finally {
      setIsSubmitting(false);
    }
  };

  // Studio Mode: Plan story + search footage, then open studio
  const handleStudioPlan = async () => {
    const effectiveTopic = topic.trim() || (isAgenticVideoMode && sourceVideoUrl.trim() ? "Source Video Highlights" : "");
    if (!effectiveTopic || isPlanning) return;

    setIsPlanning(true);
    try {
      const selectedVoice = customVoiceId.trim() || voice;
      const job = await fetchApi<VideoJob>("/api/video-generator/plan", {
        method: "POST",
        body: JSON.stringify({
          topic: effectiveTopic,
          target_duration: targetDuration,
          tts_provider: ttsProvider,
          tts_model: ttsProvider === "gemini" ? ttsModel : undefined,
          voice: selectedVoice,
          speed,
          num_scenes: numScenes,
          instructions: instructions.trim(),
          hook_enabled: hookEnabled,
          custom_hook: customHook.trim() || undefined,
          hook_style_config: hookStyle,
          subtitles_enabled: subtitlesEnabled,
          subtitle_style_config: { ...subtitleStyle, engine: subtitleStyle.engine || "remotion" },
          include_bgm: includeBgm,
          bgm_volume: bgmVolume,
          aspect_ratio: aspectRatio,
          transition: transitionStyle,
          watermark_config: watermarkEnabled && watermarkText.trim() ? {
            text: watermarkText.trim(),
            position: watermarkPosition,
            opacity: watermarkOpacity,
          } : undefined,
          cta_config: ctaEnabled && ctaHeadline.trim() ? {
            headline: ctaHeadline.trim(),
            button_text: ctaButtonText.trim(),
          } : undefined,
          ai_text_config: {
            enabled: aiTextEnabled,
          },
          source_video_url: isAgenticVideoMode && sourceVideoUrl.trim() ? sourceVideoUrl.trim() : undefined,
          agentic_understanding: agenticUnderstanding,
          video_processing_mode: isAgenticVideoMode ? videoProcessingMode : "agentic",
          media_resolution: isAgenticVideoMode ? mediaResolution : "low",
          fps: isAgenticVideoMode && videoProcessingMode === "static" ? staticFps : undefined,
          start_offset: isAgenticVideoMode && videoProcessingMode === "static" ? parseMmSsToSeconds(startOffsetStr) : undefined,
          end_offset: isAgenticVideoMode && videoProcessingMode === "static" ? parseMmSsToSeconds(endOffsetStr) : undefined,
        }),
      });
      setPage(1);
      void loadJobs(1);
      setStudioJob(job);
      toast.success("AI script & candidate footage search started. Reviewing studio...");
    } catch (error) {
      toast.error(errorMessage(error, "Failed to plan video."));
    } finally {
      setIsPlanning(false);
    }
  };

  // Launch render from studio with selected footage
  const handleStartRenderWithSelected = async (jobId: string, updatedScenes: SceneItem[]) => {
    await fetchApi<VideoJob>("/api/video-generator/render-selected", {
      method: "POST",
      body: JSON.stringify({
        job_id: jobId,
        selected_scenes: updatedScenes,
        hook_enabled: hookEnabled,
        custom_hook: customHook.trim() || undefined,
        hook_style_config: hookStyle,
        subtitles_enabled: subtitlesEnabled,
        subtitle_style_config: { ...subtitleStyle, engine: subtitleStyle.engine || "remotion" },
        include_bgm: includeBgm,
        bgm_volume: bgmVolume,
        aspect_ratio: aspectRatio,
        transition: transitionStyle,
        watermark_config: watermarkEnabled && watermarkText.trim() ? {
          text: watermarkText.trim(),
          position: watermarkPosition,
          opacity: watermarkOpacity,
        } : undefined,
        cta_config: ctaEnabled && ctaHeadline.trim() ? {
          headline: ctaHeadline.trim(),
          button_text: ctaButtonText.trim(),
        } : undefined,
        ai_text_config: {
          enabled: aiTextEnabled,
        },
      }),
    });
    setPage(1);
    void loadJobs(1);
    toast.success("Video rendering initiated with your selected footage!");
  };

  const handleDownload = async (jobId: string) => {
    const token = getToken();
    try {
      const response = await fetch(`${API_BASE}/api/video-generator/jobs/${jobId}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Download failed" }));
        throw new Error(error.detail || "Download failed");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `video_${jobId}.mp4`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(errorMessage(error, "Failed to download video."));
    }
  };

  const handleRetryJob = async (jobId: string) => {
    if (isRetrying) return;
    setIsRetrying(jobId);
    try {
      await fetchApi<VideoJob>(`/api/video-generator/jobs/${jobId}/retry`, {
        method: "POST",
      });
      toast.success("Retrying video generation.");
      void loadJobs();
    } catch (error) {
      toast.error(errorMessage(error, "Failed to retry job."));
    } finally {
      setIsRetrying(null);
    }
  };

  const handleDeleteJob = async (jobId: string) => {
    if (
      !(await confirmDialog({
        title: "Delete video generator job?",
        message: "This will permanently delete this job record, downloaded footage clips, and the generated final video.\n\nThis action cannot be undone.",
        confirmText: "Yes, Delete Job",
        danger: true,
      }))
    )
      return;

    try {
      await fetchApi(`/api/video-generator/jobs/${jobId}`, {
        method: "DELETE",
      });
      setJobs((prev) => prev.filter((j) => j.job_id !== jobId));
      setTotalJobs((prev) => Math.max(0, prev - 1));
      if (activeJob?.job_id === jobId) setActiveJob(null);
      if (studioJob?.job_id === jobId) setStudioJob(null);
      toast.success("Job deleted successfully.");
    } catch (error) {
      toast.error(errorMessage(error, "Failed to delete job."));
    }
  };

  const openEditorFor = (tab: "presets" | "hook" | "subtitle") => {
    setActiveStyleTab(tab);
    setShowStyleEditor(true);
  };



  if (!user) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <Card className="max-w-sm p-8 text-center">
          <AlertCircle className="mx-auto mb-3 h-10 w-10 text-amber-400" />
          <p className="text-sm font-medium text-zinc-200">Silakan login terlebih dahulu</p>
          <p className="mt-1 text-xs leading-5 text-zinc-500">
            Anda perlu login untuk membuat dan mengelola video AI.
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-2 sm:p-4 lg:p-6 space-y-4 sm:space-y-6">
      <div className="mx-auto max-w-7xl space-y-4 sm:space-y-6 pb-6">
        {/* Banner Header */}
        <section className="relative overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/60 p-4 sm:p-6 backdrop-blur-xs">
          <div className="relative flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 sm:h-11 sm:w-11 shrink-0 items-center justify-center rounded-xl bg-violet-500/10 text-violet-400 border border-violet-500/20 shadow-xs">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-violet-400">AI Video Production Studio</p>
                <h1 className="mt-1 text-lg sm:text-xl font-semibold tracking-tight text-zinc-100">Video Generator</h1>
                <p className="mt-1 max-w-2xl text-xs sm:text-sm leading-5 sm:leading-6 text-zinc-400">
                  Generate full vertical 9:16 short-form videos with customizable opening hooks, karaoke captions (1-6 words), multi-source footage selection, and voice synthesis.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 self-start rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-xs text-zinc-300 sm:self-auto">
              <Film className="h-3.5 w-3.5 text-violet-400" /> 9:16 · 1080 × 1920 · Multi-Engine Hook & Subtitles
            </div>
          </div>
        </section>

        {/* Creation Form Studio */}
        <form onSubmit={handleQuickSubmit}>
          <Card className="p-3.5 sm:p-6 space-y-4 sm:space-y-6">
            {/* Form Top Bar: Title & Preset Selector */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-800/80 pb-4">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-violet-400" />
                <h2 className="text-sm font-semibold text-zinc-100">Video Studio & Configuration</h2>
              </div>

              {/* Preset Selector */}
              <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
                <Bookmark className="h-3.5 w-3.5 text-zinc-400" />
                <span className="text-xs text-zinc-400 font-medium">Style Preset:</span>
                <select
                  value={selectedPresetId}
                  onChange={(e) => handleSelectPreset(e.target.value)}
                  className="rounded-lg border border-zinc-800 bg-zinc-900/80 px-2.5 py-1.5 text-xs text-zinc-200 outline-none transition focus:border-violet-500/60 flex-1 sm:flex-initial"
                >
                  <option value="">Custom Styles</option>
                  {userPresets.map((p) => (
                    <option key={p.id} value={String(p.id)}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <Button
                  type="button"
                  size="xs"
                  variant="outline"
                  onClick={() => openEditorFor("presets")}
                  icon={<Palette className="h-3 w-3 text-violet-400" />}
                >
                  Presets
                </Button>
              </div>
            </div>

            {/* Studio Layout: Left Controls vs Right Visual Suite */}
            <div className="grid gap-4 sm:gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(340px,1fr)]">
              {/* Left Column: Narrative, Audio, Format & Spec */}
              <div className="space-y-4">
                {/* 0. Input Mode & Agentic Pipeline Selector */}
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-3.5 sm:p-4 space-y-3">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="flex items-center gap-2">
                      <Sparkles className="h-4 w-4 text-violet-400" />
                      <span className="text-xs font-semibold uppercase tracking-wider text-zinc-200">
                        Input Mode & AI Pipeline
                      </span>
                    </div>
                    <div className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-950 p-0.5 text-xs">
                      <button
                        type="button"
                        onClick={() => setIsAgenticVideoMode(false)}
                        className={cn(
                          "px-2.5 py-1 rounded-md text-[11px] font-medium transition",
                          !isAgenticVideoMode
                            ? "bg-violet-600 text-white shadow-xs"
                            : "text-zinc-400 hover:text-zinc-200"
                        )}
                      >
                        Topic Prompt
                      </button>
                      <button
                        type="button"
                        onClick={() => setIsAgenticVideoMode(true)}
                        className={cn(
                          "px-2.5 py-1 rounded-md text-[11px] font-medium transition flex items-center gap-1.5",
                          isAgenticVideoMode
                            ? "bg-violet-600 text-white shadow-xs"
                            : "text-zinc-400 hover:text-zinc-200"
                        )}
                      >
                        <Video className="h-3 w-3 text-violet-300" />
                        Video Understanding
                      </button>
                    </div>
                  </div>

                  {/* Agentic Video Understanding Explainer & Input */}
                  {isAgenticVideoMode && (
                    <div className="space-y-3.5 pt-1">
                      {/* Explainer Banner */}
                      <div className="rounded-lg border border-violet-500/30 bg-violet-950/20 p-3 space-y-1.5">
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <span className="text-[11px] font-semibold text-violet-300 flex items-center gap-1.5">
                            <Sparkles className="h-3.5 w-3.5 text-violet-400" />
                            Gemini 3.8 Flash Video Understanding
                          </span>
                          <span className="text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full font-medium">
                            Up to 88% Fewer Tokens
                          </span>
                        </div>
                        <p className="text-[11px] text-zinc-400 leading-relaxed">
                          Gemini mengeksplorasi timeline video secara dinamis menggunakan multimodal audio & visual reasoning untuk menyelaraskan narasi dengan segmen footage paling viral dan relevan.
                        </p>
                      </div>

                      {/* 1. Input Method Tabs */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <label className="text-[11px] font-medium text-zinc-300">
                            Metode Input Video:
                          </label>
                          <span className="text-[10px] text-zinc-500">File API, Inline Data, atau YouTube</span>
                        </div>
                        <div className="grid grid-cols-3 gap-1.5 rounded-lg border border-zinc-800 bg-zinc-950 p-1">
                          <button
                            type="button"
                            onClick={() => setVideoInputMethod("youtube")}
                            className={cn(
                              "flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-[11px] font-medium transition",
                              videoInputMethod === "youtube"
                                ? "bg-violet-600 text-white shadow-xs"
                                : "text-zinc-400 hover:text-zinc-200"
                            )}
                          >
                            <Video className="h-3.5 w-3.5" />
                            YouTube URL
                          </button>
                          <button
                            type="button"
                            onClick={() => setVideoInputMethod("upload")}
                            className={cn(
                              "flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-[11px] font-medium transition",
                              videoInputMethod === "upload"
                                ? "bg-violet-600 text-white shadow-xs"
                                : "text-zinc-400 hover:text-zinc-200"
                            )}
                          >
                            <Upload className="h-3.5 w-3.5" />
                            Upload File
                          </button>
                          <button
                            type="button"
                            onClick={() => setVideoInputMethod("cloud")}
                            className={cn(
                              "flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-[11px] font-medium transition",
                              videoInputMethod === "cloud"
                                ? "bg-violet-600 text-white shadow-xs"
                                : "text-zinc-400 hover:text-zinc-200"
                            )}
                          >
                            <Cloud className="h-3.5 w-3.5" />
                            Cloud Storage
                          </button>
                        </div>

                        {/* YouTube URL input */}
                        {videoInputMethod === "youtube" && (
                          <div className="relative">
                            <input
                              id="source-video-url"
                              type="url"
                              value={sourceVideoUrl}
                              onChange={(e) => setSourceVideoUrl(e.target.value)}
                              placeholder="https://www.youtube.com/watch?v=... (Preview Mode)"
                              className="w-full rounded-lg border border-zinc-800 bg-zinc-900/80 px-3.5 py-2 pl-9 text-xs text-zinc-100 placeholder:text-zinc-600 outline-none transition focus:border-violet-500/60"
                            />
                            <Video className="h-4 w-4 text-zinc-500 absolute left-3 top-2.5" />
                          </div>
                        )}

                        {/* Direct File Upload input */}
                        {videoInputMethod === "upload" && (
                          <div className="space-y-2">
                            <input
                              ref={fileInputRef}
                              type="file"
                              accept=".mp4,.mov,.webm,.avi,.mkv"
                              className="hidden"
                              onChange={(e) => {
                                const f = e.target.files?.[0];
                                if (f) void handleUploadSourceVideo(f);
                              }}
                            />
                            {uploadedVideoFile ? (
                              <div className="flex items-center justify-between rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-2.5 text-xs">
                                <div className="flex items-center gap-2 min-w-0">
                                  <FileVideo className="h-4 w-4 text-emerald-400 shrink-0" />
                                  <div className="min-w-0">
                                    <p className="font-medium text-emerald-200 truncate">{uploadedVideoFile.filename}</p>
                                    <div className="flex items-center gap-2 text-[10px] text-zinc-400">
                                      <span>{(uploadedVideoFile.size_bytes / 1024 / 1024).toFixed(1)} MB</span>
                                      {uploadedVideoFile.duration_mm_ss && <span>• {uploadedVideoFile.duration_mm_ss}</span>}
                                      <span className={cn(
                                        "px-1.5 py-0.2 rounded border font-mono",
                                        uploadedVideoFile.is_inline_eligible
                                          ? "bg-violet-500/20 text-violet-300 border-violet-500/30"
                                          : "bg-blue-500/20 text-blue-300 border-blue-500/30"
                                      )}>
                                        {uploadedVideoFile.is_inline_eligible ? "Inline Data (<20MB)" : "Google Files API"}
                                      </span>
                                    </div>
                                  </div>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => fileInputRef.current?.click()}
                                  className="text-[11px] text-zinc-400 hover:text-white px-2 py-1 rounded bg-zinc-800 transition shrink-0"
                                >
                                  Ganti Video
                                </button>
                              </div>
                            ) : (
                              <div
                                onClick={() => fileInputRef.current?.click()}
                                onDragOver={(e) => e.preventDefault()}
                                onDrop={(e) => {
                                  e.preventDefault();
                                  const f = e.dataTransfer.files?.[0];
                                  if (f) void handleUploadSourceVideo(f);
                                }}
                                className="border border-dashed border-zinc-700 hover:border-violet-500/60 bg-zinc-950/40 rounded-lg p-4 text-center cursor-pointer transition group"
                              >
                                {isUploadingSourceVideo ? (
                                  <div className="flex flex-col items-center justify-center space-y-2 py-1">
                                    <Loader2 className="h-5 w-5 animate-spin text-violet-400" />
                                    <span className="text-xs text-zinc-300">Mengunggah file & memeriksa durasi video...</span>
                                  </div>
                                ) : (
                                  <div className="flex flex-col items-center justify-center space-y-1.5 py-1">
                                    <Upload className="h-5 w-5 text-zinc-500 group-hover:text-violet-400 transition" />
                                    <p className="text-xs text-zinc-300 font-medium">
                                      Klik atau drag & drop file video di sini
                                    </p>
                                    <p className="text-[10px] text-zinc-500">
                                      MP4, MOV, WEBM (File &lt;20MB otomatis menggunakan Inline Data, &ge;20MB via Google Files API)
                                    </p>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        )}

                        {/* Cloud Storage input */}
                        {videoInputMethod === "cloud" && (
                          <div className="relative">
                            <input
                              type="text"
                              value={sourceVideoUrl}
                              onChange={(e) => setSourceVideoUrl(e.target.value)}
                              placeholder="gs://cloud-samples-data/generative-ai/video/... (GCS URI)"
                              className="w-full rounded-lg border border-zinc-800 bg-zinc-900/80 px-3.5 py-2 pl-9 text-xs text-zinc-100 placeholder:text-zinc-600 outline-none transition focus:border-violet-500/60"
                            />
                            <Cloud className="h-4 w-4 text-zinc-500 absolute left-3 top-2.5" />
                          </div>
                        )}
                      </div>

                      {/* 2. Processing Mode Selector (Agentic vs Static) */}
                      <div className="space-y-1.5 pt-1 border-t border-zinc-800/60">
                        <label className="text-[11px] font-medium text-zinc-300 block">
                          Mode Pemrosesan Gemini:
                        </label>
                        <div className="grid grid-cols-2 gap-2">
                          <div
                            onClick={() => {
                              setVideoProcessingMode("agentic");
                              setAgenticUnderstanding(true);
                            }}
                            className={cn(
                              "rounded-lg border p-2.5 cursor-pointer transition text-left space-y-1",
                              videoProcessingMode === "agentic"
                                ? "border-violet-500 bg-violet-500/10 ring-1 ring-violet-500"
                                : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700"
                            )}
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-semibold text-violet-200 flex items-center gap-1">
                                <Sparkles className="h-3 w-3 text-violet-400" />
                                Agentic Mode
                              </span>
                              <span className="text-[9px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.2 rounded font-mono">
                                Disarankan
                              </span>
                            </div>
                            <p className="text-[10px] text-zinc-400 leading-tight">
                              Eksplorasi timeline dinamis, hemat hingga 88% token, sinkronisasi narasi otomatis.
                            </p>
                          </div>

                          <div
                            onClick={() => {
                              setVideoProcessingMode("static");
                              setAgenticUnderstanding(false);
                            }}
                            className={cn(
                              "rounded-lg border p-2.5 cursor-pointer transition text-left space-y-1",
                              videoProcessingMode === "static"
                                ? "border-violet-500 bg-violet-500/10 ring-1 ring-violet-500"
                                : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700"
                            )}
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-semibold text-zinc-200 flex items-center gap-1">
                                <SlidersHorizontal className="h-3 w-3 text-zinc-400" />
                                Static Mode
                              </span>
                              <span className="text-[9px] bg-zinc-800 text-zinc-400 px-1.5 py-0.2 rounded font-mono">
                                Custom FPS
                              </span>
                            </div>
                            <p className="text-[10px] text-zinc-400 leading-tight">
                              Sampling frame tetap (1 FPS / kustom) dan opsi clipping interval MM:SS.
                            </p>
                          </div>
                        </div>

                        {/* Static Sub-Controls */}
                        {videoProcessingMode === "static" && (
                          <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-2.5 space-y-2.5 mt-2">
                            <div className="flex items-center justify-between text-xs">
                              <span className="text-[11px] text-zinc-400">Sampling Frame Rate (FPS):</span>
                              <div className="flex items-center gap-1">
                                {[0.5, 1.0, 2.0].map((f) => (
                                  <button
                                    key={f}
                                    type="button"
                                    onClick={() => setStaticFps(f)}
                                    className={cn(
                                      "px-2 py-0.5 rounded text-[10px] font-medium border transition",
                                      staticFps === f
                                        ? "bg-violet-600 text-white border-violet-500"
                                        : "bg-zinc-900 text-zinc-400 border-zinc-800 hover:text-white"
                                    )}
                                  >
                                    {f} FPS
                                  </button>
                                ))}
                              </div>
                            </div>

                            <div className="grid grid-cols-2 gap-2 text-xs">
                              <div>
                                <label className="block text-[10px] text-zinc-400 mb-0.5">Start Offset (MM:SS):</label>
                                <input
                                  type="text"
                                  placeholder="00:00"
                                  value={startOffsetStr}
                                  onChange={(e) => setStartOffsetStr(e.target.value)}
                                  className="w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 outline-none focus:border-zinc-700"
                                />
                              </div>
                              <div>
                                <label className="block text-[10px] text-zinc-400 mb-0.5">End Offset (MM:SS):</label>
                                <input
                                  type="text"
                                  placeholder="01:30"
                                  value={endOffsetStr}
                                  onChange={(e) => setEndOffsetStr(e.target.value)}
                                  className="w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 outline-none focus:border-zinc-700"
                                />
                              </div>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* 3. Media Resolution Selector */}
                      <div className="flex items-center justify-between pt-1 border-t border-zinc-800/60 text-xs">
                        <div className="space-y-0.5">
                          <span className="text-[11px] font-medium text-zinc-300 block">Media Resolution:</span>
                          <span className="text-[10px] text-zinc-500">
                            {mediaResolution === "low" ? "Low (~66 token/frame, cepat & hemat)" : "High (~258 token/frame, detail tajam)"}
                          </span>
                        </div>
                        <div className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-950 p-0.5">
                          <button
                            type="button"
                            onClick={() => setMediaResolution("low")}
                            className={cn(
                              "px-2.5 py-1 rounded text-[10px] font-medium transition",
                              mediaResolution === "low"
                                ? "bg-violet-600 text-white shadow-xs"
                                : "text-zinc-400 hover:text-zinc-200"
                            )}
                          >
                            Low (Disarankan)
                          </button>
                          <button
                            type="button"
                            onClick={() => setMediaResolution("high")}
                            className={cn(
                              "px-2.5 py-1 rounded text-[10px] font-medium transition",
                              mediaResolution === "high"
                                ? "bg-violet-600 text-white shadow-xs"
                                : "text-zinc-400 hover:text-zinc-200"
                            )}
                          >
                            High Detail
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* 1. Topic & Narrative Card */}
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <label htmlFor="video-topic" className="text-xs font-semibold uppercase tracking-wider text-zinc-300">
                      {isAgenticVideoMode ? "Focus Topic & Subject (Optional)" : "Video Topic & Subject"}
                    </label>
                    <span className="text-[11px] tabular-nums text-zinc-500 font-mono">{topic.length}/500</span>
                  </div>

                  <textarea
                    id="video-topic"
                    value={topic}
                    onChange={(event) => setTopic(event.target.value)}
                    placeholder="Example: How deep-sea creatures survive extreme ocean pressure"
                    maxLength={500}
                    rows={3}
                    className="w-full resize-none rounded-lg border border-zinc-800 bg-zinc-900/60 px-3.5 py-2.5 text-sm leading-6 text-zinc-100 placeholder:text-zinc-600 outline-none transition focus:border-violet-500/60"
                  />

                  {/* Dynamic Trending Topics (Hermes Multi-Source Engine) */}
                  <div className="rounded-lg border border-amber-500/20 bg-amber-950/15 p-3 space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5">
                        <Flame className="h-4 w-4 text-amber-400 fill-amber-400" />
                        <span className="text-xs font-semibold text-amber-200">
                          Topik Trending Hari Ini (Real-Time)
                        </span>
                        <span className="text-[10px] text-amber-400/80 bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.2 rounded font-mono">
                          {trendingTopics.length} Topik
                        </span>
                      </div>

                      <div className="flex items-center gap-1.5">
                        {/* Region Selector */}
                        <div className="flex items-center gap-1 bg-zinc-900/90 border border-zinc-800 rounded-md px-2 py-0.5 text-[11px]">
                          <Globe className="h-3 w-3 text-zinc-400" />
                          <select
                            value={trendingRegion}
                            onChange={(e) => {
                              const newReg = e.target.value;
                              setTrendingRegion(newReg);
                              void loadTrendingTopics(newReg);
                            }}
                            className="bg-transparent text-zinc-200 outline-none cursor-pointer text-xs"
                          >
                            <option value="ID" className="bg-zinc-900">Indonesia (ID)</option>
                            <option value="GLOBAL" className="bg-zinc-900">Worldwide (Global)</option>
                            <option value="US" className="bg-zinc-900">United States (US)</option>
                            <option value="MY" className="bg-zinc-900">Malaysia (MY)</option>
                            <option value="SG" className="bg-zinc-900">Singapore (SG)</option>
                            <option value="GB" className="bg-zinc-900">United Kingdom (GB)</option>
                            <option value="JP" className="bg-zinc-900">Japan (JP)</option>
                          </select>
                        </div>

                        {/* Refresh Button */}
                        <button
                          type="button"
                          onClick={() => loadTrendingTopics(trendingRegion, true)}
                          disabled={isLoadingTrending}
                          className="flex items-center justify-center h-6 w-6 rounded-md border border-zinc-800 bg-zinc-900/80 text-zinc-400 hover:text-zinc-100 hover:border-zinc-700 transition"
                          title="Refresh topik trending dari YouTube Data API, Google Trends & TikTok"
                        >
                          <RefreshCw className={cn("h-3 w-3", isLoadingTrending && "animate-spin text-amber-400")} />
                        </button>

                        {/* Modal opener button */}
                        <button
                          type="button"
                          onClick={() => setShowTrendingModal(true)}
                          className="flex items-center gap-1 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-300 hover:bg-amber-500/20 transition"
                        >
                          <TrendingUp className="h-3 w-3" />
                          <span>Detail Analisis</span>
                        </button>
                      </div>
                    </div>

                    {/* Trending Pills */}
                    {isLoadingTrending ? (
                      <div className="flex items-center gap-2 py-1 text-xs text-zinc-500">
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-400" />
                        <span>Menganalisis YouTube Data API, Google Trends & TikTok...</span>
                      </div>
                    ) : trendingTopics.length > 0 ? (
                      <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                        {trendingTopics.map((t, idx) => (
                          <button
                            key={idx}
                            type="button"
                            onClick={() => handleSelectTrendingTopic(t)}
                            className="group flex items-center gap-1.5 rounded-md border border-zinc-800/80 bg-zinc-900/80 px-2.5 py-1 text-[11px] text-zinc-300 hover:border-amber-500/50 hover:bg-zinc-800/90 hover:text-white transition truncate max-w-[280px]"
                            title={`${t.topic} — ${t.angle}`}
                          >
                            <span className="flex h-4 w-4 items-center justify-center rounded-full bg-amber-500/20 text-[9px] font-bold text-amber-300">
                              {idx + 1}
                            </span>
                            <span className="truncate">{t.topic}</span>
                            {t.source && (
                              <span className="text-[9px] text-zinc-500 font-mono">
                                ({t.source.split(" ")[0]})
                              </span>
                            )}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="flex items-center justify-between text-xs text-zinc-500 py-0.5">
                        <span>Belum ada data trending terkini.</span>
                        <button
                          type="button"
                          onClick={() => loadTrendingTopics(trendingRegion, true)}
                          className="text-amber-400 underline hover:text-amber-300"
                        >
                          Muat Sekarang
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Directorial Tone Chips */}
                  <div className="flex flex-wrap items-center gap-1.5 pt-1.5 border-t border-zinc-800/60">
                    <span className="text-[10px] uppercase tracking-wider text-zinc-500 mr-0.5">Tone:</span>
                    {CREATIVE_TONES.map((t) => (
                      <button
                        key={t.label}
                        type="button"
                        onClick={() => setInstructions((prev) => (prev ? `${prev}. ${t.prompt}` : t.prompt))}
                        className="rounded-md border border-zinc-800 bg-zinc-900/70 px-2 py-0.5 text-[10px] text-zinc-400 hover:border-zinc-700 hover:text-zinc-200 transition"
                      >
                        {t.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* 2. Audio & Narration Card */}
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 space-y-3.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Volume2 className="h-4 w-4 text-violet-400" />
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-200">
                        Audio & Narration
                      </h3>
                    </div>
                    <span className="text-[11px] text-zinc-400 font-medium">
                      {ttsProvider === "gemini" ? "Google Gemini Flash TTS" : "Deepgram Aura TTS"}
                    </span>
                  </div>

                  {/* TTS Provider Selector Toggle */}
                  <div className="space-y-1.5">
                    <label className="block text-[11px] font-medium text-zinc-400">
                      TTS Engine Provider
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setTtsProvider("gemini");
                          setVoice("Kore");
                        }}
                        className={`flex items-center justify-between rounded-lg border p-2.5 text-left transition ${
                          ttsProvider === "gemini"
                            ? "border-violet-500/60 bg-violet-500/10 text-zinc-100 shadow-xs"
                            : "border-zinc-800 bg-zinc-900/50 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                        }`}
                      >
                        <div>
                          <div className="text-xs font-semibold text-zinc-100">Google Gemini</div>
                          <div className="text-[10px] text-zinc-400">Flash TTS · Native ID & EN</div>
                        </div>
                        <span className="rounded bg-violet-500/20 px-1.5 py-0.5 text-[9px] font-bold text-violet-300">
                          Recommended
                        </span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setTtsProvider("deepgram");
                          setVoice("");
                          setCustomVoiceId("");
                        }}
                        className={`flex items-center justify-between rounded-lg border p-2.5 text-left transition ${
                          ttsProvider === "deepgram"
                            ? "border-violet-500/60 bg-violet-500/10 text-zinc-100 shadow-xs"
                            : "border-zinc-800 bg-zinc-900/50 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                        }`}
                      >
                        <div>
                          <div className="text-xs font-semibold text-zinc-100">Deepgram</div>
                          <div className="text-[10px] text-zinc-400">Aura · Ultra Fast</div>
                        </div>
                        <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[9px] font-medium text-zinc-400">
                          Optional
                        </span>
                      </button>
                    </div>
                  </div>

                  {/* Gemini TTS Model, Region/Style Filter, and Voice Controls */}
                  {ttsProvider === "gemini" ? (
                    <div className="space-y-3">
                      <div className="grid gap-3 sm:grid-cols-2">
                        {/* Gemini Models */}
                        <div>
                          <label htmlFor="video-tts-model" className="mb-1.5 block text-xs font-medium text-zinc-300">
                            Model Gemini TTS
                          </label>
                          <select
                            id="video-tts-model"
                            value={ttsModel}
                            onChange={(e) => setTtsModel(e.target.value)}
                            className="w-full rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-sm text-zinc-100 outline-none transition focus:border-violet-500/60"
                          >
                            {ttsModels.map((m) => (
                              <option key={m.model_id} value={m.model_id}>
                                {m.name || m.model_id} {m.free_tier ? "· [Free Tier]" : "· [Pro]"}
                              </option>
                            ))}
                          </select>
                        </div>

                        {/* Country / Region Filter */}
                        <div>
                          <label htmlFor="video-country-filter" className="mb-1.5 flex items-center gap-1 text-xs font-medium text-zinc-300">
                            <Globe className="h-3.5 w-3.5 text-violet-400" />
                            Filter Bahasa &amp; Gaya Daerah
                          </label>
                          <select
                            id="video-country-filter"
                            value={selectedCountry}
                            onChange={(e) => setSelectedCountry(e.target.value)}
                            className="w-full rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-sm text-zinc-100 outline-none transition focus:border-violet-500/60"
                          >
                            {availableCountries.map((c) => (
                              <option key={c} value={c}>
                                {c === "All" ? "Semua Bahasa & Gaya" : c === "Indonesia" ? "Bahasa Indonesia (Semua Gaya Daerah)" : c}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>

                      {/* Gemini Voice List & Details */}
                      <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/50 p-3 space-y-2.5">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                          <div className="flex-1">
                            <label htmlFor="video-voice" className="mb-1 block text-xs font-medium text-zinc-300">
                              Karakter Suara &amp; Gaya Bicara ({filteredVoices.length} Variasi)
                            </label>
                            <select
                              id="video-voice"
                              value={customVoiceId ? "custom" : voice}
                              onChange={(e) => {
                                if (e.target.value === "custom") {
                                  setVoice("");
                                } else {
                                  setCustomVoiceId("");
                                  setVoice(e.target.value);
                                }
                              }}
                              className="w-full rounded-lg border border-zinc-800 bg-zinc-900/90 px-3 py-2 text-sm text-zinc-100 outline-none transition focus:border-violet-500/60"
                            >
                              <option value="Kore">Kore · Default Native Voice</option>
                              {filteredVoices.map((option) => (
                                <option key={option.model || option.key} value={option.model}>
                                  {option.key} {option.gender ? `(${option.gender})` : ""}
                                </option>
                              ))}
                              <option value="custom">Gunakan Prebuilt Voice Name custom...</option>
                            </select>
                          </div>

                          {/* Audio Preview Button */}
                          <div className="sm:pt-5">
                            {activeVoiceOption?.preview_url ? (
                              <button
                                type="button"
                                onClick={() => handleTogglePlayVoice(activeVoiceOption)}
                                className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition border ${
                                  playingVoiceId === activeVoiceOption.model
                                    ? "border-violet-400 bg-violet-600 text-white shadow-xs animate-pulse"
                                    : "border-zinc-800 bg-zinc-900 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100"
                                }`}
                                title="Dengar contoh audio suara ini"
                              >
                                {playingVoiceId === activeVoiceOption.model ? (
                                  <>
                                    <Pause className="h-3.5 w-3.5 fill-current" />
                                    <span>Berhenti</span>
                                  </>
                                ) : (
                                  <>
                                    <Play className="h-3.5 w-3.5 fill-current" />
                                    <span>Dengar Suara</span>
                                  </>
                                )}
                              </button>
                            ) : null}
                          </div>
                        </div>

                        {/* Custom Voice ID write-in if desired */}
                        {customVoiceId !== "" && (
                          <div className="pt-1">
                            <input
                              type="text"
                              value={customVoiceId}
                              onChange={(e) => setCustomVoiceId(e.target.value)}
                              placeholder="Ketik nama voice Gemini (contoh: Kore, Puck, Fenrir, Aoede, Charon, Leda, Zephyr, Orus)"
                              className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 placeholder:text-zinc-600 outline-none transition focus:border-violet-500/60 font-mono"
                            />
                          </div>
                        )}
                      </div>

                      {/* Pacing & Info */}
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div>
                          <label htmlFor="video-speed" className="mb-1.5 block text-xs font-medium text-zinc-300">
                            Pacing / Kecepatan Bicara
                          </label>
                          <select
                            id="video-speed"
                            value={speed}
                            onChange={(event) => setSpeed(Number(event.target.value))}
                            className="w-full rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-sm text-zinc-100 outline-none transition focus:border-violet-500/60"
                          >
                            <option value={0.85}>Calm · 0.85×</option>
                            <option value={1}>Natural · 1.0×</option>
                            <option value={1.15}>Energetic · 1.15×</option>
                            <option value={1.3}>Fast · 1.3×</option>
                          </select>
                        </div>
                        <div className="flex items-center text-[11px] text-zinc-400 pt-5">
                          Google Gemini TTS Audio API terhubung dari Settings &gt; Database &amp; Env Config.
                        </div>
                      </div>
                    </div>
                  ) : (
                    /* Deepgram Voice Controls */
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <label htmlFor="video-voice" className="mb-1.5 block text-xs font-medium text-zinc-300">
                          Deepgram Aura Voice
                        </label>
                        <div className="flex items-center gap-2">
                          <select
                            id="video-voice"
                            value={voice}
                            onChange={(event) => setVoice(event.target.value)}
                            className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-sm text-zinc-100 outline-none transition focus:border-violet-500/60"
                          >
                            <option value="">Default (Thalia)</option>
                            {voices
                              .filter((v) => v.provider === "deepgram")
                              .map((option) => (
                                <option key={option.key} value={option.model}>
                                  {option.key.toUpperCase()} · {option.model}
                                </option>
                              ))}
                          </select>
                          {activeVoiceOption?.preview_url ? (
                            <button
                              type="button"
                              onClick={() => handleTogglePlayVoice(activeVoiceOption)}
                              className={`flex items-center justify-center rounded-lg px-3 py-2 text-xs font-medium transition border ${
                                playingVoiceId === activeVoiceOption.model
                                  ? "border-violet-400 bg-violet-600 text-white shadow-xs animate-pulse"
                                  : "border-zinc-800 bg-zinc-900 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100"
                              }`}
                              title="Dengar contoh audio suara Deepgram ini"
                            >
                              {playingVoiceId === activeVoiceOption.model ? (
                                <Pause className="h-3.5 w-3.5 fill-current" />
                              ) : (
                                <Play className="h-3.5 w-3.5 fill-current" />
                              )}
                            </button>
                          ) : null}
                        </div>
                      </div>

                      {/* Pacing */}
                      <div>
                        <label htmlFor="video-speed" className="mb-1.5 block text-xs font-medium text-zinc-300">
                          Pacing
                        </label>
                        <select
                          id="video-speed"
                          value={speed}
                          onChange={(event) => setSpeed(Number(event.target.value))}
                          className="w-full rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-sm text-zinc-100 outline-none transition focus:border-violet-500/60"
                        >
                          <option value={0.85}>Calm · 0.85×</option>
                          <option value={1}>Natural · 1.0×</option>
                          <option value={1.15}>Energetic · 1.15×</option>
                          <option value={1.3}>Fast · 1.3×</option>
                        </select>
                      </div>
                    </div>
                  )}

                  {/* Background Music Row */}
                  <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-3 space-y-2">
                    <Toggle
                      checked={includeBgm}
                      onChange={setIncludeBgm}
                      label="Background Music"
                      description="A royalty-free track is mixed below the narration."
                    />
                    {includeBgm && (
                      <div className="pt-1">
                        <RangeSlider
                          label="Music Level"
                          value={bgmVolume}
                          min={0.05}
                          max={0.3}
                          step={0.01}
                          onChange={setBgmVolume}
                          suffix=""
                          description="Narration remains dominant."
                        />
                      </div>
                    )}
                  </div>
                </div>

                {/* 3. Format & Scene Pacing Card */}
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 space-y-3.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Film className="h-4 w-4 text-violet-400" />
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-200">
                        Video Format & Visual Elements
                      </h3>
                    </div>
                    <span className="text-[11px] text-zinc-500 font-mono">
                      {aspectRatio === "9:16" ? "9:16 · 1080×1920" : aspectRatio === "16:9" ? "16:9 · 1920×1080" : "1:1 · 1080×1080"}
                    </span>
                  </div>

                  {/* Aspect Ratio Selector (Portrait, Landscape, Square) */}
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-zinc-300">Aspect Ratio</label>
                    <div className="grid grid-cols-3 gap-2">
                      <button
                        type="button"
                        onClick={() => setAspectRatio("9:16")}
                        className={cn(
                          "flex flex-col items-center justify-center gap-1 rounded-lg border py-2 px-2 text-xs font-medium transition",
                          aspectRatio === "9:16"
                            ? "border-violet-500/60 bg-violet-500/15 text-zinc-100 shadow-xs"
                            : "border-zinc-800 bg-zinc-900/50 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                        )}
                      >
                        <span className="font-semibold">9:16 Portrait</span>
                        <span className="text-[10px] text-zinc-500">Shorts / TikTok / Reels</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setAspectRatio("16:9")}
                        className={cn(
                          "flex flex-col items-center justify-center gap-1 rounded-lg border py-2 px-2 text-xs font-medium transition",
                          aspectRatio === "16:9"
                            ? "border-violet-500/60 bg-violet-500/15 text-zinc-100 shadow-xs"
                            : "border-zinc-800 bg-zinc-900/50 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                        )}
                      >
                        <span className="font-semibold">16:9 Landscape</span>
                        <span className="text-[10px] text-zinc-500">YouTube / Web</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setAspectRatio("1:1")}
                        className={cn(
                          "flex flex-col items-center justify-center gap-1 rounded-lg border py-2 px-2 text-xs font-medium transition",
                          aspectRatio === "1:1"
                            ? "border-violet-500/60 bg-violet-500/15 text-zinc-100 shadow-xs"
                            : "border-zinc-800 bg-zinc-900/50 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                        )}
                      >
                        <span className="font-semibold">1:1 Square</span>
                        <span className="text-[10px] text-zinc-500">Instagram Feed</span>
                      </button>
                    </div>
                  </div>

                  {/* Duration Picker */}
                  <div>
                    <div className="mb-1.5 flex items-center justify-between">
                      <label className="text-xs font-medium text-zinc-300">Target duration</label>
                      <span className="text-xs text-violet-400 font-medium">{targetDuration}s</span>
                    </div>
                    <div className="grid grid-cols-4 gap-1.5">
                      {[45, 60, 90, 120].map((d) => (
                        <button
                          key={d}
                          type="button"
                          onClick={() => setTargetDuration(d)}
                          className={cn(
                            "rounded-lg border py-2 text-xs font-medium transition text-center",
                            targetDuration === d
                              ? "border-violet-500/60 bg-violet-500/15 text-zinc-100"
                              : "border-zinc-800 bg-zinc-900/50 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                          )}
                        >
                          {d}s {d === 45 ? "Short" : d === 60 ? "Reel" : d === 90 ? "Story" : "Full"}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Scene Transitions */}
                  <div>
                    <label htmlFor="video-transition" className="mb-1.5 block text-xs font-medium text-zinc-300">
                      Transisi Antar Adegan
                    </label>
                    <select
                      id="video-transition"
                      value={transitionStyle}
                      onChange={(e) => setTransitionStyle(e.target.value)}
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-sm text-zinc-100 outline-none transition focus:border-violet-500/60"
                    >
                      <option value="fade">Fade (Smooth Crossfade)</option>
                      <option value="dissolve">Dissolve (Cinematic Blend)</option>
                      <option value="slideleft">Slide Left (Dynamic Flow)</option>
                      <option value="zoom">Zoom (Punchy Kinetic Cut)</option>
                      <option value="pixelize">Pixelize (Digital Pixel Glitch)</option>
                      <option value="none">None (Clean Hard Cut)</option>
                    </select>
                  </div>

                  {/* AI Text Overlay Toggle */}
                  <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-3">
                    <Toggle
                      checked={aiTextEnabled}
                      onChange={setAiTextEnabled}
                      label="AI Text Overlay & Motion Keywords"
                      description="Menyorot poin penting dari script narasi dengan animasi teks kinetik."
                    />
                  </div>

                  {/* Watermark Branding Card */}
                  <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-3 space-y-2.5">
                    <Toggle
                      checked={watermarkEnabled}
                      onChange={setWatermarkEnabled}
                      label="Watermark & Channel Branding"
                      description="Tambahkan watermark identitas channel/brand pada video."
                    />
                    {watermarkEnabled && (
                      <div className="grid gap-2.5 pt-1 sm:grid-cols-2">
                        <div>
                          <label className="mb-1 block text-[11px] text-zinc-400">Teks Watermark</label>
                          <input
                            type="text"
                            value={watermarkText}
                            onChange={(e) => setWatermarkText(e.target.value)}
                            placeholder="@mychannel"
                            className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-100 placeholder:text-zinc-600 outline-none focus:border-violet-500/60 font-mono"
                          />
                        </div>
                        <div>
                          <label className="mb-1 block text-[11px] text-zinc-400">Posisi Watermark</label>
                          <select
                            value={watermarkPosition}
                            onChange={(e) => setWatermarkPosition(e.target.value)}
                            className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-100 outline-none focus:border-violet-500/60"
                          >
                            <option value="bottom-right">Kanan Bawah (Default)</option>
                            <option value="bottom-left">Kiri Bawah</option>
                            <option value="top-right">Kanan Atas</option>
                            <option value="top-left">Kiri Atas</option>
                          </select>
                        </div>
                        <div className="sm:col-span-2">
                          <RangeSlider
                            label="Opasitas Watermark"
                            value={watermarkOpacity}
                            min={0.1}
                            max={1.0}
                            step={0.05}
                            onChange={setWatermarkOpacity}
                            suffix=""
                            description="Tingkat transparansi teks watermark."
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Call to Action (CTA) Outro Card */}
                  <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-3 space-y-2.5">
                    <Toggle
                      checked={ctaEnabled}
                      onChange={setCtaEnabled}
                      label="Call to Action (CTA) Outro Card"
                      description="Tampilkan kartu penutup ajakan aksi (Follow, Like, Share) di detik akhir."
                    />
                    {ctaEnabled && (
                      <div className="grid gap-2.5 pt-1 sm:grid-cols-2">
                        <div>
                          <label className="mb-1 block text-[11px] text-zinc-400">Teks Headline CTA</label>
                          <input
                            type="text"
                            value={ctaHeadline}
                            onChange={(e) => setCtaHeadline(e.target.value)}
                            placeholder="Follow untuk konten menarik lainnya!"
                            className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-100 placeholder:text-zinc-600 outline-none focus:border-violet-500/60"
                          />
                        </div>
                        <div>
                          <label className="mb-1 block text-[11px] text-zinc-400">Teks Tombol CTA</label>
                          <input
                            type="text"
                            value={ctaButtonText}
                            onChange={(e) => setCtaButtonText(e.target.value)}
                            placeholder="Follow Sekarang"
                            className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-100 placeholder:text-zinc-600 outline-none focus:border-violet-500/60"
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Footage Cuts Dropdown */}
                  <div>
                    <label htmlFor="video-scenes" className="mb-1.5 block text-xs font-medium text-zinc-300">
                      Footage pacing & cuts
                    </label>
                    <select
                      id="video-scenes"
                      value={numScenes}
                      onChange={(event) => setNumScenes(Number(event.target.value))}
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-sm text-zinc-100 outline-none transition focus:border-violet-500/60"
                    >
                      <option value={0}>Auto (AI Dynamic Pacing · 3s–10s Smart Cuts)</option>
                      <option value={8}>8 cuts (Cinematic ~8s shots)</option>
                      <option value={12}>12 cuts (Dynamic ~5s cuts)</option>
                      <option value={15}>15 cuts (Fast viral ~4s cuts)</option>
                      <option value={18}>18 cuts (Ultra rapid ~3.5s)</option>
                      <option value={22}>22 cuts (Max density)</option>
                    </select>
                  </div>

                  {/* Creative Direction */}
                  <div>
                    <div className="mb-1.5 flex items-center justify-between">
                      <label htmlFor="video-instructions" className="text-xs font-medium text-zinc-300">
                        Creative direction <span className="font-normal text-zinc-600">optional</span>
                      </label>
                      <span className="text-[11px] tabular-nums text-zinc-600 font-mono">{instructions.length}/1000</span>
                    </div>
                    <textarea
                      id="video-instructions"
                      value={instructions}
                      onChange={(event) => setInstructions(event.target.value)}
                      placeholder="Example: cinematic documentary mood, focus on mysterious biology, end with a philosophical question."
                      maxLength={1000}
                      rows={2}
                      className="w-full resize-none rounded-lg border border-zinc-800 bg-zinc-900/60 px-3.5 py-2 text-sm leading-6 text-zinc-100 placeholder:text-zinc-600 outline-none transition focus:border-violet-500/60"
                    />
                  </div>
                </div>

                {/* 4. Subtle Specs Bar */}
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-zinc-800 bg-zinc-900/40 px-3.5 py-2.5 text-[11px] text-zinc-400">
                  <span className="font-mono text-zinc-300">
                    {aspectRatio === "9:16" ? "1080×1920 (9:16)" : aspectRatio === "16:9" ? "1920×1080 (16:9)" : "1080×1080 (1:1)"}
                  </span>
                  <span className="text-zinc-700">•</span>
                  <span>
                    {ttsProvider === "gemini" ? "Google Gemini TTS" : "Deepgram Aura"} ({speed}×)
                  </span>
                  <span className="text-zinc-700">•</span>
                  <span className={hookEnabled ? "text-violet-300" : "text-zinc-600"}>
                    {hookEnabled ? "Hook Active" : "No Hook"}
                  </span>
                  <span className="text-zinc-700">•</span>
                  <span className={subtitlesEnabled ? "text-violet-300" : "text-zinc-600"}>
                    {subtitlesEnabled ? `${subtitleStyle.maxWordsPerLine || 3}w Captions` : "No Captions"}
                  </span>
                  <span className="text-zinc-700">•</span>
                  <span className="text-zinc-400 capitalize">
                    Transisi: {transitionStyle}
                  </span>
                  {watermarkEnabled && watermarkText && (
                    <>
                      <span className="text-zinc-700">•</span>
                      <span className="text-violet-300">Watermark: {watermarkText}</span>
                    </>
                  )}
                  {ctaEnabled && (
                    <>
                      <span className="text-zinc-700">•</span>
                      <span className="text-amber-300">CTA Outro</span>
                    </>
                  )}
                </div>
              </div>

              {/* Right Column: Visual Studio (Live Preview + Hook + Subtitles Controls) */}
              <div className="space-y-4 rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
                <div className="flex items-center justify-between border-b border-zinc-800/60 pb-2.5">
                  <div className="flex items-center gap-2">
                    <SlidersHorizontal className="h-4 w-4 text-violet-400" />
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-200">Visual & Audio Studio</h3>
                  </div>
                  <span className="text-[11px] text-zinc-400 font-mono bg-zinc-900/80 border border-zinc-800 px-2 py-0.5 rounded-md">
                    {aspectRatio === "9:16" ? "1080×1920 · 9:16" : aspectRatio === "16:9" ? "1920×1080 · 16:9" : "1080×1080 · 1:1"}
                  </span>
                </div>

                {/* Live Canvas Preview */}
                <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-3 shadow-inner">
                  <LiveVideoPreview
                    hookEnabled={hookEnabled}
                    customHook={customHook}
                    hookStyle={hookStyle}
                    subtitlesEnabled={subtitlesEnabled}
                    subtitleStyle={subtitleStyle}
                    topic={topic}
                    onCustomizeHook={() => openEditorFor("hook")}
                    onCustomizeSubtitle={() => openEditorFor("subtitle")}
                    aspectRatio={aspectRatio}
                    watermarkEnabled={watermarkEnabled}
                    watermarkText={watermarkText}
                    watermarkPosition={watermarkPosition}
                    watermarkOpacity={watermarkOpacity}
                    ctaEnabled={ctaEnabled}
                    ctaHeadline={ctaHeadline}
                    ctaButtonText={ctaButtonText}
                    aiTextEnabled={aiTextEnabled}
                  />
                </div>

                {/* Custom Style Studio Launchpad Card */}
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-3.5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="h-8 w-8 rounded-lg bg-violet-500/10 border border-violet-500/20 flex items-center justify-center text-violet-400 shrink-0">
                        <Palette className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <h4 className="text-xs font-semibold text-zinc-100 uppercase tracking-wider">Custom Style Editor</h4>
                        <p className="text-[11px] text-zinc-400 truncate">19 Hook Animations & 24 Subtitle Styles</p>
                      </div>
                    </div>

                    <Button
                      type="button"
                      size="sm"
                      variant="primary"
                      onClick={() => openEditorFor("presets")}
                      icon={<Palette className="h-3.5 w-3.5" />}
                    >
                      Edit Styles
                    </Button>
                  </div>

                  {/* Summary Badges Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
                    {/* Hook Badge Card */}
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900/80 p-2.5 flex items-center justify-between gap-2 hover:border-zinc-700 transition">
                      <div className="flex items-center gap-2 min-w-0">
                        <Toggle checked={hookEnabled} onChange={setHookEnabled} />
                        <div className="min-w-0 cursor-pointer" onClick={() => openEditorFor("hook")}>
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-violet-400">Hook</span>
                            <span className="h-1.5 w-1.5 rounded-full bg-violet-400 shrink-0" />
                            <span className="text-xs font-medium text-zinc-200 truncate">
                              {(hookStyle.animation || "impact_badge").replace(/^(skia_|hf_)/, "").replace(/_/g, " ").toUpperCase()}
                            </span>
                          </div>
                          <p className="text-[10px] text-zinc-500 truncate">
                            {hookStyle.fontFamily || "Anton"} · {hookStyle.fontSize || 54}px
                          </p>
                        </div>
                      </div>
                      <Button
                        type="button"
                        size="xs"
                        variant="ghost"
                        onClick={() => openEditorFor("hook")}
                        icon={<Sparkles className="h-3 w-3 text-zinc-400" />}
                      >
                        Edit
                      </Button>
                    </div>

                    {/* Subtitle Badge Card */}
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900/80 p-2.5 flex items-center justify-between gap-2 hover:border-zinc-700 transition">
                      <div className="flex items-center gap-2 min-w-0">
                        <Toggle checked={subtitlesEnabled} onChange={setSubtitlesEnabled} />
                        <div className="min-w-0 cursor-pointer" onClick={() => openEditorFor("subtitle")}>
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-violet-400">Captions</span>
                            <span
                              className="h-1.5 w-1.5 rounded-full shrink-0"
                              style={{ backgroundColor: subtitleStyle.highlightColor || "#FACC15" }}
                            />
                            <span className="text-xs font-medium text-zinc-200 truncate">
                              {(subtitleStyle.stylePreset || "classic").replace(/_/g, " ").toUpperCase()}
                            </span>
                          </div>
                          <p className="text-[10px] text-zinc-500 truncate">
                            {subtitleStyle.maxWordsPerLine || 3} words/line · {subtitleStyle.fontFamily || "Montserrat"}
                          </p>
                        </div>
                      </div>
                      <Button
                        type="button"
                        size="xs"
                        variant="ghost"
                        onClick={() => openEditorFor("subtitle")}
                        icon={<Palette className="h-3 w-3 text-zinc-400" />}
                      >
                        Edit
                      </Button>
                    </div>
                  </div>

                  {/* Optional Custom Hook Text */}
                  {hookEnabled && (
                    <div className="pt-1">
                      <label className="text-[11px] font-medium text-zinc-400 mb-1 flex items-center justify-between">
                        <span>
                          Custom Hook Text <span className="text-zinc-600 font-normal">(empty = AI generated)</span>
                        </span>
                        <button
                          type="button"
                          onClick={() => openEditorFor("hook")}
                          className="text-[10px] text-violet-400 hover:underline flex items-center gap-1"
                        >
                          <Sparkles className="h-2.5 w-2.5" /> Customize Animation
                        </button>
                      </label>
                      <input
                        type="text"
                        value={customHook}
                        onChange={(e) => setCustomHook(e.target.value)}
                        placeholder="e.g. WHAT IF EARTH STOPPED SPINNING?"
                        maxLength={100}
                        className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-xs text-zinc-200 placeholder:text-zinc-600 outline-none focus:border-violet-500/60"
                      />
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Action Buttons Bar */}
            <div className="mt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-t border-zinc-800/80 pt-4">
              <p className="text-xs leading-5 text-zinc-400">
                Choose <span className="text-zinc-200 font-medium">Studio Plan</span> to curate footage 1-by-1 in Footage Studio, or <span className="text-zinc-200 font-medium">Generate video</span> for 1-click auto.
              </p>

              <div className="flex flex-wrap items-center gap-2.5">
                <Button
                  type="button"
                  size="md"
                  variant="outline"
                  disabled={isPlanning || isSubmitting || (!topic.trim() && !(isAgenticVideoMode && sourceVideoUrl.trim()))}
                  loading={isPlanning}
                  onClick={handleStudioPlan}
                  icon={<Layers className="h-4 w-4 text-zinc-300" />}
                >
                  {isPlanning ? "Planning scenes..." : "Studio Plan & Select Footage"}
                </Button>

                <Button
                  type="submit"
                  size="md"
                  variant="primary"
                  disabled={isSubmitting || isPlanning || (!topic.trim() && !(isAgenticVideoMode && sourceVideoUrl.trim()))}
                  loading={isSubmitting}
                  icon={<Sparkles className="h-4 w-4" />}
                >
                  {isSubmitting ? "Starting..." : "Generate video"}
                </Button>
              </div>
            </div>
          </Card>
        </form>

        {/* Generated Videos History */}
        <section className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-zinc-200">Generated videos</h2>
              <p className="mt-0.5 text-xs text-zinc-500">Jobs update automatically while processing.</p>
            </div>
            <Button
              type="button"
              size="xs"
              variant="ghost"
              onClick={() => {
                setIsLoading(true);
                void loadJobs();
              }}
              icon={<RefreshCw className="h-3 w-3" />}
            >
              Refresh
            </Button>
          </div>

          {loadError && (
            <Card className="flex items-center justify-between gap-3 border-red-500/20 bg-red-500/5 p-3">
              <p className="text-xs text-red-200">{loadError}</p>
              <Button
                type="button"
                size="xs"
                variant="outline"
                onClick={() => {
                  setIsLoading(true);
                  void loadJobs();
                }}
              >
                Try again
              </Button>
            </Card>
          )}

          {isLoading ? (
            <Card className="flex justify-center p-12">
              <Loader2 className="h-6 w-6 animate-spin text-zinc-600" />
            </Card>
          ) : jobs.length === 0 ? (
            <Card className="p-12 text-center">
              <Film className="mx-auto mb-3 h-10 w-10 text-zinc-700" />
              <p className="text-sm text-zinc-400">Your generated videos will appear here.</p>
              <p className="mt-1 text-xs text-zinc-600">Start with a topic, pick a hook & subtitle style above.</p>
            </Card>
          ) : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 sm:gap-3.5">
                {jobs.map((job) => (
                  <VideoCard
                    key={job.job_id}
                    job={job}
                    onPlay={setActiveJob}
                    onDownload={handleDownload}
                    onPublishSocial={setPublishJob}
                    onRetry={handleRetryJob}
                    onDelete={handleDeleteJob}
                    onOpenStudio={setStudioJob}
                    isRetrying={isRetrying === job.job_id}
                  />
                ))}
              </div>

              {totalPages > 1 && (
                <div className="mt-4 flex items-center justify-between gap-3">
                  <p className="text-xs tabular-nums text-zinc-500">
                    Showing {(page - 1) * 8 + 1}&ndash;{Math.min(page * 8, totalJobs)} of {totalJobs}
                  </p>
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      size="xs"
                      variant="outline"
                      disabled={page <= 1}
                      onClick={() => {
                        setIsLoading(true);
                        void loadJobs(page - 1);
                      }}
                      icon={<ChevronLeft className="h-3.5 w-3.5" />}
                    >
                      Prev
                    </Button>
                    <span className="text-xs tabular-nums text-zinc-400">
                      Page {page} / {totalPages}
                    </span>
                    <Button
                      type="button"
                      size="xs"
                      variant="outline"
                      disabled={page >= totalPages}
                      onClick={() => {
                        setIsLoading(true);
                        void loadJobs(page + 1);
                      }}
                    >
                      Next
                      <ChevronRight className="ml-1 h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      </div>

      {/* Video Stream Modal */}
      {activeJob && (
        <VideoModal
          job={activeJob}
          onClose={() => setActiveJob(null)}
          onDownload={handleDownload}
          onPublishSocial={setPublishJob}
        />
      )}

      {/* Scene & Footage Studio Modal */}
      {studioJob && (
        <SceneFootageStudioModal
          job={studioJob}
          onClose={() => setStudioJob(null)}
          onStartRender={handleStartRenderWithSelected}
          onUpdateJob={handleUpdateStudioJob}
        />
      )}

      {/* Hermes Trending Radar Modal (Multi-Source Real-Time Analysis) */}
      <TrendingRadarModal
        isOpen={showTrendingModal}
        onClose={() => setShowTrendingModal(false)}
        topics={trendingTopics}
        isLoading={isLoadingTrending}
        region={trendingRegion}
        onRegionChange={(reg) => {
          setTrendingRegion(reg);
          void loadTrendingTopics(reg);
        }}
        onRefresh={() => loadTrendingTopics(trendingRegion, true)}
        onSelectTopic={handleSelectTrendingTopic}
      />

      {/* Schedule / Post to Social Media Modal */}
      {publishJob && (
        <ScheduleModal
          open={!!publishJob}
          onClose={() => setPublishJob(null)}
          jobId={publishJob.job_id}
          videoSource="video_generator"
          defaultCaption={publishJob.topic || publishJob.title || ""}
          hookText={publishJob.custom_hook || publishJob.title || publishJob.topic || ""}
          itemLabel={`(${publishJob.title || publishJob.topic || "AI Video"})`}
        />
      )}

      {/* Style Editor Modal (Hook, Subtitle & Presets Tabs) */}
      <StyleEditorModal
        open={showStyleEditor}
        onClose={() => setShowStyleEditor(false)}
        hookStyle={hookStyle}
        subtitleStyle={subtitleStyle}
        onHookChange={setHookStyle}
        onSubtitleChange={setSubtitleStyle}
        activeTab={activeStyleTab}
        aspectRatio="9:16"
        isSuperadmin={user?.is_superadmin}
        isPremium={user?.is_premium}
        userFeatures={user?.features}
      />
    </div>
  );
}
