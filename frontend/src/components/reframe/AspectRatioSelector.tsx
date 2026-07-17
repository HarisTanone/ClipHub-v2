import { cn } from "@/lib/utils";

type AspectRatio = "9:16" | "16:9" | "1:1";

interface AspectRatioSelectorProps {
  value: AspectRatio;
  onChange: (ratio: AspectRatio) => void;
}

const RATIOS: AspectRatio[] = ["9:16", "16:9", "1:1"];

export function AspectRatioSelector({
  value,
  onChange,
}: AspectRatioSelectorProps) {
  return (
    <div className="flex items-center gap-2">
      {RATIOS.map((ratio) => {
        const isActive = value === ratio;
        return (
          <button
            key={ratio}
            type="button"
            onClick={() => onChange(ratio)}
            className={cn(
              "px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors",
              isActive
                ? "border-emerald-500 bg-emerald-500/10 text-emerald-400"
                : "border-zinc-700 text-zinc-500 hover:border-zinc-600"
            )}
          >
            {ratio}
          </button>
        );
      })}
    </div>
  );
}
