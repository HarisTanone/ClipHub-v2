import { useState, useEffect, useCallback } from "react";
import { Film, Play, Clock, Loader2, CheckCircle2, AlertCircle, Download, RefreshCw, Sparkles } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { API_BASE, getToken } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

interface VideoGenJob {
  job_id: string;
  topic: string;
  status: string;
  progress: number;
  target_duration: number;
  voice: string;
  title: string | null;
  error: string | null;
  output_path: string | null;
  created_at: number;
  completed_at: number | null;
  scenes_count: number;
  estimated_duration: number | null;
}

interface VoiceOption {
  key: string;
  model: string;
}

// ─── API Helpers ──────────────────────────────────────────────────────────────

async function apiGenerate(payload: {
  topic: string;
  target_duration: number;
  voice: string;
  speed: number;
  instructions: string;
}): Promise<VideoGenJob> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/video-generator/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to generate video");
  }
  return res.json();
}

async function apiListJobs(): Promise<VideoGenJob[]> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/video-generator/jobs`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to fetch jobs");
  return res.json();
}

async function apiGetJob(jobId: string): Promise<VideoGenJob> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/video-generator/jobs/${jobId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to fetch job");
  return res.json();
}

async function apiListVoices(): Promise<VoiceOption[]> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/video-generator/voices`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  return res.json();
}

