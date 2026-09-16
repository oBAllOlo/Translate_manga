/** Responsive top header with search trigger and system status. */
import { useLocation } from "react-router-dom";
import { useUIStore } from "@/stores/ui-store";
import { Search, Sparkles, Menu, Cpu } from "lucide-react";

export function TopHeader() {
  const location = useLocation();
  const { openJobModal, toggleSidebar } = useUIStore();

  const getPageTitle = () => {
    if (location.pathname === "/") return "แดชบอร์ดภาพรวม";
    if (location.pathname.startsWith("/library")) return "คลังมังงะ (Series Catalog)";
    return "Manga Studio";
  };

  return (
    <header className="h-18 px-6 flex items-center justify-between border-b border-border/60 bg-background/60 backdrop-blur-xl sticky top-0 z-30">
      <div className="flex items-center gap-3">
        <button
          onClick={toggleSidebar}
          aria-label="Toggle sidebar"
          className="p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-secondary md:hidden transition-colors"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div>
          <h2 className="text-lg font-bold tracking-tight text-foreground">
            {getPageTitle()}
          </h2>
          <p className="text-xs text-muted-foreground hidden sm:block">
            Manga Translation Automation Engine · Google Lens Core
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* Quick Search / Paste Trigger */}
        <button
          onClick={() => openJobModal()}
          className="hidden sm:flex items-center gap-2.5 px-3.5 py-1.5 rounded-xl bg-secondary/70 hover:bg-secondary text-muted-foreground hover:text-foreground border border-border text-xs transition-all cursor-pointer group shadow-sm"
        >
          <Search className="w-3.5 h-3.5 text-muted-foreground group-hover:text-primary transition-colors" />
          <span>วาง URL มังงะเพื่อเริ่มแปล...</span>
          <kbd className="px-1.5 py-0.5 text-[10px] font-mono bg-background/80 rounded border border-border/80 text-muted-foreground">
            Ctrl+K
          </kbd>
        </button>

        {/* System Status Pill */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/25 text-emerald-400 text-xs font-medium">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <Cpu className="w-3.5 h-3.5 opacity-80 hidden md:inline" />
          <span className="hidden sm:inline font-mono text-[11px]">Lens CDP Ready</span>
        </div>
      </div>
    </header>
  );
}
