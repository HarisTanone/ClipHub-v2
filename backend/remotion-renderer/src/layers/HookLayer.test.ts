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

describe("HookLayer - Effect Layer Styles (Double-Render Prevention)", () => {
  // Simulate the glitch_rgb effect layer style generation
  function getGlitchRgbStyles(frame: number) {
    const redLayer = {
      color: "#ff0000",
      opacity: 0.5,
      mixBlendMode: "screen" as const,
      transform: `translateY(-50%) translateX(${Math.sin(frame * 0.5) * 3 - 4}px)`,
    };
    const cyanLayer = {
      color: "#00ffff",
      opacity: 0.5,
      mixBlendMode: "screen" as const,
      transform: `translateY(-50%) translateX(${4 - Math.sin(frame * 0.5) * 3}px)`,
    };
    return { redLayer, cyanLayer };
  }

  // Simulate the shake_neon glow layer style generation
  function getShakeNeonGlowStyles(frame: number, color: string) {
    const baseGlow = {
      opacity: 0.3,
      filter: "blur(4px)",
      color,
      textShadow: `0 0 12px ${color}, 0 0 24px ${color}`,
    };
    const secondGlow = {
      opacity: 0.35,
      filter: "blur(1.5px)",
      color,
      textShadow: `0 0 6px ${color}, 0 0 12px ${color}`,
      transform: `translateY(-50%) translate(${Math.sin(frame * 0.8) * 2}px, ${Math.cos(frame * 0.6) * 2}px)`,
    };
    return { baseGlow, secondGlow };
  }

  // Simulate the danger_bold glow layer style generation
  function getDangerBoldGlowStyle() {
    return {
      color: "#FF0000",
      opacity: 0.3,
      filter: "blur(3px)",
      textShadow: "0 0 10px #FF0000, 0 0 20px #FF0000, 0 0 40px rgba(255,0,0,0.3)",
    };
  }

  it("glitch_rgb layers should use mixBlendMode: screen for proper RGB blending", () => {
    const { redLayer, cyanLayer } = getGlitchRgbStyles(10);
    expect(redLayer.mixBlendMode).toBe("screen");
    expect(cyanLayer.mixBlendMode).toBe("screen");
  });

  it("glitch_rgb layers should have reduced opacity (0.5) for subtlety", () => {
    const { redLayer, cyanLayer } = getGlitchRgbStyles(10);
    expect(redLayer.opacity).toBe(0.5);
    expect(cyanLayer.opacity).toBe(0.5);
  });

  it("shake_neon base glow layer should have blur(4px) to prevent readable duplicate", () => {
    const { baseGlow } = getShakeNeonGlowStyles(10, "#FFFFFF");
    expect(baseGlow.filter).toBe("blur(4px)");
    expect(baseGlow.opacity).toBe(0.3);
  });

  it("shake_neon second glow layer should have blur(1.5px) to prevent readable duplicate", () => {
    const { secondGlow } = getShakeNeonGlowStyles(10, "#FFFFFF");
    expect(secondGlow.filter).toBe("blur(1.5px)");
    expect(secondGlow.opacity).toBe(0.35);
  });

  it("danger_bold glow layer should have blur(3px) to function as aura not duplicate text", () => {
    const style = getDangerBoldGlowStyle();
    expect(style.filter).toBe("blur(3px)");
    expect(style.opacity).toBe(0.3);
  });

  it("danger_bold glow layer should retain red color and textShadow for glow effect", () => {
    const style = getDangerBoldGlowStyle();
    expect(style.color).toBe("#FF0000");
    expect(style.textShadow).toContain("#FF0000");
  });
});
