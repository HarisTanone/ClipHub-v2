/**
 * CreativeComposition — 17 animated subtitle styles inspired by remotion-subtitles.
 * Source: https://github.com/ali-abassi/remotion-templates
 *
 * Styles: Bounce, Fire, Glitch, Neon, Lightning, Explosive, Fade, Glow,
 *         Rotate, Shake, 3D, TiltShift, Typewriter, Waving, Zoom, Colorful, Caption
 *
 * User selects a "creative_style" and all subtitles render with that animation.
 */
import React, { useMemo } from "react";
import {
  AbsoluteFill,
  Sequence,
  OffthreadVideo,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { makeTransform, scale, translateY } from "@remotion/animation-utils";
import type { ClipCompositionProps, Word } from "../types";
import { FramingTransitionLayer } from "../layers/FramingTransitionLayer";
import { AITextLayer, HideDuringTextEmphasis } from "../layers/AITextLayer";
import { BrollLayer, HideDuringBroll } from "../layers/BrollLayer";

// Available creative styles
export type CreativeStyle =
  | "bounce" | "fire" | "glitch" | "neon" | "lightning"
  | "explosive" | "fade" | "glow" | "rotate" | "shake"
  | "threedish" | "tiltshift" | "typewriter" | "waving" | "zoom"
  | "colorful" | "classic";

export const CreativeComposition: React.FC<ClipCompositionProps> = ({
  creativeDirection,
  videoPath,
  words,
  hookText,
  textEmphasisEvents = [],
  brollEvents = [],
}) => {
  const { fps, width } = useVideoConfig();
  const frame = useCurrentFrame();

  // Get creative style from config
  const hookConfig = creativeDirection?.hook_style_config || {};
  const subtitleConfig = creativeDirection?.subtitle_style_config || {};
  const creativeStyle: CreativeStyle = (hookConfig.creative_style || subtitleConfig.creative_style || "neon") as CreativeStyle;

  // Hook
  const hookDuration = hookConfig.duration || 3.0;
  const hookEndFrame = Math.floor(hookDuration * fps);
  const hookVisible = frame < hookEndFrame && hookText;
  const hookOpacity = interpolate(frame, [0, 10, hookEndFrame - 10, hookEndFrame], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  // Subtitles — manual grouping for reliability
  const pages = useMemo(() => {
    const result: any[] = [];
    for (let i = 0; i < words.length; i += 3) {
      const group = words.slice(i, i + 3);
      result.push({
        startMs: Math.round(group[0].start * 1000),
        endMs: Math.round(group[group.length - 1].end * 1000),
        text: group.map(w => w.word).join(" "),
        tokens: group.map(w => ({ text: w.word + " ", fromMs: Math.round(w.start * 1000), toMs: Math.round(w.end * 1000) })),
      });
    }
    return result;
  }, [words]);

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* Video */}
      {videoPath && (
        <AbsoluteFill>
          <FramingTransitionLayer
            events={creativeDirection.framing_events}
            style={hookConfig.transitionStyle || creativeDirection.transition_style || "cut"}
            duration={hookConfig.transitionDuration || creativeDirection.transition_duration || 0.35}
          >
            <OffthreadVideo src={videoPath} style={{ objectFit: "cover", width: "100%", height: "100%" }} />
          </FramingTransitionLayer>
        </AbsoluteFill>
      )}

      {textEmphasisEvents.length > 0 && (
        <AbsoluteFill style={{ zIndex: 1 }}>
          <AITextLayer events={textEmphasisEvents} style={creativeDirection.text_emphasis_style_config} />
        </AbsoluteFill>
      )}

      {/* B-Roll motion graphic layer */}
      {brollEvents.length > 0 && (
        <AbsoluteFill style={{ zIndex: 2, pointerEvents: "none" }}>
          <BrollLayer events={brollEvents} style={creativeDirection.broll_style_config} />
        </AbsoluteFill>
      )}

      {/* Hook with creative style */}
      {hookVisible && (
        <AbsoluteFill style={{ zIndex: 2, justifyContent: "center", alignItems: "center", backgroundColor: "rgba(0,0,0,0.6)", opacity: hookOpacity }}>
          <CreativeText text={hookText} style={creativeStyle} frame={frame} fontSize={48} />
        </AbsoluteFill>
      )}

      {/* Subtitles with creative animation */}
      <HideDuringTextEmphasis events={textEmphasisEvents}>
      <HideDuringBroll events={brollEvents}>
      {pages.map((page, index) => {
        const startFrame = Math.round((page.startMs / 1000) * fps);
        const endFrame = Math.round((page.endMs / 1000) * fps) + 3;
        const dur = endFrame - startFrame;
        if (dur <= 0) return null;

        const text = page.tokens?.map((t: any) => t.text).join("") || page.text || "";

        return (
          <Sequence key={index} from={startFrame} durationInFrames={dur}>
            <AbsoluteFill style={{ zIndex: 1, justifyContent: "flex-end", alignItems: "center", paddingBottom: 200 }}>
              <CreativeText text={text.trim()} style={creativeStyle} frame={0} fontSize={36} />
            </AbsoluteFill>
          </Sequence>
        );
      })}
      </HideDuringBroll>
      </HideDuringTextEmphasis>
    </AbsoluteFill>
  );
};

