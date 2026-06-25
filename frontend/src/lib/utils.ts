import { type ClassValue } from "./types";

export function cn(...classes: ClassValue[]): string {
  return classes.filter(Boolean).join(" ");
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

export function formatTimeAgo(dateStr: string | null): string {
  if (!dateStr) return "Unknown";
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (seconds < 60) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString("id-ID", { day: "numeric", month: "short" });
}

export function formatDate(dateStr: string | null): string {
  if (!dateStr) return "-";
  return new Date(dateStr).toLocaleDateString("id-ID", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function extractVideoId(url: string): string | null {
  const patterns = [
    /(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/,
    /youtube\.com\/embed\/([a-zA-Z0-9_-]{11})/,
    /youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})/,
  ];
  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match) return match[1];
  }
  return null;
}

export function getStatusColor(status: string): string {
  const map: Record<string, string> = {
    completed: "text-emerald-400",
    failed: "text-red-400",
    timeout: "text-red-400",
    processing: "text-blue-400",
    downloading: "text-blue-400",
    analyzing: "text-violet-400",
    transcribing: "text-violet-400",
    rendering: "text-amber-400",
    whisper: "text-amber-400",
    queued: "text-zinc-400",
    validating: "text-blue-400",
  };
  return map[status] || "text-zinc-400";
}

export function getStatusBg(status: string): string {
  const map: Record<string, string> = {
    completed: "bg-emerald-500/12 text-emerald-400",
    failed: "bg-red-500/12 text-red-400",
    timeout: "bg-red-500/12 text-red-400",
    processing: "bg-blue-500/12 text-blue-400",
    downloading: "bg-blue-500/12 text-blue-400",
    analyzing: "bg-violet-500/12 text-violet-400",
    transcribing: "bg-violet-500/12 text-violet-400",
    rendering: "bg-amber-500/12 text-amber-400",
    whisper: "bg-amber-500/12 text-amber-400",
    queued: "bg-zinc-500/12 text-zinc-400",
    validating: "bg-blue-500/12 text-blue-400",
  };
  return map[status] || "bg-zinc-500/12 text-zinc-400";
}

export function truncateUrl(url: string, maxLen = 40): string {
  try {
    const u = new URL(url);
    const path = u.pathname + u.search;
    if (path.length > maxLen) return path.slice(0, maxLen) + "...";
    return u.host + path;
  } catch {
    if (url.length > maxLen) return url.slice(0, maxLen) + "...";
    return url;
  }
}
