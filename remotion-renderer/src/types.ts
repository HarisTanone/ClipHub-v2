/** Scene graph from Python backend */
export interface SceneGraph {
  clip_rank: number;
  duration: number;
  layers: SceneLayer[];
}

export interface SceneLayer {
  id: string;
  type: string;
  z_index: number;
}

export interface SceneEvent {
  event_type: string;
  start: number;
  end: number;
  preset?: string;
  params?: Record<string, unknown>;
}

/** Creative direction + custom style configs */
export interface CreativeDirection {
  primary_color?: string;
  secondary_color?: string;
  background_accent?: string;
  typography_mood?: string;
  music_mood?: string;
  subtitle_uppercase?: boolean;
  subtitle_position?: string;
  // Custom style configs from editor
  hook_style_config?: Record<string, any>;
  subtitle_style_config?: Record<string, any>;
  text_emphasis_style_config?: TextEmphasisStyleConfig;
  // Auto zoom events from prosody analysis
  zoom_events?: Array<{ time: number; intensity?: number; duration?: number }>;
  reframe_method?: string;
  reframe_layout?: "single" | "double";
  layout_mode?: "static" | "dynamic";
  layout_events?: Array<{ time: number; layout: "single" | "double" }>;
  framing_events?: FramingEvent[];
  transition_style?: TransitionStyle;
  transition_duration?: number;
  subtitle_position_y?: number;
  content_profile?: Record<string, any>;
  // v3.1 B-roll motion graphic global style config (rendered in Remotion)
  broll_style_config?: BrollStyleConfig;
}

export type TransitionStyle = "cut" | "fade" | "slide" | "zoom";

export interface FramingEvent {
  time: number;
  kind: "speaker" | "layout";
  from?: number | string;
  to?: number | string;
}

/** Word-level timestamps from Whisper */
export interface Word {
  word: string;
  start: number;
  end: number;
  highlight?: boolean;
}

export type TextEmphasisEffect =
  | "behind_person"
  | "spotlight"
  | "side_label"
  | "floating_text"
  | "auto_avoid"
  | "around_head"
  | "depth_text"
  | "kinetic_type";

export interface PersonForegroundFrame {
  frame: number;
  path: string;
  x: number;
  y: number;
  width: number;
  height: number;
  // Optional person tracking metadata for advanced effects
  head_x?: number;
  head_y?: number;
  head_width?: number;
  head_height?: number;
  depth_z?: number; // Estimated depth (0 = far, 1 = near) for depth_text effect
}

export interface TextEmphasisEvent {
  id: string;
  start: number;
  end: number;
  text: string;
  effect: TextEmphasisEffect;
  position?: "left" | "center" | "right";
  source_width?: number;
  source_height?: number;
  foreground_frames?: PersonForegroundFrame[];
  fallback_reason?: string;
}

export interface TextEmphasisStyleConfig {
  effectMode?: "auto" | TextEmphasisEffect;
  animation?: "cinematic" | "slam" | "reveal" | "glitch" | "neon";
  fontFamily?: string;
  fontSize?: number;
  fontWeight?: string;
  letterSpacing?: number;
  lineHeight?: number;
  color?: string;
  accentColor?: string;
  uppercase?: boolean;
  strokeEnabled?: boolean;
  strokeColor?: string;
  strokeWidth?: number;
  shadowEnabled?: boolean;
  shadowColor?: string;
  shadowBlur?: number;
  positionY?: number;
  maxWidthPct?: number;
  // New: effect-specific tuning
  floatSpeed?: number; // For floating_text: vertical oscillation speed (0.5-3.0)
  avoidPadding?: number; // For auto_avoid: padding around person bbox (px)
  aroundHeadRadius?: number; // For around_head: radius from head center (%)
  depthIntensity?: number; // For depth_text: parallax intensity (0.1-1.0)
  depthParallax?: number; // For depth_text: foreground/background separation scale (0.05-1.0)
  depthFade?: number; // For depth_text: enter/exit fade duration in seconds (0.1-1.5)
  kineticStagger?: number; // For kinetic_type: word stagger delay (frames)
}

// ─── B-Roll Motion Graphic Events (rendered in Remotion) ─────────────────────
// When broll_enabled, each BRollSuggestion with a motion_graphic style is
// rendered as a Remotion layer (consistent with preview).  This replaces
// the legacy FFmpeg drawtext/overlay path for motion-graphic styles so that
// what the user sees in preview matches the final render exactly.

export type BrollMotionStyle =
  | "ken_burns" // Slow zoom + pan (documentary style)
  | "parallax_zoom" // Depth-based zoom with parallax layers
  | "light_sweep" // Light sweep across image + text reveal
  | "particle_float" // Floating particles + text
  | "depth_parallax" // Foreground/background parallax
  | "glitch_reveal" // Glitch + reveal
  | "typewriter" // Typewriter text
  | "stroke_draw" // SVG stroke draw text
  | "word_pop" // Legacy compatibility: scale/pop text
  | "line_reveal" // Legacy compatibility: mask wipe
  | "particle_burst"; // Legacy compatibility: particle burst

export interface BrollEvent {
  id: string;
  start: number; // seconds (relative to clip)
  end: number; // seconds (relative to clip)
  keyword: string; // Text to display
  motionStyle: BrollMotionStyle;
  // Optional static image asset (local path or URL). If absent, renders as
  // motion typography on a dark gradient background.
  imagePath?: string;
  // Optional styling overrides
  textColor?: string;
  accentColor?: string;
  fontFamily?: string;
}

export interface BrollStyleConfig {
  // Global defaults applied to all B-roll events unless overridden per-event.
  defaultMotionStyle?: BrollMotionStyle;
  fontFamily?: string;
  textColor?: string;
  accentColor?: string;
  // 0..1 — how much the B-roll darkens/blurs the underlying video while active.
  backdropDim?: number;
  backdropBlur?: number; // px
}

/** Props for the main ClipComposition */
export interface ClipCompositionProps {
  sceneGraph: SceneGraph;
  creativeDirection: CreativeDirection;
  videoPath: string;
  words: Word[];
  hookText: string;
  hookAnimation: string;
  textEmphasisEvents?: TextEmphasisEvent[];
  brollEvents?: BrollEvent[];
  enableThreeJS: boolean;
  enableAI: boolean;
}

/** Render request from Python backend */
export interface RenderRequest {
  compositionId: string;
  outputPath: string;
  props: ClipCompositionProps;
  durationInFrames: number;
  fps: number;
  width: number;
  height: number;
  codec?: string;
  quality?: "low" | "medium" | "high";
  concurrency?: number;
}

/** Render response */
export interface RenderResponse {
  success: boolean;
  outputPath?: string;
  renderTimeSeconds?: number;
  error?: string;
}
