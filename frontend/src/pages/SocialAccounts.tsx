import { useState, useEffect, useCallback } from "react";
import { Share2, Facebook, Instagram, Youtube, RefreshCw, Trash2, Plus, ExternalLink, AlertTriangle } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { confirmDialog } from "@/components/ui/ConfirmDialog";
import { API_BASE, getToken } from "@/lib/api";
import { cn } from "@/lib/utils";

// ─── API helpers ──────────────────────────────────────────────────────────────

async function fetchAccounts(page = 1, limit = 20): Promise<any> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/social/accounts?page=${page}&limit=${limit}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to fetch accounts");
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

// YouTube (multi-step)
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

// LinkedIn (multi-step)
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

// ─── Platform icon helper ─────────────────────────────────────────────────────

function PlatformIcon({ type, className }: { type: string; className?: string }) {
  const base = cn("h-4 w-4", className);
  switch (type) {
    case "facebook": return <Facebook className={cn(base, "text-blue-400")} />;
    case "instagram": return <Instagram className={cn(base, "text-pink-400")} />;
    case "youtube": return <Youtube className={cn(base, "text-red-400")} />;
    case "tiktok": return <svg className={cn(base, "text-zinc-200")} viewBox="0 0 24 24" fill="currentColor"><path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.88 2.89 2.89 0 01-2.88-2.88 2.89 2.89 0 012.88-2.88c.28 0 .56.04.82.1v-3.5a6.37 6.37 0 00-.82-.05A6.34 6.34 0 003.15 15.7a6.34 6.34 0 006.34 6.34 6.34 6.34 0 006.34-6.34V9.44a8.16 8.16 0 003.76.92V6.69z"/></svg>;
    case "threads": return <svg className={cn(base, "text-zinc-200")} viewBox="0 0 24 24" fill="currentColor"><path d="M12.186 24h-.007C5.461 23.956.057 18.529 0 11.8v-.318C.074 4.773 5.497-.023 12.207 0c3.268.012 6.162 1.262 8.137 3.518l-2.49 2.368C16.474 4.2 14.447 3.399 12.2 3.39c-4.732.017-8.556 3.862-8.556 8.588 0 4.737 3.84 8.594 8.568 8.594 3.718 0 6.562-1.96 7.604-5.17H12.2V12h11.544c.132.694.2 1.408.2 2.13 0 6.545-4.394 9.87-11.758 9.87z"/></svg>;
    case "linkedin": return <svg className={cn(base, "text-blue-300")} viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>;
    default: return <Share2 className={base} />;
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

  // Listen for OAuth callback message
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
      // Use current origin as redirect — works for both local and production
      // Repliz requires a valid URL (not localhost). For local dev, use ngrok or nip.io.
      const redirectUrl = `${window.location.origin}/social/facebook/callback`;
      const data = await facebookAuthorize(redirectUrl);
      // Open Facebook OAuth in popup
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
      // Fetch pages
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
      // Use the page-specific token (not user token) — required by Facebook Graph API
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
      <Button size="sm" onClick={handleStart} icon={<Facebook className="h-3.5 w-3.5" />}>
        Connect Facebook
      </Button>
    );
  }

  if (step === "authorizing" || step === "exchanging") {
    return (
      <div className="flex items-center gap-2 text-xs text-zinc-400">
        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
        {step === "authorizing" ? "Waiting for Facebook authorization..." : "Exchanging token..."}
      </div>
    );
  }

  if (step === "selecting") {
    return (
      <div className="space-y-2">
        <p className="text-xs text-zinc-400 mb-2">Select a page to connect:</p>
        {pages.length === 0 ? (
          <p className="text-[11px] text-zinc-600">No pages found. Make sure you have admin access to at least one Facebook Page.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {pages.map((page) => (
              <button
                key={page.id}
                onClick={() => handleConnectPage(page.id)}
                disabled={connecting !== null}
                className={cn(
                  "flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors",
                  connecting === page.id
                    ? "border-blue-500 bg-blue-500/10"
                    : "border-zinc-800 hover:border-zinc-600 bg-zinc-950/60"
                )}
              >
                {page.picture ? (
                  <img src={page.picture} alt="" className="h-8 w-8 rounded-full object-cover" />
                ) : (
                  <div className="h-8 w-8 rounded-full bg-zinc-800 flex items-center justify-center">
                    <Facebook className="h-4 w-4 text-blue-400" />
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-zinc-200 font-medium truncate">{page.name}</p>
                  {page.username && <p className="text-[10px] text-zinc-500 truncate">@{page.username}</p>}
                </div>
                {connecting === page.id && <RefreshCw className="h-3.5 w-3.5 text-blue-400 animate-spin shrink-0" />}
              </button>
            ))}
          </div>
        )}
        <Button size="sm" variant="outline" onClick={() => { setStep("idle"); setPages([]); setFbToken(""); }}>
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

  // Listen for OAuth callback message
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
      <Button size="sm" onClick={handleStart} icon={<PlatformIcon type="tiktok" className="h-3.5 w-3.5" />}>
        Connect TikTok
      </Button>
    );
  }

  return (
    <div className="flex items-center gap-2 text-xs text-zinc-400">
      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
      {step === "authorizing" ? "Waiting for TikTok authorization..." : "Connecting..."}
    </div>
  );
}

// ─── Simple Connect Flow (Instagram, Threads) ─────────────────────────────────

function SimpleConnectFlow({ platform, authFn, connectFn, onConnected }: {
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
  }, []);

  async function handleStart() {
    setStep("authorizing");
    try {
      const redirectUrl = `${window.location.origin}/social/${platform}/callback`;
      const data = await authFn(redirectUrl);
      const popup = window.open(data.url, `${platform}_oauth`, "width=600,height=700,scrollbars=yes");
      if (!popup) { toast.error("Popup blocked"); setStep("idle"); }
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
      <Button size="sm" onClick={handleStart} icon={<PlatformIcon type={platform} className="h-3.5 w-3.5" />}>
        Connect
      </Button>
    );
  }
  return (
    <div className="flex items-center gap-2 text-xs text-zinc-400">
      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
      {step === "authorizing" ? "Waiting..." : "Connecting..."}
    </div>
  );
}

