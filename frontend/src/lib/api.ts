// Auto-detect API base: use same hostname as frontend but backend port (8000)
// This ensures nip.io, local LAN, and production IPs work without manual env config
export function detectApiBase(): string {
  if (typeof window !== "undefined" && window.location && window.location.hostname) {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:8000`;
  }
  const envUrl = import.meta.env.VITE_API_URL;
  if (envUrl && typeof envUrl === "string" && envUrl.trim() !== "") {
    return envUrl;
  }
  return "http://localhost:8000";
}
const API_BASE = detectApiBase();

function getToken(): string | null {
  return localStorage.getItem("access_token");
}

function setTokens(access: string, refresh: string) {
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
}

function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) return null;

  try {
    const res = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) {
      clearTokens();
      return null;
    }
    const data = await res.json();
    setTokens(data.access_token, data.refresh_token);
    return data.access_token;
  } catch {
    clearTokens();
    return null;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${path}`;
  let token = getToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let res = await fetch(url, { ...options, headers });

  if (res.status === 401 && token) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      headers["Authorization"] = `Bearer ${newToken}`;
      res = await fetch(url, { ...options, headers });
    } else {
      clearTokens();
      window.location.href = "/login";
      throw new Error("Session expired");
    }
  }

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, error.detail || "Request failed");
  }

  return res.json();
}

