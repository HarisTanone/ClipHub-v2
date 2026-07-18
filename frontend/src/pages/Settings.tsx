import { useState, useEffect } from "react";
import { Save, Server, Cpu, Sparkles, Film, UserPlus, Trash2, AlertTriangle, Shield, Zap } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { RangeSlider } from "@/components/ui/RangeSlider";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { system, storage, API_BASE, getToken } from "@/lib/api";
import { cn } from "@/lib/utils";
import { SectionDescription } from "@/components/reframe/SectionDescription";
import { ImagePreviewPanel } from "@/components/reframe/ImagePreviewPanel";
import { REFRAME_SLIDER_META, REFRAME_SECTION_DESCRIPTIONS } from "@/components/reframe/ReframeSliderMeta";

// ─── API helpers ─────────────────────────────────────────────────────────────

async function fetchSettings(): Promise<any> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/settings`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) return null;
  return (await res.json()).data;
}

async function saveSettings(payload: any): Promise<boolean> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/settings`, { method: "PUT", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify(payload) });
  return res.ok;
}

async function fetchUsers(): Promise<any[]> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/auth/users`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) return [];
  const data = await res.json();
  return data.data || data.users || [];
}

async function createUserApi(payload: any): Promise<boolean> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/auth/users`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify(payload) });
  return res.ok;
}

async function deleteUserApi(id: number): Promise<boolean> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/auth/users/${id}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
  return res.ok;
}

const PREMIUM_FEATURES = [
  { code: "dual_subtitle", name: "Dual Font Style" },
  { code: "auto_grid", name: "Auto Grid" },
  { code: "threejs_effects", name: "Three.js Effects" },
  { code: "ai_layer", name: "AI Layer" },
];

async function getUserFeatures(userId: number): Promise<string[]> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/features/user/${userId}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) return [];
  const data = await res.json();
  return (data.data || []).map((f: any) => f.code);
}

async function grantFeatureApi(userId: number, featureCode: string): Promise<boolean> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/features/grant`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ user_id: userId, feature_code: featureCode }) });
  return res.ok;
}

async function revokeFeatureApi(userId: number, featureCode: string): Promise<boolean> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/features/revoke`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ user_id: userId, feature_code: featureCode }) });
  return res.ok;
}

// ─── Reframe Tuning API ───────────────────────────────────────────────────────

interface ReframeTuning {
  sample_interval_sec: number;
  max_samples: number;
  face_confidence: number;
  min_face_size_ratio: number;
  max_face_size_ratio: number;
  min_separation_ratio: number;
  min_coexist_ratio: number;
  dominance_single_crop: number;
  grid_base_zoom: number;
  grid_max_zoom: number;
  grid_face_margin: number;
  grid_enter_samples: number;
  grid_exit_samples: number;
  min_grid_segment_seconds: number;
  min_face_area_px: number;
  min_area_ratio_to_max: number;
  min_frame_ratio: number;
  ghost_iou_threshold: number;
  ghost_center_dist_ratio: number;
  ghost_center_dist_broad: number;
  min_pair_size_ratio: number;
}

const REFRAME_TUNING_DEFAULTS: ReframeTuning = {
  sample_interval_sec: 0.333, max_samples: 720, face_confidence: 0.55,
  min_face_size_ratio: 0.10, max_face_size_ratio: 0.50,
  min_separation_ratio: 0.05, min_coexist_ratio: 0.40,
  dominance_single_crop: 0.75, grid_base_zoom: 1.08, grid_max_zoom: 3.50,
  grid_face_margin: 0.35, grid_enter_samples: 4, grid_exit_samples: 2,
  min_grid_segment_seconds: 1.20,
  min_face_area_px: 4000, min_area_ratio_to_max: 0.25, min_frame_ratio: 0.15,
  ghost_iou_threshold: 0.25, ghost_center_dist_ratio: 0.08,
  ghost_center_dist_broad: 0.20, min_pair_size_ratio: 0.18,
};

// Integer-valued reframe fields (must not be persisted as floats).
const REFRAME_INT_KEYS: (keyof ReframeTuning)[] = [
  "max_samples", "grid_enter_samples", "grid_exit_samples", "min_face_area_px",
];

