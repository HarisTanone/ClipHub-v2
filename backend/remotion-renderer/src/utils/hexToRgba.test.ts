import { describe, it, expect } from "vitest";
import { hexToRgba } from "./hexToRgba";

describe("hexToRgba", () => {
  it("should convert 6-char hex correctly", () => {
    expect(hexToRgba("#FF0000", 0.5)).toBe("rgba(255, 0, 0, 0.5)");
  });

  it("should convert 3-char hex correctly", () => {
    expect(hexToRgba("#F00", 0.5)).toBe("rgba(255, 0, 0, 0.5)");
  });

  it("should strip alpha from 8-char hex and use provided opacity", () => {
    expect(hexToRgba("#FF000080", 0.7)).toBe("rgba(255, 0, 0, 0.7)");
  });

  it("should fallback for invalid hex", () => {
    expect(hexToRgba("#ZZZZZZ", 0.5)).toBe("rgba(0, 0, 0, 0.5)");
    expect(hexToRgba("invalid", 0.3)).toBe("rgba(0, 0, 0, 0.3)");
  });

  it("should handle opacity 0", () => {
    expect(hexToRgba("#FF0000", 0)).toBe("rgba(255, 0, 0, 0)");
  });

  it("should handle opacity 1", () => {
    expect(hexToRgba("#FF0000", 1)).toBe("rgba(255, 0, 0, 1)");
  });

  it("should work without # prefix", () => {
    expect(hexToRgba("FF0000", 0.5)).toBe("rgba(255, 0, 0, 0.5)");
  });

  it("should handle black", () => {
    expect(hexToRgba("#000000", 0.4)).toBe("rgba(0, 0, 0, 0.4)");
  });

  it("should handle white", () => {
    expect(hexToRgba("#FFFFFF", 1)).toBe("rgba(255, 255, 255, 1)");
  });
});
