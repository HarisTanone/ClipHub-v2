import { useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, Info, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Promise-based confirm dialog — drop-in replacement for window.confirm().
 *
 * Usage:
 *   if (!(await confirmDialog({ title: "...", message: "...", confirmText: "Delete", danger: true }))) return;
 *
 * Alert-style (single OK button):
 *   alertDialog({ title: "Oops", message: "Something failed" });
 *
 * Mount <ConfirmDialog /> once at the app root.
 */

export interface ConfirmOptions {
  title: string;
  message?: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  /** When true, renders a single OK button (alert style). */
  alert?: boolean;
  /** Optional custom icon element shown in the badge. */
  icon?: ReactNode;
}

interface PendingState extends ConfirmOptions {
  resolve: (value: boolean) => void;
}

let pending: PendingState | null = null;
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((l) => l());
}

function settle(result: boolean) {
  const resolve = pending?.resolve;
  pending = null;
  notify();
  resolve?.(result);
}

export function confirmDialog(options: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    // If a previous dialog is still pending, resolve it as cancelled first
    // so its caller never hangs on an unresolved promise.
    if (pending) pending.resolve(false);
    pending = { ...options, resolve };
    notify();
  });
}

export function alertDialog(options: Omit<ConfirmOptions, "alert">): Promise<void> {
  return confirmDialog({ ...options, alert: true }).then(() => undefined);
}

export function ConfirmDialog() {
  const [, forceRender] = useState(0);

  useEffect(() => {
    const rerender = () => forceRender((n) => n + 1);
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && pending) settle(false);
    };
    listeners.add(rerender);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      listeners.delete(rerender);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  if (!pending) return null;

  const opts = pending;
  const isAlert = opts.alert ?? false;
  const isDanger = opts.danger ?? false;

  const iconBadge = opts.icon ?? (isAlert ? <Info className="h-5 w-5" /> : <AlertTriangle className="h-5 w-5" />);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={() => settle(false)}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={opts.title}
        className="relative w-full max-w-sm overflow-hidden rounded-xl border border-zinc-800 bg-[#111113] shadow-2xl animate-fade-in"
      >
        <div className="p-5">
          <div className="flex items-start gap-3.5">
            <div
              className={cn(
                "flex h-11 w-11 shrink-0 items-center justify-center rounded-full",
                isAlert
                  ? "bg-indigo-500/10 text-indigo-400"
                  : isDanger
                    ? "bg-red-500/10 text-red-400"
                    : "bg-amber-500/10 text-amber-400"
              )}
            >
              {iconBadge}
            </div>
            <div className="min-w-0 pt-0.5">
              <h3 className="text-sm font-semibold text-zinc-100">{opts.title}</h3>
              {opts.message && (
                <p className="mt-1.5 text-xs leading-relaxed whitespace-pre-line text-zinc-400">{opts.message}</p>
              )}
            </div>
          </div>

          <div className="mt-5 flex gap-2.5">
            {!isAlert && (
              <button
                type="button"
                onClick={() => settle(false)}
                className="flex-1 rounded-lg border border-zinc-700 px-4 py-2.5 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-800/70 hover:text-zinc-100 active:scale-[0.98]"
              >
                {opts.cancelText || "Cancel"}
              </button>
            )}
            <button
              type="button"
              autoFocus={!isDanger || isAlert}
              onClick={() => settle(true)}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-semibold text-white shadow-lg transition-all active:scale-[0.98]",
                isAlert
                  ? "bg-indigo-500 shadow-indigo-500/25 hover:bg-indigo-400"
                  : isDanger
                    ? "bg-red-500 shadow-red-500/25 hover:bg-red-400"
                    : "bg-indigo-500 shadow-indigo-500/25 hover:bg-indigo-400"
              )}
            >
              {isDanger && !isAlert && <Trash2 className="h-3.5 w-3.5" />}
              {opts.confirmText || (isAlert ? "OK" : "Confirm")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
