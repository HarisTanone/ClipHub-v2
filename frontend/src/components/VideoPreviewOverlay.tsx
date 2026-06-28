import { useMemo } from "react";
import type { HookStyle, SubtitleStyle } from "./StyleEditorModal";

/**
 * VideoPreviewOverlay — Real-time HTML/CSS simulation of FFmpeg hook text
 * and subtitle rendering, synced to video currentTime.
 *
 * IMPORTANT: This must match the actual FFmpeg output from backend.
 * Each hook animation uses the SAME math as FFmpeg drawtext expressions:
 *   - glitch_rgb: 3 text layers, offset by sin(t*15)*3 px
 *   - shake_neon: glow layers + sin(t*25)*2, cos(t*20)*2 shake
 *   - cinematic_reveal: letterbox + 1s fade-in
 *   - danger_bold: red glow pulse
 *   - zoom_punch / fade_scale: alpha fade
 *   - slide_punch_framer: slide from off-screen
 *   - typewriter: char-by-char reveal
 */

interface Word {
  word: string;
  start: number;
  end: number;
  highlight?: boolean;
}

interface PreviewOverlayProps {
  currentTime: number;
  hookText: string;
  hookStyle: string;
  hookStyleConfig?: HookStyle;
  subtitleStyleConfig?: SubtitleStyle;
  words: Word[];
  showHook: boolean;
  showSubtitles: boolean;
  hookDuration?: number;
}

// ─── Alpha calculation matching FFmpeg expression ────────────────────────────
// FFmpeg: if(lt(t,0.5), t/0.5, if(gt(t, dur-0.5), (dur-t)/0.5, 1))
function calcAlpha(t: number, duration: number): number {
  if (t < 0) return 0;
  if (t > duration) return 0;
  if (t < 0.5) return t / 0.5;
  if (t > duration - 0.5) return (duration - t) / 0.5;
  return 1;
}

// Cinematic reveal alpha: slower fade (1s in, 0.8s out)
function calcCinematicAlpha(t: number, duration: number): number {
  if (t < 0) return 0;
  if (t > duration) return 0;
  if (t < 1.0) return t / 1.0;
  if (t > duration - 0.8) return (duration - t) / 0.8;
  return 1;
}

// ─── Indonesian stop words for emphasis detection ────────────────────────────
const STOP_WORDS = new Set([
  "yang", "dan", "di", "ke", "dari", "ini", "itu", "dengan", "untuk",
  "pada", "adalah", "juga", "akan", "sudah", "udah", "gak", "nggak",
  "tidak", "bukan", "ada", "bisa", "lagi", "kalau", "aja", "sih",
  "ya", "dong", "deh", "nih", "tuh", "loh", "kan", "pun", "atau",
  "tapi", "jadi", "saya", "aku", "kamu", "dia", "kita", "mereka",
  "the", "is", "a", "to", "of", "in", "it", "and", "for", "but",
  "so", "he", "she", "we", "they",
]);

function detectEmphasisWord(words: string[]): number {
  // Find longest non-stop word
  let best = 0;
  let bestLen = 0;
  for (let i = 0; i < words.length; i++) {
    const w = words[i].toLowerCase().replace(/[^a-z]/g, "");
    if (!STOP_WORDS.has(w) && w.length > bestLen) {
      bestLen = w.length;
      best = i;
    }
  }
  return best;
}

// ─── Apply text transform ────────────────────────────────────────────────────
function applyTextCase(text: string, uppercase?: boolean, capitalize?: boolean): string {
  if (uppercase) return text.toUpperCase();
  if (capitalize) return text.replace(/\b\w/g, (c) => c.toUpperCase());
  return text;
}

