import React, { useMemo } from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
  Easing,
} from "remotion";
import type { BrollEvent, BrollMotionStyle, BrollStyleConfig } from "../types";

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const easeInOut = Easing.bezier(0.45, 0, 0.55, 1);

/** Soft vignette overlay so text reads on any image. */
const Vignette: React.FC<{ intensity?: number }> = ({ intensity = 0.55 }) => (
  <AbsoluteFill
    style={{
      background: `radial-gradient(ellipse at center, transparent 30%, rgba(0,0,0,${intensity}) 100%)`,
    }}
  />
);

/** Floating particle field used by particle_float / particle_burst. */
const ParticleField: React.FC<{
  count: number;
  color: string;
  seed: number;
}> = ({ count, color, seed }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const particles = useMemo(() => {
    const rng = (n: number) => {
      const x = Math.sin(seed * 9999 + n * 137.5) * 10000;
      return x - Math.floor(x);
    };
    return Array.from({ length: count }, (_, i) => ({
      x: rng(i) * 100,
      y: rng(i + 100) * 100,
      size: 2 + rng(i + 200) * 5,
      drift: 0.2 + rng(i + 300) * 0.6,
      phase: rng(i + 400) * Math.PI * 2,
    }));
  }, [count, seed]);
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {particles.map((p: { x: number; y: number; size: number; drift: number; phase: number }, i: number) => {
        const t = frame / fps;
        const y = (p.y - t * 12 * p.drift) % 100;
        const yNorm = y < 0 ? y + 100 : y;
        const opacity = 0.25 + 0.4 * Math.sin(t * 1.5 + p.phase);
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: `${p.x}%`,
              top: `${yNorm}%`,
              width: p.size,
              height: p.size,
              borderRadius: "50%",
              background: color,
              opacity: clamp(opacity, 0, 0.7),
              boxShadow: `0 0 ${p.size * 2}px ${color}`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

/** Animated light sweep band (diagonal highlight pass). */
const LightSweep: React.FC<{ progress: number; color?: string }> = ({
  progress,
  color = "rgba(255,255,255,0.45)",
}) => {
  const x = interpolate(progress, [0, 1], [-30, 130]);
  return (
    <AbsoluteFill style={{ overflow: "hidden", pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          top: "-20%",
          left: `${x}%`,
          width: "30%",
          height: "140%",
          transform: "rotate(18deg)",
          background: `linear-gradient(90deg, transparent, ${color}, transparent)`,
          filter: "blur(8px)",
        }}
      />
    </AbsoluteFill>
  );
};

// ─── Text animation primitive ────────────────────────────────────────────────

const KeywordText: React.FC<{
  text: string;
  color: string;
  fontFamily: string;
  animation: BrollMotionStyle;
  localFrame: number;
  durationFrames: number;
  fps: number;
  accentColor?: string;
}> = ({ text, color, fontFamily, animation, localFrame, durationFrames, fps, accentColor }) => {
  const enter = spring({ frame: localFrame, fps, config: { damping: 18, stiffness: 200, mass: 0.6 } });
  const exitStart = Math.max(0, durationFrames - 10);
  const exitOpacity = interpolate(localFrame, [exitStart, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const baseStyle: React.CSSProperties = {
    fontFamily: `'${fontFamily}', sans-serif`,
    fontWeight: 800,
    textAlign: "center" as const,
    color,
    textShadow: "0 4px 24px rgba(0,0,0,0.7)",
    lineHeight: 1.05,
    letterSpacing: "-0.01em",
    willChange: "transform, opacity",
  };

  if (animation === "typewriter") {
    const chars = Math.floor(text.length * clamp(localFrame / Math.max(8, durationFrames * 0.55), 0, 1));
    const shown = text.slice(0, chars);
    const caret = localFrame % 16 < 8 && chars < text.length ? "|" : "";
    return (
      <div style={{ ...baseStyle, fontSize: 54, opacity: exitOpacity, fontFamily: `'${fontFamily}', monospace` }}>
        {shown}
        <span style={{ color: accentColor || color, opacity: 0.8 }}>{caret}</span>
      </div>
    );
  }

  if (animation === "stroke_draw") {
    const reveal = clamp(localFrame / Math.max(8, durationFrames * 0.6), 0, 1);
    return (
      <div style={{ ...baseStyle, fontSize: 60, opacity: exitOpacity, WebkitTextStroke: `2px ${accentColor || color}`, color: "transparent" }}>
        <span style={{ clipPath: `inset(0 ${(1 - reveal) * 100}% 0 0)`, display: "inline-block" }}>{text}</span>
      </div>
    );
  }

  if (animation === "glitch_reveal") {
    const offset = interpolate(enter, [0, 0.3, 0.6, 1], [-8, 5, -3, 0]);
    const rgbSplit = localFrame < 12 ? Math.abs(offset) : 0;
    return (
      <div style={{ position: "relative", opacity: exitOpacity }}>
        <div style={{ ...baseStyle, fontSize: 58, transform: `translateX(${offset}px)`, color }}>{text}</div>
        {rgbSplit > 0 && (
          <>
            <div style={{ ...baseStyle, fontSize: 58, position: "absolute", top: 0, left: 0, right: 0, transform: `translateX(${rgbSplit}px)`, color: "#ff0040", opacity: 0.7, mixBlendMode: "screen" }}>{text}</div>
            <div style={{ ...baseStyle, fontSize: 58, position: "absolute", top: 0, left: 0, right: 0, transform: `translateX(${-rgbSplit}px)`, color: "#00ffff", opacity: 0.7, mixBlendMode: "screen" }}>{text}</div>
          </>
        )}
      </div>
    );
  }

  if (animation === "word_pop" || animation === "particle_burst") {
    const scale = interpolate(enter, [0, 1], [0.3, 1]);
    return (
      <div style={{ ...baseStyle, fontSize: 64, transform: `scale(${scale})`, opacity: exitOpacity * enter }}>
        {text}
      </div>
    );
  }

  if (animation === "line_reveal") {
    const reveal = clamp(localFrame / Math.max(6, durationFrames * 0.4), 0, 1);
    return (
      <div style={{ position: "relative", opacity: exitOpacity }}>
        <div style={{ ...baseStyle, fontSize: 56, clipPath: `inset(0 ${(1 - reveal) * 100}% 0 0)` }}>{text}</div>
        <div style={{ height: 3, background: accentColor || color, width: `${reveal * 100}%`, margin: "8px auto 0", boxShadow: `0 0 12px ${accentColor || color}` }} />
      </div>
    );
  }

  // Default: ken_burns, parallax_zoom, light_sweep, depth_parallax, particle_float
  const yShift = interpolate(enter, [0, 1], [24, 0]);
  return (
    <div style={{ ...baseStyle, fontSize: 60, transform: `translateY(${yShift}px)`, opacity: exitOpacity * enter }}>
      {text}
    </div>
  );
};

// ─── Single B-roll Event Renderer ────────────────────────────────────────────

const BrollEventView: React.FC<{
  event: BrollEvent;
  globalStyle: BrollStyleConfig;
}> = ({ event, globalStyle }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const startFrame = Math.round(event.start * fps);
  const endFrame = Math.max(startFrame + 1, Math.round(event.end * fps));
  const localFrame = frame - startFrame;
  const durationFrames = endFrame - startFrame;

  if (frame < startFrame || frame >= endFrame) return null;

  const motionStyle = event.motionStyle || globalStyle.defaultMotionStyle || "ken_burns";
  const textColor = event.textColor || globalStyle.textColor || "#FFFFFF";
  const accentColor = event.accentColor || globalStyle.accentColor || "#00E5C7";
  const fontFamily = event.fontFamily || globalStyle.fontFamily || "Poppins";
  const backdropDim = globalStyle.backdropDim ?? 0.45;
  const backdropBlur = globalStyle.backdropBlur ?? 8;
  const progress = clamp(localFrame / Math.max(1, durationFrames), 0, 1);

  // ─── Image-based motion graphic ──────────────────────────────────────────
  if (event.imagePath) {
    let imageTransform = "";
    let overlay: React.ReactNode = null;

    if (motionStyle === "ken_burns") {
      const scale = interpolate(progress, [0, 1], [1.05, 1.18], { easing: easeInOut });
      const panX = interpolate(progress, [0, 1], [-2, 2]);
      const panY = interpolate(progress, [0, 1], [-1, 1]);
      imageTransform = `scale(${scale}) translate(${panX}%, ${panY}%)`;
    } else if (motionStyle === "parallax_zoom" || motionStyle === "depth_parallax") {
      const scale = interpolate(progress, [0, 1], [1.12, 1.0], { easing: easeInOut });
      imageTransform = `scale(${scale})`;
    } else if (motionStyle === "light_sweep") {
      imageTransform = `scale(${interpolate(progress, [0, 1], [1.08, 1.04])})`;
      overlay = <LightSweep progress={progress} />;
    } else if (motionStyle === "particle_float" || motionStyle === "particle_burst") {
      imageTransform = `scale(${interpolate(progress, [0, 1], [1.04, 1.1])})`;
      overlay = <ParticleField count={28} color={accentColor} seed={event.start} />;
    } else if (motionStyle === "glitch_reveal") {
      const jitter = localFrame < 10 ? Math.sin(localFrame * 3.1) * 1.5 : 0;
      imageTransform = `scale(1.06) translateX(${jitter}px)`;
    } else {
      imageTransform = `scale(${interpolate(progress, [0, 1], [1.05, 1.12])})`;
    }

    const imgOpacity = interpolate(localFrame, [0, 6, durationFrames - 8, durationFrames], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

    return (
      <AbsoluteFill style={{ zIndex: 2, pointerEvents: "none" }}>
        <AbsoluteFill style={{ background: `rgba(0,0,0,${backdropDim})`, backdropFilter: `blur(${backdropBlur}px)` }} />
        <AbsoluteFill style={{ overflow: "hidden" }}>
          <Img
            src={event.imagePath}
            style={{ width: "100%", height: "100%", objectFit: "cover", transform: imageTransform, opacity: imgOpacity }}
          />
          <Vignette intensity={0.5} />
          {overlay}
        </AbsoluteFill>
        <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: "12%" }}>
          <KeywordText text={event.keyword} color={textColor} accentColor={accentColor} fontFamily={fontFamily} animation={motionStyle} localFrame={localFrame} durationFrames={durationFrames} fps={fps} />
        </AbsoluteFill>
      </AbsoluteFill>
    );
  }

  // ─── Typography-only motion graphic (no image) ───────────────────────────
  const panelOpacity = interpolate(localFrame, [0, 8, durationFrames - 10, durationFrames], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ zIndex: 2, pointerEvents: "none" }}>
      <AbsoluteFill style={{ background: `rgba(0,0,0,${backdropDim})`, backdropFilter: `blur(${backdropBlur}px)` }} />
      <AbsoluteFill
        style={{
          background: "linear-gradient(135deg, rgba(10,10,20,0.85) 0%, rgba(20,15,35,0.75) 100%)",
          opacity: panelOpacity,
        }}
      />
      {(motionStyle === "particle_float" || motionStyle === "particle_burst") && (
        <ParticleField count={36} color={accentColor} seed={event.start} />
      )}
      {motionStyle === "light_sweep" && <LightSweep progress={progress} />}
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", padding: "0 8%" }}>
        <KeywordText text={event.keyword} color={textColor} accentColor={accentColor} fontFamily={fontFamily} animation={motionStyle} localFrame={localFrame} durationFrames={durationFrames} fps={fps} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ─── Main BrollLayer ─────────────────────────────────────────────────────────

export const BrollLayer: React.FC<{
  events?: BrollEvent[];
  style?: BrollStyleConfig;
}> = ({ events = [], style = {} }) => {
  if (!events.length) return null;
  const globalStyle: BrollStyleConfig = {
    defaultMotionStyle: style.defaultMotionStyle || "ken_burns",
    fontFamily: style.fontFamily || "Poppins",
    textColor: style.textColor || "#FFFFFF",
    accentColor: style.accentColor || "#00E5C7",
    backdropDim: style.backdropDim ?? 0.45,
    backdropBlur: style.backdropBlur ?? 8,
  };
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {events.map((ev) => (
        <BrollEventView key={ev.id} event={ev} globalStyle={globalStyle} />
      ))}
    </AbsoluteFill>
  );
};

/** Check if the current frame is inside any B-roll event (for hiding subtitles). */
export const isFrameInBroll = (
  frame: number,
  fps: number,
  events: BrollEvent[] | undefined,
): boolean => (events || []).some((event) => {
  const start = Math.round(Number(event.start || 0) * fps);
  const end = Math.round(Number(event.end || 0) * fps);
  return frame >= start && frame < end;
});

export const HideDuringBroll: React.FC<{
  events?: BrollEvent[];
  children: React.ReactNode;
}> = ({ events, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return isFrameInBroll(frame, fps, events) ? null : <>{children}</>;
};


