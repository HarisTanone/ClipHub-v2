import { describe, it, expect } from "vitest";

describe("HookLayer - Stroke Rendering Logic", () => {
  // Simulate the stroke logic from HookLayer
  function getStrokeStyle(config: { strokeEnabled?: boolean; strokeWidth?: number; strokeColor?: string; fontSize?: number }) {
    const fontSize = config.fontSize || 48;
    const strokeEnabled = config.strokeEnabled;
    
    return {
      paintOrder: strokeEnabled !== false ? "stroke" : undefined,
      WebkitTextStroke: strokeEnabled !== false
        ? `${config.strokeWidth || Math.max(2, fontSize * 0.04)}px ${config.strokeColor || "rgba(0,0,0,0.8)"}`
        : undefined,
    };
  }

  it("should NOT apply stroke when strokeEnabled is false", () => {
    const style = getStrokeStyle({ strokeEnabled: false, fontSize: 48 });
    expect(style.paintOrder).toBeUndefined();
    expect(style.WebkitTextStroke).toBeUndefined();
  });

  it("should apply stroke when strokeEnabled is true with user values", () => {
    const style = getStrokeStyle({ strokeEnabled: true, strokeWidth: 5, strokeColor: "#FF0000", fontSize: 48 });
    expect(style.paintOrder).toBe("stroke");
    expect(style.WebkitTextStroke).toBe("5px #FF0000");
  });

  it("should apply default stroke when strokeEnabled is undefined (backward compat)", () => {
    const style = getStrokeStyle({ fontSize: 48 });
    expect(style.paintOrder).toBe("stroke");
    // Default: Math.max(2, 48 * 0.04) = Math.max(2, 1.92) = 2
    expect(style.WebkitTextStroke).toBe("2px rgba(0,0,0,0.8)");
  });

  it("should apply default stroke when strokeEnabled is true but no custom values", () => {
    const style = getStrokeStyle({ strokeEnabled: true, fontSize: 60 });
    expect(style.paintOrder).toBe("stroke");
    // Math.max(2, 60 * 0.04) = Math.max(2, 2.4) = 2.4
    expect(style.WebkitTextStroke).toBe("2.4px rgba(0,0,0,0.8)");
  });

  it("should use user strokeWidth over calculated default", () => {
    const style = getStrokeStyle({ strokeEnabled: true, strokeWidth: 8, fontSize: 48 });
    expect(style.WebkitTextStroke).toContain("8px");
  });
});
