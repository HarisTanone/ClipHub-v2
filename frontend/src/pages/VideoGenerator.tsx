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
  RefreshCw,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Sparkles,
  Type,
  Video,
  Volume2,
  X,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { RangeSlider } from "@/components/ui/RangeSlider";
import { Toggle } from "@/components/ui/Toggle";
import { useToast } from "@/components/ui/Toast";
import {
  DEFAULT_HOOK_STYLE,
  DEFAULT_SUBTITLE_STYLE,
  StyleEditorModal,
  type HookStyle,
  type SubtitleStyle,
} from "@/components/StyleEditorModal";
import { API_BASE, getToken } from "@/lib/api";
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

const CAPTION_PRESETS: CaptionPreset[] = [
  {
    id: "classic",
    name: "Classic",
    description: "Karaoke clean",
    accent: "#FACC15",
    patch: {
      stylePreset: "classic",
      fontFamily: "DejaVu Sans",
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
      fontFamily: "DejaVu Sans",
      fontSize: 64,
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
      fontFamily: "DejaVu Sans",
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
      fontFamily: "DejaVu Sans",
      fontSize: 50,
      fontWeight: "700",
      color: "#F8FAFC",
      highlightColor: "#FFFFFF",
      bgEnabled: false,
      strokeEnabled: false,
      shadowEnabled: true,
      shadowBlur: 10,
      position: "bottom",
      positionY: 84,
      maxWordsPerLine: 5,
      lineTransition: "line_reveal",
    },
  },
];

function loadSubtitleStyle(): SubtitleStyle {
  try {
    const saved = localStorage.getItem("autocliper_video_generator_subtitle_style");
    return {
      ...DEFAULT_SUBTITLE_STYLE,
      fontFamily: "DejaVu Sans",
      fontSize: 54,
      fontWeight: "800",
      positionY: 84,
      ...(saved ? JSON.parse(saved) : {}),
      engine: "ffmpeg",
    } as SubtitleStyle;
  } catch {
    return {
      ...DEFAULT_SUBTITLE_STYLE,
      fontFamily: "DejaVu Sans",
      fontSize: 54,
      fontWeight: "800",
      positionY: 84,
      engine: "ffmpeg",
    };
  }
}

async function fetchApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
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

