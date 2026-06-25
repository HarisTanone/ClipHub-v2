import { useMemo } from "react";
import { cn } from "@/lib/utils";

/**
 * VideoPreviewOverlay - renders a live HTML/CSS simulation of hook text
 * and subtitle words synced to currentTime.
 *
 * This previews what the final rendered clip will look like without
 * requiring a backend re-encode.
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
  words: Word[];
  showHook: boolean;
  showSubtitles: boolean;
  hookDuration?: number;
}

const HOOK_STYLES: Record<string, { color: string; fontSize: string; fontWeight: string; bg: string; animation: string }> = {
  zoom_punch: { color: "#FFFFFF", fontSize: "clamp(18px, 5vw, 32px)", fontWeight: "800", bg: "rgba(0,0,0,0.6)", animation: "scale" },
  fade_scale: { color: "#FFFFFF", fontSize: "clamp(16px, 4.5vw, 28px)", fontWeight: "700", bg: "rgba(0,0,0,0.5)", animation: "fade" },
  slide_punch_framer: { color: "#FFFFFF", fontSize: "clamp(17px, 4.8vw, 30px)", fontWeight: "700", bg: "rgba(0,0,0,0.65)", animation: "slide" },
  typewriter: { color: "#00FF88", fontSize: "clamp(14px, 4vw, 24px)", fontWeight: "700", bg: "rgba(0,0,0,0.7)", animation: "typewriter" },
};

export function VideoPreviewOverlay({
  currentTime,
  hookText,
  hookStyle,
  words,
  showHook,
  showSubtitles,
  hookDuration = 3.0,
}: PreviewOverlayProps) {
  const style = HOOK_STYLES[hookStyle] || HOOK_STYLES.zoom_punch;
  const subtitleOffset = hookDuration; // subtitles start after hook ends

  // Hook visibility
  const hookVisible = showHook && currentTime < hookDuration && hookText;

  // Hook opacity (fade in/out)
  const hookOpacity = useMemo(() => {
    if (!hookVisible) return 0;
    if (currentTime < 0.5) return currentTime / 0.5;
    if (currentTime > hookDuration - 0.5) return (hookDuration - currentTime) / 0.5;
    return 1;
  }, [currentTime, hookVisible, hookDuration]);

  // Hook scale for zoom_punch
  const hookScale = useMemo(() => {
    if (style.animation !== "scale") return 1;
    if (currentTime < 0.3) return 0.85 + (currentTime / 0.3) * 0.15;
    return 1;
  }, [currentTime, style.animation]);

  // Current subtitle words (show 3 words at a time after hookDuration)
  const visibleWords = useMemo(() => {
    if (!showSubtitles || !words.length) return [];
    return words.filter((w) => {
      const adjustedStart = w.start + subtitleOffset;
      const adjustedEnd = w.end + subtitleOffset;
      return currentTime >= adjustedStart - 0.1 && currentTime <= adjustedEnd + 0.8;
    }).slice(0, 4);
  }, [currentTime, words, showSubtitles, subtitleOffset]);

  // Typewriter effect
  const typewriterText = useMemo(() => {
    if (style.animation !== "typewriter" || !hookVisible) return hookText;
    const charsPerSec = hookText.length / (hookDuration - 0.5);
    const charsVisible = Math.min(Math.floor(currentTime * charsPerSec), hookText.length);
    return hookText.slice(0, charsVisible);
  }, [currentTime, hookText, hookVisible, hookDuration, style.animation]);

  // Find active word for highlight
  const activeWordIdx = useMemo(() => {
    if (!visibleWords.length) return -1;
    return visibleWords.findIndex((w) => {
      const s = w.start + subtitleOffset;
      const e = w.end + subtitleOffset;
      return currentTime >= s && currentTime <= e;
    });
  }, [currentTime, visibleWords, subtitleOffset]);

  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden">
      {/* Hook overlay */}
      {hookVisible && (
        <div
          className="absolute inset-0 flex items-center justify-center px-6 transition-none"
          style={{ backgroundColor: style.bg, opacity: hookOpacity }}
        >
          <p
            className="text-center leading-tight max-w-[85%]"
            style={{
              color: style.color,
              fontSize: style.fontSize,
              fontWeight: style.fontWeight,
              transform: `scale(${hookScale})`,
              fontFamily: "'Inter', sans-serif",
              textShadow: "0 2px 8px rgba(0,0,0,0.7)",
            }}
          >
            {style.animation === "typewriter" ? typewriterText : hookText}
            {style.animation === "typewriter" && (
              <span className="animate-pulse ml-0.5 opacity-70">|</span>
            )}
          </p>
        </div>
      )}

      {/* Subtitle overlay */}
      {visibleWords.length > 0 && currentTime >= subtitleOffset && (
        <div className="absolute bottom-[12%] left-0 right-0 flex justify-center px-4">
          <div className="flex flex-wrap justify-center gap-1.5 max-w-[90%] bg-black/40 rounded-lg px-3 py-2">
            {visibleWords.map((w, i) => (
              <span
                key={`${w.word}-${i}`}
                className="text-sm font-bold px-0.5"
                style={{
                  color: i === activeWordIdx ? "#FFCC00" : "#FFFFFF",
                  transform: i === activeWordIdx ? "scale(1.1)" : "scale(1)",
                  textShadow: "0 1px 4px rgba(0,0,0,0.8)",
                  fontFamily: "'Inter', sans-serif",
                  transition: "color 0.1s, transform 0.1s",
                }}
              >
                {w.word}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Timeline indicator */}
      <div className="absolute top-2 left-2 flex items-center gap-1.5">
        {hookVisible && (
          <span className="bg-emerald-500/80 text-[9px] text-white font-medium px-1.5 py-0.5 rounded">
            HOOK
          </span>
        )}
        {visibleWords.length > 0 && currentTime >= subtitleOffset && (
          <span className="bg-blue-500/80 text-[9px] text-white font-medium px-1.5 py-0.5 rounded">
            SUB
          </span>
        )}
      </div>
    </div>
  );
}
