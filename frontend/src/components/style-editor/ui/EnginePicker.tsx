import { Clapperboard, Zap, Download, Palette, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { ENGINE_NOTES, type RenderEngine } from "@/lib/renderEngines";

export function EnginePicker({
  engine,
  onChange,
  kind,
  isSuperadmin = false,
}: {
  engine: RenderEngine;
  onChange: (e: RenderEngine) => void;
  kind: "hook" | "subtitle";
  isSuperadmin?: boolean;
}) {
  const allEngines = ["remotion", "hyperframes", "ffmpeg", "skia"] as RenderEngine[];
  // Gate: remotion/hyperframes hidden only for SUBTITLE when non-superadmin
  // Hook always shows all engines
  const engineOptions = allEngines.filter((id) => {
    if (kind === "hook") return true; // Hook: semua engine tersedia untuk semua user
    const meta = ENGINE_NOTES[id];
    if (meta.superuserOnly && !isSuperadmin) return false;
    return true;
  });

  const getIcon = (id: string) => {
    switch (id) {
      case "remotion": return Clapperboard;
      case "hyperframes": return Zap;
      case "ffmpeg": return Download;
      case "skia": return Palette;
      default: return Clapperboard;
    }
  };

  const getTheme = (id: string, active: boolean) => {
    if (!active) {
      return "border-zinc-800/90 bg-zinc-900/40 text-zinc-400 hover:border-zinc-700 hover:bg-zinc-900/80 hover:text-zinc-200";
    }
    switch (id) {
      case "remotion":
        return "border-emerald-500/60 bg-emerald-500/10 text-emerald-100 ring-1 ring-emerald-500/40 shadow-[0_0_15px_rgba(16,185,129,0.15)]";
      case "hyperframes":
        return "border-cyan-500/60 bg-cyan-500/10 text-cyan-100 ring-1 ring-cyan-500/40 shadow-[0_0_15px_rgba(6,182,212,0.15)]";
      case "ffmpeg":
        return "border-purple-500/60 bg-purple-500/10 text-purple-100 ring-1 ring-purple-500/40 shadow-[0_0_15px_rgba(168,85,247,0.15)]";
      case "skia":
        return "border-amber-500/60 bg-amber-500/10 text-amber-100 ring-1 ring-amber-500/40 shadow-[0_0_15px_rgba(245,158,11,0.15)]";
      default:
        return "border-emerald-500/60 bg-emerald-500/10 text-emerald-100";
    }
  };

  const getBadgeStyle = (id: string, active: boolean) => {
    if (!active) return "bg-zinc-800 text-zinc-500 border border-zinc-700/50";
    switch (id) {
      case "remotion": return "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
      case "hyperframes": return "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40";
      case "ffmpeg": return "bg-purple-500/20 text-purple-300 border border-purple-500/40";
      case "skia": return "bg-amber-500/20 text-amber-300 border border-amber-500/40";
      default: return "bg-white/10 text-white";
    }
  };

  const getIconColor = (id: string, active: boolean) => {
    if (!active) return "text-zinc-500";
    switch (id) {
      case "remotion": return "text-emerald-400";
      case "hyperframes": return "text-cyan-400";
      case "ffmpeg": return "text-purple-400";
      case "skia": return "text-amber-400";
      default: return "text-white";
    }
  };

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-3 space-y-3">
      <div className={cn("grid gap-2.5", engineOptions.length <= 2 ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-1 sm:grid-cols-2")}>
        {engineOptions.map((id) => {
          const meta = ENGINE_NOTES[id];
          const active = engine === id;
          const Icon = getIcon(id);
          return (
            <button
              key={id}
              type="button"
              onClick={() => onChange(id)}
              className={cn(
                "group relative flex flex-col justify-between gap-2 rounded-xl border p-3 text-left transition-all",
                getTheme(id, active),
              )}
            >
              <div className="flex items-center justify-between gap-2 w-full">
                <span className="flex items-center gap-2 text-xs font-bold tracking-tight">
                  <Icon className={cn("h-4 w-4 shrink-0 transition-colors", getIconColor(id, active))} />
                  <span className={active ? "text-zinc-100" : "text-zinc-300 group-hover:text-zinc-100"}>{meta.label}</span>
                </span>
                <span className={cn(
                  "rounded-full px-2 py-0.5 text-[9px] font-black uppercase tracking-wider shrink-0 transition-colors",
                  getBadgeStyle(id, active),
                )}>
                  {meta.badge}
                </span>
              </div>
              <p className="text-[10px] leading-snug text-zinc-400 opacity-90">
                <span className={cn("font-medium", active ? "text-zinc-300" : "text-zinc-400")}>{meta.speed}</span> · {meta.quality}
              </p>
            </button>
          );
        })}
      </div>
      <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/50 px-3 py-2.5 flex items-start gap-2">
        <div className={cn("mt-0.5 shrink-0", getIconColor(engine, true))}>
          <Sparkles className="w-3.5 h-3.5" />
        </div>
        <p className="text-[10px] leading-relaxed text-zinc-400">
          <span className="font-semibold text-zinc-200">Note · {kind}: </span>
          {ENGINE_NOTES[engine].note}
        </p>
      </div>
    </div>
  );
}
