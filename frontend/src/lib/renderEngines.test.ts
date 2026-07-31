import { describe, expect, it } from "vitest";

import { HF_HOOK_STYLES, HF_SUBTITLE_STYLES } from "./renderEngines";

describe("HyperFrames fixed style catalogue", () => {
  it("uses a separate v2 namespace with eight unique looks", () => {
    const styles = [...HF_HOOK_STYLES, ...HF_SUBTITLE_STYLES];
    expect(styles).toHaveLength(8);
    expect(new Set(styles.map((style) => style.id)).size).toBe(8);
    expect(styles.every((style) => style.id.endsWith("_v2"))).toBe(true);
  });
});
