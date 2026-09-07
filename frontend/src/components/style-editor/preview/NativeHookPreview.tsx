import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Loader2, RefreshCw } from "lucide-react";
import { getToken, hookPreviewApi } from "@/lib/api";
import type { HookStyle } from "../types";
import { getHookPreviewSample } from "../utils";

interface NativeHookPreviewProps {
  style: HookStyle;
  preset?: string | null;
  frame?: number;
}

export function NativeHookPreview({ style, preset, frame = 30 }: NativeHookPreviewProps) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [specHash, setSpecHash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const text = style.text?.trim() || getHookPreviewSample(style.animation);
  const payloadKey = useMemo(
    () => JSON.stringify({ preset: preset || null, config: style, text, frame }),
    [preset, style, text, frame],
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await hookPreviewApi.render(
          { preset: preset || null, config: style as unknown as Record<string, unknown>, text, frame },
          controller.signal,
        );
        if (controller.signal.aborted) return;
        const token = getToken();
        const separator = result.image_url.includes("?") ? "&" : "?";
        setImageUrl(token ? `${result.image_url}${separator}token=${encodeURIComponent(token)}` : result.image_url);
        setSpecHash(result.hash);
      } catch (cause) {
        if (controller.signal.aborted) return;
        setImageUrl(null);
        setSpecHash(null);
        setError(cause instanceof Error ? cause.message : "Native Hook preview gagal dirender");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [payloadKey, retry]);

  return (
    <div className="flex w-full flex-col items-center gap-3">
      <div className="mb-1 flex w-full items-center justify-between gap-2">
        <p className="text-[9px] uppercase tracking-widest text-zinc-600">Native Preview</p>
        <span className="rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-[9px] text-zinc-400">
          {style.engine || "remotion"}
        </span>
      </div>
      <div className="relative aspect-[9/16] w-full max-w-[270px] overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950">
        {imageUrl && !error && (
          <img
            src={imageUrl}
            alt={`Native Hook preview ${style.engine || "remotion"}`}
            className="h-full w-full object-cover"
            onError={() => setError("Artifact native preview tidak dapat dimuat")}
          />
        )}
        {loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-zinc-950/80 text-zinc-400">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span className="text-[10px]">Rendering native frame</span>
          </div>
        )}
        {!loading && error && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-5 text-center">
            <AlertCircle className="h-5 w-5 text-red-400" />
            <p className="text-[10px] leading-relaxed text-red-300">{error}</p>
            <button
              type="button"
              onClick={() => setRetry((value) => value + 1)}
              className="flex items-center gap-1.5 rounded-md border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-[10px] text-zinc-300 hover:bg-zinc-800"
            >
              <RefreshCw className="h-3 w-3" /> Coba lagi
            </button>
          </div>
        )}
      </div>
      <p className="h-3 font-mono text-[8px] text-zinc-700">
        {specHash ? `spec ${specHash.slice(0, 12)}` : ""}
      </p>
    </div>
  );
}
