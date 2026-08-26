import { cn } from "@/lib/utils";
import type { SubtitleStyle } from "../types";
import { SUBTITLE_TRANSITION_META } from "../types";

export function SubtitlePresetCard({
  preset,
  active,
  onClick,
}: {
  preset: { id: string; name: string; style: Partial<SubtitleStyle> };
  active: boolean;
  onClick: () => void;
}) {
  const transition = preset.style.lineTransition || "word_pop";
  const meta = SUBTITLE_TRANSITION_META[transition] || SUBTITLE_TRANSITION_META.word_pop;
  const font = preset.style.fontFamily || "Poppins";
  const color = preset.style.highlightColor || meta.accent;
  const presetKey = preset.style.stylePreset || "classic";
  const isLightCard = presetKey === "bubble_chat" || presetKey === "breaking_tape" || presetKey === "quote_box" || presetKey === "word_tiles";
  const previewBg = preset.style.bgEnabled === false
    ? "transparent"
    : preset.style.bgColor
      ? `${preset.style.bgColor}${Math.round((preset.style.bgOpacity ?? 0.45) * 255).toString(16).padStart(2, "0")}`
      : "rgba(0,0,0,0.28)";
  const previewRadius = presetKey === "caption_strip" ? 0 : presetKey === "breaking_tape" ? 2 : presetKey === "bubble_chat" || presetKey === "gradient_glass" ? 14 : preset.style.bgRadius ?? 6;
  const previewTransform = presetKey === "breaking_tape" ? "rotate(-1.5deg)" : undefined;

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group min-h-[92px] rounded-lg border p-3 text-left transition-all",
        active ? "border-emerald-400 bg-emerald-500/10 ring-1 ring-emerald-400/25" : "border-zinc-800 bg-zinc-900/70 hover:border-zinc-600 hover:bg-zinc-900"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className={cn("text-[12px] font-semibold truncate", active ? "text-emerald-300" : "text-zinc-200")}>{preset.name}</p>
          <p className="mt-0.5 text-[9px] text-zinc-500 truncate">{meta.label} / {font}</p>
        </div>
        <span className="h-5 min-w-5 rounded-full border" style={{ backgroundColor: `${color}22`, borderColor: `${color}66` }} />
      </div>
      <div
        className={cn(
          "relative mt-3 flex flex-wrap items-center justify-center gap-1.5 overflow-hidden border px-2 py-2",
          isLightCard ? "border-black/10" : "border-white/10",
          presetKey === "lower_third" && "justify-start"
        )}
        style={{
          backgroundColor: previewBg,
          borderRadius: previewRadius,
          transform: previewTransform,
          boxShadow: presetKey === "neon_pulse" ? `0 0 22px ${color}44` : undefined,
        }}
      >
        {(presetKey === "editorial_banner" || presetKey === "lower_third" || presetKey === "documentary") && (
          <span className="absolute left-0 top-0 h-full w-1.5" style={{ backgroundColor: color }} />
        )}
        {presetKey === "neon_pulse" && (
          <span className="absolute inset-x-3 top-1 h-0.5 rounded-full" style={{ backgroundColor: color, boxShadow: `0 0 12px ${color}` }} />
        )}
        {presetKey === "bubble_chat" && (
          <span className="absolute bottom-[-5px] left-7 h-3 w-3 rotate-45" style={{ backgroundColor: previewBg }} />
        )}
        {["ini", "kata", "penting"].map((word, index) => (
          <span
            key={word}
            style={{
              color: index === 1 ? color : preset.style.color || "#FFFFFF",
              fontFamily: index === 1 && preset.style.dualStyleEnabled ? `'${preset.style.highlightFontFamily || "Anton"}', sans-serif` : `'${font}', sans-serif`,
              fontWeight: index === 1 ? 900 : Number(preset.style.fontWeight || 700),
              WebkitTextStroke: presetKey === "meme_impact" && index !== 1 ? "0.5px #000" : undefined,
              textShadow: presetKey === "neon_pulse" && index === 1 ? `0 0 10px ${color}` : undefined,
              textTransform: preset.style.uppercase || (index === 1 && preset.style.highlightUppercase) ? "uppercase" : "none",
            }}
            className={cn("relative z-10 text-[11px]", index === 1 && "scale-110")}
          >
            {word}
          </span>
        ))}
      </div>
    </button>
  );
}
