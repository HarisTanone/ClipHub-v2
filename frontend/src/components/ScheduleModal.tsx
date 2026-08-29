import { useState, useEffect, useMemo } from "react";
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
  Layers,
  Sparkles,
  AlertCircle,
  Share2,
  Tag,
  Hash,
  Bot,
  Video,
  MessageSquare,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Textarea, Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { useToast } from "@/components/ui/Toast";
import { API_BASE, getToken } from "@/lib/api";
import { cn } from "@/lib/utils";

// ─── Custom Platform Icons ───────────────────────────────────────────────────

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

async function publishClip(payload: {
  jobId: string;
  clipRank?: number;
  videoSource?: string;
  accountIds: string[];
  caption: string;
  title: string;
  topic?: string;
  tags?: string[];
  isAiGenerated?: boolean;
  scheduleAt: string;
  type: string;
}): Promise<any> {
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
  /** Job ID */
  jobId: string;
  /** Clip rank number (optional for video generator) */
  clipRank?: number;
  /** Video source type */
  videoSource?: "clip" | "video_generator";
  /** Pre-filled caption from clip */
  defaultCaption?: string;
  /** Clip hook text / Video title */
  hookText?: string;
  /** Custom label for header */
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
  const [accounts, setAccounts] = useState<any[]>([]);
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const [title, setTitle] = useState(hookText || "");
  const [caption, setCaption] = useState(defaultCaption || "");
  const [firstReply, setFirstReply] = useState("");
  const [topic, setTopic] = useState("");
  const [tagsStr, setTagsStr] = useState("");
  const [postType, setPostType] = useState<"video" | "reel" | "story">("video");
  const [isAiGenerated, setIsAiGenerated] = useState(true);
  const [scheduleMode, setScheduleMode] = useState<"now" | "later">("now");
  const [scheduleDate, setScheduleDate] = useState("");
  const [scheduleTime, setScheduleTime] = useState("");
  const [posting, setPosting] = useState(false);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [status, setStatus] = useState<{ gdrive_configured: boolean; repliz_configured: boolean } | null>(null);

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
          // Default select the first connected account if none selected
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

  // Unique platform types available
  const availablePlatforms = useMemo(() => {
    const set = new Set<string>();
    connectedAccounts.forEach((a) => {
      if (a.type) set.add(a.type.toLowerCase().trim());
    });
    return Array.from(set);
  }, [connectedAccounts]);

  // Filtered accounts for display
  const displayedAccounts = useMemo(() => {
    if (activeFilter === "all") return connectedAccounts;
    return connectedAccounts.filter((a) => (a.type || "").toLowerCase().trim() === activeFilter);
  }, [connectedAccounts, activeFilter]);

  // Check if selected accounts include Threads or YouTube
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
    const displayedIds = displayedAccounts.map((a) => a._id || a.id).filter(Boolean);
    const allSelected = displayedIds.every((id) => selectedAccountIds.includes(id));
    if (allSelected) {
      setSelectedAccountIds((prev) => prev.filter((id) => !displayedIds.includes(id)));
    } else {
      setSelectedAccountIds((prev) => Array.from(new Set([...prev, ...displayedIds])));
    }
  }

  function getScheduleAt(): string {
    if (scheduleMode === "now") {
      // TikTok and Repliz require scheduled posts to be at least 20 minutes in the future
      const d = new Date(Date.now() + 20 * 60 * 1000);
      return d.toISOString();
    }
    if (!scheduleDate || !scheduleTime) return "";
    return new Date(`${scheduleDate}T${scheduleTime}:00`).toISOString();
  }

  async function handlePost() {
    if (selectedAccountIds.length === 0) {
      toast.error("Pilih minimal 1 akun untuk memposting.");
      return;
    }
    const scheduleAt = getScheduleAt();
    if (!scheduleAt) {
      toast.error("Tentukan tanggal dan waktu jadwal posting.");
      return;
    }

    const tags = tagsStr
      ? tagsStr.split(",").map((t) => t.trim().replace(/^#/, "")).filter(Boolean)
      : [];

    setPosting(true);
    try {
      const payload = {
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

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-2.5 sm:p-4 animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg bg-zinc-900 border border-zinc-800/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[94vh] sm:max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 sm:px-6 sm:py-4 border-b border-zinc-800/80 bg-zinc-900/50">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="h-8 w-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 shrink-0">
              <Share2 className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-zinc-100 flex items-center gap-1.5 flex-wrap">
                <span>Post to Social Media</span>
                <span className="text-[11px] font-normal text-zinc-400">
                  {itemLabel || (clipRank ? `(Clip #${clipRank})` : `(AI Generated Video)`)}
                </span>
              </h2>
              <p className="text-[11px] text-zinc-500 truncate">
                Pilih satu atau beberapa akun untuk publikasi video
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
        <div className="px-4 py-3 sm:px-6 sm:py-4 space-y-3.5 sm:space-y-4 overflow-y-auto flex-1 custom-scrollbar">
          {/* Status Warnings */}
          {status && !status.repliz_configured && (
            <div className="flex items-start gap-2.5 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-amber-300">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <p className="text-xs leading-relaxed">
                Repliz API belum dikonfigurasi. Pastikan <code className="bg-amber-950/60 px-1 py-0.5 rounded text-[11px]">REPLIZ_ACCESS_KEY</code> dan <code className="bg-amber-950/60 px-1 py-0.5 rounded text-[11px]">REPLIZ_SECRET_KEY</code> sudah terisi di backend.
              </p>
            </div>
          )}

          {status && !status.gdrive_configured && (
            <div className="flex items-start gap-2.5 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-amber-300">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <p className="text-xs leading-relaxed">
                Google Drive belum dikonfigurasi. Video membutuhkan Cloud Storage Google Drive untuk direct link publik ke Repliz API.
              </p>
            </div>
          )}

          {/* Account Selector Section */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <label className="text-xs font-semibold text-zinc-200">
                  Pilih Akun Platform
                </label>
                {selectedAccountIds.length > 0 && (
                  <Badge variant="success" size="sm" className="px-2 py-0 text-[10px] font-semibold">
                    {selectedAccountIds.length} Akun Terpilih
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
                      <Square className="h-3.5 w-3.5" /> Hapus Pilihan
                    </>
                  ) : (
                    <>
                      <CheckSquare className="h-3.5 w-3.5" /> Pilih Semua ({displayedAccounts.length})
                    </>
                  )}
                </button>
              )}
            </div>

            {/* Platform Filter Pills */}
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

            {/* Account List */}
            {loadingAccounts ? (
              <div className="flex items-center justify-center gap-2 py-8 text-xs text-zinc-500">
                <RefreshCw className="h-4 w-4 animate-spin text-emerald-400" />
                <span>Memuat daftar akun sosial media...</span>
              </div>
            ) : connectedAccounts.length === 0 ? (
              <div className="rounded-xl border border-dashed border-zinc-800 bg-zinc-950/40 p-6 text-center">
                <Share2 className="h-6 w-6 text-zinc-600 mx-auto mb-2" />
                <p className="text-xs text-zinc-400 font-medium">Belum ada akun sosial media yang terhubung.</p>
                <p className="text-[11px] text-zinc-600 mt-1">
                  Koneksikan akun TikTok, YouTube, Instagram, dsb di menu Social Accounts terlebih dahulu.
                </p>
              </div>
            ) : displayedAccounts.length === 0 ? (
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4 text-center text-xs text-zinc-500">
                Tidak ada akun untuk platform <span className="capitalize text-zinc-300 font-medium">{activeFilter}</span>.
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-2 max-h-48 overflow-y-auto pr-1 custom-scrollbar">
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
                      onKeyDown={(e) => {
                        if (e.key === " " || e.key === "Enter") {
                          e.preventDefault();
                          toggleAccount(accId);
                        }
                      }}
                      className={cn(
                        "group relative w-full flex items-center gap-3.5 rounded-xl border p-2.5 sm:p-3 text-left cursor-pointer transition-all duration-150 select-none",
                        isSelected
                          ? "border-emerald-500/60 bg-emerald-500/10 shadow-[0_0_15px_rgba(16,185,129,0.08)] ring-1 ring-emerald-500/30"
                          : "border-zinc-800/80 bg-zinc-950/50 hover:border-zinc-700 hover:bg-zinc-900/60"
                      )}
                    >
                      {/* Custom Checkbox */}
                      <div
                        className={cn(
                          "h-5 w-5 rounded-md flex items-center justify-center border transition-all shrink-0",
                          isSelected
                            ? "bg-emerald-500 border-emerald-500 text-zinc-950 shadow-sm"
                            : "border-zinc-700 bg-zinc-900/80 text-transparent group-hover:border-zinc-500"
                        )}
                      >
                        <Check className="h-3.5 w-3.5 stroke-[3]" />
                      </div>

                      {/* Avatar / Platform Icon */}
                      <div className="relative shrink-0">
                        {acc.picture ? (
                          <img
                            src={acc.picture}
                            alt=""
                            className="h-8 w-8 rounded-full object-cover border border-zinc-700 bg-zinc-800"
                          />
                        ) : (
                          <div className="h-8 w-8 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center">
                            <PlatformIcon type={acc.type} className="h-4 w-4" />
                          </div>
                        )}
                        <div className="absolute -bottom-1 -right-1 rounded-full p-0.5 bg-zinc-900 border border-zinc-800">
                          <PlatformIcon type={acc.type} className="h-2.5 w-2.5" />
                        </div>
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-xs font-semibold text-zinc-100 truncate">
                            {acc.name || "Akun Sosial"}
                          </p>
                          <span
                            className={cn(
                              "text-[10px] font-medium px-2 py-0.5 rounded-full border capitalize tracking-wider",
                              platBadgeColor
                            )}
                          >
                            {acc.type}
                          </span>
                        </div>
                        <p className="text-[11px] text-zinc-500 truncate mt-0.5">
                          {acc.username ? `@${acc.username}` : `ID: ${accId.slice(-6)}`}
                        </p>
                      </div>

                      {/* Selection Tag */}
                      {isSelected && (
                        <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 rounded-md shrink-0">
                          Selected
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Title & Post Type */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
            <div className="sm:col-span-2 space-y-1">
              <label className="text-xs font-semibold text-zinc-200">Judul Konten</label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Judul video / YouTube Title..."
                className="text-xs bg-zinc-950/60 border-zinc-800 rounded-xl"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-zinc-200">Tipe Post</label>
              <select
                value={postType}
                onChange={(e: any) => setPostType(e.target.value)}
                className="w-full h-9 rounded-xl border border-zinc-800 bg-zinc-950/60 px-2.5 text-xs text-zinc-200 outline-none focus:border-emerald-500/50"
              >
                <option value="video">Video (Standard)</option>
                <option value="reel">Reel / Shorts</option>
                <option value="story">Story</option>
              </select>
            </div>
          </div>

          {/* Caption Box */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-zinc-200">
                Caption Post
              </label>
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
            <div className="flex items-center justify-between text-[10px] text-zinc-500 px-1">
              <span>Caption akan diterapkan ke semua akun yang dipilih.</span>
              <span>{caption.length} karakter</span>
            </div>
          </div>

          {/* Platform Specific Addons */}
          {(hasThreadsSelected || hasYouTubeSelected) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 p-3 rounded-xl border border-zinc-800/80 bg-zinc-950/40">
              {hasThreadsSelected && (
                <div className="space-y-1">
                  <label className="text-[11px] font-medium text-zinc-300 flex items-center gap-1">
                    <Tag className="h-3 w-3 text-zinc-400" /> Threads Topic
                  </label>
                  <Input
                    value={topic}
                    onChange={(e) => setTopic(e.target.value)}
                    placeholder="e.g. Technology, AI, Podcast"
                    className="text-xs bg-zinc-900 border-zinc-800 rounded-lg h-8"
                  />
                </div>
              )}
              {hasYouTubeSelected && (
                <div className="space-y-1">
                  <label className="text-[11px] font-medium text-zinc-300 flex items-center gap-1">
                    <Hash className="h-3 w-3 text-red-400" /> YouTube Tags
                  </label>
                  <Input
                    value={tagsStr}
                    onChange={(e) => setTagsStr(e.target.value)}
                    placeholder="Shorts, Viral, Podcast (pisah koma)"
                    className="text-xs bg-zinc-900 border-zinc-800 rounded-lg h-8"
                  />
                </div>
              )}
            </div>
          )}

          {/* Auto First Comment (Repliz Replies Feature) */}
          <div className="space-y-1.5 p-3 rounded-xl border border-zinc-800/80 bg-zinc-950/40">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-zinc-200 flex items-center gap-1.5">
                <MessageSquare className="h-3.5 w-3.5 text-blue-400" />
                <span>Komentar Pertama Otomatis (First Reply)</span>
              </label>
              <span className="text-[10px] text-zinc-500 font-mono">Opsional</span>
            </div>
            <Input
              value={firstReply}
              onChange={(e) => setFirstReply(e.target.value)}
              placeholder="e.g. Link info lengkap & promo ada di deskripsi/bio!"
              className="text-xs bg-zinc-900 border-zinc-800 focus:border-blue-500/50 rounded-lg h-8"
            />
            <p className="text-[10px] text-zinc-500">
              Repliz akan otomatis memposting komentar ini segera setelah video tayang di media sosial.
            </p>
          </div>

          {/* Schedule Timing */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-zinc-200">Waktu Publikasi</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setScheduleMode("now")}
                className={cn(
                  "flex items-center justify-center gap-2 rounded-xl border p-2.5 text-xs font-medium transition-all",
                  scheduleMode === "now"
                    ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-400 font-semibold shadow-sm"
                    : "border-zinc-800/80 bg-zinc-950/40 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                )}
              >
                <Send className="h-3.5 w-3.5" /> Post Sekarang
              </button>
              <button
                type="button"
                onClick={() => setScheduleMode("later")}
                className={cn(
                  "flex items-center justify-center gap-2 rounded-xl border p-2.5 text-xs font-medium transition-all",
                  scheduleMode === "later"
                    ? "border-blue-500/60 bg-blue-500/10 text-blue-400 font-semibold shadow-sm"
                    : "border-zinc-800/80 bg-zinc-950/40 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                )}
              >
                <Clock className="h-3.5 w-3.5" /> Jadwalkan Nanti
              </button>
            </div>

            {scheduleMode === "later" && (
              <div className="grid grid-cols-2 gap-2.5 pt-1 animate-in fade-in duration-150">
                <div>
                  <label className="text-[10px] font-medium text-zinc-400 mb-1 block">
                    Pilih Tanggal
                  </label>
                  <input
                    type="date"
                    min={new Date().toISOString().split("T")[0]}
                    value={scheduleDate}
                    onChange={(e) => setScheduleDate(e.target.value)}
                    className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-blue-500/50"
                  />
                </div>
                <div>
                  <label className="text-[10px] font-medium text-zinc-400 mb-1 block">
                    Pilih Jam
                  </label>
                  <input
                    type="time"
                    value={scheduleTime}
                    onChange={(e) => setScheduleTime(e.target.value)}
                    className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-blue-500/50"
                  />
                </div>
              </div>
            )}
          </div>

          {/* AI Generated Badge Option */}
          <div className="flex items-center justify-between p-2.5 rounded-xl border border-zinc-800 bg-zinc-950/40 text-xs">
            <div className="flex items-center gap-2 text-zinc-300">
              <Bot className="h-4 w-4 text-emerald-400" />
              <span>Tandai sebagai Konten AI (Repliz isAiGenerated)</span>
            </div>
            <input
              type="checkbox"
              checked={isAiGenerated}
              onChange={(e) => setIsAiGenerated(e.target.checked)}
              className="h-4 w-4 rounded border-zinc-700 bg-zinc-900 text-emerald-500 focus:ring-0 cursor-pointer"
            />
          </div>

          {/* Storage Notice */}
          <div className="rounded-xl border border-zinc-800/80 bg-zinc-950/40 p-2.5 flex items-center gap-2.5 text-[11px] text-zinc-400">
            <Upload className="h-4 w-4 text-emerald-400 shrink-0" />
            <span>
              Video di-upload ke Cloud Storage 1x dan dijadwalkan otomatis ke akun media sosial via Repliz API.
            </span>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-3 sm:px-6 sm:py-3.5 border-t border-zinc-800/80 bg-zinc-900/50 flex-wrap gap-2">
          <div className="text-xs text-zinc-400">
            {selectedAccountIds.length > 0 ? (
              <span>
                <strong className="text-zinc-100">{selectedAccountIds.length}</strong> akun dipilih
              </span>
            ) : (
              <span className="text-amber-400 text-[11px]">Pilih minimal 1 akun</span>
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
                selectedAccountIds.length === 0 ||
                (scheduleMode === "later" && (!scheduleDate || !scheduleTime)) ||
                (status !== null && !status.repliz_configured)
              }
              className="bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold px-4"
              icon={scheduleMode === "now" ? <Send className="h-3.5 w-3.5" /> : <Clock className="h-3.5 w-3.5" />}
            >
              {posting
                ? `Memposting (${selectedAccountIds.length} akun)...`
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
