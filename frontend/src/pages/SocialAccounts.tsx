import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Share2,
  Facebook,
  Instagram,
  Youtube,
  RefreshCw,
  Trash2,
  Plus,
  Users,
  User as UserIcon,
  Search,
  CheckCircle2,
  AlertCircle,
  ShieldCheck,
  Globe,
  SlidersHorizontal,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { confirmDialog } from "@/components/ui/ConfirmDialog";
import { API_BASE, getToken } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

// ─── API helpers ──────────────────────────────────────────────────────────────

async function fetchAccounts(params: {
  page?: number;
  limit?: number;
  types?: string;
  search?: string;
  userId?: number | null;
} = {}): Promise<any> {
  const token = getToken();
  const query = new URLSearchParams();
  if (params.page) query.set("page", String(params.page));
  if (params.limit) query.set("limit", String(params.limit));
  if (params.types) query.set("types", params.types);
  if (params.search) query.set("search", params.search);
  if (params.userId) query.set("user_id", String(params.userId));

  const res = await fetch(`${API_BASE}/api/social/accounts?${query.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to fetch accounts");
  return res.json();
}

async function fetchAccountUsers(): Promise<any[]> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/accounts/users`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  return res.json();
}

async function fetchAccountCount(): Promise<any> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/accounts/count`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  return res.json();
}

async function removeAccount(accountId: string): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/accounts/${accountId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to remove");
}

async function facebookAuthorize(redirect: string): Promise<{ url: string }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/facebook/authorize?redirect=${encodeURIComponent(redirect)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to authorize");
  return res.json();
}

async function facebookExchange(code: string): Promise<{ token: string }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/facebook/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Exchange failed");
  return res.json();
}

async function facebookPages(accessToken: string): Promise<{ docs: any[] }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/facebook/pages?token=${encodeURIComponent(accessToken)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to fetch pages");
  return res.json();
}

async function facebookConnect(pageId: string, accessToken: string): Promise<{ accountId: string }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/facebook/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ pageId, token: accessToken }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to connect");
  return res.json();
}

async function tiktokAuthorize(redirect: string): Promise<{ url: string }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/tiktok/authorize?redirect=${encodeURIComponent(redirect)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to authorize");
  return res.json();
}

async function tiktokConnect(code: string): Promise<{ accountId: string }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/tiktok/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Connect failed");
  return res.json();
}

// Instagram
async function instagramAuthorize(redirect: string): Promise<{ url: string }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/instagram/authorize?redirect=${encodeURIComponent(redirect)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to authorize");
  return res.json();
}

async function instagramConnect(code: string): Promise<{ accountId: string }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/instagram/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Connect failed");
  return res.json();
}

// Threads
async function threadsAuthorize(redirect: string): Promise<{ url: string }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/threads/authorize?redirect=${encodeURIComponent(redirect)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to authorize");
  return res.json();
}

async function threadsConnect(code: string): Promise<{ accountId: string }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/threads/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Connect failed");
  return res.json();
}

// YouTube
async function youtubeAuthorize(redirect: string): Promise<{ url: string }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/youtube/authorize?redirect=${encodeURIComponent(redirect)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to authorize");
  return res.json();
}

async function youtubeExchange(code: string): Promise<{ token: string }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/youtube/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Exchange failed");
  return res.json();
}

async function youtubeChannels(accessToken: string): Promise<any[]> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/youtube/channels?token=${encodeURIComponent(accessToken)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  const data = await res.json();
  return data.docs || data || [];
}

async function youtubeConnect(channelId: string, accessToken: string): Promise<{ accountId: string }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/youtube/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ channelId, token: accessToken }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Connect failed");
  return res.json();
}

// LinkedIn
async function linkedinAuthorize(redirect: string): Promise<{ url: string }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/linkedin/authorize?redirect=${encodeURIComponent(redirect)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to authorize");
  return res.json();
}

async function linkedinExchange(code: string): Promise<{ token: string }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/linkedin/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Exchange failed");
  return res.json();
}

async function linkedinOrganizations(accessToken: string): Promise<any[]> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/linkedin/organizations?token=${encodeURIComponent(accessToken)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  const data = await res.json();
  return data.docs || data || [];
}

async function linkedinConnect(organizationId: string, accessToken: string): Promise<{ accountId: string }> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/linkedin/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ organizationId, token: accessToken }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Connect failed");
  return res.json();
}

// ─── Platform icon helper ─────────────────────────────────────────────────────

function PlatformIcon({ type, className }: { type: string; className?: string }) {
  const base = cn("h-4 w-4 shrink-0", className);
  switch (type) {
    case "facebook":
      return <Facebook className={cn(base, "text-blue-400")} />;
    case "instagram":
      return <Instagram className={cn(base, "text-pink-400")} />;
    case "youtube":
      return <Youtube className={cn(base, "text-red-400")} />;
    case "tiktok":
      return (
        <svg className={cn(base, "text-zinc-200")} viewBox="0 0 24 24" fill="currentColor">
          <path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.88 2.89 2.89 0 01-2.88-2.88 2.89 2.89 0 012.88-2.88c.28 0 .56.04.82.1v-3.5a6.37 6.37 0 00-.82-.05A6.34 6.34 0 003.15 15.7a6.34 6.34 0 006.34 6.34 6.34 6.34 0 006.34-6.34V9.44a8.16 8.16 0 003.76.92V6.69z" />
        </svg>
      );
    case "threads":
      return (
        <svg className={cn(base, "text-zinc-200")} viewBox="0 0 24 24" fill="currentColor">
          <path d="M12.186 24h-.007C5.461 23.956.057 18.529 0 11.8v-.318C.074 4.773 5.497-.023 12.207 0c3.268.012 6.162 1.262 8.137 3.518l-2.49 2.368C16.474 4.2 14.447 3.399 12.2 3.39c-4.732.017-8.556 3.862-8.556 8.588 0 4.737 3.84 8.594 8.568 8.594 3.718 0 6.562-1.96 7.604-5.17H12.2V12h11.544c.132.694.2 1.408.2 2.13 0 6.545-4.394 9.87-11.758 9.87z" />
        </svg>
      );
    case "linkedin":
      return (
        <svg className={cn(base, "text-sky-400")} viewBox="0 0 24 24" fill="currentColor">
          <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
        </svg>
      );
    default:
      return <Share2 className={base} />;
  }
}

// ─── Facebook Connect Flow ────────────────────────────────────────────────────

type FbStep = "idle" | "authorizing" | "exchanging" | "selecting" | "connecting";

function FacebookConnectFlow({ onConnected }: { onConnected: () => void }) {
  const toast = useToast();
  const [step, setStep] = useState<FbStep>("idle");
  const [pages, setPages] = useState<any[]>([]);
  const [fbToken, setFbToken] = useState("");
  const [connecting, setConnecting] = useState<string | null>(null);

  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (event.data?.type === "facebook-oauth-callback" && event.data.code) {
        handleExchange(event.data.code);
      }
    }
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

  async function handleStart() {
    setStep("authorizing");
    try {
      const redirectUrl = `${window.location.origin}/social/facebook/callback`;
      const data = await facebookAuthorize(redirectUrl);
      const popup = window.open(data.url, "facebook_oauth", "width=600,height=700,scrollbars=yes");
      if (!popup) {
        toast.error("Popup blocked — allow popups for this site");
        setStep("idle");
      }
    } catch (e: any) {
      toast.error(e.message || "Failed to start Facebook auth");
      setStep("idle");
    }
  }

  async function handleExchange(code: string) {
    setStep("exchanging");
    try {
      const data = await facebookExchange(code);
      setFbToken(data.token);
      const pagesData = await facebookPages(data.token);
      setPages(pagesData.docs || []);
      setStep("selecting");
    } catch (e: any) {
      toast.error(e.message || "Exchange failed");
      setStep("idle");
    }
  }

  async function handleConnectPage(pageId: string) {
    setConnecting(pageId);
    try {
      const page = pages.find((p: any) => p.id === pageId);
      const pageToken = page?.token || fbToken;
      await facebookConnect(pageId, pageToken);
      toast.success("Facebook page connected");
      setStep("idle");
      setPages([]);
      setFbToken("");
      onConnected();
    } catch (e: any) {
      toast.error(e.message || "Connect failed");
    } finally {
      setConnecting(null);
    }
  }

  if (step === "idle") {
    return (
      <Button size="xs" variant="outline" onClick={handleStart} icon={<Plus className="h-3 w-3" />}>
        Connect
      </Button>
    );
  }

  if (step === "authorizing" || step === "exchanging") {
    return (
      <div className="flex items-center gap-1.5 text-[11px] text-zinc-400">
        <RefreshCw className="h-3 w-3 animate-spin text-blue-400" />
        <span>{step === "authorizing" ? "Authorizing..." : "Exchanging..."}</span>
      </div>
    );
  }

  if (step === "selecting") {
    return (
      <div className="mt-2 space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/90 p-2.5">
        <p className="text-[11px] font-medium text-zinc-300">Select Facebook Page:</p>
        {pages.length === 0 ? (
          <p className="text-[10px] text-zinc-500">No pages found with admin access.</p>
        ) : (
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {pages.map((page) => (
              <button
                key={page.id}
                onClick={() => handleConnectPage(page.id)}
                disabled={connecting !== null}
                className={cn(
                  "w-full flex items-center gap-2 rounded border px-2 py-1.5 text-left text-xs transition",
                  connecting === page.id
                    ? "border-blue-500 bg-blue-500/10 text-white"
                    : "border-zinc-800 bg-zinc-950/60 text-zinc-300 hover:border-zinc-700 hover:text-zinc-100"
                )}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{page.name}</p>
                  {page.username && <p className="truncate text-[10px] text-zinc-500">@{page.username}</p>}
                </div>
                {connecting === page.id && <RefreshCw className="h-3 w-3 animate-spin text-blue-400" />}
              </button>
            ))}
          </div>
        )}
        <Button size="xs" variant="ghost" onClick={() => { setStep("idle"); setPages([]); setFbToken(""); }}>
          Cancel
        </Button>
      </div>
    );
  }

  return null;
}

// ─── TikTok Connect Flow ──────────────────────────────────────────────────────

type TtStep = "idle" | "authorizing" | "connecting";

function TikTokConnectFlow({ onConnected }: { onConnected: () => void }) {
  const toast = useToast();
  const [step, setStep] = useState<TtStep>("idle");

  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (event.data?.type === "tiktok-oauth-callback" && event.data.code) {
        handleConnect(event.data.code);
      }
    }
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

  async function handleStart() {
    setStep("authorizing");
    try {
      const redirectUrl = `${window.location.origin}/social/tiktok/callback`;
      const data = await tiktokAuthorize(redirectUrl);
      const popup = window.open(data.url, "tiktok_oauth", "width=600,height=700,scrollbars=yes");
      if (!popup) {
        toast.error("Popup blocked — allow popups for this site");
        setStep("idle");
      }
    } catch (e: any) {
      toast.error(e.message || "Failed to start TikTok auth");
      setStep("idle");
    }
  }

  async function handleConnect(code: string) {
    setStep("connecting");
    try {
      await tiktokConnect(code);
      toast.success("TikTok account connected");
      setStep("idle");
      onConnected();
    } catch (e: any) {
      toast.error(e.message || "Connect failed");
      setStep("idle");
    }
  }

  if (step === "idle") {
    return (
      <Button size="xs" variant="outline" onClick={handleStart} icon={<Plus className="h-3 w-3" />}>
        Connect
      </Button>
    );
  }

  return (
    <div className="flex items-center gap-1.5 text-[11px] text-zinc-400">
      <RefreshCw className="h-3 w-3 animate-spin text-zinc-300" />
      <span>{step === "authorizing" ? "Authorizing..." : "Connecting..."}</span>
    </div>
  );
}

// ─── Simple Connect Flow (Instagram, Threads) ─────────────────────────────────

function SimpleConnectFlow({
  platform,
  authFn,
  connectFn,
  onConnected,
}: {
  platform: string;
  authFn: (redirect: string) => Promise<{ url: string }>;
  connectFn: (code: string) => Promise<{ accountId: string }>;
  onConnected: () => void;
}) {
  const toast = useToast();
  const [step, setStep] = useState<"idle" | "authorizing" | "connecting">("idle");

  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (event.data?.type === `${platform}-oauth-callback` && event.data.code) {
        handleConnect(event.data.code);
      }
    }
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [platform]);

  async function handleStart() {
    setStep("authorizing");
    try {
      const redirectUrl = `${window.location.origin}/social/${platform}/callback`;
      const data = await authFn(redirectUrl);
      const popup = window.open(data.url, `${platform}_oauth`, "width=600,height=700,scrollbars=yes");
      if (!popup) {
        toast.error("Popup blocked");
        setStep("idle");
      }
    } catch (e: any) {
      toast.error(e.message || `Failed to start ${platform} auth`);
      setStep("idle");
    }
  }

  async function handleConnect(code: string) {
    setStep("connecting");
    try {
      await connectFn(code);
      toast.success(`${platform} account connected`);
      setStep("idle");
      onConnected();
    } catch (e: any) {
      toast.error(e.message || "Connect failed");
      setStep("idle");
    }
  }

  if (step === "idle") {
    return (
      <Button size="xs" variant="outline" onClick={handleStart} icon={<Plus className="h-3 w-3" />}>
        Connect
      </Button>
    );
  }
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-zinc-400">
      <RefreshCw className="h-3 w-3 animate-spin text-zinc-300" />
      <span>{step === "authorizing" ? "Authorizing..." : "Connecting..."}</span>
    </div>
  );
}

// ─── Multi-step Connect Flow (YouTube, LinkedIn) ──────────────────────────────

function MultiStepConnectFlow({
  platform,
  authFn,
  exchangeFn,
  listFn,
  connectFn,
  entityLabel,
  entityIdField,
  onConnected,
}: {
  platform: string;
  authFn: (redirect: string) => Promise<{ url: string }>;
  exchangeFn: (code: string) => Promise<{ token: string }>;
  listFn: (token: string) => Promise<any[]>;
  connectFn: (entityId: string, token: string) => Promise<{ accountId: string }>;
  entityLabel: string;
  entityIdField: string;
  onConnected: () => void;
}) {
  const toast = useToast();
  const [step, setStep] = useState<"idle" | "authorizing" | "exchanging" | "selecting" | "connecting">("idle");
  const [entities, setEntities] = useState<any[]>([]);
  const [accessToken, setAccessToken] = useState("");
  const [connecting, setConnecting] = useState<string | null>(null);

  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (event.data?.type === `${platform}-oauth-callback` && event.data.code) {
        handleExchange(event.data.code);
      }
    }
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [platform]);

  async function handleStart() {
    setStep("authorizing");
    try {
      const redirectUrl = `${window.location.origin}/social/${platform}/callback`;
      const data = await authFn(redirectUrl);
      const popup = window.open(data.url, `${platform}_oauth`, "width=600,height=700,scrollbars=yes");
      if (!popup) {
        toast.error("Popup blocked");
        setStep("idle");
      }
    } catch (e: any) {
      toast.error(e.message || `Failed to start ${platform} auth`);
      setStep("idle");
    }
  }

  async function handleExchange(code: string) {
    setStep("exchanging");
    try {
      const data = await exchangeFn(code);
      setAccessToken(data.token);
      const items = await listFn(data.token);
      setEntities(Array.isArray(items) ? items : []);
      setStep("selecting");
    } catch (e: any) {
      toast.error(e.message || "Exchange failed");
      setStep("idle");
    }
  }

  async function handleConnect(entityId: string) {
    setConnecting(entityId);
    try {
      await connectFn(entityId, accessToken);
      toast.success(`${platform} account connected`);
      setStep("idle");
      setEntities([]);
      setAccessToken("");
      onConnected();
    } catch (e: any) {
      toast.error(e.message || "Connect failed");
    } finally {
      setConnecting(null);
    }
  }

  if (step === "idle") {
    return (
      <Button size="xs" variant="outline" onClick={handleStart} icon={<Plus className="h-3 w-3" />}>
        Connect
      </Button>
    );
  }

  if (step === "authorizing" || step === "exchanging") {
    return (
      <div className="flex items-center gap-1.5 text-[11px] text-zinc-400">
        <RefreshCw className="h-3 w-3 animate-spin text-zinc-300" />
        <span>{step === "authorizing" ? "Authorizing..." : "Exchanging..."}</span>
      </div>
    );
  }

  if (step === "selecting") {
    return (
      <div className="mt-2 space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/90 p-2.5">
        <p className="text-[11px] font-medium text-zinc-300">Select {entityLabel}:</p>
        {entities.length === 0 ? (
          <p className="text-[10px] text-zinc-500">No {entityLabel} found.</p>
        ) : (
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {entities.map((entity) => {
              const id = entity[entityIdField] || entity.id || entity._id;
              return (
                <button
                  key={id}
                  onClick={() => handleConnect(id)}
                  disabled={connecting !== null}
                  className={cn(
                    "w-full flex items-center gap-2 rounded border px-2 py-1.5 text-left text-xs transition",
                    connecting === id
                      ? "border-emerald-500 bg-emerald-500/10 text-white"
                      : "border-zinc-800 bg-zinc-950/60 text-zinc-300 hover:border-zinc-700 hover:text-zinc-100"
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{entity.name || entity.title || id}</p>
                    {entity.username && <p className="truncate text-[10px] text-zinc-500">@{entity.username}</p>}
                  </div>
                  {connecting === id && <RefreshCw className="h-3 w-3 animate-spin text-emerald-400" />}
                </button>
              );
            })}
          </div>
        )}
        <Button size="xs" variant="ghost" onClick={() => { setStep("idle"); setEntities([]); setAccessToken(""); }}>
          Cancel
        </Button>
      </div>
    );
  }

  return null;
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function SocialAccounts() {
  const { user } = useAuth();
  const toast = useToast();

  const [accounts, setAccounts] = useState<any[]>([]);
  const [usersList, setUsersList] = useState<any[]>([]);
  const [count, setCount] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [removing, setRemoving] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedPlatform, setSelectedPlatform] = useState<string>("all");
  const [selectedUserId, setSelectedUserId] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const isSuperadmin = Boolean(user?.is_superadmin);

  const loadAccounts = useCallback(async () => {
    setLoading(true);
    try {
      const [accountsData, countData] = await Promise.all([
        fetchAccounts({
          userId: selectedUserId !== "all" ? Number(selectedUserId) : null,
          types: selectedPlatform !== "all" ? selectedPlatform : undefined,
          search: searchQuery.trim() || undefined,
        }),
        fetchAccountCount(),
      ]);
      setAccounts(accountsData.docs || []);
      setCount(countData);
    } catch (e: any) {
      toast.error(e.message || "Failed to load accounts");
    } finally {
      setLoading(false);
    }
  }, [selectedUserId, selectedPlatform, searchQuery, toast]);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  useEffect(() => {
    if (isSuperadmin) {
      fetchAccountUsers().then(setUsersList).catch(() => setUsersList([]));
    }
  }, [isSuperadmin]);

  async function handleRemove(accountId: string, name: string) {
    if (
      !(await confirmDialog({
        title: "Disconnect account?",
        message: `Account "${name}" will be disconnected. You can reconnect it anytime.`,
        confirmText: "Disconnect",
        danger: true,
      }))
    )
      return;

    setRemoving(accountId);
    try {
      await removeAccount(accountId);
      toast.success("Account disconnected successfully");
      loadAccounts();
      if (isSuperadmin) {
        fetchAccountUsers().then(setUsersList).catch(() => {});
      }
    } catch (e: any) {
      toast.error(e.message || "Failed to disconnect account");
    } finally {
      setRemoving(null);
    }
  }

  const platforms = [
    { key: "facebook", label: "Facebook", border: "border-blue-500/30" },
    { key: "tiktok", label: "TikTok", border: "border-zinc-500/30" },
    { key: "instagram", label: "Instagram", border: "border-pink-500/30" },
    { key: "threads", label: "Threads", border: "border-zinc-400/30" },
    { key: "youtube", label: "YouTube", border: "border-red-500/30" },
    { key: "linkedin", label: "LinkedIn", border: "border-sky-500/30" },
  ];

  // Client-side filtering for search & status (if already loaded)
  const filteredAccounts = useMemo(() => {
    return accounts.filter((acc) => {
      if (statusFilter === "live" && !acc.isConnected) return false;
      if (statusFilter === "offline" && acc.isConnected) return false;

      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const nameMatch = acc.name?.toLowerCase().includes(query);
        const usernameMatch = acc.username?.toLowerCase().includes(query);
        const ownerNameMatch = acc.owner?.full_name?.toLowerCase().includes(query);
        const ownerEmailMatch = acc.owner?.email?.toLowerCase().includes(query);
        if (!nameMatch && !usernameMatch && !ownerNameMatch && !ownerEmailMatch) {
          return false;
        }
      }
      return true;
    });
  }, [accounts, statusFilter, searchQuery]);

  return (
    <div className="flex h-full min-h-0 flex-col space-y-3 p-2 sm:p-4 lg:p-5 overflow-y-auto">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-zinc-800/80 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <Share2 className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-semibold text-zinc-100">Social Accounts</h1>
              {isSuperadmin ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-violet-500/15 text-violet-300 border border-violet-500/30">
                  <ShieldCheck className="h-3 w-3" />
                  Superadmin Mode (All Users)
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-zinc-800 text-zinc-300">
                  <UserIcon className="h-3 w-3" />
                  My Accounts
                </span>
              )}
            </div>
            <p className="text-[11px] text-zinc-500">
              {isSuperadmin
                ? "Monitor and manage connected social media channels across all system users."
                : "Manage and authorize your social media channels for direct video publishing."}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <Button
            size="xs"
            variant="outline"
            onClick={loadAccounts}
            loading={loading}
            icon={<RefreshCw className="h-3 w-3" />}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Stats row */}
      {count && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
          <button
            type="button"
            onClick={() => setSelectedPlatform("all")}
            className={cn(
              "rounded-lg border px-3 py-2 text-left transition-all",
              selectedPlatform === "all"
                ? "border-emerald-500/60 bg-emerald-500/10 shadow-sm"
                : "border-zinc-800/80 bg-zinc-950/40 hover:border-zinc-700"
            )}
          >
            <div className="flex items-center gap-1.5">
              <Globe className="h-3.5 w-3.5 text-emerald-400" />
              <span className="text-[10px] font-medium text-zinc-300">All Platforms</span>
            </div>
            <p className="text-base font-semibold mt-0.5 text-zinc-100 tabular-nums">
              {count.total || accounts.length}
            </p>
          </button>

          {platforms.map((p) => {
            const val = (count as any)[p.key] || 0;
            const active = selectedPlatform === p.key;
            return (
              <button
                key={p.key}
                type="button"
                onClick={() => setSelectedPlatform(active ? "all" : p.key)}
                className={cn(
                  "rounded-lg border px-3 py-2 text-left transition-all",
                  active
                    ? "border-violet-500/60 bg-violet-500/10 shadow-sm"
                    : "border-zinc-800/80 bg-zinc-950/40 hover:border-zinc-700"
                )}
              >
                <div className="flex items-center gap-1.5">
                  <PlatformIcon type={p.key} className="h-3.5 w-3.5" />
                  <span className="text-[10px] font-medium text-zinc-300">{p.label}</span>
                </div>
                <p className={cn("text-base font-semibold mt-0.5 tabular-nums", val > 0 ? "text-zinc-100" : "text-zinc-600")}>
                  {val}
                </p>
              </button>
            );
          })}
        </div>
      )}

      {/* Main Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 min-h-0 flex-1">
        {/* Left Column: Connect Platform (4 cols on large screen) */}
        <div className="lg:col-span-4 space-y-3">
          <Card className="p-3.5 space-y-3">
            <div className="flex items-center justify-between border-b border-zinc-800/80 pb-2">
              <div className="flex items-center gap-1.5">
                <Plus className="h-3.5 w-3.5 text-emerald-400" />
                <h3 className="text-xs font-semibold text-zinc-100">Connect New Channel</h3>
              </div>
              <span className="text-[10px] text-zinc-500">6 Platforms</span>
            </div>

            <div className="space-y-1.5">
              {/* Facebook */}
              <div className="flex items-center justify-between rounded-lg border border-zinc-800/70 bg-zinc-950/40 px-3 py-2 hover:border-zinc-700 transition">
                <div className="flex items-center gap-2">
                  <Facebook className="h-4 w-4 text-blue-400" />
                  <div>
                    <p className="text-xs font-medium text-zinc-200">Facebook</p>
                    <p className="text-[10px] text-zinc-500">Pages & Video</p>
                  </div>
                </div>
                <FacebookConnectFlow onConnected={loadAccounts} />
              </div>

              {/* TikTok */}
              <div className="flex items-center justify-between rounded-lg border border-zinc-800/70 bg-zinc-950/40 px-3 py-2 hover:border-zinc-700 transition">
                <div className="flex items-center gap-2">
                  <PlatformIcon type="tiktok" className="h-4 w-4" />
                  <div>
                    <p className="text-xs font-medium text-zinc-200">TikTok</p>
                    <p className="text-[10px] text-zinc-500">Short-form Video</p>
                  </div>
                </div>
                <TikTokConnectFlow onConnected={loadAccounts} />
              </div>

              {/* Instagram */}
              <div className="flex items-center justify-between rounded-lg border border-zinc-800/70 bg-zinc-950/40 px-3 py-2 hover:border-zinc-700 transition">
                <div className="flex items-center gap-2">
                  <Instagram className="h-4 w-4 text-pink-400" />
                  <div>
                    <p className="text-xs font-medium text-zinc-200">Instagram</p>
                    <p className="text-[10px] text-zinc-500">Reels & Media</p>
                  </div>
                </div>
                <SimpleConnectFlow
                  platform="instagram"
                  authFn={instagramAuthorize}
                  connectFn={instagramConnect}
                  onConnected={loadAccounts}
                />
              </div>

              {/* Threads */}
              <div className="flex items-center justify-between rounded-lg border border-zinc-800/70 bg-zinc-950/40 px-3 py-2 hover:border-zinc-700 transition">
                <div className="flex items-center gap-2">
                  <PlatformIcon type="threads" className="h-4 w-4" />
                  <div>
                    <p className="text-xs font-medium text-zinc-200">Threads</p>
                    <p className="text-[10px] text-zinc-500">Text & Video posts</p>
                  </div>
                </div>
                <SimpleConnectFlow
                  platform="threads"
                  authFn={threadsAuthorize}
                  connectFn={threadsConnect}
                  onConnected={loadAccounts}
                />
              </div>

              {/* YouTube */}
              <div className="flex items-center justify-between rounded-lg border border-zinc-800/70 bg-zinc-950/40 px-3 py-2 hover:border-zinc-700 transition">
                <div className="flex items-center gap-2">
                  <Youtube className="h-4 w-4 text-red-400" />
                  <div>
                    <p className="text-xs font-medium text-zinc-200">YouTube</p>
                    <p className="text-[10px] text-zinc-500">Shorts & Channels</p>
                  </div>
                </div>
                <MultiStepConnectFlow
                  platform="youtube"
                  authFn={youtubeAuthorize}
                  exchangeFn={youtubeExchange}
                  listFn={youtubeChannels}
                  connectFn={youtubeConnect}
                  entityLabel="channel"
                  entityIdField="channelId"
                  onConnected={loadAccounts}
                />
              </div>

              {/* LinkedIn */}
              <div className="flex items-center justify-between rounded-lg border border-zinc-800/70 bg-zinc-950/40 px-3 py-2 hover:border-zinc-700 transition">
                <div className="flex items-center gap-2">
                  <PlatformIcon type="linkedin" className="h-4 w-4 text-sky-400" />
                  <div>
                    <p className="text-xs font-medium text-zinc-200">LinkedIn</p>
                    <p className="text-[10px] text-zinc-500">Company & Profiles</p>
                  </div>
                </div>
                <MultiStepConnectFlow
                  platform="linkedin"
                  authFn={linkedinAuthorize}
                  exchangeFn={linkedinExchange}
                  listFn={linkedinOrganizations}
                  connectFn={linkedinConnect}
                  entityLabel="organization"
                  entityIdField="organizationId"
                  onConnected={loadAccounts}
                />
              </div>
            </div>
          </Card>
        </div>

        {/* Right Column: Connected Accounts & Filters (8 cols on large screen) */}
        <div className="lg:col-span-8 space-y-3 flex flex-col min-h-0">
          <Card className="p-3.5 space-y-3 flex-1 flex flex-col min-h-0">
            {/* Filter toolbar */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800/80 pb-2.5">
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-emerald-400" />
                <h3 className="text-xs font-semibold text-zinc-100">Connected Accounts</h3>
                <span className="text-[10px] font-medium text-zinc-400 bg-zinc-800 px-1.5 py-0.5 rounded">
                  {filteredAccounts.length}
                </span>
              </div>

              {/* User filter for superadmin */}
              <div className="flex flex-wrap items-center gap-2">
                {isSuperadmin && usersList.length > 0 && (
                  <div className="flex items-center gap-1.5">
                    <Users className="h-3.5 w-3.5 text-zinc-400" />
                    <select
                      value={selectedUserId}
                      onChange={(e) => setSelectedUserId(e.target.value)}
                      className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-zinc-600"
                    >
                      <option value="all">All Users ({usersList.reduce((a, b) => a + (b.accounts_count || 0), 0)})</option>
                      {usersList.map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.full_name || u.email} ({u.accounts_count})
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Status filter */}
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-zinc-600"
                >
                  <option value="all">Status: All</option>
                  <option value="live">Live Only</option>
                  <option value="offline">Offline Only</option>
                </select>
              </div>
            </div>

            {/* Search filter input */}
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-500" />
              <input
                type="text"
                placeholder={
                  isSuperadmin
                    ? "Search by account name, username, or owner email/name..."
                    : "Search connected accounts..."
                }
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-md border border-zinc-800/80 bg-zinc-950/60 pl-8 pr-3 py-1.5 text-xs text-zinc-200 placeholder:text-zinc-600 outline-none focus:border-zinc-600 transition"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-2 text-[10px] text-zinc-500 hover:text-zinc-300"
                >
                  Clear
                </button>
              )}
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto space-y-1.5 pr-0.5">
              {loading ? (
                <div className="flex flex-col items-center justify-center py-12 text-zinc-500">
                  <RefreshCw className="h-5 w-5 animate-spin mb-2" />
                  <p className="text-xs">Loading accounts...</p>
                </div>
              ) : filteredAccounts.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <div className="h-9 w-9 rounded-full bg-zinc-900 flex items-center justify-center text-zinc-600 mb-2">
                    <Share2 className="h-4 w-4" />
                  </div>
                  <p className="text-xs font-medium text-zinc-400">No accounts found</p>
                  <p className="text-[11px] text-zinc-600 mt-0.5 max-w-xs">
                    {searchQuery || selectedPlatform !== "all" || selectedUserId !== "all"
                      ? "Try changing your filter or search query."
                      : "Connect your first social media platform from the panel on the left."}
                  </p>
                </div>
              ) : (
                <div className="space-y-1.5">
                  {filteredAccounts.map((acc) => {
                    const accId = acc._id || acc.id;
                    const isLive = Boolean(acc.isConnected);
                    const owner = acc.owner;

                    return (
                      <div
                        key={accId}
                        className="flex items-center gap-2.5 rounded-lg border border-zinc-800/60 bg-zinc-950/30 px-3 py-2 hover:border-zinc-700 transition-all group"
                      >
                        {/* Avatar */}
                        {acc.picture ? (
                          <img
                            src={acc.picture}
                            alt=""
                            className="h-8 w-8 rounded-full object-cover shrink-0 ring-1 ring-zinc-800"
                          />
                        ) : (
                          <div className="h-8 w-8 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center shrink-0">
                            <PlatformIcon type={acc.type} className="h-3.5 w-3.5" />
                          </div>
                        )}

                        {/* Info */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="text-xs font-medium text-zinc-100 truncate">{acc.name || "Unnamed Account"}</p>
                            {isLive ? (
                              <span className="inline-flex items-center gap-1 text-[9px] text-emerald-400 bg-emerald-500/10 px-1.5 py-0.2 rounded font-medium">
                                <span className="h-1 w-1 rounded-full bg-emerald-400 animate-pulse" />
                                Live
                              </span>
                            ) : (
                              <span className="text-[9px] text-red-400 bg-red-500/10 px-1.5 py-0.2 rounded font-medium">
                                Offline
                              </span>
                            )}
                          </div>

                          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-0.5 text-[10px] text-zinc-500">
                            <span className="flex items-center gap-1">
                              <PlatformIcon type={acc.type} className="h-2.5 w-2.5" />
                              <span className="capitalize">{acc.type}</span>
                            </span>
                            {acc.username && <span>@{acc.username}</span>}

                            {/* Owner tag if superadmin */}
                            {isSuperadmin && (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 text-[9px]">
                                <UserIcon className="h-2.5 w-2.5 text-violet-400" />
                                <span>{owner ? `${owner.full_name || owner.email}` : "System / Unassigned"}</span>
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Action buttons */}
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => handleRemove(accId, acc.name)}
                            disabled={removing === accId}
                            className="p-1.5 rounded text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                            title="Disconnect Account"
                          >
                            {removing === accId ? (
                              <RefreshCw className="h-3.5 w-3.5 animate-spin text-red-400" />
                            ) : (
                              <Trash2 className="h-3.5 w-3.5" />
                            )}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
