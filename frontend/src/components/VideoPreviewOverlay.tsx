import { useMemo } from "react";
import type { HookStyle, SubtitleStyle } from "./StyleEditorModal";
import { DEFAULT_HOOK_STYLE } from "./StyleEditorModal";
import { HookPreviewRenderer } from "./style-editor/preview/HookPreviewRenderer";

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
 *   - podcast_lower_third / quote_card / waveform_pulse / breaking_tape / mic_drop: podcast hook layouts
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
  autoGridLayout?: "single" | "double";
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
  autoGridLayout = "single",
}: PreviewOverlayProps) {
  // Effective duration from config or default
  const duration = hookStyleConfig?.duration || hookDuration;
  const subtitleOffset = 0; // subtitles render from time 0 (hook is visual overlay via z-index, matching Remotion)

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

  // ─── Hook style-specific rendering (100% Visual Parity with HookPreviewRenderer) ───
  const hookRender = useMemo(() => {
    if (!hookVisible) return null;

    const animKey = (hookStyle || hookStyleConfig?.animation || "").toLowerCase().replace(/[\s-]+/g, "_");
    const mergedStyle: HookStyle = {
      ...DEFAULT_HOOK_STYLE,
      ...(hookStyleConfig || {} as any),
      animation: animKey || DEFAULT_HOOK_STYLE.animation,
    };

    return (
      <div
        className="absolute inset-0 pointer-events-none transition-opacity duration-150"
        style={{ opacity: hookAlpha }}
      >
        <HookPreviewRenderer style={mergedStyle} customText={displayHookText} scale={1.0} />
      </div>
    );
  }, [hookVisible, hookStyle, hookAlpha, displayHookText, hookStyleConfig]);

  const subtitleRender = useMemo(() => {
    if (!showSubtitles || !words.length) return null;
    if (currentTime < subtitleOffset) return null;
    // Suppress subtitles while Hook overlay is active on screen (exact parity with Remotion)
    if (hookVisible) return null;

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
    const position = autoGridLayout === "double" ? "center" : (cfg?.position || "bottom");
    const visualPreset = cfg?.stylePreset || "classic";
    const highlightWords: string[] = cfg?.highlightWords || [];
    const highlightStyleType = cfg?.highlightStyle || "scale";

    // Dual style config (matches Remotion SubtitleLayer)
    const dualStyleEnabled = cfg?.dualStyleEnabled;
    const highlightFontFamily = cfg?.highlightFontFamily || "Anton";
    const highlightFontSize = cfg?.highlightFontSize;
    const highlightFontWeight = cfg?.highlightFontWeight || "900";
    const highlightLetterSpacing = cfg?.highlightLetterSpacing || 0;
    const highlightItalic = cfg?.highlightItalic || false;
    const highlightUppercase = cfg?.highlightUppercase || false;

    // Matching Remotion: left-aligned presets
    const alignLeft = visualPreset === "terminal_type" || visualPreset === "lower_third" || visualPreset === "documentary";
    const isImpactPreset = visualPreset === "meme_impact" || visualPreset === "breaking_tape" || visualPreset === "comic_burst";
    const isLightPanel = visualPreset === "bubble_chat" || visualPreset === "breaking_tape" || visualPreset === "quote_box" || visualPreset === "word_tiles";
    const presetWantsDual = visualPreset === "dual_pop" || visualPreset === "neon_pulse" || visualPreset === "meme_impact";

    // Per-preset maxWidth matching Remotion defaults
    const defaultMaxWidth = (() => {
      switch (visualPreset) {
        case "lower_third": return 82;
        case "quote_box": return 80;
        case "minimal_clean": return 84;
        case "meme_impact": return 92;
        case "breaking_tape": return 88;
        case "caption_strip": return 96;
        case "terminal_type": return 86;
        default: return 90;
      }
    })();
    const maxWidthPct = Math.min(96, Math.max(45, Number(cfg?.maxWidthPct ?? defaultMaxWidth)));

    // Font override for terminal_type (monospace, matching Remotion)
    const effectiveFontFamily = visualPreset === "terminal_type" ? "monospace" : `'${fontFamily}', sans-serif`;

    // Group words into pages with the same punctuation/pause/max-word rules as
    // Remotion's groupWordsToSubtitlePages().
    const lines: Word[][] = [];
    let currentLine: Word[] = [];

    for (let i = 0; i < words.length; i++) {
      const w = words[i];
      const nextWord = words[i + 1];
      currentLine.push(w);
      const full = currentLine.length >= maxWordsPerLine;
      const punctuation = /[.,!?;:]$/.test(w.word) && currentLine.length >= 2;
      const pause = nextWord ? nextWord.start - w.end > 0.5 : true;
      if (full || punctuation || pause) { lines.push(currentLine); currentLine = []; }
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
    const posStyle: React.CSSProperties = (() => {
      let topPct = 82;
      if (position === "top") {
        topPct = typeof cfg?.positionY === "number" && cfg.positionY <= 35 ? cfg.positionY : 12;
      } else if (position === "center") {
        topPct = typeof cfg?.positionY === "number" && cfg.positionY > 35 && cfg.positionY < 65 ? cfg.positionY : 50;
      } else {
        // bottom
        topPct = typeof cfg?.positionY === "number" && cfg.positionY >= 65 ? cfg.positionY : 82;
      }
      return { top: `${topPct}%`, bottom: "auto", transform: "translateY(-50%)" };
    })();

    // Panel style matching Remotion presetPanelStyle per preset
    const presetPanelStyle: React.CSSProperties = (() => {
      switch (visualPreset) {
        case "neon_pulse":
          return { border: `1px solid ${highlightColor}88`, boxShadow: `0 0 28px ${highlightColor}52, inset 0 0 22px rgba(2,6,23,0.65)` };
        case "meme_impact":
          return { filter: "drop-shadow(0 10px 18px rgba(0,0,0,0.55))" };
        case "editorial_banner":
          return { borderLeft: `9px solid ${highlightColor}`, boxShadow: "0 14px 30px rgba(0,0,0,0.34)" };
        case "lower_third":
          return { borderLeft: `10px solid ${highlightColor}`, boxShadow: "0 18px 34px rgba(0,0,0,0.42)" };
        case "bubble_chat":
          return { border: "1px solid rgba(17,24,39,0.12)", boxShadow: "0 18px 38px rgba(0,0,0,0.26)" };
        case "breaking_tape":
          return { border: "2px solid rgba(17,17,17,0.9)", boxShadow: "0 16px 28px rgba(0,0,0,0.35)", transform: "rotate(-1.1deg)" };
        case "quote_box":
          return { borderLeft: `7px solid ${highlightColor}`, boxShadow: "0 18px 40px rgba(0,0,0,0.28)" };
        case "documentary":
          return { borderLeft: `5px solid ${highlightColor}`, boxShadow: "0 16px 32px rgba(0,0,0,0.36)" };
        case "dual_pop":
          return { border: `1px solid ${highlightColor}55`, boxShadow: "0 12px 28px rgba(0,0,0,0.35)" };
        case "caption_strip":
          return { width: "100%", borderRadius: 0, borderTop: `4px solid ${highlightColor}`, borderBottom: `4px solid ${highlightColor}77` };
        case "gradient_glass":
          return { background: `linear-gradient(120deg, ${bgColor}CC, ${highlightColor}48)`, border: `1px solid ${highlightColor}88`, backdropFilter: "blur(12px)", borderRadius: 18 };
        case "comic_burst":
          return { filter: "drop-shadow(9px 10px 0 rgba(17,24,39,.72))" };
        case "terminal_type":
          return { border: `2px solid ${highlightColor}88`, borderTop: `16px solid ${highlightColor}59`, boxShadow: `0 0 28px ${highlightColor}33, inset 0 0 24px rgba(0,0,0,0.48)` };
        default:
          return {};
      }
    })();

    // ─── Emphasis mode: big keyword + small context (matches Remotion) ───
    if (lineTransition === "emphasis") {
      const wordTexts = visibleLine.map((w) => w.word);
      const emphIdx = detectEmphasisWord(wordTexts);
      const contextWords = visibleLine.filter((_, i) => i !== emphIdx).map((w) => applyTextCase(w.word, uppercase, capitalize)).join(" ");
      const emphWord = applyTextCase(visibleLine[emphIdx]?.word || "", dualStyleEnabled ? highlightUppercase : uppercase, capitalize);

      return (
        <div
          className="absolute left-0 right-0 flex justify-center px-4"
          style={posStyle}
        >
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, textAlign: "center", maxWidth: `${maxWidthPct}%` }}>
            {contextWords && (
              <span style={{
                color,
                fontSize: `clamp(10px, ${fontSize * 0.48 * 0.055}vw, ${Math.max(18, fontSize * 0.48)}px)`,
                fontWeight: fontWeight as any,
                fontFamily: effectiveFontFamily,
                fontStyle: italic ? "italic" : "normal",
                letterSpacing: cfg?.letterSpacing || 0,
                lineHeight: cfg?.lineHeight || 1.12,
                textShadow: strokeEnabled ? `0 0 ${cfg?.shadowBlur || 8}px ${cfg?.shadowColor || "#000"}` : undefined,
                WebkitTextStroke: strokeEnabled ? `${Math.max(1, strokeWidth * 0.55)}px ${strokeColor}` : undefined,
              }}>{contextWords}</span>
            )}
            <span style={{
              color: highlightColor,
              fontSize: dualStyleEnabled
                ? `clamp(20px, ${(highlightFontSize || fontSize * 1.35) * 0.055}vw, ${highlightFontSize || fontSize * 1.35}px)`
                : `clamp(20px, ${fontSize * highlightScale * 1.2 * 0.055}vw, ${fontSize * highlightScale * 1.2}px)`,
              fontWeight: dualStyleEnabled ? Number(highlightFontWeight) : 900,
              fontFamily: dualStyleEnabled ? `'${highlightFontFamily}', sans-serif` : effectiveFontFamily,
              fontStyle: dualStyleEnabled ? (highlightItalic ? "italic" : "normal") : (italic ? "italic" : "normal"),
              letterSpacing: dualStyleEnabled ? highlightLetterSpacing : (cfg?.letterSpacing || 0),
              lineHeight: cfg?.lineHeight || 1.05,
              textShadow: [
                visualPreset === "spotlight_keyword" ? `0 0 30px ${highlightColor}A6` : "",
                highlightGlow ? `0 0 16px ${highlightGlowColor}` : "",
              ].filter(Boolean).join(", ") || undefined,
              WebkitTextStroke: strokeEnabled ? `${dualStyleEnabled ? 3 : strokeWidth}px ${strokeColor}` : undefined,
              ...(visualPreset === "spotlight_keyword" ? { padding: "0 18px", borderRadius: 10, background: `linear-gradient(90deg, transparent, ${highlightColor}28, transparent)` } : {}),
            }}>{emphWord}</span>
          </div>
        </div>
      );
    }

    if (lineTransition === "line_reveal") {
      return (
        <div
          className="absolute left-0 right-0 flex justify-center px-4"
          style={posStyle}
        >
          <div
            style={{
              position: "relative",
              display: "flex",
              flexWrap: "wrap",
              justifyContent: alignLeft ? "flex-start" : "center",
              gap: `${cfg?.wordSpacing || 6}px`,
              maxWidth: `${maxWidthPct}%`,
              backgroundColor: bgEnabled ? `${bgColor}${Math.round(bgOpacity * 255).toString(16).padStart(2, "0")}` : "transparent",
              borderRadius: bgEnabled ? `${bgRadius}px` : undefined,
              padding: bgEnabled ? `${cfg?.bgPadding || 12}px` : undefined,
              overflow: "hidden",
              ...presetPanelStyle,
            }}
          >
            <div style={{ width: "100%", height: 5, borderRadius: 999, backgroundColor: highlightColor, marginBottom: 8 }} />
            {visibleLine.map((w, i) => {
              const wordStart = w.start + subtitleOffset;
              const wordEnd = w.end + subtitleOffset;
              const isActive = currentTime >= wordStart && currentTime <= wordEnd;
              const isRevealed = currentTime >= wordStart - 0.05;
              if (!isRevealed) return null;
              const wordText = applyTextCase(w.word, uppercase, capitalize);

              return (
                <span
                  key={`${w.word}-${i}`}
                  style={{
                    fontFamily: effectiveFontFamily,
                    fontSize: `clamp(12px, ${fontSize * 0.055}vw, ${fontSize}px)`,
                    fontWeight: isActive ? "900" : fontWeight as any,
                    color: isActive ? highlightColor : color,
                    textShadow: strokeEnabled ? `0 0 ${strokeWidth}px ${strokeColor}` : "none",
                    fontStyle: italic ? "italic" : "normal",
                    display: "inline-block",
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
    }

    // ─── Normal karaoke-style word-by-word (matching Remotion SubtitlePage) ───
    return (
      <div
        className="absolute left-0 right-0 px-4"
        style={{ ...posStyle, display: "flex", justifyContent: alignLeft ? "flex-start" : "center", padding: alignLeft ? "0 46px" : "0 24px" }}
      >
        <div
          style={{
            position: "relative",
            display: "flex",
            flexWrap: "wrap",
            justifyContent: alignLeft ? "flex-start" : "center",
            alignItems: "baseline",
            gap: `${cfg?.wordSpacing || 6}px`,
            maxWidth: `${maxWidthPct}%`,
            lineHeight: cfg?.lineHeight || 1.12,
            textAlign: alignLeft ? "left" : "center",
            backgroundColor: bgEnabled ? `${bgColor}${Math.round(bgOpacity * 255).toString(16).padStart(2, "0")}` : "transparent",
            borderRadius: bgEnabled ? `${bgRadius}px` : undefined,
            padding: bgEnabled ? `${cfg?.bgPadding || 12}px` : undefined,
            ...presetPanelStyle,
          }}
        >
          {/* Neon pulse top bar */}
          {visualPreset === "neon_pulse" && (
            <div style={{ position: "absolute", top: 6, left: 16, right: 16, height: 3, borderRadius: 999, background: `linear-gradient(90deg, transparent, ${highlightColor}, transparent)`, boxShadow: `0 0 16px ${highlightColor}`, zIndex: 0 }} />
          )}
          {/* Lower third left gradient */}
          {visualPreset === "lower_third" && (
            <div style={{ position: "absolute", top: 0, bottom: 0, left: 0, width: 72, background: `linear-gradient(90deg, ${highlightColor}38, transparent)`, zIndex: 0 }} />
          )}
          {/* Bubble chat triangle */}
          {visualPreset === "bubble_chat" && (
            <div style={{ position: "absolute", bottom: -10, left: 34, width: 22, height: 22, transform: "rotate(45deg)", backgroundColor: bgEnabled ? `${bgColor}${Math.round(bgOpacity * 255).toString(16).padStart(2, "0")}` : "#F8FAFC", borderRight: "1px solid rgba(17,24,39,0.08)", borderBottom: "1px solid rgba(17,24,39,0.08)", zIndex: 0 }} />
          )}
          {/* Breaking tape stripe pattern */}
          {visualPreset === "breaking_tape" && (
            <div style={{ position: "absolute", inset: 0, backgroundImage: "repeating-linear-gradient(135deg, transparent 0 18px, rgba(17,17,17,.08) 18px 26px)", zIndex: 0 }} />
          )}
          {/* Quote box inner border */}
          {visualPreset === "quote_box" && (
            <div style={{ position: "absolute", inset: 9, border: `1px solid ${highlightColor}3D`, zIndex: 0 }} />
          )}
          {/* Gradient glass shine */}
          {visualPreset === "gradient_glass" && (
            <div style={{ position: "absolute", inset: 0, borderRadius: "inherit", background: "linear-gradient(115deg, rgba(255,255,255,.15), transparent 42%)", zIndex: 0 }} />
          )}
          {/* Terminal type prompt character */}
          {visualPreset === "terminal_type" && (
            <span style={{ position: "relative", zIndex: 1, color: highlightColor, fontFamily: "monospace", fontSize, fontWeight: 900, marginRight: 4 }}>&gt;</span>
          )}
          {visibleLine.map((w, i) => {
            const wordStart = w.start + subtitleOffset;
            const wordEnd = w.end + subtitleOffset;
            const isActive = currentTime >= wordStart && currentTime <= wordEnd;
            const isRevealed = currentTime >= wordStart - 0.05;

            if (lineTransition === "word_pop" && !isActive) return null;

            const isKeyword = Boolean(w.highlight) || highlightWords.includes(w.word.toLowerCase());
            // Match Remotion: karaoke color for all active, but scale/size only for keywords
            const shouldHighlight = isActive || isKeyword;
            const shouldEnlarge = isActive && isKeyword;

            // Dual style logic matching Remotion
            const useDual = shouldEnlarge && (dualStyleEnabled === true || (dualStyleEnabled === undefined && presetWantsDual));

            const wordFontSize = useDual
              ? (highlightFontSize || fontSize * (isImpactPreset ? 1.22 : 1.12))
              : fontSize;
            const presetScale = shouldEnlarge && isImpactPreset ? 1.1 : shouldEnlarge && visualPreset === "neon_pulse" ? 1.06 : 1;
            const wordScale = shouldEnlarge ? (useDual ? presetScale : highlightScale * presetScale) : 1;
            const wordColor = visualPreset === "word_tiles"
              ? (shouldHighlight ? "#18181B" : "#FFFFFF")
              : shouldHighlight ? highlightColor : color;
            const wordWeight = useDual
              ? Number(highlightFontWeight)
              : (shouldHighlight && cfg?.highlightBold !== false ? 900 : Number(fontWeight));
            const wordFontFamily = useDual ? `'${highlightFontFamily}', sans-serif` : effectiveFontFamily;

            const wordUppercase = useDual ? highlightUppercase : uppercase;
            let wordText = applyTextCase(w.word, wordUppercase, useDual ? false : capitalize);

            // Shadows matching Remotion
            const wordShadow: string[] = [];
            if (useDual ? cfg?.highlightShadowEnabled : cfg?.shadowEnabled) {
              wordShadow.push(`0 0 ${useDual ? (cfg?.highlightShadowBlur || 12) : (cfg?.shadowBlur || 8)}px ${useDual ? (cfg?.highlightShadowColor || "#000") : (cfg?.shadowColor || "#000")}`);
            }
            if (shouldHighlight && highlightGlow) {
              wordShadow.push(`0 0 12px ${highlightGlowColor}`);
            }
            if (shouldHighlight && visualPreset === "neon_pulse") {
              wordShadow.push(`0 0 24px ${highlightColor}`);
            }
            if (isImpactPreset) {
              wordShadow.push("0 7px 16px rgba(0,0,0,0.5)");
            }
            if (strokeEnabled && !wordShadow.length) {
              wordShadow.push(`0 0 ${strokeWidth}px ${strokeColor}`);
            }

            // Text stroke matching Remotion
            const textStroke = (useDual ? cfg?.highlightStrokeEnabled : strokeEnabled)
              ? `${(useDual ? (cfg?.highlightStrokeWidth || 3) : strokeWidth)}px ${useDual ? (cfg?.highlightStrokeColor || "#000") : strokeColor}`
              : visualPreset === "meme_impact"
                ? `${shouldHighlight ? 4 : 3}px #000000`
                : visualPreset === "comic_burst"
                  ? `${shouldHighlight ? 5 : 4}px #111827`
                  : undefined;

            // Per-word background (word_tiles, bubble_chat, breaking_tape)
            const presetBackground = visualPreset === "word_tiles"
              ? (shouldHighlight ? highlightColor : `${color}EA`)
              : shouldHighlight && visualPreset === "bubble_chat"
                ? `${highlightColor}28`
                : shouldHighlight && visualPreset === "breaking_tape"
                  ? "rgba(17,17,17,0.12)"
                  : undefined;
            const presetPadding = visualPreset === "word_tiles" ? "8px 12px" : presetBackground ? "2px 8px" : undefined;

            // Transform parts matching Remotion
            const transformParts: string[] = [];
            if (wordScale !== 1) transformParts.push(`scale(${wordScale})`);
            if (shouldHighlight && visualPreset === "meme_impact") transformParts.push("translateY(-4px)");
            if (shouldHighlight && visualPreset === "breaking_tape") transformParts.push("skewX(-4deg)");
            if (shouldHighlight && visualPreset === "comic_burst") transformParts.push("rotate(-3deg) translateY(-5px)");

            // Highlight style decorations (matching Remotion)
            const highlightDecor: React.CSSProperties = !useDual && shouldHighlight && highlightStyleType === "underline"
              ? { textDecoration: "underline", textDecorationColor: highlightColor, textUnderlineOffset: "4px", textDecorationThickness: "3px" }
              : !useDual && shouldHighlight && highlightStyleType === "background"
                ? { backgroundColor: `${highlightColor}30`, borderRadius: 4, padding: "2px 6px" }
                : !useDual && shouldHighlight && highlightStyleType === "strikethrough"
                  ? { textDecoration: "line-through", textDecorationColor: highlightColor, textDecorationThickness: "3px" }
                  : {};

            // Spotlight keyword pill
            const spotlightStyle: React.CSSProperties = shouldHighlight && visualPreset === "spotlight_keyword"
              ? { padding: "0 18px", borderRadius: 10, background: `linear-gradient(90deg, transparent, ${highlightColor}28, transparent)` }
              : {};

            return (
              <span
                key={`${w.word}-${i}`}
                style={{
                  position: "relative",
                  zIndex: 1,
                  fontFamily: wordFontFamily,
                  fontSize: `clamp(12px, ${wordFontSize * 0.055}vw, ${wordFontSize}px)`,
                  fontWeight: wordWeight,
                  color: wordColor,
                  transform: transformParts.length ? transformParts.join(" ") : "scale(1)",
                  transformOrigin: "center bottom",
                  textShadow: wordShadow.join(", ") || "none",
                  fontStyle: useDual ? (highlightItalic ? "italic" : "normal") : (italic ? "italic" : "normal"),
                  letterSpacing: useDual ? highlightLetterSpacing : (cfg?.letterSpacing || 0),
                  display: "inline-block",
                  transition: "transform 0.1s ease-out, color 0.05s",
                  paintOrder: textStroke ? "stroke" : undefined,
                  WebkitTextStroke: textStroke,
                  backgroundColor: presetBackground,
                  borderRadius: presetBackground ? (visualPreset === "word_tiles" ? 7 : 8) : undefined,
                  padding: presetPadding,
                  lineHeight: cfg?.lineHeight || 1.12,
                  maxWidth: "100%",
                  overflowWrap: "anywhere",
                  wordBreak: "break-word",
                  ...highlightDecor,
                  ...spotlightStyle,
                }}
              >
                {wordText}
              </span>
            );
          })}
        </div>
      </div>
    );
  }, [currentTime, words, showSubtitles, subtitleOffset, subtitleStyleConfig, autoGridLayout]);

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
