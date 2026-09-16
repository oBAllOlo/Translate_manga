# Ticket 01: Core LLM Refine Module

## Description
Implement the pure logic module `core/refine.py` that interacts with Ollama to refine Thai manga translations.

## Requirements
- Reads `lens_translations.json` from chapter work directory.
- Reads `llm_refined.json` for caching (skip already-refined pages unless `force=True`).
- Checks Ollama health (`GET /api/tags`) and validates model availability before starting.
- Sequential page-by-page calls to Ollama chat endpoint (`POST /api/chat`) with manga translator persona system prompt.
- Saves progress and results to `llm_refined.json`.
- Supports `on_progress(done, total)` callback.
- Configurable via `OLLAMA_BASE_URL` and `OLLAMA_MODEL`.
- Comprehensive unit tests at the `core/refine.py` seam with mocked HTTP responses.
