import { useState, useEffect, useCallback, useRef } from "react";
import { Film, Play, Clock, Loader2, CheckCircle2, AlertCircle, Download, RefreshCw, Sparkles, X } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { API_BASE, getToken } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

// ─── Types ──────────────────────────────────────────────────────────────────

interface VideoJob {
  job_id: string;
  topic: string;
  status: string;
  progress: number;
  step_label: string;
  target_duration: number;
  voice: string;
  title: string | null;
  error: string | null;
  output_path: string | null;
  created_at: number;
  completed_at: number | null;
  scenes_count: number;
  estimated_duration: number | null;
  thumbnail_url: string | null;
}

interface VoiceOption {
  key: string;
  model: string;
}

// ─── API helpers ─────────────────────────────────────────────────────────────

async function fetchApi<T>(path: string, opts?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(opts?.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ─── Status Badge ────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { icon: typeof CheckCircle2; color: string; label: string }> = {
    completed: { icon: CheckCircle2, color: "text-emerald-400 bg-emerald-500/10", label: "Done" },
    failed: { icon: AlertCircle, color: "text-red-400 bg-red-500/10", label: "Failed" },
    queued: { icon: Clock, color: "text-zinc-400 bg-zinc-500/10", label: "Queued" },
  };

  const processing = !["completed", "failed", "queued"].includes(status);
  const entry = map[status] || (processing
    ? { icon: Loader2, color: "text-purple-400 bg-purple-500/10", label: "Processing" }
    : { icon: Clock, color: "text-zinc-400 bg-zinc-500/10", label: status });

  const Icon = entry.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium", entry.color)}>
      <Icon className={cn("h-3 w-3", processing && status !== "queued" ? "animate-spin" : "")} />
      {entry.label}
    </span>
  );
}

// ─── Progress Bar with Step Label ────────────────────────────────────────────

function ProgressIndicator({ progress, stepLabel }: { progress: number; stepLabel: string }) {
  return (
    <div className="mt-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[11px] text-zinc-400">{stepLabel}</span>
        <span className="text-[11px] text-zinc-500 tabular-nums">{progress}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-purple-500 to-indigo-500 transition-all duration-700 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}

// ─── Video Modal ─────────────────────────────────────────────────────────────

function VideoModal({ job, onClose }: { job: VideoJob; onClose: () => void }) {
  const token = getToken();
  const streamUrl = `${API_BASE}/api/video-generator/jobs/${job.job_id}/stream?token=${token}`;

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm" onClick={onClose}>
      <div className="relative max-w-[360px] w-full mx-4" onClick={e => e.stopPropagation()}>
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute -top-10 right-0 text-zinc-400 hover:text-white transition-colors"
        >
          <X className="h-6 w-6" />
        </button>

        {/* Title */}
        <div className="mb-3">
          <p className="text-sm font-medium text-zinc-200 truncate">{job.title || job.topic}</p>
          <p className="text-xs text-zinc-500">{job.scenes_count} scenes — {job.target_duration}s</p>
        </div>

        {/* Video player (phone frame) */}
        <div className="aspect-[9/16] rounded-xl overflow-hidden bg-black border border-zinc-700 shadow-2xl">
          <video
            src={streamUrl}
            controls
            autoPlay
            playsInline
            className="w-full h-full object-contain"
          />
        </div>
      </div>
    </div>
  );
}

// ─── Video Card (Grid Item) ──────────────────────────────────────────────────

