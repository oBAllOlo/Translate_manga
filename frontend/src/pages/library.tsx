/** Library — Series-Centric Catalog with cover art grid and chapter drawer. */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchChapters, deleteAllChapters, type SeriesGroup } from "@/api/client";
import { SeriesCard } from "@/components/library/series-card";
import { ChapterDrawer } from "@/components/library/chapter-drawer";
import { ConfirmModal } from "@/components/common/confirm-modal";
import { useUIStore } from "@/stores/ui-store";
import {
  Search,
  SlidersHorizontal,
  Trash2,
  ArrowUpDown,
  PlusCircle,
} from "lucide-react";

export default function LibraryPage() {
  const queryClient = useQueryClient();
  const { openJobModal } = useUIStore();

  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "completed" | "in-progress">("all");
  const [sortBy, setSortBy] = useState<"recent" | "title" | "count">("recent");
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["chapters"],
    queryFn: fetchChapters,
  });

  const series = data?.series ?? [];
  const totalChapters = data?.chapters?.length ?? 0;

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["chapters"] });
  };

  const confirmDeleteAll = async () => {
    setIsDeleting(true);
    try {
      await deleteAllChapters();
      await queryClient.invalidateQueries({ queryKey: ["chapters"] });
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      useUIStore.getState().clearContinueReading();
      setIsDeleteModalOpen(false);
    } finally {
      setIsDeleting(false);
    }
  };

  // Filter & Sort Logic
  const filteredSeries = series
    .filter((s) => {
      // Search
      if (search.trim()) {
        const q = search.toLowerCase();
        const titleMatch = s.series_title.toLowerCase().includes(q);
        const chapterMatch = (s.chapters || []).some((c) =>
          (c.title || c.name).toLowerCase().includes(q)
        );
        if (!titleMatch && !chapterMatch) return false;
      }

      // Completion filter
      const chapters = s.chapters || [];
      const transCount = chapters.filter(
        (c) => c.thumb_kind === "translated" || c.translated_count > 0
      ).length;
      const isCompleted = chapters.length > 0 && transCount === chapters.length;

      if (filter === "completed" && !isCompleted) return false;
      if (filter === "in-progress" && isCompleted) return false;

      return true;
    })
    .sort((a, b) => {
      if (sortBy === "title") return a.series_title.localeCompare(b.series_title);
      if (sortBy === "count") return (b.chapter_count || 0) - (a.chapter_count || 0);
      // default: recent
      const aTime = Math.max(...(a.chapters || []).map((c) => c.mtime || 0), 0);
      const bTime = Math.max(...(b.chapters || []).map((c) => c.mtime || 0), 0);
      return bTime - aTime;
    });

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Top Search & Filter Bar */}
      <div className="p-4 rounded-2xl bg-card/80 border border-border/70 shadow-xl glass-panel space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          {/* Search Box */}
          <div className="relative flex-1 min-w-[260px]">
            <Search className="w-4 h-4 absolute left-3.5 top-3 text-muted-foreground" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="ค้นหาชื่อมังงะ หรือชื่อตอน..."
              className="w-full pl-10 pr-4 py-2.5 bg-secondary/70 rounded-xl border border-border text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 text-foreground transition-all"
            />
          </div>

          {/* Sort Dropdown */}
          <div className="flex items-center gap-1.5 bg-secondary/70 rounded-xl p-1 border border-border text-xs">
            <ArrowUpDown className="w-3.5 h-3.5 text-muted-foreground ml-2" />
            <button
              onClick={() => setSortBy("recent")}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                sortBy === "recent"
                  ? "bg-primary text-white font-semibold shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              ล่าสุด
            </button>
            <button
              onClick={() => setSortBy("title")}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                sortBy === "title"
                  ? "bg-primary text-white font-semibold shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              ชื่อ ก-ฮ
            </button>
            <button
              onClick={() => setSortBy("count")}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                sortBy === "count"
                  ? "bg-primary text-white font-semibold shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              จำนวนตอน
            </button>
          </div>

          {/* Delete All Button */}
          {(series.length > 0 || totalChapters > 0) && (
            <button
              id="btn-delete-all-library"
              onClick={() => setIsDeleteModalOpen(true)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-muted-foreground hover:text-destructive hover:bg-destructive/10 border border-transparent hover:border-destructive/30 text-xs font-semibold transition-all cursor-pointer"
              title="ลบมังงะทั้งหมดในระบบ"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>ลบทั้งหมด</span>
            </button>
          )}
        </div>

        {/* Filter Chips */}
        <div className="flex items-center gap-2 flex-wrap pt-1 text-xs">
          <span className="text-muted-foreground font-medium flex items-center gap-1">
            <SlidersHorizontal className="w-3 h-3 text-primary" />
            สถานะ:
          </span>
          {[
            { id: "all", label: `ทั้งหมด (${series.length} เรื่อง · ${totalChapters} ตอน)` },
            { id: "completed", label: "แปลครบแล้ว" },
            { id: "in-progress", label: "มีตอนรอแปลต่อ" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setFilter(tab.id as any)}
              className={`px-3 py-1 rounded-lg transition-all ${
                filter === tab.id
                  ? "bg-primary/20 text-violet-300 border border-primary/40 font-semibold"
                  : "bg-secondary/60 text-muted-foreground hover:text-foreground border border-border"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Series Grid */}
      {isLoading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {[...Array(6)].map((_, i) => (
            <div
              key={i}
              className="aspect-[3/4] rounded-2xl bg-secondary/50 animate-pulse border border-border/50"
            />
          ))}
        </div>
      ) : filteredSeries.length === 0 ? (
        <div className="text-center py-20 rounded-2xl bg-card/40 border border-border/50 space-y-3 glass-panel">
          <div className="w-16 h-16 rounded-2xl bg-secondary flex items-center justify-center text-3xl mx-auto shadow-inner">
            📚
          </div>
          <h3 className="text-base font-bold text-foreground">
            {search ? "ไม่พบมังงะที่ตรงกับคำค้นหา" : "ยังไม่มีมังงะในคลัง"}
          </h3>
          <p className="text-xs text-muted-foreground max-w-sm mx-auto">
            {search
              ? "ลองค้นหาด้วยคำอื่น หรือตรวจสอบตัวสะกด"
              : "กดปุ่มด้านล่างเพื่อเพิ่ม URL ตอนมังงะจาก MangaDex หรือ WeebCentral"}
          </p>
          {!search && (
            <button
              onClick={() => openJobModal()}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 via-primary to-indigo-600 text-white font-semibold text-xs shadow-lg shadow-primary/25 hover:brightness-110 active:scale-95 transition-all mt-2 cursor-pointer"
            >
              <PlusCircle className="w-4 h-4" />
              เพิ่มงานแปลเรื่องแรก
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {filteredSeries.map((s) => (
            <SeriesCard key={s.series_title} series={s} />
          ))}
        </div>
      )}

      {/* Slide-over Chapter Drawer */}
      <ChapterDrawer onRefresh={handleRefresh} />

      {/* Delete All Confirmation Modal */}
      <ConfirmModal
        isOpen={isDeleteModalOpen}
        title="ยืนยันการลบมังงะทั้งหมด"
        description="คุณแน่ใจหรือไม่ว่าต้องการลบมังงะและตอนทั้งหมดในระบบ? ไฟล์ภาพที่แปลแล้วและ PDF ทั้งหมดจะถูกลบถาวร"
        confirmText="ลบทั้งหมด"
        cancelText="ยกเลิก"
        isDestructive={true}
        isLoading={isDeleting}
        onConfirm={confirmDeleteAll}
        onClose={() => setIsDeleteModalOpen(false)}
      />
    </div>
  );
}
