import { useState, useEffect } from "react";
import { X, Type, Sparkles, Bookmark, Trash2, Save, Download } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { FeatureLock } from "@/components/ui/FeatureLock";
import { presets as presetsApi, type Preset } from "@/lib/api";
import { cn } from "@/lib/utils";

function useGoogleFont(fontFamily: string) {
  useEffect(() => {
    if (!fontFamily || fontFamily === "monospace") return;
    const id = `gfont-${fontFamily.replace(/\s/g, "")}`;
    if (document.getElementById(id)) return;
    const link = document.createElement("link");
    link.id = id;
    link.rel = "stylesheet";
    link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(fontFamily)}:wght@400;500;600;700;800;900&display=swap`;
    document.head.appendChild(link);
  }, [fontFamily]);
}

// ─── Types ───────────────────────────────────────────────────────────────────

export interface HookStyle {
  animation: string;
  text: string;
  fontFamily: string;
  fontSize: number;
  fontWeight: string;
  letterSpacing: number;
  lineHeight: number;
  color: string;
  gradientEnabled: boolean;
  gradientFrom: string;
  gradientTo: string;
  gradientAngle: number;
  shadowEnabled: boolean;
  shadowColor: string;
  shadowBlur: number;
  shadowX: number;
  shadowY: number;
  glowEnabled: boolean;
  glowColor: string;
  glowSize: number;
  bgColor: string;
  bgOpacity: number;
  position: "center" | "top" | "bottom";
  positionY: number; // fine-tune vertical %
  textAlign: "center" | "left" | "right";
  uppercase: boolean;
  italic: boolean;
  // Accent line
  lineEnabled: boolean;
  linePosition: "top" | "bottom" | "left" | "right" | "center-h" | "center-v" | "auto-bottom";
  lineColor: string;
  lineWidth: number;
  lineAutoWidth: boolean;
  lineThickness: number;
  lineOffset: number;
  // Border/box around text
  boxEnabled: boolean;
  boxColor: string;
  boxOpacity: number;
  boxPadding: number;
  boxRadius: number;
  // Duration
  duration: number;
  fadeIn: number;
  fadeOut: number;
}

export interface SubtitleStyle {
  fontFamily: string;
  fontSize: number;
  fontWeight: string;
  letterSpacing: number;
  lineHeight: number;
  color: string;
  highlightColor: string;
  highlightScale: number;
  highlightBold: boolean;
  highlightStyle: "scale" | "underline" | "background" | "strikethrough";
  highlightGlow: boolean;
  highlightGlowColor: string;
  highlightWords: string[];
  // Dual style (optional — separate font/style for highlight words)
  dualStyleEnabled: boolean;
  highlightFontFamily: string;
  highlightFontSize: number;
  highlightFontWeight: string;
  highlightLetterSpacing: number;
  highlightItalic: boolean;
  highlightUppercase: boolean;
  highlightStrokeEnabled: boolean;
  highlightStrokeColor: string;
  highlightStrokeWidth: number;
  highlightShadowEnabled: boolean;
  highlightShadowColor: string;
  highlightShadowBlur: number;
  // Common
  bgEnabled: boolean;
  bgColor: string;
  bgOpacity: number;
  bgRadius: number;
  bgPadding: number;
  position: "bottom" | "center" | "top";
  positionY: number;
  uppercase: boolean;
  italic: boolean;
  strokeEnabled: boolean;
  strokeColor: string;
  strokeWidth: number;
  shadowEnabled: boolean;
  shadowColor: string;
  shadowBlur: number;
  maxWordsPerLine: number;
  wordSpacing: number;
  animationStyle: "pop" | "fade" | "slide" | "none";
  animationSpeed: number;
}

export const DEFAULT_HOOK_STYLE: HookStyle = {
  animation: "fade_scale",
  text: "",
  fontFamily: "Poppins",
  fontSize: 48,
  fontWeight: "800",
  letterSpacing: 0,
  lineHeight: 1.3,
  color: "#FFFFFF",
  gradientEnabled: false,
  gradientFrom: "#FFFFFF",
  gradientTo: "#FFCC00",
  gradientAngle: 180,
  shadowEnabled: true,
  shadowColor: "#000000",
  shadowBlur: 12,
  shadowX: 0,
  shadowY: 4,
  glowEnabled: false,
  glowColor: "#FFCC00",
  glowSize: 20,
  bgColor: "#000000",
  bgOpacity: 0.6,
  position: "center",
  positionY: 50,
  textAlign: "center",
  uppercase: false,
  italic: false,
  lineEnabled: false,
  linePosition: "bottom",
  lineColor: "#FFCC00",
  lineWidth: 60,
  lineAutoWidth: false,
  lineThickness: 4,
  lineOffset: 12,
  boxEnabled: false,
  boxColor: "#FFFFFF",
  boxOpacity: 0.1,
  boxPadding: 20,
  boxRadius: 8,
  duration: 3.0,
  fadeIn: 0.3,
  fadeOut: 0.3,
};

export const DEFAULT_SUBTITLE_STYLE: SubtitleStyle = {
  fontFamily: "Poppins",
  fontSize: 34,
  fontWeight: "700",
  letterSpacing: 0,
  lineHeight: 1.4,
  color: "#FFFFFF",
  highlightColor: "#FFCC00",
  highlightScale: 1.2,
  highlightBold: true,
  highlightStyle: "scale",
  highlightGlow: false,
  highlightGlowColor: "#FFCC00",
  highlightWords: [],
  dualStyleEnabled: false,
  highlightFontFamily: "Anton",
  highlightFontSize: 38,
  highlightFontWeight: "900",
  highlightLetterSpacing: 1,
  highlightItalic: false,
  highlightUppercase: true,
  highlightStrokeEnabled: true,
  highlightStrokeColor: "#000000",
  highlightStrokeWidth: 3,
  highlightShadowEnabled: true,
  highlightShadowColor: "#000000",
  highlightShadowBlur: 12,
  bgEnabled: true,
  bgColor: "#000000",
  bgOpacity: 0.4,
  bgRadius: 8,
  bgPadding: 12,
  position: "bottom",
  positionY: 85,
  uppercase: false,
  italic: false,
  strokeEnabled: true,
  strokeColor: "#000000",
  strokeWidth: 2,
  shadowEnabled: true,
  shadowColor: "#000000",
  shadowBlur: 8,
  maxWordsPerLine: 3,
  wordSpacing: 6,
  animationStyle: "pop",
  animationSpeed: 1.0,
};

// ─── Presets ─────────────────────────────────────────────────────────────────

const HOOK_PRESETS: { id: string; name: string; style: Partial<HookStyle> }[] = [
  { id: "bold_white", name: "Bold White", style: { color: "#FFFFFF", bgOpacity: 0.6, fontSize: 52, fontFamily: "Anton", uppercase: true, glowEnabled: false } },
  { id: "neon_green", name: "Neon Green", style: { color: "#00FF88", bgOpacity: 0.7, fontSize: 44, fontFamily: "Inter", glowEnabled: true, glowColor: "#00FF88", glowSize: 25 } },
  { id: "cinematic", name: "Cinematic", style: { color: "#E0E0E0", bgOpacity: 0.5, fontSize: 46, fontFamily: "Montserrat", lineEnabled: true, lineColor: "#FF4444", linePosition: "bottom", letterSpacing: 2 } },
  { id: "minimal", name: "Minimal", style: { color: "#FFFFFF", bgOpacity: 0.3, fontSize: 38, fontFamily: "Inter", fontWeight: "500", shadowBlur: 4 } },
  { id: "glitch_red", name: "Glitch Red", style: { color: "#FF3333", bgOpacity: 0.7, fontSize: 50, fontFamily: "Anton", uppercase: true, animation: "glitch" } },
  { id: "typewriter", name: "Typewriter", style: { color: "#00FF88", bgOpacity: 0.75, fontSize: 40, fontFamily: "monospace", animation: "typewriter" } },
  { id: "gradient_gold", name: "Gold Gradient", style: { gradientEnabled: true, gradientFrom: "#FFD700", gradientTo: "#FF8C00", fontSize: 50, fontFamily: "Montserrat", fontWeight: "900" } },
  { id: "boxed", name: "Boxed", style: { boxEnabled: true, boxColor: "#FFFFFF", boxOpacity: 0.15, boxPadding: 24, boxRadius: 12, fontSize: 42 } },
];

const SUBTITLE_PRESETS: { id: string; name: string; style: Partial<SubtitleStyle> }[] = [
  { id: "classic", name: "Classic White", style: { color: "#FFFFFF", highlightColor: "#FFCC00", fontSize: 34, bgOpacity: 0.4, animationStyle: "pop" } },
  { id: "bold_yellow", name: "Bold Yellow", style: { color: "#FFFFFF", highlightColor: "#FFD700", fontSize: 38, highlightScale: 1.3, uppercase: true, animationStyle: "pop" } },
  { id: "neon", name: "Neon Pop", style: { color: "#FFFFFF", highlightColor: "#00FFCC", fontSize: 32, bgColor: "#001a1a", bgOpacity: 0.6, highlightGlow: true, highlightGlowColor: "#00FFCC" } },
  { id: "minimal", name: "Minimal", style: { color: "#CCCCCC", highlightColor: "#FFFFFF", fontSize: 30, bgEnabled: false, strokeWidth: 3, animationStyle: "fade" } },
  { id: "big_impact", name: "Big Impact", style: { color: "#FFFFFF", highlightColor: "#FF4444", fontSize: 42, highlightScale: 1.4, uppercase: true, fontFamily: "Anton", animationStyle: "pop" } },
  { id: "slide_clean", name: "Slide Clean", style: { color: "#FFFFFF", highlightColor: "#4ECDC4", fontSize: 32, fontFamily: "Inter", animationStyle: "slide", bgRadius: 20 } },
  { id: "glow_purple", name: "Glow Purple", style: { color: "#FFFFFF", highlightColor: "#A855F7", highlightGlow: true, highlightGlowColor: "#A855F7", fontSize: 36, bgOpacity: 0.3 } },
];

// ─── Modal ───────────────────────────────────────────────────────────────────

interface StyleEditorModalProps {
  open: boolean;
  onClose: () => void;
  hookStyle: HookStyle;
  subtitleStyle: SubtitleStyle;
  onHookChange: (style: HookStyle) => void;
  onSubtitleChange: (style: SubtitleStyle) => void;
  aspectRatio?: string;
  inline?: boolean;
  activeTab?: "presets" | "hook" | "subtitle";
  thumbnailUrl?: string;
  isSuperadmin?: boolean;
  isPremium?: boolean;
  userFeatures?: string[];
  activePresetId?: number | null;
  onPresetSelect?: (id: number) => void;
}

export function StyleEditorModal({ open, onClose, hookStyle, subtitleStyle, onHookChange, onSubtitleChange, aspectRatio = "9:16", inline, activeTab, thumbnailUrl, isSuperadmin, isPremium, userFeatures, activePresetId: externalActivePresetId, onPresetSelect }: StyleEditorModalProps) {
  const [tab, setTab] = useState<"presets" | "hook" | "subtitle">(activeTab || "hook");

  useEffect(() => { if (activeTab) setTab(activeTab); }, [activeTab]);

  if (!open) return null;

  const animationStyles = `
    @keyframes fadeScale { 0%,100% { opacity:0.4; transform:translateY(-50%) scale(0.9); } 50% { opacity:1; transform:translateY(-50%) scale(1); } }
    @keyframes slideUp { 0%,100% { opacity:0.3; transform:translateY(-40%); } 50% { opacity:1; transform:translateY(-50%); } }
    @keyframes glitch { 0% { transform:translateY(-50%) translateX(-2px); } 25% { transform:translateY(-50%) translateX(2px); } 50% { transform:translateY(-50%) translateX(-1px); } 75% { transform:translateY(-50%) translateX(1px); } 100% { transform:translateY(-50%); } }
    @keyframes typewriter { 0% { width:0; overflow:hidden; } 50%,100% { width:100%; } }
    @keyframes popIn { 0%,100% { transform:scale(0.9); opacity:0.5; } 50% { transform:scale(1.05); opacity:1; } }
    @keyframes fadeIn { 0%,100% { opacity:0.3; } 50% { opacity:1; } }
    @keyframes slideInUp { 0%,100% { transform:translateY(4px); opacity:0.4; } 50% { transform:translateY(0); opacity:1; } }
  `;

  // Inline mode: just render the content without overlay
  if (inline) {
    return (
      <div className="h-full overflow-hidden">
        <style>{animationStyles}</style>
        {tab === "presets" ? <PresetsTab hookStyle={hookStyle} subtitleStyle={subtitleStyle} onHookChange={onHookChange} onSubtitleChange={onSubtitleChange} externalActiveId={externalActivePresetId} onPresetSelect={onPresetSelect} /> : tab === "hook" ? <HookEditor style={hookStyle} onChange={onHookChange} aspectRatio={aspectRatio} thumbnailUrl={thumbnailUrl} /> : <SubtitleEditor style={subtitleStyle} onChange={onSubtitleChange} aspectRatio={aspectRatio} thumbnailUrl={thumbnailUrl} isSuperadmin={isSuperadmin} isPremium={isPremium} userFeatures={userFeatures} />}
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <style>{animationStyles}</style>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-[95vw] max-w-[1100px] h-[88vh] bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800 shrink-0">
          <div className="flex items-center gap-4">
            <h2 className="text-sm font-semibold text-zinc-100">Custom Style Editor</h2>
            <div className="flex bg-zinc-800 rounded-lg p-0.5">
              <button type="button" onClick={() => setTab("presets")} className={cn("px-3 py-1.5 text-xs font-medium rounded-md transition-colors", tab === "presets" ? "bg-emerald-600 text-white" : "text-zinc-400 hover:text-zinc-200")}>
                <Bookmark className="h-3 w-3 inline mr-1.5" />Presets
              </button>
              <button type="button" onClick={() => setTab("hook")} className={cn("px-3 py-1.5 text-xs font-medium rounded-md transition-colors", tab === "hook" ? "bg-emerald-600 text-white" : "text-zinc-400 hover:text-zinc-200")}>
                <Type className="h-3 w-3 inline mr-1.5" />Hook
              </button>
              <button type="button" onClick={() => setTab("subtitle")} className={cn("px-3 py-1.5 text-xs font-medium rounded-md transition-colors", tab === "subtitle" ? "bg-emerald-600 text-white" : "text-zinc-400 hover:text-zinc-200")}>
                <Sparkles className="h-3 w-3 inline mr-1.5" />Subtitle
              </button>
            </div>
          </div>
          <button type="button" onClick={onClose} className="p-1.5 rounded-lg text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"><X className="h-4 w-4" /></button>
        </div>
        <div className="flex-1 overflow-hidden">
          {tab === "presets" ? <PresetsTab hookStyle={hookStyle} subtitleStyle={subtitleStyle} onHookChange={onHookChange} onSubtitleChange={onSubtitleChange} externalActiveId={externalActivePresetId} onPresetSelect={onPresetSelect} /> : tab === "hook" ? <HookEditor style={hookStyle} onChange={onHookChange} aspectRatio={aspectRatio} thumbnailUrl={thumbnailUrl} /> : <SubtitleEditor style={subtitleStyle} onChange={onSubtitleChange} aspectRatio={aspectRatio} thumbnailUrl={thumbnailUrl} isSuperadmin={isSuperadmin} isPremium={isPremium} userFeatures={userFeatures} />}
        </div>
      </div>
    </div>
  );
}

// ─── Presets Tab ─────────────────────────────────────────────────────────────

function PresetsTab({ hookStyle, subtitleStyle, onHookChange, onSubtitleChange, externalActiveId, onPresetSelect }: { hookStyle: HookStyle; subtitleStyle: SubtitleStyle; onHookChange: (s: HookStyle) => void; onSubtitleChange: (s: SubtitleStyle) => void; externalActiveId?: number | null; onPresetSelect?: (id: number) => void }) {
  const [userPresets, setUserPresets] = useState<Preset[]>([]);
  const [loading, setLoading] = useState(true);
  const [saveName, setSaveName] = useState("");
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [activePresetId, setActivePresetId] = useState<number | null>(externalActiveId ?? null);

  // Sync from external
  useEffect(() => { if (externalActiveId !== undefined) setActivePresetId(externalActiveId); }, [externalActiveId]);

  useEffect(() => {
    presetsApi.list().then((list) => { setUserPresets(list); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  function loadPreset(preset: Preset) {
    onHookChange({ ...DEFAULT_HOOK_STYLE, ...preset.hook_style } as HookStyle);
    onSubtitleChange({ ...DEFAULT_SUBTITLE_STYLE, ...preset.subtitle_style } as SubtitleStyle);
    setActivePresetId(preset.id);
    if (onPresetSelect) onPresetSelect(preset.id);
    setStatusMsg(`Loaded "${preset.name}"`);
    setTimeout(() => setStatusMsg(""), 2000);
  }

  async function handleSave() {
    if (!saveName.trim()) return;
    setSaving(true);
    try {
      await presetsApi.create(saveName.trim(), hookStyle, subtitleStyle);
      setSaveName("");
      setStatusMsg(`Saved "${saveName.trim()}"`);
      setTimeout(() => setStatusMsg(""), 2000);
      const list = await presetsApi.list();
      setUserPresets(list);
    } catch { setStatusMsg("Failed to save"); }
    finally { setSaving(false); }
  }

  async function handleDelete(id: number, name: string) {
    if (!confirm(`Delete preset "${name}"?`)) return;
    try {
      await presetsApi.remove(id);
      setUserPresets((prev) => prev.filter((p) => p.id !== id));
      setStatusMsg(`Deleted "${name}"`);
      setTimeout(() => setStatusMsg(""), 2000);
    } catch { setStatusMsg("Failed to delete"); }
  }

  return (
    <div className="h-full p-5 overflow-y-auto">
      {/* Save current as preset */}
      <div className="mb-6">
        <h3 className="text-xs font-semibold text-zinc-200 mb-3 flex items-center gap-2">
          <Save className="h-3.5 w-3.5 text-emerald-400" />Save Current Style as Preset
        </h3>
        <div className="flex gap-2">
          <input type="text" value={saveName} onChange={(e) => setSaveName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), handleSave())} placeholder="Enter preset name..." className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50" />
          <Button type="button" size="sm" loading={saving} onClick={handleSave} icon={<Save className="h-3.5 w-3.5" />}>Save</Button>
        </div>
        {statusMsg && <p className="text-[11px] text-emerald-400 mt-2">{statusMsg}</p>}
      </div>

      {/* Preset list */}
      <div>
        <h3 className="text-xs font-semibold text-zinc-200 mb-3 flex items-center gap-2">
          <Bookmark className="h-3.5 w-3.5 text-emerald-400" />My Presets ({userPresets.length})
        </h3>
        {loading ? (
          <div className="flex items-center gap-2 py-4"><div className="h-4 w-4 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin" /><span className="text-xs text-zinc-500">Loading...</span></div>
        ) : userPresets.length === 0 ? (
          <div className="text-center py-8 border border-dashed border-zinc-800 rounded-xl">
            <Bookmark className="h-6 w-6 text-zinc-700 mx-auto mb-2" />
            <p className="text-xs text-zinc-500">No presets saved yet</p>
            <p className="text-[10px] text-zinc-600 mt-1">Configure your hook & subtitle styles, then save them here</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {userPresets.map((p) => (
              <div key={p.id} className={cn("relative group rounded-xl border p-3 transition-all",
                activePresetId === p.id
                  ? "border-emerald-500 bg-emerald-500/8 ring-1 ring-emerald-500/20"
                  : "border-zinc-800 bg-zinc-900/50 hover:border-emerald-500/40")}>
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <h4 className={cn("text-sm font-medium truncate pr-2", activePresetId === p.id ? "text-emerald-300" : "text-zinc-200")}>{p.name}</h4>
                    {activePresetId === p.id && <span className="shrink-0 text-[8px] bg-emerald-500/20 text-emerald-400 font-bold uppercase px-1.5 py-0.5 rounded-full">Active</span>}
                  </div>
                  <button type="button" onClick={() => handleDelete(p.id, p.name)} className="absolute top-2.5 right-2.5 p-1 rounded text-zinc-700 hover:text-red-400 hover:bg-zinc-800 opacity-0 group-hover:opacity-100 transition-all">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                <div className="space-y-1 text-[10px] text-zinc-500 mb-3">
                  <p>Hook: <span className="text-zinc-400">{(p.hook_style as any)?.animation?.replace(/_/g, " ") || "default"}</span></p>
                  <p>Font: <span className="text-zinc-400">{(p.hook_style as any)?.fontFamily || "Poppins"}</span></p>
                  <p>Highlight: <span style={{ color: (p.subtitle_style as any)?.highlightColor || "#FFCC00" }}>{(p.subtitle_style as any)?.highlightColor || "#FFCC00"}</span></p>
                  {p.owner_email && <p>Owner: <span className="text-zinc-400">{p.owner_name || p.owner_email}</span></p>}
                </div>
                <button type="button" onClick={() => loadPreset(p)} className={cn("w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg border text-[11px] font-medium transition-colors",
                  activePresetId === p.id
                    ? "border-emerald-500 bg-emerald-500/20 text-emerald-300"
                    : "border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10")}>
                  <Download className="h-3 w-3" />{activePresetId === p.id ? "Active" : "Load Preset"}
                </button>
                {p.created_at && <p className="text-[9px] text-zinc-700 mt-2 text-center">{new Date(p.created_at).toLocaleDateString()}</p>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Hook Editor ─────────────────────────────────────────────────────────────

function HookEditor({ style, onChange, aspectRatio, thumbnailUrl }: { style: HookStyle; onChange: (s: HookStyle) => void; aspectRatio: string; thumbnailUrl?: string }) {
  const update = (patch: Partial<HookStyle>) => onChange({ ...style, ...patch });
  const [activePreset, setActivePreset] = useState<string | null>(null);
  useGoogleFont(style.fontFamily);
  const previewAspect = aspectRatio === "16:9" ? "16/9" : aspectRatio === "1:1" ? "1/1" : "9/16";

  return (
    <div className="grid grid-cols-12 h-full">
      <div className="col-span-8 p-4 overflow-y-auto space-y-4 border-r border-zinc-800">
        {/* Presets */}
        <Section title="Quick Presets">
          <div className="flex flex-wrap gap-1.5">
            {HOOK_PRESETS.map(p => (
              <button key={p.id} type="button" onClick={() => { update(p.style as any); setActivePreset(p.id); }}
                className={cn("px-2.5 py-1.5 rounded-lg border text-[11px] transition-colors",
                  activePreset === p.id ? "border-emerald-500 bg-emerald-500/10 text-emerald-400 font-medium" : "border-zinc-700 text-zinc-300 hover:border-emerald-500 hover:text-emerald-400"
                )}>{p.name}</button>
            ))}
          </div>
        </Section>

        <Section title="Hook Text">
          <textarea value={style.text} onChange={(e) => update({ text: e.target.value })} placeholder="Leave empty for AI-generated hook..." rows={2} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 resize-none focus:outline-none focus:border-zinc-500" />
        </Section>

        <Section title="Animation & Timing">
          <div className="grid grid-cols-4 gap-2 mb-3">
            {["fade_scale", "slide_up", "glitch", "typewriter"].map(a => (
              <button key={a} type="button" onClick={() => update({ animation: a })} className={cn("py-2 rounded-lg border text-[11px] font-medium transition-colors", style.animation === a ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600")}>{a.replace("_", " ")}</button>
            ))}
          </div>
          <div className="grid grid-cols-3 gap-3">
            <RangeInput label={`Duration: ${style.duration}s`} min={15} max={60} value={Math.round(style.duration * 10)} onChange={(v) => update({ duration: v / 10 })} />
            <RangeInput label={`Fade In: ${style.fadeIn}s`} min={1} max={10} value={Math.round(style.fadeIn * 10)} onChange={(v) => update({ fadeIn: v / 10 })} />
            <RangeInput label={`Fade Out: ${style.fadeOut}s`} min={1} max={10} value={Math.round(style.fadeOut * 10)} onChange={(v) => update({ fadeOut: v / 10 })} />
          </div>
        </Section>

        <Section title="Typography">
          <div className="grid grid-cols-3 gap-3">
            <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={["Poppins", "Inter", "Montserrat", "Anton", "Bebas Neue", "Oswald", "Raleway", "Roboto", "Lato", "Nunito", "Playfair Display", "Merriweather", "Barlow Condensed", "Archivo Black", "Righteous", "monospace"]} />
            <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
            <SelectSmall label="Align" value={style.textAlign} onChange={(v) => update({ textAlign: v as any })} options={["center", "left", "right"]} />
          </div>
          <div className="grid grid-cols-3 gap-3 mt-3">
            <RangeInput label={`Size: ${style.fontSize}px`} min={24} max={80} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
            <RangeInput label={`Spacing: ${style.letterSpacing}px`} min={-2} max={12} value={style.letterSpacing} onChange={(v) => update({ letterSpacing: v })} />
            <RangeInput label={`Line H: ${style.lineHeight}`} min={10} max={24} value={Math.round(style.lineHeight * 10)} onChange={(v) => update({ lineHeight: v / 10 })} />
          </div>
          <div className="flex gap-4 mt-3">
            <Checkbox label="UPPERCASE" checked={style.uppercase} onChange={(v) => update({ uppercase: v })} />
            <Checkbox label="Italic" checked={style.italic} onChange={(v) => update({ italic: v })} />
          </div>
        </Section>

        <Section title="Colors & Effects">
          <div className="grid grid-cols-2 gap-3">
            <ColorPicker label="Text Color" value={style.color} onChange={(v) => update({ color: v })} />
            <ColorPicker label="Background" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
          </div>
          <RangeInput label={`BG Opacity: ${Math.round(style.bgOpacity * 100)}%`} min={0} max={100} value={Math.round(style.bgOpacity * 100)} onChange={(v) => update({ bgOpacity: v / 100 })} />
          {/* Gradient */}
          <div className="mt-3">
            <Checkbox label="Enable text gradient" checked={style.gradientEnabled} onChange={(v) => update({ gradientEnabled: v })} />
            {style.gradientEnabled && (
              <div className="grid grid-cols-3 gap-3 mt-2">
                <ColorPicker label="From" value={style.gradientFrom} onChange={(v) => update({ gradientFrom: v })} />
                <ColorPicker label="To" value={style.gradientTo} onChange={(v) => update({ gradientTo: v })} />
                <RangeInput label={`Angle: ${style.gradientAngle}°`} min={0} max={360} value={style.gradientAngle} onChange={(v) => update({ gradientAngle: v })} />
              </div>
            )}
          </div>
          {/* Shadow */}
          <div className="mt-3">
            <Checkbox label="Text shadow" checked={style.shadowEnabled} onChange={(v) => update({ shadowEnabled: v })} />
            {style.shadowEnabled && (
              <div className="grid grid-cols-4 gap-3 mt-2">
                <ColorPicker label="Color" value={style.shadowColor} onChange={(v) => update({ shadowColor: v })} />
                <RangeInput label={`Blur: ${style.shadowBlur}`} min={0} max={40} value={style.shadowBlur} onChange={(v) => update({ shadowBlur: v })} />
                <RangeInput label={`X: ${style.shadowX}`} min={-10} max={10} value={style.shadowX} onChange={(v) => update({ shadowX: v })} />
                <RangeInput label={`Y: ${style.shadowY}`} min={-10} max={10} value={style.shadowY} onChange={(v) => update({ shadowY: v })} />
              </div>
            )}
          </div>
          {/* Glow */}
          <div className="mt-3">
            <Checkbox label="Text glow" checked={style.glowEnabled} onChange={(v) => update({ glowEnabled: v })} />
            {style.glowEnabled && (
              <div className="grid grid-cols-2 gap-3 mt-2">
                <ColorPicker label="Glow Color" value={style.glowColor} onChange={(v) => update({ glowColor: v })} />
                <RangeInput label={`Glow Size: ${style.glowSize}px`} min={5} max={60} value={style.glowSize} onChange={(v) => update({ glowSize: v })} />
              </div>
            )}
          </div>
        </Section>

        <Section title="Position">
          <div className="grid grid-cols-3 gap-2 mb-3">
            {(["top", "center", "bottom"] as const).map(p => (
              <button key={p} type="button" onClick={() => update({ position: p, positionY: p === "top" ? 20 : p === "bottom" ? 80 : 50 })} className={cn("py-2 rounded-lg border text-[11px] font-medium capitalize transition-colors", style.position === p ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600")}>{p}</button>
            ))}
          </div>
          <RangeInput label={`Vertical: ${style.positionY}%`} min={5} max={95} value={style.positionY} onChange={(v) => update({ positionY: v })} />
        </Section>

        <Section title="Accent Line">
          <Checkbox label="Enable accent line" checked={style.lineEnabled} onChange={(v) => update({ lineEnabled: v })} />
          {style.lineEnabled && (
            <div className="mt-3 space-y-3">
              <div className="grid grid-cols-7 gap-2">
                {(["top", "center-h", "bottom", "left", "center-v", "right", "auto-bottom"] as const).map(p => (
                  <button key={p} type="button" onClick={() => update({ linePosition: p })} className={cn("py-1.5 rounded-lg border text-[10px] font-medium capitalize transition-colors", style.linePosition === p ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-700 text-zinc-400")}>{p.replace("-h", " ↔").replace("-v", " ↕").replace("auto-bottom", "Auto ↓")}</button>
                ))}
              </div>
              <Checkbox label="Auto-adjust width (match text)" checked={style.lineAutoWidth} onChange={(v) => update({ lineAutoWidth: v, lineWidth: v ? 80 : style.lineWidth })} />
              <div className="grid grid-cols-4 gap-3">
                <ColorPicker label="Color" value={style.lineColor} onChange={(v) => update({ lineColor: v })} />
                {!style.lineAutoWidth && <RangeInput label={`Width: ${style.lineWidth}%`} min={10} max={100} value={style.lineWidth} onChange={(v) => update({ lineWidth: v })} />}
                <RangeInput label={`Thick: ${style.lineThickness}px`} min={1} max={12} value={style.lineThickness} onChange={(v) => update({ lineThickness: v })} />
                <RangeInput label={`Offset: ${style.lineOffset}px`} min={0} max={40} value={style.lineOffset} onChange={(v) => update({ lineOffset: v })} />
              </div>
            </div>
          )}
        </Section>

        <Section title="Text Box / Border">
          <Checkbox label="Enable box around text" checked={style.boxEnabled} onChange={(v) => update({ boxEnabled: v })} />
          {style.boxEnabled && (
            <div className="grid grid-cols-4 gap-3 mt-3">
              <ColorPicker label="Box Color" value={style.boxColor} onChange={(v) => update({ boxColor: v })} />
              <RangeInput label={`Opacity: ${Math.round(style.boxOpacity * 100)}%`} min={0} max={100} value={Math.round(style.boxOpacity * 100)} onChange={(v) => update({ boxOpacity: v / 100 })} />
              <RangeInput label={`Padding: ${style.boxPadding}px`} min={4} max={48} value={style.boxPadding} onChange={(v) => update({ boxPadding: v })} />
              <RangeInput label={`Radius: ${style.boxRadius}px`} min={0} max={24} value={style.boxRadius} onChange={(v) => update({ boxRadius: v })} />
            </div>
          )}
        </Section>
      </div>

      {/* Preview */}
      <div className="col-span-4 p-4 flex flex-col items-center bg-zinc-950 overflow-y-auto">
        <p className="text-[9px] text-zinc-600 mb-3 uppercase tracking-widest shrink-0">Live Preview</p>
        <div className="relative w-full bg-zinc-900 rounded-lg overflow-hidden border border-zinc-800 shrink-0" style={{ aspectRatio: previewAspect }}>
          {thumbnailUrl && <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-cover" />}
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          {/* Text with animation */}
          <div className="absolute inset-0 flex px-4" style={{ justifyContent: style.textAlign === "left" ? "flex-start" : style.textAlign === "right" ? "flex-end" : "center" }}>
            <div className={cn("w-full flex", getHookAnimationClass(style.animation))} style={{ position: "absolute", top: `${style.positionY}%`, transform: "translateY(-50%)", left: 0, right: 0, justifyContent: style.textAlign === "left" ? "flex-start" : style.textAlign === "right" ? "flex-end" : "center", padding: "0 16px" }}>
              <p style={{
                color: style.gradientEnabled ? "transparent" : style.color,
                background: style.gradientEnabled ? `linear-gradient(${style.gradientAngle}deg, ${style.gradientFrom}, ${style.gradientTo})` : undefined,
                WebkitBackgroundClip: style.gradientEnabled ? "text" : undefined,
                fontSize: Math.max(style.fontSize * 0.32, 12),
                fontWeight: Number(style.fontWeight),
                fontFamily: style.fontFamily === "monospace" ? "monospace" : `'${style.fontFamily}', sans-serif`,
                fontStyle: style.italic ? "italic" : "normal",
                letterSpacing: style.letterSpacing,
                lineHeight: style.lineHeight,
                textShadow: [
                  style.shadowEnabled ? `${style.shadowX}px ${style.shadowY}px ${style.shadowBlur}px ${style.shadowColor}` : "",
                  style.glowEnabled ? `0 0 ${style.glowSize}px ${style.glowColor}` : "",
                ].filter(Boolean).join(", ") || undefined,
                textTransform: style.uppercase ? "uppercase" : "none",
                textAlign: style.textAlign,
                maxWidth: "90%",
                ...(style.boxEnabled ? { backgroundColor: `${style.boxColor}${Math.round(style.boxOpacity * 255).toString(16).padStart(2, "0")}`, padding: style.boxPadding * 0.4, borderRadius: style.boxRadius } : {}),
              }}>
                {style.text || "Hook text preview here"}
              </p>
            </div>
          </div>
          {/* Accent line */}
          {style.lineEnabled && <AccentLinePreview style={style} />}
          <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-600">{style.animation.replace("_", " ")} | {style.duration}s</p>
        </div>
      </div>
    </div>
  );
}

// ─── Subtitle Editor ─────────────────────────────────────────────────────────

function SubtitleEditor({ style, onChange, aspectRatio, thumbnailUrl, isSuperadmin, isPremium, userFeatures }: { style: SubtitleStyle; onChange: (s: SubtitleStyle) => void; aspectRatio: string; thumbnailUrl?: string; isSuperadmin?: boolean; isPremium?: boolean; userFeatures?: string[] }) {
  const update = (patch: Partial<SubtitleStyle>) => onChange({ ...style, ...patch });
  const [newWord, setNewWord] = useState("");
  const [activeWordIdx, setActiveWordIdx] = useState(0);
  const [activePreset, setActivePreset] = useState<string | null>(null);
  useGoogleFont(style.fontFamily);
  useGoogleFont(style.dualStyleEnabled ? style.highlightFontFamily : "");
  const previewAspect = aspectRatio === "16:9" ? "16/9" : aspectRatio === "1:1" ? "1/1" : "9/16";

  // Cycle through words for animated preview
  useEffect(() => {
    const interval = setInterval(() => {
      setActiveWordIdx((prev) => (prev + 1) % 4);
    }, 800);
    return () => clearInterval(interval);
  }, []);

  function addHighlightWord() {
    if (newWord.trim() && !style.highlightWords.includes(newWord.trim().toLowerCase())) {
      update({ highlightWords: [...style.highlightWords, newWord.trim().toLowerCase()] });
      setNewWord("");
    }
  }

  return (
    <div className="grid grid-cols-12 h-full">
      <div className="col-span-8 p-4 overflow-y-auto space-y-4 border-r border-zinc-800">
        <Section title="Quick Presets">
          <div className="flex flex-wrap gap-1.5">
            {SUBTITLE_PRESETS.map(p => (
              <button key={p.id} type="button" onClick={() => { update(p.style as any); setActivePreset(p.id); }}
                className={cn("px-2.5 py-1.5 rounded-lg border text-[11px] transition-colors",
                  activePreset === p.id ? "border-emerald-500 bg-emerald-500/10 text-emerald-400 font-medium" : "border-zinc-700 text-zinc-300 hover:border-emerald-500 hover:text-emerald-400"
                )}>{p.name}</button>
            ))}
          </div>
        </Section>

        <Section title="Typography">
          <div className="grid grid-cols-3 gap-3">
            <SelectSmall label="Font" value={style.fontFamily} onChange={(v) => update({ fontFamily: v })} options={["Poppins", "Inter", "Montserrat", "Anton", "Bebas Neue", "Oswald", "Raleway", "Roboto", "Lato", "Nunito", "Playfair Display", "Merriweather", "Barlow Condensed", "Archivo Black", "Righteous"]} />
            <SelectSmall label="Weight" value={style.fontWeight} onChange={(v) => update({ fontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
            <RangeInput label={`Size: ${style.fontSize}px`} min={20} max={52} value={style.fontSize} onChange={(v) => update({ fontSize: v })} />
          </div>
          <div className="grid grid-cols-3 gap-3 mt-3">
            <RangeInput label={`Spacing: ${style.letterSpacing}px`} min={-1} max={8} value={style.letterSpacing} onChange={(v) => update({ letterSpacing: v })} />
            <RangeInput label={`Line H: ${style.lineHeight}`} min={10} max={24} value={Math.round(style.lineHeight * 10)} onChange={(v) => update({ lineHeight: v / 10 })} />
            <RangeInput label={`Words/line: ${style.maxWordsPerLine}`} min={2} max={6} value={style.maxWordsPerLine} onChange={(v) => update({ maxWordsPerLine: v })} />
          </div>
          <div className="flex gap-4 mt-3">
            <Checkbox label="UPPERCASE" checked={style.uppercase} onChange={(v) => update({ uppercase: v })} />
            <Checkbox label="Italic" checked={style.italic} onChange={(v) => update({ italic: v })} />
          </div>
        </Section>

        <Section title="Colors">
          <div className="grid grid-cols-3 gap-3">
            <ColorPicker label="Text" value={style.color} onChange={(v) => update({ color: v })} />
            <ColorPicker label="Highlight" value={style.highlightColor} onChange={(v) => update({ highlightColor: v })} />
            <ColorPicker label="BG" value={style.bgColor} onChange={(v) => update({ bgColor: v })} />
          </div>
        </Section>

        <Section title="Highlight Effect">
          <div className="grid grid-cols-4 gap-2 mb-3">
            {(["scale", "underline", "background", "strikethrough"] as const).map(s => (
              <button key={s} type="button" onClick={() => update({ highlightStyle: s })}
                className={cn("py-1.5 rounded-lg border text-[10px] font-medium capitalize transition-colors",
                  style.highlightStyle === s ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600")}>{s}</button>
            ))}
          </div>
          <div className="grid grid-cols-3 gap-3">
            <RangeInput label={`Scale: ${style.highlightScale.toFixed(1)}x`} min={10} max={20} value={Math.round(style.highlightScale * 10)} onChange={(v) => update({ highlightScale: v / 10 })} />
            <div className="flex flex-col justify-end"><Checkbox label="Bold" checked={style.highlightBold} onChange={(v) => update({ highlightBold: v })} /></div>
            <div className="flex flex-col justify-end"><Checkbox label="Glow" checked={style.highlightGlow} onChange={(v) => update({ highlightGlow: v })} /></div>
          </div>
          {style.highlightGlow && (
            <div className="grid grid-cols-2 gap-3 mt-2">
              <ColorPicker label="Glow Color" value={style.highlightGlowColor} onChange={(v) => update({ highlightGlowColor: v })} />
            </div>
          )}
        </Section>

        <Section title="Dual Font Style (Highlight Words)">
          <FeatureLock featureName="Dual Font Style" featureCode="dual_subtitle" isSuperadmin={isSuperadmin} isPremium={isPremium} userFeatures={userFeatures}>
            <Checkbox label="Use separate style for highlight words" checked={style.dualStyleEnabled} onChange={(v) => update({ dualStyleEnabled: v })} />
            <p className="text-[9px] text-zinc-600 mt-1 mb-2">Kata-kata penting (MAKANYA, JANGAN, dll) akan menggunakan font & style berbeda dari teks normal.</p>
            {style.dualStyleEnabled && (
              <div className="mt-3 p-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 space-y-3">
                <p className="text-[10px] text-emerald-400 font-medium uppercase tracking-wider">Highlight Word Style</p>
                <div className="grid grid-cols-3 gap-3">
                  <SelectSmall label="Font" value={style.highlightFontFamily} onChange={(v) => update({ highlightFontFamily: v })} options={["Anton", "Poppins", "Inter", "Montserrat", "Bebas Neue", "Oswald", "Raleway", "Roboto", "Archivo Black", "Righteous", "Barlow Condensed", "Playfair Display"]} />
                  <SelectSmall label="Weight" value={style.highlightFontWeight} onChange={(v) => update({ highlightFontWeight: v })} options={["400", "500", "600", "700", "800", "900"]} />
                  <RangeInput label={`Size: ${style.highlightFontSize}px`} min={24} max={56} value={style.highlightFontSize} onChange={(v) => update({ highlightFontSize: v })} />
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <RangeInput label={`Spacing: ${style.highlightLetterSpacing}px`} min={-1} max={8} value={style.highlightLetterSpacing} onChange={(v) => update({ highlightLetterSpacing: v })} />
                  <div className="flex flex-col justify-end"><Checkbox label="UPPERCASE" checked={style.highlightUppercase} onChange={(v) => update({ highlightUppercase: v })} /></div>
                  <div className="flex flex-col justify-end"><Checkbox label="Italic" checked={style.highlightItalic} onChange={(v) => update({ highlightItalic: v })} /></div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div><Checkbox label="Stroke" checked={style.highlightStrokeEnabled} onChange={(v) => update({ highlightStrokeEnabled: v })} /></div>
                  <div><Checkbox label="Shadow" checked={style.highlightShadowEnabled} onChange={(v) => update({ highlightShadowEnabled: v })} /></div>
                </div>
                {style.highlightStrokeEnabled && (
                  <div className="grid grid-cols-2 gap-3">
                    <ColorPicker label="Stroke Color" value={style.highlightStrokeColor} onChange={(v) => update({ highlightStrokeColor: v })} />
                    <RangeInput label={`Width: ${style.highlightStrokeWidth}px`} min={1} max={6} value={style.highlightStrokeWidth} onChange={(v) => update({ highlightStrokeWidth: v })} />
                  </div>
                )}
                {style.highlightShadowEnabled && (
                  <div className="grid grid-cols-2 gap-3">
                    <ColorPicker label="Shadow Color" value={style.highlightShadowColor} onChange={(v) => update({ highlightShadowColor: v })} />
                    <RangeInput label={`Blur: ${style.highlightShadowBlur}px`} min={0} max={24} value={style.highlightShadowBlur} onChange={(v) => update({ highlightShadowBlur: v })} />
                  </div>
                )}
              </div>
            )}
          </FeatureLock>
        </Section>

        <Section title="Background & Stroke">
          <div className="grid grid-cols-2 gap-3">
            <div><Checkbox label="Background" checked={style.bgEnabled} onChange={(v) => update({ bgEnabled: v })} /></div>
            <div><Checkbox label="Stroke/Outline" checked={style.strokeEnabled} onChange={(v) => update({ strokeEnabled: v })} /></div>
          </div>
          {style.bgEnabled && (
            <div className="grid grid-cols-3 gap-3 mt-2">
              <RangeInput label={`Opacity: ${Math.round(style.bgOpacity * 100)}%`} min={0} max={100} value={Math.round(style.bgOpacity * 100)} onChange={(v) => update({ bgOpacity: v / 100 })} />
              <RangeInput label={`Radius: ${style.bgRadius}px`} min={0} max={24} value={style.bgRadius} onChange={(v) => update({ bgRadius: v })} />
              <RangeInput label={`Padding: ${style.bgPadding}px`} min={4} max={32} value={style.bgPadding} onChange={(v) => update({ bgPadding: v })} />
            </div>
          )}
          {style.strokeEnabled && (
            <div className="grid grid-cols-2 gap-3 mt-2">
              <ColorPicker label="Stroke" value={style.strokeColor} onChange={(v) => update({ strokeColor: v })} />
              <RangeInput label={`Width: ${style.strokeWidth}px`} min={1} max={6} value={style.strokeWidth} onChange={(v) => update({ strokeWidth: v })} />
            </div>
          )}
          <div className="mt-2"><Checkbox label="Text shadow" checked={style.shadowEnabled} onChange={(v) => update({ shadowEnabled: v })} /></div>
          {style.shadowEnabled && (
            <div className="grid grid-cols-2 gap-3 mt-2">
              <ColorPicker label="Shadow" value={style.shadowColor} onChange={(v) => update({ shadowColor: v })} />
              <RangeInput label={`Blur: ${style.shadowBlur}px`} min={0} max={20} value={style.shadowBlur} onChange={(v) => update({ shadowBlur: v })} />
            </div>
          )}
        </Section>

        <Section title="Position">
          <div className="grid grid-cols-3 gap-2 mb-3">
            {(["top", "center", "bottom"] as const).map(p => (
              <button key={p} type="button" onClick={() => update({ position: p, positionY: p === "top" ? 15 : p === "bottom" ? 85 : 50 })} className={cn("py-2 rounded-lg border text-[11px] font-medium capitalize transition-colors", style.position === p ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600")}>{p}</button>
            ))}
          </div>
          <RangeInput label={`Vertical: ${style.positionY}%`} min={5} max={95} value={style.positionY} onChange={(v) => update({ positionY: v })} />
          <RangeInput label={`Word gap: ${style.wordSpacing}px`} min={2} max={16} value={style.wordSpacing} onChange={(v) => update({ wordSpacing: v })} />
        </Section>

        <Section title="Animation">
          <div className="grid grid-cols-4 gap-2 mb-3">
            {(["pop", "fade", "slide", "none"] as const).map(a => (
              <button key={a} type="button" onClick={() => update({ animationStyle: a })} className={cn("py-2 rounded-lg border text-[11px] font-medium capitalize transition-colors", style.animationStyle === a ? "border-emerald-500 bg-emerald-500/10 text-emerald-400" : "border-zinc-700 text-zinc-400 hover:border-zinc-600")}>{a}</button>
            ))}
          </div>
          <RangeInput label={`Speed: ${style.animationSpeed.toFixed(1)}x`} min={5} max={20} value={Math.round(style.animationSpeed * 10)} onChange={(v) => update({ animationSpeed: v / 10 })} />
        </Section>

        <Section title="Highlight Words (kata penting)">
          <p className="text-[10px] text-zinc-500 mb-2">AI auto-detect dari transkrip. Tambah manual jika perlu.</p>
          <div className="flex gap-2">
            <input type="text" value={newWord} onChange={(e) => setNewWord(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addHighlightWord())} placeholder="Tambah kata..." className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500" />
            <Button type="button" size="xs" onClick={addHighlightWord}>Add</Button>
          </div>
          {style.highlightWords.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {style.highlightWords.map(w => (
                <span key={w} className="flex items-center gap-1 bg-yellow-500/10 border border-yellow-500/30 text-yellow-400 text-[10px] font-medium px-2 py-0.5 rounded-full">
                  {w}<button type="button" onClick={() => update({ highlightWords: style.highlightWords.filter(x => x !== w) })} className="hover:text-red-400"><X className="h-2.5 w-2.5" /></button>
                </span>
              ))}
            </div>
          )}
        </Section>
      </div>

      {/* Preview */}
      <div className="col-span-4 p-4 flex flex-col items-center bg-zinc-950 overflow-y-auto">
        <p className="text-[9px] text-zinc-600 mb-3 uppercase tracking-widest shrink-0">Live Preview</p>
        <div className="relative w-full bg-zinc-900 rounded-lg overflow-hidden border border-zinc-800 shrink-0" style={{ aspectRatio: previewAspect }}>
          {thumbnailUrl && <img src={thumbnailUrl} alt="" className="absolute inset-0 w-full h-full object-cover" />}
          <div className="absolute inset-0 bg-gradient-to-b from-zinc-700/30 to-zinc-900/50" />
          <div className="absolute left-0 right-0 flex justify-center px-3" style={{ top: `${style.positionY}%`, transform: "translateY(-50%)" }}>
            <div className={cn("flex flex-wrap justify-center", getSubAnimationClass(style.animationStyle))} style={{ gap: style.wordSpacing * 0.5, backgroundColor: style.bgEnabled ? `${style.bgColor}${Math.round(style.bgOpacity * 255).toString(16).padStart(2, "0")}` : "transparent", padding: style.bgPadding * 0.4, borderRadius: style.bgRadius }}>
              {["ini", "kata", "penting", "banget"].map((w, i) => {
                const isHighlight = i === activeWordIdx;
                const isKeyword = style.highlightWords.includes(w);
                const shouldHighlight = isHighlight || isKeyword;
                const useDual = shouldHighlight && style.dualStyleEnabled;
                const fs = Math.max((shouldHighlight ? (useDual ? style.highlightFontSize : style.fontSize * style.highlightScale) : style.fontSize) * 0.35, 10);

                const hlStyle = style.highlightStyle || "scale";
                const wordStyles: React.CSSProperties = {
                  color: shouldHighlight ? style.highlightColor : style.color,
                  fontSize: fs,
                  fontWeight: useDual ? Number(style.highlightFontWeight) : (shouldHighlight && style.highlightBold ? 900 : Number(style.fontWeight)),
                  fontFamily: useDual ? `'${style.highlightFontFamily}', sans-serif` : `'${style.fontFamily}', sans-serif`,
                  fontStyle: useDual ? (style.highlightItalic ? "italic" : "normal") : (style.italic ? "italic" : "normal"),
                  letterSpacing: useDual ? style.highlightLetterSpacing : style.letterSpacing,
                  textTransform: useDual ? (style.highlightUppercase ? "uppercase" : "none") : (style.uppercase ? "uppercase" : "none"),
                  textShadow: [
                    (useDual ? style.highlightShadowEnabled : style.shadowEnabled) ? `0 0 ${useDual ? style.highlightShadowBlur : style.shadowBlur}px ${useDual ? style.highlightShadowColor : style.shadowColor}` : "",
                    shouldHighlight && style.highlightGlow ? `0 0 12px ${style.highlightGlowColor}` : "",
                  ].filter(Boolean).join(", ") || undefined,
                  WebkitTextStroke: (useDual ? style.highlightStrokeEnabled : style.strokeEnabled) ? `${(useDual ? style.highlightStrokeWidth : style.strokeWidth) * 0.3}px ${useDual ? style.highlightStrokeColor : style.strokeColor}` : undefined,
                  transition: "all 0.2s ease",
                  display: "inline-block",
                  // Highlight style decorations (only if NOT dual — dual uses its own complete style)
                  ...(!useDual && shouldHighlight && hlStyle === "underline" ? { textDecoration: "underline", textDecorationColor: style.highlightColor, textUnderlineOffset: "3px", textDecorationThickness: "2px" } : {}),
                  ...(!useDual && shouldHighlight && hlStyle === "background" ? { backgroundColor: `${style.highlightColor}30`, borderRadius: 3, padding: "1px 4px" } : {}),
                  ...(!useDual && shouldHighlight && hlStyle === "strikethrough" ? { textDecoration: "line-through", textDecorationColor: style.highlightColor, textDecorationThickness: "2px" } : {}),
                };

                return <span key={i} style={wordStyles}>{w}</span>;
              })}
            </div>
          </div>
          <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-600">{style.animationStyle} | {style.position}</p>
        </div>
      </div>
    </div>
  );
}

// ─── Animation helpers ───────────────────────────────────────────────────────

function getHookAnimationClass(animation: string): string {
  switch (animation) {
    case "fade_scale": return "animate-[fadeScale_2s_ease-in-out_infinite]";
    case "slide_up": return "animate-[slideUp_2s_ease-in-out_infinite]";
    case "glitch": return "animate-[glitch_0.5s_steps(2)_infinite]";
    case "typewriter": return "animate-[typewriter_3s_steps(20)_infinite]";
    default: return "";
  }
}

function getSubAnimationClass(animation: string): string {
  switch (animation) {
    case "pop": return "animate-[popIn_1.5s_ease-in-out_infinite]";
    case "fade": return "animate-[fadeIn_2s_ease-in-out_infinite]";
    case "slide": return "animate-[slideInUp_1.5s_ease-in-out_infinite]";
    default: return "";
  }
}

// ─── Shared ──────────────────────────────────────────────────────────────────

function AccentLinePreview({ style }: { style: HookStyle }) {
  const pos = style.linePosition;
  const base: React.CSSProperties = { backgroundColor: style.lineColor, position: "absolute" };
  // Auto-adjust: calculate width/height based on approximate text length
  const textLen = (style.text || "Hook text preview here").length;
  const autoWidthPct = Math.min(Math.max(textLen * 2.5, 20), 70); // 20-70% based on text
  const autoHeightPct = Math.min(Math.max(textLen * 1.5, 15), 50); // 15-50% for vertical
  const autoW = style.lineAutoWidth ? `${autoWidthPct}%` : `${style.lineWidth}%`;
  const autoH = style.lineAutoWidth ? `${autoHeightPct}%` : `${style.lineWidth}%`;

  if (pos === "top") Object.assign(base, { top: style.lineOffset, left: "50%", transform: "translateX(-50%)", width: autoW, height: style.lineThickness });
  if (pos === "bottom") Object.assign(base, { bottom: style.lineOffset, left: "50%", transform: "translateX(-50%)", width: autoW, height: style.lineThickness });
  if (pos === "left") Object.assign(base, { left: style.lineOffset, top: "50%", transform: "translateY(-50%)", height: autoH, width: style.lineThickness });
  if (pos === "right") Object.assign(base, { right: style.lineOffset, top: "50%", transform: "translateY(-50%)", height: autoH, width: style.lineThickness });
  if (pos === "center-h") Object.assign(base, { top: `calc(50% + ${style.lineOffset}px)`, left: "50%", transform: "translate(-50%, -50%)", width: autoW, height: style.lineThickness });
  if (pos === "center-v") Object.assign(base, { top: "50%", left: `calc(50% + ${style.lineOffset}px)`, transform: "translate(-50%, -50%)", height: autoH, width: style.lineThickness });
  if (pos === "auto-bottom") Object.assign(base, { top: `calc(${style.positionY}% + ${style.lineOffset + 20}px)`, left: "50%", transform: "translateX(-50%)", width: autoW, height: style.lineThickness });
  return <div style={base} />;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <div><h4 className="text-[11px] font-semibold text-zinc-300 mb-2 uppercase tracking-wider">{title}</h4>{children}</div>;
}

function ColorPicker({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="text-[10px] text-zinc-500 block mb-1">{label}</label>
      <div className="flex items-center gap-2 bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5">
        <input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="w-5 h-5 rounded border-0 cursor-pointer bg-transparent" />
        <span className="text-[10px] text-zinc-400 font-mono">{value}</span>
      </div>
    </div>
  );
}

function RangeInput({ label, min, max, value, onChange }: { label: string; min: number; max: number; value: number; onChange: (v: number) => void }) {
  const percent = ((value - min) / (max - min)) * 100;
  return (
    <div>
      <label className="text-[10px] text-zinc-500 block mb-1">{label}</label>
      <div className="relative w-full h-6 flex items-center">
        <div className="absolute left-0 right-0 h-2 bg-zinc-700 rounded-full" />
        <div className="absolute left-0 h-2 bg-emerald-600 rounded-full" style={{ width: `${percent}%` }} />
        <input type="range" min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))} className="absolute w-full h-6 opacity-0 cursor-pointer z-10" />
        <div className="absolute w-4 h-4 bg-emerald-500 rounded-full shadow-lg border-2 border-emerald-400 pointer-events-none" style={{ left: `calc(${percent}% - 8px)` }} />
      </div>
    </div>
  );
}

function Checkbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="w-3.5 h-3.5 rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500/20" />
      <span className="text-[11px] text-zinc-400">{label}</span>
    </label>
  );
}

function SelectSmall({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <div>
      <label className="text-[10px] text-zinc-500 block mb-1">{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5 text-[11px] text-zinc-300 focus:outline-none focus:border-zinc-500">
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}
