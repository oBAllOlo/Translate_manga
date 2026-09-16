/** API client + TanStack Query configuration. */
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: true, retry: 1, staleTime: 5_000 },
  },
});

const BASE = "";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Jobs ──────────────────────────────────────────────────────
export interface Job {
  id: string;
  url: string;
  title?: string;
  slug?: string;
  work_dir?: string;
  status: string;
  message?: string;
  total_pages?: number;
  downloaded?: number;
  translated?: number;
  failed?: number;
  pdf?: string;
  is_range?: boolean;
  total_chapters?: number;
  done_chapters?: number;
  current_chapter?: number;
  created_at?: string;
  updated_at?: string;
}

export const fetchJobs = () => request<{ jobs: Job[]; active: boolean }>("/api/jobs");
export const createJob = (url: string, chunk = 8, concurrency = 8) =>
  request<{ id: string }>("/api/jobs", {
    method: "POST",
    body: JSON.stringify({ url, chunk, concurrency }),
  });
export const createRangeJob = (base_url: string, start: number, end: number, chunk = 8, concurrency = 8) =>
  request<{ id: string }>("/api/jobs/range", {
    method: "POST",
    body: JSON.stringify({ base_url, start, end, chunk, concurrency }),
  });
export const deleteAllJobs = () =>
  request<{ ok: boolean }>("/api/jobs", { method: "DELETE" });
export const deleteJob = (id: string) =>
  request<{ ok: boolean }>(`/api/jobs/${id}`, { method: "DELETE" });


// ── Chapters ──────────────────────────────────────────────────
export interface ChapterSummary {
  name: string;
  title: string;
  page_count?: number;
  translated_count: number;
  pdfs: string[];
  thumb?: string;
  thumb_kind: string;
  has_failed: boolean;
  mtime: number;
  series_title?: string;
}

export interface SeriesGroup {
  series_title: string;
  chapters: ChapterSummary[];
  chapter_count: number;
  thumb?: string;
  thumb_name?: string;
}

export interface PageInfo {
  page: number;
  file?: string;
  url?: string;
  translated_file?: string;
  has_translation: boolean;
}

export interface ChapterDetail {
  name: string;
  title: string;
  source?: string;
  page_count?: number;
  translated_count: number;
  pages: PageInfo[];
  pdfs: string[];
  has_failed: boolean;
}

export const fetchChapters = () =>
  request<{ chapters: ChapterSummary[]; series: SeriesGroup[] }>("/api/chapters");
export const fetchChapter = (name: string) =>
  request<ChapterDetail>(`/api/chapters/${encodeURIComponent(name)}`);
export const translateChapter = (name: string) =>
  request<{ job_id: string }>(`/api/chapters/${encodeURIComponent(name)}/translate`, { method: "POST" });
export const retryChapter = (name: string) =>
  request<{ job_id: string }>(`/api/chapters/${encodeURIComponent(name)}/retry`, { method: "POST" });
export const deleteChapter = (name: string) =>
  request<{ deleted: string }>(`/api/chapters/${encodeURIComponent(name)}`, { method: "DELETE" });
export const deleteAllChapters = () =>
  request<{ deleted: string[]; count: number }>("/api/chapters", { method: "DELETE" });
export const touchupPage = (name: string, page: number, imageData: string) =>
  request<{ success: boolean; page: number; file: string }>(
    `/api/chapters/${encodeURIComponent(name)}/pages/${page}/touchup`,
    {
      method: "POST",
      body: JSON.stringify({ image_data: imageData }),
    }
  );
export const recleanPage = (name: string, page: number) =>
  request<{ success: boolean; page: number; file: string }>(
    `/api/chapters/${encodeURIComponent(name)}/pages/${page}/reclean`,
    {
      method: "POST",
      body: JSON.stringify({}),
    }
  );

/** Resolves any raw PDF path to a clean browser-accessible /output/ URL */
export function resolvePdfUrl(pdfPath?: string): string {
  if (!pdfPath) return "";
  const normalized = pdfPath
    .replace(/\\/g, "/")
    .replace(/^[A-Za-z]:.*?[\\/]output[\\/]/i, "")
    .replace(/^\/?(?:\.\.\/)?output\//i, "")
    .replace(/^\.\.\//, "")
    .replace(/^\/+/, "");
  return `/output/${normalized}`;
}
