/** Dashboard — Cyber-Manga Command Center with stats, continue reading, and live pipeline. */
import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  fetchJobs,
  fetchChapters,
  createJob,
  deleteAllJobs,
  deleteJob,
  cancelJob,
  cancelAllJobs,
  resolvePdfUrl,
  type Job,
} from "@/api/client";
import { useUIStore } from "@/stores/ui-store";
import { ConfirmModal } from "@/components/common/confirm-modal";
import {
  Sparkles,
  Layers,
  BookOpen,
  Languages,
  Activity,
  CheckCircle2,
  XCircle,
  Download,
  Loader2,
  FileDown,
  ArrowRight,
  PlusCircle,
  Trash2,
  X,
  Ban,
} from "lucide-react";

function calcProgress(j: Job): number {
  if (j.status === "done" || j.status === "error") return 100;
  if (j.status === "refining") {
    const total = j.total_pages || 1;
    const ref = j.translated || 0;
    return Math.max(5, Math.min(99, Math.round((ref / total) * 100)));
  }
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

function resolveThumbUrl(slug: string, thumb?: string): string {
  if (!thumb) return `/output/${encodeURI(slug)}/translated_images/page-001.png`;
  if (thumb.startsWith("http") || thumb.startsWith("/")) return thumb;
  const normalized = thumb.replace(/\\/g, "/");
  const match = normalized.match(/output\/(.+)$/);
  if (match) {
    return `/output/${match[1]}`;
  }
  if (normalized.startsWith("images/") || normalized.startsWith("translated_images/")) {
    return `/output/${encodeURI(slug)}/${normalized}`;
  }
  return `/output/${encodeURI(slug)}/translated_images/${normalized}`;
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { openJobModal, continueReading, clearContinueReading, showToast } = useUIStore();
  const [quickUrl, setQuickUrl] = useState("");
  const [quickChunk, setQuickChunk] = useState(8);
  const [quickConcurrency, setQuickConcurrency] = useState(8);
  const [quickLoading, setQuickLoading] = useState(false);
  const [jobFilter, setJobFilter] = useState<"all" | "active" | "done" | "error">("all");
  const [isClearModalOpen, setIsClearModalOpen] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [clearMode, setClearMode] = useState<"completed" | "all">("completed");
  const [cancellingJobId, setCancellingJobId] = useState<string | null>(null);
  const [isCancellingAll, setIsCancellingAll] = useState(false);

  const { data: jobsData } = useQuery({
    queryKey: ["jobs"],
    queryFn: fetchJobs,
    refetchInterval: 3000,
  });

  const { data: chaptersData, isLoading: chaptersLoading } = useQuery({
    queryKey: ["chapters"],
    queryFn: fetchChapters,
  });

  const jobs = jobsData?.jobs ?? [];
  const chapters = chaptersData?.chapters ?? [];
  const series = chaptersData?.series ?? [];

  // Check if continueReading target chapter actually still exists in library
  const continueReadingValid = Boolean(
    continueReading &&
      continueReading.chapterSlug &&
      chapters.length > 0 &&
      chapters.some(
        (c) =>
          c.name.toLowerCase() === continueReading.chapterSlug.toLowerCase() ||
          (continueReading.chapterTitle && c.title === continueReading.chapterTitle)
      )
  );

  // If chapters finished loading and library is empty or chapter was deleted, auto-clear continueReading
  useEffect(() => {
    if (!chaptersLoading && continueReading && !continueReadingValid) {
      clearContinueReading();
    }
  }, [chaptersLoading, continueReading, continueReadingValid, clearContinueReading]);

  // Metrics
  const totalSeries = series.length;
  const totalChapters = chapters.length;
  const totalTranslatedPages = chapters.reduce(
    (acc, c) => acc + (c.translated_count || 0),
    0
  );
  const activeJobs = jobs.filter(
    (j) => j.status !== "done" && j.status !== "error"
  );

  const handleQuickSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickUrl.trim()) return;
    setQuickLoading(true);
    try {
      await createJob(quickUrl.trim(), quickChunk, quickConcurrency);
      setQuickUrl("");
    } catch (err: any) {
      alert("Error: " + err.message);
    } finally {
      setQuickLoading(false);
    }
  };

  const handleCancelSingleJob = async (jobId: string) => {
    setCancellingJobId(jobId);
    try {
      await cancelJob(jobId);
      showToast("ยกเลิกงานเรียบร้อยแล้ว", "success");
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
    } catch (err: any) {
      showToast("เกิดข้อผิดพลาดในการยกเลิก: " + err.message, "error");
    } finally {
      setCancellingJobId(null);
    }
  };

  const handleCancelAllJobs = async () => {
    setIsCancellingAll(true);
    try {
      const res = await cancelAllJobs();
      showToast(`ยกเลิกงานที่กำลังรันทั้งหมดเรียบร้อยแล้ว (${res.cancelled_count || 0} งาน)`, "success");
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
    } catch (err: any) {
      showToast("เกิดข้อผิดพลาดในการยกเลิกงาน: " + err.message, "error");
    } finally {
      setIsCancellingAll(false);
    }
  };

  const handleClearHistory = async () => {
    setIsClearing(true);
    try {
      await deleteAllJobs(clearMode === "all");
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      showToast(clearMode === "all" ? "ยกเลิกและล้างคิวงานทั้งหมดแล้ว" : "ล้างประวัติงานที่เสร็จสิ้นแล้ว", "success");
      setIsClearModalOpen(false);
    } catch (err: any) {
      showToast("เกิดข้อผิดพลาด: " + err.message, "error");
    } finally {
      setIsClearing(false);
    }
  };

  const handleDeleteSingleJob = async (jobId: string) => {
    try {
      await deleteJob(jobId);
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      showToast("ลบงานออกจากรายการแล้ว", "success");
    } catch (err) {
      console.error("Failed to delete job", err);
    }
  };

  const filteredJobs = jobs.filter((j) => {
    if (jobFilter === "active") return j.status !== "done" && j.status !== "error";
    if (jobFilter === "done") return j.status === "done";
    if (jobFilter === "error") return j.status === "error";
    return true;
  });

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* 1. Metrics Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-2xl bg-card border border-border/70 glass-panel-interactive">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              มังงะในคลัง
            </span>
            <div className="w-8 h-8 rounded-xl bg-violet-500/15 text-violet-400 flex items-center justify-center">
              <BookOpen className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-black text-foreground">{totalSeries}</span>
            <span className="text-xs text-muted-foreground">เรื่อง</span>
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-card border border-border/70 glass-panel-interactive">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              ตอนทั้งหมด
            </span>
            <div className="w-8 h-8 rounded-xl bg-primary/15 text-primary flex items-center justify-center">
              <Layers className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-black text-foreground">{totalChapters}</span>
            <span className="text-xs text-muted-foreground">ตอน</span>
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-card border border-border/70 glass-panel-interactive">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              หน้าที่แปลแล้ว (Lens)
            </span>
            <div className="w-8 h-8 rounded-xl bg-emerald-500/15 text-emerald-400 flex items-center justify-center">
              <Languages className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-black text-emerald-400">
              {totalTranslatedPages.toLocaleString()}
            </span>
            <span className="text-xs text-muted-foreground">หน้า</span>
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-card border border-border/70 glass-panel-interactive">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              งานที่กำลังรัน
            </span>
            <div className="w-8 h-8 rounded-xl bg-cyan-500/15 text-cyan-400 flex items-center justify-center">
              <Activity className={`w-4 h-4 ${activeJobs.length > 0 ? "animate-spin" : ""}`} />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-black text-cyan-400">{activeJobs.length}</span>
            <span className="text-xs text-muted-foreground">งาน</span>
          </div>
        </div>
      </div>

      {/* 2. Continue Reading Banner (if user has read recently and chapter still exists) */}
      {continueReadingValid && continueReading && (
        <div className="p-6 rounded-2xl bg-gradient-to-r from-violet-950/40 via-card to-card border border-primary/30 shadow-xl flex items-center justify-between gap-6 flex-wrap glass-panel animate-in fade-in duration-200">
          <div className="flex items-center gap-4 min-w-0">
            {continueReading.thumb ? (
              <img
                src={resolveThumbUrl(continueReading.chapterSlug, continueReading.thumb)}
                alt=""
                onError={(e) => {
                  const target = e.currentTarget;
                  if (!target.dataset.fallback) {
                    target.dataset.fallback = "1";
                    target.src = `/output/${encodeURI(continueReading.chapterSlug)}/images/page-001.png`;
                  } else {
                    target.style.display = "none";
                  }
                }}
                className="w-14 h-20 object-cover rounded-xl border border-border shadow-md shrink-0"
              />
            ) : (
              <div className="w-14 h-20 rounded-xl bg-secondary flex items-center justify-center text-xl shrink-0">
                📖
              </div>
            )}
            <div className="min-w-0">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-primary/20 text-violet-300 mb-1">
                <BookOpen className="w-3 h-3" />
                อ่านต่อจากครั้งล่าสุด
              </div>
              <h3 className="text-base font-bold text-foreground truncate">
                {continueReading.chapterTitle}
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                กำลังอ่านอยู่ที่หน้า {continueReading.page}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => navigate(`/reader/${encodeURIComponent(continueReading.chapterSlug)}`)}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-white font-semibold text-xs shadow-lg shadow-primary/30 hover:brightness-110 active:scale-95 transition-all cursor-pointer"
            >
              <span>อ่านต่อเลย</span>
              <ArrowRight className="w-4 h-4" />
            </button>

            <button
              id="btn-dismiss-continue-reading"
              onClick={clearContinueReading}
              className="p-2.5 rounded-xl text-muted-foreground hover:text-foreground hover:bg-secondary/80 border border-border/60 transition-all cursor-pointer"
              title="ปิดการแจ้งเตือนนี้"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* 3. Quick Start Translate Box */}
      <div className="p-6 rounded-2xl bg-card/80 border border-border/80 shadow-xl glass-panel space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-primary/15 text-primary flex items-center justify-center">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-foreground">
                แปลมังงะแบบด่วน (Quick Submit)
              </h3>
              <p className="text-xs text-muted-foreground">
                วางลิงก์ตอนมังงะเพื่อเริ่มดาวน์โหลด แปล Lens และแปลงเป็น PDF ทันที
              </p>
            </div>
          </div>

          <button
            onClick={() => openJobModal()}
            className="text-xs text-primary hover:underline flex items-center gap-1 font-medium"
          >
            <PlusCircle className="w-3.5 h-3.5" />
            เปิดตัวช่วยแปลแบบหลายตอน (Range)
          </button>
        </div>

        <form onSubmit={handleQuickSubmit} className="flex gap-2.5 flex-wrap">
          <input
            type="text"
            value={quickUrl}
            onChange={(e) => setQuickUrl(e.target.value)}
            placeholder="วาง URL ตอนมังงะ (MangaDex, WeebCentral, MangaBlaze)..."
            className="flex-1 min-w-[280px] px-4 py-2.5 bg-secondary/70 rounded-xl border border-border text-foreground text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 font-mono transition-all"
            required
          />

          <div className="flex items-center gap-1 bg-secondary/80 rounded-xl p-1 border border-border text-xs">
            <span className="px-2 text-muted-foreground font-mono">PDF:</span>
            {[0, 8, 16].map((sz) => (
              <button
                key={sz}
                type="button"
                onClick={() => setQuickChunk(sz)}
                className={`px-2.5 py-1 rounded-lg transition-all ${
                  quickChunk === sz
                    ? "bg-primary text-white font-semibold shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {sz === 0 ? "ไม่ทำ" : `${sz} หน้า`}
              </button>
            ))}
          </div>

          {/* Lens Concurrency selector */}
          <div className="flex items-center gap-1 bg-secondary/80 rounded-xl p-1 border border-border text-xs">
            <span className="px-2 text-muted-foreground font-mono">Lens:</span>
            {[2, 4, 8, 12].map((c) => (
              <button
                key={c}
                type="button"
                id={`btn-concurrency-${c}`}
                onClick={() => setQuickConcurrency(c)}
                className={`px-2.5 py-1 rounded-lg transition-all ${
                  quickConcurrency === c
                    ? "bg-emerald-600 text-white font-semibold shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
                title={`ใช้ ${c} thread แปลพร้อมกัน`}
              >
                {c}×
              </button>
            ))}
          </div>

          <button
            type="submit"
            disabled={quickLoading}
            className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 via-primary to-indigo-600 text-white text-xs font-semibold shadow-lg shadow-primary/25 hover:brightness-110 active:scale-95 disabled:opacity-50 transition-all cursor-pointer"
          >
            {quickLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Sparkles className="w-4 h-4" />
            )}
            เริ่มแปลเลย →
          </button>
        </form>
      </div>

      {/* 4. Live Activity Pipeline */}
      <div className="space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" />
            <h3 className="text-base font-bold text-foreground">
              กิจกรรมและคิวงานล่าสุด (Live Jobs Pipeline)
            </h3>
          </div>

          {/* Actions & Filter Pills */}
          <div className="flex items-center gap-2 flex-wrap">
            {activeJobs.length > 0 && (
              <button
                id="btn-cancel-all-jobs"
                onClick={handleCancelAllJobs}
                disabled={isCancellingAll}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-500/15 text-rose-300 hover:bg-rose-500 hover:text-white border border-rose-500/30 hover:border-rose-500 text-xs font-semibold shadow-sm active:scale-95 transition-all cursor-pointer disabled:opacity-50"
                title="ยกเลิกงานทั้งหมดที่กำลังทำงานอยู่"
              >
                {isCancellingAll ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Ban className="w-3.5 h-3.5 text-rose-400" />
                )}
                <span>ยกเลิกงานทั้งหมด ({activeJobs.length})</span>
              </button>
            )}

            {jobs.length > 0 && (
              <button
                id="btn-clear-jobs-history"
                onClick={() => {
                  setClearMode(activeJobs.length > 0 ? "all" : "completed");
                  setIsClearModalOpen(true);
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-muted-foreground hover:text-destructive hover:bg-destructive/10 border border-border/80 hover:border-destructive/30 text-xs font-semibold transition-all cursor-pointer"
                title="ล้างรายการงานในคิว"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>ล้างรายการงาน</span>
              </button>
            )}

            <div className="flex items-center gap-1 bg-secondary/80 rounded-xl p-1 border border-border text-xs">
              {[
                { id: "all", label: `ทั้งหมด (${jobs.length})` },
                { id: "active", label: `กำลังทำงาน (${activeJobs.length})` },
                { id: "done", label: "เสร็จแล้ว" },
                { id: "error", label: "ข้อผิดพลาด" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setJobFilter(tab.id as any)}
                  className={`px-3 py-1 rounded-lg font-medium transition-all ${
                    jobFilter === tab.id
                      ? "bg-primary text-white shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Jobs List */}
        {filteredJobs.length === 0 ? (
          <div className="text-center py-12 rounded-2xl bg-card/50 border border-border/50 text-muted-foreground text-xs">
            ไม่มีงานในสถานะนี้
          </div>
        ) : (
          <div className="grid gap-3">
            {filteredJobs.map((job) => {
              const progress = calcProgress(job);
              const isRunning = job.status !== "done" && job.status !== "error";

              return (
                <div
                  key={job.id}
                  className="p-4 rounded-2xl bg-card/80 border border-border/80 hover:border-primary/40 shadow-sm glass-panel transition-all space-y-3"
                >
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-bold text-foreground">
                          {job.title || job.url}
                        </span>
                        {job.is_range && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-violet-500/20 text-violet-300 border border-violet-500/30">
                            Range Job
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground font-mono truncate mt-0.5">
                        {job.url}
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      {job.status === "done" && (
                        <button
                          onClick={() => {
                            const slug = job.slug || job.url.split("/").filter(Boolean).pop();
                            if (slug) navigate(`/reader/${encodeURIComponent(slug)}`);
                          }}
                          className="px-3 py-1.5 rounded-xl bg-primary/20 text-violet-300 hover:bg-primary hover:text-white text-xs font-semibold flex items-center gap-1 transition-all cursor-pointer"
                        >
                          <BookOpen className="w-3.5 h-3.5" />
                          เปิดอ่าน
                        </button>
                      )}

                      {job.pdf && (
                        <a
                          href={resolvePdfUrl(job.pdf)}
                          target="_blank"
                          rel="noreferrer"
                          className="px-3 py-1.5 rounded-xl bg-secondary hover:bg-card border border-border text-xs font-semibold flex items-center gap-1 transition-all"
                        >
                          <FileDown className="w-3.5 h-3.5 text-cyan-400" />
                          PDF
                        </a>
                      )}

                      {/* Cancel Running Job Button */}
                      {isRunning && (
                        <button
                          onClick={() => handleCancelSingleJob(job.id)}
                          disabled={cancellingJobId === job.id}
                          className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-rose-500/15 text-rose-300 hover:bg-rose-500 hover:text-white border border-rose-500/30 text-xs font-semibold shadow-xs active:scale-95 transition-all cursor-pointer disabled:opacity-50"
                          title="ยกเลิกการทำงานของงานนี้ทันที"
                        >
                          {cancellingJobId === job.id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Ban className="w-3.5 h-3.5" />
                          )}
                          <span>ยกเลิก</span>
                        </button>
                      )}

                      <button
                        onClick={() => handleDeleteSingleJob(job.id)}
                        className="p-1.5 rounded-xl text-muted-foreground hover:text-destructive hover:bg-destructive/10 border border-transparent hover:border-destructive/30 transition-all cursor-pointer"
                        title={isRunning ? "ยกเลิกและลบงานนี้" : "ลบงานนี้ออกจากประวัติ"}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Progress & Status Step */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span className="flex items-center gap-1.5">
                        {job.status === "parsing" && (
                          <span className="text-amber-400 flex items-center gap-1">
                            <Loader2 className="w-3 h-3 animate-spin" /> กำลังอ่านหน้าเว็บ
                          </span>
                        )}
                        {job.status === "downloading" && (
                          <span className="text-cyan-400 flex items-center gap-1">
                            <Download className="w-3 h-3 animate-bounce" /> กำลังดาวน์โหลดภาพ ({job.downloaded || 0}/{job.total_pages || "?"})
                          </span>
                        )}
                        {job.status === "translating" && (
                          <span className="text-violet-400 flex items-center gap-1">
                            <Languages className="w-3 h-3 animate-pulse" /> กำลังแปลด้วย Google Lens ({job.translated || 0}/{job.total_pages || "?"})
                          </span>
                        )}
                        {job.status === "refining" && (
                          <span className="text-fuchsia-400 flex items-center gap-1">
                            <Sparkles className="w-3.5 h-3.5 animate-pulse" /> {job.message || `กำลังขัดเกลาสำนวน AI (${job.translated || 0}/${job.total_pages || "?"})`}
                          </span>
                        )}
                        {job.status === "done" && (
                          <span className="text-emerald-400 flex items-center gap-1">
                            <CheckCircle2 className="w-3.5 h-3.5" /> แปลและสร้างไฟล์สมบูรณ์แล้ว
                          </span>
                        )}
                        {job.status === "error" && (
                          <span className="text-red-400 flex items-center gap-1">
                            <XCircle className="w-3.5 h-3.5" /> {job.message || "เกิดข้อผิดพลาด"}
                          </span>
                        )}
                      </span>

                      {isRunning && (
                        <span className="font-mono text-foreground font-bold">
                          {progress}%
                        </span>
                      )}
                    </div>

                    {isRunning && (
                      <div className="w-full bg-secondary rounded-full h-2 overflow-hidden">
                        <div
                          className="bg-gradient-to-r from-violet-500 via-primary to-cyan-400 h-2 rounded-full transition-all duration-300 shadow-sm"
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Clear Jobs History Confirmation Modal */}
      <ConfirmModal
        isOpen={isClearModalOpen}
        title={clearMode === "all" ? "ยืนยันการยกเลิกและล้างคิวงานทั้งหมด" : "ยืนยันการล้างประวัติงาน"}
        description={
          clearMode === "all"
            ? `ต้องการยกเลิกงานที่กำลังรันอยู่ทั้งหมด และลบรายการงานทั้ง ${jobs.length} งานออกจากระบบใช่หรือไม่? ไฟล์มังงะที่แปลแล้วจะไม่ถูกลบ`
            : "ต้องการลบประวัติงานที่เสร็จสิ้นและข้อผิดพลาดทั้งหมดออกจากรายการใช่หรือไม่? ไฟล์มังงะที่แปลแล้วจะไม่ถูกลบ"
        }
        confirmText={clearMode === "all" ? "ยกเลิกและล้างทั้งหมด" : "ล้างประวัติ"}
        cancelText="ยกเลิก"
        isDestructive={true}
        isLoading={isClearing}
        onConfirm={handleClearHistory}
        onClose={() => setIsClearModalOpen(false)}
      />
    </div>
  );
}
