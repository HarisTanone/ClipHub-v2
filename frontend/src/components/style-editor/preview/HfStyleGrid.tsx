import { useState } from "react";
import { cn } from "@/lib/utils";
import type { HfStylePreset } from "@/lib/renderEngines";

export function HfStyleGrid({
  items,
  activeId,
  onSelect,
}: {
  items: HfStylePreset[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  const PAGE_SIZE = 6;
  const totalPages = Math.ceil(items.length / PAGE_SIZE) || 1;
  const activeIndex = items.findIndex((s) => s.id === activeId);
  const initialPage = activeIndex >= 0 ? Math.floor(activeIndex / PAGE_SIZE) + 1 : 1;
  const [page, setPage] = useState(initialPage);

  const startIndex = (page - 1) * PAGE_SIZE;
  const visibleItems = items.slice(startIndex, startIndex + PAGE_SIZE);

  return (
    <div className="space-y-3">
      {/* 2 lines x 3 columns grid = 6 items */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
        {visibleItems.map((s) => {
          const active = activeId === s.id;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => onSelect(s.id)}
              className={cn(
                "group relative rounded-xl border p-2.5 text-left transition-all flex flex-col justify-between gap-2 overflow-hidden",
                active
                  ? "border-cyan-500 bg-cyan-950/30 ring-1 ring-cyan-500/50 shadow-md shadow-cyan-500/10"
                  : "border-zinc-800 bg-zinc-950/60 hover:border-zinc-700 hover:bg-zinc-900/60"
              )}
            >
              <div>
                <div className="flex items-center justify-between gap-1.5 mb-1.5">
                  <p className="text-[11px] font-bold text-zinc-100 group-hover:text-white truncate">
                    {s.name}
                  </p>
                  <span
                    className="shrink-0 rounded px-1.5 py-0.5 text-[8px] font-black uppercase tracking-wider"
                    style={{
                      color: s.accent,
                      backgroundColor: `${s.accent}18`,
                      border: `1px solid ${s.accent}44`,
                    }}
                  >
                    {s.mood}
                  </span>
                </div>
                <p className="text-[9px] text-zinc-400 line-clamp-2 leading-relaxed">
                  {s.desc}
                </p>
              </div>

              <div
                className="mt-1 flex h-9 items-center justify-center rounded-lg text-[10px] font-black tracking-wide uppercase px-2 shadow-inner"
                style={{
                  background: `linear-gradient(135deg, ${s.accent}25, rgba(0,0,0,0.7))`,
                  color: s.accent,
                  border: `1px solid ${s.accent}33`,
                  textShadow: `0 0 10px ${s.accent}88`,
                }}
              >
                {s.preview}
              </div>
            </button>
          );
        })}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-2 border-t border-zinc-800/60">
          <span className="text-[10px] text-zinc-500 font-medium">
            Page {page} of {totalPages} ({items.length} styles)
          </span>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              disabled={page === 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="px-2 py-0.5 text-[10px] font-semibold rounded border border-zinc-800 bg-zinc-900 text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-zinc-800 transition-colors"
            >
              Prev
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPage(p)}
                className={cn(
                  "w-5 h-5 text-[9px] font-bold rounded transition-colors",
                  page === p
                    ? "bg-cyan-500 text-black shadow-sm"
                    : "border border-zinc-800 bg-zinc-900/80 text-zinc-400 hover:text-white hover:bg-zinc-800"
                )}
              >
                {p}
              </button>
            ))}
            <button
              type="button"
              disabled={page === totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="px-2 py-0.5 text-[10px] font-semibold rounded border border-zinc-800 bg-zinc-900 text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-zinc-800 transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
