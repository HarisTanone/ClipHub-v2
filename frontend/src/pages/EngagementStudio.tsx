import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Sparkles,
  Video,
  Timer,
  CheckCircle2,
  RefreshCw,
  Plus,
  Trash2,
  ArrowLeft,
  Sliders,
  ThumbsUp,
  MessageSquare,
  HelpCircle,
  Eye,
  Layers,
  ChevronRight,
  ShieldCheck,
  Link,
  Search,
  AlertCircle,
  ExternalLink,
  Play,
  X,
} from "lucide-react";
import { socialApi } from "@/lib/api";
import { Toggle } from "@/components/ui/Toggle";
import { PlatformIcon } from "@/components/social/PlatformIcon";

interface CommenterConfig {
  accountId: string;
  accountName?: string;
  roleCategory?: "pro" | "contra" | "netral" | "apatis" | "hate" | "curious" | "custom";
  persona: string;
}

const ROLE_OPTIONS = [
  {
    value: "pro",
    label: "Pro / Hype",
    desc: "Mendukung, setuju, relate parah",
    defaultPersona: "jujurly relate bgt mana valid parah poin kreatornya",
    badgeColor: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  },
  {
    value: "contra",
    label: "Kontra / Menentang",
    desc: "Ga setuju, membantah argumen, skeptis",
    defaultPersona: "agak laen sih menurut gw, ga semua orang relate sama opini ini",
    badgeColor: "bg-rose-500/15 text-rose-400 border-rose-500/30",
  },
  {
    value: "netral",
    label: "Netral / Penengah",
    desc: "Objektif santai, menengahi di tengah-tengah",
    defaultPersona: "di satu sisi bener sih, which is tergantung sikon masing2 juga ga sih",
    badgeColor: "bg-cyan-500/15 text-cyan-400 border-cyan-500/30",
  },
  {
    value: "apatis",
    label: "Tidak Peduli / Cuek",
    desc: "Apatis, 'terus gue kudu gimana', lewat fyp",
    defaultPersona: "info yang sangat tidak merubah nasib hidup gw, tapi oke lah lewat fyp",
    badgeColor: "bg-zinc-800 text-zinc-400 border-zinc-700",
  },
  {
    value: "hate",
    label: "Hate / Julid Salty",
    desc: "Sarkas, salty, roasting tipis netizen",
    defaultPersona: "konten ginian doang masuk fyp, fomo bgt anjir yg nonton",
    badgeColor: "bg-red-500/15 text-red-400 border-red-500/30",
  },
  {
    value: "curious",
    label: "Tanya / Penasaran",
    desc: "Kepo, minta spill info lanjutan",
    defaultPersona: "spill detailnya dong min, kepo bgt literally belom paham",
    badgeColor: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  },
  {
    value: "custom",
    label: "Kustom Bebas",
    desc: "Ketik instruksi gaya bahasa sesukamu",
    defaultPersona: "Ketik instruksi gaya bahasa sesukamu",
    badgeColor: "bg-purple-500/15 text-purple-400 border-purple-500/30",
  },
] as const;

interface SocialAccountOption {
  id: string;
  name: string;
  platform: string;
  username?: string;
  picture?: string;
}

