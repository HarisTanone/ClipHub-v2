import React from "react";
import { AbsoluteFill, Sequence, OffthreadVideo, useVideoConfig } from "remotion";
import type { ClipCompositionProps } from "../types";
import { HookLayer } from "../layers/HookLayer";
import { SubtitleLayer } from "../layers/SubtitleLayer";
import { ZoomLayer } from "../layers/ZoomLayer";

// ─── Font Loader ─────────────────────────────────────────────────────────────

function useRemotionFont(fontName: string | undefined) {
  if (!fontName || fontName === "monospace") return;
  try {
    const id = `gfont-${fontName.replace(/\s/g, "")}`;
    if (typeof document !== "undefined" && !document.getElementById(id)) {
      const link = document.createElement("link");
      link.id = id;
      link.rel = "stylesheet";
      link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(fontName)}:wght@400;500;600;700;800;900&display=swap`;
      document.head.appendChild(link);
    }
  } catch { /* headless may not have document */ }
}

// ─── Config Hooks (per-component style isolation) ────────────────────────────

function useHookConfig(creativeDirection: any, hookAnimation?: string) {
  const config = creativeDirection.hook_style_config || {};
  return {
    config: { ...config, animation: hookAnimation || config.animation },
    duration: config.duration || 3.0,
    fontFamily: config.fontFamily || "Poppins",
  };
}

function useSubtitleConfig(creativeDirection: any) {
  const config = creativeDirection.subtitle_style_config || {};
  return {
    config,
    fontFamily: config.fontFamily || "Poppins",
    highlightFontFamily: config.dualStyleEnabled ? config.highlightFontFamily : undefined,
  };
}

// ─── Main Composition ────────────────────────────────────────────────────────

/**
 * ClipComposition — Main render composition.
 *
 * Layer stack (bottom to top):
 *   L1: Base Video + Auto Zoom (ZoomLayer)
 *   L2: Subtitles (SubtitleLayer) — filtered: hidden during hook period
 *   L3: Hook overlay (HookLayer) — first N seconds, highest z-index
 *
 * Style configs are isolated per-component:
 *   - hook_style_config → HookLayer only
 *   - subtitle_style_config → SubtitleLayer only
 */
export const ClipComposition: React.FC<ClipCompositionProps> = ({
  creativeDirection,
  videoPath,
  words,
  hookText,
  hookAnimation,
}) => {
  const { fps } = useVideoConfig();

  // ─── Per-component config extraction ─────────────────────────────
  const hook = useHookConfig(creativeDirection, hookAnimation);
  const subtitle = useSubtitleConfig(creativeDirection);

  const hookDurationFrames = Math.floor(hook.duration * fps);

  // ─── Font loading (isolated per component) ───────────────────────
  useRemotionFont(subtitle.fontFamily);
  useRemotionFont(hook.fontFamily);
  if (subtitle.highlightFontFamily) {
    useRemotionFont(subtitle.highlightFontFamily);
  }

  // ─── Zoom events from prosody analysis ───────────────────────────
  const zoomEvents = creativeDirection.zoom_events || [];

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* L1: Base Video + Auto Zoom */}
      {videoPath && (
        <AbsoluteFill>
          <ZoomLayer zoomEvents={zoomEvents} maxScale={1.15} defaultDuration={0.5}>
            <OffthreadVideo
              src={videoPath}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          </ZoomLayer>
        </AbsoluteFill>
      )}

      {/* L2: Subtitles — words overlapping hook get clamped, not discarded */}
      {words.length > 0 && (
        <AbsoluteFill style={{ zIndex: 1, pointerEvents: "none" }}>
          <SubtitleLayer
            words={hookText
              ? words
                .filter(w => w.end > hook.duration)
                .map(w => ({ ...w, start: Math.max(w.start, hook.duration) }))
              : words}
            config={subtitle.config}
            fps={fps}
          />
        </AbsoluteFill>
      )}

      {/* L3: Hook overlay — renders with fade-out buffer for smooth transition */}
      {hookText && (
        <Sequence from={0} durationInFrames={hookDurationFrames + Math.floor(fps * 0.5)}>
          <AbsoluteFill style={{ zIndex: 2 }}>
            <HookLayer text={hookText} config={hook.config} />
          </AbsoluteFill>
        </Sequence>
      )}
    </AbsoluteFill>
  );
};
