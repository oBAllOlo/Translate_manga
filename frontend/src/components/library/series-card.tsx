/** Series Card — displays a manga series with cover art and completion stats. */
import { useNavigate } from "react-router-dom";
import { useUIStore } from "@/stores/ui-store";
import type { SeriesGroup } from "@/api/client";
import { BookOpen, Layers, CheckCircle2, ChevronRight, Sparkles } from "lucide-react";

export function SeriesCard({ series }: { series: SeriesGroup }) {
  const navigate = useNavigate();
  const { openSeriesDrawer } = useUIStore();

  const chapters = series.chapters || [];
  const translatedChapters = chapters.filter(
    (c) => c.thumb_kind === "translated" || c.translated_count > 0
  ).length;
  const refinedChapters = chapters.filter((c) => c.has_refined).length;
  const progressPercent = Math.round(
    (translatedChapters / (chapters.length || 1)) * 100
  );
  const refinePercent = Math.round(
    (refinedChapters / (chapters.length || 1)) * 100
  );

  const thumbUrl = series.thumb
    ? `/output/${encodeURI(series.thumb_name || chapters[0]?.name || "")}/${series.thumb}`
    : null;

  return (
    <div
      onClick={() => openSeriesDrawer(series)}
      className="group relative rounded-2xl bg-card border border-border/70 hover:border-primary/50 overflow-hidden flex flex-col cursor-pointer transition-all duration-300 hover:-translate-y-1.5 hover:shadow-2xl hover:shadow-primary/15 glass-panel-interactive"
    >
      {/* Cover Image Container */}
      <div className="aspect-[3/4] bg-secondary/80 relative overflow-hidden">
        {thumbUrl ? (
          <img
            src={thumbUrl}
            alt={series.series_title}
            loading="lazy"
            className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center text-muted-foreground gap-2">
            <span className="text-4xl">📚</span>
            <span className="text-xs">ไม่มีภาพปก</span>
          </div>
        )}

        {/* Gradient Overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/20 to-transparent pointer-events-none" />

        {/* Chapter Count Badge */}
        <div className="absolute top-3 right-3 px-2.5 py-1 rounded-lg bg-background/80 backdrop-blur-md border border-white/10 text-xs font-bold text-foreground flex items-center gap-1 shadow-lg">
          <Layers className="w-3 h-3 text-primary" />
          <span>{chapters.length} ตอน</span>
        </div>

        {/* Translated & Refined Status Tags */}
        <div className="absolute top-3 left-3 flex flex-col gap-1 z-10">
          {progressPercent === 100 && (
            <div className="px-2 py-0.5 rounded-md bg-emerald-500/90 text-white text-[10px] font-bold backdrop-blur-sm shadow-md flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" />
              แปลครบแล้ว
            </div>
          )}
          {refinedChapters > 0 && (
            <div className="px-2 py-0.5 rounded-md bg-fuchsia-600/90 text-white text-[10px] font-bold backdrop-blur-sm shadow-md flex items-center gap-1">
              <Sparkles className="w-2.5 h-2.5" />
              <span>{refinedChapters === chapters.length ? "เกลา AI ครบแล้ว" : `เกลา AI ${refinedChapters}/${chapters.length}`}</span>
            </div>
          )}
        </div>
      </div>

      {/* Card Content */}
      <div className="p-4 flex-1 flex flex-col justify-between">
        <div>
          <h4
            className="text-sm font-bold text-foreground group-hover:text-primary transition-colors line-clamp-1 leading-snug"
            title={series.series_title}
          >
            {series.series_title}
          </h4>
          <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1.5 flex-wrap">
            <span>{translatedChapters} จาก {chapters.length} ตอนแปลแล้ว</span>
            {refinedChapters > 0 && (
              <span className="text-fuchsia-400 font-medium">· ✨ {refinedChapters} ตอนเกลาแล้ว</span>
            )}
          </p>
        </div>

        {/* Progress Bars */}
        <div className="mt-3 space-y-2">
          {/* Translation Progress */}
          <div className="space-y-1">
            <div className="w-full bg-secondary rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-gradient-to-r from-violet-500 to-emerald-400 h-1.5 rounded-full transition-all duration-300"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-0.5">
              <span>แปลไทย (Lens)</span>
              <span className="font-mono font-medium text-foreground">
                {progressPercent}%
              </span>
            </div>
          </div>

          {/* AI Refine Progress (if any chapters translated) */}
          {translatedChapters > 0 && (
            <div className="space-y-1">
              <div className="w-full bg-secondary rounded-full h-1.5 overflow-hidden">
                <div
                  className="bg-gradient-to-r from-fuchsia-500 to-violet-500 h-1.5 rounded-full transition-all duration-300"
                  style={{ width: `${refinePercent}%` }}
                />
              </div>
              <div className="flex items-center justify-between text-[11px] text-fuchsia-300/90 pt-0.5">
                <span className="flex items-center gap-1">
                  <Sparkles className="w-2.5 h-2.5 text-fuchsia-400" />
                  เกลาสำนวน (AI)
                </span>
                <span className="font-mono font-medium text-fuchsia-300">
                  {refinePercent}%
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
