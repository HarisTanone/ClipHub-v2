import { cn } from "@/lib/utils";
import type { HookStyle } from "../types";
import { HOOK_ANIMATION_META } from "../types";
import { getHookPreviewSample } from "../utils";

export function HookPresetCard({
  preset,
  active,
  onClick,
}: {
  preset: { id: string; name: string; style: Partial<HookStyle> };
  active: boolean;
  onClick: () => void;
}) {
  const animation = preset.style.animation || "podcast_lower_third";
  const meta = HOOK_ANIMATION_META[animation] || HOOK_ANIMATION_META.podcast_lower_third;
  const font = preset.style.fontFamily || "Poppins";
  const color = preset.style.gradientEnabled ? preset.style.gradientTo || meta.accent : preset.style.color || meta.accent;

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative min-h-[98px] rounded-lg border p-3 text-left overflow-hidden transition-all",
        active
          ? "border-emerald-400 bg-emerald-500/10 ring-1 ring-emerald-400/25"
          : "border-zinc-800 bg-zinc-900/70 hover:border-zinc-600 hover:bg-zinc-900"
      )}
    >
      <div className="absolute inset-x-0 top-0 h-1" style={{ background: `linear-gradient(90deg, ${meta.accent}, transparent)` }} />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className={cn("text-[12px] font-semibold truncate", active ? "text-emerald-300" : "text-zinc-200")}>{preset.name}</p>
          <p className="mt-0.5 text-[9px] text-zinc-500 truncate">{meta.label} / {font}</p>
        </div>
        <span className="rounded-md px-1.5 py-0.5 text-[8px] font-black" style={{ color, backgroundColor: `${color}18`, border: `1px solid ${color}44` }}>
          {meta.preview}
        </span>
      </div>
      <div className="mt-3 flex items-end gap-2">
        <div className="flex-1 min-w-0">
          <div className="h-8 rounded-md border border-white/10 bg-black/30 px-2 flex items-center overflow-hidden">
            <span
              style={{
                color,
                fontFamily: font === "monospace" ? "monospace" : `'${font}', sans-serif`,
                fontWeight: Number(preset.style.fontWeight || 800),
                letterSpacing: 0,
              }}
              className="text-[11px] truncate"
            >
              {getHookPreviewSample(animation)}
            </span>
          </div>
        </div>
        <span className="text-[8px] text-zinc-600 group-hover:text-zinc-400">{meta.mood}</span>
      </div>
    </button>
  );
}
