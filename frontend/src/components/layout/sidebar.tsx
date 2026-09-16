/** Collapsible sidebar navigation for Manga Translate. */
import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchJobs } from "@/api/client";
import { useUIStore } from "@/stores/ui-store";
import {
  LayoutDashboard,
  BookOpen,
  PlusCircle,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Activity,
  Layers,
} from "lucide-react";

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar, openJobModal } = useUIStore();

  const { data } = useQuery({
    queryKey: ["jobs"],
    queryFn: fetchJobs,
    refetchInterval: 3000,
  });

  const activeJobsCount = (data?.jobs ?? []).filter(
    (j) => j.status !== "done" && j.status !== "error"
  ).length;

  return (
    <aside
      className={`fixed top-0 left-0 bottom-0 z-40 flex flex-col bg-card/85 backdrop-blur-2xl border-r border-border/80 transition-all duration-300 ease-in-out ${
        sidebarCollapsed ? "w-20" : "w-64"
      }`}
    >
      {/* Brand Header */}
      <div className="h-18 flex items-center px-4.5 border-b border-border/60 justify-between gap-3">
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="relative w-10 h-10 rounded-xl bg-gradient-to-tr from-violet-600 via-primary to-cyan-400 p-0.5 shrink-0 shadow-lg shadow-primary/25">
            <div className="w-full h-full bg-background/90 rounded-[10px] flex items-center justify-center font-black text-xl text-primary">
              <Sparkles className="w-5 h-5 text-violet-400 animate-pulse" />
            </div>
            {activeJobsCount > 0 && (
              <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-emerald-500 border-2 border-background"></span>
              </span>
            )}
          </div>

          {!sidebarCollapsed && (
            <div className="min-w-0 transition-opacity duration-200">
              <h1 className="text-base font-bold tracking-tight text-gradient">
                Manga Studio
              </h1>
              <p className="text-[11px] text-muted-foreground truncate font-medium">
                Google Lens AI Translate
              </p>
            </div>
          )}
        </div>

        <button
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
        >
          {sidebarCollapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <ChevronLeft className="w-4 h-4" />
          )}
        </button>
      </div>

      {/* Quick Action Button */}
      <div className="p-3">
        <button
          onClick={() => openJobModal()}
          className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-xl font-semibold text-sm text-white bg-gradient-to-r from-violet-600 via-primary to-indigo-600 hover:brightness-110 active:scale-[0.98] shadow-lg shadow-primary/25 transition-all group ${
            sidebarCollapsed ? "px-0" : "px-4"
          }`}
          title="เพิ่มงานแปลใหม่ (Ctrl+K)"
        >
          <PlusCircle className="w-4 h-4 group-hover:rotate-90 transition-transform duration-200 shrink-0" />
          {!sidebarCollapsed && (
            <span className="truncate">
              เพิ่มงานใหม่ <span className="text-xs opacity-70 ml-1 font-mono">⌘K</span>
            </span>
          )}
        </button>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-3 py-2 space-y-1.5 overflow-y-auto">
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all ${
              isActive
                ? "bg-primary/15 text-violet-300 border border-primary/30 shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary/60"
            } ${sidebarCollapsed ? "justify-center px-0" : ""}`
          }
          title="แดชบอร์ด"
        >
          <LayoutDashboard className="w-4.5 h-4.5 shrink-0" />
          {!sidebarCollapsed && <span>แดชบอร์ด</span>}
        </NavLink>

        <NavLink
          to="/library"
          className={({ isActive }) =>
            `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all ${
              isActive
                ? "bg-primary/15 text-violet-300 border border-primary/30 shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary/60"
            } ${sidebarCollapsed ? "justify-center px-0" : ""}`
          }
          title="คลังมังงะ"
        >
          <BookOpen className="w-4.5 h-4.5 shrink-0" />
          {!sidebarCollapsed && (
            <div className="flex-1 flex items-center justify-between">
              <span>คลังมังงะ</span>
              <span className="text-[11px] px-1.5 py-0.5 rounded-md bg-secondary text-muted-foreground">
                Series
              </span>
            </div>
          )}
        </NavLink>
      </nav>

      {/* Active Jobs Mini Pill (Sidebar Bottom) */}
      <div className="p-3 border-t border-border/60">
        <div
          className={`rounded-xl bg-secondary/50 border border-border/50 p-2.5 flex items-center gap-2.5 ${
            sidebarCollapsed ? "justify-center p-2" : ""
          }`}
        >
          <div className="relative">
            <Activity className={`w-4 h-4 ${activeJobsCount > 0 ? "text-emerald-400 animate-spin" : "text-muted-foreground"}`} />
          </div>
          {!sidebarCollapsed && (
            <div className="min-w-0 flex-1">
              <div className="text-xs font-medium text-foreground flex items-center justify-between">
                <span>คิวงานเบื้องหลัง</span>
                <span
                  className={`text-[10px] font-bold px-1.5 py-0.2 rounded-full ${
                    activeJobsCount > 0
                      ? "bg-emerald-500/20 text-emerald-400"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  {activeJobsCount} งาน
                </span>
              </div>
              <div className="text-[10px] text-muted-foreground truncate mt-0.5">
                {activeJobsCount > 0 ? "กำลังแปล / ดาวน์โหลด" : "พร้อมรับงานใหม่"}
              </div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