// ─── Multi-step Connect Flow (YouTube, LinkedIn) ──────────────────────────────

function MultiStepConnectFlow({ platform, authFn, exchangeFn, listFn, connectFn, entityLabel, entityIdField, onConnected }: {
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
  }, []);

  async function handleStart() {
    setStep("authorizing");
    try {
      const redirectUrl = `${window.location.origin}/social/${platform}/callback`;
      const data = await authFn(redirectUrl);
      const popup = window.open(data.url, `${platform}_oauth`, "width=600,height=700,scrollbars=yes");
      if (!popup) { toast.error("Popup blocked"); setStep("idle"); }
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
      <Button size="sm" onClick={handleStart} icon={<PlatformIcon type={platform} className="h-3.5 w-3.5" />}>
        Connect
      </Button>
    );
  }

  if (step === "authorizing" || step === "exchanging") {
    return (
      <div className="flex items-center gap-2 text-xs text-zinc-400">
        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
        {step === "authorizing" ? "Waiting..." : "Exchanging..."}
      </div>
    );
  }

  if (step === "selecting") {
    return (
      <div className="space-y-2">
        <p className="text-xs text-zinc-400 mb-2">Select {entityLabel}:</p>
        {entities.length === 0 ? (
          <p className="text-[11px] text-zinc-600">No {entityLabel} found.</p>
        ) : (
          <div className="space-y-1.5">
            {entities.map((entity) => {
              const id = entity[entityIdField] || entity.id || entity._id;
              return (
                <button
                  key={id}
                  onClick={() => handleConnect(id)}
                  disabled={connecting !== null}
                  className={cn(
                    "w-full flex items-center gap-3 rounded-lg border px-3 py-2 text-left transition-colors",
                    connecting === id ? "border-emerald-500 bg-emerald-500/10" : "border-zinc-800 hover:border-zinc-600 bg-zinc-950/60"
                  )}
                >
                  {entity.picture && <img src={entity.picture} alt="" className="h-7 w-7 rounded-full object-cover" />}
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-zinc-200 font-medium truncate">{entity.name || entity.title || id}</p>
                    {entity.username && <p className="text-[10px] text-zinc-500">@{entity.username}</p>}
                  </div>
                  {connecting === id && <RefreshCw className="h-3.5 w-3.5 animate-spin shrink-0" />}
                </button>
              );
            })}
          </div>
        )}
        <Button size="sm" variant="outline" onClick={() => { setStep("idle"); setEntities([]); setAccessToken(""); }}>
          Cancel
        </Button>
      </div>
    );
  }

  return null;
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function SocialAccounts() {
  const toast = useToast();
  const [accounts, setAccounts] = useState<any[]>([]);
  const [count, setCount] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [removing, setRemoving] = useState<string | null>(null);

  const loadAccounts = useCallback(async () => {
    setLoading(true);
    try {
      const [data, countData] = await Promise.all([fetchAccounts(), fetchAccountCount()]);
      setAccounts(data.docs || []);
      setCount(countData);
    } catch (e: any) {
      toast.error(e.message || "Failed to load accounts");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);

  async function handleRemove(accountId: string, name: string) {
    if (!(await confirmDialog({
      title: "Disconnect account?",
      message: `"${name}" will be disconnected. You can reconnect it later.`,
      confirmText: "Disconnect",
      danger: true,
    }))) return;
    setRemoving(accountId);
    try {
      await removeAccount(accountId);
      toast.success("Account disconnected");
      loadAccounts();
    } catch (e: any) {
      toast.error(e.message || "Failed to remove");
    } finally {
      setRemoving(null);
    }
  }

  const platforms = [
    { key: "facebook", label: "Facebook", available: true },
    { key: "tiktok", label: "TikTok", available: true },
    { key: "instagram", label: "Instagram", available: true },
    { key: "threads", label: "Threads", available: true },
    { key: "youtube", label: "YouTube", available: true },
    { key: "linkedin", label: "LinkedIn", available: true },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0 mb-3">
        <div className="flex items-center gap-2">
          <Share2 className="h-4 w-4 text-emerald-400" />
          <h1 className="text-base font-semibold text-zinc-100">Social Accounts</h1>
          {count && <Badge variant="default" size="sm">{count.total || 0} connected</Badge>}
        </div>
        <Button size="sm" variant="outline" onClick={loadAccounts} loading={loading} icon={<RefreshCw className="h-3 w-3" />}>
          Refresh
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto space-y-3">
        {/* Platform counts — compact row */}
        {count && (
          <div className="flex flex-wrap gap-1.5">
            {platforms.map((p) => (
              <div key={p.key} className="flex items-center gap-1.5 rounded-md border border-zinc-800/60 bg-zinc-950/40 px-2 py-1">
                <PlatformIcon type={p.key} className="h-3 w-3" />
                <span className="text-[10px] text-zinc-400">{p.label}</span>
                <span className="text-[10px] font-bold text-zinc-200">{(count as any)[p.key] || 0}</span>
              </div>
            ))}
          </div>
        )}

        {/* Connect new account — compact grid */}
        <Card className="p-3">
          <div className="flex items-center gap-2 mb-2">
            <Plus className="h-3.5 w-3.5 text-emerald-400" />
            <h3 className="text-xs font-semibold text-zinc-100">Connect Account</h3>
          </div>

          <div className="space-y-1.5">
            {/* Facebook */}
            <div className="flex items-center justify-between rounded-md border border-zinc-800 px-3 py-2">
              <div className="flex items-center gap-2">
                <Facebook className="h-4 w-4 text-blue-400" />
                <span className="text-[11px] font-medium text-zinc-200">Facebook Pages</span>
              </div>
              <FacebookConnectFlow onConnected={loadAccounts} />
            </div>

            {/* TikTok */}
            <div className="flex items-center justify-between rounded-md border border-zinc-800 px-3 py-2">
              <div className="flex items-center gap-2">
                <PlatformIcon type="tiktok" className="h-4 w-4" />
                <span className="text-[11px] font-medium text-zinc-200">TikTok</span>
              </div>
              <TikTokConnectFlow onConnected={loadAccounts} />
            </div>

            {/* Instagram */}
            <div className="flex items-center justify-between rounded-md border border-zinc-800 px-3 py-2">
              <div className="flex items-center gap-2">
                <Instagram className="h-4 w-4 text-pink-400" />
                <span className="text-[11px] font-medium text-zinc-200">Instagram</span>
              </div>
              <SimpleConnectFlow platform="instagram" authFn={instagramAuthorize} connectFn={instagramConnect} onConnected={loadAccounts} />
            </div>

            {/* Threads */}
            <div className="flex items-center justify-between rounded-md border border-zinc-800 px-3 py-2">
              <div className="flex items-center gap-2">
                <PlatformIcon type="threads" className="h-4 w-4" />
                <span className="text-[11px] font-medium text-zinc-200">Threads</span>
              </div>
              <SimpleConnectFlow platform="threads" authFn={threadsAuthorize} connectFn={threadsConnect} onConnected={loadAccounts} />
            </div>

            {/* YouTube */}
            <div className="flex items-center justify-between rounded-md border border-zinc-800 px-3 py-2">
              <div className="flex items-center gap-2">
                <Youtube className="h-4 w-4 text-red-400" />
                <span className="text-[11px] font-medium text-zinc-200">YouTube</span>
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
            <div className="flex items-center justify-between rounded-md border border-zinc-800 px-3 py-2">
              <div className="flex items-center gap-2">
                <PlatformIcon type="linkedin" className="h-4 w-4" />
                <span className="text-[11px] font-medium text-zinc-200">LinkedIn</span>
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

        {/* Connected accounts list */}
        <Card className="p-3">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-zinc-100">Connected Accounts</h3>
            <span className="text-[9px] text-zinc-600">{accounts.length} account(s)</span>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-4">
              <RefreshCw className="h-4 w-4 text-zinc-600 animate-spin" />
              <span className="ml-2 text-[11px] text-zinc-500">Loading...</span>
            </div>
          ) : accounts.length === 0 ? (
            <div className="text-center py-4">
              <Share2 className="h-6 w-6 text-zinc-700 mx-auto mb-1" />
              <p className="text-[11px] text-zinc-500">No accounts connected yet</p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {accounts.map((acc) => (
                <div key={acc._id || acc.id} className="flex items-center gap-2.5 rounded-md border border-zinc-800 px-3 py-2 hover:border-zinc-700 transition-colors">
                  {acc.picture ? (
                    <img src={acc.picture} alt="" className="h-7 w-7 rounded-full object-cover shrink-0" />
                  ) : (
                    <div className="h-7 w-7 rounded-full bg-zinc-800 flex items-center justify-center shrink-0">
                      <PlatformIcon type={acc.type} className="h-3 w-3" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <p className="text-[11px] text-zinc-200 font-medium truncate">{acc.name}</p>
                      <PlatformIcon type={acc.type} className="h-2.5 w-2.5" />
                      {acc.isConnected ? (
                        <span className="text-[8px] bg-emerald-500/15 text-emerald-400 px-1 py-0.5 rounded font-medium">Active</span>
                      ) : (
                        <span className="text-[8px] bg-red-500/15 text-red-400 px-1 py-0.5 rounded font-medium">Offline</span>
                      )}
                    </div>
                    <p className="text-[9px] text-zinc-500 truncate">@{acc.username || acc.generatedId} · {acc.type}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRemove(acc._id || acc.id, acc.name)}
                    disabled={removing === (acc._id || acc.id)}
                    className="p-1 rounded text-zinc-600 hover:text-red-400 hover:bg-zinc-800 transition-colors shrink-0"
                    title="Disconnect"
                  >
                    {removing === (acc._id || acc.id) ? (
                      <RefreshCw className="h-3 w-3 animate-spin" />
                    ) : (
                      <Trash2 className="h-3 w-3" />
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function settings_configured(): boolean {
  return true;
}
