import { useState, useEffect } from "react";
import { models, type ModelStatus } from "@/lib/api";

const STATUS_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  available: { bg: "bg-emerald-500/10", text: "text-emerald-400", dot: "bg-emerald-400" },
  rate_limited: { bg: "bg-amber-500/10", text: "text-amber-400", dot: "bg-amber-400" },
  exhausted: { bg: "bg-red-500/10", text: "text-red-400", dot: "bg-red-400" },
  error: { bg: "bg-red-500/10", text: "text-red-400", dot: "bg-red-400" },
};

const PROVIDER_ICONS: Record<string, string> = {
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
      <div className="flex items-center gap-2 py-4">
        <div className="h-4 w-4 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin" />
        <span className="text-xs text-zinc-500">Loading models...</span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
        LLM Models Status
        <span className="text-[10px] text-zinc-600 font-normal">(auto-refresh 10s)</span>
      </h3>

      <div className="grid gap-2">
        {modelList.map((model) => {
          const colors = STATUS_COLORS[model.status] || STATUS_COLORS.error;
          const usagePercent = model.requests_limit > 0
            ? Math.min(100, (model.requests_today / model.requests_limit) * 100)
            : 0;

          return (
            <div
              key={model.key}
              className={`rounded-lg border border-zinc-800 p-3 ${colors.bg}`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <span className="w-6 h-6 rounded-md bg-zinc-800 flex items-center justify-center text-[10px] font-bold text-zinc-400">
                    {PROVIDER_ICONS[model.provider] || "?"}
                  </span>
                  <div>
                    <p className="text-[11px] font-medium text-zinc-200">{model.name}</p>
                    <p className="text-[9px] text-zinc-500">{model.purpose}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${colors.dot} ${model.status === "available" ? "animate-pulse" : ""}`} />
                  <span className={`text-[10px] font-medium ${colors.text}`}>
                    {model.status === "available" ? "Ready" :
                     model.status === "rate_limited" ? `Wait ${model.cooldown_remaining}s` :
                     model.status === "exhausted" ? "Exhausted" : "Error"}
                  </span>
                </div>
              </div>

              {/* Usage bar */}
              {model.requests_limit > 0 && (
                <div className="mt-2">
                  <div className="flex justify-between text-[9px] text-zinc-500 mb-0.5">
                    <span>{model.requests_today}/{model.requests_limit} requests</span>
                    {model.tokens_limit > 0 && (
                      <span>{Math.round(model.tokens_used / 1000)}K/{Math.round(model.tokens_limit / 1000)}K tokens</span>
                    )}
                  </div>
                  <div className="h-1 rounded-full bg-zinc-800 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        usagePercent >= 90 ? "bg-red-500" :
                        usagePercent >= 60 ? "bg-amber-500" : "bg-emerald-500"
                      }`}
                      style={{ width: `${usagePercent}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Error message */}
              {model.last_error && model.status !== "available" && (
                <p className="mt-1.5 text-[9px] text-red-400/70 truncate">{model.last_error}</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
