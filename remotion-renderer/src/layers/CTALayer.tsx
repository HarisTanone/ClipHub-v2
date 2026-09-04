import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

export interface CTAProps {
  enabled?: boolean;
  ctaType?: "card" | "text" | "both" | string;
  template?: "follow_badge" | "like_share" | "link_bio" | "subscribe_pill" | "comment_prompt" | "custom_card" | string;
  duration?: number;
  duration_sec?: number;
  text?: string;
  headline?: string;
  subhead?: string;
  buttonText?: string;
  selectedIcon?: "tiktok" | "instagram" | "youtube" | "bell" | "link" | "share" | "message" | "zap" | "user_plus" | "heart" | "star" | string;
  socialPlatform?: "tiktok" | "instagram" | "youtube" | "general" | "custom" | string;
  socialHandle?: string;
  position?: "bottom" | "center" | "lower-third" | "top" | string;
  bgBox?: boolean;
  animation?: "slide_up" | "pop_in" | "fade_bounce" | "glow_pulse" | "glitch" | string;
  primaryColor?: string;
  textColor?: string;
  backgroundColor?: string;
  bgOpacity?: number;
  fontSize?: number;
  fontFamily?: string;
  fontWeight?: string;
  showIcon?: boolean;
  showArrow?: boolean;
  avatarUrl?: string;
  // Legacy fields
  type?: string;
  handle?: string;
}

