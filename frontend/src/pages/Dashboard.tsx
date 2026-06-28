import { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { PlusCircle, Activity, CheckCircle, XCircle, Clock, RefreshCw, Inbox, Search, ChevronLeft, ChevronRight, Filter } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SkeletonRow } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { jobs, system, type JobSummary } from "@/lib/api";
import { formatTimeAgo, truncateUrl, formatDuration, cn } from "@/lib/utils";

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
      list = list.filter((j) => j.status === statusFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((j) =>
        (j.video_title || "").toLowerCase().includes(q) ||
        j.youtube_url.toLowerCase().includes(q) ||
        j.job_id.toLowerCase().includes(q)
      );
    }
    return list;
  }, [jobList, statusFilter, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  // Reset page on filter change
  useEffect(() => { setPage(1); }, [search, statusFilter]);

  // Extract video ID for thumbnail
  function getYouTubeThumb(url: string): string | null {
    const match = url.match(/(?:v=|youtu\.be\/|shorts\/)([a-zA-Z0-9_-]{11})/);
    return match ? `https://i.ytimg.com/vi/${match[1]}/default.jpg` : null;
  }

  return (
    <div className="h-full flex flex-col gap-4">
      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 shrink-0">
        <StatCard icon={<Activity className="h-4 w-4" />} label="Active" value={stats.active} color="blue" />
        <StatCard icon={<CheckCircle className="h-4 w-4" />} label="Completed" value={stats.completed} color="emerald" />
        <StatCard icon={<XCircle className="h-4 w-4" />} label="Failed" value={stats.failed} color="red" />
        <StatCard icon={<Clock className="h-4 w-4" />} label="Total Jobs" value={stats.total} color="zinc" />
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap shrink-0">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by video title, URL, or job ID..."
            className="w-full bg-zinc-900 border border-zinc-800 rounded-lg pl-9 pr-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600"
          />
        </div>

        {/* Status filter */}
        <div className="flex items-center gap-1">
          {["all", "completed", "failed", "processing"].map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStatusFilter(s === "processing" ? "processing" : s)}
              className={cn(
                "px-2.5 py-1.5 rounded-lg text-[10px] font-medium border transition-colors capitalize",
                statusFilter === s ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-400" : "border-zinc-800 text-zinc-500 hover:border-zinc-700"
              )}
            >
              {s}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Button variant="ghost" size="xs" onClick={loadData} icon={<RefreshCw className="h-3 w-3" />}>Refresh</Button>
          <Link to="/jobs/new"><Button size="sm" icon={<PlusCircle className="h-3.5 w-3.5" />}>New Job</Button></Link>
        </div>
      </div>

      {/* Job list */}
      <Card className="flex-1 p-0 flex flex-col min-h-0">
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
              description={search ? "Try a different search term" : "Submit a YouTube URL to generate clips"}
              action={!search ? <Link to="/jobs/new"><Button size="sm" icon={<PlusCircle className="h-3.5 w-3.5" />}>Create first job</Button></Link> : undefined}
            />
          ) : (
            <div className="divide-y divide-zinc-800/30">
              {paginated.map((job) => {
                const thumb = getYouTubeThumb(job.youtube_url);
                return (
                  <Link
                    key={job.job_id}
                    to={`/jobs/${job.job_id}`}
                    className="flex items-center gap-3 px-4 py-3 hover:bg-zinc-800/20 transition-colors"
                  >
                    {/* Thumbnail */}
                    <div className="shrink-0 w-16 h-10 rounded overflow-hidden bg-zinc-800">
                      {thumb ? (
                        <img src={thumb} alt="" className="w-full h-full object-cover" loading="lazy" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <Activity className="h-3 w-3 text-zinc-700" />
                        </div>
                      )}
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-zinc-200 truncate">{job.video_title || truncateUrl(job.youtube_url, 60)}</p>
                      <div className="flex items-center gap-3 text-[10px] text-zinc-500 mt-0.5">
                        <span className="font-mono">{job.job_id.replace("job_", "").slice(0, 8)}</span>
                        <span>{job.target_aspect_ratio || "9:16"}</span>
                        {job.pipeline_version && <span className={job.pipeline_version === "v2" ? "text-blue-400" : "text-emerald-400"}>{job.pipeline_version.toUpperCase()}</span>}
                        {job.clips_success > 0 && <span>{job.clips_success}/{job.clips_total} clips</span>}
                        <span>{formatTimeAgo(job.created_at)}</span>
                      </div>
                    </div>

                    {/* Status */}
                    <div className="shrink-0">
                      <Badge variant="status" status={job.status} size="sm" dot>{job.status}</Badge>
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

function StatCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: number; color: string }) {
  const colors: Record<string, string> = {
    blue: "border-blue-500/40 text-blue-400",
    emerald: "border-emerald-500/40 text-emerald-400",
    red: "border-red-500/40 text-red-400",
    zinc: "border-zinc-600/40 text-zinc-400",
  };
  const c = colors[color] || colors.zinc;
  return (
    <Card className={cn("p-3 border", c.split(" ")[0])}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-2xl font-bold text-zinc-100">{value}</p>
          <p className="text-[10px] text-zinc-500 mt-0.5">{label}</p>
        </div>
        <span className={c.split(" ")[1]}>{icon}</span>
      </div>
    </Card>
  );
}
