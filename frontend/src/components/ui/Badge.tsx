import { cn } from "@/lib/utils";
import { getStatusBg } from "@/lib/utils";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "default" | "success" | "warning" | "error" | "info" | "status";
  status?: string;
  dot?: boolean;
  size?: "sm" | "md";
}

const variantStyles = {
  default: "bg-zinc-800 text-zinc-300 border-zinc-700/50",
  success: "bg-emerald-500/12 text-emerald-400 border-emerald-500/20",
  warning: "bg-amber-500/12 text-amber-400 border-amber-500/20",
  error: "bg-red-500/12 text-red-400 border-red-500/20",
  info: "bg-blue-500/12 text-blue-400 border-blue-500/20",
  status: "",
};

const dotColors: Record<string, string> = {
  default: "bg-zinc-400",
  success: "bg-emerald-400",
  warning: "bg-amber-400",
  error: "bg-red-400",
  info: "bg-blue-400",
};

export function Badge({ children, variant = "default", status, dot, size = "sm" }: BadgeProps) {
  const resolvedVariant = variant === "status" && status ? undefined : variant;
  const statusStyles = variant === "status" && status ? getStatusBg(status) : "";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-medium border",
        size === "sm" ? "px-2 py-0.5 text-[11px] rounded-md" : "px-2.5 py-1 text-xs rounded-lg",
        resolvedVariant ? variantStyles[resolvedVariant] : statusStyles,
        !resolvedVariant && !statusStyles && variantStyles.default
      )}
    >
      {dot && (
        <span
          className={cn(
            "w-1.5 h-1.5 rounded-full",
            resolvedVariant ? dotColors[resolvedVariant] || dotColors.default : "bg-current"
          )}
        />
      )}
      {children}
    </span>
  );
}
