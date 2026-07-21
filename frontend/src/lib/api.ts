const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

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
  // v3.1: Default motion-graphic style for B-roll events (rendered in Remotion).
  // Empty/undefined = AI picks per-suggestion.
  broll_motion_style?: string;
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
  processing_mode?: "analyze" | "direct";
  custom_hook?: string;
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
    reframe_layout?: "single" | "double";
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

  async createUpload(file: File, payload: UploadJobPayload): Promise<JobResponse> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("options_json", JSON.stringify(payload));
    return requestForm<JobResponse>("/api/jobs/upload", formData);
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
    const base = `${API_BASE}/api/jobs/${jobId}/clips/${rank}/final`;
    return quality && quality !== "original" ? `${base}?quality=${quality}` : base;
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
  hook_style: Record<string, any>;
  subtitle_style: Record<string, any>;
  text_emphasis_style: Record<string, any>;
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

  async create(name: string, hook_style: Record<string, any>, subtitle_style: Record<string, any>, text_emphasis_style: Record<string, any> = {}): Promise<{ success: boolean; id: number; message: string }> {
    return request("/api/presets", {
      method: "POST",
      body: JSON.stringify({ name, hook_style, subtitle_style, text_emphasis_style }),
    });
  },

  async remove(id: number): Promise<{ success: boolean; message: string }> {
    return request(`/api/presets/${id}`, { method: "DELETE" });
  },
};

// ─── Storage/Cleanup API ─────────────────────────────────────────────────────

export const storage = {
  async clearProcessingData(): Promise<{ success: boolean; message: string }> {
    return request("/api/storage/clear", { method: "POST" });
  },
};

export { getToken, setTokens, clearTokens, API_BASE };

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
