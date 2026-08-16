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

// ─── Bespoke Vector SVG Icons (No Emojis) ───────────────────────────────────

const VectorFlameIcon: React.FC<{ color: string }> = ({ color }) => (
  <svg width="38" height="38" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M12 2C10.5 4.5 9 6.5 9 9C9 10.66 10.34 12 12 12C13.66 12 15 10.66 15 9C15 6.5 13.5 4.5 12 2Z"
      fill={color}
      opacity="0.9"
    />
    <path
      d="M17.5 8C17.5 8 16.5 10 16.5 11.5C16.5 13.98 14.48 16 12 16C9.52 16 7.5 13.98 7.5 11.5C7.5 9.5 8.5 7.5 9.5 6C6.5 7.5 4.5 10.5 4.5 14C4.5 18.14 7.86 21.5 12 21.5C16.14 21.5 19.5 18.14 19.5 14C19.5 11.5 18.7 9.5 17.5 8Z"
      fill={color}
    />
  </svg>
);

const VectorRocketIcon: React.FC<{ color: string }> = ({ color }) => (
  <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z" />
    <path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z" />
    <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0" />
    <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" />
  </svg>
);

const VectorProfitIcon: React.FC<{ color: string }> = ({ color }) => (
  <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v10" />
    <path d="M15 9.5a2.5 2.5 0 0 0-5 0c0 2 5 2 5 4a2.5 2.5 0 0 1-5 0" />
  </svg>
);

const VectorIdeaIcon: React.FC<{ color: string }> = ({ color }) => (
  <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5" />
    <path d="M9 18h6" />
    <path d="M10 22h4" />
  </svg>
);

const VectorChartIcon: React.FC<{ color: string }> = ({ color }) => (
  <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
    <polyline points="16 7 22 7 22 13" />
  </svg>
);

const VectorWarningIcon: React.FC<{ color: string }> = ({ color }) => (
  <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);

const VectorQuestionIcon: React.FC<{ color: string }> = ({ color }) => (
  <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="9" />
    <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);

const VectorTrophyIcon: React.FC<{ color: string }> = ({ color }) => (
  <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6" />
    <path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18" />
    <path d="M4 22h16" />
    <path d="M10 14.66V17c0 .55-.45 1-1 1H8v4h8v-4h-1c-.55 0-1-.45-1-1v-2.34" />
    <path d="M6 4h12a2 2 0 0 1 2 2v3a6 6 0 0 1-6 6h0a6 6 0 0 1-6-6V6a2 2 0 0 1 2-2Z" />
  </svg>
);

// ─── Reaction Badge Catalog & Detector ────────────────────────────────────────

const REACTION_BADGES: Record<
  string,
  { icon: React.FC<{ color: string }>; color: string; label: string }
> = {
  fire: { icon: VectorFlameIcon, color: "#FF4500", label: "HOT TOPIC" },
  rocket: { icon: VectorRocketIcon, color: "#6366F1", label: "SCALE & GROW" },
  money: { icon: VectorProfitIcon, color: "#10B981", label: "HIGH VALUE" },
  profit: { icon: VectorProfitIcon, color: "#10B981", label: "HIGH VALUE" },
  idea: { icon: VectorIdeaIcon, color: "#F59E0B", label: "KEY INSIGHT" },
  growth: { icon: VectorChartIcon, color: "#10B981", label: "TRENDING UP" },
  chart: { icon: VectorChartIcon, color: "#10B981", label: "TRENDING UP" },
  warning: { icon: VectorWarningIcon, color: "#EF4444", label: "IMPORTANT" },
  important: { icon: VectorWarningIcon, color: "#EF4444", label: "IMPORTANT" },
  question: { icon: VectorQuestionIcon, color: "#3B82F6", label: "KEY QUESTION" },
  success: { icon: VectorTrophyIcon, color: "#F59E0B", label: "WINNER" },
};

function getReactionForText(text: string) {
  const lower = text.toLowerCase();
  for (const [key, val] of Object.entries(REACTION_BADGES)) {
    if (lower.includes(key)) {
      return val;
    }
  }
  return null;
}

