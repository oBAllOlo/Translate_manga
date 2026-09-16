/** Slide-over Chapter Drawer with batch operations & individual chapter actions. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useUIStore } from "@/stores/ui-store";
import {
  translateChapter,
  retryChapter,
  deleteChapter,
  resolvePdfUrl,
  type ChapterSummary,
} from "@/api/client";
import { ConfirmModal } from "@/components/common/confirm-modal";
import {
  X,
  BookOpen,
  Languages,
  RotateCw,
  Trash2,
  Search,
  FileDown,
} from "lucide-react";

export function ChapterDrawer({ onRefresh }: { onRefresh: () => void }) {
  const navigate = useNavigate();
  const { selectedSeries, isSeriesDrawerOpen, closeSeriesDrawer } = useUIStore();
  const [filter, setFilter] = useState<"all" | "translated" | "untranslated" | "failed">("all");
  const [search, setSearch] = useState("");
  const [batchLoading, setBatchLoading] = useState(false);
  const [confirmModal, setConfirmModal] = useState<{
    isOpen: boolean;
    title: string;
    description: string;
    confirmText?: string;
    isDestructive?: boolean;
    onConfirm: () => Promise<void> | void;
  } | null>(null);

  if (!isSeriesDrawerOpen || !selectedSeries) return null;

  const chapters = selectedSeries.chapters || [];

  // Filtering
  const filteredChapters = chapters.filter((ch) => {
    const isTrans = ch.thumb_kind === "translated" || ch.translated_count > 0;
    const isFailed = ch.has_failed;

    if (filter === "translated" && !isTrans) return false;
    if (filter === "untranslated" && isTrans) return false;
    if (filter === "failed" && !isFailed) return false;

    if (search.trim()) {
      const q = search.toLowerCase();
      return (ch.title || ch.name).toLowerCase().includes(q);
    }
    return true;
  });

  const untranslatedCount = chapters.filter(
    (ch) => ch.thumb_kind !== "translated" && ch.translated_count === 0
  ).length;
  const failedCount = chapters.filter((ch) => ch.has_failed).length;
  const translatedCount = chapters.filter(
    (ch) => ch.thumb_kind === "translated" || ch.translated_count > 0
  ).length;

  // Batch translate all untranslated
  const handleBatchTranslate = () => {
    const target = chapters.filter(
      (ch) => ch.thumb_kind !== "translated" && ch.translated_count === 0
    );
    if (target.length === 0) return;

    setConfirmModal({
      isOpen: true,
      title: "ยืนยันการแปลยกชุด",
      description: `ต้องการเริ่มแปล Google Lens ทั้งหมด ${target.length} ตอนที่ยังไม่ได้แปลใช่หรือไม่?`,
      confirmText: "เริ่มแปลทั้งหมด",
      onConfirm: async () => {
        setBatchLoading(true);
        setConfirmModal(null);
        try {
          for (const ch of target) {
            await translateChapter(ch.name);
          }
          onRefresh();
        } catch (err: any) {
          alert("เกิดข้อผิดพลาด: " + err.message);
        } finally {
          setBatchLoading(false);
        }
      },
    });
  };

  // Batch retry failed
  const handleBatchRetry = () => {
    const target = chapters.filter((ch) => ch.has_failed);
    if (target.length === 0) return;

    setConfirmModal({
      isOpen: true,
      title: "ยืนยันการ Retry หน้าที่ล้มเหลว",
      description: `ต้องการ Retry หน้าที่ล้มเหลวใน ${target.length} ตอนใช่หรือไม่?`,
      confirmText: "Retry ทั้งหมด",
      onConfirm: async () => {
        setBatchLoading(true);
        setConfirmModal(null);
        try {
          for (const ch of target) {
            await retryChapter(ch.name);
          }
          onRefresh();
        } catch (err: any) {
          alert("เกิดข้อผิดพลาด: " + err.message);
        } finally {
          setBatchLoading(false);
        }
      },
    });
  };

  const handleTranslateOne = async (ch: ChapterSummary) => {
    await translateChapter(ch.name);
    onRefresh();
  };

  const handleRetryOne = async (ch: ChapterSummary) => {
    await retryChapter(ch.name);
    onRefresh();
  };

  const handleDeleteOne = (ch: ChapterSummary) => {
    setConfirmModal({
      isOpen: true,
      title: "ยืนยันการลบตอน",
      description: `ต้องการลบตอน "${ch.title || ch.name}" ออกจากคลังมังงะใช่หรือไม่? ข้อมูลของตอนนี้จะถูกลบถาวร`,
      confirmText: "ลบตอนนี้",
      isDestructive: true,
      onConfirm: async () => {
        setBatchLoading(true);
        try {
          await deleteChapter(ch.name);
          const curr = useUIStore.getState().continueReading;
          if (curr && curr.chapterSlug.toLowerCase() === ch.name.toLowerCase()) {
            useUIStore.getState().clearContinueReading();
          }
          onRefresh();
          setConfirmModal(null);
        } finally {
          setBatchLoading(false);
        }
      },
    });
  };

  const handleDeleteSeries = () => {
    if (chapters.length === 0) return;
    const title = selectedSeries?.series_title || "เรื่องนี้";
    setConfirmModal({
      isOpen: true,
      title: `ยืนยันการลบทั้งเรื่อง "${title}"`,
      description: `ต้องการลบมังงะเรื่องนี้พร้อมตอนทั้งหมด ${chapters.length} ตอนออกจากระบบใช่หรือไม่? ไฟล์ทั้งหมดจะถูกลบถาวร`,
      confirmText: "ลบทั้งเรื่อง",
      isDestructive: true,
      onConfirm: async () => {
        setBatchLoading(true);
        try {
          for (const ch of chapters) {
            await deleteChapter(ch.name);
          }
          const curr = useUIStore.getState().continueReading;
          if (curr && chapters.some((c) => c.name.toLowerCase() === curr.chapterSlug.toLowerCase())) {
            useUIStore.getState().clearContinueReading();
          }
          closeSeriesDrawer();
          onRefresh();
          setConfirmModal(null);
        } finally {
          setBatchLoading(false);
        }
      },
    });
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        onClick={closeSeriesDrawer}
        className="absolute inset-0 bg-background/70 backdrop-blur-sm transition-opacity"
      />

      {/* Slide-over panel */}
      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-xl bg-card border-l border-border/80 shadow-2xl flex flex-col glass-panel animate-in slide-in-from-right duration-300">
          {/* Header */}
          <div className="p-6 border-b border-border/60 flex items-start justify-between gap-4">
            <div className="flex gap-4 min-w-0">
              {selectedSeries.thumb ? (
                <img
                  src={`/output/${encodeURI(selectedSeries.thumb_name || selectedSeries.chapters[0]?.name || "")}/${selectedSeries.thumb}`}
                  alt={selectedSeries.series_title}
                  className="w-16 h-22 object-cover rounded-xl border border-border shadow-md shrink-0"
                />
              ) : (
                <div className="w-16 h-22 rounded-xl bg-secondary flex items-center justify-center text-2xl border border-border shrink-0">
                  📖
                </div>
              )}
              <div className="min-w-0">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-primary">
                  มังงะซีรีส์
                </span>
                <h3 className="text-lg font-bold text-foreground truncate mt-0.5" title={selectedSeries.series_title}>
                  {selectedSeries.series_title}
                </h3>
                <div className="flex items-center gap-3 text-xs text-muted-foreground mt-2">
                  <span>📚 {chapters.length} ตอน</span>
                  <span>✨ แปลแล้ว {translatedCount}/{chapters.length}</span>
                </div>
              </div>
            </div>

            <button
              onClick={closeSeriesDrawer}
              className="p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Batch Actions Bar */}
          <div className="p-4 bg-secondary/40 border-b border-border/60 flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2">
              {untranslatedCount > 0 && (
                <button
                  onClick={handleBatchTranslate}
                  disabled={batchLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gradient-to-r from-violet-600 to-primary text-white text-xs font-semibold shadow-sm hover:brightness-110 active:scale-95 transition-all disabled:opacity-50"
                >
                  <Languages className="w-3.5 h-3.5" />
                  แปลทุกตอน ({untranslatedCount})
                </button>
              )}
              {failedCount > 0 && (
                <button
                  onClick={handleBatchRetry}
                  disabled={batchLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/40 text-xs font-semibold hover:bg-amber-500/30 active:scale-95 transition-all disabled:opacity-50"
                >
                  <RotateCw className="w-3.5 h-3.5" />
                  Retry หน้าที่ตกหล่น ({failedCount})
                </button>
              )}
              {chapters.length > 0 && (
                <button
                  id="btn-delete-series-drawer"
                  onClick={handleDeleteSeries}
                  disabled={batchLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 border border-transparent hover:border-destructive/30 text-xs font-semibold transition-all disabled:opacity-50 cursor-pointer"
                  title="ลบมังงะเรื่องนี้พร้อมทุกตอนออกจากระบบ"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  ลบเรื่องนี้
                </button>
              )}
            </div>

            <div className="text-xs text-muted-foreground font-mono">
              {Math.round((translatedCount / (chapters.length || 1)) * 100)}% สมบูรณ์
            </div>
          </div>

          {/* Search & Filter Chips */}
          <div className="p-4 space-y-2.5 border-b border-border/60">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-muted-foreground" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="ค้นหาตอน..."
                className="w-full pl-9 pr-4 py-2 bg-secondary/70 rounded-xl border border-border text-xs focus:outline-none focus:border-primary text-foreground"
              />
            </div>
            <div className="flex gap-1.5 flex-wrap">
              {[
                { id: "all", label: `ทั้งหมด (${chapters.length})` },
                { id: "translated", label: `แปลแล้ว (${translatedCount})` },
                { id: "untranslated", label: `ยังไม่แปล (${untranslatedCount})` },
                ...(failedCount > 0 ? [{ id: "failed", label: `ล้มเหลว (${failedCount})` }] : []),
              ].map((t) => (
                <button
                  key={t.id}
                  onClick={() => setFilter(t.id as any)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                    filter === t.id
                      ? "bg-primary text-white shadow-sm"
                      : "bg-secondary text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          {/* Chapters List */}
          <div className="flex-1 overflow-y-auto p-4 space-y-2.5">
            {filteredChapters.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground text-xs">
                ไม่พบตอนที่ตรงกับเงื่อนไข
              </div>
            ) : (
              filteredChapters.map((ch) => {
                const isTrans = ch.thumb_kind === "translated" || ch.translated_count > 0;

                return (
                  <div
                    key={ch.name}
                    className="p-3 rounded-xl bg-secondary/50 hover:bg-secondary border border-border/60 hover:border-primary/40 transition-all flex items-center justify-between gap-3 group"
                  >
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <div className="w-12 h-16 rounded-lg bg-black/60 overflow-hidden shrink-0 relative border border-border">
                        {ch.thumb && (
                          <img
                            src={`/output/${encodeURI(ch.name)}/${ch.thumb}`}
                            alt=""
                            className="w-full h-full object-cover"
                          />
                        )}
                        <span
                          className={`absolute bottom-1 right-1 px-1 py-0.2 rounded text-[9px] font-bold ${
                            isTrans
                              ? "bg-emerald-500 text-white"
                              : "bg-amber-500 text-black"
                          }`}
                        >
                          {isTrans ? "TH" : "EN"}
                        </span>
                      </div>

                      <div className="min-w-0 flex-1">
                        <div
                          onClick={() => {
                            closeSeriesDrawer();
                            navigate(`/reader/${encodeURIComponent(ch.name)}`);
                          }}
                          className="font-semibold text-sm text-foreground hover:text-primary cursor-pointer truncate transition-colors"
                          title={ch.title || ch.name}
                        >
                          {ch.title || ch.name}
                        </div>
                        <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2">
                          <span>
                            📄 แปลแล้ว {ch.translated_count}/{ch.page_count || "?"} หน้า
                          </span>
                          {ch.pdfs.length > 0 && (
                            <span className="text-cyan-400 font-mono text-[11px]">
                              · {ch.pdfs.length} PDF
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        onClick={() => {
                          closeSeriesDrawer();
                          navigate(`/reader/${encodeURIComponent(ch.name)}`);
                        }}
                        className="px-3 py-1.5 rounded-lg bg-primary/20 text-violet-300 hover:bg-primary hover:text-white text-xs font-semibold flex items-center gap-1 transition-all"
                        title="เปิดอ่านมังงะ"
                      >
                        <BookOpen className="w-3.5 h-3.5" />
                        อ่าน
                      </button>

                      {ch.pdfs && ch.pdfs.length > 0 && (
                        <a
                          href={resolvePdfUrl(ch.pdfs[0])}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2.5 py-1.5 rounded-lg bg-secondary text-cyan-400 hover:text-cyan-300 hover:bg-card border border-border text-xs font-semibold flex items-center gap-1 transition-all"
                          title="เปิดดูไฟล์ PDF"
                        >
                          <FileDown className="w-3.5 h-3.5" />
                          <span>PDF</span>
                        </a>
                      )}

                      {!isTrans && (
                        <button
                          onClick={() => handleTranslateOne(ch)}
                          className="p-1.5 rounded-lg bg-secondary text-muted-foreground hover:text-foreground hover:bg-card border border-border"
                          title="สั่งแปลด้วย Google Lens"
                        >
                          <Languages className="w-3.5 h-3.5" />
                        </button>
                      )}

                      {ch.has_failed && (
                        <button
                          onClick={() => handleRetryOne(ch)}
                          className="p-1.5 rounded-lg bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 border border-amber-500/30"
                          title="Retry หน้าที่ตกหล่น"
                        >
                          <RotateCw className="w-3.5 h-3.5" />
                        </button>
                      )}

                      <button
                        onClick={() => handleDeleteOne(ch)}
                        className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/15 transition-colors"
                        title="ลบตอนนี้"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Confirmation Modal */}
      {confirmModal && (
        <ConfirmModal
          isOpen={confirmModal.isOpen}
          title={confirmModal.title}
          description={confirmModal.description}
          confirmText={confirmModal.confirmText}
          isDestructive={confirmModal.isDestructive}
          isLoading={batchLoading}
          onConfirm={confirmModal.onConfirm}
          onClose={() => setConfirmModal(null)}
        />
      )}
    </div>
  );
}