export function EngagementStudio() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const editRuleId = searchParams.get("edit") ? parseInt(searchParams.get("edit")!) : null;

  const [accounts, setAccounts] = useState<SocialAccountOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [triggering, setTriggering] = useState(false);

  // Platform Filter tab for selecting target account
  const [selectedPlatform, setSelectedPlatform] = useState<string>("all");

  // Form State
  const [formName, setFormName] = useState("Campaign Auto Engagement Skena");
  const [formTargetAccountId, setFormTargetAccountId] = useState("");
  const [formTargetMode, setFormTargetMode] = useState<"latest" | "specific" | "url">("latest");
  const [formTargetUrl, setFormTargetUrl] = useState("");
  const [resolvingUrl, setResolvingUrl] = useState(false);
  const [resolvedUrlData, setResolvedUrlData] = useState<any | null>(null);

  const [formSpecificContentIds, setFormSpecificContentIds] = useState<string[]>([]);
  const [manualContentIdInput, setManualContentIdInput] = useState("");
  const [gallerySearchQuery, setGallerySearchQuery] = useState("");
  const [formDelayMinutes, setFormDelayMinutes] = useState(5);
  const [formAutoLikeComments, setFormAutoLikeComments] = useState(true);
  const [formIsActive, setFormIsActive] = useState(true);
  const [formCommenters, setFormCommenters] = useState<CommenterConfig[]>([]);

  // Video Gallery for Target Account
  const [targetContents, setTargetContents] = useState<any[]>([]);
  const [loadingContents, setLoadingContents] = useState(false);

  // Preview AI Comment State
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewResults, setPreviewResults] = useState<any[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Auto-sync commenters based on target account platform
  const syncCommentersForTarget = useCallback(
    (targetAccId: string, currentCommenters: CommenterConfig[] = [], allAccounts: SocialAccountOption[] = accounts) => {
      const targetAcc = allAccounts.find((a) => a.id === targetAccId);
      if (!targetAcc) return [];

      const targetPlatform = (targetAcc.platform || "tiktok").toLowerCase();

      // ALL other accounts on the SAME platform become commenters
      const peerAccounts = allAccounts.filter(
        (a) =>
          (a.platform || "tiktok").toLowerCase() === targetPlatform &&
          a.id !== targetAccId
      );

      return peerAccounts.map((a, idx) => {
        const existing = currentCommenters.find((c) => c.accountId === a.id);
        const role = ROLE_OPTIONS[idx % ROLE_OPTIONS.length];
        return {
          accountId: a.id,
          accountName: a.name,
          roleCategory: existing?.roleCategory || (role.value as any),
          persona: existing?.persona || role.defaultPersona,
        };
      });
    },
    [accounts]
  );

  // Load Accounts & Existing Rule if editing
  useEffect(() => {
    async function init() {
      try {
        setLoading(true);
        const accRes = await socialApi.getAccounts();
        const docs = (accRes?.docs || []).map((a: any) => ({
          id: a._id || a.id,
          name: a.name || a.username || "Account",
          platform: (a.type || a.platform || "tiktok").toLowerCase(),
          username: a.username || "",
          picture: a.picture || "",
        }));
        setAccounts(docs);

        if (editRuleId) {
          const rules = await socialApi.getEngagementRules();
          const targetRule = (rules || []).find((r: any) => r.id === editRuleId);
          if (targetRule) {
            setFormName(targetRule.name);
            setFormTargetAccountId(targetRule.targetAccountId || "");
            const mode = (targetRule.targetMode || "latest") as "latest" | "specific" | "url";
            setFormTargetMode(mode);
            if (targetRule.targetUrl) {
              setFormTargetUrl(targetRule.targetUrl);
              setResolvedUrlData({
                id: targetRule.specificContentId || "",
                contentId: targetRule.specificContentId || "",
                platform: targetRule.targetPlatform || "tiktok",
                url: targetRule.targetUrl,
                title: targetRule.name || "Video Target",
                description: "",
                uploader: targetRule.targetAccountName || "",
                thumbnail: "",
                duration: 0,
                durationFormatted: "",
              });
            }
            const contentIds = targetRule.specificContentIds && targetRule.specificContentIds.length > 0
              ? targetRule.specificContentIds
              : targetRule.specificContentId
              ? [targetRule.specificContentId]
              : [];
            setFormSpecificContentIds(contentIds);
            setFormDelayMinutes(targetRule.delayMinutes ?? 5);
            setFormAutoLikeComments(targetRule.autoLikeComments !== false);
            setFormIsActive(targetRule.isActive);
            setFormCommenters(targetRule.commenters || []);

            const targetAcc = docs.find((a: any) => a.id === targetRule.targetAccountId);
            if (targetAcc) {
              setSelectedPlatform(targetAcc.platform);
            }
          }
        } else if (docs.length > 0) {
          const first = docs[0];
          setFormTargetAccountId(first.id);
          setSelectedPlatform(first.platform);
          const initialCommenters = syncCommentersForTarget(first.id, [], docs);
          setFormCommenters(initialCommenters);
        }
      } catch (err) {
        console.error("Gagal load data studio:", err);
      } finally {
        setLoading(false);
      }
    }
    init();
  }, [editRuleId]);

  // Load target account videos when target changes & mode is specific
  useEffect(() => {
    if (formTargetAccountId && formTargetMode === "specific") {
      setLoadingContents(true);
      socialApi
        .getTargetAccountContents(formTargetAccountId, 30)
        .then((items) => setTargetContents(items || []))
        .catch(() => setTargetContents([]))
        .finally(() => setLoadingContents(false));
    } else {
      setTargetContents([]);
    }
  }, [formTargetAccountId, formTargetMode]);

  // Available platforms breakdown
  const platformStats = useMemo(() => {
    const map: Record<string, number> = {};
    accounts.forEach((a) => {
      const p = a.platform || "tiktok";
      map[p] = (map[p] || 0) + 1;
    });
    return map;
  }, [accounts]);

  const platformKeys = useMemo(() => Object.keys(platformStats), [platformStats]);

  const filteredAccounts = useMemo(() => {
    if (selectedPlatform === "all") return accounts;
    return accounts.filter((a) => (a.platform || "tiktok").toLowerCase() === selectedPlatform.toLowerCase());
  }, [accounts, selectedPlatform]);

  const handleSelectTargetAccount = (acc: SocialAccountOption) => {
    setFormTargetAccountId(acc.id);
    setFormSpecificContentIds([]);
    const autoCommenters = syncCommentersForTarget(acc.id, formCommenters);
    setFormCommenters(autoCommenters);
  };

  const handleResolveUrl = async (urlToResolve = formTargetUrl) => {
    const trimmed = urlToResolve.trim();
    if (!trimmed) {
      alert("Masukkan URL video terlebih dahulu");
      return;
    }
    try {
      setResolvingUrl(true);
      const data = await socialApi.resolveEngagementUrl(trimmed);
      setResolvedUrlData(data);
      setFormTargetUrl(data.url || trimmed);
      if (data.contentId) {
        setFormSpecificContentIds([data.contentId]);
      }
    } catch (err: any) {
      alert(`Gagal memeriksa URL video: ${err.message || err}`);
    } finally {
      setResolvingUrl(false);
    }
  };

  const handleAddCommenter = (accId: string) => {
    if (!accId) return;
    const acc = accounts.find((a) => a.id === accId);
    if (!acc) return;
    if (formCommenters.some((c) => c.accountId === accId)) return;
    const nextIdx = formCommenters.length;
    const role = ROLE_OPTIONS[nextIdx % ROLE_OPTIONS.length];
    setFormCommenters((prev) => [
      ...prev,
      {
        accountId: acc.id,
        accountName: acc.name,
        roleCategory: role.value as any,
        persona: role.defaultPersona,
      },
    ]);
  };

  const handleRemoveCommenter = (idx: number) => {
    setFormCommenters((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleDirectTrigger = async () => {
    if (formTargetMode === "url") {
      if (!resolvedUrlData && !formTargetUrl.trim()) {
        alert("Masukkan dan periksa URL video pada Langkah 2 terlebih dahulu");
        return;
      }
    } else if (!formTargetAccountId) {
      alert("Pilih akun target utama pada Langkah 1 terlebih dahulu");
      return;
    }

    if (formCommenters.length === 0 || formCommenters.some((c) => !c.accountId)) {
      alert("Pilih minimal satu akun pengomentar pada Langkah 3");
      return;
    }

    const targetAcc = accounts.find((a) => a.id === formTargetAccountId);
    const resolvedCid = resolvedUrlData?.contentId || (formSpecificContentIds.length > 0 ? formSpecificContentIds[0] : "");

    try {
      setTriggering(true);
      const res = await socialApi.triggerEngagement({
        targetAccountId: formTargetAccountId || formCommenters[0]?.accountId,
        targetMode: formTargetMode,
        targetUrl: formTargetMode === "url" ? formTargetUrl : undefined,
        contentId: formTargetMode === "url" ? (resolvedCid || undefined) : (formSpecificContentIds[0] || undefined),
        contentIds: formTargetMode === "specific" ? formSpecificContentIds : undefined,
        metadata: resolvedUrlData
          ? {
              title: resolvedUrlData.title,
              description: resolvedUrlData.description,
              uploader: resolvedUrlData.uploader,
              platform: resolvedUrlData.platform,
            }
          : undefined,
        delayMinutes: Number(formDelayMinutes) || 0,
        autoLikeComments: formAutoLikeComments,
        commenters: formCommenters.map((c) => ({
          accountId: c.accountId,
          accountName: accounts.find((a) => a.id === c.accountId)?.name || c.accountName || "",
          roleCategory: c.roleCategory || "pro",
          persona: c.persona || "Reaksi natural",
        })),
      });
      alert(res.message || "Tugas auto engagement berhasil dijadwalkan!");
      navigate("/social-engagement");
    } catch (err: any) {
      alert(`Gagal menjalankan engagement: ${err.message || err}`);
    } finally {
      setTriggering(false);
    }
  };

  const handleSaveRule = async () => {
    if (formTargetMode === "url") {
      if (!formTargetUrl.trim() && !resolvedUrlData) {
        alert("Masukkan URL video pada Langkah 2 terlebih dahulu");
        return;
      }
    } else {
      if (!formTargetAccountId) {
        alert("Pilih akun target utama (Akun A)");
        return;
      }
      if (formTargetMode === "specific" && formSpecificContentIds.length === 0) {
        alert("Pilih minimal satu video spesifik dari galeri atau masukkan Content ID");
        return;
      }
    }

    if (formCommenters.length === 0 || formCommenters.some((c) => !c.accountId)) {
      alert("Pilih minimal satu akun pengomentar");
      return;
    }

    const targetAcc = accounts.find((a) => a.id === formTargetAccountId);
    const resolvedCid = resolvedUrlData?.contentId || (formSpecificContentIds.length > 0 ? formSpecificContentIds[0] : "");
    const payload = {
      name: formName || "Auto Engagement Rule",
      targetAccountId: formTargetAccountId || (formCommenters[0]?.accountId || ""),
      targetAccountName: targetAcc?.name || (resolvedUrlData?.uploader || ""),
      targetPlatform: targetAcc?.platform || resolvedUrlData?.platform || "tiktok",
      targetMode: formTargetMode,
      targetUrl: formTargetMode === "url" ? formTargetUrl : "",
      specificContentIds: formTargetMode === "url" && resolvedCid ? [resolvedCid] : formSpecificContentIds,
      specificContentId: resolvedCid,
      isActive: formIsActive,
      delayMinutes: Number(formDelayMinutes) || 0,
      autoLikeComments: formAutoLikeComments,
      commenters: formCommenters.map((c) => ({
        accountId: c.accountId,
        accountName: accounts.find((a) => a.id === c.accountId)?.name || c.accountName || "",
        roleCategory: c.roleCategory || "pro",
        persona: c.persona || "Reaksi natural",
      })),
    };

    try {
      setSaving(true);
      if (editRuleId) {
        await socialApi.updateEngagementRule(editRuleId, payload);
      } else {
        await socialApi.createEngagementRule(payload);
      }
      navigate("/social-engagement");
    } catch (err: any) {
      alert(`Gagal menyimpan aturan: ${err.message || err}`);
    } finally {
      setSaving(false);
    }
  };

  const handlePreviewAI = async () => {
    if (formCommenters.length === 0) return;
    setPreviewLoading(true);
    setPreviewModalOpen(true);
    try {
      const mockMeta = resolvedUrlData
        ? {
            title: resolvedUrlData.title,
            description: resolvedUrlData.description,
            topic: resolvedUrlData.uploader || "Video Target",
          }
        : {
            title: "Trik Bikin Konten FYP Tiap Hari",
            description: "Rahasia konsisten upload video tanpa burnout untuk kreator skena Jakarta",
            topic: "Edukasi & Lifestyle",
          };
      const res = await socialApi.previewEngagementComments(
        mockMeta,
        formCommenters.map((c) => ({
          accountId: c.accountId,
          accountName: accounts.find((a) => a.id === c.accountId)?.name || c.accountName || "Akun",
          roleCategory: c.roleCategory || "pro",
          persona: c.persona,
        }))
      );
      setPreviewResults(res?.previews || []);
    } catch (err: any) {
      alert(`Gagal generate preview: ${err.message || err}`);
    } finally {
      setPreviewLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="h-6 w-6 animate-spin text-emerald-400" />
          <span className="text-xs text-zinc-400">Memuat konfigurasi Engagement Studio...</span>
        </div>
      </div>
    );
  }

  const targetAccountObj = accounts.find((a) => a.id === formTargetAccountId);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto pr-1">
      <div className="space-y-6 max-w-6xl mx-auto w-full pb-20">
        {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate("/social-engagement")}
            className="p-2 rounded-xl border border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
            title="Kembali ke Dashboard Engagement"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-semibold text-zinc-100">
                {editRuleId ? "Edit Aturan Engagement" : "Studio Konfigurasi Engagement"}
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 uppercase">
                Superadmin Only
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-0.5">
              Kelola alur komentar silang multi-akun, auto-like antar bot, dan persona skena Jaksel.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={handlePreviewAI}
            className="flex items-center gap-2 px-3 py-2 rounded-xl border border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 text-xs font-medium transition-colors"
          >
            <Sparkles className="h-4 w-4 text-cyan-400" />
            Preview AI
          </button>
          <button
            type="button"
            onClick={handleDirectTrigger}
            disabled={triggering}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 text-xs font-semibold transition-colors disabled:opacity-50"
          >
            {triggering ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4 fill-current" />}
            Jalankan Sekarang
          </button>
          <button
            type="button"
            onClick={handleSaveRule}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-zinc-950 text-xs font-semibold transition-colors disabled:opacity-50 shadow-lg shadow-emerald-500/20"
          >
            {saving ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
            {editRuleId ? "Simpan Perubahan" : "Aktifkan Aturan Baru"}
          </button>
        </div>
      </div>

      {/* Basic Settings Card */}
      <div className="p-5 rounded-2xl border border-zinc-800 bg-zinc-900/40 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="sm:col-span-2 space-y-1.5">
            <label className="text-zinc-400 text-xs font-medium">Nama Kampanye / Aturan</label>
            <input
              type="text"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              placeholder="Contoh: Auto Engagement Trio TikTok"
              className="w-full px-3.5 py-2 rounded-xl border border-zinc-800 bg-zinc-950/60 text-zinc-200 text-xs focus:outline-none focus:border-emerald-500"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-zinc-400 text-xs font-medium">Status Otomasi</label>
            <div className="flex items-center gap-3 pt-1">
              <Toggle checked={formIsActive} onChange={setFormIsActive} />
              <span className="text-xs font-semibold text-zinc-200">
                {formIsActive ? "Aktif Berjalan" : "Nonaktif"}
              </span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-zinc-800/60">
          {/* Staggered Delay Setting */}
          <div className="p-3.5 rounded-xl border border-zinc-800/80 bg-zinc-950/40 space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-zinc-300 flex items-center gap-1.5">
                <Timer className="h-4 w-4 text-amber-400" />
                Jeda Waktu Antar User (Menit)
              </label>
              <span className="font-mono text-amber-400 font-bold text-xs">{formDelayMinutes} Menit</span>
            </div>
            <input
              type="number"
              min="0"
              max="120"
              value={formDelayMinutes}
              onChange={(e) => setFormDelayMinutes(Math.max(0, parseInt(e.target.value) || 0))}
              className="w-full px-3 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-200 text-xs focus:outline-none focus:border-emerald-500"
            />
            <p className="text-[11px] text-zinc-500 leading-snug">
              User 1 komentar menit 0, User 2 menit ke-{formDelayMinutes}, User 3 menit ke-{formDelayMinutes * 2}, dst.
            </p>
          </div>

          {/* Auto-Like Setting */}
          <div className="p-3.5 rounded-xl border border-zinc-800/80 bg-zinc-950/40 space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-zinc-300 flex items-center gap-1.5">
                <ThumbsUp className="h-4 w-4 text-emerald-400" />
                Fitur Auto-Like Antar Akun
              </label>
              <Toggle checked={formAutoLikeComments} onChange={setFormAutoLikeComments} />
            </div>
            <p className="text-[11px] text-zinc-400 leading-snug pt-1">
              Ketika Akun C berkomentar, otomatis memberikan like pada komentar Akun B sebelumnya melalui Repliz API (menaikkan engagement & ranking FYP).
            </p>
          </div>
        </div>
      </div>

      {/* Target Account Selection with Platform Filter Icons */}
      <div className="p-5 rounded-2xl border border-zinc-800 bg-zinc-900/40 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
              <Layers className="h-4 w-4 text-cyan-400" />
              1. Pilih Akun Target Utama (Akun A)
            </h3>
            <p className="text-xs text-zinc-400 mt-0.5">
              Akun target yang memposting video. Semua akun lain di platform yang sama otomatis menjadi pengomentar.
            </p>
          </div>

          {/* Platform Filter Buttons */}
          <div className="flex items-center gap-1.5 bg-zinc-950 p-1 rounded-xl border border-zinc-800 overflow-x-auto">
            <button
              onClick={() => setSelectedPlatform("all")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                selectedPlatform === "all"
                  ? "bg-zinc-800 text-zinc-100 shadow"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Semua ({accounts.length})
            </button>
            {platformKeys.map((p) => (
              <button
                key={p}
                onClick={() => setSelectedPlatform(p)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  selectedPlatform === p
                    ? "bg-zinc-800 text-zinc-100 shadow"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <PlatformIcon type={p} className="h-3.5 w-3.5" />
                <span className="capitalize">{p}</span> ({platformStats[p]})
              </button>
            ))}
          </div>
        </div>

        {/* Accounts Card Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {filteredAccounts.map((acc) => {
            const isSelected = formTargetAccountId === acc.id;
            const peerCount = accounts.filter(
              (a) => (a.platform || "").toLowerCase() === (acc.platform || "").toLowerCase() && a.id !== acc.id
            ).length;

            return (
              <div
                key={acc.id}
                onClick={() => handleSelectTargetAccount(acc)}
                className={`group relative p-3.5 rounded-xl border cursor-pointer transition-all flex items-center gap-3 ${
                  isSelected
                    ? "border-emerald-500 bg-emerald-500/10 ring-1 ring-emerald-500 shadow-lg shadow-emerald-500/10"
                    : "border-zinc-800/80 bg-zinc-950/60 hover:border-zinc-700 hover:bg-zinc-900"
                }`}
              >
                <div className="h-10 w-10 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center shrink-0 overflow-hidden">
                  {acc.picture ? (
                    <img src={acc.picture} alt={acc.name} className="h-full w-full object-cover" />
                  ) : (
                    <PlatformIcon type={acc.platform} className="h-5 w-5" />
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <PlatformIcon type={acc.platform} className="h-3.5 w-3.5" />
                    <span className="text-xs font-semibold text-zinc-100 truncate">{acc.name}</span>
                  </div>
                  <p className="text-[10px] text-zinc-500 truncate mt-0.5">
                    {peerCount} akun pengomentar siap
                  </p>
                </div>

                {isSelected && (
                  <div className="h-5 w-5 rounded-full bg-emerald-500 text-zinc-950 flex items-center justify-center shrink-0">
                    <CheckCircle2 className="h-3.5 w-3.5 fill-current" />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Target Content Selection (Latest vs Specific vs Direct URL) */}
      <div className="p-5 rounded-2xl border border-zinc-800 bg-zinc-900/40 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
              <Video className="h-4 w-4 text-emerald-400" />
              2. Target Postingan Video {targetAccountObj ? `(${targetAccountObj.name})` : ""}
            </h3>
            <p className="text-xs text-zinc-400 mt-0.5">
              Pilih apakah bot akan otomatis komentar di video terbaru, memilih spesifik dari galeri akun, atau memasukkan link URL video langsung.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2 bg-zinc-950 p-1.5 rounded-xl border border-zinc-800 text-xs">
            <label className={`flex items-center gap-2 px-3 py-1.5 rounded-lg cursor-pointer transition-colors ${
              formTargetMode === "latest" ? "bg-zinc-800 text-emerald-400 font-semibold" : "text-zinc-400 hover:text-zinc-200"
            }`}>
              <input
                type="radio"
                name="targetMode"
                value="latest"
                checked={formTargetMode === "latest"}
                onChange={() => setFormTargetMode("latest")}
                className="accent-emerald-500"
              />
              <span>Postingan Terbaru</span>
            </label>

            <label className={`flex items-center gap-2 px-3 py-1.5 rounded-lg cursor-pointer transition-colors ${
              formTargetMode === "specific" ? "bg-zinc-800 text-emerald-400 font-semibold" : "text-zinc-400 hover:text-zinc-200"
            }`}>
              <input
                type="radio"
                name="targetMode"
                value="specific"
                checked={formTargetMode === "specific"}
                onChange={() => setFormTargetMode("specific")}
                className="accent-emerald-500"
              />
              <span>Pilih Spesifik ({formSpecificContentIds.length} dipilih)</span>
            </label>

            <label className={`flex items-center gap-2 px-3 py-1.5 rounded-lg cursor-pointer transition-colors ${
              formTargetMode === "url" ? "bg-zinc-800 text-emerald-400 font-semibold" : "text-zinc-400 hover:text-zinc-200"
            }`}>
              <input
                type="radio"
                name="targetMode"
                value="url"
                checked={formTargetMode === "url"}
                onChange={() => setFormTargetMode("url")}
                className="accent-emerald-500"
              />
              <span className="flex items-center gap-1.5">
                <Link className="h-3.5 w-3.5 text-cyan-400" />
                Input URL Video Langsung
              </span>
            </label>
          </div>
        </div>

        {/* Mode 1: Latest Post Info */}
        {formTargetMode === "latest" && (
          <div className="p-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5 space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-emerald-400">
              <CheckCircle2 className="h-4 w-4" />
              <span>Otomatis Menargetkan Postingan Terbaru (Strict Latest Publication)</span>
            </div>
            <p className="text-xs text-zinc-300 leading-relaxed">
              Sistem secara otomatis mengambil postingan terbaru yang diterbitkan oleh Akun Target Utama dan mengurutkan secara ketat berdasarkan tanggal publikasi terkini (descending). Setiap kali dipicu, komentar hanya akan ditujukan ke postingan yang paling baru dirilis sehingga tidak akan kembali ke video lama.
            </p>
          </div>
        )}

        {/* Mode 2: Specific Post Selection */}
        {formTargetMode === "specific" && (
          <div className="space-y-3 pt-2 border-t border-zinc-800/60">
            {!formTargetAccountId ? (
              <div className="p-4 rounded-xl border border-amber-500/30 bg-amber-500/10 flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-xs font-semibold text-amber-300">Akun Target Utama Belum Dipilih</h4>
                  <p className="text-xs text-zinc-300 mt-1">
                    Silakan pilih salah satu Akun Target Utama pada Langkah 1 terlebih dahulu untuk memuat galeri postingan video akun tersebut.
                  </p>
                </div>
              </div>
            ) : (
              <>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="text-zinc-400">
                      Pilih satu atau lebih video dari galeri akun <strong className="text-zinc-200">{targetAccountObj?.name}</strong>:
                    </span>
                    <span className="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 font-mono text-[11px]">
                      {formSpecificContentIds.length} dipilih
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <div className="relative">
                      <Search className="h-3.5 w-3.5 text-zinc-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
                      <input
                        type="text"
                        value={gallerySearchQuery}
                        onChange={(e) => setGallerySearchQuery(e.target.value)}
                        placeholder="Cari judul video..."
                        className="pl-8 pr-3 py-1 rounded-lg border border-zinc-800 bg-zinc-950 text-zinc-200 text-xs focus:outline-none focus:border-emerald-500 w-44"
                      />
                    </div>
                    {formSpecificContentIds.length > 0 && (
                      <button
                        type="button"
                        onClick={() => setFormSpecificContentIds([])}
                        className="text-rose-400 hover:text-rose-300 text-xs underline"
                      >
                        Reset Pilihan
                      </button>
                    )}
                  </div>
                </div>

                {loadingContents ? (
                  <div className="flex items-center justify-center gap-2 py-12 text-zinc-500 text-xs">
                    <RefreshCw className="h-4 w-4 animate-spin text-cyan-400" />
                    <span>Mengambil galeri video akun target...</span>
                  </div>
                ) : targetContents.length > 0 ? (
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3 max-h-80 overflow-y-auto pr-1">
                    {targetContents
                      .filter((c) => {
                        if (!gallerySearchQuery.trim()) return true;
                        const q = gallerySearchQuery.toLowerCase();
                        return (
                          (c.title || "").toLowerCase().includes(q) ||
                          (c.description || "").toLowerCase().includes(q) ||
                          (c.id || "").toLowerCase().includes(q)
                        );
                      })
                      .map((c) => {
                        const isSelected = formSpecificContentIds.includes(c.id);
                        return (
                          <div
                            key={c.id}
                            onClick={() => {
                              setFormSpecificContentIds((prev) =>
                                isSelected ? prev.filter((id) => id !== c.id) : [...prev, c.id]
                              );
                            }}
                            className={`group relative rounded-xl border p-2 flex flex-col gap-2 cursor-pointer transition-all ${
                              isSelected
                                ? "border-emerald-500 bg-emerald-500/15 ring-1 ring-emerald-500 shadow-lg shadow-emerald-500/10"
                                : "border-zinc-800 bg-zinc-950/60 hover:border-zinc-700 hover:bg-zinc-900"
                            }`}
                          >
                            {/* Video Thumbnail */}
                            <div className="aspect-[9/16] w-full bg-zinc-950 rounded-lg overflow-hidden relative flex items-center justify-center">
                              {c.thumbnail ? (
                                <img
                                  src={c.thumbnail}
                                  alt={c.title || "Video thumbnail"}
                                  className="w-full h-full object-cover transition-transform group-hover:scale-105"
                                />
                              ) : (
                                <div className="text-zinc-600 flex flex-col items-center gap-1">
                                  <Video className="h-6 w-6" />
                                  <span className="text-[9px]">No Media</span>
                                </div>
                              )}

                              <div
                                className={`absolute top-2 right-2 rounded-full p-1 transition-all ${
                                  isSelected
                                    ? "bg-emerald-500 text-zinc-950"
                                    : "bg-black/60 text-transparent border border-zinc-700"
                                }`}
                              >
                                <CheckCircle2 className="h-3.5 w-3.5 fill-current" />
                              </div>
                            </div>

                            <div className="space-y-0.5">
                              <p className="text-[11px] font-medium text-zinc-200 line-clamp-2 leading-snug">
                                {c.title || c.description || "Video Tanpa Judul"}
                              </p>
                              <p className="text-[9px] text-zinc-500">
                                {c.createdAt ? new Date(c.createdAt).toLocaleDateString() : ""}
                              </p>
                            </div>
                          </div>
                        );
                      })}
                  </div>
                ) : (
                  <div className="text-center py-8 text-zinc-500 border border-zinc-800/80 rounded-xl text-xs">
                    Tidak ada video yang ditemukan dari akun target ini.
                  </div>
                )}

                {/* Manual Content ID */}
                <div className="pt-2 flex items-center gap-2">
                  <input
                    type="text"
                    value={manualContentIdInput}
                    onChange={(e) => setManualContentIdInput(e.target.value)}
                    placeholder="Atau tambahkan Content ID manual (misal: 113958387982006_942538351814577)"
                    className="flex-1 px-3 py-2 rounded-xl border border-zinc-800 bg-zinc-950 text-zinc-200 focus:outline-none focus:border-emerald-500 font-mono text-xs"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      const val = manualContentIdInput.trim();
                      if (val && !formSpecificContentIds.includes(val)) {
                        setFormSpecificContentIds((prev) => [...prev, val]);
                        setManualContentIdInput("");
                      }
                    }}
                    className="px-4 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-semibold"
                  >
                    Tambah ID
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {/* Mode 3: Direct Video URL Input */}
        {formTargetMode === "url" && (
          <div className="space-y-4 pt-3 border-t border-zinc-800/60">
            <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-950/80 space-y-3">
              <label className="text-xs font-semibold text-zinc-300 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <Link className="h-4 w-4 text-cyan-400" />
                  Masukkan URL Video (TikTok, YouTube, Instagram Reels, atau Repliz)
                </span>
                <span className="text-[11px] text-zinc-500">Mendukung link pendek & link web</span>
              </label>

              <div className="flex gap-2">
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={formTargetUrl}
                    onChange={(e) => {
                      setFormTargetUrl(e.target.value);
                      if (resolvedUrlData && e.target.value !== resolvedUrlData.url) {
                        setResolvedUrlData(null);
                      }
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        handleResolveUrl();
                      }
                    }}
                    placeholder="Contoh: https://www.tiktok.com/@username/video/7345678901234567890 atau https://youtu.be/..."
                    className="w-full px-3.5 py-2.5 rounded-xl border border-zinc-800 bg-zinc-900 text-zinc-200 text-xs focus:outline-none focus:border-emerald-500 font-mono"
                  />
                  {formTargetUrl && (
                    <button
                      type="button"
                      onClick={() => {
                        setFormTargetUrl("");
                        setResolvedUrlData(null);
                      }}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>

                <button
                  type="button"
                  disabled={resolvingUrl || !formTargetUrl.trim()}
                  onClick={() => handleResolveUrl()}
                  className="px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold flex items-center gap-2 transition-all shadow-lg shadow-emerald-900/20 shrink-0"
                >
                  {resolvingUrl ? (
                    <>
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      <span>Memeriksa...</span>
                    </>
                  ) : (
                    <>
                      <Search className="h-3.5 w-3.5" />
                      <span>Periksa & Dapatkan ID</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Resolved Video Card Preview */}
            {resolvedUrlData && (
              <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5">
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                    Video Berhasil Ditemukan & Terverifikasi
                  </span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-zinc-800 text-zinc-300 border border-zinc-700">
                    {resolvedUrlData.platform}
                  </span>
                </div>

                <div className="flex flex-col sm:flex-row gap-4">
                  {resolvedUrlData.thumbnail && (
                    <div className="w-28 aspect-[9/16] sm:w-24 sm:aspect-[9/16] bg-zinc-950 rounded-lg overflow-hidden border border-zinc-800 shrink-0">
                      <img
                        src={resolvedUrlData.thumbnail}
                        alt={resolvedUrlData.title}
                        className="w-full h-full object-cover"
                      />
                    </div>
                  )}

                  <div className="flex-1 min-w-0 space-y-2">
                    <div>
                      <h4 className="text-sm font-semibold text-zinc-100 line-clamp-2">
                        {resolvedUrlData.title || "Video Tanpa Judul"}
                      </h4>
                      {resolvedUrlData.uploader && (
                        <p className="text-xs text-zinc-400 mt-0.5">
                          Oleh: <span className="text-zinc-200 font-medium">{resolvedUrlData.uploader}</span>
                        </p>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-2 pt-1 text-[11px]">
                      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-zinc-950 border border-zinc-800 font-mono text-zinc-300">
                        <span className="text-zinc-500 text-[10px]">CONTENT ID:</span>
                        <span className="text-emerald-400 font-bold">{resolvedUrlData.contentId}</span>
                      </div>

                      {resolvedUrlData.durationFormatted && (
                        <div className="px-2.5 py-1 rounded-md bg-zinc-950 border border-zinc-800 font-mono text-zinc-400">
                          {resolvedUrlData.durationFormatted}
                        </div>
                      )}

                      <a
                        href={resolvedUrlData.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-zinc-900 hover:bg-zinc-800 text-cyan-400 text-xs transition-colors"
                      >
                        <span>Buka Link</span>
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Auto-Assigned Commenters & Personas */}
      <div className="p-5 rounded-2xl border border-zinc-800 bg-zinc-900/40 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-amber-400" />
              3. Akun Pengomentar & Persona AI ({formCommenters.length} Akun Terpilih)
            </h3>
            <p className="text-xs text-zinc-400 mt-0.5">
              Tentukan akun pengomentar dan variasikan peran unik (Pro, Kontra, Netral, Hate, dll) dengan jeda waktu aman antar user.
            </p>
          </div>

          {/* Add extra commenter dropdown */}
          {accounts.filter((a) => !formCommenters.some((c) => c.accountId === a.id)).length > 0 && (
            <div className="flex items-center gap-2">
              <select
                onChange={(e) => {
                  if (e.target.value) {
                    handleAddCommenter(e.target.value);
                    e.target.value = "";
                  }
                }}
                defaultValue=""
                className="px-3 py-1.5 rounded-xl border border-zinc-800 bg-zinc-950 text-zinc-200 text-xs focus:outline-none focus:border-emerald-500"
              >
                <option value="" disabled>
                  + Tambah Akun Pengomentar Lain...
                </option>
                {accounts
                  .filter((a) => !formCommenters.some((c) => c.accountId === a.id))
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} ({a.platform})
                    </option>
                  ))}
              </select>
            </div>
          )}
        </div>

        {formCommenters.length === 0 ? (
          <div className="p-8 text-center border border-zinc-800/80 rounded-xl text-xs text-zinc-500 bg-zinc-950/40">
            Belum ada akun pengomentar yang ditambahkan. Silakan pilih akun di atas atau hubungkan akun sosial media baru.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {formCommenters.map((commenter, idx) => {
              const roleObj =
                ROLE_OPTIONS.find((r) => r.value === (commenter.roleCategory || "pro")) ||
                ROLE_OPTIONS[0];

              return (
                <div
                  key={idx}
                  className="p-4 rounded-xl border border-zinc-800 bg-zinc-950/60 space-y-3 relative group"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-zinc-300">
                        #{idx + 1}
                      </span>
                      <span className="text-xs font-semibold text-zinc-100">
                        {commenter.accountName || commenter.accountId}
                      </span>
                      <span className="text-[10px] text-amber-400 font-mono">
                        (+{idx * formDelayMinutes}m)
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded border text-[10px] font-mono ${roleObj.badgeColor}`}>
                        {roleObj.label}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleRemoveCommenter(idx)}
                        className="p-1 rounded text-zinc-500 hover:text-rose-400 hover:bg-zinc-900 transition-colors"
                        title="Hapus akun pengomentar ini"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-[10px] text-zinc-400">
                      <span>Pilih Kategori Peran:</span>
                      <span className="text-zinc-500">{roleObj.desc}</span>
                    </div>
                    <select
                      value={commenter.roleCategory || "pro"}
                      onChange={(e) => {
                        const val = e.target.value as any;
                        const matchedRole = ROLE_OPTIONS.find((r) => r.value === val);
                        setFormCommenters((prev) =>
                          prev.map((c, i) =>
                            i === idx
                              ? {
                                  ...c,
                                  roleCategory: val,
                                  persona: matchedRole?.defaultPersona || c.persona,
                                }
                              : c
                          )
                        );
                      }}
                      className="w-full px-2.5 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-200 text-xs focus:outline-none focus:border-emerald-500 font-medium"
                    >
                      {ROLE_OPTIONS.map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label} — {r.desc}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-[10px] text-zinc-400">
                      <span>Instruksi Persona AI (Skena Jaksel):</span>
                      <span className="text-zinc-500 italic">Otomatis / opsional edit</span>
                    </div>
                    <input
                      type="text"
                      value={commenter.persona}
                      onChange={(e) => {
                        const val = e.target.value;
                        setFormCommenters((prev) =>
                          prev.map((c, i) => (i === idx ? { ...c, persona: val } : c))
                        );
                      }}
                      className="w-full px-2.5 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-200 text-xs focus:outline-none focus:border-emerald-500 font-mono"
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* AI Preview Modal */}
      {previewModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="w-full max-w-xl rounded-2xl border border-zinc-800 bg-[#0d0d11] p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-cyan-400" />
                <h3 className="text-sm font-semibold text-zinc-100">
                  Preview Variasi Komentar Skena Jaksel
                </h3>
              </div>
              <button
                onClick={() => setPreviewModalOpen(false)}
                className="p-1 rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {previewLoading ? (
              <div className="py-8 text-center text-xs text-zinc-400 flex flex-col items-center gap-2">
                <RefreshCw className="h-5 w-5 animate-spin text-cyan-400" />
                <span>LLM sedang membuat komentar unik untuk tiap akun...</span>
              </div>
            ) : (
              <div className="space-y-2.5 max-h-96 overflow-y-auto pr-1">
                {previewResults.map((p, idx) => {
                  const roleObj =
                    ROLE_OPTIONS.find((r) => r.value === (p.roleCategory || "pro")) ||
                    ROLE_OPTIONS[0];
                  return (
                    <div
                      key={idx}
                      className="p-3 rounded-xl border border-zinc-800/80 bg-zinc-950/60 space-y-1.5 text-xs"
                    >
                      <div className="flex items-center justify-between text-zinc-400">
                        <span className="font-semibold text-zinc-200">
                          {p.accountName || p.accountId}
                        </span>
                        <span className={`px-1.5 py-0.5 rounded border text-[10px] font-mono ${roleObj.badgeColor}`}>
                          {roleObj.label}
                        </span>
                      </div>
                      <p className="text-emerald-300 font-medium italic bg-zinc-900/60 p-2.5 rounded-lg border border-zinc-800/50">
                        "{p.comment}"
                      </p>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="flex justify-end pt-2 border-t border-zinc-800/80">
              <button
                onClick={() => setPreviewModalOpen(false)}
                className="px-4 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs font-semibold text-zinc-200"
              >
                Tutup
              </button>
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}
