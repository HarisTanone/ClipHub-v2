import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  Calendar,
  Clock,
  Send,
  X,
  RefreshCw,
  Upload,
  Check,
  CheckSquare,
  Square,
  Sparkles,
  AlertCircle,
  Share2,
  Tag,
  Hash,
  Bot,
  MessageSquare,
  Music,
  Volume2,
  VolumeX,
  Play,
  Pause,
  Flame,
  ShieldCheck,
  UserCheck,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Textarea, Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { useToast } from "@/components/ui/Toast";
import { API_BASE, getToken, socialApi, type TikTokMusicTrack } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

// ─── Custom Platform Icons (Pure SVG) ─────────────────────────────────────────

function PlatformIcon({ type, className = "h-4 w-4" }: { type: string; className?: string }) {
  const norm = (type || "").toLowerCase().trim();
  if (norm === "youtube") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="currentColor">
        <path
          fill="#FF0000"
          d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"
        />
      </svg>
    );
  }
  if (norm === "tiktok") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="currentColor">
        <path
          fill="#EE1D52"
          d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.24 1.07-.14 1.61.24 1.64 1.82 2.89 3.5 2.76 1.47-.04 2.7-1.07 3.03-2.5.14-.53.18-1.08.18-1.63V.02z"
        />
      </svg>
    );
  }
  if (norm === "facebook") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="currentColor">
        <path
          fill="#1877F2"
          d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"
        />
      </svg>
    );
  }
  if (norm === "instagram") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="currentColor">
        <path
          fill="#E4405F"
          d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"
        />
      </svg>
    );
  }
  if (norm === "threads") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="currentColor">
        <path
          fill="#FFFFFF"
          d="M12.186 24C5.464 24 0 18.536 0 11.814 0 5.092 5.464 0 12.186 0c6.608 0 11.968 5.253 12.18 11.859h-2.754c-.206-5.1-4.43-9.105-9.426-9.105-5.215 0-9.432 4.217-9.432 9.432 0 5.215 4.217 9.432 9.432 9.432 4.542 0 8.358-3.23 9.245-7.568h-9.245v-2.754h11.996C24.092 20.308 18.665 24 12.186 24z"
        />
      </svg>
    );
  }
  if (norm === "linkedin") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="currentColor">
        <path
          fill="#0A66C2"
          d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"
        />
      </svg>
    );
  }
  return <Share2 className={cn("text-zinc-400", className)} />;
}

function getPlatformColorClass(type: string) {
  const norm = (type || "").toLowerCase().trim();
  if (norm === "youtube") return "bg-red-500/10 text-red-400 border-red-500/20";
  if (norm === "tiktok") return "bg-pink-500/10 text-pink-400 border-pink-500/20";
  if (norm === "facebook") return "bg-blue-500/10 text-blue-400 border-blue-500/20";
  if (norm === "instagram") return "bg-fuchsia-500/10 text-fuchsia-400 border-fuchsia-500/20";
  if (norm === "threads") return "bg-zinc-700/20 text-zinc-300 border-zinc-600/30";
  if (norm === "linkedin") return "bg-sky-500/10 text-sky-400 border-sky-500/20";
  return "bg-zinc-800 text-zinc-400 border-zinc-700";
}

// ─── API calls ────────────────────────────────────────────────────────────────

