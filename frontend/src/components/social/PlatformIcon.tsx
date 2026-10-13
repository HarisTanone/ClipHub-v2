import React from "react";
import {
  Share2,
  Facebook,
  Instagram,
  Youtube,
} from "lucide-react";
import { cn } from "@/lib/utils";

export function PlatformIcon({ type, className }: { type: string; className?: string }) {
  const base = cn("h-4 w-4 shrink-0", className);
  const t = (type || "").toLowerCase();
  switch (t) {
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
