import { useState } from "react";
import { Lock, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

interface FeatureLockProps {
  children: React.ReactNode;
  featureName: string;
  featureCode: string;
  isSuperadmin?: boolean;
  userFeatures?: string[];
  className?: string;
}

/**
 * FeatureLock — wraps any UI section with a lock overlay.
 * Access granted if: superadmin OR user has the feature_code in their features list.
 * Regular users without access see "Coming Soon" animation on click.
 */
export function FeatureLock({ children, featureName, featureCode, isSuperadmin, userFeatures = [], className }: FeatureLockProps) {
  const [showNotif, setShowNotif] = useState(false);

  // Superadmin or user has this feature granted
  const hasAccess = isSuperadmin || userFeatures.includes(featureCode);

  if (hasAccess) {
    return <>{children}</>;
  }

  function handleClick() {
    setShowNotif(true);
    setTimeout(() => setShowNotif(false), 2500);
  }

  return (
    <div className={cn("relative", className)}>
      {/* Locked content (blurred) */}
      <div className="pointer-events-none select-none opacity-40 blur-[1px]">
        {children}
      </div>

      {/* Lock overlay */}
      <div
        onClick={handleClick}
        className="absolute inset-0 z-10 flex items-center justify-center cursor-pointer rounded-lg border border-dashed border-zinc-700/50 bg-zinc-900/20 backdrop-blur-[0.5px] transition-all hover:border-zinc-600 hover:bg-zinc-900/30"
      >
        <div className="flex flex-col items-center gap-2">
          <div className="w-10 h-10 rounded-full bg-zinc-800/80 flex items-center justify-center border border-zinc-700/50">
            <Lock className="h-4 w-4 text-zinc-500" />
          </div>
          <span className="text-[10px] text-zinc-500 font-medium">{featureName}</span>
          <span className="text-[8px] text-zinc-600">Premium</span>
        </div>
      </div>

      {/* Coming Soon notification */}
      {showNotif && (
        <div className="absolute inset-0 z-20 flex items-center justify-center pointer-events-none">
          <div className="animate-[comingSoon_2.5s_ease-out_forwards] flex flex-col items-center gap-3 bg-zinc-900/95 border border-emerald-500/30 rounded-2xl px-8 py-6 shadow-2xl shadow-emerald-500/10">
            <div className="relative">
              <Sparkles className="h-8 w-8 text-emerald-400 animate-pulse" />
              <div className="absolute -top-1 -right-1 w-3 h-3 bg-emerald-500 rounded-full animate-ping" />
            </div>
            <div className="text-center">
              <p className="text-sm font-semibold text-zinc-100">Coming Soon</p>
              <p className="text-[10px] text-zinc-500 mt-1">{featureName}</p>
            </div>
            <div className="flex gap-1">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="w-1.5 h-1.5 rounded-full bg-emerald-500"
                  style={{ animation: `bounce 0.6s ${i * 0.15}s infinite alternate` }}
                />
              ))}
            </div>
          </div>
        </div>
      )}

      <style>{`
        @keyframes comingSoon {
          0% { opacity: 0; transform: scale(0.8); }
          15% { opacity: 1; transform: scale(1.02); }
          85% { opacity: 1; transform: scale(1); }
          100% { opacity: 0; transform: scale(0.95) translateY(-10px); }
        }
        @keyframes bounce {
          from { transform: translateY(0); }
          to { transform: translateY(-4px); }
        }
      `}</style>
    </div>
  );
}
