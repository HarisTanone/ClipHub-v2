import { useState, useEffect, useRef, useCallback } from "react";
import { jobs, type ProgressResponse } from "@/lib/api";

interface ProgressState {
  status: string;
  currentStep: number;
  totalSteps: number;
  percentage: number;
  stepLabel: string | null;
  isTerminal: boolean;
  error: string | null;
  clipsAvailable: number[];
  clipsTotal: number;
  eta: ProgressResponse["data"]["eta"];
}

export function useProgress(jobId: string | undefined, enabled = true) {
  const [progress, setProgress] = useState<ProgressState | null>(null);
  const intervalRef = useRef<number | null>(null);

  const poll = useCallback(async () => {
    if (!jobId) return;
    try {
      const res = await jobs.getProgress(jobId);
      const d = res.data;
      setProgress((prev) => {
        const newPercentage = d.progress.percentage;
        // Never go backwards unless terminal
        if (prev && !d.is_terminal && newPercentage < prev.percentage && prev.percentage > 10) {
          return prev;
        }
        return {
          status: d.status,
          currentStep: d.progress.current_step,
          totalSteps: d.progress.total_steps,
          percentage: newPercentage,
          stepLabel: d.progress.step_label,
          isTerminal: d.is_terminal,
          error: d.error,
          clipsAvailable: d.clips.available,
          clipsTotal: d.clips.total,
          eta: d.eta,
        };
      });

      if (d.is_terminal && intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    } catch {
      // silent
    }
  }, [jobId]);

  useEffect(() => {
    if (!jobId || !enabled) return;

    poll();
    intervalRef.current = window.setInterval(poll, 2000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [jobId, enabled, poll]);

  return { progress, refetch: poll };
}

export function useSSEProgress(jobId: string | undefined, enabled = true) {
  const [events, setEvents] = useState<any[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId || !enabled) return;

    const url = jobs.getProgressSSEUrl(jobId);
    const source = new EventSource(url);
    sourceRef.current = source;

    source.onopen = () => setIsConnected(true);

    source.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setEvents((prev) => [...prev, data]);
      } catch {
        // ignore malformed events
      }
    };

    source.onerror = () => {
      setIsConnected(false);
      source.close();
    };

    return () => {
      source.close();
      sourceRef.current = null;
      setIsConnected(false);
    };
  }, [jobId, enabled]);

  return { events, isConnected };
}