async function fetchSocialAccounts(): Promise<any[]> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/accounts?page=1&limit=100`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  const data = await res.json();
  return data.docs || [];
}

async function publishClip(payload: any): Promise<any> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Gagal mempublish ke akun social media");
  }
  return res.json();
}

async function checkPublishStatus(): Promise<{ gdrive_configured: boolean; repliz_configured: boolean }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/publish/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return { gdrive_configured: false, repliz_configured: false };
  return res.json();
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface ScheduleModalProps {
  open: boolean;
  onClose: () => void;
  jobId: string;
  clipRank?: number;
  videoSource?: "clip" | "video_generator";
  defaultCaption?: string;
  hookText?: string;
  itemLabel?: string;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ScheduleModal({
  open,
  onClose,
  jobId,
  clipRank,
  videoSource,
  defaultCaption,
  hookText,
  itemLabel,
}: ScheduleModalProps) {
  const toast = useToast();
  const { user, isSuperadmin } = useAuth();
  const canPublish = isSuperadmin || user?.role !== "viewer";

  const [accounts, setAccounts] = useState<any[]>([]);
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const [title, setTitle] = useState(hookText || "");
  const [caption, setCaption] = useState(defaultCaption || "");
  const [firstReply, setFirstReply] = useState("");
  const [topic, setTopic] = useState("");
  const [tagsStr, setTagsStr] = useState("");
  const [postType, setPostType] = useState<"video" | "reel" | "story">("video");
  const [isAiGenerated, setIsAiGenerated] = useState(false);
  const [scheduleMode, setScheduleMode] = useState<"now" | "later">("now");
  const [scheduleDate, setScheduleDate] = useState("");
  const [scheduleTime, setScheduleTime] = useState("");
  const [posting, setPosting] = useState(false);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [status, setStatus] = useState<{ gdrive_configured: boolean; repliz_configured: boolean } | null>(null);

  // ── TikTok Music Auto-Pick & Volume States ──
  const [autoPickMusic, setAutoPickMusic] = useState(false);
  const [musicTracks, setMusicTracks] = useState<TikTokMusicTrack[]>([]);
  const [selectedTrack, setSelectedTrack] = useState<TikTokMusicTrack | null>(null);
  const [loadingMusic, setLoadingMusic] = useState(false);
  const [showAllMusic, setShowAllMusic] = useState(false);
  const [originalVolume, setOriginalVolume] = useState<number>(100);
  const [musicVolume, setMusicVolume] = useState<number>(0);
  const [playingTrackId, setPlayingTrackId] = useState<string | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (open) {
      setTitle(hookText || (clipRank ? `Clip #${clipRank}` : "AI Generated Video"));
      setCaption(defaultCaption || "");
      setLoadingAccounts(true);
      Promise.all([fetchSocialAccounts(), checkPublishStatus()])
        .then(([accs, st]) => {
          setAccounts(accs);
          setStatus(st);
          const connected = accs.filter((a: any) => a.isConnected);
          if (connected.length > 0 && selectedAccountIds.length === 0) {
            const firstId = connected[0]._id || connected[0].id;
            if (firstId) setSelectedAccountIds([firstId]);
          }
        })
        .finally(() => setLoadingAccounts(false));
    }
  }, [open, defaultCaption, hookText]);

  const connectedAccounts = useMemo(() => {
    return accounts.filter((a) => a.isConnected);
  }, [accounts]);

  const availablePlatforms = useMemo(() => {
    const set = new Set<string>();
    connectedAccounts.forEach((a) => {
      if (a.type) set.add(a.type.toLowerCase().trim());
    });
    return Array.from(set);
  }, [connectedAccounts]);

  const displayedAccounts = useMemo(() => {
    if (activeFilter === "all") return connectedAccounts;
    return connectedAccounts.filter((a) => (a.type || "").toLowerCase().trim() === activeFilter);
  }, [connectedAccounts, activeFilter]);

  const hasThreadsSelected = useMemo(() => {
    return connectedAccounts.some(
      (a) => (a.type || "").toLowerCase().trim() === "threads" && selectedAccountIds.includes(a._id || a.id)
    );
  }, [connectedAccounts, selectedAccountIds]);

  const hasYouTubeSelected = useMemo(() => {
    return connectedAccounts.some(
      (a) => (a.type || "").toLowerCase().trim() === "youtube" && selectedAccountIds.includes(a._id || a.id)
    );
  }, [connectedAccounts, selectedAccountIds]);

  const hasTikTokSelected = useMemo(() => {
    return connectedAccounts.some(
      (a) => (a.type || "").toLowerCase().trim() === "tiktok" && selectedAccountIds.includes(a._id || a.id)
    );
  }, [connectedAccounts, selectedAccountIds]);

  // Load TikTok trending music when TikTok account is selected and music feature is active
  useEffect(() => {
    if (open && hasTikTokSelected && autoPickMusic && musicTracks.length === 0) {
      setLoadingMusic(true);
      socialApi
        .getTikTokTrendingMusic({ country_code: "ID", limit: 30 })
        .then((res) => {
          if (res && res.tracks && res.tracks.length > 0) {
            setMusicTracks(res.tracks);
            if (!selectedTrack) {
              setSelectedTrack(res.tracks[0]);
            }
          }
        })
        .catch((err) => {
          console.warn("Failed to load TikTok music:", err);
        })
        .finally(() => setLoadingMusic(false));
    }
  }, [open, hasTikTokSelected, autoPickMusic, musicTracks.length, selectedTrack]);

  // Clean up audio player when modal is closed
  useEffect(() => {
    return () => {
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
        audioPlayerRef.current = null;
      }
    };
  }, [open]);

  if (!open) return null;

  function toggleAccount(accId: string) {
    setSelectedAccountIds((prev) => {
      if (prev.includes(accId)) {
        return prev.filter((id) => id !== accId);
      } else {
        return [...prev, accId];
      }
    });
  }

  function handleSelectAll() {
    const displayedIds = displayedAccounts.map((a) => a._id || a.id);
    const allSelected = displayedIds.every((id) => selectedAccountIds.includes(id));
    if (allSelected) {
      setSelectedAccountIds((prev) => prev.filter((id) => !displayedIds.includes(id)));
    } else {
      setSelectedAccountIds((prev) => Array.from(new Set([...prev, ...displayedIds])));
    }
  }

  function handleToggleAutoPickMusic(checked: boolean) {
    setAutoPickMusic(checked);
    if (checked) {
      setMusicVolume(0); // Default 0% music volume as requested
      if (musicTracks.length > 0 && !selectedTrack) {
        setSelectedTrack(musicTracks[0]);
      }
    } else {
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
        setPlayingTrackId(null);
      }
    }
  }

  function togglePlayDemo(track: TikTokMusicTrack, e?: React.MouseEvent) {
    e?.stopPropagation();
    if (playingTrackId === track.id) {
      audioPlayerRef.current?.pause();
      setPlayingTrackId(null);
    } else {
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
      }
      const audio = new Audio(track.url);
      audio.volume = Math.max(0.2, musicVolume > 0 ? musicVolume / 100 : 0.7);
      audio.onended = () => setPlayingTrackId(null);
      audio.onerror = () => {
        toast.error("Gagal memuat audio demo lagu");
        setPlayingTrackId(null);
      };
      audio.play().catch(() => setPlayingTrackId(null));
      audioPlayerRef.current = audio;
      setPlayingTrackId(track.id);
    }
  }

  async function handlePost() {
    if (selectedAccountIds.length === 0) {
      toast.error("Pilih minimal satu akun sosial media.");
      return;
    }

    let scheduleAt: string;
    if (scheduleMode === "now") {
      const future = new Date(Date.now() + 2 * 60 * 1000);
      scheduleAt = future.toISOString();
    } else {
      if (!scheduleDate || !scheduleTime) {
        toast.error("Pilih tanggal dan jam untuk menjadwalkan postingan.");
        return;
      }
      const scheduled = new Date(`${scheduleDate}T${scheduleTime}:00`);
      if (isNaN(scheduled.getTime())) {
        toast.error("Format tanggal atau jam tidak valid.");
        return;
      }
      scheduleAt = scheduled.toISOString();
    }

    const tags = tagsStr
      ? tagsStr.split(",").map((t) => t.trim().replace(/^#/, "")).filter(Boolean)
      : [];

    setPosting(true);
    try {
      const payload: any = {
        jobId,
        clipRank: clipRank || 1,
        videoSource: videoSource || (clipRank !== undefined ? "clip" : "video_generator"),
        accountIds: selectedAccountIds,
        caption,
        title: title || hookText || "Video",
        topic: topic || "",
        tags,
        firstReply: firstReply.trim() || undefined,
        isAiGenerated,
        scheduleAt,
        type: postType,
        isAutoAddMusic: hasTikTokSelected && autoPickMusic,
        music:
          hasTikTokSelected && autoPickMusic && selectedTrack
            ? {
                id: selectedTrack.id,
                name: selectedTrack.name,
                artist: selectedTrack.artist,
                thumbnail: selectedTrack.thumbnail,
                url: selectedTrack.url,
              }
            : undefined,
        originalVolume: originalVolume / 100,
        musicVolume: hasTikTokSelected && autoPickMusic ? musicVolume / 100 : 0,
      };

      const result = await publishClip(payload);
      const successCount = result.count || selectedAccountIds.length;
      if (scheduleMode === "now") {
        toast.success(`Video berhasil di-upload dan dijadwalkan untuk segera tayang di ${successCount} akun!`);
      } else {
        toast.success(`Berhasil dijadwalkan untuk ${scheduleDate} ${scheduleTime} ke ${successCount} akun!`);
      }
      onClose();
    } catch (e: any) {
      toast.error(e.message || "Gagal mempublish video");
    } finally {
      setPosting(false);
    }
  }

  const isAllDisplayedSelected =
    displayedAccounts.length > 0 &&
    displayedAccounts.every((a) => selectedAccountIds.includes(a._id || a.id));

  const visibleMusicTracks = showAllMusic ? musicTracks : musicTracks.slice(0, 4);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-2.5 sm:p-4 animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="w-full max-w-3xl bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-zinc-800 bg-zinc-900/60 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-9 w-9 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 shrink-0">
              <Share2 className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-sm font-bold text-zinc-100">Post to Social Media</h2>
                <span className="text-xs font-medium text-zinc-400">
                  {itemLabel || (clipRank ? `(Clip #${clipRank})` : `(AI Generated Video)`)}
                </span>
                {isSuperadmin ? (
                  <Badge variant="info" size="sm" className="gap-1 border-cyan-500/30 bg-cyan-500/10 text-cyan-300 py-0 text-[10px]">
                    <ShieldCheck className="h-2.5 w-2.5" /> Superadmin
                  </Badge>
                ) : user?.role === "editor" ? (
                  <Badge variant="default" size="sm" className="gap-1 border-blue-500/30 bg-blue-500/10 text-blue-300 py-0 text-[10px]">
                    <UserCheck className="h-2.5 w-2.5" /> Editor
                  </Badge>
                ) : null}
              </div>
              <p className="text-[11px] text-zinc-500 truncate">
                Pilih akun sosial media dan atur opsi publikasi konten
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-colors shrink-0 ml-2"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4 overflow-y-auto flex-1 custom-scrollbar">
          {/* Status Warnings */}
          {status && !status.repliz_configured && (
            <div className="flex items-start gap-2.5 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-amber-300">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <p className="text-xs leading-relaxed">
                Repliz API belum dikonfigurasi. Pastikan <code className="bg-amber-950/60 px-1 py-0.5 rounded text-[11px]">REPLIZ_ACCESS_KEY</code> dan <code className="bg-amber-950/60 px-1 py-0.5 rounded text-[11px]">REPLIZ_SECRET_KEY</code> sudah terisi di backend.
              </p>
            </div>
          )}

          {!canPublish && (
            <div className="flex items-start gap-2.5 rounded-xl border border-zinc-700 bg-zinc-950/60 p-3 text-zinc-400 text-xs">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-zinc-400" />
              <p>Peran akun Anda saat ini adalah Viewer (Read-only). Publikasi video hanya dapat dilakukan oleh Editor atau Superadmin.</p>
            </div>
          )}

          {/* 2-Column Responsive Layout */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            {/* ── LEFT COLUMN: Accounts & Timing (5 cols) ── */}
            <div className="lg:col-span-5 space-y-4">
              {/* Account Selector */}
              <div className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <label className="text-xs font-semibold text-zinc-200">
                      Pilih Akun Platform
                    </label>
                    {selectedAccountIds.length > 0 && (
                      <Badge variant="success" size="sm" className="px-2 py-0 text-[10px] font-semibold">
                        {selectedAccountIds.length} Terpilih
                      </Badge>
                    )}
                  </div>

                  {connectedAccounts.length > 0 && (
                    <button
                      type="button"
                      onClick={handleSelectAll}
                      className="text-xs font-medium text-emerald-400 hover:text-emerald-300 flex items-center gap-1 transition-colors"
                    >
                      {isAllDisplayedSelected ? (
                        <>
                          <Square className="h-3.5 w-3.5" /> Hapus Semua
                        </>
                      ) : (
                        <>
                          <CheckSquare className="h-3.5 w-3.5" /> Pilih Semua ({displayedAccounts.length})
                        </>
                      )}
                    </button>
                  )}
                </div>

                {/* Filter Pills */}
                {availablePlatforms.length > 1 && (
                  <div className="flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar">
                    <button
                      type="button"
                      onClick={() => setActiveFilter("all")}
                      className={cn(
                        "px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all whitespace-nowrap",
                        activeFilter === "all"
                          ? "bg-zinc-100 text-zinc-950 font-semibold"
                          : "bg-zinc-800/80 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                      )}
                    >
                      Semua ({connectedAccounts.length})
                    </button>
                    {availablePlatforms.map((plat) => {
                      const count = connectedAccounts.filter((a) => (a.type || "").toLowerCase().trim() === plat).length;
                      return (
                        <button
                          key={plat}
                          type="button"
                          onClick={() => setActiveFilter(plat)}
                          className={cn(
                            "px-2.5 py-1 rounded-lg text-[11px] font-medium flex items-center gap-1.5 transition-all whitespace-nowrap capitalize",
                            activeFilter === plat
                              ? "bg-zinc-100 text-zinc-950 font-semibold"
                              : "bg-zinc-800/80 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                          )}
                        >
                          <PlatformIcon type={plat} className="h-3 w-3" />
                          {plat} ({count})
                        </button>
                      );
                    })}
                  </div>
                )}

                {/* Account Cards */}
                {loadingAccounts ? (
                  <div className="flex items-center justify-center gap-2 py-6 text-xs text-zinc-500">
                    <RefreshCw className="h-4 w-4 animate-spin text-emerald-400" />
                    <span>Memuat daftar akun...</span>
                  </div>
                ) : connectedAccounts.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-zinc-800 bg-zinc-950/40 p-4 text-center">
                    <Share2 className="h-5 w-5 text-zinc-600 mx-auto mb-1.5" />
                    <p className="text-xs text-zinc-400 font-medium">Belum ada akun sosial media yang terhubung.</p>
                    <p className="text-[10px] text-zinc-600 mt-1">Koneksikan di menu Social Accounts.</p>
                  </div>
                ) : displayedAccounts.length === 0 ? (
                  <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4 text-center text-xs text-zinc-500">
                    Tidak ada akun untuk platform <span className="capitalize text-zinc-300 font-medium">{activeFilter}</span>.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-2 max-h-52 overflow-y-auto pr-1 custom-scrollbar">
                    {displayedAccounts.map((acc) => {
                      const accId = acc._id || acc.id;
                      const isSelected = selectedAccountIds.includes(accId);
                      const platBadgeColor = getPlatformColorClass(acc.type);

                      return (
                        <div
                          key={accId}
                          onClick={() => toggleAccount(accId)}
                          role="button"
                          tabIndex={0}
                          className={cn(
                            "group relative w-full flex items-center gap-3 rounded-xl border p-2.5 text-left cursor-pointer transition-all duration-150 select-none",
                            isSelected
                              ? "border-emerald-500/60 bg-emerald-500/10 ring-1 ring-emerald-500/30"
                              : "border-zinc-800 bg-zinc-950/50 hover:border-zinc-700 hover:bg-zinc-900/60"
                          )}
                        >
                          <div
                            className={cn(
                              "h-4 w-4 rounded flex items-center justify-center border transition-all shrink-0",
                              isSelected
                                ? "bg-emerald-500 border-emerald-500 text-zinc-950 shadow-sm"
                                : "border-zinc-700 bg-zinc-900/80 text-transparent group-hover:border-zinc-500"
                            )}
                          >
                            <Check className="h-3 w-3 stroke-[3]" />
                          </div>

                          <div className="relative shrink-0">
                            {acc.picture ? (
                              <img
                                src={acc.picture}
                                alt=""
                                className="h-7 w-7 rounded-full object-cover border border-zinc-700 bg-zinc-800"
                              />
                            ) : (
                              <div className="h-7 w-7 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center">
                                <PlatformIcon type={acc.type} className="h-3.5 w-3.5" />
                              </div>
                            )}
                            <div className="absolute -bottom-1 -right-1 rounded-full p-0.5 bg-zinc-900 border border-zinc-800">
                              <PlatformIcon type={acc.type} className="h-2.5 w-2.5" />
                            </div>
                          </div>

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5">
                              <p className="text-xs font-semibold text-zinc-100 truncate">
                                {acc.name || "Akun Sosial"}
                              </p>
                              <span className={cn("text-[9px] font-medium px-1.5 py-0.2 rounded border capitalize", platBadgeColor)}>
                                {acc.type}
                              </span>
                            </div>
                            <p className="text-[10px] text-zinc-500 truncate">
                              {acc.username ? `@${acc.username}` : `ID: ${accId.slice(-6)}`}
                            </p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Timing */}
              <div className="space-y-2 pt-1 border-t border-zinc-800/80">
                <label className="text-xs font-semibold text-zinc-200">Waktu Publikasi</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setScheduleMode("now")}
                    className={cn(
                      "flex items-center justify-center gap-2 rounded-xl border p-2 text-xs font-medium transition-all",
                      scheduleMode === "now"
                        ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-400 font-semibold shadow-sm"
                        : "border-zinc-800 bg-zinc-950/40 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                    )}
                  >
                    <Send className="h-3.5 w-3.5" /> Post Sekarang
                  </button>
                  <button
                    type="button"
                    onClick={() => setScheduleMode("later")}
                    className={cn(
                      "flex items-center justify-center gap-2 rounded-xl border p-2 text-xs font-medium transition-all",
                      scheduleMode === "later"
                        ? "border-blue-500/60 bg-blue-500/10 text-blue-400 font-semibold shadow-sm"
                        : "border-zinc-800 bg-zinc-950/40 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                    )}
                  >
                    <Clock className="h-3.5 w-3.5" /> Jadwalkan
                  </button>
                </div>

                {scheduleMode === "later" && (
                  <div className="grid grid-cols-2 gap-2 pt-1 animate-in fade-in duration-150">
                    <div>
                      <label className="text-[10px] font-medium text-zinc-400 mb-1 block">Tanggal</label>
                      <input
                        type="date"
                        min={new Date().toISOString().split("T")[0]}
                        value={scheduleDate}
                        onChange={(e) => setScheduleDate(e.target.value)}
                        className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-200 outline-none focus:border-blue-500/50"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] font-medium text-zinc-400 mb-1 block">Jam (WIB)</label>
                      <input
                        type="time"
                        value={scheduleTime}
                        onChange={(e) => setScheduleTime(e.target.value)}
                        className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-200 outline-none focus:border-blue-500/50"
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Post Type & AI Toggle */}
              <div className="space-y-2 pt-1 border-t border-zinc-800/80">
                <div className="flex items-center justify-between gap-2">
                  <div className="w-1/2 space-y-1">
                    <label className="text-xs font-semibold text-zinc-200">Tipe Post</label>
                    <select
                      value={postType}
                      onChange={(e: any) => setPostType(e.target.value)}
                      className="w-full h-8 rounded-xl border border-zinc-800 bg-zinc-950/60 px-2.5 text-xs text-zinc-200 outline-none focus:border-emerald-500/50"
                    >
                      <option value="video">Video</option>
                      <option value="reel">Reel / Shorts</option>
                      <option value="story">Story</option>
                    </select>
                  </div>
                  <div className="w-1/2 pt-4">
                    <label className="flex items-center gap-2 text-[11px] text-zinc-300 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={isAiGenerated}
                        onChange={(e) => setIsAiGenerated(e.target.checked)}
                        className="h-3.5 w-3.5 rounded border-zinc-700 bg-zinc-900 text-emerald-500 focus:ring-0 cursor-pointer"
                      />
                      <span>Tandai Konten AI</span>
                    </label>
                  </div>
                </div>
              </div>
            </div>

            {/* ── RIGHT COLUMN: Content & TikTok Viral Music (7 cols) ── */}
            <div className="lg:col-span-7 space-y-3.5">
              {/* Title & Caption */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-zinc-200">Judul Konten</label>
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Judul video / YouTube Title..."
                  className="text-xs bg-zinc-950/60 border-zinc-800 rounded-xl h-8"
                />
              </div>

              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-zinc-200">Caption Post</label>
                  {hookText && (
                    <button
                      type="button"
                      onClick={() => setCaption((prev) => (prev ? `${hookText}\n\n${prev}` : hookText))}
                      className="text-[10px] font-medium text-emerald-400 hover:text-emerald-300 flex items-center gap-1"
                    >
                      <Sparkles className="h-3 w-3" /> Masukkan Hook
                    </button>
                  )}
                </div>
                <Textarea
                  value={caption}
                  onChange={(e) => setCaption(e.target.value)}
                  rows={3}
                  placeholder="Tulis caption atau deskripsi untuk video ini..."
                  className="text-xs bg-zinc-950/60 border-zinc-800 focus:border-emerald-500/50 rounded-xl"
                />
              </div>

              {/* Platform Addons */}
              {(hasThreadsSelected || hasYouTubeSelected) && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 p-2.5 rounded-xl border border-zinc-800 bg-zinc-950/40">
                  {hasThreadsSelected && (
                    <div className="space-y-1">
                      <label className="text-[10px] font-medium text-zinc-300 flex items-center gap-1">
                        <Tag className="h-3 w-3 text-zinc-400" /> Threads Topic
                      </label>
                      <Input
                        value={topic}
                        onChange={(e) => setTopic(e.target.value)}
                        placeholder="AI, Podcast"
                        className="text-xs bg-zinc-900 border-zinc-800 rounded-lg h-7"
                      />
                    </div>
                  )}
                  {hasYouTubeSelected && (
                    <div className="space-y-1">
                      <label className="text-[10px] font-medium text-zinc-300 flex items-center gap-1">
                        <Hash className="h-3 w-3 text-red-400" /> YouTube Tags
                      </label>
                      <Input
                        value={tagsStr}
                        onChange={(e) => setTagsStr(e.target.value)}
                        placeholder="Shorts, Viral (pisah koma)"
                        className="text-xs bg-zinc-900 border-zinc-800 rounded-lg h-7"
                      />
                    </div>
                  )}
                </div>
              )}

              {/* ── TIKTOK VIRAL MUSIC SUITE ── */}
              {hasTikTokSelected && (
                <div className="rounded-xl border border-pink-500/30 bg-gradient-to-b from-pink-950/20 via-zinc-950/60 to-zinc-950/60 p-3.5 space-y-3 shadow-sm">
                  {/* Header & Toggle */}
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <div className="h-7 w-7 rounded-lg bg-pink-500/15 border border-pink-500/30 flex items-center justify-center text-pink-400 shrink-0">
                        <Flame className="h-4 w-4" />
                      </div>
                      <div>
                        <h3 className="text-xs font-bold text-zinc-100 flex items-center gap-1.5">
                          <span>Auto Pick Lagu Viral TikTok</span>
                          <span className="text-[10px] font-semibold text-pink-400 bg-pink-500/10 px-1.5 py-0.2 rounded border border-pink-500/20">
                            Viral Addon
                          </span>
                        </h3>
                        <p className="text-[10px] text-zinc-400">
                          Sematkan lagu trending TikTok untuk mendongkrak algoritma FYP
                        </p>
                      </div>
                    </div>

                    <button
                      type="button"
                      role="switch"
                      aria-checked={autoPickMusic}
                      onClick={() => handleToggleAutoPickMusic(!autoPickMusic)}
                      className={cn(
                        "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none",
                        autoPickMusic ? "bg-pink-500" : "bg-zinc-800"
                      )}
                    >
                      <span
                        className={cn(
                          "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out",
                          autoPickMusic ? "translate-x-4" : "translate-x-0"
                        )}
                      />
                    </button>
                  </div>

                  {/* Body when Auto Pick is active */}
                  {autoPickMusic && (
                    <div className="space-y-3 pt-1 animate-in fade-in duration-200">
                      {/* Track Selection Cards */}
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <label className="text-[11px] font-semibold text-zinc-300 flex items-center gap-1">
                            <Music className="h-3 w-3 text-pink-400" /> Rekomendasi Lagu Trending Teratas
                          </label>
                          {musicTracks.length > 4 && (
                            <button
                              type="button"
                              onClick={() => setShowAllMusic(!showAllMusic)}
                              className="text-[10px] text-pink-400 hover:text-pink-300 flex items-center gap-0.5"
                            >
                              {showAllMusic ? (
                                <>
                                  Tutup <ChevronUp className="h-3 w-3" />
                                </>
                              ) : (
                                <>
                                  Lihat Lainnya ({musicTracks.length}) <ChevronDown className="h-3 w-3" />
                                </>
                              )}
                            </button>
                          )}
                        </div>

                        {loadingMusic ? (
                          <div className="flex items-center justify-center gap-2 py-4 text-xs text-zinc-500">
                            <RefreshCw className="h-3.5 w-3.5 animate-spin text-pink-400" />
                            <span>Mengambil data lagu viral TikTok dari Repliz...</span>
                          </div>
                        ) : musicTracks.length === 0 ? (
                          <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/60 text-center text-xs text-zinc-500">
                            Sedang memuat data lagu trending...
                          </div>
                        ) : (
                          <div className="grid grid-cols-1 gap-1.5 max-h-44 overflow-y-auto pr-1 custom-scrollbar">
                            {visibleMusicTracks.map((track) => {
                              const isSelected = selectedTrack?.id === track.id;
                              const isPlaying = playingTrackId === track.id;

                              return (
                                <div
                                  key={track.id}
                                  onClick={() => setSelectedTrack(track)}
                                  className={cn(
                                    "flex items-center justify-between p-2 rounded-lg border text-left cursor-pointer transition-all duration-150",
                                    isSelected
                                      ? "border-pink-500/60 bg-pink-500/10 ring-1 ring-pink-500/30"
                                      : "border-zinc-800/80 bg-zinc-900/50 hover:border-zinc-700"
                                  )}
                                >
                                  <div className="flex items-center gap-2.5 min-w-0">
                                    {/* Thumbnail & Rank Badge */}
                                    <div className="relative shrink-0">
                                      {track.thumbnail ? (
                                        <img
                                          src={track.thumbnail}
                                          alt=""
                                          className="h-8 w-8 rounded-md object-cover border border-zinc-700 bg-zinc-800"
                                        />
                                      ) : (
                                        <div className="h-8 w-8 rounded-md bg-zinc-800 border border-zinc-700 flex items-center justify-center text-pink-400">
                                          <Music className="h-4 w-4" />
                                        </div>
                                      )}
                                      <span className="absolute -top-1 -left-1 text-[8px] font-bold bg-pink-600 text-white rounded px-1">
                                        #{track.rank}
                                      </span>
                                    </div>

                                    {/* Track Info */}
                                    <div className="min-w-0">
                                      <p className="text-xs font-semibold text-zinc-100 truncate">
                                        {track.name}
                                      </p>
                                      <div className="flex items-center gap-1.5 mt-0.5">
                                        <span className="text-[10px] text-zinc-400 truncate max-w-[110px]">
                                          {track.artist}
                                        </span>
                                        <span className="text-[9px] text-pink-400 bg-pink-950/60 px-1 py-0.2 rounded border border-pink-500/20 truncate">
                                          {track.usage_label}
                                        </span>
                                      </div>
                                    </div>
                                  </div>

                                  {/* Play/Pause Demo & Selection */}
                                  <div className="flex items-center gap-2 shrink-0 ml-2">
                                    <button
                                      type="button"
                                      onClick={(e) => togglePlayDemo(track, e)}
                                      className={cn(
                                        "h-7 w-7 rounded-full flex items-center justify-center transition-colors border",
                                        isPlaying
                                          ? "bg-pink-500 text-zinc-950 border-pink-400 shadow-sm"
                                          : "bg-zinc-800 text-zinc-300 border-zinc-700 hover:text-white hover:bg-zinc-700"
                                      )}
                                      title={isPlaying ? "Jeda demo lagu" : "Dengarkan demo lagu"}
                                    >
                                      {isPlaying ? (
                                        <Pause className="h-3 w-3 fill-current" />
                                      ) : (
                                        <Play className="h-3 w-3 fill-current ml-0.5" />
                                      )}
                                    </button>

                                    <div
                                      className={cn(
                                        "h-4 w-4 rounded-full border flex items-center justify-center",
                                        isSelected
                                          ? "border-pink-500 bg-pink-500 text-zinc-950"
                                          : "border-zinc-700"
                                      )}
                                    >
                                      {isSelected && <div className="h-1.5 w-1.5 rounded-full bg-zinc-950" />}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>

                      {/* Dual Volume Sliders */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-zinc-800/80">
                        {/* 1. Original Video Volume */}
                        <div className="space-y-1.5 p-2 rounded-lg bg-zinc-900/60 border border-zinc-800/80">
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="font-semibold text-zinc-300 flex items-center gap-1">
                              <Volume2 className="h-3.5 w-3.5 text-emerald-400" />
                              Suara Asli Video
                            </span>
                            <span className="font-mono text-emerald-400 font-bold">{originalVolume}%</span>
                          </div>
                          <input
                            type="range"
                            min="0"
                            max="100"
                            value={originalVolume}
                            onChange={(e) => setOriginalVolume(Number(e.target.value))}
                            className="w-full accent-emerald-500 h-1.5 bg-zinc-800 rounded-lg cursor-pointer"
                          />
                          <p className="text-[9px] text-zinc-500">Volume suara dialog pembicara asli</p>
                        </div>

                        {/* 2. TikTok Music Overlay Volume */}
                        <div className="space-y-1.5 p-2 rounded-lg bg-zinc-900/60 border border-zinc-800/80">
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="font-semibold text-zinc-300 flex items-center gap-1">
                              <Music className="h-3.5 w-3.5 text-pink-400" />
                              Volume Musik TikTok
                            </span>
                            <span className="font-mono text-pink-400 font-bold">{musicVolume}%</span>
                          </div>
                          <input
                            type="range"
                            min="0"
                            max="100"
                            value={musicVolume}
                            onChange={(e) => setMusicVolume(Number(e.target.value))}
                            className="w-full accent-pink-500 h-1.5 bg-zinc-800 rounded-lg cursor-pointer"
                          />
                          <p className="text-[9px] text-zinc-500">
                            {musicVolume === 0
                              ? "Volume 0% tetap menautkan algoritma viral TikTok tanpa mengubah audio video."
                              : `Musik akan dimixing di latar belakang dengan volume ${musicVolume}%.`}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* First Reply Option */}
              <div className="space-y-1 p-2.5 rounded-xl border border-zinc-800/80 bg-zinc-950/40">
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-semibold text-zinc-300 flex items-center gap-1.5">
                    <MessageSquare className="h-3 w-3 text-blue-400" />
                    <span>Komentar Pertama Otomatis (First Reply)</span>
                  </label>
                  <span className="text-[9px] text-zinc-500">Opsional</span>
                </div>
                <Input
                  value={firstReply}
                  onChange={(e) => setFirstReply(e.target.value)}
                  placeholder="Link info lengkap & promo ada di bio!"
                  className="text-xs bg-zinc-900 border-zinc-800 focus:border-blue-500/50 rounded-lg h-7"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-zinc-800 bg-zinc-900/60 shrink-0 flex-wrap gap-2">
          <div className="text-xs text-zinc-400">
            {selectedAccountIds.length > 0 ? (
              <span>
                <strong className="text-zinc-100">{selectedAccountIds.length}</strong> akun dipilih
                {autoPickMusic && selectedTrack && (
                  <span className="ml-2 text-pink-400 font-medium text-[11px]">
                    Lagu: {selectedTrack.name} ({musicVolume}%)
                  </span>
                )}
              </span>
            ) : (
              <span className="text-amber-400 text-xs">Pilih minimal 1 akun sosial media</span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={onClose}
              className="border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
            >
              Batal
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handlePost}
              loading={posting}
              disabled={
                !canPublish ||
                selectedAccountIds.length === 0 ||
                (scheduleMode === "later" && (!scheduleDate || !scheduleTime)) ||
                (status !== null && !status.repliz_configured)
              }
              className="bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold px-4"
              icon={scheduleMode === "now" ? <Send className="h-3.5 w-3.5" /> : <Clock className="h-3.5 w-3.5" />}
            >
              {posting
                ? `Memproses (${selectedAccountIds.length} akun)...`
                : scheduleMode === "now"
                ? selectedAccountIds.length > 1
                  ? `Post ke ${selectedAccountIds.length} Akun`
                  : "Post Sekarang"
                : selectedAccountIds.length > 1
                ? `Jadwalkan ke ${selectedAccountIds.length} Akun`
                : "Jadwalkan Post"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
