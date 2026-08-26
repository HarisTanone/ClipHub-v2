import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  Save, Server, Cpu, Sparkles, Film, UserPlus, Trash2, AlertTriangle, Shield,
  Zap, Play, Terminal, RefreshCw, CheckCircle2, XCircle, BrainCircuit, Bot,
  Send, Key, Eye, EyeOff, Radio, Bell, Video, Copy, Check, MessageSquare, Palette,
  SlidersHorizontal, UserCheck, Layers, Lock, Activity, Globe, Info, HelpCircle, HardDrive, CheckSquare,
  Upload, FileText, ExternalLink, ShieldCheck, Clock
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { RangeSlider } from "@/components/ui/RangeSlider";
import { useToast } from "@/components/ui/Toast";
import { confirmDialog } from "@/components/ui/ConfirmDialog";
import { useAuth } from "@/hooks/useAuth";
import { system, storage, systemConfig, autopilotApi, presetsApi, socialApi, type AutopilotSettings, type AutopilotQuotaInfo, type SystemConfigItem, API_BASE, getToken } from "@/lib/api";
import { cn } from "@/lib/utils";
import { SectionDescription } from "@/components/reframe/SectionDescription";
import { ImagePreviewPanel } from "@/components/reframe/ImagePreviewPanel";
import { REFRAME_SLIDER_META, REFRAME_SECTION_DESCRIPTIONS } from "@/components/reframe/ReframeSliderMeta";
import { AutopilotPresetPreview } from "@/components/autopilot/AutopilotPresetPreview";
import {
  StyleEditorModal,
  DEFAULT_HOOK_STYLE,
  DEFAULT_SUBTITLE_STYLE,
  DEFAULT_TEXT_EMPHASIS_STYLE,
  DEFAULT_WATERMARK_STYLE,
  DEFAULT_CTA_STYLE,
  type HookStyle,
  type SubtitleStyle,
  type TextEmphasisStyle,
  type WatermarkStyle,
  type CtaStyle,
} from "@/components/StyleEditorModal";

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

// ─── Telegram Settings API ───────────────────────────────────────────────────

interface TelegramSettings {
  is_enabled: boolean;
  bot_token: string;
  bot_username: string;
  chat_id: string;
  group_id: string;
  channel_id: string;
  topic_id: string;
  allowed_users: string;
  notify_on_job_start: boolean;
  notify_on_job_complete: boolean;
  notify_on_job_failed: boolean;
  send_video_files: boolean;
  include_caption: boolean;
  include_hashtags: boolean;
  include_virality_score: boolean;
  notify_target: string;
  auto_post_social: boolean;
  auto_post_platforms: string;
  auto_post_schedule_mode: string;
  auto_post_interval_hours: number;
  auto_post_peak_hours: string;
}

const TELEGRAM_SETTINGS_DEFAULTS: TelegramSettings = {
  is_enabled: false,
  bot_token: "",
  bot_username: "",
  chat_id: "",
  group_id: "",
  channel_id: "",
  topic_id: "",
  allowed_users: "",
  notify_on_job_start: true,
  notify_on_job_complete: true,
  notify_on_job_failed: true,
  send_video_files: true,
  include_caption: true,
  include_hashtags: true,
  include_virality_score: true,
  notify_target: "all",
  auto_post_social: false,
  auto_post_platforms: "tiktok,instagram,youtube",
  auto_post_schedule_mode: "ai",
  auto_post_interval_hours: 4,
  auto_post_peak_hours: "11:30, 15:00, 18:30, 20:30",
};

async function fetchTelegramSettings(): Promise<TelegramSettings | null> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/telegram/settings`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data.data || null;
}

async function saveTelegramSettingsApi(payload: TelegramSettings): Promise<boolean> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/telegram/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  return res.ok;
}

async function testTelegramConnectionApi(bot_token?: string, target_id?: string): Promise<any> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/telegram/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ bot_token, target_id }),
  });
  return res.json();
}

async function testTelegramVideoApi(target_id?: string): Promise<any> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/telegram/test-video`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ target_id }),
  });
  return res.json();
}

async function fetchTelegramSocialAccounts(): Promise<any[]> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/telegram/social-accounts`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  const data = await res.json();
  return data.accounts || [];
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

// ─── Object Overlay (AI visual entities → photo card style) ──────────────────

interface ObjectOverlayConfig {
  enabled: boolean;
  max_per_clip: number;
  box_size_ratio: number;
  corner_radius: number;
  position: string;
  animation: string;
  duration_sec: number;
  margin_ratio: number;
  text_color: string;
  bg_color: string;
  border_color: string;
  font_scale: number;
  opacity: number;
  min_relevance: number;
  show_label: boolean;
}

const OBJECT_OVERLAY_DEFAULTS: ObjectOverlayConfig = {
  enabled: true,
  max_per_clip: 3,
  box_size_ratio: 0.28,
  corner_radius: 18,
  position: "auto",
  animation: "slide_right",
  duration_sec: 2.4,
  margin_ratio: 0.04,
  text_color: "255,255,255",
  bg_color: "20,20,24",
  border_color: "255,255,255",
  font_scale: 0.55,
  opacity: 0.95,
  min_relevance: 0.35,
  show_label: true,
};

function normalizeObjectOverlay(raw: Partial<ObjectOverlayConfig> | null | undefined): ObjectOverlayConfig {
  const out = { ...OBJECT_OVERLAY_DEFAULTS };
  if (!raw) return out;
  out.enabled = Boolean(raw.enabled ?? out.enabled);
  out.show_label = Boolean(raw.show_label ?? out.show_label);
  out.position = String(raw.position || out.position);
  out.animation = String(raw.animation || out.animation);
  out.text_color = String(raw.text_color || out.text_color);
  out.bg_color = String(raw.bg_color || out.bg_color);
  out.border_color = String(raw.border_color || out.border_color);
  for (const key of ["max_per_clip", "box_size_ratio", "corner_radius", "duration_sec", "margin_ratio", "font_scale", "opacity", "min_relevance"] as const) {
    const val = raw[key];
    if (val === undefined || val === null) continue;
    const num = typeof val === "number" ? val : parseFloat(String(val));
    if (Number.isNaN(num)) continue;
    (out as any)[key] = key === "max_per_clip" || key === "corner_radius" ? Math.round(num) : num;
  }
  return out;
}

function objectOverlayEquals(a: ObjectOverlayConfig, b: ObjectOverlayConfig): boolean {
  return (Object.keys(OBJECT_OVERLAY_DEFAULTS) as (keyof ObjectOverlayConfig)[]).every((key) => {
    const av = a[key];
    const bv = b[key];
    if (typeof av === "number" && typeof bv === "number") return Math.abs(av - bv) < 1e-6;
    return av === bv;
  });
}

async function fetchObjectOverlay(): Promise<ObjectOverlayConfig | null> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/settings/object-overlay`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) return null;
  const data = await res.json();
  return data.data || null;
}

async function saveObjectOverlay(payload: ObjectOverlayConfig): Promise<boolean> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/settings/object-overlay`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  return res.ok;
}

async function resetObjectOverlay(): Promise<ObjectOverlayConfig | null> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/settings/object-overlay/reset`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data.data || null;
}

export interface HyperFramesConfig {
  enabled: boolean;
  mode: "auto" | "manual";
  default_template: string;
  position: "safe_upper" | "top" | "floating_badge";
  server_url?: string;
  timeout_sec?: number;
}

const HYPERFRAMES_DEFAULTS: HyperFramesConfig = {
  enabled: true,
  mode: "auto",
  default_template: "hook_cyber_hud",
  position: "safe_upper",
};

async function fetchHyperFrames(): Promise<{ data: HyperFramesConfig; catalogue: any } | null> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/settings/hyperframes`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  return res.json();
}

async function saveHyperFrames(payload: Partial<HyperFramesConfig>): Promise<boolean> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/settings/hyperframes`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  return res.ok;
}

async function resetHyperFrames(): Promise<HyperFramesConfig | null> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/settings/hyperframes/reset`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data.data || null;
}

interface TestRunStatus {
  status: "idle" | "running" | "deploying" | "passed" | "failed";
  stage: string;
  message: string;
  updated_at?: string;
  video_available: boolean;
  video_version?: number;
  deploy_requested: boolean;
}

async function fetchTestRunStatus(): Promise<{ data: TestRunStatus; log: string } | null> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/settings/test-run/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  return res.json();
}

async function startTestRun(): Promise<TestRunStatus> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/settings/test-run`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || "Failed to start tests");
  return body.data;
}