const ReactionBadge: React.FC<{
  badge: { icon: React.FC<{ color: string }>; color: string; label: string };
  localFrame: number;
  fps: number;
}> = ({ badge, localFrame, fps }) => {
  const bounce = spring({ frame: localFrame, fps, config: { damping: 11, stiffness: 220, mass: 0.5 } });
  const rotate = interpolate(bounce, [0, 1], [-12, 0]);
  const IconComponent = badge.icon;

  return (
    <div
      style={{
        display: "inline-flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 8,
        transform: `scale(${bounce}) rotate(${rotate}deg)`,
        marginBottom: 14,
      }}
    >
      <div
        style={{
          width: 72,
          height: 72,
          borderRadius: 22,
          background: `linear-gradient(135deg, ${badge.color}25, ${badge.color}55)`,
          border: `1.5px solid ${badge.color}88`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: `0 14px 36px ${badge.color}45, 0 4px 14px rgba(0,0,0,0.6)`,
          backdropFilter: "blur(12px)",
        }}
      >
        <IconComponent color={badge.color} />
      </div>
      <span
        style={{
          fontSize: 10,
          fontWeight: 900,
          letterSpacing: 1.5,
          color: "#fff",
          background: `linear-gradient(90deg, ${badge.color}99, ${badge.color}dd)`,
          padding: "3px 10px",
          borderRadius: 99,
          border: `1px solid rgba(255,255,255,0.25)`,
          boxShadow: `0 4px 12px ${badge.color}44`,
          textTransform: "uppercase",
        }}
      >
        {badge.label}
      </span>
    </div>
  );
};

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
  const enter = spring({ frame: localFrame, fps, config: { damping: 14, stiffness: 210, mass: 0.6 } });
  const exitStart = Math.max(0, durationFrames - 10);
  const exitOpacity = interpolate(localFrame, [exitStart, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const reaction = getReactionForText(text);

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
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
        {reaction && <ReactionBadge badge={reaction} localFrame={localFrame} fps={fps} />}
        <div style={{ ...baseStyle, fontSize: 54, opacity: exitOpacity, fontFamily: `'${fontFamily}', monospace` }}>
          {shown}
          <span style={{ color: accentColor || color, opacity: 0.8 }}>{caret}</span>
        </div>
      </div>
    );
  }

  if (animation === "stroke_draw") {
    const reveal = clamp(localFrame / Math.max(8, durationFrames * 0.6), 0, 1);
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
        {reaction && <ReactionBadge badge={reaction} localFrame={localFrame} fps={fps} />}
        <div style={{ ...baseStyle, fontSize: 60, opacity: exitOpacity, WebkitTextStroke: `2px ${accentColor || color}`, color: "transparent" }}>
          <span style={{ clipPath: `inset(0 ${(1 - reveal) * 100}% 0 0)`, display: "inline-block" }}>{text}</span>
        </div>
      </div>
    );
  }

  if (animation === "glitch_reveal") {
    const offset = interpolate(enter, [0, 0.3, 0.6, 1], [-8, 5, -3, 0]);
    const rgbSplit = localFrame < 12 ? Math.abs(offset) : 0;
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
        {reaction && <ReactionBadge badge={reaction} localFrame={localFrame} fps={fps} />}
        <div style={{ position: "relative", opacity: exitOpacity }}>
          <div style={{ ...baseStyle, fontSize: 58, transform: `translateX(${offset}px)`, color }}>{text}</div>
          {rgbSplit > 0 && (
            <>
              <div style={{ ...baseStyle, fontSize: 58, position: "absolute", top: 0, left: 0, right: 0, transform: `translateX(${rgbSplit}px)`, color: "#ff0040", opacity: 0.7, mixBlendMode: "screen" }}>{text}</div>
              <div style={{ ...baseStyle, fontSize: 58, position: "absolute", top: 0, left: 0, right: 0, transform: `translateX(${-rgbSplit}px)`, color: "#00ffff", opacity: 0.7, mixBlendMode: "screen" }}>{text}</div>
            </>
          )}
        </div>
      </div>
    );
  }

  if (animation === "word_pop" || animation === "particle_burst") {
    const scale = interpolate(enter, [0, 1], [0.3, 1]);
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
        {reaction && <ReactionBadge badge={reaction} localFrame={localFrame} fps={fps} />}
        <div style={{ ...baseStyle, fontSize: 64, transform: `scale(${scale})`, opacity: exitOpacity * enter }}>
          {text}
        </div>
      </div>
    );
  }

  if (animation === "line_reveal") {
    const reveal = clamp(localFrame / Math.max(6, durationFrames * 0.4), 0, 1);
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
        {reaction && <ReactionBadge badge={reaction} localFrame={localFrame} fps={fps} />}
        <div style={{ position: "relative", opacity: exitOpacity }}>
          <div style={{ ...baseStyle, fontSize: 56, clipPath: `inset(0 ${(1 - reveal) * 100}% 0 0)` }}>{text}</div>
          <div style={{ height: 3, background: accentColor || color, width: `${reveal * 100}%`, margin: "8px auto 0", boxShadow: `0 0 12px ${accentColor || color}` }} />
        </div>
      </div>
    );
  }

  // Default: ken_burns, parallax_zoom, light_sweep, depth_parallax, particle_float
  const yShift = interpolate(enter, [0, 1], [24, 0]);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
      {reaction && <ReactionBadge badge={reaction} localFrame={localFrame} fps={fps} />}
      <div style={{ ...baseStyle, fontSize: 60, transform: `translateY(${yShift}px)`, opacity: exitOpacity * enter }}>
        {text}
      </div>
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
      const panX = interpolate(progress, [0, 1], [-2.5, 2.5]);
      const panY = interpolate(progress, [0, 1], [-1.5, 1.5]);
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


