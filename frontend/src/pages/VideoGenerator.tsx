import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
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
  type HookStyle,
  type SubtitleStyle,
} from "@/components/StyleEditorModal";
import { API_BASE, getToken, presets as presetsApi, type Preset } from "@/lib/api";
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
  error: string | null;
  output_path: string | null;
  created_at: number;
  completed_at: number | null;
  scenes_count: number;
  estimated_duration: number | null;
  thumbnail_url: string | null;
  scenes?: SceneItem[];
}

interface VoiceOption {
  key: string;
  model: string;
}

interface JobListResponse {
  items: VideoJob[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

interface CaptionPreset {
  id: string;
  name: string;
  description: string;
  accent: string;
  patch: Partial<SubtitleStyle>;
}

interface HookPreset {
  id: string;
  name: string;
  description: string;
  accent: string;
  patch: Partial<HookStyle>;
}

const HOOK_PRESETS: HookPreset[] = [
  {
    id: "impact_badge",
    name: "Impact Hazard",
    description: "Yellow caution pill",
    accent: "#FACC15",
    patch: {
      animation: "skia_impact_badge",
      fontFamily: "Anton",
      fontSize: 54,
      fontWeight: "800",
      color: "#000000",
      bgColor: "#FACC15",
      bgOpacity: 1,
      boxEnabled: true,
      boxRadius: 14,
      boxColor: "#FACC15",
      position: "top",
      positionY: 15,
      uppercase: true,
    },
  },
  {
    id: "neon_cyber",
    name: "Neon Cyber",
    description: "Cyan glow frame",
    accent: "#00F0FF",
    patch: {
      animation: "skia_neon_cyberpunk",
      fontFamily: "Montserrat",
      fontSize: 50,
      fontWeight: "900",
      color: "#00F0FF",
      bgColor: "#0A0F1E",
      bgOpacity: 0.85,
      boxEnabled: true,
      boxRadius: 16,
      strokeEnabled: true,
      strokeColor: "#00F0FF",
      strokeWidth: 3,
      glowEnabled: true,
      glowColor: "#00F0FF",
      position: "top",
      positionY: 15,
      uppercase: true,
    },
  },
  {
    id: "frosted_pill",
    name: "Frosted Glass",
    description: "Modern capsule blur",
    accent: "#FFFFFF",
    patch: {
      animation: "skia_frosted_pill",
      fontFamily: "Inter",
      fontSize: 46,
      fontWeight: "800",
      color: "#FFFFFF",
      bgColor: "#FFFFFF",
      bgOpacity: 0.22,
      boxEnabled: true,
      boxRadius: 999,
      strokeEnabled: true,
      strokeColor: "#FFFFFF",
      strokeWidth: 2,
      position: "top",
      positionY: 15,
      uppercase: false,
    },
  },
  {
    id: "aurora",
    name: "Aurora Glow",
    description: "Emerald gradient",
    accent: "#10B981",
    patch: {
      animation: "skia_aurora_gradient",
      fontFamily: "Outfit",
      fontSize: 50,
      fontWeight: "800",
      color: "#10B981",
      gradientEnabled: true,
      gradientFrom: "#10B981",
      gradientTo: "#8B5CF6",
      bgColor: "#050F0A",
      bgOpacity: 0.82,
      boxEnabled: true,
      boxRadius: 16,
      position: "top",
      positionY: 15,
      uppercase: false,
    },
  },
];

const CAPTION_PRESETS: CaptionPreset[] = [
  {
    id: "classic",
    name: "Classic",
    description: "Karaoke clean",
    accent: "#FACC15",
    patch: {
      stylePreset: "classic",
      fontFamily: "Montserrat",
      fontSize: 54,
      fontWeight: "800",
      color: "#FFFFFF",
      highlightColor: "#FACC15",
      bgEnabled: true,
      bgColor: "#000000",
      bgOpacity: 0.42,
      position: "bottom",
      positionY: 84,
      maxWordsPerLine: 3,
      lineTransition: "word_pop",
    },
  },
  {
    id: "impact",
    name: "Impact",
    description: "Bold short-form",
    accent: "#FB3B4E",
    patch: {
      stylePreset: "meme_impact",
      fontFamily: "Anton",
      fontSize: 62,
      fontWeight: "900",
      color: "#FFFFFF",
      highlightColor: "#FB3B4E",
      bgEnabled: false,
      uppercase: true,
      strokeEnabled: true,
      strokeColor: "#000000",
      strokeWidth: 4,
      position: "bottom",
      positionY: 82,
      maxWordsPerLine: 2,
      lineTransition: "word_pop",
    },
  },
  {
    id: "neon",
    name: "Neon",
    description: "Dark tech glow",
    accent: "#22D3EE",
    patch: {
      stylePreset: "neon_pulse",
      fontFamily: "Montserrat",
      fontSize: 56,
      fontWeight: "900",
      color: "#ECFEFF",
      highlightColor: "#22D3EE",
      bgEnabled: true,
      bgColor: "#020617",
      bgOpacity: 0.76,
      strokeEnabled: true,
      strokeColor: "#0F172A",
      strokeWidth: 2,
      shadowEnabled: true,
      shadowBlur: 16,
      position: "bottom",
      positionY: 84,
      maxWordsPerLine: 3,
      lineTransition: "word_pop",
    },
  },
  {
    id: "minimal",
    name: "Minimal",
    description: "Editorial clean",
    accent: "#F8FAFC",
    patch: {
      stylePreset: "minimal_clean",
      fontFamily: "Inter",
      fontSize: 48,
      fontWeight: "700",
      color: "#F8FAFC",
      highlightColor: "#FFFFFF",
      bgEnabled: false,
      strokeEnabled: false,
      shadowEnabled: true,
      shadowBlur: 10,
      position: "bottom",
      positionY: 84,
      maxWordsPerLine: 4,
      lineTransition: "line_reveal",
    },
  },
];

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
      engine: "ffmpeg",
    } as SubtitleStyle;
  } catch {
    return {
      ...DEFAULT_SUBTITLE_STYLE,
      fontFamily: "Montserrat",
      fontSize: 54,
      fontWeight: "800",
      positionY: 84,
      maxWordsPerLine: 3,
      engine: "ffmpeg",
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
}: {
  hookEnabled: boolean;
  customHook: string;
  hookStyle: HookStyle;
  subtitlesEnabled: boolean;
  subtitleStyle: SubtitleStyle;
  topic: string;
  onCustomizeHook: () => void;
  onCustomizeSubtitle: () => void;
}) {
  const [activeWordIdx, setActiveWordIdx] = useState(0);
  const [previewMode, setPreviewMode] = useState<"full" | "hook" | "subtitles">("full");
  const [isPlaying, setIsPlaying] = useState(true);

  const hookText =
    customHook.trim() ||
    (topic.trim() ? topic.trim().slice(0, 48).toUpperCase() : "CAN AI REPLACE PROGRAMMERS?");

  const wordsCount = Math.max(1, Math.min(6, subtitleStyle.maxWordsPerLine || 3));

  // Dynamic sample words adapted from topic if available
  const sampleWords = useMemo(() => {
    if (topic.trim()) {
      const clean = topic
        .trim()
        .replace(/[^\w\s]/gi, "")
        .toUpperCase()
        .split(/\s+/)
        .filter(Boolean);
      if (clean.length >= wordsCount) {
        return clean.slice(0, wordsCount);
      }
      if (clean.length > 0) {
        const fillers = ["IN", "THIS", "EXCLUSIVE", "STORY", "NOW"];
        return [...clean, ...fillers].slice(0, wordsCount);
      }
    }
    return ["UNVEILING", "THE", "HIDDEN", "TRUTH", "RIGHT", "NOW"].slice(0, wordsCount);
  }, [topic, wordsCount]);

  // Animate karaoke active word cycle
  useEffect(() => {
    if (!isPlaying) return;
    const timer = setInterval(() => {
      setActiveWordIdx((prev) => (prev + 1) % wordsCount);
    }, 650);
    return () => clearInterval(timer);
  }, [isPlaying, wordsCount]);

  // Hook preset style mapping
  const isImpact = hookStyle.animation === "skia_impact_badge";
  const isNeon = hookStyle.animation === "skia_neon_cyberpunk";
  const isFrosted = hookStyle.animation === "skia_frosted_pill";
  const isAurora = hookStyle.animation === "skia_aurora_gradient";

  const hookBoxStyle = useMemo(() => {
    if (isImpact) {
      return {
        backgroundColor: "#FACC15",
        color: "#000000",
        fontFamily: "Anton, Impact, sans-serif",
        border: "2px solid #000000",
        boxShadow: "0 4px 14px rgba(0, 0, 0, 0.8), 0 0 0 1px #FACC15",
        borderRadius: "10px",
        padding: "6px 12px",
      };
    }
    if (isNeon) {
      return {
        backgroundColor: "rgba(10, 15, 30, 0.9)",
        color: "#00F0FF",
        fontFamily: "Montserrat, sans-serif",
        border: "2px solid #00F0FF",
        boxShadow: "0 0 16px rgba(0, 240, 255, 0.6), inset 0 0 8px rgba(0, 240, 255, 0.3)",
        borderRadius: "12px",
        padding: "6px 12px",
      };
    }
    if (isFrosted) {
      return {
        backgroundColor: "rgba(255, 255, 255, 0.2)",
        backdropFilter: "blur(12px)",
        color: "#FFFFFF",
        fontFamily: "Inter, sans-serif",
        border: "1.5px solid rgba(255, 255, 255, 0.7)",
        boxShadow: "0 8px 24px rgba(0, 0, 0, 0.5)",
        borderRadius: "999px",
        padding: "5px 14px",
      };
    }
    if (isAurora) {
      return {
        background: "linear-gradient(135deg, rgba(16,185,129,0.35) 0%, rgba(139,92,246,0.35) 100%)",
        backdropFilter: "blur(10px)",
        color: "#10B981",
        fontFamily: "Outfit, sans-serif",
        border: "1.5px solid #10B981",
        boxShadow: "0 0 18px rgba(16, 185, 129, 0.4)",
        borderRadius: "12px",
        padding: "6px 12px",
      };
    }
    const hookBg = hookStyle.boxEnabled ? (hookStyle.bgColor || "#FACC15") : "transparent";
    const hookOpacity = hookStyle.boxEnabled ? (hookStyle.bgOpacity ?? 1) : 1;
    return {
      backgroundColor: hookBg,
      opacity: hookOpacity,
      color: hookStyle.color || "#000000",
      borderRadius: `${Math.min(16, hookStyle.boxRadius || 12)}px`,
      padding: "5px 8px",
      fontFamily: hookStyle.fontFamily || "Anton",
      border: hookStyle.strokeEnabled ? `${hookStyle.strokeWidth || 1}px solid ${hookStyle.strokeColor || "#000"}` : undefined,
      boxShadow: hookStyle.shadowEnabled ? `0 3px ${hookStyle.shadowBlur || 6}px ${hookStyle.shadowColor || "#000000"}` : undefined,
    };
  }, [isImpact, isNeon, isFrosted, isAurora, hookStyle]);

  const subBg = subtitleStyle.bgEnabled
    ? `${subtitleStyle.bgColor}${Math.round(Math.max(0, Math.min(subtitleStyle.bgOpacity, 1)) * 255).toString(16).padStart(2, "0")}`
    : "transparent";

  const positionClass =
    subtitleStyle.position === "top"
      ? "top-14"
      : subtitleStyle.position === "center"
      ? "top-1/2 -translate-y-1/2"
      : "bottom-14";

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
              ? "bg-violet-600/30 text-violet-200 border border-violet-500/40 shadow-xs"
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
              ? "bg-amber-500/20 text-amber-200 border border-amber-500/40 shadow-xs"
              : "text-zinc-400 hover:text-zinc-200"
          )}
        >
          <Sparkles className="h-3 w-3 text-amber-400" /> Hook (0-3s)
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

      {/* Realistic Smartphone Mockup */}
      <div className="relative aspect-[9/16] w-[230px] sm:w-[250px] shrink-0 overflow-hidden rounded-[32px] border-[5px] border-zinc-800/90 bg-zinc-950 shadow-2xl ring-1 ring-white/15">
        {/* Dynamic Island Notch */}
        <div className="absolute left-1/2 top-2 z-30 flex h-4 w-20 -translate-x-1/2 items-center justify-between rounded-full bg-black px-2.5 border border-zinc-800/80 shadow-md">
          <div className="h-1.5 w-1.5 rounded-full bg-zinc-700" />
          <div className="h-1.5 w-1.5 rounded-full bg-emerald-500/70" />
        </div>

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

        {/* Right Side Social Overlay (TikTok / Reels style) */}
        <div className="absolute right-2 bottom-16 z-20 flex flex-col items-center gap-3">
          <div className="relative flex h-7 w-7 items-center justify-center rounded-full border border-white/40 bg-gradient-to-tr from-violet-600 to-fuchsia-600 text-[10px] font-bold text-white shadow-md">
            AI
            <div className="absolute -bottom-1 flex h-3 w-3 items-center justify-center rounded-full bg-rose-500 text-[8px] text-white">
              +
            </div>
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

        {/* Opening Hook Overlay */}
        {hookEnabled && (previewMode === "full" || previewMode === "hook") ? (
          <div
            onClick={onCustomizeHook}
            className="absolute left-3 right-10 top-10 z-20 cursor-pointer transition-all hover:scale-[1.03]"
            title="Click to customize opening hook"
          >
            <div
              className="text-center transition-all mx-auto leading-snug break-words"
              style={{
                ...hookBoxStyle,
                fontSize: "11px",
                fontWeight: Number(hookStyle.fontWeight) || 800,
                textTransform: hookStyle.uppercase ? "uppercase" : "none",
                letterSpacing: `${hookStyle.letterSpacing || 0.5}px`,
              }}
            >
              {hookText}
            </div>
            <div className="mt-1 flex items-center justify-center gap-1 text-[8px] font-medium uppercase tracking-wider text-amber-300 drop-shadow-md">
              <Sparkles className="h-2.5 w-2.5 text-amber-400" /> Opening Hook (0–3s)
            </div>
          </div>
        ) : null}

        {/* Karaoke Subtitles Overlay */}
        {subtitlesEnabled && (previewMode === "full" || previewMode === "subtitles") ? (
          <div
            onClick={onCustomizeSubtitle}
            className={cn("absolute left-3 right-10 z-20 cursor-pointer transition-all hover:scale-[1.03]", positionClass)}
            title="Click to customize captions"
          >
            <div
              className="text-center transition-all mx-auto leading-snug flex flex-wrap items-center justify-center gap-x-1.5 gap-y-1"
              style={{
                backgroundColor: subBg,
                borderRadius: subtitleStyle.bgEnabled ? `${Math.min(subtitleStyle.bgRadius || 8, 12)}px` : undefined,
                padding: subtitleStyle.bgEnabled ? "4px 8px" : "2px 4px",
                fontFamily: subtitleStyle.fontFamily || "Montserrat, sans-serif",
                fontSize: `${Math.max(10, Math.min(16, (subtitleStyle.fontSize || 54) * 0.22))}px`,
                fontWeight: Number(subtitleStyle.fontWeight) || 800,
                fontStyle: subtitleStyle.italic ? "italic" : "normal",
                textTransform: subtitleStyle.uppercase ? "uppercase" : "none",
                textShadow: subtitleStyle.strokeEnabled || subtitleStyle.shadowEnabled
                  ? `0 1px ${Math.max(2, (subtitleStyle.shadowBlur || 8) * 0.3)}px ${subtitleStyle.strokeColor || "#000000"}`
                  : undefined,
              }}
            >
              {sampleWords.map((word, idx) => {
                const isActive = idx === activeWordIdx;
                return (
                  <span
                    key={idx}
                    className={cn(
                      "transition-all duration-150 inline-block",
                      isActive
                        ? "scale-110 font-black drop-shadow-[0_2px_8px_rgba(250,204,21,0.6)]"
                        : "opacity-90"
                    )}
                    style={{
                      color: isActive
                        ? subtitleStyle.highlightColor || "#FACC15"
                        : subtitleStyle.color || "#FFFFFF",
                    }}
                  >
                    {word}
                  </span>
                );
              })}
            </div>
            <div className="mt-1 flex items-center justify-center gap-1 text-[8px] font-medium uppercase tracking-wider text-violet-300 drop-shadow-md">
              <Type className="h-2.5 w-2.5 text-violet-400" /> {wordsCount} {wordsCount === 1 ? "word" : "words"} / line (Karaoke Sync)
            </div>
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
          icon={<Sparkles className="h-3 w-3 text-amber-400" />}
        >
          Hook
        </Button>
        <Button
          type="button"
          size="xs"
          variant="outline"
          onClick={onCustomizeSubtitle}
          icon={<Palette className="h-3 w-3 text-violet-400" />}
        >
          Subtitles
        </Button>
        <button
          type="button"
          onClick={() => setIsPlaying((p) => !p)}
          className="flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900/80 px-2 py-1 text-[11px] text-zinc-400 hover:text-zinc-200 transition"
          title="Play/Pause live karaoke preview"
        >
          {isPlaying ? <Pause className="h-3 w-3 text-emerald-400" /> : <Play className="h-3 w-3 text-zinc-400" />}
          {isPlaying ? "Playing" : "Paused"}
        </button>
      </div>
    </div>
  );
}

