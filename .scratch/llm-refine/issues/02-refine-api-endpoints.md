# Ticket 02: Refine API Endpoints & Job Integration

## Description
Integrate the LLM refiner into the FastAPI backend with async background job and single-page endpoints.

## Requirements
- Schemas in `backend/app/models/schemas.py` for refine request/response, and update `PageInfo`, `ChapterSummary`, `ChapterDetail`.
- Background job `run_refine_job` in `backend/app/services/job_runner.py` with progress throttle and WebSocket events.
- Endpoint `POST /api/chapters/{name}/refine` (starts background job).
- Endpoint `POST /api/chapters/{name}/pages/{page_no}/refine` (refines single page synchronously).
- Updated `GET /api/chapters/{name}` to include `has_refined` and per-page `refined_text` and `original_text`.
- Updated `_scan_chapter` in `backend/app/routers/chapters.py` to include `has_refined`.
