import React from "react";
import { Quote } from "lucide-react";
import { cn } from "@/lib/utils";
import type { HookStyle } from "../types";
import { getHookPreviewSample } from "../utils";

export function HookPreviewRenderer({
  style,
  customText,
  scale = 1.0,
}: {
  style: HookStyle;
  customText?: string;
  scale?: number;
}) {
  const text = customText || style.text || getHookPreviewSample(style.animation);
  const fontSize = Math.max(style.fontSize * 0.32 * scale, 10);
  const fontFamily = style.fontFamily === "monospace" ? "monospace" : `'${style.fontFamily}', sans-serif`;
  const fontWeight = Number(style.fontWeight);
  const fontStyle = style.italic ? ("italic" as const) : ("normal" as const);

  const baseTextStyle: React.CSSProperties = {
    fontSize,
    fontWeight,
    fontFamily,
    fontStyle,
    letterSpacing: style.letterSpacing,
    lineHeight: style.lineHeight,
    textTransform: style.uppercase ? "uppercase" : "none",
    textAlign: style.textAlign,
    maxWidth: "90%",
    whiteSpace: "pre-line",
    wordBreak: "break-word",
    paintOrder: style.strokeEnabled ? "stroke" : undefined,
    WebkitTextStroke: style.strokeEnabled ? `${Math.max(style.strokeWidth * 0.32, 0.7)}px ${style.strokeColor}` : undefined,
  };

  const textShadow = [
    style.shadowEnabled ? `${style.shadowX}px ${style.shadowY}px ${style.shadowBlur}px ${style.shadowColor}` : "",
    style.glowEnabled ? `0 0 ${style.glowSize}px ${style.glowColor}` : "",
  ].filter(Boolean).join(", ") || undefined;

  const colorStyle: React.CSSProperties = style.gradientEnabled
    ? { background: `linear-gradient(${style.gradientAngle}deg, ${style.gradientFrom}, ${style.gradientTo})`, WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }
    : { color: style.color };

  const boxStyle: React.CSSProperties = style.boxEnabled
    ? { backgroundColor: `${style.boxColor}${Math.round(style.boxOpacity * 255).toString(16).padStart(2, "0")}`, padding: style.boxPadding * 0.4, borderRadius: style.boxRadius }
    : {};

  const posTop = `${style.positionY}%`;

  switch (style.animation) {
    case "paper_clip_scrap": {
      const cardBg = style.boxColor || "#FEF08A";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{
              position: "relative",
              background: cardBg,
              borderRadius: 14,
              padding: "24px 20px 18px 20px",
              boxShadow: "0 18px 40px rgba(0,0,0,0.5)",
              transform: "rotate(-2.5deg)",
            }}>
              {/* Washi tape top-right */}
              <div style={{
                position: "absolute",
                top: -8,
                right: 18,
                width: 44,
                height: 16,
                backgroundColor: "rgba(255, 255, 255, 0.7)",
                border: "1px solid rgba(200, 200, 200, 0.5)",
                transform: "rotate(12deg)",
              }} />

              {/* Realistic SVG Paper Clip top-left */}
              <div style={{
                position: "absolute",
                top: -14,
                left: 18,
                width: 22,
                height: 48,
                zIndex: 10,
                filter: "drop-shadow(1px 3px 3px rgba(0,0,0,0.4))",
              }}>
                <svg viewBox="0 0 38 90" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ width: "100%", height: "100%" }}>
                  <path
                    d="M12 28 V70 C12 76 17 81 23 81 C29 81 34 76 34 70 V18 C34 9 27 2 18 2 C9 2 2 9 2 18 V74"
                    stroke="#475569"
                    strokeWidth="5"
                    strokeLinecap="round"
                  />
                  <path
                    d="M12 28 V70 C12 76 17 81 23 81 C29 81 34 76 34 70 V18 C34 9 27 2 18 2 C9 2 2 9 2 18 V74"
                    stroke="#E2E8F0"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                  />
                </svg>
              </div>

              <p style={{
                ...baseTextStyle,
                color: style.color || "#1C1917",
                fontSize: Math.max(fontSize * 0.78, 12),
                fontWeight: 900,
                textAlign: "center",
                lineHeight: 1.2,
              }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "trending_radar": {
      const magenta = style.lineColor || "#D946EF";
      const cyan = "#06B6D4";
      const badgeTitle = style.badgeText || "TRENDING NOW";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{
              position: "relative",
              background: "rgba(9, 5, 20, 0.94)",
              borderRadius: 14,
              padding: "24px 18px 18px 18px",
              border: `1.5px solid ${magenta}`,
              boxShadow: `0 18px 40px rgba(0,0,0,0.6), 0 0 16px ${magenta}66`,
            }}>
              {/* Corner HUD Crosshairs */}
              <div style={{ position: "absolute", top: 4, left: 4, width: 8, height: 8, borderTop: `2px solid ${cyan}`, borderLeft: `2px solid ${cyan}` }} />
              <div style={{ position: "absolute", top: 4, right: 4, width: 8, height: 8, borderTop: `2px solid ${cyan}`, borderRight: `2px solid ${cyan}` }} />
              <div style={{ position: "absolute", bottom: 4, left: 4, width: 8, height: 8, borderBottom: `2px solid ${cyan}`, borderLeft: `2px solid ${cyan}` }} />
              <div style={{ position: "absolute", bottom: 4, right: 4, width: 8, height: 8, borderBottom: `2px solid ${cyan}`, borderRight: `2px solid ${cyan}` }} />

              {/* Top Badge: TRENDING NOW */}
              <div style={{
                position: "absolute",
                top: -12,
                left: "50%",
                transform: "translateX(-50%)",
                backgroundColor: magenta,
                color: "#FFFFFF",
                padding: "3px 12px",
                borderRadius: 999,
                fontSize: 9,
                fontWeight: 900,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                display: "flex",
                alignItems: "center",
                gap: 5,
                boxShadow: `0 4px 12px ${magenta}88`,
              }}>
                <span style={{ width: 6, height: 6, borderRadius: 999, backgroundColor: "#FFFFFF" }} />
                <span>{badgeTitle}</span>
              </div>

              <p style={{
                ...baseTextStyle,
                color: style.color || "#FFFFFF",
                fontSize: Math.max(fontSize * 0.78, 12),
                fontWeight: 900,
                textAlign: "center",
                lineHeight: 1.2,
                marginTop: 4,
              }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "news_breaking_live": {
      const red = style.lineColor || "#DC2626";
      const badgeTitle = style.badgeText || "BREAKING NEWS";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{
              position: "relative",
              borderRadius: 12,
              overflow: "hidden",
              backgroundColor: "rgba(15, 23, 42, 0.95)",
              border: "1px solid rgba(255,255,255,0.15)",
              boxShadow: "0 18px 40px rgba(0,0,0,0.6)",
            }}>
              {/* Header */}
              <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "6px 12px",
                borderBottom: "1px solid rgba(255,255,255,0.1)",
                backgroundColor: "rgba(0,0,0,0.3)",
              }}>
                <div style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 5,
                  backgroundColor: red,
                  color: "#FFFFFF",
                  padding: "2px 8px",
                  borderRadius: 4,
                  fontSize: 9,
                  fontWeight: 900,
                  textTransform: "uppercase",
                }}>
                  <span style={{ width: 6, height: 6, borderRadius: 999, backgroundColor: "#FFFFFF" }} />
                  <span>{badgeTitle}</span>
                </div>
                <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 8, fontWeight: 800 }}>LIVE</span>
              </div>

              {/* Text */}
              <p style={{
                ...baseTextStyle,
                padding: "12px 14px",
                color: style.color || "#FFFFFF",
                fontSize: Math.max(fontSize * 0.76, 12),
                fontWeight: 900,
                textAlign: "left",
                lineHeight: 1.2,
              }}>{text}</p>

              {/* Bottom Red Accent */}
              <div style={{ height: 3, backgroundColor: red }} />
            </div>
          </div>
        </>
      );
    }

    case "news_viralin_badge": {
      const cardBg = style.boxColor || "#EAB308";
      const badgeBg = style.lineColor || "#1D4ED8";
      const badgeTitle = style.badgeText || "#VIRALIN";
      const badgeSub = (style as any).badgeSubText || "";
      const showBadge = style.badgeEnabled !== false;
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {/* White paper rotated card behind */}
            <div style={{ position: "absolute", inset: -4, background: "#FFFFFF", transform: "rotate(-3deg)", borderRadius: 8, boxShadow: "0 14px 30px rgba(0,0,0,0.45)" }} />
            {/* Main yellow card */}
            <div style={{ position: "relative", background: cardBg, padding: "28px 20px 20px 20px", borderRadius: 8, boxShadow: "0 16px 36px rgba(0,0,0,0.5)" }}>
              {/* Tilted Blue Badge */}
              {showBadge && (
                <div style={{ position: "absolute", top: -20, left: "50%", transform: "translateX(-50%) rotate(-3.5deg)", background: badgeBg, borderRadius: 6, padding: "4px 14px", boxShadow: "0 6px 16px rgba(0,0,0,0.4)", border: "1.5px solid rgba(255,255,255,0.2)", display: "flex", flexDirection: "column", alignItems: "center" }}>
                  <span style={{ color: "#FACC15", fontFamily: "'Montserrat', sans-serif", fontWeight: 900, fontSize: 13, fontStyle: "italic", lineHeight: 1.1, textTransform: "uppercase" }}>{badgeTitle}</span>
                  {badgeSub ? <span style={{ color: "#FFFFFF", fontFamily: "'Inter', sans-serif", fontWeight: 700, fontSize: 8, lineHeight: 1 }}>{badgeSub}</span> : null}
                </div>
              )}
              <p style={{ ...baseTextStyle, color: style.color || "#09090B", fontSize: Math.max(fontSize * 0.78, 12), fontWeight: 900, textAlign: "center", lineHeight: 1.2, marginTop: showBadge ? 4 : 0 }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "news_portal_pantau": {
      const cardBg = style.boxColor || "#FFFFFF";
      const accentColor = style.lineColor || "#DC2626";
      const categoryTag = style.badgeText || "INTERNASIONAL";
      const footerLabel = style.footerText || "READ MORE AT chatgpt.com";
      const showBadge = style.badgeEnabled !== false;
      const showFooter = style.footerEnabled !== false;
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ position: "relative", background: cardBg, borderRadius: "10px 10px 0 0", padding: "18px 18px 14px 18px", boxShadow: "0 18px 40px rgba(0,0,0,0.5)", borderBottom: `4px solid ${accentColor}` }}>
              {showBadge && (
                <div style={{ display: "inline-block", background: accentColor, color: "#FFFFFF", fontFamily: "'Inter', sans-serif", fontWeight: 900, fontSize: 10, letterSpacing: "0.05em", textTransform: "uppercase", padding: "3px 8px", borderRadius: 3, marginBottom: 8 }}>{categoryTag}</div>
              )}
              <p style={{ ...baseTextStyle, color: style.color || "#09090B", fontSize: Math.max(fontSize * 0.76, 12), fontWeight: 900, textAlign: "left", lineHeight: 1.18, textTransform: "uppercase" }}>{text}</p>
              {showFooter && (
                <div style={{ marginTop: 10, paddingTop: 6, borderTop: "1px solid rgba(0,0,0,0.08)", color: "#71717A", fontSize: 8, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.08em" }}>{footerLabel}</div>
              )}
              {/* Bottom speech notch */}
              <div style={{ position: "absolute", bottom: -12, right: 28, width: 0, height: 0, borderLeft: "10px solid transparent", borderRight: "10px solid transparent", borderTop: `12px solid ${accentColor}` }} />
            </div>
          </div>
        </>
      );
    }

    case "news_offset_box": {
      const cardBg = style.boxColor || "#DC2626";
      const offsetColor = style.lineColor || "#FFFFFF";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-5 right-5" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {/* White offset border sticking out top-left */}
            <div style={{ position: "absolute", top: -8, left: -8, width: "65%", height: "80%", borderTop: `3px solid ${offsetColor}`, borderLeft: `3px solid ${offsetColor}` }} />
            {/* Main red box */}
            <div style={{ position: "relative", background: cardBg, padding: "18px 18px", boxShadow: "0 16px 36px rgba(0,0,0,0.5)" }}>
              <p style={{ ...baseTextStyle, color: style.color || "#FFFFFF", fontSize: Math.max(fontSize * 0.78, 12), fontWeight: 900, textAlign: "center", lineHeight: 1.22 }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "brutalist_bracket": {
      const cardBg = style.boxColor || "#FFFFFF";
      const bracketColor = style.lineColor || "#000000";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-5 right-5" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {/* Left bracket */}
            <div style={{ position: "absolute", top: -10, left: -10, bottom: -10, width: 24, borderTop: `5px solid ${bracketColor}`, borderLeft: `5px solid ${bracketColor}`, borderBottom: `5px solid ${bracketColor}` }} />
            <div style={{ position: "relative", background: cardBg, padding: "18px 20px", boxShadow: "0 16px 36px rgba(0,0,0,0.5)" }}>
              <p style={{ ...baseTextStyle, color: style.color || "#09090B", fontSize: Math.max(fontSize * 0.78, 12), fontWeight: 900, textAlign: "left", lineHeight: 1.2 }}>
                {text.split(/(!!+|!\s*!)/g).map((part, idx) => {
                  if (part.includes("!")) return <span key={idx} style={{ color: "#EF4444", fontWeight: 900 }}> {part}</span>;
                  return <span key={idx}>{part}</span>;
                })}
              </p>
            </div>
          </div>
        </>
      );
    }

    case "quote_strip_tape": {
      const quoteBg = style.lineColor || "#0D9488";
      const tapeBg = style.boxColor || "#FFFFFF";
      const words = text.split(/\s+/).filter(Boolean);
      const lines: string[] = [];
      let cur = "";
      for (const w of words) {
        if ((cur + " " + w).trim().split(" ").length > 3) {
          lines.push(cur);
          cur = w;
        } else {
          cur = cur ? `${cur} ${w}` : w;
        }
      }
      if (cur) lines.push(cur);
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-5 right-5 flex flex-col items-start" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ background: quoteBg, color: "#FFFFFF", borderRadius: 3, padding: "4px 6px", marginBottom: 6, display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
              <Quote className="w-3.5 h-3.5 fill-current" />
            </div>
            <div className="flex flex-col items-start gap-1.5">
              {lines.map((line, lIdx) => (
                <span key={lIdx} style={{ background: tapeBg, color: style.color || "#09090B", padding: "4px 12px", fontFamily, fontSize: Math.max(fontSize * 0.72, 11), fontWeight: 900, textTransform: "uppercase", letterSpacing: "0.04em", boxShadow: "0 6px 16px rgba(0,0,0,0.4)" }}>
                  {line}
                </span>
              ))}
            </div>
          </div>
        </>
      );
    }

    case "podcast_lower_third": {
      const accent = style.lineColor || "#16F2B3";
      const showBadge = style.badgeEnabled !== false;
      const badgeLabel = style.badgeText || "ON AIR";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-3 right-3 animate-[podcastLowerPreview_2.8s_ease-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{
              display: "grid",
              gridTemplateColumns: showBadge ? "auto 1fr" : "1fr",
              gap: 8,
              alignItems: "center",
              background: "linear-gradient(90deg, rgba(6,17,31,0.94), rgba(20,28,44,0.78))",
              border: `1px solid ${accent}55`,
              borderLeft: `5px solid ${accent}`,
              borderRadius: 12,
              boxShadow: `0 12px 30px rgba(0,0,0,0.35), 0 0 18px ${accent}33`,
              padding: "10px 12px",
            }}>
              {showBadge && (
                <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "center" }}>
                  <span style={{ width: 8, height: 8, borderRadius: 99, background: accent, boxShadow: `0 0 12px ${accent}`, animation: "podcastOnAirPulse_1s ease-in-out infinite" }} />
                  <span style={{ color: accent, fontSize: 8, fontWeight: 900, letterSpacing: 0 }}>{badgeLabel}</span>
                </div>
              )}
              <p style={{ ...baseTextStyle, color: style.color, fontSize: Math.max(fontSize * 0.86, 12), textAlign: "left", lineHeight: 1.02, textShadow }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "quote_card": {
      const cardColor = `${style.boxColor}${Math.round((style.boxOpacity || 0.96) * 255).toString(16).padStart(2, "0")}`;
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4 animate-[quoteCardPreview_3s_ease-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{
              position: "relative",
              background: cardColor,
              borderRadius: 14,
              padding: "20px 18px 16px",
              boxShadow: "0 16px 30px rgba(0,0,0,0.38)",
              border: "1px solid rgba(255,255,255,0.72)",
            }}>
              <span style={{ position: "absolute", top: -13, left: 14, color: "#FF4D2D", fontSize: 36, fontFamily: "Georgia, serif", lineHeight: 1 }}>"</span>
              <p style={{ ...baseTextStyle, color: style.color || "#171717", fontSize: Math.max(fontSize * 0.82, 13), lineHeight: 1.12, textShadow: "none" }}>{text}</p>
              <div style={{ width: "38%", height: 3, background: "#FF4D2D", borderRadius: 99, margin: "10px auto 0" }} />
            </div>
          </div>
        </>
      );
    }

    case "waveform_pulse": {
      const bars = Array.from({ length: 13 });
      const waveColor = style.glowColor || style.color || "#14F1D9";
      const showBadge = style.badgeEnabled !== false;
      const badgeLabel = style.badgeText || "LIVE AUDIO";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-x-0 flex flex-col items-center justify-center gap-3 px-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {showBadge && (
              <span style={{ color: waveColor, fontSize: 8, fontWeight: 900, letterSpacing: 1, textTransform: "uppercase" }}>{badgeLabel}</span>
            )}
            <div style={{ display: "flex", gap: 4, height: 34, alignItems: "center" }}>
              {bars.map((_, i) => (
                <span key={i} style={{
                  width: 4,
                  height: 26 + (i % 4) * 6,
                  borderRadius: 99,
                  background: waveColor,
                  boxShadow: `0 0 12px ${waveColor}`,
                  transformOrigin: "center",
                  animation: `waveformBarPreview ${0.72 + (i % 3) * 0.14}s ease-in-out ${i * 0.04}s infinite`,
                }} />
              ))}
            </div>
            <p className="animate-[waveformTextPreview_1.1s_ease-in-out_infinite]" style={{ ...baseTextStyle, ...colorStyle, ...boxStyle, textShadow }}>{text}</p>
          </div>
        </>
      );
    }

    case "breaking_tape": {
      const tapeColor = style.boxColor || "#FFDD2D";
      const showBadge = style.badgeEnabled !== false;
      const badgeLabel = style.badgeText || "HOT TAKE";
      const badgeColor = style.lineColor || "#D71920";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-[-8%] right-[-8%] animate-[breakingTapePreview_2.5s_ease-out_infinite]" style={{ top: posTop, transform: "translateY(-50%) rotate(-4deg)" }}>
            <div style={{
              background: `linear-gradient(90deg, ${tapeColor}, #FFF06A, ${tapeColor})`,
              borderTop: "3px solid rgba(0,0,0,0.92)",
              borderBottom: "3px solid rgba(0,0,0,0.92)",
              boxShadow: "0 18px 28px rgba(0,0,0,0.32)",
              padding: "11px 28px",
              textAlign: "center",
            }}>
              {showBadge && (
                <span style={{ display: "block", color: badgeColor, fontSize: 8, fontWeight: 900, letterSpacing: 0, marginBottom: 2 }}>{badgeLabel}</span>
              )}
              <p style={{ ...baseTextStyle, color: style.color || "#111111", fontSize: Math.max(fontSize * 0.9, 14), lineHeight: 1, textShadow: "none" }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "mic_drop": {
      const accent = style.boxColor || style.gradientTo || "#FF4D7D";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-x-0 flex flex-col items-center justify-center px-4 animate-[micDropPreview_2.5s_cubic-bezier(.2,.85,.25,1)_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{
              position: "relative",
              borderRadius: 999,
              border: `3px solid ${accent}`,
              boxShadow: `0 0 26px ${accent}66, inset 0 0 18px rgba(255,255,255,0.08)`,
              padding: "18px 22px",
              background: "rgba(5,5,7,0.74)",
            }}>
              <span style={{ position: "absolute", left: "50%", bottom: -16, width: 46, height: 4, transform: "translateX(-50%)", borderRadius: 99, background: accent, boxShadow: `0 0 18px ${accent}` }} />
              <p style={{ ...baseTextStyle, ...colorStyle, textShadow, fontSize: Math.max(fontSize * 0.82, 14), lineHeight: 1.02 }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "split_panel": {
      const accent = style.lineColor || "#38BDF8";
      const panel = `${style.boxColor || "#0F172A"}${Math.round((style.boxOpacity || 0.86) * 255).toString(16).padStart(2, "0")}`;
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4 animate-[splitPanelPreview_2.6s_ease-in-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ display: "grid", gridTemplateColumns: style.badgeEnabled ? "48px 1fr" : "1fr", borderRadius: 12, overflow: "hidden", background: panel, boxShadow: `0 16px 32px rgba(0,0,0,0.34), 0 0 18px ${accent}33`, border: `1px solid ${accent}44` }}>
              {style.badgeEnabled && <div style={{ background: accent, color: "#06111F", display: "grid", placeItems: "center", fontSize: 8, fontWeight: 900, writingMode: "vertical-rl", textTransform: "uppercase", letterSpacing: 1 }}>{style.badgeText || "POINT"}</div>}
              <div style={{ padding: "16px 18px", position: "relative" }}>
                {style.decorativeElements && <span style={{ position: "absolute", left: 16, right: 16, bottom: 8, height: 2, borderRadius: 99, background: accent, opacity: 0.8 }} />}
                <p style={{ ...baseTextStyle, ...colorStyle, textShadow, fontSize: Math.max(fontSize * 0.9, 14), textAlign: "left" }}>{text}</p>
              </div>
            </div>
          </div>
        </>
      );
    }

    case "kinetic_stack": {
      const accent = style.boxColor || "#F97316";
      const words = text.split(/\s+/).filter(Boolean).slice(0, 5);
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-x-4 flex flex-col items-center gap-1.5 animate-[kineticStackPreview_2.4s_ease-in-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {words.map((word, i) => (
              <span key={`${word}-${i}`} style={{ ...baseTextStyle, color: style.color, background: i % 2 === 0 ? accent : "#F8FAFC", padding: "3px 12px", borderRadius: 5, boxShadow: `5px 5px 0 ${style.lineColor || "#111827"}`, transform: `translateX(${(i % 2 === 0 ? -1 : 1) * Math.min(24, 7 + i * 4)}px) rotate(${i % 2 === 0 ? -1.5 : 1.5}deg)`, fontSize: Math.max(fontSize * 0.82, 14), lineHeight: 1 }}>
                {word}
              </span>
            ))}
          </div>
        </>
      );
    }

    case "glass_flash": {
      const accent = style.lineColor || "#C084FC";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4 animate-[glassFlashPreview_2.8s_ease-in-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ position: "relative", overflow: "hidden", borderRadius: 18, padding: "22px 18px", background: `${style.boxColor || "#FFFFFF"}${Math.round((style.boxOpacity || 0.14) * 255).toString(16).padStart(2, "0")}`, border: `1px solid ${accent}55`, boxShadow: `0 18px 36px rgba(0,0,0,0.35), 0 0 22px ${accent}33`, backdropFilter: "blur(10px)" }}>
              {style.decorativeElements && <span className="absolute inset-y-[-20%] w-12 animate-[signalScanLine_2s_ease-in-out_infinite]" style={{ left: 0, background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.42), transparent)", transform: "skewX(-18deg)" }} />}
              {style.badgeEnabled && <span style={{ color: accent, fontSize: 8, fontWeight: 900, letterSpacing: 1.5 }}>{style.badgeText || "FOCUS"}</span>}
              <p style={{ ...baseTextStyle, ...colorStyle, textShadow, marginTop: style.badgeEnabled ? 5 : 0 }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "marker_swipe": {
      const accent = style.boxColor || style.lineColor || "#FDE047";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-x-4 flex justify-center" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ position: "relative", padding: "8px 12px" }}>
              {style.decorativeElements && <span className="absolute left-0 right-0 top-1/2 h-[54%] origin-left animate-[markerSwipePreview_2.4s_ease-in-out_infinite]" style={{ background: accent, borderRadius: 8, transform: "translateY(-50%)", opacity: style.boxOpacity || 0.86 }} />}
              <p className="relative" style={{ ...baseTextStyle, color: style.color, textShadow, fontSize: Math.max(fontSize, 16) }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "signal_scan": {
      const accent = style.lineColor || "#22D3EE";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4 animate-[signalScanPreview_2.5s_ease-in-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ position: "relative", overflow: "hidden", padding: "18px 18px", borderRadius: 10, border: `1px solid ${accent}66`, background: `${style.boxColor || "#0EA5E9"}${Math.round((style.boxOpacity || 0.16) * 255).toString(16).padStart(2, "0")}`, boxShadow: `0 0 22px ${accent}33` }}>
              {style.decorativeElements && <span className="absolute inset-y-0 w-10 animate-[signalScanLine_1.6s_linear_infinite]" style={{ left: 0, background: `linear-gradient(90deg, transparent, ${accent}77, transparent)` }} />}
              {style.badgeEnabled && <span style={{ color: accent, fontSize: 8, fontWeight: 900, letterSpacing: 1.3 }}>{style.badgeText || "SIGNAL"}</span>}
              <p style={{ ...baseTextStyle, ...colorStyle, textShadow, marginTop: style.badgeEnabled ? 4 : 0 }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "comment_reply": {
      const accent = style.lineColor || "#18181B";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-8" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ position: "relative", borderRadius: 14, padding: "14px 16px", background: `${style.boxColor || "#FFFFFF"}${Math.round((style.boxOpacity || 0.98) * 255).toString(16).padStart(2, "0")}`, boxShadow: "0 16px 32px rgba(0,0,0,.32)" }}>
              <span style={{ display: "block", marginBottom: 5, color: `${accent}99`, fontSize: 8, fontWeight: 700 }}>{style.badgeText || "replying to @viewer"}</span>
              <p style={{ ...baseTextStyle, color: style.color || "#18181B", fontSize: Math.max(fontSize * 0.78, 13), textAlign: "left", textShadow: "none" }}>{text}</p>
              <span style={{ position: "absolute", left: 20, bottom: -8, width: 18, height: 18, background: style.boxColor || "#FFFFFF", transform: "rotate(45deg)" }} />
            </div>
          </div>
        </>
      );
    }

    case "search_prompt": {
      const accent = style.lineColor || "#22D3EE";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ display: "grid", gridTemplateColumns: "28px 1fr 26px", alignItems: "center", gap: 8, borderRadius: 999, padding: "10px 13px", background: `${style.boxColor || "#0F172A"}${Math.round((style.boxOpacity || 0.94) * 255).toString(16).padStart(2, "0")}`, border: `1px solid ${accent}66`, boxShadow: `0 0 22px ${accent}22` }}>
              <span style={{ color: accent, fontSize: 17 }}>⌕</span>
              <p style={{ ...baseTextStyle, color: style.color, fontSize: Math.max(fontSize * 0.72, 12), textAlign: "left", textShadow }}> {text}</p>
              <span style={{ color: accent, fontSize: 14 }}>↗</span>
            </div>
          </div>
        </>
      );
    }

    case "countdown_list": {
      const accent = style.boxColor || "#FACC15";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute left-4 right-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{ display: "grid", gridTemplateColumns: "70px 1fr", overflow: "hidden", borderRadius: 12, border: `3px solid ${style.lineColor || "#111827"}`, boxShadow: `7px 7px 0 ${style.lineColor || "#111827"}` }}>
              <span style={{ display: "grid", placeItems: "center", background: accent, color: "#111827", fontSize: 28, fontWeight: 1000 }}>{style.badgeText || "03"}</span>
              <p style={{ ...baseTextStyle, color: style.color || "#111827", background: "#F8FAFC", padding: "14px", fontSize: Math.max(fontSize * 0.74, 13), textAlign: "left", textShadow: "none" }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "pov_stamp": {
      const accent = style.boxColor || "#FB7185";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-x-5" style={{ top: posTop, transform: "translateY(-50%) rotate(-2deg)" }}>
            <span style={{ display: "inline-block", marginBottom: 6, padding: "4px 10px", borderRadius: 6, background: accent, color: "#FFFFFF", fontSize: 11, fontWeight: 1000, letterSpacing: 1 }}>{style.badgeText || "POV"}</span>
            <p style={{ ...baseTextStyle, color: style.color, padding: "12px 15px", border: `2px solid ${accent}`, borderRadius: 8, background: "rgba(18,7,12,.78)", textShadow, fontSize: Math.max(fontSize * 0.86, 14), textAlign: "left" }}>{text}</p>
          </div>
        </>
      );
    }

    case "glitch_rgb": {
      // 3 separate text layers matching FFmpeg: Red(-4+sin(t*15)*3), Cyan(+4-sin(t*15)*3), White(center)
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {/* Red channel — animated offset left */}
            <p className="absolute animate-[glitchRedLayer_0.8s_steps(4)_infinite]" style={{ ...baseTextStyle, color: "#FF0000", opacity: 0.7 }}>{text}</p>
            {/* Cyan channel — animated offset right */}
            <p className="absolute animate-[glitchCyanLayer_0.8s_steps(4)_infinite]" style={{ ...baseTextStyle, color: "#00FFFF", opacity: 0.7 }}>{text}</p>
            {/* Main text on top */}
            <p className="relative" style={{ ...baseTextStyle, ...colorStyle, ...boxStyle, textShadow }}>{text}</p>
          </div>
        </>
      );
    }

    case "shake_neon": {
      // Multiple glow layers + shake matching FFmpeg
      const neonColor = style.color || "#00FFCC";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {/* Glow layer 1: large dim blur */}
            <p className="absolute" style={{ ...baseTextStyle, color: neonColor, opacity: 0.3, filter: "blur(3px)", textShadow: `0 0 12px ${neonColor}, 0 0 24px ${neonColor}` }}>{text}</p>
            {/* Glow layer 2: medium, shaking */}
            <p className="absolute animate-[shakeNeonGlow_1.2s_ease-in-out_infinite]" style={{ ...baseTextStyle, color: neonColor, opacity: 0.5, textShadow: `0 0 6px ${neonColor}, 0 0 12px ${neonColor}` }}>{text}</p>
            {/* Main text: subtle shake */}
            <p className="relative animate-[shakeNeonMain_1.5s_ease-in-out_infinite]" style={{ ...baseTextStyle, color: neonColor, textShadow: `0 0 10px ${neonColor}, 0 0 20px ${neonColor}, 0 0 40px ${neonColor}`, ...boxStyle }}>{text}</p>
          </div>
        </>
      );
    }

    case "cinematic_reveal": {
      // Letterbox bars + dark overlay + elegant slow fade
      const revealColor = style.color || "#FFD700";
      return (
        <>
          {/* Letterbox bars */}
          <div className="absolute top-0 left-0 right-0 z-10" style={{ height: "12%", backgroundColor: "#000" }} />
          <div className="absolute bottom-0 left-0 right-0 z-10" style={{ height: "12%", backgroundColor: "#000" }} />
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4 animate-[cinematicRevealText_3.5s_ease-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <p style={{ ...baseTextStyle, color: revealColor, textShadow: `2px 2px 4px rgba(0,0,0,0.8)${style.glowEnabled ? `, 0 0 ${style.glowSize}px ${style.glowColor}` : ""}`, ...boxStyle }}>{text}</p>
          </div>
        </>
      );
    }

    case "danger_bold": {
      // Red glow behind + main text with thick border + pulse
      const dangerColor = style.color || "#FF2D2D";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4 animate-[dangerPulse_1.2s_ease-in-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            {/* Red glow behind */}
            <p className="absolute" style={{ ...baseTextStyle, color: "#FF0000", opacity: 0.4, textShadow: `0 0 10px #FF0000, 0 0 20px #FF0000, 0 0 40px rgba(255,0,0,0.3)` }}>{text}</p>
            {/* Main text with stroke */}
            <p className="relative" style={{ ...baseTextStyle, color: dangerColor, WebkitTextStroke: "1.5px black", textShadow: `0 0 10px #FF0000, 0 0 20px rgba(255,0,0,0.5)`, ...boxStyle }}>{text}</p>
          </div>
        </>
      );
    }

    case "bold_slam": {
      // Bold slam: scale entrance + shake + rotated box
      const boldSlamColor = style.boxColor || "#FFE600";
      const boldSlamStroke = "#16130B";
      const boldSlamText = style.color || "#16130B";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4 animate-[boldSlamPreview_2s_ease-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <div style={{
              background: boldSlamColor,
              padding: "20px 36px",
              borderRadius: 16,
              border: `5px solid ${boldSlamStroke}`,
              boxShadow: `8px 8px 0px ${boldSlamStroke}`,
            }}>
              <p style={{ ...baseTextStyle, color: boldSlamText, textTransform: "uppercase" as const }}>{text}</p>
            </div>
          </div>
        </>
      );
    }

    case "typewriter": {
      // Character reveal animation
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <p className="overflow-hidden whitespace-nowrap animate-[typewriterReveal_3s_steps(20)_infinite]" style={{ ...baseTextStyle, ...colorStyle, ...boxStyle, textShadow, borderRight: "2px solid currentColor" }}>{text}</p>
          </div>
        </>
      );
    }

    case "slide_up":
    case "slide_punch_framer": {
      const animClass = style.animation === "slide_up"
        ? "animate-[slideUpPreview_2s_ease-in-out_infinite]"
        : "animate-[slidePunchPreview_2s_ease-out_infinite]";
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className={cn("absolute inset-0 flex items-center justify-center px-4", animClass)} style={{ top: posTop, transform: "translateY(-50%)" }}>
            <p style={{ ...baseTextStyle, ...colorStyle, ...boxStyle, textShadow }}>{text}</p>
          </div>
        </>
      );
    }

    case "glitch": {
      // Simple glitch jitter
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4 animate-[glitchJitter_0.5s_steps(2)_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <p style={{ ...baseTextStyle, ...colorStyle, ...boxStyle, textShadow }}>{text}</p>
          </div>
        </>
      );
    }

    case "fade_scale":
    default: {
      return (
        <>
          <div className="absolute inset-0" style={{ backgroundColor: style.bgColor, opacity: style.bgOpacity }} />
          <div className="absolute inset-0 flex items-center justify-center px-4 animate-[fadeScalePreview_2.5s_ease-in-out_infinite]" style={{ top: posTop, transform: "translateY(-50%)" }}>
            <p style={{ ...baseTextStyle, ...colorStyle, ...boxStyle, textShadow }}>{text}</p>
          </div>
        </>
      );
    }
  }
}
