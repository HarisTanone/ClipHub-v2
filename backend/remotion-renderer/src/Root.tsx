import { Composition } from "remotion";
import { ClipComposition } from "./compositions/ClipComposition";
import { TikTokComposition } from "./compositions/TikTokComposition";
import { CreativeComposition } from "./compositions/CreativeComposition";
import type { ClipCompositionProps } from "./types";

export const RemotionRoot: React.FC = () => {
  const defaultProps: ClipCompositionProps = {
    sceneGraph: { clip_rank: 1, duration: 30, layers: [] },
    creativeDirection: {
      primary_color: "#FFFFFF",
      secondary_color: "#FFCC00",
      hook_style_config: {},
      subtitle_style_config: {},
    },
    videoPath: "",
    words: [],
    hookText: "",
    hookAnimation: "fade_scale",
    enableThreeJS: false,
    enableAI: false,
  };

  return (
    <>
      <Composition id="ClipComposition" component={ClipComposition as any} durationInFrames={900} fps={30} width={1080} height={1920} defaultProps={defaultProps} />
      <Composition id="TikTokComposition" component={TikTokComposition as any} durationInFrames={900} fps={30} width={1080} height={1920} defaultProps={defaultProps} />
      <Composition id="CreativeComposition" component={CreativeComposition as any} durationInFrames={900} fps={30} width={1080} height={1920} defaultProps={defaultProps} />
    </>
  );
};
