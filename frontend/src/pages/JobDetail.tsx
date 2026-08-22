import { useState, useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Play, XCircle, ExternalLink, Clock, User, Eye, Sparkles, Layers, Film, Scissors, Radio, CheckCircle, AlertTriangle, Activity, RefreshCw, FileVideo, Lock, LoaderCircle, Download, Copy, Check, Zap } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ProgressBar, StepProgress } from "@/components/ui/Progress";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import { jobs, preview, youtubeCookies, type JobDetailResponse, type VideoPreview, type ClipInfo } from "@/lib/api";
import { useProgress } from "@/hooks/useProgress";
import { formatDuration, formatDate, cn } from "@/lib/utils";

const PIPELINE_STEPS = [
  { name: "validate", label: "Validating URL" },
  { name: "download", label: "Downloading Video" },
  { name: "transcript", label: "Transcript" },
  { name: "analysis", label: "AI Analysis" },
  { name: "prepare", label: "Preparing Clips" },
  { name: "aspect_router", label: "Aspect Routing" },
  { name: "trim", label: "Trimming" },
  { name: "reframe", label: "Smart Framing" },
  { name: "word_level", label: "Word Sync" },
  { name: "highlights", label: "Subtitle Data" },
  { name: "assets", label: "Assets" },
  { name: "subtitle", label: "Overlay" },
  { name: "remotion_render", label: "Remotion" },
  { name: "thumbnail", label: "Thumbnails" },
  { name: "finalize", label: "Finalizing" },
  { name: "assemble", label: "Assembling" },
];

