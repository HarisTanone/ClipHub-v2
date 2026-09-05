import { useState, useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard, PlusCircle, Settings, Zap, X, ChevronLeft, ChevronRight,
  Share2, Film, ChevronDown, SlidersHorizontal, Bot, Video, Cpu, Sparkles,
  Palette, Send, HardDrive, BrainCircuit, ShieldCheck, Terminal
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";

const mainNavItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/jobs/new", icon: PlusCircle, label: "New Job" },
  { to: "/video-generator", icon: Film, label: "Video Generator" },
  { to: "/social", icon: Share2, label: "Social Accounts" },
];

interface SidebarProps {
  open: boolean;
  onClose: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export function Sidebar({ open, onClose, collapsed, onToggleCollapse }: SidebarProps) {
  const location = useLocation();
  const { user } = useAuth();
  const isSuperadmin = user?.is_superadmin || user?.role === "superadmin" || false;

  const isSettingsActive = location.pathname.startsWith("/settings");
  const isHermesActive = location.pathname.startsWith("/settings/hermes");

  const [settingsOpen, setSettingsOpen] = useState<boolean>(true);
  const [hermesOpen, setHermesOpen] = useState<boolean>(true);

  // Auto-expand on navigation to settings
  useEffect(() => {
    if (isSettingsActive) {
      setSettingsOpen(true);
    }
    if (isHermesActive) {
      setHermesOpen(true);
    }
  }, [isSettingsActive, isHermesActive]);

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm md:hidden" onClick={onClose} />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex flex-col bg-[#0c0c0f] border-r border-zinc-800/60",
          "transition-all duration-200 ease-out",
          "md:static md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
          "w-[min(85vw,17rem)]",
          collapsed ? "md:w-16" : "md:w-60"
        )}
      >
        {/* Brand */}
        <div className="flex h-12 items-center justify-between px-3 border-b border-zinc-800/60 shrink-0">
          <div className="flex items-center gap-2 overflow-hidden">
            <div className="h-7 w-7 rounded-lg bg-emerald-600/20 flex items-center justify-center shrink-0">
              <Zap className="h-4 w-4 text-emerald-400" />
            </div>
            {/* mobile drawer always shows brand; desktop hides when collapsed */}
            <span className={cn(
              "text-sm font-semibold tracking-tight text-zinc-100 whitespace-nowrap",
              collapsed && "md:hidden"
            )}>AutoCliper</span>
          </div>
          <button onClick={onClose} className="md:hidden rounded-md p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-2 py-3 space-y-1 overflow-y-auto scrollbar-thin">
          {mainNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              onClick={onClose}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium transition-colors",
                  collapsed && "md:justify-center md:px-0",
                  isActive ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-400 hover:bg-zinc-800/70 hover:text-zinc-200"
                )
              }
              title={collapsed ? item.label : undefined}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              <span className={cn(collapsed && "md:hidden")}>{item.label}</span>
            </NavLink>
          ))}

          {/* ─── Settings Accordion / Dropdown Tree ─── */}
          <div className="pt-1">
            {/* Settings Head */}
            <button
              type="button"
              onClick={() => {
                if (collapsed) {
                  onToggleCollapse();
                  setSettingsOpen(true);
                } else {
                  setSettingsOpen((prev) => !prev);
                }
              }}
              className={cn(
                "w-full flex items-center justify-between rounded-lg px-2.5 py-2 text-[13px] font-medium transition-colors select-none",
                collapsed && "md:justify-center md:px-0",
                isSettingsActive
                  ? "text-zinc-100 bg-zinc-850"
                  : "text-zinc-400 hover:bg-zinc-800/70 hover:text-zinc-200"
              )}
              title={collapsed ? "Settings" : undefined}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <Settings className={cn("h-4 w-4 shrink-0", isSettingsActive && "text-cyan-400")} />
                <span className={cn("truncate", collapsed && "md:hidden")}>Settings</span>
              </div>
              {!collapsed && (
                <ChevronDown
                  className={cn(
                    "h-3.5 w-3.5 shrink-0 text-zinc-500 transition-transform duration-200",
                    settingsOpen && "rotate-180"
                  )}
                />
              )}
            </button>

            {/* Settings Child Items (expanded tree) */}
            {settingsOpen && !collapsed && (
              <div className="mt-1 ml-2.5 pl-2.5 border-l border-zinc-800/80 space-y-0.5 animate-in fade-in-50 duration-150">
                {/* 1. General */}
                <NavLink
                  to="/settings/general"
                  onClick={onClose}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors",
                      isActive
                        ? "bg-cyan-500/15 text-cyan-300 font-semibold"
                        : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                    )
                  }
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <SlidersHorizontal className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">General</span>
                  </div>
                </NavLink>

                {/* 2. Hermes Sub-Group */}
                <div className="space-y-0.5 pt-0.5">
                  <button
                    type="button"
                    onClick={() => setHermesOpen((prev) => !prev)}
                    className={cn(
                      "w-full flex items-center justify-between gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors text-left",
                      isHermesActive
                        ? "text-zinc-200 font-semibold"
                        : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                    )}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Bot className={cn("h-3.5 w-3.5 shrink-0", isHermesActive ? "text-cyan-400" : "text-zinc-500")} />
                      <span className="truncate">Hermes</span>
                    </div>
                    <ChevronDown
                      className={cn(
                        "h-3 w-3 text-zinc-500 transition-transform duration-200 shrink-0",
                        hermesOpen && "rotate-180"
                      )}
                    />
                  </button>

                  {/* Hermes Sub-Items */}
                  {hermesOpen && (
                    <div className="ml-2 pl-2 border-l border-zinc-800/70 space-y-0.5 animate-in fade-in-50 duration-150">
                      <NavLink
                        to="/settings/hermes/autopilot"
                        onClick={onClose}
                        className={({ isActive }) =>
                          cn(
                            "flex items-center justify-between gap-1.5 rounded-lg px-2 py-1 text-[11px] font-medium transition-colors",
                            isActive
                              ? "bg-cyan-500/15 text-cyan-300 font-semibold"
                              : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                          )
                        }
                      >
                        <div className="flex items-center gap-1.5 min-w-0">
                          <Bot className="h-3 w-3 shrink-0" />
                          <span className="truncate">Autopilot Clipper</span>
                        </div>
                        <span className="text-[9px] px-1 py-0.2 rounded bg-zinc-800/80 text-zinc-400 border border-zinc-700/50 shrink-0">
                          1 Video
                        </span>
                      </NavLink>

                      <NavLink
                        to="/settings/hermes/videogen"
                        onClick={onClose}
                        className={({ isActive }) =>
                          cn(
                            "flex items-center justify-between gap-1.5 rounded-lg px-2 py-1 text-[11px] font-medium transition-colors",
                            isActive
                              ? "bg-cyan-500/15 text-cyan-300 font-semibold"
                              : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                          )
                        }
                      >
                        <div className="flex items-center gap-1.5 min-w-0">
                          <Video className="h-3 w-3 shrink-0" />
                          <span className="truncate">Video Gen Auto-Post</span>
                        </div>
                        <span className="text-[9px] px-1 py-0.2 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 shrink-0">
                          3-5 Video
                        </span>
                      </NavLink>
                    </div>
                  )}
                </div>

                {/* 3. Render Engine */}
                <NavLink
                  to="/settings/render"
                  onClick={onClose}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors",
                      isActive
                        ? "bg-cyan-500/15 text-cyan-300 font-semibold"
                        : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                    )
                  }
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Film className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">Render Engine</span>
                  </div>
                </NavLink>

                {/* 4. Reframe Tuning */}
                <NavLink
                  to="/settings/reframe"
                  onClick={onClose}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors",
                      isActive
                        ? "bg-cyan-500/15 text-cyan-300 font-semibold"
                        : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                    )
                  }
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Cpu className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">Reframe Tuning</span>
                  </div>
                </NavLink>

                {/* 5. HyperFrames Hook */}
                <NavLink
                  to="/settings/hyperframes"
                  onClick={onClose}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors",
                      isActive
                        ? "bg-cyan-500/15 text-cyan-300 font-semibold"
                        : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                    )
                  }
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Sparkles className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">HyperFrames Hook</span>
                  </div>
                </NavLink>

                {/* 6. Object Overlay */}
                <NavLink
                  to="/settings/object"
                  onClick={onClose}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors",
                      isActive
                        ? "bg-cyan-500/15 text-cyan-300 font-semibold"
                        : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                    )
                  }
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Palette className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">Object Overlay</span>
                  </div>
                </NavLink>

                {/* 7. Telegram Bot */}
                <NavLink
                  to="/settings/telegram"
                  onClick={onClose}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors",
                      isActive
                        ? "bg-cyan-500/15 text-cyan-300 font-semibold"
                        : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                    )
                  }
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Send className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">Telegram Bot</span>
                  </div>
                </NavLink>

                {/* Superadmin Section */}
                {isSuperadmin && (
                  <div className="pt-2 border-t border-zinc-800/70 mt-1.5 space-y-0.5">
                    <p className="px-2 py-0.5 text-[9px] font-bold text-zinc-400 uppercase tracking-wider">
                      Administration
                    </p>

                    <NavLink
                      to="/settings/system"
                      onClick={onClose}
                      className={({ isActive }) =>
                        cn(
                          "flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors",
                          isActive
                            ? "bg-cyan-500/15 text-cyan-300 font-semibold"
                            : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                        )
                      }
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <HardDrive className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">Database &amp; Env</span>
                      </div>
                    </NavLink>

                    <NavLink
                      to="/settings/models"
                      onClick={onClose}
                      className={({ isActive }) =>
                        cn(
                          "flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors",
                          isActive
                            ? "bg-cyan-500/15 text-cyan-300 font-semibold"
                            : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                        )
                      }
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <BrainCircuit className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">AI Models</span>
                      </div>
                    </NavLink>

                    <NavLink
                      to="/settings/users"
                      onClick={onClose}
                      className={({ isActive }) =>
                        cn(
                          "flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors",
                          isActive
                            ? "bg-cyan-500/15 text-cyan-300 font-semibold"
                            : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                        )
                      }
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <ShieldCheck className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">Access Control</span>
                      </div>
                    </NavLink>

                    <NavLink
                      to="/settings/testing"
                      onClick={onClose}
                      className={({ isActive }) =>
                        cn(
                          "flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors",
                          isActive
                            ? "bg-cyan-500/15 text-cyan-300 font-semibold"
                            : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                        )
                      }
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <Terminal className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">Test &amp; Deploy</span>
                      </div>
                    </NavLink>
                  </div>
                )}
              </div>
            )}
          </div>
        </nav>

        {/* Collapse toggle (desktop only) */}
        <div className="hidden md:flex border-t border-zinc-800/60 px-2 py-2 shrink-0">
          <button
            onClick={onToggleCollapse}
            className="w-full flex items-center justify-center gap-2 rounded-lg px-2 py-1.5 text-zinc-500 hover:bg-zinc-800/70 hover:text-zinc-300 transition-colors"
            title={collapsed ? "Expand" : "Collapse"}
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
            {!collapsed && <span className="text-[11px]">Collapse</span>}
          </button>
        </div>
      </aside>
    </>
  );
}

