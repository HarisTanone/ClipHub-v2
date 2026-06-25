import { cn } from "@/lib/utils";

interface ProgressBarProps {
  value: number;
  max?: number;
  size?: "sm" | "md";
  color?: "emerald" | "blue" | "amber" | "red";
  label?: string;
  showValue?: boolean;
  className?: string;
}

const colorMap = {
  emerald: "bg-emerald-500",
  blue: "bg-blue-500",
  amber: "bg-amber-500",
  red: "bg-red-500",
};

export function ProgressBar({
  value,
  max = 100,
  size = "md",
  color = "emerald",
  label,
  showValue,
  className,
}: ProgressBarProps) {
  const pct = Math.min(Math.max((value / max) * 100, 0), 100);

  return (
    <div className={cn("w-full", className)}>
      {(label || showValue) && (
        <div className="flex items-center justify-between mb-1.5">
          {label && <span className="text-xs text-zinc-400">{label}</span>}
          {showValue && <span className="text-xs text-zinc-500 font-mono">{Math.round(pct)}%</span>}
        </div>
      )}
      <div className={cn("w-full rounded-full bg-zinc-800 overflow-hidden", size === "sm" ? "h-1" : "h-1.5")}>
        <div
          className={cn("h-full rounded-full transition-all duration-500 ease-out", colorMap[color])}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

interface StepProgressProps {
  steps: Array<{ name: string; label: string }>;
  currentStep: number;
  className?: string;
}

export function StepProgress({ steps, currentStep, className }: StepProgressProps) {
  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center gap-1">
        {steps.map((step, i) => (
          <div
            key={step.name}
            className={cn(
              "flex-1 h-1 rounded-full transition-colors duration-300",
              i + 1 <= currentStep ? "bg-emerald-500" : i + 1 === currentStep + 1 ? "bg-emerald-500/30" : "bg-zinc-800"
            )}
          />
        ))}
      </div>
      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-400">
          {currentStep > 0 && currentStep <= steps.length
            ? steps[currentStep - 1].label
            : "Waiting..."}
        </span>
        <span className="text-xs text-zinc-500 font-mono">
          {currentStep}/{steps.length}
        </span>
      </div>
    </div>
  );
}
