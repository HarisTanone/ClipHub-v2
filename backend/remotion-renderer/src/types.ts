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
}

/** Word-level timestamps from Whisper */
export interface Word {
  word: string;
  start: number;
  end: number;
  highlight?: boolean;
}

/** Props for the main ClipComposition */
export interface ClipCompositionProps {
  sceneGraph: SceneGraph;
  creativeDirection: CreativeDirection;
  videoPath: string;
  words: Word[];
  hookText: string;
  hookAnimation: string;
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
