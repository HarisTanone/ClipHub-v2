import { useState } from "react";
import { cn } from "@/lib/utils";

interface RangeSliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  description?: string;
  tooltip?: { what: string; increase: string; decrease: string };
}

export function RangeSlider({ label, value, min, max, step, onChange, description, tooltip }: RangeSliderProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  const pct = ((value - min) / (max - min)) * 100;

  return (
    <div className="space-y-1.5">
      <div
        className="flex items-center justify-between relative"
        onMouseEnter={() => tooltip && setShowTooltip(true)}
        onMouseLeave={() => tooltip && setShowTooltip(false)}
        onFocus={() => tooltip && setShowTooltip(true)}
        onBlur={() => tooltip && setShowTooltip(false)}
      >
        <label className="text-[11px] text-zinc-400">{label}</label>
        <span className="text-[11px] font-mono text-zinc-300">{Number.isInteger(value) ? value : value.toFixed(2)}</span>

        {tooltip && showTooltip && (
          <div
            role="tooltip"
            className="absolute bottom-full left-0 mb-2 z-50 w-64 p-2.5 bg-zinc-800 border border-zinc-700 rounded-lg shadow-lg"
          >
            <p className="text-[11px] text-zinc-300 mb-1">{tooltip.what}</p>
            <p className="text-[11px] text-zinc-500">↑ {tooltip.increase}</p>
            <p className="text-[11px] text-zinc-500">↓ {tooltip.decrease}</p>
          </div>
        )}
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1.5 rounded-full appearance-none bg-zinc-700 cursor-pointer"
        style={{
          background: `linear-gradient(to right, #10b981 0%, #10b981 ${pct}%, #3f3f46 ${pct}%, #3f3f46 100%)`,
        }}
      />
      {description && (
        <p data-testid="slider-description" className="text-[11px] text-zinc-500">
          {description}
        </p>
      )}
    </div>
  );
}