// Normalize a raw config object coming from the API into a fully-typed
// ReframeTuning, coercing numeric types and filling any missing keys from
// defaults. This guarantees the local state matches what is persisted so
// save → refresh round-trips are stable and equality checks are reliable.
function normalizeReframeTuning(raw: Partial<ReframeTuning> | null | undefined): ReframeTuning {
  const out = { ...REFRAME_TUNING_DEFAULTS } as ReframeTuning;
  if (!raw) return out;
  (Object.keys(REFRAME_TUNING_DEFAULTS) as (keyof ReframeTuning)[]).forEach((key) => {
    const val = raw[key];
    if (val === undefined || val === null) return;
    const num = typeof val === "number" ? val : parseFloat(String(val));
    if (Number.isNaN(num)) return;
    out[key] = REFRAME_INT_KEYS.includes(key) ? Math.round(num) : num;
  });
  return out;
}

// Deep-ish equality for two reframe configs (numeric comparison with epsilon
// to avoid float noise from DB round-trips).
function reframeTuningEquals(a: ReframeTuning, b: ReframeTuning): boolean {
  return (Object.keys(REFRAME_TUNING_DEFAULTS) as (keyof ReframeTuning)[]).every((key) => {
    return Math.abs((a[key] as number) - (b[key] as number)) < 1e-6;
  });
}

async function fetchReframeTuning(): Promise<ReframeTuning | null> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/settings/reframe-tuning`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) return null;
  const data = await res.json();
  return data.data || null;
}


async function saveReframeTuning(payload: ReframeTuning): Promise<boolean> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/settings/reframe-tuning`, { method: "PUT", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify(payload) });
  return res.ok;
}