export function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const toast = useToast();
  const navigate = useNavigate();
  const [isReprocessing, setIsReprocessing] = useState(false);
  const [data, setData] = useState<JobDetailResponse["data"] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [videoMeta, setVideoMeta] = useState<VideoPreview | null>(null);

  const isTerminal = data ? ["completed", "failed", "timeout"].includes(data.status) : false;
  const { progress } = useProgress(jobId, !isTerminal);

  async function loadDetail() {
    if (!jobId) return;
    setIsLoading(true);
    try {
      const detailRes = await jobs.getDetail(jobId);
      setData(detailRes.data);
      setError(null);
      // Fetch YouTube metadata only for YouTube source URLs
      if (detailRes.data.source_type !== "upload" && detailRes.data.youtube_url && !videoMeta) {
        preview.fetchMetadata(detailRes.data.youtube_url).then(setVideoMeta).catch(() => null);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadDetail();
  }, [jobId]);

  // Refresh when progress says terminal
  useEffect(() => {
    if (progress?.isTerminal && data && !isTerminal) {
      loadDetail();
    }
  }, [progress?.isTerminal]);

  // Candidate slots and final clips become available independently. Refresh
  // both when AI publishes the total and whenever another final render unlocks.
  useEffect(() => {
    const renderedCount = data?.clips?.filter((clip) => clip.has_final).length || 0;
    const listedCount = data?.clips?.length || 0;
    if (
      !isTerminal
      && progress
      && (progress.clipsAvailable.length !== renderedCount || progress.clipsTotal !== listedCount)
    ) loadDetail();
  }, [progress?.clipsAvailable.join(","), progress?.clipsTotal]);

  async function handleCancel() {
    if (!jobId) return;
    try {
      await jobs.cancel(jobId);
      toast.success("Job cancelled");
      loadDetail();
    } catch (e: any) {
      toast.error(e.message);
    }
  }

  async function handleReprocess() {
    if (!jobId) return;
    setIsReprocessing(true);
    try {
      const next = await jobs.reprocess(jobId);
      toast.success("Reprocess started and is now tracked");
      navigate(`/jobs/${next.job_id}`);
    } catch (e: any) { toast.error(e.message || "Could not reprocess job"); }
    finally { setIsReprocessing(false); }
  }

  const [isAutoFixingCookies, setIsAutoFixingCookies] = useState(false);

  async function handleAutoFixCookiesAndReprocess() {
    if (!jobId) return;
    setIsAutoFixingCookies(true);
    try {
      toast.info("Sedang mengambil cookies YouTube otomatis dari browser...");
      const cookieRes = await youtubeCookies.autoExtract("auto");
      if (!cookieRes.success) {
        toast.error(cookieRes.message || "Gagal mengambil cookies otomatis");
        setIsAutoFixingCookies(false);
        return;
      }
      toast.success(cookieRes.message);

      toast.info("Memulai proses ulang video dengan sesi cookies baru...");
      const next = await jobs.reprocess(jobId);
      toast.success("Proses ulang berhasil dijalankan!");
      if (next?.job_id && next.job_id !== jobId) {
        navigate(`/jobs/${next.job_id}`);
      } else {
        loadDetail();
      }
    } catch (e: any) {
      toast.error(e?.message || "Gagal memproses ulang dengan cookies");
    } finally {
      setIsAutoFixingCookies(false);
    }
  }

  if (isLoading && !data) {
    return (
      <div className="h-full min-h-0 overflow-y-auto space-y-3">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (error || !data) {
    return (
      <EmptyState
        icon={<XCircle className="h-10 w-10 text-red-400" />}
        title="Job not found"
        description={error || "Could not load job details"}
        action={<Link to="/"><Button variant="secondary" size="sm">Back to Dashboard</Button></Link>}
      />
    );
  }

  const currentStep = progress?.currentStep ?? (isTerminal && data.status === "completed" ? PIPELINE_STEPS.length : 0);
  const percentage = progress?.percentage ?? (data.status === "completed" ? 100 : 0);
  const readyClips = data.clips?.filter((clip) => clip.has_final).length || 0;
  const remainingClips = Math.max(0, data.clips_total - readyClips);
  const remainingLabel = isTerminal ? "unavailable" : "processing";
  const clipCompletionRate = data.clips_total ? Math.round((readyClips / data.clips_total) * 100) : 0;
  const jobShort = (jobId || data.job_id).replace("job_", "").slice(0, 12);
  const stageLabel = progress?.stepLabel || (data.status === "completed" ? "Completed" : isTerminal ? "Stopped" : "Preparing pipeline");
  const createdDate = data.created_at ? formatDate(data.created_at).split(",")[0] : "-";
  const isUploadSource = data.source_type === "upload";
  const sourceLabel = data.source_label || data.youtube_url;

  return (
    <div className="h-full min-h-0 overflow-y-auto space-y-3">
      <Card className="p-4 overflow-hidden">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-3 min-w-0">
            <Link to="/" className="mt-0.5 rounded-lg border border-zinc-800 p-2 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 transition-colors shrink-0">
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-emerald-500/25 bg-emerald-500/10 text-emerald-300">
                  <Film className="h-4 w-4" />
                </span>
                <h1 className="text-lg font-semibold text-zinc-100 truncate">{videoMeta?.title || "Job Detail"}</h1>
                <Badge variant="status" status={data.status} dot>{data.status}</Badge>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
                <span className="font-mono text-zinc-400">{jobShort}</span>
                <span>{data.target_aspect_ratio || "9:16"}</span>
                <span>{createdDate}</span>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {readyClips > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => window.open(jobs.getDownloadAllUrl(data.job_id), "_blank")}
                icon={<Download className="h-3.5 w-3.5 text-emerald-400" />}
                className="border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20"
              >
                Download All ZIP ({readyClips})
              </Button>
            )}
            <Button variant="ghost" size="xs" onClick={loadDetail} icon={<RefreshCw className="h-3 w-3" />}>Refresh</Button>
            {!isTerminal && (
              <Button variant="danger" size="sm" onClick={handleCancel}>Cancel</Button>
            )}
            {(data.status === "failed" || data.status === "timeout") && <Button size="sm" onClick={handleReprocess} loading={isReprocessing} icon={<RefreshCw className="h-3.5 w-3.5" />}>Reprocess</Button>}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <MetricTile icon={<Activity className="h-4 w-4" />} label="Progress" value={`${percentage}%`} hint={stageLabel} tone="blue" />
          <MetricTile icon={<Scissors className="h-4 w-4" />} label="Clips" value={`${readyClips}/${data.clips_total}`} hint={`${readyClips} ready, ${remainingClips} ${remainingLabel} · ${clipCompletionRate}%`} tone="emerald" />
          <MetricTile icon={<Clock className="h-4 w-4" />} label="Duration" value={data.video_duration ? formatDuration(data.video_duration) : "-"} hint="Source length" tone="amber" />
          <MetricTile icon={<Film className="h-4 w-4" />} label="Output" value={data.target_aspect_ratio || "9:16"} hint={data.style_preset || "Custom style"} tone="zinc" />
        </div>

      </Card>

      {!isTerminal && (
        <Card className="p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2">
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-blue-500/20 bg-blue-500/10 text-blue-300">
                <Radio className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-zinc-100">Render Timeline</p>
                <p className="truncate text-[11px] text-zinc-500">{stageLabel}</p>
              </div>
            </div>
            <Badge variant="info" size="sm">{percentage}%</Badge>
          </div>
          <StepProgress steps={PIPELINE_STEPS} currentStep={currentStep} />
          <ProgressBar value={percentage} className="mt-3" label="Render progress" showValue />
          {progress?.eta && <p className="mt-2 text-[10px] text-zinc-500">Estimated remaining {formatDuration(progress.eta.remaining_seconds)} · based on {progress.eta.sample_count} completed jobs and current measured progress</p>}
        </Card>
      )}

      {isTerminal && (
        <Card className={cn("p-3 border", data.status === "completed" ? "border-emerald-500/20 bg-emerald-500/[0.04]" : "border-amber-500/20 bg-amber-500/[0.04]")}>
          <div className="flex items-center gap-2">
            {data.status === "completed" ? <CheckCircle className="h-4 w-4 text-emerald-400" /> : <AlertTriangle className="h-4 w-4 text-amber-400" />}
            <p className="text-sm text-zinc-200">{data.status === "completed" ? "Job completed and clips are ready to review." : "Job stopped before completion."}</p>
          </div>
        </Card>
      )}

      {data.error_message && (
        <div className="space-y-3">
          <Card className="p-4 border-red-500/20 bg-red-950/20">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
              <p className="text-sm text-red-300">{data.error_message}</p>
            </div>
          </Card>

          {/* Smart Auto-Fix Suggestion for YouTube Bot Block / Unavailable */}
          {(data.error_message.toLowerCase().includes("tidak tersedia") ||
            data.error_message.toLowerCase().includes("unavailable") ||
            data.error_message.toLowerCase().includes("private") ||
            data.error_message.toLowerCase().includes("bot") ||
            data.error_message.toLowerCase().includes("sign in") ||
            data.error_message.toLowerCase().includes("403") ||
            data.error_message.toLowerCase().includes("verifikasi")) && !isUploadSource && (
            <Card className="p-4 border-amber-500/40 bg-gradient-to-r from-amber-950/50 via-zinc-900/80 to-zinc-900/80 shadow-xl">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div className="flex items-start gap-3">
                  <div className="h-10 w-10 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 shrink-0">
                    <Zap className="h-5 w-5 fill-current" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-amber-200 uppercase tracking-wider">Saran: Ambil Cookies YouTube Otomatis (1-Klik)</h4>
                    <p className="text-[11px] text-zinc-300 mt-0.5 leading-relaxed">
                      YouTube mendeteksi IP server dan memerlukan autentikasi browser. Klik tombol di samping agar sistem <strong className="text-amber-300">langsung mengambil cookies browser otomatis tanpa ekstensi</strong> dan memproses ulang video ini.
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0 w-full sm:w-auto">
                  <Button
                    onClick={handleAutoFixCookiesAndReprocess}
                    loading={isAutoFixingCookies}
                    size="sm"
                    className="w-full sm:w-auto bg-amber-500 hover:bg-amber-400 text-zinc-950 font-bold border-none shadow-md"
                    icon={<Zap className="h-3.5 w-3.5 fill-current" />}
                  >
                    Ambil Cookies & Proses Ulang
                  </Button>
                </div>
              </div>
            </Card>
          )}
        </div>
      )}

      <Card className="p-0 overflow-hidden">
        {videoMeta && !isUploadSource ? (
          <div className="flex flex-col md:flex-row">
            <a
              href={data.youtube_url}
              target="_blank"
              rel="noopener noreferrer"
              className="relative aspect-video w-full shrink-0 bg-zinc-800 md:w-64 group"
            >
              <img
                src={videoMeta.thumbnail}
                alt={videoMeta.title}
                className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                loading="lazy"
              />
              <div className="absolute inset-0 flex items-center justify-center bg-black/20 opacity-0 transition-opacity group-hover:opacity-100">
                <span className="rounded-lg bg-black/70 p-2 text-white">
                  <ExternalLink className="h-4 w-4" />
                </span>
              </div>
              {videoMeta.duration_string && (
                <span className="absolute bottom-1.5 right-1.5 bg-black/80 text-[10px] text-white font-mono px-1.5 py-0.5 rounded">
                  {videoMeta.duration_string}
                </span>
              )}
            </a>
            <div className="flex min-w-0 flex-1 flex-col justify-center gap-2 p-4">
              <div className="flex items-center gap-2">
                <span className="rounded-md border border-red-500/20 bg-red-500/10 px-2 py-0.5 text-[10px] font-medium text-red-300">Source</span>
                <span className="truncate text-[10px] text-zinc-600">{data.youtube_url}</span>
              </div>
              <p className="text-sm font-semibold leading-snug text-zinc-100 line-clamp-2">{videoMeta.title}</p>
              <div className="flex flex-wrap items-center gap-3 text-[11px] text-zinc-500">
                <span className="flex items-center gap-1">
                  <User className="h-3 w-3" />
                  {videoMeta.channel}
                </span>
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {videoMeta.duration_string || formatDuration(videoMeta.duration)}
                </span>
                {videoMeta.view_count && (
                  <span className="flex items-center gap-1">
                    <Eye className="h-3 w-3" />
                    {videoMeta.view_count > 1000000
                      ? `${(videoMeta.view_count / 1000000).toFixed(1)}M`
                      : `${(videoMeta.view_count / 1000).toFixed(0)}K`} views
                  </span>
                )}
              </div>
              {videoMeta.description && (
                <p className="text-[11px] leading-relaxed text-zinc-600 line-clamp-2">{videoMeta.description}</p>
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between gap-3 p-3">
            <div className="flex min-w-0 items-center gap-3">
              <div className={cn("flex h-12 w-16 shrink-0 items-center justify-center rounded-lg border", isUploadSource ? "border-emerald-500/20 bg-emerald-500/[0.04]" : "border-zinc-800 bg-zinc-900")}>
                {isUploadSource ? <FileVideo className="h-5 w-5 text-emerald-400" /> : <Radio className="h-4 w-4 text-zinc-600" />}
              </div>
              <div className="min-w-0">
                <p className="text-[11px] text-zinc-500 mb-0.5">{isUploadSource ? "Upload Video" : "Source"}</p>
                <p className="text-sm text-zinc-300 truncate">{sourceLabel}</p>
              </div>
            </div>
            {!isUploadSource && (
              <a href={data.youtube_url} target="_blank" rel="noopener noreferrer" className="shrink-0 rounded-lg p-2 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300 transition-colors">
                <ExternalLink className="h-4 w-4" />
              </a>
            )}
          </div>
        )}
      </Card>

      {data.clips && data.clips.length > 0 && (
        <Card className="p-0 overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-zinc-800/60 px-4 py-3">
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-zinc-100">Clips</h2>
              <p className="text-[10px] text-zinc-500">
                {data.clips_total} clips · {readyClips} ready · {remainingClips} {remainingLabel}
                {progress?.activeClip && (
                  <span className="ml-1.5 inline-flex items-center gap-1 text-amber-400 font-medium">
                    · Sedang memproses Klip #{progress.activeClip.rank} ({progress.activeClip.stage}{progress.activeClip.eta_seconds ? ` · ~${progress.activeClip.eta_seconds}s` : ""})
                  </span>
                )}
              </p>
            </div>
            <Badge variant="default" size="sm">{data.target_aspect_ratio || "9:16"}</Badge>
          </div>
          {/* Final output always 9:16 — medium phone cards, horizontal scroll */}
          <div className="flex gap-2 overflow-x-auto p-2.5 snap-x mobile-h-scroll">
            {data.clips.map((clip) => (
              <div key={clip.rank} className="shrink-0 w-[min(50vw,160px)] sm:w-[144px] md:w-[160px] snap-start">
                <ClipCard
                  jobId={data.job_id}
                  clip={clip}
                  aspectRatio="9:16"
                  activeClip={progress?.activeClip}
                  clipProgress={progress?.clipsProgress?.[String(clip.rank)]}
                  isJobTerminal={isTerminal}
                />
              </div>
            ))}
          </div>
        </Card>
      )}

      {isTerminal && data.clips_total === 0 && data.status === "completed" && (
        <EmptyState title="No clips generated" description="The pipeline completed but produced no clips" />
      )}
    </div>
  );
}

function MetricTile({ icon, label, value, hint, tone }: { icon: React.ReactNode; label: string; value: string; hint: string; tone: "blue" | "emerald" | "amber" | "zinc" }) {
  const tones = {
    blue: "border-blue-500/20 bg-blue-500/[0.04] text-blue-300",
    emerald: "border-emerald-500/20 bg-emerald-500/[0.04] text-emerald-300",
    amber: "border-amber-500/20 bg-amber-500/[0.04] text-amber-300",
    zinc: "border-zinc-800 bg-zinc-950/40 text-zinc-400",
  };

  return (
    <div className={cn("rounded-lg border p-3", tones[tone])}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</p>
          <p className="mt-1 truncate text-sm font-semibold text-zinc-100">{value}</p>
        </div>
        <span className="rounded-md border border-current/20 bg-current/10 p-2">{icon}</span>
      </div>
      <p className="mt-2 truncate text-[10px] text-zinc-500">{hint}</p>
    </div>
  );
}

function FeaturePill({ icon, label, value, active }: { icon: React.ReactNode; label: string; value: string | boolean; active: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-lg border px-2.5 py-1 text-[11px]",
        active ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : "border-zinc-800 bg-zinc-950/50 text-zinc-500"
      )}
    >
      {icon}
      <span className="text-zinc-500">{label}</span>
      <span className="font-medium capitalize text-current">{String(value)}</span>
    </span>
  );
}

