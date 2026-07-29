import { describe, expect, it } from "vitest";
import { isFrameInTextEmphasis } from "./AITextLayer";

describe("AITextLayer timeline contract", () => {
  const events = [
    { id: "one", start: 4, end: 6, text: "IDE BESAR", effect: "depth_cutout" as const },
    { id: "two", start: 12, end: 13.5, text: "42 PERSEN", effect: "hero_punch" as const },
  ];

  it("hides subtitles only while an emphasis event is active", () => {
    expect(isFrameInTextEmphasis(119, 30, events)).toBe(false);
    expect(isFrameInTextEmphasis(120, 30, events)).toBe(true);
    expect(isFrameInTextEmphasis(179, 30, events)).toBe(true);
    expect(isFrameInTextEmphasis(180, 30, events)).toBe(false);
    expect(isFrameInTextEmphasis(360, 30, events)).toBe(true);
    expect(isFrameInTextEmphasis(405, 30, events)).toBe(false);
  });

  it("ignores events beyond the hard maximum of two", () => {
    const extra = [...events, { id: "three", start: 20, end: 22, text: "NO", effect: "side_rail" as const }];
    expect(isFrameInTextEmphasis(20 * 30, 30, extra)).toBe(false);
  });

  it("accepts legacy effect names on the event contract", () => {
    const legacy = [{ id: "old", start: 1, end: 2, text: "X", effect: "spotlight" as const }];
    expect(isFrameInTextEmphasis(30, 30, legacy)).toBe(true);
  });
});
