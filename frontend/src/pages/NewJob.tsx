import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Send, Monitor, Smartphone, Square, Clock, Palette, Type, Sparkles, ChevronLeft, ChevronRight, Bookmark, Save, Youtube, UploadCloud, FileVideo, X, MoveRight, Layers, Zap, Check, FileText, Loader2, Search } from "lucide-react";
import { Link } from "react-router-dom";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Toggle } from "@/components/ui/Toggle";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { FeatureLock } from "@/components/ui/FeatureLock";
import { StyleEditorModal, DEFAULT_HOOK_STYLE, DEFAULT_SUBTITLE_STYLE, DEFAULT_TEXT_EMPHASIS_STYLE, DEFAULT_WATERMARK_STYLE, DEFAULT_CTA_STYLE, normaliseTextEmphasisStyle, normaliseCtaStyle, type HookStyle, type SubtitleStyle, type TextEmphasisStyle, type WatermarkStyle, type CtaStyle } from "@/components/StyleEditorModal";
import { jobs, preview, presets as presetsApi, analyze, type VideoPreview, type Preset, type AnalyzeResponse, API_BASE } from "@/lib/api";
import { cn, formatDuration, extractCleanYouTubeUrl, extractVideoId } from "@/lib/utils";
import { BackgroundTemplateSection, type BackgroundMode } from "@/components/BackgroundTemplateSection";
import { ClipTimelineEditor, type EditableClip } from "@/components/ClipTimelineEditor";