function ClipCard({
  jobId,
  clip,
  aspectRatio,
  activeClip,
  clipProgress,
  isJobTerminal,
}: {
  jobId: string;
  clip: ClipInfo;
  aspectRatio: string;
  activeClip?: { rank: number; total: number; stage: string; eta_seconds: number | null } | null;
  clipProgress?: { status: string; stage: string; eta_seconds: number | null };
  isJobTerminal?: boolean;
}) {
  const toast = useToast();
  const [copied, setCopied] = useState(false);
  const finalUrl = clip.has_final ? jobs.getClipFinalUrl(jobId, clip.rank) : null;
  const thumbUrl = clip.has_thumbnail ? jobs.getClipThumbUrl(jobId, clip.rank) : null;

  const isPortrait = true; // final output always TikTok 9:16
  const hasScore = clip.score !== null && clip.score !== undefined;
  const score = hasScore ? (clip.score! <= 1 ? Math.round(clip.score! * 100) : Math.round(clip.score!)) : null;
  const timeline = `${formatDuration(clip.start)} - ${formatDuration(clip.end)}`;

  const isCurrentActive = activeClip?.rank === clip.rank;
  const isClipProcessing = isCurrentActive || clipProgress?.status === "processing";
  const activeStage = isCurrentActive ? activeClip?.stage : clipProgress?.stage || "Rendering…";
  const activeEta = isCurrentActive ? activeClip?.eta_seconds : clipProgress?.eta_seconds ?? null;

  const handleCopyCaption = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const text = `${clip.hook || `Clip #${clip.rank}`}\n\nSimak pembahasan lengkapnya!\n\n#fyp #viral #trending #reels #shorts #podcast #cliphub`;
    navigator.clipboard?.writeText(text);
    setCopied(true);
    toast.success(`Caption Clip #${clip.rank} disalin!`);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (finalUrl) {
      window.open(finalUrl, "_blank");
    }
  };

  const card = (
    <Card className={cn(
        "p-0 overflow-hidden h-full flex flex-col rounded-md transition-colors",
        clip.has_final
          ? "hover:border-emerald-500/30 hover:bg-zinc-900/80 cursor-pointer"
          : isClipProcessing
          ? "border-amber-500/40 bg-zinc-950/60 shadow-[0_0_12px_rgba(245,158,11,0.08)]"
          : "border-zinc-800/70 bg-zinc-950/45 cursor-not-allowed"
      )}>
        <div className="bg-zinc-950 relative overflow-hidden aspect-[9/16]">
          {finalUrl ? (
            <video
              src={finalUrl}
              poster={thumbUrl || undefined}
              className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
              playsInline
              preload="none"
              muted
            />
          ) : (
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(63,63,70,0.28),_rgba(9,9,11,0.96)_68%)]" />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-transparent to-black/30" />
          <div className="absolute left-1 top-1 flex items-center gap-1">
            <span className="rounded bg-black/80 px-1 py-0.5 text-[8px] font-bold text-white">#{clip.rank}</span>
            {score !== null && <span className="rounded bg-emerald-500/90 px-1 py-0.5 text-[8px] font-bold text-white">{score}</span>}
          </div>
          <div className="absolute right-1 top-1">
            {clip.has_final ? (
              <span className="rounded bg-emerald-500/90 px-1 py-0.5 text-[8px] font-semibold text-white">Ready</span>
            ) : isClipProcessing ? (
              <span className="inline-flex items-center gap-1 rounded border border-amber-500/30 bg-amber-500/20 px-1.5 py-0.5 text-[8px] font-medium text-amber-300 animate-pulse">
                <LoaderCircle className="h-2 w-2 animate-spin text-amber-300" />
                {activeEta !== null && activeEta > 0 ? `~${activeEta}s` : "Active"}
              </span>
            ) : (
              <span className="inline-flex items-center gap-0.5 rounded border border-zinc-700 bg-black/75 px-1 py-0.5 text-[8px] font-medium text-zinc-400">
                {isJobTerminal ? <Lock className="h-2 w-2" /> : `Queue #${clip.rank}`}
              </span>
            )}
          </div>
          {clip.has_final ? (
            <div className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
              <span className="rounded-md bg-black/65 p-1.5 text-white">
                <Play className="h-3 w-3 fill-current" />
              </span>
            </div>
          ) : isClipProcessing ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 px-2 text-center">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-amber-500/40 bg-amber-950/60 text-amber-300 shadow-[0_0_8px_rgba(245,158,11,0.2)]">
                <LoaderCircle className="h-3.5 w-3.5 animate-spin text-amber-300" />
              </span>
              <p className="text-[9px] font-semibold text-amber-200 leading-tight line-clamp-1">{activeStage}</p>
              {activeEta !== null && activeEta > 0 && (
                <p className="text-[8px] font-mono text-amber-400/90 font-medium">Selesai dlm ~{activeEta}s</p>
              )}
            </div>
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 px-2 text-center">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-zinc-800 bg-zinc-900/80 text-zinc-500">
                {isJobTerminal ? <Lock className="h-3 w-3" /> : <Clock className="h-3 w-3" />}
              </span>
              <p className="text-[8px] font-medium text-zinc-500 leading-tight">
                {isJobTerminal ? "Unavailable" : "Menunggu giliran…"}
              </p>
            </div>
          )}
          {clip.duration ? (
            <div className="absolute bottom-1 right-1">
              <span className="rounded bg-black/80 px-1 py-0.5 font-mono text-[8px] text-white">{formatDuration(clip.duration)}</span>
            </div>
          ) : null}
        </div>
        <div className="px-1.5 py-1.5 flex-1 flex flex-col gap-0.5 min-h-0">
          <p className="text-[10px] text-zinc-100 font-medium line-clamp-2 leading-snug">
            {clip.hook || `Clip ${clip.rank}`}
          </p>
          <div className="mt-auto flex items-center justify-between gap-1 text-[8px] text-zinc-500 pt-1">
            <span className="font-mono truncate">{timeline}</span>
            {clip.has_final && (
              <div className="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  onClick={handleCopyCaption}
                  className="rounded p-0.5 hover:bg-zinc-800 text-zinc-400 hover:text-emerald-300 transition-colors"
                  title="Copy caption & hashtags"
                >
                  {copied ? <Check className="h-2.5 w-2.5 text-emerald-400" /> : <Copy className="h-2.5 w-2.5" />}
                </button>
                <button
                  type="button"
                  onClick={handleDownload}
                  className="rounded p-0.5 hover:bg-zinc-800 text-zinc-400 hover:text-emerald-300 transition-colors"
                  title="Download MP4"
                >
                  <Download className="h-2.5 w-2.5" />
                </button>
              </div>
            )}
          </div>
        </div>
      </Card>
  );

  return clip.has_final ? (
    <Link to={`/jobs/${jobId}/clips/${clip.rank}`} className="group block h-full">
      {card}
    </Link>
  ) : (
    <div className="block h-full" aria-disabled="true">
      {card}
    </div>
  );
}