function VideoModal({ job, onClose }: { job: VideoJob; onClose: () => void }) {
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
      <div role="dialog" aria-modal="true" aria-label="Video preview" className="relative w-full max-w-[390px]" onClick={(event) => event.stopPropagation()}>
        <button type="button" aria-label="Close preview" onClick={onClose} className="absolute -top-10 right-0 rounded-lg p-1 text-zinc-400 transition-colors hover:bg-white/10 hover:text-white">
          <X className="h-5 w-5" />
        </button>
        <div className="mb-3">
          <p className="truncate text-sm font-medium text-zinc-100">{job.title || job.topic}</p>
          <p className="text-xs text-zinc-500">{job.scenes_count || "—"} scenes · {job.target_duration}s target</p>
        </div>
        <div className="aspect-[9/16] overflow-hidden rounded-2xl border border-zinc-700 bg-black shadow-2xl">
          <video src={streamUrl} controls autoPlay playsInline preload="metadata" className="h-full w-full object-contain" />
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
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-3.5 bg-zinc-900/60 shrink-0">
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

          <div className="flex items-center gap-2 shrink-0">
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
              className="p-1 rounded-lg text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition"
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
                          className="rounded-md border border-zinc-800 bg-zinc-950 px-2.5 py-1 text-[11px] text-zinc-200 placeholder:text-zinc-600 outline-none focus:border-zinc-700 w-52 sm:w-64"
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

                          const platformLabel =
                            cand.platform === "pexels"
                              ? "Pexels"
                              : cand.platform === "pixabay"
                              ? "Pixabay"
                              : "YouTube";

                          const platformColor =
                            cand.platform === "pexels"
                              ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/30"
                              : cand.platform === "pixabay"
                              ? "bg-sky-950/80 text-sky-300 border-sky-500/30"
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
  onRetry,
  onDelete,
  onOpenStudio,
  isRetrying,
}: {
  job: VideoJob;
  onPlay: (job: VideoJob) => void;
  onDownload: (jobId: string) => void;
  onRetry: (jobId: string) => void;
  onDelete: (jobId: string) => void;
  onOpenStudio: (job: VideoJob) => void;
  isRetrying?: boolean;
}) {
  const completed = job.status === "completed";
  const isAwaitingSelection = job.status === "awaiting_selection";
  const processing = isProcessing(job.status);

  return (
    <Card className="group overflow-hidden p-0 flex flex-col justify-between">
      <button
        type="button"
        disabled={!completed}
        onClick={() => completed && onPlay(job)}
        className={cn(
          "relative flex aspect-[9/16] w-full items-center justify-center bg-zinc-900 text-left",
          completed && "cursor-pointer hover:brightness-75"
        )}
      >
        {job.thumbnail_url ? (
          <img src={job.thumbnail_url} alt={job.title || job.topic} className="h-full w-full object-cover" />
        ) : (
          <Film className="h-10 w-10 text-zinc-700" />
        )}

        {completed && (
          <span className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover:opacity-100">
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white/20 pl-0.5 text-white backdrop-blur">
              <Play className="h-6 w-6" />
            </span>
          </span>
        )}

        {isAwaitingSelection && (
          <span className="absolute inset-0 flex flex-col items-center justify-center bg-black/60 p-3 text-center">
            <Layers className="mb-2 h-7 w-7 text-amber-300" />
            <span className="text-xs font-semibold text-amber-100">Footage Ready</span>
            <span className="mt-0.5 text-[10px] text-zinc-300">Click Select Footage to review</span>
          </span>
        )}

        {processing && (
          <span className="absolute inset-0 flex flex-col items-center justify-center bg-black/65">
            <Loader2 className="mb-2 h-8 w-8 animate-spin text-violet-300" />
            <span className="max-w-[80%] truncate text-center text-[11px] font-medium text-violet-100">
              {job.step_label}
            </span>
            <span className="mt-0.5 text-[10px] text-zinc-400">{job.progress}%</span>
          </span>
        )}

        {job.status === "failed" && (
          <span className="absolute inset-0 flex flex-col items-center justify-center bg-black/65">
            <AlertCircle className="mb-1 h-8 w-8 text-red-300" />
            <span className="text-[11px] text-red-200">Generation failed</span>
          </span>
        )}

        <span className="absolute left-2 top-2">
          <StatusBadge status={job.status} />
        </span>
      </button>

      <div className="p-3 space-y-2">
        <div>
          <p className="truncate text-xs font-medium text-zinc-200" title={job.title || job.topic}>
            {job.title || job.topic}
          </p>
          <p className="mt-0.5 truncate text-[11px] text-zinc-500">
            {job.target_duration}s · {job.scenes_count || "Planning"} scenes
          </p>
        </div>

        {processing && <ProgressIndicator progress={job.progress} stepLabel={job.step_label} />}
        {job.error && (
          <p className="mt-2 line-clamp-2 text-[11px] leading-4 text-red-300" title={job.error}>
            {job.error}
          </p>
        )}

        {/* Action Buttons */}
        <div className="pt-1 flex items-center justify-between gap-1.5">
          <div className="flex flex-wrap gap-1.5">
            {isAwaitingSelection && (
              <Button
                type="button"
                size="xs"
                variant="primary"
                onClick={() => onOpenStudio(job)}
                icon={<Layers className="h-3 w-3" />}
              >
                Select Footage
              </Button>
            )}

            {completed && (
              <>
                <Button
                  type="button"
                  size="xs"
                  variant="outline"
                  onClick={() => onPlay(job)}
                  icon={<Play className="h-3 w-3" />}
                >
                  Watch
                </Button>
                <Button
                  type="button"
                  size="xs"
                  variant="outline"
                  onClick={() => onDownload(job.job_id)}
                  icon={<Download className="h-3 w-3" />}
                >
                  Download
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
                icon={<RotateCcw className="h-3 w-3" />}
              >
                Retry
              </Button>
            )}
          </div>

          <button
            type="button"
            className="p-1.5 rounded-lg text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition ml-auto"
            onClick={() => onDelete(job.job_id)}
            title="Delete Job"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </Card>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

interface TopicCategory {
  name: string;
  icon: string;
  topics: string[];
}

const TOPIC_CATEGORIES: TopicCategory[] = [
  {
    name: "Tech & AI",
    icon: "🤖",
    topics: [
      "Can AI really replace human software engineers in 2026?",
      "The mystery of the developer who pushed 10,000 commits at night",
      "Why quantum computing will break modern encryption overnight",
    ],
  },
  {
    name: "Deep Mysteries",
    icon: "🌊",
    topics: [
      "How deep-sea animals withstand extreme ocean pressure",
      "The bizarre physics of rogue ocean waves appearing from nowhere",
      "Why airplanes avoid flying over the Pacific Ocean",
    ],
  },
  {
    name: "Mind & Habits",
    icon: "🧠",
    topics: [
      "The psychology of why we procrastinate hard tasks",
      "The hidden dopamine loops inside your favorite mobile apps",
      "How 10 minutes of morning sunlight reprograms your circadian clock",
    ],
  },
  {
    name: "Secrets & History",
    icon: "🏛️",
    topics: [
      "How ancient builders engineered earthquake-proof pyramids",
      "The mysterious lost civilizations hidden under rainforest canopies",
      "The secret communication network used before the telegraph",
    ],
  },
  {
    name: "Business & Wealth",
    icon: "💼",
    topics: [
      "Why modern airlines make more profit on miles than flights",
      "How a single chip shortage paused global car manufacturing",
      "The untold origin of the standard 40-hour work week",
    ],
  },
];

const CREATIVE_VIBES = [
  { label: "⚡ High Energy Viral", prompt: "Fast-paced, high energy viral storytelling with punchy surprising facts." },
  { label: "🎬 Cinematic Mystery", prompt: "Atmospheric, mysterious mood with dramatic tension and deep questions." },
  { label: "🔬 Sharp Explainer", prompt: "Clear, authoritative breakdown focusing on fascinating technical mechanics." },
  { label: "💡 Mindset Takeaway", prompt: "Reflective, inspirational narrative ending with a thought-provoking conclusion." },
];

export function VideoGeneratorPage() {
  const { user } = useAuth();
  const toast = useToast();

  // Basic narrative state
  const [topic, setTopic] = useState("");
  const [activeCategoryIdx, setActiveCategoryIdx] = useState(0);
  const [targetDuration, setTargetDuration] = useState(65);
  const [voice, setVoice] = useState("");
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

  // Job and list state
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [jobs, setJobs] = useState<VideoJob[]>([]);
  const [totalJobs, setTotalJobs] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const [activeJob, setActiveJob] = useState<VideoJob | null>(null);
  const [studioJob, setStudioJob] = useState<VideoJob | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPlanning, setIsPlanning] = useState(false);
  const [isRetrying, setIsRetrying] = useState<string | null>(null);
  const [loadError, setLoadError] = useState("");

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
      setVoices(response);
    } catch {
      setVoices([]);
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

  useEffect(() => {
    void loadJobs();
    void loadVoices();
    void loadUserPresets();
  }, [loadJobs, loadVoices, loadUserPresets]);

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

  const applyCaptionPreset = (preset: CaptionPreset) => {
    setSubtitleStyle((current) => ({
      ...current,
      ...preset.patch,
      engine: "ffmpeg",
    } as SubtitleStyle));
  };

  const applyHookPreset = (preset: HookPreset) => {
    setHookStyle((current) => ({
      ...current,
      ...preset.patch,
    } as HookStyle));
  };

  // Words per line change handler
  const handleWordsPerLineChange = (words: number) => {
    setSubtitleStyle((prev) => ({
      ...prev,
      maxWordsPerLine: words,
      engine: "ffmpeg",
    }));
  };

  // One-click quick generation (Auto mode)
  const handleQuickSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!topic.trim() || isSubmitting) return;

    setIsSubmitting(true);
    try {
      await fetchApi<VideoJob>("/api/video-generator/generate", {
        method: "POST",
        body: JSON.stringify({
          topic: topic.trim(),
          target_duration: targetDuration,
          voice,
          speed,
          num_scenes: numScenes,
          instructions: instructions.trim(),
          hook_enabled: hookEnabled,
          custom_hook: customHook.trim() || undefined,
          hook_style_config: hookStyle,
          subtitles_enabled: subtitlesEnabled,
          subtitle_style_config: { ...subtitleStyle, engine: "ffmpeg" },
          include_bgm: includeBgm,
          bgm_volume: bgmVolume,
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
    if (!topic.trim() || isPlanning) return;

    setIsPlanning(true);
    try {
      const job = await fetchApi<VideoJob>("/api/video-generator/plan", {
        method: "POST",
        body: JSON.stringify({
          topic: topic.trim(),
          target_duration: targetDuration,
          voice,
          speed,
          num_scenes: numScenes,
          instructions: instructions.trim(),
          hook_enabled: hookEnabled,
          custom_hook: customHook.trim() || undefined,
          hook_style_config: hookStyle,
          subtitles_enabled: subtitlesEnabled,
          subtitle_style_config: { ...subtitleStyle, engine: "ffmpeg" },
          include_bgm: includeBgm,
          bgm_volume: bgmVolume,
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
      toast.error(errorMessage(error, "Download failed."));
    }
  };

  const handleRetry = async (jobId: string) => {
    if (isRetrying) return;
    setIsRetrying(jobId);
    try {
      const updatedJob = await fetchApi<VideoJob>(`/api/video-generator/jobs/${jobId}/retry`, { method: "POST" });
      setJobs((prev) => prev.map((j) => (j.job_id === jobId ? updatedJob : j)));
      toast.success("Retrying video generation in background.");
    } catch (error) {
      toast.error(errorMessage(error, "Unable to retry this job."));
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

  const topicSuggestions = [
    "How deep-sea animals withstand extreme ocean pressure",
    "The mystery of the developer who pushed 10,000 commits at night",
    "Why airplanes avoid flying over the Pacific Ocean",
    "The psychology of why we procrastinate hard tasks",
    "How ancient builders engineered earthquake-proof pyramids",
  ];

  if (!user?.is_superadmin) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <Card className="max-w-sm p-8 text-center">
          <AlertCircle className="mx-auto mb-3 h-10 w-10 text-red-400" />
          <p className="text-sm font-medium text-zinc-200">Superadmin access required</p>
          <p className="mt-1 text-xs leading-5 text-zinc-500">
            Video Generator uses external AI, TTS, and rendering resources.
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6 space-y-6">
      <div className="mx-auto max-w-7xl space-y-6 pb-6">
        {/* Banner Header */}
        <section className="relative overflow-hidden rounded-2xl border border-violet-500/20 bg-gradient-to-br from-violet-950/40 via-zinc-950 to-zinc-950 p-5 sm:p-6">
          <div className="absolute -right-20 -top-24 h-56 w-56 rounded-full bg-fuchsia-500/15 blur-3xl" />
          <div className="relative flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="flex items-start gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-violet-500/15 text-violet-300 border border-violet-500/30 shadow-inner">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-violet-300">AI Video Production Studio</p>
                <h1 className="mt-1 text-xl font-semibold tracking-tight text-zinc-50">Video Generator</h1>
                <p className="mt-1 max-w-2xl text-sm leading-6 text-zinc-400">
                  Generate full vertical 9:16 short-form videos with custom opening hooks, karaoke captions (1-6 words), multi-source footage selection, and voice synthesis.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 self-start rounded-lg border border-zinc-800 bg-black/40 px-3 py-2 text-xs text-zinc-300 sm:self-auto backdrop-blur-xs">
              <Film className="h-3.5 w-3.5 text-violet-300" /> 9:16 · 1080 × 1920 · Skia Hook & ASS Subtitles
            </div>
          </div>
        </section>

        {/* Creation Form Studio */}
        <form onSubmit={handleQuickSubmit}>
          <Card className="p-4 sm:p-6 space-y-6">
            {/* Form Top Bar: Title & Preset Selector */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-800/80 pb-4">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-violet-300" />
                <h2 className="text-sm font-semibold text-zinc-100">Video Studio & Configuration</h2>
              </div>

              {/* Preset Selector */}
              <div className="flex items-center gap-2">
                <Bookmark className="h-3.5 w-3.5 text-zinc-400" />
                <span className="text-xs text-zinc-400 font-medium">Style Preset:</span>
                <select
                  value={selectedPresetId}
                  onChange={(e) => handleSelectPreset(e.target.value)}
                  className="rounded-lg border border-zinc-800 bg-zinc-950/80 px-2.5 py-1.5 text-xs text-zinc-200 outline-none transition focus:border-violet-500/60"
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
                  icon={<Palette className="h-3 w-3 text-violet-300" />}
                >
                  Presets
                </Button>
              </div>
            </div>

            {/* Studio Layout: Left Controls vs Right Visual Suite */}
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(340px,1fr)]">
              {/* Left Column: Narrative, Audio Suite, Format, Specs */}
              <div className="space-y-4">
                {/* 1. Topic & Story Ideation Card */}
                <div className="rounded-2xl border border-zinc-800/80 bg-zinc-950/60 p-4 space-y-3.5 shadow-sm">
                  <div className="flex items-center justify-between gap-3 border-b border-zinc-800/60 pb-2.5">
                    <div className="flex items-center gap-2">
                      <Sparkles className="h-4 w-4 text-violet-400" />
                      <label htmlFor="video-topic" className="text-xs font-semibold uppercase tracking-wider text-zinc-200">
                        Video Topic & Subject
                      </label>
                    </div>
                    <span className="text-[11px] tabular-nums text-zinc-500 font-mono">{topic.length}/500</span>
                  </div>

                  <textarea
                    id="video-topic"
                    value={topic}
                    onChange={(event) => setTopic(event.target.value)}
                    placeholder="Example: How deep-sea creatures survive extreme ocean pressure"
                    maxLength={500}
                    rows={3}
                    className="w-full resize-none rounded-xl border border-zinc-800 bg-zinc-900/60 px-3.5 py-2.5 text-sm leading-6 text-zinc-100 placeholder:text-zinc-600 outline-none transition focus:border-violet-500/70 focus:ring-2 focus:ring-violet-500/20"
                  />

                  {/* Category Pills & Interactive Topic Suggestions */}
                  <div className="space-y-2">
                    <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
                      <span className="text-[10px] uppercase font-medium tracking-wider text-zinc-500 shrink-0">Inspiration:</span>
                      {TOPIC_CATEGORIES.map((cat, idx) => (
                        <button
                          key={cat.name}
                          type="button"
                          onClick={() => setActiveCategoryIdx(idx)}
                          className={cn(
                            "flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-medium transition shrink-0",
                            activeCategoryIdx === idx
                              ? "bg-violet-600/30 text-violet-200 border border-violet-500/40 shadow-xs"
                              : "bg-zinc-900/60 text-zinc-400 border border-zinc-800/80 hover:text-zinc-200 hover:border-zinc-700"
                          )}
                        >
                          <span>{cat.icon}</span>
                          <span>{cat.name}</span>
                        </button>
                      ))}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 pt-0.5">
                      {TOPIC_CATEGORIES[activeCategoryIdx].topics.map((t, idx) => (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => setTopic(t)}
                          className={cn(
                            "flex items-start gap-1.5 rounded-lg border p-2 text-left text-xs transition",
                            topic === t
                              ? "border-violet-500/50 bg-violet-500/10 text-violet-200"
                              : "border-zinc-800/80 bg-zinc-900/40 text-zinc-400 hover:border-violet-500/30 hover:text-zinc-200"
                          )}
                        >
                          <Lightbulb className="h-3.5 w-3.5 text-amber-400/80 shrink-0 mt-0.5" />
                          <span className="line-clamp-2 leading-relaxed">{t}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* 2. Audio & Speech Engine Card (Voice, Pacing & BGM) */}
                <div className="rounded-2xl border border-zinc-800/80 bg-zinc-950/60 p-4 space-y-3.5 shadow-sm">
                  <div className="flex items-center justify-between border-b border-zinc-800/60 pb-2.5">
                    <div className="flex items-center gap-2">
                      <Volume2 className="h-4 w-4 text-emerald-400" />
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-200">
                        Audio & Speech Engine
                      </h3>
                    </div>
                    <span className="rounded-md border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
                      Deepgram Aura-2
                    </span>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    {/* Narrator Voice */}
                    <div>
                      <div className="mb-1.5 flex items-center justify-between">
                        <label htmlFor="video-voice" className="text-xs font-medium text-zinc-300">
                          Narrator voice
                        </label>
                        <span className="text-[10px] text-zinc-500">Natural TTS</span>
                      </div>
                      <select
                        id="video-voice"
                        value={voice}
                        onChange={(event) => setVoice(event.target.value)}
                        className="w-full rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-sm text-zinc-100 outline-none transition focus:border-violet-500/60"
                      >
                        <option value="">Default narrator</option>
                        {voices.map((option) => (
                          <option key={option.key} value={option.model}>
                            {option.key} · {option.model}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Voice Pacing Dropdown */}
                    <div>
                      <div className="mb-1.5 flex items-center justify-between">
                        <label htmlFor="video-speed" className="text-xs font-medium text-zinc-300">
                          Pacing
                        </label>
                        <span className="text-[10px] font-semibold text-violet-300">{speed}× Tempo</span>
                      </div>
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

                  {/* Speed Quick Selector Cards */}
                  <div className="grid grid-cols-4 gap-1.5">
                    {[
                      { val: 0.85, label: "0.85×", sub: "Calm" },
                      { val: 1.0, label: "1.0×", sub: "Natural" },
                      { val: 1.15, label: "1.15×", sub: "Viral" },
                      { val: 1.3, label: "1.3×", sub: "Rapid" },
                    ].map((s) => (
                      <button
                        key={s.val}
                        type="button"
                        onClick={() => setSpeed(s.val)}
                        className={cn(
                          "rounded-lg border py-1.5 text-center transition",
                          speed === s.val
                            ? "border-violet-400/60 bg-violet-500/20 text-violet-100"
                            : "border-zinc-800/80 bg-zinc-900/40 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                        )}
                      >
                        <div className="text-xs font-bold">{s.label}</div>
                        <div className="text-[9px] text-zinc-500">{s.sub}</div>
                      </button>
                    ))}
                  </div>

                  {/* Background Music Integrated into Audio Engine */}
                  <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/50 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <Toggle
                        checked={includeBgm}
                        onChange={setIncludeBgm}
                        label="Background Music"
                        description="A royalty-free track is mixed below the narration."
                      />
                    </div>
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
                <div className="rounded-2xl border border-zinc-800/80 bg-zinc-950/60 p-4 space-y-3.5 shadow-sm">
                  <div className="flex items-center justify-between border-b border-zinc-800/60 pb-2.5">
                    <div className="flex items-center gap-2">
                      <Film className="h-4 w-4 text-blue-400" />
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-200">
                        Format & Scene Pacing
                      </h3>
                    </div>
                    <span className="text-[11px] text-zinc-400 font-mono">9:16 Vertical</span>
                  </div>

                  {/* Duration Picker */}
                  <div>
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <label className="text-xs font-medium text-zinc-300">Target duration</label>
                      <span className="text-xs font-medium text-violet-200">{targetDuration} seconds</span>
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { duration: 50, label: "50s", desc: "Quick Reel", words: "~120 words" },
                        { duration: 65, label: "65s", desc: "Standard", words: "~160 words" },
                        { duration: 90, label: "90s", desc: "Deep Dive", words: "~220 words" },
                      ].map((item) => (
                        <button
                          key={item.duration}
                          type="button"
                          onClick={() => setTargetDuration(item.duration)}
                          className={cn(
                            "rounded-xl border p-2.5 text-center transition",
                            targetDuration === item.duration
                              ? "border-violet-400/60 bg-violet-500/15 text-violet-100 shadow-xs"
                              : "border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                          )}
                        >
                          <div className="text-xs font-bold">{item.label}</div>
                          <div className="text-[10px] text-zinc-300">{item.desc}</div>
                          <div className="text-[9px] text-zinc-500">{item.words}</div>
                        </button>
                      ))}
                    </div>
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

                  {/* Creative Direction & Vibe Chips */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-3">
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
                      className="w-full resize-none rounded-xl border border-zinc-800 bg-zinc-900/60 px-3.5 py-2.5 text-sm leading-6 text-zinc-100 placeholder:text-zinc-600 outline-none transition focus:border-violet-500/60 focus:ring-2 focus:ring-violet-500/15"
                    />
                    <div className="flex flex-wrap gap-1">
                      {CREATIVE_VIBES.map((vibe) => (
                        <button
                          key={vibe.label}
                          type="button"
                          onClick={() => setInstructions((prev) => (prev ? `${prev}. ${vibe.prompt}` : vibe.prompt))}
                          className="rounded-md border border-zinc-800 bg-zinc-900/60 px-2 py-0.5 text-[10px] text-zinc-400 hover:border-violet-500/40 hover:text-zinc-200 transition"
                        >
                          {vibe.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* 4. Live Production Spec Sheet */}
                <div className="rounded-2xl border border-violet-500/20 bg-gradient-to-br from-violet-950/30 via-zinc-950 to-zinc-950 p-3.5">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-violet-300 mb-2">
                    <Wand2 className="h-3.5 w-3.5" /> Studio Output Specs
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                    <div className="rounded-lg border border-zinc-800/80 bg-black/40 p-2">
                      <span className="text-zinc-500 block text-[9px] uppercase">Format</span>
                      <span className="font-semibold text-zinc-200">1080×1920 9:16</span>
                    </div>
                    <div className="rounded-lg border border-zinc-800/80 bg-black/40 p-2">
                      <span className="text-zinc-500 block text-[9px] uppercase">Narration</span>
                      <span className="font-semibold text-zinc-200">{voice ? voice.split("-")[2] || "Deepgram" : "Default"} ({speed}×)</span>
                    </div>
                    <div className="rounded-lg border border-zinc-800/80 bg-black/40 p-2">
                      <span className="text-zinc-500 block text-[9px] uppercase">Hook Overlay</span>
                      <span className="font-semibold text-amber-300">{hookEnabled ? "Active (0-3s)" : "Disabled"}</span>
                    </div>
                    <div className="rounded-lg border border-zinc-800/80 bg-black/40 p-2">
                      <span className="text-zinc-500 block text-[9px] uppercase">Karaoke Captions</span>
                      <span className="font-semibold text-violet-300">{subtitlesEnabled ? `${subtitleStyle.maxWordsPerLine || 3}w / line` : "Disabled"}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Right Column: Visual Studio (Live 9:16 Preview + Hook + Subtitles Controls) */}
              <div className="space-y-4 rounded-2xl border border-zinc-800/80 bg-zinc-950/60 p-4 shadow-sm">
                <div className="flex items-center justify-between border-b border-zinc-800/60 pb-2.5">
                  <div className="flex items-center gap-2">
                    <SlidersHorizontal className="h-4 w-4 text-violet-300" />
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-200">Visual & Audio Studio</h3>
                  </div>
                  <span className="text-[11px] text-zinc-400 font-mono bg-zinc-900/80 border border-zinc-800 px-2 py-0.5 rounded-md">1080×1920 · 9:16</span>
                </div>

                {/* Live 9:16 Canvas Preview */}
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
                  />
                </div>

                {/* Opening Hook Overlay Section */}
                <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/50 p-3.5 space-y-3">
                  <div className="flex items-center justify-between">
                    <Toggle
                      checked={hookEnabled}
                      onChange={setHookEnabled}
                      label="Opening Hook Title"
                      description="Burn an attention-grabbing hook overlay in the first 3 seconds."
                    />
                    <Button
                      type="button"
                      size="xs"
                      variant="outline"
                      onClick={() => openEditorFor("hook")}
                      icon={<Palette className="h-3 w-3 text-amber-400" />}
                    >
                      Style
                    </Button>
                  </div>

                  {hookEnabled && (
                    <div className="space-y-2.5 pt-1">
                      <div>
                        <label className="text-[11px] font-medium text-zinc-400 mb-1 block">
                          Custom Hook Text <span className="text-zinc-600 font-normal">(empty = AI generated)</span>
                        </label>
                        <input
                          type="text"
                          value={customHook}
                          onChange={(e) => setCustomHook(e.target.value)}
                          placeholder="e.g. THE SECRET OF DEEP OCEAN"
                          maxLength={100}
                          className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-xs text-zinc-200 placeholder:text-zinc-600 outline-none focus:border-amber-500/60"
                        />
                      </div>

                      {/* Hook Quick Presets */}
                      <div>
                        <span className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5 block">Hook Style Presets:</span>
                        <div className="grid grid-cols-2 gap-1.5">
                          {HOOK_PRESETS.map((preset) => (
                            <button
                              key={preset.id}
                              type="button"
                              onClick={() => applyHookPreset(preset)}
                              className={cn(
                                "rounded-lg border px-2.5 py-2 text-left transition text-xs",
                                hookStyle.animation === preset.patch.animation
                                  ? "border-amber-400/60 bg-amber-500/15 text-amber-100 shadow-xs"
                                  : "border-zinc-800 bg-zinc-950/60 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                              )}
                            >
                              <div className="flex items-center gap-1.5">
                                <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: preset.accent }} />
                                <span className="font-medium truncate">{preset.name}</span>
                              </div>
                              <div className="text-[10px] text-zinc-500 truncate mt-0.5">{preset.description}</div>
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Subtitles & Words-Per-Line Section */}
                <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/50 p-3.5 space-y-3">
                  <div className="flex items-center justify-between">
                    <Toggle
                      checked={subtitlesEnabled}
                      onChange={setSubtitlesEnabled}
                      label="Karaoke Subtitles"
                      description="Render styled ASS captions synced with narration."
                    />
                    <Button
                      type="button"
                      size="xs"
                      variant="outline"
                      onClick={() => openEditorFor("subtitle")}
                      icon={<Palette className="h-3 w-3 text-violet-400" />}
                    >
                      Style
                    </Button>
                  </div>

                  {subtitlesEnabled && (
                    <div className="space-y-3 pt-1">
                      {/* Words Per Line Selector (1 to 6 words) */}
                      <div>
                        <div className="flex items-center justify-between mb-1.5">
                          <label className="text-[11px] font-medium text-zinc-300">
                            Words displayed per line:
                          </label>
                          <span className="text-xs font-semibold text-violet-300">
                            {subtitleStyle.maxWordsPerLine || 3} {Number(subtitleStyle.maxWordsPerLine) === 1 ? "word" : "words"}
                          </span>
                        </div>
                        <div className="grid grid-cols-6 gap-1">
                          {[1, 2, 3, 4, 5, 6].map((w) => (
                            <button
                              key={w}
                              type="button"
                              onClick={() => handleWordsPerLineChange(w)}
                              className={cn(
                                "rounded-md border py-1.5 text-xs font-medium transition text-center",
                                (subtitleStyle.maxWordsPerLine || 3) === w
                                  ? "border-violet-400/60 bg-violet-500/25 text-violet-200 shadow-xs"
                                  : "border-zinc-800 bg-zinc-950/60 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                              )}
                            >
                              {w}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Subtitle Quick Presets */}
                      <div>
                        <span className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5 block">Caption Presets:</span>
                        <div className="grid grid-cols-2 gap-1.5">
                          {CAPTION_PRESETS.map((preset) => (
                            <button
                              key={preset.id}
                              type="button"
                              onClick={() => applyCaptionPreset(preset)}
                              className={cn(
                                "rounded-lg border px-2.5 py-2 text-left transition text-xs",
                                subtitleStyle.stylePreset === preset.patch.stylePreset
                                  ? "border-violet-400/60 bg-violet-500/15 text-violet-100 shadow-xs"
                                  : "border-zinc-800 bg-zinc-950/60 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                              )}
                            >
                              <div className="flex items-center gap-1.5">
                                <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: preset.accent }} />
                                <span className="font-medium truncate">{preset.name}</span>
                              </div>
                              <div className="text-[10px] text-zinc-500 truncate mt-0.5">{preset.description}</div>
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Action Buttons Bar */}
            <div className="mt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-t border-zinc-800/80 pt-4">
              <p className="text-xs leading-5 text-zinc-400">
                Choose <span className="text-violet-300 font-medium">Studio Plan</span> to curate footage 1-by-1 in Footage Studio, or <span className="text-zinc-200 font-medium">Generate video</span> for 1-click auto.
              </p>

              <div className="flex flex-wrap items-center gap-2.5">
                <Button
                  type="button"
                  size="md"
                  variant="outline"
                  disabled={isPlanning || isSubmitting || !topic.trim()}
                  loading={isPlanning}
                  onClick={handleStudioPlan}
                  icon={<Layers className="h-4 w-4 text-violet-400" />}
                >
                  {isPlanning ? "Planning scenes..." : "Studio Plan & Select Footage"}
                </Button>

                <Button
                  type="submit"
                  size="md"
                  variant="primary"
                  disabled={isSubmitting || isPlanning || !topic.trim()}
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
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                {jobs.map((job) => (
                  <VideoCard
                    key={job.job_id}
                    job={job}
                    onPlay={setActiveJob}
                    onDownload={handleDownload}
                    onRetry={handleRetry}
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
      {activeJob && <VideoModal job={activeJob} onClose={() => setActiveJob(null)} />}

      {/* Scene & Footage Studio Modal */}
      {studioJob && (
        <SceneFootageStudioModal
          job={studioJob}
          onClose={() => setStudioJob(null)}
          onStartRender={handleStartRenderWithSelected}
          onUpdateJob={handleUpdateStudioJob}
        />
      )}

      {/* Style Editor Modal (Hook, Subtitle & Presets Tabs) */}
      <StyleEditorModal
        open={showStyleEditor}
        onClose={() => setShowStyleEditor(false)}
        hookStyle={hookStyle}
        subtitleStyle={subtitleStyle}
        onHookChange={setHookStyle}
        onSubtitleChange={(style) => setSubtitleStyle({ ...style, engine: "ffmpeg" })}
        activeTab={activeStyleTab}
        aspectRatio="9:16"
        isSuperadmin={user?.is_superadmin}
        isPremium={user?.is_premium}
        userFeatures={user?.features}
      />
    </div>
  );
}
