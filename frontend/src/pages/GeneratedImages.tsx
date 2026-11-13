import { useState, useEffect, useRef } from "react";
import {
  Sparkles,
  Image as ImageIcon,
  Film,
  Calendar,
  Clock,
  Send,
  Download,
  Copy,
  Plus,
  Trash2,
  RefreshCw,
  Sliders,
  Type,
  Music,
  Check,
  Layers,
  Eye,
  ExternalLink,
  Share2,
  CheckCircle2,
  AlertCircle,
  X,
  Palette,
  Play,
  Upload,
  Pencil,
  RotateCcw,
  Database,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Pause,
  Search,
  Volume2,
  Music2,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { PlatformIcon } from "@/components/social/PlatformIcon";
import {
  imageStudioApi,
  socialApi,
  ImageStudioSettings,
  ImageStudioSlot,
  TypographyTemplateMeta,
  CanvasAspectRatioMeta,
  AccentColorPreset,
  ImageStudioRun,
  ImageStudioProgress,
  PlatformAccountInfo,
  TikTokMusicTrack,
  NewsArticlePreview,
  NewsQueueItem,
  DesignAnalysisResult,
  API_BASE,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const ACCENT_PRESETS = [
  { name: "Gold", hex: "#D4AF37" },
  { name: "Amber", hex: "#F59E0B" },
  { name: "Cyan", hex: "#06B6D4" },
  { name: "Emerald", hex: "#10B981" },
  { name: "Rose", hex: "#F43F5E" },
  { name: "Purple", hex: "#8B5CF6" },
  { name: "White", hex: "#FFFFFF" },
];

const LAYOUT_ENGINE_OPTIONS = [
  { id: "minimal_quote", label: "Minimalist Aesthetic Quote" },
  { id: "bold_editorial", label: "Bold Editorial Magazine" },
  { id: "skena_magazine", label: "Skena Retro Indie" },
  { id: "brutalist_poster", label: "Neo-Brutalist Poster" },
  { id: "luxury_gold", label: "Luxury Gold & Noir" },
  { id: "cyberpunk_neon", label: "Cyberpunk Neon Glow" },
  { id: "aesthetic_carousel_card", label: "Carousel Insight Card" },
  { id: "news_bulletin", label: "News Bulletin & Breaking Card" },
  { id: "poetic_whisper", label: "Poetic Whisper" },
  { id: "modern_business", label: "Modern Business & Creator" },
  { id: "cinematic_film", label: "Cinematic Film Still" },
  { id: "daily_stoic", label: "Daily Stoic Maxim" },
];

export function GeneratedImagesPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<"instant" | "automation" | "history" | "catalog">("instant");
  const [catalogSubTab, setCatalogSubTab] = useState<"templates" | "fonts" | "aspects" | "accents">("templates");
  const [loading, setLoading] = useState<boolean>(true);
  const [savingSettings, setSavingSettings] = useState<boolean>(false);
  const [generating, setGenerating] = useState<boolean>(false);
  const [triggeringRun, setTriggeringRun] = useState<boolean>(false);
  const [suggesting, setSuggesting] = useState<boolean>(false);
  const [genProgress, setGenProgress] = useState<ImageStudioProgress | null>(null);
  const progressPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Settings State
  const [settings, setSettings] = useState<ImageStudioSettings | null>(null);
  const [templates, setTemplates] = useState<TypographyTemplateMeta[]>([]);
  const [fonts, setFonts] = useState<string[]>([]);
  const [fontsDetailed, setFontsDetailed] = useState<any[]>([]);
  const [aspectRatios, setAspectRatios] = useState<CanvasAspectRatioMeta[]>([]);
  const [accentPresets, setAccentPresets] = useState<AccentColorPreset[]>([]);
  const [accounts, setAccounts] = useState<PlatformAccountInfo[]>([]);
  const [history, setHistory] = useState<ImageStudioRun[]>([]);

  const getAccountMeta = (acc: PlatformAccountInfo | any) => {
    const accId = acc.account_id || acc._id || acc.id || "";
    const platform = (acc.platform || acc.type || "").toLowerCase();
    const avatar = acc.picture || acc.avatar || acc.avatar_url || "";
    const displayName = acc.name || acc.username || acc.title || platform;
    const username = acc.username ? (acc.username.startsWith("@") ? acc.username : `@${acc.username}`) : "";
    const ownerName = acc.owner?.full_name || acc.owner?.email || "";
    return { accId, platform, avatar, displayName, username, ownerName };
  };

  // Instant Studio Form State
  const [topic, setTopic] = useState<string>("Mindset & Stoicism");
  const [prompt, setPrompt] = useState<string>("");
  const [quoteHook, setQuoteHook] = useState<string>("DAILY WISDOM");
  const [quoteHeadline, setQuoteHeadline] = useState<string>(
    "Fokus pada apa yang ada dalam kendalimu, dan berdamailah dengan sisanya."
  );
  const [quoteBody, setQuoteBody] = useState<string>(
    "Kebahagiaan sejati dimulai saat kamu berhenti membiarkan opini orang lain mendikte nilaimu."
  );
  const [quoteAuthor, setQuoteAuthor] = useState<string>("Marcus Aurelius");
  const [quoteHandle, setQuoteHandle] = useState<string>("@cliperhub");
  const [selectedTemplate, setSelectedTemplate] = useState<string>("minimal_quote");
  const [selectedFont, setSelectedFont] = useState<string>("auto");
  const [selectedModel, setSelectedModel] = useState<string>("auto");
  const [aspectRatio, setAspectRatio] = useState<string>("9:16");
  const [accentColor, setAccentColor] = useState<string>("#D4AF37");
  const [mediaType, setMediaType] = useState<string>("image");
  const [backgroundSource, setBackgroundSource] = useState<string>("ai_gemini");
  const [imageCount, setImageCount] = useState<number>(1);
  const [autoPostInstant, setAutoPostInstant] = useState<boolean>(false);
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);

  // Custom Media Upload State
  const [customUploadUrl, setCustomUploadUrl] = useState<string>("");
  const [customUploadLocalPath, setCustomUploadLocalPath] = useState<string>("");
  const [uploadingMedia, setUploadingMedia] = useState<boolean>(false);

  // Design Reference / Clone Design Wizard State (Instant tab only)
  const [cloneReferencePreviewUrl, setCloneReferencePreviewUrl] = useState<string>("");
  const [cloneAnalyzing, setCloneAnalyzing] = useState<boolean>(false);
  const [cloneAnalysis, setCloneAnalysis] = useState<DesignAnalysisResult | null>(null);
  const [clonePresetName, setClonePresetName] = useState<string>("");
  const [cloneSaving, setCloneSaving] = useState<boolean>(false);

  // Automation: Multi-Topic News Discovery preview
  const [newsPreviewArticles, setNewsPreviewArticles] = useState<NewsArticlePreview[]>([]);
  const [loadingNewsPreview, setLoadingNewsPreview] = useState<boolean>(false);

  // Automation: Always Update news queue
  const [newsQueue, setNewsQueue] = useState<NewsQueueItem[]>([]);
  const [loadingNewsQueue, setLoadingNewsQueue] = useState<boolean>(false);

  // Preview & Result State
  const [latestResult, setLatestResult] = useState<any | null>(null);
  const [activeSlideIndex, setActiveSlideIndex] = useState<number>(0);
  const [historySlideIndices, setHistorySlideIndices] = useState<Record<number, number>>({});
  const [selectedRunForSocial, setSelectedRunForSocial] = useState<ImageStudioRun | null>(null);
  const [socialModalOpen, setSocialModalOpen] = useState<boolean>(false);
  const [publishingSocial, setPublishingSocial] = useState<boolean>(false);
  const [publishSuccessMessage, setPublishSuccessMessage] = useState<string>("");

  // Instant Studio Music State
  const [musicEnabledInstant, setMusicEnabledInstant] = useState<boolean>(false);
  const [musicModeInstant, setMusicModeInstant] = useState<"auto" | "custom">("auto");
  const [selectedTrackInstant, setSelectedTrackInstant] = useState<TikTokMusicTrack | null>(null);
  const [instantMusicSearch, setInstantMusicSearch] = useState<string>("");
  const [instantMusicTracks, setInstantMusicTracks] = useState<TikTokMusicTrack[]>([]);
  const [loadingInstantMusic, setLoadingInstantMusic] = useState<boolean>(false);

  // Social Modal Music State
  const [modalMusicEnabled, setModalMusicEnabled] = useState<boolean>(false);
  const [modalMusicMode, setModalMusicMode] = useState<"auto" | "custom">("auto");
  const [modalSelectedTrack, setModalSelectedTrack] = useState<TikTokMusicTrack | null>(null);
  const [modalMusicSearch, setModalMusicSearch] = useState<string>("");
  const [modalMusicTracks, setModalMusicTracks] = useState<TikTokMusicTrack[]>([]);
  const [loadingModalMusic, setLoadingModalMusic] = useState<boolean>(false);

  // Shared Audio Preview Player
  const [playingTrackId, setPlayingTrackId] = useState<string | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);

  // New Topic & Slot inputs for Automation tab
  const [newTopicInput, setNewTopicInput] = useState<string>("");

  // Database Template Modal State
  const [templateModalOpen, setTemplateModalOpen] = useState<boolean>(false);
  const [editingTemplate, setEditingTemplate] = useState<TypographyTemplateMeta | null>(null);
  const [templateForm, setTemplateForm] = useState<{
    id: string;
    name: string;
    vibe: string;
    primary_font: string;
    secondary_font: string;
    recommended_accent: string;
    layout_type: string;
  }>({
    id: "",
    name: "",
    vibe: "",
    primary_font: "Playfair Display",
    secondary_font: "Inter",
    recommended_accent: "#EAB308",
    layout_type: "minimal_quote",
  });
  const [savingTemplate, setSavingTemplate] = useState<boolean>(false);
  const [resettingTemplates, setResettingTemplates] = useState<boolean>(false);

  useEffect(() => {
    fetchInitialData();
  }, []);

  const fetchInitialData = async () => {
    setLoading(true);
    try {
      // Settings is fetched and applied on its own, ahead of the slower/unrelated
      // calls below (social accounts hits an external API). Bundling it into one
      // Promise.all used to mean any toggle the user clicked before that slowest
      // call resolved got silently clobbered by this initial setSettings.
      const settingsRes = await imageStudioApi.getSettings();
      if (settingsRes.success && settingsRes.data) {
        setSettings(settingsRes.data);
        if (settingsRes.data.target_account_ids) {
          setSelectedAccountIds(settingsRes.data.target_account_ids);
        }
      }

      const [tplRes, fontsRes, accRes, histRes, arRes, accentsRes] = await Promise.all([
        imageStudioApi.getTemplates(),
        imageStudioApi.getFonts(),
        socialApi.getAccounts().catch(() => ({ docs: [] })),
        imageStudioApi.getHistory().catch(() => ({ data: [] })),
        imageStudioApi.getAspectRatios().catch(() => ({ data: [] })),
        imageStudioApi.getAccents().catch(() => ({ data: [] })),
      ]);

      if (tplRes.success) setTemplates(tplRes.data);
      if (fontsRes.success) {
        setFonts(fontsRes.data);
        if ((fontsRes as any).fonts) setFontsDetailed((fontsRes as any).fonts);
      }
      if (accRes && accRes.docs) setAccounts(accRes.docs);
      if (histRes && "data" in histRes && Array.isArray(histRes.data)) setHistory(histRes.data);
      if (arRes && "data" in arRes && Array.isArray(arRes.data)) setAspectRatios(arRes.data);
      if (accentsRes && "data" in accentsRes && Array.isArray(accentsRes.data)) setAccentPresets(accentsRes.data);
    } catch (err) {
      console.error("Failed to load initial data:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveSettings = async () => {
    if (!settings) return;
    setSavingSettings(true);
    try {
      const res = await imageStudioApi.updateSettings({
        enabled: settings.enabled,
        topics: settings.topics,
        daily_slots: settings.daily_slots,
        images_per_session: settings.images_per_session,
        aspect_ratio: settings.aspect_ratio,
        template_preset: settings.template_preset,
        font_family: settings.font_family,
        background_source: settings.background_source,
        media_type: settings.media_type,
        auto_post_enabled: settings.auto_post_enabled,
        target_account_ids: settings.target_account_ids,
        music_enabled: settings.music_enabled,
        music_track: settings.music_track,
        footage_duration_sec: settings.footage_duration_sec,
        content_mode: settings.content_mode,
        publish_mode: settings.publish_mode,
        always_update_interval_min: settings.always_update_interval_min,
      });
      if (res.success && res.data) {
        setSettings(res.data);
      }
    } catch (err) {
      console.error("Failed saving settings:", err);
    } finally {
      setSavingSettings(false);
    }
  };

  const handleSuggestContent = async () => {
    if (!topic.trim()) {
      alert("Silakan masukkan tema atau topik visual terlebih dahulu.");
      return;
    }
    setSuggesting(true);
    try {
      const res = await imageStudioApi.suggestContent(topic.trim());
      if (res.success && res.data) {
        if (res.data.hook) setQuoteHook(res.data.hook);
        if (res.data.headline) setQuoteHeadline(res.data.headline);
        if (res.data.body) setQuoteBody(res.data.body);
        if (res.data.author) setQuoteAuthor(res.data.author);
        if (res.data.prompt) setPrompt(res.data.prompt);
      } else {
        alert("Gagal mendapatkan saran konten dari AI.");
      }
    } catch (err: any) {
      alert(`Gagal membuat konten AI: ${err.message || err}`);
    } finally {
      setSuggesting(false);
    }
  };

  // Audio demo cleanup
  useEffect(() => {
    return () => {
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
        audioPlayerRef.current = null;
      }
    };
  }, []);

  const togglePlayAudio = (track: TikTokMusicTrack, e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (playingTrackId === track.id) {
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
      }
      setPlayingTrackId(null);
    } else {
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
      }
      const audio = new Audio(track.url);
      audio.volume = 0.5;
      audio.onended = () => setPlayingTrackId(null);
      audio.onerror = () => setPlayingTrackId(null);
      audio.play().catch(() => setPlayingTrackId(null));
      audioPlayerRef.current = audio;
      setPlayingTrackId(track.id);
    }
  };

  const loadInstantMusicTracks = async (query?: string) => {
    setLoadingInstantMusic(true);
    try {
      const res = await socialApi.getTikTokTrendingMusic({
        search: query?.trim() || undefined,
        limit: 20,
        country_code: "ID",
      });
      if (res && res.tracks) {
        setInstantMusicTracks(res.tracks);
      }
    } catch (err) {
      console.warn("Failed to fetch TikTok music tracks:", err);
    } finally {
      setLoadingInstantMusic(false);
    }
  };

  const loadModalMusicTracks = async (query?: string) => {
    setLoadingModalMusic(true);
    try {
      const res = await socialApi.getTikTokTrendingMusic({
        search: query?.trim() || undefined,
        limit: 20,
        country_code: "ID",
      });
      if (res && res.tracks) {
        setModalMusicTracks(res.tracks);
      }
    } catch (err) {
      console.warn("Failed to fetch TikTok music tracks for modal:", err);
    } finally {
      setLoadingModalMusic(false);
    }
  };

  const genProgressToken = () => {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
    return `tok_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  };

  const stopProgressPolling = () => {
    if (progressPollRef.current) {
      clearInterval(progressPollRef.current);
      progressPollRef.current = null;
    }
  };

  const startProgressPolling = (token: string) => {
    stopProgressPolling();
    progressPollRef.current = setInterval(async () => {
      try {
        const res = await imageStudioApi.getProgress(token);
        if (res.success && res.data) {
          setGenProgress(res.data);
          if (res.data.status === "done" || res.data.status === "failed") {
            stopProgressPolling();
          }
        }
      } catch {
        // Transient polling error — next tick will retry, no need to surface it.
      }
    }, 1000);
  };

  // Cleanup polling interval on unmount
  useEffect(() => {
    return () => stopProgressPolling();
  }, []);

  // Auto-refresh the Always Update news queue once when its panel becomes visible
  useEffect(() => {
    if (activeTab === "automation" && settings?.publish_mode === "always_update") {
      handleRefreshNewsQueue();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, settings?.publish_mode]);

  const handleInstantGenerate = async () => {
    setGenerating(true);
    setLatestResult(null);
    setActiveSlideIndex(0);
    const token = genProgressToken();
    setGenProgress({ total: imageCount, completed: 0, status: "running", current_label: "Memulai..." });
    startProgressPolling(token);
    try {
      const res = await imageStudioApi.generateInstant({
        topic,
        prompt,
        quote_hook: quoteHook,
        quote_headline: quoteHeadline,
        quote_body: quoteBody,
        quote_author: quoteAuthor,
        quote_handle: quoteHandle,
        accent_color: accentColor,
        template_preset: selectedTemplate,
        font_family: selectedFont,
        model_name: selectedModel === "auto" ? undefined : selectedModel,
        aspect_ratio: aspectRatio,
        background_source: backgroundSource,
        custom_background_path: customUploadLocalPath || undefined,
        media_type: mediaType,
        image_count: imageCount,
        auto_post: autoPostInstant,
        target_account_ids: selectedAccountIds,
        music_enabled: musicEnabledInstant,
        music_id: musicModeInstant === "custom" && selectedTrackInstant ? selectedTrackInstant.id : undefined,
        music_name: musicModeInstant === "custom" && selectedTrackInstant ? selectedTrackInstant.name : undefined,
        music_artist: musicModeInstant === "custom" && selectedTrackInstant ? selectedTrackInstant.artist : undefined,
        music_thumbnail: musicModeInstant === "custom" && selectedTrackInstant ? selectedTrackInstant.thumbnail : undefined,
        progress_token: token,
      });
      if (res.success && res.data) {
        setLatestResult(res.data);
        setActiveSlideIndex(0);
        // Refresh history
        const hRes = await imageStudioApi.getHistory();
        if (hRes.success) setHistory(hRes.data);
      }
    } catch (err: any) {
      alert(`Gagal membuat visual post: ${err.message || err}`);
    } finally {
      try {
        const finalProg = await imageStudioApi.getProgress(token);
        if (finalProg.success && finalProg.data) setGenProgress(finalProg.data);
      } catch {
        // Ignore — final panel state just stays at its last known value.
      }
      stopProgressPolling();
      setGenerating(false);
    }
  };

  const handleTriggerManualHermes = async () => {
    setTriggeringRun(true);
    const token = genProgressToken();
    setGenProgress({
      total: settings?.images_per_session || 2,
      completed: 0,
      status: "running",
      current_label: "Memulai sesi Hermes...",
    });
    startProgressPolling(token);
    try {
      const res = await imageStudioApi.triggerRun({
        slot_name: "Manual Hermes Run",
        progress_token: token,
      });
      if (res.success && res.data) {
        setLatestResult(res.data);
        setActiveSlideIndex(0);
        const hRes = await imageStudioApi.getHistory();
        if (hRes.success) setHistory(hRes.data);
      }
    } catch (err: any) {
      alert(`Gagal menjalankan sesi Hermes: ${err.message || err}`);
    } finally {
      try {
        const finalProg = await imageStudioApi.getProgress(token);
        if (finalProg.success && finalProg.data) setGenProgress(finalProg.data);
      } catch {
        // Ignore — final panel state just stays at its last known value.
      }
      stopProgressPolling();
      setTriggeringRun(false);
    }
  };

  const handleCheckNewsNow = async () => {
    if (!settings?.topics.length) return;
    setLoadingNewsPreview(true);
    try {
      const res = await imageStudioApi.discoverNews(settings.topics);
      if (res.success) setNewsPreviewArticles(res.data);
    } catch (err: any) {
      alert(`Gagal mencari berita: ${err.message || err}`);
    } finally {
      setLoadingNewsPreview(false);
    }
  };

  const handleRefreshNewsQueue = async () => {
    setLoadingNewsQueue(true);
    try {
      const res = await imageStudioApi.getNewsQueue();
      if (res.success) setNewsQueue(res.data);
    } catch {
      // Silent — the queue panel just keeps showing its last known state.
    } finally {
      setLoadingNewsQueue(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>, type: "image" | "music") => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingMedia(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("media_type", type);
      const res = await imageStudioApi.uploadMedia(formData);
      if (res.success && res.url) {
        if (type === "image") {
          setCustomUploadUrl(res.url);
          setCustomUploadLocalPath(res.local_path || "");
          setBackgroundSource("user_upload");
        } else if (settings) {
          setSettings({ ...settings, music_track: res.url });
        }
      }
    } catch (err: any) {
      alert(`Upload gagal: ${err.message || err}`);
    } finally {
      setUploadingMedia(false);
    }
  };

  const handleAnalyzeDesignReference = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setCloneAnalysis(null);
    setCloneReferencePreviewUrl(URL.createObjectURL(file));
    setCloneAnalyzing(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await imageStudioApi.analyzeDesign(formData);
      if (res.success && res.data) {
        setCloneAnalysis(res.data);
        setClonePresetName(res.data.suggested_name || "Preset Clone Design");
      }
    } catch (err: any) {
      alert(`Analisis desain gagal: ${err.message || err}`);
    } finally {
      setCloneAnalyzing(false);
    }
  };

  const handleSaveClonePreset = async () => {
    if (!cloneAnalysis || !clonePresetName.trim()) return;
    setCloneSaving(true);
    try {
      const res = await imageStudioApi.cloneDesign({
        name: clonePresetName.trim(),
        primary_font: cloneAnalysis.primary_font,
        secondary_font: cloneAnalysis.secondary_font,
        recommended_accent: cloneAnalysis.recommended_accent,
        layout_type: cloneAnalysis.layout_type,
        vibe: cloneAnalysis.vibe,
      });
      if (res.success && res.data) {
        const tRes = await imageStudioApi.getTemplates();
        if (tRes.success) setTemplates(tRes.data);
        setSelectedTemplate(res.data.id);
        setAccentColor(cloneAnalysis.recommended_accent);
        setBackgroundSource("ai_gemini");
        setCloneAnalysis(null);
        setCloneReferencePreviewUrl("");
        setClonePresetName("");
      }
    } catch (err: any) {
      alert(`Gagal menyimpan preset: ${err.message || err}`);
    } finally {
      setCloneSaving(false);
    }
  };

  const handleDeleteHistory = async (id: number) => {
    if (!confirm("Hapus visual post ini beserta filenya?")) return;
    try {
      await imageStudioApi.deleteHistoryItem(id);
      setHistory((prev) => prev.filter((item) => item.id !== id));
    } catch (err) {
      console.error("Gagal menghapus item:", err);
    }
  };

  const handleOpenSocialModal = (run: ImageStudioRun) => {
    setSelectedRunForSocial(run);
    setSocialModalOpen(true);
    setPublishSuccessMessage("");
    // Force explicit re-selection per run instead of carrying over whatever
    // was last picked (Instant Studio's selector, or a previous run's modal) —
    // publishing this specific run to stale/unintended accounts is a real risk.
    setSelectedAccountIds([]);
    setModalMusicEnabled(Boolean(run.social_details?.music_enabled || false));
    setModalMusicMode("auto");
    setModalSelectedTrack(null);
    if (audioPlayerRef.current) {
      audioPlayerRef.current.pause();
      setPlayingTrackId(null);
    }
  };

  const handlePublishFromModal = async () => {
    if (!selectedRunForSocial || selectedAccountIds.length === 0) return;
    setPublishingSocial(true);
    try {
      const res = await imageStudioApi.publishToSocial({
        run_id: selectedRunForSocial.id,
        account_ids: selectedAccountIds,
        title: selectedRunForSocial.topic,
        caption: `${selectedRunForSocial.quote_headline}\n\n${selectedRunForSocial.quote_body}`,
        music_enabled: modalMusicEnabled,
        music_id: modalMusicMode === "custom" && modalSelectedTrack ? modalSelectedTrack.id : undefined,
        music_name: modalMusicMode === "custom" && modalSelectedTrack ? modalSelectedTrack.name : undefined,
        music_artist: modalMusicMode === "custom" && modalSelectedTrack ? modalSelectedTrack.artist : undefined,
        music_thumbnail: modalMusicMode === "custom" && modalSelectedTrack ? modalSelectedTrack.thumbnail : undefined,
      });
      if (res.success) {
        if (res.status === "partial") {
          const failedCount = res.details?.failures?.length || 0;
          setPublishSuccessMessage(
            `Sebagian berhasil: ${failedCount} akun gagal dijadwalkan. Cek detail akun di riwayat.`
          );
        } else {
          setPublishSuccessMessage("Post berhasil dijadwalkan ke akun media sosial terpilih.");
        }
        const hRes = await imageStudioApi.getHistory();
        if (hRes.success) setHistory(hRes.data);
      } else {
        alert("Gagal menjadwalkan post ke media sosial.");
      }
    } catch (err: any) {
      alert(`Error scheduling post: ${err.message || err}`);
    } finally {
      setPublishingSocial(false);
    }
  };

  const handleOpenCreateTemplateModal = () => {
    setEditingTemplate(null);
    setTemplateForm({
      id: "",
      name: "",
      vibe: "",
      primary_font: fonts[0] || "Playfair Display",
      secondary_font: fonts[1] || "Inter",
      recommended_accent: "#EAB308",
      layout_type: "minimal_quote",
    });
    setTemplateModalOpen(true);
  };

  const handleOpenEditTemplateModal = (tpl: TypographyTemplateMeta) => {
    setEditingTemplate(tpl);
    setTemplateForm({
      id: tpl.id,
      name: tpl.name,
      vibe: tpl.vibe,
      primary_font: tpl.primary_font,
      secondary_font: tpl.secondary_font,
      recommended_accent: tpl.recommended_accent,
      layout_type: tpl.layout_type || tpl.id,
    });
    setTemplateModalOpen(true);
  };

  const handleSaveTemplate = async () => {
    if (!templateForm.name.trim()) {
      alert("Silakan masukkan nama template.");
      return;
    }
    setSavingTemplate(true);
    try {
      if (editingTemplate) {
        const res = await imageStudioApi.updateTemplate(editingTemplate.id, {
          name: templateForm.name.trim(),
          vibe: templateForm.vibe.trim(),
          primary_font: templateForm.primary_font,
          secondary_font: templateForm.secondary_font,
          recommended_accent: templateForm.recommended_accent,
          layout_type: templateForm.layout_type,
        });
        if (res.success) {
          const tplRes = await imageStudioApi.getTemplates();
          if (tplRes.success) setTemplates(tplRes.data);
          setTemplateModalOpen(false);
        }
      } else {
        const res = await imageStudioApi.createTemplate({
          id: templateForm.id.trim() || undefined,
          name: templateForm.name.trim(),
          vibe: templateForm.vibe.trim(),
          primary_font: templateForm.primary_font,
          secondary_font: templateForm.secondary_font,
          recommended_accent: templateForm.recommended_accent,
          layout_type: templateForm.layout_type,
        });
        if (res.success) {
          const tplRes = await imageStudioApi.getTemplates();
          if (tplRes.success) setTemplates(tplRes.data);
          setTemplateModalOpen(false);
        }
      }
    } catch (err: any) {
      alert(`Gagal menyimpan template ke database: ${err.message || err}`);
    } finally {
      setSavingTemplate(false);
    }
  };

  const handleDeleteTemplate = async (templateId: string, templateName: string) => {
    if (!confirm(`Hapus template "${templateName}" dari database?`)) return;
    try {
      const res = await imageStudioApi.deleteTemplate(templateId);
      if (res.success) {
        setTemplates((prev) => prev.filter((t) => t.id !== templateId));
      }
    } catch (err: any) {
      alert(`Gagal menghapus template: ${err.message || err}`);
    }
  };

  const handleResetTemplates = async () => {
    if (!confirm("Reset semua template ke 12 preset bawaan database? Kustomisasi sebelumnya akan direset.")) return;
    setResettingTemplates(true);
    try {
      const res = await imageStudioApi.resetTemplates();
      if (res.success && res.data) {
        setTemplates(res.data);
      }
    } catch (err: any) {
      alert(`Gagal me-reset template: ${err.message || err}`);
    } finally {
      setResettingTemplates(false);
    }
  };

  // Helper to format media URL
  const formatMediaUrl = (url: string) => {
    if (!url) return "";
    if (url.startsWith("http://") || url.startsWith("https://")) return url;
    return `${API_BASE}${url}`;
  };

  return (
    <div className="flex-1 min-h-0 h-full overflow-y-auto pr-1 pb-24 space-y-6 text-zinc-100 overscroll-contain">
      {/* ─── Top Page Header ─────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-800/80 pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="h-9 w-9 rounded-xl bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-purple-400">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                Generated Images &amp; Visual Studio
              </h1>
              <p className="text-xs text-zinc-400">
                Studio pembuatan konten visual &amp; carousel estetik Pinterest/Instagram dengan Hermes Automation
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-2 rounded-xl bg-zinc-900 border border-zinc-800 px-3 py-1.5 text-xs text-zinc-400">
            <span className="h-2 w-2 rounded-full bg-emerald-500 ring-2 ring-emerald-500/20" />
            <span className="font-medium text-zinc-300">Gateway: 9router</span>
            <span className="text-zinc-600">|</span>
            <span className="text-zinc-400 font-mono text-[11px] truncate max-w-[200px]" title={settings?.gateway_endpoint || "Dynamic System Config"}>
              {settings?.gateway_endpoint ? new URL(settings.gateway_endpoint).host : "Dinamis"}
            </span>
          </div>

          <button
            onClick={handleTriggerManualHermes}
            disabled={triggeringRun}
            className="flex items-center gap-2 rounded-xl bg-zinc-800 hover:bg-zinc-700/80 border border-zinc-700/60 px-4 py-2 text-xs font-semibold text-zinc-200 transition-all shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={cn("h-3.5 w-3.5 text-cyan-400", triggeringRun && "animate-spin")} />
            <span>{triggeringRun ? "Hermes Mengeksekusi..." : "Jalankan Hermes Sekarang"}</span>
          </button>
        </div>
      </div>

      {/* ─── Live Generation Progress Panel ─────────────────────────────── */}
      {genProgress && (
        <div
          className={cn(
            "rounded-2xl border p-4 space-y-2.5",
            genProgress.status === "failed"
              ? "border-rose-500/40 bg-rose-500/5"
              : genProgress.status === "done"
              ? "border-emerald-500/30 bg-emerald-500/5"
              : "border-purple-500/30 bg-purple-500/5"
          )}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-semibold text-zinc-200">
              {genProgress.status === "failed" ? (
                <AlertCircle className="h-4 w-4 text-rose-400" />
              ) : genProgress.status === "done" ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              ) : (
                <Sparkles className="h-4 w-4 text-purple-400 animate-pulse" />
              )}
              <span>{genProgress.current_label}</span>
            </div>
            <span className="text-[11px] text-zinc-400 font-mono">
              {genProgress.completed}/{genProgress.total}
            </span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-zinc-800 overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500",
                genProgress.status === "failed"
                  ? "bg-rose-500"
                  : genProgress.status === "done"
                  ? "bg-emerald-500"
                  : "bg-purple-500"
              )}
              style={{
                width: `${Math.min(100, Math.round((genProgress.completed / Math.max(1, genProgress.total)) * 100))}%`,
              }}
            />
          </div>
          {genProgress.status === "failed" && genProgress.error && (
            <p className="text-[11px] text-rose-300">{genProgress.error}</p>
          )}
        </div>
      )}

      {/* ─── Navigation Tabs ─────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 border-b border-zinc-800/80 overflow-x-auto scrollbar-none">
        <button
          onClick={() => setActiveTab("instant")}
          className={cn(
            "flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-colors whitespace-nowrap",
            activeTab === "instant"
              ? "border-purple-500 text-purple-400 bg-purple-500/5"
              : "border-transparent text-zinc-400 hover:text-zinc-200 hover:bg-zinc-850"
          )}
        >
          <Sparkles className="h-4 w-4" />
          <span>Instant Studio</span>
        </button>

        <button
          onClick={() => setActiveTab("automation")}
          className={cn(
            "flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-colors whitespace-nowrap",
            activeTab === "automation"
              ? "border-cyan-500 text-cyan-400 bg-cyan-500/5"
              : "border-transparent text-zinc-400 hover:text-zinc-200 hover:bg-zinc-850"
          )}
        >
          <Clock className="h-4 w-4" />
          <span>Automasi Harian (Hermes)</span>
          {settings?.enabled && (
            <span className="h-2 w-2 rounded-full bg-emerald-500 ring-4 ring-emerald-500/20" />
          )}
        </button>

        <button
          onClick={() => setActiveTab("history")}
          className={cn(
            "flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-colors whitespace-nowrap",
            activeTab === "history"
              ? "border-emerald-500 text-emerald-400 bg-emerald-500/5"
              : "border-transparent text-zinc-400 hover:text-zinc-200 hover:bg-zinc-850"
          )}
        >
          <Layers className="h-4 w-4" />
          <span>Galeri &amp; Riwayat ({history.length})</span>
        </button>

        <button
          onClick={() => setActiveTab("catalog")}
          className={cn(
            "flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-colors whitespace-nowrap",
            activeTab === "catalog"
              ? "border-amber-500 text-amber-400 bg-amber-500/5"
              : "border-transparent text-zinc-400 hover:text-zinc-200 hover:bg-zinc-850"
          )}
        >
          <Palette className="h-4 w-4" />
          <span>Katalog Template Tipografi</span>
        </button>
      </div>

      {/* ─── TAB 1: INSTANT STUDIO ────────────────────────────────────────── */}
      {activeTab === "instant" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Controls Column */}
          <div className="lg:col-span-7 space-y-5">
            {/* 1. Content & Topic Card */}
            <div className="rounded-2xl border border-zinc-800 bg-[#0e0e12] p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
                <div className="flex items-center gap-2">
                  <Type className="h-4 w-4 text-purple-400" />
                  <span className="text-sm font-semibold text-zinc-200">Konten &amp; Hirarki Teks</span>
                </div>
                <button
                  type="button"
                  onClick={handleSuggestContent}
                  disabled={suggesting}
                  className="flex items-center gap-1.5 rounded-lg bg-purple-500/10 hover:bg-purple-500/20 border border-purple-500/30 px-3 py-1 text-xs font-semibold text-purple-300 transition-colors disabled:opacity-50"
                  title="Biarkan AI 9router merumuskan hook viral, headline kutipan, refleksi dan prompt visual otomatis"
                >
                  <Sparkles className={cn("h-3.5 w-3.5 text-purple-400", suggesting && "animate-spin")} />
                  <span>{suggesting ? "Menulis dengan AI..." : "Bantu Tulis dengan AI (Copilot)"}</span>
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                    Topik / Tema Visual
                  </label>
                  <input
                    type="text"
                    value={topic}
                    onChange={(e) => setTopic(e.target.value)}
                    placeholder="misal: Mindset & Stoicism, Bisnis Modern..."
                    className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3.5 py-2 text-xs text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-purple-500"
                  />
                </div>

                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                    Hook / Kategori Tag
                  </label>
                  <input
                    type="text"
                    value={quoteHook}
                    onChange={(e) => setQuoteHook(e.target.value)}
                    placeholder="misal: DAILY WISDOM, PERSPECTIVE..."
                    className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3.5 py-2 text-xs text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-purple-500"
                  />
                </div>
              </div>

              <div>
                <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                  Headline Utama / Kutipan
                </label>
                <textarea
                  rows={2}
                  value={quoteHeadline}
                  onChange={(e) => setQuoteHeadline(e.target.value)}
                  placeholder="Kutipan utama atau kalimat punchy..."
                  className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3.5 py-2 text-xs text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-purple-500"
                />
              </div>

              <div>
                <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                  Teks Penjelas / Body / Poin Insight (Opsional)
                </label>
                <textarea
                  rows={2}
                  value={quoteBody}
                  onChange={(e) => setQuoteBody(e.target.value)}
                  placeholder="Kalimat penjelas, atau pisahkan dengan baris baru untuk format bullet points..."
                  className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3.5 py-2 text-xs text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-purple-500"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                    Nama Penulis / Tokoh
                  </label>
                  <input
                    type="text"
                    value={quoteAuthor}
                    onChange={(e) => setQuoteAuthor(e.target.value)}
                    placeholder="Marcus Aurelius, Seneca, Steve Jobs..."
                    className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3.5 py-2 text-xs text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-purple-500"
                  />
                </div>

                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                    Social Handle / Watermark
                  </label>
                  <input
                    type="text"
                    value={quoteHandle}
                    onChange={(e) => setQuoteHandle(e.target.value)}
                    placeholder="@cliperhub"
                    className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3.5 py-2 text-xs text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-purple-500"
                  />
                </div>
              </div>
            </div>

            {/* 2. Visual Template & Font Selection */}
            <div className="rounded-2xl border border-zinc-800 bg-[#0e0e12] p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
                <div className="flex items-center gap-2">
                  <Palette className="h-4 w-4 text-cyan-400" />
                  <span className="text-sm font-semibold text-zinc-200">Template Tipografi Pinterest &amp; Font</span>
                </div>
                <span className="text-[11px] text-zinc-500">{templates.length} Preset Tersedia</span>
              </div>

              {/* Template selector cards */}
              <div>
                <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-2">
                  Pilih Preset Gaya Tipografi
                </label>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2.5 max-h-56 overflow-y-auto pr-1">
                  {templates.map((tpl) => (
                    <button
                      key={tpl.id}
                      type="button"
                      onClick={() => setSelectedTemplate(tpl.id)}
                      className={cn(
                        "flex flex-col text-left p-3 rounded-xl border text-xs transition-all",
                        selectedTemplate === tpl.id
                          ? "border-purple-500 bg-purple-500/10 text-white shadow-sm ring-1 ring-purple-500/40"
                          : "border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                      )}
                    >
                      <div className="flex items-center justify-between w-full mb-1">
                        <span className="font-semibold truncate">{tpl.name}</span>
                        {selectedTemplate === tpl.id && <Check className="h-3.5 w-3.5 text-purple-400 shrink-0" />}
                      </div>
                      <span className="text-[10px] text-zinc-500 line-clamp-1">{tpl.vibe}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Font Override & Accent Color */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                    Font Utama
                  </label>
                  <select
                    value={selectedFont}
                    onChange={(e) => setSelectedFont(e.target.value)}
                    className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3.5 py-2 text-xs text-zinc-200 focus:outline-none focus:border-cyan-500"
                  >
                    <option value="auto">Auto (Sesuai Karakter Template)</option>
                    {fonts.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                    Warna Aksen Teks
                  </label>
                  <div className="flex items-center gap-1.5 pt-0.5">
                    {(accentPresets.length > 0 ? accentPresets : ACCENT_PRESETS).map((p) => (
                      <button
                        key={p.hex}
                        type="button"
                        onClick={() => setAccentColor(p.hex)}
                        className={cn(
                          "h-6 w-6 rounded-full border transition-all flex items-center justify-center",
                          accentColor.toLowerCase() === p.hex.toLowerCase() ? "scale-110 border-white ring-2 ring-purple-500/50" : "border-transparent"
                        )}
                        style={{ backgroundColor: p.hex }}
                        title={p.name}
                      >
                        {accentColor.toLowerCase() === p.hex.toLowerCase() && <Check className="h-3 w-3 text-black" />}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* 3. Media & Canvas Dimensions */}
            <div className="rounded-2xl border border-zinc-800 bg-[#0e0e12] p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
                <div className="flex items-center gap-2">
                  <Sliders className="h-4 w-4 text-emerald-400" />
                  <span className="text-sm font-semibold text-zinc-200">Format &amp; Sumber Media</span>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                    Tipe Output
                  </label>
                  <div className="grid grid-cols-2 gap-1.5">
                    <button
                      type="button"
                      onClick={() => setMediaType("image")}
                      className={cn(
                        "flex items-center justify-center gap-1.5 rounded-xl border py-2 text-xs font-medium transition-all",
                        mediaType === "image"
                          ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                          : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-zinc-200"
                      )}
                    >
                      <ImageIcon className="h-3.5 w-3.5" />
                      <span>Gambar</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setMediaType("video_footage")}
                      className={cn(
                        "flex items-center justify-center gap-1.5 rounded-xl border py-2 text-xs font-medium transition-all",
                        mediaType === "video_footage"
                          ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                          : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-zinc-200"
                      )}
                    >
                      <Film className="h-3.5 w-3.5" />
                      <span>Video</span>
                    </button>
                  </div>
                </div>

                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                    Aspek Rasio
                  </label>
                  <select
                    value={aspectRatio}
                    onChange={(e) => setAspectRatio(e.target.value)}
                    className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-emerald-500"
                  >
                    {aspectRatios.map((ar) => (
                      <option key={ar.id} value={ar.id}>
                        {ar.name} ({ar.width}x{ar.height})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                    Jumlah Foto (Batch)
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={imageCount}
                    onChange={(e) => setImageCount(parseInt(e.target.value) || 1)}
                    className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3.5 py-2 text-xs text-zinc-200 focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              {/* Background Source Selector */}
              <div>
                <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                  Sumber Latar Belakang
                </label>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                  {[
                    { id: "ai_gemini", label: "AI Gemini 3.1", desc: "Generated Image API" },
                    { id: "pexels", label: "Pexels Stock", desc: "Stock Foto/Video" },
                    { id: "pixabay", label: "Pixabay Stock", desc: "Royalty Free" },
                    { id: "user_upload", label: "Upload Background", desc: "Foto / Footage Anda" },
                    { id: "design_clone", label: "Clone Design", desc: "Tiru gaya dari referensi" },
                  ].map((src) => (
                    <button
                      key={src.id}
                      type="button"
                      onClick={() => setBackgroundSource(src.id)}
                      className={cn(
                        "flex flex-col text-left p-2.5 rounded-xl border text-xs transition-all",
                        backgroundSource === src.id
                          ? "border-emerald-500 bg-emerald-500/10 text-white ring-1 ring-emerald-500/30"
                          : "border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                      )}
                    >
                      <span className="font-semibold">{src.label}</span>
                      <span className="text-[10px] text-zinc-500">{src.desc}</span>
                    </button>
                  ))}
                </div>

                {backgroundSource === "ai_gemini" && (
                  <div className="mt-3 p-3.5 rounded-xl border border-zinc-800 bg-zinc-900/60 space-y-3">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1">
                          Model AI Image
                        </label>
                        <select
                          value={selectedModel}
                          onChange={(e) => setSelectedModel(e.target.value)}
                          className="w-full rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-emerald-500"
                        >
                          <option value="auto">Auto (Dinamis dari Settings / System)</option>
                          <option value="ag/gemini-3.1-flash-image">ag/gemini-3.1-flash-image</option>
                          <option value="gemini-2.5-flash-image">gemini-2.5-flash-image</option>
                          <option value="gemini-2.0-flash-exp">gemini-2.0-flash-exp</option>
                        </select>
                      </div>
                      <div className="flex flex-col justify-end">
                        <span className="text-[11px] text-zinc-500 pb-1">
                          Terkoneksi langsung ke 9router Gateway secara dinamis tanpa hardcode.
                        </span>
                      </div>
                    </div>

                    <div>
                      <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1">
                        Prompt Visual AI (Opsional / Copilot Auto-Fill)
                      </label>
                      <textarea
                        rows={2}
                        value={prompt}
                        onChange={(e) => setPrompt(e.target.value)}
                        placeholder="Deskripsi visual adegan foto (misal: cinematic dramatic moody shadows, ultra detailed). Kosongkan jika ingin AI menyusunnya otomatis dari topik..."
                        className="w-full rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-xs text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-emerald-500"
                      />
                    </div>
                  </div>
                )}

                {backgroundSource === "user_upload" && (
                  <div className="mt-3 p-3 rounded-xl border border-dashed border-zinc-700 bg-zinc-900/80 flex items-center justify-between">
                    <div className="text-xs text-zinc-300">
                      {customUploadUrl ? "Foto kustom terunggah — akan dipakai langsung sebagai background." : "Pilih file gambar atau video dari komputer Anda"}
                    </div>
                    <label className="cursor-pointer rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs px-3 py-1.5 text-zinc-200 font-medium transition-colors">
                      <input
                        type="file"
                        accept="image/*,video/*"
                        className="hidden"
                        onChange={(e) => handleFileUpload(e, "image")}
                        disabled={uploadingMedia}
                      />
                      <span>{uploadingMedia ? "Mengunggah..." : "Pilih File"}</span>
                    </label>
                  </div>
                )}

                {backgroundSource === "design_clone" && (
                  <div className="mt-3 p-3.5 rounded-xl border border-dashed border-purple-700/50 bg-purple-500/5 space-y-3">
                    <p className="text-[11px] text-zinc-400">
                      Upload desain referensi (poster, quote card, dsb). AI akan menganalisis tipografi, warna, dan tata letaknya —
                      <span className="text-zinc-300"> bukan foto-nya</span> — lalu dijadikan preset tipografi yang bisa dipakai ulang.
                    </p>

                    {!cloneAnalysis && !cloneAnalyzing && (
                      <label className="flex items-center justify-center gap-2 cursor-pointer rounded-lg border border-purple-500/40 bg-purple-500/10 hover:bg-purple-500/20 text-xs px-3 py-2.5 text-purple-200 font-medium transition-colors">
                        <Upload className="h-3.5 w-3.5" />
                        <input type="file" accept="image/*" className="hidden" onChange={handleAnalyzeDesignReference} />
                        <span>Upload Gambar Referensi</span>
                      </label>
                    )}

                    {cloneAnalyzing && (
                      <div className="flex items-center gap-2 text-xs text-purple-300 py-2">
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        <span>AI sedang menganalisis gaya desain referensi...</span>
                      </div>
                    )}

                    {cloneAnalysis && (
                      <div className="space-y-3">
                        <div className="flex items-center gap-3">
                          {cloneReferencePreviewUrl && (
                            <img src={cloneReferencePreviewUrl} alt="Referensi" className="h-20 w-14 object-cover rounded-lg border border-zinc-700" />
                          )}
                          <div className="flex-1 space-y-1 text-[11px] text-zinc-400">
                            <p className="text-zinc-300">{cloneAnalysis.vibe}</p>
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-300">
                                {LAYOUT_ENGINE_OPTIONS.find((l) => l.id === cloneAnalysis.layout_type)?.label || cloneAnalysis.layout_type}
                              </span>
                              <span className="px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-300">{cloneAnalysis.primary_font}</span>
                              <span
                                className="h-3.5 w-3.5 rounded-full border border-white/20"
                                style={{ backgroundColor: cloneAnalysis.recommended_accent }}
                                title={cloneAnalysis.recommended_accent}
                              />
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <input
                            type="text"
                            value={clonePresetName}
                            onChange={(e) => setClonePresetName(e.target.value)}
                            placeholder="Nama preset..."
                            className="flex-1 rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-purple-500"
                          />
                          <button
                            type="button"
                            onClick={handleSaveClonePreset}
                            disabled={cloneSaving || !clonePresetName.trim()}
                            className="shrink-0 px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold disabled:opacity-50 transition-colors"
                          >
                            {cloneSaving ? "Menyimpan..." : "Simpan sebagai Preset"}
                          </button>
                          <button
                            type="button"
                            onClick={() => { setCloneAnalysis(null); setCloneReferencePreviewUrl(""); setClonePresetName(""); }}
                            className="shrink-0 px-2.5 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 text-xs transition-colors"
                          >
                            Batal
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Social Auto Post Switch */}
              <div className="pt-2 border-t border-zinc-800/80">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Share2 className="h-4 w-4 text-purple-400" />
                    <span className="text-xs font-semibold text-zinc-200">Auto-Post ke Akun Media Sosial</span>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={autoPostInstant}
                      onChange={(e) => setAutoPostInstant(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-purple-600"></div>
                  </label>
                </div>

                {autoPostInstant && (
                  <div className="mt-2 space-y-2">
                    <span className="text-[11px] text-zinc-400 block">Pilih Akun Tujuan:</span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                      {accounts.length === 0 ? (
                        <div className="col-span-full py-3 px-4 rounded-xl border border-zinc-800 bg-zinc-900/40 text-center text-xs text-zinc-400">
                          Belum ada akun media sosial yang terhubung. Buka menu Social Accounts untuk menghubungkan akun.
                        </div>
                      ) : (
                        accounts.map((acc) => {
                          const { accId, platform, avatar, displayName, username, ownerName } = getAccountMeta(acc);
                          const isSelected = selectedAccountIds.includes(accId);
                          return (
                            <button
                              key={accId}
                              type="button"
                              onClick={() => {
                                setSelectedAccountIds((prev) =>
                                  isSelected ? prev.filter((id) => id !== accId) : [...prev, accId]
                                );
                              }}
                              className={cn(
                                "flex items-center gap-2.5 p-2 rounded-xl border text-xs text-left transition-all",
                                isSelected
                                  ? "border-purple-500 bg-purple-500/15 text-purple-200 ring-1 ring-purple-500/30"
                                  : "border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700"
                              )}
                            >
                              {avatar ? (
                                <img
                                  src={avatar}
                                  alt=""
                                  className="h-8 w-8 rounded-full object-cover shrink-0 ring-1 ring-zinc-700 bg-zinc-800"
                                />
                              ) : (
                                <div className="h-8 w-8 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0">
                                  <PlatformIcon type={platform} className="h-4 w-4 text-zinc-300" />
                                </div>
                              )}
                              <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-1.5">
                                  <span className="font-semibold text-xs text-zinc-200 truncate">{displayName}</span>
                                  <PlatformIcon type={platform} className="h-3 w-3 shrink-0" />
                                </div>
                                <div className="flex items-center gap-1.5 text-[10px] text-zinc-400 truncate">
                                  {username && <span className="truncate">{username}</span>}
                                  {user?.is_superadmin && ownerName && (
                                    <span className="text-[9px] px-1 rounded bg-zinc-800 text-zinc-400 border border-zinc-700/60 truncate">
                                      {ownerName}
                                    </span>
                                  )}
                                </div>
                              </div>
                              {isSelected && (
                                <div className="h-4 w-4 rounded-full bg-purple-500 flex items-center justify-center shrink-0 text-white">
                                  <Check className="h-2.5 w-2.5 stroke-[3]" />
                                </div>
                              )}
                            </button>
                          );
                        })
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Music Section for Social Post (TikTok, Instagram, Facebook) */}
              <div className="pt-3 border-t border-zinc-800/80 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Music className="h-4 w-4 text-purple-400" />
                    <div>
                      <span className="text-xs font-semibold text-zinc-200 block">
                        Musik Latar (TikTok, Instagram, Facebook)
                      </span>
                      <span className="text-[10px] text-zinc-500">
                        Disinkronkan otomatis melalui Repliz Gold API
                      </span>
                    </div>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={musicEnabledInstant}
                      onChange={(e) => {
                        const val = e.target.checked;
                        setMusicEnabledInstant(val);
                        if (val && instantMusicTracks.length === 0) {
                          loadInstantMusicTracks();
                        }
                        if (!val && audioPlayerRef.current) {
                          audioPlayerRef.current.pause();
                          setPlayingTrackId(null);
                        }
                      }}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-purple-600"></div>
                  </label>
                </div>

                {musicEnabledInstant && (
                  <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3 space-y-3">
                    {/* Mode selection: Auto vs Custom TikTok track */}
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => setMusicModeInstant("auto")}
                        className={cn(
                          "flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg border text-xs font-medium transition-all",
                          musicModeInstant === "auto"
                            ? "border-purple-500 bg-purple-500/15 text-purple-200 ring-1 ring-purple-500/30"
                            : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-zinc-200"
                        )}
                      >
                        <Sparkles className="h-3.5 w-3.5 text-purple-400" />
                        <span>Otomatis Trending</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setMusicModeInstant("custom");
                          if (instantMusicTracks.length === 0) loadInstantMusicTracks();
                        }}
                        className={cn(
                          "flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg border text-xs font-medium transition-all",
                          musicModeInstant === "custom"
                            ? "border-purple-500 bg-purple-500/15 text-purple-200 ring-1 ring-purple-500/30"
                            : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-zinc-200"
                        )}
                      >
                        <Music2 className="h-3.5 w-3.5 text-purple-400" />
                        <span>Pilih Lagu TikTok</span>
                      </button>
                    </div>

                    {musicModeInstant === "auto" ? (
                      <p className="text-[11px] text-zinc-400 bg-purple-500/5 border border-purple-500/20 rounded-lg p-2.5">
                        Platform (TikTok &amp; Instagram) akan secara otomatis memilih sound musik yang sedang viral dan relevan untuk visual album Anda.
                      </p>
                    ) : (
                      <div className="space-y-2.5">
                        {/* Selected Track Banner */}
                        {selectedTrackInstant ? (
                          <div className="flex items-center justify-between p-2.5 rounded-lg border border-purple-500/30 bg-purple-500/10">
                            <div className="flex items-center gap-2.5 min-w-0">
                              {selectedTrackInstant.thumbnail ? (
                                <img
                                  src={selectedTrackInstant.thumbnail}
                                  alt=""
                                  className="h-9 w-9 rounded-md object-cover border border-purple-500/40 shrink-0"
                                />
                              ) : (
                                <div className="h-9 w-9 rounded-md bg-purple-900/50 border border-purple-500/40 flex items-center justify-center shrink-0">
                                  <Music className="h-4 w-4 text-purple-300" />
                                </div>
                              )}
                              <div className="min-w-0">
                                <p className="text-xs font-semibold text-purple-200 truncate">{selectedTrackInstant.name}</p>
                                <p className="text-[10px] text-purple-300/80 truncate">{selectedTrackInstant.artist}</p>
                              </div>
                            </div>
                            <div className="flex items-center gap-1.5 shrink-0">
                              <button
                                type="button"
                                onClick={(e) => togglePlayAudio(selectedTrackInstant, e)}
                                className="p-1.5 rounded-md bg-purple-500/20 hover:bg-purple-500/40 text-purple-300 transition-colors"
                                title="Putar Demo"
                              >
                                {playingTrackId === selectedTrackInstant.id ? (
                                  <Pause className="h-3.5 w-3.5" />
                                ) : (
                                  <Play className="h-3.5 w-3.5" />
                                )}
                              </button>
                              <button
                                type="button"
                                onClick={() => setSelectedTrackInstant(null)}
                                className="p-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 text-[10px] transition-colors"
                              >
                                Ganti
                              </button>
                            </div>
                          </div>
                        ) : (
                          <>
                            {/* Search input */}
                            <div className="relative">
                              <input
                                type="text"
                                value={instantMusicSearch}
                                onChange={(e) => setInstantMusicSearch(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") {
                                    e.preventDefault();
                                    loadInstantMusicTracks(instantMusicSearch);
                                  }
                                }}
                                placeholder="Cari judul lagu / artis TikTok..."
                                className="w-full rounded-lg bg-zinc-950 border border-zinc-800 pl-8 pr-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-purple-500"
                              />
                              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500" />
                            </div>

                            {/* Track list */}
                            <div className="max-h-48 overflow-y-auto space-y-1 pr-1">
                              {loadingInstantMusic ? (
                                <div className="py-6 text-center text-xs text-zinc-500 flex items-center justify-center gap-2">
                                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                                  <span>Memuat track TikTok...</span>
                                </div>
                              ) : instantMusicTracks.length === 0 ? (
                                <div className="py-4 text-center text-xs text-zinc-500">
                                  Tidak ada track ditemukan. Tekan Enter untuk mencari.
                                </div>
                              ) : (
                                instantMusicTracks.map((track) => (
                                  <div
                                    key={track.id}
                                    onClick={() => setSelectedTrackInstant(track)}
                                    className="flex items-center justify-between p-2 rounded-lg border border-zinc-800/80 bg-zinc-950/60 hover:border-zinc-700 hover:bg-zinc-850 cursor-pointer transition-all"
                                  >
                                    <div className="flex items-center gap-2 min-w-0">
                                      {track.thumbnail ? (
                                        <img
                                          src={track.thumbnail}
                                          alt=""
                                          className="h-8 w-8 rounded object-cover shrink-0"
                                        />
                                      ) : (
                                        <div className="h-8 w-8 rounded bg-zinc-800 flex items-center justify-center shrink-0">
                                          <Music className="h-3.5 w-3.5 text-zinc-400" />
                                        </div>
                                      )}
                                      <div className="min-w-0">
                                        <p className="text-xs font-medium text-zinc-200 truncate">{track.name}</p>
                                        <p className="text-[10px] text-zinc-500 truncate">{track.artist}</p>
                                      </div>
                                    </div>
                                    <div className="flex items-center gap-1.5 shrink-0 ml-2">
                                      <button
                                        type="button"
                                        onClick={(e) => togglePlayAudio(track, e)}
                                        className="p-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
                                        title="Dengar Demo"
                                      >
                                        {playingTrackId === track.id ? (
                                          <Pause className="h-3 w-3" />
                                        ) : (
                                          <Play className="h-3 w-3" />
                                        )}
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => setSelectedTrackInstant(track)}
                                        className="px-2 py-1 rounded bg-purple-600/80 hover:bg-purple-600 text-white text-[10px] font-medium transition-colors"
                                      >
                                        Pilih
                                      </button>
                                    </div>
                                  </div>
                                ))
                              )}
                            </div>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Action Button */}
            <button
              onClick={handleInstantGenerate}
              disabled={generating}
              className="w-full flex items-center justify-center gap-2.5 py-3.5 px-6 rounded-2xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-semibold text-sm shadow-lg shadow-purple-600/20 transition-all disabled:opacity-50"
            >
              <Sparkles className={cn("h-4 w-4", generating && "animate-spin")} />
              <span>{generating ? "AI Sedang Menghasilkan Visual..." : "Buat Visual Post Sekarang"}</span>
            </button>
          </div>

          {/* Live Preview Column */}
          <div className="lg:col-span-5 space-y-4">
            <div className="rounded-2xl border border-zinc-800 bg-[#0e0e12] p-5">
              <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3 mb-4">
                <div className="flex items-center gap-2">
                  <Eye className="h-4 w-4 text-purple-400" />
                  <span className="text-sm font-semibold text-zinc-200">Pratinjau Hasil</span>
                </div>
                {latestResult && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                    Selesai
                  </span>
                )}
              </div>

              {latestResult ? (
                <div className="space-y-4">
                  {/* Media Viewer with Carousel Slider */}
                  <div className="relative rounded-xl overflow-hidden border border-zinc-800 bg-black flex items-center justify-center min-h-[360px] max-h-[520px] select-none">
                    {latestResult.video_url ? (
                      <video
                        src={formatMediaUrl(latestResult.video_url)}
                        controls
                        className="w-full h-auto max-h-[520px] object-contain"
                      />
                    ) : (
                      <>
                        <img
                          src={formatMediaUrl(
                            (latestResult.image_urls && latestResult.image_urls[activeSlideIndex]) ||
                              latestResult.image_urls?.[0]
                          )}
                          alt={`Preview ${activeSlideIndex + 1}`}
                          className="w-full h-auto max-h-[520px] object-contain transition-opacity duration-200"
                        />

                        {/* Top Badge: Slide Counter / Album tag */}
                        {latestResult.image_urls && latestResult.image_urls.length > 1 && (
                          <div className="absolute top-3 right-3 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-black/75 backdrop-blur-md text-white text-[11px] font-semibold border border-white/15 shadow-xl z-10">
                            <Layers className="h-3 w-3 text-purple-400" />
                            <span>Foto {activeSlideIndex + 1} dari {latestResult.image_urls.length}</span>
                          </div>
                        )}

                        {/* Prev Button */}
                        {latestResult.image_urls && latestResult.image_urls.length > 1 && (
                          <button
                            type="button"
                            onClick={() =>
                              setActiveSlideIndex(
                                (prev) => (prev - 1 + latestResult.image_urls.length) % latestResult.image_urls.length
                              )
                            }
                            className="absolute left-3 top-1/2 -translate-y-1/2 h-9 w-9 rounded-full bg-black/60 hover:bg-black/85 text-white flex items-center justify-center backdrop-blur-sm border border-white/20 shadow-xl transition-all hover:scale-105 active:scale-95 z-10"
                            aria-label="Foto Sebelumnya"
                          >
                            <ChevronLeft className="h-5 w-5" />
                          </button>
                        )}

                        {/* Next Button */}
                        {latestResult.image_urls && latestResult.image_urls.length > 1 && (
                          <button
                            type="button"
                            onClick={() =>
                              setActiveSlideIndex((prev) => (prev + 1) % latestResult.image_urls.length)
                            }
                            className="absolute right-3 top-1/2 -translate-y-1/2 h-9 w-9 rounded-full bg-black/60 hover:bg-black/85 text-white flex items-center justify-center backdrop-blur-sm border border-white/20 shadow-xl transition-all hover:scale-105 active:scale-95 z-10"
                            aria-label="Foto Berikutnya"
                          >
                            <ChevronRight className="h-5 w-5" />
                          </button>
                        )}

                        {/* Indicator Dots inside image */}
                        {latestResult.image_urls && latestResult.image_urls.length > 1 && (
                          <div className="absolute bottom-3 left-0 right-0 flex justify-center items-center gap-1.5 z-10">
                            {latestResult.image_urls.map((_: string, idx: number) => (
                              <button
                                key={idx}
                                type="button"
                                onClick={() => setActiveSlideIndex(idx)}
                                className={cn(
                                  "transition-all rounded-full h-1.5",
                                  activeSlideIndex === idx
                                    ? "w-6 bg-purple-500 shadow-md shadow-purple-500/50"
                                    : "w-1.5 bg-white/40 hover:bg-white/70"
                                )}
                                aria-label={`Pindah ke foto ${idx + 1}`}
                              />
                            ))}
                          </div>
                        )}
                      </>
                    )}
                  </div>

                  {/* Thumbnail Filmstrip Carousel for Multi-Image */}
                  {latestResult.image_urls && latestResult.image_urls.length > 1 && (
                    <div className="space-y-1.5 pt-1">
                      <div className="flex items-center justify-between text-[11px] text-zinc-400">
                        <span className="font-medium">Semua Foto Album ({latestResult.image_urls.length} Foto):</span>
                        <span className="text-zinc-500">Klik untuk memilih slide</span>
                      </div>
                      <div className="flex items-center gap-2 overflow-x-auto pb-1.5 pt-0.5 scrollbar-thin">
                        {latestResult.image_urls.map((url: string, idx: number) => (
                          <button
                            key={idx}
                            type="button"
                            onClick={() => setActiveSlideIndex(idx)}
                            className={cn(
                              "relative shrink-0 rounded-lg overflow-hidden border-2 transition-all",
                              activeSlideIndex === idx
                                ? "border-purple-500 ring-2 ring-purple-500/40 shadow-lg scale-105"
                                : "border-zinc-800 opacity-60 hover:opacity-100 hover:border-zinc-700"
                            )}
                          >
                            <img
                              src={formatMediaUrl(url)}
                              alt={`Thumbnail ${idx + 1}`}
                              className="h-16 w-12 object-cover"
                            />
                            <span className="absolute bottom-1 right-1 px-1 py-0.2 rounded bg-black/80 text-[9px] font-mono text-zinc-200">
                              #{idx + 1}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Actions for Latest Result */}
                  <div className="space-y-2 pt-1">
                    <div className="flex items-center gap-2">
                      <a
                        href={formatMediaUrl(
                          latestResult.video_url ||
                            (latestResult.image_urls && latestResult.image_urls[activeSlideIndex]) ||
                            latestResult.image_urls?.[0]
                        )}
                        download={`visual_post_${activeSlideIndex + 1}.png`}
                        className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-xs font-medium text-zinc-200 transition-colors"
                      >
                        <Download className="h-3.5 w-3.5" />
                        <span>Download #{activeSlideIndex + 1}</span>
                      </a>
                      {latestResult.image_urls && latestResult.image_urls.length > 1 && (
                        <button
                          type="button"
                          onClick={() => {
                            latestResult.image_urls.forEach((u: string, i: number) => {
                              const a = document.createElement("a");
                              a.href = formatMediaUrl(u);
                              a.download = `visual_album_${i + 1}.png`;
                              document.body.appendChild(a);
                              a.click();
                              document.body.removeChild(a);
                            });
                          }}
                          className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-xs font-medium text-zinc-200 transition-colors"
                          title="Download semua foto sekaligus"
                        >
                          <Download className="h-3.5 w-3.5 text-purple-400" />
                          <span>Unduh Semua ({latestResult.image_urls.length})</span>
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => {
                          const currentUrl =
                            latestResult.video_url ||
                            (latestResult.image_urls && latestResult.image_urls[activeSlideIndex]) ||
                            latestResult.image_urls?.[0];
                          navigator.clipboard.writeText(formatMediaUrl(currentUrl));
                          alert("URL media disalin ke clipboard!");
                        }}
                        className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-xs font-medium text-zinc-200 transition-colors"
                      >
                        <Copy className="h-3.5 w-3.5" />
                        <span>Salin URL</span>
                      </button>
                    </div>

                    {/* Direct Social Post Button for This Session Result */}
                    <button
                      type="button"
                      onClick={() => {
                        const runObj: ImageStudioRun = {
                          id: latestResult.id || 0,
                          user_id: user?.id || 0,
                          run_date: new Date().toISOString().split("T")[0],
                          session_name: latestResult.session_name || "Instant Studio",
                          topic: latestResult.topic || topic,
                          prompt: latestResult.prompt || prompt,
                          quote_hook: latestResult.quote_hook || quoteHook,
                          quote_headline: latestResult.quote_headline || quoteHeadline,
                          quote_body: latestResult.quote_body || quoteBody,
                          quote_author: latestResult.quote_author || quoteAuthor,
                          quote_handle: latestResult.quote_handle || quoteHandle,
                          media_type: latestResult.media_type || mediaType,
                          template_preset: latestResult.template || selectedTemplate,
                          font_name: latestResult.font || selectedFont,
                          aspect_ratio: latestResult.aspect_ratio || aspectRatio,
                          image_urls: latestResult.image_urls || [],
                          video_url: latestResult.video_url || null,
                          social_post_status: latestResult.social_post_status || "pending",
                          social_details: latestResult.social_details || null,
                          trigger_source: "instant_studio",
                          created_at: new Date().toISOString(),
                        };
                        handleOpenSocialModal(runObj);
                      }}
                      className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-md shadow-purple-600/20 transition-colors"
                    >
                      <Share2 className="h-3.5 w-3.5" />
                      <span>
                        {latestResult.image_urls && latestResult.image_urls.length > 1
                          ? `Posting Album ke Media Sosial (${latestResult.image_urls.length} Foto)`
                          : "Posting ke Media Sosial"}
                      </span>
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-24 text-center text-zinc-500 space-y-3">
                  <div className="h-12 w-12 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-600">
                    <ImageIcon className="h-6 w-6" />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-zinc-400">Belum ada visual yang dibuat di sesi ini</p>
                    <p className="text-[11px] text-zinc-600 mt-1">
                      Pilih template dan klik tombol buat untuk melihat pratinjau
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ─── TAB 2: AUTOMATION (HERMES SCHEDULER) ────────────────────────── */}
      {activeTab === "automation" && (
        <div className="max-w-4xl space-y-6">
          <div className="rounded-2xl border border-zinc-800 bg-[#0e0e12] p-6 space-y-6">
            {/* Master Toggle */}
            <div className="flex items-center justify-between pb-5 border-b border-zinc-800">
              <div>
                <h3 className="text-base font-semibold text-white">Automasi Harian Hermes Visual Post</h3>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Hermes akan secara mandiri menghasilkan visual harian berdasarkan topik &amp; jadwal slot waktu
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings?.enabled || false}
                  onChange={(e) => settings && setSettings({ ...settings, enabled: e.target.checked })}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
              </label>
            </div>

            {/* AI Gateway Status Info */}
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-emerald-500 ring-2 ring-emerald-500/20" />
                  <span className="font-semibold text-zinc-200">Koneksi AI Gateway (Dinamis dari Settings / System)</span>
                </div>
                <p className="text-zinc-400 font-mono text-[11px]">
                  Endpoint: <span className="text-cyan-400">{settings?.gateway_endpoint || "http://100.64.5.96:20128/v1/images/generations"}</span>
                </p>
              </div>
              <div className="flex items-center gap-3">
                <select
                  value={settings?.model_name || "auto"}
                  onChange={(e) => settings && setSettings({ ...settings, model_name: e.target.value })}
                  className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-cyan-500"
                >
                  <option value="auto">Model: Auto (Default System)</option>
                  <option value="ag/gemini-3.1-flash-image">ag/gemini-3.1-flash-image</option>
                  <option value="gemini-2.5-flash-image">gemini-2.5-flash-image</option>
                  <option value="gemini-2.0-flash-exp">gemini-2.0-flash-exp</option>
                </select>
                <a
                  href="/settings/system"
                  className="text-[11px] text-zinc-400 hover:text-cyan-400 underline transition-colors whitespace-nowrap"
                >
                  Settings &gt; System
                </a>
              </div>
            </div>

            {/* Visual Output Preset for Automation Runs */}
            <div className="space-y-3 pt-2">
              <div>
                <h4 className="text-xs font-semibold text-zinc-200 uppercase tracking-wider">
                  Preset Visual Output Harian
                </h4>
                <p className="text-[11px] text-zinc-500">
                  Gaya, format, dan sumber media yang dipakai setiap sesi automasi berjalan tanpa interaksi pengguna
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                    Tipe Output
                  </label>
                  <div className="grid grid-cols-2 gap-1.5">
                    <button
                      type="button"
                      onClick={() => settings && setSettings({ ...settings, media_type: "image" })}
                      className={cn(
                        "flex items-center justify-center gap-1.5 rounded-xl border py-2 text-xs font-medium transition-all",
                        settings?.media_type === "image"
                          ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                          : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-zinc-200"
                      )}
                    >
                      <ImageIcon className="h-3.5 w-3.5" />
                      <span>Gambar</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => settings && setSettings({ ...settings, media_type: "video_footage" })}
                      className={cn(
                        "flex items-center justify-center gap-1.5 rounded-xl border py-2 text-xs font-medium transition-all",
                        settings?.media_type === "video_footage"
                          ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                          : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-zinc-200"
                      )}
                    >
                      <Film className="h-3.5 w-3.5" />
                      <span>Video</span>
                    </button>
                  </div>
                </div>

                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                    Aspek Rasio
                  </label>
                  <select
                    value={settings?.aspect_ratio || "9:16"}
                    onChange={(e) => settings && setSettings({ ...settings, aspect_ratio: e.target.value })}
                    className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-emerald-500"
                  >
                    {aspectRatios.map((ar) => (
                      <option key={ar.id} value={ar.id}>
                        {ar.name} ({ar.width}x{ar.height})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                    Template Tipografi
                  </label>
                  <select
                    value={settings?.template_preset || "auto"}
                    onChange={(e) => settings && setSettings({ ...settings, template_preset: e.target.value })}
                    className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="auto">Auto (Dipilih AI sesuai topik)</option>
                    {templates.map((tpl) => (
                      <option key={tpl.id} value={tpl.id}>
                        {tpl.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                    Font Utama
                  </label>
                  <select
                    value={settings?.font_family || "auto"}
                    onChange={(e) => settings && setSettings({ ...settings, font_family: e.target.value })}
                    className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="auto">Auto (Sesuai Karakter Template)</option>
                    {fonts.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                  Sumber Latar Belakang
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { id: "ai_gemini", label: "AI Gemini", desc: "Generated Image API" },
                    { id: "pexels", label: "Pexels Stock", desc: "Stock Foto/Video" },
                    { id: "pixabay", label: "Pixabay Stock", desc: "Royalty Free" },
                  ].map((src) => (
                    <button
                      key={src.id}
                      type="button"
                      onClick={() => settings && setSettings({ ...settings, background_source: src.id })}
                      className={cn(
                        "flex flex-col text-left p-2.5 rounded-xl border text-xs transition-all",
                        settings?.background_source === src.id
                          ? "border-emerald-500 bg-emerald-500/10 text-white ring-1 ring-emerald-500/30"
                          : "border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                      )}
                    >
                      <span className="font-semibold">{src.label}</span>
                      <span className="text-[10px] text-zinc-500">{src.desc}</span>
                    </button>
                  ))}
                </div>
                <p className="text-[10px] text-zinc-500 mt-1.5">
                  Upload Background dan Clone Design butuh interaksi manual, jadi tidak tersedia untuk sesi automasi — pakai tab Instant Studio untuk membuat preset Clone Design, lalu pilih preset-nya di Template Tipografi di atas.
                </p>
              </div>

              {settings?.media_type === "video_footage" && (
                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1.5">
                    Durasi Footage (detik)
                  </label>
                  <input
                    type="number"
                    min={3}
                    max={30}
                    value={settings?.footage_duration_sec || 8}
                    onChange={(e) =>
                      settings && setSettings({ ...settings, footage_duration_sec: parseInt(e.target.value) || 8 })
                    }
                    className="w-32 rounded-xl bg-zinc-900 border border-zinc-800 px-3.5 py-2 text-xs text-zinc-200 focus:outline-none focus:border-emerald-500"
                  />
                </div>
              )}

              <div className="flex items-center justify-between pt-1">
                <div className="flex items-center gap-2">
                  <Music className="h-4 w-4 text-purple-400" />
                  <div>
                    <span className="text-xs font-semibold text-zinc-200 block">Musik Latar Otomatis</span>
                    <span className="text-[10px] text-zinc-500">Platform akan memilih sound trending yang relevan</span>
                  </div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings?.music_enabled || false}
                    onChange={(e) =>
                      settings && setSettings({ ...settings, music_enabled: e.target.checked, music_track: "auto" })
                    }
                    className="sr-only peer"
                  />
                  <div className="w-9 h-5 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-purple-600"></div>
                </label>
              </div>
            </div>

            {/* Publishing Mode: Scheduled Slots vs Always Update */}
            <div className="space-y-3">
              <div>
                <h4 className="text-xs font-semibold text-zinc-200 uppercase tracking-wider">
                  Mode Publikasi
                </h4>
                <p className="text-[11px] text-zinc-500">
                  Pilih antara jadwal slot tetap, atau pemantauan berita terus-menerus tanpa batas jumlah post harian
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => settings && setSettings({ ...settings, publish_mode: "scheduled" })}
                  className={cn(
                    "flex flex-col text-left p-3 rounded-xl border text-xs transition-all",
                    (settings?.publish_mode || "scheduled") === "scheduled"
                      ? "border-emerald-500 bg-emerald-500/10 text-white ring-1 ring-emerald-500/30"
                      : "border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                  )}
                >
                  <span className="font-semibold flex items-center gap-1.5"><Calendar className="h-3.5 w-3.5" /> Scheduled Mode</span>
                  <span className="text-[10px] text-zinc-500 mt-0.5">Posting mengikuti slot Pagi, Siang, Malam</span>
                </button>
                <button
                  type="button"
                  onClick={() => settings && setSettings({ ...settings, publish_mode: "always_update" })}
                  className={cn(
                    "flex flex-col text-left p-3 rounded-xl border text-xs transition-all",
                    settings?.publish_mode === "always_update"
                      ? "border-emerald-500 bg-emerald-500/10 text-white ring-1 ring-emerald-500/30"
                      : "border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                  )}
                >
                  <span className="font-semibold flex items-center gap-1.5"><RefreshCw className="h-3.5 w-3.5" /> Always Update Mode</span>
                  <span className="text-[10px] text-zinc-500 mt-0.5">Hermes terus memantau berita baru, tidak dibatasi jumlah posting harian</span>
                </button>
              </div>
            </div>

            {(settings?.publish_mode || "scheduled") === "scheduled" ? (
              /* Daily Slots Manager */
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-xs font-semibold text-zinc-200 uppercase tracking-wider">
                      Jadwal Slot Sesi Harian (Pagi / Siang / Malam)
                    </h4>
                    <p className="text-[11px] text-zinc-500">
                      Tentukan waktu dan kuota jumlah foto yang dihasilkan per sesi
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      if (!settings) return;
                      const newSlot: ImageStudioSlot = {
                        name: `Sesi ${settings.daily_slots.length + 1}`,
                        time: "12:00",
                        count: 2,
                        enabled: true,
                      };
                      setSettings({ ...settings, daily_slots: [...settings.daily_slots, newSlot] });
                    }}
                    className="flex items-center gap-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 px-3 py-1.5 text-xs text-zinc-300 font-medium transition-colors"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>Tambah Slot</span>
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {settings?.daily_slots.map((slot, idx) => (
                    <div key={idx} className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <input
                          type="text"
                          value={slot.name}
                          onChange={(e) => {
                            const name = e.target.value;
                            const updated = settings.daily_slots.map((s, i) => (i === idx ? { ...s, name } : s));
                            setSettings({ ...settings, daily_slots: updated });
                          }}
                          className="bg-transparent font-semibold text-xs text-zinc-200 focus:outline-none border-b border-transparent focus:border-zinc-700"
                        />
                        <button
                          type="button"
                          onClick={() => {
                            const updated = settings.daily_slots.filter((_, i) => i !== idx);
                            setSettings({ ...settings, daily_slots: updated });
                          }}
                          className="text-zinc-500 hover:text-rose-400 p-1"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>

                      <div className="flex items-center gap-2">
                        <Clock className="h-3.5 w-3.5 text-cyan-400 shrink-0" />
                        <input
                          type="time"
                          value={slot.time}
                          onChange={(e) => {
                            const time = e.target.value;
                            const updated = settings.daily_slots.map((s, i) => (i === idx ? { ...s, time } : s));
                            setSettings({ ...settings, daily_slots: updated });
                          }}
                          className="w-full rounded-lg bg-zinc-950 border border-zinc-800 px-2.5 py-1 text-xs text-zinc-200 focus:outline-none focus:border-cyan-500"
                        />
                      </div>

                      <div className="flex items-center justify-between text-xs text-zinc-400">
                        <span>Jumlah Foto:</span>
                        <input
                          type="number"
                          min={1}
                          max={10}
                          value={slot.count}
                          onChange={(e) => {
                            const count = parseInt(e.target.value) || 1;
                            const updated = settings.daily_slots.map((s, i) => (i === idx ? { ...s, count } : s));
                            setSettings({ ...settings, daily_slots: updated });
                          }}
                          className="w-16 rounded-lg bg-zinc-950 border border-zinc-800 px-2 py-0.5 text-xs text-right text-zinc-200 focus:outline-none"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              /* Always Update Panel: check interval + live news queue */
              <div className="space-y-3">
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-4 space-y-3">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1">
                        Interval Cek Berita (menit)
                      </label>
                      <p className="text-[10px] text-zinc-500">
                        Semakin kecil interval, semakin cepat Hermes bereaksi terhadap berita baru — tapi semakin besar beban ke server.
                      </p>
                    </div>
                    <input
                      type="number"
                      min={5}
                      max={120}
                      value={settings?.always_update_interval_min || 20}
                      onChange={(e) =>
                        settings && setSettings({ ...settings, always_update_interval_min: Math.max(5, Math.min(120, parseInt(e.target.value) || 20)) })
                      }
                      className="w-20 shrink-0 rounded-lg bg-zinc-950 border border-zinc-800 px-2.5 py-1.5 text-xs text-right text-zinc-200 focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                  {settings?.last_news_check_at && (
                    <p className="text-[10px] text-zinc-500">
                      Pengecekan terakhir: {new Date(settings.last_news_check_at).toLocaleString("id-ID")}
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-semibold text-zinc-200 uppercase tracking-wider">
                      Antrean Berita ({newsQueue.length})
                    </h4>
                    <button
                      type="button"
                      onClick={handleRefreshNewsQueue}
                      disabled={loadingNewsQueue}
                      className="flex items-center gap-1.5 text-[11px] text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-50"
                    >
                      <RefreshCw className={cn("h-3 w-3", loadingNewsQueue && "animate-spin")} />
                      <span>Muat Ulang</span>
                    </button>
                  </div>
                  <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
                    {newsQueue.length === 0 ? (
                      <p className="text-xs text-zinc-500 py-4 text-center">
                        Belum ada antrean. Antrean akan terisi otomatis setiap interval cek berita tercapai.
                      </p>
                    ) : (
                      newsQueue.map((item) => (
                        <div key={item.id} className="flex items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2">
                          <div className="min-w-0">
                            <p className="text-xs text-zinc-200 truncate">{item.article_title}</p>
                            <p className="text-[10px] text-zinc-500 truncate">{item.source_name} — {item.topic}</p>
                          </div>
                          <span
                            className={cn(
                              "shrink-0 px-2 py-0.5 rounded-full text-[10px] font-medium border",
                              item.status === "done" && "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
                              item.status === "pending" && "bg-zinc-800 text-zinc-400 border-zinc-700",
                              item.status === "processing" && "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
                              item.status === "failed" && "bg-rose-500/15 text-rose-300 border-rose-500/30"
                            )}
                          >
                            {item.status}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Topic Rotation */}
            <div className="space-y-3 pt-2">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-semibold text-zinc-200 uppercase tracking-wider flex items-center gap-2">
                    <span>Rotasi Topik Hermes Harian</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] bg-purple-500/20 text-purple-300 border border-purple-500/30">
                      {settings?.topics.length || 0} Briefing Aktif
                    </span>
                  </h4>
                  <p className="text-[11px] text-zinc-400 mt-0.5">
                    Masukkan briefing, topik, atau arahan konten apapun (bebas tanpa batasan domain). Hermes akan mandiri mengeksplorasi sudut pandang unik, merumuskan teks, dan menciptakan prompt visual secara kreatif setiap harinya.
                  </p>
                </div>
              </div>

              {/* Mode Konten Hermes: Quote / News / Both */}
              <div className="space-y-1.5">
                <span className="text-[10px] text-zinc-500 uppercase tracking-wider block">Mode Konten Hermes:</span>
                <div className="grid grid-cols-3 gap-1.5">
                  {[
                    { id: "quote", label: "Quote", desc: "Kutipan & wisdom dari AI" },
                    { id: "news", label: "Berita Terkini", desc: "Cari berita nyata per topik" },
                    { id: "both", label: "Keduanya", desc: "Acak quote & berita" },
                  ].map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => settings && setSettings({ ...settings, content_mode: m.id })}
                      className={cn(
                        "flex flex-col text-left p-2 rounded-xl border text-xs transition-all",
                        (settings?.content_mode || "quote") === m.id
                          ? "border-purple-500 bg-purple-500/10 text-white ring-1 ring-purple-500/30"
                          : "border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                      )}
                    >
                      <span className="font-semibold">{m.label}</span>
                      <span className="text-[10px] text-zinc-500">{m.desc}</span>
                    </button>
                  ))}
                </div>

                {(settings?.content_mode === "news" || settings?.content_mode === "both") && (
                  <div className="mt-2 p-3 rounded-xl border border-cyan-800/40 bg-cyan-500/5 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[11px] text-zinc-400">
                        Hermes akan mencari berita real-time untuk tiap topik di bawah (Google News, YouTube, TikTok) sebelum membuat konten.
                      </p>
                      <button
                        type="button"
                        onClick={handleCheckNewsNow}
                        disabled={loadingNewsPreview || !settings?.topics.length}
                        className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-[11px] font-semibold disabled:opacity-50 transition-colors"
                      >
                        <RefreshCw className={cn("h-3 w-3", loadingNewsPreview && "animate-spin")} />
                        <span>Cek Berita Sekarang</span>
                      </button>
                    </div>
                    {newsPreviewArticles.length > 0 && (
                      <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
                        {newsPreviewArticles.map((a, i) => (
                          <div key={i} className="rounded-lg border border-zinc-800 bg-zinc-900/70 px-3 py-2">
                            <p className="text-xs text-zinc-200">{a.title}</p>
                            <p className="text-[10px] text-zinc-500 mt-0.5">{a.source} — {a.recency} — topik: {a.topic}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Quick Inspiration Badges */}
              <div className="space-y-1.5">
                <span className="text-[10px] text-zinc-500 uppercase tracking-wider block">Inspirasi Cepat Topik (Klik untuk Menambahkan):</span>
                <div className="flex flex-wrap gap-1.5">
                  {[
                    "Motivasi & Stoikisme Modern",
                    "Mindset Sukses & Finansial",
                    "Strategi Bisnis & Kepemimpinan",
                    "Teknologi & Tren AI 2026",
                    "Produktivitas & Deep Work",
                    "Kesehatan Mental & Kebugaran",
                    "Parenting & Edukasi Keluarga",
                    "Filosofi Ketenangan Hidup",
                  ].map((sugg) => (
                    <button
                      key={sugg}
                      type="button"
                      onClick={() => {
                        if (!settings) return;
                        if (!settings.topics.includes(sugg)) {
                          setSettings({ ...settings, topics: [...settings.topics, sugg] });
                        }
                      }}
                      className="px-2.5 py-1 rounded-lg bg-zinc-900 hover:bg-zinc-800 border border-zinc-800/80 hover:border-zinc-700 text-[11px] text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-1"
                    >
                      <Plus className="h-3 w-3 text-purple-400" />
                      <span>{sugg}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex gap-2">
                <input
                  type="text"
                  value={newTopicInput}
                  onChange={(e) => setNewTopicInput(e.target.value)}
                  placeholder="Ketik topik atau briefing bebas (misal: Tips Mengatasi Burnout di Tempat Kerja)..."
                  className="flex-1 rounded-xl bg-zinc-900 border border-zinc-800 px-3.5 py-2 text-xs text-zinc-200 focus:outline-none focus:border-cyan-500"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && newTopicInput.trim() && settings) {
                      setSettings({ ...settings, topics: [...settings.topics, newTopicInput.trim()] });
                      setNewTopicInput("");
                    }
                  }}
                />
                <button
                  type="button"
                  onClick={() => {
                    if (newTopicInput.trim() && settings) {
                      setSettings({ ...settings, topics: [...settings.topics, newTopicInput.trim()] });
                      setNewTopicInput("");
                    }
                  }}
                  className="px-4 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-xs font-medium text-zinc-200 transition-colors"
                >
                  Tambah
                </button>
              </div>

              <div className="flex flex-wrap gap-2 pt-1">
                {settings?.topics.map((t, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-zinc-900 border border-zinc-800 text-xs text-zinc-300"
                  >
                    <span>{t}</span>
                    <button
                      type="button"
                      onClick={() => {
                        const updated = settings.topics.filter((_, i) => i !== idx);
                        setSettings({ ...settings, topics: updated });
                      }}
                      className="text-zinc-500 hover:text-rose-400 p-0.5"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            </div>

            {/* Target Social Accounts */}
            <div className="space-y-3 pt-2">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-semibold text-zinc-200 uppercase tracking-wider">
                    Auto-Post ke Akun Media Sosial
                  </h4>
                  <p className="text-[11px] text-zinc-400">
                    Secara otomatis jadwalkan dan publikasikan hasil visual ke akun media sosial setiap sesi berjalan
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings?.auto_post_enabled || false}
                    onChange={(e) => settings && setSettings({ ...settings, auto_post_enabled: e.target.checked })}
                    className="sr-only peer"
                  />
                  <div className="w-9 h-5 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-purple-600"></div>
                </label>
              </div>

              {settings?.auto_post_enabled && (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 pt-1">
                  {accounts.length === 0 ? (
                    <div className="col-span-full py-4 px-4 rounded-xl border border-zinc-800 bg-zinc-900/40 text-center text-xs text-zinc-400">
                      Belum ada akun media sosial yang terhubung. Kunjungi menu Social Accounts untuk menghubungkan akun Anda.
                    </div>
                  ) : (
                    accounts.map((acc) => {
                      const { accId, platform, avatar, displayName, username, ownerName } = getAccountMeta(acc);
                      const isSelected = (settings.target_account_ids || []).includes(accId);
                      return (
                        <button
                          key={accId}
                          type="button"
                          onClick={() => {
                            const prev = settings.target_account_ids || [];
                            const updated = isSelected ? prev.filter((id) => id !== accId) : [...prev, accId];
                            setSettings({ ...settings, target_account_ids: updated });
                          }}
                          className={cn(
                            "flex items-center gap-3 p-3 rounded-xl border text-xs text-left transition-all",
                            isSelected
                              ? "border-purple-500 bg-purple-500/15 text-purple-200 ring-1 ring-purple-500/30"
                              : "border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700"
                          )}
                        >
                          {avatar ? (
                            <img
                              src={avatar}
                              alt=""
                              className="h-8 w-8 rounded-full object-cover shrink-0 ring-1 ring-zinc-700 bg-zinc-800"
                            />
                          ) : (
                            <div className="h-8 w-8 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0">
                              <PlatformIcon type={platform} className="h-4 w-4 text-zinc-300" />
                            </div>
                          )}
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5">
                              <span className="font-semibold text-xs text-zinc-200 truncate">{displayName}</span>
                              <PlatformIcon type={platform} className="h-3 w-3 shrink-0" />
                            </div>
                            <div className="flex items-center gap-1.5 text-[10px] text-zinc-400 truncate">
                              {username && <span className="truncate">{username}</span>}
                              {user?.is_superadmin && ownerName && (
                                <span className="text-[9px] px-1 rounded bg-zinc-800 text-zinc-400 border border-zinc-700/60 truncate">
                                  {ownerName}
                                </span>
                              )}
                            </div>
                          </div>
                          {isSelected && (
                            <div className="h-4 w-4 rounded-full bg-purple-500 flex items-center justify-center shrink-0 text-white">
                              <Check className="h-2.5 w-2.5 stroke-[3]" />
                            </div>
                          )}
                        </button>
                      );
                    })
                  )}
                </div>
              )}
            </div>

            {/* Save Button */}
            <div className="pt-4 border-t border-zinc-800 flex justify-end">
              <button
                onClick={handleSaveSettings}
                disabled={savingSettings}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-colors shadow-md shadow-emerald-600/20 disabled:opacity-50"
              >
                <Check className="h-4 w-4" />
                <span>{savingSettings ? "Menyimpan..." : "Simpan Pengaturan Automasi"}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── TAB 3: HISTORY & GALLERY ────────────────────────────────────── */}
      {activeTab === "history" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-zinc-200">Riwayat Visual Post &amp; Carousel</h3>
            <button
              onClick={fetchInitialData}
              className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Segarkan</span>
            </button>
          </div>

          {history.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {history.map((run) => (
                <div
                  key={run.id}
                  className="rounded-2xl border border-zinc-800 bg-[#0e0e12] overflow-hidden flex flex-col justify-between"
                >
                  <div className="relative aspect-[9/16] bg-black max-h-[380px] overflow-hidden select-none">
                    {run.video_url ? (
                      <video
                        src={formatMediaUrl(run.video_url)}
                        controls
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <>
                        <img
                          src={formatMediaUrl(
                            run.image_urls?.[historySlideIndices[run.id] || 0] || run.image_urls?.[0]
                          )}
                          alt={run.topic}
                          className="w-full h-full object-cover transition-opacity duration-150"
                        />

                        {/* Slide badge if album */}
                        {run.image_urls && run.image_urls.length > 1 && (
                          <div className="absolute top-2.5 right-2.5 z-10">
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-purple-900/80 backdrop-blur-sm text-purple-200 border border-purple-500/30 flex items-center gap-1">
                              <Layers className="h-3 w-3" />
                              <span>Album {(historySlideIndices[run.id] || 0) + 1}/{run.image_urls.length}</span>
                            </span>
                          </div>
                        )}

                        {/* Prev/Next arrows on Card */}
                        {run.image_urls && run.image_urls.length > 1 && (
                          <>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setHistorySlideIndices((prev) => {
                                  const cur = prev[run.id] || 0;
                                  const total = run.image_urls.length;
                                  return { ...prev, [run.id]: (cur - 1 + total) % total };
                                });
                              }}
                              className="absolute left-1.5 top-1/2 -translate-y-1/2 h-7 w-7 rounded-full bg-black/65 hover:bg-black/90 text-white flex items-center justify-center backdrop-blur-sm border border-white/20 transition-all z-10"
                              aria-label="Foto Sebelumnya"
                            >
                              <ChevronLeft className="h-4 w-4" />
                            </button>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setHistorySlideIndices((prev) => {
                                  const cur = prev[run.id] || 0;
                                  const total = run.image_urls.length;
                                  return { ...prev, [run.id]: (cur + 1) % total };
                                });
                              }}
                              className="absolute right-1.5 top-1/2 -translate-y-1/2 h-7 w-7 rounded-full bg-black/65 hover:bg-black/90 text-white flex items-center justify-center backdrop-blur-sm border border-white/20 transition-all z-10"
                              aria-label="Foto Berikutnya"
                            >
                              <ChevronRight className="h-4 w-4" />
                            </button>
                            {/* Dots */}
                            <div className="absolute bottom-2 left-0 right-0 flex justify-center items-center gap-1 z-10">
                              {run.image_urls.map((_: string, idx: number) => (
                                <span
                                  key={idx}
                                  className={cn(
                                    "rounded-full h-1 transition-all",
                                    (historySlideIndices[run.id] || 0) === idx
                                      ? "w-4 bg-purple-500"
                                      : "w-1 bg-white/40"
                                  )}
                                />
                              ))}
                            </div>
                          </>
                        )}
                      </>
                    )}
                    <div className="absolute top-2.5 left-2.5 z-10">
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-black/70 backdrop-blur-sm text-zinc-200 border border-white/10 uppercase">
                        {run.template_preset}
                      </span>
                    </div>
                  </div>

                  <div className="p-4 space-y-2.5">
                    <div>
                      <h4 className="text-xs font-semibold text-zinc-200 line-clamp-1">{run.topic}</h4>
                      <p className="text-[11px] text-zinc-500 line-clamp-2 mt-0.5">
                        {run.quote_headline || run.prompt}
                      </p>
                    </div>

                    <div className="flex items-center justify-between text-[10px] text-zinc-500 border-t border-zinc-800/80 pt-2">
                      <span>{run.run_date}</span>
                      <span
                        className={cn(
                          "px-2 py-0.5 rounded-full capitalize",
                          run.social_post_status === "scheduled" || run.social_post_status === "published"
                            ? "bg-purple-500/15 text-purple-400"
                            : run.social_post_status === "partial"
                            ? "bg-amber-500/15 text-amber-400"
                            : "bg-zinc-800 text-zinc-400"
                        )}
                      >
                        {run.social_post_status}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 pt-1">
                      <button
                        type="button"
                        onClick={() => handleOpenSocialModal(run)}
                        className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs font-medium text-zinc-200 transition-colors"
                      >
                        <Share2 className="h-3.5 w-3.5 text-purple-400" />
                        <span>Posting</span>
                      </button>
                      <a
                        href={formatMediaUrl(
                          run.video_url ||
                            (run.image_urls && run.image_urls[historySlideIndices[run.id] || 0]) ||
                            run.image_urls?.[0]
                        )}
                        download={`visual_${(historySlideIndices[run.id] || 0) + 1}.png`}
                        className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors"
                        title="Download Foto"
                      >
                        <Download className="h-3.5 w-3.5" />
                      </a>
                      <button
                        type="button"
                        onClick={() => handleDeleteHistory(run.id)}
                        className="p-1.5 rounded-lg bg-zinc-800 hover:bg-rose-900/40 text-zinc-500 hover:text-rose-400 transition-colors"
                        title="Hapus"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-20 text-center text-zinc-500">
              <Layers className="h-8 w-8 mx-auto mb-2 text-zinc-600" />
              <p className="text-xs">Belum ada riwayat pembuatan visual</p>
            </div>
          )}
        </div>
      )}

      {/* ─── TAB 4: TEMPLATE CATALOG ─────────────────────────────────────── */}
      {activeTab === "catalog" && (
        <div className="space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-800/80 pb-4">
            <div>
              <h3 className="text-base font-semibold text-white flex items-center gap-2">
                <span>Katalog Tipografi Database</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-purple-500/15 text-purple-300 border border-purple-500/30">
                  {templates.length} Tersimpan di DB
                </span>
              </h3>
              <p className="text-xs text-zinc-400 mt-0.5">
                Preset tipografi disimpan secara dinamis di SQLite database. Anda dapat mengedit font, warna aksen, tata letak, atau menambahkan template kustom baru.
              </p>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={handleResetTemplates}
                disabled={resettingTemplates}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 text-xs text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-50"
                title="Reset kembali ke 12 preset standar pabrik"
              >
                <RotateCcw className={cn("h-3.5 w-3.5", resettingTemplates && "animate-spin")} />
                <span>Reset Default</span>
              </button>

              <button
                type="button"
                onClick={handleOpenCreateTemplateModal}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-md shadow-purple-600/20 transition-colors"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>Tambah Template</span>
              </button>
            </div>
          </div>

          {/* Sub Navigation for Database Typography Catalogue */}
          <div className="flex items-center gap-2 border-b border-zinc-800/60 pb-2">
            <button
              type="button"
              onClick={() => setCatalogSubTab("templates")}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5",
                catalogSubTab === "templates"
                  ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
              )}
            >
              <Layers className="h-3.5 w-3.5" />
              <span>Preset Template ({templates.length})</span>
            </button>
            <button
              type="button"
              onClick={() => setCatalogSubTab("fonts")}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5",
                catalogSubTab === "fonts"
                  ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
              )}
            >
              <Type className="h-3.5 w-3.5" />
              <span>Koleksi Font ({fontsDetailed.length || fonts.length})</span>
            </button>
            <button
              type="button"
              onClick={() => setCatalogSubTab("aspects")}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5",
                catalogSubTab === "aspects"
                  ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
              )}
            >
              <Sliders className="h-3.5 w-3.5" />
              <span>Rasio Kanvas ({aspectRatios.length})</span>
            </button>
            <button
              type="button"
              onClick={() => setCatalogSubTab("accents")}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5",
                catalogSubTab === "accents"
                  ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
              )}
            >
              <Palette className="h-3.5 w-3.5" />
              <span>Preset Aksen ({accentPresets.length})</span>
            </button>
          </div>

          {/* Sub-tab 1: Templates */}
          {catalogSubTab === "templates" && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {templates.map((tpl) => (
                <div
                  key={tpl.id}
                  className="rounded-2xl border border-zinc-800 bg-[#0e0e12] p-5 space-y-4 flex flex-col justify-between"
                >
                  <div className="space-y-3">
                    <img
                      src={imageStudioApi.getTemplatePreviewUrl(tpl.id, tpl.updated_at)}
                      alt={`Preview ${tpl.name}`}
                      loading="lazy"
                      className="w-full aspect-[9/16] max-h-56 object-cover rounded-xl border border-zinc-800 bg-zinc-950"
                    />
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-sm font-bold text-white truncate">{tpl.name}</span>
                        <span
                          className="h-3.5 w-3.5 rounded-full shrink-0 border border-white/20"
                          style={{ backgroundColor: tpl.recommended_accent }}
                          title={`Aksen: ${tpl.recommended_accent}`}
                        />
                      </div>
                      <span
                        className={cn(
                          "text-[10px] px-2 py-0.5 rounded-full font-medium border shrink-0",
                          tpl.is_builtin
                            ? "bg-zinc-800/80 text-zinc-400 border-zinc-700/60"
                            : "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                        )}
                      >
                        {tpl.is_builtin ? "Preset Bawaan" : "Kustom"}
                      </span>
                    </div>

                    <p className="text-xs text-zinc-400 line-clamp-2">{tpl.vibe}</p>

                    <div className="rounded-xl bg-zinc-900/80 p-3 space-y-1.5 text-[11px] text-zinc-400 border border-zinc-800/60 font-mono">
                      <div className="flex justify-between">
                        <span className="text-zinc-500">Engine Layout:</span>
                        <span className="text-cyan-400 font-medium truncate max-w-[150px]">{tpl.layout_type || tpl.id}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-zinc-500">Font Utama:</span>
                        <span className="text-zinc-200 font-medium truncate max-w-[150px]">{tpl.primary_font}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-zinc-500">Font Sekunder:</span>
                        <span className="text-zinc-200 font-medium truncate max-w-[150px]">{tpl.secondary_font}</span>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2 pt-2 border-t border-zinc-800/60">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedTemplate(tpl.id);
                          setAccentColor(tpl.recommended_accent);
                          setActiveTab("instant");
                        }}
                        className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl bg-purple-600/20 hover:bg-purple-600/30 border border-purple-500/40 text-purple-300 text-xs font-semibold transition-colors"
                      >
                        <Sparkles className="h-3.5 w-3.5" />
                        <span>Gunakan Template</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => handleOpenEditTemplateModal(tpl)}
                        className="p-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white transition-colors"
                        title="Edit Konfigurasi Template di Database"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>

                      {!tpl.is_builtin && (
                        <button
                          type="button"
                          onClick={() => handleDeleteTemplate(tpl.id, tpl.name)}
                          className="p-2 rounded-xl bg-zinc-800 hover:bg-rose-900/40 text-zinc-400 hover:text-rose-400 transition-colors"
                          title="Hapus Template Kustom dari Database"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Sub-tab 2: Fonts */}
          {catalogSubTab === "fonts" && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {(fontsDetailed.length > 0 ? fontsDetailed : fonts.map((fn, idx) => ({ id: `font_${idx}`, font_name: fn, file_name: `${fn.replace(/ /g, '')}.ttf`, is_builtin: 1 }))).map((f) => (
                <div key={f.id || f.font_name} className="rounded-2xl border border-zinc-800 bg-[#0e0e12] p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Type className="h-4 w-4 text-purple-400" />
                      <span className="text-xs font-bold text-white">{f.font_name}</span>
                    </div>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400 border border-zinc-700/60">
                      {f.is_builtin ? "Built-in TTF" : "Custom Font"}
                    </span>
                  </div>
                  <div className="rounded-xl bg-zinc-950 p-3 border border-zinc-800/80">
                    <p className="text-xs text-zinc-400 font-mono text-[10px] mb-1">File: {f.file_name}</p>
                    <p className="text-sm text-zinc-100 font-medium line-clamp-1" style={{ fontFamily: f.font_name }}>
                      The quick brown fox jumps over the lazy dog.
                    </p>
                  </div>
                  <div className="flex justify-between items-center text-[10px] text-zinc-500 pt-1 border-t border-zinc-800/60">
                    <span>Tabel: image_typography_fonts</span>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedFont(f.font_name);
                        setActiveTab("instant");
                      }}
                      className="text-purple-400 hover:text-purple-300 font-medium"
                    >
                      Pilih Font Ini
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Sub-tab 3: Canvas Aspect Ratios */}
          {catalogSubTab === "aspects" && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {aspectRatios.map((ar) => (
                <div key={ar.id} className="rounded-2xl border border-zinc-800 bg-[#0e0e12] p-4 space-y-3 flex flex-col justify-between">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-bold text-white">{ar.id}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                        {ar.width} x {ar.height} px
                      </span>
                    </div>
                    <p className="text-xs font-medium text-zinc-300">{ar.name}</p>
                    <p className="text-[11px] text-zinc-500 line-clamp-3">{ar.description}</p>
                  </div>
                  <div className="pt-2 border-t border-zinc-800/60 flex items-center justify-between">
                    <span className="text-[10px] text-zinc-500 font-mono">SQLite DB</span>
                    <button
                      type="button"
                      onClick={() => {
                        setAspectRatio(ar.id);
                        setActiveTab("instant");
                      }}
                      className="text-xs text-cyan-400 hover:text-cyan-300 font-medium"
                    >
                      Gunakan Rasio
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Sub-tab 4: Accent Color Presets */}
          {catalogSubTab === "accents" && (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7 gap-3">
              {accentPresets.map((ac) => (
                <button
                  key={ac.id}
                  type="button"
                  onClick={() => {
                    setAccentColor(ac.hex);
                    setActiveTab("instant");
                  }}
                  className="rounded-xl border border-zinc-800 bg-[#0e0e12] p-3 text-center space-y-2 hover:border-zinc-700 transition-all group"
                >
                  <div
                    className="h-9 w-full rounded-lg border border-white/20 shadow-inner group-hover:scale-105 transition-transform"
                    style={{ backgroundColor: ac.hex }}
                  />
                  <div>
                    <p className="text-xs font-bold text-white">{ac.name}</p>
                    <p className="text-[10px] font-mono text-zinc-400">{ac.hex}</p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ─── Social Publish Modal ────────────────────────────────────────── */}
      {socialModalOpen && selectedRunForSocial && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl border border-zinc-800 bg-[#0c0c0f] p-6 space-y-5 shadow-2xl animate-in fade-in-50 zoom-in-95">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div className="flex items-center gap-2">
                <Share2 className="h-4 w-4 text-purple-400" />
                <h3 className="text-sm font-bold text-white">Posting ke Media Sosial</h3>
              </div>
              <button
                onClick={() => {
                  setSocialModalOpen(false);
                  if (audioPlayerRef.current) {
                    audioPlayerRef.current.pause();
                    setPlayingTrackId(null);
                  }
                }}
                className="text-zinc-500 hover:text-zinc-300"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {publishSuccessMessage ? (
              <div className="py-4 text-center space-y-3">
                <CheckCircle2 className="h-8 w-8 text-emerald-400 mx-auto" />
                <p className="text-xs text-zinc-300">{publishSuccessMessage}</p>
                <button
                  onClick={() => setSocialModalOpen(false)}
                  className="px-4 py-2 rounded-xl bg-zinc-800 text-xs text-white"
                >
                  Tutup
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Post Summary & Bulking Album Indicator */}
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">
                      Format Pengiriman
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30">
                      {selectedRunForSocial.image_urls && selectedRunForSocial.image_urls.length > 1
                        ? `Carousel Album (${selectedRunForSocial.image_urls.length} Foto)`
                        : selectedRunForSocial.video_url
                        ? "Video"
                        : "Foto Tunggal"}
                    </span>
                  </div>

                  {selectedRunForSocial.image_urls && selectedRunForSocial.image_urls.length > 1 ? (
                    <div className="space-y-1.5 pt-1">
                      <p className="text-[11px] text-zinc-400">
                        Seluruh {selectedRunForSocial.image_urls.length} foto akan dikirim sekaligus sebagai album carousel (bulking) ke platform media sosial yang mendukung.
                      </p>
                      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 pt-0.5">
                        {selectedRunForSocial.image_urls.map((u: string, idx: number) => (
                          <img
                            key={idx}
                            src={formatMediaUrl(u)}
                            alt=""
                            className="h-14 w-10 rounded-md object-cover border border-zinc-700 shrink-0"
                          />
                        ))}
                      </div>
                    </div>
                  ) : (
                    <p className="text-[11px] text-zinc-400">
                      Topik: <span className="text-zinc-200 font-medium">{selectedRunForSocial.topic}</span>
                    </p>
                  )}
                </div>

                {/* Music Options inside Modal */}
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Music className="h-4 w-4 text-purple-400" />
                      <div>
                        <span className="text-xs font-semibold text-zinc-200 block">
                          Sertakan Musik Latar
                        </span>
                        <span className="text-[10px] text-zinc-500">
                          TikTok, Instagram, Facebook (Repliz Gold)
                        </span>
                      </div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={modalMusicEnabled}
                        onChange={(e) => {
                          const val = e.target.checked;
                          setModalMusicEnabled(val);
                          if (val && modalMusicTracks.length === 0) {
                            loadModalMusicTracks();
                          }
                          if (!val && audioPlayerRef.current) {
                            audioPlayerRef.current.pause();
                            setPlayingTrackId(null);
                          }
                        }}
                        className="sr-only peer"
                      />
                      <div className="w-9 h-5 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-purple-600"></div>
                    </label>
                  </div>

                  {modalMusicEnabled && (
                    <div className="space-y-2 pt-1 border-t border-zinc-800/80">
                      <div className="grid grid-cols-2 gap-2">
                        <button
                          type="button"
                          onClick={() => setModalMusicMode("auto")}
                          className={cn(
                            "flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg border text-xs font-medium transition-all",
                            modalMusicMode === "auto"
                              ? "border-purple-500 bg-purple-500/15 text-purple-200 ring-1 ring-purple-500/30"
                              : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-zinc-200"
                          )}
                        >
                          <Sparkles className="h-3 w-3 text-purple-400" />
                          <span>Otomatis Trending</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setModalMusicMode("custom");
                            if (modalMusicTracks.length === 0) loadModalMusicTracks();
                          }}
                          className={cn(
                            "flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg border text-xs font-medium transition-all",
                            modalMusicMode === "custom"
                              ? "border-purple-500 bg-purple-500/15 text-purple-200 ring-1 ring-purple-500/30"
                              : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-zinc-200"
                          )}
                        >
                          <Music2 className="h-3 w-3 text-purple-400" />
                          <span>Pilih Lagu TikTok</span>
                        </button>
                      </div>

                      {modalMusicMode === "auto" ? (
                        <p className="text-[10px] text-zinc-400 bg-purple-500/5 border border-purple-500/20 rounded-md p-2">
                          Platform media sosial akan menyisipkan audio trending teratas secara otomatis.
                        </p>
                      ) : (
                        <div className="space-y-2">
                          {modalSelectedTrack ? (
                            <div className="flex items-center justify-between p-2 rounded-lg border border-purple-500/30 bg-purple-500/10">
                              <div className="flex items-center gap-2 min-w-0">
                                {modalSelectedTrack.thumbnail ? (
                                  <img
                                    src={modalSelectedTrack.thumbnail}
                                    alt=""
                                    className="h-8 w-8 rounded object-cover shrink-0"
                                  />
                                ) : (
                                  <div className="h-8 w-8 rounded bg-purple-900/40 flex items-center justify-center shrink-0">
                                    <Music className="h-3.5 w-3.5 text-purple-300" />
                                  </div>
                                )}
                                <div className="min-w-0">
                                  <p className="text-xs font-semibold text-purple-200 truncate">{modalSelectedTrack.name}</p>
                                  <p className="text-[10px] text-purple-300/80 truncate">{modalSelectedTrack.artist}</p>
                                </div>
                              </div>
                              <div className="flex items-center gap-1 shrink-0">
                                <button
                                  type="button"
                                  onClick={(e) => togglePlayAudio(modalSelectedTrack, e)}
                                  className="p-1 rounded bg-purple-500/20 text-purple-300 hover:bg-purple-500/40"
                                  title="Putar Demo"
                                >
                                  {playingTrackId === modalSelectedTrack.id ? (
                                    <Pause className="h-3 w-3" />
                                  ) : (
                                    <Play className="h-3 w-3" />
                                  )}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setModalSelectedTrack(null)}
                                  className="px-1.5 py-0.5 rounded bg-zinc-800 text-[10px] text-zinc-300 hover:bg-zinc-700"
                                >
                                  Ganti
                                </button>
                              </div>
                            </div>
                          ) : (
                            <>
                              <div className="relative">
                                <input
                                  type="text"
                                  value={modalMusicSearch}
                                  onChange={(e) => setModalMusicSearch(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") {
                                      e.preventDefault();
                                      loadModalMusicTracks(modalMusicSearch);
                                    }
                                  }}
                                  placeholder="Cari lagu TikTok..."
                                  className="w-full rounded-lg bg-zinc-950 border border-zinc-800 pl-7 pr-2 py-1 text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-purple-500"
                                />
                                <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-zinc-500" />
                              </div>

                              <div className="max-h-36 overflow-y-auto space-y-1 pr-1">
                                {loadingModalMusic ? (
                                  <div className="py-4 text-center text-[11px] text-zinc-500 flex items-center justify-center gap-1.5">
                                    <RefreshCw className="h-3 w-3 animate-spin" />
                                    <span>Memuat musik...</span>
                                  </div>
                                ) : modalMusicTracks.length === 0 ? (
                                  <div className="py-2 text-center text-[10px] text-zinc-500">
                                    Tekan Enter untuk mencari lagu.
                                  </div>
                                ) : (
                                  modalMusicTracks.map((track) => (
                                    <div
                                      key={track.id}
                                      onClick={() => setModalSelectedTrack(track)}
                                      className="flex items-center justify-between p-1.5 rounded-lg border border-zinc-800/80 bg-zinc-950/60 hover:bg-zinc-850 cursor-pointer"
                                    >
                                      <div className="flex items-center gap-1.5 min-w-0">
                                        {track.thumbnail && (
                                          <img src={track.thumbnail} alt="" className="h-6 w-6 rounded object-cover shrink-0" />
                                        )}
                                        <div className="min-w-0">
                                          <p className="text-[11px] font-medium text-zinc-200 truncate">{track.name}</p>
                                          <p className="text-[9px] text-zinc-500 truncate">{track.artist}</p>
                                        </div>
                                      </div>
                                      <div className="flex items-center gap-1 shrink-0 ml-1">
                                        <button
                                          type="button"
                                          onClick={(e) => togglePlayAudio(track, e)}
                                          className="p-1 rounded bg-zinc-800 text-zinc-300"
                                        >
                                          {playingTrackId === track.id ? (
                                            <Pause className="h-2.5 w-2.5" />
                                          ) : (
                                            <Play className="h-2.5 w-2.5" />
                                          )}
                                        </button>
                                        <button
                                          type="button"
                                          onClick={() => setModalSelectedTrack(track)}
                                          className="px-1.5 py-0.5 rounded bg-purple-600 text-white text-[9px]"
                                        >
                                          Pilih
                                        </button>
                                      </div>
                                    </div>
                                  ))
                                )}
                              </div>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div>
                  <span className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-2">
                    Pilih Akun Tujuan:
                  </span>
                  <div className="space-y-1.5 max-h-52 overflow-y-auto pr-0.5">
                    {accounts.length === 0 ? (
                      <div className="py-4 px-3 rounded-xl border border-zinc-800 bg-zinc-900/40 text-center text-xs text-zinc-400">
                        Belum ada akun media sosial yang terhubung.
                      </div>
                    ) : (
                      accounts.map((acc) => {
                        const { accId, platform, avatar, displayName, username, ownerName } = getAccountMeta(acc);
                        const isSelected = selectedAccountIds.includes(accId);
                        return (
                          <button
                            key={accId}
                            type="button"
                            onClick={() => {
                              setSelectedAccountIds((prev) =>
                                isSelected ? prev.filter((id) => id !== accId) : [...prev, accId]
                              );
                            }}
                            className={cn(
                              "w-full flex items-center justify-between p-2.5 rounded-xl border text-xs text-left transition-all",
                              isSelected
                                ? "border-purple-500 bg-purple-500/15 text-purple-200 ring-1 ring-purple-500/30"
                                : "border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700"
                            )}
                          >
                            <div className="flex items-center gap-2.5 min-w-0 flex-1">
                              {avatar ? (
                                <img
                                  src={avatar}
                                  alt=""
                                  className="h-8 w-8 rounded-full object-cover shrink-0 ring-1 ring-zinc-700 bg-zinc-800"
                                />
                              ) : (
                                <div className="h-8 w-8 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0">
                                  <PlatformIcon type={platform} className="h-4 w-4 text-zinc-300" />
                                </div>
                              )}
                              <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-1.5">
                                  <span className="font-semibold text-xs text-zinc-200 truncate">{displayName}</span>
                                  <PlatformIcon type={platform} className="h-3 w-3 shrink-0" />
                                </div>
                                <div className="flex items-center gap-1.5 text-[10px] text-zinc-400 truncate">
                                  {username && <span className="truncate">{username}</span>}
                                  {user?.is_superadmin && ownerName && (
                                    <span className="text-[9px] px-1 rounded bg-zinc-800 text-zinc-400 border border-zinc-700/60 truncate">
                                      {ownerName}
                                    </span>
                                  )}
                                </div>
                              </div>
                            </div>
                            {isSelected && (
                              <div className="h-4 w-4 rounded-full bg-purple-500 flex items-center justify-center shrink-0 text-white ml-2">
                                <Check className="h-2.5 w-2.5 stroke-[3]" />
                              </div>
                            )}
                          </button>
                        );
                      })
                    )}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handlePublishFromModal}
                  disabled={publishingSocial || selectedAccountIds.length === 0}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold transition-colors disabled:opacity-50"
                >
                  <Send className="h-3.5 w-3.5" />
                  <span>
                    {publishingSocial
                      ? "Menjadwalkan..."
                      : selectedRunForSocial.image_urls && selectedRunForSocial.image_urls.length > 1
                      ? `Jadwalkan Posting Album (${selectedRunForSocial.image_urls.length} Foto)`
                      : "Jadwalkan Posting Sekarang"}
                  </span>
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── Database Template Create / Edit Modal ──────────────────────── */}
      {templateModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg rounded-2xl border border-zinc-800 bg-[#0c0c0f] p-6 space-y-5 shadow-2xl animate-in fade-in-50 zoom-in-95">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div className="flex items-center gap-2">
                <Palette className="h-4 w-4 text-purple-400" />
                <h3 className="text-sm font-bold text-white">
                  {editingTemplate ? `Edit Template Database: ${editingTemplate.name}` : "Tambah Template Tipografi Baru"}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setTemplateModalOpen(false)}
                className="text-zinc-500 hover:text-zinc-300"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              {!editingTemplate && (
                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1">
                    Template ID (Slug Unik)
                  </label>
                  <input
                    type="text"
                    value={templateForm.id}
                    onChange={(e) => setTemplateForm({ ...templateForm, id: e.target.value })}
                    placeholder="misal: retro_warm_quote (opsional, auto-generate dari nama)"
                    className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3.5 py-2 text-xs text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-purple-500 font-mono"
                  />
                </div>
              )}

              <div>
                <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1">
                  Nama Template
                </label>
                <input
                  type="text"
                  value={templateForm.name}
                  onChange={(e) => setTemplateForm({ ...templateForm, name: e.target.value })}
                  placeholder="misal: Retro Coffee Minimalist..."
                  className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3.5 py-2 text-xs text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-purple-500"
                />
              </div>

              <div>
                <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1">
                  Deskripsi Gaya / Vibe
                </label>
                <input
                  type="text"
                  value={templateForm.vibe}
                  onChange={(e) => setTemplateForm({ ...templateForm, vibe: e.target.value })}
                  placeholder="misal: Warm tones, vintage typography, soft background..."
                  className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3.5 py-2 text-xs text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-purple-500"
                />
              </div>

              <div>
                <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1">
                  Engine Tata Letak (Layout Base)
                </label>
                <select
                  value={templateForm.layout_type}
                  onChange={(e) => setTemplateForm({ ...templateForm, layout_type: e.target.value })}
                  className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-purple-500"
                >
                  {LAYOUT_ENGINE_OPTIONS.map((opt) => (
                    <option key={opt.id} value={opt.id}>
                      {opt.label} ({opt.id})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1">
                    Font Utama (Headline/Kutipan)
                  </label>
                  <select
                    value={templateForm.primary_font}
                    onChange={(e) => setTemplateForm({ ...templateForm, primary_font: e.target.value })}
                    className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-purple-500"
                  >
                    {fonts.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1">
                    Font Sekunder (Body/Tag/Author)
                  </label>
                  <select
                    value={templateForm.secondary_font}
                    onChange={(e) => setTemplateForm({ ...templateForm, secondary_font: e.target.value })}
                    className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-purple-500"
                  >
                    {fonts.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider block mb-1">
                  Warna Aksen Rekomendasi
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={templateForm.recommended_accent}
                    onChange={(e) => setTemplateForm({ ...templateForm, recommended_accent: e.target.value })}
                    className="w-32 rounded-xl bg-zinc-900 border border-zinc-800 px-3 py-2 text-xs text-zinc-100 font-mono uppercase focus:outline-none focus:border-purple-500"
                  />
                  <div className="flex items-center gap-1.5">
                    {(accentPresets.length > 0 ? accentPresets : ACCENT_PRESETS).map((p) => (
                      <button
                        key={p.hex}
                        type="button"
                        onClick={() => setTemplateForm({ ...templateForm, recommended_accent: p.hex })}
                        className={cn(
                          "h-6 w-6 rounded-full border transition-all",
                          templateForm.recommended_accent.toLowerCase() === p.hex.toLowerCase()
                            ? "scale-110 border-white ring-2 ring-purple-500/50"
                            : "border-transparent"
                        )}
                        style={{ backgroundColor: p.hex }}
                        title={p.name}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div className="pt-3 border-t border-zinc-800 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setTemplateModalOpen(false)}
                className="px-4 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-xs font-medium text-zinc-300 transition-colors"
              >
                Batal
              </button>
              <button
                type="button"
                onClick={handleSaveTemplate}
                disabled={savingTemplate}
                className="flex items-center gap-1.5 px-5 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-md shadow-purple-600/20 transition-colors disabled:opacity-50"
              >
                <Check className="h-3.5 w-3.5" />
                <span>{savingTemplate ? "Menyimpan ke DB..." : "Simpan ke Database"}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