// Clean vector SVG icons for professional video end-cards (Zero Emojis)
const TikTokIcon: React.FC<{ size?: number; color?: string; style?: React.CSSProperties }> = ({ size = 18, color = "currentColor", style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={color} style={style}>
    <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.89 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.11V9.43a6.34 6.34 0 0 0-.79-.05 6.34 6.34 0 0 0-6.34 6.34 6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.34-6.34V8.71a8.21 8.21 0 0 0 4.76 1.52v-3.44a4.82 4.82 0 0 1-1-.1z" />
  </svg>
);

const InstagramIcon: React.FC<{ size?: number; color?: string; style?: React.CSSProperties }> = ({ size = 18, color = "currentColor", style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={style}>
    <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
    <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
    <line x1="17.5" y1="6.5" x2="17.51" y2="6.5" />
  </svg>
);

const YouTubeIcon: React.FC<{ size?: number; color?: string; style?: React.CSSProperties }> = ({ size = 18, color = "currentColor", style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={color} style={style}>
    <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
  </svg>
);

const BellIcon: React.FC<{ size?: number; color?: string; style?: React.CSSProperties }> = ({ size = 18, color = "currentColor", style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={style}>
    <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
    <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
  </svg>
);

const CheckIcon: React.FC<{ size?: number; color?: string; style?: React.CSSProperties }> = ({ size = 18, color = "currentColor", style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" style={style}>
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const PlusIcon: React.FC<{ size?: number; color?: string; style?: React.CSSProperties }> = ({ size = 18, color = "currentColor", style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={style}>
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
);

const ArrowUpRightIcon: React.FC<{ size?: number; color?: string; style?: React.CSSProperties }> = ({ size = 18, color = "currentColor", style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" style={style}>
    <line x1="7" y1="17" x2="17" y2="7" />
    <polyline points="7 7 17 7 17 17" />
  </svg>
);

const ShareIcon: React.FC<{ size?: number; color?: string; style?: React.CSSProperties }> = ({ size = 18, color = "currentColor", style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={style}>
    <circle cx="18" cy="5" r="3" />
    <circle cx="6" cy="12" r="3" />
    <circle cx="18" cy="19" r="3" />
    <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
    <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
  </svg>
);

const MessageIcon: React.FC<{ size?: number; color?: string; style?: React.CSSProperties }> = ({ size = 18, color = "currentColor", style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={style}>
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);

const ZapIcon: React.FC<{ size?: number; color?: string; style?: React.CSSProperties }> = ({ size = 18, color = "currentColor", style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={style}>
    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
  </svg>
);

const HeartIcon: React.FC<{ size?: number; color?: string; style?: React.CSSProperties }> = ({ size = 18, color = "currentColor", style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={style}>
    <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
  </svg>
);

const StarIcon: React.FC<{ size?: number; color?: string; style?: React.CSSProperties }> = ({ size = 18, color = "currentColor", style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={style}>
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
);

function renderVectorIcon(iconId: string, size: number, color: string = "#FFFFFF") {
  switch (iconId) {
    case "tiktok": return <TikTokIcon size={size} color={color} />;
    case "instagram": return <InstagramIcon size={size} color={color} />;
    case "youtube": return <YouTubeIcon size={size} color={color} />;
    case "bell": return <BellIcon size={size} color={color} />;
    case "link": return <ArrowUpRightIcon size={size} color={color} />;
    case "share": return <ShareIcon size={size} color={color} />;
    case "message": return <MessageIcon size={size} color={color} />;
    case "zap": return <ZapIcon size={size} color={color} />;
    case "user_plus": return <PlusIcon size={size} color={color} />;
    case "heart": return <HeartIcon size={size} color={color} />;
    case "star": return <StarIcon size={size} color={color} />;
    default: return <PlusIcon size={size} color={color} />;
  }
}

/**
 * End-card CTA Layer — rendered during the final N seconds (1.0s - 6.0s, default 3.0s)
 * Supporting 3 Modes: Plain Text, Social Creator Card, & Text + Vector SVG Icon.
 */
export const CTALayer: React.FC<{ cta?: CTAProps | null; clipDurationSec: number }> = ({
  cta,
  clipDurationSec,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (!cta) return null;
  if (cta.enabled === false) return null;

  const rawDur = typeof cta.duration === "number" ? cta.duration : (typeof cta.duration_sec === "number" ? cta.duration_sec : 3.0);
  const durationSec = Math.max(1.0, Math.min(6.0, rawDur || 3.0));

  const startSec = Math.max(0, clipDurationSec - durationSec);
  const startFrame = Math.floor(startSec * fps);
  if (frame < startFrame) return null;

  const local = frame - startFrame;

  // Spring animation calculations
  const anim = cta.animation || "slide_up";
  const enterSpring = spring({ frame: local, fps, config: { damping: 14, stiffness: 180, mass: 0.6 } });
  const bounceSpring = spring({ frame: local, fps, config: { damping: 9, stiffness: 240, mass: 0.5 } });

  let translateY = 0;
  let scale = 1;
  let opacity = 1;

  if (anim === "pop_in") {
    scale = interpolate(bounceSpring, [0, 1], [0.6, 1]);
    opacity = interpolate(enterSpring, [0, 0.4, 1], [0, 1, 1]);
  } else if (anim === "fade_bounce") {
    scale = interpolate(bounceSpring, [0, 1], [0.85, 1]);
    translateY = interpolate(bounceSpring, [0, 1], [25, 0]);
    opacity = interpolate(enterSpring, [0, 1], [0, 1]);
  } else if (anim === "glow_pulse") {
    scale = 1 + Math.sin(local * 0.15) * 0.03;
    opacity = interpolate(enterSpring, [0, 1], [0, 1]);
  } else if (anim === "glitch") {
    translateY = local < 6 ? (local % 2 === 0 ? -3 : 3) : 0;
    scale = local < 6 ? 1.04 : 1;
    opacity = local < 2 ? 0.6 : 1;
  } else {
    // Default slide_up
    translateY = interpolate(enterSpring, [0, 1], [50, 0]);
    opacity = interpolate(enterSpring, [0, 1], [0, 1]);
  }

  // Positioning
  const pos = cta.position || "bottom";
  let positionStyle: React.CSSProperties = {
    position: "absolute",
    left: "50%",
    transform: `translateX(-50%) translateY(${translateY}px) scale(${scale})`,
    opacity,
  };

  if (pos === "top") {
    positionStyle.top = "8%";
  } else if (pos === "center") {
    positionStyle.top = "50%";
    positionStyle.transform = `translateX(-50%) translateY(-50%) translateY(${translateY}px) scale(${scale})`;
  } else if (pos === "lower-third") {
    positionStyle.bottom = "20%";
  } else {
    // bottom
    positionStyle.bottom = "7%";
  }

  // Extract template & mode properties (supports both camelCase and snake_case)
  const anyCta = cta as any;
  const ctaType = cta.ctaType || anyCta.cta_type || "card";
  const template = cta.template || "follow_badge";
  const plainText = cta.text || anyCta.cta_text || cta.headline || "Follow Untuk Tips Berikutnya!";
  const headline = cta.headline || anyCta.cta_headline || cta.text || "Follow For More";
  const subhead = cta.subhead || (cta.socialHandle || cta.handle ? (cta.socialHandle || cta.handle) : (anyCta.social_handle || ""));
  const buttonText = cta.buttonText || anyCta.button_text || (template === "subscribe_pill" ? "SUBSCRIBE" : template === "link_bio" ? "KLIK LINK" : template === "like_share" ? "BAGIKAN" : template === "comment_prompt" ? "KOMEN" : template === "custom_card" ? "JOIN NOW" : "FOLLOW");
  const primaryColor = cta.primaryColor || anyCta.primary_color || (template === "subscribe_pill" ? "#EF4444" : template === "link_bio" ? "#3B82F6" : "#10B981");
  const textColor = cta.textColor || anyCta.text_color || "#FFFFFF";
  const rawBgOp = typeof cta.bgOpacity === "number" ? cta.bgOpacity : (typeof anyCta.bg_opacity === "number" ? anyCta.bg_opacity : 92);
  const bgOpacity = rawBgOp / 100;
  const bgColor = cta.backgroundColor || anyCta.background_color || anyCta.bg_color || "#0F172A";
  const fontFamily = cta.fontFamily || anyCta.font_family || "Poppins, Montserrat, sans-serif";
  const fontSize = cta.fontSize || anyCta.font_size || 26;
  const fontWeight = cta.fontWeight || anyCta.font_weight || "700";
  const bgBox = cta.bgBox !== false && anyCta.bg_box !== false;
  const selectedIcon = cta.selectedIcon || anyCta.selected_icon || "tiktok";

  // Dynamic button state
  const isFollowed = (template === "follow_badge" || cta.socialPlatform === "tiktok") && local > 25;
  const bellSwing = template === "subscribe_pill" ? Math.sin(local * 0.4) * 14 : 0;
  const iconSize = Math.max(14, fontSize - 10);

  // 1. PLAIN TEXT MODE
  if (ctaType === "text") {
    return (
      <AbsoluteFill style={{ pointerEvents: "none", zIndex: 35 }}>
        <div
          style={{
            ...positionStyle,
            width: "88%",
            maxWidth: 520,
            textAlign: "center",
            fontFamily,
            color: textColor,
            ...(bgBox
              ? {
                background: bgColor.startsWith("#")
                  ? `${bgColor}${Math.round(bgOpacity * 255).toString(16).padStart(2, "0")}`
                  : bgColor,
                backdropFilter: "blur(16px)",
                WebkitBackdropFilter: "blur(16px)",
                borderRadius: 20,
                padding: "14px 22px",
                border: `1.5px solid ${primaryColor}55`,
                boxShadow: `0 16px 40px rgba(0,0,0,0.6), 0 0 25px ${primaryColor}33`,
              }
              : {
                padding: "8px 12px",
              }),
          }}
        >
          <p
            style={{
              margin: 0,
              fontSize,
              fontWeight,
              lineHeight: 1.3,
              textShadow: bgBox ? "0 2px 8px rgba(0,0,0,0.5)" : "0 3px 12px rgba(0,0,0,0.9), 0 0 8px #000000",
            }}
          >
            {plainText}
          </p>
        </div>
      </AbsoluteFill>
    );
  }

  // 2. TEXT + ICON (BOTH) MODE
  if (ctaType === "both") {
    return (
      <AbsoluteFill style={{ pointerEvents: "none", zIndex: 35 }}>
        <div
          style={{
            ...positionStyle,
            width: "auto",
            maxWidth: "90%",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 12,
            fontFamily,
            color: textColor,
            ...(bgBox
              ? {
                background: bgColor.startsWith("#")
                  ? `${bgColor}${Math.round(bgOpacity * 255).toString(16).padStart(2, "0")}`
                  : bgColor,
                backdropFilter: "blur(16px)",
                WebkitBackdropFilter: "blur(16px)",
                borderRadius: 999,
                padding: "12px 24px",
                border: `1.5px solid ${primaryColor}55`,
                boxShadow: `0 16px 40px rgba(0,0,0,0.6), 0 0 25px ${primaryColor}33`,
              }
              : {
                padding: "8px 16px",
              }),
          }}
        >
          <div
            style={{
              padding: 8,
              borderRadius: "50%",
              backgroundColor: primaryColor,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: `0 4px 12px ${primaryColor}66`,
              flexShrink: 0,
            }}
          >
            {renderVectorIcon(selectedIcon, iconSize, "#FFFFFF")}
          </div>
          <p
            style={{
              margin: 0,
              fontSize,
              fontWeight,
              lineHeight: 1.2,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              textShadow: bgBox ? "0 2px 8px rgba(0,0,0,0.5)" : "0 3px 12px rgba(0,0,0,0.9), 0 0 8px #000000",
            }}
          >
            {plainText}
          </p>
        </div>
      </AbsoluteFill>
    );
  }

  // 3. CARD MODE (Default)
  return (
    <AbsoluteFill style={{ pointerEvents: "none", zIndex: 35 }}>
      <div
        style={{
          ...positionStyle,
          width: "90%",
          maxWidth: 480,
          background: bgColor.startsWith("#")
            ? `${bgColor}${Math.round(bgOpacity * 255).toString(16).padStart(2, "0")}`
            : bgColor,
          backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)",
          borderRadius: 24,
          padding: "16px 20px",
          border: `1.5px solid ${primaryColor}55`,
          boxShadow: `0 16px 40px rgba(0,0,0,0.6), 0 0 25px ${primaryColor}33`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 14,
          color: textColor,
          fontFamily,
        }}
      >
        {/* Left: Text Info */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <div
            style={{
              fontSize,
              fontWeight,
              lineHeight: 1.25,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              textShadow: "0 2px 10px rgba(0,0,0,0.5)",
            }}
          >
            {headline}
          </div>
          {subhead && (
            <div
              style={{
                marginTop: 8,
                fontSize: Math.max(13, fontSize - 10),
                fontWeight: 500,
                opacity: 0.9,
                color: "#94A3B8",
                lineHeight: 1.2,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {subhead}
            </div>
          )}
        </div>

        {/* Right: Interactive Badge / Action Button */}
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            padding: "10px 18px",
            borderRadius: 999,
            background: isFollowed ? "#10B981" : primaryColor,
            color: "#FFFFFF",
            fontWeight: 800,
            fontSize: Math.max(13, fontSize - 10),
            letterSpacing: 0.5,
            boxShadow: `0 4px 15px ${primaryColor}66`,
            flexShrink: 0,
            transition: "all 0.3s ease",
          }}
        >
          {template === "subscribe_pill" && (
            <div style={{ transform: `rotate(${bellSwing}deg)`, display: "flex", alignItems: "center", transformOrigin: "top center" }}>
              <BellIcon size={iconSize} color="#FFFFFF" />
            </div>
          )}
          {template === "follow_badge" && (
            <div style={{ display: "flex", alignItems: "center" }}>
              {isFollowed ? <CheckIcon size={iconSize} color="#FFFFFF" /> : <PlusIcon size={iconSize} color="#FFFFFF" />}
            </div>
          )}
          {template === "link_bio" && (
            <div style={{ display: "flex", alignItems: "center" }}>
              <ArrowUpRightIcon size={iconSize} color="#FFFFFF" />
            </div>
          )}
          {template === "like_share" && (
            <div style={{ display: "flex", alignItems: "center" }}>
              <ShareIcon size={iconSize} color="#FFFFFF" />
            </div>
          )}
          {template === "comment_prompt" && (
            <div style={{ display: "flex", alignItems: "center" }}>
              <MessageIcon size={iconSize} color="#FFFFFF" />
            </div>
          )}
          {template === "custom_card" && (
            <div style={{ display: "flex", alignItems: "center" }}>
              <ZapIcon size={iconSize} color="#FFFFFF" />
            </div>
          )}
          <span>{isFollowed ? "FOLLOWED" : buttonText}</span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