export function NewJob() {
  const navigate = useNavigate();
  const toast = useToast();
  const { user } = useAuth();
  const [url, setUrl] = useState("");
  const [sourceMode, setSourceMode] = useState<"youtube" | "upload">("youtube");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState("");
  const [uploadProcessingMode, setUploadProcessingMode] = useState<"analyze" | "direct">("analyze");
  const [directHook, setDirectHook] = useState("");
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [templateMode] = useState<"custom">("custom");
  const [backgroundMode, setBackgroundMode] = useState<BackgroundMode>("template");
  const [backgroundTemplateId, setBackgroundTemplateId] = useState("dark-studio");
  const [backgroundImageDataUrl, setBackgroundImageDataUrl] = useState<string | null>(null);
  const [forceReprocess, setForceReprocess] = useState(false);
  const [brollEnabled, setBrollEnabled] = useState(false);
  const [brollImageOverlay, setBrollImageOverlay] = useState(true);
  const [brollBehindPerson, setBrollBehindPerson] = useState(true);
  const [brollVideoFootage, setBrollVideoFootage] = useState(true);
  const [autogridEnabled, setAutogridEnabled] = useState(false);
  const [textEmphasisEnabled, setTextEmphasisEnabled] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [urlError, setUrlError] = useState("");

  // ─── Analyze-only flow state ─────────────────────────────────────
  const [analyzeStep, setAnalyzeStep] = useState<"input" | "analyzing" | "review">("input");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzeResult, setAnalyzeResult] = useState<AnalyzeResponse | null>(null);
  const [editableClips, setEditableClips] = useState<EditableClip[]>([]);

  // Style editor inline (not modal)
  const [styleTab, setStyleTab] = useState<"presets" | "hook" | "subtitle" | "other">("hook");
  const [hookStyleConfig, setHookStyleConfig] = useState<HookStyle>(() => {
    try { const s = localStorage.getItem("autocliper_hook_style"); return s ? { ...DEFAULT_HOOK_STYLE, ...JSON.parse(s) } : DEFAULT_HOOK_STYLE; } catch { return DEFAULT_HOOK_STYLE; }
  });
  const [subtitleStyleConfig, setSubtitleStyleConfig] = useState<SubtitleStyle>(() => {
    try { const s = localStorage.getItem("autocliper_subtitle_style"); return s ? { ...DEFAULT_SUBTITLE_STYLE, ...JSON.parse(s) } : DEFAULT_SUBTITLE_STYLE; } catch { return DEFAULT_SUBTITLE_STYLE; }
  });
  const [textEmphasisStyleConfig, setTextEmphasisStyleConfig] = useState<TextEmphasisStyle>(() => {
    try { const s = localStorage.getItem("autocliper_text_emphasis_style"); return s ? normaliseTextEmphasisStyle(JSON.parse(s)) : DEFAULT_TEXT_EMPHASIS_STYLE; } catch { return DEFAULT_TEXT_EMPHASIS_STYLE; }
  });
  const [watermarkStyleConfig, setWatermarkStyleConfig] = useState<WatermarkStyle>(() => {
    try { const s = localStorage.getItem("autocliper_watermark_style"); return s ? { ...DEFAULT_WATERMARK_STYLE, ...JSON.parse(s) } : DEFAULT_WATERMARK_STYLE; } catch { return DEFAULT_WATERMARK_STYLE; }
  });
  const [ctaStyleConfig, setCtaStyleConfig] = useState<CtaStyle>(() => {
    try { const s = localStorage.getItem("autocliper_cta_style"); return s ? normaliseCtaStyle(JSON.parse(s)) : DEFAULT_CTA_STYLE; } catch { return DEFAULT_CTA_STYLE; }
  });

  useEffect(() => { localStorage.setItem("autocliper_hook_style", JSON.stringify(hookStyleConfig)); }, [hookStyleConfig]);
  useEffect(() => { localStorage.setItem("autocliper_subtitle_style", JSON.stringify(subtitleStyleConfig)); }, [subtitleStyleConfig]);
  useEffect(() => { localStorage.setItem("autocliper_text_emphasis_style", JSON.stringify(textEmphasisStyleConfig)); }, [textEmphasisStyleConfig]);
  useEffect(() => { localStorage.setItem("autocliper_watermark_style", JSON.stringify(watermarkStyleConfig)); }, [watermarkStyleConfig]);
  useEffect(() => { localStorage.setItem("autocliper_cta_style", JSON.stringify(ctaStyleConfig)); }, [ctaStyleConfig]);

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
    if (preset.text_emphasis_style) setTextEmphasisStyleConfig(normaliseTextEmphasisStyle(preset.text_emphasis_style));
    if (preset.watermark_style) setWatermarkStyleConfig({ ...DEFAULT_WATERMARK_STYLE, ...preset.watermark_style } as WatermarkStyle);
    if (preset.cta_style) setCtaStyleConfig(normaliseCtaStyle(preset.cta_style));
    setActivePresetId(preset.id);
    toast.success(`Loaded: ${preset.name}`);
  }

  async function handleSavePreset() {
    if (!presetName.trim()) { toast.error("Name required"); return; }
    setSavingPreset(true);
    try {
      await presetsApi.create(presetName.trim(), hookStyleConfig, subtitleStyleConfig, textEmphasisStyleConfig, watermarkStyleConfig, ctaStyleConfig);
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
    const videoId = extractVideoId(value);
    if (!videoId) { setUrlError("Enter a valid YouTube URL"); return false; }
    setUrlError("");
    return true;
  }

  function validateUpload(file: File | null): boolean {
    if (!file) { setUploadError("Video file required"); return false; }
    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    if (!["mp4", "mov", "m4v", "mkv", "webm"].includes(ext)) {
      setUploadError("Use MP4, MOV, MKV, or WEBM");
      return false;
    }
    if (file.size <= 0) {
      setUploadError("File is empty");
      return false;
    }
    setUploadError("");
    return true;
  }

  function handleUrlChange(value: string) {
    setUrl(value);
    if (urlError) validateUrl(value);
    if (previewTimeout.current) clearTimeout(previewTimeout.current);
    setVideoMeta(null);
    const videoId = extractVideoId(value);
    if (videoId) {
      const cleanUrl = `https://www.youtube.com/watch?v=${videoId}`;
      previewTimeout.current = window.setTimeout(async () => {
        setIsLoadingPreview(true);
        try { setVideoMeta(await preview.fetchMetadata(cleanUrl)); } catch { }
        finally { setIsLoadingPreview(false); }
      }, 600);
    }
  }

  async function handleAnalyze() {
    if (!validateUrl(url)) return;
    setIsAnalyzing(true);
    setAnalyzeStep("analyzing");
    try {
      const submitUrl = extractCleanYouTubeUrl(url);
      const result = await analyze.analyzeOnly(submitUrl);
      setAnalyzeResult(result);
      const sortedClips = [...(result.clips || [])].sort((a, b) => a.start - b.start);
      setEditableClips(
        sortedClips.map((c, i) => ({
          ...c,
          rank: i + 1,
          ai_start: c.start,
          ai_end: c.end,
          modified: false,
        }))
      );
      setAnalyzeStep("review");
    } catch (e: any) {
      toast.error(e.message || "Analysis failed");
      setAnalyzeStep("input");
    } finally {
      setIsAnalyzing(false);
    }
  }

  function handleBackToInput() {
    setAnalyzeStep("input");
    setAnalyzeResult(null);
    setEditableClips([]);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (isSubmitting || isAnalyzing) return;
    if (sourceMode === "youtube" && !validateUrl(url)) return;
    if (sourceMode === "upload" && !validateUpload(uploadFile)) return;

    setIsSubmitting(true);
    setUploadProgress(sourceMode === "upload" ? 0 : null);

    const isFromReview = analyzeStep === "review" && editableClips.length > 0;
    const jobOptions = {
      target_aspect_ratio: aspectRatio,
      hook_style: hookStyleConfig.animation || undefined,
      force_reprocess: isFromReview ? false : (sourceMode === "youtube" ? forceReprocess : true),
      source_job_id: isFromReview ? analyzeResult?.job_id : undefined,
      use_remotion: true,
      ai_layer_enabled: true,
      threejs_enabled: false,
      remotion_quality: "medium",
      hook_style_config: {
        ...hookStyleConfig,
        engine: hookStyleConfig.engine || (hookStyleConfig.animation?.startsWith("skia_") ? "skia" : (hookStyleConfig.animation?.startsWith("hook_") ? "hyperframes" : "remotion")),
        hf_template: hookStyleConfig.hf_template,
        template_mode: templateMode,
      },
      subtitle_style_config: {
        ...subtitleStyleConfig,
        engine: subtitleStyleConfig.engine || (
          ["glassmorphism", "clean_editorial", "podcast_pro", "kinetic_word_box", "neon_tube", "gradient_fill", "cinematic_slate", "modern_mono", "bold_impact_stroke", "dual_layer", "retro_chrome", "outline_stack"].includes(subtitleStyleConfig.stylePreset || "")
          || subtitleStyleConfig.stylePreset?.startsWith("skia_")
            ? "skia"
            : (subtitleStyleConfig.hf_template?.startsWith("sub_") ? "hyperframes" : "ffmpeg")
        ),
        hf_template: subtitleStyleConfig.hf_template,
      },
      broll_enabled: brollEnabled,
      broll_image_overlay: brollEnabled ? brollImageOverlay : false,
      broll_behind_person: brollEnabled ? brollBehindPerson : false,
      broll_video_footage: brollEnabled ? brollVideoFootage : false,
      autogrid_enabled: aspectRatio === "9:16" ? autogridEnabled : false,
      text_emphasis_enabled: textEmphasisEnabled,
      text_emphasis_style_config: textEmphasisStyleConfig,
      watermark_config: watermarkStyleConfig,
      cta_config: ctaStyleConfig,
      processing_mode: sourceMode === "upload" ? uploadProcessingMode : "analyze" as const,
      custom_hook: sourceMode === "upload" && uploadProcessingMode === "direct"
        ? directHook.trim() || undefined
        : undefined,
      // Custom clips from analyze-review step (user-adjusted timestamps & hooks)
      ...(editableClips.length > 0 ? {
        custom_clips: editableClips.map((c) => ({
          rank: c.rank,
          start: c.start,
          end: c.end,
          hook: c.hook,
          score: c.score,
        })),
      } : {}),
      ...(aspectRatio === "16:9" || aspectRatio === "1:1"
        ? {
          background_mode: backgroundMode,
          background_template_id: backgroundMode === "template" ? backgroundTemplateId : undefined,
          background_image_data_url:
            backgroundMode === "upload" ? backgroundImageDataUrl || undefined : undefined,
        }
        : {}),
    };
    try {
      let res;
      if (sourceMode === "upload" && uploadFile) {
        res = await jobs.createUpload(uploadFile, jobOptions, (pct) => {
          setUploadProgress(pct);
        });
      } else {
        const submitUrl = extractCleanYouTubeUrl(url);
        res = await jobs.create({ youtube_url: submitUrl, ...jobOptions });
      }
      toast.success(`Job created: ${res.job_id}`);
      navigate(`/jobs/${res.job_id}`);
    } catch (e: any) {
      toast.error(e.message || "Failed to create job");
    } finally {
      setIsSubmitting(false);
      setUploadProgress(null);
    }
  }

  const submitButtonLabel = isSubmitting
    ? uploadProgress !== null
      ? uploadProgress >= 100
        ? "Processing Video..."
        : `Uploading (${uploadProgress}%)...`
      : "Creating Job..."
    : "Start Processing";

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0 mb-3">
        <div className="flex items-center gap-3">
          {analyzeStep === "review" ? (
            <button type="button" onClick={handleBackToInput} className="rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 transition-colors">
              <ArrowLeft className="h-4 w-4" />
            </button>
          ) : (
            <Link to="/" className="rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 transition-colors">
              <ArrowLeft className="h-4 w-4" />
            </Link>
          )}
          <h1 className="text-base font-semibold text-zinc-100">
            {analyzeStep === "review" ? "Review Clips" : "New Job"}
          </h1>
          {analyzeStep === "review" && analyzeResult && (
            <span className="text-[10px] text-zinc-500 font-medium">
              {analyzeResult.video_title}
            </span>
          )}
        </div>
        {analyzeStep === "review" ? (
          <Button
            type="button"
            size="sm"
            loading={isSubmitting}
            disabled={isSubmitting || isAnalyzing}
            onClick={handleSubmit}
            icon={<Send className="h-3.5 w-3.5" />}
          >
            {submitButtonLabel}
          </Button>
        ) : (
          <Button
            type="button"
            size="sm"
            loading={isSubmitting}
            disabled={isSubmitting || isAnalyzing}
            onClick={handleSubmit}
            icon={<Send className="h-3.5 w-3.5" />}
          >
            {submitButtonLabel}
          </Button>
        )}
      </div>

      {/* ─── REVIEW STATE (split-view: clips + video) ─────────────────── */}
      {analyzeStep === "review" && analyzeResult && (
        <div className="flex-1 min-h-0 overflow-y-auto pb-4">
          <ClipTimelineEditor
            clips={editableClips}
            videoDuration={analyzeResult.video_duration}
            videoSrc={analyze.getSourceVideoUrl(analyzeResult.job_id)}
            onClipsChange={setEditableClips}
          />
        </div>
      )}

      {/* ─── INPUT STATE (normal form — also shows during analyzing) ──── */}
      {(analyzeStep === "input" || analyzeStep === "analyzing") && (
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-3 min-h-0 overflow-y-auto lg:overflow-hidden">
        {/* Left: URL + Config (col-4) */}
        <div className="lg:col-span-4 min-h-0 space-y-3 overflow-y-auto pb-4 lg:pb-0">
          {/* Source */}
          <Card className="p-3">
            <div className="mb-3 grid grid-cols-2 gap-1 rounded-lg border border-zinc-800 bg-zinc-950/70 p-1">
              <button
                type="button"
                onClick={() => setSourceMode("youtube")}
                className={cn("flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-[11px] font-medium transition-colors", sourceMode === "youtube" ? "bg-emerald-600 text-white" : "text-zinc-500 hover:text-zinc-300")}
              >
                <Youtube className="h-3.5 w-3.5" /> YouTube URL
              </button>
              <button
                type="button"
                onClick={() => {
                  setSourceMode("upload");
                  setUrlError("");
                  setVideoMeta(null);
                }}
                className={cn("flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-[11px] font-medium transition-colors", sourceMode === "upload" ? "bg-emerald-600 text-white" : "text-zinc-500 hover:text-zinc-300")}
              >
                <UploadCloud className="h-3.5 w-3.5" /> Upload Video
              </button>
            </div>

            {sourceMode === "youtube" ? (
              <>
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
                          {videoMeta.duration && videoMeta.duration < 45 && (
                            <p className="text-[9px] text-amber-400 mt-1">
                              Video pendek — clip yang dihasilkan AI dengan durasi di bawah 15 detik tidak akan diproses.
                            </p>
                          )}
                        </div>
                      </div>
                    ) : null}
                  </div>
                )}
                {videoMeta && (
                  <>
                    <Button
                      type="button"
                      size="sm"
                      className="mt-2 w-full"
                      loading={isAnalyzing}
                      onClick={handleAnalyze}
                      icon={<Search className="h-3.5 w-3.5" />}
                    >
                      {isAnalyzing ? "Analyzing..." : "Analyze & Preview Clips"}
                    </Button>
                    {isAnalyzing && (
                      <div className="mt-2 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.04] p-2.5">
                        <div className="flex items-center gap-2">
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-400 shrink-0" />
                          <div>
                            <p className="text-[11px] font-medium text-zinc-200">Downloading & Analyzing</p>
                            <p className="text-[9px] text-zinc-500 mt-0.5">AI sedang menganalisis video untuk menemukan momen terbaik. Mungkin 30-120 detik.</p>
                          </div>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </>
            ) : (
              <div className="space-y-2">
                <label className={cn("group flex min-h-28 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed px-3 py-4 text-center transition-colors", uploadFile ? "border-emerald-500/40 bg-emerald-500/[0.04]" : "border-zinc-700 bg-zinc-900/40 hover:border-zinc-600")}>
                  <input
                    key={uploadFile ? uploadFile.name : "empty-upload"}
                    type="file"
                    accept="video/mp4,video/quicktime,video/x-m4v,video/x-matroska,video/webm,.mp4,.mov,.m4v,.mkv,.webm"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0] || null;
                      setUploadFile(file);
                      if (file) validateUpload(file);
                    }}
                  />
                  <UploadCloud className={cn("mb-2 h-6 w-6", uploadFile ? "text-emerald-400" : "text-zinc-600 group-hover:text-zinc-400")} />
                  <span className="text-xs font-medium text-zinc-300">{uploadFile ? "Video selected" : "Choose video file"}</span>
                  <span className="mt-1 text-[10px] text-zinc-600">MP4, MOV, MKV, WEBM</span>
                </label>
                {uploadFile && (
                  <div className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/60 p-2">
                    <FileVideo className="h-4 w-4 shrink-0 text-emerald-400" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[11px] font-medium text-zinc-200">{uploadFile.name}</p>
                      <p className="text-[9px] text-zinc-600">{(uploadFile.size / 1024 / 1024).toFixed(1)} MB</p>
                    </div>
                    <button type="button" disabled={isSubmitting} onClick={() => { setUploadFile(null); setUploadError(""); }} className="rounded p-1 text-zinc-600 hover:bg-zinc-800 hover:text-zinc-300 disabled:opacity-50">
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
                {uploadProgress !== null && (
                  <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.04] p-2.5">
                    <div className="flex items-center justify-between text-[11px] font-medium text-zinc-200 mb-1.5">
                      <span className="flex items-center gap-1.5">
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-400" />
                        {uploadProgress >= 100 ? "Processing on server..." : "Uploading video..."}
                      </span>
                      <span className="text-emerald-400 font-mono text-xs">{uploadProgress}%</span>
                    </div>
                    <div className="w-full bg-zinc-800 rounded-full h-1.5 overflow-hidden">
                      <div
                        className="bg-emerald-500 h-1.5 rounded-full transition-all duration-200 ease-out"
                        style={{ width: `${Math.max(5, uploadProgress)}%` }}
                      />
                    </div>
                  </div>
                )}
                {uploadError && <p className="text-[10px] text-red-400">{uploadError}</p>}
                <div className="grid grid-cols-2 gap-2">
                  <button type="button" onClick={() => setUploadProcessingMode("analyze")} className={cn("rounded-lg border p-2 text-left", uploadProcessingMode === "analyze" ? "border-emerald-500 bg-emerald-500/10" : "border-zinc-800")}><p className="text-[11px] font-medium text-zinc-200">Analyze first</p><p className="text-[9px] text-zinc-500">Find and cut viral moments</p></button>
                  <button type="button" onClick={() => setUploadProcessingMode("direct")} className={cn("rounded-lg border p-2 text-left", uploadProcessingMode === "direct" ? "border-emerald-500 bg-emerald-500/10" : "border-zinc-800")}><p className="text-[11px] font-medium text-zinc-200">Direct edit</p><p className="text-[9px] text-zinc-500">Keep full video; subtitle + optional hook</p></button>
                </div>
                {uploadProcessingMode === "direct" && (
                  <Input
                    label="Custom Hook (optional)"
                    value={directHook}
                    onChange={(event) => setDirectHook(event.target.value)}
                    maxLength={500}
                    placeholder="Masukkan hook yang tampil di awal video"
                    hint="Kosongkan jika hanya ingin menampilkan subtitle."
                    className="text-xs"
                  />
                )}
              </div>
            )}
          </Card>

          {/* Aspect — content framing; final TikTok canvas always 9:16 */}
          <Card className="p-3">
            <label className="block text-[10px] font-medium text-zinc-500 mb-2 uppercase tracking-wider">Content Aspect</label>
            <p className="mb-2 text-[9px] text-zinc-600 leading-snug">
              Output upload TikTok selalu 9:16. Pilih framing video utama: 9:16 full-bleed, atau 16:9/1:1 di tengah + template isi atas/bawah.
            </p>
            <div className="grid grid-cols-3 gap-1.5">
              {aspectOptions.map((opt) => (
                <button key={opt.value} type="button" onClick={() => { setAspectRatio(opt.value); if (opt.value !== "9:16") setAutogridEnabled(false); }}
                  className={cn("flex flex-col items-center gap-0.5 rounded-lg border py-2 transition-all",
                    aspectRatio === opt.value ? "border-emerald-500/60 bg-emerald-500/8 text-emerald-400" : "border-zinc-800 text-zinc-500 hover:border-zinc-700")}>
                  <opt.icon className="h-4 w-4" />
                  <span className="text-[10px] font-medium">{opt.label}</span>
                </button>
              ))}
            </div>
          </Card>

          {/* Background/template — 16:9 & 1:1 only */}
          {(aspectRatio === "16:9" || aspectRatio === "1:1") && (
            <Card className="p-3">
              <BackgroundTemplateSection
                aspectRatio={aspectRatio}
                mode={backgroundMode}
                onModeChange={setBackgroundMode}
                templateId={backgroundTemplateId}
                onTemplateChange={setBackgroundTemplateId}
                uploadPreviewUrl={backgroundImageDataUrl}
                onUpload={(file) => {
                  const reader = new FileReader();
                  reader.onload = () => setBackgroundImageDataUrl(String(reader.result || ""));
                  reader.readAsDataURL(file);
                }}
                onClearUpload={() => setBackgroundImageDataUrl(null)}
                thumbnailUrl={videoMeta?.thumbnail}
              />
            </Card>
          )}

          {/* Options */}
          <Card className="p-3">
            <Toggle label="Force Reprocess" description={sourceMode === "upload" ? "Upload manual selalu diproses sebagai job baru." : videoMeta?.cache?.has_cache ? "Video sudah pernah diproses. Aktifkan untuk proses ulang dari awal." : "Proses ulang meski video sudah pernah diproses"} checked={sourceMode === "upload" ? true : forceReprocess} onChange={setForceReprocess} disabled={sourceMode === "upload"} />
            {sourceMode === "youtube" && videoMeta?.cache && (
              <div className={cn("mt-2 rounded-lg px-2.5 py-2 text-[10px]", videoMeta.cache.has_cache ? "bg-amber-500/8 border border-amber-500/20" : "bg-zinc-800/50 border border-zinc-800")}>
                {videoMeta.cache.has_cache ? (
                  <div className="space-y-0.5">
                    <p className="text-amber-400 font-medium"><Zap className="inline w-3 h-3 mr-1" />Cache tersedia</p>
                    <p className="text-zinc-400">{videoMeta.cache.clips_success} clips berhasil • diproses {videoMeta.cache.processed_at ? new Date(videoMeta.cache.processed_at).toLocaleDateString("id-ID") : ""}</p>
                    {!forceReprocess && <p className="text-zinc-500 italic">Akan menggunakan hasil sebelumnya</p>}
                    {forceReprocess && <p className="text-emerald-400"><Check className="inline w-3 h-3 mr-1" />Akan diproses ulang dari awal</p>}
                  </div>
                ) : videoMeta.cache.has_transcript ? (
                  <p className="text-zinc-400"><FileText className="inline w-3 h-3 mr-1" />Transcript tersedia, clip belum diproses</p>
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
              <Toggle
                label="Auto B-roll"
                description={brollEnabled
                  ? "AI menambahkan visual pendukung tanpa mengubah audio atau waktu subtitle."
                  : "Opsional. Video tetap menggunakan visual asli jika dinonaktifkan."}
                checked={brollEnabled}
                onChange={setBrollEnabled}
              />
              {brollEnabled && (
                <div className="ml-1 space-y-2 rounded-lg border border-zinc-800/80 bg-zinc-950/50 p-2.5">
                  <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-500">Pilihan Jenis B-Roll</p>
                  <Toggle
                    label="Floating Object Card"
                    description="Kartu visual glassmorphism + live indicator dot & label di pojok atas (OpenCV)."
                    checked={brollImageOverlay}
                    onChange={setBrollImageOverlay}
                  />
                  <Toggle
                    label="Behind Person 16:9"
                    description="Stock footage 16:9 sinematik di belakang subjek dengan efek bottom gradient fade lembut."
                    checked={brollBehindPerson}
                    onChange={setBrollBehindPerson}
                  />
                  <Toggle
                    label="Full-Frame Cutaway"
                    description="Transisi video stock relevan 2–4 detik dengan audio asli tetap mengalir utuh (L-Cut)."
                    checked={brollVideoFootage}
                    onChange={setBrollVideoFootage}
                  />
                  {!brollImageOverlay && !brollBehindPerson && !brollVideoFootage && (
                    <p className="text-[10px] text-amber-500/90">Centang minimal 1 jenis, atau matikan Auto B-roll.</p>
                  )}
                </div>
              )}
              <FeatureLock featureName="Auto Grid" featureCode="auto_grid" isSuperadmin={user?.is_superadmin} isPremium={user?.is_premium} userFeatures={user?.features}>
                <Toggle
                  label="Auto-Grid"
                  description={aspectRatio === "9:16" ? "Deteksi dulu: 1 orang = single, ≥2 orang berbeda = auto switch 2-grid (panel tidak boleh orang sama). Transisi single→grid memakai style yang dipilih user." : "Hanya tersedia untuk 9:16. YOLO, face/sound detection, dan Auto-Grid dinonaktifkan pada rasio lain."}
                  checked={autogridEnabled}
                  onChange={setAutogridEnabled}
                  disabled={aspectRatio !== "9:16"}
                />
              </FeatureLock>
              <Toggle
                label="AI Cinematic Text"
                description={textEmphasisEnabled
                  ? "Aktif: AI memilih maksimal 2 frasa punchline/tesis paling kuat dengan 13 gaya visual (Behind Person 3D, Hero Punch, Z-Parallax, Kinetic Cascade, dll). Subtitle karaoke berhenti halus saat teks sinematik tampil."
                  : "Opsional. Jika mati, hasil subtitle tetap normal tanpa teks sinematik."}
                checked={textEmphasisEnabled}
                onChange={(enabled) => { setTextEmphasisEnabled(enabled); if (enabled) setStyleTab("other"); }}
              />
              {textEmphasisEnabled && (
                <div className="ml-1 flex items-center justify-between rounded-lg border border-zinc-800/80 bg-zinc-950/50 px-2.5 py-1.5 text-[11px]">
                  <span className="text-zinc-400">
                    Mode: <span className="font-semibold text-emerald-400">{textEmphasisStyleConfig.effectMode === "auto" ? "AI Auto (Smart Selection)" : textEmphasisStyleConfig.effectMode}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => setStyleTab("other")}
                    className="text-[10px] font-medium text-emerald-400 hover:text-emerald-300 transition-colors"
                  >
                    Edit Style &rarr;
                  </button>
                </div>
              )}
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
              <Row label="Words/Line" value={`${subtitleStyleConfig.maxWordsPerLine || 4} kata`} />
              <Row label="AI Text" value={textEmphasisEnabled ? textEmphasisStyleConfig.effectMode.replace(/_/g, " ") : "off"} />
              <Row label="Watermark" value={watermarkStyleConfig.enabled ? (watermarkStyleConfig.type === "text" ? watermarkStyleConfig.text || "text" : "image") : "off"} />
              <Row label="CTA End-Card" value={ctaStyleConfig.enabled ? `${ctaStyleConfig.template.replace(/_/g, " ")} (${ctaStyleConfig.duration}s)` : "off"} />
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
            <button type="button" onClick={() => setStyleTab("other")} className={cn("px-3 py-1.5 text-xs font-medium rounded-lg transition-colors", styleTab === "other" ? "bg-emerald-600 text-white" : "bg-zinc-800 text-zinc-400 hover:text-zinc-200")}><Layers className="h-3 w-3 inline mr-1" />Other</button>
          </div>

          {/* Style editor content */}
          <Card className="flex min-h-0 flex-1 flex-col overflow-hidden p-0">
            <StyleEditorModal
              open={true}
              onClose={() => { }}
              hookStyle={hookStyleConfig}
              subtitleStyle={subtitleStyleConfig}
              textEmphasisStyle={textEmphasisStyleConfig}
              onHookChange={setHookStyleConfig}
              onSubtitleChange={setSubtitleStyleConfig}
              onTextEmphasisChange={setTextEmphasisStyleConfig}
              watermarkStyle={watermarkStyleConfig}
              onWatermarkChange={setWatermarkStyleConfig}
              ctaStyle={ctaStyleConfig}
              onCtaChange={setCtaStyleConfig}
              aspectRatio={aspectRatio}
              inline
              activeTab={styleTab}
              thumbnailUrl={videoMeta?.thumbnail}
              canvasBackground={
                aspectRatio === "16:9" || aspectRatio === "1:1"
                  ? {
                    mode: backgroundMode,
                    templateId: backgroundTemplateId,
                    imageDataUrl: backgroundImageDataUrl,
                  }
                  : null
              }
              isSuperadmin={user?.is_superadmin}
              isPremium={user?.is_premium}
              userFeatures={user?.features}
              aiTextEnabled={textEmphasisEnabled}
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
      )}
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
