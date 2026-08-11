import { useState, useEffect } from "react";
import { Calendar, Clock, Send, X, Facebook, RefreshCw, Upload } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { useToast } from "@/components/ui/Toast";
import { API_BASE, getToken } from "@/lib/api";
import { cn } from "@/lib/utils";

// ─── API calls ────────────────────────────────────────────────────────────────

async function fetchSocialAccounts(): Promise<any[]> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/accounts?page=1&limit=50`, {
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
    throw new Error(err.detail || "Failed to publish");
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
  /** Clip rank number */
  clipRank: number;
  /** Pre-filled caption from clip */
  defaultCaption?: string;
  /** Clip hook text */
  hookText?: string;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ScheduleModal({ open, onClose, jobId, clipRank, defaultCaption, hookText }: ScheduleModalProps) {
  const toast = useToast();
  const [accounts, setAccounts] = useState<any[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>("");
  const [caption, setCaption] = useState(defaultCaption || "");
  const [scheduleMode, setScheduleMode] = useState<"now" | "later">("now");
  const [scheduleDate, setScheduleDate] = useState("");
  const [scheduleTime, setScheduleTime] = useState("");
  const [posting, setPosting] = useState(false);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [status, setStatus] = useState<{ gdrive_configured: boolean; repliz_configured: boolean } | null>(null);

  useEffect(() => {
    if (open) {
      setCaption(defaultCaption || "");
      setLoadingAccounts(true);
      Promise.all([fetchSocialAccounts(), checkPublishStatus()]).then(([accs, st]) => {
        setAccounts(accs);
        setStatus(st);
        const connected = accs.filter((a: any) => a.isConnected);
        if (connected.length > 0 && !selectedAccount) {
          setSelectedAccount(connected[0]._id || connected[0].id);
        }
      }).finally(() => setLoadingAccounts(false));
    }
  }, [open]);

  if (!open) return null;

  const connectedAccounts = accounts.filter((a) => a.isConnected);

  function getScheduleAt(): string {
    if (scheduleMode === "now") {
      // Schedule 1 minute from now (Repliz needs future time)
      const d = new Date(Date.now() + 60_000);
      return d.toISOString();
    }
    if (!scheduleDate || !scheduleTime) return "";
    return new Date(`${scheduleDate}T${scheduleTime}:00`).toISOString();
  }

  async function handlePost() {
    if (!selectedAccount) {
      toast.error("Pilih akun terlebih dahulu");
      return;
    }
    const scheduleAt = getScheduleAt();
    if (!scheduleAt) {
      toast.error("Pilih tanggal dan waktu");
      return;
    }

    setPosting(true);
    try {
      const payload = {
        jobId,
        clipRank,
        accountId: selectedAccount,
        caption,
        title: hookText || "",
        scheduleAt,
        type: "video",
      };

      await publishClip(payload);
      toast.success(scheduleMode === "now" ? "Video di-upload dan dijadwalkan!" : `Dijadwalkan untuk ${scheduleDate} ${scheduleTime}`);
      onClose();
    } catch (e: any) {
      toast.error(e.message || "Gagal publish");
    } finally {
      setPosting(false);
    }
  }

  function PlatformIcon({ type }: { type: string }) {
    if (type === "facebook") return <Facebook className="h-3.5 w-3.5 text-blue-400" />;
    return <Send className="h-3.5 w-3.5 text-zinc-400" />;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-md mx-4 bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Send className="h-4 w-4 text-emerald-400" />
            <h2 className="text-sm font-semibold text-zinc-100">Post to Social Media</h2>
          </div>
          <button type="button" onClick={onClose} className="p-1 rounded text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4 max-h-[70vh] overflow-y-auto">
          {/* Status warnings */}
          {status && !status.repliz_configured && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2.5">
              <p className="text-[11px] text-amber-400">Repliz API belum dikonfigurasi. Set REPLIZ_ACCESS_KEY dan REPLIZ_SECRET_KEY di .env backend.</p>
            </div>
          )}

          {/* Account selector */}
          <div>
            <label className="text-xs font-medium text-zinc-400 mb-2 block">Pilih Akun</label>
            {loadingAccounts ? (
              <div className="flex items-center gap-2 text-xs text-zinc-500">
                <RefreshCw className="h-3 w-3 animate-spin" /> Loading accounts...
              </div>
            ) : connectedAccounts.length === 0 ? (
              <p className="text-[11px] text-zinc-600">Belum ada akun terhubung. Connect di menu Social.</p>
            ) : (
              <div className="space-y-1.5">
                {connectedAccounts.map((acc) => (
                  <button
                    key={acc._id || acc.id}
                    type="button"
                    onClick={() => setSelectedAccount(acc._id || acc.id)}
                    className={cn(
                      "w-full flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors",
                      selectedAccount === (acc._id || acc.id)
                        ? "border-emerald-500/50 bg-emerald-500/5"
                        : "border-zinc-800 hover:border-zinc-600 bg-zinc-950/60"
                    )}
                  >
                    {acc.picture ? (
                      <img src={acc.picture} alt="" className="h-7 w-7 rounded-full object-cover" />
                    ) : (
                      <div className="h-7 w-7 rounded-full bg-zinc-800 flex items-center justify-center">
                        <PlatformIcon type={acc.type} />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-zinc-200 font-medium truncate">{acc.name}</p>
                      <p className="text-[10px] text-zinc-500">{acc.type}</p>
                    </div>
                    {selectedAccount === (acc._id || acc.id) && (
                      <Badge variant="success" size="sm">Selected</Badge>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Caption */}
          <div>
            <label className="text-xs font-medium text-zinc-400 mb-2 block">Caption</label>
            <Textarea
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              rows={4}
              placeholder="Tulis caption untuk post..."
              className="text-xs"
            />
            <p className="text-[10px] text-zinc-600 mt-1">{caption.length} karakter</p>
          </div>

          {/* Schedule mode */}
          <div>
            <label className="text-xs font-medium text-zinc-400 mb-2 block">Waktu Post</label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setScheduleMode("now")}
                className={cn(
                  "flex-1 flex items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-xs font-medium transition-colors",
                  scheduleMode === "now"
                    ? "border-emerald-500/50 bg-emerald-500/5 text-emerald-400"
                    : "border-zinc-800 text-zinc-500 hover:border-zinc-600"
                )}
              >
                <Send className="h-3.5 w-3.5" /> Post Sekarang
              </button>
              <button
                type="button"
                onClick={() => setScheduleMode("later")}
                className={cn(
                  "flex-1 flex items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-xs font-medium transition-colors",
                  scheduleMode === "later"
                    ? "border-blue-500/50 bg-blue-500/5 text-blue-400"
                    : "border-zinc-800 text-zinc-500 hover:border-zinc-600"
                )}
              >
                <Clock className="h-3.5 w-3.5" /> Jadwalkan
              </button>
            </div>

            {scheduleMode === "later" && (
              <div className="grid grid-cols-2 gap-2 mt-3">
                <div>
                  <label className="text-[10px] text-zinc-500 mb-1 block">Tanggal</label>
                  <input
                    type="date"
                    value={scheduleDate}
                    onChange={(e) => setScheduleDate(e.target.value)}
                    className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-zinc-600"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 mb-1 block">Waktu</label>
                  <input
                    type="time"
                    value={scheduleTime}
                    onChange={(e) => setScheduleTime(e.target.value)}
                    className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-zinc-600"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Info */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2.5">
            <div className="flex items-center gap-2">
              <Upload className="h-3.5 w-3.5 text-blue-400" />
              <p className="text-[11px] text-zinc-400">
                Video akan di-upload ke Repliz Storage lalu diposting ke social media.
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-zinc-800">
          <Button variant="outline" size="sm" onClick={onClose}>Batal</Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handlePost}
            loading={posting}
            disabled={!selectedAccount || (scheduleMode === "later" && (!scheduleDate || !scheduleTime)) || (status !== null && !status.repliz_configured)}
            icon={scheduleMode === "now" ? <Send className="h-3.5 w-3.5" /> : <Clock className="h-3.5 w-3.5" />}
          >
            {posting ? "Uploading..." : scheduleMode === "now" ? "Post Sekarang" : "Jadwalkan"}
          </Button>
        </div>
      </div>
    </div>
  );
}
