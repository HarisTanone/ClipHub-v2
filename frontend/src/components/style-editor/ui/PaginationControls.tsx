import { ChevronLeft, ChevronRight } from "lucide-react";
import { PAGINATION_PAGE_SIZE } from "../types";

export function PaginationControls({
  page,
  totalItems,
  onPageChange,
  label,
}: {
  page: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  label: string;
}) {
  const totalPages = Math.max(1, Math.ceil(totalItems / PAGINATION_PAGE_SIZE));
  const start = totalItems === 0 ? 0 : (page - 1) * PAGINATION_PAGE_SIZE + 1;
  const end = Math.min(page * PAGINATION_PAGE_SIZE, totalItems);

  if (totalPages <= 1) {
    return (
      <div className="mt-2 flex justify-end text-[10px] text-zinc-600">
        {totalItems} {label}
      </div>
    );
  }

  return (
    <div className="mt-3 flex items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-950/50 px-2.5 py-2">
      <span className="text-[10px] text-zinc-500">
        {start}-{end} of {totalItems} {label}
      </span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page === 1}
          className="rounded-md p-1 text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-200 disabled:pointer-events-none disabled:opacity-30"
          aria-label={`Previous ${label} page`}
          title="Previous page"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
        <span className="min-w-10 text-center font-mono text-[10px] text-zinc-400">
          {page}/{totalPages}
        </span>
        <button
          type="button"
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
          disabled={page === totalPages}
          className="rounded-md p-1 text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-200 disabled:pointer-events-none disabled:opacity-30"
          aria-label={`Next ${label} page`}
          title="Next page"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