// ─── Status helpers ───────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: typeof Loader2 }> = {
  queued: { label: "Queued", color: "zinc", icon: Clock },
  generating_story: { label: "Generating Story", color: "blue", icon: Sparkles },
  searching_footage: { label: "Searching Footage", color: "blue", icon: Loader2 },
  downloading: { label: "Downloading", color: "blue", icon: Loader2 },
  generating_tts: { label: "Generating Voice", color: "blue", icon: Loader2 },
  assembling: { label: "Assembling", color: "indigo", icon: Loader2 },
  rendering: { label: "Rendering", color: "purple", icon: Loader2 },
  completed: { label: "Completed", color: "emerald", icon: CheckCircle2 },
  failed: { label: "Failed", color: "red", icon: AlertCircle },
};

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] || { label: status, color: "zinc", icon: Clock };
  const Icon = cfg.icon;
  const isActive = !["completed", "failed", "queued"].includes(status);

  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium",
      cfg.color === "emerald" && "bg-emerald-500/10 text-emerald-400",
      cfg.color === "red" && "bg-red-500/10 text-red-400",
      cfg.color === "blue" && "bg-blue-500/10 text-blue-400",
      cfg.color === "indigo" && "bg-indigo-500/10 text-indigo-400",
      cfg.color === "purple" && "bg-purple-500/10 text-purple-400",
      cfg.color === "zinc" && "bg-zinc-500/10 text-zinc-400",
    )}>
      <Icon className={cn("h-3 w-3", isActive && "animate-spin")} />
      {cfg.label}
    </span>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function VideoGeneratorPage() {
  const { user } = useAuth();
  const toast = useToast();

  // Form state
  const [topic, setTopic] = useState("");
  const [targetDuration, setTargetDuration] = useState(65);
  const [voice, setVoice] = useState("");
  const [speed, setSpeed] = useState(1.0);
  const [instructions, setInstructions] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Data state
  const [jobs, setJobs] = useState<VideoGenJob[]>([]);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Polling
  const [pollInterval, setPollInterval] = useState<ReturnType<typeof setInterval> | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      const data = await apiListJobs();
      setJobs(data);
    } catch {
      // silent
    }
  }, []);

  const loadVoices = useCallback(async () => {
    try {
      const data = await apiListVoices();
      setVoices(data);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    Promise.all([loadJobs(), loadVoices()]).finally(() => setIsLoading(false));
  }, [loadJobs, loadVoices]);

  // Poll active jobs
  useEffect(() => {
    const hasActiveJobs = jobs.some(j => !["completed", "failed"].includes(j.status));
    if (hasActiveJobs && !pollInterval) {
      const interval = setInterval(loadJobs, 3000);
      setPollInterval(interval);
    } else if (!hasActiveJobs && pollInterval) {
      clearInterval(pollInterval);
      setPollInterval(null);
    }
    return () => { if (pollInterval) clearInterval(pollInterval); };
  }, [jobs, pollInterval, loadJobs]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) return;

    setIsSubmitting(true);
    try {
      const job = await apiGenerate({
        topic: topic.trim(),
        target_duration: targetDuration,
        voice,
        speed,
        instructions: instructions.trim(),
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
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <AlertCircle className="h-12 w-12 text-zinc-600 mx-auto mb-3" />
          <p className="text-zinc-400 text-sm">This feature is restricted to superadmin users.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="h-9 w-9 rounded-lg bg-purple-600/20 flex items-center justify-center">
          <Film className="h-5 w-5 text-purple-400" />
        </div>
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">AI Video Generator</h1>
          <p className="text-xs text-zinc-500">Topic to video — AI story, footage search, TTS, render</p>
        </div>
      </div>

      {/* Generate Form */}
      <Card className="p-5">
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Topic */}
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">Topic</label>
            <input
              type="text"
              value={topic}
              onChange={e => setTopic(e.target.value)}
              placeholder="e.g. How the Titanic sank in 1912"
              className="w-full rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-purple-500/50"
              required
              maxLength={500}
            />
          </div>

          {/* Row: Duration + Voice + Speed */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Duration (sec)</label>
              <input
                type="number"
                value={targetDuration}
                onChange={e => setTargetDuration(Number(e.target.value))}
                min={50}
                max={90}
                className="w-full rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2.5 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-purple-500/50"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Voice</label>
              <select
                value={voice}
                onChange={e => setVoice(e.target.value)}
                className="w-full rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2.5 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-purple-500/50"
              >
                <option value="">Default (Thalia)</option>
                {voices.map(v => (
                  <option key={v.key} value={v.model}>{v.key} — {v.model}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Speed</label>
              <input
                type="number"
                value={speed}
                onChange={e => setSpeed(Number(e.target.value))}
                min={0.5}
                max={2.0}
                step={0.1}
                className="w-full rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2.5 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-purple-500/50"
              />
            </div>
          </div>

          {/* Instructions */}
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">
              Additional Instructions <span className="text-zinc-600">(optional)</span>
            </label>
            <textarea
              value={instructions}
              onChange={e => setInstructions(e.target.value)}
              placeholder="e.g. Make it dramatic, use suspenseful tone, focus on human stories..."
              rows={2}
              maxLength={1000}
              className="w-full rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-purple-500/50 resize-none"
            />
          </div>

          {/* Submit */}
          <Button
            type="submit"
            disabled={isSubmitting || !topic.trim()}
            className="w-full sm:w-auto"
          >
            {isSubmitting ? (
              <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Generating...</>
            ) : (
              <><Sparkles className="h-4 w-4 mr-2" /> Generate Video</>
            )}
          </Button>
        </form>
      </Card>

      {/* Jobs List */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-300">Generation Jobs</h2>
          <button onClick={loadJobs} className="text-zinc-500 hover:text-zinc-300 transition-colors">
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-6 w-6 text-zinc-600 animate-spin" />
          </div>
        ) : jobs.length === 0 ? (
          <Card className="p-8 text-center">
            <Film className="h-10 w-10 text-zinc-700 mx-auto mb-3" />
            <p className="text-sm text-zinc-500">No videos generated yet. Enter a topic above to get started.</p>
          </Card>
        ) : (
          <div className="space-y-2">
            {jobs.map(job => (
              <Card key={job.job_id} className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <StatusBadge status={job.status} />
                      {job.scenes_count > 0 && (
                        <span className="text-xs text-zinc-600">{job.scenes_count} scenes</span>
                      )}
                    </div>
                    <p className="text-sm font-medium text-zinc-200 truncate">
                      {job.title || job.topic}
                    </p>
                    <p className="text-xs text-zinc-500 mt-0.5">
                      {job.topic} — {job.target_duration}s target
                    </p>
                    {job.error && (
                      <p className="text-xs text-red-400 mt-1 truncate">{job.error}</p>
                    )}
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {/* Progress */}
                    {!["completed", "failed"].includes(job.status) && (
                      <span className="text-xs text-zinc-500 tabular-nums">{job.progress}%</span>
                    )}

                    {/* Download button */}
                    {job.status === "completed" && (
                      <button
                        onClick={() => handleDownload(job.job_id)}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 text-xs font-medium hover:bg-emerald-500/20 transition-colors"
                      >
                        <Download className="h-3.5 w-3.5" />
                        Download
                      </button>
                    )}
                  </div>
                </div>

                {/* Progress bar */}
                {!["completed", "failed"].includes(job.status) && (
                  <div className="mt-3 h-1 rounded-full bg-zinc-800 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-purple-500 transition-all duration-500"
                      style={{ width: `${job.progress}%` }}
                    />
                  </div>
                )}
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
