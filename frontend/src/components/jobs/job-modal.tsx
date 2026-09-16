/** Universal Job Modal — submit single or range manga translation jobs. */
import { useState, useEffect } from "react";
import { useUIStore } from "@/stores/ui-store";
import { createJob, createRangeJob } from "@/api/client";
import {
  X,
  Sparkles,
  Layers,
  ExternalLink,
  Clipboard,
  Loader2,
  Check,
  AlertCircle,
  FileText,
} from "lucide-react";

const CHUNK_PRESETS = [
  { label: "ไม่สร้าง PDF", value: 0 },
  { label: "4 หน้า/แผ่น", value: 4 },
  { label: "8 หน้า (แนะนำ)", value: 8 },
  { label: "16 หน้า", value: 16 },
  { label: "รวมทั้งตอน", value: 999 },
];

const SUPPORTED_SITES = [
  { name: "MangaDex", url: "https://mangadex.org/" },
  { name: "WeebCentral", url: "https://weebcentral.com/" },
  { name: "MangaBlaze", url: "https://mangablaze.com/" },
  { name: "IsekaiNonbiri", url: "https://isekai-nonbiri.com/" },
];

export function JobModal() {
  const { isJobModalOpen, closeJobModal, jobModalInitialUrl } = useUIStore();

  const [mode, setMode] = useState<"single" | "range">("single");
  const [url, setUrl] = useState("");
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [chunk, setChunk] = useState(8);
  const [concurrency, setConcurrency] = useState(8);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Sync initial URL if provided
  useEffect(() => {
    if (jobModalInitialUrl) {
      setUrl(jobModalInitialUrl);
    }
  }, [jobModalInitialUrl]);

  // Global keyboard shortcut Ctrl+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        useUIStore.getState().openJobModal();
      } else if (e.key === "Escape" && isJobModalOpen) {
        closeJobModal();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isJobModalOpen, closeJobModal]);

  // Auto-detect range URLs
  const handleUrlChange = (val: string) => {
    setUrl(val);
    setError(null);
    // If URL looks like a series base URL (e.g., contains /manga/<slug>/ but not /chapter/), suggest range
    if (
      val.includes("/manga/") &&
      !val.includes("/chapter/") &&
      !val.includes("/chapters/")
    ) {
      setMode("range");
    }
  };

  const handlePasteClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        handleUrlChange(text.trim());
      }
    } catch {
      // clipboard access denied or not supported
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);

    if (!url.trim()) {
      setError("กรุณากรอก URL มังงะ");
      return;
    }

    setLoading(true);
    try {
      if (mode === "single") {
        await createJob(url.trim(), chunk, concurrency);
        setSuccessMsg("✓ เริ่มงานแปลแล้ว! ติดตามความคืบหน้าได้ที่แถบด้านล่าง");
      } else {
        const start = parseInt(rangeStart, 10);
        const end = parseInt(rangeEnd, 10);
        if (isNaN(start) || isNaN(end) || start < 1 || start > end) {
          throw new Error("ช่วงตอนไม่ถูกต้อง (เช่น ตอนที่ 1 ถึง 10)");
        }
        await createRangeJob(url.trim(), start, end, chunk, concurrency);
        setSuccessMsg(`✓ เริ่มดาวน์โหลดและแปลตอนที่ ${start} ถึง ${end} แล้ว!`);
      }

      setTimeout(() => {
        setUrl("");
        setRangeStart("");
        setRangeEnd("");
        setConcurrency(8);
        setSuccessMsg(null);
        closeJobModal();
      }, 1500);
    } catch (err: any) {
      setError(err.message || "เกิดข้อผิดพลาดในการเริ่มงาน");
    } finally {
      setLoading(false);
    }
  };

  if (!isJobModalOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-xl rounded-2xl bg-card border border-border/80 shadow-2xl overflow-hidden glass-panel">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border/60">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary/15 text-primary flex items-center justify-center">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground">
                เพิ่มงานแปลมังงะใหม่
              </h3>
              <p className="text-xs text-muted-foreground">
                ดาวน์โหลด แปลภาษาไทยด้วย Google Lens และสร้าง Long Strip PDF
              </p>
            </div>
          </div>
          <button
            onClick={closeJobModal}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Mode Selector */}
        <div className="flex p-1.5 mx-5 mt-4 bg-secondary/80 rounded-xl border border-border/50 text-xs font-medium">
          <button
            type="button"
            onClick={() => setMode("single")}
            className={`flex-1 py-1.5 rounded-lg flex items-center justify-center gap-1.5 transition-all ${
              mode === "single"
                ? "bg-primary text-white shadow-md shadow-primary/25 font-semibold"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            แปลตอนเดียว (Single Chapter)
          </button>
          <button
            type="button"
            onClick={() => setMode("range")}
            className={`flex-1 py-1.5 rounded-lg flex items-center justify-center gap-1.5 transition-all ${
              mode === "range"
                ? "bg-primary text-white shadow-md shadow-primary/25 font-semibold"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            แปลหลายตอนต่อเนื่อง (Range)
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {/* URL Input */}
          <div>
            <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">
              {mode === "single" ? "URL ตอนมังงะ" : "Base URL ของมังงะ"}
            </label>
            <div className="relative flex items-center">
              <input
                type="text"
                value={url}
                onChange={(e) => handleUrlChange(e.target.value)}
                placeholder={
                  mode === "single"
                    ? "เช่น https://weebcentral.com/chapters/... หรือ MangaDex"
                    : "เช่น https://mangablaze.com/manga/<slug>/"
                }
                className="w-full px-4 py-2.5 pr-20 bg-secondary/80 rounded-xl border border-border text-foreground text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all font-mono"
                required
                autoFocus
              />
              <button
                type="button"
                onClick={handlePasteClipboard}
                className="absolute right-2 px-2.5 py-1 rounded-lg text-xs text-muted-foreground hover:text-foreground bg-card border border-border/80 hover:border-primary flex items-center gap-1 transition-all"
                title="วางจากคลิปบอร์ด"
              >
                <Clipboard className="w-3 h-3" />
                วาง
              </button>
            </div>
          </div>

          {/* Chapter Range Fields */}
          {mode === "range" && (
            <div className="grid grid-cols-2 gap-3 p-3.5 rounded-xl bg-secondary/40 border border-border/60">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">
                  ตอนเริ่มต้น (Start)
                </label>
                <input
                  type="number"
                  min={1}
                  value={rangeStart}
                  onChange={(e) => setRangeStart(e.target.value)}
                  placeholder="เช่น 1"
                  className="w-full px-3 py-2 bg-secondary rounded-lg border border-border text-foreground text-sm focus:outline-none focus:border-primary"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">
                  ตอนสิ้นสุด (End)
                </label>
                <input
                  type="number"
                  min={1}
                  value={rangeEnd}
                  onChange={(e) => setRangeEnd(e.target.value)}
                  placeholder="เช่น 10"
                  className="w-full px-3 py-2 bg-secondary rounded-lg border border-border text-foreground text-sm focus:outline-none focus:border-primary"
                  required
                />
              </div>
            </div>
          )}

          {/* Chunk Presets */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                <FileText className="w-3.5 h-3.5 text-primary" />
                การแบ่งหน้า Long Strip PDF (Chunk Size)
              </label>
              <span className="text-[11px] text-muted-foreground font-mono">
                {chunk === 0 ? "ไม่สร้าง PDF" : `${chunk} หน้า / ไฟล์`}
              </span>
            </div>
            <div className="grid grid-cols-5 gap-1.5">
              {CHUNK_PRESETS.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => setChunk(p.value)}
                  className={`py-1.5 px-2 rounded-lg text-xs font-medium border text-center transition-all ${
                    chunk === p.value
                      ? "bg-primary/20 border-primary text-violet-300 font-semibold shadow-sm"
                      : "bg-secondary/60 border-border text-muted-foreground hover:text-foreground hover:bg-secondary"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Lens Concurrency */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
                ความเร็วแปล Lens (Concurrency)
              </label>
              <span className="text-[11px] text-emerald-400 font-mono">
                {concurrency}× threads
              </span>
            </div>
            <div className="grid grid-cols-4 gap-1.5">
              {[2, 4, 8, 12].map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setConcurrency(c)}
                  className={`py-1.5 px-2 rounded-lg text-xs font-medium border text-center transition-all ${
                    concurrency === c
                      ? "bg-emerald-600/20 border-emerald-500 text-emerald-400 font-semibold shadow-sm"
                      : "bg-secondary/60 border-border text-muted-foreground hover:text-foreground hover:bg-secondary"
                  }`}
                >
                  {c}× threads
                </button>
              ))}
            </div>
          </div>

          {/* Supported Sites */}
          <div className="pt-2">
            <div className="text-[11px] text-muted-foreground mb-1.5">
              🌐 เว็บไซต์ที่รองรับ Parser:
            </div>
            <div className="flex flex-wrap gap-1.5">
              {SUPPORTED_SITES.map((s) => (
                <a
                  key={s.name}
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium bg-secondary/60 border border-border/80 text-muted-foreground hover:text-foreground hover:border-primary transition-all"
                >
                  {s.name}
                  <ExternalLink className="w-2.5 h-2.5 opacity-60" />
                </a>
              ))}
            </div>
          </div>

          {/* Feedback messages */}
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-destructive/15 border border-destructive/30 text-destructive text-xs">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {successMsg && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-xs">
              <Check className="w-4 h-4 shrink-0" />
              <span>{successMsg}</span>
            </div>
          )}

          {/* Submit Button */}
          <div className="pt-2 flex justify-end gap-2.5">
            <button
              type="button"
              onClick={closeJobModal}
              className="px-4 py-2.5 rounded-xl border border-border text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-secondary transition-all"
            >
              ยกเลิก
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 via-primary to-indigo-600 text-white text-xs font-semibold shadow-lg shadow-primary/30 hover:brightness-110 active:scale-[0.98] disabled:opacity-50 transition-all cursor-pointer"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  กำลังส่งคำขอ...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  เริ่มดาวน์โหลดและแปล →
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
