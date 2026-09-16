/** Floating task dock — persistent real-time monitoring widget in bottom-right corner. */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { fetchJobs, type Job } from "@/api/client";
import {
  Activity,
  ChevronDown,
  ChevronUp,
  Download,
  Languages,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  BookOpen,
  FileDown,
  ExternalLink,
} from "lucide-react";

function calcProgress(j: Job): number {
  if (j.status === "done" || j.status === "error") return 100;
  if (j.status === "translating") {
    const total = j.total_pages || 1;
    const tr = j.translated || 0;
    return 60 + Math.min(39, Math.round((tr / total) * 40));
  }
  if (j.status === "downloading") {
    const total = j.total_pages || 1;
    const dl = j.downloaded || 0;
    return 10 + Math.min(49, Math.round((dl / total) * 50));
  }
  if (j.status === "parsing") return 8;
  return 0;
}

const STATUS_TEXT: Record<string, string> = {
  queued: "รอคิว",
  parsing: "อ่านข้อมูล URL",
  downloading: "ดาวน์โหลดภาพ",
  translating: "แปลไทยด้วย Google Lens",
  done: "เสร็จสมบูรณ์",
  error: "เกิดข้อผิดพลาด",
};

export function FloatingJobDock() {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);

  const { data } = useQuery({
    queryKey: ["jobs"],
    queryFn: fetchJobs,
    refetchInterval: 2500,
  });

  const jobs = data?.jobs ?? [];
  const activeJobs = jobs.filter(
    (j) => j.status !== "done" && j.status !== "error"
  );

  // If there are no jobs at all, hide the dock
  if (jobs.length === 0) return null;

  const currentActive = activeJobs[0];

  return (
    <div className="fixed bottom-5 right-5 z-40 max-w-md w-full sm:w-[380px] select-none transition-all">
      {/* Expanded Task Panel */}
      {expanded && (
        <div className="mb-2.5 rounded-2xl bg-card/95 backdrop-blur-2xl border border-border/80 shadow-2xl p-4 space-y-3 glass-panel animate-in slide-in-from-bottom-3 duration-200">
          <div className="flex items-center justify-between border-b border-border/60 pb-2.5">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-primary animate-pulse" />
              <h4 className="text-xs font-bold text-foreground">
                ความคืบหน้างานแปล ({activeJobs.length} กำลังทำงาน)
              </h4>
            </div>
            <button
              onClick={() => setExpanded(false)}
              className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary"
            >
              <ChevronDown className="w-4 h-4" />
            </button>
          </div>

          <div className="max-h-64 overflow-y-auto space-y-2.5 pr-1">
            {jobs.slice(0, 5).map((job) => {
              const progress = calcProgress(job);
              const isRunning =
                job.status !== "done" && job.status !== "error";

              return (
                <div
                  key={job.id}
                  className="p-2.5 rounded-xl bg-secondary/50 border border-border/50 text-xs space-y-1.5"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold text-foreground truncate">
                        {job.title || job.url}
                      </div>
                      <div className="text-[11px] text-muted-foreground flex items-center gap-1.5 mt-0.5">
                        {job.status === "translating" && (
                          <span className="inline-flex items-center gap-1 text-violet-400">
                            <Languages className="w-3 h-3 animate-spin" />
                            แปลไทย {job.translated || 0}/{job.total_pages || "?"} หน้า
                          </span>
                        )}
                        {job.status === "downloading" && (
                          <span className="inline-flex items-center gap-1 text-cyan-400">
                            <Download className="w-3 h-3 animate-bounce" />
                            ดาวน์โหลด {job.downloaded || 0}/{job.total_pages || "?"} หน้า
                          </span>
                        )}
                        {job.status === "parsing" && (
                          <span className="inline-flex items-center gap-1 text-amber-400">
                            <Loader2 className="w-3 h-3 animate-spin" />
                            กำลังอ่านข้อมูล
                          </span>
                        )}
                        {job.status === "done" && (
                          <span className="inline-flex items-center gap-1 text-emerald-400">
                            <CheckCircle2 className="w-3 h-3" />
                            แปลเสร็จแล้ว ({job.translated || job.total_pages || 0} หน้า)
                          </span>
                        )}
                        {job.status === "error" && (
                          <span className="inline-flex items-center gap-1 text-red-400">
                            <XCircle className="w-3 h-3" />
                            {job.message || "เกิดข้อผิดพลาด"}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Action button */}
                    {job.status === "done" && (
                      <button
                        onClick={() => {
                          const slug = job.slug || job.url.split("/").filter(Boolean).pop();
                          if (slug) navigate(`/reader/${encodeURIComponent(slug)}`);
                        }}
                        className="px-2 py-1 rounded-lg bg-primary/20 text-violet-300 hover:bg-primary hover:text-white transition-all text-[11px] font-semibold flex items-center gap-1 shrink-0"
                      >
                        <BookOpen className="w-3 h-3" />
                        อ่าน
                      </button>
                    )}
                  </div>

                  {/* Progress bar */}
                  {isRunning && (
                    <div className="w-full bg-secondary rounded-full h-1.5 overflow-hidden">
                      <div
                        className="bg-gradient-to-r from-violet-500 to-cyan-400 h-1.5 rounded-full transition-all duration-300"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Floating Pill Trigger */}
      <div
        onClick={() => setExpanded(!expanded)}
        className={`flex items-center justify-between p-3 rounded-2xl bg-card/90 backdrop-blur-xl border border-border/80 shadow-2xl cursor-pointer hover:border-primary/50 transition-all ${
          activeJobs.length > 0 ? "border-primary/40 glow-primary" : ""
        }`}
      >
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 ${
              activeJobs.length > 0
                ? "bg-primary text-white"
                : "bg-secondary text-muted-foreground"
            }`}
          >
            {activeJobs.length > 0 ? (
              <Languages className="w-4 h-4 animate-pulse" />
            ) : (
              <Activity className="w-4 h-4" />
            )}
          </div>
          <div className="min-w-0">
            <div className="text-xs font-bold text-foreground flex items-center gap-2 truncate">
              <span>
                {activeJobs.length > 0
                  ? `กำลังแปล ${activeJobs.length} ตอน`
                  : "งานแปลทั้งหมดพร้อมแล้ว"}
              </span>
              {activeJobs.length > 0 && currentActive && (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded-full bg-primary/20 text-violet-300">
                  {calcProgress(currentActive)}%
                </span>
              )}
            </div>
            <div className="text-[11px] text-muted-foreground truncate">
              {currentActive
                ? `${STATUS_TEXT[currentActive.status] || currentActive.status}: ${
                    currentActive.title || currentActive.url
                  }`
                : "คลิกเพื่อดูประวัติงานล่าสุด"}
            </div>
          </div>
        </div>

        <div className="p-1 text-muted-foreground hover:text-foreground">
          {expanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronUp className="w-4 h-4" />
          )}
        </div>
      </div>
    </div>
  );
}
