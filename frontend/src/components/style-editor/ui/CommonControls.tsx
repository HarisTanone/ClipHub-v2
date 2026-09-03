import React from "react";
import { cn } from "@/lib/utils";
import { RangeSlider } from "@/components/ui/RangeSlider";

export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-[11px] font-semibold text-zinc-300 mb-2 uppercase tracking-wider">{title}</h4>
      {children}
    </div>
  );
}

export function UnavailableHint({ text }: { text: string }) {
  return (
    <p className="rounded-md border border-zinc-800 bg-zinc-900/60 px-2 py-1 text-[9px] text-zinc-600">{text}</p>
  );
}

export function ColorPicker({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="text-[10px] text-zinc-500 block mb-1">{label}</label>
      <div className="flex items-center gap-2 bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5">
        <input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="w-5 h-5 rounded border-0 cursor-pointer bg-transparent" />
        <span className="text-[10px] text-zinc-400 font-mono">{value}</span>
      </div>
    </div>
  );
}

export function RangeInput({ label, min, max, value, onChange }: { label: string; min: number; max: number; value: number; onChange: (v: number) => void }) {
  const percent = ((value - min) / (max - min)) * 100;
  return (
    <div>
      <label className="text-[10px] text-zinc-500 block mb-1">{label}</label>
      <div className="relative w-full h-6 flex items-center">
        <div className="absolute left-0 right-0 h-2 bg-zinc-700 rounded-full" />
        <div className="absolute left-0 h-2 bg-emerald-600 rounded-full" style={{ width: `${percent}%` }} />
        <input type="range" min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))} className="absolute w-full h-6 opacity-0 cursor-pointer z-10" />
        <div className="absolute w-4 h-4 bg-emerald-500 rounded-full shadow-lg border-2 border-emerald-400 pointer-events-none" style={{ left: `calc(${percent}% - 8px)` }} />
      </div>
    </div>
  );
}

export function Checkbox({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label
      className={cn(
        "flex items-center gap-2.5 select-none transition-all py-1 px-1.5 rounded-lg hover:bg-zinc-800/40 group",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"
      )}
    >
      <div className="relative inline-flex items-center shrink-0">
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          className="sr-only peer"
        />
        <div
          className={cn(
            "w-7 h-4 rounded-full transition-colors duration-200 ease-in-out relative border",
            checked
              ? "bg-emerald-500 border-emerald-400 shadow-sm shadow-emerald-500/25"
              : "bg-zinc-800 border-zinc-600 group-hover:border-zinc-500",
            disabled && "opacity-50"
          )}
        >
          <div
            className={cn(
              "w-2.5 h-2.5 rounded-full transition-transform duration-200 ease-in-out absolute top-[2px] left-[2px] shadow-sm",
              checked ? "translate-x-3 bg-zinc-950" : "translate-x-0 bg-zinc-300"
            )}
          />
        </div>
      </div>
      <span
        className={cn(
          "text-[11px] transition-colors leading-tight",
          checked ? "text-zinc-200 font-medium" : "text-zinc-400 group-hover:text-zinc-300"
        )}
      >
        {label}
      </span>
    </label>
  );
}

export function SelectSmall({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <div>
      <label className="text-[10px] text-zinc-500 block mb-1">{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5 text-[11px] text-zinc-300 focus:outline-none focus:border-zinc-500">
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

export function SliderField({ label, value, min, max, suffix = "", step = 1, onChange }: { label: string; value: number; min: number; max: number; suffix?: string; step?: number; onChange: (value: number) => void }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
      <RangeSlider label={label} value={value} min={min} max={max} step={step} suffix={suffix} onChange={onChange} />
    </div>
  );
}

export function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-950/40 p-2.5">
      <input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="h-7 w-9 cursor-pointer rounded border-0 bg-transparent" />
      <span>
        <span className="block text-[9px] font-semibold uppercase tracking-wider text-zinc-500">{label}</span>
        <span className="text-[10px] text-zinc-300">{value}</span>
      </span>
    </label>
  );
}

export function MiniToggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <button type="button" onClick={() => onChange(!checked)} className={cn("rounded-lg border px-2 py-2 text-[10px] font-medium transition-colors", checked ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-300" : "border-zinc-800 text-zinc-500")}>
      {label}
    </button>
  );
}
