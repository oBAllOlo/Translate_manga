---
name: manga-translate-pdf
description: Download manga chapter page images and translate them to Thai using Google Lens, then generate a reading PDF. Supports WeebCentral, MangaDex, and MangaBlaze URLs. Includes batch mode, chapter ranges, retry-on-failure, and a Flask web UI.
---

# Manga Translate PDF

## Goal

```text
chapter URL
  -> download page images
  -> translate via Google Lens (overlay on image)
  -> generate a long-strip reading PDF
```

## Supported Sources

| Source | Method |
|--------|--------|
| weebcentral.com | HTTP API (`/chapters/{id}/images` with HTMX header) |
| mangadex.org | MangaDex Public API (`/at-home/server/{id}`) |
| mangablaze.com | Selenium headless Chrome (bypasses bot blocking) |

Domain detection is automatic — `from-url` / `go` / `batch` / `chapter-range` pick the right parser.

## Translation Engine

**Google Lens only.** Each downloaded page image URL is sent to Google Lens (via the local `lens_images_core` library); Lens returns a translated image (Thai overlaid on the original) which is saved and bundled into a long-strip PDF.

- No API key required
- Depends on Chrome + Selenium + Google Lens cookies + unofficial Google Lens endpoint
- Requires HTTP image URLs (so local archives / PDFs are not supported)

## Preferred Stack

- Download: Python `requests`, `BeautifulSoup`, `selenium`
- Translation: Google Lens via `Translate-image-manga-In-Page-main/lens_images_core.py`
- PDF output: `reportlab`
- Cache artifacts: `manifest.json`, `lens_translations.json`, `lens_failed.json`
- Web UI: Flask (`web_app.py`)

## Commands

### Web UI (recommended)

```powershell
.\.venv\Scripts\pip install flask
.\.venv\Scripts\python web_app.py
```

Open `http://127.0.0.1:5000`:
- Paste a chapter URL → start
- Or use **Chapter Range** form for multiple chapters
- Watch progress, open PDFs, retry failed pages, delete folders

### One-shot URL

```powershell
.\.venv\Scripts\python manga_translate.py go "https://mangadex.org/chapter/..."
```

Equivalent (more flags):

```powershell
.\.venv\Scripts\python manga_translate.py from-url "<url>" --lens-long-pdf
```

### Chapter range (MangaBlaze etc.)

```powershell
.\.venv\Scripts\python manga_translate.py chapter-range "https://mangablaze.com/manga/<slug>/" 1 5 --lens-long-pdf
```

### Batch (many URLs)

```powershell
# from file (one URL per line, # for comments)
.\.venv\Scripts\python manga_translate.py batch --file urls.txt --lens-long-pdf

# or inline
.\.venv\Scripts\python manga_translate.py batch "https://..." "https://..." --lens-long-pdf
```

### Retry failed pages

```powershell
.\.venv\Scripts\python manga_translate.py lens-retry ".\output\chapter-id" --max-retries 3
```

### PDF helpers

```powershell
# Pack until each page reaches a max height (mm) instead of fixed chunk size
.\.venv\Scripts\python manga_translate.py make-long-pdf ".\output\chapter-id" --max-page-height-mm 800
```

## Workflow

1. **Parse source.** Detect domain → call the matching parser → produce a manifest of page images.
2. **Download.** Save originals to `images/page-001.png` etc. Persist `manifest.json` with source URL and per-page metadata.
3. **Translate.** Async loop with retries (default 2). For each page, send the image URL to Google Lens; save returned data URLs to `translated_images/`. Failed pages go into `lens_failed.json` for later retry.
4. **Generate PDF.** Stack `translated_images/` into a long-strip PDF (configurable chunk size or `--max-page-height-mm`).

## Output Layout

```
output/{chapter-slug}/
  images/                 original page images
  translated_images/      Lens-translated overlays
  manifest.json           source + page list
  lens_translations.json  Lens metadata per page
  lens_failed.json        only if any pages still failed after retries
  lens-translated-long.pdf
```

## Quality Rules

- Keep all intermediate JSON files so translation can be retried without re-downloading.
- Do not overwrite previous output unless the user asks; new chapters go into their own slug folder.
- Treat downloaded manga pages as private reading assets and avoid publishing redistributed translated images/PDFs.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\pip install flask  # for the web UI
```
