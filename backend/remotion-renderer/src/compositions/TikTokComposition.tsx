/**
 * TikTok-style composition using official @remotion/captions.
 * Uses createTikTokStyleCaptions for auto word grouping,
 * fitText for responsive font sizing, OffthreadVideo for stability,
 * and spring animations for smooth word transitions.
 *
 * User can choose this instead of custom ClipComposition.
 */
import React, { useMemo } from "react";
import {
  AbsoluteFill,
  Sequence,
  OffthreadVideo,
  useVideoConfig,
  useCurrentFrame,
  spring,
  interpolate,
} from "remotion";
import { makeTransform, scale, translateY } from "@remotion/animation-utils";
import { fitText } from "@remotion/layout-utils";
import type { ClipCompositionProps, Word } from "../types";

const HIGHLIGHT_COLOR = "#39E508";

export const TikTokComposition: React.FC<ClipCompositionProps> = ({
  creativeDirection,
  videoPath,
  words,
  hookText,
}) => {
  const { fps, width } = useVideoConfig();
  const frame = useCurrentFrame();

  // TikTok mode always uses green highlight — ignore user subtitle config
  const highlightColor = HIGHLIGHT_COLOR; // #39E508
  const textColor = "#FFFFFF";

  // Hook duration
  const hookDuration = creativeDirection?.hook_style_config?.duration || 3.0;
  const hookEndFrame = Math.floor(hookDuration * fps);

  // Group words into pages — manual grouping for reliable token format
  const pages = useMemo(() => {
    const result: any[] = [];
    for (let i = 0; i < words.length; i += 3) {
      const group = words.slice(i, i + 3);
      result.push({
        startMs: Math.round(group[0].start * 1000),
        text: group.map(w => w.word).join(" "),
        tokens: group.map(w => ({ text: w.word + " ", fromMs: Math.round(w.start * 1000), toMs: Math.round(w.end * 1000) })),
      });
    }
    return result;
  }, [words]);

  // Hook visibility
  const hookVisible = frame < hookEndFrame && hookText;
  const hookOpacity = interpolate(
    frame,
    [0, 10, hookEndFrame - 10, hookEndFrame],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const hookScale = spring({ frame, fps, config: { damping: 12, stiffness: 200 } });

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* Video layer — OffthreadVideo for stability */}
      {videoPath && (
        <AbsoluteFill>
          <OffthreadVideo
            src={videoPath}
            style={{ objectFit: "cover", width: "100%", height: "100%" }}
          />
        </AbsoluteFill>
      )}

      {/* Hook layer */}
      {hookVisible && (
        <AbsoluteFill
          style={{
            justifyContent: "center",
            alignItems: "center",
            backgroundColor: "rgba(0,0,0,0.6)",
            opacity: hookOpacity,
          }}
        >
          <div
            style={{
              transform: makeTransform([scale(hookScale)]),
              color: textColor,
              fontSize: 48,
              fontWeight: 800,
              textAlign: "center",
              padding: "0 40px",
              lineHeight: 1.3,
              textShadow: "0 4px 12px rgba(0,0,0,0.8)",
              fontFamily: "'Inter', sans-serif",
            }}
          >
            {hookText}
          </div>
        </AbsoluteFill>
      )}

      {/* TikTok-style captions */}
      {pages.map((page, index) => {
        const nextPage = pages[index + 1] ?? null;
        const subtitleStartFrame = Math.round((page.startMs / 1000) * fps);
        const subtitleEndFrame = nextPage
          ? Math.round((nextPage.startMs / 1000) * fps)
          : subtitleStartFrame + 45; // ~1.5s fallback
        const durationInFrames = Math.max(1, subtitleEndFrame - subtitleStartFrame);

        return (
          <Sequence key={index} from={subtitleStartFrame} durationInFrames={durationInFrames}>
            <TikTokSubtitlePage
              page={page}
              highlightColor={highlightColor}
              textColor={textColor}
              viewportWidth={width}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

// Subtitle page with spring animation and fitText
function TikTokSubtitlePage({
  page,
  highlightColor,
  textColor,
  viewportWidth,
}: {
  page: any;
  highlightColor: string;
  textColor: string;
  viewportWidth: number;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({
    frame,
    fps,
    config: { damping: 200 },
    durationInFrames: 5,
  });

  // Auto-fit text to viewport width
  const pageText = page.tokens?.map((t: any) => t.text).join("") || page.text || "";
  let fontSize = 60;
  try {
    const fitted = fitText({
      fontFamily: "Inter",
      text: pageText.toUpperCase() || "X",
      withinWidth: viewportWidth * 0.85,
    });
    fontSize = Math.min(90, fitted.fontSize);
  } catch {
    fontSize = 60;
  }

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        top: undefined,
        bottom: 280,
        height: 180,
      }}
    >
      <div
        style={{
          fontSize,
          fontWeight: 800,
          fontFamily: "'Inter', sans-serif",
          textTransform: "uppercase",
          color: textColor,
          WebkitTextStroke: "8px black",
          paintOrder: "stroke",
          transform: makeTransform([
            scale(interpolate(enter, [0, 1], [0.85, 1])),
            translateY(interpolate(enter, [0, 1], [30, 0])),
          ]),
        }}
      >
        {(() => {
          const tokens = page.tokens || [];
          const totalTokens = tokens.length || 1;
          const framesPerToken = Math.max(1, Math.floor(30 / totalTokens)); // spread across ~1s
          const activeIdx = Math.min(Math.floor(frame / framesPerToken), totalTokens - 1);
          return tokens.map((t: any, idx: number) => (
            <span
              key={idx}
              style={{
                display: "inline",
                whiteSpace: "pre",
                color: idx === activeIdx ? highlightColor : textColor,
              }}
            >
              {t.text}
            </span>
          ));
        })() || pageText}
      </div>
    </AbsoluteFill>
  );
}
