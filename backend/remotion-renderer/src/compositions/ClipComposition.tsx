import React from "react";
import { AbsoluteFill, Sequence, OffthreadVideo, useVideoConfig } from "remotion";
import type { ClipCompositionProps } from "../types";
import { HookLayer } from "../layers/HookLayer";
import { SubtitleLayer } from "../layers/SubtitleLayer";

// Dynamic font loader — injects Google Fonts stylesheet
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

/**
 * Main clip composition:
 * 1. Base video
 * 2. Hook text (first N seconds, uses hook_style_config)
 * 3. Subtitles (word-by-word, uses subtitle_style_config)
 */
export const ClipComposition: React.FC<ClipCompositionProps> = ({
  creativeDirection,
  videoPath,
  words,
  hookText,
  hookAnimation,
}) => {
  const { fps } = useVideoConfig();

  // Read full style configs from creative direction (passed from Python)
  const hookConfig = creativeDirection.hook_style_config || {};
  const subtitleConfig = creativeDirection.subtitle_style_config || {};

  const hookDuration = hookConfig.duration || 3.0;
  const hookDurationFrames = Math.floor(hookDuration * fps);

  // Load fonts for subtitle (normal + highlight)
  useRemotionFont(subtitleConfig.fontFamily || "Poppins");
  useRemotionFont(hookConfig.fontFamily || "Poppins");
  if (subtitleConfig.dualStyleEnabled && subtitleConfig.highlightFontFamily) {
    useRemotionFont(subtitleConfig.highlightFontFamily);
  }

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* Layer 1: Base Video — OffthreadVideo for stability */}
      {videoPath && (
        <AbsoluteFill>
          <OffthreadVideo
            src={videoPath}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        </AbsoluteFill>
      )}

      {/* Layer 2: Hook (first N seconds) */}
      {hookText && (
        <Sequence from={0} durationInFrames={hookDurationFrames}>
          <HookLayer text={hookText} config={hookConfig} />
        </Sequence>
      )}

      {/* Layer 3: Subtitles (starts AFTER hook to avoid overlap) */}
      {words.length > 0 && (
        <Sequence from={hookText ? hookDurationFrames : 0}>
          <SubtitleLayer
            words={words}
            config={subtitleConfig}
            fps={fps}
            startOffset={hookText ? -hookDuration : 0}
          />
        </Sequence>
      )}
    </AbsoluteFill>
  );
};
