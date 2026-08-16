import { describe, expect, it } from "vitest";

import {
  ENGINE_NOTES,
  HF_HOOK_STYLES,
  HF_SUBTITLE_STYLES,
  FFMPEG_HOOK_PRESETS,
  FFMPEG_SUBTITLE_PRESETS,
  SKIA_HOOK_PRESETS,
  SKIA_SUBTITLE_PRESETS,
  resolveEngine,
} from "./renderEngines";

describe("Render engines catalogue & permissions", () => {
  it("defines permissions for all 4 engines", () => {
    expect(ENGINE_NOTES.remotion.superuserOnly).toBe(true);
    expect(ENGINE_NOTES.hyperframes.superuserOnly).toBe(true);
    expect(ENGINE_NOTES.ffmpeg.superuserOnly).toBe(false);
    expect(ENGINE_NOTES.skia.superuserOnly).toBe(false);
  });

  it("resolves engine names properly", () => {
    expect(resolveEngine("remotion")).toBe("remotion");
    expect(resolveEngine("hyperframes")).toBe("hyperframes");
    expect(resolveEngine("hf")).toBe("hyperframes");
    expect(resolveEngine("ffmpeg")).toBe("ffmpeg");
    expect(resolveEngine("drawtext")).toBe("ffmpeg");
    expect(resolveEngine("skia")).toBe("skia");
    expect(resolveEngine("canvaskit")).toBe("skia");
    expect(resolveEngine("unknown")).toBe("remotion");
  });

  it("HyperFrames catalogue has 8 v2 presets", () => {
    const styles = [...HF_HOOK_STYLES, ...HF_SUBTITLE_STYLES];
    expect(styles).toHaveLength(8);
    expect(new Set(styles.map((style) => style.id)).size).toBe(8);
    expect(styles.every((style) => style.id.endsWith("_v2"))).toBe(true);
  });

  it("FFmpeg presets catalogue is complete", () => {
    expect(FFMPEG_HOOK_PRESETS.length).toBeGreaterThanOrEqual(10);
    expect(FFMPEG_SUBTITLE_PRESETS.length).toBe(10);
  });

  it("Skia GPU presets catalogue is complete", () => {
    expect(SKIA_HOOK_PRESETS.length).toBeGreaterThanOrEqual(8);
    expect(SKIA_SUBTITLE_PRESETS.length).toBe(10);
  });

  it("enforces subtitle engine permission matrix (regular user: ffmpeg, skia; superuser: all 4)", () => {
    const allEngines = ["remotion", "hyperframes", "ffmpeg", "skia"] as const;
    const superuserSubtitleEngines = allEngines.filter(
      (eng) => true // superuser has access to all engines
    );
    const regularUserSubtitleEngines = allEngines.filter(
      (eng) => !ENGINE_NOTES[eng].superuserOnly
    );

    expect(superuserSubtitleEngines).toEqual(["remotion", "hyperframes", "ffmpeg", "skia"]);
    expect(regularUserSubtitleEngines).toEqual(["ffmpeg", "skia"]);
  });

  it("ensures each engine has distinct and independent style presets", () => {
    const ffmpegHookIds = new Set(FFMPEG_HOOK_PRESETS.map(p => p.id));
    const skiaHookIds = new Set(SKIA_HOOK_PRESETS.map(p => p.id));
    const hfHookIds = new Set(HF_HOOK_STYLES.map(p => p.id));

    // Preset IDs should not collide across distinct engines
    for (const id of skiaHookIds) {
      expect(ffmpegHookIds.has(id)).toBe(false);
      expect(hfHookIds.has(id)).toBe(false);
    }
  });
});
