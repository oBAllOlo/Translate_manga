/** Modern App Layout with Collapsible Sidebar, Header, Job Modal & Floating Task Dock. */
import { useWebSocket } from "@/hooks/use-websocket";
import { useUIStore } from "@/stores/ui-store";
import { Sidebar } from "@/components/layout/sidebar";
import { TopHeader } from "@/components/layout/top-header";
import { JobModal } from "@/components/jobs/job-modal";
import { FloatingJobDock } from "@/components/jobs/floating-job-dock";

export function AppLayout({ children }: { children: React.ReactNode }) {
  useWebSocket();
  const { sidebarCollapsed } = useUIStore();

  return (
    <div className="min-h-screen bg-background text-foreground flex">
      {/* Collapsible Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <div
        className={`flex-1 flex flex-col min-w-0 transition-all duration-300 ease-in-out ${
          sidebarCollapsed ? "pl-20" : "pl-64"
        }`}
      >
        <TopHeader />

        <main className="flex-1 p-6 md:p-8 max-w-[1600px] w-full mx-auto">
          {children}
        </main>
      </div>

      {/* Global Modals & Persistent Dock */}
      <JobModal />
      <FloatingJobDock />
    </div>
  );
}
