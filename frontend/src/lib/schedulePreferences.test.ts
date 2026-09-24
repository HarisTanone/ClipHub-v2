import { beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULT_SCHEDULE_PREFERENCES,
  loadSchedulePreferences,
  resetSchedulePreferences,
  saveSchedulePreferences,
  type SchedulePreferences,
} from "./schedulePreferences";

const user = { id: 42 };

beforeEach(() => localStorage.clear());

describe("schedule preferences", () => {
  it("returns safe defaults when a user has no saved preferences", () => {
    expect(loadSchedulePreferences(user)).toEqual(DEFAULT_SCHEDULE_PREFERENCES);
  });

  it("persists preferences separately for each user", () => {
    const saved: SchedulePreferences = {
      ...DEFAULT_SCHEDULE_PREFERENCES,
      musicVolume: 42,
      originalVolume: 80,
      selectedGenre: "POP",
      scheduleMode: "later",
      batchScheduleMode: "custom",
      batchMusicMode: "single",
      postType: "reel",
      dailyScheduleHour: 17,
      batchIntervalHours: 3,
      captionHashtags: ["#brand", "#campaign"],
    };
    saveSchedulePreferences(user, saved);
    saveSchedulePreferences({ id: 7 }, { ...saved, musicVolume: 11 });

    expect(loadSchedulePreferences(user)).toEqual(saved);
    expect(loadSchedulePreferences({ id: 7 }).musicVolume).toBe(11);
  });

  it("clamps unsafe numeric values and ignores invalid enums from storage", () => {
    localStorage.setItem("autocliper.schedule-preferences.v1.user.42", JSON.stringify({
      musicVolume: 250,
      originalVolume: -1,
      selectedGenre: "HACKED",
      scheduleMode: "instant",
      dailyScheduleHour: 44,
      batchIntervalHours: 0,
      captionHashtags: ["ok", ""],
    }));

    expect(loadSchedulePreferences(user)).toEqual({
      ...DEFAULT_SCHEDULE_PREFERENCES,
      musicVolume: 100,
      originalVolume: 0,
      dailyScheduleHour: 23,
      batchIntervalHours: 1,
      captionHashtags: ["#ok"],
    });
  });

  it("resets only the selected user's preferences", () => {
    saveSchedulePreferences(user, { ...DEFAULT_SCHEDULE_PREFERENCES, musicVolume: 10 });
    saveSchedulePreferences({ id: 7 }, { ...DEFAULT_SCHEDULE_PREFERENCES, musicVolume: 20 });

    resetSchedulePreferences(user);

    expect(loadSchedulePreferences(user)).toEqual(DEFAULT_SCHEDULE_PREFERENCES);
    expect(loadSchedulePreferences({ id: 7 }).musicVolume).toBe(20);
  });
});
