import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useLocation, Link } from "react-router-dom";
import {
  ArrowLeft,
  Send,
  SlidersHorizontal,
  Sparkles,
  Scissors,
  Plus,
  RotateCcw,
  Play,
  Copy,
  Trash2,
  Clock,
  HelpCircle,
  Eye,
  EyeOff,
  CheckCircle2,
  AlertCircle,
  Smartphone,
  Monitor,
  Square,
  Layers,
  Share2,
  RefreshCw,
  Info,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Toggle } from "@/components/ui/Toggle";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import {
  jobs,
  analyze,
  presets as presetsApi,
  socialApi,
  type AnalyzeResponse,
  type Preset,
  type PlatformsStatusResponse,
} from "@/lib/api";
import { cn, formatDuration } from "@/lib/utils";
import {
  ClipTimelineEditor,
  type EditableClip,
} from "@/components/ClipTimelineEditor";

interface DraftJobConfig {
  aspectRatio?: string;
  stylePreset?: string;
  activePresetId?: number | null;
  brollEnabled?: boolean;
  brollImageOverlay?: boolean;
  brollBehindPerson?: boolean;
  brollVideoFootage?: boolean;
  autogridEnabled?: boolean;
  textEmphasisEnabled?: boolean;
  autoPostSocial?: boolean;
  autoPostPlatforms?: string[];
  autoPostAccountIds?: string[];
  autoPostScheduleMode?: "ai" | "custom";
  autoPostCustomTime?: string;
  hookStyleConfig?: any;
  subtitleStyleConfig?: any;
  textEmphasisStyleConfig?: any;
  watermarkStyleConfig?: any;
  ctaStyleConfig?: any;
}

