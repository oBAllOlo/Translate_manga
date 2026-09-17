# 0006: Security Hardening, Input Confinement, and DoS Guardrails

We decided to implement comprehensive security hardening across the entire application stack following an in-depth security audit that identified critical vulnerabilities in static file serving, URL parser dispatch, slug extraction, client-side rendering, and unthrottled batch job scheduling.

## Decisions

1. **Canonical API Consolidation**: Establish the modern FastAPI service (`backend/app/`) as the canonical API gateway for the project. Maintain `web_app.py` only for backward compatibility while deprecating it and fixing its DOM XSS and path traversal flaws.
2. **Strict Parser Hostname Whitelist & SSRF Guard**: Replace substring matching (`domain in url`) in `core/parsers/base.py` with strict URL scheme (`http`/`https`) and hostname validation. Prohibit loopback (`127.0.0.0/8`), link-local (`169.254.0.0/16`), and private IP ranges to prevent Server-Side Request Forgery and internal port probing (such as the local Ollama daemon on port 11434).
3. **Static File Confinement**: Require all file serving endpoints (`serve_spa` in `backend/app/main.py` and `serve_output` in `backend/app/routers/files.py`) to enforce canonical path containment via `Path.resolve().is_relative_to()`. This prevents arbitrary file reads across the server filesystem.
4. **Strict Chapter Slug Sanitization**: Mandate that all chapter slug derivations from URLs or titles pass through `slugify()` and be verified as non-empty safe single-component path names, preventing traversal outside `output/`.
5. **Batch Range & DoS Guardrails**: Enforce a maximum batch limit of 50 chapters per range request in `POST /api/jobs/range` (`(body.end - body.start + 1) <= 50`) and sequential execution to protect local GPU, CPU, memory, and network resources from exhaustion.
6. **Cross-Site WebSocket Hijacking (CSWSH) Defense**: Validate the `Origin` header during WebSocket connection setup in `/ws/progress` against the trusted local origins list before accepting the connection.
7. **Prompt Injection Boundary Isolation**: Wrap third-party OCR manga dialogue in structural boundary tags (`<dialogue>...</dialogue>`) and update the system prompt in `core/refine.py` to treat enclosed content exclusively as text to polish rather than executable system instructions.

## Rationale

- **Path Traversal Protection**: Serving single-page applications and static media should never expose root repository files, SQLite databases (`manga.db`), or system configurations.
- **SSRF Prevention**: Substring checks allow attackers to smuggle internal targets through query strings or paths. Strict hostname allowlisting ensures only authentic manga source sites are fetched.
- **Resource Protection**: Manga translation involves heavy pipeline operations (headless Chrome, Google Lens CDP, ReportLab PDF chunking, OpenCV inpainting). Unbounded batch range inputs could freeze the host machine or trigger rate limits on Google Lens.
- **AI Safety**: Manga text originates from uncontrolled third-party images. Explicit boundary tagging prevents dialogue text from hijacking LLM system behavior.

## Consequences

- Requests with invalid URLs or unsupported hostnames will be rejected immediately with HTTP 400.
- Range jobs exceeding 50 chapters must be split into multiple requests.
- WebSocket clients from untrusted origins will receive a 1008 policy violation closure.
