import { cn } from "@/lib/utils";

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  description?: string;
  disabled?: boolean;
}

export function Toggle({ checked, onChange, label, description, disabled }: ToggleProps) {
  return (
    <label
      className={cn(
        "flex items-center justify-between gap-3 rounded-lg border border-zinc-800/80 px-4 py-3 transition-colors",
        disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:border-zinc-700"
      )}
    >
      <div className="min-w-0">
        {label && <p className="text-sm text-zinc-200 font-medium">{label}</p>}
        {description && <p className="text-xs text-zinc-500 mt-0.5">{description}</p>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={cn(
          "relative shrink-0 w-9 h-5 rounded-full transition-colors duration-200",
          checked ? "bg-emerald-600" : "bg-zinc-700"
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white transition-transform duration-200 shadow-sm",
            checked && "translate-x-4"
          )}
        />
      </button>
    </label>
  );
}
