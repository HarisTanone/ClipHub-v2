import { useState, useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Play, XCircle, ExternalLink, Clock, User, Eye, Sparkles, Layers, Film, Scissors, Radio, CheckCircle, AlertTriangle, Activity, RefreshCw, FileVideo } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ProgressBar, StepProgress } from "@/components/ui/Progress";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import { jobs, preview, type JobDetailResponse, type VideoPreview, type JobResponse, type ClipInfo, API_BASE } from "@/lib/api";
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
  const [data, setData] = useState<JobDetailResponse["data"] | null>(null);
  const [jobData, setJobData] = useState<JobResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [videoMeta, setVideoMeta] = useState<VideoPreview | null>(null);

  const isTerminal = data ? ["completed", "failed", "timeout"].includes(data.status) : false;
  const { progress } = useProgress(jobId, !isTerminal);

  // Check if Remotion was used
  const useRemotion = jobData?.use_remotion || false;
  const remotionFeatures = {
    aiLayer: jobData?.ai_layer_enabled || false,
    threejs: jobData?.threejs_enabled || false,
    quality: jobData?.remotion_quality || "medium",
  };

  async function loadDetail() {
    if (!jobId) return;
    setIsLoading(true);
    try {
      const [detailRes, jobRes] = await Promise.all([
        jobs.getDetail(jobId),
        jobs.get(jobId),
      ]);
      setData(detailRes.data);
      setJobData(jobRes);
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

  if (isLoading && !data) {
    return (
      <div className="space-y-3">
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
  const clipCompletionRate = data.clips_total ? Math.round((data.clips_success / data.clips_total) * 100) : 0;
  const jobShort = (jobId || data.job_id).replace("job_", "").slice(0, 12);
  const stageLabel = progress?.stepLabel || (data.status === "completed" ? "Completed" : isTerminal ? "Stopped" : "Preparing pipeline");
  const createdDate = data.created_at ? formatDate(data.created_at).split(",")[0] : "-";
  const isUploadSource = data.source_type === "upload";
  const sourceLabel = data.source_label || data.youtube_url;

  return (
    <div className="space-y-3">
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
            <Button variant="ghost" size="xs" onClick={loadDetail} icon={<RefreshCw className="h-3 w-3" />}>Refresh</Button>
            {!isTerminal && (
              <Button variant="danger" size="sm" onClick={handleCancel}>Cancel</Button>
            )}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <MetricTile icon={<Activity className="h-4 w-4" />} label="Progress" value={`${percentage}%`} hint={stageLabel} tone="blue" />
          <MetricTile icon={<Scissors className="h-4 w-4" />} label="Clips" value={`${data.clips_success}/${data.clips_total}`} hint={`${readyClips} ready, ${clipCompletionRate}% complete`} tone="emerald" />
          <MetricTile icon={<Clock className="h-4 w-4" />} label="Duration" value={data.video_duration ? formatDuration(data.video_duration) : "-"} hint="Source length" tone="amber" />
          <MetricTile icon={<Film className="h-4 w-4" />} label="Output" value={data.target_aspect_ratio || "9:16"} hint={data.style_preset || "Custom style"} tone="zinc" />
        </div>

        <div className="mt-4 flex flex-wrap gap-2 border-t border-zinc-800/60 pt-3">
          <FeaturePill icon={<Sparkles className="h-3.5 w-3.5" />} label="Remotion" value={useRemotion ? "On" : "Off"} active={useRemotion} />
          <FeaturePill icon={<Sparkles className="h-3.5 w-3.5" />} label="AI Layer" value={remotionFeatures.aiLayer ? "On" : "Off"} active={remotionFeatures.aiLayer} />
          <FeaturePill icon={<Layers className="h-3.5 w-3.5" />} label="3D Layer" value={remotionFeatures.threejs ? "On" : "Off"} active={remotionFeatures.threejs} />
          <FeaturePill icon={<CheckCircle className="h-3.5 w-3.5" />} label="Quality" value={remotionFeatures.quality} active />
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
        <Card className="p-4 border-red-500/20 bg-red-950/20">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
            <p className="text-sm text-red-300">{data.error_message}</p>
          </div>
        </Card>
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
              <p className="text-[10px] text-zinc-500">{data.clips_success}/{data.clips_total} generated, {readyClips} final renders ready</p>
            </div>
            <Badge variant="default" size="sm">{data.target_aspect_ratio || "9:16"}</Badge>
          </div>
          {(data.target_aspect_ratio || "9:16") === "9:16" ? (
            /* 9:16 portrait — horizontal scroll row */
            <div className="flex gap-3 overflow-x-auto p-3 snap-x">
              {data.clips.map((clip) => (
                <div key={clip.rank} className="shrink-0 w-[220px] snap-start">
                  <ClipCard jobId={data.job_id} clip={clip} aspectRatio="9:16" />
                </div>
              ))}
            </div>
          ) : (
            /* 16:9 or 1:1 — grid */
            <div className="grid grid-cols-1 gap-3 p-3 lg:grid-cols-2">
              {data.clips.map((clip) => (
                <ClipCard key={clip.rank} jobId={data.job_id} clip={clip} aspectRatio={data.target_aspect_ratio || "16:9"} />
              ))}
            </div>
          )}
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

function ClipCard({ jobId, clip, aspectRatio }: { jobId: string; clip: ClipInfo; aspectRatio: string }) {
  const finalUrl = clip.has_final ? jobs.getClipFinalUrl(jobId, clip.rank) : null;
  const thumbUrl = clip.has_thumbnail ? jobs.getClipThumbUrl(jobId, clip.rank) : null;
  const rawUrl = `${API_BASE}/api/jobs/${jobId}/clips/${clip.rank}/raw`;

  const isPortrait = aspectRatio === "9:16";
  const hasScore = clip.score !== null && clip.score !== undefined;
  const score = hasScore ? (clip.score! <= 1 ? Math.round(clip.score! * 100) : Math.round(clip.score!)) : null;
  const timeline = `${formatDuration(clip.start)} - ${formatDuration(clip.end)}`;

  return (
    <Link to={`/jobs/${jobId}/clips/${clip.rank}`} className="group block h-full">
      <Card className="p-0 overflow-hidden h-full flex flex-col rounded-lg hover:border-emerald-500/30 hover:bg-zinc-900/80 transition-colors cursor-pointer">
        <div className={cn(
          "bg-zinc-950 relative overflow-hidden",
          isPortrait ? "aspect-[9/16]" : aspectRatio === "1:1" ? "aspect-square" : "aspect-video"
        )}>
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
            thumbUrl ? (
              <img src={thumbUrl} alt={`Clip ${clip.rank}`} className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" loading="lazy" />
            ) : (
              <video
                src={rawUrl}
                className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                playsInline
                preload="metadata"
                muted
              />
            )
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-black/35" />
          <div className="absolute left-2 top-2 flex items-center gap-1.5">
            <span className="rounded bg-black/80 px-1.5 py-0.5 text-[9px] font-bold text-white">#{clip.rank}</span>
            {score !== null && <span className="rounded bg-emerald-500/90 px-1.5 py-0.5 text-[9px] font-bold text-white">{score}</span>}
          </div>
          {clip.has_final && (
            <div className="absolute right-2 top-2">
              <Badge variant="success" size="sm">Ready</Badge>
            </div>
          )}
          <div className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
            <span className="rounded-lg bg-black/65 p-2 text-white">
              <Play className="h-4 w-4 fill-current" />
            </span>
          </div>
          {clip.duration && (
            <div className="absolute bottom-2 right-2">
              <span className="rounded bg-black/80 px-1.5 py-0.5 font-mono text-[9px] text-white">{formatDuration(clip.duration)}</span>
            </div>
          )}
        </div>
        <div className="p-3 flex-1 flex flex-col gap-2">
          <p className="text-[12px] text-zinc-100 font-semibold line-clamp-2 leading-snug">
            {clip.hook || `Clip ${clip.rank}`}
          </p>
          {clip.reason && <p className="text-[10px] text-zinc-600 line-clamp-2 leading-relaxed">{clip.reason}</p>}
          <div className="mt-auto flex flex-wrap items-center gap-2 text-[10px] text-zinc-500">
            <span className="font-mono">{timeline}</span>
            {clip.has_words && <span>{clip.word_count} words</span>}
            {!clip.has_final && <span className="text-amber-400">rendering</span>}
          </div>
        </div>
      </Card>
    </Link>
  );
}
