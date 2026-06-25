import React from "react";
import { AbsoluteFill, Sequence, OffthreadVideo, useVideoConfig } from "remotion";
import type { ClipCompositionProps } from "../types";
import { HookLayer } from "../layers/HookLayer";
import { SubtitleLayer } from "../layers/SubtitleLayer";

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

      {/* Layer 3: Subtitles (no offset - timestamps from Whisper are already relative to clip start) */}
      {words.length > 0 && (
        <AbsoluteFill>
          <SubtitleLayer
            words={words}
            config={subtitleConfig}
            fps={fps}
            startOffset={0}
          />
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
