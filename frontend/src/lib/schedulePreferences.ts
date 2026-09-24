export type ScheduleMode = "now" | "later";
export type BatchScheduleMode = "same" | "ai" | "custom";
export type BatchMusicMode = "ai_distinct" | "single";
export type SchedulePostType = "video" | "reel" | "story";

export interface SchedulePreferences {
  musicVolume: number;
  originalVolume: number;
  selectedGenre: string;
  scheduleMode: ScheduleMode;
  batchScheduleMode: BatchScheduleMode;
  batchMusicMode: BatchMusicMode;
  postType: SchedulePostType;
  dailyScheduleHour: number;
  batchIntervalHours: number;
  captionHashtags: string[];
}

export const DEFAULT_SCHEDULE_PREFERENCES: SchedulePreferences = {
  musicVolume: 25,
  originalVolume: 100,
  selectedGenre: "RECOMMENDED",
  scheduleMode: "now",
  batchScheduleMode: "same",
  batchMusicMode: "ai_distinct",
  postType: "video",
  dailyScheduleHour: 19,
  batchIntervalHours: 2,
  captionHashtags: ["#fyp", "#viral", "#trending", "#reels", "#shorts", "#autocliper"],
};

const STORAGE_PREFIX = "autocliper.schedule-preferences.v1.user.";
const MAX_HASHTAGS = 20;
const MAX_TAG_LENGTH = 64;
const ALLOWED_GENRES = new Set([
  "RECOMMENDED", "VIRAL_TODAY", "POP", "EDM", "ROCK", "FOLK", "JAZZ",
]);

function storageKey(user: { id?: number | string } | null | undefined): string | null {
  const id = user?.id;
  if (id === undefined || id === null || String(id).trim() === "") return null;
  return `${STORAGE_PREFIX}${encodeURIComponent(String(id))}`;
}

function clampNumber(value: unknown, fallback: number, min: number, max: number): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? Math.min(max, Math.max(min, Math.round(parsed))) : fallback;
}

function parseHashtags(value: unknown): string[] {
  if (!Array.isArray(value)) return [...DEFAULT_SCHEDULE_PREFERENCES.captionHashtags];
  const valid = value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim().replace(/^#+/, ""))
    .filter((item) => /^[\p{L}\p{N}_]{1,63}$/u.test(item))
    .slice(0, MAX_HASHTAGS)
    .map((item) => `#${item}`);
  return valid.length > 0 || value.length === 0 ? valid : [...DEFAULT_SCHEDULE_PREFERENCES.captionHashtags];
}

export function normalizeSchedulePreferences(value: unknown): SchedulePreferences {
  const input = value && typeof value === "object" ? value as Partial<SchedulePreferences> : {};
  const genre = typeof input.selectedGenre === "string" && ALLOWED_GENRES.has(input.selectedGenre)
    ? input.selectedGenre
    : DEFAULT_SCHEDULE_PREFERENCES.selectedGenre;
  const scheduleMode: ScheduleMode = input.scheduleMode === "later" ? "later" : "now";
  const batchScheduleMode: BatchScheduleMode = ["same", "ai", "custom"].includes(String(input.batchScheduleMode))
    ? input.batchScheduleMode as BatchScheduleMode
    : DEFAULT_SCHEDULE_PREFERENCES.batchScheduleMode;
  const batchMusicMode: BatchMusicMode = input.batchMusicMode === "single" ? "single" : "ai_distinct";
  const postType: SchedulePostType = ["video", "reel", "story"].includes(String(input.postType))
    ? input.postType as SchedulePostType
    : DEFAULT_SCHEDULE_PREFERENCES.postType;

  return {
    musicVolume: clampNumber(input.musicVolume, DEFAULT_SCHEDULE_PREFERENCES.musicVolume, 0, 100),
    originalVolume: clampNumber(input.originalVolume, DEFAULT_SCHEDULE_PREFERENCES.originalVolume, 0, 100),
    selectedGenre: genre,
    scheduleMode,
    batchScheduleMode,
    batchMusicMode,
    postType,
    dailyScheduleHour: clampNumber(input.dailyScheduleHour, DEFAULT_SCHEDULE_PREFERENCES.dailyScheduleHour, 0, 23),
    batchIntervalHours: clampNumber(input.batchIntervalHours, DEFAULT_SCHEDULE_PREFERENCES.batchIntervalHours, 1, 24),
    captionHashtags: parseHashtags(input.captionHashtags),
  };
}

export function loadSchedulePreferences(user: { id?: number | string } | null | undefined): SchedulePreferences {
  const key = storageKey(user);
  if (!key || typeof localStorage === "undefined") return { ...DEFAULT_SCHEDULE_PREFERENCES, captionHashtags: [...DEFAULT_SCHEDULE_PREFERENCES.captionHashtags] };
  try {
    const raw = localStorage.getItem(key);
    return raw ? normalizeSchedulePreferences(JSON.parse(raw)) : { ...DEFAULT_SCHEDULE_PREFERENCES, captionHashtags: [...DEFAULT_SCHEDULE_PREFERENCES.captionHashtags] };
  } catch {
    return { ...DEFAULT_SCHEDULE_PREFERENCES, captionHashtags: [...DEFAULT_SCHEDULE_PREFERENCES.captionHashtags] };
  }
}

export function saveSchedulePreferences(
  user: { id?: number | string } | null | undefined,
  preferences: SchedulePreferences,
): void {
  const key = storageKey(user);
  if (!key || typeof localStorage === "undefined") return;
  localStorage.setItem(key, JSON.stringify(normalizeSchedulePreferences(preferences)));
}

export function resetSchedulePreferences(user: { id?: number | string } | null | undefined): void {
  const key = storageKey(user);
  if (key && typeof localStorage !== "undefined") localStorage.removeItem(key);
}
