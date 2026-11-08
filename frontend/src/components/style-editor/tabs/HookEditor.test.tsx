/**
 * Regression test for the same crash class fixed in SubtitleEditor.test.tsx:
 * a reset helper (resetEngineScopedHookKeys) could leave a numeric field
 * (`motionIntensity`) as `false`/`undefined`, and the Remotion tab renders
 * `style.motionIntensity.toFixed(1)` directly — throwing and crashing the
 * whole React tree instead of just that control.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { HookEditor } from "./HookEditor";
import { DEFAULT_HOOK_STYLE } from "../types";
import type { HookStyle } from "../types";

vi.mock("../utils", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../utils")>();
  return { ...actual, useGoogleFont: () => {} };
});

vi.mock("../preview/NativeHookPreview", () => ({
  NativeHookPreview: () => null,
}));

function renderEditor(style: HookStyle) {
  const onChange = vi.fn();
  render(<HookEditor style={style} onChange={onChange} aspectRatio="9:16" />);
  return onChange;
}

describe("HookEditor - Remotion tab motionIntensity", () => {
  it("renders without crashing when motionIntensity is not a number (false)", () => {
    const style: HookStyle = {
      ...DEFAULT_HOOK_STYLE,
      engine: "remotion",
      motionIntensity: false as unknown as number,
    };
    expect(() => renderEditor(style)).not.toThrow();
    expect(screen.getByText(/Hook Components/i)).toBeTruthy();
  });

  it("renders without crashing when motionIntensity is undefined", () => {
    const style: HookStyle = {
      ...DEFAULT_HOOK_STYLE,
      engine: "remotion",
      motionIntensity: undefined as unknown as number,
    };
    expect(() => renderEditor(style)).not.toThrow();
    expect(screen.getByText(/Hook Components/i)).toBeTruthy();
  });
});
