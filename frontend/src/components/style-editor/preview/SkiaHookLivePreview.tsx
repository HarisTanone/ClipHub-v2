import type { CanvasConfig } from "@/lib/canvasTemplates";
import type { HookStyle } from "../types";
import { NativeHookPreview } from "./NativeHookPreview";

interface SkiaHookLivePreviewProps {
  style: HookStyle;
  thumbnailUrl?: string;
  aspectRatio?: string;
  canvas?: CanvasConfig | null;
}

export { NativeHookPreview };

/**
 * SkiaHookLivePreview — 1:1 parity with final backend render.
 * Delegates to NativeHookPreview so preview pixels match final bake exactly.
 */
export function SkiaHookLivePreview({ style }: SkiaHookLivePreviewProps) {
  return <NativeHookPreview style={{ ...style, engine: "skia" }} preset={style.animation} frame={30} />;
}
