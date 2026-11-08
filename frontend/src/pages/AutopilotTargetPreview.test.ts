/**
 * Regression tests for computeAutopilotTargetPreview() — the "Target Hari
 * Ini" preview shown on settings/hermes/autopilot. A user reported that the
 * video shown as today's target was completely different from the video
 * autopilot actually processed. Root cause: this client-side mirror of the
 * backend's pick_candidate_from_channel_or_playlist() omitted the
 * min_duration_sec/max_duration_sec filter entirely, so it could pick a
 * video the backend would have skipped (or vice versa) purely for duration
 * reasons. (A second contributing cause — the preview's video pool being
 * shallower than the backend's own fetch depth for "all_playlist" — is
 * covered on the backend side by
 * test_all_playlist_strategy_fetches_deeper_pool_than_latest_strategies in
 * backend/tests/test_autopilot.py.)
 */
import { describe, it, expect } from "vitest";
import { computeAutopilotTargetPreview } from "./Settings";
import type { AutopilotVideoItem, AutopilotSettings } from "@/lib/api";

function video(overrides: Partial<AutopilotVideoItem>): AutopilotVideoItem {
  return {
    id: "vid", title: "Video", url: "https://www.youtube.com/watch?v=vid",
    duration_sec: 1200, duration_formatted: "20:00", thumbnail: "", is_processed: false,
    index: 0,
    ...overrides,
  } as AutopilotVideoItem;
}

function settings(overrides: Partial<AutopilotSettings>): AutopilotSettings {
  return {
    video_selection_strategy: "latest_2",
    min_duration_sec: 480,
    max_duration_sec: 3600,
    ...overrides,
  } as AutopilotSettings;
}

describe("computeAutopilotTargetPreview", () => {
  it("skips a video outside the configured duration range, matching the backend's duration_ok filter", () => {
    const videos = [
      video({ id: "too_short", duration_sec: 30 }), // below min_duration_sec
      video({ id: "in_range", duration_sec: 900 }),
    ];
    const result = computeAutopilotTargetPreview(videos, settings({ video_selection_strategy: "latest_1" }));
    expect(result?.video.id).toBe("in_range");
  });

  it("falls back to the unfiltered pool when duration filtering would eliminate every candidate", () => {
    const videos = [video({ id: "too_short", duration_sec: 30 })];
    const result = computeAutopilotTargetPreview(videos, settings({ video_selection_strategy: "latest_1" }));
    expect(result?.video.id).toBe("too_short");
  });

  it("treats an unknown duration (<=0) as always eligible", () => {
    const videos = [video({ id: "unknown_dur", duration_sec: 0 })];
    const result = computeAutopilotTargetPreview(videos, settings({ video_selection_strategy: "latest_1" }));
    expect(result?.video.id).toBe("unknown_dur");
  });

  it("manual target bypasses duration filtering and every strategy, same as the backend", () => {
    const videos = [
      video({ id: "manual_pick", duration_sec: 30 }),
      video({ id: "other", duration_sec: 900 }),
    ];
    const result = computeAutopilotTargetPreview(
      videos,
      settings({ manual_target_video_id: "manual_pick", video_selection_strategy: "all_playlist" } as Partial<AutopilotSettings>)
    );
    expect(result?.isManual).toBe(true);
    expect(result?.video.id).toBe("manual_pick");
  });

  it("all_playlist picks the oldest unprocessed video among eligible candidates", () => {
    const videos = [
      video({ id: "newest", is_processed: false }),
      video({ id: "middle", is_processed: true }),
      video({ id: "oldest", is_processed: false }),
    ];
    const result = computeAutopilotTargetPreview(videos, settings({ video_selection_strategy: "all_playlist" }));
    expect(result?.video.id).toBe("oldest");
  });

  it("returns null when there are no videos", () => {
    expect(computeAutopilotTargetPreview([], settings({}))).toBeNull();
    expect(computeAutopilotTargetPreview(undefined, settings({}))).toBeNull();
  });
});
