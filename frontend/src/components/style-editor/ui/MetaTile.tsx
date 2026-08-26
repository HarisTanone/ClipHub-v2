import { cn } from "@/lib/utils";
import type { OptionMeta } from "../types";

export function MetaTile({ meta, active, onClick }: { meta: OptionMeta; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-lg border p-2.5 text-left transition-all min-h-[86px]",
        active ? "border-emerald-400 bg-emerald-500/10 ring-1 ring-emerald-400/20" : "border-zinc-800 bg-zinc-900/60 hover:border-zinc-600"
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={cn("text-[11px] font-semibold", active ? "text-emerald-300" : "text-zinc-200")}>{meta.label}</span>
        <span className="rounded px-1.5 py-0.5 text-[8px] font-black" style={{ color: meta.accent, backgroundColor: `${meta.accent}18` }}>
          {meta.preview}
        </span>
      </div>
      <p className="mt-1 text-[9px] text-zinc-500">{meta.mood}</p>
      <p className="mt-1.5 line-clamp-2 text-[9px] leading-snug text-zinc-600">{meta.desc}</p>
    </button>
  );
}

export function TimingOptionCard({ meta, active, onClick, kind }: { meta: OptionMeta; active: boolean; onClick: () => void; kind: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative min-h-[92px] overflow-hidden rounded-lg border p-3 text-left transition-all",
        active
          ? "border-emerald-400 bg-emerald-500/10 ring-1 ring-emerald-400/25"
          : "border-zinc-800 bg-zinc-900/70 hover:border-zinc-600 hover:bg-zinc-900"
      )}
    >
      <div className="absolute inset-x-0 top-0 h-1" style={{ background: `linear-gradient(90deg, ${meta.accent}, transparent)` }} />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className={cn("text-[12px] font-semibold", active ? "text-emerald-300" : "text-zinc-200")}>{meta.label}</p>
          <p className="mt-1 line-clamp-2 text-[9px] leading-snug text-zinc-500">{meta.desc}</p>
        </div>
        <span className="rounded-md px-1.5 py-0.5 text-[8px] font-black" style={{ color: meta.accent, backgroundColor: `${meta.accent}18`, border: `1px solid ${meta.accent}44` }}>
          {meta.preview}
        </span>
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-800">
          <div className="h-full w-2/3 rounded-full transition-all group-hover:w-full" style={{ backgroundColor: meta.accent }} />
        </div>
        <span className="rounded border border-zinc-800 bg-zinc-950/80 px-1.5 py-0.5 text-[8px] uppercase tracking-wide text-zinc-500">{kind}</span>
      </div>
    </button>
  );
}

export function FontChips({ fonts, active, onSelect }: { fonts: string[]; active: string; onSelect: (font: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {fonts.map((font) => (
        <button
          key={font}
          type="button"
          onClick={() => onSelect(font)}
          className={cn(
            "rounded-lg border px-2.5 py-1.5 text-[10px] transition-colors",
            active === font ? "border-emerald-500 bg-emerald-500/10 text-emerald-300" : "border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:border-zinc-600"
          )}
          style={{ fontFamily: font === "monospace" ? "monospace" : `'${font}', sans-serif` }}
        >
          {font}
        </button>
      ))}
    </div>
  );
}
