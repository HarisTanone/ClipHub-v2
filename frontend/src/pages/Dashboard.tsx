import { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { PlusCircle, Activity, CheckCircle, XCircle, Clock, RefreshCw, Inbox, Search, ChevronLeft, ChevronRight, Trash2, SlidersHorizontal, Film, Radio, Sparkles, PlayCircle, FileVideo } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SkeletonRow } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { jobs, system, type JobSummary } from "@/lib/api";
import { formatTimeAgo, truncateUrl, formatDuration, cn } from "@/lib/utils";
import { ModelStatusPanel } from "@/components/ModelStatusPanel";

const PAGE_SIZE = 10;

export function Dashboard() {
  const [jobList, setJobList] = useState<JobSummary[]>([]);
  const [stats, setStats] = useState({ total: 0, active: 0, completed: 0, failed: 0 });
  const [health, setHealth] = useState<{ status: string; version: string; mode: string } | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sourceFilter, setSourceFilter] = useState<"all" | "youtube" | "upload">("all");
  const [page, setPage] = useState(1);

  async function loadData() {
    setIsLoading(true);
    setError(null);
    try {
      const res = await jobs.list({ limit: 200 });
      setJobList(res.data);
      const total = res.data.length;
      const completed = res.data.filter((j) => j.status === "completed").length;
      const failed = res.data.filter((j) => j.status === "failed" || j.status === "timeout").length;
      setStats({ total, active: total - completed - failed, completed, failed });
    } catch (e: any) {
      setError(e.message || "Failed to load");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadData();
    system.health().then(setHealth).catch(() => null);
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, []);

  // Filtered & paginated
  const filtered = useMemo(() => {
    let list = jobList;
    if (statusFilter !== "all") {
      if (statusFilter === "processing") {
        // Match ALL active/in-progress statuses (V1 + V2 pipeline)
        list = list.filter((j) => j.status !== "completed" && j.status !== "failed" && j.status !== "timeout");
      } else {
        list = list.filter((j) => j.status === statusFilter);
      }
    }
    if (sourceFilter !== "all") list = list.filter((j) => (j.source_type || "youtube") === sourceFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((j) =>
        (j.video_title || "").toLowerCase().includes(q) ||
        (j.source_label || "").toLowerCase().includes(q) ||
        j.youtube_url.toLowerCase().includes(q) ||
        j.job_id.toLowerCase().includes(q)
      );
    }
    return list;
  }, [jobList, statusFilter, sourceFilter, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const completionRate = stats.total ? Math.round((stats.completed / stats.total) * 100) : 0;
  const failedRate = stats.total ? Math.round((stats.failed / stats.total) * 100) : 0;
  const activeJobs = jobList.filter((j) => (j.status !== "completed" && j.status !== "failed" && j.status !== "timeout") || (j.active_operations && j.active_operations > 0)).slice(0, 3);

  // Reset page on filter change
  useEffect(() => { setPage(1); }, [search, statusFilter, sourceFilter]);

  // Extract video ID for thumbnail
  function getYouTubeThumb(url: string): string | null {
    const match = url.match(/(?:v=|youtu\.be\/|shorts\/)([a-zA-Z0-9_-]{11})/);
    return match ? `https://i.ytimg.com/vi/${match[1]}/hqdefault.jpg` : null;
  }

  function getSourceLabel(job: JobSummary): string {
    if (job.video_title) return job.video_title;
    if (job.source_label && job.source_label !== job.youtube_url) return job.source_label;
    // Fallback: show "YouTube · VIDEO_ID" instead of raw URL
    const match = job.youtube_url.match(/(?:v=|youtu\.be\/|shorts\/)([a-zA-Z0-9_-]{11})/);
    return match ? `YouTube · ${match[1]}` : truncateUrl(job.youtube_url, 40);
  }

  return (
    <div className="h-full flex flex-col gap-4">
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-3 shrink-0">
        <Card className="p-4 overflow-hidden">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-emerald-500/25 bg-emerald-500/10 text-emerald-300">
                  <Radio className="h-4 w-4" />
                </span>
                <div>
                  <h1 className="text-lg font-semibold text-zinc-100">Clip Pipeline</h1>
                  <p className="text-[11px] text-zinc-500">Monitor jobs, render status, and recent clip output.</p>
                </div>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <HealthPill status={health?.status} mode={health?.mode} />
              <Button variant="ghost" size="xs" onClick={loadData} icon={<RefreshCw className="h-3 w-3" />}>Refresh</Button>
              <Link to="/jobs/new"><Button size="sm" icon={<PlusCircle className="h-3.5 w-3.5" />}>New Job</Button></Link>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard icon={<Activity className="h-4 w-4" />} label="Active" value={stats.active} color="blue" hint={activeJobs.length ? "Running now" : "Queue idle"} />
            <StatCard icon={<CheckCircle className="h-4 w-4" />} label="Completed" value={stats.completed} color="emerald" hint={`${completionRate}% success share`} />
            <StatCard icon={<XCircle className="h-4 w-4" />} label="Failed" value={stats.failed} color="red" hint={`${failedRate}% needs review`} />
            <StatCard icon={<Clock className="h-4 w-4" />} label="Total Jobs" value={stats.total} color="zinc" hint="All tracked jobs" />
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Live Queue</p>
              <p className="mt-1 text-sm font-semibold text-zinc-100">{stats.active} active job{stats.active === 1 ? "" : "s"}</p>
            </div>
            <span className="rounded-lg border border-blue-500/20 bg-blue-500/10 p-2 text-blue-300">
              <Sparkles className="h-4 w-4" />
            </span>
          </div>
          <div className="mt-3 space-y-2">
            {activeJobs.length ? activeJobs.map((job) => (
              <Link key={job.job_id} to={`/jobs/${job.job_id}`} className="block rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2 hover:border-zinc-700">
                <p className="truncate text-[11px] font-medium text-zinc-200">{job.video_title || truncateUrl(job.youtube_url, 42)}</p>
                <div className="mt-1 flex items-center justify-between gap-2">
                  <span className="font-mono text-[9px] text-zinc-600">{job.job_id.replace("job_", "").slice(0, 8)}</span>
                  <Badge variant="status" status={job.status} size="sm" dot>{job.status}</Badge>
                </div>
              </Link>
            )) : (
              <div className="rounded-lg border border-dashed border-zinc-800 py-5 text-center">
                <Film className="mx-auto h-5 w-5 text-zinc-700" />
                <p className="mt-2 text-[11px] text-zinc-500">No active render queue</p>
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Model Status (compact 4-col grid) */}
      <ModelStatusPanel />

      {/* Toolbar */}
      <Card className="p-3 shrink-0">
        <div className="flex items-center gap-3 flex-wrap">
          {/* Search */}
          <div className="relative flex-1 min-w-[240px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search title, URL, or job ID..."
              className="w-full bg-zinc-950/70 border border-zinc-800 rounded-lg pl-9 pr-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50"
            />
          </div>

          <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value as "all" | "youtube" | "upload")} className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-[10px] text-zinc-300 outline-none">
            <option value="all">All sources</option><option value="youtube">YouTube</option><option value="upload">Upload</option>
          </select>

          {/* Status filter */}
          <div className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-950/60 p-1">
            <SlidersHorizontal className="ml-1 h-3.5 w-3.5 text-zinc-600" />
            {["all", "completed", "failed", "processing"].map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setStatusFilter(s === "processing" ? "processing" : s)}
                className={cn(
                  "px-2.5 py-1.5 rounded-md text-[10px] font-medium transition-colors capitalize",
                  statusFilter === s ? "bg-emerald-500/15 text-emerald-300" : "text-zinc-500 hover:bg-zinc-800/70 hover:text-zinc-300"
                )}
              >
                {s}
              </button>
            ))}
          </div>

          <div className="ml-auto text-[10px] text-zinc-500">
            {filtered.length} visible / {jobList.length} total
          </div>
        </div>
      </Card>

      {/* Job list */}
      <Card className="flex-1 p-0 flex flex-col">
        <div className="flex items-center justify-between border-b border-zinc-800/60 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">Jobs</h2>
            <p className="text-[10px] text-zinc-500">Latest jobs are refreshed automatically.</p>
          </div>
          <Badge variant="default" size="sm">{PAGE_SIZE} per page</Badge>
        </div>
        <div className="flex-1 overflow-y-auto min-h-0">
          {isLoading && !jobList.length ? (
            <div className="px-4 py-3 space-y-2">
              {Array.from({ length: 6 }).map((_, i) => <SkeletonRow key={i} />)}
            </div>
          ) : error ? (
            <div className="px-4 py-8 text-center">
              <p className="text-sm text-red-400">{error}</p>
              <Button variant="ghost" size="sm" onClick={loadData} className="mt-2">Retry</Button>
            </div>
          ) : paginated.length === 0 ? (
            <EmptyState
              icon={<Inbox className="h-8 w-8" />}
              title={search ? "No results" : "No jobs yet"}
              description={search ? "Try a different search term" : "Submit a YouTube URL or upload a video to generate clips"}
              action={!search ? <Link to="/jobs/new"><Button size="sm" icon={<PlusCircle className="h-3.5 w-3.5" />}>Create first job</Button></Link> : undefined}
            />
          ) : (
            <div className="grid grid-cols-2 gap-3 p-3 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
              {paginated.map((job) => {
                const isUpload = job.source_type === "upload";
                const thumb = isUpload ? jobs.getSourceThumbUrl(job.job_id) : getYouTubeThumb(job.youtube_url);
                return (
                  <Link
                    key={job.job_id}
                    to={`/jobs/${job.job_id}`}
                    className="group relative flex min-w-0 flex-col overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950/50 hover:border-emerald-500/30 hover:bg-zinc-900/70 transition-colors"
                  >
                    {/* Thumbnail */}
                    <div className="relative aspect-video w-full overflow-hidden bg-zinc-800">
                      {thumb ? (
                        <img src={thumb} alt="" className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" loading="lazy" />
                      ) : isUpload ? (
                        <div className="w-full h-full flex items-center justify-center bg-emerald-500/[0.04]">
                          <FileVideo className="h-4 w-4 text-emerald-400" />
                        </div>
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <Activity className="h-3 w-3 text-zinc-700" />
                        </div>
                      )}
                      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />
                      <PlayCircle className="absolute bottom-1 right-1 h-3.5 w-3.5 text-white/70 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>

                    {/* Info */}
                    <div className="min-w-0 p-3">
                      <p className="text-sm font-medium text-zinc-200 truncate group-hover:text-zinc-100">{getSourceLabel(job)}</p>
                      <div className="flex items-center gap-3 text-[10px] text-zinc-500 mt-1 flex-wrap">
                        <span className={isUpload ? "text-emerald-400" : "text-red-400"}>{isUpload ? "UPLOAD" : "YOUTUBE"}</span>
                        <span className="font-mono">{job.job_id.replace("job_", "").slice(0, 8)}</span>
                        <span>{job.target_aspect_ratio || "9:16"}</span>
                        {job.pipeline_version && <span className={job.pipeline_version === "v2" ? "text-blue-400" : "text-emerald-400"}>{job.pipeline_version.toUpperCase()}</span>}
                        <span>{job.clips_success}/{job.clips_total || 0} clips</span>
                        <span>{formatTimeAgo(job.created_at)}</span>
                      </div>
                    </div>

                    {/* Status + Delete */}
                    <div className="flex flex-wrap items-center gap-1.5 px-3 pb-3">
                      {/* Live progress for active jobs */}
                      {job.status !== "completed" && job.status !== "failed" && job.status !== "timeout" && <JobProgressIndicator jobId={job.job_id} />}
                      {/* Restyle operation indicator */}
                      {job.active_operations ? <span className="inline-flex items-center gap-1 rounded bg-violet-500/15 px-1.5 py-0.5 text-[9px] font-medium text-violet-300"><span className="h-1.5 w-1.5 rounded-full bg-violet-400 animate-pulse" />restyling</span> : null}
                      <Badge variant="status" status={job.status} size="sm" dot>{job.status}</Badge>
                      {(job.status === "completed" || job.status === "failed" || job.status === "timeout") && (
                        <button
                          type="button"
                          onClick={async (e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            if (!confirm(`Delete job "${job.video_title || job.job_id}"?\nThis will remove all clips and files.`)) return;
                            try {
                              await jobs.delete(job.job_id);
                              loadData();
                            } catch (err) {
                              alert("Failed to delete job");
                            }
                          }}
                          className="p-1 rounded text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                          title="Delete job"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-2.5 border-t border-zinc-800/60 shrink-0">
            <span className="text-[10px] text-zinc-500">
              Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page === 1}
                className="p-1 rounded text-zinc-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="text-[11px] text-zinc-400 px-2">{page} / {totalPages}</span>
              <button
                type="button"
                onClick={() => setPage(Math.min(totalPages, page + 1))}
                disabled={page === totalPages}
                className="p-1 rounded text-zinc-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

function StatCard({ icon, label, value, color, hint }: { icon: React.ReactNode; label: string; value: number; color: string; hint?: string }) {
  const colors: Record<string, string> = {
    blue: "border-blue-500/30 bg-blue-500/[0.04] text-blue-400",
    emerald: "border-emerald-500/30 bg-emerald-500/[0.04] text-emerald-400",
    red: "border-red-500/30 bg-red-500/[0.04] text-red-400",
    zinc: "border-zinc-700/70 bg-zinc-900/40 text-zinc-400",
  };
  const c = colors[color] || colors.zinc;
  const [borderColor, bgColor, textColor] = c.split(" ");
  return (
    <Card className={cn("p-3 border rounded-lg", borderColor, bgColor)}>
      <div className="flex items-center justify-between">
        <div className="min-w-0">
          <p className="text-2xl font-bold text-zinc-100">{value}</p>
          <p className="text-[10px] text-zinc-500 mt-0.5">{label}</p>
        </div>
        <span className={cn("rounded-md border border-current/20 bg-current/10 p-2", textColor)}>{icon}</span>
      </div>
      {hint && <p className="mt-2 truncate text-[10px] text-zinc-500">{hint}</p>}
    </Card>
  );
}

function HealthPill({ status, mode }: { status?: string; mode?: string }) {
  const healthy = status === "healthy" || status === "ok";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-lg border px-2.5 py-1 text-[11px] font-medium",
        healthy ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : "border-amber-500/20 bg-amber-500/10 text-amber-300"
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", healthy ? "bg-emerald-400" : "bg-amber-400")} />
      {status || "connecting"}
      {mode && <span className="text-current/60">/ {mode}</span>}
    </span>
  );
}

// ─── Live Progress Indicator ─────────────────────────────────────────────────

const STEP_LABELS: Record<string, string> = {
  validate: "Validating",
  download: "Downloading",
  v2_transcript: "Transcribing",
  transcript: "Transcribing",
  v2_highlight_analysis: "AI Analyzing",
  highlight_analysis: "AI Analyzing",
  gemini_analysis: "AI Analyzing",
  aspect_router: "Configuring",
  trim: "Trimming Clips",
  yolo_reframe: "Smart Framing",
  v2_selective_whisper: "Word Sync",
  whisper: "Word Sync",
  v2_vad_refine: "Refining Cuts",
  highlights: "Processing",
  broll: "B-Roll",
  hook_render: "Rendering Hook",
  subtitle_render: "Subtitles",
  encoding: "Encoding",
  cdn_upload: "Uploading",
  assemble: "Finalizing",
};

function JobProgressIndicator({ jobId }: { jobId: string }) {
  const [progress, setProgress] = useState<{ pct: number; label: string } | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const res = await jobs.getProgress(jobId);
        if (cancelled) return;
        const p = res.data.progress;
        const label = STEP_LABELS[p.step_name || ""] || p.step_label || "Processing";
        setProgress({ pct: p.percentage, label });
      } catch {
        // ignore
      }
    }

    poll();
    const interval = setInterval(poll, 3000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [jobId]);

  if (!progress) return null;

  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1 rounded-full bg-zinc-800 overflow-hidden">
        <div
          className="h-full rounded-full bg-emerald-500 transition-all duration-500"
          style={{ width: `${progress.pct}%` }}
        />
      </div>
      <span className="text-[9px] text-zinc-400 whitespace-nowrap truncate max-w-[80px]">{progress.label} {progress.pct}%</span>
    </div>
  );
}
