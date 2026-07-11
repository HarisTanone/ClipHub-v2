import { useState, useEffect, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Play, Type, Layers, Edit3, Download, Save, X, Palette, Eye, Wand2, ChevronLeft, ChevronRight } from "lucide-react";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Input";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { VideoPreviewOverlay } from "@/components/VideoPreviewOverlay";
import { StyleEditorModal, DEFAULT_HOOK_STYLE, DEFAULT_SUBTITLE_STYLE, type HookStyle, type SubtitleStyle } from "@/components/StyleEditorModal";
import { jobs, API_BASE, type ClipDetailResponse } from "@/lib/api";
import { formatDuration, cn } from "@/lib/utils";

type PreviewQuality = "original" | "720" | "480" | "360";

export function ClipViewer() {
  const { jobId, rank } = useParams<{ jobId: string; rank: string }>();
  const toast = useToast();
  const { user } = useAuth();
  const videoRef = useRef<HTMLVideoElement>(null);
  const pendingSeekRef = useRef<number | null>(null);

  const [clip, setClip] = useState<ClipDetailResponse["data"] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);

  // Preview - default OFF
  const [showHook, setShowHook] = useState(false);
  const [showSubtitles, setShowSubtitles] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [previewQuality, setPreviewQuality] = useState<PreviewQuality>("original");

  // Hook editing
  const [isEditingHook, setIsEditingHook] = useState(false);
  const [hookText, setHookText] = useState("");
  const [isSavingHook, setIsSavingHook] = useState(false);

  // Style editor modal (same as NewJob) — load from localStorage
  const [styleModalOpen, setStyleModalOpen] = useState(false);
  const [hookStyleConfig, setHookStyleConfig] = useState<HookStyle>(() => {
    try { const s = localStorage.getItem("autocliper_hook_style"); return s ? { ...DEFAULT_HOOK_STYLE, ...JSON.parse(s) } : DEFAULT_HOOK_STYLE; } catch { return DEFAULT_HOOK_STYLE; }
  });
  const [subtitleStyleConfig, setSubtitleStyleConfig] = useState<SubtitleStyle>(() => {
    try { const s = localStorage.getItem("autocliper_subtitle_style"); return s ? { ...DEFAULT_SUBTITLE_STYLE, ...JSON.parse(s) } : DEFAULT_SUBTITLE_STYLE; } catch { return DEFAULT_SUBTITLE_STYLE; }
  });
  const [isRestyling, setIsRestyling] = useState(false);
  const [videoRevision, setVideoRevision] = useState(0);

  // Other clips from same job
  const [otherClips, setOtherClips] = useState<any[]>([]);

  const clipRank = rank ? parseInt(rank) : 0;

  async function loadClip() {
    if (!jobId || !rank) return;
    setIsLoading(true);
    try {
      const [clipRes, detailRes] = await Promise.all([
        jobs.getClipDetail(jobId, clipRank),
        jobs.getDetail(jobId),
      ]);
      setClip(clipRes.data);
      setHookText(clipRes.data.hook || "");
      if (clipRes.data.hook_style_config && Object.keys(clipRes.data.hook_style_config).length > 0) {
        setHookStyleConfig({ ...DEFAULT_HOOK_STYLE, ...clipRes.data.hook_style_config } as HookStyle);
      }
      if (clipRes.data.subtitle_style_config && Object.keys(clipRes.data.subtitle_style_config).length > 0) {
        setSubtitleStyleConfig({ ...DEFAULT_SUBTITLE_STYLE, ...clipRes.data.subtitle_style_config } as SubtitleStyle);
      }
      // Set other clips (exclude current)
      const allClips = detailRes.data.clips || [];
      setOtherClips(allClips.filter((c: any) => c.rank !== clipRank));
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => { loadClip(); }, [jobId, rank]);

  async function handleSaveHook() {
    if (!jobId || !hookText.trim()) return;
    setIsSavingHook(true);
    try {
      await jobs.editHook(jobId, clipRank, hookText.trim());
      toast.success("Hook updated");
      setIsEditingHook(false);
      loadClip();
    } catch (e: any) { toast.error(e.message || "Failed to save"); }
    finally { setIsSavingHook(false); }
  }

  async function handleRestyle() {
    if (!jobId) return;
    setIsRestyling(true);
    try {
      const res = await jobs.restyle(jobId, clipRank, {
        hook_text: hookText.trim() || undefined,
        hook_style: hookStyleConfig.animation,
        hook_style_config: hookStyleConfig,
        subtitle_style_config: subtitleStyleConfig,
        subtitle_enabled: true,
      });
      setShowRaw(false);
      setPreviewMode(false);
      setVideoRevision(Date.now());
      await loadClip();
      toast.success(res.message || `Clip #${clipRank} updated`);
    } catch (e: any) { toast.error(e.message || "Restyle failed"); }
    finally { setIsRestyling(false); }
  }

  function handlePreviewQualityChange(quality: PreviewQuality) {
    pendingSeekRef.current = videoRef.current?.currentTime ?? null;
    setPreviewQuality(quality);
  }

  if (isLoading && !clip) {
    return <div className="space-y-3"><SkeletonCard /><SkeletonCard /></div>;
  }

  if (error || !clip) {
    return (
      <EmptyState title="Clip not found" description={error || "Could not load clip details"}
        action={<Link to={`/jobs/${jobId}`}><Button variant="secondary" size="sm">Back to Job</Button></Link>} />
    );
  }

  const rawUrl = clip.urls.raw ? `${API_BASE}${clip.urls.raw}` : null;
  const finalDownloadUrl = clip.urls.final ? `${API_BASE}${clip.urls.final}` : null;
  const finalPreviewUrl = finalDownloadUrl && !showRaw
    ? jobs.getClipFinalUrl(jobId!, clipRank, previewQuality)
    : finalDownloadUrl;
  const versionedFinalUrl = finalPreviewUrl
    ? `${finalPreviewUrl}${finalPreviewUrl.includes("?") ? "&" : "?"}v=${videoRevision}`
    : null;
  const videoUrl = showRaw ? (rawUrl || versionedFinalUrl) : (versionedFinalUrl || rawUrl);

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0 mb-3">
        <div className="flex items-center gap-3 min-w-0">
          <Link to={`/jobs/${jobId}`} className="rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 transition-colors">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-base font-semibold text-zinc-100">Clip #{clipRank}</h1>
              {clip.score && <Badge variant="success" size="sm">Score: {clip.score}</Badge>}
              <Badge variant="default" size="sm">{formatDuration(clip.duration)}</Badge>
            </div>
            {clip.hook && <p className="text-[11px] text-zinc-500 truncate max-w-[400px]">{clip.hook}</p>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={() => setStyleModalOpen(true)} icon={<Palette className="h-3.5 w-3.5" />}>
            Style Editor
          </Button>
          <Button variant="primary" size="sm" onClick={handleRestyle} loading={isRestyling} icon={<Wand2 className="h-3.5 w-3.5" />}>
            Restyle
          </Button>
        </div>
      </div>

      {/* Main: Video + Sidebar */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-3 min-h-0 overflow-hidden">
        {/* Video panel */}
        <div className="flex flex-col gap-2 lg:col-span-7 min-h-0">
          <Card className="p-0 overflow-hidden flex-1 flex flex-col min-h-0">
            <div className="relative bg-black flex-1 min-h-[250px]">
              {videoUrl ? (
                <>
                  <video
                    ref={videoRef}
                    src={videoUrl}
                    className="w-full h-full object-contain"
                    onTimeUpdate={() => videoRef.current && setCurrentTime(videoRef.current.currentTime)}
                    onLoadedMetadata={() => {
                      if (videoRef.current && pendingSeekRef.current !== null) {
                        videoRef.current.currentTime = pendingSeekRef.current;
                        pendingSeekRef.current = null;
                      }
                    }}
                    playsInline
                    preload="auto"
                    controls
                  />
                  {previewMode && (
                    <VideoPreviewOverlay
                      currentTime={currentTime}
                      hookText={hookText || clip.hook || ""}
                      hookStyle={hookStyleConfig.animation}
                      hookStyleConfig={hookStyleConfig}
                      subtitleStyleConfig={subtitleStyleConfig}
                      words={clip.words || []}
                      showHook={showHook}
                      showSubtitles={showSubtitles}
                    />
                  )}
                </>
              ) : (
                <div className="absolute inset-0 flex items-center justify-center">
                  <Play className="h-10 w-10 text-zinc-700" />
                </div>
              )}
            </div>
          </Card>

          {/* Controls */}
          <div className="flex items-center gap-1.5 flex-wrap shrink-0">
            <ToggleBtn label={showRaw ? "RAW" : "FINAL"} active={showRaw} onClick={() => setShowRaw(!showRaw)} color="amber" />
            <ToggleBtn label="Preview" active={previewMode} onClick={() => setPreviewMode(!previewMode)} icon={<Eye className="h-3 w-3" />} />
            <ToggleBtn label="Hook" active={showHook} onClick={() => setShowHook(!showHook)} icon={<Type className="h-3 w-3" />} />
            <ToggleBtn label="Sub" active={showSubtitles} onClick={() => setShowSubtitles(!showSubtitles)} icon={<Layers className="h-3 w-3" />} />
            <QualitySelect
              value={previewQuality}
              onChange={handlePreviewQualityChange}
              disabled={showRaw || !finalDownloadUrl}
            />
            <div className="ml-auto flex gap-1.5">
              {rawUrl && <a href={rawUrl} download><Button variant="outline" size="xs" icon={<Download className="h-3 w-3" />}>Raw</Button></a>}
              {finalDownloadUrl && <a href={finalDownloadUrl} download><Button variant="primary" size="xs" icon={<Download className="h-3 w-3" />}>Final</Button></a>}
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="lg:col-span-5 min-h-0 overflow-y-auto space-y-3">
          {/* Other clips - horizontal carousel with arrows */}
          {otherClips.length > 0 && (
            <Card className="p-3">
              <h3 className="text-xs font-semibold text-zinc-300 mb-2">Other Clips ({otherClips.length})</h3>
              <OtherClipsCarousel clips={otherClips} jobId={jobId!} />
            </Card>
          )}

          {/* Style summary */}
          <Card className="p-3">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-semibold text-zinc-300">Current Style</h3>
              <Button type="button" variant="ghost" size="xs" onClick={() => setStyleModalOpen(true)} icon={<Palette className="h-3 w-3" />}>Edit</Button>
            </div>
            <div className="space-y-1">
              <MiniRow label="Hook Animation" value={hookStyleConfig.animation.replace(/_/g, " ")} />
              <MiniRow label="Hook Font" value={hookStyleConfig.fontFamily} />
              <MiniRow label="Hook Color" value={hookStyleConfig.color} color={hookStyleConfig.color} />
              <MiniRow label="Sub Font" value={subtitleStyleConfig.fontFamily} />
              <MiniRow label="Sub Highlight" value={subtitleStyleConfig.highlightColor} color={subtitleStyleConfig.highlightColor} />
              <MiniRow label="Sub Position" value={subtitleStyleConfig.position} />
              {hookStyleConfig.glowEnabled && <MiniRow label="Glow" value="ON" highlight />}
              {hookStyleConfig.lineEnabled && <MiniRow label="Accent Line" value={hookStyleConfig.linePosition} highlight />}
            </div>
          </Card>

          {/* Words */}
          {clip.words && clip.words.length > 0 && (
            <Card className="p-3">
              <h3 className="text-xs font-semibold text-zinc-300 mb-2">Transcript ({clip.words.length} words)</h3>
              <div className="flex flex-wrap gap-0.5 max-h-32 overflow-y-auto">
                {clip.words.map((w, i) => (
                  <span key={i} className={cn("text-[10px] px-1 py-0.5 rounded",
                    currentTime >= w.start && currentTime <= w.end + 0.3
                      ? "bg-emerald-500/30 text-emerald-300 font-bold"
                      : "text-zinc-500"
                  )}>{w.word}</span>
                ))}
              </div>
            </Card>
          )}

          {/* Info */}
          <Card className="p-3">
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px]">
              <span className="text-zinc-500">Timeline</span><span className="text-zinc-300">{clip.start?.toFixed(1)}s → {clip.end?.toFixed(1)}s</span>
              <span className="text-zinc-500">Duration</span><span className="text-zinc-300">{formatDuration(clip.duration)}</span>
              <span className="text-zinc-500">Words</span><span className="text-zinc-300">{clip.words?.length || 0}</span>
              <span className="text-zinc-500">Raw</span><span className={clip.file_status.raw ? "text-emerald-400" : "text-zinc-600"}>{clip.file_status.raw ? "Ready" : "Missing"}</span>
              <span className="text-zinc-500">Final</span><span className={clip.file_status.final ? "text-emerald-400" : "text-zinc-600"}>{clip.file_status.final ? "Ready" : "Missing"}</span>
            </div>
          </Card>

          {/* Hook Text - at bottom */}
          <Card className="p-3">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-semibold text-zinc-300">Hook Text</h3>
              <Button type="button" variant="ghost" size="xs" onClick={() => setIsEditingHook(!isEditingHook)} icon={isEditingHook ? <X className="h-3 w-3" /> : <Edit3 className="h-3 w-3" />}>
                {isEditingHook ? "Cancel" : "Edit"}
              </Button>
            </div>
            {isEditingHook ? (
              <div className="space-y-2">
                <Textarea value={hookText} onChange={(e) => setHookText(e.target.value)} rows={2} placeholder="Hook text..." />
                <Button size="xs" onClick={handleSaveHook} loading={isSavingHook} icon={<Save className="h-3 w-3" />}>Save</Button>
              </div>
            ) : (
              <p className="text-[12px] text-zinc-300 bg-zinc-900/60 rounded-lg p-2.5 leading-relaxed">{clip.hook || "No hook"}</p>
            )}
          </Card>
        </div>
      </div>

      {/* Style Editor Modal - same as NewJob */}
      <StyleEditorModal
        open={styleModalOpen}
        onClose={() => setStyleModalOpen(false)}
        hookStyle={hookStyleConfig}
        subtitleStyle={subtitleStyleConfig}
        onHookChange={setHookStyleConfig}
        onSubtitleChange={setSubtitleStyleConfig}
        aspectRatio="9:16"
        isSuperadmin={user?.is_superadmin}
        userFeatures={user?.features}
      />
    </div>
  );
}

