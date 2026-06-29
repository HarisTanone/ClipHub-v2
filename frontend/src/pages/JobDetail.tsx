import { useState, useEffect } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Play, Download, RotateCcw, XCircle, ExternalLink, Clock, User, Eye, Sparkles, Layers } from "lucide-react";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ProgressBar, StepProgress } from "@/components/ui/Progress";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import { jobs, preview, type JobDetailResponse, type VideoPreview, type JobResponse, API_BASE } from "@/lib/api";
import { useProgress } from "@/hooks/useProgress";
import { formatDuration, formatDate, cn } from "@/lib/utils";

const PIPELINE_STEPS = [
  { name: "validate", label: "Validating URL" },
  { name: "download", label: "Downloading Video" },
  { name: "transcript", label: "Transcribing Audio" },
  { name: "gemini", label: "AI Analyzing Highlights" },
  { name: "prepare", label: "Preparing Clips" },
  { name: "trim", label: "Trimming Clips" },
  { name: "whisper", label: "Syncing Words" },
  { name: "highlights", label: "Processing Highlights" },
  { name: "reframe", label: "Smart Framing (YOLO)" },
  { name: "visual_overlay", label: "Rendering Hook & Subtitle" },
  { name: "thumbnail", label: "Generating Thumbnails" },
  { name: "finalize", label: "Finalizing" },
  { name: "cdn_upload", label: "Uploading" },
  { name: "assemble", label: "Assembling Output" },
];

export function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
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
      // Fetch YouTube metadata for the source URL
      if (detailRes.data.youtube_url && !videoMeta) {
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

  const currentStep = progress?.currentStep || (isTerminal && data.status === "completed" ? 14 : 0);
  const percentage = progress?.percentage || (data.status === "completed" ? 100 : 0);

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/" className="rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 transition-colors shrink-0">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-semibold text-zinc-100 truncate">Job Detail</h1>
              <Badge variant="status" status={data.status} dot>{data.status}</Badge>
            </div>
            <p className="text-[11px] text-zinc-500 font-mono truncate">{jobId}</p>
          </div>
        </div>
        {!isTerminal && (
          <Button variant="danger" size="sm" onClick={handleCancel}>Cancel</Button>
        )}
      </div>

      {/* Meta row */}
      <Card className="p-3">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
          <MetaStat label="Aspect" value={data.target_aspect_ratio || "9:16"} />
          <MetaStat label="Duration" value={data.video_duration ? formatDuration(data.video_duration) : "-"} />
          <MetaStat label="Clips" value={`${data.clips_success}/${data.clips_total}`} />
          <MetaStat label="Created" value={formatDate(data.created_at).split(",")[0] || "-"} />
        </div>
        {/* Remotion status indicator */}
        {useRemotion && (
          <div className="mt-3 pt-3 border-t border-zinc-800/60 flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-1.5 text-xs">
              <Sparkles className="h-3.5 w-3.5 text-purple-400" />
              <span className="text-zinc-400">Remotion</span>
              <Badge variant="success" size="sm">ON</Badge>
            </div>
            {remotionFeatures.aiLayer && (
              <div className="flex items-center gap-1.5 text-xs">
                <Sparkles className="h-3.5 w-3.5 text-amber-400" />
                <span className="text-zinc-400">AI Layer</span>
              </div>
            )}
            <div className="flex items-center gap-1.5 text-xs">
              <span className="text-zinc-500">Quality:</span>
              <span className="text-zinc-300 capitalize">{remotionFeatures.quality}</span>
            </div>
          </div>
        )}
      </Card>

      {/* Progress */}
      {!isTerminal && (
        <Card className="p-4">
          <StepProgress steps={PIPELINE_STEPS} currentStep={currentStep} />
          <ProgressBar value={percentage} className="mt-3" showValue />
        </Card>
      )}

      {/* Error message */}
      {data.error_message && (
        <Card className="p-4 border-red-500/20 bg-red-950/20">
          <p className="text-sm text-red-300">{data.error_message}</p>
        </Card>
      )}

      {/* Source - YouTube metadata */}
      <Card className="p-0 overflow-hidden">
        {videoMeta ? (
          <div className="flex gap-0">
            {/* Thumbnail */}
            <a
              href={data.youtube_url}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 w-44 h-24 bg-zinc-800 relative group"
            >
              <img
                src={videoMeta.thumbnail}
                alt={videoMeta.title}
                className="w-full h-full object-cover"
                loading="lazy"
              />
              <div className="absolute inset-0 bg-black/30 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                <ExternalLink className="h-4 w-4 text-white" />
              </div>
              {videoMeta.duration_string && (
                <span className="absolute bottom-1.5 right-1.5 bg-black/80 text-[10px] text-white font-mono px-1.5 py-0.5 rounded">
                  {videoMeta.duration_string}
                </span>
              )}
            </a>
            {/* Info */}
            <div className="flex-1 min-w-0 p-3 flex flex-col justify-center gap-1.5">
              <p className="text-sm text-zinc-200 font-medium line-clamp-2 leading-snug">{videoMeta.title}</p>
              <div className="flex items-center gap-3 text-[11px] text-zinc-500 flex-wrap">
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
                <p className="text-[10px] text-zinc-600 line-clamp-1">{videoMeta.description}</p>
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between gap-3 p-3">
            <div className="min-w-0">
              <p className="text-[11px] text-zinc-500 mb-0.5">Source</p>
              <p className="text-sm text-zinc-300 truncate">{data.youtube_url}</p>
            </div>
            <a href={data.youtube_url} target="_blank" rel="noopener noreferrer" className="shrink-0 rounded-lg p-2 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300 transition-colors">
              <ExternalLink className="h-4 w-4" />
            </a>
          </div>
        )}
      </Card>

      {/* Clips */}
      {data.clips && data.clips.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[13px] font-semibold text-zinc-200">
              Clips ({data.clips_success}/{data.clips_total})
            </h2>
          </div>
          {(data.target_aspect_ratio || "9:16") === "9:16" ? (
            /* 9:16 portrait — horizontal scroll row */
            <div className="flex gap-3 overflow-x-auto pb-3 -mx-1 px-1 snap-x">
              {data.clips.map((clip) => (
                <div key={clip.rank} className="shrink-0 w-[220px] snap-start">
                  <ClipCard jobId={data.job_id} clip={clip} aspectRatio="9:16" />
                </div>
              ))}
            </div>
          ) : (
            /* 16:9 or 1:1 — grid */
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {data.clips.map((clip) => (
                <ClipCard key={clip.rank} jobId={data.job_id} clip={clip} aspectRatio={data.target_aspect_ratio || "16:9"} />
              ))}
            </div>
          )}
        </div>
      )}

      {isTerminal && data.clips_total === 0 && data.status === "completed" && (
        <EmptyState title="No clips generated" description="The pipeline completed but produced no clips" />
      )}
    </div>
  );
}

function MetaStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</p>
      <p className="text-sm font-medium text-zinc-200 mt-0.5">{value}</p>
    </div>
  );
}

function ClipCard({ jobId, clip, aspectRatio }: { jobId: string; clip: any; aspectRatio: string }) {
  const finalUrl = clip.has_final ? jobs.getClipFinalUrl(jobId, clip.rank) : null;
  const thumbUrl = clip.has_thumbnail ? jobs.getClipThumbUrl(jobId, clip.rank) : null;
  const rawUrl = `${API_BASE}/api/jobs/${jobId}/clips/${clip.rank}/raw`;

  const isPortrait = aspectRatio === "9:16";

  return (
    <Link to={`/jobs/${jobId}/clips/${clip.rank}`} className="block h-full">
      <Card className="p-0 overflow-hidden h-full flex flex-col hover:border-zinc-700 transition-colors cursor-pointer">
        <div className={cn(
          "bg-zinc-950 relative overflow-hidden",
          isPortrait ? "aspect-[9/16]" : aspectRatio === "1:1" ? "aspect-square" : "aspect-video"
        )}>
          {finalUrl ? (
            <video
              src={finalUrl}
              poster={thumbUrl || undefined}
              className="w-full h-full object-cover"
              controls
              playsInline
              preload="none"
            />
          ) : (
            /* No final — show thumbnail, or video frame from raw, or placeholder */
            thumbUrl ? (
              <img src={thumbUrl} alt={`Clip ${clip.rank}`} className="w-full h-full object-cover" loading="lazy" />
            ) : (
              <video
                src={rawUrl}
                className="w-full h-full object-cover"
                playsInline
                preload="metadata"
                muted
              />
            )
          )}
          {/* Badges */}
          <div className="absolute top-1.5 left-1.5">
            <span className="bg-black/80 text-[9px] text-white font-bold px-1.5 py-0.5 rounded">#{clip.rank}</span>
          </div>
          {clip.has_final && (
            <div className="absolute top-1.5 right-1.5">
              <Badge variant="success" size="sm">Ready</Badge>
            </div>
          )}
          {clip.duration && (
            <div className="absolute bottom-1.5 right-1.5">
              <span className="bg-black/80 text-[9px] text-white font-mono px-1.5 py-0.5 rounded">{formatDuration(clip.duration)}</span>
            </div>
          )}
        </div>
        {/* Info */}
        <div className="p-2.5 flex-1 flex flex-col justify-between gap-1">
          {clip.hook && <p className="text-[11px] text-zinc-200 font-medium line-clamp-2 leading-snug">{clip.hook}</p>}
          <div className="flex items-center justify-between mt-auto">
            {clip.score && <span className="text-[9px] text-zinc-500">Score: {clip.score}</span>}
          </div>
        </div>
      </Card>
    </Link>
  );
}
