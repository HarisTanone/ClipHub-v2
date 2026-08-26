import { Palette } from "lucide-react";
import type { CanvasConfig } from "@/lib/canvasTemplates";
import { SKIA_HOOK_PRESETS } from "@/lib/renderEngines";
import type { HookStyle } from "../types";
import { getHookPreviewSample } from "../utils";
import { CanvasPreviewFrame } from "./CanvasPreviewFrame";

export function SkiaHookLivePreview({
  style,
  thumbnailUrl,
  aspectRatio = "9:16",
  canvas,
}: {
  style: HookStyle;
  thumbnailUrl?: string;
  aspectRatio?: string;
  canvas?: CanvasConfig | null;
}) {
  const presetId = style.animation || "skia_zoom_punch";
  const preset = SKIA_HOOK_PRESETS.find((p) => p.id === presetId || p.id === `skia_${presetId}`) || SKIA_HOOK_PRESETS[0];
  const sample = style.text || getHookPreviewSample(presetId);
  const posTop = `${style.positionY ?? 40}%`;

  return (
    <>
      <div className="mb-3 flex w-full items-center justify-between gap-2">
        <p className="text-[9px] text-zinc-600 uppercase tracking-widest shrink-0">Live Preview</p>
        <span className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[9px] text-amber-300">
          <Palette className="inline w-3 h-3 mr-1" />Skia Canvas GPU
        </span>
      </div>
      <CanvasPreviewFrame canvas={canvas || null} thumbnailUrl={thumbnailUrl} dimOverlay>
        <div className="absolute left-0 right-0 flex items-center justify-center px-3 pointer-events-none" style={{ top: posTop, transform: "translateY(-50%)" }}>
          {presetId === "paper_clip_scrap" ? (
            <div
              style={{
                position: "relative",
                padding: "16px 18px 12px 18px",
                maxWidth: "90%",
                background: style.boxColor || "#FEF08A",
                borderRadius: "10px",
                transform: "rotate(-2.5deg)",
                boxShadow: "0 12px 28px rgba(0,0,0,0.5)",
                boxSizing: "border-box",
              }}
            >
              {/* Washi tape top right */}
              <div style={{ position: "absolute", top: -6, right: 12, width: 32, height: 12, backgroundColor: "rgba(255, 255, 255, 0.7)", border: "1px solid rgba(200, 200, 200, 0.5)", transform: "rotate(12deg)" }} />
              {/* Paper Clip SVG top left */}
              <div style={{ position: "absolute", top: -10, left: 12, width: 16, height: 36, zIndex: 10, filter: "drop-shadow(1px 2px 2px rgba(0,0,0,0.4))" }}>
                <svg viewBox="0 0 38 90" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ width: "100%", height: "100%" }}>
                  <path d="M12 28 V70 C12 76 17 81 23 81 C29 81 34 76 34 70 V18 C34 9 27 2 18 2 C9 2 2 9 2 18 V74" stroke="#475569" strokeWidth="5" strokeLinecap="round" />
                  <path d="M12 28 V70 C12 76 17 81 23 81 C29 81 34 76 34 70 V18 C34 9 27 2 18 2 C9 2 2 9 2 18 V74" stroke="#E2E8F0" strokeWidth="2.5" strokeLinecap="round" />
                </svg>
              </div>
              <p
                style={{
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 15),
                  fontWeight: 900,
                  fontFamily: `'${style.fontFamily || "Montserrat"}', sans-serif`,
                  color: style.color || "#1C1917",
                  textTransform: "uppercase",
                  textAlign: "center",
                  wordBreak: "break-word",
                  lineHeight: 1.2,
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "trending_radar" ? (
            <div
              style={{
                position: "relative",
                padding: "16px 16px 12px 16px",
                maxWidth: "92%",
                background: "rgba(9, 5, 20, 0.94)",
                borderRadius: "10px",
                border: "1.5px solid #D946EF",
                boxShadow: "0 12px 28px rgba(0,0,0,0.6), 0 0 14px rgba(217,70,239,0.4)",
                boxSizing: "border-box",
              }}
            >
              {/* Corner HUD */}
              <div style={{ position: "absolute", top: 3, left: 3, width: 6, height: 6, borderTop: "2px solid #06B6D4", borderLeft: "2px solid #06B6D4" }} />
              <div style={{ position: "absolute", top: 3, right: 3, width: 6, height: 6, borderTop: "2px solid #06B6D4", borderRight: "2px solid #06B6D4" }} />
              <div style={{ position: "absolute", bottom: 3, left: 3, width: 6, height: 6, borderBottom: "2px solid #06B6D4", borderLeft: "2px solid #06B6D4" }} />
              <div style={{ position: "absolute", bottom: 3, right: 3, width: 6, height: 6, borderBottom: "2px solid #06B6D4", borderRight: "2px solid #06B6D4" }} />
              {/* Badge */}
              <div style={{ position: "absolute", top: -8, left: "50%", transform: "translateX(-50%)", background: "#D946EF", color: "#FFFFFF", padding: "1px 8px", borderRadius: 999, fontSize: 7, fontWeight: 900, letterSpacing: "0.1em", textTransform: "uppercase", display: "flex", alignItems: "center", gap: 3 }}>
                <span style={{ width: 4, height: 4, borderRadius: 999, backgroundColor: "#FFFFFF" }} />
                <span>{style.badgeText || "TRENDING NOW"}</span>
              </div>
              <p
                style={{
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 15),
                  fontWeight: 900,
                  fontFamily: `'${style.fontFamily || "Montserrat"}', sans-serif`,
                  color: style.color || "#FFFFFF",
                  textTransform: "uppercase",
                  textAlign: "center",
                  wordBreak: "break-word",
                  lineHeight: 1.2,
                  marginTop: 2,
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "news_breaking_live" ? (
            <div
              style={{
                position: "relative",
                maxWidth: "92%",
                borderRadius: "8px",
                overflow: "hidden",
                background: "rgba(15, 23, 42, 0.95)",
                border: "1px solid rgba(255,255,255,0.15)",
                boxShadow: "0 12px 28px rgba(0,0,0,0.6)",
                boxSizing: "border-box",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "4px 8px", borderBottom: "1px solid rgba(255,255,255,0.1)", background: "rgba(0,0,0,0.3)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 4, background: "#DC2626", color: "#FFFFFF", padding: "1px 6px", borderRadius: 3, fontSize: 7, fontWeight: 900, textTransform: "uppercase" }}>
                  <span style={{ width: 4, height: 4, borderRadius: 999, backgroundColor: "#FFFFFF" }} />
                  <span>{style.badgeText || "BREAKING"}</span>
                </div>
                <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 6, fontWeight: 800 }}>LIVE</span>
              </div>
              <p
                style={{
                  padding: "8px 10px",
                  fontSize: Math.min(Math.max(style.fontSize * 0.20, 10), 14),
                  fontWeight: 900,
                  fontFamily: `'${style.fontFamily || "Montserrat"}', sans-serif`,
                  color: style.color || "#FFFFFF",
                  textAlign: "left",
                  wordBreak: "break-word",
                  lineHeight: 1.2,
                }}
              >
                {sample}
              </p>
              <div style={{ height: 2, backgroundColor: "#DC2626" }} />
            </div>
          ) : presetId === "skia_neon_cyberpunk" ? (
            <div
              style={{
                position: "relative",
                padding: "8px 14px",
                maxWidth: "92%",
                background: "rgba(10, 15, 30, 0.85)",
                borderRadius: "10px",
                border: "1.5px solid #00F0FF",
                boxShadow: "0 0 16px rgba(0,240,255,0.4), inset 0 0 12px rgba(255,0,127,0.25)",
                backdropFilter: "blur(8px)",
                boxSizing: "border-box",
              }}
            >
              <div style={{ position: "absolute", top: -2, left: -2, width: 6, height: 6, borderTop: "2px solid #FF007F", borderLeft: "2px solid #FF007F" }} />
              <div style={{ position: "absolute", bottom: -2, right: -2, width: 6, height: 6, borderBottom: "2px solid #FF007F", borderRight: "2px solid #FF007F" }} />
              <p
                style={{
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                  fontWeight: 900,
                  fontFamily: `'${style.fontFamily || "Montserrat"}', sans-serif`,
                  background: "linear-gradient(135deg, #00F0FF, #FF007F)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  textTransform: "uppercase",
                  letterSpacing: "0.03em",
                  textAlign: "center",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "skia_frosted_pill" ? (
            <div
              style={{
                padding: "6px 14px",
                maxWidth: "92%",
                background: "rgba(255, 255, 255, 0.15)",
                borderRadius: "999px",
                border: "1px solid rgba(255, 255, 255, 0.35)",
                boxShadow: "0 8px 24px rgba(0, 0, 0, 0.4)",
                backdropFilter: "blur(12px)",
                boxSizing: "border-box",
              }}
            >
              <p
                style={{
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 15),
                  fontWeight: 800,
                  fontFamily: `'${style.fontFamily || "Plus Jakarta Sans"}', sans-serif`,
                  color: "#FFFFFF",
                  textAlign: "center",
                  letterSpacing: "-0.01em",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "skia_aurora_gradient" ? (
            <div
              style={{
                position: "relative",
                padding: "6px 14px",
                maxWidth: "92%",
                borderRadius: "8px",
                background: "rgba(5, 15, 10, 0.8)",
                boxShadow: "0 0 20px rgba(16, 185, 129, 0.35)",
                boxSizing: "border-box",
              }}
            >
              <p
                style={{
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                  fontWeight: 900,
                  fontFamily: `'${style.fontFamily || "Outfit"}', sans-serif`,
                  background: "linear-gradient(135deg, #10B981 0%, #38BDF8 50%, #8B5CF6 100%)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  textAlign: "center",
                  textTransform: "uppercase",
                  letterSpacing: "0.03em",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "skia_impact_badge" ? (
            <div
              style={{
                background: "linear-gradient(135deg, #FACC15, #EAB308)",
                padding: "5px 12px",
                maxWidth: "92%",
                borderRadius: "5px",
                transform: "rotate(-1.5deg)",
                boxShadow: "0 4px 0 #713F12, 0 8px 18px rgba(0,0,0,0.5)",
                boxSizing: "border-box",
              }}
            >
              <p
                style={{
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                  fontWeight: 900,
                  fontFamily: `'${style.fontFamily || "Anton"}', sans-serif`,
                  color: "#000000",
                  textTransform: "uppercase",
                  letterSpacing: "0.02em",
                  textAlign: "center",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "skia_3d_chrome" ? (
            <p
              style={{
                fontSize: Math.min(Math.max(style.fontSize * 0.24, 12), 17),
                fontWeight: 900,
                maxWidth: "92%",
                fontFamily: `'${style.fontFamily || "Bebas Neue"}', sans-serif`,
                background: "linear-gradient(180deg, #FFFFFF 0%, #E2E8F0 30%, #FBBF24 50%, #78350F 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                textAlign: "center",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
                filter: "drop-shadow(0 3px 8px rgba(0,0,0,0.85))",
                wordBreak: "break-word",
              }}
            >
              {sample}
            </p>
          ) : presetId === "skia_ruby_flame" ? (
            <p
              style={{
                fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                fontWeight: 900,
                maxWidth: "92%",
                fontFamily: `'${style.fontFamily || "Bungee"}', sans-serif`,
                background: "linear-gradient(135deg, #FF3366, #FF9900)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                textAlign: "center",
                textTransform: "uppercase",
                filter: "drop-shadow(0 0 12px rgba(255, 46, 46, 0.6))",
                wordBreak: "break-word",
              }}
            >
              {sample}
            </p>
          ) : presetId === "skia_gold_prestige" ? (
            <div className="w-full text-center px-2" style={{ maxWidth: "92%" }}>
              <p
                style={{
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                  fontWeight: 800,
                  fontFamily: `'${style.fontFamily || "Playfair Display"}', serif`,
                  background: "linear-gradient(135deg, #FEF08A, #CA8A04)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  textAlign: "center",
                  letterSpacing: "0.03em",
                  filter: "drop-shadow(0 2px 6px rgba(202, 138, 4, 0.4))",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "skia_minimal_editorial" ? (
            <div
              style={{
                backgroundColor: "rgba(15, 23, 42, 0.75)",
                borderRadius: "8px",
                border: "1px solid rgba(255, 255, 255, 0.2)",
                padding: "5px 12px",
                maxWidth: "92%",
                boxSizing: "border-box",
              }}
            >
              <p
                style={{
                  color: "#FFFFFF",
                  fontFamily: `'${style.fontFamily || "Inter"}', sans-serif`,
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 15),
                  fontWeight: 800,
                  textAlign: "center",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "skia_glitch_rgb" ? (
            <div className="relative text-center px-2" style={{ maxWidth: "92%" }}>
              <p
                style={{
                  position: "absolute",
                  inset: 0,
                  color: "#FF0000",
                  opacity: 0.7,
                  transform: "translate(-2px, 0)",
                  fontFamily: `'${style.fontFamily || "Anton"}', sans-serif`,
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                  fontWeight: 900,
                  textTransform: "uppercase",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
              <p
                style={{
                  position: "absolute",
                  inset: 0,
                  color: "#00FFFF",
                  opacity: 0.7,
                  transform: "translate(2px, 0)",
                  fontFamily: `'${style.fontFamily || "Anton"}', sans-serif`,
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                  fontWeight: 900,
                  textTransform: "uppercase",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
              <p
                style={{
                  position: "relative",
                  color: style.color || "#FFFFFF",
                  fontFamily: `'${style.fontFamily || "Anton"}', sans-serif`,
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                  fontWeight: 900,
                  textTransform: "uppercase",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "skia_typewriter" ? (
            <div
              style={{
                backgroundColor: "rgba(9, 13, 22, 0.85)",
                borderRadius: "6px",
                border: "1px solid rgba(34, 197, 94, 0.4)",
                padding: "5px 10px",
                maxWidth: "92%",
                boxSizing: "border-box",
                boxShadow: "0 0 12px rgba(34, 197, 94, 0.25)",
              }}
            >
              <p
                style={{
                  color: "#22C55E",
                  fontFamily: `'${style.fontFamily || "Space Grotesk"}', monospace`,
                  fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 14),
                  fontWeight: 700,
                  textTransform: "uppercase",
                  textAlign: "center",
                  wordBreak: "break-word",
                }}
              >
                {sample}
              </p>
            </div>
          ) : presetId === "skia_fade_scale" ? (
            <p
              style={{
                fontSize: Math.min(Math.max(style.fontSize * 0.22, 11), 16),
                fontWeight: 800,
                maxWidth: "92%",
                fontFamily: `'${style.fontFamily || "Poppins"}', sans-serif`,
                color: style.color || "#FFFFFF",
                textAlign: "center",
                paintOrder: style.strokeEnabled ? "stroke" : undefined,
                WebkitTextStroke: style.strokeEnabled ? `${Math.max(style.strokeWidth * 0.25, 0.6)}px ${style.strokeColor || "#000"}` : undefined,
                textShadow: "0 4px 12px rgba(0,0,0,0.6)",
                wordBreak: "break-word",
              }}
            >
              {sample}
            </p>
          ) : (
            <p
              style={{
                fontSize: Math.min(Math.max(style.fontSize * 0.24, 12), 17),
                fontWeight: 900,
                fontFamily: style.fontFamily === "monospace" ? "monospace" : `'${style.fontFamily || "Anton"}', sans-serif`,
                color: style.color || "#FFFFFF",
                textTransform: style.uppercase ? "uppercase" : "none",
                textAlign: "center",
                maxWidth: "92%",
                whiteSpace: "pre-line",
                wordBreak: "break-word",
                padding: "4px 8px",
                backgroundColor: (style.bgOpacity || 0) > 0 ? `${style.bgColor || "black"}${Math.round(style.bgOpacity * 255).toString(16).padStart(2, "0")}` : "transparent",
                paintOrder: style.strokeEnabled ? "stroke" : undefined,
                WebkitTextStroke: style.strokeEnabled ? `${Math.max(style.strokeWidth * 0.25, 0.6)}px ${style.strokeColor || "#000"}` : undefined,
                textShadow: style.shadowEnabled ? `2px 2px 0px ${style.shadowColor || "#000"}` : undefined,
              }}
            >
              {sample}
            </p>
          )}
        </div>
        <p className="absolute bottom-2 left-0 right-0 text-center text-[8px] text-zinc-500 z-10">
          skia gpu · {preset.name} | {style.duration}s
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