function ToggleBtn({ label, active, onClick, icon, color = "emerald" }: { label: string; active: boolean; onClick: () => void; icon?: React.ReactNode; color?: string }) {
  const activeClass = color === "amber" ? "border-amber-500/40 bg-amber-500/8 text-amber-400" : "border-emerald-500/40 bg-emerald-500/8 text-emerald-400";
  return (
    <button type="button" onClick={onClick} className={cn("flex items-center gap-1 rounded-lg border px-2 py-1 text-[10px] font-medium transition-colors", active ? activeClass : "border-zinc-800 bg-zinc-900/50 text-zinc-500")}>
      {icon}{label}
    </button>
  );
}

function QualitySelect({
  value,
  onChange,
  disabled,
}: {
  value: PreviewQuality;
  onChange: (quality: PreviewQuality) => void;
  disabled?: boolean;
}) {
  return (
    <label className={cn(
      "flex items-center gap-1 rounded-lg border px-2 py-1 text-[10px] font-medium transition-colors",
      disabled ? "border-zinc-900 bg-zinc-950/40 text-zinc-700" : "border-zinc-800 bg-zinc-900/50 text-zinc-400"
    )}>
      <span>Quality</span>
      <select
        aria-label="Preview quality"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value as PreviewQuality)}
        className="bg-transparent text-zinc-200 outline-none disabled:text-zinc-700"
      >
        <option value="original">Original</option>
        <option value="720">720p</option>
        <option value="480">480p</option>
        <option value="360">360p</option>
      </select>
    </label>
  );
}

