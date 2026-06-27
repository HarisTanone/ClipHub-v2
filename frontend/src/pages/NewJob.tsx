import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Send, Monitor, Smartphone, Square, Clock, Eye, User, Palette, Type, Sparkles, ChevronLeft, ChevronRight, Bookmark, Save } from "lucide-react";
import { Link } from "react-router-dom";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Toggle } from "@/components/ui/Toggle";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { StyleEditorModal, DEFAULT_HOOK_STYLE, DEFAULT_SUBTITLE_STYLE, type HookStyle, type SubtitleStyle } from "@/components/StyleEditorModal";
import { FeatureLock } from "@/components/ui/FeatureLock";
import { jobs, preview, presets as presetsApi, type VideoPreview, type Preset, API_BASE } from "@/lib/api";
import { cn, formatDuration } from "@/lib/utils";

export function NewJob() {
  const navigate = useNavigate();
  const toast = useToast();
  const { user } = useAuth();
  const [url, setUrl] = useState("");
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [templateMode] = useState<"custom">("custom");
  const [forceReprocess, setForceReprocess] = useState(false);
  const [smartCamera, setSmartCamera] = useState(false);
  const [smartSubtitlePos, setSmartSubtitlePos] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [urlError, setUrlError] = useState("");

  // Style editor inline (not modal)
  const [styleTab, setStyleTab] = useState<"presets" | "hook" | "subtitle">("hook");
  const [hookStyleConfig, setHookStyleConfig] = useState<HookStyle>(() => {
    try { const s = localStorage.getItem("autocliper_hook_style"); return s ? JSON.parse(s) : DEFAULT_HOOK_STYLE; } catch { return DEFAULT_HOOK_STYLE; }
  });
  const [subtitleStyleConfig, setSubtitleStyleConfig] = useState<SubtitleStyle>(() => {
    try { const s = localStorage.getItem("autocliper_subtitle_style"); return s ? JSON.parse(s) : DEFAULT_SUBTITLE_STYLE; } catch { return DEFAULT_SUBTITLE_STYLE; }
  });

  useEffect(() => { localStorage.setItem("autocliper_hook_style", JSON.stringify(hookStyleConfig)); }, [hookStyleConfig]);
  useEffect(() => { localStorage.setItem("autocliper_subtitle_style", JSON.stringify(subtitleStyleConfig)); }, [subtitleStyleConfig]);

  // YouTube preview
  const [videoMeta, setVideoMeta] = useState<VideoPreview | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const previewTimeout = useRef<number | null>(null);

  // User presets
  const [userPresets, setUserPresets] = useState<Preset[]>([]);
  const [presetPage, setPresetPage] = useState(0);
  const [savingPreset, setSavingPreset] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [showSavePreset, setShowSavePreset] = useState(false);
  const [activePresetId, setActivePresetId] = useState<number | null>(null);
  const presetsPerPage = 3;

  useEffect(() => {
    presetsApi.list().then(setUserPresets).catch(() => { });
  }, []);

  function loadPreset(preset: Preset) {
    setHookStyleConfig({ ...DEFAULT_HOOK_STYLE, ...preset.hook_style } as HookStyle);
    setSubtitleStyleConfig({ ...DEFAULT_SUBTITLE_STYLE, ...preset.subtitle_style } as SubtitleStyle);
    setActivePresetId(preset.id);
    toast.success(`Loaded: ${preset.name}`);
  }

  async function handleSavePreset() {
    if (!presetName.trim()) { toast.error("Name required"); return; }
    setSavingPreset(true);
    try {
      await presetsApi.create(presetName.trim(), hookStyleConfig, subtitleStyleConfig);
      toast.success(`Preset "${presetName}" saved`);
      setPresetName("");
      setShowSavePreset(false);
      const list = await presetsApi.list();
      setUserPresets(list);
    } catch (e: any) {
      toast.error(e.message || "Failed to save preset");
    } finally {
      setSavingPreset(false);
    }
  }

  const totalPresetPages = Math.max(1, Math.ceil(userPresets.length / presetsPerPage));
  const visiblePresets = userPresets.slice(presetPage * presetsPerPage, (presetPage + 1) * presetsPerPage);

  const aspectOptions = [
    { value: "9:16", icon: Smartphone, label: "9:16", desc: "Shorts" },
    { value: "16:9", icon: Monitor, label: "16:9", desc: "YouTube" },
    { value: "1:1", icon: Square, label: "1:1", desc: "Instagram" },
  ];

  function validateUrl(value: string): boolean {
    if (!value.trim()) { setUrlError("URL required"); return false; }
    const pattern = /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\/)[a-zA-Z0-9_-]+/;
    if (!pattern.test(value)) { setUrlError("Enter a valid YouTube URL"); return false; }
    setUrlError("");
    return true;
  }

  function handleUrlChange(value: string) {
    setUrl(value);
    if (urlError) validateUrl(value);
    if (previewTimeout.current) clearTimeout(previewTimeout.current);
    setVideoMeta(null);
    const pattern = /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\/)[a-zA-Z0-9_-]{11}/;
    if (pattern.test(value)) {
      previewTimeout.current = window.setTimeout(async () => {
        setIsLoadingPreview(true);
        try { setVideoMeta(await preview.fetchMetadata(value.trim())); } catch { }
        finally { setIsLoadingPreview(false); }
      }, 600);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validateUrl(url)) return;
    setIsSubmitting(true);
    // Auto-prefix https:// if missing
    let submitUrl = url.trim();
    if (!submitUrl.startsWith("http")) {
      submitUrl = "https://www." + submitUrl;
    } else if (submitUrl.startsWith("http://")) {
      submitUrl = submitUrl.replace("http://", "https://");
    }
    try {
      const res = await jobs.create({
        youtube_url: submitUrl,
        target_aspect_ratio: aspectRatio,
        hook_style: hookStyleConfig.animation || undefined,
        force_reprocess: forceReprocess,
        use_remotion: true,
        ai_layer_enabled: true,
        threejs_enabled: false,
        remotion_quality: "medium",
        hook_style_config: { ...hookStyleConfig, template_mode: templateMode },
        subtitle_style_config: subtitleStyleConfig,
        smart_camera: smartCamera,
        smart_subtitle_position: smartSubtitlePos,
      });
      toast.success(`Job created: ${res.job_id}`);
      navigate(`/jobs/${res.job_id}`);
    } catch (e: any) {
      toast.error(e.message || "Failed to create job");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0 mb-3">
        <div className="flex items-center gap-3">
          <Link to="/" className="rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 transition-colors">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="text-base font-semibold text-zinc-100">New Job</h1>
        </div>
        <Button type="button" size="sm" loading={isSubmitting} onClick={handleSubmit} icon={<Send className="h-3.5 w-3.5" />}>
          Start Processing
        </Button>
      </div>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-3 min-h-0 overflow-hidden">
        {/* Left: URL + Config (col-4) */}
        <div className="lg:col-span-4 space-y-3 overflow-y-auto">
          {/* URL */}
          <Card className="p-3">
            <Input label="YouTube URL" placeholder="https://youtube.com/watch?v=..." type="url" value={url} onChange={(e) => handleUrlChange(e.target.value)} error={urlError} />
            {(isLoadingPreview || videoMeta) && (
              <div className="mt-2 rounded-lg border border-zinc-800/60 bg-zinc-900/50 overflow-hidden">
                {isLoadingPreview && !videoMeta ? (
                  <div className="flex items-center gap-2 p-2"><div className="h-3 w-3 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin" /><span className="text-[10px] text-zinc-500">Loading...</span></div>
                ) : videoMeta ? (
                  <div className="flex gap-2 p-2">
                    <img src={videoMeta.thumbnail} alt="" className="shrink-0 w-20 h-12 rounded object-cover" />
                    <div className="flex-1 min-w-0">
                      <p className="text-[11px] text-zinc-200 font-medium line-clamp-1">{videoMeta.title}</p>
                      <p className="text-[9px] text-zinc-500 flex items-center gap-1.5 mt-0.5">
                        <span>{videoMeta.channel}</span><span>{videoMeta.duration_string}</span>
                      </p>
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </Card>

          {/* Aspect */}
          <Card className="p-3">
            <label className="block text-[10px] font-medium text-zinc-500 mb-2 uppercase tracking-wider">Aspect Ratio</label>
            <div className="grid grid-cols-3 gap-1.5">
              {aspectOptions.map((opt) => (
                <button key={opt.value} type="button" onClick={() => setAspectRatio(opt.value)}
                  className={cn("flex flex-col items-center gap-0.5 rounded-lg border py-2 transition-all",
                    aspectRatio === opt.value ? "border-emerald-500/60 bg-emerald-500/8 text-emerald-400" : "border-zinc-800 text-zinc-500 hover:border-zinc-700")}>
                  <opt.icon className="h-4 w-4" />
                  <span className="text-[10px] font-medium">{opt.label}</span>
                </button>
              ))}
            </div>
          </Card>

          {/* Options */}
          <Card className="p-3">
            <Toggle label="Force Reprocess" description={videoMeta?.cache?.has_cache ? "Video sudah pernah diproses. Aktifkan untuk proses ulang dari awal." : "Proses ulang meski video sudah pernah diproses"} checked={forceReprocess} onChange={setForceReprocess} />
            {videoMeta?.cache && (
              <div className={cn("mt-2 rounded-lg px-2.5 py-2 text-[10px]", videoMeta.cache.has_cache ? "bg-amber-500/8 border border-amber-500/20" : "bg-zinc-800/50 border border-zinc-800")}>
                {videoMeta.cache.has_cache ? (
                  <div className="space-y-0.5">
                    <p className="text-amber-400 font-medium">⚡ Cache tersedia</p>
                    <p className="text-zinc-400">{videoMeta.cache.clips_success} clips berhasil • diproses {videoMeta.cache.processed_at ? new Date(videoMeta.cache.processed_at).toLocaleDateString("id-ID") : ""}</p>
                    {!forceReprocess && <p className="text-zinc-500 italic">Akan menggunakan hasil sebelumnya</p>}
                    {forceReprocess && <p className="text-emerald-400">✓ Akan diproses ulang dari awal</p>}
                  </div>
                ) : videoMeta.cache.has_transcript ? (
                  <p className="text-zinc-400">📝 Transcript tersedia, clip belum diproses</p>
                ) : (
                  <p className="text-zinc-500">Video belum pernah diproses</p>
                )}
              </div>
            )}
          </Card>

          {/* Smart Features */}
          <Card className="p-3">
            <label className="block text-[10px] font-medium text-zinc-500 mb-2 uppercase tracking-wider">Smart Features</label>
            <div className="space-y-2">
              <FeatureLock featureName="Smart Camera" featureCode="smart_camera" isSuperadmin={user?.is_superadmin} isPremium={user?.is_premium} userFeatures={user?.features}>
                <Toggle label="Smart Camera" description="Photography framing (eye-level, headroom, tracking)" checked={smartCamera} onChange={setSmartCamera} />
              </FeatureLock>
              <FeatureLock featureName="Smart Subtitle Position" featureCode="smart_subtitle_pos" isSuperadmin={user?.is_superadmin} isPremium={user?.is_premium} userFeatures={user?.features}>
                <Toggle label="Smart Subtitle Position" description="Auto posisi subtitle (hindari wajah)" checked={smartSubtitlePos} onChange={setSmartSubtitlePos} />
              </FeatureLock>
            </div>
          </Card>

          {/* Presets Carousel */}
          <Card className="p-3">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5">
                <Bookmark className="h-3 w-3 text-emerald-400" />
                <h3 className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">My Presets</h3>
              </div>
              <button type="button" onClick={() => setShowSavePreset(!showSavePreset)} className="text-[10px] text-emerald-400 hover:text-emerald-300 font-medium transition-colors">
                {showSavePreset ? "Cancel" : "+ Save Current"}
              </button>
            </div>

            {showSavePreset && (
              <div className="flex gap-1.5 mb-2">
                <input type="text" value={presetName} onChange={(e) => setPresetName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), handleSavePreset())} placeholder="Preset name..." className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5 text-[11px] text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50" />
                <Button type="button" size="xs" loading={savingPreset} onClick={handleSavePreset} icon={<Save className="h-3 w-3" />}>Save</Button>
              </div>
            )}

            {userPresets.length === 0 ? (
              <p className="text-[10px] text-zinc-600 py-2 text-center">No presets yet. Save your current style above.</p>
            ) : (
              <>
                <div className="space-y-1.5">
                  {visiblePresets.map((p) => (
                    <button key={p.id} type="button" onClick={() => loadPreset(p)}
                      className={cn("w-full flex items-center gap-2 rounded-lg border px-2.5 py-2 transition-all text-left group",
                        activePresetId === p.id
                          ? "border-emerald-500 bg-emerald-500/10 ring-1 ring-emerald-500/30"
                          : "border-zinc-800 hover:border-emerald-500/50 hover:bg-emerald-500/5")}>
                      <div className={cn("shrink-0 w-5 h-5 rounded flex items-center justify-center",
                        activePresetId === p.id ? "bg-emerald-500/30" : "bg-gradient-to-br from-emerald-500/20 to-zinc-800")}>
                        <Palette className={cn("h-2.5 w-2.5", activePresetId === p.id ? "text-emerald-300" : "text-emerald-400")} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className={cn("text-[11px] font-medium truncate", activePresetId === p.id ? "text-emerald-300" : "text-zinc-300 group-hover:text-emerald-300")}>{p.name}</p>
                        <p className="text-[9px] text-zinc-600 truncate">{p.hook_style?.animation || "custom"} · {p.hook_style?.fontFamily || "Poppins"}</p>
                      </div>
                      {activePresetId === p.id && <span className="shrink-0 text-[8px] text-emerald-400 font-bold uppercase tracking-wider">Active</span>}
                    </button>
                  ))}
                </div>
                {totalPresetPages > 1 && (
                  <div className="flex items-center justify-center gap-2 mt-2">
                    <button type="button" disabled={presetPage === 0} onClick={() => setPresetPage((p) => p - 1)}
                      className="p-1 rounded text-zinc-500 hover:text-zinc-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
                      <ChevronLeft className="h-3.5 w-3.5" />
                    </button>
                    <span className="text-[9px] text-zinc-600">{presetPage + 1}/{totalPresetPages}</span>
                    <button type="button" disabled={presetPage >= totalPresetPages - 1} onClick={() => setPresetPage((p) => p + 1)}
                      className="p-1 rounded text-zinc-500 hover:text-zinc-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
                      <ChevronRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
              </>
            )}
          </Card>

          {/* Style summary */}
          <Card className="p-3">
            <h3 className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-2">Active Style</h3>
            <div className="space-y-1 text-[10px]">
              <Row label="Hook" value={hookStyleConfig.animation.replace(/_/g, " ")} />
              <Row label="Font" value={hookStyleConfig.fontFamily} />
              <Row label="Sub Highlight" value={subtitleStyleConfig.highlightColor} color={subtitleStyleConfig.highlightColor} />
              <Row label="Sub Position" value={`${subtitleStyleConfig.position} ${subtitleStyleConfig.positionY}%`} />
            </div>
          </Card>
        </div>

        {/* Right: Style Editor (col-8) */}
        <div className="lg:col-span-8 flex flex-col min-h-0 overflow-hidden">
          {/* Tabs */}
          <div className="flex items-center gap-1 mb-2 shrink-0">
            <button type="button" onClick={() => setStyleTab("presets")}
              className={cn("px-3 py-1.5 text-xs font-medium rounded-lg transition-colors", styleTab === "presets" ? "bg-emerald-600 text-white" : "bg-zinc-800 text-zinc-400 hover:text-zinc-200")}>
              <Bookmark className="h-3 w-3 inline mr-1" />Presets
            </button>
            <button type="button" onClick={() => setStyleTab("hook")}
              className={cn("px-3 py-1.5 text-xs font-medium rounded-lg transition-colors", styleTab === "hook" ? "bg-emerald-600 text-white" : "bg-zinc-800 text-zinc-400 hover:text-zinc-200")}>
              <Type className="h-3 w-3 inline mr-1" />Hook
            </button>
            <button type="button" onClick={() => setStyleTab("subtitle")}
              className={cn("px-3 py-1.5 text-xs font-medium rounded-lg transition-colors", styleTab === "subtitle" ? "bg-emerald-600 text-white" : "bg-zinc-800 text-zinc-400 hover:text-zinc-200")}>
              <Sparkles className="h-3 w-3 inline mr-1" />Subtitle
            </button>
          </div>

          {/* Style editor content */}
          <Card className="flex-1 p-0 overflow-hidden min-h-0">
            <StyleEditorModal
              open={true}
              onClose={() => { }}
              hookStyle={hookStyleConfig}
              subtitleStyle={subtitleStyleConfig}
              onHookChange={setHookStyleConfig}
              onSubtitleChange={setSubtitleStyleConfig}
              aspectRatio={aspectRatio}
              inline
              activeTab={styleTab}
              thumbnailUrl={videoMeta?.thumbnail}
              isSuperadmin={user?.is_superadmin}
              isPremium={user?.is_premium}
              userFeatures={user?.features}
              activePresetId={activePresetId}
              onPresetSelect={(id) => {
                setActivePresetId(id);
                // Navigate carousel to page containing selected preset
                const idx = userPresets.findIndex(p => p.id === id);
                if (idx >= 0) setPresetPage(Math.floor(idx / presetsPerPage));
              }}
            />
          </Card>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-zinc-500">{label}</span>
      <span className="text-zinc-300 font-medium" style={color ? { color } : undefined}>{value}</span>
    </div>
  );
}
