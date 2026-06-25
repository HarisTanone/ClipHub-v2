import { useState, useEffect, useCallback } from "react";
import { jobs, type JobListResponse, type JobDetailResponse, type JobSummary } from "@/lib/api";

export function useJobList(params?: { status?: string; limit?: number }) {
  const [data, setData] = useState<JobListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await jobs.list(params);
      setData(res);
    } catch (e: any) {
      setError(e.message || "Failed to load jobs");
    } finally {
      setIsLoading(false);
    }
  }, [params?.status, params?.limit]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { data, isLoading, error, refetch: fetch };
}

export function useJobDetail(jobId: string | undefined) {
  const [data, setData] = useState<JobDetailResponse["data"] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!jobId) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await jobs.getDetail(jobId);
      setData(res.data);
    } catch (e: any) {
      setError(e.message || "Failed to load job");
    } finally {
      setIsLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { data, isLoading, error, refetch: fetch };
}

export function useJobStats() {
  const [stats, setStats] = useState({ active: 0, completed: 0, failed: 0, total: 0 });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [all, completed, failed] = await Promise.all([
          jobs.list({ limit: 1 }),
          jobs.list({ status: "completed", limit: 1 }),
          jobs.list({ status: "failed", limit: 1 }),
        ]);
        const total = all.pagination.total;
        const comp = completed.pagination.total;
        const fail = failed.pagination.total;
        setStats({
          total,
          completed: comp,
          failed: fail,
          active: total - comp - fail,
        });
      } catch {
        // silently fail
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, []);

  return { stats, isLoading };
}
