import { useCallback, useEffect, useRef, useState } from "react";
import { Clock, Film, GripHorizontal, Play, Pause, RotateCcw, Scissors, Plus, Trash2, Edit3, FastForward, Rewind, Sparkles, HelpCircle, Shield, Gauge, Check, Copy } from "lucide-react";
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
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);
  const [showSafeZone, setShowSafeZone] = useState<boolean>(false);
  const [showShortcutsModal, setShowShortcutsModal] = useState<boolean>(false);
  const [activeClipIndex, setActiveClipIndex] = useState(0);
  const [startInputText, setStartInputText] = useState("");
  const [endInputText, setEndInputText] = useState("");
  const [dragging, setDragging] = useState<{
    clipIndex: number;
    handle: "start" | "end";
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

  // Seek to clip start
  const seekToClip = useCallback((index: number) => {
    const video = videoRef.current;
    if (!video || !clips[index]) return;
    setActiveClipIndex(index);
    video.currentTime = clips[index].start;
    setCurrentTime(clips[index].start);
  }, [clips]);

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

  // Add new clip at current playhead position
  const addClip = useCallback(() => {
    const start = Math.max(0, currentTime);
    const defaultDuration = 20;
    const end = Math.min(videoDuration, start + defaultDuration);
    if (end - start < 5) return;

    const maxRank = clips.length > 0 ? Math.max(...clips.map((c) => c.rank)) : 0;
    const newClip: EditableClip = {
      rank: maxRank + 1,
      start,
      end,
      duration: Math.round((end - start) * 100) / 100,
      score: null,
      hook: "Custom Clip",
      reason: null,
      content_type: null,
      speaker_energy: null,
      ai_start: start,
      ai_end: end,
      modified: false,
      manual: true,
    };

    const updated = [...clips, newClip];
    onClipsChange(updated);
    setActiveClipIndex(updated.length - 1);
  }, [clips, currentTime, videoDuration, onClipsChange]);

  // Delete clip
  const deleteClip = useCallback((index: number) => {
    if (clips.length <= 1) return;
    const updated = clips.filter((_, i) => i !== index);
    updated.forEach((c, i) => { c.rank = i + 1; });
    onClipsChange(updated);
    setActiveClipIndex(Math.min(activeClipIndex, updated.length - 1));
  }, [clips, activeClipIndex, onClipsChange]);

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
    if (currentTime >= clip.end - minDuration) return;
    clip.start = Math.round(currentTime * 10) / 10;
    clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
    clip.modified = clip.start !== clip.ai_start || clip.end !== clip.ai_end;
    onClipsChange(updated);
  }, [activeClip, activeClipIndex, clips, currentTime, onClipsChange]);

  const setEndToPlayhead = useCallback(() => {
    if (!activeClip) return;
    const updated = [...clips];
    const clip = updated[activeClipIndex];
    const minDuration = 5;
    if (currentTime <= clip.start + minDuration) return;
    clip.end = Math.round(Math.min(videoDuration, currentTime) * 10) / 10;
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
      // Don't trigger shortcuts if user is typing in an input or textarea
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
        addClip();
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
  }, [togglePlay, seekRelative, setStartToPlayhead, setEndToPlayhead, addClip, previewClip, activeClipIndex]);

  // Timeline drag handler
  const handleTimelineMouseDown = useCallback(
    (e: React.MouseEvent, clipIndex: number, handle: "start" | "end") => {
      e.preventDefault();
      e.stopPropagation();
      setDragging({ clipIndex, handle });
    },
    []
  );

  useEffect(() => {
    if (!dragging) return;

    const onMouseMove = (e: MouseEvent) => {
      const timeline = timelineRef.current;
      if (!timeline) return;
      const rect = timeline.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const newTime = ratio * videoDuration;

      const updated = [...clips];
      const clip = updated[dragging.clipIndex];
      const minDuration = 5;

      if (dragging.handle === "start") {
        const maxStart = clip.end - minDuration;
        clip.start = Math.max(0, Math.min(newTime, maxStart));
      } else {
        const minEnd = clip.start + minDuration;
        clip.end = Math.min(videoDuration, Math.max(newTime, minEnd));
      }
      clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
      clip.modified = clip.start !== clip.ai_start || clip.end !== clip.ai_end;
      onClipsChange(updated);

      const video = videoRef.current;
      if (video) {
        video.currentTime = dragging.handle === "start" ? clip.start : clip.end;
      }
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
    <div className="flex flex-col lg:flex-row gap-3 min-h-0 relative">
      {/* Left: AI Analysis Results + Add/Delete */}
      <div className="lg:w-[360px] shrink-0 space-y-2 overflow-y-auto max-h-[calc(100vh-250px)] pr-1">
        <div className="flex items-center justify-between mb-1 sticky top-0 bg-[var(--color-surface)] py-1 z-10">
          <div className="flex items-center gap-1.5">
            <Scissors className="h-3.5 w-3.5 text-emerald-400" />
            <h3 className="text-xs font-semibold text-zinc-100">
              Clips ({clips.length})
            </h3>
          </div>
          <div className="flex items-center gap-2">
            {hasAnyModified && (
              <button
                type="button"
                onClick={resetAll}
                className="flex items-center gap-1 text-[10px] text-amber-400 hover:text-amber-300 font-medium"
              >
                <RotateCcw className="h-3 w-3" />
                Reset All
              </button>
            )}
            <button
              type="button"
              onClick={addClip}
              className="flex items-center gap-1 rounded-md bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-1 text-[10px] text-emerald-300 hover:bg-emerald-500/25 font-medium transition-colors"
              title="Add clip at current position (Shortcut: N)"
            >
              <Plus className="h-3 w-3" />
              Add Clip
            </button>
          </div>
        </div>

        {clips.map((clip, idx) => {
          const isSelected = activeClipIndex === idx;
          return (
            <Card
              key={`${clip.rank}-${idx}`}
              className={cn(
                "p-3 cursor-pointer transition-all border relative",
                isSelected
                  ? "border-emerald-500 bg-emerald-500/[0.08] shadow-[0_0_12px_rgba(16,185,129,0.15)] ring-1 ring-emerald-500/40"
                  : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700 hover:bg-zinc-900/40"
              )}
              onClick={() => seekToClip(idx)}
            >
              <div className="flex items-start justify-between gap-2.5">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className={cn(
                      "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-extrabold",
                      isSelected ? "bg-emerald-500 text-zinc-950" : "bg-zinc-800 text-zinc-200"
                    )}>
                      #{clip.rank}
                    </span>
                    {clip.score !== null && (
                      <span className="shrink-0 flex items-center gap-0.5 rounded bg-emerald-500/20 border border-emerald-500/30 px-1.5 py-0.5 text-[10px] font-bold text-emerald-300">
                        <Sparkles className="w-2.5 h-2.5" />
                        {clip.score}
                      </span>
                    )}
                    {clip.manual && (
                      <span className="shrink-0 rounded bg-blue-500/20 border border-blue-500/30 px-1.5 py-0.5 text-[9px] font-medium text-blue-300">
                        Manual
                      </span>
                    )}
                    {clip.modified && !clip.manual && (
                      <span className="shrink-0 rounded bg-amber-500/20 border border-amber-500/30 px-1.5 py-0.5 text-[9px] font-medium text-amber-300">
                        Edited
                      </span>
                    )}
                  </div>
                  {clip.hook && (
                    <p className="mt-1.5 text-xs font-semibold text-zinc-100 line-clamp-2 leading-snug">
                      {clip.hook}
                    </p>
                  )}
                  <div className="mt-2 flex items-center gap-2.5 text-[10px] text-zinc-400">
                    <span className="flex items-center gap-1 bg-zinc-900/80 px-2 py-0.5 rounded font-mono border border-zinc-800">
                      <Clock className="h-3 w-3 text-emerald-400" />
                      {formatTime(clip.start)} - {formatTime(clip.end)}
                    </span>
                    <span className="font-mono text-zinc-300 font-medium">{clip.duration.toFixed(1)}s</span>
                  </div>
                  {clip.reason && (
                    <p className="mt-1.5 text-[10px] text-zinc-500 line-clamp-2 leading-relaxed">{clip.reason}</p>
                  )}
                </div>
                <div className="flex flex-col gap-1.5 shrink-0 pt-0.5">
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); previewClip(idx); }}
                    className="rounded-lg p-1.5 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/25 transition-colors"
                    title="Preview clip audio/video (P)"
                  >
                    <Play className="h-3.5 w-3.5 fill-current" />
                  </button>
                  {clip.modified && !clip.manual && (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); resetClip(idx); }}
                      className="rounded-lg p-1.5 bg-amber-500/10 text-amber-400 hover:bg-amber-500/25 transition-colors"
                      title="Reset to AI timestamps"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                    </button>
                  )}
                  {clips.length > 1 && (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); deleteClip(idx); }}
                      className="rounded-lg p-1.5 bg-red-500/10 text-red-400 hover:bg-red-500/25 transition-colors"
                      title="Delete clip"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {/* Right: Video Player + Safe Zones + Controls + Timeline */}
      <div className="flex-1 min-w-0 flex flex-col gap-3">
        {/* Video Player Container with Safe-Zone overlay support */}
        <div className="relative rounded-xl overflow-hidden border border-zinc-800 bg-black shadow-lg">
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
              {/* 9:16 bounding box in video */}
              <div className="h-full aspect-[9/16] border-2 border-dashed border-sky-400/70 bg-sky-500/[0.04] relative flex flex-col justify-between p-3 select-none">
                {/* Top Safe Area (Header / Search / Live tabs) */}
                <div className="rounded border border-sky-400/30 bg-sky-500/20 px-2 py-1 text-[8px] font-bold text-sky-200 text-center tracking-wider uppercase">
                  Top UI Zone (Search / Tabs)
                </div>

                {/* Right Action Icons Zone */}
                <div className="absolute right-2 bottom-16 flex flex-col items-center gap-2">
                  <div className="w-6 h-6 rounded-full bg-black/60 border border-sky-400/40 flex items-center justify-center text-[7px] text-white">❤️</div>
                  <div className="w-6 h-6 rounded-full bg-black/60 border border-sky-400/40 flex items-center justify-center text-[7px] text-white">💬</div>
                  <div className="w-6 h-6 rounded-full bg-black/60 border border-sky-400/40 flex items-center justify-center text-[7px] text-white">↗️</div>
                  <div className="w-6 h-6 rounded-full bg-black/60 border border-sky-400/40 flex items-center justify-center text-[7px] text-white">🎵</div>
                </div>

                {/* Bottom Safe Area (Username & Caption Zone) */}
                <div className="rounded border border-sky-400/30 bg-sky-500/20 p-1.5 text-[8px] font-bold text-sky-200 text-left w-3/4 space-y-0.5">
                  <p className="font-bold">@creator · TikTok / Reels UI</p>
                  <p className="text-[7px] text-sky-300 font-normal truncate">Caption & audio title safe area...</p>
                </div>
              </div>
            </div>
          )}

          {/* Center Play overlay */}
          <button
            type="button"
            onClick={togglePlay}
            className="absolute inset-0 flex items-center justify-center bg-transparent hover:bg-black/20 transition-colors group"
          >
            {!isPlaying && (
              <span className="flex h-14 w-14 items-center justify-center rounded-full bg-black/60 text-white opacity-90 group-hover:opacity-100 group-hover:scale-105 transition-all shadow-xl backdrop-blur-sm">
                <Play className="h-6 w-6 ml-0.5 fill-current" />
              </span>
            )}
          </button>

          {/* Control bar */}
          <div className="absolute bottom-2.5 left-2.5 right-2.5 flex items-center justify-between gap-2 rounded-lg bg-black/80 px-3 py-1.5 text-xs font-mono text-white backdrop-blur-md border border-zinc-800">
            {/* Left: Play/Pause & Time */}
            <div className="flex items-center gap-2.5">
              <button type="button" onClick={togglePlay} className="hover:text-emerald-400 transition-colors">
                {isPlaying ? <Pause className="h-3.5 w-3.5 fill-current" /> : <Play className="h-3.5 w-3.5 fill-current" />}
              </button>
              <span className="font-semibold text-emerald-300">{formatTimePrecise(currentTime)}</span>
              <span className="text-zinc-500">/</span>
              <span className="text-zinc-400">{formatTimePrecise(videoDuration)}</span>
            </div>

            {/* Right: Playback Speed, Safe Zone & Shortcut Help */}
            <div className="flex items-center gap-2">
              {/* Speed buttons */}
              <div className="flex items-center bg-zinc-900/90 rounded-md border border-zinc-800 p-0.5">
                {[0.75, 1, 1.25, 1.5, 2].map((spd) => (
                  <button
                    key={spd}
                    type="button"
                    onClick={() => changeSpeed(spd)}
                    className={cn(
                      "px-1.5 py-0.5 text-[9px] rounded font-mono font-medium transition-colors",
                      playbackSpeed === spd
                        ? "bg-emerald-500 text-zinc-950 font-bold"
                        : "text-zinc-400 hover:text-zinc-200"
                    )}
                  >
                    {spd}x
                  </button>
                ))}
              </div>

              {/* Safe Zone Toggle */}
              <button
                type="button"
                onClick={() => setShowSafeZone(!showSafeZone)}
                className={cn(
                  "flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-sans font-medium transition-colors border",
                  showSafeZone
                    ? "border-sky-500/50 bg-sky-500/20 text-sky-300"
                    : "border-zinc-700/60 bg-zinc-900/60 text-zinc-400 hover:text-zinc-200"
                )}
                title="Toggle 9:16 Social Safe-Zone Overlay"
              >
                <Shield className="h-3 w-3" />
                Safe Zone
              </button>

              {/* Shortcut Help Button */}
              <button
                type="button"
                onClick={() => setShowShortcutsModal(!showShortcutsModal)}
                className="p-1 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
                title="Keyboard Shortcuts (?)"
              >
                <HelpCircle className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* Shortcuts popover */}
        {showShortcutsModal && (
          <div className="p-3 rounded-lg border border-zinc-700/80 bg-zinc-900/95 text-xs space-y-2 shadow-xl">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-1.5">
              <span className="font-semibold text-zinc-200 flex items-center gap-1.5">
                <HelpCircle className="h-3.5 w-3.5 text-emerald-400" />
                Keyboard Shortcuts Pro
              </span>
              <button type="button" onClick={() => setShowShortcutsModal(false)} className="text-zinc-500 hover:text-zinc-300">✕</button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px]">
              <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">Space</kbd> Play / Pause</div>
              <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">J</kbd> / <kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">L</kbd> Seek -5s / +5s</div>
              <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">[</kbd> Set Start here</div>
              <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">]</kbd> Set End here</div>
              <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">N</kbd> Add Clip at Playhead</div>
              <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">P</kbd> Preview Active Clip</div>
            </div>
          </div>
        )}

        {/* Timeline with clip markers */}
        <Card className="p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5">
              <Film className="h-3.5 w-3.5 text-violet-400" />
              <span className="text-[10px] font-medium text-zinc-300 uppercase tracking-wider">Visual Timeline</span>
            </div>
            <span className="text-[10px] text-zinc-500">
              Drag handles to adjust · Click timeline to seek
            </span>
          </div>

          {/* Timeline bar */}
          <div
            ref={timelineRef}
            className="relative h-14 rounded-lg bg-zinc-950 border border-zinc-800 overflow-visible cursor-crosshair"
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const ratio = (e.clientX - rect.left) / rect.width;
              const time = Math.max(0, Math.min(videoDuration, ratio * videoDuration));
              if (videoRef.current) {
                videoRef.current.currentTime = time;
                setCurrentTime(time);
              }
            }}
          >
            {/* Clip regions */}
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
                    "absolute top-1 bottom-1 rounded-md border transition-colors select-none",
                    isActive
                      ? "bg-emerald-500/30 border-emerald-400 z-[5] shadow-[0_0_8px_rgba(16,185,129,0.4)]"
                      : clip.manual
                        ? "bg-blue-500/15 border-blue-500/40"
                        : "bg-violet-500/20 border-violet-500/40",
                    clip.modified && !clip.manual && "border-amber-400/70"
                  )}
                  style={{ left: `${left}%`, width: `${Math.max(width, 0.5)}%` }}
                  onClick={(e) => { e.stopPropagation(); seekToClip(idx); }}
                >
                  {/* Clip label */}
                  <span className={cn(
                    "absolute top-0.5 left-1 text-[9px] font-black",
                    isActive ? "text-emerald-300" : clip.manual ? "text-blue-300" : "text-violet-300"
                  )}>
                    #{clip.rank}
                  </span>

                  {/* Start handle */}
                  <div
                    className="absolute left-0 top-0 bottom-0 w-3 cursor-col-resize flex items-center justify-center bg-emerald-500/20 hover:bg-emerald-500/50 rounded-l-md"
                    onMouseDown={(e) => handleTimelineMouseDown(e, idx, "start")}
                    title="Drag to adjust Start"
                  >
                    <GripHorizontal className="h-3 w-3 text-white rotate-90" />
                  </div>

                  {/* End handle */}
                  <div
                    className="absolute right-0 top-0 bottom-0 w-3 cursor-col-resize flex items-center justify-center bg-emerald-500/20 hover:bg-emerald-500/50 rounded-r-md"
                    onMouseDown={(e) => handleTimelineMouseDown(e, idx, "end")}
                    title="Drag to adjust End"
                  >
                    <GripHorizontal className="h-3 w-3 text-white rotate-90" />
                  </div>
                </div>
              );
            })}

            {/* Playhead */}
            <div
              className="absolute top-0 bottom-0 w-0.5 bg-white pointer-events-none z-10 shadow-[0_0_6px_#fff]"
              style={{ left: `${(currentTime / videoDuration) * 100}%` }}
            >
              <div className="absolute -top-1.5 -left-1.5 w-3.5 h-3.5 rounded-full bg-white shadow-md border-2 border-emerald-500" />
            </div>
          </div>

          {/* Time scale */}
          <div className="flex justify-between mt-1.5 text-[9px] text-zinc-500 font-mono">
            <span>0:00</span>
            <span>{formatTime(videoDuration * 0.25)}</span>
            <span>{formatTime(videoDuration * 0.5)}</span>
            <span>{formatTime(videoDuration * 0.75)}</span>
            <span>{formatTime(videoDuration)}</span>
          </div>
        </Card>

        {/* Active clip detailed timing editor */}
        {activeClip && (
          <Card className="p-3.5 space-y-3 border-zinc-800 bg-zinc-950/60">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Edit3 className="h-3.5 w-3.5 text-emerald-400" />
                <span className="text-xs font-semibold text-zinc-200">
                  Clip #{activeClip.rank} Timing & Details
                </span>
                {activeClip.modified && (
                  <span className="rounded bg-amber-500/20 px-1.5 py-0.2 text-[9px] font-semibold text-amber-300">
                    Custom Timing
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
                    Reset to AI
                  </button>
                )}
                {clips.length > 1 && (
                  <button
                    type="button"
                    onClick={() => deleteClip(activeClipIndex)}
                    className="flex items-center gap-1 text-[10px] text-red-400 hover:text-red-300 font-medium"
                  >
                    <Trash2 className="h-3 w-3" />
                    Delete
                  </button>
                )}
              </div>
            </div>

            {/* Editable Hook Title */}
            <div>
              <label className="block text-[10px] font-medium text-zinc-400 mb-1">Hook Title</label>
              <input
                type="text"
                value={activeClip.hook || ""}
                onChange={(e) => updateHookTitle(e.target.value)}
                placeholder="Judul hook untuk clip ini..."
                className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-xs text-zinc-100 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none"
              />
            </div>

            {/* Start & End Precision Inputs with Nudges */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {/* Start Time Box */}
              <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-2.5 space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">Start Time</label>
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
                  onClick={setStartToPlayhead}
                  className="w-full text-center py-1 rounded bg-emerald-500/10 border border-emerald-500/20 text-[10px] text-emerald-400 hover:bg-emerald-500/20 font-medium transition-colors"
                >
                  Set to Playhead ({formatTime(currentTime)}) [Key: []
                </button>
              </div>

              {/* End Time Box */}
              <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-2.5 space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">End Time</label>
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
                  onClick={setEndToPlayhead}
                  className="w-full text-center py-1 rounded bg-emerald-500/10 border border-emerald-500/20 text-[10px] text-emerald-400 hover:bg-emerald-500/20 font-medium transition-colors"
                >
                  Set to Playhead ({formatTime(currentTime)}) [Key: ]]
                </button>
              </div>

              {/* Total Duration & Preview Box */}
              <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-2.5 flex flex-col justify-between">
                <div>
                  <label className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">Clip Duration</label>
                  <p className="text-xl font-bold font-mono text-zinc-100 mt-1">
                    {activeClip.duration.toFixed(1)}<span className="text-xs text-zinc-500 font-normal ml-1">detik</span>
                  </p>
                  <p className="text-[10px] text-zinc-500 mt-1">
                    {formatTime(activeClip.start)} sampai {formatTime(activeClip.end)}
                  </p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => previewClip(activeClipIndex)}
                  icon={<Play className="h-3.5 w-3.5 fill-current" />}
                  className="w-full mt-2"
                >
                  Play Active Clip (P)
                </Button>
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
