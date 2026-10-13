import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  MessageSquareQuote,
  Plus,
  Play,
  Trash2,
  Edit2,
  RefreshCw,
  Clock,
  ShieldCheck,
  AlertCircle,
  CheckCircle2,
  Users,
  Video,
  Sparkles,
  Timer,
  ChevronRight,
  X,
  Sliders,
  Send,
  StopCircle,
  Eye,
  CornerDownRight,
} from "lucide-react";
import { socialApi } from "@/lib/api";
import { Toggle } from "@/components/ui/Toggle";

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

interface EngagementRule {
  id: number;
  name: string;
  targetAccountId: string;
  targetAccountName: string;
  targetPlatform: string;
  targetMode: "latest" | "specific";
  specificContentId: string;
  specificContentIds?: string[];
  isActive: boolean;
  delayMinutes: number;
  commenters: CommenterConfig[];
  createdAt: string;
  updatedAt: string;
}

interface EngagementTask {
  id: number;
  rule_id: number | null;
  content_id: string;
  target_account_id: string;
  target_mode: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  total_commenters: number;
  completed_commenters: number;
  created_at: string;
  updated_at: string;
}

interface EngagementLog {
  id: number;
  task_id: number;
  rule_id: number;
  content_id: string;
  target_account_id: string;
  commenter_account_id: string;
  commenter_account_name: string;
  comment_text: string;
  scheduled_at: string | null;
  executed_at: string | null;
  status: "pending" | "waiting_delay" | "posting" | "success" | "failed" | "cancelled";
  repliz_comment_id: string;
  error_message: string;
  created_at: string;
}

interface SocialAccountOption {
  id: string;
  name: string;
  platform: string;
  username?: string;
}

