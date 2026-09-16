/** Global UI store for modals, drawers, and shell states. */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { SeriesGroup } from "@/api/client";

interface UIState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;

  isJobModalOpen: boolean;
  jobModalInitialUrl: string;
  openJobModal: (initialUrl?: string) => void;
  closeJobModal: () => void;

  selectedSeries: SeriesGroup | null;
  isSeriesDrawerOpen: boolean;
  openSeriesDrawer: (series: SeriesGroup) => void;
  closeSeriesDrawer: () => void;

  isShortcutsModalOpen: boolean;
  setShortcutsModalOpen: (open: boolean) => void;

  // History: tracks recently read chapters for "Continue Reading"
  continueReading: {
    chapterSlug: string;
    chapterTitle: string;
    seriesTitle?: string;
    page: number;
    thumb?: string;
    updatedAt: number;
  } | null;
  clearContinueReading: () => void;
  setContinueReading: (info: {
    chapterSlug: string;
    chapterTitle: string;
    seriesTitle?: string;
    page: number;
    thumb?: string;
  } | null) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),

      isJobModalOpen: false,
      jobModalInitialUrl: "",
      openJobModal: (initialUrl = "") =>
        set({ isJobModalOpen: true, jobModalInitialUrl: initialUrl }),
      closeJobModal: () =>
        set({ isJobModalOpen: false, jobModalInitialUrl: "" }),

      selectedSeries: null,
      isSeriesDrawerOpen: false,
      openSeriesDrawer: (series) =>
        set({ selectedSeries: series, isSeriesDrawerOpen: true }),
      closeSeriesDrawer: () =>
        set({ isSeriesDrawerOpen: false, selectedSeries: null }),

      isShortcutsModalOpen: false,
      setShortcutsModalOpen: (open) => set({ isShortcutsModalOpen: open }),

      continueReading: null,
      clearContinueReading: () => set({ continueReading: null }),
      setContinueReading: (info) =>
        set({
          continueReading: info
            ? {
                ...info,
                updatedAt: Date.now(),
              }
            : null,
        }),
    }),
    {
      name: "manga-translate-ui-store",
      partialize: (s) => ({
        sidebarCollapsed: s.sidebarCollapsed,
        continueReading: s.continueReading,
      }),
    }
  )
);