// ─── Creative Text Component (17 styles) ─────────────────────────────────────

function CreativeText({ text, style, frame: parentFrame, fontSize }: { text: string; style: CreativeStyle; frame: number; fontSize: number }) {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const baseStyle: React.CSSProperties = {
    fontSize,
    fontWeight: 800,
    textAlign: "center",
    color: "white",
    fontFamily: "'Inter', sans-serif",
    textTransform: "uppercase",
    maxWidth: "90%",
  };

  switch (style) {
    case "bounce": {
      const bounceY = interpolate(frame, [0, durationInFrames * 0.15, durationInFrames * 0.3], [30, -15, 0], { extrapolateRight: "clamp" });
      const opacity = interpolate(frame, [0, 5], [0, 1], { extrapolateRight: "clamp" });
      return <span style={{ ...baseStyle, transform: `translateY(${bounceY}px)`, opacity, textShadow: "0 0 10px rgba(255,255,255,0.5)" }}>{text}</span>;
    }
    case "fire": {
      const shake = interpolate(frame, [0, 3, 6, 9], [0, 4, -4, 0], { extrapolateRight: "clamp" });
      const opacity = interpolate(frame, [0, 5], [0, 1], { extrapolateRight: "clamp" });
      const hue1 = interpolate(frame, [0, 15], [0, 30], { extrapolateRight: "clamp" });
      const hue2 = interpolate(frame, [0, 15], [30, 60], { extrapolateRight: "clamp" });
      return <span style={{ ...baseStyle, color: "transparent", backgroundImage: `linear-gradient(to right, hsl(${hue1},100%,50%), hsl(${hue2},100%,50%))`, WebkitBackgroundClip: "text", transform: `translateY(${shake}px)`, opacity }}>{text}</span>;
    }
    case "glitch": {
      const gx = interpolate(frame, [0, 2, 4, 6, 8], [0, 6, -6, 3, 0], { extrapolateRight: "clamp" });
      const gy = interpolate(frame, [0, 3, 5, 7], [0, 3, -3, 0], { extrapolateRight: "clamp" });
      const opacity = interpolate(frame, [0, 3], [0, 1], { extrapolateRight: "clamp" });
      return (
        <span style={{ ...baseStyle, position: "relative", opacity }}>
          <span style={{ position: "absolute", color: "#ff0000", transform: `translate(${gx - 2}px, ${gy}px)`, opacity: 0.7, mixBlendMode: "screen" }}>{text}</span>
          <span style={{ position: "absolute", color: "#00ffff", transform: `translate(${gx + 2}px, ${-gy}px)`, opacity: 0.7, mixBlendMode: "screen" }}>{text}</span>
          <span style={{ position: "relative" }}>{text}</span>
        </span>
      );
    }
    case "neon": {
      const opacity = interpolate(frame, [0, 5], [0, 1], { extrapolateRight: "clamp" });
      const glowIntensity = interpolate(frame, [0, 10, 20], [10, 30, 20], { extrapolateRight: "clamp" });
      return <span style={{ ...baseStyle, color: "#00ffcc", textShadow: `0 0 ${glowIntensity}px #00ffcc, 0 0 ${glowIntensity * 2}px #00ffcc`, opacity }}>{text}</span>;
    }
    case "lightning": {
      const flash = frame % 12 < 3 ? 1.5 : 1;
      const opacity = interpolate(frame, [0, 3], [0, 1], { extrapolateRight: "clamp" });
      return <span style={{ ...baseStyle, color: "#FFF", textShadow: `0 0 ${20 * flash}px #4444FF, 0 0 ${40 * flash}px #4444FF`, transform: `scale(${flash > 1 ? 1.05 : 1})`, opacity }}>{text}</span>;
    }
    case "explosive": {
      const s = spring({ frame, fps, config: { damping: 8, stiffness: 300 } });
      return <span style={{ ...baseStyle, transform: makeTransform([scale(s)]), textShadow: "0 0 20px rgba(255,100,0,0.8)", color: "#FFD700" }}>{text}</span>;
    }
    case "fade": {
      const opacity = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: "clamp" });
      return <span style={{ ...baseStyle, opacity }}>{text}</span>;
    }
    case "glow": {
      const opacity = interpolate(frame, [0, 5], [0, 1], { extrapolateRight: "clamp" });
      const glow = interpolate(frame, [0, 15, 30], [5, 25, 15], { extrapolateRight: "clamp" });
      return <span style={{ ...baseStyle, textShadow: `0 0 ${glow}px #FFFFFF, 0 0 ${glow * 2}px #FFCC00`, opacity }}>{text}</span>;
    }
    case "rotate": {
      const rot = interpolate(frame, [0, 8], [-5, 0], { extrapolateRight: "clamp" });
      const opacity = interpolate(frame, [0, 5], [0, 1], { extrapolateRight: "clamp" });
      return <span style={{ ...baseStyle, transform: `rotate(${rot}deg)`, opacity }}>{text}</span>;
    }
    case "shake": {
      const sx = Math.sin(frame * 0.8) * 3;
      const sy = Math.cos(frame * 0.6) * 2;
      const opacity = interpolate(frame, [0, 3], [0, 1], { extrapolateRight: "clamp" });
      return <span style={{ ...baseStyle, transform: `translate(${sx}px, ${sy}px)`, opacity }}>{text}</span>;
    }
    case "threedish": {
      const opacity = interpolate(frame, [0, 5], [0, 1], { extrapolateRight: "clamp" });
      return <span style={{ ...baseStyle, textShadow: "2px 2px 0 #333, 4px 4px 0 #222, 6px 6px 0 #111", opacity }}>{text}</span>;
    }
    case "tiltshift": {
      const tilt = interpolate(frame, [0, 10], [3, 0], { extrapolateRight: "clamp" });
      const opacity = interpolate(frame, [0, 5], [0, 1], { extrapolateRight: "clamp" });
      return <span style={{ ...baseStyle, transform: `perspective(500px) rotateX(${tilt}deg)`, opacity }}>{text}</span>;
    }
    case "typewriter": {
      const chars = Math.floor(interpolate(frame, [0, fps * 1.2], [0, text.length], { extrapolateRight: "clamp" }));
      return <span style={{ ...baseStyle, color: "#00FF88", fontFamily: "monospace" }}>{text.slice(0, chars)}<span style={{ opacity: frame % 16 < 10 ? 1 : 0 }}>|</span></span>;
    }
    case "waving": {
      const wave = Math.sin(frame * 0.15) * 5;
      const opacity = interpolate(frame, [0, 5], [0, 1], { extrapolateRight: "clamp" });
      return <span style={{ ...baseStyle, transform: `translateY(${wave}px)`, opacity }}>{text}</span>;
    }
    case "zoom": {
      const z = interpolate(frame, [0, 8], [0.7, 1], { extrapolateRight: "clamp" });
      const opacity = interpolate(frame, [0, 5], [0, 1], { extrapolateRight: "clamp" });
      return <span style={{ ...baseStyle, transform: `scale(${z})`, opacity }}>{text}</span>;
    }
    case "colorful": {
      const hue = (frame * 5) % 360;
      const opacity = interpolate(frame, [0, 5], [0, 1], { extrapolateRight: "clamp" });
      return <span style={{ ...baseStyle, color: `hsl(${hue}, 100%, 70%)`, textShadow: `0 0 10px hsl(${hue}, 100%, 50%)`, opacity }}>{text}</span>;
    }
    default: { // classic
      const opacity = interpolate(frame, [0, 5], [0, 1], { extrapolateRight: "clamp" });
      return <span style={{ ...baseStyle, textShadow: "0 2px 8px rgba(0,0,0,0.8)", opacity }}>{text}</span>;
    }
  }
}
