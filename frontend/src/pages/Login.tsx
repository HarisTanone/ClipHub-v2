import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Zap, LogIn, Eye, EyeOff, Mail, Lock, ShieldCheck, Film, Sparkles, CheckCircle } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/hooks/useAuth";

export function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password) {
      setError("Email and password required");
      return;
    }

    setIsLoading(true);
    setError("");
    try {
      await login(email.trim(), password);
      navigate("/");
    } catch (e: any) {
      setError(e.message || "Login failed. Check your credentials.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#09090b] px-4 py-6 text-zinc-100">
      <div className="mx-auto grid min-h-[calc(100vh-3rem)] w-full max-w-5xl items-center gap-4 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="hidden lg:block">
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/55 p-4">
            <div className="flex items-center justify-between border-b border-zinc-800/70 pb-3">
              <div className="flex items-center gap-2">
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-emerald-500/20 bg-emerald-500/10 text-emerald-300">
                  <Zap className="h-4 w-4" />
                </span>
                <div>
                  <p className="text-sm font-semibold">AutoCliper</p>
                  <p className="text-[10px] text-zinc-500">Render control room</p>
                </div>
              </div>
              <span className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 text-[10px] font-medium text-emerald-300">Live</span>
            </div>

            <div className="mt-4 grid grid-cols-3 gap-2">
              <PreviewMetric icon={<Film className="h-3.5 w-3.5" />} label="Queued" value="18" />
              <PreviewMetric icon={<Sparkles className="h-3.5 w-3.5" />} label="Hooks" value="42" />
              <PreviewMetric icon={<CheckCircle className="h-3.5 w-3.5" />} label="Ready" value="96%" />
            </div>

            <div className="mt-4 space-y-2">
              {[
                ["Podcast clip", "Hook render", "82%"],
                ["Founder story", "Subtitle sync", "61%"],
                ["Product demo", "Final encode", "94%"],
              ].map(([title, stage, pct]) => (
                <div key={title} className="rounded-lg border border-zinc-800 bg-zinc-900/45 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-xs font-medium text-zinc-200">{title}</p>
                      <p className="mt-0.5 text-[10px] text-zinc-500">{stage}</p>
                    </div>
                    <span className="font-mono text-[10px] text-emerald-300">{pct}</span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-zinc-800">
                    <div className="h-full rounded-full bg-emerald-500" style={{ width: pct }} />
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 rounded-lg border border-blue-500/20 bg-blue-500/[0.04] p-3">
              <div className="flex items-start gap-2">
                <ShieldCheck className="mt-0.5 h-4 w-4 text-blue-300" />
                <div>
                  <p className="text-xs font-medium text-zinc-200">Secure workspace</p>
                  <p className="mt-1 text-[11px] leading-relaxed text-zinc-500">Login session protects renders, presets, clip exports, and Remotion styling controls.</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="mx-auto w-full max-w-md space-y-5">
          <div className="flex items-center gap-3">
            <div className="h-11 w-11 rounded-lg border border-emerald-500/20 bg-emerald-500/10 flex items-center justify-center">
              <Zap className="h-5 w-5 text-emerald-300" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-zinc-100">AutoCliper</h1>
              <p className="text-sm text-zinc-500">Sign in to manage clips and renders</p>
            </div>
          </div>

          <Card className="p-5 rounded-lg">
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="block text-xs font-medium text-zinc-400">Email</label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="admin@autocliper.com"
                    autoComplete="email"
                    className="w-full rounded-lg border border-zinc-700/60 bg-zinc-900/80 py-2 pl-9 pr-3 text-sm text-zinc-100 placeholder:text-zinc-600 transition-colors duration-150 focus:border-emerald-500/60 focus:outline-none focus:ring-1 focus:ring-emerald-500/20"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-medium text-zinc-400">Password</label>
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter password"
                    autoComplete="current-password"
                    className="w-full rounded-lg border border-zinc-700/60 bg-zinc-900/80 py-2 pl-9 pr-10 text-sm text-zinc-100 placeholder:text-zinc-600 transition-colors duration-150 focus:border-emerald-500/60 focus:outline-none focus:ring-1 focus:ring-emerald-500/20"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                    className="absolute right-2 top-1/2 rounded-md p-1.5 -translate-y-1/2 text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    title={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {error && (
                <div className="rounded-lg bg-red-950/30 border border-red-500/20 px-3 py-2">
                  <p className="text-xs text-red-400">{error}</p>
                </div>
              )}

              <Button
                type="submit"
                size="lg"
                className="w-full"
                loading={isLoading}
                icon={<LogIn className="h-4 w-4" />}
              >
                Sign in
              </Button>
            </form>
          </Card>

          <p className="text-center text-[11px] text-zinc-600">
            AutoCliper Pipeline v0.4
          </p>
        </div>
      </div>
    </div>
  );
}

function PreviewMetric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/45 p-3">
      <div className="flex items-center justify-between text-emerald-300">
        {icon}
        <span className="text-sm font-semibold text-zinc-100">{value}</span>
      </div>
      <p className="mt-2 text-[10px] text-zinc-500">{label}</p>
    </div>
  );
}