async function fetchTestVideo(): Promise<Blob | null> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/settings/test-run/video`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.ok ? res.blob() : null;
}

// ─── Main ────────────────────────────────────────────────────────────────────

export function Settings() {
  const toast = useToast();
  const { user } = useAuth();
  const isSuperadmin = user?.is_superadmin || false;
  const [tab, setTab] = useState<"general" | "render" | "users" | "reframe" | "object" | "hyperframes" | "testing" | "models" | "telegram" | "autopilot" | "system_config">("general");
  const [health, setHealth] = useState<any>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Hermes Autopilot State
  const [autopilotSettings, setAutopilotSettings] = useState<AutopilotSettings | null>(null);
  const [autopilotQuota, setAutopilotQuota] = useState<AutopilotQuotaInfo | null>(null);
  const [autopilotCanRun, setAutopilotCanRun] = useState<boolean>(true);
  const [autopilotPresets, setAutopilotPresets] = useState<any[]>([]);
  const [autopilotPlatforms, setAutopilotPlatforms] = useState<any>({});
  const [autopilotHistory, setAutopilotHistory] = useState<any[]>([]);
  const [isLoadingAutopilot, setIsLoadingAutopilot] = useState<boolean>(false);
  const [isSavingAutopilot, setIsSavingAutopilot] = useState<boolean>(false);
  const [isRunningAutopilot, setIsRunningAutopilot] = useState<boolean>(false);
  const [showStyleModal, setShowStyleModal] = useState<boolean>(false);
  const [editorHook, setEditorHook] = useState<HookStyle>(DEFAULT_HOOK_STYLE);
  const [editorSub, setEditorSub] = useState<SubtitleStyle>(DEFAULT_SUBTITLE_STYLE);
  const [editorTe, setEditorTe] = useState<TextEmphasisStyle>(DEFAULT_TEXT_EMPHASIS_STYLE);
  const [editorWm, setEditorWm] = useState<WatermarkStyle>(DEFAULT_WATERMARK_STYLE);
  const [editorCta, setEditorCta] = useState<CtaStyle>(DEFAULT_CTA_STYLE);

  // Dynamic Database System Config
  const [sysConfigItems, setSysConfigItems] = useState<SystemConfigItem[]>([]);
  const [sysConfigEdits, setSysConfigEdits] = useState<Record<string, any>>({});
  const [sysConfigCategory, setSysConfigCategory] = useState<string>("all");
  const [sysConfigSearch, setSysConfigSearch] = useState<string>("");
  const [sysConfigUnmask, setSysConfigUnmask] = useState<boolean>(false);
  const [isLoadingSysConfig, setIsLoadingSysConfig] = useState<boolean>(false);
  const [isSavingSysConfig, setIsSavingSysConfig] = useState<boolean>(false);
  const [canEditSecrets, setCanEditSecrets] = useState<boolean>(false);

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
  // Object overlay style (entities from AI; knobs from DB)
  const [objectOverlay, setObjectOverlay] = useState<ObjectOverlayConfig>(OBJECT_OVERLAY_DEFAULTS);
  const [objectBaseline, setObjectBaseline] = useState<ObjectOverlayConfig>(OBJECT_OVERLAY_DEFAULTS);
  const [isSavingObject, setIsSavingObject] = useState(false);
  const [isResettingObject, setIsResettingObject] = useState(false);

  // HyperFrames Hook & Polish Config
  const [hfConfig, setHfConfig] = useState<HyperFramesConfig>(HYPERFRAMES_DEFAULTS);
  const [hfBaseline, setHfBaseline] = useState<HyperFramesConfig>(HYPERFRAMES_DEFAULTS);
  const [hfCatalogue, setHfCatalogue] = useState<any[]>([]);
  const [hfCataloguePage, setHfCataloguePage] = useState(1);
  const [isSavingHf, setIsSavingHf] = useState(false);
  const [isResettingHf, setIsResettingHf] = useState(false);

  const [testStatus, setTestStatus] = useState<TestRunStatus | null>(null);
  const [testLog, setTestLog] = useState("");
  const [isStartingTest, setIsStartingTest] = useState(false);
  const [testVideoUrl, setTestVideoUrl] = useState<string | null>(null);
  const [testRefreshKey, setTestRefreshKey] = useState(0);

  // Model settings (superadmin)
  const [modelSettings, setModelSettings] = useState<Array<{key: string; value: string; description: string; updated_at: string | null}>>([]);
  const [modelEdits, setModelEdits] = useState<Record<string, string>>({});
  const [isSavingModels, setIsSavingModels] = useState(false);
  const [modelTestResult, setModelTestResult] = useState<any>(null);
  const [isTestingModel, setIsTestingModel] = useState(false);
  const [availableModels, setAvailableModels] = useState<Array<{id: string; owned_by: string}>>([]);
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [testAllResults, setTestAllResults] = useState<any>(null);
  const [isTestingAll, setIsTestingAll] = useState(false);
  const [modelSearch, setModelSearch] = useState("");
  const [testingModelId, setTestingModelId] = useState<string | null>(null);

  // Telegram settings (superadmin)
  const [telegramSettings, setTelegramSettings] = useState<TelegramSettings>(TELEGRAM_SETTINGS_DEFAULTS);
  const [showBotToken, setShowBotToken] = useState(false);
  const [isSavingTelegram, setIsSavingTelegram] = useState(false);
  const [isTestingTelegram, setIsTestingTelegram] = useState(false);
  const [isTestingTelegramVideo, setIsTestingTelegramVideo] = useState(false);
  const [telegramTestResult, setTelegramTestResult] = useState<any>(null);
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null);
  const [telegramSocialAccounts, setTelegramSocialAccounts] = useState<any[]>([]);

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
    fetchObjectOverlay().then((d) => {
      if (d) {
        const normalized = normalizeObjectOverlay(d);
        setObjectOverlay(normalized);
        setObjectBaseline(normalized);
      }
    });
    fetchHyperFrames().then((res) => {
      if (res?.data) {
        setHfConfig(res.data);
        setHfBaseline(res.data);
      }
      if (res?.catalogue?.hook) {
        setHfCatalogue(res.catalogue.hook);
      }
    });
  }, []);

  useEffect(() => {
    if (!isSuperadmin || tab !== "testing") return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let currentVideoVersion: number | undefined;

    const refresh = async () => {
      const result = await fetchTestRunStatus();
      if (cancelled || !result) return;
      setTestStatus(result.data);
      setTestLog(result.log || "");

      if (result.data.video_available && result.data.video_version !== currentVideoVersion) {
        currentVideoVersion = result.data.video_version;
        const blob = await fetchTestVideo();
        if (!cancelled && blob) {
          const nextUrl = URL.createObjectURL(blob);
          setTestVideoUrl((previous) => {
            if (previous) URL.revokeObjectURL(previous);
            return nextUrl;
          });
        }
      }
      if (!cancelled && ["running", "deploying"].includes(result.data.status)) {
        timer = setTimeout(refresh, 2000);
      }
    };

    refresh();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [isSuperadmin, tab, testRefreshKey]);

  useEffect(() => () => {
    if (testVideoUrl) URL.revokeObjectURL(testVideoUrl);
  }, [testVideoUrl]);

  // Whether there are unsaved changes relative to the last persisted snapshot.
  const reframeDirty = !reframeTuningEquals(reframeTuning, reframeBaseline);
  const objectDirty = !objectOverlayEquals(objectOverlay, objectBaseline);


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
    if (!(await confirmDialog({ title: "Deactivate user?", message: `${email} will be deactivated and lose access to the dashboard.`, confirmText: "Deactivate", danger: true }))) return;
    const ok = await deleteUserApi(id);
    if (ok) { toast.success("User deactivated"); fetchUsers().then(setUsers); }
    else toast.error("Failed");
  }

  async function handleClearStorage() {
    if (!(await confirmDialog({
      title: "Clear all storage & processing data?",
      message: "This will delete ALL clipping jobs, video generator assets, output videos, downloaded footages, thumbnails, analysis caches, and all objects in the configured storage bucket.\n\nPresets, user accounts, and system settings will be preserved.\n\nThis action cannot be undone.",
      confirmText: "Yes, Clear Everything",
      danger: true,
    }))) return;
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
    if (!(await confirmDialog({ title: "Restore reframe tuning?", message: "All reframe tuning will be reset to factory defaults. This will be applied after you Save.", confirmText: "Restore" }))) return;
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

  function handleObjectChange(key: keyof ObjectOverlayConfig, value: any) {
    setObjectOverlay((p) => ({ ...p, [key]: value }));
  }

  async function handleSaveObject() {
    setIsSavingObject(true);
    const payload = normalizeObjectOverlay(objectOverlay);
    const ok = await saveObjectOverlay(payload);
    if (ok) {
      setObjectOverlay(payload);
      setObjectBaseline(payload);
      toast.success("Object overlay saved");
    } else {
      toast.error("Failed to save object overlay");
    }
    setIsSavingObject(false);
  }

  function handleResetObject() {
    if (!objectDirty) return;
    setObjectOverlay(objectBaseline);
    toast.success("Reverted unsaved changes");
  }

  async function handleRestoreObjectDefaults() {
    if (!(await confirmDialog({ title: "Restore object overlay style?", message: "The object overlay style will be reset to factory defaults.", confirmText: "Restore" }))) return;
    setIsResettingObject(true);
    const data = await resetObjectOverlay();
    if (data) {
      const normalized = normalizeObjectOverlay(data);
      setObjectOverlay(normalized);
      setObjectBaseline(normalized);
      toast.success("Object overlay restored to defaults");
    } else {
      toast.error("Failed to restore defaults");
    }
    setIsResettingObject(false);
  }

  const hfDirty = JSON.stringify(hfConfig) !== JSON.stringify(hfBaseline);

  function handleHfChange(key: keyof HyperFramesConfig, value: any) {
    setHfConfig((p) => ({ ...p, [key]: value }));
  }

  async function handleSaveHf() {
    setIsSavingHf(true);
    const ok = await saveHyperFrames(hfConfig);
    if (ok) {
      setHfBaseline(hfConfig);
      toast.success("HyperFrames settings saved");
    } else {
      toast.error("Failed to save HyperFrames settings");
    }
    setIsSavingHf(false);
  }

  function handleResetHf() {
    if (!hfDirty) return;
    setHfConfig(hfBaseline);
    toast.success("Reverted unsaved changes");
  }

  async function handleRestoreHfDefaults() {
    if (!(await confirmDialog({ title: "Restore HyperFrames settings?", message: "HyperFrames hook & polish settings will be reset to defaults.", confirmText: "Restore" }))) return;
    setIsResettingHf(true);
    const data = await resetHyperFrames();
    if (data) {
      setHfConfig(data);
      setHfBaseline(data);
      toast.success("HyperFrames restored to defaults");
    } else {
      toast.error("Failed to restore defaults");
    }
    setIsResettingHf(false);
  }

  async function handleStartTest() {
    if (!(await confirmDialog({ title: "Run server tests?", message: "All server tests will run now. Deployment will NOT run from this button.", confirmText: "Run Tests" }))) return;
    setIsStartingTest(true);
    try {
      const status = await startTestRun();
      setTestStatus(status);
      setTestLog("");
      setTestRefreshKey((value) => value + 1);
      toast.success("Server tests started");
    } catch (error: any) {
      toast.error(error.message || "Failed to start tests");
    } finally {
      setIsStartingTest(false);
    }
  }

  // ─── Model Settings handlers ───────────────────────────────────────────────

  const [isLoadingModelSettings, setIsLoadingModelSettings] = useState(false);

  async function fetchModelSettings() {
    try {
      setIsLoadingModelSettings(true);
      const token = getToken();
      const res = await fetch(`${API_BASE}/api/settings/models`, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) return;
      const data = await res.json();
      if (data.success) {
        setModelSettings(data.data || []);
        // Initialize edits from current values
        const edits: Record<string, string> = {};
        for (const s of (data.data || [])) edits[s.key] = s.value;
        setModelEdits(edits);
      }
    } catch (e) {
      console.warn("[Settings] fetchModelSettings failed:", e);
    } finally {
      setIsLoadingModelSettings(false);
    }
  }

  async function handleSaveModels() {
    setIsSavingModels(true);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/api/settings/models`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ settings: modelEdits }),
      });
      const data = await res.json();
      if (data.success) {
        toast.success(`${data.updated} model setting(s) updated`);
        fetchModelSettings();
      } else {
        toast.error(data.detail || "Failed to save");
      }
    } catch (e: any) {
      toast.error(e?.message || "Network error saving models");
    } finally {
      setIsSavingModels(false);
    }
  }

  async function handleTestModel(modelId?: string) {
    const model = modelId || modelEdits["NINE_ROUTER_MODEL"] || undefined;
    setIsTestingModel(true);
    setModelTestResult(null);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/api/settings/models/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          base_url: modelEdits["NINE_ROUTER_BASE_URL"] || undefined,
          api_key: modelEdits["NINE_ROUTER_API_KEY"] || undefined,
          model,
          prompt: "Reply with OK",
        }),
      });
      const data = await res.json();
      setModelTestResult(data);
      if (data.success) {
        toast.success(`Model "${model || "default"}" connected`);
      } else {
        toast.error(data.error || data.detail || `Model test failed`);
      }
    } catch (e: any) {
      setModelTestResult({ success: false, error: e?.message || "Network error", model });
      toast.error(e?.message || "Network error testing model");
    } finally {
      setIsTestingModel(false);
    }
  }

  async function handleFetchAvailableModels() {
    setIsLoadingModels(true);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/api/settings/models/available`, { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (data.success) {
        setAvailableModels(data.models || []);
        toast.success(`${data.models?.length || 0} model(s) found`);
      } else {
        toast.error(data.error || "Failed to fetch models");
      }
    } catch (e: any) {
      toast.error(e?.message || "Network error fetching models");
    } finally {
      setIsLoadingModels(false);
    }
  }

  async function handleTestAllModels() {
    setIsTestingAll(true);
    setTestAllResults(null);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/api/settings/models/test-all`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setTestAllResults(data);
      if (data.success) {
        toast.success(`${data.ok}/${data.total} model(s) active`);
      } else {
        toast.error(data.error || "Test failed");
      }
    } catch (e: any) {
      setTestAllResults({ success: false, error: e?.message || "Network error" });
      toast.error(e?.message || "Network error testing models");
    } finally {
      setIsTestingAll(false);
    }
  }

  async function handleTestAvailableModel(modelId: string) {
    setTestingModelId(modelId);
    try {
      await handleTestModel(modelId);
    } finally {
      setTestingModelId(null);
    }
  }

  useEffect(() => {
    if (isSuperadmin && tab === "models") {
      fetchModelSettings();
      if (availableModels.length === 0) {
        handleFetchAvailableModels();
      }
    }
    if (isSuperadmin && tab === "telegram") {
      fetchTelegramSettings().then((d) => {
        if (d) setTelegramSettings(d);
      });
      fetchTelegramSocialAccounts().then(setTelegramSocialAccounts);
    }
    if (tab === "system_config") {
      loadSystemConfig(sysConfigUnmask);
    }
    if (tab === "autopilot") {
      loadAutopilotData();
    }
  }, [isSuperadmin, tab, sysConfigUnmask]);

  async function loadAutopilotData() {
    setIsLoadingAutopilot(true);
    try {
      const [res, presetsRes, platsRes, histRes] = await Promise.all([
        autopilotApi.getSettings(),
        presetsApi.list().catch(() => ({ presets: [] })),
        socialApi.getPlatformsStatus().catch(() => ({ platforms: [] })),
        autopilotApi.getHistory(15).catch(() => ({ data: [] })),
      ]);
      if (res && res.data) {
        setAutopilotSettings(res.data);
        setAutopilotQuota(res.quota);
        setAutopilotCanRun(res.can_run_today);
      }
      const rawPresets = (presetsRes as any)?.data || (presetsRes as any)?.presets || (Array.isArray(presetsRes) ? presetsRes : []);
      setAutopilotPresets(Array.isArray(rawPresets) ? rawPresets : []);
      const rawPlats = (platsRes as any)?.platforms || platsRes || {};
      setAutopilotPlatforms(rawPlats);
      const rawHist = (histRes as any)?.data || (Array.isArray(histRes) ? histRes : []);
      setAutopilotHistory(Array.isArray(rawHist) ? rawHist : []);
    } catch (e: any) {
      toast.error("Gagal memuat pengaturan Autopilot: " + (e?.message || ""));
    } finally {
      setIsLoadingAutopilot(false);
    }
  }

  function getAutopilotPlatInfo(platId: string): { connected: boolean; count: number; accounts: any[] } {
    if (!autopilotPlatforms) return { connected: false, count: 0, accounts: [] };
    if (typeof autopilotPlatforms === "object" && !Array.isArray(autopilotPlatforms)) {
      const pMap = (autopilotPlatforms as any)?.platforms || autopilotPlatforms;
      const p = pMap[platId];
      if (p) {
        const isConn = Boolean(p.connected || p.count > 0 || (p.accounts && p.accounts.length > 0));
        const accList = Array.isArray(p.accounts) ? p.accounts : [];
        return {
          connected: isConn,
          count: p.count || accList.length || (isConn ? 1 : 0),
          accounts: accList,
        };
      }
    } else if (Array.isArray(autopilotPlatforms)) {
      const accList = autopilotPlatforms.filter((a: any) => (a.platform || a.type || "").toLowerCase() === platId.toLowerCase());
      return {
        connected: accList.length > 0,
        count: accList.length,
        accounts: accList,
      };
    }
    return { connected: false, count: 0, accounts: [] };
  }

  async function handleSaveAutopilot() {
    if (!autopilotSettings) return;
    setIsSavingAutopilot(true);
    try {
      const res = await autopilotApi.updateSettings(autopilotSettings);
      if (res && res.data) {
        setAutopilotSettings(res.data);
        setAutopilotQuota(res.quota);
        setAutopilotCanRun(res.can_run_today);
        toast.success("Pengaturan Hermes Autopilot berhasil disimpan!");
      }
    } catch (e: any) {
      toast.error("Gagal menyimpan Autopilot: " + (e?.message || ""));
    } finally {
      setIsSavingAutopilot(false);
    }
  }

  async function handleTriggerAutopilot(force: boolean = false) {
    setIsRunningAutopilot(true);
    try {
      toast.info("Memulai Hermes Autopilot discovery & submission...");
      const res = await autopilotApi.triggerRun(force);
      if (res.success) {
        toast.success(`Autopilot berhasil! Video '${res.video?.title}' disubmit (Job #${res.job_id})`);
        loadAutopilotData();
      } else {
        toast.error(res.message || "Autopilot gagal dijalankan");
      }
    } catch (e: any) {
      toast.error("Error menjalankan Autopilot: " + (e?.message || ""));
    } finally {
      setIsRunningAutopilot(false);
    }
  }

  async function loadSystemConfig(unmask: boolean = false) {
    setIsLoadingSysConfig(true);
    try {
      const res = await systemConfig.get(unmask);
      if (res && res.data) {
        setSysConfigItems(res.data);
        setCanEditSecrets(res.can_edit_secrets);
        const initialEdits: Record<string, any> = {};
        res.data.forEach(item => {
          initialEdits[item.key] = item.value;
        });
        setSysConfigEdits(initialEdits);
      }
    } catch (err: any) {
      toast.error("Gagal memuat konfigurasi sistem: " + (err?.message || ""));
    } finally {
      setIsLoadingSysConfig(false);
    }
  }

  async function handleSaveSysConfig() {
    setIsSavingSysConfig(true);
    try {
      const res = await systemConfig.update(sysConfigEdits);
      if (res && res.success) {
        toast.success(res.message || "Konfigurasi sistem berhasil diperbarui");
        loadSystemConfig(sysConfigUnmask);
      }
    } catch (err: any) {
      toast.error("Gagal menyimpan konfigurasi: " + (err?.message || ""));
    } finally {
      setIsSavingSysConfig(false);
    }
  }

  async function handleResetSysConfigKey(key: string) {
    if (!(await confirmDialog({ title: `Reset ${key}?`, message: `Reset konfigurasi ${key} ke default sistem?`, confirmText: "Reset", danger: true }))) return;
    try {
      const res = await systemConfig.reset(key);
      if (res && res.success) {
        toast.success(`Konfigurasi ${key} direset ke default`);
        loadSystemConfig(sysConfigUnmask);
      }
    } catch (err: any) {
      toast.error("Gagal mereset konfigurasi: " + (err?.message || ""));
    }
  }

  async function handleSaveTelegram() {
    setIsSavingTelegram(true);
    const ok = await saveTelegramSettingsApi(telegramSettings);
    if (ok) {
      toast.success("Pengaturan Telegram berhasil disimpan");
      fetchTelegramSettings().then((d) => { if (d) setTelegramSettings(d); });
    } else {
      toast.error("Gagal menyimpan pengaturan Telegram");
    }
    setIsSavingTelegram(false);
  }

  async function handleTestTelegram() {
    setIsTestingTelegram(true);
    setTelegramTestResult(null);
    try {
      const res = await testTelegramConnectionApi(
        telegramSettings.bot_token,
        telegramSettings.chat_id || telegramSettings.group_id || telegramSettings.channel_id
      );
      setTelegramTestResult(res);
      if (res.success) {
        toast.success(`Koneksi bot berhasil! ${res.bot_username ? `(@${res.bot_username})` : ""}`);
        if (res.bot_username && res.bot_username !== telegramSettings.bot_username) {
          setTelegramSettings((p) => ({ ...p, bot_username: res.bot_username }));
        }
      } else {
        toast.error(res.error || "Tes koneksi bot gagal");
      }
    } catch (e: any) {
      toast.error(e.message || "Tes koneksi gagal");
    } finally {
      setIsTestingTelegram(false);
    }
  }

  async function handleTestTelegramVideo() {
    setIsTestingTelegramVideo(true);
    try {
      const res = await testTelegramVideoApi(
        telegramSettings.chat_id || telegramSettings.group_id || telegramSettings.channel_id
      );
      if (res.success) {
        toast.success(`Video tes berhasil dikirim ke Telegram (${res.sent_count || 1} target)!`);
      } else {
        toast.error(res.error || "Gagal mengirim video tes ke Telegram");
      }
    } catch (e: any) {
      toast.error(e.message || "Gagal mengirim video tes");
    } finally {
      setIsTestingTelegramVideo(false);
    }
  }

  function handleCopyCommand(cmd: string) {
    navigator.clipboard.writeText(cmd);
    setCopiedCmd(cmd);
    setTimeout(() => setCopiedCmd(null), 2000);
    toast.success("Perintah disalin ke clipboard");
  }


  const tabs = [
    { id: "general" as const, label: "General", icon: <SlidersHorizontal className="h-3.5 w-3.5" />, group: "Preferences", badge: "All Users" },
    { id: "autopilot" as const, label: "Hermes Autopilot", icon: <Bot className="h-3.5 w-3.5" />, group: "Automation", badge: "1 Video/Hari" },
    { id: "render" as const, label: "Render Engine", icon: <Film className="h-3.5 w-3.5" />, group: "Preferences", badge: "All Users" },
    { id: "reframe" as const, label: "Reframe Tuning", icon: <Cpu className="h-3.5 w-3.5" />, group: "Visual Studio", badge: isSuperadmin ? "Global Defaults" : "Personal" },
    { id: "hyperframes" as const, label: "HyperFrames Hook", icon: <Sparkles className="h-3.5 w-3.5" />, group: "Visual Studio", badge: isSuperadmin ? "Global Defaults" : "Personal" },
    { id: "object" as const, label: "Object Overlay", icon: <Palette className="h-3.5 w-3.5" />, group: "Visual Studio", badge: isSuperadmin ? "Global Defaults" : "Personal" },
    ...(isSuperadmin ? [
      { id: "system_config" as const, label: "Database & Env Config", icon: <HardDrive className="h-3.5 w-3.5" />, group: "Administration", badge: "Dynamic DB" },
      { id: "models" as const, label: "AI Models", icon: <BrainCircuit className="h-3.5 w-3.5" />, group: "Administration", badge: "Superadmin" },
      { id: "telegram" as const, label: "Telegram Bot", icon: <Bot className="h-3.5 w-3.5" />, group: "Administration", badge: "Superadmin" },
      { id: "users" as const, label: "Users", icon: <UserPlus className="h-3.5 w-3.5" />, group: "Administration", badge: "Superadmin" },
      { id: "testing" as const, label: "Test & Deploy", icon: <Terminal className="h-3.5 w-3.5" />, group: "Administration", badge: "Superadmin" },
    ] : []),
  ];

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="shrink-0 space-y-3 mb-4">
        <div className="flex flex-wrap items-center justify-between gap-3 bg-zinc-950/70 border border-zinc-800/80 rounded-2xl px-4 py-3 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-violet-500/20 to-indigo-500/20 border border-violet-500/30 flex items-center justify-center text-violet-300">
              <SlidersHorizontal className="h-4 w-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-semibold text-zinc-100">Settings</h1>
                {isSuperadmin ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                    <Shield className="h-2.5 w-2.5" />
                    Superadmin
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-zinc-800 text-zinc-300 border border-zinc-700">
                    <UserCheck className="h-2.5 w-2.5" />
                    User Settings
                  </span>
                )}
              </div>
              <p className="text-[11px] text-zinc-400">
                {isSuperadmin
                  ? "Sistem kontrol penuh: model AI, bot Telegram, manajemen pengguna, dan visual tuning global."
                  : "Pengaturan preferensi video, engine rendering, dan studio visual personal."}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {tab === "users" || tab === "testing" ? null : tab === "autopilot" ? (
              <div className="flex items-center gap-2">
                <Button
                  onClick={() => handleTriggerAutopilot(false)}
                  loading={isRunningAutopilot}
                  disabled={!autopilotCanRun}
                  size="sm"
                  variant="outline"
                  icon={<Play className="h-3.5 w-3.5" />}
                >
                  {autopilotCanRun ? "Jalankan Hari Ini (1 Video)" : "Kuota Hari Ini Terpenuhi"}
                </Button>
                <Button onClick={handleSaveAutopilot} loading={isSavingAutopilot} icon={<Save className="h-3.5 w-3.5" />} size="sm">Save</Button>
              </div>
            ) : tab === "hyperframes" ? (
              <div className="flex items-center gap-2">
                {hfDirty && <span className="text-[10px] text-amber-400 font-medium mr-1 animate-pulse">Unsaved changes</span>}
                <Button onClick={handleRestoreHfDefaults} loading={isResettingHf} size="sm" variant="outline">Restore Defaults</Button>
                <Button onClick={handleResetHf} disabled={!hfDirty} size="sm" variant="outline">Reset</Button>
                <Button onClick={handleSaveHf} disabled={!hfDirty} loading={isSavingHf} icon={<Save className="h-3.5 w-3.5" />} size="sm">Save</Button>
              </div>
            ) : tab === "reframe" ? (
              <div className="flex items-center gap-2">
                {reframeDirty && <span className="text-[10px] text-amber-400 font-medium mr-1 animate-pulse">Unsaved changes</span>}
                <Button onClick={handleRestoreReframeDefaults} loading={isResettingReframe} size="sm" variant="outline">Restore Defaults</Button>
                <Button onClick={handleResetReframe} disabled={!reframeDirty} size="sm" variant="outline">Reset</Button>
                <Button onClick={handleSaveReframe} disabled={!reframeDirty} loading={isSavingReframe} icon={<Save className="h-3.5 w-3.5" />} size="sm">Save</Button>
              </div>
            ) : tab === "object" ? (
              <div className="flex items-center gap-2">
                {objectDirty && <span className="text-[10px] text-amber-400 font-medium mr-1 animate-pulse">Unsaved changes</span>}
                <Button onClick={handleRestoreObjectDefaults} loading={isResettingObject} size="sm" variant="outline">Restore Defaults</Button>
                <Button onClick={handleResetObject} disabled={!objectDirty} size="sm" variant="outline">Reset</Button>
                <Button onClick={handleSaveObject} disabled={!objectDirty} loading={isSavingObject} icon={<Save className="h-3.5 w-3.5" />} size="sm">Save</Button>
              </div>
            ) : tab === "models" ? (
              <div className="flex items-center gap-2">
                <Button onClick={handleTestAllModels} loading={isTestingAll} size="sm" variant="outline" icon={<RefreshCw className="h-3.5 w-3.5" />}>Test All</Button>
                <Button onClick={() => handleTestModel()} loading={isTestingModel} size="sm" variant="outline" icon={<Zap className="h-3.5 w-3.5" />}>Test Model</Button>
                <Button onClick={handleSaveModels} loading={isSavingModels} icon={<Save className="h-3.5 w-3.5" />} size="sm">Save</Button>
              </div>
            ) : tab === "telegram" ? (
              <div className="flex items-center gap-2">
                <Button onClick={handleTestTelegram} loading={isTestingTelegram} size="sm" variant="outline" icon={<Zap className="h-3.5 w-3.5" />}>Test Ping</Button>
                <Button onClick={handleTestTelegramVideo} loading={isTestingTelegramVideo} size="sm" variant="outline" icon={<Play className="h-3.5 w-3.5" />}>Test Video</Button>
                <Button onClick={handleSaveTelegram} loading={isSavingTelegram} icon={<Save className="h-3.5 w-3.5" />} size="sm">Save</Button>
              </div>
            ) : (
              <Button onClick={handleSave} loading={isSaving} icon={<Save className="h-3.5 w-3.5" />} size="sm">Save</Button>
            )}
          </div>
        </div>

        {/* Tab Pills Navigation */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
          {tabs.map((t) => {
            const isActive = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border transition-all whitespace-nowrap",
                  isActive
                    ? "bg-zinc-800 border-zinc-700 text-zinc-100 shadow-sm"
                    : "bg-zinc-900/40 border-zinc-800/60 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40"
                )}
              >
                <span className={cn(isActive ? "text-violet-400" : "text-zinc-500")}>{t.icon}</span>
                <span>{t.label}</span>
                {t.group === "Administration" && (
                  <span className="text-[9px] font-semibold px-1 rounded bg-red-500/10 text-red-400 border border-red-500/20">Admin</span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab content */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === "general" && (
          <div className="space-y-4 max-w-4xl">
            {/* Scope info card */}
            <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-3.5 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2.5">
                <Info className="h-4 w-4 text-violet-400 shrink-0" />
                <span className="text-zinc-300">
                  {isSuperadmin
                    ? "Pengaturan preferensi default tingkat akun dan parameter pipeline sistem."
                    : "Preferensi render default yang otomatis digunakan saat memproses video baru."}
                </span>
              </div>
              <Badge variant="default" className="text-[10px]">
                {isSuperadmin ? "Admin & User Preferences" : "User Preferences"}
              </Badge>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {health && (
                <Card className="p-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="h-9 w-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                      <Server className="h-4 w-4 text-emerald-400" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-zinc-200">Backend Server Status</p>
                      <p className="text-[11px] text-zinc-500">v{health.version} — Mode: {health.mode}</p>
                    </div>
                  </div>
                  <span className="flex items-center gap-1.5 text-[11px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20 font-medium">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    Online
                  </span>
                </Card>
              )}

              <Card className="p-4 space-y-2.5">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-semibold text-zinc-200 flex items-center gap-1.5">
                    <Film className="h-3.5 w-3.5 text-zinc-400" />
                    Default Aspect Ratio
                  </h3>
                  <span className="text-[10px] text-zinc-500 font-mono">{settings.default_aspect_ratio}</span>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { id: "9:16", label: "9:16", desc: "Shorts/Reels" },
                    { id: "16:9", label: "16:9", desc: "YouTube" },
                    { id: "1:1", label: "1:1", desc: "Square" },
                  ].map((ratio) => (
                    <button
                      key={ratio.id}
                      type="button"
                      onClick={() => handleChange("default_aspect_ratio", ratio.id)}
                      className={cn(
                        "rounded-lg border p-2 text-center transition-all",
                        settings.default_aspect_ratio === ratio.id
                          ? "border-violet-500 bg-violet-500/10 text-zinc-100"
                          : "border-zinc-800 bg-zinc-950/40 text-zinc-400 hover:border-zinc-700"
                      )}
                    >
                      <span className="block text-xs font-bold">{ratio.label}</span>
                      <span className="block text-[10px] text-zinc-500">{ratio.desc}</span>
                    </button>
                  ))}
                </div>
              </Card>

              <Card className="p-4 space-y-2">
                <div className="flex items-center gap-1.5">
                  <Cpu className="h-3.5 w-3.5 text-zinc-400" />
                  <h3 className="text-xs font-semibold text-zinc-200">Whisper Speech-to-Text Model</h3>
                </div>
                {isSuperadmin ? (
                  <>
                    <Select
                      value={settings.whisper_model_size}
                      onChange={(e) => handleChange("whisper_model_size", e.target.value)}
                      options={[
                        { value: "tiny", label: "Tiny (Sangat Cepat · Akurasi Dasar)" },
                        { value: "base", label: "Base (Cepat · Akurasi Standar)" },
                        { value: "small", label: "Small (Seimbang)" },
                        { value: "medium", label: "Medium (Direkomendasikan)" },
                        { value: "large-v3", label: "Large v3 (Akurasi Timestamp Tertinggi)" },
                      ]}
                    />
                    <p className="text-[10px] text-zinc-500">
                      Model berukuran lebih besar menghasilkan timestamp kata dan akurasi karaoke yang lebih presisi.
                    </p>
                  </>
                ) : (
                  <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-2.5">
                    <p className="text-xs text-zinc-300 font-medium">Model Aktif: <span className="text-violet-300 uppercase">{settings.whisper_model_size}</span></p>
                    <p className="text-[10px] text-zinc-500 mt-0.5">Dikonfigurasi oleh administrator sistem untuk pemrosesan transkrip.</p>
                  </div>
                )}
              </Card>

              <Card className="p-4 space-y-2">
                <div className="flex items-center gap-1.5">
                  <HelpCircle className="h-3.5 w-3.5 text-zinc-400" />
                  <h3 className="text-xs font-semibold text-zinc-200">Alur Kerja Otomatisasi Video</h3>
                </div>
                <div className="space-y-1.5 text-[11px] text-zinc-400">
                  <div className="flex items-center gap-2">
                    <span className="h-4 w-4 rounded-full bg-violet-500/20 text-violet-300 text-[10px] font-bold flex items-center justify-center">1</span>
                    <span>Masukkan URL YouTube / topik konten</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="h-4 w-4 rounded-full bg-violet-500/20 text-violet-300 text-[10px] font-bold flex items-center justify-center">2</span>
                    <span>AI menganalisis scene viral & transkrip kata</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="h-4 w-4 rounded-full bg-violet-500/20 text-violet-300 text-[10px] font-bold flex items-center justify-center">3</span>
                    <span>Remotion / HyperFrames me-render hook & subtitle</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="h-4 w-4 rounded-full bg-violet-500/20 text-violet-300 text-[10px] font-bold flex items-center justify-center">4</span>
                    <span>Unduh hasil video berkualitas tinggi atau kirim ke Telegram</span>
                  </div>
                </div>
              </Card>
            </div>

            {/* Superadmin System Controls */}
            {isSuperadmin && (
              <div className="pt-2 space-y-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-zinc-300">
                  <Shield className="h-3.5 w-3.5 text-red-400" />
                  <span>Superadmin System Controls</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Card className="p-4 border-amber-500/20 bg-zinc-950/40">
                    <div className="flex items-center gap-2 mb-2">
                      <Zap className="h-3.5 w-3.5 text-amber-400" />
                      <h3 className="text-xs font-semibold text-zinc-200">Pipeline Engine Mode</h3>
                    </div>
                    <p className="text-[11px] text-zinc-400 mb-3">
                      Pilih engine AI default untuk pemrosesan kurasi video klip.
                    </p>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => handleChange("pipeline_mode", "v1")}
                        className={cn(
                          "flex-1 px-3 py-2.5 rounded-lg border text-xs font-medium transition-all text-left",
                          settings.pipeline_mode === "v1"
                            ? "border-emerald-500 bg-emerald-500/10 text-emerald-400 shadow-sm"
                            : "border-zinc-800 text-zinc-400 hover:border-zinc-700"
                        )}
                      >
                        <span className="block text-[10px] uppercase font-bold text-emerald-400">V1 — Gemini</span>
                        <span className="text-[11px] text-zinc-300">Multi-Key Pool & High Accuracy</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleChange("pipeline_mode", "v2")}
                        className={cn(
                          "flex-1 px-3 py-2.5 rounded-lg border text-xs font-medium transition-all text-left",
                          settings.pipeline_mode === "v2"
                            ? "border-blue-500 bg-blue-500/10 text-blue-400 shadow-sm"
                            : "border-zinc-800 text-zinc-400 hover:border-zinc-700"
                        )}
                      >
                        <span className="block text-[10px] uppercase font-bold text-blue-400">V2 — 9Router</span>
                        <span className="text-[11px] text-zinc-300">Local Gateway & LLM Fallback</span>
                      </button>
                    </div>
                  </Card>

                  <Card className="p-4 border-red-500/20 bg-zinc-950/40">
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle className="h-3.5 w-3.5 text-red-400" />
                      <h3 className="text-xs font-semibold text-zinc-200">Danger Zone: Bersihkan Storage</h3>
                    </div>
                    <p className="text-[11px] text-zinc-400 mb-3">
                      Hapus seluruh riwayat job, file video hasil render, footage unduhan, dan objek di MinIO. Akun dan preset akan dipertahankan.
                    </p>
                    <Button
                      type="button"
                      size="sm"
                      onClick={handleClearStorage}
                      loading={isClearing}
                      className="bg-red-600/90 hover:bg-red-600 text-white border-red-600 w-full"
                      icon={<Trash2 className="h-3.5 w-3.5" />}
                    >
                      Bersihkan Semua Data Pemrosesan
                    </Button>
                  </Card>
                </div>
              </div>
            )}
          </div>
        )}

        {tab === "render" && (
          <div className="space-y-4 max-w-3xl">
            <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-3.5 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2.5">
                <Film className="h-4 w-4 text-violet-400 shrink-0" />
                <span className="text-zinc-300">
                  Konfigurasi render engine Remotion berbasis React untuk animasi hook, subtitle karaoke, dan visual layer.
                </span>
              </div>
              <Badge variant="default" className="text-[10px]">Tersedia untuk Semua Pengguna</Badge>
            </div>

            <Card className="p-4 space-y-4">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-lg bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
                    <Sparkles className="h-4 w-4 text-violet-400" />
                  </div>
                  <div>
                    <h3 className="text-xs font-semibold text-zinc-100">Remotion React Renderer</h3>
                    <p className="text-[11px] text-zinc-400">Rendering visual dinamis dengan frame-accurate timeline.</p>
                  </div>
                </div>
                <span className={cn(
                  "px-2 py-0.5 text-[10px] font-medium rounded-full border",
                  settings.use_remotion
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                    : "bg-zinc-800 text-zinc-400 border-zinc-700"
                )}>
                  {settings.use_remotion ? "Aktif" : "Nonaktif"}
                </span>
              </div>

              <div className="space-y-3">
                <FeatureToggle
                  icon={<Film className="h-3.5 w-3.5" />}
                  label="Gunakan Engine Remotion"
                  desc="Me-render hook dan subtitle dengan engine React modern untuk kualitas tertinggi"
                  active={settings.use_remotion}
                  onToggle={() => handleChange("use_remotion", !settings.use_remotion)}
                />

                {settings.use_remotion && (
                  <>
                    <FeatureToggle
                      icon={<Sparkles className="h-3.5 w-3.5" />}
                      label="AI Cinematic Text Layer"
                      desc="Otomatis mengekstrak kata kunci transkrip dan memunculkan animasi tipografi dinamis"
                      active={settings.remotion_ai_layer}
                      onToggle={() => handleChange("remotion_ai_layer", !settings.remotion_ai_layer)}
                    />

                    <div className="pt-1">
                      <Select
                        label="Kualitas Encoding Video (CRF)"
                        value={settings.remotion_quality}
                        onChange={(e) => handleChange("remotion_quality", e.target.value)}
                        options={[
                          { value: "low", label: "Fast Draft (CRF 28 · Render Cepat · Ukuran Kecil)" },
                          { value: "medium", label: "Standard 1080p (CRF 18 · Seimbang & Jernih)" },
                          { value: "high", label: "Cinematic High (CRF 12 · Kualitas Maksimal)" },
                        ]}
                      />
                    </div>
                  </>
                )}
              </div>
            </Card>

            <Card className="p-4 space-y-2">
              <h3 className="text-xs font-semibold text-zinc-200 flex items-center gap-1.5">
                <Activity className="h-3.5 w-3.5 text-zinc-400" />
                Akselerasi & Optimasi Performa
              </h3>
              <p className="text-[11px] text-zinc-400 leading-relaxed">
                Engine Remotion bekerja berdampingan dengan FFmpeg hardware passthrough. Ketika mode AI Layer aktif, frame visual di-overlay langsung ke video master tanpa perlu encoding ulang ganda.
              </p>
            </Card>
          </div>
        )}

        {tab === "reframe" && (
          <div className="space-y-4">
            <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-3.5 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2.5">
                <Cpu className="h-4 w-4 text-violet-400 shrink-0" />
                <span className="text-zinc-300">
                  {isSuperadmin
                    ? "Konfigurasi Person-First Reframe Global (default untuk seluruh proses kliping video di server)."
                    : "Kustomisasi Person-First Reframe untuk workspace akun Anda."}
                </span>
              </div>
              <Badge variant="default" className="text-[10px]">
                {isSuperadmin ? "Global Defaults (Superadmin)" : "Personal Tuning Override"}
              </Badge>
            </div>

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
          </div>
        )}

        {tab === "hyperframes" && (
          <div className="max-w-4xl space-y-5">
            {/* Scope info card */}
            <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-3.5 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2.5">
                <Sparkles className="h-4 w-4 text-violet-400 shrink-0" />
                <span className="text-zinc-300">
                  {isSuperadmin
                    ? "Katalog Template HyperFrames Hook & Polish (dapat dipilih langsung saat generate video)."
                    : "Pilihan template HyperFrames Hook & Polish untuk video klip akun Anda."}
                </span>
              </div>
              <Badge variant="default" className="text-[10px]">
                {isSuperadmin ? "Global Template Catalog" : "Studio Style Presets"}
              </Badge>
            </div>

            {/* Master Controls Card */}
            <Card className="p-5 space-y-4 border-violet-500/20 bg-zinc-950/70">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-violet-400" />
                    HyperFrames Hook &amp; Polish Layer
                  </h3>
                  <p className="text-xs text-zinc-400 mt-1">
                    Render kartu topik/hook dinamis berbasis HTML5/CSS headless di posisi aman atas (tidak menabrak subtitle).
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={cn("text-xs font-bold px-2 py-0.5 rounded", hfConfig.enabled ? "bg-emerald-500/20 text-emerald-300" : "bg-zinc-800 text-zinc-500")}>
                    {hfConfig.enabled ? "ACTIVE" : "DISABLED"}
                  </span>
                </div>
              </div>

              <div className="pt-2 border-t border-zinc-800/60 grid grid-cols-1 md:grid-cols-3 gap-4">
                <FeatureToggle
                  icon={<Zap className="h-3.5 w-3.5" />}
                  label="Enable HyperFrames"
                  desc="Aktifkan layer hook & topic polish"
                  active={hfConfig.enabled}
                  onToggle={() => handleHfChange("enabled", !hfConfig.enabled)}
                />

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-zinc-300">Selection Mode</label>
                  <div className="grid grid-cols-2 gap-1.5 bg-zinc-900/80 p-1 rounded-lg border border-zinc-800">
                    <button
                      type="button"
                      onClick={() => handleHfChange("mode", "auto")}
                      className={cn(
                        "py-1.5 px-2 text-xs font-medium rounded-md transition-all text-center flex items-center justify-center gap-1.5",
                        hfConfig.mode === "auto"
                          ? "bg-violet-600 text-white font-bold shadow-md shadow-violet-600/30"
                          : "text-zinc-400 hover:text-zinc-200"
                      )}
                    >
                      <Bot className="w-3.5 h-3.5" />
                      AI Auto
                    </button>
                    <button
                      type="button"
                      onClick={() => handleHfChange("mode", "manual")}
                      className={cn(
                        "py-1.5 px-2 text-xs font-medium rounded-md transition-all text-center flex items-center justify-center gap-1.5",
                        hfConfig.mode === "manual"
                          ? "bg-violet-600 text-white font-bold shadow-md shadow-violet-600/30"
                          : "text-zinc-400 hover:text-zinc-200"
                      )}
                    >
                      <Palette className="w-3.5 h-3.5" />
                      Spesifik
                    </button>
                  </div>
                  <p className="text-[10px] text-zinc-500 mt-0.5">
                    {hfConfig.mode === "auto"
                      ? "AI otomatis merotasi 12+ style per klip agar bervariasi."
                      : "Gunakan 1 template yang Anda pilih di bawah untuk semua klip."}
                  </p>
                </div>

                <Select
                  label="Safe Zone Placement"
                  value={hfConfig.position || "safe_upper"}
                  onChange={(e) => handleHfChange("position", e.target.value)}
                  options={[
                    { value: "safe_upper", label: "Safe Upper Area (Recommended)" },
                    { value: "top", label: "Top Screen Banner" },
                    { value: "floating_badge", label: "Top-Left Floating Badge" },
                  ]}
                />
              </div>
            </Card>

            {/* Style Catalogue Grid */}
            <Card className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-xs font-semibold text-zinc-200 uppercase tracking-wider">
                    Koleksi Visual Styles (12+ Hook &amp; Polish Designs)
                  </h3>
                  <p className="text-[11px] text-zinc-500 mt-0.5">
                    Klik salah satu kartu untuk memilih template spesifik atau melihat estetika desainnya.
                  </p>
                </div>
                {hfConfig.mode === "auto" && (
                  <span className="text-[10px] bg-violet-500/20 text-violet-300 font-semibold px-2.5 py-1 rounded-full border border-violet-500/30">
                    Mode Auto Aktif: Semua style akan dirotasi otomatis
                  </span>
                )}
              </div>

              {(() => {
                const catalogueItems = hfCatalogue.length > 0 ? hfCatalogue : [
                  // ── Page 1: Premier Hero Styles (User Top 6) ──
                  { id: "hook_cyber_hud", name: "Cyberpunk Tech HUD", design: "cyber-hud", accent: "#00F0FF", description: "Tech HUD digital box dengan aksen neon cyan & bracket cyberpunk" },
                  { id: "hook_floating_badge", name: "Top Floating Badge", design: "floating-badge", accent: "#10B981", description: "Badge melayang di sudut atas dengan beacon live pulse & list neon" },
                  { id: "hook_kinetic_split", name: "Kinetic Duotone Split", design: "kinetic-split", accent: "#FF6B00", description: "Panel terbelah oranye-hitam dinamis dengan nomor indeks kinetik" },
                  { id: "hook_electric_surge", name: "Electric Plasma Shockwave", design: "electric-surge", accent: "#818CF8", description: "Shockwave plasma nebula elektrik dengan aksen petir & laser glow" },
                  { id: "hook_glass_minimal", name: "Frosted Glassmorphism", design: "glass-minimal", accent: "#A78BFA", description: "Kartu transparan frosted glass Apple-grade dengan efek blur & glow halus" },
                  { id: "hook_editorial_pill", name: "Editorial Minimal Pill", design: "editorial-pill", accent: "#E2E8F0", description: "Kapsul obsidian hitam matte dengan dot emas & tipografi editorial" },

                  // ── Page 2: High-Converting & Cinematic ──
                  { id: "hook_breaking_news", name: "Breaking News Live", design: "breaking-news", accent: "#EF4444", description: "Banner merah bold dengan badge LIVE UPDATE berkedip" },
                  { id: "hook_luxury_noir", name: "Luxury Obsidian & Gold", design: "luxury-noir", accent: "#D4AF37", description: "Kartu hitam obsidian pekat dengan list emas sampanye mewah" },
                  { id: "hook_retro_synth", name: "80s Retro Synthwave", design: "retro-synth", accent: "#F43F5E", description: "Estetika synthwave retro 80-an dengan tabung neon ungu-pink" },
                  { id: "hook_chromatic_gate_v2", name: "Chromatic Gate Y2K", design: "chromatic-gate", accent: "#FF2E88", description: "Gerbang chromatic tajam dengan glitch RGB & sudut brutalist" },
                  { id: "hook_gradient_aura", name: "Gradient Aura Mesh", design: "gradient-aura", accent: "#38BDF8", description: "Cahaya aura mesh gradasi multi-warna halus di sekitar teks" },
                  { id: "hook_warning_hazard", name: "Warning Industrial Hazard", design: "warning-hazard", accent: "#F59E0B", description: "Pita hazard striping dengan badge critical notice" },

                  // ── Page 3: Creative Technical & Sci-Fi ──
                  { id: "hook_orbit_stamp_v2", name: "Orbit Stamp Seal", design: "orbit-stamp", accent: "#8B5CF6", description: "Cap lingkaran orbit berputar futuristik tanda autentik" },
                  { id: "hook_pixel_ticker_v2", name: "Arcade Pixel Ticker", design: "pixel-ticker", accent: "#F7FF58", description: "Pixel ticker kuning retro dengan grid dot arcade" },
                  { id: "hook_blueprint_v2", name: "Blueprint Arch Reveal", design: "blueprint-reveal", accent: "#52C7FF", description: "Sketsa blueprint biru arsitektural terukur" },
                  { id: "hook_comic_pop", name: "Comic Pop Burst", design: "comic-pop", accent: "#FACC15", description: "Badge komik miring bold kuning dengan aksen halftone pop-art" },
                  { id: "hook_hologram_scan", name: "Sci-Fi Hologram Scanner", design: "hologram-scan", accent: "#06B6D4", description: "Data feed holographic sci-fi dengan scanline vertikal" },
                  { id: "hook_cinema_tape", name: "Caution Stencil Tape", design: "cinema-tape", accent: "#EAB308", description: "Pita peringatan diagonal kuning-hitam dengan font stencil industrial" },
                ];

                const PAGE_SIZE = 6;
                const totalPages = Math.ceil(catalogueItems.length / PAGE_SIZE) || 1;
                const currentPage = Math.min(Math.max(1, hfCataloguePage), totalPages);
                const startIndex = (currentPage - 1) * PAGE_SIZE;
                const visibleCatalogue = catalogueItems.slice(startIndex, startIndex + PAGE_SIZE);

                return (
                  <div className="space-y-4">
                    {/* 2 lines x 3 grid items = 6 items */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                      {visibleCatalogue.map((item: any) => {
                        const isSelected = hfConfig.default_template === item.id;
                        return (
                          <div
                            key={item.id}
                            onClick={() => {
                              handleHfChange("default_template", item.id);
                              handleHfChange("mode", "manual");
                              toast.success(`Template set to "${item.name}"`);
                            }}
                            className={cn(
                              "group relative cursor-pointer rounded-xl border p-3.5 transition-all flex flex-col justify-between gap-3 text-left overflow-hidden",
                              isSelected
                                ? "border-violet-500 bg-violet-950/30 shadow-lg shadow-violet-500/10 ring-1 ring-violet-500/50"
                                : "border-zinc-800/80 bg-zinc-950/60 hover:border-zinc-700 hover:bg-zinc-900/60"
                            )}
                          >
                            <div>
                              <div className="flex items-center justify-between gap-2 mb-2">
                                <div className="flex items-center gap-2 min-w-0">
                                  <span
                                    className="w-3 h-3 rounded-full shrink-0 shadow-sm"
                                    style={{ backgroundColor: item.accent || "#a78bfa" }}
                                  />
                                  <span className="font-bold text-xs text-zinc-100 group-hover:text-white transition-colors truncate">
                                    {item.name}
                                  </span>
                                </div>
                                {isSelected && (
                                  <span className="flex items-center gap-1 text-[9px] font-bold bg-violet-600 text-white px-1.5 py-0.5 rounded uppercase shrink-0">
                                    <Check className="h-2.5 w-2.5" /> Selected
                                  </span>
                                )}
                              </div>
                              <p className="text-[11px] text-zinc-400 line-clamp-2 leading-relaxed">
                                {item.description || "Gaya animasi hook visual profesional."}
                              </p>
                            </div>

                            <div className="flex items-center justify-between pt-2 border-t border-zinc-800/50 text-[10px] text-zinc-500">
                              <span className="font-mono text-zinc-500">{item.design}</span>
                              <span
                                className="font-mono font-semibold"
                                style={{ color: item.accent || "#a78bfa" }}
                              >
                                {item.accent}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {/* Pagination Controls */}
                    {totalPages > 1 && (
                      <div className="flex items-center justify-between pt-3 mt-2 border-t border-zinc-800/70">
                        <span className="text-xs text-zinc-400">
                          Halaman <strong className="text-zinc-200">{currentPage}</strong> dari <strong className="text-zinc-200">{totalPages}</strong> ({catalogueItems.length} styles total)
                        </span>
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            disabled={currentPage === 1}
                            onClick={() => setHfCataloguePage(Math.max(1, currentPage - 1))}
                            className="px-2.5 py-1 text-xs font-semibold rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-zinc-800 transition-colors"
                          >
                            Prev
                          </button>
                          {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                            <button
                              key={p}
                              type="button"
                              onClick={() => setHfCataloguePage(p)}
                              className={cn(
                                "w-7 h-7 text-xs font-bold rounded-lg transition-colors",
                                currentPage === p
                                  ? "bg-violet-600 text-white shadow-sm"
                                  : "border border-zinc-800 bg-zinc-900/70 text-zinc-400 hover:text-white hover:bg-zinc-800"
                              )}
                            >
                              {p}
                            </button>
                          ))}
                          <button
                            type="button"
                            disabled={currentPage === totalPages}
                            onClick={() => setHfCataloguePage(Math.min(totalPages, currentPage + 1))}
                            className="px-2.5 py-1 text-xs font-semibold rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-zinc-800 transition-colors"
                          >
                            Next
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}
            </Card>
          </div>
        )}

        {tab === "object" && (
          <div className="max-w-2xl space-y-4">
            <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-3.5 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2.5">
                <Palette className="h-4 w-4 text-violet-400 shrink-0" />
                <span className="text-zinc-300">
                  {isSuperadmin
                    ? "Pengaturan Top Image & Watermark Branding Global (default untuk seluruh server)."
                    : "Pengaturan Top Image & Watermark Branding untuk video akun Anda."}
                </span>
              </div>
              <Badge variant="default" className="text-[10px]">
                {isSuperadmin ? "Global Defaults (Superadmin)" : "Personal Workspace"}
              </Badge>
            </div>

            <Card className="p-4">
              <p className="text-[11px] text-zinc-400 mb-3">
                Entity card and branding layer baked into video before subtitle overlays.
              </p>
              <div className="space-y-3">
                <FeatureToggle
                  icon={<Sparkles className="h-3.5 w-3.5" />}
                  label="Enable Object Overlay"
                  desc="AI entities → stock photo card + label"
                  active={objectOverlay.enabled}
                  onToggle={() => handleObjectChange("enabled", !objectOverlay.enabled)}
                />
                <FeatureToggle
                  icon={<Film className="h-3.5 w-3.5" />}
                  label="Show Label"
                  desc="Text under image card"
                  active={objectOverlay.show_label}
                  onToggle={() => handleObjectChange("show_label", !objectOverlay.show_label)}
                />
                <RangeSlider label="Max per clip" value={objectOverlay.max_per_clip} min={0} max={6} step={1} onChange={(v) => handleObjectChange("max_per_clip", v)} />
                <RangeSlider label="Box size ratio" value={objectOverlay.box_size_ratio} min={0.12} max={0.55} step={0.01} onChange={(v) => handleObjectChange("box_size_ratio", v)} />
                <RangeSlider label="Corner radius" value={objectOverlay.corner_radius} min={0} max={40} step={1} onChange={(v) => handleObjectChange("corner_radius", v)} />
                <RangeSlider label="Duration (sec)" value={objectOverlay.duration_sec} min={1} max={5} step={0.1} onChange={(v) => handleObjectChange("duration_sec", v)} />
                <RangeSlider label="Margin ratio" value={objectOverlay.margin_ratio} min={0.01} max={0.12} step={0.01} onChange={(v) => handleObjectChange("margin_ratio", v)} />
                <RangeSlider label="Font scale" value={objectOverlay.font_scale} min={0.3} max={1.2} step={0.05} onChange={(v) => handleObjectChange("font_scale", v)} />
                <RangeSlider label="Opacity" value={objectOverlay.opacity} min={0.3} max={1} step={0.05} onChange={(v) => handleObjectChange("opacity", v)} />
                <RangeSlider label="Min relevance" value={objectOverlay.min_relevance} min={0.1} max={0.9} step={0.05} onChange={(v) => handleObjectChange("min_relevance", v)} />
                <Select
                  label="Position"
                  value={objectOverlay.position}
                  onChange={(e) => handleObjectChange("position", e.target.value)}
                  options={[
                    { value: "auto", label: "Dynamic Auto (Speaker Avoidance)" },
                    { value: "top_left", label: "Top Left" },
                    { value: "top_right", label: "Top Right" },
                    { value: "center_left", label: "Center Left" },
                    { value: "center_right", label: "Center Right" },
                    { value: "bottom_left", label: "Bottom Left" },
                    { value: "bottom_right", label: "Bottom Right" },
                  ]}
                />
                <Select
                  label="Animation"
                  value={objectOverlay.animation}
                  onChange={(e) => handleObjectChange("animation", e.target.value)}
                  options={[
                    { value: "slide_right", label: "Slide right" },
                    { value: "slide_left", label: "Slide left" },
                    { value: "slide_down", label: "Slide down" },
                    { value: "slide_up", label: "Slide up" },
                    { value: "fade", label: "Fade" },
                    { value: "pop", label: "Pop" },
                  ]}
                />
                <Input label="Text color (R,G,B)" value={objectOverlay.text_color} onChange={(e) => handleObjectChange("text_color", e.target.value)} />
                <Input label="BG color (R,G,B)" value={objectOverlay.bg_color} onChange={(e) => handleObjectChange("bg_color", e.target.value)} />
                <Input label="Border color (R,G,B)" value={objectOverlay.border_color} onChange={(e) => handleObjectChange("border_color", e.target.value)} />
              </div>
            </Card>
          </div>
        )}

        {tab === "users" && isSuperadmin && (
          <div className="max-w-3xl space-y-4">
            <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-3.5 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2.5">
                <UserPlus className="h-4 w-4 text-violet-400 shrink-0" />
                <span className="text-zinc-300">
                  Manajemen akun pengguna sistem dan aktivasi fitur premium (Dual Subtitle, Auto Grid, Three.js, AI Layer).
                </span>
              </div>
              <Badge variant="default" className="text-[10px]">Superadmin Access</Badge>
            </div>

            <div className="flex items-center justify-between">
              <p className="text-xs text-zinc-500">{users.length} users registered</p>
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

        {tab === "models" && isSuperadmin && (
          <div className="max-w-4xl space-y-4">
            <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-3.5 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2.5">
                <BrainCircuit className="h-4 w-4 text-violet-400 shrink-0" />
                <span className="text-zinc-300">
                  Monitoring status LLM model 9Router, fallback provider, kuota Gemini API key pool, dan latensi benchmark.
                </span>
              </div>
              <Badge variant="default" className="text-[10px]">Superadmin Access</Badge>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Left: Model Settings Form */}
            <div className="lg:col-span-2 space-y-4">
              <Card className="p-4">
                <div className="flex items-center gap-2 mb-4">
                  <BrainCircuit className="h-4 w-4 text-violet-400" />
                  <h3 className="text-sm font-semibold text-zinc-100">9router Model Configuration</h3>
                </div>
                <p className="text-[11px] text-zinc-500 mb-4">
                  Pengaturan model AI yang digunakan pipeline. Perubahan berlaku langsung setelah Save — tidak perlu restart server.
                </p>
                {isLoadingModelSettings ? (
                  <div className="flex items-center justify-center py-8">
                    <RefreshCw className="h-5 w-5 text-zinc-600 animate-spin" />
                    <span className="ml-2 text-xs text-zinc-500">Loading model settings...</span>
                  </div>
                ) : modelSettings.length === 0 ? (
                  <div className="text-center py-8">
                    <p className="text-[11px] text-zinc-600">Tidak ada model settings. Pastikan backend running dan migration sudah dijalankan.</p>
                  </div>
                ) : (
                <div className="space-y-3">
                  {modelSettings.map((s) => (
                    <div key={s.key}>
                      <label className="block text-[11px] font-medium text-zinc-400 mb-1">
                        {s.key}
                        {s.description && <span className="ml-2 text-zinc-600 font-normal">— {s.description}</span>}
                      </label>
                      <input
                        type={s.key.includes("API_KEY") ? "password" : "text"}
                        value={modelEdits[s.key] ?? ""}
                        onChange={(e) => setModelEdits((p) => ({ ...p, [s.key]: e.target.value }))}
                        className="w-full rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-violet-500 focus:outline-none transition-colors"
                        placeholder={s.key}
                      />
                      {s.updated_at && (
                        <p className="text-[9px] text-zinc-700 mt-0.5">Updated: {new Date(s.updated_at).toLocaleString()}</p>
                      )}
                    </div>
                  ))}
                </div>
                )}
              </Card>

              {/* Available Models from 9router */}
              <Card className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-semibold text-zinc-200">Available Models (from 9router)</h3>
                  <div className="flex items-center gap-1.5">
                    <Button onClick={handleTestAllModels} loading={isTestingAll} size="sm" variant="outline" icon={<RefreshCw className="h-3 w-3" />}>
                      Test All
                    </Button>
                    <Button onClick={handleFetchAvailableModels} loading={isLoadingModels} size="sm" variant="outline" icon={<RefreshCw className="h-3 w-3" />}>
                      Refresh
                    </Button>
                  </div>
                </div>
                {availableModels.length > 0 && (
                  <div className="relative mb-3">
                    <input
                      type="text"
                      placeholder="Cari model atau penyedia (mis. groq, openai)..."
                      value={modelSearch}
                      onChange={(e) => setModelSearch(e.target.value)}
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-950/60 pl-3 pr-8 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:border-violet-500 focus:outline-none transition-colors"
                    />
                    {modelSearch && (
                      <button
                        type="button"
                        onClick={() => setModelSearch("")}
                        className="absolute right-2 top-1/2 -translate-y-1/2 w-5 h-5 rounded-full flex items-center justify-center text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
                        aria-label="Clear search"
                      >
                        <XCircle className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                )}
                {availableModels.length > 0 ? (() => {
                  const filtered = availableModels.filter((m) => {
                    const q = modelSearch.trim().toLowerCase();
                    if (!q) return true;
                    return m.id.toLowerCase().includes(q) || (m.owned_by || "").toLowerCase().includes(q);
                  });
                  return (
                    <>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-[9px] text-zinc-600">
                          {filtered.length}/{availableModels.length} model
                        </span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-48 overflow-y-auto">
                        {filtered.map((m) => {
                          const isDefault = modelEdits["NINE_ROUTER_MODEL"] === m.id;
                          const isPass1 = modelEdits["NINE_ROUTER_PASS1_MODEL"] === m.id || modelEdits["NINE_ROUTER_MODEL_PASS1"] === m.id;
                          const isPass2 = modelEdits["NINE_ROUTER_PASS2_MODEL"] === m.id || modelEdits["NINE_ROUTER_MODEL_PASS2"] === m.id;
                          const isAiLayer = modelEdits["NINE_ROUTER_AI_LAYER_MODEL"] === m.id || modelEdits["NINE_ROUTER_MODEL_AI_LAYER"] === m.id;
                          const isAssigned = isDefault || isPass1 || isPass2 || isAiLayer;

                          return (
                            <div
                              key={m.id}
                              className={cn(
                                "group flex flex-col gap-1.5 rounded-lg border p-2.5 text-xs transition-all",
                                isAssigned
                                  ? "border-violet-500/60 bg-violet-500/[0.08]"
                                  : "border-zinc-800 bg-zinc-950/60 hover:border-zinc-700"
                              )}
                            >
                              <div className="flex items-start justify-between gap-1.5">
                                <div className="min-w-0 flex-1">
                                  <div className="flex items-center gap-1.5 flex-wrap">
                                    <span className="font-semibold text-zinc-100 truncate block">{m.id}</span>
                                    {isDefault && <span className="rounded bg-violet-500/20 px-1.5 py-0.2 text-[8px] font-bold text-violet-300 uppercase">Default</span>}
                                    {isPass1 && <span className="rounded bg-blue-500/20 px-1.5 py-0.2 text-[8px] font-bold text-blue-300 uppercase">Pass 1</span>}
                                    {isPass2 && <span className="rounded bg-emerald-500/20 px-1.5 py-0.2 text-[8px] font-bold text-emerald-300 uppercase">Pass 2</span>}
                                    {isAiLayer && <span className="rounded bg-amber-500/20 px-1.5 py-0.2 text-[8px] font-bold text-amber-300 uppercase">AI Layer</span>}
                                  </div>
                                  {m.owned_by && <span className="text-zinc-500 text-[10px] truncate block mt-0.5">{m.owned_by}</span>}
                                </div>
                                <button
                                  type="button"
                                  onClick={() => handleTestAvailableModel(m.id)}
                                  disabled={testingModelId !== null}
                                  title={`Test model ${m.id}`}
                                  className={cn(
                                    "shrink-0 flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-medium transition-colors",
                                    testingModelId === m.id
                                      ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
                                      : "border-zinc-700/60 text-zinc-400 hover:border-emerald-500/50 hover:text-emerald-300",
                                    testingModelId !== null && testingModelId !== m.id && "opacity-40 cursor-not-allowed"
                                  )}
                                >
                                  {testingModelId === m.id ? (
                                    <RefreshCw className="h-3 w-3 animate-spin text-amber-400" />
                                  ) : (
                                    <Zap className="h-3 w-3 text-amber-400" />
                                  )}
                                  Test
                                </button>
                              </div>

                              {/* Quick Role Assignment Buttons */}
                              <div className="flex items-center gap-1 pt-1 border-t border-zinc-800/60 flex-wrap">
                                <span className="text-[9px] text-zinc-500 mr-1">Set as:</span>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setModelEdits((p) => ({ ...p, NINE_ROUTER_MODEL: m.id }));
                                    toast.success(`"${m.id}" set as Default model`);
                                  }}
                                  className={cn(
                                    "px-1.5 py-0.5 text-[9px] rounded font-medium transition-colors",
                                    isDefault ? "bg-violet-600 text-white font-bold" : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
                                  )}
                                >
                                  Default
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setModelEdits((p) => ({ ...p, NINE_ROUTER_PASS1_MODEL: m.id, NINE_ROUTER_MODEL_PASS1: m.id }));
                                    toast.success(`"${m.id}" set as Pass 1 model`);
                                  }}
                                  className={cn(
                                    "px-1.5 py-0.5 text-[9px] rounded font-medium transition-colors",
                                    isPass1 ? "bg-blue-600 text-white font-bold" : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
                                  )}
                                >
                                  Pass 1
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setModelEdits((p) => ({ ...p, NINE_ROUTER_PASS2_MODEL: m.id, NINE_ROUTER_MODEL_PASS2: m.id }));
                                    toast.success(`"${m.id}" set as Pass 2 model`);
                                  }}
                                  className={cn(
                                    "px-1.5 py-0.5 text-[9px] rounded font-medium transition-colors",
                                    isPass2 ? "bg-emerald-600 text-white font-bold" : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
                                  )}
                                >
                                  Pass 2
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setModelEdits((p) => ({ ...p, NINE_ROUTER_AI_LAYER_MODEL: m.id, NINE_ROUTER_MODEL_AI_LAYER: m.id }));
                                    toast.success(`"${m.id}" set as AI Layer model`);
                                  }}
                                  className={cn(
                                    "px-1.5 py-0.5 text-[9px] rounded font-medium transition-colors",
                                    isAiLayer ? "bg-amber-600 text-white font-bold" : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
                                  )}
                                >
                                  AI Layer
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      {filtered.length === 0 && (
                        <p className="text-[11px] text-zinc-600">Tidak ada model yang cocok dengan "{modelSearch}".</p>
                      )}
                    </>
                  );
                })() : (
                  <p className="text-[11px] text-zinc-600">Klik Refresh untuk melihat model tersedia di 9router.</p>
                )}
              </Card>
            </div>

            {/* Right: Test Result */}
            <div className="space-y-4">
              <Card className="p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Zap className="h-4 w-4 text-amber-400" />
                  <h3 className="text-xs font-semibold text-zinc-200">Test Result</h3>
                </div>
                {modelTestResult ? (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      {modelTestResult.success ? (
                        <Badge variant="success" dot>Connected</Badge>
                      ) : (
                        <Badge variant="error" dot>Failed</Badge>
                      )}
                      {modelTestResult.latency_hint && (
                        <span className="text-[10px] text-zinc-500">{modelTestResult.latency_hint}</span>
                      )}
                    </div>
                    <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
                      <p className="text-[10px] text-zinc-500 mb-1">Model: {modelTestResult.model}</p>
                      <p className="text-[10px] text-zinc-500 mb-2">URL: {modelTestResult.base_url}</p>
                      {modelTestResult.response && (
                        <div className="border-t border-zinc-800 pt-2 mt-2">
                          <p className="text-[10px] text-zinc-500 mb-1">Response:</p>
                          <p className="text-xs text-zinc-300">{modelTestResult.response}</p>
                        </div>
                      )}
                      {modelTestResult.error && (
                        <div className="border-t border-zinc-800 pt-2 mt-2">
                          <p className="text-[10px] text-red-400">{modelTestResult.error}</p>
                        </div>
                      )}
                      {modelTestResult.usage && (
                        <div className="border-t border-zinc-800 pt-2 mt-2">
                          <p className="text-[10px] text-zinc-600">
                            Tokens: {modelTestResult.usage.prompt_tokens || 0} in / {modelTestResult.usage.completion_tokens || 0} out
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg border border-dashed border-zinc-700 bg-zinc-950/40 p-6 text-center">
                    <Zap className="h-6 w-6 text-zinc-700 mx-auto mb-2" />
                    <p className="text-[11px] text-zinc-500">Klik "Test Model" untuk cek koneksi</p>
                    <p className="text-[10px] text-zinc-700 mt-1">Mengirim prompt sederhana ke model aktif</p>
                  </div>
                )}
              </Card>

              <Card className="p-4">
                <h3 className="text-xs font-semibold text-zinc-200 mb-2">Catatan</h3>
                <ul className="space-y-1.5 text-[11px] text-zinc-500">
                  <li>• Setting disimpan di DB, bukan .env</li>
                  <li>• Perubahan model langsung aktif tanpa restart</li>
                  <li>• Gunakan Test untuk validasi sebelum Save</li>
                  <li>• PASS1 = transcript analysis, PASS2 = highlight</li>
                  <li>• AI_LAYER = text emphasis generation</li>
                </ul>
              </Card>

              {/* Test All Models Results */}
              <Card className="p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Server className="h-4 w-4 text-blue-400" />
                  <h3 className="text-xs font-semibold text-zinc-200">All Models Status</h3>
                </div>
                {testAllResults?.success && testAllResults?.results ? (
                  <div className="space-y-2">
                    <div className="flex items-center gap-3 mb-3">
                      <Badge variant="success" size="sm">{testAllResults.ok} Active</Badge>
                      {testAllResults.failed > 0 && <Badge variant="error" size="sm">{testAllResults.failed} Failed</Badge>}
                      <span className="text-[10px] text-zinc-600">{testAllResults.total} total</span>
                    </div>
                    <div className="max-h-64 overflow-y-auto space-y-1">
                      {(testAllResults.results || []).map((r: any) => (
                        <div key={r.model} className={cn(
                          "flex items-center justify-between px-2 py-1.5 rounded text-[11px] border",
                          r.status === "ok" ? "border-emerald-900/40 bg-emerald-950/20" : "border-red-900/40 bg-red-950/20"
                        )}>
                          <div className="flex items-center gap-2 min-w-0">
                            <span className={r.status === "ok" ? "text-emerald-400" : "text-red-400"}>
                              {r.status === "ok" ? <CheckCircle2 className="inline w-3.5 h-3.5" /> : <XCircle className="inline w-3.5 h-3.5" />}
                            </span>
                            <span className="text-zinc-300 truncate font-mono">{r.model}</span>
                          </div>
                          <span className="text-[10px] text-zinc-600 shrink-0 ml-2">
                            {r.latency || (r.error ? r.error.slice(0, 20) : "")}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : testAllResults?.error ? (
                  <p className="text-[11px] text-red-400">{testAllResults.error}</p>
                ) : (
                  <p className="text-[11px] text-zinc-600">Klik "Test All" untuk cek semua model sekaligus.</p>
                )}
              </Card>
            </div>
          </div>
          </div>
        )}

        {tab === "telegram" && isSuperadmin && (
          <div className="max-w-5xl space-y-4">
            <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-3.5 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2.5">
                <Bot className="h-4 w-4 text-violet-400 shrink-0" />
                <span className="text-zinc-300">
                  Konfigurasi Bot Telegram @AutoCliperBot, routing webhook/polling, serta scheduler social media auto-posting.
                </span>
              </div>
              <Badge variant="default" className="text-[10px]">Superadmin Access</Badge>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Left Column: Configuration & Triggers */}
            <div className="space-y-4">
              {/* Integration Status & Master Switch */}
              <Card className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      "h-9 w-9 rounded-lg flex items-center justify-center transition-colors",
                      telegramSettings.is_enabled ? "bg-emerald-500/10 text-emerald-400" : "bg-zinc-800 text-zinc-500"
                    )}>
                      <Bot className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold text-zinc-100">Telegram Bot Integration</h3>
                        <Badge variant={telegramSettings.is_enabled ? "success" : "default"} size="sm">
                          {telegramSettings.is_enabled ? "Active" : "Disabled"}
                        </Badge>
                        {telegramSettings.bot_username && (
                          <Badge variant="default" size="sm">
                            @{telegramSettings.bot_username}
                          </Badge>
                        )}
                      </div>
                      <p className="text-[11px] text-zinc-500 mt-0.5">
                        Kirim notifikasi rendering video, klip MP4, dan kendalikan bot via Hermes agent.
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setTelegramSettings((p) => ({ ...p, is_enabled: !p.is_enabled }))}
                    className={cn(
                      "shrink-0 w-11 h-6 rounded-full relative transition-colors cursor-pointer",
                      telegramSettings.is_enabled ? "bg-emerald-600" : "bg-zinc-700"
                    )}
                  >
                    <span
                      className={cn(
                        "absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform",
                        telegramSettings.is_enabled && "translate-x-5"
                      )}
                    />
                  </button>
                </div>
              </Card>

              {/* Bot Credentials & Target IDs */}
              <Card className="p-4 space-y-3">
                <div className="flex items-center gap-2 mb-1">
                  <Key className="h-4 w-4 text-emerald-400" />
                  <h3 className="text-xs font-semibold text-zinc-200">Bot Credentials &amp; Targets</h3>
                </div>

                <div>
                  <label className="text-[11px] font-medium text-zinc-400 block mb-1">Bot Token (dari @BotFather)</label>
                  <div className="relative">
                    <input
                      type={showBotToken ? "text" : "password"}
                      value={telegramSettings.bot_token}
                      onChange={(e) => setTelegramSettings((p) => ({ ...p, bot_token: e.target.value }))}
                      placeholder="1234567890:ABCdefGHIjklMNO..."
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs font-mono text-zinc-200 placeholder:text-zinc-600 focus:border-emerald-500 focus:outline-none pr-9"
                    />
                    <button
                      type="button"
                      onClick={() => setShowBotToken(!showBotToken)}
                      className="absolute right-2.5 top-2.5 text-zinc-500 hover:text-zinc-300"
                    >
                      {showBotToken ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] font-medium text-zinc-400 block mb-1">Personal Chat ID</label>
                    <input
                      type="text"
                      value={telegramSettings.chat_id}
                      onChange={(e) => setTelegramSettings((p) => ({ ...p, chat_id: e.target.value }))}
                      placeholder="123456789"
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs font-mono text-zinc-200 placeholder:text-zinc-600 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-zinc-400 block mb-1">Group ID (diawali -100)</label>
                    <input
                      type="text"
                      value={telegramSettings.group_id}
                      onChange={(e) => setTelegramSettings((p) => ({ ...p, group_id: e.target.value }))}
                      placeholder="-1001234567890"
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs font-mono text-zinc-200 placeholder:text-zinc-600 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] font-medium text-zinc-400 block mb-1">Channel ID (diawali -100)</label>
                    <input
                      type="text"
                      value={telegramSettings.channel_id}
                      onChange={(e) => setTelegramSettings((p) => ({ ...p, channel_id: e.target.value }))}
                      placeholder="-1009876543210"
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs font-mono text-zinc-200 placeholder:text-zinc-600 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-zinc-400 block mb-1">Topic / Thread ID (Opsional)</label>
                    <input
                      type="text"
                      value={telegramSettings.topic_id}
                      onChange={(e) => setTelegramSettings((p) => ({ ...p, topic_id: e.target.value }))}
                      placeholder="123 (untuk supergroup topic)"
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs font-mono text-zinc-200 placeholder:text-zinc-600 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-[11px] font-medium text-zinc-400 block mb-1">Broadcast Target</label>
                  <Select
                    value={telegramSettings.notify_target}
                    onChange={(e) => setTelegramSettings((p) => ({ ...p, notify_target: e.target.value }))}
                    options={[
                      { value: "all", label: "Kirim ke Semua Target yang Dikonfigurasi" },
                      { value: "chat", label: "Hanya Chat ID Personal" },
                      { value: "group", label: "Hanya Group ID" },
                      { value: "channel", label: "Hanya Channel ID" },
                    ]}
                  />
                </div>

                <div>
                  <label className="text-[11px] font-medium text-zinc-400 block mb-1">Allowed User IDs (Hermes Bot Access)</label>
                  <input
                    type="text"
                    value={telegramSettings.allowed_users}
                    onChange={(e) => setTelegramSettings((p) => ({ ...p, allowed_users: e.target.value }))}
                    placeholder="123456789, 987654321 (pisah koma)"
                    className="w-full rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs font-mono text-zinc-200 placeholder:text-zinc-600 focus:border-emerald-500 focus:outline-none"
                  />
                  <p className="text-[10px] text-zinc-600 mt-1">Kosongkan jika bot boleh diakses oleh siapa saja yang memiliki akses bot.</p>
                </div>
              </Card>

              {/* Notification & Media Delivery Settings */}
              <Card className="p-4 space-y-2">
                <div className="flex items-center gap-2 mb-2">
                  <Bell className="h-4 w-4 text-emerald-400" />
                  <h3 className="text-xs font-semibold text-zinc-200">Notification &amp; Delivery Triggers</h3>
                </div>

                <FeatureToggle
                  icon={<Zap className="h-3.5 w-3.5" />}
                  label="Notifikasi Job Dimulai"
                  desc="Kirim pesan status saat video mulai diproses"
                  active={telegramSettings.notify_on_job_start}
                  onToggle={() => setTelegramSettings((p) => ({ ...p, notify_on_job_start: !p.notify_on_job_start }))}
                />

                <FeatureToggle
                  icon={<CheckCircle2 className="h-3.5 w-3.5" />}
                  label="Notifikasi Job Selesai"
                  desc="Kirim rangkuman klip dan skor viralitas saat rendering selesai"
                  active={telegramSettings.notify_on_job_complete}
                  onToggle={() => setTelegramSettings((p) => ({ ...p, notify_on_job_complete: !p.notify_on_job_complete }))}
                />

                <FeatureToggle
                  icon={<AlertTriangle className="h-3.5 w-3.5" />}
                  label="Notifikasi Job Gagal"
                  desc="Kirim peringatan error jika proses clipping/render mengalami kegagalan"
                  active={telegramSettings.notify_on_job_failed}
                  onToggle={() => setTelegramSettings((p) => ({ ...p, notify_on_job_failed: !p.notify_on_job_failed }))}
                />

                <FeatureToggle
                  icon={<Video className="h-3.5 w-3.5" />}
                  label="Kirim File Video MP4 Langsung"
                  desc="Upload video klip 9:16 langsung ke Telegram (maks 50MB per video)"
                  active={telegramSettings.send_video_files}
                  onToggle={() => setTelegramSettings((p) => ({ ...p, send_video_files: !p.send_video_files }))}
                />

                <FeatureToggle
                  icon={<Film className="h-3.5 w-3.5" />}
                  label="Sertakan Hashtag &amp; Caption AI"
                  desc="Tambahkan tag #fyp #viral dan hook title pada caption video"
                  active={telegramSettings.include_hashtags}
                  onToggle={() => setTelegramSettings((p) => ({ ...p, include_hashtags: !p.include_hashtags }))}
                />
              </Card>

              {/* AI Auto-Post to Social Media */}
              <Card className="p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Send className="h-4 w-4 text-emerald-400" />
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-xs font-semibold text-zinc-200">AI Auto-Post ke Media Sosial</h3>
                        <Badge variant={telegramSettings.auto_post_social ? "success" : "default"} size="sm">
                          {telegramSettings.auto_post_social ? "Aktif" : "Nonaktif"}
                        </Badge>
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setTelegramSettings((p) => ({ ...p, auto_post_social: !p.auto_post_social }))}
                    className={cn(
                      "shrink-0 w-8 h-4 rounded-full relative transition-colors cursor-pointer",
                      telegramSettings.auto_post_social ? "bg-emerald-600" : "bg-zinc-700"
                    )}
                  >
                    <span
                      className={cn(
                        "absolute top-0.5 left-0.5 h-3 w-3 rounded-full bg-white transition-transform",
                        telegramSettings.auto_post_social && "translate-x-4"
                      )}
                    />
                  </button>
                </div>

                <p className="text-[11px] text-zinc-500">
                  Secara otomatis menjadwalkan dan memposting setiap klip video ke akun sosial media terpilih menggunakan jam tayang cerdas (AI Peak-Hour Scheduling).
                </p>

                {/* Target Platforms Selector */}
                <div className="space-y-1.5 pt-1">
                  <div className="flex items-center justify-between">
                    <label className="text-[11px] font-medium text-zinc-400">Platform Target:</label>
                    <span className="text-[10px] text-zinc-500">
                      {telegramSocialAccounts.length} akun terhubung
                    </span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                    {[
                      { code: "tiktok", name: "TikTok" },
                      { code: "instagram", name: "Instagram" },
                      { code: "youtube", name: "YouTube Shorts" },
                      { code: "facebook", name: "Facebook" },
                      { code: "threads", name: "Threads" },
                      { code: "linkedin", name: "LinkedIn" },
                    ].map((plat) => {
                      const currentList = telegramSettings.auto_post_platforms
                        ? telegramSettings.auto_post_platforms.split(",").map((p) => p.trim().toLowerCase())
                        : [];
                      const isSelected = currentList.includes(plat.code);
                      const matchingAccounts = telegramSocialAccounts.filter(
                        (a) => a.platform?.toLowerCase() === plat.code
                      );
                      const hasAccount = matchingAccounts.length > 0;

                      return (
                        <button
                          key={plat.code}
                          type="button"
                          onClick={() => {
                            let updated: string[];
                            if (isSelected) {
                              updated = currentList.filter((p) => p !== plat.code);
                            } else {
                              updated = [...currentList, plat.code];
                            }
                            setTelegramSettings((p) => ({ ...p, auto_post_platforms: updated.join(",") }));
                          }}
                          className={cn(
                            "flex items-center justify-between px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-all text-left",
                            isSelected
                              ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-300"
                              : "border-zinc-800 bg-zinc-950/40 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
                          )}
                        >
                          <div className="flex items-center gap-1.5 min-w-0">
                            <div className={cn(
                              "w-3 h-3 rounded flex items-center justify-center border text-[9px] shrink-0",
                              isSelected ? "border-emerald-400 bg-emerald-500 text-white" : "border-zinc-600"
                            )}>
                              {isSelected && <Check className="w-2.5 h-2.5" />}
                            </div>
                            <span className="truncate">{plat.name}</span>
                          </div>
                          {hasAccount ? (
                            <span className="text-[8px] bg-emerald-500/20 text-emerald-400 px-1 py-0.2 rounded font-mono shrink-0">
                              {matchingAccounts.length}
                            </span>
                          ) : (
                            <span className="text-[8px] text-zinc-600 shrink-0">0</span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                  <div>
                    <label className="text-[11px] font-medium text-zinc-400 block mb-1">Mode Jadwal Posting</label>
                    <Select
                      value={telegramSettings.auto_post_schedule_mode}
                      onChange={(e) => setTelegramSettings((p) => ({ ...p, auto_post_schedule_mode: e.target.value }))}
                      options={[
                        { value: "ai", label: "AI Smart Peak Hours (Disarankan)" },
                        { value: "custom", label: "Custom Jam Tayang / Manual" },
                        { value: "instant", label: "Instant (1-2 Menit ke Depan)" },
                      ]}
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-zinc-400 block mb-1">Interval Antar Klip (Jam)</label>
                    <input
                      type="number"
                      min={1}
                      max={24}
                      value={telegramSettings.auto_post_interval_hours}
                      onChange={(e) => setTelegramSettings((p) => ({ ...p, auto_post_interval_hours: parseInt(e.target.value) || 4 }))}
                      className="w-full rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs text-zinc-200 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-[11px] font-medium text-zinc-400 block mb-1">Jam Tayang Utama (Peak Hours)</label>
                  <input
                    type="text"
                    value={telegramSettings.auto_post_peak_hours}
                    onChange={(e) => setTelegramSettings((p) => ({ ...p, auto_post_peak_hours: e.target.value }))}
                    placeholder="11:30, 15:00, 18:30, 20:30"
                    className="w-full rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs font-mono text-zinc-200 placeholder:text-zinc-600 focus:border-emerald-500 focus:outline-none"
                  />
                  <p className="text-[10px] text-zinc-600 mt-1">
                    Caption, judul hook, dan hashtag otomatis diekstrak dari JSON metadata video klip.
                  </p>
                </div>
              </Card>
            </div>

            {/* Right Column: Live Testing, Diagnostics & Bot Commands */}
            <div className="space-y-4">
              {/* Test & Diagnostics Card */}
              <Card className="p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Radio className="h-4 w-4 text-emerald-400" />
                    <h3 className="text-xs font-semibold text-zinc-200">Bot Diagnostics &amp; Live Test</h3>
                  </div>
                  <div className="flex gap-1.5">
                    <Button
                      size="xs"
                      variant="outline"
                      onClick={handleTestTelegram}
                      loading={isTestingTelegram}
                      icon={<Zap className="h-3 w-3" />}
                    >
                      Ping Test
                    </Button>
                    <Button
                      size="xs"
                      variant="outline"
                      onClick={handleTestTelegramVideo}
                      loading={isTestingTelegramVideo}
                      icon={<Video className="h-3 w-3" />}
                    >
                      Send Sample MP4
                    </Button>
                  </div>
                </div>

                {telegramTestResult ? (
                  <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-zinc-300 font-medium">Status Koneksi:</span>
                      <Badge variant={telegramTestResult.success ? "success" : "error"} size="sm">
                        {telegramTestResult.success ? "Bot Valid" : "Gagal"}
                      </Badge>
                    </div>
                    {telegramTestResult.bot_name && (
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-zinc-500">Nama Bot:</span>
                        <span className="text-zinc-200 font-medium">{telegramTestResult.bot_name} (@{telegramTestResult.bot_username})</span>
                      </div>
                    )}
                    {telegramTestResult.latency_ms !== undefined && (
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-zinc-500">Latency API:</span>
                        <span className="text-emerald-400 font-mono">{telegramTestResult.latency_ms}ms</span>
                      </div>
                    )}
                    {telegramTestResult.destination && (
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-zinc-500">Target Chat/Group:</span>
                        <span className="text-zinc-300 font-mono">{telegramTestResult.destination}</span>
                      </div>
                    )}
                    {telegramTestResult.message_sent && (
                      <div className="text-[10px] text-emerald-400 flex items-center gap-1 mt-1">
                        <Check className="h-3 w-3" /> Pesan uji coba berhasil dikirim ke target
                      </div>
                    )}
                    {telegramTestResult.send_error && (
                      <div className="text-[10px] text-amber-400 mt-1">
                        Peringatan pengiriman: {telegramTestResult.send_error}
                      </div>
                    )}
                    {telegramTestResult.error && (
                      <div className="text-[10px] text-red-400 mt-1">
                        Error: {telegramTestResult.error}
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-[11px] text-zinc-500">
                    Gunakan tombol Ping Test untuk memverifikasi bot token Telegram dan target chat ID sebelum menyimpan.
                  </p>
                )}
              </Card>

              {/* Bot Commands Quick Reference */}
              <Card className="p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 text-emerald-400" />
                  <h3 className="text-xs font-semibold text-zinc-200">Perintah Bot Telegram (@AutoCliperBot)</h3>
                </div>
                <p className="text-[11px] text-zinc-500">
                  Bot Telegram terhubung dengan Hermes AI agent untuk mengontrol AutoCliper secara interaktif:
                </p>

                <div className="space-y-1.5">
                  {[
                    { cmd: "/start", desc: "Mulai dan buka menu interaktif" },
                    { cmd: "/viral gym motivation", desc: "Cari video YouTube viral berdasar topik" },
                    { cmd: "/submit https://youtu.be/xxx", desc: "Submit video URL ke pipeline render" },
                    { cmd: "/presets", desc: "Lihat daftar style subtitle & template" },
                    { cmd: "/status <job_id>", desc: "Cek progress real-time per klip" },
                    { cmd: "/jobs", desc: "Daftar job terbaru dengan paginasi" },
                    { cmd: "/model grok", desc: "Ganti model AI LLM yang aktif" },
                    { cmd: "/id", desc: "Lihat User ID Telegram Anda" },
                  ].map((item) => (
                    <div
                      key={item.cmd}
                      onClick={() => handleCopyCommand(item.cmd)}
                      className="group flex items-center justify-between rounded-lg border border-zinc-800/60 bg-zinc-950/40 px-2.5 py-1.5 hover:border-zinc-700 hover:bg-zinc-900/50 cursor-pointer transition-colors"
                    >
                      <div className="min-w-0 flex items-center gap-2">
                        <code className="text-[11px] text-emerald-400 font-mono font-medium">{item.cmd}</code>
                        <span className="text-[10px] text-zinc-500 truncate">{item.desc}</span>
                      </div>
                      <span className="text-[9px] text-zinc-600 group-hover:text-zinc-400 shrink-0 ml-2">
                        {copiedCmd === item.cmd ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>

              {/* Service Deployment Guide */}
              <Card className="p-4 space-y-2">
                <div className="flex items-center gap-2 mb-1">
                  <Terminal className="h-4 w-4 text-zinc-400" />
                  <h3 className="text-xs font-semibold text-zinc-200">Systemd Daemon Service</h3>
                </div>
                <p className="text-[11px] text-zinc-500">
                  Untuk menjalankan bot Telegram sebagai background service di server VPS/Linux:
                </p>
                <div className="rounded-lg bg-zinc-950 p-2.5 border border-zinc-800 text-[10px] font-mono text-zinc-300 space-y-1">
                  <p className="text-zinc-500"># Deploy service</p>
                  <p className="text-emerald-400">bash scripts/setup-telegram-bot.sh</p>
                  <p className="text-zinc-500 mt-2"># Cek status &amp; logs</p>
                  <p>systemctl status autocliper-telegram-bot</p>
                  <p>journalctl -u autocliper-telegram-bot -f</p>
                </div>
              </Card>
            </div>
          </div>
          </div>
        )}

        {tab === "testing" && isSuperadmin && (
          <div className="max-w-5xl space-y-4">
            <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-3.5 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2.5">
                <Terminal className="h-4 w-4 text-emerald-400 shrink-0" />
                <span className="text-zinc-300">
                  Server Automated Test Suite: Menjalankan unit test backend & frontend, Remotion render check, dan smoke test video preview.
                </span>
              </div>
              <Badge variant="default" className="text-[10px]">Superadmin Access</Badge>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="space-y-4">
              <Card className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <Terminal className="h-4 w-4 text-emerald-400" />
                      <h3 className="text-sm font-semibold text-zinc-100">Server Test Gate</h3>
                      {testStatus && (
                        <Badge
                          variant={testStatus.status === "passed" ? "success" : testStatus.status === "failed" ? "error" : testStatus.status === "running" || testStatus.status === "deploying" ? "warning" : "default"}
                          dot
                        >
                          {testStatus.status}
                        </Badge>
                      )}
                    </div>
                    <p className="text-[11px] text-zinc-500">
                      Menjalankan backend, frontend, Remotion, build, dan smoke test clip_01.mp4.
                    </p>
                  </div>
                  <Button
                    size="sm"
                    onClick={handleStartTest}
                    loading={isStartingTest}
                    disabled={testStatus?.status === "running" || testStatus?.status === "deploying"}
                    icon={<Play className="h-3.5 w-3.5" />}
                  >
                    Run Tests
                  </Button>
                </div>

                <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
                  <div className="flex items-center gap-2">
                    {testStatus?.status === "passed" ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> :
                      testStatus?.status === "failed" ? <XCircle className="h-4 w-4 text-red-400" /> :
                        <RefreshCw className={cn("h-4 w-4 text-amber-400", testStatus?.status === "running" && "animate-spin")} />}
                    <div>
                      <p className="text-xs font-medium text-zinc-200">{testStatus?.stage || "Not started"}</p>
                      <p className="text-[10px] text-zinc-500">{testStatus?.message || "Click Run Tests to begin"}</p>
                    </div>
                  </div>
                  <p className="mt-2 text-[10px] text-zinc-600">
                    Trigger dari halaman ini memakai --no-deploy. Jalankan ./test.sh via SSH untuk test lalu deploy otomatis.
                  </p>
                </div>
              </Card>

              <Card className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-semibold text-zinc-200">Testing Log</h3>
                  <span className="text-[10px] text-zinc-600">logs/test.log</span>
                </div>
                <pre data-testid="test-run-log" className="h-[420px] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-black p-3 font-mono text-[10px] leading-relaxed text-zinc-300 border border-zinc-800">
                  {testLog || "Belum ada log testing."}
                </pre>
              </Card>
            </div>

            <Card className="p-4 self-start">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h3 className="text-xs font-semibold text-zinc-200">Result Preview</h3>
                  <p className="text-[10px] text-zinc-600">clip_test_final.mp4</p>
                </div>
                {testStatus?.video_available && <Badge variant="success">Ready</Badge>}
              </div>
              {testVideoUrl ? (
                <video data-testid="test-video-preview" src={testVideoUrl} controls preload="metadata" className="w-full max-h-[680px] rounded-lg bg-black" />
              ) : (
                <div className="aspect-[9/16] max-h-[620px] rounded-lg border border-dashed border-zinc-700 bg-zinc-950/40 flex items-center justify-center">
                  <div className="text-center px-6">
                    <Film className="h-8 w-8 text-zinc-700 mx-auto mb-2" />
                    <p className="text-xs text-zinc-500">Preview belum tersedia</p>
                    <p className="text-[10px] text-zinc-700 mt-1">Video muncul setelah smoke test berhasil.</p>
                  </div>
                </div>
              )}
            </Card>
          </div>
          </div>
        )}

        {tab === "autopilot" && (
          <div className="space-y-4">
            {/* Header info banner */}
            <div className="rounded-xl border border-violet-500/30 bg-gradient-to-r from-violet-950/40 via-indigo-950/30 to-zinc-900/60 p-4 flex flex-wrap items-center justify-between gap-3 shadow-lg">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-violet-500/10 border border-violet-500/30 flex items-center justify-center text-violet-300">
                  <Bot className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-zinc-100 flex items-center gap-2">
                    Hermes Autopilot — Autonomous Video Discovery &amp; Auto-Post
                    <Badge variant="default" className="text-[9px] uppercase font-bold text-violet-300 border-violet-500/30 bg-violet-500/10">
                      Maks. 1 Video/Hari
                    </Badge>
                  </h2>
                  <p className="text-[11px] text-zinc-400 mt-0.5">
                    Hermes AI mencari video YouTube viral setiap hari sesuai niche Anda, merender klip dengan preset 5 layer visual lengkap, dan otomatis menjadwalkan ke akun media sosial.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Badge
                  variant={autopilotCanRun ? "success" : "warning"}
                  className="px-3 py-1 text-xs font-semibold"
                >
                  {autopilotQuota ? `${autopilotQuota.today_runs}/${autopilotQuota.max_daily_videos} Video Hari Ini` : "Kuota Harian: 1 Video"}
                </Badge>
              </div>
            </div>

            {isLoadingAutopilot ? (
              <Card className="p-8 text-center">
                <RefreshCw className="h-6 w-6 text-violet-400 animate-spin mx-auto mb-2" />
                <p className="text-xs text-zinc-400">Memuat pengaturan Hermes Autopilot...</p>
              </Card>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
                {/* Left Column: Configuration */}
                <div className="lg:col-span-7 space-y-4">
                  {/* Master Switch Card */}
                  <Card className="p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          "h-10 w-10 rounded-xl flex items-center justify-center transition-colors border",
                          autopilotSettings?.enabled
                            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                            : "bg-zinc-800/80 border-zinc-700 text-zinc-500"
                        )}>
                          <Zap className="h-5 w-5" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-zinc-100">Hermes Autopilot Daemon</span>
                            <Badge variant={autopilotSettings?.enabled ? "success" : "default"}>
                              {autopilotSettings?.enabled ? "AKTIF" : "NONAKTIF"}
                            </Badge>
                          </div>
                          <p className="text-[11px] text-zinc-400 mt-0.5">
                            {autopilotSettings?.enabled
                              ? `Berjalan otomatis setiap hari pada jam ${autopilotSettings.run_time || "08:00"} WIB`
                              : "Otomasi nonaktif. Aktifkan sakelar untuk menjalankan pencarian dan posting harian otomatis."}
                          </p>
                        </div>
                      </div>

                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={autopilotSettings?.enabled || false}
                          onChange={(e) => {
                            if (autopilotSettings) {
                              setAutopilotSettings({ ...autopilotSettings, enabled: e.target.checked });
                            }
                          }}
                          className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-violet-600"></div>
                      </label>
                    </div>
                  </Card>

                  {/* Niche & Search Settings */}
                  <Card className="p-4 space-y-3">
                    <div className="flex items-center gap-2">
                      <Film className="h-4 w-4 text-violet-400" />
                      <h3 className="text-xs font-semibold text-zinc-200">1. Niche &amp; Topik Pencarian YouTube Viral</h3>
                    </div>

                    <div>
                      <label className="text-[11px] text-zinc-400 block mb-1">Keywords / Niche Query</label>
                      <Input
                        value={autopilotSettings?.niche_query || ""}
                        onChange={(e) => {
                          if (autopilotSettings) {
                            setAutopilotSettings({ ...autopilotSettings, niche_query: e.target.value });
                          }
                        }}
                        placeholder="Contoh: podcast bisnis, motivasi indonesia, tips trading crypto"
                      />
                    </div>

                    {/* Quick Niche Pills */}
                    <div>
                      <span className="text-[10px] text-zinc-500 block mb-1.5">Rekomendasi Niche Cepat:</span>
                      <div className="flex flex-wrap gap-1.5">
                        {[
                          "podcast bisnis",
                          "motivasi hidup",
                          "tips investasi saham",
                          "gym motivation",
                          "ai tech news",
                          "self improvement",
                        ].map((niche) => (
                          <button
                            key={niche}
                            type="button"
                            onClick={() => {
                              if (autopilotSettings) {
                                setAutopilotSettings({ ...autopilotSettings, niche_query: niche });
                              }
                            }}
                            className={cn(
                              "px-2 py-0.5 rounded-md text-[10px] font-medium border transition-colors",
                              autopilotSettings?.niche_query === niche
                                ? "bg-violet-500/20 border-violet-500/50 text-violet-300"
                                : "bg-zinc-800/60 border-zinc-700/60 text-zinc-400 hover:text-zinc-200"
                            )}
                          >
                            + {niche}
                          </button>
                        ))}
                      </div>
                    </div>
                  </Card>

                  {/* Visual Style Preset Selection & Live 5-Layer Preview */}
                  <Card className="p-4">
                    <AutopilotPresetPreview
                      selectedSlug={autopilotSettings?.preset_slug || "default"}
                      onSelectSlug={(slug) => {
                        if (autopilotSettings) {
                          setAutopilotSettings({ ...autopilotSettings, preset_slug: slug });
                        }
                      }}
                      presets={autopilotPresets}
                      onOpenEditor={() => setShowStyleModal(true)}
                    />
                  </Card>

                  {/* Social Media Target & Schedule Time */}
                  <Card className="p-4 space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Globe className="h-4 w-4 text-violet-400" />
                        <h3 className="text-xs font-semibold text-zinc-200">3. Target Platform Auto-Post &amp; Waktu Jalan</h3>
                      </div>
                      <Link
                        to="/social"
                        className="text-[11px] text-violet-400 hover:text-violet-300 flex items-center gap-1 hover:underline"
                      >
                        <span>Kelola Akun Sosial</span>
                        <ExternalLink className="h-3 w-3" />
                      </Link>
                    </div>

                    <p className="text-[11px] text-zinc-400">
                      Hanya platform yang sudah terhubung di menu Social Accounts yang dapat dipilih. Platform yang belum terhubung akan berstatus readonly sampai akun Anda hubungkan.
                    </p>

                    {/* Platform Checkboxes & Multi-Account Breakdown */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 pt-1">
                      {[
                        { id: "tiktok", name: "TikTok" },
                        { id: "instagram", name: "Instagram Reels" },
                        { id: "youtube", name: "YouTube Shorts" },
                        { id: "facebook", name: "Facebook" },
                        { id: "threads", name: "Threads" },
                        { id: "linkedin", name: "LinkedIn" },
                      ].map((plat) => {
                        const platInfo = getAutopilotPlatInfo(plat.id);
                        const isConnected = platInfo.connected;
                        const currentPlats = (autopilotSettings?.target_platforms || "").toLowerCase().split(",").map(p => p.trim());
                        const isChecked = isConnected && currentPlats.includes(plat.id);

                        return (
                          <div
                            key={plat.id}
                            className={cn(
                              "p-3 rounded-xl border text-xs transition-all flex flex-col justify-between",
                              !isConnected
                                ? "bg-zinc-950/40 border-zinc-800/60 opacity-60 cursor-not-allowed"
                                : isChecked
                                ? "bg-violet-950/30 border-violet-500/50 text-violet-200 shadow-sm"
                                : "bg-zinc-900/50 border-zinc-800 text-zinc-400 hover:border-zinc-700"
                            )}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <label className={cn("flex items-center gap-2 select-none", isConnected ? "cursor-pointer" : "cursor-not-allowed")}>
                                <input
                                  type="checkbox"
                                  disabled={!isConnected}
                                  checked={isChecked}
                                  onChange={(e) => {
                                    if (!autopilotSettings || !isConnected) return;
                                    let updated: string[];
                                    if (e.target.checked) {
                                      updated = Array.from(new Set([...currentPlats, plat.id]));
                                    } else {
                                      updated = currentPlats.filter(p => p !== plat.id);
                                    }
                                    setAutopilotSettings({
                                      ...autopilotSettings,
                                      target_platforms: updated.filter(Boolean).join(","),
                                    });
                                  }}
                                  className="rounded border-zinc-700 text-violet-600 focus:ring-violet-500 h-3.5 w-3.5 disabled:opacity-40"
                                />
                                <span className={cn("font-medium truncate", !isConnected ? "text-zinc-500" : isChecked ? "text-violet-200" : "text-zinc-300")}>
                                  {plat.name}
                                </span>
                              </label>

                              {isConnected ? (
                                <span className="text-[9px] bg-emerald-500/10 text-emerald-400 px-1.5 py-0.5 rounded border border-emerald-500/20 font-medium shrink-0">
                                  {platInfo.count} Akun
                                </span>
                              ) : (
                                <Link
                                  to="/social"
                                  className="inline-flex items-center gap-1 text-[9px] text-amber-400 hover:text-amber-300 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20 shrink-0"
                                >
                                  <span>Belum Terhubung</span>
                                  <ExternalLink className="h-2.5 w-2.5" />
                                </Link>
                              )}
                            </div>

                            {/* Multi-Account Selector when platform has multiple accounts & is checked */}
                            {isConnected && isChecked && platInfo.accounts.length > 1 && (
                              <div className="mt-2.5 pt-2 border-t border-zinc-800/80 space-y-1.5 pl-5">
                                <span className="text-[10px] text-zinc-400 font-medium block">Pilih Akun {plat.name}:</span>
                                <div className="space-y-1 max-h-32 overflow-y-auto pr-1">
                                  {platInfo.accounts.map((acc: any) => {
                                    const accId = String(acc.account_id || acc.id || acc._id);
                                    const currentAccIds = Array.isArray(autopilotSettings?.target_account_ids)
                                      ? autopilotSettings.target_account_ids
                                      : [];
                                    const isAccSelected = currentAccIds.length === 0 || currentAccIds.includes(accId);

                                    return (
                                      <label key={accId} className="flex items-center gap-2 text-[10px] text-zinc-300 hover:text-zinc-100 cursor-pointer select-none">
                                        <input
                                          type="checkbox"
                                          checked={isAccSelected}
                                          onChange={(e) => {
                                            if (!autopilotSettings) return;
                                            let updatedAccs: string[];
                                            if (e.target.checked) {
                                              updatedAccs = currentAccIds.length === 0
                                                ? [accId]
                                                : Array.from(new Set([...currentAccIds, accId]));
                                            } else {
                                              const allPlatIds = platInfo.accounts.map((a: any) => String(a.account_id || a.id || a._id));
                                              const baseList = currentAccIds.length === 0 ? allPlatIds : currentAccIds;
                                              updatedAccs = baseList.filter((id: string) => id !== accId);
                                            }
                                            setAutopilotSettings({
                                              ...autopilotSettings,
                                              target_account_ids: updatedAccs,
                                            });
                                          }}
                                          className="rounded border-zinc-700 bg-zinc-800 text-violet-500 focus:ring-violet-500/30 h-3 w-3"
                                        />
                                        <span className="truncate">{acc.name || acc.username} {acc.username ? `(@${acc.username})` : ""}</span>
                                      </label>
                                    );
                                  })}
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-zinc-800/80">
                      <div>
                        <label className="text-[11px] text-zinc-400 block mb-1">Jam Eksekusi Harian (WIB)</label>
                        <Input
                          type="time"
                          value={autopilotSettings?.run_time || "08:00"}
                          onChange={(e) => {
                            if (autopilotSettings) {
                              setAutopilotSettings({ ...autopilotSettings, run_time: e.target.value });
                            }
                          }}
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-zinc-400 block mb-1">Mode Jadwal Post</label>
                        <Select
                          value={autopilotSettings?.schedule_mode || "ai"}
                          onChange={(e) => {
                            if (autopilotSettings) {
                              setAutopilotSettings({ ...autopilotSettings, schedule_mode: e.target.value });
                            }
                          }}
                          options={[
                            { value: "ai", label: "AI Same-Day Spread (Semua video hari ini disebar berkala di jam berbeda)" },
                            { value: "instant", label: "Instant Post (Langsung tayang saat render selesai)" },
                            { value: "custom", label: "Custom Schedule Time (Interval manual)" },
                          ]}
                        />
                      </div>
                    </div>
                  </Card>
                </div>

                {/* Right Column: Today's Status & History */}
                <div className="lg:col-span-5 space-y-4">
                  {/* Today Run Trigger Card */}
                  <Card className="p-4 border-violet-500/20 bg-gradient-to-b from-violet-950/20 to-zinc-900/60">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-semibold text-zinc-200 flex items-center gap-1.5">
                        <Activity className="h-3.5 w-3.5 text-violet-400" />
                        Status Kuota Hari Ini
                      </span>
                      <Badge variant={autopilotCanRun ? "success" : "default"}>
                        {autopilotQuota ? `${autopilotQuota.today_runs}/${autopilotQuota.max_daily_videos} Video` : "1 Video/Hari"}
                      </Badge>
                    </div>

                    <div className="p-3 rounded-lg bg-zinc-900/80 border border-zinc-800 space-y-2 mb-3">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-zinc-400">Status Kesiapan:</span>
                        <span className={cn("font-medium flex items-center gap-1", autopilotCanRun ? "text-emerald-400" : "text-amber-400")}>
                          {autopilotCanRun ? (
                            <>
                              <CheckCircle2 className="h-3.5 w-3.5" />
                              <span>Siap Eksekusi</span>
                            </>
                          ) : (
                            <>
                              <Clock className="h-3.5 w-3.5" />
                              <span>Kuota Hari Ini Terpenuhi</span>
                            </>
                          )}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-zinc-400">Jadwal Harian:</span>
                        <span className="text-zinc-200">{autopilotSettings?.run_time || "08:00"} WIB</span>
                      </div>
                      {autopilotSettings?.last_video_title && (
                        <div className="pt-1 border-t border-zinc-800/80">
                          <span className="text-[10px] text-zinc-500 block mb-0.5">Video Terakhir:</span>
                          <p className="text-xs text-zinc-300 line-clamp-2 font-medium">
                            {autopilotSettings.last_video_title}
                          </p>
                          {autopilotSettings.last_job_id && (
                            <span className="text-[10px] text-violet-400 font-mono mt-0.5 block">
                              Job #{autopilotSettings.last_job_id}
                            </span>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Button
                        onClick={() => handleTriggerAutopilot(false)}
                        loading={isRunningAutopilot}
                        disabled={!autopilotCanRun}
                        className="w-full"
                        variant="primary"
                        icon={<Play className="h-4 w-4" />}
                      >
                        {autopilotCanRun ? "Jalankan Autopilot Hari Ini (1 Video)" : "Kuota Hari Ini Selesai"}
                      </Button>

                      {!autopilotCanRun && (
                        <Button
                          onClick={() => handleTriggerAutopilot(true)}
                          loading={isRunningAutopilot}
                          className="w-full text-xs text-zinc-400 hover:text-zinc-200"
                          variant="ghost"
                          size="sm"
                        >
                          Paksa Jalankan Ulang (Force Run)
                        </Button>
                      )}
                    </div>
                  </Card>

                  {/* Recent Autopilot Runs */}
                  <Card className="p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-zinc-200 flex items-center gap-1.5">
                        <Film className="h-3.5 w-3.5 text-zinc-400" />
                        Riwayat Eksekusi Harian
                      </span>
                      <Button
                        onClick={loadAutopilotData}
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 text-[10px]"
                        icon={<RefreshCw className="h-2.5 w-2.5" />}
                      >
                        Refresh
                      </Button>
                    </div>

                    {autopilotHistory.length === 0 ? (
                      <div className="p-6 text-center text-xs text-zinc-500">
                        Belum ada riwayat eksekusi Autopilot.
                      </div>
                    ) : (
                      <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                        {autopilotHistory.map((run: any) => (
                          <div
                            key={run.id}
                            className="p-2.5 rounded-lg border border-zinc-800/80 bg-zinc-900/40 text-xs space-y-1"
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-semibold text-zinc-200 text-[11px] truncate max-w-[200px]" title={run.video_title}>
                                {run.video_title || "YouTube Video"}
                              </span>
                              <Badge variant={run.status === "completed" ? "success" : run.status === "submitted" ? "warning" : "error"} className="text-[9px]">
                                {run.status}
                              </Badge>
                            </div>
                            <div className="flex items-center justify-between text-[10px] text-zinc-400">
                              <span>Tanggal: {run.run_date}</span>
                              <span className="text-violet-400 font-mono">Job #{run.job_id}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </Card>
                </div>
              </div>
            )}
          </div>
        )}

        {tab === "system_config" && (
          <div className="max-w-6xl space-y-4">
            {/* Header info banner */}
            <div className="rounded-xl border border-violet-500/30 bg-gradient-to-r from-violet-950/40 via-indigo-950/30 to-zinc-900/60 p-4 flex flex-wrap items-center justify-between gap-3 shadow-lg">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-violet-500/10 border border-violet-500/30 flex items-center justify-center text-violet-300">
                  <HardDrive className="h-4 w-4" />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-zinc-100 flex items-center gap-2">
                    Dynamic Database &amp; Runtime Config (RBAC)
                    <Badge variant="default" className="text-[9px] uppercase font-bold text-violet-300 border-violet-500/30 bg-violet-500/10">
                      Live Settings
                    </Badge>
                  </h2>
                  <p className="text-[11px] text-zinc-400 mt-0.5">
                    Semua konfigurasi di bawah tersimpan di database dan berlaku langsung saat rendering tanpa perlu restart server.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {canEditSecrets && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const next = !sysConfigUnmask;
                      setSysConfigUnmask(next);
                      loadSystemConfig(next);
                    }}
                    icon={sysConfigUnmask ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  >
                    {sysConfigUnmask ? "Mask Secrets" : "Show Secrets"}
                  </Button>
                )}
                <Button
                  size="sm"
                  onClick={handleSaveSysConfig}
                  loading={isSavingSysConfig}
                  icon={<Save className="h-3.5 w-3.5" />}
                >
                  Save All Config
                </Button>
              </div>
            </div>

            {/* Filter & Search Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 bg-zinc-900/60 border border-zinc-800 p-3 rounded-xl">
              <div className="flex flex-wrap items-center gap-1.5">
                {[
                  { id: "all", label: "Semua Kategori" },
                  { id: "ai_llm", label: "AI & LLM" },
                  { id: "api_keys", label: "API Keys" },
                  { id: "render_limits", label: "Render & Limits" },
                  { id: "vision_reframe", label: "Vision & Reframe" },
                  { id: "broll_effects", label: "B-Roll & Effects" },
                  { id: "storage_cdn", label: "Storage & CDN" },
                ].map((cat) => (
                  <button
                    key={cat.id}
                    type="button"
                    onClick={() => setSysConfigCategory(cat.id)}
                    className={cn(
                      "px-3 py-1 rounded-lg text-xs font-medium transition-colors border",
                      sysConfigCategory === cat.id
                        ? "bg-violet-600 border-violet-500 text-white shadow"
                        : "bg-zinc-800/80 border-zinc-700 text-zinc-400 hover:text-zinc-200"
                    )}
                  >
                    {cat.label}
                  </button>
                ))}
              </div>

              <div className="w-full sm:w-64">
                <input
                  type="text"
                  value={sysConfigSearch}
                  onChange={(e) => setSysConfigSearch(e.target.value)}
                  placeholder="Cari nama setting / deskripsi..."
                  className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-violet-500"
                />
              </div>
            </div>

            {/* Settings Cards List */}
            {isLoadingSysConfig ? (
              <div className="p-8 text-center text-zinc-500 text-xs">
                <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2 text-violet-400" />
                Memuat konfigurasi sistem dari database...
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {sysConfigItems
                  .filter((item) => {
                    if (sysConfigCategory !== "all" && item.category !== sysConfigCategory) return false;
                    if (sysConfigSearch.trim()) {
                      const q = sysConfigSearch.toLowerCase();
                      return item.key.toLowerCase().includes(q) || (item.description || "").toLowerCase().includes(q);
                    }
                    return true;
                  })
                  .map((item) => {
                    const currentVal = sysConfigEdits[item.key] !== undefined ? sysConfigEdits[item.key] : item.value;
                    return (
                      <div
                        key={item.key}
                        className="rounded-xl border border-zinc-800/80 bg-zinc-900/50 p-3.5 space-y-2.5 flex flex-col justify-between hover:border-zinc-700 transition-colors"
                      >
                        <div className="space-y-1">
                          <div className="flex items-center justify-between gap-2">
                            <code className="text-xs font-mono font-bold text-violet-300 truncate" title={item.key}>
                              {item.key}
                            </code>
                            <div className="flex items-center gap-1 shrink-0">
                              <span className={cn(
                                "px-1.5 py-0.5 rounded text-[8px] font-bold uppercase border",
                                item.min_role === "superadmin" ? "bg-red-500/10 border-red-500/30 text-red-400" :
                                item.min_role === "editor" ? "bg-amber-500/10 border-amber-500/30 text-amber-400" :
                                "bg-zinc-800 border-zinc-700 text-zinc-400"
                              )}>
                                {item.min_role}
                              </span>
                              {item.is_secret && (
                                <span className="px-1.5 py-0.5 rounded text-[8px] font-bold uppercase bg-violet-500/10 border border-violet-500/30 text-violet-400">
                                  Secret
                                </span>
                              )}
                            </div>
                          </div>
                          <p className="text-[11px] text-zinc-400 leading-relaxed">{item.description}</p>
                        </div>

                        {/* Input editor based on data_type */}
                        <div className="pt-2 border-t border-zinc-800/60 flex items-center justify-between gap-3">
                          {item.data_type === "bool" ? (
                            <button
                              type="button"
                              onClick={() => {
                                const next = !currentVal;
                                setSysConfigEdits(prev => ({ ...prev, [item.key]: next }));
                              }}
                              className={cn(
                                "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none",
                                currentVal ? "bg-emerald-600" : "bg-zinc-700"
                              )}
                            >
                              <span
                                className={cn(
                                  "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out",
                                  currentVal ? "translate-x-4" : "translate-x-0"
                                )}
                              />
                            </button>
                          ) : item.data_type === "int" || item.data_type === "float" ? (
                            <input
                              type="number"
                              step={item.data_type === "float" ? "0.05" : "1"}
                              value={currentVal ?? ""}
                              onChange={(e) => {
                                const v = item.data_type === "float" ? parseFloat(e.target.value) : parseInt(e.target.value, 10);
                                setSysConfigEdits(prev => ({ ...prev, [item.key]: isNaN(v) ? e.target.value : v }));
                              }}
                              className="flex-1 bg-zinc-950 border border-zinc-700 rounded-lg px-2.5 py-1 text-xs text-zinc-200 font-mono focus:outline-none focus:border-violet-500"
                            />
                          ) : item.is_secret && !sysConfigUnmask ? (
                            <input
                              type="password"
                              value={currentVal ?? ""}
                              onChange={(e) => setSysConfigEdits(prev => ({ ...prev, [item.key]: e.target.value }))}
                              placeholder={item.value ? "••••••••••••" : "Belum diisi..."}
                              className="flex-1 bg-zinc-950 border border-zinc-700 rounded-lg px-2.5 py-1 text-xs text-zinc-200 font-mono focus:outline-none focus:border-violet-500"
                            />
                          ) : (
                            <input
                              type="text"
                              value={typeof currentVal === "object" ? JSON.stringify(currentVal) : (currentVal ?? "")}
                              onChange={(e) => setSysConfigEdits(prev => ({ ...prev, [item.key]: e.target.value }))}
                              className="flex-1 bg-zinc-950 border border-zinc-700 rounded-lg px-2.5 py-1 text-xs text-zinc-200 font-mono focus:outline-none focus:border-violet-500"
                            />
                          )}

                          {isSuperadmin && (
                            <button
                              type="button"
                              onClick={() => handleResetSysConfigKey(item.key)}
                              className="text-[10px] text-zinc-500 hover:text-red-400 shrink-0 transition-colors"
                              title="Reset ke default"
                            >
                              Reset
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
              </div>
            )}
          </div>
        )}

        {/* Style Editor Modal for Preset Customization */}
        {showStyleModal && (
          <StyleEditorModal
            open={showStyleModal}
            onClose={() => {
              setShowStyleModal(false);
              loadAutopilotData();
            }}
            hookStyle={editorHook}
            subtitleStyle={editorSub}
            textEmphasisStyle={editorTe}
            watermarkStyle={editorWm}
            ctaStyle={editorCta}
            onHookChange={setEditorHook}
            onSubtitleChange={setEditorSub}
            onTextEmphasisChange={setEditorTe}
            onWatermarkChange={setEditorWm}
            onCtaChange={setEditorCta}
            onPresetLoad={(preset) => {
              if (preset.slug && autopilotSettings) {
                setAutopilotSettings({ ...autopilotSettings, preset_slug: preset.slug });
              }
              loadAutopilotData();
            }}
            isSuperadmin={isSuperadmin}
          />
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
