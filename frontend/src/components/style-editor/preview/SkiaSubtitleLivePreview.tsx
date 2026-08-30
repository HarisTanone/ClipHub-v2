import React from "react";
import { Palette } from "lucide-react";
import type { CanvasConfig } from "@/lib/canvasTemplates";
import { SKIA_SUBTITLE_PRESETS } from "@/lib/renderEngines";
import type { SubtitleStyle } from "../types";
import { useGoogleFont } from "../utils";
import { CanvasPreviewFrame } from "./CanvasPreviewFrame";

export function SkiaSubtitleLivePreview({
  style,
  thumbnailUrl,
  activeWordIdx,
  canvas,
}: {
  style: SubtitleStyle;
  thumbnailUrl?: string;
  activeWordIdx: number;
  canvas?: CanvasConfig | null;
}) {
  const presetId = style.stylePreset || "clean_editorial";
  const preset = SKIA_SUBTITLE_PRESETS.find((p) => p.id === presetId) || SKIA_SUBTITLE_PRESETS[0];
  const posTop = style.position === "top"
    ? `${style.positionY != null && style.positionY <= 35 ? style.positionY : 15}%`
    : style.position === "center"
      ? `${style.positionY != null && style.positionY > 35 && style.positionY < 65 ? style.positionY : 50}%`
      : `${style.positionY != null && style.positionY >= 65 ? style.positionY : 82}%`;
  const sampleWords = ["ini", "kata", "penting", "banget", "untuk", "kamu"];
  const count = Math.max(1, Math.min(6, style.maxWordsPerLine || 4));
  const words = sampleWords.slice(0, count);

  // Ensure all preset Google Fonts are available in the DOM
  useGoogleFont(style.fontFamily || "Inter");
  useGoogleFont("Inter");
  useGoogleFont("Plus Jakarta Sans");
  useGoogleFont("Montserrat");
  useGoogleFont("Poppins");
  useGoogleFont("Playfair Display");
  useGoogleFont("Space Grotesk");
  useGoogleFont("Anton");
  useGoogleFont("Outfit");
  useGoogleFont("Bebas Neue");
  useGoogleFont("Archivo Black");

  return (
    <>
      <div className="mb-3 flex w-full items-center justify-between gap-2">
        <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
        <span className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[9px] text-amber-300">
          <Palette className="inline w-3 h-3 mr-1" />Skia Canvas GPU
        </span>
      </div>
      <CanvasPreviewFrame canvas={canvas || null} thumbnailUrl={thumbnailUrl} dimOverlay>
        <div className="absolute left-0 right-0 flex justify-center px-3 pointer-events-none" style={{ top: posTop, transform: "translateY(-50%)" }}>
          {(() => {
            const isWordPop = style.lineTransition === "word_pop";
            const isLineReveal = style.lineTransition === "line_reveal";
            const displayWords = isWordPop ? [words[activeWordIdx % words.length]] : words;

            // Card / Capsule background styles
            const hasBg = style.bgEnabled || presetId === "glassmorphism" || presetId === "clean_editorial" || presetId === "podcast_pro" || presetId === "modern_mono";
            const bgOpacity = style.bgOpacity ?? (presetId === "glassmorphism" ? 0.25 : 0.75);
            const bgHex = style.bgColor || (presetId === "podcast_pro" ? "#121216" : presetId === "modern_mono" ? "#080c14" : presetId === "clean_editorial" ? "#0f172a" : "#1e293b");
            const bgAlpha = Math.round(Math.max(0, Math.min(1, bgOpacity)) * 255).toString(16).padStart(2, "0");
            const bgRadius = style.bgRadius ?? (presetId === "podcast_pro" ? 999 : presetId === "glassmorphism" ? 16 : 12);
            const bgPadding = style.bgPadding ?? 16;

            const containerStyle: React.CSSProperties = {
              display: "flex",
              flexWrap: isWordPop ? "nowrap" : "wrap",
              alignItems: "center",
              justifyContent: "center",
              maxWidth: "94%",
              gap: isWordPop ? 0 : Math.max(3, (style.wordSpacing ?? 6) * 0.6),
              ...(hasBg ? {
                backgroundColor: presetId === "glassmorphism" ? undefined : `${bgHex}${bgAlpha}`,
                background: presetId === "glassmorphism"
                  ? `linear-gradient(135deg, rgba(255, 255, 255, ${bgOpacity}) 0%, rgba(255, 255, 255, ${bgOpacity * 0.3}) 100%)`
                  : undefined,
                backdropFilter: "blur(12px)",
                WebkitBackdropFilter: "blur(12px)",
                border: presetId === "glassmorphism"
                  ? "1.5px solid rgba(255, 255, 255, 0.55)"
                  : presetId === "podcast_pro"
                    ? "1.5px solid rgba(16, 185, 129, 0.5)"
                    : presetId === "modern_mono"
                      ? "1.5px solid #06B6D4"
                      : "1px solid rgba(255, 255, 255, 0.12)",
                boxShadow: presetId === "glassmorphism"
                  ? "0 8px 32px 0 rgba(0, 0, 0, 0.45), inset 0 0 12px rgba(255, 255, 255, 0.25)"
                  : presetId === "podcast_pro"
                    ? "0 0 16px rgba(16, 185, 129, 0.35)"
                    : presetId === "modern_mono"
                      ? "0 0 16px rgba(6, 182, 212, 0.35)"
                      : "0 8px 24px rgba(0,0,0,0.5)",
                borderRadius: `${bgRadius}px`,
                padding: `${Math.round(bgPadding * 0.35)}px ${Math.round(bgPadding * 0.65)}px`,
              } : {}),
              ...(isLineReveal ? {
                borderLeft: `3px solid ${style.highlightColor || "#38BDF8"}`,
              } : {}),
              ...(presetId === "cinematic_slate" ? {
                borderTop: "1.5px solid rgba(252, 211, 77, 0.6)",
                borderBottom: "1.5px solid rgba(252, 211, 77, 0.6)",
                padding: "6px 14px",
              } : {}),
            };

            return (
              <div style={containerStyle}>
                {presetId === "podcast_pro" && (
                  <div className="flex items-center gap-1 shrink-0 mr-1">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_#10B981]" />
                    <span className="text-[7px] font-bold text-emerald-400 tracking-wider">MIC</span>
                  </div>
                )}
                {presetId === "modern_mono" && (
                  <div className="flex items-center gap-1 w-full border-b border-cyan-500/30 pb-1 mb-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                    <span className="w-1.5 h-1.5 rounded-full bg-yellow-500" />
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                    <span className="text-[7px] text-cyan-400 font-mono ml-1 font-bold">TERMINAL v2.0</span>
                  </div>
                )}
                {displayWords.map((w, i) => {
                  const isActive = isWordPop ? true : (i === activeWordIdx % words.length);
                  const isKeyword = style.highlightWords?.includes(w.toLowerCase());
                  const shouldHighlight = isActive || isKeyword;

                  const fontSize = Math.min(Math.max((style.fontSize || 42) * 0.23, 10), 17);
                  const fontWeight = shouldHighlight
                    ? (style.highlightBold !== false ? 900 : Number(style.fontWeight || 700))
                    : Number(style.fontWeight || 600);

                  // Colors & Gradients
                  const gradActive = style.gradientEnabled
                    ? `linear-gradient(135deg, ${style.gradientFrom || "#667EEA"} 0%, ${style.gradientTo || "#764BA2"} 100%)`
                    : presetId === "retro_chrome"
                      ? "linear-gradient(180deg, #FFF9C4 0%, #FFFFFF 35%, #F57F17 50%, #FFD54F 60%, #E65100 100%)"
                      : null;

                  const gradInactive = style.gradientEnabled
                    ? `linear-gradient(135deg, ${style.gradientFrom || "#667EEA"}80 0%, ${style.gradientTo || "#764BA2"}80 100%)`
                    : presetId === "retro_chrome"
                      ? "linear-gradient(180deg, #E0E0E0 0%, #FFFFFF 40%, #757575 50%, #BDBDBD 60%, #424242 100%)"
                      : null;

                  const grad = shouldHighlight ? gradActive : gradInactive;

                  // Text shadows & Glow
                  const glowColor = style.glowColor || style.highlightColor || "#00FFFF";
                  const shadowParts: string[] = [];
                  if (shouldHighlight && style.glowEnabled) {
                    shadowParts.push(`0 0 10px ${glowColor}`, `0 0 20px ${glowColor}B3`);
                  } else if (shouldHighlight && (presetId === "neon_tube" || presetId === "glassmorphism")) {
                    shadowParts.push(`0 0 10px ${style.highlightColor || "#38BDF8"}`);
                  } else if (style.shadowEnabled) {
                    shadowParts.push(`0 0 ${style.shadowBlur || 8}px ${style.shadowColor || "#000000"}`);
                  } else {
                    shadowParts.push("0 2px 6px rgba(0,0,0,0.8)");
                  }

                  // Active scale
                  const scaleVal = shouldHighlight && (style.highlightBold !== false || isWordPop)
                    ? (style.highlightScale || 1.15)
                    : 1.0;

                  // Stroke / Outline
                  const strokeWidth = style.strokeEnabled ? (style.strokeWidth || 3) * 0.25 : 0;
                  const strokeColor = style.strokeColor || "#000000";

                  const wordStyle: React.CSSProperties = {
                    fontFamily: `'${style.fontFamily || "Inter"}', sans-serif`,
                    fontSize: fontSize,
                    fontWeight: fontWeight,
                    letterSpacing: `${style.letterSpacing || 0}px`,
                    textTransform: style.uppercase ? "uppercase" : style.capitalize ? "capitalize" : "none",
                    fontStyle: style.italic ? "italic" : "normal",
                    transform: `scale(${scaleVal})`,
                    transition: "transform 0.15s ease, color 0.15s ease",
                    display: "inline-block",
                    wordBreak: "break-word",
                    textShadow: shadowParts.join(", ") || undefined,
                    ...(grad ? {
                      background: grad,
                      WebkitBackgroundClip: "text",
                      WebkitTextFillColor: "transparent",
                    } : {
                      color: shouldHighlight ? (style.highlightColor || "#38BDF8") : (style.color || "#FFFFFF"),
                    }),
                    ...(strokeWidth > 0 ? {
                      WebkitTextStroke: `${strokeWidth}px ${strokeColor}`,
                      paintOrder: "stroke fill",
                    } : {}),
                    ...(presetId === "kinetic_word_box" && shouldHighlight ? {
                      backgroundColor: style.highlightColor || "#FF0055",
                      color: "#FFFFFF",
                      WebkitTextFillColor: "#FFFFFF",
                      borderRadius: "6px",
                      padding: "2px 6px",
                      boxShadow: `0 4px 14px ${style.highlightColor || "#FF0055"}B3`,
                    } : {}),
                    ...(presetId === "clean_editorial" && shouldHighlight ? {
                      borderBottom: `2.5px solid ${style.highlightColor || "#38BDF8"}`,
                      paddingBottom: 2,
                    } : {}),
                  };

                  return (
                    <span key={`${w}-${i}`} style={wordStyle}>
                      {w}
                      {presetId === "modern_mono" && shouldHighlight && <span className="animate-pulse text-cyan-400 ml-0.5">_</span>}
                    </span>
                  );
                })}
              </div>
            );
          })()}
        </div>
        <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-500 z-10">
          skia gpu · {preset.name}
        </p>
      </CanvasPreviewFrame>
      <div className="mt-3 grid w-full grid-cols-2 gap-2 text-[10px]">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2">
          <span className="text-zinc-600">Font</span>
          <p className="truncate text-zinc-300">{style.fontFamily}</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2">
          <span className="text-zinc-600">Preset</span>
          <p className="truncate text-amber-400">{preset.name}</p>
        </div>
      </div>
    </>
  );
}