async function requestForm<T>(
  path: string,
  formData: FormData,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${path}`;
  let token = getToken();

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let res = await fetch(url, { ...options, method: options.method || "POST", body: formData, headers });

  if (res.status === 401 && token) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      headers["Authorization"] = `Bearer ${newToken}`;
      res = await fetch(url, { ...options, method: options.method || "POST", body: formData, headers });
    } else {
      clearTokens();
      window.location.href = "/login";
      throw new Error("Session expired");
    }
  }

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, error.detail || "Request failed");
  }

  return res.json();
}

async function requestFormWithProgress<T>(
  path: string,
  formData: FormData,
  onProgress?: (percent: number) => void
): Promise<T> {
  const url = `${API_BASE}${path}`;
  let token = getToken();

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);

    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          onProgress(percent);
        }
      };
    }

    xhr.onload = async () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const json = JSON.parse(xhr.responseText);
          resolve(json);
        } catch {
          resolve({} as T);
        }
      } else if (xhr.status === 401 && token) {
        const newToken = await refreshAccessToken();
        if (newToken) {
          try {
            const res = await requestFormWithProgress<T>(path, formData, onProgress);
            resolve(res);
          } catch (err) {
            reject(err);
          }
        } else {
          clearTokens();
          window.location.href = "/login";
          reject(new Error("Session expired"));
        }
      } else {
        try {
          const error = JSON.parse(xhr.responseText);
          reject(new ApiError(xhr.status, error.detail || "Upload failed"));
        } catch {
          reject(new ApiError(xhr.status, xhr.statusText || "Upload failed"));
        }
      }
    };

    xhr.onerror = () => {
      reject(new ApiError(0, "Network error during upload"));
    };

    xhr.ontimeout = () => {
      reject(new ApiError(0, "Upload timed out"));
    };

    xhr.send(formData);
  });
}

async function requestBlob(path: string): Promise<Blob> {
  const url = `${API_BASE}${path}`;
  let token = getToken();
  const headers: Record<string, string> = { Accept: "image/*" };
  if (token) headers.Authorization = `Bearer ${token}`;

  let res = await fetch(url, { headers });
  if (res.status === 401 && token) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      headers.Authorization = `Bearer ${newToken}`;
      res = await fetch(url, { headers });
    } else {
      clearTokens();
      window.location.href = "/login";
      throw new Error("Session expired");
    }
  }

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, error.detail || "Failed to load image");
  }
  return res.blob();
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

// ─── Auth API ─────────────────────────────────────────────────────────────────

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
  role_id: number;
  permissions: string[];
  is_superadmin: boolean;
  is_premium: boolean;
  is_active: boolean;
  features: string[];
  pipeline: string;
  created_at: string | null;
  last_login_at: string | null;
}

export const auth = {
  async login(email: string, password: string): Promise<LoginResponse> {
    const data = await request<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setTokens(data.access_token, data.refresh_token);
    return data;
  },

  async logout(): Promise<void> {
    const refreshToken = localStorage.getItem("refresh_token");
    try {
      await request("/api/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } finally {
      clearTokens();
    }
  },

  async me(): Promise<User> {
    const res = await request<{ success: boolean; data: User }>("/api/auth/me");
    return res.data;
  },

  isAuthenticated(): boolean {
    return !!getToken();
  },
};

// ─── Jobs API ─────────────────────────────────────────────────────────────────

export interface CreateJobPayload {
  youtube_url: string;
  force_reprocess?: boolean;
  style_preset?: string;
  target_aspect_ratio?: string;
  hook_engine?: string;
  hook_style?: string;
  broll_enabled?: boolean;
  autogrid_enabled?: boolean;
  /** Object image+text cards (OpenCV). Only when broll_enabled. */
  broll_image_overlay?: boolean;
  /** Top stock behind person cutout. Only when broll_enabled. */
  broll_behind_person?: boolean;
  /** Full-frame video splice. Only when broll_enabled. */
  broll_video_footage?: boolean;
  text_emphasis_enabled?: boolean;
  // Remotion fields
  use_remotion?: boolean;
  ai_layer_enabled?: boolean;
  threejs_enabled?: boolean;
  remotion_quality?: string;
  // Full style configs from Custom Style Editor
  hook_style_config?: Record<string, any>;
  subtitle_style_config?: Record<string, any>;
  text_emphasis_style_config?: Record<string, any>;
  watermark_config?: Record<string, any>;
  processing_mode?: "analyze" | "direct";
  custom_hook?: string;
  // Canvas background (16:9 / 1:1 only)
  background_mode?: "template" | "upload" | null;
  background_template_id?: string | null;
  background_image_data_url?: string | null;
  // Custom clips and source job from analyze-review preview step
  custom_clips?: Array<{
    rank: number;
    start: number;
    end: number;
    hook?: string | null;
    score?: number | null;
  }>;
  source_job_id?: string;
}

export type UploadJobPayload = Omit<CreateJobPayload, "youtube_url">;

export interface JobSummary {
  job_id: string;
  youtube_url: string;
  source_type?: string;
  source_label?: string;
  video_title: string;
  status: string;
  video_duration: number | null;
  clips_total: number;
  clips_success: number;
  clips_failed: number;
  style_preset: string | null;
  target_aspect_ratio: string | null;
  pipeline_version: string;
  active_operations?: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface JobListResponse {
  success: boolean;
  data: JobSummary[];
  pagination: {
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
  };
}

export interface JobResponse {
  job_id: string;
  youtube_url: string;
  source_type?: string;
  source_label?: string;
  status: string;
  video_duration: number | null;
  render_progress: string | null;
  error_message: string | null;
  clips_data: any;
  clips_total: number;
  clips_success: number;
  clips_failed: number;
  is_cached?: boolean;
  // v0.4 fields
  style_preset: string | null;
  target_aspect_ratio: string | null;
  // v3.0 Remotion fields
  use_remotion: boolean;
  ai_layer_enabled: boolean;
  threejs_enabled: boolean;
  remotion_quality: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface ClipInfo {
  rank: number;
  score: number | null;
  start: number;
  end: number;
  duration: number;
  hook: string | null;
  reason: string | null;
  has_words: boolean;
  word_count: number;
  has_final: boolean;
  has_thumbnail: boolean;
  render_status: "ready" | "processing" | "unavailable";
  virality?: {
    score?: number;
    total?: number;
    factors?: string[];
    hook?: number;
    hook_punch?: number;
    retention?: number;
    emotion?: number;
    visual?: number;
    visual_density?: number;
  } | null;
  cta?: { text?: string; type?: string; kind?: string; duration_sec?: number; duration?: number; position?: string } | null;
  retention_hints?: { suggested_cuts?: Array<{ start: number; end: number; reason?: string }> } | null;
  thumb_seek?: number | null;
  object_overlay_events?: Array<Record<string, any>>;
  visual_entities?: Array<Record<string, any>>;
  hyperframes_polish?: {
    template?: string;
    mode?: string;
    events?: number;
    labels?: string[];
    hook_engine?: string;
    subtitle_engine?: string;
    hook_template?: string | null;
    subtitle_template?: string | null;
  } | null;
  top_overlay_events?: Array<Record<string, any>>;
}

export interface JobDetailResponse {
  success: boolean;
  data: {
    job_id: string;
    youtube_url: string;
    source_type?: string;
    source_label?: string;
    status: string;
    video_duration: number | null;
    style_preset: string | null;
    target_aspect_ratio: string | null;
    error_message: string | null;
    clips_total: number;
    clips_success: number;
    clips_failed: number;
    clips: ClipInfo[];
    files: { raw: string[]; final: string[]; thumbnails: string[] };
    created_at: string | null;
    updated_at: string | null;
  };
}

export interface ClipDetailResponse {
  success: boolean;
  data: {
    job_id: string;
    rank: number;
    score: number | null;
    start: number;
    end: number;
    duration: number;
    hook: string | null;
    reason: string | null;
    words: Array<{ word: string; start: number; end: number; highlight?: boolean }>;
    highlights: any[];
    hook_style: string | null;
    hook_style_config: Record<string, any>;
    subtitle_style_config: Record<string, any>;
    text_emphasis_style_config: Record<string, any>;
    text_emphasis_events: Array<Record<string, any>>;
    watermark_config?: Record<string, any>;
    cta_config?: Record<string, any>;
    reframe_layout?: "single" | "double";
    virality?: {
      score?: number;
      total?: number;
      factors?: string[];
      hook?: number;
      hook_punch?: number;
      retention?: number;
      emotion?: number;
      visual?: number;
      visual_density?: number;
    } | null;
    cta?: { text?: string; type?: string; kind?: string; duration_sec?: number; duration?: number; position?: string } | null;
    retention_hints?: { suggested_cuts?: Array<{ start: number; end: number; reason?: string }> } | null;
    thumb_seek?: number | null;
    object_overlay_events?: Array<Record<string, any>>;
    visual_entities?: Array<Record<string, any>>;
    hyperframes_polish?: {
      template?: string;
      mode?: string;
      events?: number;
      labels?: string[];
      hook_engine?: string;
      subtitle_engine?: string;
      hook_template?: string | null;
      subtitle_template?: string | null;
    } | null;
    top_overlay_events?: Array<Record<string, any>>;
    captions?: { tiktok?: string; instagram?: string; youtube?: string; plain?: string };
    hashtags?: string[];
    hook_alts?: Array<{ text: string; style: string; chars?: number }>;
    file_status: { raw: boolean; final: boolean; thumbnail: boolean };
    urls: { raw: string | null; final: string | null; thumbnail: string | null };
  };
}

export interface ProgressResponse {
  success: boolean;
  data: {
    job_id: string;
    status: string;
    is_terminal: boolean;
    progress: {
      current_step: number;
      total_steps: number;
      percentage: number;
      step_name: string | null;
      step_label: string | null;
    };
    clips: {
      total: number;
      success: number;
      failed: number;
      available: number[];
    };
    active_clip?: {
      rank: number;
      total: number;
      stage: string;
      eta_seconds: number | null;
      timestamp?: string;
    } | null;
    clips_progress?: Record<string, {
      status: string;
      stage: string;
      eta_seconds: number | null;
    }>;
    error: string | null;
    timestamps: { created_at: string | null; updated_at: string | null };
    eta?: null | { remaining_seconds: number; estimated_total_seconds: number; elapsed_seconds: number; sample_count: number; basis: string };
  };
  pipeline_steps: Array<{ number: number; name: string; label: string }>;
}

export const jobs = {
  async list(params?: { status?: string; limit?: number; offset?: number }): Promise<JobListResponse> {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));
    const qs = query.toString();
    return request<JobListResponse>(`/api/jobs${qs ? `?${qs}` : ""}`);
  },

  async get(jobId: string): Promise<JobResponse> {
    return request<JobResponse>(`/api/jobs/${jobId}`);
  },

  async getDetail(jobId: string): Promise<JobDetailResponse> {
    return request<JobDetailResponse>(`/api/jobs/${jobId}/detail`);
  },

  async create(payload: CreateJobPayload): Promise<JobResponse> {
    return request<JobResponse>("/api/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async createUpload(
    file: File,
    payload: UploadJobPayload,
    onProgress?: (percent: number) => void
  ): Promise<JobResponse> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("options_json", JSON.stringify(payload));
    return requestFormWithProgress<JobResponse>("/api/jobs/upload", formData, onProgress);
  },

  async cancel(jobId: string): Promise<{ success: boolean; message: string }> {
    return request(`/api/jobs/${jobId}/cancel`, { method: "POST" });
  },

  async reprocess(jobId: string): Promise<JobResponse> {
    return request<JobResponse>(`/api/jobs/${jobId}/reprocess`, { method: "POST" });
  },

  async delete(jobId: string): Promise<{ success: boolean; message: string }> {
    return request(`/api/jobs/${jobId}`, { method: "DELETE" });
  },

  async getProgress(jobId: string): Promise<ProgressResponse> {
    return request<ProgressResponse>(`/api/jobs/${jobId}/progress/poll`);
  },

  getProgressSSEUrl(jobId: string): string {
    return `${API_BASE}/api/jobs/${jobId}/progress`;
  },

  getClipVideoUrl(jobId: string, rank: number): string {
    return `${API_BASE}/api/jobs/${jobId}/clips/${rank}/video`;
  },

  getClipRawUrl(jobId: string, rank: number): string {
    return `${API_BASE}/api/jobs/${jobId}/clips/${rank}/raw`;
  },

  getClipFinalUrl(jobId: string, rank: number, quality?: "original" | "720" | "480" | "360" | "320"): string {
    const q = quality && quality !== "original" ? `?quality=${quality}` : "";
    return `${API_BASE}/api/jobs/${jobId}/clips/${rank}/final${q}`;
  },

  getDownloadAllUrl(jobId: string): string {
    return `${API_BASE}/api/jobs/${jobId}/download-all`;
  },

  getClipThumbUrl(jobId: string, rank: number): string {
    return `${API_BASE}/api/jobs/${jobId}/clips/${rank}/thumb`;
  },

  async getSourceThumbBlob(jobId: string): Promise<Blob> {
    return requestBlob(`/api/jobs/${jobId}/source-thumb`);
  },

  async getClipDetail(jobId: string, rank: number): Promise<ClipDetailResponse> {
    return request<ClipDetailResponse>(`/api/jobs/${jobId}/clips/${rank}/detail`);
  },

  async renderAITextPreview(jobId: string, rank: number, frame: number, style: Record<string, any>): Promise<{ success: boolean; image: string; frame: number }> {
    return request(`/api/jobs/${jobId}/clips/${rank}/ai-text-preview`, {
      method: "POST",
      body: JSON.stringify({ frame, text_emphasis_style_config: style }),
    });
  },

  async editHook(jobId: string, rank: number, hookText: string): Promise<any> {
    return request(`/api/jobs/${jobId}/clips/${rank}/hook`, {
      method: "PATCH",
      body: JSON.stringify({ hook_text: hookText }),
    });
  },

  async editStyle(jobId: string, rank: number, hookStyle: string, config?: any, subtitleConfig?: any): Promise<any> {
    return request(`/api/jobs/${jobId}/clips/${rank}/style`, {
      method: "PATCH",
      body: JSON.stringify({ hook_style: hookStyle, hook_style_config: config, subtitle_style_config: subtitleConfig }),
    });
  },

  async rerender(jobId: string, rank: number, options?: {
    hook_text?: string;
    hook_style?: string;
    hook_style_config?: Record<string, any>;
  }): Promise<any> {
    return request(`/api/jobs/${jobId}/clips/${rank}/rerender`, {
      method: "POST",
      body: JSON.stringify(options || {}),
    });
  },

  async restyle(jobId: string, rank: number, options: {
    hook_text?: string;
    hook_style?: string;
    hook_style_config?: Record<string, any>;
    subtitle_style_config?: Record<string, any>;
    text_emphasis_style_config?: Record<string, any>;
    watermark_config?: Record<string, any>;
    cta_config?: Record<string, any>;
    subtitle_enabled?: boolean;
    broll_enabled?: boolean;
  }): Promise<any> {
    return request(`/api/jobs/${jobId}/clips/${rank}/restyle`, {
      method: "POST",
      body: JSON.stringify(options),
    });
  },

  async getClipOperation(jobId: string, rank: number): Promise<{ success: boolean; data: null | { status: string; stage: string; percentage: number; error?: string } }> {
    return request(`/api/jobs/${jobId}/clips/${rank}/operation`);
  },
};

// ─── Health API ───────────────────────────────────────────────────────────────

export interface VideoPreview {
  video_id: string;
  title: string;
  channel: string;
  channel_url: string;
  duration: number;
  duration_string: string;
  view_count: number | null;
  like_count: number | null;
  upload_date: string;
  thumbnail: string;
  description: string;
  cache?: {
    has_cache: boolean;
    has_transcript: boolean;
    last_job_id?: string | null;
    last_status?: string;
    clips_total?: number;
    clips_success?: number;
    processed_at?: string;
    message?: string | null;
  };
}

export const preview = {
  async fetchMetadata(url: string): Promise<VideoPreview> {
    const res = await request<{ success: boolean; data: VideoPreview }>(
      `/api/preview?url=${encodeURIComponent(url)}`
    );
    return res.data;
  },
};

export const system = {
  async health(): Promise<{ status: string; version: string; mode: string }> {
    return request("/health");
  },
};

// ─── Presets API ──────────────────────────────────────────────────────────────

export interface Preset {
  id: number;
  name: string;
  slug?: string;
  hook_style: Record<string, any>;
  subtitle_style: Record<string, any>;
  text_emphasis_style: Record<string, any>;
  watermark_style?: Record<string, any>;
  cta_style?: Record<string, any>;
  broll_style?: Record<string, any>;
  autopost_style?: Record<string, any>;
  created_at: string | null;
  owner_email?: string;
  owner_name?: string;
}

export interface PresetsListResponse {
  success: boolean;
  data: Preset[];
  total: number;
}

export const presets = {
  async list(): Promise<Preset[]> {
    const res = await request<PresetsListResponse>("/api/presets");
    return res.data;
  },

  async getBySlug(slugOrId: string): Promise<Preset> {
    const res = await request<{ success: boolean; data: Preset }>(`/api/presets/${slugOrId}`);
    return res.data;
  },

  async create(
    name: string,
    hook_style: Record<string, any>,
    subtitle_style: Record<string, any>,
    text_emphasis_style: Record<string, any> = {},
    watermark_style: Record<string, any> = {},
    cta_style: Record<string, any> = {},
    slug?: string,
    broll_style: Record<string, any> = {},
    autopost_style: Record<string, any> = {}
  ): Promise<{ success: boolean; id: number; slug: string; message: string }> {
    return request("/api/presets", {
      method: "POST",
      body: JSON.stringify({
        name,
        slug: slug || undefined,
        hook_style,
        subtitle_style,
        text_emphasis_style,
        watermark_style,
        cta_style,
        broll_style,
        autopost_style,
      }),
    });
  },

  async remove(id: number): Promise<{ success: boolean; message: string }> {
    return request(`/api/presets/${id}`, { method: "DELETE" });
  },
};

export const presetsApi = presets;

// ─── Social Accounts API ─────────────────────────────────────────────────────

export interface PlatformAccountInfo {
  account_id: string;
  name: string;
  username: string;
  platform: string;
  picture?: string;
  user_id?: number;
}

export interface PlatformsStatusResponse {
  total_accounts: number;
  platforms: Record<
    string,
    {
      connected: boolean;
      count: number;
      accounts: PlatformAccountInfo[];
    }
  >;
  has_any_connected: boolean;
}

export const socialApi = {
  async getPlatformsStatus(): Promise<PlatformsStatusResponse> {
    return request<PlatformsStatusResponse>("/api/social/accounts/platforms-status");
  },
  async getAccounts(): Promise<{ docs: PlatformAccountInfo[] }> {
    return request("/api/social/accounts?page=1&limit=100");
  },
};

// ─── Storage/Cleanup API ─────────────────────────────────────────────────────

export const storage = {
  async clearProcessingData(): Promise<{ success: boolean; message: string }> {
    return request("/api/storage/clear", { method: "POST" });
  },
};

// ─── Analyze-Only API ─────────────────────────────────────────────────────────

export interface AnalyzeClipCandidate {
  rank: number;
  start: number;
  end: number;
  duration: number;
  score: number | null;
  hook: string | null;
  reason: string | null;
  content_type: string | null;
  speaker_energy: string | null;
}

export interface AnalyzeResponse {
  success: boolean;
  job_id: string;
  video_duration: number;
  video_title: string;
  thumbnail: string;
  clips: AnalyzeClipCandidate[];
  creative_direction: Record<string, any> | null;
}

export const analyze = {
  async analyzeOnly(youtubeUrl: string): Promise<AnalyzeResponse> {
    return request<AnalyzeResponse>("/api/jobs/analyze-only", {
      method: "POST",
      body: JSON.stringify({ youtube_url: youtubeUrl }),
    });
  },

  getSourceVideoUrl(jobId: string): string {
    const token = getToken();
    const base = `${API_BASE}/api/jobs/${jobId}/source-video`;
    return token ? `${base}?token=${encodeURIComponent(token)}` : base;
  },
};

export { getToken, setTokens, clearTokens, API_BASE };

// ─── Subtitle Styles API ─────────────────────────────────────────────────────

export interface SubtitleStyleMeta {
  id: string;
  name: string;
  description: string;
  category: string;
}

export const subtitleStyles = {
  async list(): Promise<{ ffmpeg: SubtitleStyleMeta[]; skia: SubtitleStyleMeta[] }> {
    return request("/api/style-presets/subtitle-styles");
  },
  async get(engine: string, styleId: string): Promise<{ data: Record<string, any> }> {
    return request(`/api/style-presets/subtitle-styles/${engine}/${styleId}`);
  },
  async generateWithAI(prompt: string, currentStyle?: any, videoContext?: string): Promise<{
    ok: boolean;
    subtitle_style: Record<string, any>;
    explanation: string;
    highlight_keywords: string[];
  }> {
    return request("/api/settings/subtitle-ai-generate", {
      method: "POST",
      body: JSON.stringify({ prompt, current_style: currentStyle, video_context: videoContext }),
    });
  },
};

// ─── Models Status API ───────────────────────────────────────────────────────

export interface ModelStatus {
  key: string;
  name: string;
  provider: string;
  purpose: string;
  status: "available" | "rate_limited" | "error" | "exhausted";
  last_error: string;
  cooldown_remaining: number;
  requests_today: number;
  requests_limit: number;
  tokens_used: number;
  tokens_limit: number;
  last_success: number | null;
  last_failure: number | null;
}

export const models = {
  async getStatus(): Promise<ModelStatus[]> {
    const res = await request<{ success: boolean; models: ModelStatus[] }>("/api/settings/models");
    return res.models;
  },
};

// ─── System Config API (Dynamic DB-backed RBAC settings) ─────────────────────

export interface SystemConfigItem {
  key: string;
  value: any;
  raw_value?: string;
  category: "ai_llm" | "api_keys" | "render_limits" | "vision_reframe" | "broll_effects" | "storage_cdn" | string;
  data_type: "string" | "int" | "float" | "bool" | "json";
  min_role: "superadmin" | "editor" | "viewer";
  is_secret: boolean;
  description: string;
  updated_at: string | null;
  updated_by: number | null;
}

export const systemConfig = {
  async get(unmask: boolean = false): Promise<{
    success: boolean;
    role: string;
    can_edit_secrets: boolean;
    data: SystemConfigItem[];
  }> {
    return request(`/api/settings/system-config?unmask=${unmask ? "true" : "false"}`);
  },
  async update(settings: Record<string, any>): Promise<{
    success: boolean;
    message: string;
    updated_count: number;
  }> {
    return request("/api/settings/system-config", {
      method: "PUT",
      body: JSON.stringify({ settings }),
    });
  },
  async reset(key?: string): Promise<{
    success: boolean;
    message: string;
  }> {
    return request("/api/settings/system-config/reset", {
      method: "POST",
      body: JSON.stringify({ key }),
    });
  },
};

export interface YouTubeCookiesStatus {
  exists: boolean;
  size_bytes: number;
  line_count: number;
  cookie_count: number;
  last_modified: number | null;
  path: string;
  error?: string;
}

export const youtubeCookies = {
  async getStatus(): Promise<{ success: boolean; data: YouTubeCookiesStatus }> {
    return request<{ success: boolean; data: YouTubeCookiesStatus }>("/api/settings/youtube-cookies");
  },
  async saveCookies(content: string): Promise<{ success: boolean; message: string; data?: Partial<YouTubeCookiesStatus> }> {
    return request("/api/settings/youtube-cookies", {
      method: "POST",
      body: JSON.stringify({ content }),
    });
  },
  async deleteCookies(): Promise<{ success: boolean; message: string }> {
    return request("/api/settings/youtube-cookies", {
      method: "DELETE",
    });
  },
  async testCookies(): Promise<{ success: boolean; message: string; title?: string; formats_count?: number }> {
    return request("/api/settings/youtube-cookies/test", {
      method: "POST",
    });
  },
  async autoExtract(browser: string = "auto"): Promise<{
    success: boolean;
    message: string;
    browser_used?: string;
    data?: YouTubeCookiesStatus;
  }> {
    return request("/api/settings/youtube-cookies/auto-extract", {
      method: "POST",
      body: JSON.stringify({ browser }),
    });
  },
};

// ─── Autopilot API ────────────────────────────────────────────────────────────

export interface AutopilotSettings {
  id?: number;
  user_id?: number;
  enabled: boolean;
  niche_query: string;
  preset_slug: string;
  target_platforms: string;
  target_account_ids: string[];
  schedule_mode: string;
  custom_schedule_time?: string;
  run_time: string;
  min_duration_sec: number;
  max_duration_sec: number;
  max_daily_videos: number;
  last_run_at?: string | null;
  last_job_id?: string | null;
  last_video_url?: string | null;
  last_video_title?: string | null;
  updated_at?: string;
}

export interface AutopilotQuotaInfo {
  today_date: string;
  today_runs: number;
  max_daily_videos: number;
  last_run?: Record<string, any> | null;
}

export interface AutopilotStatusResponse {
  success: boolean;
  data: AutopilotSettings;
  quota: AutopilotQuotaInfo;
  can_run_today: boolean;
  status_message?: string;
}

export const autopilotApi = {
  async getSettings(): Promise<AutopilotStatusResponse> {
    return request<AutopilotStatusResponse>("/api/autopilot/settings");
  },
  async updateSettings(data: Partial<AutopilotSettings>): Promise<AutopilotStatusResponse> {
    return request<AutopilotStatusResponse>("/api/autopilot/settings", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },
  async triggerRun(force: boolean = false): Promise<{
    success: boolean;
    status: string;
    job_id?: string;
    video?: {
      title: string;
      url: string;
      virality_score: number;
      duration_sec: number;
      views: number;
    };
    preset_slug?: string;
    message?: string;
  }> {
    return request("/api/autopilot/run", {
      method: "POST",
      body: JSON.stringify({ force }),
    });
  },
  async getHistory(limit: number = 20): Promise<{ success: boolean; data: any[] }> {
    return request<{ success: boolean; data: any[] }>(`/api/autopilot/history?limit=${limit}`);
  },
};

