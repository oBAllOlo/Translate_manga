# Manga Translate — Domain Glossary

> This file defines the canonical vocabulary for the project.
> It is **not** a spec or implementation guide — just terms and their meanings.

## Core Concepts

| Term | Definition |
|------|-----------|
| **Chapter** | A single downloadable unit of manga pages from a source site. Identified by a slug derived from the source URL. |
| **Series** | A group of Chapters that belong to the same manga title. Chapters are grouped by matching manga title from their manifest metadata. |
| **Page** | One image within a Chapter, numbered sequentially (1-indexed). Exists as both an *original* and optionally a *translated* variant. |
| **Parser** | A pluggable module that extracts page image URLs and chapter title from a specific source website (e.g., MangaDex, WeebCentral). |
| **Source Site** | A website that hosts manga pages. Each site requires its own Parser. Currently supported: MangaDex, WeebCentral, MangaBlaze, IsekaiNonbiri. |
| **Job** | A unit of background work: downloading pages, translating via Lens, and/or building a PDF. Has lifecycle states: `queued → parsing → downloading → translating → done \| error`. |
| **Translation** | The process of overlaying Thai text onto a manga page image using Google Lens. The result is a new image with translated text rendered in-place. |
| **Lens Core** | The vendored `lens_images_core` library that communicates with Google Lens via Chrome DevTools Protocol (CDP) to perform image translation. |
| **Manifest** | A `manifest.json` file inside a Chapter's work directory. Records source URL, title, page count, and per-page metadata. |
| **Work Directory** | The filesystem folder for a single Chapter under `output/<chapter-slug>/`. Contains `images/`, `translated_images/`, `manifest.json`, and translation metadata. |
| **Long Strip PDF** | A PDF where multiple page images are stacked vertically on a single tall page (like webtoon scrolling), chunked by a configurable number of pages. |
| **Reader** | The in-browser manga viewing interface. Supports three modes: *Long Strip* (continuous vertical scroll), *Page-by-Page* (discrete page navigation), and *Double Page* (two-page book spread). |
| **Library** | The UI view showing all downloaded Chapters, grouped by Series, with search/filter/sort capabilities. |
| **Dashboard** | The command center UI view showing system statistics, continue reading shortcuts, and real-time job activity. |
| **Cleaning** | The process of removing original foreign text and dirty artifacts from manga speech bubbles or art panels to restore the background. |
| **Inpainting** | Algorithmic or model-based reconstruction of erased or damaged image regions behind removed text. |
| **Typesetting** | The layout, font styling, Thai word-wrapping, and rendering of translated text onto cleaned pages. |
| **Touch-up** | Manual or interactive fine-tuning of bubble cleaning, text masks, or translations directly within the Reader UI. |
| **Diff Mask** | A binary mask created by comparing an original manga page with its translated counterpart to isolate text bounding boxes and modified pixels. |
| **Bubble Inpainter** | The module responsible for erasing ghost text and blending rectangular patches to match surrounding speech bubble gradients. |
| **LLM Refine** | An optional post-processing step that sends Thai translation text from Google Lens through a local LLM (TranslateGemma 12B via Ollama) to polish phrasing, naturalness, and manga dialogue tone. |
| **Refined Text** | The polished Thai translation produced by LLM Refine, stored alongside the original Lens translation in `llm_refined.json` without overwriting the original text or re-rendering the images. |

