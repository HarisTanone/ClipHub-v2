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
    const hookTop = `${cfg?.positionY ?? 50}%`;
    const overlayBg = `rgba(0,0,0,${bgOpacity})`;

    // ─── ANIMATION-SPECIFIC RENDERING ──────────────────────────────────
    switch (hookStyle) {
      case "podcast_lower_third": {
        const progress = Math.min(1, t / 0.45);
        const y = (1 - progress) * 56;
        const accent = cfg?.lineColor || "#16F2B3";
        const dotOpacity = 0.35 + Math.abs(Math.sin(t * 9)) * 0.65;

        return (
          <div className="absolute inset-0" style={{ backgroundColor: overlayBg, opacity: hookAlpha }}>
            <div
              className="absolute left-[7%] right-[7%] grid items-center"
              style={{
                top: hookTop,
                gridTemplateColumns: "54px 1fr",
                gap: 12,
                transform: `translateY(calc(-50% + ${y}px))`,
                padding: "14px 16px",
                borderRadius: 16,
                border: `1px solid ${accent}66`,
                borderLeft: `6px solid ${accent}`,
                background: "linear-gradient(90deg, rgba(6,17,31,0.96), rgba(16,24,39,0.82))",
                boxShadow: `0 18px 38px rgba(0,0,0,0.38), 0 0 22px ${accent}33`,
              }}
            >
              <div className="flex flex-col items-center gap-1.5">
                <span style={{ width: 11, height: 11, borderRadius: 99, backgroundColor: accent, opacity: dotOpacity, boxShadow: `0 0 14px ${accent}` }} />
                <span style={{ color: accent, fontSize: 10, fontWeight: 900, letterSpacing: 0 }}>ON AIR</span>
              </div>
              <p style={{ ...baseTextStyle, color, textAlign: "left", lineHeight: 1.04, textShadow: textShadowParts.join(", ") || "0 4px 18px rgba(0,0,0,0.65)" }}>
                {textContent}
              </p>
            </div>
          </div>
        );
      }

      case "quote_card": {
        const progress = Math.min(1, t / 0.45);
        const scale = 0.88 + progress * 0.12;
        const accent = cfg?.lineColor || "#FF4D2D";
        const card = cfg?.boxColor || "#F5EFE1";

        return (
          <div className="absolute inset-0 flex items-center justify-center" style={{ backgroundColor: overlayBg, opacity: hookAlpha }}>
            <div
              style={{
                position: "relative",
                width: "78%",
                padding: "30px 28px 22px",
                borderRadius: 22,
                background: card,
                border: "2px solid rgba(255,255,255,0.72)",
                boxShadow: "0 28px 58px rgba(0,0,0,0.42)",
                transform: `scale(${scale}) rotate(-1deg)`,
              }}
            >
              <span style={{ position: "absolute", top: -24, left: 20, color: accent, fontSize: 70, fontFamily: "Georgia, serif", lineHeight: 1 }}>"</span>
              <p style={{ ...baseTextStyle, color: cfg?.color || "#171717", lineHeight: cfg?.lineHeight || 1.16, textShadow: "none" }}>{textContent}</p>
              <div style={{ width: "36%", height: 5, borderRadius: 999, margin: "18px auto 0", backgroundColor: accent }} />
            </div>
          </div>
        );
      }

      case "waveform_pulse": {
        const waveColor = cfg?.glowColor || cfg?.gradientTo || color || "#14F1D9";
        const pulse = 1 + Math.sin(t * 5.4) * 0.035;
        const bars = Array.from({ length: 15 });
        const waveTextStyle: React.CSSProperties = gradientEnabled
          ? {
            background: `linear-gradient(${gradientAngle}deg, ${gradientFrom}, ${gradientTo || waveColor})`,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }
          : { color };

        return (
          <div className="absolute inset-0 flex items-center justify-center" style={{ backgroundColor: overlayBg, opacity: hookAlpha }}>
            <div style={{ textAlign: "center", transform: `scale(${pulse})`, width: "100%" }}>
              <div className="flex items-center justify-center" style={{ gap: 5, height: 64, marginBottom: 12 }}>
                {bars.map((_, i) => {
                  const h = 20 + Math.abs(Math.sin(t * 8 + i * 0.7)) * (24 + (i % 4) * 5);
                  return <span key={i} style={{ width: 6, height: h, borderRadius: 99, backgroundColor: waveColor, boxShadow: `0 0 14px ${waveColor}`, opacity: 0.45 + Math.abs(Math.sin(t * 7 + i)) * 0.55 }} />;
                })}
              </div>
              <p style={{ ...baseTextStyle, ...waveTextStyle, textShadow: textShadowParts.join(", ") || `0 0 18px ${waveColor}` }}>{textContent}</p>
            </div>
          </div>
        );
      }

      case "breaking_tape": {
        const progress = Math.min(1, t / 0.35);
        const x = (1 - progress) * -120;
        const tapeColor = cfg?.boxColor || "#FFDD2D";

        return (
          <div className="absolute inset-0" style={{ backgroundColor: overlayBg, opacity: hookAlpha }}>
            <div
              className="absolute left-[-12%] right-[-12%]"
              style={{
                top: hookTop,
                transform: `translateY(-50%) translateX(${x}px) rotate(-4deg)`,
                padding: "14px 34px",
                background: `linear-gradient(90deg, ${tapeColor}, #FFF06A, ${tapeColor})`,
                borderTop: "4px solid rgba(0,0,0,0.92)",
                borderBottom: "4px solid rgba(0,0,0,0.92)",
                boxShadow: "0 22px 44px rgba(0,0,0,0.38)",
                textAlign: "center",
              }}
            >
              <span style={{ display: "block", color: "#D71920", fontSize: 12, fontWeight: 900, letterSpacing: 0, marginBottom: 4 }}>HOT TAKE</span>
              <p style={{ ...baseTextStyle, color: cfg?.color || "#111111", lineHeight: 0.98, textShadow: "none" }}>{textContent}</p>
            </div>
          </div>
        );
      }

      case "mic_drop": {
        const progress = Math.min(1, t / 0.35);
        const y = (1 - progress) * -180;
        const accent = cfg?.boxColor || cfg?.gradientTo || "#FF4D7D";
        const impact = t > 0.35 && t < 0.8 ? 1 + Math.sin(t * 30) * 0.045 : 1;

        return (
          <div className="absolute inset-0 flex items-center justify-center" style={{ backgroundColor: overlayBg, opacity: hookAlpha }}>
            <div
              style={{
                width: "78%",
                padding: "24px 28px",
                borderRadius: 999,
                border: `4px solid ${accent}`,
                background: "rgba(5,5,7,0.78)",
                boxShadow: `0 0 34px ${accent}66, inset 0 0 20px rgba(255,255,255,0.08)`,
                transform: `translateY(${y}px) scale(${impact})`,
                textAlign: "center",
              }}
            >
              <p style={{ ...baseTextStyle, ...colorStyle, textShadow: textShadowParts.join(", ") || `0 0 22px ${accent}`, lineHeight: 1.02 }}>{textContent}</p>
            </div>
            {t > 0.35 && t < 0.8 && <span style={{ position: "absolute", top: "62%", left: "50%", width: `${160 + (t - 0.35) * 520}px`, height: 5, borderRadius: 99, backgroundColor: accent, transform: "translateX(-50%)", boxShadow: `0 0 22px ${accent}`, opacity: 1 - (t - 0.35) / 0.45 }} />}
          </div>
        );
      }

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

      case "comment_reply": {
        const panel = cfg?.boxColor || "#FFFFFF";
        const accent = cfg?.lineColor || "#18181B";
        return (
          <div className="absolute inset-0" style={{ backgroundColor: overlayBg, opacity: hookAlpha }}>
            <div style={{ position: "absolute", top: hookTop, left: "7%", right: "13%", transform: "translateY(-50%)", borderRadius: 18, padding: "18px 20px", background: panel, boxShadow: "0 20px 44px rgba(0,0,0,.36)" }}>
              <span style={{ display: "block", marginBottom: 6, color: `${accent}99`, fontSize: 10, fontWeight: 700 }}>{cfg?.badgeText || "replying to @viewer"}</span>
              <p style={{ ...baseTextStyle, color: cfg?.color || "#18181B", textAlign: "left", textShadow: "none" }}>{textContent}</p>
              <span style={{ position: "absolute", left: 28, bottom: -9, width: 20, height: 20, background: panel, transform: "rotate(45deg)" }} />
            </div>
          </div>
        );
      }

      case "search_prompt": {
        const accent = cfg?.lineColor || "#22D3EE";
        return (
          <div className="absolute inset-0" style={{ backgroundColor: overlayBg, opacity: hookAlpha }}>
            <div style={{ position: "absolute", top: hookTop, left: "6%", right: "6%", transform: "translateY(-50%)", display: "grid", gridTemplateColumns: "36px 1fr 28px", alignItems: "center", gap: 10, padding: "14px 18px", borderRadius: 999, background: cfg?.boxColor || "#0F172A", border: `1px solid ${accent}66` }}>
              <span style={{ color: accent, fontSize: 24 }}>⌕</span>
              <p style={{ ...baseTextStyle, color, textAlign: "left", textShadow: textShadowParts.join(", ") }}>{textContent}</p>
              <span style={{ color: accent, fontSize: 20 }}>↗</span>
            </div>
          </div>
        );
      }

      case "countdown_list": {
        const accent = cfg?.boxColor || "#FACC15";
        const ink = cfg?.lineColor || "#111827";
        return (
          <div className="absolute inset-0" style={{ backgroundColor: overlayBg, opacity: hookAlpha }}>
            <div style={{ position: "absolute", top: hookTop, left: "7%", right: "7%", transform: "translateY(-50%)", display: "grid", gridTemplateColumns: "82px 1fr", overflow: "hidden", borderRadius: 16, border: `4px solid ${ink}`, boxShadow: `8px 8px 0 ${ink}` }}>
              <span style={{ display: "grid", placeItems: "center", background: accent, color: ink, fontSize: 38, fontWeight: 1000 }}>{cfg?.badgeText || "03"}</span>
              <p style={{ ...baseTextStyle, color: cfg?.color || ink, background: "#F8FAFC", padding: "18px", textAlign: "left", textShadow: "none" }}>{textContent}</p>
            </div>
          </div>
        );
      }

      case "pov_stamp": {
        const accent = cfg?.boxColor || "#FB7185";
        return (
          <div className="absolute inset-0" style={{ backgroundColor: overlayBg, opacity: hookAlpha }}>
            <div style={{ position: "absolute", top: hookTop, left: "8%", right: "8%", transform: "translateY(-50%) rotate(-2deg)" }}>
              <span style={{ display: "inline-block", marginBottom: 8, padding: "6px 12px", borderRadius: 7, background: accent, color: "#FFFFFF", fontSize: 13, fontWeight: 1000 }}>{cfg?.badgeText || "POV"}</span>
              <p style={{ ...baseTextStyle, color, padding: "16px 18px", borderRadius: 10, border: `2px solid ${accent}`, background: "rgba(18,7,12,.8)", textAlign: "left", textShadow: textShadowParts.join(", ") }}>{textContent}</p>
            </div>
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

      case "bold_slam": {
        const entrance = Math.min(1, t / 0.3);
        const shakeX = t > 0.5 && t < 0.9 ? Math.sin(t * 60) * 3 : 0;
        const shakeY = t > 0.5 && t < 0.9 ? Math.cos(t * 50) * 3 : 0;
        const rotate = Math.max(-8 * (1 - Math.min(1, t / 0.35)), 0);
        const boldSlamStroke = "#16130B";
        return (
          <div className="absolute inset-0 flex items-center justify-center" style={{ opacity: hookAlpha }}>
            <div
              style={{
                transform: `translate(${shakeX}px, ${shakeY}px) scale(${entrance}) rotate(${-rotate}deg)`,
                background: cfg?.boxColor || "#FFE600",
                padding: "20px 36px",
                borderRadius: 16,
                border: `5px solid ${boldSlamStroke}`,
                boxShadow: `8px 8px 0px ${boldSlamStroke}`,
              }}
            >
              <div
                style={{
                  fontFamily: "'Arial Black', Impact, sans-serif",
                  fontWeight: 900,
                  fontSize: Math.min(fontSize || 48, 36),
                  lineHeight: 1.15,
                  color: cfg?.color || "#16130B",
                  textAlign: "center" as const,
                  textTransform: "uppercase" as const,
                }}
              >
                {textContent}
              </div>
            </div>
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
    const posStyle: React.CSSProperties = typeof cfg?.positionY === "number"
      ? { top: `${cfg.positionY}%`, bottom: "auto", transform: "translateY(-50%)" }
      : position === "top"
        ? { top: "8%", bottom: "auto" }
        : position === "center"
          ? { top: "50%", bottom: "auto", transform: "translateY(-50%)" }
          : { bottom: "12%" };

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

            if (!isRevealed) return null;

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
