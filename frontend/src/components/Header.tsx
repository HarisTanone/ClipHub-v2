import { Menu, LogOut } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";

interface HeaderProps {
  onMenuClick: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const { user, logout } = useAuth();

  return (
    <header className="flex h-12 items-center justify-between border-b border-zinc-800/60 bg-[#0c0c0f]/80 px-4 backdrop-blur-md shrink-0">
      {/* Left: mobile menu + breadcrumb */}
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          className="md:hidden rounded-md p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
          aria-label="Open menu"
        >
          <Menu className="h-4.5 w-4.5" />
        </button>
        <span className="text-xs text-zinc-500 hidden md:block font-medium">Pipeline v0.4</span>
      </div>

      {/* Right: user */}
      <div className="flex items-center gap-2">
        {user && (
          <>
            <span className="text-xs text-zinc-400 hidden sm:block">{user.full_name || user.email}</span>
            <span className="text-[10px] text-zinc-500 hidden sm:block">({user.role})</span>
            <button
              onClick={logout}
              className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300 transition-colors"
              title="Logout"
            >
              <LogOut className="h-3.5 w-3.5" />
            </button>
          </>
        )}
      </div>
    </header>
  );
}
