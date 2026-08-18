import { useCallback, useEffect, useRef, useState } from "react";
import {
  Clock,
  Film,
  GripHorizontal,
  Play,
  Pause,
  RotateCcw,
  Scissors,
  Plus,
  Trash2,
  Edit3,
  FastForward,
  Rewind,
  Sparkles,
  HelpCircle,
  Shield,
  Copy,
  Heart,
  MessageSquare,
  Share2,
  Music,
  X,
  BookmarkPlus,
  ArrowRightToLine,
  ArrowLeftToLine,
  Sliders,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import type { AnalyzeClipCandidate } from "@/lib/api";

export interface EditableClip extends AnalyzeClipCandidate {
  /** Original AI timestamps (for reset) */
  ai_start: number;
  ai_end: number;
  /** Whether user has modified this clip */
  modified: boolean;
  /** Whether this clip was manually added (not from AI) */
  manual?: boolean;
}

interface ClipTimelineEditorProps {
  clips: EditableClip[];
  videoDuration: number;
  videoSrc: string;
  onClipsChange: (clips: EditableClip[]) => void;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatTimePrecise(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1);
  return `${m}:${parseFloat(s) < 10 ? "0" : ""}${s}`;
}

function parseTimeToSeconds(input: string): number | null {
  const trimmed = input.trim().replace(",", ".");
  if (!trimmed) return null;
  if (trimmed.includes(":")) {
    const parts = trimmed.split(":").map(Number);
    if (parts.some(isNaN)) return null;
    if (parts.length === 2) {
      return parts[0] * 60 + parts[1];
    } else if (parts.length === 3) {
      return parts[0] * 3600 + parts[1] * 60 + parts[2];
    }
  }
  const val = parseFloat(trimmed);
  return isNaN(val) ? null : val;
}

export function ClipTimelineEditor({
  clips,
  videoDuration,
  videoSrc,
  onClipsChange,
}: ClipTimelineEditorProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [hoverTime, setHoverTime] = useState<number | null>(null);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);
  const [showSafeZone, setShowSafeZone] = useState<boolean>(false);
  const [showShortcutsModal, setShowShortcutsModal] = useState<boolean>(false);
  const [activeClipIndex, setActiveClipIndex] = useState(0);
  const [startInputText, setStartInputText] = useState("");
  const [endInputText, setEndInputText] = useState("");

  const [dragging, setDragging] = useState<{
    clipIndex: number;
    handle: "start" | "end" | "move";
    initialTime: number;
    initialStart: number;
    initialEnd: number;
  } | null>(null);

  const activeClip = clips[activeClipIndex] || null;

  // Sync input text when active clip changes or timestamps update
  useEffect(() => {
    if (activeClip) {
      setStartInputText(formatTimePrecise(activeClip.start));
      setEndInputText(formatTimePrecise(activeClip.end));
    }
  }, [activeClip?.start, activeClip?.end, activeClipIndex]);

  // Sync video time display
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onTimeUpdate = () => setCurrentTime(video.currentTime);
    video.addEventListener("timeupdate", onTimeUpdate);
    return () => video.removeEventListener("timeupdate", onTimeUpdate);
  }, []);

  // Play/pause toggle
  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      video.play();
      setIsPlaying(true);
    } else {
      video.pause();
      setIsPlaying(false);
    }
  }, []);

  // Seek relative
  const seekRelative = useCallback((delta: number) => {
    const video = videoRef.current;
    if (!video) return;
    const target = Math.max(0, Math.min(videoDuration, video.currentTime + delta));
    video.currentTime = target;
    setCurrentTime(target);
  }, [videoDuration]);

  // Change playback speed
  const changeSpeed = useCallback((speed: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.playbackRate = speed;
    setPlaybackSpeed(speed);
  }, []);

  // Seek to specific clip
  const seekToClip = useCallback((index: number) => {
    const video = videoRef.current;
    if (!video || !clips[index]) return;
    setActiveClipIndex(index);
    video.currentTime = clips[index].start;
    setCurrentTime(clips[index].start);
  }, [clips]);

  // Jump to clip start/end
  const jumpToActiveStart = useCallback(() => {
    if (!activeClip || !videoRef.current) return;
    videoRef.current.currentTime = activeClip.start;
    setCurrentTime(activeClip.start);
  }, [activeClip]);

  const jumpToActiveEnd = useCallback(() => {
    if (!activeClip || !videoRef.current) return;
    videoRef.current.currentTime = activeClip.end;
    setCurrentTime(activeClip.end);
  }, [activeClip]);

  // Preview active clip (play from start to end)
  const previewClip = useCallback((index: number) => {
    const video = videoRef.current;
    if (!video || !clips[index]) return;
    setActiveClipIndex(index);
    video.currentTime = clips[index].start;
    video.play();
    setIsPlaying(true);

    const checkEnd = () => {
      if (video.currentTime >= clips[index].end) {
        video.pause();
        setIsPlaying(false);
        video.removeEventListener("timeupdate", checkEnd);
      }
    };
    video.addEventListener("timeupdate", checkEnd);
  }, [clips]);

  // Reset clip to AI original
  const resetClip = useCallback((index: number) => {
    const updated = [...clips];
    updated[index] = {
      ...updated[index],
      start: updated[index].ai_start,
      end: updated[index].ai_end,
      duration: Math.round((updated[index].ai_end - updated[index].ai_start) * 100) / 100,
      modified: false,
    };
    onClipsChange(updated);
  }, [clips, onClipsChange]);

  // Reset all clips
  const resetAll = useCallback(() => {
    const updated = clips.map((c) => ({
      ...c,
      start: c.ai_start,
      end: c.ai_end,
      duration: Math.round((c.ai_end - c.ai_start) * 100) / 100,
      modified: false,
    }));
    onClipsChange(updated);
  }, [clips, onClipsChange]);

  // Add new clip at current playhead position or target time
  const addClipAtTime = useCallback((targetTime?: number, defaultLen: number = 45) => {
    const start = Math.max(0, targetTime !== undefined ? targetTime : currentTime);
    const end = Math.min(videoDuration, start + defaultLen);
    if (end - start < 5) return;

    const maxRank = clips.length > 0 ? Math.max(...clips.map((c) => c.rank)) : 0;
    const newClip: EditableClip = {
      rank: maxRank + 1,
      start: Math.round(start * 10) / 10,
      end: Math.round(end * 10) / 10,
      duration: Math.round((end - start) * 100) / 100,
      score: null,
      hook: `Klip #${maxRank + 1}`,
      reason: "Dibuat manual oleh pengguna",
      content_type: "custom",
      speaker_energy: "medium",
      ai_start: start,
      ai_end: end,
      modified: false,
      manual: true,
    };

    const updated = [...clips, newClip];
    onClipsChange(updated);
    setActiveClipIndex(updated.length - 1);
    if (videoRef.current) {
      videoRef.current.currentTime = start;
      setCurrentTime(start);
    }
  }, [clips, currentTime, videoDuration, onClipsChange]);

  // Duplicate clip
  const duplicateClip = useCallback((index: number) => {
    const source = clips[index];
    if (!source) return;
    const len = source.end - source.start;
    const newStart = Math.min(videoDuration - 5, source.end + 1);
    const newEnd = Math.min(videoDuration, newStart + len);

    const maxRank = clips.length > 0 ? Math.max(...clips.map((c) => c.rank)) : 0;
    const newClip: EditableClip = {
      ...source,
      rank: maxRank + 1,
      start: Math.round(newStart * 10) / 10,
      end: Math.round(newEnd * 10) / 10,
      duration: Math.round((newEnd - newStart) * 100) / 100,
      hook: `${source.hook || "Klip"} (Salinan)`,
      ai_start: newStart,
      ai_end: newEnd,
      modified: true,
      manual: true,
    };

    const updated = [...clips, newClip];
    onClipsChange(updated);
    setActiveClipIndex(updated.length - 1);
  }, [clips, videoDuration, onClipsChange]);

  // Delete clip
  const deleteClip = useCallback((index: number) => {
    if (clips.length <= 1) return;
    const updated = clips.filter((_, i) => i !== index);
    updated.forEach((c, i) => { c.rank = i + 1; });
    onClipsChange(updated);
    setActiveClipIndex(Math.min(activeClipIndex, updated.length - 1));
  }, [clips, activeClipIndex, onClipsChange]);

  // Set preset duration for active clip
  const setExactDuration = useCallback((desiredDuration: number) => {
    if (!activeClip) return;
    const updated = [...clips];
    const clip = updated[activeClipIndex];
    const newEnd = Math.min(videoDuration, clip.start + desiredDuration);
    clip.end = Math.round(newEnd * 10) / 10;
    clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
    clip.modified = clip.start !== clip.ai_start || clip.end !== clip.ai_end;
    onClipsChange(updated);
  }, [activeClip, activeClipIndex, clips, videoDuration, onClipsChange]);

  // Nudge timing helpers
  const nudgeStart = useCallback((delta: number) => {
    if (!activeClip) return;
    const updated = [...clips];
    const clip = updated[activeClipIndex];
    const minDuration = 5;
    const newStart = Math.max(0, Math.min(clip.start + delta, clip.end - minDuration));
    clip.start = Math.round(newStart * 10) / 10;
    clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
    clip.modified = clip.start !== clip.ai_start || clip.end !== clip.ai_end;
    onClipsChange(updated);
    if (videoRef.current) videoRef.current.currentTime = clip.start;
  }, [activeClip, activeClipIndex, clips, onClipsChange]);

  const nudgeEnd = useCallback((delta: number) => {
    if (!activeClip) return;
    const updated = [...clips];
    const clip = updated[activeClipIndex];
    const minDuration = 5;
    const newEnd = Math.min(videoDuration, Math.max(clip.end + delta, clip.start + minDuration));
    clip.end = Math.round(newEnd * 10) / 10;
    clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
    clip.modified = clip.start !== clip.ai_start || clip.end !== clip.ai_end;
    onClipsChange(updated);
    if (videoRef.current) videoRef.current.currentTime = clip.end;
  }, [activeClip, activeClipIndex, clips, videoDuration, onClipsChange]);

  // Set start / end to current playhead
  const setStartToPlayhead = useCallback(() => {
    if (!activeClip) return;
    const updated = [...clips];
    const clip = updated[activeClipIndex];
    const minDuration = 5;
    if (currentTime >= clip.end - minDuration) {
      // If current playhead is past end, push end forward
      clip.start = Math.round(currentTime * 10) / 10;
      clip.end = Math.min(videoDuration, clip.start + 30);
    } else {
      clip.start = Math.round(currentTime * 10) / 10;
    }
    clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
    clip.modified = clip.start !== clip.ai_start || clip.end !== clip.ai_end;
    onClipsChange(updated);
  }, [activeClip, activeClipIndex, clips, currentTime, videoDuration, onClipsChange]);

  const setEndToPlayhead = useCallback(() => {
    if (!activeClip) return;
    const updated = [...clips];
    const clip = updated[activeClipIndex];
    const minDuration = 5;
    if (currentTime <= clip.start + minDuration) {
      // If current playhead is before start, pull start backward
      clip.end = Math.round(Math.min(videoDuration, currentTime) * 10) / 10;
      clip.start = Math.max(0, clip.end - 30);
    } else {
      clip.end = Math.round(Math.min(videoDuration, currentTime) * 10) / 10;
    }
    clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
    clip.modified = clip.start !== clip.ai_start || clip.end !== clip.ai_end;
    onClipsChange(updated);
  }, [activeClip, activeClipIndex, clips, currentTime, videoDuration, onClipsChange]);

  // Update hook title
  const updateHookTitle = useCallback((text: string) => {
    if (!activeClip) return;
    const updated = [...clips];
    updated[activeClipIndex].hook = text;
    updated[activeClipIndex].modified = true;
    onClipsChange(updated);
  }, [activeClip, activeClipIndex, clips, onClipsChange]);

  // Global Keyboard Shortcuts
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) {
        return;
      }

      if (e.code === "Space") {
        e.preventDefault();
        togglePlay();
      } else if (e.key === "ArrowLeft" || e.key === "j" || e.key === "J") {
        e.preventDefault();
        seekRelative(-5);
      } else if (e.key === "ArrowRight" || e.key === "l" || e.key === "L") {
        e.preventDefault();
        seekRelative(5);
      } else if (e.key === "[") {
        e.preventDefault();
        setStartToPlayhead();
      } else if (e.key === "]") {
        e.preventDefault();
        setEndToPlayhead();
      } else if (e.key === "n" || e.key === "N") {
        e.preventDefault();
        addClipAtTime();
      } else if (e.key === "p" || e.key === "P") {
        e.preventDefault();
        previewClip(activeClipIndex);
      } else if (e.key === "?") {
        e.preventDefault();
        setShowShortcutsModal((prev) => !prev);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [togglePlay, seekRelative, setStartToPlayhead, setEndToPlayhead, addClipAtTime, previewClip, activeClipIndex]);

  // Timeline Mouse Drag Handler (Supports start handle, end handle, and whole-clip move)
  const handleTimelineMouseDown = useCallback(
    (e: React.MouseEvent, clipIndex: number, handle: "start" | "end" | "move") => {
      e.preventDefault();
      e.stopPropagation();
      const timeline = timelineRef.current;
      if (!timeline) return;
      const rect = timeline.getBoundingClientRect();
      const clickTime = Math.max(0, Math.min(videoDuration, ((e.clientX - rect.left) / rect.width) * videoDuration));

      setActiveClipIndex(clipIndex);
      setDragging({
        clipIndex,
        handle,
        initialTime: clickTime,
        initialStart: clips[clipIndex].start,
        initialEnd: clips[clipIndex].end,
      });
    },
    [clips, videoDuration]
  );

  useEffect(() => {
    if (!dragging) return;

    const onMouseMove = (e: MouseEvent) => {
      const timeline = timelineRef.current;
      if (!timeline) return;
      const rect = timeline.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const currentMouseTime = ratio * videoDuration;

      const updated = [...clips];
      const clip = updated[dragging.clipIndex];
      const minDuration = 5;
      const clipLen = dragging.initialEnd - dragging.initialStart;

      if (dragging.handle === "start") {
        const maxStart = clip.end - minDuration;
        clip.start = Math.max(0, Math.min(currentMouseTime, maxStart));
        clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
        if (videoRef.current) videoRef.current.currentTime = clip.start;
      } else if (dragging.handle === "end") {
        const minEnd = clip.start + minDuration;
        clip.end = Math.min(videoDuration, Math.max(currentMouseTime, minEnd));
        clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
        if (videoRef.current) videoRef.current.currentTime = clip.end;
      } else if (dragging.handle === "move") {
        const delta = currentMouseTime - dragging.initialTime;
        let newStart = dragging.initialStart + delta;
        let newEnd = dragging.initialEnd + delta;

        if (newStart < 0) {
          newStart = 0;
          newEnd = clipLen;
        } else if (newEnd > videoDuration) {
          newEnd = videoDuration;
          newStart = Math.max(0, videoDuration - clipLen);
        }

        clip.start = Math.round(newStart * 10) / 10;
        clip.end = Math.round(newEnd * 10) / 10;
        clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
        if (videoRef.current) videoRef.current.currentTime = clip.start;
      }

      clip.modified = clip.start !== clip.ai_start || clip.end !== clip.ai_end;
      onClipsChange(updated);
    };

    const onMouseUp = () => setDragging(null);

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    return () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
  }, [dragging, clips, videoDuration, onClipsChange]);

  const hasAnyModified = clips.some((c) => c.modified);

  return (
    <div className="flex flex-col lg:flex-row gap-3 min-h-0 relative select-none">
      {/* ─── LEFT: Clip Candidates List ──────────────────────────── */}
      <div className="lg:w-[340px] shrink-0 space-y-2 overflow-y-auto max-h-[calc(100vh-220px)] pr-1">
        <div className="flex items-center justify-between sticky top-0 bg-[var(--color-surface)] py-1.5 z-10 border-b border-zinc-800">
          <div className="flex items-center gap-1.5">
            <Scissors className="h-3.5 w-3.5 text-emerald-400" />
            <h3 className="text-xs font-semibold text-zinc-100">
              Kandidat Klip ({clips.length})
            </h3>
          </div>
          <div className="flex items-center gap-1.5">
            {hasAnyModified && (
              <button
                type="button"
                onClick={resetAll}
                className="flex items-center gap-1 text-[10px] text-amber-400 hover:text-amber-300 font-medium px-1.5 py-0.5 rounded hover:bg-zinc-800 transition-colors"
                title="Kembalikan semua ke timestamp AI"
              >
                <RotateCcw className="h-2.5 w-2.5" />
                Reset
              </button>
            )}
            <button
              type="button"
              onClick={() => addClipAtTime()}
              className="flex items-center gap-1 rounded-md bg-emerald-500/20 border border-emerald-500/40 px-2.5 py-1 text-[11px] text-emerald-300 hover:bg-emerald-500/30 font-semibold transition-all shadow-sm"
              title="Tambah klip baru pada posisi playhead (Shortcut: N)"
            >
              <Plus className="h-3.5 w-3.5" />
              Tambah Klip
            </button>
          </div>
        </div>

        {clips.map((clip, idx) => {
          const isSelected = activeClipIndex === idx;
          const isSweetSpot = clip.duration >= 30 && clip.duration <= 70;

          return (
            <Card
              key={`${clip.rank}-${idx}`}
              className={cn(
                "p-2.5 cursor-pointer transition-all border relative rounded-xl",
                isSelected
                  ? "border-emerald-500 bg-emerald-500/[0.08] shadow-[0_0_15px_rgba(16,185,129,0.12)] ring-1 ring-emerald-500/50"
                  : "border-zinc-800 bg-zinc-950/50 hover:border-zinc-700 hover:bg-zinc-900/50"
              )}
              onClick={() => seekToClip(idx)}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span
                      className={cn(
                        "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-black",
                        isSelected ? "bg-emerald-500 text-zinc-950" : "bg-zinc-800 text-zinc-200"
                      )}
                    >
                      #{clip.rank}
                    </span>
                    {clip.score !== null && (
                      <span className="shrink-0 flex items-center gap-0.5 rounded bg-emerald-500/20 border border-emerald-500/30 px-1.5 py-0.5 text-[10px] font-bold text-emerald-300">
                        <Sparkles className="w-2.5 h-2.5" />
                        {clip.score}
                      </span>
                    )}
                    {clip.manual && (
                      <span className="shrink-0 rounded bg-sky-500/20 border border-sky-500/30 px-1.5 py-0.5 text-[9px] font-medium text-sky-300">
                        Manual
                      </span>
                    )}
                    {clip.modified && !clip.manual && (
                      <span className="shrink-0 rounded bg-amber-500/20 border border-amber-500/30 px-1.5 py-0.5 text-[9px] font-medium text-amber-300">
                        Disesuaikan
                      </span>
                    )}
                  </div>

                  {clip.hook && (
                    <p className="mt-1 text-xs font-semibold text-zinc-100 line-clamp-2 leading-snug">
                      {clip.hook}
                    </p>
                  )}

                  <div className="mt-1.5 flex items-center gap-2 text-[10px] text-zinc-400">
                    <span className="flex items-center gap-1 bg-zinc-900/90 px-1.5 py-0.5 rounded font-mono border border-zinc-800">
                      <Clock className="h-2.5 w-2.5 text-emerald-400" />
                      {formatTime(clip.start)} - {formatTime(clip.end)}
                    </span>
                    <span
                      className={cn(
                        "font-mono font-medium",
                        isSweetSpot ? "text-emerald-400" : "text-amber-400"
                      )}
                    >
                      {clip.duration.toFixed(1)}s
                    </span>
                  </div>
                </div>

                <div className="flex flex-col gap-1 shrink-0">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      previewClip(idx);
                    }}
                    className="rounded-lg p-1.5 bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
                    title="Putar pratinjau klip (P)"
                  >
                    <Play className="h-3.5 w-3.5 fill-current" />
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      duplicateClip(idx);
                    }}
                    className="rounded-lg p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
                    title="Duplikat klip ini"
                  >
                    <Copy className="h-3 w-3" />
                  </button>
                  {clips.length > 1 && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteClip(idx);
                      }}
                      className="rounded-lg p-1.5 text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                      title="Hapus klip"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  )}
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {/* ─── RIGHT: Video Player + Timeline Track + Quick Action Controls ─ */}
      <div className="flex-1 min-w-0 flex flex-col gap-3">
        {/* Video Player Container */}
        <div className="relative rounded-xl overflow-hidden border border-zinc-800 bg-black shadow-xl">
          <video
            ref={videoRef}
            src={videoSrc}
            className="w-full aspect-video object-contain bg-black"
            preload="metadata"
            playsInline
            onEnded={() => setIsPlaying(false)}
          />

          {/* Social Safe Zone Mockup Overlay (9:16 TikTok / Reels simulator) */}
          {showSafeZone && (
            <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
              <div className="h-full aspect-[9/16] border-2 border-dashed border-sky-400/70 bg-sky-500/[0.04] relative flex flex-col justify-between p-3 select-none">
                <div className="rounded border border-sky-400/30 bg-sky-500/20 px-2 py-1 text-[8px] font-bold text-sky-200 text-center tracking-wider uppercase">
                  Top UI Safe Zone
                </div>
                <div className="absolute right-2 bottom-16 flex flex-col items-center gap-2">
                  <div className="w-6 h-6 rounded-full bg-black/60 border border-sky-400/40 flex items-center justify-center text-[7px] text-white">
                    <Heart className="w-3 h-3 fill-rose-500 text-rose-500" />
                  </div>
                  <div className="w-6 h-6 rounded-full bg-black/60 border border-sky-400/40 flex items-center justify-center text-[7px] text-white">
                    <MessageSquare className="w-3 h-3 text-zinc-300" />
                  </div>
                  <div className="w-6 h-6 rounded-full bg-black/60 border border-sky-400/40 flex items-center justify-center text-[7px] text-white">
                    <Share2 className="w-3 h-3 text-zinc-300" />
                  </div>
                </div>
                <div className="rounded border border-sky-400/30 bg-sky-500/20 p-1.5 text-[8px] font-bold text-sky-200 text-left w-3/4 space-y-0.5">
                  <p className="font-bold">@creator · 9:16 Safe Area</p>
                  <p className="text-[7px] text-sky-300 font-normal truncate">Subtitle & caption safe space</p>
                </div>
              </div>
            </div>
          )}

          {/* Center Play Overlay Button */}
          <button
            type="button"
            onClick={togglePlay}
            className="absolute inset-0 flex items-center justify-center bg-transparent hover:bg-black/15 transition-colors group"
          >
            {!isPlaying && (
              <span className="flex h-14 w-14 items-center justify-center rounded-full bg-black/70 text-white opacity-90 group-hover:opacity-100 group-hover:scale-105 transition-all shadow-2xl backdrop-blur-md border border-white/20">
                <Play className="h-6 w-6 ml-0.5 fill-current text-emerald-400" />
              </span>
            )}
          </button>

          {/* Control Bar Overlay on Video */}
          <div className="absolute bottom-2.5 left-2.5 right-2.5 flex items-center justify-between gap-2 rounded-lg bg-black/85 px-3 py-1.5 text-xs font-mono text-white backdrop-blur-md border border-zinc-800 shadow-md">
            <div className="flex items-center gap-2.5">
              <button type="button" onClick={togglePlay} className="hover:text-emerald-400 transition-colors p-0.5">
                {isPlaying ? <Pause className="h-3.5 w-3.5 fill-current text-emerald-400" /> : <Play className="h-3.5 w-3.5 fill-current" />}
              </button>
              <button type="button" onClick={() => seekRelative(-5)} className="text-zinc-400 hover:text-white" title="Mundur 5s (J)">
                <Rewind className="h-3.5 w-3.5" />
              </button>
              <button type="button" onClick={() => seekRelative(5)} className="text-zinc-400 hover:text-white" title="Maju 5s (L)">
                <FastForward className="h-3.5 w-3.5" />
              </button>
              <span className="font-semibold text-emerald-300">{formatTimePrecise(currentTime)}</span>
              <span className="text-zinc-600">/</span>
              <span className="text-zinc-400">{formatTimePrecise(videoDuration)}</span>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center bg-zinc-900/90 rounded-md border border-zinc-800 p-0.5">
                {[0.75, 1, 1.25, 1.5, 2].map((spd) => (
                  <button
                    key={spd}
                    type="button"
                    onClick={() => changeSpeed(spd)}
                    className={cn(
                      "px-1.5 py-0.5 text-[9px] rounded font-mono font-medium transition-colors",
                      playbackSpeed === spd ? "bg-emerald-500 text-zinc-950 font-bold" : "text-zinc-400 hover:text-zinc-200"
                    )}
                  >
                    {spd}x
                  </button>
                ))}
              </div>

              <button
                type="button"
                onClick={() => setShowSafeZone(!showSafeZone)}
                className={cn(
                  "flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-sans font-medium transition-colors border",
                  showSafeZone ? "border-sky-500/50 bg-sky-500/20 text-sky-300" : "border-zinc-700/60 bg-zinc-900/60 text-zinc-400 hover:text-zinc-200"
                )}
                title="Toggle 9:16 Social Safe-Zone Overlay"
              >
                <Shield className="h-3 w-3" />
                9:16 Safe Zone
              </button>

              <button
                type="button"
                onClick={() => setShowShortcutsModal(!showShortcutsModal)}
                className="p-1 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
                title="Panduan Pintasan Keyboard (?)"
              >
                <HelpCircle className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* Shortcuts popover */}
        {showShortcutsModal && (
          <div className="p-3 rounded-xl border border-zinc-700/80 bg-zinc-900/95 text-xs space-y-2 shadow-2xl">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-1.5">
              <span className="font-semibold text-zinc-200 flex items-center gap-1.5">
                <HelpCircle className="h-3.5 w-3.5 text-emerald-400" />
                Pintasan Keyboard Editor
              </span>
              <button type="button" onClick={() => setShowShortcutsModal(false)} className="text-zinc-500 hover:text-zinc-300">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px]">
              <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">Space</kbd> Play / Pause</div>
              <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">J</kbd> / <kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">L</kbd> Mundur/Maju 5s</div>
              <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">[</kbd> Pasang Titik Mulai (Start)</div>
              <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">]</kbd> Pasang Titik Selesai (End)</div>
              <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">N</kbd> Buat Klip Baru di Sini</div>
              <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">P</kbd> Pratinjau Klip Aktif</div>
            </div>
          </div>
        )}

        {/* ─── QUICK CLIP ACTIONS BAR (Paling Mudah Digunakan) ────────── */}
        <div className="flex flex-wrap items-center justify-between gap-2 p-2 rounded-xl bg-zinc-900/70 border border-zinc-800 shadow-inner">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider pl-1">
              Set Titik:
            </span>
            <button
              type="button"
              onClick={setStartToPlayhead}
              className="flex items-center gap-1 rounded-lg bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-1 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/25 transition-all"
              title="Set awal klip aktif pada waktu video saat ini (Pintasan: [)"
            >
              <ArrowRightToLine className="h-3.5 w-3.5" />
              Mulai di Sini <span className="text-[10px] opacity-60 font-mono">[</span>
            </button>
            <button
              type="button"
              onClick={setEndToPlayhead}
              className="flex items-center gap-1 rounded-lg bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-1 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/25 transition-all"
              title="Set akhir klip aktif pada waktu video saat ini (Pintasan: ])"
            >
              <ArrowLeftToLine className="h-3.5 w-3.5" />
              Selesai di Sini <span className="text-[10px] opacity-60 font-mono">]</span>
            </button>
            <button
              type="button"
              onClick={() => addClipAtTime(currentTime, 45)}
              className="flex items-center gap-1 rounded-lg bg-sky-500/20 border border-sky-500/40 px-2.5 py-1 text-xs font-semibold text-sky-200 hover:bg-sky-500/30 transition-all ml-1"
              title="Buat klip baru 45 detik mulai dari posisi sekarang (Pintasan: N)"
            >
              <BookmarkPlus className="h-3.5 w-3.5 text-sky-300" />
              + Klip Baru (45s)
            </button>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-medium text-zinc-400">Durasi Cepat:</span>
            {[30, 45, 60, 90].map((sec) => (
              <button
                key={sec}
                type="button"
                onClick={() => setExactDuration(sec)}
                className="px-2 py-0.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300 hover:text-white transition-colors"
                title={`Ubah durasi klip aktif menjadi ${sec} detik`}
              >
                {sec}s
              </button>
            ))}
          </div>
        </div>

        {/* ─── VISUAL TIMELINE TRACK ───────────────────────────────────── */}
        <Card className="p-3 space-y-2 border-zinc-800 bg-zinc-950/80">
          <div className="flex items-center justify-between text-[11px]">
            <div className="flex items-center gap-2">
              <Film className="h-3.5 w-3.5 text-emerald-400" />
              <span className="font-semibold text-zinc-200">Visual Timeline Multi-Klip</span>
              <span className="text-[10px] text-zinc-500">
                (Klik/geser track untuk seek · Geser kotak untuk atur waktu · Double click untuk tambah klip)
              </span>
            </div>
            {hoverTime !== null && (
              <span className="text-[10px] font-mono text-emerald-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
                Posisi Kursor: {formatTimePrecise(hoverTime)}
              </span>
            )}
          </div>

          {/* Main Timeline Bar */}
          <div
            ref={timelineRef}
            className="relative h-16 rounded-xl bg-zinc-950 border-2 border-zinc-800/90 overflow-visible cursor-crosshair select-none shadow-inner"
            onMouseMove={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
              setHoverTime(ratio * videoDuration);
            }}
            onMouseLeave={() => setHoverTime(null)}
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
              const time = ratio * videoDuration;
              if (videoRef.current) {
                videoRef.current.currentTime = time;
                setCurrentTime(time);
              }
            }}
            onDoubleClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
              const time = ratio * videoDuration;
              addClipAtTime(time, 45);
            }}
          >
            {/* Background Tick Lines */}
            <div className="absolute inset-0 flex justify-between pointer-events-none opacity-20 px-2">
              {Array.from({ length: 20 }).map((_, i) => (
                <div key={i} className="h-full w-px bg-zinc-500" />
              ))}
            </div>

            {/* Clip Regions */}
            {clips.map((clip, idx) => {
              const clampedStart = Math.max(0, Math.min(clip.start, videoDuration));
              const clampedEnd = Math.max(0, Math.min(clip.end, videoDuration));
              if (clampedEnd <= clampedStart) return null;
              const left = (clampedStart / videoDuration) * 100;
              const width = ((clampedEnd - clampedStart) / videoDuration) * 100;
              const isActive = idx === activeClipIndex;

              return (
                <div
                  key={`${clip.rank}-${idx}`}
                  className={cn(
                    "absolute top-1 bottom-1 rounded-lg border-2 transition-all select-none group/clip",
                    isActive
                      ? "bg-emerald-500/35 border-emerald-400 z-20 shadow-[0_0_12px_rgba(16,185,129,0.4)]"
                      : clip.manual
                        ? "bg-sky-500/20 border-sky-500/50 hover:border-sky-400 z-10"
                        : "bg-violet-500/20 border-violet-500/50 hover:border-violet-400 z-10",
                    clip.modified && !clip.manual && "border-amber-400"
                  )}
                  style={{ left: `${left}%`, width: `${Math.max(width, 1)}%` }}
                  onMouseDown={(e) => handleTimelineMouseDown(e, idx, "move")}
                  onClick={(e) => {
                    e.stopPropagation();
                    seekToClip(idx);
                  }}
                  title="Geser area tengah untuk memindahkan seluruh klip"
                >
                  {/* Clip Header Label */}
                  <div className="absolute top-1 left-1.5 right-1.5 flex items-center justify-between pointer-events-none">
                    <span
                      className={cn(
                        "text-[10px] font-black px-1 rounded",
                        isActive
                          ? "bg-emerald-400 text-zinc-950"
                          : clip.manual
                            ? "bg-sky-400 text-zinc-950"
                            : "bg-violet-400 text-zinc-950"
                      )}
                    >
                      #{clip.rank}
                    </span>
                    <span className="text-[9px] font-mono font-bold text-white bg-black/60 px-1 rounded">
                      {clip.duration.toFixed(1)}s
                    </span>
                  </div>

                  {/* Left (Start) Grab Handle */}
                  <div
                    className="absolute left-0 top-0 bottom-0 w-3.5 cursor-col-resize flex items-center justify-center bg-emerald-500/40 hover:bg-emerald-400 rounded-l-md transition-colors"
                    onMouseDown={(e) => handleTimelineMouseDown(e, idx, "start")}
                    title="Tarik untuk mengatur Titik Mulai (Start)"
                  >
                    <GripHorizontal className="h-3 w-3 text-white rotate-90" />
                  </div>

                  {/* Right (End) Grab Handle */}
                  <div
                    className="absolute right-0 top-0 bottom-0 w-3.5 cursor-col-resize flex items-center justify-center bg-emerald-500/40 hover:bg-emerald-400 rounded-r-md transition-colors"
                    onMouseDown={(e) => handleTimelineMouseDown(e, idx, "end")}
                    title="Tarik untuk mengatur Titik Selesai (End)"
                  >
                    <GripHorizontal className="h-3 w-3 text-white rotate-90" />
                  </div>
                </div>
              );
            })}

            {/* Hover Cursor Line */}
            {hoverTime !== null && (
              <div
                className="absolute top-0 bottom-0 w-px border-r border-dashed border-emerald-400/80 pointer-events-none z-25"
                style={{ left: `${(hoverTime / videoDuration) * 100}%` }}
              />
            )}

            {/* Live Playhead Line */}
            <div
              className="absolute top-0 bottom-0 w-0.5 bg-white pointer-events-none z-30 shadow-[0_0_8px_#fff]"
              style={{ left: `${(currentTime / videoDuration) * 100}%` }}
            >
              <div className="absolute -top-2 -left-2 w-4 h-4 rounded-full bg-white shadow-xl border-2 border-emerald-500" />
            </div>
          </div>

          {/* Time Scale Footer */}
          <div className="flex justify-between text-[10px] text-zinc-500 font-mono pt-0.5">
            <span>0:00</span>
            <span>{formatTime(videoDuration * 0.25)}</span>
            <span>{formatTime(videoDuration * 0.5)}</span>
            <span>{formatTime(videoDuration * 0.75)}</span>
            <span>{formatTime(videoDuration)}</span>
          </div>
        </Card>

        {/* ─── ACTIVE CLIP DETAILED ADJUSTMENT PANEL ───────────────────── */}
        {activeClip && (
          <Card className="p-3.5 space-y-3 border-zinc-800 bg-zinc-950/70 rounded-xl">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sliders className="h-4 w-4 text-emerald-400" />
                <span className="text-xs font-bold text-zinc-100">
                  Pengaturan Presisi Klip #{activeClip.rank}
                </span>
                {activeClip.modified && (
                  <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[9px] font-semibold text-amber-300">
                    Kustomisasi Aktif
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {activeClip.modified && !activeClip.manual && (
                  <button
                    type="button"
                    onClick={() => resetClip(activeClipIndex)}
                    className="flex items-center gap-1 text-[10px] text-amber-400 hover:text-amber-300 font-medium"
                  >
                    <RotateCcw className="h-3 w-3" />
                    Reset AI
                  </button>
                )}
                {clips.length > 1 && (
                  <button
                    type="button"
                    onClick={() => deleteClip(activeClipIndex)}
                    className="flex items-center gap-1 text-[10px] text-red-400 hover:text-red-300 font-medium"
                  >
                    <Trash2 className="h-3 w-3" />
                    Hapus Klip
                  </button>
                )}
              </div>
            </div>

            {/* Editable Hook Title */}
            <div>
              <label className="block text-[10px] font-semibold text-zinc-400 uppercase tracking-wider mb-1">
                Judul Hook Klip (3 Detik Pertama)
              </label>
              <input
                type="text"
                value={activeClip.hook || ""}
                onChange={(e) => updateHookTitle(e.target.value)}
                placeholder="Masukkan judul atau hook untuk klip ini..."
                className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-xs text-zinc-100 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none"
              />
            </div>

            {/* Start & End Precision Inputs with Step Nudges */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {/* Start Time Box */}
              <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-2.5 space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
                    Titik Mulai (Start)
                  </label>
                  <span className="text-[9px] text-zinc-500 font-mono">{activeClip.start.toFixed(1)}s</span>
                </div>
                <input
                  type="text"
                  value={startInputText}
                  onChange={(e) => {
                    const text = e.target.value;
                    setStartInputText(text);
                    const val = parseTimeToSeconds(text);
                    if (val !== null) {
                      const updated = [...clips];
                      const clip = updated[activeClipIndex];
                      clip.start = Math.max(0, Math.min(val, clip.end - 5));
                      clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
                      clip.modified = clip.start !== clip.ai_start || clip.end !== clip.ai_end;
                      onClipsChange(updated);
                    }
                  }}
                  placeholder="mm:ss atau detik"
                  className="w-full rounded-md border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 text-xs text-emerald-300 font-mono font-bold focus:border-emerald-500 focus:outline-none"
                />
                <div className="flex items-center gap-1 pt-1">
                  <button type="button" onClick={() => nudgeStart(-5)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">-5s</button>
                  <button type="button" onClick={() => nudgeStart(-1)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">-1s</button>
                  <button type="button" onClick={() => nudgeStart(1)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">+1s</button>
                  <button type="button" onClick={() => nudgeStart(5)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">+5s</button>
                </div>
                <button
                  type="button"
                  onClick={jumpToActiveStart}
                  className="w-full text-center py-1 rounded bg-zinc-800/80 text-[10px] text-zinc-300 hover:text-white hover:bg-zinc-700 transition-colors"
                >
                  Lompat ke Mulai ({formatTime(activeClip.start)})
                </button>
              </div>

              {/* End Time Box */}
              <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-2.5 space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
                    Titik Selesai (End)
                  </label>
                  <span className="text-[9px] text-zinc-500 font-mono">{activeClip.end.toFixed(1)}s</span>
                </div>
                <input
                  type="text"
                  value={endInputText}
                  onChange={(e) => {
                    const text = e.target.value;
                    setEndInputText(text);
                    const val = parseTimeToSeconds(text);
                    if (val !== null) {
                      const updated = [...clips];
                      const clip = updated[activeClipIndex];
                      clip.end = Math.min(videoDuration, Math.max(val, clip.start + 5));
                      clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
                      clip.modified = clip.start !== clip.ai_start || clip.end !== clip.ai_end;
                      onClipsChange(updated);
                    }
                  }}
                  placeholder="mm:ss atau detik"
                  className="w-full rounded-md border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 text-xs text-emerald-300 font-mono font-bold focus:border-emerald-500 focus:outline-none"
                />
                <div className="flex items-center gap-1 pt-1">
                  <button type="button" onClick={() => nudgeEnd(-5)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">-5s</button>
                  <button type="button" onClick={() => nudgeEnd(-1)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">-1s</button>
                  <button type="button" onClick={() => nudgeEnd(1)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">+1s</button>
                  <button type="button" onClick={() => nudgeEnd(5)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">+5s</button>
                </div>
                <button
                  type="button"
                  onClick={jumpToActiveEnd}
                  className="w-full text-center py-1 rounded bg-zinc-800/80 text-[10px] text-zinc-300 hover:text-white hover:bg-zinc-700 transition-colors"
                >
                  Lompat ke Selesai ({formatTime(activeClip.end)})
                </button>
              </div>

              {/* Total Duration & Preview Box */}
              <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-2.5 flex flex-col justify-between">
                <div>
                  <label className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
                    Total Durasi Klip
                  </label>
                  <p className="text-2xl font-bold font-mono text-zinc-100 mt-1">
                    {activeClip.duration.toFixed(1)}
                    <span className="text-xs text-zinc-500 font-normal ml-1">detik</span>
                  </p>
                  <p className="text-[10px] text-zinc-400 mt-0.5">
                    {formatTime(activeClip.start)} s/d {formatTime(activeClip.end)}
                  </p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => previewClip(activeClipIndex)}
                  icon={<Play className="h-3.5 w-3.5 fill-current text-emerald-400" />}
                  className="w-full mt-2 border-emerald-500/30 hover:bg-emerald-500/10 text-emerald-300"
                >
                  Putar Klip Ini (P)
                </Button>
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
