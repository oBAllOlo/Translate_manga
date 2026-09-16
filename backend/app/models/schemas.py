"""Pydantic schemas for API request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


class JobCreate(BaseModel):
    url: str
    chunk: int = 8
    concurrency: int = Field(default=8, ge=2, le=12)


class RangeJobCreate(BaseModel):
    base_url: str
    start: int
    end: int
    chunk: int = 8
    concurrency: int = Field(default=8, ge=2, le=12)


class JobResponse(BaseModel):
    id: str
    url: str
    title: str | None = None
    status: str = "queued"
    message: str | None = None
    total_pages: int | None = None
    downloaded: int | None = None
    translated: int | None = None
    failed: int | None = None
    pdf: str | None = None
    is_range: bool = False
    total_chapters: int | None = None
    done_chapters: int | None = None
    current_chapter: int | None = None
    work_dir: str | None = None
    slug: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ---------------------------------------------------------------------------
# Chapters
# ---------------------------------------------------------------------------


class PageInfo(BaseModel):
    page: int
    file: str | None = None
    url: str | None = None
    translated_file: str | None = None
    has_translation: bool = False
    original_text: str | None = None
    refined_text: str | None = None


class RefineRequest(BaseModel):
    force: bool = False


class RefinePageResponse(BaseModel):
    page: int
    original_text: str = ""
    refined_text: str = ""
    model: str = ""
    cached: bool = False
    error: str | None = None


class TouchupRequest(BaseModel):
    image_data: str  # data:image/... base64 URL


class RecleanRequest(BaseModel):
    diff_thresh: int = 15
    dilate_px: int = 7
    inpaint_radius: int = 7


class ChapterSummary(BaseModel):
    name: str
    title: str
    page_count: int | None = None
    translated_count: int = 0
    pdfs: list[str] = []
    thumb: str | None = None
    thumb_kind: str = "none"
    has_failed: bool = False
    has_refined: bool = False
    mtime: float = 0
    series_title: str | None = None


class SeriesGroup(BaseModel):
    series_title: str
    chapters: list[ChapterSummary] = []
    chapter_count: int = 0
    thumb: str | None = None
    thumb_name: str | None = None


class ChapterDetail(BaseModel):
    name: str
    title: str
    source: str | None = None
    page_count: int | None = None
    translated_count: int = 0
    pages: list[PageInfo] = []
    pdfs: list[str] = []
    has_failed: bool = False
    has_refined: bool = False


# ---------------------------------------------------------------------------
# WebSocket messages
# ---------------------------------------------------------------------------


class WSMessage(BaseModel):
    type: str  # "job_update" | "chapter_changed" | "job_complete"
    data: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# API state
# ---------------------------------------------------------------------------


class AppState(BaseModel):
    jobs: list[JobResponse] = []
    chapters: list[ChapterSummary] = []
    series: list[SeriesGroup] = []
    active: bool = False