function VideoCard({
  job,
  onPlay,
  onDownload,
}: {
  job: VideoJob;
  onPlay: (job: VideoJob) => void;
  onDownload: (jobId: string) => void;
}) {
  const isProcessing = !["completed", "failed", "queued"].includes(job.status);
  const isCompleted = job.status === "completed";

  return (
    <Card className="overflow-hidden group">
      {/* Thumbnail / Preview area */}
      <div
        className={cn(
          "relative aspect-[9/16] bg-zinc-900 flex items-center justify-center cursor-pointer",
          isCompleted && "hover:brightness-75 transition-all"
        )}
        onClick={() => isCompleted && onPlay(job)}
      >
        {/* Thumbnail image */}
        {job.thumbnail_url ? (
          <img
            src={job.thumbnail_url}
            alt={job.title || job.topic}
            className="w-full h-full object-cover"
          />
        ) : (
          <Film className="h-10 w-10 text-zinc-700" />
        )}

        {/* Play overlay on completed */}
        {isCompleted && (
          <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/40">
            <div className="w-12 h-12 rounded-full bg-white/20 backdrop-blur flex items-center justify-center">
              <Play className="h-6 w-6 text-white ml-0.5" />
            </div>
          </div>
        )}

        {/* Processing overlay */}
        {isProcessing && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/60">
            <Loader2 className="h-8 w-8 text-purple-400 animate-spin mb-2" />
            <span className="text-[11px] text-purple-300 font-medium">{job.step_label}</span>
            <span className="text-[10px] text-zinc-400 mt-0.5">{job.progress}%</span>
          </div>
        )}

        {/* Failed overlay */}
        {job.status === "failed" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/60">
            <AlertCircle className="h-8 w-8 text-red-400 mb-1" />
            <span className="text-[11px] text-red-300">Failed</span>
          </div>
        )}

        {/* Status badge (top-left) */}
        <div className="absolute top-2 left-2">
          <StatusBadge status={job.status} />
        </div>
      </div>

      {/* Info */}
      <div className="p-3">
        <p className="text-xs font-medium text-zinc-200 truncate" title={job.title || job.topic}>
          {job.title || job.topic}
        </p>
        <p className="text-[11px] text-zinc-500 mt-0.5 truncate">{job.topic}</p>

        {/* Progress bar for processing jobs */}
        {isProcessing && (
          <ProgressIndicator progress={job.progress} stepLabel={job.step_label} />
        )}

        {/* Error message */}
        {job.error && (
          <p className="text-[11px] text-red-400 mt-1 truncate" title={job.error}>{job.error}</p>
        )}

        {/* Actions for completed */}
        {isCompleted && (
          <div className="flex items-center gap-2 mt-2">
            <button
              onClick={(e) => { e.stopPropagation(); onPlay(job); }}
              className="flex items-center gap-1 px-2 py-1 rounded-md bg-purple-500/10 text-purple-400 text-[11px] font-medium hover:bg-purple-500/20 transition-colors"
            >
              <Play className="h-3 w-3" /> Watch
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onDownload(job.job_id); }}
              className="flex items-center gap-1 px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-400 text-[11px] font-medium hover:bg-emerald-500/20 transition-colors"
            >
              <Download className="h-3 w-3" /> Download
            </button>
          </div>
        )}
      </div>
    </Card>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export function VideoGeneratorPage() {
  const { user } = useAuth();
  const toast = useToast();

  // Form state
  const [topic, setTopic] = useState("");
  const [targetDuration, setTargetDuration] = useState(65);
  const [instructions, setInstructions] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Jobs
  const [jobs, setJobs] = useState<VideoJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Modal
  const [activeJob, setActiveJob] = useState<VideoJob | null>(null);

  // Polling
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      const data = await fetchApi<VideoJob[]>("/api/video-generator/jobs");
      setJobs(data);
    } catch {
      // ignore
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Poll every 3s if any job is processing
  useEffect(() => {
    loadJobs();

    pollRef.current = setInterval(() => {
      loadJobs();
    }, 3000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [loadJobs]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim() || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const job = await fetchApi<VideoJob>("/api/video-generator/generate", {
        method: "POST",
        body: JSON.stringify({
          topic: topic.trim(),
          target_duration: targetDuration,
          instructions: instructions.trim(),
        }),
      });
      setJobs(prev => [job, ...prev]);
      setTopic("");
      setInstructions("");
      toast.success(`Video generation started: "${job.topic}"`);
    } catch (err: any) {
      toast.error(err.message || "Failed to start generation");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDownload = async (jobId: string) => {
    const token = getToken();
    try {
      const res = await fetch(`${API_BASE}/api/video-generator/jobs/${jobId}/download`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `video_${jobId}.mp4`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      toast.error(err.message || "Download failed");
    }
  };

  // Superuser gate
  if (!user?.is_superadmin) {
    return (
      <div className="flex items-center justify-center h-full">
        <Card className="p-8 text-center max-w-sm">
          <AlertCircle className="h-10 w-10 text-red-400 mx-auto mb-3" />
          <p className="text-sm text-zinc-300">Superadmin access required</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      {/* Header + Form */}
      <Card className="p-5">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-9 h-9 rounded-lg bg-purple-500/10 flex items-center justify-center">
            <Sparkles className="h-5 w-5 text-purple-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-zinc-100">AI Video Generator</h1>
            <p className="text-xs text-zinc-500">Topic to video — AI story, YouTube footage, TTS narration</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="flex gap-3">
            <input
              type="text"
              value={topic}
              onChange={e => setTopic(e.target.value)}
              placeholder="Enter topic: e.g. How black holes destroy stars..."
              maxLength={500}
              className="flex-1 rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-purple-500/50"
            />
            <input
              type="number"
              value={targetDuration}
              onChange={e => setTargetDuration(Number(e.target.value))}
              min={30}
              max={120}
              className="w-20 rounded-lg bg-zinc-900 border border-zinc-800 px-2 py-2.5 text-sm text-zinc-100 text-center focus:outline-none focus:ring-1 focus:ring-purple-500/50"
              title="Duration (seconds)"
            />
          </div>

          <div className="flex gap-3 items-end">
            <textarea
              value={instructions}
              onChange={e => setInstructions(e.target.value)}
              placeholder="Additional instructions (optional): e.g. dramatic tone, focus on visuals..."
              rows={1}
              maxLength={1000}
              className="flex-1 rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-purple-500/50 resize-none"
            />
            <Button type="submit" disabled={isSubmitting || !topic.trim()}>
              {isSubmitting ? (
                <><Loader2 className="h-4 w-4 animate-spin mr-1.5" /> Generating</>
              ) : (
                <><Sparkles className="h-4 w-4 mr-1.5" /> Generate</>
              )}
            </Button>
          </div>
        </form>
      </Card>

      {/* Jobs Grid */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-zinc-300">Generated Videos</h2>
          <button onClick={loadJobs} className="text-zinc-500 hover:text-zinc-300 transition-colors">
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-6 w-6 text-zinc-600 animate-spin" />
          </div>
        ) : jobs.length === 0 ? (
          <Card className="p-12 text-center">
            <Film className="h-10 w-10 text-zinc-700 mx-auto mb-3" />
            <p className="text-sm text-zinc-500">No videos generated yet. Enter a topic above to get started.</p>
          </Card>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {jobs.map(job => (
              <VideoCard
                key={job.job_id}
                job={job}
                onPlay={setActiveJob}
                onDownload={handleDownload}
              />
            ))}
          </div>
        )}
      </div>

      {/* Video Modal */}
      {activeJob && (
        <VideoModal job={activeJob} onClose={() => setActiveJob(null)} />
      )}
    </div>
  );
}
