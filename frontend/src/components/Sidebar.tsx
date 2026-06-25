import { NavLink } from "react-router-dom";
import { LayoutDashboard, PlusCircle, Settings, Zap, X, ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/jobs/new", icon: PlusCircle, label: "New Job" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

interface SidebarProps {
  open: boolean;
  onClose: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export function Sidebar({ open, onClose, collapsed, onToggleCollapse }: SidebarProps) {
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
          collapsed ? "w-16" : "w-52"
        )}
      >
        {/* Brand */}
        <div className="flex h-12 items-center justify-between px-3 border-b border-zinc-800/60">
          <div className="flex items-center gap-2 overflow-hidden">
            <div className="h-7 w-7 rounded-lg bg-emerald-600/20 flex items-center justify-center shrink-0">
              <Zap className="h-4 w-4 text-emerald-400" />
            </div>
            {!collapsed && <span className="text-sm font-semibold tracking-tight text-zinc-100 whitespace-nowrap">AutoCliper</span>}
          </div>
          <button onClick={onClose} className="md:hidden rounded-md p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-2 py-3 space-y-0.5">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              onClick={onClose}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium transition-colors",
                  collapsed && "justify-center px-0",
                  isActive ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-400 hover:bg-zinc-800/70 hover:text-zinc-200"
                )
              }
              title={collapsed ? item.label : undefined}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {!collapsed && item.label}
            </NavLink>
          ))}
        </nav>

        {/* Collapse toggle (desktop only) */}
        <div className="hidden md:flex border-t border-zinc-800/60 px-2 py-2">
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
