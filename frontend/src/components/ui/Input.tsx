import { type InputHTMLAttributes, type TextareaHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, className = "", ...props }, ref) => {
    return (
      <div className="space-y-1.5">
        {label && (
          <label className="block text-xs font-medium text-zinc-400">{label}</label>
        )}
        <input
          ref={ref}
          className={cn(
            "w-full rounded-lg border bg-zinc-900/80 px-3 py-2 text-sm text-zinc-100",
            "placeholder:text-zinc-600 transition-colors duration-150",
            "focus:outline-none focus:ring-1",
            error
              ? "border-red-500/60 focus:border-red-500 focus:ring-red-500/30"
              : "border-zinc-700/60 focus:border-emerald-500/60 focus:ring-emerald-500/20",
            className
          )}
          {...props}
        />
        {error && <p className="text-[11px] text-red-400">{error}</p>}
        {hint && !error && <p className="text-[11px] text-zinc-500">{hint}</p>}
      </div>
    );
  }
);

Input.displayName = "Input";

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: { value: string; label: string }[];
}

export function Select({ label, error, options, className = "", ...props }: SelectProps) {
  return (
    <div className="space-y-1.5">
      {label && (
        <label className="block text-xs font-medium text-zinc-400">{label}</label>
      )}
      <select
        className={cn(
          "w-full rounded-lg border bg-zinc-900/80 px-3 py-2 text-sm text-zinc-100",
          "transition-colors duration-150 focus:outline-none focus:ring-1",
          error
            ? "border-red-500/60 focus:border-red-500 focus:ring-red-500/30"
            : "border-zinc-700/60 focus:border-emerald-500/60 focus:ring-emerald-500/20",
          className
        )}
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && <p className="text-[11px] text-red-400">{error}</p>}
    </div>
  );
}

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, className = "", ...props }, ref) => {
    return (
      <div className="space-y-1.5">
        {label && (
          <label className="block text-xs font-medium text-zinc-400">{label}</label>
        )}
        <textarea
          ref={ref}
          className={cn(
            "w-full rounded-lg border bg-zinc-900/80 px-3 py-2 text-sm text-zinc-100 resize-none",
            "placeholder:text-zinc-600 transition-colors duration-150",
            "focus:outline-none focus:ring-1",
            error
              ? "border-red-500/60 focus:border-red-500 focus:ring-red-500/30"
              : "border-zinc-700/60 focus:border-emerald-500/60 focus:ring-emerald-500/20",
            className
          )}
          {...props}
        />
        {error && <p className="text-[11px] text-red-400">{error}</p>}
      </div>
    );
  }
);

Textarea.displayName = "Textarea";
