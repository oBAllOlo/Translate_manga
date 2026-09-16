/** Reader — Immersive Manga Experience with Hold-to-Peek, 3 Modes, Scrubber & Next Chapter Flow. */
import { useEffect, useCallback, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchChapter, fetchChapters, resolvePdfUrl, refineChapter, refineChapterPage, type ChapterDetail } from "@/api/client";
import { useReaderStore, type ReaderMode } from "@/stores/reader-store";
import { useUIStore } from "@/stores/ui-store";
import {
  ArrowLeft,
  ZoomIn,
  ZoomOut,
  Maximize,
  Minimize,
  Eye,
  EyeOff,
  ChevronLeft,
  ChevronRight,
  Columns2,
  Rows3,
  BookOpen,
  HelpCircle,
  X,
  Sparkles,
  ArrowRight,
  Compass,
  AlertCircle,
  FileDown,
  FileText,
  Paintbrush,
  Loader2,
  Copy,
  Check,
  Languages,
} from "lucide-react";
import TouchupModal from "@/components/TouchupModal";

export default function ReaderPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const isScrollingFromSliderRef = useRef(false);
  const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const {
    mode,
    setMode,
    showTranslated,
    isPeeking,
    setIsPeeking,
    currentPage,
    setPage,
    zoom,
    setZoom,
    resetZoom,
    autoNextChapter,
  } = useReaderStore();

  const { setContinueReading, openJobModal } = useUIStore();

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showHud, setShowHud] = useState(true);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [isTouchupOpen, setIsTouchupOpen] = useState(false);
  const [touchupPageNo, setTouchupPageNo] = useState(1);
  const [imgTimestamp, setImgTimestamp] = useState(Date.now());

  const queryClient = useQueryClient();
  const [isRefinePanelOpen, setIsRefinePanelOpen] = useState(false);
  const [isRefiningPage, setIsRefiningPage] = useState(false);
  const [refineError, setRefineError] = useState<string | null>(null);
  const [copiedOriginal, setCopiedOriginal] = useState(false);
  const [copiedRefined, setCopiedRefined] = useState(false);

  // Fullscreen toggle
  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
      setIsFullscreen(true);
    } else {
      document.exitFullscreen().catch(() => {});
      setIsFullscreen(false);
    }
  }, []);

  // Fetch current chapter
  const { data: chapter, isLoading, isError } = useQuery({
    queryKey: ["chapter", slug],
    queryFn: () => fetchChapter(slug!),
    enabled: !!slug,
    retry: 1,
  });

  // Fetch all chapters to determine Next/Prev chapters in the same series
  const { data: allData } = useQuery({
    queryKey: ["chapters"],
    queryFn: fetchChapters,
  });

  const pages = chapter?.pages ?? [];
  const totalPages = pages.length;
  const currentPageInfo = pages[currentPage - 1];

  const handleRefineCurrentPage = async (force = true) => {
    if (!slug || !currentPage) return;
    setIsRefiningPage(true);
    setRefineError(null);
    try {
      const res = await refineChapterPage(slug, currentPage, force);
      if (res.error) {
        setRefineError(res.error);
      }
      queryClient.setQueryData(["chapter", slug], (old: ChapterDetail | undefined) => {
        if (!old) return old;
        const updatedPages = old.pages.map((p) => {
          if (p.page === currentPage) {
            return {
              ...p,
              original_text: res.original_text || p.original_text,
              refined_text: res.refined_text,
            };
          }
          return p;
        });
        return {
          ...old,
          has_refined: true,
          pages: updatedPages,
        };
      });
    } catch (err: any) {
      setRefineError(err.message || "เกิดข้อผิดพลาดในการขัดเกลาสำนวน");
    } finally {
      setIsRefiningPage(false);
    }
  };

  const handleRefineWholeChapter = async () => {
    if (!slug) return;
    try {
      await refineChapter(slug);
      queryClient.invalidateQueries({ queryKey: ["chapter", slug] });
      queryClient.invalidateQueries({ queryKey: ["chapters"] });
      alert("เริ่มงานขัดเกลาทุกหน้าในเบื้องหลังแล้ว ติดตามความคืบหน้าได้ที่ Dashboard");
    } catch (err: any) {
      alert("เกิดข้อผิดพลาด: " + err.message);
    }
  };

  const handleCopy = (text: string, isRefined: boolean) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    if (isRefined) {
      setCopiedRefined(true);
      setTimeout(() => setCopiedRefined(false), 2000);
    } else {
      setCopiedOriginal(true);
      setTimeout(() => setCopiedOriginal(false), 2000);
    }
  };

  // Find next & previous chapters in same series
  let nextChapterSlug: string | null = null;
  let prevChapterSlug: string | null = null;
  if (allData && slug) {
    for (const s of allData.series) {
      const idx = s.chapters.findIndex((c) => c.name === slug);
      if (idx !== -1) {
        if (idx + 1 < s.chapters.length) nextChapterSlug = s.chapters[idx + 1].name;
        if (idx - 1 >= 0) prevChapterSlug = s.chapters[idx - 1].name;
        break;
      }
    }
  }

  // Helper to normalize any file path under output
  const normalizePath = (p?: string) => {
    if (!p) return "";
    return p
      .replace(/\\/g, "/")
      .replace(/^[A-Za-z]:.*?[\\/]output[\\/]/i, "")
      .replace(/^\/?(?:\.\.\/)?output\//i, "")
      .replace(/^\.\.\//, "")
      .replace(/^\/+/, "");
  };

  // Resolved PDF URL for this chapter
  const pdfUrl = chapter?.pdfs?.length
    ? resolvePdfUrl(chapter.pdfs[0])
    : slug
    ? `/output/pdfs/${slug}.pdf`
    : "";

  // Update continue reading
  useEffect(() => {
    if (chapter && slug && chapter.pages.length > 0) {
      const firstPage = chapter.pages[0];
      const targetThumb = firstPage.has_translation && firstPage.translated_file
        ? firstPage.translated_file
        : firstPage.file;
      const cleanThumb = normalizePath(targetThumb);
      const thumb = cleanThumb
        ? cleanThumb.replace(/^[^\/]+\//, "")
        : (firstPage.has_translation ? "translated_images/page-001.jpg" : "images/page-001.jpg");

      setContinueReading({
        chapterSlug: slug,
        chapterTitle: chapter.title,
        page: currentPage,
        thumb,
      });
    }
  }, [chapter, slug, currentPage, setContinueReading]);

  // Image source helper: checks if peeking (force original) or showing translated
  const getImageUrl = useCallback(
    (page: typeof pages[0]) => {
      if (!page) return "";
      const effectiveShowTranslated = !isPeeking && showTranslated;

      const targetPath = (effectiveShowTranslated && page.has_translation && page.translated_file)
        ? page.translated_file
        : page.file;

      let url = "";
      if (targetPath) {
        const clean = normalizePath(targetPath);
        if (clean) url = `/output/${clean}`;
      }

      if (!url) {
        const folder = effectiveShowTranslated ? "translated_images" : "images";
        url = `/output/${slug}/${folder}/page-${String(page.page).padStart(3, "0")}.jpg`;
      }

      return `${url}?t=${imgTimestamp}`;
    },
    [isPeeking, showTranslated, slug, imgTimestamp]
  );

  // Jump to specific page and scroll the view accordingly in Long Strip
  const jumpToPage = useCallback(
    (pageNo: number, smooth = true) => {
      const targetPage = Math.max(1, Math.min(pageNo, totalPages || 1));
      setPage(targetPage);

      if (mode === "long-strip") {
        isScrollingFromSliderRef.current = true;
        const el = document.getElementById(`page-${targetPage}`);
        if (el) {
          el.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
        }
        if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
        scrollTimeoutRef.current = setTimeout(() => {
          isScrollingFromSliderRef.current = false;
        }, 800);
      }
    },
    [mode, setPage, totalPages]
  );

  // Synchronize currentPage and bottom slider with viewport during Long Strip scrolling
  const handleCanvasScroll = useCallback(() => {
    if (mode !== "long-strip" || isScrollingFromSliderRef.current) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Viewport focal line: top of canvas + 140px (accounts for top HUD)
    const focalY = canvas.getBoundingClientRect().top + 140;
    let foundPage = 1;

    for (const p of pages) {
      const el = document.getElementById(`page-${p.page}`);
      if (el) {
        const rect = el.getBoundingClientRect();
        if (rect.top <= focalY && rect.bottom >= focalY) {
          foundPage = p.page;
          break;
        } else if (rect.top > focalY) {
          break;
        } else {
          foundPage = p.page;
        }
      }
    }

    if (foundPage !== currentPage) {
      setPage(foundPage);
    }
  }, [mode, pages, currentPage, setPage]);

  // When switching into long-strip mode from another mode, align scroll to current page
  useEffect(() => {
    if (mode === "long-strip" && currentPage > 1) {
      const timer = setTimeout(() => {
        const el = document.getElementById(`page-${currentPage}`);
        if (el) {
          el.scrollIntoView({ behavior: "auto", block: "start" });
        }
      }, 60);
      return () => clearTimeout(timer);
    }
  }, [mode]);

  // Keyboard navigation & Hold-to-Peek
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Avoid shortcuts if typing in input
      if ((e.target as HTMLElement).tagName === "INPUT") return;

      // Hold-to-Peek: H or Shift
      if ((e.key === "h" || e.key === "H" || e.key === "Shift") && !isPeeking) {
        setIsPeeking(true);
      }

      if (e.key === "ArrowRight" || e.key === " ") {
        e.preventDefault();
        const step = mode === "double-page" ? 2 : 1;
        jumpToPage(Math.min(currentPage + step, totalPages), true);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        const step = mode === "double-page" ? 2 : 1;
        jumpToPage(Math.max(currentPage - step, 1), true);
      } else if (e.key === "Escape") {
        if (showShortcuts) setShowShortcuts(false);
        else navigate(-1);
      } else if (e.key === "f" || e.key === "F") {
        e.preventDefault();
        toggleFullscreen();
      } else if (e.key === "m" || e.key === "M") {
        e.preventDefault();
        const modes: ReaderMode[] = ["long-strip", "page-by-page", "double-page", "pdf"];
        const nextMode = modes[(modes.indexOf(mode) + 1) % modes.length];
        setMode(nextMode);
      } else if (e.key === "?") {
        e.preventDefault();
        setShowShortcuts((prev) => !prev);
      } else if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        setZoom(zoom + 15);
      } else if (e.key === "-") {
        e.preventDefault();
        setZoom(zoom - 15);
      } else if (e.key === "0") {
        e.preventDefault();
        resetZoom();
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.key === "h" || e.key === "H" || e.key === "Shift") {
        setIsPeeking(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, [
    isPeeking,
    mode,
    currentPage,
    totalPages,
    jumpToPage,
    setMode,
    zoom,
    setZoom,
    resetZoom,
    navigate,
    showShortcuts,
    setIsPeeking,
    toggleFullscreen,
  ]);

  // Next Chapter countdown trigger when reaching end of chapter
  useEffect(() => {
    if (currentPage >= totalPages && totalPages > 0 && nextChapterSlug && autoNextChapter) {
      setCountdown(5);
      const timer = setInterval(() => {
        setCountdown((c) => {
          if (c === null) return null;
          if (c <= 1) {
            clearInterval(timer);
            navigate(`/reader/${encodeURIComponent(nextChapterSlug!)}`);
            return null;
          }
          return c - 1;
        });
      }, 1000);
      return () => clearInterval(timer);
    } else {
      setCountdown(null);
    }
  }, [currentPage, totalPages, nextChapterSlug, autoNextChapter, navigate]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-background text-muted-foreground gap-3">
        <Sparkles className="w-8 h-8 text-primary animate-pulse" />
        <span className="text-sm font-medium">กำลังเตรียมหน้าอ่านมังงะ...</span>
      </div>
    );
  }

  if (isError || !chapter) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-background text-foreground p-6 text-center space-y-4">
        <div className="w-16 h-16 rounded-2xl bg-destructive/15 text-destructive flex items-center justify-center text-2xl border border-destructive/30 shadow-lg glow-primary">
          <AlertCircle className="w-8 h-8" />
        </div>
        <div className="space-y-1">
          <h2 className="text-xl font-bold text-foreground">
            ไม่พบตอนมังงะนี้ในระบบ (404 Not Found)
          </h2>
          <p className="text-xs text-muted-foreground max-w-md">
            ไฟล์ของตอนนี้อาจยังไม่ได้ดาวน์โหลด หรือถูกลบออกจากเครื่องแล้ว
          </p>
        </div>

        <div className="p-3 rounded-xl bg-secondary/60 border border-border text-xs font-mono text-muted-foreground max-w-md w-full truncate">
          slug: {slug}
        </div>

        <div className="flex items-center gap-3 pt-2 flex-wrap justify-center">
          <button
            onClick={() => openJobModal()}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 via-primary to-indigo-600 text-white font-semibold text-xs shadow-lg shadow-primary/30 hover:brightness-110 active:scale-95 transition-all cursor-pointer"
          >
            <Sparkles className="w-4 h-4" />
            <span>ดาวน์โหลดและแปลตอนนี้</span>
          </button>
          <button
            onClick={() => navigate("/")}
            className="px-4 py-2.5 rounded-xl bg-secondary text-foreground text-xs font-semibold hover:bg-card border border-border transition-all"
          >
            กลับสู่หน้าแดชบอร์ด
          </button>
          <button
            onClick={() => navigate("/library")}
            className="px-4 py-2.5 rounded-xl bg-secondary text-foreground text-xs font-semibold hover:bg-card border border-border transition-all"
          >
            ไปที่คลังมังงะ
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 bg-[#06070a] text-foreground flex flex-col z-50 select-none overflow-hidden"
    >
      {/* 1. Top HUD Toolbar (Glassmorphism & Auto-Hide on mouse idle or toggle) */}
      <div
        className={`flex items-center justify-between px-4 py-3 bg-card/85 backdrop-blur-2xl border-b border-border/80 transition-all duration-300 z-40 shrink-0 ${
          showHud ? "translate-y-0" : "-translate-y-full"
        }`}
      >
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => navigate(-1)}
            className="p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
            title="กลับ (Esc)"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>

          <div className="min-w-0">
            <h2 className="text-sm font-bold text-foreground truncate" title={chapter.title}>
              {chapter.title}
            </h2>
            <div className="text-[11px] text-muted-foreground flex items-center gap-2">
              <span>หน้า {currentPage} จาก {totalPages}</span>
              {isPeeking ? (
                <span className="text-amber-400 font-bold animate-pulse">
                  [PEEK] กำลังดูภาพต้นฉบับ (EN)
                </span>
              ) : showTranslated ? (
                <span className="text-emerald-400 font-semibold">
                  ✓ ภาษาไทย (Google Lens)
                </span>
              ) : (
                <span className="text-muted-foreground">ต้นฉบับอังกฤษ</span>
              )}
            </div>
          </div>
        </div>

        {/* Controls Toolbar */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Hold to Peek Eye Button */}
          <button
            onMouseDown={() => setIsPeeking(true)}
            onMouseUp={() => setIsPeeking(false)}
            onTouchStart={() => setIsPeeking(true)}
            onTouchEnd={() => setIsPeeking(false)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all cursor-pointer ${
              isPeeking
                ? "bg-amber-500 text-black border-amber-400 shadow-md shadow-amber-500/30"
                : "bg-secondary text-muted-foreground hover:text-foreground hover:bg-card border-border"
            }`}
            title="กดค้างไว้เพื่อดูภาพต้นฉบับ (คีย์ลัด: กด H หรือ Shift ค้าง)"
          >
            {isPeeking ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            <span className="hidden sm:inline">
              {isPeeking ? "ปล่อยเพื่อแปลไทย" : "กดค้างเทียบภาพ (H)"}
            </span>
          </button>

          {/* Mode Switcher */}
          <div className="flex items-center gap-0.5 bg-secondary/80 rounded-xl p-1 border border-border">
            <button
              onClick={() => setMode("long-strip")}
              className={`p-1.5 rounded-lg transition-all ${
                mode === "long-strip"
                  ? "bg-primary text-white shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              title="เลื่อนแนวตั้ง (Long Strip)"
            >
              <Rows3 className="w-4 h-4" />
            </button>
            <button
              onClick={() => setMode("page-by-page")}
              className={`p-1.5 rounded-lg transition-all ${
                mode === "page-by-page"
                  ? "bg-primary text-white shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              title="ทีละหน้า (Page by Page)"
            >
              <BookOpen className="w-4 h-4" />
            </button>
            <button
              onClick={() => setMode("double-page")}
              className={`p-1.5 rounded-lg transition-all ${
                mode === "double-page"
                  ? "bg-primary text-white shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              title="หน้าคู่ (Double Page)"
            >
              <Columns2 className="w-4 h-4" />
            </button>
            <button
              onClick={() => setMode("pdf")}
              className={`p-1.5 rounded-lg transition-all ${
                mode === "pdf"
                  ? "bg-primary text-white shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              title="โหมดเอกสาร PDF (PDF Viewer)"
            >
              <FileText className="w-4 h-4" />
            </button>
          </div>

          {/* Direct PDF Link */}
          {pdfUrl && (
            <a
              href={pdfUrl}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-violet-600/20 text-violet-300 hover:bg-violet-600 hover:text-white border border-violet-500/30 text-xs font-semibold transition-all cursor-pointer"
              title="เปิดไฟล์ PDF ฉบับเต็มในแท็บใหม่"
            >
              <FileDown className="w-4 h-4 text-cyan-400" />
              <span className="hidden sm:inline">เปิด PDF</span>
            </a>
          )}

          {/* Zoom Controls */}
          <div className="hidden md:flex items-center gap-1 bg-secondary/80 rounded-xl p-1 border border-border text-xs">
            <button
              onClick={() => setZoom(zoom - 15)}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground"
              title="ลดขนาด (-)"
            >
              <ZoomOut className="w-4 h-4" />
            </button>
            <button
              onClick={resetZoom}
              className="px-2 py-0.5 font-mono text-[11px] text-muted-foreground hover:text-foreground"
              title="รีเซ็ต (0)"
            >
              {zoom}%
            </button>
            <button
              onClick={() => setZoom(zoom + 15)}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground"
              title="เพิ่มขนาด (+)"
            >
              <ZoomIn className="w-4 h-4" />
            </button>
          </div>

          {/* Touch-up Studio Button */}
          <button
            onClick={() => {
              setTouchupPageNo(currentPage);
              setIsTouchupOpen(true);
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-600/20 text-emerald-300 hover:bg-emerald-600 hover:text-white border border-emerald-500/30 text-xs font-semibold transition-all cursor-pointer shadow-sm"
            title="เปิดเครื่องมือลบคราบ / แต่งภาพหน้านี้ (Touch-up Studio)"
          >
            <Paintbrush className="w-3.5 h-3.5 text-emerald-400" />
            <span className="hidden sm:inline">Touch-up</span>
          </button>

          {/* AI Refine Comparison Panel Toggle */}
          <button
            id="btn-toggle-refine-panel"
            onClick={() => setIsRefinePanelOpen(!isRefinePanelOpen)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all cursor-pointer shadow-sm ${
              isRefinePanelOpen
                ? "bg-fuchsia-600 text-white border-fuchsia-500 shadow-fuchsia-500/20"
                : "bg-fuchsia-600/20 text-fuchsia-300 hover:bg-fuchsia-600 hover:text-white border-fuchsia-500/30"
            }`}
            title="เปิด/ปิด หน้าต่างเปรียบเทียบสำนวน AI (Ollama TranslateGemma)"
          >
            <Sparkles className="w-3.5 h-3.5 text-fuchsia-400" />
            <span className="hidden sm:inline">สำนวน AI</span>
            {currentPageInfo?.refined_text && (
              <span className="w-1.5 h-1.5 rounded-full bg-fuchsia-300 animate-pulse" />
            )}
          </button>

          {/* Fullscreen & Help */}
          <button
            onClick={toggleFullscreen}
            className="p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
            title="เต็มจอ (F)"
          >
            {isFullscreen ? <Minimize className="w-4 h-4" /> : <Maximize className="w-4 h-4" />}
          </button>

          <button
            onClick={() => setShowShortcuts(true)}
            className="p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
            title="คีย์ลัด (?)"
          >
            <HelpCircle className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 2. Main Reader Canvas & AI Refine Comparison Panel */}
      <div className="flex-1 flex overflow-hidden relative w-full">
        <div
          ref={canvasRef}
          onScroll={handleCanvasScroll}
          className="flex-1 overflow-y-auto overflow-x-hidden relative flex flex-col items-center justify-start p-2 sm:p-4"
          style={{ scrollBehavior: "smooth" }}
        >
        {/* Mode: Long Strip */}
        {mode === "long-strip" && (
          <div
            className="flex flex-col items-center gap-2 max-w-4xl w-full mx-auto"
            style={{ width: `${zoom}%` }}
          >
            {pages.map((p, index) => (
              <div
                key={p.page}
                id={`page-${p.page}`}
                className="group relative w-full shadow-2xl bg-black rounded-lg overflow-hidden border border-border/40"
              >
                <img
                  src={getImageUrl(p)}
                  alt={`Page ${p.page}`}
                  loading={index < 4 ? "eager" : "lazy"}
                  className="w-full h-auto object-contain block mx-auto"
                />
                <div className="absolute top-3 right-3 flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setTouchupPageNo(p.page);
                      setIsTouchupOpen(true);
                    }}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-neutral-900/85 hover:bg-emerald-600 text-neutral-200 hover:text-white text-[11px] font-medium backdrop-blur-md border border-neutral-700/60 shadow-lg transition-all cursor-pointer"
                    title="ลบคราบ / แต่งภาพหน้านี้"
                  >
                    <Paintbrush className="w-3 h-3 text-emerald-400" />
                    <span>Touch-up</span>
                  </button>
                </div>
                <div className="absolute bottom-2 right-2 px-2 py-0.5 rounded-md bg-black/70 backdrop-blur-sm text-[10px] text-muted-foreground font-mono">
                  {p.page}
                </div>
              </div>
            ))}

            {/* End of Chapter Card */}
            <div className="w-full my-12 p-8 rounded-2xl bg-card border border-border/80 text-center space-y-4 glass-panel max-w-xl mx-auto">
              <div className="w-12 h-12 rounded-2xl bg-primary/20 text-primary flex items-center justify-center mx-auto text-xl">
                🎉
              </div>
              <h3 className="text-lg font-bold text-foreground">
                จบตอน "{chapter.title}" แล้ว
              </h3>
              <p className="text-xs text-muted-foreground">
                คุณได้อ่านครบทั้ง {totalPages} หน้าเรียบร้อยแล้ว
              </p>

              {nextChapterSlug ? (
                <div className="pt-2 space-y-2">
                  <button
                    onClick={() => navigate(`/reader/${encodeURIComponent(nextChapterSlug!)}`)}
                    className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-gradient-to-r from-violet-600 to-primary text-white font-semibold text-sm shadow-lg shadow-primary/25 hover:brightness-110 active:scale-95 transition-all cursor-pointer"
                  >
                    <span>อ่านตอนถัดไปทันที</span>
                    <ArrowRight className="w-4 h-4" />
                  </button>
                  {countdown !== null && (
                    <div className="text-xs text-primary animate-pulse">
                      กำลังเปลี่ยนไปตอนถัดไปอัตโนมัติใน {countdown} วินาที...
                    </div>
                  )}
                </div>
              ) : (
                <button
                  onClick={() => navigate("/library")}
                  className="px-5 py-2.5 rounded-xl bg-secondary text-foreground text-xs font-semibold hover:bg-card border border-border"
                >
                  กลับสู่คลังมังงะ
                </button>
              )}
            </div>
          </div>
        )}

        {/* Mode: Page-by-Page */}
        {mode === "page-by-page" && (
          <div className="flex-1 flex flex-col items-center justify-center w-full max-w-4xl mx-auto relative">
            {pages[currentPage - 1] && (
              <div
                className="relative max-h-[85vh] flex items-center justify-center shadow-2xl rounded-xl overflow-hidden bg-black border border-border/40"
                style={{ transform: `scale(${zoom / 100})`, transformOrigin: "center center" }}
              >
                <img
                  src={getImageUrl(pages[currentPage - 1])}
                  alt={`Page ${currentPage}`}
                  className="max-h-[85vh] w-auto object-contain"
                />
              </div>
            )}

            {/* Click navigation overlays */}
            <div
              onClick={() => jumpToPage(Math.max(currentPage - 1, 1))}
              className="absolute left-0 inset-y-0 w-1/4 cursor-w-resize flex items-center justify-start pl-4 group"
              title="หน้าก่อนหน้า (←)"
            >
              <div className="p-3 rounded-full bg-black/60 text-white/50 group-hover:text-white group-hover:bg-black/80 transition-all opacity-0 group-hover:opacity-100">
                <ChevronLeft className="w-6 h-6" />
              </div>
            </div>

            <div
              onClick={() => {
                if (currentPage < totalPages) {
                  jumpToPage(currentPage + 1);
                } else if (nextChapterSlug) {
                  navigate(`/reader/${encodeURIComponent(nextChapterSlug)}`);
                }
              }}
              className="absolute right-0 inset-y-0 w-1/4 cursor-e-resize flex items-center justify-end pr-4 group"
              title="หน้าถัดไป (→)"
            >
              <div className="p-3 rounded-full bg-black/60 text-white/50 group-hover:text-white group-hover:bg-black/80 transition-all opacity-0 group-hover:opacity-100">
                <ChevronRight className="w-6 h-6" />
              </div>
            </div>
          </div>
        )}

        {/* Mode: Double Page (Book spread) */}
        {mode === "double-page" && (
          <div className="flex-1 flex items-center justify-center w-full max-w-6xl mx-auto gap-1">
            {/* Left Page */}
            {pages[currentPage - 1] && (
              <div className="max-h-[85vh] flex items-center justify-center bg-black rounded-lg overflow-hidden border border-border/40 shadow-xl">
                <img
                  src={getImageUrl(pages[currentPage - 1])}
                  alt={`Page ${currentPage}`}
                  className="max-h-[85vh] w-auto object-contain"
                />
              </div>
            )}
            {/* Right Page */}
            {pages[currentPage] && (
              <div className="max-h-[85vh] flex items-center justify-center bg-black rounded-lg overflow-hidden border border-border/40 shadow-xl">
                <img
                  src={getImageUrl(pages[currentPage])}
                  alt={`Page ${currentPage + 1}`}
                  className="max-h-[85vh] w-auto object-contain"
                />
              </div>
            )}
          </div>
        )}

        {/* Mode: PDF Viewer */}
        {mode === "pdf" && (
          <div className="flex-1 w-full h-full max-w-6xl mx-auto flex flex-col p-2">
            {pdfUrl ? (
              <iframe
                src={pdfUrl}
                className="w-full h-[calc(100vh-130px)] rounded-xl border border-border/70 bg-[#0d0e12] shadow-2xl"
                title={`PDF - ${chapter.title}`}
              />
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-8 space-y-3">
                <AlertCircle className="w-8 h-8 text-amber-400" />
                <p className="text-sm font-semibold">ไม่พบไฟล์ PDF สำหรับตอนนี้</p>
                <p className="text-xs text-muted-foreground">
                  คุณสามารถอ่านผ่านโหมดเลื่อนแนวตั้ง (Long Strip) หรือทีละหน้าได้ตามปกติ
                </p>
              </div>
            )}
          </div>
        )}
        </div>

        {/* AI Refine Comparison Side Panel */}
        {isRefinePanelOpen && (
          <aside className="w-80 sm:w-96 border-l border-border/80 bg-card/95 backdrop-blur-2xl flex flex-col h-full z-30 shadow-2xl shrink-0 animate-in slide-in-from-right duration-200">
            {/* Header */}
            <div className="p-4 border-b border-border/70 flex items-center justify-between gap-3 shrink-0 bg-secondary/30">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-xl bg-fuchsia-500/15 text-fuchsia-400 flex items-center justify-center border border-fuchsia-500/25 shadow-sm">
                  <Sparkles className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground">เปรียบเทียบสำนวน AI</h3>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="text-[11px] text-muted-foreground font-medium">
                      หน้า {currentPage} จาก {totalPages}
                    </span>
                    {currentPageInfo?.refined_text && (
                      <span className="px-1.5 py-0.2 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                        ขัดเกลาแล้ว
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <button
                onClick={() => setIsRefinePanelOpen(false)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
                title="ปิดหน้าต่างเปรียบเทียบ"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Content Body */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {refineError && (
                <div className="p-3 rounded-xl bg-destructive/15 border border-destructive/30 text-destructive text-xs space-y-1 animate-in fade-in">
                  <div className="flex items-center gap-1.5 font-bold">
                    <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                    <span>เกิดข้อผิดพลาด</span>
                  </div>
                  <p className="text-[11px] leading-relaxed opacity-90">{refineError}</p>
                </div>
              )}

              {/* 1. Google Lens Original Text Card */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                    <Languages className="w-3 h-3 text-cyan-400" />
                    Google Lens (แปลดิบ)
                  </span>
                  {currentPageInfo?.original_text && (
                    <button
                      onClick={() => handleCopy(currentPageInfo.original_text!, false)}
                      className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                      title="คัดลอกข้อความ Lens"
                    >
                      {copiedOriginal ? (
                        <>
                          <Check className="w-3 h-3 text-emerald-400" />
                          <span className="text-emerald-400">คัดลอกแล้ว</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3 h-3" />
                          <span>คัดลอก</span>
                        </>
                      )}
                    </button>
                  )}
                </div>
                <div className="p-3.5 rounded-xl bg-secondary/60 border border-border/70 text-xs leading-relaxed text-foreground/90 font-sans whitespace-pre-wrap select-text max-h-56 overflow-y-auto">
                  {currentPageInfo?.original_text ? (
                    currentPageInfo.original_text
                  ) : (
                    <span className="text-muted-foreground italic">ไม่มีข้อความที่ตรวจจับได้สำหรับหน้านี้</span>
                  )}
                </div>
              </div>

              {/* 2. Ollama TranslateGemma Refined Text Card */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-fuchsia-300 uppercase tracking-wider flex items-center gap-1">
                    <Sparkles className="w-3 h-3 text-fuchsia-400" />
                    Ollama TranslateGemma 12B
                  </span>
                  {currentPageInfo?.refined_text && (
                    <button
                      onClick={() => handleCopy(currentPageInfo.refined_text!, true)}
                      className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                      title="คัดลอกข้อความที่ขัดเกลาแล้ว"
                    >
                      {copiedRefined ? (
                        <>
                          <Check className="w-3 h-3 text-emerald-400" />
                          <span className="text-emerald-400">คัดลอกแล้ว</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3 h-3" />
                          <span>คัดลอก</span>
                        </>
                      )}
                    </button>
                  )}
                </div>

                {currentPageInfo?.refined_text ? (
                  <div className="p-3.5 rounded-xl bg-gradient-to-br from-fuchsia-950/25 via-fuchsia-900/10 to-card border border-fuchsia-500/35 text-xs leading-relaxed text-fuchsia-50 font-sans whitespace-pre-wrap select-text shadow-sm max-h-72 overflow-y-auto">
                    {currentPageInfo.refined_text}
                  </div>
                ) : (
                  <div className="p-5 rounded-xl bg-secondary/30 border border-dashed border-border/80 text-center space-y-2">
                    <div className="w-9 h-9 rounded-xl bg-fuchsia-500/10 text-fuchsia-400 flex items-center justify-center mx-auto">
                      <Sparkles className="w-4 h-4" />
                    </div>
                    <p className="text-xs font-semibold text-foreground">ยังไม่ได้ขัดเกลาสำนวนหน้านี้</p>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      กดปุ่มขัดเกลาด้านล่างเพื่อส่งบทสนทนานี้ให้ TranslateGemma ปรับสำนวนไทยให้อ่านลื่นและมีอรรถรสเหมือนมังงะแปลไทยแท้
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Action Footer */}
            <div className="p-4 border-t border-border/70 bg-secondary/30 space-y-2 shrink-0">
              <button
                id="btn-refine-current-page"
                onClick={() => handleRefineCurrentPage(true)}
                disabled={isRefiningPage || !currentPageInfo?.original_text}
                className="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-fuchsia-600 to-violet-600 text-white text-xs font-bold shadow-md shadow-fuchsia-600/20 hover:brightness-110 active:scale-95 disabled:opacity-50 disabled:pointer-events-none transition-all flex items-center justify-center gap-2 cursor-pointer"
                title={
                  !currentPageInfo?.original_text
                    ? "หน้านี้ไม่มีข้อความต้นฉบับจาก Lens"
                    : "เริ่มขัดเกลาสำนวนหน้านี้ด้วย Ollama TranslateGemma"
                }
              >
                {isRefiningPage ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>กำลังขัดเกลาสำนวนหน้านี้...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    <span>
                      {currentPageInfo?.refined_text ? "ขัดเกลาหน้านี้ซ้ำ (Re-refine)" : "ขัดเกลาหน้านี้ (AI Refine)"}
                    </span>
                  </>
                )}
              </button>

              <button
                onClick={handleRefineWholeChapter}
                className="w-full py-1.5 px-3 rounded-lg text-xs font-semibold text-muted-foreground hover:text-fuchsia-300 hover:bg-secondary transition-all flex items-center justify-center gap-1.5 cursor-pointer"
                title="เริ่มงานขัดเกลาทุกหน้าของตอนนี้ในเบื้องหลัง"
              >
                <span>ขัดเกลาทั้งตอน ({totalPages} หน้า)</span>
              </button>
            </div>
          </aside>
        )}
      </div>

      {/* 3. Bottom Scrubber & Quick Slider (For Page-by-Page & Double-Page) */}
      <div className="px-6 py-2.5 bg-card/85 backdrop-blur-2xl border-t border-border/80 flex items-center justify-between gap-4 z-40 shrink-0">
        <div className="flex items-center gap-2">
          {prevChapterSlug ? (
            <button
              onClick={() => navigate(`/reader/${encodeURIComponent(prevChapterSlug!)}`)}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-secondary text-xs text-muted-foreground hover:text-foreground transition-all"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              ตอนก่อนหน้า
            </button>
          ) : (
            <div />
          )}
        </div>

        {/* Page Slider / Scrubber */}
        <div className="flex-1 max-w-md flex items-center gap-3">
          <button
            onClick={() => jumpToPage(Math.max(currentPage - 1, 1), true)}
            disabled={currentPage <= 1}
            className="p-1 rounded-lg text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer transition-colors"
            title="หน้าก่อนหน้า"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>

          <input
            type="range"
            min={1}
            max={totalPages || 1}
            value={currentPage}
            onInput={(e) => jumpToPage(parseInt((e.target as HTMLInputElement).value, 10), false)}
            onChange={(e) => jumpToPage(parseInt(e.target.value, 10), true)}
            className="flex-1 accent-primary h-2 bg-secondary rounded-lg cursor-pointer py-1"
          />

          <button
            onClick={() => jumpToPage(Math.min(currentPage + 1, totalPages), true)}
            disabled={currentPage >= totalPages}
            className="p-1 rounded-lg text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer transition-colors"
            title="หน้าถัดไป"
          >
            <ChevronRight className="w-4 h-4" />
          </button>

          <span className="text-xs font-mono text-muted-foreground min-w-[50px] text-right select-none">
            {currentPage} / {totalPages}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {nextChapterSlug ? (
            <button
              onClick={() => navigate(`/reader/${encodeURIComponent(nextChapterSlug!)}`)}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-primary/20 text-violet-300 hover:bg-primary hover:text-white text-xs font-semibold transition-all"
            >
              ตอนถัดไป
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          ) : (
            <div />
          )}
        </div>
      </div>

      {/* 4. Keyboard Shortcuts Modal */}
      {showShortcuts && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="w-full max-w-md rounded-2xl bg-card border border-border/80 shadow-2xl p-6 space-y-4 glass-panel">
            <div className="flex items-center justify-between border-b border-border/60 pb-3">
              <div className="flex items-center gap-2">
                <Compass className="w-5 h-5 text-primary" />
                <h3 className="text-base font-bold text-foreground">
                  คีย์ลัดการใช้งาน Reader
                </h3>
              </div>
              <button
                onClick={() => setShowShortcuts(false)}
                className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2.5 text-xs">
              <div className="flex justify-between py-1 border-b border-border/40">
                <span className="text-muted-foreground">กดค้างเพื่อดูภาพต้นฉบับอังกฤษ</span>
                <kbd className="px-2 py-0.5 rounded bg-secondary font-mono text-primary font-bold">
                  H หรือ Shift ค้าง
                </kbd>
              </div>
              <div className="flex justify-between py-1 border-b border-border/40">
                <span className="text-muted-foreground">หน้าถัดไป / ย้อนกลับ</span>
                <kbd className="px-2 py-0.5 rounded bg-secondary font-mono text-foreground">
                  → / ← หรือ Spacebar
                </kbd>
              </div>
              <div className="flex justify-between py-1 border-b border-border/40">
                <span className="text-muted-foreground">สลับโหมดอ่าน (Scroll/Page/Double/PDF)</span>
                <kbd className="px-2 py-0.5 rounded bg-secondary font-mono text-foreground">
                  M
                </kbd>
              </div>
              <div className="flex justify-between py-1 border-b border-border/40">
                <span className="text-muted-foreground">เปิด / ปิด หน้าต่างเต็มจอ</span>
                <kbd className="px-2 py-0.5 rounded bg-secondary font-mono text-foreground">
                  F
                </kbd>
              </div>
              <div className="flex justify-between py-1 border-b border-border/40">
                <span className="text-muted-foreground">ซูมเข้า / ออก / รีเซ็ต</span>
                <kbd className="px-2 py-0.5 rounded bg-secondary font-mono text-foreground">
                  + / - / 0
                </kbd>
              </div>
              <div className="flex justify-between py-1 border-b border-border/40">
                <span className="text-muted-foreground">ออกจากหน้าอ่านมังงะ</span>
                <kbd className="px-2 py-0.5 rounded bg-secondary font-mono text-foreground">
                  Esc
                </kbd>
              </div>
            </div>

            <div className="pt-2 text-center">
              <button
                onClick={() => setShowShortcuts(false)}
                className="px-5 py-2 rounded-xl bg-primary text-white font-semibold text-xs"
              >
                เข้าใจแล้ว
              </button>
            </div>
          </div>
        </div>
      )}
      {/* 5. Touch-up Studio Modal */}
      {pages[touchupPageNo - 1] && (
        <TouchupModal
          isOpen={isTouchupOpen}
          onClose={() => setIsTouchupOpen(false)}
          chapterSlug={slug || ""}
          pageNumber={touchupPageNo}
          imageUrl={getImageUrl(pages[touchupPageNo - 1])}
          onSaved={() => {
            setImgTimestamp(Date.now());
          }}
        />
      )}
    </div>
  );
}
