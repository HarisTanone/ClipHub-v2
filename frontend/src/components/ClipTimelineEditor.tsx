import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  FastForward,
  Rewind,
  Sparkles,
  HelpCircle,
  Shield,
  Copy,
  Heart,
  MessageSquare,
  Share2,
  Volume2,
  VolumeX,
  Repeat,
  ZoomIn,
  ZoomOut,
  Maximize2,
  X,
  BookmarkPlus,
  ArrowRightToLine,
  ArrowLeftToLine,
  Sliders,
  Check,
  Magnet,
  Eye,
  EyeOff,
  ChevronDown,
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
  /** Whether this clip is selected/included for final rendering (default: true) */
  included?: boolean;
}

interface ClipTimelineEditorProps {
  clips: EditableClip[];
  videoDuration: number;
  videoSrc: string;
  onClipsChange: (clips: EditableClip[]) => void;
  activeClipIndex?: number;
  onActiveClipChange?: (index: number) => void;
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
  activeClipIndex: controlledActiveIndex,
  onActiveClipChange,
}: ClipTimelineEditorProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const timelineScrollRef = useRef<HTMLDivElement>(null);
  const timelineTrackRef = useRef<HTMLDivElement>(null);
  const minimapRef = useRef<HTMLDivElement>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [hoverTime, setHoverTime] = useState<number | null>(null);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);
  const [volume, setVolume] = useState<number>(1);
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [isLoopingActive, setIsLoopingActive] = useState<boolean>(false);
  const [showSafeZone, setShowSafeZone] = useState<boolean>(false);
  const [showShortcutsModal, setShowShortcutsModal] = useState<boolean>(false);
  const [internalActiveIndex, setInternalActiveIndex] = useState(0);
  const [startInputText, setStartInputText] = useState("");
  const [endInputText, setEndInputText] = useState("");

  // Timeline zoom: 1 (fit) to 10 (10x zoom)
  const [zoomLevel, setZoomLevel] = useState<number>(1);
  const [enableSnapping, setEnableSnapping] = useState<boolean>(true);

  // Dragging state
  const [dragging, setDragging] = useState<{
    clipIndex: number;
    handle: "start" | "end" | "move";
    initialTime: number;
    initialStart: number;
    initialEnd: number;
  } | null>(null);

  const activeClipIndex = controlledActiveIndex !== undefined ? controlledActiveIndex : internalActiveIndex;

  const setActiveClip = useCallback(
    (idx: number) => {
      if (onActiveClipChange) {
        onActiveClipChange(idx);
      } else {
        setInternalActiveIndex(idx);
      }
    },
    [onActiveClipChange]
  );

  const activeClip = clips[activeClipIndex] || null;

  // Sync inputs with active clip
  useEffect(() => {
    if (activeClip) {
      setStartInputText(formatTimePrecise(activeClip.start));
      setEndInputText(formatTimePrecise(activeClip.end));
    }
  }, [activeClip?.start, activeClip?.end, activeClipIndex]);

  // Video timeupdate and loop / auto-stop handling
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onTimeUpdate = () => {
      const t = video.currentTime;
      setCurrentTime(t);

      const curClip = clips[activeClipIndex];
      if (curClip && !video.paused) {
        if (t >= curClip.end) {
          if (isLoopingActive) {
            video.currentTime = curClip.start;
            setCurrentTime(curClip.start);
          } else {
            video.pause();
            video.currentTime = curClip.end;
            setCurrentTime(curClip.end);
            setIsPlaying(false);
          }
        }
      }
    };

    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);

    video.addEventListener("timeupdate", onTimeUpdate);
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);

    return () => {
      video.removeEventListener("timeupdate", onTimeUpdate);
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
    };
  }, [clips, activeClipIndex, isLoopingActive]);

  // Sync volume / mute
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.volume = isMuted ? 0 : volume;
  }, [volume, isMuted]);

  // Toggle play/pause
  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    const curClip = clips[activeClipIndex];

    if (video.paused) {
      if (curClip && video.currentTime >= curClip.end - 0.2) {
        video.currentTime = curClip.start;
        setCurrentTime(curClip.start);
      }
      video.play().catch(() => {});
    } else {
      video.pause();
    }
  }, [clips, activeClipIndex]);

  // Seek relative
  const seekRelative = useCallback(
    (delta: number) => {
      const video = videoRef.current;
      if (!video) return;
      const target = Math.max(0, Math.min(videoDuration, video.currentTime + delta));
      video.currentTime = target;
      setCurrentTime(target);
    },
    [videoDuration]
  );

  // Seek directly
  const seekTo = useCallback(
    (time: number, autoPlay: boolean = false) => {
      const video = videoRef.current;
      if (!video) return;
      const clamped = Math.max(0, Math.min(videoDuration, time));
      video.currentTime = clamped;
      setCurrentTime(clamped);
      if (autoPlay) {
        video.play().catch(() => {});
      }
    },
    [videoDuration]
  );

  // Seek to clip and set active
  const seekToClip = useCallback(
    (index: number, autoPlay: boolean = true) => {
      const video = videoRef.current;
      if (!video || !clips[index]) return;
      setActiveClip(index);
      const targetClip = clips[index];
      video.currentTime = targetClip.start;
      setCurrentTime(targetClip.start);
      if (autoPlay) {
        video.play().catch(() => {});
      }
    },
    [clips, setActiveClip]
  );

  // Jump to clip start / end
  const jumpToActiveStart = useCallback(() => {
    if (!activeClip || !videoRef.current) return;
    seekTo(activeClip.start);
  }, [activeClip, seekTo]);

  const jumpToActiveEnd = useCallback(() => {
    if (!activeClip || !videoRef.current) return;
    seekTo(activeClip.end);
  }, [activeClip, seekTo]);

  // Reset single clip
  const resetClip = useCallback(
    (index: number) => {
      const updated = [...clips];
      updated[index] = {
        ...updated[index],
        start: updated[index].ai_start,
        end: updated[index].ai_end,
        duration: Math.round((updated[index].ai_end - updated[index].ai_start) * 100) / 100,
        modified: false,
      };
      onClipsChange(updated);
    },
    [clips, onClipsChange]
  );

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

  // Toggle clip inclusion
  const toggleClipInclusion = useCallback(
    (index: number) => {
      const updated = [...clips];
      const isCurrentlyIncluded = updated[index].included !== false;
      updated[index] = {
        ...updated[index],
        included: !isCurrentlyIncluded,
      };
      onClipsChange(updated);
    },
    [clips, onClipsChange]
  );

  // Add clip at playhead
  const addClipAtTime = useCallback(
    (targetTime?: number, defaultLen: number = 45) => {
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
        included: true,
      };

      const updated = [...clips, newClip];
      onClipsChange(updated);
      setActiveClip(updated.length - 1);
      seekTo(start);
    },
    [clips, currentTime, videoDuration, onClipsChange, setActiveClip, seekTo]
  );

  // Duplicate clip
  const duplicateClip = useCallback(
    (index: number) => {
      const source = clips[index];
      if (!source) return;
      const len = source.end - source.start;
      const newStart = Math.min(videoDuration - 5, source.end + 0.5);
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
        included: true,
      };

      const updated = [...clips, newClip];
      onClipsChange(updated);
      setActiveClip(updated.length - 1);
    },
    [clips, videoDuration, onClipsChange, setActiveClip]
  );

  // Delete clip
  const deleteClip = useCallback(
    (index: number) => {
      if (clips.length <= 1) return;
      const updated = clips.filter((_, i) => i !== index);
      updated.forEach((c, i) => {
        c.rank = i + 1;
      });
      onClipsChange(updated);
      setActiveClip(Math.min(activeClipIndex, updated.length - 1));
    },
    [clips, activeClipIndex, onClipsChange, setActiveClip]
  );

  // Exact duration quick preset
  const setExactDuration = useCallback(
    (desiredDuration: number) => {
      if (!activeClip) return;
      const updated = [...clips];
      const clip = updated[activeClipIndex];
      const newEnd = Math.min(videoDuration, clip.start + desiredDuration);
      clip.end = Math.round(newEnd * 10) / 10;
      clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
      clip.modified = clip.start !== clip.ai_start || clip.end !== clip.ai_end;
      onClipsChange(updated);
    },
    [activeClip, activeClipIndex, clips, videoDuration, onClipsChange]
  );

  // Nudge timing helpers
  const nudgeStart = useCallback(
    (delta: number) => {
      if (!activeClip) return;
      const updated = [...clips];
      const clip = updated[activeClipIndex];
      const minDuration = 5;
      const newStart = Math.max(0, Math.min(clip.start + delta, clip.end - minDuration));
      clip.start = Math.round(newStart * 10) / 10;
      clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
      clip.modified = clip.start !== clip.ai_start || clip.end !== clip.ai_end;
      onClipsChange(updated);
      seekTo(clip.start);
    },
    [activeClip, activeClipIndex, clips, onClipsChange, seekTo]
  );

  const nudgeEnd = useCallback(
    (delta: number) => {
      if (!activeClip) return;
      const updated = [...clips];
      const clip = updated[activeClipIndex];
      const minDuration = 5;
      const newEnd = Math.min(videoDuration, Math.max(clip.end + delta, clip.start + minDuration));
      clip.end = Math.round(newEnd * 10) / 10;
      clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
      clip.modified = clip.start !== clip.ai_start || clip.end !== clip.ai_end;
      onClipsChange(updated);
      seekTo(clip.end);
    },
    [activeClip, activeClipIndex, clips, videoDuration, onClipsChange, seekTo]
  );

  // Set start / end to current playhead
  const setStartToPlayhead = useCallback(() => {
    if (!activeClip) return;
    const updated = [...clips];
    const clip = updated[activeClipIndex];
    const minDuration = 5;
    if (currentTime >= clip.end - minDuration) {
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
  const updateHookTitle = useCallback(
    (text: string) => {
      if (!activeClip) return;
      const updated = [...clips];
      updated[activeClipIndex].hook = text;
      updated[activeClipIndex].modified = true;
      onClipsChange(updated);
    },
    [activeClip, activeClipIndex, clips, onClipsChange]
  );

  // ─── Multi-Track Lane Assignment (Greedy Interval Scheduling) ─────────────
  const { clipLanes, totalLanes } = useMemo(() => {
    const indexed = clips.map((clip, originalIndex) => ({ clip, originalIndex }));
    indexed.sort((a, b) => a.clip.start - b.clip.start);

    const laneEndTimes: number[] = [];
    const assignment = new Map<number, number>(); // originalIndex -> lane

    for (const item of indexed) {
      let placedLane = -1;
      for (let l = 0; l < laneEndTimes.length; l++) {
        if (laneEndTimes[l] <= item.clip.start) {
          placedLane = l;
          laneEndTimes[l] = item.clip.end;
          break;
        }
      }
      if (placedLane === -1) {
        placedLane = laneEndTimes.length;
        laneEndTimes.push(item.clip.end);
      }
      assignment.set(item.originalIndex, placedLane);
    }

    return {
      clipLanes: assignment,
      totalLanes: Math.max(1, laneEndTimes.length),
    };
  }, [clips]);

  // ─── Snapping Helper ───────────────────────────────────────────────────────
  const applySnap = useCallback(
    (targetTime: number, excludeClipIndex: number): number => {
      if (!enableSnapping) return targetTime;
      const SNAP_THRESHOLD = 0.5; // seconds
      let bestTime = targetTime;
      let minDiff = SNAP_THRESHOLD;

      // Check playhead
      const playheadDiff = Math.abs(currentTime - targetTime);
      if (playheadDiff < minDiff) {
        bestTime = currentTime;
        minDiff = playheadDiff;
      }

      // Check other clip boundaries
      clips.forEach((c, idx) => {
        if (idx === excludeClipIndex) return;
        const diffStart = Math.abs(c.start - targetTime);
        if (diffStart < minDiff) {
          bestTime = c.start;
          minDiff = diffStart;
        }
        const diffEnd = Math.abs(c.end - targetTime);
        if (diffEnd < minDiff) {
          bestTime = c.end;
          minDiff = diffEnd;
        }
      });

      return bestTime;
    },
    [enableSnapping, currentTime, clips]
  );

  // ─── Timeline Mouse Drag Handler ──────────────────────────────────────────
  const handleTimelineMouseDown = useCallback(
    (e: React.MouseEvent, clipIndex: number, handle: "start" | "end" | "move") => {
      e.preventDefault();
      e.stopPropagation();
      const track = timelineTrackRef.current;
      if (!track) return;
      const rect = track.getBoundingClientRect();
      const clickRatio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const clickTime = clickRatio * videoDuration;

      setActiveClip(clipIndex);
      setDragging({
        clipIndex,
        handle,
        initialTime: clickTime,
        initialStart: clips[clipIndex].start,
        initialEnd: clips[clipIndex].end,
      });
    },
    [clips, videoDuration, setActiveClip]
  );

  useEffect(() => {
    if (!dragging) return;

    const onMouseMove = (e: MouseEvent) => {
      const track = timelineTrackRef.current;
      if (!track) return;
      const rect = track.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      let currentMouseTime = ratio * videoDuration;

      const updated = [...clips];
      const clip = updated[dragging.clipIndex];
      const minDuration = 5;
      const clipLen = dragging.initialEnd - dragging.initialStart;

      if (dragging.handle === "start") {
        currentMouseTime = applySnap(currentMouseTime, dragging.clipIndex);
        const maxStart = clip.end - minDuration;
        clip.start = Math.max(0, Math.min(currentMouseTime, maxStart));
        clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
        seekTo(clip.start);
      } else if (dragging.handle === "end") {
        currentMouseTime = applySnap(currentMouseTime, dragging.clipIndex);
        const minEnd = clip.start + minDuration;
        clip.end = Math.min(videoDuration, Math.max(currentMouseTime, minEnd));
        clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
        seekTo(clip.end);
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
        seekTo(clip.start);
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
  }, [dragging, clips, videoDuration, onClipsChange, applySnap, seekTo]);

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
        seekToClip(activeClipIndex, true);
      } else if (e.key === "m" || e.key === "M") {
        e.preventDefault();
        setIsMuted((prev) => !prev);
      } else if (e.key === "s" || e.key === "S") {
        e.preventDefault();
        setEnableSnapping((prev) => !prev);
      } else if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        setZoomLevel((prev) => Math.min(10, prev + 1));
      } else if (e.key === "-" || e.key === "_") {
        e.preventDefault();
        setZoomLevel((prev) => Math.max(1, prev - 1));
      } else if (e.key === "?") {
        e.preventDefault();
        setShowShortcutsModal((prev) => !prev);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    togglePlay,
    seekRelative,
    setStartToPlayhead,
    setEndToPlayhead,
    addClipAtTime,
    seekToClip,
    activeClipIndex,
  ]);

  // Keep playhead in view when playing or scrubbing in zoomed mode
  useEffect(() => {
    if (zoomLevel <= 1 || !timelineScrollRef.current || !timelineTrackRef.current) return;
    const container = timelineScrollRef.current;
    const trackWidth = timelineTrackRef.current.clientWidth;
    const playheadX = (currentTime / videoDuration) * trackWidth;

    const scrollLeft = container.scrollLeft;
    const clientWidth = container.clientWidth;
    const margin = 120;

    if (playheadX < scrollLeft + margin) {
      container.scrollLeft = Math.max(0, playheadX - margin);
    } else if (playheadX > scrollLeft + clientWidth - margin) {
      container.scrollLeft = playheadX - clientWidth + margin;
    }
  }, [currentTime, videoDuration, zoomLevel]);

  // Dynamic Ruler Graduations
  const rulerTicks = useMemo(() => {
    if (videoDuration <= 0) return [];
    let baseInterval = 10;
    if (videoDuration > 1800) baseInterval = 120;
    else if (videoDuration > 600) baseInterval = 60;
    else if (videoDuration > 180) baseInterval = 30;
    else if (videoDuration > 60) baseInterval = 15;

    const interval = Math.max(1, baseInterval / zoomLevel);
    const count = Math.ceil(videoDuration / interval);
    const ticks: { time: number; label?: string; isMajor: boolean }[] = [];

    for (let i = 0; i <= count; i++) {
      const t = Math.min(videoDuration, i * interval);
      const isMajor = i % 2 === 0 || count < 15;
      ticks.push({
        time: t,
        label: isMajor ? formatTimePrecise(t) : undefined,
        isMajor,
      });
    }
    return ticks;
  }, [videoDuration, zoomLevel]);

  return (
    <div className="flex flex-col gap-3.5 min-h-0 relative select-none">
      {/* ─── VIDEO PLAYER CONTAINER ────────────────────────────────────────── */}
      <div className="relative rounded-2xl overflow-hidden border border-zinc-800/80 bg-black shadow-2xl">
        <div className="relative w-full aspect-video max-h-[480px] bg-black flex items-center justify-center">
          <video
            ref={videoRef}
            src={videoSrc}
            className="w-full h-full object-contain bg-black"
            preload="metadata"
            playsInline
            onEnded={() => setIsPlaying(false)}
          />

          {/* Social Safe Zone Mockup Overlay (9:16 TikTok / Reels simulator) */}
          {showSafeZone && (
            <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
              <div className="h-full aspect-[9/16] border-2 border-dashed border-sky-400/80 bg-sky-500/[0.05] relative flex flex-col justify-between p-3 select-none backdrop-blur-[0.5px]">
                <div className="rounded-md border border-sky-400/40 bg-sky-500/25 px-2 py-0.5 text-[9px] font-bold text-sky-200 text-center tracking-wider uppercase shadow">
                  9:16 Top Safe Zone
                </div>
                <div className="absolute right-3 bottom-20 flex flex-col items-center gap-3 pointer-events-auto opacity-90">
                  <div className="w-8 h-8 rounded-full bg-black/70 border border-sky-400/50 flex items-center justify-center shadow-lg">
                    <Heart className="w-4 h-4 fill-rose-500 text-rose-500" />
                  </div>
                  <div className="w-8 h-8 rounded-full bg-black/70 border border-sky-400/50 flex items-center justify-center shadow-lg">
                    <MessageSquare className="w-4 h-4 text-zinc-200" />
                  </div>
                  <div className="w-8 h-8 rounded-full bg-black/70 border border-sky-400/50 flex items-center justify-center shadow-lg">
                    <Share2 className="w-4 h-4 text-zinc-200" />
                  </div>
                </div>
                <div className="rounded-lg border border-sky-400/40 bg-black/80 p-2 text-[9px] font-medium text-sky-200 text-left w-3/4 space-y-1 shadow-lg backdrop-blur-md">
                  <p className="font-bold text-white flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />
                    Area Teks & Subtitle Aman
                  </p>
                  <p className="text-[8px] text-zinc-400 leading-tight">
                    Simulasi tampilan antarmuka TikTok, Reels, & Shorts agar judul hook tidak tertutup tombol.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Center Play Overlay Button */}
          <button
            type="button"
            onClick={togglePlay}
            className="absolute inset-0 flex items-center justify-center bg-transparent hover:bg-black/20 transition-colors group cursor-pointer"
          >
            {!isPlaying && (
              <span className="flex h-16 w-16 items-center justify-center rounded-full bg-black/75 text-white opacity-90 group-hover:opacity-100 group-hover:scale-105 transition-all shadow-2xl backdrop-blur-md border border-white/20">
                <Play className="h-7 w-7 ml-1 fill-current text-emerald-400" />
              </span>
            )}
          </button>

          {/* Control Bar Overlay on Video */}
          <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between gap-3 rounded-xl bg-zinc-950/85 px-3 py-2 text-xs font-mono text-white backdrop-blur-md border border-zinc-800/90 shadow-xl">
            {/* Left controls */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={togglePlay}
                className="hover:text-emerald-400 transition-colors p-1 rounded-md hover:bg-zinc-800"
                title="Play/Pause (Space)"
              >
                {isPlaying ? <Pause className="h-4 w-4 fill-current text-emerald-400" /> : <Play className="h-4 w-4 fill-current" />}
              </button>
              <button
                type="button"
                onClick={() => seekRelative(-5)}
                className="text-zinc-400 hover:text-white p-1 rounded-md hover:bg-zinc-800 transition-colors"
                title="Mundur 5s (J)"
              >
                <Rewind className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => seekRelative(5)}
                className="text-zinc-400 hover:text-white p-1 rounded-md hover:bg-zinc-800 transition-colors"
                title="Maju 5s (L)"
              >
                <FastForward className="h-3.5 w-3.5" />
              </button>

              <div className="h-4 w-px bg-zinc-800 mx-1" />

              <span className="font-semibold text-emerald-300">{formatTimePrecise(currentTime)}</span>
              <span className="text-zinc-600">/</span>
              <span className="text-zinc-400">{formatTimePrecise(videoDuration)}</span>
            </div>

            {/* Right controls */}
            <div className="flex items-center gap-2">
              {/* Volume control */}
              <div className="flex items-center gap-1.5 bg-zinc-900/90 rounded-lg px-2 py-1 border border-zinc-800">
                <button
                  type="button"
                  onClick={() => setIsMuted(!isMuted)}
                  className="text-zinc-400 hover:text-white transition-colors"
                  title="Mute / Unmute (M)"
                >
                  {isMuted || volume === 0 ? (
                    <VolumeX className="h-3.5 w-3.5 text-rose-400" />
                  ) : (
                    <Volume2 className="h-3.5 w-3.5 text-emerald-400" />
                  )}
                </button>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={isMuted ? 0 : volume}
                  onChange={(e) => {
                    setVolume(parseFloat(e.target.value));
                    setIsMuted(false);
                  }}
                  className="w-14 h-1 accent-emerald-500 cursor-pointer"
                  title={`Volume: ${Math.round((isMuted ? 0 : volume) * 100)}%`}
                />
              </div>

              {/* Loop Active Clip Toggle */}
              <button
                type="button"
                onClick={() => setIsLoopingActive(!isLoopingActive)}
                className={cn(
                  "flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-sans font-medium transition-colors border",
                  isLoopingActive
                    ? "border-emerald-500/50 bg-emerald-500/20 text-emerald-300 shadow-sm"
                    : "border-zinc-800 bg-zinc-900/80 text-zinc-400 hover:text-zinc-200"
                )}
                title="Ulangi klip aktif terus menerus saat diputar"
              >
                <Repeat className="h-3 w-3" />
                <span className="hidden sm:inline">Loop Klip</span>
              </button>

              {/* Playback Speed dropdown/pills */}
              <div className="flex items-center bg-zinc-900/90 rounded-lg border border-zinc-800 p-0.5">
                {[0.75, 1, 1.25, 1.5, 2].map((spd) => (
                  <button
                    key={spd}
                    type="button"
                    onClick={() => {
                      if (videoRef.current) videoRef.current.playbackRate = spd;
                      setPlaybackSpeed(spd);
                    }}
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

              {/* 9:16 Safe Zone Simulator */}
              <button
                type="button"
                onClick={() => setShowSafeZone(!showSafeZone)}
                className={cn(
                  "flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-sans font-medium transition-colors border",
                  showSafeZone
                    ? "border-sky-500/50 bg-sky-500/20 text-sky-300"
                    : "border-zinc-800 bg-zinc-900/80 text-zinc-400 hover:text-zinc-200"
                )}
                title="Toggle Simulasi 9:16 Safe Zone UI"
              >
                <Shield className="h-3 w-3" />
                <span className="hidden sm:inline">9:16 Safe Zone</span>
              </button>

              {/* Shortcuts modal toggle */}
              <button
                type="button"
                onClick={() => setShowShortcutsModal(!showShortcutsModal)}
                className="p-1 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
                title="Pintasan Keyboard (?)"
              >
                <HelpCircle className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Shortcuts modal */}
      {showShortcutsModal && (
        <div className="p-3.5 rounded-2xl border border-zinc-700/80 bg-zinc-900/95 text-xs space-y-2.5 shadow-2xl backdrop-blur-md">
          <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
            <span className="font-semibold text-zinc-100 flex items-center gap-1.5">
              <HelpCircle className="h-4 w-4 text-emerald-400" />
              Pintasan Keyboard Editor Timeline
            </span>
            <button
              type="button"
              onClick={() => setShowShortcutsModal(false)}
              className="text-zinc-500 hover:text-zinc-300 p-0.5 rounded"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-[10px]">
            <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">Space</kbd> Play / Pause</div>
            <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">J</kbd> / <kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">L</kbd> Mundur / Maju 5s</div>
            <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">[</kbd> Set Titik Mulai (Start)</div>
            <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">]</kbd> Set Titik Selesai (End)</div>
            <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">N</kbd> Buat Klip Baru di Sini</div>
            <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">P</kbd> Pratinjau Klip Aktif</div>
            <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">+</kbd> / <kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">-</kbd> Zoom In / Out</div>
            <div><kbd className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono border border-zinc-700 text-emerald-300">S</kbd> Toggle Magnet Snap</div>
          </div>
        </div>
      )}

      {/* ─── QUICK TIMELINE ACTIONS BAR ─────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 p-2.5 rounded-2xl bg-zinc-900/80 border border-zinc-800/90 shadow-sm">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider pl-1">
            Set Titik:
          </span>
          <button
            type="button"
            onClick={setStartToPlayhead}
            className="flex items-center gap-1.5 rounded-xl bg-emerald-500/15 border border-emerald-500/30 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/25 transition-all shadow-sm"
            title="Set awal klip aktif pada posisi playhead video saat ini (Pintasan: [)"
          >
            <ArrowRightToLine className="h-3.5 w-3.5" />
            Mulai di Sini <span className="text-[10px] opacity-60 font-mono">[</span>
          </button>
          <button
            type="button"
            onClick={setEndToPlayhead}
            className="flex items-center gap-1.5 rounded-xl bg-emerald-500/15 border border-emerald-500/30 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/25 transition-all shadow-sm"
            title="Set akhir klip aktif pada posisi playhead video saat ini (Pintasan: ])"
          >
            <ArrowLeftToLine className="h-3.5 w-3.5" />
            Selesai di Sini <span className="text-[10px] opacity-60 font-mono">]</span>
          </button>
          <button
            type="button"
            onClick={() => addClipAtTime(currentTime, 45)}
            className="flex items-center gap-1.5 rounded-xl bg-sky-500/20 border border-sky-500/40 px-3 py-1.5 text-xs font-semibold text-sky-200 hover:bg-sky-500/30 transition-all shadow-sm"
            title="Buat klip baru 45 detik mulai dari posisi sekarang (Pintasan: N)"
          >
            <BookmarkPlus className="h-3.5 w-3.5 text-sky-300" />
            + Klip Baru (45s)
          </button>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] font-medium text-zinc-400">Durasi Cepat:</span>
          {[30, 45, 60, 90].map((sec) => (
            <button
              key={sec}
              type="button"
              onClick={() => setExactDuration(sec)}
              className="px-2.5 py-1 rounded-lg bg-zinc-800/90 hover:bg-zinc-700 text-xs font-mono text-zinc-300 hover:text-white transition-colors"
              title={`Ubah durasi klip aktif menjadi ${sec} detik`}
            >
              {sec}s
            </button>
          ))}
          <button
            type="button"
            onClick={() => setEnableSnapping(!enableSnapping)}
            className={cn(
              "flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors border ml-1",
              enableSnapping
                ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                : "border-zinc-800 bg-zinc-900 text-zinc-500 hover:text-zinc-300"
            )}
            title="Snap ke playhead & batas klip (Pintasan: S)"
          >
            <Magnet className="h-3 w-3" />
            Snap
          </button>
        </div>
      </div>

      {/* ─── VISUAL TIMELINE CARD (Mini-Map + Zoom + Multi-Track) ──────────── */}
      <Card className="p-3.5 space-y-3 border-zinc-800 bg-zinc-950/90 rounded-2xl shadow-xl">
        {/* Timeline Header with Title & Zoom Controls */}
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2">
            <Film className="h-4 w-4 text-emerald-400" />
            <span className="font-bold text-zinc-100">Visual Multi-Track Timeline</span>
            <span className="text-[10px] text-zinc-400 bg-zinc-900 border border-zinc-800 px-2 py-0.5 rounded-full">
              {totalLanes > 1 ? `${totalLanes} Track Aktif (Anti-Overlap)` : "1 Track Utama"}
            </span>
          </div>

          {/* Zoom controls */}
          <div className="flex items-center gap-2 bg-zinc-900/90 border border-zinc-800/80 rounded-xl px-2 py-1">
            <span className="text-[10px] text-zinc-400 font-medium">Zoom:</span>
            <button
              type="button"
              onClick={() => setZoomLevel((z) => Math.max(1, z - 1))}
              disabled={zoomLevel <= 1}
              className="p-1 rounded text-zinc-400 hover:text-white hover:bg-zinc-800 disabled:opacity-40 transition-colors"
              title="Zoom Out (-)"
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </button>
            <input
              type="range"
              min="1"
              max="10"
              step="1"
              value={zoomLevel}
              onChange={(e) => setZoomLevel(parseInt(e.target.value, 10))}
              className="w-20 h-1 accent-emerald-500 cursor-pointer"
              title={`Zoom: ${zoomLevel}x`}
            />
            <button
              type="button"
              onClick={() => setZoomLevel((z) => Math.min(10, z + 1))}
              disabled={zoomLevel >= 10}
              className="p-1 rounded text-zinc-400 hover:text-white hover:bg-zinc-800 disabled:opacity-40 transition-colors"
              title="Zoom In (+)"
            >
              <ZoomIn className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setZoomLevel(1)}
              className="text-[10px] font-medium text-emerald-400 hover:text-emerald-300 px-1.5 py-0.5 rounded hover:bg-emerald-500/10 transition-colors"
              title="Reset Zoom ke 1x (Fit Video)"
            >
              Fit
            </button>
          </div>
        </div>

        {/* ─── 1. MINI-MAP OVERVIEW BAR (Selalu Menampilkan Seluruh Video) ───── */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[9px] text-zinc-500 font-mono">
            <span>Ikhtisar Video Penuh</span>
            <span>0:00 s/d {formatTime(videoDuration)}</span>
          </div>
          <div
            ref={minimapRef}
            className="relative h-6 w-full rounded-lg bg-zinc-900/90 border border-zinc-800/80 overflow-hidden cursor-pointer"
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
              seekTo(ratio * videoDuration);
            }}
            title="Klik untuk berpindah posisi playhead secara instan di video penuh"
          >
            {/* Background ticks */}
            <div className="absolute inset-0 flex justify-between pointer-events-none opacity-15">
              {Array.from({ length: 15 }).map((_, i) => (
                <div key={i} className="h-full w-px bg-zinc-400" />
              ))}
            </div>

            {/* Clips on Mini-map */}
            {clips.map((clip, idx) => {
              const left = (clip.start / videoDuration) * 100;
              const width = Math.max(0.8, ((clip.end - clip.start) / videoDuration) * 100);
              const isActive = idx === activeClipIndex;
              const isIncluded = clip.included !== false;

              return (
                <div
                  key={`minimap-${clip.rank}-${idx}`}
                  className={cn(
                    "absolute top-0.5 bottom-0.5 rounded-sm transition-all pointer-events-none",
                    !isIncluded
                      ? "bg-zinc-600/40"
                      : isActive
                        ? "bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.8)]"
                        : clip.manual
                          ? "bg-sky-400/70"
                          : "bg-violet-400/70"
                  )}
                  style={{ left: `${left}%`, width: `${width}%` }}
                />
              );
            })}

            {/* Mini-map Playhead */}
            <div
              className="absolute top-0 bottom-0 w-0.5 bg-white shadow-[0_0_6px_#fff] pointer-events-none z-10"
              style={{ left: `${(currentTime / videoDuration) * 100}%` }}
            />
          </div>
        </div>

        {/* ─── 2. MAIN SCROLLABLE TIMELINE TRACK ────────────────────────────── */}
        <div
          ref={timelineScrollRef}
          className="relative overflow-x-auto rounded-xl border border-zinc-800/90 bg-zinc-950 p-2 select-none"
        >
          <div
            ref={timelineTrackRef}
            className="relative cursor-crosshair"
            style={{ width: `${100 * zoomLevel}%`, minWidth: "100%" }}
            onMouseMove={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
              setHoverTime(ratio * videoDuration);
            }}
            onMouseLeave={() => setHoverTime(null)}
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
              seekTo(ratio * videoDuration);
            }}
            onDoubleClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
              addClipAtTime(ratio * videoDuration, 45);
            }}
          >
            {/* Dynamic Time Ruler Header */}
            <div className="relative h-6 border-b border-zinc-800 mb-1 pointer-events-none">
              {rulerTicks.map((tick, i) => {
                const left = (tick.time / videoDuration) * 100;
                return (
                  <div
                    key={i}
                    className="absolute top-0 bottom-0 flex flex-col items-center pointer-events-none"
                    style={{ left: `${left}%` }}
                  >
                    <div className={cn("w-px bg-zinc-700", tick.isMajor ? "h-2.5 bg-zinc-500" : "h-1.5")} />
                    {tick.label && (
                      <span className="text-[8px] font-mono text-zinc-500 mt-0.5 -translate-x-1/2">
                        {tick.label}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Track Lanes Container */}
            <div
              className="relative space-y-1.5 py-1"
              style={{ minHeight: `${totalLanes * 46}px` }}
            >
              {/* Background Grid Guidelines */}
              <div className="absolute inset-0 flex justify-between pointer-events-none opacity-10">
                {Array.from({ length: 20 * zoomLevel }).map((_, i) => (
                  <div key={i} className="h-full w-px bg-zinc-400" />
                ))}
              </div>

              {/* Render Lanes */}
              {Array.from({ length: totalLanes }).map((_, laneIdx) => (
                <div
                  key={`lane-${laneIdx}`}
                  className="relative h-10 w-full rounded-lg bg-zinc-900/40 border border-zinc-800/40"
                >
                  {/* Lane Label */}
                  {totalLanes > 1 && (
                    <span className="absolute left-1.5 top-1 text-[8px] font-bold text-zinc-600 uppercase pointer-events-none">
                      Track {laneIdx + 1}
                    </span>
                  )}
                </div>
              ))}

              {/* Clip Blocks Positioned in Their Assigned Lane */}
              {clips.map((clip, idx) => {
                const clampedStart = Math.max(0, Math.min(clip.start, videoDuration));
                const clampedEnd = Math.max(0, Math.min(clip.end, videoDuration));
                if (clampedEnd <= clampedStart) return null;
                const left = (clampedStart / videoDuration) * 100;
                const width = ((clampedEnd - clampedStart) / videoDuration) * 100;
                const isActive = idx === activeClipIndex;
                const lane = clipLanes.get(idx) || 0;
                const laneTop = lane * (40 + 6) + 4; // 40px lane height + 6px space
                const isIncluded = clip.included !== false;

                return (
                  <div
                    key={`${clip.rank}-${idx}`}
                    className={cn(
                      "absolute rounded-xl border-2 transition-all select-none group/clip cursor-grab active:cursor-grabbing",
                      !isIncluded && "opacity-40 grayscale-[40%]",
                      isActive
                        ? "bg-emerald-500/35 border-emerald-400 z-20 shadow-[0_0_16px_rgba(16,185,129,0.45)] ring-1 ring-emerald-400/60"
                        : clip.manual
                          ? "bg-sky-500/20 border-sky-500/60 hover:border-sky-400 z-10"
                          : "bg-violet-500/20 border-violet-500/60 hover:border-violet-400 z-10",
                      clip.modified && !clip.manual && "border-amber-400"
                    )}
                    style={{
                      left: `${left}%`,
                      width: `${Math.max(width, 0.6)}%`,
                      top: `${laneTop}px`,
                      height: "38px",
                    }}
                    onMouseDown={(e) => handleTimelineMouseDown(e, idx, "move")}
                    onClick={(e) => {
                      e.stopPropagation();
                      seekToClip(idx);
                    }}
                    title="Geser bagian tengah untuk memindahkan posisi seluruh klip"
                  >
                    {/* Clip Info Label */}
                    <div className="absolute top-1 left-3 right-3 flex items-center justify-between pointer-events-none overflow-hidden">
                      <div className="flex items-center gap-1 min-w-0">
                        <span
                          className={cn(
                            "text-[9px] font-black px-1.5 py-0.2 rounded shrink-0",
                            isActive
                              ? "bg-emerald-400 text-zinc-950"
                              : clip.manual
                                ? "bg-sky-400 text-zinc-950"
                                : "bg-violet-400 text-zinc-950"
                          )}
                        >
                          #{clip.rank}
                        </span>
                        {clip.hook && (
                          <span className="text-[9px] font-semibold text-zinc-200 truncate hidden sm:inline">
                            {clip.hook}
                          </span>
                        )}
                      </div>
                      <span className="text-[9px] font-mono font-bold text-white bg-black/70 px-1 rounded shrink-0">
                        {clip.duration.toFixed(1)}s
                      </span>
                    </div>

                    {/* Left (Start) Ergonomic Grab Handle */}
                    <div
                      className="absolute left-0 top-0 bottom-0 w-3.5 cursor-col-resize flex items-center justify-center bg-emerald-500/50 hover:bg-emerald-400 rounded-l-lg transition-colors group-hover/clip:bg-emerald-400"
                      onMouseDown={(e) => handleTimelineMouseDown(e, idx, "start")}
                      title="Tarik untuk mengatur Titik Mulai (Start)"
                    >
                      <div className="w-1 h-3 rounded-full bg-white/90" />
                    </div>

                    {/* Right (End) Ergonomic Grab Handle */}
                    <div
                      className="absolute right-0 top-0 bottom-0 w-3.5 cursor-col-resize flex items-center justify-center bg-emerald-500/50 hover:bg-emerald-400 rounded-r-lg transition-colors group-hover/clip:bg-emerald-400"
                      onMouseDown={(e) => handleTimelineMouseDown(e, idx, "end")}
                      title="Tarik untuk mengatur Titik Selesai (End)"
                    >
                      <div className="w-1 h-3 rounded-full bg-white/90" />
                    </div>
                  </div>
                );
              })}

              {/* Hover Cursor Line */}
              {hoverTime !== null && (
                <div
                  className="absolute top-0 bottom-0 w-px border-r border-dashed border-emerald-400/90 pointer-events-none z-25"
                  style={{ left: `${(hoverTime / videoDuration) * 100}%` }}
                >
                  <span className="absolute -top-5 -translate-x-1/2 text-[8px] font-mono bg-emerald-950/90 text-emerald-300 border border-emerald-500/40 px-1 rounded shadow">
                    {formatTimePrecise(hoverTime)}
                  </span>
                </div>
              )}

              {/* Live Playhead Line */}
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-white pointer-events-none z-30 shadow-[0_0_8px_#fff]"
                style={{ left: `${(currentTime / videoDuration) * 100}%` }}
              >
                <div className="absolute -top-3 -left-2 w-4 h-4 rounded-full bg-white shadow-xl border-2 border-emerald-500" />
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* ─── ACTIVE CLIP DETAILED ADJUSTMENT PANEL ───────────────────────────── */}
      {activeClip && (
        <Card className="p-4 space-y-3.5 border-zinc-800 bg-zinc-950/85 rounded-2xl shadow-xl">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Sliders className="h-4 w-4 text-emerald-400" />
              <span className="text-sm font-bold text-zinc-100">
                Pengaturan Presisi Klip #{activeClip.rank}
              </span>
              {activeClip.score !== null && (
                <span className="flex items-center gap-1 rounded-md bg-emerald-500/20 border border-emerald-500/30 px-2 py-0.5 text-xs font-bold text-emerald-300">
                  <Sparkles className="w-3 h-3" />
                  Skor Viral: {activeClip.score}
                </span>
              )}
              {activeClip.modified && (
                <span className="rounded bg-amber-500/20 border border-amber-500/40 px-2 py-0.5 text-[10px] font-semibold text-amber-300">
                  Disesuaikan
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              {/* Inclusion toggle */}
              <button
                type="button"
                onClick={() => toggleClipInclusion(activeClipIndex)}
                className={cn(
                  "flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-lg border transition-colors",
                  activeClip.included !== false
                    ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                    : "border-zinc-800 bg-zinc-900 text-zinc-500 hover:text-zinc-300"
                )}
              >
                {activeClip.included !== false ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                {activeClip.included !== false ? "Sertakan dalam Render" : "Lewati Klip Ini"}
              </button>

              {activeClip.modified && !activeClip.manual && (
                <button
                  type="button"
                  onClick={() => resetClip(activeClipIndex)}
                  className="flex items-center gap-1 text-xs text-amber-400 hover:text-amber-300 font-medium px-2 py-1 rounded-lg hover:bg-zinc-800 transition-colors"
                >
                  <RotateCcw className="h-3 w-3" />
                  Reset AI
                </button>
              )}

              {clips.length > 1 && (
                <button
                  type="button"
                  onClick={() => deleteClip(activeClipIndex)}
                  className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 font-medium px-2 py-1 rounded-lg hover:bg-red-500/10 transition-colors"
                >
                  <Trash2 className="h-3 w-3" />
                  Hapus
                </button>
              )}
            </div>
          </div>

          {/* Editable Hook Title */}
          <div>
            <label className="block text-[10px] font-bold text-zinc-400 uppercase tracking-wider mb-1.5">
              Judul Hook Klip (3 Detik Pertama Video Pendek)
            </label>
            <input
              type="text"
              value={activeClip.hook || ""}
              onChange={(e) => updateHookTitle(e.target.value)}
              placeholder="Masukkan judul atau hook menarik untuk klip ini..."
              className="w-full rounded-xl border border-zinc-800 bg-zinc-900/70 px-3.5 py-2 text-xs text-zinc-100 placeholder-zinc-600 focus:border-emerald-500 focus:outline-none shadow-inner"
            />
          </div>

          {/* Start, End, & Summary Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* Start Box */}
            <div className="rounded-xl border border-zinc-800/90 bg-zinc-900/50 p-3 space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">
                  Titik Mulai (Start)
                </label>
                <span className="text-[10px] text-emerald-400 font-mono font-bold">
                  {activeClip.start.toFixed(1)}s
                </span>
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
                className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-xs text-emerald-300 font-mono font-bold focus:border-emerald-500 focus:outline-none"
              />
              <div className="flex items-center gap-1 pt-1">
                <button type="button" onClick={() => nudgeStart(-5)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">-5s</button>
                <button type="button" onClick={() => nudgeStart(-1)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">-1s</button>
                <button type="button" onClick={() => nudgeStart(-0.1)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">-0.1s</button>
                <button type="button" onClick={() => nudgeStart(0.1)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">+0.1s</button>
                <button type="button" onClick={() => nudgeStart(1)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">+1s</button>
                <button type="button" onClick={() => nudgeStart(5)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">+5s</button>
              </div>
              <button
                type="button"
                onClick={jumpToActiveStart}
                className="w-full text-center py-1 rounded bg-zinc-800/80 text-[10px] text-zinc-300 hover:text-white hover:bg-zinc-700 transition-colors font-medium"
              >
                Lompat ke Mulai ({formatTime(activeClip.start)})
              </button>
            </div>

            {/* End Box */}
            <div className="rounded-xl border border-zinc-800/90 bg-zinc-900/50 p-3 space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">
                  Titik Selesai (End)
                </label>
                <span className="text-[10px] text-emerald-400 font-mono font-bold">
                  {activeClip.end.toFixed(1)}s
                </span>
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
                className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-xs text-emerald-300 font-mono font-bold focus:border-emerald-500 focus:outline-none"
              />
              <div className="flex items-center gap-1 pt-1">
                <button type="button" onClick={() => nudgeEnd(-5)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">-5s</button>
                <button type="button" onClick={() => nudgeEnd(-1)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">-1s</button>
                <button type="button" onClick={() => nudgeEnd(-0.1)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">-0.1s</button>
                <button type="button" onClick={() => nudgeEnd(0.1)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">+0.1s</button>
                <button type="button" onClick={() => nudgeEnd(1)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">+1s</button>
                <button type="button" onClick={() => nudgeEnd(5)} className="flex-1 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] font-mono text-zinc-300">+5s</button>
              </div>
              <button
                type="button"
                onClick={jumpToActiveEnd}
                className="w-full text-center py-1 rounded bg-zinc-800/80 text-[10px] text-zinc-300 hover:text-white hover:bg-zinc-700 transition-colors font-medium"
              >
                Lompat ke Selesai ({formatTime(activeClip.end)})
              </button>
            </div>

            {/* Total Duration & Preview Trigger */}
            <div className="rounded-xl border border-zinc-800/90 bg-zinc-900/50 p-3 flex flex-col justify-between">
              <div>
                <label className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">
                  Total Durasi Klip
                </label>
                <div className="flex items-baseline gap-2 mt-1">
                  <p className="text-3xl font-black font-mono text-zinc-100">
                    {activeClip.duration.toFixed(1)}
                  </p>
                  <span className="text-xs text-zinc-400">detik</span>
                  <span
                    className={cn(
                      "text-[10px] font-semibold px-2 py-0.5 rounded-full ml-auto",
                      activeClip.duration >= 30 && activeClip.duration <= 60
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                        : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                    )}
                  >
                    {activeClip.duration >= 30 && activeClip.duration <= 60
                      ? "Durasi Ideal (30-60s)"
                      : activeClip.duration < 30
                        ? "Durasi Singkat"
                        : "Durasi Panjang"}
                  </span>
                </div>
                <p className="text-[10px] text-zinc-400 mt-1">
                  Rentang: {formatTime(activeClip.start)} s/d {formatTime(activeClip.end)}
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                onClick={() => seekToClip(activeClipIndex, true)}
                icon={<Play className="h-3.5 w-3.5 fill-current" />}
                className="w-full mt-3 bg-emerald-500 text-zinc-950 font-bold hover:bg-emerald-400 shadow-lg shadow-emerald-500/20"
              >
                Putar Pratinjau Klip Ini (P)
              </Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
