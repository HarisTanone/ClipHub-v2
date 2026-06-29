/**
 * Convert a hex color string + opacity to rgba() format.
 *
 * This replaces the fragile hex-appending pattern where opacity was concatenated
 * as hex characters (e.g., `#000000${hexOpacity}`). The rgba() format is consistent
 * with CSS preview behavior in the Custom Style Editor.
 *
 * Handles:
 * - 3-char hex: #RGB → rgba(R, G, B, opacity)
 * - 6-char hex: #RRGGBB → rgba(R, G, B, opacity)
 * - 8-char hex: #RRGGBBAA → strips alpha, uses provided opacity
 * - Invalid hex: falls back to rgba(0, 0, 0, opacity)
 */
export function hexToRgba(hex: string, opacity: number): string {
  // Strip # prefix
  let cleanHex = hex.replace(/^#/, "");

  // Handle 8-char hex (strip alpha channel, use provided opacity)
  if (cleanHex.length === 8) {
    cleanHex = cleanHex.slice(0, 6);
  }

  // Handle 3-char hex → expand to 6-char
  if (cleanHex.length === 3) {
    cleanHex = cleanHex
      .split("")
      .map((c) => c + c)
      .join("");
  }

  // Validate 6-char hex
  if (cleanHex.length !== 6 || !/^[0-9a-fA-F]{6}$/.test(cleanHex)) {
    // Fallback for invalid hex
    return `rgba(0, 0, 0, ${opacity})`;
  }

  const r = parseInt(cleanHex.slice(0, 2), 16);
  const g = parseInt(cleanHex.slice(2, 4), 16);
  const b = parseInt(cleanHex.slice(4, 6), 16);

  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}