async function resetReframeTuning(): Promise<ReframeTuning | null> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/settings/reframe-tuning/reset`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) return null;
  const data = await res.json();
  return data.data || null;
}

// ─── Main ────────────────────────────────────────────────────────────────────

export function Settings() {
  const toast = useToast();
  const { user } = useAuth();
  const isSuperadmin = user?.is_superadmin || false;
  const [tab, setTab] = useState<"general" | "render" | "users" | "reframe">("general");
  const [health, setHealth] = useState<any>(null);
  const [isSaving, setIsSaving] = useState(false);

  const [settings, setSettings] = useState({
    default_aspect_ratio: "9:16",
    whisper_model_size: "medium",
    use_remotion: true,
    remotion_ai_layer: true,
    remotion_quality: "medium",
    pipeline_mode: "v1" as "v1" | "v2",
  });

  // Users
  const [users, setUsers] = useState<any[]>([]);
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newName, setNewName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  // Clear storage
  const [isClearing, setIsClearing] = useState(false);

  // Reframe tuning
  const [reframeTuning, setReframeTuning] = useState<ReframeTuning>(REFRAME_TUNING_DEFAULTS);
  // Snapshot of the last PERSISTED value (loaded from server or last successful save).
  // Used by Reset to revert unsaved edits back to what is actually stored.
  const [reframeBaseline, setReframeBaseline] = useState<ReframeTuning>(REFRAME_TUNING_DEFAULTS);
  const [isSavingReframe, setIsSavingReframe] = useState(false);
  const [isResettingReframe, setIsResettingReframe] = useState(false);
  const [aspectRatio, setAspectRatio] = useState<"9:16" | "16:9" | "1:1">("9:16");

  useEffect(() => {
    system.health().then(setHealth).catch(() => null);
    fetchSettings().then((d) => { if (d) setSettings((p) => ({ ...p, ...d })); });
    fetchUsers().then(setUsers);
    fetchReframeTuning().then((d) => {
      if (d) {
        const normalized = normalizeReframeTuning(d);
        setReframeTuning(normalized);
        setReframeBaseline(normalized);
      }
    });
  }, []);

  // Whether there are unsaved changes relative to the last persisted snapshot.
  const reframeDirty = !reframeTuningEquals(reframeTuning, reframeBaseline);


  function handleChange(key: string, value: any) { setSettings((p) => ({ ...p, [key]: value })); }

  async function handleSave() {
    setIsSaving(true);
    const ok = await saveSettings(settings);
    toast[ok ? "success" : "error"](ok ? "Settings saved" : "Failed to save");
    setIsSaving(false);
  }

  async function handleCreateUser() {
    if (!newEmail || !newPassword) { toast.error("Email and password required"); return; }
    const ok = await createUserApi({ email: newEmail, password: newPassword, full_name: newName });
    if (ok) { toast.success("User created"); setShowCreateUser(false); setNewEmail(""); setNewName(""); setNewPassword(""); fetchUsers().then(setUsers); }
    else toast.error("Failed to create user");
  }

  async function handleDeleteUser(id: number, email: string) {
    if (!confirm(`Deactivate ${email}?`)) return;
    const ok = await deleteUserApi(id);
    if (ok) { toast.success("User deactivated"); fetchUsers().then(setUsers); }
    else toast.error("Failed");
  }

  async function handleClearStorage() {
    if (!confirm("This will delete ALL job records, output files, and downloads.\n\nPresets and user accounts will be preserved.\n\nContinue?")) return;
    setIsClearing(true);
    try {
      const res = await storage.clearProcessingData();
      toast.success(res.message || "Storage cleared");
    } catch (e: any) {
      toast.error(e.message || "Failed to clear storage");
    } finally {
      setIsClearing(false);
    }
  }

  function handleReframeChange(key: keyof ReframeTuning, value: number) {
    setReframeTuning((p) => ({ ...p, [key]: value }));
  }

  async function handleSaveReframe() {
    setIsSavingReframe(true);
    // Normalize before persisting so what we save == what we snapshot as baseline.
    const payload = normalizeReframeTuning(reframeTuning);
    const ok = await saveReframeTuning(payload);
    if (ok) {
      // Persisted successfully: this normalized payload is now the new baseline.
      setReframeTuning(payload);
      setReframeBaseline(payload);
      toast.success("Reframe tuning saved");
    } else {
      toast.error("Failed to save");
    }
    setIsSavingReframe(false);
  }

  // "Reset" reverts any unsaved edits back to the last persisted snapshot
  // (i.e. the state as it was before the current round of editing / before save).
  function handleResetReframe() {
    if (!reframeDirty) return;
    setReframeTuning(reframeBaseline);
    toast.success("Reverted unsaved changes");
  }

  // "Restore defaults" pulls the factory defaults from the backend and applies
  // them locally (still requires an explicit Save to persist).
  async function handleRestoreReframeDefaults() {
    if (!confirm("Restore all reframe tuning to factory defaults? This will be applied after you Save.")) return;
    setIsResettingReframe(true);
    const data = await resetReframeTuning();
    if (data) {
      const normalized = normalizeReframeTuning(data);
      setReframeTuning(normalized);
      setReframeBaseline(normalized);
      toast.success("Reframe tuning restored to defaults");
    } else {
      toast.error("Failed to restore defaults");
    }
    setIsResettingReframe(false);
  }


  const tabs = [
    { id: "general" as const, label: "General" },
    { id: "reframe" as const, label: "Reframe Tuning" },
    ...(isSuperadmin ? [{ id: "render" as const, label: "Render Engine" }] : []),
    ...(isSuperadmin ? [{ id: "users" as const, label: "Users" }] : []),
  ];

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0 mb-4">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold text-zinc-100">Settings</h1>
          <div className="flex bg-zinc-800/80 rounded-lg p-0.5">
            {tabs.map((t) => (
              <button key={t.id} type="button" onClick={() => setTab(t.id)}
                className={cn("px-3 py-1.5 text-xs font-medium rounded-md transition-colors", tab === t.id ? "bg-zinc-700 text-zinc-100" : "text-zinc-500 hover:text-zinc-300")}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
        {tab === "users" ? null : tab === "reframe" ? (
          <div className="flex items-center gap-2">
            {reframeDirty && <span className="text-[10px] text-amber-400 font-medium mr-1">Unsaved changes</span>}
            <Button onClick={handleRestoreReframeDefaults} loading={isResettingReframe} size="sm" variant="outline">Restore Defaults</Button>
            <Button onClick={handleResetReframe} disabled={!reframeDirty} size="sm" variant="outline">Reset</Button>
            <Button onClick={handleSaveReframe} disabled={!reframeDirty} loading={isSavingReframe} icon={<Save className="h-3.5 w-3.5" />} size="sm">Save</Button>
          </div>
        ) : (

          <Button onClick={handleSave} loading={isSaving} icon={<Save className="h-3.5 w-3.5" />} size="sm">Save</Button>
        )}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {tab === "general" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 max-w-4xl">
            {health && (
              <Card className="p-3">
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-lg bg-emerald-500/10 flex items-center justify-center"><Server className="h-4 w-4 text-emerald-400" /></div>
                  <div><p className="text-sm text-zinc-200 font-medium">Backend Connected</p><p className="text-[11px] text-zinc-500">v{health.version} — {health.mode}</p></div>
                  <span className="ml-auto h-2 w-2 rounded-full bg-emerald-500" />
                </div>
              </Card>
            )}

            <Card className="p-4">
              <h3 className="text-xs font-semibold text-zinc-200 mb-3">Default Aspect Ratio</h3>
              <Select value={settings.default_aspect_ratio} onChange={(e) => handleChange("default_aspect_ratio", e.target.value)}
                options={[{ value: "9:16", label: "9:16 (Portrait)" }, { value: "16:9", label: "16:9 (Landscape)" }, { value: "1:1", label: "1:1 (Square)" }]} />
            </Card>

            <Card className="p-4">
              <div className="flex items-center gap-1.5 mb-3"><Cpu className="h-3.5 w-3.5 text-zinc-500" /><h3 className="text-xs font-semibold text-zinc-200">Whisper Model</h3></div>
              {isSuperadmin ? (
                <>
                  <Select value={settings.whisper_model_size} onChange={(e) => handleChange("whisper_model_size", e.target.value)}
                    options={[{ value: "tiny", label: "Tiny (fastest)" }, { value: "base", label: "Base" }, { value: "small", label: "Small" }, { value: "medium", label: "Medium (recommended)" }, { value: "large-v3", label: "Large v3 (best)" }]} />
                  <p className="text-[10px] text-zinc-600 mt-2">Larger = more accurate timestamps, slower.</p>
                </>
              ) : (
                <p className="text-[11px] text-zinc-500">Model: <span className="text-zinc-300 font-medium">{settings.whisper_model_size}</span></p>
              )}
            </Card>

            <Card className="p-4">
              <h3 className="text-xs font-semibold text-zinc-200 mb-3">How It Works</h3>
              <div className="space-y-1.5 text-[11px] text-zinc-500">
                <p>1. Paste YouTube URL → AI picks best clips</p>
                <p>2. Whisper generates word timestamps</p>
                <p>3. Remotion renders with your custom style</p>
                <p>4. Download final clips</p>
              </div>
            </Card>

            {isSuperadmin && (
              <Card className="p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Zap className="h-3.5 w-3.5 text-amber-400" />
                  <h3 className="text-xs font-semibold text-zinc-200">Pipeline Mode</h3>
                </div>
                <p className="text-[11px] text-zinc-500 mb-3">Switch AI engine untuk processing video Anda sendiri.</p>
                <div className="flex gap-2">
                  <button type="button"
                    onClick={() => handleChange("pipeline_mode", "v1")}
                    className={cn("flex-1 px-3 py-2 rounded-lg border text-xs font-medium transition-all",
                      settings.pipeline_mode === "v1"
                        ? "border-emerald-500 bg-emerald-500/10 text-emerald-400"
                        : "border-zinc-700 text-zinc-500 hover:border-zinc-600")}>
                    <span className="block text-[10px] opacity-70">Premium</span>
                    V1 — Gemini
                  </button>
                  <button type="button"
                    onClick={() => handleChange("pipeline_mode", "v2")}
                    className={cn("flex-1 px-3 py-2 rounded-lg border text-xs font-medium transition-all",
                      settings.pipeline_mode === "v2"
                        ? "border-blue-500 bg-blue-500/10 text-blue-400"
                        : "border-zinc-700 text-zinc-500 hover:border-zinc-600")}>
                    <span className="block text-[10px] opacity-70">Free</span>
                    V2 — 9router
                  </button>
                </div>
              </Card>
            )}

            {isSuperadmin && (
              <Card className="p-4 border-red-500/20">
                <div className="flex items-center gap-2 mb-3">
                  <AlertTriangle className="h-3.5 w-3.5 text-red-400" />
                  <h3 className="text-xs font-semibold text-zinc-200">Clear Storage</h3>
                </div>
                <p className="text-[11px] text-zinc-500 mb-3">Delete all job records, output videos, and downloaded files. Presets and user accounts will be preserved.</p>
                <Button type="button" size="sm" onClick={handleClearStorage} loading={isClearing} className="bg-red-600 hover:bg-red-700 border-red-700" icon={<Trash2 className="h-3.5 w-3.5" />}>
                  Clear All Processing Data
                </Button>
              </Card>
            )}

          </div>
        )}

        {tab === "render" && (
          <div className="max-w-2xl space-y-4">
            <Card className="p-4">
              <div className="flex items-center gap-1.5 mb-3"><Sparkles className="h-3.5 w-3.5 text-zinc-500" /><h3 className="text-xs font-semibold text-zinc-200">Render Engine</h3></div>
              <div className="space-y-3">
                <FeatureToggle icon={<Film className="h-3.5 w-3.5" />} label="Use Remotion" desc="React-based rendering" active={settings.use_remotion} onToggle={() => handleChange("use_remotion", !settings.use_remotion)} />
                {settings.use_remotion && (
                  <>
                    <FeatureToggle icon={<Sparkles className="h-3.5 w-3.5" />} label="AI Layer" desc="Auto VFX from transcript" active={settings.remotion_ai_layer} onToggle={() => handleChange("remotion_ai_layer", !settings.remotion_ai_layer)} />
                    <Select label="Quality" value={settings.remotion_quality} onChange={(e) => handleChange("remotion_quality", e.target.value)}
                      options={[{ value: "low", label: "Low (CRF 28)" }, { value: "medium", label: "Medium (CRF 18)" }, { value: "high", label: "High (CRF 12)" }]} />
                  </>
                )}
              </div>
            </Card>
          </div>
        )}

        {tab === "reframe" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* LEFT: Config sliders (col-4) */}
            <div className="lg:col-span-4 space-y-4 order-2 lg:order-1">
              {/* Sampling & Detection */}
              <Card className="p-4">
                <h3 className="text-xs font-semibold text-zinc-200 mb-3 flex items-center gap-1.5"><Cpu className="h-3.5 w-3.5 text-zinc-500" />Sampling &amp; Detection</h3>
                <SectionDescription
                  pipelineStage={REFRAME_SECTION_DESCRIPTIONS.samplingDetection.pipelineStage}
                  description={REFRAME_SECTION_DESCRIPTIONS.samplingDetection.description}
                />
                <div className="space-y-3 mt-3">
                  <RangeSlider label="Sample Interval (sec)" value={reframeTuning.sample_interval_sec} min={0.1} max={1.0} step={0.01} onChange={(v) => handleReframeChange("sample_interval_sec", v)} description={REFRAME_SLIDER_META.sample_interval_sec.description} tooltip={REFRAME_SLIDER_META.sample_interval_sec.tooltip} />
                  <RangeSlider label="Max Samples" value={reframeTuning.max_samples} min={60} max={1440} step={10} onChange={(v) => handleReframeChange("max_samples", v)} description={REFRAME_SLIDER_META.max_samples.description} tooltip={REFRAME_SLIDER_META.max_samples.tooltip} />
                  <RangeSlider label="Face Confidence" value={reframeTuning.face_confidence} min={0.1} max={0.9} step={0.01} onChange={(v) => handleReframeChange("face_confidence", v)} description={REFRAME_SLIDER_META.face_confidence.description} tooltip={REFRAME_SLIDER_META.face_confidence.tooltip} />
                  <RangeSlider label="Min Face Size Ratio" value={reframeTuning.min_face_size_ratio} min={0.02} max={0.30} step={0.01} onChange={(v) => handleReframeChange("min_face_size_ratio", v)} description={REFRAME_SLIDER_META.min_face_size_ratio.description} tooltip={REFRAME_SLIDER_META.min_face_size_ratio.tooltip} />
                  <RangeSlider label="Max Face Size Ratio" value={reframeTuning.max_face_size_ratio} min={0.20} max={0.80} step={0.01} onChange={(v) => handleReframeChange("max_face_size_ratio", v)} description={REFRAME_SLIDER_META.max_face_size_ratio.description} tooltip={REFRAME_SLIDER_META.max_face_size_ratio.tooltip} />
                  <RangeSlider label="Min Separation Ratio (two-person threshold)" value={reframeTuning.min_separation_ratio} min={0.05} max={0.50} step={0.01} onChange={(v) => handleReframeChange("min_separation_ratio", v)} description={REFRAME_SLIDER_META.min_separation_ratio.description} tooltip={REFRAME_SLIDER_META.min_separation_ratio.tooltip} />
                  <RangeSlider label="Min Coexist Ratio (both faces simultaneous)" value={reframeTuning.min_coexist_ratio} min={0.10} max={0.80} step={0.01} onChange={(v) => handleReframeChange("min_coexist_ratio", v)} description={REFRAME_SLIDER_META.min_coexist_ratio.description} tooltip={REFRAME_SLIDER_META.min_coexist_ratio.tooltip} />
                </div>
              </Card>

              {/* Auto Grid */}
              <Card className="p-4">
                <h3 className="text-xs font-semibold text-zinc-200 mb-3 flex items-center gap-1.5"><Film className="h-3.5 w-3.5 text-zinc-500" />Auto Grid</h3>
                <SectionDescription
                  pipelineStage={REFRAME_SECTION_DESCRIPTIONS.autoGrid.pipelineStage}
                  description={REFRAME_SECTION_DESCRIPTIONS.autoGrid.description}
                />
                <div className="space-y-3 mt-3">
                  <RangeSlider label="Dominance Single Crop (switch to single above this)" value={reframeTuning.dominance_single_crop} min={0.50} max={0.95} step={0.01} onChange={(v) => handleReframeChange("dominance_single_crop", v)} description={REFRAME_SLIDER_META.dominance_single_crop.description} tooltip={REFRAME_SLIDER_META.dominance_single_crop.tooltip} />
                  <RangeSlider label="Grid Base Zoom" value={reframeTuning.grid_base_zoom} min={1.0} max={1.5} step={0.01} onChange={(v) => handleReframeChange("grid_base_zoom", v)} description={REFRAME_SLIDER_META.grid_base_zoom.description} tooltip={REFRAME_SLIDER_META.grid_base_zoom.tooltip} />
                  <RangeSlider label="Grid Max Zoom (2-person separation)" value={reframeTuning.grid_max_zoom} min={1.2} max={3.0} step={0.01} onChange={(v) => handleReframeChange("grid_max_zoom", v)} description={REFRAME_SLIDER_META.grid_max_zoom.description} tooltip={REFRAME_SLIDER_META.grid_max_zoom.tooltip} />
                  <RangeSlider label="Grid Face Margin (breathing room)" value={reframeTuning.grid_face_margin} min={0.10} max={0.60} step={0.01} onChange={(v) => handleReframeChange("grid_face_margin", v)} description={REFRAME_SLIDER_META.grid_face_margin.description} tooltip={REFRAME_SLIDER_META.grid_face_margin.tooltip} />
                  <RangeSlider label="Grid Enter Samples (confirm 2nd person)" value={reframeTuning.grid_enter_samples} min={1} max={10} step={1} onChange={(v) => handleReframeChange("grid_enter_samples", v)} description={REFRAME_SLIDER_META.grid_enter_samples.description} tooltip={REFRAME_SLIDER_META.grid_enter_samples.tooltip} />
                  <RangeSlider label="Grid Exit Samples (close when 1 leaves)" value={reframeTuning.grid_exit_samples} min={1} max={6} step={1} onChange={(v) => handleReframeChange("grid_exit_samples", v)} description={REFRAME_SLIDER_META.grid_exit_samples.description} tooltip={REFRAME_SLIDER_META.grid_exit_samples.tooltip} />
                  <RangeSlider label="Min Grid Segment (sec, anti-flicker)" value={reframeTuning.min_grid_segment_seconds} min={0.5} max={3.0} step={0.1} onChange={(v) => handleReframeChange("min_grid_segment_seconds", v)} description={REFRAME_SLIDER_META.min_grid_segment_seconds.description} tooltip={REFRAME_SLIDER_META.min_grid_segment_seconds.tooltip} />
                </div>
              </Card>

              {/* Ghost Detection */}
              <Card className="p-4">
                <h3 className="text-xs font-semibold text-zinc-200 mb-3 flex items-center gap-1.5"><AlertTriangle className="h-3.5 w-3.5 text-zinc-500" />Ghost Detection</h3>
                <SectionDescription
                  pipelineStage={REFRAME_SECTION_DESCRIPTIONS.ghostDetection.pipelineStage}
                  description={REFRAME_SECTION_DESCRIPTIONS.ghostDetection.description}
                />
                <div className="space-y-3 mt-3">
                  <RangeSlider label="Min Face Area (px)" value={reframeTuning.min_face_area_px} min={500} max={15000} step={100} onChange={(v) => handleReframeChange("min_face_area_px", v)} description={REFRAME_SLIDER_META.min_face_area_px.description} tooltip={REFRAME_SLIDER_META.min_face_area_px.tooltip} />
                  <RangeSlider label="Min Area Ratio to Max" value={reframeTuning.min_area_ratio_to_max} min={0.05} max={0.60} step={0.01} onChange={(v) => handleReframeChange("min_area_ratio_to_max", v)} description={REFRAME_SLIDER_META.min_area_ratio_to_max.description} tooltip={REFRAME_SLIDER_META.min_area_ratio_to_max.tooltip} />
                  <RangeSlider label="Min Frame Ratio (track persistence)" value={reframeTuning.min_frame_ratio} min={0.05} max={0.50} step={0.01} onChange={(v) => handleReframeChange("min_frame_ratio", v)} description={REFRAME_SLIDER_META.min_frame_ratio.description} tooltip={REFRAME_SLIDER_META.min_frame_ratio.tooltip} />
                  <RangeSlider label="Ghost IoU Threshold (duplicate overlap)" value={reframeTuning.ghost_iou_threshold} min={0.10} max={0.60} step={0.01} onChange={(v) => handleReframeChange("ghost_iou_threshold", v)} description={REFRAME_SLIDER_META.ghost_iou_threshold.description} tooltip={REFRAME_SLIDER_META.ghost_iou_threshold.tooltip} />
                  <RangeSlider label="Ghost Center Dist Ratio" value={reframeTuning.ghost_center_dist_ratio} min={0.02} max={0.30} step={0.01} onChange={(v) => handleReframeChange("ghost_center_dist_ratio", v)} description={REFRAME_SLIDER_META.ghost_center_dist_ratio.description} tooltip={REFRAME_SLIDER_META.ghost_center_dist_ratio.tooltip} />
                  <RangeSlider label="Ghost Center Dist Broad" value={reframeTuning.ghost_center_dist_broad} min={0.05} max={0.50} step={0.01} onChange={(v) => handleReframeChange("ghost_center_dist_broad", v)} description={REFRAME_SLIDER_META.ghost_center_dist_broad.description} tooltip={REFRAME_SLIDER_META.ghost_center_dist_broad.tooltip} />
                  <RangeSlider label="Min Pair Size Ratio (big+small face pairing)" value={reframeTuning.min_pair_size_ratio} min={0.05} max={0.50} step={0.01} onChange={(v) => handleReframeChange("min_pair_size_ratio", v)} description={REFRAME_SLIDER_META.min_pair_size_ratio.description} tooltip={REFRAME_SLIDER_META.min_pair_size_ratio.tooltip} />
                </div>
              </Card>

            </div>
            {/* RIGHT: Preview panel (col-8) */}
            <div className="lg:col-span-8 order-1 lg:order-2">
              <ImagePreviewPanel
                reframeTuning={reframeTuning}
                aspectRatio={aspectRatio}
                onAspectRatioChange={setAspectRatio}
              />
            </div>
          </div>
        )}

        {tab === "users" && (
          <div className="max-w-3xl space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-xs text-zinc-500">{users.length} users</p>
              <Button size="sm" onClick={() => setShowCreateUser(!showCreateUser)} icon={showCreateUser ? undefined : <UserPlus className="h-3.5 w-3.5" />}>
                {showCreateUser ? "Cancel" : "Add User"}
              </Button>
            </div>

            {showCreateUser && (
              <Card className="p-4">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <Input label="Email" type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} placeholder="user@email.com" />
                  <Input label="Name" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Full Name" />
                  <Input label="Password" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="min 6 chars" />
                </div>
                <Button size="sm" className="mt-3" onClick={handleCreateUser} icon={<Save className="h-3 w-3" />}>Create</Button>
              </Card>
            )}

            <Card className="p-0">
              <div className="divide-y divide-zinc-800/30">
                {users.map((u) => (
                  <UserRow key={u.id} user={u} isSuperadmin={isSuperadmin} onDelete={handleDeleteUser} toast={toast} />
                ))}
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}

function UserRow({ user: u, isSuperadmin, onDelete, toast }: { user: any; isSuperadmin: boolean; onDelete: (id: number, email: string) => void; toast: any }) {
  const [expanded, setExpanded] = useState(false);
  const [isPremium, setIsPremium] = useState(false);
  const [loading, setLoading] = useState(false);

  async function togglePremium() {
    setLoading(true);
    const newValue = !isPremium;
    const token = getToken();
    const res = await fetch(`${API_BASE}/api/features/set-premium`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ user_id: u.id, is_premium: newValue }),
    });
    if (res.ok) {
      setIsPremium(newValue);
      toast.success(`${u.email} → ${newValue ? "Premium (V1 Gemini)" : "Free (V2 9router)"}`);
    } else {
      toast.error("Failed to update premium status");
    }
    setLoading(false);
  }

  function handleExpand() {
    if (!expanded) {
      // Fetch current premium status
      const token = getToken();
      fetch(`${API_BASE}/api/features/user/${u.id}`, { headers: { Authorization: `Bearer ${token}` } })
        .then(r => r.json())
        .then(d => setIsPremium(d.data?.is_premium || false))
        .catch(() => { });
    }
    setExpanded(!expanded);
  }

  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-3">
        <div className="shrink-0 w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center">
          <span className="text-[11px] font-bold text-zinc-400">{(u.full_name || u.email)[0].toUpperCase()}</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm text-zinc-200 font-medium truncate">{u.full_name || u.email}</p>
            <Badge variant={u.role === "superadmin" ? "success" : "default"} size="sm">{u.role}</Badge>
          </div>
          <p className="text-[10px] text-zinc-500">{u.email}</p>
        </div>
        {u.role !== "superadmin" && isSuperadmin && (
          <button type="button" onClick={handleExpand} className={cn("p-1.5 rounded transition-colors", expanded ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-600 hover:text-emerald-400 hover:bg-zinc-800")}>
            <Shield className="h-3.5 w-3.5" />
          </button>
        )}
        {u.role !== "superadmin" && (
          <button type="button" onClick={() => onDelete(u.id, u.email)} className="p-1.5 rounded text-zinc-600 hover:text-red-400 hover:bg-zinc-800 transition-colors">
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      {expanded && u.role !== "superadmin" && (
        <div className="mt-2 ml-11 flex items-center gap-3">
          <button
            type="button"
            disabled={loading}
            onClick={togglePremium}
            className={cn(
              "px-3 py-1.5 rounded-lg border text-xs font-medium transition-all flex items-center gap-2",
              isPremium
                ? "border-amber-500 bg-amber-500/10 text-amber-400"
                : "border-zinc-700 text-zinc-500 hover:border-zinc-600"
            )}
          >
            <span className={cn("w-2 h-2 rounded-full", isPremium ? "bg-amber-400" : "bg-zinc-600")} />
            {isPremium ? "Premium (V1 Gemini)" : "Free (V2 9router)"}
          </button>
          {isPremium && (
            <span className="text-[10px] text-zinc-600">All features unlocked</span>
          )}
        </div>
      )}
    </div>
  );
}

function FeatureToggle({ icon, label, desc, active, onToggle }: { icon: React.ReactNode; label: string; desc?: string; active: boolean; onToggle: () => void }) {
  return (
    <button type="button" onClick={onToggle} className="w-full flex items-center justify-between rounded-lg border border-zinc-800/60 px-3 py-2.5 hover:border-zinc-700 transition-colors text-left">
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-zinc-400 shrink-0">{icon}</span>
        <div><span className="text-xs text-zinc-300 font-medium">{label}</span>{desc && <p className="text-[10px] text-zinc-600">{desc}</p>}</div>
      </div>
      <div className={cn("shrink-0 w-8 h-4 rounded-full relative transition-colors", active ? "bg-emerald-600" : "bg-zinc-700")}>
        <span className={cn("absolute top-0.5 left-0.5 h-3 w-3 rounded-full bg-white transition-transform", active && "translate-x-4")} />
      </div>
    </button>
  );
}