export function SocialEngagement() {
  const navigate = useNavigate();
  const [rules, setRules] = useState<EngagementRule[]>([]);
  const [tasks, setTasks] = useState<EngagementTask[]>([]);
  const [logs, setLogs] = useState<EngagementLog[]>([]);
  const [accounts, setAccounts] = useState<SocialAccountOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Modal State
  const [modalOpen, setModalOpen] = useState(false);
  const [editingRuleId, setEditingRuleId] = useState<number | null>(null);
  const [formName, setFormName] = useState("");
  const [formTargetAccountId, setFormTargetAccountId] = useState("");
  const [formTargetMode, setFormTargetMode] = useState<"latest" | "specific">("latest");
  const [formSpecificContentIds, setFormSpecificContentIds] = useState<string[]>([]);
  const [manualContentIdInput, setManualContentIdInput] = useState("");
  const [formDelayMinutes, setFormDelayMinutes] = useState(5);
  const [formIsActive, setFormIsActive] = useState(true);
  const [formCommenters, setFormCommenters] = useState<CommenterConfig[]>([]);

  // Content Selection Picker State
  const [targetContents, setTargetContents] = useState<any[]>([]);
  const [loadingContents, setLoadingContents] = useState(false);

  // Preview AI Comment State
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewResults, setPreviewResults] = useState<any[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Active Tab
  const [activeTab, setActiveTab] = useState<"rules" | "tasks" | "logs">("rules");
  const [triggeringId, setTriggeringId] = useState<number | null>(null);

  const loadData = useCallback(async () => {
    try {
      setRefreshing(true);
      const [rulesData, accountsData, tasksData, logsData] = await Promise.all([
        socialApi.getEngagementRules(),
        socialApi.getAccounts(),
        socialApi.getEngagementTasks(30),
        socialApi.getEngagementLogs({ limit: 50 }),
      ]);

      setRules(rulesData || []);
      const accDocs = (accountsData?.docs || []).map((a: any) => ({
        id: a._id || a.id,
        name: a.name || a.username || "Account",
        platform: a.type || a.platform || "tiktok",
        username: a.username || "",
      }));
      setAccounts(accDocs);
      setTasks(tasksData || []);
      setLogs(logsData || []);
    } catch (err) {
      console.error("Gagal memuat data engagement:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 15000); // Poll status every 15s
    return () => clearInterval(interval);
  }, [loadData]);

  // Load target account videos when target account changes & mode is specific
  useEffect(() => {
    if (formTargetAccountId && formTargetMode === "specific") {
      setLoadingContents(true);
      socialApi
        .getTargetAccountContents(formTargetAccountId, 15)
        .then((items) => {
          setTargetContents(items || []);
        })
        .catch(() => setTargetContents([]))
        .finally(() => setLoadingContents(false));
    } else {
      setTargetContents([]);
    }
  }, [formTargetAccountId, formTargetMode]);

  // Auto-sync commenters based on target account platform
  const syncCommentersForTarget = useCallback(
    (targetAccId: string, currentCommenters: CommenterConfig[] = []) => {
      const targetAcc = accounts.find((a) => a.id === targetAccId);
      if (!targetAcc) return [];

      const targetPlatform = targetAcc.platform || "tiktok";

      // Filter all accounts that share the SAME platform and EXCLUDE the target account itself
      const peerAccounts = accounts.filter(
        (a) =>
          (a.platform || "tiktok").toLowerCase() === targetPlatform.toLowerCase() &&
          a.id !== targetAccId
      );

      // Map each peer account to a commenter config
      return peerAccounts.map((a, idx) => {
        // Check if user already had a config for this account
        const existing = currentCommenters.find((c) => c.accountId === a.id);
        const role = ROLE_OPTIONS[idx % ROLE_OPTIONS.length];
        return {
          accountId: a.id,
          accountName: a.name,
          roleCategory: existing?.roleCategory || role.value,
          persona: existing?.persona || role.defaultPersona,
        };
      });
    },
    [accounts]
  );

  const handleTargetAccountChange = (newTargetId: string) => {
    setFormTargetAccountId(newTargetId);
    setFormSpecificContentIds([]);
    const autoCommenters = syncCommentersForTarget(newTargetId, formCommenters);
    setFormCommenters(autoCommenters);
  };
  const handleOpenCreate = () => {
    setEditingRuleId(null);
    setFormName("Auto Engagement Rule");
    const firstAcc = accounts[0];
    const firstAccId = firstAcc?.id || "";
    setFormTargetAccountId(firstAccId);
    setFormTargetMode("latest");
    setFormSpecificContentIds([]);
    setManualContentIdInput("");
    setFormDelayMinutes(5);
    setFormIsActive(true);

    const autoCommenters = syncCommentersForTarget(firstAccId);
    setFormCommenters(autoCommenters);
    setModalOpen(true);
  };

  const handleOpenEdit = (rule: EngagementRule) => {
    setEditingRuleId(rule.id);
    setFormName(rule.name);
    setFormTargetAccountId(rule.targetAccountId);
    setFormTargetMode(rule.targetMode);
    const contentIds = rule.specificContentIds && rule.specificContentIds.length > 0
      ? rule.specificContentIds
      : rule.specificContentId
      ? [rule.specificContentId]
      : [];
    setFormSpecificContentIds(contentIds);
    setManualContentIdInput("");
    setFormDelayMinutes(rule.delayMinutes ?? 5);
    setFormIsActive(rule.isActive);
    setFormCommenters(
      (rule.commenters || []).map((c) => ({
        ...c,
        roleCategory: c.roleCategory || "pro",
      }))
    );
    setModalOpen(true);
  };

  const handleSaveRule = async () => {
    if (!formTargetAccountId) {
      alert("Pilih akun target utama (Akun A)");
      return;
    }
    if (formCommenters.length === 0 || formCommenters.some((c) => !c.accountId)) {
      alert("Pilih minimal satu akun pengomentar");
      return;
    }

    const targetAcc = accounts.find((a) => a.id === formTargetAccountId);
    const payload = {
      name: formName || "Auto Engagement Rule",
      targetAccountId: formTargetAccountId,
      targetAccountName: targetAcc?.name || "",
      targetPlatform: targetAcc?.platform || "tiktok",
      targetMode: formTargetMode,
      specificContentIds: formSpecificContentIds,
      specificContentId: formSpecificContentIds[0] || "",
      isActive: formIsActive,
      delayMinutes: Number(formDelayMinutes) || 0,
      commenters: formCommenters.map((c) => ({
        accountId: c.accountId,
        accountName: accounts.find((a) => a.id === c.accountId)?.name || c.accountName || "",
        roleCategory: c.roleCategory || "pro",
        persona: c.persona || "Reaksi natural",
      })),
    };

    try {
      if (editingRuleId) {
        await socialApi.updateEngagementRule(editingRuleId, payload);
      } else {
        await socialApi.createEngagementRule(payload);
      }
      setModalOpen(false);
      loadData();
    } catch (err: any) {
      alert(`Gagal menyimpan rule: ${err.message || err}`);
    }
  };

  const handleToggleRule = async (ruleId: number, currentStatus: boolean) => {
    try {
      await socialApi.toggleEngagementRule(ruleId, !currentStatus);
      setRules((prev) =>
        prev.map((r) => (r.id === ruleId ? { ...r, isActive: !currentStatus } : r))
      );
    } catch (err: any) {
      alert(`Gagal mengubah status: ${err.message || err}`);
    }
  };

  const handleDeleteRule = async (ruleId: number) => {
    if (!confirm("Hapus rule auto engagement ini?")) return;
    try {
      await socialApi.deleteEngagementRule(ruleId);
      setRules((prev) => prev.filter((r) => r.id !== ruleId));
    } catch (err: any) {
      alert(`Gagal menghapus rule: ${err.message || err}`);
    }
  };

  const handleTriggerRule = async (rule: EngagementRule) => {
    try {
      setTriggeringId(rule.id);
      const res = await socialApi.triggerEngagement({ ruleId: rule.id });
      alert(res.message || "Tugas engagement berhasil dijadwalkan!");
      loadData();
      setActiveTab("tasks");
    } catch (err: any) {
      alert(`Gagal menjalankan engagement: ${err.message || err}`);
    } finally {
      setTriggeringId(null);
    }
  };

  const handleCancelTask = async (taskId: number) => {
    if (!confirm("Batalkan eksekusi tugas ini?")) return;
    try {
      await socialApi.cancelEngagementTask(taskId);
      loadData();
    } catch (err: any) {
      alert(`Gagal membatalkan task: ${err.message || err}`);
    }
  };

  const handlePreviewAI = async () => {
    if (formCommenters.length === 0) return;
    setPreviewLoading(true);
    setPreviewModalOpen(true);
    try {
      const mockMeta = {
        title: "Tips Produktivitas Konten Harian",
        description: "Rahasia konsisten upload video tanpa burnout untuk kreator TikTok",
        topic: "Tips & Edukasi",
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

  const addCommenterRow = () => {
    const unselected = accounts.find(
      (a) => a.id !== formTargetAccountId && !formCommenters.some((c) => c.accountId === a.id)
    );
    const nextRoleIndex = formCommenters.length % ROLE_OPTIONS.length;
    const defaultRole = ROLE_OPTIONS[nextRoleIndex];
    setFormCommenters((prev) => [
      ...prev,
      {
        accountId: unselected?.id || "",
        accountName: unselected?.name || "",
        roleCategory: defaultRole.value as any,
        persona: defaultRole.defaultPersona,
      },
    ]);
  };

  const removeCommenterRow = (index: number) => {
    setFormCommenters((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
              <MessageSquareQuote className="h-5 w-5" />
            </div>
            <h1 className="text-lg font-semibold text-zinc-100">Cross-Account Auto Engagement</h1>
          </div>
          <p className="text-xs text-zinc-400 mt-1">
            Otomasi komentar antar akun TikTok (Akun A posting, Akun B dan C otomatis komentar bertahap dengan perspektif unik via AI).
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800 text-xs font-medium text-zinc-300 transition-colors"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <button
            onClick={() => navigate("/social-engagement/studio")}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-xs font-semibold text-zinc-950 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            Buka Studio Engagement
          </button>
        </div>
      </div>

      {/* Stats Summary Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-xl border border-zinc-800/80 bg-zinc-900/40">
          <div className="flex items-center justify-between text-zinc-400 text-xs">
            <span>Total Aturan</span>
            <Sliders className="h-4 w-4 text-zinc-500" />
          </div>
          <div className="text-xl font-bold text-zinc-100 mt-1">{rules.length}</div>
        </div>

        <div className="p-3.5 rounded-xl border border-zinc-800/80 bg-zinc-900/40">
          <div className="flex items-center justify-between text-zinc-400 text-xs">
            <span>Aturan Aktif</span>
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="text-xl font-bold text-emerald-400 mt-1">
            {rules.filter((r) => r.isActive).length}
          </div>
        </div>

        <div className="p-3.5 rounded-xl border border-zinc-800/80 bg-zinc-900/40">
          <div className="flex items-center justify-between text-zinc-400 text-xs">
            <span>Tugas Berjalan / Antrean</span>
            <Timer className="h-4 w-4 text-amber-400" />
          </div>
          <div className="text-xl font-bold text-amber-400 mt-1">
            {tasks.filter((t) => t.status === "running" || t.status === "pending").length}
          </div>
        </div>

        <div className="p-3.5 rounded-xl border border-zinc-800/80 bg-zinc-900/40">
          <div className="flex items-center justify-between text-zinc-400 text-xs">
            <span>Total Komentar Terkirim</span>
            <CheckCircle2 className="h-4 w-4 text-cyan-400" />
          </div>
          <div className="text-xl font-bold text-cyan-400 mt-1">
            {logs.filter((l) => l.status === "success").length}
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex items-center gap-1 border-b border-zinc-800 pb-px">
        <button
          onClick={() => setActiveTab("rules")}
          className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold border-b-2 transition-colors ${
            activeTab === "rules"
              ? "border-emerald-500 text-emerald-400"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          <Sliders className="h-3.5 w-3.5" />
          Daftar Aturan ({rules.length})
        </button>

        <button
          onClick={() => setActiveTab("tasks")}
          className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold border-b-2 transition-colors ${
            activeTab === "tasks"
              ? "border-emerald-500 text-emerald-400"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          <Timer className="h-3.5 w-3.5" />
          Antrean Tugas ({tasks.filter((t) => t.status === "running" || t.status === "pending").length})
        </button>

        <button
          onClick={() => setActiveTab("logs")}
          className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold border-b-2 transition-colors ${
            activeTab === "logs"
              ? "border-emerald-500 text-emerald-400"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          <Clock className="h-3.5 w-3.5" />
          Riwayat Komentar ({logs.length})
        </button>
      </div>

      {/* Tab: Rules List */}
      {activeTab === "rules" && (
        <div className="space-y-3">
          {rules.length === 0 ? (
            <div className="text-center py-12 border border-zinc-800/80 rounded-xl bg-zinc-900/20">
              <MessageSquareQuote className="h-10 w-10 text-zinc-600 mx-auto mb-2" />
              <h3 className="text-sm font-semibold text-zinc-300">Belum ada aturan engagement</h3>
              <p className="text-xs text-zinc-500 max-w-md mx-auto mt-1 mb-4">
                Atur akun target A dan akun bot B & C untuk saling berkomentar otomatis dengan jeda waktu yang aman.
              </p>
              <button
                onClick={() => navigate("/social-engagement/studio")}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500 text-xs font-semibold text-zinc-950 hover:bg-emerald-600"
              >
                <Plus className="h-3.5 w-3.5" />
                Buka Studio Engagement
              </button>
            </div>
          ) : (
            rules.map((rule) => {
              const targetAcc = accounts.find((a) => a.id === rule.targetAccountId);
              return (
                <div
                  key={rule.id}
                  className="p-4 rounded-xl border border-zinc-800/80 bg-zinc-900/30 hover:border-zinc-700/80 transition-all space-y-3"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <Toggle
                        checked={rule.isActive}
                        onChange={() => handleToggleRule(rule.id, rule.isActive)}
                      />
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-zinc-100">{rule.name}</span>
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-medium uppercase ${
                              rule.isActive
                                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                : "bg-zinc-800 text-zinc-400"
                            }`}
                          >
                            {rule.isActive ? "Aktif" : "Non-Aktif"}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-zinc-400 mt-0.5">
                          <span>Target:</span>
                          <span className="text-zinc-200 font-medium">
                            {targetAcc?.name || rule.targetAccountName || rule.targetAccountId}
                          </span>
                          <span className="text-zinc-600">•</span>
                          <span className="text-cyan-400">
                            {rule.targetMode === "latest" ? "Postingan Terbaru" : `Spesifik (${rule.specificContentId || "-"})`}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleTriggerRule(rule)}
                        disabled={triggeringId === rule.id}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border border-emerald-500/30 text-xs font-semibold transition-colors disabled:opacity-50"
                        title="Eksekusi komentar sekarang"
                      >
                        <Play className={`h-3 w-3 ${triggeringId === rule.id ? "animate-spin" : ""}`} />
                        Jalankan Sekarang
                      </button>
                      <button
                        onClick={() => navigate(`/social-engagement/studio?edit=${rule.id}`)}
                        className="p-1.5 rounded-lg border border-zinc-800 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200"
                        title="Edit rule di Studio"
                      >
                        <Edit2 className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => handleDeleteRule(rule.id)}
                        className="p-1.5 rounded-lg border border-zinc-800 hover:bg-rose-500/10 text-zinc-400 hover:text-rose-400"
                        title="Hapus rule"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Commenters & Delay Flow Bar */}
                  <div className="p-2.5 rounded-lg bg-zinc-950/60 border border-zinc-800/60 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
                    <div className="flex items-center gap-2 text-zinc-400">
                      <Timer className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                      <span>
                        Jeda bertahap: <strong className="text-zinc-200">{rule.delayMinutes} menit</strong> per user
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-zinc-500">Alur:</span>
                      {rule.commenters.map((c, i) => {
                        const roleObj =
                          ROLE_OPTIONS.find((r) => r.value === (c.roleCategory || "pro")) ||
                          ROLE_OPTIONS[0];
                        return (
                          <div key={i} className="flex items-center gap-1">
                            {i > 0 && <ChevronRight className="h-3 w-3 text-zinc-600" />}
                            <span
                              className={`px-2 py-0.5 rounded border text-[11px] font-mono flex items-center gap-1 ${roleObj.badgeColor}`}
                              title={`Peran: ${roleObj.label} | Persona: ${c.persona}`}
                            >
                              <span>{c.accountName || c.accountId}</span>
                              <span className="text-[10px] opacity-80 uppercase font-semibold">
                                [{roleObj.label.split("/")[0].trim()}]
                              </span>
                              <span className="text-zinc-400 text-[10px]">
                                (+{i * rule.delayMinutes}m)
                              </span>
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Tab: Tasks Monitor */}
      {activeTab === "tasks" && (
        <div className="space-y-3">
          {tasks.length === 0 ? (
            <div className="text-center py-10 border border-zinc-800 rounded-xl bg-zinc-900/20 text-zinc-500 text-xs">
              Belum ada tugas engagement yang berjalan atau terjadwal.
            </div>
          ) : (
            tasks.map((task) => (
              <div
                key={task.id}
                className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-900/40 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-zinc-200">Tugas #{task.id}</span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-medium uppercase ${
                        task.status === "completed"
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                          : task.status === "running"
                          ? "bg-amber-500/10 text-amber-400 border border-amber-500/20 animate-pulse"
                          : task.status === "cancelled"
                          ? "bg-zinc-800 text-zinc-400"
                          : "bg-cyan-500/10 text-cyan-400"
                      }`}
                    >
                      {task.status}
                    </span>
                    <span className="text-zinc-500">•</span>
                    <span className="text-zinc-400 font-mono">Content: {task.content_id}</span>
                  </div>

                  <div className="text-zinc-400 mt-1 flex items-center gap-2">
                    <span>
                      Progress:{" "}
                      <strong className="text-zinc-200">
                        {task.completed_commenters} / {task.total_commenters} Akun
                      </strong>
                    </span>
                    <span className="text-zinc-600">•</span>
                    <span>Waktu: {new Date(task.created_at).toLocaleTimeString()}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {(task.status === "running" || task.status === "pending") && (
                    <button
                      onClick={() => handleCancelTask(task.id)}
                      className="flex items-center gap-1 px-2.5 py-1 rounded bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/30 text-rose-400 text-xs font-semibold"
                    >
                      <StopCircle className="h-3 w-3" />
                      Batalkan
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Tab: Logs History */}
      {activeTab === "logs" && (
        <div className="rounded-xl border border-zinc-800 overflow-hidden bg-zinc-900/30">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-zinc-900/70 border-b border-zinc-800 text-zinc-400">
                <tr>
                  <th className="py-2.5 px-3 font-medium">Status</th>
                  <th className="py-2.5 px-3 font-medium">Akun Pengomentar</th>
                  <th className="py-2.5 px-3 font-medium">Isi Komentar (AI)</th>
                  <th className="py-2.5 px-3 font-medium">Jadwal / Eksekusi</th>
                  <th className="py-2.5 px-3 font-medium">Repliz ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60 text-zinc-300">
                {logs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-zinc-500">
                      Belum ada catatan komentar.
                    </td>
                  </tr>
                ) : (
                  logs.map((log) => (
                    <tr key={log.id} className="hover:bg-zinc-900/40">
                      <td className="py-2.5 px-3 whitespace-nowrap">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-medium uppercase ${
                            log.status === "success"
                              ? "bg-emerald-500/10 text-emerald-400"
                              : log.status === "waiting_delay"
                              ? "bg-amber-500/10 text-amber-400 animate-pulse"
                              : log.status === "posting"
                              ? "bg-cyan-500/10 text-cyan-400"
                              : "bg-rose-500/10 text-rose-400"
                          }`}
                        >
                          {log.status === "waiting_delay" ? "Menunggu Jeda" : log.status}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-medium text-zinc-200 whitespace-nowrap">
                        {log.commenter_account_name || log.commenter_account_id}
                      </td>
                      <td className="py-2.5 px-3 max-w-xs truncate text-zinc-300" title={log.comment_text}>
                        {log.comment_text || <span className="text-zinc-600 italic">Belum digenerate</span>}
                      </td>
                      <td className="py-2.5 px-3 whitespace-nowrap text-zinc-400">
                        {log.executed_at
                          ? new Date(log.executed_at).toLocaleTimeString()
                          : log.scheduled_at
                          ? `Terjadwal ${new Date(log.scheduled_at).toLocaleTimeString()}`
                          : "-"}
                      </td>
                      <td className="py-2.5 px-3 font-mono text-[11px] text-zinc-500 whitespace-nowrap">
                        {log.repliz_comment_id || log.error_message || "-"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modal: Create / Edit Rule */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 sm:p-6 overflow-y-auto">
          <div className="w-full max-w-4xl max-h-[92vh] flex flex-col rounded-2xl border border-zinc-800 bg-[#0d0d11] shadow-2xl overflow-hidden animate-in fade-in-50 duration-150">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-zinc-800/80 px-6 py-4 shrink-0 bg-zinc-950/40">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
                  <Sliders className="h-4 w-4" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-zinc-100">
                    {editingRuleId ? "Edit Aturan Engagement" : "Buat Aturan Engagement Baru"}
                  </h2>
                  <p className="text-[11px] text-zinc-400">
                    Konfigurasi akun target, video spesifik, dan akun pengomentar otomatis.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setModalOpen(false)}
                className="p-1.5 rounded-lg text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 space-y-5 text-xs overflow-y-auto flex-1">
              {/* Rule Name & Active Toggle */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="sm:col-span-2 space-y-1.5">
                  <label className="text-zinc-400 font-medium">Nama Aturan</label>
                  <input
                    type="text"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="Contoh: Auto Comment TikTok Skena"
                    className="w-full px-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900/60 text-zinc-200 focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-zinc-400 font-medium">Status Otomasi</label>
                  <div className="flex items-center gap-2.5 pt-1">
                    <Toggle checked={formIsActive} onChange={setFormIsActive} />
                    <span className="text-zinc-300 font-medium">
                      {formIsActive ? "Aktif" : "Nonaktif"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Target Account (Akun A) */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-zinc-300 font-medium">
                    Akun Target Utama (Akun yang memposting video)
                  </label>
                  <span className="text-[11px] text-emerald-400 font-mono">
                    Akun pengomentar otomatis disesuaikan platform yang sama
                  </span>
                </div>
                <select
                  value={formTargetAccountId}
                  onChange={(e) => handleTargetAccountChange(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900/60 text-zinc-200 focus:outline-none focus:border-emerald-500"
                >
                  <option value="">-- Pilih Akun Target --</option>
                  {accounts.map((acc) => (
                    <option key={acc.id} value={acc.id}>
                      {acc.name} ({acc.platform})
                    </option>
                  ))}
                </select>
              </div>

              {/* Mode Target: Latest Post vs Specific Post */}
              <div className="space-y-3 p-4 rounded-xl border border-zinc-800/80 bg-zinc-950/40">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <label className="text-zinc-300 font-semibold flex items-center gap-1.5">
                    <Video className="h-4 w-4 text-cyan-400" />
                    Target Postingan Video
                  </label>
                  <div className="flex items-center gap-4">
                    <label className="flex items-center gap-2 text-zinc-300 cursor-pointer">
                      <input
                        type="radio"
                        name="targetMode"
                        value="latest"
                        checked={formTargetMode === "latest"}
                        onChange={() => setFormTargetMode("latest")}
                        className="accent-emerald-500"
                      />
                      <span>Otomatis di Postingan Terbaru</span>
                    </label>
                    <label className="flex items-center gap-2 text-zinc-300 cursor-pointer">
                      <input
                        type="radio"
                        name="targetMode"
                        value="specific"
                        checked={formTargetMode === "specific"}
                        onChange={() => setFormTargetMode("specific")}
                        className="accent-emerald-500"
                      />
                      <span>Pilih Postingan Spesifik (Bisa Multiple)</span>
                    </label>
                  </div>
                </div>

                {formTargetMode === "specific" && (
                  <div className="pt-2 space-y-3 border-t border-zinc-800/70">
                    <div className="flex items-center justify-between">
                      <span className="text-zinc-400 font-medium">
                        Pilih satu atau lebih video dari galeri akun target ({formSpecificContentIds.length} dipilih):
                      </span>
                      {formSpecificContentIds.length > 0 && (
                        <button
                          type="button"
                          onClick={() => setFormSpecificContentIds([])}
                          className="text-xs text-rose-400 hover:text-rose-300 underline"
                        >
                          Reset Pilihan
                        </button>
                      )}
                    </div>

                    {loadingContents ? (
                      <div className="flex items-center justify-center gap-2 py-8 text-zinc-500">
                        <RefreshCw className="h-4 w-4 animate-spin text-cyan-400" />
                        <span>Mengambil daftar video & thumbnail dari Repliz...</span>
                      </div>
                    ) : targetContents.length > 0 ? (
                      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 max-h-64 overflow-y-auto pr-1">
                        {targetContents.map((c) => {
                          const isSelected = formSpecificContentIds.includes(c.id);
                          return (
                            <div
                              key={c.id}
                              onClick={() => {
                                setFormSpecificContentIds((prev) =>
                                  isSelected
                                    ? prev.filter((id) => id !== c.id)
                                    : [...prev, c.id]
                                );
                              }}
                              className={`group relative rounded-xl border p-2 flex flex-col gap-2 cursor-pointer transition-all ${
                                isSelected
                                  ? "border-emerald-500 bg-emerald-500/10 shadow-lg shadow-emerald-500/10 ring-1 ring-emerald-500"
                                  : "border-zinc-800 bg-zinc-900/60 hover:border-zinc-700 hover:bg-zinc-900"
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
                                    <span className="text-[10px]">No Preview</span>
                                  </div>
                                )}

                                {/* Selection Checkmark Badge */}
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

                              {/* Title / Description */}
                              <div className="space-y-0.5">
                                <p className="text-[11px] font-medium text-zinc-200 line-clamp-2 leading-snug">
                                  {c.title || c.description || "Video Tanpa Judul"}
                                </p>
                                <p className="text-[10px] text-zinc-500">
                                  {c.createdAt ? new Date(c.createdAt).toLocaleDateString() : ""}
                                </p>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="text-center py-6 text-zinc-500 border border-zinc-800/80 rounded-lg">
                        Tidak ada postingan video yang ditemukan untuk akun ini.
                      </div>
                    )}

                    {/* Manual ID Input */}
                    <div className="pt-2 flex items-center gap-2">
                      <input
                        type="text"
                        value={manualContentIdInput}
                        onChange={(e) => setManualContentIdInput(e.target.value)}
                        placeholder="Atau tambah ID Postingan manual (misal: 113958387982006_942538351814577)"
                        className="flex-1 px-3 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-200 focus:outline-none focus:border-emerald-500 font-mono text-xs"
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
                        className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 font-semibold"
                      >
                        Tambah ID
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Delay Inter-User Setting */}
              <div className="space-y-1.5 p-4 rounded-xl border border-zinc-800/80 bg-zinc-950/40">
                <div className="flex items-center justify-between">
                  <label className="text-zinc-300 font-semibold flex items-center gap-1.5">
                    <Timer className="h-4 w-4 text-amber-400" />
                    Jeda Waktu Antar User Komentar (Menit)
                  </label>
                  <span className="font-mono text-amber-400 font-bold text-sm">{formDelayMinutes} Menit</span>
                </div>
                <input
                  type="number"
                  min="0"
                  max="120"
                  value={formDelayMinutes}
                  onChange={(e) => setFormDelayMinutes(Math.max(0, parseInt(e.target.value) || 0))}
                  className="w-full px-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-200 focus:outline-none focus:border-emerald-500"
                />
                <p className="text-[11px] text-zinc-500 leading-relaxed">
                  Contoh: Jika disetel 5 menit, maka Akun 1 komentar di menit ke-0, Akun 2 di menit ke-5, Akun 3 di menit ke-10, dst.
                </p>
              </div>

              {/* Commenter Accounts & Personas */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <label className="text-zinc-200 font-semibold flex items-center gap-1.5">
                      <Users className="h-4 w-4 text-emerald-400" />
                      Akun Pengomentar & Persona AI ({formCommenters.length} Akun)
                    </label>
                    <p className="text-[11px] text-zinc-500">
                      Otomatis mencakup semua akun se-platform selain akun target utama. Persona tidak wajib diubah karena sudah otomatis sesuai peran.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={addCommenterRow}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 text-xs font-semibold transition-colors"
                  >
                    <Plus className="h-3 w-3" /> Tambah Baris
                  </button>
                </div>

                <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
                  {formCommenters.length === 0 ? (
                    <div className="text-center py-6 text-zinc-500 border border-zinc-800/80 rounded-xl">
                      Tidak ada akun lain yang tersedia di platform yang sama.
                    </div>
                  ) : (
                    formCommenters.map((commenter, idx) => {
                      const currentRoleObj =
                        ROLE_OPTIONS.find((r) => r.value === (commenter.roleCategory || "pro")) ||
                        ROLE_OPTIONS[0];

                      return (
                        <div
                          key={idx}
                          className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-900/60 space-y-2.5"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-zinc-200">
                                #{idx + 1} {commenter.accountName || commenter.accountId}
                              </span>
                              <span className="text-[11px] text-amber-400 font-mono">
                                (+{idx * formDelayMinutes}m)
                              </span>
                            </div>
                            <button
                              type="button"
                              onClick={() => removeCommenterRow(idx)}
                              className="text-zinc-500 hover:text-rose-400 p-1 rounded"
                              title="Hapus baris pengomentar ini"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>

                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div>
                              <label className="text-[10px] text-zinc-400">Pilih Akun Pengomentar</label>
                              <select
                                value={commenter.accountId}
                                onChange={(e) => {
                                  const val = e.target.value;
                                  setFormCommenters((prev) =>
                                    prev.map((c, i) =>
                                      i === idx
                                        ? {
                                            ...c,
                                            accountId: val,
                                            accountName: accounts.find((a) => a.id === val)?.name || "",
                                          }
                                        : c
                                    )
                                  );
                                }}
                                className="w-full mt-1 px-2.5 py-1.5 rounded border border-zinc-800 bg-zinc-900 text-zinc-200 text-xs focus:outline-none focus:border-emerald-500"
                              >
                                <option value="">-- Pilih Akun --</option>
                                {accounts
                                  .filter((a) => a.id !== formTargetAccountId)
                                  .map((acc) => (
                                    <option key={acc.id} value={acc.id}>
                                      {acc.name} ({acc.platform})
                                    </option>
                                  ))}
                              </select>
                            </div>

                            <div>
                              <label className="text-[10px] text-zinc-400">Kategori Peran (Stance Komentar)</label>
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
                                className="w-full mt-1 px-2.5 py-1.5 rounded border border-zinc-800 bg-zinc-900 text-zinc-200 text-xs focus:outline-none focus:border-emerald-500 font-medium"
                              >
                                {ROLE_OPTIONS.map((r) => (
                                  <option key={r.value} value={r.value}>
                                    {r.label} — {r.desc}
                                  </option>
                                ))}
                              </select>
                            </div>
                          </div>

                          <div>
                            <div className="flex items-center justify-between text-[10px] text-zinc-400">
                              <span>Instruksi Persona AI (Skena Jaksel):</span>
                              <span className="text-zinc-500 italic">Otomatis diisi sesuai peran (opsional jika ingin diedit)</span>
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
                              placeholder="Gaya bahasa persona..."
                              className="w-full mt-1 px-2.5 py-1.5 rounded border border-zinc-800 bg-zinc-900 text-zinc-200 text-xs focus:outline-none focus:border-emerald-500 font-mono"
                            />
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between border-t border-zinc-800/80 px-6 py-4 shrink-0 bg-zinc-950/40">
              <button
                type="button"
                onClick={handlePreviewAI}
                className="flex items-center gap-2 px-3.5 py-2 rounded-lg border border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 text-xs font-medium transition-colors"
              >
                <Sparkles className="h-4 w-4 text-cyan-400" />
                Preview Variasi Komentar AI
              </button>

              <div className="flex items-center gap-2.5">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="px-4 py-2 rounded-lg border border-zinc-800 bg-transparent hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 text-xs font-medium transition-colors"
                >
                  Batal
                </button>
                <button
                  type="button"
                  onClick={handleSaveRule}
                  className="px-5 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-zinc-950 text-xs font-semibold transition-colors"
                >
                  Simpan Aturan
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal: AI Preview Comments */}
      {previewModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg rounded-2xl border border-zinc-800 bg-[#0d0d11] p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-cyan-400" />
                <h3 className="text-sm font-semibold text-zinc-100">
                  Preview Variasi Komentar Berbeda
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
                <span>Menghasilkan komentar AI dengan sudut pandang unik...</span>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-xs text-zinc-400">
                  Contoh respons yang dihasilkan model untuk video sampel:
                </p>
                {previewResults.map((p, idx) => {
                  const roleObj =
                    ROLE_OPTIONS.find((r) => r.value === (p.roleCategory || "pro")) ||
                    ROLE_OPTIONS[0];
                  return (
                    <div
                      key={idx}
                      className="p-3 rounded-lg border border-zinc-800/80 bg-zinc-950/60 space-y-1.5 text-xs"
                    >
                      <div className="flex items-center justify-between text-zinc-400">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-zinc-200">
                            {p.accountName || p.accountId}
                          </span>
                          <span
                            className={`px-1.5 py-0.5 rounded border text-[10px] font-mono ${roleObj.badgeColor}`}
                          >
                            {roleObj.label}
                          </span>
                        </div>
                        <span className="text-[10px] text-zinc-500 truncate max-w-xs">
                          {p.persona}
                        </span>
                      </div>
                      <p className="text-emerald-300 font-medium italic bg-zinc-900/50 p-2.5 rounded border border-zinc-800/50">
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
                className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs font-semibold text-zinc-200"
              >
                Tutup
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