export function VideoPreviewOverlay({
  currentTime,
  hookText,
  hookStyle,
  hookStyleConfig,
  subtitleStyleConfig,
  words,
  showHook,
  showSubtitles,
  hookDuration = 3.0,
}: PreviewOverlayProps) {
  // Effective duration from config or default
  const duration = hookStyleConfig?.duration || hookDuration;
  const subtitleOffset = duration; // subtitles start after hook ends

  // ─── Hook Rendering ──────────────────────────────────────────────────────
  const hookVisible = showHook && currentTime >= 0 && currentTime < duration && !!hookText;
  const t = currentTime; // time in seconds, same as FFmpeg 't' variable

  const hookAlpha = hookVisible ? calcAlpha(t, duration) : 0;

  // Apply text transform for hook
  const displayHookText = useMemo(() => {
    if (!hookText) return "";
    if (hookStyleConfig?.uppercase) return hookText.toUpperCase();
    return hookText;
  }, [hookText, hookStyleConfig?.uppercase]);

  // Multi-line split (same as backend: >4 words → split in middle)
  const hookLines = useMemo(() => {
    const wordsList = displayHookText.split(/\s+/);
    if (wordsList.length > 4) {
      const mid = Math.floor(wordsList.length / 2);
      return [wordsList.slice(0, mid).join(" "), wordsList.slice(mid).join(" ")];
    }
    return [displayHookText];
  }, [displayHookText]);

  // ─── Hook style-specific rendering ─────────────────────────────────────
  const hookRender = useMemo(() => {
    if (!hookVisible) return null;

    // Get config values or defaults matching FFmpeg
    const cfg = hookStyleConfig;
    const fontFamily = cfg?.fontFamily || "Poppins";
    const fontSize = cfg?.fontSize || 48;
    const fontWeight = cfg?.fontWeight || "800";
    const color = cfg?.color || "#FFFFFF";
    const bgOpacity = cfg?.bgOpacity ?? 0.6;
    const letterSpacing = cfg?.letterSpacing || 0;
    const italic = cfg?.italic || false;
    const glowEnabled = cfg?.glowEnabled || false;
    const glowColor = cfg?.glowColor || "#FFCC00";
    const glowSize = cfg?.glowSize || 20;
    const gradientEnabled = cfg?.gradientEnabled || false;
    const gradientFrom = cfg?.gradientFrom || "#FFFFFF";
    const gradientTo = cfg?.gradientTo || "#FFCC00";
    const gradientAngle = cfg?.gradientAngle || 180;
    const shadowEnabled = cfg?.shadowEnabled ?? true;
    const shadowColor = cfg?.shadowColor || "#000000";
    const shadowBlur = cfg?.shadowBlur || 12;
    const shadowX = cfg?.shadowX || 0;
    const shadowY = cfg?.shadowY || 4;

    // Common text style
    const baseTextStyle: React.CSSProperties = {
      fontFamily: `'${fontFamily}', sans-serif`,
      fontSize: `clamp(14px, ${fontSize * 0.065}vw, ${fontSize}px)`,
      fontWeight: fontWeight as any,
      letterSpacing: `${letterSpacing}px`,
      fontStyle: italic ? "italic" : "normal",
      lineHeight: cfg?.lineHeight || 1.3,
      textAlign: "center",
      maxWidth: "85%",
      whiteSpace: "pre-line",
      wordBreak: "break-word",
    };

    // Text shadow from config
    const textShadowParts: string[] = [];
    if (shadowEnabled) {
      textShadowParts.push(`${shadowX}px ${shadowY}px ${shadowBlur}px ${shadowColor}`);
    }
    if (glowEnabled) {
      textShadowParts.push(`0 0 ${glowSize}px ${glowColor}`);
      textShadowParts.push(`0 0 ${glowSize * 2}px ${glowColor}`);
    }

    // Gradient or solid color
    const colorStyle: React.CSSProperties = gradientEnabled
      ? {
        background: `linear-gradient(${gradientAngle}deg, ${gradientFrom}, ${gradientTo})`,
        WebkitBackgroundClip: "text",
        WebkitTextFillColor: "transparent",
        backgroundClip: "text",
      }
      : { color };

    const textContent = hookLines.join("\n");

    // ─── ANIMATION-SPECIFIC RENDERING ──────────────────────────────────
    switch (hookStyle) {
      case "glitch_rgb": {
        // FFmpeg: 3 drawtext layers
        // Red: x=(w-text_w)/2-4+sin(t*15)*3, color=#FF0000@0.7
        // Cyan: x=(w-text_w)/2+4-sin(t*15)*3, color=#00FFFF@0.7
        // White: x=(w-text_w)/2, color=white
        const offsetX = Math.sin(t * 15) * 3; // matches sin(t*15)*3
        const redX = -4 + offsetX;
        const cyanX = 4 - offsetX;

        return (
          <div
            className="absolute inset-0 flex items-center justify-center"
            style={{ backgroundColor: `rgba(0,0,0,${bgOpacity})`, opacity: hookAlpha }}
          >
            {/* Red channel layer */}
            <p
              style={{
                ...baseTextStyle,
                position: "absolute",
                color: "#FF0000",
                opacity: 0.7,
                transform: `translate(${redX}px, 0)`,
                textShadow: "none",
              }}
            >
              {textContent}
            </p>
            {/* Cyan channel layer */}
            <p
              style={{
                ...baseTextStyle,
                position: "absolute",
                color: "#00FFFF",
                opacity: 0.7,
                transform: `translate(${cyanX}px, 0)`,
                textShadow: "none",
              }}
            >
              {textContent}
            </p>
            {/* Main white text on top */}
            <p
              style={{
                ...baseTextStyle,
                position: "relative",
                ...colorStyle,
                textShadow: textShadowParts.join(", ") || "none",
              }}
            >
              {textContent}
            </p>
          </div>
        );
      }

      case "shake_neon": {
        // FFmpeg: glow layer1 (borderw=12, @0.3), glow layer2 (borderw=6, @0.5, +sin(t*25)*2, cos(t*20)*2),
        // main text (+sin(t*30)*1.5, cos(t*35)*1)
        const glowX2 = Math.sin(t * 25) * 2;
        const glowY2 = Math.cos(t * 20) * 2;
        const mainX = Math.sin(t * 30) * 1.5;
        const mainY = Math.cos(t * 35) * 1;
        const neonColor = color || "#00FFCC";

        return (
          <div
            className="absolute inset-0 flex items-center justify-center"
            style={{ backgroundColor: `rgba(0,0,0,${bgOpacity})`, opacity: hookAlpha }}
          >
            {/* Glow layer 1: large, dim blur */}
            <p
              style={{
                ...baseTextStyle,
                position: "absolute",
                color: neonColor,
                opacity: 0.3,
                textShadow: `0 0 12px ${neonColor}, 0 0 24px ${neonColor}`,
                filter: "blur(2px)",
              }}
            >
              {textContent}
            </p>
            {/* Glow layer 2: medium glow, shaking */}
            <p
              style={{
                ...baseTextStyle,
                position: "absolute",
                color: neonColor,
                opacity: 0.5,
                transform: `translate(${glowX2}px, ${glowY2}px)`,
                textShadow: `0 0 6px ${neonColor}, 0 0 12px ${neonColor}`,
              }}
            >
              {textContent}
            </p>
            {/* Main text: subtle shake */}
            <p
              style={{
                ...baseTextStyle,
                position: "relative",
                color: neonColor,
                transform: `translate(${mainX}px, ${mainY}px)`,
                textShadow: `0 0 10px ${neonColor}, 0 0 20px ${neonColor}, 0 0 40px ${neonColor}`,
              }}
            >
              {textContent}
            </p>
          </div>
        );
      }

      case "cinematic_reveal": {
        // FFmpeg: letterbox bars (12% top/bottom), dark overlay, slow 1s fade
        const cinAlpha = calcCinematicAlpha(t, duration);
        const revealColor = color || "#FFD700";

        return (
          <div className="absolute inset-0" style={{ opacity: cinAlpha }}>
            {/* Letterbox top bar */}
            <div
              className="absolute top-0 left-0 right-0"
              style={{ height: "12%", backgroundColor: "#000000" }}
            />
            {/* Letterbox bottom bar */}
            <div
              className="absolute bottom-0 left-0 right-0"
              style={{ height: "12%", backgroundColor: "#000000" }}
            />
            {/* Dark overlay */}
            <div
              className="absolute inset-0"
              style={{ backgroundColor: `rgba(0,0,0,${bgOpacity})` }}
            />
            {/* Main text */}
            <div className="absolute inset-0 flex items-center justify-center">
              <p
                style={{
                  ...baseTextStyle,
                  color: revealColor,
                  textShadow: `2px 2px 4px rgba(0,0,0,0.8)${glowEnabled ? `, 0 0 ${glowSize}px ${glowColor}` : ""}`,
                }}
              >
                {textContent}
              </p>
            </div>
          </div>
        );
      }

      case "danger_bold": {
        // FFmpeg: red glow behind (borderw=10, #FF0000@0.4, bordercolor=#FF0000@0.2)
        // + main text with thick border
        const dangerColor = color || "#FF2D2D";
        // Simulate pulse: subtle scale oscillation
        const pulse = 1 + Math.sin(t * 5) * 0.02;

        return (
          <div
            className="absolute inset-0 flex items-center justify-center"
            style={{ backgroundColor: `rgba(0,0,0,${bgOpacity})`, opacity: hookAlpha }}
          >
            {/* Red glow behind */}
            <p
              style={{
                ...baseTextStyle,
                position: "absolute",
                color: "#FF0000",
                opacity: 0.4,
                textShadow: `0 0 10px #FF0000, 0 0 20px #FF0000, 0 0 40px rgba(255,0,0,0.3)`,
                transform: `scale(${pulse})`,
              }}
            >
              {textContent}
            </p>
            {/* Main text with thick border (simulated via text-stroke) */}
            <p
              style={{
                ...baseTextStyle,
                position: "relative",
                color: dangerColor,
                WebkitTextStroke: "3px black",
                textShadow: `0 0 10px #FF0000, 0 0 20px rgba(255,0,0,0.5)`,
                transform: `scale(${pulse})`,
              }}
            >
              {textContent}
            </p>
          </div>
        );
      }

      case "typewriter": {
        // FFmpeg: character-by-character isn't native, but the style uses green monospace
        // We simulate by revealing chars over time
        const charsPerSec = displayHookText.length / (duration - 0.5);
        const charsVisible = Math.min(Math.floor(t * charsPerSec), displayHookText.length);
        const revealed = displayHookText.slice(0, charsVisible);

        return (
          <div
            className="absolute inset-0 flex items-center justify-center"
            style={{ backgroundColor: `rgba(0,0,0,${bgOpacity})`, opacity: hookAlpha }}
          >
            <p
              style={{
                ...baseTextStyle,
                ...colorStyle,
                textShadow: textShadowParts.join(", ") || "0 2px 8px rgba(0,0,0,0.7)",
              }}
            >
              {revealed}
              <span style={{ opacity: 0.7, animation: "blink 1s step-end infinite" }}>|</span>
            </p>
          </div>
        );
      }

      case "slide_punch_framer": {
        // FFmpeg doesn't actually animate x position (drawtext x is static),
        // but CSS preview simulates a slide-in effect for visual feedback
        const slideProgress = Math.min(1, t / 0.4);
        const slideX = (1 - slideProgress) * -100; // slide from left
        const bounceScale = slideProgress >= 1 ? 1 : 0.95 + slideProgress * 0.05;

        return (
          <div
            className="absolute inset-0 flex items-center justify-center"
            style={{ backgroundColor: `rgba(0,0,0,${bgOpacity})`, opacity: hookAlpha }}
          >
            <p
              style={{
                ...baseTextStyle,
                ...colorStyle,
                textShadow: textShadowParts.join(", ") || "0 2px 8px rgba(0,0,0,0.7)",
                transform: `translateX(${slideX}%) scale(${bounceScale})`,
                transition: "none",
              }}
            >
              {textContent}
            </p>
          </div>
        );
      }

      case "fade_scale": {
        // FFmpeg: simple drawtext with alpha fade — we add slight scale for "scale" feel
        const scaleProgress = Math.min(1, t / 0.6);
        const scale = 0.92 + scaleProgress * 0.08;

        return (
          <div
            className="absolute inset-0 flex items-center justify-center"
            style={{ backgroundColor: `rgba(0,0,0,${bgOpacity})`, opacity: hookAlpha }}
          >
            <p
              style={{
                ...baseTextStyle,
                ...colorStyle,
                textShadow: textShadowParts.join(", ") || "0 2px 8px rgba(0,0,0,0.7)",
                transform: `scale(${scale})`,
              }}
            >
              {textContent}
            </p>
          </div>
        );
      }

      case "zoom_punch":
      default: {
        // FFmpeg: bold white, alpha fade, static position
        // We add a quick scale-in to 1 for "punch" feel
        const punchScale = t < 0.3 ? 0.85 + (t / 0.3) * 0.15 : 1;

        return (
          <div
            className="absolute inset-0 flex items-center justify-center"
            style={{ backgroundColor: `rgba(0,0,0,${bgOpacity})`, opacity: hookAlpha }}
          >
            <p
              style={{
                ...baseTextStyle,
                ...colorStyle,
                textShadow: textShadowParts.join(", ") || "0 2px 8px rgba(0,0,0,0.7)",
                transform: `scale(${punchScale})`,
              }}
            >
              {textContent}
            </p>
          </div>
        );
      }
    }
  }, [hookVisible, hookStyle, hookAlpha, t, duration, hookLines, displayHookText, hookStyleConfig]);

  // ─── Subtitle Rendering ────────────────────────────────────────────────────
  const subtitleRender = useMemo(() => {
    if (!showSubtitles || !words.length) return null;
    if (currentTime < subtitleOffset) return null;

    const cfg = subtitleStyleConfig;
    const fontFamily = cfg?.fontFamily || "Inter";
    const fontSize = cfg?.fontSize || 34;
    const fontWeight = cfg?.fontWeight || "700";
    const color = cfg?.color || "#FFFFFF";
    const highlightColor = cfg?.highlightColor || "#FFCC00";
    const highlightScale = cfg?.highlightScale || 1.1;
    const bgEnabled = cfg?.bgEnabled ?? true;
    const bgColor = cfg?.bgColor || "#000000";
    const bgOpacity = cfg?.bgOpacity ?? 0.4;
    const bgRadius = cfg?.bgRadius ?? 8;
    const uppercase = cfg?.uppercase || false;
    const capitalize = cfg?.capitalize || false;
    const italic = cfg?.italic || false;
    const strokeEnabled = cfg?.strokeEnabled ?? true;
    const strokeColor = cfg?.strokeColor || "#000000";
    const strokeWidth = cfg?.strokeWidth || 2;
    const maxWordsPerLine = cfg?.maxWordsPerLine || 3;
    const highlightGlow = cfg?.highlightGlow || false;
    const highlightGlowColor = cfg?.highlightGlowColor || highlightColor;
    const lineTransition = cfg?.lineTransition || "word_pop";
    const position = cfg?.position || "bottom";

    // Group words into lines (matching backend logic)
    const lines: Word[][] = [];
    let currentLine: Word[] = [];
    let currentChars = 0;
    const maxChars = 25;

    for (let i = 0; i < words.length; i++) {
      const w = words[i];
      const wordLen = w.word.length;
      const newChars = currentChars + wordLen + (currentLine.length ? 1 : 0);
      const wordCount = currentLine.length + 1;

      let forceNew = false;
      if (currentLine.length > 0) {
        const prevEnd = currentLine[currentLine.length - 1].end;
        if (w.start - prevEnd > 0.5) forceNew = true;
      }

      if (forceNew || wordCount > maxWordsPerLine || newChars > maxChars) {
        if (currentLine.length) lines.push(currentLine);
        currentLine = [w];
        currentChars = wordLen;
      } else {
        currentLine.push(w);
        currentChars = newChars;
      }
    }
    if (currentLine.length) lines.push(currentLine);

    // Find visible line (the one whose time range includes currentTime)
    const adjustedTime = currentTime - subtitleOffset;
    const visibleLineIdx = lines.findIndex((line) => {
      const lineStart = line[0].start;
      const lineEnd = line[line.length - 1].end;
      return adjustedTime >= lineStart - 0.1 && adjustedTime <= lineEnd + 0.3;
    });

    if (visibleLineIdx === -1) return null;
    const visibleLine = lines[visibleLineIdx];

    // Position style
    const posStyle: React.CSSProperties =
      position === "top"
        ? { top: "8%", bottom: "auto" }
        : position === "center"
          ? { top: "50%", bottom: "auto", transform: "translateY(-50%)" }
          : { bottom: "12%" };

    // ─── Emphasis mode: big keyword + small context ─────────────────────
    if (lineTransition === "emphasis") {
      const wordTexts = visibleLine.map((w) => w.word);
      const emphIdx = detectEmphasisWord(wordTexts);

      return (
        <div
          className="absolute left-0 right-0 flex flex-col items-center justify-center px-4"
          style={posStyle}
        >
          {visibleLine.map((w, i) => {
            const wordStart = w.start + subtitleOffset;
            const isVisible = currentTime >= wordStart - 0.05;
            if (!isVisible) return null;

            const isEmphasis = i === emphIdx;
            let wordText = applyTextCase(w.word, uppercase, capitalize);

            return (
              <span
                key={`${w.word}-${i}`}
                style={{
                  fontFamily: `'${fontFamily}', sans-serif`,
                  fontSize: isEmphasis
                    ? `clamp(24px, ${fontSize * 2.6 * 0.06}vw, ${fontSize * 2.6}px)`
                    : `clamp(10px, ${fontSize * 0.8 * 0.06}vw, ${fontSize * 0.8}px)`,
                  fontWeight: isEmphasis ? "900" : fontWeight as any,
                  color: isEmphasis ? highlightColor : color,
                  textShadow: isEmphasis && highlightGlow
                    ? `0 0 10px ${highlightGlowColor}, 0 0 20px ${highlightGlowColor}`
                    : strokeEnabled ? `0 0 ${strokeWidth}px ${strokeColor}` : "none",
                  display: "block",
                  textAlign: "center",
                  lineHeight: isEmphasis ? 1.2 : 1.4,
                  fontStyle: italic ? "italic" : "normal",
                }}
              >
                {wordText}
              </span>
            );
          })}
        </div>
      );
    }

    // ─── Normal karaoke-style word-by-word ──────────────────────────────
    return (
      <div
        className="absolute left-0 right-0 flex justify-center px-4"
        style={posStyle}
      >
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: `${cfg?.wordSpacing || 6}px`,
            backgroundColor: bgEnabled ? `${bgColor}${Math.round(bgOpacity * 255).toString(16).padStart(2, "0")}` : "transparent",
            borderRadius: bgEnabled ? `${bgRadius}px` : undefined,
            padding: bgEnabled ? `${cfg?.bgPadding || 12}px` : undefined,
          }}
        >
          {visibleLine.map((w, i) => {
            const wordStart = w.start + subtitleOffset;
            const wordEnd = w.end + subtitleOffset;
            const isActive = currentTime >= wordStart && currentTime <= wordEnd;
            const isRevealed = currentTime >= wordStart - 0.05;

            if (!isRevealed) return null;

            let wordText = applyTextCase(w.word, uppercase, capitalize);

            const wordShadow: string[] = [];
            if (strokeEnabled) {
              wordShadow.push(`0 0 ${strokeWidth}px ${strokeColor}`);
            }
            if (isActive && highlightGlow) {
              wordShadow.push(`0 0 8px ${highlightGlowColor}`);
              wordShadow.push(`0 0 16px ${highlightGlowColor}`);
            }

            return (
              <span
                key={`${w.word}-${i}`}
                style={{
                  fontFamily: `'${fontFamily}', sans-serif`,
                  fontSize: `clamp(12px, ${fontSize * 0.055}vw, ${fontSize}px)`,
                  fontWeight: fontWeight as any,
                  color: isActive ? highlightColor : color,
                  transform: isActive ? `scale(${highlightScale})` : "scale(1)",
                  textShadow: wordShadow.join(", ") || "none",
                  fontStyle: italic ? "italic" : "normal",
                  display: "inline-block",
                  transition: "color 0.1s, transform 0.1s",
                  WebkitTextStroke: strokeEnabled ? `${strokeWidth * 0.3}px ${strokeColor}` : undefined,
                }}
              >
                {wordText}
              </span>
            );
          })}
        </div>
      </div>
    );
  }, [currentTime, words, showSubtitles, subtitleOffset, subtitleStyleConfig]);

  // ─── Accent line for hook (if enabled) ─────────────────────────────────────
  const accentLine = useMemo(() => {
    if (!hookVisible || !hookStyleConfig?.lineEnabled) return null;
    const cfg = hookStyleConfig;
    const lineColor = cfg.lineColor || "#FF4444";
    const lineThickness = cfg.lineThickness || 3;

    // Only show bottom accent line in overlay (simplified)
    return (
      <div
        className="absolute left-1/2 -translate-x-1/2"
        style={{
          bottom: "38%",
          width: "40%",
          height: `${lineThickness}px`,
          backgroundColor: lineColor,
          opacity: hookAlpha,
        }}
      />
    );
  }, [hookVisible, hookStyleConfig, hookAlpha]);

  // ─── Box decoration for hook ───────────────────────────────────────────────
  const hookBox = useMemo(() => {
    if (!hookVisible || !hookStyleConfig?.boxEnabled) return null;
    const cfg = hookStyleConfig;
    return (
      <div
        className="absolute inset-0 flex items-center justify-center pointer-events-none"
        style={{ opacity: hookAlpha }}
      >
        <div
          style={{
            border: `2px solid ${cfg.boxColor || "#FFFFFF"}`,
            borderRadius: `${cfg.boxRadius || 12}px`,
            padding: `${cfg.boxPadding || 24}px`,
            backgroundColor: `${cfg.boxColor || "#FFFFFF"}${Math.round((cfg.boxOpacity || 0.15) * 255).toString(16).padStart(2, "0")}`,
          }}
        >
          {/* Empty — text is rendered separately, this is just the box decoration */}
          <span style={{ visibility: "hidden", fontSize: `${hookStyleConfig.fontSize || 48}px` }}>
            {displayHookText}
          </span>
        </div>
      </div>
    );
  }, [hookVisible, hookStyleConfig, hookAlpha, displayHookText]);

  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden">
      {/* Blink cursor keyframe */}
      <style>{`@keyframes blink { 50% { opacity: 0; } }`}</style>

      {/* Hook overlay */}
      {hookRender}
      {accentLine}
      {hookBox}

      {/* Subtitle overlay */}
      {subtitleRender}

      {/* Timeline indicator badges */}
      <div className="absolute top-2 left-2 flex items-center gap-1.5">
        {hookVisible && (
          <span className="bg-emerald-500/80 text-[9px] text-white font-medium px-1.5 py-0.5 rounded">
            HOOK
          </span>
        )}
        {showSubtitles && currentTime >= subtitleOffset && (
          <span className="bg-blue-500/80 text-[9px] text-white font-medium px-1.5 py-0.5 rounded">
            SUB
          </span>
        )}
      </div>
    </div>
  );
}
