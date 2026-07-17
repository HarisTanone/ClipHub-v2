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

export type TextEmphasisEffect = "behind_person" | "spotlight" | "side_label";

export interface PersonForegroundFrame {
  frame: number;
  path: string;
  x: number;
  y: number;
  width: number;
  height: number;
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
