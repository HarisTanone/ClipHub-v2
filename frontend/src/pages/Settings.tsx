import { useState, useEffect } from "react";
import { Save, Server, Cpu, Sparkles, Film, UserPlus, Trash2, AlertTriangle, Shield, Zap } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { system, storage, API_BASE, getToken } from "@/lib/api";
import { cn } from "@/lib/utils";

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
  { code: "smart_camera", name: "Smart Camera" },
  { code: "smart_subtitle_pos", name: "Smart Subtitle Position" },
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

// ─── Main ────────────────────────────────────────────────────────────────────

export function Settings() {
  const toast = useToast();
  const { user } = useAuth();
  const isSuperadmin = user?.is_superadmin || false;
  const [tab, setTab] = useState<"general" | "render" | "users">("general");
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

  useEffect(() => {
    system.health().then(setHealth).catch(() => null);
    fetchSettings().then((d) => { if (d) setSettings((p) => ({ ...p, ...d })); });
    fetchUsers().then(setUsers);
  }, []);

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

  const tabs = [
    { id: "general" as const, label: "General" },
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
        {tab !== "users" && (
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
                    V2 — Groq
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
      toast.success(`${u.email} → ${newValue ? "Premium (V1 Gemini)" : "Free (V2 Groq)"}`);
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
            {isPremium ? "Premium (V1 Gemini)" : "Free (V2 Groq)"}
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
