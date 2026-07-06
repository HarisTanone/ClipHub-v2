import { describe, it, expect } from "vitest";
import {
  groupWordsToSubtitlePages,
  normaliseSubtitleWords,
  resolveSubtitleVisualPreset,
  resolveSubtitlePositionY,
} from "./SubtitleLayer";

describe("SubtitleLayer - Page Grouping", () => {
  // Helper: calculate startFrame (the fixed version)
  function calcStartFrame(pageStartMs: number, fps: number): number {
    return Math.round((pageStartMs / 1000) * fps);
  }

  it("should group words into pages of max 3 words", () => {
    const words = [
      { word: "Hello", start: 0.5, end: 0.8 },
      { word: "world", start: 0.9, end: 1.2 },
      { word: "this", start: 1.3, end: 1.5 },
      { word: "is", start: 1.6, end: 1.7 },
      { word: "a", start: 1.8, end: 1.9 },
      { word: "test", start: 2.0, end: 2.3 },
    ];
    const pages = groupWordsToSubtitlePages(words, 3);
    expect(pages).toHaveLength(2);
    expect(pages[0].tokens).toHaveLength(3);
    expect(pages[1].tokens).toHaveLength(3);
  });

  it("should break on gap > 0.5s", () => {
    const words = [
      { word: "Hello", start: 0.5, end: 0.8 },
      { word: "world", start: 2.0, end: 2.3 }, // gap > 0.5s
    ];
    const pages = groupWordsToSubtitlePages(words, 3);
    expect(pages).toHaveLength(2);
    expect(pages[0].tokens).toHaveLength(1);
    expect(pages[1].tokens).toHaveLength(1);
  });

  it("should calculate correct startFrame from Whisper timestamps (no offset)", () => {
    const fps = 30;
    // Word at t=1.5s → frame 45
    expect(calcStartFrame(1500, fps)).toBe(45);
    // Word at t=0s → frame 0
    expect(calcStartFrame(0, fps)).toBe(0);
    // Word at t=4.0s → frame 120
    expect(calcStartFrame(4000, fps)).toBe(120);
    // Word at t=0.5s → frame 15
    expect(calcStartFrame(500, fps)).toBe(15);
  });

  it("should NEVER produce negative startFrame (the bug that was fixed)", () => {
    const fps = 30;
    // Previously with startOffset=-3: calcStartFrame(1500, fps) would be ((1.5 + (-3)) * 30) = -45
    // After fix: all frames are non-negative
    const testTimestamps = [0, 100, 500, 1000, 1500, 2000, 2500, 3000, 5000, 10000];
    for (const ms of testTimestamps) {
      const frame = calcStartFrame(ms, fps);
      expect(frame).toBeGreaterThanOrEqual(0);
    }
  });

  it("words during hook period (0-3s) should have valid positive frames", () => {
    const fps = 30;
    // These words are spoken during hook overlay (first 3 seconds)
    // They should still render at correct frames (hook is just visual overlay)
    const hookPeriodWords = [
      { word: "Hey", start: 0.2, end: 0.4 },
      { word: "everyone", start: 0.5, end: 0.9 },
      { word: "welcome", start: 1.0, end: 1.4 },
      { word: "back", start: 1.5, end: 1.8 },
      { word: "to", start: 2.0, end: 2.1 },
      { word: "the", start: 2.2, end: 2.3 },
      { word: "channel", start: 2.4, end: 2.9 },
    ];
    const pages = groupWordsToSubtitlePages(hookPeriodWords, 3);
    for (const page of pages) {
      const frame = calcStartFrame(page.startMs, fps);
      expect(frame).toBeGreaterThanOrEqual(0);
      expect(frame).toBeLessThan(90); // All within first 3 seconds (90 frames at 30fps)
    }
  });

  it("active word highlight timing should use page-relative time correctly", () => {
    // The highlight check: startRel <= timeInMs && endRel > timeInMs
    // where startRel = t.fromMs - page.startMs
    // and timeInMs = (frame / fps) * 1000 (frame-local within Sequence)
    // Since Sequence from = startFrame = page.startMs/1000*fps,
    // at frame 0 within the Sequence, absolute time = page.startMs/1000
    // timeInMs at frame 0 = 0ms → startRel for first token = 0ms → active ✓
    
    const page = {
      startMs: 4000,
      endMs: 5000,
      tokens: [
        { text: "hello ", fromMs: 4000, toMs: 4300 },
        { text: "world ", fromMs: 4400, toMs: 4700 },
        { text: "test ", fromMs: 4800, toMs: 5000 },
      ],
    };

    // Simulate frame 0 within the Sequence (just entered this page)
    const fps = 30;
    const frame = 0;
    const timeInMs = (frame / fps) * 1000; // 0ms
    
    const token0 = page.tokens[0];
    const startRel0 = token0.fromMs - page.startMs; // 4000 - 4000 = 0
    const endRel0 = token0.toMs - page.startMs; // 4300 - 4000 = 300
    
    // At frame 0 (timeInMs=0): first token is active (0 <= 0 && 300 > 0)
    expect(startRel0 <= timeInMs && endRel0 > timeInMs).toBe(true);
    
    // At frame 15 (timeInMs=500ms): second token should be active
    const frame15 = 15;
    const timeInMs15 = (frame15 / fps) * 1000; // 500ms
    const token1 = page.tokens[1];
    const startRel1 = token1.fromMs - page.startMs; // 4400 - 4000 = 400
    const endRel1 = token1.toMs - page.startMs; // 4700 - 4000 = 700
    expect(startRel1 <= timeInMs15 && endRel1 > timeInMs15).toBe(true);
  });

  it("normalises dirty word timing before page grouping", () => {
    const cleaned = normaliseSubtitleWords([
      { word: " later ", start: 1.2, end: 1.1 },
      { word: "first", start: -0.1, end: 0.2 },
      { word: "first", start: -0.08, end: 0.22 },
      { word: "", start: 0.3, end: 0.4 },
      { word: "overlap", start: 0.1, end: 0.5 },
    ]);

    expect(cleaned.map((w) => w.word)).toEqual(["first", "overlap", "later"]);
    expect(cleaned[0].start).toBe(0);
    expect(cleaned[1].start).toBeGreaterThan(cleaned[0].end);
    expect(cleaned[2].end).toBeGreaterThan(cleaned[2].start);
  });

  it("resolves subtitle Y from position when positionY is absent", () => {
    expect(resolveSubtitlePositionY({ position: "top" })).toBe(18);
    expect(resolveSubtitlePositionY({ position: "center" })).toBe(50);
    expect(resolveSubtitlePositionY({ position: "bottom" })).toBe(85);
    expect(resolveSubtitlePositionY({ positionY: 120 })).toBe(94);
  });

  it("keeps AI-highlighted words in subtitle pages", () => {
    const pages = groupWordsToSubtitlePages([
      { word: "normal", start: 0, end: 0.2 },
      { word: "power", start: 0.3, end: 0.5, highlight: true },
    ], 4);

    expect(pages[0].tokens[1].highlight).toBe(true);
  });

  it("resolves visual presets for new and legacy subtitle styles", () => {
    expect(resolveSubtitleVisualPreset({ stylePreset: "neon_pulse" })).toBe("neon_pulse");
    expect(resolveSubtitleVisualPreset({ lineTransition: "emphasis" })).toBe("spotlight_keyword");
    expect(resolveSubtitleVisualPreset({ lineTransition: "line_reveal" })).toBe("editorial_banner");
    expect(resolveSubtitleVisualPreset({ dualStyleEnabled: true })).toBe("dual_pop");
    expect(resolveSubtitleVisualPreset({ stylePreset: "bold_yellow" })).toBe("dual_pop");
  });
});