export function ReviewClips() {
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const { user } = useAuth();
  const params = useParams<{ sessionId?: string; jobId?: string }>();
  const sessionId = params.sessionId || params.jobId;

  // ─── Session & Clips State ────────────────────────────────────────────────
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [analyzeResult, setAnalyzeResult] = useState<AnalyzeResponse | null>(null);
  const [editableClips, setEditableClips] = useState<EditableClip[]>([]);
  const [activeClipIndex, setActiveClipIndex] = useState<number>(0);
  const [filterMode, setFilterMode] = useState<"all" | "included" | "manual">("all");
  const [sortBy, setSortBy] = useState<"time" | "score">("time");

  // ─── Render Settings Modal State ──────────────────────────────────────────
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Settings for the final job
  const [aspectRatio, setAspectRatio] = useState<string>("9:16");
  const [userPresets, setUserPresets] = useState<Preset[]>([]);
  const [selectedPresetSlug, setSelectedPresetSlug] = useState<string>("");
  const [brollEnabled, setBrollEnabled] = useState(false);
  const [brollImageOverlay, setBrollImageOverlay] = useState(true);
  const [brollBehindPerson, setBrollBehindPerson] = useState(true);
  const [brollVideoFootage, setBrollVideoFootage] = useState(true);
  const [autogridEnabled, setAutogridEnabled] = useState(false);
  const [textEmphasisEnabled, setTextEmphasisEnabled] = useState(false);

  // AI Auto-Post State
  const [autoPostSocial, setAutoPostSocial] = useState(false);
  const [autoPostPlatforms, setAutoPostPlatforms] = useState<string[]>([]);
  const [autoPostAccountIds, setAutoPostAccountIds] = useState<string[]>([]);
  const [autoPostScheduleMode, setAutoPostScheduleMode] = useState<"ai" | "custom">("ai");
  const [autoPostCustomTime, setAutoPostCustomTime] = useState("");
  const [platformsStatus, setPlatformsStatus] = useState<PlatformsStatusResponse | null>(null);

  // Other style configs passed from draft
  const [rawStyles, setRawStyles] = useState<{
    hookStyleConfig?: any;
    subtitleStyleConfig?: any;
    textEmphasisStyleConfig?: any;
    watermarkStyleConfig?: any;
    ctaStyleConfig?: any;
  }>({});

  // ─── 1. Load Initial Data (Router State or API) ───────────────────────────
  useEffect(() => {
    presetsApi.list().then(setUserPresets).catch(() => {});
    socialApi.getPlatformsStatus().then(setPlatformsStatus).catch(() => {});

    // Try draft config from sessionStorage or location.state
    let draft: DraftJobConfig | null = location.state?.draftConfig || null;
    if (!draft) {
      try {
        const saved = sessionStorage.getItem("autocliper_job_draft_config");
        if (saved) draft = JSON.parse(saved);
      } catch {}
    }

    if (draft) {
      if (draft.aspectRatio) setAspectRatio(draft.aspectRatio);
      if (draft.stylePreset) setSelectedPresetSlug(draft.stylePreset);
      if (draft.brollEnabled !== undefined) setBrollEnabled(draft.brollEnabled);
      if (draft.brollImageOverlay !== undefined) setBrollImageOverlay(draft.brollImageOverlay);
      if (draft.brollBehindPerson !== undefined) setBrollBehindPerson(draft.brollBehindPerson);
      if (draft.brollVideoFootage !== undefined) setBrollVideoFootage(draft.brollVideoFootage);
      if (draft.autogridEnabled !== undefined) setAutogridEnabled(draft.autogridEnabled);
      if (draft.textEmphasisEnabled !== undefined) setTextEmphasisEnabled(draft.textEmphasisEnabled);
      if (draft.autoPostSocial !== undefined) setAutoPostSocial(draft.autoPostSocial);
      if (draft.autoPostPlatforms) setAutoPostPlatforms(draft.autoPostPlatforms);
      if (draft.autoPostAccountIds) setAutoPostAccountIds(draft.autoPostAccountIds);
      if (draft.autoPostScheduleMode) setAutoPostScheduleMode(draft.autoPostScheduleMode);
      if (draft.autoPostCustomTime) setAutoPostCustomTime(draft.autoPostCustomTime);
      setRawStyles({
        hookStyleConfig: draft.hookStyleConfig,
        subtitleStyleConfig: draft.subtitleStyleConfig,
        textEmphasisStyleConfig: draft.textEmphasisStyleConfig,
        watermarkStyleConfig: draft.watermarkStyleConfig,
        ctaStyleConfig: draft.ctaStyleConfig,
      });
    }

    // Check if analyzeResult passed via router state
    if (location.state?.analyzeResult) {
      const res = location.state.analyzeResult as AnalyzeResponse;
      setAnalyzeResult(res);
      const sorted = [...(res.clips || [])].sort((a, b) => a.start - b.start);
      setEditableClips(
        sorted.map((c, i) => ({
          ...c,
          rank: i + 1,
          ai_start: c.start,
          ai_end: c.end,
          modified: false,
          included: true,
        }))
      );
      setLoading(false);
      return;
    }

    // Otherwise fetch from backend session
    if (sessionId) {
      setLoading(true);
      setLoadError("");
      analyze
        .getAnalyzeSession(sessionId)
        .then((res) => {
          setAnalyzeResult(res);
          const sorted = [...(res.clips || [])].sort((a, b) => a.start - b.start);
          setEditableClips(
            sorted.map((c, i) => ({
              ...c,
              rank: i + 1,
              ai_start: c.start,
              ai_end: c.end,
              modified: false,
              included: true,
            }))
          );
        })
        .catch((err: any) => {
          const msg = err.message || "Gagal memuat sesi analisis";
          setLoadError(msg);
          toast.error(msg);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
      setLoadError("ID sesi analisis tidak ditemukan.");
    }
  }, [sessionId]);

  // ─── 2. Auto-save Clip Adjustments to Backend Session ───────────────────────
  useEffect(() => {
    if (!analyzeResult || editableClips.length === 0) return;
    const timer = setTimeout(() => {
      analyze
        .updateAnalyzeSession(analyzeResult.job_id, editableClips)
        .catch(() => {});
    }, 1200);
    return () => clearTimeout(timer);
  }, [editableClips, analyzeResult]);

  // ─── Filtered and Sorted Clips ─────────────────────────────────────────────
  const displayedClips = useMemo(() => {
    let list = [...editableClips];
    if (filterMode === "included") {
      list = list.filter((c) => c.included !== false);
    } else if (filterMode === "manual") {
      list = list.filter((c) => c.manual);
    }

    if (sortBy === "score") {
      list.sort((a, b) => (b.score || 0) - (a.score || 0));
    } else {
      list.sort((a, b) => a.start - b.start);
    }
    return list;
  }, [editableClips, filterMode, sortBy]);

  const includedCount = useMemo(
    () => editableClips.filter((c) => c.included !== false).length,
    [editableClips]
  );

  const hasAnyModified = editableClips.some((c) => c.modified);

  // ─── Clip Actions ──────────────────────────────────────────────────────────
  const toggleSelectAll = useCallback(() => {
    const allIncluded = editableClips.every((c) => c.included !== false);
    setEditableClips((prev) =>
      prev.map((c) => ({
        ...c,
        included: !allIncluded,
      }))
    );
  }, [editableClips]);

  const toggleIncludeClip = useCallback((idx: number) => {
    setEditableClips((prev) => {
      const next = [...prev];
      if (next[idx]) {
        next[idx] = {
          ...next[idx],
          included: next[idx].included === false ? true : false,
        };
      }
      return next;
    });
  }, []);

  const resetAllClips = useCallback(() => {
    setEditableClips((prev) =>
      prev.map((c) => ({
        ...c,
        start: c.ai_start,
        end: c.ai_end,
        duration: Math.round((c.ai_end - c.ai_start) * 100) / 100,
        modified: false,
      }))
    );
    toast.success("Semua klip telah di-reset ke timestamp AI");
  }, [toast]);

  const addManualClip = useCallback(() => {
    if (!analyzeResult) return;
    const dur = analyzeResult.video_duration;
    const start = 0;
    const end = Math.min(dur, 45);
    const maxRank = editableClips.length > 0 ? Math.max(...editableClips.map((c) => c.rank)) : 0;
    const newClip: EditableClip = {
      rank: maxRank + 1,
      start,
      end,
      duration: Math.round((end - start) * 100) / 100,
      score: null,
      hook: `Klip #${maxRank + 1}`,
      reason: "Dibuat manual oleh pengguna",
      content_type: "custom",
      speaker_energy: "medium",
      ai_start: start,
      ai_end: end,
      modified: false,
      manual: true,
      included: true,
    };
    setEditableClips((prev) => [...prev, newClip]);
    setActiveClipIndex(editableClips.length);
    toast.success("Klip baru berhasil ditambahkan");
  }, [analyzeResult, editableClips, toast]);

  // ─── Submit Job to Processing Pipeline ─────────────────────────────────────
  async function handleStartProcessing() {
    if (isSubmitting || !analyzeResult) return;
    const selected = editableClips.filter((c) => c.included !== false);
    if (selected.length === 0) {
      toast.error("Pilih minimal 1 klip untuk diproses!");
      return;
    }

    setIsSubmitting(true);
    try {
      // Re-order ranks sequentially 1, 2, 3...
      const customClipsPayload = selected.map((c, i) => ({
        rank: i + 1,
        start: Math.round(c.start * 100) / 100,
        end: Math.round(c.end * 100) / 100,
        hook: c.hook?.trim() || `Klip #${i + 1}`,
        score: c.score,
      }));

      const jobOptions = {
        style_preset: selectedPresetSlug || undefined,
        target_aspect_ratio: aspectRatio,
        force_reprocess: false,
        source_job_id: analyzeResult.job_id,
        use_remotion: true,
        ai_layer_enabled: true,
        threejs_enabled: false,
        remotion_quality: "medium",
        hook_style_config: rawStyles.hookStyleConfig,
        subtitle_style_config: rawStyles.subtitleStyleConfig,
        broll_enabled: brollEnabled,
        broll_image_overlay: brollEnabled ? brollImageOverlay : false,
        broll_behind_person: brollEnabled ? brollBehindPerson : false,
        broll_video_footage: brollEnabled ? brollVideoFootage : false,
        autogrid_enabled: aspectRatio === "9:16" ? autogridEnabled : false,
        text_emphasis_enabled: textEmphasisEnabled,
        text_emphasis_style_config: rawStyles.textEmphasisStyleConfig,
        watermark_config: rawStyles.watermarkStyleConfig,
        cta_config: rawStyles.ctaStyleConfig,
        auto_post_social: autoPostSocial,
        auto_post_platforms: autoPostPlatforms.join(","),
        auto_post_account_ids: autoPostAccountIds,
        auto_post_schedule_mode: autoPostScheduleMode,
        auto_post_custom_time: autoPostScheduleMode === "custom" && autoPostCustomTime ? autoPostCustomTime : undefined,
        custom_clips: customClipsPayload,
      };

      const res = await jobs.create({
        youtube_url: analyzeResult.youtube_url || "",
        ...jobOptions,
      });

      // Clear draft storage
      sessionStorage.removeItem("autocliper_job_draft_config");
      toast.success(`Job berhasil dibuat: ${res.job_id}`);
      navigate(`/jobs/${res.job_id}`);
    } catch (e: any) {
      toast.error(e.message || "Gagal membuat job");
    } finally {
      setIsSubmitting(false);
    }
  }

  // ─── Loading State ─────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex h-full min-h-0 flex-col items-center justify-center p-8 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/10 border border-emerald-500/30 shadow-lg">
          <RefreshCw className="h-6 w-6 text-emerald-400 animate-spin" />
        </div>
        <h2 className="mt-4 text-base font-semibold text-zinc-100">
          Memuat Sesi Review Clips
        </h2>
        <p className="mt-1 text-xs text-zinc-500 max-w-sm">
          Mengambil data klip kandidat dan video sumber dari server...
        </p>
      </div>
    );
  }

  // ─── Error / Not Found State ───────────────────────────────────────────────
  if (loadError || !analyzeResult) {
    return (
      <div className="flex h-full min-h-0 flex-col items-center justify-center p-8 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-400 shadow-lg">
          <AlertCircle className="h-7 w-7" />
        </div>
        <h2 className="mt-4 text-base font-semibold text-zinc-100">
          Sesi Review Tidak Ditemukan
        </h2>
        <p className="mt-1 text-xs text-zinc-400 max-w-md">
          {loadError ||
            "Sesi analisis video mungkin sudah kedaluwarsa atau belum pernah dibuat."}
        </p>
        <Link to="/jobs/new" className="mt-5">
          <Button size="sm" icon={<ArrowLeft className="h-3.5 w-3.5" />}>
            Kembali ke Buat Job Baru
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* ─── TOP HEADER ──────────────────────────────────────────────────────── */}
      <header className="flex flex-wrap items-center justify-between gap-3 shrink-0 mb-3 pb-2 border-b border-zinc-800/80">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            to="/jobs/new"
            className="rounded-xl p-2 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
            title="Kembali ke formulir New Job"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>

          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold text-zinc-100 truncate">
                Review & Edit Clips
              </h1>
              <Badge variant="default" className="text-[10px] font-mono">
                {includedCount} dari {editableClips.length} Klip Dipilih
              </Badge>
            </div>
            <p className="text-xs text-zinc-400 truncate max-w-lg mt-0.5">
              {analyzeResult.video_title || "YouTube Video"} · {formatDuration(analyzeResult.video_duration)}
            </p>
          </div>
        </div>

        {/* Right header actions */}
        <div className="flex items-center gap-2.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setShowSettingsModal(true)}
            icon={<SlidersHorizontal className="h-3.5 w-3.5" />}
            className="border-zinc-700/80 hover:bg-zinc-800 text-zinc-200"
          >
            Pengaturan Render
          </Button>

          <Button
            type="button"
            size="sm"
            loading={isSubmitting}
            disabled={isSubmitting || includedCount === 0}
            onClick={handleStartProcessing}
            icon={<Send className="h-3.5 w-3.5" />}
            className="bg-emerald-500 text-zinc-950 font-bold hover:bg-emerald-400 shadow-lg shadow-emerald-500/20"
          >
            {isSubmitting
              ? "Memproses..."
              : `Proses ${includedCount} Klip Terpilih`}
          </Button>
        </div>
      </header>

      {/* ─── MAIN TWO-COLUMN WORKSPACE ────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col lg:flex-row gap-3.5 min-h-0 overflow-y-auto lg:overflow-hidden pb-4">
        {/* ─── LEFT COLUMN: Clip Candidates Sidebar ──────────────────────────── */}
        <div className="lg:w-[350px] shrink-0 flex flex-col min-h-0 bg-zinc-950/60 border border-zinc-800/80 rounded-2xl p-3 shadow-inner">
          {/* Sidebar Header with Selection & Filter controls */}
          <div className="shrink-0 space-y-2 pb-2.5 border-b border-zinc-800">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Scissors className="h-4 w-4 text-emerald-400" />
                <h3 className="text-xs font-bold text-zinc-100">
                  Daftar Klip ({editableClips.length})
                </h3>
              </div>
              <div className="flex items-center gap-1">
                {hasAnyModified && (
                  <button
                    type="button"
                    onClick={resetAllClips}
                    className="flex items-center gap-1 text-[10px] text-amber-400 hover:text-amber-300 font-medium px-1.5 py-0.5 rounded hover:bg-zinc-800 transition-colors"
                    title="Kembalikan semua klip ke timestamp AI"
                  >
                    <RotateCcw className="h-2.5 w-2.5" />
                    Reset
                  </button>
                )}
                <button
                  type="button"
                  onClick={addManualClip}
                  className="flex items-center gap-1 rounded-lg bg-emerald-500/20 border border-emerald-500/40 px-2 py-1 text-[11px] text-emerald-300 hover:bg-emerald-500/30 font-semibold transition-all shadow-sm"
                  title="Tambah klip baru manual"
                >
                  <Plus className="h-3 w-3" />
                  Tambah
                </button>
              </div>
            </div>

            {/* Filter and Sort bar */}
            <div className="flex items-center justify-between gap-1 text-[10px]">
              <div className="flex items-center bg-zinc-900 rounded-lg p-0.5 border border-zinc-800">
                <button
                  type="button"
                  onClick={() => setFilterMode("all")}
                  className={cn(
                    "px-2 py-0.5 rounded-md font-medium transition-colors",
                    filterMode === "all" ? "bg-zinc-800 text-white font-bold" : "text-zinc-400 hover:text-zinc-200"
                  )}
                >
                  Semua
                </button>
                <button
                  type="button"
                  onClick={() => setFilterMode("included")}
                  className={cn(
                    "px-2 py-0.5 rounded-md font-medium transition-colors",
                    filterMode === "included" ? "bg-zinc-800 text-emerald-300 font-bold" : "text-zinc-400 hover:text-zinc-200"
                  )}
                >
                  Terpilih ({includedCount})
                </button>
                <button
                  type="button"
                  onClick={() => setFilterMode("manual")}
                  className={cn(
                    "px-2 py-0.5 rounded-md font-medium transition-colors",
                    filterMode === "manual" ? "bg-zinc-800 text-sky-300 font-bold" : "text-zinc-400 hover:text-zinc-200"
                  )}
                >
                  Manual
                </button>
              </div>

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={toggleSelectAll}
                  className="text-[10px] text-zinc-400 hover:text-white px-1.5 py-0.5 rounded hover:bg-zinc-800 transition-colors"
                >
                  {editableClips.every((c) => c.included !== false) ? "Lepas Semua" : "Pilih Semua"}
                </button>
              </div>
            </div>
          </div>

          {/* Sidebar Clips List (Scrollable) */}
          <div className="flex-1 min-h-0 overflow-y-auto space-y-2.5 pt-2.5 pr-0.5">
            {displayedClips.map((clip) => {
              const originalIndex = editableClips.findIndex((c) => c.rank === clip.rank);
              const isSelected = activeClipIndex === originalIndex;
              const isSweetSpot = clip.duration >= 30 && clip.duration <= 60;
              const isIncluded = clip.included !== false;

              return (
                <Card
                  key={`${clip.rank}-${originalIndex}`}
                  className={cn(
                    "p-3 cursor-pointer transition-all border relative rounded-xl",
                    !isIncluded && "opacity-50 grayscale-[30%] bg-zinc-950/30",
                    isSelected
                      ? "border-emerald-500 bg-emerald-500/[0.08] shadow-[0_0_15px_rgba(16,185,129,0.14)] ring-1 ring-emerald-500/50"
                      : "border-zinc-800/90 bg-zinc-900/40 hover:border-zinc-700 hover:bg-zinc-900/70"
                  )}
                  onClick={() => setActiveClipIndex(originalIndex)}
                >
                  <div className="flex items-start justify-between gap-2">
                    {/* Checkbox inclusion toggle */}
                    <div
                      className="pt-0.5 shrink-0"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleIncludeClip(originalIndex);
                      }}
                      title={isIncluded ? "Klip ini disertakan dalam render" : "Klip ini dilewati"}
                    >
                      <input
                        type="checkbox"
                        checked={isIncluded}
                        onChange={() => {}}
                        className="h-4 w-4 rounded border-zinc-700 bg-zinc-900 text-emerald-500 focus:ring-emerald-500 focus:ring-offset-0 cursor-pointer"
                      />
                    </div>

                    {/* Clip content details */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span
                          className={cn(
                            "rounded px-1.5 py-0.2 text-[9px] font-black",
                            isSelected ? "bg-emerald-500 text-zinc-950" : "bg-zinc-800 text-zinc-200"
                          )}
                        >
                          #{clip.rank}
                        </span>

                        {clip.score !== null && (
                          <span className="flex items-center gap-0.5 rounded bg-emerald-500/20 border border-emerald-500/30 px-1.5 py-0.2 text-[9px] font-bold text-emerald-300">
                            <Sparkles className="w-2.5 h-2.5" />
                            {clip.score}
                          </span>
                        )}

                        {clip.manual && (
                          <span className="rounded bg-sky-500/20 border border-sky-500/30 px-1.5 py-0.2 text-[9px] font-medium text-sky-300">
                            Manual
                          </span>
                        )}

                        {clip.modified && !clip.manual && (
                          <span className="rounded bg-amber-500/20 border border-amber-500/30 px-1.5 py-0.2 text-[9px] font-medium text-amber-300">
                            Disesuaikan
                          </span>
                        )}
                      </div>

                      {/* Hook text */}
                      <p className="mt-1 text-xs font-semibold text-zinc-100 line-clamp-2 leading-snug">
                        {clip.hook || `Klip #${clip.rank}`}
                      </p>

                      {/* Time & Duration badge */}
                      <div className="mt-1.5 flex items-center gap-2 text-[10px] text-zinc-400">
                        <span className="flex items-center gap-1 bg-zinc-900/90 px-1.5 py-0.5 rounded font-mono border border-zinc-800">
                          <Clock className="h-2.5 w-2.5 text-emerald-400" />
                          {Math.floor(clip.start / 60)}:
                          {Math.floor(clip.start % 60).toString().padStart(2, "0")} -{" "}
                          {Math.floor(clip.end / 60)}:
                          {Math.floor(clip.end % 60).toString().padStart(2, "0")}
                        </span>
                        <span
                          className={cn(
                            "font-mono font-semibold",
                            isSweetSpot ? "text-emerald-400" : "text-amber-400"
                          )}
                        >
                          {clip.duration.toFixed(1)}s
                        </span>
                      </div>

                      {/* AI Reason hint if available */}
                      {clip.reason && (
                        <p className="mt-1 text-[9px] text-zinc-500 line-clamp-1 italic">
                          "{clip.reason}"
                        </p>
                      )}
                    </div>

                    {/* Quick Card Action */}
                    <div className="flex flex-col gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setActiveClipIndex(originalIndex);
                        }}
                        className="rounded-lg p-1.5 bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
                        title="Pilih dan putar pratinjau"
                      >
                        <Play className="h-3 w-3 fill-current" />
                      </button>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        </div>

        {/* ─── RIGHT COLUMN: Video Player & Advanced Multi-Track Timeline ─────── */}
        <div className="flex-1 min-w-0 flex flex-col min-h-0 overflow-y-auto lg:overflow-visible">
          <ClipTimelineEditor
            clips={editableClips}
            videoDuration={analyzeResult.video_duration}
            videoSrc={analyze.getSourceVideoUrl(analyzeResult.job_id)}
            onClipsChange={setEditableClips}
            activeClipIndex={activeClipIndex}
            onActiveClipChange={setActiveClipIndex}
          />
        </div>
      </div>

      {/* ─── RENDER SETTINGS MODAL ────────────────────────────────────────────── */}
      <Modal
        open={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
        title="Pengaturan Render Video"
        size="lg"
      >
        <div className="space-y-4 text-xs">
          {/* Target Aspect Ratio */}
          <div>
            <label className="block text-xs font-bold text-zinc-200 mb-2">
              Format Rasio Video
            </label>
            <div className="grid grid-cols-3 gap-2">
              {[
                { val: "9:16", icon: Smartphone, label: "9:16 (Shorts/Reels)", desc: "Vertikal Penuh" },
                { val: "16:9", icon: Monitor, label: "16:9 (YouTube)", desc: "Horizontal" },
                { val: "1:1", icon: Square, label: "1:1 (Instagram)", desc: "Persegi" },
              ].map(({ val, icon: Icon, label, desc }) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => setAspectRatio(val)}
                  className={cn(
                    "flex flex-col items-center justify-center p-3 rounded-xl border transition-all text-center",
                    aspectRatio === val
                      ? "border-emerald-500 bg-emerald-500/15 text-emerald-300 font-bold"
                      : "border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:border-zinc-700"
                  )}
                >
                  <Icon className="h-5 w-5 mb-1 text-emerald-400" />
                  <span className="text-xs">{label}</span>
                  <span className="text-[9px] text-zinc-500 mt-0.5">{desc}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Style Preset Selector */}
          <div>
            <label className="block text-xs font-bold text-zinc-200 mb-1.5">
              Preset Gaya & Tampilan
            </label>
            <select
              value={selectedPresetSlug}
              onChange={(e) => setSelectedPresetSlug(e.target.value)}
              className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 focus:border-emerald-500 focus:outline-none"
            >
              <option value="">Default AI Style</option>
              {userPresets.map((p) => (
                <option key={p.id} value={p.slug || `preset-${p.id}`}>
                  {p.name} ({p.slug || `preset-${p.id}`})
                </option>
              ))}
            </select>
            <p className="text-[10px] text-zinc-500 mt-1">
              Pilih preset untuk menerapkan kombinasi subtitle, hook visual, dan warna animasi otomatis.
            </p>
          </div>

          {/* Features Toggles */}
          <div className="space-y-2 pt-2 border-t border-zinc-800">
            <h4 className="text-xs font-bold text-zinc-200">Fitur AI Video</h4>

            <div className="flex items-center justify-between p-2 rounded-xl bg-zinc-900/60 border border-zinc-800">
              <div>
                <p className="text-xs font-medium text-zinc-200">B-Roll Visual Footages</p>
                <p className="text-[10px] text-zinc-500">Sisipkan gambar/video b-roll pelengkap otomatis sesuai narasi</p>
              </div>
              <Toggle checked={brollEnabled} onChange={setBrollEnabled} />
            </div>

            {aspectRatio === "9:16" && (
              <div className="flex items-center justify-between p-2 rounded-xl bg-zinc-900/60 border border-zinc-800">
                <div>
                  <p className="text-xs font-medium text-zinc-200">Auto Grid Reframe (Split Screen)</p>
                  <p className="text-[10px] text-zinc-500">Otomatis deteksi pembicara ganda untuk format potret 9:16</p>
                </div>
                <Toggle checked={autogridEnabled} onChange={setAutogridEnabled} />
              </div>
            )}

            <div className="flex items-center justify-between p-2 rounded-xl bg-zinc-900/60 border border-zinc-800">
              <div>
                <p className="text-xs font-medium text-zinc-200">AI Cinematic Text Emphasis</p>
                <p className="text-[10px] text-zinc-500">Sorot kata-kata kunci penting dengan animasi warna dinamis</p>
              </div>
              <Toggle checked={textEmphasisEnabled} onChange={setTextEmphasisEnabled} />
            </div>

            {/* Auto Post Social */}
            <div className="flex items-center justify-between p-2 rounded-xl bg-zinc-900/60 border border-zinc-800">
              <div>
                <p className="text-xs font-medium text-zinc-200">AI Auto-Post ke Media Sosial</p>
                <p className="text-[10px] text-zinc-500">Jadwalkan posting otomatis setelah video selesai di-render</p>
              </div>
              <Toggle checked={autoPostSocial} onChange={setAutoPostSocial} />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-3 border-t border-zinc-800">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowSettingsModal(false)}
            >
              Tutup & Simpan
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
