import { useEffect } from "react";

/**
 * TikTok OAuth callback page.
 * Opened in a popup by TikTokConnectFlow — extracts the code from URL params
 * and posts it back to the parent window.
 */
export function TikTokCallback() {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    if (code && window.opener) {
      window.opener.postMessage({ type: "tiktok-oauth-callback", code }, window.location.origin);
      window.close();
    }
  }, []);

  return (
    <div className="min-h-screen bg-[#09090b] flex items-center justify-center">
      <div className="text-center">
        <div className="h-8 w-8 rounded-full border-2 border-zinc-400 border-t-transparent animate-spin mx-auto mb-3" />
        <p className="text-sm text-zinc-400">Connecting TikTok account...</p>
        <p className="text-[10px] text-zinc-600 mt-1">This window will close automatically</p>
      </div>
    </div>
  );
}
