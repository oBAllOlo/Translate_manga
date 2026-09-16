/** Reader settings store (Zustand). */
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ReaderMode = "long-strip" | "page-by-page" | "double-page" | "pdf";

interface ReaderState {
  mode: ReaderMode;
  showTranslated: boolean;
  isPeeking: boolean; // when true, temporarily shows original raw image
  currentPage: number;
  zoom: number;
  autoNextChapter: boolean;
  setMode: (mode: ReaderMode) => void;
  toggleTranslated: () => void;
  setShowTranslated: (show: boolean) => void;
  setIsPeeking: (peeking: boolean) => void;
  setPage: (page: number) => void;
  setZoom: (zoom: number) => void;
  resetZoom: () => void;
  setAutoNextChapter: (auto: boolean) => void;
}

export const useReaderStore = create<ReaderState>()(
  persist(
    (set) => ({
      mode: "long-strip",
      showTranslated: true,
      isPeeking: false,
      currentPage: 1,
      zoom: 100,
      autoNextChapter: true,
      setMode: (mode) => set({ mode }),
      toggleTranslated: () => set((s) => ({ showTranslated: !s.showTranslated })),
      setShowTranslated: (showTranslated) => set({ showTranslated }),
      setIsPeeking: (isPeeking) => set({ isPeeking }),
      setPage: (page) => set({ currentPage: page }),
      setZoom: (zoom) => set({ zoom: Math.max(25, Math.min(300, zoom)) }),
      resetZoom: () => set({ zoom: 100 }),
      setAutoNextChapter: (autoNextChapter) => set({ autoNextChapter }),
    }),
    {
      name: "manga-reader-settings",
      partialize: (s) => ({
        mode: s.mode,
        showTranslated: s.showTranslated,
        zoom: s.zoom,
        autoNextChapter: s.autoNextChapter,
      }),
    }
  )
);