function CaptionPreview({ style }: { style: SubtitleStyle }) {
  const background = style.bgEnabled
    ? `${style.bgColor}${Math.round(Math.max(0, Math.min(style.bgOpacity, 1)) * 255).toString(16).padStart(2, "0")}`
    : "transparent";
  const positionClass = style.position === "top" ? "top-5" : style.position === "center" ? "top-1/2 -translate-y-1/2" : "bottom-5";

  return (
    <div className="relative aspect-[9/16] w-[104px] shrink-0 overflow-hidden rounded-xl border border-zinc-800 bg-gradient-to-br from-zinc-700 via-zinc-900 to-black shadow-xl">
      <div className="absolute inset-0 opacity-40" style={{ background: "radial-gradient(circle at 74% 22%, #a855f7, transparent 30%), radial-gradient(circle at 24% 70%, #0ea5e9, transparent 32%)" }} />
      <div className={cn("absolute left-2 right-2", positionClass)}>
        <p
          className="text-center leading-tight"
          style={{
            color: style.color,
            background,
            borderRadius: style.bgEnabled ? Math.min(style.bgRadius, 12) : undefined,
            padding: style.bgEnabled ? "5px 4px" : 0,
            fontFamily: style.fontFamily,
            fontSize: `${Math.max(10, Math.min(19, style.fontSize * 0.31))}px`,
            fontWeight: Number(style.fontWeight),
            fontStyle: style.italic ? "italic" : "normal",
            textTransform: style.uppercase ? "uppercase" : "none",
            textShadow: style.strokeEnabled || style.shadowEnabled
              ? `0 1px ${Math.max(1, style.shadowBlur * 0.28)}px ${style.strokeColor}`
              : undefined,
          }}
        >
          THIS IS <span style={{ color: style.highlightColor }}>THE MOMENT</span>
        </p>
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
}: {
  job: VideoJob;
  onClose: () => void;
  onStartRender: (jobId: string, updatedScenes: SceneItem[]) => Promise<void>;
}) {
  const toast = useToast();
  const [scenes, setScenes] = useState<SceneItem[]>(() => {
    return (job.scenes || []).map((s) => ({
      ...s,
      selected_footage: s.selected_footage || s.footage_source || (s.footage_candidates?.[0] || null),
    }));
  });
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
        `/api/video-generator/jobs/${job.job_id}/search-scene`,
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
      await onStartRender(job.job_id, scenes);
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
                Footage Studio: {job.title || job.topic}
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
            <div className="py-12 text-center text-zinc-500">
              <Film className="mx-auto h-8 w-8 mb-2 opacity-50" />
              <p className="text-sm">No scenes generated for this job.</p>
            </div>
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
  onOpenStudio,
}: {
  job: VideoJob;
  onPlay: (job: VideoJob) => void;
  onDownload: (jobId: string) => void;
  onRetry: (jobId: string) => void;
  onOpenStudio: (job: VideoJob) => void;
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
        <div className="pt-1 flex flex-wrap gap-1.5">
          {isAwaitingSelection && (
            <Button
              type="button"
              size="xs"
              variant="primary"
              className="w-full"
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
              onClick={() => onRetry(job.job_id)}
              icon={<RotateCcw className="h-3 w-3" />}
            >
              Retry
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function VideoGeneratorPage() {
  const { user } = useAuth();
  const toast = useToast();

  const [topic, setTopic] = useState("");
  const [targetDuration, setTargetDuration] = useState(65);
  const [voice, setVoice] = useState("");
  const [speed, setSpeed] = useState(1);
  const [numScenes, setNumScenes] = useState(0);
  const [instructions, setInstructions] = useState("");
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(true);
  const [subtitleStyle, setSubtitleStyle] = useState<SubtitleStyle>(loadSubtitleStyle);
  const [includeBgm, setIncludeBgm] = useState(true);
  const [bgmVolume, setBgmVolume] = useState(0.15);

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

  const [showStyleEditor, setShowStyleEditor] = useState(false);
  const [editorHookStyle, setEditorHookStyle] = useState<HookStyle>(DEFAULT_HOOK_STYLE);

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

  useEffect(() => {
    void loadJobs();
    void loadVoices();
  }, [loadJobs, loadVoices]);

  useEffect(() => {
    localStorage.setItem("autocliper_video_generator_subtitle_style", JSON.stringify(subtitleStyle));
  }, [subtitleStyle]);

  const hasProcessingJob = useMemo(() => jobs.some((job) => isProcessing(job.status)), [jobs]);

  useEffect(() => {
    if (!hasProcessingJob) return undefined;
    const timer = window.setInterval(() => {
      void loadJobs();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [hasProcessingJob, loadJobs]);

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
          subtitles_enabled: subtitlesEnabled,
          subtitle_style_config: { ...subtitleStyle, engine: "ffmpeg" },
          include_bgm: includeBgm,
          bgm_volume: bgmVolume,
        }),
      });
      setPage(1);
      void loadJobs(1);
      setStudioJob(job);
      toast.success("AI script & footage candidate search started. Reviewing studio...");
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
      await fetchApi<VideoJob>(`/api/video-generator/jobs/${jobId}/retry`, { method: "POST" });
      setPage(1);
      void loadJobs(1);
      toast.success("A new generation attempt has started.");
    } catch (error) {
      toast.error(errorMessage(error, "Unable to retry this job."));
    } finally {
      setIsRetrying(null);
    }
  };

  const applyCaptionPreset = (preset: CaptionPreset) => {
    setSubtitleStyle((current) => ({ ...current, ...preset.patch, engine: "ffmpeg" } as SubtitleStyle));
  };

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
        {/* Banner */}
        <section className="relative overflow-hidden rounded-2xl border border-violet-500/20 bg-gradient-to-br from-violet-950/40 via-zinc-950 to-zinc-950 p-5 sm:p-6">
          <div className="absolute -right-20 -top-24 h-56 w-56 rounded-full bg-fuchsia-500/15 blur-3xl" />
          <div className="relative flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="flex items-start gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-violet-500/15 text-violet-300 border border-violet-500/30">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-violet-300">AI Video Studio</p>
                <h1 className="mt-1 text-xl font-semibold tracking-tight text-zinc-50">Video Generator</h1>
                <p className="mt-1 max-w-2xl text-sm leading-6 text-zinc-400">
                  Transform any topic into a 9:16 vertical video with AI narration, multi-source footage selection, styled karaoke captions, and delivery-ready MP4.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 self-start rounded-lg border border-zinc-800 bg-black/30 px-3 py-2 text-xs text-zinc-400 sm:self-auto">
              <Film className="h-3.5 w-3.5 text-violet-300" /> 9:16 · 1080 × 1920 · MP4
            </div>
          </div>
        </section>

        {/* Creation Form */}
        <form onSubmit={handleQuickSubmit}>
          <Card className="p-4 sm:p-5">
            <div className="mb-5 flex items-center justify-between border-b border-zinc-800/80 pb-3">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-violet-300" />
                <h2 className="text-sm font-semibold text-zinc-100">Create New Video</h2>
              </div>
              <span className="text-[11px] text-zinc-500">Interactive Studio or Quick Auto</span>
            </div>

            <div className="grid gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.9fr)]">
              {/* Left Column: Script & Voice Controls */}
              <div className="space-y-4">
                <div>
                  <div className="mb-1.5 flex items-center justify-between gap-3">
                    <label htmlFor="video-topic" className="text-xs font-medium text-zinc-300">
                      Topic
                    </label>
                    <span className="text-[11px] tabular-nums text-zinc-600">{topic.length}/500</span>
                  </div>
                  <textarea
                    id="video-topic"
                    value={topic}
                    onChange={(event) => setTopic(event.target.value)}
                    placeholder="Example: How the deep ocean creatures survive extreme pressures"
                    maxLength={500}
                    rows={3}
                    className="w-full resize-none rounded-xl border border-zinc-800 bg-zinc-950/70 px-3.5 py-3 text-sm leading-6 text-zinc-100 placeholder:text-zinc-600 outline-none transition focus:border-violet-500/60 focus:ring-2 focus:ring-violet-500/15"
                  />
                  <p className="mt-1.5 text-[11px] leading-4 text-zinc-500">
                    Be specific about the subject. The AI will write the hook, narrative breakdown, and search multi-source footage per scene.
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <div>
                    <label htmlFor="video-voice" className="mb-1.5 block text-xs font-medium text-zinc-300">
                      Narrator voice
                    </label>
                    <select
                      id="video-voice"
                      value={voice}
                      onChange={(event) => setVoice(event.target.value)}
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-950/70 px-3 py-2.5 text-sm text-zinc-100 outline-none transition focus:border-violet-500/60"
                    >
                      <option value="">Default narrator</option>
                      {voices.map((option) => (
                        <option key={option.key} value={option.model}>
                          {option.key} · {option.model}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="video-speed" className="mb-1.5 block text-xs font-medium text-zinc-300">
                      Pacing
                    </label>
                    <select
                      id="video-speed"
                      value={speed}
                      onChange={(event) => setSpeed(Number(event.target.value))}
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-950/70 px-3 py-2.5 text-sm text-zinc-100 outline-none transition focus:border-violet-500/60"
                    >
                      <option value={0.85}>Calm · 0.85×</option>
                      <option value={1}>Natural · 1.0×</option>
                      <option value={1.15}>Energetic · 1.15×</option>
                      <option value={1.3}>Fast · 1.3×</option>
                    </select>
                  </div>
                  <div>
                    <label htmlFor="video-scenes" className="mb-1.5 block text-xs font-medium text-zinc-300">
                      Scene count
                    </label>
                    <select
                      id="video-scenes"
                      value={numScenes}
                      onChange={(event) => setNumScenes(Number(event.target.value))}
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-950/70 px-3 py-2.5 text-sm text-zinc-100 outline-none transition focus:border-violet-500/60"
                    >
                      <option value={0}>Auto plan</option>
                      <option value={6}>6 scenes</option>
                      <option value={8}>8 scenes</option>
                      <option value={10}>10 scenes</option>
                    </select>
                  </div>
                </div>

                <div>
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <label className="text-xs font-medium text-zinc-300">Target duration</label>
                    <span className="text-xs font-medium text-violet-200">{targetDuration} seconds</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {[50, 65, 90].map((duration) => (
                      <button
                        key={duration}
                        type="button"
                        onClick={() => setTargetDuration(duration)}
                        className={cn(
                          "rounded-lg border px-3 py-2 text-xs font-medium transition",
                          targetDuration === duration
                            ? "border-violet-400/60 bg-violet-500/15 text-violet-100"
                            : "border-zinc-800 bg-zinc-950/50 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                        )}
                      >
                        {duration}s {duration === 50 ? "Quick" : duration === 65 ? "Balanced" : "Long"}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="mb-1.5 flex items-center justify-between gap-3">
                    <label htmlFor="video-instructions" className="text-xs font-medium text-zinc-300">
                      Creative direction <span className="font-normal text-zinc-600">optional</span>
                    </label>
                    <span className="text-[11px] tabular-nums text-zinc-600">{instructions.length}/1000</span>
                  </div>
                  <textarea
                    id="video-instructions"
                    value={instructions}
                    onChange={(event) => setInstructions(event.target.value)}
                    placeholder="Example: cinematic documentary mood, focus on mysterious biology, end with a philosophical question."
                    maxLength={1000}
                    rows={2}
                    className="w-full resize-none rounded-xl border border-zinc-800 bg-zinc-950/70 px-3.5 py-2.5 text-sm leading-6 text-zinc-100 placeholder:text-zinc-600 outline-none transition focus:border-violet-500/60 focus:ring-2 focus:ring-violet-500/15"
                  />
                </div>
              </div>

              {/* Right Column: Style & Audio Controls */}
              <div className="space-y-4 rounded-xl border border-zinc-800/80 bg-zinc-950/35 p-3.5 sm:p-4">
                <div className="flex items-center gap-2">
                  <SlidersHorizontal className="h-4 w-4 text-violet-300" />
                  <h3 className="text-sm font-medium text-zinc-100">Render controls</h3>
                </div>

                <Toggle
                  checked={subtitlesEnabled}
                  onChange={setSubtitlesEnabled}
                  label="Burn-in subtitles"
                  description="Timed ASS karaoke captions are rendered directly into the MP4."
                />

                {subtitlesEnabled && (
                  <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-3 space-y-3">
                    <div className="flex gap-3">
                      <CaptionPreview style={subtitleStyle} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-200">
                          <Type className="h-3.5 w-3.5 text-violet-300" /> Caption style
                        </div>
                        <p className="mt-1 text-[11px] leading-4 text-zinc-500">
                          {subtitleStyle.fontFamily} · {subtitleStyle.fontSize}px · {subtitleStyle.position}
                        </p>
                        <Button
                          type="button"
                          size="xs"
                          variant="outline"
                          className="mt-2.5"
                          onClick={() => setShowStyleEditor(true)}
                          icon={<Palette className="h-3 w-3" />}
                        >
                          Customize
                        </Button>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      {CAPTION_PRESETS.map((preset) => (
                        <button
                          key={preset.id}
                          type="button"
                          onClick={() => applyCaptionPreset(preset)}
                          className={cn(
                            "rounded-lg border px-2.5 py-2 text-left transition",
                            subtitleStyle.stylePreset === preset.patch.stylePreset
                              ? "border-violet-400/50 bg-violet-500/10"
                              : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700"
                          )}
                        >
                          <span className="block text-[11px] font-medium text-zinc-200">
                            <span
                              className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full"
                              style={{ backgroundColor: preset.accent }}
                            />
                            {preset.name}
                          </span>
                          <span className="mt-0.5 block text-[10px] text-zinc-500">{preset.description}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <Toggle
                  checked={includeBgm}
                  onChange={setIncludeBgm}
                  label="Background music"
                  description="A royalty-free track is mixed below the narration when available."
                />

                {includeBgm && (
                  <RangeSlider
                    label="Music level"
                    value={bgmVolume}
                    min={0.05}
                    max={0.3}
                    step={0.01}
                    onChange={setBgmVolume}
                    suffix=""
                    description="Narration remains dominant."
                  />
                )}
              </div>
            </div>

            {/* Action Buttons Bar */}
            <div className="mt-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-t border-zinc-800/80 pt-4">
              <p className="text-xs leading-5 text-zinc-500">
                Choose <span className="text-violet-300 font-medium">Studio Plan</span> to select footage 1 by 1 per scene, or <span className="text-zinc-300 font-medium">Generate video</span> for 1-click auto.
              </p>

              <div className="flex flex-wrap items-center gap-2">
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
              <p className="mt-1 text-xs text-zinc-600">Start with a topic and choose a caption style above.</p>
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
                    onOpenStudio={setStudioJob}
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
        />
      )}

      {/* Subtitle Style Editor Modal */}
      <StyleEditorModal
        open={showStyleEditor}
        onClose={() => setShowStyleEditor(false)}
        hookStyle={editorHookStyle}
        subtitleStyle={subtitleStyle}
        onHookChange={setEditorHookStyle}
        onSubtitleChange={(style) => setSubtitleStyle({ ...style, engine: "ffmpeg" })}
        activeTab="subtitle"
        aspectRatio="9:16"
        isSuperadmin={user?.is_superadmin}
        isPremium={user?.is_premium}
        userFeatures={user?.features}
      />
    </div>
  );
}
