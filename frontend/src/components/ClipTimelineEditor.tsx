import { useCallback, useEffect, useRef, useState } from "react";
import { Clock, Film, GripHorizontal, Play, Pause, RotateCcw, Scissors } from "lucide-react";
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
  const [activeClipIndex, setActiveClipIndex] = useState(0);
  const [dragging, setDragging] = useState<{
    clipIndex: number;
    handle: "start" | "end";
  } | null>(null);

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
      const minDuration = 5; // minimum 5 seconds per clip

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

      // Sync video to dragged position
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
    <div className="flex flex-col lg:flex-row gap-3 min-h-0">
      {/* Left: AI Analysis Results */}
      <div className="lg:w-[340px] shrink-0 space-y-2 overflow-y-auto max-h-[calc(100vh-280px)]">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-1.5">
            <Scissors className="h-3.5 w-3.5 text-emerald-400" />
            <h3 className="text-xs font-semibold text-zinc-200">
              AI Clip Candidates ({clips.length})
            </h3>
          </div>
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
        </div>

        {clips.map((clip, idx) => (
          <Card
            key={clip.rank}
            className={cn(
              "p-2.5 cursor-pointer transition-all border",
              activeClipIndex === idx
                ? "border-emerald-500/50 bg-emerald-500/[0.06]"
                : "border-zinc-800 hover:border-zinc-700"
            )}
            onClick={() => seekToClip(idx)}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="shrink-0 rounded bg-zinc-800 px-1.5 py-0.5 text-[9px] font-bold text-zinc-300">
                    #{clip.rank}
                  </span>
                  {clip.score !== null && (
                    <span className="shrink-0 rounded bg-emerald-500/20 px-1.5 py-0.5 text-[9px] font-bold text-emerald-300">
                      {clip.score}
                    </span>
                  )}
                  {clip.modified && (
                    <span className="shrink-0 rounded bg-amber-500/20 px-1 py-0.5 text-[8px] font-medium text-amber-300">
                      Edited
                    </span>
                  )}
                </div>
                {clip.hook && (
                  <p className="mt-1 text-[11px] font-medium text-zinc-200 line-clamp-2 leading-snug">
                    {clip.hook}
                  </p>
                )}
                <div className="mt-1.5 flex items-center gap-2 text-[10px] text-zinc-500">
                  <span className="flex items-center gap-0.5">
                    <Clock className="h-2.5 w-2.5" />
                    {formatTime(clip.start)} - {formatTime(clip.end)}
                  </span>
                  <span>{clip.duration.toFixed(1)}s</span>
                </div>
                {clip.reason && (
                  <p className="mt-1 text-[9px] text-zinc-600 line-clamp-1">{clip.reason}</p>
                )}
              </div>
              <div className="flex flex-col gap-1 shrink-0">
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); previewClip(idx); }}
                  className="rounded p-1 text-zinc-500 hover:bg-emerald-500/10 hover:text-emerald-400 transition-colors"
                  title="Preview clip"
                >
                  <Play className="h-3 w-3" />
                </button>
                {clip.modified && (
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); resetClip(idx); }}
                    className="rounded p-1 text-zinc-500 hover:bg-amber-500/10 hover:text-amber-400 transition-colors"
                    title="Reset to AI"
                  >
                    <RotateCcw className="h-3 w-3" />
                  </button>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Right: Video Player + Timeline */}
      <div className="flex-1 min-w-0 flex flex-col gap-2">
        {/* Video Player */}
        <div className="relative rounded-xl overflow-hidden border border-zinc-800 bg-black">
          <video
            ref={videoRef}
            src={videoSrc}
            className="w-full aspect-video object-contain bg-black"
            preload="metadata"
            playsInline
            onEnded={() => setIsPlaying(false)}
          />
          {/* Play overlay */}
          <button
            type="button"
            onClick={togglePlay}
            className="absolute inset-0 flex items-center justify-center bg-transparent hover:bg-black/20 transition-colors group"
          >
            {!isPlaying && (
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-black/50 text-white opacity-0 group-hover:opacity-100 transition-opacity">
                <Play className="h-5 w-5 ml-0.5" />
              </span>
            )}
          </button>
          {/* Time display */}
          <div className="absolute bottom-2 left-2 flex items-center gap-2 rounded-lg bg-black/70 px-2 py-1 text-[11px] font-mono text-white backdrop-blur-sm">
            <button type="button" onClick={togglePlay} className="hover:text-emerald-400 transition-colors">
              {isPlaying ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            </button>
            <span>{formatTimePrecise(currentTime)} / {formatTimePrecise(videoDuration)}</span>
          </div>
        </div>

        {/* Timeline with clip markers */}
        <Card className="p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5">
              <Film className="h-3 w-3 text-violet-400" />
              <span className="text-[10px] font-medium text-zinc-400 uppercase tracking-wider">Timeline</span>
            </div>
            <span className="text-[10px] text-zinc-600">
              Drag handles to adjust clip boundaries
            </span>
          </div>

          {/* Timeline bar */}
          <div
            ref={timelineRef}
            className="relative h-12 rounded-lg bg-zinc-900 border border-zinc-800 overflow-hidden cursor-crosshair"
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const ratio = (e.clientX - rect.left) / rect.width;
              const time = ratio * videoDuration;
              if (videoRef.current) {
                videoRef.current.currentTime = time;
                setCurrentTime(time);
              }
            }}
          >
            {/* Clip regions */}
            {clips.map((clip, idx) => {
              const left = (clip.start / videoDuration) * 100;
              const width = ((clip.end - clip.start) / videoDuration) * 100;
              const isActive = idx === activeClipIndex;

              return (
                <div
                  key={clip.rank}
                  className={cn(
                    "absolute top-1 bottom-1 rounded-md border transition-colors",
                    isActive
                      ? "bg-emerald-500/20 border-emerald-500/60"
                      : "bg-violet-500/10 border-violet-500/30",
                    clip.modified && "border-amber-500/50"
                  )}
                  style={{ left: `${left}%`, width: `${width}%` }}
                  onClick={(e) => { e.stopPropagation(); seekToClip(idx); }}
                >
                  {/* Clip label */}
                  <span className={cn(
                    "absolute top-0.5 left-1 text-[8px] font-bold",
                    isActive ? "text-emerald-300" : "text-violet-300"
                  )}>
                    {clip.rank}
                  </span>

                  {/* Start handle */}
                  <div
                    className="absolute left-0 top-0 bottom-0 w-2 cursor-col-resize flex items-center justify-center hover:bg-white/10 rounded-l-md"
                    onMouseDown={(e) => handleTimelineMouseDown(e, idx, "start")}
                  >
                    <GripHorizontal className="h-2.5 w-2.5 text-zinc-400 rotate-90" />
                  </div>

                  {/* End handle */}
                  <div
                    className="absolute right-0 top-0 bottom-0 w-2 cursor-col-resize flex items-center justify-center hover:bg-white/10 rounded-r-md"
                    onMouseDown={(e) => handleTimelineMouseDown(e, idx, "end")}
                  >
                    <GripHorizontal className="h-2.5 w-2.5 text-zinc-400 rotate-90" />
                  </div>
                </div>
              );
            })}

            {/* Playhead */}
            <div
              className="absolute top-0 bottom-0 w-0.5 bg-white/80 pointer-events-none z-10"
              style={{ left: `${(currentTime / videoDuration) * 100}%` }}
            >
              <div className="absolute -top-0.5 -left-1 w-2.5 h-2.5 rounded-full bg-white shadow" />
            </div>
          </div>

          {/* Time scale */}
          <div className="flex justify-between mt-1 text-[9px] text-zinc-600 font-mono">
            <span>0:00</span>
            <span>{formatTime(videoDuration * 0.25)}</span>
            <span>{formatTime(videoDuration * 0.5)}</span>
            <span>{formatTime(videoDuration * 0.75)}</span>
            <span>{formatTime(videoDuration)}</span>
          </div>
        </Card>

        {/* Active clip detail edit */}
        {clips[activeClipIndex] && (
          <Card className="p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-medium text-zinc-400 uppercase tracking-wider">
                Clip #{clips[activeClipIndex].rank} — Timing
              </span>
              {clips[activeClipIndex].modified && (
                <button
                  type="button"
                  onClick={() => resetClip(activeClipIndex)}
                  className="flex items-center gap-1 text-[10px] text-amber-400 hover:text-amber-300 font-medium"
                >
                  <RotateCcw className="h-2.5 w-2.5" />
                  Reset to AI
                </button>
              )}
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-[9px] text-zinc-600 mb-0.5">Start</label>
                <input
                  type="number"
                  step={0.1}
                  min={0}
                  max={clips[activeClipIndex].end - 5}
                  value={clips[activeClipIndex].start.toFixed(1)}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    if (isNaN(val)) return;
                    const updated = [...clips];
                    const clip = updated[activeClipIndex];
                    clip.start = Math.max(0, Math.min(val, clip.end - 5));
                    clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
                    clip.modified = clip.start !== clip.ai_start || clip.end !== clip.ai_end;
                    onClipsChange(updated);
                  }}
                  className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-200 font-mono focus:border-emerald-500/50 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[9px] text-zinc-600 mb-0.5">End</label>
                <input
                  type="number"
                  step={0.1}
                  min={clips[activeClipIndex].start + 5}
                  max={videoDuration}
                  value={clips[activeClipIndex].end.toFixed(1)}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    if (isNaN(val)) return;
                    const updated = [...clips];
                    const clip = updated[activeClipIndex];
                    clip.end = Math.min(videoDuration, Math.max(val, clip.start + 5));
                    clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
                    clip.modified = clip.start !== clip.ai_start || clip.end !== clip.ai_end;
                    onClipsChange(updated);
                  }}
                  className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-200 font-mono focus:border-emerald-500/50 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[9px] text-zinc-600 mb-0.5">Duration</label>
                <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-2 py-1.5 text-xs text-zinc-400 font-mono">
                  {clips[activeClipIndex].duration.toFixed(1)}s
                </div>
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