function MiniRow({ label, value, highlight, color }: { label: string; value: string; highlight?: boolean; color?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[10px] text-zinc-500">{label}</span>
      <span className={cn("text-[10px] font-medium", highlight ? "text-emerald-400" : "text-zinc-300")} style={color ? { color } : undefined}>{value}</span>
    </div>
  );
}

function OtherClipsCarousel({ clips, jobId }: { clips: any[]; jobId: string }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  function scroll(dir: "left" | "right") {
    if (!scrollRef.current) return;
    const amount = scrollRef.current.offsetWidth * 0.8;
    scrollRef.current.scrollBy({ left: dir === "left" ? -amount : amount, behavior: "smooth" });
  }

  return (
    <div className="relative">
      {clips.length > 3 && (
        <>
          <button type="button" onClick={() => scroll("left")}
            className="absolute -left-1 top-1/2 -translate-y-1/2 z-10 w-6 h-6 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center text-zinc-400 hover:text-white hover:bg-zinc-700 transition-colors">
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <button type="button" onClick={() => scroll("right")}
            className="absolute -right-1 top-1/2 -translate-y-1/2 z-10 w-6 h-6 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center text-zinc-400 hover:text-white hover:bg-zinc-700 transition-colors">
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </>
      )}

      <div ref={scrollRef} className="flex gap-2 overflow-x-auto scrollbar-hide snap-x px-1">
        {clips.map((c) => {
          const finalSrc = c.has_final ? jobs.getClipFinalUrl(jobId, c.rank) : `${API_BASE}/api/jobs/${jobId}/clips/${c.rank}/raw`;
          const thumbUrl = c.has_thumbnail ? jobs.getClipThumbUrl(jobId, c.rank) : null;
          return (
            <Link key={c.rank} to={`/jobs/${jobId}/clips/${c.rank}`}
              className="shrink-0 w-[calc(33.33%-6px)] min-w-[100px] snap-start rounded-lg border border-zinc-800/60 overflow-hidden hover:border-zinc-600 transition-colors group">
              <div className="aspect-[9/16] bg-zinc-950 relative overflow-hidden">
                <video
                  src={finalSrc}
                  poster={thumbUrl || undefined}
                  className="w-full h-full object-cover"
                  autoPlay
                  muted
                  loop
                  playsInline
                  preload="auto"
                />
                <span className="absolute top-1 left-1 bg-black/80 text-[8px] text-white font-bold px-1 py-0.5 rounded">#{c.rank}</span>
                {c.score && <span className="absolute bottom-1 left-1 bg-emerald-600/90 text-[7px] text-white font-bold px-1 py-0.5 rounded">{c.score}</span>}
                {c.has_final && <span className="absolute top-1 right-1 bg-emerald-500/90 text-[7px] text-white px-1 py-0.5 rounded">Ready</span>}
              </div>
              <div className="p-1.5">
                <p className="text-[9px] text-zinc-300 font-medium truncate">{c.hook || `Clip ${c.rank}`}</p>
                <div className="flex items-center gap-1 mt-0.5">
                  <span className="text-[8px] text-zinc-500">{c.duration ? formatDuration(c.duration) : ""}</span>
                  {c.score && <span className="text-[8px] bg-emerald-500/20 text-emerald-400 font-bold px-1 py-0.5 rounded">{c.score}</span>}
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
