import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Zap, LogIn } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/hooks/useAuth";

export function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
    <div className="min-h-screen bg-[#09090b] flex items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">
        {/* Logo */}
        <div className="flex flex-col items-center gap-3">
          <div className="h-12 w-12 rounded-xl bg-emerald-600/20 flex items-center justify-center">
            <Zap className="h-6 w-6 text-emerald-400" />
          </div>
          <div className="text-center">
            <h1 className="text-xl font-semibold text-zinc-100">AutoCliper</h1>
            <p className="text-sm text-zinc-500 mt-1">Sign in to your account</p>
          </div>
        </div>

        {/* Login form */}
        <Card className="p-5">
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@autocliper.com"
              autoComplete="email"
            />
            <Input
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              autoComplete="current-password"
            />

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
  );
}
