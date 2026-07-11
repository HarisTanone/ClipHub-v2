import { useState, useEffect } from "react";
import { models, type ModelStatus } from "@/lib/api";

const STATUS_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  available: { bg: "bg-emerald-500/10", text: "text-emerald-400", dot: "bg-emerald-400" },
  rate_limited: { bg: "bg-amber-500/10", text: "text-amber-400", dot: "bg-amber-400" },
  exhausted: { bg: "bg-red-500/10", text: "text-red-400", dot: "bg-red-400" },
  error: { bg: "bg-red-500/10", text: "text-red-400", dot: "bg-red-400" },
};

const PROVIDER_ICONS: Record<string, string> = {
  "9router": "9",
  gemini: "G",
  groq: "Q",
  ollama: "O",
};

export function ModelStatusPanel() {
  const [modelList, setModelList] = useState<ModelStatus[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000); // refresh every 10s
    return () => clearInterval(interval);
  }, []);

  async function fetchStatus() {
    try {
      const data = await models.getStatus();
      setModelList(data);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-2">
        <div className="h-3 w-3 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin" />
        <span className="text-[10px] text-zinc-500">Loading...</span>
      </div>
    );
  }

  const nineRouter = modelList.find((model) => model.provider === "9router" || model.key === "nine_router");

  return (
    <div className="space-y-2">
      {nineRouter && (
        <div className="flex items-center gap-2 rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-3 py-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-cyan-500/15 text-[10px] font-black text-cyan-300">9R</span>
          <div className="min-w-0">
            <p className="text-[9px] font-semibold uppercase tracking-wider text-cyan-500">9router model aktif</p>
            <p className="truncate text-[11px] font-medium text-zinc-200">{nineRouter.name.replace(/^9router\s*/i, "")}</p>
          </div>
          <span className={`ml-auto h-2 w-2 rounded-full ${(STATUS_COLORS[nineRouter.status] || STATUS_COLORS.error).dot}`} />
        </div>
      )}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
      {modelList.map((model) => {
        const colors = STATUS_COLORS[model.status] || STATUS_COLORS.error;
        const usagePercent = model.requests_limit > 0
          ? Math.min(100, (model.requests_today / model.requests_limit) * 100)
          : 0;

        return (
          <div
            key={model.key}
            className="rounded-lg border border-zinc-800 px-2.5 py-2 bg-zinc-900/50"
          >
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-1.5">
                <span className="w-5 h-5 rounded bg-zinc-800 flex items-center justify-center text-[9px] font-bold text-zinc-500">
                  {PROVIDER_ICONS[model.provider] || "?"}
                </span>
                <span className="text-[10px] font-medium text-zinc-300 truncate max-w-[90px]">{model.provider === "9router" ? model.name.replace(/^9router\s*/i, "") : model.name.split(" ").slice(0, 2).join(" ")}</span>
              </div>
              <div className="flex items-center gap-1">
                <span className={`w-1.5 h-1.5 rounded-full ${colors.dot} ${model.status === "available" ? "animate-pulse" : ""}`} />
              </div>
            </div>
            {/* Compact usage */}
            {model.requests_limit > 0 ? (
              <div>
                <div className="h-1 rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${usagePercent >= 90 ? "bg-red-500" :
                      usagePercent >= 60 ? "bg-amber-500" : "bg-emerald-500"
                      }`}
                    style={{ width: `${Math.max(2, usagePercent)}%` }}
                  />
                </div>
                <span className="text-[8px] text-zinc-600 mt-0.5 block">{model.requests_today}/{model.requests_limit}</span>
              </div>
            ) : (
              <span className="text-[8px] text-zinc-600">unlimited</span>
            )}
          </div>
        );
      })}
      </div>
    </div>
  );
}
