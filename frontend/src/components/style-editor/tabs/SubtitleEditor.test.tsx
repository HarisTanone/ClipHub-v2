/**
 * Regression test for a reported crash: on /jobs/new, opening the Subtitle
 * tab and clicking the "Skia" engine sub-tab produced a black/blank screen.
 *
 * Root cause: resetEngineScopedSubtitleKeys() (fired on every engine
 * switch) reset `highlightScale` to `false`/`undefined`, but the Skia tab
 * renders `style.highlightScale.toFixed(1)` directly — calling `.toFixed`
 * on a non-number threw an uncaught TypeError during render, which crashes
 * the whole React tree (hence the black screen) instead of just that tab.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SubtitleEditor } from "./SubtitleEditor";
import { DEFAULT_SUBTITLE_STYLE } from "../types";
import type { SubtitleStyle } from "../types";

vi.mock("../utils", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../utils")>();
  return { ...actual, useGoogleFont: () => {} };
});

function renderEditor(style: SubtitleStyle) {
  const onChange = vi.fn();
  render(<SubtitleEditor style={style} onChange={onChange} />);
  return onChange;
}

describe("SubtitleEditor - Skia engine tab", () => {
  it("renders Skia tab content without crashing when highlightScale is not a number (false)", () => {
    // Exact state produced by the (buggy) engine-switch reset before the fix.
    const style: SubtitleStyle = {
      ...DEFAULT_SUBTITLE_STYLE,
      engine: "skia",
      highlightScale: false as unknown as number,
    };
    expect(() => renderEditor(style)).not.toThrow();
    expect(screen.getByText(/Skia Subtitle Presets/i)).toBeTruthy();
  });

  it("renders Skia tab content without crashing when highlightScale is undefined", () => {
    const style: SubtitleStyle = {
      ...DEFAULT_SUBTITLE_STYLE,
      engine: "skia",
      highlightScale: undefined as unknown as number,
    };
    expect(() => renderEditor(style)).not.toThrow();
    expect(screen.getByText(/Skia Render Engine/i)).toBeTruthy();
  });

  it("renders normally for the FFmpeg tab (sanity baseline)", () => {
    const style: SubtitleStyle = { ...DEFAULT_SUBTITLE_STYLE, engine: "ffmpeg" };
    expect(() => renderEditor(style)).not.toThrow();
    expect(screen.getByText(/FFmpeg Subtitle Presets/i)).toBeTruthy();
  });
});
