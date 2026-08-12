import { useEffect } from "react";

/**
 * Generic OAuth callback page for Instagram, Threads, YouTube, LinkedIn.
 * Opened in a popup — extracts the code from URL params
 * and posts it back to the parent window with the platform type.
 */
export function SocialCallback() {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    // Determine platform from URL path: /social/{platform}/callback
    const pathParts = window.location.pathname.split("/");
    const platformIdx = pathParts.indexOf("social") + 1;
    const platform = pathParts[platformIdx] || "unknown";

    if (code && window.opener) {
      window.opener.postMessage(
        { type: `${platform}-oauth-callback`, code },
        window.location.origin
      );
      window.close();
    }
  }, []);

  return (
    <div className="min-h-screen bg-[#09090b] flex items-center justify-center">
      <div className="text-center">
        <div className="h-8 w-8 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin mx-auto mb-3" />
        <p className="text-sm text-zinc-400">Connecting account...</p>
        <p className="text-[10px] text-zinc-600 mt-1">This window will close automatically</p>
      </div>
    </div>
  );
}
