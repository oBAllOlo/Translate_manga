# Ticket 03: Chapter Status & Refine All UI

## Description
Expose refine operations and status indicators in the frontend library and chapter drawer.

## Requirements
- API client functions in `frontend/src/api/client.ts`: `refineChapter`, `refineChapterPage`.
- Updated TypeScript interfaces (`ChapterSummary`, `ChapterDetail`, `PageInfo`).
- Visual indicator (badge) for chapters with refined translations in `frontend/src/components/library/chapter-drawer.tsx` and `frontend/src/pages/library.tsx`.
- "Refine All" action button for chapters with translations.
